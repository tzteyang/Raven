"""The content compliance owner: the generic `Owner` with the facts the head of legal and compliance judges a drill by.

From the case's own materials (the filings table, the evidence table and its update, the registration notice) and the
card's handouts (the submission form with each note's text, the image list) it computes, for every note the card
submits, what the evidence gives on the note's publish date and which marks the note needs. From what the employee
wrote, filed and delivered it reads the light each review card gives, the reports each card cites, the word-table hits
and marks in each rewrite, the five sections of each card, what each release slip releases and what light those notes
had when the slip was written, the legal referrals, the ledger rows, the order of the writes, and any web link or
penalty case anywhere. The owner's model still decides every verdict; the words, folder names and table headings are
the scenario's, read from its `reference.md`.
"""

import re
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
from pathlib import Path

from experimental.cultivation.counterpart.owner import Owner, delivery_versions
from experimental.cultivation.counterpart.rulers import CONFIG, delivered, messages, occurrences, tables, words
from experimental.harness.raven_adapter.action.runtime import REFUSED
from experimental.harness.scenario.contract import frontmatter
from experimental.simulation.bench.scenario import Scenario

COLORS = ("red", "yellow", "green")
WRITERS = ("write_file", "edit_file")
HOLDOUT = "holdout-"
TEXTS = (".md", ".txt", ".csv", ".json")
DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
URL = re.compile(r"https?://\S+|www\.\S+")
EXPECTED_LINE = re.compile(r"^\s*(lights|recheck):(.*)$", re.M)
# A markdown heading; a line such as a topic tag list starting with `#` and no space is body text.
HEADING = re.compile(r"\s*#{1,6}\s")
# Full-width parentheses and the enumeration comma, spelled by code point so the source stays in ASCII.
PARENS = re.compile(f"{chr(0xFF08)}[^{chr(0xFF09)}]*{chr(0xFF09)}")
SNIPPET = 60


@dataclass(frozen=True)
class Vocabulary:
    """The words, headings and patterns of the scenario's `reference.md`."""

    found: dict

    @classmethod
    def load(cls, root: Path) -> "Vocabulary":
        return cls(words(Path(root) / CONFIG))

    def __getitem__(self, key: str) -> tuple[str, ...]:
        return self.found[key]

    def one(self, key: str) -> str:
        return self.found[key][0]

    def pattern(self, key: str) -> re.Pattern:
        return re.compile(self.one(key))

    @property
    def folders(self) -> dict[str, str]:
        return {
            "card": self.one("card_folder"),
            "slip": self.one("slip_folder"),
            "legal": self.one("legal_folder"),
            "ledger": self.one("ledger_folder"),
        }


def _day(text: str) -> date | None:
    found = DAY.search(text or "")
    return date.fromisoformat(found.group()) if found else None


def _column(header: list[str], keys) -> int | None:
    return next((index for index, cell in enumerate(header) if any(key in cell for key in keys)), None)


def _rows(text: str, *keys: tuple[str, ...]) -> list[list[str | None]]:
    """For every table whose header has a column for each key group, its rows reduced to those columns."""
    out = []
    for found in tables(text):
        header, *body = found
        columns = [_column(header, group) for group in keys]
        if any(column is None for column in columns):
            continue
        out += [[row[column] if column < len(row) else None for column in columns] for row in body]
    return out


@dataclass(frozen=True)
class Version:
    """One row of the evidence table, an update or a registration: what it covers and from when to when."""

    report: str
    formulas: frozenset[str]
    start: date
    until: date
    phrase: str
    review_from: date | None = None


@dataclass(frozen=True)
class Evidence:
    versions: tuple[Version, ...]
    registrations: tuple[Version, ...]
    products: dict[str, frozenset[str]]

    @classmethod
    def load(cls, scenario, vocabulary: Vocabulary) -> "Evidence":
        def text(name):
            return frontmatter(scenario.text(name))[1] if name in scenario.materials else ""

        def versions(names, identifier):
            out = []
            for name in names:
                for table in tables(text(name)):
                    header, *body = table
                    columns = [
                        _column(header, vocabulary[key])
                        for key in ("report_column", "formula_column", "from_columns", "until_column", "phrase_column")
                    ]
                    if any(column is None for column in columns):
                        continue
                    change = _column(header, vocabulary["change_column"])
                    for row in body:
                        values = [row[column] if column < len(row) else "" for column in columns]
                        report, formulas, start, until, phrase = values
                        corrected = (
                            change is not None
                            and change < len(row)
                            and any(word in row[change] for word in vocabulary["correction_words"])
                        )
                        found = identifier.search(report or "")
                        first, last = _day(start), _day(until)
                        if found and first and last:
                            out.append(
                                Version(
                                    found.group(),
                                    frozenset(vocabulary.pattern("formula_id").findall(formulas or "")),
                                    first,
                                    last,
                                    phrase or "",
                                    first if corrected else None,
                                )
                            )
            return tuple(out)

        registered = []
        for name in vocabulary["registration"]:
            for number, formulas, start, until in _rows(
                text(name),
                vocabulary["report_column"],
                vocabulary["formula_column"],
                vocabulary["from_columns"],
                vocabulary["until_column"],
            ):
                found = vocabulary.pattern("registration_id").search(number or "")
                if found and _day(start) and _day(until):
                    formula_ids = frozenset(vocabulary.pattern("formula_id").findall(formulas or ""))
                    registered.append(Version(found.group(), formula_ids, _day(start), _day(until), ""))
        products = {}
        for filings in vocabulary["filings"]:
            for product, formulas in _rows(text(filings), vocabulary["name_column"], vocabulary["formula_column"]):
                if product:
                    products[product] = frozenset(vocabulary.pattern("formula_id").findall(formulas or ""))
        return cls(versions(vocabulary["evidence"], vocabulary.pattern("report_id")), tuple(registered), products)

    def status(self, report: str, formulas, publish: date | None, review: date | None = None) -> str:
        """Whether `report` backs a claim on a product of `formulas` published on `publish`."""
        rows = [row for row in self.versions if row.report == report] or [
            row for row in self.registrations if row.report == report
        ]
        if not rows:
            return "not in the evidence tables"
        if publish is None:
            return "publish date unknown"
        if not formulas:
            return "product formula unknown"
        if any(row.review_from is not None for row in rows) and review is None:
            return "review date unknown for a coverage correction"
        live = [
            row for row in rows if (row.review_from <= review if row.review_from is not None else row.start <= publish)
        ]
        if not live:
            return f"not in force until {min(row.start for row in rows).isoformat()}"
        row = max(live, key=lambda version: version.start)
        if publish > row.until:
            return f"expired {row.until.isoformat()}"
        if not set(formulas) <= row.formulas:
            return f"covers only {', '.join(sorted(row.formulas))}"
        return "usable"

    def formulas_of(self, product: str) -> frozenset[str]:
        names = [name for name in self.products if name in (product or "")]
        return self.products[max(names, key=len)] if names else frozenset()

    def relevant(self, formulas) -> list[str]:
        ids = [row.report for row in (*self.versions, *self.registrations) if set(formulas) & row.formulas]
        return list(dict.fromkeys(ids))

    def starred(self, formulas, publish: date | None, review: date | None = None) -> dict[str, str]:
        """The asterisked approved phrases usable for these formulas on that day, normalised, by report."""
        out = {}
        for row in self.versions:
            if "*" in row.phrase and self.status(row.report, formulas, publish, review) == "usable":
                out[row.report] = _normal(row.phrase)
        return out


