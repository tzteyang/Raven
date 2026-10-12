"""The Studio's live sessions: the configuration, a session's process taking the loop's steps as the page asks for
them, and the server relaying those steps to it and serving what the session recorded."""

import asyncio
import json
import multiprocessing
import re
import shutil
import threading
import time
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from experimental.curator.generation.run import GenerationPausedError
from experimental.curator.harness import Task
from experimental.iteration import session as stepping
from experimental.simulation.scenario import BUNDLED
from experimental.webui import employ, session_host
from experimental.webui.live import Handle, Live, LiveConfig
from experimental.webui.serve import Handler
from experimental.webui.session_host import Host
from raven.config.schema import Config
from tests.test_iteration_run import CURATE, FakeWorker
from tests.test_iteration_run import analyses as analyses  # noqa: F401 -- the loop test's Analyst stand-in

TRAVEL = BUNDLED / "travel_agency"
SESSION = "live-20260929120000-abcdef"


class Employee(FakeWorker):
    """The employee as a session's process sees it: a baseline with a real configuration, started and closed."""

    def __init__(self, root, workdir, task):
        super().__init__(root, task)
        config = Config()
        config.agents.defaults.model = "deepseek/deepseek-flash"
        config.agents.defaults.reasoning_effort = "low"
        config.agents.defaults.workspace = str(root / "home")
        config.providers.deepseek.api_key = "placeholder"
        self.baseline = SimpleNamespace(task=task, config=config, workdir=workdir)
        self.started = self.closed = False
        self.seen = []

    @property
    def revision_id(self):
        return self.artifact_id

    async def run(self, text, *, session_key):
        self.seen.append(sorted(path.name for path in Path(self.baseline.workdir).rglob("*") if path.is_file()))
        return await super().run(text, session_key=session_key)

    async def start(self):
        self.started = True

    async def close(self):
        self.closed = True


class Together:
    """`employ.together` without processes: each trial on its own replica, one after another."""

    def __init__(self, trials, spawn, placed):
        self.trials, self.spawn, self.placed = trials, spawn, placed

    async def run(self, worker):
        sessions = {}
        for name, trial in self.trials.items():
            replica = self.spawn(worker, name)
            self.placed[name] = {"workdir": replica.baseline.workdir}
            sessions.update(await trial.run(replica))
        return sessions


async def no_question(provider, packet, *, model, effort, timeout):
    raise AssertionError("this test drafts no AI question")


async def no_proposal(provider, packet, *, model, effort, timeout):
    raise AssertionError("this test proposes no acceptance checks")


async def no_inquiry(provider, packet, *, model, effort, timeout):
    raise AssertionError("this test asks the analyst and the curator nothing")


def employment(
    hired, *, failing=None, saving=True, question=no_question, propose=no_proposal, inquire=no_inquiry, preparer=None
):
    """What a session's process borrows (`experimental.webui.employ`) with the employee faked and the materials handed
    over for real; `hired` collects each employee with how it was hired, and each replica a scripted trial played on.
    A saved deployment is the employee's artifact id; without `saving` the employee delegates and none is saved.
    `question`, `propose` and `inquire` stand in for the models that draft an AI question, propose acceptance checks
    and answer a question about the analyst's or the curator's step."""

    def hire(contract, config, *, task, workdir, root, subagent_model, timeout, guard, delegation=True, how="hire"):
        if failing is not None:
            raise failing
        employee = Employee(root, workdir, task)
        hired.append(SimpleNamespace(employee=employee, how=how, guard=guard, delegation=delegation))
        return employee

    def replicate(worker, config, root, *, subagent_model, timeout):
        replica = Employee(root, root / "workdir", worker.baseline.task)
        replica.artifact_id = worker.artifact_id
        hired.append(SimpleNamespace(employee=replica, how="replica"))
        return replica

    async def save(employee, path):
        if saving:
            path.write_text(json.dumps({"revision": employee.artifact_id, "task": employee.baseline.task.id}))
        return saving

    async def load(employee, path):
        saved = json.loads(path.read_text())
        assert saved["task"] == employee.baseline.task.id
        employee.artifact_id = saved["revision"]

    return SimpleNamespace(
        prepare=lambda: None,
        starting=lambda: {"raven_commit": "c0"},
        hire=hire,
        rehire=partial(hire, how="rehire"),
        hand_over=employ.hand_over,
        standing_norms=lambda contract, names: {},
        counterpart_view=employ.counterpart_view,
        references=employ.references,
        question=question,
        propose=propose,
        inquire=inquire,
        preparer=preparer,
        replicate=replicate,
        together=Together,
        save=save,
        load=load,
    )


@pytest.fixture
def curations(monkeypatch):
    calls = []

    async def improve(worker, provider, **options):
        calls.append(options)
        worker.artifact_id = f"artifact-{len(calls)}"
        path = worker.root / "curation" / f"c{len(calls)}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"feedback": options.get("feedback"), "active_artifact_id": worker.artifact_id}))

    monkeypatch.setattr(stepping, "improve", improve)
    return calls


def write_config(tmp_path, **values):
    (tmp_path / "raven.json").write_text(
        json.dumps({"agents": {"defaults": {"model": "deepseek/deepseek-flash", "reasoningEffort": "low"}}})
    )
    path = tmp_path / "live.json"
    path.write_text(
        json.dumps({"config": "raven.json", "root": "live", "rounds": 3, "turns": 4, "timeout": 30, **values})
    )
    return path


def spec(tmp_path, **values):
    config = LiveConfig.load(write_config(tmp_path))
    run_dir = config.root / "runs" / SESSION
    run_dir.mkdir(parents=True, exist_ok=True)
    return {**config.spec(run_dir, config.root / "workdirs" / SESSION, "Serve the agency's travellers"), **values}


