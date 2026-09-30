"""Planning initialization, committed projections and concrete interaction results."""

from pydantic import BaseModel, ConfigDict

from .interaction import InteractionScope


class PlanningInitialization(BaseModel):
    """Establish one session owner from its mission and restored checkpoint.

    Task text is the worker's business objective, not Curator construction
    instructions. Current customer input arrives through runtime observations.
    Initialization must work during candidate validation without inference.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    scope: InteractionScope
    task: str
    restored: bool


class PlanningProjection[ViewT](BaseModel):
    """A detached, reconstructible view and its current model-facing guidance.

    Partial plans and concrete empty views are valid. Candidate alternatives
    remain distinguishable from the active plan. Guidance is replaced on the
    next model call; None withdraws it. External facts survive replanning.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    view: ViewT
    guidance: str | None = None


class PlanningResult[ViewT, ReplyT](BaseModel):
    """Separate a business answer from the resulting plan projection.

    A normal refusal may record a blocker. Acceptance/refusal belongs to ReplyT;
    invalid requests and dependency failures remain exceptions. Queries return
    the existing projection unchanged. Successful commands publish a projection
    after checkpointing. Tool and peer callers receive reply; the host records
    the complete result as evidence.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    reply: ReplyT
    projection: PlanningProjection[ViewT]
