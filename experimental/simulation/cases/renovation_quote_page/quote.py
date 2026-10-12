"""The renovation company's quote rules, computed exactly, for the owner's reference figures.

The finance rules (the `quote-rules` material) fix the arithmetic: the billed area is at least the minimum area, the
base and the demolition are billed on it, the management fee and the tax are each rounded to the fen, the promotion
in force on the quote date is judged on the gross with tax (a threshold met exactly counts) and only the final total
is rounded to the yuan, half up. Which price list and which promotion are in force on a date is read from the price
list and promotion materials themselves, so the owner computes from the documents the employee holds. The rates, the
area bounds and the words a parse needs are the case's `reference.md` values; nothing here judges anything.
"""

import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from experimental.cultivation.counterpart.rulers import tables
from experimental.harness.scenario.contract import document

FEN = Decimal("0.01")
YUAN = Decimal("1")
DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
FIGURE = re.compile(r"\d[\d,]*(?:\.\d+)?")
# Full-width ASCII forms and the ideographic space, mapped to their half-width forms.
HALF = {code: code - 0xFEE0 for code in range(0xFF01, 0xFF5F)} | {0x3000: 0x20}


def _day(text: str) -> date:
    found = DATE.search(text)
    if not found:
        raise ValueError(f"no date in {text!r}")
    return date(*(int(part) for part in found.groups()))


def _days(text: str) -> list[date]:
    return [date(*(int(part) for part in found)) for found in DATE.findall(text)]


def _figure(text: str) -> Decimal:
    found = FIGURE.search(text)
    if not found:
        raise ValueError(f"no figure in {text!r}")
    return Decimal(found.group().replace(",", ""))


@dataclass(frozen=True)
class PriceList:
    code: str
    start: date
    units: dict[str, Decimal]
    demolition: Decimal
    custom: Decimal


@dataclass(frozen=True)
class Promotion:
    code: str
    start: date
    end: date
    tiers: tuple[tuple[Decimal, Decimal], ...]

    def cut(self, gross: Decimal) -> Decimal:
        """The highest tier the gross reaches, a threshold met exactly included."""
        return next((cut for threshold, cut in self.tiers if gross >= threshold), Decimal(0))


@dataclass(frozen=True)
class Case:
    """One input set as a salesperson types it: `label=area;tier;Y|N;Y|N` (demolition, custom package)."""

    label: str
    area: str
    tier: str
    demolish: bool
    custom: bool

    @classmethod
    def parse(cls, spec: str) -> "Case":
        label, _, rest = spec.partition("=")
        area, tier, demolish, custom = rest.split(";")
        return cls(label, area, tier, demolish == "Y", custom == "Y")

    def __str__(self) -> str:
        return f"{self.label} {self.area or '(blank)'}/{self.tier}/{'Y' if self.demolish else 'N'}/{'Y' if self.custom else 'N'}"


@dataclass(frozen=True)
class Quote:
    billed: Decimal
    base: Decimal
    demolition: Decimal
    custom: Decimal
    management: Decimal
    tax: Decimal
    gross: Decimal
    discount: Decimal
    total: Decimal
    price_list: str
    promotion: str | None
    valid_until: date


