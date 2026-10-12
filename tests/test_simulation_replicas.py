"""A round's drills played at once: replicas start where the employee stands, on its revision, and are closed after."""

import asyncio
import json
import os
import runpy
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from experimental.cultivation.counterpart.owner import delivery_versions, handles
from experimental.cultivation.employee import AREA, HOME, WORKDIR, Together, hire, replicate
from experimental.harness.participation.compartment import Guard, GuardedFactory
from experimental.harness.participation.hearing import opaque
from experimental.harness.participation.protocols import Exchange
from experimental.harness.raven_adapter.deployment import child_directory
from experimental.harness.raven_adapter.hosting.prepare import prepare_children
from experimental.harness.raven_adapter.strategy import Scopes
from experimental.harness.raven_adapter.worker import Execution
from experimental.harness.scenario.sealed import Sealed
from experimental.simulation.bench.lab import lab_placement, replica_lab
from experimental.simulation.bench.scenario import BUNDLED, Scenario
from experimental.simulation.cases.travel_agency.owner import NAME as REVIEW
from experimental.simulation.cases.travel_agency.owner import Agency
from raven.contracts.llm_provider import LLMResponse, ToolCallRequest
from raven.providers.factory import make_lazy_provider
from tests.fixtures.harness_curator.authoring import profile

TRAVEL = BUNDLED / "travel_agency"
AUTHORED = profile({"TOOLS.md": "Quote from the price list."})


def config_file(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "providers": {"deepseek": {"api_key": "k"}},
                "agents": {"defaults": {"model": "deepseek/x", "provider": "deepseek"}},
            }
        )
    )
    return path


def test_owner_delivery_versions_preserve_same_named_snapshots_and_mark_reused_paths_unknown(tmp_path):
    paths = [tmp_path / folder / "resume.md" for folder in ("first", "second")]
    for path, text in zip(paths, ("Original statement.", "Corrected statement."), strict=True):
        path.parent.mkdir()
        path.write_text(text)
    exchanges = [SimpleNamespace(execution=SimpleNamespace(deliverables=(path,))) for path in paths]
    versions = delivery_versions(exchanges)
    assert [row["files"]["resume.md"] for row in versions] == ["Original statement.", "Corrected statement."]
    assert [row["turn"] for row in versions] == [1, 2]
    reused = delivery_versions([exchanges[1], exchanges[1]])
    assert reused[0]["files"] == {} and "resume.md" in reused[0]["unavailable"]
    assert reused[1]["files"]["resume.md"] == "Corrected statement."


def test_repeated_drills_start_fresh_lab_clocks_without_resetting_an_active_drill(tmp_path):
    source = BUNDLED / "orchard_livestream" / "lab"
    registry = tmp_path / "connections.json"
    template = {"connections": [{"id": "local-lab", "transport": "local", "paths": ["/original"]}]}
    registry.write_text(json.dumps(template))
    first_registry = replica_lab(source, tmp_path / "first", registry)
    second_registry = replica_lab(source, tmp_path / "second", registry)
    first_work = Path(json.loads(first_registry.read_text())["connections"][0]["paths"][0])
    second_work = Path(json.loads(second_registry.read_text())["connections"][0]["paths"][0])
    assert lab_placement(first_registry) == {
        "machine": "local-lab",
        "workdir": first_work,
        "registry": first_registry.resolve(),
    }
    assert lab_placement(second_registry)["workdir"] == second_work != first_work
    first = runpy.run_path(str(first_work / "live_console.py"))
    second = runpy.run_path(str(second_work / "live_console.py"))
    session = next(iter(first["sessions"](first["DATA"].read_text())))
    beginning = first["read"](session, now=1000)
    later = first["read"](session, now=1480)
    fresh = second["read"](session, now=1490)
    assert fresh == beginning and later != beginning
    assert first["read"](session, now=1500) != beginning
    assert json.loads(registry.read_text()) == template


def test_replica_connections_override_only_its_child_environment(tmp_path, monkeypatch):
    from experimental.cultivation import employee as module

    monkeypatch.setattr(
        "raven.agent.subagent.vendored_agents.agents_root", lambda: Path(__file__).resolve().parents[1] / "agents"
    )
    oncall = next(row for row in module.discover_product_rows() if row.name == "Raven-Oncall")
    monkeypatch.setattr(module, "discover_product_rows", lambda: [oncall])
    monkeypatch.setenv("RAVEN_CONNECTIONS", "/initial/registry.json")
    config = config_file(tmp_path)
    (tmp_path / "work").mkdir()
    worker = hire(Scenario.load(TRAVEL).contract, config, workdir=tmp_path / "work", root=tmp_path / "run")
    worker.children = prepare_children(worker.baseline, worker.area, ["Raven", "Raven-Oncall"])
    registry = tmp_path / "drill-registry.json"
    registry.write_text('{"connections": []}')
    replica = replicate(worker, config, tmp_path / "replica", connections=registry)
    rows = {row.name: row for row in replica.baseline.config.subagents.agents}
    original = {row.name: row for row in worker.baseline.config.subagents.agents}
    assert rows["Raven-Oncall"].env["RAVEN_CONNECTIONS"] == str(registry)
    assert rows["Raven"].env["RAVEN_CONNECTIONS"] == str(registry)
    assert original["Raven-Oncall"].env["RAVEN_CONNECTIONS"] == "/initial/registry.json"
    assert os.environ["RAVEN_CONNECTIONS"] == "/initial/registry.json"


