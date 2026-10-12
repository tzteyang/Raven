"""The launch copy case: it loads with its by-version plan, exam schedule and own owner, every card hands over its
files and states rows its sheet makes usable on its date, and the owner's facts measure a compliant revision, a
violating one and the live register the way the case's word table and sheets define them."""

import hashlib
from datetime import date
from pathlib import Path

import pytest

from experimental.harness.participation.protocols import Exchange, Execution
from experimental.harness.scenario.contract import load
from experimental.harness.scenario.disclosure import partition
from experimental.simulation.__main__ import owner_of
from experimental.simulation.bench.scenario import BUNDLED, Scenario
from experimental.simulation.bench.value import delivered_for
from experimental.simulation.cases.launch_messaging import owner as measures

ROOT = BUNDLED / "launch_messaging"
COLON = chr(0xFF1A)
OLD = "AF5-1014-1"
NEW = "AF5-1022-1"


@pytest.fixture(scope="module")
def case():
    scenario = Scenario.load(ROOT)
    vocabulary = measures.Vocabulary.load(ROOT / "reference.md")
    return scenario, vocabulary, measures.briefs(scenario.contract, vocabulary)


def turn(reply="", files=(), records=(), user="request"):
    rows = [{"kind": "runner.event", "event_type": "Text", "event": {"content": reply}}, *records]
    return Exchange(user, Execution("t1", [], rows, {}, "a", tuple(str(path) for path in files)))


def handout(name: str) -> str:
    return (ROOT / "handouts" / "fuhe" / name).read_text()


def evidence_line(n: int, row) -> str:
    condition = row.condition + "".join(f" {note}" for note in row.notes)
    vocabulary = measures.Vocabulary.load(ROOT / "reference.md")
    kind = vocabulary.third_party if row.third else vocabulary.internal_test
    cells = [
        str(n),
        row.concern,
        row.id,
        f"{kind} {row.issuer}",
        row.report or "-",
        row.wording,
        condition,
        str(row.issued),
    ]
    return "| " + " | ".join([*cells, str(row.valid)]) + " |"


def card_row(line: str, cell: int, value: str) -> str:
    cells = [part.strip() for part in line.strip().strip("|").split("|")]
    cells[cell] = value
    return "| " + " | ".join(cells) + " |"


def revised(rows) -> tuple[str, str]:
    """The re-check card's answer built from its own handouts: points 1 and 2 move to F15 and F14, nothing else."""
    screen = handout(f"{_prefix(0)}-{OLD}.md").replace(OLD, NEW)
    card = handout(f"{_prefix(1)}-{OLD}.md").replace(OLD, NEW)
    vocabulary = measures.Vocabulary.load(ROOT / "reference.md")
    screen = screen.replace(
        f"| {vocabulary.version} | {chr(0x7B2C)} 1 {chr(0x7248)} |",
        f"| {vocabulary.version} | {chr(0x7B2C)} 2 {chr(0x7248)} |",
    )
    screen = screen.replace(
        f"| {vocabulary.replaces} | {vocabulary.no_replacement} |", f"| {vocabulary.replaces} | {OLD} |"
    )
    screen = screen.replace("2026-10-14", "2026-10-22")
    moved = {"1": rows["F15"], "2": rows["F14"]}
    lines = []
    for line in screen.splitlines():
        n = line[2:3] if line.startswith("| ") else ""
        if n in moved and f"| F{n} |" in line:
            line = evidence_line(int(n), moved[n])
        lines.append(line)
    trained = []
    for line in card.splitlines():
        n = line[2:3] if line.startswith("| ") else ""
        if n in moved and line.startswith(f"| {n} |"):
            row = moved[n]
            line = card_row(line, 2, row.wording + "; " + row.condition)
            line = card_row(line, 3, f"{row.id} {row.report}; {row.condition}")
        trained.append(line)
    return "\n".join(lines) + "\n", "\n".join(trained) + "\n"


def _prefix(index: int) -> str:
    """The file-name prefixes of the two delivered files, as the re-check card's handouts spell them."""
    names = sorted(
        path.name.removesuffix(f"-{OLD}.md")
        for path in (ROOT / "handouts" / "fuhe").iterdir()
        if path.name.endswith(f"-{OLD}.md")
    )
    vocabulary = measures.Vocabulary.load(ROOT / "reference.md")
    first = next(name for name in names if vocabulary.first_screen_file in name)
    return first if index == 0 else next(name for name in names if name != first)


def snapshot_name(vocabulary) -> str:
    folder = ROOT / "handouts" / "fuhe"
    return next(path.name for path in folder.iterdir() if path.name.startswith(vocabulary.snapshot_prefix))


