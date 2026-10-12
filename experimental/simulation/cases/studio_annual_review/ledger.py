"""The studio's order ledger read from its workbook, and the figures the owner's conventions give for a period.

The workbook is read with the standard library (zip and XML), cell by cell with its column, the way the owner keeps
it: three sheets (the platform export, the hand-copied short-video export and the WeChat ledger), merged title rows,
dates as Excel serials or as text in several styles, amounts with currency marks. The words it needs (sheet names,
column headers, status and payment words) and the price history are the scenario's, read from its `reference.md` and
its price material, so no case wording lives in this code.

`Ledger.figures` gives, for a period: monthly revenue by shoot day, month-on-month changes, the biggest drop, revenue
by channel, the repurchase rate, the entry errors and duplicates to list, the zero-amount orders, the orders crossing
a price change, and a breakdown for follow-up questions. Nothing here judges the employee's work.
"""

import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from xml.etree import ElementTree

from experimental.cultivation.counterpart.rulers import tables

_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_RELS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_REL_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
_EPOCH = datetime(1899, 12, 30)
PACKAGES = ("id_photo", "portrait_basic", "portrait_classic", "portrait_premium", "family")
CHANNELS = ("dianping", "douyin", "wechat")
PLATFORM_COLUMNS = ("id", "listing", "bought", "used", "phone", "paid", "status")
WECHAT_COLUMNS = ("id", "day", "name", "phone", "package", "kind", "paid", "note")
YEAR_DAYS = 365
LISTED = 12


def half_up(value: Decimal, places: int = 0) -> float:
    step = Decimal(1).scaleb(-places)
    return float(value.quantize(step, rounding=ROUND_HALF_UP))


def column_index(reference: str) -> int:
    letters = re.match(r"[A-Z]+", reference).group()
    number = 0
    for letter in letters:
        number = number * 26 + ord(letter) - 64
    return number - 1


def workbook(path: Path) -> dict[str, list[tuple[int, dict[int, object]]]]:
    """Each sheet by title: its rows in order, each its number and its cells by column index (strings or floats)."""
    with zipfile.ZipFile(path) as book:
        names = set(book.namelist())
        shared = []
        if "xl/sharedStrings.xml" in names:
            for item in ElementTree.fromstring(book.read("xl/sharedStrings.xml")).iter(f"{_MAIN}si"):
                shared.append("".join(node.text or "" for node in item.iter(f"{_MAIN}t")))
        targets = {
            rel.get("Id"): rel.get("Target")
            for rel in ElementTree.fromstring(book.read("xl/_rels/workbook.xml.rels")).iter(f"{_RELS}Relationship")
        }
        sheets = {}
        for sheet in ElementTree.fromstring(book.read("xl/workbook.xml")).iter(f"{_MAIN}sheet"):
            target = targets[sheet.get(_REL_ID)].lstrip("/")
            target = target if target.startswith("xl/") else f"xl/{target}"
            rows = []
            for row in ElementTree.fromstring(book.read(target)).iter(f"{_MAIN}row"):
                cells = {}
                for cell in row.iter(f"{_MAIN}c"):
                    kind, value = cell.get("t"), cell.find(f"{_MAIN}v")
                    if kind == "s" and value is not None:
                        cells[column_index(cell.get("r"))] = shared[int(value.text)]
                    elif kind == "inlineStr":
                        cells[column_index(cell.get("r"))] = "".join(node.text or "" for node in cell.iter(f"{_MAIN}t"))
                    elif kind == "str" and value is not None:
                        cells[column_index(cell.get("r"))] = value.text or ""
                    elif value is not None and value.text not in (None, ""):
                        cells[column_index(cell.get("r"))] = float(value.text)
                rows.append((int(row.get("r")), cells))
            sheets[sheet.get("name")] = rows
        return sheets


