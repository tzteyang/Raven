"""A session performs the loop's steps one call each, records what `run` records, and resumes from its record."""

import json
from types import SimpleNamespace

import pytest

from experimental.cultivation.conversation import Conversation
from experimental.harness.analyst.feedback import Feedback
from experimental.harness.curator.generation.run import GapReportedError, GenerationPausedError
from experimental.harness.curator.generation.run import Limits as CuratorLimits
from experimental.harness.loop import session as stepping
from experimental.harness.loop.records import load, runs
from experimental.harness.loop.run import run
from experimental.harness.loop.session import Limits, Outcome, Session, StepError
from experimental.harness.participation.protocols import Handover, Signal
from tests.test_iteration_run import CONTINUE, CURATE, FakeWorker, Scripted, Verifier, failing, passing
from tests.test_iteration_run import analyses as analyses  # noqa: F401 -- the loop test's Analyst stand-in


@pytest.fixture
def curations(monkeypatch):
    calls = []

    async def improve(worker, provider, *, feedback=None, model=None, limits=None, probe=None, observations=None):
        calls.append({"feedback": feedback, "model": model, "limits": limits, "observations": observations})
        worker.artifact_id = f"artifact-{len(calls)}"
        path = worker.root / "curation" / f"c{len(calls)}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"feedback": feedback, "active_artifact_id": worker.artifact_id}))

    monkeypatch.setattr(stepping, "improve", improve)
    return calls


def student(*messages):
    return Conversation(Scripted("student", *messages), max_turns=2)


@pytest.mark.asyncio
async def test_only_frozen_normal_task_verification_updates_experience(tmp_path, analyses):
    from unittest.mock import AsyncMock

    class Fixed:
        def verification_policy(self):
            return {"kind": "test_environment", "version": 1}

        async def evaluate(self, sessions):
            return Signal("fixed", satisfied=True, authority="external")

    experience = SimpleNamespace(
        identity="experience-policy",
        access=SimpleNamespace(access_scope="project"),
        outcome=AsyncMock(return_value={"status": "recorded"}),
    )

    async def curate(worker, provider, **kwargs):
        assert kwargs["experience"] is experience
        worker.artifact_id = "revision-1"
        path = worker.root / "curation" / "completed.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "active_artifact_id": worker.artifact_id,
                    "experience_learning": {"event": "episode-1", "origin": {"scope": "root", "input_key": "curation"}},
                }
            )
        )

    fixed = Fixed()
    worker = FakeWorker(tmp_path)
    session = Session.open(worker, object(), curator=curate, experience=experience, assessors=(fixed,))
    assert await session.onboard()
    await session.trial(student("normal input"))
    await session.holdout((Conversation(Scripted("held", "independent input"), max_turns=1),), (fixed,))
    experience.outcome.assert_not_awaited()
    await session.assess(fixed)
    experience.outcome.assert_awaited_once()
    args, kwargs = experience.outcome.call_args
    assert args[0] == "episode-1" and args[1].comparability == "comparable" and kwargs["held_out"] is False
    await session.assess(fixed)
    experience.outcome.assert_awaited_once()
    restored = Session.resume(worker, object(), session.path, curator=curate, experience=experience, assessors=(fixed,))
    assert restored.record["experience_pending"][0]["observed"]
    with pytest.raises(ValueError, match="original experience"):
        Session.resume(worker, object(), session.path, curator=curate)


OPENING = (
    Signal("agency", "Here are our materials.", attachments=(Handover("sop", "norm", ("uploads/sop/sop.md",)),)),
)


def shape(record):
    """A joined run as it reads, without what differs between two runs of one script: ids, file names, keys."""
    return {
        "task": record["task"],
        "status": record["status"],
        "stop": record.get("stop"),
        "opening": record["opening"],
        "onboarding": [row["feedback"] for row in record["initial_curation"]],
        "rounds": [
            {
                "turns": [
                    (exchange["user"], exchange["execution"]["records"])
                    for exchanges in item["sessions"].values()
                    for exchange in exchanges
                ],
                "signals": item["signals"],
                "feedback": item["feedback"],
                "curated": item["curated"],
                "analysis": [row["feedback"] for row in item["analysis"]],
                "curation": [row["feedback"]["signals"] for row in item["curation"]],
            }
            for item in record["rounds"]
        ],
    }