def write_event(path: str, after: str, call: str = "c1") -> list[dict]:
    start = {"phase": "start", "tool_call_id": call, "name": "write_file", "arguments": {"path": path}}
    done = {"phase": "complete", "tool_call_id": call, "ok": True, "file_change": {"path": path, "after": after}}
    return [
        {"kind": "runner.event", "event_type": "ToolEvent", "event": start},
        {"kind": "runner.event", "event_type": "ToolEvent", "event": done},
    ]


def append_event(path: str, content: str, call: str = "c2") -> list[dict]:
    arguments = {"path": path, "content": content, "mode": "append"}
    start = {"phase": "start", "tool_call_id": call, "name": "write_file", "arguments": arguments}
    done = {"phase": "complete", "tool_call_id": call, "ok": True}
    return [
        {"kind": "runner.event", "event_type": "ToolEvent", "event": start},
        {"kind": "runner.event", "event_type": "ToolEvent", "event": done},
    ]


def test_the_case_loads_with_its_plan_exam_schedule_and_owner(case):
    scenario, _, _ = case
    read = load(ROOT)
    assert len(read.situation.cases) == 12 and len(read.materials) == 9
    plan = read.exchange.plans["by-version"]
    assert len(plan.steps) == 3 and len(plan.labels) == 3
    assert partition(plan.steps, read.handed) == plan.steps
    assert set(read.exchange.initial) == set(plan.steps[0])
    schedule = read.situation.schedule
    assert schedule.holdout_rounds == (0, 1, 3) and len(schedule.holdout) == 6
    assert schedule.rounds[2] == (schedule.rounds[0][0], schedule.rounds[0][2])
    names = {item.id for item in read.situation.cases}
    assert {name for step in schedule.rounds for name in step} | set(schedule.holdout) == names
    assert all(check.derived_from for check in read.statements.checks)
    assert {check.id for check in read.statements.checks if check.applies_when} == {"citation-notes", "revision-scoped"}
    assert owner_of(scenario) is measures.LaunchOwner


def test_every_card_hands_over_its_files_and_names_rows_usable_on_its_date(case):
    _, vocabulary, briefs = case
    read = load(ROOT)
    for item in read.situation.cases:
        assert item.files and all((ROOT / path).is_file() for path in item.files)
        assert item.expected and measures.expected_points(item.expected), item.id
        brief = briefs[item.id]
        assert brief.day is not None and brief.model, item.id
        for row in brief.expected:
            assert measures.standing(brief.rows[row], brief.day, vocabulary) == "usable", (item.id, row)
    twin, source = "dunguoagain", "dunguo"
    cases = {item.id: item for item in read.situation.cases}
    assert cases[twin].text == cases[source].text and cases[twin].expected == cases[source].expected
    assert [Path(path).read_text() for path in (ROOT / p for p in cases[twin].files)] == [
        Path(path).read_text() for path in (ROOT / p for p in cases[source].files)
    ]


def test_the_rows_a_card_passes_over_stand_as_its_answer_says(case):
    _, vocabulary, briefs = case

    def standing(card, row):
        return measures.standing(briefs[card].rows[row], briefs[card].day, vocabulary)

    assert standing("fuhe", "F2").startswith("void from 2026-10-20")
    assert standing("fuhe", "F11").startswith("expired")
    assert standing("fuhe", "F10") == "comparison wording" and standing("fuhe", "F6") == "barred from external use"
    assert [standing("yangshenghu", row) for row in ("F1", "F2", "F3")] == [
        "expired 2026-05-19",
        "comparison wording",
        "barred from external use",
    ]
    assert standing("zaocanji", "F2") == "issuer without CMA or CNAS" and standing("zaocanji", "F3").startswith("void")
    assert standing("mianbao", "F3").startswith("expired") and standing("mianbao", "F2") == "usable"
    for card, internal, third in (("pobiji", "F1", "F2"), ("doujiang", "F1", "F2"), ("fuhe", "F1", "F15")):
        assert standing(card, internal) == standing(card, third) == "usable"
        assert third in briefs[card].expected and internal not in briefs[card].expected
    assert measures.standing(briefs["fuhe"].rows["F2"], date(2026, 10, 14), vocabulary) == "usable"
    row = briefs["shuihu"].rows["F1"]
    assert measures.standing(row, None, vocabulary) == "request date unobserved"
    missing = measures.Row(**{**row.__dict__, "valid": None})
    assert measures.standing(missing, briefs["shuihu"].day, vocabulary) == "evidence date or validity unobserved"


def test_absolute_words_spare_time_order_uses_and_comparisons_are_caught(case):
    _, vocabulary, briefs = case
    ordinal, sequence = vocabulary.forbidden[1], vocabulary.time_order[1]
    assert sequence.startswith(ordinal)
    assert measures.absolutes(sequence, vocabulary) == []
    assert measures.absolutes(sequence + ordinal, vocabulary) == [ordinal]
    assert measures.absolutes(briefs["mianbao"].rows["F2"].wording, vocabulary) == []
    assert measures.absolutes(briefs["dunguo"].rows["F4"].wording, vocabulary) == []
    rows = briefs["fuhe"].rows
    assert measures.comparisons(rows["F6"].wording, vocabulary) and measures.comparisons(
        rows["F10"].wording, vocabulary
    )
    assert measures.comparisons(rows["F1"].wording, vocabulary) == []


