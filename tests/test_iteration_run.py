"""Rounds alternate trial, evaluation, analysis and curation, and stop for the declared reasons."""

import json
from types import SimpleNamespace

import pytest

from experimental.analyst import role
from experimental.analyst.feedback import Feedback
from experimental.assessor.dataset import Case, Dataset, contains
from experimental.assessor.human import Human
from experimental.curator.generation.run import GenerationPausedError
from experimental.curator.generation.run import Limits as CuratorLimits
from experimental.curator.harness import Attributed, Attribution, Diagnosis, Task
from experimental.curator.raven_adapter.worker import Execution, TurnTimeoutError
from experimental.iteration import session as stepping
from experimental.iteration.conversation import Conversation
from experimental.iteration.hearing import opaque
from experimental.iteration.history import Diagnosed, Raised
from experimental.iteration.protocols import Exchange, Handover, Item, Signal
from experimental.iteration.records import load, runs
from experimental.iteration.run import run
from experimental.iteration.session import Limits, satisfied, trial_sessions


class FakeWorker:
    def __init__(self, root, task=Task(text="Serve the agency's travellers")):
        self.baseline = SimpleNamespace(task=task)
        self.root = root
        self.last_plan = None
        self.artifact_id = "artifact-0"
        self.runs = []

    async def run(self, text, *, session_key):
        self.runs.append((session_key, text))
        records = [{"kind": "runner.event", "event_type": "Text", "event": {"content": f"Reply to {text}"}}]
        return Execution(f"turn-{len(self.runs)}", [], records, {}, self.artifact_id)


class Scripted:
    def __init__(self, name, *messages):
        self.name, self.messages = name, list(messages)

    async def speak(self, exchanges):
        return self.messages.pop(0) if self.messages else None


class Verifier:
    def __init__(self, *rounds):
        self.rounds = list(rounds)

    async def evaluate(self, sessions):
        return self.rounds.pop(0)


def failing(text=""):
    return Signal(
        "verifier", text, items=(Item("asks budget", "fail", "student", note="Reply to Plan"),), satisfied=False
    )


def passing():
    return Signal("verifier", items=(Item("asks budget", "pass", "student"),), satisfied=True)


REQUIREMENT = {
    "behavior": "Ask for the budget before recommending.",
    "observed": "Turn turn-1 recommended without asking.",
    "evidence": ["turn-1"],
    "expectation": "new",
    "acceptance": "The first recommendation follows a budget question.",
    "strength": "must_hold",
}
CURATE = Feedback(decision="curate", reason="Intake gap.", requirements=(REQUIREMENT,))
CONTINUE = Feedback(decision="continue", reason="Every evaluator is satisfied and none added a remark.")


@pytest.fixture
def curations(monkeypatch):
    calls = []

    async def improve(worker, provider, *, feedback=None, model=None, limits=None, probe=None, observations=None):
        calls.append({"feedback": feedback, "model": model, "limits": limits, "observations": observations})
        worker.artifact_id = f"artifact-{len(calls)}"
        worker.last_attribution = Attributed(
            attribution=Attribution(diagnoses=(Diagnosis(about="task", state="absent", evidence=("task",)),)),
            identity={"implementation": "model"},
        )
        path = worker.root / "curation" / f"c{len(calls)}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"feedback": feedback, "active_artifact_id": worker.artifact_id}))

    monkeypatch.setattr(stepping, "improve", improve)
    return calls


@pytest.fixture
def analyses(monkeypatch):
    calls, scripted = [], []

    async def analyse(
        worker,
        provider,
        signals,
        sessions,
        *,
        previous_signals,
        previous_feedback,
        history,
        model,
        limits,
        sealed=None,
        spoken=None,
    ):
        calls.append(
            {
                "signals": signals,
                "previous_signals": previous_signals,
                "previous": previous_feedback,
                "history": history,
                "model": model,
                "sessions": sessions,
                "spoken": spoken,
            }
        )
        feedback = scripted.pop(0)
        path = worker.root / "analysis" / f"a{len(calls)}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"feedback": feedback.model_dump(mode="json")}))
        return feedback

    monkeypatch.setattr(role, "analyse", analyse)
    return SimpleNamespace(calls=calls, scripted=scripted)


