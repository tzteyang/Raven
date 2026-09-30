"""Prompt resources, proactive guidance and memory projection reach native worker execution."""

from copy import deepcopy
from functools import partial

import pytest

from experimental.curator.harness import Task
from experimental.curator.raven_adapter.worker import Worker, WorkerError
from raven.contracts.llm_provider import LLMResponse
from tests.integration.test_harness_curator_e2e import baseline as baseline
from tests.integration.test_harness_curator_e2e import plan_for, replay_provider
from tests.test_harness_curator_generation import response

ACTION = """from pydantic import BaseModel, ConfigDict
from experimental.curator.harness.prompts import Prompt
from experimental.curator.harness.preparation import PreparationRequest
from experimental.curator.harness.strategies import ActionStrategy
from experimental.curator.harness.action import ActionEvent, ActionDecision

class Inputs(BaseModel):
    goal: str
    question: str

class Guidance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str

GUIDANCE = Prompt.from_file(__file__, "prompts/guide.md", Inputs)

class Action(ActionStrategy[None, None]):
    def __init__(self, state, task, infer, host):
        self.state, self.task, self.infer, self.host = state, task, infer, host
    def prepare(self, request: PreparationRequest) -> None:
        self.host.prompt("action:GUIDANCE")
    async def handle_event(self, event: ActionEvent) -> ActionDecision:
        if event.kind != "progress":
            return ActionDecision()
        self.state["guidance_calls"] = self.state.get("guidance_calls", 0) + 1
        question = next(row["content"] for row in reversed(event.messages) if row["role"] == "user")
        inputs = Inputs(goal=self.task.text, question=question)
        return ActionDecision(guidance=GUIDANCE.render(inputs))

def create(state, task, *, infer, host):
    return Action(state, task, infer, host)
"""
MEMORY = """from experimental.curator.harness.strategies import MemoryStrategy
from experimental.curator.harness.context import InitialContext, ContextRequest, ContextView, CompactionRequest

class Memory(MemoryStrategy[bool, str, bool]):
    async def initialize(self, initial: InitialContext) -> bool:
        return True
    async def compose(self, request: ContextRequest) -> ContextView:
        return ContextView(messages=[*request.messages[:-1],
            {"role": "assistant", "content": "noise " * request.budget}, request.messages[-1]])
    async def compact(self, request: CompactionRequest) -> ContextView:
        required = [request.messages[i] for i in request.required]
        systems = [message for message in request.messages if message["role"] == "system"]
        return ContextView(messages=[*systems,
            {"role": "assistant", "content": "MEMORY_COMPACTED"}, *required])

def create(state, task):
    return Memory()
"""


