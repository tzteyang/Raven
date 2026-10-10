"""Check independent Critic decisions and complete exact proposal indexing."""

import pytest

from experimental.experience.contracts import BuildRequest, ExperienceReview, ReviewIssue
from experimental.experience.critic import ModelExperienceCritic
from experimental.experience.model import ModelCallError
from tests.experience_helpers import Provider, event, proposal, response


@pytest.mark.asyncio
async def test_critic_returns_a_specific_revision_issue_from_its_own_prompt():
    source = event()
    issue = ReviewIssue(kind="too_vague", field="guidance", reason="Identify the consumer and an observable effect.")
    review = ExperienceReview(proposal_index=0, decision="revise", issues=(issue,))
    provider = Provider(response("submit_reviews", {"reviews": [review.model_dump(mode="json")]}))
    critic = ModelExperienceCritic(provider)
    result = await critic.review((proposal(source, "Validate carefully."),), BuildRequest(events=(source.view,)))
    assert result == (review,)
    assert "independent Experience Critic" in provider.requests[0]["messages"][0]["content"]
    assert "universal claim" in provider.requests[0]["messages"][0]["content"]
    schema = provider.requests[0]["tools"][0]["function"]["parameters"]
    assert schema["properties"]["reviews"]["minItems"] == schema["properties"]["reviews"]["maxItems"] == 1
    assert schema["$defs"]["ExperienceReview"]["properties"]["proposal_index"]["enum"] == [0]


@pytest.mark.asyncio
@pytest.mark.parametrize("indices", [[], [1], [0, 0]])
async def test_missing_unknown_and_duplicate_review_indices_are_rejected(indices):
    reviews = [{"proposal_index": index, "decision": "accept", "issues": []} for index in indices]
    source = event()
    provider = Provider(response("submit_reviews", {"reviews": reviews}))
    with pytest.raises(ModelCallError, match="exactly once"):
        await ModelExperienceCritic(provider).review((proposal(source),), BuildRequest(events=(source.view,)))


@pytest.mark.asyncio
async def test_no_proposals_need_no_critic_call():
    provider = Provider()
    assert await ModelExperienceCritic(provider).review((), BuildRequest(events=(event().view,))) == ()
    assert not provider.requests
