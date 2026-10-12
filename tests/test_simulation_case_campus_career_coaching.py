"""The campus career coaching case: it loads as a scenario, its plan and schedule hold together, and its owner computes
the facts a coaching lead judges a session by from resumes, records, practice answers and signing advice."""

import datetime
import re
from pathlib import Path

import pytest

from experimental.cultivation.counterpart.rulers import tables
from experimental.harness.participation.protocols import Exchange
from experimental.harness.raven_adapter.worker import Execution
from experimental.harness.scenario.contract import load
from experimental.harness.scenario.disclosure import partition
from experimental.simulation.__main__ import owner_of
from experimental.simulation.bench.scenario import BUNDLED, Scenario
from experimental.simulation.cases.campus_career_coaching.owner import (
    CareerCentreOwner,
    Vocabulary,
    card_of,
    facts,
    interview_facts,
    record_facts,
    resumes_delivered,
    rows,
)

ROOT = BUNDLED / "campus_career_coaching"
VOCABULARY = Vocabulary.load(ROOT)
WEEKDAYS = "".join(chr(code) for code in (0x4E00, 0x4E8C, 0x4E09, 0x56DB, 0x4E94, 0x516D, 0x65E5))
SEEN_ON = (chr(0x661F) + chr(0x671F), chr(0x5468))
FULL_OPEN, FULL_CLOSE = chr(0xFF08), chr(0xFF09)


def reply(text: str) -> dict:
    return {"kind": "runner.event", "event_type": "Text", "event": {"content": text}}


def write(call: str, path: str, content: str, *, mode: str | None = None, after: str | None = None) -> list[dict]:
    arguments = {"path": path, "content": content, **({"mode": mode} if mode else {})}
    done = {"phase": "complete", "tool_call_id": call, "ok": True}
    if after is not None:
        done["file_change"] = {"path": f"/work/{path}", "after": after}
    return [
        {
            "kind": "runner.event",
            "event_type": "ToolEvent",
            "event": {"phase": "start", "name": "write_file", "tool_call_id": call, "arguments": arguments},
        },
        {"kind": "runner.event", "event_type": "ToolEvent", "event": done},
    ]


def turn(user: str, text: str, *, records=(), deliver=()) -> Exchange:
    return Exchange(user, Execution("t", [], [reply(text), *records], {}, deliverables=tuple(map(str, deliver))))


def handouts(card: str) -> dict[str, str]:
    persona = next(persona for persona in Scenario.load(ROOT).personas if persona.name == card)
    return {Path(path).name: Path(path).read_text() for path in persona.files}


def slip(card: str) -> dict:
    found = {}
    for text in handouts(card).values():
        for table in tables(text):
            for row in table:
                if len(row) > 1 and row[0] in (VOCABULARY.number_label, VOCABULARY.name_label):
                    found.setdefault(row[0], row[1])
    return found


def quotes(material: str) -> list[str]:
    """The material's block quotes, each run of `>` lines joined without the markers."""
    groups, current = [], []
    for line in (ROOT / "materials" / material / "SKILL.md").read_text().splitlines():
        if line.startswith(">"):
            current.append(line[1:].strip())
        elif current:
            groups.append("\n".join(current))
            current = []
    return groups


def record_block(card: str, *, day: str | None = None, empty: bool = False) -> str:
    student = facts([], handouts(card), VOCABULARY)["student"]
    header = f"## {day or student['date']} {student['topic']}\n"
    fields = (*VOCABULARY.record_fields, *VOCABULARY.record_metadata)
    return header + "\n".join(f"- {field}: {'' if empty else 'recorded'}" for field in fields)


