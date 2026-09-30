"""Action rules for host events and agent requests, separate from native scheduling."""

from typing import Protocol

from ..action import (
    ActionDecision,
    ActionEvent,
    ActionInteraction,
    ActionResponse,
    ControlEvent,
    FailureEvent,
    InputEvent,
    OutcomeEvent,
    ProgressEvent,
    ProposalEvent,
)
from ..preparation import StrategyPreparation


class ActionStrategy[CommandT, ReplyT](StrategyPreparation, Protocol):
    """Own behavior judgments and explicit interaction semantics.

    Host events and agent requests have different provenance and response
    obligations. Both can propose controls, but only within the allowance
    supplied by their actual consumer. The host reports application separately.
    Cross-strategy changes use their owners' public operations; this strategy
    never owns a second plan, memory store or tool executor.

    Translate a business constraint into an event with enough real evidence
    and a consumer capable of applying the intended effect. Model guidance
    belongs in context; mandatory execution conditions require host checks.
    Candidate prepare selects native generation/execution policies, while
    these handlers decide within the active turn and its existing grants.

    A factory may accept the host's infer dependency for one typed semantic
    judgment when the evidence needs interpretation. The strategy owns its
    prompt, input selection and result-to-control mapping. It shares the
    attempt with sequential peer calls and cannot create a judging agent loop.
    """

    async def handle_event(self, event: ActionEvent) -> ActionDecision:
        """Handle an explicitly selected observation or execution event.

        Distinguish unexecuted proposals, real outcomes, failure and control
        receipts. Missing evidence is unknown, not success. Guidance has a
        model-input consumer; diagnostic reasons do not implicitly become
        correction messages. An applied receipt does not undo earlier effects.
        """
        return await {
            "input": self._handle_input,
            "progress": self._handle_progress,
            "proposal": self._handle_proposal,
            "outcome": self._handle_outcome,
            "failure": self._handle_failure,
            "control": self._handle_control,
        }[event.kind](event)

    async def _handle_input(self, event: InputEvent) -> ActionDecision:
        """Optional early-input judgment; the default continues native intake."""
        return ActionDecision()

    async def _handle_progress(self, event: ProgressEvent) -> ActionDecision:
        """Optional pre-decision judgment; the default requests no change."""
        return ActionDecision()

    async def _handle_proposal(self, event: ProposalEvent) -> ActionDecision:
        """Optional proposal judgment shared by batch, dispatch and reply stages."""
        return ActionDecision()

    async def _handle_outcome(self, event: OutcomeEvent) -> ActionDecision:
        """Optional actual-outcome handling; proposed calls are not execution receipts."""
        return ActionDecision()

    async def _handle_failure(self, event: FailureEvent) -> ActionDecision:
        """Optional failure handling within native recovery ordering and limits."""
        return ActionDecision()

    async def _handle_control(self, event: ControlEvent) -> ActionDecision:
        """Optional application-receipt handling; the default does not schedule controls."""
        return ActionDecision()

    async def handle_request(self, request: ActionInteraction[CommandT]) -> ActionResponse[ReplyT]:
        """Respond to a typed agent request using the same rules as supervision.

        A tool exposes only the command, never host identity or control grants.
        Its domain reply is distinct from the host receipt. Voluntary requests
        do not replace mandatory pre-dispatch checks. Enabled bindings require
        an implementation; an unselected entry is not an empty success.
        """
        raise NotImplementedError("action request handling is not provided")
