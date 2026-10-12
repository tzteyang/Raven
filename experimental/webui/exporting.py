"""Portable employee packages built from a checked, idle Studio deployment."""

import base64
import hashlib
import io
import json
import re
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path

from raven.config.schema import AgentDefaults

from ..curator.harness import Artifact, Task
from ..curator.harness.artifact import relative_path
from ..curator.raven_adapter.deployment import _STATE_FILES, _digest
from ..curator.raven_adapter.inspection import fingerprint

FORMAT = 1
NAME = re.compile(r"expert-live-[0-9]{14}-[0-9a-f]{6}")
OPTIONS = frozenset(
    {
        "model",
        "reasoningEffort",
        "temperature",
        "maxToolIterations",
        "contextWindowTokens",
        "llmCallTimeout",
        "streamIdleTimeout",
        "llmFirstByteTimeout",
        "enablePersonalization",
    }
)
RUN = '''#!/usr/bin/env python
"""Serve a Studio employee using the installed Raven source checkout."""

import sys
from pathlib import Path

try:
    import raven
    source = Path(raven.__file__).resolve().parent.parent
    if not (source / "experimental/webui/employee_runtime.py").is_file():
        raise ImportError("the installed Raven has no Studio employee runtime")
    sys.path.insert(0, str(source))
    from experimental.webui.employee_runtime import main
except ImportError as exc:
    sys.exit(f"This employee needs the Raven source version with Studio export support: {exc}")

if __name__ == "__main__":
    main(Path(__file__).resolve().parent)
'''
README = """# Studio employee

This package contains one saved employee: its task, authored Harness, prepared
content, memory and planning checkpoints, and the materials it received.
Evaluation records, provider credentials and the training machine's configuration
are not included.

## Install and run

Use the Raven source version that provides Studio employee export. Install that
checkout with `uv sync --frozen`; a release wheel without `experimental/` cannot
run this package. The launcher finds the checkout through the installed `raven`
module and reports a compatibility error if that runtime is absent.

Extract this whole employee folder into the host Raven's `agents/` directory and
restart the host. Raven discovers `subagent.json` and launches `run.py` over ACP.
For a direct ACP client, use the source environment's interpreter with `run.py`.
Stdout carries ACP frames; diagnostics go to stderr.

Configure the host Raven for the model recorded in `package.json` and any web or
other tools the employee needs. The launcher reads the host configuration under
`RAVEN_HOME` at runtime; it does not create another credential file. The model and
the few exported generation settings override the host defaults, while providers,
tool credentials and host restrictions come from that host.

## Saved work

Each package digest gets its own state root and ACP home outside this folder.
The first launch restores the saved content, strategy state and uploads; later
launches keep the employee's progress. Re-exporting a different snapshot creates
a separate state root instead of replacing that progress. For an isolated launch,
set `RAVEN_STUDIO_STATE_ROOT` and `RAVEN_STUDIO_ACP_HOME` to dedicated directories.
Only one process can serve the same state root at a time.

Checksums detect changed package files. Keep the original package for recovery;
installing another revision does not migrate runtime state from an older one.
"""


@dataclass(frozen=True)
class Export:
    filename: str
    data: bytes