async def until(check, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        await asyncio.sleep(0.01)
    raise AssertionError("the session did not get there in time")


async def settled(host):
    await until(lambda: host.step is None)
    return host.state()


async def play(host, *messages):
    """One trial with the person saying `messages`, ended from the page."""
    assert (await host.handle({"op": "trial"}))["ok"]
    for text in messages:
        await until(lambda: (trial := host.state()["trial"]) and trial["waiting"])
        assert (await host.handle({"op": "say", "text": text}))["ok"]
    await until(lambda: (trial := host.state()["trial"]) and trial["waiting"])
    assert (await host.handle({"op": "close"}))["ok"]
    return await settled(host)


def test_a_live_configuration_reads_its_paths_from_its_own_folder_and_refuses_what_it_does_not_know(tmp_path):
    config = LiveConfig.load(write_config(tmp_path))
    assert config.config == (tmp_path / "raven.json").resolve() and config.root == (tmp_path / "live").resolve()
    assert config.scenario == TRAVEL.resolve() and config.models == config.efforts == {}
    started = config.spec(tmp_path / "run", tmp_path / "work", "the job")
    assert (started["run_dir"], started["workdir"], started["task"]) == (
        str(tmp_path / "run"),
        str(tmp_path / "work"),
        "the job",
    )
    assert started["record"] is None and started["standard"] == [] and started["rounds"] == 3
    for values, message in (
        ({"budget": 3}, "unknown keys"),
        ({"rounds": 0}, "rounds must be a positive integer"),
        ({"config": "missing.json"}, "is not a file"),
        ({"timeout": True}, "timeout must be"),
        ({"models": {"counterpart": "x"}}, "not a model role of this run"),
        ({"efforts": {"curator": 2}}, "must map model roles"),
        ({"experience_scope": " "}, "experience_scope"),
        ({"experience_migrate": "yes"}, "experience_migrate"),
        ({"information": "web"}, "information is ask"),
        ({"title": " "}, "title names the configured scenario"),
    ):
        with pytest.raises(ValueError, match=message):
            LiveConfig.load(write_config(tmp_path, **values))
    bare = tmp_path / "bare.json"
    bare.write_text(json.dumps({"config": "raven.json"}))
    with pytest.raises(ValueError, match=r"needs \['root'\]"):
        LiveConfig.load(bare)


def test_live_experience_configuration_reaches_the_host_without_changing_default_runs(tmp_path):
    default = LiveConfig.load(write_config(tmp_path))
    assert default.experience_memory is None
    configured = LiveConfig.load(
        write_config(tmp_path, experience_memory="memory", experience_scope="project", experience_migrate=True)
    )
    supplied = configured.spec(tmp_path / "run", tmp_path / "work", "task")
    assert supplied["experience_memory"] == str((tmp_path / "memory").resolve())
    assert supplied["experience_scope"] == "project" and supplied["experience_migrate"] is True


def test_the_materials_offered_are_those_the_curator_may_receive_with_where_each_came_from(tmp_path):
    scenario = tmp_path / "agency"
    shutil.copytree(TRAVEL, scenario)
    contract = json.loads((scenario / "contract.json").read_text())
    contract["materials"]["price-list"]["visibility"] = ["counterpart", "analyst"]
    (scenario / "contract.json").write_text(json.dumps(contract))
    spec = json.loads((scenario / "scenario.json").read_text())
    spec["initial"] = [name for name in spec["initial"] if name != "price-list"]
    spec["plans"] = {
        plan: [[name for name in step if name != "price-list"] for step in steps]
        for plan, steps in spec["plans"].items()
    }
    (scenario / "scenario.json").write_text(json.dumps(spec))
    origin = {"origin": "induced", "confirmed": False, "items": ["greet-by-name"]}
    (scenario / "provenance.json").write_text(json.dumps({"materials": {"consultation-scripts": origin}}))
    live = Live(LiveConfig.load(write_config(tmp_path, scenario="agency")))
    offered = {row["name"]: row for row in live.materials()}
    assert "price-list" not in offered and offered["service-sop"]["kind"] == "norm"
    assert "uploads/service-sop/SKILL.md" in offered["service-sop"]["files"] and "origin" not in offered["service-sop"]
    assert offered["consultation-scripts"]["origin"] == origin
    with pytest.raises(ValueError, match=r"hands over no materials named \['price-list'\]"):
        employ.hand_over(live.contract, ["price-list"], uploads=tmp_path / "uploads", shared=tmp_path / "shared")


@pytest.mark.asyncio
async def test_a_live_session_takes_the_loops_steps_as_the_page_asks_and_refuses_what_the_session_refuses(
    tmp_path, curations, analyses
):
    analyses.scripted.extend([CURATE])
    hired = []
    host = Host(spec(tmp_path), employment(hired))
    await host.boot()
    try:
        state = host.state()
        assert state["failed"] is None and state["status"] == "running" and not state["onboarded"]
        assert host.session.boundaries.policy == "warn" and hired[0].guard is not None and hired[0].employee.started
        settings = json.loads((host.root / "settings.json").read_text())
        assert settings["chain"] == "live" and settings["models"]["partner"] == "deepseek/deepseek-flash"
        assert settings["models"]["curator"] == "deepseek/deepseek-flash" and "counterpart" not in settings["models"]
        assert "raven.json" not in json.dumps(settings) and settings["efforts"]["curator"] == "low"

        reply = await host.handle({"op": "onboard", "text": "Here is our SOP.", "materials": ["service-sop"]})
        assert reply["ok"]
        state = await settled(host)
        assert state["onboarded"] and state["error"] is None
        assert curations[0]["feedback"]["signals"][0]["text"] == "Here is our SOP."
        record = json.loads(host.session.path.read_text())
        assert record["opening"][0]["source"] == "human"
        assert record["opening"][0]["attachments"][0]["name"] == "service-sop"
        assert (host.workdir / "uploads" / "service-sop" / "SKILL.md").is_file()

        refused = await host.handle({"op": "analyse"})
        assert not refused["ok"] and "the analysis needs trials" in refused["error"]

        assert (await host.handle({"op": "trial"}))["ok"]
        await until(lambda: (trial := host.state()["trial"]) and trial["waiting"])
        assert (await host.handle({"op": "say", "text": "   "}))["error"] == "the message is empty"
        assert (await host.handle({"op": "say", "text": "Plan a trip"}))["ok"]
        assert (await host.handle({"op": "say", "text": "Too soon"}))["error"] == "the employee is still answering"
        trial = await until(
            lambda: (trial := host.state()["trial"]) and trial["waiting"] and trial["exchanges"] and trial
        )
        assert trial["name"] == "trial-1" and trial["said"] is None and trial["exchanges"][0]["user"] == "Plan a trip"
        assert trial["exchanges"][0]["execution"]["records"][0]["kind"] == "runner.event"
        assert (await host.handle({"op": "close"}))["ok"]
        state = await settled(host)
        assert state["trial"] is None and state["pending"] == {"sessions": 1, "signals": 0}

        assert (await host.handle({"op": "signal", "text": "Ask for the budget first."}))["ok"]
        assert (await host.handle({"op": "analyse"}))["ok"]
        state = await settled(host)
        assert state["reviewing"] and state["outcome"] == {"next": "curate", "reason": ""}
        assert [signal.text for signal in analyses.calls[0]["signals"]] == ["Ask for the budget first."]
        refused = await host.handle({"op": "trial"})
        assert not refused["ok"] and "before the analysis" in refused["error"]
        assert (await host.handle({"op": "signal", "text": "That requirement is wrong: keep the greeting."}))["ok"]
        assert host.state()["reviewing"]

        assert (await host.handle({"op": "curate"}))["ok"]
        state = await settled(host)
        assert not state["reviewing"] and host.session.rounds[-1].curation == ("c2.json",)
        assert [signal["text"] for signal in curations[1]["feedback"]["signals"]] == [
            "Ask for the budget first.",
            "That requirement is wrong: keep the greeting.",
        ]
        refused = await host.handle({"op": "signal", "text": "   "})
        assert not refused["ok"] and refused["error"] == "the message is empty"

        assert (await host.handle({"op": "finish", "reason": "the owner is done"}))["ok"] and host.ended
        record = json.loads(host.session.path.read_text())
        assert record["status"] == "finished" and record["stop"] == "the owner is done"
    finally:
        await host.close()
    assert hired[0].employee.closed


@pytest.mark.asyncio
async def test_the_person_asks_the_analyst_and_the_curator_about_their_steps_and_the_answers_are_kept(
    tmp_path, curations, analyses
):
    analyses.scripted.extend([CURATE])
    asked, hold = [], asyncio.Event()

    async def inquire(provider, packet, *, model, effort, timeout):
        asked.append(packet)
        if packet["question"] == "Fail please":
            raise RuntimeError("the model provider failed")
        if packet["question"].startswith("Held"):
            await hold.wait()
        return f"Answer {len(asked)}"

    host = Host(spec(tmp_path), employment([], inquire=inquire))
    await host.boot()
    try:
        refused = await host.handle({"op": "inquire", "role": "analyst", "round": 1, "question": "Why?"})
        assert not refused["ok"] and "no analysis" in refused["error"]
        assert (await host.handle({"op": "onboard", "text": "Here is our SOP.", "materials": ["service-sop"]}))["ok"]
        await settled(host)
        refused = await host.handle({"op": "inquire", "role": "curator", "round": 0, "question": "What did you add?"})
        assert not refused["ok"] and "no finished curation" in refused["error"]

        assert (await host.handle({"op": "trial"}))["ok"]
        await until(lambda: (trial := host.state()["trial"]) and trial["waiting"])
        assert (await host.handle({"op": "say", "text": "Plan a trip"}))["ok"]
        await until(lambda: (trial := host.state()["trial"]) and trial["waiting"] and trial["exchanges"])
        assert (await host.handle({"op": "close"}))["ok"]
        await settled(host)
        assert (await host.handle({"op": "signal", "text": "Ask for the budget first."}))["ok"]
        assert (await host.handle({"op": "analyse"}))["ok"]
        await settled(host)
        assert (await host.handle({"op": "inquire", "role": "analyst", "round": 1, "question": "Why curate?"}))["ok"]
        answered = await until(lambda: (items := host.state()["inquiries"]) and "answer" in items[-1] and items)
        assert answered[-1]["answer"] == "Answer 1" and asked[0]["role"] == "analyst" and asked[0]["earlier"] == []
        record = asked[0]["record"]
        assert (
            record["analysis"]["decision"] == "curate" and record["signals"][0]["text"] == "Ask for the budget first."
        )
        assert record["trials"][0]["turns"][0]["said"] == "Plan a trip"
        for bad in (
            {"role": "worker", "round": 1, "question": "Hi"},
            {"role": "analyst", "round": True, "question": "Hi"},
            {"role": "analyst", "round": 1, "question": "   "},
            {"role": "analyst", "round": 1, "question": "x" * 2001},
            {"role": "analyst", "round": 0, "question": "The onboarding has no analysis"},
            {"role": "curator", "round": 1, "question": "Not curated yet"},
        ):
            assert not (await host.handle({"op": "inquire", **bad}))["ok"]

        assert (await host.handle({"op": "curate"}))["ok"]
        await settled(host)
        assert (await host.handle({"op": "inquire", "role": "curator", "round": 1, "question": "What changed?"}))["ok"]
        await until(lambda: "answer" in host.state()["inquiries"][-1])
        assert asked[-1]["role"] == "curator" and "understanding" in asked[-1]["record"]["curation"]
        assert (await host.handle({"op": "inquire", "role": "analyst", "round": 1, "question": "Fail please"}))["ok"]
        failed = await until(lambda: "error" in host.state()["inquiries"][-1] and host.state()["inquiries"][-1])
        assert "the model provider failed" in failed["error"] and "busy" not in failed
        assert (await host.handle({"op": "inquire", "role": "analyst", "round": 1, "question": "And then?"}))["ok"]
        await until(lambda: "answer" in host.state()["inquiries"][-1])
        assert asked[-1]["earlier"] == [{"question": "Why curate?", "answer": "Answer 1"}]
        kept = json.loads((host.root / "inquiries.json").read_text())["items"]
        assert [item["question"] for item in kept] == ["Why curate?", "What changed?", "Fail please", "And then?"]

        for number in (1, 2, 3):
            assert (await host.handle({"op": "inquire", "role": "analyst", "round": 1, "question": f"Held {number}"}))[
                "ok"
            ]
        refused = await host.handle({"op": "inquire", "role": "curator", "round": 1, "question": "One more"})
        assert not refused["ok"] and "being answered" in refused["error"]
        assert [item.get("busy") for item in host.state()["inquiries"][-3:]] == [True] * 3
        hold.set()
        await until(lambda: all("answer" in item for item in host.state()["inquiries"][-3:]))
        assert (await host.handle({"op": "inquire", "role": "curator", "round": 1, "question": "One more"}))["ok"]
        await until(lambda: "answer" in host.state()["inquiries"][-1])
    finally:
        await host.close()


@pytest.mark.asyncio
async def test_pending_inquiries_are_saved_and_cancellation_stays_visible_after_resume(tmp_path):
    entered = asyncio.Event()

    async def inquire(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    host = Host(spec(tmp_path), employment([], inquire=inquire))
    await host.boot()
    host._step_record = lambda role, number: {}
    try:
        assert (await host.handle({"op": "inquire", "role": "analyst", "round": 1, "question": "Why?"}))["ok"]
        await asyncio.wait_for(entered.wait(), 5)
        saved = json.loads((host.root / "inquiries.json").read_text())["items"]
        assert saved[0]["question"] == "Why?" and saved[0]["busy"]
    finally:
        await host.close()
    saved = json.loads((host.root / "inquiries.json").read_text())["items"]
    assert "interrupted" in saved[0]["error"] and "busy" not in saved[0]
    resumed = Host({**host.spec, "record": str(host.session.path)}, employment([]))
    await resumed.boot()
    try:
        assert resumed.state()["inquiries"] == saved
    finally:
        await resumed.close()


@pytest.mark.asyncio
async def test_information_preparation_asks_the_person_on_the_page_who_answers_or_skips_before_the_onboarding(
    tmp_path, curations
):
    from experimental.research.information import Question, Result, Review
    from tests.test_research_collection import accepted, snapshot

    seen = []

    def preparer(contract, released, material_root, *, records, model, effort, ask, research):
        async def prepare(worker, provider, *, feedback=None, admit=None):
            seen.append({"released": released(), "research": research, "records": records, "together": ask.together})
            first = Question(
                id="q1", dimension="role", question="Who signs off?", reason="Unclear.", assumption="The lead"
            )
            second = Question(id="q2", dimension="role", question="Which tone?", reason="Unclear.")
            seen.extend(await asyncio.gather(ask(first), ask(second)))
            return Result(snapshot=snapshot(), review=Review.model_validate(accepted()))

        return prepare

    host = Host(spec(tmp_path, information="ask"), employment([], preparer=preparer))
    await host.boot()
    try:
        assert host.state()["information"] == {"questions": [], "asked": []}
        refused = await host.handle({"op": "answer", "id": "q1", "text": "Too early"})
        assert not refused["ok"] and "not waiting" in refused["error"]
        assert (await host.handle({"op": "onboard", "text": "Here is our SOP.", "materials": ["service-sop"]}))["ok"]
        waiting = await until(lambda: len(questions := host.state()["information"]["questions"]) == 2 and questions)
        assert [question["question"] for question in waiting] == ["Who signs off?", "Which tone?"]
        assert waiting[0]["assumption"] == "The lead"
        assert not (await host.handle({"op": "answer", "id": "q2", "text": "   "}))["ok"]
        assert not (await host.handle({"op": "answer", "text": "No question named"}))["ok"]
        assert (await host.handle({"op": "answer", "id": "q2", "text": "Plain and brief"}))["ok"]
        await until(lambda: [q["id"] for q in host.state()["information"]["questions"]] == ["q1"])
        assert (await host.handle({"op": "answer", "id": "q1", "skip": True}))["ok"]
        state = await settled(host)
        assert state["onboarded"] and state["information"]["questions"] == []
        assert {item["id"]: item["answer"] for item in state["information"]["asked"]} == {
            "q1": None,
            "q2": "Plain and brief",
        }
        assert seen[0]["released"] == ["service-sop"] and seen[0]["research"] is False and seen[0]["together"] is True
        assert seen[1:] == [None, "Plain and brief"]
        assert json.loads(host.session.path.read_text())["information"]["status"] == "ready"
    finally:
        await host.close()
    (tmp_path / "plain").mkdir()
    plain = Host(spec(tmp_path / "plain"), employment([]))
    await plain.boot()
    try:
        refused = await plain.handle({"op": "answer", "text": "x"})
        assert (
            not refused["ok"] and "prepares no information" in refused["error"] and plain.state()["information"] is None
        )
    finally:
        await plain.close()


@pytest.mark.asyncio
async def test_an_ai_question_drafts_the_next_message_of_a_held_trial_from_what_the_counterpart_may_see(
    tmp_path, curations
):
    asked = []

    async def question(provider, packet, *, model, effort, timeout):
        asked.append(packet)
        if len(asked) == 3:
            raise RuntimeError("the model provider failed")
        return {"message": f"Draft {len(asked)}", "aim": "Asks for the budget", "good": "Asks before planning"}

    host = Host(spec(tmp_path), employment([], question=question))
    await host.boot()
    try:
        assert (await host.handle({"op": "onboard", "text": "Here is our SOP.", "materials": ["service-sop"]}))["ok"]
        await settled(host)
        refused = await host.handle({"op": "question"})
        assert not refused["ok"] and "a trial you hold yourself" in refused["error"]

        assert (await host.handle({"op": "trial"}))["ok"]
        await until(lambda: (trial := host.state()["trial"]) and trial["waiting"])
        assert (await host.handle({"op": "question"}))["ok"]
        drafted = await until(lambda: (q := host.state()["question"]) and "message" in q and q)
        assert drafted["trial"] == "trial-1" and drafted["message"] == "Draft 1" and drafted["good"]
        [packet] = asked
        assert packet["job"] == "Serve the agency's travellers" and packet["trial"] == [] and packet["earlier"] == []
        assert packet["materials"] and all(name.startswith("service-sop/") for name in packet["materials"])
        assert packet["checks"] and packet["counterpart"] and packet["requirements"] == []

        assert (await host.handle({"op": "say", "text": drafted["message"]}))["ok"]
        await until(lambda: (trial := host.state()["trial"]) and trial["waiting"] and trial["exchanges"])
        assert (await host.handle({"op": "question"}))["ok"]
        await until(lambda: (q := host.state()["question"]) and q.get("message") == "Draft 2")
        assert asked[1]["trial"][0]["said"] == "Draft 1" and asked[1]["earlier"] == ["Draft 1"]

        assert (await host.handle({"op": "question"}))["ok"]
        failed = await until(lambda: (q := host.state()["question"]) and "error" in q and q)
        assert "the model provider failed" in failed["error"] and host.state()["trial"]["waiting"]
        assert (await host.handle({"op": "close"}))["ok"]
        assert (await settled(host))["question"] is None
    finally:
        await host.close()


@pytest.mark.asyncio
async def test_proposed_checks_are_settled_by_the_person_and_join_what_every_assessment_holds_trials_to(
    tmp_path, curations
):
    packets = []
    stated = {"example": "Stated plainly", "rule": "State facts without superlatives"}
    claimed = {"example": "The best by far", "rule": "Superlatives are welcome"}

    async def propose(provider, packet, *, model, effort, timeout):
        packets.append(packet)
        if len(packets) == 2:
            raise RuntimeError("the model provider failed")
        return [
            {"topic": "May replies use superlatives?", "why": "Trial 1 said best", "options": [stated, claimed]},
            {"topic": "How long may a reply be?", "why": "Trial 1 ran long", "options": [stated, claimed]},
        ]

    host = Host(spec(tmp_path), employment([], propose=propose))
    await host.boot()
    try:
        refused = await host.handle({"op": "propose"})
        assert not refused["ok"] and "once the employee is onboarded" in refused["error"]
        assert (await host.handle({"op": "onboard", "text": "Here is our SOP.", "materials": ["service-sop"]}))["ok"]
        await settled(host)
        refused = await host.handle({"op": "propose"})
        assert not refused["ok"] and "open a trial first" in refused["error"]
        await play(host, "Plan a trip", "Make it shorter")

        assert (await host.handle({"op": "propose"}))["ok"]
        proposals = await until(lambda: (p := host.state()["proposals"]) and "items" in p and p)
        [packet] = packets
        assert packet["trials"][0]["turns"][0]["said"] == "Plan a trip" and packet["chosen"] == []
        assert packet["checks"] and packet["job"] == "Serve the agency's travellers"
        assert [item["chosen"] for item in proposals["items"]] == [None, None]

        assert (await host.handle({"op": "adopt", "index": 0, "option": 0}))["ok"]
        state = host.state()
        assert state["adopted"] == ["State facts without superlatives"]
        [held] = host.session.external_requirements
        assert held.source == "human" and held.situation == "May replies use superlatives?" and held.kind == "gate"
        assert host.session.signals[-1].text == "State facts without superlatives"
        assert json.loads(host.session.path.read_text())["external_requirements"][0]["quote"] == held.quote
        again = await host.handle({"op": "adopt", "index": 0, "option": 1})
        assert not again["ok"] and "already settled" in again["error"]
        for wrong in ({"index": 1, "option": True}, {"index": 1, "option": 2}, {"index": 5, "option": 0}, {"index": 1}):
            assert not (await host.handle({"op": "adopt", **wrong}))["ok"], wrong
        assert (await host.handle({"op": "adopt", "index": 1, "rule": "  At most five lines  "}))["ok"]
        assert host.state()["adopted"] == ["State facts without superlatives", "At most five lines"]
        assert host.state()["proposals"]["items"][1]["chosen"] == {"option": None, "rule": "At most five lines"}

        assert (await host.handle({"op": "propose"}))["ok"]
        failed = await until(lambda: (p := host.state()["proposals"]) and "error" in p and p)
        assert "the model provider failed" in failed["error"] and len(host.session.external_requirements) == 2
        assert packets[1]["chosen"] == ["State facts without superlatives", "At most five lines"]
    finally:
        await host.close()


@pytest.mark.asyncio
async def test_a_paused_onboarding_resumes_on_the_same_opening_when_the_page_asks_again(
    tmp_path, curations, monkeypatch
):
    pauses = [GenerationPausedError(SimpleNamespace(trace=[], calls=0, model_copy=lambda deep: None))]
    improve = stepping.improve

    async def interrupted(worker, provider, **options):
        if pauses:
            raise pauses.pop()
        await improve(worker, provider, **options)

    monkeypatch.setattr(stepping, "improve", interrupted)
    host = Host(spec(tmp_path), employment([]))
    await host.boot()
    try:
        assert (await host.handle({"op": "onboard", "text": "Here is our SOP."}))["ok"]
        state = await settled(host)
        assert state["status"] == "paused" and state["onboarded"] and state["error"] is None
        refused = await host.handle({"op": "trial"})
        assert not refused["ok"] and "resumes first" in refused["error"]
        assert (await host.handle({"op": "onboard"}))["ok"]
        state = await settled(host)
        assert state["status"] == "running" and len(curations) == 1
        assert curations[0]["feedback"]["signals"][0]["text"] == "Here is our SOP."
    finally:
        await host.close()


@pytest.mark.asyncio
async def test_a_session_that_cannot_start_says_why_and_can_still_be_closed(tmp_path):
    host = Host(spec(tmp_path), employment([], failing=ValueError("the configuration names no model")))
    await host.boot()
    state = host.state()
    assert state["failed"] == "starting" and state["error"] == "ValueError: the configuration names no model"
    assert await host.handle({"op": "onboard", "text": "hi"}) == {
        "ok": False,
        "error": "the session could not start",
        "state": state,
    }
    assert (await host.handle({"op": "finish"}))["ok"] and host.ended
    await host.close()


@pytest.mark.asyncio
async def test_resuming_rehires_the_employee_on_the_record_and_its_saved_deployment(tmp_path, curations):
    hired = []
    first = Host(spec(tmp_path), employment(hired))
    await first.boot()
    try:
        await first.handle({"op": "onboard", "text": "Here is our SOP."})
        await settled(first)
        await play(first, "Plan a trip")
        task = first.employee.baseline.task
    finally:
        await first.close()
    assert json.loads((first.root / "deployment.json").read_text())["revision"] == "artifact-1"
    kept = {"record": str(first.session.path)}
    resumed = Host(spec(tmp_path, **kept), employment(hired))
    await resumed.boot()
    try:
        state = resumed.state()
        assert hired[-1].how == "rehire" and hired[-1].employee.baseline.task == task
        assert state["onboarded"] and state["pending"] == {"sessions": 1, "signals": 0}
        assert state["revision"] == "artifact-1" and state["saved"]
        assert not (resumed.root / "settings.json").read_text().count("rehire")
        await play(resumed)
        assert list(resumed.session.sessions) == ["trial-1", "trial-2"]
    finally:
        await resumed.close()


FLAKY = """
from pathlib import Path

from experimental.iteration.protocols import Item, Signal


class Flaky:
    name = "flaky"

    def __init__(self, spec, employee):
        self.failed = Path(spec["run_dir"]) / "flaky-failed"

    async def evaluate(self, sessions):
        if not self.failed.exists():
            self.failed.write_text("once")
            raise RuntimeError("assessor: provider error: HTTP 503")
        return Signal("flaky", "judged", items=tuple(Item(f"{key}:ok", "pass", key) for key in sessions))


def make(spec, employee):
    return Flaky(spec, employee)
"""


@pytest.mark.asyncio
@pytest.mark.parametrize("detached", [False, True])
async def test_a_failed_assessment_is_retried_on_the_saved_practice_and_judged_again(
    tmp_path, curations, analyses, detached
):
    (tmp_path / "flaky.py").write_text(FLAKY)
    hired = []
    host = Host(spec(tmp_path, assessor=f"{tmp_path / 'flaky.py'}:make"), employment(hired))
    await host.boot()
    try:
        await host.handle({"op": "onboard", "text": "Working instructions"})
        await settled(host)
        await play(host, "Saved practice input")
        await host.handle({"op": "signal", "text": "Saved judgement"})
        assert (await host.handle({"op": "assess"}))["ok"]
        state = await settled(host)
        assert state["status"] == "error" and state["failed"] == "assess" and "HTTP 503" in state["error"]
        if detached:
            kept = {**host.spec, "record": str(host.session.path), "retry": "assess"}
            await host.close()
            host = Host(kept, employment(hired))
            await host.boot()
        else:
            refused = await host.handle({"op": "retry_analysis"})
            assert not refused["ok"] and "unfinished failed analysis" in refused["error"]
            assert (await host.handle({"op": "retry"}))["ok"]
        state = host.state()
        assert state["status"] == "running" and state["failed"] is None and state["error"] is None
        assert state["pending"] == {"sessions": 1, "signals": 1}
        assert [signal.text for signal in host.session.signals] == ["Saved judgement"]
        assert (await host.handle({"op": "assess"}))["ok"]
        assert (await settled(host))["assessed"]
        assert [signal.source for signal in host.session.signals] == ["human", "flaky"]
        assert sum(len(item.employee.runs) for item in hired) == 1
        refused = await host.handle({"op": "retry"})
        assert not refused["ok"] and "unfinished failed analysis or assessment" in refused["error"]
    finally:
        await host.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("detached", [False, True])
async def test_failed_analysis_recovery_restores_evidence_without_running_the_employee(
    tmp_path, curations, analyses, detached
):
    hired = []
    host = Host(spec(tmp_path), employment(hired))
    await host.boot()
    try:
        await host.handle({"op": "onboard", "text": "Working instructions"})
        await settled(host)
        await play(host, "Saved practice input")
        await host.handle({"op": "signal", "text": "Saved judgement"})
        answers = stepping.evidence_fingerprint(host.session.sessions)
        await host.handle({"op": "analyse"})
        assert (await settled(host))["status"] == "error"
        if detached:
            kept = {**host.spec, "record": str(host.session.path), "retry_analysis": True}
            await host.close()
            host = Host(kept, employment(hired))
            await host.boot()
        else:
            assert (await host.handle({"op": "retry_analysis"}))["ok"]
        assert host.state()["status"] == "running" and host.state()["failed"] is None
        assert host.state()["rounds"] == 0
        assert stepping.evidence_fingerprint(host.session.sessions) == answers
        assert host.session.signals[0].text == "Saved judgement"
        assert sum(len(item.employee.runs) for item in hired) == 1
        analyses.scripted.append(CURATE)
        assert (await host.handle({"op": "analyse"}))["ok"]
        assert (await settled(host))["reviewing"]
        assert sum(len(item.employee.runs) for item in hired) == 1
    finally:
        await host.close()


@pytest.mark.asyncio
async def test_a_session_whose_employee_delegates_cannot_resume_once_its_harness_changed(tmp_path, curations):
    first = Host(spec(tmp_path), employment([], saving=False))
    await first.boot()
    try:
        await first.handle({"op": "onboard", "text": "Here is our SOP."})
        assert not (await settled(first))["saved"]
    finally:
        await first.close()
    blocked = Host(spec(tmp_path, record=str(first.session.path)), employment([], saving=False))
    await blocked.boot()
    assert blocked.state()["failed"] == "starting" and "never saved" in blocked.state()["error"]
    await blocked.close()


def test_a_late_answer_is_dropped_when_the_next_one_is_read():
    parent, child = multiprocessing.Pipe()
    handle = Handle(SimpleNamespace(is_alive=lambda: True), parent)
    assert handle.ask({"op": "state"}, 0.05) is None
    late = child.recv()
    child.send({"seq": late["seq"], "state": {"step": "late"}})

    def answer():
        asked = child.recv()
        child.send({"seq": asked["seq"], "state": {"step": None}})

    thread = threading.Thread(target=answer)
    thread.start()
    reply = handle.ask({"op": "state"}, 5)
    thread.join()
    assert reply["state"] == {"step": None} and handle.last == {"step": None}


class Threaded:
    """A session's process as a thread of the test, on a real pipe."""

    def __init__(self, target):
        self.thread = threading.Thread(target=target, daemon=True)
        self.thread.start()

    def is_alive(self):
        return self.thread.is_alive()

    def join(self, timeout=None):
        self.thread.join(timeout)

    def terminate(self):
        pass


def threaded(borrowed):
    def start(started):
        parent, child = multiprocessing.Pipe()
        return Threaded(lambda: asyncio.run(session_host.serve(child, started, borrowed))), parent

    return start


def call(url, body=None, *, headers=None, data=None):
    if body is not None:
        data, headers = json.dumps(body).encode(), {"Content-Type": "application/json", **(headers or {})}
    request = Request(url, data=data, headers=headers or {}, method="GET" if data is None else "POST")
    try:
        with urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read())
    except HTTPError as error:
        return error.code, json.loads(error.read())


def poll(url, check, timeout=15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status, body = call(url)
        if status == 200 and check(body):
            return body
        time.sleep(0.05)
    raise AssertionError(f"{url} did not get there in time")


@pytest.fixture
def studio(tmp_path, curations, analyses):
    live = Live(LiveConfig.load(write_config(tmp_path)), start=threaded(employment([])))
    runs = tmp_path / "runs"
    runs.mkdir()
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, root=runs.resolve(), live=live))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield SimpleNamespace(base=f"http://127.0.0.1:{server.server_address[1]}/api/studio/live", live=live)
    server.shutdown()
    server.server_close()
    live.close()


