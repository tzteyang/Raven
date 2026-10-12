"""The renovation quote page's owner: the generic `Owner` with the facts the operations head judges a drill by.

The drills deliver a quote page, so the facts are the page tried the way a salesperson uses it (`page`): on every day
the card cares about (its business date, the days around a price or promotion switch, the first day after the last
promotion), with the network refused, for the checked historical sheets, the boundary and refused inputs of the finance
rules and the inputs the card's conversation and attachments name, each reading set beside what the finance rules give
for that input on that day (`quote`, from the case's own price lists and promotions). A day the driver could not work
the page on (a control it did not find or a page it could not operate) is marked
unreliable instead of being compared, so the owner judges it from the page text or leaves it unknown. Besides: what
the page file itself shows (references outside it, internal cost data in its source), the quote sheet's items (number,
validity, measured-area note, the codes it names, the version), and from the execution records and the drill's own
workdir the order in which the check record, the page and the hand-over happened, what the check record and the
release register name, and which readings the check record claims that the page contradicts. The owner reads these
the way a person uses a calculator and a ruler, and still decides every verdict. The words, rates and inputs are the
case's `reference.md` values.
"""

import hashlib
import re
import unicodedata
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path

from experimental.cultivation.counterpart.owner import Owner
from experimental.cultivation.counterpart.rulers import CONFIG, browser_executable, tables, words
from experimental.harness.scenario.contract import document
from experimental.simulation.cases.renovation_quote_page.page import Words, examine, source_facts, squeeze, total_of
from experimental.simulation.cases.renovation_quote_page.quote import HALF, Book, Case, load, money
from experimental.simulation.cases.renovation_quote_page.release import (
    bound_pages,
    html_delivered,
    operations,
    snapshots,
    workflow,
)

WRITES = ("write_file", "edit_file")
DELIVER = "deliver_files"
PREFIXES = re.compile(r"^(?:holdout-|s\d+-)+")
REPEAT = re.compile(r"-\d+$")
DAY = re.compile(r"(?:(\d{4})\D{1,2})?(\d{1,2})\D{1,2}(\d{1,2})")
STEPS = 40
CLAIMS = 20


def release(version: str) -> tuple[int, ...]:
    """A version's numbers, so v1.10 comes after v1.9."""
    return tuple(int(part) for part in re.findall(r"\d+", version))


def version_pattern(found: dict) -> re.Pattern:
    """A version as a page or a file name writes it: `v1.2`, or the version word followed by the numbers."""
    word = re.escape(found["version_word"][0])
    return re.compile(rf"(?:[vV]|{word}\s*)(\d+\.\d+)")


def versions_in(text: str, found: dict) -> list[str]:
    return sorted({f"v{number}" for number in version_pattern(found).findall(text or "")}, key=release)


def fold(text: str) -> str:
    """Text as the record facts compare it: width-folded, lower-cased, without spaces or thousands separators."""
    return squeeze(unicodedata.normalize("NFKC", text or "")).lower().replace(",", "")


def card_of(name: str, card) -> str:
    """The card a drill played: the card's own name, or the drill's name without the exam and set prefixes and the
    repeat suffix."""
    found = getattr(card, "name", None)
    return found or REPEAT.sub("", PREFIXES.sub("", name))


def cases(found: dict, key: str) -> list[Case]:
    return [Case.parse(spec) for spec in found.get(key, ())]


def plan(found: dict, card: str) -> list[tuple[date, list[Case]]]:
    """The days and inputs a card's page is tried with: on its business date the historical sheets, the boundary and
    refused inputs and the card's own; on every further date the switch inputs and the card's own."""
    days = [date.fromisoformat(day) for day in found.get(card, ())]
    if not days:
        return []
    own = cases(found, f"extra_{card}")
    first = [*cases(found, "history_cases"), *cases(found, "edge_cases"), *cases(found, "refused_cases"), *own]
    original = {
        label: date.fromisoformat(day) for value in found.get("history_dates", ()) for label, day in [value.split("=")]
    }
    historical = [
        (day, [case]) for case in cases(found, "history_cases") if (day := original.get(case.label)) and day not in days
    ]
    return [(days[0], first), *((day, [*cases(found, "switch_cases"), *own]) for day in days[1:]), *historical]


def expected_text(book: Book, case: Case, day: date) -> str:
    quote = book.quote(case, day)
    return "prompt" if quote is None else money(quote.total)


