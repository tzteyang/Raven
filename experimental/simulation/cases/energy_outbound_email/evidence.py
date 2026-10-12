"""Retain operation outcomes, actor identities and file versions for the outbound case."""

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from experimental.harness.raven_adapter.action.runtime import REFUSED


@dataclass(frozen=True)
class Event:
    """A paired tool lifecycle, retaining uncertainty and the completion's native evidence."""

    order: int
    turn: int
    actor: str
    name: str
    arguments: dict
    result: str
    ok: bool | None
    call_id: str = ""
    start_turn: int = 0
    identity: dict = field(default_factory=dict)
    completion: dict = field(default_factory=dict)
    execution_id: str | None = None
    start_order: int = 0
    completion_order: int | None = None
    lifecycle_ambiguous: bool = False


@dataclass(frozen=True)
class Write:
    """One attempted file effect and the exact text retained at that operation, if observable."""

    order: int
    turn: int
    actor: str
    tool: str
    path: str
    arguments: dict
    ok: bool | None
    content: str | None = None
    provenance: str = "unavailable"
    call_id: str = ""
    identity: dict = field(default_factory=dict)
    execution_id: str | None = None
    monotonic_ns: int | None = None
    observed_at: float | None = None
    native_effects: tuple[dict, ...] = ()
    scope_gap: bool = False
    resource_identity: str | None = None
    resource_limits: tuple[str, ...] = ()
    invalidates_all: bool = False
    bytes_known: bool = True
    no_effect: bool = False

    @property
    def sha256(self):
        return (
            hashlib.sha256(self.content.encode("utf-8")).hexdigest()
            if self.content is not None and self.bytes_known
            else None
        )


def events(exchanges) -> list[Event]:
    """Keep start positions and ambiguous reused ids rather than dropping potential file mutations."""
    pending, entries, position = {}, [], 0

    def observed(rows, identity):
        for row in rows:
            if row.get("kind") == "child.execution":
                child = {key: row.get(key) for key in ("harness", "launch", "pid", "revision", "log")}
                yield from observed(row.get("records") or (), child)
            elif row.get("kind") == "runner.event" and row.get("event_type", "ToolEvent") == "ToolEvent":
                yield (
                    {**identity, "conversation": row.get("conversation")},
                    {
                        **(row.get("event") or {}),
                        "host_monotonic_ns": row.get("monotonic_ns"),
                        "host_observed_at": row.get("observed_at"),
                        "actor_execution_id": row.get("turn_id"),
                    },
                )

    for turn, exchange in enumerate(exchanges, 1):
        for identity, event in observed(exchange.execution.records, {"harness": "employee"}):
            position += 1
            key = (json.dumps(identity, sort_keys=True), str(event.get("tool_call_id") or ""))
            if event.get("phase") == "start" and event.get("name"):
                waiting = pending.setdefault(key, [])
                ambiguous = bool(waiting) or not key[1]
                for prior in waiting:
                    prior["ambiguous"] = True
                entry = {
                    "begun": event,
                    "start_turn": turn,
                    "start_order": position,
                    "identity": identity,
                    "ambiguous": ambiguous,
                    "turn": turn,
                    "completion": {},
                    "completion_order": None,
                    "execution_id": None,
                }
                entries.append(entry)
                waiting.append(entry)
            elif event.get("phase") == "complete" and pending.get(key):
                entry = pending[key].pop(0)
                entry.update(
                    {
                        "completion": event,
                        "completion_order": position,
                        "turn": turn,
                        "execution_id": getattr(exchange.execution, "turn_id", None),
                    }
                )
            elif event.get("phase") == "complete":
                entries.append(
                    {
                        "begun": {"name": "unpaired_completion", "tool_call_id": event.get("tool_call_id")},
                        "start_turn": 0,
                        "start_order": 0,
                        "identity": identity,
                        "ambiguous": True,
                        "turn": turn,
                        "completion": {**event, "lifecycle_start_unobserved": True},
                        "completion_order": position,
                        "execution_id": getattr(exchange.execution, "turn_id", None),
                    }
                )
    entries.sort(key=lambda entry: entry["completion_order"] or entry["start_order"])
    found = []
    for order, entry in enumerate(entries, 1):
        begun, complete = entry["begun"], entry["completion"]
        result = str(complete.get("result_preview") or "")
        value = complete.get("ok")
        ok = (
            None
            if entry["ambiguous"]
            else False
            if result.startswith(REFUSED)
            else value
            if isinstance(value, bool)
            else None
        )
        found.append(
            Event(
                order,
                entry["turn"],
                entry["identity"]["harness"],
                begun["name"],
                begun.get("arguments") or {},
                result,
                ok,
                str(begun.get("tool_call_id") or ""),
                entry["start_turn"],
                entry["identity"],
                complete,
                entry["execution_id"],
                entry["start_order"],
                entry["completion_order"],
                entry["ambiguous"],
            )
        )
    return found


