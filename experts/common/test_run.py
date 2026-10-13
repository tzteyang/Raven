"""Offline driver/resume regressions; no credentials, Studio processes or model calls.

From the repository root: uv run python -m unittest discover -s experts/common -p test_run.py -v
"""

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import resume
import run


class FakeStudio:
    """Persist the same round boundaries as Session.analyse/curate/holdout."""

    def __init__(self, *, done=0, onboarded=True, paused=False, reviewing=False,
                 cached=False, examined=False, curations=()):
        self.calls, self.logs, self.curations = [], [], set(curations)
        self.record = {"status": "paused" if paused else "running", "rounds": [
            {"sessions": {name: [] for name in names}, "feedback": {"decision": "continue"}}
            for names in run.ROUNDS[:done]
        ], "pending": {}}
        self.current = {
            "step": None, "status": self.record["status"], "onboarded": onboarded,
            "reviewing": reviewing, "assessor": True, "revision": "unchanged-revision",
            "exam": {"current": {"failed": 0, "judged": 1} if cached else None},
        }
        if reviewing:
            self.record["pending"]["review"] = {"activity": []}
        if examined:
            self.exam()

    def exam(self):
        self.record["pending"].update(holdout={"x01": [], "y01": []},
                                      holdout_signals=[{"source": "judge", "items": [{"result": "fail"}]}])
        self.record["pending"].pop("holdout_assessment", None)
        self.current["exam"]["current"] = {"failed": 1, "judged": 1}

    def state(self, session):
        state, record = copy.deepcopy(self.current), copy.deepcopy(self.record)
        state["rounds"] = len(record["rounds"])
        state["assessed"] = bool(record["pending"].get("signals"))
        state["pending"] = {part: len(record["pending"].get(part, ())) for part in ("sessions", "signals")}
        return {"attached": True, "state": state, "record": record}

    def log(self, message):
        self.logs.append(message)

    def step(self, session, op, body=None):
        self.calls.append((op, body))
        assert self.record["status"] != "error"
        pending = self.record["pending"]
        if op == "onboard":
            assert not self.record["rounds"]
            self.current["onboarded"] = True
            self.current["status"] = self.record["status"] = "running"
        elif op == "curate":
            assert "review" in pending
            self.current["reviewing"] = False
            self.current["status"] = self.record["status"] = "running"
            self.record["pending"] = {}
            self.current["revision"] = f"curated-{len(self.record['rounds'])}"
        elif op == "exam":
            assert self.current["onboarded"] and self.record["status"] == "running"
            assert "review" not in pending
            assert not run.exam_complete(self.record), "the completed pending exam must not run twice"
            self.exam()
        elif op == "script":
            assert run.exam_complete(self.record)
            assert not (set(pending.get("sessions", {})) & set(body["names"]))
            pending.setdefault("sessions", {}).update({name: [] for name in body["names"]})
        elif op == "assess":
            assert pending.get("sessions")
            pending["signals"] = [{"source": "judge"}]
        elif op == "analyse":
            assert pending.get("sessions") and pending.get("signals")
            self.record["rounds"].append(copy.deepcopy(pending))
            number = len(self.record["rounds"])
            self.current["reviewing"] = number in self.curations
            self.current["outcome"] = {"next": "curate" if self.current["reviewing"] else "continue"}
            self.record["pending"] = {"review": {"activity": []}} if self.current["reviewing"] else {}
        else:
            raise AssertionError(op)
        return self.state(session)["state"]