@pytest.mark.asyncio
async def test_curate_reaches_improve_with_the_signals_and_the_next_round_runs_on_the_revision(
    tmp_path, curations, analyses
):
    worker = FakeWorker(tmp_path)
    student = Conversation(Scripted("student", "Plan a trip", "Cheap please", "Plan again"), max_turns=2)
    analyses.scripted.extend([CURATE, CONTINUE])
    limits = Limits(max_rounds=4, curator=CuratorLimits(call_timeout=7))
    rounds = await run(
        worker,
        provider=object(),
        trials=[student],
        assessors=[Verifier(failing("Never asked the budget."), passing())],
        model="analyst",
        curator_model="curator",
        limits=limits,
    )
    assert [row["feedback"] is None for row in curations] == [True, False]
    assert curations[1]["feedback"]["decision"] == "curate" and curations[1]["model"] == "curator"
    assert curations[0]["limits"] is curations[1]["limits"] is limits.curator
    assert curations[1]["feedback"]["signals"][0]["text"] == "Never asked the budget."
    assert curations[1]["feedback"]["signals"][0]["satisfied"] is False
    assert "items" not in curations[1]["feedback"]["signals"][0]
    assert [text for _, text in worker.runs] == ["Plan a trip", "Cheap please", "Plan again"]
    keys = [key for key, _ in worker.runs]
    assert all(key.startswith(f"curator:{opaque('student')}:") for key in keys)
    assert keys[0] == keys[1] != keys[2]
    assert [item.curated for item in rounds] == [True, False]
    assert rounds[1].sessions["student"][0].execution.artifact_id == "artifact-2"
    assert rounds[0].sessions["student"][1].assistant == "Reply to Cheap please"
    assert analyses.calls[0]["previous"] is None and analyses.calls[1]["previous"] is CURATE
    assert analyses.calls[0]["previous_signals"] == () and analyses.calls[1]["previous_signals"] == rounds[0].signals
    assert analyses.calls[0]["model"] == "analyst"
    assert analyses.calls[0]["history"] == () and curations[1]["feedback"]["history"] == []
    earlier = analyses.calls[1]["history"][0]
    assert earlier.round == 1 and "fail" in earlier.results["verifier"].values()
    assert earlier.requirements == (
        Raised(id="", behavior=REQUIREMENT["behavior"], strength="must_hold", acceptance=REQUIREMENT["acceptance"]),
    )
    assert earlier.diagnoses == (Diagnosed(about="task", state="absent"),)
    record = json.loads(next((tmp_path / "iteration").glob("*.json")).read_text())
    assert record["task"] == "Serve the agency's travellers" and len(record["rounds"]) == 2
    assert record["status"] == "finished"
    assert record["rounds"][0]["signals"][0]["items"][0]["result"] == "fail"
    joined = load(runs(tmp_path)[0])
    first, second = joined["rounds"]
    exchange = first["sessions"]["student"][0]
    assert exchange["user"] == "Plan a trip"
    assert exchange["execution"]["records"][0]["event"]["content"] == "Reply to Plan a trip"
    item = first["signals"][0]["items"][0]
    assert (item["id"], item["result"], item["session"]) == ("asks budget", "fail", "student")
    assert first["feedback"]["requirements"][0]["behavior"] == REQUIREMENT["behavior"]
    assert joined["initial_curation"][0]["active_artifact_id"] == "artifact-1"
    assert first["curation"][0]["active_artifact_id"] == "artifact-2"
    assert [round_["signals"][0]["items"][0]["result"] for round_ in (first, second)] == ["fail", "pass"]
    assert second["feedback"]["decision"] == "continue" and second["curation"] == []
    assert record["initial_curation"] == ["c1.json"]
    assert [(item["analysis"], item["curation"]) for item in record["rounds"]] == [
        (["a1.json"], ["c2.json"]),
        (["a2.json"], []),
    ]
    joined = load(runs(tmp_path)[0])
    assert joined["initial_curation"][0]["file"] == "c1.json" and joined["initial_curation"][0]["feedback"] is None
    assert joined["rounds"][0]["curation"][0]["feedback"]["decision"] == "curate"
    assert joined["rounds"][0]["analysis"][0]["feedback"]["reason"] == "Intake gap."
    assert joined["rounds"][1]["curation"] == []


