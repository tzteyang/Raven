"""Planning binding validates concrete contracts and preserves task state on failures."""

import json
from pathlib import Path

import pytest
from pydantic_core import PydanticSerializationError

from experimental.curator.harness import Artifact, Task
from experimental.curator.raven_adapter.materialize import write_package
from experimental.curator.raven_adapter.observe import Recorder
from experimental.curator.raven_adapter.planning.contracts import PlanningBinding, PlanningObservation
from experimental.curator.raven_adapter.planning.runtime import BoundPlanning

FIXTURES = Path(__file__).parent / "fixtures/harness_curator"


def files():
    return {name: (FIXTURES / name).read_text() for name in ("task_planning.py", "planning_bindings.py")}


def binding():
    return PlanningBinding(
        factory="task_planning:create",
        tool={"name": "curator_planning", "description": "Read or update the task plan."},
        context=True,
        observe=("before_model", "after_iteration"),
        requests=True,
    )


def make(tmp_path, *, contents=None, task=None):
    package = write_package(tmp_path / "package", Artifact(values={}, files=contents or files()))
    return BoundPlanning(
        binding(),
        task or Task(id="task", text="Verify"),
        tmp_path / "state.json",
        package,
        Recorder(tmp_path / "records.jsonl"),
    )


@pytest.mark.asyncio
async def test_one_checkpoint_connects_tool_context_evidence_and_reconstruction(tmp_path):
    planning = make(tmp_path)
    await planning.prepare()
    assert planning.facts()["view"]["items"] == {"Verify": False}
    tool = planning.tool()
    assert "operation" in str(tool.parameters)
    await tool.execute(request={"operation": "complete", "item": "Verify"})
    assert '"Verify":true' in await planning.addendum()
    evidence = PlanningObservation(
        scope=planning.scope(),
        event_id="event",
        phase="after_iteration",
        iteration=1,
        messages=[{"role": "tool", "name": "planning_probe", "tool_call_id": "check", "content": "EVIDENCE:failed"}],
        response=None,
    )
    await planning.observe(evidence)
    await planning.observe(evidence)
    assert planning.state["seen"] == ["check"]
    assert planning.facts()["view"]["items"] == {"Verify": False}
    before = planning.path.read_bytes()
    restored = make(tmp_path)
    await restored.prepare()
    assert restored.path.read_bytes() == before
    assert restored.facts()["view"] == planning.facts()["view"]
    assert restored.state["seen"] == ["check"]
    with pytest.raises(ValueError, match="another task"):
        make(tmp_path, task=Task(id="different", text="Verify"))


@pytest.mark.asyncio
async def test_observation_contract_failure_retains_replay_inputs_and_owned_state(tmp_path):
    contents = files()
    contents["task_planning.py"] = contents["task_planning.py"].replace(
        "class Evidence(BaseModel):",
        "class Stamp(BaseModel):\n    sequence: int\n\n\nclass Evidence(BaseModel):\n    stamp: Stamp | None = None",
    )
    contents["planning_bindings.py"] = (
        contents["planning_bindings.py"]
        .replace("return Evidence(", "change = Evidence(")
        .replace(
            "    return None\n\n\nclass Probe",
            '                change.stamp = {"sequence": 1}\n                return change\n    return None\n\n\nclass Probe',
        )
    )
    planning = make(tmp_path, contents=contents)
    await planning.prepare()
    before = planning.path.read_bytes()
    observation = PlanningObservation(
        scope=planning.scope(),
        event_id="event",
        phase="after_iteration",
        iteration=2,
        messages=[{"role": "tool", "name": "planning_probe", "tool_call_id": "result", "content": "EVIDENCE:passed"}],
        response=None,
    )
    with pytest.raises(PydanticSerializationError, match="Stamp"):
        await planning.observe(observation)
    assert planning.path.read_bytes() == before
    error = next(row for row in planning.recorder.rows if row["kind"] == "planning.error")
    assert error["operation"] == "observe"
    assert error["arguments"][1] == observation.model_dump(mode="json")
    assert error["state"] == planning.state
    assert not any(row["kind"] == "planning.call" and row["operation"] == "interact" for row in planning.recorder.rows)
    contents["planning_bindings.py"] = contents["planning_bindings.py"].replace(
        'change.stamp = {"sequence": 1}',
        'change = type(change).model_validate({**change.model_dump(), "stamp": {"sequence": 1}})',
    )
    repaired = make(tmp_path, contents=contents)
    await repaired.prepare()
    await repaired.observe(PlanningObservation.model_validate(error["arguments"][1]))
    assert repaired.current_view["items"] == {"Verify": True}