class DriverTests(unittest.TestCase):
    def cultivate(self, studio, extra=None):
        run.cultivate(studio, "kept-session", "working instructions", extra)
        self.assertEqual(studio.logs[-1], "ALL ROUNDS DONE")

    def resume(self, studio):
        with tempfile.TemporaryDirectory(prefix="driver-unit-") as directory:
            case = Path(directory)
            (case / "wkr-fixture").mkdir()
            (case / "wkr-fixture/onboarding.md").write_text("working instructions")
            (case / "session.txt").write_text("kept-session\n")
            with patch.object(run, "Studio", return_value=studio):
                resume.main(["8800", str(case)])

    def test_resume_initialization_and_paused_initial_curation_before_exam(self):
        for onboarded, paused in ((False, False), (True, True), (False, True)):
            with self.subTest(onboarded=onboarded, paused=paused):
                studio = FakeStudio(onboarded=onboarded, paused=paused, cached=True)
                self.resume(studio)
                self.assertEqual([op for op, _ in studio.calls[:2]], ["onboard", "exam"])
                self.assertEqual(len(studio.record["rounds"]), 4)

    def test_resume_reviewing_or_paused_last_round_curates_before_exam(self):
        for paused in (False, True):
            with self.subTest(paused=paused):
                studio = FakeStudio(done=4, reviewing=True, paused=paused, cached=True)
                self.resume(studio)
                self.assertEqual([op for op, _ in studio.calls], ["curate", "exam"])
                self.assertEqual(studio.logs[-1], "ALL ROUNDS DONE")

    def test_run_does_not_skip_last_curation_at_round_count_limit(self):
        studio = FakeStudio(done=4, reviewing=True, cached=True)
        # A saved review is sufficient even if the transient process flag is absent.
        studio.current["reviewing"] = False
        self.cultivate(studio)
        self.assertEqual([op for op, _ in studio.calls], ["curate", "exam"])

    def test_same_revision_cache_does_not_skip_missing_round_exams(self):
        studio = FakeStudio(done=3, cached=True)
        self.cultivate(studio)
        self.assertEqual([op for op, _ in studio.calls], ["exam", "script", "assess", "analyse", "exam"])
        self.assertEqual(studio.current["revision"], "unchanged-revision")

    def test_pending_holdout_assessment_requires_exam_despite_signals_and_cache(self):
        studio = FakeStudio(done=4, examined=True)
        studio.record["pending"]["holdout_assessment"] = {"sessions": ["x01", "y01"]}
        self.cultivate(studio)
        self.assertEqual([op for op, _ in studio.calls], ["exam"])

    def test_holdout_answers_without_judge_signals_are_not_completed(self):
        studio = FakeStudio(done=4, examined=True)
        studio.record["pending"]["holdout_signals"] = []
        self.cultivate(studio)
        self.assertEqual([op for op, _ in studio.calls], ["exam"])

    def test_record_error_never_reports_completion_even_with_four_rounds(self):
        studio = FakeStudio(done=4, examined=True)
        studio.record.update(status="error", error="analyst assessment failed")
        with self.assertRaisesRegex(RuntimeError, "session record is error: analyst assessment failed"):
            self.resume(studio)
        self.assertEqual(studio.calls, [])
        self.assertNotIn("ALL ROUNDS DONE", studio.logs)

    def test_normal_flow_exams_baseline_and_each_round_including_unchanged_revisions(self):
        studio = FakeStudio(onboarded=False, curations=(1, 3))
        self.cultivate(studio)
        expected = ["onboard", "exam"]
        for number in range(1, 5):
            expected += ["script", "assess", "analyse"]
            if number in (1, 3):
                expected += ["curate"]
            expected += ["exam"]
        self.assertEqual([op for op, _ in studio.calls], expected)
        self.assertEqual([body["names"] for op, body in studio.calls if op == "script"], run.ROUNDS)
        self.assertTrue(all(round_["holdout_signals"] for round_ in studio.record["rounds"]))
        self.assertTrue(run.exam_complete(studio.record))

    def test_complete_session_does_not_replay_training_or_exams(self):
        studio = FakeStudio(done=4, examined=True)
        self.cultivate(studio)
        self.assertEqual(studio.calls, [])

    def test_extra_rounds_follow_the_existing_completed_rounds(self):
        studio = FakeStudio(done=4, examined=True)
        self.cultivate(studio, [["t01"], ["t02"]])
        self.assertEqual(len(studio.record["rounds"]), 6)
        self.assertEqual([body["names"] for op, body in studio.calls if op == "script"], [["t01"], ["t02"]])

    def test_existing_practice_and_assessment_resume_at_analysis(self):
        studio = FakeStudio(done=3, examined=True)
        studio.record["pending"].update(sessions={name: [] for name in run.ROUNDS[3]}, signals=[{"source": "judge"}])
        self.cultivate(studio)
        self.assertEqual([op for op, _ in studio.calls], ["analyse", "exam"])

    def test_resumed_analysis_failure_reuses_saved_training_and_exam(self):
        studio = FakeStudio(done=3, examined=True)
        failed_round = copy.deepcopy(studio.record["pending"])
        failed_round.update(sessions={name: [] for name in run.ROUNDS[3]},
                            signals=[{"source": "judge"}], feedback=None)
        studio.record["rounds"].append(failed_round)
        studio.record.update(status="error", error="analyst: provider error: HTTP 503")
        studio.record["pending"] = {}
        studio.current["status"] = "error"

        def recover(session, snapshot):
            self.assertTrue(run.transient_analysis(snapshot))
            studio.record["pending"] = studio.record["rounds"].pop()
            studio.record["status"] = studio.current["status"] = "running"
            return True

        with patch.object(studio, "recover_analysis", side_effect=recover, create=True) as restored:
            self.cultivate(studio)
        restored.assert_called_once()
        self.assertEqual([op for op, _ in studio.calls], ["analyse", "exam"])
        self.assertEqual(len(studio.record["rounds"]), 4)


