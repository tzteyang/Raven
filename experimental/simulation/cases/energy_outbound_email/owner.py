"""Supply the outbound sales manager's source-backed operation and letter evidence.

Every observable draft, queue and delivered version is retained with its content and identity. Explicit tool
outcomes, native file changes, host timing and the configured lab distinguish completed effects from attempts.
Current disk state does not prove earlier contents or chronology. Word and number measurements remain partial;
the owner model reads the full applicable sources, conversation and versions and decides the semantic verdicts.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from experimental.cultivation.counterpart.owner import Owner
from experimental.cultivation.counterpart.rulers import (
    CONFIG,
    chinese_number,
    messages,
    occurrences,
    tables,
    words,
)
from experimental.simulation.bench.lab import declared_runs, invokes, script_run

from .delivery import delivered_as_requested
from .evidence import (
    Event,
    Write,
    contents,
    delivered_versions,
    events,
    write_records,
    writes,
)

SNIPPET = 120
CASE_ID = re.compile(r"CS-\d{2}")
NOTICE_ID = re.compile(r"GG\d{8}-\d{3}")
ISO_DATE = re.compile(r"20\d\d-\d\d-\d\d")
SESSION = re.compile(r"^(?:holdout-)?(?:s\d+-)?([a-z]+)(?:-\d+)?$")
WRITE_TOOLS = ("write_file", "edit_file")
READ_TOOLS = ("read_file",)
COMMAND_TOOLS = ("exec", "ops_submit")


@dataclass(frozen=True)
class Case:
    """One case of the library as the employee received it."""

    id: str
    industry: str
    scale: int
    place: str
    live: str
    wording: str
    auth: str
    expiry: str
    external: str
    client: str
    source: str = ""


@dataclass(frozen=True)
class Target:
    """What a card is about: the company, its short name, industry and scale, the requester and the signal words."""

    company: str
    short: str
    industry: str
    scale: int
    requester: str
    signal: tuple[str, ...]


class Vocabulary:
    """The words the sales manager's facts are computed with, from the scenario's `reference.md` table."""

    def __init__(self, table: dict[str, tuple[str, ...]]):
        self.table = table

    @classmethod
    def load(cls, root: Path) -> "Vocabulary":
        return cls(words(Path(root) / CONFIG))

    def __getitem__(self, key: str) -> tuple[str, ...]:
        return self.table[key]

    def one(self, key: str) -> str:
        return self.table[key][0]

    def target(self, card: str) -> Target | None:
        values = self.table.get(card)
        if not values or len(values) < 5 or not values[3].isdigit():
            return None
        return Target(values[0], values[1], values[2], int(values[3]), values[4], tuple(values[5:]))

    def notice(self, card: str) -> str | None:
        values = self.table.get(f"{card}_notice")
        return values[0] if values else None

    @property
    def today(self) -> str:
        return self.one("today")


def card_name(name: str, card) -> str:
    """The card a drill played: the card's own name, else the drill's name without its round, exam or repeat marks."""
    if card is not None and getattr(card, "name", None):
        return card.name
    found = SESSION.match(name or "")
    return found.group(1) if found else name


def count(text: str) -> int:
    """Characters as the outreach norms count them: everything but spaces and line breaks."""
    return len(re.sub(r"\s", "", text or ""))


def _cells(row: list[str], head: list[str], column: str) -> str:
    return row[head.index(column)] if column in head and head.index(column) < len(row) else ""


def library(folders, vocabulary: Vocabulary) -> tuple[dict[str, Case], dict[str, str]]:
    """The cases and the withdrawals in these material folders: every table carrying the library's id and wording
    columns is a case table, every table carrying the withdrawal column is a withdrawal table."""
    cases, withdrawn = {}, {}
    key, wording, gone = vocabulary.one("case_id"), vocabulary.one("case_wording"), vocabulary.one("withdrawn_column")
    for folder in folders:
        for path in sorted(Path(folder).rglob("*.md")):
            for table in tables(path.read_text(encoding="utf-8")):
                head, *rows = table
                if key in head and wording in head:
                    for row in rows:

                        def cell(column, row=row, head=head):
                            return _cells(row, head, vocabulary.one(column))

                        scale = re.sub(r"\D", "", cell("case_scale"))
                        cases[cell("case_id")] = Case(
                            id=cell("case_id"),
                            industry=cell("case_industry"),
                            scale=int(scale) if scale else 0,
                            place=cell("case_place"),
                            live=cell("case_live"),
                            wording=cell("case_wording"),
                            auth=cell("case_auth"),
                            expiry=cell("case_expiry") if ISO_DATE.fullmatch(cell("case_expiry")) else "",
                            external=cell("case_external"),
                            client=cell("case_client"),
                            source=cell("case_source"),
                        )
                elif key in head and gone in head:
                    for row in rows:
                        found = ISO_DATE.search(_cells(row, head, gone))
                        if found:
                            withdrawn[_cells(row, head, key)] = found.group(0)
    return cases, withdrawn


def usable(case: Case, on: str, withdrawn: dict[str, str], vocabulary: Vocabulary) -> bool:
    """Whether a case may be cited on a date: nameable or anonymous, not past its expiry, not withdrawn by then."""
    if case.auth not in (vocabulary.one("auth_named"), vocabulary.one("auth_anonymous")):
        return False
    if not case.expiry or case.expiry < on:
        return False
    return not (case.id in withdrawn and withdrawn[case.id] <= on)


def ranked(cases, withdrawn, target: Target, on: str, vocabulary: Vocabulary, limit: int = 3, exclude=()) -> list[dict]:
    """The selection order of outreach norms 3.4 for a target: same industry, closest machine count, usable that day;
    ties go to the nameable case, then the newer one."""
    named = vocabulary.one("auth_named")
    found = [
        case
        for case in cases.values()
        if case.id not in exclude and case.industry == target.industry and usable(case, on, withdrawn, vocabulary)
    ]
    found.sort(key=lambda case: (abs(case.scale - target.scale), case.auth != named, _negated(case.live)))
    return [
        {
            "case": case.id,
            "machines": case.scale,
            "difference": abs(case.scale - target.scale),
            "authorisation": case.auth,
        }
        for case in found[:limit]
    ]


def _negated(live: str) -> int:
    digits = re.sub(r"\D", "", live)
    return -int(digits) if digits else 0


def leads(folder, vocabulary: Vocabulary) -> tuple[list[dict], list[dict]]:
    """The CRM export's lead rows and do-not-contact rows, each as a dict by column name."""
    found, barred = [], []
    company, scope = vocabulary.one("crm_company"), vocabulary.one("dnc_scope")
    for path in sorted(Path(folder).rglob("*.md")):
        for table in tables(path.read_text(encoding="utf-8")):
            head, *rows = table
            if company not in head:
                continue
            rows = [dict(zip(head, row, strict=False)) for row in rows]
            (barred if scope in head else found if vocabulary.one("crm_owner") in head else []).extend(rows)
    return found, barred


