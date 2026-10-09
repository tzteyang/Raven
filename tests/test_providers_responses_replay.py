"""A replayed function call on the Responses route carries no item id.

Azure OpenAI stores responses and, seeing the item id of a function call it
generated, demands that response's reasoning item beside it, which the
transcript never keeps (OpenRouter asked for neither). Without the id the call
is the client's own and only its call_id has to match the output after it.
"""

from __future__ import annotations

import pytest


class _Response:
    status_code = 200


class _StreamContext:
    async def __aenter__(self):
        return _Response()

    async def __aexit__(self, *exc):
        return False


class _Client:
    """Stands in for httpx.AsyncClient and keeps the body of the one request."""

    bodies: list[dict] = []

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def stream(self, method, url, *, headers, json):
        self.bodies.append(json)
        return _StreamContext()


@pytest.mark.asyncio
async def test_a_replayed_function_call_keeps_its_call_id_and_drops_its_item_id(monkeypatch):
    from raven.providers import openai_responses_provider as mod

    async def fake_consume(response, timeout, **kwargs):
        return "done", [], "stop"

    monkeypatch.setattr(mod.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(mod, "_consume_sse", fake_consume)
    _Client.bodies = []
    provider = mod.OpenAIResponsesProvider(api_key="k", default_model="gpt-6.1-sol")
    messages = [
        {"role": "user", "content": "Look Lyon up."},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {"id": "call_1|fc_stored", "type": "function", "function": {"name": "lookup", "arguments": "{}"}}
            ],
        },
        {"role": "tool", "tool_call_id": "call_1|fc_stored", "content": "513275"},
    ]

    await provider.chat(messages, tools=[{"type": "function", "function": {"name": "lookup", "parameters": {}}}])

    [body] = _Client.bodies
    calls = [item for item in body["input"] if item["type"] == "function_call"]
    assert calls == [{"type": "function_call", "call_id": "call_1", "name": "lookup", "arguments": "{}"}]
    assert [item["call_id"] for item in body["input"] if item["type"] == "function_call_output"] == ["call_1"]
