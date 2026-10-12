"""Measure NDA drill evidence without promoting search hits or attempted actions to judgments.

Retained deliveries keep their turn and content identity. Issue and change tables remain separate, live legal files
are compared with the pre-drill baseline, and tool outcomes retain their actor and execution scope. The owner reads
complete contextual evidence and still decides the semantic criteria.
"""

import hashlib
import re
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

from experimental.cultivation.counterpart.owner import Owner
from experimental.cultivation.counterpart.rulers import CONFIG, messages, tables, words
from experimental.harness.participation.files import read_delivered
from experimental.harness.raven_adapter.action.runtime import REFUSED
from experimental.harness.scenario.contract import load
from experimental.simulation.cases.nda_triage_team.delivery import (
    actual_clauses,
    canonical,
    changed_clause_details,
    delivered,
)

WRITES = ("write_file", "edit_file")
CLAUSE = re.compile(r"\d+(?:\.\d+)*(?:\s*\([a-z0-9]{1,3}\))*", re.I)
LABEL = re.compile(r"(?i)\b(?:sections?|clauses?|articles?|art|sec)\b\.?|" + re.escape(chr(0xA7)))
FIELD = re.compile(r"^\s*([a-z][a-z ]*):\s*(.*)$")
VERSION = re.compile(r"(?<![\w.])V\d+(?:\.\d+)+(?![\w.])", re.I)
HAN = re.compile(r"[\u3400-\u9fff]")


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@dataclass(frozen=True)
class Vocabulary:
    """Case words and exact source schemas; membership aliases are exact names, never substring identities."""

    colours: tuple[str, ...]
    version: str
    superseded: tuple[str, ...]
    internal_marks: tuple[str, ...]
    internal_notices: tuple[str, ...]
    clause_header: str
    issue_columns: tuple[str, ...]
    change_columns: tuple[str, ...]
    register_columns: tuple[str, ...]
    pending_columns: tuple[str, ...]
    register: str
    notes_folder: str
    archives: tuple[str, ...]
    director_only: tuple[str, ...]
    signers: tuple[str, ...]
    signer_aliases: tuple[str, ...]
    sign_claims: tuple[str, ...]
    negations: tuple[str, ...]
    contract_desk: tuple[str, ...]
    other_desks: tuple[str, ...]
    external_mark: str
    external_prefix: str
    external_intent: tuple[str, ...]
    internal_words: tuple[str, ...]
    external_internal_english: tuple[str, ...]
    row_prefix: str
    pending_prefix: str
    memo_prefix: str
    basis_labels: tuple[str, ...]
    counterpart_labels: tuple[str, ...]
    handler_labels: tuple[str, ...]
    playbook_titles: tuple[str, ...]
    uncovered_basis: tuple[str, ...]
    resolved_labels: tuple[str, ...]
    new_issue_labels: tuple[str, ...]
    problem_labels: tuple[str, ...]
    checked_labels: tuple[str, ...]
    none_labels: tuple[str, ...]
    clause_labels: dict[str, set[str]]
    changed_clause_details: dict[str, dict[str, set[str]]]
    section_labels: dict[str, tuple[str, ...]]
    known_rows: frozenset[str] = frozenset()

    @classmethod
    def load(cls, scenario) -> "Vocabulary":
        root = Path(scenario.root)
        found = words(root / CONFIG)
        known = frozenset(
            row
            for path in sorted((root / "materials" / found["register_material"][0]).rglob("*.md"))
            for row in table_rows(path.read_text())
            if row.startswith(("|" + found["row_prefix"][0], "|" + found["pending_prefix"][0]))
        )
        return cls(
            colours=found["colours"],
            version=found["version"][0],
            superseded=found["superseded"],
            internal_marks=found["internal_mark"],
            internal_notices=found["internal_notices"],
            clause_header=found["clause_header"][0],
            issue_columns=found["issue_columns"],
            change_columns=found["change_columns"],
            register_columns=found["register_columns"],
            pending_columns=found["pending_columns"],
            register=found["register"][0],
            notes_folder=found["notes_folder"][0],
            archives=found["archives"],
            director_only=found["director_only"],
            signers=found["signers"],
            signer_aliases=found["signer_aliases"],
            sign_claims=found["sign_claims"],
            negations=found["negations"],
            contract_desk=found["contract_members"],
            other_desks=found["other_members"],
            external_mark=found["external_mark"][0],
            external_prefix=found["external_prefix"][0],
            external_intent=found["external_intent"],
            internal_words=found["internal_words"],
            external_internal_english=found["external_internal_english"],
            row_prefix=found["row_prefix"][0],
            pending_prefix=found["pending_prefix"][0],
            memo_prefix=found["memo_prefix"][0],
            basis_labels=found["basis_labels"],
            counterpart_labels=found["counterpart_labels"],
            handler_labels=found["handler_labels"],
            playbook_titles=found["playbook_titles"],
            uncovered_basis=found["uncovered_basis"],
            resolved_labels=found["resolved_labels"],
            new_issue_labels=found["new_issue_labels"],
            problem_labels=found["problem_labels"],
            checked_labels=found["checked_labels"],
            none_labels=found["none_labels"],
            clause_labels={
                case.id: actual_clauses(root, case, expected_of(case)) for case in load(root).situation.cases
            },
            changed_clause_details={
                case.id: changed_clause_details(root, case, expected_of(case)) for case in load(root).situation.cases
            },
            section_labels={
                key: found[label]
                for key, label in (
                    ("conclusion", "conclusion_labels"),
                    ("background", "background_labels"),
                    ("next", "next_labels"),
                    ("record", "record_labels"),
                )
            },
            known_rows=known,
        )

    @property
    def internal_mark(self) -> str:
        return self.internal_marks[0]


