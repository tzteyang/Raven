"""Scope, provenance, read-only boundaries and partial failure across live strategy owners."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from experimental.curator.harness import Artifact, Task
from experimental.curator.harness.context import ContextRequest, ContextSource
from experimental.curator.harness.interaction import InteractionScope, InteractionTool
from experimental.curator.harness.resources import EffectiveCapabilities
from experimental.curator.raven_adapter.action.contracts import ActionBinding
from experimental.curator.raven_adapter.action.runtime import BoundAction
from experimental.curator.raven_adapter.calls import OperationGroup, owner_operation
from experimental.curator.raven_adapter.context_sources import ContextFrame, SourceContext
from experimental.curator.raven_adapter.materialize import write_package
from experimental.curator.raven_adapter.memory.context import ProjectionOverflowError
from experimental.curator.raven_adapter.memory.contracts import MemoryBinding
from experimental.curator.raven_adapter.memory.runtime import BoundMemory
from experimental.curator.raven_adapter.memory.window import MemoryWindow
from experimental.curator.raven_adapter.model_input import ModelInput
from experimental.curator.raven_adapter.observe import Recorder
from experimental.curator.raven_adapter.peers import RuntimePeers
from experimental.curator.raven_adapter.strategy import SESSION
from raven.contracts.assembled import TokenBudget
from raven.contracts.harness import ShrinkResult, WindowPressure, WindowState


@pytest.mark.asyncio
@pytest.mark.parametrize("overflow", [True, False])
async def test_model_input_classifies_only_projection_pressure(tmp_path, overflow):
    view = EffectiveCapabilities(
        scope=InteractionScope(task_id="pressure", session_key="session", harness_id="test", revision="test"), tools=[]
    )
    recorder = Recorder(tmp_path / "observations.jsonl")
    native = SimpleNamespace(decide=AsyncMock())
    error = ProjectionOverflowError(101, 100) if overflow else ValueError("protected source removed")
    memory = SimpleNamespace(project=AsyncMock(side_effect=error))
    capability = SimpleNamespace(effective=lambda tools: view, recorder=recorder)
    sources = SimpleNamespace(frame=lambda session: None, projection_sources=lambda *args, **kwargs: ())
    adapter = ModelInput(native, capability, sources, memory)
    request = SimpleNamespace(messages=[{"role": "user", "content": "Preserve this request."}], tools=[])
    if overflow:
        result = await adapter.decide(request)
        assert result.finish_reason == "error"
        assert result.error_classification.should_compress
        assert result.error_classification.category == "context_overflow"
        assert "model.input.pressure" in recorder.path.read_text()
    else:
        with pytest.raises(ValueError, match="protected source removed"):
            await adapter.decide(request)
    native.decide.assert_not_awaited()


@pytest.mark.asyncio
async def test_concurrent_opposite_peer_chains_complete_without_lock_inversion():
    group = OperationGroup()
    locks = {name: asyncio.Lock() for name in ("memory", "action")}
    entered, requested, proceed = asyncio.Event(), asyncio.Event(), asyncio.Event()
    completed = []

    async def first():
        async with owner_operation("memory", locks["memory"], group=group):
            entered.set()
            await proceed.wait()
            async with owner_operation("action", locks["action"], group=group):
                completed.append("memory-action")

    async def second():
        await entered.wait()
        requested.set()
        async with owner_operation("action", locks["action"], group=group):
            async with owner_operation("memory", locks["memory"], group=group):
                completed.append("action-memory")

    tasks = [asyncio.create_task(first()), asyncio.create_task(second())]
    await requested.wait()
    await asyncio.sleep(0)
    proceed.set()
    await asyncio.wait_for(asyncio.gather(*tasks), timeout=2)
    assert completed == ["memory-action", "action-memory"]


@pytest.mark.asyncio
async def test_parallel_children_cannot_bypass_the_current_strategy_chain():
    group = OperationGroup()

    async def child():
        async with owner_operation("memory", asyncio.Lock(), group=group):
            pytest.fail("a parallel child entered the parent's ownership chain")

    async with owner_operation("action", asyncio.Lock(), group=group):
        with pytest.raises(RuntimeError, match="parallel strategy requests"):
            await asyncio.create_task(child())


CODE = """from pydantic import BaseModel
from experimental.curator.harness.strategies import MemoryStrategy, ActionStrategy
from experimental.curator.harness.context import InitialContext, ContextRequest, ContextView, CompactionRequest
from experimental.curator.harness.interaction import InteractionRequest
from experimental.curator.harness.action import ActionInteraction, ActionResponse

class Command(BaseModel):
    text: str
class Reply(BaseModel):
    count: int

