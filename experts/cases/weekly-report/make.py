"""运营周报：三套工作规则、40 道题（20 培养 + 10 道同规则考试 + 10 道换规则考试）、参考答案和 Studio 场景包。

  python3 make.py

依据《专家自进化》4.2 的案例改写成「工作规则随题交给员工」：三家电商的总监对周报的偏好不同（段名和顺序、第一行怎么写、
环比怎么写、单位怎么写、禁用词、字数上限、上周没有的指标怎么标）。培养题和同规则考试题用 R1（青禾电商）、R2（木棉电商）
交替，换规则考试题全用员工从没见过的 R3（北辰电商）。每道题给一周的零散记录、上周周报和指标口径表；记录按种子生成，
埋下要总监拍板的事、已经确认过的事（不写）、下周计划、不是指标的数字。边界题再埋别名（“新增客户”对“新客数”）、单位不统一
（“12.4 万”）、上周没有的指标。参考答案给每个指标的本周数、上周数和未取舍的变化；生成时校验四舍五入不落在正中间、
照规则写的一份周报不超过字数上限。check.py 只读员工看到的文件另写一遍算法复核。
"""

import json
import random
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENARIO = HERE / "wkr-weekly-report"
DAYS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
# standard name: (aliases, unit, kind, low, high)
METRICS = {
    "新客数": (("新客", "新增客户", "新客户"), "人", "count", 600, 3000),
    "成交额": (("GMV", "销售额"), "元", "count", 60000, 900000),
    "访客数": (("UV", "访客"), "人", "count", 8000, 90000),
    "订单数": (("单量", "订单"), "单", "count", 500, 6000),
    "客单价": (("单均价", "AOV"), "元", "count", 60, 400),
    "转化率": (("支付转化率", "转化"), "%", "rate", 1.0, 9.0),
    "复购率": (("回购率", "复购"), "%", "rate", 8.0, 40.0),
    "退款率": (("退款占比",), "%", "rate", 1.0, 9.0),
    "加购率": (("加购占比", "加购转化"), "%", "rate", 5.0, 25.0),
}
DECIDE = ("要总监拍板", "需要总监决定", "请总监确认")
DECISIONS = [
    ("投放预算被砍 20%", "是否停掉信息流投放"), ("直播间主播临时请假", "是否改成店铺自播"),
    ("大促报名截止在即", "要不要报名 11 月大促"), ("仓库发货延迟两天", "是否给受影响客户发补偿券"),
    ("新品样品到货晚了", "首发日期是否推迟一周"), ("竞品降价 15%", "要不要跟进降价"),
    ("客服人手不够", "是否临时外包夜班客服"), ("会员日预算超了", "是否砍掉会员日赠品"),
]
CONFIRMED = ["已和总监确认双 11 预热节奏", "总监已同意追加短视频预算", "上周提的赠品方案总监已批"]
PLANS = ["下周上线会员日", "下周二做一场直播", "下周上新 3 款秋冬单品", "下周复盘大促报名材料", "下周启动老客召回短信",
         "下周和仓库对一次发货时效", "下周测试新的详情页首图"]
NOISE = ["周一开了选品会，定了 5 款候选", "周二和设计对了 2 版海报", "周三培训新人客服 3 名", "周四整理了竞品价格表",
         "周五清理了 12 条差评回复", "周六值班处理工单 40 张", "周日更新了店铺公告"]

