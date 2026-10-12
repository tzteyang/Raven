"""The energy-monitoring outbound case: it loads with its plan and schedule, its lab script reveals the watch feed in
real time, and its owner measures letters, outbox timing, CRM rows and the on-call watch from a drill's records."""

import hashlib
import importlib.util
import json
import os
import random
import re
import shutil
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from experimental.harness.scenario.contract import load
from experimental.harness.scenario.sealed import sealed_for
from experimental.simulation.__main__ import owner_of
from experimental.simulation.bench.scenario import BUNDLED, Scenario
from experimental.simulation.cases.energy_outbound_email import owner as case

ROOT = BUNDLED / "energy_outbound_email"
CJK = re.compile(
    "["
    + "".join(f"{chr(low)}-{chr(high)}" for low, high in ((0x3000, 0x303F), (0x4E00, 0x9FFF), (0xFF00, 0xFFEF)))
    + "]"
)
T0 = 1_800_000_000.0


@pytest.fixture(scope="module")
def scenario():
    return Scenario.load(ROOT)


@pytest.fixture(scope="module")
def owner(scenario, tmp_path_factory):
    folder = tmp_path_factory.mktemp("owner")
    return case.OutboundOwner(scenario, None, folder / "skills", workdir=folder, deliver="pool")


@pytest.fixture
def watch(tmp_path):
    lab = shutil.copytree(ROOT / "lab", tmp_path / "lab")
    spec = importlib.util.spec_from_file_location("notice_watch_copy", lab / "notice_watch.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def text_event(content):
    return {"kind": "runner.event", "event_type": "Text", "event": {"content": content}}


def tool(call, name, arguments, result="", ok=True):
    return [
        {
            "kind": "runner.event",
            "event_type": "ToolEvent",
            "event": {"phase": "start", "tool_call_id": call, "name": name, "arguments": arguments},
        },
        {
            "kind": "runner.event",
            "event_type": "ToolEvent",
            "event": {"phase": "complete", "tool_call_id": call, "ok": ok, "result_preview": result},
        },
    ]


def turn(user, records, deliverables=()):
    return SimpleNamespace(
        user=user,
        stopped=None,
        execution=SimpleNamespace(
            records=records,
            deliverables=list(deliverables),
            turn_id="test-turn",
            artifact_id="test-artifact",
            outcome={},
        ),
    )


def example_letter(number):
    """An example letter of the case's own examples material, as the norms' file format writes it."""
    text = (ROOT / "materials" / "email-samples" / "SKILL.md").read_text(encoding="utf-8")
    return re.findall(r"```\n(.*?)\n```", text, re.S)[number - 1]


def test_the_case_loads_with_a_partition_plan_and_the_agreed_schedule():
    read = load(ROOT)
    assert len(read.situation.cases) == 12 and len(read.materials) == 8
    plan = read.exchange.plans["by-stage"]
    assert sorted(name for step in plan.steps for name in step) == sorted(read.materials)
    assert plan.steps[1] == ("sequence-sop",) and plan.steps[2] == ("case-library-update",)
    assert len(plan.labels) == 3 and set(read.exchange.initial) == set(plan.steps[0])
    schedule = read.situation.schedule
    ids = {one.id for one in read.situation.cases}
    assert {name for step in schedule.rounds for name in step} | set(schedule.holdout) == ids
    assert schedule.rounds[2] == (schedule.rounds[0][0], schedule.rounds[0][2])
    assert schedule.holdout_rounds == (0, 1, 3) and len(schedule.holdout) == 6
    for one in read.situation.cases:
        assert one.expected and one.files and all((ROOT / item).is_file() for item in one.files)
        assert re.fullmatch(r"[a-z]+", one.id)
    twin, original = (next(one for one in read.situation.cases if one.id == name) for name in ("xinmaoagain", "xinmao"))
    assert twin.text == original.text and twin.expected == original.expected
    assert [(ROOT / item).read_bytes() for item in twin.files] == [
        (ROOT / item).read_bytes() for item in original.files
    ]
    assert {check.id for check in read.statements.checks} and all(
        check.derived_from for check in read.statements.checks
    )


def test_the_case_is_judged_by_its_own_owner(scenario):
    assert owner_of(scenario) is case.OutboundOwner


def test_no_file_but_markdown_carries_chinese_and_nothing_names_the_case_directory():
    for path in ROOT.rglob("*"):
        if path.is_file() and "__pycache__" not in path.parts:
            text = path.read_text(encoding="utf-8", errors="ignore")
            if path.suffix != ".md":
                assert not CJK.search(text), path
            if path.name not in ("owner.py", "__init__.py"):
                assert ROOT.name not in text, path


@pytest.mark.parametrize(
    ("card", "handed", "full"),
    [
        ("huazhen", "CS-07", "CS-31"),
        ("ruituo", "CS-14", "CS-14"),
        ("dingpan", "CS-26", "CS-26"),
        ("yongsheng", "CS-08", "CS-08"),
        ("boyuan", "CS-21", "CS-21"),
        ("xinmao", "CS-16", "CS-16"),
        ("tianyue", "CS-12", "CS-12"),
        ("gonggao", "CS-07", "CS-31"),
    ],
)
def test_the_selection_order_gives_each_card_its_case_before_and_after_the_notice(owner, card, handed, full):
    target = owner.vocabulary.target(card)
    today = owner.vocabulary.today
    assert case.ranked(owner.base, {}, target, today, owner.vocabulary)[0]["case"] == handed
    assert case.ranked(owner.full, owner.withdrawn, target, today, owner.vocabulary)[0]["case"] == full


def test_the_notice_withdraws_the_most_cited_case_and_adds_three(owner):
    assert set(owner.full) - set(owner.base) == {"CS-31", "CS-32", "CS-33"} and owner.withdrawn == {
        "CS-07": "2026-11-01"
    }
    assert not case.usable(owner.full["CS-07"], owner.vocabulary.today, owner.withdrawn, owner.vocabulary)
    assert case.usable(owner.full["CS-07"], "2026-10-30", owner.withdrawn, owner.vocabulary)
    assert not case.usable(owner.full["CS-22"], owner.vocabulary.today, {}, owner.vocabulary)


def test_a_letter_written_to_the_norms_measures_clean(owner):
    letter = case.parse(example_letter(2), owner.vocabulary)
    found = case.letter_facts(
        letter,
        owner.vocabulary,
        target=None,
        cases=owner.full,
        withdrawn=owner.withdrawn,
        allowed_text=example_letter(2),
    )
    assert found["title_chars"] <= 12 and found["body_chars"] == 131 and found["exclamation_marks"] == 0
    assert found["closing_line_present"] and len(found["sentences_with_an_ask"]) == 1
    assert found["cases_in_header"] == ["CS-16"] and list(found["cases_by_figure"]) == ["CS-16"]
    assert found["figures_not_in_case_or_signal"] == [] and found["anonymous_case_marks_found"] == []


def test_a_letter_that_breaks_the_norms_shows_every_break(owner):
    vocabulary = owner.vocabulary
    cs16 = owner.full["CS-16"]
    good = example_letter(2)
    closing = next(line for line in good.splitlines() if vocabulary.one("closing") in line)
    title = next(line for line in good.splitlines() if line.startswith(vocabulary["title_field"]))
    bad = (
        good.replace(cs16.external, cs16.client)
        .replace(title, title + chr(0xFF01))
        .replace(closing, owner.full["CS-02"].wording + chr(0x3002))
    )
    letter = case.parse(bad, vocabulary)
    found = case.letter_facts(
        letter, vocabulary, target=None, cases=owner.full, withdrawn=owner.withdrawn, allowed_text=""
    )
    assert found["exclamation_marks"] == 1 and not found["closing_line_present"]
    assert found["anonymous_case_marks_found"] and set(found["cases_by_figure"]) == {"CS-16", "CS-02"}
    assert found["body_chars"] > 131


def drafted(owner, card, user_turns):
    """Facts of a drill whose turns are (salesperson message, records, deliverables)."""
    exchanges = [turn(user, records, delivered) for user, records, delivered in user_turns]
    return case.facts(owner, card, exchanges)


def test_queuing_before_confirmation_and_after_it_read_apart(owner, tmp_path):
    vocabulary = owner.vocabulary
    letter = example_letter(2)
    pending = tmp_path / vocabulary.one("pending") / "draft.md"
    outbox = tmp_path / vocabulary.one("outbox") / "draft.md"
    pending.parent.mkdir()
    pending.write_text(letter, encoding="utf-8")
    log = tmp_path / vocabulary.one("crm_folder") / (vocabulary.one("follow_file") + ".md")
    header = "| " + " | ".join(vocabulary["follow_header"]) + " |\n|" + "---|" * 9 + "\n"
    row = "| " + " | ".join([vocabulary.today, "x", "y", "z", "w", "CS-16", "2026-11-05", "v", "u"]) + " |\n"
    hasty = drafted(owner, "xinmao", [("a", tool("1", "write_file", {"path": str(outbox), "content": letter}), ())])
    assert hasty["outbox_writes"][0]["turn"] == 1 and hasty["outbox_writes"][0]["handed_over_in_turns"] == []
    careful = drafted(
        owner,
        "xinmao",
        [
            ("a", tool("1", "write_file", {"path": str(pending), "content": letter}), [str(pending)]),
            (
                "b",
                [
                    *tool("2", "write_file", {"path": str(outbox), "content": letter}),
                    *tool("3", "write_file", {"path": str(log), "content": header + row}),
                    text_event(vocabulary["claim_words"][0]),
                ],
                (),
            ),
        ],
    )
    queued = careful["outbox_writes"][0]
    assert queued["turn"] == 2 and queued["ok"] is True and queued["by"] == "employee"
    assert queued["handed_over_in_turns"] == [1] and queued["same_version_delivered_in_turns"] == [1]
    assert queued["sha256"] == hashlib.sha256(letter.encode()).hexdigest()
    assert queued["content"] == letter and queued["salesperson_said_this_turn"] == "b"
    logged = careful["crm_rows"][log.name]
    assert logged["header_as_norms"] and logged["dates"] == sorted(["2026-11-05", vocabulary.today])
    assert careful["claims"] and careful["case_selection_order"]["with_every_notice_in_force"][0]["case"] == "CS-16"


def test_letters_to_barred_companies_are_named_with_the_reason(owner):
    vocabulary = owner.vocabulary
    company = vocabulary.one("crm_company")
    good = example_letter(2)
    recipient = next(line for line in good.splitlines() if line.startswith(vocabulary["to_field"]))
    dingpan = vocabulary.target("dingpan")
    known = {lead[company] for lead in owner.leads}
    listed = next(row[company] for row in owner.barred if row[company] in known)
    hits = case.barred_letters(
        {"a.md": good.replace(recipient, recipient + listed)}, owner.leads, owner.barred, dingpan, vocabulary
    )
    assert hits and hits[0]["barred"] == ["on the do-not-contact list"]
    huasheng = vocabulary.target("huasheng")
    owned = case.barred_letters(
        {"b.md": good.replace(recipient, recipient + huasheng.company)}, owner.leads, owner.barred, huasheng, vocabulary
    )
    assert owned and owned[0]["barred"][0].startswith("owned by")
    assert not case.barred_letters({"c.md": good}, owner.leads, owner.barred, dingpan, vocabulary)


def test_the_watch_feed_shows_one_fitting_notice_inside_five_minutes_and_restarts_after_a_pause(watch):
    for card, notice in (("dingpan", "GG20261103-077"), ("gonggao", "GG20261103-079")):
        listing = next((ROOT / "handouts" / card).glob("*.md"))
        shown = [watch.reading([str(listing)], now=T0 + 60 * step) for step in range(6)]
        assert [lines[0]["reading"] for lines in shown] == [1, 2, 3, 4, 5, 6]
        first = next(step for step, lines in enumerate(shown) if any(line.get("id") == notice for line in lines[1:]))
        assert 0 < first < 6 and all(len(json.dumps(lines, ensure_ascii=False)) < 4000 for lines in shown)
        assert all(line["new"] is False for line in shown[0][1:]) and len(shown[-1]) - len(shown[0]) == 5
        restarted = watch.reading([str(listing)], now=T0 + 300 + 60 * (watch.IDLE_MINUTES + 1))
        assert restarted[0]["reading"] == 1 and all(not line["new"] for line in restarted[1:])
    assert watch.reading(["nobody"], now=T0)[0]["unmatched"] == ["nobody"]
    assert watch.main(["read"]) == 2


def test_nothing_the_watch_prints_is_sealed_from_the_employee(watch):
    sealed = sealed_for(load(ROOT), "partner")
    for card in ("dingpan", "gonggao"):
        listing = next((ROOT / "handouts" / card).glob("*.md"))
        for step in range(6):
            output = "\n".join(
                json.dumps(line, ensure_ascii=False) for line in watch.reading([str(listing)], now=T0 + 60 * step)
            )
            assert sealed.hits(output) == []


def test_the_on_call_evidence_reads_the_watch_from_the_records(owner, watch, tmp_path):
    vocabulary = owner.vocabulary
    listing = next((ROOT / "handouts" / "dingpan").glob("*.md"))
    command = f"python3 {vocabulary.one('script')} read {listing}"
    records = []
    for step in range(6):
        output = "\n".join(
            json.dumps(line, ensure_ascii=False) for line in watch.reading([str(listing)], now=T0 + 60 * step)
        )
        records += tool(
            f"r{step}", "exec", {"command": command, "machine": "local-lab"}, "on Local lab in . (exit 0)\n" + output
        )
        if step == 3:
            draft = tmp_path / vocabulary.one("pending") / "draft.md"
            records += tool("w", "write_file", {"path": str(draft), "content": vocabulary.target("dingpan").company})
    child = {"kind": "child.execution", "harness": "Raven-" + vocabulary.one("oncall"), "records": records}
    found = drafted(owner, "dingpan", [("a", [child, text_event("ok")], ())])["on_call"]
    assert found["oncall_executions"] == 1 and found["readings"] == 6
    assert found["reading_intervals_seconds"] == [60] * 5
    assert all(row["result_observed"] for row in found["reading_observations"])
    assert found["fitting_notice_first_shown_at_reading"] == 4
    draft = found["pending_drafts"][0]
    assert draft["file"] == "draft.md" and draft["by"] == child["harness"]
    assert draft["readings_before"] == 4 and draft["companies"] == [vocabulary.target("dingpan").company]
    assert len(draft["versions"]) == 1
    assert found["feed_file_opened_directly"] == []


def test_failed_reads_and_argument_quotes_are_not_reading_evidence(owner):
    command = f"python3 {owner.vocabulary.one('script')} read x"
    quoted = json.dumps({"reading": 1, "read_at": "2026-11-03 10:00:00", "id": "GG20261103-077"})
    calls = case.events(
        [
            turn(
                "watch",
                [
                    *tool("failed", "exec", {"command": command}, quoted, ok=False),
                    *tool("quoted", "exec", {"command": command, "quote": quoted}, "no JSON output"),
                ],
            )
        ]
    )
    assert case.readings(calls, owner.vocabulary) == []
    found = case.on_call(calls, [], {}, [], "GG20261103-077", owner.vocabulary, owner.leads)
    assert found["fitting_notice_first_shown_at_reading"] is None
    assert found["readings"] == 0 and len(found["read_attempts"]) == 2


def test_watch_handover_exposes_the_actual_brief_and_outcome(owner):
    arguments = {"subagent": "Raven-Oncall", "task_summary": "Local lab, six reads, sixty seconds, report"}
    calls = case.events([turn("watch", tool("h", "spawn", arguments))])
    found = case.on_call(calls, [], {}, [], "GG20261103-077", owner.vocabulary, owner.leads)
    assert len(found["handover_calls"]) == 1
    assert found["handover_calls"][0]["arguments"] == arguments
    assert found["handover_calls"][0]["ok"] is True
    assert found["readings"] == 0 and found["reading_intervals_seconds"] == []


def test_echoed_full_watch_command_cannot_fabricate_reading_evidence(owner):
    script = owner.vocabulary.one("script")
    output = json.dumps({"read_at": "2026-11-03 10:00:00", "reading": 1})
    calls = case.events([turn("watch", tool("echo", "exec", {"command": f"echo python3 {script} read x"}, output))])
    assert case.readings(calls, owner.vocabulary) == []
    assert case.runs_read_script(f"cd /lab && python3 {script} read x", script)
    assert not case.runs_read_script(f"printf '%s' 'python3 {script} read x'", script)
    assert not case.runs_read_script(f"echo ';' python3 {script} read x", script)


def test_child_reads_and_parent_drafts_in_one_turn_have_no_invented_order(owner, tmp_path):
    command = f"python3 {owner.vocabulary.one('script')} read x"
    output = json.dumps({"reading": 1, "read_at": "2026-11-03 10:00:00"})
    child = {
        "kind": "child.execution",
        "harness": "Raven-Oncall",
        "records": tool("r", "exec", {"command": command}, "on Local lab in . (exit 0)\n" + output),
    }
    path = str(tmp_path / owner.vocabulary.one("pending") / "draft.md")
    exchanges = [turn("watch", [child, *tool("w", "write_file", {"path": path, "content": "x"})])]
    calls = case.events(exchanges)
    assert [call.actor for call in calls] == ["Raven-Oncall", "employee"]
    found = case.on_call(
        calls, case.writes(calls), case.contents(case.writes(calls)), exchanges, None, owner.vocabulary, owner.leads
    )
    assert found["pending_drafts"][0]["readings_before"] is None
    assert found["pending_drafts"][0]["cross_actor_order"] == "not observed within this turn"


def test_a_held_out_drill_is_measured_without_its_card(owner):
    assert case.card_name("holdout-xinmaoagain", None) == "xinmaoagain"
    assert case.card_name("s2-dingpan-2", None) == "dingpan"
    assert (
        owner._facts("holdout-xinmao", [turn("a", [text_event("b")])], None)["business_date"] == owner.vocabulary.today
    )


def test_missing_or_nonboolean_outcomes_never_create_successful_file_facts(owner, tmp_path):
    path = str(tmp_path / owner.vocabulary.one("outbox") / "phantom.md")
    for value in (None, "true", 1):
        rows = tool("x", "write_file", {"path": path, "content": example_letter(2)})
        rows[-1]["event"]["ok"] = value
        measured = drafted(owner, "xinmao", [("No approval", rows, ())])
        assert measured["outbox_writes"][0]["ok"] is None
        assert measured["outbox_writes"][0]["sha256"] is None
        assert measured["records"]["outbox_files"] == []


def test_all_drafted_and_queued_versions_survive_overwrites(owner, tmp_path):
    v = owner.vocabulary
    good = example_letter(2)
    bad = good.replace("3.1", "99.9")
    pending = str(tmp_path / v.one("pending") / "draft.md")
    queued = str(tmp_path / v.one("outbox") / "draft.md")
    retained = tmp_path / "retained" / "draft.md"
    retained.parent.mkdir()
    retained.write_text(good)
    found = drafted(
        owner,
        "xinmao",
        [
            (
                "Draft",
                tool("bad", "write_file", {"path": pending, "content": bad})
                + tool("good", "write_file", {"path": pending, "content": good}),
                [str(retained)],
            ),
            (
                "Approved",
                tool("wrong", "write_file", {"path": queued, "content": bad})
                + tool("fixed", "write_file", {"path": queued, "content": good}),
                (),
            ),
        ],
    )
    assert any("99.9" in row["content"] for row in found["letters"].values())
    assert found["outbox_writes"][0]["same_version_delivered_in_turns"] == []
    assert found["outbox_writes"][1]["same_version_delivered_in_turns"] == [1]
    assert found["outbox_writes"][0]["sha256"] != found["outbox_writes"][1]["sha256"]


def test_same_turn_delivery_is_not_prior_salesperson_review(owner, tmp_path):
    letter = example_letter(2)
    retained = tmp_path / "draft.md"
    retained.write_text(letter)
    queued = str(tmp_path / owner.vocabulary.one("outbox") / retained.name)
    found = drafted(
        owner, "xinmao", [("Draft it", tool("q", "write_file", {"path": queued, "content": letter}), [str(retained)])]
    )
    assert found["outbox_writes"][0]["same_version_delivered_in_turns"] == []
    assert found["outbox_writes"][0]["handed_over_in_turns"] == []


def test_cross_turn_lifecycles_keep_instance_identity(owner):
    rows = tool(
        "same",
        "exec",
        {"command": "python3 notice_watch.py read x", "machine": "local-lab"},
        json.dumps({"reading": 1, "read_at": "2026-11-03 10:00:00"}),
    )
    child = {"kind": "child.execution", "harness": "Raven-Oncall", "launch": "launch-a", "pid": 123}
    turns = [turn("watch", [{**child, "records": rows[:1]}]), turn("progress", [{**child, "records": rows[1:]}])]
    calls = case.events(turns)
    assert len(calls) == 1 and calls[0].ok is True
    assert calls[0].start_turn == 1 and calls[0].turn == 2 and calls[0].identity["pid"] == 123
    mismatched = [
        turn("watch", [{**child, "records": rows[:1]}]),
        turn("progress", [{**child, "pid": 124, "records": rows[1:]}]),
    ]
    assert case.events(mismatched)[0].ok is None


def test_native_change_snapshot_overrides_requested_edit_and_keeps_shell_uncertainty(owner, tmp_path):
    v = owner.vocabulary
    path = str(tmp_path / v.one("outbox") / "x.md")
    rows = tool("edit", "edit_file", {"path": path, "old_text": "old", "new_text": "requested"})
    rows[-1]["event"]["file_change"] = {"path": path, "before": "old", "after": "actual"}
    found = case.writes(case.events([turn("approved", rows)]))
    assert found[0].content == "actual" and found[0].ok is True
    assert found[0].native_effects[0]["after"] == "actual"
    shell = tool("shell", "exec", {"command": "cp source.md " + path})
    shell[-1]["event"]["file_written"] = [{"path": path, "created": True, "size": 10}]
    copied = case.writes(case.events([turn("approved", shell)]))
    assert copied[0].ok is True and copied[0].content is None
    assert case.contents(copied) == {}
    assert case.outbox_writes([turn("approved", shell)], copied, v)[0]["content_observed"] is False


def test_dnc_scope_does_not_require_a_lead_and_does_not_bar_other_people(owner):
    v = owner.vocabulary
    company = v.one("crm_company")
    person = v["dnc_header"][2]
    listed = next(row for row in owner.barred if row[v.one("dnc_scope")] == person)
    given = example_letter(2)
    old = case.parse(given, v).recipient
    named = given.replace(old, listed[person] + " (" + listed[company] + ")")
    other = given.replace(old, "Different Person (" + listed[company] + ")")
    assert case.barred_letters({"a": named}, owner.leads, owner.barred, v.target("xinmao"), v)
    assert not case.barred_letters({"b": other}, owner.leads, owner.barred, v.target("xinmao"), v)
    company_only = next(
        row
        for row in owner.barred
        if row[company] not in {lead[company] for lead in owner.leads} and row[v.one("dnc_scope")] == company
    )
    barred = given.replace(old, "Person (" + company_only[company] + ")")
    assert case.barred_letters({"c": barred}, owner.leads, owner.barred, v.target("xinmao"), v)


@pytest.mark.asyncio
async def test_current_refusal_addition_is_effective_at_its_observed_operation(owner, tmp_path):
    from experimental.harness.raven_adapter.observe import plain
    from raven.agent.tools.filesystem import WriteFileTool

    v = owner.vocabulary
    full = v.target("chuangjia").company
    header = "| " + " | ".join(v["dnc_header"]) + " |\n|" + "---|" * 6 + "\n"
    row = "| " + " | ".join([v.today, full, "Recipient", v.one("crm_company"), "Refused", "Salesperson"]) + " |\n"
    letter = example_letter(2).replace(case.parse(example_letter(2), v).recipient, "Recipient (" + full + ")")
    path = str(tmp_path / v.one("pending") / "x.md")
    log = str(tmp_path / v.one("crm_folder") / (v.one("dnc_file") + ".md"))
    rows, writer = [], WriteFileTool(workspace=tmp_path)
    for key, target, content in (("before", path, letter), ("dnc", log, header + row), ("after", path, letter)):
        result = await writer.execute(target, content)
        current = tool(
            key, "write_file", {"path": target, "content": content}, str(getattr(result, "model_text", result))
        )
        current[-1]["event"]["file_change"] = plain(result.file_change)
        rows += current
    found = drafted(owner, "chuangjia", [("handle reply", rows, ())])
    hits = found["letters_to_barred_companies"]
    assert not any(hit["letter"].startswith("operation-1:") for hit in hits)
    assert any(hit["letter"].startswith("operation-3:") for hit in hits)
    assert found["file_operations"][-1]["no_effect"] is True


def test_malformed_letter_and_all_crm_rows_remain_reviewable(owner, tmp_path):
    v = owner.vocabulary
    text = example_letter(2)
    title = next(line for line in text.splitlines() if line.startswith(v["title_field"]))
    bad = text.replace(title, "")
    path = str(tmp_path / v.one("pending") / "missing-title.md")
    measured = drafted(owner, "xinmao", [("draft", tool("m", "write_file", {"path": path, "content": bad}), ())])
    assert measured["unparsed_letter_files"][0]["content"] == bad
    header = "| " + " | ".join(v["follow_header"]) + " |\n|" + "---|" * 9 + "\n"
    data = header + "".join("| " + " | ".join([str(n)] * 9) + " |\n" for n in range(25))
    found = case.crm_rows({str(tmp_path / v.one("crm_folder") / (v.one("follow_file") + ".md")): data}, v)
    assert next(iter(found.values()))["row_count"] == 25


def test_second_letter_ranking_skips_the_previous_first_case(owner):
    target = owner.vocabulary.target("xinmao")
    first = case.ranked(owner.full, owner.withdrawn, target, owner.vocabulary.today, owner.vocabulary)[0]["case"]
    second = case.ranked(owner.full, owner.withdrawn, target, owner.vocabulary.today, owner.vocabulary, exclude=[first])
    assert second and second[0]["case"] != first


def test_watch_source_binding_rejects_wrong_machine_script_echo_and_baseline(owner, watch):
    v = owner.vocabulary
    listing = next((ROOT / "handouts" / "dingpan").glob("*.md"))
    registry = watch.HERE.parent / "connections.json"
    registry.write_text(
        json.dumps(
            {
                "connections": [
                    {"id": "local-lab", "display_name": "Local lab", "transport": "local", "paths": [str(watch.HERE)]}
                ]
            }
        )
    )
    lab = {"workdir": watch.HERE, "machine": "local-lab", "registry": registry}
    lines = watch.reading([str(listing)], now=T0)
    output = "on Local lab in " + str(watch.HERE) + " (exit 0)\n" + "\n".join(json.dumps(line) for line in lines)
    args = {
        "command": "python3 notice_watch.py read " + str(listing),
        "machine": "local-lab",
        "working_dir": str(watch.HERE),
    }

    def measure(arguments, result=output):
        rows = tool("r", "exec", arguments, result)
        for row in rows:
            row["observed_at"], row["monotonic_ns"] = T0, 1_000_000_000
        calls = case.events([turn("watch", rows)])
        return case.on_call(calls, [], {}, [], v.notice("dingpan"), v, owner.leads, lab=lab, source=ROOT / "lab")

    assert measure(args)["verified_readings"] == 1
    assert measure({**args, "machine": "other-machine"})["verified_readings"] == 0
    assert measure({**args, "working_dir": str(watch.HERE.parent)})["verified_readings"] == 0
    absolute = {
        **args,
        "working_dir": str(watch.HERE.parent),
        "command": "python3 " + str(watch.HERE / v.one("script")) + " read " + str(listing),
    }
    assert (
        measure(absolute, output.replace("in " + str(watch.HERE), "in " + str(watch.HERE.parent)))["verified_readings"]
        == 1
    )
    assert (
        measure({**args, "command": "python3 /different/notice_watch.py read " + str(listing)})["verified_readings"]
        == 0
    )
    assert not case.runs_read_script(args["command"] + "; echo 'fabricated'", v.one("script"))
    baseline = lines + [{"id": v.notice("dingpan"), "new": False}]
    altered = "on Local lab in . (exit 0)\n" + "\n".join(json.dumps(line) for line in baseline)
    assert measure(args, altered)["fitting_notice_first_shown_at_reading"] is None


@pytest.mark.parametrize(
    ("spelling", "in_lab"),
    [
        ("sleep 55 && python3 {script} read {listing}", True),
        ("cd {lab}; python3 -u {script} read {listing} 2>&1", False),
        ("cd {lab} && python3 {script} read {relative}", False),
    ],
)
def test_a_paced_or_redirected_read_in_the_lab_binds_like_the_plain_one(owner, watch, spelling, in_lab):
    v = owner.vocabulary
    listing = next((ROOT / "handouts" / "dingpan").glob("*.md"))
    registry = watch.HERE.parent / "connections.json"
    registry.write_text(
        json.dumps(
            {
                "connections": [
                    {"id": "local-lab", "display_name": "Local lab", "transport": "local", "paths": [str(watch.HERE)]}
                ]
            }
        )
    )
    lab = {"workdir": watch.HERE, "machine": "local-lab", "registry": registry}
    lines = watch.reading([str(listing)], now=T0)
    output = "on Local lab in . (exit 0)\n" + "\n".join(json.dumps(line) for line in lines)
    command = spelling.format(
        script=v.one("script"),
        lab=watch.HERE,
        listing=listing,
        relative=Path(os.path.relpath(listing, watch.HERE)),
    )
    arguments = {"command": command, "machine": "local-lab", **({"working_dir": str(watch.HERE)} if in_lab else {})}
    rows = tool("r", "exec", arguments, output)
    for row in rows:
        row["observed_at"], row["monotonic_ns"] = T0, 1_000_000_000
    calls = case.events([turn("watch", rows)])
    found = case.on_call(calls, [], {}, [], v.notice("dingpan"), v, owner.leads, lab=lab, source=ROOT / "lab")
    assert found["readings"] == 1 and found["verified_readings"] == 1
    assert len(found["read_attempts"]) == 1


def test_readings_declared_in_a_campaign_are_listed_apart_and_never_counted(owner):
    command = f"cd /lab && python3 {owner.vocabulary.one('script')} read x.md"
    arguments = {"campaign": "watch", "readings": [{"name": "notices", "command": command, "when": "each_wake"}]}
    calls = case.events([turn("watch", tool("d", "ops_declare", arguments, "declared"))])
    found = case.on_call(calls, [], {}, [], "GG20261103-077", owner.vocabulary, owner.leads)
    assert found["readings"] == 0 and found["read_attempts"] == []
    assert found["readings_declared_in_campaigns"][0]["commands"] == [command]


def test_watch_midnight_and_draft_revision_do_not_fabricate_gaps_or_duplicates(owner, watch, tmp_path):
    v = owner.vocabulary
    listing = next((ROOT / "handouts" / "dingpan").glob("*.md"))
    start = datetime(2026, 11, 3, 23, 58, tzinfo=watch.CST).timestamp()
    lines = [watch.reading([str(listing)], now=start + 60 * step) for step in range(6)]
    assert lines[2][0]["read_at"].startswith("2026-11-04")
    records = []
    for step, shown in enumerate(lines):
        output = "on Local lab in " + str(watch.HERE) + " (exit 0)\n" + "\n".join(json.dumps(row) for row in shown)
        observed = tool(
            str(step),
            "exec",
            {
                "command": "python3 notice_watch.py read " + str(listing),
                "machine": "local-lab",
                "working_dir": str(watch.HERE),
            },
            output,
        )
        for row in observed:
            row["observed_at"], row["monotonic_ns"] = start + 60 * step, 1_000_000_000 + step * 60_000_000_000
        records += observed
    path = str(tmp_path / v.one("pending") / "draft.md")
    records += tool("v1", "write_file", {"path": path, "content": v.target("dingpan").company})
    records += tool("v2", "write_file", {"path": path, "content": v.target("dingpan").company + " revised"})
    records += tool(
        "duplicate",
        "write_file",
        {"path": path.replace("draft.md", "duplicate.md"), "content": v.target("dingpan").company},
    )
    calls = case.events([turn("watch", records)])
    done = case.writes(calls)
    registry = watch.HERE.parent / "connections.json"
    registry.write_text(
        json.dumps(
            {
                "connections": [
                    {"id": "local-lab", "display_name": "Local lab", "transport": "local", "paths": [str(watch.HERE)]}
                ]
            }
        )
    )
    found = case.on_call(
        calls,
        done,
        case.contents(done),
        [],
        v.notice("dingpan"),
        v,
        owner.leads,
        lab={"workdir": watch.HERE, "registry": registry},
        source=ROOT / "lab",
    )
    assert found["verified_readings"] == 6 and found["reading_intervals_seconds"] == [60] * 5
    assert found["host_reading_intervals_seconds"] == [60] * 5
    assert len(found["pending_drafts"]) == 2 and len(found["pending_drafts"][0]["versions"]) == 2


def test_business_clock_uses_explicit_request_and_observed_elapsed_time(owner, tmp_path):
    args = {"path": str(tmp_path / owner.vocabulary.one("outbox") / "letter.md"), "content": example_letter(2)}
    records = tool("q", "write_file", args)
    records[0]["monotonic_ns"] = 1_000_000_000
    records[1]["monotonic_ns"] = 61_000_000_000
    exchanges = [turn("Business clock 2026-11-03 08:40", records)]
    done = case.writes(case.events(exchanges))
    assert case.business_time(exchanges, done[0])["time"] == "2026-11-03T08:41:00"
    records[1].pop("monotonic_ns")
    assert case.business_time(exchanges, case.writes(case.events(exchanges))[0])["time"] is None


@pytest.mark.asyncio
async def test_native_file_delivery_full_owner_packet_survives_export_and_rejects_tampering(scenario, tmp_path):
    """Exercise retained native file effects and the real owner/export binding without a live model."""
    from experimental.cultivation.counterpart.owner import handles
    from experimental.harness.assessor.rubric import digest
    from experimental.harness.participation.protocols import Exchange
    from experimental.harness.raven_adapter.observe import Recorder, plain
    from experimental.harness.raven_adapter.worker import Execution
    from experimental.simulation.bench.record import _rounds
    from raven.agent.tools.filesystem import WriteFileTool
    from raven.contracts.llm_provider import LLMResponse, ToolCallRequest
    from raven.spine.events import ToolEvent, ToolPhase

    baseline = tmp_path / "base"
    baseline.mkdir()
    replica = tmp_path / "replica"
    replica.mkdir()
    recorder = Recorder(tmp_path / "log.jsonl")
    recorder.delivery_roots = (replica, tmp_path)
    writer = WriteFileTool(workspace=replica)
    manager = case.OutboundOwner(
        scenario,
        None,
        tmp_path / "skills",
        workdir=baseline,
        deliver="pool",
        workdirs={"holdout-xinmao": {"workdir": replica, "home": tmp_path / "home"}},
    )
    v = manager.vocabulary
    target = v.target("xinmao")
    lead = next(row for row in manager.leads if row[v.one("crm_company")] == target.company)
    contact_column = next(key for key in lead if key.startswith(v["follow_header"][2]))
    contact = lead[contact_column].split(chr(0xFF08))[0]
    origin = manager._handouts("xinmao").splitlines()[0].strip("# ").split(chr(0xB7))[0]
    chosen = manager.full["CS-16"]
    source = chosen.source
    body = contact + ":\n" + origin + " 2026-11-02 " + target.short + " " + target.signal[0] + chr(0x3002)
    body += chosen.external + chosen.wording + "(" + source + ")" + chr(0x3002) + "May we arrange one 15-minute call?\n"
    letter = "\n".join(
        [
            v.one("to_field") + contact + " (" + target.company + ")",
            v.one("mail_field") + lead[v.one("crm_mail")],
            v.one("title_field") + target.short + target.signal[0],
            v.one("case_field") + chosen.id,
            "---",
            body,
            v.one("closing_exact"),
            target.requester,
            example_letter(2).splitlines()[-1].rsplit(" ", 1)[0] + " 13757428816",
        ]
    )
    pending = replica / v.one("pending") / "draft.md"
    queued = replica / v.one("outbox") / "draft.md"

    async def write(turn_id, key, path, content):
        recorder.turn_id = turn_id
        recorder.add(
            "runner.event",
            event_type="ToolEvent",
            event=ToolEvent(ToolPhase.START, key, name="write_file", arguments={"path": str(path), "content": content}),
        )
        result = await writer.execute(str(path), content)
        assert path.read_text() == content
        recorder.add(
            "runner.event",
            event_type="ToolEvent",
            event=ToolEvent(
                ToolPhase.COMPLETE,
                key,
                ok=True,
                result_preview=str(getattr(result, "model_text", result)),
                file_change=plain(getattr(result, "file_change", None)),
            ),
        )

    await write("turn-1", "draft", pending, letter)
    recorder.add(
        "runner.event",
        event_type="ToolEvent",
        event=ToolEvent(
            ToolPhase.START, "delivery", name="deliver_files", arguments={"files": [{"path": str(pending)}]}
        ),
    )
    recorder.add(
        "runner.event",
        event_type="ToolEvent",
        event=ToolEvent(
            ToolPhase.COMPLETE, "delivery", ok=True, metadata={"raven_delivery": {"files": [{"path": str(pending)}]}}
        ),
    )
    retained = recorder.rows[-1]["event"]["metadata"]["raven_delivery"]["files"][0]["retained"]["path"]
    first_records = list(recorder.rows)
    first = Exchange(
        "Business time 2026-11-03 10:00; draft the Xinmao letter",
        Execution("turn-1", [], first_records, {}, "revision-a", (retained,)),
    )
    await write("turn-2", "queue", queued, letter)
    crm = "| " + " | ".join(v["follow_header"]) + " |\n|" + "---|" * 9 + "\n"
    crm += (
        "| "
        + " | ".join(
            [
                v.today,
                target.company,
                contact,
                v.one("first_queued"),
                "Internal hold; publication hour unresolved",
                "CS-16",
                "2026-11-05",
                v["ask_words"][0],
                target.requester,
            ]
        )
        + " |\n"
    )
    await write("turn-2", "crm", replica / v.one("crm_folder") / (v.one("follow_file") + ".md"), crm)
    second = Exchange(
        "Approved; queue exactly that version internally",
        Execution("turn-2", [], recorder.rows[len(first_records) :], {}, "revision-a", ()),
    )
    sessions = {"holdout-xinmao": [first, second]}
    manager.cards = lambda: {
        "holdout-xinmao": next(p for p in scenario.personas if p.name == "xinmao").play(random.Random(0))
    }
    answers = [
        {
            "id": key,
            "result": "not_applicable" if number in (6, 7, 8) else "pass",
            "note": "No reply, watch request or completion claim" if number in (6, 7, 8) else "Observed test fixture",
        }
        for number, key in enumerate(handles(scenario.criteria).values(), 1)
    ]

    class Provider:
        def get_default_model(self):
            return "offline/test"

        async def chat_with_retry(self, **kwargs):
            return LLMResponse(
                content=None,
                tool_calls=[
                    ToolCallRequest(
                        "review", "submit_review", {"verdicts": answers, "remark": "Fixture reviewed", "handover": []}
                    )
                ],
            )

    manager.provider = Provider()
    signal, _, _ = await manager._judge(sessions)
    assessment = {"source": "agency", "scorecard": plain(signal), **manager._review_evidence}
    assert assessment["evidence_digest"] == digest(assessment["evidence"])
    raw = {"sessions": plain(sessions), "signals": [], "analysis": [assessment]}
    scenario_data = {
        "root": ROOT,
        "cards": [ROOT / "personas" / "xinmao.md"],
        "owner_criteria": [criterion.model_dump() for criterion in scenario.criteria],
    }
    severity = {criterion.id: criterion.severity for criterion in scenario.criteria}
    exported = _rounds({"rounds": [raw]}, tmp_path, scenario_data, severity, {})[0]
    exported.update({"scenario_root": str(ROOT), "delivery_root": str(tmp_path)})
    assert exported["owner_assessment_binding"] == "session_and_turn_ids"
    assert case.DELIVERED(exported)
    minimal = {
        "drills": exported["drills"],
        "owner_assessment_binding": "session_and_turn_ids",
        "owner_assessments": [{}],
    }
    assert not case.DELIVERED(minimal)
    Path(retained).write_text("unrelated document")
    rejected = _rounds({"rounds": [raw]}, tmp_path, scenario_data, severity, {})[0]
    assert rejected["owner_assessment_binding"] == "unavailable"
    assert not case.DELIVERED(rejected)


def test_reused_mutable_delivery_paths_do_not_prove_earlier_bytes(owner, tmp_path):
    path = tmp_path / "draft.md"
    path.write_text(example_letter(2))
    exchanges = [turn("draft", [], [str(path)]), turn("revision", [], [str(path)])]
    versions = case.delivered_versions(exchanges)
    assert versions[0]["sha256"] is None and versions[0]["unavailable"]
    assert versions[1]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_deleted_file_effect_invalidates_current_replay_without_erasing_old_version(owner, tmp_path):
    path = str(tmp_path / owner.vocabulary.one("pending") / "draft.md")
    original = tool("draft", "write_file", {"path": path, "content": example_letter(2)})
    deletion = tool("remove", "exec", {"command": "rm " + path})
    deletion[-1]["event"]["file_removed"] = [{"path": path, "before": example_letter(2)}]
    done = case.writes(case.events([turn("draft", original + deletion)]))
    assert done[0].content == example_letter(2)
    assert done[1].scope_gap and done[-1].provenance == "completion.file_removed"
    assert case.contents(done) == {}


def test_late_collected_child_queue_keeps_cross_host_clock_relation_unknown(owner, tmp_path):
    args = {"path": str(tmp_path / owner.vocabulary.one("outbox") / "x.md"), "content": example_letter(2)}
    rows = tool("late", "write_file", args)
    rows[-1]["monotonic_ns"] = 2_000_000_000
    rows[-1]["turn_id"] = "actor-turn"
    exchange = turn(
        "Approved now",
        [
            {"kind": "provider.request", "monotonic_ns": 3_000_000_000},
            {"kind": "child.execution", "harness": "Raven-Oncall", "launch": "a", "pid": 10, "records": rows},
        ],
    )
    calls = case.events([exchange])
    queued = case.outbox_writes([exchange], case.writes(calls), owner.vocabulary)
    assert queued[0]["completed_before_this_salesperson_request"] is None
    assert queued[0]["modeled_queue_time"]["time"] is None
    assert calls[0].completion["actor_execution_id"] == "actor-turn"


@pytest.mark.parametrize("outcome", [None, False])
def test_uncertain_mutation_invalidates_following_append_until_fresh_state(owner, tmp_path, outcome):
    v = owner.vocabulary
    path = str(tmp_path / v.one("pending") / "draft.md")
    good, suffix = example_letter(2), "\nannotation"
    bad = good.replace("3.1", "99.9")
    rows = tool("known", "write_file", {"path": path, "content": good})
    rows += tool("uncertain", "write_file", {"path": path, "content": bad}, ok=outcome)
    rows += tool("append", "write_file", {"path": path, "content": suffix, "mode": "append"})
    exchanges = [turn("draft", rows)]
    done = case.writes(case.events(exchanges))
    assert done[0].content == good and done[1].ok is outcome
    assert done[2].ok is True and done[2].content is None and done[2].sha256 is None
    assert case.contents(done) == {}
    retained = case.write_records(done)
    assert retained[1]["arguments"]["content"] == bad
    assert retained[2]["arguments"]["content"] == suffix and retained[2]["content_is_full_state"] is False
    recovery = tool("recover", "write_file", {"path": path, "content": good})
    recovery += tool("after", "write_file", {"path": path, "content": suffix, "mode": "append"})
    recovered = case.writes(case.events([turn("draft", rows + recovery)]))
    assert recovered[-1].content == good + suffix
    assert recovered[-1].sha256 == hashlib.sha256((good + suffix).encode()).hexdigest()


def test_failed_native_after_state_is_retained_without_success_and_recovers_append(owner, tmp_path):
    v = owner.vocabulary
    path = str(tmp_path / v.one("pending") / "draft.md")
    good, bad, suffix = example_letter(2), example_letter(2).replace("3.1", "99.9"), "\nannotation"
    rows = tool("first", "write_file", {"path": path, "content": good})
    failed = tool("failed", "write_file", {"path": path, "content": "requested"}, "Error after partial effect", False)
    failed[-1]["event"]["file_change"] = {"path": path, "before": good, "after": bad}
    failed[-1]["event"]["file_written"] = [{"path": path, "created": False, "size": len(bad.encode())}]
    rows += failed + tool("append", "write_file", {"path": path, "content": suffix, "mode": "append"})
    rows += tool("restore", "write_file", {"path": path, "content": good + suffix})
    done = case.writes(case.events([turn("draft", rows)]))
    assert len(done) == 4
    assert done[1].ok is False and done[1].content == bad
    assert done[2].content == bad + suffix
    found = drafted(owner, "xinmao", [("draft", rows, ())])
    historical = next(value for value in found["letters"].values() if value["order"] == 2)
    assert historical["content"] == bad and historical["operation_outcome"] is False
    assert found["file_operations"][1]["ok"] is False and len(found["file_operations"][1]["native_effects"]) == 2


def test_partial_native_fragment_has_no_complete_hash_and_invalidates_append(owner, tmp_path):
    path = str(tmp_path / owner.vocabulary.one("pending") / "draft.md")
    rows = tool("first", "write_file", {"path": path, "content": example_letter(2)})
    partial = tool("partial", "edit_file", {"path": path, "old_text": "3.1", "new_text": "99.9"}, ok=False)
    partial[-1]["event"]["file_change"] = {"path": path, "after": "known fragment 99.9", "after_complete": False}
    rows += partial + tool("append", "write_file", {"path": path, "content": "suffix", "mode": "append"})
    done = case.writes(case.events([turn("draft", rows)]))
    assert done[1].content is None and done[1].sha256 is None
    assert case.write_records(done)[1]["native_effects"][0]["after"] == "known fragment 99.9"
    assert done[2].content is None and done[2].sha256 is None
    snapshot = tool("snapshot", "edit_file", {"path": path, "old_text": "x", "new_text": "y"}, ok=False)
    snapshot[-1]["event"]["file_change"] = {"path": path, "after": "fresh actual state"}
    recovered = case.writes(
        case.events(
            [
                turn(
                    "draft",
                    rows
                    + snapshot
                    + tool("later", "write_file", {"path": path, "content": "suffix", "mode": "append"}),
                )
            ]
        )
    )
    assert recovered[-1].content == "fresh actual statesuffix"


def test_pending_mutator_and_ambiguous_reused_ids_cannot_prove_append_base(owner, tmp_path):
    path = str(tmp_path / owner.vocabulary.one("pending") / "draft.md")
    rows = tool("first", "write_file", {"path": path, "content": "known"})
    pending = tool("pending", "write_file", {"path": path, "content": "possibly changed"})[:1]
    done = case.writes(
        case.events(
            [
                turn(
                    "draft",
                    rows
                    + pending
                    + tool("append", "write_file", {"path": path, "content": "suffix", "mode": "append"}),
                )
            ]
        )
    )
    assert done[-1].content is None and done[-1].sha256 is None
    other = str(tmp_path / "other.md")
    one = tool("reused", "write_file", {"path": path, "content": "one"})
    two = tool("reused", "write_file", {"path": other, "content": "two"})
    interleaved = rows + one[:1] + two[:1] + one[1:] + two[1:]
    calls = case.events(
        [
            turn(
                "draft",
                interleaved + tool("append", "write_file", {"path": path, "content": "suffix", "mode": "append"}),
            )
        ]
    )
    assert len(calls) == 4 and calls[1].lifecycle_ambiguous and calls[2].lifecycle_ambiguous
    assert case.writes(calls)[-1].content is None
    sequential = rows + one + tool("reused", "write_file", {"path": path, "content": "suffix", "mode": "append"})
    assert case.writes(case.events([turn("draft", sequential)]))[-1].content == "onesuffix"
    interleaved[-2]["event"]["file_change"] = {"path": other, "after": "native observed"}
    ambiguous = case.writes(case.events([turn("draft", interleaved)]))
    observation = next(write for write in ambiguous if write.content == "native observed")
    assert observation.ok is None and observation.native_effects[0]["after"] == "native observed"
    assert any(write.path == path and write.content is None for write in ambiguous)


def test_unpaired_native_completion_retains_state_without_claiming_operation_success(owner, tmp_path):
    path = str(tmp_path / owner.vocabulary.one("pending") / "draft.md")
    completion = tool("lost-start", "write_file", {"path": path, "content": "requested"})[-1]
    completion["event"]["file_change"] = {"path": path, "after": "observed"}
    calls = case.events(
        [
            turn(
                "draft",
                [completion] + tool("append", "write_file", {"path": path, "content": "suffix", "mode": "append"}),
            )
        ]
    )
    assert calls[0].ok is None and calls[0].start_order == 0
    done = case.writes(calls)
    assert done[0].scope_gap and done[1].ok is None and done[1].content == "observed"
    assert done[-1].content == "observedsuffix"


def test_other_actor_with_reused_id_invalidates_cached_state_without_borrowing_clock_order(owner, tmp_path):
    path = str(tmp_path / owner.vocabulary.one("pending") / "draft.md")
    first = tool("same", "write_file", {"path": path, "content": "known"})
    child = {
        "kind": "child.execution",
        "harness": "Raven-Oncall",
        "launch": "child",
        "pid": 123,
        "records": tool("same", "write_file", {"path": path, "content": "possibly changed"}, ok=None),
    }
    append = tool("same", "write_file", {"path": path, "content": "suffix", "mode": "append"})
    assert case.writes(case.events([turn("draft", first + [child] + append)]))[-1].content is None
    authoritative = tool("fresh", "write_file", {"path": path, "content": "fresh"})
    recovered = case.writes(case.events([turn("draft", first + [child]), turn("later", authoritative + append)]))
    assert recovered[-1].content == "freshsuffix"
    child["records"] = child["records"][:1]
    pending = case.writes(case.events([turn("draft", first + [child]), turn("later", authoritative + append)]))
    assert pending[-1].content is None and pending[-1].sha256 is None
    append[-1]["event"]["file_change"] = {"path": path, "after": "actual complete after-state"}
    observed = case.writes(case.events([turn("draft", first + [child]), turn("later", authoritative + append)]))
    assert observed[-1].content == "actual complete after-state" and observed[-1].ok is True


@pytest.mark.parametrize("completion", [True, False])
def test_opaque_command_scope_gap_prevents_cached_append_without_claiming_a_file_write(owner, tmp_path, completion):
    path = str(tmp_path / owner.vocabulary.one("pending") / "draft.md")
    first = tool("first", "write_file", {"path": path, "content": "known"})
    opaque = tool("opaque", "exec", {"command": "python mutator.py", "working_dir": str(tmp_path)})
    append = tool("append", "write_file", {"path": path, "content": "suffix", "mode": "append"})
    rows = first + (opaque if completion else opaque[:1]) + append
    done = case.writes(case.events([turn("draft", rows)]))
    assert done[1].scope_gap and done[1].path == "" and done[1].content is None
    assert done[-1].content is None and done[-1].sha256 is None and case.contents(done) == {}
    record = case.write_records(done)[1]
    assert record["arguments"]["command"] == "python mutator.py" and record["scope_gap"]
    assert record["native_effects"] == [] and record["ok"] is (True if completion else None)
    if completion:
        full = tool("snapshot", "edit_file", {"path": path, "old_text": "x", "new_text": "y"}, ok=False)
        full[-1]["event"]["file_change"] = {"path": path, "after": "fresh observed"}
        recovered = case.writes(case.events([turn("draft", rows + full + append)]))
        assert recovered[-1].content == "fresh observedsuffix"
        overwrite = tool("recover", "write_file", {"path": path, "content": "fresh"})
        assert case.writes(case.events([turn("draft", rows + overwrite + append)]))[-1].content == "freshsuffix"


@pytest.mark.parametrize("name,args", [("exec", {"run_in_background": True}), ("ops_submit", {})])
def test_job_submission_completion_does_not_close_possible_background_mutation(owner, tmp_path, name, args):
    path = str(tmp_path / owner.vocabulary.one("pending") / "draft.md")
    submitted = tool("job", name, {"command": "python mutator.py", **args})
    fresh = tool("fresh", "write_file", {"path": path, "content": "observed"})
    append = tool("append", "write_file", {"path": path, "content": "suffix", "mode": "append"})
    done = case.writes(case.events([turn("draft", submitted + fresh + append)]))
    assert done[0].scope_gap and done[-1].content is None and done[-1].sha256 is None


def test_watch_unknown_recipient_does_not_prove_an_extra_draft_and_failed_observed_state_survives(owner, tmp_path):
    path = str(tmp_path / owner.vocabulary.one("pending") / "draft.md")
    good, suffix = example_letter(2), "suffix"
    parsed = case.parse(good, owner.vocabulary)
    other = good.replace(parsed.recipient, "Another Person")
    first = tool("first", "write_file", {"path": path, "content": good})
    uncertain = tool("uncertain", "edit_file", {"path": path, "old_text": "x", "new_text": "y"}, ok=None)
    append = tool("append", "write_file", {"path": path, "content": suffix, "mode": "append"})

    def measure(rows):
        exchanges = [turn("watch", rows)]
        calls = case.events(exchanges)
        done = case.writes(calls)
        return case.on_call(
            calls, done, case.contents(done), exchanges, "requested-watch", owner.vocabulary, owner.leads
        )

    found = measure(first + uncertain + append)
    assert len(found["pending_drafts"]) == 1 and len(found["pending_drafts"][0]["versions"]) == 2
    version = found["pending_drafts"][0]["versions"][-1]
    assert version["content"] is None and version["recipient"] is None and not version["draft_identity_observed"]
    assert found["pending_drafts"][0]["draft_identity_limits"]
    second = tool("second", "write_file", {"path": path, "content": other})
    separate = measure(first + second + uncertain + append)
    assert len(separate["pending_drafts"]) == 2 and len(separate["unknown_draft_versions"]) == 1
    assert separate["unknown_draft_versions"][0]["content"] is None
    failed = tool("failed", "edit_file", {"path": path, "old_text": "x", "new_text": "y"}, ok=False)
    failed[-1]["event"]["file_change"] = {"path": path, "after": other}
    observed = measure(first + failed)
    assert len(observed["pending_drafts"]) == 2
    assert observed["pending_drafts"][-1]["versions"][0]["operation_outcome"] is False


@pytest.mark.parametrize(
    "mutation",
    [
        "write_file",
        "exec",
        "dotdot",
        "relative",
        "symlink",
        "hardlink",
        "retired_symlink",
        "retired_hardlink",
        "dotdot_snapshot",
        "symlink_snapshot",
        "crlf_edit",
        "known_crlf_edit",
        "known_retired_hardlink",
    ],
)
@pytest.mark.asyncio
async def test_uncertain_native_append_stays_unknown_in_owner_assessor_and_export(scenario, tmp_path, mutation):
    """Verify actual intermediate bytes and uncertainty propagation through both retained assessment routes."""
    from experimental.cultivation.counterpart.owner import handles
    from experimental.harness.assessor.standard import Assessor, Standard
    from experimental.harness.participation.protocols import Exchange
    from experimental.harness.raven_adapter.observe import Recorder, plain
    from experimental.harness.raven_adapter.worker import Execution
    from experimental.harness.scenario.digest import digest as scenario_digest
    from experimental.simulation.bench.record import _exam, _rounds
    from raven.agent.tools.filesystem import EditFileTool, WriteFileTool
    from raven.agent.tools.shell import ExecTool
    from raven.contracts.llm_provider import LLMResponse, ToolCallRequest
    from raven.spine.events import ToolEvent, ToolPhase

    workdir, baseline = tmp_path / "work", tmp_path / "baseline"
    workdir.mkdir()
    baseline.mkdir()
    recorder = Recorder(tmp_path / "native.jsonl")
    writer = WriteFileTool(workspace=workdir)
    manager = case.OutboundOwner(
        scenario,
        None,
        tmp_path / "skills",
        workdir=baseline,
        deliver="pool",
        workdirs={"holdout-xinmao": {"workdir": workdir, "home": tmp_path / "home"}},
    )
    path = workdir / manager.vocabulary.one("pending") / "draft.md"
    good, bad, suffix = example_letter(2), example_letter(2).replace("3.1", "99.9"), "\nannotation"
    recorder.turn_id = "native-turn"
    alias = path.parent / "alias.md"

    async def write(key, content, *, mode="overwrite", incomplete=False):
        target = str(path)
        if key == "uncertain":
            if mutation.startswith("dotdot"):
                target = str(path.parent / ".." / path.parent.name / "." / path.name)
            elif mutation == "relative":
                target = str(Path(path.parent.name) / ".." / path.parent.name / path.name)
            elif "symlink" in mutation or "hardlink" in mutation:
                target = str(alias)
        args = {"path": target, "content": content, "mode": mode}
        recorder.add(
            "runner.event",
            event_type="ToolEvent",
            event=ToolEvent(ToolPhase.START, key, name="write_file", arguments=args),
        )
        result = await writer.execute(args["path"], content, mode=mode)
        assert not str(result).startswith("Error")
        recorder.add(
            "runner.event",
            event_type="ToolEvent",
            event=ToolEvent(
                ToolPhase.COMPLETE,
                key,
                ok=True,
                result_preview=str(getattr(result, "model_text", result)),
                file_change=plain(getattr(result, "file_change", None)),
            ),
        )
        if incomplete:
            recorder.rows[-1]["event"]["ok"] = True if mutation == "known_retired_hardlink" else None
            if not mutation.endswith("snapshot") and mutation != "known_retired_hardlink":
                recorder.rows[-1]["event"]["file_change"] = None

    await write("first", good.replace("\n", "\r\n") if "crlf" in mutation else good, incomplete=mutation == "crlf_edit")
    if "symlink" in mutation:
        alias.symlink_to(path)
    elif "hardlink" in mutation:
        alias.hardlink_to(path)
    if "crlf" in mutation:
        args = {"path": str(path), "old_text": "3.1", "new_text": "99.9"}
        recorder.add(
            "runner.event",
            event_type="ToolEvent",
            event=ToolEvent(ToolPhase.START, "uncertain", name="edit_file", arguments=args),
        )
        result = await EditFileTool(workspace=workdir).execute(**args)
        assert "\r\n" not in result.file_change.after and b"\r\n" in path.read_bytes()
        recorder.add(
            "runner.event",
            event_type="ToolEvent",
            event=ToolEvent(
                ToolPhase.COMPLETE,
                "uncertain",
                ok=True,
                result_preview=str(getattr(result, "model_text", result)),
                file_change=plain(result.file_change),
            ),
        )
    elif mutation != "exec":
        await write("uncertain", bad, incomplete=True)
        if "retired_" in mutation:
            alias.unlink()
    else:
        import shlex
        import sys

        script = tmp_path / "mutator.py"
        script.write_text("from pathlib import Path\nPath(" + repr(str(path)) + ").write_text(" + repr(bad) + ")\n")
        args = {"command": shlex.quote(sys.executable) + " " + shlex.quote(str(script)), "working_dir": str(workdir)}
        recorder.add(
            "runner.event",
            event_type="ToolEvent",
            event=ToolEvent(ToolPhase.START, "uncertain", name="exec", arguments=args),
        )
        result = await ExecTool(working_dir=str(workdir), follow_binding=False).execute(**args)
        assert result.ok is True and result.file_change is None
        recorder.add(
            "runner.event",
            event_type="ToolEvent",
            event=ToolEvent(ToolPhase.COMPLETE, "uncertain", ok=True, result_preview=str(result)),
        )
    await write("append", suffix, mode="append")
    assert path.read_text() == bad + suffix
    (tmp_path / "actual_intermediate.md").write_bytes(path.read_bytes())
    exact_append = (
        path.read_bytes().decode() if mutation.endswith("snapshot") or mutation == "known_crlf_edit" else None
    )
    await write("restore", good + suffix)
    exchange = Exchange(
        "Business time 2026-11-03 10:00; prepare the draft",
        Execution("native-turn", [], recorder.rows, {}, "revision-a", ()),
    )
    sessions = {"holdout-xinmao": [exchange]}
    manager.cards = lambda: {
        "holdout-xinmao": next(p for p in scenario.personas if p.name == "xinmao").play(random.Random(0))
    }

    class Provider:
        def get_default_model(self):
            return "offline/test"

        async def chat_with_retry(self, messages=None, tools=None, **kwargs):
            name = tools[0]["function"]["name"]
            if name == "submit_review":
                result = {
                    "verdicts": [
                        {"id": handle, "result": "unknown", "note": "Uncertain historical state"}
                        for handle in handles(scenario.criteria).values()
                    ],
                    "remark": "Historical state remains unknown",
                    "handover": [],
                }
            else:
                result = {
                    "verdicts": [
                        {"id": criterion.id, "result": "unknown", "note": "Uncertain historical state"}
                        for criterion in scenario.criteria
                    ]
                }
            return LLMResponse(content=None, tool_calls=[ToolCallRequest("offline", name, result)])

    provider = Provider()
    manager.provider = provider
    signal, _, _ = await manager._judge(sessions)
    owner_packet = manager._review_evidence
    owner_refs = owner_packet["evidence"]["references"]["holdout-xinmao"]
    append = next(row for row in owner_refs["file_operations"] if row["call_id"] == "append")
    assert append["ok"] is True and append["content"] == exact_append
    expected_sha = hashlib.sha256(exact_append.encode()).hexdigest() if exact_append is not None else None
    assert append["sha256"] == expected_sha
    assert append["arguments"]["content"] == suffix
    assert path.read_text() == good + suffix
    criterion_rows = [criterion.model_dump() for criterion in scenario.criteria]
    source = {
        "root": ROOT,
        "cards": [ROOT / "personas" / "xinmao.md"],
        "owner_criteria": criterion_rows,
        "exam_criteria": criterion_rows,
    }
    severity = {criterion.id: criterion.severity for criterion in scenario.criteria}
    raw = {
        "sessions": plain(sessions),
        "signals": [],
        "analysis": [{"source": "agency", "scorecard": plain(signal), **owner_packet}],
    }
    owner_export = _rounds({"rounds": [raw]}, tmp_path, source, severity, {})[0]
    assert owner_export["owner_assessment_binding"] == "session_and_turn_ids"
    retained = owner_export["drills"][0]["references"]["file_operations"]
    assert next(row for row in retained if row["call_id"] == "append")["sha256"] == expected_sha

    standard = Standard.declared(
        ((criterion.id, criterion.check) for criterion in scenario.criteria),
        applies_when={criterion.id: criterion.applies_when for criterion in scenario.criteria},
    )
    references = {**owner_refs, "scenario_digest": scenario_digest(ROOT)}
    assessor = Assessor(
        provider,
        standard,
        sources=("declared",),
        task=scenario.profile,
        references=lambda _: {"holdout-xinmao": references},
        norms=lambda: scenario.standing_norms(scenario.kinds),
        materials=lambda: scenario.evidence_materials(scenario.kinds, role="counterpart"),
    )
    verdicts = await assessor._measure(provider, sessions)
    assert all(item.result == "unknown" for item in verdicts)
    assessed = assessor.assessments[-1]
    ref = assessed["evidence"]["references"]["holdout-xinmao"]
    assert next(row for row in ref["file_operations"] if row["call_id"] == "append")["content"] == exact_append
    exam_export = _exam(raw, 1, tmp_path, {"xinmao"}, severity, json.loads(json.dumps(assessor.assessments)), source)
    assert exam_export["assessment_binding"] == "session_and_turn_ids"
    ref = exam_export["drills"][0]["references"]
    assert next(row for row in ref["file_operations"] if row["call_id"] == "append")["sha256"] == expected_sha


def test_equivalent_paths_share_targets_and_pending_overlap_state(owner, tmp_path):
    path = tmp_path / owner.vocabulary.one("pending") / "draft.md"
    alias = path.parent / ".." / path.parent.name / path.name
    known = tool("known", "write_file", {"path": str(path), "content": "known"})
    appended = tool("append", "write_file", {"path": str(alias), "content": "suffix", "mode": "append"})
    done = case.writes(case.events([turn("draft", known + appended)]), tmp_path)
    assert done[-1].path == str(path) and done[-1].resource_identity == str(path)
    assert done[-1].content == "knownsuffix"
    pending = tool("pending", "edit_file", {"path": str(alias), "old_text": "x", "new_text": "y"})[:1]
    blocked = case.writes(case.events([turn("draft", known + pending + appended)]), tmp_path)
    assert blocked[-1].content is None and blocked[-1].sha256 is None
    assert blocked[1].arguments["path"] == str(alias) and blocked[1].path == str(path)


@pytest.mark.parametrize("alias_kind", ["dotdot", "symlink", "hardlink", "retired_symlink", "retired_hardlink"])
def test_delivery_resource_aliases_cannot_certify_an_earlier_mutable_snapshot(owner, tmp_path, alias_kind):
    path = tmp_path / owner.vocabulary.one("pending") / "draft.md"
    path.parent.mkdir()
    path.write_text(example_letter(2))
    alias = path.parent / "alias.md"
    if alias_kind == "dotdot":
        alias = path.parent / ".." / path.parent.name / path.name
    elif "symlink" in alias_kind:
        alias.symlink_to(path)
    else:
        alias.hardlink_to(path)
    if alias_kind.startswith("retired_"):
        alias.unlink()
    versions = case.delivered_versions([turn("draft", [], [str(path)]), turn("revision", [], [str(alias)])])
    assert versions[0]["sha256"] is None and versions[0]["unavailable"]
    if alias_kind == "dotdot":
        assert versions[1]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    else:
        assert versions[1]["sha256"] is None and versions[1]["resource_limits"]


@pytest.mark.asyncio
@pytest.mark.parametrize("known_base", [True, False])
async def test_native_crlf_edit_keeps_text_and_byte_identity_distinct(owner, tmp_path, known_base):
    """An actual native edit's normalized text cannot silently certify its preserved CRLF bytes."""
    from experimental.harness.raven_adapter.observe import plain
    from raven.agent.tools.filesystem import EditFileTool, WriteFileTool

    path = tmp_path / owner.vocabulary.one("pending") / "draft.md"
    writer, editor = WriteFileTool(workspace=tmp_path), EditFileTool(workspace=tmp_path)
    original = example_letter(2).replace("\n", "\r\n")
    result = await writer.execute(str(path), original)
    first = tool("first", "write_file", {"path": str(path), "content": original}, ok=True if known_base else None)
    if known_base:
        first[-1]["event"]["file_change"] = plain(result.file_change)
    result = await editor.execute(str(path), "3.1", "99.9")
    assert "\r\n" in path.read_bytes().decode() and "\r\n" not in result.file_change.after
    edited = tool("edit", "edit_file", {"path": str(path), "old_text": "3.1", "new_text": "99.9"})
    edited[-1]["event"]["file_change"] = plain(result.file_change)
    edit_bytes = path.read_bytes()
    await writer.execute(str(path), "suffix", mode="append")
    appended = tool("append", "write_file", {"path": str(path), "content": "suffix", "mode": "append"})
    rows = first + edited + appended
    done = case.writes(case.events([turn("draft", rows)]), tmp_path)
    edit = next(write for write in done if write.call_id == "edit")
    if known_base:
        assert edit.content.encode() == edit_bytes and edit.sha256 == hashlib.sha256(edit_bytes).hexdigest()
        assert done[-1].content.encode() == path.read_bytes()
        assert done[-1].sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    else:
        assert edit.content == result.file_change.after and not edit.bytes_known and edit.sha256 is None
        assert done[-1].content is None and done[-1].sha256 is None
        measured = case.facts(owner, "xinmao", [turn("draft", rows)], {"workdir": tmp_path})
        historical = next(row for row in measured["letters"].values() if row["order"] == edit.order)
        assert historical["sha256"] is None and "99.9" in historical["content"]
        current = next(row for key, row in measured["letters"].items() if key.startswith("state:"))
        assert current["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_non_text_current_state_is_explicitly_unavailable(owner, tmp_path):
    path = tmp_path / owner.vocabulary.one("pending") / "draft.md"
    path.parent.mkdir()
    path.write_bytes(b"\xff\xfe invalid text")
    measured = case.facts(owner, "xinmao", [turn("draft", [])], {"workdir": tmp_path})
    assert str(path) in measured["unreadable_state_files"]
    assert str(path) not in measured["current_state"]
    assert not measured["letters"]
