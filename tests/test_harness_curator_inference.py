"""Strategy inference preserves host scope, effective model parameters, allowances and failure boundaries."""

import asyncio
import json
from typing import Literal

import pytest
from pydantic import BaseModel, ConfigDict

from experimental.curator.harness.inference import InferenceError, InferenceRequest
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
        self.running = self.most = 0

    def get_default_model(self):
        return "worker/model"

    async def chat(self, **parameters):
        self.requests.append(parameters)
        self.started.set()
        self.running += 1
        self.most = max(self.most, self.running)
        try:
            await asyncio.sleep(0)
            if self.block:
                await asyncio.Event().wait()
            response = self.response(parameters) if callable(self.response) else self.response
            if isinstance(response, Exception):
                raise response
            return response
        finally:
            self.running -= 1

    async def chat_with_retry(self, **parameters):
        raise AssertionError("the retry ladder must not be used")


def inference(tmp_path, provider=None, **limits):
    recorder = Recorder(tmp_path / "observations.jsonl")
    recorder.turn_id = "turn-a"
    provider = provider or Provider()
    return Inference(provider, recorder, **limits), provider, recorder


async def judge(infer, **sampling):
    return await infer(
        instruction="Check the supplied evidence.", data={"evidence": []}, output_type=Verdict, **sampling
    )


@pytest.mark.asyncio
async def test_an_operation_and_its_peers_share_an_allowance_of_calls_and_the_turn_has_its_own(tmp_path):
    infer, provider, recorder = inference(tmp_path, operation_calls=2, turn_calls=3)
    group = OperationGroup()
    async with owner_operation("action", asyncio.Lock(), group=group, operation="handle_event", source_id="event-a"):
        result = await judge(infer, max_output_tokens=400)
        assert result.verdict == "insufficient_evidence"
        async with owner_operation("memory", asyncio.Lock(), group=group, operation="interact"):
            await judge(infer)
            with pytest.raises(InferenceError, match="0 of its 2 inference calls left"):
                await judge(infer)
    async with owner_operation("action", asyncio.Lock(), group=group):
        await judge(infer)
        with pytest.raises(InferenceError, match="turn budget"):
            await judge(infer)
    assert len(provider.requests) == 3
    request = provider.requests[0]
    assert {key: value for key, value in request.items() if key != "messages"} == {
        "model": "worker/model",
        "max_tokens": 400,
        "tools": None,
        "tool_choice": None,
    }
    assert '"additionalProperties": false' in request["messages"][0]["content"]
    events = [row for row in recorder.rows if row["kind"] in {"strategy.inference", "strategy.inference.result"}]
    assert len(events) == 6
    assert events[0]["operation_id"] == events[1]["operation_id"] == events[2]["operation_id"]
    assert events[0]["source_id"] == "event-a"
    assert events[0]["timeout"] == 20
    infer.release("turn-a")
    recorder.turn_id = "turn-b"
    async with owner_operation("action", asyncio.Lock(), group=group):
        await judge(infer)
    assert len(provider.requests) == 4


@pytest.mark.asyncio
async def test_the_turn_input_allowance_bounds_many_small_judgments(tmp_path):
    infer, provider, _ = inference(tmp_path, turn_input_bytes=900)
    async with owner_operation("action", asyncio.Lock(), group=OperationGroup()):
        await judge(infer)
        with pytest.raises(InferenceError, match="turn input allowance"):
            await judge(infer)
    assert len(provider.requests) == 1


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
async def test_invalid_judgments_fail_without_repair_and_each_call_spends_the_allowance(tmp_path, response):
    infer, provider, recorder = inference(tmp_path, Provider(response), operation_calls=2)
    async with owner_operation("action", asyncio.Lock(), group=OperationGroup()):
        for _ in range(2):
            with pytest.raises(InferenceError):
                await judge(infer)
        with pytest.raises(InferenceError, match="calls left"):
            await judge(infer)
    assert len(provider.requests) == 2
    assert not any(row["kind"] == "strategy.inference.result" for row in recorder.rows)
    assert sum(row["kind"] == "strategy.inference.error" for row in recorder.rows) == 3