def encoded(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def decoded(value) -> bytes | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("saved file content must be base64 text or null")
    return base64.b64decode(value, validate=True)


def checked_deployment(value: dict) -> dict:
    if not isinstance(value, dict) or value.get("sha256") != _digest(
        {key: item for key, item in value.items() if key != "sha256"}
    ):
        raise ValueError("the saved deployment does not match its checksum")
    if value.get("children"):
        raise ValueError("a delegating employee cannot be exported as one agent")
    if not isinstance(value.get("content"), dict) or not isinstance(value.get("state"), dict):
        raise ValueError("saved content and strategy state must be file mappings")
    artifact = Artifact.model_validate(value["artifact"])
    Task.model_validate(value["task"])
    if value["revision"] != fingerprint(artifact.model_dump(mode="json")):
        raise ValueError("the saved deployment revision does not match its artifact")
    for name, row in value["content"].items():
        relative_path(name)
        if not isinstance(row, list) or len(row) != 2 or type(row[1]) is not int or not 0 <= row[1] <= 0o777:
            raise ValueError("invalid saved content permissions")
        decoded(row[0])
    for name, content in value["state"].items():
        relative_path(name)
        if name not in _STATE_FILES:
            raise ValueError("unknown saved strategy state file")
        decoded(content)
    return value


def safe_file(root: Path, name: str) -> Path:
    path = root / relative_path(name)
    if any(part.is_symlink() for part in (path, *path.parents) if part != root and part.is_relative_to(root)):
        raise ValueError("employee package files cannot be symbolic links")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("employee package path leaves its folder")
    return path


def read_stable(path: Path) -> bytes:
    before = path.stat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("employee package inputs must be regular files")
    content = path.read_bytes()
    after = path.stat()
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError("the employee files changed while exporting; try again when idle")
    return content


def available(path: Path) -> bool:
    try:
        if path.is_symlink():
            return False
        checked_deployment(json.loads(read_stable(path)))
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False


def build(directory: Path, config: Path, *, revision: str | None = None) -> Export:
    name = f"expert-{directory.name}"
    if not NAME.fullmatch(name):
        raise ValueError("invalid employee package name")
    saved_bytes = read_stable(safe_file(directory, "deployment.json"))
    saved = checked_deployment(json.loads(saved_bytes))
    if revision is not None and saved["revision"] != revision:
        raise ValueError("the latest employee revision has not been saved yet")
    trained = json.loads(config.read_text())
    defaults = AgentDefaults.model_validate(trained.get("agents", {}).get("defaults", {})).model_dump(
        mode="json",
        by_alias=True,
        exclude_unset=True,
    )
    options = {key: value for key, value in defaults.items() if key in OPTIONS}
    settings_path = directory / "settings.json"
    if settings_path.is_file():
        settings = json.loads(settings_path.read_text())
        for field, group in (("model", "models"), ("reasoningEffort", "efforts")):
            if value := settings.get(group, {}).get("partner"):
                options[field] = value
    if not isinstance(options.get("model"), str) or not options["model"].strip():
        raise ValueError("the saved employee has no model setting")
    kept = {key: saved[key] for key in ("artifact", "content", "state", "task", "revision")}
    kept["sha256"] = _digest(kept)
    manifest = {
        "name": name,
        "kind": "acp",
        "description": saved["task"]["text"],
        "enabled": True,
        "command": "{PYTHON} {SUBAGENT_DIR}/run.py",
        "cwd": "{SUBAGENT_DIR}",
        "readyTimeoutMs": 180000,
        "timeout": None,
        "maxOutputChars": 60000,
    }
    files = {
        "subagent.json": encoded(manifest),
        "deployment.json": encoded(kept),
        "run.py": RUN.encode(),
        "README.md": README.encode(),
    }
    uploads = safe_file(directory, "employee/home/uploads")
    material_paths = sorted(uploads.rglob("*")) if uploads.exists() else []
    for path in material_paths:
        relative = path.relative_to(uploads).as_posix()
        found = safe_file(uploads, relative)
        if found.is_file():
            files[f"uploads/{relative}"] = read_stable(found)
        elif not found.is_dir():
            raise ValueError("uploads contain a nonregular file")
    if material_paths != (sorted(uploads.rglob("*")) if uploads.exists() else []):
        raise ValueError("the employee materials changed while exporting; try again")
    if saved_bytes != (directory / "deployment.json").read_bytes():
        raise ValueError("the employee deployment changed while exporting; try again")
    package = {
        "format": FORMAT,
        "name": name,
        "options": options,
        "source": {"session": directory.name, "deployment_sha256": saved["sha256"]},
        "files": {path: hashlib.sha256(data).hexdigest() for path, data in files.items()},
    }
    package["sha256"] = _digest(package)
    files["package.json"] = encoded(package)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, data in files.items():
            entry = zipfile.ZipInfo(f"{name}/{path}")
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = (stat.S_IFREG | (0o755 if path == "run.py" else 0o600)) << 16
            archive.writestr(entry, data)
    return Export(f"{name}.zip", output.getvalue())


def load_package(folder: Path) -> tuple[dict, dict[str, bytes]]:
    package = json.loads(safe_file(folder, "package.json").read_bytes())
    if not isinstance(package, dict) or package.get("format") != FORMAT or not NAME.fullmatch(package.get("name", "")):
        raise ValueError("unsupported Studio employee package")
    if package.get("sha256") != _digest({key: value for key, value in package.items() if key != "sha256"}):
        raise ValueError("the employee package does not match its checksum")
    if not isinstance(package.get("options"), dict) or set(package["options"]) - OPTIONS:
        raise ValueError("unknown employee model options")
    if not isinstance(package.get("files"), dict):
        raise ValueError("the employee package needs its file checksums")
    files = {}
    for name, digest in package["files"].items():
        files[name] = safe_file(folder, name).read_bytes()
        if hashlib.sha256(files[name]).hexdigest() != digest:
            raise ValueError(f"employee package checksum mismatch: {name}")
    if not {"subagent.json", "deployment.json", "run.py", "README.md"} <= files.keys():
        raise ValueError("the employee package is incomplete")
    checked_deployment(json.loads(files["deployment.json"]))
    return package, files
