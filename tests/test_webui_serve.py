"""The web view's server: run index and detail, kept deliverables, scenario criteria and deck thumbnails."""

import json
import os
import shutil
import threading
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import urlopen

import pytest

from experimental.iteration.hearing import opaque
from experimental.webui import serve
from experimental.webui.serve import (
    Handler,
    cached_page,
    compact,
    cursors,
    deliverable,
    detail,
    index,
    live,
    pending_stage,
    phase,
    scenario,
    thumbnails,
    upload,
    upload_thumbnails,
)


def write(root, worker, stem, run):
    path = root / worker / "iteration" / f"{stem}.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(run))
    return path


def kept(root, name="deck.pptx", body=b"deck"):
    file = root / "run" / "deliverables" / "turn-1" / name
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(body)
    return file


def fake_render(calls, pages=2, pause=None):
    def render(file, out, width):
        calls.append((file, width))
        if pause is not None:
            pause.wait(5)
        for number in range(1, pages + 1):
            (out / f"page-{number:02d}.png").write_bytes(b"png")

    return render


@pytest.fixture
def served(tmp_path):
    scenario_file = tmp_path / "scenario" / "scenario.json"
    scenario_file.parent.mkdir()
    scenario_file.write_text(
        json.dumps({"initial": ["sop"], "criteria": [{"id": "c1", "check": "C", "severity": "red_line"}]})
    )
    runs = tmp_path / "runs"
    runs.mkdir()
    cache = tmp_path / "thumbs-cache"
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), partial(Handler, root=runs.resolve(), scenario=scenario_file, cache=cache.resolve())
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}", runs
    server.shutdown()
    server.server_close()


def get(url):
    try:
        with urlopen(url, timeout=10) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        return error.code, json.loads(error.read())


def test_index_lists_runs_newest_first_and_detail_joins_records(tmp_path):
    first = write(tmp_path, "w1", "r1", {"task": "Older", "rounds": [{"analysis": ["a.json"], "curation": []}]})
    second = write(tmp_path, "w2", "r2", {"task": "Newer", "rounds": [], "error": "budget"})
    (tmp_path / "w1" / "analysis").mkdir()
    (tmp_path / "w1" / "analysis" / "a.json").write_text(json.dumps({"feedback": {"decision": "curate"}}))
    (tmp_path / "loose.json").write_text("{}")
    os.utime(first, (1, 1))
    os.utime(second, (2, 2))
    entries = index(tmp_path)
    assert [entry["id"] for entry in entries] == ["w2/r2", "w1/r1"]
    assert entries[0]["error"] == "budget" and entries[1]["rounds"] == 1
    assert entries[0]["status"] == "finished" and entries[1]["status"] == "finished"
    assert entries[1]["name"] == "w1" and entries[1]["passes"] == [[0, 0]]
    run = detail(tmp_path, "w1/r1")
    assert run["rounds"][0]["analysis"][0]["feedback"]["decision"] == "curate"
    assert run["labels"] == {}


def test_the_run_list_counts_the_scorecard_a_speaking_owner_kept(tmp_path):
    items = [{"id": "C1", "result": "pass"}, {"id": "C2", "result": "fail"}, {"id": "C3", "result": "unknown"}]
    rounds = [{"signals": [{"source": "agency", "text": "Close.", "items": []}], "analysis": ["s.json", "gone.json"]}]
    write(tmp_path, "w", "r", {"task": "T", "rounds": rounds})
    (tmp_path / "w" / "analysis").mkdir()
    (tmp_path / "w" / "analysis" / "s.json").write_text(
        json.dumps({"source": "agency", "scorecard": {"source": "agency", "items": items}})
    )
    assert index(tmp_path)[0]["passes"] == [[1, 1]]
    assert detail(tmp_path, "w1/missing") is None
    assert detail(tmp_path, "nope") is None
    assert detail(tmp_path, "../w1/r1") is None


def test_only_kept_deliverables_under_the_runs_root_are_served(tmp_path):
    kept = tmp_path / "run" / "deliverables" / "turn-1" / "trip.html"
    kept.parent.mkdir(parents=True)
    kept.write_text("<h1>trip</h1>")
    (tmp_path / "run" / "config.json").write_text("{}")
    outside = tmp_path.parent / "elsewhere.html"
    assert deliverable(tmp_path, str(kept)) == kept.resolve()
    assert deliverable(tmp_path, str(tmp_path / "run" / "config.json")) is None
    assert deliverable(tmp_path, str(kept.parent / ".." / ".." / "config.json")) is None
    assert deliverable(tmp_path, str(outside)) is None


def test_scenario_serves_criteria_with_severity_and_degrades_when_missing(tmp_path):
    spec = tmp_path / "travel" / "scenario.json"
    (tmp_path / "travel" / "materials" / "price-list").mkdir(parents=True)
    (tmp_path / "travel" / "materials" / "price-list" / "SKILL.md").write_text("prices")
    (tmp_path / "travel" / "materials" / "loose").mkdir()
    spec.write_text(
        json.dumps(
            {
                "initial": ["price-list"],
                "criteria": [
                    {"id": "quote", "check": "Quote from the list", "severity": "red_line"},
                    {"id": "tone", "check": "Warm"},
                ],
            }
        )
    )
    served = scenario(spec)
    assert served["criteria"] == [
        {"id": "quote", "check": "Quote from the list", "severity": "red_line"},
        {"id": "tone", "check": "Warm", "severity": "standard"},
    ]
    assert served["initial"] == ["price-list"] and served["materials"] == ["price-list"]
    assert scenario(tmp_path / "absent.json") == {"criteria": [], "initial": [], "materials": []}
    assert scenario(None)["criteria"] == []
    broken = tmp_path / "broken.json"
    broken.write_text("{")
    assert scenario(broken)["criteria"] == [] and "error" in scenario(broken)


