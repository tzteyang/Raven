"""The orchard live-room case: it loads with its schedule and plan, its product cards parse, the host's facts are
computed right on a compliant and a violating script and on a live watch, and the live console in `lab/` advances in
real time from its first read without ever printing sealed text."""

import importlib.util
import itertools
import json
import shutil
import sys

import pytest

from experimental.harness.participation.protocols import Exchange, Execution
from experimental.harness.raven_adapter.action.runtime import REFUSED
from experimental.harness.scenario.contract import ROLES, load
from experimental.harness.scenario.disclosure import partition
from experimental.harness.scenario.sealed import sealed_for
from experimental.simulation.__main__ import owner_of
from experimental.simulation.bench.scenario import BUNDLED, Scenario
from experimental.simulation.cases.orchard_livestream.owner import (
    OrchardOwner,
    Vocabulary,
    cards,
    facts,
    persona_of,
    reads_console,
    ruled_out,
    script_facts,
    watch_facts,
)

CASE = BUNDLED / "orchard_livestream"
LAB = CASE / "lab"
HAN = range(0x3400, 0xA000)
CALLS = itertools.count()


@pytest.fixture(scope="module")
def scenario():
    return Scenario.load(CASE)


@pytest.fixture(scope="module")
def vocabulary(scenario):
    return Vocabulary.load(scenario)


@pytest.fixture(scope="module")
def product(scenario, vocabulary):
    return cards(scenario, vocabulary)


@pytest.fixture
def console(tmp_path):
    """The lab folder as the launcher places it on Local lab, imported from there so nothing is written in the case."""
    lab = tmp_path / "lab"
    shutil.copytree(LAB, lab)
    spec = importlib.util.spec_from_file_location("live_console_copy", lab / "live_console.py")
    module = importlib.util.module_from_spec(spec)
    written = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = written
    return module, lab


def sample(name: str) -> str:
    """The fenced script in a material, the way it was handed over."""
    text = (CASE / "materials" / name / "SKILL.md").read_text()
    return text.split("```")[1].strip("\n")


def turn(reply, records=(), files=()):
    rows = [{"kind": "runner.event", "event_type": "Text", "event": {"content": reply}}, *records]
    return Exchange("request", Execution("t1", [], rows, {}, "a", tuple(str(path) for path in files)))


def started(name, arguments):
    return {
        "kind": "runner.event",
        "event_type": "ToolEvent",
        "event": {"phase": "start", "name": name, "arguments": arguments, "tool_call_id": str(next(CALLS))},
    }


def called(name, arguments, *, ok=True, output=""):
    begun = started(name, arguments)
    ended = {
        "kind": "runner.event",
        "event_type": "ToolEvent",
        "event": {
            "phase": "complete",
            "tool_call_id": begun["event"]["tool_call_id"],
            "result_preview": output,
            "ok": ok,
        },
    }
    return [begun, ended]


def printed(reading):
    preview = "on Local lab in . (exit 0)\n" + json.dumps(reading, ensure_ascii=False)
    return called("exec", {"command": f"python3 live_console.py read {reading['session']}"}, output=preview)


def test_the_case_loads_with_its_schedule_plan_and_twin_exam_card(scenario):
    read = load(CASE)
    names = {case.id for case in read.situation.cases}
    assert len(names) == 12 and all(name.isalpha() and name.islower() for name in names)
    schedule = read.situation.schedule
    assert [len(step) for step in schedule.rounds] == [3, 3, 2] and schedule.rounds[2] == ("mingwan", "kaibo")
    assert set(schedule.rounds[2]) <= set(schedule.rounds[0])
    assert schedule.holdout_rounds == (0, 1, 3) and len(schedule.holdout) == 6
    assert {name for step in schedule.rounds for name in step} | set(schedule.holdout) == names
    for case in read.situation.cases:
        assert case.expected and case.files, case.id
        assert all((CASE / item).is_file() for item in case.files)
    for plan in read.exchange.plans.values():
        assert partition(plan.steps, read.handed) and len(plan.labels) == len(plan.steps)
    assert read.exchange.initial == read.exchange.plans["by-stage"].steps[0]
    assert set(read.handed) == set(read.materials) and all(check.derived_from for check in read.statements.checks)
    twin, held = (CASE / "personas" / "wujinagain.md").read_text(), (CASE / "personas" / "wujin.md").read_text()
    assert twin.replace("wujinagain", "wujin") == held
    assert all(
        (CASE / "handouts" / "wujinagain" / path.name).read_bytes() == path.read_bytes()
        for path in (CASE / "handouts" / "wujin").iterdir()
    )
    assert owner_of(scenario) is OrchardOwner


