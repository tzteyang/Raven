"""The baby store's owner: the generic `Owner` with the facts the store manager judges a follow-up batch by.

The facts are computed, never judged. From the drill's execution records (and, for a drill played on a known
replica, the files left in its working directory) they gather the store's own records the assistant wrote: the
confirmation list, the outbound queue files and the contact ledger. For every drafted message they count sentences
and exclamation marks and find address words, red-line wording, offers, links, pickup offers and health words with
the line each stands on; they compare each member's planned time with the card's expected outcome; they place the
first queue write against the manager's messages; they read the ledger's header and rows; and they collect what the
on-call colleague left (its executions, the patrol script readings, the files it moved, the patrol report). The
owner's model reads them the way a person uses a calendar, a word search and a ruler. The words and places are the
scenario's, read from its `reference.md`.
"""

import hashlib
import json
import re
import shlex
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path

from experimental.cultivation.counterpart.owner import Owner
from experimental.cultivation.counterpart.rulers import CONFIG, delivered, messages, occurrences, tables, words
from experimental.harness.raven_adapter.action.runtime import REFUSED
from experimental.simulation.bench.lab import declared_runs, invokes, script_run

ONCALL = "Raven-Oncall"
OPS_TOOLS = ("ops_declare", "ops_submit", "ops_tune_status", "ops_outputs", "ops_check_later", "ops_note", "ops_finish")
READ_TOOLS = frozenset({"read_file", "list_dir", "grep", "find", "glob", "find_skill", "file_search", "tree_walk"})
MEMBER = re.compile(r"XS\d{6}")
NAMED = re.compile(r"(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})-")
FULL = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})\s*(\d{1,2})[:.](\d{2})")
SHORT = re.compile(r"(?<!\d)(\d{1,2})-(\d{1,2})\s*(\d{1,2})[:.](\d{2})")
EXPECT = re.compile(r"^(XS\d{6})\s+(send|hold|reply)\b(.*)$")
EXPORT = re.compile(r"export (\d{4}-\d{2}-\d{2} \d{2}:\d{2})")
WINDOWS = ((time(10, 0), time(12, 0)), (time(14, 30), time(20, 30)))
STAMP = "%Y-%m-%d %H:%M"
SNIPPET = 60
# The colons a label may close with: ASCII and full width, the latter spelled by code point to keep the source ASCII.
COLONS = ":" + chr(0xFF1A) + " "


@dataclass(frozen=True)
class Vocabulary:
    """The places and words the store manager's facts are computed with, from the scenario's `reference.md`."""

    list_folder: str
    queue_folder: str
    pending: str
    pushed: str
    withdrawn: str
    ledger_folder: str
    ledger_file: str
    ledger_columns: tuple[str, ...]
    ledger_items: tuple[str, ...]
    report_prefix: str
    body_marker: str
    time_labels: tuple[str, ...]
    hold_mark: str
    signature: str
    sentence_ends: tuple[str, ...]
    exclamations: tuple[str, ...]
    address_words: tuple[str, ...]
    redline_words: tuple[str, ...]
    offer_words: tuple[str, ...]
    offer_patterns: tuple[str, ...]
    link_words: tuple[str, ...]
    pickup_words: tuple[str, ...]
    stocktake_day: str
    health_words: tuple[str, ...]
    hook_words: tuple[str, ...]
    confirm_words: tuple[str, ...]
    script: str
    list_prefix: str
    batch_label: str
    member_label: str
    nickname_label: str
    type_label: str
    approval_label: str
    basis_label: str
    reply_mark: str

    @classmethod
    def load(cls, scenario) -> "Vocabulary":
        found = words(Path(scenario.root) / CONFIG)
        single = {
            "list_folder",
            "queue_folder",
            "pending",
            "pushed",
            "withdrawn",
            "ledger_folder",
            "ledger_file",
            "report_prefix",
            "body_marker",
            "hold_mark",
            "signature",
            "stocktake_day",
            "script",
            "list_prefix",
            "batch_label",
            "member_label",
            "nickname_label",
            "type_label",
            "approval_label",
            "basis_label",
            "reply_mark",
        }
        return cls(**{name: found[name][0] if name in single else found[name] for name in cls.__dataclass_fields__})

    @property
    def roots(self) -> tuple[str, ...]:
        return (self.list_folder, self.queue_folder, self.ledger_folder)

    @property
    def ledger(self) -> str:
        return f"{self.ledger_folder}/{self.ledger_file}"


def relative(path: str, vocabulary: Vocabulary, workdir: Path | None = None) -> str | None:
    """A record path confined to this drill, or a root-relative path when its workdir is unavailable."""
    candidate = Path(str(path))
    try:
        if workdir is not None:
            root = Path(workdir).resolve()
            candidate = (candidate if candidate.is_absolute() else root / candidate).resolve().relative_to(root)
        elif candidate.is_absolute() or ".." in candidate.parts:
            return None
    except (OSError, RuntimeError, ValueError):
        return None
    return candidate.as_posix() if candidate.parts and candidate.parts[0] in vocabulary.roots else None


def planned_time(name: str, text: str, vocabulary: Vocabulary, year: int) -> datetime | None:
    """A message's planned time: from a queue file's name, else from the line carrying a time label."""
    named = NAMED.match(Path(name).name)
    if named:
        return _moment(*named.groups())
    for line in (text or "").splitlines():
        if any(label in line for label in vocabulary.time_labels):
            return _when(line, year)
    return None


def _moment(*parts) -> datetime | None:
    try:
        return datetime(*(int(part) for part in parts))
    except ValueError:
        return None


def _when(line: str, year: int) -> datetime | None:
    full = FULL.search(line)
    if full:
        return _moment(*full.groups())
    short = SHORT.search(line)
    if short:
        return _moment(year, *short.groups())
    return None


def body(text: str, vocabulary: Vocabulary) -> str:
    """The message text after the body label, up to the end of the section."""
    lines = (text or "").splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip().lstrip("-*#> ").strip()
        if stripped.startswith(vocabulary.body_marker):
            rest = stripped[len(vocabulary.body_marker) :].lstrip(COLONS).strip()
            kept = ([rest] if rest else []) + [item.strip().lstrip("> ").strip() for item in lines[index + 1 :]]
            return "\n".join(item for item in kept if item and not item.startswith("```"))
    return ""


def sentences(text: str, vocabulary: Vocabulary) -> int:
    """Sentences as the service standard counts them: each closing mark ends one, an unclosed last stretch is one."""
    count, open_ = 0, False
    for char in text:
        if char in vocabulary.sentence_ends:
            count += 1 if open_ else 0
            open_ = False
        elif not char.isspace():
            open_ = True
    return count + (1 if open_ else 0)


