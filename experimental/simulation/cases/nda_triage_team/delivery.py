"""Verify source-bound NDA Markdown delivery roles and source-required amendment documents.

This deterministic gate checks actual retained bytes, memo structure, source positions and the required preferred
wording. It does not certify conversational permissions, legal judgments, actual approvals or live legal records;
those remain the explicitly scoped semantic criteria.
"""

import hashlib
import re
import unicodedata
from pathlib import Path

from experimental.harness.scenario.contract import load
from experimental.harness.scenario.digest import digest

ROOT = Path(__file__).resolve().parent


def canonical(text: str) -> str:
    """Compare authorized reflow, quotation/punctuation and defined-party/purpose substitutions."""
    text = unicodedata.normalize("NFKC", text).casefold()
    for original, substitute in (
        ("receiving party", "recipient"),
        ("disclosing party", "discloser"),
        ("proposed arrangement", "purpose"),
        ("potential partnership", "purpose"),
        ("opportunity", "purpose"),
        ("evaluation", "purpose"),
        ("project", "purpose"),
    ):
        text = text.replace(original, substitute)
    return " ".join(re.findall(r"\w+", text))


def mappings(value: str) -> dict[str, str]:
    if not value or value == "none":
        return {}
    return dict(part.strip().split("=", 1) for part in value.split(","))


def source_root(item: dict) -> Path:
    root = Path(str(item.get("scenario_root") or ""))
    if not item.get("scenario_root") or not root.is_dir() or digest(root) != digest(ROOT):
        raise ValueError("The retained NDA scenario source is unavailable or differs from this evaluator.")
    return root.resolve()


def retained(item: dict, file: dict) -> tuple[str, str]:
    root = Path(str(item.get("delivery_root") or ""))
    if not item.get("delivery_root") or not root.is_dir() or not file.get("path") or not file.get("sha256"):
        raise ValueError("NDA delivery lacks a retained root, path or full content identity.")
    root = root.resolve()
    path = Path(str(file["path"]))
    path = (path if path.is_absolute() else root / path).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("The retained NDA file is unavailable or outside its delivery root.")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != file["sha256"]:
        raise ValueError("The retained NDA file changed after its recorded delivery.")
    if path.name != file.get("name") or path.suffix.lower() != ".md":
        return path.name, ""
    try:
        return path.name, raw.decode("utf-8")
    except UnicodeError as exc:
        raise ValueError("The retained Markdown NDA file is unreadable.") from exc


def preferred(root: Path, position: str) -> str:
    text = (root / "materials/clause-bank/SKILL.md").read_text()
    section = re.search(r"(?ms)^## " + re.escape(position) + r"\s.*?(?=^## |\Z)", text)
    if not section:
        return ""
    if position == "2.3":
        match = re.search(r"(?m)^\s*- \(d\)\s*(.+)", section.group())
    else:
        match = re.search(r"(?m)^- \*\*P(?:[^*]*)\*\*[^A-Za-z]*(.+)", section.group())
    if not match:
        return ""
    value = match.group(1)
    if position == "2.15":
        value = next(
            (
                line.split(chr(0xFF1A), 1)[-1]
                for line in section.group().splitlines()
                if "HKIAC" in line or "Hong Kong International Arbitration Centre" in line
            ),
            value,
        )
    if position == "2.9":
        return "delete"
    return value


def proposed_matches(root: Path, clause: str, position: str, text: str) -> bool:
    if position == "2.9":
        return bool(
            re.fullmatch(
                r"(?is)\s*(?:please\s+)?delete\s+(?:section|clause)\s+"
                + re.escape(clause)
                + r"\s*(?:in\s+its\s+entirety)?[.\s\"']*",
                text,
            )
        )
    target = canonical(preferred(root, position))
    if not target:
        return False
    proposed = re.sub(
        r"(?is)^\s*(?:replace\s+(?:with|clause\s+[^:]+\s+with)|add(?:\s+at\s+the\s+end)?|restore(?:\s+subclause\s+[^:]+)?)\s*:\s*",
        "",
        text,
    ).strip()
    if position == "2.3":
        proposed = re.sub(
            r"(?i)^\s*(?:add|restore)\s+(?:the\s+)?(?:following\s+)?(?:exclusion|subclause)\s*(?:"
            + re.escape(clause)
            + r")?\s*:\s*",
            "",
            proposed,
        )
        normalized = canonical(proposed)
        return normalized in (target, "d " + target)
    return canonical(proposed) == target


