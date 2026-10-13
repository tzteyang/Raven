"""Offline crash/resume tests; no credentials, model calls or ACP processes.

From the repository root: uv run python -m unittest discover -s experts/common -p test_accept.py -v
"""

import asyncio
import copy
import io
import json
import select
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import accept
from examiner import Case, Scoring

from raven.contracts.llm_provider import ErrorClassification, LLMResponse, ToolCallRequest


def score(fail=False):
    return Scoring.model_validate({"items": [
        {"id": "T-body", "applicable": True, "count": int(fail), "reason": "The fake judge decided.",
         "errors": [{"quote": "answer", "problem": "The model reports a rule violation."}] if fail else []},
        {"id": "T-format", "applicable": False, "count": 0, "reason": "Not applicable.", "errors": []},
    ]})


class FakeBackend:
    def __init__(self, error=None):
        self.calls, self.last, self.on_record, self.error = [], None, None, error

    async def run(self, task, **kwargs):
        self.calls.append(kwargs)
        name = kwargs["task_id"]
        workspace = kwargs["workspace"]
        (workspace / "answer.txt").write_text(f"artifact {name}")
        self.last = SimpleNamespace(closing_text=f"answer {name}", text=f"planning\nanswer {name}")
        if self.on_record:
            self.on_record(self.last)
        await kwargs["on_delta"](self.last.text)
        if self.error:
            raise self.error
        return self.last.text


class FakeExaminer:
    def __init__(self, failure_at=None, malformed=False):
        self.calls, self.failure_at, self.malformed = [], failure_at, malformed

    async def judge(self, question, product):
        self.calls.append((question["name"], product))
        if question["name"] == self.failure_at:
            raise ConnectionError("GATEWAY_CONCURRENCY_FULL")
        result = score(fail=True)  # Deliberately low-scoring: completion must not choose a better sample.
        if self.malformed:
            result.items.pop()
        return result, []


class AcceptanceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="accept-unit-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.case, self.host = self.root / "sample", self.root / "host"
        self.case.mkdir()
        scenario = self.case / "wkr-sample"
        scenario.mkdir()
        (self.case / "rules").mkdir()
        (self.case / "rules/R1.md").write_text("original working rules")
        (scenario / "scenario.json").write_text(json.dumps({"criteria": [
            {"id": "T-body", "check": "Content", "severity": "standard"},
            {"id": "T-format", "check": "Format", "severity": "standard"},
        ]}))
        self.names = [f"{prefix}{i:02}" for prefix in ("x", "y") for i in range(1, 11)]
        bank = [{"name": name, "group": "same" if name[0] == "x" else "new", "rules": "R1",
                 "text": f"Question {name}", "files": {"工作规则.md": "original working rules", "nested/data.txt": "data"},
                 "reference": {}} for name in self.names]
        (self.case / "questions.json").write_text(json.dumps(bank))
        (self.case / "live.json").write_text(json.dumps({"scenario": "wkr-sample", "models": {"assessor": "moonshotai/kimi-k3"}, "efforts": {"assessor": "high"}}))
        self.folder = self.host / "agents/expert-sample"
        self.folder.mkdir(parents=True)
        (self.folder / "harness.json").write_text(json.dumps({"revision": "a1234567890abcdef", "artifact": {}}))
        (self.folder / "run.py").write_text("# fake agent entry; never executed\n")
        (self.folder / "config.json").write_text(json.dumps({"agents": {"defaults": {"provider": "openrouter", "model": "z-ai/glm-5.3-flash"}}}))
        self.spec = Case(scenario)

    def run_state(self, run_id="repeat-1", names=None):
        directory = self.case / "accept-runs" / run_id
        directory.mkdir(parents=True, exist_ok=True)
        with patch.object(accept.tempfile, "mkdtemp", side_effect=lambda **kw: tempfile.TemporaryDirectory.__init__):
            pass
        # Keep the deliberately retained workspaces inside this test's temporary tree.
        mkdtemp = tempfile.mkdtemp
        with patch.object(accept.tempfile, "mkdtemp", side_effect=lambda **kw: mkdtemp(dir=self.root, **kw)):
            return accept.Run(self.spec, self.host, self.names if names is None else names, run_id)

    async def evaluate(self, run, backend=None, examiner=None):
        backend, examiner = backend or FakeBackend(), examiner or FakeExaminer()
        with redirect_stdout(io.StringIO()):
            out, rows = await accept.evaluate(run, backend, examiner)
        return out, rows, backend, examiner

    async def test_twentieth_judge_failure_retains_first_nineteen_and_answer(self):
        run, backend, examiner = self.run_state(), FakeBackend(), FakeExaminer(failure_at="y10")
        with redirect_stdout(io.StringIO()), self.assertRaises(ConnectionError):
            await accept.evaluate(run, backend, examiner)
        saved = json.loads(run.path.read_text())
        self.assertEqual(sum(i["stage"] == "scored" for i in saved["items"].values()), 19)
        self.assertEqual(saved["items"]["y10"]["stage"], "judging")
        original = saved["items"]["y10"]["answer"]["product"]
        self.assertIn("answer y10", original)
        self.assertIn("artifact y10", original)
        self.assertEqual(len(backend.calls), 20)
        self.assertEqual(list(self.case.glob("accept-*.json")), [])
        self.assertTrue(any(e["event"] == "judge_failed" for e in saved["events"]))
        # Recovery must judge the frozen string, even if something changes the scratch file later.
        (Path(saved["scratch"]) / "y10/answer.txt").write_text("changed after the failed judgment")
        out, rows, resumed_backend, resumed_judge = await self.evaluate(self.run_state())
        self.assertEqual(resumed_backend.calls, [])
        self.assertEqual(resumed_judge.calls, [("y10", original)])
        self.assertEqual(len(rows), 20)
        self.assertEqual(len({r["name"] for r in rows}), 20)
        self.assertTrue(all(r["failed"] == ["T-body"] for r in rows))
        self.assertEqual(json.loads(out.read_text()), rows)

    async def test_complete_run_is_idempotent_without_loading_config(self):
        run = self.run_state()
        out, rows, _, _ = await self.evaluate(run)
        with patch.object(accept, "load_config", side_effect=AssertionError("must not load credentials")):
            with redirect_stdout(io.StringIO()):
                await accept.main([str(self.case), str(self.host), "--run-id", run.run_id])
        out2, rows2, backend, judge = await self.evaluate(self.run_state())
        self.assertEqual((out2, rows2), (out, rows))
        self.assertEqual(backend.calls, [])
        self.assertEqual(judge.calls, [])
        self.assertEqual(list(self.case.glob("accept-*.json")), [out])

    async def test_completed_run_with_missing_report_is_not_rewritten_or_redispatched(self):
        run = self.run_state()
        out, _, _, _ = await self.evaluate(run)
        out.unlink()
        before = (run.path.read_bytes(), run.path.stat().st_mtime_ns)
        with patch.object(accept, "load_config", side_effect=AssertionError("must not load credentials")), \
                redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, "completed acceptance report is missing"):
                await accept.main([str(self.case), str(self.host), "--run-id", run.run_id])
        self.assertEqual((run.path.read_bytes(), run.path.stat().st_mtime_ns), before)
        self.assertFalse(out.exists())

    async def test_independent_repeat_has_new_workspace_sessions_and_report(self):
        first, second = self.run_state("r1"), self.run_state("r2")
        out1, _, b1, _ = await self.evaluate(first)
        out2, _, b2, _ = await self.evaluate(second)
        self.assertNotEqual(first.data["scratch"], second.data["scratch"])
        self.assertNotEqual(out1, out2)
        self.assertTrue(set(c["session_key"] for c in b1.calls).isdisjoint(c["session_key"] for c in b2.calls))
        self.assertTrue(Path(first.data["scratch"]).is_dir())

    async def test_agent_business_error_is_preserved_and_judged_once(self):
        run = self.run_state(names=["x01"])
        backend = FakeBackend(accept.AcpEmptyTurnError("failed tool"))
        out, rows, _, judge = await self.evaluate(run, backend)
        self.assertIn("AcpEmptyTurnError", rows[0]["error"])
        self.assertIn("answer x01", rows[0]["product"])
        self.assertIn("planning", rows[0]["full_reply"])
        self.assertEqual(len(backend.calls), 1)
        self.assertEqual(len(judge.calls), 1)
        self.assertEqual(out, run.directory / "subset.json")
        self.assertEqual(list(self.case.glob("accept-*.json")), [])

    async def test_cancelled_dispatch_keeps_collected_output_without_redispatch(self):
        run, backend = self.run_state(names=["x01"]), FakeBackend(asyncio.CancelledError())
        with self.assertRaises(asyncio.CancelledError):
            await accept.evaluate(run, backend, FakeExaminer())
        self.assertEqual(json.loads(run.path.read_text())["items"]["x01"]["stage"], "dispatching")
        _, rows, resumed, judge = await self.evaluate(self.run_state(names=["x01"]))
        self.assertEqual(resumed.calls, [])
        self.assertIn("InterruptedError", rows[0]["error"])
        self.assertIn("answer x01", rows[0]["product"])
        self.assertIn("artifact x01", judge.calls[0][1])

    async def test_programming_error_stops_and_does_not_loop_or_rerun(self):
        run, backend = self.run_state(names=["x01"]), FakeBackend(TypeError("implementation defect"))
        with self.assertRaises(TypeError):
            await accept.evaluate(run, backend, FakeExaminer())
        with self.assertRaisesRegex(RuntimeError, "needs repair"):
            await accept.evaluate(self.run_state(names=["x01"]), FakeBackend(), FakeExaminer())
        self.assertEqual(len(backend.calls), 1)
        self.assertEqual(list(self.case.glob("accept-*.json")), [])

    async def test_missing_verdict_does_not_mark_question_done(self):
        run = self.run_state(names=["x01"])
        with self.assertRaisesRegex(ValueError, "each criterion"):
            await accept.evaluate(run, FakeBackend(), FakeExaminer(malformed=True))
        self.assertEqual(json.loads(run.path.read_text())["items"]["x01"]["stage"], "judging")
        self.assertFalse((run.directory / "subset.json").exists())
        _, rows, backend, judge = await self.evaluate(self.run_state(names=["x01"]))
        self.assertEqual(backend.calls, [])
        self.assertEqual(len(judge.calls), 1)
        self.assertEqual(len(rows[0]["verdicts"]), 2)

    async def test_crash_between_report_and_complete_marker_recovers_same_report(self):
        run = self.run_state()
        out, rows, _, _ = await self.evaluate(run)
        run.data["status"] = "running"
        run.save()
        out2, rows2, backend, judge = await self.evaluate(self.run_state())
        self.assertEqual((out2, rows2), (out, rows))
        self.assertEqual((backend.calls, judge.calls), ([], []))
        self.assertEqual(len(list(self.case.glob("accept-*.json"))), 1)

    async def test_corrupt_completed_verdict_cannot_be_published(self):
        run = self.run_state()
        await self.evaluate(run)
        run.data["items"]["y10"]["result"]["verdicts"].append(copy.deepcopy(run.data["items"]["y10"]["result"]["verdicts"][0]))
        run.save()
        with self.assertRaises(ValueError):
            await self.evaluate(self.run_state())

    def test_stable_input_hash_ignores_logs_but_rejects_rule_changes(self):
        self.run_state()
        (self.case / "run.out").write_text("new runtime log")
        (self.case / "pipeline.json").write_text('{"status":"running"}')
        (self.host / "config.json").symlink_to(self.root / "config-not-read")
        self.run_state()
        (self.case / "rules/R1.md").write_text("changed working rules")
        with self.assertRaisesRegex(ValueError, "inputs changed"):
            self.run_state()

    def test_rejects_reusing_id_with_different_question_set_or_agent(self):
        self.run_state(names=["x01"])
        with self.assertRaisesRegex(ValueError, "inputs changed"):
            self.run_state(names=["x02"])
        (self.folder / "harness.json").write_text('{"revision":"new-revision"}')
        with self.assertRaisesRegex(ValueError, "inputs changed"):
            self.run_state(names=["x01"])

    def test_atomic_write_failure_leaves_previous_checkpoint(self):
        path = self.root / "partial.json"
        accept.atomic_json(path, {"before": 1})
        with patch.object(accept.os, "replace", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                accept.atomic_json(path, {"after": 2})
        self.assertEqual(json.loads(path.read_text()), {"before": 1})
        self.assertEqual(list(self.root.glob(".partial.json-*")), [])

    def test_same_run_lock_is_exclusive(self):
        directory = self.case / "accept-runs/test-lock"
        with accept.run_lock(directory):
            with self.assertRaisesRegex(RuntimeError, "already active"):
                with accept.run_lock(directory):
                    self.fail("lock was not exclusive")
        with accept.run_lock(directory):
            pass

    async def test_cli_can_explicitly_refuse_an_active_run(self):
        directory = self.case / "accept-runs/test-lock"
        with accept.run_lock(directory), self.assertRaisesRegex(RuntimeError, "already active"):
            await accept.main([str(self.case), str(self.host), "--run-id", "test-lock", "--no-wait-for-lock"])

    async def test_waiting_cli_joins_completed_run_without_dispatch_judge_or_checkpoint_writes(self):
        run = self.run_state()
        process = None
        try:
            with accept.run_lock(run.directory):
                process = subprocess.Popen(
                    [sys.executable, accept.__file__, str(self.case), str(self.host), "--run-id", run.run_id],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                )
                self.assertTrue(select.select([process.stdout], [], [], 10)[0], "follower did not reach its lock")
                self.assertIn("WAITING_FOR_RUN", process.stdout.readline())
                self.assertIsNone(process.poll())
                out, rows, backend, judge = await self.evaluate(run)
                before = (run.path.read_bytes(), run.path.stat().st_mtime_ns, out.read_bytes(), out.stat().st_mtime_ns)
            stdout, stderr = process.communicate(timeout=10)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertIn("JOINED_RUN", stdout)
            self.assertIn("ACCEPT", stdout)
        finally:
            if process is not None:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=10)
        self.assertEqual((len(backend.calls), len(judge.calls), len(rows)), (20, 20, 20))
        self.assertEqual((run.path.read_bytes(), run.path.stat().st_mtime_ns, out.read_bytes(), out.stat().st_mtime_ns), before)
        self.assertEqual(list(self.case.glob("accept-*.json")), [out])

    async def test_waiting_cli_revalidates_inputs_after_the_owner_releases_the_lock(self):
        run = self.run_state()
        await self.evaluate(run)
        waiting, errors = threading.Event(), []
        flock = accept.fcntl.flock

        def observed_flock(file, operation):
            if operation == accept.fcntl.LOCK_EX:
                waiting.set()
            return flock(file, operation)

        def follower():
            try:
                asyncio.run(accept.main([str(self.case), str(self.host), "--run-id", run.run_id]))
            except BaseException as exc:
                errors.append(exc)

        before = run.path.read_bytes()
        with patch.object(accept.fcntl, "flock", side_effect=observed_flock), \
                patch.object(accept, "load_config", side_effect=AssertionError("binding failure cannot start models")), \
                redirect_stdout(io.StringIO()):
            with accept.run_lock(run.directory):
                thread = threading.Thread(target=follower)
                thread.start()
                self.assertTrue(waiting.wait(5))
                (self.case / "rules/R1.md").write_text("changed while waiting")
            thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], ValueError)
        self.assertIn("inputs changed", str(errors[0]))
        self.assertEqual(run.path.read_bytes(), before)

    def test_legacy_and_new_cli_question_arguments(self):
        args = accept.arguments(["case", "host", "x01", "--run-id", "r1", "y01"])
        self.assertEqual((args.names, args.run_id), (["x01", "y01"], "r1"))
        self.assertEqual(accept.arguments(["case", "host", "x01"]).names, ["x01"])
        self.assertTrue(accept.arguments(["case", "host"]).wait_for_lock)
        self.assertTrue(accept.arguments(["case", "host", "--wait-for-lock"]).wait_for_lock)
        self.assertFalse(accept.arguments(["case", "host", "--no-wait-for-lock"]).wait_for_lock)
        with redirect_stdout(io.StringIO()), patch("sys.stderr", new=io.StringIO()), self.assertRaises(SystemExit):
            accept.arguments(["case", "host", "--run-id", "../escape"])

    async def test_provider_audit_records_errors_and_every_retry_response(self):
        run = self.run_state(names=["x01"])
        class Provider:
            async def chat(self, **kwargs):
                if kwargs.get("fail"):
                    raise ConnectionError("temporary error")
                return LLMResponse(content="judge evidence", finish_reason="error" if kwargs.get("error_response") else "stop",
                                   error_classification=ErrorClassification("server") if kwargs.get("error_response") else None,
                                   tool_calls=[ToolCallRequest("call", "submit_verdicts", score().model_dump())])
        audit = accept.AuditedProvider(Provider(), run)
        audit.question = "x01"
        with self.assertRaises(ConnectionError):
            await audit.chat(fail=True)
        await audit.chat(error_response=True)
        await audit.chat()
        events = json.loads(run.path.read_text())["events"]
        self.assertEqual(sum(e["event"] == "judge_call_started" for e in events), 3)
        self.assertEqual(sum(e["event"] == "judge_call_error" for e in events), 1)
        responses = [e for e in events if e["event"] == "judge_call_response"]
        self.assertEqual([e["finish_reason"] for e in responses], ["error", "stop"])
        self.assertEqual(responses[0]["error_category"], "server")
        self.assertEqual(responses[1]["submissions"][0]["arguments"], score().model_dump())


if __name__ == "__main__":
    unittest.main()
