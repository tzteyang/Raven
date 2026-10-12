"""The laundry chain's owner: the generic `Owner` with the facts the shop owner judges a short-video script by.

A drill delivers a spoken script for a group-buy video, one sentence a line, each line with a shot note in brackets,
under a short header. The facts are computed, never judged. For every delivered version of a script: its spoken length
counted the way the script norms count it (only what is said, brackets left out, figures, units, times and ranges as
they are read aloud), each line's length, the opening line's length with the prices and pains it names, whether the
closing line carries the call to action, the lines without a shot note, the length the header states, the listed words
found on the script's lines (pet phrases, hook templates, ending cliches, off-platform contact, absolute claims,
comparison prices, exaggerations, sold counts, promises the guarantee rules do not make), the prices, pickup times and
stores it names, each price matched against the group-buy listings, and the publish date, account and number its
header states. For the last version, the ledger rows that opened with the same pain or with the same sentence apart
from its figures, each with its distance from the publish date and whether it is the same account. From the records
and the drill's working directory: native ledger mutations with their outcomes and event positions, uncertain
operations that name it, delivered script events, the rows written,
the rows the ledger file holds beyond the export, the turn of the last script, and whether a ledger was read before
the first script went out.

The owner reads these the way a person uses a stopwatch and a word search. The words and counting conventions are the
scenario's `reference.md`; the listings and the ledger export are read from the scenario's own materials, so nothing
here names a price, a word or a date.
"""

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from difflib import SequenceMatcher
from pathlib import Path

from experimental.cultivation.counterpart.owner import Owner
from experimental.cultivation.counterpart.rulers import (
    CONFIG,
    around,
    chinese_number,
    messages,
    occurrences,
    tables,
    words,
)
from experimental.harness.participation.files import read_delivered
from experimental.harness.raven_adapter.observe import delivered_files
from experimental.harness.scenario.contract import frontmatter

SNIPPET = 80
LISTS = (
    "catchphrases",
    "clickbait",
    "ending_cliches",
    "offsite",
    "absolute",
    "comparison",
    "overpromise",
    "exaggeration",
    "sold",
)
PAINS = "pain_"
READS = frozenset({"read_file", "grep", "find", "list_dir", "load_skill", "read_skill"})
MUTATIONS = frozenset({"write_file", "edit_file", "append_file"})
PATH_KEYS = ("path", "file", "file_path", "target", "destination", "ledger")
SIMILAR = 0.85
ROWS_SHOWN = 6
LEAST_LINES = 3
SCRIPT_SUFFIXES = frozenset({".md", ".txt"})
LISTING_COLUMNS = {
    "id": "listing_id",
    "name": "listing_name",
    "group": "listing_group",
    "store": "listing_store",
    "stores": "listing_stores",
    "status": "listing_status",
}
LEDGER_COLUMNS = {
    "date": "ledger_date",
    "account": "ledger_account",
    "number": "ledger_number",
    "deal": "ledger_deal",
    "pain": "ledger_pain",
    "first": "ledger_first",
    "speaker": "ledger_speaker",
    "store": "ledger_store",
    "count": "ledger_count",
    "version": "ledger_version",
    "status": "ledger_status",
    "orders": "ledger_orders",
    "notes": "ledger_notes",
}

_HAN = f"{chr(0x3400)}-{chr(0x4DBF)}{chr(0x4E00)}-{chr(0x9FFF)}{chr(0xF900)}-{chr(0xFAFF)}"
_SAID = re.compile(rf"[{_HAN}A-Za-z0-9]")
_FIGURE = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_DASH = "[-~" + chr(0x2013) + chr(0x2014) + "]"
_FULLWIDTH_COMMA, _LIST_COMMA = chr(0xFF0C), chr(0x3001)
_BRACKETS = re.compile(r"\[[^\]]*\]|\([^)]*\)|" + chr(0x3010) + "[^" + chr(0x3011) + "]*" + chr(0x3011))
_SHOT_OPENERS = r"[\[(" + chr(0x3010) + "]"
_ENUMERATED = re.compile(r"^\s*(?:\d{1,2}\s*(?:[.)]|" + _LIST_COMMA + r")(?!\d)|\(\d{1,2}\))\s*")
_BOLD_LINE = re.compile(r"^\s*\*\*[^*]+\*\*\s*[:]?\s*$")
_RULE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
_DAY = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_DIGITS = "".join(chinese_number(str(digit)) for digit in range(10))
_TEN, _HUNDRED, _THOUSAND = chinese_number("10"), chinese_number("100")[-1], chinese_number("1000")[-1]
_POINT = chinese_number("0.5")[1]
_NONZERO, _ZERO = _DIGITS[1:], _DIGITS[0]
_NUMERAL = re.compile(
    rf"(?=[{_DIGITS}{_TEN}])(?:[{_NONZERO}]{_THOUSAND})?(?:{_ZERO}?[{_NONZERO}]{_HUNDRED})?"
    rf"(?:{_ZERO}?[{_NONZERO}]?{_TEN})?(?:{_ZERO}?[{_NONZERO}])?(?:{_POINT}[{_DIGITS}]+)?"
)
_NUMERIC = re.compile(rf"[\d{_DIGITS}{_TEN}{_HUNDRED}{_THOUSAND}{_POINT}.]+")