def figure_pattern(units) -> re.Pattern:
    alternatives = "|".join(re.escape(unit) for unit in sorted(units, key=len, reverse=True))
    return re.compile(rf"(\d+(?:\.\d+)?)\s*({alternatives})")


def figures(text: str, vocabulary: Vocabulary) -> list[str]:
    """The figures with a unit in a text, spaces removed, in order."""
    return [number + unit for number, unit in figure_pattern(vocabulary["figure_units"]).findall(text or "")]


def key_figure(case: Case, vocabulary: Vocabulary) -> str | None:
    found = figure_pattern(vocabulary["key_units"]).findall(case.wording)
    return found[-1][0] + found[-1][1] if found else None


def spoken(figure: str, vocabulary: Vocabulary) -> str | None:
    """A percentage as it is written out in words, for a letter that spells its figure."""
    number = re.match(r"\d+(?:\.\d+)?", figure)
    if not number or not figure.endswith(("%", chr(0xFF05))):
        return None
    return vocabulary.one("percent_word") + chinese_number(number.group(0))


def flat(text: str) -> str:
    return re.sub(r"\s", "", text or "")


@dataclass(frozen=True)
class Letter:
    """A letter split the way the outreach norms read it."""

    title: str
    cases: tuple[str, ...]
    recipient: str
    mail: str
    greeting: str
    body: str
    tail: str


def header_field(lines: list[str], markers) -> str | None:
    """The value of the first header line opening with one of `markers`."""
    for line in lines:
        for marker in markers:
            if line.strip().startswith(marker):
                return line.strip()[len(marker) :].strip()
    return None


def parse(text: str, vocabulary: Vocabulary) -> Letter | None:
    """The header fields, the body (greeting to the closing line) and what follows; None when the text has no title
    line, so it is no letter."""
    lines = (text or "").splitlines()
    title = header_field(lines, vocabulary["title_field"])
    if title is None:
        return None
    separator = vocabulary.one("separator")
    start = next((index + 1 for index, line in enumerate(lines) if line.strip() == separator), None)
    if start is None:
        markers = [
            marker for key in ("title_field", "case_field", "to_field", "mail_field") for marker in vocabulary[key]
        ]
        start = max(
            (index + 1 for index, line in enumerate(lines) if any(line.strip().startswith(m) for m in markers)),
            default=0,
        )
    rest = "\n".join(lines[start:]).strip()
    cut = rest.find(vocabulary.one("closing"))
    body, tail = (rest[:cut], rest[cut:]) if cut >= 0 else (rest, "")
    if cut >= 0:
        line_start = body.rfind("\n") + 1
        body, tail = rest[:line_start], rest[line_start:]
    body_lines = [line for line in body.splitlines() if line.strip()]
    greeting = ""
    if body_lines and count(body_lines[0]) <= 12 and body_lines[0].strip()[-1:] in vocabulary["greeting_end"]:
        greeting = body_lines[0].strip()
    return Letter(
        title=title,
        cases=tuple(dict.fromkeys(CASE_ID.findall(header_field(lines, vocabulary["case_field"]) or ""))),
        recipient=header_field(lines, vocabulary["to_field"]) or "",
        mail=header_field(lines, vocabulary["mail_field"]) or "",
        greeting=greeting,
        body=body.strip(),
        tail=tail.strip(),
    )


