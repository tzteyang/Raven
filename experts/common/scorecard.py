"""成绩单：每个案例的考试和验收结果排在一起，写成 Markdown。

  uv run python experts/common/scorecard.py [--records] <案例名>… > 成绩单.md

--records：读仓库里随案例保存的验收记录（cases/<案例>/records/）和 experts/agents/ 里验收过的专家，
不读本机 runs/experts 下的运行结果。

每个案例三行验收（宿主 Raven 按 ACP 派活、同一个评审判同 20 道考试题：x 同规则 10 道、y 新规则 10 道）：
plain（没培养过的 plain Raven）、v0（Studio 入职改造后、第一轮培养前）、培养后（导出到宿主的那一版）；
只汇总保存的模型判定；完整20题且无派活/证据错误的报告才进入能力表，异常记录另列。
重复使用同一套20题，不是新增独立样本。Studio轨迹按评审来源分组；例题包括固定题、改善和退步。
员工通道按答卷transport分层；混合通道运行仍只算一次完整验收，不解释为纯训练因果增益。
"""

import json
import re
import sys
from collections import Counter
from functools import lru_cache
from html import escape
from pathlib import Path

HERE = Path(__file__).resolve().parent
CASES = HERE.parent / "cases"
REPOSITORY = HERE.parents[1]
GTM = REPOSITORY.parent  # the workspace that holds runs/ beside the checkout


GROUPS = ("same", "new")


def verdict_problem(row, criteria=None) -> str | None:
    """Validate model evidence/summary shape only; do not decide correctness."""
    if not isinstance(row, dict) or row.get("group") not in GROUPS:
        return "题组缺失或无效"
    verdicts = row.get("verdicts")
    if not isinstance(verdicts, list) or not verdicts:
        return "缺少逐项 LLM verdict"
    ids, failed, judged = [], [], []
    for v in verdicts:
        if not isinstance(v, dict) or not isinstance(v.get("id"), str) or not v["id"]:
            return "verdict id 无效"
        ids.append(v["id"])
        count, errors = v.get("count"), v.get("errors")
        if (type(v.get("applicable")) is not bool or type(count) is not int or count < 0
                or not isinstance(errors, list) or count != len(errors)
                or (not v["applicable"] and count)
                or not isinstance(v.get("reason"), str) or not v["reason"].strip()
                or v.get("result") == "unknown"):
            return f"{v['id']}: verdict 待核或结构不完整"
        if any(not isinstance(e, dict) or any(not isinstance(e.get(k), str) or not e[k].strip()
                                             for k in ("quote", "problem")) for e in errors):
            return f"{v['id']}: 缺少模型错误引文或理由"
        if v["applicable"]:
            judged.append(v["id"])
            if count:
                failed.append(v["id"])
    if len(set(ids)) != len(ids) or (criteria is not None and set(ids) != {c["id"] for c in criteria}):
        return "LLM verdict 未恰好覆盖每项 criterion 一次"
    for key, expected in (("failed", failed), ("judged", judged)):
        if (not isinstance(row.get(key), list) or any(not isinstance(v, str) for v in row[key])
                or sorted(row[key]) != sorted(expected)):
            return f"{key} 与保存的 LLM verdict 不一致"
    return None