@pytest.mark.asyncio
async def test_measurement_only_signals_stay_out_of_analysis_curation_history_and_stop(tmp_path, curations, analyses):
    from experimental.harness.loop.records import cultivation
    from experimental.harness.participation.protocols import Item

    analyses.scripted.extend([CURATE, CURATE, CONTINUE])
    worker = FakeWorker(tmp_path)
    session = Session.open(worker, object(), measuring={"agency"})
    assert await session.onboard()
    await session.trial(student("Plan a trip", "Cheap please"))
    session.signal(
        Signal(
            "agency",
            "PRIVATE_MEASUREMENT_ONLY",
            satisfied=False,
            authority="external",
            items=(Item("private-check", "fail", "private-session"),),
        )
    )
    await session.assess(Verifier(failing("Ask the budget.")))
    assert (await session.analyse()).next == "curate"
    assert all(signal.source != "agency" for signal in analyses.calls[-1]["signals"])
    assert "PRIVATE_MEASUREMENT_ONLY" not in json.dumps(session.history)
    assert any(signal.source == "agency" for signal in session.rounds[-1].signals)
    assert await session.curate()
    assert "PRIVATE_MEASUREMENT_ONLY" not in json.dumps(curations[-1]["feedback"])
    assert all("agency" not in item.satisfied for item in session.history)
    assert all("agency" not in item.results and "agency" not in item.failed_in for item in session.history)
    await session.trial(student("Plan again", "Cheap please"))
    session.signal(Signal("agency", "PRIVATE_MEASUREMENT_ONLY", satisfied=False, authority="external"))
    await session.assess(Verifier(failing("Ask again.")))
    assert await session.analyse() == Outcome("curate")
    assert all("agency" not in item.satisfied for item in analyses.calls[-1]["history"])
    assert await session.curate()
    assert all("agency" not in item["satisfied"] for item in curations[-1]["feedback"]["history"])
    await session.trial(student("Final plan"))
    await session.assess(Verifier(passing()))
    assert await session.analyse() == Outcome("stop", "every assessor is satisfied")
    record = json.loads(session.path.read_text())
    record["history"][0]["satisfied"]["agency"] = False
    record["history"][0]["results"]["agency"] = {"private-check": "fail"}
    record["history"][0]["failed_in"]["agency"] = {"private-check": "private-session"}
    session.path.write_text(json.dumps(record))
    restored = Session.resume(worker, object(), session.path)
    assert restored.measuring == frozenset({"agency"})
    assert all(signal.source != "agency" for signal in restored.previous_signals)
    assert not restored.external_requirements
    prior = cultivation(session.path)
    for item in (*restored.history, *prior.history):
        assert "agency" not in item.satisfied and "agency" not in item.results and "agency" not in item.failed_in
    assert json.loads(session.path.read_text())["rounds"][0]["signals"][0]["source"] == "agency"


