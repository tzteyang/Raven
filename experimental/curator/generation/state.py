"""Serializable progress at a completed tool round, bound to its original inputs."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..harness import Candidate, Plan, Validation
from ..harness.artifact import Selection
from ..harness.attribution import Attributed
from ..raven_adapter.inspection import fingerprint
from .context.collect import Context


class GenerationState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_id: str
    stage: Literal["select", "design", "implement", "repair"] = "select"
    attribution: Attributed | None = None
    selection: Selection | None = None
    plan: Plan | None = None
    candidate: Candidate | None = None
    validation: Validation | None = None
    messages: list[dict] = Field(default_factory=list)
    staged: dict[str, str] = Field(default_factory=dict)
    trace: list[dict] = Field(default_factory=list)
    calls: int = Field(default=0, ge=0)
    queries: int = Field(default=0, ge=0)
    checks: int = Field(default=0, ge=0)
    repairs: int = Field(default=0, ge=0)

    @staticmethod
    def identity(context: Context) -> str:
        return fingerprint(
            {
                "task": context.task,
                "baseline": context.declaration.baseline,
                "contract": context.declaration.contract_id,
                "facts": context.facts,
                "sources": context.sources,
                "feedback": context.feedback,
                "observations": context.observations,
                "previous_plan": context.previous_plan.model_dump(mode="json") if context.previous_plan else None,
                "exploration": context.exploration,
            }
        )

    def check(self, context, limits):
        if self.input_id != self.identity(context):
            raise ValueError("curation inputs changed; cannot resume this generation")
        # A submission refused on the last call gets one more call (see `run.ask`), so the calls spent may exceed the
        # budget by one; resuming with the same budget then pauses again instead of failing.
        spent = {"calls": self.calls - 1, "queries": self.queries, "checks": self.checks, "repairs": self.repairs}
        if any(getattr(limits, f"max_{name}") < used for name, used in spent.items()):
            raise ValueError("resume limits are cumulative and cannot be below consumed budgets")

    def advance(self, stage):
        self.stage = stage
        self.messages = []
