"""Pipeline restarts retain completed experts and finish interrupted repetition plans."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import pipeline


class PipelineRestartTests(unittest.TestCase):
    def check_restart(self, stage, counts, continues, name="store-ticket"):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case = root / "experts/cases" / name
            case.mkdir(parents=True)
            (case / "questions.json").write_text("[]")
            agent = root / "runs/experts/host/agents" / f"expert-{name}"
            agent.mkdir(parents=True)
            (agent / "harness.json").write_text('{"revision":"trained"}')
            control = root / "runs/experts/control"
            (control / "ready").mkdir(parents=True)
            (control / "ready" / f"{name}.json").write_text("{}")
            (control / "dispatch.ready").touch()
            (control / f"{name}.json").write_text(json.dumps({"stage": stage}))
            with patch.object(pipeline, "ROOT", root), patch.object(pipeline, "REPOSITORY", root), \
                    patch.object(pipeline, "CONTROL", control):
                worker = pipeline.Pipeline(name, 3)
                with patch.object(worker, "accepted", side_effect=lambda tag: [None] * counts[tag]), \
                        patch.object(worker, "train") as train, patch.object(worker, "accept") as accept, \
                        patch.object(worker, "close_studio") as close, redirect_stdout(io.StringIO()):
                    worker.run()
                self.assertEqual(train.call_count, int(continues))
                self.assertEqual(accept.call_count, int(continues))
                close.assert_called_once()

    def test_previously_completed_expert_is_not_repeated(self):
        self.check_restart("complete", {"trained": 3, "plain": 3, "v0": 3}, False)

    def test_each_historical_expert_retains_its_existing_reports(self):
        for name in pipeline.ALIASES:
            with self.subTest(name=name):
                self.check_restart("complete", {tag: 3 for tag in ("trained", "plain", "v0")}, False, name)

    def test_interrupted_third_version_must_finish_repetition_plan(self):
        self.check_restart("failed", {"trained": 3, "plain": 3, "v0": 1}, True, "booking-page")

    def test_control_complete_cannot_reduce_later_expert_repetition_plan(self):
        self.check_restart("complete", {"trained": 1, "plain": 1, "v0": 1}, True, "booking-page")

    def test_cleanup_failure_does_not_repeat_complete_acceptance(self):
        self.check_restart("failed", {"trained": 3, "plain": 3, "v0": 3}, False)

    def test_analysis_recovery_stop_does_not_repeat_the_driver(self):
        with tempfile.TemporaryDirectory() as directory:
            worker = pipeline.Pipeline("booking-page", 3)
            worker.case = Path(directory)
            with patch.object(pipeline, "exists", return_value=False), \
                    patch.object(worker, "start_studio"), patch.object(worker, "state"), \
                    patch.object(worker, "command", return_value=75) as command, \
                    patch.object(pipeline.time, "sleep") as sleep:
                with self.assertRaisesRegex(RuntimeError, "Analysis recovery refused or exhausted"):
                    worker.train()
            command.assert_called_once()
            sleep.assert_not_called()


class PipelineAcceptanceOrderTests(unittest.TestCase):
    revision = "abcdef1234567890"

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pipeline-order-unit-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.case = self.root / "experts/cases/booking-page"
        (self.case / "wkr-booking-page").mkdir(parents=True)
        (self.case / "live.json").write_text('{"scenario":"wkr-booking-page","models":{"assessor":"moonshotai/kimi-k3"},"efforts":{"assessor":"high"}}')
        self.names = [f"{prefix}{number:02}" for prefix in ("x", "y") for number in range(1, 11)]
        (self.case / "questions.json").write_text(json.dumps([
            {"name": name, "group": "same" if name.startswith("x") else "new"} for name in self.names
        ]))
        (self.case / "wkr-booking-page/scenario.json").write_text('{"criteria":[{"id":"T1"}]}')
        self.tags = (self.revision[:12], "plain", "v0")
        for home, revision in (("host", self.revision), ("host-plain", "plain"), ("host-v0", "v0")):
            source = self.root / "runs/experts" / home / "agents/expert-booking-page"
            source.mkdir(parents=True)
            for name, value in (("harness.json", json.dumps({"revision": revision})), ("run.py", "# not executed"),
                                ("config.json", "{}"), ("subagent.json", "{}")):
                (source / name).write_text(value)
        (self.root / "runs/experts/control").mkdir(parents=True)
        for name, value in (("ROOT", self.root), ("REPOSITORY", self.root), ("CONTROL", self.root / "runs/experts/control")):
            patcher = patch.object(pipeline, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch("export.export")  # Fixture exports are already present; never read real configs.
        patcher.start()
        self.addCleanup(patcher.stop)
        self.worker = pipeline.Pipeline("booking-page", 3)

    def checkpoint(self, tag, repeat):
        return self.case / "accept-runs" / f"parallel-v1-{tag}-{repeat}" / "partial.json"

    def report(self, tag, repeat, *, checkpoint=True):
        path = self.case / f"accept-{tag}-fixture-{repeat}.json"
        rows = [{"name": name, "group": "same" if name.startswith("x") else "new", "product": "saved answer",
                 "error": None, "loose": [], "failed": [], "judged": ["T1"],
                 "verdicts": [{"id": "T1", "applicable": True, "count": 0, "reason": "Fake judge", "errors": []}]}
                for name in self.names]
        path.write_text(json.dumps(rows))
        if checkpoint:
            partial = self.checkpoint(tag, repeat)
            partial.parent.mkdir(parents=True, exist_ok=True)
            partial.write_text(json.dumps({"status": "complete", "run_id": f"parallel-v1-{tag}-{repeat}", "report": str(path)}))
        return path

    def test_repeat_one_and_three_finishing_first_still_joins_repeat_two(self):
        preserved = []
        for tag in self.tags:
            for repeat in (1, 3):
                report = self.report(tag, repeat)
                preserved.extend([report, self.checkpoint(tag, repeat)])
            checkpoint = self.checkpoint(tag, 2)
            checkpoint.parent.mkdir(parents=True, exist_ok=True)
            checkpoint.write_text(json.dumps({"status": "running", "run_id": f"parallel-v1-{tag}-2", "items": {"x01": {"stage": "judging"}}}))
        before = [(p.read_bytes(), p.stat().st_mtime_ns) for p in preserved]
        joined = []

        def command(argv, log):
            self.assertIn("--wait-for-lock", argv)
            run_id = argv[argv.index("--run-id") + 1]
            joined.append(run_id)
            tag, repeat = run_id.removeprefix("parallel-v1-").rsplit("-", 1)
            if repeat == "2":
                self.report(tag, 2)  # Simulate the existing owner completing while accept waits.
            return 0

        with patch.object(self.worker, "command", side_effect=command), redirect_stdout(io.StringIO()):
            self.worker.accept()
        self.assertEqual(joined, [f"parallel-v1-{tag}-{repeat}" for tag in self.tags for repeat in (1, 2, 3)])
        self.assertEqual([(p.read_bytes(), p.stat().st_mtime_ns) for p in preserved], before)
        self.assertEqual(len(list(self.case.glob("accept-*.json"))), 9)
        self.assertEqual(json.loads(self.worker.state_file.read_text())["stage"], "complete")

    def test_unrelated_third_report_cannot_replace_the_pending_second_repeat(self):
        for tag in self.tags:
            for repeat in (1, 3):
                self.report(tag, repeat)
            self.report(tag, "unrelated", checkpoint=False)
            checkpoint = self.checkpoint(tag, 2)
            checkpoint.parent.mkdir(parents=True, exist_ok=True)
            checkpoint.write_text(json.dumps({"status": "running", "run_id": f"parallel-v1-{tag}-2"}))
        self.assertFalse(self.worker.acceptance_complete(self.revision[:12]))
        with patch.object(self.worker, "command", return_value=0) as command, redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, "incomplete acceptance checkpoint"):
                self.worker.accept()
        self.assertEqual([call.args[0][-2] for call in command.call_args_list],
                         [f"parallel-v1-{self.tags[0]}-1", f"parallel-v1-{self.tags[0]}-2"])
        self.assertNotEqual(json.loads(self.worker.state_file.read_text())["stage"], "complete")

    def test_all_fixed_runs_are_retained_without_training_export_or_dispatch(self):
        for tag in self.tags:
            for repeat in (1, 2, 3):
                self.report(tag, repeat)
        with patch.object(self.worker, "train") as train, patch.object(self.worker, "accept") as accept, \
                patch.object(self.worker, "close_studio"), redirect_stdout(io.StringIO()):
            self.worker.run()
        train.assert_not_called()
        accept.assert_not_called()
        self.assertEqual(json.loads(self.worker.state_file.read_text())["stage"], "complete")

    def test_user_acceptance_stops_pipeline_without_additional_reports(self):
        saved = {"case": "booking-page", "stage": "complete", "acceptance_source": "user"}
        self.worker.state_file.write_text(json.dumps(saved))
        with patch.object(self.worker, "train") as train, patch.object(self.worker, "accept") as accept, \
                redirect_stdout(io.StringIO()):
            self.worker.run()
        train.assert_not_called()
        accept.assert_not_called()
        self.assertEqual(json.loads(self.worker.state_file.read_text()), saved)

    def test_final_completion_rechecks_all_three_versions_strictly(self):
        reports = [self.report(tag, repeat) for tag in self.tags for repeat in (1, 2, 3)]

        def command(argv, log):
            if argv[-2] == "parallel-v1-v0-3":
                rows = json.loads(reports[0].read_text())
                rows[-1]["verdicts"] = []  # Earlier report becomes ineligible before the final gate.
                reports[0].write_text(json.dumps(rows))
            return 0

        with patch.object(self.worker, "command", side_effect=command), redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, "all required complete"):
                self.worker.accept()
        self.assertNotEqual(json.loads(self.worker.state_file.read_text())["stage"], "complete")


if __name__ == "__main__":
    unittest.main()
