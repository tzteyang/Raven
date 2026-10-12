"""Execution accounting invariants, checked against transport sends and persisted snapshots."""

import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace

import httpx
import pytest

from raven.observability import execution
from raven.observability.ledger import FILENAME, Ledger, LedgerError, merge, read_tree
from raven.observability.report import build, read
from raven.providers.anthropic_messages_provider import AnthropicMessagesProvider
from raven.providers.litellm_provider import LiteLLMProvider


def test_snapshots_are_idempotent_and_reject_conflicts(tmp_path):
    with execution.run(tmp_path):
        with execution.attempt("test", "model") as request:
            request.usage({"prompt_tokens": 100, "completion_tokens": 10})
            first = deepcopy(request.row)
            request.usage({"completion_tokens": 15, "cost_usd": 0}, complete=True)
        final = deepcopy(request.row)
    ledger = Ledger(tmp_path / FILENAME)
    ledger.put(first)
    ledger.put(final)
    ledger.put(final)
    found = read(tmp_path)["attempts"]
    assert len(found) == 1 and found[0] == {**final, "part": "simulation"}
    assert merge([first, final, first, final]) == [final]
    with pytest.raises(LedgerError, match="Conflicting"):
        ledger.put({**final, "status": "different"})
    with pytest.raises(LedgerError, match="identity changed"):
        ledger.put({**final, "version": final["version"] + 1, "parent_id": "wrong-stage"})
    totals = read(tmp_path)["totals"]
    assert totals["output_tokens"] == 15 and totals["cost_usd"] == 0
    assert totals["input_tokens"] is None and totals["input_total_tokens"] == 100
    assert totals["cache_read_tokens"] is None


def test_unknown_usage_is_not_zero_and_cache_is_not_counted_twice(tmp_path):
    with execution.run(tmp_path):
        with execution.attempt("test", "model") as request:
            request.usage(
                {
                    "prompt_tokens": 100,
                    "completion_tokens": 20,
                    "cache_read_input_tokens": 70,
                    "cache_creation_input_tokens": 10,
                    "cost_usd": 0,
                },
                complete=True,
            )
        with execution.attempt("test", "model"):
            pass
    totals = read(tmp_path)["totals"]
    assert totals["input_total_tokens"] == 100
    assert totals["input_tokens"] == 20
    assert totals["missing"]["cost_usd"] == 1 and totals["cost_usd"] == 0
    assert totals["missing"]["output_tokens"] == 1


@pytest.mark.asyncio
async def test_concurrent_scopes_and_detached_work_keep_their_owner(tmp_path):
    ready = asyncio.Event()

    async def child():
        await ready.wait()
        with execution.attempt("test", "model") as request:
            request.usage({"completion_tokens": 3})

    async def branch(stage):
        with execution.scope(stage, stage=stage):
            task = asyncio.create_task(child())
        return task

    with execution.run(tmp_path):
        tasks = await asyncio.gather(branch("trial"), branch("assess"))
        ready.set()
        await asyncio.gather(*tasks)
    report = read(tmp_path)
    assert {row["attributes"]["stage"] for row in report["attempts"]} == {"trial", "assess"}
    assert report["totals"]["output_tokens"] == 6
    assert not report["missing_parents"]
    assert execution.current() is None


@pytest.mark.asyncio
async def test_cancellation_records_partial_usage_and_restores_context(tmp_path):
    async def cancelled():
        with execution.scope("trial"):
            with execution.attempt("test", "model") as request:
                request.usage({"prompt_tokens": 7})
                raise asyncio.CancelledError

    with execution.run(tmp_path):
        parent = execution.current()
        with pytest.raises(asyncio.CancelledError):
            await cancelled()
        assert execution.current() is parent
    (row,) = read(tmp_path)["attempts"]
    assert row["status"] == "cancelled" and row["usage"]["input_total_tokens"] == 7
    assert row["usage"]["output_tokens"] is None and not row["usage_complete"]


@pytest.mark.asyncio
async def test_a_failed_final_write_does_not_turn_cancellation_into_a_retry(tmp_path, monkeypatch):
    put = Ledger.put

    def fail_finish(self, row):
        if row["ended_at"] is not None:
            raise LedgerError("disk unavailable")
        put(self, row)

    monkeypatch.setattr(Ledger, "put", fail_finish)
    with pytest.raises(asyncio.CancelledError) as stopped:
        with execution.run(tmp_path), execution.attempt("test", "model"):
            raise asyncio.CancelledError
    assert any("disk unavailable" in note for note in stopped.value.__notes__)
    assert execution.current() is None
    assert read(tmp_path)["totals"]["unfinished"] == 1