@pytest.mark.asyncio
async def test_tool_inputs_cannot_select_the_observation_lane(tmp_path):
    planning = make(tmp_path)
    await planning.prepare()
    before = planning.path.read_bytes()
    for request in ({"operation": "evidence", "item": "Verify"}, {"operation": "view", "trusted": True}):
        with pytest.raises(ValueError):
            await planning.tool().execute(request=request)
    assert planning.path.read_bytes() == before


@pytest.mark.asyncio
async def test_invalid_return_restores_mutable_state_and_reconstructs_the_owner(tmp_path):
    contents = files()
    contents["task_planning.py"] = contents["task_planning.py"].replace(
        'self.state["items"][change.item] = True',
        'self.state["items"][change.item] = True\n            return {"wrong": "view"}',
    )
    planning = make(tmp_path, contents=contents)
    await planning.prepare()
    before = planning.path.read_bytes()
    with pytest.raises(ValueError):
        await planning.tool().execute(request={"operation": "complete", "item": "Verify"})
    assert planning.path.read_bytes() == before
    assert json.loads(await planning.tool().execute(request={"operation": "view"}))["items"] == {"Verify": False}


@pytest.mark.asyncio
async def test_factory_migration_is_explicit_but_initialize_cannot_reset_progress(tmp_path):
    planning = make(tmp_path)
    await planning.prepare()
    await planning.tool().execute(request={"operation": "complete", "item": "Verify"})
    contents = files()
    contents["task_planning.py"] = contents["task_planning.py"].replace(
        "return Planning(state)", 'state.setdefault("migration", "explicit")\n    return Planning(state)'
    )
    migrated = make(tmp_path, contents=contents)
    await migrated.prepare()
    assert migrated.state["migration"] == "explicit"
    assert migrated.current_view["items"]["Verify"]
    contents = files()
    contents["task_planning.py"] = contents["task_planning.py"].replace("if not self.state:", "if True:")
    reset = make(tmp_path, contents=contents)
    before = reset.path.read_bytes()
    with pytest.raises(ValueError, match="changed existing state"):
        await reset.prepare()
    assert reset.path.read_bytes() == before


@pytest.mark.asyncio
async def test_changed_policy_rejects_unverified_completion_without_losing_state(tmp_path):
    planning = make(tmp_path)
    await planning.prepare()
    contents = files()
    contents["task_planning.py"] = contents["task_planning.py"].replace(
        "GUARD_COMPLETION = False", "GUARD_COMPLETION = True"
    )
    guarded = make(tmp_path, contents=contents)
    await guarded.prepare()
    before = guarded.path.read_bytes()
    with pytest.raises(ValueError, match="verified execution"):
        await guarded.tool().execute(request={"operation": "complete", "item": "Verify"})
    assert guarded.path.read_bytes() == before
    assert guarded.current_view["guarded"]


