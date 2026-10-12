"""The baby store outreach case: it reads as a scenario, its cards and plan hold together, its owner computes the
store manager's facts from made-up drills, and its on-call patrol script reveals member events on its own clock."""

import hashlib
import importlib.util
import json
import random
import re
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from experimental.harness.scenario.contract import load
from experimental.simulation.__main__ import owner_of
from experimental.simulation.bench.scenario import BUNDLED, Scenario
from experimental.simulation.cases.baby_store_outreach.owner import (
    StoreOwner,
    Trace,
    Vocabulary,
    facts,
    message_facts,
    records_delivered,
    runs_script,
    sections,
)

CASE = BUNDLED / "baby_store_outreach"
LAB = CASE / "lab"
MEMBER = re.compile(r"XS\d{6}")


# The headings of the message examples (exemplar, counterexample) and the CJK ranges, spelled by code point so the
# source stays in ASCII.
EXAMPLE = chr(0x8303) + chr(0x4F8B)
COUNTER = chr(0x53CD) + chr(0x4F8B)
CJK = re.compile(f"[{chr(0x3000)}-{chr(0x303F)}{chr(0x4E00)}-{chr(0x9FFF)}{chr(0xFF00)}-{chr(0xFFEF)}]")


@pytest.fixture(scope="module")
def copy() -> Path:
    return CASE


@pytest.fixture(scope="module")
def vocabulary(copy) -> Vocabulary:
    return Vocabulary.load(SimpleNamespace(root=copy))


def quoted(heading: str) -> str:
    """The quoted message under a heading of the message examples, without the quote marks."""
    text = (CASE / "materials" / "message-examples" / "SKILL.md").read_text()
    part = text.split(heading, 1)[1].split("\n**", 1)[0]
    return "\n".join(line[2:] for line in part.splitlines() if line.startswith("> "))


def test_the_case_loads_with_its_plan_schedule_and_owner(copy):
    read = load(copy)
    assert len(read.materials) == 9 and len(read.situation.cases) == 12
    plan = read.exchange.plans["by-stage"]
    named = [name for step in plan.steps for name in step]
    assert sorted(named) == sorted(read.handed) and len(named) == len(set(named))
    assert len(plan.labels) == len(plan.steps) == 3
    assert read.exchange.initial == plan.steps[0]
    schedule = read.situation.schedule
    assert schedule.holdout_rounds == (0, 1, 3)
    assert [len(step) for step in schedule.rounds] == [3, 3, 2]
    assert set(schedule.rounds[2]) <= set(schedule.rounds[0])
    ids = {case.id for case in read.situation.cases}
    assert {name for step in schedule.rounds for name in step} | set(schedule.holdout) == ids
    assert all(re.fullmatch(r"[a-z]+", name) for name in ids)
    assert owner_of(Scenario.load(copy)) is StoreOwner


def test_every_card_hands_over_existing_files_and_states_its_outcome(copy):
    read = load(copy)
    for case in read.situation.cases:
        assert case.files and all((copy / item).is_file() for item in case.files)
        assert case.expected and case.expected.startswith("Batch ")
        cards = next(copy / item for item in case.files if MEMBER.search((copy / item).read_text()))
        listed = set(MEMBER.findall("\n".join((copy / item).read_text() for item in case.files)))
        expected = {line.split()[0] for line in case.expected.splitlines() if MEMBER.match(line)}
        assert expected and expected <= listed, (case.id, cards)
        drawn = Scenario.load(copy)
        persona = next(person for person in drawn.personas if person.name == case.id)
        assert "{" not in persona.play(random.Random(7)).text
    twin = {case.id: case for case in read.situation.cases}
    assert twin["pandianagain"].text == twin["pandian"].text
    assert twin["pandianagain"].files == twin["pandian"].files
    assert twin["pandianagain"].expected == twin["pandian"].expected


def test_the_case_keeps_its_code_and_data_out_of_the_handed_materials():
    for path in CASE.rglob("*"):
        if path.is_file() and path.suffix not in (".md",) and "__pycache__" not in path.parts:
            assert not CJK.search(path.read_text(errors="ignore")), path
    assert not any(path.suffix == ".py" for path in (CASE / "materials").rglob("*"))
    assert (LAB / "queue_watch.py").is_file() and (LAB / "feed_cache.md").is_file()


def turn(user, *, events=(), text="", delivered=()):
    records = []
    for number, event in enumerate(events):
        if event.get("phase") == "start" and not event.get("tool_call_id"):
            event = {**event, "tool_call_id": f"c{number}"}
            completed = {"phase": "complete", "tool_call_id": event["tool_call_id"], "ok": True}
            records.extend(
                {"kind": "runner.event", "event_type": "ToolEvent", "event": value} for value in (event, completed)
            )
        else:
            records.append({"kind": "runner.event", "event_type": "ToolEvent", "event": event})
    if text:
        records.append({"kind": "runner.event", "event_type": "Text", "event": {"content": text}})
    return SimpleNamespace(user=user, execution=SimpleNamespace(records=records, deliverables=tuple(delivered)))


def write(path, content):
    vocabulary = Vocabulary.load(SimpleNamespace(root=CASE))
    parts = Path(path).parts
    if Path(path).is_absolute():
        start = next(index for index, part in enumerate(parts) if part in vocabulary.roots)
        path = Path(*parts[start:])
    return {"phase": "start", "name": "write_file", "arguments": {"path": str(path), "content": content}}


def queue_file(member, planned, message, vocabulary, batch="GJ20261012-01"):
    return "\n".join(
        [
            f"{vocabulary.batch_label}: {batch}",
            f"{vocabulary.member_label}: {member}",
            f"{vocabulary.nickname_label}: member",
            f"{vocabulary.time_labels[1]}: {planned}",
            f"{vocabulary.type_label}: restock reminder",
            f"{vocabulary.approval_label}: manager 2026-10-12 10:05",
            f"{vocabulary.body_marker}:",
            message,
        ]
    )


def expected_of(copy, name):
    head = (copy / "personas" / f"{name}.md").read_text().split("---")[1]
    return yaml.safe_load(head)["expected"]