RULES = {
    "R1": {
        "brand": "青禾电商", "sections": ("本周结果", "需要的支持", "下周计划"), "first": "line", "limit": 300,
        "banned": ("赋能", "抓手", "持续推进", "闭环"), "rate_style": "pp", "new_word": "新增", "wan": False,
        "change": lambda sign, value, kind: f"（{sign}{value}{'pp' if kind == 'rate' else '%'}）",
        "text": """# 青禾电商 · 运营周报工作规则

1. 固定三段，顺序和标题不变：“## 本周结果”“## 需要的支持”“## 下周计划”。
2. 第一行（三段之前）是一句话结论。
3. 本周结果里，口径表里的每个指标（本周记录里出现的）都写本周数和环比，例如“新客数 1240 人（+18.1%）”“转化率 3.1%（-0.5pp）”。
4. 不用“赋能”“抓手”“持续推进”“闭环”这四个词。
5. 全文不超过 300 字（字数按字符算，标点算，空格和换行不算）。

补充口径：

- 指标按《指标口径表》的标准名写，数值写成标准单位的完整数字（记录里写“12.4 万”的，写成 124000）。
- 数值类指标写百分比变化（本周 ÷ 上周 − 1），比率类指标写百分点变化（本周 − 上周，写 pp），都保留一位小数，带正负号；计算过程中不取舍，最后再保留。
- 上周周报里没有的指标，不写环比，写“新增”，例如“加购率 12.3%（新增）”。
- 记录里要总监决定的事（写着“要总监拍板”“需要总监决定”“请总监确认”的），都写进“需要的支持”，写清要总监决定什么；已经确认过的不写。
- 记录里下周要做的事都写进“下周计划”。
""",
    },
    "R2": {
        "brand": "木棉电商", "sections": ("进展", "风险与求助", "下周重点"), "first": "prefix", "limit": 320,
        "banned": ("打通", "颗粒度", "对齐", "拉通"), "rate_style": "pp", "new_word": "首周", "wan": True,
        "change": lambda sign, value, kind: f"，较上周 {sign}{value}{'pp' if kind == 'rate' else '%'}",
        "text": """# 木棉电商 · 运营周报工作规则

1. 固定三段，顺序和标题不变：“## 进展”“## 风险与求助”“## 下周重点”。
2. 第一行（三段之前）以“一句话：”开头，写一句结论。
3. 进展里，口径表里的每个指标（本周记录里出现的）都写本周数和变化，写成“指标 本周数，较上周 变化”，例如“新客数 1240 人，较上周 +18.1%”“转化率 3.1%，较上周 -0.5pp”。
4. 不用“打通”“颗粒度”“对齐”“拉通”这四个词。
5. 全文不超过 320 字（字数按字符算，标点算，空格和换行不算）。

补充口径：

- 指标按《指标口径表》的标准名写。数值在 10000 及以上的写成“万”，保留一位小数（例如 124000 元写成“12.4 万元”）；不到 10000 的写完整数字。
- 数值类指标写百分比变化（本周 ÷ 上周 − 1），比率类指标写百分点变化（本周 − 上周，写 pp），都保留一位小数，带正负号；计算过程中不取舍，最后再保留。
- 上周周报里没有的指标，不写变化，写“首周”，例如“加购率 12.3%，首周”。
- 记录里要总监决定的事（写着“要总监拍板”“需要总监决定”“请总监确认”的），都写进“风险与求助”，写清要总监决定什么；已经确认过的不写。
- 记录里下周要做的事都写进“下周重点”。
""",
    },
    "R3": {
        "brand": "北辰电商", "sections": ("结论", "数据", "待决策", "下周"), "first": "section", "limit": 340,
        "banned": ("赋能", "抓手", "打通", "闭环", "对齐"), "rate_style": "words", "new_word": "上周无数据", "wan": False,
        "change": None,
        "text": """# 北辰电商 · 运营周报工作规则

1. 固定四段，顺序和标题不变：“## 结论”“## 数据”“## 待决策”“## 下周”。周报从“## 结论”开始，前面不写别的。
2. “## 结论”只写一句话。
3. “## 数据”里，口径表里的每个指标（本周记录里出现的）都写本周数和变化：数值类写“比上周增长 X%”或“比上周下降 X%”；比率类写“比上周上升 X 个百分点”或“比上周下降 X 个百分点”。
4. 不用“赋能”“抓手”“打通”“闭环”“对齐”这五个词。
5. 全文不超过 340 字（字数按字符算，标点算，空格和换行不算）。

补充口径：

- 指标按《指标口径表》的标准名写，数值写成标准单位的完整数字（记录里写“12.4 万”的，写成 124000）。
- 数值类指标的变化是 本周 ÷ 上周 − 1，比率类是 本周 − 上周，都保留一位小数（不写正负号，用“增长/下降”“上升/下降”表示方向）；计算过程中不取舍，最后再保留。变化正好是 0 的写“与上周持平”。
- 上周周报里没有的指标，不写变化，写“上周无数据”。
- 记录里要总监决定的事（写着“要总监拍板”“需要总监决定”“请总监确认”的），都写进“## 待决策”，写清要总监决定什么；已经确认过的不写。
- 记录里下周要做的事都写进“## 下周”。
""",
    },
}

# name, group, segment, rules, number of metrics, number of new metrics (no baseline), aliases?, wan units?
SPECS = []
for i in range(1, 21):
    rule = "R1" if i % 2 else "R2"
    edge = i > 10
    SPECS.append((f"t{i:02d}", "train", "edge" if edge else "common", rule, 5 + i % 3, 1 + i % 2 if edge else 0, edge, edge))