def test_failed_start_prevents_external_work(tmp_path):
    blocker = tmp_path / "blocked"
    blocker.write_text("not a directory")
    context = execution.Context(Ledger(blocker / FILENAME), "run")
    sent = []
    with execution.bind(context), pytest.raises(LedgerError):
        with execution.attempt("test", "model"):
            sent.append(True)
    assert sent == []


def test_the_parent_ledger_is_private_even_when_its_directory_is_traversable(tmp_path):
    tmp_path.chmod(0o711)
    with execution.run(tmp_path):
        pass
    assert (tmp_path / FILENAME).stat().st_mode & 0o777 == 0o600


def test_an_invalid_shard_cannot_be_returned_as_a_partial_total(tmp_path):
    import sqlite3

    with execution.run(tmp_path), execution.attempt("test", "model") as request:
        request.usage({"cost_usd": 1})
    with sqlite3.connect(tmp_path / FILENAME) as database:
        database.execute("UPDATE snapshots SET payload = '[]' WHERE id = ?", (request.row["id"],))
    with pytest.raises(LedgerError, match="Invalid execution accounting"):
        read(tmp_path)


def test_receiver_uses_its_own_ledger_and_copies_are_deduplicated(tmp_path):
    with execution.run(tmp_path / "parent", run_id="run"):
        payload = execution.carrier()
        assert not any("path" in key or "ledger" in key for key in payload)
        with execution.receive(payload, tmp_path / "child"):
            with execution.attempt("test", "model") as request:
                request.usage({"completion_tokens": 12}, complete=True)
    rows = read_tree(tmp_path)
    assert build(rows + rows)["totals"]["output_tokens"] == 12
    assert not build(rows)["missing_parents"]
    assert len(Ledger(tmp_path / "parent" / FILENAME).read()) == 1


def anthropic_payload():
    return {
        "id": "response-1",
        "model": "served-model",
        "content": [{"type": "text", "text": "Answer"}],
        "stop_reason": "end_turn",
        "usage": {
            "input_tokens": 11,
            "output_tokens": 5,
            "cache_read_input_tokens": 7,
            "cache_creation_input_tokens": 0,
        },
    }


@pytest.mark.asyncio
async def test_transport_retries_have_distinct_attempts_and_actual_model(tmp_path, monkeypatch):
    sent = []

    async def transport(request):
        sent.append(json.loads(request.content))
        if len(sent) == 1:
            return httpx.Response(503, json={"error": {"message": "temporarily unavailable"}})
        return httpx.Response(200, json=anthropic_payload())

    client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: client(transport=httpx.MockTransport(transport), **kwargs)
    )
    provider = AnthropicMessagesProvider(api_key="test", default_model="claude-test")
    monkeypatch.setattr(provider, "_CHAT_RETRY_DELAYS", (0,))
    with execution.run(tmp_path), execution.scope("curate"):
        response = await provider.chat_with_retry(messages=[{"role": "user", "content": "Hello"}])
    assert response.finish_reason != "error"
    report = read(tmp_path)
    attempts = report["attempts"]
    assert len(sent) == len(attempts) == 2
    assert len({row["id"] for row in attempts}) == 2
    assert [row["status"] for row in attempts] == ["error", "ok"]
    assert attempts[1]["served_model"] == "served-model"
    assert report["totals"]["output_tokens"] == 5
    assert report["totals"]["input_total_tokens"] == 18
    assert report["totals"]["missing"]["output_tokens"] == 1


@pytest.mark.asyncio
async def test_anthropic_wire_repair_is_another_attempt(tmp_path, monkeypatch):
    sent = []

    async def transport(request):
        sent.append(json.loads(request.content))
        if len(sent) == 1:
            return httpx.Response(
                400,
                json={
                    "error": {
                        "message": "max_tokens: 999999 > 8192, which is the maximum allowed number of output tokens"
                    }
                },
            )
        return httpx.Response(200, json=anthropic_payload())

    client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: client(transport=httpx.MockTransport(transport), **kwargs)
    )
    provider = AnthropicMessagesProvider(api_key="test", default_model="claude-test")
    with execution.run(tmp_path):
        await provider.chat(messages=[{"role": "user", "content": "Hello"}], max_tokens=999999)
    assert len(sent) == len(read(tmp_path)["attempts"])
    assert sent
    assert len(sent) == 2