def squeeze(line: str) -> str:
    return re.sub(r"\s+", "", line)


def table_rows(text: str) -> list[str]:
    return [squeeze("|" + "|".join(row) + "|") for table in tables(text or "") for row in table]


def clause_numbers(cell: str) -> list[str]:
    """Normalise counterparty Section/Article labels without treating page labels as clause evidence."""
    if re.search(r"(?i)\bpages?\b", str(cell or "")):
        return []
    text = LABEL.sub(" ", str(cell or "")).replace(chr(0x7B2C), " ").replace(chr(0x6761), " ")
    return [re.sub(r"\s+", "", match.group()).lower() for match in CLAUSE.finditer(text)]


def same_clause(one: str, other: str) -> bool:
    return clause_numbers(one) == clause_numbers(other) and bool(clause_numbers(one))


def clause_covered(expected: str, cited) -> bool:
    return any(
        number == expected or number.startswith(expected + ".") or number.startswith(expected + "(") for number in cited
    )


def cell_label(cell: str) -> str:
    return squeeze(cell.strip().strip("*`_"))


def rows_for(text: str, columns: tuple[str, ...]) -> list[list[str]]:
    wanted = tuple(cell_label(cell) for cell in columns)
    return [
        row
        for table in tables(text or "")
        if table and tuple(cell_label(cell) for cell in table[0]) == wanted
        for row in table[1:]
    ]


def issue_rows(text: str, vocabulary: Vocabulary) -> list[list[str]]:
    return rows_for(text, vocabulary.issue_columns)


def change_rows(text: str, vocabulary: Vocabulary) -> list[list[str]]:
    return rows_for(text, vocabulary.change_columns)


def cited_clauses(text: str, vocabulary: Vocabulary) -> list[str]:
    return list(
        dict.fromkeys(
            number for row in issue_rows(text, vocabulary) for number in clause_numbers(row[0] if row else "")
        )
    )


def first_line(text: str) -> str:
    lines = (text or "").splitlines()
    return lines[0] if lines else ""


def colour_of(line: str, vocabulary: Vocabulary) -> str | None:
    bare = line.strip().strip("#*>`_ \t").strip()
    return bare if bare in vocabulary.colours else None


def is_memo(text: str, vocabulary: Vocabulary) -> bool:
    return (
        colour_of(first_line(text), vocabulary) is not None
        or any(mark in (text or "") for mark in vocabulary.internal_marks)
        or bool(issue_rows(text, vocabulary))
    )


def header(text: str) -> str:
    lines = text.splitlines()[1:]
    out = []
    for line in lines:
        if not line.strip():
            break
        out.append(line)
    return "\n".join(out)


def field_lines(text: str, labels: tuple[str, ...]) -> list[str]:
    pattern = re.compile(
        r"^\s*(?:[-*]\s*)?(?:\*\*)?(?:"
        + "|".join(re.escape(label) for label in labels)
        + r")(?:\*\*)?\s*[:"
        + chr(0xFF1A)
        + r"]",
        re.I,
    )
    return [line for line in text.splitlines() if pattern.search(line)]


