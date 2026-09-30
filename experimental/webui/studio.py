"""The Studio's view of a recorded run: the joined record with the bulky model inputs cut down, and those inputs
served one at a time on request.

A run's model inputs (`provider.request`, `model.input`), capability views, assembled contexts, long strategy calls and
sub-harness executions (`child.execution`) are most of its size, and the Studio needs their bodies only when a reader
opens one. `slim` keeps what identifies each and replaces its body with a reference that `raw_record` resolves, in a
round's trials, its held-out trials and the round still in progress (`pending`). The Curator's and the attributor's
records are cut the same way: a query keeps a preview of what it returned, an attributor's request its size, and a
composite curation drops its checkpoint, which repeats the root's generation.
"""

import json
import threading
import time
from pathlib import Path

from .process import redact
from .rundir import annex, joined, labels

# What a sub-harness execution keeps of its records: the mechanisms that acted and the inputs its model received.
CHILD_KEPT = ("action.", "planning.", "capability.", "memory.", "strategy.", "loop.", "model.input")
CACHE_SIZE = 4
# A strategy call whose arguments exceed this many characters keeps only what identifies it.
BULKY = 2000
# What a Curator or attributor query keeps of its result.
PREVIEW = 600
INDEX_TTL = 120
PARTS = ("sessions", "holdout")
# Strategy results that can carry a whole model input or plan; an Action result is a decision and stays whole.
LONG_RESULTS = ("memory.result", "capability.result", "planning.result")

_cache: dict[Path, tuple[tuple[int, int], dict]] = {}
_guard = threading.Lock()
_index: dict[Path, tuple[tuple, float, list]] = {}
_building: set[Path] = set()


def _size(value) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str))


def _messages(holder: dict) -> dict:
    messages = holder.get("messages") if isinstance(holder.get("messages"), list) else []
    chars = sum(_size(message.get("content")) for message in messages if isinstance(message, dict))
    return {"count": len(messages), "chars": chars}


def _names(items) -> list[str]:
    names = []
    for item in items if isinstance(items, list | tuple) else ():
        if isinstance(item, dict):
            name = item.get("name") or (item.get("function") or {}).get("name")
            if name:
                names.append(str(name))
    return names


def event_summary(arguments) -> dict:
    """The identifying fields of a strategy call's first argument (an event or a request), without its payload."""
    first = arguments[0] if isinstance(arguments, list) and arguments and isinstance(arguments[0], dict) else {}
    summary = {
        key: first[key] for key in ("kind", "stage", "event_id", "request_id", "allowed_controls") if key in first
    }
    if isinstance(first.get("text"), str):
        summary["text"] = first["text"][:400]
    if isinstance(first.get("calls"), list):
        summary["calls"] = _names(first["calls"])
    if "command" in first and _size(first["command"]) <= 400:
        summary["command"] = first["command"]
    return summary


def _slim_record(record: dict, ref: dict) -> dict:
    """A record whose body is a model input, a capability view, a context or a long strategy call, reduced to what
    identifies it plus `ref`; any other record as it was kept."""
    kind = str(record.get("kind") or "")
    head = {"kind": kind, "turn_id": record.get("turn_id"), "ref": ref}
    if kind == "provider.request":
        parameters = record.get("parameters") if isinstance(record.get("parameters"), dict) else {}
        tools = parameters.get("tools") if isinstance(parameters.get("tools"), list) else []
        return {
            **head,
            "model": parameters.get("model"),
            "reasoning_effort": parameters.get("reasoning_effort"),
            "messages": _messages(parameters),
            "tools": len(tools),
        }
    if kind == "model.input":
        return {**head, "messages": _messages(record), "tools": len(record.get("tools") or [])}
    if kind == "capability.effective":
        view = record.get("view") if isinstance(record.get("view"), dict) else {}
        return {**head, "tools": _names(view.get("tools")), "skills": _names(view.get("skills"))}
    if kind == "memory.context":
        return {**head, **{key: record[key] for key in ("estimated_tokens", "allowance", "sources") if key in record}}
    if kind == "child.execution":
        return _slim_child(record, ref)
    if kind.endswith(".call") and _size(record.get("arguments")) > BULKY:
        rest = {key: value for key, value in record.items() if key != "arguments"}
        return {
            **rest,
            "arguments": {"size": _size(record.get("arguments")), **event_summary(record.get("arguments"))},
            "ref": ref,
        }
    if kind in LONG_RESULTS and _size(record.get("result")) > BULKY:
        rest = {key: value for key, value in record.items() if key != "result"}
        return {**rest, "result": _result_summary(record.get("result")), "ref": ref}
    return record