@pytest.mark.asyncio
async def test_stream_close_preserves_start_usage_without_leaking_context(tmp_path, monkeypatch):
    events = [
        {"type": "message_start", "message": {"id": "stream-1", "model": "served", "usage": {"input_tokens": 11}}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hello"}},
        {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 5}},
    ]
    wire = "".join(f"data: {json.dumps(event)}\n\n" for event in events)
    client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, text=wire)), **kwargs
        ),
    )
    provider = AnthropicMessagesProvider(api_key="test", default_model="claude-test")
    with execution.run(tmp_path):
        before = execution.current()
        stream = provider.chat_stream(messages=[{"role": "user", "content": "Hello"}])
        await anext(stream)
        assert execution.current() is before
        await stream.aclose()
    (row,) = read(tmp_path)["attempts"]
    assert row["status"] == "cancelled"
    assert row["usage"]["input_tokens"] == 11 and row["usage"]["output_tokens"] is None


@pytest.mark.asyncio
async def test_responses_id_survives_interruption_before_any_usage(tmp_path, monkeypatch):
    from raven.providers.openai_responses_provider import OpenAIResponsesProvider

    class Interrupted(httpx.AsyncByteStream):
        async def __aiter__(self):
            event = {"type": "response.created", "response": {"id": "pending-response", "model": "served"}}
            yield f"data: {json.dumps(event)}\n\n".encode()
            raise httpx.ReadError("stream interrupted")

    client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=Interrupted())), **kwargs
        ),
    )
    provider = OpenAIResponsesProvider(api_key="test", default_model="gpt-test", api_base="https://example.test")
    with execution.run(tmp_path):
        response = await provider.chat(messages=[{"role": "user", "content": "Hello"}])
    assert response.finish_reason == "error"
    (row,) = read(tmp_path)["attempts"]
    assert row["response_id"] == "pending-response" and row["served_model"] == "served"
    assert row["usage"]["cost_usd"] is None and not row["usage_complete"]


@pytest.mark.asyncio
async def test_litellm_records_usage_before_response_parsing_and_disables_hidden_retries(tmp_path, monkeypatch):
    from raven.providers import litellm_provider

    sent = []

    async def transport(**kwargs):
        sent.append(kwargs)
        return SimpleNamespace(usage={"prompt_tokens": 10, "completion_tokens": 4}, model="actual", id="r1", choices=[])

    monkeypatch.setattr(litellm_provider, "acompletion", transport)
    provider = LiteLLMProvider(
        api_key="test", default_model="test", provider_name="custom", api_base="https://example.test/v1"
    )
    with execution.run(tmp_path):
        response = await provider.chat(messages=[{"role": "user", "content": "Hello"}])
    assert response.finish_reason == "error"
    (row,) = read(tmp_path)["attempts"]
    assert len(sent) == 1 and sent[0]["num_retries"] == sent[0]["max_retries"] == 0
    assert row["status"] == "error" and row["usage"]["output_tokens"] == 4


def test_disabled_accounting_creates_no_records(tmp_path):
    with execution.scope("stage"), execution.attempt("test", "model") as request:
        request.usage({"completion_tokens": 1})
    assert not list(tmp_path.iterdir())


def test_repeated_usage_does_not_rewrite_the_snapshot(tmp_path):
    with execution.run(tmp_path), execution.attempt("test", "model") as request:
        usage = {"prompt_tokens": 100, "completion_tokens": 20}
        request.usage(usage)
        saved = Ledger(tmp_path / FILENAME).read()
        request.usage(usage)
        assert Ledger(tmp_path / FILENAME).read() == saved


def test_raw_provider_fields_and_nulls_survive_normalization(tmp_path):
    with execution.run(tmp_path), execution.attempt("test", "model") as request:
        request.usage(
            {"prompt_tokens": 100}, raw={"input_tokens": 100, "details": {"cache_ttl": "5m", "unknown": None}}
        )
        request.usage({"completion_tokens": 5}, raw={"output_tokens": 5, "details": {"extra": 1}})
    (row,) = read(tmp_path)["attempts"]
    assert row["raw_usage"] == {
        "input_tokens": 100,
        "output_tokens": 5,
        "details": {"cache_ttl": "5m", "unknown": None, "extra": 1},
    }
    assert row["usage"]["input_total_tokens"] == 100 and row["usage"]["output_tokens"] == 5


