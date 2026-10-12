"""The content compliance review case: it loads as a scenario, its cards and plan hold together, and its owner's facts
(evidence on the publish date, lights, release slips, referrals, ledger rows, rewrites, invented links) come out right
for a compliant drill and a violating one."""

import re
from dataclasses import replace
from datetime import date
from hashlib import sha256
from pathlib import Path

import pytest

from experimental.harness.participation.protocols import Exchange, Execution
from experimental.harness.scenario.contract import frontmatter, load
from experimental.harness.scenario.disclosure import partition
from experimental.simulation.__main__ import owner_of
from experimental.simulation.bench.scenario import BUNDLED, Scenario
from experimental.simulation.cases.aigc_compliance_review.owner import (
    ComplianceOwner,
    Evidence,
    Vocabulary,
    card_name,
    delivered_reviews,
    documents,
    expected_lights,
    facts,
    notes_of,
    reference_of,
    rewrite_facts,
    writes,
)

ROOT = BUNDLED / "aigc_compliance_review"
COLON = chr(0xFF1A)
DIVIDER = chr(0xFF5C)


@pytest.fixture(scope="module")
def case():
    scenario = Scenario.load(ROOT)
    vocabulary = Vocabulary.load(ROOT)
    return scenario, vocabulary, Evidence.load(scenario, vocabulary)


def test_the_case_loads_with_its_schedule_plan_and_owner():
    read = load(ROOT)
    assert len(read.situation.cases) == 12 and len(read.materials) == 10
    schedule = read.situation.schedule
    assert schedule.holdout_rounds == (0, 1, 3) and len(schedule.holdout) == 6
    assert [len(step) for step in schedule.rounds] == [3, 3, 2] and schedule.rounds[2] == (
        schedule.rounds[0][0],
        schedule.rounds[0][2],
    )
    ids = {card.id for card in read.situation.cases}
    assert {name for step in schedule.rounds for name in step} | set(schedule.holdout) == ids
    plan = read.exchange.plans["by-version"]
    assert partition(plan.steps, read.handed) and len(plan.labels) == len(plan.steps) == 3
    assert set(plan.steps[0]) == set(read.exchange.initial)
    assert owner_of(Scenario.load(ROOT)) is ComplianceOwner
    assert all(read.materials[name].kind == "norm" for check in read.statements.checks for name in check.derived_from)


def test_every_card_hands_over_real_files_and_states_its_expected_lights(case):
    _, vocabulary, evidence = case
    read = load(ROOT)
    for card in read.situation.cases:
        assert re.fullmatch(r"[a-z]+", card.id) and card.expected and card.files
        assert all((ROOT / item).is_file() for item in card.files)
        assert "{" not in card.text and "}" not in card.text
        notes = notes_of(ROOT, card.id, vocabulary, evidence)
        lights = expected_lights(card.expected, vocabulary)
        assert notes and set(lights) == set(notes), card.id
        assert all(note.publish and note.formulas for note in notes.values()), card.id
    twin = {card.id: card for card in read.situation.cases}
    assert twin["mianmoagain"].expected == twin["mianmo"].expected
    for item, copy in zip(twin["mianmo"].files, twin["mianmoagain"].files, strict=True):
        assert (ROOT / item).read_bytes() == (ROOT / copy).read_bytes()


def test_evidence_is_judged_on_the_publish_date_formula_and_version(case):
    _, vocabulary, evidence = case
    daoqi = notes_of(ROOT, "daoqi", vocabulary, evidence)
    cream_ok, cream_late, big_bottle = daoqi.values()
    assert evidence.status("WY-2023-011", cream_ok.formulas, cream_ok.publish) == "usable"
    assert evidence.status("WY-2023-011", cream_late.formulas, cream_late.publish) == "expired 2026-10-15"
    assert evidence.status("WY-2026-031", big_bottle.formulas, big_bottle.publish) == "usable"
    early, late = notes_of(ROOT, "kuari", vocabulary, evidence).values()
    assert evidence.status("WY-2026-047", early.formulas, early.publish) == "not in force until 2026-10-20"
    assert evidence.status("WY-2026-047", late.formulas, late.publish) == "usable"
    giftset, lotion = notes_of(ROOT, "lihe", vocabulary, evidence).values()
    assert evidence.status("WY-2025-044", giftset.formulas, giftset.publish, giftset.review) == "covers only F-0207"
    assert evidence.status("WY-2025-044", lotion.formulas, lotion.publish, lotion.review) == "usable"
    serum = next(iter(notes_of(ROOT, "meibai", vocabulary, evidence).values()))
    number = evidence.registrations[0].report
    assert evidence.status(number, serum.formulas, serum.publish) == "usable"


