"""Apply typed Action judgments at native event, request and mandatory gate boundaries."""

import asyncio
from dataclasses import dataclass
from uuid import uuid4

from raven.agent.loop.recovery import DraftGate
from raven.contracts.loop_hooks import AgentHook, HookDecision

from ...harness.action import (
    ActionDecision,
    ActionEvent,
    ActionInteraction,
    ActionResponse,
    ControlEvent,
    ControlReceipt,
    FailureEvent,
    InputEvent,
    OutcomeEvent,
    ProgressEvent,
    ProposalEvent,
    ProposedCall,
)
from ...harness.interaction import InteractionScope
from ...harness.preparation import StrategyPreparation
from ...harness.strategies import ActionStrategy
from ..interaction_tools import interaction_tool
from ..observe import plain
from ..strategy import SESSION, BoundStrategy, concrete


@dataclass
class PendingControl:
    receipt: ControlReceipt
    decision: ActionDecision
    context: object | None = None
    message_count: int = 0
    rollbacks: int = 0
    refused: int = 0


class BoundAction(BoundStrategy):
    """One session owner for supervision, model requests and native dispatch checks."""

    def __init__(
        self, config, task, path, package, recorder, *, infer=None, plan=None, peers=None, scope=None, host=None
    ):
        selected = []
        if config.events:
            selected.append("handle_event")
        if config.tool or config.requests:
            selected.append("handle_request")
        super().__init__(
            "action",
            ActionStrategy,
            config,
            task,
            path,
            package,
            recorder,
            optional=tuple(selected),
            infer=infer,
            plan=plan,
            peers=peers,
            host=host,
            inherited=("handle_event",),
        )
        if config.events and type(self.strategy).handle_event is ActionStrategy.handle_event:
            if not any(
                getattr(type(self.strategy), f"_handle_{kind}", None) is not getattr(ActionStrategy, f"_handle_{kind}")
                for kind in config.events
            ):
                raise TypeError("action strategy must implement handle_event or a selected protected handler")
        if not selected and type(self.strategy).prepare is StrategyPreparation.prepare:
            raise TypeError("action strategy requires preparation or a selected interaction")
        self.scope = scope or (
            lambda: InteractionScope(
                harness_id=str(path.parent),
                task_id=task.id,
                revision=package.name,
                session_key=SESSION.get(),
                turn_id=recorder.turn_id,
            )
        )
        if config.events and self.types["handle_event"] != ([ActionEvent], ActionDecision):
            raise TypeError("handle_event must accept ActionEvent and return ActionDecision")
        self.request_type, self.command_type = None, None
        if "handle_request" in selected:
            request, result = self.types["handle_request"]
            if not isinstance(request[0], type) or not issubclass(request[0], ActionInteraction):
                raise TypeError("handle_request requires ActionInteraction with a concrete command type")
            if not isinstance(result, type) or not issubclass(result, ActionResponse):
                raise TypeError("handle_request requires ActionResponse with a concrete reply type")
            self.request_type = request[0]
            self.command_type = concrete(request[0].model_fields["command"].annotation)
        self.plan, self.peers = plan, peers
        self.runtime = None
        self.pending = {}
        self.guidance = {}
        self.sinks = {}
        self.failed_checks = {}

    def bind(self, runtime):
        self.runtime = runtime

    def _key(self):
        scope = self.scope()
        return scope.session_key, scope.turn_id

    def _base(self, controls, *, can_guide=False):
        return {
            "scope": self.scope(),
            "event_id": uuid4().hex,
            "allowed_controls": controls,
            "can_guide": can_guide,
            "plan": self.plan() if self.plan else None,
        }

    def _capabilities(self):
        return self.peers.capabilities() if self.peers else None

    def _controls(self, context):
        values = ["continue", "finish"]
        if context.metadata.get("hook_rollbacks", 0) < self.runtime.loop._MAX_HOOK_ROLLBACKS:
            values.append("revise")
        return tuple(values)

    def _receipt(self, source_id, decision, status, reason=None, *, control_id=None):
        value = ControlReceipt(
            scope=self.scope(),
            control_id=control_id or uuid4().hex,
            source_id=source_id,
            control=decision.control,
            status=status,
            reason=reason if reason is not None else decision.reason or decision.feedback,
        )
        self.recorder.add("action.control", receipt=value)
        return value

    def _validate(self, decision, allowed, can_guide, source_id):
        if decision.control not in allowed or (decision.guidance is not None and not can_guide):
            self._receipt(source_id, decision, "unsupported", "effect is not supported at this boundary")
            raise ValueError("action returned an effect unsupported at this boundary")
        if decision.generation is not None and decision.generation.max_tokens is not None:
            budget = self.runtime.loop.harness.memory.token_budget() if self.runtime is not None else None
            if budget is None or decision.generation.max_tokens > budget.reserved_output:
                self._receipt(source_id, decision, "unsupported", "generation exceeds the reserved output allowance")
                raise ValueError("generation overrides exceed the reserved output allowance")

    async def handle_event(self, event):
        if event.kind not in self.config.events:
            return ActionDecision()
        return await self.call(
            "handle_event",
            event,
            source=event.kind,
            source_id=event.event_id,
            validate=lambda result: self._validate(result, event.allowed_controls, event.can_guide, event.event_id),
        )

    async def request(self, command, *, origin="agent"):
        if self.request_type is None:
            raise ValueError("this Action has no declared request operation")
        identifier = uuid4().hex
        controls = ("continue", "revise", "finish") if self.scope().turn_id is not None else ("continue",)
        request = self.request_type(
            scope=self.scope(),
            request_id=identifier,
            origin=origin,
            command=command,
            allowed_controls=controls,
        )
        result = await self.call(
            "handle_request",
            request,
            source=origin,
            source_id=identifier,
            validate=lambda value: self._validate(value.decision, controls, False, identifier),
        )
        receipt = None
        if result.decision.control != "continue":
            held = self.pending.setdefault(self._key(), [])
            if any(item.context is None for item in held):
                receipt = self._receipt(
                    identifier, result.decision, "rejected", "another control is queued for this boundary"
                )
            else:
                receipt = self._receipt(identifier, result.decision, "requested")
                held.append(PendingControl(receipt, result.decision))
        return {"reply": plain(result.reply), "control": plain(receipt)}

    def tool(self):
        if self.config.tool is None or self.command_type is None:
            raise ValueError("Action has no declared model request tool")
        return interaction_tool(self.config.tool, self.command_type, self.request)

    def model_guidance(self, sink):
        if self._key() in self.failed_checks:
            raise RuntimeError("a required Action check was interrupted before the model decision")
        self.sinks[self._key()] = sink
        return self.guidance.pop(self._key(), None)

    def _apply(self, decision, source_id, context, pending=None):
        if decision.guidance is not None:
            self.guidance[self._key()] = decision.guidance
        if decision.control == "continue":
            return HookDecision()
        receipt = pending.receipt if pending else self._receipt(source_id, decision, "requested")
        item = pending or PendingControl(receipt, decision)
        item.context = context
        item.message_count = len(context.messages or ())
        item.rollbacks = context.metadata.get("hook_rollbacks", 0)
        item.refused = context.metadata.get("rollbacks_refused", 0)
        if pending is None:
            self.pending.setdefault(self._key(), []).append(item)
        if decision.control == "revise":
            return HookDecision(
                rollback=True,
                rollback_inject=[{"role": "user", "content": decision.feedback}],
                rollback_overrides=decision.generation.model_dump(exclude_none=True) if decision.generation else None,
            )
        if decision.control == "finish":
            sink = self.sinks.get(self._key())
            if isinstance(sink, DraftGate):
                sink.discard()
            return HookDecision(short_circuit_result=decision.reply)
        raise ValueError("per-call rejection requires the dispatch gate")

    async def _settle(self, *, final=False, emitted_reply=None):
        remaining = []
        settled = []
        for item in self.pending.get(self._key(), ()):
            status, reason = None, None
            context = item.context
            if context is not None and item.decision.control == "revise":
                if context.metadata.get("hook_rollbacks", 0) > item.rollbacks:
                    status = "applied"
                elif context.metadata.get("rollbacks_refused", 0) > item.refused:
                    status, reason = "rejected", "native rollback budget refused the request"
            if context is not None and item.decision.control == "finish":
                if any(
                    row.get("role") == "assistant" and row.get("content") == item.decision.reply
                    for row in (context.messages or ())[item.message_count :]
                ):
                    status = "applied"
                if getattr(context, "turn_request", None) is not None and emitted_reply == item.decision.reply:
                    status = "applied"
            if status is None and final:
                status, reason = "rejected", "the turn ended without evidence of control application"
            if status is None:
                remaining.append(item)
            else:
                receipt = self._receipt(
                    item.receipt.source_id,
                    item.decision,
                    status,
                    reason,
                    control_id=item.receipt.control_id,
                )
                settled.append(receipt)
        self.pending[self._key()] = remaining
        for receipt in settled:
            await self.handle_event(ControlEvent(**self._base(("continue",)), receipt=receipt))

    async def finish(self, *, emitted_reply=None):
        try:
            await self._settle(final=True, emitted_reply=emitted_reply)
        except Exception as exc:
            self.recorder.add("action.error", operation="control_observation", error=str(exc))
        finally:
            self.pending.pop(self._key(), None)
            self.guidance.pop(self._key(), None)
            self.sinks.pop(self._key(), None)
            self.failed_checks.pop(self._key(), None)

    async def _guard(self, context, operation):
        try:
            await self._settle()
            return await operation()
        except asyncio.CancelledError:
            self.failed_checks[self._key()] = True
            self.recorder.add("action.error", operation="event_consumer", error="required Action check was cancelled")
            raise
        except Exception as exc:
            self.recorder.add("action.error", operation="event_consumer", error=f"{type(exc).__name__}: {exc}")
            return self._apply(
                ActionDecision(
                    control="finish",
                    reply="Execution stopped because the required action check could not be completed.",
                ),
                "handler_failure",
                context,
            )

    @staticmethod
    def _calls(response):
        return tuple(
            ProposedCall(name=call.name, arguments=plain(call.arguments), call_id=call.id)
            for call in getattr(response, "tool_calls", ()) or ()
        )

    def hook(self):
        owner = self

        class ActionHook(AgentHook):
            name = "curator-action"
            rolls_back_iterations = True

            async def before_user_inbound(self, context):
                async def run():
                    event = InputEvent(**owner._base(("continue", "finish")), text=context.inbound_content or "")
                    return owner._apply(await owner.handle_event(event), event.event_id, context)

                return await owner._guard(context, run)

            async def before_iteration(self, context):
                async def run():
                    event = ProgressEvent(
                        **owner._base(("continue", "finish"), can_guide=True),
                        messages=plain(context.messages or []),
                        offered_tools=plain(context.tools or []),
                        previous_capabilities=owner._capabilities(),
                        iteration=context.iteration,
                    )
                    result = await owner.handle_event(event)
                    return owner._apply(result, event.event_id, context)

                return await owner._guard(context, run)

            async def before_execute_tools(self, context):
                async def run():
                    event = ProposalEvent(
                        **owner._base(owner._controls(context)),
                        stage="batch",
                        calls=owner._calls(context.response),
                        text=getattr(context.response, "content", None),
                        capabilities=owner._capabilities(),
                    )
                    return owner._apply(await owner.handle_event(event), event.event_id, context)

                return await owner._guard(context, run)

            async def after_iteration(self, context):
                async def run():
                    for pending in owner.pending.get(owner._key(), ()):
                        if pending.context is None:
                            owner._validate(
                                pending.decision, owner._controls(context), False, pending.receipt.source_id
                            )
                            return owner._apply(pending.decision, pending.receipt.source_id, context, pending)
                    calls = owner._calls(context.response)
                    if calls:
                        event = OutcomeEvent(
                            **owner._base(owner._controls(context), can_guide=True),
                            messages=plain(context.messages or []),
                            proposed_calls=calls,
                            capabilities=owner._capabilities(),
                        )
                    else:
                        event = ProposalEvent(
                            **owner._base(owner._controls(context)),
                            stage="reply",
                            text=getattr(context.response, "content", None),
                            capabilities=owner._capabilities(),
                        )
                    return owner._apply(await owner.handle_event(event), event.event_id, context)

                return await owner._guard(context, run)

            async def terminal_answerless(self, context):
                async def run():
                    event = FailureEvent(
                        **owner._base(("continue", "finish")),
                        reason="The native execution ended without a usable final answer.",
                        terminal=True,
                        messages=plain(context.messages or []),
                    )
                    return owner._apply(await owner.handle_event(event), event.event_id, context)

                return await owner._guard(context, run)

        return ActionHook()

    def gate(self):
        owner = self

        class ActionGate:
            name = "curator-action"

            async def adjudicate(self, name, params, *, session_workdir):
                event = ProposalEvent(
                    **owner._base(("continue", "reject")),
                    stage="dispatch",
                    calls=(ProposedCall(name=name, arguments=plain(params)),),
                    capabilities=owner._capabilities(),
                )
                result = await owner.handle_event(event)
                if result.control == "continue":
                    return None
                receipt = owner._receipt(event.event_id, result, "applied")
                try:
                    await owner.handle_event(ControlEvent(**owner._base(("continue",)), receipt=receipt))
                except Exception as exc:
                    owner.recorder.add("action.error", operation="control_observation", error=str(exc))
                return f"Action refused this call [{receipt.control_id}]: {result.feedback}"

        return ActionGate()


def build_gate(context):
    """Resolve the already bound owner when Raven constructs its native gate contribution."""
    from ..bind import _ASSEMBLY

    return _ASSEMBLY.get()[3]["action_gate"]