@pytest.mark.asyncio
async def test_each_session_keeps_its_own_plan_across_restarts(tmp_path):
    from experimental.curator.raven_adapter.strategy import SESSION
    from raven.permissions.turn import start_permission_turn

    # Outside an explicit session the key falls back to the current turn's conversation, and a turn another test
    # bound in this process would otherwise name one here.
    start_permission_turn(None, conversation_id="", turn_id="unattended")
    planning = make(tmp_path)
    await planning.prepare()
    tool = planning.tool()
    token = SESSION.set("traveller:a")
    try:
        await tool.execute(request={"operation": "complete", "item": "Verify"})
        assert '"Verify":true' in await planning.addendum()
    finally:
        SESSION.reset(token)
    token = SESSION.set("traveller:b")
    try:
        assert '"Verify":false' in await planning.addendum()
    finally:
        SESSION.reset(token)
    assert planning.facts()["view"]["items"] == {"Verify": False}
    assert set(planning.facts()["sessions"]) == {"traveller:a", "traveller:b"}
    restored = make(tmp_path)
    token = SESSION.set("traveller:a")
    try:
        assert '"Verify":true' in await restored.addendum()
    finally:
        SESSION.reset(token)


@pytest.mark.asyncio
async def test_other_components_read_a_detached_copy_of_their_own_conversations_plan(tmp_path):
    from experimental.curator.raven_adapter.strategy import SESSION

    planning = make(tmp_path)
    token = SESSION.set("traveller:a")
    try:
        assert planning.read() is None
        await planning.tool().execute(request={"operation": "complete", "item": "Verify"})
        seen = planning.read()
        assert seen["items"] == {"Verify": True}
        seen["items"]["Verify"] = False
        assert planning.read()["items"] == {"Verify": True}
    finally:
        SESSION.reset(token)
    token = SESSION.set("traveller:b")
    try:
        assert planning.read() is None
        await planning.addendum()
        assert planning.read()["items"] == {"Verify": False}
    finally:
        SESSION.reset(token)


@pytest.mark.asyncio
@pytest.mark.parametrize("effect", ["state", "projection"])
async def test_queries_cannot_change_state_or_publish_different_guidance(tmp_path, effect):
    contents = files()
    replacement = (
        '            self.state["unexpected"] = True\n'
        if effect == "state"
        else '            projection = projection.model_copy(update={"guidance": "NEW_GUIDANCE"})\n'
    )
    contents["task_planning.py"] = contents["task_planning.py"].replace(
        "            return PlanningResult[View, View](reply=projection.view, projection=projection)",
        replacement + "            return PlanningResult[View, View](reply=projection.view, projection=projection)",
    )
    planning = make(tmp_path, contents=contents)
    await planning.prepare()
    before, view = planning.path.read_bytes(), planning.read()
    with pytest.raises(ValueError, match="query changed"):
        await planning.tool().execute(request={"operation": "view"}, mode="query")
    assert planning.path.read_bytes() == before
    assert planning.read() == view
    assert "unexpected" not in planning.state
    assert "NEW_GUIDANCE" not in planning.latest_projection.guidance


@pytest.mark.asyncio
async def test_business_refusal_can_record_a_blocker_and_returns_only_its_reply(tmp_path):
    contents = files()
    source = contents["task_planning.py"].replace("GUARD_COMPLETION = False", "GUARD_COMPLETION = True")
    source = source.replace("Command | Evidence, View]", "Command | Evidence, dict]")
    source = source.replace("PlanningResult[View, View]", "PlanningResult[View, dict]")
    source = source.replace("reply=projection.view,", "reply=projection.view.model_dump(),")
    source = source.replace(
        '                raise ValueError("completion requires verified execution evidence")',
        '                self.state["blocker"] = "Missing execution evidence"\n'
        '                return PlanningResult[View, dict](reply={"accepted": False, "reason": self.state["blocker"]}, projection=self._projection())',
    )
    contents["task_planning.py"] = source
    planning = make(tmp_path, contents=contents)
    result = json.loads(await planning.tool().execute(request={"operation": "complete", "item": "Verify"}))
    assert result == {"accepted": False, "reason": "Missing execution evidence"}
    assert planning.state["blocker"] == "Missing execution evidence"
    assert planning.read()["items"] == {"Verify": False}
    assert "projection" not in result