def test_a_replica_copies_the_employee_as_it_stands_with_its_installed_revision(tmp_path):
    scenario, config = Scenario.load(TRAVEL), config_file(tmp_path)
    (tmp_path / "work").mkdir()
    guard = Guard("partner", Sealed.of([], tokens=["wbt-budget"]))
    employee = hire(scenario.contract, config, workdir=tmp_path / "work", root=tmp_path / "run", guard=guard)
    employee.children = prepare_children(employee.baseline, employee.area, ["Raven"])
    employee.children["Raven"].artifact = profile({"TOOLS.md": "Search first."})
    employee.artifact = AUTHORED
    home = employee.baseline.config.workspace_path
    (home / "skills" / "service-sop").mkdir(parents=True)
    (home / "skills" / "service-sop" / "SKILL.md").write_text("SOP")
    (home / "sessions").mkdir()
    (home / "sessions" / "old.jsonl").write_text("{}")
    (tmp_path / "work" / "handover").mkdir()
    (tmp_path / "work" / "handover" / "ticket.md").write_text("earlier ticket")
    saved = {"task_id": employee.baseline.task.id, "data": {}, "sessions": {"c1": {"stage": "S2"}}}
    (employee.area / "planning.json").write_text(json.dumps(saved))
    child_state = child_directory(employee.area, "Raven")
    child_state.mkdir(parents=True, exist_ok=True)
    (child_state / "action.json").write_text('{"held": 1}')

    root = tmp_path / "run" / "replicas" / "1-student"
    replica = replicate(employee, config, root)
    area = root / AREA
    assert replica.root == root.resolve() and replica.area == area.resolve()
    assert replica.baseline.config.workspace_path == area / HOME
    assert (area / HOME / "skills" / "service-sop" / "SKILL.md").read_text() == "SOP"
    assert not (area / HOME / "sessions").exists()
    assert (area / WORKDIR / "handover" / "ticket.md").read_text() == "earlier ticket"
    assert replica.baseline.workdir == area / WORKDIR
    assert replica.artifact == AUTHORED and replica.children["Raven"].artifact == employee.children["Raven"].artifact
    assert replica.children["Raven"].baseline.config.workspace_path == area / HOME / "subagents" / "Raven"
    # A replica under a new task id would refuse the employee's saved plan before any drill started.
    assert replica.baseline.task == employee.baseline.task
    assert Scopes("planning", replica.baseline.task, area / "planning.json", dict, per_session=True).saved["c1"] == {
        "stage": "S2"
    }
    assert (child_directory(area, "Raven") / "action.json").read_text() == '{"held": 1}'
    assert employee.artifact == AUTHORED and (tmp_path / "work" / "handover" / "ticket.md").is_file()
    assert replica.revision_id == employee.revision_id
    assert replica.provider_factory == GuardedFactory(make_lazy_provider, guard)


class Employee:
    def __init__(self, workdir, artifact=AUTHORED, package="_curator_abc"):
        self.baseline = SimpleNamespace(workdir=workdir, config=SimpleNamespace(workspace_path=workdir / "home"))
        self.root = workdir
        self.artifact, self.children, self.package = artifact, {}, package
        self.started = self.closed = False

    def records(self):
        return [{"kind": "runtime.bound", "package": f"/runs/x/{self.package}"}] if self.started else []

    async def start(self):
        self.started = True

    async def close(self):
        self.closed = True


class Drill:
    def __init__(self, name, gate=None, error=None):
        self.name, self.gate, self.error, self.worker = name, gate, error, None

    async def run(self, worker):
        self.worker = worker
        if self.gate:
            await self.gate.wait()
        if self.error:
            raise self.error
        return {self.name: []}