@pytest.mark.asyncio
async def test_a_turn_past_the_time_limit_ends_its_conversation_and_is_kept(tmp_path):
    class Slow(FakeWorker):
        async def run(self, text, *, session_key):
            if self.runs:
                late = Execution("turn-late", [], [], {"timed_out": True, "timeout": 600, "explicit_reply": False})
                raise TurnTimeoutError("worker timed out after 600s during the operation", [], late)
            return await super().run(text, session_key=session_key)

    student = Conversation(Scripted("student", "Plan a trip", "Cheaper?", "Thanks"), max_turns=3)
    (exchanges,) = (await student.run(Slow(tmp_path))).values()
    assert [exchange.user for exchange in exchanges] == ["Plan a trip", "Cheaper?"]
    assert exchanges[-1].execution.outcome["timed_out"] and exchanges[-1].assistant == ""


@pytest.mark.asyncio
async def test_a_dataset_is_both_trial_and_evaluator_and_scores_pass_rate(tmp_path, curations, analyses):
    worker = FakeWorker(tmp_path)
    dataset = Dataset(
        [Case("1", "What is 2+2?", "Reply to What is 2+2?"), Case("2", "Capital of France?", "Paris")],
        threshold=0.5,
    )
    analyses.scripted.append(CONTINUE)
    rounds = await run(worker, object(), [dataset], [dataset], limits=Limits(max_rounds=3))
    assert [(key.rsplit(":", 1)[0], text) for key, text in worker.runs] == [
        ("case:1", "What is 2+2?"),
        ("case:2", "Capital of France?"),
    ]
    assert len({key.rsplit(":", 1)[1] for key, _ in worker.runs}) == 1
    (signal,) = rounds[0].signals
    assert signal.metrics == {"pass_rate": 0.5} and signal.satisfied is True
    assert [(item.id, item.result) for item in signal.items] == [("1", "pass"), ("2", "fail")]
    assert signal.items[1].expected == "Paris" and signal.items[1].actual == "Reply to Capital of France?"
    assert len(rounds) == 1 and not rounds[0].curated
    strict = Dataset(dataset.cases, score=contains, threshold=1.0)
    assert (await strict.evaluate({"case:1": [Exchange("q", Execution("t", [], [], {}))]})).items[1].result == "unknown"
    scored = Dataset(dataset.cases, score=lambda actual, expected: 0.25)
    assert (await scored.evaluate(await scored.run(FakeWorker(tmp_path / "s")))).metrics == {"pass_rate": 0.25}
    for bad in (
        {"cases": []},
        {"cases": [Case("1", "a", "b"), Case("1", "c", "d")]},
        {"cases": dataset.cases, "threshold": 2},
    ):
        with pytest.raises(ValueError):
            Dataset(**bad)


@pytest.mark.asyncio
async def test_rounds_stop_when_the_analyst_says_stop_or_no_evaluator_speaks(tmp_path, curations, analyses):
    worker = FakeWorker(tmp_path)
    analyses.scripted.append(Feedback(decision="stop", reason="Owner accepted."))
    human_round = Verifier(Signal("human", "Good, stop."))
    rounds = await run(worker, object(), [Conversation(Scripted("user", "Hi"))], [human_round])
    assert len(rounds) == 1 and not rounds[0].curated and len(curations) == 1
    analyses.scripted.append(CONTINUE)
    rounds = await run(FakeWorker(tmp_path / "b"), object(), [Conversation(Scripted("user", "Hi"))], [Verifier(None)])
    assert len(rounds) == 1 and rounds[0].signals == ()


@pytest.mark.asyncio
async def test_round_budget_caps_an_unsatisfied_loop_and_errors_are_recorded(tmp_path, curations, analyses):
    worker = FakeWorker(tmp_path)
    analyses.scripted.extend([CURATE, CURATE])
    trial = Conversation(Scripted("s", "a", "b"))
    rounds = await run(worker, object(), [trial], [Verifier(failing(), failing())], limits=Limits(max_rounds=2))
    assert len(rounds) == 2 and len(curations) == 2 and [item.curated for item in rounds] == [True, False]
    with pytest.raises(ValueError, match="bound to a current task"):
        await run(FakeWorker(tmp_path / "c", task=None), object(), [], [])
    broken = FakeWorker(tmp_path / "d")
    with pytest.raises(IndexError):
        await run(broken, object(), [Conversation(Scripted("s", "a"))], [Verifier()])
    record = json.loads(next((broken.root / "iteration").glob("*.json")).read_text())
    assert record["status"] == "error" and "error" in record
    assert [(item["feedback"], item["curated"]) for item in record["rounds"]] == [(None, False)]
    (name,) = record["initial_curation"]
    (broken.root / "curation" / name).unlink()
    assert load(runs(broken.root)[0])["initial_curation"] == [{"missing": name}]
    assert runs(tmp_path / "nowhere") == []


