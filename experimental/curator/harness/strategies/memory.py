"""Initialization, information interaction and projection owned by one Memory strategy."""

from abc import abstractmethod
from typing import Protocol

from ..context import CompactionRequest, ContextRequest, ContextView, InitialContext
from ..interaction import InteractionRequest
from ..preparation import StrategyPreparation


class MemoryStrategy[InitializationT, CommandT, ReplyT](StrategyPreparation, Protocol):
    """Own context organization and the meaning of information operations.

    A factory binds explicit resources and owned state. initialize establishes
    or restores organization from actual baseline sources; compose uses current
    sources, state and effective capabilities on every model call. Concrete
    interaction commands define retrieval, recording, correction or other
    domain operations without prescribing a fixed CRUD vocabulary.

    Candidate prepare selects durable profile/storage dependencies; initialize
    organizes one session, and compose projects its current inputs. Supplied
    expert text is material, not proof that a procedure or control was applied.
    Use Planning for plan mutations and Action for execution judgments.
    """

    @abstractmethod
    async def initialize(self, initial: InitialContext) -> InitializationT:
        """Establish or resume this session's initial context organization.

        Preserve restored progress and distinguish shared task knowledge from
        session working state. The concrete result is supplied to compose; it
        may describe a layout or policy but must not freeze dynamic inputs.
        No private template-method sequence or baseline text layout is required.
        """
        ...

    async def interact(self, request: InteractionRequest[CommandT]) -> ReplyT:
        """Handle a typed information request using its host-supplied provenance.

        Agent claims and host execution observations remain distinct. Return an
        actual outcome, including a valid no-op or refusal; dependency failures
        remain errors. Repeated evidence must not accidentally duplicate facts.
        The host selects this operation explicitly for tools or observations.
        Query mode forbids writes to session and shared information, including
        through peers. A nested command cannot relax an upstream query boundary.
        """
        raise NotImplementedError("memory interaction is not provided")

    @abstractmethod
    async def compose(self, request: ContextRequest) -> ContextView:
        """Organize the actual model-call input without rewriting retained state.

        Use the current source content and effective capability view. Required
        messages and source text survive unchanged. The result is a detached
        projection, not the session archive or a claim that a resource was used.
        """
        ...

    async def compact(self, request: CompactionRequest) -> ContextView:
        """Reduce a projection at a declared pressure point.

        Preserve required content and tool/result pairing. A projection that
        cannot fit must fail explicitly. Image/provider recovery and loop
        retries remain host responsibilities. Persisting a summary requires an
        explicit information operation rather than hidden writes here.
        """
        raise NotImplementedError("memory compaction is not provided")