def test_every_card_has_a_product_card_whose_links_the_console_matches(scenario, product, console):
    module, lab = console
    assert set(product) == {persona.name for persona in scenario.personas}
    for card in product.values():
        assert card.room and len(card.links) == 3 and all(link.price for link in card.links.values())
        assert set(card.aftersale) == {1, 2, 3}
    two = product["pingyuan"]
    assert two.aftersale[3] != two.aftersale[1] and "11" in two.shipping
    area = Vocabulary.load(scenario).one("protected_area")
    assert [no for no, link in two.links.items() if area not in link.origin] == [3]
    sessions = module.sessions((lab / "sessions.md").read_text())
    rooms = {card.room: name for name, card in product.items()}
    for number, session in sessions.items():
        handed = next(persona for persona in scenario.personas if persona.name == rooms[number]).files
        table = [line for line in handed[0].read_text().splitlines() if line.startswith("|") and line[2:3].isdigit()]
        quotas = [int(line.strip("|").split("|")[-2]) for line in table]
        assert (
            quotas == [item["quota"] for item in session["links"]] == [anchor for anchor in session["stock"][0][1][:3]]
        )


def test_a_compliant_sample_script_measures_clean(product, vocabulary):
    script = sample("pitch-sample")
    found = script_facts(script, product["mingwan"], vocabulary)
    assert found["spoken_length"] == 246 and found["minute_markers"]
    assert found["minutes"] == [{"spoken_length": 246, "interaction_token_clauses": 3}]
    assert [
        (row["price"], row["card_links_at_this_price"], row["detected_components_agree"]) for row in found["prices"]
    ] == [(19.9, [1], True)]
    assert [(row["links"], row["phrase_present_anywhere"]) for row in found["after_sales"]] == [([1], True)]
    assert found["shipping"] == {
        "presale_token_present": True,
        "date_tokens_present": {"11-25": True},
        "hour_tokens_present": {"48": True},
    }
    assert found["regional_name"]["same_sentence_outside_cooccurrences"] == [] and "sugar_figures" not in found
    assert ruled_out(script, vocabulary) == {}


def test_a_wrong_price_for_the_spec_said_is_caught(product, vocabulary):
    script = sample("pitch-sample").replace("19.9", "49.9")
    (row,) = script_facts(script, product["mingwan"], vocabulary)["prices"]
    assert (
        row["card_links_at_this_price"] == [3] and row["named_weight_jin"] == 5 and not row["detected_components_agree"]
    )


def test_a_link_named_earlier_in_the_minute_holds_its_price_to_that_link(product, vocabulary):
    link, jin, yuan = vocabulary.one("link_word"), vocabulary.one("jin"), vocabulary.one("yuan")
    stop = chr(0x3002)
    script = f"3 {link}{stop}10 {jin}, 75-80mm, 39.9 {yuan}{stop}2 {link}{stop}10 {jin}, 39.9 {yuan}{stop}"
    rows = script_facts(script, product["pingyuan"], vocabulary)["prices"]
    assert [(row["named_link"], row["detected_components_agree"]) for row in rows] == [(3, False), (2, True)]