def test_conflicting_cache_counters_are_not_converted_into_zero_fresh_input(tmp_path):
    with execution.run(tmp_path), execution.attempt("test", "model") as request:
        request.usage({"prompt_tokens": 10, "cache_read_input_tokens": 11, "cache_creation_input_tokens": 0})
    report = read(tmp_path)
    assert report["attempts"][0]["usage"]["input_tokens"] is None
    assert report["totals"]["inconsistent_usage"] == 1


@pytest.mark.asyncio
async def test_a_returned_model_error_is_an_error_at_both_levels(tmp_path, monkeypatch):
    from raven.providers.azure_openai_provider import AzureOpenAIProvider

    client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"choices": [], "usage": {"completion_tokens": 4}})
            ),
            **kwargs,
        ),
    )
    provider = AzureOpenAIProvider(api_key="test", default_model="gpt-test", api_base="https://example.test")
    monkeypatch.setattr(provider, "_CHAT_RETRY_DELAYS", ())
    with execution.run(tmp_path):
        response = await provider.chat_with_retry(messages=[{"role": "user", "content": "Hello"}])
    assert response.finish_reason == "error"
    report = read(tmp_path)
    assert report["attempts"][0]["status"] == "error"
    assert report["totals"]["output_tokens"] == 4
    assert next(row for row in report["spans"] if row["name"] == "llm.call")["status"] == "error"


def test_experimental_cost_readers_share_the_ledger_and_never_add_legacy_totals(tmp_path):
    from experimental.simulation.bench.record import _cost
    from experimental.simulation.suite import spend
    from raven.observability.report import cost

    (tmp_path / "suite-summary.json").write_text(json.dumps({"spend": {"total": 999}}))
    with execution.run(tmp_path):
        with execution.attempt("test", "model") as request:
            request.usage({"cost_usd": 0})
        with execution.attempt("test", "model"):
            pass
    expected = cost(read(tmp_path))
    assert _cost(tmp_path, None) == spend(tmp_path)["accounting"] == expected
    assert expected["total"] == 0 and expected["missing_calls"] == 1


def test_every_request_is_attributed_to_one_part_by_the_session_it_ran_under(tmp_path):
    from raven.observability.report import cost

    with execution.run(tmp_path):
        with execution.attempt("test", "model") as request:
            request.usage({"cost_usd": 1})
        with execution.scope("session.turn", session_key="webchat:1"), execution.attempt("test", "model") as request:
            request.usage({"cost_usd": 2})
        with execution.scope("acp.prompt", session_key="acp:child"), execution.attempt("test", "model") as request:
            request.usage({"cost_usd": 4})
        with execution.attempt("claude", "model", external=True) as request:
            request.usage({"quota_usd": 8})
    report = read(tmp_path)
    assert sorted(row["part"] for row in report["attempts"]) == ["employee", "research", "simulation", "subagents"]
    assert cost(report)["by_part"] == {"simulation": 1, "employee": 2, "subagents": 4}
    assert cost(report)["quota"] == {"research": 8}


def test_a_budget_estimate_never_becomes_reported_spend(tmp_path):
    from experimental.simulation.suite import over_budget, spend

    with execution.run(tmp_path), execution.attempt("test", "deepseek/deepseek-flash") as request:
        request.usage({"prompt_tokens": 1_000_000, "completion_tokens": 500_000})
    amount = spend(tmp_path)
    assert amount["total"] is None
    assert amount["budget_total"] == pytest.approx(0.9)
    assert amount["accounting"]["missing_calls"] == 1
    assert amount["budget_pricing"]["rates"] and amount["budget_pricing"]["version"]
    assert over_budget([SimpleNamespace(state=tmp_path, records=tmp_path, started=1)], 0.8)