def test_the_case_loads_with_a_staged_plan_and_a_schedule_of_its_own_cards():
    read = load(ROOT)
    names = {case.id for case in read.situation.cases}
    assert len(read.situation.cases) == 12 and len(read.materials) == 9
    plan = read.exchange.plans["by-stage"]
    assert partition(plan.steps, read.handed) and len(plan.labels) == len(plan.steps) == 3
    assert set(read.exchange.initial) == set(plan.steps[0])
    schedule = read.situation.schedule
    assert {name for step in schedule.rounds for name in step} | set(schedule.holdout) == names
    assert schedule.rounds[2] == (schedule.rounds[0][0], schedule.rounds[0][2])
    assert schedule.holdout_rounds == (0, 1, 3) and len(schedule.holdout) == 6
    assert all(re.fullmatch(r"[a-z]+", name) for name in names)
    for case in read.situation.cases:
        assert case.expected and case.files
        assert all((ROOT / item).is_file() for item in case.files)
    twin = next(case for case in read.situation.cases if case.id.endswith("again"))
    original = next(case for case in read.situation.cases if case.id == twin.id[: -len("again")])
    assert (twin.text, twin.files, twin.expected) == (original.text, original.files, original.expected)
    assert all(read.materials[name].kind == "norm" for check in read.statements.checks for name in check.derived_from)


def test_the_bench_finds_the_case_owner():
    assert owner_of(Scenario.load(ROOT)) is CareerCentreOwner


def test_dated_weekdays_agree_with_the_calendar():
    pattern = re.compile(
        rf"(20\d\d)-(\d\d)-(\d\d)\s*[{FULL_OPEN}(](?:{'|'.join(SEEN_ON)})?([{WEEKDAYS}])[{FULL_CLOSE})]"
    )
    seen = 0
    for path in ROOT.rglob("*.md"):
        for year, month, day, weekday in pattern.findall(path.read_text()):
            seen += 1
            assert WEEKDAYS[datetime.date(int(year), int(month), int(day)).weekday()] == weekday, (path.name, day)
    assert seen >= 20


def test_the_template_example_is_the_length_it_states():
    template = (ROOT / "materials" / "resume-template" / "SKILL.md").read_text()
    example = template.split("```markdown")[-1].split("```")[0]
    stated = re.search(chr(0x8303) + chr(0x4F8B) + r"[^\n]*?(\d+) " + chr(0x884C), template)
    assert stated and rows(example, VOCABULARY) == int(stated.group(1))
    assert f"{VOCABULARY.row_limit} " in template and f"{VOCABULARY.row_width} " in template


def test_a_resume_kept_to_the_student_facts_shows_no_finding(tmp_path):
    given = handouts("yutong")
    resume_name = next(name for name in given if name.startswith(slip("yutong")[VOCABULARY.name_label] + "-"))
    resume = tmp_path / resume_name
    resume.write_text(given[resume_name])
    others = {name: text for name, text in given.items() if name != resume_name}
    found = facts([turn("ok", "ok", deliver=[resume])], others, VOCABULARY)["resume"][resume_name]
    assert found["education_first"] and found["named_by_template"]
    assert found["rows"] <= found["row_limit"]
    assert found["cpa_subjects"] == [VOCABULARY.cpa_subjects[-1]]
    assert not found["pending_wording"] and not found["unsourced_numbers"] and not found["dates_off_style"]
    assert found["role_words"] and all(hit["in_student_files"] for hit in found["role_words"])