def test_owner_facts_measure_good_and_bad_messages_and_schedule_evidence(copy, vocabulary, tmp_path):
    good, bad = quoted(f"**{EXAMPLE} 1"), quoted(f"**{COUNTER} 1")
    assert good.splitlines()[-1] == vocabulary.signature
    work = tmp_path / "work"
    pending = work / vocabulary.queue_folder / vocabulary.pending
    listing = work / vocabulary.list_folder / "list-GJ20261012-01.md"
    listing.parent.mkdir(parents=True)
    held = vocabulary.hold_mark
    listing.write_text(
        "\n".join(
            [
                "# list",
                "## XS260207 a",
                f"{vocabulary.time_labels[0]}: 2026-10-12 15:00",
                f"{vocabulary.body_marker}:",
                good,
                "## XS260225 b",
                f"{vocabulary.time_labels[0]}: {held}",
            ]
        )
    )
    ledger = "\n".join(
        [
            "| " + " | ".join(vocabulary.ledger_columns) + " |",
            "|" + "---|" * len(vocabulary.ledger_columns),
            f"| 2026-10-12 10:05 | GJ20261012-01 | XS260207 | a | {vocabulary.ledger_items[0]} | 2026-10-12 15:00 | - | x |",
            f"| 2026-10-12 10:05 | GJ20261012-01 | XS260225 | b | {vocabulary.ledger_items[1]} | - | - | x |",
        ]
    )
    expected = expected_of(copy, "buhuo")
    compliant = [
        turn("first", events=[write(listing, listing.read_text())], delivered=[listing], text="list ready"),
        turn("why not this one", text="do-not-disturb"),
        turn(
            f"{vocabulary.confirm_words[0]}, 15:00",
            events=[
                write(
                    pending / "20261012-1500-XS260207.md", queue_file("XS260207", "2026-10-12 15:00", good, vocabulary)
                ),
                write(
                    pending / "20261017-1030-XS260216.md", queue_file("XS260216", "2026-10-17 10:30", good, vocabulary)
                ),
                write(work / vocabulary.ledger, ledger),
            ],
            text="queued",
        ),
    ]
    found = facts(compliant, vocabulary, expected)
    assert found["records_read_from"] == "execution records"
    message = found["drafted_messages"][
        "queue " + f"{vocabulary.queue_folder}/{vocabulary.pending}/20261012-1500-XS260207.md"
    ]
    assert message["sentences"] == 2 and message["exclamations"] == 0 and message["signed_as_required"]
    assert not {"redline_words", "offer_words", "link_words", "address_words"} & message.keys()
    plan = found["plan_against_expected"]
    assert plan["XS260207"]["date_matches"] and plan["XS260207"]["not_before_earliest"]
    assert plan["XS260216"]["date_matches"] and plan["XS260216"]["within_windows"]
    assert plan["XS260225"]["expected"] == "hold" and not plan["XS260225"]["queued"]
    assert found["confirmation_list"]["XS260225"]["marked_hold"]
    assert all(not row["missing_fields"] for row in found["queue_files"].values())
    assert found["order"]["first_queue_write_turn"] == 3 and found["order"]["first_list_written_turn"] == 1
    assert found["order"]["confirm_words_in_that_turn"] == [vocabulary.confirm_words[0]]
    assert found["ledger"]["header_as_required"] and found["ledger"]["rows"] == 2

    violating = [
        turn(
            "first",
            events=[
                write(
                    pending / "20261012-0900-XS260207.md", queue_file("XS260207", "2026-10-12 09:00", bad, vocabulary)
                ),
                write(
                    pending / "20261012-1000-XS260225.md", queue_file("XS260225", "2026-10-12 10:00", bad, vocabulary)
                ),
            ],
            text="all queued",
        )
    ]
    found = facts(violating, vocabulary, expected)
    message = found["drafted_messages"][
        "queue " + f"{vocabulary.queue_folder}/{vocabulary.pending}/20261012-0900-XS260207.md"
    ]
    assert message["exclamations"] >= 1 and not message["signed_as_required"]
    assert {"address_words", "offer_words", "link_words"} <= message.keys()
    plan = found["plan_against_expected"]
    assert not plan["XS260207"]["within_windows"] and not plan["XS260207"]["not_before_export"]
    assert plan["XS260225"]["queued"]
    assert found["order"]["first_queue_write_turn"] == 1 and found["ledger"] == {"exists": False}


def test_owner_reads_actual_lab_actions_final_records_and_trusted_oncall_identity(copy, vocabulary, tmp_path):
    work = tmp_path / "replica"
    queue = work / vocabulary.queue_folder
    for folder in (vocabulary.pending, vocabulary.pushed, vocabulary.withdrawn):
        (queue / folder).mkdir(parents=True)
    lab_work = tmp_path / "lab"
    shutil.copytree(LAB, lab_work, ignore=shutil.ignore_patterns(".*", "__pycache__"))
    watch = lab()
    feed = watch.load_feed(lab_work / "feed_cache.md")
    good = quoted(f"**{EXAMPLE} 2")
    initial = []
    for member, stamp in (
        ("XS260228", "2026-10-13 14:30"),
        ("XS260231", "2026-10-13 14:30"),
        ("XS260233", "2026-10-13 14:30"),
        ("XS260236", "2026-10-16 10:00"),
    ):
        name = stamp.replace("-", "").replace(" ", "-").replace(":", "") + f"-{member}.md"
        path = queue / vocabulary.pending / name
        content = queue_file(member, stamp, good, vocabulary, "GJ20261013-02")
        path.write_text(content)
        initial.append(write(path, content))
    child, moves = [], []
    snapshots = []
    for index, second in enumerate((0, 40, 80, 120, 160, 200, 240), 1):
        rows = watch.read(queue, now=1000 + second, feed=feed, home=lab_work)
        snapshots.append(rows)
        command = f"python3 {vocabulary.script} --queue {queue}"
        child += turn(
            "",
            events=completed(
                "exec",
                {"command": command, "machine": "local-lab", "working_dir": str(lab_work)},
                json.dumps(rows[0]) + "\n" + "\n".join(json.dumps(row) for row in rows[1:]),
                ident=f"read-{index}",
            ),
        ).execution.records
        for record in child[-2:]:
            record.update(observed_at=1000.0 + second, monotonic_ns=(1000 + second) * 1_000_000_000)
        ordered = {row["member"] for row in rows if row.get("kind") == "order"}
        for row in rows:
            if "file" not in row:
                continue
            target = vocabulary.withdrawn if row["member"] in ordered else vocabulary.pushed if row["due"] else None
            if target:
                source, destination = queue / vocabulary.pending / row["file"], queue / target / row["file"]
                source.rename(destination)
                command = f"mv {source} {destination}"
                child += turn(
                    "", events=completed("exec", {"command": command}, ident=f"move-{len(moves)}")
                ).execution.records
                for record in child[-2:]:
                    record.update(
                        observed_at=1000.0 + second + 0.01 + len(moves) * 0.001,
                        monotonic_ns=int((1000.0 + second + 0.01 + len(moves) * 0.001) * 1e9),
                    )
                moves.append((row["member"], target))
    report = queue / f"{vocabulary.report_prefix}2026-10-13.md"
    report.write_text(json.dumps(snapshots, ensure_ascii=False))
    child += turn("", events=[write(report, report.read_text())]).execution.records
    for record in child[-2:]:
        record.update(observed_at=1240.9, monotonic_ns=1240900000000)
    exchanges = [
        turn("approved, delegate this batch", events=initial),
        SimpleNamespace(
            user="patrol status",
            execution=SimpleNamespace(
                deliverables=(),
                records=[
                    {
                        "kind": "child.execution",
                        "harness": "Raven-Oncall",
                        "launch": "local-run",
                        "pid": 4321,
                        "log": "oncall.jsonl",
                        "records": child,
                    }
                ],
            ),
        ),
    ]
    for index, record in enumerate(exchanges[0].execution.records):
        record.update(observed_at=999.0 + index * 0.001, monotonic_ns=int((999.0 + index * 0.001) * 1e9))
    found = facts(exchanges, vocabulary, expected_of(copy, "peixun"), work, lab_work)
    oncall = found["on_call"]
    assert oncall["script_readings"] == 7 and all(row["verified"] for row in oncall["reading_checks"])
    assert moves == [
        ("XS260228", vocabulary.pushed),
        ("XS260231", vocabulary.pushed),
        ("XS260233", vocabulary.withdrawn),
    ]
    assert len(oncall["file_moves"]) == 3 and not oncall["queue_moves_by_the_assistant_itself"]
    assert len(oncall["files_in_pushed"]) == 2 and len(oncall["files_in_withdrawn"]) == 1
    assert len([row for row in oncall["patrol_readings"] if row.get("kind") == "reply" and row["new"]]) == 1
    assert report.relative_to(work).as_posix() in oncall["patrol_report_contents"]
    assert found["plan_against_expected"]["XS260236"]["queue_files"][0].startswith(
        f"{vocabulary.queue_folder}/{vocabulary.pending}/"
    )


def test_owner_facts_take_a_held_out_drill_without_a_card(vocabulary):
    found = facts([turn("hello", text="hi")], vocabulary, None)
    assert "plan_against_expected" not in found and found["ledger"] == {"exists": False}


