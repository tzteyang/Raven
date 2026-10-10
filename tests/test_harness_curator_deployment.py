"""Content ownership across root and managed child homes rejects ambiguous writers."""

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from experimental.harness.contract import Artifact, Task
from experimental.harness.raven_adapter.baselines import Baseline
from experimental.harness.raven_adapter.content import check_owners
from experimental.harness.raven_adapter.deployment import Child
from experimental.harness.raven_adapter.preparation import PreparedHarness
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
    from experimental.harness.curator.composition.requirements import feedback_for

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
@pytest.mark.parametrize("checkpoint", ["planning.json", "strategies.json"])
async def test_failed_activation_restores_the_checkpoint_flushed_by_shutdown(tmp_path, cleanup_fails, checkpoint):
    import asyncio
    from unittest.mock import AsyncMock

    from experimental.harness.contract import Declaration
    from experimental.harness.raven_adapter.deployment import activate
    from experimental.harness.raven_adapter.inspection import Inspection
    from experimental.harness.raven_adapter.targets import catalogue
    from tests.test_harness_curator_generation import assigned

    root = tmp_path / "runtime"
    root.mkdir()
    state = root / checkpoint
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
@pytest.mark.parametrize("checkpoint_name", ["planning.json", "strategies.json"])
async def test_root_and_child_activation_is_one_boundary_that_restores_every_home_and_checkpoint(
    tmp_path, failure, checkpoint_name
):
    """A root revision and a child revision activate together. When the restarted root fails, or a child reports a
    revision other than the one submitted, both homes' content, both artifacts and the flushed checkpoints return to
    what the shutdown left."""
    import asyncio
    from unittest.mock import AsyncMock

    from experimental.harness.contract import Commitment, Declaration
    from experimental.harness.raven_adapter.deployment import activate, child_directory
    from experimental.harness.raven_adapter.inspection import Inspection, fingerprint
    from experimental.harness.raven_adapter.inspection.runtime import declaration_for
    from experimental.harness.raven_adapter.targets import catalogue
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
    checkpoint = child_directory(runtime, "Hosted") / checkpoint_name
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

    from experimental.harness.contract import CommitmentChange, Declaration, Plan
    from experimental.harness.contract.commitments import assign
    from experimental.harness.raven_adapter.deployment import activate
    from experimental.harness.raven_adapter.inspection import Inspection
    from experimental.harness.raven_adapter.targets import catalogue

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

    from experimental.harness.contract import Commitment, CommitmentChange, Declaration, Plan
    from experimental.harness.contract.commitments import assign
    from experimental.harness.raven_adapter.deployment import activate
    from experimental.harness.raven_adapter.inspection import Inspection
    from experimental.harness.raven_adapter.inspection.runtime import declaration_for
    from experimental.harness.raven_adapter.targets import catalogue

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
    from experimental.harness.contract import Commitment

    child = Child(baseline(tmp_path / "home"))
    child.commitments = (Commitment(id="H1", surface="memory.strategy", statement="Keep the brief", serves=("task",)),)
    assert Child.restore(json.loads(json.dumps(child.export()))).commitments == child.commitments
