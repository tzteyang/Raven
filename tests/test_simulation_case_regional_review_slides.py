"""The regional review case: its cards, schedule and disclosure plan, the finance tables its owner reads, and the facts
the owner computes from a delivered page's source, its rendering at the projector's size and its versions."""

import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from experimental.cultivation.counterpart.rulers import browser_executable
from experimental.harness.participation.protocols import Exchange, Execution
from experimental.harness.scenario.contract import load
from experimental.harness.scenario.disclosure import partition
from experimental.harness.scenario.sealed import sealed_for
from experimental.simulation.bench.scenario import Scenario
from experimental.simulation.cases.regional_review_slides import owner as case

NAME = "regional_review_slides"
SCENARIO = Scenario.load(NAME)
VOCABULARY = case.Vocabulary.load(SCENARIO.root)
CARDS = case.cards(SCENARIO.root)
BOOKS = {
    "q3": case.book(SCENARIO.text(VOCABULARY.one("quarter_table")), VOCABULARY),
    "oct": case.book(SCENARIO.text(VOCABULARY.one("october_table")), VOCABULARY),
}
# Each test runs under a fresh HOME, where no browser is cached, so the machine's Chromium is found once here.
CHROMIUM = browser_executable()
NOT_RENDERED = {"error": "not rendered in this test"}
STYLE = (
    "<style>body{margin:0;font-family:'Microsoft YaHei',sans-serif;font-size:28px;color:#0A1F44}"
    "li{width:420px}.src{position:absolute;right:56px;bottom:24px;font-size:16px}</style>"
)


def unrendered(path, vocabulary):
    return NOT_RENDERED


def turn(reply, records=(), files=(), number=1):
    rows = [{"kind": "runner.event", "event_type": "Text", "event": {"content": reply}}, *records]
    return Exchange("request", Execution(f"t{number}", [], rows, {}, "a", tuple(str(path) for path in files)))


def wrote(path, text):
    event = {"phase": "complete", "ok": True, "file_change": {"path": str(path), "after": text}}
    return {"kind": "runner.event", "event_type": "ToolEvent", "event": event}


def handouts(card):
    persona = next(persona for persona in SCENARIO.personas if persona.name == card)
    return {path.name: path for path in persona.files}


def han(*codes):
    return "".join(chr(code) for code in codes)


def test_the_case_loads_with_its_cards_schedule_and_by_version_plan():
    read = load(SCENARIO.root)
    cases = {item.id: item for item in read.situation.cases}
    assert len(cases) == 12 and len(read.materials) == 8
    for item in cases.values():
        assert item.expected and item.files and all((read.root / path).is_file() for path in item.files)
        assert item.id in CARDS and CARDS[item.id].region in VOCABULARY.all("regions")
    schedule = read.situation.schedule
    assert {name for step in schedule.rounds for name in step} | set(schedule.holdout) == set(cases)
    assert schedule.rounds[2] == ("quarter", "crowded") and set(schedule.rounds[2]) <= set(schedule.rounds[0])
    assert len(schedule.holdout) == 6 and schedule.holdout_rounds == (0, 1, 3)
    plan = read.exchange.plans["by-version"]
    assert len(plan.steps) == 3 and len(plan.labels) == 3
    assert partition(plan.steps, read.handed) == plan.steps and set(read.exchange.initial) == set(plan.steps[0])
    twin, original = cases["northwestagain"], cases["northwest"]
    assert twin.text == original.text and twin.expected == original.expected
    assert [(read.root / path).read_bytes() for path in twin.files] == [
        (read.root / path).read_bytes() for path in original.files
    ]
    trained = {Path(path).name for name in schedule.rounds[0] + schedule.rounds[1] for path in cases[name].files}
    held = {Path(path).name for name in schedule.holdout for path in cases[name].files}
    assert not trained & held
    for card in CARDS.values():
        if card.base:
            assert case.base_page(card, handouts(card.name)).lstrip().startswith("<!DOCTYPE html>")