@pytest.mark.asyncio
async def test_the_strategy_chooses_its_sampling_and_the_rest_follows_the_workers_own_settings(tmp_path):
    infer, provider, recorder = inference(tmp_path)
    async with owner_operation("action", asyncio.Lock(), group=OperationGroup()):
        await judge(infer, max_output_tokens=800, reasoning_effort="minimal")
        await judge(infer)
    chosen, inherited = provider.requests
    assert (chosen["max_tokens"], chosen["reasoning_effort"]) == (800, "minimal")
    assert "max_tokens" not in inherited and "reasoning_effort" not in inherited and "temperature" not in inherited
    first, second = [row["parameters"] for row in recorder.rows if row["kind"] == "strategy.inference"]
    assert first["chosen"] == ["max_tokens", "reasoning_effort"] and second["chosen"] == []
    assert (second["max_tokens"], second["reasoning_effort"], second["temperature"]) == (1024, "low", 0.2)
    described = infer.describe()
    assert described["max_output_tokens"] == {
        "chosen_by": "strategy",
        "default": 1024,
        "ceiling": 1024,
        "includes_reasoning": True,
    }
    assert described["reasoning_effort"] == {"chosen_by": "strategy", "choices": ["low", "minimal"], "default": "low"}
    assert (described["max_calls_per_operation"], described["max_calls_per_turn"]) == (12, 48)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sampling",
    [
        {"max_output_tokens": 0},
        {"max_output_tokens": True},
        {"max_output_tokens": "4096"},
        {"max_output_tokens": 4096},
        {"reasoning_effort": "extreme"},
        {"reasoning_effort": "high"},
    ],
)
async def test_unaccepted_or_stronger_sampling_is_refused_before_the_call_and_spends_nothing(tmp_path, sampling):
    infer, provider, _ = inference(tmp_path, operation_calls=1)
    async with owner_operation("action", asyncio.Lock(), group=OperationGroup()):
        with pytest.raises(ValueError):
            await judge(infer, **sampling)
        assert (await judge(infer)).verdict == "insufficient_evidence"
    assert len(provider.requests) == 1


@pytest.mark.asyncio
async def test_a_worker_without_its_own_effort_leaves_a_judgment_none_to_choose(tmp_path):
    provider = Provider()
    provider.generation = GenerationSettings(timeout=20)
    infer, _, _ = inference(tmp_path, provider)
    assert infer.describe()["reasoning_effort"]["choices"] == []
    async with owner_operation("action", asyncio.Lock(), group=OperationGroup()):
        with pytest.raises(ValueError, match="may not exceed the worker's own"):
            await judge(infer, reasoning_effort="minimal")
        await judge(infer, max_output_tokens=50000)
    assert provider.requests[0]["max_tokens"] == 50000


@pytest.mark.asyncio
async def test_a_cut_off_judgment_says_why(tmp_path):
    provider = Provider(
        LLMResponse(content='{"verdict":"sat', finish_reason="length", usage={"completion_tokens": 900})
    )
    infer, _, recorder = inference(tmp_path, provider)
    async with owner_operation("action", asyncio.Lock(), group=OperationGroup()):
        with pytest.raises(InferenceError):
            await judge(infer, max_output_tokens=900)
    (error,) = [row for row in recorder.rows if row["kind"] == "strategy.inference.error"]
    assert "finish_reason=length" in error["error"] and "completion_tokens" in error["error"]


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
async def test_tasks_the_strategy_starts_and_escaped_callbacks_cannot_judge(tmp_path):
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
async def test_each_judges_a_batch_at_once_and_returns_every_result_or_its_error_in_order(tmp_path):
    def answer(parameters):
        rule = json.loads(parameters["messages"][1]["content"])["rule"]
        if rule == "broken":
            return LLMResponse(content="not JSON")
        return LLMResponse(content=json.dumps({"verdict": "satisfied", "explanation": rule}))

    infer, provider, recorder = inference(tmp_path, Provider(answer), operation_calls=3)
    async with owner_operation("action", asyncio.Lock(), group=OperationGroup(), source_id="event-a"):
        verdicts = await infer.each(
            [
                InferenceRequest("Judge the first rule.", {"rule": "first"}),
                {"instruction": "Judge the broken rule.", "data": {"rule": "broken"}},
                ("Judge the last rule.", {"rule": "last"}),
            ],
            output_type=Verdict,
        )
        with pytest.raises(InferenceError, match="0 of its 3 inference calls left"):
            await judge(infer)
    assert [verdict.explanation for verdict in (verdicts[0], verdicts[2])] == ["first", "last"]
    assert isinstance(verdicts[1], InferenceError) and verdicts[1].kind == "result"
    assert provider.most == 3
    calls = [row for row in recorder.rows if row["kind"] == "strategy.inference"]
    assert [row["call"] for row in calls] == [1, 2, 3] and {row["source_id"] for row in calls} == {"event-a"}