def body_sections(text: str, vocabulary: Vocabulary) -> dict[str, list[str]]:
    return {name: field_lines(text, labels) for name, labels in vocabulary.section_labels.items()}


def memo_facts(text: str, vocabulary: Vocabulary) -> dict:
    """Keep raw lines, exact table roles and the actual header basis; no field asserts semantic correctness."""
    lines = text.splitlines()
    line = first_line(text)
    colour = colour_of(line, vocabulary)
    head = header(text)
    basis = field_lines(head, vocabulary.basis_labels)
    policy_versions = []
    for item in basis:
        for title in vocabulary.playbook_titles:
            match = re.search(re.escape(title) + r"\s*(V\d+(?:\.\d+)+)(?![\w.])", item, re.I)
            if match:
                policy_versions.append(match.group(1).upper())
    return {
        "first_line": line,
        "colour": colour,
        "first_line_is_only_the_colour": line in vocabulary.colours,
        "second_line": lines[1] if len(lines) > 1 else "",
        "internal_mark": len(lines) > 1 and lines[1] in vocabulary.internal_notices,
        "header": head,
        "basis_lines": basis,
        "playbook_version_in_force_named": bool(policy_versions) and set(policy_versions) == {vocabulary.version},
        "superseded_versions_named": [version for version in vocabulary.superseded if version in policy_versions],
        "policy_versions_in_basis": policy_versions,
        "header_counterparty_lines": field_lines(head, vocabulary.counterpart_labels),
        "header_handler_lines": field_lines(head, vocabulary.handler_labels),
        "sections": body_sections(text, vocabulary),
        "no_issues_lines": field_lines(text, vocabulary.problem_labels),
        "checked_lines": field_lines(text, vocabulary.checked_labels),
        "issue_rows": issue_rows(text, vocabulary),
        "change_rows": change_rows(text, vocabulary),
        "cited_clauses": cited_clauses(text, vocabulary),
        "change_clauses": list(
            dict.fromkeys(
                number for row in change_rows(text, vocabulary) for number in clause_numbers(row[0] if row else "")
            )
        ),
        "measurement_scope": "Exact formatting and citations only; assess every row's substantive content separately.",
    }


def expected_of(card) -> dict[str, str]:
    fields = {}
    for line in (getattr(card, "expected", None) or "").splitlines():
        match = FIELD.match(line)
        if match:
            fields[match.group(1).strip()] = match.group(2).strip()
    return fields


def listed(value: str | None) -> list[str]:
    return (
        []
        if not value or value.strip().lower().startswith("none")
        else [number for part in value.split(",") for number in clause_numbers(part)]
    )


def comparison_check(changed, cited, *, details=None) -> dict:
    """A source-group citation covers its change; precise citations must cover every verified changed leaf."""
    required = {number: set((details or {}).get(number) or {number}) for number in changed}
    accepted = {number for parent, leaves in required.items() for number in (parent, *leaves)}
    missing = {parent: sorted(leaves - set(cited)) for parent, leaves in required.items() if parent not in cited}
    return {
        "change_details": {parent: sorted(leaves) for parent, leaves in required.items()},
        "changed_not_cited": [parent for parent in changed if missing.get(parent)],
        "changed_details_not_cited": [number for leaves in missing.values() for number in leaves],
        "outside_changed_scope": [number for number in cited if number not in accepted],
    }


def expected_check(memos: dict[str, dict], card, *, allowed=(), change_details=None) -> dict:
    """Compare each retained memo independently; change citations cannot supply missing issue rows."""
    fields = expected_of(card)
    if "verdict" not in fields:
        return {}
    issues, changed = listed(fields.get("issues")), listed(fields.get("changed"))
    per_memo = {}
    for name, measured in memos.items():
        cited, compared = measured["cited_clauses"], measured["change_clauses"]
        valid_cited = [number for number in cited if number in issues or number in allowed]
        one = {
            "verdict": fields["verdict"],
            "memo_colours": [measured["colour"] or measured["first_line"]],
            "issues": issues,
            "cited": cited,
            "missing": [number for number in issues if not clause_covered(number, valid_cited)],
            "invalid_clause_labels": [number for number in cited if number not in valid_cited],
            "extra": [number for number in cited if not any(clause_covered(issue, [number]) for issue in issues)],
        }
        if changed:
            coverage = comparison_check(changed, compared, details=change_details)
            outside = comparison_check(changed, [*cited, *compared], details=change_details)["outside_changed_scope"]
            overbroad = [number for number in outside if any(clause_covered(number, [change]) for change in changed)]
            one.update(
                changed=changed,
                **{key: value for key, value in coverage.items() if key != "outside_changed_scope"},
                cited_unchanged=[number for number in outside if number in allowed and number not in overbroad],
                invalid_change_clause_labels=[number for number in outside if number not in allowed],
                overbroad_change_clause_labels=overbroad,
            )
        per_memo[name] = one
    if len(per_memo) == 1:
        return next(iter(per_memo.values()))
    return {"verdict": fields["verdict"], "issues": issues, "per_memo": per_memo, "memo_available": bool(per_memo)}