def normal(text: str) -> str:
    """Text as the measures read it: NFKC-folded, except that a full-width comma stays a clause break and never
    becomes a thousands separator."""
    return unicodedata.normalize("NFKC", (text or "").replace(_FULLWIDTH_COMMA, _LIST_COMMA))


def _pairs(values) -> dict[str, str]:
    """`a=b` values of a reference row as a mapping, keys folded the way script text is."""
    return {normal(key): reading for key, _, reading in (value.partition("=") for value in values)}


def numeral_value(numeral: str) -> float:
    """The value of a well-formed Chinese numeral as `chinese_number` writes one: up to the thousands, decimals
    digit by digit."""
    whole, _, decimals = numeral.partition(_POINT)
    total = current = 0
    for char in whole:
        if char in _DIGITS:
            current = _DIGITS.index(char)
        elif char == _TEN:
            total, current = total + (current or 1) * 10, 0
        elif char == _HUNDRED:
            total, current = total + current * 100, 0
        elif char == _THOUSAND:
            total, current = total + current * 1000, 0
    total += current
    if decimals:
        return round(total + float("0." + "".join(str(_DIGITS.index(char)) for char in decimals)), 2)
    return total


def _plain(value: float):
    return int(value) if float(value).is_integer() else value


def spoken_count(text: str) -> int:
    """How many characters spoken text counts: Chinese characters and Latin letters, one each, after its figures
    were turned into words (a figure left in digits counts one a digit)."""
    return len(_SAID.findall(text))


@dataclass(frozen=True)
class Listing:
    """One row of the group-buy listings: id, name, group and store price, the stores cell and the status cell."""

    id: str
    name: str
    group: float
    store: float
    stores: str
    status: str


@dataclass(frozen=True)
class Posted:
    """One row of the publishing ledger export; `line` is the row's cells joined, folded, without spaces."""

    day: date
    account: str
    number: str
    deal: str
    pain: str
    first: str
    line: str


@dataclass(frozen=True)
class Line:
    """One spoken line of a script: as written, as read aloud, its count and whether it carries a shot note."""

    raw: str
    spoken: str
    count: int
    shot: bool
    conforming_shot: bool = True


def _column(header: list[str], word: str) -> int | None:
    return next((index for index, cell in enumerate(header) if word in cell), None)


def _rows_of(text: str, wanted: dict[str, str]) -> list[dict[str, str]] | None:
    """The rows of the first table in `text` whose header names every column word of `wanted`, each row keyed by
    the column's short name, with `line`, the whole row folded; None when no table has those columns."""
    for table in tables(text):
        header, *rows = table
        at = {name: _column(header, word) for name, word in wanted.items()}
        if any(index is None for index in at.values()):
            continue
        widest = max(at.values())
        return [
            {**{name: row[index] for name, index in at.items()}, "line": _squeezed("|".join(row))}
            for row in rows
            if len(row) > widest
        ]
    return None


def _price(cell: str) -> float:
    found = re.search(r"\d+(?:\.\d+)?", cell)
    if found is None:
        raise ValueError(f"a listing price without a figure: {cell!r}")
    return round(float(found.group()), 2)


def _squeezed(text: str) -> str:
    return re.sub(r"\s", "", normal(text))


def _bare(text: str) -> str:
    """A line with only its characters and figures left: no spacing, punctuation or markup."""
    return re.sub(r"[^\w]", "", normal(text)).replace("_", "")