@pytest.mark.asyncio
async def test_speech_stream_preserves_usage_before_audio_decoding(tmp_path, monkeypatch):
    from raven.agent.tools.media_gen import SpeechGenerateTool

    events = [
        {
            "choices": [{"delta": {"audio": {"data": "AAE=", "transcript": "Hi"}}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        },
        {"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 5}},
    ]
    wire = "".join(f"data: {json.dumps(event)}\n\n" for event in events) + "data: [DONE]\n\n"
    sent = []

    async def transport(request):
        sent.append(request)
        return httpx.Response(200, text=wire)

    client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: client(transport=httpx.MockTransport(transport), **kwargs)
    )
    tool = SpeechGenerateTool(SimpleNamespace(api_base="https://example.test", api_key="test", model="speech"))
    with execution.run(tmp_path):
        audio, transcript = await tool._stream_audio_pcm({"model": "speech"})
    assert audio == b"\x00\x01" and transcript == "Hi"
    report = read(tmp_path)
    assert report["totals"]["attempts"] == len(sent) == 1
    assert report["totals"]["output_tokens"] == 5
    assert report["attempts"][0]["usage_complete"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "adapter",
    [
        "anthropic",
        "anthropic_stream",
        "responses",
        "codex",
        "azure",
        "litellm",
        "litellm_stream",
        "image",
        "speech",
        "video",
    ],
)
async def test_usage_in_an_http_error_is_retained(adapter, tmp_path, monkeypatch):
    from raven.agent.tools.media_gen import ImageGenerateTool, SpeechGenerateTool, VideoGenerateTool
    from raven.providers import litellm_provider
    from raven.providers.azure_openai_provider import AzureOpenAIProvider
    from raven.providers.openai_codex_provider import OpenAICodexProvider
    from raven.providers.openai_responses_provider import OpenAIResponsesProvider

    sent = []
    payload = {
        "id": "charged-error",
        "error": {"message": "Failure"},
        "usage": {
            "input_tokens": 10,
            "prompt_tokens": 10,
            "output_tokens": 4,
            "completion_tokens": 4,
            "cost": 0.2,
        },
    }

    async def transport(request):
        sent.append(request)
        return httpx.Response(503, json=payload)

    async def sdk(**kwargs):
        request = httpx.Request("POST", "https://example.test/model")
        sent.append(request)
        raise httpx.HTTPStatusError(
            "Failure", request=request, response=httpx.Response(503, json=payload, request=request)
        )

    client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: client(transport=httpx.MockTransport(transport), **kwargs)
    )
    monkeypatch.setattr(litellm_provider, "acompletion", sdk)
    monkeypatch.setattr("raven.providers.chatgpt_token.access_token_and_account", lambda: ("token", "account"))
    config = SimpleNamespace(api_key="test", api_base="https://example.test", model="test-model")
    messages = [{"role": "user", "content": "Hello"}]
    with execution.run(tmp_path):
        try:
            if adapter == "image":
                tool = ImageGenerateTool(config, workspace=tmp_path)
                await tool._via_images_api("model", "prompt", None, None, None)
            elif adapter == "speech":
                await SpeechGenerateTool(config)._stream_audio_pcm({"model": "model"})
            elif adapter == "video":
                await VideoGenerateTool(config, workspace=tmp_path).execute("prompt")
            else:
                if adapter.startswith("anthropic"):
                    provider = AnthropicMessagesProvider(api_key="test", default_model="claude-test")
                elif adapter == "azure":
                    provider = AzureOpenAIProvider(api_key="test", default_model="model", api_base=config.api_base)
                elif adapter == "responses":
                    provider = OpenAIResponsesProvider(api_key="test", default_model="model", api_base=config.api_base)
                elif adapter == "codex":
                    provider = OpenAICodexProvider(default_model="model")
                else:
                    provider = LiteLLMProvider(
                        api_key="test", default_model="model", api_base=config.api_base, provider_name="custom"
                    )
                if adapter.endswith("_stream"):
                    async for _ in provider.chat_stream(messages=messages):
                        pass
                else:
                    result = await provider.chat(messages=messages)
                    assert result.finish_reason == "error"
        except httpx.HTTPStatusError:
            pass
    report = read(tmp_path)
    assert len(sent) == report["totals"]["attempts"] == 1
    assert report["totals"]["cost_usd"] == 0.2
    assert report["totals"]["output_tokens"] == 4
    assert report["attempts"][0]["status"] == "error"


def test_web_reader_selects_only_the_indexed_execution_run(tmp_path):
    from experimental.webui.serve import execution_report

    root = tmp_path / "worker"
    (root / "iteration").mkdir(parents=True)
    (root / "iteration" / "record.json").write_text(json.dumps({"execution_run_id": "selected"}))
    for name, output in (("selected", 5), ("other", 100)):
        with execution.run(root, run_id=name), execution.attempt("test", "model") as request:
            request.usage({"completion_tokens": output})
    report = execution_report(tmp_path, "worker/record")
    assert report["totals"]["output_tokens"] == 5
    assert execution_report(tmp_path, "../record") is None
    assert execution_report(tmp_path, "worker/missing") is None


@pytest.mark.asyncio
async def test_fallback_preserves_each_requested_model(tmp_path, monkeypatch):
    sent = []

    async def transport(request):
        body = json.loads(request.content)
        sent.append(body["model"])
        if len(sent) == 1:
            return httpx.Response(503, json={"error": {"message": "temporarily unavailable"}})
        return httpx.Response(200, json=anthropic_payload())

    client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: client(transport=httpx.MockTransport(transport), **kwargs)
    )
    provider = AnthropicMessagesProvider(api_key="test", default_model="claude-first")
    monkeypatch.setattr(provider, "_CHAT_RETRY_DELAYS", ())
    with execution.run(tmp_path):
        await provider.chat_with_retry(
            messages=[{"role": "user", "content": "Hello"}], model="claude-first", fallback_models=["claude-second"]
        )
    assert sent == ["claude-first", "claude-second"]
    assert [row["attributes"]["model"] for row in read(tmp_path)["attempts"]] == sent