def records_of(rows):
    for row in rows or ():
        if not isinstance(row, dict):
            continue
        yield row
        if row.get("kind") == "child.execution":
            yield from records_of(row.get("records"))


def scoped_records(rows, actor="desk"):
    for index, row in enumerate(rows or ()):
        if not isinstance(row, dict):
            continue
        yield actor, row
        if row.get("kind") == "child.execution":
            identity = f"{row.get('harness', 'unknown')}:{row.get('launch', '')}:{row.get('pid', '')}"
            child = f"{actor}/{identity}" if row.get("launch") and row.get("pid") else f"{actor}/{identity}:{index}"
            yield from scoped_records(row.get("records"), child)


def calls(exchanges) -> list[dict]:
    """Pair outcomes by turn, actor and occurrence; preserve unknown success and recorded timestamps."""
    made = []
    for number, turn in enumerate(exchanges, 1):
        pending = defaultdict(deque)
        for actor, row in scoped_records(turn.execution.records):
            event = row.get("event") or {}
            if row.get("kind") != "runner.event" or row.get("event_type", "ToolEvent") != "ToolEvent":
                continue
            key = (actor, row.get("turn_id") or turn.execution.turn_id, event.get("tool_call_id"))
            if event.get("phase") == "start" and event.get("name"):
                pending[key].append(len(made))
                made.append(
                    {
                        "name": event["name"],
                        "arguments": event.get("arguments") or {},
                        "ok": None,
                        "turn": number,
                        "execution_id": turn.execution.turn_id,
                        "actor": actor,
                        "tool_call_id": event.get("tool_call_id"),
                        "started_at": row.get("time") or event.get("timestamp"),
                        "completed_at": None,
                    }
                )
            elif event.get("phase") == "complete" and event.get("tool_call_id") and pending[key]:
                call = made[pending[key].popleft()]
                outcome = event.get("ok")
                refused = str(event.get("result_preview") or "").startswith(REFUSED)
                call.update(
                    ok=False if refused else outcome if isinstance(outcome, bool) else None,
                    completed_at=row.get("time") or event.get("timestamp"),
                    result_preview=event.get("result_preview"),
                    metadata=event.get("metadata") or {},
                )
    return made


def relative_path(path: str, workdir: Path | None) -> str | None:
    """A resolved path inside the trusted workdir; an unknown absolute workdir never gains provenance."""
    raw = Path(str(path))
    if workdir is None:
        if raw.is_absolute() or ".." in raw.parts:
            return None
        return raw.as_posix()
    root = Path(workdir).resolve()
    target = (raw if raw.is_absolute() else root / raw).resolve()
    return target.relative_to(root).as_posix() if target.is_relative_to(root) else None


def written(arguments: dict) -> str:
    return str(arguments.get("content") or arguments.get("new_text") or arguments.get("new_string") or "")


def added_rows(text: str, known: frozenset[str]) -> list[str]:
    return [row for row in table_rows(text) if row not in known]


