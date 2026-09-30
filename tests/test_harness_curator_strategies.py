"""Semantic strategy boundaries, checkpoint ownership and validated resource decisions."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import BaseModel
from pydantic_core import PydanticSerializationError

from experimental.curator.harness import Artifact, Task
from experimental.curator.harness.action import FailureEvent, ProposalEvent
from experimental.curator.harness.context import ContextRequest, ContextSource
from experimental.curator.harness.preparation import PreparationRequest
from experimental.curator.harness.resources import EffectiveCapabilities, SelectionRequest
from experimental.curator.raven_adapter.action.contracts import ActionBinding
from experimental.curator.raven_adapter.action.runtime import BoundAction
from experimental.curator.raven_adapter.capability.catalog import CapabilityCatalog
from experimental.curator.raven_adapter.capability.contracts import CapabilityBinding
from experimental.curator.raven_adapter.capability.runtime import BoundCapability
from experimental.curator.raven_adapter.context_sources import ContextFrame
from experimental.curator.raven_adapter.materialize import write_package
from experimental.curator.raven_adapter.memory.contracts import MemoryBinding
from experimental.curator.raven_adapter.memory.runtime import BoundMemory
from experimental.curator.raven_adapter.observe import Recorder
from raven.agent.tools.registry import ToolRegistry
from raven.config.raven import RavenConfig
from raven.contracts.assembled import TokenBudget
from raven.contracts.participant import StepView
from raven.memory_engine.skill_local.registry import SkillRegistry

FIXTURES = Path(__file__).parent / "fixtures/harness_curator"
ROLES = {
    "memory": (MemoryBinding, BoundMemory),
    "capability": (CapabilityBinding, BoundCapability),
    "action": (ActionBinding, BoundAction),
}


def files():
    return {
        name: (FIXTURES / name).read_text()
        for name in (
            "task_memory.py",
            "task_capability.py",
            "task_action.py",
            "strategy_bindings.py",
        )
    }


def values():
    return {
        "memory.strategy": {"factory": "task_memory:create", "observe": True},
        "capability.strategy": {"factory": "task_capability:create"},
        "action.strategy": {"factory": "task_action:create", "events": ["proposal", "outcome", "failure"]},
    }


def make(tmp_path, role, contents=None, task=None):
    package = write_package(tmp_path / "package", Artifact(values={}, files=contents or files()))
    binding, implementation = ROLES[role]
    task = task or Task(id="task", text="Find evidence")
    recorder = Recorder(tmp_path / "records.jsonl")
    recorder.turn_id = "turn"
    config = binding.model_validate(values()[f"{role}.strategy"])
    kwargs = {}
    if role == "capability":
        kwargs["catalog"] = CapabilityCatalog(
            "candidate", package, tmp_path / "assembly", material_base=tmp_path, recorder=recorder
        )
    owner = implementation(config, task, tmp_path / f"{role}.json", package, recorder, **kwargs)
    if role == "capability":
        owner.prepare_candidate(
            PreparationRequest(harness_id="test", revision="candidate", task=task, assets=contents or files())
        )
        native = RavenConfig()
        owner.stage_skills(tmp_path, native)
        registry = SkillRegistry(
            tmp_path / "home",
            builtin_skills_dir=tmp_path / "empty",
            extra_dirs=[(Path(row.path), row.name, False) for row in native.skill_forge.local_dirs],
        )
        owner.install(
            SimpleNamespace(
                loop=SimpleNamespace(
                    tools=ToolRegistry(), context=SimpleNamespace(skills=SimpleNamespace(registry=registry))
                )
            )
        )
    return owner


def step(**kwargs):
    return replace(
        StepView(
            session_key="session",
            iteration=1,
            response=None,
            transcript=(),
            history=(),
            turn_base=0,
            question="Find evidence",
            rollbacks=0,
            mode=None,
            mode_overlay=None,
            phase="iteration",
        ),
        **kwargs,
    )


async def initialize(owner):
    frame = ContextFrame(
        (ContextSource(name="identity", owner="native", kind="identity", text="IDENTITY"),),
        [{"role": "system", "content": "IDENTITY"}, {"role": "user", "content": "Question"}],
        [],
        TokenBudget(8000, 1000, 0, 1, 6999),
        True,
    )
    await owner.initialize_context(None, frame)
    return ContextRequest(
        scope=owner.scope(),
        messages=frame.messages,
        budget=7000,
        required=(1,),
        turn_start=1,
        sources=frame.sources,
        history=[],
        initialization={"prefix": "MEMORY_CONTEXT:"},
        capabilities=EffectiveCapabilities(scope=owner.scope(), tools=[]),
    )


@pytest.mark.asyncio
async def test_memory_query_is_read_only_and_a_restored_owner_resumes_shared_evidence(tmp_path):
    owner = make(tmp_path, "memory")
    await initialize(owner)
    assert (await owner.interact({"kind": "evidence", "call_id": "call", "value": "cobalt"})).stored
    before = owner.path.read_bytes()
    assert (await owner.interact({"kind": "query", "text": "cobalt"})).facts == ["cobalt"]
    assert (await owner.interact({"kind": "query", "text": "missing"})).facts == []
    assert owner.path.read_bytes() == before
    restored = make(tmp_path, "memory")
    await initialize(restored)
    assert (await restored.interact({"kind": "query", "text": "cobalt"})).facts == ["cobalt"]
    assert restored.path.read_bytes() == before


@pytest.mark.asyncio
async def test_checkpoints_reject_other_task_identity(tmp_path):
    owner = make(tmp_path, "memory")
    await owner.prepare()
    with pytest.raises(ValueError, match="another task"):
        make(tmp_path, "memory", task=Task(id="other", text="Find evidence"))


@pytest.mark.parametrize("role", ROLES)
@pytest.mark.asyncio
async def test_translation_result_validation_records_inputs_before_any_consumer_runs(tmp_path, role):
    class Detail(BaseModel):
        count: int

    class Result(BaseModel):
        detail: Detail

    owner = make(tmp_path, role)
    await owner.prepare()
    before = owner.path.read_bytes()
    supplied = {"count": 3}

    def translate(value):
        result = Result(detail=Detail(count=value["count"]))
        result.detail = {"count": value["count"]}
        return result

    with pytest.raises(PydanticSerializationError):
        owner.translate("context", translate, supplied, output=Result)
    error = next(row for row in owner.recorder.rows if row["kind"] == f"{role}.error")
    assert error["arguments"] == [supplied] and error["state"] == owner.state
    assert owner.path.read_bytes() == before
    assert owner.translate("context", lambda value: Result(detail=value), supplied, output=Result).detail.count == 3


@pytest.mark.asyncio
async def test_memory_projection_mutation_and_invalid_reply_restore_owned_state(tmp_path):
    contents = files()
    contents["task_memory.py"] = contents["task_memory.py"].replace(
        "        return ContextView(", '        self.state["bad"] = True\n        return ContextView('
    )
    owner = make(tmp_path, "memory", contents)
    request = await initialize(owner)
    before, instance = owner.path.read_bytes(), owner.strategy
    with pytest.raises(ValueError, match="changed retained state"):
        await owner.call("compose", request, source="model_input", readonly=True)
    assert "bad" not in owner.state and owner.path.read_bytes() == before
    assert owner.strategy is instance
    contents = files()
    contents["task_memory.py"] = contents["task_memory.py"].replace(
        "return Receipt(stored=True)", 'return {"wrong": True}'
    )
    owner = make(tmp_path, "memory", contents)
    await initialize(owner)
    before = owner.path.read_bytes()
    with pytest.raises(ValueError):
        await owner.interact({"kind": "evidence", "call_id": "new", "value": "wrong"})
    assert owner.scopes.shared == {"facts": {}} and owner.path.read_bytes() == before


@pytest.mark.asyncio
async def test_capability_selection_uses_active_resources_and_invalid_names_preserve_state(tmp_path):
    owner = make(tmp_path, "capability")
    await owner.prepare()
    assert await owner.catalog.tools["evidence_probe"].execute() == "FACT:cobalt"
    request = SelectionRequest(
        scope=owner.scope(),
        messages=[],
        tools=[owner.catalog.tools["evidence_probe"].to_schema()],
        skills=owner.catalog.skill_views(owner.runtime),
    )
    result = await owner.select(request)
    assert result.tools == ("evidence_probe",) and result.skills[0].name == "evidence"
    assert owner.state["selections"] == 1
    contents = files()
    contents["task_capability.py"] = contents["task_capability.py"].replace("tools=tuple(names)", 'tools=("invented",)')
    bad = make(tmp_path, "capability", contents)
    before = dict(bad.state)
    with pytest.raises(ValueError, match="offered"):
        await bad.select(request)
    assert bad.state == before
    assert any(row["kind"] == "capability.error" for row in bad.recorder.rows)


@pytest.mark.asyncio
async def test_action_reply_and_terminal_failure_have_distinct_control_allowances(tmp_path):
    owner = make(tmp_path, "action")
    await owner.prepare()
    proposal = ProposalEvent(
        scope=owner.scope(),
        event_id="proposal",
        allowed_controls=("continue", "revise", "finish"),
        stage="reply",
        text="Claim",
    )
    result = await owner.handle_event(proposal)
    assert result.control == "revise" and result.feedback
    terminal = FailureEvent(
        scope=owner.scope(),
        event_id="failure",
        allowed_controls=("continue", "finish"),
        reason="No answer",
        terminal=True,
        messages=[],
    )
    assert "incomplete" in (await owner.handle_event(terminal)).reply
    assert owner.state == {"retries": 1, "recoveries": 1}
    restored = make(tmp_path, "action")
    assert restored.state == owner.state
    with pytest.raises(ValueError, match="unsupported"):
        await owner.handle_event(proposal.model_copy(update={"allowed_controls": ("continue",)}))
    assert owner.state == restored.state


@pytest.mark.parametrize(
    "role,method", [("memory", "initialize"), ("capability", "select"), ("action", "handle_event")]
)
def test_missing_selected_operations_are_not_silent_defaults(tmp_path, role, method):
    contents = files()
    name = f"task_{role}.py"
    contents[name] = contents[name].replace(f"async def {method}(", f"async def missing_{method}(")
    with pytest.raises(TypeError):
        make(tmp_path, role, contents)


def test_removed_protocol_payloads_fail_explicitly():
    for cls, value in [
        (MemoryBinding, {"query": "bindings:query"}),
        (CapabilityBinding, {"need": "bindings:need"}),
        (ActionBinding, {"proposal": "bindings:proposal"}),
    ]:
        with pytest.raises(ValueError):
            cls(factory="strategy:create", **value)


def test_session_working_state_and_explicit_shared_knowledge_survive_reconstruction(tmp_path):
    from experimental.curator.raven_adapter.strategy import SESSION, Scopes

    task = Task(id="task", text="Serve travellers")
    memory = Scopes("memory", task, tmp_path / "memory.json", lambda state: state, per_session=True)
    for key in ("traveller:a", "traveller:b"):
        token = SESSION.set(key)
        try:
            memory.current().state["seen"] = key
            memory.shared.setdefault("seen", []).append(key)
        finally:
            SESSION.reset(token)
    memory.save()
    reopened = Scopes("memory", task, tmp_path / "memory.json", lambda state: state, per_session=True)
    assert reopened.shared == {"seen": ["traveller:a", "traveller:b"]}
    token = SESSION.set("traveller:b")
    try:
        assert reopened.current().state == {"seen": "traveller:b"} and reopened.current().resuming
    finally:
        SESSION.reset(token)


@pytest.mark.parametrize("inheritance", ["missing", "lookalike", "indirect"])
def test_strategy_factory_requires_the_public_protocol_in_its_inheritance_chain(tmp_path, inheritance):
    """One role stands for all: the check is the same line of `BoundStrategy` for every protocol."""
    role = "action"
    contents = files()
    path = f"task_{role}.py"
    name = role.title()
    protocol = f"{name}Strategy"
    line = next(line for line in contents[path].splitlines() if line.startswith(f"class {name}("))
    if inheritance == "missing":
        replacement = f"class {name}:"
    elif inheritance == "lookalike":
        replacement = f"class {protocol}:\n    pass\n\n\nclass {name}({protocol}):"
    else:
        base = line.replace(f"class {name}(", f"class Shared{name}(", 1)
        replacement = f"{base}\n    pass\n\n\nclass {name}(Shared{name}):"
    contents[path] = contents[path].replace(line, replacement)
    if inheritance == "indirect":
        assert make(tmp_path, role, contents).strategy is not None
    else:
        with pytest.raises(TypeError, match=f"explicitly inheriting {protocol}"):
            make(tmp_path, role, contents)