def resource(path, workdir=None):
    """Normalize anchored spellings; present aliases only widen historical identity uncertainty."""
    raw = Path(str(path))
    anchored = Path(workdir) / raw if workdir and not raw.is_absolute() else raw
    display = os.path.normpath(str(anchored))
    limits = []
    if not anchored.is_absolute() or str(raw).startswith("~"):
        limits.append("The actual filesystem workspace/home anchor is not observed.")
    else:
        current = Path(anchored.anchor)
        for part in anchored.parts[1:]:
            current /= part
            try:
                if current.is_symlink():
                    limits.append("A present symlink cannot establish its historical target.")
                    break
                info = current.stat()
                if current.is_file() and info.st_nlink > 1:
                    limits.append("A present hardlink cannot establish historical resource equivalence.")
                    break
            except FileNotFoundError:
                continue
            except (OSError, ValueError):
                limits.append("Filesystem identity is unavailable; distinct resources are not established.")
                break
    return display, None if limits else display, tuple(limits)


def writes(calls: list[Event], workdir=None) -> list[Write]:
    """Keep native state separate from tool success; uncertain mutators invalidate future replay."""
    found, previous = [], {}

    def normalized(path):
        return resource(path, workdir)[0]

    def native_effects(call):
        change = call.completion.get("file_change")
        effects = [change] if isinstance(change, dict) and change.get("path") else []
        effects += [
            row for row in call.completion.get("file_written") or [] if isinstance(row, dict) and row.get("path")
        ]
        effects += [
            {**row, "removed": True}
            for row in call.completion.get("file_removed") or []
            if isinstance(row, dict) and row.get("path")
        ]
        return effects

    resources = {}
    for call in calls:
        paths = [effect["path"] for effect in native_effects(call)]
        if call.name in ("write_file", "edit_file") and call.arguments.get("path"):
            paths.append(call.arguments["path"])
        resources[id(call)] = [resource(path, workdir) for path in paths]

    def unknown_targets(call):
        return (
            call.name in ("exec", "ops_submit", "unpaired_completion")
            or any(identity is None for _, identity, _ in resources[id(call)])
            or (call.name in ("write_file", "edit_file") and (call.ok is not True or not resources[id(call)]))
        )

    def effects_pending(call):
        return (
            call.completion_order is None
            or call.name == "ops_submit"
            or (call.name == "exec" and call.arguments.get("run_in_background") is True)
        )

    def targets(call):
        return {identity for _, identity, _ in resources[id(call)] if identity is not None}

    def uncertain_base(call, path, prior):
        for other in calls:
            if other is call or (not unknown_targets(other) and path not in targets(other)):
                continue
            if (
                other.identity != call.identity
                and other.start_turn <= call.turn
                and (effects_pending(other) or other.turn >= prior[2].turn)
            ):
                return True
            if (
                other.identity == call.identity
                and other.start_order < (call.completion_order or call.start_order)
                and (
                    effects_pending(other)
                    or (other.completion_order is not None and other.completion_order > call.start_order)
                )
            ):
                return True
        return False

    for call in calls:
        clear_all = unknown_targets(call)
        requested = call.arguments.get("content")
        requested_bytes = requested.replace("\n", os.linesep).encode("utf-8") if isinstance(requested, str) else None
        requested_path = normalized(call.arguments["path"]) if call.arguments.get("path") else ""
        no_effect = (
            call.name == "write_file"
            and call.arguments.get("mode") != "append"
            and call.ok is True
            and not call.completion.get("truncated")
            and requested_bytes is not None
            and call.result
            == f"File unchanged: {requested_path} already holds exactly these {len(requested_bytes)} bytes, so nothing was written."
        )
        change = call.completion.get("file_change")
        observed_new = (
            call.name == "write_file"
            and call.arguments.get("mode") != "append"
            and call.ok is True
            and isinstance(change, dict)
            and "before" in change
            and change["before"] is None
            and isinstance(change.get("after"), str)
        )
        clear_others = (
            call.name in ("write_file", "edit_file")
            and not observed_new
            and not no_effect
            and bool(set(previous) - targets(call))
        )
        own_prior = (
            {path: previous[path] for path in targets(call) if path in previous}
            if clear_others and not clear_all
            else {}
        )
        gap_record = call.name in ("exec", "ops_submit", "unpaired_completion") or any(
            identity is None for _, identity, _ in resources[id(call)]
        )
        if clear_all or clear_others:
            previous.clear()
        if gap_record:
            found.append(
                Write(
                    call.order,
                    call.turn,
                    call.actor,
                    call.name,
                    "",
                    call.arguments,
                    call.ok,
                    provenance="Potential file effects have no exhaustive observed target coverage.",
                    call_id=call.call_id,
                    identity=call.identity,
                    execution_id=call.execution_id,
                    monotonic_ns=call.completion.get("host_monotonic_ns"),
                    observed_at=call.completion.get("host_observed_at"),
                    scope_gap=True,
                )
            )
        effects = native_effects(call)
        if call.name in ("write_file", "edit_file") and call.arguments.get("path"):
            requested_path = normalized(call.arguments["path"])
            if not effects or (
                call.lifecycle_ambiguous and requested_path not in {normalized(effect["path"]) for effect in effects}
            ):
                effects.append({"path": call.arguments["path"]})
        by_path = {}
        for effect in effects:
            by_path.setdefault(normalized(effect["path"]), []).append(effect)
        for path, native in by_path.items():
            identities = [resource(effect["path"], workdir) for effect in native]
            identity = path if all(item[1] == path for item in identities) else None
            limits = tuple(dict.fromkeys(limit for item in identities for limit in item[2]))
            prior = previous.pop(path, None) or own_prior.pop(path, None)
            if identity is None or (clear_all and not gap_record):
                previous.clear()
            content, source, bytes_known = None, "unavailable", False
            full = [
                effect["after"]
                for effect in native
                if isinstance(effect.get("after"), str)
                and effect.get("after_complete") is not False
                and not effect.get("after_truncated")
            ]
            removed = any(effect.get("removed") for effect in native)
            partial = any(
                isinstance(effect.get("after"), str)
                and (effect.get("after_complete") is False or effect.get("after_truncated"))
                for effect in native
            )
            if full and len(set(full)) == 1 and not removed:
                content, source = full[0], "completion.file_change after-state; operation outcome is separate"
                bytes_known = "\n" not in content or (call.name == "write_file" and os.linesep == "\n")
                if (
                    call.name == "edit_file"
                    and call.ok is True
                    and prior is not None
                    and prior[1] == call.identity
                    and not uncertain_base(call, path, prior)
                    and any(effect.get("before") == prior[0].replace("\r\n", "\n") for effect in native)
                ):
                    content = content.replace("\n", "\r\n") if "\r\n" in prior[0] else content
                    bytes_known = True
                    source += "; newline bytes established by prior state and native edit contract"
            elif full or partial or removed:
                source = (
                    "completion.file_removed" if removed and len(native) == 1 else "conflicting or partial native state"
                )
            elif (
                identity is not None
                and call.ok is True
                and call.name == "write_file"
                and isinstance(call.arguments.get("content"), str)
            ):
                if call.arguments.get("mode") != "append":
                    content = call.arguments["content"]
                    source = (
                        "native unchanged-state contract; no write performed"
                        if no_effect
                        else "successful overwrite contract"
                    )
                elif prior is not None and prior[1] == call.identity and not uncertain_base(call, path, prior):
                    content, source = prior[0] + call.arguments["content"], "successful append to observed version"
                bytes_known = content is not None and os.linesep == "\n"
            if content is not None and identity is not None and bytes_known:
                previous[path] = (content, call.identity, call)
            found.append(
                Write(
                    call.order,
                    call.turn,
                    call.actor,
                    call.name,
                    path,
                    call.arguments,
                    call.ok,
                    content,
                    source,
                    call.call_id,
                    call.identity,
                    call.execution_id,
                    call.completion.get("host_monotonic_ns"),
                    call.completion.get("host_observed_at"),
                    tuple(native),
                    resource_identity=identity,
                    resource_limits=limits,
                    invalidates_all=identity is None or ((clear_all or clear_others) and not gap_record),
                    bytes_known=bytes_known,
                    no_effect=no_effect,
                )
            )
    return found