@dataclass(frozen=True)
class Words:
    """The scenario's words for its ledger, from the `reference.md` table (see `experimental.cultivation.counterpart.rulers.words`)."""

    found: dict[str, tuple[str, ...]]

    def __getitem__(self, key: str) -> tuple[str, ...]:
        return self.found[key]

    def one(self, key: str) -> str:
        return self.found[key][0]

    def columns(self, sheet: str) -> tuple[str, ...]:
        """One sheet's column headers, in the order `Ledger` reads them."""
        roles = PLATFORM_COLUMNS if sheet != "wechat" else WECHAT_COLUMNS
        return tuple(self.one(f"{sheet}_{role}") for role in roles)


@dataclass(frozen=True)
class Prices:
    """The price history: each change's day and the prices from that day on, by package and for one extra retouch."""

    changes: tuple[tuple[date, dict[str, int]], ...]

    @classmethod
    def read(cls, text: str, words: Words) -> "Prices":
        columns = words["price_columns"]
        for table in tables(text):
            header, *rows = table
            if not header or not header[0].startswith(words.one("price_header")):
                continue
            where = [next(index for index, cell in enumerate(header) if cell.startswith(name)) for name in columns]
            changes = []
            for row in rows:
                day = date.fromisoformat(re.search(r"\d{4}-\d{2}-\d{2}", row[0]).group())
                values = [int(re.search(r"\d+", row[index]).group()) for index in where]
                changes.append((day, dict(zip((*PACKAGES, "retouch"), values))))
            return cls(tuple(sorted(changes)))
        raise ValueError("the price material has no price history table")

    def of(self, item: str, day: date) -> int:
        found = [prices[item] for start, prices in self.changes if day >= start]
        if not found:
            raise ValueError(f"no price for {item} on {day}")
        return found[-1]


@dataclass
class Order:
    id: str
    channel: str
    package: str | None
    ordered: datetime
    shot: datetime | None
    key: tuple[str, str] | None
    valid: bool
    amount: float = 0.0
    rows: list[int] = field(default_factory=list)


def _month(moment: datetime) -> str:
    return f"{moment.year}-{moment.month:02d}"


def _previous(month: str) -> str:
    year, number = int(month[:4]), int(month[5:])
    return f"{year - 1}-12" if number == 1 else f"{year}-{number - 1:02d}"


def months(first: str, last: str) -> list[str]:
    out, current = [], first
    while current <= last:
        out.append(current)
        year, number = int(current[:4]), int(current[5:])
        current = f"{year + 1}-01" if number == 12 else f"{year}-{number + 1:02d}"
    return out


