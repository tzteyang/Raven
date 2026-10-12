"""The studio annual review case: it loads as a scenario with a by-stage plan, its cards and handouts are complete, the
owner's figures read from each card's ledger agree with the card's expected answer, and the owner measures a delivered
page, the questions asked before it, the checked-orders record and any delegation the way the case's criteria use them.

Chinese words are read from the case's `reference.md`, so this module stays in ASCII."""

import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest

from experimental.cultivation.counterpart.rulers import CONFIG, words
from experimental.harness.participation.files import read_delivered
from experimental.harness.scenario.contract import load
from experimental.harness.scenario.disclosure import Disclosure, partition
from experimental.harness.scenario.sealed import sealed_for
from experimental.simulation.bench.scenario import BUNDLED, Scenario
from experimental.simulation.cases.studio_annual_review.ledger import Words
from experimental.simulation.cases.studio_annual_review.owner import StudioOwner, blocks, card_of

ROOT = BUNDLED / "studio_annual_review"
VOCABULARY = Words(words(ROOT / CONFIG))
WECHAT = VOCABULARY.one("sheet_wechat")
MONTH = VOCABULARY["date_words"][1]
YUAN = VOCABULARY.one("money_marks")
STOP = VOCABULARY.one("sentence_ends")
ASK = VOCABULARY.one("question_marks")
ORDER = re.compile(rf"{WECHAT}-\d{{4}}|\d{{16,19}}")
CHANNELS = {"Dianping": "dianping", "Douyin": "douyin", "WeChat ledger": "wechat"}
CARDS = sorted(case.id for case in load(ROOT).situation.cases)
CJK = re.compile(
    "["
    + "".join(f"{chr(low)}-{chr(high)}" for low, high in ((0x3000, 0x303F), (0x4E00, 0x9FFF), (0xFF00, 0xFFEF)))
    + "]+"
)


def _line(expected: str, label: str) -> str | None:
    return next((line for line in expected.splitlines() if line.startswith(label)), None)


