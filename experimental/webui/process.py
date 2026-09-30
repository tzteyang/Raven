"""A playbook node's process for the web view, read-only: the steps its sub-agent took, in order.

Three places hold a node's work. Once the node has finished, the record's agent home keeps its provider-shaped
transcript, prompt and output beside the conversation (``subagents/nodes/<node>.*``). While an external sub-harness
runs, only its ACP frame journal under the run's state root grows (``traces/logs/acp-frames``). While an in-process
node runs, the worker log's ``provider.request`` rows carry its conversation so far. Nothing outside the record's
agent home, its worker logs and the frame journals is opened, and every string this module returns passes `redact`.
"""

import json
import mmap
import re
import threading
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path

from ..automation.employee import AREA, HOME

NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,199}")
SECRETS = (
    re.compile(r"sk-[A-Za-z0-9-]{20,}"),
    re.compile(r"jina_[A-Za-z0-9_]{20,}"),
    re.compile(r"(?<![0-9A-Za-z])[0-9A-Fa-f]{40}(?![0-9A-Za-z])"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}"),
)
REDACTED = "<redacted>"

FINISHED = {"completed", "failed", "exception", "cancelled", "canceled", "skipped", "timeout", "error", "stopped"}
KEEP = {"thought": 4_000, "message": 12_000, "input": 6_000, "stderr": 4_000, "plan": 4_000, "error": 4_000}
RESULT_KEEP = 1_200
INPUT_KEEP = 1_500
PROMPT_KEEP = 60_000
OUTPUT_KEEP = 120_000
STEP_LIMIT = 400
CHUNK = 4_000_000
# A node whose journal has no call row yet is matched by the journal's name: the connection opens within seconds of
# the node starting, and a slow handshake has been measured at about fifteen.
NAME_WINDOW = (-5_000, 180_000)

_guard = threading.Lock()
_journals: "OrderedDict[Path, _Journal]" = OrderedDict()
_logs: "OrderedDict[Path, _Log]" = OrderedDict()
_dag_logs: dict[tuple[Path, str], Path] = {}
_sessions: dict[tuple[Path, str], Path] = {}
_contains_seen: dict[tuple[Path, int, bytes], bool] = {}


def redact(value):
    """`value` with anything shaped like an API key or a bare 40-hex token replaced, at any depth."""
    if isinstance(value, str):
        for pattern in SECRETS:
            value = pattern.sub(REDACTED, value)
        return value
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items()}
    return value


def safe_name(text: str) -> bool:
    """Whether `text` can name a file part: letters, digits, dot, dash and underscore, never a path or `..`."""
    return bool(text) and NAME.fullmatch(text) is not None and ".." not in text


def _within(path: Path, base: Path) -> bool:
    try:
        return path.resolve().is_relative_to(base.resolve())
    except OSError:
        return False


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + "..."


def _ms(stamp) -> int | None:
    """Epoch milliseconds of a naive ISO timestamp, read in this machine's zone as its writer on this machine did."""
    if not isinstance(stamp, str) or not stamp:
        return None
    try:
        moment = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    return int(moment.timestamp() * 1000)


def _read_text(path: Path, limit: int) -> tuple[str | None, int]:
    """A text file's content cut to `limit` characters, and its full length; None when it is absent."""
    if not path.is_file():
        return None, 0
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None, 0
    return _cut(text, limit), len(text)


def _complete_lines(file: Path, start: int, end: int):
    """Each complete line between two byte offsets, with where it starts and where the next one does."""
    with file.open("rb") as stream:
        stream.seek(start)
        carry = b""
        position = start
        while position < end:
            block = stream.read(min(CHUNK, end - position))
            if not block:
                break
            position += len(block)
            data = carry + block
            cut = data.rfind(b"\n")
            if cut < 0:
                carry = data
                continue
            offset = position - len(data)
            for line in data[:cut].split(b"\n"):
                yield line, offset, offset + len(line) + 1
                offset += len(line) + 1
            carry = data[cut + 1 :]


def _contains(path: Path, needles: list[bytes]) -> bool:
    """Whether a file holds any of `needles`; a finished file's answer is remembered by its size."""
    try:
        size = path.stat().st_size
    except OSError:
        return False
    if size == 0:
        return False
    key = (path, size, b"|".join(needles))
    if key in _contains_seen:
        return _contains_seen[key]
    try:
        with path.open("rb") as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as view:
            found = any(view.find(needle) >= 0 for needle in needles)
    except (OSError, ValueError):
        return False
    if len(_contains_seen) > 5000:
        _contains_seen.clear()
    _contains_seen[key] = found
    return found


