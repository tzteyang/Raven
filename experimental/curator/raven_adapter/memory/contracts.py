"""Memory bindings connect typed information commands and explicit context lifetimes."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from ...harness.interaction import InteractionScope, InteractionTool
from ..strategy import TaskBinding

TARGET = "memory.strategy"


class MemoryObservation(BaseModel):
    """Actual completed-iteration evidence, supplied by the host rather than tool arguments."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scope: InteractionScope
    event_id: str
    iteration: int
    messages: list[dict[str, JsonValue]]
    proposal: JsonValue


class MemoryInput(BaseModel):
    """Actual inbound text before context initialization; never a fabricated InitialContext."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scope: InteractionScope
    text: str


class MemoryArchive(BaseModel):
    """Native sent-phase evidence for record annotation, without claiming delivery acknowledgement."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scope: InteractionScope
    reply: str | None
    messages: list[dict[str, JsonValue]]


class MemoryBinding(TaskBinding):
    """Select information interaction and supported pressure paths.

    The factory receives session state and may declare keyword-only shared for
    task-wide JSON knowledge, infer for bounded inference, plan for a read-only
    plan, or peers for declared cross-strategy operations. Source-aware context
    assembly is required by default; unsupported baselines fail explicitly.
    """

    tool: InteractionTool | None = None
    requests: bool = Field(
        default=False, description="Enable typed peer information requests without a model-facing tool."
    )
    observe: bool = Field(
        default=False,
        description="Enable the strategy's synchronous _observe(observation: MemoryObservation) -> CommandT | None. "
        "Select actual host evidence to pass to interact with observation provenance; "
        "None means this observation needs no information operation.",
    )
    intake: bool = Field(
        default=False,
        description="Enable async _intake(MemoryInput) -> str | None on the same strategy owner, "
        "before initialize. Return model-facing derived text or None to preserve input. "
        "The original input remains in execution evidence; early replies belong to Action.",
    )
    archive: bool = Field(
        default=False,
        description="Enable async _archive(MemoryArchive) -> dict[str, JsonValue] | None on the same owner. "
        "Its result annotates the native turn record at the reachable sent phase; it does not rewrite a reply.",
    )
    compact: tuple[Literal["projection", "proactive", "overflow"], ...] = Field(
        default=(),
        description="Pressure paths explicitly implemented by compact. Projection is checked "
        "at each model call; proactive/overflow are native mid-turn window paths. "
        "Other native shrink paths remain delegated.",
    )
    require_sources: bool = Field(
        default=True,
        description="Require a source-aware ContextEngine so initialize can organize baseline content. "
        "False explicitly accepts an opaque protected baseline; it does not grant authority to rewrite that baseline.",
    )