@pytest.mark.asyncio
async def test_a_batch_is_admitted_whole_or_refused_whole(tmp_path):
    infer, provider, _ = inference(tmp_path, operation_calls=2)
    requests = [InferenceRequest("Judge.", {"rule": number}) for number in range(3)]
    async with owner_operation("action", asyncio.Lock(), group=OperationGroup()):
        with pytest.raises(InferenceError, match="2 of its 2 inference calls left"):
            await infer.each(requests, output_type=Verdict)
        with pytest.raises(ValueError, match="at least one"):
            await infer.each([], output_type=Verdict)
        assert len(await infer.each(requests[:2], output_type=Verdict)) == 2
    assert len(provider.requests) == 2


@pytest.mark.asyncio
async def test_cancelling_a_batch_cancels_every_judgment_in_it(tmp_path):
    provider = Provider()
    provider.block = True
    infer, _, recorder = inference(tmp_path, provider)

    async def operation():
        async with owner_operation("action", asyncio.Lock(), group=OperationGroup()):
            await infer.each([InferenceRequest("Judge.", {"rule": number}) for number in range(3)], output_type=Verdict)

    task = asyncio.create_task(operation())
    await asyncio.wait_for(provider.started.wait(), 1)
    while provider.running < 3:
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert provider.running == 0
    assert sum(row.get("error_kind") == "cancelled" for row in recorder.rows) == 3


@pytest.mark.asyncio
async def test_an_operation_has_a_time_window_for_its_judgments(tmp_path):
    infer, provider, recorder = inference(tmp_path, operation_seconds=0.05)
    async with owner_operation("action", asyncio.Lock(), group=OperationGroup()):
        await judge(infer)
        assert [row["timeout"] for row in recorder.rows if row["kind"] == "strategy.inference"][0] < 1
        await asyncio.sleep(0.06)
        with pytest.raises(InferenceError, match="inference time is spent"):
            await judge(infer)
    assert len(provider.requests) == 1
    infer, provider, _ = inference(tmp_path, operation_seconds=0.05, turn_input_bytes=900)
    async with owner_operation("action", asyncio.Lock(), group=OperationGroup()):
        with pytest.raises(InferenceError, match="input allowance"):
            await infer(instruction="Check.", data={"evidence": ["x" * 1000]}, output_type=Verdict)
        await asyncio.sleep(0.06)
        await judge(infer)
    assert len(provider.requests) == 1


@pytest.mark.asyncio
async def test_timeout_spends_a_call_and_cancellation_remains_cancellation(tmp_path):
    provider = Provider()
    provider.block = True
    infer, _, recorder = inference(tmp_path, provider, timeout=0.02, operation_calls=1)
    async with owner_operation("action", asyncio.Lock(), group=OperationGroup()):
        with pytest.raises(InferenceError) as error:
            await judge(infer)
        assert error.value.kind == "timeout"
        with pytest.raises(InferenceError, match="calls left"):
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