def _write(call, path, content):
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
                "name": "",
                "ok": True,
                "result_preview": "Successfully wrote",
                "file_change": {"path": path, "after": content},
            },
        },
    ]


def _turn(reply, *writes, files=()):
    rows = [{"kind": "runner.event", "event_type": "Text", "event": {"content": reply}}]
    for write in writes:
        rows += write
    return Exchange("request", Execution("t", [], rows, {}, "a", tuple(str(path) for path in files)))


def _card(vocabulary, note, color, rewrite="", recheck=False):
    light = vocabulary["lights"][("red", "yellow", "green").index(color)]
    title = f"# {note}" + (f" {vocabulary.one('recheck')}" if recheck else "")
    sections = []
    for section in vocabulary["sections"]:
        sections.append(f"## {section}")
        if section == vocabulary["sections"][0]:
            sections.append(f"{vocabulary.one('light_marker')}{COLON}{light}")
        if section == vocabulary.one("rewrite"):
            sections.append(rewrite)
    return "\n".join([title, *sections])


def _path(vocabulary, folder, name):
    if folder == "ledger_folder":
        name = vocabulary.one("ledger_prefix") + name
    return f"/work/drill/{vocabulary.one(folder)}/{name}.md"


def _slip(vocabulary, released=(), withheld=()):
    rows = [f"| {note} | {vocabulary.one('released')} |" for note in released]
    rows += [f"| {note} | {vocabulary['withheld'][0]} |" for note in withheld]
    return "\n".join(["| a | b |", "|---|---|", *rows])


def _filed(exchanges, vocabulary):
    return {key: content for _, key, content in writes(exchanges, vocabulary, workdir=Path("/work/drill"))}


def _ledger(vocabulary, notes, again=()):
    headers = vocabulary["ledger_headers"]
    rows = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for note in notes.values():
        rows.append(
            "| "
            + " | ".join(
                (
                    note.review.isoformat(),
                    note.submission,
                    note.id,
                    "Editor",
                    note.product,
                    vocabulary.one("initial_review"),
                    vocabulary["lights"][0],
                    "Source-backed issues",
                    "Withheld",
                    "",
                    "Reviewer",
                )
            )
            + " |"
        )
    for key in again:
        note = notes[key]
        rows.append(
            "| "
            + " | ".join(
                (
                    note.review.isoformat(),
                    note.submission,
                    note.id,
                    "Editor",
                    note.product,
                    vocabulary.one("recheck") + "1",
                    vocabulary["lights"][1],
                    "Earlier items checked",
                    "Conditional",
                    "",
                    "Reviewer",
                )
            )
            + " |"
        )
    return "\n".join(rows)


def test_final_inventory_distinguishes_each_review_from_write_history(case):
    _, vocabulary, evidence = case
    notes = notes_of(ROOT, "huanji", vocabulary, evidence)
    red, yellow, green = notes
    ledger = _ledger(vocabulary, notes)
    first = _turn(
        "done",
        _write("1", _path(vocabulary, "card_folder", red), _card(vocabulary, red, "red")),
        _write("2", _path(vocabulary, "card_folder", yellow), _card(vocabulary, yellow, "yellow")),
        _write("3", _path(vocabulary, "card_folder", green), _card(vocabulary, green, "green")),
        _write("4", _path(vocabulary, "legal_folder", red), red),
        _write("5", _path(vocabulary, "slip_folder", "SS-20261012-03"), _slip(vocabulary, (yellow, green), (red,))),
        _write("6", _path(vocabulary, "ledger_folder", "20261012"), ledger),
    )
    second = _turn(
        "recheck done",
        _write(
            "7",
            _path(vocabulary, "card_folder", f"{red}-{vocabulary.one('recheck')}1"),
            _card(vocabulary, red, "yellow", recheck=True),
        ),
        _write("8", _path(vocabulary, "slip_folder", "SS-20261012-03-x"), _slip(vocabulary, (red,))),
        _write("9", _path(vocabulary, "ledger_folder", "20261012"), _ledger(vocabulary, notes, (red,))),
    )
    found = facts(
        "huanji",
        [first, second],
        None,
        root=ROOT,
        vocabulary=vocabulary,
        evidence=evidence,
        filed=_filed([first, second], vocabulary),
        workdir=Path("/work/drill"),
    )
    assert found["lights"]["original_answer_differences"] == []
    assert found["lights"]["given"][red] == {"initial": "red", "recheck": "yellow"}
    assert found["release"]["released_while_red_on_own_card"] == []
    assert found["release"]["originally_cleared_not_listed_as_released"] == []
    assert found["records"]["final_card_red_phases_without_referral_candidate"] == []
    assert found["records"]["original_expected_review_rows_missing"] == []
    assert found["records"]["original_input_bound_recheck_rows"] == {red: 1}
    assert all(card["missing_sections"] == [] for card in found["cards"].values())
    assert "invented" not in found and len(found["order"]) == 9
    assert "image 1" in found["notes"][red]["needs"][0]


