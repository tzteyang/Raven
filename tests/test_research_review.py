"""Research review admits findings one by one, returns the withheld parts, and repairs editorially when it can."""

import asyncio
import json

import pytest

from experimental.research.information import FindingVerdict, ResearchBrief, ResearchReview
from experimental.research.inquiry import Inquiry
from experimental.research.review import review_research
from tests.research_helpers import research_brief
from tests.test_research_inquiry import FOUND, PAGE, TEXT, Pages


class Researcher:
    def __init__(self, *answers):
        self.answers = list(answers)
        self.requests, self.revisions = [], []

    async def research(self, packet, web, check, **kwargs):
        self.requests.append(packet)
        return self.answers.pop(0), {"researcher": "controlled"}

    async def revise(self, packet, check, **kwargs):
        self.revisions.append(packet)
        return self.answers.pop(0), {"researcher": "controlled", "editorial": True}


def delivery(**changes):
    return Inquiry.model_validate(
        {"findings": [FOUND], "synthesis": "The source establishes the serving window.", **changes}
    )


def verdicts(*admitted, withheld=()):
    return tuple(
        [FindingVerdict(id=id, admit=True) for id in admitted]
        + [FindingVerdict(id=id, admit=False, reason=reason) for id, reason in withheld]
    )


@pytest.mark.asyncio
async def test_rejection_returns_to_caller_and_only_an_explicit_second_call_repairs(tmp_path):
    actor = Researcher(delivery(findings=[{**FOUND, "text": "Tea is served at midnight."}]), delivery())
    reviews = []

    async def review(packet, records):
        reviews.append(packet)
        assert packet["source_views"][PAGE] == TEXT
        assert packet["source_view_sizes"][PAGE] == {"chars": len(TEXT), "truncated": False}
        assert 0 < packet["time_budget_seconds"] < 3600
        if len(reviews) == 1:
            assert not packet["previous_reviews"] and packet["admitted_earlier"] == []
            return ResearchReview(
                reason="The quote does not support midnight.",
                findings=verdicts(withheld=(("researched-1", "The passage says two to five."),)),
                synthesis_admitted=False,
                issues=("Correct the time.",),
                needs_new_sources=True,
            )
        assert packet["previous_reviews"][0]["issues"] == ["Correct the time."]
        return ResearchReview(reason="The corrected claim follows the source.", findings=verdicts("researched-1"))

    first = await review_research(
        actor, ResearchBrief(**research_brief()), Pages({PAGE: TEXT}), review, records=tmp_path / "first"
    )
    assert actor.requests[0]["time_budget_seconds"] == 3600
    assert not first["review"]["accepted"] and first["status"] == "rejected" and len(actor.requests) == 1
    assert first["findings"] == [] and first["withheld"][0]["reasons"] == ["The passage says two to five."]
    assert json.loads((tmp_path / "first/status.json").read_text())["status"] == "rejected"
    second = await review_research(
        actor,
        ResearchBrief(**research_brief()),
        Pages({PAGE: TEXT}),
        review,
        records=tmp_path / "second",
        previous=tmp_path / "first",
    )
    assert second["review"]["accepted"] and second["status"] == "accepted"
    assert len(actor.requests) == 2 and not actor.revisions
    assert actor.requests[1]["revision"]["source_views"][PAGE] == TEXT
    assert actor.requests[1]["revision"]["editorial"] is False
    assert [review["accepted"] for review in second["review_history"]] == [False, True]
    assert second["findings"][0]["text"] == FOUND["text"]