def template_body(text: str) -> str:
    match = re.search(r"(?im)^\s*[*#` ]*1[.)]?\s+Definitions[*` ]*\s*$", text)
    if not match:
        return ""
    body = text[match.end() :]
    body = re.split(r"(?i)Signed for and on behalf of", body, maxsplit=1)[0]
    return re.sub(r"(?i)Option A \(Counterparty outside mainland China\):\s*", "", body)


def full_template(root: Path, text: str) -> bool:
    source = (root / "materials/nda-template/SKILL.md").read_text()
    source = re.sub(r"(?m)^Option B .*\n?", "", source)
    return (
        "MUTUAL CONFIDENTIALITY AGREEMENT" in text
        and bool(template_body(text))
        and canonical(template_body(text)) == canonical(template_body(source))
    )


def actual_clauses(root: Path, card, fields) -> set[str]:
    version = "v2" if "keeping the number" in fields.get("register", "") else "v1"
    files = [root / name for name in card.files]
    if version == "v2":
        files = [path for path in files if "v2" in path.name]
    pattern = re.compile(r"(?im)^\s*(?:\*\*)?(?:Article\s+)?(\d+(?:\.\d+)*)(?:[.\s(])")
    return {match.group(1) for path in files for match in pattern.finditer(path.read_text())}


def changed_clause_details(root: Path, card, fields) -> dict[str, set[str]]:
    """Bind a grouped change to actual changed/deleted numbered bodies in its prior and current texts."""
    from experimental.simulation.cases.nda_triage_team.owner import clause_covered, listed

    changed = listed(fields.get("changed"))
    if not changed:
        return {}
    pattern = re.compile(r"(?im)^\s*(?:\*\*)?(?:Article\s+)?(\d+(?:\.\d+)*)(?:[.\s(])")
    versions = []
    for version in ("v1", "v2"):
        bodies = {}
        for name in card.files:
            if not re.search(r"(?i)_" + version + r"(?:[_.]|$)", Path(name).name):
                continue
            text = re.split(r"(?im)^Signed (?:by|for|for and on behalf of)\b", (root / name).read_text())[0]
            labels = list(pattern.finditer(text))
            for index, label in enumerate(labels):
                end = labels[index + 1].start() if index + 1 < len(labels) else len(text)
                bodies[label.group(1)] = re.sub(r"\s+", " ", text[label.end() : end]).strip()
        versions.append(bodies)
    before, current = versions
    labels = before.keys() | current.keys()
    differing = {number for number in labels if before.get(number) != current.get(number)}
    details = {}
    for number in changed:
        descendants = {label for label in labels if label != number and clause_covered(number, [label])}
        leaves = {
            label
            for label in descendants
            if label in differing
            and not any(other != label and clause_covered(label, [other]) for other in descendants)
        }
        details[number] = leaves or {number}
    return details