def test_the_server_relays_the_pages_steps_to_the_sessions_process_and_serves_its_record(studio):
    status, info = call(studio.base)
    assert status == 200 and info["enabled"] and info["sessions"] == [] and info["settings"]["rounds"] == 3
    assert info["task"].strip() and any(row["name"] == "service-sop" for row in info["materials"])
    status, created = call(studio.base, {"title": "Agency", "task": "Serve the agency's travellers"})
    assert status == 201 and created["title"] == "Agency" and created["attached"]
    session = f"{studio.base}/{created['id']}"
    body = poll(session, lambda body: body["state"] and body["state"]["step"] is None and "record" in body)
    assert body["record"]["task"] == "Serve the agency's travellers" and body["run"].startswith(created["id"] + "/")
    assert body["progress"] == {"curation": None, "paused": None}
    status, again = call(f"{session}?stamp={body['stamp']}")
    assert status == 200 and "record" not in again and again["state"]["status"] == "running"

    status, reply = call(f"{session}/onboard", {"text": "Here is our SOP.", "materials": ["service-sop"]})
    assert status == 200 and reply["ok"] and "seq" not in reply
    body = poll(session, lambda body: body["state"]["onboarded"] and body["state"]["step"] is None)
    assert body["record"]["opening"][0]["attachments"][0]["name"] == "service-sop"
    status, refused = call(f"{session}/analyse", {})
    assert status == 409 and "the analysis needs trials" in refused["error"]
    status, refused = call(f"{session}/revert", {})
    assert status == 409 and "no earlier version" in refused["error"]
    status, refused = call(f"{session}/script", {"names": ["nothing"]})
    assert status == 409 and "no practice scripts named" in refused["error"]
    status, refused = call(f"{session}/question", {})
    assert status == 409 and "a trial you hold yourself" in refused["error"]
    status, refused = call(f"{session}/propose", {})
    assert status == 409 and "open a trial first" in refused["error"]
    status, refused = call(f"{session}/adopt", {"index": 0, "option": 0})
    assert status == 409 and "one of the proposed checks" in refused["error"]
    status, refused = call(f"{session}/inquire", {"role": "analyst", "round": 1, "question": "Why?"})
    assert status == 409 and "no analysis to ask about" in refused["error"]
    assert call(f"{session}/signal", {"text": "x"}, headers={"Origin": "http://elsewhere.example"})[0] == 403
    form = {"Content-Type": "application/x-www-form-urlencoded"}
    assert call(f"{session}/signal", data=b"text=x", headers=form)[0] == 415
    assert call(f"{session}/unknown", {})[0] == 404
    status, refused = call(f"{studio.base}/scenarios", {"title": ""})
    assert status == 400 and "title" in refused["error"]
    assert call(f"{studio.base}/live-20260101000000-000000/onboard", {})[0] == 404

    status, archived = call(f"{session}/archive", {"name": "Agency v1", "version": "v1"})
    assert status == 200 and archived["archived"] == {"name": "Agency v1", "version": "v1"}
    assert archived["status"] == "finished" and not archived["attached"]
    assert call(f"{session}/trial", {})[0] == 410
    [row] = call(studio.base)[1]["sessions"]
    assert row["id"] == created["id"] and row["archived"]["name"] == "Agency v1"


