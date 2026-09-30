"""Code-owned resources and setup exercised through the actual isolated Raven worker."""

from functools import partial

import pytest

from experimental.curator.harness import Task
from experimental.curator.raven_adapter.worker import Worker
from raven.contracts.llm_provider import LLMResponse
from raven.session.manager import SessionManager
from tests.integration.test_harness_curator_e2e import baseline as baseline
from tests.integration.test_harness_curator_e2e import plan_for, replay_provider

pytestmark = pytest.mark.integration

CODE = """from experimental.curator.harness.preparation import PreparationRequest
from experimental.curator.harness.context import InitialContext, ContextRequest, ContextView
from experimental.curator.harness.resources import (
    CapabilityContribution, CapabilitySelection, RegistrationReceipt, SelectionRequest, SkillContribution,
)
from experimental.curator.harness.strategies import CapabilityStrategy, MemoryStrategy

class Memory(MemoryStrategy[dict, str, str]):
    def __init__(self, host):
        self.host = host
    def prepare(self, request: PreparationRequest) -> None:
        self.host.profile({"TOOLS.md": request.assets["profile.md"]})
    async def initialize(self, initial: InitialContext) -> dict:
        return {"sources": [source.name for source in initial.sources]}
    async def compose(self, request: ContextRequest) -> ContextView:
        return ContextView(messages=request.messages)

class Capability(CapabilityStrategy):
    def __init__(self, registrar):
        self.registrar = registrar
    def _prepare_skills(self, request: PreparationRequest) -> tuple[SkillContribution, ...]:
        return (SkillContribution(name="evidence", source="Provided expert material", files={
            "SKILL.md": request.assets["skill/SKILL.md"],
            "references/fact.md": request.assets["skill/references/fact.md"],
        }),)
    def register(self, contribution: CapabilityContribution) -> RegistrationReceipt:
        return self.registrar.register(contribution)
    async def select(self, request: SelectionRequest) -> CapabilitySelection:
        return CapabilitySelection()

def memory(state, task, *, host):
    return Memory(host)
def capability(state, task, *, registrar):
    return Capability(registrar)
"""


async def read_installed_reference(bound):
    source = bound.capability.catalog.skill_root / "evidence" / "references" / "fact.md"
    result = await bound.runtime.loop.tools.execute("read_file", {"path": str(source)})
    assert "EVIDENCE:amber-72" in str(result)


@pytest.mark.asyncio
async def test_code_preparation_adopts_assets_and_changes_native_context_with_reversible_withdrawal(baseline, tmp_path):
    baseline.task = Task(text="Build an expert from supplied materials.")
    baseline.config.tools.restrict_to_workspace = True
    profile = baseline.config.workspace_path / "TOOLS.md"
    profile.write_text("Original native profile")
    async with Worker(baseline, tmp_path / "runtime", provider_factory=replay_provider, timeout=45) as worker:
        view = await worker.inspect()
        assert {target.name for target in view.declaration.targets} == {
            "memory.strategy",
            "planning.strategy",
            "capability.strategy",
            "action.strategy",
        }
        with pytest.raises(ValueError):
            view.declaration.accept(plan_for("capability.resources"), {"values": {"capability.resources": []}})
        candidate = view.declaration.accept(
            plan_for("memory.strategy", "capability.strategy"),
            {
                "values": {
                    "memory.strategy": {"factory": "policy:memory"},
                    "capability.strategy": {"factory": "policy:capability"},
                },
                "files": {
                    "policy.py": CODE,
                    "profile.md": "EXPERT_PROFILE: use the installed evidence procedure.",
                    "skill/SKILL.md": "---\nname: evidence\ndescription: Inspect supplied evidence.\n---\nRead references/fact.md.",
                    "skill/references/fact.md": "EVIDENCE:amber-72",
                },
            },
        )
        checked = await worker.check(candidate, probe=read_installed_reference)
        assert checked.passed, checked.errors
        assert profile.read_text() == "Original native profile"
        installed = await worker.install(candidate)
        assert "EXPERT_PROFILE" in profile.read_text()
        assert installed.facts["capability_resources"]["installed"]
        outcome = await worker.run("Describe your working method briefly.")
        assert not outcome.errors
        assert any("EXPERT_PROFILE" in str(row) for row in outcome.records if row["kind"] == "provider.request")
        view = await worker.inspect()
        withdrawal = view.declaration.accept(
            plan_for("memory.strategy", "capability.strategy"),
            {
                "values": {},
                "remove": ["memory.strategy", "capability.strategy"],
            },
        )
        restored = await worker.install(withdrawal)
        assert profile.read_text() == "Original native profile"
        assert not any(row["name"] == "evidence" for row in restored.facts["skills"])
        assert worker.artifact.files["skill/references/fact.md"] == "EVIDENCE:amber-72"


