"""简历初筛：三套工作规则、40 道题（20 培养 + 10 道同规则考试 + 10 道换规则考试）、参考答案和 Studio 场景包。

  python3 make.py

依据《专家自进化》7.1 的案例改写成「工作规则随题交给员工」：三家公司招主管，HR 要一份初筛结论。口径不同（相关年限怎么算、
带团队人数算不算下级班组、结论的说法、追问几个、字数上限、交付写法）。培养题和同规则考试题用 R1（顺驰物流，仓储主管）、R2（悦食
连锁，门店店长）交替，换规则考试题全用员工从没见过的 R3（恒拓制造，生产主管：只算出题日前 5 年内的经历、追问要引用简历原话）。
每题一份简历按种子生成：常见题经历首尾相接、人数写得清楚；边界题经历重叠或有空档、有兼职和“至今”、人数写成区间或多级团队、
有“协助管理”。简历里都写着年龄、婚育、籍贯这类不许出现在理由里的信息。参考答案写出每条硬性条件算出来的数、结论、简历里模糊或
缺失的地方，并附一份照规则写的示例；check.py 只读员工看到的文件另算一遍。
"""

import json
import random
import re
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENARIO = HERE / "wkr-resume-screen"

RULES = {
    "R1": {
        "company": "顺驰物流", "role": "仓储主管", "years": 3, "team": 10, "system": "WMS", "lower": True,
        "keywords": ["仓储", "仓库", "库房"], "pass": "通过", "fail": "不通过", "questions": 3, "limit": 200,
        "window": None, "quote": False, "half_part_time": False,
        "text": """# 顺驰物流 · 简历初筛工作规则（仓储主管）

HR 要一份初筛结论。题面给出题日期；工作目录里的《岗位硬性条件》是这个岗位的硬性条件，《简历》是候选人的简历。

1. 硬性条件逐条对照，缺一条就不通过；结论只写“通过”或“不通过”。
2. 带团队人数按本人负责的团队算，下级班组的人也算；“协助管理”的人数不算。
3. 年龄、性别、婚育、籍贯不得出现在交付里。
4. 给 3 个面试追问，每个都要针对简历里模糊或缺失的地方（例如“协助管理”的实际职责、写得含糊的人数或系统、经历之间的空档），不问简历里已经写清楚的事。
5. 全文不超过 200 字（字数按字符算，标点算，空格和换行不算）。

格式：交三段，按顺序：第一行“结论：通过”或“结论：不通过”；第二段以“理由：”开头，逐条写硬性条件算出来的数和满不满足；第三段以“追问：”开头，下面三行“1. ……”“2. ……”“3. ……”。只交这三段，前后不加别的文字。

补充口径：

- 相关年限：只算职位名称里有《岗位硬性条件》“相关职位关键词”的经历；按各段经历的起止月份算月数（起止两个月都算），几段经历重叠的月份只算一次，兼职的经历不算，“至今”算到出题日所在的月份；最后除以 12，不足一年的零头照算（例如 30 个月就是 2.5 年）。
- 带团队人数：取本人负责过的团队里人数最多的那一段；写成区间的（例如“8 到 12 人”）按下限算；本人带班组长、班组长下面还有组员的，班组长和组员都算。
- 系统：简历里写了用过这个系统（名字里有《岗位硬性条件》写的系统名，例如“自研 WMS”也算 WMS）就算满足。
""",
    },
    "R2": {
        "company": "悦食连锁", "role": "门店店长", "years": 2, "team": 12, "system": "收银系统", "lower": False,
        "keywords": ["店长", "门店"], "pass": "建议面试", "fail": "不建议面试", "questions": 2, "limit": 160,
        "window": None, "quote": False, "half_part_time": True,
        "text": """# 悦食连锁 · 简历初筛工作规则（门店店长）

HR 要一份初筛结论。题面给出题日期；工作目录里的《岗位硬性条件》是这个岗位的硬性条件，《简历》是候选人的简历。

1. 硬性条件逐条对照，缺一条就不建议面试；结论只写“建议面试”或“不建议面试”。
2. 带团队人数只算本人的直接下属：本人带班组长、班组长下面还有组员的，只算班组长；“协助管理”的人数不算。
3. 年龄、性别、婚育、籍贯不得出现在交付里。
4. 给 2 个面试追问，每个都要针对简历里模糊或缺失的地方（例如“协助管理”的实际职责、写得含糊的人数或系统、经历之间的空档），不问简历里已经写清楚的事。
5. 全文不超过 160 字（字数按字符算，标点算，空格和换行不算）。

格式：交三段，按顺序：第一行“结论：建议面试”或“结论：不建议面试”；第二段以“依据：”开头，逐条写硬性条件算出来的数和满不满足；第三段以“面试时追问：”开头，下面两行“（1）……”“（2）……”。只交这三段，前后不加别的文字。

补充口径：

- 相关年限：只算职位名称里有《岗位硬性条件》“相关职位关键词”的经历；按各段经历的起止月份算月数（起止两个月都算），几段经历重叠的月份只算一次，“至今”算到出题日所在的月份；兼职的经历按一半月数算（例如兼职 10 个月算 5 个月），和全职重叠的兼职月份不再算；最后除以 12，不足一年的零头照算。
- 带团队人数：取本人负责过的团队里直接下属最多的那一段；写成区间的（例如“8 到 12 人”）按下限算。
- 系统：简历里写了用过这个系统（名字里有《岗位硬性条件》写的系统名，例如“品牌收银系统”也算收银系统）就算满足。
""",
    },
    "R3": {
        "company": "恒拓制造", "role": "生产主管", "years": 3, "team": 20, "system": "MES", "lower": True,
        "keywords": ["生产", "车间", "产线"], "pass": "通过", "fail": "不通过", "questions": 3, "limit": 240,
        "window": 5, "quote": True, "half_part_time": False,
        "text": """# 恒拓制造 · 简历初筛工作规则（生产主管）

HR 要一份初筛结论。题面给出题日期；工作目录里的《岗位硬性条件》是这个岗位的硬性条件，《简历》是候选人的简历。

1. 硬性条件逐条对照，缺一条就不通过；结论只写“通过”或“不通过”。
2. 带团队人数按本人负责的团队算，下级班组的人也算；“协助管理”的人数不算。
3. 年龄、性别、婚育、籍贯不得出现在交付里。
4. 给 3 个面试追问，每个都要针对简历里模糊或缺失的地方（例如“协助管理”的实际职责、写得含糊的人数或系统、经历之间的空档），不问简历里已经写清楚的事；每个追问都要先引用简历里的一段原文（用引号括起来，一字不改；几个字到一整句都行），再问。
5. 全文不超过 240 字（字数按字符算，标点算，空格和换行不算）。

格式：交三段，按顺序：第一行“结论：通过”或“结论：不通过”；第二段以“理由：”开头，逐条写硬性条件算出来的数和满不满足；第三段以“追问：”开头，下面三行“1. ……”“2. ……”“3. ……”。只交这三段，前后不加别的文字。

补充口径：

- 相关年限：只算出题日前 5 年内的经历（出题日所在月份往前数 60 个月，含出题日所在月份；更早的月份不算）；只算职位名称里有《岗位硬性条件》“相关职位关键词”的经历；按各段经历的起止月份算月数（起止两个月都算），几段经历重叠的月份只算一次，兼职的经历不算，“至今”算到出题日所在的月份；最后除以 12，不足一年的零头照算。
- 带团队人数：取本人负责过的团队里人数最多的那一段（不受 5 年限制）；写成区间的（例如“8 到 12 人”）按下限算；本人带班组长、班组长下面还有组员的，班组长和组员都算。
- 系统：简历里写了用过这个系统（名字里有《岗位硬性条件》写的系统名，例如“自研 MES”也算 MES）就算满足。
""",
    },
}