@dataclass(frozen=True)
class Book:
    """The rates and bounds of the finance rules and every price list and promotion the materials hold."""

    tiers: tuple[str, ...]
    units: tuple[str, ...]
    management: Decimal
    tax: Decimal
    minimum: Decimal
    low: Decimal
    high: Decimal
    validity: int
    price_lists: tuple[PriceList, ...]
    promotions: tuple[Promotion, ...]

    def price_list(self, on: date) -> PriceList:
        started = [item for item in self.price_lists if item.start <= on]
        if not started:
            raise ValueError(f"no price list is in force on {on}")
        return max(started, key=lambda item: item.start)

    def promotion(self, on: date) -> Promotion | None:
        return next((item for item in self.promotions if item.start <= on <= item.end), None)

    def area(self, raw: str) -> Decimal | None:
        """The area the finance rules accept from what was typed, or None when the page must refuse it."""
        text = (raw or "").translate(HALF).strip()
        for unit in self.units:
            if text.endswith(unit):
                text = text[: -len(unit)].rstrip()
                break
        if not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", text):
            return None
        value = Decimal(text)
        return value if self.low <= value <= self.high else None

    def quote(self, case: Case, on: date) -> Quote | None:
        """The quote sheet the rules give for `case` on `on`, or None when the area must be refused."""
        area = self.area(case.area)
        if area is None:
            return None
        prices, promotion = self.price_list(on), self.promotion(on)
        billed = max(area, self.minimum)
        base = billed * prices.units[case.tier]
        demolition = billed * prices.demolition if case.demolish else Decimal(0)
        custom = prices.custom if case.custom else Decimal(0)
        subtotal = base + demolition + custom
        management = (subtotal * self.management).quantize(FEN, ROUND_HALF_UP)
        tax = ((subtotal + management) * self.tax).quantize(FEN, ROUND_HALF_UP)
        gross = subtotal + management + tax
        discount = promotion.cut(gross) if promotion else Decimal(0)
        return Quote(
            billed=billed,
            base=base,
            demolition=demolition,
            custom=custom,
            management=management,
            tax=tax,
            gross=gross,
            discount=discount,
            total=(gross - discount).quantize(YUAN, ROUND_HALF_UP),
            price_list=prices.code,
            promotion=promotion.code if promotion else None,
            valid_until=on + timedelta(days=self.validity),
        )


def _head(text: str, label: str) -> str:
    """The value beside `label` in a document's header table."""
    for table in tables(text):
        for row in table:
            if len(row) > 1 and row[0] == label:
                return row[1]
    raise ValueError(f"no {label!r} row in the document's header table")


def _columns(text: str, *names: str) -> list[dict[str, str]]:
    """The rows of the first table whose header names every column in `names`, as header-to-cell mappings."""
    for table in tables(text):
        header = table[0]
        if all(any(name in cell for cell in header) for name in names):
            return [dict(zip(header, row)) for row in table[1:]]
    raise ValueError(f"no table with the columns {names}")


def _cell(row: dict[str, str], name: str) -> str:
    return next(value for header, value in row.items() if name in header)


def price_list(text: str, words: dict) -> PriceList:
    """A price list material: its code and effective date, and the selling price of each tier and add-on."""
    (code_label,), (start_label,) = words["code_label"], words["effective_label"]
    (item,), (column,) = words["item_column"], words["price_column"]
    rows = _columns(text, item, column)

    def price(match) -> Decimal:
        return _figure(_cell(next(row for row in rows if match(_cell(row, item))), column))

    return PriceList(
        code=_head(text, code_label),
        start=_day(_head(text, start_label)),
        units={tier: price(lambda name, tier=tier: name == tier) for tier in words["tier_names"]},
        demolition=price(lambda name: words["demolition_label"][0] in name),
        custom=price(lambda name: words["custom_label"][0] in name),
    )


def promotion(text: str, words: dict) -> Promotion:
    """A promotion material: its code, its period and its tiers, highest threshold first."""
    (code_label,), (period_label,) = words["code_label"], words["period_label"]
    (threshold,), (cut,) = words["threshold_column"], words["cut_column"]
    start, end = _days(_head(text, period_label))[:2]
    tiers = sorted(
        ((_figure(_cell(row, threshold)), _figure(_cell(row, cut))) for row in _columns(text, threshold, cut)),
        reverse=True,
    )
    return Promotion(code=_head(text, code_label), start=start, end=end, tiers=tuple(tiers))


def load(root: Path, words: dict) -> Book:
    """The book the owner computes with: the rates of `reference.md` and the materials' price lists and promotions."""
    materials = Path(root) / "materials"

    def read(name: str) -> str:
        found = document(materials / name)
        if found is None:
            raise ValueError(f"material {name} has no document")
        return found.read_text()

    management, tax = (Decimal(value) for value in words["rates"])
    low, high = (Decimal(value) for value in words["area_bounds"])
    return Book(
        tiers=words["tier_names"],
        units=words["area_units"],
        management=management,
        tax=tax,
        minimum=Decimal(words["minimum_area"][0]),
        low=low,
        high=high,
        validity=int(words["validity_days"][0]),
        price_lists=tuple(price_list(read(name), words) for name in words["price_lists"]),
        promotions=tuple(promotion(read(name), words) for name in words["promotions"]),
    )


def money(value: Decimal) -> str:
    """A total as the quote sheet shows it: whole yuan with thousands separators."""
    return f"{int(value):,}"
