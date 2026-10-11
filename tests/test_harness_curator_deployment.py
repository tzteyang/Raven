"""Content ownership across root and managed child homes rejects ambiguous writers."""

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from experimental.curator.harness import Artifact, Task
from experimental.curator.raven_adapter.baselines import Baseline
from experimental.curator.raven_adapter.content import check_owners
from experimental.curator.raven_adapter.deployment import Child
from experimental.curator.raven_adapter.preparation import PreparedHarness
from raven.config.raven import RavenConfig
from raven.config.schema import Config
from tests.fixtures.harness_curator.authoring import action, profile


def baseline(home):
    config = Config()
    config.agents.defaults.workspace = str(home)
    return Baseline(config, RavenConfig(), home.parent, task=Task(text="Work"))


def test_root_content_may_not_reach_into_a_managed_child_home(tmp_path):
    root = baseline(tmp_path / "root")
    child = baseline(tmp_path / "root/subagents/Hosted")
    check_owners(
        root,
        PreparedHarness(content={"memory": {"TOOLS.md": "root"}}),
        {"Hosted": (child, PreparedHarness(content={"memory": {"TOOLS.md": "child"}}))},
    )
    with pytest.raises(ValueError, match="root content overlaps"):
        check_owners(
            root,
            PreparedHarness(content={"memory": {"subagents/Hosted/TOOLS.md": "x"}}),
            {"Hosted": (child, PreparedHarness())},
        )


def test_shared_home_does_not_allow_two_content_writers(tmp_path):
    root, shared = baseline(tmp_path / "root"), baseline(tmp_path / "shared")
    with pytest.raises(ValueError, match="both own"):
        check_owners(
            root,
            PreparedHarness(),
            {
                "first": (shared, PreparedHarness(content={"memory": {"TOOLS.md": "one"}})),
                "second": (shared, PreparedHarness(content={"memory": {"TOOLS.md": "two"}})),
            },
        )


def preview(prepared, child_prepared=None):
    @asynccontextmanager
    async def checked(*args, **kwargs):
        async def agent_state(name):
            return {"inspection": {"facts": {"prepared": child_prepared.model_dump(mode="json")}}}

        yield SimpleNamespace(prepared=prepared, agent_state=agent_state)

    return checked


def test_feedback_location_routes_requirements_without_discarding_original_signals():
    from experimental.curator.composition.requirements import feedback_for

    feedback = {
        "signals": ["supplied document"],
        "requirements": [
            {"behavior": "root", "locations": ["root"]},
            {"behavior": "child", "locations": ["child/Hosted"]},
            {"behavior": "unknown", "locations": []},
        ],
    }
    selected = feedback_for("Hosted", feedback)
    assert [item["behavior"] for item in selected["requirements"]] == ["child", "unknown"]
    assert selected["signals"] == feedback["signals"]
    assert len(feedback["requirements"]) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("cleanup_fails", [False, True])
