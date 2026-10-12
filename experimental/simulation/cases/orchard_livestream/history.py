"""Retain native operations and live-file versions without turning partial observations into compliance."""

import hashlib
import json
from collections import defaultdict, deque
from pathlib import Path

from experimental.harness.raven_adapter.action.runtime import REFUSED


def retained_deliveries(exchanges):
    """Keep each delivery occurrence; a reused mutable path cannot prove earlier bytes."""
    last = {
        str(path): (turn, ordinal)
        for turn, exchange in enumerate(exchanges, 1)
        for ordinal, path in enumerate(exchange.execution.deliverables, 1)
    }
    found = []
    for turn, exchange in enumerate(exchanges, 1):
        versions, unavailable = [], []
        for ordinal, path in enumerate(exchange.execution.deliverables, 1):
            entry = {"name": Path(path).name, "ordinal": ordinal}
            if last[str(path)] != (turn, ordinal):
                unavailable.append({**entry, "reason": "A reused path has no separate retained earlier snapshot."})
                continue
            try:
                raw = Path(path).read_bytes()
                versions.append({**entry, "sha256": hashlib.sha256(raw).hexdigest(), "content": raw.decode("utf-8")})
            except (OSError, UnicodeError) as exc:
                unavailable.append({**entry, "reason": type(exc).__name__})
        if versions or unavailable:
            found.append({"turn": turn, "versions": versions, "unavailable": unavailable})
    return found


def contained(path, root):
    """Resolve a path only inside a known replica, including symlink containment."""
    if not root or not path:
        return None
    root = Path(root)
    try:
        if root.is_symlink() or not root.is_dir():
            return None
        target = Path(path)
        target = target if target.is_absolute() else root / target
        return target.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, RuntimeError, ValueError):
        return None


def file_state(path, root):
    relative = contained(path, root)
    if relative is None:
        return {"status": "unavailable", "reason": "Replica root or contained path is unavailable."}
    try:
        raw = (Path(root) / relative).read_bytes()
        return {
            "status": "read",
            "path": relative,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "content": raw.decode("utf-8"),
        }
    except FileNotFoundError:
        return {"status": "absent", "path": relative}
    except (OSError, UnicodeError) as exc:
        return {"status": "unavailable", "path": relative, "reason": type(exc).__name__}


def events(exchanges):
    """Flatten child records using their own host clocks and execution identities, never collection time."""
    rows, gaps = [], []

    def visit(records, turn, actor, scope):
        for position, row in enumerate(records):
            if row.get("kind") == "child.execution":
                identity = [row.get("harness"), row.get("launch"), row.get("pid"), row.get("log")]
                child_scope = json.dumps(identity)
                if not all(identity) or any((row.get("omitted") or {}).values()):
                    gaps.append(
                        {
                            "turn": turn,
                            "scope": child_scope,
                            "reason": "Child identity or complete log coverage is unavailable.",
                        }
                    )
                visit(row.get("records") or (), turn, str(row.get("harness") or "child"), child_scope)
            elif row.get("kind") == "runner.event":
                rows.append({"row": row, "turn": turn, "actor": actor, "scope": scope, "position": position})

    for turn, exchange in enumerate(exchanges, 1):
        visit(exchange.execution.records, turn, "assistant", "root")
    complete_clocks = all(
        type(item["row"].get("monotonic_ns")) is int and item["row"]["monotonic_ns"] > 0 for item in rows
    )
    if complete_clocks:
        rows.sort(key=lambda item: item["row"]["monotonic_ns"])
    elif rows:
        gaps.append(
            {
                "reason": "Some host event clocks are missing; collection order cannot establish cross-process chronology."
            }
        )
    return rows, gaps


