"""Materialize immutable artifact packages and patch native configuration values."""

import importlib
import os
import shutil
import sys
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from ..harness import Artifact
from ..harness.artifact import relative_path
from .inspection import Baseline, fingerprint

PLUGIN_ID = "experimental-curator"


def merge(base: Any, change: Any) -> Any:
    if isinstance(base, dict) and isinstance(change, dict):
        result = deepcopy(base)
        for key, value in change.items():
            result[key] = merge(result[key], value) if key in result else deepcopy(value)
        return result
    return deepcopy(change)


def extend_artifact(active: Artifact, proposed: Artifact) -> Artifact:
    missing = set(proposed.remove) - active.values.keys()
    if missing:
        raise ValueError(f"cannot retire targets that are not currently authored: {sorted(missing)}")
    values = {name: value for name, value in active.values.items() if name not in proposed.remove}
    values = merge(values, proposed.values)
    if set(proposed.remove_files) - active.files.keys():
        raise ValueError("cannot retire supporting files that are not currently authored")
    files = {name: text for name, text in active.files.items() if name not in proposed.remove_files}
    return Artifact(values=values, files={**files, **proposed.files})


def write_package(root: Path, artifact: Artifact) -> Path:
    identity = fingerprint(artifact.model_dump(mode="json"))
    package = root / f"_curator_{identity[:20]}"
    expected = {**artifact.files}
    expected.setdefault("__init__.py", "")
    if package.exists():
        found = {
            path.relative_to(package).as_posix(): path.read_text()
            for path in package.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts
        }
        if found != expected:
            raise ValueError("artifact package content changed after materialization")
        return package
    package.mkdir(parents=True)
    for name, content in expected.items():
        path = package / relative_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return package


def qualified_reference(reference: str, package: Path) -> str:
    module, separator, function = reference.partition(":")
    if not separator:
        raise ValueError(f"invalid factory reference: {reference}")
    relative = Path(*module.split("."))
    if (package / relative).with_suffix(".py").is_file() or (package / relative / "__init__.py").is_file():
        module = f"{package.name}.{module}"
    return f"{module}:{function}"


def load_object(reference: str, package: Path):
    root = str(package.parent)
    if root not in sys.path:
        sys.path.insert(0, root)
    module, _, name = qualified_reference(reference, package).partition(":")
    try:
        loaded = importlib.import_module(module)
    except ModuleNotFoundError as exc:
        if exc.name != module:
            raise
        held = sorted(
            path.relative_to(package).as_posix()
            for path in package.rglob("*.py")
            if "__pycache__" not in path.parts and path != package / "__init__.py"
        )
        raise ModuleNotFoundError(
            f"No module named '{module}': the reference {reference} names a module that is neither installed nor "
            f"in the authored package, which holds {', '.join(held) or 'no source files'}. Put the module's complete "
            f"source in the artifact's files, for example files['{module.replace('.', '/')}.py'].",
            name=module,
        ) from exc
    return getattr(loaded, name)


def load_factory(reference: str, package: Path):
    value = load_object(reference, package)
    if not callable(value):
        raise TypeError(f"factory is not callable: {reference}")
    return value


def native_settings(baseline: Baseline, prepared) -> Baseline:
    """Apply only typed effects produced by executing the owning strategy."""
    data = baseline.export()
    data["config"] = merge(data["config"], prepared.config)
    data["extensions"] = merge(data["extensions"], prepared.extensions)
    effective = Baseline.restore(data)
    held = baseline.config.tools.disabled_tools
    effective.config.tools.disabled_tools = [
        *held,
        *(name for name in effective.config.tools.disabled_tools if name not in held),
    ]
    return effective


def _check_parent(home: Path, path: Path) -> None:
    if not path.parent.resolve().is_relative_to(home.absolute()):
        raise ValueError(f"content parent escapes agent home: {path}")


def _write(path: Path, content: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".curator-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def restore_content(home: Path, saved: dict) -> None:
    for path, (content, mode) in saved.items():
        _check_parent(home, path)
        if content is None:
            path.unlink(missing_ok=True)
        elif isinstance(content, str):
            path.unlink(missing_ok=True)
            path.symlink_to(content)
        else:
            _write(path, content, mode)


def remap_paths(paths, mapping) -> tuple[Path, ...]:
    """Move each path under the copy of the root it lies in; a path outside every mapped root stays where it is."""
    roots = sorted(((Path(a).resolve(), Path(b).resolve()) for a, b in mapping), key=lambda pair: -len(str(pair[0])))
    result = []
    for path in paths:
        path = Path(path).resolve()
        moved = next(
            (copied / path.relative_to(original) for original, copied in roots if path.is_relative_to(original)), path
        )
        result.append(moved)
    return tuple(result)


def copy_local_state(baseline: Baseline, destination: Path, exclude=(), *, remap=()) -> Baseline:
    """Copy validation inputs while retaining home/workdir ancestry and avoiding self-copy.

    The baseline's file roots move with the copy: a root inside the home or the workdir follows it, and `remap` names
    further (original, copied) pairs, such as a parent's home and workdir when a child is copied beside it.
    """
    home, workdir = baseline.config.workspace_path, baseline.workdir
    excluded = {Path(path).resolve() for path in (*exclude, destination)}

    def ignore(path, names):
        return [name for name in names if (Path(path) / name).resolve() in excluded]

    def copy(source, target):
        if source.exists():
            shutil.copytree(source, target, ignore=ignore)
        else:
            target.mkdir(parents=True)

    if home.is_relative_to(workdir):
        copied_workdir = destination / "work"
        copied_home = copied_workdir / home.relative_to(workdir)
        copy(workdir, copied_workdir)
        copied_home.mkdir(parents=True, exist_ok=True)
    elif workdir.is_relative_to(home):
        copied_home = destination / "agent"
        copied_workdir = copied_home / workdir.relative_to(home)
        copy(home, copied_home)
        copied_workdir.mkdir(parents=True, exist_ok=True)
    else:
        copied_home, copied_workdir = destination / "agent", destination / "work"
        copy(home, copied_home)
        copy(workdir, copied_workdir)
    result = Baseline.restore(baseline.export())
    result.config.agents.defaults.workspace = str(copied_home)
    result.workdir = copied_workdir
    mapping = ((home, copied_home), (workdir, copied_workdir), *remap)
    result.file_roots = remap_paths(baseline.file_roots, mapping)
    result.read_roots = remap_paths(baseline.read_roots, mapping)
    return result
