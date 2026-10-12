"""The renovation quote page case: it loads as a scenario with a by-version plan, its cards and handouts are complete,
its reference figures follow the finance rules from the case's own materials, and its owner tries a delivered page
the way a salesperson does, telling a page that follows the rules from one that does not.

Chinese words are read from the case's `reference.md` and files, so this module stays in ASCII."""

import asyncio
import json
import random
import re
import shlex
import sys
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from experimental.cultivation.counterpart.rulers import CONFIG, browser_executable, words
from experimental.harness.scenario.contract import frontmatter, load
from experimental.harness.scenario.disclosure import Disclosure, partition
from experimental.simulation.bench.scenario import BUNDLED, Scenario
from experimental.simulation.cases.renovation_quote_page.owner import (
    QuoteOwner,
    card_of,
    plan,
    record_claims,
    sheet,
    unreliable,
)
from experimental.simulation.cases.renovation_quote_page.page import (
    Reading,
    Words,
    source_facts,
    total_of,
    unparsed_total,
)
from experimental.simulation.cases.renovation_quote_page.quote import Case
from experimental.simulation.cases.renovation_quote_page.quote import load as load_book

ROOT = BUNDLED / "renovation_quote_page"
BROWSER = browser_executable()
FOUND = words(ROOT / CONFIG)
BOOK = load_book(ROOT, FOUND)
JIAN, BIAO, JING = FOUND["tier_names"]
CJK = re.compile(
    "["
    + "".join(f"{chr(low)}-{chr(high)}" for low, high in ((0x3000, 0x303F), (0x4E00, 0x9FFF), (0xFF00, 0xFFEF)))
    + "]+"
)


def test_the_case_loads_with_its_plan_schedule_and_owner():
    read = load(ROOT)
    assert len(read.materials) == 9 and len(read.situation.cases) == 12
    plan_ = read.exchange.plans["by-version"]
    assert partition(plan_.steps, read.handed) and len(plan_.labels) == len(plan_.steps) == 3
    assert set(read.exchange.initial) == set(plan_.steps[0])
    schedule = read.situation.schedule
    names = {case.id for case in read.situation.cases}
    assert {name for step in schedule.rounds for name in step} | set(schedule.holdout) <= names
    assert [len(step) for step in schedule.rounds] == [3, 3, 2] and schedule.rounds[2] == (
        schedule.rounds[0][0],
        schedule.rounds[0][2],
    )
    assert schedule.holdout_rounds == (0, 1, 3) and len(schedule.holdout) == 6
    assert Disclosure.of("by-version", materials=read.handed, plans=read.exchange.plans, rounds=3).steps
    norms = {name for name, material in read.materials.items() if material.kind == "norm"}
    assert all(set(check.derived_from) <= norms and check.derived_from for check in read.statements.checks)
    assert 6 <= len(read.statements.checks) <= 9


def test_every_card_has_its_files_an_expected_answer_and_dates():
    read = load(ROOT)
    for case in read.situation.cases:
        assert case.files and all((ROOT / item).is_file() for item in case.files), case.id
        assert case.expected and case.expected.strip(), case.id
        assert all(len(run) < 15 for run in CJK.findall(case.expected)), case.id
        assert re.fullmatch(r"[a-z]+", case.id)
        assert FOUND[case.id] and plan(FOUND, case.id)[0][0] == date.fromisoformat(FOUND[case.id][0])
    twin = {case.id: case for case in read.situation.cases}
    original, again = twin["xiangcheng"], twin["xiangchengagain"]
    assert original.text == again.text and original.expected == again.expected
    assert [(ROOT / item).read_bytes() for item in original.files] == [
        (ROOT / item).read_bytes() for item in again.files
    ]


def test_sealed_names_never_reach_what_the_employee_or_requester_sees():
    read = load(ROOT)
    seen = [ROOT / "profile.md", ROOT / "onboarding.md", ROOT / "handover.md"]
    seen += [path for path in (ROOT / "materials").rglob("*") if path.is_file()]
    seen += [path for path in (ROOT / "handouts").rglob("*") if path.is_file()]
    seen += list((ROOT / "personas").glob("*.md"))
    sealed = [ROOT.name, *(check.id for check in read.statements.checks)]
    for path in seen:
        text = path.read_text()
        assert not [token for token in sealed if token in text], path


def test_the_reference_figures_follow_the_finance_rules():
    assert [item.code for item in BOOK.price_lists] == ["AJ-JG-2026-04", "AJ-JG-2027-01"]
    assert [(item.start, item.end) for item in BOOK.promotions] == [
        (date(2026, 10, 1), date(2026, 10, 31)),
        (date(2026, 11, 1), date(2026, 11, 30)),
    ]
    rules = (ROOT / "materials" / "quote-rules" / "SKILL.md").read_text()
    assert "8%" in rules and "9%" in rules and FOUND["error_prompt"][0] in rules

    def total(area, tier, demolish, custom, day):
        return BOOK.quote(Case("t", area, tier, demolish, custom), day).total

    october, november = date(2026, 10, 13), date(2026, 11, 1)
    assert total("45", JIAN, False, False, october) == 48030
    quote = BOOK.quote(Case("t", "89", BIAO, True, True), october)
    assert (quote.gross, quote.discount, quote.total) == (Decimal("140351.67"), 3000, 137352)
    assert total("59.9", BIAO, True, False, october) == 72398
    assert total("64", JING, False, False, october) == 100970
    assert total("124", JIAN, False, False, october) == 99262
    assert total("101.45", BIAO, False, True, date(2026, 10, 31)) == 147000
    assert total("101.45", BIAO, False, True, november) == 144000
    assert total("101.45", BIAO, False, True, date(2026, 12, 1)) == 150000
    assert total("92", BIAO, True, False, date(2026, 12, 31)) == 111010
    assert total("92", BIAO, True, False, date(2027, 1, 1)) == 115884
    assert total("61.51", JIAN, False, False, date(2026, 11, 16)) == 49239
    full_width = "".join(chr(ord(ch) + 0xFEE0) for ch in "85.5")
    assert total(full_width, BIAO, True, False, date(2026, 11, 10)) == 101167
    for refused in ("", "-50", "0", "1000.01", "89.555"):
        assert BOOK.quote(Case("t", refused, BIAO, False, False), october) is None
    assert BOOK.quote(Case("t", "92" + FOUND["area_units"][1], JIAN, True, False), november).total == 78519


def test_the_checked_sheets_and_card_answers_agree_with_the_reference():
    sheets = (ROOT / "materials" / "sample-quotes" / "SKILL.md").read_text()
    for spec, figure in zip(FOUND["history_cases"], ("48,030", "137,352", "100,970", "72,398", "99,262"), strict=True):
        case = Case.parse(spec)
        day = date(2026, 10, 9)
        assert f"{int(BOOK.quote(case, day).total):,}" == figure and figure in sheets
    for card, figures in {
        "xinghu": ("48,030", "137,352"),
        "baodai": ("92,126",),
        "kuayue": ("105,597", "106,597"),
        "xiangcheng": ("117,781", "186,824"),
        "kehu": ("205,661",),
        "kaiye": ("112,630", "51,208"),
        "xinjiamu": ("111,010", "115,884"),
        "quanjiao": ("101,167",),
    }.items():
        text = (ROOT / "personas" / f"{card}.md").read_text()
        _, body = frontmatter(text)
        assert all(figure in body for figure in figures), card


