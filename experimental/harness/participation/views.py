"""Views of a worker's exchanges that every participant reads alike: the conversation as the other side saw it, the
files handed over either way, what the worker filed beside its replies, the calls it made besides looking around, and
the reports its colleagues sent back."""

import hashlib
import json
import re
from collections import defaultdict, deque
from pathlib import Path

from experimental.harness.participation.allowance import excerpt, reading_budget
from experimental.harness.participation.channel import said
from experimental.harness.participation.files import read_delivered
from experimental.harness.raven_adapter.action.runtime import REFUSED
from experimental.harness.raven_adapter.observe import plain

REPORT = re.compile(
    r"\[BEGIN UNTRUSTED subagent #(?P<tag>\w+)[^\]\n]*\]\n(?P<body>.*?)\n\[END UNTRUSTED subagent #(?P=tag)\]", re.S
)
ANNOUNCE = re.compile(
    r"\[Subagent '[^\n]*' [^\n]*\]\n\nTask: (?P<task>.*?)\n(?:\nInstance handle: [^\n]*\n)?"
    r"(?:Working directory: [^\n]*\n)?\nResult:\Z",
    re.S,
)
FAILED_CALLS = re.compile(r"^\[raven\] (?P<failed>\d+) of this run's (?P<made>\d+) tool calls? failed\.")
OTHER_BLOCK = re.compile(
    r"\[BEGIN UNTRUSTED (?!subagent )[^\]#]*#(?P<tag>\w+)[^\]]*\].*?\[END UNTRUSTED [^\]#]*#(?P=tag)\]", re.S
)
TASK_LABEL, ANSWER_LABEL = "The task the sub-agent was given:", "What it returned as its answer:"
TAIL_LABEL = "Tail of what the sub-agent did"
LOOKS = frozenset({"read_file", "list_dir", "grep", "find", "web_search", "web_fetch", "load_skill", "read_skill"})
TEXT_FILES = frozenset({".md", ".txt", ".csv", ".json", ".yaml", ".yml"})
PRIVATE = frozenset({"sessions", "subagents", "uploads", "skills", "memory", "agent_memory", "user_memory", "decks"})