def shown_text(reading) -> str:
    if reading.total is not None:
        amount = f"{int(reading.total):,}" if reading.total == int(reading.total) else f"{reading.total:,}"
        shown = f"total {amount}" + (" with the prompt" if reading.prompt else "")
    else:
        shown = "prompt" if reading.prompt else "no total and no prompt"
    if reading.alerts:
        shown += f" (alert: {reading.alerts[0][:40]})"
    return shown


def agrees(book: Book, reading, day: date) -> bool:
    quote = book.quote(reading.case, day)
    if quote is None:
        return reading.prompt and reading.total is None and not reading.rendered.get("money_fields")
    return reading.total is not None and reading.total == quote.total


def unreliable(readings, book: Book, day: date) -> str | None:
    """Why a day's readings say nothing about the page: a control the driver did not find, a page it could not
    operate. An operated page that shows no result is still an observed result."""
    if not readings:
        return "nothing was read"
    missing = [item for item in readings[0].controls if item.endswith(" none")]
    if not readings[0].controls or missing:
        return f"the driver found no control for: {', '.join(missing) or 'anything'}"
    if any(r.refused == "no area box found" for r in readings):
        return "the driver found no area box"
    broken = [r.refused for r in readings if r.refused and r.refused.startswith(("could not work", "could not parse"))]
    if broken:
        return broken[0]
    return None


def valid_until(line: str, label: str, found: dict, day: date) -> date | None:
    """The date a validity line names: the one after the until word when it has one, else the last on the line;
    a date without a year is in the business year, or the next when its month lies before."""
    text = squeeze(line)
    after = text[text.index(label) + len(label) :] if label in text else text
    until = found["until_word"][0]
    if until in after:
        after = after[after.rindex(until) + len(until) :]
    dates = DAY.findall(after) or DAY.findall(text)
    if not dates:
        return None
    year, month, day_of = dates[-1]
    year = int(year) if year else day.year + (1 if int(month) < day.month else 0)
    try:
        return date(year, int(month), int(day_of))
    except ValueError:
        return None


def sheet(text: str, day: date, found: dict, book: Book, *, clock=None, region=None) -> dict:
    """The quote sheet's required items as the page showed them for the sheet input on the business date."""
    prefix = re.escape(found["quote_prefix"][0])
    number = re.search(rf"{prefix}(\d{{8}})-(\d{{6}})(?!\d)", text or "")
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    validity = next(
        (line for label in found["validity_labels"] for line in lines if label in line and DAY.search(squeeze(line))),
        None,
    )
    until = None
    if validity:
        label = next(label for label in found["validity_labels"] if label in validity)
        until = valid_until(validity, label, found, day)
    prices, promotion = book.price_list(day), book.promotion(day)
    known = [item.code for item in (*book.price_lists, *book.promotions)]
    region = region if region is not None else _sheet_region(lines, number.group(0) if number else None, found)
    time_valid = bool(number) and int(number[2][:2]) < 24 and int(number[2][2:4]) < 60 and int(number[2][4:]) < 60
    actual_clock = datetime.fromisoformat(clock.replace("Z", "+00:00")) if clock else None
    if actual_clock:
        from experimental.simulation.cases.renovation_quote_page.page import OFFSET

        actual_clock = actual_clock.astimezone(OFFSET)
    return {
        "quote_number": number.group(0) if number else None,
        "number_carries_the_date": bool(number) and number.group(1) == day.strftime("%Y%m%d") and time_valid,
        "issuing_time_is_valid": time_valid,
        "number_matches_observed_clock": bool(number) and number[1] + number[2] == actual_clock.strftime("%Y%m%d%H%M%S")
        if actual_clock
        else None,
        "observed_clock": clock,
        "valid_until_line": validity[:60] if validity else None,
        "valid_until_is_date_plus_7": until == day + timedelta(days=book.validity) if until else False,
        "measured_area_note": squeeze(found["measure_note"][0]) in squeeze(region),
        "in_force": f"{prices.code}; {promotion.code if promotion else 'no promotion'}",
        "codes_in_sheet": [code for code in known if code in region],
        "codes_elsewhere": [code for code in known if code not in region and code in (text or "")],
        "versions_shown": versions_in(text, found),
        "required_title": squeeze(found["sheet_title"][0]) in squeeze(region),
        "validity_note": squeeze(found["validity_note"][0]) in squeeze(region),
        "required_field_labels_not_found": [
            label for label in found["sheet_fields"] if squeeze(label) not in squeeze(region)
        ],
        "text": region,
    }