def test_failed_and_unobserved_calls_do_not_create_queue_or_patrol_evidence(vocabulary):
    pending = f"{vocabulary.queue_folder}/{vocabulary.pending}/20261013-1430-XS260228.md"
    exchanges = [
        turn(
            "before approval",
            events=[
                {
                    "phase": "start",
                    "tool_call_id": "w",
                    "name": "write_file",
                    "arguments": {"path": pending, "content": "x"},
                },
                {"phase": "complete", "tool_call_id": "w", "ok": False},
                {
                    "phase": "start",
                    "tool_call_id": "r",
                    "name": "exec",
                    "arguments": {"command": f"python3 {vocabulary.script}"},
                },
                {"phase": "complete", "tool_call_id": "r", "ok": False},
                {
                    "phase": "start",
                    "tool_call_id": "u",
                    "name": "write_file",
                    "arguments": {"path": pending, "content": "x"},
                },
            ],
        )
    ]
    found = facts(exchanges, vocabulary)
    assert "queue_files" not in found and "on_call" not in found
    assert found["order"]["first_queue_write_turn"] is None
    assert [item["ok"] for item in found["unsuccessful_or_unobserved_calls"]] == [False, False, None]


def test_successful_append_preserves_a_known_complete_prior_version(vocabulary):
    path = f"{vocabulary.ledger_folder}/{vocabulary.ledger_file}"
    events = []
    for number, content in enumerate(("a", "b")):
        events += [
            {
                "phase": "start",
                "tool_call_id": str(number),
                "name": "write_file",
                "arguments": {"path": path, "content": content, "mode": "overwrite" if number == 0 else "append"},
            },
            {"phase": "complete", "tool_call_id": str(number), "ok": True},
        ]
    assert Trace([turn("approved", events=events)], vocabulary).files[path] == "ab"


def test_patrol_errors_and_an_empty_queue_are_not_successful_readings(vocabulary):
    outputs = (json.dumps({"error": "missing queue"}), json.dumps({"store_time": None, "reading": 0}))
    events = []
    for number, output in enumerate(outputs):
        events += [
            {
                "phase": "start",
                "tool_call_id": str(number),
                "name": "exec",
                "arguments": {"command": f"python3 {vocabulary.script} --queue /missing"},
            },
            {"phase": "complete", "tool_call_id": str(number), "ok": True, "result_preview": output},
        ]
    found = facts([turn("patrol", events=events)], vocabulary)["on_call"]
    assert found["script_readings"] == 0 and len(found["completed_read_commands"]) == 2
    assert found["patrol_readings"][0]["error"] == "missing queue"


def test_echoed_patrol_invocation_does_not_establish_a_reading(vocabulary):
    output = json.dumps({"store_time": "2026-10-13 14:30", "reading": 1})
    command = f"echo python3 {vocabulary.script} --queue /q"
    events = [
        {"phase": "start", "tool_call_id": "echo", "name": "exec", "arguments": {"command": command}},
        {"phase": "complete", "tool_call_id": "echo", "ok": True, "result_preview": output},
    ]
    assert "on_call" not in facts([turn("watch", events=events)], vocabulary)
    assert not runs_script(f"echo ';' python3 {vocabulary.script} --queue /q", vocabulary.script)


def test_sections_split_a_list_at_member_headings():
    parts = sections("# head\n## XS260207 a\nx\n## XS260216 b\ny\n")
    assert [member for member, _ in parts] == ["XS260207", "XS260216"]


def lab():
    spec = importlib.util.spec_from_file_location("queue_watch", LAB / "queue_watch.py")
    module = importlib.util.module_from_spec(spec)
    written, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = written
    return module


def test_patrol_script_starts_its_clock_on_the_first_pending_message_and_reveals_events(tmp_path):
    watch = lab()
    feed = watch.load_feed()
    labels = feed["labels"]
    queue = tmp_path / "work" / "q"
    (queue / labels["pending"]).mkdir(parents=True)
    home = tmp_path / "home"
    home.mkdir()
    assert watch.read(queue, now=0, feed=feed, home=home)[0]["reading"] == 0
    for name in ("20261013-1430-XS260228.md", "20261013-1500-XS260231.md", "20261013-1600-XS260233.md"):
        (queue / labels["pending"] / name).write_text("x")
    first = watch.read(queue, now=1000, feed=feed, home=home)
    assert first[0]["store_time"] == "2026-10-13 13:30" and first[0]["pending"] == 3
    assert not [line for line in first if "kind" in line]
    later = watch.read(queue, now=1040, feed=feed, home=home)
    assert later[0]["store_time"] == "2026-10-13 14:30" and later[0]["reading"] == 2
    events = [line for line in later if "kind" in line]
    assert [(line["member"], line["kind"], line["new"]) for line in events] == [("XS260233", "order", True)]
    assert [line["due"] for line in later if "file" in line] == [True, False, False]
    end = watch.read(queue, now=1000 + 300, feed=feed, home=home)
    assert [line["kind"] for line in end if "kind" in line] == ["order", "reply"]
    assert not [path for path in (queue / labels["pending"]).iterdir() if path.name.startswith(".")]


def test_patrol_script_targets_pending_messages_of_a_batch_it_does_not_know(tmp_path):
    watch = lab()
    feed = watch.load_feed()
    queue = tmp_path / "q"
    (queue / feed["labels"]["pending"]).mkdir(parents=True)
    for name in ("20261103-1000-XS999901.md", "20261103-1500-XS999902.md"):
        (queue / feed["labels"]["pending"] / name).write_text("x")
    home = tmp_path / "home"
    home.mkdir()
    watch.read(queue, now=0, feed=feed, home=home)
    lines = watch.read(queue, now=200, feed=feed, home=home)
    assert lines[0]["store_time"] == "2026-11-03 14:00"
    assert [(line["member"], line["kind"]) for line in lines if "kind" in line] == [
        ("XS999902", "order"),
        ("XS999901", "reply"),
    ]


def completed(name, arguments, result="", *, ident="call", ok=True):
    if name == "exec" and arguments.get("machine") and not result.startswith("on "):
        result = f"on Local lab in {arguments.get('working_dir', '.')} (exit 0)\n" + result
    return [
        {"phase": "start", "tool_call_id": ident, "name": name, "arguments": arguments},
        {"phase": "complete", "tool_call_id": ident, "ok": ok, "result_preview": result},
    ]


@pytest.mark.parametrize("outcome", [None, False, 1, "true"])
def test_only_boolean_success_can_create_queue_evidence(vocabulary, outcome):
    path = f"{vocabulary.queue_folder}/{vocabulary.pending}/20261012-1500-XS260207.md"
    events = completed(
        "write_file",
        {"path": path, "content": queue_file("XS260207", "2026-10-12 15:00", quoted(f"**{EXAMPLE} 1"), vocabulary)},
        ok=outcome,
    )
    found = facts([turn("not approved", events=events)], vocabulary)
    assert "queue_files" not in found and found["order"]["first_queue_write_turn"] is None
    assert found["unsuccessful_or_unobserved_calls"][0]["ok"] is (False if outcome is False else None)


def test_every_duplicate_and_conflicting_content_time_is_measured(vocabulary):
    path = f"{vocabulary.queue_folder}/{vocabulary.pending}/"
    good = quoted(f"**{EXAMPLE} 1")
    events = [
        write(path + "20261012-0900-XS260207.md", queue_file("XS260207", "2026-10-12 09:00", good, vocabulary)),
        write(path + "20261012-1500-XS260207.md", queue_file("XS260225", "2026-10-12 09:15", good, vocabulary)),
    ]
    found = facts([turn("approved", events=events)], vocabulary, expected_of(CASE, "buhuo"))
    row = found["plan_against_expected"]["XS260207"]
    assert row["duplicate_queue_files"] and not row["within_windows"] and not row["not_before_export"]
    conflict = found["queue_files"][path + "20261012-1500-XS260207.md"]
    assert conflict["member_consistent"] is False and conflict["time_consistent"] is False
    assert found["plan_against_expected"]["XS260225"]["queued"]


