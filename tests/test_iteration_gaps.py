"""A curation's open questions reach the counterpart at its next review or research, by their kind, and the next
curation reads the settled ones with their provenance; without answerers the questions only stay in the record."""

import pytest

from experimental.cultivation.conversation import Conversation
from experimental.harness.curator.generation.run import GapReportedError
from experimental.harness.loop.gaps import Gaps, Reply, heard_answers
from experimental.harness.loop.session import Limits, Outcome, Session
from experimental.harness.participation.compartment import Boundaries, BoundaryError
from experimental.harness.participation.protocols import Signal
from experimental.harness.scenario.sealed import Sealed
from tests.test_iteration_run import CONTINUE, CURATE, FakeWorker, Scripted
from tests.test_iteration_run import analyses as analyses  # noqa: F401 -- the loop test's Analyst stand-in

QUESTION = "Who approves a refund above the listed amount?"


def student(*messages):
    return Conversation(Scripted("student", *messages), max_turns=2)


class Answerers:
    """A counterpart and a researcher that record what they were asked and reply from scripts."""

    def __init__(self, replies=(), found=None):
        self.replies, self.found = list(replies), found or {}
        self.asked, self.researched = [], []

    async def answer(self, question):
        self.asked.append(question)
        return self.replies.pop(0)

    async def research(self, worker, provider, questions, *, admit):
        self.researched.append(list(questions))
        return {row["id"]: self.found.get(row["question"], {"reason": "Nothing found."}) for row in questions}

    def gaps(self, *, counterpart=True, research=True, tasks=3):
        return Gaps(
            answer=self.answer if counterpart else None,
            research=self.research if research else None,
            research_tasks=tasks,
        )


class Curator:
    """Reports one gap of each scripted kind, one curation after another, and keeps the feedback it was given."""

    def __init__(self, *kinds):
        self.kinds, self.feedback = list(kinds), []
        self.__name__ = "curator"

    async def __call__(self, worker, provider, *, feedback=None, **options):
        self.feedback.append(feedback)
        if self.kinds:
            kind = self.kinds.pop(0)
            raise GapReportedError("select", f"{QUESTION} ({kind})", kind=kind)


async def round_(session, text="Refunds are wrong."):
    await session.trial(student("Hi"))
    session.signal(Signal("human", text))
    await session.assess()
    return await session.analyse()


def test_a_question_goes_where_its_kind_can_be_settled():
    both = Gaps(answer=Reply, research=Reply)
    assert [both.route(kind) for kind in ("private", "unclear", "public")] == ["counterpart", "counterpart", "research"]
    assert both.route("unclear", declined=True) == "research"
    assert both.route("private", declined=True) == "unanswered"
    assert both.route("private", declined=True, referred=True) == "research"
    asking = Gaps(answer=Reply)
    assert asking.route("public") == "unanswered" and asking.route("unclear", declined=True) == "unanswered"
    researching = Gaps(research=Reply)
    assert researching.route("private") == "unanswered" and researching.route("unclear") == "research"
    with pytest.raises(ValueError, match="counterpart, research or both"):
        Gaps()
    with pytest.raises(ValueError, match="unknown question kind"):
        both.route("secret")


@pytest.mark.asyncio
async def test_a_private_question_waits_for_the_next_review_and_reaches_the_next_curation_as_stated(tmp_path, analyses):
    analyses.scripted.extend([CURATE, CURATE, CONTINUE])
    answerers = Answerers([Reply("Refunds above the list need the manager.")])
    curator = Curator("private")
    session = Session.open(FakeWorker(tmp_path), object(), curator=curator, gaps=answerers.gaps())
    assert await session.onboard()
    assert answerers.asked == [] and answerers.researched == []
    (row,) = session.record["questions"]
    assert row["status"] == "pending" and row["route"] == "counterpart" and row["kind"] == "private"
    assert await round_(session) == Outcome("curate")
    assert answerers.asked == [{"id": "question-1", "question": f"{QUESTION} (private)", "kind": "private"}]
    assert answerers.researched == []
    assert row["answer"] == {"provenance": "counterpart", "text": "Refunds above the list need the manager."}
    await session.curate()
    assert curator.feedback[-1]["information"]["answers"] == [
        {
            "id": "question-1",
            "question": f"{QUESTION} (private)",
            "kind": "private",
            "status": "answered",
            "answer": {"provenance": "counterpart", "text": "Refunds above the list need the manager."},
        }
    ]


