"""Simulated user answers preserve adoption meaning without releasing private source material, for preparation
questions and for the questions a curation leaves open."""

import json

import pytest

from experimental.cultivation.collector.information import Question
from experimental.harness.loop.gaps import Reply
from experimental.harness.scenario import load
from experimental.simulation.bench.information import CounterpartAnswers, gap_answerers
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
    assert record["answer"] == {"text": None, "reason": "The material does not say.", "public": False}


CURATION_QUESTION = {"id": "question-1", "question": "Who approves a discount above the list?", "kind": "private"}


@pytest.mark.asyncio
async def test_a_curation_question_is_answered_as_stated_or_referred_to_public_sources(tmp_path):
    scenario = load(make_scenario(tmp_path / "shop"))
    provider = Provider(
        response("answer_question", {"text": "The shift lead approves it.", "reason": "Our practice."}),
        response("answer_question", {"text": None, "reason": "That is a legal question.", "public": True}),
    )
    answer = CounterpartAnswers(provider, scenario, ("owner-policy",), ("prices",), records=tmp_path / "answers")
    assert await answer.reply(CURATION_QUESTION) == Reply("The shift lead approves it.")
    assert json.loads(provider.requests[0]["messages"][1]["content"])["question"] == CURATION_QUESTION
    public = {**CURATION_QUESTION, "id": "question-2", "question": "How long may refunds take by law?"}
    assert await answer.reply(public) == Reply(None, public=True)
    assert len(list((tmp_path / "answers").glob("*.json"))) == 2


@pytest.mark.asyncio
async def test_a_curation_answer_quoting_material_not_yet_handed_over_is_withheld(tmp_path):
    scenario = load(make_scenario(tmp_path / "shop"))
    provider = Provider(
        response(
            "answer_question",
            {"text": "Greet the customer and quote from the price list only.", "reason": "Our procedure."},
        )
    )
    answer = CounterpartAnswers(provider, scenario, ("sop",), ("prices",), records=tmp_path / "answers")
    assert await answer.reply(CURATION_QUESTION) == Reply(None)
    record = json.loads(next((tmp_path / "answers").glob("*.json")).read_text())
    assert record["answer"]["text"] is None and "release scope" in record["answer"]["reason"]


def test_gap_answerers_use_what_is_configured_and_refuse_what_is_named_but_missing(tmp_path):
    scenario = load(make_scenario(tmp_path / "shop"))
    counterpart = CounterpartAnswers(Provider(), scenario, ("owner-policy",), ("prices",), records=tmp_path / "a")

    async def research(worker, provider, questions, *, admit):
        return {}

    assert gap_answerers("none", counterpart, research) is None
    assert gap_answerers("both") is None
    both = gap_answerers("both", counterpart, research, research_tasks=2)
    assert both.answer == counterpart.reply and both.research is research and both.research_tasks == 2
    assert gap_answerers("counterpart", counterpart, research).research is None
    assert gap_answerers("research", counterpart, research).answer is None
    assert gap_answerers("both", None, research).answer is None
    with pytest.raises(ValueError, match="information-answer-material"):
        gap_answerers("counterpart", None, research)
    with pytest.raises(ValueError, match="research channel"):
        gap_answerers("research", counterpart, None)