def report_issues(rows, questions: list[dict], criteria: list[dict]) -> list[str]:
    """Pure admission check: [] means a full report without dispatch/evidence errors.

    Unknowns and dispatch failures remain in the audit, not the performance sample.
    This checks evidence completeness, never the correctness of an answer.
    """
    wanted = {q["name"]: q["group"] for q in questions if q["group"] in GROUPS}
    if len(wanted) != 20 or any(list(wanted.values()).count(g) != 10 for g in GROUPS):
        return ["unknown: 题库不是同规则/新规则各 10 道"]
    if len({c["id"] for c in criteria}) != len(criteria) or not criteria:
        return ["unknown: criteria 缺失或重复"]
    if not isinstance(rows, list):
        return ["unknown: 报告不是答卷列表"]
    names = [r.get("name") for r in rows if isinstance(r, dict)]
    issues = []
    if len(rows) != 20 or any(not isinstance(n, str) for n in names) or sorted(n for n in names if isinstance(n, str)) != sorted(wanted):
        issues.append("unknown: 未恰好覆盖既定 20 题（缺失、重复或多出题号）")
    for row in rows:
        name = row.get("name", "?") if isinstance(row, dict) else "?"
        problem = verdict_problem(row, criteria)
        if problem:
            issues.append(f"unknown: {name}: {problem}")
        if not isinstance(row, dict):
            continue
        if not isinstance(name, str) or wanted.get(name) != row.get("group"):
            issues.append(f"unknown: {name}: 题组与题库不一致")
        if row.get("error"):
            issues.append(f"error: {name}: {row['error']}")
        if row.get("loose"):
            issues.append(f"unknown: {name}: LLM 引用在产出中找不到（loose）")
        if not problem and not row["judged"]:
            issues.append(f"not_applicable: {name}: 无适用判定，不能记为整题全对")
        if not isinstance(row.get("product"), str):
            issues.append(f"unknown: {name}: 缺少答卷原文")
    return issues


def case_spec(case: Path) -> tuple[list[dict], list[dict]]:
    live = json.loads((case / "live.json").read_text())
    return (json.loads((case / "questions.json").read_text()),
            json.loads((case / live["scenario"] / "scenario.json").read_text())["criteria"])


def tally(rows: list[dict]) -> dict:
    """Evidenced answers only; the original four keys remain catalog-compatible."""
    out = {key: [0, 0] for key in ("same", "new", "same_ok", "new_ok")}
    out.update({f"{g}_{kind}": 0 for g in GROUPS for kind in ("error", "unknown", "not_applicable", "loose")})
    out["unassigned_unknown"] = 0
    for row in rows:
        if not isinstance(row, dict) or row.get("group") not in GROUPS:
            out["unassigned_unknown"] += 1
            continue
        group = row["group"]
        if row.get("error"):
            out[group + "_error"] += 1
            continue
        if verdict_problem(row) or row.get("loose"):
            out[group + "_unknown"] += 1
            out[group + "_loose"] += bool(row.get("loose"))
            continue
        out[group + "_not_applicable"] += sum(not v["applicable"] for v in row["verdicts"])
        if not row["judged"]:
            continue
        out[group][0] += len(row["failed"])
        out[group][1] += len(row["judged"])
        out[group + "_ok"][0] += not row["failed"]
        out[group + "_ok"][1] += 1
    return out


def reports_of(case: Path, tag: str, folder: Path | None = None):
    """Return (admitted [(path, rows)], excluded [(path, issues)]), from `folder` (default: the case directory)."""
    questions, criteria = case_spec(case)
    admitted, excluded = [], []
    for path in sorted((folder or case).glob(f"accept-{tag}-*.json")):
        try:
            rows = json.loads(path.read_text())
            issues = report_issues(rows, questions, criteria)
        except (ValueError, OSError) as exc:
            issues = [f"unknown: 无法读报告：{exc}"]
        if issues:
            excluded.append((path, issues))
        else:
            admitted.append((path, rows))
    return admitted, excluded


def runs_of(case: Path, tag: str) -> list[list[dict]]:
    return [rows for _, rows in reports_of(case, tag)[0]]


@lru_cache(maxsize=64)
def _studio_record(path: Path, mtime_ns: int, size: int) -> tuple[dict, ...]:
    """Cache only extracted counts; mtime/size key versions of potentially huge JSON."""
    record = json.loads(path.read_text())
    out = []
    parts = [(f"rounds[{i}]", part) for i, part in enumerate(record.get("rounds", []))]
    parts.append(("pending", record.get("pending")))
    for position, part in parts:
        if not part:
            continue
        counts = {}
        for signal in part.get("holdout_signals", []):
            source = signal.get("source", "未记录")
            for item in signal.get("items", []):
                name = item.get("session") or str(item.get("id", "")).rsplit(":", 1)[-1]
                group = "x" if re.fullmatch(r"x\d+", name) else "y" if re.fullmatch(r"y\d+", name) else "未定位"
                count = counts.setdefault((source, group), Counter())
                result = item.get("result")
                count[result if result in ("pass", "fail", "unknown", "not_applicable") else "unknown"] += 1
        out.extend({"file": path, "position": position, "source": source,
                    "group": group, **{k: count[k] for k in ("pass", "fail", "unknown", "not_applicable")}}
                   for (source, group), count in sorted(counts.items()))
    return tuple(out)