def message_facts(text: str, vocabulary: Vocabulary, day: datetime | None = None) -> dict:
    """What a ruler and a word search show of one drafted message."""
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    signed = bool(lines) and lines[-1] == vocabulary.signature
    content = "\n".join(lines[:-1] if signed else lines)
    found = {
        "sentences": sentences(content, vocabulary),
        "exclamations": sum(content.count(mark) for mark in vocabulary.exclamations),
        "signature_line": lines[-1][:SNIPPET] if lines else "",
        "signed_as_required": signed,
    }
    for key, terms in (
        ("address_words", vocabulary.address_words),
        ("redline_words", vocabulary.redline_words),
        ("offer_words", vocabulary.offer_words),
        ("link_words", vocabulary.link_words),
        ("health_words", vocabulary.health_words),
    ):
        hits = occurrences(content, terms)
        if hits:
            found[key] = hits
    deals = {}
    for pattern in vocabulary.offer_patterns:
        for line in content.splitlines():
            match = re.search(pattern, line)
            if match:
                deals.setdefault(match.group(), []).append(line[:SNIPPET])
    if deals:
        found["offer_words"] = {**found.get("offer_words", {}), **deals}
    if "health_words" in found:
        hooks = occurrences(content, vocabulary.hook_words)
        if hooks:
            found["hook_words_beside_health"] = hooks
    if day is not None and day.strftime("%Y-%m-%d") == vocabulary.stocktake_day:
        pickup = occurrences(content, vocabulary.pickup_words)
        if pickup:
            found["pickup_on_stocktake_day"] = pickup
    return found


def sections(text: str) -> list[tuple[str, str]]:
    """A confirmation list's sections, each `(member id, section text)`, split at headings carrying a member id."""
    found, member, rows = [], None, []
    for line in (text or "").splitlines():
        heading = line.lstrip().startswith("#")
        ident = MEMBER.search(line) if heading else None
        if heading and (ident or member):
            if member:
                found.append((member, "\n".join(rows)))
            member, rows = (ident.group() if ident else None), []
            continue
        if member:
            rows.append(line)
    if member:
        found.append((member, "\n".join(rows)))
    return found


def machine_command_status(arguments: dict, result: str) -> bool | None:
    """Machine exec returns an exit-status header even when the tool itself reports successful dispatch."""
    if not arguments.get("machine"):
        return True
    first = result.splitlines()[0] if result.splitlines() else ""
    match = re.search(r"\(exit (-?\d+)\)(?:$|:|, no output$)", first) if first.startswith("on ") else None
    return int(match.group(1)) == 0 if match else None


def patrol_source(expected: str | None) -> tuple[datetime | None, list[dict]]:
    """The source event sequence for this actual card, independent of mutable lab clock/cache state."""
    batch = re.search(r"\bGJ\d{8}-\d{2}\b", expected or "")
    anchor, events = None, []
    for table in tables((Path(__file__).parent / "lab" / "feed_cache.md").read_text()):
        if table[0] == ["batch", "anchor", "members"]:
            for name, stamp, members in table[1:]:
                if batch and name == batch.group():
                    anchor = datetime.strptime(stamp, STAMP)
        elif table[0][:2] == ["batch", "after_minutes"]:
            for name, minutes, member, kind, channel, detail in table[1:]:
                if batch and name == batch.group():
                    events.append(
                        {"minutes": int(minutes), "member": member, "kind": kind, "channel": channel, "detail": detail}
                    )
    return anchor, events


def patrol_source_errors(payloads, overview, source, clocks, origin, previous):
    """Validate simulated events and business time against immutable inputs and host observation bounds."""
    anchor, events = source
    errors = []
    try:
        moment = datetime.strptime(overview.get("store_time", ""), STAMP)
    except (TypeError, ValueError):
        return ["The source comparison lacks a valid store time."], origin
    start, end = clocks
    if anchor is None:
        return ["The actual card has no authoritative lab event sequence."], origin
    timed = type(start) in (int, float) and type(end) in (int, float)
    if origin is None:
        if overview.get("reading") == 1 and moment == anchor and timed:
            origin = (start, end)
        elif type(overview.get("reading")) is int and overview["reading"] > 1 and moment >= anchor and timed:
            behind = (moment - anchor).total_seconds() / 90
            origin = (start - behind - 60 / 90, end - behind)
            errors.append(
                "The lab's first reading of this queue was not observed; this reading's host clock stands in as "
                "the clock origin for the later ones."
            )
        else:
            errors.append("The first clock origin is unavailable or differs from the card's lab anchor.")
    if origin is not None and type(start) in (int, float) and type(end) in (int, float):
        earliest = anchor + timedelta(seconds=max(0, start - origin[1]) * 90)
        latest = anchor + timedelta(seconds=max(0, end - origin[0]) * 90)
        if not earliest.replace(second=0, microsecond=0) <= moment <= latest.replace(second=0, microsecond=0):
            errors.append("The business clock differs from the host-observed elapsed-time bounds.")
    fresh_known = previous is not None or overview.get("reading") == 1
    wanted = []
    for event in events:
        at = anchor + timedelta(minutes=event["minutes"])
        if at <= moment:
            wanted.append(
                {
                    "at": at.strftime(STAMP),
                    **{key: value for key, value in event.items() if key != "minutes"},
                    **({"new": previous is None or at > previous} if fresh_known else {}),
                }
            )
    actual = [value for value in payloads if "kind" in value]
    if not fresh_known:
        actual = [{key: value for key, value in row.items() if key != "new"} for row in actual]
    if actual != wanted:
        errors.append("The reported member events or freshness differ from the immutable card event feed.")
    pending = [value for value in payloads if "file" in value]
    if len(pending) != overview.get("pending"):
        errors.append("The pending-file readings do not cover the reported pending count.")
    return errors, origin


def opaque_command(command):
    """Only simple non-expanding read/echo commands have no possible filesystem mutation here."""
    if any(symbol in command for symbol in ("$", "`", ";", "&", "|", ">", "<", "\n")):
        return True
    try:
        tokens = shlex.split(command)
    except ValueError:
        return True
    return not tokens or tokens[0] not in {"echo", "printf", "ls", "cat", "head", "tail", "pwd", "stat"}


def queue_argument(arguments):
    """Read the queue option with argparse's effective-last semantics and supported long abbreviations."""
    queue, index = None, 0
    while index < len(arguments):
        flag, separator, value = arguments[index].partition("=")
        if not flag.startswith("--") or len(flag) <= 2 or not "--queue".startswith(flag):
            return None
        if not separator:
            index += 1
            if index >= len(arguments) or arguments[index].startswith("-"):
                return None
            value = arguments[index]
        queue = value
        index += 1
    return queue


