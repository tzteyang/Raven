"""Single-step inference preserves host scope, effective model parameters and failure boundaries."""

import asyncio
from typing import Literal

import pytest
from pydantic import BaseModel, ConfigDict

from experimental.curator.harness.inference import InferenceError
from experimental.curator.raven_adapter.calls import OperationGroup, owner_operation
from experimental.curator.raven_adapter.inference import Inference
from experimental.curator.raven_adapter.observe import Recorder
from raven.contracts.llm_provider import GenerationSettings, LLMResponse, ToolCallRequest


class Verdict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: Literal["satisfied", "needs_revision", "insufficient_evidence"]
    explanation: str


class Provider:
    generation = GenerationSettings(temperature=0.2, max_tokens=1024, reasoning_effort="low", timeout=20)

    def __init__(self, response=None):
        self.response = response or LLMResponse(
            content='{"verdict":"insufficient_evidence","explanation":"No receipt"}'
        )
        self.requests = []
        self.started = asyncio.Event()
        self.block = False

    def get_default_model(self):
        return "worker/model"

    async def chat(self, **parameters):
        self.requests.append(parameters)
        self.started.set()
        if self.block:
            await asyncio.Event().wait()
        if isinstance(self.response, Exception):
            raise self.response
        return self.response

    async def chat_with_retry(self, **parameters):
        raise AssertionError("the retry ladder must not be used")


def inference(tmp_path, provider=None, **limits):
    recorder = Recorder(tmp_path / "observations.jsonl")
    recorder.turn_id = "turn-a"
    provider = provider or Provider()
    return Inference(provider, recorder, **limits), provider, recorder


async def judge(infer):
    return await infer(instruction="Check the supplied evidence.", data={"evidence": []}, output_type=Verdict)


@pytest.mark.asyncio
async def test_one_attempt_is_shared_with_peers_and_turn_budget_survives_new_operations(tmp_path):
    infer, provider, recorder = inference(tmp_path, max_calls=1, max_output_tokens=400)
    group = OperationGroup()
    async with owner_operation("action", asyncio.Lock(), group=group, operation="handle_event", source_id="event-a"):
        result = await judge(infer)
        assert result.verdict == "insufficient_evidence"
        async with owner_operation("memory", asyncio.Lock(), group=group, operation="interact"):
            with pytest.raises(InferenceError, match="already spent"):
                await judge(infer)
    async with owner_operation("action", asyncio.Lock(), group=group):
        with pytest.raises(InferenceError, match="turn budget"):
            await judge(infer)
    assert len(provider.requests) == 1
    request = provider.requests[0]
    assert {key: request[key] for key in ("model", "max_tokens", "temperature", "reasoning_effort", "tools")} == {
        "model": "worker/model",
        "max_tokens": 400,
        "temperature": 0.2,
        "reasoning_effort": "low",
        "tools": None,
    }
    assert '"additionalProperties": false' in request["messages"][0]["content"]
    events = [row for row in recorder.rows if row["kind"] in {"strategy.inference", "strategy.inference.result"}]
    assert len(events) == 2
    assert events[0]["operation_id"] == events[1]["operation_id"]
    assert events[0]["source_id"] == "event-a"
    assert events[0]["timeout"] == 20
    infer.release("turn-a")
    recorder.turn_id = "turn-b"
    async with owner_operation("action", asyncio.Lock(), group=group):
        await judge(infer)
    assert len(provider.requests) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        LLMResponse(content="not JSON"),
        LLMResponse(content='{"verdict":"satisfied","explanation":"ok","control":"finish"}'),
        LLMResponse(content='{"verdict":"invented","explanation":"ok"}'),
        LLMResponse(content=""),
        LLMResponse(content='{"verdict":"satisfied","explanation":"ok"}', finish_reason="length"),
        LLMResponse(content="{}", tool_calls=[ToolCallRequest(id="call", name="exec", arguments={})]),
        RuntimeError("provider failed"),
    ],
)
async def test_invalid_judgments_fail_without_repair_or_a_second_attempt(tmp_path, response):
    infer, provider, recorder = inference(tmp_path, Provider(response))
    async with owner_operation("action", asyncio.Lock(), group=OperationGroup()):
        with pytest.raises(InferenceError):
            await judge(infer)
        with pytest.raises(InferenceError, match="already spent"):
            await judge(infer)
    assert len(provider.requests) == 1
    assert not any(row["kind"] == "strategy.inference.result" for row in recorder.rows)
    assert any(row["kind"] == "strategy.inference.error" for row in recorder.rows)


@pytest.mark.asyncio
async def test_scope_input_and_active_turn_are_enforced_before_the_provider_call(tmp_path):
    infer, provider, recorder = inference(tmp_path, max_input_bytes=10)
    with pytest.raises(InferenceError, match="current host"):
        await judge(infer)
    async with owner_operation("action", asyncio.Lock(), group=OperationGroup()):
        recorder.turn_id = None
        with pytest.raises(InferenceError, match="active worker turn"):
            await judge(infer)
        recorder.turn_id = "turn-a"
        with pytest.raises(InferenceError, match="byte allowance"):
            await judge(infer)
    assert provider.requests == []


@pytest.mark.asyncio
async def test_background_and_escaped_callbacks_cannot_acquire_another_allowance(tmp_path):
    infer, provider, _ = inference(tmp_path)
    resume = asyncio.Event()

    async def escaped():
        await resume.wait()
        return await judge(infer)

    async with owner_operation("action", asyncio.Lock(), group=OperationGroup()):
        with pytest.raises(InferenceError, match="current host"):
            await asyncio.create_task(judge(infer))
        delayed = asyncio.create_task(escaped())
    resume.set()
    with pytest.raises(InferenceError, match="current host"):
        await delayed
    assert provider.requests == []


@pytest.mark.asyncio
async def test_timeout_spends_the_attempt_and_cancellation_remains_cancellation(tmp_path):
    provider = Provider()
    provider.block = True
    infer, _, recorder = inference(tmp_path, provider, timeout=0.02)
    async with owner_operation("action", asyncio.Lock(), group=OperationGroup()):
        with pytest.raises(InferenceError) as error:
            await judge(infer)
        assert error.value.kind == "timeout"
        with pytest.raises(InferenceError, match="already spent"):
            await judge(infer)
    infer.timeout = 30
    provider.started.clear()

    async def operation():
        async with owner_operation("action", asyncio.Lock(), group=OperationGroup()):
            await judge(infer)

    task = asyncio.create_task(operation())
    await asyncio.wait_for(provider.started.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(provider.requests) == 2
    assert recorder.rows[-1]["error_kind"] == "cancelled"
