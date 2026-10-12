"""Content identity of a Scenario directory, independent of information acquisition."""

import hashlib
from pathlib import Path


def digest(root: Path, *, include_generated: bool = False) -> str:
    """Hash source files and paths, excluding generated/local state unless checking a legacy record."""
    hashed = hashlib.sha256()
    for file in sorted(path for path in Path(root).rglob("*") if path.is_file()):
        relative = file.relative_to(root)
        if not include_generated and any(part.startswith(".") or part == "__pycache__" for part in relative.parts):
            continue
        hashed.update(relative.as_posix().encode() + b"\0")
        hashed.update(file.read_bytes() + b"\0")
    return f"sha256:{hashed.hexdigest()}"
