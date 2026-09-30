"""Each turn keeps its own copy of the files it handed over through deliver_files, a timed-out turn included."""

import pytest

from experimental.curator.raven_adapter.baselines import Baseline
from experimental.curator.raven_adapter.worker import TurnTimeoutError, Worker, WorkerTimeoutError
from raven.config.raven import RavenConfig
from raven.config.schema import Config


def delivered(path, phase="start"):
    return {
        "kind": "runner.event",
        "event_type": "ToolEvent",
        "event": {"name": "deliver_files", "phase": phase, "arguments": {"files": [{"path": str(path)}]}},
    }


def test_delivered_files_are_copied_per_turn_and_later_rewrites_do_not_touch_the_copy(tmp_path):
    worker = Worker(Baseline(Config(), RavenConfig(), tmp_path), tmp_path / "worker")
    page = tmp_path / "trip.html"
    page.write_text("<h1>v0</h1>")
    records = [
        delivered(page),
        delivered(page, phase="end"),
        delivered(tmp_path / "missing.html"),
        {"kind": "runner.event"},
    ]
    first = worker._keep_deliverables("turn-1", records)
    page.write_text("<h1>v1</h1>")
    second = worker._keep_deliverables("turn-2", [delivered("trip.html")])
    assert first == (str(worker.root / "deliverables" / "turn-1" / "trip.html"),)
    assert open(first[0]).read() == "<h1>v0</h1>" and open(second[0]).read() == "<h1>v1</h1>"
    assert worker._keep_deliverables("turn-3", []) == ()


@pytest.mark.asyncio
async def test_a_turn_past_the_timeout_keeps_what_it_did_and_says_it_timed_out(tmp_path):
    worker = Worker(Baseline(Config(), RavenConfig(), tmp_path), tmp_path / "worker")
    page = tmp_path / "draft.html"
    page.write_text("<h1>draft</h1>")

    async def timed_out(request):
        turn = request["turn"]["turn_id"]
        rows = [{**delivered(page), "turn_id": turn}, {"kind": "runner.event", "turn_id": "an-earlier-turn"}]
        raise WorkerTimeoutError(f"worker timed out after {worker.timeout}s during the operation", rows)

    worker._exchange = timed_out
    with pytest.raises(TurnTimeoutError, match="timed out") as info:
        await worker.run("Plan a trip", session_key="curator:family:1")
    execution = info.value.execution
    assert execution.outcome == {"timed_out": True, "timeout": worker.timeout, "explicit_reply": False}
    assert [row["turn_id"] for row in execution.records] == [execution.turn_id]
    assert open(execution.deliverables[0]).read() == "<h1>draft</h1>" and worker.last_execution is execution