def test_a_curators_paraphrase_of_the_rules_meets_no_sealed_window():
    read = load(SCENARIO.root)
    seal = sealed_for(read, "curator")
    for text in (
        "The title must state the completion rate and where the gap or surplus lies.",
        "Every text except the logo and the source line must render at 28px or larger.",
        "When the director relays a comment, change only what it names, then say what changed and that the rest is unchanged.",
        "Tell the director which draft figures were changed to the finance table's figures and why.",
        "For each city below target, give the reason and the month and amount it will be made up in, marked as a forecast.",
        "Deliver one page only; never offer styles to pick from or preview pages.",
    ):
        assert seal.hits(text) == [], text
    pages = [
        (read.root / item).read_text()
        for item in next(item for item in read.situation.cases if item.id == "northeast").files
        if item.endswith(".md") and "html" in (read.root / item).read_text()
    ]
    assert (
        pages and seal.hits("th, td { padding: 6px 28px; text-align: right; border-bottom: 1px solid #D9DEE7; }") == []
    )


def test_the_finance_tables_give_each_card_its_figures_by_issue():
    q3, october = BOOKS["q3"], BOOKS["oct"]
    assert len(q3.regions) == len(october.regions) == len(VOCABULARY.all("regions")) == 8
    assert len(q3.cities) == len(october.cities) == 34 and len(october.revised) == 3 and len(q3.flash) == 4
    east = case.allowed(CARDS["quarter"], BOOKS, VOCABULARY)
    assert {Decimal("2.00"), Decimal("1.84"), Decimal("0.16")} <= east.dec and Decimal("92") in east.pct
    assert ("dec", Decimal("1.83")) in east.stale and ("dec", Decimal("2.10")) in east.stale
    assert east.region_rate == Decimal("92") and [name for name, _ in east.below] == list(
        east.below and [n for n, _ in east.below]
    )
    assert ("pct", Decimal("71")) in {("pct", rate) for _, rate in east.below} and CARDS["quarter"].region not in dict(
        east.below
    )
    first = case.allowed(CARDS["remedy"], BOOKS, VOCABULARY)
    assert Decimal("2.00") in first.dec and Decimal("31") in first.pct and Decimal("2.10") not in first.dec
    assert ("pct", Decimal("30")) in first.stale and ("int", Decimal("1646")) in first.stale
    second = case.allowed(CARDS["stretch"], BOOKS, VOCABULARY)
    assert Decimal("0.45") in second.dec and Decimal("27") in second.pct
    assert ("dec", Decimal("0.42")) in second.stale and ("pct", Decimal("29")) in second.stale
    assert [rate for name, rate in second.below] == [Decimal("83"), Decimal("68")]
    south = case.allowed(CARDS["dense"], BOOKS, VOCABULARY)
    assert Decimal("0.03") in south.dec and Decimal("0.02") not in south.dec
    name, file, last = case.meeting(CARDS["monthly"], VOCABULARY)
    assert file == f"{CARDS['monthly'].region}-{name}.html" and last == "2026-10-31" and " " not in name
    assert case.meeting(CARDS["quarter"], VOCABULARY)[2] == "2026-09-30"


def test_an_october_card_says_its_date_and_is_held_to_the_issue_in_force_that_day():
    year, month, day = VOCABULARY.all("date_words")[:3]
    full = rf"(\d{{4}})\s*{year}\s*(\d{{1,2}})\s*{month}\s*(\d{{1,2}})\s*{day}"
    second_from = date(*map(int, re.search(full, SCENARIO.text(VOCABULARY.one("october_table"))).groups()))
    assert second_from == date(2026, 11, 4)
    opening = han(0x5F00, 0x53E3, 0x8BF4)
    revised = BOOKS["oct"].revised
    played = [persona for persona in SCENARIO.personas if CARDS[persona.name].issue in ("first", "second")]
    checked = []
    for persona in played:
        card = CARDS[persona.name]
        when = date.fromisoformat(re.search(r"card dated (\d{4}-\d{2}-\d{2})", persona.expected).group(1))
        assert card.issue == ("first" if when < second_from else "second"), persona.name
        if card.region not in revised:
            continue
        line = next(line for line in persona.text.splitlines() if line.startswith(opening))
        assert re.search(rf"{when.month}\s*{month}\s*{when.day}\s*{day}", line), persona.name
        (first, second), _ = revised[card.region]
        in_force, replaced = (first, second) if card.issue == "first" else (second, first)
        figures = case.allowed(card, BOOKS, VOCABULARY)
        assert case.yi(in_force) in figures.dec and ("dec", case.yi(replaced)) in figures.stale, persona.name
        checked.append(persona.name)
    assert sorted(checked) == ["monthly", "remedy", "stretch"]