def test_a_kept_session_whose_process_is_gone_is_read_and_resumed_but_takes_no_step(tmp_path):
    config = LiveConfig.load(write_config(tmp_path))
    kept = config.root / "runs" / SESSION
    (kept / "iteration").mkdir(parents=True)
    (kept / "studio.json").write_text(json.dumps({"id": SESSION, "title": "Earlier", "task": "the job", "created": 1}))
    record = {"task_id": "t", "task": "the job", "status": "running", "rounds": [], "opening": []}
    (kept / "iteration" / "r.json").write_text(json.dumps(record))
    started = []
    live = Live(config, start=lambda spec: started.append(spec) or (SimpleNamespace(is_alive=lambda: False), None))
    [row] = live.info()["sessions"]
    assert (row["title"], row["status"], row["run"], row["attached"]) == ("Earlier", "running", f"{SESSION}/r", False)
    body = live.snapshot(SESSION)
    assert body["state"] is None and not body["busy"] and body["record"]["task"] == "the job"
    (kept / "boundaries.jsonl").write_text('{"role": "curator", "event": "enter"}\n')
    assert "record" not in live.snapshot(SESSION, body["stamp"])
    (kept / "iteration" / "r.json").write_text(json.dumps({**record, "status": "paused"}))
    assert live.snapshot(SESSION, body["stamp"])["record"]["status"] == "paused"
    (kept / "iteration" / "r.json").write_text(json.dumps(record))
    assert live.step(SESSION, "trial", {}) == (410, {"error": "the session's process has ended"})
    assert live.snapshot("../runs") is None and live.step("live-1", "trial", {})[0] == 404
    status, _ = live.step(SESSION, "resume", {})
    assert status == 202 and started[0]["record"] == str(kept / "iteration" / "r.json")


