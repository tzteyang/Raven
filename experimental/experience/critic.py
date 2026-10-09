"""Review exact experience proposals for transfer, specificity, source bounds and evidence."""

from pydantic import Field

from .contracts import (
    SOURCE,
    BuildRequest,
    Contract,
    ExperienceCondition,
    ExperienceProposal,
    ExperienceReview,
    digest,
    for_model,
)
from .governance import Issue, Record
from .model import PROMPTS, ModelCallError, ModelClient


class ReviewSubmission(Contract):
    AUDIENCES = {"reviews": SOURCE}
    reviews: tuple[ExperienceReview, ...] = Field(max_length=4)


class AuditSubmission(Record):
    issues: tuple[Issue, ...] = Field(default=(), max_length=8)


def validate_reviews(reviews: tuple[ExperienceReview, ...], count: int) -> None:
    if sorted(review.proposal_index for review in reviews) != list(range(count)):
        raise ModelCallError("invalid_submission", "Review every proposal index exactly once; do not invent indices.")


class ModelExperienceCritic(ModelClient):
    def __init__(self, provider, **kwargs):
        super().__init__(provider, (PROMPTS / "critic.md").read_text(), **kwargs)

    def identity(self) -> dict:
        return {
            **super().identity(ReviewSubmission, "submit_reviews"),
            "submission_constraints": 2,
            "request_schema": digest(BuildRequest.model_json_schema()),
            "audit": digest(
                {"prompt": (PROMPTS / "audit.md").read_text(), "schema": AuditSubmission.model_json_schema()}
            ),
        }

    async def audit(self, *, methods: list[dict], evidence: list[dict]) -> tuple[Issue, ...]:
        client = ModelClient(
            self.provider,
            (PROMPTS / "audit.md").read_text(),
            model=self.model,
            effort=self.effort,
            limits=self.limits,
            trace=self.trace,
        )
        targets = {row["target"] for row in methods}
        known = {row["reference"] for row in evidence}
        schema = AuditSubmission.model_json_schema()
        schema["properties"]["issues"]["maxItems"] = min(8, len(targets))
        fields = schema["$defs"]["Issue"]["properties"]
        fields["target"] = {"type": "string", "enum": sorted(targets)}
        fields["evidence"]["items"] = {"type": "string", "enum": sorted(known)}
        fields["fields"]["items"] = {
            "type": "string",
            "enum": [
                "content.guidance",
                "content.support_kind",
                "content.condition",
                *("content.condition." + key for key in ExperienceCondition.model_fields),
            ],
        }
        result = await client.submit(
            {"methods": methods, "evidence": evidence},
            AuditSubmission,
            "submit_experience_diagnoses",
            submission_schema=schema,
        )
        if len({issue.target for issue in result.issues}) != len(result.issues):
            raise ModelCallError("invalid_submission", "Each method needs one bounded diagnosis.")
        for issue in result.issues:
            if issue.target not in targets or set(issue.evidence) - known:
                raise ModelCallError("invalid_submission", "Diagnoses must cite the supplied methods and evidence.")
        return result.issues

    async def review(
        self, proposals: tuple[ExperienceProposal, ...], request: BuildRequest, *, correction: str | None = None
    ) -> tuple[ExperienceReview, ...]:
        if not proposals:
            return ()
        packet = {
            "evidence": for_model(request, "critic"),
            "proposals": [for_model(proposal, "critic") for proposal in proposals],
            "proposal_indices": list(range(len(proposals))),
        }
        schema = ReviewSubmission.model_json_schema()
        schema["properties"]["reviews"].update(minItems=len(proposals), maxItems=len(proposals))
        schema["$defs"]["ExperienceReview"]["properties"]["proposal_index"] = {
            "type": "integer",
            "enum": packet["proposal_indices"],
        }
        result = await self.submit(
            packet, ReviewSubmission, "submit_reviews", correction=correction, submission_schema=schema
        )
        validate_reviews(result.reviews, len(proposals))
        return result.reviews
