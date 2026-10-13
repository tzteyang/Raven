"""独立从员工文件复算参考，并用真正浏览器检查40份可行答卷。

不调用make.py的规则/冲突函数。--quick仅复算参考；默认完整浏览器验证。
--probes写出5份手写模板答卷供LLM评审探测。
"""

import argparse
import json
import re
from pathlib import Path

from fixtures import answer
from measure import measure

HERE = Path(__file__).resolve().parent


def independent(question):
    source = json.loads(question["files"]["课表.json"])
    rules, ref = question["files"]["工作规则.md"], question["reference"]
    by_id = {c["id"]: c for c in source["courses"]}
    m = re.search(r"间隔正好 (\d+) 分钟", rules)
    gap = int(m[1]) if m else 0
    m = re.search(r"同一日期最多预约 (\d+) 节", rules)
    limit = int(m[1]) if m else None
    notices = {"ok": re.search(r"页面显示“([^”]+)”", rules)[1], "conflict": re.search(r"冲突时显示“([^”]+)”", rules)[1],
               "limit": re.search(r"也不能约，提示“([^”]+)”", rules)[1] if limit else None}
    initial = {i: c["remaining"] for i, c in by_id.items()}
    diffs = []
    def same(label, got, want):
        if got != want:
            diffs.append((label, got, want))
    same("initial", ref["初始名额"], initial)
    same("full", ref["满员id"], sorted(i for i, c in by_id.items() if c["remaining"] == 0))
    same("types", ref["筛选后可见id"], {t: sorted(i for i, c in by_id.items() if c["type"] == t) for t in {c["type"] for c in by_id.values()}})
    same("key", ref["当前存储键"], re.search(r"键名严格为“([^”]+)”", rules)[1] + source["week_id"])
    same("gap", ref["规则参数"]["gap"], gap)
    same("limit", ref["规则参数"]["limit"], limit)
    minute = lambda t: int(t.split(":")[0]) * 60 + int(t.split(":")[1])
    def conflicts(a, b):
        if a["date"] != b["date"]:
            return False
        # Independent disjoint-interval formula: sort the pair, compare end + break to next start.
        before, after = sorted((a, b), key=lambda c: c["start"])
        return minute(before["end"]) + gap > minute(after["start"])
    booked, notice = set(), ""
    for step in ref["顺序操作"]:
        cid = step["click"]
        c = by_id[cid]
        if cid in booked:
            action = "保持，不能重复扣名额"
        elif any(conflicts(c, by_id[i]) for i in booked):
            action, notice = "拒绝，时间冲突", notices["conflict"]
        elif limit is not None and sum(by_id[i]["date"] == c["date"] for i in booked) == limit:
            action, notice = "拒绝，达到当日上限", notices["limit"]
        else:
            booked.add(cid)
            action, notice = "成功", notices["ok"]
        same(step["action"], {k: step[k] for k in ("result", "notice", "booked", "remaining")},
             dict(result=action, notice=notice, booked=sorted(booked), remaining={i: c["remaining"] - int(i in booked) for i, c in by_id.items()}))
    mixed = {i for i in ref["混合存储"]["input"] if isinstance(i, str) and i in by_id and by_id[i]["remaining"] > 0}
    same("mixed", ref["混合存储"]["booked"], sorted(mixed))
    return diffs


