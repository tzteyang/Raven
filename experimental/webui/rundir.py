"""What the pages read of one run directory besides the Studio's slimmed view: the joined record, guarded so a record
that fails to load is a clear error rather than a traceback, with each round's verdicts; the opaque label each of its
sessions goes by where the Curator sees it; each sub-harness execution's work as steps; what a run keeps beside its iteration record that no role reads: the
standard assessor's record (`standard.json`), the compartment log (`boundaries.jsonl`, see
`experimental.iteration.compartment`) and where each material came from (the `provenance` of `settings.json`); and
how a curation in progress stands (its progress file) or where a paused one stopped (its checkpoint)."""

import json
from functools import lru_cache
from pathlib import Path

from experimental.iteration.hearing import opaque
from experimental.iteration.records import load
from experimental.webui.process import redact

BOUNDARY_ROWS = 2000
ERROR_KEEP = 1500
STANDARD_LIMIT = 8_000_000
# A sub-harness execution's work as a reader follows it: each tool call with its result and what it said, in order,
# each cut to a preview.
CHILD_STEPS = 200
STEP_PREVIEW = 400


class RecordError(Exception):
    """A run record that exists but cannot be read or joined, with why."""


def _reason(exc: Exception) -> str:
    text = f"{type(exc).__name__}: {exc}"
    return redact(text if len(text) <= ERROR_KEEP else text[:ERROR_KEEP] + "...")


def verdicts(round_: dict, analysis) -> list[dict]:
    """The round's verdicts by assessor: each signal that carries its items, and for an assessor whose signal carries
    none the scorecard it kept among the round's `analysis` records. An assessor that only speaks, such as the
    simulated owner (`experimental.simulation.agency`), keeps its verdicts there, where no role reads them; a scorecard
    whose every item names one of the round's held-out drills belongs to their assessment, not the round's."""
    carried = [signal for signal in round_.get("signals") or () if isinstance(signal, dict) and signal.get("items")]
    spoken = {signal.get("source") for signal in carried}
    held = set(round_.get("holdout") or ())
    kept = []
    for record in analysis or ():
        card = record.get("scorecard") if isinstance(record, dict) else None
        if not isinstance(card, dict) or card.get("source") in spoken or not isinstance(card.get("items"), list):
            continue
        sessions = {item.get("session") for item in card["items"] if isinstance(item, dict)}
        if held and sessions and sessions <= held:
            continue
        kept.append(card)
    return [*carried, *kept]


def _clip(value, limit: int = STEP_PREVIEW) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + "..."


def child_steps(rows) -> dict:
    """A sub-harness execution's work from its runner events: each tool call (name, arguments, result preview, whether
    it succeeded) and each reply, in order; past `CHILD_STEPS` the rest is only counted."""
    steps, calls = [], {}
    for row in rows if isinstance(rows, list) else ():
        if not isinstance(row, dict) or row.get("kind") != "runner.event" or not isinstance(row.get("event"), dict):
            continue
        event = row["event"]
        if row.get("event_type") == "ToolEvent" and event.get("phase") == "start":
            step = {"tool": str(event.get("name") or ""), "arguments": _clip(event.get("arguments") or {})}
            calls[event.get("tool_call_id")] = step
            steps.append(step)
        elif row.get("event_type") == "ToolEvent" and event.get("phase") == "complete":
            if step := calls.pop(event.get("tool_call_id"), None):
                step.update(result=_clip(event.get("result_preview") or ""), ok=event.get("ok") is not False)
        elif row.get("event_type") == "Text" and isinstance(event.get("content"), str) and event["content"].strip():
            steps.append({"text": _clip(event["content"], 4 * STEP_PREVIEW)})
    return {"steps": steps[:CHILD_STEPS], "steps_omitted": max(0, len(steps) - CHILD_STEPS)}


def _step_children(records) -> None:
    """Give every sub-harness execution among `records`, nested ones too, its `child_steps`."""
    for row in records if isinstance(records, list) else ():
        if not isinstance(row, dict):
            continue
        if row.get("kind") == "child.execution":
            row.update(child_steps(row.get("records")))
        _step_children(row.get("records"))


