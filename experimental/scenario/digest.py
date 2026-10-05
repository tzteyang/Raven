"""Content identity of a Scenario directory, independent of information acquisition."""

import hashlib
from pathlib import Path


def digest(root: Path) -> str:
    """The SHA-256 of a directory's files, their paths included, so a researched package names its input exactly."""
    hashed = hashlib.sha256()
    for file in sorted(path for path in Path(root).rglob("*") if path.is_file()):
        hashed.update(file.relative_to(root).as_posix().encode() + b"\0")
        hashed.update(file.read_bytes() + b"\0")
    return f"sha256:{hashed.hexdigest()}"