def register_facts(
    exchanges, vocabulary: Vocabulary, live: str | None = None, base: str | None = None, *, workdir=None
) -> dict:
    """Full structured live rows and their baseline changes; write arguments remain a separate weaker channel."""
    known = frozenset(table_rows(base)) if base else vocabulary.known_rows
    writes = []
    for call in calls(exchanges):
        raw = str(call["arguments"].get("path") or "")
        if call["name"] not in WRITES or Path(vocabulary.register).name not in raw:
            continue
        path = relative_path(raw, workdir) if call["actor"] == "desk" or Path(raw).is_absolute() else None
        writes.append(
            {
                **{
                    key: call[key]
                    for key in ("name", "ok", "turn", "execution_id", "actor", "started_at", "completed_at")
                },
                "path": raw,
                "resolved_relative_path": path,
                "live_register": path == vocabulary.register if path is not None else None,
                "path_resolution": "resolved against trusted desk workdir"
                if path is not None
                else "unknown actor workdir or outside trusted workdir",
                "write_arguments": written(call["arguments"]),
            }
        )
    found = {"writes": writes} if writes else {}
    if live is None:
        return found
    main = rows_for(live, vocabulary.register_columns)
    pending = rows_for(live, vocabulary.pending_columns)
    structured = []
    for kind, columns, rows in (
        ("nda", vocabulary.register_columns, main),
        ("pending", vocabulary.pending_columns, pending),
    ):
        for cells in rows:
            raw = squeeze("|" + "|".join(cells) + "|")
            if raw not in known:
                structured.append(
                    {
                        "table": kind,
                        "cells": cells,
                        "columns": list(columns),
                        "column_count_matches": len(cells) == len(columns),
                        "raw": raw,
                    }
                )
    current = set(table_rows(live))
    found.update(
        rows_added=[row["raw"] for row in structured],
        pending_rows_added=[row["raw"] for row in structured if row["table"] == "pending"],
        structured_rows_added=structured,
        history_rows_missing=sorted(
            row
            for row in known
            if row.startswith(("|" + vocabulary.row_prefix, "|" + vocabulary.pending_prefix)) and row not in current
        ),
        text=live,
        sha256=sha(live),
        baseline_sha256=sha(base) if base is not None else None,
        schemas_present={
            "nda": any(
                tuple(cell_label(cell) for cell in table[0])
                == tuple(cell_label(cell) for cell in vocabulary.register_columns)
                for table in tables(live)
                if table
            ),
            "pending": any(
                tuple(cell_label(cell) for cell in table[0])
                == tuple(cell_label(cell) for cell in vocabulary.pending_columns)
                for table in tables(live)
                if table
            ),
        },
    )
    return found


def registration_number(vocabulary: Vocabulary, card, base: str | None) -> str:
    returned = expected_of(card).get("register", "")
    if "keeping the number" in returned:
        match = re.search(re.escape(vocabulary.row_prefix) + r"\d+", returned)
        if match:
            return match.group()
    snapshot_rows = ["|" + "|".join(row) + "|" for row in rows_for(base or "", vocabulary.register_columns)]
    source = snapshot_rows or [
        *vocabulary.known_rows,
        *("|" + "|".join(row) + "|" for row in rows_for(base or "", vocabulary.register_columns)),
    ]
    source = [squeeze(row) for row in source]
    numbers = [
        int(match.group(1))
        for row in source
        if (match := re.match(r"\|" + re.escape(vocabulary.row_prefix) + r"(\d+)\|", row))
    ]
    return f"{vocabulary.row_prefix}{max(numbers, default=0) + 1:03d}"


def escalation_notes(
    exchanges, vocabulary: Vocabulary, notes: dict[str, str] | None = None, *, base_notes=None, workdir=None
) -> dict[str, str]:
    """Only new or changed canonical live notes; tool-only attempts do not establish a retained note."""
    if notes is None:
        return {}
    before = base_notes or {}
    return {
        path: text
        for path, text in notes.items()
        if relative_path(path, workdir) == path
        and Path(path).parent.as_posix() == vocabulary.notes_folder
        and before.get(path) != text
    }


def desk_of(label: str, vocabulary: Vocabulary) -> str:
    name = label.strip().casefold()
    if name in {word.casefold() for word in vocabulary.other_desks}:
        return "other"
    if name in {word.casefold() for word in vocabulary.contract_desk}:
        return "contract"
    return "unclear"


