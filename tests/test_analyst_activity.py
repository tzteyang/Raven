"""Mechanism activity counts each decision once.

The resample test takes its rows from the producers themselves (the bound strategy's call and callback records,
the loop observer's control row); the other fixtures follow the same shapes by hand, texts translated to English.
"""

import pytest

from experimental.analyst.activity import activity
from experimental.curator.raven_adapter.worker import Execution
from experimental.iteration.protocols import Exchange

FEEDBACK = "This message asks three questions; keep at most two."
REFUSED_STEP = [
    {
        "kind": "planning.error",
        "turn_id": "t",
        "operation": "revise",
        "source": "tool",
        "error": "ValueError: moving from S1 to S3 is not allowed (stages may not be skipped)",
    },
    {
        "kind": "planning.error",
        "turn_id": "t",
        "operation": "tool",
        "source": "tool",
        "error": "moving from S1 to S3 is not allowed (stages may not be skipped)",
    },
    {"kind": "planning.error", "turn_id": "t", "operation": "view", "error": "KeyError: 'stage'"},
]


def rows_of(records):
    sessions = {"family": [Exchange("Hi", Execution("t", [], records, {}, "a"))]}
    return {(row["target"], row["decision"]): row for row in activity(sessions)}


@pytest.mark.asyncio
async def test_a_resample_counts_once_though_the_host_applies_it_and_the_loop_rolls_back(tmp_path):
    from types import SimpleNamespace

    from experimental.curator.raven_adapter.observe import LoopObserver
    from raven.contracts.llm_provider import LLMResponse
    from raven.contracts.loop_hooks import AgentHookContext
    from tests.test_harness_curator_strategies import make

    owner = make(tmp_path, "action")
    await owner.prepare()
    owner.recorder.turn_id = "t"
    owner.bind(SimpleNamespace(loop=SimpleNamespace(_MAX_HOOK_ROLLBACKS=3)))
    context = AgentHookContext(session_key="session", messages=[], response=LLMResponse(content="Unverified reply."))
    assert (await owner.hook().after_iteration(context)).rollback
    context.metadata["hook_rollbacks"] = 1
    await owner.finish()
    observer = LoopObserver(owner.recorder)
    observer.metadata = context.metadata
    observer.finish()
    assert [row["kind"] for row in owner.recorder.rows] == [
        "action.call",
        "action.result",
        "action.control",
        "action.control",
        "loop.control",
    ]
    rows = rows_of(owner.recorder.rows)
    interventions = {key: row["count"] for key, row in rows.items() if row["acted"]}
    assert interventions == {("action.strategy", "resample"): 1}
    assert "Call evidence_probe before finishing." in rows[("action.strategy", "resample")]["reasons"][0]
    assert rows[("action.strategy", "control_requested")]["count"] == 1 and not rows[("loop", "rollback")]["acted"]
    assert rows[("action.strategy", "assessed")]["count"] == 1 and not rows[("action.strategy", "assessed")]["acted"]


def test_control_receipts_count_actual_application_once_and_preserve_request_timing():
    def control(identity, operation, status):
        return {
            "kind": "action.control",
            "receipt": {
                "control_id": identity,
                "control": operation,
                "status": status,
            },
        }

    rows = rows_of(
        [
            control("end", "finish", "requested"),
            {"kind": "runner.event", "event_type": "Text", "event": {"content": "Final reply"}},
            control("end", "finish", "applied"),
            control("end", "finish", "applied"),
            control("blocked", "reject", "applied"),
            {
                "kind": "runner.event",
                "event_type": "ToolEvent",
                "event": {
                    "phase": "complete",
                    "name": "probe",
                    "ok": False,
                    "result_preview": "Action refused this call [blocked]: Missing evidence.",
                },
            },
            control("budget", "revise", "requested"),
            control("budget", "revise", "rejected"),
            control("invalid", "revise", "unsupported"),
        ]
    )
    acted = {key: row["count"] for key, row in rows.items() if row["acted"]}
    assert acted == {("action.strategy", "end"): 1, ("action.strategy", "refused"): 1}
    assert not rows[("action.strategy", "end")].get("after_visible_output")
    assert rows[("action.strategy", "refused")]["after_visible_output"] == 1
    assert rows[("action.strategy", "control_rejected")]["count"] == 1
    assert rows[("action.strategy", "control_unsupported")]["count"] == 1