def _normal(text: str) -> str:
    return re.sub(r"[\s*]", "", PARENS.sub("", text or ""))


@dataclass(frozen=True)
class Note:
    id: str
    product: str
    formulas: frozenset[str]
    publish: date | None
    link: str
    statement: str
    text: str
    images: tuple[tuple[str, str, str], ...]
    review: date | None = None
    submission: str = ""


def card_name(name: str, card) -> str:
    """The card a drill played: the card's own name, or the session name without the exam prefix and repeat."""
    if card is not None and getattr(card, "name", None):
        return card.name
    base = name[len(HOLDOUT) :] if name.startswith(HOLDOUT) else name
    return re.sub(r"-\d+$", "", base)


def notes_of(root: Path, card: str, vocabulary: Vocabulary, evidence: Evidence) -> dict[str, Note]:
    """The notes a card submits, read from its handouts: the submission form and the image list."""
    folder = Path(root) / "handouts" / card
    if not folder.is_dir():
        return {}
    note_id = vocabulary.pattern("note_id")
    texts = {path.name: path.read_text() for path in folder.glob("*.md")}
    form = next((text for name, text in texts.items() if name.startswith(vocabulary.one("submission_file"))), "")
    listing = next((text for name, text in texts.items() if name.startswith(vocabulary.one("image_file"))), "")
    images: dict[str, list[tuple[str, str, str]]] = {}
    for number, place, method, label in _rows(
        listing,
        vocabulary["note_column"],
        vocabulary["place_column"],
        vocabulary["method_column"],
        vocabulary["label_column"],
    ):
        found = note_id.search(number or "")
        if found:
            images.setdefault(found.group(), []).append((place or "", method or "", label or ""))
    notes = {}
    for number, product, publish, link, statement in _rows(
        form,
        vocabulary["note_column"],
        vocabulary["product_column"],
        vocabulary["publish_column"],
        vocabulary["link_column"],
        vocabulary["statement_column"],
    ):
        found = note_id.search(number or "")
        if not found:
            continue
        key = found.group()
        notes[key] = Note(
            key,
            product or "",
            evidence.formulas_of(product or ""),
            _day(publish or ""),
            link or "",
            statement or "",
            _note_text(form, key),
            tuple(images.get(key, ())),
            _day(_metadata(form, vocabulary).get(vocabulary.one("submitted_key"), "")),
            _metadata(form, vocabulary).get(vocabulary.one("batch_key"), ""),
        )
    return notes


def _metadata(text: str, vocabulary: Vocabulary) -> dict[str, str]:
    return dict(_rows(text, vocabulary["item_column"], vocabulary["value_column"]))


def _note_text(form: str, key: str) -> str:
    lines, out, inside = form.splitlines(), [], False
    for line in lines:
        if HEADING.match(line):
            inside = line.startswith("###") and key in line
            continue
        if inside:
            out.append(line)
    return "\n".join(out).strip()