class Memory(MemoryStrategy[bool, Command, Reply]):
    def __init__(self, state, shared, peers):
        self.state, self.shared, self.peers = state, shared, peers
    async def initialize(self, initial: InitialContext) -> bool:
        self.state.setdefault("initialized", True)
        self.shared.setdefault("notes", [])
        return True
    async def interact(self, request: InteractionRequest[Command]) -> Reply:
        if request.command.text == "read":
            return Reply(count=len(self.shared["notes"]))
        self.state["calls"] = self.state.get("calls", 0) + 1
        self.shared["notes"].append(request.command.text)
        if request.command.text == "cycle":
            await self.peers.request_action({"text": "cycle"})
        return Reply(count=len(self.shared["notes"]))
    async def compose(self, request: ContextRequest) -> ContextView:
        await self.peers.interact_memory({"text": "forbidden-write"})
        return ContextView(messages=request.messages)
    async def compact(self, request: CompactionRequest) -> ContextView:
        return ContextView(messages=[
            message for index, message in enumerate(request.messages)
            if index >= request.turn_start or message["role"] in {"system", "developer"}
        ])

class Action(ActionStrategy[Command, Reply]):
    def __init__(self, state, peers):
        self.state, self.peers = state, peers
    async def handle_request(self, request: ActionInteraction[Command]) -> ActionResponse[Reply]:
        self.state["calls"] = self.state.get("calls", 0) + 1
        receipt = await self.peers.interact_memory({"text": request.command.text})
        if request.command.text == "partial":
            raise ValueError("the later action step failed")
        return ActionResponse(reply=Reply(count=receipt["count"]))

def memory(state, task, *, shared, peers):
    return Memory(state, shared, peers)
def action(state, task, *, peers):
    return Action(state, peers)