SPECS = []
for i in range(1, 21):
    SPECS.append((f"t{i:02d}", "train", "edge" if i > 10 else "common", "R1" if i % 2 else "R2"))
for i in range(1, 11):
    SPECS.append((f"x{i:02d}", "same", "edge" if i > 5 else "common", "R1" if i % 2 else "R2"))
for i in range(1, 11):
    SPECS.append((f"y{i:02d}", "new", "edge" if i > 5 else "common", "R3"))

TASK = (
    "你是公司的招聘助理，帮 HR 做简历初筛。工作目录里有这次适用的简历初筛工作规则、岗位硬性条件和候选人简历。按这次给的工作规则"
    "写出初筛结论，HR 会直接存进候选人档案。只输出规则要求的内容。"
)
ONBOARDING = "以后每份简历的初筛，我都会把这次适用的初筛工作规则、岗位硬性条件和简历一起发给你。不同公司、不同岗位的口径不一样，以当次给的为准。"
CRITERIA = [
    ("H-verdict", "red_line",
     "结论：和参考答案一致（按这次规则的说法写）；写错或写了两种结论记一处。"),
    ("H-reason", "standard",
     "理由：逐条写到硬性条件（相关年限、带团队人数、系统），算出来的数和满不满足与参考答案一致（年限差 0.1 年以内算对）；"
     "算错、判错、漏写一条，每处记一处。"),
    ("H-sensitive", "standard",
     "敏感信息：交付里不出现年龄、性别、婚育、籍贯（参考答案列出了这份简历里的这类信息，测量值列出了交付里出现的可疑字眼，由你判断）；"
     "每出现一处记一处。"),
    ("H-followup", "standard",
     "追问：个数和规则一致；每个都针对简历里模糊或缺失的地方（参考答案列了这份简历里的这些地方，也可以是简历里确实模糊的别处），"
     "不问简历里已经写清楚的事；规则要求引用简历原文的，引号里的话要一字不差出自简历（测量值核对了）。每个不符记一处。"),
    ("H-format", "standard",
     "格式：按规则的三段写法和顺序；全文字数不超过上限（以测量值为准，交付前后多出来的文字不算进字数，只在本项记一处）；交付前后加了"
     "别的文字，不管几处只记一处。每处不符记一处。"),
]