def test_last_seasons_script_measures_every_violation(product, vocabulary):
    script = (CASE / "handouts" / "laoguiju").glob("*-2*.md")
    old = next(path for path in script if "2025" in path.read_text()).read_text()
    found = script_facts(old, product["laoguiju"], vocabulary)
    assert [(row["price"], row["detected_components_agree"]) for row in found["prices"]] == [
        (69.9, False),
        (45.9, False),
    ]
    assert [row["phrase_present_anywhere"] for row in found["after_sales"]] == [False]
    assert found["shipping"]["presale_token_present"] is False and found["shipping"]["date_tokens_present"] == {
        "11-25": False
    }
    hits = ruled_out(old, vocabulary)
    forbidden = vocabulary.forbidden
    assert {forbidden[0], forbidden[3], forbidden[12], forbidden[21]} <= set(hits)


def test_the_regional_name_on_an_outside_link_is_reported(product, vocabulary):
    word, area = vocabulary.one("link_word"), vocabulary.one("protected_name")
    line = f"3 {word}, {area}" + chr(0x8110) + chr(0x6A59) + ", 36.9" + vocabulary.one("yuan")
    found = script_facts(line, product["pingyuan"], vocabulary)
    assert (
        found["regional_name"]["same_sentence_outside_cooccurrences"]
        and found["prices"][0]["detected_components_agree"]
    )


def board_path(vocabulary, room):
    return f"{vocabulary.one('live_folder')}/{room}/{vocabulary.one('board')}.md"


def timed(rows, seconds):
    for offset, row in enumerate(rows):
        row["observed_at"] = 1000.0 + seconds + offset * 0.001
        row["monotonic_ns"] = int((1000 + seconds + offset * 0.001) * 1e9)
    return rows


def test_native_reading_history_keeps_overwritten_notice_and_board_content(product, vocabulary, console, tmp_path):
    module, lab = console
    room = product["kaibo"].room
    session = module.sessions((lab / "sessions.md").read_text())[room]
    board = board_path(vocabulary, room)
    original, replacement = vocabulary.forbidden[12], "source-supported correction"
    records = []
    for delta in (0, 120, 240, 360, 480):
        payload = module.reading(room, session, session["first_read"] + delta)
        records += timed(
            called(
                "exec",
                {"machine": "local-lab", "working_dir": str(lab), "command": f"python3 live_console.py read {room}"},
                output="on Local lab in . (exit 0)\n" + json.dumps(payload),
            ),
            delta,
        )
        if delta == 240:
            records += timed(called("write_file", {"path": board, "content": original}), delta + 1)
            records += timed(called("write_file", {"path": board, "content": replacement}), delta + 2)
    child = {
        "kind": "child.execution",
        "harness": "Raven-Oncall",
        "launch": "native",
        "pid": 42,
        "log": "child.jsonl",
        "records": records,
    }
    found = watch_facts(
        [turn("done", [child])],
        product["kaibo"],
        vocabulary,
        workdir=tmp_path,
        lab={"machine": "local-lab", "workdir": lab},
    )
    assert len(found["readings"]) == 5 and all(row["verified_source"] for row in found["readings"])
    first_completion = next(row for row in records if row.get("event", {}).get("phase") == "complete")
    native_result = first_completion["event"]["result_preview"]
    first_completion["event"]["result_preview"] = native_result.replace("(exit 0)", "(exit 1)")
    failed = watch_facts(
        [turn("done", [child])],
        product["kaibo"],
        vocabulary,
        workdir=tmp_path,
        lab={"machine": "local-lab", "workdir": lab},
    )
    assert not failed["readings"][0]["verified_source"]
    first_completion["event"]["result_preview"] = native_result
    assert [row["content"] for row in found["versions"]] == [original, replacement]
    assert found["platform_notices"][0]["notice"]["text"]
    assert found["platform_notices"][0]["response_requires_semantic_review"]
    assert not any("board_line_after" in row for row in found["platform_notices"])
    wrong = watch_facts(
        [turn("done", [child])],
        product["kaibo"],
        vocabulary,
        workdir=tmp_path,
        lab={"machine": "local-lab", "workdir": tmp_path / "missing"},
    )
    assert not any(row["verified_source"] for row in wrong["readings"])