@dataclass(frozen=True)
class Ruler:
    """The scenario's words and counting conventions (`reference.md`), its group-buy listings and its ledger export."""

    words: dict[str, tuple[str, ...]]
    listings: tuple[Listing, ...]
    posted: tuple[Posted, ...]
    pains: dict[str, tuple[str, ...]]
    today: date

    @classmethod
    def load(cls, scenario) -> "Ruler":
        found = words(Path(scenario.root) / CONFIG)

        def material(key: str) -> str:
            return frontmatter(scenario.text(found[key][0]))[1]

        wanted = {name: found[key][0] for name, key in LISTING_COLUMNS.items()}
        listings = tuple(
            Listing(row["id"], row["name"], _price(row["group"]), _price(row["store"]), row["stores"], row["status"])
            for row in _rows_of(material("listings_material"), wanted) or ()
            if re.search(r"\d", row["group"])
        )
        posted = tuple(
            Posted(
                date.fromisoformat(row["date"]),
                row["account"],
                row["number"],
                row["deal"],
                row["pain"],
                row["first"],
                row["line"],
            )
            for row in _rows_of(material("ledger_material"), cls._ledger_columns(found)) or ()
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["date"])
        )
        pains = {values[0]: values for key, values in found.items() if key.startswith(PAINS)}
        if not listings or not posted or not pains:
            raise ValueError(f"{CONFIG}: the listings, the ledger export or the pain words came out empty")
        return cls(found, listings, posted, pains, date.fromisoformat(found["today"][0]))

    @staticmethod
    def _ledger_columns(found: dict) -> dict[str, str]:
        return {name: found[key][0] for name, key in LEDGER_COLUMNS.items()}

    def word(self, key: str) -> str:
        return self.words[key][0]

    @property
    def number(self) -> re.Pattern:
        return re.compile(rf"{re.escape(self.word('number_prefix'))}\d{{4}}-\d{{2}}")

    # Reading a line aloud

    def spoken(self, line: str) -> str:
        """A script line as it is read aloud: brackets, a leading number and a leading label dropped, and every
        figure, unit, time, range and symbol replaced by the words the script norms read it as."""
        text = _BRACKETS.sub("", normal(line).replace("**", ""))
        text = _ENUMERATED.sub("", text, count=1)
        text = re.sub(rf"^\s*{re.escape(self.word('spoken_label'))}\s*:\s*", "", text)
        text = re.sub(rf"(\d{{1,2}}):(\d{{2}})(?:\s*{_DASH}\s*(\d{{1,2}}):(\d{{2}}))?", self._times, text)
        year = re.escape(self.word("year_word"))
        text = re.sub(rf"(\d{{4}})(?=\s*{year})", lambda m: "".join(chinese_number(d) for d in m.group(1)), text)
        for symbol, reading in _pairs(self.words["currency_symbols"]).items():
            text = re.sub(
                rf"{re.escape(symbol)}\s*({_FIGURE})(?:\s*{re.escape(reading)})?",
                lambda m, said=reading: chinese_number(m.group(1)) + said,
                text,
            )
        for symbol, reading in _pairs(self.words["prefix_units"]).items():
            text = re.sub(
                rf"({_FIGURE})\s*{re.escape(symbol)}", lambda m, said=reading: said + chinese_number(m.group(1)), text
            )
        to = self.word("range_word")
        text = re.sub(rf"({_FIGURE})\s*{_DASH}\s*(?=\d)", lambda m: chinese_number(m.group(1)) + to, text)
        units = {unit.lower(): reading for unit, reading in _pairs(self.words["suffix_units"]).items()}
        pattern = "|".join(re.escape(unit) for unit in sorted(units, key=len, reverse=True))
        text = re.sub(
            rf"({_FIGURE})\s*(?i:({pattern}))(?![A-Za-z])",
            lambda m: chinese_number(m.group(1)) + units[m.group(2).lower()],
            text,
        )
        text = re.sub(_FIGURE, lambda m: chinese_number(m.group()), text)
        for symbol, reading in _pairs(self.words["symbols"]).items():
            text = text.replace(symbol, reading)
        return text.strip()

    def _times(self, match: re.Match) -> str:
        hour, half, minute = self.words["time_words"][:3]

        def read(hours: str, minutes: str) -> str:
            said = chinese_number(str(int(hours))) + hour
            if int(minutes) == 30:
                return said + half
            return said + (chinese_number(str(int(minutes))) + minute if int(minutes) else "")

        first = read(match.group(1), match.group(2))
        if match.group(3) is None:
            return first
        return first + self.word("range_word") + read(match.group(3), match.group(4))

    # Recognising a script

    def _has_shot(self, text: str) -> bool:
        return bool(re.search(rf"{_SHOT_OPENERS}\s*{re.escape(self.word('shot'))}", text))

    def _conforming_shot(self, text: str) -> bool:
        opener, closer = chr(0xFF3B), chr(0xFF3D)
        label = re.escape(self.word("shot"))
        pattern = rf"{opener}\s*{label}\s*[:{chr(0xFF1A)}][^{closer}]+{closer}\s*$"
        return text.count(opener) == 1 and bool(re.search(pattern, text))

    def is_ledger(self, text: str) -> bool:
        """Whether a text is a ledger rather than a script: a table headed with the ledger's columns."""
        return bool(_rows_of(text, self._ledger_columns(self.words)) is not None)

    def _blocks(self, text: str) -> list[list[str]]:
        """The document split at headings, bold-only lines and horizontal rules."""
        blocks, current = [], []
        for raw in (text or "").splitlines():
            folded = normal(raw)
            if folded.lstrip().startswith("#") or _BOLD_LINE.match(folded) or _RULE.match(folded):
                blocks.append(current)
                current = []
            else:
                current.append(raw)
        blocks.append(current)
        return blocks

    def _section(self, text: str) -> list[str]:
        """The block that holds the script: the one with the most lines carrying a shot note, then the most numbered
        lines, so a checklist under its own heading is not read as spoken."""

        def score(block):
            shots = sum(1 for raw in block if self._has_shot(normal(raw)))
            return shots, sum(1 for raw in block if _ENUMERATED.match(normal(raw)))

        return max(self._blocks(text), key=score)

    def lines(self, text: str) -> list[Line]:
        """The spoken lines of a script: the rows of a table with a column named as spoken and a shot column, or
        else, in the block that holds the script, the contiguous run of numbered lines, lines carrying a shot note
        and lines labelled as spoken; a line that is only a shot note, bracketed or labelled, gives the spoken line
        before it its note; once the run holds a script, the first other line ends it. Explicit numbered lines
        remain spoken even when the required shot note is missing."""
        table = self._table_lines(text)
        if table:
            return table
        label = re.compile(rf"^{re.escape(self.word('spoken_label'))}\s*:")
        shot_label = re.compile(rf"^{re.escape(self.word('shot'))}\s*:")
        found: list[Line] = []
        for raw in self._section(text):
            folded = normal(raw).replace("**", "").strip()
            bullet = folded.startswith(("- ", "* "))
            bare = folded[2:].strip() if bullet else folded
            if not bare or bare.startswith(("|", ">")):
                continue
            if shot_label.match(bare) or (self._has_shot(bare) and not self.spoken(bare)):
                if found:
                    found[-1] = Line(found[-1].raw + "\n" + raw.strip(), found[-1].spoken, found[-1].count, True, False)
                continue
            if not (_ENUMERATED.match(bare) or self._has_shot(bare) or label.match(bare)):
                if len(found) >= LEAST_LINES:
                    break
                continue
            said = self.spoken(bare)
            if said:
                found.append(
                    Line(raw.strip(), said, spoken_count(said), self._has_shot(bare), self._conforming_shot(raw))
                )
        return found

    def _table_lines(self, text: str) -> list[Line]:
        label, shot = self.word("spoken_label"), self.word("shot")
        for table in tables(normal(text)):
            header, *rows = table
            said = next((index for index, cell in enumerate(header) if cell.strip() == label), None)
            noted = _column(header, shot)
            if said is None or noted is None:
                continue
            found = []
            for row in rows:
                if len(row) <= said or not row[said].strip():
                    continue
                spoken = self.spoken(row[said])
                has = bool(len(row) > noted and row[noted].strip()) or self._has_shot(row[said])
                found.append(Line(" | ".join(row), spoken, spoken_count(spoken), has, False))
            if found:
                return found
        return []

    def stated(self, text: str) -> int | None:
        """The spoken length a script's header states, if it states one."""
        label = re.escape(self.word("count_label"))
        numeral = rf"[\d{_DIGITS}{_TEN}{_HUNDRED}{_THOUSAND}]+"
        found = re.search(rf"{label}\s*[:{chr(0xFF1A)}]?\s*({numeral})", normal(text).replace("**", ""))
        if not found:
            return None
        value = found.group(1)
        return int(value) if value.isdigit() else int(numeral_value(value))

    def header(self, text: str) -> dict:
        """What a script's header states: its publish date (the profile's year), its account and its number."""
        folded = normal(text)
        found: dict = {}
        line = next((item for item in folded.splitlines() if self.word("publish_label") in item), "")
        day = re.search(r"(\d{1,2})\s*" + chr(0x6708) + r"\s*(\d{1,2})\s*" + chr(0x65E5), line) or _DAY.search(line)
        if day:
            try:
                parts = [int(part) for part in day.groups()]
                found["publish"] = date(*(parts if len(parts) == 3 else [self.today.year, *parts]))
            except ValueError:
                pass
        line = next((item for item in folded.splitlines() if self.word("account_label") in item), "")
        found["account"] = next((account for account in self.words["accounts"] if account in line), None)
        number = self.number.search(folded)
        found["number"] = number.group() if number else None
        return found

    # What a line names

    def numerals(self, spoken: str, *, positions: bool = False):
        """(numeral, value, the few characters after it) for every Chinese numeral in a spoken text, the colloquial
        two read as two."""
        normalized = spoken.replace(self.word("two_word"), _DIGITS[2])
        for match in _NUMERAL.finditer(normalized):
            if match.group():
                found = (
                    spoken[match.start() : match.end()],
                    numeral_value(match.group()),
                    spoken[match.end() : match.end() + 3],
                )
                yield (*found, match.start()) if positions else found

    def _counting(self, after: str) -> bool:
        units = (*self.words["count_units"], *self.words.get("count_units_more", ()))
        return any(after.lstrip().startswith(unit) for unit in units)

    def prices(self, spoken: str) -> list[dict]:
        """Candidate prices supported by a currency suffix, price context or catalogue value, with each value's
        matching listings; counting-unit quantities are separate."""
        known: dict[float, list[str]] = {}
        for listing in self.listings:
            known.setdefault(listing.group, []).append(f"{listing.id} group price ({listing.status})")
            known.setdefault(listing.store, []).append(f"{listing.id} store price ({listing.status})")
        found = []
        for numeral, value, after, at in self.numerals(spoken, positions=True):
            if self._counting(after):
                continue
            priced = any(after.lstrip().startswith(word) for word in self.words["currency"])
            before = spoken[max(0, at - 8) : at]
            contextual = any(mark in before for mark in self.words.get("price_marks", ()))
            if not priced and not contextual and value not in known:
                continue
            found.append({"said": numeral, "value": _plain(value), "listings": known.get(value, [])})
        return found

    def times(self, lines: list[Line]) -> list[dict]:
        """The durations the spoken lines name in the pickup-time units, with the line each stands on; one standing
        in a validity clause is marked so, and a phrase that only names a day is left out."""
        found = []
        for index, line in enumerate(lines, 1):
            spoken = line.spoken
            for phrase in self.words.get("not_durations", ()):
                spoken = spoken.replace(phrase, "")
            for numeral, value, after, at in self.numerals(spoken, positions=True):
                unit = next((unit for unit in self.words["time_units"] if after.lstrip().startswith(unit)), None)
                if not unit:
                    continue
                separators = ",;.!?" + _LIST_COMMA + chr(0x3002) + chr(0xFF1B) + chr(0xFF01) + chr(0xFF1F)
                start = max(spoken.rfind(mark, 0, at) for mark in separators) + 1
                ends = [boundary for mark in separators if (boundary := spoken.find(mark, at)) >= 0]
                end = min(ends, default=len(spoken))
                context = spoken[max(start, at - 6) : min(end, at + len(numeral) + 6)]
                entry = {"said": numeral + unit, "value": _plain(value), "unit": unit, "line": index}
                if any(mark in context for mark in self.words.get("validity_marks", ())):
                    entry["kind"] = "validity"
                elif not any(mark in context for mark in self.words.get("pickup_marks", ())):
                    entry["kind"] = "unclassified"
                found.append(entry)
        return found

    def stores(self, lines: list[Line]) -> dict:
        named = [
            {"store": store, "line": index}
            for index, line in enumerate(lines, 1)
            for store in self.words["stores"]
            if store in line.spoken
        ]
        counter = self.word("store_counter")
        counted = [
            {"count": _plain(value), "line": index, "context": around(line.spoken, numeral)}
            for index, line in enumerate(lines, 1)
            for numeral, value, after in self.numerals(line.spoken)
            if after.startswith(counter)
        ]
        return {key: value for key, value in (("named", named), ("counted", counted)) if value}

    def pains_in(self, text: str) -> list[str]:
        folded = normal(text)
        return [name for name, variants in self.pains.items() if any(normal(word) in folded for word in variants)]

    def hits(self, text: str, keys=LISTS) -> dict[str, dict[str, list[str]]]:
        folded = normal(text).lower()
        found = {}
        for key in keys:
            hit = occurrences(folded, tuple(normal(term).lower() for term in self.words[key]))
            if hit:
                found[key] = hit
        return found

    def guarantee(self, text: str) -> dict:
        """Whether the one sentence the guarantee rules allow stands in the text, and every other line that speaks of
        compensation."""
        allowed = _bare(self.word("guarantee_line"))
        lines = normal(text).splitlines()
        present = [index for index, line in enumerate(lines, 1) if allowed in _bare(line)]
        compact = [re.sub(r"[^\w]", "", line).replace("_", "") for line in lines]
        residual = "\n".join(line.replace(allowed, "") for line in compact)
        others = occurrences(
            residual,
            tuple(normal(term) for term in self.words["guarantee_terms"]),
        )
        return {"allowed_sentence_lines": present, "other_compensation_lines": others}

    def displayed(self, lines: list[Line]) -> list[dict]:
        """Public copy explicitly marked as subtitles, overlays or cards, separate from scene directions."""
        marks = "|".join(re.escape(normal(mark)) for mark in self.words["display_marks"])
        quote = "[\"'" + chr(0x201C) + chr(0x201D) + chr(0x2018) + chr(0x2019) + "]"
        found = []
        for index, line in enumerate(lines, 1):
            folded = normal(line.raw)
            notes = _BRACKETS.findall(folded)
            notes.extend(
                raw.strip() for raw in folded.splitlines() if re.match(rf"\s*{re.escape(self.word('shot'))}\s*:", raw)
            )
            for note in notes:
                marker = re.search(marks, note)
                if marker is None:
                    continue
                end = -1 if note.endswith(("]", ")", chr(0x3011))) else None
                tail = note[marker.end() : end].strip(" :")
                quoted = re.findall(rf"{quote}(.*?){quote}", tail)
                for text in quoted or [tail]:
                    if not text:
                        continue
                    spoken = self.spoken(text)
                    measured = [Line(text, spoken, spoken_count(spoken), True)]
                    found.append(
                        {
                            "line": index,
                            "text": text,
                            "prices": self.prices(spoken),
                            "times": self.times(measured),
                            "stores": self.stores(measured),
                            "guarantee": self.guarantee(text),
                            "word_hits": self.hits(text),
                        }
                    )
        return found

    # One version of a script

    def version(self, source: str, turn: int, text: str) -> dict | None:
        """The facts of one script version, or None when `text` holds too few spoken lines to be a script."""
        lines = self.lines(text)
        if len(lines) < LEAST_LINES:
            return None
        first, last = lines[0], lines[-1]
        said = "\n".join(line.spoken for line in lines)
        cta = self.word("cta")
        stated = self.header(text)
        found = {
            "source": source,
            "turn": turn,
            "header": {
                "publish": stated["publish"].isoformat() if stated.get("publish") else None,
                "account": stated["account"],
                "number": stated["number"],
            },
            "spoken_lines": len(lines),
            "spoken_count": sum(line.count for line in lines),
            "line_counts": [line.count for line in lines],
            "lines": [
                {"raw": line.raw, "read_as": line.spoken, "count": line.count, "prices": self.prices(line.spoken)}
                for line in lines
            ],
            "stated_count": self.stated(text),
            "first_line": first.raw[:SNIPPET],
            "first_line_read_as": first.spoken[:SNIPPET],
            "first_line_count": first.count,
            "first_line_prices": self.prices(first.spoken),
            "first_line_pains": self.pains_in(_BRACKETS.sub("", normal(first.raw))),
            "last_line": last.raw[:SNIPPET],
            "cta_in_last_line": cta in last.spoken,
            "cta_lines": [index for index, line in enumerate(lines, 1) if cta in line.spoken],
            "lines_without_shot": [
                index for index, line in enumerate(lines, 1) if not line.shot or not line.conforming_shot
            ],
            "prices": self.prices(said),
            "pickup_times": self.times(lines),
            "stores": self.stores(lines),
            "guarantee": self.guarantee("\n".join(line.raw for line in lines)),
            "word_hits": self.hits("\n".join(line.raw for line in lines)),
            "displayed_claims": self.displayed(lines),
        }
        return {key: value for key, value in found.items() if value not in (None, [], {})}

    def history(self, first_line: str, publish: date | None = None, account: str | None = None) -> dict:
        """The ledger rows that opened with a pain this line names, or with this sentence apart from its figures,
        newest first, each with its distance before the publish date (today when the script states none), whether
        it is the same account and whether it falls in the norms' window; and the summary of both for the same
        account inside the window."""
        publish = publish or self.today
        window = int(self.word("window_days"))
        line = _BRACKETS.sub("", _ENUMERATED.sub("", normal(first_line)))
        pains = self.pains_in(line)
        bare = _bare(line)
        skeleton = _NUMERIC.sub("", bare)
        same, swapped, like = [], [], []
        for row in sorted(self.posted, key=lambda posted: posted.day, reverse=True):
            days = (publish - row.day).days
            entry = {
                "date": row.day.isoformat(),
                "days_before_publish": days,
                "in_window": 0 < days <= window,
                "same_account": None if account is None else row.account == account,
                "account": row.account,
                "number": row.number,
                "pain": row.pain,
                "first": row.first,
            }
            if row.pain in pains:
                same.append(entry)
            posted_bare = _bare(row.first)
            if skeleton and skeleton == _NUMERIC.sub("", posted_bare):
                swapped.append(entry)
            ratio = SequenceMatcher(None, bare, posted_bare).ratio()
            if ratio >= SIMILAR:
                like.append({**entry, "similarity": round(ratio, 2)})

        def clash(rows):
            return any(row["in_window"] and row["same_account"] is not False for row in rows)

        found = {
            "publish": publish.isoformat(),
            "account": account,
            "pains": pains,
            "same_pain_rows": same,
            "figure_swap_of": swapped,
            "similar_first_lines": like,
            "same_pain_in_window": clash(same),
            "figure_swap_in_window": clash(swapped),
        }
        return {key: value for key, value in found.items() if value not in (None, [], {})}

    # The publishing ledger in the records and in the working directory

    def _ledger(self, path: str) -> bool:
        return normal(path).replace("\\", "/").rstrip("/").endswith(self.word("ledger_path"))

    def _ledgerish(self, text: str) -> bool:
        return Path(self.word("ledger_path")).stem in normal(text) or self.word("ledger_material") in text

    def _new_rows(self, text: str) -> list[str]:
        """The rows of a ledger text beyond the export: from the table headed with the ledger's columns, or, in a
        text without one (an appended row), the table rows carrying a date; rows with a number the export lacks
        first."""
        exported = {row.line for row in self.posted}
        numbers = {row.number for row in self.posted}
        found = _rows_of(normal(text), self._ledger_columns(self.words))
        if found is None:
            found = [
                {"line": _squeezed(line), "number": "", "raw": line.strip()}
                for line in normal(text).splitlines()
                if line.strip().startswith("|") and _DAY.search(line)
            ]
        else:
            found = [{**row, "raw": "|".join(row[name] for name in LEDGER_COLUMNS)} for row in found]
        rows = [row for row in found if row["line"] not in exported]
        rows.sort(key=lambda row: 0 if self.number.search(row["line"]) and row["number"] not in numbers else 1)
        return [row["raw"][:200] for row in rows]

    def ledger_file(self, workdir: Path | None, numbers: set[str]) -> dict | None:
        """What the live ledger file in the drill's working directory holds: whether it exists, how many rows of
        the export it carries, its rows beyond the export, the numbers of more than one row, and whether a row
        stands for each script number."""
        if workdir is None:
            return None
        path = Path(workdir) / self.word("ledger_path")
        if not path.is_file():
            return {"exists": False}
        text = path.read_text(errors="replace")
        rows = _rows_of(normal(text), self._ledger_columns(self.words)) or []
        exported = {row.line for row in self.posted}
        counted: dict[str, int] = {}
        for row in rows:
            counted[row["number"]] = counted.get(row["number"], 0) + 1
        found = {
            "exists": True,
            "export_rows_kept": sum(1 for row in rows if row["line"] in exported),
            "rows_beyond_export": [
                "|".join(row[name] for name in LEDGER_COLUMNS)[:200] for row in rows if row["line"] not in exported
            ][-ROWS_SHOWN:],
            "numbers_with_several_rows": sorted(number for number, count in counted.items() if count > 1),
            "new_rows": [row for row in rows if row["line"] not in exported],
        }
        if numbers:
            found["row_for_script_number"] = {number: counted.get(number, 0) for number in sorted(numbers)}
        return found

    def ledger(self, exchanges, versions: list[dict], workdir: Path | None = None) -> dict:
        """What the records and the working directory show of the live ledger: native mutation calls with their
        outcomes and event positions; uncertain operations naming it; writes to other files named like it; the rows written; the turns
        of the last script and the last write; whether a ledger was read before the first script went out; and the
        ledger file itself. The order of the last write against the last script is None when nothing in the
        records shows a write but the file holds rows beyond the export."""
        writes, elsewhere, rows, unverified, deliveries = [], [], [], [], []
        first_read = first_script = None
        names = {version["source"] for version in versions}
        position = 0
        for turn, exchange in enumerate(exchanges, start=1):
            started = {}
            for row in _runner_rows(exchange.execution.records):
                position += 1
                event = row.get("event") or {}
                if event.get("phase") == "start" and event.get("name"):
                    started[event.get("tool_call_id")] = event
                    given = event.get("arguments") or {}
                    target = " ".join(str(given.get(key) or "") for key in ("path", "pattern", "query", "name"))
                    if event["name"] in READS and first_read is None and self._ledgerish(target):
                        first_read = (turn, position)
                    continue
                sent = [Path(str(item["path"])).name for item in delivered_files(row)]
                if any(name in names for name in sent):
                    deliveries.append({"turn": turn, "event_position": position, "files": sent})
                    if first_script is None:
                        first_script = (turn, position)
                begun = started.get(event.get("tool_call_id"))
                if not begun or event.get("phase") != "complete" or begun.get("name") in READS:
                    continue
                given = begun.get("arguments") or {}
                paths = [str(given.get(key) or "") for key in PATH_KEYS]
                done = {
                    "turn": turn,
                    "event_position": position,
                    "tool": begun["name"],
                    "ok": event.get("ok"),
                }
                if begun["name"] == "deliver_files":
                    continue
                if begun["name"] in MUTATIONS and any(self._ledger(path) for path in paths):
                    writes.append(done)
                    if done["ok"] is True:
                        rows.extend(self._new_rows(str(given.get("content") or given.get("new_text") or "")))
                elif begun["name"] in MUTATIONS and any(self._ledgerish(path) for path in paths if path):
                    elsewhere.append({**done, "path": next(path for path in paths if self._ledgerish(path))[-SNIPPET:]})
                elif self._ledger_named(given, event):
                    unverified.append(
                        {**done, "evidence": "the call names the ledger but does not establish a mutation"}
                    )
        if first_script is None and versions:
            first_script = (versions[0]["turn"], position + 1)
        numbers = {version["header"]["number"] for version in versions if version.get("header", {}).get("number")}
        file = self.ledger_file(workdir, numbers)
        last_script = max((version["turn"] for version in versions), default=None)
        last_write = max((write["turn"] for write in writes if write["ok"] is True), default=None)
        if last_script is None:
            order = None
        elif last_write is not None:
            order = last_write >= last_script
        elif file and file.get("rows_beyond_export"):
            order = None
        else:
            order = False
        found = {
            "writes": writes,
            "writes_elsewhere": elsewhere,
            "rows_written": list(dict.fromkeys(rows))[:ROWS_SHOWN],
            "unverified_operations": unverified,
            "script_delivery_events": deliveries,
            "file": file,
            "last_script_turn": last_script,
            "last_ledger_write_turn": last_write,
            "written_with_or_after_last_script": order,
            "read_before_first_script": None
            if first_script is None
            else first_read is not None and first_read < first_script,
        }
        return {key: value for key, value in found.items() if value not in ([], None)}

    def _ledger_named(self, arguments: dict, completion: dict) -> bool:
        stem = Path(self.word("ledger_path")).stem
        try:
            given = json.dumps(arguments, ensure_ascii=False)
        except (TypeError, ValueError):
            given = str(arguments)
        return stem in normal(given) or stem in normal(str(completion.get("result_preview") or ""))