@pytest.mark.asyncio
async def test_a_public_question_is_researched_right_away_and_carries_its_sources(tmp_path, analyses):
    finding = {
        "text": "Card refunds settle within ten days.",
        "kind": "fact",
        "situation": "",
        "sources": ["https://a"],
    }
    answerers = Answerers(found={f"{QUESTION} (public)": {"findings": [finding], "synthesis": "Ten days."}})
    curator = Curator("public")
    session = Session.open(FakeWorker(tmp_path), object(), curator=curator, gaps=answerers.gaps())
    analyses.scripted.extend([CURATE, CONTINUE])
    assert await session.onboard()
    assert answerers.researched == [[{"id": "question-1", "question": f"{QUESTION} (public)", "kind": "public"}]]
    assert answerers.asked == []
    (row,) = session.record["questions"]
    assert row["status"] == "answered" and row["researched"] == 0
    assert row["answer"] == {"provenance": "research", "findings": [finding], "synthesis": "Ten days."}
    await round_(session)
    await session.curate()
    (heard,) = curator.feedback[-1]["information"]["answers"]
    assert heard["answer"]["provenance"] == "research" and heard["answer"]["findings"][0]["sources"] == ["https://a"]


@pytest.mark.asyncio
async def test_research_takes_only_what_is_public_or_left_open_and_the_rest_stays_unanswered(tmp_path, analyses):
    analyses.scripted.extend([CURATE, CURATE, CURATE, CONTINUE])
    answerers = Answerers([Reply(None), Reply(None), Reply(None, public=True)])
    curator = Curator("unclear", "private", "private")
    session = Session.open(
        FakeWorker(tmp_path), object(), curator=curator, gaps=answerers.gaps(), limits=Limits(max_rounds=4)
    )
    assert await session.onboard()
    await round_(session)
    first = session.record["questions"][0]
    assert first["counterpart"] == "left open" and first["status"] == "unanswered"
    assert [row["kind"] for batch in answerers.researched for row in batch] == ["unclear"]
    await session.curate()
    await round_(session)
    second = session.record["questions"][1]
    assert second["status"] == "unanswered" and second["reason"] == "The counterpart left it open."
    assert [row["kind"] for batch in answerers.researched for row in batch] == ["unclear"]
    await session.curate()
    await round_(session)
    third = session.record["questions"][2]
    assert third["counterpart"] == "referred to public sources" and third["researched"] == 2
    assert [row["kind"] for batch in answerers.researched for row in batch] == ["unclear", "private"]
    await session.curate()
    assert {row["status"] for row in curator.feedback[-1]["information"]["answers"]} == {"unanswered"}


@pytest.mark.asyncio
async def test_research_between_two_analyses_is_bounded_and_the_rest_waits(tmp_path, analyses):
    analyses.scripted.extend([CONTINUE, CONTINUE])
    answerers = Answerers()
    session = Session.open(
        FakeWorker(tmp_path),
        object(),
        curator=Curator(),
        gaps=answerers.gaps(counterpart=False, tasks=1),
        limits=Limits(max_rounds=3),
    )
    assert await session.onboard()
    session.record["questions"] = [
        {"id": f"question-{n}", "round": 0, "stage": "select", "question": f"Q{n}", "kind": "public"}
        | {"status": "pending", "route": "research"}
        for n in (1, 2)
    ]
    await round_(session, "Fine.")
    assert [[row["id"] for row in batch] for batch in answerers.researched] == [["question-1"]]
    assert session.record["questions"][1]["status"] == "pending"
    await round_(session, "Fine.")
    assert [[row["id"] for row in batch] for batch in answerers.researched] == [["question-1"], ["question-2"]]


@pytest.mark.asyncio
async def test_nobody_is_asked_when_no_curation_could_read_the_answer_and_finishing_leaves_it_unanswered(
    tmp_path, analyses
):
    analyses.scripted.extend([CURATE])
    answerers = Answerers([Reply("Never asked.")])
    session = Session.open(
        FakeWorker(tmp_path), object(), curator=Curator("unclear"), gaps=answerers.gaps(), limits=Limits(max_rounds=1)
    )
    assert await session.onboard()
    await round_(session)
    assert answerers.asked == [] and answerers.researched == []
    session.finish()
    assert session.record["questions"][0]["status"] == "unanswered"


@pytest.mark.asyncio
async def test_without_answerers_the_question_only_stays_in_the_record(tmp_path, analyses):
    analyses.scripted.extend([CURATE, CONTINUE])
    curator = Curator("private")
    session = Session.open(FakeWorker(tmp_path), object(), curator=curator)
    assert await session.onboard()
    await round_(session)
    await session.curate()
    assert session.record["questions"] == [
        {"round": 0, "stage": "select", "question": f"{QUESTION} (private)", "kind": "private"}
    ]
    assert curator.feedback[-1] is not None and "information" not in curator.feedback[-1]
    assert heard_answers(session.record["questions"]) == []


@pytest.mark.asyncio
async def test_research_results_enter_the_curator_compartment_like_its_information(tmp_path, analyses):
    secret = "the refund approval threshold listed only in the sealed check text of this run"
    answerers = Answerers(found={f"{QUESTION} (public)": {"findings": [{"text": secret}], "synthesis": ""}})
    boundaries = Boundaries({"curator": Sealed.of([secret])})
    session = Session.open(
        FakeWorker(tmp_path), object(), curator=Curator("public"), gaps=answerers.gaps(), boundaries=boundaries
    )
    with pytest.raises(BoundaryError, match="admit:gaps.research"):
        await session.onboard()
