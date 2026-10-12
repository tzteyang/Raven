"""The studio owner: the generic `Owner` with the figures the owner judges a review by.

For the card a drill played, the owner computes from the ledger the card handed over (`ledger.Ledger`) what its
conventions give for the period asked: the three headline figures, the entry errors and duplicates to list, the
zero-amount orders and the orders crossing a price change, with a breakdown for follow-up questions. It then measures
what the employee did: the files it delivered (how many, which kinds), what the delivered page names and states (order
numbers, percentages, amounts with decimals or in ten-thousands, paragraphs past two sentences), what it asked before
its first page, what it wrote into the checked-orders record, and whom it delegated to. The owner's model reads these
the way a person uses a calculator and a ruler and decides every verdict itself. The case's words come from its
`reference.md`; the prices from its price material.
"""

import hashlib
import re
from html.parser import HTMLParser
from pathlib import Path

from experimental.cultivation.counterpart.owner import Owner
from experimental.cultivation.counterpart.rulers import CONFIG, messages, tables, words
from experimental.harness.scenario.contract import frontmatter
from experimental.simulation.cases.studio_annual_review.ledger import Ledger, Prices, Words

from .delivery import delivered_as_requested
from .evidence import deliveries, render

SESSION = re.compile(r"^(?:s\d+-|holdout-)?(?P<card>[a-z]+?)(?:-\d+)?$")
PAGES = (".html", ".htm")
DELEGATING = ("spawn", "run_subagent_dag")
BLOCKS = frozenset({"p", "li", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6", "div", "section", "blockquote", "tr"})
HIDDEN = frozenset({"script", "style", "template", "head"})
SNIPPET = 80
LISTED = 8


def card_of(name: str, card) -> str | None:
    """The card a drill played: the drawn card's name, or the session name without its set and repeat marks."""
    if card is not None and getattr(card, "name", None):
        return card.name
    found = SESSION.match(name)
    return found.group("card") if found else None


class _Blocks(HTMLParser):
    """A page's visible text split at block elements: each paragraph, list item, cell or heading on its own."""

    def __init__(self):
        super().__init__()
        self.blocks, self._text, self._hidden = [], [], 0

    def _flush(self):
        text = " ".join("".join(self._text).split())
        if text:
            self.blocks.append(text)
        self._text = []

    def handle_starttag(self, tag, attrs):
        if tag in HIDDEN:
            self._hidden += 1
        elif tag in BLOCKS or tag == "br":
            self._flush()

    def handle_endtag(self, tag):
        if tag in HIDDEN and self._hidden:
            self._hidden -= 1
        elif tag in BLOCKS:
            self._flush()

    def handle_data(self, data):
        if not self._hidden:
            self._text.append(data)


def blocks(html: str) -> list[str]:
    parser = _Blocks()
    parser.feed(html)
    parser.close()
    parser._flush()
    return parser.blocks


def delivered_paths(exchanges):
    """All ordered file occurrences, including missing final artifacts and identical basenames."""
    return deliveries(exchanges)[0]


def page_facts(exchanges, figures: dict | None, vocabulary: Words) -> dict:
    """What the delivered files are, and what the page delivered last names and states."""
    files, groups = deliveries(exchanges)
    pages = [entry for entry in files if Path(entry["name"]).suffix.lower() in PAGES]
    found = {
        "delivery_versions": files,
        "delivery_groups": groups,
        "delivered_files": [entry["name"] for entry in files],
        "html_pages": [entry["name"] for entry in pages],
        "other_files": [entry["name"] for entry in files if Path(entry["name"]).suffix.lower() not in PAGES],
        "delivery_scope": "Counts are historical occurrences, not the number of final logical reports. Same-page corrections may replace earlier versions, even when renamed. Judge actual requests, batches and correction context; never collapse separate same-name files or silently omit an unreadable final artifact.",
    }
    if groups:
        found["final_delivery_group"] = groups[-1]
    if not pages:
        return found
    latest = pages[-1]
    if latest["status"] != "read":
        found["final_page_observation"] = "unavailable; an older file cannot stand in for the last page"
        return found
    name, raw = latest["name"], latest["content"]
    viewed = render(raw)
    text = viewed.get("text") if viewed.get("status") == "rendered" else "\n".join(blocks(raw))
    found["full_page_source"] = raw
    found["rendered_page"] = viewed
    found["page_text"] = text
    found["render_scope"] = (
        "Text/DOM/style/rectangle evidence supports semantic phone readability and base-layout comparison. No fixed minimum size is invented. Missing visual evidence is unknown; a lexical match does not prove a visible correctly attributed number."
    )
    ends = "".join(vocabulary["sentence_ends"]) + "!?"
    long = [
        block[:SNIPPET]
        for block in blocks(viewed.get("dom", raw))
        if len(re.findall(rf"[{re.escape(ends)}]", block)) > 2
    ]
    yuan, big = vocabulary.one("money_marks"), vocabulary.one("big_unit")
    measured = {
        "page": name,
        "percentages": sorted(set(re.findall(r"[-+]?\d+(?:\.\d+)?\s*%", text))),
        "amounts_with_decimals": sorted(set(re.findall(rf"\d[\d,]*\.\d+\s*{re.escape(yuan)}", text)))[:LISTED],
        "amounts_in_ten_thousands": sorted(set(re.findall(rf"\d+(?:\.\d+)?\s*{re.escape(big)}", text)))[:LISTED],
        "paragraphs_over_two_sentences": long,
    }
    if figures:
        listed = [item["order"] for item in figures["entry_errors"]] + [item["order"] for item in figures["duplicates"]]
        zero = [item["order"] for item in figures["zero_amount"]]
        crossing = [item["order"] for item in figures["price_change_orders"]]
        measured["entry_errors_named"] = [order for order in listed if order in text]
        measured["entry_errors_missing"] = [order for order in listed if order not in text]
        measured["zero_amount_named"] = [order for order in zero if order in text]
        measured["price_change_orders_named"] = [order for order in crossing if order in text]
        drop = figures["biggest_drop"]
        if isinstance(drop, dict):
            month = int(drop["month"][5:])
            measured["names_drop_month"] = bool(re.search(rf"(?<!\d){month}\s*{vocabulary['date_words'][1]}", text))
            measured["names_drop_percent"] = bool(re.search(rf"(?<!\d){abs(drop['rounded'])}\s*%", text))
        rate = figures["repurchase_rate_percent"]
        if rate is not None:
            measured["names_repurchase_percent"] = bool(re.search(rf"(?<!\d){rate}\s*%", text))
    measured["scope"] = (
        "Order/percentage/decimal hits are candidates only. Preserve exact original erroneous amounts in error details; only ordinary summary money and percentages must be integer. Required section structure, full error-detail fields and numerical attribution need full contextual judgment."
    )
    found["page_measures"] = measured
    return found


def questions_before_page(exchanges, vocabulary: Words) -> dict:
    """The questions the employee asked in the turns before its first page, and the turn that delivered it."""
    files = [
        any(Path(path).suffix.lower() in PAGES for path in exchange.execution.deliverables) for exchange in exchanges
    ]
    first = next((index for index, has in enumerate(files, start=1) if has), None)
    said = messages(exchanges)[: (first - 1) if first else len(exchanges)]
    marks = "".join(vocabulary["question_marks"])
    asked = [
        piece.strip()[-SNIPPET:]
        for text in said
        for piece in re.findall(rf"[^\n{re.escape(marks)}]*[{re.escape(marks)}]", text)
        if piece.strip()
    ]
    return {"first_page_turn": first, "questions_before_first_page": asked[:LISTED]}


def _events(exchanges):
    for exchange in exchanges:
        for row in exchange.execution.records:
            yield row


def checked_records(exchanges, vocabulary, year=None, *, workdir=None):
    """Actual contained checked-order bytes, never an attempted write or a filename suffix."""
    if not year or workdir is None:
        return {"status": "unavailable", "reason": "Replica path or year is unavailable."}
    root = Path(workdir)
    relative = Path(vocabulary.one("review_folder")) / f"{vocabulary.one('checked_file')}-{year}.md"
    path = root / relative
    try:
        if root.is_symlink() or not root.is_dir() or not path.resolve().is_relative_to(root.resolve()):
            return {"status": "unavailable", "reason": "The checked-order path is outside the replica."}
        raw = path.read_bytes()
        content = raw.decode("utf-8")
    except FileNotFoundError:
        return {"status": "absent", "path": relative.as_posix()}
    except (OSError, UnicodeError, RuntimeError):
        return {"status": "unavailable", "path": relative.as_posix()}
    ids = re.compile(rf"{re.escape(vocabulary.one('sheet_wechat'))}-\d{{4}}|\d{{16,19}}")
    parsed = tables(content)
    headers = tuple(vocabulary["checked_headers"])
    return {
        "status": "read",
        "path": relative.as_posix(),
        "content": content,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "orders": sorted(set(ids.findall(content))),
        "tables": parsed,
        "has_required_headers": any(tuple(table[0]) == headers for table in parsed),
        "scope": "Presence is not complete confirmation: inspect every six-field row, actual owner confirmation and dates. Order-id mentions alone do not prove a valid saved record.",
    }


def delegations(exchanges) -> dict:
    """Whom the employee handed work to: each delegation's agent, node and title, and the child runs recorded."""
    handed, children = [], {}
    for row in _events(exchanges):
        kind = row.get("kind")
        if kind == "runner.event":
            event = row.get("event") or {}
            if event.get("phase") != "start" or event.get("name") not in DELEGATING:
                continue
            arguments = event.get("arguments") or {}
            nodes = arguments.get("nodes") if event["name"] == "run_subagent_dag" else [arguments]
            for node in nodes or ():
                if isinstance(node, dict):
                    handed.append(
                        {
                            "tool": event["name"],
                            "agent": node.get("subagent") or node.get("agent"),
                            "node": node.get("node_id") or node.get("id"),
                            "title": str(arguments.get("task_summary") or "")[:SNIPPET],
                        }
                    )
        elif kind == "child.execution":
            harness = str(row.get("harness") or "")
            children[harness] = children.get(harness, 0) + 1
    found = {}
    if handed:
        found["delegation_scope"] = (
            "These are delegation attempts and observed child appearances, not successful completion of the requested task."
        )
        found["delegated"] = handed[:20]
        found["delegated_count"] = len(handed)
    if children:
        found["child_runs"] = children
    return found


class StudioOwner(Owner):
    """The owner of the photo studio, judging review pages with the figures its own ledger gives."""

    def __init__(self, scenario, provider, skills, **options):
        super().__init__(scenario, provider, skills, facts=self._facts, **options)
        self.vocabulary = Words(words(Path(scenario.root) / CONFIG))
        price = frontmatter(scenario.text(self.vocabulary.one("price_material")))[1]
        self.prices = Prices.read(price, self.vocabulary)
        self.personas = {persona.name: persona for persona in getattr(scenario, "personas", ())}
        self.ledgers: dict[Path, Ledger] = {}

    def figures(self, card: str | None) -> dict | None:
        """What the card's ledger gives for the period it asks; None when the card hands over no ledger."""
        persona = self.personas.get(card) if card else None
        key = f"period_{card}"
        if persona is None or key not in self.vocabulary.found:
            return None
        books = [path for path in persona.files if Path(path).suffix.lower() == ".xlsx"]
        if not books:
            return None
        path = Path(books[0])
        if path not in self.ledgers:
            self.ledgers[path] = Ledger(path, self.vocabulary, self.prices)
        marker = self.vocabulary.one("checked_file")
        ids = re.compile(rf"{re.escape(self.vocabulary.one('sheet_wechat'))}-\d{{4}}|\d{{16,19}}")
        checked = tuple(
            order
            for item in persona.files
            if marker in Path(item).name and Path(item).suffix == ".md"
            for order in ids.findall(Path(item).read_text())
        )
        start, end = self.vocabulary[key]
        return self.ledgers[path].figures((start, end), checked)

    def _facts(self, name, exchanges, card) -> dict:
        found: dict = {}
        figures = self.figures(card_of(name, card))
        if figures:
            found["ledger_answer"] = figures
        found.update(page_facts(exchanges, figures, self.vocabulary))
        found.update(questions_before_page(exchanges, self.vocabulary))
        year = figures["period"][:4] if figures else None
        placed = self.workdirs.get(name) or {}
        state = checked_records(exchanges, self.vocabulary, year, workdir=placed.get("workdir"))
        found["checked_orders_state"] = state
        if state["status"] == "read":
            found["checked_order_files"] = [state]
        actual = self.personas.get(card_of(name, card))
        found["card"] = card_of(name, card)
        found["provided_base_pages"] = []
        if actual:
            for source in actual.files:
                if Path(source).suffix.lower() != ".md":
                    continue
                for raw in re.findall(r"```html\s*\n(.*?)```", Path(source).read_text(), re.S):
                    found["provided_base_pages"].append(
                        {"name": Path(source).name, "source": raw, "rendered": render(raw)}
                    )
        found["native_operations"] = []

        def capture(rows, scope):
            for row in rows:
                if row.get("kind") == "child.execution":
                    capture(
                        row.get("records") or (),
                        {key: row.get(key) for key in ("harness", "launch", "pid", "log", "omitted")},
                    )
                elif row.get("kind") == "runner.event" and row.get("event_type", "ToolEvent") == "ToolEvent":
                    found["native_operations"].append(
                        {
                            "scope": scope,
                            "event": row.get("event"),
                            "observed_at": row.get("observed_at"),
                            "monotonic_ns": row.get("monotonic_ns"),
                        }
                    )

        for turn, exchange in enumerate(exchanges, 1):
            capture(exchange.execution.records, {"actor": "assistant", "turn": turn})
        found.update(delegations(exchanges))
        return found


# The owner the simulation entry judges this case by (`experimental.simulation.__main__.owner_of`).
DELIVERED = delivered_as_requested
OWNER = StudioOwner