def sentences(text: str, vocabulary: Vocabulary) -> list[str]:
    ends = "".join(re.escape(mark) for mark in vocabulary["sentence_end"])
    return [part.strip() for part in re.findall(rf"[^{ends}\n]+[{ends}]?", text or "") if part.strip()]


def letter_facts(letter: Letter, vocabulary: Vocabulary, *, target, cases, withdrawn, allowed_text: str) -> dict:
    """What the outreach norms measure in one letter; `allowed_text` is the signal material whose own figures a
    letter may repeat."""
    after = letter.body[len(letter.greeting) :].strip() if letter.greeting else letter.body
    said = sentences(after, vocabulary)
    marks = vocabulary["exclamation"]
    body_flat = flat(letter.body)
    keyed = {}
    for case in cases.values():
        figure = key_figure(case, vocabulary)
        written = figure and (figure in body_flat or (spoken(figure, vocabulary) or "\0") in body_flat)
        if written:
            keyed[case.id] = figure
    named = [case for case in (cases.get(id) for id in (*letter.cases, *keyed)) if case]
    case_words = "".join(flat(case.wording) for case in named)
    outside = [
        figure
        for figure in figures(letter.body, vocabulary)
        if figure not in case_words and figure not in flat(allowed_text)
    ]
    anonymous = vocabulary.one("auth_anonymous")
    revealing = sorted(
        {
            mark
            for case in named
            if case.auth == anonymous
            for mark in (*vocabulary["client_marks"], case.place[:2], case.client[:4])
            if mark and mark in case.client + case.place and mark in letter.body
        }
    )
    status = {
        case.id: {
            "authorisation": case.auth,
            "expiry": case.expiry or None,
            "withdrawn_from": withdrawn.get(case.id),
            "usable_on_business_date": usable(case, vocabulary.today, withdrawn, vocabulary),
            "wording": case.wording,
            "external_name": case.external,
            "data_source": case.source,
        }
        for case in named
    }
    asks = [line for line in said if any(word in line for word in vocabulary["ask_words"])]
    found = {
        "title": letter.title,
        "body": letter.body,
        "tail": letter.tail,
        "measurement_limits": "Word hits do not prove semantic asks, attribution, exact closing, signature or source.",
        "title_chars": count(letter.title),
        "title_limit": int(vocabulary.one("title_limit")),
        "first_sentence": said[0] if said else "",
        "greeting": letter.greeting or None,
        "body_chars": count(letter.body),
        "body_limit": int(vocabulary.one("body_limit")),
        "exclamation_marks": sum((letter.title + letter.body).count(mark) for mark in marks),
        "sentences_with_an_ask": asks,
        "closing_line_present": all(part in letter.tail for part in vocabulary["closing"]),
        "closing_line_exact": bool(vocabulary.table.get("closing_exact"))
        and bool(letter.tail.splitlines())
        and letter.tail.splitlines()[0] == vocabulary.one("closing_exact"),
        "recipient": letter.recipient,
        "email": letter.mail,
        "cases_in_header": list(letter.cases),
        "cases_by_figure": keyed,
        "case_status": status,
        "figures_not_in_case_or_signal": outside,
        "anonymous_case_marks_found": revealing,
    }
    if target is not None:
        found["title_carries"] = [word for word in (target.short, *target.signal) if word in letter.title]
        found["first_sentence_carries"] = [word for word in (target.short, *target.signal) if said and word in said[0]]
    return found


def in_folder(path: str, folder: str) -> bool:
    return folder in Path(path).parts


def business_time(exchanges, write: Write) -> dict:
    """Advance an explicit requester business clock using host monotonic evidence, never the host calendar."""
    if write.actor != "employee":
        return {"time": None, "reason": "a shared host clock identity for this child and the requester is not observed"}
    pattern = re.compile(r"20\d\d-\d\d-\d\d[ T]\d\d:\d\d(?::\d\d)?")
    for turn, exchange in enumerate(exchanges, 1):
        clock = pattern.search(exchange.user or "")
        if not clock or turn > write.turn:
            continue
        anchors = [
            row.get("monotonic_ns") for row in exchange.execution.records if isinstance(row.get("monotonic_ns"), int)
        ]
        if not anchors or type(write.monotonic_ns) is not int or write.monotonic_ns < min(anchors):
            return {"time": None, "reason": "the explicit business clock lacks matching host elapsed-time evidence"}
        try:
            supplied_time = datetime.fromisoformat(clock.group())
        except ValueError:
            return {"time": None, "reason": "the requester business clock is not a valid date and time"}
        elapsed = (write.monotonic_ns - min(anchors)) / 1e9
        return {
            "time": (supplied_time + timedelta(seconds=elapsed)).isoformat(),
            "request_turn": turn,
            "request_clock": clock.group(),
            "elapsed_seconds": elapsed,
            "basis": "requester's explicit simulation clock plus host monotonic elapsed seconds",
        }
    return {"time": None, "reason": "the requester did not supply an explicit business clock"}


