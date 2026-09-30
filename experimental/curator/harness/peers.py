"""Narrow cross-strategy operations, always resolved in the current host scope."""

from typing import Protocol

from pydantic import JsonValue

from .interaction import InteractionMode
from .resources import EffectiveCapabilities


class StrategyPeers(Protocol):
    """Read committed views or request a change through its actual owner.

    Dynamic domain commands are validated against the target's concrete schema.
    Successful changes are independent commits: a later failure in the caller
    does not roll back another owner's state or external effects. Cyclic awaited
    owner calls are rejected rather than deadlocking their checkpoint locks.
    """

    def read_plan(self) -> JsonValue:
        """Return the last produced plan view, detached, or None when unavailable."""
        ...

    async def interact_planning(self, command: JsonValue, *, mode: InteractionMode = "command") -> JsonValue:
        """Submit a typed planning request and return its business reply."""
        ...

    async def interact_memory(self, command: JsonValue, *, mode: InteractionMode = "command") -> JsonValue:
        """Submit an information request; an upstream query stays read-only."""
        ...

    def capabilities(self) -> EffectiveCapabilities | None:
        """Read the latest actual model-call view, or None before one was produced."""
        ...

    async def request_action(self, command: JsonValue) -> JsonValue:
        """Request an Action judgment through its declared request operation."""
        ...