"""


@pytest.fixture
def owners(tmp_path):
    token = SESSION.set("session:a")
    try:
        recorder = Recorder(tmp_path / "records.jsonl")
        recorder.turn_id = "turn:a"
        task = Task(id="task", text="Retain information through explicit interactions.")
        package = write_package(tmp_path / "package", Artifact(values={}, files={"owners.py": CODE}))
        peers = RuntimePeers(recorder)

        def scope():
            return InteractionScope(
                harness_id="root",
                task_id=task.id,
                revision="first",
                session_key=SESSION.get(),
                turn_id=recorder.turn_id,
            )

        memory = BoundMemory(
            MemoryBinding(
                factory="owners:memory",
                tool=InteractionTool(name="memory_notes", description="Record notes."),
                compact=("proactive", "overflow"),
            ),
            task,
            tmp_path / "memory.json",
            package,
            recorder,
            peers=peers,
            scope=scope,
        )
        action = BoundAction(
            ActionBinding(factory="owners:action", events=(), requests=True),
            task,
            tmp_path / "action.json",
            package,
            recorder,
            peers=peers,
            scope=scope,
        )
        peers.bind(memory=memory, action=action)
        budget = TokenBudget(
            context_length=8000,
            reserved_output=1000,
            reserved_tools=0,
            reserved_system=1,
            available_history=6999,
        )
        frame = ContextFrame(
            (ContextSource(name="identity", owner="native", kind="identity", text="IDENTITY"),),
            [{"role": "system", "content": "IDENTITY"}, {"role": "user", "content": "Current question"}],
            [],
            budget,
            True,
        )
        yield SimpleNamespace(memory=memory, action=action, peers=peers, recorder=recorder, scope=scope, frame=frame)
    finally:
        SESSION.reset(token)


def test_skill_source_projection_targets_the_assembled_user_message_after_a_correction():
    source = ContextSource(
        name="skill_menu", owner="native", kind="skills", role="user", text="SKILL_MENU", required=False
    )
    original = {"role": "user", "content": "Runtime\nSKILL_MENU\n\nQuestion"}
    frame = ContextFrame((source,), [original], [], None, True)
    correction = {"role": "user", "content": "Correct the previous answer."}
    messages = [original, correction]
    projected = SourceContext().strip_native_skills(messages, frame)
    assert projected == [{"role": "user", "content": "Runtime\n\n\nQuestion"}, correction]
    assert messages[0] == original and "SKILL_MENU" in original["content"]


@pytest.mark.asyncio
async def test_peer_calls_use_one_owner_and_a_later_failure_does_not_undo_another_owner(owners):
    await owners.memory.initialize_context("session:a", owners.frame)
    result = await owners.action.request({"text": "retained"}, origin="strategy")
    assert result["reply"]["count"] == 1
    assert owners.memory.scopes.shared["notes"] == ["retained"]
    assert owners.action.state["calls"] == 1
    with pytest.raises(ValueError, match="later action step failed"):
        await owners.action.request({"text": "partial"}, origin="strategy")
    assert owners.action.state["calls"] == 1
    assert owners.memory.scopes.shared["notes"] == ["retained", "partial"]
    assert any(row["kind"] == "strategy.peer_result" and row["target"] == "memory" for row in owners.recorder.rows)


@pytest.mark.asyncio
async def test_awaited_owner_cycle_is_rejected_before_deadlock_and_restores_each_failed_owner(owners):
    await owners.memory.initialize_context("session:a", owners.frame)
    with pytest.raises(RuntimeError, match="cyclic strategy operation"):
        await asyncio.wait_for(owners.action.request({"text": "cycle"}), timeout=1)
    assert "calls" not in owners.action.state
    assert "calls" not in owners.memory.state
    assert owners.memory.scopes.shared["notes"] == []


@pytest.mark.asyncio
async def test_compose_cannot_reenter_its_own_owner_through_a_peer(owners):
    await owners.memory.initialize_context("session:a", owners.frame)
    request = ContextRequest(
        scope=owners.scope(),
        messages=owners.frame.messages,
        budget=7000,
        required=(1,),
        turn_start=1,
        sources=owners.frame.sources,
        history=[],
        initialization=True,
        capabilities=EffectiveCapabilities(scope=owners.scope(), tools=[]),
    )
    with pytest.raises(RuntimeError, match="cyclic strategy operation"):
        await owners.memory.call("compose", request, source="model_input", readonly=True)
    assert owners.memory.scopes.shared["notes"] == []
    assert "calls" not in owners.memory.state


@pytest.mark.asyncio
async def test_model_tool_arguments_cannot_select_host_identity_or_observation_provenance(owners):
    await owners.memory.initialize_context("session:a", owners.frame)
    with pytest.raises(ValueError):
        await owners.memory.tool().execute(request={"text": "forged"}, origin="observation")
    assert owners.memory.scopes.shared["notes"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["read", "attempted-write"])
async def test_planning_query_propagates_readonly_to_memory(owners, tmp_path, text):
    from experimental.curator.raven_adapter.planning.runtime import BoundPlanning
    from tests.test_harness_curator_planning_binding import binding, files

    await owners.memory.initialize_context("session:a", owners.frame)
    contents = files()
    contents["task_planning.py"] = contents["task_planning.py"].replace(
        "        change = request.command",
        f'        await self.peers.interact_memory({{"text": "{text}"}}, mode="command")\n'
        "        change = request.command",
    )
    contents["task_planning.py"] += (
        "\n_original_create = create\ndef create(state, *, peers):\n"
        "    value = _original_create(state)\n    value.peers = peers\n    return value\n"
    )
    package = write_package(tmp_path / "planning-package", Artifact(values={}, files=contents))
    planning = BoundPlanning(
        binding(),
        Task(id="task", text="Verify"),
        tmp_path / "planning.json",
        package,
        owners.recorder,
        peers=owners.peers,
        scope=owners.scope,
    )
    owners.peers.bind(memory=owners.memory, planning=planning, action=owners.action)
    await planning.prepare()
    if text == "read":
        result = await owners.peers.interact_planning({"operation": "view"}, mode="query")
        assert result["items"] == {"Verify": False}
    else:
        with pytest.raises(ValueError, match="read-only"):
            await owners.peers.interact_planning({"operation": "view"}, mode="query")
    assert owners.memory.scopes.shared["notes"] == []
    assert "calls" not in owners.memory.state
    request = next(
        row for row in owners.recorder.rows if row["kind"] == "memory.call" and row["operation"] == "interact"
    )
    assert request["arguments"][0]["mode"] == "query"


@pytest.mark.asyncio
async def test_cancelled_required_event_cannot_become_a_silent_native_noop(owners):
    async def cancelled():
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await owners.action._guard(SimpleNamespace(messages=[], metadata={}), cancelled)
    with pytest.raises(RuntimeError, match="interrupted"):
        owners.action.model_guidance(None)
    await owners.action.finish()


@pytest.mark.asyncio
async def test_selected_pressure_paths_share_native_retry_budget_and_delegate_image_handling(owners):
    await owners.memory.initialize_context("session:a", owners.frame)
    sources = SourceContext()
    sources.frames["session:a"] = owners.frame
    delegated = []

    class Native:
        def token_budget(self):
            return owners.frame.budget

        async def shrink(self, messages, *, pressure, state, model):
            delegated.append(pressure)
            return ShrinkResult(messages, False)

    native = Native()
    loop = SimpleNamespace(
        tools=SimpleNamespace(get_definitions=lambda: []),
        harness=SimpleNamespace(memory=native),
        _compaction=SimpleNamespace(trigger_ratio=0.85),
    )
    owners.memory.runtime = SimpleNamespace(loop=loop)
    owners.memory.context_sources = sources
    wrapper = MemoryWindow(native, owners.memory, SimpleNamespace(read=lambda: None), loop)
    messages = [
        owners.frame.messages[0],
        {"role": "user", "content": "Old request"},
        {"role": "assistant", "content": "history " * 9000},
        owners.frame.messages[-1],
    ]
    state = WindowState(image_window=2, last_context_used=7900)
    result = await wrapper.shrink(messages, pressure=WindowPressure.PROACTIVE, state=state, model=None)
    assert result.changed and result.messages == owners.frame.messages
    assert state.compress_retries == 1 and state.last_context_used == 0
    result = await wrapper.shrink(messages, pressure=WindowPressure.STANDING, state=state, model=None)
    assert not result.changed and delegated == [WindowPressure.STANDING]
    result = await wrapper.shrink(messages, pressure=WindowPressure.OVERFLOW, state=state, model=None)
    assert result.changed and state.compress_retries == 2
    result = await wrapper.shrink(messages, pressure=WindowPressure.OVERFLOW, state=state, model=None)
    assert not result.changed and state.compress_retries == 2
    assert (
        len([row for row in owners.recorder.rows if row["kind"] == "memory.call" and row["operation"] == "compact"])
        == 2
    )