def studio_exams(case: Path) -> list[dict]:
    """Current session counts; unchanged records use a bounded metadata-keyed cache."""
    session_file = case / "session.txt"
    if not session_file.exists():
        return []
    live = json.loads((case / "live.json").read_text())
    session = session_file.read_text().strip()
    root = (case / live["root"] / "runs" / session / "iteration").resolve()
    out = []
    for path in sorted(root.glob("*.json")):
        stat = path.stat()
        # Copy the small rows so consumers cannot mutate a later cache hit.
        out.extend({**row, "session": session} for row in _studio_record(path, stat.st_mtime_ns, stat.st_size))
    return out


def learned(case: Path, agents: Path = GTM / "runs" / "experts" / "host" / "agents") -> list[str]:
    folder = agents / f"expert-{case.name}"
    if not (folder / "harness.json").exists():
        return []
    artifact = json.loads((folder / "harness.json").read_text())["artifact"]
    files = artifact.get("files", {})
    out = []
    for path, text in files.items():
        if path.endswith("SKILL.md"):
            name = re.search(r"^name:\s*(.+)$", text, re.M)
            desc = re.search(r"^description:\s*(.+)$", text, re.M)
            out.append(f"技能 `{name.group(1) if name else path}`：{desc.group(1) if desc else ''}（{len(text)} 字）")
        else:
            out.append(f"策略文件 `{path}`（{len(text)} 字）")
    out += [f"策略项 `{key}`" for key in artifact.get("values", {})]
    return out


def examples(plain: list[dict], trained: list[dict]) -> list[tuple[str, str]]:
    """Fixed x01 plus first improvement/regression by id, regardless of magnitude."""
    before = {r["name"]: r for r in plain if not verdict_problem(r) and not r.get("error") and not r.get("loose") and r["judged"]}
    after = {r["name"]: r for r in trained if not verdict_problem(r) and not r.get("error") and not r.get("loose") and r["judged"]}
    names = sorted(before.keys() & after.keys())
    selected = {}
    if "x01" in names:
        selected["x01"] = ["固定题 x01"]
    for label, sign in (("改善例（按题号第一处）", 1), ("退步例（按题号第一处）", -1)):
        name = next((n for n in names if sign * (len(before[n]["failed"]) - len(after[n]["failed"])) > 0), None)
        if name:
            selected.setdefault(name, []).append(label)
    return [(name, "；".join(labels)) for name, labels in selected.items()]


def frac(value: list[int]) -> str:
    return f"{value[0]}/{value[1]}" if value[1] else "—"


def cell(tallies, key):
    values = [t[key] for t in tallies]
    total = [sum(v[i] for v in values) for i in (0, 1)]
    return f"{frac(total)}（每次 {', '.join(frac(v) for v in values)}）"


def row_transport(row: dict) -> dict:
    """Absent metadata is the documented legacy route, never the current default."""
    if "transport" not in row:
        return {"provider": "OpenRouter", "model": "z-ai/glm-5.3-flash",
                "client_alias": "z-ai/glm-5.3-flash", "kind": "legacy", "implicit_legacy": True}
    transport = row["transport"]
    if not isinstance(transport, dict) or any(not isinstance(transport.get(k), str) or not transport[k].strip()
                                              for k in ("provider", "model")):
        return {"provider": "未记录", "model": "未记录", "client_alias": "未记录",
                "kind": "unknown", "implicit_legacy": False}
    alias = transport.get("client_alias") or transport["model"]
    return {"provider": transport["provider"], "model": transport["model"],
            "client_alias": alias if isinstance(alias, str) else "未记录",
            "kind": "legacy" if transport["provider"].casefold() == "openrouter" else "new",
            "implicit_legacy": False}


