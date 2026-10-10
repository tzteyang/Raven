"""Views of a worker's exchanges that every participant reads alike: the conversation as the other side saw it, the
files handed over, the calls the worker made besides looking around, and the reports its colleagues sent back."""

import re
from pathlib import Path

from experimental.harness.participation.allowance import excerpt, reading_budget
from experimental.harness.participation.channel import said
from experimental.harness.participation.files import read_delivered
from experimental.harness.raven_adapter.action.runtime import REFUSED

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
    started, finished = [], {}
    for row in records:
        event = row.get("event") or {}
        if row.get("kind") != "runner.event" or row.get("event_type", "ToolEvent") != "ToolEvent":
            continue
        if event.get("phase") == "start" and event.get("name") and event["name"] not in LOOKS:
            started.append(event)
        elif event.get("phase") == "complete" and event.get("tool_call_id"):
            finished[event["tool_call_id"]] = event
    found = []
    for event in started:
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
        done = finished.get(event.get("tool_call_id"))
        refused = done is not None and str(done.get("result_preview") or "").startswith(REFUSED)
        outcome = {"ok": None} if done is None else {"ok": done.get("ok") is not False and not refused}
        if done is not None and not outcome["ok"]:
            outcome["error"] = str(done.get("result_preview") or "")[:300]
        found.append({"action": event["name"], "target": target, **outcome})
    return found