def joined(path: Path) -> dict:
    """`records.load(path)`: the run with its analysis, attribution and curation records and its ledger, each round
    with its `verdicts` and each sub-harness execution in its trials with its `child_steps`."""
    try:
        run = load(path)
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
        raise RecordError(f"the run record {Path(path).name} could not be loaded: {_reason(exc)}") from exc
    for holder in (*(run.get("rounds") or ()), run.get("pending")):
        if not isinstance(holder, dict):
            continue
        for part in ("sessions", "holdout"):
            for exchanges in (holder.get(part) or {}).values() if isinstance(holder.get(part), dict) else ():
                for exchange in exchanges or ():
                    execution = exchange.get("execution") if isinstance(exchange, dict) else None
                    _step_children(execution.get("records") if isinstance(execution, dict) else None)
    for round_ in run.get("rounds") or ():
        if isinstance(round_, dict):
            round_["verdicts"] = verdicts(round_, round_.get("analysis"))
    return run


def labels(run: dict) -> dict[str, str]:
    """Each session the record names (a round's trials and held-out trials, and the round in progress) with the opaque
    label it goes by in the cited turns, the activity rows, its session key and its replica folder
    (`experimental.iteration.hearing.opaque`)."""
    names = set()
    for holder in (*(run.get("rounds") or ()), run.get("pending")):
        for part in ("sessions", "holdout"):
            value = holder.get(part) if isinstance(holder, dict) else None
            if isinstance(value, dict):
                names.update(str(name) for name in value)
    return {name: opaque(name) for name in sorted(names)}


def _criterion_view(row: dict) -> dict:
    """Project the current contract or an unchanged legacy record into the read-only view."""
    fields = ("id", "text", "source", "strength", "provenance", "situation", "acceptance", "quote")
    if "definition" not in row:
        return {
            **{key: row.get(key, "") for key in fields},
            **{key: row[key] for key in ("kind", "authority", "checks") if key in row},
        }
    definition, basis, assessment = row["definition"], row.get("basis", {}), row.get("assessment", {})
    references = basis.get("references", ())
    decision = assessment.get("decision")
    checks = [("decision", decision), *(("required", check) for check in assessment.get("required_checks", ()))]
    return {
        "id": row.get("id", ""),
        "parent_id": row.get("parent_id"),
        "text": definition.get("acceptance", ""),
        "subject": definition.get("subject", ""),
        "situation": definition.get("applies_when", ""),
        "acceptance": definition.get("acceptance", ""),
        "source": row.get("origin", ""),
        "kind": row.get("kind", ""),
        "authority": row.get("authority", ""),
        "strength": "should" if row.get("kind") == "quality" else "must_hold",
        "provenance": ", ".join(
            f"{ref['source']}@{ref['version'][:12]}" if ref.get("version") else ref.get("source", "")
            for ref in references
        ),
        "quote": "\n".join(ref["quote"] for ref in references if ref.get("quote")),
        "derivation": basis.get("derivation", ""),
        "evidence_requirements": assessment.get("evidence_requirements", []),
        "checks": [
            {
                "role": role,
                "method": check.get("method", "") if check else "missing",
                "spec": (check.get("instruction") or check.get("verifier") or check.get("expression") or "")
                if check
                else "No whole-criterion decision",
            }
            for role, check in checks
        ],
    }