def _sheet_region(lines: list[str], number: str | None, found: dict) -> str:
    """The lines of the quote sheet proper: from its number (or its first marker) to its last marker line."""
    marks = (found["measure_note"][0], found["validity_note"][0], *found["total_labels"][:1])
    starts = [
        index
        for index, line in enumerate(lines)
        if (number and number in line) or squeeze(found["sheet_title"][0]) in squeeze(line)
    ]
    ends = [index for index, line in enumerate(lines) if any(squeeze(mark) in squeeze(line) for mark in marks)]
    if not starts or not ends:
        return "\n".join(lines)
    end = max(ends[-1], starts[0]) + 1
    # The sheet's closing note may run on past its last marker; the footer, carrying the version, is not the sheet.
    while end < len(lines) and end < ends[-1] + 3 and not version_pattern(found).search(lines[end]):
        end += 1
    return "\n".join(lines[starts[0] : end])


def page_facts(path: Path, card: str, found: dict, book: Book, executable: str | None) -> tuple[dict, dict]:
    """The page tried on the card's days, with what each input gave against what the rules give, and an index of
    every reading by day and input for the check record's claims."""
    content = path.read_bytes()
    try:
        html = content.decode("utf-8-sig")
        complete_source = True
    except UnicodeError:
        html = content.decode("utf-8", errors="replace")
        complete_source = False
    facts = {"file": path.name, **source_facts(html, found)}
    facts["source_complete"] = complete_source
    facts["source_sha256"] = hashlib.sha256(content).hexdigest()
    if not complete_source:
        facts["source_limitation"] = "Unsupported source encoding; replacement text cannot prove confidentiality."
    name_rule = rf"{re.escape(found['page_name'][0])}-v\d+\.\d+\.html"
    facts["file_name_follows_the_procedure"] = bool(re.fullmatch(name_rule, path.name))
    days = plan(found, card)
    if not days:
        facts["tried"] = "no dates are set for this card"
        return facts, {}
    if executable is None:
        facts["tried"] = "not tried: no headless browser on this host; judge the page from its text"
        return facts, {}
    try:
        seen = examine(path, days, Words.of(found), executable, card if card in ("baodai", "kehu") else None)
    except Exception as exc:  # noqa: BLE001 -- a page that cannot be tried is a fact for the owner, not a failed review
        facts["tried"] = f"the page could not be tried: {str(exc).splitlines()[0][:160]}"
        return facts, {}
    runs, index = {}, {}
    for day, result in seen["runs"].items():
        readings = result["readings"]
        prices, promotion = book.price_list(day), book.promotion(day)
        run = {"in_force": f"{prices.code}; {promotion.code if promotion else 'no promotion'}"}
        if readings:
            run["controls"] = "; ".join(readings[0].controls)
        reason = unreliable(readings, book, day)
        if reason:
            run["tried"] = f"unreliable, not compared: {reason}"
        else:
            run["agree"] = " ".join(r.case.label for r in readings if agrees(book, r, day))
            run["differ"] = [
                {
                    "input": str(r.case),
                    "rules_give": expected_text(book, r.case, day),
                    "page_shows": shown_text(r),
                    **({"note": r.refused} if r.refused else {}),
                    **({"total_line": r.line} if r.line else {}),
                }
                for r in readings
                if not agrees(book, r, day)
            ]
            for r in readings:
                index[
                    (day.isoformat(), r.case.area.translate(HALF).strip(), r.case.tier, r.case.demolish, r.case.custom)
                ] = r
        run["observations"] = [
            {
                "input": str(r.case),
                "raw_area": r.case.area,
                "finance": {key: str(value) for key, value in asdict(quote).items()}
                if (quote := book.quote(r.case, day)) is not None
                else "prompt",
                "page_shows": shown_text(r),
                "sheet": sheet(
                    r.text, day, found, book, clock=r.rendered.get("clock"), region=r.rendered.get("sheet_text") or None
                )
                if r.total is not None
                else None,
                "body_text": r.text,
                "money_fields": r.rendered.get("money_fields"),
                "layout": r.rendered.get("layout"),
                "controls": r.controls,
                "refused": r.refused,
            }
            for r in readings
        ]
        run["invalid_after_valid"] = [
            {
                "input": str(r.case),
                "page_shows": shown_text(r),
                "prompt": r.prompt,
                "money_still_visible": bool(r.rendered.get("money_fields")),
                "body_text": r.text,
                "money_fields": r.rendered.get("money_fields"),
                "refused": r.refused,
            }
            for r in result.get("invalid_transitions", [])
        ]
        run["same_second_issuance"] = result.get("issuance", {})
        run["requested_fields"] = result.get("requested_fields", {})
        if day == days[0][0]:
            chosen = next((r for r in readings if r.case.label == found["sheet_case"][0]), None)
            if chosen is not None and not reason:
                run["sheet"] = sheet(
                    chosen.text,
                    day,
                    found,
                    book,
                    clock=chosen.rendered.get("clock"),
                    region=chosen.rendered.get("sheet_text") or None,
                )
            if result["layout"]:
                run["phone_layout"] = {
                    "sideways_scroll_at_390px": result["layout"]["overflow"],
                    "sheet_height_px_of_844": result["layout"]["height"],
                }
        runs[day.isoformat()] = run
    facts["runs"] = runs
    facts["requests_refused_offline"] = seen["blocked"]
    facts["observed_local_requests"] = seen.get("local_requests", [])
    if seen["errors"]:
        facts["script_errors"] = seen["errors"]
    return facts, index