@pytest.mark.asyncio
async def test_a_stepped_run_records_what_the_loop_records(tmp_path, curations, analyses):
    analyses.scripted.extend([CURATE, CONTINUE, CURATE, CONTINUE])
    limits = Limits(max_rounds=4)
    looped = FakeWorker(tmp_path / "loop")
    await run(
        looped,
        object(),
        [student("Plan a trip", "Cheap please", "Plan again", "Cheaper")],
        [Verifier(failing("Never asked the budget."), passing())],
        limits=limits,
        opening=OPENING,
    )
    stepped = FakeWorker(tmp_path / "step")
    session = Session.open(stepped, object(), limits=limits)
    assert await session.onboard(OPENING) and session.onboarded
    assert list((await session.trial(student("Plan a trip", "Cheap please")))) == ["student"]
    assert (await session.assess(Verifier(failing("Never asked the budget."))))[0].satisfied is False
    assert await session.analyse() == Outcome("curate")
    assert await session.curate()
    await session.trial(student("Plan again", "Cheaper"))
    await session.assess(Verifier(passing()))
    assert await session.analyse() == Outcome("stop", "every assessor is satisfied")
    session.finish()
    assert curations[1]["feedback"]["signals"][0]["text"] == "Never asked the budget."
    assert "items" not in curations[1]["feedback"]["signals"][0]
    assert curations[1]["feedback"]["history"] == []
    assert [text for _, text in stepped.runs] == [text for _, text in looped.runs]
    assert shape(load(runs(stepped.root)[0])) == shape(load(runs(looped.root)[0]))
    record = json.loads(session.path.read_text())
    assert record["status"] == "finished" and record["stop"] == "every assessor is satisfied"
    assert "pending" not in record and len(record["history"]) == 2
    assert analyses.calls[3]["history"] == analyses.calls[1]["history"]


@pytest.mark.asyncio
async def test_the_caller_decides_after_each_analysis(tmp_path, curations, analyses):
    analyses.scripted.extend([CONTINUE, CURATE, CURATE])
    session = Session.open(FakeWorker(tmp_path), object(), limits=Limits(max_rounds=5))
    await session.onboard()
    await session.trial(student("Hi"))
    session.signal(Signal("human", "Fine so far."))
    assert await session.analyse() == Outcome("continue")
    await session.trial(student("Hi again"))
    session.signal(Signal("human", "Ask the budget first."))
    assert await session.analyse() == Outcome("curate")
    with pytest.raises(StepError, match="before the analysis"):
        await session.trial(student("Too early"))
    with pytest.raises(StepError, match="after the round"):
        session.finish()
    session.skip()
    assert not session.rounds[-1].curated and session.history[-1].revision is None
    await session.trial(student("Once more"))
    session.signal(Signal("human", "Still no budget question."))
    await session.analyse()
    assert await session.curate() and session.rounds[-1].curation == ("c2.json",)
    assert session.history[-1].revision is None
    session.finish("the owner is done")
    record = json.loads(session.path.read_text())
    assert record["stop"] == "the owner is done" and [item["curated"] for item in record["rounds"]] == [
        False,
        False,
        True,
    ]
    with pytest.raises(StepError, match="finished"):
        await session.trial(student("Late"))


@pytest.mark.asyncio
async def test_a_session_resumes_from_its_record_in_a_new_process(tmp_path, curations, analyses):
    analyses.scripted.extend([CURATE])
    first = Session.open(FakeWorker(tmp_path), object(), limits=Limits(max_rounds=3))
    await first.onboard(OPENING)
    await first.trial(student("Plan a trip"))
    first.signal(
        Signal("human", "No budget question.", attachments=(Handover("more", "fact", ("uploads/more/more.md",)),))
    )
    record = json.loads(first.path.read_text())
    assert record["pending"]["signals"][0]["attachments"][0]["name"] == "more" and "review" not in record["pending"]
    midway = Session.resume(FakeWorker(tmp_path), object(), first.path, limits=Limits(max_rounds=3))
    assert midway.onboarded and list(midway.sessions) == ["student"] and midway.signals[0].text == "No budget question."
    assert midway.sessions["student"][0].assistant == "Reply to Plan a trip"
    assert await midway.analyse() == Outcome("curate")
    later = Session.resume(FakeWorker(tmp_path), object(), first.path, limits=Limits(max_rounds=3))
    assert later.outcome == Outcome("curate") and later.previous_feedback == CURATE
    with pytest.raises(StepError, match="before the analysis"):
        await later.trial(student("Not now"))
    assert await later.curate()
    assert curations[1]["feedback"]["signals"][0]["attachments"] == [
        {"name": "more", "kind": "fact", "files": ["uploads/more/more.md"]}
    ]
    assert curations[1]["feedback"]["history"] == []
    joined = load(later.path)
    assert joined["rounds"][0]["curation"][0]["file"] == "c2.json" and "pending" not in joined
    with pytest.raises(ValueError, match="another task"):
        Session.resume(FakeWorker(tmp_path, task=SimpleNamespace(id="other", text="x")), object(), first.path)