def _plain(content) -> str:
    """Message content as text: a string, or the text parts of a content list."""
    if isinstance(content, list):
        return "\n".join(
            str(part.get("text", ""))
            for part in content
            if isinstance(part, dict) and part.get("type", "text") == "text"
        )
    return content if isinstance(content, str) else "" if content is None else json.dumps(content, ensure_ascii=False)


_UNTRUSTED_HEAD = re.compile(r"^\[BEGIN UNTRUSTED[^\]]*\]\n?")
_UNTRUSTED_TAIL = re.compile(r"\n?\[END UNTRUSTED[^\]]*\]\s*$")


def _unwrap(text: str) -> str:
    """A tool result without the untrusted-data fence Raven wraps it in."""
    return _UNTRUSTED_TAIL.sub("", _UNTRUSTED_HEAD.sub("", text.lstrip()))


_TITLE_KEYS = ("query", "queries", "url", "path", "file_path", "command", "pattern", "skill_id", "name", "project")


def _arguments(raw):
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except ValueError:
            return raw
    return raw


def _title(name: str, arguments) -> str:
    """A tool call as one line: its name and its most telling argument, the way an ACP agent titles it."""
    if isinstance(arguments, dict):
        for key in _TITLE_KEYS:
            value = arguments.get(key)
            if isinstance(value, list) and value and isinstance(value[0], str):
                value = ", ".join(value)
            if isinstance(value, str) and value.strip():
                return _cut(f"{name}: {' '.join(value.split())}", 160)
    return name


def _short(arguments) -> str:
    """Arguments as key=value pairs on one line."""
    if isinstance(arguments, dict):
        line = ", ".join(
            f"{key}={value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)}"
            for key, value in arguments.items()
        )
    elif arguments in (None, ""):
        line = ""
    else:
        line = arguments if isinstance(arguments, str) else json.dumps(arguments, ensure_ascii=False)
    return _cut(" ".join(line.split()), 240)


def _dump(arguments) -> str:
    if arguments in (None, ""):
        return ""
    text = arguments if isinstance(arguments, str) else json.dumps(arguments, ensure_ascii=False, indent=2)
    return _cut(text, INPUT_KEEP)


_LEVEL = {"info": 0, "warning": 1, "error": 2}


def _level(line: str) -> str:
    if re.search(r"\b(ERROR|CRITICAL|Traceback|Exception)\b", line):
        return "error"
    return "warning" if "WARNING" in line else "info"


class _Steps:
    """One run's steps in order; thoughts and messages that stream in chunks merge into one step."""

    def __init__(self):
        self.steps: list[dict] = []
        self.tools: dict[str, dict] = {}
        self.prompt: str | None = None
        self.stop: str | None = None
        self.title: str | None = None
        self.started: int | None = None

    def add(self, step: dict) -> dict:
        self.steps.append(step)
        return step

    def text(self, kind: str, text: str, time: int | None, merge: bool = True) -> None:
        if not text:
            return
        last = self.steps[-1] if self.steps else None
        keep = KEEP.get(kind, 6_000)
        if merge and last is not None and last["kind"] == kind:
            last["length"] += len(text)
            if len(last["text"]) < keep:
                last["text"] += text
            return
        self.add({"kind": kind, "time": time, "text": text[:keep], "length": len(text)})

    def stderr(self, line: str, time: int | None) -> None:
        if not line:
            return
        last = self.steps[-1] if self.steps else None
        level = _level(line)
        if last is not None and last["kind"] == "stderr":
            last["length"] += len(line) + 1
            if len(last["text"]) < KEEP["stderr"]:
                last["text"] += "\n" + line
            if _LEVEL[level] > _LEVEL[last["level"]]:
                last["level"] = level
            return
        self.add({"kind": "stderr", "time": time, "text": line, "length": len(line), "level": level})

    def tool(self, call: str, name: str, title: str, kind, arguments, time: int | None, status: str) -> dict:
        step = {
            "kind": "tool",
            "id": call,
            "name": name,
            "title": title or name,
            "tool_kind": kind,
            "args": _short(arguments),
            "input": _dump(arguments),
            "status": status,
            "result": "",
            "time": time,
            "ended": None,
        }
        self.add(step)
        if call:
            self.tools[call] = step
        return step

    def finish_tool(self, call: str, status: str | None, result: str, time: int | None, name: str = "") -> None:
        step = self.tools.get(call)
        if step is None:
            step = self.tool(call, name or "tool", name or "tool", None, None, time, "running")
        if status:
            step["status"] = status
        if result:
            step["result"] = _cut(result, RESULT_KEEP)
            step["result_length"] = len(result)
        if status in ("completed", "failed"):
            step["ended"] = time

    def settle(self) -> None:
        """Mark tool calls that never got a result, once the run is known to be over."""
        for step in self.steps:
            if step["kind"] == "tool" and step["status"] in ("running", "pending"):
                step["status"] = "no result"