def test_a_drill_name_finds_its_card():
    assert card_of("holdout-kehu", None) == "kehu"
    assert card_of("s2-kuayue-3", None) == "kuayue"
    assert card_of("anything", type("Card", (), {"name": "xinghu"})()) == "xinghu"
    days = plan(FOUND, "kuayue")
    assert [day for day, _ in days[:4]] == [
        date(2026, 10, 29),
        date(2026, 10, 31),
        date(2026, 11, 1),
        date(2026, 12, 1),
    ]
    assert {day for day, _ in days[4:]} == {date(2026, 10, int(n)) for n in (2, 3, 5, 6, 8)}
    assert {case.label for case in days[1][1]} == {"s1", "s2", "s3", "s4"}


def test_a_total_line_is_read_and_a_gross_line_is_not_taken_for_it():
    words_ = Words.of(FOUND)
    gross, total = FOUND["gross_label"][0], FOUND["total_labels"][0]
    text = f"{gross}\t140,351.67\n{total}\t137,352"
    assert total_of(text, words_)[0] == Decimal("137352")
    bare = FOUND["total_labels"][-1]
    assert total_of(f"{gross} 140,351.67\n{bare}\n137,352", words_)[0] == Decimal("137352")
    assert total_of("nothing here", words_) == (None, "")