def contents(done: list[Write]) -> dict[str, str]:
    """Last full observed text; uncertain mutators never silently preserve an older version."""
    found = {}
    for write in done:
        if write.scope_gap or write.invalidates_all:
            found.clear()
        if not write.scope_gap and write.content is not None and write.resource_identity is not None:
            found[write.resource_identity] = write.content
        elif not write.scope_gap:
            found.pop(write.path, None)
    return found


def delivered_versions(exchanges) -> list[dict]:
    """Every retained delivery with exact bytes; a reused mutable path cannot prove its earlier contents."""
    found = []

    def snapshot_resource(path):
        display, identity, limits = resource(path)
        if not Path(path).is_file():
            return display, None, (*limits, "The retained snapshot path is unavailable.")
        return display, identity, limits

    last = {
        snapshot_resource(path)[1]: (turn, index)
        for turn, exchange in enumerate(exchanges, 1)
        for index, path in enumerate(exchange.execution.deliverables)
        if snapshot_resource(path)[1] is not None
    }
    uncertain = [
        (turn, index)
        for turn, exchange in enumerate(exchanges, 1)
        for index, path in enumerate(exchange.execution.deliverables)
        if snapshot_resource(path)[1] is None
    ]
    for turn, exchange in enumerate(exchanges, 1):
        for index, path in enumerate(exchange.execution.deliverables):
            content, fingerprint, unavailable = None, None, None
            _, identity, limits = snapshot_resource(path)
            if identity is None:
                unavailable = "The retained path's historical resource identity is unresolved: " + " ".join(limits)
            elif any(position > (turn, index) for position in uncertain):
                unavailable = "A later delivery has unresolved resource identity; this earlier mutable path cannot establish its historical bytes."
            elif last.get(identity) != (turn, index):
                unavailable = "An earlier delivery reused a mutable path without a separately retained snapshot."
            else:
                try:
                    data = Path(path).read_bytes()
                    fingerprint = hashlib.sha256(data).hexdigest()
                    try:
                        content = data.decode("utf-8")
                    except UnicodeError:
                        unavailable = "The delivered bytes cannot be decoded as a text letter or report."
                except OSError:
                    unavailable = "The retained delivery bytes are unavailable."
            found.append(
                {
                    "turn": turn,
                    "index": index,
                    "name": Path(path).name,
                    "sha256": fingerprint,
                    "content": content,
                    "unavailable": unavailable,
                    "execution_id": getattr(exchange.execution, "turn_id", None),
                    "original_path": str(path),
                    "resource_identity": identity,
                    "resource_limits": list(limits),
                }
            )
    return found


def write_records(done: list[Write]) -> list[dict]:
    """Expose attempted versus successful operations and all retained byte versions to semantic review."""
    return [
        {
            "order": w.order,
            "turn": w.turn,
            "actor": w.actor,
            "identity": w.identity,
            "tool": w.tool,
            "call_id": w.call_id,
            "execution_id": w.execution_id,
            "path": w.path,
            "monotonic_ns": w.monotonic_ns,
            "observed_at": w.observed_at,
            "ok": w.ok,
            "sha256": w.sha256,
            "content": w.content,
            "provenance": w.provenance,
            "arguments": w.arguments,
            "native_effects": list(w.native_effects),
            "scope_gap": w.scope_gap,
            "resource_identity": w.resource_identity,
            "resource_limits": list(w.resource_limits),
            "invalidates_all": w.invalidates_all,
            "content_is_full_state": w.content is not None,
            "bytes_known": w.bytes_known,
            "no_effect": w.no_effect,
            "observation_limits": "Requested fragments do not prove effects; native text may normalize newline bytes; present filesystem aliases cannot establish historical identity; observed state does not change the operation outcome.",
        }
        for w in done
    ]