def test_figures_are_read_even_when_a_character_touches_them_and_dates_are_not_figures():
    yi_unit, wan_unit, _ = VOCABULARY.all("units")
    year, month, day = VOCABULARY.all("date_words")[:3]
    forecast = VOCABULARY.one("forecast")
    text = "\n".join(
        [
            f"total1.83{yi_unit} at91.6%",
            f"total 1.84 {yi_unit} at 92%, gap 0.16 {yi_unit}",
            f"Nanjing860{wan_unit} {forecast}11{month}",
            f"2026{year}9{month}30{day}, 1280{case.TIMES}800, Q3, V1.3, 3 points",
            f"Ningbo1,944{wan_unit} and 777",
        ]
    )
    assert [value for _, value, _ in case.figures(text, VOCABULARY)][:2] == [Decimal("1.83"), Decimal("91.6")]
    assert case.tokens(f"total1.84{yi_unit}") == [("dec", Decimal("1.84"))]
    found = case.figure_facts(text, CARDS["quarter"], BOOKS, VOCABULARY)
    assert found["scalar_values_found_in_table"] == 3
    assert [line.split(" in: ")[0] for line in found["corrected_or_replaced_figures"]] == ["1.83", "91.6%", "1,944"]
    assert found["director_figures"] == [
        {"figure": "860", "line": f"Nanjing860{wan_unit} {forecast}11{month}", "forecast_mark": True}
    ]
    assert found["figures_not_in_the_table"] == [f"777 in: Ningbo1,944{wan_unit} and 777"]
    assert case.later_months(f"Nanjing 11 {month}, 2026 {year} 9 {month}", CARDS["quarter"], VOCABULARY) == [11]
    assert case.chars(" ab  12% ,") == 6


def test_the_data_block_and_the_below_target_cities_are_measured_per_city():
    _, wan_unit, _ = VOCABULARY.all("units")
    _, month = VOCABULARY.all("date_words")[:2]
    forecast = VOCABULARY.one("forecast")
    region, cities = (
        CARDS["monthly"].region,
        [name for (owner, name) in BOOKS["oct"].cities if owner == CARDS["monthly"].region],
    )
    tianjin, taiyuan = cities[1], cities[3]
    page = "\n".join(
        [
            f"{region[:2]} 10{month} 92%",
            "0.41 0.38 92% 1.26 30%",
            f"{tianjin} 258{wan_unit}: customer delay",
            f"{forecast} 11{month} 78{wan_unit}, 12{month} 180{wan_unit}",
            f"{taiyuan} 142{wan_unit}, {forecast} 11{month}",
            "1,600 1,670 104% 1,000 742 74% 820 826 101% 680 538 79%",
        ]
    )
    block = case.data_block(page, CARDS["monthly"], BOOKS, VOCABULARY)
    assert block["required"] == 18 and block["scalar_present"] == 18 and block["scalar_missing"] == []
    assert len(block["required_items"]) == 18 and "scope" in block
    short = case.data_block("0.41 0.38 92%", CARDS["monthly"], BOOKS, VOCABULARY)
    assert (
        short["scalar_present"] == 4
        and short["scalar_missing"][0].startswith(region)
        and len(short["scalar_missing"]) == 14
    )
    below = case.below_target(page, CARDS["monthly"], BOOKS, VOCABULARY)
    assert below["region_rate"] == "92%" and [city["name"] for city in below["cities"]] == [tianjin, taiyuan]
    first, second = below["cities"]
    assert first["a_line_names_an_amount"] and not first["a_line_names_a_later_month"]
    assert second["a_line_names_a_later_month"] and second["a_line_has_the_forecast_mark"]
    assert [row["months"] for row in below["recovery_lines"]] == [[11, 12], [11]]
    assert all(row["forecast_mark"] for row in below["recovery_lines"])