_ACP_STATUS = {"in_progress": "running", "pending": "pending", "completed": "completed", "failed": "failed"}


def _content_text(content) -> str:
    """The text of an ACP tool call's content blocks; a diff reads as the path it touched."""
    if isinstance(content, dict):
        content = [content]
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "diff":
            parts.append(f"diff {block.get('path', '')}")
            continue
        inner = block.get("content") if isinstance(block.get("content"), dict) else block
        if isinstance(inner.get("text"), str):
            parts.append(inner["text"])
    return "\n".join(parts)


class _Journal:
    """Steps per task parsed from one ACP frame journal, extended as the file grows.

    A connection can answer several calls; each `acp_call` row opens the steps of the task it names, and the
    connection's own handshake and stderr before the first call belong to the first task.
    """

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        self._reset()

    def _reset(self) -> None:
        self.offset = 0
        self.preamble = _Steps()
        self.segments: dict[str, _Steps] = {}
        self.current: _Steps | None = None
        self.pending: dict = {}
        self.first: str | None = None

    def refresh(self) -> None:
        size = self.path.stat().st_size
        if size < self.offset:
            self._reset()
        for line, _, end in _complete_lines(self.path, self.offset, size):
            self.offset = end
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                self._take(row)

    def steps_for(self, task: str | None) -> _Steps | None:
        if task and task in self.segments:
            return self.segments[task]
        if not self.segments:
            return self.preamble
        return None

    def _take(self, row: dict) -> None:
        time = _ms(row.get("timestamp"))
        if row.get("_type") == "acp_call":
            task = str(row.get("task_id") or row.get("instance") or "")
            steps = _Steps()
            steps.started = time
            if self.first is None:
                self.first = task
                steps.steps = [dict(step) for step in self.preamble.steps]
            self.segments[task] = steps
            self.current = steps
            return
        target = self.current or self.preamble
        direction = row.get("dir")
        if direction == "err":
            target.stderr(str(row.get("text") or "").rstrip(), time)
            return
        frame = row.get("frame") if isinstance(row.get("frame"), dict) else {}
        method = frame.get("method")
        params = frame.get("params") if isinstance(frame.get("params"), dict) else {}
        if direction == "in" and method == "session/update":
            self._update(target, params.get("update") if isinstance(params.get("update"), dict) else {}, time)
        elif direction == "in" and method == "session/request_permission":
            call = params.get("toolCall") if isinstance(params.get("toolCall"), dict) else {}
            step = target.add(
                {"kind": "permission", "time": time, "text": str(call.get("title") or ""), "status": "asked"}
            )
            self.pending[frame.get("id")] = step
        elif direction == "in" and method == "elicitation/create":
            step = target.add(
                {"kind": "question", "time": time, "text": str(params.get("message") or ""), "status": "asked"}
            )
            self.pending[frame.get("id")] = step
        elif direction == "out" and method == "session/prompt":
            target.prompt = _plain(params.get("prompt"))
        elif direction == "out" and method is None and frame.get("id") in self.pending:
            result = frame.get("result") if isinstance(frame.get("result"), dict) else {}
            outcome = result.get("outcome") if isinstance(result.get("outcome"), dict) else {}
            self.pending.pop(frame.get("id"))["status"] = str(
                result.get("action") or outcome.get("outcome") or "answered"
            )
        elif direction == "in" and method is None and isinstance(frame.get("error"), dict):
            error = frame["error"]
            target.add({"kind": "error", "time": time, "text": _cut(str(error.get("message") or error), 4000)})
        elif direction == "in" and method is None and isinstance(frame.get("result"), dict):
            if "stopReason" in frame["result"]:
                target.stop = str(frame["result"]["stopReason"])

    @staticmethod
    def _update(target: _Steps, update: dict, time: int | None) -> None:
        kind = update.get("sessionUpdate")
        if kind == "agent_thought_chunk":
            target.text("thought", _content_text(update.get("content")), time)
        elif kind == "agent_message_chunk":
            target.text("message", _content_text(update.get("content")), time)
        elif kind == "user_message_chunk":
            target.text("input", _content_text(update.get("content")), time)
        elif kind == "tool_call":
            meta = update.get("_meta") if isinstance(update.get("_meta"), dict) else {}
            title = str(update.get("title") or "")
            name = str(meta.get("raven.toolName") or title.split(":")[0] or "tool")
            target.tool(
                str(update.get("toolCallId") or ""),
                name,
                title,
                update.get("kind"),
                update.get("rawInput"),
                time,
                _ACP_STATUS.get(str(update.get("status")), str(update.get("status") or "pending")),
            )
        elif kind == "tool_call_update":
            status = update.get("status")
            target.finish_tool(
                str(update.get("toolCallId") or ""),
                _ACP_STATUS.get(str(status), str(status)) if status else None,
                _content_text(update.get("content")),
                time,
            )
        elif kind == "plan":
            entries = update.get("entries") if isinstance(update.get("entries"), list) else []
            lines = [
                f"[{entry.get('status', '')}] {entry.get('content', '')}"
                for entry in entries
                if isinstance(entry, dict)
            ]
            if lines:
                target.add({"kind": "plan", "time": time, "text": "\n".join(lines), "length": len(lines)})
        elif kind == "session_info_update" and update.get("title"):
            target.title = str(update["title"])


