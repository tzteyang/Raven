"""Exercise a candidate's synchronous translations and its capability selection with synthetic host input before it
is installed.

The host refuses a planning observation translation that changes state, but only when the translation runs; a
candidate whose `_observe` keeps bookkeeping in its state passes assembly and then stops the worker on its first
turn. The same holds for a capability selection that names a skill the host does not list as named (a provenance
string given as the skill's source, say) or a tool it does not offer. This probe runs inside the validation copy
(`worker.check(candidate, probe=...)`): it drives every declared observation phase once with a synthetic observation
built from the task, and the capability selection once on the installed catalogue and the runtime's tools, so such a
candidate fails validation and reaches repair instead of the worker. It leaves no state behind and calls no model
beyond what the candidate's own selection calls: a translation that returns a command runs that command through the
candidate's own `interact`, as the runtime would, on the copied state.
"""

from experimental.curator.harness.action import FailureEvent, InputEvent, OutcomeEvent, ProgressEvent, ProposalEvent
from experimental.curator.raven_adapter.memory.contracts import MemoryObservation
from experimental.curator.raven_adapter.planning.contracts import PlanningObservation

PROBE = "validation.translation"
ALL_CONTROLS = ("continue", "reject", "revise", "finish")


async def exercise_translations(bound) -> None:
    task = getattr(getattr(bound, "baseline", None), "task", None)
    text = getattr(task, "text", "") or "probe"
    await _planning(bound, text)
    await _memory(bound, text)
    await _action(bound, text)
    await _capability(bound, text)


def _event(kind, scope, text):
    common = {
        "scope": scope,
        "event_id": f"validation-probe-{kind}",
        "allowed_controls": ALL_CONTROLS,
        "can_guide": True,
    }
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
        event = _event(kind, action.scope(), text)
        if event is None:
            bound.recorder.add(PROBE, strategy="action", event=kind, status="not_synthesised")
            continue
        await action.handle_event(event)
        bound.recorder.add(PROBE, strategy="action", event=kind, status="passed")


async def _memory(bound, text) -> None:
    """Memory's after-iteration observation translation, without the interaction it may propose: the copied
    session has no initialized context for one, and the rule under test is the translation's."""
    memory = (getattr(bound, "strategies", None) or {}).get("memory")
    if memory is None or memory.observe is None:
        bound.recorder.add(PROBE, strategy="memory", status="not_bound" if memory is None else "no_observation")
        return
    await memory.prepare()
    observation = MemoryObservation(
        scope=memory.scope(),
        event_id="validation-probe-after_iteration",
        iteration=0,
        messages=[{"role": "user", "content": text}, {"role": "assistant", "content": ""}],
        proposal={"content": "", "tool_calls": []},
    )
    memory.translate("observe", memory.observe, observation, output=memory.command_type | None)
    bound.recorder.add(PROBE, strategy="memory", phase="after_iteration", status="passed")


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


async def _capability(bound, text) -> None:
    """The capability strategy's selection once, as a turn's first step would ask it; a native selection is not
    candidate code and is not exercised."""
    capability = getattr(bound, "capability", None)
    if capability is None or capability.config is None:
        bound.recorder.add(PROBE, strategy="capability", status="not_bound" if capability is None else "native")
        return
    await capability.prepare()
    offered = capability.runtime.loop.tools.get_definitions()
    await capability.select(capability.selection_request(offered, [{"role": "user", "content": text}]))
    bound.recorder.add(PROBE, strategy="capability", operation="select", status="passed")