class Ledger:
    """One workbook read the owner's way; `problems` lists the cells it could not read."""

    def __init__(self, path: Path, words: Words, prices: Prices):
        self.words, self.prices, self.problems = words, prices, []
        self.year = int(re.search(r"(20\d\d)", Path(path).name).group(1))
        self.sheets = workbook(path)
        self.orders: list[Order] = []
        self.errors: list[dict] = []
        self.duplicates: list[dict] = []
        self.zero: list[dict] = []
        self.linked: dict[str, str] = {}
        self._read()

    # ---------- reading cells ----------
    def _date(self, value) -> datetime | None:
        if value is None or value == "":
            return None
        if isinstance(value, float):
            return _EPOCH + timedelta(seconds=round(value * 86400))
        text = str(value).strip()
        year_word, month_word, day_word = self.words["date_words"]
        clock = r"(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?"
        found = re.fullmatch(rf"(\d{{4}})[-/.](\d{{1,2}})[-/.](\d{{1,2}}){clock}", text)
        if found:
            y, m, d, hh, mm, ss = found.groups()
            return datetime(int(y), int(m), int(d), int(hh or 0), int(mm or 0), int(ss or 0))
        found = re.fullmatch(rf"(\d{{1,2}})/(\d{{1,2}}){clock}", text)
        if found:
            m, d, hh, mm, ss = found.groups()
            return datetime(self.year, int(m), int(d), int(hh or 0), int(mm or 0), int(ss or 0))
        found = re.fullmatch(
            rf"(?:(\d{{4}}){re.escape(year_word)})?(\d{{1,2}}){re.escape(month_word)}(\d{{1,2}}){re.escape(day_word)}{clock}",
            text,
        )
        if found:
            y, m, d, hh, mm, ss = found.groups()
            return datetime(int(y or self.year), int(m), int(d), int(hh or 0), int(mm or 0), int(ss or 0))
        self.problems.append(f"unreadable date {text!r}")
        return None

    def _amount(self, value) -> float | None:
        if isinstance(value, float):
            return value
        text = str(value or "").replace(",", "").replace(" ", "")
        for mark in self.words["money_marks"]:
            text = text.replace(mark, "")
        try:
            return float(text)
        except ValueError:
            self.problems.append(f"unreadable amount {value!r}")
            return None

    @staticmethod
    def _key(value) -> tuple[str, str] | None:
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        digits = re.sub(r"[^\d*]", "", str(value or ""))
        if len(digits) != 11 or "*" in digits[:3] + digits[-4:]:
            return None
        return digits[:3], digits[-4:]

    def _package(self, text) -> str | None:
        for word, package in zip(self.words["package_words"], PACKAGES):
            if word in str(text or ""):
                return package
        return None

    def _table(self, sheet: str, first: str, names: tuple[str, ...]) -> list[tuple[int, dict[str, object]]]:
        rows = self.sheets.get(sheet, [])
        for at, (_, cells) in enumerate(rows):
            labels = {str(value).strip(): index for index, value in cells.items()}
            if first in labels:
                where = {name: labels.get(name) for name in names}
                return [
                    (number, {name: cells.get(index) if index is not None else None for name, index in where.items()})
                    for number, cells in rows[at + 1 :]
                    if cells.get(labels[first]) not in (None, "")
                ]
        self.problems.append(f"no header row in sheet {sheet}")
        return []

    # ---------- orders ----------
    def _read(self) -> None:
        words, prices = self.words, self.prices
        platform: dict[str, Order] = {}
        for channel, sheet, columns in (
            ("dianping", words.one("sheet_dianping"), words.columns("dianping")),
            ("douyin", words.one("sheet_douyin"), words.columns("douyin")),
        ):
            ident, listing, bought, used, phone, paid, status = columns
            for number, row in self._table(sheet, ident, columns):
                oid = str(row[ident]).strip()
                if oid in platform:
                    self.duplicates.append({"order": oid, "sheet": sheet, "rows": [platform[oid].rows[0], number]})
                    continue
                package, ordered = self._package(row[listing]), self._date(row[bought])
                if package is None or ordered is None:
                    self.problems.append(f"{sheet} row {number}: no package or order time")
                    continue
                done = str(row[status] or "").strip() in words["done_status"]
                shot = self._date(row[used]) if done else None
                order = Order(oid, channel, package, ordered, shot, self._key(row[phone]), done and shot is not None)
                order.rows.append(number)
                expected, recorded = prices.of(package, ordered.date()), self._amount(row[paid])
                order.amount = expected
                if order.valid and recorded is not None and abs(recorded - expected) > 0.5:
                    self.errors.append(
                        {"order": oid, "sheet": sheet, "row": number, "recorded": row[paid], "should_be": expected}
                    )
                platform[oid] = order
        self._wechat(platform)
        self.orders.extend(platform.values())

    def _wechat(self, platform: dict[str, Order]) -> None:
        words, prices = self.words, self.prices
        sheet = words.one("sheet_wechat")
        columns = words.columns("wechat")
        ident, day, _, phone, package_column, kind_column, paid, note = columns
        full, deposit_word, balance_word, addon_word, refund_word = words["payment_types"]
        unit = words.one("count_unit")
        groups: dict[str, list[tuple[int, dict]]] = {}
        seen: dict[tuple[str, str], int] = {}
        for number, row in self._table(sheet, ident, columns):
            oid, kind = str(row[ident]).strip(), str(row[kind_column] or "").strip()
            if (oid, kind) in seen:
                self.duplicates.append({"order": oid, "sheet": sheet, "rows": [seen[(oid, kind)], number]})
                continue
            seen[(oid, kind)] = number
            groups.setdefault(oid, []).append((number, row))
        addons = re.compile(rf"{re.escape(addon_word)}(\d+){re.escape(unit)}")
        deposit = int(words.one("deposit"))
        for oid, rows in groups.items():
            by_kind = {str(row[kind_column] or "").strip(): (number, row) for number, row in rows}
            if addon_word in by_kind and len(by_kind) == 1:
                number, row = by_kind[addon_word]
                linked = re.search(r"\d{12,}", str(row[note] or ""))
                count = addons.search(str(row[note] or ""))
                when = self._date(row[day])
                target = platform.get(linked.group()) if linked else None
                if target is None or count is None or when is None:
                    self.problems.append(f"{sheet} row {number}: an extra retouch not tied to an order")
                    continue
                expected = int(count.group(1)) * prices.of("retouch", when.date())
                target.amount += expected
                target.rows.append(number)
                self.linked[oid] = target.id
                recorded = self._amount(row[paid])
                if recorded is not None and abs(recorded - expected) > 0.5:
                    self.errors.append(
                        {"order": oid, "sheet": sheet, "row": number, "recorded": row[paid], "should_be": expected}
                    )
                continue
            first = rows[0][1]
            package = self._package(first[package_column])
            paid_deposit = by_kind.get(deposit_word)
            final = by_kind.get(balance_word) or by_kind.get(full)
            start = self._date((paid_deposit or final or rows[0])[1][day])
            shot = self._date(final[1][day]) if final else None
            if final is not None and final is by_kind.get(full) and self._amount(final[1][paid]) == 0:
                text = str(final[1][note] or "").strip()
                self.zero.append(
                    {
                        "order": oid,
                        "day": shot.date().isoformat() if shot else None,
                        "note": text,
                        "noted": any(word in text for word in words["clear_note"]),
                        "row": final[0],
                    }
                )
                continue
            if package is None or start is None:
                self.problems.append(f"{sheet} order {oid}: no package or date")
                continue
            total = 0.0
            if paid_deposit is not None:
                total += deposit
                recorded = self._amount(paid_deposit[1][paid])
                if recorded is not None and abs(recorded - deposit) > 0.5:
                    self.errors.append(
                        {
                            "order": oid,
                            "sheet": sheet,
                            "row": paid_deposit[0],
                            "recorded": paid_deposit[1][paid],
                            "should_be": deposit,
                        }
                    )
            if final is not None and shot is not None:
                extra = addons.search(str(final[1][note] or ""))
                retouch = int(extra.group(1)) * prices.of("retouch", shot.date()) if extra else 0
                if final is by_kind.get(balance_word):
                    expected = prices.of(package, start.date()) - deposit + retouch
                else:
                    expected = prices.of(package, shot.date()) + retouch
                total += expected
                recorded = self._amount(final[1][paid])
                if recorded is not None and abs(recorded - expected) > 0.5:
                    self.errors.append(
                        {
                            "order": oid,
                            "sheet": sheet,
                            "row": final[0],
                            "recorded": final[1][paid],
                            "should_be": expected,
                        }
                    )
            for number, row in rows:
                if str(row[kind_column] or "").strip() == refund_word:
                    total += self._amount(row[paid]) or 0.0
            order = Order(oid, "wechat", package, start, shot, self._key(first[phone]), shot is not None and total > 0)
            order.amount = total
            order.rows = [number for number, _ in rows]
            self.orders.append(order)

    # ---------- figures ----------
    def _inside(self, order: str, in_period: set[str]) -> bool:
        """Whether an order, or the order an extra-retouch row belongs to, was shot in the period."""
        return order in in_period or self.linked.get(order) in in_period

    def figures(self, period: tuple[str, str], checked: tuple[str, ...] = ()) -> dict:
        wanted = months(*period)
        inside = set(wanted)
        before = _previous(wanted[0])
        shown = ([before] if before >= f"{self.year}-01" else []) + wanted
        valid = [order for order in self.orders if order.valid]
        monthly = {month: Decimal(0) for month in shown}
        counts = {month: 0 for month in shown}
        packages = {month: {package: 0 for package in PACKAGES} for month in shown}
        channels = {channel: Decimal(0) for channel in CHANNELS}
        mix = {channel: {package: [0, 0] for package in PACKAGES} for channel in CHANNELS}
        shoot_days: set[date] = set()
        for order in valid:
            month = _month(order.shot)
            if month in monthly:
                monthly[month] += Decimal(str(order.amount))
                counts[month] += 1
                packages[month][order.package] += round(order.amount)
            if month in inside:
                channels[order.channel] += Decimal(str(order.amount))
                mix[order.channel][order.package][0] += 1
                mix[order.channel][order.package][1] += round(order.amount)
                shoot_days.add(order.shot.date())
        changes = {}
        for month in wanted:
            prior = _previous(month)
            if prior in monthly and monthly[prior]:
                changes[month] = half_up((monthly[month] - monthly[prior]) * 100 / monthly[prior], 1)
        drops = {month: change for month, change in changes.items() if change < 0}
        drop = min(drops.items(), key=lambda item: item[1]) if drops else None
        events = sorted(valid, key=lambda order: (order.shot, order.ordered, order.id))
        earlier: dict[tuple[str, str], list[datetime]] = {}
        counted = repeat = 0
        for order in events:
            if _month(order.shot) in inside:
                counted += 1
                if order.key and any(
                    moment.date() < order.shot.date() and order.shot - moment <= timedelta(days=YEAR_DAYS)
                    for moment in earlier.get(order.key, ())
                ):
                    repeat += 1
            if order.key:
                earlier.setdefault(order.key, []).append(order.shot)
        in_period = {order.id for order in valid if _month(order.shot) in inside}
        listed = [item for item in self.errors if self._inside(item["order"], in_period)]
        twice = [item for item in self.duplicates if self._inside(item["order"], in_period)]
        wrong = {item["order"] for item in listed} | {item["order"] for item in twice}
        crossing = [
            {
                "order": order.id,
                "channel": order.channel,
                "ordered": order.ordered.date().isoformat(),
                "shot": order.shot.date().isoformat(),
                "price_then": self.prices.of(order.package, order.ordered.date()),
                "price_on_shoot_day": self.prices.of(order.package, order.shot.date()),
            }
            for order in valid
            if order.id in in_period
            and order.id not in wrong
            and self.prices.of(order.package, order.ordered.date()) != self.prices.of(order.package, order.shot.date())
        ]
        top = max(channels, key=channels.get)
        return {
            "period": f"{period[0]} to {period[1]}",
            "monthly_revenue": {month: round(value) for month, value in monthly.items()},
            "valid_orders_by_month": counts,
            "month_on_month_percent": changes,
            "biggest_drop": {"month": drop[0], "percent": drop[1], "rounded": int(half_up(Decimal(str(drop[1]))))}
            if drop
            else "no month fell",
            "channel_revenue": {channel: round(value) for channel, value in channels.items()},
            "top_channel": top,
            "valid_orders": counted,
            "repurchase_orders": repeat,
            "repurchase_rate_percent": int(half_up(Decimal(repeat) * 100 / Decimal(counted))) if counted else None,
            "entry_errors": listed,
            "duplicates": twice,
            "zero_amount": [
                {**item, "on_checked_list": item["order"] in checked}
                for item in self.zero
                if item["day"] and item["day"][:7] in inside
            ],
            "price_change_orders": crossing[:LISTED],
            "price_change_count": len(crossing),
            "revenue_by_package": {month: values for month, values in packages.items()},
            "orders_and_revenue_by_channel_and_package": {
                channel: {package: pair for package, pair in values.items() if pair[0]}
                for channel, values in mix.items()
            },
            "days_without_shoots": self._quiet(wanted, shoot_days),
            "unreadable": self.problems[:LISTED],
        }

    @staticmethod
    def _quiet(wanted: list[str], days: set[date]) -> dict[str, str]:
        """Per month, its longest run of four or more days without a shoot."""
        found = {}
        for month in wanted:
            year, number = int(month[:4]), int(month[5:])
            day, best, run = date(year, number, 1), None, None
            while day.month == number:
                if day in days:
                    run = None
                else:
                    run = run or day
                    if best is None or (day - run) > (best[1] - best[0]):
                        best = (run, day)
                day += timedelta(days=1)
            if best and (best[1] - best[0]).days >= 3:
                found[month] = f"{best[0].isoformat()} to {best[1].isoformat()}"
        return found