def artifact():
    return {
        "values": {
            "action.strategy": {"factory": "action:create", "events": ["progress"]},
        },
        "files": {"action.py": ACTION, "prompts/guide.md": "GUIDANCE_A: $goal / $question"},
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_prompt_guidance_reaches_model_and_revision_preserves_state(baseline, tmp_path):
    baseline.task = Task(id="prompt-task", text="Use evidence")
    async with Worker(baseline, tmp_path / "runtime", provider_factory=replay_provider, timeout=30) as worker:
        proposed = artifact()
        inspection = await worker.inspect()
        candidate = inspection.declaration.accept(plan_for(*proposed["values"]), proposed)
        assert (await worker.check(candidate)).passed
        await worker.install(candidate)
        first = await worker.run("First question")
        assert not first.errors
        assert any(
            "GUIDANCE_A: Use evidence /" in str(row) and "First question" in str(row)
            for row in first.records
            if row["kind"] == "provider.request"
        )
        facts = (await worker.inspect()).facts
        assert facts["prompts"]["action:GUIDANCE"]["input_schema"]["required"] == ["goal", "question"]
        assert facts["action"]["sessions"]["curator:task"]["guidance_calls"] == 1
        change = {
            "values": {"action.strategy": proposed["values"]["action.strategy"]},
            "files": {"prompts/guide.md": "GUIDANCE_B: $goal / $question"},
        }
        inspection = await worker.inspect()
        await worker.install(inspection.declaration.accept(plan_for("action.strategy"), change))
        second = await worker.run("Second question")
        assert not second.errors
        assert any(
            "GUIDANCE_B: Use evidence /" in str(row) and "Second question" in str(row)
            for row in second.records
            if row["kind"] == "provider.request"
        )
        assert (await worker.inspect()).facts["action"]["sessions"]["curator:task"]["guidance_calls"] == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_memory_compacts_native_context_and_rejects_lost_protected_messages(baseline, tmp_path):
    baseline.task = Task(text="Keep the current goal")
    proposed = {
        "values": {"memory.strategy": {"factory": "memory:create", "compact": ["projection"]}},
        "files": {"memory.py": MEMORY},
    }
    async with Worker(baseline, tmp_path / "runtime", provider_factory=replay_provider, timeout=30) as worker:
        inspection = await worker.inspect()
        await worker.install(inspection.declaration.accept(plan_for(*proposed["values"]), proposed))
        result = await worker.run("Keep this exact current question")
        assert not result.errors
        assert any(row["kind"] == "memory.call" and row["operation"] == "compact" for row in result.records)
        assert any(
            "MEMORY_COMPACTED" in str(row) and "Keep this exact current question" in str(row)
            for row in result.records
            if row["kind"] == "provider.request"
        )
        bad = deepcopy(proposed)
        bad["files"]["memory.py"] = bad["files"]["memory.py"].replace(
            'systems = [message for message in request.messages if message["role"] == "system"]', "systems = []"
        )
        inspection = await worker.inspect()
        await worker.install(inspection.declaration.accept(plan_for("memory.strategy"), bad))
        with pytest.raises(WorkerError, match="protected") as failed:
            await worker.run("Preserve the user message")
        assert not any(row["kind"] == "provider.request" for row in failed.value.records)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_strategy_inference_is_distinct_from_worker_model_decision(baseline, tmp_path):
    baseline.task = Task(text="Use an explicit inference dependency")
    proposed = artifact()
    proposed["files"]["action.py"] = proposed["files"]["action.py"].replace(
        "return ActionDecision(guidance=GUIDANCE.render(inputs))",
        "answer = await self.infer(instruction=GUIDANCE.render(inputs), data={}, output_type=Guidance)\n"
        "        return ActionDecision(guidance=answer.text)",
    )
    provider = partial(
        replay_provider,
        responses=[LLMResponse(content='{"text":"INFERRED_GUIDANCE"}'), LLMResponse(content="Final answer")],
    )
    async with Worker(baseline, tmp_path / "runtime", provider_factory=provider, timeout=30) as worker:
        inspection = await worker.inspect()
        await worker.install(inspection.declaration.accept(plan_for(*proposed["values"]), proposed))
        result = await worker.run("Work")
        assert not result.errors
        assert any(row["kind"] == "strategy.inference" for row in result.records)
        requests = [row for row in result.records if row["kind"] == "provider.request"]
        assert len(requests) == 2 and "INFERRED_GUIDANCE" in str(requests[-1])


SEMANTIC_ACTION = """from typing import Literal
from pydantic import BaseModel, ConfigDict
from experimental.curator.harness.action import ActionEvent, ActionDecision
from experimental.curator.harness.preparation import PreparationRequest
from experimental.curator.harness.prompts import Prompt
from experimental.curator.harness.strategies import ActionStrategy

class Criteria(BaseModel):
    goal: str

class Judgment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: Literal["satisfied", "needs_revision", "insufficient_evidence"]
    explanation: str

CHECK = Prompt.from_file(__file__, "review.md", Criteria)

class Action(ActionStrategy[None, None]):
    def __init__(self, task, infer, host):
        self.task, self.infer, self.host = task, infer, host

    def prepare(self, request: PreparationRequest) -> None:
        self.host.prompt("action:CHECK")

    async def handle_event(self, event: ActionEvent) -> ActionDecision:
        if event.kind != "proposal" or event.stage != "CHECK_STAGE":
            return ActionDecision()
        result = await self.infer(
            instruction=CHECK.render(Criteria(goal=self.task.text)),
            data={"candidate": event.text, "calls": [call.model_dump(mode="json") for call in event.calls]},
            output_type=Judgment,
        )
        if result.verdict == "satisfied":
            return ActionDecision()
        if event.stage == "dispatch":
            return ActionDecision(control="reject", feedback=result.explanation)
        if "revise" in event.allowed_controls:
            return ActionDecision(control="revise", feedback=result.explanation)
        return ActionDecision(control="finish", reply="The required check could not establish completion.")

def create(state, task, *, infer, host):
    return Action(task, infer, host)
"""


def semantic_artifact(stage):
    return {
        "values": {
            "action.strategy": {"factory": "action:create", "events": ["proposal"], "dispatch": stage == "dispatch"}
        },
        "files": {
            "action.py": SEMANTIC_ACTION.replace("CHECK_STAGE", stage),
            "review.md": "Evaluate the candidate against $goal using only supplied evidence. "
            "Distinguish a violation from insufficient evidence and explain the needed correction.",
        },
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_semantic_result_resamples_the_main_loop_with_one_attempt_per_proposal(baseline, tmp_path):
    baseline.task = Task(text="Do not claim completion without supporting evidence.")
    provider = partial(
        replay_provider,
        responses=[
            LLMResponse(content="Unsupported candidate"),
            LLMResponse(content='{"verdict":"needs_revision","explanation":"State what remains unverified."}'),
            LLMResponse(content="Corrected candidate: verification is still outstanding."),
            LLMResponse(content='{"verdict":"satisfied","explanation":"The limitation is explicit."}'),
        ],
    )
    async with Worker(baseline, tmp_path / "runtime", provider_factory=provider, timeout=45) as worker:
        proposed = semantic_artifact("reply")
        inspection = await worker.inspect()
        await worker.install(inspection.declaration.accept(plan_for(*proposed["values"]), proposed))
        execution = await worker.run("Report the outcome.")
        assert not execution.errors
        assert "Corrected candidate" in execution.text and "Unsupported candidate" not in execution.text
        judgments = [row for row in execution.records if row["kind"] == "strategy.inference.result"]
        assert len(judgments) == 2 and len({row["operation_id"] for row in judgments}) == 2
        requests = [row for row in execution.records if row["kind"] == "provider.request"]
        assert len(requests) == 4
        assert sum(row["method"] == "chat" for row in requests) == 2
        assert any(
            "State what remains unverified." in str(row["parameters"]["messages"])
            for row in requests
            if row["method"] != "chat"
        )
        assert any(
            row["kind"] == "action.control"
            and row["receipt"]["control"] == "revise"
            and row["receipt"]["status"] == "applied"
            and row["receipt"]["source_id"] == judgments[0]["source_id"]
            for row in execution.records
        )
        assert (await worker.inspect()).facts["inference"]["attempts_per_operation_chain"] == 1


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "judgment",
    [
        '{"verdict":"insufficient_evidence","explanation":"The requested destination is not established."}',
        "invalid judgment JSON",
    ],
)
async def test_semantic_dispatch_refusal_and_failed_check_do_not_execute_the_tool(baseline, tmp_path, judgment):
    destination = baseline.workdir / "unapproved.txt"
    baseline.task = Task(text="Write only to an established destination.")
    baseline.config.permissions.tools["write_file"] = "allow"
    provider = partial(
        replay_provider,
        responses=[
            response("write_file", {"path": str(destination), "content": "must not be written"}),
            LLMResponse(content=judgment),
            LLMResponse(content="No file was written."),
        ],
    )
    async with Worker(baseline, tmp_path / "runtime", provider_factory=provider, timeout=45) as worker:
        proposed = semantic_artifact("dispatch")
        inspection = await worker.inspect()
        await worker.install(inspection.declaration.accept(plan_for(*proposed["values"]), proposed))
        execution = await worker.run("Prepare the requested output.")
        assert not destination.exists()
        assert len([row for row in execution.records if row["kind"] == "strategy.inference"]) == 1
        if judgment.startswith("{"):
            assert any(
                row["kind"] == "action.control"
                and row["receipt"]["control"] == "reject"
                and row["receipt"]["status"] == "applied"
                for row in execution.records
            )
        else:
            assert any(
                row["kind"] == "strategy.inference.error" and row["error_kind"] == "result" for row in execution.records
            )
