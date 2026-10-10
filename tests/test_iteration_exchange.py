"""The exchange loop's grace: undelivered replies (no tool call, unparsable or off-schema arguments) are retried
without charging the budget, up to `grace`, the submission-only last call never runs a query, and a reply's text goes
back into the conversation capped. Every call asks for the model's whole output, and a reply cut at the output ceiling
is asked again down the effort ladder to no reasoning."""

import pytest
from pydantic import BaseModel, ConfigDict, field_validator

from experimental.harness.participation.exchange import ECHOED_CHARS, OUTPUT_TOKENS, ExchangeError, descent, exchange
from experimental.harness.participation.model_calls import MalformedArgumentsError
from raven.contracts.llm_provider import LLMResponse, ToolCallRequest
from tests.research_helpers import Provider, response

TOOLS = [{"type": "function", "function": {"name": "submit", "parameters": {"type": "object"}}}]
QUERY = {"type": "function", "function": {"name": "read", "parameters": {"type": "object"}}}


def accept(arguments):
    if arguments.get("broken"):
        raise MalformedArgumentsError("Tool arguments were not a valid JSON object.")
    if "value" not in arguments:
        raise ValueError("value is required")
    return arguments["value"]


@pytest.mark.asyncio
async def test_undelivered_replies_are_retried_without_charge_up_to_the_grace():
    provider = Provider(
        LLMResponse(content="Thinking out loud."),
        response("submit", {"broken": True}),
        response("submit", {"value": 1}),
    )
    trace = []
    name, value = await exchange(
        provider, [], TOOLS, submit={"submit": accept}, max_calls=1, grace=2, trace=trace, label="stage"
    )
    assert (name, value) == ("submit", 1)
    assert [(row["event"], row.get("charged", True)) for row in trace] == [
        ("model.call", True),
        ("output.missing", False),
        ("model.call", True),
        ("output.rejected", False),
        ("model.call", True),
        ("submit", True),
    ]
    assert [row["call"] for row in trace if row["event"] == "model.call"] == [1, 2, 3]


@pytest.mark.asyncio
async def test_the_grace_is_bounded_and_semantic_rejections_still_count():
    provider = Provider(
        response("submit", {"broken": True}),
        response("submit", {"broken": True}),
        response("submit", {"value": 1}),
    )
    with pytest.raises(ExchangeError, match="stage: submission budget exhausted") as info:
        await exchange(provider, [], TOOLS, submit={"submit": accept}, max_calls=1, grace=1, label="stage")
    assert [row.get("charged", True) for row in info.value.trace if row["event"] == "output.rejected"] == [False, True]

    provider = Provider(response("submit", {}), response("submit", {"value": 1}))
    with pytest.raises(ExchangeError, match="submission budget exhausted") as info:
        await exchange(provider, [], TOOLS, submit={"submit": accept}, max_calls=1, grace=2, label="stage")
    (rejected,) = [row for row in info.value.trace if row["event"] == "output.rejected"]
    assert rejected["error"] == "value is required" and "charged" not in rejected


@pytest.mark.asyncio
async def test_without_grace_the_budget_is_final():
    provider = Provider(LLMResponse(content="Thinking out loud."), response("submit", {"value": 1}))
    with pytest.raises(ExchangeError, match="submission budget exhausted"):
        await exchange(provider, [], TOOLS, submit={"submit": accept}, max_calls=1, grace=0, label="stage")


@pytest.mark.asyncio
async def test_a_query_named_on_the_submission_only_last_call_is_refused_and_never_run():
    ran = []
    provider = Provider(
        response("read", {"path": "a"}),
        response("read", {"path": "b"}),
        response("submit", {"value": 1}),
    )
    trace = []
    name, value = await exchange(
        provider,
        [],
        [QUERY, *TOOLS],
        submit={"submit": accept},
        query={"read": lambda arguments: ran.append(arguments["path"]) or "text"},
        max_calls=2,
        grace=1,
        trace=trace,
        label="stage",
    )
    assert (name, value) == ("submit", 1) and ran == ["a"]
    (refused,) = [row for row in trace if row["event"] == "output.rejected"]
    assert refused["tools"] == ["read"] and refused["charged"] is False
    assert [tool["function"]["name"] for tool in provider.requests[-1]["tools"]] == ["submit"]

    provider = Provider(response("read", {"path": "a"}), response("read", {"path": "b"}))
    with pytest.raises(ExchangeError, match="submission budget exhausted"):
        await exchange(
            provider, [], [QUERY, *TOOLS], submit={"submit": accept}, query={"read": ran.append}, max_calls=2, grace=0
        )
    assert ran == ["a", {"path": "a"}]


@pytest.mark.asyncio
async def test_a_degenerate_reply_text_is_capped_before_it_goes_back_into_the_conversation():
    markup = "<invoke name=submit>" * 50_000
    provider = Provider(
        LLMResponse(content=markup, tool_calls=[ToolCallRequest("c1", "submit", {})]),
        response("submit", {"value": 1}),
    )
    conversation, trace = [], []
    name, value = await exchange(
        provider, conversation, TOOLS, submit={"submit": accept}, max_calls=2, trace=trace, label="stage"
    )
    assert (name, value) == ("submit", 1)
    echoed = conversation[0]
    assert echoed["tool_calls"][0]["function"]["name"] == "submit"
    assert echoed["content"].startswith(markup[:ECHOED_CHARS]) and len(echoed["content"]) < ECHOED_CHARS + 100
    assert {"label": "stage", "event": "output.capped", "content_chars": len(markup)} in trace
    assert sum(len(message.get("content") or "") for message in conversation) < 2 * ECHOED_CHARS