# An ACP sub-harness's transcript marks a tool call that did not complete by its status in brackets.
_MARKED = re.compile(r"^\[(failed|error|cancelled)\]")


def _messages_steps(messages: list, prompt: str | None = None) -> _Steps:
    """Steps from provider-shaped messages: assistant rows with reasoning, content and tool calls, tool rows after."""
    steps = _Steps()
    for row in messages:
        if not isinstance(row, dict):
            continue
        role, time = row.get("role"), _ms(row.get("timestamp"))
        if role == "assistant":
            reasoning = row.get("reasoning_content")
            if not reasoning and isinstance(row.get("thinking_blocks"), list):
                reasoning = "\n".join(
                    str(block.get("thinking", "")) for block in row["thinking_blocks"] if isinstance(block, dict)
                )
            if isinstance(reasoning, str) and reasoning.strip():
                steps.text("thought", reasoning, time, merge=False)
            content = _plain(row.get("content"))
            if content.strip():
                steps.text("message", content, time, merge=False)
            for call in row.get("tool_calls") or []:
                if not isinstance(call, dict):
                    continue
                function = call.get("function") if isinstance(call.get("function"), dict) else call
                name = str(function.get("name") or "tool")
                arguments = _arguments(function.get("arguments"))
                steps.tool(str(call.get("id") or ""), name, _title(name, arguments), None, arguments, time, "running")
        elif role == "tool":
            text = _unwrap(_plain(row.get("content")))
            marked = _MARKED.match(text)
            status = marked.group(1) if marked else "failed" if text.startswith("Error") else "completed"
            steps.finish_tool(
                str(row.get("tool_call_id") or ""),
                "failed" if status == "error" else status,
                text,
                time,
                str(row.get("name") or ""),
            )
        elif role == "user":
            text = _plain(row.get("content"))
            if text.strip() and text.strip() != (prompt or "").strip():
                steps.text("input", text, time, merge=False)
    return steps


def _transcript(path: Path, prompt: str | None) -> _Steps | None:
    if not path.is_file():
        return None
    rows = []
    try:
        with path.open("rb") as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
    except OSError:
        return None
    return _messages_steps(rows, prompt)


def _prompt_key(text: str) -> str:
    return " ".join(text.split())[:400]


def _judged_task(text: str) -> str:
    """The task a sub-agent judge was shown, from inside its untrusted fence."""
    head = text.find("[BEGIN UNTRUSTED")
    if head < 0:
        return ""
    start = text.find("]", head)
    end = text.find("[END UNTRUSTED", start)
    return text[start + 1 : end if end >= 0 else None].strip()


