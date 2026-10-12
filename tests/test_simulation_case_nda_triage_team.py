"""Offline NDA contract, retained-file, action-provenance and source-bound delivery regressions.

These checks verify their declared mechanical conditions, not the correctness of untested semantic owner verdicts.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from experimental.harness.participation.protocols import Exchange, Execution
from experimental.harness.raven_adapter.action.runtime import REFUSED
from experimental.harness.scenario.contract import load
from experimental.harness.scenario.disclosure import partition
from experimental.simulation.__main__ import owner_of
from experimental.simulation.bench.scenario import BUNDLED, Scenario
from experimental.simulation.cases.nda_triage_team.owner import (
    DELIVERED,
    NdaOwner,
    Vocabulary,
    calls,
    change_rows,
    clause_numbers,
    expected_of,
    facts,
    memo_facts,
    registration_number,
    relative_path,
    rows_for,
    same_clause,
)

NAME = "nda_triage_team"
ROOT = BUNDLED / NAME


def scenario() -> Scenario:
    return Scenario.load(NAME)


def vocabulary() -> Vocabulary:
    return Vocabulary.load(scenario())


def card(name: str):
    return next(persona for persona in scenario().personas if persona.name == name)


def call(name, arguments, number, ok=True):
    return [
        {
            "kind": "runner.event",
            "event_type": "ToolEvent",
            "event": {"phase": "start", "name": name, "arguments": arguments, "tool_call_id": f"c{number}"},
        },
        {
            "kind": "runner.event",
            "event_type": "ToolEvent",
            "event": {"phase": "complete", "tool_call_id": f"c{number}", "ok": ok},
        },
    ]


def turn(reply, records=(), files=()):
    rows = [{"kind": "runner.event", "event_type": "Text", "event": {"content": reply}}, *records]
    return Exchange("request", Execution("t1", [], rows, {}, "a", tuple(str(path) for path in files)))


def memo(words: Vocabulary, first: str, clauses, *, version="V2.3", mark=True) -> str:
    rows = "\n".join(f"| {number} | x | y | z | w |" for number in clauses)
    head = words.internal_notices[0] if mark else "memo"
    return (
        f"{first}\n{head}\n- basis: playbook {version}\n\n"
        f"| {' | '.join(words.issue_columns)} |\n|---|---|---|---|---|\n{rows}\n"
    )


def snapshot_rows() -> list[str]:
    text = (ROOT / "materials" / "nda-register" / "SKILL.md").read_text()
    return [line for line in text.splitlines() if line.startswith("| NDA-2026-0")]


def test_the_case_loads_with_its_owner_schedule_and_partitioned_plan():
    read = load(ROOT)
    assert len(read.situation.cases) == 12 and len(read.materials) == 9
    assert owner_of(scenario()) is NdaOwner
    schedule = read.situation.schedule
    assert schedule.rounds[0] == ("kestrel", "lindqvist", "harbourline")
    assert schedule.rounds[2] == ("kestrel", "harbourline")
    assert len(schedule.holdout) == 6 and schedule.holdout_rounds == (0, 1, 3)
    names = {case.id for case in read.situation.cases}
    assert {name for step in schedule.rounds for name in step} | set(schedule.holdout) <= names
    plan = read.exchange.plans["by-stage"]
    assert partition(plan.steps, read.handed) and len(plan.labels) == len(plan.steps)
    assert set(read.exchange.initial) == set(plan.steps[0])
    assert {check.id for check in read.statements.checks} and len(read.statements.checks) == 11
    assert all(set(check.derived_from) <= set(read.statements.norms) for check in read.statements.checks)


def test_every_card_hands_over_existing_files_and_states_an_expected_answer():
    read = load(ROOT)
    for case in read.situation.cases:
        assert case.files and all((ROOT / item).is_file() for item in case.files)
        fields = expected_of(case)
        assert fields.get("verdict") in ("GREEN", "YELLOW", "RED"), case.id
        assert "issues" in fields and "next" in fields and "register" in fields, case.id
        assert case.id.isalpha() and case.id.islower()
    twin = {case.id: case for case in read.situation.cases}
    assert twin["southerlyagain"].files == twin["southerly"].files
    assert twin["southerlyagain"].expected == twin["southerly"].expected


def test_clause_numbers_are_read_as_the_counterparty_writes_them():
    article, clause = chr(0x7B2C), chr(0x6761)
    assert clause_numbers("7.2(b)") == ["7.2(b)"]
    assert clause_numbers(f"{article} 5 {clause}") == ["5"]
    assert clause_numbers("Section 12.6") == ["12.6"]
    assert clause_numbers("Article 7") == ["7"]
    assert clause_numbers("3(d)") == ["3(d)"] and clause_numbers("none") == []
    assert not same_clause("3", "3(d)") and not same_clause("8.1", "8") and not same_clause("1", "12")
    assert same_clause("Section 3(d)", "3(d)") and clause_numbers("page 7") == []


def test_a_red_drill_retains_file_and_operation_facts(tmp_path):
    words = vocabulary()
    delivered = tmp_path / "memo-kestrel-v1.md"
    delivered.write_text(memo(words, "RED", ["5", "7", "9", "11"]))
    row = "| NDA-2026-087 | v1 | 2026-10-12 | Kestrel Ridge Solutions, Inc. | x | y | RED | 5, 7, 9, 11 | z | - | NDA-2026-087-SJ1 | f.md |"
    register = "\n".join([*snapshot_rows(), row])
    records = [
        *call(
            "spawn",
            {"subagent": "commercial-contracts-counsel", "node_id": "nda-kestrel", "task_summary": "NDA review"},
            1,
        ),
        *call("write_file", {"path": f"/runs/r1/workdir/{words.register}", "content": register}, 2),
        *call(
            "write_file", {"path": f"/runs/r1/workdir/{words.notes_folder}/NDA-2026-087-SJ1.md", "content": "# note"}, 3
        ),
    ]
    records.append(
        {
            "kind": "child.execution",
            "harness": "commercial-contracts-counsel",
            "instances": [{"agent": "commercial-contracts-counsel", "nodeId": "nda-kestrel"}],
            "records": [
                {"kind": "runner.event", "event_type": "Text", "event": {"content": "Contracts review completed"}}
            ],
        }
    )
    exchanges = [turn("RED: escalated.", records, files=[delivered])]
    found = facts(
        exchanges,
        words,
        card("kestrel"),
        live=register_text([row]),
        base=register_text(),
        notes={f"{words.notes_folder}/NDA-2026-087-SJ1.md": "# note"},
        base_notes={},
        observed=True,
        workdir=Path("/runs/r1/workdir"),
    )
    one = next(iter(found["memos"].values()))
    assert one["colour"] == "RED" and one["first_line_is_only_the_colour"]
    assert one["internal_mark"] and one["playbook_version_in_force_named"] and not one["superseded_versions_named"]
    check = found["expected_check"]
    assert check["verdict"] == "RED" and check["missing"] == [] and check["extra"] == []
    assert found["register"]["writes"][0]["live_register"] is True
    assert len(found["register"]["rows_added"]) == 1 and "NDA-2026-087" in found["register"]["rows_added"][0]
    assert list(found["escalation_notes"]) == [f"{words.notes_folder}/NDA-2026-087-SJ1.md"]
    assert found["desks"] == {"contract": 1, "other": 0, "unclear": 0}


def test_a_non_compliant_drill_shows_each_miss(tmp_path):
    words = vocabulary()
    delivered = tmp_path / "memo.md"
    delivered.write_text(memo(words, "# Verdict: GREEN", ["5", "7", "3"], version="V2.2", mark=False))
    claim = f"GREEN, {words.sign_claims[0]}."
    records = [
        *call("spawn", {"subagent": "privacy-data-counsel", "node_id": "pi", "task_summary": "data check"}, 1),
        *call(
            "run_subagent_dag",
            {
                "nodes": [
                    {"id": "ip", "subagent": "ip-portfolio-counsel", "node_summary": "IP"},
                    {"id": "nda", "subagent": "Raven"},
                ]
            },
            2,
        ),
        *call(
            "write_file",
            {"path": f"/runs/r1/workdir/uploads/nda-register/{Path(words.register).name}", "content": "| new |"},
            3,
        ),
    ]
    found = facts([turn(claim, records, files=[delivered])], words, card("kestrel"))
    one = next(iter(found["memos"].values()))
    assert one["colour"] is None and one["first_line"].endswith("GREEN")
    assert not one["internal_mark"] and one["superseded_versions_named"] == ["V2.2"]
    check = found["expected_check"]
    assert check["missing"] == ["9", "11"] and check["extra"] == ["3"]
    assert found["register"]["writes"][0]["live_register"] is None
    assert found["desks"] == {"contract": 0, "other": 0, "unclear": 0}
    assert [one["desk"] for one in found["delegations"]] == ["other", "other", "unclear"]
    assert found["sign_lines"] and found["colours_in_replies"]["message 1"]["GREEN"] == [claim]
    assert "escalation_notes" not in found


def test_a_returned_version_is_measured_by_its_changes(tmp_path):
    words = vocabulary()
    delivered = tmp_path / "memo-v2.md"
    delivered.write_text(memo(words, "YELLOW", ["3(d)", "4"]) + comparison(words, ["3(d)", "6", "9", "12"]))
    found = facts([turn("YELLOW", files=[delivered])], words, card("fernhill"))
    check = found["expected_check"]
    assert check["changed"] == ["3(d)", "6", "9", "12"] and check["issues"] == ["3(d)"]
    assert check["cited_unchanged"] == ["4"] and check["changed_not_cited"] == [] and check["extra"] == ["4"]
    blind = tmp_path / "memo-blind.md"
    blind.write_text(memo(words, "GREEN", []) + comparison(words, ["6", "9", "12"]))
    check = facts([turn("GREEN", files=[blind])], words, card("fernhill"))["expected_check"]
    assert check["missing"] == ["3(d)"] and check["changed_not_cited"] == ["3(d)"]


def test_facts_without_a_card_or_anything_found_stay_small():
    words = vocabulary()
    assert facts([turn("hello")], words, None) == {}
    assert "expected_check" not in facts([turn("RED")], words, SimpleNamespace(expected=None))


def test_the_owner_reads_the_replica_register_and_notes(tmp_path):
    words = vocabulary()
    own, replica = tmp_path / "own", tmp_path / "replica"
    for place in (own, replica):
        (place / Path(words.register).parent).mkdir(parents=True)
    (own / words.register).write_text(register_text())
    added = "| NDA-2026-087 | v1 | 2026-10-12 | Pacific Lantern Retail Holdings Limited | x | y | YELLOW | 8, 12.4 | z | - | s | f |"
    pending = "| LD-2026-05 | 2026-10-12 | audit | NDA-2026-087 / 8 | x | NDA-2026-087-SJ1 | open | - | - | - |"
    (replica / words.register).write_text(register_text([added], [pending]))
    (replica / words.notes_folder).mkdir(parents=True)
    (replica / words.notes_folder / "NDA-2026-087-SJ1.md").write_text("# note 8 and 12.4")
    owner = NdaOwner(scenario(), None, tmp_path / "skills", workdir=own, uploads=tmp_path / "home" / "uploads")
    owner.workdirs["s2-lantern"] = {"workdir": str(replica), "home": str(tmp_path / "home")}
    found = owner._facts("s2-lantern", [turn("YELLOW")], card("lantern"))
    assert len(found["register"]["rows_added"]) == 2 and len(found["register"]["pending_rows_added"]) == 1
    assert list(found["escalation_notes"]) == [f"{words.notes_folder}/NDA-2026-087-SJ1.md"]
    assert "unavailable" in next(
        iter(owner._facts("holdout-lotusgate", [turn("hello")], None)["archive_observation"].values())
    )


def test_returned_memos_accept_the_recheck_mark():
    words = vocabulary()
    text = memo(words, "YELLOW", ["3(d)"]).replace(words.internal_mark, words.internal_marks[1])
    assert memo_facts(text, words)["internal_mark"] is True


def test_failed_and_export_register_writes_are_not_saved_rows():
    words = vocabulary()
    row = "| NDA-2026-087 | v1 | RED |"
    records = [
        *call("write_file", {"path": words.register, "content": row}, 1, ok=False),
        *call("write_file", {"path": f"uploads/{words.register}", "content": row}, 2),
    ]
    found = facts([turn("done", records)], words, card("kestrel"))["register"]
    assert "rows_added" not in found and found["observability"] == "unobserved final state"
    assert found["expected_registration_number"] == "NDA-2026-087"


def test_completed_refusal_does_not_save_a_register_or_escalation_note():
    words = vocabulary()
    records = call("write_file", {"path": words.register, "content": "| NDA-2026-087 | v1 | RED |"}, 1)
    records[-1]["event"]["result_preview"] = REFUSED + "no write occurred"
    refused_note = call("write_file", {"path": f"{words.notes_folder}/note.md", "content": "submitted"}, 2)
    refused_note[-1]["event"]["result_preview"] = REFUSED + "no write occurred"
    found = facts([turn("done", [*records, *refused_note])], words, card("kestrel"))
    assert "rows_added" not in found["register"] and "escalation_notes" not in found


def test_new_number_follows_live_baseline_and_returned_number_is_retained():
    words = vocabulary()
    baseline = register_text(
        [
            "| NDA-2026-102 | v1 | 2026-10-12 | New Company | initiator | counterparty text | RED | 5 | escalated | none | note | memo | "
        ]
    )
    assert registration_number(words, card("kestrel"), baseline) == "NDA-2026-103"
    assert registration_number(words, card("fernhill"), baseline) == "NDA-2026-079"


def test_member_group_is_not_inferred_from_the_task_summary():
    words = vocabulary()
    records = call(
        "spawn",
        {"subagent": "commercial-contracts-counsel", "task_summary": "privacy-data-counsel is not needed"},
        1,
    )
    assert facts([turn("done", records)], words)["delegations"][0]["desk"] == "contract"
    assert facts([turn("done", records)], words)["delegations"][0]["execution_verified"] is False


def test_external_change_request_reports_internal_content(tmp_path):
    words = vocabulary()
    path = tmp_path / f"{words.external_mark}-changes.md"
    path.write_text(f"Section 8: {words.colours[1]} {words.internal_words[0]}")
    found = facts([turn("attached", files=[path])], words)
    assert set(next(iter(found["external_request_leaks"].values()))["literal_hits"]) >= {
        words.colours[1],
        words.internal_words[0],
    }


def register_text(added=(), pending=()):
    words = vocabulary()
    source = (ROOT / "materials/nda-register/SKILL.md").read_text()
    main = rows_for(source, words.register_columns)
    deferred = rows_for(source, words.pending_columns)
    return (
        f"| {' | '.join(words.register_columns)} |\n|"
        + "---|" * len(words.register_columns)
        + "\n"
        + "\n".join("| " + " | ".join(row) + " |" for row in main)
        + "\n"
        + "\n".join(added)
        + f"\n\n| {' | '.join(words.pending_columns)} |\n|"
        + "---|" * len(words.pending_columns)
        + "\n"
        + "\n".join("| " + " | ".join(row) + " |" for row in deferred)
        + "\n"
        + "\n".join(pending)
    )


def comparison(words, clauses):
    return f"\n| {' | '.join(words.change_columns)} |\n|---|---|---|---|\n" + "".join(
        f"| {number} | Previous wording | Actual changed wording | New issue |\n" for number in clauses
    )


def delivered_fixture(tmp_path, name, *, external=None):
    words = vocabulary()
    selected = card(name)
    fields = expected_of(selected)
    current = "v2" if name in ("fernhill", "thamesgate") else "v1"
    reg = "NDA-2026-079" if name == "fernhill" else "NDA-2026-084" if name == "thamesgate" else "NDA-2026-087"
    company = fields["counterparty"].split(" (register", 1)[0]
    head = words.internal_notices[1 if current == "v2" else 0]
    text = (
        f"{fields['verdict']}\n{head}\n"
        f"- {words.counterpart_labels[0]}: {company} (counterparty text, {current}, received 2026-10-12)\n"
        f"- {words.basis_labels[0]}: playbook V2.3; clause bank V1.6\n"
        f"- {words.handler_labels[0]}: commercial-contracts-counsel | {reg} | 2026-10-12\n\n"
        f"{words.section_labels['conclusion'][0]}: The current policy verdict is {fields['verdict']}.\n"
        f"{words.section_labels['background'][0]}: Business cooperation; no personal information unless verified.\n"
        f"{words.section_labels['next'][0]}: Follow the policy route; no unpublished disclosure before execution.\n"
        f"{words.section_labels['record'][0]}: {reg}; follow the recorded escalation requirements.\n\n"
    )
    positions = (
        {}
        if fields["positions"] == "none"
        else dict(part.strip().split("=") for part in fields["positions"].split(","))
    )
    if positions:
        text += f"| {' | '.join(words.issue_columns)} |\n|---|---|---|---|---|\n"
        for number, policy in positions.items():
            basis = words.uncovered_basis[0] if policy == "uncovered" else f"playbook {policy}"
            proposed = "Director position awaited" if policy == "uncovered" else f"Use clause bank {policy}-P"
            text += f"| {number} | Actual counterparty clause differs from policy | {basis} | {proposed} | Required approver decides deviations |\n"
    if not positions:
        text += f"{words.problem_labels[0]}: {words.none_labels[0]}\n{words.checked_labels[0]}: Mutuality, definitions and exclusions, survival, residuals, employee restrictions, personal data, AI training, and governing law/dispute resolution meet the playbook.\n"
    if fields.get("changed"):
        text += f"\n| {' | '.join(words.change_columns)} |\n|---|---|---|---|\n"
        for number in fields["changed"].split(", "):
            judgment = "New issue (YELLOW)" if number in positions else "Resolved"
            text += f"| {number} | Previous clause | Current changed clause | {judgment} |\n"
    path = tmp_path / f"{words.memo_prefix}-{name.title()}-{current}.md"
    path.write_text(text)
    files = [path]
    if external is not None:
        path = tmp_path / f"{words.external_prefix}-{name.title()}-{current}-{words.external_mark}.md"
        path.write_text(external)
        files.append(path)
    import hashlib

    return {
        "scenario_root": str(ROOT),
        "delivery_root": str(tmp_path),
        "drills": [
            {
                "card": name,
                "exchanges": [
                    {
                        "turn_id": "retained-t1",
                        "delivered": [
                            {
                                "name": path.name,
                                "path": path.name,
                                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                            }
                            for path in files
                        ],
                    }
                ],
            }
        ],
    }


def test_header_measures_physical_lines_and_actual_policy_basis():
    words = vocabulary()
    valid = memo(words, "RED", ["5"])
    assert memo_facts(valid, words)["internal_mark"]
    assert not memo_facts("\n" + valid, words)["first_line_is_only_the_colour"]
    assert not memo_facts(" RED \n" + valid.split("\n", 1)[1], words)["first_line_is_only_the_colour"]
    assert not memo_facts(valid.replace("V2.3", "V2.30"), words)["playbook_version_in_force_named"]
    historical = memo_facts(valid + "\nPrevious review used V2.2.\n", words)
    assert historical["playbook_version_in_force_named"] and historical["superseded_versions_named"] == []
    footer_mark = "RED\nMemo\n- basis: playbook V2.3\n\n" + words.internal_notices[0]
    assert not memo_facts(footer_mark, words)["internal_mark"]


def test_comparison_only_cannot_supply_a_required_problem_row(tmp_path):
    words = vocabulary()
    path = tmp_path / "comparison.md"
    path.write_text(memo(words, "YELLOW", []) + comparison(words, ["3(d)", "6", "9", "12"]))
    found = facts([turn("YELLOW", files=[path])], words, card("fernhill"))
    assert found["expected_check"]["missing"] == ["3(d)"]
    assert found["expected_check"]["changed_not_cited"] == []
    assert len(change_rows(path.read_text(), words)) == 4


def test_outcomes_do_not_cross_turns_children_or_repeated_ids():
    first = turn("blocked", call("write_file", {"path": "register.md"}, 1, ok=False))
    second = turn("done", call("write_file", {"path": "unrelated.md"}, 1))
    assert [item["ok"] for item in calls([first, second])] == [False, True]
    missing = call("write_file", {"path": "unknown.md"}, 2)
    missing[-1]["event"].pop("ok")
    assert calls([turn("", missing)])[0]["ok"] is None
    child = {
        "kind": "child.execution",
        "harness": "commercial-contracts-counsel",
        "records": call("write_file", {"path": "child.md"}, 1),
    }
    together = calls([turn("", [*call("write_file", {"path": "parent.md"}, 1, ok=False), child])])
    assert [item["ok"] for item in together] == [False, True]
    assert together[0]["actor"] != together[1]["actor"]


def test_successful_write_arguments_are_not_final_register_state():
    words = vocabulary()
    for outcome in (True, False, None):
        records = call("write_file", {"path": words.register, "content": "| NDA-2026-087 | v1 | RED |"}, 1, ok=outcome)
        found = facts([turn("registered", records)], words, card("kestrel"))
        assert "rows_added" not in found["register"]
        assert found["register"]["observability"] == "unobserved final state"
        assert found["operations"][0]["ok"] is outcome


def test_paths_and_live_observations_do_not_promote_other_folders(tmp_path):
    words = vocabulary()
    assert relative_path("archive/" + words.register, tmp_path) != words.register
    assert relative_path("uploads/" + words.notes_folder + "/note.md", tmp_path) != words.notes_folder + "/note.md"
    assert relative_path("../outside.md", tmp_path) is None
    assert relative_path("/outside/" + words.register, tmp_path) is None
    owner = NdaOwner(scenario(), None, tmp_path / "skills", workdir=tmp_path / "own", uploads=tmp_path / "home/uploads")
    owner.workdirs["kestrel"] = {"workdir": str(tmp_path / "missing"), "home": str(tmp_path / "home")}
    found = owner._facts("kestrel", [turn("registered")], card("kestrel"))
    assert found["register"]["observability"] == "unobserved final state"
    assert "unavailable" in found["register"]["observation"]["register"]
    assert "escalation_notes" not in found


def test_full_current_note_is_distinct_from_inherited_note(tmp_path):
    words = vocabulary()
    own, replica = tmp_path / "own", tmp_path / "replica"
    own.mkdir()
    replica.mkdir()
    for place in (own, replica):
        (place / words.notes_folder).mkdir(parents=True)
        (place / words.notes_folder / "old.md").write_text("Earlier unrelated note")
    note = "Business details. " * 40 + "\nSubmit to legal director Xu Qing; section 5 pushback remains unresolved.\n"
    path = replica / words.notes_folder / "NDA-2026-087-SJ1.md"
    path.write_text(note)
    owner = NdaOwner(scenario(), None, tmp_path / "skills", workdir=own, uploads=tmp_path / "home/uploads")
    owner.workdirs["kestrel"] = {"workdir": str(replica), "home": str(tmp_path / "home")}
    found = owner._facts("kestrel", [turn("escalated")], card("kestrel"))
    assert found["escalation_notes"] == {str(path.relative_to(replica)): note}
    assert found["note_inventory"][words.notes_folder + "/old.md"]["changed"] is False
    assert found["note_provenance"][str(path.relative_to(replica))]["change"] == "new"


def test_failed_delegation_and_substring_alias_are_not_completed_contract_work():
    words = vocabulary()
    records = call("spawn", {"subagent": "privacy-data-counsel", "node_id": "privacy"}, 1, ok=False)
    records += call("spawn", {"subagent": "pretend-commercial-contracts-counsel", "node_id": "nda"}, 2)
    found = facts([turn("", records)], words)
    assert found["delegations"][0]["ok"] is False
    assert found["desks"]["other"] == 0
    assert found["delegations"][1]["desk"] == "unclear"


def test_context_includes_filed_director_wording_and_external_presentation(tmp_path):
    words = vocabulary()
    path = tmp_path / "changes.md"
    path.write_text("YELLOW. " + words.internal_words[0])
    found = facts(
        [turn("changes.md: forward to the counterparty", files=[path])],
        words,
        filed={"workdir/note.md": "No authority to propose: " + " ".join(words.director_only)},
    )
    assert found["external_request_leaks"]
    assert "filed workdir/note.md" in found["director_only_wording"]
    english = facts([turn("Future signer Han Dong, only after the director decision")], words)
    assert words.signers[-1] in english["signers_named"]


def test_each_delivered_version_keeps_its_own_issue_rows(tmp_path):
    words = vocabulary()
    first = tmp_path / "first/memo.md"
    second = tmp_path / "second/memo.md"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_text(memo(words, "RED", ["5", "7"]))
    second.write_text(memo(words, "RED", ["9", "11"]))
    found = facts([turn("", files=[first]), turn("", files=[second])], words, card("kestrel"))
    checks = list(found["expected_check"]["per_memo"].values())
    assert len(found["memos"]) == 2
    assert checks[0]["missing"] == ["9", "11"]
    assert checks[1]["missing"] == ["5", "7"]


def test_native_same_turn_deliveries_keep_every_memo_occurrence(tmp_path):
    import hashlib

    from experimental.harness.assessor.standard import observations
    from experimental.harness.raven_adapter.observe import Recorder
    from experimental.harness.raven_adapter.worker import Worker

    words = vocabulary()
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    path = workdir / "memo.md"
    recorder = Recorder(tmp_path / "employee/generation/observations.jsonl")
    recorder.delivery_roots = (workdir, tmp_path / "employee")
    recorder.turn_id = "same-turn"
    contents = [memo(words, "GREEN", ["5", "7"]), memo(words, "RED", ["9", "11"])]
    for ordinal, content in enumerate(contents, 1):
        path.write_text(content)
        recorder.add(
            "runner.event",
            event_type="ToolEvent",
            event={
                "phase": "complete",
                "tool_call_id": f"d{ordinal}",
                "ok": True,
                "metadata": {"raven_delivery": {"files": [{"path": str(path)}]}},
            },
        )
    for outcome in (False, None, "true"):
        recorder.add(
            "runner.event",
            event_type="ToolEvent",
            event={
                "phase": "complete",
                "ok": outcome,
                "metadata": {"raven_delivery": {"files": [{"path": str(path)}]}},
            },
        )
    proxy = SimpleNamespace(
        root=tmp_path / "run", area=tmp_path / "employee", baseline=SimpleNamespace(workdir=workdir)
    )
    kept = Worker._keep_deliverables(proxy, "same-turn", recorder.rows)
    exchange = Exchange("Review Kestrel NDA", Execution("same-turn", [], recorder.rows, {}, "actual-revision", kept))
    measured = facts([exchange], words, card("kestrel"))
    packet = observations({"kestrel": [exchange]})
    packet["references"] = {"kestrel": measured}
    retained = list(packet["references"]["kestrel"]["delivered_files"].values())
    assert len(kept) == len(measured["memos"]) == len(retained) == 2
    assert [item["text"] for item in retained] == contents
    assert [item["ordinal"] for item in retained] == [1, 2]
    assert all(item["turn"] == 1 and item["execution_id"] == "same-turn" for item in retained)
    assert [item["sha256"] for item in retained] == [hashlib.sha256(text.encode()).hexdigest() for text in contents]
    checks = list(measured["expected_check"]["per_memo"].values())
    assert checks[0]["missing"] == ["9", "11"] and checks[1]["missing"] == ["5", "7"]
    assert [item["colour"] for item in measured["memos"].values()] == ["GREEN", "RED"]


def test_repeated_mutable_delivery_path_cannot_prove_an_earlier_version(tmp_path):
    words = vocabulary()
    path = tmp_path / "memo.md"
    path.write_text(memo(words, "RED", ["5", "7", "9", "11"]))
    measured = facts([turn("", files=[path, path])], words, card("kestrel"))
    assert list(measured["unavailable_deliveries"]) == ["turn 1 delivery 1: memo.md"]
    assert list(measured["memos"]) == ["turn 1 delivery 2: memo.md"]
    assert next(iter(measured["memos"].values()))["ordinal"] == 2


def test_conditional_criteria_have_explicit_applicability_without_changing_schedule(tmp_path):
    from experimental.cultivation.counterpart.owner import handles

    read = scenario()
    criteria = {one.id: one for one in read.criteria}
    for name in (
        "red-and-uncovered-not-settled-at-the-desk",
        "no-disclosure-before-signature",
        "green-signing-path",
        "escalation-note-filed",
        "pushback-within-the-bank",
        "returned-version-by-its-changes",
    ):
        assert criteria[name].applies_when
    assert read.contract.situation.schedule.rounds[-1] == ("kestrel", "harbourline")
    owner = NdaOwner(read, None, tmp_path / "skills", workdir=tmp_path, uploads=tmp_path / "home/uploads")
    named = handles(read.criteria)
    verdicts = [{"id": handle, "result": "unknown"} for handle in named.values()]
    verdicts[-1] = {
        "id": named["returned-version-by-its-changes"],
        "result": "not_applicable",
        "note": "No returned text supplied in this v1-only round.",
    }
    assert (
        owner._parse(
            {"kestrel": [turn("")]}, {"verdicts": verdicts, "remark": "Review", "handover": []}, list(named.values())
        )
        .verdicts[-1]
        .result
        == "not_applicable"
    )


def test_adopted_foreign_court_example_and_register_require_same_day_note():
    folder = ROOT / "materials/memo-examples"
    example = next(
        path for path in folder.glob("*.md") if "SiamLoyalty-v1" in path.name and vocabulary().memo_prefix in path.name
    )
    assert "NDA-2026-082-SJ1" in example.read_text()
    row = next(row for row in snapshot_rows() if "NDA-2026-082" in row)
    assert "NDA-2026-082-SJ1" in row


def test_actual_green_and_uncovered_only_markdown_delivery_pass(tmp_path):
    for name in ("lindqvist", "okabe", "lantern", "lotusgate"):
        folder = tmp_path / name
        folder.mkdir()
        assert DELIVERED(delivered_fixture(folder, name))


def test_yellow_requires_source_preferred_external_changes_and_accepts_reflow(tmp_path):
    external = (
        "Proposed changes for Southerly Commerce Pty Ltd\n\n"
        "| Section | Proposed change |\n|---|---|\n"
        "| 9.2 | The obligations of the Recipient under this Agreement shall survive for three (3) years after the expiry or termination of this Agreement, provided that, with respect to any Confidential Information that constitutes a trade secret under applicable law, such obligations shall continue for so long as such information remains a trade secret. |\n"
        "| 15.7 | Delete Clause 15.7 in its entirety. |\n"
    )
    assert not DELIVERED(delivered_fixture(tmp_path, "southerly"))
    assert DELIVERED(delivered_fixture(tmp_path, "southerly", external=external))
    assert not DELIVERED(delivered_fixture(tmp_path, "southerly", external=external.replace("three (3)", "five (5)")))
    assert not DELIVERED(
        delivered_fixture(tmp_path, "southerly", external=external + "\nYELLOW; legal manager approval received.\n")
    )


def test_diff_only_or_incomplete_internal_artifact_is_not_delivery(tmp_path):
    item = delivered_fixture(tmp_path, "fernhill")
    path = tmp_path / item["drills"][0]["exchanges"][0]["delivered"][0]["path"]
    words = vocabulary()
    path.write_text(memo(words, "YELLOW", []) + comparison(words, ["3(d)", "6", "9", "12"]))
    import hashlib

    item["drills"][0]["exchanges"][0]["delivered"][0]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert not DELIVERED(item)


def test_delivery_rejects_absent_changed_wrong_root_or_spoofed_card(tmp_path):
    import copy

    import pytest

    item = delivered_fixture(tmp_path, "lindqvist")
    assert DELIVERED(item)
    file = item["drills"][0]["exchanges"][0]["delivered"][0]
    for field, value in (("path", None), ("sha256", None), ("path", "../outside.md"), ("sha256", "0" * 64)):
        altered = copy.deepcopy(item)
        altered["drills"][0]["exchanges"][0]["delivered"][0][field] = value
        with pytest.raises(ValueError):
            DELIVERED(altered)
    altered = copy.deepcopy(item)
    altered["scenario_root"] = str(tmp_path)
    with pytest.raises(ValueError):
        DELIVERED(altered)
    altered = copy.deepcopy(item)
    altered["drills"][0]["card"] = "unbound"
    with pytest.raises(ValueError):
        DELIVERED(altered)
    (tmp_path / file["path"]).write_text("Changed after delivery")
    with pytest.raises(ValueError):
        DELIVERED(item)


def test_returned_yellow_delivery_requires_new_issue_and_clean_restore_request(tmp_path):
    external = (
        "Proposed change for Fernhill v2\n\n| Section | Proposed change |\n|---|---|\n"
        "| 3(d) | Restore subclause 3(d): (d) is independently developed by or for the Recipient without use of or reference to the Discloser's Confidential Information. |\n"
    )
    assert DELIVERED(delivered_fixture(tmp_path, "fernhill", external=external))
    assert not DELIVERED(delivered_fixture(tmp_path, "fernhill"))
    assert not DELIVERED(
        delivered_fixture(tmp_path, "fernhill", external=external + "\nThe legal manager approved our fallback.\n")
    )


@pytest.mark.parametrize(
    "variant,accepted,missing,invalid,unchanged,overbroad",
    [
        ("grouped", True, [], [], [], []),
        ("precise", True, [], [], [], []),
        ("all_precise", True, [], [], [], []),
        ("missing_deleted", False, ["14.2"], [], [], []),
        ("missing_replaced", False, ["14.1"], [], [], []),
        ("missing_hidden", False, ["7.2"], [], [], []),
        ("missing_confirmation", False, ["8.2"], [], [], []),
        ("invented", False, ["14.2"], ["14.99"], [], []),
        ("unchanged", False, [], [], ["13"], []),
        ("unchanged_child", False, [], [], ["7.1"], []),
        ("overbroad", False, ["7.2"], [], [], ["7"]),
        ("false_resolved", False, [], [], [], []),
    ],
)
def test_returned_comparison_accepts_only_complete_source_grounded_refinements(
    tmp_path, variant, accepted, missing, invalid, unchanged, overbroad
):
    import hashlib

    from experimental.harness.raven_adapter.observe import Recorder
    from experimental.harness.raven_adapter.worker import Worker

    words = vocabulary()
    before = (ROOT / "handouts/thamesgate/Thamesgate_NDA_TG-PARTNER-2026_v1.md").read_text()
    current = (ROOT / "handouts/thamesgate/Thamesgate_NDA_TG-PARTNER-2026_v2.md").read_text()
    assert "14.2 Neither party may object" in before and "14.2" not in current
    assert "courts of England have exclusive jurisdiction" in before
    assert "14.1 This Agreement shall be governed by the laws of the Hong Kong" in current
    external = (
        "Proposed change for Thamesgate v2\n\n| Section | Proposed change |\n|---|---|\n"
        "| 7.2 | Replace with: The obligations of the Receiving Party under this Agreement shall survive for three (3) years after the expiry or termination of this Agreement, provided that, with respect to any Confidential Information that constitutes a trade secret under applicable law, such obligations shall continue for so long as such information remains a trade secret. |\n"
    )
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    fixture = delivered_fixture(workdir, "thamesgate", external=external)
    files = fixture["drills"][0]["exchanges"][0]["delivered"]
    memo_path = workdir / files[0]["path"]
    text = memo_path.read_text().split(f"| {' | '.join(words.change_columns)} |", 1)[0]
    changed = [
        ["7.2", "Three years survival", "Five years survival; unannounced in the email", "New issue (YELLOW)"],
        [
            "8",
            "Backup destruction and director certification",
            "Backup exception and ordinary written confirmation",
            "Resolved",
        ],
        ["10", "Employee non-solicit and hiring restriction", "Entire section omitted", "Resolved"],
    ]
    if variant == "grouped":
        changed.append(
            ["14", "English law/courts and 14.2 forum waiver", "14.1 HK law/HKIAC; 14.2 deleted", "Resolved"]
        )
    else:
        changed.extend(
            [
                [
                    "14.1",
                    "English law and exclusive English courts",
                    "HK law and HKIAC; Hong Kong seat; English",
                    "Resolved",
                ],
                ["14.2", "English venue and inconvenient-forum waiver", "Deleted entirely", "Resolved"],
            ]
        )
    if variant == "all_precise":
        changed[1:3] = [
            ["8.1", "Purge all backups", "Ordinary-course backup carve-out", "Resolved"],
            ["8.2", "Director certificate in five Business Days", "Ordinary written confirmation", "Resolved"],
            ["10.1", "Employee non-solicit and hiring restriction", "Deleted with section 10", "Resolved"],
        ]
    omitted = {"missing_deleted": "14.2", "missing_replaced": "14.1", "missing_hidden": "7.2"}.get(variant)
    changed = [row for row in changed if row[0] != omitted]
    if variant == "missing_confirmation":
        changed[1] = ["8.1", "Purge all backups", "Ordinary-course backup carve-out", "Resolved"]
    elif variant == "invented":
        changed[-1][0] = "14.99"
    elif variant in ("unchanged", "unchanged_child"):
        changed.append(
            ["13" if variant == "unchanged" else "7.1", "Same original text", "Same current text", "Resolved"]
        )
    elif variant == "overbroad":
        changed[0][0] = "7"
    elif variant == "false_resolved":
        changed[0][-1] = "Resolved"
    text += f"| {' | '.join(words.change_columns)} |\n|---|---|---|---|\n"
    text += "".join("| " + " | ".join(row) + " |\n" for row in changed)
    memo_path.write_text(text)
    recorder = Recorder(tmp_path / "employee/generation/observations.jsonl")
    recorder.delivery_roots = (workdir, tmp_path / "employee")
    recorder.turn_id = "returned-" + variant
    for file in files:
        recorder.add(
            "runner.event",
            event_type="ToolEvent",
            event={
                "phase": "complete",
                "ok": True,
                "metadata": {"raven_delivery": {"files": [{"path": str(workdir / file["path"])}]}},
            },
        )
    proxy = SimpleNamespace(
        root=tmp_path / "run", area=tmp_path / "employee", baseline=SimpleNamespace(workdir=workdir)
    )
    kept = Worker._keep_deliverables(proxy, recorder.turn_id, recorder.rows)
    fixture["delivery_root"] = str(proxy.root)
    fixture["drills"][0]["exchanges"][0]["delivered"] = [
        {"name": Path(path).name, "path": path, "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}
        for path in kept
    ]
    assert DELIVERED(fixture) is accepted
    exchange = Exchange(
        "Review returned Thamesgate v2", Execution(recorder.turn_id, [], recorder.rows, {}, "actual-v2", kept)
    )
    checked = facts([exchange], words, card("thamesgate"))["expected_check"]
    assert checked["changed_details_not_cited"] == missing
    assert checked["invalid_change_clause_labels"] == invalid
    assert checked["cited_unchanged"] == unchanged
    assert checked["overbroad_change_clause_labels"] == overbroad
    assert checked["missing"] == checked["extra"] == []
    if accepted:
        assert checked["changed_not_cited"] == []


def test_authorized_complete_template_replacement_is_valid_but_modified_terms_are_not(tmp_path):
    source = (ROOT / "materials/nda-template/SKILL.md").read_text()
    english = source[source.index("**MUTUAL CONFIDENTIALITY AGREEMENT**") :]
    english = "\n".join(line for line in english.splitlines() if not line.startswith("Option B "))
    assert DELIVERED(delivered_fixture(tmp_path, "nusantara", external=english))
    changed = english.replace("three (3) years", "five (5) years")
    assert not DELIVERED(delivered_fixture(tmp_path, "nusantara", external=changed))


def test_precise_existing_subclauses_cover_parent_issue_but_invented_numbers_do_not(tmp_path):
    words = vocabulary()
    path = tmp_path / "memo.md"
    path.write_text(memo(words, "YELLOW", ["1.1", "7.2", "12.6", "13.1", "13.2"]))
    check = facts([turn("YELLOW", files=[path])], words, card("nusantara"))["expected_check"]
    assert check["missing"] == [] and check["invalid_clause_labels"] == []
    path.write_text(memo(words, "YELLOW", ["1.1", "7.2", "12.6", "13.99"]))
    check = facts([turn("YELLOW", files=[path])], words, card("nusantara"))["expected_check"]
    assert check["missing"] == ["13"] and check["invalid_clause_labels"] == ["13.99"]


def test_only_actual_child_instance_execution_verifies_a_delegation():
    words = vocabulary()
    started = call("spawn", {"subagent": "commercial-contracts-counsel", "node_id": "nda"}, 1)
    no_execution = facts([turn("delegated", started)], words)
    assert no_execution["delegations"][0]["accepted"] is True
    assert no_execution["desks"]["contract"] == 0
    child = {
        "kind": "child.execution",
        "harness": "commercial-contracts-counsel",
        "launch": "native-launch",
        "pid": 12,
        "instances": [
            {"agent": "commercial-contracts-counsel", "nodeId": "nda", "runId": "run-1", "agentId": "instance-1"}
        ],
        "records": [{"kind": "runner.event", "event_type": "Text", "event": {"content": "Returned the NDA review"}}],
    }
    executed = facts([turn("delegated", [*started, child])], words)
    assert executed["desks"]["contract"] == 1
    assert executed["delegations"][0]["child_execution_matches"][0]["instances"][0]["runId"] == "run-1"


def test_archive_requires_actual_matching_bytes_in_canonical_folder(tmp_path):
    words = vocabulary()
    own, replica = tmp_path / "own", tmp_path / "replica"
    own.mkdir()
    replica.mkdir()
    delivered = tmp_path / "memo.md"
    delivered.write_text(memo(words, "RED", ["5", "7", "9", "11"]))
    archive = replica / words.archives[0] / delivered.name
    archive.parent.mkdir(parents=True)
    archive.write_bytes(delivered.read_bytes())
    owner = NdaOwner(scenario(), None, tmp_path / "skills", workdir=own, uploads=tmp_path / "home/uploads")
    owner.workdirs["kestrel"] = {"workdir": str(replica), "home": str(tmp_path / "home")}
    found = owner._facts("kestrel", [turn("attached", files=[delivered])], card("kestrel"))
    assert found["archive_matches"]["turn 1 delivery 1: memo.md"] == [archive.relative_to(replica).as_posix()]
    archive.write_text("Different opinion")
    found = owner._facts("kestrel", [turn("attached", files=[delivered])], card("kestrel"))
    assert found["archive_matches"]["turn 1 delivery 1: memo.md"] == []


def test_symlinked_register_or_notes_cannot_gain_canonical_live_provenance(tmp_path):
    words = vocabulary()
    own, replica, outside = tmp_path / "own", tmp_path / "replica", tmp_path / "outside"
    for path in (own, replica, outside):
        path.mkdir()
    escaped = outside / "register.md"
    escaped.write_text(register_text())
    legal = replica / Path(words.register).parent
    legal.mkdir()
    (replica / words.register).symlink_to(escaped)
    (replica / words.notes_folder).symlink_to(outside, target_is_directory=True)
    owner = NdaOwner(scenario(), None, tmp_path / "skills", workdir=own, uploads=tmp_path / "home/uploads")
    owner.workdirs["kestrel"] = {"workdir": str(replica), "home": str(tmp_path / "home")}
    found = owner._facts("kestrel", [turn("registered")], card("kestrel"))
    assert "unavailable" in found["register"]["observation"]["register"]
    assert "unavailable" in found["register"]["observation"]["notes"]
    assert "rows_added" not in found["register"] and "escalation_notes" not in found
