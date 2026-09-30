"""Candidate preparation, before native construction and session initialization."""

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from .artifact import ArtifactPath
from .state import Task


class PreparationRequest(BaseModel):
    """Detached candidate inputs, never an active turn or a mutable runtime.

    Assets contain the candidate's complete text package. Material roots name
    inspected host inputs; adopting a package still requires its digest and
    resource admission. Preparation can be repeated during checks, activation
    and restart. It must not reset session progress or perform external work.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    harness_id: str
    revision: str
    task: Task
    assets: dict[ArtifactPath, str] = Field(default_factory=dict)
    material_roots: tuple[str, ...] = ()


class StrategyPreparation(Protocol):
    """Optional candidate setup implemented by the same generated strategy.

    The host calls prepare once per assembly on a candidate owner, before
    constructing native components. Session owners are distinct instances.
    Only explicit resource/host preparation services retain its effects;
    private attributes and session checkpoint changes are not a handoff.
    Factories stay inert. Runtime interaction cannot reopen preparation.
    """

    def prepare(self, request: PreparationRequest) -> None:
        """Prepare this revision through supplied, candidate-scoped services.

        The default preserves the native baseline. Override when this strategy
        installs resources or changes native setup. This synchronous phase
        consumes already authored code and assets; live connections and their
        asynchronous lifecycle remain host-owned.
        """