def _route_key(transport: dict) -> tuple[str, str, str]:
    return tuple(transport[k] for k in ("provider", "model", "client_alias"))


def route_summary(reports_by_version: dict[str, list[tuple[Path, list[dict]]]]) -> dict:
    """Describe admitted reports by answer route, preserving whole-run counts.

    Caller supplies complete reports from reports_of. Different since/reason
    timestamps do not create a route; provider/model/client_alias identify it.
    Counts are descriptive and neither choose reruns nor imply causal effects.
    """
    routes, layers, reports = {}, {}, []
    for version, found in reports_by_version.items():
        for path, rows in found:
            run_routes = Counter()
            for row in rows:
                if verdict_problem(row) or row.get("error") or row.get("loose") or not row["judged"]:
                    continue
                transport = row_transport(row)
                key = _route_key(transport)
                route = routes.setdefault(key, {**transport, "id": f"R{len(routes) + 1}", "answers": 0,
                                                "implicit_legacy_answers": 0})
                route["answers"] += 1
                route["implicit_legacy_answers"] += transport["implicit_legacy"]
                run_routes[route["id"]] += 1
                layer = layers.setdefault((route["id"], version, row["group"]), {
                    "route": route["id"], "version": version, "group": row["group"], "answers": 0,
                    "fully_correct": 0, "failed": 0, "judged": 0, "question_names": set(), "report_paths": set()})
                layer["answers"] += 1
                layer["fully_correct"] += not row["failed"]
                layer["failed"] += len(row["failed"])
                layer["judged"] += len(row["judged"])
                layer["question_names"].add(row["name"])
                layer["report_paths"].add(str(path))
            reports.append({"version": version, "path": str(path), "routes": dict(run_routes),
                            "mixed": len(run_routes) > 1})
    values = list(routes.values())
    if not values:
        state, label = "pending", "尚无完整有效验收，通道待齐"
    elif any(route["kind"] == "unknown" for route in values):
        state, label = "unknown", "含通道未记录的答卷"
    elif len(values) > 1:
        state, label = "mixed", "混合通道"
    elif values[0]["kind"] == "legacy":
        state, label = "legacy", "纯旧通道（OpenRouter）"
    else:
        state, label = "new", "纯新通道"
    strata = []
    for layer in layers.values():
        strata.append({**layer, "question_names": sorted(layer["question_names"]),
                       "distinct_questions": len(layer["question_names"]),
                       "report_paths": sorted(layer["report_paths"]), "source_reports": len(layer["report_paths"])})
    return {"state": state, "label": label, "routes": values, "strata": strata, "reports": reports,
            "complete_reports": len(reports), "mixed_reports": sum(r["mixed"] for r in reports)}


def route_context(case: Path, summary: dict) -> list[str]:
    """Explain observed routing and this case's recovery without reading configs."""
    lines = [f"员工通道：**{summary['label']}**（以当前完整有效报告中的答卷为准）。"]
    recovery_file = REPOSITORY / "experts/reports/quota-recovery-executed.json"
    if recovery_file.exists():
        recovery = json.loads(recovery_file.read_text())
        changes = [change for change in recovery.get("changes", []) if change.get("case") == case.name]
        if changes:
            count = sum(len(change.get("questions", [])) for change in changes)
            lines += [f"本专家进入额度事故恢复：{len(changes)} 次运行的 {count} 道派活纳入重做清单；全批共 {recovery.get('questions', '未记录')} 道。"
                      f"清单不按分数选择，原答卷与模型判定留档，正常条目保持不变。见[执行记录]({recovery_file})。",
                      "恢复后的后续派活改经兼容适配器与排队网关。原通道为 OpenRouter / z-ai/glm-5.3-flash；"
                      "新通道为 custom gateway / glm-5.3-flash，客户端仍使用 z-ai/glm-5.3-flash 别名。"
                      "只验证了相同宣称模型名及SSE/工具协议，未独立验证两个provider等价。"
                      "因此本专家的版本比较是描述性结果，不能把通道变化后的差异归为纯训练因果增益。"]
        elif summary["state"] == "legacy":
            lines += ["本专家未列入这次109题恢复清单，保留既有旧通道验收；没有因事故重跑。"]
    if summary["state"] in ("new", "mixed", "unknown"):
        lines += ["主表合并结果只作描述；不同provider或通道未明时，不能当作同条件训练对照。"
                  "下方按路由分层仍是不同题号/运行构成的观察子样本，不单独证明因果增益。"]
    return lines