@pytest.mark.asyncio
async def test_stream_cumulative_and_repeated_usage_is_not_added(tmp_path, monkeypatch):
    from raven.providers import litellm_provider
    from tests.test_litellm_provider_stream import _FakeChoice, _FakeChunk, _FakeDelta

    sent = []

    async def chunks():
        yield _FakeChunk(choices=[], usage={"prompt_tokens": 10, "completion_tokens": 3})
        yield _FakeChunk(choices=[_FakeChoice(_FakeDelta(content="Answer"), finish_reason="stop")])
        yield _FakeChunk(choices=[], usage={"completion_tokens": 8, "cost": 0.25})
        yield _FakeChunk(choices=[], usage={"completion_tokens": 8, "cost": 0.25})

    async def transport(**kwargs):
        sent.append(kwargs)
        return chunks()

    monkeypatch.setattr(litellm_provider, "acompletion", transport)
    provider = LiteLLMProvider(
        api_key="test", default_model="test", provider_name="custom", api_base="https://example.test/v1"
    )
    with execution.run(tmp_path):
        async for _ in provider.chat_stream(messages=[{"role": "user", "content": "Hello"}]):
            pass
    report = read(tmp_path)
    assert len(sent) == report["totals"]["attempts"] == 1
    assert report["totals"]["input_total_tokens"] == 10
    assert report["totals"]["output_tokens"] == 8
    assert report["totals"]["cost_usd"] == 0.25
    assert report["attempts"][0]["usage_complete"]