def test_the_page_source_shows_fonts_links_colours_decoration_and_motion():
    loud = (
        '<html><head><link href="https://fonts.example.com/a.css" rel="stylesheet"><style>'
        "body{font-family:'Inter',inherit,sans-serif;background:linear-gradient(90deg,#1e1b4b,#7c3aed);color:white}"
        "#bad{color:#0A1F44}h1{animation:rise 1s;filter:blur(1px)}@keyframes rise{from{opacity:0}}"
        "p{text-shadow:0 1px 2px rgba(0,0,0,.4)}.page::before{content:'';background:#F2F4F8}"
        '</style></head><body><section class="slide active"><h1>Q3 review</h1></section>'
        '<svg xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="g"/></defs>'
        '<rect fill="url(#g)"/><rect fill="#0B5FFF"/></svg><a href="#top">up</a></body></html>'
    )
    found = case.source_facts(loud, VOCABULARY)
    assert found["fonts_outside_the_rule"] == ["Inter"] and found["references_outside_the_file"] == [
        "https://fonts.example.com/a.css"
    ]
    assert set(found["colours_outside_the_palette"]) == {"#1E1B4B", "#7C3AED", "#000000"}
    assert found["gradients"] == 2 and found["shadows"] == 1 and found["translucent_colours"] == ["rgba(0,0,0,.4)"]
    assert found["filters"] == 1 and found["pseudo_element_decorations"] == 1
    assert found["motion"] == {"keyframes": 1, "animation": 1} and found["slide_sections"] == 1
    exemplar = case.HTML_BLOCK.search(SCENARIO.text("good-page")).group(1)
    quiet = case.source_facts(exemplar, VOCABULARY)
    assert set(quiet) == {"fonts_declared", "h1", "document_title"}


def test_visible_text_reads_one_block_per_line_whatever_inline_markup_it_holds():
    html = "<div class='a'>done<b>1.13 </b><span>yi</span></div><ul><li><b>Tianjin</b> short <i>by</i> 258</li></ul><p>x<br>y</p>"
    assert case.visible(html).splitlines() == ["done1.13 yi", "Tianjin short by 258", "x", "y"]


@pytest.mark.skipif(CHROMIUM is None, reason="no headless Chromium on this machine")
def test_rendering_measures_scaling_the_source_block_wrapped_lines_and_what_does_not_fit(tmp_path, monkeypatch):
    monkeypatch.setattr(case, "browser_executable", lambda: CHROMIUM)
    width, height = VOCABULARY.projector
    source, year, month, day = VOCABULARY.one("source_mark"), *VOCABULARY.all("date_words")[:3]
    scaled = tmp_path / "scaled.html"
    scaled.write_text(
        '<html><body style="margin:0"><div id="s" style="width:1920px;height:1080px;transform-origin:0 0">'
        '<h1 style="font-size:64px">Title</h1><ul><li style="font-size:42px">first point</li></ul>'
        '<p style="font-size:30px;opacity:0">later slide</p></div><script>const s=document.getElementById("s");'
        's.style.transform="scale("+Math.min(innerWidth/1920,innerHeight/1080)+")"</script></body></html>'
    )
    probed = case.rendered(scaled, VOCABULARY)
    assert "error" not in probed, probed
    facts = case.render_facts(probed, VOCABULARY, floor_in_force=True)
    sizes = {text["text"]: text["px"] for text in probed["texts"]}
    assert sizes["first point"] == pytest.approx(42 * width / 1920, abs=0.3)
    assert facts["hidden_text"] == ["later slide"] and facts["largest_text"]["text"] == "Title"
    assert facts["points"] == [{"text": "first point", "chars": 10}] and facts["size_floor_in_force"] is True
    inline = tmp_path / "inline.html"
    inline.write_text(
        f"<html><head>{STYLE}</head><body><ol><li>Tianjin <b>74%</b>, a customer delayed its acceptance; "
        f"<b>180</b> expected by mid-December</li><li><b>Shijiazhuang</b> 101%</li></ol>"
        f'<div class="src">{source}: finance, until <span>2026 {year} 10 {month} 31 {day}</span></div>'
        "</body></html>"
    )
    probed = case.rendered(inline, VOCABULARY)
    facts = case.render_facts(probed, VOCABULARY, floor_in_force=True)
    assert "overlapping_text" not in facts and "text_below_the_floor" not in facts
    assert facts["source_line"]["px"] == 16 and facts["source_line"]["at_bottom_right"] is True
    assert f"31 {day}" in facts["source_line"]["text"] and facts["smallest_text_px"] == 28
    tall = tmp_path / "tall.html"
    tall.write_text(
        '<html><body style="margin:0;font-family:sans-serif">'
        + "".join(f'<p style="font-size:40px">row {n}</p>' for n in range(14))
        + '<div style="width:300px;overflow:hidden;white-space:nowrap;font-size:40px">'
        + "a very long line that cannot fit in the box</div>"
        + '<div style="position:absolute;left:0;top:0;width:200px;height:60px;background:#0B5FFF"></div>'
        + '<p style="position:absolute;left:10px;top:10px;font-size:40px;margin:0">over</p></body></html>'
    )
    facts = case.render_facts(case.rendered(tall, VOCABULARY), VOCABULARY, floor_in_force=False)
    assert facts["page_scrolls"] is True and facts["content_size"][1] > height
    assert "row 13" in facts["text_outside_the_screen"] and facts["clipped_text"]
    assert facts["overlapping_text"] and facts["decorations"]["empty_coloured_boxes"]