def test_resuming_a_failed_analysis_requires_explicit_retry_and_rejects_other_ended_runs(tmp_path):
    config = LiveConfig.load(write_config(tmp_path))
    kept = config.root / "runs" / SESSION
    (kept / "iteration").mkdir(parents=True)
    (kept / "studio.json").write_text(json.dumps({"id": SESSION, "task": "the job", "created": 1}))
    record = {
        "task_id": "t",
        "task": "the job",
        "status": "error",
        "opening": [],
        "error": "analyst: provider error: HTTP 503",
        "rounds": [{"sessions": {"practice": []}, "signals": [], "feedback": None, "curated": False}],
    }
    path = kept / "iteration" / "r.json"
    path.write_text(json.dumps(record))
    started = []
    live = Live(config, start=lambda spec: started.append(spec) or (SimpleNamespace(is_alive=lambda: False), None))
    assert live.summary(SESSION)["retry"] == {"step": "analyse", "error": "analyst: provider error: HTTP 503"}
    assert live.step(SESSION, "resume", {})[0] == 409
    assert live.step(SESSION, "resume", {"retry": "curate"})[0] == 400
    assert live.step(SESSION, "resume", {"retry": "assess"})[0] == 409
    assert live.step(SESSION, "resume", {"retry": "analyse"})[0] == 202
    assert started[-1]["retry"] == "analyse"
    assert json.loads(path.read_text()) == record
    for status, stage in (("finished", "analyse"), ("error", "assess"), ("running", "analyse")):
        path.write_text(json.dumps({**record, "status": status, "error_step": stage}))
        assert live.step(SESSION, "resume", {"retry": "analyse"})[0] == 409
    assert len(started) == 1 and live.summary(SESSION)["retry"] is None
    path.write_text(json.dumps({**record, "error": "assessor: timed out", "error_step": "assess"}))
    assert live.summary(SESSION)["retry"] == {"step": "assess", "error": "assessor: timed out"}
    assert live.step(SESSION, "resume", {"retry": "assess"})[0] == 202 and started[-1]["retry"] == "assess"