def test_an_unrevised_draft_shows_every_kind_of_finding(tmp_path):
    given = handouts("shuyao")
    draft_name = next(name for name in given if any(mark in name for mark in VOCABULARY.draft_marks))
    draft = tmp_path / draft_name
    draft.write_text(given[draft_name])
    replies = ["2025 ... 30 ... 45", "100 ... 45"]
    exchanges = [turn(replies[0], "ok?"), turn(replies[1], "ok", deliver=[draft])]
    found = facts(exchanges, given, VOCABULARY)
    resume = found["resume"][draft_name]
    figures = {item["figure"]: item for item in resume["unsourced_numbers"]}
    assert {"100", "600", "30%"} <= set(figures) and "45" not in figures and "2025" not in figures
    assert figures["100"]["in_draft"] and figures["100"]["student_said"] == [replies[1]]
    assert figures["600"]["student_said"] == []
    assert {item["figure"] for item in resume["draft_figures_kept"]} >= {"100", "600"}
    assert any(not hit["in_student_files"] for hit in resume["role_words"])
    assert len(resume["pending_wording"]) >= 2 and resume["dates_off_style"]
    assert not resume["education_first"] and resume["rows"] > resume["row_limit"]
    report = next(text for name, text in given.items() if name.startswith("CPA"))
    passed = {row[0] for table in tables(report) for row in table if row[0] in VOCABULARY.cpa_subjects}
    assert passed < set(resume["cpa_subjects"])
    assert not resume["named_by_template"]
    assert found["process"]["questions_before_first_delivery"] == 1


def test_the_record_is_rebuilt_from_the_writes_and_read_for_its_fields(tmp_path):
    given = handouts("shuyao")
    number = slip("shuyao")[VOCABULARY.number_label]
    path = f"{VOCABULARY.records_folder}/{number}.md"
    head = f"# {number}\n"
    fields = record_block("shuyao")
    exchanges = [
        turn("a", "b", records=write("w1", path, head, after=head)),
        turn("c", "d", records=write("w2", path, fields, mode="append")),
    ]
    record = facts(exchanges, given, VOCABULARY)["records"][0]
    assert record["path"] == path and record["named_by_student_number"]
    assert record["missing_fields"] == [] and record["written_in_turns"] == [1, 2]
    assert record["dates_cited"] == ["2026-10-13"] and record["from"].startswith("rebuilt")
    partial = "\n".join(fields.splitlines()[:1] + fields.splitlines()[3:])
    misplaced = facts([turn("a", "b", records=write("w3", f"{number}.md", partial, after=partial))], given, VOCABULARY)
    assert misplaced["records"] == []
    placed = tmp_path / VOCABULARY.records_folder
    placed.mkdir()
    (placed / f"{number}.md").write_text(partial)
    kept = facts([turn("a", "b")], given, VOCABULARY, tmp_path)["records"][0]
    assert kept["from"] == "working folder" and kept["missing_fields"] == list(VOCABULARY.record_fields[:2])
    assert kept["written_in_turns"] == []


def test_a_practice_session_without_a_ready_answer_and_one_with_it():
    given = handouts("yutong")
    first, feedback, again, verification, confirmation, comparison = quotes("interview-samples")[:6]
    ready = quotes("interview-samples")[-1]
    session = [turn("hi", "?"), turn(first, feedback), turn(again, verification), turn(confirmation, comparison)]
    practice = facts(session, given, VOCABULARY)["interview"]
    assert practice["student_long_answers"] == [2, 3] and practice["model_answers"] == []
    assert practice["feedback_turns"][0]["outline_points"] == 3
    handed_answer = facts([*session[:2], turn(again, ready)], given, VOCABULARY)["interview"]
    assert [item["turn"] for item in handed_answer["model_answers"]] == [3]
    assert handed_answer["model_answers"][0]["labels"]
    assert "interview" not in facts([turn("2025 ... 30", "ok")], handouts("shuyao"), VOCABULARY)


def test_signing_facts_name_the_offices_and_the_cap():
    cap = VOCABULARY.penalty_cap
    advice = f"{VOCABULARY.desks[0]} {VOCABULARY.desks[2].replace(' ', '')} {cap[0]},{cap[1:]}"
    found = facts([turn("hi", advice)], handouts("yiming"), VOCABULARY)["signing"]
    assert found["cap_named"] and set(found["offices_named"]) == {VOCABULARY.desks[0], VOCABULARY.desks[2]}
    assert "signing" not in facts([turn("hi", advice)], handouts("shuyao"), VOCABULARY)


