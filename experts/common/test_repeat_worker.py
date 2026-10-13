"""Offline single-repeat coordination tests; shared lock behavior lives in test_accept.py."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import baseline_worker
import repeat_worker


class RepeatWorkerTests(unittest.TestCase):
    revision = "abcdef1234567890"

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="repeat-unit-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.case = self.root / "experts/cases/sample"
        (self.case / "wkr-sample").mkdir(parents=True)
        (self.case / "live.json").write_text('{"scenario":"wkr-sample","models":{"assessor":"moonshotai/kimi-k3"},"efforts":{"assessor":"high"}}')
        self.names = [f"{prefix}{number:02}" for prefix in ("x", "y") for number in range(1, 11)]
        (self.case / "questions.json").write_text(json.dumps([
            {"name": name, "group": "same" if name.startswith("x") else "new"} for name in self.names
        ]))
        (self.case / "wkr-sample/scenario.json").write_text('{"criteria":[{"id":"T1"}]}')
        for home, revision in (("host-plain", "plain"), ("host-v0", "v0"), ("host", self.revision)):
            source = self.root / "runs/experts" / home / "agents/expert-sample"
            source.mkdir(parents=True)
            for name, content in (("harness.json", json.dumps({"revision": revision, "artifact": {}})),
                                  ("run.py", "# never executed\n"), ("config.json", '{}'), ("subagent.json", '{}')):
                (source / name).write_text(content)
        self.other_states = [self.root / "runs/experts/control/sample.json",
                             self.root / "runs/experts/control/baselines/sample-plain.json"]
        for path in self.other_states:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{"stage":"acceptance"}')

    def worker(self, tag="plain", repeat=2):
        return repeat_worker.RepeatWorker("sample", tag, repeat, root=self.root, repository=self.root)

    def report(self, worker, *, unknown=False):
        path = self.case / f"accept-{worker.version}-fixture-{worker.repeat}.json"
        rows = [{"name": name, "group": "same" if name.startswith("x") else "new", "product": "saved answer",
                 "error": None, "loose": [], "failed": [], "judged": ["T1"],
                 "verdicts": [{"id": "T1", "applicable": True, "count": 0, "reason": "Fake model decision", "errors": []}]}
                for name in self.names]
        if unknown:
            rows[-1]["verdicts"] = []
        path.write_text(json.dumps(rows))
        checkpoint = self.case / "accept-runs" / worker.run_id(worker.repeat) / "partial.json"
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_text(json.dumps({"status": "complete", "run_id": worker.run_id(worker.repeat), "report": str(path)}))
        return path

    def test_prepares_only_the_requested_repeat_from_each_export_without_dispatch(self):
        for tag in ("plain", "v0", self.revision[:12]):
            with self.subTest(tag=tag):
                worker = self.worker(tag)
                with patch.object(worker, "command") as command, redirect_stdout(io.StringIO()):
                    worker.run(prepare_only=True)
                command.assert_not_called()
                self.assertFalse(worker.host(1).exists())
                self.assertFalse(worker.host(3).exists())
                host = worker.host(2)
                self.assertEqual((host / "config.json").readlink(), self.root / "secrets/raven-experts.json")
                for name in baseline_worker.FILES:
                    self.assertEqual((host / "agents/expert-sample" / name).read_bytes(), (worker.source / name).read_bytes())
                saved = json.loads(worker.state_file.read_text())
                self.assertEqual((saved["stage"], saved["repeat"], saved["run_id"]), ("ready", 2, f"parallel-v1-{tag}-2"))

    def test_existing_checkpoint_and_runtime_are_not_changed_by_preparation(self):
        worker = self.worker(self.revision[:12])
        worker.prepare()
        report = self.report(worker)
        checkpoint = self.case / "accept-runs" / worker.run_id(2) / "partial.json"
        runtime = worker.host(2) / "runtime-progress"
        runtime.write_text("existing runtime state")
        paths = [report, checkpoint, runtime, worker.host(2) / "agents/expert-sample/harness.json"]
        before = [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths]
        worker.prepare()
        self.assertEqual([(path.read_bytes(), path.stat().st_mtime_ns) for path in paths], before)
        # The current trained export must match the selected tag before a new host can be made.
        other = self.worker("0123456789ab", 3)
        with self.assertRaisesRegex(ValueError, "does not match"):
            other.prepare()
        self.assertFalse(other.host(3).exists())

    def test_one_admitted_report_updates_only_its_repeat_state(self):
        worker = self.worker(self.revision[:12], 3)
        before = [path.read_bytes() for path in self.other_states]
        with patch.object(worker, "command", side_effect=lambda repeat: self.report(worker) and 0) as command, \
                redirect_stdout(io.StringIO()):
            worker.run()
        command.assert_called_once_with(3)
        saved = json.loads(worker.state_file.read_text())
        self.assertEqual((saved["stage"], saved["repeat"]), ("complete", 3))
        self.assertEqual([path.read_bytes() for path in self.other_states], before)
        self.assertEqual(len(list(self.case.glob("accept-*.json"))), 1)

    def test_incomplete_model_evidence_stops_without_replacing_the_answer(self):
        worker = self.worker("v0")
        with patch.object(worker, "command", side_effect=lambda repeat: self.report(worker, unknown=True) and 0) as command, \
                redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, "not admitted"):
                worker.run()
        command.assert_called_once_with(2)
        self.assertEqual(json.loads(worker.state_file.read_text())["stage"], "failed")
        self.assertEqual(len(list(self.case.glob("accept-*.json"))), 1)

    def test_subprocess_joins_the_exact_pipeline_run_and_keeps_a_separate_log(self):
        worker = self.worker(self.revision[:12], 3)
        with patch.object(baseline_worker.subprocess, "run") as command:
            command.return_value.returncode = 0
            self.assertEqual(worker.command(3), 0)
        self.assertEqual(command.call_args.args[0][2:], [str(self.case), str(worker.host(3)),
                        "--run-id", f"parallel-v1-{self.revision[:12]}-3", "--wait-for-lock"])
        self.assertEqual(Path(command.call_args.kwargs["stdout"].name).parent,
                         self.root / "runs/experts/control/repeats/logs")

    def test_cli_rejects_extra_samples_and_requires_tmux_for_execution(self):
        for args in (["sample", "plain", "4"], ["sample", "plain", "2"]):
            with patch.dict(repeat_worker.os.environ, {"TMUX": ""}), \
                    patch("sys.stderr", new=io.StringIO()), patch.object(repeat_worker, "RepeatWorker") as worker:
                with self.assertRaises(SystemExit):
                    repeat_worker.main(args)
            worker.assert_not_called()
        with patch.dict(repeat_worker.os.environ, {"TMUX": ""}), patch.object(repeat_worker, "RepeatWorker") as worker:
            repeat_worker.main(["sample", "plain", "2", "--prepare-only"])
        worker.return_value.run.assert_called_once_with(prepare_only=True)


if __name__ == "__main__":
    unittest.main()