class _Log:
    """What one worker log says about playbook runs: node progress, in-process node calls and judge verdicts."""

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        self._reset()

    def _reset(self) -> None:
        self.offset = 0
        self.dags: dict[str, dict] = {}
        self.requests: dict[str, list[tuple[int, list[dict], int]]] = {}
        self.judges: list[tuple[int, str]] = []
        self.verdicts: list[tuple[int, dict]] = []

    def refresh(self) -> None:
        size = self.path.stat().st_size
        if size < self.offset:
            self._reset()
        for line, begin, end in _complete_lines(self.path, self.offset, size):
            self.offset = end
            if b'"dag.progress"' in line:
                self._dag(line, begin)
            elif b'"provider.request"' in line and (b"# Subagent" in line or b"You decide whether a sub-agent" in line):
                self._request(line, begin)
            elif b'"provider.response"' in line and b"report_verdict" in line:
                self._verdict(line, begin)

    @staticmethod
    def _row(line: bytes) -> dict:
        try:
            row = json.loads(line)
        except ValueError:
            return {}
        return row if isinstance(row, dict) else {}

    def _dag(self, line: bytes, begin: int) -> None:
        row = self._row(line)
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        run = str(payload.get("run_id") or "")
        if row.get("kind") != "dag.progress" or not run:
            return
        dag = self.dags.setdefault(run, {"start": begin, "end": None, "nodes": {}, "summary": None})
        name = row.get("name")
        if name == "dag_run_started":
            dag["start"] = begin
            dag["summary"] = payload.get("task_summary")
            for spec in payload.get("nodes") or []:
                if isinstance(spec, dict) and spec.get("id"):
                    node = dag["nodes"].setdefault(str(spec["id"]), {})
                    node.update(subagent=spec.get("subagent"), summary=spec.get("node_summary"))
        elif name == "dag_node_updated" and payload.get("node"):
            node = dag["nodes"].setdefault(str(payload["node"]), {})
            for key in ("status", "started_at", "ended_at"):
                if payload.get(key) is not None:
                    node[key] = payload[key]
        elif name == "dag_run_completed":
            dag["end"] = begin
            manifest = payload.get("manifest") if isinstance(payload.get("manifest"), dict) else {}
            for entry in manifest.get("files") or []:
                if isinstance(entry, dict) and entry.get("node"):
                    node = dag["nodes"].setdefault(str(entry["node"]), {})
                    for key in ("status", "started_at", "ended_at", "error", "subagent"):
                        if entry.get(key) is not None:
                            node[key] = entry[key]

    def _request(self, line: bytes, begin: int) -> None:
        row = self._row(line)
        messages = (row.get("parameters") or {}).get("messages") if isinstance(row.get("parameters"), dict) else None
        if row.get("kind") != "provider.request" or not isinstance(messages, list) or len(messages) < 2:
            return
        system = _plain(messages[0].get("content")) if isinstance(messages[0], dict) else ""
        task = _plain(messages[1].get("content")) if isinstance(messages[1], dict) else ""
        if system.startswith("You decide whether a sub-agent"):
            self.judges.append((begin, _prompt_key(_judged_task(task))))
        elif system.startswith("# Subagent"):
            key = _prompt_key(task)
            steps = _messages_steps(messages[2:])
            entries = self.requests.setdefault(key, [])
            entries.append((begin, steps.steps, len(messages)))
            del entries[:-3]

    def _verdict(self, line: bytes, begin: int) -> None:
        row = self._row(line)
        response = row.get("response") if isinstance(row.get("response"), dict) else {}
        for call in response.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            function = call.get("function") if isinstance(call.get("function"), dict) else call
            if function.get("name") != "report_verdict":
                continue
            arguments = _arguments(function.get("arguments"))
            outcome = arguments.get("outcome") if isinstance(arguments, dict) else None
            reason = _plain(response.get("content")) or str(response.get("reasoning_content") or "")
            self.verdicts.append((begin, {"outcome": str(outcome or "unknown"), "reason": _cut(reason, 4000)}))
            return

    def pairs(self) -> list[tuple[int, str, dict]]:
        """Each judge call with the verdict that answered it: the first unclaimed verdict logged after it."""
        events = sorted([(at, 0, key) for at, key in self.judges] + [(at, 1, v) for at, v in self.verdicts])
        waiting: list[tuple[int, str]] = []
        paired = []
        for at, kind, value in events:
            if kind == 0:
                waiting.append((at, value))
            elif waiting:
                judge_at, key = waiting.pop(0)
                paired.append((judge_at, key, value))
        return paired