@pytest.mark.asyncio
async def test_trials_conversations_and_limits_hold_their_bounds(tmp_path):
    worker = FakeWorker(tmp_path)
    assert len((await Conversation(Scripted("s", "a", "b", "c"), max_turns=2).run(worker))["s"]) == 2
    assert len((await Conversation(Scripted("s", "a"), max_turns=5).run(worker))["s"]) == 1
    with pytest.raises(ValueError, match="same session key"):
        await trial_sessions(worker, [Conversation(Scripted("s", "a")), Conversation(Scripted("s", "b"))])
    assert not satisfied(()) and not satisfied((Signal("h", "x"),)) and not satisfied((passing(), Signal("h", "x")))
    assert satisfied((passing(),)) and not satisfied((passing(), failing()))
    with pytest.raises(ValueError, match="positive integer"):
        Limits(max_rounds=0)
    with pytest.raises(ValueError, match="positive turn budget"):
        Conversation(Scripted("s"), max_turns=0)


@pytest.mark.asyncio
async def test_human_shows_the_reply_and_maps_terminal_input_to_the_protocols():
    answers = iter(["", "  Hello  ", "/done", "Ask budget first.", ""])
    shown = []
    human = Human(ask=lambda label: next(answers), show=shown.append)
    execution = Execution(
        "t",
        [],
        [
            {"kind": "runner.event", "event_type": "Text", "event": {"content": "Hi!"}},
            {"kind": "tool.error", "error": "boom"},
        ],
        {},
    )
    assert await human.speak([Exchange("hey", execution)]) == "  Hello  "
    assert shown == ["Hi!", "Execution issue: boom"]
    assert await human.speak([]) is None
    assert await human.evaluate({}) == Signal("human", "Ask budget first.")
    assert await human.evaluate({}) is None

    def eof(label):
        raise EOFError

    assert await Human(ask=eof).speak([]) is None and await Human(ask=eof).evaluate({}) is None


@pytest.mark.asyncio
async def test_an_opening_reaches_the_first_curation_and_the_record(tmp_path, curations, analyses):
    worker = FakeWorker(tmp_path)
    student = Conversation(Scripted("student", "Plan a trip"), max_turns=1)
    analyses.scripted.append(CONTINUE)
    opening = Signal(
        "agency", "Here are our materials.", attachments=(Handover("sop", "norm", ("uploads/sop/sop.md",)),)
    )
    await run(
        worker,
        provider=object(),
        trials=[student],
        assessors=[Verifier(passing())],
        limits=Limits(max_rounds=1),
        opening=(opening,),
    )
    assert curations[0]["feedback"] == {
        "signals": [
            {
                "source": "agency",
                "text": "Here are our materials.",
                "satisfied": None,
                "attachments": [{"name": "sop", "kind": "norm", "files": ["uploads/sop/sop.md"]}],
            }
        ]
    }
    record = json.loads(next((tmp_path / "iteration").glob("*.json")).read_text())
    assert record["opening"][0]["attachments"] == [{"name": "sop", "kind": "norm", "files": ["uploads/sop/sop.md"]}]