def execution_digest(sessions) -> str:
    """Bind an assessment to actual turn records, outcomes and delivered bytes, independent of archive paths."""
    evidence = {}
    for name, exchanges in sessions.items():
        evidence[name] = []
        for exchange in exchanges:
            execution = exchange.execution
            files = []
            for path in execution.deliverables:
                try:
                    fingerprint = hashlib.sha256(Path(path).read_bytes()).hexdigest()
                except OSError:
                    fingerprint = None
                files.append({"name": Path(path).name, "sha256": fingerprint})
            evidence[name].append(
                {
                    "turn_id": execution.turn_id,
                    "artifact_id": getattr(execution, "artifact_id", ""),
                    "user": exchange.user,
                    "records": plain(execution.records),
                    "outcome": plain(getattr(execution, "outcome", {})),
                    "deliverables": files,
                }
            )
    return hashlib.sha256(json.dumps(evidence, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def transcript(exchanges, speaker: str = "customer") -> list[dict]:
    """What the speaker saw: each message, the names of any files handed over with it, and why the reply never
    came, if it did not."""
    rows = []
    for exchange in exchanges:
        row = {speaker: exchange.user, "assistant": said(exchange)}
        if exchange.execution.deliverables:
            row["delivered"] = [Path(path).name for path in exchange.execution.deliverables]
        if exchange.stopped:
            row["stopped"] = exchange.stopped
        rows.append(row)
    return rows


def opened(exchanges, *, tokens: int | None = None) -> dict[str, str]:
    """What a person sees on opening each file handed over so far, latest version of each, cut to `tokens` with a
    note of what is left out (`experimental.harness.participation.allowance.reading_budget` by default)."""
    tokens = reading_budget() if tokens is None else tokens
    files = {}
    for exchange in exchanges:
        for path in exchange.execution.deliverables:
            if Path(path).is_file():
                files[Path(path).name] = excerpt(read_delivered(path), tokens)
    return files


def cut(text: str, tokens: int | None = None) -> str:
    """`text` up to about `tokens` tokens (`experimental.harness.participation.allowance.reading_budget` by default); a longer one says how
    much was left out, so the owner never takes a cut document for the whole of it."""
    return excerpt(text, reading_budget() if tokens is None else tokens)


def _changed(folder: Path, before: Path, skip=frozenset()):
    """Each file under `folder` that is new or changed against `before`, as its path relative to `folder` and its
    resolved path, in name order. Hidden entries and `__pycache__` are skipped, and so are top-level entries named in
    `skip`. Escaped links cannot supply file contents or prove a change against the baseline."""
    folder, before = Path(folder), Path(before)
    if folder.is_symlink() or before.is_symlink() or not folder.is_dir():
        return
    current_root, baseline_root = folder.resolve(), before.resolve()
    for path in sorted(folder.rglob("*")):
        relative = path.relative_to(folder)
        if (
            skip & set(relative.parts[:1])
            or "__pycache__" in relative.parts
            or any(part.startswith(".") for part in relative.parts)
        ):
            continue
        try:
            current, old = path.resolve(), (before / relative).resolve()
        except (OSError, RuntimeError):
            continue
        if not current.is_relative_to(current_root) or not old.is_relative_to(baseline_root) or not current.is_file():
            continue
        if old.is_file() and old.read_bytes() == current.read_bytes():
            continue
        yield relative, current


def written(folder: Path, before: Path, *, label: str, skip=frozenset(), tokens: int | None = None) -> dict[str, str]:
    """Files under `folder` that are new or changed against `before`, keyed `label/relative path`.

    Text files come with their content; anything else (decks, scripts, build output) is listed by name only. Hidden
    entries are the host's and tools' own bookkeeping (Raven's `.raven` checkpoints, a deck engine's dot files), not
    something the employee filed. Escaped links cannot supply file contents or prove a change against the baseline.
    """
    files = {}
    for relative, path in _changed(folder, before, skip):
        key = f"{label}/{relative.as_posix()}"
        if relative.suffix.lower() in TEXT_FILES and not relative.parts[0] == "decks":
            text = path.read_bytes().decode(errors="replace")
            files[key] = cut(text.replace("\r\n", "\n").replace("\r", "\n"), tokens)
        else:
            files[key] = f"[{relative.suffix or 'file'}; content not shown]"
    return files


def handed(folder: Path, before: Path, *, label: str, tokens: int | None = None) -> dict[str, str]:
    """Files under `folder` that `before` does not hold as they are, keyed `label/relative path`: what was handed in
    on top of a baseline, each as a person sees it on opening it (see `read_delivered`), cut to `tokens` with a note
    of what is left out (`experimental.harness.participation.allowance.reading_budget` by default)."""
    tokens = reading_budget() if tokens is None else tokens
    return {
        f"{label}/{relative.as_posix()}": excerpt(read_delivered(path), tokens)
        for relative, path in _changed(folder, before)
    }


def reports(exchanges, *, tokens: int | None = None) -> list[dict]:
    """Every report a colleague (a subagent or a playbook step) sent back to the employee, with the task it had.

    Read from the model requests of the employee's turns, where each reaches it in marked blocks: a delegation's
    announced result quotes the task the employee wrote for it, and a tally of its failed tool calls when it had any
    (`failed_calls`); a reviewed result names the task it was given, then what it returned as its answer (the tail of
    what it did is left out); a playbook step's account follows the note that names the step. The task is the
    employee's own hand-over, so it is kept whole up to the same `tokens` as the report. The same report repeats in
    every later request, so each is kept once.
    """
    found: dict[str, dict] = {}
    for turn in exchanges:
        for row in turn.execution.records:
            if row.get("kind") != "provider.request":
                continue
            for message in (row.get("parameters") or {}).get("messages") or []:
                content = message.get("content") if isinstance(message, dict) else None
                if not isinstance(content, str) or "[BEGIN UNTRUSTED subagent" not in content:
                    continue
                content, task, start, last = OTHER_BLOCK.sub("", content), "", 0, None
                for match in REPORT.finditer(content):
                    lead = content[start : match.start()].strip()
                    start = match.end()
                    label = lead.splitlines()[-1] if lead else ""
                    body = match.group("body").strip()
                    if TASK_LABEL in label:
                        task = body
                        continue
                    if label.startswith(TAIL_LABEL):
                        continue
                    tally = FAILED_CALLS.match(lead.split("\n\n")[-1])
                    if tally:
                        if last is not None and "failed_calls" not in last:
                            last["failed_calls"] = f"{tally['failed']} of {tally['made']} failed: {body}"
                        continue
                    announced = ANNOUNCE.search(lead)
                    if announced:
                        asked = announced.group("task").strip()
                    else:
                        asked = task if ANSWER_LABEL in label else lead.split("\n\n")[-1]
                        asked = asked.split("Working directory:", 1)[0].strip()
                        asked = "" if asked.startswith("[Runtime Context") else asked
                    report = cut(body, tokens)
                    last = found.setdefault(report, {"task": "", "report": report})
                    last["task"] = last["task"] or cut(asked, tokens)
    return list(found.values())


def back_office(exchanges) -> list[dict]:
    """What the employee did besides talking, turn by turn and in order: files written, commands, playbooks,
    delegations and deliveries, each with whether it succeeded (see `actions`), so the owner can see what happened
    before what and never takes a failed write for a filed ticket."""
    return [
        {"turn": index, **action}
        for index, turn in enumerate(exchanges, start=1)
        for action in actions(turn.execution.records)
    ]


def actions(records) -> list[dict]:
    """The calls in one execution's records besides looking around, in order, each with its target and whether it
    succeeded (`ok`, with the tool's error when it failed, null when no outcome was recorded). A call an Action
    strategy refused did not run, so it failed, with the refusal as its error."""
    started, pending, finished = [], defaultdict(deque), {}
    for row in records:
        event = row.get("event") or {}
        if row.get("kind") != "runner.event" or row.get("event_type", "ToolEvent") != "ToolEvent":
            continue
        if event.get("phase") == "start" and event.get("name"):
            pending[event.get("tool_call_id")].append(len(started))
            started.append(event)
        elif event.get("phase") == "complete" and event.get("tool_call_id"):
            waiting = pending[event["tool_call_id"]]
            if waiting:
                finished[waiting.popleft()] = event
    found = []
    for index, event in enumerate(started):
        if event["name"] in LOOKS:
            continue
        arguments = event.get("arguments") or {}
        target = (
            arguments.get("path")
            or arguments.get("node_id")
            or arguments.get("name")
            or arguments.get("agent")
            or str(arguments.get("command") or "")[:120]
            or [
                Path(str(item.get("path") or "")).name
                for item in arguments.get("files") or []
                if isinstance(item, dict)
            ]
        )
        done = finished.get(index)
        refused = done is not None and str(done.get("result_preview") or "").startswith(REFUSED)
        reported = done.get("ok") if done is not None else None
        outcome = {"ok": False if refused else reported if isinstance(reported, bool) else None}
        if done is not None and outcome["ok"] is False:
            outcome["error"] = str(done.get("result_preview") or "")[:300]
        found.append({"action": event["name"], "target": target, **outcome})
    return found