@pytest.mark.asyncio
async def test_memory_lifecycle_keeps_raw_input_and_stamps_the_native_turn_record(baseline, tmp_path):
    baseline.task = Task(text="Keep original information and actual completion records.")
    code = """from pydantic import JsonValue
from experimental.curator.harness.context import InitialContext, ContextRequest, ContextView
from experimental.curator.harness.strategies import MemoryStrategy
from experimental.curator.raven_adapter.memory.contracts import MemoryInput, MemoryArchive

class Memory(MemoryStrategy[dict, str, str]):
    def __init__(self, state):
        self.state = state
    async def _intake(self, request: MemoryInput) -> str | None:
        self.state.setdefault("raw", []).append(request.text)
        return request.text + "\\nMODEL_DERIVED_NOTE"
    async def initialize(self, initial: InitialContext) -> dict:
        return {"observed_inputs": len(self.state["raw"])}
    async def compose(self, request: ContextRequest) -> ContextView:
        return ContextView(messages=request.messages)
    async def _archive(self, request: MemoryArchive) -> dict[str, JsonValue] | None:
        return {"memory_summary": {"raw": self.state["raw"][-1], "reply": request.reply}}
def create(state, task):
    return Memory(state)
"""
    async with Worker(baseline, tmp_path / "runtime", provider_factory=replay_provider, timeout=45) as worker:
        view = await worker.inspect()
        candidate = view.declaration.accept(
            plan_for("memory.strategy"),
            {
                "values": {"memory.strategy": {"factory": "memory:create", "intake": True, "archive": True}},
                "files": {"memory.py": code},
            },
        )
        await worker.install(candidate)
        result = await worker.run("Original customer request.")
        assert not result.errors
        assert any("MODEL_DERIVED_NOTE" in str(row) for row in result.records if row["kind"] == "provider.request")
        session = SessionManager(baseline.config.workspace_path).get_or_create("curator:task")
        assert any(row.get("content") == "Original customer request." for row in session.messages)
        assert any(
            row.get("observers", {}).get("memory_summary", {}).get("raw") == "Original customer request."
            for row in session.messages
        )


ACTION_CODE = """from experimental.curator.harness.action import ActionDecision, InputEvent, ProposalEvent, GenerationOverrides
from experimental.curator.harness.strategies import ActionStrategy

class Action(ActionStrategy[str, str]):
    async def _handle_input(self, event: InputEvent) -> ActionDecision:
        if event.text == "Stop at intake.":
            return ActionDecision(control="finish", reply="Stopped before model execution.")
        return ActionDecision()
    async def _handle_proposal(self, event: ProposalEvent) -> ActionDecision:
        if event.stage == "reply" and event.text == "DRAFT":
            return ActionDecision(control="revise", feedback="Use the verified final response.",
                                  generation=GenerationOverrides(temperature=0.3, max_tokens=512))
        return ActionDecision()
def create(state, task):
    return Action()
"""


@pytest.mark.asyncio
async def test_action_protected_handlers_deliver_early_control_and_native_resample_parameters(baseline, tmp_path):
    baseline.task = Task(text="Apply control at the appropriate native phase.")
    factory = partial(replay_provider, responses=[LLMResponse(content="DRAFT"), LLMResponse(content="FINAL")])
    async with Worker(baseline, tmp_path / "runtime", provider_factory=factory, timeout=45) as worker:
        view = await worker.inspect()
        candidate = view.declaration.accept(
            plan_for("action.strategy"),
            {
                "values": {"action.strategy": {"factory": "action:create", "events": ["input", "proposal"]}},
                "files": {"action.py": ACTION_CODE},
            },
        )
        await worker.install(candidate)
        early = await worker.run("Stop at intake.")
        assert not early.errors
        assert "Stopped before model execution." in early.text
        assert not any(row["kind"] == "provider.request" for row in early.records)
        assert any(row["kind"] == "action.control" and row["receipt"]["status"] == "applied" for row in early.records)
        revised = await worker.run("Produce the verified final reply.")
        assert not revised.errors
        requests = [row for row in revised.records if row["kind"] == "provider.request"]
        assert len(requests) == 2
        assert requests[1]["parameters"]["temperature"] == 0.3
        assert requests[1]["parameters"]["max_tokens"] == 512
        assert revised.text == "FINAL"