async def test_failed_activation_restores_the_checkpoint_flushed_by_shutdown(tmp_path, cleanup_fails):
    import asyncio
    from unittest.mock import AsyncMock

    from experimental.curator.harness import Declaration
    from experimental.curator.raven_adapter.deployment import activate
    from experimental.curator.raven_adapter.inspection import Inspection
    from experimental.curator.raven_adapter.targets import catalogue
    from tests.test_harness_curator_generation import assigned

    root = tmp_path / "runtime"
    root.mkdir()
    state = root / "planning.json"
    state.write_text('{"version": "before shutdown"}')
    declaration = Declaration("old", catalogue())
    candidate = declaration.accept(assigned(declaration, "action.strategy"), action(generation={"temperature": 0.2}))
    worker = SimpleNamespace(
        baseline=baseline(tmp_path / "home"),
        root=root,
        area=root,
        children={},
        commitments=(),
        artifact=Artifact(values={}),
        _lock=asyncio.Lock(),
        prepared=PreparedHarness(),
        _validation_copy=preview(PreparedHarness()),
        _exchange=AsyncMock(return_value=True),
        _inspect=AsyncMock(return_value=Inspection(declaration, {}, {})),
        _accept=lambda candidate, inspection: candidate,
    )
    closed = 0

    async def close():
        nonlocal closed
        closed += 1
        if closed == 1:
            state.write_text('{"version": "flushed"}')
        elif cleanup_fails:
            raise RuntimeError("Candidate cleanup failed")

    async def start():
        if worker.artifact.values:
            state.write_text('{"version": "failed candidate"}')
            raise RuntimeError("Candidate start failed")
        assert state.read_text() == '{"version": "flushed"}'

    worker._close, worker._start = close, start
    with pytest.raises(RuntimeError, match="Candidate (start|cleanup) failed"):
        await activate(worker, candidate)
    assert worker.artifact.values == {} and state.read_text() == '{"version": "flushed"}'


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "root_start", "child_revision"])
async def test_root_and_child_activation_is_one_boundary_that_restores_every_home_and_checkpoint(tmp_path, failure):
    """A root revision and a child revision activate together. When the restarted root fails, or a child reports a
    revision other than the one submitted, both homes' content, both artifacts and the flushed checkpoints return to
    what the shutdown left."""
    import asyncio
    from unittest.mock import AsyncMock

    from experimental.curator.harness import Commitment, Declaration
    from experimental.curator.raven_adapter.deployment import activate, child_directory
    from experimental.curator.raven_adapter.inspection import Inspection, fingerprint
    from experimental.curator.raven_adapter.inspection.runtime import declaration_for
    from experimental.curator.raven_adapter.targets import catalogue
    from tests.test_harness_curator_generation import assigned

    before = (Commitment(id="H1", surface="memory.strategy", statement="Keep the profile", serves=("task",)),)
    home, child_home = tmp_path / "home", tmp_path / "home" / "subagents" / "Hosted"
    child_home.mkdir(parents=True)
    (home / "TOOLS.md").write_text("root before")
    (child_home / "TOOLS.md").write_text("child before")
    root_declaration, child_declaration = Declaration("root@1", catalogue()), declaration_for("hosted@1", {})
    child = Child(baseline(child_home), profile({"TOOLS.md": "child before"}))
    child.commitments = before
    submitted = child_declaration.accept(
        assigned(child_declaration, "memory.strategy", current=before), profile({"TOOLS.md": "child after"})
    )
    candidate = root_declaration.accept(
        assigned(root_declaration, "memory.strategy", current=before), profile({"TOOLS.md": "root after"})
    )
    runtime = tmp_path / "runtime"
    checkpoint = child_directory(runtime, "Hosted") / "planning.json"
    checkpoint.parent.mkdir(parents=True)
    checkpoint.write_text('{"version": "before"}')
    payload = {
        "identity": "hosted@1",
        "unavailable": {},
        "facts": {"prepared": {"content": {"memory": {"TOOLS.md": "child before"}}}},
        "sources": {},
    }
    expected = fingerprint(submitted.artifact.model_dump(mode="json"))

    async def exchange(request):
        if request["operation"] == "idle":
            return True
        assert request == {"operation": "inspect_agent", "agent": "Hosted"}
        return {"inspection": payload, "revision": "other" if failure == "child_revision" else expected}

    worker = SimpleNamespace(
        baseline=baseline(home),
        root=runtime,
        area=runtime,
        children={"Hosted": child},
        artifact=profile({"TOOLS.md": "root before"}),
        last_plan=None,
        commitments=before,
        _lock=asyncio.Lock(),
        prepared=PreparedHarness(content={"memory": {"TOOLS.md": "root before"}}),
        _validation_copy=preview(
            PreparedHarness(content={"memory": {"TOOLS.md": "root after"}}),
            PreparedHarness(content={"memory": {"TOOLS.md": "child after"}}),
        ),
        _exchange=exchange,
        _inspect=AsyncMock(return_value=Inspection(root_declaration, {}, {})),
        _accept=lambda candidate, inspection: candidate,
    )
    starts = []

    async def close():
        checkpoint.write_text('{"version": "flushed"}')

    async def start():
        """The real start materialises what each home's artifact authors."""
        (home / "TOOLS.md").write_text(json.loads(worker.artifact.files["memory_profile.json"])["TOOLS.md"])
        (child_home / "TOOLS.md").write_text(
            json.loads(worker.children["Hosted"].artifact.files["memory_profile.json"])["TOOLS.md"]
        )
        starts.append((json.loads(worker.artifact.files["memory_profile.json"])["TOOLS.md"], checkpoint.read_text()))
        if (
            failure == "root_start"
            and json.loads(worker.artifact.files["memory_profile.json"])["TOOLS.md"] == "root after"
        ):
            checkpoint.write_text('{"version": "half-started"}')
            raise RuntimeError("root start failed")

    worker._close, worker._start = close, start
    if failure:
        with pytest.raises((RuntimeError, ValueError), match="root start failed|did not activate the expected"):
            await activate(worker, candidate, {"Hosted": submitted})
        assert worker.artifact == profile({"TOOLS.md": "root before"})
        assert worker.children["Hosted"].artifact == profile({"TOOLS.md": "child before"})
        assert worker.children["Hosted"].plan is None and worker.last_plan is None
        assert worker.commitments == before and worker.children["Hosted"].commitments == before
        assert (home / "TOOLS.md").read_text() == "root before"
        assert (child_home / "TOOLS.md").read_text() == "child before"
        assert checkpoint.read_text() == '{"version": "flushed"}'
        assert starts == [("root after", '{"version": "flushed"}'), ("root before", '{"version": "flushed"}')]
        assert worker.prepared.files() == {"TOOLS.md": "root before"}
        return
    await activate(worker, candidate, {"Hosted": submitted})
    assert (home / "TOOLS.md").read_text() == "root after" and (child_home / "TOOLS.md").read_text() == "child after"
    assert worker.children["Hosted"].artifact == submitted.artifact and worker.children["Hosted"].plan == submitted.plan
    assert worker.children["Hosted"].original == child.original
    assert worker.last_plan == candidate.plan and starts == [("root after", '{"version": "flushed"}')]
    assert [item.id for item in worker.commitments] == ["H1", "H2"]
    assert [item.id for item in worker.children["Hosted"].commitments] == ["H1", "H2"]