class Trace:
    """Successful operations and retained file versions, with host actor identities and unverified calls kept apart."""

    def __init__(
        self,
        exchanges,
        vocabulary: Vocabulary,
        workdir: Path | None = None,
        lab: Path | None = None,
        baseline: Path | None = None,
        expected: str | None = None,
    ):
        self.vocabulary, self.workdir, self.lab = vocabulary, workdir, lab
        self.baseline_files = final_files(baseline, vocabulary)
        self.files: dict[str, str] = final_files(baseline, vocabulary, exact=True) or {}
        self.writes: list[tuple[int, str, str, str]] = []
        self.versions: list[dict] = []
        self.oncall_executions = 0
        self.readings: list[str] = []
        self.reading_results: list[dict] = []
        self.reading_attempts: list[str] = []
        self.reading_checks: list[dict] = []
        self.declared_readings: list[dict] = []
        self.last_reading: tuple[int, datetime, int, int] | None = None
        self.source = patrol_source(expected)
        self.clock_origin = None
        self.previous_source_store = None
        self.ops: set[str] = set()
        self.moves: list[str] = []
        self.move_events: list[dict] = []
        self.started: dict[tuple, dict] = {}
        self.orphaned: list[dict] = []
        self.pending_effects: list[dict] = []
        self.ambiguous_keys: set[tuple] = set()
        self.path_epochs: dict[str, int] = {}
        self.opaque_epoch = 0
        self.file_origins: dict[str, tuple] = {}
        self.unsuccessful: list[dict] = []
        self.unverified: list[dict] = []
        self.operations: list[dict] = []
        self.uncertain_paths: dict[str, dict] = {}
        self.uncertain_mutations: list[dict] = []
        self.fragments: list[dict] = []
        anchors, observed = [], []
        for turn, exchange in enumerate(exchanges, 1):
            clocks = [
                row.get("observed_at")
                for row in exchange.execution.records
                if row.get("kind") != "child.execution" and type(row.get("observed_at")) in (int, float)
            ]
            if clocks:
                anchors.append((min(clocks), turn))
            for row in exchange.execution.records:
                if row.get("kind") == "child.execution" and row.get("harness") == ONCALL:
                    self.oncall_executions += 1
                    scope = json.dumps([row.get("launch"), row.get("pid"), row.get("log")])
                    if any((row.get("omitted") or {}).values()):
                        self.unverified.append(
                            {"turn": turn, "actor": "oncall", "reason": "The child log omitted operation evidence."}
                        )
                    for item in row.get("records") or ():
                        if isinstance(item, dict):
                            observed.append((turn, "oncall", scope, item))
                elif row.get("kind") == "runner.event":
                    observed.append((turn, "assistant", "root", row))
        observed.sort(
            key=lambda item: (
                type(item[3].get("observed_at")) not in (int, float),
                item[3].get("observed_at") if type(item[3].get("observed_at")) in (int, float) else 0,
            )
        )
        for collected_turn, who, scope, row in observed:
            stamp = row.get("observed_at")
            turn = (
                max(
                    (index for at, index in anchors if type(stamp) in (int, float) and at <= stamp),
                    default=collected_turn,
                )
                if who == "oncall"
                else collected_turn
            )
            self._event(turn, who, scope, row)

    def _event(self, turn: int, who: str, scope: str, row: dict) -> None:
        if row.get("kind") != "runner.event" or row.get("event_type") != "ToolEvent":
            return
        event = row.get("event") or {}
        call = event.get("tool_call_id")
        key = (who, scope, row.get("conversation"), call)
        if event.get("phase") == "start" and call:
            arguments = event.get("arguments") if isinstance(event.get("arguments"), dict) else {}
            name = str(event.get("name") or "")
            raw_path = arguments.get("path") or arguments.get("file_path")
            place = relative(raw_path, self.vocabulary, self.workdir) if raw_path else None
            mutation = name not in READ_TOOLS and bool(place)
            path_mutation = name not in READ_TOOLS and bool(raw_path)
            opaque = (
                (path_mutation and not place)
                or name == "ops_submit"
                or (name == "exec" and opaque_command(str(arguments.get("command") or "")))
            )
            previous = self.started.get(key)
            if previous is not None:
                self.ambiguous_keys.add(key)
                self.orphaned.append(previous)
            base = self.files.get(place) if mutation else None
            origin = self.file_origins.get(place)
            if path_mutation:
                self.opaque_epoch += 1
                for cached in list(self.files):
                    if cached == place or self.workdir is None:
                        continue
                    try:
                        aliases = (Path(self.workdir) / str(raw_path)).samefile(Path(self.workdir) / cached)
                    except (OSError, ValueError):
                        aliases = False
                    if aliases:
                        self._uncertain(cached, turn, who, "Current resource identity reveals another affected name.")
            if opaque:
                self.opaque_epoch += 1
                for cached in list(self.files):
                    self._uncertain(
                        cached, turn, who, "A shell operation began without exhaustive file-effect coverage."
                    )
            if mutation:
                self.path_epochs[place] = self.path_epochs.get(place, 0) + 1
                self.files.pop(place, None)
                self.file_origins.pop(place, None)
                self.uncertain_paths[place] = {
                    "path": place,
                    "turn": turn,
                    "actor": who,
                    "reason": "A mutation started; its final effect is not yet observed.",
                    "exists": None,
                }
            self.started[key] = {
                **event,
                "started_turn": turn,
                "actor": who,
                "scope": scope,
                "observed_at": row.get("observed_at"),
                "monotonic_ns": row.get("monotonic_ns"),
                "_path": place if mutation else None,
                "_opaque": opaque,
                "_base": base,
                "_origin": origin,
                "_path_epoch": self.path_epochs.get(place),
                "_opaque_epoch": self.opaque_epoch,
            }
            return
        if event.get("phase") != "complete" or key not in self.started:
            return
        begun = self.started.pop(key)
        started_turn = begun["started_turn"]
        outcome = None if key in self.ambiguous_keys else event.get("ok")
        arguments = begun.get("arguments") or {}
        native = (
            machine_command_status(arguments, str(event.get("result_preview") or ""))
            if begun.get("name") == "exec" and isinstance(arguments, dict)
            else True
        )
        if outcome is True and native is not True:
            outcome = native
        refused = str(event.get("result_preview") or "").startswith(REFUSED)
        if outcome is not True or refused:
            arguments = begun.get("arguments") or {}
            name = str(begun.get("name") or "")
            path = arguments.get("path") or arguments.get("file_path") if isinstance(arguments, dict) else None
            place = relative(path, self.vocabulary, self.workdir) if path else None
            if place and name not in READ_TOOLS:
                self._uncertain(
                    place, turn, who, "The intervening mutation did not have a confirmed successful outcome."
                )
            if path and name not in READ_TOOLS:
                self._invalidate_cached(
                    turn, who, "An unconfirmed path mutation has no exhaustive resource-effect coverage."
                )
            elif name in ("exec", "ops_submit"):
                for cached in list(self.files):
                    self._uncertain(
                        cached,
                        turn,
                        who,
                        "An unsuccessful or unobserved shell operation may have changed the cached bytes.",
                    )
            self.unsuccessful.append(
                {
                    "turn": turn,
                    "actor": who,
                    "tool": begun.get("name"),
                    "call_id": call,
                    "ok": False if refused or outcome is False else None,
                    "arguments": arguments,
                    "native_file_change": event.get("file_change"),
                }
            )
            return
        name, arguments = str(begun.get("name") or ""), begun.get("arguments") or {}
        if not isinstance(arguments, dict):
            return
        if name not in READ_TOOLS:
            self.operations.append(
                {
                    "started_turn": started_turn,
                    "completed_turn": turn,
                    "actor": who,
                    "call_id": call,
                    "tool": name,
                    "arguments": arguments,
                    "result": str(event.get("result_preview") or ""),
                    "started_at": begun.get("observed_at"),
                    "completed_at": row.get("observed_at"),
                    "started_monotonic_ns": begun.get("monotonic_ns"),
                    "completed_monotonic_ns": row.get("monotonic_ns"),
                }
            )
        if name in OPS_TOOLS:
            self.ops.add(name)
        if declared := declared_runs(arguments, self.vocabulary.script):
            self.declared_readings.append({"turn": turn, "actor": who, "tool": name, "commands": declared})
        if name == "ops_submit" or (name == "exec" and arguments.get("run_in_background") is True):
            self.pending_effects.append(begun)
            self.unverified.append(
                {
                    "turn": turn,
                    "actor": who,
                    "tool": name,
                    "reason": "Submission success does not prove asynchronous file effects have finished.",
                }
            )
        command = str(arguments.get("command") or "")
        if command:
            self._command(
                turn,
                who,
                scope,
                call,
                name,
                arguments,
                str(event.get("result_preview") or ""),
                {**row, "started_at": begun.get("observed_at")},
            )
        change = event.get("file_change") or {}
        path = change.get("path") or arguments.get("path") or arguments.get("file_path")
        place = relative(path, self.vocabulary, self.workdir) if path else None
        if place is None or name in READ_TOOLS:
            return
        pending = self._pending_mutation(place)
        replay_safe = (
            begun.get("_path") == place
            and begun.get("_path_epoch") == self.path_epochs.get(place)
            and begun.get("_opaque_epoch") == self.opaque_epoch
            and not pending
        )
        before = begun.get("_base") if replay_safe and begun.get("_origin") in (None, (who, scope)) else None
        bytes_known = True
        if isinstance(change.get("after"), str):
            content = change["after"]
            if name == "edit_file":
                if before is not None and change.get("before") == before.replace("\r\n", "\n"):
                    if "\r\n" in before:
                        content = content.replace("\n", "\r\n")
                else:
                    bytes_known = "\n" not in content
            elif name != "write_file" or arguments.get("mode") == "append":
                bytes_known = False
            if pending:
                bytes_known = False
        elif name == "write_file" and isinstance(arguments.get("content"), str) and replay_safe:
            content = arguments["content"]
            if arguments.get("mode") == "append":
                if before is None:
                    self.unverified.append(
                        {
                            "turn": turn,
                            "actor": who,
                            "path": place,
                            "reason": "The prior content of an append was not observed.",
                        }
                    )
                    self.fragments.append(
                        {
                            "turn": started_turn,
                            "actor": who,
                            "path": place,
                            "operation": "append",
                            "fragment": content,
                            "call_id": call,
                        }
                    )
                    self._uncertain(
                        place,
                        turn,
                        who,
                        "Only an appended fragment was observed, not complete current bytes.",
                        exists=None if pending else True,
                    )
                    self.writes.append((started_turn, who, place, name))
                    return
                content = before + content
        else:
            self.unverified.append(
                {
                    "turn": turn,
                    "actor": who,
                    "path": place,
                    "reason": "The successful operation retained no complete file content.",
                }
            )
            self._uncertain(
                place,
                turn,
                who,
                "The successful operation did not retain complete current bytes.",
                exists=None if pending else True,
            )
            self.fragments.append(
                {
                    "turn": started_turn,
                    "actor": who,
                    "path": place,
                    "operation": name,
                    "arguments": arguments,
                    "call_id": call,
                }
            )
            self.writes.append((started_turn, who, place, name))
            return
        self.files[place] = content
        self.file_origins[place] = (who, scope)
        self.uncertain_paths.pop(place, None)
        self.writes.append((started_turn, who, place, name))
        self.versions.append(
            {
                "turn": started_turn,
                "completed_turn": turn,
                "started_at": begun.get("observed_at"),
                "completed_at": row.get("observed_at"),
                "started_monotonic_ns": begun.get("monotonic_ns"),
                "completed_monotonic_ns": row.get("monotonic_ns"),
                "actor": who,
                "path": place,
                "tool": name,
                "call_id": call,
                "content": content,
                "bytes_known": bytes_known,
                "content_representation": "exact_utf8_bytes" if bytes_known else "native_normalized_text",
                "sha256": hashlib.sha256(content.encode()).hexdigest() if bytes_known else None,
            }
        )
        if not bytes_known:
            self._uncertain(
                place, turn, who, "The native text snapshot does not establish original newline bytes.", exists=True
            )
        if pending:
            self._uncertain(
                place, turn, who, "Another in-flight mutation can change this observed snapshot.", exists=None
            )

    def _pending_mutation(self, place):
        return any(
            entry.get("_opaque") or entry.get("_path")
            for entry in [*self.started.values(), *self.orphaned, *self.pending_effects]
        )

    def _uncertain(self, place, turn, who, reason, *, exists=None) -> None:
        self.files.pop(place, None)
        self.file_origins.pop(place, None)
        state = {"path": place, "turn": turn, "actor": who, "reason": reason, "exists": exists}
        self.uncertain_paths[place] = state
        self.uncertain_mutations.append(state)

    def _invalidate_cached(self, turn, who, reason) -> None:
        for place in list(self.files):
            self._uncertain(place, turn, who, reason)

    def _command(self, turn, who, scope, call, tool, arguments, result, observation) -> None:
        command = arguments["command"]
        if tool != "exec":
            self.unverified.append(
                {
                    "turn": turn,
                    "actor": who,
                    "tool": tool,
                    "reason": "A submitted command is not an observed shell execution.",
                }
            )
            if tool == "ops_submit":
                self._invalidate_cached(
                    turn, who, "A submitted job may change cached files without a retained snapshot."
                )
            return
        try:
            parser = shlex.shlex(command, posix=True, punctuation_chars=";&|><")
            parser.whitespace_split = True
            tokens = list(parser)
        except ValueError:
            tokens = []
        direct = bool(tokens) and not any(word and set(word) <= set(";&|><") for word in tokens)
        readonly = (
            direct
            and tokens[0] in {"ls", "cat", "head", "tail", "pwd", "stat", "echo"}
            and "$(" not in command
            and "`" not in command
        )
        if runs_script(command, self.vocabulary.script):
            label = f"turn {turn} ({who}), call {call}: {command}"
            self.reading_attempts.append(label)
            payloads = []
            for line in result.splitlines():
                try:
                    value = json.loads(line)
                except (TypeError, ValueError):
                    continue
                if isinstance(value, dict):
                    payloads.append(value)
                    self.reading_results.append(
                        {
                            **value,
                            "turn": turn,
                            "actor": who,
                            "scope": scope,
                            "call_id": call,
                            "observed_at": observation.get("observed_at"),
                            "monotonic_ns": observation.get("monotonic_ns"),
                        }
                    )
            overviews = [value for value in payloads if "reading" in value or "store_time" in value]
            reasons = []
            if who != "oncall":
                reasons.append("The host recorded the caller as the assistant, not the on-call colleague.")
            elif not all(json.loads(scope)):
                reasons.append("The child execution's launch, process and log identity were unavailable.")
            stamp, monotonic = observation.get("observed_at"), observation.get("monotonic_ns")
            if type(stamp) not in (int, float) or type(monotonic) is not int or monotonic < 1:
                reasons.append("The host observation clocks were unavailable.")
            if arguments.get("machine") != "local-lab":
                reasons.append("The command did not name the registered local-lab machine.")
            expected_queue = (Path(self.workdir) / self.vocabulary.queue_folder).resolve() if self.workdir else None
            run = script_run(command, self.vocabulary.script, arguments.get("working_dir"))
            queue_arg = queue_argument(list(run.arguments)) if run else None
            queue_path = run.path(queue_arg) if run and queue_arg else None
            unbound = len(reasons)
            if expected_queue is None or queue_path is None or queue_path.resolve() != expected_queue:
                reasons.append("The effective command queue is not this drill's queue folder.")
            if self.lab is None:
                reasons.append("The registered lab script identity was not available.")
            else:
                script = run.script_path if run else None
                source = Path(__file__).parent / "lab" / self.vocabulary.script
                try:
                    if (
                        script is None
                        or script.resolve() != (Path(self.lab) / self.vocabulary.script).resolve()
                        or script.read_bytes() != source.read_bytes()
                    ):
                        reasons.append("The command did not use this case's pristine lab script.")
                    if (Path(self.lab) / "feed_cache.md").read_bytes() != source.with_name(
                        "feed_cache.md"
                    ).read_bytes():
                        reasons.append("The lab event feed differed from this case's source.")
                except OSError:
                    reasons.append("The lab script bytes were unavailable.")
            if run is None:
                reasons.append("The result was not retained for one direct Python invocation.")
            bound = len(reasons) == unbound
            overview = overviews[0] if len(overviews) == 1 else {}
            try:
                moment = datetime.strptime(overview.get("store_time", ""), STAMP)
            except (TypeError, ValueError):
                moment = None
            number = overview.get("reading")
            if len(overviews) != 1 or type(number) is not int or number < 1 or moment is None:
                reasons.append("Exactly one positive reading overview with a valid store time is required.")
            if any(
                type(overview.get(key)) is not int or overview[key] < 0
                for key in ("pending", "pushed", "withdrawn", "next_check_seconds")
            ):
                reasons.append("The overview counts or cadence were missing or invalid.")
            if any(
                set(value) & {"actor", "turn", "scope", "call_id", "observed_at", "monotonic_ns"} for value in payloads
            ):
                reasons.append("The script payload claimed host attribution metadata.")
            source_errors, origin = patrol_source_errors(
                payloads,
                overview,
                self.source,
                (observation.get("started_at"), stamp),
                self.clock_origin,
                self.previous_source_store,
            )
            reasons.extend(source_errors)
            if bound and moment is not None:
                self.clock_origin, self.previous_source_store = origin, moment
            if self.last_reading and number is not None and moment is not None:
                if type(number) is not int or number <= self.last_reading[0] or moment <= self.last_reading[1]:
                    reasons.append("The reading number or store time did not advance.")
                if type(monotonic) is int and monotonic - self.last_reading[2] < self.last_reading[3] * 1_000_000_000:
                    reasons.append("The next read preceded the host-observed suggested interval.")
            self.reading_checks.append(
                {
                    "turn": turn,
                    "actor": who,
                    "call_id": call,
                    "command": command,
                    "verified": not reasons,
                    "limitations": reasons,
                    "observed_at": stamp,
                    "monotonic_ns": monotonic,
                }
            )
            if not reasons:
                self.last_reading = (number, moment, monotonic, overview["next_check_seconds"])
                self.readings.append(label)
        if not direct or not tokens or tokens[0] != "mv":
            if not runs_script(command, self.vocabulary.script) and (not readonly):
                self.unverified.append(
                    {
                        "turn": turn,
                        "actor": who,
                        "command": command,
                        "reason": "Shell effects require the actual command, retained output and state; they were not reconstructed.",
                    }
                )
                self._invalidate_cached(
                    turn, who, "Opaque shell effects prevent reconstruction from earlier cached bytes."
                )
            return
        if any(word.startswith("-") and word != "--" for word in tokens[1:]):
            self.unverified.append(
                {
                    "turn": turn,
                    "actor": who,
                    "reason": "Move flags require observed state rather than inferred transfer.",
                    "command": command,
                }
            )
            self._invalidate_cached(turn, who, "Move flags left the current file locations or bytes unverified.")
            return
        positional = [token for token in tokens[1:] if not token.startswith("-")]
        if len(positional) != 2:
            self.unverified.append(
                {"turn": turn, "actor": who, "reason": "A multi-source move was not reconstructed.", "command": command}
            )
            return
        source, destination = positional
        place = relative(source, self.vocabulary, self.workdir)
        target = relative(destination, self.vocabulary, self.workdir)
        if not place or not target or not target.startswith(f"{self.vocabulary.queue_folder}/"):
            return
        moved = target if target.endswith(".md") else f"{target.rstrip('/')}/{Path(place).name}"
        self.moves.append(f"turn {turn} ({who}): {command}")
        self.move_events.append(
            {
                "turn": turn,
                "actor": who,
                "source": place,
                "destination": moved,
                "call_id": call,
                "command": command,
                "content_observed": place in self.files,
                "observed_at": observation.get("observed_at"),
                "monotonic_ns": observation.get("monotonic_ns"),
            }
        )
        self.writes.append((turn, who, moved, "mv"))
        if place in self.files:
            self.files[moved] = self.files.pop(place)

    def first(self, who: str, prefix: str) -> int | None:
        return next((turn for turn, by, place, _ in self.writes if by == who and place.startswith(prefix)), None)


