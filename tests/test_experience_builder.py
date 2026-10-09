"""Check bounded Builder submissions and source isolation on actual provider interfaces."""

import pytest

from experimental.experience.builder import ModelExperienceBuilder
from experimental.experience.contracts import BuildRequest
from experimental.experience.model import ModelCallError, ModelLimits
from raven.contracts.llm_provider import LLMResponse
from tests.experience_helpers import Provider, event, proposal, response


@pytest.mark.asyncio
async def test_builder_returns_grounded_proposals_and_keeps_host_metadata_out():
    source = event()
    method = proposal(source)
    provider = Provider(response("submit_experience", {"proposals": [method.model_dump(mode="json")]}))
    builder = ModelExperienceBuilder(provider)
    assert await builder.build(BuildRequest(events=(source.view,))) == (method,)
    request = provider.requests[0]
    assert "UNTRUSTED" in request["messages"][1]["content"]
    assert "lineage_id" not in request["messages"][1]["content"]
    assert len(request["tools"]) == 1 and request["max_tokens"] == builder.limits.max_output
    assert builder.trace[0]["usage"]["total_tokens"] == 12


@pytest.mark.asyncio
async def test_builder_can_submit_no_candidate():
    provider = Provider(response("submit_experience", {"proposals": []}))
    assert await ModelExperienceBuilder(provider).build(BuildRequest(events=(event().view,))) == ()


@pytest.mark.asyncio
async def test_unknown_evidence_does_not_become_a_valid_proposal():
    method = proposal(event("another"))
    provider = Provider(response("submit_experience", {"proposals": [method.model_dump(mode="json")]}))
    with pytest.raises(ModelCallError, match="current event batch"):
        await ModelExperienceBuilder(provider).build(BuildRequest(events=(event().view,)))


@pytest.mark.asyncio
async def test_input_overflow_fails_before_any_provider_call():
    provider = Provider()
    with pytest.raises(ModelCallError) as error:
        await ModelExperienceBuilder(provider, limits=ModelLimits(max_input_bytes=1)).build(
            BuildRequest(events=(event().view,))
        )
    assert error.value.kind == "input_limit" and not error.value.called and not provider.requests


@pytest.mark.asyncio
async def test_provider_failure_is_not_retried_and_secrets_are_not_returned():
    provider = Provider(RuntimeError("private provider credential"))
    with pytest.raises(ModelCallError) as error:
        await ModelExperienceBuilder(provider).build(BuildRequest(events=(event().view,)))
    assert len(provider.requests) == 1 and "credential" not in str(error.value)


@pytest.mark.asyncio
async def test_truncated_and_wrong_tool_results_are_rejected():
    wrong = response("execute", {"command": "outside-source"})
    truncated = response("submit_experience", {"proposals": []})
    truncated.truncated = True
    for value in (wrong, truncated):
        with pytest.raises(ModelCallError):
            await ModelExperienceBuilder(Provider(value)).build(BuildRequest(events=(event().view,)))


@pytest.mark.asyncio
async def test_spent_output_budget_without_submission_is_reported_even_with_a_stop_finish_reason():
    provider = Provider(LLMResponse(content="", tool_calls=[], usage={"completion_tokens": 20}, finish_reason="stop"))
    builder = ModelExperienceBuilder(provider, limits=ModelLimits(max_output=20))
    with pytest.raises(ModelCallError) as error:
        await builder.build(BuildRequest(events=(event().view,)))
    assert error.value.kind == "truncated" and builder.trace[0]["error"] == "output_limit"
    assert len(provider.requests) == 1