@pytest.mark.parametrize(
    ("session", "expected"),
    [("holdout-jiayi", "jiayi"), ("holdout-jiayiagain-2", "jiayiagain"), ("s2-zixuan", "zixuan")],
)
def test_a_session_name_leads_back_to_its_card(session, expected):
    assert card_of(session, None) == expected


def test_the_owner_hook_reads_a_held_out_card_without_a_drawn_card(tmp_path):
    owner = CareerCentreOwner(Scenario.load(ROOT), None, tmp_path / "skills", workdir=tmp_path, deliver="pool")
    found = owner._facts("holdout-jiayi", [turn("hi", "ok")], None)
    assert found["student"]["number"] == slip("jiayi")[VOCABULARY.number_label]
    assert found["records"] == [] and "resume" not in found


@pytest.mark.parametrize("outcome", [False, None, "absent", "refused"])
def test_unsuccessful_or_unknown_writes_do_not_reconstruct_a_record(outcome):
    path = f"{VOCABULARY.records_folder}/{slip('shuyao')[VOCABULARY.number_label]}.md"
    events = write("same", path, record_block("shuyao"))
    done = events[-1]["event"]
    if outcome == "absent":
        done.pop("ok")
    elif outcome == "refused":
        from experimental.harness.raven_adapter.action.runtime import REFUSED

        done["result_preview"] = REFUSED + " [probe]: declined"
    else:
        done["ok"] = outcome
    found = facts([turn("a", "b", records=events)], handouts("shuyao"), VOCABULARY)
    assert found["records"] == []
    assert found["process"]["files_written"][0]["ok"] is (False if outcome in (False, "refused") else None)


def test_captured_after_content_can_establish_an_otherwise_unreported_write():
    path = f"{VOCABULARY.records_folder}/{slip('shuyao')[VOCABULARY.number_label]}.md"
    events = write("same", path, record_block("shuyao"), after=record_block("shuyao"))
    events[-1]["event"].pop("ok")
    found = facts([turn("a", "b", records=events)], handouts("shuyao"), VOCABULARY)
    assert found["records"][0]["written_in_turns"] == [1]
    assert found["records"][0]["current_session_found"]


def test_write_call_ids_are_local_to_the_turn_and_child_execution():
    path = f"{VOCABULARY.records_folder}/{slip('shuyao')[VOCABULARY.number_label]}.md"
    successful = write("same", path, record_block("shuyao"))
    failed = write("same", path, "wrong")
    failed[-1]["event"]["ok"] = False
    child = {"kind": "child.execution", "records": failed}
    exchanges = [turn("a", "b", records=[successful[0], child, successful[1]]), turn("c", "d", records=failed)]
    found = facts(exchanges, handouts("shuyao"), VOCABULARY)
    assert found["records"][0]["written_in_turns"] == [1]
    assert found["records"][0]["current_session_found"]
    assert [item["ok"] for item in found["process"]["files_written"]] == [True, False, False]


def test_shell_created_record_uses_actual_baseline_state_instead_of_tool_name(tmp_path):
    before, placed = tmp_path / "before", tmp_path / "placed"
    before.mkdir()
    folder = placed / VOCABULARY.records_folder
    folder.mkdir(parents=True)
    (folder / f"{slip('shuyao')[VOCABULARY.number_label]}.md").write_text(record_block("shuyao"))
    known = facts([turn("a", "b")], handouts("shuyao"), VOCABULARY, placed, before)["records"][0]
    assert known["changed_this_session"] is True and known["pre_existing"] is False
    assert known["written_in_turns"] == []
    unknown = facts([turn("a", "b")], handouts("shuyao"), VOCABULARY, placed)["records"][0]
    assert unknown["pre_existing"] is None and unknown["changed_this_session"] is None