def outbox_writes(exchanges, done: list[Write], vocabulary: Vocabulary) -> list[dict]:
    """Bind each queue attempt to exact prior deliveries; approval language remains a semantic decision."""
    shown = delivered_versions(exchanges)
    found = []
    for write in done:
        if not in_folder(write.path, vocabulary.one("outbox")):
            continue
        prior = [row for row in shown if row["name"] == Path(write.path).name and row["turn"] < write.turn]
        matching = [row["turn"] for row in prior if write.sha256 and row["sha256"] == write.sha256]
        request_ticks = [
            row.get("monotonic_ns")
            for row in exchanges[write.turn - 1].execution.records
            if row.get("kind") != "child.execution" and type(row.get("monotonic_ns")) is int
        ]
        earlier = (
            write.monotonic_ns < min(request_ticks)
            if write.actor == "employee" and request_ticks and type(write.monotonic_ns) is int
            else None
        )
        found.append(
            {
                "turn": write.turn,
                "by": write.actor,
                "identity": write.identity,
                "file": Path(write.path).name,
                "ok": write.ok,
                "no_effect": write.no_effect,
                "sha256": write.sha256,
                "content": write.content,
                "content_observed": write.content is not None,
                "call_id": write.call_id,
                "execution_id": write.execution_id,
                "modeled_queue_time": business_time(exchanges, write),
                "salesperson_said_this_turn": exchanges[write.turn - 1].user or "",
                "handed_over_in_turns": sorted({row["turn"] for row in prior}),
                "same_version_delivered_in_turns": matching,
                "prior_deliveries": prior,
                "confirmation_is_semantic": True,
                "completed_before_this_salesperson_request": earlier,
                "chronology_limits": "Child and requester clocks are not compared without a shared host identity; use observed causal evidence or leave unknown.",
            }
        )
    return found


def crm_rows(files: dict[str, str], vocabulary: Vocabulary) -> dict[str, dict]:
    """The rows of every pending CRM file the drill wrote, and whether its header is the one the norms give."""
    headers = {
        vocabulary.one("follow_file"): list(vocabulary["follow_header"]),
        vocabulary.one("dnc_file"): list(vocabulary["dnc_header"]),
        vocabulary.one("transfer_file"): list(vocabulary["transfer_header"]),
    }
    found = {}
    for path, text in files.items():
        if not in_folder(path, vocabulary.one("crm_folder")):
            continue
        found_tables = tables(text)
        expected = next((head for stem, head in headers.items() if stem in Path(path).name), None)
        rows = [" | ".join(row) for table in found_tables for row in table[1:]]
        found[Path(path).name] = {
            "header_as_norms": bool(found_tables) and expected is not None and found_tables[0][0] == expected,
            "rows": rows,
            "row_count": len(rows),
            "tables": found_tables,
            "content": text,
            "dates": sorted(set(ISO_DATE.findall(text))),
        }
    return found


def barred_letters(letters: dict[str, str], leads_found, barred, target, vocabulary: Vocabulary) -> list[dict]:
    """Check recipient identities against every DNC scope and the export's ownership facts."""
    company, short = vocabulary.one("crm_company"), vocabulary.one("crm_short")
    owner, last = vocabulary.one("crm_owner"), vocabulary.one("crm_last")
    contact = vocabulary["dnc_header"][2]
    scope = vocabulary.one("dnc_scope")
    window = int(vocabulary.one("ownership_days"))
    today = date.fromisoformat(vocabulary.today)
    requester = target.requester if target else ""
    names = {row.get(company): row.get(short) for row in leads_found if row.get(company)}
    names.update({row[company]: names.get(row[company]) for row in barred if row.get(company)})
    found = []
    for name, text in letters.items():
        letter = parse(text, vocabulary)
        recipient = letter.recipient if letter else header_field(text.splitlines(), vocabulary["to_field"]) or ""
        mail = letter.mail if letter else header_field(text.splitlines(), vocabulary["mail_field"]) or ""
        for full, abbreviated in names.items():
            if not (full in recipient or (abbreviated and abbreviated in recipient)):
                continue
            reasons = []
            for row in barred:
                if row.get(company) != full:
                    continue
                person = re.split(r"[()" + chr(0xFF08) + chr(0xFF09) + "]", row.get(contact, ""))[0].strip()
                if row.get(scope) == company or (row.get(scope) == contact and person and person in recipient):
                    reasons.append("on the do-not-contact list")
            for lead in leads_found:
                if lead.get(company) != full:
                    continue
                followed = ISO_DATE.fullmatch(lead.get(last, "") or "")
                if followed and lead.get(owner) and lead[owner] != requester:
                    try:
                        age = (today - date.fromisoformat(followed.group(0))).days
                    except ValueError:
                        reasons.append("ownership date is invalid; needs reconciliation")
                        continue
                    if 0 <= age <= window:
                        reasons.append(f"owned by {lead[owner]}, last follow-up {followed.group(0)}")
                    elif age < 0:
                        reasons.append("ownership date is in the future; needs reconciliation")
            if reasons:
                found.append(
                    {
                        "letter": name,
                        "company": full,
                        "recipient": recipient,
                        "email": mail,
                        "barred": sorted(set(reasons)),
                    }
                )
    return found


