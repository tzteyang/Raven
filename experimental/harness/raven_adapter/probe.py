"""Exercise declared strategy operations and the actual Memory input path on copied state.

The probe assembles native context for a synthetic task message, initializes Memory,
checks observation translations, Planning interactions, Action events and Capability
selection, then uses ModelInput.prepare to run the same projection checks as a real
model call. It does not request a worker answer; strategy inference may still run.
Coverage is recorded per operation and does not establish full business correctness.
"""

from uuid import uuid4

from experimental.harness.contract.action import FailureEvent, InputEvent, OutcomeEvent, ProgressEvent, ProposalEvent
from experimental.harness.raven_adapter.memory.contracts import MemoryObservation
from experimental.harness.raven_adapter.model_input import ModelInput
from experimental.harness.raven_adapter.planning.contracts import PlanningObservation
from experimental.harness.raven_adapter.strategy import SESSION
from raven.contracts.context import TurnContext
from raven.contracts.harness import ActionRequest

PROBE = "validation.translation"
ALL_CONTROLS = ("continue", "reject", "revise", "finish")


async def exercise_translations(bound) -> None:
    task = getattr(getattr(bound, "baseline", None), "task", None)
    text = getattr(task, "text", "") or "probe"
    turn_id = f"validation:{uuid4().hex}"
    token = SESSION.set(turn_id)
    previous = bound.recorder.turn_id
    bound.recorder.turn_id = turn_id
    inference = getattr(bound, "inference", None)
    try:
        if inference is not None:
            inference.observe_window(bound.runtime.loop.context_window_tokens)
        await _planning(bound, text)
        frame = await _memory(bound, text)
        await _action(bound, text)
        tools = await _capability(bound, text, messages=frame.messages if frame is not None else None)
        if frame is not None:
            await ModelInput(None, bound.capability, bound.context_sources, bound.strategies["memory"]).prepare(
                ActionRequest(
                    provider=bound.runtime.loop.provider,
                    messages=frame.messages,
                    tools=tools,
                    model=bound.runtime.loop.model,
                    fallback_models=[],
                    stream_call=None,
                )
            )
            bound.recorder.add(PROBE, strategy="memory", operation="compose", status="passed")
    finally:
        if inference is not None:
            inference.release(turn_id)
        bound.recorder.turn_id = previous
        SESSION.reset(token)


def _event(kind, action, text):
    common = {**action.envelope(ALL_CONTROLS, can_guide=True), "event_id": f"validation-probe-{kind}"}
    messages = [{"role": "user", "content": text}]
    if kind == "input":
        return InputEvent(**common, text=text)
    if kind == "progress":
        return ProgressEvent(**common, messages=messages, offered_tools=[], iteration=0)
    if kind == "proposal":
        return ProposalEvent(**common, stage="reply", text=text)
    if kind == "outcome":
        return OutcomeEvent(**common, messages=messages, proposed_calls=())
    if kind == "failure":
        return FailureEvent(**common, reason="validation probe", terminal=False, messages=messages)
    return None


async def _action(bound, text) -> None:
    """Each declared Action event once, with every control allowed so only a failing handler fails; a control
    receipt needs a real applied control and is not synthesised."""
    action = (getattr(bound, "strategies", None) or {}).get("action")
    if action is None:
        bound.recorder.add(PROBE, strategy="action", status="not_bound")
        return
    await action.prepare()
    for kind in action.config.events:
        event = _event(kind, action, text)
        if event is None:
            bound.recorder.add(PROBE, strategy="action", event=kind, status="not_synthesised")
            continue
        await action.handle_event(event)
        bound.recorder.add(PROBE, strategy="action", event=kind, status="passed")


async def _memory(bound, text):
    """Initialize Memory from native context before checking its observation translation and final projection."""
    memory = (getattr(bound, "strategies", None) or {}).get("memory")
    if memory is None:
        bound.recorder.add(PROBE, strategy="memory", status="not_bound")
        return
    session = SESSION.get()
    await bound.context_sources.assemble(
        session,
        [],
        bound.runtime.loop.harness.memory.token_budget(),
        turn=TurnContext(current_message=text, channel="validation", chat_id="strategies"),
    )
    frame = bound.context_sources.frame(session)
    await memory.initialize_context(session, frame)
    bound.recorder.add(PROBE, strategy="memory", operation="initialize", status="passed")
    if memory.observe is None:
        bound.recorder.add(PROBE, strategy="memory", operation="observe", status="not_selected")
        return frame
    observation = MemoryObservation(
        scope=memory.scope(),
        event_id="validation-probe-after_iteration",
        iteration=0,
        messages=[*frame.messages, {"role": "assistant", "content": ""}],
        proposal={"content": "", "tool_calls": []},
    )
    memory.translate("observe", memory.observe, observation, output=memory.command_type | None)
    bound.recorder.add(PROBE, strategy="memory", phase="after_iteration", status="passed")
    return frame


async def _planning(bound, text) -> None:
    planning = bound.planning
    if planning is None:
        bound.recorder.add(PROBE, strategy="planning", status="not_bound")
        return
    await planning.prepare()
    for phase in planning.config.observe:
        observation = PlanningObservation(
            scope=planning.scope(),
            event_id=f"validation-probe-{phase}",
            phase=phase,
            iteration=0,
            messages=[{"role": "user", "content": text}],
            response=None if phase == "before_model" else {"content": "", "tool_calls": []},
            tools=[],
        )
        await planning.observe(observation)
        bound.recorder.add(PROBE, strategy="planning", phase=phase, status="passed")


async def _capability(bound, text, *, messages=None):
    """The capability strategy's selection once, as a turn's first step would ask it; a native selection is not
    candidate code and is not exercised."""
    capability = getattr(bound, "capability", None)
    if capability is None:
        bound.recorder.add(PROBE, strategy="capability", status="not_bound")
        return []
    offered = capability.runtime.loop.tools.get_definitions()
    if capability.config is None:
        bound.recorder.add(PROBE, strategy="capability", status="native")
        return offered
    await capability.prepare()
    selected = await capability.select(
        capability.selection_request(offered, messages or [{"role": "user", "content": text}])
    )
    bound.recorder.add(PROBE, strategy="capability", operation="select", status="passed")
    return offered if selected.tools is None else [row for row in offered if row["function"]["name"] in selected.tools]