def test_without_a_live_configuration_the_server_only_replays(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, root=runs.resolve()))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}/api/studio/live"
    try:
        status, body = call(base)
        assert status == 404 and "without --live-config" in body["error"]
        assert call(base, {"task": "the job"})[0] == 404
    finally:
        server.shutdown()
        server.server_close()


EXAMINER = """
from experimental.iteration.protocols import Item, Signal


class Examiner:
    name = "examiner"

    def __init__(self, spec, employee):
        self.employee = employee

    async def evaluate(self, sessions):
        failing = self.employee.artifact_id != "artifact-1"
        items = tuple(Item(f"{key}:report", "fail" if failing else "pass", key) for key in sessions)
        return Signal("examiner", "scored", items=items)


def make(spec, employee):
    return Examiner(spec, employee)
"""


def scripted_config(tmp_path):
    (tmp_path / "examiner.py").write_text(EXAMINER)
    week = [
        {"text": "Monday's posts", "files": {"inbox/monday.json": "[1]"}},
        {"text": "Friday: send the report", "files": {"inbox/friday.json": "[2]"}},
    ]
    scripts = [
        {"name": "week-1", "title": "First week", "steps": week},
        {"name": "exam-1", "exam": True, "steps": [{"text": "Exam week", "files": {"inbox/exam.json": "[3]"}}]},
    ]
    (tmp_path / "scripts.json").write_text(json.dumps(scripts))
    return {"scripts": "scripts.json", "assessor": "examiner.py:make", "delegation": False}


def test_scripts_are_named_steps_that_write_only_inside_the_working_directory(tmp_path):
    from experimental.webui.live import scripts

    config = LiveConfig.load(write_config(tmp_path, **scripted_config(tmp_path)))
    assert config.scripts == (tmp_path / "scripts.json").resolve() and not config.delegation
    assert config.assessor == f"{(tmp_path / 'examiner.py').resolve()}:make"
    loaded = scripts(config.scripts)
    assert [(item["name"], item["title"], item["exam"], len(item["steps"])) for item in loaded] == [
        ("week-1", "First week", False, 2),
        ("exam-1", "exam-1", True, 1),
    ]
    for bad, message in (
        ([{"name": "trial-3", "steps": [{"text": "x"}]}], "own name"),
        ([{"name": "a", "steps": [{"text": "x"}]}, {"name": "a", "steps": [{"text": "y"}]}], "own name"),
        ([{"name": "a", "steps": []}], "no steps"),
        ([{"name": "a", "steps": [{"text": " "}]}], "says a text"),
        ([{"name": "a", "steps": [{"text": "x", "files": {"../up.json": ""}}]}], "outside the working directory"),
        ([{"name": "a", "steps": [{"text": "x", "files": {"/etc/x": ""}}]}], "outside the working directory"),
    ):
        (tmp_path / "bad.json").write_text(json.dumps(bad))
        with pytest.raises(ValueError, match=message):
            scripts(tmp_path / "bad.json")
    with pytest.raises(ValueError, match="assessor names a Python file"):
        LiveConfig.load(write_config(tmp_path, assessor="missing.py:make"))
    with pytest.raises(ValueError, match="names no saved deployment"):
        LiveConfig.load(write_config(tmp_path, versions={"exp": "missing.json"}))


