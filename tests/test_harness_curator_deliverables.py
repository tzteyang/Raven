"""Each turn keeps its own copy of the files it handed over through deliver_files, a timed-out turn included; a
call the turn made that handed nothing over, such as one an Action strategy refused, keeps nothing."""

import pytest

from experimental.harness.raven_adapter.baselines import Baseline
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