def reference_of(note: Note, vocabulary: Vocabulary, evidence: Evidence) -> dict:
    """What the materials give for one note on its publish date, and each mark it needs, present or missing in the
    note as submitted."""
    ai, none = vocabulary.one("ai"), set(vocabulary["none"])
    first = next((line for line in note.text.splitlines() if line.strip()), "")

    def state(present: bool) -> str:
        return "present" if present else "missing"

    needs = []
    ai_images = [image for image in note.images if ai in image[1]]
    for place, method, label in ai_images:
        needs.append(f"image {place} label at top-left ({method}; label now: {label})")
    if ai_images:
        needs.append(f"first-line AI statement: {state(any(mark in first for mark in vocabulary['ai_marks']))}")
        needs.append(f"platform AI statement: form says {note.statement}")
    if note.link.strip() and note.link.strip() not in none:
        needs.append(
            f"advert mark in first line ({note.link}): {state(any(m in first for m in vocabulary['ad_marks']))}"
        )
    text = _normal(note.text)
    for report, phrase in evidence.starred(note.formulas, note.publish, note.review).items():
        if phrase and phrase in text:
            needs.append(f"footnote required for {report}; report identifier mention: {state(report in note.text)}")
    prefix = _common_prefix(list(evidence.products))
    for row in evidence.registrations:
        named = [name for name, formulas in evidence.products.items() if formulas and formulas <= row.formulas]
        names = {*named, *(name[len(prefix) :] for name in named if prefix)}
        about = bool(note.formulas) and note.formulas <= row.formulas
        if about or any(name and name in note.text for name in names):
            needs.append(
                f"registration number {row.report} where the registered product or efficacy is named: "
                f"exact identifier mention: {state(row.report in note.text)}; full placement/subject still require review"
            )
    return {
        "product": note.product,
        "formulas": sorted(note.formulas),
        "publish": note.publish.isoformat() if note.publish else None,
        "review": note.review.isoformat() if note.review else None,
        "evidence_on_publish_date": {
            report: evidence.status(report, note.formulas, note.publish, note.review)
            for report in evidence.relevant(note.formulas)
        },
        "needs": needs,
    }


def _common_prefix(names: list[str]) -> str:
    if not names:
        return ""
    prefix = names[0]
    for name in names[1:]:
        while not name.startswith(prefix):
            prefix = prefix[:-1]
    return prefix


def expected_lights(text: str | None, vocabulary: Vocabulary) -> dict[str, dict[str, str]]:
    """The lights the card's expected answer gives: per note, `initial` and `recheck`."""
    found: dict[str, dict[str, str]] = {}
    pair = re.compile(rf"({vocabulary.one('note_id')})\s+(red|yellow|green)")
    for kind, rest in EXPECTED_LINE.findall(text or ""):
        for note, color in pair.findall(rest):
            found.setdefault(note, {})["initial" if kind == "lights" else "recheck"] = color
    return found


def _expected_text(root: Path, card: str, given) -> str | None:
    if given:
        return given
    path = Path(root) / "personas" / f"{card}.md"
    if not path.is_file():
        return None
    head, _ = frontmatter(path.read_text())
    return head.get("expected")


# What the employee wrote.


def _key(path: str, vocabulary: Vocabulary, *, workdir: Path | None = None, home: Path | None = None) -> str | None:
    """Preserve a file's business/private origin; an unresolved absolute path remains unscoped."""
    file = Path(path)
    parts = file.parts
    if "uploads" in parts:
        return None
    if not parts:
        return None
    if parts[0] in ("workdir", "home", "delivered"):
        return file.as_posix()
    if file.is_absolute():
        for origin, root in (("workdir", workdir), ("home", home)):
            if root is not None and file.is_relative_to(root):
                return f"{origin}/{file.relative_to(root).as_posix()}"
        return f"unscoped/{file.as_posix().lstrip('/')}"
    if ".." in parts:
        return f"unscoped/{file.as_posix()}"
    return f"workdir/{file.as_posix()}"


def _events(records, scope=()):
    for index, row in enumerate(records or ()):
        if not isinstance(row, dict):
            continue
        if row.get("kind") == "runner.event":
            yield {**(row.get("event") or {}), "_scope": scope}
        elif row.get("kind") == "child.execution":
            yield from _events(row.get("records"), (*scope, index))


def _operations(exchanges, *, success_only=True):
    """Matched operations in completion order; unknown or refused outcomes do not prove success."""
    for turn, exchange in enumerate(exchanges, start=1):
        pending = defaultdict(deque)
        for index, event in enumerate(_events(exchange.execution.records)):
            call_id = event.get("tool_call_id")
            call = (event.get("_scope"), call_id)
            if event.get("phase") == "start" and call_id:
                pending[call].append(event)
            elif event.get("phase") == "complete" and call_id and pending[call]:
                start = pending[call].popleft()
                succeeded = event.get("ok") is True and not str(event.get("result_preview") or "").startswith(REFUSED)
                if succeeded or not success_only:
                    yield turn, index, start, event
        if not success_only:
            for waiting in pending.values():
                for start in waiting:
                    yield turn, -1, start, {}


def _write_snapshots(exchanges, vocabulary: Vocabulary, **roots):
    """Successful writes whose complete post-write text is available, in operation order."""
    out, known = [], {}
    for turn, index, start, event in _operations(exchanges):
        change, arguments = event.get("file_change"), start.get("arguments") or {}
        if isinstance(change, dict) and isinstance(change.get("after"), str):
            path, content = str(change.get("path") or arguments.get("path") or ""), change["after"]
        elif start.get("name") == "write_file" and isinstance(arguments.get("content"), str):
            path, content = str(arguments.get("path") or ""), arguments["content"]
            key = _key(path, vocabulary, **roots)
            if arguments.get("mode") == "append":
                if key not in known:
                    continue
                content = known[key] + content
        else:
            continue
        key = _key(path, vocabulary, **roots)
        if key and Path(key).suffix.lower() in TEXTS:
            known[key] = content
            out.append((turn, index, key, content))
    return out


def writes(exchanges, vocabulary: Vocabulary, **roots) -> list[tuple[int, str, str]]:
    """Retained complete successful write snapshots, not a final file inventory."""
    return [(turn, key, content) for turn, _, key, content in _write_snapshots(exchanges, vocabulary, **roots)]


def documents(exchanges, vocabulary: Vocabulary, filed: dict | None = None) -> dict[str, str]:
    """Verified final filed texts and retained delivered files; write history cannot prove final presence."""
    docs = {}
    for path, content in (filed or {}).items():
        key = _key(path, vocabulary)
        if (
            key
            and Path(key).suffix.lower() in TEXTS
            and isinstance(content, str)
            and "content not shown]" not in content
        ):
            docs[key] = content
    for name, content in delivered(exchanges).items():
        if Path(name).suffix.lower() in TEXTS:
            docs[f"delivered/{name}"] = content
    return docs