def _rounded(value) -> int:
    return int(Decimal(str(abs(value))).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _amount(text: str) -> int:
    return int(text.replace(",", ""))


def test_the_case_loads_with_its_plan_schedule_and_owner():
    read = load(ROOT)
    assert len(read.materials) == 6 and len(read.situation.cases) == 12
    plan = read.exchange.plans["by-stage"]
    assert partition(plan.steps, read.handed) and len(plan.labels) == len(plan.steps) == 2
    assert set(read.exchange.initial) == set(plan.steps[0])
    schedule = read.situation.schedule
    names = {case.id for case in read.situation.cases}
    assert {name for step in schedule.rounds for name in step} | set(schedule.holdout) <= names
    assert [len(step) for step in schedule.rounds] == [3, 3, 2]
    assert schedule.rounds[2] == (schedule.rounds[0][0], schedule.rounds[0][2])
    assert schedule.holdout_rounds == (0, 1, 3) and len(schedule.holdout) == 6
    assert not set(schedule.holdout) & {name for step in schedule.rounds for name in step}
    assert Disclosure.of("by-stage", materials=read.handed, plans=read.exchange.plans, rounds=3).steps
    norms = {name for name, material in read.materials.items() if material.kind == "norm"}
    assert all(check.derived_from and set(check.derived_from) <= norms for check in read.statements.checks)
    assert 6 <= len(read.statements.checks) <= 9
    assert {check.severity for check in read.statements.checks} >= {"red_line"}


def test_every_card_has_its_files_an_expected_answer_and_a_period():
    read = load(ROOT)
    for case in read.situation.cases:
        assert re.fullmatch(r"[a-z]+", case.id)
        assert case.files and all((ROOT / item).is_file() for item in case.files), case.id
        assert sum(Path(item).suffix == ".xlsx" for item in case.files) == 1, case.id
        assert case.expected and case.expected.strip(), case.id
        assert all(len(run) < 15 for run in CJK.findall(case.expected)), case.id
        start, end = VOCABULARY[f"period_{case.id}"]
        assert start <= end and start[:4] == end[:4]
    twin = {case.id: case for case in read.situation.cases}
    original, again = twin["siji"], twin["sijiagain"]
    assert original.text == again.text and original.expected == again.expected
    assert [(ROOT / item).read_bytes() for item in original.files] == [
        (ROOT / item).read_bytes() for item in again.files
    ]


def test_nothing_the_employee_sees_names_the_case_or_its_checks():
    read = load(ROOT)
    seen = [ROOT / "profile.md", ROOT / "onboarding.md", ROOT / "handover.md"]
    seen += [path for path in (ROOT / "materials").rglob("*") if path.is_file()]
    seen += [path for path in (ROOT / "handouts").rglob("*") if path.is_file()]
    seen += list((ROOT / "personas").glob("*.md"))
    sealed = [ROOT.name, *(check.id for check in read.statements.checks)]
    for path in seen:
        text = read_delivered(path) if path.suffix == ".xlsx" else path.read_text()
        assert not [name for name in sealed if name in text], path


def test_a_natural_restatement_of_the_conventions_meets_no_sealed_window():
    read = load(ROOT)
    seals = [sealed_for(read, role) for role in ("curator", "partner")]
    for text in (
        "When the owner confirms an order is fine, the order is written into the year's checked-orders file in the "
        "review folder, not the inbox.",
        "A price-change order, a noted or checked zero-amount order, or an order from another month is not an error.",
        "Report every entry error or duplicate for the period with its order number; do not report a price-change "
        "order, a noted or checked zero-amount order, or an order from another month.",
        "When the owner questions a figure or asks for more, the reply goes back to the ledger with concrete figures, "
        "keeps a right figure rather than giving way, corrects a wrong one and hands the page over again, and states "
        "nothing the ledger cannot show.",
        "Each request ends with exactly one HTML page handed over as a file; no spreadsheet, slide deck or Word "
        "document.",
        "If the new page changes the earlier layout or counting line, say so; do not drop one of its sections; say "
        "under its title what changed.",
    ):
        assert [seal.hits(text) for seal in seals] == [[], []], text


@pytest.fixture(scope="module")
def owner(tmp_path_factory):
    folder = tmp_path_factory.mktemp("owner")
    return StudioOwner(Scenario.load(ROOT), object(), folder / "skills", workdir=folder / "work", deliver="pool")


@pytest.mark.parametrize("name", CARDS)
def test_the_owner_figures_agree_with_each_cards_expected_answer(owner, name):
    expected = owner.personas[name].expected
    figures = owner.figures(name)
    drop = _line(expected, "Biggest month-on-month drop:")
    if drop:
        month, percent = re.search(r"(\d{4}-\d{2}), (-\d+)%", drop).groups()
        assert figures["biggest_drop"]["month"] == month and figures["biggest_drop"]["rounded"] == int(percent)
        line = drop
    else:
        line = _line(expected, "Month on month:")
        month, way, percent = re.search(r"(\d{4}-\d{2}) (up|down) (\d+)%", line).groups()
        change = figures["month_on_month_percent"][month]
        assert _rounded(change) == int(percent) and (change > 0) == (way == "up")
        assert (figures["biggest_drop"] == "no month fell") == (way == "up")
    this, last, prior = re.search(r"\(([\d,]+) vs ([\d,]+) in (\d{4}-\d{2})\)", line).groups()
    assert figures["monthly_revenue"][month] == _amount(this) and figures["monthly_revenue"][prior] == _amount(last)

    channels = re.findall(r"(Dianping|Douyin|WeChat ledger) ([\d,]+)", _line(expected, "Top channel:"))
    assert {CHANNELS[label]: _amount(value) for label, value in channels} == figures["channel_revenue"]
    assert CHANNELS[channels[0][0]] == figures["top_channel"]

    rate, repeat, valid = re.search(r"(\d+)% \((\d+) of (\d+) valid orders\)", expected).groups()
    assert (figures["repurchase_rate_percent"], figures["repurchase_orders"], figures["valid_orders"]) == (
        int(rate),
        int(repeat),
        int(valid),
    )

    listed = _line(expected, "Entry errors to list:")
    found = {item["order"]: item for item in figures["entry_errors"]}
    twice = {item["order"] for item in figures["duplicates"]}
    assert set(ORDER.findall(listed)) == set(found) | twice
    for order, recorded, right in re.findall(rf"({WECHAT}-\d{{4}}|\d{{16,19}}) \(([\d.]+) for (\d+)\)", listed):
        assert found[order]["should_be"] == int(right) and found[order]["recorded"].replace(YUAN, "") == recorded

    zero = _line(expected, "Zero-amount orders:")
    held = {item["order"] for item in figures["zero_amount"] if item["on_checked_list"]}
    noted = {item["order"] for item in figures["zero_amount"] if item["noted"] and not item["on_checked_list"]}
    asked = {item["order"] for item in figures["zero_amount"]} - held - noted
    assert set(ORDER.findall(zero)) == held | noted | asked
    assert {order for part in zero.split("; ") if "checked list" in part for order in ORDER.findall(part)} == held
    assert {order for part in zero.split("; ") if "clear note" in part for order in ORDER.findall(part)} == noted
    assert {order for part in zero.split("; ") if "ask the owner" in part for order in ORDER.findall(part)} == asked

    right_at_old_price = _line(expected, "Not errors:")
    crossing = {item["order"] for item in figures["price_change_orders"]} - set(found)
    assert set(ORDER.findall(right_at_old_price or "")) == crossing
    assert figures["price_change_count"] == len(figures["price_change_orders"])


@dataclass
class Execution:
    records: list = field(default_factory=list)
    deliverables: tuple = ()


@dataclass
class Turn:
    user: str
    execution: Execution


def _text(content: str) -> dict:
    return {"kind": "runner.event", "event_type": "Text", "event": {"content": content}}


def _write(call: str, path: str, content: str) -> list[dict]:
    return [
        {
            "kind": "runner.event",
            "event_type": "ToolEvent",
            "event": {"phase": "start", "tool_call_id": call, "name": "write_file", "arguments": {"path": path}},
        },
        {
            "kind": "runner.event",
            "event_type": "ToolEvent",
            "event": {
                "phase": "complete",
                "tool_call_id": call,
                "ok": True,
                "file_change": {"path": path, "after": content},
            },
        },
    ]


def _delegate() -> list[dict]:
    start = {"kind": "runner.event", "event_type": "ToolEvent"}
    return [
        {
            **start,
            "event": {
                "phase": "start",
                "name": "spawn",
                "arguments": {"subagent": "tidier", "node_id": "n1", "task_summary": "tidy the ledger"},
            },
        },
        {
            **start,
            "event": {
                "phase": "start",
                "name": "run_subagent_dag",
                "arguments": {"nodes": [{"id": "a", "subagent": "counter"}, {"id": "b", "subagent": "writer"}]},
            },
        },
        {"kind": "child.execution", "harness": "tidier"},
    ]


def _page(figures: dict, *, right: bool) -> str:
    drop = figures["biggest_drop"]
    month, percent = int(drop["month"][5:]), abs(drop["rounded"])
    rate = figures["repurchase_rate_percent"]
    orders = [item["order"] for item in figures["entry_errors"]] + [item["order"] for item in figures["duplicates"]]
    if right:
        rows = "".join(f"<li>{order}</li>" for order in orders)
        return (
            f"<html><body><h1>1-9{MONTH}</h1>"
            f"<p>{month}{MONTH} -{percent}%{STOP} 26,489{YUAN}{STOP}</p>"
            f"<p>123,364{YUAN}{STOP}</p><p>{rate}%{STOP} {figures['repurchase_orders']}/{figures['valid_orders']}{STOP}</p><ul>{rows}</ul></body></html>"
        )
    return (
        f"<html><body><h1>1-9{MONTH}</h1>"
        f"<p>a{STOP}b{STOP}c{STOP}</p><p>12.3{VOCABULARY.one('big_unit')} 26489.50{YUAN}</p>"
        f"<p>{orders[0]}</p></body></html>"
    )


@pytest.fixture(scope="module")
def judged(owner, tmp_path_factory):
    figures = owner.figures("qiansanji")
    folder = tmp_path_factory.mktemp("drills")
    record = f"{VOCABULARY.one('review_folder')}/{VOCABULARY.one('checked_file')}-2026.md"
    inbox = f"{VOCABULARY.one('inbox')}/{VOCABULARY.one('checked_file')}-2026.md"
    zero = [item["order"] for item in figures["zero_amount"]]
    found = {}
    for right in (True, False):
        place = folder / ("right" if right else "wrong")
        place.mkdir()
        page = place / "review.html"
        page.write_text(_page(figures, right=right))
        delivered = (str(page),) if right else (str(page), str(place / "figures.xlsx"))
        if not right:
            (place / "figures.xlsx").write_bytes(b"")
        if right:
            exchanges = [
                Turn("hello", Execution([_text(f"1-9{MONTH}{ASK}")])),
                Turn("answer", Execution([*_write("a", record, "\n".join(zero)), _text("ok")], delivered)),
            ]
        else:
            exchanges = [
                Turn("hello", Execution([*_delegate(), *_write("b", inbox, zero[0]), _text("ok")], delivered)),
            ]
        session = "s1-qiansanji" if right else "holdout-qiansanji-2"
        owner.workdirs[session] = {"workdir": place}
        if right:
            actual_record = place / record
            actual_record.parent.mkdir()
            actual_record.write_text("\n".join(zero))
        found[right] = owner._facts("s1-qiansanji" if right else "holdout-qiansanji-2", exchanges, None)
    return figures, found


def test_a_page_that_follows_the_conventions_is_measured_as_such(judged):
    figures, found = judged
    facts = found[True]
    assert facts["ledger_answer"] == figures
    assert facts["html_pages"] == ["review.html"] and facts["other_files"] == []
    measures = facts["page_measures"]
    assert measures["names_drop_month"] and measures["names_drop_percent"] and measures["names_repurchase_percent"]
    assert measures["entry_errors_missing"] == [] and len(measures["entry_errors_named"]) == 4
    assert measures["amounts_with_decimals"] == [] and measures["amounts_in_ten_thousands"] == []
    assert measures["paragraphs_over_two_sentences"] == []
    assert facts["first_page_turn"] == 2 and len(facts["questions_before_first_page"]) == 1
    assert [Path(item["path"]).parent.name for item in facts["checked_order_files"]] == [
        VOCABULARY.one("review_folder")
    ]
    assert set(facts["checked_order_files"][0]["orders"]) == {item["order"] for item in figures["zero_amount"]}
    assert "delegated" not in facts and "child_runs" not in facts


def test_a_page_that_breaks_the_conventions_is_caught(judged):
    _, found = judged
    facts = found[False]
    assert facts["other_files"] == ["figures.xlsx"]
    measures = facts["page_measures"]
    assert not measures["names_drop_month"] and not measures["names_repurchase_percent"]
    assert len(measures["entry_errors_missing"]) == 3
    assert measures["amounts_with_decimals"] and measures["amounts_in_ten_thousands"]
    assert len(measures["paragraphs_over_two_sentences"]) == 1
    assert facts["first_page_turn"] == 1 and facts["questions_before_first_page"] == []
    assert "checked_order_files" not in facts
    assert facts["delegated_count"] == 3 and facts["child_runs"] == {"tidier": 1}
    assert [item["agent"] for item in facts["delegated"]] == ["tidier", "counter", "writer"]


def test_blocks_and_card_names():
    assert blocks("<h1>a</h1><p>b<br>c</p><script>x</script><td>d</td>") == ["a", "b", "c", "d"]
    assert card_of("s1-qiansanji", None) == "qiansanji"
    assert card_of("holdout-sijiagain-2", None) == "sijiagain"
    assert card_of("s3-qiansanji-1", None) == "qiansanji"
    assert card_of("anything", type("Drawn", (), {"name": "erjidu"})()) == "erjidu"
    assert card_of("Not-a-card", None) is None


def test_checked_orders_require_saved_content_in_the_right_folder_and_year(owner, tmp_path):
    owner.workdirs["s1-qiansanji"] = {"workdir": tmp_path}
    marker, folder = VOCABULARY.one("checked_file"), VOCABULARY.one("review_folder")
    order = "1234567890123456"
    failed = _write("failed", f"{folder}/{marker}-2026.md", order)
    failed[-1]["event"]["ok"] = False
    attempted = _write("attempted", f"{folder}/{marker}-2026.md", order)[:1]
    misplaced = _write("elsewhere", f"tmp/{marker}-2026.md", order)
    wrong_year = _write("old", f"{folder}/{marker}-2025.md", order)
    facts = owner._facts(
        "s1-qiansanji", [Turn("hello", Execution([*failed, *attempted, *misplaced, *wrong_year]))], None
    )
    assert "checked_order_files" not in facts


def test_checked_orders_require_actual_file_in_addition_to_delegated_write(owner, tmp_path):
    marker, folder = VOCABULARY.one("checked_file"), VOCABULARY.one("review_folder")
    order = "1234567890123456"
    child = {
        "kind": "child.execution",
        "harness": "helper",
        "records": _write("saved", f"{folder}/{marker}-2026.md", order),
    }
    facts = owner._facts("s1-qiansanji", [Turn("hello", Execution([child]))], None)
    assert "checked_order_files" not in facts or facts["checked_orders_state"]["has_required_headers"] is False
    owner.workdirs["s1-qiansanji"] = {"workdir": tmp_path}
    path = tmp_path / folder / f"{marker}-2026.md"
    path.parent.mkdir()
    path.write_text(order)
    facts = owner._facts("s1-qiansanji", [Turn("hello", Execution([child]))], None)
    assert facts["checked_order_files"][0]["orders"] == [order]
    assert facts["checked_orders_state"]["has_required_headers"] is False


def test_missing_final_page_and_duplicate_basenames_remain_distinct(tmp_path):
    from experimental.simulation.cases.studio_annual_review.owner import page_facts

    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    paths = [first / "review.html", second / "review.html"]
    paths[0].write_text("<h1>Old</h1>")
    paths[1].write_text("<h1>New</h1>")
    facts = page_facts([Turn("request", Execution([], tuple(map(str, paths))))], None, VOCABULARY)
    assert len(facts["delivery_versions"]) == 2
    assert facts["page_text"].strip() == "New"
    paths[-1].unlink()
    missing = page_facts([Turn("request", Execution([], tuple(map(str, paths))))], None, VOCABULARY)
    assert "unavailable" in missing["final_page_observation"] and "page_measures" not in missing


def test_checked_order_path_cannot_escape_through_symlink(owner, tmp_path):
    root, outside = tmp_path / "work", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    folder, marker = VOCABULARY.one("review_folder"), VOCABULARY.one("checked_file")
    (root / folder).symlink_to(outside, target_is_directory=True)
    (outside / f"{marker}-2026.md").write_text("1234567890123456")
    owner.workdirs["escaped"] = {"workdir": root}
    facts = owner._facts("escaped", [Turn("request", Execution())], type("Card", (), {"name": "qiansanji"})())
    assert facts["checked_orders_state"]["status"] == "unavailable" and "checked_order_files" not in facts


def test_actual_mobile_render_keeps_tiny_and_wide_layout_evidence(tmp_path):
    from experimental.simulation.cases.studio_annual_review.evidence import CHROMIUM, render

    if CHROMIUM is None:
        pytest.skip("No Chromium")
    regular = render('<html><body><p style="font-size:18px">Revenue 100</p></body></html>')
    broken = render('<html><body style="width:9000px"><p style="font-size:1px">Revenue 100</p></body></html>')
    assert regular["status"] == broken["status"] == "rendered"
    assert not regular["horizontal_scroll"] and broken["horizontal_scroll"]
    assert regular["text_nodes"][0]["font_px"] == 18 and broken["text_nodes"][0]["font_px"] == 1


def test_native_batches_keep_equal_basenames_and_allow_a_replacing_rename(tmp_path):
    from types import SimpleNamespace

    from experimental.harness.raven_adapter.observe import Recorder
    from experimental.harness.raven_adapter.worker import Worker
    from experimental.simulation.cases.studio_annual_review.evidence import deliveries

    work = tmp_path / "work"
    work.mkdir()
    left, right = work / "left", work / "right"
    left.mkdir()
    right.mkdir()
    paths = [left / "review.html", right / "review.html", work / "corrected.html"]
    for index, path in enumerate(paths):
        path.write_text(f"<h1>Page {index}</h1>")
    recorder = Recorder(tmp_path / "employee/observations.jsonl")
    recorder.delivery_roots = (work,)
    for call, group in enumerate((paths[:2], paths[2:]), 1):
        recorder.add(
            "runner.event",
            event_type="ToolEvent",
            event={
                "phase": "complete",
                "tool_call_id": str(call),
                "ok": True,
                "metadata": {"raven_delivery": {"files": [{"path": str(path)} for path in group]}},
            },
        )
    proxy = SimpleNamespace(root=tmp_path, area=tmp_path / "employee", baseline=SimpleNamespace(workdir=work))
    kept = Worker._keep_deliverables(proxy, "one", recorder.rows)
    versions, groups = deliveries([Turn("request", Execution(recorder.rows, kept))])
    assert len(versions) == 3 and [len(group["files"]) for group in groups] == [2, 1]
    assert all(group["verified"] for group in groups)
    assert [file["name"] for file in groups[0]["files"]] == ["review.html", "review.html"]
    assert groups[-1]["files"][0]["name"] == "corrected.html"


@pytest.mark.parametrize("previous_day,expected_repeats", [(10, 0), (9, 1)])
def test_repeat_requires_an_earlier_calendar_day(previous_day, expected_repeats):
    from datetime import datetime
    from types import SimpleNamespace

    from experimental.simulation.cases.studio_annual_review.ledger import PACKAGES, Ledger, Order

    ledger = Ledger.__new__(Ledger)
    ledger.year = 2026
    ledger.orders = []
    ledger.errors, ledger.duplicates, ledger.zero, ledger.problems = [], [], [], []
    ledger.linked = {}
    ledger.prices = SimpleNamespace(of=lambda package, day: 100)
    for index, (day, hour) in enumerate(((previous_day, 9), (10, 15)), 1):
        at = datetime(2026, 4, day, hour)
        order = Order(str(index), "wechat", PACKAGES[0], at, at, ("139", "0000"), True)
        order.amount = 100
        ledger.orders.append(order)
    measured = ledger.figures(("2026-04", "2026-04"))
    assert measured["valid_orders"] == 2 and measured["repurchase_orders"] == expected_repeats