def test_the_old_version_is_stale_for_the_recheck(case, tmp_path):
    _, vocabulary, briefs = case
    files = []
    for prefix in (_prefix(0), _prefix(1)):
        path = tmp_path / f"{prefix}-{OLD}.md"
        path.write_text(handout(path.name))
        files.append(path)
    found = measures.facts([turn("ok", files)], vocabulary, briefs["fuhe"])
    points = {entry["point"]: entry for entry in found["evidence"]}
    assert points[1]["cited"] == ["F1"] and points[1]["expected"] == "F15"
    assert points[2]["standing"] == "void from 2026-10-20" and points[3]["standing"] == "usable"
    assert points[3]["footnotes_copied"] is True
    assert found["revision"]["new_number"] is False
    assert found["register"] == {"path": vocabulary.register_path, "seen_in": None, "observed": False}
    assert "wording" not in found and "untraced_figures" not in found


def test_wording_only_revision_retains_valid_evidence_and_other_copy(case):
    _, vocabulary, briefs = case
    original = handout(f"{_prefix(0)}-{OLD}.md")
    previous = measures.parse("old.md", original, vocabulary)
    revised_text = original.replace(OLD, NEW).replace(previous.points[3], "4 items not detected")
    latest = measures.parse("new.md", revised_text, vocabulary)
    measured = measures.revision(previous, latest)
    assert measured["new_number"] and measured["title_unchanged"] and measured["proposition_unchanged"]
    assert measured["points"][:2] == [
        {"point": 1, "text_unchanged": True, "evidence": "unchanged", "evidence_text_unchanged": True},
        {"point": 2, "text_unchanged": True, "evidence": "unchanged", "evidence_text_unchanged": True},
    ]
    assert measured["points"][2] == {
        "point": 3,
        "text_unchanged": False,
        "evidence": "unchanged",
        "evidence_text_unchanged": True,
    }
    assert measures.standing(briefs["fuhe"].rows["F3"], briefs["fuhe"].day, vocabulary) == "usable"


def test_a_scoped_revision_and_its_register_row_are_measured(case, tmp_path):
    _, vocabulary, briefs = case
    brief = briefs["fuhe"]
    screen, card = revised(brief.rows)
    files = [tmp_path / f"{_prefix(0)}-{NEW}.md", tmp_path / f"{_prefix(1)}-{NEW}.md"]
    files[0].write_text(screen)
    files[1].write_text(card)
    before = handout(snapshot_name(vocabulary))
    old_row = next(line for line in before.splitlines() if line.startswith(f"| {OLD} |"))
    cells = [cell.strip() for cell in old_row.strip().strip("|").split("|")]
    cells[0], cells[1], cells[4], cells[5], cells[10] = NEW, "2026-10-22", "2", OLD, "F15, F14, F3"
    cells[11] = cells[11].replace(OLD, NEW)
    path = f"/work/{vocabulary.register_path}"
    register = before.rstrip("\n") + "\n"
    appended = "| " + " | ".join(cells) + " |\n"
    records = write_event(path, register) + append_event(path, appended)
    exchanges = [turn("ok", files, records)]
    found = measures.facts(exchanges, vocabulary, brief, measures.live_register(exchanges, vocabulary))
    assert [entry["cited"][0] for entry in found["evidence"]] == list(brief.expected)
    assert all(entry["standing"] == "usable" and entry["condition_copied"] for entry in found["evidence"])
    revision = found["revision"]
    assert revision["previous"] == OLD and revision["latest"] == NEW and revision["new_number"] is True
    assert revision["title_unchanged"] and revision["proposition_unchanged"]
    assert [point["text_unchanged"] for point in revision["points"]] == [True, True, True]
    assert [point["evidence"] for point in revision["points"]] == ["F1 -> F15", "F2 -> F14", "unchanged"]
    agreement = found["training_card"]
    assert agreement["number_same"] and agreement["intro_same_as_proposition"]
    assert all(point["text_same"] and point["evidence_same"] for point in agreement["points"])
    kept = found["register"]
    assert kept["seen_in"] == "records" and kept["observed"] and kept["exists"]
    assert kept["starting_rows_changed"] == [] and kept["starting_rows_lost"] == []
    assert kept["export_rows_absent"] == [] and kept["export_rows_changed"] == []
    (row,) = kept["appended"]
    assert row["number"] == NEW and row["replaces"] == OLD and row["evidence"] == ["F15", "F14", "F3"]
    assert row["matches_delivered"]["proposition"] and all(row["matches_delivered"]["points"])
    assert row["matches_delivered"]["evidence"]
    assert all(value is True for key, value in row["matches_delivered"].items() if key != "points")