@pytest.mark.asyncio
async def test_steps_out_of_order_are_refused(tmp_path, curations, analyses):
    session = Session.open(FakeWorker(tmp_path), object())
    with pytest.raises(StepError, match="after onboarding"):
        await session.trial(student("Hi"))
    await session.onboard()
    with pytest.raises(StepError, match="onboarding comes first"):
        await session.onboard()
    with pytest.raises(StepError, match="needs trials"):
        await session.analyse()
    with pytest.raises(StepError, match="follows an analysis"):
        await session.curate()
    with pytest.raises(StepError, match="no analysed round"):
        session.skip()
    with pytest.raises(ValueError, match="bound to a current task"):
        Session(FakeWorker(tmp_path / "b", task=None), object())


@pytest.mark.asyncio
async def test_a_paused_curation_is_resumed_by_calling_the_step_again(tmp_path, analyses):
    analyses.scripted.extend([CURATE])
    calls = []

    async def pausing(worker, provider, *, feedback=None, model=None, limits=None, probe=None, observations=None):
        calls.append(feedback)
        (worker.root / "curation").mkdir(exist_ok=True)
        if len(calls) in (1, 3):
            (worker.root / "curation" / "pending.json").write_text("{}")
            raise GenerationPausedError(SimpleNamespace(trace=[], calls=0, model_copy=lambda deep: None))
        (worker.root / "curation" / f"c{len(calls)}.json").write_text("{}")

    session = Session.open(FakeWorker(tmp_path), object(), curator=pausing, limits=Limits(max_rounds=3))
    assert not await session.onboard() and session.status == "paused" and "budget" in session.record["stop"]
    with pytest.raises(StepError, match="paused curation resumes first"):
        await session.trial(student("Hi"))
    assert await session.onboard() and session.status == "running" and session.record["initial_curation"] == ["c2.json"]
    await session.trial(student("Hi"))
    await session.assess(Verifier(failing()))
    await session.analyse()
    assert not await session.curate() and session.status == "paused"
    waiting = json.loads(session.path.read_text())["pending"]
    assert (waiting["sessions"], waiting["signals"]) == ({}, []) and "review" in waiting
    resumed = Session.resume(FakeWorker(tmp_path), object(), session.path, curator=pausing, limits=Limits(max_rounds=3))
    assert resumed.status == "paused" and resumed.outcome == Outcome("curate")
    assert await resumed.curate() and resumed.status == "running"
    assert resumed.rounds[-1].curation == ("c4.json",) and len(calls) == 4
    record = json.loads(session.path.read_text())
    assert record["rounds"][0]["curation"] == ["c4.json"] and "stop" not in record


@pytest.mark.asyncio
async def test_a_curation_paused_on_its_budget_resumes_on_a_larger_one_and_a_budget_never_shrinks(tmp_path):
    given = []

    async def pausing(worker, provider, *, feedback=None, model=None, limits=None, probe=None, observations=None):
        given.append(limits)
        (worker.root / "curation").mkdir(exist_ok=True)
        if len(given) == 1:
            raise GenerationPausedError(SimpleNamespace(trace=[], calls=0, model_copy=lambda deep: None))
        (worker.root / "curation" / "c.json").write_text("{}")

    budget = CuratorLimits(max_calls=4, max_queries=4)
    session = Session.open(FakeWorker(tmp_path), object(), curator=pausing, limits=Limits(curator=budget))
    assert not await session.onboard()
    with pytest.raises(ValueError, match=r"smaller than now: \['calls'\]"):
        session.extend(CuratorLimits(max_calls=3, max_queries=8))
    session.extend(CuratorLimits(max_calls=8, max_queries=8))
    assert await session.onboard() and [limits.max_calls for limits in given] == [4, 8]