def delegations(exchanges, vocabulary: Vocabulary) -> list[dict]:
    found = []
    executed = child_executions(exchanges)
    for call in calls(exchanges):
        arguments = call["arguments"]
        if call["name"] == "spawn":
            items = [(arguments.get("subagent"), arguments.get("node_id"), arguments.get("task_summary"))]
        elif call["name"] == "run_subagent_dag":
            items = [
                (node.get("subagent"), node.get("id"), node.get("node_summary"))
                for node in arguments.get("nodes") or []
                if isinstance(node, dict)
            ]
        else:
            continue
        for target, node, summary in items:
            matching = [
                child
                for child in executed
                if child["turn"] == call["turn"]
                and str(child.get("harness") or "").casefold() == str(target or "").casefold()
                and any(
                    str(instance.get("agent") or "").casefold() == str(target or "").casefold()
                    and str(instance.get("nodeId") or instance.get("node_id") or "") == str(node or "")
                    for instance in child.get("instances") or []
                    if isinstance(instance, dict)
                )
            ]
            found.append(
                {
                    "tool": call["name"],
                    "target": target,
                    "node": node,
                    "summary": str(summary or ""),
                    "desk": desk_of(str(target or ""), vocabulary),
                    "ok": call["ok"],
                    "accepted": call["ok"] is True,
                    "child_execution_matches": matching,
                    "execution_verified": any(child.get("records") for child in matching) and call["ok"] is True,
                    "actor": call["actor"],
                    "execution_id": call["execution_id"],
                    "turn": call["turn"],
                    "tool_call_id": call["tool_call_id"],
                    "result_preview": call.get("result_preview"),
                    "result_metadata": call.get("metadata", {}),
                    "identity_scope": "Exact target alias; inspect child instance/run and returned result for actual membership and performance.",
                }
            )
    return found


def child_executions(exchanges) -> list[dict]:
    return [
        {
            "turn": number,
            "parent_execution_id": turn.execution.turn_id,
            **{
                key: row.get(key) for key in ("harness", "revision", "launch", "pid", "instances", "omitted", "records")
            },
        }
        for number, turn in enumerate(exchanges, 1)
        for row in records_of(turn.execution.records)
        if row.get("kind") == "child.execution"
    ]


def context_hits(text: str, terms) -> dict[str, list[str]]:
    return {term: [line for line in text.splitlines() if term in line] for term in terms if term in text}