@pytest.mark.asyncio
async def test_an_activation_that_changes_no_code_still_makes_its_curation_current(tmp_path):
    """A curation whose artifact leaves the code as it is restarts nothing, yet its plan, its attribution and the
    commitment list it leaves become the worker's current ones, so the round's history records this curation and
    not the one before."""
    import asyncio
    from unittest.mock import AsyncMock

    from experimental.curator.harness import CommitmentChange, Declaration, Plan
    from experimental.curator.harness.commitments import assign
    from experimental.curator.raven_adapter.deployment import activate
    from experimental.curator.raven_adapter.inspection import Inspection
    from experimental.curator.raven_adapter.targets import catalogue

    declaration = Declaration("old", catalogue())
    native = CommitmentChange(
        action="add", surface="native", statement="The host's delivery tool hands files over", serves=("task",)
    )
    plan = Plan(understanding="Keep the code; record what the host already does", commitments=assign((), [native]))
    candidate = declaration.accept(plan, {"values": {}})
    worker = SimpleNamespace(
        baseline=baseline(tmp_path / "home"),
        root=tmp_path,
        area=tmp_path,
        children={},
        commitments=(),
        artifact=Artifact(values={}),
        last_plan=Plan(understanding="The curation before"),
        _lock=asyncio.Lock(),
        _exchange=AsyncMock(return_value=True),
        _inspect=AsyncMock(return_value=Inspection(declaration, {}, {})),
        _accept=lambda candidate, inspection: candidate,
        _start=AsyncMock(),
        _close=AsyncMock(),
    )
    await activate(worker, candidate)
    assert worker.last_plan == candidate.plan and worker.last_children == {}
    assert [(item.id, item.surface) for item in worker.commitments] == [("H1", "native")]
    worker._start.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_child_curation_without_code_changes_and_a_restored_child_settle_their_commitments(tmp_path):
    """A child whose submitted candidate leaves its code as it is keeps the plan and the commitments the curation
    gave it; a child returned to its original version keeps its ids taken, every entry retired."""
    import asyncio
    from unittest.mock import AsyncMock

    from experimental.curator.harness import Commitment, CommitmentChange, Declaration, Plan
    from experimental.curator.harness.commitments import assign
    from experimental.curator.raven_adapter.deployment import activate
    from experimental.curator.raven_adapter.inspection import Inspection
    from experimental.curator.raven_adapter.inspection.runtime import declaration_for
    from experimental.curator.raven_adapter.targets import catalogue

    root_declaration, child_declaration = Declaration("root@1", catalogue()), declaration_for("hosted@1", {})
    kept, restored = Child(baseline(tmp_path / "kept")), Child(baseline(tmp_path / "restored"))
    restored.commitments = (Commitment(id="H1", surface="memory.strategy", statement="Keep notes", serves=("task",)),)
    native = CommitmentChange(action="add", surface="native", statement="The host reports back", serves=("task",))
    plan = Plan(understanding="Record what the host already does", commitments=assign((), [native]))
    submitted = child_declaration.accept(plan, {"values": {}})
    payload = {"identity": "hosted@1", "unavailable": {}, "facts": {}, "sources": {}}

    async def exchange(request):
        return True if request["operation"] == "idle" else {"inspection": payload, "revision": ""}

    worker = SimpleNamespace(
        baseline=baseline(tmp_path / "home"),
        root=tmp_path,
        area=tmp_path,
        children={"Kept": kept, "Restored": restored},
        commitments=(),
        artifact=Artifact(values={}),
        last_plan=None,
        _lock=asyncio.Lock(),
        _exchange=exchange,
        _inspect=AsyncMock(return_value=Inspection(root_declaration, {}, {})),
        _accept=lambda candidate, inspection: candidate,
        _start=AsyncMock(),
        _close=AsyncMock(),
    )
    candidate = root_declaration.accept(Plan(understanding="Revise the children"), {"values": {}})
    await activate(worker, candidate, {"Kept": submitted, "Restored": None})
    worker._start.assert_not_awaited()
    assert worker.children["Kept"].plan == plan
    assert [(item.id, item.surface) for item in worker.children["Kept"].commitments] == [("H1", "native")]
    (retired,) = worker.children["Restored"].commitments
    assert retired.id == "H1" and retired.retired and worker.children["Restored"].plan is None
    assert worker.last_children == {"Kept": submitted}