for i in range(1, 11):
    rule = "R1" if i % 2 else "R2"
    edge = i > 5
    SPECS.append((f"x{i:02d}", "same", "edge" if edge else "common", rule, 5 + (i + 1) % 3, 1 + i % 2 if edge else 0, edge, edge))
for i in range(1, 11):
    edge = i > 5
    SPECS.append((f"y{i:02d}", "new", "edge" if edge else "common", "R3", 5 + (i + 2) % 3, 1 + i % 2 if edge else 0, edge, edge))

TASK = (
    "你是电商公司的运营助理，帮运营组长给总监写周报。工作目录里有这次适用的周报工作规则、这一周的零散记录、上周的周报和"
    "指标口径表。按这次给的工作规则写出这一周的周报，组长会直接发给总监。只输出周报本身。"
)
ONBOARDING = "以后每周写周报，我都会把这次适用的周报工作规则、本周记录、上周周报和指标口径表一起发给你。不同公司总监的要求不一样，以当次给的为准。"
CRITERIA = [
    ("W-numbers", "red_line",
     "指标和变化：本周记录里出现的口径表指标都要写（用标准名），本周数（按规则的单位写法）和变化（按规则的算法、写法、一位小数、"
     "方向）和参考答案一致；上周没有的按规则标注。漏写指标、指标名不是标准名、本周数或变化不对、写法不对，每处记一处"
     "（变化的数值以参考答案的未取舍值四舍五入到一位小数为准）。"),
    ("W-asks", "standard",
     "要总监决定的事：参考答案列出的每一件都写进规则指定的那一段，并写清要总监决定什么；已经确认过的事不写进去。漏写、"
     "写错要决定的内容、把已确认的事写进去，每处记一处。"),
    ("W-plans", "standard",
     "下周计划：参考答案列出的下周要做的事都写进规则指定的那一段；漏一件记一处。"),
    ("W-form", "standard",
     "格式：段数、段名和顺序按规则（每段以“## 段名”开头）；第一行或结论按规则的写法只写一句话；不出现规则禁用的词；"
     "全文字数不超过规则上限（以测量值为准）。每处不符记一处。"),
]


def d(value) -> Decimal:
    return Decimal(str(value))


def one(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)}"


def safe(value: Decimal) -> bool:
    scaled = value * 10
    frac = scaled - scaled.to_integral_value(rounding="ROUND_FLOOR")
    return abs(frac - Decimal("0.5")) >= Decimal("0.05")


def shown_value(name: str, value: Decimal, rule: str) -> str:
    unit, kind = METRICS[name][1], METRICS[name][2]
    if kind == "rate":
        return f"{value}%"
    if RULES[rule]["wan"] and value >= 10000:
        return f"{one(value / 10000)} 万{unit}"
    return f"{value} {unit}"


def change_text(name: str, change: Decimal | None, rule: str) -> str:
    r = RULES[rule]
    kind = METRICS[name][2]
    if change is None:
        return {"R1": "（新增）", "R2": "，首周", "R3": "，上周无数据"}[rule]
    if rule == "R3":
        size = one(abs(change))
        if Decimal(size) == 0:
            return "，与上周持平"
        if kind == "rate":
            return f"，比上周{'上升' if change > 0 else '下降'} {size} 个百分点"
        return f"，比上周{'增长' if change > 0 else '下降'} {size}%"
    sign = "+" if change > 0 else "-"
    return r["change"](sign, one(abs(change)), kind)