def _result_summary(result) -> dict:
    """A long strategy result's small fields as they are (a Memory order, a decision) and its size."""
    kept = {"size": _size(result)}
    if isinstance(result, dict):
        kept.update({key: value for key, value in result.items() if _size(value) <= BULKY // 5})
    return kept


def _slim_child(record: dict, ref: dict) -> dict:
    inner = record.get("records") if isinstance(record.get("records"), list) else []
    counts: dict[str, int] = {}
    kept = []
    for position, row in enumerate(inner):
        kind = row.get("kind", "") if isinstance(row, dict) else ""
        counts[kind] = counts.get(kind, 0) + 1
        if isinstance(row, dict) and str(kind).startswith(CHILD_KEPT):
            kept.append(_slim_record(row, {**ref, "child": position}))
    rest = {key: value for key, value in record.items() if key != "records"}
    return {**rest, "records": kept, "counts": counts, "ref": ref}


def slim_exchange(exchange: dict, ref: dict) -> dict:
    """One exchange with its bulky records reduced (see `_slim_record`), each referred to under `ref`, which names the
    round, part, session and turn the exchange is kept at."""
    execution = dict(exchange.get("execution") or {})
    execution["records"] = [
        _slim_record(record, {**ref, "index": index}) for index, record in enumerate(execution.get("records") or [])
    ]
    execution.pop("events", None)
    return {**exchange, "execution": execution}


def _slim_sessions(sessions, ref: dict) -> dict:
    return {
        key: [
            slim_exchange(exchange, {**ref, "session": key, "turn": turn})
            for turn, exchange in enumerate(exchanges or ())
        ]
        for key, exchanges in (sessions or {}).items()
    }


def _preview(value):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= PREVIEW else text[:PREVIEW] + "..."


def _slim_trace(trace) -> list:
    """A generation or attribution trace with each query's result cut to a preview and long notes shortened; what a
    stage submitted is kept whole, since the raw-output pane shows it."""
    out = []
    for event in trace if isinstance(trace, list) else ():
        if not isinstance(event, dict):
            continue
        kept = dict(event)
        if event.get("event") in ("query", "query.rejected", "tool.skipped", "action.unavailable"):
            result = event.get("result")
            if isinstance(result, dict):
                kept["result"] = {
                    key: _preview(item) if key in ("text", "error") else item
                    for key, item in result.items()
                    if key in ("text", "error", "failed", "index")
                }
            elif result is not None:
                kept["result"] = _preview(result)
            if _size(event.get("arguments")) > BULKY:
                kept["arguments"] = _preview(event.get("arguments"))
        if event.get("event") == "validation" and _size(event.get("observations")) > BULKY:
            kept["observations"] = _slim_observations(event.get("observations"))
        if isinstance(event.get("content"), str) and len(event["content"]) > 4 * PREVIEW:
            kept["content"] = event["content"][: 4 * PREVIEW] + "..."
        out.append(kept)
    return out


def _slim_observations(rows) -> list:
    """Validation observations with a child execution cut to its record counts."""
    out = []
    for row in rows if isinstance(rows, list) else ():
        if isinstance(row, dict) and row.get("kind") == "child.execution" and _size(row) > BULKY:
            records = row.get("records") if isinstance(row.get("records"), list) else []
            counts: dict[str, int] = {}
            for item in records:
                kind = str(item.get("kind", "")) if isinstance(item, dict) else ""
                counts[kind] = counts.get(kind, 0) + 1
            out.append({key: row[key] for key in ("kind", "harness", "revision") if key in row} | {"counts": counts})
        else:
            out.append(row)
    return out


def _slim_generated(generated):
    if not isinstance(generated, dict):
        return generated
    kept = {**generated, "trace": _slim_trace(generated.get("trace"))}
    validation = generated.get("validation")
    if isinstance(validation, dict):
        kept["validation"] = {**validation, "observations": _slim_observations(validation.get("observations"))}
    return kept


def _slim_curation(record):
    """A curation record with its traces cut (see `_slim_trace`) and a composite checkpoint reduced to its scopes."""
    if not isinstance(record, dict):
        return record
    kept = dict(record)
    if "generated" in kept:
        kept["generated"] = _slim_generated(kept["generated"])
    if isinstance(kept.get("child_changes"), dict):
        kept["child_changes"] = {name: _slim_generated(value) for name, value in kept["child_changes"].items()}
    if isinstance(kept.get("composition"), dict):
        composition = kept["composition"]
        kept["composition"] = {key: composition[key] for key in ("input_id", "scopes", "error") if key in composition}
    if "trace" in kept:
        kept["trace"] = _slim_trace(kept["trace"])
    return kept


def _slim_attribution(record):
    """An attribution record without its request (only its size is kept) and with its trace cut."""
    if not isinstance(record, dict):
        return record
    kept = {key: value for key, value in record.items() if key not in ("request", "feedback")}
    if isinstance(record.get("request"), list):
        kept["request"] = _messages({"messages": record["request"]})
    if "trace" in record:
        kept["trace"] = _slim_trace(record["trace"])
    return kept


def slim(run: dict) -> dict:
    """The joined run with each bulky record (see `_slim_record`) reduced to a summary and a `ref` for `raw_record`,
    and its curation and attribution records cut down."""
    rounds = []
    for number, round_ in enumerate(run.get("rounds") or []):
        kept = {
            **round_,
            **{part: _slim_sessions(round_.get(part), {"round": number, "part": part}) for part in PARTS},
        }
        kept["curation"] = [_slim_curation(record) for record in round_.get("curation") or ()]
        kept["attribution"] = [_slim_attribution(record) for record in round_.get("attribution") or ()]
        rounds.append(kept)
    out = {
        **run,
        "rounds": rounds,
        "initial_curation": [_slim_curation(record) for record in run.get("initial_curation") or ()],
        "initial_attribution": [_slim_attribution(record) for record in run.get("initial_attribution") or ()],
    }
    pending = run.get("pending")
    if isinstance(pending, dict):
        out["pending"] = {
            **pending,
            **{part: _slim_sessions(pending.get(part), {"round": "pending", "part": part}) for part in PARTS},
        }
    return out


def studio_run(path: Path) -> dict:
    """`slim` of the joined record, cached by the record file's size and modification time while a few runs are open,
    with its sessions' opaque labels (`rundir.labels`) and the run directory's standard and compartment log
    (`rundir.annex`) read fresh; a record that fails to load raises `rundir.RecordError`."""
    stat = path.stat()
    key = (stat.st_mtime_ns, stat.st_size)
    with _guard:
        hit = _cache.get(path)
    if hit and hit[0] == key:
        value = hit[1]
    else:
        value = slim(joined(path))
        with _guard:
            _cache[path] = (key, value)
            while len(_cache) > CACHE_SIZE:
                _cache.pop(next(iter(_cache)))
    return {**value, "labels": labels(value), **annex(path.parents[1])}


def studio_index(root: Path, build) -> list[dict]:
    """`build(root)` (the viewer's run index), kept between calls and refreshed in the background.

    Building the index reads every record in full, which takes tens of seconds over a large runs folder. The first
    call builds it; later calls answer at once with the last index and, when an iteration record changed or the
    index is `INDEX_TTL` old (a running record may have stalled since), rebuild it on a thread for the next call.
    """
    root = Path(root)
    key = _index_key(root)
    with _guard:
        hit = _index.get(root)
    if hit is None:
        value = build(root)
        with _guard:
            _index[root] = (key, time.time(), value)
        return value
    if hit[0] != key or time.time() - hit[1] >= INDEX_TTL:
        _refresh(root, build, key)
    return hit[2]


def _index_key(root: Path) -> tuple:
    return tuple(
        (str(path), path.stat().st_mtime_ns, path.stat().st_size)
        for worker in sorted(item for item in root.iterdir() if item.is_dir())
        for path in sorted((worker / "iteration").glob("*.json"))
    )


def _refresh(root: Path, build, key: tuple) -> None:
    with _guard:
        if root in _building:
            return
        _building.add(root)

    def work():
        try:
            value = build(root)
            with _guard:
                _index[root] = (key, time.time(), value)
        finally:
            with _guard:
                _building.discard(root)

    threading.Thread(target=work, daemon=True).start()


def raw_record(
    path: Path,
    round_: int | None,
    session: str,
    turn: int,
    index: int,
    child: int | None = None,
    part: str = "sessions",
) -> dict | None:
    """One record as the run kept it, secrets redacted, named by the `ref` that `slim` left in its place: `round_` is
    the round's index, or None for the round in progress; `part` its trials or its held-out trials; `child` a record
    inside a sub-harness execution. A record that fails to load raises `rundir.RecordError`."""
    if part not in PARTS:
        return None
    run = joined(path)
    try:
        holder = run["pending"] if round_ is None else run["rounds"][round_]
        record = holder[part][session][turn]["execution"]["records"][index]
        return redact(record if child is None else record["records"][child])
    except (IndexError, KeyError, TypeError):
        return None