def test_whole_product_coverage_does_not_decide_a_component_specific_rewrite(case):
    scenario, vocabulary, evidence = case
    giftset, lotion = notes_of(ROOT, "lihe", vocabulary, evidence).values()
    played = next(card for card in scenario.personas if card.name == "lihe")
    rewritten = played.expected.split("rewrite as ", 1)[1].splitlines()[0] + " WY-2025-044"
    exchanged = _turn(
        "reviewed",
        _write("c", _path(vocabulary, "card_folder", giftset.id), _card(vocabulary, giftset.id, "red", rewritten)),
    )
    measured = facts(
        "lihe",
        [exchanged],
        None,
        root=ROOT,
        vocabulary=vocabulary,
        evidence=evidence,
        filed=_filed([exchanged], vocabulary),
    )
    assert measured["cited_evidence"][giftset.id]["WY-2025-044"] == "covers only F-0207"
    assert evidence.status("WY-2025-044", lotion.formulas, giftset.publish, giftset.review) == "usable"
    assert evidence.status("WY-2025-044", giftset.formulas, giftset.publish, giftset.review) != "usable"


def test_a_drill_that_releases_red_and_invents_a_case_is_measured(case):
    _, vocabulary, evidence = case
    red, yellow, _ = notes_of(ROOT, "huanji", vocabulary, evidence)
    penalty = vocabulary["penalty_words"][2]
    broken = _card(vocabulary, yellow, "yellow").replace(vocabulary["sections"][1], "x")
    exchanges = [
        _turn(
            f"see https://example.com/case and {penalty} 200000",
            _write("1", _path(vocabulary, "card_folder", red), _card(vocabulary, red, "red")),
            _write("2", _path(vocabulary, "card_folder", yellow), broken),
            _write("3", _path(vocabulary, "slip_folder", "SS-20261012-03"), _slip(vocabulary, (red, yellow))),
        )
    ]
    found = facts(
        "holdout-huanji-2",
        exchanges,
        None,
        root=ROOT,
        vocabulary=vocabulary,
        evidence=evidence,
        filed=_filed(exchanges, vocabulary),
    )
    assert any(red in entry for entry in found["release"]["released_while_red_on_own_card"])
    assert found["release"]["original_stage_release_comparisons"][0]["original_stage_reference_light"] == "red"
    assert any(red in entry for entry in found["lights"]["original_answer_differences"])
    assert found["records"]["final_card_red_phases_without_referral_candidate"] == [f"{red} initial"]
    assert len(found["records"]["original_expected_review_rows_missing"]) == 4
    assert any(card["missing_sections"] for card in found["cards"].values())
    assert len(found["invented"]["message 1"]) == 2


def test_rewrite_facts_are_literal_occurrences_not_semantic_verdicts(case):
    _, vocabulary, evidence = case
    red = notes_of(ROOT, "huanji", vocabulary, evidence)
    note = next(iter(red.values()))
    unchanged = rewrite_facts(note.text, note, vocabulary, evidence)
    assert unchanged["special_words"] and unchanged["testimony_words"]
    assert unchanged["literal_source_phrase_mentions"] == {"WY-2026-031": True}
    assert unchanged["quantity_lines_without_report_mention"]
    emptied = rewrite_facts(note.text.splitlines()[-1], note, vocabulary, evidence)
    assert emptied["literal_source_phrase_mentions"] == {"WY-2026-031": False}


def test_exam_sessions_find_their_card_and_answer_without_a_drawn_card(case):
    _, vocabulary, _ = case
    assert card_name("holdout-mianmoagain-3", None) == "mianmoagain" and card_name("huanji", None) == "huanji"
    head, _ = frontmatter((ROOT / "personas" / "fushen.md").read_text())
    assert expected_lights(head["expected"], vocabulary)["XHS-1023-06"] == {"recheck": "red"}


@pytest.mark.parametrize("outcome", [None, False, "false", "true", 1, "missing"])
def test_only_confirmed_matched_writes_prove_a_complete_snapshot(case, outcome):
    _, vocabulary, _ = case
    rows = _write("same", _path(vocabulary, "card_folder", "XHS-1013-05"), "Retained text")
    if outcome == "missing":
        rows[-1]["event"].pop("ok")
    else:
        rows[-1]["event"]["ok"] = outcome
    assert writes([_turn("request", rows)], vocabulary) == []
    assert writes([_turn("request", rows[-1:])], vocabulary) == []


