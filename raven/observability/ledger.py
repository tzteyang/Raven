"""Durable execution snapshots, merged by identity rather than added on delivery."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path

FILENAME = "execution.sqlite3"
IDENTITY = ("id", "run_id", "parent_id", "kind", "name", "started_at", "pid")


def _same_operation(previous, row):
    if any(previous[key] != row[key] for key in IDENTITY):
        raise LedgerError(f"Execution identity changed: {row['id']}")


class LedgerError(RuntimeError):
    """Execution accounting could not be persisted or reconciled."""


class Ledger:
    """One locally writable shard; no live connection crosses a process or thread."""

    def __init__(self, path: Path | str):
        self.path = Path(path).resolve()

    def put(self, row: dict) -> None:
        try:
            payload = json.dumps(row, sort_keys=True, separators=(",", ":"), allow_nan=False)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
            os.close(descriptor)
            self.path.chmod(0o600)
            with closing(sqlite3.connect(self.path, timeout=10)) as connection, connection:
                connection.execute("PRAGMA synchronous=FULL")
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS snapshots "
                    "(id TEXT PRIMARY KEY, version INTEGER NOT NULL, payload TEXT NOT NULL)"
                )
                connection.execute("BEGIN IMMEDIATE")
                existing = connection.execute(
                    "SELECT version, payload FROM snapshots WHERE id = ?", (row["id"],)
                ).fetchone()
                if existing:
                    _same_operation(json.loads(existing[1]), row)
                if existing and existing[0] == row["version"] and existing[1] != payload:
                    raise LedgerError(f"Conflicting execution snapshot: {row['id']} version {row['version']}")
                connection.execute(
                    "INSERT INTO snapshots VALUES (?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
                    "version = excluded.version, payload = excluded.payload WHERE excluded.version > snapshots.version",
                    (row["id"], row["version"], payload),
                )
        except (OSError, sqlite3.Error, TypeError, ValueError, KeyError) as exc:
            raise LedgerError(f"Cannot persist execution accounting in {self.path}: {exc}") from exc

    def read(self) -> list[dict]:
        if not self.path.is_file():
            return []
        try:
            with closing(sqlite3.connect(f"{self.path.as_uri()}?mode=ro", uri=True, timeout=10)) as connection:
                return [json.loads(row[0]) for row in connection.execute("SELECT payload FROM snapshots")]
        except (OSError, ValueError, sqlite3.Error) as exc:
            raise LedgerError(f"Cannot read execution accounting in {self.path}: {exc}") from exc


def merge(rows) -> list[dict]:
    """Deduplicate copied shards and delayed snapshots without hiding conflicts."""
    found = {}
    for row in rows:
        previous = found.get(row["id"])
        if previous:
            _same_operation(previous, row)
        if previous and previous["version"] == row["version"] and previous != row:
            raise LedgerError(f"Conflicting execution snapshot: {row['id']}")
        if previous is None or previous["version"] < row["version"]:
            found[row["id"]] = row
    return sorted(found.values(), key=lambda row: (row["started_at"], row["id"]))


def read_tree(root: Path) -> list[dict]:
    """Read local worker shards without granting workers access to their parent's ledger."""
    root = Path(root).resolve()

    def unreadable(exc):
        raise LedgerError(f"Cannot enumerate execution accounting under {root}: {exc}") from exc

    rows = []
    if not root.exists():
        return rows
    for folder, directories, files in os.walk(root, onerror=unreadable):
        directories[:] = sorted(name for name in directories if name not in {".git", ".venv", "node_modules"})
        path = Path(folder) / FILENAME
        if FILENAME in files and path.resolve().is_relative_to(root):
            rows.extend(Ledger(path).read())
    return merge(rows)
