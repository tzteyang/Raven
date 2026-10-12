"""The laundry chain short-video case: it loads, its cards are complete, and its owner's facts measure scripts right.

Chinese sample text is read from the case's own markdown (the published scripts, the flagged ones, the counting
examples of the norms), so this file stays in ASCII.
"""

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from experimental.cultivation.counterpart.rulers import tables, words
from experimental.harness.scenario.contract import load
from experimental.simulation.__main__ import owner_of
from experimental.simulation.bench.scenario import BUNDLED, Scenario
from experimental.simulation.cases.laundry_short_video.owner import (
    LaundryOwner,
    Line,
    Ruler,
    facts,
    intended,
    script_delivered,
    spoken_count,
)

CASE = BUNDLED / "laundry_short_video"
FENCE = "`" * 3


@pytest.fixture(scope="module")
def ruler() -> Ruler:
    return Ruler.load(Scenario.load(CASE))


def _blocks(material: str) -> list[str]:
    text = (CASE / "materials" / material / "SKILL.md").read_text()
    return re.findall(rf"{FENCE}\n(.*?){FENCE}", text, re.S)


def _published(number: str) -> str:
    return next(block for block in _blocks("script-samples") if number in block.splitlines()[0])


def _flagged() -> str:
    return next(block for block in _blocks("flagged-scripts") if block.startswith("1."))


def _turn(text="", delivered=(), records=()):
    rows = [{"kind": "runner.event", "event_type": "Text", "event": {"content": text}}, *records]
    return SimpleNamespace(user="", execution=SimpleNamespace(deliverables=tuple(delivered), records=rows))


def _call(number, name, arguments, ok=True):
    started = {"phase": "start", "tool_call_id": number, "name": name, "arguments": arguments}
    finished = {"phase": "complete", "tool_call_id": number, "ok": ok}
    return [
        {"kind": "runner.event", "event_type": "ToolEvent", "event": started},
        {"kind": "runner.event", "event_type": "ToolEvent", "event": finished},
    ]


def _delivery(number, path):
    event = {"phase": "complete", "tool_call_id": number, "ok": True}
    event["metadata"] = {"raven_delivery": {"files": [{"path": str(path)}], "message": "ok"}}
    return [{"kind": "runner.event", "event_type": "ToolEvent", "event": event}]


def test_the_case_loads_with_its_own_owner_and_a_complete_schedule():
    read = load(CASE)
    assert owner_of(Scenario.load(CASE)) is LaundryOwner
    names = {case.id for case in read.situation.cases}
    assert len(names) == 12 and len(read.materials) == 8
    for case in read.situation.cases:
        assert case.expected and case.expected.strip()
        assert case.files and all((CASE / item).is_file() for item in case.files)
    schedule = read.situation.schedule
    assert {name for step in schedule.rounds for name in step} | set(schedule.holdout) <= names
    assert len(schedule.holdout) == 6 and schedule.holdout_rounds == (0, 1, 3)
    assert schedule.rounds[2] == (schedule.rounds[0][0], schedule.rounds[0][2])
    for plan in read.exchange.plans.values():
        given = [name for step in plan.steps for name in step]
        assert sorted(given) == sorted(read.materials) and len(given) == len(set(given))


def test_the_twin_card_repeats_its_exam_card_word_for_word():
    twin, original = (CASE / "personas" / f"{name}.md" for name in ("xieziagain", "xiezi"))
    assert twin.read_text().replace("xieziagain", "xiezi") == original.read_text()
    files = [CASE / "handouts" / name for name in ("xieziagain", "xiezi")]
    assert [path.read_bytes() for path in sorted(files[0].iterdir())] == [
        path.read_bytes() for path in sorted(files[1].iterdir())
    ]


def test_the_counting_examples_of_the_norms_are_what_the_ruler_counts(ruler):
    norms = (CASE / "materials" / "script-norms" / "SKILL.md").read_text()
    examples = [table for table in tables(norms) if len(table[0]) == 3 and table[1][2].isdigit()]
    assert examples
    for written, _, count in examples[0][1:]:
        assert spoken_count(ruler.spoken(written)) == int(count), written


