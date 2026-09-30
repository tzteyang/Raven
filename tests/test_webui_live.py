"""The Studio's live sessions: the configuration, a session's process taking the loop's steps as the page asks for
them, and the server relaying those steps to it and serving what the session recorded."""

import asyncio
import json
import multiprocessing
import shutil
import threading
import time
from functools import partial
from http.server import ThreadingHTTPServer
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

    async def start(self):
        self.started = True

    async def close(self):
        self.closed = True


def employment(hired, *, failing=None, rehire=None):
    """What a session's process borrows (`experimental.webui.employ`) with the employee faked and the materials handed
    over for real; `hired` collects each employee with how it was hired."""

    def hire(contract, config, *, task, workdir, root, subagent_model, timeout, guard):
        if failing is not None:
            raise failing
        employee = Employee(root, workdir, Task(text=task))
        hired.append(SimpleNamespace(employee=employee, how="hire", guard=guard))
        return employee

    def rehired(contract, config, *, task, workdir, root, subagent_model, timeout, guard):
        record = next((root / "iteration").glob("*.json"))
        employee = Employee(root, workdir, Task(id=json.loads(record.read_text())["task_id"], text=task))
        hired.append(SimpleNamespace(employee=employee, how="rehire", guard=guard))
        return employee

    return SimpleNamespace(
        prepare=lambda: None,
        starting=lambda: {"raven_commit": "c0"},
        hire=hire,
        rehire=rehire or rehired,
        hand_over=employ.hand_over,
        standing_norms=lambda contract, names: {},
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
    (tmp_path / "raven.json").write_text("{}")
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
    assert config.scenario == TRAVEL.resolve() and config.curator_effort == "high"
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
    ):
        with pytest.raises(ValueError, match=message):
            LiveConfig.load(write_config(tmp_path, **values))
    bare = tmp_path / "bare.json"
    bare.write_text(json.dumps({"config": "raven.json"}))
    with pytest.raises(ValueError, match=r"needs \['root'\]"):
        LiveConfig.load(bare)


def test_the_materials_offered_are_those_the_curator_may_receive_with_where_each_came_from(tmp_path):
    scenario = tmp_path / "agency"
    shutil.copytree(TRAVEL, scenario)
    contract = json.loads((scenario / "contract.json").read_text())
    contract["materials"]["price-list"]["visibility"] = ["party", "analyst"]
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
        assert settings["chain"] == "live" and settings["models"]["employee"] == "deepseek/deepseek-flash"
        assert "raven.json" not in json.dumps(settings) and settings["efforts"]["curator"] == "high"

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

        assert (await host.handle({"op": "curate"}))["ok"]
        state = await settled(host)
        assert not state["reviewing"] and host.session.rounds[-1].curation == ("c2.json",)

        assert (await host.handle({"op": "finish", "reason": "the owner is done"}))["ok"] and host.ended
        record = json.loads(host.session.path.read_text())
        assert record["status"] == "finished" and record["stop"] == "the owner is done"
    finally:
        await host.close()
    assert hired[0].employee.closed


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
async def test_resuming_rehires_the_employee_on_the_record_and_the_loop_cannot_rehire_yet(tmp_path, curations):
    hired = []
    first = Host(spec(tmp_path), employment(hired))
    await first.boot()
    try:
        await first.handle({"op": "onboard", "text": "Here is our SOP."})
        await settled(first)
        await play(first, "Plan a trip")
    finally:
        await first.close()
    kept = {"record": str(first.session.path)}
    resumed = Host(spec(tmp_path, **kept), employment(hired))
    await resumed.boot()
    try:
        state = resumed.state()
        assert hired[-1].how == "rehire" and state["onboarded"] and state["pending"] == {"sessions": 1, "signals": 0}
        assert not (resumed.root / "settings.json").read_text().count("rehire")
        await play(resumed)
        assert list(resumed.session.sessions) == ["trial-1", "trial-2"]
    finally:
        await resumed.close()
    blocked = Host(spec(tmp_path, **kept), employment(hired, rehire=employ.rehire))
    await blocked.boot()
    assert blocked.state()["failed"] == "starting"
    assert blocked.state()["error"].startswith(
        "UnsupportedError: resuming needs the employee of an existing run directory"
    )
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
    assert call(f"{session}/signal", {"text": "x"}, headers={"Origin": "http://elsewhere.example"})[0] == 403
    form = {"Content-Type": "application/x-www-form-urlencoded"}
    assert call(f"{session}/signal", data=b"text=x", headers=form)[0] == 415
    assert call(f"{session}/unknown", {})[0] == 404
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