def runs_script(command: str, script: str) -> bool:
    """A direct Python invocation at a shell-command boundary, excluding echoed command text."""
    return invokes(command, script)


def final_files(workdir: Path | None, vocabulary: Vocabulary, *, exact=False) -> dict[str, str] | None:
    """The store's records as the drill left them in its working directory; None when the directory is unknown."""
    if workdir is None or not Path(workdir).is_dir():
        return None
    found = {}
    for root in vocabulary.roots:
        folder = Path(workdir) / root
        if folder.is_dir():
            for path in sorted(folder.rglob("*")):
                relative_path = path.relative_to(workdir)
                if (
                    path.is_file()
                    and path.resolve().is_relative_to(Path(workdir).resolve())
                    and not any(part.startswith(".") for part in relative_path.parts)
                ):
                    try:
                        content = path.read_bytes().decode("utf-8", errors="strict" if exact else "replace")
                    except (OSError, UnicodeError):
                        continue
                    found[path.relative_to(workdir).as_posix()] = content
    return found


def expectations(expected: str | None) -> tuple[datetime | None, dict[str, dict]]:
    """The export time and each member's expected outcome, read from a card's `expected` lines."""
    now, members = None, {}
    for line in (expected or "").splitlines():
        line = line.strip()
        found = EXPORT.search(line)
        if found and now is None:
            now = datetime.strptime(found.group(1), STAMP)
        match = EXPECT.match(line)
        if not match:
            continue
        member, action, rest = match.groups()
        entry = {"action": action}
        if action == "send":
            day = re.search(r"\d{4}-\d{2}-\d{2}", rest)
            entry["date"] = day.group() if day else None
            fixed = re.search(r"\bat (\d{2}:\d{2})", rest)
            earliest = re.search(r"\bfrom (\d{2}:\d{2})", rest)
            entry["at"] = fixed.group(1) if fixed else None
            entry["from"] = earliest.group(1) if earliest else None
        members[member] = entry
    return now, members


