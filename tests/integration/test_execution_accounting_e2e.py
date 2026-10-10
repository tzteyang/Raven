"""Account real worker and ACP subprocess traffic against a local provider server."""

import json
import os
import shlex
import subprocess
import sys
import threading
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from experimental.harness.contract import Artifact
from experimental.harness.raven_adapter.worker import Worker
from raven.acp_client.acp_agent import AcpAgentBackend
from raven.acp_client.pool import AcpConnectionPool
from raven.agent.subagent.instances import InstanceRegistry
from raven.contracts.llm_provider import GenerationSettings
from raven.observability import execution
from raven.observability.report import read
from raven.providers.anthropic_messages_provider import AnthropicMessagesProvider
from tests.integration.test_harness_curator_e2e import baseline as baseline

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def local_provider(config, endpoint):
    provider = AnthropicMessagesProvider(api_key="test", api_base=endpoint, default_model=config.agents.defaults.model)
    provider.generation = GenerationSettings(max_tokens=100, temperature=0)
    return provider


@pytest.fixture
def server():
    sent = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            sent.append(body)
            usage = {
                "input_tokens": 11,
                "output_tokens": 5,
                "cache_read_input_tokens": 0,
                "cache_creation_input_tokens": 0,
            }
            if body.get("stream"):
                events = [
                    {"type": "message_start", "message": {"id": str(len(sent)), "model": "served", "usage": usage}},
                    {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Answer"}},
                    {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": usage},
                    {"type": "message_stop"},
                ]
                payload = "".join(f"data: {json.dumps(event)}\n\n" for event in events).encode()
            else:
                payload = json.dumps(
                    {
                        "id": str(len(sent)),
                        "model": "served",
                        "usage": usage,
                        "content": [{"type": "text", "text": "Answer"}],
                        "stop_reason": "end_turn",
                    }
                ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream" if body.get("stream") else "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{http.server_port}", sent
    finally:
        http.shutdown()
        http.server_close()
        thread.join()


async def test_worker_records_every_physical_request_under_its_trial(baseline, tmp_path, server):
    endpoint, sent = server
    root = tmp_path / "run"
    with execution.run(root, run_id="worker-run"):
        async with Worker(
            baseline, root, provider_factory=partial(local_provider, endpoint=endpoint), timeout=45
        ) as worker:
            with execution.scope("trial", round_index=2, stage="trial"):
                result = await worker.run("Answer briefly.", session_key="curator:tracked")
            assert "Answer" in result.text
    report = read(root)
    assert sent and len(report["attempts"]) == len(sent)
    assert report["totals"]["output_tokens"] == 5 * len(sent)
    assert not report["missing_parents"]
    operations = {row["name"] for row in report["spans"]}
    assert {
        "harness.memory.assemble",
        "harness.planning.prepare",
        "harness.capability.select",
        "harness.action.decide",
    } <= operations
    action = [row for row in report["spans"] if row["name"] == "harness.action.decide"]
    assert sum(row["totals"]["output_tokens"] or 0 for row in action) == 5 * len(sent)
    for row in report["attempts"]:
        assert row["run_id"] == "worker-run"
        assert row["attributes"]["round_index"] == 2
        assert row["attributes"]["session_key"] == "curator:tracked"
        assert row["pid"] != os.getpid()


async def test_acp_dispatch_propagates_context_into_the_actual_child(baseline, tmp_path, server):
    endpoint, sent = server
    root = tmp_path / "run"
    root.mkdir()
    baseline.hosting, baseline.allow_delegation = "acp", False
    deployment = root / "deployment.json"
    deployment.write_text(
        json.dumps(
            {
                "baseline": baseline.export(),
                "artifact": Artifact(values={}).model_dump(),
                "state_dir": str(root / "child"),
            }
        )
    )
    launcher = root / "launch.py"
    launcher.write_text(
        "import asyncio, sys\nfrom pathlib import Path\nfrom functools import partial\n"
        "from experimental.harness.raven_adapter.hosting.acp import main\n"
        "from tests.integration.test_execution_accounting_e2e import local_provider\n"
        "asyncio.run(main(Path(sys.argv[1]), provider_factory=partial(local_provider, endpoint=sys.argv[2])))\n"
    )
    pool = AcpConnectionPool()
    backend = AcpAgentBackend(
        name="Tracked",
        command=shlex.join([sys.executable, str(launcher), str(deployment), endpoint]),
        cwd=str(baseline.workdir),
        env={"PYTHONPATH": str(Path(__file__).resolve().parents[2]), "RAVEN_HOME": str(root / "native")},
        pool=pool,
        registry=InstanceRegistry(root / "instances.json"),
    )
    try:
        with execution.run(root, run_id="acp-run"), execution.scope("trial", stage="trial", round_index=3):
            await backend.run(
                "Answer briefly.",
                task_id="tracked",
                workspace=baseline.workdir,
                executor=None,
                session_key="parent:task",
            )
    finally:
        await pool.close_all()
    report = read(root)
    assert sent and len(report["attempts"]) == len(sent)
    assert report["totals"]["output_tokens"] == len(sent) * 5
    assert not report["missing_parents"]
    assert all(row["attributes"]["round_index"] == 3 for row in report["attempts"])


async def test_abrupt_process_exit_retains_started_attempt_and_known_usage(tmp_path):
    with execution.run(tmp_path / "parent", run_id="crash-run"):
        payload = execution.carrier()
        code = (
            "import json, os, sys\nfrom raven.observability import execution\n"
            "with execution.receive(json.loads(sys.stdin.read()), sys.argv[1]):\n"
            "    request = execution.attempt('local', 'test')\n"
            "    request.usage({'prompt_tokens': 11})\n"
            "    os._exit(9)\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code, str(tmp_path / "child")], input=json.dumps(payload), text=True, timeout=10
        )
    assert result.returncode == 9
    report = read(tmp_path)
    (row,) = report["attempts"]
    assert row["status"] == "running" and row["ended_at"] is None
    assert report["totals"]["unfinished"] == 1
    assert report["totals"]["input_total_tokens"] == 11
    assert report["totals"]["output_tokens"] is None


async def test_temporary_validation_preserves_its_requests_before_cleanup(baseline, tmp_path, server):
    from tests.integration.test_harness_curator_e2e import exercise_turn, plan_for

    endpoint, sent = server
    root = tmp_path / "run"
    with execution.run(root):
        async with Worker(
            baseline, root, provider_factory=partial(local_provider, endpoint=endpoint), timeout=45
        ) as worker:
            inspection = await worker.inspect()
            candidate = inspection.declaration.accept(plan_for(), Artifact(values={}))
            with execution.scope("validate", stage="validate"):
                result = await worker.check(candidate, probe=exercise_turn)
            assert result.passed, result.errors
    report = read(root)
    assert sent and len(report["attempts"]) == len(sent)
    assert report["totals"]["output_tokens"] == 5 * len(sent)
    assert not report["missing_parents"]
    assert all(row["attributes"]["stage"] == "validate" for row in report["attempts"])


async def test_external_codex_reports_a_total_without_inventing_input_or_output(tmp_path, monkeypatch):
    from experimental.cultivation.collector.researchers import Agent
    from tests.test_research_calls import Answer, fake_codex

    calls = fake_codex(tmp_path, monkeypatch, {"answer": "ok", "count": 2})
    with execution.run(tmp_path / "run"), execution.scope("collector"):
        await Agent("codex").stage("Select.", Answer)
    report = read(tmp_path / "run")
    assert len(calls.read_text().splitlines()) == report["totals"]["external_calls"] == 1
    assert report["totals"]["attempts"] == 0
    assert report["totals"]["total_tokens"] == 1234
    assert report["totals"]["input_total_tokens"] is None and report["totals"]["output_tokens"] is None


async def test_external_corrections_do_not_double_count_subscription_equivalents(tmp_path, monkeypatch):
    from experimental.cultivation.collector.researchers import Agent
    from tests.test_research_calls import Answer
    from tests.test_research_inquiry import fake

    count = tmp_path / "invocations"
    payload = {
        "type": "result",
        "subtype": "success",
        "total_cost_usd": 0.25,
        "structured_output": {"answer": "ok", "count": 2},
        "usage": {
            "input_tokens": 10,
            "output_tokens": 5,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        },
    }
    fake(
        tmp_path,
        monkeypatch,
        "claude",
        "import json,sys\nfrom pathlib import Path\nsys.stdin.read()\n"
        + f"count = Path({str(count)!r})\nfirst = not count.exists()\n"
        + "with count.open('a') as f: f.write('call\\n')\n"
        + "print(json.dumps({'type': 'system', 'subtype': 'init', 'apiKeySource': 'none'}))\n"
        + f"payload = {payload!r}\n"
        + "if first: payload['structured_output']['count'] = 'invalid'\nprint(json.dumps(payload))\n",
    )
    with execution.run(tmp_path / "run"), execution.scope("collector"):
        _, result = await Agent("claude").stage("Select.", Answer, records=tmp_path / "evidence")
    report = read(tmp_path / "run")
    assert result["cost_usd"] == 0.5
    assert len(count.read_text().splitlines()) == report["totals"]["external_calls"] == 2
    assert report["totals"]["cost_usd"] is None
    assert report["totals"]["quota_usd"] == 0.5
    assert report["totals"]["output_tokens"] == 10
