"""Audit evaluation episodes and propose current corrections and reusable construction guidance."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from experimental.harness.assessor.revision import Permission
from experimental.harness.contract.declaration import schema_for
from experimental.harness.curator.generation.context.render import tool
from experimental.harness.experience.governance import Issue as ExperienceIssue
from experimental.harness.participation.exchange import exchange, messages

PROMPT = Path(__file__).resolve().parent / "prompts" / "review.md"
REVIEW = "submit_evaluation_review"


class Issue(BaseModel):
    """An evidenced defect in the evaluation apparatus, not an instruction to change the worker."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    criterion: str = Field(description="An existing criterion id, or empty for a missing requirement.")
    target: Literal["rubric", "check", "evidence"]
    evidence: str = Field(min_length=1)
    correction: str = Field(min_length=1)
    allow: tuple[Permission, ...] = ()
    episode: str = ""


class GuidanceCorrection(BaseModel):
    """An evidenced, bounded reason to revise an already adopted construction method."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    cause: Literal["content", "scope", "selection", "loading", "application", "execution", "evaluation"]
    reason: str = Field(min_length=1, max_length=1600)
    fields: tuple[Literal["text", "kind", "scope"], ...] = ()


class GuidanceProposal(BaseModel):
    """A scoped principle or procedure proposed from named evaluation episodes; it is not adopted guidance."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["principle", "procedure"]
    scope: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=1600)
    episodes: tuple[str, ...] = Field(min_length=1, max_length=4)
    replaces: str | None = None
    correction: GuidanceCorrection | None = None


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    issues: tuple[Issue, ...] = Field(default=(), max_length=12)
    guidance: tuple[GuidanceProposal, ...] = Field(default=(), max_length=4)
    guidance_issues: tuple[ExperienceIssue, ...] = Field(default=(), max_length=8)


@dataclass
class MetaReviewer:
    """One bounded audit per assessment; adoption belongs to independently validated host operations."""

    model: str | None = None
    effort: str | None = None
    max_calls: int = 2
    timeout: float = 120
    trace: list[dict] = field(default_factory=list)
    reviews: list[dict] = field(default_factory=list)

    async def review(
        self,
        provider,
        *,
        task: str,
        norms: dict,
        assessment: dict,
        history=(),
        scope="task",
        guidance=(),
        open_issues=(),
        open_guidance_issues=(),
    ) -> Review:
        episodes = [*history[-3:], assessment]
        known = {episode["id"] for episode in episodes}
        known.update(issue["episode"] for issue in open_issues if issue.get("episode"))
        criteria = {criterion["id"]: criterion for criterion in assessment["criteria"]}
        packet = {
            "task": task,
            "materials": norms,
            "episodes": episodes,
            "scope": scope,
            "active_guidance": list(guidance),
            "open_issues": list(open_issues),
            "open_guidance_issues": list(open_guidance_issues),
        }

        def accept(arguments):
            review = Review.model_validate(arguments)
            for issue in review.issues:
                if issue.criterion and issue.criterion not in criteria:
                    raise ValueError(f"review names an unknown criterion: {issue.criterion!r}")
                if issue.episode and issue.episode not in known:
                    raise ValueError("evaluation defects must refer to a supplied episode")
                if issue.target == "evidence" and issue.allow:
                    raise ValueError("missing evidence does not authorize a rubric patch")
                for permission in issue.allow:
                    if permission.op == "add":
                        if issue.target != "rubric" or permission.parent_id != (issue.criterion or None):
                            raise ValueError("an addition must belong to the identified missing-coverage scope")
                    else:
                        if permission.id != issue.criterion or not issue.criterion:
                            raise ValueError("a repair permission must name the issue's criterion")
                        if criteria[issue.criterion].get("authority") == "external":
                            raise ValueError("external criteria are protected from model repairs")
                    if issue.target == "check" and (
                        permission.op != "rewrite"
                        or any(
                            field != "assessment" and not field.startswith("assessment.") for field in permission.fields
                        )
                    ):
                        raise ValueError("checker repairs may change only assessment fields")
            review = review.model_copy(
                update={
                    "issues": tuple(
                        issue.model_copy(update={"episode": issue.episode or assessment["id"]})
                        for issue in review.issues
                    )
                }
            )
            for proposal in review.guidance:
                if set(proposal.episodes) - known:
                    raise ValueError("guidance must cite supplied evaluation episodes")
                if proposal.scope not in (scope, "*"):
                    raise ValueError("guidance scope must be the supplied scope or a proposed cross-task '*'")
            available_guidance = {row["id"] for row in guidance} | {row["target"] for row in open_guidance_issues}
            if len({issue.target for issue in review.guidance_issues}) != len(review.guidance_issues):
                raise ValueError("combine the diagnosis of each guidance entry into one bounded issue")
            for issue in review.guidance_issues:
                if issue.target not in available_guidance or set(issue.evidence) - known:
                    raise ValueError("guidance issues must cite supplied methods and evaluation episodes")
                if set(issue.fields) - {"content.text", "content.kind", "scope"}:
                    raise ValueError("guidance diagnoses cannot change host metadata or admission rules")
            return review

        _, review = await exchange(
            provider,
            messages(PROMPT.read_text(), packet),
            [tool(REVIEW, "Submit evaluation defects and candidate construction guidance.", schema_for(Review))],
            submit={REVIEW: accept},
            model=self.model,
            effort=self.effort,
            max_calls=self.max_calls,
            timeout=self.timeout,
            trace=self.trace,
            label="meta_reviewer",
        )
        self.reviews.append({"episode": assessment["id"], **review.model_dump(mode="json")})
        return review

    def record(self) -> dict:
        return {"reviews": list(self.reviews), "trace": list(self.trace)}

    def restore(self, record: dict) -> None:
        """Retain prior audits when a host resumes its evaluation record."""
        self.reviews = list(record.get("reviews", ()))
        self.trace = list(record.get("trace", ()))