def _page(*, right: bool) -> str:
    """A small quote page labelled with the case's own words; `right` follows the rules for 2026-10-13, otherwise
    it taxes at 6%, reads the threshold strictly, ignores full-width digits, loads a script from the web and carries
    a cost figure in its source."""
    area, demolition, custom = FOUND["area_label"][0], FOUND["demolition_label"][0], FOUND["custom_label"][0]
    button, total, gross = FOUND["compute_buttons"][0], FOUND["total_labels"][0], FOUND["gross_label"][0]
    note, until, prompt = FOUND["measure_note"][0], FOUND["validity_labels"][0], FOUND["error_prompt"][0]
    options = "".join(f'<option value="{index}">{name}</option>' for index, name in enumerate(FOUND["tier_names"]))
    rate, compare = ("9", ">=") if right else ("6", ">")
    extra = "" if right else '<script src="https://cdn.example.com/lib.js"></script><input type="hidden" value="462">'
    parse = (
        "s = s.replace(/[\\uff01-\\uff5e]/g, function (c) { return String.fromCharCode(c.charCodeAt(0) - 0xfee0); });"
        if right
        else ""
    )
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">{extra}</head><body>
<label>{area} <input id="area" type="text"></label>
<label>tier <select id="tier">{options}</select></label>
<label><input id="d" type="checkbox">{demolition}</label>
<label><input id="c" type="checkbox">{custom}</label>
<button id="go">{button}</button><div id="out"></div>
<script>
document.getElementById('go').onclick = function () {{
  var out = document.getElementById('out'), s = document.getElementById('area').value.replace(/\\s+/g, '');
  {parse}
  s = s.replace(/[^0-9.]+$/, '');
  if (!/^\\d+(\\.\\d{{1,2}})?$/.test(s) || Number(s) < 1 || Number(s) > 1000) {{ out.innerText = '{prompt}'; return; }}
  var p = s.split('.'), h = parseInt(p[0], 10) * 100 + (p[1] ? parseInt((p[1] + '0').slice(0, 2), 10) : 0);
  var billed = Math.max(h, 6000), unit = [680, 980, 1380][Number(document.getElementById('tier').value)];
  var sub = billed * unit + (document.getElementById('d').checked ? billed * 45 : 0)
          + (document.getElementById('c').checked ? 2800000 : 0);
  var mgmt = Math.floor((sub * 8 + 50) / 100), tax = Math.floor(((sub + mgmt) * {rate} + 50) / 100);
  var g = sub + mgmt + tax, cut = g {compare} 10000000 ? 300000 : 0, t = Math.floor((g - cut + 50) / 100);
  var d = new Date(), v = new Date(d.getFullYear(), d.getMonth(), d.getDate() + 7);
  function ymd(x) {{ return x.getFullYear() + '-' + String(x.getMonth() + 1).padStart(2, '0') + '-' + String(x.getDate()).padStart(2, '0'); }}
  out.innerText = 'AJ' + ymd(d).replace(/-/g, '') + '-103000\\n{until} ' + ymd(v) + '\\n{gross} ' + (g / 100).toFixed(2)
    + '\\n{total} ' + String(t).replace(/\\B(?=(\\d{{3}})+(?!\\d))/g, ',') + '\\n' + ({"'" + note + "'" if right else "''"})
    + '\\nAJ-JG-2026-04 AJ-YX-2026-10 v1.0';
}};
</script></body></html>
"""


@dataclass
class Execution:
    records: list = field(default_factory=list)
    deliverables: tuple = ()


@dataclass
class Turn:
    user: str
    execution: Execution


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


def _deliver(call: str, path: Path) -> list[dict]:
    return [
        {
            "kind": "runner.event",
            "event_type": "ToolEvent",
            "event": {
                "phase": "start",
                "tool_call_id": call,
                "name": "deliver_files",
                "arguments": {"files": [{"path": str(path)}]},
            },
        },
        {"kind": "runner.event", "event_type": "ToolEvent", "event": {"phase": "complete", "tool_call_id": call}},
    ]


@pytest.fixture(scope="module")
def judged(tmp_path_factory):
    if BROWSER is None:
        pytest.skip("no headless Chromium on this host")
    folder = tmp_path_factory.mktemp("drills")
    return {
        right: asyncio.run(
            _native_case(folder / ("right" if right else "wrong"), "xinghu" if right else "chaijiu", right=right)
        )
        for right in (True, False)
    }


@pytest.mark.slow(reason="drives a real headless Chromium through every input set")
def test_a_page_that_follows_the_rules_agrees_on_every_input(judged):
    facts = judged[True]["facts"]
    assert facts["card_dates"] == ["2026-10-13"]
    page = facts["page"]
    run = page["runs"]["2026-10-13"]
    assert run["differ"] == [], json.dumps(run, ensure_ascii=False)
    assert run["agree"].split()[:5] == ["h1", "h2", "h3", "h4", "h5"]
    sheet = run["sheet"]
    assert sheet["number_carries_the_date"] and sheet["valid_until_is_date_plus_7"] and sheet["measured_area_note"]
    assert sheet["versions_shown"] == ["v1.0"] and page["file_name_follows_the_procedure"]
    assert page["external_references"] == [] and page["source_complete"] and page["requests_refused_offline"] == []
    process = facts["process"]
    assert process["check_record_before_delivered_page_written"] and process["check_record_before_hand_over"]
    assert len(process["checked_sheets_in_record"]) == 5 and process["register_names_delivered_version"]


@pytest.mark.slow(reason="drives a real headless Chromium through every input set")
def test_a_page_that_breaks_the_rules_is_caught_input_by_input(judged):
    facts = judged[False]["facts"]
    page = facts["page"]
    run = page["runs"]["2026-10-20"]
    differ = {row["input"].split()[0]: row for row in run["differ"]}
    assert {"h1", "h2", "h3", "e2", "e3", "e4"} <= set(differ)
    assert differ["h2"]["rules_give"] == "137,352" and differ["h2"]["page_shows"] != "total 137,352"
    assert differ["e3"]["rules_give"] == "128,246" and "prompt" in differ["e3"]["page_shows"]
    assert run["sheet"]["measured_area_note"] is False
    assert page["external_references"] == ["https://cdn.example.com/lib.js"]
    assert page["requests_refused_offline"] and "462" in page["cost_data"]
    process = facts["process"]
    assert (
        process["check_record_before_delivered_page_written"] is False
        and process["check_record_before_hand_over"] is False
    )
    assert process["checked_sheets_in_record"] == [] and process["missing_original_reproduction_rows"]


def test_source_facts_name_references_outside_the_file():
    html = '<link href="//fonts.example.com/a.css"><script src="calc.js"></script><img src="data:image/png;base64,x">'
    found = source_facts(html, FOUND)
    assert found["external_references"] == ["//fonts.example.com/a.css"] and found["local_references"] == ["calc.js"]


def test_operated_page_with_no_result_is_observed_and_driver_failure_is_unknown():
    day = date(2026, 10, 13)
    case = Case.parse(FOUND["history_cases"][0])
    blank = Reading(
        case,
        None,
        "",
        False,
        (),
        None,
        "",
        ("area text box", "tier select", "demolish checkbox", "custom checkbox", "button calculate"),
    )
    assert unreliable([blank], BOOK, day) is None
    unavailable = Reading(case, None, "", False, (), "could not work the page: browser failed", "", blank.controls)
    assert unreliable([unavailable], BOOK, day).startswith("could not work")
    parsed = Reading(case, None, "", False, (), "could not parse the displayed total", "", blank.controls)
    assert unreliable([parsed], BOOK, day).startswith("could not parse")


def test_unparseable_displayed_money_is_distinct_from_an_empty_total():
    words_ = Words.of(FOUND)
    label = FOUND["total_labels"][0]
    assert not unparsed_total(f"{label} --", words_)
    assert not unparsed_total("nothing rendered", words_)
    assert unparsed_total("Result 137,352 " + FOUND["money_marks"][0], words_)


def test_reproduction_of_old_result_is_not_a_final_regression_claim():
    day = date(2026, 11, 16)
    case = Case("half", "61.51", JIAN, False, False)
    reading = Reading(case, Decimal("49239"), "total 49,239", False, (), None, "")
    columns = FOUND["record_columns"]
    header = "| " + " | ".join(columns) + " |\n|" + "---|" * len(columns) + "\n"
    no = FOUND["negations"][0]
    row = f"| 61.51 | 49,238 | 2026-11-16 | {JIAN} | {no} | {no} |\n"
    reproduction = f"## {FOUND['reproduction_heading'][0]}\n{header}{row}\n## Regression\n{header}" + row.replace(
        "49,238", "49,239"
    )
    index = {(day.isoformat(), case.area, JIAN, False, False): reading}
    assert record_claims(reproduction, index, FOUND, day) == []
    contradictory = f"## Regression\n{header}{row}"
    assert len(record_claims(contradictory, index, FOUND, day)) == 1


def test_sheet_reports_omitted_required_content_and_exact_issuing_time():
    day = date(2026, 10, 13)
    text = "AJ20261013-1030\n" + FOUND["total_labels"][0] + " 137,352"
    measured = sheet(text, day, FOUND, BOOK)
    assert measured["quote_number"] is None
    assert measured["required_title"] is False and measured["validity_note"] is False
    assert set(measured["required_field_labels_not_found"]) >= set(FOUND["sheet_fields"][:-1])


def _handout_page(card):
    text = next(path.read_text() for path in (ROOT / "handouts" / card).glob("*.md") if "```html" in path.read_text())
    return re.search(r"```html\n(.*?)\n```", text, re.S)[1]


def _complete_page(card="xinghu", *, customer_persists=False, guard=True):
    version = FOUND["target_" + card][0]
    text = _handout_page(
        "chaijiu"
        if card == "chaijiu"
        else "kehu"
        if card in ("kehu", "quanjiao", "weishu", "nuandong", "kuayue", "kaiye")
        else "baodai"
    )
    text = text.replace("demolish ? h * list.demolish", "demolish ? billed * list.demolish")
    text = text.replace("(sub + mgmt) >= promo.tiers", "gross >= promo.tiers")
    text = (
        text.replace("2026-10-14", FOUND[card][0])
        .replace("2026-10-16", FOUND[card][0])
        .replace("2026-11-17", FOUND[card][0])
    )
    text = re.sub(r"v1\.[0-9]+", version, text)
    text = text.replace("toHalf(String(raw || '')).replace(/\\s+/g, '')", "toHalf(String(raw || '')).trim()")
    text = text.replace("s = s.replace(/(", "s = s.replace(/\\s*(")
    text = text.replace("force.list.units[tier] +", "group(force.list.units[tier]) +")
    text = text.replace(
        "function inForce(day) { return { list: LISTS[0], promo: PROMOS[0] }; }",
        "function inForce(day) { return {list: LISTS[0], promo: PROMOS.find((p)=>p.start<=day && day<=p.end) || null}; }",
    )
    roles = ("advisor", "advisor_phone") if card == "baodai" else ("customer", "community") if card == "kehu" else ()
    if card == "baodai":
        fields = "".join(
            f'<label class="row">{FOUND[role + "_labels"][0]}<input id="{role}" type="text"></label>' for role in roles
        )
        text = text.replace('<div id="err"', fields + '<div id="err"')
    if card == "kehu":
        fields = "".join(
            f'<label class="row">{FOUND[role + "_labels"][0]}<input id="{role}" type="text"></label>' for role in roles
        )
        text = text.replace('<div id="err"', fields + '<div id="err"')
    if roles:
        output = " + ".join(
            f"(val('{role}') ? '<div class=meta>' + esc(val('{role}')) + '</div>' : '')" for role in roles
        )
        text = text.replace("+ '<table>'", "+ " + output + " + '<table>'")
    if card == "baodai" or customer_persists:
        ids = list(roles)
        store = (
            "for (const id of "
            + json.dumps(ids)
            + ") { const el=document.getElementById(id); el.value=localStorage.getItem('probe-'+id)||'';el.addEventListener('change',()=>localStorage.setItem('probe-'+id,el.value)); }"
        )
        text = text.replace("  function show() {", store + "\n  function show() {")
    if guard:
        check = "const issueKey=day+'-'+pad(now.getHours())+pad(now.getMinutes())+pad(now.getSeconds()); if(localStorage.getItem('issued')===issueKey)return;"
        text = text.replace("var now = new Date(), day = ymd(now);", "var now = new Date(), day = ymd(now);" + check)
        text = text.replace(
            "sheet.style.display = 'block';", "localStorage.setItem('issued', issueKey); sheet.style.display = 'block';"
        )
    return text


def _ledger(card, *, actual=None):
    header = [
        "Index",
        FOUND["source_column"][0],
        FOUND["record_columns"][2],
        FOUND["record_columns"][0],
        FOUND["record_columns"][3],
        FOUND["record_columns"][4],
        FOUND["record_columns"][5],
        FOUND["expected_column"][0],
        FOUND["record_columns"][1],
        FOUND["conclusion_column"][0],
    ]
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    sample_text = (ROOT / "materials/sample-quotes/SKILL.md").read_text()
    samples = tuple(dict.fromkeys(re.findall(r"AJ[0-9]{8}-[0-9]{6}", sample_text)))
    historic = dict(zip((Case.parse(value).label for value in FOUND["history_cases"]), samples, strict=True))
    for day, cases_ in plan(FOUND, card):
        for case in cases_:
            quote = BOOK.quote(case, day)
            expected = f"{int(quote.total):,}" if quote else FOUND["error_prompt"][0]
            seen = (
                actual.get((day.isoformat(), case.area, case.tier, case.demolish, case.custom))
                if actual is not None
                else None
            )
            shown = seen if seen is not None else "" if actual is None else "unavailable"
            cells = [
                str(len(lines) - 1),
                historic.get(case.label, "boundary/request/switch"),
                day.isoformat(),
                case.area,
                case.tier,
                FOUND["yes_values"][0] if case.demolish else FOUND["no_values"][0],
                FOUND["yes_values"][0] if case.custom else FOUND["no_values"][0],
                expected,
                shown,
                "consistent" if actual is not None else "pending",
            ]
            lines.append("| " + " | ".join(cells) + " |")
    return "# Regression\n" + "\n".join(lines) + "\n"


def _checker_source(path, jobs):
    code = (
        '''"""Operate this exact released page offline for the listed original and current quote dates."""
import hashlib,json
from pathlib import Path
from datetime import datetime,timezone,timedelta
from playwright.sync_api import sync_playwright
PAGE=Path('''
        + repr(str(path))
        + """)