def facts(
    exchanges,
    vocabulary: Vocabulary,
    card=None,
    *,
    live=None,
    base=None,
    notes=None,
    base_notes=None,
    observed=False,
    workdir=None,
    observation=None,
    filed=None,
    archives=None,
    archive_observation=None,
) -> dict:
    """Facts retain complete source context, provenance and uncertainty; every criterion remains semantic."""
    found, files, memos, unavailable = {}, {}, {}, {}
    reused = {
        str(path): (number, ordinal)
        for number, turn in enumerate(exchanges, 1)
        for ordinal, path in enumerate(turn.execution.deliverables, 1)
    }
    for number, turn in enumerate(exchanges, 1):
        for ordinal, path in enumerate(turn.execution.deliverables, 1):
            key = f"turn {number} delivery {ordinal}: {Path(path).name}"
            if reused[str(path)] != (number, ordinal):
                unavailable[key] = "Earlier delivery reused a mutable path without a separate snapshot."
                continue
            try:
                raw = Path(path).read_bytes()
                text = raw.decode("utf-8") if Path(path).suffix.lower() == ".md" else read_delivered(Path(path))
            except (OSError, UnicodeError) as exc:
                unavailable[key] = type(exc).__name__
                continue
            files[key] = {
                "name": Path(path).name,
                "path": str(path),
                "turn": number,
                "ordinal": ordinal,
                "execution_id": turn.execution.turn_id,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "text": text,
                "format": Path(path).suffix.lower(),
            }
            if is_memo(text, vocabulary):
                memos[key] = {
                    **memo_facts(text, vocabulary),
                    **{
                        name: files[key][name]
                        for name in ("name", "path", "turn", "ordinal", "execution_id", "sha256", "text", "format")
                    },
                }
    if memos:
        found["memos"] = memos
    if unavailable:
        found["unavailable_deliveries"] = unavailable
    card_id = getattr(card, "name", getattr(card, "id", ""))
    check = expected_check(
        memos,
        card,
        allowed=vocabulary.clause_labels.get(card_id, set()),
        change_details=vocabulary.changed_clause_details.get(card_id, {}),
    )
    if check:
        found["expected_check"] = check
    if files:
        found["delivered_files"] = files
    if archives is not None:
        found["archive_inventory"] = {path: {"sha256": sha(text), "text": text} for path, text in archives.items()}
        found["archive_matches"] = {
            key: [
                path
                for path, text in archives.items()
                if Path(path).name == entry["name"] and sha(text) == entry["sha256"]
            ]
            for key, entry in files.items()
        }
    if archive_observation is not None:
        found["archive_observation"] = archive_observation
    register = register_facts(exchanges, vocabulary, live, base, workdir=workdir)
    if card is not None or register or observed:
        register["observability"] = "working directory" if observed and live is not None else "unobserved final state"
        register["observation"] = observation or {
            "register": "read" if live is not None else "unavailable",
            "notes": "read" if notes is not None else "unavailable",
        }
        if card is not None:
            register["expected_registration_number"] = registration_number(vocabulary, card, base)
            fields = expected_of(card)
            counterpart = fields.get("counterparty", "").split(" (register", 1)[0]
            version = "v2" if "keeping the number" in fields.get("register", "") else "v1"
            register["record_scope"] = {
                "counterparty": counterpart,
                "version": version,
                "number": register["expected_registration_number"],
            }
            register["current_nda_rows"] = [
                row
                for row in register.get("structured_rows_added", [])
                if row["table"] == "nda"
                and row["column_count_matches"]
                and canonical(row["cells"][3]) == canonical(counterpart)
                and row["cells"][1].casefold() == version
            ]
            register["current_pending_rows"] = [
                row
                for row in register.get("structured_rows_added", [])
                if row["table"] == "pending"
                and row["column_count_matches"]
                and register["expected_registration_number"] in row["cells"][3]
            ]
        found["register"] = register
    changed_notes = escalation_notes(exchanges, vocabulary, notes, base_notes=base_notes, workdir=workdir)
    if changed_notes:
        found["escalation_notes"] = changed_notes
        found["note_provenance"] = {
            path: {
                "sha256": sha(text),
                "baseline_sha256": sha(base_notes[path]) if base_notes and path in base_notes else None,
                "change": "modified" if base_notes and path in base_notes else "new",
            }
            for path, text in changed_notes.items()
        }
    if notes is not None:
        found["note_inventory"] = {
            path: {"sha256": sha(text), "changed": path in changed_notes} for path, text in notes.items()
        }
    operations = calls(exchanges)
    if operations:
        found["operations"] = operations
    handed = delegations(exchanges, vocabulary)
    if handed:
        found["delegations"] = handed
        found["desks_scope"] = (
            "Counts of observed instance-bound executions, not a verdict on every accepted or attempted handoff."
        )
        found["desks"] = {
            desk: sum(item["execution_verified"] and item["desk"] == desk for item in handed)
            for desk in ("contract", "other", "unclear")
        }
    children = child_executions(exchanges)
    if children:
        found["child_executions"] = children
    said = messages(exchanges)
    sources = (
        {f"message {number}": text for number, text in enumerate(said, 1)}
        | {key: entry["text"] for key, entry in files.items()}
        | {f"filed {path}": text for path, text in changed_notes.items()}
    )
    if filed:
        sources.update({f"filed {path}": text for path, text in filed.items()})
    if live is not None:
        sources["live register"] = live
    colours = {
        key: context_hits(text, vocabulary.colours)
        for key, text in sources.items()
        if key.startswith("message") and context_hits(text, vocabulary.colours)
    }
    if colours:
        found["colours_in_replies"] = colours
    for key, terms in (("sign_lines", vocabulary.sign_claims), ("director_only_wording", vocabulary.director_only)):
        hits = {source: hit for source, text in sources.items() if (hit := context_hits(text, terms))}
        if hits:
            found[key] = hits
    names = [(name, alias) for name, alias in zip(vocabulary.signers, vocabulary.signer_aliases)]
    signers = {
        name: {
            source: lines
            for source, text in sources.items()
            if (
                lines := [
                    line
                    for line in text.splitlines()
                    if name in line or re.search(r"\b" + re.escape(alias) + r"\b", line, re.I)
                ]
            )
        }
        for name, alias in names
    }
    if any(signers.values()):
        found["signers_named"] = {name: contexts for name, contexts in signers.items() if contexts}
    external = {}
    for key, entry in files.items():
        clues = [
            line
            for text in said
            for line in text.splitlines()
            if entry["name"] in line and any(term.casefold() in line.casefold() for term in vocabulary.external_intent)
        ]
        candidate = (
            vocabulary.external_mark in entry["name"]
            or entry["name"].startswith(vocabulary.external_prefix)
            or bool(rows_for(entry["text"], ("Section", "Proposed change")))
            or bool(clues)
        )
        if candidate:
            hits = context_hits(
                entry["text"], (*vocabulary.colours, *vocabulary.internal_words, *vocabulary.external_internal_english)
            )
            chinese = [line for line in entry["text"].splitlines() if HAN.search(line)]
            external[key] = {
                "audience": "external candidate; read presentation and negations",
                "presentation": clues,
                "literal_hits": hits,
                "Chinese_text": chinese,
                "text": entry["text"],
                "sha256": entry["sha256"],
            }
    if external:
        found["external_documents"] = external
        found["external_request_leaks"] = {
            key: value for key, value in external.items() if value["literal_hits"] or value["Chinese_text"]
        }
    if card is not None:
        found["measurement_scope"] = (
            "These are full contextual facts, not criterion verdicts. Actual requester answers, live state, table meaning and actual approvals control semantic decisions."
        )
    return found


