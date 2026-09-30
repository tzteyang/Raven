"""Candidate resource registration and selection from an actually active catalogue."""

from abc import abstractmethod
from typing import Protocol

from ..preparation import PreparationRequest, StrategyPreparation
from ..resources import (
    CapabilityContribution,
    CapabilitySelection,
    RegistrationReceipt,
    SelectionRequest,
    SkillContribution,
    ToolContribution,
)


class CapabilityStrategy(StrategyPreparation, Protocol):
    """Own capability admission policy and task-directed runtime selection.

    A factory may receive the host's keyword-only registrar dependency and
    delegate registration to it. Registration is candidate-scoped; selection
    state is per session. Tools from other strategies use the same register
    operation, while their handlers and business state stay with their owners.

    Existing packages, newly authored skills and tool implementations all need
    explicit admission. Package bytes, interpreted metadata and executable
    dependencies are separate concerns. Candidate host services can configure
    supported native mechanisms; listing an unavailable child or connector
    cannot create that capability or enlarge its execution authority.
    """

    def prepare(self, request: PreparationRequest) -> None:
        """Submit authored resources before the candidate registrar closes.

        Override this operation for another preparation algorithm, or override
        the protected tool/skill producers below. They return inert proposals;
        every accepted resource passes register. A refusal fails this default
        preparation rather than silently publishing an incomplete candidate.
        """
        for contribution in (*self._prepare_tools(request), *self._prepare_skills(request)):
            receipt = self.register(contribution)
            if receipt.status == "rejected":
                raise ValueError(f"capability preparation refused {contribution.name}: {receipt.reason}")

    def _prepare_tools(self, request: PreparationRequest) -> tuple[ToolContribution, ...]:
        """Optionally produce this implementation's tools; the default adds none."""
        return ()

    def _prepare_skills(self, request: PreparationRequest) -> tuple[SkillContribution, ...]:
        """Optionally adopt or author complete skills using inspected inputs/assets.

        The host copies pinned packages, including binary and nested assets.
        This producer chooses the content; listing an asset alone never
        activates it. The default adds no managed skills.
        """
        return ()

    @abstractmethod
    def register(self, contribution: CapabilityContribution) -> RegistrationReceipt:
        """Accept or refuse one inert resource contribution.

        Use the supplied registrar for an accepted contribution. A staged
        receipt is not activation or permission. Exact repeats are idempotent;
        conflicting identity or a closed candidate is refused. Do not execute
        tools, start services or alter the session's retained selection state.
        """
        ...

    @abstractmethod
    async def select(self, request: SelectionRequest) -> CapabilitySelection:
        """Choose tools and skill delivery using actual runtime information.

        None delegates a native choice; an empty tuple selects nothing.
        Selection must name available resources and never installs resources or
        grants execution permission. The host publishes the effective view
        after applying remaining native visibility and protection rules.
        """
        ...