def _runner_rows(records):
    """Runner rows in order, a delegated child's rows in place of its execution row."""
    for row in records:
        if row.get("kind") == "child.execution":
            yield from _runner_rows([item for item in row.get("records") or () if isinstance(item, dict)])
        elif row.get("kind") == "runner.event":
            yield row


def scripts(exchanges, ruler: Ruler) -> list[dict]:
    """Every delivered candidate script, regardless of filename; ledger files are separate evidence. Replies are
    measured only when no delivered text held a script."""
    delivered = [
        (turn, path)
        for turn, exchange in enumerate(exchanges, start=1)
        for path in map(Path, exchange.execution.deliverables)
        if path.suffix.lower() in SCRIPT_SUFFIXES and path.is_file()
    ]
    found = []
    for turn, path in delivered:
        text = read_delivered(path)
        if ruler._ledger(path.name) or ruler.is_ledger(text):
            continue
        version = ruler.version(path.name, turn, text)
        if version:
            found.append(version)
    if found:
        return found
    for turn, text in enumerate(messages(exchanges), start=1):
        version = ruler.version(f"message {turn}", turn, text)
        if version:
            found.append(version)
    return found


def intended(card, ruler: Ruler, exchanges=()) -> dict:
    """Independent card bindings, updated by explicit customer publication instructions; never by output headers."""
    expected = getattr(card, "expected", None) or ""
    accounts = "|".join(re.escape(account) for account in ruler.words["accounts"])
    account = re.search(rf"\baccount\s*:?\s*({accounts})", expected, re.I)
    publish = re.search(r"\bpublish[^\n]{0,32}?(\d{4}-\d{2}-\d{2})", expected, re.I)
    binding = {
        **({"account": account.group(1)} if account else {}),
        **({"publish": publish.group(1)} if publish else {}),
    }
    aliases = _pairs(ruler.words["account_aliases"])
    separators = "[,;.!?\n" + _LIST_COMMA + chr(0x3002) + chr(0xFF1B) + chr(0xFF01) + chr(0xFF1F) + "]"
    uncertain = []
    for exchange in exchanges:
        for clause in re.split(separators, normal(exchange.user)):
            if not any(mark in clause for mark in ruler.words["publish_actions"]):
                continue
            if any(mark in clause for mark in ruler.words["past_marks"]):
                continue
            if any(mark in clause for mark in ruler.words["publication_uncertain"]):
                uncertain.append(clause)
                continue
            candidates, covered = set(), []
            for alias, value in sorted(aliases.items(), key=lambda item: len(item[0]), reverse=True):
                for match in re.finditer(re.escape(alias), clause):
                    if any(start <= match.start() and match.end() <= end for start, end in covered):
                        continue
                    covered.append(match.span())
                    context = clause[max(0, match.start() - 6) : match.end() + 6]
                    if any(mark in context for mark in ruler.words["publication_negations"]):
                        continue
                    candidates.add(value)
            if len(candidates) == 1:
                binding["account"] = candidates.pop()
            elif len(candidates) > 1:
                uncertain.append(clause)
            if any(mark in clause for mark in ruler.words["publication_negations"]):
                continue
            dates = list(_DAY.finditer(clause)) or list(
                re.finditer(
                    r"(\d{1,2})\s*" + chr(0x6708) + r"\s*(\d{1,2})\s*[" + chr(0x65E5) + chr(0x53F7) + "]",
                    clause,
                )
            )
            if len(dates) > 1:
                uncertain.append(clause)
                continue
            if dates:
                try:
                    parts = [int(part) for part in dates[0].groups()]
                    binding["publish"] = date(*(parts if len(parts) == 3 else [ruler.today.year, *parts])).isoformat()
                except ValueError:
                    uncertain.append(clause)
    if uncertain:
        binding["uncertain_publication_clauses"] = uncertain
    return binding


