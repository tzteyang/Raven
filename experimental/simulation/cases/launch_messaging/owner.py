"""The launch copy owner: the generic `Owner` with the facts a brand lead checks a drill's copy by.

A drill asks for a product's first-screen copy and sales training card from an evidence-sheet export and a research
excerpt the requester hands over. The facts are measured, never judged: the lengths of the title, the proposition and
the points; which evidence row each point cites, where that row stood on the request date (the sheet's export date)
and whether its usable wording and its test condition with the footnotes were carried over; listed absolute words
(time-order uses spared), comparison wording, scope and efficacy words in the customer-facing lines, and
competitor-matrix terms anywhere in a delivered file; figures in those lines that neither a handout, the requester nor
a handed-over material gave; whether the training card repeats the first screen; what the live register gained and
whether the rows it started with survived; how a revision differs from the version it replaces; and, for requests
dated from the citation notice, the first-screen notes. Every word the measures use is the scenario's, read from its
`reference.md`; the owner's model still decides every verdict.
"""

import hashlib
import re
import unicodedata
from collections import defaultdict, deque
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path

from experimental.cultivation.counterpart.owner import Owner, delivery_versions
from experimental.cultivation.counterpart.rulers import CONFIG, around, tables, words
from experimental.harness.scenario.digest import digest

SNIPPET = 60
# Full-width punctuation the case's files use, spelled by code point so the source stays in ASCII: the colon, the
# round brackets and the square brackets a footnote marker sits in.
_COLON = chr(0xFF1A)
_ROUND = chr(0xFF08) + chr(0xFF09)
_SQUARE = chr(0xFF3B) + chr(0xFF3D)
# The Chinese numerals one to nine, as a point may be numbered.
_NUMERALS = "".join(chr(code) for code in (0x4E00, 0x4E8C, 0x4E09, 0x56DB, 0x4E94, 0x516D, 0x4E03, 0x516B, 0x4E5D))
# The words for year, month, day, clause and section that mark a number as a date or a reference, not a figure.
_YEAR, _MONTH, _DAY = chr(0x5E74), chr(0x6708), chr(0x65E5)
_REFERENCE = chr(0x7B2C), chr(0x6761), chr(0x8282), chr(0x7248)
_ASCII = "A-Za-z0-9"
ROW = re.compile(rf"(?<![{_ASCII}])F\d{{1,2}}(?![{_ASCII}])")
REPORT = re.compile(rf"(?<![{_ASCII}])JC-\d{{3}}(?![{_ASCII}])")
NUMBER = re.compile(rf"(?<![{_ASCII}])[A-Z]{{2}}\d-\d{{4}}-\d+(?![{_ASCII}])")
MODEL = re.compile(rf"(?<![{_ASCII}])[A-Z]{{2}}\d(?![{_ASCII}])")
DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
DATED = re.compile(
    rf"\d{{4}}\s*{_YEAR}(?:\s*\d{{1,2}}\s*{_MONTH}(?:\s*\d{{1,2}}\s*{_DAY})?)?|\d{{1,2}}\s*{_MONTH}\s*\d{{1,2}}\s*{_DAY}"
    rf"|{_REFERENCE[0]}\s*\d+(?:\.\d+)*\s*[{_REFERENCE[1]}{_REFERENCE[2]}{_REFERENCE[3]}]?"
)
FIGURE = re.compile(r"\d+(?:\.\d+)?")
SESSION = re.compile(r"^(?:holdout-|s\d+-)?(?P<card>[a-z]+)(?:-\d+)?$")
POINTS = re.compile(r"^\s*points:\s*(?P<ids>.+)$", re.M)
SKIPPED = re.compile(r"^\s*Skipped for want of usable evidence:\s*(?P<names>[^;]+)", re.M)
EXPECTED_MODEL = re.compile(r"\bmodel (?P<model>[A-Z]{2}\d)\b")


@dataclass(frozen=True)
class Vocabulary:
    """The words the brand lead's facts are computed with, from the scenario's `reference.md` table."""

    first_screen_file: str
    training_file: str
    sheet_file: str
    export_date: str
    title: str
    proposition: str
    point: str
    intro: str
    number: str
    basis: str
    notes: str
    skip_sections: tuple[str, ...]
    sheet_columns: tuple[str, ...]
    third_party: str
    void_mark: str
    internal_only: str
    unqualified: str
    footnote: str
    internal_test: str
    internal_label: str
    notice_from: date
    limits: tuple[int, int, int]
    count_unit: str
    forbidden: tuple[str, ...]
    time_order: tuple[str, ...]
    scope_words: tuple[str, ...]
    efficacy: tuple[str, ...]
    comparison: tuple[str, ...]
    comparative: str
    comparative_skip: tuple[str, ...]
    comparative_words: tuple[str, ...]
    competitor: tuple[str, ...]
    register_path: str
    register_columns: tuple[str, ...]
    snapshot_prefix: str
    request_date: str
    requester: str
    version: str
    replaces: str
    no_replacement: str
    internal_sections: tuple[str, ...]
    file_names: tuple[str, ...]
    sample_label: str
    sample_unit: str
    research_file: str
    quantity_units: tuple[str, ...]
    report_label: str

    @classmethod
    def load(cls, path: Path) -> "Vocabulary":
        found = words(path)
        one = {key: values[0] for key, values in found.items()}
        title, proposition, point = (int(value) for value in found["limits"])
        return cls(
            first_screen_file=one["first_screen_file"],
            training_file=one["training_file"],
            sheet_file=one["sheet_file"],
            export_date=one["export_date"],
            title=one["title_label"],
            proposition=one["proposition_label"],
            point=one["point_label"],
            intro=one["intro_label"],
            number=one["number_label"],
            basis=one["basis_label"],
            notes=one["notes_label"],
            skip_sections=found["skip_sections"],
            sheet_columns=found["sheet_columns"],
            third_party=one["third_party"],
            void_mark=one["void_mark"],
            internal_only=one["internal_only"],
            unqualified=one["unqualified"],
            footnote=one["footnote"],
            internal_test=one["internal_test"],
            internal_label=one["internal_label"],
            notice_from=date.fromisoformat(one["notice_from"]),
            limits=(title, proposition, point),
            count_unit=one["count_unit"],
            forbidden=found["forbidden"],
            time_order=found["time_order"],
            scope_words=found["scope_words"],
            efficacy=found["efficacy"],
            comparison=found["comparison"],
            comparative=one["comparative"],
            comparative_skip=found["comparative_skip"],
            comparative_words=found["comparative_words"],
            competitor=found["competitor"],
            register_path=one["register_path"],
            register_columns=found["register_columns"],
            snapshot_prefix=one["snapshot_prefix"],
            request_date=one["request_date_label"],
            requester=one["requester_label"],
            version=one["version_label"],
            replaces=one["replaces_label"],
            no_replacement=one["no_replacement"],
            internal_sections=found["internal_sections"],
            file_names=found["file_names"],
            sample_label=one["sample_label"],
            sample_unit=one["sample_unit"],
            research_file=one["research_file"],
            quantity_units=found["quantity_units"],
            report_label=one["report_label"],
        )

    @property
    def comparative_pattern(self) -> re.Pattern:
        return re.compile(
            re.escape(self.comparative) + r".{0,6}?(?:" + "|".join(map(re.escape, self.comparative_words)) + ")"
        )