def in_windows(moment: datetime) -> bool:
    return any(start <= moment.time() <= end for start, end in WINDOWS)


def plan_check(entry: dict, times: list[datetime], now: datetime | None) -> dict:
    """Compare every observed time, leaving absence distinct from a successful schedule."""
    out = {"expected": entry["action"], "planned_times_found": [moment.strftime(STAMP) for moment in times]}
    if entry["action"] != "send":
        return out
    out["expected"] = f"send {entry['date']}"
    out["schedule_observed"] = bool(times)
    out["date_matches"] = all(moment.strftime("%Y-%m-%d") == entry["date"] for moment in times) if times else None
    out["within_windows"] = all(in_windows(moment) for moment in times) if times else None
    if now is not None:
        out["not_before_export"] = all(moment >= now for moment in times) if times else None
    if entry.get("at"):
        out["time_as_fixed"] = all(moment.strftime("%H:%M") == entry["at"] for moment in times) if times else None
    if entry.get("from"):
        out["not_before_earliest"] = (
            all(moment.strftime("%H:%M") >= entry["from"] for moment in times) if times else None
        )
    return out


def field_values(text: str, labels) -> dict[str, list[str]]:
    """Every exact field occurrence, preserving contradictory repeated metadata."""
    found = {}
    for line in text.splitlines():
        stripped = line.strip().lstrip("-*#> ").strip()
        for label in labels:
            if stripped.startswith(label) and stripped[len(label) :].startswith((":", chr(0xFF1A))):
                found.setdefault(label, []).append(stripped[len(label) :].lstrip(COLONS).strip())
    return found