def browser_check(question, observed):
    ref = question["reference"]
    data = json.loads(question["files"]["课表.json"])
    r, problems = ref["规则参数"], []
    def same(label, got, want):
        if got != want:
            problems.append((label, got, want))
    def state(label, got, expected, notice=None):
        same(label + ".remaining", got["remaining"], {i: str(n) for i, n in expected["remaining"].items()})
        same(label + ".booked", sorted(got["buttons"].get(r["booked"], [])), expected["booked"])
        if notice is not None:
            same(label + ".notice", got["notice"], notice)
    if "浏览器实测" not in observed:
        return [("browser tool unavailable", observed)]
    b = observed["浏览器实测"]
    if "probe_error" in b or "probe_interrupted" in b:
        return [("browser interrupted", b)]
    same("requests", b["external_requests"], [])
    same("pageerrors", b["pageerrors"], [])
    same("dialogs", b["dialogs"], [])
    initial = dict(booked=[], remaining=ref["初始名额"])
    state("initial", b["initial"], initial)
    same("initial.count", b["initial"]["cardCount"], len(data["courses"]))
    same("initial.all", sorted(b["initial"]["visible"]), sorted(ref["初始名额"]))
    same("initial.full", sorted(b["initial"]["disabled"]), ref["满员id"])
    same("initial.missing", b["initial"]["missing"], [])
    same("notice", b["initial"]["noticeAttributes"], dict(role="status", live="polite", visible=True))
    details = {d["id"]: d["text"] for d in b["initial"]["details"]}
    for c in data["courses"]:
        for key in ["title", "type", "date", "start", "end", "coach"]:
            if c[key] not in details[c["id"]]:
                problems.append(("missing course detail", c["id"], key))
    for f in b["filters"]:
        if "error" in f:
            problems.append(("filter error", f))
            continue
        same("filter." + f["selected"], sorted(f["visible"]), ref["筛选后可见id"].get(f["selected"], sorted(ref["初始名额"])))
        same("filter.remaining", f["remaining"], {i: str(n) for i, n in ref["初始名额"].items()})
    for f in b["full"]:
        same("full.operation", f["operation"]["action"], "鼠标实际点到按钮位置")
        same("full.disabled", f["operation"].get("browserDisabled"), True)
        state("full", f["after"], initial)
    for expected, got in zip(ref["顺序操作"], b["sequence"]):
        state(expected["action"], got["after"], expected, expected["notice"])
    same("saved.keys", list(b["saved"]), [ref["当前存储键"]])
    if ref["当前存储键"] in b["saved"]:
        same("saved.ids", sorted(json.loads(b["saved"][ref["当前存储键"]])), ref["刷新后"]["booked"])
    state("reload", b["reload"], ref["刷新后"])
    for f in b["filter_after_booking"]:
        state("post-filter", f["after"], ref["刷新后"])
        same("post-filter.visible", sorted(f["after"]["visible"]), ref["筛选后可见id"].get(f["selected"], sorted(ref["初始名额"])))
    for f in b["storage_cases"]:
        state("storage." + f["name"], f["after"], ref["混合存储"] if f["name"] == "混合数组" else initial)
        same("storage.errors", f["pageerrors"], [])
    keys = b["keyboard"]
    same("keyboard.enter", keys["enterSent"], True)
    state("keyboard", keys["after"], ref["顺序操作"][0], r["success"])
    same("keyboard.tab.ids", sorted({f["course"] for f in keys["tab"] if f["isBook"]}), sorted(i for i, n in ref["初始名额"].items() if n > 0))
    if not any(f["id"] == "type-filter" for f in keys["tab"]):
        problems.append("filter is unreachable by Tab")
    if any(not f["focusVisible"] for f in keys["tab"] if f["isBook"] or f["id"] == "type-filter"):
        problems.append("focus invisible")
    disabled = b["storage_disabled"]
    state("disabled.initial", disabled["initial"], initial)
    state("disabled.book", disabled["after"], ref["顺序操作"][0], r["success"])
    state("disabled.reload", disabled["reload"], initial)
    return problems


def write_probes(bank):
    q, y = bank["t12"], bank["y06"]
    good = answer(q)
    probes = [dict(name="t12", label="right", expect=[], answer=good),
              dict(name="t12", label="wrong", expect=["BP-reserve", "BP-storage"], answer=answer(q, ["start-only", "no-save"])),
              dict(name="y06", label="right", expect=[], answer=answer(y)),
              dict(name="y06", label="wrong", expect=["BP-reserve", "BP-keyboard"], answer=answer(y, ["daily", "keyboard"])),
              dict(name="t12", label="wrapper", expect=["BP-delivery"], answer="页面写好了，下面是交付。\n\n" + good + "\n\n已检查，随时可以约课。")]
    destination = Path(__file__).resolve().parent / "probes" / "probe-booking-page.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(probes, ensure_ascii=False, indent=1) + "\n")
    print("probes:", destination)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--probes", action="store_true")
    parser.add_argument("--only")
    args = parser.parse_args()
    bank = {q["name"]: q for q in json.loads((HERE / "questions.json").read_text())}
    wrong = []
    for name, q in bank.items():
        if args.only and name != args.only:
            continue
        errors = independent(q)
        if not args.quick:
            errors.extend(browser_check(q, measure(q, answer(q))))
        if errors:
            wrong.append((name, errors))
        print(name, "ok" if not errors else errors, flush=True)
    print("mismatches:", wrong or "none", flush=True)
    assert not wrong
    if args.probes:
        write_probes(bank)


if __name__ == "__main__":
    main()