def standard(worker_root: Path) -> dict | None:
    """The standard the automatic assessor held the rounds to, as the simulation wrote it when the run ended: each
    criterion with its source, strength, provenance and, for a derived one, the norm passage it quotes; the norms the
    rubric builder read; the builder's numbered revisions (`experimental.assessor.builder`), each with the changes it
    applied and the passages it found nothing checkable in; and the model calls by label. None when the run kept no
    standard (yet)."""
    path = Path(worker_root) / "standard.json"
    if not path.is_file() or path.is_symlink():
        return None
    if path.stat().st_size > STANDARD_LIMIT:
        return {
            "error": f"standard.json is larger than {STANDARD_LIMIT} bytes",
            "criteria": [],
            "derived_from": [],
            "revisions": [],
        }
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        return {"error": _reason(exc), "criteria": [], "derived_from": [], "revisions": []}
    if not isinstance(value, dict):
        return {"error": "standard.json holds no object", "criteria": [], "derived_from": [], "revisions": []}
    builder = value.get("rubric_builder", value.get("critic"))
    builder = builder if isinstance(builder, dict) else {}
    reviewer = value.get("meta_reviewer")
    reviewer = reviewer if isinstance(reviewer, dict) else {}
    calls: dict[str, int] = {}
    for row in (*(value.get("trace") or ()), *(builder.get("trace") or ()), *(reviewer.get("trace") or ())):
        if isinstance(row, dict) and row.get("event") == "model.call":
            label = str(row.get("label") or "")
            label = {"critic": "rubric_builder", "standard": "assessor"}.get(label, label)
            calls[label] = calls.get(label, 0) + 1
    change_fields = ("id", "op", "reason", "explanation")
    revisions = [
        {
            "version": row.get("version"),
            **{key: row[key] for key in ("base_version", "rubric_version", "scope", "note") if key in row},
            "new_norms": [str(name) for name in row.get("new_norms") or ()],
            "changes": [
                {
                    **{key: str(change.get(key) or "") for key in change_fields},
                    "text": str(_criterion_view(change.get("criterion") or {}).get("text") or ""),
                    "quote": str(_criterion_view(change.get("criterion") or {}).get("quote") or ""),
                    "material": str(
                        (change.get("criterion") or {}).get("material")
                        or ", ".join(
                            ref.get("source", "")
                            for ref in (change.get("criterion") or {}).get("basis", {}).get("references", ())
                        )
                    ),
                    "before": (
                        _criterion_view(change["before"])["text"]
                        if isinstance(change.get("before"), dict)
                        else str(change.get("before") or "")
                    ),
                    **(
                        {"parent_id": change["criterion"]["parent_id"]}
                        if "parent_id" in (change.get("criterion") or {})
                        else {}
                    ),
                }
                for change in row.get("changes") or ()
                if isinstance(change, dict)
            ],
            "unchecked": [
                {key: str(item.get(key) or "") for key in ("material", "section", "reason")}
                for item in row.get("unchecked") or ()
                if isinstance(item, dict)
            ],
        }
        for row in builder.get("versions") or ()
        if isinstance(row, dict)
    ]
    record = {
        "criteria": [
            _criterion_view(row) for row in value.get("criteria") or () if isinstance(row, dict) and row.get("id")
        ],
        "derived_from": [str(name) for name in builder.get("read") or value.get("derived_from") or ()],
        "revisions": revisions,
        "calls": calls,
        "assessments": [
            {
                key: row[key]
                for key in (
                    "id",
                    "version",
                    "checks",
                    "review",
                    "unresolved",
                    "review_error",
                    "repair_error",
                    "learning_error",
                    "retained_program_failures",
                    "rubric_version",
                    "repair_status",
                    "repair_validation",
                    "repair_rejected",
                    "evidence_restored",
                )
                if key in row
            }
            for row in value.get("assessments", ())
            if isinstance(row, dict)
        ],
        "guidance": {
            "entries": [
                {"id": id, "state": row.get("state"), **row.get("proposal", {})}
                for id, row in (value.get("guidance") or {}).get("entries", {}).items()
            ],
            "history": (value.get("guidance") or {}).get("history", []),
        },
    }
    for key in ("assessments", "guidance"):
        if key not in value:
            record.pop(key)
    if "runs" in builder:
        record["construction"] = [
            {
                key: run[key]
                for key in ("status", "calls", "added", "steps", "error", "reason", "rubric_version")
                if key in run
            }
            for run in builder["runs"]
        ]
        record["pending"] = [
            {"target": work["target"], "reason": work["reason"]} for work in builder.get("pending", ())
        ]
    return redact(record)


def boundaries(worker_root: Path) -> dict | None:
    """The compartment log: every enter, admit, violation and leave row, the last `BOUNDARY_ROWS` of them, with each
    role's counts and every violation however old. None when the run kept no log."""
    path = Path(worker_root) / "boundaries.jsonl"
    if not path.is_file() or path.is_symlink():
        return None
    rows, violations, counts = [], [], {}
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError as exc:
        return {"error": _reason(exc), "rows": [], "violations": [], "counts": {}, "total": 0}
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict):
            continue
        kept = {
            "time": row.get("time") if isinstance(row.get("time"), (int, float)) else None,
            "role": str(row.get("role") or ""),
            "event": str(row.get("event") or ""),
            "where": str(row.get("where") or ""),
            "hits": [str(hit) for hit in row.get("hits") or ()],
        }
        role = counts.setdefault(kept["role"], {})
        role[kept["event"]] = role.get(kept["event"], 0) + 1
        rows.append(kept)
        if kept["event"] == "violation":
            violations.append(kept)
    return redact({"rows": rows[-BOUNDARY_ROWS:], "violations": violations, "counts": counts, "total": len(rows)})