def _cached(cache: OrderedDict, path: Path, make, size: int):
    with _guard:
        item = cache.get(path)
        if item is None:
            item = make(path)
            cache[path] = item
        cache.move_to_end(path)
        while len(cache) > size:
            cache.popitem(last=False)
    return item


def _journal(path: Path) -> _Journal:
    journal = _cached(_journals, path, _Journal, 24)
    with journal.lock:
        journal.refresh()
    return journal


def _log(path: Path) -> _Log:
    log = _cached(_logs, path, _Log, 8)
    with log.lock:
        log.refresh()
    return log


def session_dir(worker_root: Path, dag: str) -> Path | None:
    """The `subagents` folder of the conversation whose playbook run `dag` is, inside the record's agent home."""
    key = (worker_root, dag)
    if key in _sessions:
        return _sessions[key]
    home = worker_root / AREA / HOME
    for graph in sorted((home / "sessions").glob(f"*/*/subagents/mas_dag/{dag}/graph.json")):
        folder = graph.parent.parent.parent
        if _within(graph, home) and _within(folder, home):
            _sessions[key] = folder
            return folder
    return None


def dag_log(worker_root: Path, dag: str) -> Path | None:
    """The worker log that recorded playbook run `dag`, newest logs searched first."""
    key = (worker_root, dag)
    if key in _dag_logs and _dag_logs[key].is_file():
        return _dag_logs[key]
    logs = sorted(worker_root.glob(f"{AREA}/*/observations.jsonl"), key=lambda path: path.stat().st_mtime, reverse=True)
    # The id as a JSON key's value, so a later log that only quotes it inside a string does not match.
    needles = [f'"run_id": "{dag}"'.encode(), f'"run_id":"{dag}"'.encode()]
    for path in logs:
        if _within(path, worker_root) and _contains(path, needles):
            _dag_logs[key] = path
            return path
    return None


def state_root(state_roots, name: str) -> Path | None:
    """The run's state root: `<dir>/<run name>` under the first configured directory that has one."""
    for base in state_roots or ():
        candidate = Path(base) / name
        if safe_name(name) and candidate.is_dir() and _within(candidate, Path(base)):
            return candidate
    return None


def _name_times(path: Path) -> list[int]:
    """The journal's opening instant from its folder and file name, read both as local time and as UTC."""
    stamp = path.stem.rsplit("-", 1)[-1]
    try:
        naive = datetime.strptime(f"{path.parent.name} {stamp}", "%Y-%m-%d %H%M%S%f")
    except ValueError:
        return []
    return [int(naive.timestamp() * 1000), int(naive.replace(tzinfo=timezone.utc).timestamp() * 1000)]


def journal_path(state: Path | None, subagent: str, node: str, started: int | None, pointer=None) -> Path | None:
    """The frame journal a node's sub-harness wrote: the one whose call row names the node, else by name and time."""
    if state is None or not safe_name(subagent):
        return None
    frames = state / "traces" / "logs" / "acp-frames"
    if not frames.is_dir() or not _within(frames, state):
        return None
    if isinstance(pointer, str) and pointer:
        candidate = Path(pointer)
        if candidate.suffix == ".jsonl" and candidate.is_file() and _within(candidate, frames):
            return candidate.resolve()
    candidates = [path for path in frames.glob(f"*/{subagent}-*.jsonl") if path.is_file() and _within(path, frames)]
    needles = [f'"task_id": "{node}"'.encode(), f'"task_id":"{node}"'.encode()]
    hits = [path for path in candidates if _contains(path, needles)]
    if hits:
        return max(hits, key=lambda path: path.stat().st_mtime)
    if started is None:
        return None
    best, distance = None, None
    for path in candidates:
        if _contains(path, [b'"acp_call"']):
            continue
        for moment in _name_times(path):
            gap = moment - started
            if NAME_WINDOW[0] <= gap <= NAME_WINDOW[1] and (distance is None or abs(gap) < distance):
                best, distance = path, abs(gap)
    return best