def kind_of(key: str, text: str, vocabulary: Vocabulary) -> str:
    folders = vocabulary.folders
    parts = Path(key).parts
    for kind, folder in folders.items():
        if folder in parts:
            return kind
    first = next((line for line in text.splitlines() if line.strip()), "")
    if folders["slip"] in Path(key).name or folders["slip"] in first:
        return "slip"
    if vocabulary.one("light_marker") in text:
        return "card"
    return "other"


def segments(key: str, text: str, vocabulary: Vocabulary) -> list[tuple[str | None, bool, str]]:
    """A card file cut into (note, recheck, text): at every heading naming a note, else the whole file for the note
    its name or text names."""
    note_id = vocabulary.pattern("note_id")
    recheck = vocabulary.one("recheck")
    lines = text.splitlines()
    starts = [index for index, line in enumerate(lines) if HEADING.match(line) and note_id.search(line)]
    named = note_id.search(Path(key).name)
    if not starts:
        mentioned = set(note_id.findall(text))
        note = named.group() if named else (mentioned.pop() if len(mentioned) == 1 else None)
        first = next((line for line in lines if line.strip()), "")
        return [(note, recheck in Path(key).name or recheck in first, text)]
    out = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        heading = lines[start]
        part = "\n".join(lines[start:end])
        out.append((note_id.search(heading).group(), recheck in heading or recheck in Path(key).name, part))
    return out


def light_in(text: str, vocabulary: Vocabulary) -> str | None:
    """The last light a text gives on a line carrying the light marker."""
    marker, lights = vocabulary.one("light_marker"), vocabulary["lights"]
    found = None
    for line in text.splitlines():
        if marker not in line:
            continue
        rest = line[line.index(marker) + len(marker) :]
        hits = [(rest.index(word), color) for word, color in zip(lights, COLORS, strict=True) if word in rest]
        if hits:
            found = min(hits)[1]
    return found


def lights_of(part: str, recheck: bool, vocabulary: Vocabulary) -> dict[str, str]:
    """A card segment's lights: `recheck` for a recheck card or for what follows a recheck heading appended to an
    initial card, `initial` for the rest."""
    word = vocabulary.one("recheck")
    lines = part.splitlines()
    cut = next(
        (index for index, line in enumerate(lines) if index and HEADING.match(line) and word in line),
        None,
    )
    if recheck:
        before, after = "", part
    elif cut is not None:
        before, after = "\n".join(lines[:cut]), "\n".join(lines[cut:])
    else:
        before, after = part, ""
    found = {}
    for kind, text in (("initial", before), ("recheck", after)):
        light = light_in(text, vocabulary)
        if light:
            found[kind] = light
    return found


def _section_line(line: str, word: str) -> bool:
    stripped = line.strip().strip("*").strip()
    return word in stripped and (bool(HEADING.match(stripped)) or (stripped.find(word) <= 8 and len(stripped) <= 40))


def missing_sections(text: str, vocabulary: Vocabulary) -> list[str]:
    lines = text.splitlines()
    return [word for word in vocabulary["sections"] if not any(_section_line(line, word) for line in lines)]


def _header_value(text: str, label: str) -> str:
    colon, divider = chr(0xFF1A), chr(0xFF5C)
    pattern = rf"(?:^|[{divider}|])\s*{re.escape(label)}\s*[:{colon}]\s*([^\n{divider}|]+)"
    found = re.search(pattern, text, re.M)
    return found.group(1).strip() if found else ""


def _section_contents(text: str, vocabulary: Vocabulary) -> dict[str, str]:
    found, current = {word: [] for word in vocabulary["sections"]}, None
    for line in text.splitlines():
        heading = next((word for word in vocabulary["sections"] if _section_line(line, word)), None)
        if heading:
            current = heading
        elif current:
            found[current].append(line)
    return {word: "\n".join(lines).strip() for word, lines in found.items()}


def _complete_card(text: str, note: str, submission: str, vocabulary: Vocabulary) -> bool:
    if "characters not shown]" in text:
        return False
    headers = vocabulary["card_headers"]
    if any(not _header_value(text, label) for label in headers):
        return False
    if _header_value(text, headers[0]) != note or _header_value(text, headers[1]) != submission:
        return False
    sections = _section_contents(text, vocabulary)
    if not all(sections.values()) or light_in(sections[vocabulary["sections"][0]], vocabulary) is None:
        return False
    rewrite = sections[vocabulary.one("rewrite")]
    if light_in(text, vocabulary) != "green":
        if not _header_value(rewrite, vocabulary.one("title_marker")):
            return False
        body = vocabulary.one("body_marker")
        colon = chr(0xFF1A)
        marker = re.search(rf"(?m)^\s*{re.escape(body)}\s*[:{colon}]\s*\n", rewrite)
        if marker is None or not rewrite[marker.end() :].strip():
            return False
    return True


def rewrite_of(text: str, vocabulary: Vocabulary) -> str:
    """The rewrite section of a card: from its heading to the next section heading."""
    word = vocabulary.one("rewrite")
    others = [other for other in vocabulary["sections"] if other != word]
    out, inside = [], False
    for line in text.splitlines():
        if _section_line(line, word):
            inside = True
            continue
        if inside and any(_section_line(line, other) for other in others):
            break
        if inside:
            out.append(line)
    return "\n".join(out).strip()