def build(spec, rng):
    name, group, segment, rule, n_metrics, n_new, aliases, wan = spec
    names = rng.sample(list(METRICS), n_metrics)
    new = set(names[:n_new])
    rows = {}
    for metric in names:
        aliases_, unit, kind, low, high = METRICS[metric]
        if kind == "rate":
            last = d(round(rng.uniform(low, high), 1))
            now = (last + d(round(rng.uniform(-1.8, 1.8), 1))).quantize(Decimal("0.1"))
            if now <= 0:
                now = last + d("0.4")
        else:
            last = d(int(rng.uniform(low, high)))
            now = d(int(last * d(round(rng.uniform(0.78, 1.28), 3))))
            if metric in ("成交额", "访客数"):
                last, now = (last // 100) * 100, (now // 100) * 100
        rows[metric] = {"now": now, "last": None if metric in new else last}
    return names, rows


def notes_text(spec, rng, names, rows) -> tuple[str, list, list]:
    name, group, segment, rule, n_metrics, n_new, aliases, wan = spec
    lines, asks, plans = [], [], []
    for metric in names:
        aliases_, unit, kind, low, high = METRICS[metric]
        label = rng.choice(aliases_) if aliases and rng.random() < 0.7 else metric
        value = rows[metric]["now"]
        if kind == "rate":
            said = f"{value}%"
        elif wan and value >= 10000 and rng.random() < 0.8:
            said = f"{(value / 10000).normalize():f} 万"
        else:
            said = f"{value}"
        lines.append(f"{rng.choice(DAYS[2:5])}汇总：本周{label} {said}")
    for situation, question in rng.sample(DECISIONS, rng.randint(1, 3)):
        phrase = rng.choice(DECIDE)
        lines.append(f"{rng.choice(DAYS)}：{situation}，{phrase}{question}")
        asks.append(question)
    lines.append(f"{rng.choice(DAYS)}：{rng.choice(CONFIRMED)}")
    for plan in rng.sample(PLANS, rng.randint(1, 3)):
        lines.append(f"{rng.choice(DAYS)}：{plan}")
        plans.append(plan)
    lines += rng.sample(NOISE, rng.randint(3, 6))
    filler = ["和产品确认了下周的需求排期", "整理了本周用户反馈", "同步了大促报名进度", "更新了日报模板", "检查了商品库存预警"]
    while len(lines) < rng.randint(20, 26):
        lines.append(f"{rng.choice(DAYS)}：{rng.choice(filler)}")
    rng.shuffle(lines)
    return "\n".join(["# 本周零散记录", ""] + [f"- {line}" for line in lines]) + "\n", asks, plans


def last_week_text(spec, rng, names, rows) -> str:
    name, group, segment, rule, n_metrics, n_new, aliases, wan = spec
    bits = []
    for metric in names:
        last = rows[metric]["last"]
        if last is None:
            continue
        aliases_, unit, kind, low, high = METRICS[metric]
        label = rng.choice(aliases_) if aliases and rng.random() < 0.5 else metric
        bits.append(f"{label} {last}{'%' if kind == 'rate' else ' ' + unit}")
    extra = rng.choice([m for m in METRICS if m not in names])
    aliases_, unit, kind, low, high = METRICS[extra]
    value = d(round(rng.uniform(low, high), 1)) if kind == "rate" else d(int(rng.uniform(low, high)))
    bits.append(f"{extra} {value}{'%' if kind == 'rate' else ' ' + unit}")
    rng.shuffle(bits)
    return "# 上周周报（节选）\n\n本周结果：" + "；".join(bits) + "。\n"


def catalog_text() -> str:
    lines = ["# 指标口径表", "", "| 标准名 | 别名 | 标准单位 | 类型 |", "|---|---|---|---|"]
    for metric, (aliases_, unit, kind, low, high) in METRICS.items():
        lines.append(f"| {metric} | {'、'.join(aliases_)} | {unit} | {'比率类' if kind == 'rate' else '数值类'} |")
    return "\n".join(lines) + "\n"


def compute(spec, names, rows, asks, plans) -> tuple[dict, str]:
    name, group, segment, rule, n_metrics, n_new, aliases, wan = spec
    r = RULES[rule]
    metrics, lines = {}, []
    for metric in names:
        kind = METRICS[metric][2]
        now, last = rows[metric]["now"], rows[metric]["last"]
        if last is None:
            change = None
        elif kind == "rate":
            change = now - last
        else:
            change = (now / last - 1) * 100
        if change is not None:
            assert safe(change), (name, metric, change)
            assert one(abs(change)) != "0.0" or rule == "R3", (name, metric)
        if r["wan"] and kind == "count" and now >= 10000:
            assert safe(now / 1000), (name, metric, now)
        line = f"{metric} {shown_value(metric, now, rule)}{change_text(metric, change, rule)}"
        lines.append(line)
        metrics[metric] = {
            "本周数（规则写法）": shown_value(metric, now, rule), "上周数": "没有（上周周报里没有这个指标）" if last is None
            else (f"{last}%" if kind == "rate" else f"{last} {METRICS[metric][1]}"),
            "类型": "比率类" if kind == "rate" else "数值类",
            "变化（未取舍）": "—" if change is None else f"{change.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)}{'pp' if kind == 'rate' else '%'}",
            "该写": line,
        }
    sections = r["sections"]
    if rule == "R3":
        sample = [f"## {sections[0]}", "本周指标有升有降，需要总监定几件事。", f"## {sections[1]}", "；".join(lines),
                  f"## {sections[2]}", "；".join(f"请总监决定{a}" for a in asks), f"## {sections[3]}", "；".join(plans)]
    else:
        head = "一句话：本周指标有升有降，需要总监定几件事。" if r["first"] == "prefix" else "本周指标有升有降，需要总监定几件事。"
        sample = [head, f"## {sections[0]}", "；".join(lines), f"## {sections[1]}", "；".join(f"请总监决定{a}" for a in asks),
                  f"## {sections[2]}", "；".join(plans)]
    text = "\n".join(sample)
    size = len("".join(text.split()))
    assert size <= r["limit"] - 20, (name, size, r["limit"])
    reference = {
        "规则集": f"{rule}（{r['brand']}）",
        "指标": metrics,
        "要总监决定的事（都要写）": asks,
        "已经确认过、不能写进去的事": "记录里写着“已和总监确认”“总监已同意”“总监已批”的那一条",
        "下周要做的事（都要写）": plans,
        "段落": "、".join(f"## {s}" for s in sections),
        "禁用词": list(r["banned"]),
        "字数上限": r["limit"],
        "一份照规则写的示例（只作参考，措辞不唯一）": text,
    }
    return reference, text


def scenario_package():
    (SCENARIO / "personas").mkdir(parents=True, exist_ok=True)
    (SCENARIO / "profile.md").write_text(TASK + "\n")
    (SCENARIO / "onboarding.md").write_text(ONBOARDING + "\n")
    (SCENARIO / "personas" / "lead.md").write_text("运营组长发来一周的记录要写周报；每道题的记录、上周周报和规则由脚本给出。\n")
    (SCENARIO / "scenario.json").write_text(json.dumps({
        "initial": [],
        "criteria": [{"id": i, "check": text, "severity": severity} for i, severity, text in CRITERIA],
    }, ensure_ascii=False, indent=1) + "\n")
    visible = ["counterpart", "analyst", "curator"]
    (SCENARIO / "contract.json").write_text(json.dumps(
        {"checks": {i: {"visibility": visible} for i, _, _ in CRITERIA}}, ensure_ascii=False, indent=1) + "\n")


def main():
    names_ = [spec[0] for spec in SPECS]
    assert len(names_) == len(set(names_)) == 40
    (HERE / "rules").mkdir(exist_ok=True)
    for rule, r in RULES.items():
        (HERE / "rules" / f"{rule}.md").write_text(r["text"])
    bank, scripts, retries = [], [], []
    for spec in SPECS:
        name, group, segment, rule = spec[:4]
        for salt in range(80):
            rng = random.Random(f"{name}:{salt}")
            names, rows = build(spec, rng)
            notes, asks, plans = notes_text(spec, rng, names, rows)
            last = last_week_text(spec, rng, names, rows)
            try:
                reference, _ = compute(spec, names, rows, asks, plans)
                break
            except AssertionError as exc:
                retries.append((name, salt, str(exc)[:100]))
        else:
            raise RuntimeError(f"{name}: no seed passes the checks")
        files = {"工作规则.md": RULES[rule]["text"], "本周记录.md": notes, "上周周报.md": last, "指标口径表.md": catalog_text()}
        text = ("组长：这周的记录、上周的周报都在工作目录了，帮我写本周周报。\n\n这次适用的周报工作规则和材料在工作目录："
                "工作规则.md、本周记录.md、上周周报.md、指标口径表.md。")
        bank.append({"name": name, "group": group, "segment": segment, "rules": rule, "text": text, "files": files,
                     "reference": reference})
        label = {"train": "培养", "same": "考试·同规则", "new": "考试·新规则"}[group]
        scripts.append({"name": name, "title": f"{name} · {label} · {RULES[rule]['brand']}", "exam": group != "train",
                        "steps": [{"text": text, "files": files}]})
    (HERE / "questions.json").write_text(json.dumps(bank, ensure_ascii=False, indent=1) + "\n")
    (HERE / "scripts.json").write_text(json.dumps(scripts, ensure_ascii=False, indent=1) + "\n")
    scenario_package()
    print(f"{len(bank)} questions, {len(retries)} seed retries, scenario at {SCENARIO.name}")


if __name__ == "__main__":
    main()
