"""Raven bindings and trusted observation inputs for generated Planning owners."""

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from ...harness.interaction import InteractionScope, InteractionTool
from ..targets import EntryPoint

TARGET = "planning.strategy"


class PlanReader(Protocol):
    """Read this session's latest committed plan without entering its owner.

    Factories may declare the keyword-only plan dependency. The returned view
    is detached JSON, or None before this session is initialized or when no
    Planning is bound. A view describes processed evidence, not a model proposal
    currently being judged. Planning may publish partial and empty views.
    """

    def __call__(self) -> JsonValue: ...


type PlanningPhase = Literal["before_model", "after_iteration"]


class PlanningObservation(BaseModel):
    """Host input before capability selection or actual completed-iteration evidence.

    messages is this turn's current transcript, preserving tool-data boundaries.
    response is a proposal, not proof of execution. tools is the offered catalogue
    before selection, not the current effective capabilities or a permission grant.
    Stable event identity permits repeated observations to be recognized.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    scope: InteractionScope
    event_id: str
    phase: PlanningPhase
    iteration: int
    messages: list[dict[str, JsonValue]]
    response: dict[str, JsonValue] | None = None
    tools: list[dict[str, JsonValue]] = Field(default_factory=list)


class PlanningBinding(BaseModel):
    """Bind one session owner and independently select its host interaction paths.

    Tools expose business arguments and query/command mode; scope and provenance
    are host supplied. Observation translation is optional and synchronous. All
    state transitions and business judgments belong to initialize/interact.
    """

    model_config = ConfigDict(extra="forbid")

    factory: EntryPoint = Field(
        description="create(state: dict[str, JsonValue]) returns an inert instance explicitly inheriting "
        "PlanningStrategy[ViewT, CommandT, ReplyT] with concrete annotations. One checkpoint belongs to each "
        "session across turns and revisions. initialize(PlanningInitialization) restores progress and returns "
        "PlanningProjection[ViewT]; interact(InteractionRequest[CommandT]) returns PlanningResult[ViewT, ReplyT]. "
        "Factories may explicitly migrate state. Optional keyword-only peers and infer dependencies provide "
        "owner-scoped collaboration and bounded single-step inference; host prepares reusable procedures. "
        "An optional keyword-only plan reads this session's committed view (None before initialization), "
        "never an operation's uncommitted state. Projection subclasses may retain the same ViewT and public fields."
    )
    tool: InteractionTool | None = Field(
        default=None, description="Publish an Agent-facing planning.interact tool through Capability.register."
    )
    requests: bool = Field(default=False, description="Allow peer interactions independently of tool publication.")
    context: bool = Field(
        default=False, description="Deliver the committed projection's guidance before model calls; None withdraws it."
    )
    observe: tuple[PlanningPhase, ...] = Field(
        default=(),
        description="Select host phases for synchronous _observe(view: ViewT, observation: "
        "PlanningObservation) -> CommandT | None. The translation cannot change state. A returned command "
        "enters interact with observation provenance. before_model runs before Capability selection.",
    )