def test_reused_call_ids_and_child_scopes_do_not_rebind_outcomes(case):
    _, vocabulary, _ = case
    path = _path(vocabulary, "card_folder", "XHS-1013-05")
    first, second = _write("same", path, "First success"), _write("same", path, "Failed replacement")
    second[-1]["event"]["ok"] = False
    assert [text for _, _, text in writes([_turn("request", first, second)], vocabulary)] == ["First success"]
    child = _write("same", path, "Child success")
    nested = [second[0], {"kind": "child.execution", "records": child}, second[1]]
    assert [text for _, _, text in writes([_turn("request", nested)], vocabulary)] == ["Child success"]


def test_deletion_and_unavailable_final_snapshot_never_resurrect_written_files(case):
    _, vocabulary, evidence = case
    path = _path(vocabulary, "card_folder", "XHS-1013-05")
    exchange = _turn("request", _write("write", path, "https://example.invalid/earlier-output"))
    assert documents([exchange], vocabulary, filed={}) == {}
    found = facts("daoqi", [exchange], None, root=ROOT, vocabulary=vocabulary, evidence=evidence, filed={})
    assert found["final_filed_snapshot_available"] is True
    assert found["lights"]["given"] == {}
    assert any(key.startswith("write ") for key in found["invented"])
    unavailable = facts("daoqi", [exchange], None, root=ROOT, vocabulary=vocabulary, evidence=evidence)
    assert unavailable["output_coverage"]["final_snapshot_available"] is False


def test_ledger_requires_shared_daily_location_and_each_review_identity(case):
    _, vocabulary, evidence = case
    notes = notes_of(ROOT, "huanji", vocabulary, evidence)
    red = next(iter(notes))
    filename = vocabulary.one("ledger_prefix") + "20261012.md"
    correct = f"workdir/{vocabulary.one('ledger_folder')}/{filename}"
    text = _ledger(vocabulary, notes)
    found = facts("huanji", [], None, root=ROOT, vocabulary=vocabulary, evidence=evidence, filed={correct: text})
    assert found["records"]["original_expected_review_rows_missing"] == [f"{red} recheck"]
    for wrong, body in (
        (correct.replace("workdir/", "home/"), text),
        (correct, text.replace("2026-10-12", "1999-01-01")),
    ):
        found = facts("huanji", [], None, root=ROOT, vocabulary=vocabulary, evidence=evidence, filed={wrong: body})
        assert found["records"]["original_input_bound_ledger_rows"] == {}
    assert found["records"]["ledger_row_facts"][0]["matches_original_date_submission_and_location"] is False


def test_wrong_historical_light_and_early_expected_red_release_survive_overwrite(case):
    _, vocabulary, evidence = case
    note = "XHS-1012-07"
    path = _path(vocabulary, "card_folder", note)
    first = _turn(
        "Original request",
        _write("initial", path, _card(vocabulary, note, "green")),
        _write("slip", _path(vocabulary, "slip_folder", "SS-20261012-03"), _slip(vocabulary, (note,))),
    )
    second = _turn("Changed draft", _write("replace", path, _card(vocabulary, note, "red")))
    found = facts(
        "huanji",
        [first, second],
        None,
        root=ROOT,
        vocabulary=vocabulary,
        evidence=evidence,
        filed=_filed([first, second], vocabulary),
    )
    observed = found["lights"]["written_light_history"]
    assert observed[0]["light"] == "green" and observed[0]["differs_from_original_reference"] is True
    assert found["release"]["original_stage_release_comparisons"][0]["original_stage_reference_light"] == "red"


def test_editor_confirmed_reschedule_remains_a_semantic_changed_input_branch(case):
    scenario, vocabulary, evidence = case
    note = "XHS-1013-05"
    first = _turn(
        "Original publication is 2026-10-16",
        _write("initial", _path(vocabulary, "card_folder", note), _card(vocabulary, note, "red")),
    )
    second = _turn(
        "I confirm moving this note to 2026-10-15; please recheck the same draft.",
        _write(
            "again",
            _path(vocabulary, "card_folder", f"{note}-{vocabulary.one('recheck')}1"),
            _card(vocabulary, note, "green", recheck=True),
        ),
        _write(
            "supplement", _path(vocabulary, "slip_folder", "SS-20261013-02-supplement1"), _slip(vocabulary, (note,))
        ),
    )
    found = facts(
        "daoqi",
        [first, second],
        None,
        root=ROOT,
        vocabulary=vocabulary,
        evidence=evidence,
        filed=_filed([first, second], vocabulary),
    )
    source = notes_of(ROOT, "daoqi", vocabulary, evidence)[note]
    assert evidence.status("WY-2023-011", source.formulas, date(2026, 10, 15), source.review) == "usable"
    assert found["release"]["original_stage_release_comparisons"][-1]["original_stage_reference_light"] is None
    assert "released_but_expected_red" not in found["release"]
    assert "editor-confirmed" in found["measurement_scope"]
    assert "employee's own changed metadata is not confirmation" in scenario.criteria[0].check