def test_a_send_back_counts_in_the_hosts_verdict_whatever_word_the_generated_reviewer_used():
    """The reviewer said `revise` with a rule code; the host carried it out as a resample."""
    correction = "G2: this message asks three questions; at most two per message. Cut and rewrite."
    rows = rows_of(
        [
            {
                "kind": "action.result",
                "turn_id": "t",
                "operation": "assess",
                "source": "review",
                "result": {"verdict": "revise", "rule": "G2", "message": correction, "note": None, "reply": None},
            },
            {
                "kind": "action.callback",
                "turn_id": "t",
                "operation": "review",
                "result": {"verdict": "resample", "reason": "G2", "inject": [{"role": "user", "content": correction}]},
            },
            {"kind": "loop.control", "turn_id": "t", "rollbacks": 1, "rollbacks_refused": 0, "mode": "high"},
        ]
    )
    sent_back = rows[("action.strategy", "resample")]
    assert sent_back["acted"] and sent_back["count"] == 1 and correction in sent_back["reasons"][0]
    assert ("action.strategy", "revise") not in rows


def test_a_planning_step_the_strategy_rejects_is_one_refusal_and_a_crash_stays_an_error():
    rows = rows_of(REFUSED_STEP)
    refused = rows[("planning.strategy", "refused")]
    assert refused["acted"] and refused["count"] == 1 and refused["reasons"][0].startswith("moving from S1")
    assert rows[("planning.strategy", "error")]["count"] == 1 and not rows[("planning.strategy", "error")]["acted"]


def test_a_failed_tool_is_a_fact_for_the_curator_and_not_an_intervention():
    """The worker could not open a handed-over file."""
    rows = rows_of(
        [
            {
                "kind": "runner.event",
                "event_type": "ToolEvent",
                "event": {
                    "phase": "start",
                    "tool_call_id": "r1",
                    "name": "read_file",
                    "arguments": {"path": "uploads/x.md"},
                },
            },
            {
                "kind": "runner.event",
                "event_type": "ToolEvent",
                "event": {
                    "phase": "complete",
                    "tool_call_id": "r1",
                    "ok": False,
                    "result_preview": "Error: File not found: uploads/x.md",
                },
            },
        ]
    )
    failed = rows[("tool:read_file", "failed")]
    assert not failed["acted"] and failed["reasons"] == ["Error: File not found: uploads/x.md"]


def test_a_plan_that_never_changes_and_a_send_back_after_the_reply_was_visible_are_stated():
    """The plan stays at one stage for every view, and a resample comes after the reply was already shown."""
    view = {"kind": "planning.result", "operation": "view", "result": {"stage": "S1", "confirmed": False}}
    shown = {"kind": "runner.event", "event_type": "Text", "event": {"content": "Your total is 12,000."}}
    sent_back = [
        {"kind": "action.call", "turn_id": "t2", "operation": "assess", "source": "review"},
        {
            "kind": "action.result",
            "turn_id": "t2",
            "operation": "assess",
            "source": "review",
            "result": {"action": "resample", "feedback": FEEDBACK},
        },
        {
            "kind": "action.callback",
            "turn_id": "t2",
            "operation": "review",
            "result": {"verdict": "resample", "reason": FEEDBACK, "inject": [{"role": "user", "content": FEEDBACK}]},
        },
    ]
    turns = [
        Exchange("Hi", Execution("t1", [], [view, view], {}, "a")),
        Exchange("Yes", Execution("t2", [], [view, shown, *sent_back], {}, "a")),
    ]
    rows = {(row["target"], row["decision"]): row for row in activity({"family": turns})}
    still = rows[("planning.strategy", "state_unchanged")]
    assert still["count"] == 3 and "S1" in still["reasons"][0] and not still["acted"]
    assert rows[("action.strategy", "resample")]["after_visible_output"] == 1
    assert all(row["session"] == "family" for row in rows.values())