def operations(exchanges):
    rows, gaps = events(exchanges)
    pending, result = defaultdict(deque), []
    for entry in rows:
        row, event = entry["row"], entry["row"].get("event") or {}
        if row.get("event_type", "ToolEvent") != "ToolEvent":
            continue
        call = event.get("tool_call_id")
        key = entry["scope"], row.get("conversation"), call
        if event.get("phase") == "start" and call:
            pending[key].append(entry)
        elif event.get("phase") == "complete" and pending[key]:
            start = pending[key].popleft()
            begun = start["row"]["event"]
            output = str(event.get("result_preview") or "")
            ok = event.get("ok") if type(event.get("ok")) is bool else None
            if output.startswith(REFUSED):
                ok = False
            result.append(
                {
                    "actor": entry["actor"],
                    "scope": entry["scope"],
                    "call_id": call,
                    "collected_turn": entry["turn"],
                    "started_turn": start["turn"],
                    "tool": begun.get("name"),
                    "arguments": begun.get("arguments") or {},
                    "ok": ok,
                    "result": output,
                    "file_change": event.get("file_change"),
                    "started_at": start["row"].get("observed_at"),
                    "completed_at": row.get("observed_at"),
                    "started_monotonic_ns": start["row"].get("monotonic_ns"),
                    "completed_monotonic_ns": row.get("monotonic_ns"),
                }
            )
    for queue in pending.values():
        for entry in queue:
            event = entry["row"]["event"]
            result.append(
                {
                    "actor": entry["actor"],
                    "scope": entry["scope"],
                    "call_id": event.get("tool_call_id"),
                    "started_turn": entry["turn"],
                    "tool": event.get("name"),
                    "arguments": event.get("arguments") or {},
                    "ok": None,
                    "result": "",
                    "reason": "No paired completion was retained.",
                }
            )
    return result, gaps


def live_files(exchanges, vocabulary, room, workdir):
    """Keep every full write or partial edit, including failed/unknown attempts, and the final file state."""
    calls, gaps = operations(exchanges)
    expected = {
        kind: f"{vocabulary.one('live_folder')}/{room}/{vocabulary.one(kind)}.md" for kind in ("board", "record")
    }
    versions = []
    for call in calls:
        args, change = call["arguments"], call.get("file_change") or {}
        if call["tool"] not in ("write_file", "edit_file") and not change:
            continue
        path = change.get("path") or args.get("path") or args.get("file_path")
        relative = contained(path, workdir)
        kind = next((kind for kind, required in expected.items() if relative == required), None)
        if kind is None:
            if path and any(Path(str(path)).name == Path(required).name for required in expected.values()):
                gaps.append(
                    {
                        "path": str(path),
                        "reason": "A live-file operation has no verified placement in this session's replica.",
                    }
                )
            continue
        content, fragment, bytes_known = None, None, False
        if call["ok"] is True:
            if isinstance(change.get("after"), str):
                content = change["after"]
                bytes_known = (call["tool"] == "write_file" and args.get("mode") != "append") or (
                    call["tool"] == "edit_file" and "\n" not in content
                )
            elif call["tool"] == "write_file" and isinstance(args.get("content"), str):
                if args.get("mode") == "append":
                    fragment = args["content"]
                else:
                    content = args["content"]
                    bytes_known = True
            elif call["tool"] == "edit_file":
                fragment = args.get("new_text")
        versions.append(
            {
                **call,
                "kind": kind,
                "path": relative,
                "content": content,
                "fragment": fragment,
                "bytes_known": bytes_known,
                "content_representation": "exact_utf8_bytes" if bytes_known else "native_text_or_fragment",
                "sha256": hashlib.sha256(content.encode()).hexdigest() if bytes_known else None,
            }
        )
        if call["ok"] is None or (call["ok"] is True and content is None):
            gaps.append(
                {
                    "path": relative,
                    "call_id": call["call_id"],
                    "reason": "This operation does not retain a verified complete file version.",
                }
            )
    return {
        "operations": calls,
        "versions": versions,
        "coverage_gaps": gaps,
        "final_files": {kind: file_state(path, workdir) for kind, path in expected.items()},
    }