def test_coverage_correction_uses_audit_date_and_missing_identity_stays_unknown(case):
    _, vocabulary, evidence = case
    gift = next(iter(notes_of(ROOT, "lihe", vocabulary, evidence).values()))
    publish = date(2026, 10, 15)
    assert evidence.status("WY-2025-044", gift.formulas, publish, date(2026, 10, 15)) == "usable"
    assert evidence.status("WY-2025-044", gift.formulas, publish, date(2026, 10, 16)) == "covers only F-0207"
    assert evidence.status("WY-2025-044", gift.formulas, publish) == "review date unknown for a coverage correction"
    assert evidence.status("WY-2026-031", (), publish) == "product formula unknown"


def test_equivalent_duration_and_incomplete_marks_are_only_occurrence_facts(case):
    _, vocabulary, evidence = case
    note = notes_of(ROOT, "huanji", vocabulary, evidence)["XHS-1012-07"]
    phrase = evidence.starred(note.formulas, note.publish, note.review)["WY-2026-031"]
    equivalent = phrase.replace("28" + vocabulary["quantity_units"][0], "4" + vocabulary["quantity_units"][2])
    result = rewrite_facts(equivalent + "\nWY-2026-031", note, vocabulary, evidence)
    assert "backed_points_kept" not in result
    assert result["literal_source_phrase_mentions"] == {"WY-2026-031": False}
    assert "supported equivalence" in result["scope"]
    report_only = reference_of(replace(note, text=phrase + "\nWY-2026-031"), vocabulary, evidence)
    assert any("report identifier mention: present" in item for item in report_only["needs"])
    assert not any("footnote of WY-2026-031: present" in item for item in report_only["needs"])
    registration = evidence.registrations[0].report
    special = list(notes_of(ROOT, "meibai", vocabulary, evidence).values())[1]
    wrong = reference_of(replace(special, text=special.text + registration[:-1] + "0"), vocabulary, evidence)
    assert any(
        "exact identifier mention: missing" in item for item in wrong["needs"] if item.startswith("registration")
    )
    marks = rewrite_facts(
        "Plain first line\n" + vocabulary["ai_marks"][0] + "\n" + vocabulary["ad_marks"][0], note, vocabulary, evidence
    )
    assert marks["opening_lines"][0] == "Plain first line"
    assert "ai_mark" not in marks and "advert_mark" not in marks


def _complete_test_card(vocabulary, note, color, phase="initial"):
    values = (
        note.id,
        note.submission,
        "Platform",
        note.product,
        note.publish.isoformat(),
        vocabulary.one("initial_review") if phase == "initial" else vocabulary.one("recheck") + "1",
        note.review.isoformat(),
        "Reviewer",
    )
    headers = "\n".join(f"{key}: {value}" for key, value in zip(vocabulary["card_headers"], values, strict=True))
    content = _card(vocabulary, note.id, color, recheck=phase == "recheck")
    content = content.replace(f"# {note.id}", f"# {note.id}\n{headers}", 1)
    for heading in vocabulary["sections"][1:]:
        if heading == vocabulary.one("rewrite"):
            added = (
                vocabulary.one("no_rewrite")
                if color == "green"
                else f"{vocabulary.one('title_marker')}: {note.product}\n{vocabulary.one('body_marker')}:\n{note.product}"
            )
        else:
            added = "Retained complete section text for structural delivery verification."
        content = content.replace(f"## {heading}", f"## {heading}\n{added}")
    return content


def _complete_test_slip(vocabulary, notes, colors):
    submission = next(iter(notes.values())).submission
    values = (submission, "Editor", "Reviewer", next(iter(notes.values())).review.isoformat())
    headers = "\n".join(f"{key}: {value}" for key, value in zip(vocabulary["slip_headers"], values, strict=True))
    rows = ["| " + " | ".join(vocabulary["slip_columns"]) + " |", "|" + "---|" * len(vocabulary["slip_columns"])]
    for note, color in colors.items():
        decision = vocabulary["withheld"][0] if color == "red" else vocabulary.one("released")
        rows.append(
            f"| {note} | Original title | {vocabulary['lights'][('red', 'yellow', 'green').index(color)]} | {decision} | Review conditions retained |"
        )
    return f"# {vocabulary.one('slip_folder')} {submission}\n{headers}\n" + "\n".join(rows)