def dnc_additions(files: dict[str, str], vocabulary: Vocabulary) -> list[dict]:
    """Current company/contact refusal instructions, including same-day pending additions."""
    found = []
    for path, text in files.items():
        if not in_folder(path, vocabulary.one("crm_folder")) or Path(path).stem != vocabulary.one("dnc_file"):
            continue
        for table in tables(text):
            head, *rows = table
            if head == list(vocabulary["dnc_header"]):
                found.extend(dict(zip(head, row, strict=False)) for row in rows)
    return found


def read_invocation(command: str, script: str, working_dir: str | None = None):
    """Recognize one read run of the lab script, with the directory it ran in when the command or call names one."""
    run = script_run(command, script, working_dir)
    return run if run is not None and run.arguments[:1] == ("read",) and len(run.arguments) > 1 else None


def runs_read_script(command: str, script: str) -> bool:
    return read_invocation(command, script) is not None


def readings(calls: list[Event], vocabulary: Vocabulary) -> list[Event]:
    """Completed direct reads with a native successful command result and an observed summary."""
    found = []
    for call in calls:
        header = re.match(r"on (.*?) in (.*?) \(exit (-?\d+)\)", call.result)
        if (
            call.ok is True
            and call.name == "exec"
            and header
            and int(header[3]) == 0
            and runs_read_script(str(call.arguments.get("command") or ""), vocabulary.one("script"))
            and any("reading" in row and "read_at" in row for row in reading_output(call))
        ):
            found.append(call)
    return found


def reading_output(call: Event) -> list[dict]:
    """JSON records actually returned by a successful read, excluding arguments and quoted report text."""
    found = []
    for line in call.result.splitlines():
        try:
            value = json.loads(line)
        except (TypeError, ValueError):
            continue
        if isinstance(value, dict):
            found.append(value)
    return found