@pytest.mark.asyncio
async def test_persistence_failure_is_not_a_model_retry(tmp_path, monkeypatch):
    from raven.providers import litellm_provider

    sent = []
    put = Ledger.put

    def fail_usage(self, row):
        if row.get("usage", {}).get("output_tokens") is not None:
            raise LedgerError("disk unavailable")
        put(self, row)

    async def transport(**kwargs):
        sent.append(kwargs)
        return SimpleNamespace(usage={"completion_tokens": 4}, model="actual", id="r1", choices=[])

    monkeypatch.setattr(Ledger, "put", fail_usage)
    monkeypatch.setattr(litellm_provider, "acompletion", transport)
    provider = LiteLLMProvider(
        api_key="test", default_model="test", provider_name="custom", api_base="https://example.test/v1"
    )
    with execution.run(tmp_path), pytest.raises(LedgerError):
        await provider.chat_with_retry(messages=[{"role": "user", "content": "Hello"}])
    assert len(sent) == 1
    assert read(tmp_path)["totals"]["unfinished"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter", ["responses", "codex", "azure"])
async def test_other_wire_adapters_record_the_actual_response_usage(adapter, tmp_path, monkeypatch):
    from raven.providers.azure_openai_provider import AzureOpenAIProvider
    from raven.providers.openai_codex_provider import OpenAICodexProvider
    from raven.providers.openai_responses_provider import OpenAIResponsesProvider

    sent = []

    async def transport(request):
        sent.append(request)
        if adapter == "azure":
            return httpx.Response(
                200,
                json={
                    "id": "r1",
                    "model": "served",
                    "choices": [{"message": {"content": "Answer"}, "finish_reason": "stop"}],
                    "usage": {
                        "prompt_tokens": 100,
                        "completion_tokens": 8,
                        "prompt_tokens_details": {"cached_tokens": 50, "cache_write_tokens": 0},
                        "cost": 0.2,
                    },
                },
            )
        event = {
            "type": "response.completed",
            "response": {
                "id": "r1",
                "model": "served",
                "status": "completed",
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 8,
                    "input_tokens_details": {"cached_tokens": 50, "cache_write_tokens": 0},
                    "cost": 0.2,
                },
            },
        }
        return httpx.Response(200, text=f"data: {json.dumps(event)}\n\n")

    client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: client(transport=httpx.MockTransport(transport), **kwargs)
    )
    monkeypatch.setattr("raven.providers.chatgpt_token.access_token_and_account", lambda: ("token", "account"))
    if adapter == "responses":
        provider = OpenAIResponsesProvider(
            api_key="test", default_model="gpt-4o-mini", api_base="https://example.test/v1"
        )
    elif adapter == "codex":
        provider = OpenAICodexProvider(default_model="openai-codex/gpt-4o-mini")
    else:
        provider = AzureOpenAIProvider(api_key="test", default_model="gpt-4o-mini", api_base="https://example.test")
    with execution.run(tmp_path):
        await provider.chat(messages=[{"role": "user", "content": "Hello"}])
    report = read(tmp_path)
    assert len(sent) == report["totals"]["attempts"] == 1
    assert report["totals"]["input_tokens"] == 50
    assert report["totals"]["output_tokens"] == 8
    assert report["totals"]["cost_usd"] == 0.2
    assert report["attempts"][0]["response_id"] == "r1"
    raw = report["attempts"][0]["raw_usage"]
    assert raw["cost"] == 0.2
    assert raw["prompt_tokens" if adapter == "azure" else "input_tokens"] == 100


@pytest.mark.asyncio
@pytest.mark.parametrize("protocol", ["chat", "images"])
async def test_image_generation_is_accounted_at_its_http_boundary(protocol, tmp_path, monkeypatch):
    from raven.agent.tools.media_gen import ImageGenerateTool

    sent = []

    async def transport(request):
        sent.append(request)
        return httpx.Response(
            200,
            json={
                "id": "image-1",
                "choices": [{"message": {"content": "image"}}],
                "data": [],
                "usage": {"input_tokens": 10, "output_tokens": 8, "cost": 0.2},
            },
        )

    client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: client(transport=httpx.MockTransport(transport), **kwargs)
    )
    tool = ImageGenerateTool(
        SimpleNamespace(api_base="https://example.test", api_key="test", model="image-model"), workspace=tmp_path
    )
    with execution.run(tmp_path):
        if protocol == "chat":
            await tool._chat({"model": "image-model", "messages": []})
        else:
            await tool._via_images_api("image-model", "Create an image", None, None, None)
    report = read(tmp_path)
    assert len(sent) == report["totals"]["attempts"] == 1
    assert report["totals"]["input_total_tokens"] == 10
    assert report["totals"]["output_tokens"] == 8
    assert report["totals"]["cost_usd"] == 0.2


@pytest.mark.asyncio
async def test_video_polling_updates_one_submission_without_counting_downloads(tmp_path, monkeypatch):
    from raven.agent.tools.media_gen import VideoGenerateTool

    sent = []

    async def transport(request):
        sent.append(request)
        return httpx.Response(200, json={"id": "video-1"})

    async def poll(*args):
        return {"status": "completed", "url": "data:video/mp4;base64,dmlkZW8=", "usage": {"cost": 0.5}}

    client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: client(transport=httpx.MockTransport(transport), **kwargs)
    )
    tool = VideoGenerateTool(
        SimpleNamespace(api_base="https://example.test", api_key="test", model="video-model"), workspace=tmp_path
    )
    monkeypatch.setattr(tool, "_poll", poll)
    with execution.run(tmp_path):
        await tool.execute("Create a video")
    report = read(tmp_path)
    assert len(sent) == report["totals"]["attempts"] == 1
    assert report["totals"]["cost_usd"] == 0.5
    assert report["attempts"][0]["response_id"] == "video-1"