def route_table(summary: dict) -> list[str]:
    lines = ["", "员工路由分层（与判卷模型无关）：", "",
             "缺少 transport 字段的旧正常答卷依据实验历史归为 legacy OpenRouter；显式但不完整的元数据归为未记录。"
             "不根据当前默认provider反推历史。", ""]
    for route in summary["routes"]:
        lines.append(f"- {route['id']}：provider=`{route['provider']}`；model=`{route['model']}`；"
                     f"client_alias=`{route['client_alias']}`；有效答卷 {route['answers']} 次"
                     f"（其中 {route['implicit_legacy_answers']} 次无逐行通道字段，按旧记录归组）。")
    lines += ["", f"原完整运行共 {summary['complete_reports']} 次，其中 {summary['mixed_reports']} 次内部混合通道。"
              "混合运行仍只计一次完整20题验收；以下是答卷层样本数，覆盖运行数不能跨路由相加成新实验。", "",
              "| 路由 | 版本 | 题组 | 有效答卷次数 | 不同题号数 | 全对 / 有效答卷 | 失败项 / 适用项 | 覆盖原运行数 |",
              "|---|---|---|---:|---:|---|---|---:|"]
    for s in summary["strata"]:
        lines.append(f"| {s['route']} | {s['version']} | {'x 同规则' if s['group'] == 'same' else 'y 新规则'} | "
                     f"{s['answers']} | {s['distinct_questions']} | {s['fully_correct']}/{s['answers']} | "
                     f"{s['failed']}/{s['judged']} | {s['source_reports']} |")
    if summary["mixed_reports"]:
        lines += ["", "混合运行的答卷构成（不增加完整运行次数）：", ""]
        for report in summary["reports"]:
            if report["mixed"]:
                counts = "、".join(f"{r}={n}题" for r, n in report["routes"].items())
                lines.append(f"- {report['version']} [{Path(report['path']).name}]({report['path']})：{counts}。")
    return lines