async def test_every_drill_runs_at_once_on_its_own_replica_and_the_employee_plays_none(tmp_path):
    employee = Employee(tmp_path / "employee")
    employee.started = True
    made, placed = {}, {}

    def spawn(worker, label):
        assert worker is employee and not any(drill.worker for drill in drills.values())
        made[label] = Employee(tmp_path / label)
        made[label].lab = {
            "machine": "local-lab",
            "workdir": tmp_path / label / "lab",
            "registry": tmp_path / label / "connections.json",
        }
        return made[label]

    gate = asyncio.Barrier(3)
    drills = {name: Drill(name, gate) for name in ("family", "premium", "student")}
    together = Together(drills, spawn, placed)
    sessions = await asyncio.wait_for(together.run(employee), 5)
    assert sessions == {"family": [], "premium": [], "student": []}
    assert [drills[name].worker for name in drills] == [made[f"1-{opaque(name)}"] for name in drills]
    assert not employee.closed and all(replica.started and replica.closed for replica in made.values())
    assert {name: where["workdir"] for name, where in placed.items()} == {
        name: tmp_path / f"1-{opaque(name)}" for name in drills
    }
    assert {name: where["lab"]["workdir"] for name, where in placed.items()} == {
        name: tmp_path / f"1-{opaque(name)}" / "lab" for name in drills
    }
    drills = {name: Drill(name) for name in drills}
    together.trials = drills
    await together.run(employee)
    assert sorted(made) == sorted(f"{round}-{opaque(name)}" for round in (1, 2) for name in drills)
    assert not any(name in label for label in made for name in drills)


async def test_a_replica_on_another_revision_never_plays_and_every_replica_is_closed(tmp_path):
    employee = Employee(tmp_path / "employee")
    employee.started = True
    made = []

    def spawn(worker, label):
        old = label.endswith(opaque("student"))
        made.append(Employee(tmp_path / label, package="_curator_old" if old else "_curator_abc"))
        return made[-1]

    drills = {name: Drill(name) for name in ("family", "premium", "student")}
    with pytest.raises(ValueError, match="bound _curator_old"):
        await Together(drills, spawn).run(employee)
    assert not any(drill.worker for drill in drills.values()) and all(replica.closed for replica in made)


async def test_a_failed_drill_stops_the_others_and_closes_the_replicas(tmp_path):
    employee = Employee(tmp_path / "employee")
    employee.started = True
    made = []

    def spawn(worker, label):
        made.append(Employee(tmp_path / label))
        return made[-1]

    never = asyncio.Event()
    drills = {"family": Drill("family", never), "student": Drill("student", error=RuntimeError("customer left"))}
    with pytest.raises(RuntimeError, match="customer left"):
        await asyncio.wait_for(Together(drills, spawn).run(employee), 5)
    assert made and all(replica.closed for replica in made)


async def test_the_owner_reads_what_each_drill_filed_on_its_replica_and_nothing_it_found_there(tmp_path):
    scenario = Scenario.load(TRAVEL)
    employee = tmp_path / "employee"
    (employee / "workdir" / "handover").mkdir(parents=True)
    (employee / "workdir" / "handover" / "earlier.md").write_text("earlier ticket")
    (employee / "home").mkdir()
    placed = {}
    for name, text in (("family", "family ticket"), ("student", "student ticket")):
        replica = tmp_path / "replicas" / f"1-{name}"
        shutil.copytree(employee, replica)
        (replica / "workdir" / "handover" / "hold.md").write_text(text)
        (replica / "home" / "notes").mkdir()
        (replica / "home" / "notes" / "brief.md").write_text(f"{name} brief")
        placed[name] = {"workdir": replica / "workdir", "home": replica / "home"}

    def played(reply):
        records = [{"kind": "runner.event", "event_type": "Text", "event": {"content": reply}}]
        return [Exchange("Book it", Execution("t1", [], records, {}, "a"))]

    rows = [{"id": handle, "result": "pass"} for handle in handles(scenario.criteria).values()]
    verdict = LLMResponse(
        content=None, tool_calls=[ToolCallRequest(REVIEW, REVIEW, {"verdicts": rows, "remark": "Fine."})]
    )
    requests = []

    class Provider:
        async def chat_with_retry(self, **kwargs):
            requests.append(kwargs)
            return verdict

    agency = Agency(
        scenario,
        Provider(),
        employee / "home" / "skills",
        workdir=employee / "workdir",
        disclosure=scenario.disclosure("all"),
        uploads=employee / "home" / "uploads",
        workdirs=placed,
    )
    agency.prepare()
    await agency.evaluate({"family": played("Booked."), "student": played("Booked too."), "premium": played("Hi.")})
    packet = json.loads(requests[0]["messages"][1]["content"])
    assert packet["filed"] == {
        name: {"workdir/handover/hold.md": f"{name} ticket", "home/notes/brief.md": f"{name} brief"}
        for name in ("family", "student")
    }


def test_handed_over_files_land_in_uploads_and_never_replace_one_already_there(tmp_path):
    from experimental.cultivation.employee import hand_over

    source = tmp_path / "sheet.md"
    source.write_text("data")
    hand_over([source], tmp_path / "work" / "uploads")
    assert (tmp_path / "work" / "uploads" / "sheet.md").read_text() == "data"
    with pytest.raises(ValueError, match="would replace"):
        hand_over([source], tmp_path / "work" / "uploads")