def test_the_bundled_scenario_marks_red_lines():
    from experimental.webui.serve import SCENARIO

    served = scenario(SCENARIO)
    severities = {row["severity"] for row in served["criteria"]}
    assert served["criteria"] and severities <= {"red_line", "standard"} and "red_line" in severities


def test_thumbnails_refuse_paths_outside_kept_decks(tmp_path):
    calls = []
    render = fake_render(calls)
    notes = kept(tmp_path, "notes.md", b"# notes")
    loose = tmp_path / "run" / "deck.pptx"
    loose.parent.mkdir(parents=True, exist_ok=True)
    loose.write_bytes(b"deck")
    outside = tmp_path.parent / f"{tmp_path.name}-outside" / "deliverables" / "deck.pptx"
    outside.parent.mkdir(parents=True)
    outside.write_bytes(b"deck")
    deck = kept(tmp_path)
    assert thumbnails(tmp_path, str(notes), render=render) is None
    assert thumbnails(tmp_path, str(loose), render=render) is None
    assert thumbnails(tmp_path, str(outside), render=render) is None
    assert thumbnails(tmp_path, str(deck.parent / ".." / ".." / "deck.pptx"), render=render) is None
    assert (
        thumbnails(tmp_path, str(tmp_path / "run" / "deliverables" / "turn-1" / "missing.pptx"), render=render) is None
    )
    assert calls == []
    shutil.rmtree(outside.parent.parent)


def test_thumbnails_render_once_and_cache_beside_the_deck(tmp_path):
    calls = []
    deck = kept(tmp_path)
    pages = thumbnails(tmp_path, str(deck), render=fake_render(calls))
    cache = deck.parent / "deck.pptx.thumbs"
    assert pages == [cache / "page-01.png", cache / "page-02.png"]
    assert thumbnails(tmp_path, str(deck), render=fake_render(calls)) == pages
    assert len(calls) == 1 and calls[0][1] == 480
    assert sorted(path.name for path in deck.parent.iterdir()) == ["deck.pptx", "deck.pptx.thumbs"]
    assert deliverable(tmp_path, str(pages[0])) == pages[0].resolve()


def test_concurrent_thumbnail_requests_render_one_deck_once(tmp_path):
    calls, pause = [], threading.Event()
    deck = kept(tmp_path)
    render = fake_render(calls, pages=3, pause=pause)
    results = []
    threads = [
        threading.Thread(target=lambda: results.append(thumbnails(tmp_path, str(deck), render=render)))
        for _ in range(4)
    ]
    for thread in threads:
        thread.start()
    pause.set()
    for thread in threads:
        thread.join(10)
    assert len(calls) == 1
    assert len(results) == 4 and all(len(pages) == 3 for pages in results)


def test_a_failed_render_leaves_no_cache_and_is_retried(tmp_path):
    deck = kept(tmp_path)

    def broken(file, out, width):
        (out / "page-01.png").write_bytes(b"half")
        raise RuntimeError("LibreOffice produced no PDF")

    with pytest.raises(RuntimeError):
        thumbnails(tmp_path, str(deck), render=broken)
    assert sorted(path.name for path in deck.parent.iterdir()) == ["deck.pptx"]
    calls = []
    assert len(thumbnails(tmp_path, str(deck), render=fake_render(calls))) == 2 and len(calls) == 1


@pytest.mark.slow
@pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice is not installed")
def test_a_real_deck_renders_to_page_images(tmp_path):
    pptx = pytest.importorskip("pptx")
    pymupdf = pytest.importorskip("pymupdf")
    deck = kept(tmp_path)
    presentation = pptx.Presentation()
    for title in ("Plan", "Quote"):
        slide = presentation.slides.add_slide(presentation.slide_layouts[0])
        slide.shapes.title.text = title
    presentation.save(deck)
    pages = thumbnails(tmp_path, str(deck))
    assert [page.name for page in pages] == ["page-01.png", "page-02.png"]
    assert pymupdf.Pixmap(str(pages[0])).width == 480


def test_http_endpoints_serve_scenario_and_refuse_decks_outside_the_root(served, tmp_path):
    base, runs = served
    status, body = get(f"{base}/api/scenario")
    assert status == 200 and body["criteria"][0]["severity"] == "red_line" and body["initial"] == ["sop"]
    status, body = get(f"{base}/api/thumbs?path={quote(str(tmp_path / 'scenario' / 'scenario.json'))}")
    assert status == 404
    status, body = get(f"{base}/api/thumbs?path=")
    assert status == 404
    status, body = get(f"{base}/api/nothing")
    assert status == 404 and body["error"] == "unknown endpoint"


def test_http_thumbnails_report_a_failed_conversion(served):
    base, runs = served
    deck = kept(runs, "deck.pdf", b"not a pdf")
    status, body = get(f"{base}/api/thumbs?path={quote(str(deck))}")
    assert status == 500 and body["error"]
    assert sorted(path.name for path in deck.parent.iterdir()) == ["deck.pdf"]