def test_colloquial_two_keeps_its_original_store_and_duration_context(ruler):
    two = ruler.word("two_word")
    store = two + ruler.word("store_counter") + " store"
    counted = ruler.stores([Line(store, store, spoken_count(store), True)])["counted"]
    assert counted == [{"count": 2, "line": 1, "context": store}]
    duration = two + ruler.words["time_units"][0]
    measured = ruler.times([Line(duration, duration, spoken_count(duration), True)])
    assert measured == [
        {"said": duration, "value": 2, "unit": ruler.words["time_units"][0], "line": 1, "kind": "unclassified"}
    ]


def test_a_compliant_script_and_its_ledger_row_measure_as_compliant(ruler, tmp_path):
    script = _published("KB-1016-01")
    path = tmp_path / "script.md"
    path.write_text(script)
    ledger = words(CASE / "reference.md")["ledger_path"][0]
    row = "| 2026-10-20 | x | KB-1020-01 | TG-2601 | x | x | x | x | 100 | v1 | x | x | x |"
    exchanges = [
        _turn("hi", records=_call("r1", "read_file", {"path": "uploads/publish-ledger/SKILL.md"})),
        _turn("here", [path], [*_delivery("d1", path), *_call("w1", "write_file", {"path": ledger, "content": row})]),
    ]
    found = facts(exchanges, ruler)
    version = found["versions"][0]
    assert version["spoken_count"] == version["stated_count"] == 99
    assert version["first_line_count"] == 12 and version["cta_in_last_line"] is True
    assert version["first_line_prices"][0]["value"] == 79
    assert any(item.startswith("TG-2601 group") for item in version["first_line_prices"][0]["listings"])
    assert "lines_without_shot" not in version and "word_hits" not in version
    assert [time["value"] for time in version["pickup_times"]] == [5]
    assert found["opening_history"]["same_pain_rows"][0]["number"] == "KB-1016-01"
    assert found["ledger"]["written_with_or_after_last_script"] is True
    assert found["ledger"]["read_before_first_script"] is True
    assert found["ledger"]["rows_written"] == [row]


def test_a_flagged_script_shows_its_word_hits_and_a_missing_ledger_write(ruler, tmp_path):
    path = tmp_path / "flagged.md"
    path.write_text(_flagged())
    found = facts([_turn("here", [path], _delivery("d1", path))], ruler)
    version = found["versions"][0]
    assert version["first_line_count"] == 27
    assert set(version["word_hits"]) == {
        "catchphrases",
        "clickbait",
        "ending_cliches",
        "absolute",
        "comparison",
        "overpromise",
    }
    assert [price["value"] for price in version["first_line_prices"]] == [129, 69]
    assert [time["value"] for time in version["pickup_times"]] == [72]
    assert found["ledger"]["written_with_or_after_last_script"] is False
    assert found["ledger"]["read_before_first_script"] is False


def test_a_revision_after_an_overrun_is_measured_version_by_version(ruler, tmp_path):
    first, second = tmp_path / "v1.md", tmp_path / "v2.md"
    script = _published("KB-1014-01")
    lines = script.splitlines()
    shortened = [line for line in lines if not line.startswith("7.")]
    first.write_text(script)
    second.write_text("\n".join(shortened))
    found = facts([_turn("v1", [first], _delivery("a", first)), _turn("v2", [second], _delivery("b", second))], ruler)
    counts = [version["spoken_count"] for version in found["versions"]]
    assert counts[0] == 105 and counts[1] == 105 - found["versions"][0]["line_counts"][6]
    assert [version["turn"] for version in found["versions"]] == [1, 2]


def test_a_script_pasted_into_the_chat_is_still_measured(ruler):
    found = facts([_turn(_published("KB-1010-01"))], ruler)
    assert found["versions"][0]["source"] == "message 1"
    assert found["versions"][0]["spoken_count"] == 100


def test_trailing_spoken_violations_are_not_removed_as_a_checklist(ruler):
    base = _published("KB-1016-01")
    promise = ruler.word("overpromise")
    measured = ruler.version("draft.md", 1, base + f"\n8. {promise}.\n")
    assert measured["spoken_lines"] == 8
    assert measured["spoken_count"] == 99 + spoken_count(ruler.spoken(promise))
    assert measured["lines_without_shot"] == [8]
    assert measured["cta_in_last_line"] is False
    assert promise in measured["word_hits"]["overpromise"]
    separate = ruler.version("draft.md", 1, base + f"\n## Review checklist\n\n1. {promise}.\n")
    assert separate["spoken_count"] == 99
    assert "word_hits" not in separate