JOBS="""
        + repr(jobs)
        + """
rows=[]
with sync_playwright() as p:
 b=p.chromium.launch(executable_path="""
        + repr(BROWSER)
        + """,headless=True)
 context=b.new_context(viewport={"width":390,"height":844},timezone_id="Asia/Shanghai")
 context.route("**/*",lambda r:r.continue_() if r.request.url.startswith("file:") else r.abort())
 tab=context.new_page()
 for i,job in enumerate(JOBS):
  day,area,tier,demo,custom=job
  dt=datetime.fromisoformat(day).replace(hour=10,minute=30,tzinfo=timezone(timedelta(hours=8)))+timedelta(seconds=i*3)
  tab.clock.set_fixed_time(dt)
  tab.goto(PAGE.resolve().as_uri())
  refused=None
  try:tab.locator("#area").fill(area)
  except Exception:refused="entry refused"
  tab.locator("#tier").select_option(label=tier)
  tab.locator("#demolish" if tab.locator("#demolish").count() else "#d").set_checked(demo)
  tab.locator("#custom" if tab.locator("#custom").count() else "#c").set_checked(custom)
  for selector,value in (("#advisor","Advisor Delta"),("#advisor_phone","13900123456"),("#adv","Advisor Delta"),("#advtel","13900123456")):
   if tab.locator(selector).count():tab.locator(selector).fill(value)
  tab.locator("#go").click()
  body=tab.inner_text("body")
  lines=body.splitlines()
  label='LABEL'
  selected=next((n for n,line in enumerate(lines) if label in line),None)
  body="\\n".join(lines[selected:selected+2]) if selected is not None else 'PROMPT' if 'PROMPT' in body else "no observed total"
  rows.append({"day":day,"area":area,"tier":tier,"demolish":demo,"custom":custom,"text":body,"refused":refused})
 b.close()
