"""An attribution's budget, its resumable progress and how it stops early."""

from dataclasses import dataclass
from math import isfinite

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from ..generation.run import GenerationInterruptedError
from ..harness.attribution import Attribution


@dataclass(frozen=True)
class AttributionLimits:
    """An attribution's own budget, separate from the curation that follows it; `max_output` as in the
    generation's limits."""

    max_calls: int = 6
    max_queries: int = 10
    call_timeout: float = 180
    max_output: int | None = None

    def __post_init__(self):
        if (
            not isinstance(self.max_calls, int)
            or not isinstance(self.max_queries, int)
            or self.max_calls < 1
            or self.max_queries < 0
            or not isfinite(self.call_timeout)
            or self.call_timeout <= 0
            or (self.max_output is not None and (not isinstance(self.max_output, int) or self.max_output < 1))
        ):
            raise ValueError("attribution limits must be finite positive bounds (the query count may be zero)")


class AttributionState(BaseModel):
    """Serializable progress at a completed tool round, bound to the inputs and the attributor it started with."""

    model_config = ConfigDict(extra="forbid")

    input_id: str
    identity: dict[str, JsonValue]
    subjects: tuple[str, ...]
    attribution: Attribution | None = None
    messages: list[dict] = Field(default_factory=list)
    trace: list[dict] = Field(default_factory=list)
    calls: int = Field(default=0, ge=0)
    queries: int = Field(default=0, ge=0)

    def check(self, input_id: str, limits: AttributionLimits) -> None:
        if self.input_id != input_id:
            raise ValueError("attribution inputs or attributor changed; cannot resume this attribution")
        # The last call's grace (see `generation.run.ask`) may have spent one call past the budget.
        if limits.max_calls < self.calls - 1 or limits.max_queries < self.queries:
            raise ValueError("resume limits are cumulative and cannot be below consumed budgets")


class AttributionInterruptedError(GenerationInterruptedError):
    """An attribution stopped before its submission; its investigation remains valid for a continuation."""


class AttributionPausedError(AttributionInterruptedError):
    def __init__(self, state):
        super().__init__(
            f"Attribution call budget exhausted after {state.calls} calls; resume with a higher total max_calls", state
        )