def written(exchanges) -> dict[str, str]:
    """Only successful native absolute file-change snapshots, with scope-aware call pairing."""
    return {str(change["path"]): change["content"] for change in snapshots(operations(exchanges), None)}


def opened_pages(exchanges, suffixes) -> list[str]:
    """Successful native calls mentioning a page are clues to inspect, never proof of a browser check."""
    return sorted(
        {
            call["name"]
            for call in operations(exchanges)
            if call["ok"] is True
            and call["name"] not in (*WRITES, DELIVER)
            and any(suffix in str(call["arguments"]).lower() for suffix in suffixes)
        }
    )


def on_disk(workdir: Path | None, marks: tuple[str, ...]) -> dict[str, str]:
    """Text files under the drill's workdir whose path carries one of `marks`."""
    if workdir is None or not Path(workdir).is_dir():
        return {}
    return {
        path.relative_to(workdir).as_posix(): path.read_text(errors="replace")
        for path in sorted(Path(workdir).rglob("*"))
        if path.is_file() and path.suffix == ".md" and any(mark in path.as_posix() for mark in marks)
    }


def _tier_of(cell: str, found: dict) -> str | None:
    return next((tier for tier in found["tier_names"] if tier in cell), None)


def _yes(cell: str, found: dict) -> bool:
    return not any(word in cell for word in found["negations"])


def record_claims(records: str, index: dict, found: dict, business: date) -> list[dict]:
    """The check record's rows whose shown result the page does not give for the same input on the same day."""
    columns = found["record_columns"]
    area_col, shown_col, date_col, tier_col, demolish_col, custom_col = columns
    prompt = fold(found["error_prompt"][0])
    claims = []
    kept, reproduction = [], None
    for line in records.splitlines():
        heading = re.match(r"^\s*(#{1,6})\s+(.+)$", line)
        if heading:
            level, title = len(heading[1]), heading[2]
            if found["reproduction_heading"][0] in title:
                reproduction = level
            elif reproduction is not None and level <= reproduction:
                reproduction = None
        if reproduction is None:
            kept.append(line)
    for table in tables("\n".join(kept)):
        header = table[0]
        if not any(area_col in cell for cell in header) or not any(shown_col in cell for cell in header):
            continue

        def column(name, row, header=header):
            return next((row[at] for at, cell in enumerate(header) if name in cell and at < len(row)), "")

        for row in table[1:]:
            tier = _tier_of(column(tier_col, row), found)
            if tier is None:
                continue
            day = valid_until(column(date_col, row), "", found, business) or business
            key = (
                day.isoformat(),
                fold(column(area_col, row)),
                tier,
                _yes(column(demolish_col, row), found),
                _yes(column(custom_col, row), found),
            )
            reading = index.get(key)
            if reading is None:
                continue
            claimed = fold(column(shown_col, row))
            if prompt in claimed or not re.search(r"\d", claimed):
                holds = reading.prompt and reading.total is None
            else:
                amount, _ = total_of(found["total_labels"][0] + " " + column(shown_col, row), Words.of(found))
                holds = reading.total is not None and amount == reading.total
            if not holds:
                claims.append({"row": " | ".join(row)[:120], "page_shows": shown_text(reading)})
    return claims[:CLAIMS]