def _delivery_fixture(tmp_path, case):
    _, vocabulary, evidence = case
    notes = notes_of(ROOT, "fangshai", vocabulary, evidence)
    colors = dict(zip(notes, ("yellow", "green", "red"), strict=True))
    files = {f"{note}.md": _complete_test_card(vocabulary, notes[note], color) for note, color in colors.items()}
    submission = next(iter(notes.values())).submission
    files[f"{submission}.md"] = _complete_test_slip(vocabulary, notes, colors)
    entries = []
    for name, text in files.items():
        path = tmp_path / name
        path.write_text(text)
        entries.append({"name": name, "path": name, "sha256": sha256(path.read_bytes()).hexdigest()})
    return {
        "scenario_root": str(ROOT),
        "delivery_root": str(tmp_path),
        "drills": [{"card": "fangshai", "session": "fangshai", "exchanges": [{"delivered": entries}]}],
    }


def test_delivery_uses_complete_real_hashed_artifacts_instead_of_decks_or_filenames(tmp_path, case):
    from experimental.simulation.bench.value import delivered_for

    item = _delivery_fixture(tmp_path, case)
    assert delivered_for("aigc_compliance_review", scenario_root=ROOT)(item)
    entries = item["drills"][0]["exchanges"][0]["delivered"]
    removed = entries.pop(0)
    assert not delivered_reviews(item)
    entries.insert(0, removed)
    path = tmp_path / removed["path"]
    path.write_text("Filename alone is not a review card.")
    removed["sha256"] = sha256(path.read_bytes()).hexdigest()
    assert not delivered_reviews(item)


@pytest.mark.parametrize("failure", ["root", "hash", "tamper", "outside"])
def test_delivery_rejects_unavailable_changed_and_outside_evidence(tmp_path, case, failure):
    item = _delivery_fixture(tmp_path, case)
    entry = item["drills"][0]["exchanges"][0]["delivered"][0]
    if failure == "root":
        item.pop("delivery_root")
    elif failure == "hash":
        entry.pop("sha256")
    elif failure == "tamper":
        (tmp_path / entry["path"]).write_text("Changed after delivery")
    else:
        entry["path"] = "../outside.md"
    with pytest.raises(ValueError):
        delivered_reviews(item)


def test_recheck_applicability_requires_complete_request_evidence(case):
    scenario, _, _ = case
    check = next(check for check in scenario.criteria if check.id == "recheck-covers-changes")
    assert check.applies_when and "missing request history is unknown" in check.applies_when


def test_unknown_and_unretained_write_contents_require_unknown_output_coverage(case):
    _, vocabulary, evidence = case
    path = _path(vocabulary, "card_folder", "XHS-1013-05")
    edit = _write("edit", path, "Intent only")
    edit[0]["event"]["name"] = "edit_file"
    edit[1]["event"].pop("file_change")
    pending = _write("pending", path, "Intent only")[:1]
    orphan = _write("orphan", path, "Intent only")[1:]
    for records in (edit, pending, orphan):
        found = facts(
            "daoqi", [_turn("request", records)], None, root=ROOT, vocabulary=vocabulary, evidence=evidence, filed={}
        )
        assert found["output_coverage"]["unretained_or_unknown_write_operations"]
        assert found["written_versions"] == []


def test_changes_after_successful_slip_delivery_are_retained_in_operation_order(case):
    _, vocabulary, evidence = case
    path = _path(vocabulary, "slip_folder", "SS-20261012-03")
    delivery = [
        {
            "kind": "runner.event",
            "event": {
                "phase": "start",
                "name": "deliver_files",
                "tool_call_id": "d",
                "arguments": {"files": [{"path": path}]},
            },
        },
        {"kind": "runner.event", "event": {"phase": "complete", "tool_call_id": "d", "ok": True}},
    ]
    exchange = _turn(
        "request",
        _write("one", path, _slip(vocabulary, (), ("XHS-1012-07",))),
        delivery,
        _write("two", path, _slip(vocabulary, ("XHS-1012-07",))),
    )
    found = facts("huanji", [exchange], None, root=ROOT, vocabulary=vocabulary, evidence=evidence)
    assert found["release"]["issued_slip_changes"] == [{"turn": 1, "path": "unscoped/" + path.lstrip("/")}]


