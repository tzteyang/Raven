"""Retain authenticated user disclosures by conversation independently of the model's context window."""

import json
from pathlib import Path

from raven.spine.scheduler import conversation_id
from raven.spine.turn import Origin

from ..curator.raven_adapter.materialize import _write


class Disclosures:
    """Only native user ingress adds evidence; tools, delegated results and generated messages cannot grant access."""

    def __init__(self, path: Path):
        self.path = path
        self.streams = json.loads(path.read_text()) if path.exists() else {}
        if not isinstance(self.streams, dict) or any(
            not isinstance(key, str) or not isinstance(rows, list) or any(not isinstance(row, str) for row in rows)
            for key, rows in self.streams.items()
        ):
            raise ValueError("invalid conversation disclosure ledger")

    def receive(self, request) -> tuple[str, ...]:
        key = conversation_id(request)
        if request.origin == Origin.USER and request.delegated is None:
            self.streams.setdefault(key, []).append(request.text)
            _write(self.path, json.dumps(self.streams, ensure_ascii=False).encode())
        return tuple(self.streams.get(key, ()))