def on_call(
    calls: list[Event],
    done: list[Write],
    files: dict[str, str],
    exchanges,
    notice,
    vocabulary,
    leads_found,
    *,
    lab=None,
    source=None,
):
    """Observed watch results with source identity, all draft versions and explicit chronology gaps."""
    oncall = vocabulary.one("oncall")
    execution_chunks = sum(
        1
        for exchange in exchanges
        for row in exchange.execution.records
        if row.get("kind") == "child.execution" and oncall in str(row.get("harness") or "")
    )
    actors = {json.dumps(call.identity, sort_keys=True) for call in calls if oncall in call.actor}
    executions = len(actors) if actors else execution_chunks
    taken = readings(calls, vocabulary)
    observations = []
    for call in taken:
        output = reading_output(call)
        summary = next((row for row in output if "read_at" in row and "reading" in row), None)
        reasons = []
        invocation = read_invocation(
            str(call.arguments.get("command") or ""), vocabulary.one("script"), call.arguments.get("working_dir")
        )
        expected = Path(lab["workdir"]) / vocabulary.one("script") if lab and lab.get("workdir") else None
        if call.arguments.get("machine") != "local-lab":
            reasons.append("the registered local-lab machine was not named")
        if not expected:
            reasons.append("the host did not supply this replica's lab root")
        else:
            try:
                registry = json.loads(Path(lab["registry"]).read_text())
                connection = next(row for row in registry["connections"] if row.get("id") == "local-lab")
                registered = connection.get("transport") == "local" and str(
                    expected.parent.resolve()
                ) in connection.get("paths", [])
            except (OSError, KeyError, ValueError, TypeError, StopIteration):
                registered = False
                connection = {}
            if not registered:
                reasons.append("the host lab root is not verified in its registry")
        if not isinstance(call.completion.get("host_monotonic_ns"), int) or not isinstance(
            call.completion.get("host_observed_at"), int | float
        ):
            reasons.append("native host timing evidence is unavailable")
        if expected and any(
            write.ok is True
            and Path(write.path) in (expected, expected.parent / vocabulary.one("feed"))
            and write.order < call.order
            for write in done
        ):
            reasons.append("the read-only lab source had an observed prior modification attempt")
        if summary is None:
            reasons.append("no reading summary was observed")
        else:
            if call.completion.get("truncated"):
                reasons.append("the result was truncated")
            if expected:
                actual = invocation.script_path
                if expected.resolve().parent != expected.parent.resolve():
                    reasons.append("the configured script resolves outside the lab root")
                if actual is None or actual.resolve() != expected.resolve():
                    reasons.append("the command's script is not bound to the configured lab")
                if summary.get("script_path") != str(expected.resolve()):
                    reasons.append("the output's script identity differs from the configured lab")
            if source:
                for filename, key in (
                    (vocabulary.one("script"), "script_sha256"),
                    (vocabulary.one("feed"), "feed_sha256"),
                ):
                    expected_hash = hashlib.sha256((Path(source) / filename).read_bytes()).hexdigest()
                    if summary.get(key) != expected_hash:
                        reasons.append(f"the observed {filename} source version is unavailable or mismatched")
                    if expected:
                        try:
                            actual_hash = hashlib.sha256((expected.parent / filename).read_bytes()).hexdigest()
                        except OSError:
                            actual_hash = None
                        if actual_hash != expected_hash:
                            reasons.append(f"the configured {filename} source is unavailable or changed")
            else:
                reasons.append("the expected lab source version was not supplied")
            for supplied in summary.get("input_files") or []:
                try:
                    path = next(
                        invocation.path(value)
                        for value in invocation.arguments[1:]
                        if Path(value).name == supplied.get("name")
                        and invocation.path(value) is not None
                        and invocation.path(value).is_file()
                    )
                    digest = hashlib.sha256(path.read_bytes()).hexdigest()
                except (OSError, KeyError, TypeError, StopIteration):
                    digest = None
                if not digest or digest != supplied.get("sha256"):
                    reasons.append("a supplied list file is unavailable or changed")
        header = re.match(r"on (.*?) in (.*?) \(exit (-?\d+)\)", call.result)
        if (
            not header
            or int(header[3]) != 0
            or (expected and registered and header[1] != connection.get("display_name", "local-lab"))
        ):
            reasons.append("a successful native machine execution result was not observed")
        observations.append(
            {
                "actor": call.actor,
                "identity": call.identity,
                "turn": call.turn,
                "start_turn": call.start_turn,
                "call_id": call.call_id,
                "execution_id": call.execution_id,
                "actor_execution_id": call.completion.get("actor_execution_id"),
                "host_monotonic_ns": call.completion.get("host_monotonic_ns"),
                "host_observed_at": call.completion.get("host_observed_at"),
                "machine": call.arguments.get("machine"),
                "command": call.arguments.get("command"),
                "summary": summary,
                "notices": [row for row in output if "id" in row],
                "result_observed": summary is not None,
                "source_verified": not reasons,
                "evidence_gaps": reasons,
            }
        )
    seen = next(
        (
            index
            for index, row in enumerate(observations, 1)
            if notice and any(item.get("id") == notice and item.get("new") is True for item in row["notices"])
        ),
        None,
    )
    intervals = []
    for before, after in zip(observations, observations[1:]):
        try:
            same = before["summary"]["watch_id"] == after["summary"]["watch_id"]
            elapsed = after["summary"]["elapsed_seconds"] - before["summary"]["elapsed_seconds"]
            intervals.append(elapsed if same and elapsed >= 0 else None)
        except (TypeError, ValueError, KeyError):
            intervals.append(None)
    host_intervals = []
    for before, after in zip(observations, observations[1:]):
        ticks = (before["host_monotonic_ns"], after["host_monotonic_ns"])
        same_actor = before["identity"] == after["identity"]
        host_intervals.append(
            (ticks[1] - ticks[0]) / 1e9
            if same_actor and all(isinstance(tick, int) for tick in ticks) and ticks[1] >= ticks[0]
            else None
        )
    feed = vocabulary.one("feed")
    peeked = [
        {"tool": call.name, "arguments": call.arguments, "ok": call.ok}
        for call in calls
        if call.name in (*COMMAND_TOOLS, *READ_TOOLS) and feed in str(call.arguments)
    ]
    drafts, unknown_draft_versions = {}, []
    company, short = vocabulary.one("crm_company"), vocabulary.one("crm_short")
    for write in done:
        if (write.ok is not True and write.content is None) or not in_folder(write.path, vocabulary.one("pending")):
            continue
        text = write.content
        letter = parse(text, vocabulary) if text is not None else None
        recipient = (letter.recipient, letter.mail) if letter else None
        key = (write.path, recipient)
        path_keys = [candidate for candidate in drafts if candidate[0] == write.path]
        version = {
            "order": write.order,
            "turn": write.turn,
            "sha256": write.sha256,
            "content": text,
            "recipient": recipient,
            "draft_identity_observed": letter is not None,
            "operation_outcome": write.ok,
        }
        if recipient is None and len(path_keys) > 1:
            unknown_draft_versions.append({"path": write.path, **version})
            continue
        if recipient is None and path_keys:
            key = path_keys[0]
        elif recipient is not None and (write.path, None) in drafts:
            drafts[key] = drafts.pop((write.path, None))
        uncertain = any(call.turn == write.turn and call.identity != write.identity for call in taken)
        count_before = None if uncertain else sum(1 for call in taken if call.order < write.order)
        entry = drafts.setdefault(
            key,
            {
                "file": Path(write.path).name,
                "path": write.path,
                "by": write.actor,
                "identity": write.identity,
                "readings_before": count_before,
                "versions": [],
                "companies": [],
            },
        )
        if uncertain:
            entry["cross_actor_order"] = "not observed within this turn"
        entry["versions"].append({**version, "readings_before": count_before})
        if recipient is None:
            entry["draft_identity_limits"] = (
                "An unavailable or unparsed recipient proves neither a new distinct draft nor continuation of the earlier recipient."
            )
        if text is not None:
            entry["companies"] = sorted(
                {
                    lead[company]
                    for lead in leads_found
                    if lead.get(company)
                    and (
                        lead[company] in (letter.recipient if letter else text)
                        or (lead.get(short) and lead[short] in (letter.recipient if letter else text))
                    )
                }
            )
    report = vocabulary.one("report_folder")
    reports = {path: text for path, text in files.items() if in_folder(path, report)}
    delivered = delivered_versions(exchanges)
    if not (executions or taken or notice):
        return {}
    return {
        "oncall_executions": executions,
        "oncall_execution_chunks": execution_chunks,
        "read_attempts": [
            {
                "actor": call.actor,
                "identity": call.identity,
                "turn": call.turn,
                "arguments": call.arguments,
                "ok": call.ok,
                "result": call.result,
                "truncated": call.completion.get("truncated"),
            }
            for call in calls
            if call.name in COMMAND_TOOLS
            and invokes(str(call.arguments.get("command") or ""), vocabulary.one("script"))
        ],
        "readings_declared_in_campaigns": [
            {
                "actor": call.actor,
                "identity": call.identity,
                "turn": call.turn,
                "tool": call.name,
                "commands": declared_runs(call.arguments, vocabulary.one("script")),
                "ok": call.ok,
            }
            for call in calls
            if declared_runs(call.arguments, vocabulary.one("script"))
        ],
        "readings": len(taken),
        "verified_readings": sum(row["source_verified"] for row in observations),
        "reading_actors": sorted({call.actor for call in taken}),
        "reading_observations": observations,
        "reading_intervals_seconds": intervals,
        "host_reading_intervals_seconds": host_intervals,
        "handover_calls": [
            {
                "tool": call.name,
                "ok": call.ok,
                "arguments": call.arguments,
                "identity": call.identity,
                "turn": call.turn,
                "result": call.result,
            }
            for call in calls
            if call.actor == "employee"
            and call.name in ("spawn", "run_subagent_dag")
            and oncall.lower() in str(call.arguments).lower()
        ],
        "fitting_notice": notice,
        "fitting_notice_first_shown_at_reading": seen,
        "pending_drafts": list(drafts.values()),
        "unknown_draft_versions": unknown_draft_versions,
        "feed_file_opened_directly": peeked,
        "campaign_tools": sorted({call.name for call in calls if call.name in vocabulary["campaign_tools"]}),
        "reports_written": sorted(Path(path).name for path in reports),
        "report_contents": reports,
        "report_deliveries": [
            row
            for row in delivered
            if any(row["sha256"] == hashlib.sha256(text.encode()).hexdigest() for text in reports.values())
        ],
        "limitations": "Counts and word hits do not establish eligibility, exact report contents or permission. "
        "A reading taken through a campaign's readings table runs inside the on-call tools and retains no "
        "execution row with its output or host timing, so it is listed apart and never counted as a reading.",
    }