def process(exchanges, card, found, samples, workdir, version, index, business, *, book=None, delivery=None) -> dict:
    """The selected release's exact native record/register snapshots and verified input coverage."""
    book = book or load(Path(__file__).parent, found)
    bound = bound_pages(exchanges)
    delivery = delivery or (bound[-1] if bound else None)
    return workflow(exchanges, card, found, book, samples, index, business, delivery, workdir)


class QuoteOwner(Owner):
    """The operations head of the renovation company, judging the quote page drills with the rules' calculator and
    a phone that tries the delivered page."""

    def __init__(self, scenario, provider, skills, **options):
        super().__init__(scenario, provider, skills, facts=self._facts, **options)
        self.found = words(Path(scenario.root) / CONFIG)
        self.book = load(scenario.root, self.found)
        text = document(Path(scenario.root) / "materials" / self.found["samples"][0]).read_text()
        prefix = re.escape(self.found["quote_prefix"][0])
        self.samples = tuple(dict.fromkeys(re.findall(rf"{prefix}\d{{8}}-\d{{6}}", text)))
        self.executable = browser_executable()
        self.tried: dict[tuple, tuple[dict, dict]] = {}

    def _facts(self, name, exchanges, card) -> dict:
        return facts(
            exchanges,
            card_of(name, card),
            self.found,
            self.book,
            self.samples,
            workdir=(self.workdirs.get(name) or {}).get("workdir"),
            executable=self.executable,
            tried=self.tried,
        )


def delivered_pages(exchanges, suffixes) -> list[Path]:
    """Native successful retained HTML deliveries, rather than attempted or self-reported files."""
    return [item["path"] for item in bound_pages(exchanges) if item["path"].suffix.lower() in suffixes]


def tried_page(pages: list[Path], found: dict) -> Path:
    """Use the most recent actual attachment, never let an arbitrary higher filename version override it."""
    return pages[-1]


def facts(exchanges, card, found, book, samples, *, workdir=None, executable=None, tried=None) -> dict:
    """Source-bound facts for the current release, including every observed sheet and native process evidence."""
    days = found.get(card, ())
    result = {"card_dates": list(days)} if days else {}
    business = date.fromisoformat(days[0]) if days else None
    if business:
        prices, promotion = book.price_list(business), book.promotion(business)
        result["in_force_on_business_date"] = f"{prices.code}; {promotion.code if promotion else 'no promotion'}"
    bound = bound_pages(exchanges)
    target = found.get("target_" + card, (None,))[0]
    matching = [item for item in bound if versions_in(item["path"].name, found) == [target]]
    selected = (matching or bound)[-1] if bound else None
    index = {}
    if selected:
        path = selected["path"]
        key = (
            selected["sha256"],
            str(path.resolve()),
            selected["source"],
            selected["turn_id"],
            card,
            repr(found),
            repr(book),
            executable,
        )
        if tried is not None and key in tried:
            result["page"], index = tried[key]
        else:
            result["page"], index = page_facts(path, card, found, book, executable)
            if tried is not None:
                tried[key] = (result["page"], index)
        result["delivery_binding"] = {
            key: str(value) if isinstance(value, Path) else value for key, value in selected.items()
        }
        result["delivery_selection"] = (
            "latest successful copy of the release required by the card/procedure; otherwise latest successful HTML"
        )
        result["pages_delivered"] = [
            {key: str(value) if isinstance(value, Path) else value for key, value in item.items()} for item in bound
        ]
        result["page_tried"] = path.name
        result["delivered_version_matches_request"] = versions_in(path.name, found) == [target]
    else:
        result["page"] = "unknown: no retained HTML delivery with a successful native manifest was verified"
    result["process"] = process(
        exchanges, card, found, samples, workdir, target, index, business or date.today(), book=book, delivery=selected
    )
    return result


# The owner the simulation entry judges this case by (`experimental.simulation.__main__.owner_of`).
OWNER = QuoteOwner

DELIVERED = html_delivered