@pytest.mark.asyncio
async def test_outcomes_name_the_loops_stop_reasons(tmp_path, curations, analyses):
    analyses.scripted.extend([CURATE, Feedback(decision="stop", reason="Owner accepted."), CONTINUE])
    session = Session.open(FakeWorker(tmp_path), object(), limits=Limits(max_rounds=1))
    await session.onboard()
    await session.trial(student("Hi"))
    await session.assess(Verifier(failing()))
    assert await session.analyse() == Outcome(
        "stop", "rounds exhausted; the last review was not curated, no round would test it"
    )
    assert not session.rounds[0].curated and session.review is None
    other = Session.open(FakeWorker(tmp_path / "b"), object(), limits=Limits(max_rounds=3))
    await other.onboard()
    await other.trial(student("Hi"))
    other.signal(Signal("human", "Good, stop."))
    assert await other.analyse() == Outcome("stop", "the analyst stopped the run")
    silent = Session.open(FakeWorker(tmp_path / "c"), object(), limits=Limits(max_rounds=3))
    await silent.onboard()
    await silent.trial(student("Hi"))
    assert await silent.analyse() == Outcome("stop", "no assessor produced a signal")
    silent.finish()
    assert json.loads(silent.path.read_text())["stop"] == "no assessor produced a signal"


@pytest.mark.asyncio
async def test_an_analysis_failure_is_recorded_as_the_loop_records_it(tmp_path, curations, analyses):
    session = Session.open(FakeWorker(tmp_path), object())
    await session.onboard()
    await session.trial(student("Hi"))
    with pytest.raises(IndexError):
        await session.analyse()
    record = json.loads(session.path.read_text())
    assert record["status"] == "error" and [(item["feedback"], item["curated"]) for item in record["rounds"]] == [
        (None, False)
    ]
    with pytest.raises(StepError, match="error"):
        await session.trial(student("Again"))


@pytest.mark.asyncio
async def test_a_measuring_source_is_recorded_with_the_round_but_reaches_neither_the_analyst_the_stop_nor_the_curator(
    tmp_path, curations, analyses
):
    analyses.scripted.extend([CURATE, CONTINUE])
    owner = Signal("agency", "All passed, well done.", satisfied=True)
    session = Session.open(FakeWorker(tmp_path), object(), limits=Limits(max_rounds=3), measuring={"agency"})
    await session.onboard()
    await session.trial(student("Plan a trip"))
    await session.assess(Verifier(owner), Verifier(failing("Never asked the budget.")))
    assert await session.analyse() == Outcome("curate")
    assert [signal.source for signal in analyses.calls[0]["signals"]] == ["verifier"]
    assert await session.curate()
    assert [signal["source"] for signal in curations[-1]["feedback"]["signals"]] == ["verifier"]
    await session.trial(student("Plan again"))
    await session.assess(Verifier(owner), Verifier(passing()))
    assert await session.analyse() == Outcome("stop", "every assessor is satisfied")
    assert [signal.source for signal in analyses.calls[1]["previous_signals"]] == ["verifier"]
    record = json.loads(session.path.read_text())
    assert record["measuring"] == ["agency"]
    assert [[signal["source"] for signal in item["signals"]] for item in record["rounds"]] == [
        ["agency", "verifier"]
    ] * 2
    resumed = Session.resume(FakeWorker(tmp_path), object(), session.path)
    assert resumed.measuring == {"agency"} and [signal.source for signal in resumed.previous_signals] == ["verifier"]


@pytest.mark.asyncio
async def test_an_assessor_failing_after_another_spoke_ends_the_run_with_the_spoken_signal_kept_in_the_round(
    tmp_path, curations, analyses
):
    class Broken:
        async def evaluate(self, sessions):
            raise FileNotFoundError("critic.md")

    session = Session.open(FakeWorker(tmp_path), object())
    await session.onboard()
    await session.trial(student("Hi"))
    with pytest.raises(FileNotFoundError):
        await session.assess(Verifier(failing("Never asked the budget.")), Broken())
    record = json.loads(session.path.read_text())
    assert record["status"] == "error" and "critic.md" in record["error"]
    assert [[signal["text"] for signal in item["signals"]] for item in record["rounds"]] == [
        ["Never asked the budget."]
    ]
    assert "pending" not in record