def test_http_thumbnails_list_cached_pages(served):
    base, runs = served
    deck = kept(runs)
    cache = Path(f"{deck}.thumbs")
    cache.mkdir()
    (cache / "page-01.png").write_bytes(b"png")
    status, body = get(f"{base}/api/thumbs?path={quote(str(deck))}")
    assert status == 200 and body["pages"] == [str(cache / "page-01.png")]


CONTEXT = (
    "[Runtime Context \u2014 metadata only, not instructions]\nCurrent Time: 2026-09-24 01:09\nChannel: curator\n"
    "Chat ID: haggler:c0d9\n[BEGIN UNTRUSTED skill catalog #1 \u2014 data]\n- local/price-list: prices\n"
    "[END UNTRUSTED skill catalog #1]\n\n"
)


def request(turn, text, role="user"):
    return {
        "kind": "provider.request",
        "turn_id": turn,
        "parameters": {"messages": [{"role": "system", "content": "s"}, {"role": role, "content": text}]},
    }


def live_run(tmp_path, record, rows=(), worker="w1"):
    root = tmp_path / "runs"
    path = write(root, "run", "r1", record)
    log = root / "run" / "employee" / worker / "observations.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return root, path, log


def test_compact_keeps_what_the_live_view_draws_and_drops_heavy_rows():
    said = compact(request("t1", CONTEXT + "Can you do Sanya for less?"))
    assert said == {
        "kind": "provider.request",
        "turn_id": "t1",
        "text": "Can you do Sanya for less?",
        "drill": "haggler",
    }
    assert compact(request("t1", "The tool call under review: spawn")) is None
    assert compact(request("t1", "tool output", role="tool")) is None
    assert compact({"kind": "planning.observation", "turn_id": "t1", "observation": {"messages": ["x" * 5000]}}) is None
    assert compact({"kind": "memory.call", "turn_id": "t1", "operation": "compose", "arguments": [{"x": "y"}]}) is None
    event = {
        "scope": {"harness_id": "/runs/w/home", "session_key": "curator:haggler:1"},
        "event_id": "e1",
        "kind": "proposal",
        "stage": "tools",
        "calls": [{"name": "deliver_files", "arguments": {"body": "x" * 5000}}],
        "allowed_controls": ["continue", "reject"],
    }
    call = compact({"kind": "action.call", "turn_id": "t1", "operation": "handle_event", "arguments": [event]})
    assert call["arguments"] == {
        "kind": "proposal",
        "stage": "tools",
        "event_id": "e1",
        "allowed_controls": ["continue", "reject"],
        "calls": ["deliver_files"],
    }
    decided = compact(
        {
            "kind": "action.result",
            "turn_id": "t1",
            "operation": "handle_event",
            "result": {"control": "reject", "reason": "price early", "feedback": "Confirm first", "generation": None},
        }
    )
    assert decided["result"] == {"control": "reject", "reason": "price early", "feedback": "Confirm first"}
    answered = compact(
        {
            "kind": "action.result",
            "turn_id": "t1",
            "operation": "handle_request",
            "result": {"reply": {"ok": True}, "decision": {"control": "finish", "reply": "A colleague will call."}},
        }
    )
    assert answered["result"] == {"control": "finish", "reply": "A colleague will call."}
    receipt = compact(
        {
            "kind": "action.control",
            "turn_id": "t1",
            "receipt": {
                "scope": {"harness_id": "/runs/w/home"},
                "control_id": "k1",
                "source_id": "e1",
                "control": "reject",
                "status": "applied",
                "reason": None,
            },
        }
    )
    assert receipt["receipt"] == {
        "control_id": "k1",
        "source_id": "e1",
        "control": "reject",
        "status": "applied",
        "reason": "",
    }
    tool = compact(
        {
            "kind": "runner.event",
            "turn_id": "t1",
            "event_type": "ToolEvent",
            "event": {"phase": "complete", "tool_call_id": "c", "ok": False, "result_preview": "x" * 3000},
        }
    )
    assert tool["event"]["ok"] is False and len(tool["event"]["result_preview"]) < 1600
    assert (
        compact({"kind": "runner.event", "turn_id": "t1", "event_type": "Notice", "event": {"detail": "thinking"}})
        is None
    )
    done = compact(
        {
            "kind": "dag.progress",
            "turn_id": "t1",
            "name": "dag_run_completed",
            "payload": {
                "run_id": "r",
                "manifest": {
                    "dir": "/x",
                    "files": [
                        {"node": "deck", "subagent": "Raven-PPT", "status": "completed", "prompt_template": "long"}
                    ],
                },
            },
        }
    )
    assert done["payload"]["manifest"]["files"][0] == {
        "node": "deck",
        "subagent": "Raven-PPT",
        "status": "completed",
        "started_at": None,
        "ended_at": None,
        "error": None,
        "output_file": None,
        "depends_on": None,
    }


