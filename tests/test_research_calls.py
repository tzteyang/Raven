"""Agent collection calls only select host tools; Codex stages run in an empty directory; terminal input can be cancelled."""

import asyncio
import json
import os
import stat
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from experimental.research import calls, researchers, terminal


class Answer(BaseModel):
    answer: str
    count: int


FAKE_CODEX = """#!/usr/bin/env python3
import json, pathlib, sys
args = sys.argv[1:]
prompt = sys.stdin.read()
out = pathlib.Path(args[args.index("-o") + 1])
schema = json.loads(pathlib.Path(args[args.index("--output-schema") + 1]).read_text())
log = pathlib.Path(__file__).with_name("calls.jsonl")
calls = log.read_text().splitlines() if log.exists() else []
with log.open("a") as stream:
    stream.write(json.dumps({"args": args, "prompt": prompt, "cwd": str(pathlib.Path.cwd())}) + "\\n")
answers = json.loads(pathlib.Path(__file__).with_name("answers.json").read_text())
out.write_text(json.dumps(answers[min(len(calls), len(answers) - 1)]))
assert "required" in schema
print(json.dumps(answers[0]))
print("codex", file=sys.stderr)
print("tokens used", file=sys.stderr)
print("1,234", file=sys.stderr)
"""


def fake_codex(tmp_path, monkeypatch, *answers):
    binaries = tmp_path / "bin"
    binaries.mkdir()
    script = binaries / "codex"
    script.write_text(FAKE_CODEX)
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    (binaries / "answers.json").write_text(json.dumps(list(answers)))
    monkeypatch.setenv("PATH", f"{binaries}{os.pathsep}{os.environ['PATH']}")
    return binaries / "calls.jsonl"


@pytest.mark.asyncio
@pytest.mark.parametrize("agent", ["claude", "codex"])
async def test_agent_transport_returns_a_tool_selection_without_executing_tools(tmp_path, monkeypatch, agent):
    seen = []

    class Model:
        def __init__(self, name, *args, **kwargs):
            self.name, self.model, self.effort, self.budget, self.timeout = name, "test", "high", None, 30

        async def stage(self, prompt, output, **kwargs):
            seen.append((self.name, prompt, kwargs))
            assert not kwargs.get("web", False)
            return output(name="read_file", arguments_json='{"path":"reference.md"}'), {}

    monkeypatch.setattr(calls, "Agent", Model)
    provider = calls.AgentCalls(Model(agent), tmp_path)
    response = await provider.chat_with_retry(
        messages=[{"role": "system", "content": "Assess supplied evidence."}],
        tools=[{"type": "function", "function": {"name": "read_file", "parameters": {}}}],
    )
    assert response.tool_calls[0].arguments == {"path": "reference.md"}
    assert response.tool_calls[0].name == "read_file"
    assert seen[0][0] == agent
    assert json.loads(seen[0][1].split("\n\n", 1)[1])["offered_tools"][0]["function"]["name"] == "read_file"
    assert not list(tmp_path.iterdir())


@pytest.mark.asyncio
async def test_codex_stage_runs_once_in_an_empty_directory_without_search_or_user_config(tmp_path, monkeypatch):
    log = fake_codex(tmp_path, monkeypatch, {"answer": "ok", "count": 2})
    agent = researchers.Agent("codex", model="gpt-test", effort="xhigh", timeout=30)
    value, run = await agent.stage("Select a tool.", Answer, records=tmp_path / "records")
    assert value == Answer(answer="ok", count=2)
    assert run["outcome"] == "success" and run["exit"] == 0 and run["tokens"] == 1234
    call = json.loads(log.read_text().splitlines()[0])
    assert call["prompt"] == "Select a tool." and "--search" not in call["args"]
    assert "--ignore-user-config" in call["args"] and "--ephemeral" in call["args"]
    assert call["args"][call["args"].index("-m") + 1] == "gpt-test"
    assert 'model_reasoning_effort="xhigh"' in call["args"]
    assert not os.path.exists(call["cwd"])
    records = tmp_path / "records"
    assert json.loads((records / "command.json").read_text()) == ["codex", *call["args"]]
    assert (records / "prompt.txt").read_text() == "Select a tool."
    assert json.loads((records / "run.json").read_text())["tokens"] == 1234


@pytest.mark.asyncio
async def test_codex_research_searches_and_corrects_one_answer_outside_the_schema(tmp_path, monkeypatch):
    log = fake_codex(tmp_path, monkeypatch, {"answer": "ok", "count": "many"}, {"answer": "ok", "count": 3})
    agent = researchers.Agent("codex", timeout=30)
    value, run = await agent.stage("Find it.", Answer, web=True, records=tmp_path / "records")
    assert value == Answer(answer="ok", count=3)
    assert run["output_corrected"] and "validation_error" in run and run["correction"]["outcome"] == "success"
    first, second = (json.loads(line) for line in log.read_text().splitlines())
    assert "--search" in first["args"] and "--search" not in second["args"]
    assert "validation_error" in second["prompt"]
    assert (tmp_path / "records" / "correction" / "run.json").is_file()
    assert json.loads((tmp_path / "records" / "run.json").read_text())["output_corrected"]


@pytest.mark.asyncio
async def test_codex_stage_refuses_a_second_answer_outside_the_schema(tmp_path, monkeypatch):
    fake_codex(tmp_path, monkeypatch, {"answer": "ok", "count": "many"})
    agent = researchers.Agent("codex", timeout=30)
    with pytest.raises(researchers.ResearchError, match="outside the schema"):
        await agent.stage("Find it.", Answer)


def test_unsupported_effort_is_refused_for_either_agent():
    with pytest.raises(ValueError, match="unsupported codex research effort"):
        researchers.Agent("codex", effort="extreme")


@pytest.mark.asyncio
async def test_terminal_answer_cancellation_kills_the_reader_without_a_waiting_thread(monkeypatch):
    class Process:
        returncode = None
        killed = False
        waited = False

        async def communicate(self):
            await asyncio.sleep(10)

        def kill(self):
            self.killed = True
            self.returncode = -9

        async def wait(self):
            self.waited = True

    process = Process()

    async def spawn(*args, **kwargs):
        return process

    monkeypatch.setattr(terminal.asyncio, "create_subprocess_exec", spawn)
    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.01):
            await terminal.answer(SimpleNamespace(question="Which policy applies?", reason="An organisation choice."))
    assert process.killed and process.waited


@pytest.mark.asyncio
async def test_spend_limit_stops_the_collector_at_the_reported_cost_and_on_unknown_cost():
    from raven.contracts.llm_provider import LLMResponse

    class Inner:
        generation = "defaults"

        def __init__(self, *costs):
            self.costs = list(costs)

        async def chat_with_retry(self, **kwargs):
            cost = self.costs.pop(0)
            return LLMResponse(content="ok", usage={} if cost is None else {"cost_usd": cost})

    limited = calls.SpendLimit(Inner(0.6, 0.5, 0.1), 1.0)
    await limited.chat_with_retry(messages=[])
    await limited.chat_with_retry(messages=[])
    assert limited.spent == 1.1 and limited.generation == "defaults"
    with pytest.raises(RuntimeError, match=r"spend limit reached: \$1.10 of \$1.00"):
        await limited.chat_with_retry(messages=[])
    with pytest.raises(RuntimeError, match="reported no cost"):
        await calls.SpendLimit(Inner(None), 5).chat_with_retry(messages=[])
    with pytest.raises(ValueError, match="positive"):
        calls.SpendLimit(Inner(), 0)
