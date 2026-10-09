"""Simulated user answers preserve adoption meaning without releasing private source material."""

import json

import pytest

from experimental.research.information import Question
from experimental.scenario import load
from experimental.simulation.information import CounterpartAnswers
from tests.research_helpers import Provider, make_scenario, response


@pytest.mark.asyncio
async def test_counterpart_answers_a_proposal_without_passing_its_private_sources(tmp_path):
    scenario = load(make_scenario(tmp_path / "shop"))
    provider = Provider(
        response("answer_question", {"text": "Do not adopt this proposal.", "reason": "Our policy differs."})
    )
    answer = CounterpartAnswers(provider, scenario, ("owner-policy",), ("prices",), records=tmp_path / "answers")
    question = Question(
        id="adoption",
        dimension="methods",
        question="Adopt discounts?",
        proposal="Allow unrestricted discounts.",
        reason="Organisational choice.",
    )
    assert await answer(question) == "Do not adopt this proposal."
    private_input = json.loads(provider.requests[0]["messages"][1]["content"])
    assert "owner-policy" in private_input["materials"]
    record = json.loads(next((tmp_path / "answers").glob("*.json")).read_text())
    assert record["question"]["proposal"] == question.proposal
    assert "materials" not in record


@pytest.mark.asyncio
async def test_counterpart_answer_with_private_text_is_left_unresolved(tmp_path):
    scenario = load(make_scenario(tmp_path / "shop"))
    provider = Provider(
        response(
            "answer_question",
            {"text": "Discounts above ten percent need the owner's approval.", "reason": "Private policy."},
        )
    )
    answer = CounterpartAnswers(provider, scenario, ("owner-policy",), ("prices",), records=tmp_path / "answers")
    question = Question(
        id="scope", dimension="methods", question="What is the discount policy?", reason="Clarify the method."
    )
    assert await answer(question) is None


@pytest.mark.asyncio
async def test_a_null_spelled_as_text_leaves_the_question_unresolved(tmp_path):
    scenario = load(make_scenario(tmp_path / "shop"))
    provider = Provider(response("answer_question", {"text": " null ", "reason": "The material does not say."}))
    answer = CounterpartAnswers(provider, scenario, ("owner-policy",), ("prices",), records=tmp_path / "answers")
    question = Question(id="channel", dimension="tasks", question="Which channel?", reason="Format.")
    assert await answer(question) is None
    record = json.loads(next((tmp_path / "answers").glob("*.json")).read_text())
    assert record["answer"] == {"text": None, "reason": "The material does not say."}