def test_failed_and_uncompleted_calls_supply_no_live_outcomes(product, vocabulary):
    room = product["kaibo"].room
    records = [
        *called("exec", {"command": f"python3 live_console.py read {room}"}, ok=False),
        *called("write_file", {"path": board_path(vocabulary, room), "content": "replacement"}, ok=False),
        started("write_file", {"path": board_path(vocabulary, room), "content": "replacement"}),
    ]
    found = watch_facts([turn("working", records)], product["kaibo"], vocabulary)
    assert not found["readings"] and not found["platform_notices"]
    assert all(row["ok"] is not True for row in found["operations"])


def test_completed_refusal_does_not_write_a_prompt_board(product, vocabulary):
    records = called(
        "write_file",
        {"path": board_path(vocabulary, product["kaibo"].room), "content": "replacement"},
        output=REFUSED + "no write occurred",
    )
    found = watch_facts([turn("working", records)], product["kaibo"], vocabulary)
    assert "live_room_writes" not in found


def test_only_successful_console_output_for_the_played_session_is_a_reading(product, vocabulary):
    room = product["kaibo"].room
    payload = {"session": room, "on_air": "04:00", "links": [], "notices": []}
    quoted = json.dumps(payload)
    other = {**payload, "session": "wrong-session"}
    records = [
        *called("spawn", {"task_summary": quoted}, output=quoted),
        *called("exec", {"command": f"echo '{quoted}'"}, output=quoted),
        *called("exec", {"command": f"python3 live_console.py read {room}"}, output=json.dumps(other)),
        *printed(payload),
    ]
    found = watch_facts([turn("working", records)], product["kaibo"], vocabulary)
    assert len(found["readings"]) == 2
    assert not any(row["verified_source"] for row in found["readings"])
    assert found["readings"][-1]["payload"]["session"] == room


def test_console_name_echoed_in_a_command_is_not_an_invocation(vocabulary):
    invocation = f"python3 {vocabulary.one('console')} read 20261010-3"
    assert reads_console(invocation, vocabulary)
    assert reads_console("cd /lab && " + invocation, vocabulary)
    assert not reads_console("echo " + invocation, vocabulary)
    assert not reads_console("printf '%s' " + invocation, vocabulary)
    assert not reads_console("echo ';' " + invocation, vocabulary)


def test_facts_name_the_card_for_exam_and_round_sessions(scenario, product, vocabulary, tmp_path):
    assert persona_of("holdout-kanzhe") == "kanzhe" and persona_of("s2-tishi-3") == "tishi"
    script = tmp_path / "pitch.md"
    script.write_text(sample("pitch-sample"))
    found = facts([turn("ok", files=[script])], product["mingwan"], vocabulary)
    assert found["product_card"]["session"] == "20261011-1"
    assert found["delivery_versions"][0]["versions"][0]["content"] == sample("pitch-sample")
    assert not found["script_candidates"]
    assert facts([turn("ok")], None, vocabulary)["full_texts"] == {"reply 1": "ok"}


def test_the_console_runs_in_real_time_from_its_first_read(console):
    module, lab = console
    state = lab / module.STATE
    first = module.read("20261010-3", now=1000.0)
    assert first["on_air"] == "02:00" and first["clock"] == "19:02:00" and first["notices"] == []
    assert state.is_file() and not (LAB / module.STATE).exists()
    later = module.read("20261010-3", now=1000.0 + 165)
    assert later["on_air"] == "04:45" and [notice["at"] for notice in later["notices"]] == ["19:04:45"]
    assert module.read("20261010-3", now=1165.0 + module.IDLE + 1)["on_air"] == "02:00"
    assert "error" in module.read("20991231-9", now=1000.0)
    assert module.main([]) == 2