@pytest.mark.asyncio
async def test_a_supplied_curator_replaces_improve(tmp_path, curations, analyses):
    async def keep(worker, provider, *, feedback=None, model=None, limits=None, probe=None, observations=None):
        return None

    worker = FakeWorker(tmp_path)
    analyses.scripted.extend([CURATE, CONTINUE])
    rounds = await run(
        worker,
        provider=object(),
        trials=[Conversation(Scripted("student", "Plan a trip"), max_turns=1)],
        assessors=[Verifier(failing("No budget question."), passing())],
        curator=keep,
        limits=Limits(max_rounds=3),
    )
    assert curations == [] and [item.curated for item in rounds] == [True, False]
    assert worker.artifact_id == "artifact-0" and not (tmp_path / "curation").exists()
    record = json.loads(next((tmp_path / "iteration").glob("*.json")).read_text())
    assert record["curator"] == "keep" and record["initial_curation"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", [False, True])
async def test_a_round_is_recorded_before_its_curation_and_a_paused_curator_leaves_the_run_resumable(
    tmp_path, curations, analyses, transport
):
    worker = FakeWorker(tmp_path)
    analyses.scripted.extend([CURATE])
    calls = []

    async def pausing(worker, provider, *, feedback=None, model=None, limits=None, probe=None, observations=None):
        calls.append(feedback)
        if feedback is not None:
            (worker.root / "curation").mkdir(exist_ok=True)
            (worker.root / "curation" / "pending.json").write_text("{}")
            state = SimpleNamespace(trace=[], calls=0, model_copy=lambda deep: None)
            if transport:
                from experimental.curator.generation.run import GenerationInterruptedError

                raise GenerationInterruptedError("provider unavailable", state)
            raise GenerationPausedError(state)

    rounds = await run(
        worker,
        provider=object(),
        trials=[Conversation(Scripted("student", "Plan a trip"), max_turns=1)],
        assessors=[Verifier(failing("No budget question."))],
        curator=pausing,
        limits=Limits(max_rounds=3),
    )
    assert len(calls) == 2 and len(rounds) == 1 and rounds[0].curated and rounds[0].curation == ()
    record = json.loads(next((tmp_path / "iteration").glob("*.json")).read_text())
    assert record["status"] == "paused" and len(record["rounds"]) == 1
    assert ("provider" if transport else "budget") in record["stop"]
    assert record["rounds"][0]["signals"][0]["text"] == "No budget question."


@pytest.mark.asyncio
async def test_the_last_review_is_not_curated_and_the_stop_reason_says_so(tmp_path, curations, analyses):
    worker = FakeWorker(tmp_path)
    analyses.scripted.extend([CURATE])
    await run(
        worker,
        provider=object(),
        trials=[Conversation(Scripted("student", "Plan a trip"), max_turns=1)],
        assessors=[Verifier(failing())],
        limits=Limits(max_rounds=1),
    )
    record = json.loads(next((tmp_path / "iteration").glob("*.json")).read_text())
    assert record["status"] == "finished"
    assert record["stop"] == "rounds exhausted; the last review was not curated, no round would test it"
    assert record["rounds"][0]["curated"] is False and record["rounds"][0]["curation"] == []
    assert len(curations) == 1


@pytest.mark.asyncio
async def test_a_failed_analysis_still_records_the_round(tmp_path, curations, monkeypatch):
    async def analyse(*args, **kwargs):
        raise RuntimeError("analyst: submission budget exhausted")

    monkeypatch.setattr(role, "analyse", analyse)
    worker = FakeWorker(tmp_path)
    with pytest.raises(RuntimeError, match="budget"):
        await run(
            worker,
            provider=object(),
            trials=[Conversation(Scripted("student", "Plan a trip"), max_turns=1)],
            assessors=[Verifier(failing("No budget question."))],
        )
    record = json.loads(next((tmp_path / "iteration").glob("*.json")).read_text())
    assert record["status"] == "error" and len(record["rounds"]) == 1
    assert (
        record["rounds"][0]["feedback"] is None and record["rounds"][0]["signals"][0]["text"] == "No budget question."
    )
    assert load(runs(tmp_path)[0])["rounds"][0]["analysis"] == []


def test_loading_a_moved_run_finds_its_kept_deliverables_under_the_new_folder(tmp_path):
    root = tmp_path / "moved"
    (root / "iteration").mkdir(parents=True)
    kept = root / "replicas" / "1-session-ab12cd" / "deliverables" / "turn-2" / "trip.html"
    kept.parent.mkdir(parents=True)
    kept.write_text("<p>trip</p>")
    old = "/elsewhere/original/deliverables/turn-1/trip.html"
    copied = "/elsewhere/original/replicas/1-session-ab12cd/deliverables/turn-2/trip.html"
    execution = {"turn_id": "turn-1", "records": [], "artifact_id": "a", "deliverables": [old, copied]}
    record = {
        "task_id": "t",
        "task": "T",
        "rounds": [{"sessions": {"student": [{"user": "Hi", "execution": execution}]}}],
    }
    (root / "iteration" / "r.json").write_text(json.dumps(record))
    run = load(root / "iteration" / "r.json")
    assert run["rounds"][0]["sessions"]["student"][0]["execution"]["deliverables"] == [
        str(root / "deliverables" / "turn-1" / "trip.html"),
        str(kept),
    ]


@pytest.mark.asyncio
async def test_material_handed_over_with_a_review_reaches_the_curator_as_what_it_may_hear(tmp_path, curations):
    measured = (
        Signal(
            "owner",
            "Here is the brand guide.",
            items=(Item("brand", "fail", "student", expected="THE-REFERENCE"),),
            metrics={"pass_rate": 0.0},
            satisfied=False,
            attachments=(Handover("guide", "norm", ("uploads/guide/guide.md",)),),
        ),
    )

    class Owner:
        def __init__(self):
            self.reviews = [
                role.Review(Feedback(decision="supplement", reason="Waits on material.")),
                role.Review(Feedback(decision="stop", reason="All held.")),
            ]

        async def review(self, worker, sessions, signals, **context):
            return self.reviews.pop(0)

    rounds = await run(
        FakeWorker(tmp_path),
        object(),
        [Conversation(Scripted("student", "Hi", "Hi again"), max_turns=1)],
        [Verifier(*measured, *measured)],
        analyst=Owner(),
    )
    assert [item.curated for item in rounds] == [True, False] and len(curations) == 2
    feedback = curations[1]["feedback"]
    assert feedback["decision"] == "supplement" and feedback["requirements"] == []
    assert rounds[1].signals == measured and rounds[1].feedback.decision == "stop"
    assert feedback["signals"] == [
        {
            "source": "owner",
            "text": "Here is the brand guide.",
            "satisfied": False,
            "attachments": [{"name": "guide", "kind": "norm", "files": ["uploads/guide/guide.md"]}],
        }
    ]
    assert rounds[0].signals == measured


@pytest.mark.asyncio
async def test_the_curator_hears_each_rounds_verdict_but_never_the_criteria_it_was_measured_against(
    tmp_path, curations, analyses
):
    analyses.scripted.extend([CURATE, CURATE, CONTINUE])
    verifier = Verifier(failing(), failing(), passing())
    trial = Conversation(Scripted("student", "Hi", "Hi again", "Hi once more"), max_turns=1)
    await run(FakeWorker(tmp_path), object(), [trial], [verifier], limits=Limits(max_rounds=3))
    assert len(curations) == 3
    (earlier,) = [entry for entry in curations[2]["feedback"]["history"] if entry["round"] == 1]
    assert earlier["satisfied"] == {"verifier": False} and "results" not in earlier and "failed_in" not in earlier
    assert "asks budget" not in json.dumps(curations[2]["feedback"])
    assert analyses.calls[1]["history"][-1].results == {"verifier": {"asks budget": "fail"}}


@pytest.mark.asyncio
async def test_the_curator_never_receives_the_reference_answers_it_could_copy_into_the_harness(
    tmp_path, curations, analyses
):
    analyses.scripted.extend([CURATE, CONTINUE])
    dataset = Dataset([Case("capital", "Capital of France?", "PARIS-REFERENCE")], score=contains)
    reference = Signal(
        "verifier", "", items=(Item("asks", "fail", "s", expected="SECRET-EXPECTED", note="Say SECRET-NOTE"),)
    )
    verifier = Verifier(reference, reference)
    await run(FakeWorker(tmp_path), object(), [dataset], [dataset, verifier], limits=Limits(max_rounds=2))
    told = json.dumps({"feedback": curations[1]["feedback"], "observations": curations[1]["observations"]})
    assert "PARIS-REFERENCE" not in told and "SECRET-EXPECTED" not in told and "SECRET-NOTE" not in told
    assert analyses.calls[0]["signals"][0].items[0].expected == "PARIS-REFERENCE"
    observed = curations[1]["observations"]
    assert observed and observed[0]["source"] == "trial"
    assert observed[0]["turn_id"] == "turn-1" and observed[0]["artifact_id"] == "artifact-1"
    assert observed[0]["records"][0]["kind"] == "runner.event"
    assert {row["session"] for row in observed} == {opaque("case:capital")}
