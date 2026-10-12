"""Shared identities, typed interaction envelopes and model-facing declarations.

The host supplies scope and provenance. A tool exposes only its concrete command
schema; it never accepts a caller-selected session, revision or evidence source.
These contracts describe data, not a scheduler or a service locator.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

type InteractionMode = Literal["query", "command"]


class InteractionScope(BaseModel):
    """Identify the actual consumer of a strategy operation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    harness_id: str = Field(min_length=1)
    task_id: str | None = None
    revision: str = Field(min_length=1)
    session_key: str | None = None
    turn_id: str | None = None


class InteractionRequest[CommandT](BaseModel):
    """A command plus host provenance, constructed after tool argument validation.

    Repeated deliveries retain their request identity when the caller has one.
    A model's claim is still a claim when this envelope's origin is 'agent'.
    'strategy' identifies an explicit peer operation, not execution evidence.
    Query mode forbids retained-state changes and propagates through peers;
    command mode permits an operation to decide whether a change is warranted.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    scope: InteractionScope
    request_id: str = Field(min_length=1)
    origin: Literal["agent", "strategy", "observation"]
    mode: InteractionMode = "command"
    command: CommandT


class InteractionTool(BaseModel):
    """Declare a model-facing entry whose schema and handler come from its owner."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, pattern=r"^[a-zA-Z_][a-zA-Z0-9_-]*$")
    description: str = Field(min_length=1)