def flat(text: str | None) -> str:
    """Text as two copies are compared character for character: width-folded, without any spacing."""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text or ""))


def same(one: str | None, other: str | None) -> bool:
    return one is not None and other is not None and one == other


def clean(text: str, vocabulary: Vocabulary) -> str:
    """A labelled value without markdown emphasis and without a trailing length note in brackets."""
    text = re.sub(r"\*\*|`", "", text or "").strip()
    unit = re.escape(vocabulary.count_unit)
    brackets = re.escape("()" + _ROUND)
    return re.sub(rf"\s*[{brackets}][^\d{brackets}]{{0,4}}\d+\s*{unit}[^{brackets}]{{0,4}}[{brackets}]\s*$", "", text)


def length(text: str | None) -> int:
    """Characters as the copy norms count them: every visible character, spaces left out."""
    return len(re.sub(r"\s", "", text or ""))


def ordinal(text: str) -> int | None:
    """A point's number written in digits or in a Chinese numeral."""
    text = text.strip()
    if text.isdigit():
        return int(text)
    return _NUMERALS.index(text) + 1 if len(text) == 1 and text in _NUMERALS else None


def cells(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|"):
        return []
    found = [cell.strip() for cell in stripped.strip("|").split("|")]
    return [] if all(re.fullmatch(r":?-{3,}:?", cell) for cell in found) else found


def heading_of(line: str, labels) -> str | None:
    """The heading a line opens: a markdown heading, or a line that is nothing but one of `labels`, bold or not."""
    stripped = line.strip()
    if stripped.startswith("#"):
        return stripped
    bare = re.sub(r"^[*_]+|[*_:" + _COLON + r"]+$", "", stripped).strip()
    return stripped if bare and bare in labels else None


def lines_of(text: str, vocabulary: Vocabulary) -> list[tuple[str, str]]:
    """(heading, line) for every line outside the sections whose quoted words are not copy."""
    out, heading = [], ""
    labels = (*vocabulary.skip_sections, vocabulary.notes)
    for line in (text or "").splitlines():
        opened = heading_of(line, labels)
        if opened is not None:
            heading = opened
        if not any(word in heading for word in vocabulary.skip_sections):
            out.append((heading, line))
    return out


def snippet(line: str, word: str) -> str:
    line = line.strip()
    return around(line, word) if word in line else line[:SNIPPET]


# ------------------------------------------------------------------------------------------------- evidence sheet


@dataclass(frozen=True)
class Row:
    """One row of a card's evidence sheet: the columns the copy is held to."""

    id: str
    concern: str
    wording: str
    third: bool
    issuer: str
    report: str
    condition: str
    notes: tuple[str, ...]
    issued: date | None
    valid: date | None
    use: str


def _day(text: str) -> date | None:
    found = DAY.search(text or "")
    return date.fromisoformat(found.group()) if found else None


def sheet(text: str, vocabulary: Vocabulary) -> tuple[date | None, dict[str, Row]]:
    """A sheet export's date and its rows by number; a condition's footnote markers resolve to the footnote texts."""
    exported = next((_day(line) for line in (text or "").splitlines() if vocabulary.export_date in line), None)
    mark = re.escape(vocabulary.footnote)
    footnotes = {
        found.group("n"): found.group("text").strip()
        for found in re.finditer(rf"^\s*{mark}\s*(?P<n>\d+)\s*[:{_COLON}]\s*(?P<text>.+)$", text or "", re.M)
    }
    marker = re.compile(rf"[\[{_SQUARE[0]}]\s*{mark}\s*(\d+)\s*[\]{_SQUARE[1]}]")
    names = vocabulary.sheet_columns
    rows = {}
    for found in tables(text or ""):
        header = found[0]
        if names[0] not in header or names[3] not in header:
            continue
        at = {name: header.index(name) for name in names if name in header}
        for row in found[1:]:

            def cell(index: int, row=row) -> str:
                name = names[index]
                return row[at[name]] if name in at and at[name] < len(row) else ""

            condition = cell(7)
            reports = REPORT.findall(cell(6))
            rows[cell(0)] = Row(
                id=cell(0),
                concern=cell(1),
                wording=cell(3),
                third=vocabulary.third_party in cell(4),
                issuer=cell(5),
                report=reports[0] if reports else "",
                condition=marker.sub("", condition).strip(),
                notes=tuple(footnotes.get(number, "") for number in marker.findall(condition)),
                issued=_day(cell(8)),
                valid=_day(cell(9)),
                use=cell(10),
            )
    return exported, rows


def comparisons(line: str, vocabulary: Vocabulary) -> list[str]:
    """The comparison words in a line, and every comparative phrase its comparison marker opens; a word that only
    happens to carry the marker (a share, a ratio, a 'for example') is blanked first."""
    found = [word for word in vocabulary.comparison if word in line]
    for word in vocabulary.comparative_skip:
        line = line.replace(word, " " * len(word))
    return found + [match.group() for match in vocabulary.comparative_pattern.finditer(line)]


def absolutes(line: str, vocabulary: Vocabulary) -> list[str]:
    """The listed absolute words in a line, an occurrence inside a time-order use left out."""
    spared = [
        (match.start(), match.end()) for word in vocabulary.time_order for match in re.finditer(re.escape(word), line)
    ]
    return [
        word
        for word in vocabulary.forbidden
        if any(
            not any(start <= match.start() and match.end() <= end for start, end in spared)
            for match in re.finditer(re.escape(word), line)
        )
    ]


def standing(row: Row, on: date | None, vocabulary: Vocabulary) -> str:
    """Where a row stood on the request date: usable, or the first reason it could not back a point."""
    if on is None:
        return "request date unobserved"
    if row.issued is None or row.valid is None:
        return "evidence date or validity unobserved"
    if row.issued and on and row.issued > on:
        return "not yet issued on the request date"
    if vocabulary.void_mark in row.use:
        voided = _day(row.use)
        if voided is None or (on and voided <= on):
            return f"void from {voided or 'an unstated date'}"
    if vocabulary.internal_only in row.use:
        return "barred from external use"
    if row.valid and on and row.valid < on:
        return f"expired {row.valid}"
    if comparisons(row.wording, vocabulary):
        return "comparison wording"
    if row.third and vocabulary.unqualified in row.issuer and on and on >= vocabulary.notice_from:
        return "issuer without CMA or CNAS"
    if (
        row.third
        and on >= vocabulary.notice_from
        and not any(qualification in row.issuer for qualification in ("CMA", "CNAS"))
    ):
        return "issuer qualifications unobserved"
    return "usable"


# ---------------------------------------------------------------------------------------------- delivered copy


@dataclass(frozen=True)
class Copy:
    """One delivered version, first screen or training card, as its labelled lines and numbered rows read."""

    file: str
    text: str = ""
    number: str | None = None
    title: str | None = None
    proposition: str | None = None
    intro: str | None = None
    basis: str | None = None
    points: dict = field(default_factory=dict)
    says: dict = field(default_factory=dict)
    evidence: dict = field(default_factory=dict)
    rows: dict = field(default_factory=dict)
    notes: tuple = ()
    metadata: dict = field(default_factory=dict)
    duplicate_values: tuple = ()
    additional_customer_lines: tuple = ()
    turn: int | None = None
    sha256: str | None = None


def parse(name: str, text: str, vocabulary: Vocabulary, *, training: bool = False) -> Copy:
    """Read a delivered file the way the brief's appendix lays it out: labelled lines for the title, the proposition
    and the points, numbered table rows for the evidence (and, on a training card, the points and customer lines),
    and the notes under the notes heading. Anything laid out otherwise is simply not found."""
    v = vocabulary
    keys = {v.title: "title", v.proposition: "proposition", v.intro: "intro", v.number: "number", v.basis: "basis"}
    colon = f"[:{_COLON}]"
    numeral = rf"[1-9{_NUMERALS}]"
    label = re.compile(rf"^\s*(?:[-*>]\s*)?(?P<label>{'|'.join(map(re.escape, keys))})\s*{colon}\s*(?P<text>.+?)\s*$")
    point = re.compile(rf"^\s*(?:[-*>]\s*)?{re.escape(v.point)}\s*(?P<n>{numeral})\s*{colon}\s*(?P<text>.+?)\s*$")
    numbered = re.compile(rf"^(?:(?P<named>{re.escape(v.point)})\s*)?(?P<n>{numeral})$")
    note = re.compile(rf"^\s*(?:[-*>]\s*)?{re.escape(v.footnote)}\s*(?P<n>{numeral})\s*{colon}")
    found: dict = {}
    metadata, duplicates, additional = {}, [], []
    points, listed, says, evidence, rows, notes = {}, {}, {}, {}, {}, []
    header: list[str] = []
    for heading, raw in lines_of(text, v):
        line = raw.replace("**", "")
        row = cells(line)
        if row:
            first = clean(row[0], v)
            if len(row) == 2:
                if first in metadata:
                    duplicates.append(row[1])
                metadata.setdefault(first, clean(row[1], v))
            if first in keys and len(row) > 1:
                if keys[first] in found:
                    duplicates.append(clean(row[1], v))
                found.setdefault(keys[first], clean(row[1], v))
                continue
            match = numbered.match(first)
            if not match:
                header = row
                continue
            n = ordinal(match.group("n"))
            column = next((i for i, cell in enumerate(header) if v.sheet_columns[0] in cell), None)
            where = row[column] if column is not None and column < len(row) else line
            ids = tuple(dict.fromkeys(ROW.findall(where) or ROW.findall(line)))
            if ids:
                evidence.setdefault(n, ids)
                rows.setdefault(n, line)
            if len(row) > 1 and (match.group("named") or training):
                listed.setdefault(n, clean(row[1], v))
            if training and len(row) > 2:
                says.setdefault(n, clean(row[2], v))
            continue
        if v.notes in heading and (match := note.match(line)):
            notes.append((ordinal(match.group("n")), line.strip()))
            continue
        if match := point.match(line):
            n, value = ordinal(match.group("n")), clean(match.group("text"), v)
            if n in points:
                duplicates.append(value)
            points.setdefault(n, value)
        elif match := label.match(line):
            if keys[match.group("label")] in found:
                duplicates.append(clean(match.group("text"), v))
            found.setdefault(keys[match.group("label")], clean(match.group("text"), v))
        elif line.strip() and not line.strip().startswith("|") and not heading_of(line, (*v.skip_sections, v.notes)):
            if not any(word in heading for word in v.internal_sections):
                additional.append(line.strip())
    for n, value in listed.items():
        points.setdefault(n, value)
    numbers = NUMBER.findall(found.get("number") or "") or NUMBER.findall(name)
    return Copy(
        file=name,
        text=text,
        number=numbers[0] if numbers else None,
        title=found.get("title"),
        proposition=found.get("proposition"),
        intro=found.get("intro"),
        basis=found.get("basis"),
        points=dict(sorted(points.items())),
        says=says,
        evidence=evidence,
        rows=rows,
        notes=tuple(notes),
        metadata=metadata,
        duplicate_values=tuple(duplicates),
        additional_customer_lines=tuple(additional),
    )


def versions(exchanges, vocabulary: Vocabulary, *, training: bool, unavailable=None) -> list[Copy]:
    """Retained delivered Markdown versions, in handover order; local drafts never establish delivery."""
    label = vocabulary.training_file if training else vocabulary.first_screen_file
    out: list[Copy] = []

    for delivery in delivery_versions(exchanges):
        for name, text in delivery["files"].items():
            if label in name and Path(name).suffix.lower() == ".md":
                paths = [
                    Path(path)
                    for path in exchanges[delivery["turn"] - 1].execution.deliverables
                    if Path(path).name == name
                ]
                try:
                    data = paths[-1].read_bytes()
                    text = data.decode("utf-8")
                except (OSError, UnicodeError):
                    if unavailable is not None:
                        unavailable.append(
                            {
                                "turn": delivery["turn"],
                                "file": name,
                                "reason": "Delivered copy is not readable as UTF-8 Markdown.",
                            }
                        )
                    continue
                copy = parse(name, text, vocabulary, training=training)
                out = [previous for previous in out if (previous.number, previous.text) != (copy.number, copy.text)]
                out.append(replace(copy, turn=delivery["turn"], sha256=hashlib.sha256(data).hexdigest()))
    return out


def copy_lines(copy: Copy) -> list[str]:
    """The lines of a version that reach customers: title, proposition, points, customer lines and notes."""
    lines = [copy.title, copy.proposition, copy.intro, *copy.points.values(), *copy.says.values()]
    return (
        [line for line in lines if line]
        + [text for _, text in copy.notes]
        + list(copy.duplicate_values)
        + list(copy.additional_customer_lines)
    )


# --------------------------------------------------------------------------------------------------- the cards


@dataclass(frozen=True)
class Brief:
    """What a card hands over, read once: the request date, the sheet's rows, the handout texts, the version a
    re-check brings back, the register rows the materials' export and the handouts' export hold, the expected
    points and the concerns the expected answer skips."""

    card: str
    day: date | None
    model: str | None
    rows: dict
    handed: tuple[str, ...]
    previous: Copy | None
    base: dict
    exported: dict
    expected: tuple[str, ...]
    skipped: tuple[str, ...]
    previous_training: Copy | None = None
    research: tuple[str, ...] = ()


def expected_points(expected: str | None) -> tuple[str, ...]:
    found = POINTS.search(expected or "")
    return tuple(ROW.findall(found.group("ids"))) if found else ()


def expected_skipped(expected: str | None) -> tuple[str, ...]:
    found = SKIPPED.search(expected or "")
    return tuple(name.strip() for name in found.group("names").split(",") if name.strip()) if found else ()


@dataclass(frozen=True)
class Entry:
    """One register row: its number, its cells by the header's names and its line."""

    number: str | None
    named: dict
    line: str


def entries(text: str | None, vocabulary: Vocabulary) -> list[Entry]:
    out = []
    for found in tables(text or ""):
        header = found[0]
        if not header or vocabulary.number not in header[0]:
            continue
        for row in found[1:]:
            numbers = NUMBER.findall(row[0]) if row else []
            named = {name: row[index] for index, name in enumerate(header) if index < len(row)}
            out.append(Entry(numbers[0] if numbers else None, named, " | ".join(row)))
    return out


def known_rows(texts, vocabulary: Vocabulary) -> dict[str, str]:
    """Register cells preserved literally, with table padding stripped but content spacing and width intact."""
    return {entry.number: entry.line for text in texts for entry in entries(text, vocabulary) if entry.number}


def briefs(contract, vocabulary: Vocabulary) -> dict[str, Brief]:
    """Every card's brief, from the scenario's own handouts and the register exports its materials carry."""
    root = Path(contract.root)
    snapshots = [
        file.read_text()
        for material in contract.materials.values()
        for file in sorted(Path(material.path).rglob("*.md"))
        if file.name.startswith(vocabulary.snapshot_prefix)
    ]
    base = known_rows(snapshots, vocabulary)
    out = {}
    for case in contract.situation.cases:
        texts = {Path(item).name: (root / item).read_text() for item in case.files}
        day, rows = sheet(next((t for n, t in texts.items() if vocabulary.sheet_file in n), ""), vocabulary)
        previous = next((parse(n, t, vocabulary) for n, t in texts.items() if vocabulary.first_screen_file in n), None)
        handed = [t for n, t in texts.items() if n.startswith(vocabulary.snapshot_prefix)]
        model = EXPECTED_MODEL.search(case.expected or "")
        out[case.id] = Brief(
            card=case.id,
            day=day,
            model=model.group("model") if model else None,
            rows=rows,
            handed=tuple(texts.values()),
            previous=previous,
            base=base,
            exported=known_rows(handed, vocabulary),
            expected=expected_points(case.expected),
            skipped=expected_skipped(case.expected),
            previous_training=next(
                (parse(n, t, vocabulary, training=True) for n, t in texts.items() if vocabulary.training_file in n),
                None,
            ),
            research=tuple(t for n, t in texts.items() if vocabulary.research_file in n),
        )
    return out


def card_of(name: str, card, known) -> str | None:
    """The card a drill played: the playing's own name, or the drill's session name without its prefixes."""
    if getattr(card, "name", None) in known:
        return card.name
    found = SESSION.match(name or "")
    return found.group("card") if found and found.group("card") in known else None


# ------------------------------------------------------------------------------------------------------- facts


def shape(copy: Copy, vocabulary: Vocabulary) -> dict:
    title, proposition, point = vocabulary.limits
    out = {
        "file": copy.file,
        "number": copy.number,
        "title": {"text": copy.title, "length": length(copy.title), "limit": title},
        "proposition": {"text": copy.proposition, "length": length(copy.proposition), "limit": proposition},
        "points": [
            {"point": n, "text": text, "length": length(text), "limit": point} for n, text in copy.points.items()
        ],
    }
    figures = FIGURE.findall(MODEL.sub("", f"{copy.title or ''} {copy.proposition or ''}"))
    if figures:
        out["figures_in_title_or_proposition"] = figures
    missing = [name for name, value in (("title", copy.title), ("proposition", copy.proposition)) if not value]
    if missing or len(copy.points) != 3:
        out["not_found"] = missing + ([] if len(copy.points) == 3 else [f"{len(copy.points)} points found"])
    if copy.duplicate_values:
        out["duplicate_values"] = list(copy.duplicate_values)
    out["sorting_basis"] = copy.basis
    out["additional_customer_lines"] = list(copy.additional_customer_lines)
    return out


def version_number(copy: Copy, vocabulary: Vocabulary) -> int | None:
    found = re.search(r"\d+", copy.metadata.get(vocabulary.version, ""))
    return int(found.group()) if found else None


def identity(copy: Copy, brief: Brief, vocabulary: Vocabulary, previous: Copy | None = None, prior_numbers=()) -> dict:
    """Output identity compared with the source sheet's request date/model and an observed predecessor."""
    day = _day(copy.metadata.get(vocabulary.request_date, ""))
    version = version_number(copy, vocabulary)
    old_version = version_number(previous, vocabulary) if previous else 0
    expected_version = old_version + 1 if old_version is not None else None
    number = copy.number or ""
    expected_prefix = f"{brief.model}-{brief.day:%m%d}-" if brief.model and brief.day else None
    used = [*prior_numbers, *(brief.base), *(brief.exported), *([previous.number] if previous else [])]
    sequence = [
        int(number[len(expected_prefix) :])
        for number in used
        if number and expected_prefix and re.fullmatch(re.escape(expected_prefix) + r"[1-9]\d*", number)
    ]
    expected_number = f"{expected_prefix}{max(sequence, default=0) + 1}" if expected_prefix else None
    file_numbers = NUMBER.findall(copy.file)
    return {
        "request_date": str(day) if day else None,
        "request_date_matches": day == brief.day if day else False,
        "number_matches_request": bool(
            expected_prefix and re.fullmatch(re.escape(expected_prefix) + r"[1-9]\d*", number)
        ),
        "expected_number": expected_number,
        "sequence_matches": number == expected_number if expected_number else None,
        "file_number_matches": file_numbers == [number],
        "requester": copy.metadata.get(vocabulary.requester),
        "requester_present": bool(copy.metadata.get(vocabulary.requester)),
        "version": version,
        "expected_version": expected_version,
        "version_matches": version == expected_version if expected_version is not None else None,
        "replaces": copy.metadata.get(vocabulary.replaces),
        "replaces_matches": copy.metadata.get(vocabulary.replaces)
        == (previous.number if previous else vocabulary.no_replacement),
    }


def research_basis(copy: Copy, brief: Brief, exchanges, vocabulary: Vocabulary) -> dict:
    """Sample candidates only from the request's research, accepted prior basis, and actual requester answers."""
    pattern = re.compile(
        re.escape(vocabulary.sample_label) + r"[^\d\n]{0,8}(\d+)\s*" + re.escape(vocabulary.sample_unit)
    )
    sources = [*brief.research, *(turn.user for turn in exchanges)]
    if brief.previous and brief.previous.basis:
        sources.append(brief.previous.basis)
    expected = sorted({number for source in sources for number in pattern.findall(source)})
    actual = pattern.findall(copy.basis or "")
    return {
        "basis": copy.basis,
        "sample_candidates": expected,
        "sample_matches": actual == expected if len(expected) == 1 else None,
        "research_sources": list(brief.research),
        "limitation": "Check the study name/time and actual correction context semantically; ambiguous or missing sample candidates do not establish provenance.",
    }


def issuer_name(row: Row) -> str:
    """The issuer's name without the credentials annotation; the legal source permits its name alone."""
    return re.split(r"[" + re.escape("(" + _ROUND[0]) + r"]", row.issuer, maxsplit=1)[0].strip()


def quantities(text: str, vocabulary: Vocabulary) -> list[tuple[str, str]]:
    """Listed numeric-unit candidates; their absence does not establish a claim's support."""
    units = "|".join(map(re.escape, sorted(vocabulary.quantity_units, key=len, reverse=True)))
    return re.findall(r"(\d+(?:\.\d+)?)\s*(" + units + ")", text)


def evidence(
    copy: Copy, brief: Brief, expected: tuple[str, ...], vocabulary: Vocabulary, *, training=False
) -> list[dict]:
    """Per point of the latest version: the row it cites, how the row stood on the request date, and whether its
    usable wording, its condition and its footnotes stand in the point's evidence line (or, for a footnote, anywhere
    in the file) as the sheet has them."""
    out = []
    for n in sorted(set(copy.points) | set(copy.evidence)):
        ids = copy.evidence.get(n, ())
        entry: dict = {"point": n, "cited": list(ids)}
        if n <= len(expected):
            entry["expected"] = expected[n - 1]
        row = brief.rows.get(ids[0]) if ids else None
        if ids and row is None:
            entry["standing"] = "not in the card's sheet"
        if row is not None:
            raw = copy.rows.get(n, "")
            line = flat(raw)
            internal_label = (
                vocabulary.internal_label
                if training and brief.day and brief.day >= vocabulary.notice_from
                else vocabulary.internal_test
            )
            report_named = row.report in REPORT.findall(raw) if row.third else flat(internal_label) in line
            entry.update(
                concern=row.concern,
                standing=standing(row, brief.day, vocabulary),
                wording_copied=row.wording in raw,
                condition_copied=row.condition in raw,
                source_named=report_named and (training or not row.third or flat(issuer_name(row)) in line),
                report_named=report_named,
                issuer_named=flat(issuer_name(row)) in line if row.third else None,
                source_wording=row.wording,
                source_condition=row.condition,
                source_footnotes=list(row.notes),
            )
            if training:
                entry.pop("wording_copied")
            else:
                entry["type_named"] = vocabulary.third_party in raw if row.third else vocabulary.internal_test in raw
                entry["issued_copied"] = bool(row.issued) and str(row.issued) in raw
                entry["valid_until_copied"] = bool(row.valid) and str(row.valid) in raw
            if row.notes:
                in_line = all(note in raw for note in row.notes)
                in_file = in_line or all(note in copy.text for note in row.notes)
                entry["footnotes_copied"] = in_file
                entry["footnotes_where"] = "in the row" if in_line else ("elsewhere in the file" if in_file else None)
            backed = FIGURE.findall(row.wording + row.condition + "".join(row.notes))
            extra = [f for f in FIGURE.findall(MODEL.sub("", copy.points.get(n, ""))) if f not in backed]
            if extra:
                entry["point_figures_not_in_row"] = extra
            supported = quantities(row.wording + "; " + row.condition + "; ".join(row.notes), vocabulary)
            unsupported = [item for item in quantities(copy.points.get(n, ""), vocabulary) if item not in supported]
            if unsupported:
                entry["point_quantities_not_in_row"] = [{"value": value, "unit": unit} for value, unit in unsupported]
        out.append(entry)
    return out


def revision(previous: Copy, latest: Copy) -> dict:
    """How the latest version differs from the one it replaces, point by point."""
    out = {
        "previous": previous.number or previous.file,
        "latest": latest.number or latest.file,
        "new_number": None if not (previous.number and latest.number) else previous.number != latest.number,
        "previous_turn": previous.turn,
        "latest_turn": latest.turn,
        "previous_sha256": previous.sha256,
        "latest_sha256": latest.sha256,
        "title_unchanged": same(previous.title, latest.title),
        "proposition_unchanged": same(previous.proposition, latest.proposition),
        "points": [],
    }
    for n in sorted(set(previous.points) | set(latest.points)):
        before, after = previous.evidence.get(n, ())[:1], latest.evidence.get(n, ())[:1]
        out["points"].append(
            {
                "point": n,
                "text_unchanged": same(previous.points.get(n), latest.points.get(n)),
                "evidence": "unchanged"
                if before == after
                else f"{''.join(before) or 'none'} -> {''.join(after) or 'none'}",
                "evidence_text_unchanged": same(previous.rows.get(n), latest.rows.get(n)),
            }
        )
    return out


def agreement(card: Copy, screen: Copy | None) -> dict:
    """Whether the latest training card repeats the latest first screen."""
    out: dict = {"file": card.file, "number": card.number}
    if screen is None:
        out["first_screen"] = "not delivered"
        return out
    out["number_same"] = None if not (card.number and screen.number) else card.number == screen.number
    out["intro_same_as_proposition"] = same(card.intro, screen.proposition)
    out["points"] = [
        {
            "point": n,
            "text_same": same(card.points.get(n), screen.points.get(n)),
            "evidence_same": card.evidence.get(n, ())[:1] == screen.evidence.get(n, ())[:1],
        }
        for n in sorted(set(card.points) | set(screen.points))
    ]
    return out


def notes(copy: Copy, brief: Brief, vocabulary: Vocabulary) -> list[dict]:
    """Per point, the first-screen note the citation notice asks for: its source, its condition, its validity."""
    out = []
    for n in sorted(copy.points):
        ids = copy.evidence.get(n, ())
        row = brief.rows.get(ids[0]) if ids else None
        text = next((line for k, line in copy.notes if k == n), None)
        entry: dict = {"point": n, "note": text is not None}
        if text and row:
            body = flat(text)
            entry.update(
                source=(
                    row.report in REPORT.findall(text)
                    and flat(issuer_name(row)) in body
                    and vocabulary.report_label in text
                )
                if row.third
                else flat(vocabulary.internal_label) in body,
                condition=row.condition in text and all(note in text for note in row.notes),
                valid_until=bool(row.valid) and str(row.valid) in text,
            )
        out.append(entry)
    return out


def wording(copies: list[Copy], files: dict[str, str], vocabulary: Vocabulary) -> dict:
    """Absolute words, comparisons, scope words and efficacy words in the customer-facing lines of every version,
    and competitor-matrix terms anywhere in a delivered file outside the quoted sections."""
    measures = {
        "absolute": lambda line: absolutes(line, vocabulary),
        "comparison": lambda line: comparisons(line, vocabulary),
        "scope": lambda line: [word for word in vocabulary.scope_words if word in line],
        "efficacy": lambda line: [word for word in vocabulary.efficacy if word in line],
    }
    out: dict = {}
    for kind, measure in measures.items():
        for copy in copies:
            for line in copy_lines(copy):
                for word in measure(line):
                    out.setdefault(kind, {}).setdefault(f"file {copy.file}", {}).setdefault(word, []).append(
                        snippet(line, word)
                    )
    for name, text in files.items():
        for _, line in lines_of(text, vocabulary):
            for word in vocabulary.competitor:
                if word in line:
                    out.setdefault("competitor", {}).setdefault(f"file {name}", {}).setdefault(word, []).append(
                        snippet(line, word)
                    )
    return out


def scrub(text: str, vocabulary: Vocabulary) -> str:
    """A line without the numbers that are not figures: dates, clause references, version and row numbers,
    reports, models, point and footnote labels, length notes."""
    for pattern in (DAY, DATED, NUMBER, REPORT, ROW, MODEL):
        text = pattern.sub(" ", text)
    for word in (vocabulary.point, vocabulary.footnote):
        text = re.sub(rf"{re.escape(word)}\s*\d+", " ", text)
    return re.sub(rf"\d+\s*{re.escape(vocabulary.count_unit)}", " ", text)


def untraced(lines, sources, vocabulary: Vocabulary) -> list[str]:
    """Numeric membership candidates, each with its line; matching digits do not establish claim provenance."""
    known = set(FIGURE.findall("\n".join(sources)))
    out = []
    for line in lines:
        loose = [figure for figure in FIGURE.findall(scrub(line, vocabulary)) if figure not in known]
        if loose:
            out.append(f"{', '.join(dict.fromkeys(loose))}: {snippet(line, loose[0])}")
    return out


def register(found: tuple, screens: list[Copy], brief: Brief | None, vocabulary: Vocabulary) -> dict:
    """What the live register holds after the drill: the rows it gained, each against the delivered version it
    records; the rows it started with (the workdir's own table, else the materials' export) that changed or went;
    and the rows of the handout's export it never took in."""
    text, seen, start = found
    base = known_rows([start], vocabulary) if start else (brief.base if brief else {})
    exported = brief.exported if brief else {}
    out: dict = {"path": vocabulary.register_path, "seen_in": seen}
    if text is None:
        out["observed"] = seen is not None
        if seen is not None:
            out["exists"] = False
        return out
    rows = entries(text, vocabulary)
    headers = [table[0] for table in tables(text) if table and vocabulary.number in table[0][0]]
    out["header_matches"] = headers == [list(vocabulary.register_columns)]
    out["observed"], out["exists"], out["rows"] = True, True, len(rows)
    numbers = {row.number for row in rows}
    out["duplicate_numbers"] = sorted(
        number for number in numbers if number and sum(row.number == number for row in rows) > 1
    )
    out["missing_delivered_versions"] = sorted({copy.number for copy in screens if copy.number} - numbers)
    columns = vocabulary.register_columns
    by_number = {copy.number: copy for copy in screens if copy.number}
    appended = []
    for row in rows:
        if row.number in base or row.number in exported:
            continue
        evidence_cell = row.named.get(columns[10], row.line)
        entry = {
            "number": row.number,
            "version": row.named.get(columns[4]),
            "replaces": row.named.get(columns[5]),
            "evidence": ROW.findall(evidence_cell),
        }
        copy = by_number.get(row.number)
        if copy is None:
            entry["delivered_version"] = "none delivered under this number"
        else:
            entry["matches_delivered"] = {
                "proposition": same(row.named.get(columns[6]), copy.proposition),
                "points": [same(row.named.get(columns[6 + n]), copy.points.get(n)) for n in (1, 2, 3)],
                "evidence": entry["evidence"] == [copy.evidence.get(n, ("",))[0] for n in sorted(copy.points)],
                "request_date": _day(row.named.get(columns[1], "")) == brief.day if brief and brief.day else None,
                "model": row.named.get(columns[2]) == brief.model if brief and brief.model else None,
                "requester": same(row.named.get(columns[3]), copy.metadata.get(vocabulary.requester)),
                "version": row.named.get(columns[4]) == str(version_number(copy, vocabulary)),
                "replaces": same(row.named.get(columns[5]), copy.metadata.get(vocabulary.replaces)),
                "files": sorted(
                    Path(name).name
                    for name in re.findall(
                        r"[^;\s]+\.md", unicodedata.normalize("NFKC", row.named.get(columns[11], ""))
                    )
                )
                == sorted(f"{prefix}-{copy.number}.md" for prefix in vocabulary.file_names),
            }
        appended.append(entry)
    out["appended"] = appended
    imported_positions = [n for n, row in enumerate(rows) if row.number in base or row.number in exported]
    appended_positions = [n for n, row in enumerate(rows) if row.number not in base and row.number not in exported]
    out["appended_after_imports"] = (
        not appended_positions or not imported_positions or min(appended_positions) > max(imported_positions)
    )
    out["starting_rows"] = len(base)
    out["starting_rows_changed"] = sorted(
        row.number for row in rows if row.number in base and row.line != base[row.number]
    )
    out["starting_rows_lost"] = sorted(number for number in base if number not in numbers)
    out["starting_order_preserved"] = [row.number for row in rows if row.number in base] == list(base)
    if exported:
        out["export_rows_absent"] = sorted(number for number in exported if number not in numbers)
        out["export_rows_changed"] = sorted(
            row.number
            for row in rows
            if row.number in exported and (not start or row.number not in base) and row.line != exported[row.number]
        )
    return out


def _matches(path, relative: str) -> bool:
    path = str(path or "").replace("\\", "/")
    return path == relative or path.endswith("/" + relative)


def from_records(exchanges, relative: str, start: str | None) -> tuple[str | None, bool]:
    """The register as the drill's recorded file writes leave it: a whole write's or an edit's resulting text, an
    append added to what stood before. A tool that wrote it without recording its content is not seen."""
    content, seen, pending = start, False, defaultdict(deque)
    for turn in exchanges:
        for row in turn.execution.records:
            if row.get("kind") != "runner.event" or row.get("event_type", "ToolEvent") != "ToolEvent":
                continue
            event = row.get("event") or {}
            if event.get("phase") == "start":
                pending[event.get("tool_call_id")].append(event)
            elif event.get("phase") == "complete":
                queue = pending[event.get("tool_call_id")]
                begun = queue.popleft() if queue else {}
                arguments = begun.get("arguments") or {}
                change = event.get("file_change") or {}
                relevant = _matches(change.get("path"), relative) or (
                    begun.get("name") in {"write_file", "edit_file"} and _matches(arguments.get("path"), relative)
                )
                if event.get("ok") is not True:
                    if event.get("ok") is not False and relevant:
                        content, seen = None, False
                    continue
                if _matches(change.get("path"), relative) and isinstance(change.get("after"), str):
                    content, seen = change["after"], True
                elif begun.get("name") == "write_file" and arguments.get("mode") == "append" and relevant:
                    if content is not None:
                        content, seen = content + str(arguments.get("content") or ""), True
    if any(
        event.get("name") in {"write_file", "edit_file"}
        and _matches((event.get("arguments") or {}).get("path"), relative)
        for queue in pending.values()
        for event in queue
    ):
        return None, False
    return content, seen


def live_register(exchanges, vocabulary: Vocabulary, *, workdir=None, baseline=None) -> tuple:
    """(the register's text after the drill, where it was read, its text before the drill): read from the drill's
    replica workdir when the drill played on one, else rebuilt from the drill's recorded writes; `baseline` is the
    employee's own workdir, where every replica starts."""
    relative = vocabulary.register_path
    own = Path(baseline) / relative if baseline else None
    start = own.read_text() if own is not None and own.is_file() else None
    if workdir is not None:
        file = Path(workdir) / relative
        return (file.read_text() if file.is_file() else None), "workdir", start
    text, seen = from_records(exchanges, relative, start)
    return text, "records" if seen else None, start


def facts(
    exchanges,
    vocabulary: Vocabulary,
    brief: Brief | None = None,
    found_register=(None, None, None),
    expected=None,
    materials=(),
) -> dict:
    """The brand lead's facts for one drill, keyed by what each measures; a key is left out when nothing was found.
    `materials` are the texts of the materials the employee holds, which count as sources for its figures."""
    unreadable = []
    screens = versions(exchanges, vocabulary, training=False, unavailable=unreadable)
    cards = versions(exchanges, vocabulary, training=True, unavailable=unreadable)
    deliveries = delivery_versions(exchanges)
    files = {name: text for delivery in deliveries for name, text in delivery["files"].items()}
    files.update({copy.file: copy.text for copy in (*screens, *cards)})
    points = expected_points(expected) or (brief.expected if brief else ())
    skipped = expected_skipped(expected) or (brief.skipped if brief else ())
    out: dict = {}
    if brief is not None or deliveries:
        out["delivery"] = {
            "first_screen_retained": bool(screens),
            "training_card_retained": bool(cards),
            "unavailable": [
                {"turn": delivery["turn"], "files": delivery["unavailable"]}
                for delivery in deliveries
                if delivery["unavailable"]
            ],
            "unreadable": unreadable,
            "versions": [
                {
                    "turn": copy.turn,
                    "turn_id": exchanges[copy.turn - 1].execution.turn_id,
                    "artifact_id": exchanges[copy.turn - 1].execution.artifact_id,
                    "file": copy.file,
                    "number": copy.number,
                    "sha256": copy.sha256,
                }
                for copy in (*screens, *cards)
            ],
            "measurement_limit": "Parsed labels, scalar membership and lexical hits are partial facts. Check raw files, source-specific values and units, audience, scope, and verified requester answers independently.",
        }
    if brief is not None:
        out["card"] = {
            "name": brief.card,
            "request_date": str(brief.day) if brief.day else None,
            "model": brief.model,
            "expected_points": list(points),
        }
    latest = screens[-1] if screens else None
    if latest is not None:
        out["first_screen"] = shape(latest, vocabulary)
        if skipped:
            out["skipped_concerns"] = {
                "skipped": list(skipped),
                "promised_in_proposition": [c for c in skipped if c in (latest.proposition or "")],
            }
        if brief is not None and brief.rows:
            out["evidence"] = evidence(latest, brief, points, vocabulary)
        previous = screens[-2] if len(screens) > 1 else (brief.previous if brief else None)
        if brief is not None:
            starting = known_rows([found_register[2]], vocabulary) if found_register[2] else {}
            out["identity"] = identity(
                latest, brief, vocabulary, previous, [*starting, *(copy.number for copy in screens[:-1])]
            )
            out["research_basis"] = research_basis(latest, brief, exchanges, vocabulary)
        if previous is not None:
            out["revision"] = revision(previous, latest)
        if brief is not None and brief.day and brief.day >= vocabulary.notice_from:
            out["notes"] = {"required": True, "points": notes(latest, brief, vocabulary)}
    if cards:
        out["training_card"] = agreement(cards[-1], latest)
        if brief is not None and brief.rows:
            out["training_evidence"] = evidence(cards[-1], brief, points, vocabulary, training=True)
        previous_card = cards[-2] if len(cards) > 1 else (brief.previous_training if brief else None)
        if previous_card is not None:
            out["training_revision"] = revision(previous_card, cards[-1])
            out["training_revision"]["intro_unchanged"] = same(previous_card.intro, cards[-1].intro)
            out["training_revision"]["customer_lines"] = [
                {"point": n, "text_unchanged": same(previous_card.says.get(n), cards[-1].says.get(n))}
                for n in sorted(set(previous_card.says) | set(cards[-1].says))
            ]
    elif latest is not None:
        out["training_card"] = "no training card delivered"
    measured = wording([*screens[-1:], *cards[-1:]], files, vocabulary)
    if measured:
        out["wording"] = measured
    sources = [*(brief.handed if brief else ()), *(turn.user for turn in exchanges), *materials]
    loose = {
        copy.file: found
        for copy in (*screens[-1:], *cards[-1:])
        if (found := untraced(copy_lines(copy), sources, vocabulary))
    }
    if loose:
        out["untraced_figures"] = loose
    if latest is not None and latest.basis:
        basis = untraced([latest.basis], sources, vocabulary)
        if basis:
            out["basis_figures_untraced"] = basis
    if files or found_register[0] is not None:
        out["register"] = register(found_register, screens, brief, vocabulary)
    if files:
        out["delivered_files"] = sorted(files)
    return out


class LaunchOwner(Owner):
    """The brand lead of the launch copy scenario, measuring each drill with the case's word table and sheets."""

    def __init__(self, scenario, provider, skills, **options):
        super().__init__(scenario, provider, skills, facts=self._facts, **options)
        self.vocabulary = Vocabulary.load(Path(scenario.root) / CONFIG)
        self.briefs = briefs(scenario.contract, self.vocabulary)

    def _facts(self, name, exchanges, card) -> dict:
        brief = self.briefs.get(card_of(name, card, self.briefs))
        placed = self.workdirs.get(name)
        found = live_register(
            exchanges, self.vocabulary, workdir=placed["workdir"] if placed else None, baseline=self.workdir
        )
        held = tuple(self.scenario.text(material) for material in self.released)
        measured = facts(exchanges, self.vocabulary, brief, found, getattr(card, "expected", None), held)
        measured["source_case_digest"] = digest(Path(self.scenario.root))
        return measured


# The owner the simulation entry judges this case by (`experimental.simulation.__main__.owner_of`).
OWNER = LaunchOwner


def launch_delivered(item: dict) -> bool:
    """Use each filename's last retained occurrence in the latest copy-bearing turn; content needs the rubric."""
    root = Path(item.get("scenario_root") or Path(__file__).parent)
    vocabulary = Vocabulary.load(root / CONFIG)
    drills = item.get("drills", [])
    if not drills:
        return False
    for drill in drills:
        latest = None
        for turn in drill.get("exchanges", []):
            files = [
                file
                for file in turn.get("delivered", [])
                if any(prefix in file.get("name", "") for prefix in vocabulary.file_names)
            ]
            if files:
                latest = {file["name"]: file for file in files}
        if latest is None:
            return False
        found = []
        for prefix in vocabulary.file_names:
            matches = [
                file
                for file in latest.values()
                if re.fullmatch(re.escape(prefix) + r"-[A-Z]{2}\d-\d{4}-[1-9]\d*\.md", file.get("name", ""))
            ]
            if len(matches) != 1 or not matches[0].get("path") or not matches[0].get("sha256"):
                return False
            found.append(NUMBER.findall(matches[0]["name"])[0])
        if found[0] != found[1]:
            return False
    return True


DELIVERED = launch_delivered