def test_a_child_carries_its_commitments_through_export_and_restore(tmp_path):
    from experimental.curator.harness import Commitment

    child = Child(baseline(tmp_path / "home"))
    child.commitments = (Commitment(id="H1", surface="memory.strategy", statement="Keep the brief", serves=("task",)),)
    assert Child.restore(json.loads(json.dumps(child.export()))).commitments == child.commitments


@pytest.mark.asyncio
async def test_reinstate_returns_exactly_to_a_kept_deployment_and_its_commitments(tmp_path):
    import asyncio
    from unittest.mock import AsyncMock

    from experimental.curator.harness import Commitment, Declaration
    from experimental.curator.raven_adapter.deployment import keep, reinstate
    from experimental.curator.raven_adapter.inspection import Inspection
    from experimental.curator.raven_adapter.targets import catalogue

    home, root = tmp_path / "home", tmp_path / "runtime"
    root.mkdir()
    old = Artifact(values={})
    supplied = Commitment(id="H1", surface="capability.strategy", statement="Supply the norms", serves=("R1",))
    worker = SimpleNamespace(
        baseline=baseline(home),
        root=root,
        area=root,
        children={},
        artifact=old,
        prepared=PreparedHarness(content={"capability": {"skills/duty/SKILL.md": "old"}}),
        last_plan="old plan",
        last_attribution=None,
        last_selection=None,
        last_children={},
        commitments=(supplied,),
        _lock=asyncio.Lock(),
        _exchange=AsyncMock(return_value=True),
        _inspect=AsyncMock(return_value=Inspection(Declaration("old", catalogue()), {}, {})),
        _preview=None,
    )
    (home / "skills/duty").mkdir(parents=True)
    (home / "skills/duty/SKILL.md").write_text("old")
    (root / "planning.json").write_text('{"version": "old"}')
    kept = await keep(worker)

    worker.artifact = Artifact(values={"action.strategy": {"factory": "gate:create"}}, files={"gate.py": "x = 1"})
    worker.prepared = PreparedHarness(
        content={"capability": {"skills/duty/SKILL.md": "new", "skills/extra/SKILL.md": "new"}}
    )
    worker.last_plan = "new plan"
    worker.commitments = (
        supplied,
        Commitment(id="H2", surface="action.strategy", statement="Gate deliveries", serves=("R2",)),
    )
    (home / "skills/duty/SKILL.md").write_text("new")
    (home / "skills/extra").mkdir(parents=True)
    (home / "skills/extra/SKILL.md").write_text("new")
    (root / "planning.json").write_text('{"version": "new"}')
    (root / "action.json").write_text('{"gate": "new"}')
    started = []

    async def close():
        pass

    async def start():
        started.append((worker.artifact, (home / "skills/duty/SKILL.md").read_text()))

    worker._close, worker._start = close, start
    await reinstate(worker, kept)
    assert worker.artifact == old and worker.last_plan == "old plan" and worker.commitments == (supplied,)
    assert started == [(old, "old")]
    assert not (home / "skills/extra/SKILL.md").exists()
    assert (root / "planning.json").read_text() == '{"version": "old"}'
    assert not (root / "action.json").exists()