def labelled(text: str, labels) -> dict[str, str]:
    """The current field values; callers retain duplicate occurrences separately when measuring records."""
    return {label: values[-1] for label, values in field_values(text, labels).items()}


def queue_record(place: str, text: str, vocabulary: Vocabulary, year: int) -> dict:
    labels = (
        vocabulary.batch_label,
        vocabulary.member_label,
        vocabulary.nickname_label,
        vocabulary.time_labels[1],
        vocabulary.type_label,
        vocabulary.approval_label,
    )
    values = field_values(text.split(vocabulary.body_marker, 1)[0], labels)
    fields = {label: items[-1] for label, items in values.items()}
    filename_member = next(iter(MEMBER.findall(Path(place).name)), None)
    content_member = next(iter(MEMBER.findall(fields.get(vocabulary.member_label, ""))), None)
    named = NAMED.match(Path(place).name)
    named_time = _moment(*named.groups()) if named else None
    declared = _when(fields.get(vocabulary.time_labels[1], ""), year)
    declared_times = [_when(value, year) for value in values.get(vocabulary.time_labels[1], [])]
    filename_ok = bool(re.fullmatch(r"\d{8}-\d{4}-XS\d{6}\.md", Path(place).name)) and named_time is not None
    return {
        "member": content_member or filename_member,
        "member_ids": sorted(
            {member for value in values.get(vocabulary.member_label, []) for member in MEMBER.findall(value)}
            | ({filename_member} if filename_member else set())
        ),
        "filename_member": filename_member,
        "content_member": content_member,
        "member_consistent": content_member == filename_member if content_member and filename_member else None,
        "folder": Path(place).parent.name,
        "planned": (named_time or declared).strftime(STAMP) if named_time or declared else None,
        "filename_time": named_time.strftime(STAMP) if named_time else None,
        "declared_time": declared.strftime(STAMP) if declared else None,
        "declared_times_found": [moment.strftime(STAMP) for moment in declared_times if moment],
        "time_consistent": named_time == declared if named_time and declared else None,
        "filename_as_required": filename_ok,
        "fields": fields,
        "duplicate_fields": {label: items for label, items in values.items() if len(items) > 1},
        "missing_fields": [label for label in labels if not fields.get(label)],
        "body": body(text, vocabulary),
    }


def ledger_facts(text: str | None, vocabulary: Vocabulary) -> dict:
    """Ledger cells in their declared columns, without inferring an item from unrelated cells."""
    if text is None:
        return {"exists": False}
    rows = [
        [cell.strip() for cell in line.strip().strip("|").split("|")]
        for line in text.splitlines()
        if line.strip().startswith("|") and not re.fullmatch(r"[|\s:-]+", line.strip())
    ]
    if not rows:
        return {"exists": True, "table": False}
    header, body_rows = rows[0], rows[1:]
    items, entries = {}, []
    for row in body_rows:
        entry = dict(zip(vocabulary.ledger_columns, row)) if len(row) == len(vocabulary.ledger_columns) else {}
        member = row[2] if len(row) > 2 and MEMBER.fullmatch(row[2]) else "?"
        item = row[4] if len(row) > 4 and row[4] in vocabulary.ledger_items else "?"
        items.setdefault(member, []).append(item)
        entries.append(
            {
                "values": row,
                "fields": entry,
                "width_as_required": len(row) == len(header),
                "member": member,
                "item": item,
            }
        )
    return {
        "exists": True,
        "header": header,
        "header_as_required": tuple(header) == vocabulary.ledger_columns,
        "rows": len(body_rows),
        "items_by_member": items,
        "entries": entries,
    }


def ledger_versions(trace: Trace, vocabulary: Vocabulary) -> list[dict]:
    """Whether each retained ledger version preserves the observed prior bytes, including the host baseline."""
    previous = trace.baseline_files.get(vocabulary.ledger, "") if trace.baseline_files is not None else None
    ledger_versions = []
    for version in trace.versions:
        if version["path"] == vocabulary.ledger:
            ledger_versions.append(
                {
                    "turn": version["turn"],
                    "sha256": version["sha256"],
                    "preserves_previous_bytes": version["content"].startswith(previous)
                    if previous is not None
                    else None,
                }
            )
            previous = version["content"]
    return ledger_versions


def oncall_facts(trace: Trace, queue: dict, reports: dict, vocabulary: Vocabulary) -> dict | None:
    """Project measured patrol operations and final records without turning their existence into completion."""
    queue_root = f"{vocabulary.queue_folder}/"
    moved_by_assistant = [
        path
        for _, actor, path, _ in trace.writes
        if actor == "assistant"
        and path.startswith((f"{queue_root}{vocabulary.pushed}/", f"{queue_root}{vocabulary.withdrawn}/"))
    ]
    if (
        trace.oncall_executions
        or trace.reading_attempts
        or trace.moves
        or reports
        or trace.ops
        or moved_by_assistant
        or trace.declared_readings
    ):
        return {
            "oncall_executions": trace.oncall_executions,
            "script_readings": len(trace.readings),
            "patrol_readings": trace.reading_results,
            "reading_commands": trace.readings,
            "completed_read_commands": trace.reading_attempts,
            "reading_checks": trace.reading_checks,
            "readings_declared_in_campaigns": trace.declared_readings,
            "campaign_readings_scope": "A reading taken through a campaign's readings table runs inside the on-call "
            "tools and retains no execution row with its output or host timing, so it is listed apart and never "
            "counted as a script reading.",
            "ops_tools": sorted(trace.ops),
            "file_moves": trace.moves,
            "move_events": trace.move_events,
            "files_in_pushed": sorted(p for p, row in queue.items() if row["folder"] == vocabulary.pushed),
            "files_in_withdrawn": sorted(p for p, row in queue.items() if row["folder"] == vocabulary.withdrawn),
            "patrol_reports": sorted(reports),
            "patrol_report_contents": reports,
            "queue_moves_by_the_assistant_itself": moved_by_assistant,
        }
    return None