def test_live_reads_new_rows_from_an_offset_and_leaves_a_partial_line(tmp_path):
    text = {"kind": "runner.event", "turn_id": "t1", "event_type": "Text", "event": {"content": "Hello"}}
    root, _, log = live_run(
        tmp_path, {"status": "running", "rounds": [], "initial_curation": []}, [request("t1", CONTEXT + "Hi"), text]
    )
    first = live(root, "run/r1")
    (read,) = first["logs"]
    assert read["reset"] is True and read["file"] == "w1" and read["start"] == 0
    assert [row["kind"] for row in first["rows"]] == ["provider.request", "runner.event"]
    assert {row["file"] for row in first["rows"]} == {"w1"} and read["offset"] == log.stat().st_size
    with log.open("a") as stream:
        stream.write(json.dumps({"kind": "loop.control", "turn_id": "t1"}) + "\n" + '{"kind": "runner.ev')
    second = live(root, "run/r1", {"w1": read["offset"]})
    assert second["logs"][0]["reset"] is False and [row["kind"] for row in second["rows"]] == ["loop.control"]
    assert second["logs"][0]["offset"] < log.stat().st_size
    with log.open("a") as stream:
        stream.write('ent", "turn_id": "t2", "event_type": "Text", "event": {"content": "Next"}}\n')
    third = live(root, "run/r1", {"w1": second["logs"][0]["offset"]})
    assert [row["event"]["content"] for row in third["rows"]] == ["Next"]
    assert third["logs"][0]["offset"] == log.stat().st_size
    assert live(root, "run/r1", {"w1": third["logs"][0]["offset"]})["rows"] == []


def test_live_restarts_its_tail_on_a_new_worker_log_or_a_bad_offset(tmp_path, monkeypatch):
    rows = [
        {"kind": "runner.event", "turn_id": f"t{i}", "event_type": "Text", "event": {"content": f"reply {i}"}}
        for i in range(40)
    ]
    root, _, log = live_run(tmp_path, {"status": "running", "rounds": [], "initial_curation": []}, rows)
    assert live(root, "run/r1", {"w1": log.stat().st_size + 10})["logs"][0]["reset"] is True
    assert live(root, "run/r1", {"gone": 0})["logs"][0]["reset"] is True
    monkeypatch.setattr(serve, "LIVE_TAIL", 300)
    tail = live(root, "run/r1")
    start = tail["logs"][0]["start"]
    assert 0 < start < log.stat().st_size and tail["rows"] and tail["rows"][-1]["event"]["content"] == "reply 39"
    assert tail["rows"][0]["event"]["content"] != "reply 0"
    newer = root / "run" / "employee" / "w2" / "observations.jsonl"
    newer.parent.mkdir()
    newer.write_text(json.dumps({"kind": "runtime.bound", "turn_id": None, "targets": ["planning.strategy"]}) + "\n")
    os.utime(log, (1, 1))
    moved = live(root, "run/r1", {"w1": tail["logs"][0]["offset"]})
    assert [(read["file"], read["reset"]) for read in moved["logs"]] == [("w2", True)]
    assert moved["rows"][0]["kind"] == "runtime.bound" and moved["rows"][0]["file"] == "w2"


def test_live_follows_the_replicas_playing_drills_together(tmp_path, monkeypatch):
    said = [request("t1", CONTEXT + "Hi")]
    record = {"status": "running", "rounds": [], "initial_curation": []}
    root, path, log = live_run(tmp_path, record, said)
    family, honeymoon = opaque("family"), opaque("honeymoon")
    replicas = []
    for number, label in enumerate((family, honeymoon), 1):
        replica = root / "run" / "replicas" / f"1-{label}" / "employee" / "w" / "observations.jsonl"
        replica.parent.mkdir(parents=True)
        replica.write_text(json.dumps(request(f"r{number}", CONTEXT.replace("haggler", label) + "hello")) + "\n")
        os.utime(replica, (2_000 + number, 2_000 + number))
        replicas.append(replica)
    os.utime(log, (1_000, 1_000))
    reply = live(root, "run/r1")
    assert [read["file"] for read in reply["logs"]] == ["w1", f"replicas/1-{family}/w", f"replicas/1-{honeymoon}/w"]
    assert [(row["file"], row["drill"]) for row in reply["rows"]] == [
        ("w1", "haggler"),
        (f"replicas/1-{family}/w", family),
        (f"replicas/1-{honeymoon}/w", honeymoon),
    ]
    assert reply["labels"] == {}
    path.write_text(json.dumps({**record, "rounds": [{"sessions": {"family": [], "honeymoon": []}}]}))
    assert live(root, "run/r1")["labels"] == {"family": family, "honeymoon": honeymoon}
    offsets = {read["file"]: read["offset"] for read in reply["logs"]}
    with replicas[0].open("a") as stream:
        stream.write(json.dumps({"kind": "loop.control", "turn_id": "r1"}) + "\n")
    os.utime(replicas[0], (2_010, 2_010))
    again = live(root, "run/r1", offsets)
    assert [read["reset"] for read in again["logs"]] == [False, False, False]
    assert [(row["file"], row["kind"]) for row in again["rows"]] == [(f"replicas/1-{family}/w", "loop.control")]
    monkeypatch.setattr(serve, "LIVE_LOGS", 2)
    assert [read["file"] for read in live(root, "run/r1")["logs"]] == [
        f"replicas/1-{honeymoon}/w",
        f"replicas/1-{family}/w",
    ]
    os.utime(log, (2_010 - serve.STALLED - 1, 2_010 - serve.STALLED - 1))
    monkeypatch.setattr(serve, "LIVE_LOGS", 6)
    assert "w1" not in [read["file"] for read in live(root, "run/r1")["logs"]]


def test_live_cursors_read_each_log_and_offset_and_drop_malformed_pairs():
    assert cursors("w1:10,replicas/1-family/w:20") == {"w1": 10, "replicas/1-family/w": 20}
    assert cursors("w1:x,:4,nothing,w2:-1,") == {}