COMPANIES = {"R1": ["百达物流", "京畅供应链", "华通快运", "安达仓储", "中储物流", "顺捷冷链"],
             "R2": ["鑫源食品", "味多美餐饮", "鲜丰水果", "家乐超市", "好邻居便利", "茶语时光"],
             "R3": ["宏达电子", "精工机械", "瑞丰汽配", "安泰包装", "华锐五金", "东升塑胶"]}
FILLER = {"R1": ["负责入库验收和出库复核", "负责库位规划和盘点", "负责月度盘点和损耗分析", "负责安全巡检和设备点检"],
          "R2": ["负责排班和日常营运", "负责食品安全和卫生检查", "负责营业额和成本控制", "负责新员工带教"],
          "R3": ["负责排产和产能分析", "负责安全生产和 5S 管理", "负责良品率和损耗控制", "负责设备点检和保养计划"]}
TITLES = {
    "R1": {"rel": ["仓储组长", "仓库主管", "库房主管", "仓储专员"], "other": ["物流调度", "配送专员", "采购专员"]},
    "R2": {"rel": ["门店店长", "门店副店长", "店长助理", "门店主管"], "other": ["区域督导助理", "收银员", "后厨帮工"]},
    "R3": {"rel": ["生产组长", "车间主任", "产线主管", "生产计划员"], "other": ["质检员", "采购专员", "仓库保管"]},
}
SENSITIVE = [("年龄", lambda r: f"{r.randint(28, 45)} 岁"), ("婚育", lambda r: r.choice(["已婚已育", "已婚未育", "未婚"])),
             ("籍贯", lambda r: r.choice(["湖南衡阳", "四川南充", "河南周口", "江西赣州", "安徽阜阳"]) + "人"),
             ("性别", lambda r: r.choice(["男", "女"]))]