def test_earlier_script_with_an_unconventional_filename_is_still_measured(ruler, tmp_path):
    earlier = tmp_path / "draft-v1.md"
    later = tmp_path / f"{ruler.word('script_folder')}-KB-1020-01-v2.md"
    earlier.write_text(_flagged())
    later.write_text(_published("KB-1016-01"))
    measured = facts([_turn(delivered=[earlier]), _turn(delivered=[later])], ruler)
    assert [version["source"] for version in measured["versions"]] == [earlier.name, later.name]
    assert "overpromise" in measured["versions"][0]["word_hits"]


def test_shot_facts_preserve_missing_required_form_and_detached_notes(ruler):
    base = _published("KB-1016-01")
    folded = base.replace(chr(0xFF3B), "[").replace(chr(0xFF3D), "]")
    measured = ruler.version("script.md", 1, folded)
    assert measured["spoken_count"] == 99
    assert measured["lines_without_shot"] == list(range(1, 8))
    first = next(line for line in base.splitlines() if line.startswith("1."))
    spoken, note = first.split(chr(0xFF3B), 1)
    detached = base.replace(first, spoken + "\n" + chr(0xFF3B) + note)
    measured = ruler.version("script.md", 1, detached)
    assert measured["spoken_count"] == 99
    assert measured["lines_without_shot"] == [1]


def test_detached_notes_keep_their_public_safety_claims_and_line_attribution(ruler):
    base = _published("KB-1016-01")
    first = next(line for line in base.splitlines() if line.startswith("1."))
    spoken = first.split(chr(0xFF3B), 1)[0]
    promise = ruler.word("overpromise")
    cap = ruler.words["guarantee_terms"][3]
    copy = promise + ", " + cap + "2000" + ruler.word("currency")
    copy += ", " + ruler.word("price_marks") + "80" + ruler.word("currency") + ", 72h" + ruler.word("pickup_marks")
    note = chr(0xFF3B) + ruler.word("shot") + ": " + ruler.words["display_marks"][1] + '"' + copy + '"' + chr(0xFF3D)
    for replacement in (spoken + "\n" + note, spoken + "\n" + note[1:-1], first + "\n" + note):
        measured = ruler.version("script.md", 1, base.replace(first, replacement))
        assert measured["lines_without_shot"] == [1]
        assert promise in measured["word_hits"]["overpromise"]
        assert cap in measured["guarantee"]["other_compensation_lines"]
        display = next(
            row
            for row in measured["displayed_claims"]
            if row["line"] == 1 and 80 in [p["value"] for p in row["prices"]]
        )
        assert 80 in [price["value"] for price in display["prices"]]
        assert display["times"][0]["value"] == 72


def test_allowed_guarantee_does_not_hide_extra_compensation_on_the_same_line(ruler):
    allowed = ruler.word("guarantee_line")
    cap = ruler.words["guarantee_terms"][3]
    extra = cap + "2000" + ruler.word("currency")
    assert ruler.guarantee(allowed)["other_compensation_lines"] == {}
    measured = ruler.guarantee(allowed + ", " + extra)
    assert measured["allowed_sentence_lines"] == [1]
    assert cap in measured["other_compensation_lines"]


def test_displayed_claims_are_measured_separately_from_scene_directions(ruler):
    base = _published("KB-1016-01")
    first = next(line for line in base.splitlines() if line.startswith("1."))
    spoken = first.split(chr(0xFF3B), 1)[0]
    copy = ruler.word("price_marks") + "80" + ruler.word("currency")
    copy += ", " + ruler.word("pickup_marks") + "72h, " + ruler.words["stores"][-1]
    note = chr(0xFF3B) + ruler.word("shot") + ": " + ruler.word("display_marks") + '"' + copy + '"' + chr(0xFF3D)
    measured = ruler.version("script.md", 1, base.replace(first, spoken + note))
    display = next(row for row in measured["displayed_claims"] if row["line"] == 1)
    assert [price["value"] for price in display["prices"]] == [80]
    assert [time["value"] for time in display["times"]] == [72]
    assert display["stores"]["named"][0]["store"] == ruler.words["stores"][-1]
    assert measured["prices"] == ruler.version("base.md", 1, base)["prices"]
    scene = chr(0xFF3B) + ruler.word("shot") + ": 30" + chr(0x2103) + chr(0xFF3D)
    control = ruler.version("script.md", 1, base.replace(first, spoken + scene))
    assert all(row["line"] != 1 for row in control["displayed_claims"])