@pytest.mark.parametrize("number", ["20261010-2", "20261010-3"])
def test_a_watched_session_shows_something_worth_acting_on_within_five_minutes(console, number):
    module, lab = console
    session = module.sessions((lab / "sessions.md").read_text())[number]
    start = module.reading(number, session, session["first_read"])
    seen = set()
    for second in range(0, 301, 10):
        now = module.reading(number, session, session["first_read"] + second)
        for before, after in zip(start["links"], now["links"]):
            if after["stock"] < 20 <= before["stock"] or after["state"] != before["state"]:
                seen.add(("link", after["no"]))
        seen |= {("notice", notice["at"]) for notice in now["notices"]}
    assert seen


def test_nothing_the_console_prints_is_sealed_from_anyone(console):
    module, lab = console
    contract = load(CASE)
    data = (lab / "sessions.md").read_text()
    shown = [
        data,
        *(
            json.dumps(module.read(number, now=5000.0 + second, path=lab / "s.json"), ensure_ascii=False)
            for number in module.sessions(data)
            for second in range(0, 3600, 30)
        ),
    ]
    assert not any(CASE.name in text for text in shown)
    for role in ROLES:
        seal = sealed_for(contract, role)
        assert not [text[:60] for text in shown if seal.hits(text)], role


def test_code_and_data_keep_to_their_languages():
    for path in [*CASE.rglob("*.py"), *CASE.rglob("*.json"), LAB / "live_console.py"]:
        assert not any(ord(char) in HAN for char in path.read_text()), path
    assert any(ord(char) in HAN for char in (LAB / "sessions.md").read_text())


def test_append_after_unknown_write_never_manufactures_a_full_version(product, vocabulary, tmp_path):
    path = board_path(vocabulary, product["tishi"].room)
    rows = [
        *called("write_file", {"path": path, "content": "old"}),
        *called("write_file", {"path": path, "content": "uncertain"}, ok=None),
        *called("write_file", {"path": path, "content": "tail", "mode": "append"}),
    ]
    found = watch_facts([turn("done", rows)], product["tishi"], vocabulary, workdir=tmp_path)
    assert [row["content"] for row in found["versions"]] == ["old", None, None]
    assert found["versions"][-1]["fragment"] == "tail" and found["versions"][-1]["sha256"] is None
    assert found["coverage_gaps"]


def test_external_and_symlink_board_paths_cannot_prove_placement(product, vocabulary, tmp_path):
    root, outside = tmp_path / "worker", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    relative = board_path(vocabulary, product["tishi"].room)
    (root / vocabulary.one("live_folder")).symlink_to(outside, target_is_directory=True)
    rows = called("write_file", {"path": relative, "content": "replacement"})
    found = watch_facts([turn("done", rows)], product["tishi"], vocabulary, workdir=root)
    assert not found["versions"] and found["final_files"]["board"]["status"] == "unavailable"


def test_conditional_shell_and_command_session_mismatch_do_not_verify(product, vocabulary, console, tmp_path):
    module, lab = console
    room = product["kaibo"].room
    payload = module.read(room, now=1000)
    assert not reads_console(f"false && python3 live_console.py read {room}", vocabulary)
    assert not reads_console(f"true || python3 live_console.py read {room}", vocabulary)
    rows = timed(
        called(
            "exec",
            {"machine": "local-lab", "command": "python3 live_console.py read wrong-session"},
            output="on Local lab in . (exit 0)\n" + json.dumps(payload),
        ),
        0,
    )
    found = watch_facts(
        [turn("done", rows)],
        product["kaibo"],
        vocabulary,
        workdir=tmp_path,
        lab={"machine": "local-lab", "workdir": lab},
    )
    assert found["readings"] and not found["readings"][0]["verified_source"]