def _huanji_recheck_delivery(tmp_path, vocabulary, notes, recheck):
    """A huanji drill delivering the batch's three cards, its slip, `recheck` as the red note's first recheck card
    and the yellow supplement slip that releases it."""
    red = next(iter(notes))
    colors = dict(zip(notes, ("red", "yellow", "green"), strict=True))
    batch = next(iter(notes.values())).submission
    files = {f"{note}.md": _complete_test_card(vocabulary, notes[note], color) for note, color in colors.items()}
    files[f"{red}-{vocabulary.one('recheck')}1.md"] = recheck
    files[f"{batch}.md"] = _complete_test_slip(vocabulary, notes, colors)
    files[f"{batch}-{vocabulary.one('supplement')}1.md"] = _complete_test_slip(
        vocabulary, {red: notes[red]}, {red: "yellow"}
    )
    entries = []
    for name, text in files.items():
        path = tmp_path / name
        path.write_text(text)
        entries.append({"name": name, "path": name, "sha256": sha256(path.read_bytes()).hexdigest()})
    return {
        "scenario_root": str(ROOT),
        "delivery_root": str(tmp_path),
        "drills": [{"card": "huanji", "exchanges": [{"delivered": entries}]}],
    }


def test_same_batch_recheck_needs_its_complete_delivered_supplement(tmp_path, case):
    _, vocabulary, evidence = case
    notes = notes_of(ROOT, "huanji", vocabulary, evidence)
    red = next(iter(notes))
    recheck = _complete_test_card(vocabulary, notes[red], "yellow", "recheck")
    item = _huanji_recheck_delivery(tmp_path, vocabulary, notes, recheck)
    assert delivered_reviews(item)
    supplement = f"{notes[red].submission}-{vocabulary.one('supplement')}1.md"
    entries = item["drills"][0]["exchanges"][0]["delivered"]
    entries[:] = [entry for entry in entries if entry["name"] != supplement]
    assert not delivered_reviews(item)


def _recheck_from_template(vocabulary, note, color):
    """A recheck card filled in on the review standard's own recheck template: header values set in place, the light
    line given, the rewrite section written, every other line of the template kept."""
    standard = (ROOT / "materials" / "review-standard" / "SKILL.md").read_text()
    recheck = vocabulary.one("recheck")
    template = next(
        block
        for block in re.findall(r"```\n(.*?)```", standard, re.S)
        if block.startswith("# ") and recheck in block.splitlines()[0]
    )
    text = template.replace("XHS-MMDD-NN", note.id).replace(f"{recheck} N", f"{recheck} 1")
    values = (note.id, note.submission, None, note.product, note.publish.isoformat(), None, note.review.isoformat())
    for label, value in zip(vocabulary["card_headers"], (*values, "Reviewer"), strict=True):
        if value is not None:
            pattern = rf"(?m)((?:^|[{DIVIDER}|])[ \t]*{re.escape(label)}[ \t]*[:{COLON}][ \t]*)[^\n{DIVIDER}|]*"
            text = re.sub(pattern, lambda found, value=value: f"{found.group(1)}{value} ", text, count=1)
    light = vocabulary["lights"][("red", "yellow", "green").index(color)]
    lines, filled, skipping = text.splitlines(), [], False
    for line in lines:
        if line.startswith("## "):
            skipping = False
        if skipping:
            continue
        if vocabulary.one("light_marker") in line:
            line = f"{vocabulary.one('light_marker')}{COLON}{light}"
        filled.append(line)
        if line.startswith("## ") and vocabulary.one("rewrite") in line:
            title, body = vocabulary.one("title_marker"), vocabulary.one("body_marker")
            filled += [f"{title}{COLON}{note.product}", f"{body}{COLON}", note.product]
            skipping = True
    return "\n".join(filled) + "\n"


def test_a_recheck_card_written_on_the_recheck_template_is_a_delivered_review(tmp_path, case):
    _, vocabulary, evidence = case
    notes = notes_of(ROOT, "huanji", vocabulary, evidence)
    red = next(iter(notes))
    recheck = _recheck_from_template(vocabulary, notes[red], "yellow")
    platform, phase = vocabulary["card_headers"][2], vocabulary["card_headers"][5]
    assert re.search(rf"(?m)^{re.escape(phase)}{COLON}{vocabulary.one('recheck')} 1\b", recheck)
    assert delivered_reviews(_huanji_recheck_delivery(tmp_path, vocabulary, notes, recheck))
    without = re.sub(rf"\s*{DIVIDER}\s*{re.escape(platform)}{COLON}[^\n{DIVIDER}]*", "", recheck)
    assert platform not in without
    assert not delivered_reviews(_huanji_recheck_delivery(tmp_path, vocabulary, notes, without))