def facts(exchanges, ruler: Ruler, workdir: Path | None = None, card=None) -> dict:
    """The owner's facts for one drill, keyed by what each measures."""
    versions = scripts(exchanges, ruler)
    found: dict = {"versions": versions or "no script lines were delivered or said"}
    if versions:
        last = versions[-1]
        header = last.get("header", {})
        task = intended(card, ruler, exchanges) if card is not None else {}
        binding = task or header
        publish = date.fromisoformat(binding["publish"]) if binding.get("publish") else None
        found["opening_history"] = ruler.history(last["lines"][0]["read_as"], publish, binding.get("account"))
        if task:
            found["intended_binding"] = task
            found["header_binding_differences"] = {
                key: {"intended": value, "stated": header.get(key)}
                for key, value in task.items()
                if key in ("account", "publish") and header.get(key) != value
            }
    ledger = ruler.ledger(exchanges, versions, workdir)
    if ledger:
        found["ledger"] = ledger
    return found


class LaundryOwner(Owner):
    """The owner of the laundry chain's short-video scenario, judging scripts with its stopwatch and word search."""

    def __init__(self, scenario, provider, skills, **options):
        super().__init__(scenario, provider, skills, facts=self._facts, **options)
        self.ruler = Ruler.load(scenario)

    def _facts(self, name, exchanges, card) -> dict:
        placed = self.workdirs.get(name) or {}
        return facts(exchanges, self.ruler, placed.get("workdir"), card)


def script_delivered(item: dict) -> bool:
    """Every drill handed over a structurally recognized script file; content quality is assessed separately."""
    drills = item.get("drills") or []
    if not drills:
        return False
    for drill in drills:
        named = {
            Path(str(file.get("name") or file.get("path") or "")).name
            for exchange in drill.get("exchanges") or []
            for file in exchange.get("delivered") or []
            if isinstance(file, dict)
        }
        references = drill.get("references") or {}
        versions = references.get("versions") or [] if isinstance(references, dict) else []
        if not any(
            isinstance(version, dict)
            and version.get("source") in named
            and Path(version["source"]).suffix.lower() in SCRIPT_SUFFIXES
            and isinstance(version.get("lines"), list)
            and len(version["lines"]) >= LEAST_LINES
            and all(isinstance(line, dict) and line.get("read_as") for line in version["lines"])
            for version in versions
        ):
            return False
    return True


# The owner the simulation entry judges this case by (`experimental.simulation.__main__.owner_of`).
OWNER = LaundryOwner
DELIVERED = script_delivered