def test_live_skips_a_row_longer_than_one_read(tmp_path, monkeypatch):
    huge = {"kind": "runner.event", "turn_id": "t1", "event_type": "Text", "event": {"content": "x" * 5000}}
    small = {"kind": "runner.event", "turn_id": "t1", "event_type": "Text", "event": {"content": "after"}}
    root, _, log = live_run(tmp_path, {"status": "running", "rounds": [], "initial_curation": []}, [huge, small])
    monkeypatch.setattr(serve, "LIVE_CHUNK", 1000)
    first = live(root, "run/r1")
    offset = first["logs"][0]["offset"]
    assert first["rows"] == [] and 0 < offset < log.stat().st_size
    second = live(root, "run/r1", {"w1": offset})
    assert [row["event"]["content"] for row in second["rows"]] == ["after"]


def test_live_refuses_runs_outside_the_root(tmp_path):
    root, _, _ = live_run(tmp_path, {"status": "running", "rounds": []})
    assert live(root, "../run/r1") is None
    assert live(root, "run/missing") is None
    assert live(root, "run") is None
    assert live(root, "") is None


def test_live_reports_no_rows_before_the_worker_logs_anything(tmp_path):
    root = tmp_path / "runs"
    write(root, "run", "r1", {"status": "running", "rounds": []})
    reply = live(root, "run/r1")
    assert reply["rows"] == [] and reply["logs"] == [] and reply["phase"]["name"] == "curating"


def phase_of(tmp_path, record, rows=(), quiet=0.0, record_age=100.0, pending=None):
    root, path, log = live_run(tmp_path, record, rows)
    now = 1_000_000.0
    os.utime(path, (now - record_age, now - record_age))
    os.utime(log, (now - quiet, now - quiet))
    if pending is not None:
        (root / "run" / "curation").mkdir(exist_ok=True)
        (root / "run" / "curation" / "pending.json").write_text(json.dumps(pending))
    return phase(root / "run", record, path, now)


def test_phase_from_status_and_record(tmp_path):
    assert (
        phase_of(tmp_path / "a", {"status": "finished", "stop": "every evaluator is satisfied", "rounds": [{}]})["name"]
        == "finished"
    )
    assert phase_of(tmp_path / "b", {"status": "error", "error": "boom", "rounds": []})["basis"] == "boom"
    paused = phase_of(tmp_path / "c", {"status": "paused", "rounds": [{}]}, pending={"state": {"stage": "implement"}})
    assert (paused["name"], paused["stage"]) == ("paused", "implement")
    diagnosing = phase_of(tmp_path / "g", {"status": "paused", "rounds": [{}]}, pending={"attribution_state": {"x": 1}})
    assert (diagnosing["name"], diagnosing["stage"]) == ("paused", "diagnose")
    onboarding = phase_of(tmp_path / "d", {"status": "running", "rounds": []})
    assert (onboarding["name"], onboarding["round"]) == ("curating", 0)
    analysed = {
        "status": "running",
        "initial_curation": ["c.json"],
        "rounds": [{"feedback": {"decision": "curate"}, "curated": True, "curation": []}],
    }
    curating = phase_of(tmp_path / "e", analysed)
    assert (curating["name"], curating["round"]) == ("curating", 1)
    asked = {**analysed, "rounds": [{"feedback": {"decision": "curate"}, "curated": False, "curation": []}]}
    assert phase_of(tmp_path / "f", asked)["name"] != "curating"


def test_phase_of_a_trial_from_the_worker_log(tmp_path):
    record = {
        "status": "running",
        "initial_curation": ["c.json"],
        "rounds": [{"feedback": {"decision": "curate"}, "curation": ["d.json"]}],
    }
    opened = [request("t1", CONTEXT + "Hi")]
    closed = [*opened, {"kind": "loop.control", "turn_id": "t1"}]
    assert phase_of(tmp_path / "a", record, opened, quiet=600, record_age=900) == {
        "name": "trial",
        "round": 2,
        "stage": None,
        "basis": "a turn is in progress",
    }
    assert phase_of(tmp_path / "b", record, closed, quiet=30, record_age=900)["name"] == "trial"
    assert phase_of(tmp_path / "c", record, closed, quiet=600, record_age=900)["name"] == "judging or analysing"
    stalled = phase_of(tmp_path / "d", record, closed, quiet=3 * 3600, record_age=4 * 3600)
    assert stalled["name"] == "stalled or stopped" and "180 min" in stalled["basis"]
    abandoned = phase_of(tmp_path / "f", record, opened, quiet=3 * 3600, record_age=4 * 3600)
    assert abandoned["name"] == "stalled or stopped"
    assert phase_of(tmp_path / "e", record, closed, quiet=600, record_age=30)["name"] == "unknown"
    recorded = {**record, "pending": {"sessions": {"family": []}}}
    judged = phase_of(tmp_path / "g", recorded, closed, quiet=600, record_age=30)
    assert judged["name"] == "judging or analysing" and "round 2's trials are recorded" in judged["basis"]
    reviewed = {**record, "pending": {"review": {"activity": []}}}
    assert phase_of(tmp_path / "h", reviewed, closed, quiet=600, record_age=30)["name"] == "unknown"