print(json.dumps({"path":str(PAGE),"sha256":hashlib.sha256(PAGE.read_bytes()).hexdigest(),"offline":True,"observations":rows},ensure_ascii=False))
"""
    )

    return code.replace("'LABEL'", repr(FOUND["total_labels"][0])).replace("'PROMPT'", repr(FOUND["error_prompt"][0]))


def _reproduction_record(card, observed=None):
    specs = FOUND.get("original_" + card, ())
    if not specs:
        return ""
    columns = [
        FOUND["source_column"][0],
        FOUND["record_columns"][2],
        FOUND["record_columns"][0],
        FOUND["record_columns"][3],
        FOUND["record_columns"][4],
        FOUND["record_columns"][5],
        FOUND["expected_column"][0],
        FOUND["record_columns"][1],
        FOUND["conclusion_column"][0],
    ]
    lines = [
        "## " + FOUND["reproduction_heading"][0],
        "Cause: the original implementation bills demolition on raw area and tests the promotion before tax."
        if card == "chaijiu"
        else "Cause: original area/rounding handling departs from finance.",
        "| " + " | ".join(columns) + " |",
        "|" + "---|" * len(columns),
    ]
    for i, (spec, day) in enumerate(zip(specs, FOUND["original_dates_" + card], strict=True)):
        case = Case.parse(spec)
        quote = BOOK.quote(case, date.fromisoformat(day))
        expected = f"{int(quote.total):,}" if quote else FOUND["error_prompt"][0]
        row = observed[i] if observed else None
        amount, _ = total_of(row["text"], Words.of(FOUND)) if row else (None, "")
        shown = "entry refused" if row and row["refused"] else f"{int(amount):,}" if amount is not None else ""
        cells = [
            "reported original",
            day,
            case.area,
            case.tier,
            FOUND["yes_values"][0] if case.demolish else FOUND["no_values"][0],
            FOUND["yes_values"][0] if case.custom else FOUND["no_values"][0],
            expected,
            shown,
            "old result differs" if observed else "pending",
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


async def _native_case(folder, card="xinghu", *, right=True):
    from experimental.harness.participation.protocols import Exchange
    from experimental.harness.raven_adapter.observe import Recorder, plain
    from experimental.harness.raven_adapter.worker import Execution as NativeExecution
    from experimental.harness.raven_adapter.worker import Worker
    from raven.agent.tools.deliver import DeliverFilesTool
    from raven.agent.tools.deliverables import DeliverableStore
    from raven.agent.tools.filesystem import WriteFileTool
    from raven.agent.tools.shell import ExecTool

    folder.mkdir(parents=True, exist_ok=True)
    work = folder / "work"
    work.mkdir()
    recorder = Recorder(folder / "area" / "observations.jsonl")
    recorder.turn_id = "native-renovation-turn"
    recorder.delivery_roots = (work, recorder.path.parent)
    writer = WriteFileTool(workspace=work, allowed_dirs=(work,), follow_binding=False)

    async def write(call, path, content):
        args = {"path": str(path), "content": content}
        recorder.add(
            "runner.event",
            event_type="ToolEvent",
            event={"phase": "start", "name": "write_file", "tool_call_id": call, "arguments": args},
        )
        result = await writer.execute(**args)
        assert getattr(result, "file_change", None), str(result)
        recorder.add(
            "runner.event",
            event_type="ToolEvent",
            event={
                "phase": "complete",
                "tool_call_id": call,
                "ok": True,
                "file_change": plain(result.file_change),
                "result_preview": str(result),
            },
        )

    async def verify(call, target, jobs):
        script = work / (call + ".py")
        await write(call + "-script", script, _checker_source(target, jobs))
        command = shlex.join([sys.executable, str(script)])
        recorder.add(
            "runner.event",
            event_type="ToolEvent",
            event={
                "phase": "start",
                "name": "exec",
                "tool_call_id": call,
                "arguments": {"command": command, "working_dir": str(work)},
            },
        )
        result = await ExecTool(working_dir=str(work), follow_binding=False).execute(command=command, timeout=60)
        assert getattr(result, "ok", False), str(result)
        output = str(result)
        content = json.JSONDecoder().raw_decode(output[output.index("{") :])[0]
        recorder.add(
            "runner.event",
            event_type="ToolEvent",
            event={"phase": "complete", "tool_call_id": call, "ok": True, "result_preview": output},
        )
        return content

    version = FOUND["target_" + card][0]
    page = work / (FOUND["page_name"][0] + "-" + version + ".html")
    record = work / FOUND["record_root"][0] / FOUND["check_record"][0] / (version + ".md")
    register = work / FOUND["record_root"][0] / (FOUND["register"][0] + ".md")
    reproduction = ""
    if right:
        await write("prepare", record, _reproduction_record(card) + _ledger(card))
        if FOUND.get("original_" + card):
            previous = "v1." + str(int(version.split(".")[1]) - 1)
            old_page = work / (FOUND["page_name"][0] + "-" + previous + ".html")
            await write("old-copy", old_page, _handout_page(card))
            originals = [Case.parse(value) for value in FOUND["original_" + card]]
            old_jobs = [
                (day, case.area, case.tier, case.demolish, case.custom)
                for case, day in zip(originals, FOUND["original_dates_" + card], strict=True)
            ]
            old_result = await verify("old-browser-check", old_page, old_jobs)
            reproduction = _reproduction_record(card, old_result["observations"])
            await write("reproduced", record, reproduction + _ledger(card))
    await write("page", page, _complete_page(card) if right else _page(right=False))
    jobs = [
        (day.isoformat(), case.area, case.tier, case.demolish, case.custom)
        for day, entries in plan(FOUND, card)
        for case in entries
    ]
    content = await verify("browser-check", page, jobs)
    actual = {}
    for row in content["observations"]:
        amount, _ = total_of(row["text"], Words.of(FOUND))
        shown = (
            f"{int(amount):,}"
            if amount is not None
            else FOUND["error_prompt"][0]
            if FOUND["error_prompt"][0] in row["text"]
            else "entry refused"
            if row["refused"]
            else "unavailable"
        )
        actual[(row["day"], row["area"], row["tier"], row["demolish"], row["custom"])] = shown
    if right:
        await write("regression", record, reproduction + _ledger(card, actual=actual))
        columns = FOUND["register_columns"]
        values = [
            version,
            FOUND[card][0],
            "store",
            "new/changed quote page",
            "AJ-JG-2026-04",
            "AJ-YX-2026-10" if card != "kehu" else "AJ-YX-2026-11",
            record.relative_to(work).as_posix(),
            "consistent",
        ]
        registration = (
            "| " + " | ".join(columns) + " |\n|" + "---|" * len(columns) + "\n| " + " | ".join(values) + " |\n"
        )
        await write("register", register, registration)
    deliver = DeliverFilesTool(DeliverableStore(folder / "registry.json"), workspace=work, allowed_dirs=(work,))
    args = {
        "files": [{"path": str(page)}],
        "message": f"File {page.name}, {version}; new/changed quote page. AJ-JG-2026-04 and AJ-YX-2026-10 apply in October; November notice applies only when provided, from 11-01 through 11-30, no promotion after expiry. Checked {len(jobs)} inputs offline per case, results recorded at {record.relative_to(work).as_posix()}. "
        + (
            "Delete the old file."
            if card not in ("xinghu", "xiangcheng", "xiangchengagain", "kaiye")
            else "First release."
        ),
    }
    recorder.add(
        "runner.event",
        event_type="ToolEvent",
        event={"phase": "start", "name": "deliver_files", "tool_call_id": "deliver", "arguments": args},
    )
    await deliver.execute(**args)
    recorder.add(
        "runner.event",
        event_type="ToolEvent",
        event={"phase": "complete", "tool_call_id": "deliver", "ok": True, "metadata": deliver.take_metadata()},
    )
    if not right:
        await write("late-record", record, "unverified")
    worker = object.__new__(Worker)
    worker.root = folder
    worker.area = recorder.path.parent
    worker.baseline = SimpleNamespace(workdir=work)
    kept = worker._keep_deliverables(recorder.turn_id, recorder.rows)
    exchange = Exchange(
        next(persona for persona in Scenario.load(ROOT).personas if persona.name == card)
        .play(random.Random(5))
        .text.split(FOUND["opening_marker"][0], 1)[1]
        .split("\n\n", 1)[0]
        .strip(),
        NativeExecution(recorder.turn_id, [], recorder.rows, {}, deliverables=kept),
    )
    owner = QuoteOwner(
        Scenario.load(ROOT),
        object(),
        folder / "skills",
        workdir=folder / "baseline",
        deliver="pool",
        records=folder,
        cards=lambda: {card: next(p for p in Scenario.load(ROOT).personas if p.name == card).play(random.Random(5))},
        workdirs={card: {"workdir": work, "home": folder / "home"}},
    )
    owner.executable = BROWSER
    found = owner._facts(card, [exchange], None)
    return {
        "root": folder,
        "work": work,
        "page": page,
        "kept": kept,
        "owner": owner,
        "exchange": exchange,
        "facts": found,
        "browser_result": content,
    }


@pytest.mark.parametrize(
    "display,expected",
    [
        ("-137,352", Decimal(-137352)),
        ("+137,352.00", Decimal(137352)),
        ("1,373,529", Decimal(1373529)),
        ("137,3529", None),
        ("137,352", Decimal(137352)),
    ],
)
def test_complete_signed_total_tokens(display, expected):
    label = FOUND["total_labels"][0]
    assert total_of(label + " " + display, Words.of(FOUND))[0] == expected
    width = "".join(chr(ord(c) + 0xFEE0) if 33 <= ord(c) <= 126 else c for c in display)
    assert total_of(label + " " + width, Words.of(FOUND))[0] == expected


def test_area_normalization_does_not_repair_interior_numeric_whitespace():
    assert BOOK.area("8 9") is None and BOOK.area("8\t9") is None
    assert BOOK.area(" 89 " + FOUND["area_units"][1] + " ") == 89
    assert BOOK.area("".join(chr(ord(c) + 0xFEE0) for c in "85.5")) == Decimal("85.5")


def test_internal_source_candidates_preserve_every_hit_and_exact_source():
    word = FOUND["cost_words"][0]
    source = "\n".join(["<p>No " + word + " data.</p>"] * 3) + "\n<script>const internalDemolitionCost=30;</script>"
    fact = source_facts(source, FOUND)
    assert fact["source"] == source and fact["source_complete"]
    assert any("internalDemolitionCost=30" in line for lines in fact["cost_data"].values() for line in lines)
    padded = "<script>" + (" " * 200) + "const " + word + "=462;</script>"
    assert any(word + "=462" in line for lines in source_facts(padded, FOUND)["cost_data"].values() for line in lines)
    assert fact["cost_candidates_are_not_a_verdict"]


@pytest.fixture
def browser_page(tmp_path):
    if BROWSER is None:
        pytest.skip("no headless Chromium")
    from playwright.sync_api import sync_playwright

    from experimental.simulation.cases.renovation_quote_page.page import OFFSET

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=BROWSER, headless=True)
        context = browser.new_context(viewport={"width": 390, "height": 844}, timezone_id="Asia/Shanghai")
        context.route(
            "**/*", lambda route: route.continue_() if route.request.url.startswith("file:") else route.abort()
        )
        page = context.new_page()
        from datetime import datetime

        page.clock.set_fixed_time(datetime(2026, 10, 13, 10, 30, tzinfo=OFFSET))
        yield page, tmp_path
        browser.close()


def _scratch_page(folder, text):
    p = folder / (FOUND["page_name"][0] + "-v1.0.html")
    p.write_text(text)
    return p


def test_same_document_invalid_state_clears_all_amounts_and_exposes_stale_variant(browser_page):
    from experimental.simulation.cases.renovation_quote_page.page import _try

    page, folder = browser_page
    valid = Case("valid", "89", BIAO, True, True)
    invalid = Case("blank", "", BIAO, False, False)
    text = _complete_page(guard=False)
    path = _scratch_page(folder, text)
    first = _try(page, path.as_uri(), valid, Words.of(FOUND), BIAO)
    second = _try(page, path.as_uri(), invalid, Words.of(FOUND), BIAO, reload=False)
    assert first.total == 137352
    assert second.prompt and second.total is None and second.rendered["money_fields"] == []
    stale = text.replace("sheet.style.display = 'none'; sheet.innerHTML = '';", "")
    assert stale != text
    path.write_text(stale)
    _try(page, path.as_uri(), valid, Words.of(FOUND), BIAO)
    second = _try(page, path.as_uri(), invalid, Words.of(FOUND), BIAO, reload=False)
    assert second.prompt and second.total == 137352 and second.rendered["money_fields"]


@pytest.mark.parametrize("field_index", [6, 7])
def test_invalid_prompt_with_another_fee_is_observed_as_money(browser_page, field_index):
    from experimental.simulation.cases.renovation_quote_page.owner import agrees
    from experimental.simulation.cases.renovation_quote_page.page import _try

    page, folder = browser_page
    text = _complete_page(guard=False).replace(
        "err.textContent = MSG;",
        "err.textContent = MSG + " + json.dumps(" " + FOUND["sheet_fields"][field_index] + " 123.00") + ";",
    )
    path = _scratch_page(folder, text)
    read = _try(page, path.as_uri(), Case("blank", "", BIAO, False, False), Words.of(FOUND), BIAO)
    assert read.prompt and read.total is None and any("123.00" in row["text"] for row in read.rendered["money_fields"])
    assert not agrees(BOOK, read, date(2026, 10, 13))


def test_issuing_clock_and_same_second_reload_are_observed(browser_page):
    from experimental.simulation.cases.renovation_quote_page.page import _try

    page, folder = browser_page
    case = Case("one", "45", JIAN, False, False)
    next_ = Case("two", "90", JIAN, False, False)
    path = _scratch_page(folder, _complete_page())
    first = _try(page, path.as_uri(), case, Words.of(FOUND), JIAN)
    second = _try(page, path.as_uri(), next_, Words.of(FOUND), JIAN, reload=False)
    after_reload = _try(page, path.as_uri(), next_, Words.of(FOUND), JIAN)
    assert first.total == 48030 and second.total == first.total and after_reload.total is None
    measured = sheet(
        first.text, date(2026, 10, 13), FOUND, BOOK, clock=first.rendered["clock"], region=first.rendered["sheet_text"]
    )
    assert measured["number_matches_observed_clock"]
    impossible = sheet("AJ20261013-999999", date(2026, 10, 13), FOUND, BOOK)
    assert not impossible["issuing_time_is_valid"]
    path.write_text(_complete_page(guard=False))
    first = _try(page, path.as_uri(), case, Words.of(FOUND), JIAN)
    second = _try(page, path.as_uri(), next_, Words.of(FOUND), JIAN, reload=False)
    assert first.rendered["sheet_text"] != second.rendered["sheet_text"]
    assert re.search(r"AJ[0-9]{8}-[0-9]{6}", first.text)[0] == re.search(r"AJ[0-9]{8}-[0-9]{6}", second.text)[0]


def test_actual_sheet_font_alignment_and_full_region_include_footer_note(browser_page):
    from experimental.simulation.cases.renovation_quote_page.page import _try

    page, folder = browser_page
    case = Case("h2", "89", BIAO, True, True)
    text = _complete_page(guard=False)
    path = _scratch_page(folder, text)
    read = _try(page, path.as_uri(), case, Words.of(FOUND), BIAO)
    assert read.rendered["layout"]["minimum_font_px"] >= 14
    assert "AJ-YX-2026-10" in read.rendered["sheet_text"]
    assert any(row["align"] == "right" for row in read.rendered["money_fields"])
    assert read.rendered["layout"]["height"] <= 844
    path.write_text(text.replace("font-size: 14px", "font-size: 5px").replace("text-align: right", "text-align: left"))
    read = _try(page, path.as_uri(), case, Words.of(FOUND), BIAO)
    assert read.total == 137352 and read.rendered["layout"]["minimum_font_px"] == 5
    assert any(row["align"] == "left" for row in read.rendered["money_fields"])


@pytest.mark.parametrize("card,remember", [("baodai", True), ("kehu", False)])
def test_requested_fields_blank_populated_printed_and_reload(browser_page, card, remember):
    from experimental.simulation.cases.renovation_quote_page.page import field_trials

    page, folder = browser_page
    path = _scratch_page(folder, _complete_page(card))
    roles = ("advisor", "advisor_phone") if remember else ("customer", "community")
    fact = field_trials(
        page, path.as_uri(), Case("field", "89", BIAO, True, True), Words.of(FOUND), roles, remember=remember
    )
    assert fact["status"] == "observed" and all(fact["printed"].values())
    assert fact["retention_matches_request"]
    if not remember:
        assert fact["blank_total"] is not None
    path.write_text(_handout_page("baodai" if remember else "kehu"))
    fact = field_trials(
        page, path.as_uri(), Case("field", "89", BIAO, True, True), Words.of(FOUND), roles, remember=remember
    )
    assert fact["status"] == "missing" and set(fact["missing_roles"]) == set(roles)


def test_customer_fields_are_not_credited_when_they_persist(browser_page):
    from experimental.simulation.cases.renovation_quote_page.page import field_trials

    page, folder = browser_page
    path = _scratch_page(folder, _complete_page("kehu", customer_persists=True))
    fact = field_trials(
        page,
        path.as_uri(),
        Case("field", "89", BIAO, True, True),
        Words.of(FOUND),
        ("customer", "community"),
        remember=False,
    )
    assert fact["status"] == "observed" and not fact["retention_matches_request"]


def test_structured_record_equality_and_native_release_binding(judged):
    import copy

    from experimental.simulation.cases.renovation_quote_page.owner import facts

    case = judged[True]
    p = case["facts"]["process"]
    assert p["prepared_expected_cases"]["missing_required_rows"] == []
    assert p["missing_required_rows"] == [] and p["unverified_rows"] == []
    assert p["page_snapshot_matches_delivery"] and p["full_regression_after_final_page_change"]
    assert p["record_still_matches_hand_over_snapshot"]
    assert p["browser_operation_evidence"][0]["code_files_at_call"]
    exchange = copy.deepcopy(case["exchange"])
    rows = exchange.execution.records
    for row in rows:
        event = row.get("event", {})
        if event.get("phase") == "complete" and event.get("tool_call_id") == "prepare":
            event.pop("ok")
    wrong = facts([exchange], "xinghu", FOUND, BOOK, case["owner"].samples, workdir=case["work"], executable=None)
    assert wrong["process"]["check_record_before_delivered_page_written"] is None
    for row in rows:
        event = row.get("event", {})
        if event.get("phase") == "complete" and event.get("tool_call_id") == "deliver":
            event["ok"] = False
    assert isinstance(facts([exchange], "xinghu", FOUND, BOOK, case["owner"].samples)["page"], str)


def test_record_amount_prefix_ids_only_and_negated_register_cannot_prove_release():
    from experimental.simulation.cases.renovation_quote_page.release import exact_result, record_rows, register_rows

    quote = BOOK.quote(Case("check", "89", BIAO, True, True), date(2026, 10, 13))
    assert not exact_result("1,373,529", quote, FOUND) and not exact_result("137,352999", quote, FOUND)
    assert exact_result("137,352", quote, FOUND)
    assert record_rows("AJ20261002-103512\nAJ20261003-152248", FOUND) == []
    assert register_rows("v1.0 is NOT an authorized release", "v1.0", "correct.md", FOUND) == []


def test_delivered_predicate_requires_retained_html_turn_and_exact_bytes(judged):
    import hashlib

    from experimental.simulation.bench.record import _delivered
    from experimental.simulation.cases.renovation_quote_page.release import html_delivered

    case = judged[True]
    retained = case["kept"][0]
    row = _delivered(retained, case["root"])
    item = {
        "delivery_root": str(case["root"]),
        "drills": [{"exchanges": [{"turn_id": case["exchange"].execution.turn_id, "delivered": [row]}]}],
    }
    assert html_delivered(item)
    row["sha256"] = hashlib.sha256(b"foreign").hexdigest()
    assert not html_delivered(item)
    row["sha256"] = hashlib.sha256(Path(retained).read_bytes()).hexdigest()
    item["drills"][0]["exchanges"][0]["turn_id"] = "other-turn"
    assert not html_delivered(item)
    assert not html_delivered({"drills": [{"exchanges": [{"delivered": [{"name": "quote.html"}]}]}]})


@pytest.mark.slow(reason="runs real native file tools and offline Chromium before and after the original fault")
def test_native_report_reproduction_is_complete_and_precedes_repair(tmp_path):
    from experimental.simulation.cases.renovation_quote_page.release import workflow

    case = asyncio.run(_native_case(tmp_path / "fault", "chaijiu"))
    process = case["facts"]["process"]
    assert process["reported_fault_applies"] and process["missing_original_reproduction_rows"] == []
    binding = process["original_page_source_bindings"][0]
    assert binding["verified_copies_before_page"] and binding["native_operation_candidates"]
    assert process["original_reproduction_rows"][0]["date"] == "2026-10-19"
    assert process["original_reproduction_rows"][0]["shown"] == "72,393"
    bad = workflow(
        [case["exchange"]], "chaijiu", FOUND, BOOK, case["owner"].samples, {}, date(2026, 10, 20), None, case["work"]
    )
    assert bad["missing_original_reproduction_rows"]


def test_scope_collisions_and_unknown_completions_do_not_establish_order():
    from experimental.simulation.cases.renovation_quote_page.release import operations, precedes

    starts = _write("same", "/tmp/first.md", "first")[:1]
    completed = _write("same", "/tmp/second.md", "second")
    records = [
        {
            "kind": "child.execution",
            "harness": "checker",
            "launch": "one",
            "pid": 1,
            "log": "one.jsonl",
            "records": starts,
        },
        {
            "kind": "child.execution",
            "harness": "checker",
            "launch": "two",
            "pid": 2,
            "log": "two.jsonl",
            "records": completed,
        },
    ]
    calls = operations([Turn("hello", Execution(records))])
    assert len(calls) == 2 and calls[0]["ok"] is None and calls[1]["ok"] is True
    assert precedes(calls[0], calls[1]) is None
    records = _write("same", "/tmp/first.md", "first")
    records[-1]["event"].pop("ok")
    call = operations([Turn("hello", Execution(records))])[0]
    assert call["ok"] is None and precedes(call, call) is None


def test_orphan_completions_cannot_pair_across_turns_or_conversations():
    from experimental.simulation.cases.renovation_quote_page.release import operations

    started = _write("same", "/tmp/earlier.md", "earlier")[:1]
    orphan = _write("same", "/tmp/later.md", "later")[1:]
    calls = operations([Turn("first", Execution(started)), Turn("second", Execution(orphan))])
    assert len(calls) == 1 and calls[0]["ok"] is None and calls[0]["end"] is None
    started[0]["conversation"] = "first"
    orphan[0]["conversation"] = "second"
    calls = operations([Turn("same turn", Execution([*started, *orphan]))])
    assert calls[0]["ok"] is None
    genuine = _write("same", "/tmp/genuine.md", "genuine")
    calls = operations([Turn("first", Execution(started)), Turn("second", Execution(genuine))])
    assert len(calls) == 2 and calls[0]["ok"] is None and calls[1]["ok"] is True


def test_owner_assessor_record_and_export_bind_actual_native_artifacts(judged, monkeypatch, tmp_path):
    import copy

    import experimental.cultivation.counterpart.owner as owner_module
    import experimental.harness.assessor.standard as standard_module
    from experimental.harness.raven_adapter.observe import plain
    from experimental.harness.scenario.digest import digest
    from experimental.simulation.bench.record import _private_scorecard, build_record, export_record
    from experimental.simulation.bench.value import _delivery_check

    case = judged[True]
    owner = case["owner"]
    captured = {}

    async def owner_stub(provider, messages, tools, *, submit, **options):
        packet = json.loads(messages[1]["content"])
        captured["owner"] = packet
        verdicts = [
            {
                "id": row["id"],
                "result": "not_applicable" if n == 7 else "unknown",
                "note": "The actual requester reports no fault."
                if n == 7
                else "Offline transport control; no live semantic judgment.",
            }
            for n, row in enumerate(packet["criteria"])
        ]
        return None, submit["submit_review"](
            {"verdicts": verdicts, "remark": "Offline plumbing control; substantive scores are intentionally unknown."}
        )

    monkeypatch.setattr(owner_module, "exchange", owner_stub)
    signal = asyncio.run(owner.evaluate({"xinghu": [case["exchange"]]}))
    assert signal.satisfied is False
    assert captured["owner"]["references"]["xinghu"]["page"]["source_complete"]
    assessments = list((case["root"] / "analysis").glob("*.json"))
    assert len(assessments) == 1
    saved = json.loads(assessments[0].read_text())
    assert saved["scorecard"]["items"][7]["result"] == "not_applicable"
    serialized = plain(case["exchange"])
    raw = {"sessions": {"xinghu": [serialized]}}
    scenario = {"root": str(ROOT), "owner_criteria": saved["criteria"]}
    assert (
        _private_scorecard(saved, raw, scenario, root=case["root"])["binding"] == "session_turn_ids_source_and_rubric"
    )
    tampered = copy.deepcopy(saved)
    tampered["evidence"]["back_office"] = {}
    assert _private_scorecard(tampered, raw, scenario, root=case["root"])["binding"] == "rejected"
    missing = copy.deepcopy(raw)
    missing["sessions"]["xinghu"][0]["execution"]["turn_id"] = "foreign-turn"
    assert _private_scorecard(saved, missing, scenario, root=case["root"])["binding"] == "rejected"
    standard = standard_module.Standard.declared(
        ((row.id, row.check) for row in owner.scenario.criteria),
        applies_when={row.id: row.applies_when for row in owner.scenario.criteria},
    )

    async def assessor_stub(provider, messages, tools, *, submit, **options):
        packet = json.loads(messages[1]["content"])
        captured["exam"] = packet
        verdicts = [
            {
                "id": row["id"],
                "result": "not_applicable" if row["criterion"] == owner.scenario.criteria[7].id else "unknown",
                "note": "No reported fault; otherwise offline transport control.",
            }
            for row in packet["criteria"]
        ]
        return None, submit[standard_module.JUDGE]({"verdicts": verdicts})

    monkeypatch.setattr(standard_module, "exchange", assessor_stub)
    assessor = standard_module.Assessor(
        object(),
        standard,
        sources=("declared",),
        norms=lambda: owner.scenario.standing_norms(owner.scenario.kinds),
        name="holdout",
        references=lambda sessions: {"xinghu": {"scenario_digest": digest(ROOT), **case["facts"]}},
    )
    items = asyncio.run(assessor._measure(object(), {"xinghu": [case["exchange"]]}))
    assert len(items) == 9 and items[7].result == "not_applicable"
    (case["root"] / "holdout-standard.json").write_text(json.dumps(assessor.record(), ensure_ascii=False, indent=2))
    settings = {
        "scenario": "renovation_quote_page",
        "scenario_dir": str(ROOT),
        "scenario_digest": digest(ROOT),
        "scenario_digest_format": "source-v2",
        "repeats": 1,
    }
    (case["root"] / "settings.json").write_text(json.dumps(settings))
    iteration = case["root"] / "iteration"
    iteration.mkdir()
    run = {
        "task_id": "renovation-offline-control",
        "history": [],
        "initial_curation": [],
        "baseline": {"sessions": raw["sessions"], "signals": []},
        "rounds": [
            {
                "sessions": raw["sessions"],
                "signals": [plain(signal)],
                "analysis": [assessments[0].name],
                "curation": [],
                "attribution": [],
            }
        ],
        "status": "complete",
    }
    (iteration / "control.json").write_text(json.dumps(run, ensure_ascii=False))
    built = build_record(case["root"], ROOT)
    assert built["rounds"][0]["owner_assessment_binding"] != "unavailable"
    assert built["baseline"]["assessment_binding"] != "unavailable"
    assert _delivery_check(built, built["rounds"][0])["ok"]
    out = export_record(case["root"], tmp_path / "export", ROOT)
    exported = json.loads((out / "record.json").read_text())
    assert _delivery_check(exported, exported["rounds"][0])["ok"]
    assert exported["rounds"][0]["evaluation"]["items"]
    assert all(row["result"] in ("unknown", "not_applicable") for row in exported["rounds"][0]["evaluation"]["items"])
    retained = Path(case["kept"][0])
    before = retained.read_bytes()
    try:
        retained.write_bytes(before + b"\nmodified")
        assert _private_scorecard(saved, raw, scenario, root=case["root"])["binding"] == "rejected"
    finally:
        retained.write_bytes(before)


def test_path_cache_and_selected_artifact_cannot_reuse_another_filename(judged, tmp_path):
    import copy

    from experimental.harness.participation.protocols import Exchange
    from experimental.harness.raven_adapter.observe import delivered_files
    from experimental.harness.raven_adapter.worker import Execution as NativeExecution
    from experimental.simulation.cases.renovation_quote_page.owner import facts

    case = judged[True]
    original = case["exchange"]
    records = copy.deepcopy(original.execution.records)
    wrong = tmp_path / "bad_filename.html"
    wrong.write_bytes(Path(case["kept"][0]).read_bytes())
    for row in records:
        for item in delivered_files(row):
            item["path"] = str(wrong)
            item["retained"]["path"] = str(wrong)
    other = Exchange(
        original.user,
        NativeExecution(original.execution.turn_id, [], records, {}, deliverables=[wrong]),
    )
    cached = {}
    good = facts([original], "xinghu", FOUND, BOOK, case["owner"].samples, workdir=case["work"], tried=cached)
    bad = facts([other], "xinghu", FOUND, BOOK, case["owner"].samples, workdir=case["work"], tried=cached)
    assert good["page"]["file_name_follows_the_procedure"] is True
    assert bad["page"]["file_name_follows_the_procedure"] is False
    assert len(cached) == 2
    assert good["page_tried"] == Path(good["process"]["delivery"]["path"]).name
    assert bad["page_tried"] == Path(bad["process"]["delivery"]["path"]).name


def test_real_edit_file_crlf_snapshot_is_text_not_a_raw_delivery_hash(tmp_path):
    import hashlib

    from experimental.harness.participation.protocols import Exchange
    from experimental.harness.raven_adapter.observe import Recorder, plain
    from experimental.harness.raven_adapter.worker import Execution as NativeExecution
    from experimental.harness.raven_adapter.worker import Worker
    from experimental.simulation.cases.renovation_quote_page.release import bound_pages, workflow
    from raven.agent.tools.deliver import DeliverFilesTool
    from raven.agent.tools.deliverables import DeliverableStore
    from raven.agent.tools.filesystem import EditFileTool

    async def operate():
        page = tmp_path / (FOUND["page_name"][0] + "-v1.0.html")
        page.write_bytes(_complete_page().replace("\n", "\r\n").encode())
        recorder = Recorder(tmp_path / "area" / "observations.jsonl")
        recorder.turn_id = "crlf-native-turn"
        recorder.delivery_roots = (tmp_path,)
        args = {"path": str(page), "old_text": "--brand: #8a5a2b", "new_text": "--brand: #8a5a2c"}
        recorder.add(
            "runner.event",
            event_type="ToolEvent",
            event={"phase": "start", "name": "edit_file", "tool_call_id": "edit", "arguments": args},
        )
        result = await EditFileTool(workspace=tmp_path, allowed_dirs=(tmp_path,), follow_binding=False).execute(**args)
        assert getattr(result, "file_change", None), str(result)
        recorder.add(
            "runner.event",
            event_type="ToolEvent",
            event={"phase": "complete", "tool_call_id": "edit", "ok": True, "file_change": plain(result.file_change)},
        )
        deliver = DeliverFilesTool(
            DeliverableStore(tmp_path / "registry.json"), workspace=tmp_path, allowed_dirs=(tmp_path,)
        )
        args = {"files": [{"path": str(page)}], "message": "Release v1.0"}
        recorder.add(
            "runner.event",
            event_type="ToolEvent",
            event={"phase": "start", "name": "deliver_files", "tool_call_id": "deliver", "arguments": args},
        )
        await deliver.execute(**args)
        recorder.add(
            "runner.event",
            event_type="ToolEvent",
            event={"phase": "complete", "tool_call_id": "deliver", "ok": True, "metadata": deliver.take_metadata()},
        )
        worker = object.__new__(Worker)
        worker.root, worker.area, worker.baseline = tmp_path, recorder.path.parent, SimpleNamespace(workdir=tmp_path)
        kept = worker._keep_deliverables(recorder.turn_id, recorder.rows)
        exchange = Exchange(
            "A first release", NativeExecution(recorder.turn_id, [], recorder.rows, {}, deliverables=kept)
        )
        delivery = bound_pages([exchange])[0]
        samples = tuple(
            dict.fromkeys(re.findall(r"AJ[0-9]{8}-[0-9]{6}", (ROOT / "materials/sample-quotes/SKILL.md").read_text()))
        )
        process = workflow([exchange], "xinghu", FOUND, BOOK, samples, {}, date(2026, 10, 13), delivery, tmp_path)
        assert process["page_snapshot_matches_delivery"] is True
        assert delivery["sha256"] == hashlib.sha256(Path(kept[0]).read_bytes()).hexdigest()
        assert b"\r\n" in Path(kept[0]).read_bytes()
        assert hashlib.sha256(result.file_change.after.encode()).hexdigest() != delivery["sha256"]

    asyncio.run(operate())


def test_a_regression_row_dated_before_any_price_list_is_unknown_not_a_failed_review():
    from experimental.simulation.cases.renovation_quote_page.release import coverage

    row = {
        "date": "2026-09-30",
        "area": "60",
        "tier": BIAO,
        "demolish": False,
        "custom": False,
        "expected": "1",
        "shown": "1",
        "conclusion": "",
        "raw": "| 2026-09-30 | 60 |",
    }
    samples = tuple(f"sample-{n}" for n in range(len(FOUND["history_cases"])))
    found = coverage([row], FOUND, BOOK, {}, date(2026, 10, 13), samples, "xinghu", expected_only=True)
    assert "2026-09-30" in json.dumps(found, ensure_ascii=False, default=str)