def rewrite_facts(rewrite: str, note: Note | None, vocabulary: Vocabulary, evidence: Evidence) -> dict:
    if not rewrite:
        return {"rewrite": "none found"}
    found = {"scope": "Lexical occurrences only; inspect claim subject, supported equivalence and full footnotes."}
    for key in ("special_words", "medical_words", "absolute_words", "testimony_words"):
        hits = occurrences(rewrite, vocabulary[key])
        if hits:
            found[key] = hits
    lines = [line.strip() for line in rewrite.splitlines() if line.strip()]
    body = vocabulary.one("body_marker")
    start = next((index for index, line in enumerate(lines) if line.startswith(body)), None)
    opening = lines[start + 1 : start + 3] if start is not None else lines[:2]
    found["opening_lines"] = opening
    found["ai_mark_occurs"] = any(mark in rewrite for mark in vocabulary["ai_marks"])
    found["advert_mark_occurs"] = any(mark in rewrite for mark in vocabulary["ad_marks"])
    found["report_identifiers_mentioned"] = sorted(set(vocabulary.pattern("report_id").findall(rewrite)))
    found["registration_identifiers_mentioned"] = sorted(set(vocabulary.pattern("registration_id").findall(rewrite)))
    units = "|".join(re.escape(unit) for unit in vocabulary["quantity_units"])
    quantified = [line[:SNIPPET] for line in lines if re.search(rf"\d+\s*(?:{units})", line)]
    if quantified and not found["report_identifiers_mentioned"]:
        found["quantity_lines_without_report_mention"] = quantified
    if note is not None:
        text, written = _normal(note.text), _normal(rewrite)
        backed = evidence.starred(note.formulas, note.publish, note.review)
        points = {report: phrase for report, phrase in backed.items() if phrase in text}
        if points:
            found["literal_source_phrase_mentions"] = {report: phrase in written for report, phrase in points.items()}
    return found


def slip_notes(text: str, vocabulary: Vocabulary) -> dict[str, str]:
    """What a slip says of each note: `released` or `withheld`; table rows decide when the slip has any."""
    note_id = vocabulary.pattern("note_id")
    lines = [line for line in text.splitlines() if note_id.search(line)]
    rows = [line for line in lines if line.strip().startswith("|")]
    found = {}
    for line in rows or lines:
        if any(word in line for word in vocabulary["withheld"]):
            state = "withheld"
        elif any(word in line for word in vocabulary["released"]):
            state = "released"
        else:
            continue
        for note in note_id.findall(line):
            found[note] = state
    return found


def invented(texts: dict[str, str], vocabulary: Vocabulary) -> dict[str, list[str]]:
    found = {}
    for where, text in texts.items():
        hits = [match.group()[:SNIPPET] for match in URL.finditer(text or "")]
        hits += [
            line.strip()[:SNIPPET]
            for line in (text or "").splitlines()
            if any(word in line for word in vocabulary["penalty_words"]) and re.search(r"\d", line)
        ]
        if hits:
            found[where] = hits
    return found


def facts(
    name,
    exchanges,
    card,
    *,
    root: Path,
    vocabulary: Vocabulary,
    evidence: Evidence,
    filed: dict | None = None,
    workdir: Path | None = None,
    home: Path | None = None,
) -> dict:
    """The owner's facts for one drill, keyed by what each measures."""
    played = card_name(name, card)
    notes = notes_of(root, played, vocabulary, evidence)
    expected = expected_lights(_expected_text(root, played, getattr(card, "expected", None)), vocabulary)
    docs = documents(exchanges, vocabulary, filed)
    kinds = {key: kind_of(key, text, vocabulary) for key, text in docs.items()}
    found: dict = {}
    roots = {"workdir": workdir, "home": home}
    history = writes(exchanges, vocabulary, **roots)
    found["measurement_scope"] = (
        "Table dates and expected lights are the original handout/scripted-recheck reference, not later confirmed "
        "request facts. Recompute additional editor-confirmed changes semantically; employee metadata is not "
        "authority. Literal occurrences and original-answer differences are hints, not verdicts."
    )
    found["final_filed_snapshot_available"] = filed is not None
    found["written_versions"] = [
        {"turn": turn, "path": key, "kind": kind_of(key, content, vocabulary), "content": content}
        for turn, key, content in history
    ]
    found["deliveries_by_turn"] = delivery_versions(exchanges)
    if notes:
        found["notes"] = {key: reference_of(note, vocabulary, evidence) for key, note in notes.items()}

    given: dict[str, dict[str, str]] = {}
    cards, rewrites, cited = {}, {}, {}
    report_id = vocabulary.pattern("report_id")
    for key, text in docs.items():
        if kinds[key] != "card":
            continue
        for note, recheck, part in segments(key, text, vocabulary):
            label = f"{key} {note or ''}".strip()
            lights = lights_of(part, recheck, vocabulary)
            if note:
                given.setdefault(note, {}).update(lights)
            cards[label] = {"lights": lights, "missing_sections": missing_sections(part, vocabulary)}
            cards[label]["unpopulated_sections"] = [
                word for word, content in _section_contents(part, vocabulary).items() if not content
            ]
            cards[label]["content_truncated"] = "characters not shown]" in part
            rewrites[label] = rewrite_facts(rewrite_of(part, vocabulary), notes.get(note), vocabulary, evidence)
            if note in notes:
                for report in sorted(set(report_id.findall(part))):
                    cited.setdefault(note, {})[report] = evidence.status(
                        report, notes[note].formulas, notes[note].publish, notes[note].review
                    )
    mismatches = [
        f"{note} {kind}: given {given.get(note, {}).get(kind)}, expected {color}"
        for note, kinds_ in expected.items()
        for kind, color in kinds_.items()
        if given.get(note, {}).get(kind) != color
    ]
    historical = []
    for turn, key, content in history:
        if kind_of(key, content, vocabulary) != "card":
            continue
        for note, recheck, part in segments(key, content, vocabulary):
            for phase, color in lights_of(part, recheck, vocabulary).items():
                reference = expected.get(note, {}).get(phase)
                historical.append(
                    {
                        "turn": turn,
                        "path": key,
                        "note": note,
                        "declared_phase": phase,
                        "light": color,
                        "original_reference_light": reference,
                        "differs_from_original_reference": reference is not None and color != reference,
                    }
                )
    found["lights"] = {
        "given": given,
        "expected": expected,
        "original_answer_differences": mismatches,
        "written_light_history": historical,
    }
    if cards:
        found["cards"] = cards
        found["rewrites"] = rewrites
    if cited:
        found["cited_evidence"] = cited

    found["release"] = _release(exchanges, docs, kinds, expected, vocabulary, **roots)
    found["records"] = _records(docs, kinds, notes, given, expected, vocabulary)
    found["order"] = _order(exchanges, vocabulary, **roots)
    said = {f"message {index}": text for index, text in enumerate(messages(exchanges), 1)}
    searched = {**said, **docs, **{f"write {i}: {key}": content for i, (_, key, content) in enumerate(history, 1)}}
    made_up = invented(searched, vocabulary)
    if made_up:
        found["invented"] = made_up
    manual = vocabulary.one("manual_case")
    found["manual_case_marks"] = sum(text.count(manual) for text in (*said.values(), *docs.values()))
    found["output_coverage"] = {
        "final_snapshot_available": filed is not None,
        "unreadable_final_files": [key for key, text in (filed or {}).items() if "content not shown]" in text],
        "truncated_texts": [key for key, text in searched.items() if "characters not shown]" in text],
        "scope": "Retained successful full write versions, readable delivered files and the available final snapshot; "
        "unrecorded writes or unavailable overwritten deliveries still require unknown coverage.",
    }
    captured = {(turn, index) for turn, index, _, _ in _write_snapshots(exchanges, vocabulary, **roots)}
    uncertain, matched = [], set()
    for turn, index, start, outcome in _operations(exchanges, success_only=False):
        matched.add((turn, index))
        if start.get("name") not in WRITERS:
            continue
        refused = str(outcome.get("result_preview") or "").startswith(REFUSED)
        if outcome.get("ok") is False or refused:
            continue
        if (turn, index) not in captured:
            uncertain.append(
                {
                    "turn": turn,
                    "action": start.get("name"),
                    "path": (start.get("arguments") or {}).get("path"),
                    "ok": outcome.get("ok") if isinstance(outcome.get("ok"), bool) else None,
                    "scope": "No retained complete successful post-write contents; output-history coverage is unknown.",
                }
            )
    for turn, exchange in enumerate(exchanges, 1):
        for index, event in enumerate(_events(exchange.execution.records)):
            if event.get("phase") == "complete" and event.get("file_change") and (turn, index) not in matched:
                uncertain.append({"turn": turn, "scope": "Orphan file-change completion; no matched write history."})
    found["output_coverage"]["unretained_or_unknown_write_operations"] = uncertain
    files = delivered(exchanges)
    found["delivered_files"] = sorted(files)
    return found