class StepTests(unittest.TestCase):
    def analysis_failure(self):
        failed = FakeStudio(done=1).state("kept-session")
        failed["record"].update(status="error", error="analyst: provider error: HTTP 503")
        failed["record"]["rounds"][-1]["feedback"] = None
        failed["state"].update(status="error", failed="analyse", error=failed["record"]["error"])
        return failed

    def test_transient_analysis_recovery_retries_analysis_only(self):
        studio = run.Studio(8800, Path("unused.log"))
        failed = self.analysis_failure()
        restored = FakeStudio(done=0, examined=True).state("kept-session")
        complete = FakeStudio(done=1).state("kept-session")
        with patch.object(studio, "call", return_value=(200, {"ok": True})) as call, \
                patch.object(studio, "state", side_effect=[failed, restored, complete]), \
                patch.object(studio, "log"), patch.object(run.time, "sleep") as sleep:
            studio.step("kept-session", "analyse")
        self.assertEqual([item.args[0].rsplit("/", 1)[-1] for item in call.call_args_list],
                         ["analyse", "retry_analysis", "analyse"])
        sleep.assert_called_once_with(60)

    def test_detached_analysis_recovery_uses_explicit_resume(self):
        studio = run.Studio(8800, Path("unused.log"))
        failed = self.analysis_failure()
        failed["attached"] = False
        restored = FakeStudio(done=0, examined=True).state("kept-session")
        with patch.object(studio, "call", return_value=(202, {})) as call, \
                patch.object(studio, "state", return_value=restored), \
                patch.object(studio, "log"), patch.object(run.time, "sleep"):
            self.assertTrue(studio.recover_analysis("kept-session", failed))
        call.assert_called_once_with("/kept-session/resume", {"retry": "analyse"})

    def test_analysis_recovery_refusal_is_not_retried(self):
        studio = run.Studio(8800, Path("unused.log"))
        with patch.object(studio, "call", return_value=(409, {"error": "revision changed"})) as call, \
                patch.object(studio, "state") as state, \
                patch.object(studio, "log"), patch.object(run.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "analysis recovery refused.*revision changed"):
                studio.recover_analysis("kept-session", self.analysis_failure())
        call.assert_called_once()
        state.assert_not_called()

    def test_analysis_retry_budget_is_preserved_in_the_record(self):
        studio = run.Studio(8800, Path("unused.log"))
        failed = self.analysis_failure()
        failed["record"]["analysis_failures"] = [{"round": 1}] * 8
        with patch.object(studio, "call") as call, patch.object(run.time, "sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError, "recovery exhausted"):
                studio.recover_analysis("kept-session", failed)
        call.assert_not_called()
        sleep.assert_not_called()

    def test_assessment_and_nontransient_errors_do_not_request_analysis_recovery(self):
        studio = run.Studio(8800, Path("unused.log"))
        for step, error in (("assess", "HTTP 503"), ("analyse", "invalid feedback")):
            failed = self.analysis_failure()
            failed["record"].update(error_step=step, error=error)
            with self.subTest(step=step), patch.object(studio, "call") as call:
                self.assertFalse(studio.recover_analysis("kept-session", failed))
                call.assert_not_called()

    def test_transient_exam_assessment_retry_remains_supported(self):
        studio = run.Studio(8800, Path("unused.log"))
        failed = FakeStudio(done=4).state("kept-session")
        failed["state"].update(failed="exam", error="HTTP 503 GATEWAY_CONCURRENCY_FULL")
        complete = FakeStudio(done=4, examined=True).state("kept-session")
        with patch.object(studio, "call", return_value=(200, {"ok": True})) as call, \
                patch.object(studio, "state", side_effect=[failed, complete]), \
                patch.object(studio, "log"), patch.object(run.time, "sleep") as sleep:
            studio.step("kept-session", "exam")
        self.assertEqual(call.call_count, 2)
        sleep.assert_called_once_with(60)

    def test_step_checks_terminal_record_even_without_failed_flag(self):
        studio = run.Studio(8800, Path("unused.log"))
        failed = FakeStudio(done=4).state("kept-session")
        failed["record"].update(status="error", error="permanent curator failure")
        with patch.object(studio, "call", return_value=(200, {"ok": True})), \
                patch.object(studio, "state", return_value=failed), patch.object(studio, "log"):
            with self.assertRaisesRegex(RuntimeError, "permanent curator failure"):
                studio.step("kept-session", "curate")

    def test_paused_step_exhaustion_fails_instead_of_reporting_done(self):
        studio = run.Studio(8800, Path("unused.log"))
        paused = FakeStudio(done=4, reviewing=True, paused=True).state("kept-session")
        with patch.object(studio, "call", return_value=(200, {"ok": True})), \
                patch.object(studio, "state", return_value=paused), patch.object(studio, "log"):
            with self.assertRaisesRegex(RuntimeError, "still paused"):
                studio.step("kept-session", "curate", resumes=0)


if __name__ == "__main__":
    unittest.main()