def test_bare_unlisted_price_and_chinese_count_are_preserved(ruler):
    claim = ruler.word("price_marks") + "80"
    assert ruler.prices(ruler.spoken(claim)) == [{"said": ruler.spoken("80"), "value": 80, "listings": []}]
    assert ruler.stated(ruler.word("count_label") + ": " + ruler.spoken("99")) == 99
    assert ruler.stated("**" + ruler.word("count_label") + "**: **99**") == 99


def test_colloquial_validity_and_unclassified_duration_do_not_become_pickup_claims(ruler):
    text = ruler.words["validity_marks"][3] + "90" + ruler.words["time_units"][1]
    text += ruler.words["validity_marks"][5] + ", " + "5" + ruler.words["time_units"][1] + ruler.word("pickup_marks")
    said = ruler.spoken(text)
    measured = ruler.times([Line(text, said, spoken_count(said), True)])
    assert measured[0]["kind"] == "validity"
    assert measured[0]["value"] == 90
    assert measured[1]["value"] == 5
    assert "kind" not in measured[1]


@pytest.mark.parametrize("outcome", [True, False, None])
def test_ledger_delivery_never_advances_a_mutation_and_unknown_outcomes_are_not_success(ruler, outcome):
    path = ruler.word("ledger_path")
    written = _call("old", "write_file", {"path": path}, ok=outcome)
    delivered = _call("sent", "deliver_files", {"files": [{"path": path}]})
    versions = [{"source": "v2.md", "turn": 2, "header": {"number": "KB-1020-01"}}]
    measured = ruler.ledger([_turn(records=written), _turn(records=delivered)], versions)
    assert all(row["tool"] != "deliver_files" for row in measured["writes"])
    assert measured["written_with_or_after_last_script"] is False
    if outcome is True:
        assert measured["last_ledger_write_turn"] == 1
    else:
        assert "last_ledger_write_turn" not in measured
        assert measured["writes"][0]["ok"] is outcome


def test_every_labelled_card_binds_account_and_publish_independently(ruler):
    scenario = Scenario.load(CASE)
    for persona in scenario.personas:
        binding = intended(SimpleNamespace(expected=persona.expected), ruler)
        assert set(binding) == {"account", "publish"}, persona.name
        assert binding["publish"] == ("2026-10-23" if persona.name == "xuedixue" else "2026-10-20")
        assert (
            binding["account"]
            == ruler.words["accounts"][
                0 if persona.name in {"duanjian", "dayi", "sanjiantao", "huitou", "gaofeng", "tongkuang"} else 1
            ]
        )


def test_wrong_output_account_cannot_select_a_more_permissive_hook_history(ruler, tmp_path):
    base = _published("KB-1016-01")
    first = next(line for line in base.splitlines() if line.startswith("1."))
    busy = ruler.word("pain_busy")
    changed = base.replace(first, f"1. {busy}?29.9" + first[first.index(chr(0xFF3B)) :])
    path = tmp_path / "draft.md"
    path.write_text(changed)
    persona = next(persona for persona in Scenario.load(CASE).personas if persona.name == "xiezi")
    measured = facts([_turn(delivered=[path])], ruler, card=SimpleNamespace(expected=persona.expected))
    assert measured["opening_history"]["same_pain_in_window"] is True
    assert measured["intended_binding"]["account"] == ruler.words["accounts"][1]
    assert "account" in measured["header_binding_differences"]


def test_explicit_customer_publication_change_updates_independent_binding(ruler):
    persona = next(persona for persona in Scenario.load(CASE).personas if persona.name == "duanjian")
    brand = ruler.words["accounts"][1]
    message = ruler.word("publish_actions") + " " + brand + " 2026-10-23"
    binding = intended(SimpleNamespace(expected=persona.expected), ruler, [_turn()])
    changed = intended(SimpleNamespace(expected=persona.expected), ruler, [SimpleNamespace(user=message)])
    assert binding["account"] == ruler.words["accounts"][0]
    assert changed == {"account": brand, "publish": "2026-10-23"}