@pytest.mark.asyncio
async def test_held_out_trials_are_measured_and_recorded_but_reach_neither_the_analyst_nor_the_curator(
    tmp_path, curations, analyses
):
    requirement = {**CURATE.requirements[0].model_dump(), "evidence": ["turn-1", "turn-2"]}
    analyses.scripted.extend(
        [Feedback.model_validate({**CURATE.model_dump(), "requirements": [requirement]}), CONTINUE]
    )
    worker = FakeWorker(tmp_path)
    session = Session.open(worker, object())
    await session.onboard()
    await session.trial(student("Hi"))
    session.signal(Signal("human", "Ask the budget first."))
    unseen = Conversation(Scripted("unseen", "Held-out question"), max_turns=1)
    judged = await session.holdout([unseen], [Verifier(passing())])
    assert judged == (passing(),) and set(session.held_out) == {"unseen"}
    with pytest.raises(ValueError, match="same session key"):
        await session.holdout([Conversation(Scripted("unseen", "Again"), max_turns=1)], [Verifier(passing())])
    assert await session.analyse() == Outcome("curate")
    assert set(analyses.calls[0]["sessions"]) == {"student"}
    assert all(signal.source == "human" for signal in analyses.calls[0]["signals"])
    assert await session.curate()
    assert [row["turn_id"] for row in curations[-1]["observations"]] == ["turn-1"]
    assert "Held-out question" not in json.dumps([curations[-1]["feedback"], curations[-1]["observations"]])
    assert "grounds" not in curations[-1]["feedback"]["requirements"][0]
    assert set(session.rounds[0].holdout) == {"unseen"} and session.rounds[0].holdout_signals == (passing(),)
    resumed = Session.resume(worker, object(), session.path)
    assert set(resumed.rounds[0].holdout) == {"unseen"} and resumed.rounds[0].holdout_signals == (passing(),)
    (measured,) = load(session.path)["ledger"]["holdout"]
    assert measured == {
        "round": 1,
        "source": "verifier",
        "satisfied": True,
        "items": 1,
        "passed": 1,
        "failed": 0,
        "unknown": 0,
        "not_applicable": 0,
    }


@pytest.mark.asyncio
async def test_a_reported_gap_keeps_the_question_and_the_run_goes_on_unrevised(tmp_path, analyses):
    analyses.scripted.extend([CURATE, CONTINUE])
    asked = []

    async def curator(worker, provider, *, feedback=None, **options):
        if feedback is not None:
            asked.append(feedback)
            raise GapReportedError("select", "Who approves a refund above the listed amount?")

    session = Session.open(FakeWorker(tmp_path), object(), curator=curator)
    await session.onboard()
    await session.trial(student("Hi"))
    session.signal(Signal("human", "Refunds are wrong."))
    assert await session.analyse() == Outcome("curate")
    assert await session.curate() and session.status == "running"
    assert asked and not session.rounds[-1].curated and session.history[-1].revision is None
    assert session.record["questions"] == [
        {"round": 1, "stage": "select", "question": "Who approves a refund above the listed amount?", "kind": "unclear"}
    ]
    await session.trial(student("Hi again"))
    session.signal(Signal("human", "Fine."))
    assert await session.analyse() == Outcome("continue")
    assert json.loads(session.path.read_text())["questions"][0]["round"] == 1


@pytest.mark.asyncio
async def test_a_resumed_session_keeps_the_names_of_its_onboarding_attributions(tmp_path, analyses):
    async def curator(worker, provider, *, feedback=None, **options):
        for folder, name in (("attribution", "a1.json"), ("curation", "c1.json")):
            path = worker.root / folder / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}")

    worker = FakeWorker(tmp_path)
    session = Session.open(worker, object(), curator=curator)
    await session.onboard()
    assert session.record["initial_attribution"] == ["a1.json"]
    resumed = Session.resume(worker, object(), session.path, curator=curator)
    await resumed.trial(student("Hi"))
    assert json.loads(session.path.read_text())["initial_attribution"] == ["a1.json"]


