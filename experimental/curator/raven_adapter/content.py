"""Transactional ownership of native files produced by strategy preparation."""

import base64
import json
import os
from pathlib import Path

from ..harness.artifact import relative_path
from .materialize import _check_parent, _write, restore_content
from .preparation import PreparedHarness


def snapshot(home: Path, names) -> dict:
    """Capture exact prior files, including absence, symlinks and permissions."""
    saved = {}
    for name in names:
        path = home / relative_path(name)
        _check_parent(home, path)
        if path.is_symlink():
            saved[path] = (os.readlink(path), 0)
        elif path.is_file():
            saved[path] = (path.read_bytes(), path.stat().st_mode & 0o777)
        elif path.exists():
            raise ValueError(f"prepared content collides with a directory: {name}")
        else:
            saved[path] = (None, 0)
    return saved


def encode(value):
    content, mode = value
    return {
        "kind": "bytes" if isinstance(content, bytes) else "link" if isinstance(content, str) else "absent",
        "content": base64.b64encode(content).decode() if isinstance(content, bytes) else content,
        "mode": mode,
    }


def decode(value):
    content = base64.b64decode(value["content"], validate=True) if value["kind"] == "bytes" else value["content"]
    return content, value["mode"]


class ContentInstallation:
    """Apply a full code-produced revision and preserve edits made outside curation.

    The ledger belongs to the host, outside the authored package. Its paths
    are home-relative so copied validation and real deployment use the same
    ownership rules. Unchanged proposals relinquish externally edited files;
    a changed proposal cannot overwrite the outside editor.
    """

    def __init__(self, home: Path, root: Path, prepared: PreparedHarness, recorder):
        self.home, self.path, self.recorder = home, root / "content-state.json", recorder
        self.previous = self.path.read_bytes() if self.path.exists() else None
        held = json.loads(self.previous) if self.previous is not None else {}
        old = held.get("files", {})
        requested = prepared.files()
        self.saved = snapshot(home, old.keys() | requested.keys())
        originals, effective = {}, dict(requested)
        released = dict(held.get("released", {}))
        for name, row in old.items():
            current, _ = self.saved[home / name]
            if current != row["text"].encode():
                if name in requested and requested[name] != row["text"]:
                    raise ValueError(f"prepared content was changed by an outside editor: {name}")
                effective.pop(name, None)
                released[name] = row["text"]
                self.recorder.add("content.released", path=name, reason="outside editor")
            else:
                originals[name] = row["original"]
        for name, text in released.items():
            if name in effective:
                if effective[name] != text:
                    raise ValueError(f"content belongs to an outside editor; withdraw it from preparation: {name}")
                effective.pop(name)
        self.prepared = prepared.model_copy(
            update={
                "content": {
                    owner: {name: text for name, text in files.items() if name in effective}
                    for owner, files in prepared.content.items()
                }
            }
        )
        self.ledger = {
            "files": {
                name: {"text": text, "original": originals.get(name, encode(self.saved[home / name]))}
                for name, text in effective.items()
            },
            "released": {name: text for name, text in released.items() if name in requested},
        }
        self.retired = {home / name: decode(original) for name, original in originals.items() if name not in effective}

    def apply(self):
        try:
            restore_content(self.home, self.retired)
            for name, text in self.prepared.files().items():
                previous, mode = self.saved[self.home / name]
                _write(self.home / name, text.encode(), mode if isinstance(previous, bytes) else 0o600)
            _write(self.path, json.dumps(self.ledger, ensure_ascii=False).encode())
        except BaseException:
            self.rollback()
            raise

    def rollback(self):
        restore_content(self.home, self.saved)
        if self.previous is None:
            self.path.unlink(missing_ok=True)
        else:
            _write(self.path, self.previous)


def check_owners(baseline, prepared, children):
    """Check concrete prepared paths before activating a root and its children."""
    root = baseline.config.workspace_path
    for name, (child_baseline, _) in children.items():
        home = child_baseline.config.workspace_path.resolve()
        if any((root / path).resolve().is_relative_to(home) for path in prepared.files()):
            raise ValueError(f"root content overlaps the managed child {name}")
    owners = {}
    for name, (child_baseline, child_prepared) in children.items():
        for path in child_prepared.files():
            resolved = (child_baseline.config.workspace_path / path).resolve()
            if resolved in owners:
                raise ValueError(f"children {owners[resolved]} and {name} both own {resolved}")
            owners[resolved] = name
