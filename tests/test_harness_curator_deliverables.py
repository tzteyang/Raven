"""Each turn keeps its own copy of the files it handed over through deliver_files, a timed-out turn included; a
call the turn made that handed nothing over, such as one an Action strategy refused, keeps nothing."""

import pytest

from experimental.harness.raven_adapter.baselines import Baseline
from experimental.harness.raven_adapter.observe import Recorder, delivered_files
from experimental.harness.raven_adapter.worker import TurnTimeoutError, Worker, WorkerTimeoutError
from raven.config.raven import RavenConfig
from raven.config.schema import Config


def delivered(path, *, refused=False):
    """A deliver_files call as Raven records it: the start names the tool, the completion carries the manifest."""
    manifest = None if refused else {"raven_delivery": {"message": "Here it is", "files": [{"path": str(path)}]}}
    return [
        {
            "kind": "runner.event",
            "event_type": "ToolEvent",
            "event": {"name": "deliver_files", "phase": "start", "arguments": {"files": [{"path": str(path)}]}},
        },
        {
            "kind": "runner.event",
            "event_type": "ToolEvent",
            "event": {"name": "", "phase": "complete", "ok": True, "metadata": manifest},
        },
    ]


def test_delivered_files_are_copied_per_turn_and_later_rewrites_do_not_touch_the_copy(tmp_path):
    worker = Worker(Baseline(Config(), RavenConfig(), tmp_path), tmp_path / "worker")
    page = tmp_path / "trip.html"
    page.write_text("<h1>v0</h1>")
    held = tmp_path / "held.html"
    held.write_text("<h1>held</h1>")
    records = [
        *delivered(page),
        *delivered(held, refused=True),
        *delivered(tmp_path / "missing.html"),
        {"kind": "runner.event"},
    ]
    first = worker._keep_deliverables("turn-1", records)
    page.write_text("<h1>v1</h1>")
    second = worker._keep_deliverables("turn-2", delivered(page))
    assert first == (str(worker.root / "deliverables" / "turn-1" / "trip.html"),)
    assert open(first[0]).read() == "<h1>v0</h1>" and open(second[0]).read() == "<h1>v1</h1>"
    assert worker._keep_deliverables("turn-3", []) == ()


def test_delivery_completion_retains_each_version_before_same_turn_overwrites(tmp_path):
    from pathlib import Path

    from experimental.cultivation.counterpart.owner import delivery_versions
    from experimental.harness.participation.protocols import Exchange
    from experimental.harness.raven_adapter.worker import Execution

    worker = Worker(Baseline(Config(), RavenConfig(), tmp_path), tmp_path / "worker")
    recorder = Recorder(worker.area / "generation" / "observations.jsonl")
    recorder.delivery_roots = (tmp_path, worker.area)
    recorder.turn_id = "one-turn"
    page = tmp_path / "quote.html"
    for version in ("First delivered version", "Second delivered version"):
        page.write_text(version)
        for row in delivered(page):
            recorder.add(row["kind"], **{key: value for key, value in row.items() if key != "kind"})
    page.write_text("Never delivered")
    kept = worker._keep_deliverables("one-turn", recorder.rows)
    assert len(set(kept)) == 2
    assert [Path(path).name for path in kept] == ["quote.html", "quote.html"]
    assert [Path(path).read_text() for path in kept] == ["First delivered version", "Second delivered version"]
    exchange = Exchange("Deliver both versions.", Execution("one-turn", [], recorder.rows, {}, deliverables=kept))
    versions = delivery_versions([exchange])[0]["versions"]
    assert [row["content"] for row in versions] == ["First delivered version", "Second delivered version"]
    assert len({row["sha256"] for row in versions}) == 2
    first = delivered_files(recorder.rows[1])[0]["retained"]
    Path(first["path"]).write_text("Corrupted snapshot")
    assert len(worker._keep_deliverables("another-turn", recorder.rows)) == 1


@pytest.mark.parametrize("outcome", [False, None, 1, "true"])
def test_unconfirmed_delivery_outcomes_supply_no_files(tmp_path, outcome):
    row = delivered(tmp_path / "report.md")[-1]
    row["event"]["ok"] = outcome
    assert delivered_files(row) == []


def test_delivery_snapshot_never_reads_a_link_outside_worker_roots(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    private = tmp_path / "private.md"
    private.write_text("Host-only material")
    linked = work / "report.md"
    linked.symlink_to(private)
    recorder = Recorder(tmp_path / "area" / "observations.jsonl")
    recorder.delivery_roots = (work,)
    row = delivered(linked)[-1]
    recorder.add(row["kind"], **{key: value for key, value in row.items() if key != "kind"})
    item = delivered_files(recorder.rows[0])[0]
    assert item["retained"]["path"] is None
    assert not (recorder.path.parent / "deliveries").exists()


def test_recorded_event_clocks_are_host_observations_not_payload_claims(tmp_path, monkeypatch):
    from experimental.harness.raven_adapter import observe

    monkeypatch.setattr(observe.time, "time", lambda: 123.5)
    monkeypatch.setattr(observe.time, "monotonic_ns", lambda: 456789)
    recorder = Recorder(tmp_path / "observations.jsonl")
    recorder.add("runner.event", observed_at=0, monotonic_ns=-1)
    assert recorder.rows[0]["observed_at"] == 123.5
    assert recorder.rows[0]["monotonic_ns"] == 456789


@pytest.mark.asyncio
async def test_a_turn_past_the_timeout_keeps_what_it_did_and_says_it_timed_out(tmp_path):
    worker = Worker(Baseline(Config(), RavenConfig(), tmp_path), tmp_path / "worker")
    page = tmp_path / "draft.html"
    page.write_text("<h1>draft</h1>")

    async def timed_out(request):
        turn = request["turn"]["turn_id"]
        rows = [{**row, "turn_id": turn} for row in delivered(page)] + [
            {"kind": "runner.event", "turn_id": "an-earlier-turn"}
        ]
        raise WorkerTimeoutError(f"worker timed out after {worker.timeout}s during the operation", rows)

    worker._exchange = timed_out
    with pytest.raises(TurnTimeoutError, match="timed out") as info:
        await worker.run("Plan a trip", session_key="curator:family:1")
    execution = info.value.execution
    assert execution.outcome == {"timed_out": True, "timeout": worker.timeout, "explicit_reply": False}
    assert [row["turn_id"] for row in execution.records] == [execution.turn_id] * 2
    assert open(execution.deliverables[0]).read() == "<h1>draft</h1>" and worker.last_execution is execution