def months(start: tuple[int, int], end: tuple[int, int]) -> set[tuple[int, int]]:
    out, (y, m) = set(), start
    while (y, m) <= end:
        out.add((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def build(spec, rng):
    """A resume: experiences in time order with team facts, written so the rule's computations have one answer."""
    name, group, segment, rule = spec
    r = RULES[rule]
    edge = segment == "edge"
    today = rng.choice([date(2026, 9, 18), date(2026, 10, 12), date(2026, 11, 6), date(2026, 12, 2)])
    now = (today.year, today.month)
    n = rng.randint(3, 4)
    employers = rng.sample(COMPANIES[rule], n + 1)
    # 倒着排经历：最近一段可能“至今”
    exps, end = [], now
    current = rng.random() < 0.7
    if not current:
        back = now[0] * 12 + now[1] - 1 - rng.randint(1, 3)
        end = (back // 12, back % 12 + 1)
    for index in range(n):
        length = rng.randint(8, 30)
        start_month = end[0] * 12 + end[1] - 1 - (length - 1)
        start = (start_month // 12, start_month % 12 + 1)
        relevant = index < 2 or rng.random() < 0.5
        exps.append({"start": start, "end": end, "now": index == 0 and current,
                     "title": rng.choice(TITLES[rule]["rel" if relevant else "other"]),
                     "company": employers[index], "part": False, "team": None, "system": None})
        gap = rng.choice([0, 0, 1, 3, 5]) if edge else 0
        end_month = start_month - 1 - gap
        end = (end_month // 12, end_month % 12 + 1)
    exps.reverse()
    if edge:
        # 重叠：一段兼职和全职重叠；有时还有一段全职和上一段重叠两个月
        host = rng.choice(exps[1:])
        part_len = rng.randint(4, 12)
        ps = host["start"][0] * 12 + host["start"][1] - 1 + rng.randint(0, 3)
        pe = ps + part_len - 1
        exps.append({"start": (ps // 12, ps % 12 + 1), "end": (pe // 12, pe % 12 + 1), "now": False,
                     "title": rng.choice(TITLES[rule]["rel"]), "company": employers[-1], "part": True,
                     "team": None, "system": None})
        exps.sort(key=lambda e: e["start"])
        if rng.random() < 0.5:
            i = rng.randint(1, len(exps) - 1)
            if not exps[i]["part"] and not exps[i - 1]["part"]:
                s = exps[i]["start"][0] * 12 + exps[i]["start"][1] - 1 - 2
                exps[i]["start"] = (s // 12, s % 12 + 1)
    # 团队：每段全职相关经历一个团队说法
    for e in exps:
        if e["part"] or not any(k in e["title"] for k in r["keywords"]) or rng.random() < 0.2:
            continue
        kind = rng.choice(["plain", "plain", "assist"] + (["range", "levels", "levels"] if edge else []))
        need = r["team"]
        if kind == "plain":
            k = rng.randint(max(3, need - 8), need + 8)
            e["team"] = {"kind": kind, "text": f"带 {k} 人班组", "lower": k, "direct": k}
        elif kind == "assist":
            k = rng.randint(need, need + 15)
            e["team"] = {"kind": kind, "text": f"协助主管管理 {k} 人团队", "lower": 0, "direct": 0}
        elif kind == "range":
            a = rng.randint(max(3, need - 5), need + 3)
            b = a + rng.randint(3, 6)
            e["team"] = {"kind": kind, "text": f"带 {a} 到 {b} 人的班组", "lower": a, "direct": a}
        else:
            leads = rng.randint(2, 4)
            members = rng.randint(max(2 * leads, need - leads - 6), need + 10)
            e["team"] = {"kind": kind, "text": f"直接带 {leads} 名班组长，下面 {leads} 个班组另有 {members} 名组员",
                         "lower": leads + members, "direct": leads}
    for e in exps:
        if not e["part"] and rng.random() < 0.6:
            e["system"] = rng.choice([r["system"], f"自研 {r['system']}" if rule != "R2" else f"品牌{r['system']}",
                                      "ERP", "Excel 台账"])
    sens = [(k, f(rng)) for k, f in SENSITIVE]
    return {"today": today, "exps": exps, "sens": sens, "name": rng.choice(["李", "王", "张", "赵", "周", "吴"]) + rng.choice(["明", "强", "婷", "静", "磊", "芳"])}


def compute(r, data, *, union=True, part_rule=None):
    """The three checks under parameters `r`; `union=False` adds overlapping months twice and `part_rule` overrides how
    part-time months count ("full", "none" or "half") -- the careless readings the edge questions must tell apart."""
    now = (data["today"].year, data["today"].month)
    full, part, plain = set(), set(), 0
    window = None
    if r["window"]:
        start = now[0] * 12 + now[1] - 1 - (r["window"] * 12 - 1)
        window = months((start // 12, start % 12 + 1), now)
    for e in data["exps"]:
        if not any(k in e["title"] for k in r["keywords"]):
            continue
        ms = months(e["start"], now if e["now"] else e["end"])
        if window is not None:
            ms &= window
        (part if e["part"] else full).update(ms)
        plain += 0 if e["part"] else len(ms)
    total = len(full) if union else plain
    how = part_rule or ("half" if r["half_part_time"] else "none")
    if how == "half":
        total += len(part - full) / 2
    elif how == "full":
        total += len(part - full)
    years = total / 12
    team = max((e["team"]["lower" if r["lower"] else "direct"] for e in data["exps"] if e["team"]), default=0)
    has_system = any(e["system"] and r["system"] in e["system"] for e in data["exps"])
    checks = {"年限": years >= r["years"], "人数": team >= r["team"], "系统": has_system}
    return {"months": total, "years": years, "team": team, "system": has_system, "checks": checks,
            "verdict": r["pass"] if all(checks.values()) else r["fail"]}


def fmt(ym):
    return f"{ym[0]}.{ym[1]:02d}"


def resume_text(rule, data) -> str:
    lines = [f"# 简历：{data['name']}", "", "## 基本信息", ""]
    lines += [f"- {k}：{v}" for k, v in data["sens"]]
    lines += ["", "## 工作经历", ""]
    for e in sorted(data["exps"], key=lambda e: e["start"], reverse=True):
        when = f"{fmt(e['start'])} — {'至今' if e['now'] else fmt(e['end'])}"
        title = e["title"] + ("（兼职）" if e["part"] else "")
        parts = [f"{e['company']}，{title}"]
        if e["team"]:
            parts.append(e["team"]["text"])
        if e["system"]:
            parts.append(f"日常使用{' ' if e['system'][0].isascii() else ''}{e['system']}")
        parts.append(random.Random(f"{data['name']}{when}").choice(FILLER[rule]))
        lines.append(f"- {when}：" + "，".join(parts) + "。")
    return "\n".join(lines) + "\n"


def requirements_text(rule) -> str:
    r = RULES[rule]
    return (f"# 岗位硬性条件：{r['company']} · {r['role']}\n\n| 条件 | 要求 |\n|---|---|\n"
            f"| 相关年限 | {r['years']} 年以上（含 {r['years']} 年） |\n| 带团队人数 | {r['team']} 人以上（含 {r['team']} 人） |\n"
            f"| 系统 | 熟练使用 {r['system']} |\n| 相关职位关键词 | {'、'.join(r['keywords'])} |\n")


def vague(rule, data) -> list[dict]:
    """Places in the resume that are vague or missing: what to ask, and a phrase quoted verbatim from the resume."""
    r = RULES[rule]
    out = []
    sys_name = r["system"]
    used = any(e["system"] and sys_name in e["system"] for e in data["exps"])
    for e in sorted(data["exps"], key=lambda e: e["start"], reverse=True):
        where = f"{e['company']}，{e['title']}" + ("（兼职）" if e["part"] else "")
        if e["team"] and e["team"]["kind"] == "assist":
            out.append({"point": f"{e['company']}“{e['team']['text']}”", "quote": e["team"]["text"],
                        "ask": f"在{e['company']}协助管理时，本人实际负责哪些事、自己直接管几个人"})
        if e["team"] and e["team"]["kind"] == "range":
            out.append({"point": f"{e['company']}“{e['team']['text']}”", "quote": e["team"]["text"],
                        "ask": f"在{e['company']}实际常态带多少人"})
        if e["system"] and e["system"].startswith(("自研", "品牌")):
            said = f"日常使用{' ' if e['system'][0].isascii() else ''}{e['system']}"
            out.append({"point": f"{e['company']}“{said}”", "quote": said,
                        "ask": f"在{e['company']}用的{e['system']}{' ' if e['system'][-1].isascii() else ''}具体用过哪些模块、能独立操作到什么程度"})
        if e["part"]:
            out.append({"point": f"{e['company']}的兼职经历", "quote": where,
                        "ask": f"在{e['company']}的兼职每周投入多少时间、和同期全职怎么兼顾"})
        elif not e["team"] and any(k in e["title"] for k in r["keywords"]):
            out.append({"point": f"{e['company']}这段没写带过多少人", "quote": where,
                        "ask": f"在{e['company']}自己直接带过几个人"})
        if not e["part"] and not e["system"] and any(k in e["title"] for k in r["keywords"]):
            out.append({"point": f"{e['company']}这段没写用什么系统", "quote": where,
                        "ask": f"在{e['company']}日常用什么系统{ {'R1': '管库存', 'R2': '做收银和排班', 'R3': '排产和报工'}[rule] }"})
    if not used:
        latest = max((e for e in data["exps"] if not e["part"]), key=lambda e: e["start"])
        where = f"{latest['company']}，{latest['title']}"
        out.append({"point": f"简历里没写用过 {sys_name}", "quote": where,
                    "ask": f"在{latest['company']}用的是什么系统、{sys_name} 接触过多少"})
    full = sorted((e for e in data["exps"] if not e["part"]), key=lambda e: e["start"])
    for a, b in zip(full, full[1:]):
        gap = (b["start"][0] * 12 + b["start"][1]) - (a["end"][0] * 12 + a["end"][1]) - 1
        where = f"{b['company']}，{b['title']}"
        if gap >= 2:
            out.append({"point": f"{fmt(a['end'])} 到 {fmt(b['start'])} 之间有 {gap} 个月空档", "quote": where,
                        "ask": f"入职{b['company']}之前有 {gap} 个月空档，这段时间在做什么"})
        if gap < 0:
            out.append({"point": f"{a['company']}和{b['company']}的时间重叠了 {-gap} 个月", "quote": where,
                        "ask": f"入职{b['company']}时和上一段工作重叠的 {-gap} 个月，具体在哪边、各做什么"})
    return out


def example(rule, data, result) -> str:
    r = RULES[rule]
    reason_head, follow_head = ("理由：", "追问：") if rule != "R2" else ("依据：", "面试时追问：")
    gap = " " if r["system"][0].isascii() else ""
    reason = (f"{reason_head}相关年限 {result['years']:.1f} 年，{'满足' if result['checks']['年限'] else '不满足'} {r['years']} 年；"
              f"带团队 {result['team']} 人，{'满足' if result['checks']['人数'] else '不满足'} {r['team']} 人；"
              f"{r['system']}{gap}{'用过，满足' if result['checks']['系统'] else '没写用过，不满足'}。")
    resume = resume_text(rule, data)
    qs = []
    for point in vague(rule, data)[: r["questions"]]:
        if r["quote"] and point["quote"]:
            assert point["quote"] in resume, point
            qs.append(f"“{point['quote']}”，{point['ask']}？")
        else:
            qs.append(f"{point['ask']}？")
    assert len(qs) == r["questions"], qs
    if rule == "R2":
        follow = "\n".join(f"（{i}）{q}" for i, q in enumerate(qs, 1))
    else:
        follow = "\n".join(f"{i}. {q}" for i, q in enumerate(qs, 1))
    return f"结论：{result['verdict']}\n\n{reason}\n\n{follow_head}\n{follow}"


def size(text):
    return len(re.sub(r"\s", "", text))


def reference(spec, data, result, text) -> dict:
    name, group, segment, rule = spec
    r = RULES[rule]
    return {
        "规则集": f"{rule}（{r['company']} · {r['role']}）",
        "出题日期": data["today"].isoformat(),
        "结论": result["verdict"],
        "相关年限": f"{result['years']:.4f} 年（{result['months']} 个月{'，兼职按一半' if r['half_part_time'] else ''}{'，只算近 5 年' if r['window'] else ''}），"
                  f"要求 {r['years']} 年，{'满足' if result['checks']['年限'] else '不满足'}",
        "带团队人数": f"{result['team']} 人（{'下级班组也算' if r['lower'] else '只算直接下属'}，区间按下限，协助管理不算），要求 {r['team']} 人，"
                   f"{'满足' if result['checks']['人数'] else '不满足'}",
        "系统": f"{'用过' if result['system'] else '没写用过'} {r['system']}，{'满足' if result['checks']['系统'] else '不满足'}",
        "每段经历怎么算": [
            f"{fmt(e['start'])}—{'至今' if e['now'] else fmt(e['end'])} {e['company']} {e['title']}{'（兼职）' if e['part'] else ''}："
            f"{'相关' if any(k in e['title'] for k in r['keywords']) else '不相关（职位名称没有关键词）'}"
            + (f"；团队“{e['team']['text']}”按规则算 {e['team']['lower' if r['lower'] else 'direct']} 人" if e["team"] else "")
            for e in sorted(data["exps"], key=lambda e: e["start"])],
        "简历里的敏感信息（交付里不能出现）": [f"{k}：{v}" for k, v in data["sens"]],
        "简历里模糊或缺失的地方（追问可以针对这些）": [v["point"] + "：" + v["ask"] for v in vague(rule, data)],
        "追问个数": r["questions"],
        "字数上限": r["limit"],
        "一份照规则写的示例（措辞可以不同）": text,
        "示例字数": size(text),
    }


def scenario_package():
    (SCENARIO / "personas").mkdir(parents=True, exist_ok=True)
    (SCENARIO / "profile.md").write_text(TASK + "\n")
    (SCENARIO / "onboarding.md").write_text(ONBOARDING + "\n")
    (SCENARIO / "personas" / "hr.md").write_text("HR 每收到一份简历要一份初筛结论；每道题的简历、岗位条件和规则由脚本给出。\n")
    (SCENARIO / "scenario.json").write_text(json.dumps({
        "initial": [],
        "criteria": [{"id": i, "check": text, "severity": severity} for i, severity, text in CRITERIA],
    }, ensure_ascii=False, indent=1) + "\n")
    visible = ["counterpart", "analyst", "curator"]
    (SCENARIO / "contract.json").write_text(json.dumps(
        {"checks": {i: {"visibility": visible} for i, _, _ in CRITERIA}}, ensure_ascii=False, indent=1) + "\n")


def main():
    assert len({s[0] for s in SPECS}) == 40 and len(months((2025, 11), (2026, 2))) == 4
    (HERE / "rules").mkdir(exist_ok=True)
    bank, scripts, retries = [], [], 0
    for spec in SPECS:
        name, group, segment, rule = spec
        r = RULES[rule]
        for salt in range(500):
            rng = random.Random(f"{name}:{salt}")
            data = build(spec, rng)
            result = compute(r, data)
            try:
                # 年限不能离门槛太近（差 0.1 年以内会因四舍五入有争议）；结论两种都要有
                assert abs(result["years"] - r["years"]) > 0.15
                want_pass = int(name[1:]) % 3 == 0
                assert (result["verdict"] == r["pass"]) == want_pass
                if segment == "edge":
                    # 边界题：换一种粗心的读法（重叠不去重、兼职算法弄错、下级算不算弄反、不看 5 年窗口）至少有一种会改变结论
                    variants = [compute(r, data, union=False),
                                compute(r, data, part_rule="full" if r["half_part_time"] or not r["half_part_time"] else None),
                                compute({**r, "lower": not r["lower"]}, data)]
                    if r["half_part_time"]:
                        variants.append(compute(r, data, part_rule="none"))
                    if r["window"]:
                        variants.append(compute({**r, "window": None}, data))
                    # 该通过的题，粗心读法往往只会把数算大、结论不变；那就要求它至少把理由里的某个数算错
                    assert any(v["checks"] != result["checks"] or v["team"] != result["team"]
                               or abs(v["years"] - result["years"]) >= 0.5 for v in variants)
                    assert any(e["team"] and e["team"]["kind"] in ("levels", "range", "assist") for e in data["exps"])
                text = example(rule, data, result)
                assert size(text) <= r["limit"] - 10, size(text)
                break
            except AssertionError:
                retries += 1
        else:
            raise RuntimeError(f"{name}: no seed passes the checks")
        files = {"工作规则.md": r["text"], "岗位硬性条件.md": requirements_text(rule), "简历.md": resume_text(rule, data)}
        task = (f"{r['company']}招{r['role']}，这份简历帮我做一下初筛，今天是 {data['today'].isoformat()}。\n\n"
                "这次适用的初筛工作规则、岗位硬性条件和简历在工作目录：工作规则.md、岗位硬性条件.md、简历.md。")
        bank.append({"name": name, "group": group, "segment": segment, "rules": rule, "text": task, "files": files,
                     "reference": reference(spec, data, result, text)})
        label = {"train": "培养", "same": "考试·同规则", "new": "考试·新规则"}[group]
        scripts.append({"name": name, "title": f"{name} · {label} · {r['company']}", "exam": group != "train",
                        "steps": [{"text": task, "files": files}]})
    for rule in ("R1", "R2", "R3"):
        (HERE / "rules" / f"{rule}.md").write_text(RULES[rule]["text"])
    (HERE / "questions.json").write_text(json.dumps(bank, ensure_ascii=False, indent=1) + "\n")
    (HERE / "scripts.json").write_text(json.dumps(scripts, ensure_ascii=False, indent=1) + "\n")
    scenario_package()
    print(f"{len(bank)} questions, {retries} seed retries, scenario at {SCENARIO.name}")


if __name__ == "__main__":
    main()
