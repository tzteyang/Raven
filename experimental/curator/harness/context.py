"""Context sources, initialization inputs and bounded model-call projections.

Source identity and protection come from the host's actual assembly. Curator
chooses the organization of editable content; no fixed profile or private
template-method sequence is imposed on a Memory implementation.
"""

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from .interaction import InteractionScope
from .resources import EffectiveCapabilities


class ContextSource(BaseModel):
    """One sourced contribution, independent of its baseline's text formatting."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    kind: Literal["identity", "profile", "memory", "skills", "guidance", "other"]
    role: Literal["system", "developer", "user"] = "system"
    text: str
    required: bool = True
    stable: bool = False


class ContextSourceProvider(Protocol):
    """An optional face for a custom ContextEngine after its actual assemble call.

    Return the contributions used by that session's latest assembly. Unknown
    or unavailable sources must not be invented by inspecting text headings.
    """

    def context_sources(self, session_key: str) -> tuple[ContextSource, ...]: ...


class InitialContext(BaseModel):
    """Initialize or resume context organization once per active session owner.

    messages and history are detached host observations. Sources retain their
    ownership and protection. Initialization may establish a layout, policies
    and working state; its concrete return is supplied to every compose call.
    Restored state is progress to preserve, not a request to clear it.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    scope: InteractionScope
    task: str
    sources: tuple[ContextSource, ...]
    messages: list[dict[str, JsonValue]]
    history: list[dict[str, JsonValue]]
    restored: bool

    @model_validator(mode="after")
    def unique_sources(self):
        names = [source.name for source in self.sources]
        if len(names) != len(set(names)):
            raise ValueError("context source identities must be unique")
        return self


class ContextRequest(BaseModel):
    """Project the current model input, using live state and effective capabilities.

    initialization is the validated initialization result, not a frozen prompt.
    Current source content, messages and capabilities may differ on every call.
    Required message mappings and required source text survive unchanged.
    Projection does not rewrite the session archive or committed knowledge.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    scope: InteractionScope
    messages: list[dict[str, JsonValue]]
    budget: int = Field(ge=0)
    required: tuple[int, ...]
    turn_start: int = Field(ge=0)
    sources: tuple[ContextSource, ...]
    history: list[dict[str, JsonValue]]
    initialization: JsonValue
    capabilities: EffectiveCapabilities
    plan: JsonValue = None

    @model_validator(mode="after")
    def valid_indices(self):
        names = [source.name for source in self.sources]
        if len(names) != len(set(names)):
            raise ValueError("context source identities must be unique")
        if self.turn_start >= len(self.messages):
            raise ValueError("turn_start must identify a current message")
        if tuple(sorted(set(self.required))) != self.required or any(
            i < 0 or i >= len(self.messages) for i in self.required
        ):
            raise ValueError("required indices must be unique, ordered and within messages")
        return self


class ContextView(BaseModel):
    """The actual model-call message projection, checked by the host."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    messages: list[dict[str, JsonValue]]


class CompactionRequest(ContextRequest):
    """Reduce a projection at an explicitly supported pressure point.

    Native window pressure can precede the first capability selection. In that
    case capabilities is None; otherwise it is the latest actually delivered
    model-call snapshot, not a fabricated view of a future selection.
    """

    capabilities: EffectiveCapabilities | None = None
    pressure: Literal["projection", "proactive", "overflow"]