def test_negated_prior_and_filming_clauses_do_not_override_current_publication(ruler):
    persona = next(persona for persona in Scenario.load(CASE).personas if persona.name == "duanjian")
    card = SimpleNamespace(expected=persona.expected)
    owner_alias = ruler.words["account_aliases"][1].partition("=")[0]
    brand_alias = ruler.words["account_aliases"][-1].partition("=")[0]
    action = ruler.word("publish_actions")
    negated = owner_alias + ruler.word("publication_negations") + ", " + action + brand_alias
    recalled = ruler.word("past_marks") + action + owner_alias + ", " + ruler.words["publish_actions"][-1] + brand_alias
    for message in (negated, recalled):
        binding = intended(card, ruler, [SimpleNamespace(user=message)])
        assert binding["account"] == ruler.words["accounts"][1]
    filming = ruler.word("ledger_store")[:2] + "10" + chr(0x6708) + "20" + chr(0x65E5)
    publishing = ruler.words["publish_actions"][1] + "10" + chr(0x6708) + "23" + chr(0x65E5)
    binding = intended(card, ruler, [SimpleNamespace(user=filming + ", " + publishing)])
    assert binding["publish"] == "2026-10-23"
    uncertain = action + owner_alias + ruler.word("publication_uncertain") + brand_alias
    binding = intended(card, ruler, [SimpleNamespace(user=uncertain)])
    assert binding["uncertain_publication_clauses"] == [uncertain]


def test_two_deal_line_facts_expose_the_missing_other_price_and_its_correct_style(ruler):
    base = _published("KB-1016-01")
    measured = ruler.version("script.md", 1, base)
    assert measured["lines"][0]["prices"][0]["value"] == 79
    assert measured["lines"][1]["prices"] == []
    second = next(line for line in base.splitlines() if line.startswith("2."))
    note = second[second.index(chr(0xFF3B)) :]
    style = ruler.words["price_marks"][4]
    replacement = "2. " + style + "109" + ruler.word("currency") + note
    changed = ruler.version("script.md", 1, base.replace(second, replacement))
    assert changed["lines"][1]["prices"][0]["value"] == 109
    assert style in changed["lines"][1]["read_as"]


def test_ledger_file_exposes_every_required_row_field(ruler, tmp_path):
    path = tmp_path / ruler.word("ledger_path")
    path.parent.mkdir(parents=True)
    exported = (CASE / "materials" / "publish-ledger" / "SKILL.md").read_text()
    source = next(table for table in tables(exported) if len(table[0]) == 13)
    row = list(source[1])
    row[0], row[2] = "2026-10-20", "KB-1020-01"
    text = "\n".join("| " + " | ".join(items) + " |" for items in [source[0], ["---"] * 13, row])
    path.write_text(text)
    measured = ruler.ledger_file(tmp_path, {"KB-1020-01"})
    assert set(measured["new_rows"][0]) == {
        "date",
        "account",
        "number",
        "deal",
        "pain",
        "first",
        "speaker",
        "store",
        "count",
        "version",
        "status",
        "orders",
        "notes",
        "line",
    }


def test_delivery_predicate_requires_a_recognized_script_file_in_every_drill(ruler):
    script = ruler.version("draft-v1.md", 1, _published("KB-1016-01"))
    drill = {
        "references": {"versions": [script]},
        "exchanges": [{"delivered": [{"name": "draft-v1.md"}]}],
    }
    assert script_delivered({"drills": [drill]}) is True
    ledger = {**drill, "exchanges": [{"delivered": [{"name": Path(ruler.word("ledger_path")).name}]}]}
    assert script_delivered({"drills": [ledger]}) is False
    assert script_delivered({"drills": [drill, ledger]}) is False
    assert script_delivered({"drills": [{**drill, "references": {}}]}) is False
    message = {**script, "source": "message 1"}
    assert script_delivered({"drills": [{**drill, "references": {"versions": [message]}}]}) is False
    assert script_delivered({"drills": []}) is False
