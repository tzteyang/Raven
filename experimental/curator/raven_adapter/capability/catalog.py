"""Resolve candidate contributions once and install their complete resource set."""

import hashlib
import json
import shutil
import tempfile
from copy import deepcopy
from inspect import iscoroutinefunction
from pathlib import Path

from raven.agent.tools.registry import admit_tool
from raven.config.raven import LocalDirConfig
from raven.memory_engine.skill_forge.catalog import render_skill_body

from ...harness.artifact import relative_path
from ...harness.declaration import typed
from ...harness.resources import (
    CapabilityContribution,
    RegistrationReceipt,
    SkillContribution,
    SkillView,
    ToolContribution,
)
from ..materialize import load_factory


def package_files(root: Path) -> dict[str, tuple[bytes | None, int]]:
    """Read package files and directories, refusing symlinks and special files."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError("a skill package must be a regular directory")
    files = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"skill packages cannot contain symlinks: {path.relative_to(root)}")
        if not path.is_file() and not path.is_dir():
            raise ValueError(f"skill packages cannot contain special files: {path.relative_to(root)}")
        name = relative_path(path.relative_to(root).as_posix())
        files[name] = (None if path.is_dir() else path.read_bytes(), path.stat().st_mode & 0o777)
    if "SKILL.md" not in files or files["SKILL.md"][0] is None:
        raise ValueError("a skill package requires SKILL.md")
    files["SKILL.md"][0].decode("utf-8")
    return files


def package_digest(files: dict[str, tuple[bytes | None, int]]) -> str:
    """Pin file paths, contents and executable permissions in a stable package identity."""
    manifest = [
        (name, hashlib.sha256(content).hexdigest() if content is not None else None, mode)
        for name, (content, mode) in sorted(files.items())
    ]
    return hashlib.sha256(json.dumps(manifest, separators=(",", ":")).encode()).hexdigest()


def inspect_package(root: Path) -> dict:
    """Describe actual input bytes without asking a model to reproduce binary assets."""
    files = package_files(root)
    return {
        "root": str(root),
        "digest": package_digest(files),
        "files": [
            {
                "path": name,
                "kind": "directory" if content is None else "file",
                "bytes": len(content) if content is not None else 0,
                "digest": hashlib.sha256(content).hexdigest() if content is not None else None,
                "mode": mode,
            }
            for name, (content, mode) in sorted(files.items())
        ],
    }


def materialize_tree(entries, destination: Path, *, allow_runtime_caches=False):
    """Publish one immutable tree, preserving binary files, empty directories and modes."""
    expected = dict(entries)
    if destination.is_symlink():
        raise ValueError("an immutable resource tree cannot be a symlink")
    for name in tuple(expected):
        for parent in Path(name).parents:
            if parent != Path("."):
                expected.setdefault(parent.as_posix(), (None, 0o755))
    if destination.exists():
        actual = {}
        for path in destination.rglob("*"):
            name = path.relative_to(destination).as_posix()
            if path.is_symlink():
                raise ValueError("an immutable resource tree contains a symlink")
            if (
                allow_runtime_caches
                and name not in expected
                and "__pycache__" in path.relative_to(destination).parts
                and (path.is_dir() or path.suffix == ".pyc")
            ):
                continue
            if not path.is_file() and not path.is_dir():
                raise ValueError("an immutable resource tree contains a special file")
            actual[name] = (None if path.is_dir() else path.read_bytes(), path.stat().st_mode & 0o777)
        if actual != expected:
            raise ValueError("an immutable resource tree was changed externally")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix=".staging-", dir=destination.parent))
    try:
        for name, (content, mode) in expected.items():
            path = staged / name
            if content is None:
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                path.chmod(mode)
        for name, (content, mode) in sorted(expected.items(), key=lambda item: item[0].count("/"), reverse=True):
            if content is None:
                (staged / name).chmod(mode)
        staged.rename(destination)
    finally:
        if staged.exists():
            shutil.rmtree(staged)


class CapabilityCatalog:
    """A candidate-scoped registrar, followed by one native installation.

    Registration performs validation and keeps inert implementations and package
    bytes. It does not mutate a live ToolRegistry. A closed registrar never
    accepts new entries, including an otherwise idempotent repeat.
    """

    def __init__(
        self, candidate, package, root, *, material_base, material_roots=(), resolve_interaction=None, recorder=None
    ):
        self.candidate = candidate
        self.package, self.root = Path(package), Path(root)
        self.material_base = Path(material_base).resolve()
        self.material_roots = tuple(Path(path).resolve() for path in material_roots)
        self.resolve_interaction = resolve_interaction
        self.recorder = recorder
        self.contributions = {}
        self.tools = {}
        self.deferred_tools = {}
        self.skills = {}
        self.closed = False
        self.installed = False
        self.skill_root = None
        self.receipts = []

    def _receipt(self, contribution, status, reason=None):
        receipt = RegistrationReceipt(
            name=contribution.name,
            owner=contribution.owner,
            kind=contribution.kind,
            candidate=self.candidate,
            status=status,
            reason=reason,
        )
        self.receipts.append(receipt)
        if self.recorder is not None:
            self.recorder.add("capability.registration", contribution=contribution, receipt=receipt)
        return receipt

    def register(self, contribution: CapabilityContribution) -> RegistrationReceipt:
        value = typed(CapabilityContribution, contribution)
        if self.closed:
            return self._receipt(value, "rejected", "the candidate registrar is closed")
        key = (value.kind, value.name)
        previous = self.contributions.get(key)
        if previous is not None:
            if previous == value:
                return self._receipt(value, "unchanged")
            return self._receipt(value, "rejected", "resource identity conflicts with an earlier contribution")
        try:
            if isinstance(value, ToolContribution):
                if value.factory is not None:
                    factory = load_factory(value.factory, self.package)
                    if iscoroutinefunction(factory):
                        raise TypeError("tool factories must be synchronous and inert")
                    tool = None if value.native_context else factory()
                else:
                    if self.resolve_interaction is None:
                        raise ValueError("this host has no interaction resolver")
                    tool = self.resolve_interaction(value.interaction)
                if tool is not None and admit_tool(tool).name != value.name:
                    raise ValueError("declared tool name differs from its actual implementation")
            else:
                files = self._skill_files(value)
        except (ValueError, TypeError, FileNotFoundError, UnicodeError, ModuleNotFoundError, AttributeError) as exc:
            return self._receipt(value, "rejected", str(exc))
        if isinstance(value, ToolContribution):
            if tool is None:
                self.deferred_tools[value.name] = factory
            else:
                self.tools[value.name] = tool
        else:
            self.skills[value.name] = files
        self.contributions[key] = value
        return self._receipt(value, "staged")

    def _skill_files(self, contribution: SkillContribution):
        files = {}
        if contribution.package is not None:
            location = Path(contribution.package.root)
            path = location if location.is_absolute() else self.material_base / location
            if path.is_symlink():
                raise ValueError("a skill package root cannot be a symlink")
            resolved = path.resolve()
            if not any(resolved.is_relative_to(root) for root in self.material_roots):
                raise ValueError("skill package is outside the host's material roots")
            cached = self.root / "skill-inputs" / contribution.package.digest
            if not path.exists() and cached.is_dir():
                files = package_files(cached)
            else:
                files = package_files(path)
            if package_digest(files) != contribution.package.digest:
                raise ValueError("skill package changed after inspection")
            materialize_tree(files, cached)
        for name in contribution.remove_paths:
            if name not in files:
                raise ValueError(f"cannot retire an unknown skill file: {name}")
            files = {path: value for path, value in files.items() if path != name and not path.startswith(name + "/")}
        for name, text in contribution.files.items():
            previous = files.get(name)
            files[name] = (text.encode("utf-8"), previous[1] if previous and previous[0] is not None else 0o644)
        if "SKILL.md" not in files or files["SKILL.md"][0] is None:
            raise ValueError("a resulting skill package requires SKILL.md")
        files["SKILL.md"][0].decode("utf-8")
        for name in files:
            if any(
                name.startswith(parent + "/")
                for parent, value in files.items()
                if parent != name and value[0] is not None
            ):
                raise ValueError("skill file conflicts with a parent file")
        return files

    def stage(self, config):
        """Close registration and materialize an immutable complete skill source."""
        self.closed = True
        if not self.skills:
            return
        expected = {f"{skill}/{name}": value for skill, files in self.skills.items() for name, value in files.items()}
        for name in tuple(expected):
            for parent in Path(name).parents:
                if parent != Path("."):
                    expected.setdefault(parent.as_posix(), (None, 0o755))
        digest = package_digest(expected)
        destination = self.root / "capability-skills" / digest
        materialize_tree(expected, destination, allow_runtime_caches=True)
        self.skill_root = destination
        config.skill_forge.local_dirs.append(LocalDirConfig(path=str(destination), name="curator-capability"))

    def install(self, runtime, *, context=None, disabled=()):
        """Validate the whole candidate against the native runtime before adding tools."""
        if not self.closed or self.installed:
            raise ValueError("capability installation requires a closed, uninstalled candidate")
        if self.deferred_tools:
            if context is None:
                raise ValueError("deferred tool factories require host-supplied PluginContext")
            constructed = {name: factory(context) for name, factory in self.deferred_tools.items()}
            for name, tool in constructed.items():
                if admit_tool(tool).name != name:
                    raise ValueError(f"deferred tool name differs from its contribution: {name}")
            self.tools.update(constructed)
        for name, tool in self.tools.items():
            if name in disabled:
                raise ValueError(f"capability tool is disabled by the host: {name}")
            if runtime.loop.tools.get(name) is not None:
                raise ValueError(f"capability tool would replace an existing tool: {name}")
            if admit_tool(tool).name != name:
                raise ValueError(f"registered capability tool identity changed: {name}")
        if self.skill_root is not None:
            metas = runtime.loop.context.skills.registry.list_all()
            for name in self.skills:
                path = (self.skill_root / name / "SKILL.md").resolve()
                if not any(meta.path.resolve() == path for meta in metas):
                    raise ValueError(f"capability skill is not discoverable: {name}")
                if not any(meta.path.resolve() == path and meta.name == name for meta in metas):
                    raise ValueError(f"declared skill name differs from native discovery: {name}")
        for tool in self.tools.values():
            runtime.loop.tools.register(tool)
        self.installed = True
        if self.recorder is not None:
            self.recorder.add(
                "capability.installed", candidate=self.candidate, tools=list(self.tools), skills=list(self.skills)
            )

    def skill_views(self, runtime, *, bodies=()):
        """Use native discovery, availability and body rendering, including source identity."""
        registry = runtime.loop.context.skills.registry
        return tuple(
            SkillView(
                name=meta.name,
                source=meta.source,
                path=str(meta.path),
                available=registry.check_available(meta.name, source=meta.source),
                description=meta.description,
                content=render_skill_body(meta)
                if (meta.source, meta.name) in bodies or (None, meta.name) in bodies
                else None,
                digest=hashlib.sha256(meta.path.read_bytes()).hexdigest() if meta.path.is_file() else None,
            )
            for meta in registry.list_all()
        )

    def facts(self):
        return {
            "candidate": self.candidate,
            "closed": self.closed,
            "installed": self.installed,
            "registrations": [receipt.model_dump(mode="json") for receipt in self.receipts],
            "contributions": [value.model_dump(mode="json") for value in self.contributions.values()],
            "tools": [deepcopy(admit_tool(tool).schema) for tool in self.tools.values()],
            "skills": {
                name: {"digest": package_digest(files), "files": sorted(files)} for name, files in self.skills.items()
            },
        }
