"""Persist every strategy's managed state in one atomic Harness checkpoint."""

import json
from copy import deepcopy
from pathlib import Path

from experimental.harness.raven_adapter.materialize import _write

CHECKPOINT = "strategies.json"
LEGACY_CHECKPOINTS = tuple(f"{name}.json" for name in ("memory", "planning", "capability", "action"))
CHECKPOINT_FILES = (CHECKPOINT, *LEGACY_CHECKPOINTS)


class Checkpoints:
    def __init__(self, directory: Path, task_id: str):
        self.path = directory / CHECKPOINT
        self.task_id = task_id
        if self.path.exists():
            saved = json.loads(self.path.read_text())
            if saved["task_id"] != task_id:
                raise ValueError("strategy checkpoint belongs to another task")
            self.owners = saved["owners"]
        else:
            self.owners = {}
            for name in LEGACY_CHECKPOINTS:
                path = directory / name
                if path.exists():
                    saved = json.loads(path.read_text())
                    if saved.pop("task_id") != task_id:
                        raise ValueError(f"{path.stem} checkpoint belongs to another task")
                    self.owners[path.stem] = saved

    def read(self, name):
        return deepcopy(self.owners.get(name))

    def save(self, records):
        owners = deepcopy({**self.owners, **records})
        content = json.dumps({"task_id": self.task_id, "owners": owners}, sort_keys=True, ensure_ascii=False).encode()
        if not self.path.exists() or self.path.read_bytes() != content:
            _write(self.path, content)
        self.owners = owners