def origins(worker_root: Path) -> dict[str, dict]:
    """Each material the run's scenario did not take as given, by name, with its origin (induced or researched), whether
    the counterpart confirmed it and the ids of the rules or findings it holds, as the run's settings keep the research
    stage's provenance. A material it does not name was given by the counterpart."""
    path = Path(worker_root) / "settings.json"
    if not path.is_file() or path.is_symlink() or path.stat().st_size > STANDARD_LIMIT:
        return {}
    try:
        settings = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    provenance = settings.get("provenance") if isinstance(settings, dict) else None
    materials = provenance.get("materials") if isinstance(provenance, dict) else None
    return {
        str(name): {
            "origin": str(row.get("origin") or "given"),
            "confirmed": row.get("confirmed") is not False,
            "items": [str(item) for item in row.get("items") or ()],
        }
        for name, row in (materials or {}).items()
        if isinstance(row, dict)
    }


def _json_file(path: Path):
    """A JSON file of the run, or the reason it cannot be read; files over `STANDARD_LIMIT` are refused."""
    if not path.is_file() or path.is_symlink():
        return None, None
    if path.stat().st_size > STANDARD_LIMIT:
        return None, f"{path.name} is larger than {STANDARD_LIMIT} bytes"
    try:
        return json.loads(path.read_text()), None
    except (OSError, ValueError) as exc:
        return None, f"{path.name}: {_reason(exc)}"


TROUBLE = ("output.missing", "output.rejected", "group.failed", "guidance.unavailable", "stage.timeout", "wave.skipped")
EVIDENCE_ROWS = 300
EVIDENCE_CHARS = 1_200


def _decoded(text) -> dict:
    """A JSON object kept as text in an evidence field, or an empty mapping when the text is not one."""
    try:
        value = json.loads(text) if isinstance(text, str) else None
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _evidence_row(row: dict) -> dict:
    """One research or answer evidence row as a reader needs it: the question it answers, its text, its kind
    (`finding`, `synthesis` or `answer`, empty for an answer the counterpart could not give) and its sources.
    The collector keeps the question and the finding as JSON text in `origin` and `content`."""
    origin, content = _decoded(row.get("origin")), _decoded(row.get("content"))
    raw = str(row.get("content") or "")
    if row.get("channel") == "user":
        answer = "" if raw.strip() in ("", "null") else raw
        kind, text = ("answer" if answer else ""), answer
    elif "synthesis" in content:
        kind, text = "synthesis", str(content.get("synthesis") or "")
    else:
        kind, text = "finding", str(content.get("text") or raw)
    return {
        "id": str(row.get("id") or ""),
        "channel": str(row.get("channel") or ""),
        "kind": kind,
        "question": str(origin.get("question") or content.get("question") or ""),
        "attempt": str(origin.get("attempt") or ""),
        "text": text[:EVIDENCE_CHARS],
        "sources": [str(source) for source in row.get("sources") or ()],
        "dimensions": [str(name) for name in row.get("dimensions") or ()],
    }


def _waves(folder: Path) -> list[dict]:
    """Every research group of every wave (`information/wave-<n>.json`): its questions, dimensions, how it ended and
    how many findings were admitted, refused or withheld."""
    groups = []
    for path in sorted(folder.glob("wave-*.json"), key=lambda item: item.stem):
        rows, _ = _json_file(path)
        for row in rows if isinstance(rows, list) else ():
            if not isinstance(row, dict):
                continue
            groups.append(
                {
                    "wave": path.stem.removeprefix("wave-"),
                    "group": row.get("group"),
                    "status": str(row.get("status") or ""),
                    "dimensions": [str(name) for name in row.get("dimensions") or ()],
                    "questions": [str(question) for question in row.get("questions") or ()],
                    "error": str(row.get("error") or "")[:600],
                    **{key: len(row.get(key) or ()) for key in ("admitted", "refused", "withheld", "unanswered")},
                    "seconds": row.get("seconds"),
                }
            )
    return groups