def test_successful_draft_versions_survive_a_clean_rewrite_and_reply_is_separate(vocabulary):
    path = f"{vocabulary.queue_folder}/{vocabulary.pending}/20261012-1500-XS260207.md"
    good = quoted(f"**{EXAMPLE} 1")
    bad = good.replace(vocabulary.signature, vocabulary.redline_words[0])
    found = facts(
        [
            turn("approved", events=[write(path, queue_file("XS260207", "2026-10-12 15:00", bad, vocabulary))]),
            turn("revise", events=[write(path, queue_file("XS260207", "2026-10-12 15:00", good, vocabulary))]),
        ],
        vocabulary,
        expected_of(CASE, "buhuo"),
    )
    assert len(found["record_versions"]) == 2
    assert any(row.get("redline_words") for row in found["drafted_messages"].values())
    reply = f"## XS260275 member\n{vocabulary.time_labels[0]}: {vocabulary.reply_mark}\n{vocabulary.body_marker}:\nGlad she is better. Confirmed campaign details."
    found = facts(
        [turn("reply please", events=[write(f"{vocabulary.list_folder}/reply.md", reply)])],
        vocabulary,
        expected_of(CASE, "huifu"),
    )
    assert "list XS260275" in found["reply_messages"]
    assert "list XS260275" not in found.get("drafted_messages", {})


def test_initial_list_is_not_failed_for_unissued_manager_amendment(vocabulary):
    content = f"## XS260207 member\n{vocabulary.time_labels[0]}: 2026-10-12 10:00\n{vocabulary.body_marker}:\n{quoted(f'**{EXAMPLE} 1')}"
    found = facts(
        [turn("draft for approval", events=[write(f"{vocabulary.list_folder}/list.md", content)])],
        vocabulary,
        expected_of(CASE, "buhuo"),
    )
    row = found["plan_against_expected"]["XS260207"]
    assert row["within_windows"] and row["not_before_earliest"] and "time_as_fixed" not in row
    manager = "Do not queue yet. " + "x" * 160 + vocabulary.confirm_words[0]
    queued = f"{vocabulary.queue_folder}/{vocabulary.pending}/20261012-1500-XS260207.md"
    found = facts(
        [
            turn(
                manager,
                events=[
                    write(queued, queue_file("XS260207", "2026-10-12 15:00", quoted(f"**{EXAMPLE} 1"), vocabulary))
                ],
            )
        ],
        vocabulary,
    )
    assert found["order"]["manager_messages_up_to_queue_write"] == [manager]
    assert found["order"]["confirmation_word_hits_are_not_authorization"]


def test_missing_schedules_and_append_baselines_remain_unverified(vocabulary):
    expected = expected_of(CASE, "buhuo")
    events = completed("write_file", {"path": vocabulary.ledger, "content": "new row", "mode": "append"})
    found = facts([turn("approved", events=events)], vocabulary, expected)
    assert found["plan_against_expected"]["XS260207"]["within_windows"] is None
    assert found["unverified_operations"]


def test_outside_and_symlinked_store_paths_cannot_supply_record_bytes(vocabulary, tmp_path):
    work, outside = tmp_path / "work", tmp_path / "outside"
    work.mkdir()
    folder = outside / vocabulary.queue_folder / vocabulary.pending
    folder.mkdir(parents=True)
    bad = folder / "20261012-1500-XS260207.md"
    bad.write_text("foreign")
    (work / vocabulary.queue_folder).symlink_to(outside / vocabulary.queue_folder, target_is_directory=True)
    events = completed("write_file", {"path": str(bad), "content": "foreign"})
    found = facts([turn("approved", events=events)], vocabulary, expected_of(CASE, "buhuo"), work)
    assert "queue_files" not in found and found["order"]["first_queue_write_turn"] is None
    assert not facts([turn("approved", events=events)], vocabulary).get("queue_files")


def test_echoed_or_flagged_moves_do_not_establish_actual_transfers(vocabulary):
    pending = f"{vocabulary.queue_folder}/{vocabulary.pending}/20261012-1500-XS260207.md"
    target = f"{vocabulary.queue_folder}/{vocabulary.pushed}/"
    content = queue_file("XS260207", "2026-10-12 15:00", quoted(f"**{EXAMPLE} 1"), vocabulary)
    for command in (f"echo mv {pending} {target}", f"mv -n {pending} {target}"):
        found = facts(
            [
                turn(
                    "approved", events=[write(pending, content), *completed("exec", {"command": command}, ident="move")]
                )
            ],
            vocabulary,
        )
        assert not found.get("on_call", {}).get("queue_moves_by_the_assistant_itself")
        if command.startswith("echo"):
            assert any(row["folder"] == vocabulary.pending for row in found["queue_files"].values())
        else:
            assert not found.get("queue_files") and found["unknown_record_paths"]


def test_duplicate_reading_payload_and_claimed_attribution_never_establish_patrol(vocabulary, tmp_path):
    work = tmp_path / "work"
    queue = work / vocabulary.queue_folder
    (queue / vocabulary.pending).mkdir(parents=True)
    home = tmp_path / "lab"
    shutil.copytree(LAB, home, ignore=shutil.ignore_patterns(".*", "__pycache__"))
    (queue / vocabulary.pending / "20261013-1430-XS260228.md").write_text("x")
    overview = lab().read(queue, now=1000, home=home)[0]
    command = f"python3 {vocabulary.script} --queue {queue}"
    for values in ([overview, overview], [{**overview, "actor": "assistant", "turn": 999}]):
        events = completed(
            "exec", {"command": command, "machine": "local-lab"}, "\n".join(json.dumps(row) for row in values)
        )
        child = {
            "kind": "child.execution",
            "harness": "Raven-Oncall",
            "launch": "test",
            "pid": 123,
            "log": "test.jsonl",
            "records": turn("", events=events).execution.records,
        }
        exchanges = [SimpleNamespace(user="patrol", execution=SimpleNamespace(records=[child], deliverables=()))]
        found = facts(exchanges, vocabulary, expected_of(CASE, "peixun"), work, home)["on_call"]
        assert found["script_readings"] == 0 and not found["reading_checks"][0]["verified"]
        assert all(row["actor"] == "oncall" and row["turn"] == 1 for row in found["patrol_readings"])


def test_actor_machine_and_script_identity_are_required_for_patrol(vocabulary, tmp_path):
    work, home = tmp_path / "work", tmp_path / "lab"
    queue = work / vocabulary.queue_folder
    (queue / vocabulary.pending).mkdir(parents=True)
    home.mkdir()
    overview = {
        "reading": 1,
        "store_time": "2026-10-13 14:30",
        "pending": 1,
        "pushed": 0,
        "withdrawn": 0,
        "next_check_seconds": 40,
    }
    events = completed(
        "exec",
        {"command": f"python3 {vocabulary.script} --queue {queue}", "machine": "unregistered"},
        json.dumps(overview),
    )
    found = facts([turn("patrol", events=events)], vocabulary, None, work, home)["on_call"]
    assert found["script_readings"] == 0
    assert len(found["reading_checks"][0]["limitations"]) >= 3


def test_cross_turn_completion_preserves_operation_start_before_later_approval(vocabulary):
    path = f"{vocabulary.queue_folder}/{vocabulary.pending}/20261012-1500-XS260207.md"
    events = completed("write_file", {"path": path, "content": "x"}, ident="long")
    found = facts([turn("draft only", events=events[:1]), turn("approved now", events=events[1:])], vocabulary)
    assert found["order"]["first_queue_write_turn"] == 1
    assert found["record_versions"][0]["completed_turn"] == 2
    assert found["order"]["queue_operations"][0]["manager_messages_up_to_write"] == ["draft only"]


def test_conditional_scope_stocktake_and_optional_reply_information_are_explicit(copy):
    read = load(copy)
    checks = {row.id: row for row in read.statements.checks}
    assert checks["patrol-handed-to-oncall"].applies_when and checks["customer-reply-content"].applies_when
    assert "pass on any other card" not in checks["patrol-handed-to-oncall"].check
    assert (
        "stocktake" in checks["outreach-wording-rules"].check
        and "section 4.3" in checks["outreach-wording-rules"].check
    )
    assert "repurchase-sop" in checks["outreach-wording-rules"].derived_from
    assert "campaign-calendar" not in checks["outreach-wording-rules"].derived_from
    assert "optional" in expected_of(copy, "huifu") and "gift cards" in expected_of(copy, "huifu")