def _counts(steps: list[dict]) -> dict:
    tools = [step for step in steps if step["kind"] == "tool"]
    thoughts = [step for step in steps if step["kind"] == "thought"]
    return {
        "tools": len(tools),
        "failed": sum(step["status"] == "failed" for step in tools),
        "running": sum(step["status"] in ("running", "pending") for step in tools),
        "messages": sum(step["kind"] == "message" for step in steps),
        "thoughts": len(thoughts),
        "thought_chars": sum(step.get("length", 0) for step in thoughts),
        "errors": sum(step["kind"] == "error" or step.get("level") == "error" for step in steps),
    }


def _last(steps: list[dict]) -> str | None:
    for step in reversed(steps):
        if step["kind"] == "tool":
            return step["title"]
        if step["kind"] == "message":
            line = step["text"].strip().splitlines()
            return _cut(line[0], 160) if line else None
    return None


def _attempts(nodes: Path, node: str) -> list[int]:
    found = set()
    for path in nodes.glob(f"{node}.attempt-*"):
        match = re.fullmatch(re.escape(node) + r"\.attempt-(\d+)\..+", path.name)
        if match:
            found.add(int(match.group(1)))
    return sorted(found)


def node_process(
    worker_root: Path,
    state_roots,
    dag: str,
    node: str,
    *,
    attempt: int | None = None,
    source: str = "auto",
    summary: bool = False,
) -> dict | None:
    """A node's process as ordered steps with its prompt, output and judge verdicts; None when there is no such node.

    `source` picks one of `transcript`, `journal` or `provider` when it is available; `auto` prefers the record's
    transcript once the node has finished and the live source while it runs. `summary` leaves out the steps and
    texts, for a caller that only draws a node's running tally.
    """
    if not safe_name(dag) or not safe_name(node):
        return None
    worker_root = Path(worker_root).resolve()
    folder = session_dir(worker_root, dag)
    if folder is None:
        return None
    graph_file = folder / "mas_dag" / dag / "graph.json"
    try:
        graph = json.loads(graph_file.read_text())
    except (OSError, ValueError):
        graph = {}
    spec = next((row for row in graph.get("nodes") or [] if isinstance(row, dict) and str(row.get("id")) == node), None)
    try:
        manifest = json.loads((folder / "mas_dag" / dag / "manifest.json").read_text())
    except (OSError, ValueError):
        manifest = {}
    entry = manifest.get(node) if isinstance(manifest.get(node), dict) else {}
    log_path = dag_log(worker_root, dag)
    log = _log(log_path) if log_path is not None else None
    logged = ((log.dags.get(dag) or {}).get("nodes") or {}).get(node, {}) if log else {}
    if spec is None and not entry and not logged:
        return None
    spec = spec or {}
    subagent = str(entry.get("subagent") or logged.get("subagent") or spec.get("subagent") or "")

    nodes = folder / "nodes"
    attempts = _attempts(nodes, node) if nodes.is_dir() else []
    stem = f"{node}.attempt-{attempt}" if attempt is not None and attempt in attempts else node
    prompt, prompt_length = _read_text(nodes / f"{stem}.prompt.md", PROMPT_KEEP)
    output, output_length = _read_text(nodes / f"{stem}.out.md", OUTPUT_KEEP)
    transcript_file = nodes / f"{stem}.transcript.jsonl"

    status = str(entry.get("status") or logged.get("status") or "")
    if not status:
        status = "completed" if output is not None else "running" if prompt is not None else "pending"
    started = entry.get("started_at") or logged.get("started_at")
    ended = entry.get("ended_at") or logged.get("ended_at")
    finished = status in FINISHED

    frames = entry.get("acp_frames") if isinstance(entry.get("acp_frames"), dict) else {}
    state = state_root(state_roots, worker_root.name)
    journal_file = journal_path(state, subagent, node, started, frames.get("path")) if subagent else None
    journal = _journal(journal_file) if journal_file is not None else None
    live = journal.steps_for(node) if journal is not None else None

    window = log.dags.get(dag) if log else None
    key = _prompt_key(prompt or (live.prompt if live else None) or str(spec.get("prompt_template") or ""))
    provider = None
    if log is not None and window is not None and key:
        within = [
            item
            for item in log.requests.get(key, [])
            if item[0] >= window["start"] and (window["end"] is None or item[0] <= window["end"])
        ]
        provider = within[-1] if within else None

    available = {
        "transcript": transcript_file.is_file(),
        "journal": live is not None,
        "provider": provider is not None,
    }
    if source not in available or not available[source]:
        if finished and available["transcript"]:
            source = "transcript"
        elif available["journal"]:
            source = "journal"
        elif available["provider"]:
            source = "provider"
        elif available["transcript"]:
            source = "transcript"
        else:
            source = "none"

    steps: list[dict] = []
    stop = None
    if source == "transcript":
        built = _transcript(transcript_file, prompt)
        if built is not None:
            if finished:
                built.settle()
            steps = built.steps
    elif source == "journal" and live is not None:
        steps = [dict(step) for step in live.steps]
        stop = live.stop
        if finished or stop:
            for step in steps:
                if step["kind"] == "tool" and step["status"] in ("running", "pending"):
                    step["status"] = "no result"
    elif source == "provider" and provider is not None:
        steps = [dict(step) for step in provider[1]]

    prompt_from = "prompt file" if prompt is not None else None
    if prompt is None and live is not None and live.prompt:
        prompt, prompt_length, prompt_from = _cut(live.prompt, PROMPT_KEEP), len(live.prompt), "frame journal"
    if prompt is None and spec.get("prompt_template"):
        template = str(spec["prompt_template"])
        prompt, prompt_length, prompt_from = _cut(template, PROMPT_KEEP), len(template), "graph template"

    verdicts = []
    if log is not None and window is not None and key:
        for judge_at, judged, verdict in log.pairs():
            if judged == key and judge_at >= window["start"] and (window["end"] is None or judge_at <= window["end"]):
                verdicts.append(verdict)

    omitted = max(0, len(steps) - STEP_LIMIT)
    times = [moment for step in steps for moment in (step.get("time"), step.get("ended")) if isinstance(moment, int)]
    reply = {
        "dag": dag,
        "node": node,
        "subagent": subagent or None,
        "summary": spec.get("node_summary") or logged.get("summary"),
        "status": status,
        "started_at": started,
        "ended_at": ended,
        "error": entry.get("error") or logged.get("error"),
        "lane": "acp" if journal_file is not None else "in-process" if provider is not None else None,
        "source": source,
        "available": available,
        "attempt": attempt if stem != node else None,
        "attempts": attempts,
        "title": live.title if live is not None else None,
        "stop_reason": stop,
        "counts": _counts(steps),
        "last": _last(steps),
        "last_at": max(times) if times else None,
        "omitted": omitted,
        "verdicts": verdicts,
        "prompt_source": prompt_from,
        "prompt_length": prompt_length,
        "output_length": output_length,
    }
    if not summary:
        reply.update(steps=steps[omitted:], prompt=prompt, output=output)
    return redact(reply)


