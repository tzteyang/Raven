"""Offline completeness/rate regressions for the 22-expert summary."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import summary_scorecard as summary
from test_scorecard import CRITERIA, QUESTIONS, row


class SummaryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="expert-summary-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.cases = self.root / "experts/cases"
        for target, value in (("summary_scorecard.GTM", self.root), ("summary_scorecard.CASES", self.cases),
                              ("scorecard.GTM", self.root)):
            mock = patch(target, value)
            mock.start()
            self.addCleanup(mock.stop)

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def make_case(self, name, repeats=1):
        case = self.cases / name
        self.write(case / "manifest.json", {"name": "测试专家"})
        self.write(case / "questions.json", QUESTIONS)
        self.write(case / "scenario/scenario.json", {"criteria": CRITERIA})
        self.write(case / "live.json", {"scenario": "scenario", "root": "studio"})
        (case / "session.txt").write_text("current")
        (case / "run.out").write_text("10-11 20:00:00 exam done in 1s revision=abcdef123456 exam=0/40\n10-11 20:00:00 ALL ROUNDS DONE\n")
        deployment = {"revision": "abcdef1234567890", "artifact": {"files": {}, "values": {}},
                      "state": {}, "task": {"id": name}, "sha256": "verified-source-id"}
        self.write(case / "studio/runs/current/deployment.json", deployment)
        folder = self.root / "runs/experts/host/agents" / f"expert-{name}"
        self.write(folder / "harness.json", {**deployment, "source": {
            "case": name, "session": "current", "deployment_sha256": "verified-source-id"}})
        self.write(folder / "subagent.json", {"kind": "acp", "enabled": True})
        (folder / "run.py").write_text("# not executed\n")
        for tag in ("plain", "v0", "abcdef123456"):
            for n in range(repeats):
                self.write(case / f"accept-{tag}-1011-20000{n}-hash{n}.json", [row(q["name"]) for q in QUESTIONS])
        return case

    def user_accept(self, name, revision="abcdef123456"):
        self.write(self.root / "runs/experts/control" / f"{name}.json", {
            "stage": "complete", "acceptance_source": "user", "revision": revision,
            "acceptance_decision": "现在就当做全都通过验收了", "acceptance_at": "2026-10-12T00:00:00+00:00"})

    def test_historical_one_repeat_is_retained_but_new_expert_requires_three(self):
        self.make_case("store-ticket")
        self.make_case("new-case")
        self.write(self.root / "runs/experts/control/new-case.json", {"stage": "complete"})
        old = summary.expert("store-ticket", "old", "领域", "3.1")
        new = summary.expert("new-case", "new", "领域", "3.2")
        self.assertTrue(old["complete"])
        self.assertEqual(old["required"], 1)
        self.assertFalse(new["accepted"])
        self.assertEqual(new["required"], 3)
        self.assertTrue(new["trained"] and new["exported"])
        self.assertIn("临时成绩总表（未完成）", summary.render([old, new], "snapshot"))

    def test_unknown_report_is_excluded_even_if_control_claims_complete(self):
        case = self.make_case("new-case", repeats=3)
        self.write(self.root / "runs/experts/control/new-case.json", {"stage": "complete"})
        path = case / "accept-v0-1011-200002-hash2.json"
        rows = json.loads(path.read_text())
        rows[0]["verdicts"] = []
        self.write(path, rows)
        result = summary.expert("new-case", "new", "领域", "1.1")
        self.assertFalse(result["complete"])
        self.assertEqual(len(result["admitted"]["v0"]), 2)
        self.assertEqual(result["excluded"]["v0"][0][0], path)
        text = summary.render([result], "snapshot")
        self.assertIn("缺少逐项 LLM verdict", text)
        self.assertIn(path.name, text)

    def test_stale_export_and_later_training_failure_do_not_count_complete(self):
        case = self.make_case("new-case", repeats=3)
        good = summary.expert("new-case", "new", "领域", "1.1")
        self.assertTrue(good["complete"])
        self.assertIn("最终成绩总表", summary.render([good], "snapshot"))
        (case / "run.out").write_text((case / "run.out").read_text() + "STOPPED: interrupted new round\n")
        folder = self.root / "runs/experts/host/agents/expert-new-case"
        harness = json.loads((folder / "harness.json").read_text())
        harness["artifact"]["files"]["changed.py"] = "changed after deployment"
        self.write(folder / "harness.json", harness)
        self.user_accept("new-case")
        changed = summary.expert("new-case", "new", "领域", "1.1")
        self.assertFalse(changed["trained"])
        self.assertFalse(changed["exported"])
        self.assertTrue(changed["accepted"])
        self.assertTrue(changed["user_accepted"])
        self.assertFalse(changed["complete"])

    def test_user_confirmation_closes_delivery_without_inventing_measured_evidence(self):
        case = self.make_case("new-case", repeats=1)
        path = next(case.glob("accept-v0-*.json"))
        rows = json.loads(path.read_text())
        rows[0]["verdicts"] = []
        self.write(path, rows)
        before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in case.glob("accept-*.json")}
        measured = summary.expert("new-case", "new", "领域", "1.1")
        self.user_accept("new-case")
        confirmed = summary.expert("new-case", "new", "领域", "1.1")
        self.assertTrue(confirmed["user_accepted"] and confirmed["complete"])
        self.assertFalse(confirmed["accepted"])
        self.assertEqual(confirmed["metrics"], measured["metrics"])
        self.assertEqual(confirmed["admitted"], measured["admitted"])
        self.assertEqual(confirmed["excluded"], measured["excluded"])
        self.assertEqual(summary.changes([confirmed]), [])
        self.assertEqual({p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before}, before)
        text = summary.render([confirmed], "snapshot")
        self.assertIn("验收收尾与实测记录", text)
        self.assertIn("用户确认验收 1 个", text)
        self.assertIn("具备原计划三版本实测报告的专家 0 个", text)
        self.assertIn("| 已确认 | 1/0/1 |", text)
        self.assertIn("缺少逐项 LLM verdict", text)
        self.assertIn("历史复测计划已结束", text)
        for phrase in ("目标各N", "待齐", "未齐", "暂 全对", "临时成绩总表"):
            self.assertNotIn(phrase, text)

    def test_user_confirmation_is_bound_to_current_export_revision(self):
        self.make_case("new-case", repeats=0)
        self.user_accept("new-case", "different123")
        stale = summary.expert("new-case", "new", "领域", "1.1")
        self.assertFalse(stale["user_accepted"] or stale["complete"])
        self.user_accept("new-case")
        current = summary.expert("new-case", "new", "领域", "1.1")
        self.assertTrue(current["user_accepted"] and current["complete"])
        self.assertFalse(current["accepted"])
        text = summary.render([current], "snapshot")
        self.assertIn("| 已确认 | 0/0/0 |", text)
        self.assertIn("无有效完整报告", text)
        self.assertNotIn("通道待齐", text)

    def test_user_accepted_case_cannot_enter_historical_phase_comparisons(self):
        self.make_case("store-ticket")
        self.make_case("new-case")
        old = summary.expert("store-ticket", "old", "领域", "1.1")
        new = summary.expert("new-case", "new", "领域", "1.2")
        before = summary.changes([old, new])
        self.user_accept("new-case")
        confirmed = summary.expert("new-case", "new", "领域", "1.2")
        self.assertTrue(confirmed["complete"])
        self.assertEqual(summary.changes([old, confirmed]), before)
        self.assertTrue(all(group["eligible"] == 1 and group["not_ready"] == 1 for group in before))

    def test_phase_groups_compare_rates_and_keep_mixed_routes_descriptive(self):
        self.make_case("store-ticket")
        e = summary.expert("store-ticket", "old", "领域", "3.1")
        e["metrics"]["plain"]["same_ok"] = [1, 10]
        e["metrics"]["v0"]["same_ok"] = [3, 30]  # More successes, identical rate.
        e["metrics"]["trained"]["same_ok"] = [2, 10]
        e["metrics"]["trained"]["new_ok"] = [9, 10]
        e["admitted"]["trained"][0][1][0]["transport"] = {
            "provider": "custom gateway", "model": "glm-5.3-flash", "client_alias": "z-ai/glm-5.3-flash"}
        grouped = summary.changes([e])
        first = next(g for g in grouped if g["phase"] == "plain→v0" and g["group"] == "same")
        self.assertEqual(first["equal"], ["store-ticket"])
        second = next(g for g in grouped if g["phase"] == "v0→trained" and g["group"] == "same")
        self.assertEqual(second["improved"], ["store-ticket"])
        self.assertEqual(second["route"], "混合通道")
        lower = next(g for g in grouped if g["phase"] == "v0→trained" and g["group"] == "new")
        self.assertEqual(lower["regressed"], ["store-ticket"])
        self.assertIn("描述性观察", summary.render([e], "snapshot"))


if __name__ == "__main__":
    unittest.main()