def test_existing_records_distinguish_unchanged_append_and_overwrite(tmp_path):
    before, placed = tmp_path / "before", tmp_path / "placed"
    for directory in (before, placed):
        (directory / VOCABULARY.records_folder).mkdir(parents=True)
    number = slip("shuyao")[VOCABULARY.number_label]
    old = record_block("shuyao", day="2026-09-18") + "\n"
    (before / VOCABULARY.records_folder / f"{number}.md").write_text(old)
    path = placed / VOCABULARY.records_folder / f"{number}.md"
    path.write_text(old)

    def read():
        return facts([turn("a", "b")], handouts("shuyao"), VOCABULARY, placed, before)["records"][0]

    assert read()["changed_this_session"] is False
    path.write_text(old + record_block("shuyao"))
    assert read()["changed_this_session"] is True and read()["previous_content_preserved"] is True
    path.write_text(record_block("shuyao"))
    assert read()["changed_this_session"] is True and read()["previous_content_preserved"] is False


def test_record_fields_and_dates_belong_to_the_current_block(tmp_path):
    folder = tmp_path / VOCABULARY.records_folder
    folder.mkdir()
    path = folder / f"{slip('shuyao')[VOCABULARY.number_label]}.md"
    path.write_text(record_block("shuyao", day="2026-09-18") + "\n" + record_block("shuyao", empty=True))
    record = facts([], handouts("shuyao"), VOCABULARY, tmp_path)["records"][0]
    assert record["current_session_found"] and record["session_type_matches"]
    assert not record["missing_fields"]
    assert record["empty_fields"] == [*VOCABULARY.record_fields, *VOCABULARY.record_metadata]
    assert record["dates_cited"] == ["2026-10-13"] and record["previous_session"] == ""
    path.write_text(record_block("shuyao", day="2026-09-18") + "\n" + record_block("shuyao").splitlines()[0])
    record = facts([], handouts("shuyao"), VOCABULARY, tmp_path)["records"][0]
    assert record["missing_fields"] == [*VOCABULARY.record_fields, *VOCABULARY.record_metadata]


def test_the_adopted_complete_record_example_has_current_fields_and_identity():
    source = (ROOT / "materials" / "consult-records" / "SKILL.md").read_text()
    example = source.split("```markdown")[2].split("```")[0].strip()
    number = "2023210388"
    student = {
        "number": number,
        "name": example.splitlines()[0].split(number, 1)[1].strip(),
        "date": "2026-09-14",
        "topic": VOCABULARY.resume_topic,
    }
    record = record_facts(
        {f"{VOCABULARY.records_folder}/{number}.md": {"content": example, "turns": [1], "pre_existing": False}},
        student,
        VOCABULARY,
        "captured record",
    )[0]
    assert record["identity_matches"] and record["current_session_found"] and record["session_type_matches"]
    assert record["missing_fields"] == record["empty_fields"] == record["missing_identity_fields"] == []


def test_unknown_edit_content_does_not_claim_missing_record_fields():
    path = f"{VOCABULARY.records_folder}/{slip('shuyao')[VOCABULARY.number_label]}.md"
    events = write("edit", path, "proposed")
    events[0]["event"]["name"] = "edit_file"
    events[0]["event"]["arguments"] = {"path": path, "old_text": "old", "new_text": "new"}
    record = facts([turn("a", "b", records=events)], handouts("shuyao"), VOCABULARY)["records"][0]
    assert record["written_in_turns"] == [1]
    assert not record["content_available"]
    assert record["missing_fields"] is None and record["current_session_found"] is None


def test_absent_record_in_retained_workdir_is_not_replaced_by_write_arguments(tmp_path):
    path = f"{VOCABULARY.records_folder}/{slip('shuyao')[VOCABULARY.number_label]}.md"
    record = facts(
        [turn("a", "b", records=write("other-location", path, record_block("shuyao")))],
        handouts("shuyao"),
        VOCABULARY,
        tmp_path,
    )
    assert record["records"] == []