def complete_memo(name, text, fields, vocabulary, allowed_clauses, change_details=None) -> bool:
    from experimental.simulation.cases.nda_triage_team.owner import clause_covered, comparison_check, listed, memo_facts

    measured = memo_facts(text, vocabulary)
    current = "v2" if "keeping the number" in fields.get("register", "") else "v1"
    counterpart = fields.get("counterparty", "").split(" (register", 1)[0]
    if not (
        name.startswith(vocabulary.memo_prefix + "-")
        and name.endswith("-" + current + ".md")
        and measured["first_line"] == fields.get("verdict")
        and measured["internal_mark"]
        and measured["playbook_version_in_force_named"]
        and not measured["superseded_versions_named"]
        and measured["header_counterparty_lines"]
        and measured["header_handler_lines"]
        and canonical(counterpart) in canonical(measured["header"])
        and re.search(r"(?i)\b" + current + r"\b", measured["header"])
        and re.search(r"\b2026-\d{2}-\d{2}\b", measured["header"])
        and re.search(re.escape(vocabulary.row_prefix) + r"\d+", measured["header"])
        and all(measured["sections"].values())
    ):
        return False
    expected = set(listed(fields.get("issues")))
    cited = set(measured["cited_clauses"])
    if any(not clause_covered(number, cited) for number in expected) or any(
        not any(clause_covered(number, [actual]) for number in expected) for actual in cited
    ):
        return False
    if any(number not in expected and number not in allowed_clauses for number in cited):
        return False
    positions = mappings(fields.get("positions", ""))
    uncovered = vocabulary.uncovered_basis
    for row in measured["issue_rows"]:
        if len(row) != len(vocabulary.issue_columns) or not all(cell.strip() for cell in row):
            return False
        numbers = listed(row[0])
        for number in numbers:
            policy = positions.get(number) or next(
                (policy for parent, policy in positions.items() if clause_covered(parent, [number])), None
            )
            if policy == "uncovered":
                if not any(word.casefold() in row[2].casefold() for word in uncovered):
                    return False
            elif not policy or policy not in row[2] or policy + "-P" not in row[3]:
                return False
    if not expected:
        if not measured["checked_lines"] or not any(
            any(word in line for word in vocabulary.none_labels) for line in measured["no_issues_lines"]
        ):
            return False
    changed = listed(fields.get("changed"))
    if changed:
        compared = comparison_check(changed, measured["change_clauses"], details=change_details)
        if compared["changed_not_cited"] or compared["outside_changed_scope"]:
            return False
    for row in measured["change_rows"]:
        if len(row) != len(vocabulary.change_columns) or not all(cell.strip() for cell in row):
            return False
        changed_numbers = listed(row[0])
        is_issue = any(clause_covered(number, changed_numbers) for number in expected)
        if is_issue:
            if fields["verdict"] not in row[-1] or not any(
                label.casefold() in row[-1].casefold() for label in vocabulary.new_issue_labels
            ):
                return False
        elif canonical(row[-1]) not in {canonical(label) for label in vocabulary.resolved_labels}:
            return False
    return True


def complete_external(root, text, amendments, vocabulary, allowed_clauses) -> bool:
    from experimental.simulation.cases.nda_triage_team.owner import clause_covered, clause_numbers, rows_for

    if re.search(r"[\u3400-\u9fff]", text) or any(
        re.search(r"\b" + re.escape(colour) + r"\b", text) for colour in vocabulary.colours
    ):
        return False
    if any(re.search(r"\b" + re.escape(term) + r"\b", text, re.I) for term in vocabulary.external_internal_english):
        return False
    if full_template(root, text):
        return True
    rows = rows_for(text, ("Section", "Proposed change"))
    if not rows or any(len(row) != 2 or len(clause_numbers(row[0])) != 1 for row in rows):
        return False
    measured = {clause_numbers(row[0])[0]: row[1] for row in rows}
    if len(measured) != len(rows) or any(
        number not in amendments and number not in allowed_clauses for number in measured
    ):
        return False
    grouped = {
        clause: [(number, proposal) for number, proposal in measured.items() if clause_covered(clause, [number])]
        for clause in amendments
    }
    if any(not any(clause_covered(clause, [number]) for clause in amendments) for number in measured):
        return False
    return all(
        values
        and proposed_matches(
            root,
            clause,
            amendments[clause],
            " ".join(re.sub(r"(?i)^\s*Replace with:\s*", "", proposal) for _, proposal in sorted(values)),
        )
        for clause, values in grouped.items()
    )


def delivered(item: dict) -> bool:
    """An actual source-required opinion and, where applicable, an authorized external Markdown document per drill."""
    from experimental.simulation.cases.nda_triage_team.owner import Vocabulary, expected_of

    root = source_root(item)
    contract = load(root)
    vocabulary = Vocabulary.load(type("CaseSource", (), {"root": root})())
    cards = {card.id: card for card in contract.situation.cases}
    drills = item.get("drills") or []
    if not drills:
        return False
    for drill in drills:
        card = cards.get(drill.get("card"))
        if card is None:
            raise ValueError("The retained NDA drill is not bound to a card of this scenario.")
        fields = expected_of(card)
        allowed = actual_clauses(root, card, fields)
        changes = changed_clause_details(root, card, fields)
        texts = [retained(item, file) for turn in drill.get("exchanges") or [] for file in turn.get("delivered") or []]
        if not any(complete_memo(name, text, fields, vocabulary, allowed, changes) for name, text in texts):
            return False
        amendments = mappings(fields.get("amendments", ""))
        if amendments and not any(complete_external(root, text, amendments, vocabulary, allowed) for _, text in texts):
            return False
    return True
