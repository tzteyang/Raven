"""Session planning semantics authored by Curator and connected through host bindings."""

from abc import abstractmethod
from typing import Protocol

from ..interaction import InteractionRequest
from ..planning import PlanningInitialization, PlanningProjection, PlanningResult
from ..preparation import StrategyPreparation


class PlanningStrategy[ViewT, CommandT, ReplyT](StrategyPreparation, Protocol):
    """Own task organization, domain interactions and the published plan.

    Curator chooses concrete views, commands, replies and transition rules.
    Checklists, partial plans and dependency graphs share this lifecycle.
    Factories bind explicit resources and checkpoint state; private helpers
    and algorithms remain implementation choices.

    prepare may publish reusable procedures and child-customization requirements.
    Runtime interactions manage this session's progress. Capability admits tools
    and Skills, Memory assembles model input, and Action owns loop control.
    A procedure or model-reported completion is not proof of external success.
    """

    @abstractmethod
    async def initialize(self, initial: PlanningInitialization) -> PlanningProjection[ViewT]:
        """Create or restore this session and return its current projection.

        Preserve restored progress and reconstruct the projection for every new
        owner instance. Partial and concrete empty plans are valid. Initialization
        must work without a live model or ready peers. Later requirements enter
        interact; no private template-method sequence is prescribed.
        """
        ...

    @abstractmethod
    async def interact(self, request: InteractionRequest[CommandT]) -> PlanningResult[ViewT, ReplyT]:
        """Handle a concrete planning request with host identity and provenance.

        Queries cannot change retained state or the published projection. Commands
        may revise a plan, record evidence, decline a proposal while recording a
        blocker, or legitimately do nothing. Business outcomes belong to ReplyT;
        invalid input and failed dependencies remain errors. Deduplicate actual
        evidence and distinguish agent reports from host observations.

        Return a projection reconstructible from retained state. Preserve executed
        facts when changing future work. Use peers for cross-owner requests; a
        local failure cannot roll back another owner's successful operation.
        """
        ...