@pytest.mark.asyncio
async def test_scripts_play_on_replicas_the_exam_scores_versions_and_a_worse_one_is_reverted(
    tmp_path, curations, analyses
):
    analyses.scripted.extend([CURATE])
    hired = []
    config = LiveConfig.load(write_config(tmp_path, **scripted_config(tmp_path)))
    run_dir = config.root / "runs" / SESSION
    run_dir.mkdir(parents=True)
    host = Host(config.spec(run_dir, config.root / "workdirs" / SESSION, "Watch the community"), employment(hired))
    await host.boot()
    try:
        assert hired[0].delegation is False and host.state()["assessor"]
        await host.handle({"op": "onboard", "text": "Here are the norms."})
        await settled(host)
        assert not (await host.handle({"op": "script", "names": ["exam-1"]}))["ok"]
        assert (await host.handle({"op": "script", "names": ["week-1"]}))["ok"]
        state = await settled(host)
        assert state["error"] is None and state["pending"] == {"sessions": 1, "signals": 0}
        replica = next(row.employee for row in hired if row.how == "replica")
        assert replica.seen == [["monday.json"], ["friday.json", "monday.json"]]
        assert [exchange.user for exchange in host.session.sessions["week-1"]] == [
            "Monday's posts",
            "Friday: send the report",
        ]
        assert not host.employee.runs

        mark = {"session": "week-1", "turn": 1, "kind": "fix", "note": "List every urgent post first."}
        assert (await host.handle({"op": "signal", "marks": [mark]}))["ok"]
        [item] = host.session.signals[-1].items
        assert (item.result, item.expected, item.session, item.authority) == (
            "fail",
            "List every urgent post first.",
            "week-1",
            "external",
        )
        assert (
            item.note.startswith("[should have been] turn turn-2") and item.actual == "Reply to Friday: send the report"
        )
        for bad in ({**mark, "session": "week-9"}, {**mark, "turn": 5}, {**mark, "kind": "meh"}):
            assert not (await host.handle({"op": "signal", "marks": [bad]}))["ok"]

        assert (await host.handle({"op": "exam"}))["ok"]
        state = await settled(host)
        assert state["exam"]["current"]["failed"] == 0 and state["exam"]["current"]["judged"] == 1
        assert list(host.session.held_out) == ["exam-1"] and host.session.held_out_signals[0].source == "examiner"
        assert (await host.handle({"op": "assess"}))["ok"]
        assert (await settled(host))["assessed"]
        await host.handle({"op": "analyse"})
        await settled(host)
        assert [signal.source for signal in analyses.calls[0]["signals"]] == ["human", "examiner"]
        await host.handle({"op": "curate"})
        state = await settled(host)
        assert state["revision"] == "artifact-2" and state["revertible"]
        assert json.loads((host.root / "previous.json").read_text())["revision"] == "artifact-1"

        await host.handle({"op": "exam"})
        state = await settled(host)
        assert state["exam"]["current"]["failed"] == 1 and state["exam"]["previous"]["failed"] == 0
        assert (await host.handle({"op": "revert"}))["ok"]
        state = await settled(host)
        assert state["error"] is None and state["revision"] == "artifact-1" and not state["revertible"]
        assert json.loads((host.root / "deployment.json").read_text())["revision"] == "artifact-1"
        assert "[undone]" in host.session.history[-1].understanding
        assert host.session.signals[-1].text.startswith("The last change to the harness was undone")
        assert not (await host.handle({"op": "revert"}))["ok"]
    finally:
        await host.close()


@pytest.mark.asyncio
async def test_retrying_a_failed_exam_after_resume_reuses_its_answers(tmp_path, curations):
    hired = []
    config = LiveConfig.load(write_config(tmp_path, **scripted_config(tmp_path)))
    run_dir = config.root / "runs" / SESSION
    run_dir.mkdir(parents=True)
    host = Host(config.spec(run_dir, config.root / "workdirs" / SESSION, "Watch the community"), employment(hired))
    await host.boot()

    async def unavailable(sessions):
        raise TimeoutError("judge deadline")

    try:
        await host.handle({"op": "onboard"})
        await settled(host)
        host.plugin.evaluate = unavailable
        await host.handle({"op": "exam"})
        assert "judge deadline" in (await settled(host))["error"]
        answers = host.session.held_out
        assert list(answers) == ["exam-1"]
        assert sum(item.how == "replica" for item in hired) == 1
    finally:
        await host.close()
    resumed = Host({**host.spec, "record": str(host.session.path)}, employment(hired))
    await resumed.boot()
    try:
        assert (await resumed.handle({"op": "exam"}))["ok"]
        state = await settled(resumed)
        assert state["error"] is None and state["exam"]["current"]["judged"] == 1
        assert stepping.evidence_fingerprint(resumed.session.held_out) == stepping.evidence_fingerprint(answers)
        assert sum(item.how == "replica" for item in hired) == 1
        refused = await resumed.handle({"op": "exam"})
        assert not refused["ok"] and "already have a completed exam" in refused["error"]
        assert sum(item.how == "replica" for item in hired) == 1
    finally:
        await resumed.close()


@pytest.mark.asyncio
async def test_a_session_starts_from_a_saved_version_on_its_task(tmp_path, curations):
    task = Task(text="Watch the community")
    saved = tmp_path / "saved.json"
    saved.write_text(json.dumps({"revision": "artifact-7", "task": task.model_dump(mode="json")}))
    borrowed = employment([])

    async def load(employee, path):
        value = json.loads(Path(path).read_text())
        assert Task.model_validate(value["task"]) == employee.baseline.task
        employee.artifact_id = value["revision"]

    borrowed.load = load
    host = Host(spec(tmp_path, start_from=str(saved), start_name="exp14 after-A", task="ignored"), borrowed)
    await host.boot()
    try:
        assert host.employee.baseline.task == task and host.state()["revision"] == "artifact-7"
        assert json.loads((host.root / "settings.json").read_text())["start_from"] == "exp14 after-A"
        assert json.loads((host.root / "deployment.json").read_text())["revision"] == "artifact-7"
    finally:
        await host.close()


def test_a_new_session_may_start_from_a_configured_or_archived_version(tmp_path):
    saved = tmp_path / "after-A.json"
    saved.write_text(json.dumps({"task": {"text": "Watch the community", "id": "t1"}}))
    started = []
    live = Live(
        LiveConfig.load(write_config(tmp_path, versions={"exp14 after-A": "after-A.json"})),
        start=lambda spec: started.append(spec) or (SimpleNamespace(is_alive=lambda: True), None),
    )
    archived = live.runs / SESSION
    archived.mkdir()
    (archived / "studio.json").write_text(
        json.dumps({"id": SESSION, "task": "x", "archived": {"name": "Ops", "version": "v3"}})
    )
    (archived / "deployment.json").write_text(json.dumps({"task": {"text": "Run ops", "id": "t2"}}))
    assert live.info()["versions"] == [
        {"name": "exp14 after-A", "task": "Watch the community"},
        {"name": "Ops v3", "task": "Run ops"},
    ]
    assert live.create({"version": "nothing"})[0] == 400
    status, created = live.create({"version": "Ops v3", "task": "ignored", "title": "Again"})
    assert status == 201 and created["start"] == "Ops v3" and created["task"] == "Run ops"
    assert started[0]["start_from"] == str(archived / "deployment.json") and started[0]["start_name"] == "Ops v3"
    assert started[0]["task"] == "Run ops" and "versions" not in started[0]


def test_a_deleted_session_leaves_the_list_and_moves_to_the_trash_with_its_process_stopped(tmp_path):
    stopped = []
    live = Live(
        LiveConfig.load(write_config(tmp_path)),
        start=lambda spec: (SimpleNamespace(is_alive=lambda: True), None),
    )
    status, created = live.create({"task": "Plan trips", "title": "Gone soon"})
    session = created["id"]
    (live.workdirs / session).mkdir()
    (live.workdirs / session / "notes.md").write_text("kept")
    live.handles[session] = SimpleNamespace(alive=True, last=None, stop=lambda: stopped.append(session))
    assert [row["id"] for row in live.info()["sessions"]] == [session]
    assert live.step(session, "delete", {}) == (200, {"ok": True, "deleted": session})
    assert stopped == [session] and session not in live.handles and live.info()["sessions"] == []
    trash = live.runs.parent / "trash"
    assert json.loads((trash / "runs" / session / "studio.json").read_text())["title"] == "Gone soon"
    assert (trash / "workdirs" / session / "notes.md").read_text() == "kept"
    assert live.step(session, "delete", {})[0] == 404 and live.step("../runs", "delete", {})[0] == 404