def correction(tmp_path, html, name):
    folder = tmp_path / name.split(".")[0]
    folder.mkdir()
    page = folder / name
    page.write_text(html)
    return page


def test_a_compliant_and_a_violating_correction_of_a_presented_page(tmp_path):
    card = CARDS["archive"]
    base = case.base_page(card, handouts("archive"))
    file = case.meeting(card, VOCABULARY)[1]
    fixed = correction(tmp_path, base.replace(">88%<", ">83%<"), file)
    sheet = tmp_path / VOCABULARY.one("sheet_folder") / f"{Path(file).stem}.md"
    rows = [
        f"| {case.shown(kind, value)} | page | Q3 | {value} | ok |"
        for kind, value, _ in case.figures(case.visible(fixed.read_text()), VOCABULARY)
    ]
    table = "| figure | where | source | value | same |\n|---|---|---|---|---|\n" + "\n".join(rows) + "\n"
    sheet.parent.mkdir()
    sheet.write_text(table)
    good = case.facts(
        [turn("fixed", [wrote(sheet, table)], [fixed])],
        card,
        VOCABULARY,
        BOOKS,
        base=base,
        render=unrendered,
        workdir=tmp_path,
    )
    assert good["file_named_as_expected"] is True and "corrected_or_replaced_figures" not in good["figures"]
    assert "figures_not_in_the_table" not in good["figures"] and good["source_date"] == "2026-09-30"
    assert good["data_block"]["scalar_missing"] == []
    changed = good["against_the_page_handed_over"]
    assert changed["visible_lines_removed"] == ["88%"] and changed["visible_lines_added"] == ["83%"]
    assert changed["style_declarations_changed"] == 0
    assert good["reconciliation_sheet"]["filed"] and not good["reconciliation_sheet"]["page_scalars_absent_from_sheet"]
    assert good["card"]["size_floor_and_recovery_rule_in_force"] is False
    restyled = correction(tmp_path, base.replace("font-size: 24px", "font-size: 32px"), "draft-v2.html")
    bad = case.facts([turn("redone", files=[restyled])], card, VOCABULARY, BOOKS, base=base, render=unrendered)
    assert bad["file_named_as_expected"] is False and bad["reconciliation_sheet"]["status"] == "unavailable"
    assert any(line.startswith("88%") for line in bad["figures"]["corrected_or_replaced_figures"])
    assert bad["against_the_page_handed_over"]["style_declarations_changed"] == 2
    assert bad["render"] == {"rendered": NOT_RENDERED["error"]}


def test_every_page_handed_over_counts_and_pages_written_but_not_handed_over_are_listed(tmp_path):
    pages = []
    for number, name in enumerate(("style-a.html", "style-b.html", "style-c.html"), 1):
        folder = tmp_path / f"t{number}"
        folder.mkdir()
        (folder / name).write_text(f"<html><body><h1>style {number}</h1></body></html>")
        pages.append(folder / name)
    child = {"kind": "child.execution", "records": [wrote(tmp_path / "preview-d.html", "<html></html>")]}
    exchanges = [turn("pick one", [child], pages[:2]), turn("and this", files=pages[2:], number=2)]
    found = case.facts(exchanges, CARDS["north"], VOCABULARY, BOOKS, render=unrendered)
    assert [(row["turn"], row["file"]) for row in found["pages_delivered"]] == [
        (1, "style-a.html"),
        (1, "style-b.html"),
        (2, "style-c.html"),
    ]
    assert found["pages_written_not_handed_over"] == ["preview-d.html"] and len(found["revisions"]) == 2
    assert found["revisions"][0]["visible_lines_removed"] == ["style 1"]
    assert case.facts([turn("no page yet")], None, VOCABULARY, BOOKS, render=unrendered) == {}


def test_the_owner_finds_each_drills_card_by_its_name(tmp_path):
    owner = case.ReviewOwner(SCENARIO, None, tmp_path / "skills", workdir=tmp_path, deliver="pool")
    assert owner.card("holdout-northwest-2", None).name == "northwest"
    assert owner.card("s2-monthly", None).name == "monthly" and owner.card("anyone", None) is None
    drawn = type("Drawn", (), {"name": "stretch"})()
    assert owner.card("holdout-x", drawn).issue == "second"
    assert owner._facts("holdout-x", [turn("hello")], None) == {}
    found = owner._facts("s1-quarter", [turn("hello")], None)
    assert found["card"]["expected_file"] == case.meeting(CARDS["quarter"], VOCABULARY)[1]