@pytest.mark.asyncio
async def test_admitted_findings_stay_while_the_withheld_part_waits_for_an_editorial_revision(tmp_path):
    other = {
        **FOUND,
        "question": "What comes with the tea?",
        "text": "Scones always come with jam.",
        "evidence": "scones come with clotted cream",
    }
    actor = Researcher(delivery(findings=[FOUND, other]), delivery(findings=[], synthesis="Only the window holds."))

    async def review(packet, records):
        if not packet["previous_reviews"]:
            assert [finding["id"] for finding in packet["delivery"]["findings"]] == ["researched-1", "researched-2"]
            return ResearchReview(
                reason="The schedule holds; the scone claim adds jam the passage never mentions.",
                findings=verdicts("researched-1", withheld=(("researched-2", "The passage says cream, not jam."),)),
                synthesis_admitted=False,
                issues=("Drop jam from the scone finding and the synthesis.",),
            )
        assert packet["admitted_earlier"][0]["id"] == "researched-1"
        return ResearchReview(reason="The synthesis now stays within the admitted finding.")

    first = await review_research(
        actor, ResearchBrief(**research_brief()), Pages({PAGE: TEXT}), review, records=tmp_path / "first"
    )
    assert first["status"] == "partial" and not first["review"]["accepted"]
    assert [finding["id"] for finding in first["findings"]] == ["researched-1"] and first["synthesis"] == ""
    assert first["withheld"][0]["id"] == "researched-2" and first["review"]["withheld"] == ["researched-2"]
    second = await review_research(
        actor,
        ResearchBrief(**research_brief()),
        Pages({PAGE: TEXT}),
        review,
        records=tmp_path / "second",
        previous=tmp_path / "first",
    )
    assert len(actor.requests) == 1 and len(actor.revisions) == 1
    revision = actor.revisions[0]["revision"]
    assert revision["editorial"] is True and revision["admitted_findings"][0]["id"] == "researched-1"
    assert revision["source_views"][PAGE] == TEXT and revision["review"]["withheld"] == ["researched-2"]
    assert second["status"] == "accepted" and second["synthesis"] == "Only the window holds."
    assert second["run"]["editorial"] is True


@pytest.mark.asyncio
async def test_a_review_must_give_one_verdict_per_delivered_finding(tmp_path):
    actor = Researcher(delivery())

    async def incomplete(packet, records):
        return ResearchReview(reason="Looks fine.")

    with pytest.raises(ValueError, match="exactly the delivered findings"):
        await review_research(
            actor, ResearchBrief(**research_brief()), Pages({PAGE: TEXT}), incomplete, records=tmp_path / "run"
        )
    assert json.loads((tmp_path / "run/status.json").read_text())["error_type"] == "ValueError"


@pytest.mark.asyncio
async def test_refused_candidate_text_is_not_admitted_as_low_confidence_evidence(tmp_path):
    bad = {**FOUND, "text": "Unverified private rule.", "evidence": "This passage was never published anywhere."}
    actor = Researcher(delivery(findings=[FOUND, bad]))

    async def review(packet, records):
        assert len(packet["delivery"]["findings"]) == 1 and packet["leads"] == []
        assert packet["refused"][0]["text"] == bad["text"]
        return ResearchReview(
            reason="Only the retained schedule supports this bounded delivery.", findings=verdicts("researched-1")
        )

    result = await review_research(
        actor, ResearchBrief(**research_brief()), Pages({PAGE: TEXT}), review, records=tmp_path / "records"
    )
    assert len(result["refused"]) == 1 and result["status"] == "accepted"
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
async def test_unreadable_source_is_kept_as_a_lead_without_an_automatic_retry(tmp_path):
    actor = Researcher(delivery())

    async def reject(packet, records):
        assert not packet["delivery"]["findings"] and not packet["source_views"]
        assert any("could not be read" in reason for reason in packet["refused"][0]["reasons"])
        assert packet["leads"][0]["sources"] == [PAGE] and packet["leads"][0]["evidence"] == FOUND["evidence"]
        return ResearchReview(
            reason="Independent source retrieval failed.",
            synthesis_admitted=False,
            issues=("Find a readable source or preserve the gap.",),
            needs_new_sources=True,
        )

    result = await review_research(actor, ResearchBrief(**research_brief()), Pages(), reject, records=tmp_path / "run")
    assert not result["review"]["accepted"] and result["status"] == "rejected" and len(actor.requests) == 1
    assert result["refused"] and not result["findings"]
    assert json.loads((tmp_path / "run/leads.json").read_text())[0]["text"] == FOUND["text"]
    assert "check the passage by hand" in result["leads"][0]["reason"]