def test_a_scenario_built_on_the_page_is_offered_and_its_sessions_start_and_resume_in_it(tmp_path):
    started = []
    live = Live(
        LiveConfig.load(write_config(tmp_path)),
        start=lambda spec: started.append(spec) or (SimpleNamespace(is_alive=lambda: False), None),
    )
    body = {
        "title": "Weekly report",
        "profile": "Write the weekly report for the sales team.",
        "files": [{"name": "../notes.md", "text": "Q3 targets"}, {"name": "SKILL.md", "text": "mine"}],
        "practice": ["Summarise this week", "  "],
        "exam": ["Summarise last week"],
        "checks": ["Every number has its source"],
    }
    for bad, message in (
        ({"title": ""}, "title"),
        ({"profile": "x" * 8001}, "job description"),
        ({"files": [{"name": "deck.pdf", "text": "x"}]}, ".md, .txt or .csv"),
        ({"practice": "one line"}, "list of texts"),
        ({"checks": ["x"] * 41}, "at most 40 lines"),
    ):
        status, refused = live.build({**body, **bad})
        assert status == 400 and message in refused["error"], (bad, refused)
    assert not list(live.scenarios.glob("scn-*")) if live.scenarios.exists() else True
    status, built = live.build(body)
    assert status == 201 and built["built"] and built["title"] == "Weekly report"
    name = built["name"]
    assert re.fullmatch(r"scn-[0-9a-f]{8}", name)
    assert [item["name"] for item in built["scripts"]] == ["p01", "e01"] and built["scripts"][1]["exam"]
    assert built["materials"][0]["name"] == "materials" and built["materials"][0]["kind"] == "fact"
    package = live.scenarios / name / name
    assert sorted(path.name for path in (package / "materials" / "materials").iterdir()) == [
        "SKILL.md",
        "notes.md",
        "uploaded-SKILL.md",
    ]
    checks = live.scenario(name).statements.checks
    assert [(check.id, check.check) for check in checks] == [("C1", "Every number has its source")]
    offered = live.info()["scenarios"]
    assert [item["built"] for item in offered] == [False, True] and offered[1]["name"] == name
    assert offered[0]["title"] == offered[0]["task"].splitlines()[0][:80]
    (tmp_path / "titled").mkdir()
    titled = Live(LiveConfig.load(write_config(tmp_path / "titled", title="Travel desk")), start=live.start)
    assert titled.info()["scenarios"][0]["title"] == "Travel desk"

    assert live.create({"task": "x", "scenario": "scn-00000000"})[0] == 400
    assert live.create({"task": "x", "scenario": "../runs"})[0] == 400
    status, created = live.create({"task": "Write the weekly report", "scenario": name})
    assert status == 201 and created["scenario"] == name
    spec = started[-1]
    assert spec["scenario"] == str(package) and spec["scripts"] == str(live.scenarios / name / "scripts.json")
    assert spec["assessor"] is None and spec["standard"] == ["declared", "sedimented"] and spec["built"] is True
    status, plain = live.create({"task": "Plan trips"})
    assert status == 201 and plain["scenario"] is None and started[-1]["scenario"] == str(live.config.scenario)

    session = created["id"]
    (live.runs / session / "iteration").mkdir()
    (live.runs / session / "iteration" / "r.json").write_text(json.dumps({"status": "running", "rounds": []}))
    assert live.resume(session)[0] == 202
    assert started[-1]["scenario"] == str(package) and started[-1]["record"]


def test_a_built_scenarios_checks_are_judged_against_the_handed_materials_and_the_prepared_information(tmp_path):
    live = Live(
        LiveConfig.load(write_config(tmp_path)), start=lambda spec: (SimpleNamespace(is_alive=lambda: False), None)
    )
    status, built = live.build(
        {"title": "Docs", "profile": "Answer questions.", "files": [{"name": "guide.md", "text": "x" * 30_000}]}
    )
    contract = live.scenario(built["name"])
    home = tmp_path / "home"
    assert set(employ.references(contract, ["materials"], home)) == {"materials/SKILL.md", "materials/guide.md"}
    assert len(employ.references(contract, ["materials"], home)["materials/guide.md"]) == 30_000
    (home / "uploads" / "information").mkdir(parents=True)
    (home / "uploads" / "information" / "expert.md").write_text("Prepared facts")
    assert employ.references(contract, [], home) == {"uploads/information/expert.md": "Prepared facts"}
    view = employ.counterpart_view(contract, ["materials"])
    assert view["checks"] == [] and set(view["materials"]) == {"materials/SKILL.md", "materials/guide.md"}
    handed = employ.hand_over(
        contract, ["materials"], uploads=tmp_path / "agent" / "uploads", shared=tmp_path / "work" / "uploads"
    )
    assert handed[0].name == "materials" and (tmp_path / "agent" / "uploads" / "materials" / "guide.md").is_file()


@pytest.mark.asyncio
async def test_an_exam_judges_each_question_on_its_own_all_at_once():
    from experimental.iteration.protocols import Item, Signal
    from experimental.webui.session_host import EachQuestion

    class Standard:
        name = "assessor"

        def __init__(self, fail=None):
            self.asked, self.constrained, self.adopted, self.fail = [], None, [], fail
            self.running, self.together = 0, asyncio.Event()

        def constrain(self, requirements):
            self.constrained = requirements

        def twin(self):
            twin = Twin(self)
            self.asked.append(twin)
            return twin

        def adopt(self, twins):
            self.adopted.append([twin.sessions for twin in twins])

    class Twin:
        def __init__(self, inner):
            self.inner, self.sessions = inner, None

        async def evaluate(self, sessions):
            self.sessions = list(sessions)
            [key] = sessions
            if key == self.inner.fail:
                raise RuntimeError("the judge timed out")
            self.inner.running += 1
            if self.inner.running == 2:
                self.inner.together.set()
            await asyncio.wait_for(self.inner.together.wait(), 5)
            failing = key == "e02"
            items = (Item("C1", "fail" if failing else "pass"), Item("R2", "pass"))
            return Signal("assessor", "the checks", items=items, metrics={"m": 1.0}, satisfied=not failing)

    inner = Standard()
    exam = EachQuestion(inner)
    exam.constrain(("rule",))
    signal = await exam.evaluate({"e01": ["turn"], "e02": ["turn"]})
    assert inner.constrained == ("rule",) and exam.name == "assessor" and inner.adopted == [[["e01"], ["e02"]]]
    assert [(item.id, item.session, item.result) for item in signal.items] == [
        ("C1:e01", "e01", "pass"),
        ("R2:e01", "e01", "pass"),
        ("C1:e02", "e02", "fail"),
        ("R2:e02", "e02", "pass"),
    ]
    assert signal.satisfied is False and signal.metrics == {} and signal.source == "assessor"

    broken = Standard(fail="e03")
    with pytest.raises(RuntimeError, match="timed out"):
        await EachQuestion(broken).evaluate({"e01": ["turn"], "e03": ["turn"]})
    assert broken.adopted == [[["e01"], ["e03"]]] and broken.running == 1

    from experimental.assessor.standard import Assessor

    with pytest.raises(ValueError, match="no twins"):
        EachQuestion(Assessor(object(), sources=("derived",), builder=object()))


def test_with_a_token_every_request_needs_it_and_opening_with_it_sets_a_cookie(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    token = "a" * 24
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, root=runs.resolve(), token=token))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        assert call(f"{base}/api/runs")[0] == 401
        assert call(f"{base}/api/studio/live", {"task": "x"})[0] == 401
        assert call(f"{base}/api/runs", headers={"Cookie": "studio_access=" + "b" * 24})[0] == 401
        from http.client import HTTPConnection

        connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=10)
        connection.request("GET", f"/studio?token={token}&run=x")
        response = connection.getresponse()
        assert response.status == 303 and response.getheader("Location") == "/studio?run=x"
        cookie = response.getheader("Set-Cookie")
        assert cookie.startswith(f"studio_access={token}") and "HttpOnly" in cookie
        connection.close()
        assert call(f"{base}/api/runs", headers={"Cookie": f"studio_access={token}"})[0] == 200
    finally:
        server.shutdown()
        server.server_close()