def card(name: str, records: bool = False) -> str:
    """One case's card; with `records`, from the reports kept beside the case (cases/<case>/records/) and the accepted
    agent in experts/agents/, instead of this machine's runs/experts."""
    case = CASES / name
    manifest = json.loads((case / "manifest.json").read_text())
    agents = HERE.parent / "agents" if records else GTM / "runs" / "experts" / "host" / "agents"
    folder = case / "records" if records else None
    harness = agents / f"expert-{name}" / "harness.json"
    revision = json.loads(harness.read_text())["revision"] if harness.exists() else None
    versions = {label: reports_of(case, tag, folder) if tag else ([], [])
                for label, tag in (("plain", "plain"), ("v0", "v0"), ("培养后", revision[:12] if revision else None))}
    complete = all(admitted for admitted, _ in versions.values())
    routing = route_summary({label: admitted for label, (admitted, _) in versions.items()})
    lines = [f"## {manifest['name']}（{name}）", "", *route_context(case, routing), "",
             f"三版本对照：{'完整' if complete else '待齐'}；培养后 revision：`{revision or '未导出'}`。",
             "每次重复使用同一组 x/y 各 10 题，合计答卷数不代表独立新题。仅完整、逐项 LLM 评审齐全且无派活/证据错误的报告进入能力表。",
             "", "| 版本 | 完整有效 / 发现报告 | 全对题 x（合计、每次） | 全对题 y（合计、每次） | 挂项 x（合计、每次） | 挂项 y（合计、每次） |",
             "|---|---|---|---|---|---|"]
    for label, (admitted, excluded) in versions.items():
        ts = [tally(rows) for _, rows in admitted]
        cells = " | ".join(cell(ts, key) if ts else "—" for key in ("same_ok", "new_ok", "same", "new"))
        lines.append(f"| {label} | {len(admitted)} / {len(admitted) + len(excluded)} | {cells} |")
    lines += route_table(routing)
    lines += ["", "异常记录单列（未纳入能力表，也未被程序判成规则失败）：", "",
              "| 版本 | unknown 待核报告 | 派活 error 报告 | 无适用判定报告 |", "|---|---|---|---|"]
    for label, (_, excluded) in versions.items():
        counts = [sum(any(issue.startswith(prefix + ":") for issue in issues) for _, issues in excluded)
                  for prefix in ("unknown", "error", "not_applicable")]
        lines.append(f"| {label} | {' | '.join(map(str, counts))} |")
    lines += ["", "同一报告可能同时含 error 与 unknown；上表不是互斥报告数。原始报告：", ""]
    for label, (admitted, excluded) in versions.items():
        lines += [f"- {label}：[第 {i} 次]({path})" for i, (path, _) in enumerate(admitted, 1)]
        lines += [f"- {label} 未纳入：[{path.name}]({path})；" + "；".join(issues) for path, issues in excluded]
    exams = studio_exams(case)
    lines += ["", "Studio 原 run.out 的 exam 分母会随评审来源、适用项和 unknown 变化，不能当作固定工作规则指标；以下读取当前 session 的 iteration，按 source 和题组分开。位置是记录中的 JSON 路径，不推断补考或额外轮的含义。"]
    if exams:
        lines += [f"当前 session：`{exams[0]['session']}`。", "", "| 记录位置 | 评审 source | 题组 | pass | fail | unknown | not_applicable |", "|---|---|---|---|---|---|---|"]
        for exam in exams:
            lines.append(f"| [{exam['position']}]({exam['file']}) | {exam['source']} | {exam['group']} | "
                         + " | ".join(str(exam[k]) for k in ("pass", "fail", "unknown", "not_applicable")) + " |")
    else:
        lines += ["当前没有可读的逐项 Studio 考试记录；不以日志中的失败/已判数字替代。"]
    skills = learned(case, agents)
    if skills:
        lines += ["", "导出的策略产物（文件存在不等于已证明学会；效果还需对照v0、plain及通道条件，跨通道结果仅作描述）：", ""] + [f"- {s}" for s in skills]
    if versions["plain"][0] and versions["培养后"][0]:
        first = {label: admitted[0] for label, (admitted, _) in versions.items() if admitted}
        selected = examples(first["plain"][1], first["培养后"][1])
        lines += ["", "例题取各版本第一次完整有效验收；固定 x01，并补题号最先的观察改善/退步例（若有）。这是个例展示，不能替代全表；v0及每份答卷的通道一并列出。通道不同的例题不能归因为训练作用。"]
        for question, label in selected:
            lines += ["", f"### {question} · {label}", ""]
            for version in versions:
                if version not in first:
                    lines.append(f"{version}：待齐。")
                    continue
                path, rows = first[version]
                row = next(r for r in rows if r["name"] == question)
                transport = row_transport(row)
                lines += [f"<details><summary>{version} · {escape(transport['provider'])} / {escape(transport['model'])}：挂项 {len(row['failed'])}/{len(row['judged'])}</summary>", "",
                          f"[完整答卷和逐项模型判定]({path})", "", "<pre>" + escape(row["product"][:3000]) + "</pre>",
                          "（超过 3000 字的答卷在此截断；原文见上方链接。）" if len(row["product"]) > 3000 else "", "</details>"]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    names = [name for name in sys.argv[1:] if name != "--records"]
    print("\n".join(card(name, "--records" in sys.argv[1:]) for name in names))
