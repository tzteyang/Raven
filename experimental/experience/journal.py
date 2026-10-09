"""Persist shared governance transitions atomically, independently of role-owned evidence storage."""

import fcntl
import json
import os
import tempfile
from pathlib import Path

from .governance import Governance


class GovernanceFile:
    def __init__(self, path: Path):
        self.path = Path(path)

    def read(self) -> Governance:
        if not self.path.exists():
            return Governance()
        value = json.loads(self.path.read_text())
        if value.get("schema") != 1:
            raise ValueError("unsupported experience governance journal")
        return Governance(value["governance"])

    def update(self, operation):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.with_suffix(".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            current = self.read()
            changed = current.clone()
            result = operation(changed)
            value = Governance(changed.record()).record()
            if value == current.record() and self.path.exists():
                return result
            data = json.dumps({"schema": 1, "governance": value}, ensure_ascii=False, allow_nan=False).encode()
            fd, temporary = tempfile.mkstemp(prefix=self.path.name + ".", dir=self.path.parent)
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, self.path)
            finally:
                Path(temporary).unlink(missing_ok=True)
            return result