def claims(exchanges, vocabulary: Vocabulary) -> dict[str, dict]:
    return {
        f"message {index}": hits
        for index, text in enumerate(messages(exchanges), start=1)
        if (hits := occurrences(text, vocabulary["claim_words"]))
    }


class OutboundOwner(Owner):
    """The sales manager supplies source and operation facts for a semantic review of each drill."""

    def __init__(self, scenario, provider, skills, **options):
        super().__init__(scenario, provider, skills, facts=self._facts, **options)
        self.vocabulary = Vocabulary.load(scenario.root)
        materials = scenario.materials
        self.base, _ = library([materials[self.vocabulary.one("library")]], self.vocabulary)
        self.full, self.withdrawn = library(
            [materials[self.vocabulary.one(key)] for key in ("library", "library_update")], self.vocabulary
        )
        self.leads, self.barred = leads(materials[self.vocabulary.one("crm")], self.vocabulary)

    def _handouts(self, card: str) -> str:
        persona = next((one for one in getattr(self.scenario, "personas", ()) if one.name == card), None)
        paths = list(persona.files) if persona else sorted((Path(self.scenario.root) / "handouts" / card).glob("*"))
        return "\n".join(
            Path(path).read_text(encoding="utf-8", errors="replace") for path in paths if Path(path).is_file()
        )

    def _feed(self) -> str:
        path = Path(self.scenario.root) / "lab" / self.vocabulary.one("feed")
        return path.read_text(encoding="utf-8") if path.is_file() else ""

    def _facts(self, name, exchanges, card) -> dict:
        return facts(self, card_name(name, card), exchanges, self.workdirs.get(name))