def test_owner_reads_real_final_files_and_private_scope_even_without_dialog_uploads(tmp_path, case):
    scenario, vocabulary, _ = case
    base, workdir, home = (tmp_path / name for name in ("base", "workdir", "home"))
    for directory in (base, workdir, home):
        directory.mkdir()
    note = "XHS-1013-05"
    path = workdir / vocabulary.one("card_folder") / f"{note}.md"
    path.parent.mkdir()
    text = _card(vocabulary, note, "red")
    path.write_text(text)
    private = home / vocabulary.one("ledger_folder") / "wrong-day.md"
    private.parent.mkdir()
    private.write_text(f"| 1999-01-01 | {note} |")
    owner = ComplianceOwner(
        scenario,
        object(),
        tmp_path / "skills",
        workdir=base,
        deliver="pool",
        workdirs={"daoqi": {"workdir": workdir, "home": home}},
    )
    present = owner._facts("daoqi", [], None)
    assert present["lights"]["given"][note]["initial"] == "red"
    assert any(key.startswith("home/") for key in present["records"]["files_outside_shared_agreed_folders"])
    exchange = _turn("Original request", _write("retained", str(path), text))
    path.unlink()
    removed = owner._facts("daoqi", [exchange], None)
    assert note not in removed["lights"]["given"]
    assert removed["written_versions"][0]["path"].startswith("workdir/")


def test_certificate_mark_obligation_is_notice_scoped_and_preserves_the_whitening_requirement(case):
    _, vocabulary, evidence = case
    sunscreen = notes_of(ROOT, "fangshai", vocabulary, evidence)["XHS-1014-05"]
    whitening = notes_of(ROOT, "meibai", vocabulary, evidence)["XHS-1104-03"]
    solar_marks = reference_of(sunscreen, vocabulary, evidence)["needs"]
    special_marks = reference_of(whitening, vocabulary, evidence)["needs"]
    assert not any(item.startswith("registration number") for item in solar_marks)
    assert any(
        item.startswith("registration number") and "exact identifier mention: missing" in item for item in special_marks
    )
    supplied_number = evidence.registrations[0].report
    corrected = reference_of(replace(whitening, text=whitening.text + "\n" + supplied_number), vocabulary, evidence)
    assert any(
        "exact identifier mention: present" in item
        for item in corrected["needs"]
        if item.startswith("registration number")
    )


@pytest.mark.parametrize("origin", ["workdir", "home"])
def test_owner_department_directory_scan_rejects_escaped_symlinks(tmp_path, case, origin):
    scenario, vocabulary, _ = case
    base, workdir, home, outside = (tmp_path / name for name in ("base", "workdir", "home", "outside"))
    for directory in (base, workdir, home, outside):
        directory.mkdir()
    note = "XHS-1013-05"
    sentinel = "Synthetic outside-root sentinel."
    (outside / f"{note}.md").write_text(_card(vocabulary, note, "red") + "\n" + sentinel)
    directory = workdir if origin == "workdir" else home
    (directory / vocabulary.one("card_folder")).symlink_to(outside, target_is_directory=True)
    owner = ComplianceOwner(
        scenario,
        object(),
        tmp_path / "skills",
        workdir=base,
        deliver="pool",
        workdirs={"daoqi": {"workdir": workdir, "home": home}},
    )
    found = owner._facts("daoqi", [], None)
    assert note not in found["lights"]["given"]
    assert f"{origin}/{vocabulary.one('card_folder')}" in found["output_coverage"]["unreadable_final_files"]
    assert sentinel not in repr(found)


def test_owner_department_directory_scan_accepts_contained_targets(tmp_path, case):
    scenario, vocabulary, _ = case
    base, workdir, home = (tmp_path / name for name in ("base", "workdir", "home"))
    for directory in (base, workdir, home):
        directory.mkdir()
    storage = workdir / "storage"
    storage.mkdir()
    note = "XHS-1013-05"
    (storage / f"{note}.md").write_text(_card(vocabulary, note, "red"))
    (workdir / vocabulary.one("card_folder")).symlink_to(storage, target_is_directory=True)
    owner = ComplianceOwner(
        scenario,
        object(),
        tmp_path / "skills",
        workdir=base,
        deliver="pool",
        workdirs={"daoqi": {"workdir": workdir, "home": home}},
    )
    found = owner._facts("daoqi", [], None)
    assert found["lights"]["given"][note]["initial"] == "red"
    assert not found["output_coverage"]["unreadable_final_files"]