def _researchers(folder: Path) -> list[dict]:
    """The research agents the collector ran, from the `run.json` each agent call keeps
    (`experimental.research.researchers`): per agent, model asked for and effort, the models it reported answering
    with and how many calls it made."""
    found: dict[tuple[str, str, str], dict] = {}
    for path in sorted(folder.rglob("run.json")):
        row, _ = _json_file(path)
        if not isinstance(row, dict) or not row.get("researcher"):
            continue
        key = (str(row["researcher"]), str(row.get("model") or ""), str(row.get("effort") or ""))
        entry = found.setdefault(
            key, {"agent": key[0], "asked": key[1] or None, "effort": key[2] or None, "models": [], "calls": 0}
        )
        entry["calls"] += 1
        entry["models"].extend(
            name for name in dict.fromkeys(map(str, row.get("actual_models") or ())) if name not in entry["models"]
        )
    return list(found.values())


# The research stage's own records, each with the step that follows its writing; `plan-k` and `wave-k` mark a wave.
RESEARCH_STEPS = (
    ("request.json", "assessing the materials"),
    ("assessment.json", "asking the counterpart or planning"),
    ("questions.json", "planning research"),
    ("plan-", "researching"),
    ("wave-", "composing the description"),
    ("proposal-", "reviewing the description"),
)
RESEARCH_ACTIONS = 6
RESEARCH_QUESTION = 240


def research_progress(worker_root: Path) -> dict | None:
    """The research stage while it runs, from what it has written under `information/`; None before it starts and once
    its `status.json` says how it ended. `step` is what follows its newest record; per research agent call
    (`research-N`: an acquisition, then its review) the questions it was asked, whether it ended, and the searches and
    page reads in its event stream with the latest of them. Claude Code streams those events while it works, so a
    reader sees a call's searches as they happen."""
    folder = Path(worker_root) / "information"
    if not folder.is_dir() or folder.is_symlink() or (folder / "status.json").exists():
        return None
    stepped = [
        (path.stat().st_mtime, label)
        for path in folder.iterdir()
        if path.is_file()
        for prefix, label in RESEARCH_STEPS
        if path.name.startswith(prefix)
    ]
    if not stepped:
        return None
    calls, times = [], [mtime for mtime, _ in stepped]
    places = [path for path in folder.glob("research-*") if path.is_dir() and path.name[9:].isdigit()]
    for place in sorted(places, key=lambda path: int(path.name[9:])):
        status, _ = _json_file(place / "status.json")
        brief, _ = _json_file(place / "brief.json")
        streams = [place / part / "events.jsonl" for part in ("acquisition", "review")]
        streams = [stream for stream in streams if stream.is_file()]
        acted = [_actions(str(stream), stream.stat().st_mtime_ns, stream.stat().st_size) for stream in streams]
        times.extend(stream.stat().st_mtime for stream in streams)
        ended = status.get("status") if isinstance(status, dict) else None
        calls.append(
            {
                "call": int(place.name[9:]),
                "status": str(ended or ("reviewing" if len(streams) > 1 else "researching")),
                "questions": [
                    str(question)[:RESEARCH_QUESTION]
                    for question in (brief.get("questions") if isinstance(brief, dict) else None) or ()
                ][:3],
                "searches": sum(row["searches"] for row in acted),
                "reads": sum(row["reads"] for row in acted),
                "recent": [action for row in acted for action in row["recent"]][-RESEARCH_ACTIONS:],
                "updated": max([stream.stat().st_mtime for stream in streams] or [place.stat().st_mtime]),
            }
        )
    return redact(
        {
            "started": min(mtime for mtime, _ in stepped),
            "updated": max(times),
            "step": max(stepped)[1],
            "calls": calls,
        }
    )