def test_ready_answer_scan_includes_upfront_short_answers_and_excludes_only_prior_quotations():
    ready = quotes("interview-samples")[-1]
    upfront = interview_facts([ready, "done"], ["hi", ready], VOCABULARY)
    assert upfront["model_answers"] and upfront["model_answers"][0]["turn"] == 1
    short = VOCABULARY.answer_marks[0] + ": I chose auditing because I enjoy verifying records."
    assert interview_facts([short], ["hi"], VOCABULARY)["model_answers"]
    assert interview_facts([short], ["hi"], VOCABULARY)["student_long_answers"] == []
    assert interview_facts([ready], [ready], VOCABULARY)["model_answers"] == []


def test_resume_facts_keep_distinct_delivery_versions_and_mark_reused_paths_unknown(tmp_path):
    given = handouts("yutong")
    name = next(name for name in given if name.startswith(slip("yutong")[VOCABULARY.name_label] + "-"))
    paths = [tmp_path / directory / name for directory in ("first", "second")]
    for path in paths:
        path.parent.mkdir()
        path.write_text(given[name])
    paths[0].write_text(given[name] + "\n" + VOCABULARY.pending_terms[0])
    exchanges = [turn("hi", "a", deliver=[paths[0]]), turn("later", "b", deliver=[paths[1]])]
    versions = facts(exchanges, given, VOCABULARY)["resume_versions"]
    assert [version["turn"] for version in versions] == [1, 2]
    assert versions[0]["sha256"] != versions[1]["sha256"]
    assert versions[0]["facts"]["pending_wording"] and not versions[1]["facts"]["pending_wording"]
    repeated = facts([turn("hi", "a", deliver=[paths[1]]), turn("later", "b", deliver=[paths[1]])], given, VOCABULARY)
    assert not repeated["resume_versions"][0]["content_available"]
    assert repeated["resume_versions"][1]["content_available"]


def test_case_delivery_predicate_requires_only_source_bound_resume_obligations(tmp_path):
    from experimental.simulation.bench.value import delivered_for

    assert delivered_for("campus_career_coaching") is resumes_delivered
    given = handouts("yutong")
    name = next(name for name in given if name.startswith(slip("yutong")[VOCABULARY.name_label] + "-"))
    path = tmp_path / name
    path.write_text(given[name])
    references = facts([turn("hi", "a", deliver=[path])], given, VOCABULARY)
    delivered = {"name": name, "path": str(path), "sha256": references["resume_versions"][0]["sha256"]}
    resume = {"card": "shuyao", "exchanges": [{"delivered": [delivered]}], "references": references}
    advice = [{"card": card, "exchanges": [], "references": {}} for card in ("yutong", "yiming", "shiqi")]
    assert resumes_delivered({"drills": [resume, *advice]})
    assert resumes_delivered({"drills": advice})
    assert not resumes_delivered({"drills": [{**resume, "exchanges": []}, *advice]})
    assert not resumes_delivered(
        {"drills": [{**resume, "references": {"student": {"topic": VOCABULARY.practice_topic}}}]}
    )
    assert not resumes_delivered({"drills": [{"card": "unknown", "references": references}]})
    assert not resumes_delivered({"drills": []})
    delivered["sha256"] = "wrong"
    assert not resumes_delivered({"drills": [resume]})