def test_a_violating_version_is_flagged(case, tmp_path):
    _, vocabulary, briefs = case
    brief = briefs["fuhe"]
    screen, card = revised(brief.rows)
    ordinal, rival = vocabulary.forbidden[1], vocabulary.competitor[0]
    proposition = next(line for line in screen.splitlines() if line.startswith(vocabulary.proposition))
    screen = screen.replace(proposition, proposition + ordinal)
    screen = screen.replace(brief.rows["F3"].notes[0], "")
    point = next(line for line in screen.splitlines() if line.startswith(f"{vocabulary.point} 1"))
    screen = screen.replace(point, point.replace("12", "10"))
    screen = screen.replace("612", "999")
    first = next(line for line in card.splitlines() if line.startswith("| 1 |"))
    card = card.replace(first, card_row(first, 1, first.split("|")[2].strip() + rival))
    files = [tmp_path / f"{_prefix(0)}-{NEW}.md", tmp_path / f"{_prefix(1)}-{NEW}.md"]
    files[0].write_text(screen)
    files[1].write_text(card)
    snapshot = handout(snapshot_name(vocabulary))
    edited = snapshot.replace(f"| {OLD} | 2026-10-14 |", f"| {OLD} | 2026-10-22 |")
    path = f"/work/{vocabulary.register_path}"
    exchanges = [turn("ok", files, write_event(path, edited))]
    found = measures.facts(exchanges, vocabulary, brief, measures.live_register(exchanges, vocabulary))
    words = found["wording"]
    assert ordinal in words["absolute"][f"file {files[0].name}"]
    assert rival in words["competitor"][f"file {files[1].name}"]
    points = {entry["point"]: entry for entry in found["evidence"]}
    assert points[3]["footnotes_copied"] is False
    assert points[1]["point_figures_not_in_row"] == ["10"]
    assert any(line.startswith("999") for line in found["basis_figures_untraced"])
    assert "untraced_figures" not in found
    assert found["register"]["export_rows_changed"] == [OLD] and found["register"]["appended"] == []
    assert found["training_card"]["points"][0]["text_same"] is False


def test_notes_are_measured_after_the_citation_notice(case, tmp_path):
    _, vocabulary, briefs = case
    brief = briefs["shuihu"]
    rows = [brief.rows[row] for row in brief.expected]
    header = f"| {vocabulary.point} | {vocabulary.sheet_columns[0]} | x |"
    lines = [
        f"{vocabulary.number}{COLON}KT3-1029-1",
        f"{vocabulary.title}{COLON}KT3",
        f"{vocabulary.proposition}{COLON}{rows[0].concern}",
        *(f"{vocabulary.point} {n}{COLON}{row.concern}" for n, row in enumerate(rows, 1)),
        "",
        header,
        "|---|---|---|",
        *(f"| {n} | {row.id} | {row.wording} {row.condition} |" for n, row in enumerate(rows, 1)),
        "",
        f"## {vocabulary.notes}",
    ]
    for n, row in enumerate(rows, 1):
        source = (
            f"{measures.issuer_name(row)} {vocabulary.report_label} {row.report}"
            if row.third
            else vocabulary.internal_label
        )
        valid = str(row.valid) if n != 2 else ""
        lines.append(f"{vocabulary.footnote} {n}{COLON}{source} {row.condition} {valid}")
    path = tmp_path / f"{vocabulary.first_screen_file}-KT3-1029-1.md"
    path.write_text("\n".join(lines) + "\n")
    found = measures.facts([turn("ok", [path])], vocabulary, brief)
    notes = found["notes"]["points"]
    assert [note["note"] for note in notes] == [True, True, True]
    assert [note["valid_until"] for note in notes] == [True, False, True]
    assert all(note["source"] and note["condition"] for note in notes)
    assert "notes" not in measures.facts([turn("ok", [path])], vocabulary, briefs["dunguo"])


def test_session_names_resolve_to_cards_and_facts_need_no_card(case):
    _, vocabulary, briefs = case
    assert measures.card_of("holdout-dunguoagain", None, briefs) == "dunguoagain"
    assert measures.card_of("s2-pobiji-2", None, briefs) == "pobiji"
    assert measures.card_of("visitor", None, briefs) is None
    assert measures.facts([turn("hello")], vocabulary) == {}