def test_http_live_endpoint_serves_rows_and_refuses_bad_runs(served):
    base, runs = served
    path = write(runs, "run", "r1", {"status": "running", "rounds": [], "initial_curation": []})
    log = runs / "run" / "employee" / "w1" / "observations.jsonl"
    log.parent.mkdir(parents=True)
    log.write_text(json.dumps(request("t1", CONTEXT + "Hi")) + "\n")
    status, body = get(f"{base}/api/live?run=run/r1")
    assert status == 200 and body["rows"][0]["text"] == "Hi" and body["phase"]["name"] in ("trial", "unknown")
    status, body = get(f"{base}/api/live?run=run/r1&logs={quote('w1:' + str(body['logs'][0]['offset']))}")
    assert status == 200 and body["rows"] == [] and body["logs"][0]["reset"] is False
    status, body = get(f"{base}/api/live?run=run/r1&logs=w1:abc")
    assert status == 200 and body["logs"][0]["reset"] is True
    assert get(f"{base}/api/live?run=../run/r1")[0] == 404
    assert get(f"{base}/api/live?run={quote(str(path))}")[0] == 404


def uploaded_run(tmp_path):
    root = tmp_path / "runs"
    write(root, "run", "r1", {"status": "running", "rounds": [], "opening": []})
    uploads = root / "run" / "employee" / "home" / "uploads"
    uploads.mkdir(parents=True)
    (uploads / "service-sop.md").write_text("# Service SOP\n\nConfirm before quoting.")
    (uploads / "plan-deck-template.pptx").write_bytes(b"deck")
    (root / "run" / "employee" / "home" / "skills").mkdir()
    (root / "run" / "employee" / "home" / "skills" / "secret.md").write_text("not an upload")
    (root / "run" / "config.json").write_text("{}")
    return root, uploads


def test_upload_reaches_only_the_runs_home_uploads(tmp_path):
    root, uploads = uploaded_run(tmp_path)
    assert upload(root, "run/r1", "uploads/service-sop.md") == (uploads / "service-sop.md").resolve()
    assert upload(root, "run/r1", "skills/secret.md") is None
    assert upload(root, "run/r1", "uploads/../skills/secret.md") is None
    assert upload(root, "run/r1", "uploads/../../config.json") is None
    assert upload(root, "run/r1", str(uploads / "service-sop.md")) is None
    assert upload(root, "run/r1", "uploads/missing.md") is None
    assert upload(root, "run/r1", "uploads") is None
    assert upload(root, "run/r1", "") is None
    assert upload(root, "../run/r1", "uploads/service-sop.md") is None
    assert upload(root, "run/other", "uploads/service-sop.md") is None
    (uploads / "escape.md").symlink_to(root / "run" / "employee" / "home" / "skills" / "secret.md")
    assert upload(root, "run/r1", "uploads/escape.md") is None


def test_upload_thumbnails_are_cached_outside_the_run(tmp_path):
    root, uploads = uploaded_run(tmp_path)
    cache = tmp_path / "cache"
    calls = []
    pages = upload_thumbnails(root, "run/r1", "uploads/plan-deck-template.pptx", cache, render=fake_render(calls))
    assert len(pages) == 2 and all(page.is_relative_to(cache) for page in pages)
    assert sorted(path.name for path in uploads.iterdir()) == ["plan-deck-template.pptx", "service-sop.md"]
    assert (
        upload_thumbnails(root, "run/r1", "uploads/plan-deck-template.pptx", cache, render=fake_render(calls)) == pages
    )
    assert len(calls) == 1
    assert upload_thumbnails(root, "run/r1", "uploads/service-sop.md", cache, render=fake_render(calls)) is None
    assert upload_thumbnails(root, "run/r1", "uploads/../../config.json", cache, render=fake_render(calls)) is None
    assert cached_page(cache, str(pages[0])) == pages[0].resolve()
    assert cached_page(cache, str(uploads / "service-sop.md")) is None
    assert cached_page(cache, str(cache / ".." / "runs" / "run" / "config.json")) is None


def test_http_upload_serves_text_as_plain_text_and_refuses_the_rest(served):
    base, runs = served
    write(runs, "run", "r1", {"status": "running", "rounds": []})
    uploads = runs / "run" / "employee" / "home" / "uploads"
    uploads.mkdir(parents=True)
    (uploads / "sop.md").write_text("# SOP")
    (uploads / "run.sh").write_text("echo hi")
    (runs / "run" / "employee" / "home" / "notes.md").write_text("private")
    with urlopen(f"{base}/api/upload?run=run/r1&path={quote('uploads/sop.md')}", timeout=10) as response:
        assert response.read().decode() == "# SOP"
        assert response.headers["Content-Type"] == "text/plain; charset=utf-8"
        assert response.headers["Content-Security-Policy"] == "sandbox"
    for path in ("uploads/run.sh", "notes.md", "uploads/../notes.md", str(uploads / "sop.md")):
        assert get(f"{base}/api/upload?run=run/r1&path={quote(path)}")[0] == 404
    assert get(f"{base}/api/upload?run=..%2Frun%2Fr1&path={quote('uploads/sop.md')}")[0] == 404
    assert get(f"{base}/api/thumbs?run=run/r1&upload={quote('notes.md')}")[0] == 404
    assert get(f"{base}/files?path={quote(str(uploads / 'sop.md'))}")[0] == 404


def progress_file(worker_root, age, now=1_000_000.0, **fields):
    path = worker_root / "progress" / "curation.json"
    path.parent.mkdir(exist_ok=True)
    body = {
        "started": now - age - 60,
        "updated": now - age,
        "stage": "implement",
        "calls": 7,
        "queries": 12,
        "checks": 1,
        "repairs": 0,
        "staged": ["pkg/gate.py"],
        "events": [{"stage": "implement", "event": "file.staged", "path": "pkg/gate.py"}],
    }
    path.write_text(json.dumps({**body, **fields}))
    os.utime(path, (now - age, now - age))
    return path