SUBHARNESS_TEXT = {".md", ".markdown", ".txt", ".yaml", ".yml", ".toml"}
SUBHARNESS_SKIP_DIRS = {"sessions", "cache", "telemetry", "workspace", "oauth", "credentials", "traces"}
SUBHARNESS_SECRET = re.compile(r"(?i)(config|credential|secret|token|oauth|auth|\.env|password|\.key$|\.pem$)")
SUBHARNESS_KEEP = 64_000


def subharness_homes(worker_root: Path) -> list[dict]:
    """Each housed sub-harness home's current files in the record, with the text of its prose and config files.

    Sessions, hidden folders (the memory curator's traces, locks) and anything named like a config or a secret are
    left out, and only prose files carry their text.
    """
    housed = Path(worker_root) / AREA / HOME / "subagents"
    if not housed.is_dir() or not _within(housed, worker_root):
        return []
    homes = []
    for home in sorted(path for path in housed.iterdir() if path.is_dir() and safe_name(path.name)):
        files = []
        for path in sorted(home.rglob("*")):
            relative = path.relative_to(home)
            parts = relative.parts
            if (
                path.is_symlink()
                or not path.is_file()
                or parts[0] in SUBHARNESS_SKIP_DIRS
                or any(part.startswith(".") for part in parts)
                or SUBHARNESS_SECRET.search(path.name)
                or not _within(path, home)
            ):
                continue
            stat = path.stat()
            item = {"path": relative.as_posix(), "size": stat.st_size, "modified": stat.st_mtime}
            if path.suffix.lower() in SUBHARNESS_TEXT and stat.st_size <= 4 * SUBHARNESS_KEEP:
                text, length = _read_text(path, SUBHARNESS_KEEP)
                item.update(text=text, truncated=length > SUBHARNESS_KEEP)
            files.append(item)
        homes.append({"name": home.name, "files": files})
    return redact(homes)
