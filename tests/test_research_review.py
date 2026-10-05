"""Research review returns evidence or rejection without autonomously scheduling repairs."""

import asyncio
import json

import pytest

from experimental.research.information import ResearchBrief, Review
from experimental.research.inquiry import Inquiry
from experimental.research.review import review_research
from tests.research_helpers import research_brief
from tests.test_research_inquiry import FOUND, PAGE, TEXT, Pages


class Researcher:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.requests = []

    async def research(self, packet, web, check, **kwargs):
        self.requests.append(packet)
        return self.answers.pop(0), {"researcher": "controlled"}


def delivery(**changes):
    return Inquiry.model_validate(
        {"findings": [FOUND], "synthesis": "The source establishes the serving window.", **changes}
    )


@pytest.mark.asyncio
async def test_rejection_returns_to_caller_and_only_an_explicit_second_call_repairs(tmp_path):
    actor = Researcher(delivery(findings=[{**FOUND, "text": "Tea is served at midnight."}]), delivery())
    reviews = []

    async def review(packet, records):
        reviews.append(packet)
        assert packet["source_views"][PAGE] == TEXT
        assert 0 < packet["time_budget_seconds"] < 3600
        if len(reviews) == 1:
            assert not packet["previous_reviews"]
            return Review(accepted=False, reason="The quote does not support midnight.", issues=("Correct the time.",))
        assert packet["previous_reviews"][0]["issues"] == ["Correct the time."]
        return Review(accepted=True, reason="The corrected claim follows the source.")

    first = await review_research(
        actor, ResearchBrief(**research_brief()), Pages({PAGE: TEXT}), review, records=tmp_path / "first"
    )
    assert actor.requests[0]["time_budget_seconds"] == 3600
    assert not first["review"]["accepted"] and len(actor.requests) == 1
    assert json.loads((tmp_path / "first/status.json").read_text())["status"] == "rejected"
    second = await review_research(
        actor,
        ResearchBrief(**research_brief()),
        Pages({PAGE: TEXT}),
        review,
        records=tmp_path / "second",
        previous=tmp_path / "first",
    )
    assert second["review"]["accepted"] and len(actor.requests) == 2
    assert actor.requests[1]["revision"]["source_views"][PAGE] == TEXT
    assert [review["accepted"] for review in second["review_history"]] == [False, True]
    assert second["findings"][0]["text"] == FOUND["text"]


@pytest.mark.asyncio
async def test_refused_candidate_text_is_not_admitted_as_low_confidence_evidence(tmp_path):
    bad = {**FOUND, "text": "Unverified private rule.", "evidence": "This passage was never published anywhere."}
    actor = Researcher(delivery(findings=[FOUND, bad]))

    async def review(packet, records):
        assert len(packet["delivery"]["findings"]) == 1
        assert packet["refused"][0]["text"] == bad["text"]
        return Review(accepted=True, reason="Only the retained schedule supports this bounded delivery.")

    result = await review_research(
        actor, ResearchBrief(**research_brief()), Pages({PAGE: TEXT}), review, records=tmp_path / "records"
    )
    assert len(result["refused"]) == 1
    assert bad["text"] not in json.dumps(result)


@pytest.mark.asyncio
async def test_attempt_timeout_preserves_failure_without_publishing_acceptance(tmp_path):
    class Slow:
        async def research(self, *args, **kwargs):
            await asyncio.sleep(10)

    async def unused(*args):
        pytest.fail("no delivery exists to review")

    with pytest.raises(TimeoutError):
        await review_research(
            Slow(), ResearchBrief(**research_brief()), Pages(), unused, records=tmp_path / "records", timeout=0.01
        )
    assert (tmp_path / "records/trace.json").exists()
    assert not (tmp_path / "records/result.json").exists()
    assert json.loads((tmp_path / "records/status.json").read_text())["error_type"] == "TimeoutError"


@pytest.mark.asyncio
async def test_unreadable_source_is_reported_without_an_automatic_retry(tmp_path):
    actor = Researcher(delivery())

    async def reject(packet, records):
        assert not packet["delivery"]["findings"] and not packet["source_views"]
        assert any("could not be read" in reason for reason in packet["refused"][0]["reasons"])
        return Review(
            accepted=False,
            reason="Independent source retrieval failed.",
            issues=("Find a readable source or preserve the gap.",),
        )

    result = await review_research(actor, ResearchBrief(**research_brief()), Pages(), reject, records=tmp_path / "run")
    assert not result["review"]["accepted"] and len(actor.requests) == 1
    assert result["refused"] and not result["findings"]