def test_live_carries_the_curators_progress_and_refuses_a_linked_one(tmp_path):
    root, _, _ = live_run(tmp_path, {"status": "running", "rounds": []})
    assert live(root, "run/r1")["curator"] is None
    progress_file(root / "run", 5)
    assert live(root, "run/r1")["curator"]["staged"] == ["pkg/gate.py"]
    (root / "run" / "progress" / "curation.json").write_text("{broken")
    assert live(root, "run/r1")["curator"] is None
    outside = tmp_path / "elsewhere.json"
    outside.write_text(json.dumps({"stage": "select"}))
    (root / "run" / "progress" / "curation.json").unlink()
    (root / "run" / "progress" / "curation.json").symlink_to(outside)
    assert live(root, "run/r1")["curator"] is None


def test_phase_follows_the_curators_progress(tmp_path):
    onboarding = {"status": "running", "rounds": []}
    root, path, _ = live_run(tmp_path / "a", onboarding)
    now = 1_000_000.0
    os.utime(path, (now - 100, now - 100))
    os.utime(root / "run" / "employee" / "w1" / "observations.jsonl", (now - 100, now - 100))
    progress_file(root / "run", 20)
    curating = phase(root / "run", onboarding, path, now)
    assert (curating["name"], curating["round"], curating["stage"]) == ("curating", 0, "implement")
    assert "7 calls, 12 queries" in curating["basis"]
    trialled = {
        "status": "running",
        "initial_curation": ["c.json"],
        "rounds": [{"feedback": {"decision": "curate"}, "curated": True, "curation": []}],
    }
    progress_file(root / "run", 20, stage="repair")
    assert phase(root / "run", trialled, path, now)["stage"] == "repair"
    progress_file(root / "run", 20, finished=True, error="validation failed: gate signature")
    failed = phase(root / "run", trialled, path, now)
    assert failed["name"] == "error" and "gate signature" in failed["basis"]
    errored = phase(root / "run", {"status": "error", "rounds": []}, path, now)
    assert "gate signature" in errored["basis"]
    progress_file(root / "run", 20, finished=True, error=None)
    assert phase(root / "run", trialled, path, now)["basis"].startswith("round 1 was analysed")
    progress_file(root / "run", 3 * 3600)
    os.utime(path, (now - 3 * 3600, now - 3 * 3600))
    os.utime(root / "run" / "employee" / "w1" / "observations.jsonl", (now - 3 * 3600, now - 3 * 3600))
    assert phase(root / "run", onboarding, path, now)["name"] == "stalled or stopped"


def test_index_marks_a_running_record_with_no_recent_writes_as_stalled(tmp_path):
    root, path, log = live_run(tmp_path, {"status": "running", "rounds": []})
    now = 1_000_000.0
    for file in (path, log):
        os.utime(file, (now - 3 * 3600, now - 3 * 3600))
    assert index(root, now)[0]["status"] == "stalled"
    progress_file(root / "run", 60)
    assert index(root, now)[0]["status"] == "running"
    finished = write(root, "done", "r2", {"status": "finished", "rounds": []})
    os.utime(finished, (now - 3 * 3600, now - 3 * 3600))
    assert {entry["id"]: entry["status"] for entry in index(root, now)}["done/r2"] == "finished"


def test_composition_progress_reads_the_active_scope_and_cumulative_counts(tmp_path):
    from experimental.webui.serve import curator_progress

    scopes = tmp_path / "curation/scopes/attempt"
    (tmp_path / "curation").mkdir()
    (tmp_path / "curation/composition.json").write_text(json.dumps({"directory": str(scopes)}))
    (scopes / "root").mkdir(parents=True)
    (scopes / "child-example").mkdir()
    progress_file(scopes / "root", 10, calls=3, finished=True)
    progress_file(scopes / "child-example", 1, calls=2, stage="implement")
    current = curator_progress(tmp_path)
    assert current["scope"] == "child-example"
    assert current["calls"] == 5 and current["stage"] == "implement"
    checkpoint = {"directory": str(scopes), "scopes": {"Raven-PPT": "child-example"}}
    (tmp_path / "curation/composition.json").write_text(json.dumps(checkpoint))
    assert curator_progress(tmp_path)["scope"] == "Raven-PPT"
    assert pending_stage(tmp_path) is None
    (scopes / "root" / "curation").mkdir()
    (scopes / "root" / "curation" / "pending.json").write_text(json.dumps({"state": {"stage": "select"}}))
    assert pending_stage(tmp_path) == "select"
    (scopes / "child-example" / "curation").mkdir()
    (scopes / "child-example" / "curation" / "pending.json").write_text(json.dumps({"state": {"stage": "implement"}}))
    os.utime(scopes / "root" / "curation" / "pending.json", (1, 1))
    assert pending_stage(tmp_path) == "implement"
    (scopes / "child-example" / "curation" / "pending.json").write_text(json.dumps({"attribution_state": {"a": 1}}))
    assert pending_stage(tmp_path) == "diagnose"


