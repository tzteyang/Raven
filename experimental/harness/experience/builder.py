"""Construct conditional revision methods from approved evidence and bounded review feedback."""

from pydantic import Field

from experimental.harness.experience.contracts import (
    SOURCE,
    BuildRequest,
    Contract,
    ExperienceProposal,
    ExperienceReview,
    digest,
    for_model,
)
from experimental.harness.experience.governance import changed_fields
from experimental.harness.experience.model import PROMPTS, ModelCallError, ModelClient


class ProposalSubmission(Contract):
    AUDIENCES = {"proposals": SOURCE}
    proposals: tuple[ExperienceProposal, ...] = Field(default=(), max_length=4)


def validate_proposals(proposals: tuple[ExperienceProposal, ...], request: BuildRequest) -> None:
    allowed = {event.reference for event in request.events}
    if any(link.reference not in allowed for proposal in proposals for link in proposal.evidence):
        raise ModelCallError("invalid_submission", "Use only evidence references in the current event batch.")
    if any(
        set(proposal.condition.required_capabilities) - set(request.capabilities)
        or set(proposal.condition.contract_ids) - set(request.contract_ids)
        for proposal in proposals
    ):
        raise ModelCallError(
            "invalid_submission", "Use only the host capabilities and contracts supplied in the request."
        )
    identities = [proposal.model_dump_json() for proposal in proposals]
    if len(identities) != len(set(identities)):
        raise ModelCallError("invalid_submission", "Do not submit duplicate experience proposals.")
    if request.repair is not None:
        if len(proposals) > 1:
            raise ModelCallError("invalid_submission", "A scoped repair may propose only one replacement.")
        for proposal in proposals:
            changes = changed_fields(
                request.repair.current.model_dump(exclude={"evidence"}), proposal.model_dump(exclude={"evidence"})
            )
            if not changes or any(
                not any(field == allowed or field.startswith(allowed + ".") for allowed in request.repair.fields)
                for field in changes
            ):
                raise ModelCallError(
                    "invalid_submission", "The replacement exceeds the diagnosed fields or changes nothing."
                )


class ModelExperienceBuilder(ModelClient):
    def __init__(self, provider, **kwargs):
        super().__init__(provider, (PROMPTS / "build.md").read_text(), **kwargs)

    def identity(self) -> dict:
        return {
            **super().identity(ProposalSubmission, "submit_experience"),
            "submission_constraints": 2,
            "request_schema": digest(BuildRequest.model_json_schema()),
        }

    async def build(
        self,
        request: BuildRequest,
        *,
        previous: tuple[ExperienceProposal, ...] = (),
        reviews: tuple[ExperienceReview, ...] = (),
        correction: str | None = None,
    ) -> tuple[ExperienceProposal, ...]:
        packet = for_model(request, "builder")
        if previous:
            packet["revision"] = {
                "previous": [for_model(value, "builder") for value in previous],
                "reviews": [for_model(value, "builder") for value in reviews],
            }
        schema = ProposalSubmission.model_json_schema()
        maximum = 1 if correction and not previous else 4
        schema["properties"]["proposals"]["maxItems"] = maximum
        result = await self.submit(
            packet, ProposalSubmission, "submit_experience", correction=correction, submission_schema=schema
        )
        if len(result.proposals) > maximum:
            raise ModelCallError("invalid_submission", "A format repair may submit at most one concise new proposal.")
        validate_proposals(result.proposals, request)
        return result.proposals