@lru_cache(maxsize=256)
def _actions(path: str, mtime_ns: int, size: int) -> dict:
    """The searches and page reads one research agent's event stream shows, read once per version of the file."""
    searches = reads = 0
    recent = []
    try:
        lines = Path(path).read_text(errors="replace").splitlines()
    except OSError:
        lines = []
    for line in lines:
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if not isinstance(item, dict) or item.get("type") != "assistant":
            continue
        for block in (item.get("message") or {}).get("content") or ():
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            given = block.get("input") if isinstance(block.get("input"), dict) else {}
            if block.get("name") == "WebSearch":
                searches += 1
                recent.append({"tool": "search", "text": str(given.get("query") or "")[:RESEARCH_QUESTION]})
            elif block.get("name") == "WebFetch":
                reads += 1
                recent.append({"tool": "read", "text": str(given.get("url") or "")[:RESEARCH_QUESTION]})
            elif block.get("name") == "StructuredOutput":
                recent.append({"tool": "submit", "text": ""})
    return {"searches": searches, "reads": reads, "recent": recent[-RESEARCH_ACTIONS:]}


def research(worker_root: Path) -> dict | None:
    """The research stage's records beside the run (`experimental/research/`, written under `information/`): how the
    collection ended (status, stop reason, seconds), the review's verdict with its reason and issues, the description's
    title and each dimension's coverage with its text, reason, evidence count and the channels that evidence came
    through, the resources and open questions, per stage the model calls, queries and whether it submitted, with every
    reply that was missing, rejected or failed; how much evidence each channel brought (`request`, `tool` for the
    materials read, `research`, `user` for the counterpart's answers), the research and answer evidence itself, each
    research group of each wave and the research agents that ran (`_researchers`). None when the run collected no
    information."""
    folder = Path(worker_root) / "information"
    if not folder.is_dir() or folder.is_symlink():
        return None
    status, status_error = _json_file(folder / "status.json")
    result, result_error = _json_file(folder / "result.json")
    trace, trace_error = _json_file(folder / "trace.json")
    kept, evidence_error = _json_file(folder / "evidence.json")
    evidence = [row for row in kept if isinstance(row, dict)] if isinstance(kept, list) else []
    channel_of = {str(row.get("id")): str(row.get("channel") or "") for row in evidence}
    channels: dict[str, int] = {}
    for row in evidence:
        channels[channel_of[str(row.get("id"))]] = channels.get(channel_of[str(row.get("id"))], 0) + 1
    status = status if isinstance(status, dict) else {}
    result = result if isinstance(result, dict) else {}
    review = result.get("review") if isinstance(result.get("review"), dict) else {}
    description = (result.get("snapshot") or {}).get("description") or {}
    stages: dict[str, dict] = {}
    trouble = []
    for row in trace if isinstance(trace, list) else ():
        if not isinstance(row, dict):
            continue
        label, event = str(row.get("label") or ""), str(row.get("event") or "")
        stage = stages.setdefault(label, {"stage": label, "calls": 0, "queries": 0, "submitted": False})
        if event == "model.call":
            stage["calls"] += 1
        elif event == "query":
            stage["queries"] += 1
        elif event.startswith(("submit_", "review_")):
            stage["submitted"] = True
        elif event in TROUBLE:
            trouble.append(
                {
                    "stage": label,
                    "event": event,
                    "error": " ".join(
                        part
                        for part in (
                            f"group {row['group']}:" if "group" in row else "",
                            f"wave {row['wave']}:" if "wave" in row else "",
                            str(row.get("error") or row.get("error_type") or row.get("finish_reason") or ""),
                            f"{row['window']} s left" if event == "wave.skipped" and "window" in row else "",
                        )
                        if part
                    )[:600],
                    "tools": [str(name) for name in row.get("tools") or ()],
                    "charged": row.get("charged", True) is not False,
                }
            )
    return redact(
        {
            "status": str(status.get("status") or ""),
            "stop_reason": str(status.get("stop_reason") or result.get("stop_reason") or ""),
            "seconds": status.get("seconds"),
            "review": {
                "accepted": bool(review.get("accepted")),
                "reason": str(review.get("reason") or ""),
                "issues": [str(issue) for issue in review.get("issues") or ()],
            },
            "title": str(description.get("title") or ""),
            "sections": [
                {
                    "dimension": str(section.get("dimension") or ""),
                    "coverage": str(section.get("coverage") or ""),
                    "text": str(section.get("text") or ""),
                    "reason": str(section.get("reason") or ""),
                    "evidence": len(section.get("evidence") or ()),
                    "channels": sorted({channel_of.get(str(id), "") for id in section.get("evidence") or ()} - {""}),
                }
                for section in description.get("sections") or ()
                if isinstance(section, dict)
            ],
            "resources": [
                {key: str(item.get(key) or "") for key in ("name", "purpose", "availability")}
                for item in description.get("resources") or ()
                if isinstance(item, dict)
            ],
            "unresolved": [
                {
                    **{key: str(item.get(key) or "") for key in ("dimension", "question", "reason")},
                    "blocking": bool(item.get("blocking")),
                }
                for item in description.get("unresolved") or ()
                if isinstance(item, dict)
            ],
            "stages": list(stages.values()),
            "trouble": trouble,
            "channels": channels,
            "evidence": [_evidence_row(row) for row in evidence if row.get("channel") in ("research", "user")][
                :EVIDENCE_ROWS
            ],
            "groups": _waves(folder),
            "researchers": _researchers(folder),
            "errors": [error for error in (status_error, result_error, trace_error, evidence_error) if error],
        }
    )