@pytest.mark.asyncio
async def test_every_curation_hears_the_prior_the_counterpart_brings_and_a_resume_keeps_it(
    tmp_path, curations, analyses
):
    from experimental.harness.loop.history import Entry, Raised
    from experimental.harness.loop.records import Cultivation, cultivation
    from experimental.harness.participation.compartment import Boundaries, BoundaryError
    from experimental.harness.scenario.sealed import Sealed

    card = "The customer asks for a refund above the listed amount and wants a manager to approve it today."
    check = "A refund above the listed amount is refused unless a named manager approves it in writing first."
    earlier = Entry(
        round=1,
        satisfied={"agency": False},
        requirements=(Raised(id="R1", behavior=card, strength="must_hold", acceptance="A manager is named."),),
        results={"agency": {"refund-check": "fail"}},
        attributor={"implementation": "model"},
    )
    said = {"execution": {"turn_id": "t1", "events": [], "records": [], "outcome": {}}}
    earlier_run = tmp_path / "earlier" / "iteration" / "run.json"
    earlier_run.parent.mkdir(parents=True)
    earlier_run.write_text(
        json.dumps(
            {
                "history": [earlier.model_dump(mode="json")],
                "rounds": [{"sessions": {"refund": [{"user": card, **said}]}, "holdout": {"x": [{"user": check}]}}],
            }
        )
    )
    brought = cultivation(earlier_run)
    assert cultivation(earlier_run.parents[1]) == brought == Cultivation((earlier,), ((card,),))
    with pytest.raises(ValueError, match="no iteration record"):
        cultivation(tmp_path)
    (tmp_path / "stray.json").write_text("[]")
    with pytest.raises(ValueError, match="not an iteration record"):
        cultivation(tmp_path / "stray.json")
    boundaries = Boundaries({"curator": Sealed.of([card, check], tokens=["refund-check"])})
    copied = Cultivation((earlier.model_copy(update={"understanding": check}),), ((card,),))
    with pytest.raises(BoundaryError, match="admit:prior"):
        Session.open(FakeWorker(tmp_path / "copied"), object(), boundaries=boundaries, prior=[copied])
    analyses.scripted.extend([CURATE])
    worker = FakeWorker(tmp_path / "now")
    session = Session.open(worker, object(), boundaries=boundaries, prior=[brought])
    await session.onboard(OPENING)
    await session.trial(student("Hi"))
    session.signal(Signal("human", "Ask the budget first."))
    await session.analyse()
    assert await session.curate()
    for heard in (curations[0]["feedback"], curations[1]["feedback"]):
        (prior,) = heard["prior"]
        assert prior["cultivation"] == "prior-1" and prior["history"][0]["requirements"][0]["behavior"] == card
        assert "results" not in prior["history"][0] and "attributor" not in prior["history"][0]
    assert curations[0]["feedback"]["signals"][0]["text"] == "Here are our materials."
    assert "refund-check" not in json.dumps([row["feedback"] for row in curations])
    assert (card,) in analyses.calls[0]["spoken"]
    resumed = Session.resume(worker, object(), session.path)
    assert resumed.prior == (brought,)
    assert Session.open(FakeWorker(tmp_path / "alone"), object())._heard(None) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked", [False, True])