def test_customer_lines_are_measured_without_the_known_false_hits(case, tmp_path):
    _, vocabulary, briefs = case
    brief = briefs["fuhe"]
    screen, card = revised(brief.rows)
    later, rather, share = vocabulary.time_order[2], vocabulary.comparative_skip[0], vocabulary.comparative_skip[1]
    first = next(line for line in card.splitlines() if line.startswith("| 1 |"))
    says = first.split("|")[3].strip()
    card = card.replace(first, card_row(first, 2, f"{says}{later}{rather}{vocabulary.comparative_words[13]}{share}"))
    unused = next(line for line in screen.splitlines() if line.startswith("- F6"))
    screen = screen.replace(unused, unused + vocabulary.forbidden[2])
    files = [tmp_path / f"{_prefix(0)}-{NEW}.md", tmp_path / f"{_prefix(1)}-{NEW}.md"]
    files[0].write_text(screen)
    files[1].write_text(card)
    found = measures.facts([turn("ok", files)], vocabulary, brief)
    assert "wording" not in found and "untraced_figures" not in found
    clause = f"{chr(0x7B2C)} 3.1 {chr(0x6761)}"
    dated = f"10 {chr(0x6708)} 16 {chr(0x65E5)}"
    assert measures.untraced([f"{clause} {dated} 2025 {chr(0x5E74)} 99"], ["nothing"], vocabulary) == [
        "99: " + f"{clause} {dated} 2025 {chr(0x5E74)} 99"
    ]
    assert measures.untraced(["99"], ["material says 99"], vocabulary) == []
    assert measures.comparisons(rather + vocabulary.comparative_words[13], vocabulary) == []
    assert measures.comparisons(vocabulary.comparative + vocabulary.comparative_words[1], vocabulary)


def test_bold_headings_and_chinese_numerals_parse_without_crediting_draft_history(case, tmp_path):
    _, vocabulary, briefs = case
    brief = briefs["fuhe"]
    screen, _ = revised(brief.rows)
    one = chr(0x4E00)
    variant = screen.replace(f"{vocabulary.point} 1{COLON}", f"{vocabulary.point}{one}{COLON}")
    variant = variant.replace(f"## {vocabulary.notes}", f"**{vocabulary.notes}**")
    parsed = measures.parse("x.md", variant, vocabulary)
    assert sorted(parsed.points) == [1, 2, 3]
    assert measures.heading_of(f"**{vocabulary.notes}**{COLON}", (vocabulary.notes,)) is not None
    path = tmp_path / f"{_prefix(0)}-{NEW}.md"
    path.write_text(screen)
    overwritten = screen.replace(brief.previous.title, brief.previous.title + "x")
    records = write_event(str(path), screen)
    records[1]["event"]["file_change"]["before"] = overwritten
    found = measures.facts([turn("ok", [path], records)], vocabulary, brief)
    assert found["revision"]["previous"] == OLD and found["revision"]["title_unchanged"]
    assert len(measures.versions([turn("ok", [path], records)], vocabulary, training=False)) == 1


def test_a_proposition_promising_a_skipped_concern_is_listed(case, tmp_path):
    _, vocabulary, briefs = case
    brief = briefs["yangshenghu"]
    skipped = brief.skipped[0]
    path = tmp_path / f"{vocabulary.first_screen_file}-YS3-1022-1.md"
    path.write_text(f"{vocabulary.proposition}{COLON}{skipped}\n{vocabulary.point} 1{COLON}x\n")
    found = measures.facts([turn("ok", [path])], vocabulary, brief)
    assert found["skipped_concerns"] == {"skipped": [skipped], "promised_in_proposition": [skipped]}


def test_only_retained_handovers_establish_delivered_versions(case, tmp_path):
    _, vocabulary, briefs = case
    brief = briefs["fuhe"]
    screen, card = revised(brief.rows)
    paths = [tmp_path / f"{prefix}-{NEW}.md" for prefix in vocabulary.file_names]
    for path, text in zip(paths, (screen, card)):
        path.write_text(text)
    writes = write_event(str(paths[0]), screen) + write_event(str(paths[1]), card, "c2")
    local = measures.facts([turn(records=writes)], vocabulary, brief)
    assert "first_screen" not in local and "training_card" not in local
    assert not local["delivery"]["first_screen_retained"]
    old = tmp_path / f"{vocabulary.file_names[0]}-{OLD}.md"
    old.write_text(handout(old.name))
    masked = measures.facts([turn(files=[old]), turn(records=writes)], vocabulary, brief)
    assert masked["first_screen"]["number"] == OLD
    assert masked["evidence"][1]["standing"].startswith("void")
    first = measures.facts([turn(files=paths)], vocabulary, brief)
    assert first["first_screen"]["number"] == NEW
    assert all(copy["turn"] == 1 and copy["sha256"] for copy in first["delivery"]["versions"])
    assert all(copy["turn_id"] == "t1" and copy["artifact_id"] == "a" for copy in first["delivery"]["versions"])
    second_paths = [tmp_path / "second" / path.name for path in paths]
    second_paths[0].parent.mkdir()
    for path, text in zip(second_paths, (screen, card)):
        path.write_text(text)
    repeated = measures.facts([turn(files=paths), turn(files=second_paths)], vocabulary, brief)
    assert repeated["identity"]["version_matches"] and repeated["identity"]["sequence_matches"]


