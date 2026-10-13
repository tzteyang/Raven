"""Offline baseline-worker coordination tests; no ACP, credentials or model calls."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import baseline_worker


class BaselineWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="baseline-unit-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.case = self.root / "experts/cases/sample"
        (self.case / "wkr-sample").mkdir(parents=True)
        (self.case / "live.json").write_text('{"scenario":"wkr-sample","models":{"assessor":"moonshotai/kimi-k3"},"efforts":{"assessor":"high"}}')
        self.names = [f"{prefix}{number:02}" for prefix in ("x", "y") for number in range(1, 11)]
        (self.case / "questions.json").write_text(json.dumps([
            {"name": name, "group": "same" if name.startswith("x") else "new"} for name in self.names
        ]))
        (self.case / "wkr-sample/scenario.json").write_text('{"criteria":[{"id":"T1"}]}')
        self.worker = baseline_worker.BaselineWorker("sample", "plain", root=self.root, repository=self.root)
        self.worker.source.mkdir(parents=True)
        for name, content in (("harness.json", '{"revision":"plain","artifact":{}}'),
                              ("run.py", "# never executed\n"), ("config.json", '{}'), ("subagent.json", '{}')):
            (self.worker.source / name).write_text(content)
        self.main_state = self.root / "runs/experts/control/sample.json"
        self.main_state.parent.mkdir(parents=True)
        self.main_state.write_text('{"stage":"acceptance","version":"trained"}')

    def report(self, repeat, *, error=None):
        run_id = self.worker.run_id(repeat)
        path = self.case / f"accept-plain-fixture-{repeat}.json"
        rows = [{"name": name, "group": "same" if name.startswith("x") else "new", "product": "saved answer",
                 "error": error, "loose": [], "failed": [], "judged": ["T1"],
                 "verdicts": [{"id": "T1", "applicable": True, "count": 0, "reason": "Fake model decision", "errors": []}]}
                for name in self.names]
        path.write_text(json.dumps(rows))
        checkpoint = self.case / "accept-runs" / run_id / "partial.json"
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_text(json.dumps({"status": "complete", "run_id": run_id, "report": str(path)}))
        return path

    def test_prepares_three_isolated_hosts_and_reuses_them_without_writes(self):
        self.worker.prepare()
        hosts = [self.worker.host(repeat) for repeat in (1, 2, 3)]
        self.assertEqual(len(set(hosts)), 3)
        for host in hosts:
            self.assertTrue((host / "config.json").is_symlink())
            self.assertEqual((host / "config.json").readlink(), self.root / "secrets/raven-experts.json")
            for name in baseline_worker.FILES:
                self.assertEqual((host / "agents/expert-sample" / name).read_bytes(), (self.worker.source / name).read_bytes())
        artifact = hosts[0] / "agents/expert-sample/harness.json"
        before = (artifact.read_bytes(), artifact.stat().st_mtime_ns)
        (hosts[0] / "runtime-progress").write_text("existing runtime state")
        self.worker.prepare()
        self.assertEqual((artifact.read_bytes(), artifact.stat().st_mtime_ns), before)
        self.assertEqual((hosts[0] / "runtime-progress").read_text(), "existing runtime state")

    def test_existing_changed_host_is_rejected_without_overwriting(self):
        self.worker.prepare()
        artifact = self.worker.host(2) / "agents/expert-sample/harness.json"
        artifact.write_text('{"revision":"changed"}')
        with self.assertRaisesRegex(ValueError, "differs from its export"):
            self.worker.prepare()
        self.assertEqual(artifact.read_text(), '{"revision":"changed"}')

    def test_three_admitted_reports_complete_only_the_separate_baseline_state(self):
        before = self.main_state.read_bytes()
        with patch.object(self.worker, "command", side_effect=lambda repeat: self.report(repeat) and 0) as command, \
                redirect_stdout(io.StringIO()):
            self.worker.run()
        self.assertEqual([call.args[0] for call in command.call_args_list], [1, 2, 3])
        state = json.loads(self.worker.state_file.read_text())
        self.assertEqual((state["stage"], state["repetitions"]), ("complete", 3))
        self.assertEqual(len(set(state["reports"])), 3)
        self.assertEqual(self.main_state.read_bytes(), before)

    def test_completed_but_unadmitted_report_stops_without_trying_another_sample(self):
        with patch.object(self.worker, "command", side_effect=lambda repeat: self.report(repeat, error="dispatch failed") and 0) as command, \
                redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, "not admitted"):
                self.worker.run()
        command.assert_called_once_with(1)
        self.assertEqual(json.loads(self.worker.state_file.read_text())["stage"], "failed")
        self.assertEqual(len(list(self.case.glob("accept-*.json"))), 1)

    def test_first_and_third_complete_do_not_skip_the_second_repeat(self):
        preserved = [self.report(1), self.report(3)]
        before = [(p.read_bytes(), p.stat().st_mtime_ns) for p in preserved]

        def command(repeat):
            if repeat == 2:
                self.report(2)
            return 0

        with patch.object(self.worker, "command", side_effect=command) as called, redirect_stdout(io.StringIO()):
            self.worker.run()
        self.assertEqual([call.args[0] for call in called.call_args_list], [1, 2, 3])
        self.assertEqual([(p.read_bytes(), p.stat().st_mtime_ns) for p in preserved], before)
        self.assertEqual(json.loads(self.worker.state_file.read_text())["stage"], "complete")

    def test_acceptance_failure_keeps_checkpoint_for_explicit_resume(self):
        with patch.object(self.worker, "command", return_value=1) as command, redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, "reuse its checkpoint"):
                self.worker.run()
        command.assert_called_once_with(1)
        self.assertEqual(json.loads(self.worker.state_file.read_text())["stage"], "failed")

    def test_prepare_only_never_dispatches(self):
        with patch.object(self.worker, "command") as command, redirect_stdout(io.StringIO()):
            self.worker.run(prepare_only=True)
        command.assert_not_called()
        self.assertEqual(json.loads(self.worker.state_file.read_text())["stage"], "ready")

    def test_worker_subprocess_uses_pipeline_identity_and_waits_for_its_run_lock(self):
        with patch.object(baseline_worker.subprocess, "run") as command:
            command.return_value.returncode = 0
            self.assertEqual(self.worker.command(2), 0)
        argv = command.call_args.args[0]
        self.assertEqual(argv[2:], [str(self.case), str(self.worker.host(2)), "--run-id", "parallel-v1-plain-2", "--wait-for-lock"])
        self.assertEqual(command.call_args.kwargs["cwd"], self.root)

    def test_cli_refuses_long_running_work_outside_tmux(self):
        with patch.dict(baseline_worker.os.environ, {"TMUX": ""}), \
                patch("sys.stderr", new=io.StringIO()), patch.object(baseline_worker, "BaselineWorker") as worker:
            with self.assertRaises(SystemExit):
                baseline_worker.main(["sample", "plain"])
        worker.assert_not_called()

    def test_version_and_repeat_are_restricted(self):
        with self.assertRaises(ValueError):
            baseline_worker.BaselineWorker("sample", "trained", root=self.root, repository=self.root)
        with self.assertRaises(ValueError):
            self.worker.run_id(4)


if __name__ == "__main__":
    unittest.main()