def test_selector_and_dom_association_changes_survive_equal_declaration_counts():
    before = (
        '<style>.title{font-size:40px}.body{font-size:28px}</style><h1 class="title">Title</h1><p class="body">Text</p>'
    )
    after = before.replace(".title{", ".swap{").replace(".body{", ".title{").replace(".swap{", ".body{")
    measured = case.page_changes(before, after, case.visible(before), case.visible(after))
    assert measured["style_declarations_changed"] == 0
    assert measured["style_rules_before"] != measured["style_rules_after"]
    assert measured["full_source_before"] == before and measured["full_source_after"] == after
    classes = before.replace('class="title"', 'class="body"')
    assert case.page_changes(before, classes, case.visible(before), case.visible(classes))["source_changes"][
        "text_added"
    ]


def test_final_missing_delivery_does_not_fall_back_to_old_page(tmp_path):
    old = tmp_path / "old.html"
    old.write_text("<h1>Old page</h1>")
    final = tmp_path / "final.html"
    found = case.facts(
        [turn("old", files=[old]), turn("final", files=[final], number=2)],
        CARDS["quarter"],
        VOCABULARY,
        BOOKS,
        render=unrendered,
    )
    assert "unavailable" in found["final_page_observation"]
    assert "figures" not in found


def test_native_snapshot_identity_preserves_same_name_different_versions(tmp_path):
    first, last = tmp_path / "v1", tmp_path / "v2"
    first.mkdir()
    last.mkdir()
    paths = [first / "page.html", last / "page.html"]
    paths[0].write_text("<h1>Unsafe old content</h1>")
    paths[1].write_text("<h1>Corrected</h1>")
    versions = case.page_versions([turn("both", files=paths)])
    assert [entry[2] for entry in versions] == [path.read_text() for path in paths]
    reused = case.page_versions([turn("both", files=[paths[1], paths[1]])])
    assert reused[0][2] is None and reused[1][2] == paths[1].read_text()


def test_sheet_requires_actual_contained_bytes_not_suffix_or_failed_write(tmp_path):
    root, outside = tmp_path / "work", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    page = root / "page.html"
    folder = VOCABULARY.one("sheet_folder")
    (root / folder).symlink_to(outside, target_is_directory=True)
    (outside / "page.md").write_text("|1|claimed|\n|---|---|\n|1|yes|")
    found = case.sheet_facts(page, {}, "1", VOCABULARY, workdir=root)
    assert found["status"] == "unavailable" and found["filed"] is None
    for ok in (False, None, "true"):
        row = wrote(root / "page.md", "forged")
        row["event"]["ok"] = ok
        assert not case.written([row])


def test_month_and_quarter_cumulative_remain_distinct_required_occurrences():
    measured = case.data_block("0.15 104% 0.42 35%", CARDS["northeast"], BOOKS, VOCABULARY)
    labels = [entry["label"] for entry in measured["required_items"]]
    assert any("month actual 0.15" in label for label in labels)
    assert any("Q4 cumulative actual 0.15" in label for label in labels)
    assert "scope" in measured and "present" not in measured


@pytest.mark.skipif(CHROMIUM is None, reason="no headless Chromium on this machine")
def test_dynamic_financial_text_and_pointer_transparent_cover_are_observed(tmp_path, monkeypatch):
    monkeypatch.setattr(case, "browser_executable", lambda: CHROMIUM)
    page = tmp_path / "dynamic.html"
    page.write_text(
        '<html><body><table><tr><td>Actual</td><td id="actual">604</td></tr></table>'
        '<script>document.getElementById("actual").textContent="9999"</script>'
        '<div style="position:fixed;inset:0;background:#fff;pointer-events:none;z-index:100"></div></body></html>'
    )
    found = case.facts([turn("done", files=[page])], CARDS["northeast"], VOCABULARY, BOOKS)
    assert found["financial_text_source"] == "rendered DOM"
    assert found["rendered_evidence"]["tables"] == [[["Actual", "9999"]]]
    assert any("9,999" in value for value in found["figures"]["figures_not_in_the_table"])
    assert found["render"]["painted_overlap_candidates"]
