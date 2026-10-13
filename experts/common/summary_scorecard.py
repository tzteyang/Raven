"""Read-only 22-expert progress and descriptive acceptance summary.

From the repository root:
  uv run python experts/common/summary_scorecard.py --output experts/reports/summary-current.md

No models/processes are invoked. The only optional write is the generated report.
"""

import argparse
import json
import re
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path

from domains import DOMAINS
from scorecard import reports_of, tally, route_summary, route_context, route_table, frac

REPOSITORY = Path(__file__).resolve().parents[2]
GTM = REPOSITORY.parent  # the workspace that holds runs/ beside the checkout
CASES = REPOSITORY / "experts/cases"
VERSIONS = ("plain", "v0", "trained")
LABELS = {"plain": "原版", "v0": "初始配置", "trained": "训练后"}
# Historical evidence thresholds, retained for comparisons after user acceptance closes the plan.
HISTORICAL_REPEATS = {"refund-desk": 3, "complaint-desk": 3, "poster-review": 3,
                      "compete-table": 3, "store-ticket": 1}


def read_json(path: Path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def lifecycle(case: Path, harness: dict) -> dict:
    """Use current-session training evidence and exported payload, never control.complete."""
    live = read_json(case / "live.json", {})
    session_file, log_file = case / "session.txt", case / "run.out"
    session = session_file.read_text().strip() if session_file.exists() else None
    deployment_path = ((case / live["root"] / "runs" / session / "deployment.json").resolve()
                       if live.get("root") and session else None)
    deployment = read_json(deployment_path, {}) if deployment_path else {}
    log = log_file.read_text(errors="replace") if log_file.exists() else ""
    last = log.strip().splitlines()[-1] if log.strip() else ""
    exams = re.findall(r"exam done[^\n]*revision=([a-zA-Z0-9_-]+)\s+exam=", log)
    current_revision = deployment.get("revision")
    trained = bool(session and current_revision and last.endswith("ALL ROUNDS DONE")
                   and exams and exams[-1] == current_revision[:12])
    source = harness.get("source", {})
    folder = GTM / "runs/experts/host/agents" / f"expert-{case.name}"
    registration = read_json(folder / "subagent.json", {})
    exported = bool(deployment and harness and source.get("case") == case.name
                    and source.get("session") == session
                    and source.get("deployment_sha256") == deployment.get("sha256")
                    and all(harness.get(k) == deployment.get(k) for k in ("revision", "artifact", "state", "task"))
                    and (folder / "run.py").is_file()
                    and registration.get("kind") == "acp" and registration.get("enabled") is True)
    return {"trained": trained, "exported": exported, "session": session,
            "deployment": deployment_path, "log": log_file,
            "training_note": "当前日志以训练完成结束，末次考试revision与当前deployment一致" if trained else "缺少当前会话完成证据或末次revision不符",
            "export_note": "导出payload与当前deployment一致，ACP入口已启用" if exported else "导出缺失或与当前deployment/ACP入口不一致"}


def expert(case_id: str, fallback: str, domain: str, number: str) -> dict:
    case = CASES / case_id
    manifest = read_json(case / "manifest.json", {})
    harness_path = GTM / "runs/experts/host/agents" / f"expert-{case_id}" / "harness.json"
    harness = read_json(harness_path, {})
    revision = harness.get("revision")
    required = HISTORICAL_REPEATS.get(case_id, 3)
    admitted, excluded, metrics = {}, {}, {}
    for version, tag in (("plain", "plain"), ("v0", "v0"), ("trained", revision[:12] if revision else None)):
        if tag and (case / "questions.json").exists() and (case / "live.json").exists():
            good, bad = reports_of(case, tag)
        else:
            good, bad = [], []
        admitted[version], excluded[version] = good, bad
        metrics[version] = tally([row for _, rows in good for row in rows])
    state = lifecycle(case, harness)
    accepted = all(len(admitted[v]) >= required for v in VERSIONS)
    control_path = GTM / "runs/experts/control" / f"{case_id}.json"
    control = read_json(control_path, {})
    user_accepted = bool(control.get("stage") == "complete" and control.get("acceptance_source") == "user"
                         and control.get("acceptance_decision") and revision
                         and control.get("revision") == revision[:12])
    return {"id": case_id, "name": manifest.get("name", fallback), "domain": domain, "number": number,
            "required": required, "harness": harness_path, "revision": revision,
            "admitted": admitted, "excluded": excluded, "metrics": metrics, "accepted": accepted,
            "user_accepted": user_accepted, "acceptance_record": control_path,
            "acceptance_decision": control.get("acceptance_decision"), "acceptance_at": control.get("acceptance_at"),
            "routing": route_summary(admitted),
            "complete": state["trained"] and state["exported"] and (accepted or user_accepted),
            **state}


def collect() -> list[dict]:
    return [expert(case_id, fallback, domain, f"{d}.{n}")
            for d, (domain, cases) in enumerate(DOMAINS, 1)
            for n, (case_id, fallback) in enumerate(cases, 1)]


def outcome(metrics: dict, group: str) -> Fraction:
    keys = ("same_ok", "new_ok") if group == "combined" else (group + "_ok",)
    return Fraction(sum(metrics[k][0] for k in keys), sum(metrics[k][1] for k in keys))


def changes(experts: list[dict]) -> list[dict]:
    """Historical evidence only: user acceptance never admits an unmeasured comparison."""
    out = []
    for start, end in (("plain", "v0"), ("v0", "trained")):
        eligible = [e for e in experts if e["trained"] and e["exported"]
                    and all(len(e["admitted"][v]) >= e["required"] for v in (start, end))]
        for group in ("same", "new", "combined"):
            by_route = {}
            for e in eligible:
                routing = route_summary({v: e["admitted"][v] for v in (start, end)})
                bucket = by_route.setdefault(routing["label"], {"improved": [], "equal": [], "regressed": []})
                delta = outcome(e["metrics"][end], group) - outcome(e["metrics"][start], group)
                bucket["improved" if delta > 0 else "regressed" if delta < 0 else "equal"].append(e["id"])
            for route, bucket in by_route.items():
                out.append({"phase": f"{start}→{end}", "group": group, "route": route,
                            "eligible": sum(len(v) for v in bucket.values()),
                            "not_ready": len(experts) - len(eligible), **bucket})
    return out


def result_cell(item: dict, version: str) -> str:
    count = len(item["admitted"][version])
    if not count:
        return "无有效完整报告"
    stats = item["metrics"][version]
    return (f"全对 {frac(stats['same_ok'])} / {frac(stats['new_ok'])}<br>"
            f"挂项 {frac(stats['same'])} / {frac(stats['new'])}")


def render(experts: list[dict], generated: str) -> str:
    n = len(experts)
    done = sum(e["complete"] for e in experts)
    user_count = sum(e["user_accepted"] for e in experts)
    title = ("验收收尾与实测记录" if user_count else
             "最终成绩总表" if done == n and n else "临时成绩总表（未完成）")
    reports = sum(len(e["admitted"][v]) for e in experts for v in VERSIONS)
    lines = [f"# Raven 专家：{title}", "", f"生成时间：{generated}。",
             f"共 {n} 个专家；用户确认验收 {user_count} 个，训练证据完整 {sum(e['trained'] for e in experts)} 个，"
             f"导出核对通过 {sum(e['exported'] for e in experts)} 个，收尾完成 {done} 个。",
             f"已保存有效完整实测报告 {reports} 份；具备原计划三版本实测报告的专家 {sum(e['accepted'] for e in experts)} 个。", "",
             ("用户确认以各专家的 acceptance_source=user、确认原文和当前导出revision绑定记录为依据。"
              "该确认不代表所有模型评审项通过；历史复测计划已结束，未满足原计划次数的部分不再执行。"
              if user_count else "未记录用户确认；实测完成状态仍依据已保存的完整模型判定。"), "",
             "实测只计 reports_of 严格核验后的完整20题和逐项LLM判定，用户确认及 control.complete 不增加实测报告或更改分数。"
             "训练状态依据当前日志末次完成标记与deployment revision；导出再核对payload、来源会话和ACP入口。", "",
             "每个结果格按“同规则x / 新规则y”排列：全对=整题全对/有效答卷，挂项=失败criterion/适用criterion。"
             "同一组x/y各10题被重复使用，30份答卷不是30道新题。"
             "混合run仍只算一次完整验收，路由分层见各专家证据。", "",
             "额度事故使13个专家进入109题恢复，后续派活改用新通道；相同宣称模型名不证明provider等价。"
             "下表及分组统计都是描述性观察，特别是混合路由不能解释为纯训练因果增益；9个原已完成专家保留旧通道结果。", "",
             "| 领域 | 专家 | 训练 | 导出 | 用户确认验收 | 已保存实测 P/V/T报告数 | plain：全对/挂项 x / y | v0：全对/挂项 x / y | trained：全对/挂项 x / y | 路由 | 证据 |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for e in experts:
        counts = "/".join(str(len(e["admitted"][v])) for v in VERSIONS)
        lines.append(f"| {e['domain']} | {e['number']} {e['name']} | {'完整' if e['trained'] else '待核'} | "
                     f"{'完整' if e['exported'] else '待核'} | {'已确认' if e['user_accepted'] else '未记录'} | {counts} | "
                     + " | ".join(result_cell(e, v) for v in VERSIONS)
                     + f" | {'无完整有效报告' if e['routing']['state'] == 'pending' else e['routing']['label']} | [记录](#evidence-{e['id']}) |")
    lines += ["", "## 描述性变化：统计对象是专家", "",
              "按整题全对率（不是挂项数）分改善/持平/退步；使用精确分数比较。每一阶段只纳入两端版本满足历史实测条件、且训练/导出已核实的专家。"
              "历史条件为门店客单价每版本1份有效完整报告、其余每版本3份；这只是保留原统计口径，用户确认不作为实测证据。"
              "联合组汇总该专家x+y的20题，不把专家变成题目计数；x、y、联合三行不能相加。各阶段按实际参与版本的通道构成继续分层。", "",
              "| 阶段 | 题组 | 通道层 | 本层专家数 | 改善 | 持平 | 退步 | 本阶段未纳入专家数 |",
              "|---|---|---|---:|---:|---:|---:|---:|"]
    grouped = changes(experts)
    for g in grouped:
        group_name = {"same": "x 同规则", "new": "y 新规则", "combined": "x+y 联合"}[g["group"]]
        lines.append(f"| {g['phase']} | {group_name} | {g['route']} | {g['eligible']} | {len(g['improved'])} | "
                     f"{len(g['equal'])} | {len(g['regressed'])} | {g['not_ready']} |")
    if not grouped:
        lines.append("| 无满足历史对照条件的专家 | — | — | 0 | — | — | — | " + str(n) + " |")
    names = {e["id"]: e["name"] for e in experts}
    lines += ["", "同一阶段未纳入数在通道层之间重复展示，不跨行累加；仅说明实测证据范围，不产生后续任务。分组名单：", ""]
    for g in grouped:
        if g["group"] != "combined":
            continue
        pieces = [f"{label}：" + ("、".join(f"[{names[i]}](#evidence-{i})" for i in g[key]) or "无")
                  for key, label in (("improved", "改善"), ("equal", "持平"), ("regressed", "退步"))]
        lines.append(f"- {g['phase']} · 联合 · {g['route']}：" + "；".join(pieces) + "。")
    lines += ["", "## 逐专家证据与排除明细", "",
              "原始报告链接保留答卷、逐项LLM判定和transport元数据；不合格报告列出具体原因，不静默丢弃。"
              "本总表不读数百MB的完整Studio迭代轨迹；逐轮source/unknown轨迹仍可用 scorecard.py 单专家输出。"]
    for e in experts:
        lines += ["", f"<a id=\"evidence-{e['id']}\"></a>", f"### {e['number']} {e['name']}", "",
                  f"训练：{e['training_note']}；[run.out]({e['log']})。",
                  f"导出：{e['export_note']}；[harness]({e['harness']})" +
                  (f"；[deployment]({e['deployment']})。" if e["deployment"] else "。"),
                  f"完整revision：`{e['revision'] or '未导出'}`。",
                  (f"用户确认验收：{e['acceptance_decision']}；时间 {e['acceptance_at'] or '未记录'}；"
                   f"[确认记录]({e['acceptance_record']})。" if e["user_accepted"] else "用户确认验收：未记录与当前导出版本绑定的确认。"),
                  f"[v0与训练后策略正文对照]({REPOSITORY / 'experts/reports/learned-artifacts-20261011.md'}#{e['id']})。",
                  *(route_context(CASES / e["id"], e["routing"]) if e["routing"]["state"] != "pending"
                    else ["员工通道：无完整有效报告可供统计。"]), ""]
        for version in VERSIONS:
            good, bad = e["admitted"][version], e["excluded"][version]
            lines.append(f"- {LABELS[version]}：已保存 {len(good)} 份有效完整报告；排除 {len(bad)} 份。")
            lines += [f"  - [有效 {i} · {p.name}]({p})" for i, (p, _) in enumerate(good, 1)]
            lines += [f"  - [未纳入 · {p.name}]({p})：" + "；".join(issues) for p, issues in bad]
        lines += route_table(e["routing"])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="write the generated Markdown report instead of stdout")
    args = parser.parse_args()
    experts = collect()
    text = render(experts, datetime.now(timezone.utc).isoformat())
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
        print(f"Summary: {sum(e['user_accepted'] for e in experts)}/{len(experts)} user-accepted; "
              f"{sum(e['accepted'] for e in experts)} with historical three-version evidence -> {args.output.resolve()}")
    else:
        print(text)


if __name__ == "__main__":
    main()