def test_partial_price_and_unmarked_length_are_not_complete_compliance(product, vocabulary):
    text = f"2{vocabulary.one('link_word')},39.9{vocabulary.one('yuan')}"
    row = script_facts(text, product["mingwan"], vocabulary)["prices"][0]
    assert row["detected_components_agree"] and not row["all_components_detected"]
    long = "A" * 500
    measured = script_facts(long, product["mingwan"], vocabulary)
    assert len(measured["minutes"]) == 1 and measured["minutes"][0]["spoken_length"] == 500


def test_console_relative_path_uses_native_working_dir(product, vocabulary, console, tmp_path):
    module, lab = console
    room = product["kaibo"].room
    payload = module.read(room, now=1000)
    outside = tmp_path / "other"
    outside.mkdir()
    rows = timed(
        called(
            "exec",
            {"machine": "local-lab", "working_dir": str(outside), "command": f"python3 live_console.py read {room}"},
            output="on Local lab in . (exit 0)\n" + json.dumps(payload),
        ),
        0,
    )
    found = watch_facts(
        [turn("done", rows)],
        product["kaibo"],
        vocabulary,
        workdir=tmp_path,
        lab={"machine": "local-lab", "workdir": lab},
    )
    assert not found["readings"][0]["verified_source"]

    rows[0]["event"]["arguments"]["command"] = f"python3 {lab / 'live_console.py'} read {room}"
    found = watch_facts(
        [turn("done", rows)],
        product["kaibo"],
        vocabulary,
        workdir=tmp_path,
        lab={"machine": "local-lab", "workdir": lab},
    )
    assert found["readings"][0]["verified_source"]
    rows[0]["event"]["arguments"].pop("working_dir")
    rows[0]["event"]["arguments"]["command"] = f"python3 live_console.py read {room}"
    found = watch_facts(
        [turn("done", rows)],
        product["kaibo"],
        vocabulary,
        workdir=tmp_path,
        lab={"machine": "local-lab", "workdir": lab},
    )
    assert not found["readings"][0]["verified_source"]


@pytest.mark.parametrize("reply_seconds,latest", [(60, 41), (121, 15), (None, None)])
def test_reply_stock_uses_last_native_read_before_speech(product, vocabulary, console, tmp_path, reply_seconds, latest):
    module, lab = console
    room = product["kaibo"].room
    session = module.sessions((lab / "sessions.md").read_text())[room]
    records = []
    for delta in (0, 120):
        payload = module.reading(room, session, session["first_read"] + delta)
        records += timed(
            called(
                "exec",
                {"machine": "local-lab", "working_dir": str(lab), "command": f"python3 live_console.py read {room}"},
                output="on Local lab in . (exit 0)\n" + json.dumps(payload),
            ),
            delta,
        )
    reply = f"3{vocabulary.link_word[0]} {vocabulary.one('remain')}15{vocabulary.one('order_unit')}"
    exchange = turn(reply, records)
    if reply_seconds is not None:
        timed(exchange.execution.records[:1], reply_seconds)
    found = watch_facts(
        [exchange], product["kaibo"], vocabulary, workdir=tmp_path, lab={"machine": "local-lab", "workdir": lab}
    )
    assert all(row["verified_source"] for row in found["readings"])
    claim = next(row for row in found["stock_figure_candidates"] if row.get("surface") == "root_reply")
    assert claim["latest_verified_stock"] == latest
    assert claim["numeric_match"] is (None if latest is None else latest == 15)
    assert found["speech_events"][0]["event"]["content"] == reply