def test_reused_delivery_paths_leave_earlier_content_unavailable(case, tmp_path):
    _, vocabulary, briefs = case
    screen, _ = revised(briefs["fuhe"].rows)
    path = tmp_path / f"{vocabulary.file_names[0]}-{NEW}.md"
    path.write_text(screen)
    found = measures.facts([turn(files=[path]), turn(files=[path])], vocabulary, briefs["fuhe"])
    assert len(found["delivery"]["versions"]) == 1
    assert found["delivery"]["versions"][0]["turn"] == 2
    assert found["delivery"]["unavailable"][0]["turn"] == 1


def test_retained_measurements_hash_full_content_when_the_packet_is_cut(case, tmp_path, monkeypatch):
    _, vocabulary, briefs = case
    screen, _ = revised(briefs["fuhe"].rows)
    path = tmp_path / f"{vocabulary.file_names[0]}-{NEW}.md"
    path.write_text(screen)
    monkeypatch.setattr(
        measures,
        "delivery_versions",
        lambda exchanges: [{"turn": 1, "files": {path.name: screen[:30]}, "unavailable": {}}],
    )
    found = measures.facts([turn(files=[path])], vocabulary, briefs["fuhe"])
    assert found["first_screen"]["number"] == NEW
    assert found["delivery"]["versions"][0]["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_unreadable_delivered_markdown_is_explicitly_unavailable(case, tmp_path):
    _, vocabulary, briefs = case
    path = tmp_path / f"{vocabulary.file_names[0]}-{NEW}.md"
    path.write_bytes(b"\xff")
    found = measures.facts([turn(files=[path])], vocabulary, briefs["fuhe"])
    assert found["delivery"]["unreadable"][0]["file"] == path.name
    assert "first_screen" not in found


def test_delivery_predicate_requires_the_retained_latest_markdown_pair(case):
    _, vocabulary, _ = case

    def file(prefix, number=NEW):
        return {"name": f"{prefix}-{number}.md", "path": "retained.md", "sha256": "verified-by-host"}

    pair = [file(prefix) for prefix in vocabulary.file_names]
    item = {"scenario_root": str(ROOT), "drills": [{"exchanges": [{"delivered": pair}]}]}
    assert measures.DELIVERED(item)
    assert delivered_for("launch_messaging")(item)
    assert not measures.DELIVERED({"scenario_root": str(ROOT), "drills": []})
    for bad in (
        [pair[0]],
        [{"name": "arbitrary.md", "path": "retained.md", "sha256": "verified"}],
        [pair[0], file(vocabulary.file_names[1], OLD)],
        [{**pair[0], "path": None}, pair[1]],
    ):
        assert not measures.DELIVERED({"scenario_root": str(ROOT), "drills": [{"exchanges": [{"delivered": bad}]}]})
    assert not measures.DELIVERED(
        {"scenario_root": str(ROOT), "drills": [{"exchanges": [{"delivered": pair}, {"delivered": [pair[0]]}]}]}
    )


@pytest.mark.parametrize("changed", [False, True])
def test_native_same_turn_resend_uses_last_retained_occurrences(case, tmp_path, changed):
    from types import SimpleNamespace

    from experimental.harness.raven_adapter.observe import Recorder
    from experimental.harness.raven_adapter.worker import Worker
    from experimental.simulation.bench.record import _drills

    _, vocabulary, briefs = case
    work = tmp_path / "work"
    work.mkdir()
    files = [work / f"{prefix}-{NEW}.md" for prefix in vocabulary.file_names]
    texts = revised(briefs["fuhe"].rows)
    for path, text in zip(files, texts):
        path.write_text(text)
    recorder = Recorder(tmp_path / "employee/observations.jsonl")
    recorder.turn_id = "native-resend"
    recorder.delivery_roots = (work, tmp_path / "employee")
    worker = object.__new__(Worker)
    worker.baseline = SimpleNamespace(workdir=work)
    worker.area, worker.root = tmp_path / "employee", tmp_path / "state"
    for call in ("first", "resend"):
        if call == "resend" and changed:
            for path, text in zip(files, texts):
                path.write_text(text + "\nUpdated retained copy.\n")
        recorder.add(
            "runner.event",
            event_type="ToolEvent",
            event={
                "phase": "complete",
                "tool_call_id": call,
                "ok": True,
                "metadata": {"raven_delivery": {"files": [{"path": str(path)} for path in files]}},
            },
        )
    kept = worker._keep_deliverables(recorder.turn_id, recorder.rows)
    assert len(kept) == len(set(kept)) == 4
    execution = Execution(recorder.turn_id, [], recorder.rows, {}, "installed", kept)
    recorded = {"sessions": {"fuhe": [{"user": "Send the prescribed pair.", "execution": execution.__dict__}]}}

    def measured():
        drills, _, _ = _drills(recorded, worker.root, {"fuhe"})
        return {"scenario_root": str(ROOT), "delivery_root": str(worker.root), "drills": drills}

    item = measured()
    assert len(item["drills"][0]["exchanges"][0]["delivered"]) == 4
    assert measures.DELIVERED(item) and delivered_for("launch_messaging", scenario_root=ROOT)(item)
    if changed:
        assert Path(kept[0]).read_bytes() != Path(kept[2]).read_bytes()
    Path(kept[-1]).unlink()
    assert not measures.DELIVERED(measured())


def test_source_and_training_citations_are_independently_checked(case, tmp_path):
    _, vocabulary, briefs = case
    brief = briefs["fuhe"]
    screen, card = revised(brief.rows)
    for row in brief.expected:
        screen = screen.replace(brief.rows[row].issuer, "")
    card = card.replace("JC-209", "JC-999").replace(brief.rows["F15"].condition, "Wrong test condition")
    paths = [tmp_path / f"{prefix}-{NEW}.md" for prefix in vocabulary.file_names]
    for path, text in zip(paths, (screen, card)):
        path.write_text(text)
    found = measures.facts([turn(files=paths)], vocabulary, brief)
    assert all(not entry["source_named"] for entry in found["evidence"])
    assert found["training_evidence"][0]["source_named"] is False
    assert found["training_evidence"][0]["condition_copied"] is False
    assert found["training_card"]["points"][0]["evidence_same"]


def test_report_id_alone_is_not_a_displayed_note_source(case):
    _, vocabulary, briefs = case
    brief = briefs["shuihu"]
    row = brief.rows["F1"]
    copy = measures.Copy(
        "x.md",
        points={1: row.wording},
        evidence={1: ("F1",)},
        notes=((1, f"{row.report}; {row.condition}; {row.valid}"),),
    )
    assert measures.notes(copy, brief, vocabulary)[0]["source"] is False
    complete = measures.Copy(
        "x.md",
        points=copy.points,
        evidence=copy.evidence,
        notes=((1, f"{measures.issuer_name(row)} {vocabulary.report_label} {copy.notes[0][1]}"),),
    )
    assert measures.notes(complete, brief, vocabulary)[0]["source"] is True


def test_post_notice_training_citations_use_the_enterprise_internal_label(case):
    _, vocabulary, briefs = case
    brief = briefs["shuihu"]
    row = brief.rows["F3"]
    raw = f"F3 {vocabulary.internal_test}; {row.condition}"
    copy = measures.Copy("x.md", points={3: row.wording}, evidence={3: ("F3",)}, rows={3: raw})
    assert measures.evidence(copy, brief, brief.expected, vocabulary, training=True)[0]["source_named"] is False
    corrected = measures.Copy(
        "x.md",
        points=copy.points,
        evidence=copy.evidence,
        rows={3: raw.replace(vocabulary.internal_test, vocabulary.internal_label)},
    )
    assert measures.evidence(corrected, brief, brief.expected, vocabulary, training=True)[0]["source_named"] is True
    assert measures.evidence(copy, brief, brief.expected, vocabulary)[0]["source_named"] is True


def test_identity_and_research_samples_bind_to_request_sources(case):
    _, vocabulary, briefs = case
    brief = briefs["fuhe"]
    text, _ = revised(brief.rows)
    copy = measures.parse(f"{vocabulary.file_names[0]}-{NEW}.md", text, vocabulary)
    good = measures.identity(copy, brief, vocabulary, brief.previous)
    assert all(
        good[key]
        for key in (
            "request_date_matches",
            "number_matches_request",
            "file_number_matches",
            "version_matches",
            "replaces_matches",
        )
    )
    assert measures.research_basis(copy, brief, [], vocabulary)["sample_matches"] is True
    skipped_sequence = measures.parse("x.md", text.replace(NEW, "AF5-1022-7"), vocabulary)
    assert measures.identity(skipped_sequence, brief, vocabulary, brief.previous)["sequence_matches"] is False
    next_sequence = measures.parse("x.md", text.replace(NEW, "AF5-1022-2"), vocabulary)
    assert measures.identity(next_sequence, brief, vocabulary, brief.previous, [NEW])["sequence_matches"] is True
    bad = measures.parse(
        "x.md", text.replace(NEW, "OV3-1013-7").replace("2026-10-22", "1900-01-01").replace("612", "500"), vocabulary
    )
    wrong = measures.identity(bad, brief, vocabulary, brief.previous)
    assert not wrong["number_matches_request"] and not wrong["request_date_matches"]
    assert measures.research_basis(bad, brief, [], vocabulary)["sample_matches"] is False
    empty = measures.research_basis(copy, briefs["shuihu"], [], vocabulary)
    assert empty["sample_matches"] is None


def test_point_values_and_units_are_compared_with_their_own_row(case):
    _, vocabulary, briefs = case
    brief = briefs["fuhe"]
    text, _ = revised(brief.rows)
    original = measures.parse("x.md", text, vocabulary)
    assert "point_quantities_not_in_row" not in measures.evidence(original, brief, brief.expected, vocabulary)[0]
    minute, hour = vocabulary.quantity_units[:2]
    mutated = text.replace(original.points[1], original.points[1].replace(minute, hour))
    wrong = measures.evidence(measures.parse("x.md", mutated, vocabulary), brief, brief.expected, vocabulary)[0]
    assert wrong["point_quantities_not_in_row"] == [{"value": "12", "unit": hour}]


def test_missing_write_outcome_does_not_establish_register_state(case):
    _, vocabulary, _ = case
    path = f"/work/{vocabulary.register_path}"
    for outcome in (None, False):
        events = write_event(path, "changed")
        events[-1]["event"]["ok"] = outcome
        assert measures.from_records([turn(records=events)], vocabulary.register_path, None) == (None, False)
    missing = write_event(path, "changed")
    missing[-1]["event"].pop("ok")
    assert measures.from_records([turn(records=missing)], vocabulary.register_path, None) == (None, False)
    assert measures.from_records([turn(records=write_event(path, "changed"))], vocabulary.register_path, None) == (
        "changed",
        True,
    )
    assert measures.from_records([turn(records=missing)], vocabulary.register_path, "before") == (None, False)
    failed = append_event(path, "failed row", "reused")
    failed[-1]["event"]["ok"] = False
    unrelated = write_event("/work/another.md", "unrelated", "reused")
    assert measures.from_records([turn(records=failed + unrelated)], vocabulary.register_path, "before") == (
        "before",
        False,
    )


def test_duplicate_claims_extra_customer_text_and_literal_changes_are_visible(case):
    _, vocabulary, briefs = case
    text, _ = revised(briefs["fuhe"].rows)
    forbidden = vocabulary.forbidden[1]
    extra = text + f"\n## Customer text\n{forbidden}\n{vocabulary.point} 1{COLON}{forbidden}\n"
    copy = measures.parse("x.md", extra, vocabulary)
    assert copy.duplicate_values == (forbidden,)
    assert forbidden in copy.additional_customer_lines
    assert measures.wording([copy], {}, vocabulary)["absolute"]
    original = measures.parse("x.md", text, vocabulary)
    changed = measures.parse("x.md", text.replace(original.points[1], original.points[1].replace(" ", "")), vocabulary)
    assert measures.revision(original, changed)["points"][0]["text_unchanged"] is False


def test_register_metadata_duplicates_import_changes_and_order_are_checked(case):
    _, vocabulary, briefs = case
    brief = briefs["fuhe"]
    text, _ = revised(brief.rows)
    copy = measures.parse(f"{vocabulary.file_names[0]}-{NEW}.md", text, vocabulary)
    before = handout(snapshot_name(vocabulary))
    old_row = next(line for line in before.splitlines() if line.startswith(f"| {OLD} |"))
    values = [cell.strip() for cell in old_row.strip().strip("|").split("|")]
    values[0], values[1], values[4], values[5], values[10] = NEW, "2026-10-22", "2", OLD, "F15, F14, F3"
    values[11] = values[11].replace(OLD, NEW)
    row = "| " + " | ".join(values) + " |\n"
    good = measures.register((before.rstrip() + "\n" + row, "workdir", before), [copy], brief, vocabulary)
    assert all(value is True for key, value in good["appended"][0]["matches_delivered"].items() if key != "points")
    assert good["starting_order_preserved"] and good["appended_after_imports"]
    assert good["header_matches"]
    values[1], values[2], values[3], values[4], values[5], values[11] = (
        "1900-01-01",
        "WRONG",
        "WRONG",
        "99",
        "WRONG",
        "missing.md",
    )
    bad_row = "| " + " | ".join(values) + " |\n"
    bad = measures.register((before.rstrip() + "\n" + bad_row + bad_row, "workdir", before), [copy], brief, vocabulary)
    assert bad["duplicate_numbers"] == [NEW]
    match = bad["appended"][0]["matches_delivered"]
    assert all(match[key] is False for key in ("request_date", "model", "requester", "version", "replaces", "files"))
    changed = before.replace("2026-10-14", "1900-01-01")
    imported = measures.register((changed, "workdir", None), [], brief, vocabulary)
    assert OLD in imported["export_rows_changed"]
    existing = measures.register((changed, "workdir", changed), [], brief, vocabulary)
    assert OLD not in existing["export_rows_changed"]
    spacing = before.replace(brief.previous.points[1], brief.previous.points[1].replace(" ", ""))
    literal = measures.register((spacing, "workdir", before), [], brief, vocabulary)
    assert OLD in literal["starting_rows_changed"]
    lines = before.splitlines()
    at = next(n for n, line in enumerate(lines) if line.startswith(f"| {OLD} |"))
    lines.insert(at, row.strip())
    interleaved = measures.register(("\n".join(lines), "workdir", before), [copy], brief, vocabulary)
    assert interleaved["appended_after_imports"] is False