def file_state(path: Path) -> dict:
    try:
        raw = path.read_bytes()
        return {"status": "read", "text": raw.decode("utf-8"), "sha256": hashlib.sha256(raw).hexdigest()}
    except FileNotFoundError:
        return {"status": "absent"}
    except (OSError, UnicodeError) as exc:
        return {"status": "unavailable", "error": type(exc).__name__}


def note_states(workdir: Path, folder: str) -> tuple[dict[str, str] | None, str]:
    place = workdir / folder
    if relative_path(folder, workdir) != folder:
        return None, "unavailable: note folder escaped the workdir"
    try:
        place.stat()
    except FileNotFoundError:
        return {}, "absent"
    except OSError as exc:
        return None, "unavailable: " + type(exc).__name__
    try:
        texts = {}
        for path in sorted(place.rglob("*.md")):
            relative = path.relative_to(workdir).as_posix()
            if relative_path(relative, workdir) != relative or not path.resolve().is_relative_to(place.resolve()):
                return None, "unavailable: note path escaped the folder"
            state = file_state(path)
            if state["status"] != "read":
                return None, "unavailable: " + state["status"]
            texts[relative] = state["text"]
        return texts, "read"
    except OSError as exc:
        return None, "unavailable: " + type(exc).__name__


class NdaOwner(Owner):
    """The legal director reviews full live-file changes on a verified replica against its pre-drill baseline."""

    def __init__(self, scenario, provider, skills, **options):
        super().__init__(scenario, provider, skills, facts=self._facts, **options)
        self.vocabulary = Vocabulary.load(scenario)

    def _facts(self, name, exchanges, card) -> dict:
        placed = self.workdirs.get(name) or {}
        workdir = Path(placed["workdir"]) if placed.get("workdir") else None
        baseline = Path(self.workdir)
        base_state = file_state(baseline / self.vocabulary.register) if baseline.is_dir() else {"status": "unavailable"}
        base_notes, base_note_status = (
            note_states(baseline, self.vocabulary.notes_folder) if baseline.is_dir() else (None, "unavailable")
        )
        observed = workdir is not None and workdir.is_dir()
        state = (
            file_state(workdir / self.vocabulary.register)
            if observed and relative_path(self.vocabulary.register, workdir) == self.vocabulary.register
            else {"status": "unavailable: replica missing or register path escaped"}
        )
        notes, note_status = (
            note_states(workdir, self.vocabulary.notes_folder) if observed else (None, "unavailable: replica missing")
        )
        archives, archive_observation = {}, {}
        if observed:
            for folder in self.vocabulary.archives:
                contents, status = note_states(workdir, folder)
                archive_observation[folder] = status
                if contents is not None:
                    archives.update(contents)
        else:
            archive_observation = {folder: "unavailable: replica missing" for folder in self.vocabulary.archives}
        observation = {
            "workdir": str(workdir) if workdir else None,
            "register": state["status"],
            "baseline_register": base_state["status"],
            "notes": note_status,
            "baseline_notes": base_note_status,
        }
        base = base_state.get("text")
        live = state.get("text", "") if state["status"] in ("read", "absent") else None
        if base_note_status.startswith("unavailable"):
            notes = None
        return facts(
            exchanges,
            self.vocabulary,
            card,
            live=live,
            base=base,
            notes=notes,
            base_notes=base_notes,
            observed=observed and live is not None,
            workdir=workdir if observed else None,
            observation=observation,
            filed=self._filed(name) if observed else None,
            archives=archives if observed else None,
            archive_observation=archive_observation,
        )


DELIVERED = delivered
OWNER = NdaOwner