def test_the_run_list_carries_the_verdict_and_mining_summaries_rank_their_runs(served):
    url, runs = served
    write(runs, "hoh-staged-0925", "r1", {"task": "T", "rounds": []})
    (runs / "hoh-staged-0925" / "suite-summary.json").write_text(
        json.dumps({"spend": {"total": 12.5}, "value": {"verdict": "partial", "score": 21, "cases": 2}})
    )
    (runs / "hoh-mining-0925-1200.json").write_text(
        json.dumps(
            {
                "spend": 12.5,
                "ranking": [
                    {
                        "label": "staged",
                        "plan": ["--chain", "staged"],
                        "name": "hoh-staged-0925",
                        "status": "finished",
                        "rounds": 4,
                        "spend": {"total": 12.5, "employee": 3},
                        "value": {"verdict": "partial", "score": 21, "cases": 2},
                        "notes": ["dropped"],
                    },
                    "not a run",
                ],
            }
        )
    )
    (entry,) = index(runs)
    assert (entry["verdict"], entry["score"], entry["spend"]) == ("partial", 21, 12.5)
    status, body = get(f"{url}/api/mining")
    assert status == 200
    (session,) = body["sessions"]
    assert session["file"] == "hoh-mining-0925-1200.json" and session["spend"] == 12.5
    assert session["ranking"] == [
        {
            "label": "staged",
            "plan": ["--chain", "staged"],
            "name": "hoh-staged-0925",
            "status": "finished",
            "rounds": 4,
            "stopped": None,
            "spend": 12.5,
            "value": {"verdict": "partial", "score": 21, "cases": 2},
        }
    ]


def test_http_studio_serves_a_slim_run_its_kept_records_and_the_index(served):
    base, runs = served
    execution = {
        "turn_id": "t",
        "records": [{"kind": "provider.request", "parameters": {"model": "m", "messages": [], "tools": []}}],
    }

    def recorded(model):
        request = {"kind": "provider.request", "parameters": {"model": model, "messages": [], "tools": []}}
        return {"turn_id": "t", "records": [request]}

    record = {
        "task": "job",
        "rounds": [
            {
                "sessions": {"family": [{"user": "hi", "execution": execution}]},
                "holdout": {"quiet": [{"user": "held", "execution": recorded("h")}]},
            }
        ],
        "pending": {"sessions": {"family": [{"user": "next", "execution": recorded("p")}]}},
    }
    write(runs, "w", "r", record)
    status, run = get(f"{base}/api/studio/runs/w/r")
    assert status == 200
    kept = run["rounds"][0]["sessions"]["family"][0]["execution"]["records"][0]
    assert kept["ref"] == {"round": 0, "part": "sessions", "session": "family", "turn": 0, "index": 0}
    assert run["standard"] is None and run["boundaries"] is None
    status, raw = get(f"{base}/api/studio/raw?run=w/r&round=0&session=family&turn=0&index=0")
    assert (status, raw["parameters"]["model"]) == (200, "m")
    held = get(f"{base}/api/studio/raw?run=w/r&round=0&part=holdout&session=quiet&turn=0&index=0")
    assert (held[0], held[1]["parameters"]["model"]) == (200, "h")
    pending = get(f"{base}/api/studio/raw?run=w/r&round=pending&session=family&turn=0&index=0")
    assert (pending[0], pending[1]["parameters"]["model"]) == (200, "p")
    assert get(f"{base}/api/studio/raw?run=w/r&round=0&session=family&turn=0&index=5")[0] == 404
    assert get(f"{base}/api/studio/raw?run=w/r&round=x&session=family&turn=0&index=0")[0] == 404
    assert get(f"{base}/api/studio/raw?run=w/r&round=0&part=elsewhere&session=family&turn=0&index=0")[0] == 404
    assert get(f"{base}/api/studio/runs/w/missing")[0] == 404
    status, listed = get(f"{base}/api/studio/runs")
    assert status == 200 and [entry["id"] for entry in listed] == ["w/r"]


def test_http_record_is_built_by_the_builder_and_a_builder_failure_is_its_answer(tmp_path):
    runs = tmp_path / "runs"
    write(runs, "w", "r", {"task": "job", "rounds": []})
    calls = []

    def builder(worker_root, scenario_dir, state_root=None):
        calls.append(worker_root.name)
        if len(calls) > 1:
            raise RuntimeError("boom")
        return {"schema": 1, "run": worker_root.name}

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, root=runs.resolve(), builder=builder))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        assert get(f"{base}/api/record?run=w/r") == (200, {"schema": 1, "run": "w"})
        assert get(f"{base}/api/record?run=w/r") == (200, {"schema": 1, "run": "w"}) and calls == ["w"]
        (runs / "w" / "iteration" / "r.json").write_text(json.dumps({"task": "job", "rounds": [{}]}))
        status, body = get(f"{base}/api/record?run=w/r")
        assert status == 500 and body["error"] == "the record builder failed: RuntimeError: boom"
        assert get(f"{base}/api/record?run=w/missing")[0] == 404
    finally:
        server.shutdown()
        server.server_close()


def test_http_answers_a_record_that_fails_to_load_with_its_error(served):
    base, runs = served
    write(runs, "w", "r", {"task": "job", "rounds": [{"sessions": "not a mapping"}]})
    for url in (
        f"{base}/api/studio/runs/w/r",
        f"{base}/api/runs/w/r",
        f"{base}/api/studio/raw?run=w/r&round=0&session=family&turn=0&index=0",
    ):
        status, body = get(url)
        assert status == 422 and body["error"].startswith("the run record r.json could not be loaded")