@pytest.mark.parametrize(
    ("spelling", "in_lab"),
    [
        ("python3 live_console.py read {room} 2>&1", True),
        ("cd {lab}; python3 live_console.py read {room}", False),
        ("sleep 1 && python3 live_console.py read {room}", True),
        ("python3 -u live_console.py read {room}", True),
    ],
)
def test_a_paced_or_redirected_console_read_binds_like_the_plain_one(
    product, vocabulary, console, tmp_path, spelling, in_lab
):
    module, lab = console
    room = product["kaibo"].room
    session = module.sessions((lab / "sessions.md").read_text())[room]
    payload = module.reading(room, session, session["first_read"])
    arguments = {"machine": "local-lab", "command": spelling.format(lab=lab, room=room)}
    if in_lab:
        arguments["working_dir"] = str(lab)
    rows = timed(called("exec", arguments, output="on Local lab in . (exit 0)\n" + json.dumps(payload)), 0)
    found = watch_facts(
        [turn("done", rows)],
        product["kaibo"],
        vocabulary,
        workdir=tmp_path,
        lab={"machine": "local-lab", "workdir": lab},
    )
    assert len(found["readings"]) == 1 and found["readings"][0]["verified_source"]


def test_a_cumulative_board_compares_only_the_lines_each_version_adds(product, vocabulary, console, tmp_path):
    module, lab = console
    room = product["kaibo"].room
    session = module.sessions((lab / "sessions.md").read_text())[room]
    board = board_path(vocabulary, room)
    word, remain, unit = vocabulary.link_word[0], vocabulary.one("remain"), vocabulary.one("order_unit")
    lines, records = [], []
    for delta in (0, 120):
        payload = module.reading(room, session, session["first_read"] + delta)
        records += timed(
            called(
                "exec",
                {"machine": "local-lab", "working_dir": str(lab), "command": f"python3 live_console.py read {room}"},
                output="on Local lab in . (exit 0)\n" + json.dumps(payload),
            ),
            delta,
        )
        stock = next(link["stock"] for link in payload["links"] if link["no"] == 3)
        lines.append(f"{payload['on_air']} 3{word} {remain}{stock}{unit}")
        records += timed(called("write_file", {"path": board, "content": "\n".join(lines) + "\n"}), delta + 1)
    found = watch_facts(
        [turn("done", records)],
        product["kaibo"],
        vocabulary,
        workdir=tmp_path,
        lab={"machine": "local-lab", "workdir": lab},
    )
    claims = [(row["figure"], row["numeric_match"]) for row in found["stock_figure_candidates"]]
    assert len(claims) == 2 and all(match for _, match in claims)


def test_readings_declared_in_a_campaign_are_listed_apart_and_never_counted(product, vocabulary, tmp_path):
    command = f"cd /lab && python3 live_console.py read {product['kaibo'].room}"
    arguments = {"campaign": "live", "readings": [{"name": "console", "command": command, "when": "each_wake"}]}
    found = watch_facts(
        [turn("done", called("ops_declare", arguments, output="declared"))],
        product["kaibo"],
        vocabulary,
        workdir=tmp_path,
    )
    assert found["readings"] == [] and found["reading_attempts"] == []
    assert found["readings_declared_in_campaigns"][0]["commands"] == [command]


def test_native_crlf_edit_retains_full_text_without_fabricated_byte_hash(product, vocabulary, tmp_path):
    import asyncio
    from dataclasses import asdict

    from raven.agent.tools.filesystem import EditFileTool

    path = board_path(vocabulary, product["tishi"].room)
    target = tmp_path / path
    target.parent.mkdir(parents=True)
    target.write_bytes(b"old\r\n")
    arguments = {"path": path, "old_text": "old", "new_text": "new"}
    edited = asyncio.run(EditFileTool(workspace=tmp_path, follow_binding=False).execute(**arguments))
    rows = called("edit_file", arguments)
    rows[-1]["event"]["file_change"] = asdict(edited.file_change)
    found = watch_facts([turn("done", rows)], product["tishi"], vocabulary, workdir=tmp_path)
    assert target.read_bytes() == b"new\r\n"
    assert found["versions"][-1]["content"] == "new\n"
    assert found["versions"][-1]["sha256"] is None and not found["versions"][-1]["bytes_known"]
    assert found["final_files"]["board"]["content"] == "new\r\n"
    assert found["final_files"]["board"]["sha256"]