class Shaped(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimensions: list[str]

    @field_validator("dimensions")
    @classmethod
    def known(cls, value):
        if "made-up" in value:
            raise ValueError("unknown dimension")
        return value


@pytest.mark.asyncio
async def test_a_submission_off_the_schema_is_undelivered_and_a_refused_content_counts():
    def parse(arguments):
        return Shaped.model_validate(arguments).dimensions

    provider = Provider(response("submit", {"dimension": ["knowledge"]}), response("submit", {"dimensions": ["a"]}))
    trace = []
    name, value = await exchange(
        provider, [], TOOLS, submit={"submit": parse}, max_calls=1, grace=1, trace=trace, label="stage"
    )
    assert (name, value) == ("submit", ["a"])
    (refused,) = [row for row in trace if row["event"] == "output.rejected"]
    assert "Extra inputs are not permitted" in refused["error"] and refused["charged"] is False

    provider = Provider(response("submit", {"dimensions": ["made-up"]}), response("submit", {"dimensions": ["a"]}))
    with pytest.raises(ExchangeError, match="submission budget exhausted"):
        await exchange(provider, [], TOOLS, submit={"submit": parse}, max_calls=1, grace=1, label="stage")


@pytest.mark.asyncio
@pytest.mark.parametrize("effort", [None, "high"])
async def test_every_call_asks_for_the_models_whole_output_beside_the_effort(effort):
    provider = Provider(LLMResponse(content="Thinking out loud."), response("submit", {"value": 1}))
    await exchange(provider, [], TOOLS, submit={"submit": accept}, effort=effort, label="stage")
    assert [request["max_tokens"] for request in provider.requests] == [OUTPUT_TOKENS, OUTPUT_TOKENS]
    assert all(request.get("reasoning_effort") == effort for request in provider.requests)


def ceiling(**fields):
    """A reply whose output reached the 100-token ceiling its request carried."""
    return LLMResponse(usage={"completion_tokens": 100}, max_tokens=100, **{"content": None, **fields})


@pytest.mark.asyncio
async def test_a_reply_cut_at_the_ceiling_is_asked_again_down_to_no_reasoning_without_charge():
    provider = Provider(ceiling(), ceiling(), ceiling(), response("submit", {"value": 1}))
    trace, conversation = [], []
    name, value = await exchange(
        provider,
        conversation,
        TOOLS,
        submit={"submit": accept},
        effort="high",
        max_calls=1,
        grace=0,
        trace=trace,
        label="owner",
    )
    assert (name, value) == ("submit", 1)
    assert [request["reasoning_effort"] for request in provider.requests[:3]] == ["high", "high", "low"]
    assert "reasoning_effort" in provider.requests[3] and provider.requests[3]["reasoning_effort"] == "none"
    assert [row["effort"] for row in trace if row["event"] == "model.call"] == ["high", "high", "low", "none"]
    assert [row["next_effort"] for row in trace if row.get("cut")] == ["high", "low", "none"]
    assert trace[-1] == {"label": "owner", "event": "submit", "effort": "none"}
    told = [message["content"] for message in conversation if message["role"] == "user"]
    assert len(told) == 3 and all(line.startswith("Your reply was cut off at the output limit") for line in told)


@pytest.mark.asyncio
async def test_a_submission_cut_mid_arguments_is_refused_and_asked_again_and_the_floor_is_final():
    cut_short = ceiling(tool_calls=[ToolCallRequest("submit", "submit", {})])
    provider = Provider(cut_short, response("submit", {"value": 2}))
    trace = []
    assert await exchange(
        provider, [], TOOLS, submit={"submit": accept}, effort="low", max_calls=1, grace=0, trace=trace
    ) == ("submit", 2)
    (rejected,) = [row for row in trace if row["event"] == "output.rejected"]
    assert (
        rejected["error"].startswith("The reply was cut off at the output limit") and rejected["next_effort"] == "low"
    )

    flagged = LLMResponse(content=None, finish_reason="length", truncated=True)
    provider = Provider(flagged, flagged, flagged, response("submit", {"value": 3}))
    with pytest.raises(ExchangeError, match="submission budget exhausted") as info:
        await exchange(provider, [], TOOLS, submit={"submit": accept}, effort="low", max_calls=1, grace=0)
    assert [row["effort"] for row in info.value.trace if row["event"] == "model.call"] == ["low", "low", "none"]


def test_the_ladder_skips_the_rungs_between_low_and_the_effort_asked_for():
    assert descent("xhigh") == ["xhigh", "low", "none"] and descent("high") == ["high", "low", "none"]
    assert descent(None) == [None, "low", "none"]
    assert descent("low") == ["low", "none"] and descent("minimal") == ["minimal", "none"]
    assert descent("none") == ["none"]