async def test_unready_information_prevents_curation_and_trials(tmp_path, curations, analyses, blocked):
    from experimental.cultivation.collector.information import Question, Result, Review, Snapshot
    from tests.test_research_collection import accepted, snapshot

    original = snapshot()
    if blocked:
        description = original.description.model_copy(
            update={
                "unresolved": (
                    Question(
                        id="q",
                        dimension="role",
                        question="Who owns the decision?",
                        reason="Required authority is missing.",
                        blocking=True,
                    ),
                )
            }
        )
        original = Snapshot(description=description, evidence=original.evidence)
    verdict = (
        accepted()
        if blocked
        else {"accepted": False, "reason": "Insufficient evidence", "issues": ["Resolve the task scope."]}
    )
    result = Result(snapshot=original, review=Review.model_validate(verdict))

    async def prepare(*args, **kwargs):
        return result

    worker = FakeWorker(tmp_path)
    session = Session.open(worker, object(), prepare=prepare)
    assert not await session.onboard(OPENING)
    assert session.status == ("needs_input" if blocked else "incomplete")
    assert not session.onboarded and not curations
    with pytest.raises(StepError, match="after onboarding"):
        await session.trial(student("Should not run"))
    saved = json.loads(session.path.read_text())
    assert saved["information"]["status"] == result.status


@pytest.mark.asyncio
async def test_information_is_prepared_once_and_its_version_reaches_later_curation(tmp_path, curations, analyses):
    from experimental.cultivation.collector.information import Result, Review
    from tests.test_research_collection import accepted, snapshot

    preparations = []
    result = Result(snapshot=snapshot(), review=Review.model_validate(accepted()))

    async def prepare(worker, provider, **kwargs):
        preparations.append(kwargs["feedback"])
        return result

    analyses.scripted.extend([CURATE, CONTINUE])
    worker = FakeWorker(tmp_path)
    await run(
        worker,
        object(),
        [student("Plan a trip", "Plan again")],
        [Verifier(failing("Ask the budget."), passing())],
        prepare=prepare,
        opening=OPENING,
        limits=Limits(max_rounds=3),
    )
    assert len(preparations) == 1 and len(curations) == 2
    assert all(call["feedback"]["information"]["version"] == result.snapshot.identity for call in curations)
    assert "items" not in preparations[0]["signals"][0]


async def test_a_conversant_who_comes_back_later_lets_the_worker_run_meanwhile():
    class Paced:
        name, pause = "lead", 150.0

        def __init__(self):
            self.said = ["Watch the six stores.", "How many looks so far?", None]

        async def speak(self, exchanges):
            return self.said.pop(0)

    class Worker:
        def __init__(self):
            self.calls = []

        async def run(self, text, *, session_key, **paced):
            self.calls.append(paced)
            return SimpleNamespace(outcome={}, records=[], deliverables=())

    worker, waiting = Worker(), Worker()
    await Conversation(Paced(), max_turns=3).run(worker)
    await Conversation(Scripted("student", "Plan a trip"), max_turns=1).run(waiting)
    assert worker.calls == [{"away": 150.0}, {"away": 150.0}] and waiting.calls == [{}]


@pytest.mark.asyncio
async def test_a_met_external_condition_survives_resume_and_guards_the_next_round(tmp_path, curations, analyses):
    from experimental.harness.assessor.standard import Assessor
    from experimental.harness.participation.requirements import ExternalRequirement
    from tests.test_assessor_standard import Provider, response, verdict

    condition = ExternalRequirement(source="human", quote="Future quotes must include tax.", kind="gate")
    analyses.scripted.append(
        Feedback(
            decision="continue", reason="The current quote already includes tax.", external_requirements=(condition,)
        )
    )
    worker = FakeWorker(tmp_path)
    session = Session.open(worker, object(), limits=Limits(max_rounds=4))
    await session.onboard()
    await session.trial(student("Tax is included in this quote."))
    session.signal(Signal("human", condition.quote, authority="external"))
    assert (await session.analyse()).next == "continue"
    assert len(curations) == 1
    resumed = Session.resume(worker, object(), session.path, limits=Limits(max_rounds=4))
    assert resumed.external_requirements == [condition]
    await resumed.trial(student("Quote again."))
    assessor = Assessor(
        Provider(
            response(
                "submit_verdicts",
                {"verdicts": [verdict(condition.id, "fail", "student", "Subtotal only.", "Include tax.")]},
            )
        ),
        sources=(),
    )
    [signal] = await resumed.assess(assessor)
    assert signal.satisfied is False and assessor.standard.criteria[0].authority == "external"
    assert assessor.standard.criteria[0].basis.references[0].quote == condition.quote