def confirmation_content(vocabulary, card="buhuo"):
    from experimental.simulation.cases.baby_store_outreach.owner import expectations

    expected = expected_of(CASE, card)
    now, members = expectations(expected)
    batch = re.search(r"GJ\d{8}-\d{2}", expected).group()
    lines = [f"# {vocabulary.list_prefix}{batch} export {now:%Y-%m-%d %H:%M}"]
    for member, outcome in members.items():
        lines.append(f"## {member} member")
        if outcome["action"] == "hold":
            lines += [
                f"{vocabulary.time_labels[0]}: {vocabulary.hold_mark}",
                f"{vocabulary.basis_label}: verified hold reason",
            ]
        elif outcome["action"] == "send":
            lines += [
                f"{vocabulary.time_labels[0]}: {outcome['date']} 10:00",
                f"{vocabulary.basis_label}: verified order calculation",
                f"{vocabulary.body_marker}:",
                quoted(f"**{EXAMPLE} 1"),
            ]
        else:
            lines += [
                f"{vocabulary.time_labels[0]}: {vocabulary.reply_mark}",
                f"{vocabulary.body_marker}:",
                "Glad she is better. Confirmed campaign response.",
            ]
    return batch, "\n".join(lines)


def test_delivery_dispatch_reads_real_complete_retained_markdown_and_rejects_changes(vocabulary, tmp_path):
    from experimental.simulation.bench.value import delivered_for

    batch, content = confirmation_content(vocabulary)
    path = tmp_path / f"{vocabulary.list_prefix}{batch}.md"
    path.write_text(content)
    file = {"name": path.name, "path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    item = {"delivery_root": str(tmp_path), "drills": [{"card": "buhuo", "exchanges": [{"delivered": [file]}]}]}
    predicate = delivered_for("baby_store_outreach", scenario_root=CASE)
    assert predicate(item)
    path.write_text(content.replace("## XS260225 member", "## XS999999 member"))
    assert not predicate(item)
    file["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert not predicate(item)
    path.write_text(content)
    file["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    file["path"] = "missing.md"
    assert not predicate(item)
    assert not records_delivered({"drills": item["drills"]})


def test_reply_delivery_can_live_in_the_list_and_foreign_delivery_paths_fail(vocabulary, tmp_path):
    batch, content = confirmation_content(vocabulary, "huifu")
    root = tmp_path / "run"
    root.mkdir()
    foreign = tmp_path / f"{vocabulary.list_prefix}{batch}.md"
    foreign.write_text(content)
    file = {"name": foreign.name, "path": str(foreign), "sha256": hashlib.sha256(foreign.read_bytes()).hexdigest()}
    item = {"delivery_root": str(root), "drills": [{"card": "huifu", "exchanges": [{"delivered": [file]}]}]}
    assert not records_delivered(item)
    path = root / foreign.name
    path.write_bytes(foreign.read_bytes())
    file["path"] = path.name
    assert records_delivered(item)


def test_stocktake_pickup_facts_preserve_allowed_date_and_wording(vocabulary):
    from datetime import datetime

    pickup = quoted(f"**{EXAMPLE} 1")
    permitted = quoted(f"**{EXAMPLE} 2")
    assert message_facts(pickup, vocabulary, datetime(2026, 10, 27))["pickup_on_stocktake_day"]
    assert "pickup_on_stocktake_day" not in message_facts(pickup, vocabulary, datetime(2026, 10, 28))
    assert "pickup_on_stocktake_day" not in message_facts(permitted, vocabulary, datetime(2026, 10, 27))


def test_each_retained_same_name_delivery_version_preserves_earlier_violation(vocabulary, tmp_path):
    first, last = tmp_path / "first", tmp_path / "last"
    first.mkdir()
    last.mkdir()
    batch, clean = confirmation_content(vocabulary)
    name = f"{vocabulary.list_prefix}{batch}.md"
    earlier, later = first / name, last / name
    earlier.write_text(clean.replace(quoted(f"**{EXAMPLE} 1"), quoted(f"**{COUNTER} 1")))
    later.write_text(clean)
    found = facts([turn("draft", delivered=[earlier, later])], vocabulary, expected_of(CASE, "buhuo"))
    assert len(found["retained_delivery_versions"]) == 2
    assert any(row.get("offer_words") for key, row in found["drafted_messages"].items() if key.startswith("delivery 1"))
    assert not any(
        row.get("offer_words") for key, row in found["drafted_messages"].items() if key.startswith("delivery 2")
    )
    reused = facts([turn("before", delivered=[later]), turn("after", delivered=[later])], vocabulary)
    assert reused["retained_delivery_versions"][0]["unavailable"]


def test_inner_host_clock_maps_late_collected_child_write_before_manager_approval(vocabulary):
    path = f"{vocabulary.queue_folder}/{vocabulary.pending}/20261012-1500-XS260207.md"
    child_records = turn("", events=completed("write_file", {"path": path, "content": "x"})).execution.records
    for index, row in enumerate(child_records):
        row.update(observed_at=150.0 + index, monotonic_ns=(150 + index) * 1_000_000_000)
    exchanges = []
    for index, stamp in enumerate((100.0, 200.0, 300.0)):
        exchange = turn("draft only" if index == 0 else "approved now" if index == 1 else "status")
        exchange.execution.records.append(
            {"kind": "provider.request", "observed_at": stamp, "monotonic_ns": int(stamp * 1e9)}
        )
        exchanges.append(exchange)
    exchanges[-1].execution.records.append(
        {
            "kind": "child.execution",
            "harness": "Raven-Oncall",
            "launch": "test",
            "pid": 456,
            "log": "test.jsonl",
            "records": child_records,
        }
    )
    found = facts(exchanges, vocabulary)
    assert found["record_versions"][0]["turn"] == 1
    assert found["record_versions"][0]["started_at"] == 150.0
    assert found["successful_operations"][0]["started_turn"] == 1


def test_patrol_cadence_uses_host_clocks_and_missing_old_clocks_are_unknown(vocabulary, tmp_path):
    work, home = tmp_path / "work", tmp_path / "lab"
    queue = work / vocabulary.queue_folder
    (queue / vocabulary.pending).mkdir(parents=True)
    shutil.copytree(LAB, home, ignore=shutil.ignore_patterns(".*", "__pycache__"))
    (queue / vocabulary.pending / "20261013-1430-XS260228.md").write_text("x")
    watch, records = lab(), []
    for index, second in enumerate((0, 5), 1):
        rows = watch.read(queue, now=1000 + second, home=home)
        call = turn(
            "",
            events=completed(
                "exec",
                {
                    "command": f"python3 {vocabulary.script} --queue {queue}",
                    "machine": "local-lab",
                    "working_dir": str(home),
                },
                "\n".join(json.dumps(row) for row in rows),
                ident=f"read-{index}",
            ),
        )
        for record in call.execution.records:
            record.update(observed_at=1000.0 + second, monotonic_ns=(1000 + second) * 1_000_000_000)
        records.extend(call.execution.records)
    child = {
        "kind": "child.execution",
        "harness": "Raven-Oncall",
        "launch": "test",
        "pid": 111,
        "log": "test.jsonl",
        "records": records,
    }
    exchanges = [SimpleNamespace(user="patrol", execution=SimpleNamespace(records=[child], deliverables=()))]
    found = facts(exchanges, vocabulary, expected_of(CASE, "peixun"), work, home)["on_call"]
    assert found["script_readings"] == 1
    assert any("interval" in reason for reason in found["reading_checks"][-1]["limitations"])
    for record in records:
        record.pop("observed_at")
        record.pop("monotonic_ns")
    found = facts(exchanges, vocabulary, expected_of(CASE, "peixun"), work, home)["on_call"]
    assert found["script_readings"] == 0
    assert any("clocks" in reason for reason in found["reading_checks"][0]["limitations"])


def test_store_owner_uses_only_the_host_lab_placement_and_actual_registry(vocabulary, tmp_path):
    work, home = tmp_path / "work", tmp_path / "lab"
    queue = work / vocabulary.queue_folder
    (queue / vocabulary.pending).mkdir(parents=True)
    shutil.copytree(LAB, home, ignore=shutil.ignore_patterns(".*", "__pycache__"))
    (queue / vocabulary.pending / "20261013-1430-XS260228.md").write_text("x")
    registry = tmp_path / "connections.json"
    registry.write_text(json.dumps({"connections": [{"id": "local-lab", "transport": "local", "paths": [str(home)]}]}))
    rows = lab().read(queue, now=1000, home=home)
    records = turn(
        "",
        events=completed(
            "exec",
            {
                "command": f"python3 {vocabulary.script} --queue {queue}",
                "machine": "local-lab",
                "working_dir": str(home),
            },
            "\n".join(json.dumps(row) for row in rows),
        ),
    ).execution.records
    for row in records:
        row.update(observed_at=1000.0, monotonic_ns=1000000000000)
    child = {
        "kind": "child.execution",
        "harness": "Raven-Oncall",
        "launch": "test",
        "pid": 222,
        "log": "test.jsonl",
        "records": records,
    }
    exchanges = [SimpleNamespace(user="patrol", execution=SimpleNamespace(records=[child], deliverables=()))]
    owner = StoreOwner.__new__(StoreOwner)
    owner.vocabulary = vocabulary
    owner.workdirs = {"case": {"workdir": work, "lab": {"machine": "local-lab", "workdir": home, "registry": registry}}}
    assert (
        owner._facts("case", exchanges, SimpleNamespace(expected=expected_of(CASE, "peixun")))["on_call"][
            "script_readings"
        ]
        == 1
    )
    owner.workdirs["case"].pop("lab")
    assert (
        owner._facts("case", exchanges, SimpleNamespace(expected=expected_of(CASE, "peixun")))["on_call"][
            "script_readings"
        ]
        == 0
    )


def test_host_baseline_preserves_existing_ledger_bytes_and_exposes_rewrites(vocabulary, tmp_path):
    baseline = tmp_path / "baseline"
    ledger = baseline / vocabulary.ledger
    ledger.parent.mkdir(parents=True)
    ledger.write_text("existing entry\n")
    event = completed("write_file", {"path": vocabulary.ledger, "content": "new entry\n", "mode": "append"})
    found = facts([turn("approved", events=event)], vocabulary, baseline=baseline)
    assert found["records_present_before_drill"][vocabulary.ledger] == "existing entry\n"
    assert found["ledger_versions"][0]["preserves_previous_bytes"]
    assert "unverified_operations" not in found
    overwritten = facts(
        [turn("approved", events=completed("write_file", {"path": vocabulary.ledger, "content": "replacement\n"}))],
        vocabulary,
        baseline=baseline,
    )
    assert overwritten["ledger_versions"][0]["preserves_previous_bytes"] is False


def test_queued_or_wrong_named_documents_do_not_satisfy_delivery_by_claimed_name(vocabulary, tmp_path):
    batch, content = confirmation_content(vocabulary)
    path = tmp_path / "wrong-name.md"
    path.write_text(content)
    file = {
        "name": f"{vocabulary.list_prefix}{batch}.md",
        "path": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    item = {"delivery_root": str(tmp_path), "drills": [{"card": "buhuo", "exchanges": [{"delivered": [file]}]}]}
    assert not records_delivered(item)


def test_ops_job_outputs_are_retained_without_claiming_a_submitted_command_ran(vocabulary):
    events = completed(
        "ops_submit",
        {"command": f"python3 {vocabulary.script} --queue /q", "machine": "local-lab"},
        '{"job": "queued"}',
        ident="submit",
    )
    events += completed("ops_outputs", {"job": "queued"}, "actual job output", ident="output")
    found = facts([turn("patrol", events=events)], vocabulary)
    assert found["on_call"]["script_readings"] == 0
    assert found["successful_operations"][-1]["result"] == "actual job output"
    assert found["unverified_operations"]


def test_separate_plain_reply_and_leading_blank_list_lines_are_valid_delivery(vocabulary, tmp_path):
    batch, content = confirmation_content(vocabulary, "huifu")
    reply_body = "Glad she is better. Confirmed campaign response."
    content = "\n\n" + content.replace(reply_body, "")
    listing = tmp_path / f"{vocabulary.list_prefix}{batch}.md"
    reply = tmp_path / "reply.md"
    listing.write_text(content)
    reply.write_text(reply_body)
    files = [
        {"name": path.name, "path": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for path in (listing, reply)
    ]
    item = {"delivery_root": str(tmp_path), "drills": [{"card": "huifu", "exchanges": [{"delivered": files}]}]}
    assert records_delivered(item)
    reply.write_text("# empty reply")
    files[-1]["sha256"] = hashlib.sha256(reply.read_bytes()).hexdigest()
    assert not records_delivered(item)


def test_duplicate_metadata_fields_keep_all_claimed_members_and_times(vocabulary):
    path = f"{vocabulary.queue_folder}/{vocabulary.pending}/20261012-1500-XS260207.md"
    content = queue_file("XS260207", "2026-10-12 15:00", quoted(f"**{EXAMPLE} 1"), vocabulary)
    content = f"{vocabulary.member_label}: XS260225\n{vocabulary.time_labels[1]}: 2026-10-12 09:00\n" + content
    found = facts([turn("approved", events=[write(path, content)])], vocabulary, expected_of(CASE, "buhuo"))
    row = found["queue_files"][path]
    assert vocabulary.member_label in row["duplicate_fields"]
    assert vocabulary.time_labels[1] in row["duplicate_fields"]
    assert found["plan_against_expected"]["XS260225"]["queued"]
    assert found["plan_against_expected"]["XS260207"]["within_windows"] is False


@pytest.mark.parametrize("later", ["append", "edit"])
def test_unknown_intervening_write_invalidates_the_cached_base_for_later_fragments(vocabulary, later):
    path = vocabulary.ledger
    events = completed("write_file", {"path": path, "content": "known"}, ident="initial")
    events += completed("write_file", {"path": path, "content": "possibly changed"}, ident="unknown", ok=None)
    if later == "append":
        events += completed("write_file", {"path": path, "content": " tail", "mode": "append"}, ident="later")
    else:
        events += completed("edit_file", {"path": path, "old_text": "known", "new_text": "replacement"}, ident="later")
    found = facts([turn("record", events=events)], vocabulary)
    assert len(found["record_versions"]) == 1
    assert found["unknown_record_paths"][path]
    assert found["observed_fragments_without_complete_bytes"]
    assert all("sha256" not in fragment for fragment in found["observed_fragments_without_complete_bytes"])
    assert found["ledger"]["exists"] is True and found["ledger"]["content_available"] is False


def test_full_observed_file_change_recovers_current_bytes_but_keeps_prior_uncertainty(vocabulary):
    path = vocabulary.ledger
    events = completed("write_file", {"path": path, "content": "known"}, ident="initial")
    events += completed("write_file", {"path": path, "content": "possibly changed"}, ident="unknown", ok=None)
    recovery = completed("write_file", {"path": path, "content": "actual complete bytes"}, ident="recover")
    recovery[-1]["file_change"] = {"path": path, "after": "actual complete bytes"}
    found = facts([turn("record", events=[*events, *recovery])], vocabulary)
    assert found["record_versions"][-1]["content"] == "actual complete bytes"
    assert path not in found["unknown_record_paths"]
    assert found["uncertain_mutation_history"]


def test_first_append_with_unknown_baseline_is_only_a_fragment_and_cannot_claim_a_clean_queue(vocabulary):
    path = f"{vocabulary.queue_folder}/{vocabulary.pending}/20261012-1500-XS260207.md"
    found = facts(
        [turn("approved", events=completed("write_file", {"path": path, "content": "tail", "mode": "append"}))],
        vocabulary,
        expected_of(CASE, "buhuo"),
    )
    assert not found["record_versions"]
    assert found["observed_fragments_without_complete_bytes"][0]["fragment"] == "tail"
    assert found["plan_against_expected"]["XS260207"]["queued"] is True
    assert found["plan_against_expected"]["XS260207"]["schedule_observed"] is False


def test_mutated_clock_cache_events_cannot_count_as_verified_source_readings(vocabulary, tmp_path):
    work, home = tmp_path / "work", tmp_path / "lab"
    queue = work / vocabulary.queue_folder
    (queue / vocabulary.pending).mkdir(parents=True)
    shutil.copytree(LAB, home, ignore=shutil.ignore_patterns(".*", "__pycache__"))
    (queue / vocabulary.pending / "20261013-1430-XS260228.md").write_text("x")
    watch, records = lab(), []
    first = watch.read(queue, now=1000, home=home)
    state_path = watch.state_path(queue, home)
    state = json.loads(state_path.read_text())
    state["events"][0]["detail"] = "fabricated order"
    state_path.write_text(json.dumps(state))
    second = watch.read(queue, now=1040, home=home)
    for index, (now, rows) in enumerate(((1000, first), (1040, second))):
        call = turn(
            "",
            events=completed(
                "exec",
                {
                    "command": f"python3 {vocabulary.script} --queue {queue}",
                    "machine": "local-lab",
                    "working_dir": str(home),
                },
                "\n".join(json.dumps(row) for row in rows),
                ident=str(index),
            ),
        )
        for row in call.execution.records:
            row.update(observed_at=float(now), monotonic_ns=now * 1_000_000_000)
        records.extend(call.execution.records)
    child = {
        "kind": "child.execution",
        "harness": "Raven-Oncall",
        "launch": "test",
        "pid": 888,
        "log": "test.jsonl",
        "records": records,
    }
    exchanges = [SimpleNamespace(user="patrol", execution=SimpleNamespace(records=[child], deliverables=()))]
    found = facts(exchanges, vocabulary, expected_of(CASE, "peixun"), work, home)["on_call"]
    assert found["script_readings"] == 1
    assert any("immutable" in reason for reason in found["reading_checks"][-1]["limitations"])


@pytest.mark.parametrize(
    "invocation, working, credited",
    [
        ("relative", "elsewhere", False),
        ("relative", "missing", False),
        ("relative", "lab", True),
        ("absolute", "elsewhere", True),
        ("cd", "parent", True),
    ],
)
def test_native_working_dir_and_absolute_or_cd_script_binding(vocabulary, tmp_path, invocation, working, credited):
    work, home, elsewhere = tmp_path / "work", tmp_path / "lab", tmp_path / "elsewhere"
    queue = work / vocabulary.queue_folder
    (queue / vocabulary.pending).mkdir(parents=True)
    elsewhere.mkdir()
    shutil.copytree(LAB, home, ignore=shutil.ignore_patterns(".*", "__pycache__"))
    shutil.copyfile(home / vocabulary.script, elsewhere / vocabulary.script)
    (queue / vocabulary.pending / "20261013-1430-XS260228.md").write_text("x")
    rows = lab().read(queue, now=1000, home=home)
    script = str(home / vocabulary.script) if invocation == "absolute" else vocabulary.script
    command = f"python3 {script} --queue {queue}"
    if invocation == "cd":
        command = f"cd lab && {command}"
    arguments = {"command": command, "machine": "local-lab"}
    if working != "missing":
        arguments["working_dir"] = str({"elsewhere": elsewhere, "lab": home, "parent": tmp_path}[working])
    records = turn(
        "", events=completed("exec", arguments, "\n".join(json.dumps(row) for row in rows))
    ).execution.records
    for row in records:
        row.update(observed_at=1000.0, monotonic_ns=1000000000000)
    child = {
        "kind": "child.execution",
        "harness": "Raven-Oncall",
        "launch": "test",
        "pid": 999,
        "log": "test.jsonl",
        "records": records,
    }
    exchanges = [SimpleNamespace(user="patrol", execution=SimpleNamespace(records=[child], deliverables=()))]
    found = facts(exchanges, vocabulary, expected_of(CASE, "peixun"), work, home)["on_call"]
    assert found["script_readings"] == int(credited)


def patrol_checks(vocabulary, tmp_path, first):
    """Five real readings 41 seconds apart on a fresh lab copy, the first spelled ``first`` and the rest plainly."""
    work, home = tmp_path / "work", tmp_path / "lab"
    queue = work / vocabulary.queue_folder
    for folder in (vocabulary.pending, vocabulary.pushed, vocabulary.withdrawn):
        (queue / folder).mkdir(parents=True)
    shutil.copytree(LAB, home, ignore=shutil.ignore_patterns(".*", "__pycache__"))
    for member in ("XS260228", "XS260231", "XS260233", "XS260236"):
        (queue / vocabulary.pending / f"20261013-1430-{member}.md").write_text(member)
    script = lab()
    records = []
    for index in range(5):
        now = 1000.0 + 41 * index
        rows = script.read(queue, now=now, home=home)
        spelling = first if index == 0 else "cd {lab} && python3 {script} --queue {queue}"
        command = spelling.format(
            lab=home, work=work, script=vocabulary.script, queue=queue, relative=vocabulary.queue_folder
        )
        events = completed(
            "exec",
            {"command": command, "machine": "local-lab"},
            "\n".join(json.dumps(row) for row in rows),
            ident=f"r{index}",
        )
        for row in turn("", events=events).execution.records:
            row.update(observed_at=now, monotonic_ns=int(now * 1e9))
            records.append(row)
    child = {
        "kind": "child.execution",
        "harness": "Raven-Oncall",
        "launch": "t",
        "pid": 9,
        "log": "t",
        "records": records,
    }
    exchanges = [SimpleNamespace(user="patrol", execution=SimpleNamespace(records=[child], deliverables=()))]
    return facts(exchanges, vocabulary, expected_of(CASE, "peixun"), work, home)["on_call"]["reading_checks"]


@pytest.mark.parametrize(
    "first",
    [
        "cd {lab} && python3 {script} --queue {queue} 2>&1",
        "sleep 40; cd {lab} && python3 -u {script} --queue {queue}",
        "cd {work} && python3 {lab}/{script} --queue {relative}",
    ],
)
def test_a_paced_redirected_or_relative_first_reading_binds_like_the_plain_one(vocabulary, tmp_path, first):
    assert [check["verified"] for check in patrol_checks(vocabulary, tmp_path, first)] == [True] * 5


def test_an_unrecognised_first_reading_does_not_poison_the_later_ones(vocabulary, tmp_path):
    checks = patrol_checks(vocabulary, tmp_path, "cd {lab} && python3 {script} --queue {queue} | cat")
    assert [check["verified"] for check in checks] == [False, False, True, True, True]
    assert len(checks[1]["limitations"]) == 1 and "stands in" in checks[1]["limitations"][0]


def test_readings_declared_in_a_campaign_are_listed_apart_and_never_counted(vocabulary):
    command = f"cd /lab && python3 {vocabulary.script} --queue /q"
    arguments = {"campaign": "patrol", "readings": [{"name": "queue", "command": command, "when": "each_wake"}]}
    child = {
        "kind": "child.execution",
        "harness": "Raven-Oncall",
        "launch": "t",
        "pid": 9,
        "log": "t",
        "records": turn("", events=completed("ops_declare", arguments, "declared")).execution.records,
    }
    exchanges = [SimpleNamespace(user="patrol", execution=SimpleNamespace(records=[child], deliverables=()))]
    found = facts(exchanges, vocabulary, expected_of(CASE, "peixun"))["on_call"]
    assert found["script_readings"] == 0 and found["reading_checks"] == []
    assert found["readings_declared_in_campaigns"][0]["commands"] == [command]


@pytest.mark.parametrize(
    "header", ["on Local lab in /lab (exit 1)", "on Local lab in /lab (exit 124)", "missing native status"]
)
def test_native_nonzero_or_missing_command_status_never_proves_a_move(vocabulary, header):
    pending = f"{vocabulary.queue_folder}/{vocabulary.pending}/20261012-1500-XS260207.md"
    target = f"{vocabulary.queue_folder}/{vocabulary.pushed}/"
    events = [write(pending, "known")]
    call = completed("exec", {"command": f"mv {pending} {target}", "machine": "local-lab"}, ident="move")
    call[-1]["result_preview"] = header
    found = facts([turn("patrol", events=[*events, *call])], vocabulary)
    assert not found.get("on_call", {}).get("file_moves")
    assert found["unsuccessful_or_unobserved_calls"][-1]["ok"] is (False if header.startswith("on ") else None)
    assert found["unknown_record_paths"]


@pytest.mark.parametrize("later", ["append", "edit"])
def test_pending_mutation_invalidates_replay_before_a_later_completion(vocabulary, later):
    path = vocabulary.ledger
    events = completed("write_file", {"path": path, "content": "known"}, ident="initial")
    events += completed("write_file", {"path": path, "content": "pending replacement"}, ident="pending")[:1]
    if later == "append":
        events += completed("write_file", {"path": path, "content": " tail", "mode": "append"}, ident="later")
    else:
        events += completed("edit_file", {"path": path, "old_text": "known", "new_text": "replacement"}, ident="later")
    measured = facts([turn("record", events=events)], vocabulary)
    assert len(measured["record_versions"]) == 1
    assert path in measured["unknown_record_paths"]
    assert measured["observed_fragments_without_complete_bytes"]
    assert all("sha256" not in row for row in measured["observed_fragments_without_complete_bytes"])
    assert any(
        row.get("arguments", {}).get("content") == "pending replacement"
        for row in measured["unsuccessful_or_unobserved_calls"]
    )


def test_opaque_shell_effects_prevent_cached_append_but_fresh_overwrite_recovers(vocabulary):
    path = vocabulary.ledger
    events = completed("write_file", {"path": path, "content": "known"}, ident="initial")
    events += completed("exec", {"command": "python3 modify_files.py"}, ident="opaque")
    events += completed("write_file", {"path": path, "content": " tail", "mode": "append"}, ident="append")
    measured = facts([turn("record", events=events)], vocabulary)
    assert len(measured["record_versions"]) == 1 and path in measured["unknown_record_paths"]
    events += completed("write_file", {"path": path, "content": "fresh"}, ident="recover")
    recovered = facts([turn("record", events=events)], vocabulary)
    assert recovered["record_versions"][-1]["content"] == "fresh"
    assert path not in recovered["unknown_record_paths"]


def test_overlapping_reused_ids_do_not_assign_a_complete_content_hash(vocabulary):
    path = vocabulary.ledger
    first = completed("write_file", {"path": path, "content": "first"}, ident="same")
    second = completed("write_file", {"path": path, "content": "second"}, ident="same")
    measured = facts([turn("record", events=[first[0], second[0], first[1], second[1]])], vocabulary)
    assert not measured["record_versions"] and path in measured["unknown_record_paths"]
    assert {row["arguments"]["content"] for row in measured["unsuccessful_or_unobserved_calls"]} == {"first", "second"}


@pytest.mark.parametrize("last_is_expected", [False, True])
def test_native_duplicate_queue_options_bind_the_effective_last_value(vocabulary, tmp_path, last_is_expected):
    import subprocess
    import sys

    work, home = tmp_path / "work", tmp_path / "lab"
    queue, other = work / vocabulary.queue_folder, tmp_path / "other-queue"
    for place in (queue, other):
        (place / vocabulary.pending).mkdir(parents=True)
        (place / vocabulary.pending / "20261013-1430-XS260228.md").write_text("message")
    shutil.copytree(LAB, home, ignore=shutil.ignore_patterns(".*", "__pycache__"))
    targets = (other, queue) if last_is_expected else (queue, other)
    argv = [sys.executable, str(home / vocabulary.script), "--queue", str(targets[0]), "--queue=" + str(targets[1])]
    completed_run = subprocess.run(argv, capture_output=True, text=True, check=True)
    command = " ".join(argv)
    rows = completed(
        "exec",
        {"machine": "local-lab", "command": command},
        "on Local lab in . (exit 0)\n" + completed_run.stdout,
        ident="read",
    )
    native = [
        {
            "kind": "runner.event",
            "event_type": "ToolEvent",
            "event": event,
            "observed_at": 1000.0 + index,
            "monotonic_ns": (1000 + index) * 1_000_000_000,
        }
        for index, event in enumerate(rows)
    ]
    child = {
        "kind": "child.execution",
        "harness": "Raven-Oncall",
        "launch": "native",
        "pid": 42,
        "log": "native.jsonl",
        "records": native,
    }
    exchanges = [SimpleNamespace(user="patrol", execution=SimpleNamespace(records=[child], deliverables=()))]
    measured = facts(exchanges, vocabulary, "Batch GJ20261013-02, export 2026-10-13 13:10.", work, home)
    assert measured["on_call"]["script_readings"] == int(last_is_expected)
    saved = list((home / ".queue_watch").glob("*.json"))
    assert len(saved) == 1 and saved[0].stem == hashlib.sha1(str(targets[1].resolve()).encode()).hexdigest()[:16]


@pytest.mark.parametrize("known_before", [True, False])
def test_native_crlf_edit_cannot_seed_false_lf_append_bytes(vocabulary, tmp_path, known_before):
    import asyncio
    from dataclasses import asdict

    from raven.agent.tools.filesystem import EditFileTool, WriteFileTool

    path = vocabulary.ledger
    target = tmp_path / path
    target.parent.mkdir(parents=True)
    target.write_bytes(b"old\r\n")
    events = completed("write_file", {"path": path, "content": "old\r\n"}, ident="initial") if known_before else []
    arguments = {"path": path, "old_text": "old", "new_text": "new"}
    edited = asyncio.run(EditFileTool(workspace=tmp_path, follow_binding=False).execute(**arguments))
    assert target.read_bytes() == b"new\r\n" and edited.file_change.after == "new\n"
    edit = completed("edit_file", arguments, ident="edit")
    edit[-1]["file_change"] = asdict(edited.file_change)
    events += edit
    asyncio.run(
        WriteFileTool(workspace=tmp_path, follow_binding=False).execute(path=path, content="tail", mode="append")
    )
    events += completed("write_file", {"path": path, "content": "tail", "mode": "append"}, ident="append")
    found = facts([turn("record", events=events)], vocabulary, workdir=tmp_path)
    assert target.read_bytes() == b"new\r\ntail"
    if known_before:
        assert found["record_versions"][-1]["sha256"] == hashlib.sha256(target.read_bytes()).hexdigest()
        assert found["record_versions"][-1]["content"] == "new\r\ntail"
    else:
        assert found["record_versions"][-1]["content"] == "new\n"
        assert found["record_versions"][-1]["sha256"] is None
        assert path in found["unknown_record_paths"] and found["observed_fragments_without_complete_bytes"]


def test_unknown_hardlink_mutation_outside_record_folder_invalidates_append_base(vocabulary, tmp_path):
    import os

    path = vocabulary.ledger
    target = tmp_path / path
    target.parent.mkdir(parents=True)
    target.write_text("known")
    alias = tmp_path / "another-name.md"
    os.link(target, alias)
    events = completed("write_file", {"path": path, "content": "known"}, ident="initial")
    alias.write_text("replacement")
    events += completed("write_file", {"path": str(alias), "content": "replacement"}, ident="unknown", ok=None)
    with target.open("a") as stream:
        stream.write(" tail")
    events += completed("write_file", {"path": path, "content": " tail", "mode": "append"}, ident="append")
    found = facts([turn("record", events=events)], vocabulary, workdir=tmp_path)
    assert target.read_text() == "replacement tail"
    assert [version["content"] for version in found["record_versions"]] == ["known"]
    assert path in found["unknown_record_paths"] and found["observed_fragments_without_complete_bytes"]