def annex(worker_root: Path) -> dict:
    """The run directory's files beside the record, under the keys the pages read them by."""
    return {
        "standard": standard(worker_root),
        "boundaries": boundaries(worker_root),
        "origins": origins(worker_root),
        "research": research(worker_root),
    }


def _scoped(worker_root: Path, relative: str) -> list[Path] | None:
    """`relative` under the worker root, or under every scope of a composite curation in progress; None when its
    checkpoint cannot be read."""
    checkpoint = worker_root / "curation" / "composition.json"
    paths = [worker_root / relative]
    if checkpoint.is_file() and checkpoint.resolve().is_relative_to(worker_root.resolve()):
        try:
            directory = Path(json.loads(checkpoint.read_text())["directory"])
            if directory.resolve().is_relative_to(worker_root.resolve()):
                paths = list(directory.glob(f"*/{relative}"))
        except (OSError, ValueError, KeyError, TypeError):
            return None
    return [path for path in paths if path.is_file() and path.resolve().is_relative_to(worker_root.resolve())]


def progress_path(worker_root: Path) -> Path | None:
    """The Curator's live progress file: the root's, or in a composite curation the scope's written last."""
    paths = _scoped(worker_root, "progress/curation.json")
    return max(paths, key=lambda path: path.stat().st_mtime) if paths else None


def pending_stage(worker_root: Path) -> str | None:
    """The stage a paused curation stopped at, from its checkpoint: `diagnose` while it holds a paused attribution,
    else its generation's stage."""
    paths = _scoped(worker_root, "curation/pending.json")
    if not paths:
        return None
    try:
        pending = json.loads(max(paths, key=lambda path: path.stat().st_mtime).read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(pending, dict):
        return None
    if pending.get("attribution_state"):
        return "diagnose"
    return (pending.get("state") or {}).get("stage")


def _scope_name(worker_root: Path, folder: str) -> str:
    """The harness a composite curation's scope folder revises: the child its checkpoint maps the folder to, or the
    folder's own name (`root`)."""
    try:
        scopes = json.loads((worker_root / "curation" / "composition.json").read_text()).get("scopes")
    except (OSError, ValueError, AttributeError):
        scopes = None
    named = (
        {value: name for name, value in scopes.items() if isinstance(value, str)} if isinstance(scopes, dict) else {}
    )
    return named.get(folder, folder)


def curator_progress(worker_root: Path) -> dict | None:
    """The Curator's live progress file, which it rewrites before every model call and after every validation; in a
    composite curation, the scope written last, named by the harness it revises, with the counts of every scope."""
    path = progress_path(worker_root)
    if path is None:
        return None
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(value, dict):
        return None
    if path.parent.parent != worker_root:
        scope = path.parent.parent
        value["scope"] = _scope_name(worker_root, scope.name)
        rows = []
        for other in scope.parent.glob("*/progress/curation.json"):
            if not other.resolve().is_relative_to(worker_root.resolve()):
                continue
            try:
                rows.append(json.loads(other.read_text()))
            except (OSError, ValueError):
                continue
        for counter in ("calls", "queries", "checks", "repairs"):
            value[counter] = sum(row.get(counter, 0) for row in rows if isinstance(row, dict))
    return value
