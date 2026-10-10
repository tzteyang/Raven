"""Persist cumulative construction progress and exact reviewed candidate references."""

from typing import Literal

from pydantic import Field

from experimental.experience.contracts import RECORD_ONLY, Contract, ExperienceProposal, ExperienceReview


class CandidateRef(Contract):
    AUDIENCES = {"id": RECORD_ONLY, "version": RECORD_ONLY}
    id: str
    version: int = Field(ge=1)


class BuildState(Contract):
    AUDIENCES = {
        name: RECORD_ONLY
        for name in (
            "stage",
            "status",
            "builder_calls",
            "critic_calls",
            "revised",
            "proposals",
            "reviews",
            "previous",
            "previous_reviews",
            "accepted",
            "correction",
            "error",
            "trace",
        )
    }

    stage: Literal["build", "review", "revise", "finished"] = "build"
    status: Literal["ready", "running", "interrupted", "exhausted", "complete", "rejected"] = "ready"
    builder_calls: int = Field(default=0, ge=0)
    critic_calls: int = Field(default=0, ge=0)
    revised: bool = False
    proposals: tuple[ExperienceProposal, ...] = ()
    reviews: tuple[ExperienceReview, ...] = ()
    previous: tuple[ExperienceProposal, ...] = ()
    previous_reviews: tuple[ExperienceReview, ...] = ()
    accepted: tuple[CandidateRef, ...] = ()
    correction: str | None = None
    error: str | None = None
    trace: tuple[dict, ...] = ()


class BuildResult(Contract):
    AUDIENCES = {name: RECORD_ONLY for name in ("task_id", "state")}
    task_id: str
    state: BuildState