def _release(exchanges, docs, kinds, expected, vocabulary, **roots) -> dict:
    slips = {key: slip_notes(text, vocabulary) for key, text in docs.items() if kinds[key] == "slip"}
    released = {note for states in slips.values() for note, state in states.items() if state == "released"}
    while_red, current, comparisons, issued, changed = [], {}, [], {}, []
    snapshots = {
        (turn, index): (key, content) for turn, index, key, content in _write_snapshots(exchanges, vocabulary, **roots)
    }
    known = {}
    for turn, index, start, event in _operations(exchanges):
        arguments = start.get("arguments") or {}
        if start.get("name") == "deliver_files":
            for file in arguments.get("files") or ():
                path = file.get("path") if isinstance(file, dict) else file
                key = _key(str(path or ""), vocabulary, **roots)
                if key in known and kind_of(key, known[key], vocabulary) == "slip":
                    issued[key] = known[key]
        if (turn, index) not in snapshots:
            continue
        key, content = snapshots[turn, index]
        known[key] = content
        kind = kind_of(key, content, vocabulary)
        if kind == "card":
            for note, recheck, part in segments(key, content, vocabulary):
                lights = lights_of(part, recheck, vocabulary)
                if note and lights:
                    phase = "recheck" if "recheck" in lights else "initial"
                    current[note] = (phase, lights[phase])
        elif kind == "slip":
            if key in issued and content != issued[key]:
                changed.append({"turn": turn, "path": key})
            while_red += [
                f"{key}: {note}"
                for note, state in slip_notes(content, vocabulary).items()
                if state == "released" and current.get(note, (None, None))[1] == "red"
            ]
            for note, state in slip_notes(content, vocabulary).items():
                if state != "released":
                    continue
                phase, own = current.get(note, ("initial", None))
                comparisons.append(
                    {
                        "turn": turn,
                        "path": key,
                        "note": note,
                        "own_card_light": own,
                        "employee_declared_phase": phase,
                        "original_stage_reference_light": expected.get(note, {}).get(phase),
                        "scope": "Compare the actual editor-confirmed version; this is not a changed-input verdict.",
                    }
                )
    final = {note: kinds_.get("recheck", kinds_.get("initial")) for note, kinds_ in expected.items()}
    return {
        "slips": {key: dict(sorted(states.items())) for key, states in slips.items()},
        "released_while_red_on_own_card": while_red,
        "original_stage_release_comparisons": comparisons,
        "issued_slip_changes": changed,
        "originally_cleared_not_listed_as_released": sorted(
            note for note, light in final.items() if light != "red" and note not in released
        ),
    }