@pytest.mark.asyncio
async def test_a_saved_deployment_loads_into_a_new_worker_of_the_same_task_and_refuses_another(tmp_path):
    import asyncio
    from unittest.mock import AsyncMock

    from experimental.curator.harness import Commitment, Declaration
    from experimental.curator.raven_adapter.deployment import load, save
    from experimental.curator.raven_adapter.inspection import Inspection, fingerprint
    from experimental.curator.raven_adapter.targets import catalogue

    class Worker(SimpleNamespace):
        @property
        def revision_id(self):
            return fingerprint(self.artifact.model_dump(mode="json"))

    def worker(folder, task):
        home, area = folder / "home", folder / "area"
        area.mkdir(parents=True)
        made = Worker(
            baseline=baseline(home),
            root=folder,
            area=area,
            children={},
            artifact=Artifact(values={}),
            prepared=PreparedHarness(content={}),
            last_plan=None,
            last_attribution=None,
            last_selection=None,
            last_children={},
            commitments=(),
            _lock=asyncio.Lock(),
            _exchange=AsyncMock(return_value=True),
            _inspect=AsyncMock(return_value=Inspection(Declaration("old", catalogue()), {}, {})),
            _close=AsyncMock(),
            _start=AsyncMock(),
            _preview=None,
        )
        made.baseline.task = task
        return made

    task = Task(text="Work")
    source = worker(tmp_path / "first", task)
    source.artifact = Artifact(values={"action.strategy": {"factory": "gate:create"}}, files={"gate.py": "x = 1"})
    source.prepared = PreparedHarness(content={"capability": {"skills/duty/SKILL.md": "kept"}})
    source.commitments = (Commitment(id="H1", surface="action.strategy", statement="Gate", serves=("R1",)),)
    (source.baseline.config.workspace_path / "skills/duty").mkdir(parents=True)
    (source.baseline.config.workspace_path / "skills/duty/SKILL.md").write_text("kept")
    (source.area / "planning.json").write_text('{"version": "kept"}')
    path = tmp_path / "saved" / "deployment.json"
    await save(source, path)

    target = worker(tmp_path / "second", task)
    (target.area / "action.json").write_text('{"gate": "stale"}')
    await load(target, path)
    assert target.artifact == source.artifact and target.commitments == source.commitments
    assert (target.baseline.config.workspace_path / "skills/duty/SKILL.md").read_text() == "kept"
    assert (target.area / "planning.json").read_text() == '{"version": "kept"}'
    assert not (target.area / "action.json").exists()
    assert target._start.await_count == 1

    with pytest.raises(ValueError, match="another task"):
        await load(worker(tmp_path / "third", Task(text="Work")), path)
    path.write_text(path.read_text().replace("kept", "edited"))
    with pytest.raises(ValueError, match="checksum"):
        await load(worker(tmp_path / "fourth", task), path)
