"""Offline reporting regressions; no model calls or experiment writes.

From the repository root: uv run python -m unittest discover -s experts/common -p test_scorecard.py -v
"""

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scorecard import (_studio_record, case_spec, cell, examples, report_issues, reports_of,
                       route_context, route_summary, route_table, studio_exams, tally)


CRITERIA = [{"id": "body"}, {"id": "format"}]
QUESTIONS = [{"name": f"{prefix}{n:02}", "group": group}
             for prefix, group in (("x", "same"), ("y", "new")) for n in range(1, 11)]


def row(name, failed=False, format_applicable=True):
    return {"name": name, "group": "same" if name.startswith("x") else "new", "error": None,
            "product": "saved answer", "loose": [], "failed": ["body"] if failed else [],
            "judged": ["body", "format"] if format_applicable else ["body"], "verdicts": [
                {"id": "body", "applicable": True, "count": int(failed), "reason": "Saved model verdict.",
                 "errors": [{"quote": "saved answer", "problem": "The judge identified this error."}] if failed else []},
                {"id": "format", "applicable": format_applicable, "count": 0, "errors": [], "reason": "Saved model verdict."},
            ]}


class ScorecardTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="scorecard-test-")
        self.addCleanup(temporary.cleanup)
        self.case = Path(temporary.name) / "sample"
        self.case.mkdir()
        (self.case / "scenario").mkdir()
        self.write("questions.json", QUESTIONS)
        self.write("scenario/scenario.json", {"criteria": CRITERIA})
        self.write("live.json", {"scenario": "scenario", "root": "studio"})
        self.rows = [row(q["name"]) for q in QUESTIONS]

    def write(self, relative, value):
        path = self.case / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        return path

    def test_hash_names_work_but_partial_duplicate_and_missing_verdicts_do_not(self):
        good = self.write("accept-deadbeef0123-1011-193059-1234567890.json", self.rows)
        self.write("accept-deadbeef0123-1011-193059-partial.json", self.rows[:1])
        duplicate = copy.deepcopy(self.rows)
        duplicate[-1] = duplicate[0]
        self.write("accept-deadbeef0123-1011-193059-duplicate.json", duplicate)
        missing = copy.deepcopy(self.rows)
        missing[0]["verdicts"] = []
        self.write("accept-deadbeef0123-1011-193059-missing.json", missing)
        self.write("accept-runs/not-finished/partial.json", self.rows)
        admitted, excluded = reports_of(self.case, "deadbeef0123")
        self.assertEqual([p for p, _ in admitted], [good])
        self.assertEqual(len(excluded), 3)
        self.assertTrue(all(any(s.startswith("unknown:") for s in issues) for _, issues in excluded))

    def test_model_verdicts_must_cover_exact_criteria_and_agree_with_summary(self):
        questions, criteria = case_spec(self.case)
        self.assertEqual(report_issues(self.rows, questions, criteria), [])
        mutations = {
            "missing criterion": lambda r: r["verdicts"].pop(),
            "duplicate criterion": lambda r: r["verdicts"].append(copy.deepcopy(r["verdicts"][0])),
            "wrong summary": lambda r: r.update(failed=["body"]),
            "unknown": lambda r: r["verdicts"][0].update(result="unknown"),
            "wrong group": lambda r: r.update(group="new"),
            "unquoted": lambda r: r.update(loose=["not in answer"]),
        }
        for description, mutate in mutations.items():
            with self.subTest(description=description):
                rows = copy.deepcopy(self.rows)
                mutate(rows[0])
                self.assertTrue(any(i.startswith("unknown:") for i in report_issues(rows, questions, criteria)))

    def test_dispatch_error_unknown_and_not_applicable_are_not_performance(self):
        error = row("x02", failed=True)
        error["error"] = "ConnectionError: gateway unavailable"
        unknown = {"name": "x03", "group": "same", "failed": [], "judged": [], "verdicts": [], "error": None}
        na = row("x04", format_applicable=False)
        na["verdicts"][0]["applicable"] = False
        na["judged"] = []
        counts = tally([row("x01"), error, unknown, na])
        self.assertEqual(counts["same"], [0, 2])
        self.assertEqual(counts["same_ok"], [1, 1])
        self.assertEqual((counts["same_error"], counts["same_unknown"], counts["same_not_applicable"]), (1, 1, 2))
        rows = copy.deepcopy(self.rows)
        rows[1] = error
        self.assertTrue(any(i.startswith("error:") for i in report_issues(rows, QUESTIONS, CRITERIA)))

    def test_differing_applicability_keeps_each_actual_denominator(self):
        first = tally([row("x01", failed=True)])
        second = tally([row("x01", failed=True, format_applicable=False)])
        self.assertEqual(cell([first, second], "same"), "2/3（每次 1/2, 1/1）")

    def test_route_layers_keep_one_mixed_twenty_question_run_whole(self):
        rows = copy.deepcopy(self.rows)
        rows[0] = row("x01", failed=True)
        for index in (0, 19):
            rows[index]["transport"] = {"provider": "custom gateway", "model": "glm-5.3-flash",
                                         "client_alias": "z-ai/glm-5.3-flash", "since": index,
                                         "caveat": "provider equivalence unverified"}
        original = copy.deepcopy(rows)
        summary = route_summary({"培养后": [(self.case / "mixed.json", rows)]})
        self.assertEqual((summary["state"], summary["complete_reports"], summary["mixed_reports"]), ("mixed", 1, 1))
        self.assertEqual(sum(s["answers"] for s in summary["strata"]), 20)
        self.assertEqual(sorted(summary["reports"][0]["routes"].values()), [2, 18])
        self.assertEqual(len(summary["routes"]), 2)  # Different since timestamps share a route.
        new_id = next(r["id"] for r in summary["routes"] if r["kind"] == "new")
        new = {(s["route"], s["group"]): s for s in summary["strata"]}
        self.assertEqual((new[new_id, "same"]["answers"], new[new_id, "same"]["failed"]), (1, 1))
        self.assertEqual((new[new_id, "new"]["answers"], new[new_id, "new"]["fully_correct"]), (1, 1))
        self.assertEqual(rows, original)
        rendered = "\n".join(route_table(summary))
        self.assertIn("原完整运行共 1 次", rendered)
        self.assertIn("仍只计一次完整20题验收", rendered)

    def test_route_metadata_distinguishes_legacy_new_and_explicit_unknown(self):
        found = lambda rows: {"plain": [(self.case / "report.json", rows)]}
        old = route_summary(found(self.rows))
        self.assertEqual(old["state"], "legacy")
        self.assertEqual(old["routes"][0]["implicit_legacy_answers"], 20)
        rows = copy.deepcopy(self.rows)
        for r in rows:
            r["transport"] = {"provider": "custom gateway", "model": "glm-5.3-flash", "client_alias": "z-ai/glm-5.3-flash"}
        self.assertEqual(route_summary(found(rows))["state"], "new")
        rows[0]["transport"] = {}
        unknown = route_summary(found(rows))
        self.assertEqual(unknown["state"], "unknown")
        self.assertTrue(any(r["kind"] == "unknown" for r in unknown["routes"]))
        self.assertFalse(any(r["kind"] == "legacy" for r in unknown["routes"]))

    def test_recovery_notice_does_not_relabel_saved_legacy_answers(self):
        self.write("experts/reports/quota-recovery-executed.json", {
            "questions": 109, "changes": [{"case": "sample", "run_id": "repaired", "questions": ["x01", "y01"]}]})
        old = route_summary({"plain": [(self.case / "report.json", self.rows)]})
        with patch("scorecard.REPOSITORY", self.case):
            text = "\n".join(route_context(self.case, old))
            clean = "\n".join(route_context(self.case / "unaffected", old))
        self.assertIn("纯旧通道", text)  # Recovery is not evidence that old rows used the new provider.
        self.assertIn("2 道派活", text)
        self.assertIn("全批共 109 道", text)
        self.assertIn("未独立验证", text)
        self.assertIn("不能把通道变化后的差异归为纯训练因果增益", text)
        self.assertIn("没有因事故重跑", clean)

    def test_examples_include_fixed_question_improvement_and_regression(self):
        before = [row("x01"), row("x02", failed=True), row("x03")]
        after = [row("x01"), row("x02"), row("x03", failed=True)]
        selected = dict(examples(before, after))
        self.assertEqual(set(selected), {"x01", "x02", "x03"})
        self.assertIn("固定", selected["x01"])
        self.assertIn("改善", selected["x02"])
        self.assertIn("退步", selected["x03"])
        after[1]["error"] = "dispatch error"
        self.assertNotIn("x02", dict(examples(before, after)))

    def test_studio_uses_current_session_and_preserves_unknown_by_source(self):
        (self.case / "session.txt").write_text("current-session")
        self.write("studio/runs/current-session/iteration/record.json", {
            "rounds": [{"holdout_signals": [
                {"source": "rules-judge", "items": [
                    {"id": "body:x01", "session": "x01", "result": "pass"},
                    {"id": "body:y01", "session": "y01", "result": "fail"}]},
                {"source": "assessor", "items": [{"id": "R1", "session": None, "result": "unknown"}]},
            ]}], "pending": None,
        })
        self.write("studio/runs/obsolete-session/iteration/record.json", {"rounds": [{"holdout_signals": [
            {"source": "obsolete", "items": [{"id": "body:x01", "result": "fail"}]}]}]})
        (self.case / "run.out").write_text("exam=999/999\n")
        got = studio_exams(self.case)
        by = {(r["source"], r["group"]): r for r in got}
        self.assertEqual(set(by), {("rules-judge", "x"), ("rules-judge", "y"), ("assessor", "未定位")})
        self.assertEqual(by["rules-judge", "x"]["pass"], 1)
        self.assertEqual(by["rules-judge", "y"]["fail"], 1)
        self.assertEqual(by["assessor", "未定位"]["unknown"], 1)
        self.assertTrue(all(r["session"] == "current-session" for r in got))

    def test_studio_cache_tracks_mtime_size_and_session_without_sharing_mutable_rows(self):
        _studio_record.cache_clear()
        self.addCleanup(_studio_record.cache_clear)
        session = self.case / "session.txt"
        session.write_text("first")
        data = {"rounds": [{"holdout_signals": [{"source": "rules-judge", "items": [
            {"id": "body:x01", "result": "pass"}]}]}]}
        path = self.write("studio/runs/first/iteration/record.json", data)
        reads = []
        original_read = Path.read_text

        def tracked_read(target, *args, **kwargs):
            if target == path:
                reads.append(target)
            return original_read(target, *args, **kwargs)

        with patch.object(Path, "read_text", tracked_read):
            initial = studio_exams(self.case)
            initial[0]["pass"] = 999  # UI formatting cannot corrupt cached counts.
            self.assertEqual(studio_exams(self.case)[0]["pass"], 1)
            self.assertEqual(len(reads), 1)

            old = path.stat()
            data["rounds"][0]["holdout_signals"][0]["items"][0]["result"] = "fail"
            self.write("studio/runs/first/iteration/record.json", data)
            self.assertEqual(path.stat().st_size, old.st_size)
            os.utime(path, ns=(old.st_atime_ns, old.st_mtime_ns + 1))
            self.assertEqual(studio_exams(self.case)[0]["fail"], 1)
            self.assertEqual(len(reads), 2)

            old = path.stat()
            data["rounds"][0]["holdout_signals"][0]["items"].append({"id": "body:x02", "result": "unknown"})
            self.write("studio/runs/first/iteration/record.json", data)
            os.utime(path, ns=(old.st_atime_ns, old.st_mtime_ns))  # Size alone invalidates.
            self.assertEqual(studio_exams(self.case)[0]["unknown"], 1)
            self.assertEqual(len(reads), 3)

            self.write("studio/runs/second/iteration/record.json", {"rounds": [], "pending": {"holdout_signals": [
                {"source": "assessor", "items": [{"id": "R1", "result": "unknown"}]}]}})
            session.write_text("second")
            changed = studio_exams(self.case)
            self.assertEqual([(r["session"], r["source"]) for r in changed], [("second", "assessor")])
        self.assertEqual(_studio_record.cache_info().maxsize, 64)


if __name__ == "__main__":
    unittest.main()
