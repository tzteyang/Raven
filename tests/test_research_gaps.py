"""A curation's public questions are researched one group each on the collector's channel, within its limits, and in
a scenario under the release seal preparation holds."""

import json
from types import SimpleNamespace

import pytest

from experimental.cultivation.collector import gaps
from experimental.cultivation.collector.collection import CollectionLimits
from experimental.cultivation.collector.scenario import scenario_researcher
from experimental.harness.participation.compartment import BoundaryError, GuardedProvider
from experimental.harness.scenario import load
from tests.research_helpers import make_scenario
from tests.test_research_collection import delivery, finding


def worker(root):
    return SimpleNamespace(
        baseline=SimpleNamespace(task=SimpleNamespace(text="Answer the tea shop's customers.")), root=root
    )


def unanswered(why):
    result = delivery(findings=0, synthesis="")
    return {**result, "unanswered": [{"question": "Which?", "why": why, "channel": "research"}]}


@pytest.fixture
def channel(monkeypatch):
    seen = {"briefs": [], "providers": []}

    def factory(worker, provider, *, records, admit=None, **options):
        seen["providers"].append(provider)
        seen["options"] = options

        async def research(task):
            seen["briefs"].append(task.brief)
            if "refund" in task.brief.questions[0]:
                return delivery(findings=1)
            return unanswered("No public source covers it.")

        return research

    monkeypatch.setattr(gaps, "research_channel", factory)
    return seen


@pytest.mark.asyncio
async def test_each_public_question_is_its_own_brief_and_returns_findings_or_why_not(tmp_path, channel):
    questions = [
        {"id": "question-1", "question": "How long does a card refund take?", "kind": "public"},
        {"id": "question-2", "question": "Which seasonal blends are popular?", "kind": "unclear"},
    ]
    found = await gaps.research_gaps(
        worker(tmp_path), object(), questions, records=tmp_path / "gap-research", researcher="claude"
    )
    asked = list(dict.fromkeys(brief.questions for brief in channel["briefs"]))
    assert asked == [(row["question"],) for row in questions]
    assert all("Answer the tea shop's customers." in brief.background for brief in channel["briefs"])
    assert channel["options"]["researcher"] == "claude"
    expected = {key: finding()[key] for key in ("text", "kind", "situation", "sources")}
    assert found["question-1"] == {"findings": [expected], "synthesis": "Uncertainty is recorded next to each claim."}
    assert found["question-2"] == {"reason": "No public source covers it."}
    folder = tmp_path / "gap-research" / "call-1"
    assert json.loads((folder / "questions.json").read_text()) == questions
    assert (folder / "wave-1.json").is_file() and (folder / "trace.json").is_file()
    await gaps.research_gaps(worker(tmp_path), object(), questions[:1], records=tmp_path / "gap-research")
    assert (tmp_path / "gap-research" / "call-2" / "questions.json").is_file()


@pytest.mark.asyncio
async def test_research_keeps_to_the_collectors_task_allowance(tmp_path, channel):
    questions = [{"id": f"question-{n}", "question": f"Q{n}?", "kind": "public"} for n in (1, 2)]
    with pytest.raises(ValueError, match="at most 1 research tasks"):
        await gaps.research_gaps(
            worker(tmp_path), object(), questions, records=tmp_path / "r", limits=CollectionLimits(research_tasks=1)
        )
    assert channel["briefs"] == []


@pytest.mark.asyncio
async def test_a_scenario_researches_under_the_release_seal(tmp_path, monkeypatch):
    sealed_line = "Greet the customer and quote from the price list only."
    seen = []

    def factory(worker, provider, *, records, admit=None, **options):
        seen.append(provider)

        async def research(task):
            return delivery(findings=1) | {"findings": [finding(text=sealed_line)]}

        return research

    monkeypatch.setattr(gaps, "research_channel", factory)
    scenario = load(make_scenario(tmp_path / "shop"))
    research = scenario_researcher(scenario, lambda: ("prices",), records=tmp_path / "gap-research")
    admitted = []
    question = [{"id": "question-1", "question": "How long does a card refund take?", "kind": "public"}]
    with pytest.raises(BoundaryError, match="gaps.research"):
        await research(worker(tmp_path), object(), question, admit=lambda value, where: admitted.append(where))
    assert isinstance(seen[0], GuardedProvider) and seen[0].guard.role == "curator"
    assert admitted == []


@pytest.mark.asyncio
async def test_a_group_whose_research_meets_a_seal_is_withheld_and_the_others_still_answer(tmp_path, monkeypatch):
    def factory(worker, provider, *, records, admit=None, **options):
        async def research(task):
            if "deposit" in task.brief.questions[0]:
                raise BoundaryError("curator", "research.review", ["<sealed text>"])
            return delivery(findings=1)

        return research

    monkeypatch.setattr(gaps, "research_channel", factory)
    questions = [
        {"id": "question-1", "question": "May an employer ask for a deposit?", "kind": "public"},
        {"id": "question-2", "question": "How long does a card refund take?", "kind": "public"},
    ]
    found = await gaps.research_gaps(worker(tmp_path), object(), questions, records=tmp_path / "gap-research")
    assert "findings" in found["question-2"]
    assert "findings" not in found["question-1"]
    wave = json.loads((tmp_path / "gap-research" / "call-1" / "wave-1.json").read_text())
    assert any(group.get("error_type") == "BoundaryError" for group in wave)