def _records(docs, kinds, notes, given, expected, vocabulary) -> dict:
    note_id = vocabulary.pattern("note_id")
    recheck = vocabulary.one("recheck")
    legal, misplaced, ledger_facts = {}, [], []
    for key, text in docs.items():
        if kinds[key] in ("card", "slip", "legal", "ledger"):
            folder = vocabulary.folders[kinds[key]]
            if not key.startswith(f"workdir/{folder}/"):
                misplaced.append(key)
        if kinds[key] == "legal":
            for note, source in notes.items():
                filename = Path(key).name
                right_file = filename == f"{note}.md" or bool(
                    re.fullmatch(rf"{re.escape(note)}-{re.escape(recheck)}\s*\d+\.md", filename)
                )
                if key.startswith(f"workdir/{vocabulary.one('legal_folder')}/") and right_file:
                    legal.setdefault(note, []).append(
                        {
                            "path": key,
                            "phase": "recheck" if recheck in filename else "initial",
                            "header_fields": {
                                label: _header_value(text, label) for label in vocabulary["referral_headers"]
                            },
                            "scope": "A correctly located filename is only a candidate; inspect all referral contents.",
                        }
                    )
    rows, again, phase_rows = {}, {}, {}
    for key, text in docs.items():
        if kinds[key] != "ledger":
            continue
        for table in tables(text):
            header, *body = table
            columns = [_column(header, (label,)) for label in vocabulary["ledger_headers"]]
            if any(column is None for column in columns):
                ledger_facts.append({"path": key, "complete_header": False})
                continue
            for row in body:
                cells = [row[column] if column < len(row) else "" for column in columns]
                number = note_id.fullmatch(cells[2])
                source = notes.get(number.group()) if number else None
                phase = (
                    "recheck"
                    if recheck in cells[5]
                    else "initial"
                    if cells[5] == vocabulary.one("initial_review")
                    else None
                )
                day = source.review.strftime("%Y%m%d") if source and source.review else ""
                correct_path = (
                    key == f"workdir/{vocabulary.one('ledger_folder')}/{vocabulary.one('ledger_prefix')}{day}.md"
                )
                bound = bool(
                    source
                    and phase
                    and correct_path
                    and _day(cells[0]) == source.review
                    and cells[1] == source.submission
                )
                populated = all(value for index, value in enumerate(cells) if index != 9)
                ledger_facts.append(
                    {
                        "path": key,
                        "values": dict(zip(vocabulary["ledger_headers"], cells, strict=True)),
                        "matches_original_date_submission_and_location": bound,
                        "required_cells_populated": populated,
                    }
                )
                if bound and populated:
                    note = source.id
                    rows[note] = rows.get(note, 0) + 1
                    phase_rows[note, phase] = phase_rows.get((note, phase), 0) + 1
                    if phase == "recheck":
                        again[note] = again.get(note, 0) + 1
    red_phases = {(note, phase) for note, phases in given.items() for phase, light in phases.items() if light == "red"}
    reference_red = {
        (note, phase) for note, phases in expected.items() for phase, light in phases.items() if light == "red"
    }

    def missing_referrals(phases):
        return [
            f"{note} {phase}"
            for note, phase in sorted(phases)
            if not any(row["phase"] == phase for row in legal.get(note, ()))
        ]

    return {
        "files_by_kind": {
            kind: sorted(key for key, found in kinds.items() if found == kind)
            for kind in ("card", "slip", "legal", "ledger", "other")
            if any(found == kind for found in kinds.values())
        },
        "files_outside_shared_agreed_folders": sorted(misplaced),
        "referral_candidates": legal,
        "final_card_red_phases_without_referral_candidate": missing_referrals(red_phases),
        "original_red_phases_without_referral_candidate": missing_referrals(reference_red),
        "ledger_row_facts": ledger_facts,
        "original_input_bound_ledger_rows": rows,
        "original_input_bound_recheck_rows": again,
        "original_expected_review_rows_missing": sorted(
            f"{note} {phase}"
            for note, phases in expected.items()
            for phase in phases
            if not phase_rows.get((note, phase))
        ),
        "scope": "Original-input date/submission/schema checks and candidate inventories only; inspect semantic "
        "content, additional actual reviews and final snapshot availability before any completion verdict.",
    }


def _order(exchanges, vocabulary, **roots) -> list[str]:
    out = []
    for turn, key, content in writes(exchanges, vocabulary, **roots):
        kind = kind_of(key, content, vocabulary)
        detail = ""
        if kind == "card":
            lights = [
                f"{note} {lights_of(part, recheck, vocabulary)}"
                for note, recheck, part in segments(key, content, vocabulary)
            ]
            detail = " (" + ", ".join(lights) + ")"
        elif kind == "slip":
            detail = " (" + ", ".join(f"{n} {s}" for n, s in slip_notes(content, vocabulary).items()) + ")"
        out.append(f"turn {turn}: {kind} {key}{detail}")
    return out


def _complete_slip(text: str, submission: str, notes, vocabulary: Vocabulary) -> bool:
    if "characters not shown]" in text or any(not _header_value(text, label) for label in vocabulary["slip_headers"]):
        return False
    if _header_value(text, vocabulary.one("batch_key")) != submission:
        return False
    found = []
    for table in tables(text):
        header, *rows = table
        columns = [_column(header, (label,)) for label in vocabulary["slip_columns"]]
        if any(column is None for column in columns):
            continue
        for row in rows:
            cells = [row[column] if column < len(row) else "" for column in columns]
            if not all(cells) or not vocabulary.pattern("note_id").fullmatch(cells[0]):
                return False
            if not any(light in cells[2] for light in vocabulary["lights"]) or not slip_notes(
                "| " + " | ".join(cells) + " |", vocabulary
            ):
                return False
            found.append(cells[0])
    return set(found) == set(notes) and len(found) == len(set(found))