def test_delivery_obligations_use_verified_frozen_catalog_instead_of_current_catalog(tmp_path, monkeypatch):
    import shutil

    from experimental.harness.scenario.digest import digest
    from experimental.simulation.bench.value import _delivery_check
    from experimental.simulation.cases.campus_career_coaching import owner

    frozen, current = tmp_path / "frozen", tmp_path / "current"
    for directory in (frozen, current):
        shutil.copytree(ROOT, directory, ignore=shutil.ignore_patterns("__pycache__"))
    persona = next(persona for persona in Scenario.load(ROOT).personas if persona.name == "shuyao")
    appointment = persona.files[0].relative_to(ROOT)
    original = (current / appointment).read_text()
    row = f"| {VOCABULARY.topic_label} | {VOCABULARY.resume_topic} |"
    assert row in original
    (current / appointment).write_text(
        original.replace(row, f"| {VOCABULARY.topic_label} | {VOCABULARY.practice_topic} |")
    )
    monkeypatch.setattr(owner, "__file__", str(current / "owner.py"))
    item = {"drills": [{"card": "shuyao", "exchanges": [], "references": {}}]}
    assert resumes_delivered({**item, "scenario_root": str(current)})
    record = {
        "run": {
            "scenario": "campus_career_coaching",
            "scenario_source": str(frozen),
            "settings": {"scenario_digest": digest(frozen), "scenario_digest_format": "source-v2"},
        }
    }
    bound = _delivery_check(record, {**item, "scenario_root": str(current)})
    assert bound["verified"] is True and bound["ok"] is False
    advice = {"drills": [{"card": "yutong", "exchanges": [], "references": {}}]}
    assert _delivery_check(record, advice)["ok"] is True
    (frozen / appointment).write_text("changed source")
    changed = _delivery_check(record, item)
    assert changed["verified"] is False and "source is unavailable or changed" in changed["detail"]
    (frozen / appointment).write_text(original)
    with (frozen / "owner.py").open("a") as source:
        source.write("\n# Archived source differs.\n")
    record["run"]["settings"]["scenario_digest"] = digest(frozen)
    mismatch = _delivery_check(record, item)
    assert mismatch["verified"] is False and "owner source differs" in mismatch["detail"]


def test_declared_applicability_reaches_owner_without_exempting_required_records(tmp_path):
    from experimental.cultivation.counterpart.owner import handles
    from experimental.harness.assessor.standard import Standard

    contract = load(ROOT)
    conditional = {
        "resume-facts-sourced",
        "resume-role-wording",
        "certificate-column",
        "layout-one-page",
        "fact-base-before-rewrite",
        "interview-practice-loop",
        "no-ready-answer",
        "signing-and-safety",
    }
    assert {check.id for check in contract.statements.checks if check.applies_when} == conditional
    declared = Standard.declared(
        ((check.id, check.check) for check in contract.statements.checks),
        applies_when={check.id: check.applies_when for check in contract.statements.checks},
    )
    assert {check.id: check.definition.applies_when for check in declared.criteria} == {
        check.id: check.applies_when for check in contract.statements.checks
    }
    owner = CareerCentreOwner(Scenario.of(contract), None, tmp_path / "skills", workdir=tmp_path, deliver="pool")
    assert {check.id: check.applies_when for check in owner.scenario.criteria} == {
        check.id: check.applies_when for check in contract.statements.checks
    }
    named = handles(owner.scenario.criteria)
    verdicts = [{"id": handle, "result": "unknown"} for handle in named.values()]
    signing = next(verdict for verdict in verdicts if verdict["id"] == named["signing-and-safety"])
    signing.update(
        {
            "result": "not_applicable",
            "note": "The supplied resume request and its handouts raise no signing or fee work.",
        }
    )
    submission = {"verdicts": verdicts, "remark": "Review complete.", "handover": []}
    sessions = {"shuyao": [turn("Please revise my resume.", "What did the internship involve?")]}
    review = owner._parse(sessions, submission, list(named.values()))
    assert (
        next(verdict for verdict in review.verdicts if verdict.id == named["signing-and-safety"]).result
        == "not_applicable"
    )
    signing["note"] = ""
    with pytest.raises(ValueError, match="evidenced explanation"):
        owner._parse(sessions, submission, list(named.values()))
    signing.update({"result": "unknown", "note": ""})
    record = next(verdict for verdict in verdicts if verdict["id"] == named["consult-record-kept"])
    record.update({"result": "not_applicable", "note": "No record was delivered."})
    with pytest.raises(ValueError, match="unconditional"):
        owner._parse(sessions, submission, list(named.values()))
