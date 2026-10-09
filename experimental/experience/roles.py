"""Declare independent construction and review interfaces without installing a Harness."""

from typing import Protocol

from .contracts import BuildRequest, ExperienceProposal, ExperienceReview


class ExperienceBuilder(Protocol):
    async def build(
        self,
        request: BuildRequest,
        *,
        previous: tuple[ExperienceProposal, ...] = (),
        reviews: tuple[ExperienceReview, ...] = (),
        correction: str | None = None,
    ) -> tuple[ExperienceProposal, ...]: ...


class ExperienceCritic(Protocol):
    async def review(
        self, proposals: tuple[ExperienceProposal, ...], request: BuildRequest, *, correction: str | None = None
    ) -> tuple[ExperienceReview, ...]: ...