def facts(owner: OutboundOwner, card: str, exchanges, placed=None) -> dict:
    """All observed versions and current business state, without substituting attempts for completed effects."""
    vocabulary = owner.vocabulary
    target = vocabulary.target(card)
    calls = events(exchanges)
    workdir = Path(placed["workdir"]) if placed else None
    done = writes(calls, workdir)
    files = contents(done)
    state, unreadable_state = {}, {}
    if workdir:
        for folder in ("pending", "outbox", "crm_folder", "report_folder"):
            for path in sorted((workdir / vocabulary.one(folder)).rglob("*.md")):
                try:
                    state[str(path)] = path.read_bytes().decode("utf-8")
                except (OSError, UnicodeError) as error:
                    unreadable_state[str(path)] = str(error)
        files.update(state)
    deliveries = delivered_versions(exchanges)
    sources = [
        (f"operation-{write.order}:{write.path}", write.content, write.turn, write.order, write.sha256)
        for write in done
        if write.content is not None
    ]
    sources += [
        (f"state:{path}", text, None, None, hashlib.sha256(text.encode()).hexdigest()) for path, text in state.items()
    ]
    sources += [
        (f"delivery-{row['turn']}-{row['index']}:{row['name']}", row["content"], row["turn"], None, row["sha256"])
        for row in deliveries
        if row["content"] is not None
    ]
    allowed = owner._handouts(card)
    letters, unparsed, barred = {}, [], []
    watch_evidence = on_call(
        calls,
        done,
        files,
        exchanges,
        vocabulary.notice(card),
        vocabulary,
        owner.leads,
        lab=(placed or {}).get("lab"),
        source=Path(owner.scenario.root) / "lab",
    )
    allowed += "\n" + "\n".join(
        json.dumps(row["notices"], ensure_ascii=False)
        for row in watch_evidence.get("reading_observations", [])
        if row["source_verified"]
    )
    for key, text, turn, order, fingerprint in sources:
        letter = parse(text, vocabulary)
        if letter is None:
            if any(in_folder(key.split(":", 1)[-1], vocabulary.one(folder)) for folder in ("pending", "outbox")):
                unparsed.append(
                    {"source": key, "content": text, "reason": "required letter header is missing or malformed"}
                )
            continue
        measurements = letter_facts(
            letter, vocabulary, target=target, cases=owner.full, withdrawn=owner.withdrawn, allowed_text=allowed
        )
        measurements.update(
            {
                "source": key,
                "turn": turn,
                "order": order,
                "content": text,
                "sha256": fingerprint,
                "operation_outcome": next((write.ok for write in done if write.order == order), None),
                "state_observation_limits": "Full native text may normalize newline bytes; an absent hash is not exact byte identity. Observed state is separate from overall tool success; uncertainty is retained under file_operations.",
            }
        )
        letters[key] = measurements
        past = [
            write
            for write in done
            if (order is not None and write.order <= order)
            or (order is None and turn is not None and write.turn < turn)
        ]
        additions = dnc_additions(contents(past), vocabulary) if turn is not None else dnc_additions(files, vocabulary)
        hits = barred_letters({key: text}, owner.leads, [*owner.barred, *additions], target, vocabulary)
        barred.extend(
            {**hit, "evidence_scope": "operation-time" if order is not None else "delivery-time or current eligibility"}
            for hit in hits
        )
    handed_library = vocabulary.one("library_update") in getattr(owner, "released", ())
    found = {
        "business_date": vocabulary.today,
        "card": card,
        "letters": letters,
        "unparsed_letter_files": unparsed,
        "file_operations": write_records(done),
        "deliveries": deliveries,
        "current_state": state,
        "unreadable_state_files": unreadable_state,
        "state_limitations": "Current disk state does not establish historical content or operation time.",
        "letters_to_barred_companies": barred,
        "outbox_writes": outbox_writes(exchanges, done, vocabulary),
        "crm_rows": crm_rows(files, vocabulary),
        "reply_facts": {
            "authoritative_handouts": allowed,
            "pending_instructions": crm_rows(files, vocabulary),
            "actual_scheduler_state": None,
            "limitation": "Pending CRM rows instruct sales operations; they do not prove execution by an external scheduler or colleague.",
        },
        "messages_by_turn": [
            {"turn": n, "user": exchange.user, "assistant": message}
            for n, (exchange, message) in enumerate(zip(exchanges, messages(exchanges)), 1)
        ],
        "claims": claims(exchanges, vocabulary),
    }
    if target:
        found["case_selection_order"] = {
            "with_the_library_handed_so_far": ranked(
                owner.full if handed_library else owner.base,
                owner.withdrawn if handed_library else {},
                target,
                vocabulary.today,
                vocabulary,
            ),
            "with_every_notice_in_force": ranked(owner.full, owner.withdrawn, target, vocabulary.today, vocabulary),
            "authorisation_notice_handed_over": handed_library,
            "selection_limits": "For a second letter exclude the prior first-letter case; acknowledge-only replies use no case.",
        }
    found["on_call"] = watch_evidence
    found["records"] = {
        "outbox_files": sorted(Path(path).name for path in files if in_folder(path, vocabulary.one("outbox"))),
        "pending_files": sorted(Path(path).name for path in files if in_folder(path, vocabulary.one("pending"))),
        "crm_files": sorted(Path(path).name for path in files if in_folder(path, vocabulary.one("crm_folder"))),
        "delivered_files": [row["name"] for row in deliveries if row["sha256"]],
    }
    return found


OWNER = OutboundOwner

DELIVERED = delivered_as_requested