@pytest.mark.asyncio
async def test_failed_checkpoint_does_not_publish_a_new_plan(tmp_path, monkeypatch):
    planning = make(tmp_path)
    await planning.prepare()
    before = planning.path.read_bytes()

    def fail():
        raise OSError("checkpoint unavailable")

    monkeypatch.setattr(planning.scopes, "save", fail)
    with pytest.raises(OSError, match="checkpoint unavailable"):
        await planning.interact({"operation": "complete", "item": "Verify"})
    assert planning.path.read_bytes() == before
    assert planning.read()["items"] == {"Verify": False}
    assert planning.state["items"] == {"Verify": False}


@pytest.mark.asyncio
async def test_projection_subclasses_share_the_same_public_view_contract(tmp_path):
    contents = files()
    code = contents["task_planning.py"].replace("PlanningProjection[View]", "Projection")
    code = code.replace("PlanningResult[View, View]", "Result")
    code = code.replace(
        "class Planning(",
        "class Projection(PlanningProjection[View]):\n    pass\n\n\n"
        "class Result(PlanningResult[View, View]):\n    pass\n\n\nclass Planning(",
    )
    contents["task_planning.py"] = code
    planning = make(tmp_path, contents=contents)
    await planning.prepare()
    await planning.interact({"operation": "complete", "item": "Verify"})
    result = await planning.interact({"operation": "view"}, mode="query")
    assert result.reply.items == {"Verify": True}
    before = planning.path.read_bytes()
    restored = make(tmp_path, contents=contents)
    await restored.prepare()
    assert restored.read() == planning.read()
    assert restored.path.read_bytes() == before


def test_projection_subclasses_cannot_hide_a_different_view_contract(tmp_path):
    contents = files()
    code = contents["task_planning.py"].replace(
        "class Planning(", "class OtherView(View):\n    pass\n\n\nclass Planning("
    )
    contents["task_planning.py"] = code.replace("PlanningResult[View, View]", "PlanningResult[OtherView, View]")
    with pytest.raises(TypeError, match="same view type"):
        make(tmp_path, contents=contents)


def test_projection_domain_extensions_belong_in_the_view(tmp_path):
    contents = files()
    code = contents["task_planning.py"].replace("PlanningProjection[View]", "Projection")
    contents["task_planning.py"] = code.replace(
        "class Planning(",
        'class Projection(PlanningProjection[View]):\n    extra_domain_field: str = "value"\n\n\nclass Planning(',
    )
    with pytest.raises(TypeError, match="put domain fields in ViewT"):
        make(tmp_path, contents=contents)


@pytest.mark.asyncio
async def test_planning_factory_reader_is_session_scoped_and_only_reads_committed_state(tmp_path):
    from experimental.curator.raven_adapter.strategy import SESSION

    contents = files()
    contents["task_planning.py"] = contents["task_planning.py"].replace(
        '            self.state["items"][change.item] = True',
        '            self.state["items"][change.item] = True\n            self.observed_committed = self.plan_reader()',
    )
    contents["task_planning.py"] += (
        "\n_original_create = create\ndef create(state, *, plan):\n"
        "    owner = _original_create(state)\n    owner.plan_reader = plan\n"
        "    owner.initial_read = plan()\n    return owner\n"
    )
    planning = make(tmp_path, contents=contents)
    assert planning.strategy.initial_read is None
    await planning.prepare()
    await planning.interact({"operation": "complete", "item": "Verify"})
    assert planning.strategy.observed_committed["items"] == {"Verify": False}
    detached = planning.strategy.plan_reader()
    detached["items"]["Verify"] = False
    assert planning.read()["items"] == {"Verify": True}
    token = SESSION.set("other-session")
    try:
        assert planning.strategy.initial_read is None
        await planning.prepare()
        assert planning.strategy.plan_reader()["items"] == {"Verify": False}
    finally:
        SESSION.reset(token)
    assert planning.read()["items"] == {"Verify": True}