def delivered_versions_facts(exchanges, vocabulary: Vocabulary, year: int, draft) -> list[dict]:
    """Retained delivered bytes in order, with overwritten/missing snapshots explicitly unavailable."""
    deliveries = [
        (turn, str(path)) for turn, exchange in enumerate(exchanges, 1) for path in exchange.execution.deliverables
    ]
    last_delivery = {path: index for index, (_, path) in enumerate(deliveries)}
    versions = []
    for index, (turn, name) in enumerate(deliveries):
        path = Path(name)
        version = {"turn": turn, "name": path.name}
        if last_delivery[name] != index or not path.is_file():
            version["unavailable"] = "The earlier bytes were not separately retained, or the snapshot is missing."
            versions.append(version)
            continue
        if path.suffix.lower() != ".md":
            version["unavailable"] = "The delivery is not the prescribed Markdown record."
            versions.append(version)
            continue
        text = path.read_text(errors="replace")
        version.update(content=text, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        versions.append(version)
        for member, part in sections(text):
            fields = labelled(part, vocabulary.time_labels)
            if vocabulary.hold_mark not in fields.get(vocabulary.time_labels[0], ""):
                draft(
                    f"delivery {index + 1} list {member}",
                    member,
                    body(part, vocabulary),
                    _when(fields.get(vocabulary.time_labels[0], ""), year),
                )
        if re.fullmatch(r"\d{8}-\d{4}-XS\d{6}\.md", path.name):
            row = queue_record(path.name, text, vocabulary, year)
            if row["member"]:
                draft(
                    f"delivery {index + 1} queue {path.name}",
                    row["member"],
                    row["body"],
                    datetime.strptime(row["planned"], STAMP) if row["planned"] else None,
                )
    return versions


def facts(
    exchanges,
    vocabulary: Vocabulary,
    expected: str | None = None,
    workdir: Path | None = None,
    lab: Path | None = None,
    baseline: Path | None = None,
) -> dict:
    """Keep final state, historical successful output and unavailable operation evidence distinct."""
    trace = Trace(exchanges, vocabulary, workdir, lab, baseline, expected)
    files = final_files(workdir, vocabulary)
    records = files if files is not None else trace.files
    now, members = expectations(expected)
    year = now.year if now else datetime.now().year
    queue_root = f"{vocabulary.queue_folder}/"
    found = {
        "records_read_from": "working directory" if files is not None else "execution records",
        "record_versions": trace.versions,
        "successful_operations": trace.operations,
        "records_present_before_drill": trace.baseline_files,
        "patrol_event_source": {
            "anchor": trace.source[0].strftime(STAMP) if trace.source[0] else None,
            "events": trace.source[1],
        },
        "host_lab_workdir": str(lab) if lab else None,
        "unknown_record_paths": trace.uncertain_paths,
        "uncertain_mutation_history": trace.uncertain_mutations,
        "observed_fragments_without_complete_bytes": trace.fragments,
        "evidence_limits": [
            "Word occurrences are search aids, not semantic verdicts.",
            "Approval and requested amendments are judged from actual manager words and delivered versions.",
            "File transfers represent simulated pending tasks, not customer sends.",
        ],
    }
    queue, planned, drafts, replies = {}, {}, {}, {}

    def draft(key, member, content, moment=None):
        if not content:
            return
        role = "reply" if members.get(member, {}).get("action") == "reply" else "proactive"
        target = replies if role == "reply" else drafts
        target[key] = {**message_facts(content, vocabulary, moment), "member": member, "role": role, "content": content}

    for place, text in sorted(records.items()):
        if not place.startswith(queue_root) or Path(place).name.startswith(vocabulary.report_prefix):
            continue
        row = queue_record(place, text, vocabulary, year)
        queue[place] = row
        for member in row["member_ids"]:
            for stamp in dict.fromkeys([row["filename_time"], *row["declared_times_found"]]):
                if stamp:
                    planned.setdefault(member, []).append(datetime.strptime(stamp, STAMP))
        moment = datetime.strptime(row["planned"], STAMP) if row["planned"] else None
        if row["member"]:
            draft(f"queue {place}", row["member"], row["body"], moment)
    if queue:
        found["queue_files"] = queue

    lists = {place: text for place, text in records.items() if place.startswith(f"{vocabulary.list_folder}/")}
    for name, text in delivered(exchanges).items():
        if sections(text) and name not in {Path(place).name for place in lists}:
            lists[f"delivered {name}"] = text
    listed, entries = {}, []
    for place, text in lists.items():
        for member, part in sections(text):
            fields = labelled(part, (*vocabulary.time_labels, vocabulary.basis_label))
            line = fields.get(vocabulary.time_labels[0], fields.get(vocabulary.time_labels[1], ""))
            moment = _when(line, year)
            held = vocabulary.hold_mark in line
            reply = members.get(member, {}).get("action") == "reply" and not moment
            row = {
                "member": member,
                "in": place,
                "planned": moment.strftime(STAMP) if moment else None,
                "marked_hold": held,
                "reply_only": reply,
                "reason_or_basis": fields.get(vocabulary.basis_label, ""),
                "content": part,
            }
            entries.append(row)
            listed[member] = row
            if not held:
                draft(f"list {member}", member, body(part, vocabulary), moment)
            if moment and member not in planned:
                planned.setdefault(f"list:{member}", []).append(moment)
    if entries:
        found["confirmation_list"] = listed
        found["confirmation_entries"] = entries
        found["duplicate_confirmation_members"] = sorted(
            member for member in listed if sum(row["member"] == member for row in entries) > 1
        )

    for index, version in enumerate(trace.versions, 1):
        place, text = version["path"], version["content"]
        if place.startswith(queue_root) and not Path(place).name.startswith(vocabulary.report_prefix):
            row = queue_record(place, text, vocabulary, year)
            if row["member"]:
                moment = datetime.strptime(row["planned"], STAMP) if row["planned"] else None
                draft(f"version {index} queue {place}", row["member"], row["body"], moment)
        elif place.startswith(f"{vocabulary.list_folder}/"):
            for member, part in sections(text):
                fields = labelled(part, vocabulary.time_labels)
                if vocabulary.hold_mark not in fields.get(vocabulary.time_labels[0], ""):
                    draft(
                        f"version {index} list {member}",
                        member,
                        body(part, vocabulary),
                        _when(fields.get(vocabulary.time_labels[0], ""), year),
                    )
    found["retained_delivery_versions"] = delivered_versions_facts(exchanges, vocabulary, year, draft)
    historical_queue = []
    for version in trace.versions:
        if not version["path"].startswith(queue_root) or Path(version["path"]).name.startswith(
            vocabulary.report_prefix
        ):
            continue
        row = queue_record(version["path"], version["content"], vocabulary, year)
        times = [
            datetime.strptime(stamp, STAMP)
            for stamp in dict.fromkeys([row["filename_time"], *row["declared_times_found"]])
            if stamp
        ]
        historical_queue.append(
            {
                "turn": version["turn"],
                "path": version["path"],
                "record": row,
                "plan_against_expected": {
                    member: plan_check(members[member], times, now) for member in row["member_ids"] if member in members
                },
            }
        )
    found["queue_versions"] = historical_queue
    if drafts:
        found["drafted_messages"] = drafts
    if replies:
        found["reply_messages"] = replies
    if members:
        found["plan_against_expected"] = {}
        for member, entry in members.items():
            row = plan_check(entry, sorted(planned.get(member) or planned.get(f"list:{member}") or []), now)
            paths = [place for place, queued in queue.items() if member in queued["member_ids"]]
            uncertain = [
                state
                for place, state in trace.uncertain_paths.items()
                if place.startswith(queue_root) and member in MEMBER.findall(place)
            ]
            row.update(
                queued=True
                if paths or any(state["exists"] is True for state in uncertain)
                else None
                if uncertain and files is None
                else False,
                queue_files=paths,
                duplicate_queue_files=len(paths) > 1,
                in_confirmation_list=member in listed,
            )
            found["plan_against_expected"][member] = row
        found["export_time"] = now.strftime(STAMP) if now else None
    first_queue = trace.first("assistant", f"{queue_root}{vocabulary.pending}/")
    order = {
        "first_list_written_turn": trace.first("assistant", f"{vocabulary.list_folder}/"),
        "first_file_delivered_turn": next(
            (turn for turn, exchange in enumerate(exchanges, 1) if exchange.execution.deliverables), None
        ),
        "first_queue_write_turn": first_queue,
        "queue_operations": [
            {
                "turn": turn,
                "actor": actor,
                "path": path,
                "tool": tool,
                "manager_messages_up_to_write": [exchange.user for exchange in exchanges[:turn]],
                "delivery_turns_before_write": [
                    i for i, exchange in enumerate(exchanges[: turn - 1], 1) if exchange.execution.deliverables
                ],
            }
            for turn, actor, path, tool in trace.writes
            if path.startswith(queue_root)
        ],
    }
    if first_queue:
        said = [exchange.user for exchange in exchanges[:first_queue]]
        order["manager_messages_up_to_queue_write"] = said
        order["confirm_words_in_that_turn"] = [word for word in vocabulary.confirm_words if word in said[-1]]
        order["confirmation_word_hits_are_not_authorization"] = True
    found["order"] = order
    found["ledger"] = ledger_facts(records.get(vocabulary.ledger), vocabulary)
    if files is None and vocabulary.ledger in trace.uncertain_paths:
        found["ledger"] = {
            "exists": trace.uncertain_paths[vocabulary.ledger]["exists"],
            "content_available": False,
            "table": None,
        }
    found["ledger_versions"] = ledger_versions(trace, vocabulary)
    reports = {place: text for place, text in records.items() if Path(place).name.startswith(vocabulary.report_prefix)}
    oncall = oncall_facts(trace, queue, reports, vocabulary)
    if oncall:
        found["on_call"] = oncall
    attempts = trace.unsuccessful + [
        {
            "turn": event["started_turn"],
            "actor": event.get("actor"),
            "tool": event.get("name"),
            "ok": None,
            "arguments": event.get("arguments"),
            "call_id": event.get("tool_call_id"),
        }
        for event in [*trace.started.values(), *trace.orphaned]
    ]
    if attempts:
        found["unsuccessful_or_unobserved_calls"] = attempts
    if trace.unverified:
        found["unverified_operations"] = trace.unverified
    found["chat_messages_for_semantic_review"] = messages(exchanges)
    files_out = delivered(exchanges)
    if files_out:
        found["delivered_files"] = sorted(files_out)
    return found


def _delivered_content(file: dict, root: Path) -> str | None:
    """Read the retained actual bytes, rejecting missing, changed or escaped delivery records."""
    try:
        raw = Path(file["path"])
        path = (raw if raw.is_absolute() else root / raw).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file() or path.name != file.get("name"):
            return None
        content = path.read_bytes()
        if not file.get("sha256") or hashlib.sha256(content).hexdigest() != file["sha256"]:
            return None
        return content.decode("utf-8")
    except (KeyError, TypeError, OSError, UnicodeError, RuntimeError):
        return None


def records_delivered(item: dict) -> bool:
    """Each actual drill delivers a complete batch confirmation document with retained content identity."""
    from experimental.harness.scenario.contract import load

    root = Path(item["delivery_root"]) if item.get("delivery_root") else None
    if root is None:
        return False
    case_root = Path(item.get("scenario_root") or Path(__file__).parent)
    scenario = load(case_root)
    vocabulary = Vocabulary.load(scenario)
    cards = {card.id: card for card in scenario.situation.cases}
    drills = item.get("drills") or []
    if not drills:
        return False
    for drill in drills:
        card = cards.get(drill.get("card"))
        if card is None:
            return False
        now, expected = expectations(card.expected)
        batch = re.search(r"\bGJ\d{8}-\d{2}\b", card.expected or "")
        if now is None or batch is None:
            return False
        filename = f"{vocabulary.list_prefix}{batch.group()}.md"
        documents = [
            (file, _delivered_content(file, root))
            for turn in drill.get("exchanges", [])
            for file in turn.get("delivered", [])
        ]
        nicknames = {}
        for name in card.files:
            nicknames.update(re.findall(r"(?m)^##\s+(XS\d{6})\s+([^\n]+)", (case_root / name).read_text()))
        sole_reply = sum(outcome["action"] == "reply" for outcome in expected.values()) == 1
        accepted = False
        for file, content in documents:
            heading = next(
                (line.strip().lstrip(chr(0xFEFF)) for line in (content or "").splitlines() if line.strip()), ""
            )
            if file.get("name") != filename or not content or batch.group() not in heading:
                continue
            parts = sections(content)
            if len(parts) != len(expected) or {member for member, _ in parts} != set(expected):
                continue
            complete = True
            for member, part in parts:
                fields = labelled(part, (*vocabulary.time_labels, vocabulary.basis_label))
                stamp = fields.get(vocabulary.time_labels[0], "")
                action = expected[member]["action"]
                if action == "hold":
                    complete &= vocabulary.hold_mark in stamp and bool(fields.get(vocabulary.basis_label))
                elif action == "send":
                    complete &= (
                        _when(stamp, now.year) is not None
                        and bool(body(part, vocabulary))
                        and bool(fields.get(vocabulary.basis_label))
                    )
                else:
                    reply = body(part, vocabulary) or next(
                        (
                            text
                            for delivered_file, text in documents
                            if text
                            and delivered_file is not file
                            and (
                                any(
                                    identity in delivered_file.get("name", "") + text
                                    for identity in (member, nicknames.get(member, ""))
                                    if identity
                                )
                                or sole_reply
                                and sum(
                                    bool(other_text) and other_file is not file for other_file, other_text in documents
                                )
                                == 1
                            )
                            and any(line.strip() and not line.lstrip().startswith("#") for line in text.splitlines())
                        ),
                        "",
                    )
                    complete &= _when(stamp, now.year) is None and vocabulary.reply_mark in part and bool(reply)
            if complete:
                accepted = True
                break
        if not accepted:
            return False
    return True


DELIVERED = records_delivered


class StoreOwner(Owner):
    """The store manager of the baby store scenario, judging with the store's calendar, word search and ruler."""

    def __init__(self, scenario, provider, skills, **options):
        super().__init__(scenario, provider, skills, facts=self._facts, **options)
        self.vocabulary = Vocabulary.load(scenario)

    def _facts(self, name, exchanges, card) -> dict:
        placed = self.workdirs.get(name)
        lab = None
        descriptor = placed.get("lab") if placed else None
        if descriptor and descriptor.get("machine") == "local-lab":
            registry = Path(descriptor["registry"])
            if registry.is_file():
                rows = [
                    row
                    for row in json.loads(registry.read_text()).get("connections", [])
                    if row.get("id") == "local-lab" and row.get("transport") == "local"
                ]
                if len(rows) == 1 and len(rows[0].get("paths", [])) == 1:
                    candidate = Path(descriptor["workdir"]).resolve()
                    if Path(rows[0]["paths"][0]).resolve() == candidate:
                        lab = candidate
        return facts(
            exchanges,
            self.vocabulary,
            getattr(card, "expected", None),
            Path(placed["workdir"]) if placed else None,
            lab,
            getattr(self, "workdir", None),
        )


# The owner the simulation entry judges this case by (`experimental.simulation.__main__.owner_of`).
OWNER = StoreOwner