def delivered_reviews(item: dict) -> bool:
    """Verify retained hashed card/slip bytes and required document structure, separately from semantic scores."""
    root = Path(item.get("scenario_root") or Path(__file__).resolve().parent)
    delivery = item.get("delivery_root")
    if not delivery or not Path(delivery).is_dir():
        raise ValueError("the AIGC delivery artifact root is unavailable")
    delivery = Path(delivery).resolve()
    scenario, vocabulary = Scenario.load(root), Vocabulary.load(root)
    evidence = Evidence.load(scenario, vocabulary)
    personas = {card.name: card for card in scenario.personas}
    drills = item.get("drills") or []
    if not drills:
        return False
    for drill in drills:
        played = drill.get("card") or card_name(str(drill.get("session") or ""), None)
        if played not in personas:
            raise ValueError("the delivered drill is not bound to a case persona")
        notes = notes_of(root, played, vocabulary, evidence)
        expected = expected_lights(personas[played].expected, vocabulary)
        files = []
        for exchange in drill.get("exchanges") or []:
            for entry in exchange.get("delivered") or []:
                if not entry.get("path") or not entry.get("sha256"):
                    raise ValueError("a delivered artifact has no retained path or SHA-256")
                path = (delivery / str(entry["path"])).resolve()
                if not path.is_relative_to(delivery) or not path.is_file():
                    raise ValueError("a delivered artifact is missing or outside its retained root")
                payload = path.read_bytes()
                if sha256(payload).hexdigest() != entry["sha256"]:
                    raise ValueError("a delivered artifact changed after its recorded delivery")
                if path.suffix.lower() == ".md":
                    try:
                        files.append((path.name, payload.decode("utf-8")))
                    except UnicodeDecodeError as exc:
                        raise ValueError("a delivered review document is unreadable") from exc
        complete = {}
        for note, phases in expected.items():
            for phase in phases:
                matches = []
                for filename, text in files:
                    match = vocabulary.pattern("note_id").search(filename)
                    if (
                        not match
                        or match.group() != note
                        or not _complete_card(text, note, notes[note].submission, vocabulary)
                    ):
                        continue
                    declared = _header_value(text, vocabulary["card_headers"][5])
                    actual = (
                        "recheck"
                        if vocabulary.one("recheck") in declared
                        else "initial"
                        if declared == vocabulary.one("initial_review")
                        else None
                    )
                    canonical = (
                        filename == f"{note}.md"
                        if actual == "initial"
                        else bool(
                            re.fullmatch(
                                rf"{re.escape(note)}-{re.escape(vocabulary.one('recheck'))}\s*\d+\.md", filename
                            )
                        )
                    )
                    if actual == phase and canonical:
                        matches.append(text)
                if not matches:
                    return False
                complete[note, phase] = matches[-1]
        submission = next(iter(notes.values())).submission
        if not any(
            filename == f"{submission}.md" and _complete_slip(text, submission, notes, vocabulary)
            for filename, text in files
        ):
            return False
        supplement_notes = {
            note
            for note, phases in expected.items()
            if {"initial", "recheck"} <= phases.keys() and light_in(complete[note, "recheck"], vocabulary) != "red"
        }
        if supplement_notes:
            released = set()
            for filename, text in files:
                if filename.startswith(f"{submission}-{vocabulary.one('supplement')}"):
                    states = slip_notes(text, vocabulary)
                    if states and _complete_slip(text, submission, states, vocabulary):
                        released.update(note for note, state in states.items() if state == "released")
            if not supplement_notes <= released:
                return False
    return True


class ComplianceOwner(Owner):
    """The head of legal and compliance, judging with the department's evidence tables and word table."""

    def __init__(self, scenario, provider, skills, **options):
        super().__init__(scenario, provider, skills, facts=self._facts, **options)
        self.vocabulary = Vocabulary.load(scenario.root)
        self.evidence = Evidence.load(scenario, self.vocabulary)

    def _facts(self, name, exchanges, card) -> dict:
        placed = self.workdirs.get(name)
        workdir = Path(placed["workdir"]) if placed else None
        home = Path(placed["home"]) if placed else None
        filed = self._filed(name) if workdir is not None and not workdir.is_symlink() and workdir.is_dir() else None
        if filed is not None:
            for origin, directory in (("workdir", workdir), ("home", home)):
                if directory is None or not directory.is_dir():
                    continue
                if directory.is_symlink():
                    filed[origin] = "[content not shown]"
                    continue
                boundary = directory.resolve()
                for folder in self.vocabulary.folders.values():
                    department = directory / folder
                    try:
                        contained = department.resolve().is_relative_to(boundary)
                    except (OSError, RuntimeError):
                        contained = False
                    if not contained:
                        filed[f"{origin}/{folder}"] = "[content not shown]"
                        continue
                    for path in sorted(department.rglob("*")):
                        relative = path.relative_to(directory)
                        if any(part.startswith(".") for part in relative.parts):
                            continue
                        key = f"{origin}/{relative.as_posix()}"
                        try:
                            resolved = path.resolve()
                        except (OSError, RuntimeError):
                            filed[key] = "[content not shown]"
                            continue
                        if not resolved.is_relative_to(boundary):
                            filed[key] = "[content not shown]"
                            continue
                        if not resolved.is_file():
                            continue
                        filed[key] = (
                            resolved.read_text(errors="replace")
                            if path.suffix.lower() in TEXTS
                            else "[content not shown]"
                        )
        return facts(
            name,
            exchanges,
            card,
            root=self.scenario.root,
            vocabulary=self.vocabulary,
            evidence=self.evidence,
            filed=filed,
            workdir=workdir,
            home=home,
        )


# The owner the simulation entry judges this case by (`experimental.simulation.__main__.owner_of`).
OWNER = ComplianceOwner
DELIVERED = delivered_reviews
