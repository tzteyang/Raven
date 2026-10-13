"""生成简历优化的三套工作规则、40 题、参考答卷及 Raven 场景包。

uv run python make.py
只使用标准库；事实、原简历、JD 随题交付，参考答案不交给员工。
"""

import csv
import io
import json
import random
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENARIO = HERE / "wkr-resume-rewrite"
RULES = {
    "R1": {"advisor": "青禾求职咨询", "section": "改前改后", "columns": ["条目", "改前", "改后"], "limit": 8,
           "team": "带 {n} 人小组", "sources": False, "confirmed": False},
    "R2": {"advisor": "行远职业顾问", "section": "经历重写", "columns": ["原编号", "原句", "新句"], "limit": 6,
           "team": "协调 {n} 人项目组", "sources": False, "confirmed": False},
    "R3": {"advisor": "星桥求职工作室", "section": "定稿对照", "columns": ["条目", "原句", "改写", "事实出处"], "limit": 5,
           "team": "负责 {n} 人内容小组的排期", "sources": True, "confirmed": True},
}
NAMES = "林予安 陈知夏 周星禾 沈亦宁 唐书宁 陆清和 许明澄 何嘉树 宋思言 谢云舒 苏予晴 叶景行 顾云溪 林嘉悦 白承宇 梁映雪 夏星野 温予初 程以宁 罗晓川 江思齐 赵嘉宁 韩景初 余曼青 姜若舟 杜晴川 方亦可 魏知远 袁若溪 丁书禾 孟一诺 邵明川 康予然 郑庭安 严星河 施雨棠 陶知遥 秦若楠 侯清越 乔嘉木".split()
BRANDS = ["栖山户外", "禾序家居", "橙屿文创", "蓝谷烘焙", "微光阅读", "藤野园艺", "见山旅行", "拾光摄影"]
SCHOOLS = ["浙江传媒学院", "南京晓庄学院", "成都大学", "浙江工商大学", "湖南工商大学"]
KEYWORDS = ["内容增长", "内容策划", "A/B测试", "项目协作", "活动运营"]
ABSENT = ["SEO", "SEM", "SQL", "付费投放", "预算管理", "用户研究"]
HEAD = ["事实编号", "条目", "所在经历", "项目", "本人动作", "结果事实", "状态", "补充说明"]
TASK = ("你是简历优化顾问。每次收到求职者的完整原简历、经核对的事实表、目标岗位 JD 和本次工作规则。"
        "按当次规则改写指定的工作经历条目，交出改前改后对照。数字和经历以事实表为依据，不凭原简历或 JD 补经历。")
ONBOARDING = ("以后每次都会提供工作规则.md、原简历.md、事实表.csv 和目标岗位.md。请逐次读规则，"
              "在事实边界内优化简历表达和岗位关键词，不把上一位求职者的数字、规则或经历套过来。")
CRITERIA = [
    ("RW-fact", "red_line", "事实与数字：只判改写列。每个新增、错误、推算出来的数字，数值虽相同却换了指标、期间、单位、"
     "范围或约/余限定，以及把尚待核实的结果写成定论，各按一个独立事实记一处。参考答案给出允许的结果及口径，等值写法算同一数。"
     "遗漏应保留的结果只归 RW-writing；JD 关键词问题只归 RW-keyword；个人/团队归属、职责夸大只归 RW-role。"
     "改前列按原文照抄的旧错误不算本项错误。交付表格前后说明不判本项，只在 RW-format 记。"),
    ("RW-writing", "standard", "覆盖与表达：原简历 E1–E5 各有一条改写，保持所属项目；每条都写清本人做了什么（动作及对象）和"
     "结果，并保留该条目所有可用事实行里的结果指标。遗漏整条条目记一处，不再逐个记其遗漏的结果；已有条目中缺本人动作或"
     "漏一个结果指标各记一处；整条没有量化结果只记一处，不再把漏掉的每个结果分别记。错误数值只归 RW-fact，数字写错不等于"
     "没有量化结果。输出条数上限/表头/顺序由 RW-format 判。只判表格改写列，前后说明不判本项。"),
    ("RW-keyword", "standard", "JD 关键词：只在改写列核对。岗位文件列出的关键词，有本人实际工作动作支撑的都应至少出现一次，"
     "无实际工作动作支撑的不能出现（即使写成否定句或学习计划也不能放进改写）。必须沿用岗位文件的关键词原词；每个应写未写或"
     "不该写却写出的关键词记一处，同一关键词重复出现只记一次。上过课、听过同事讲解、看过别人的报告不算实操；不能从职位名"
     "推断经历。事实和参考答案列出支持关系。改前列和前后说明里的词不判本项。"),
    ("RW-role", "standard", "职责与归属：只判改写列。小组条目必须按本次规则的人数与职责固定说法写（数字等值允许，数字周围空格"
     "不限）；协助的工作仍写协助，团队整体成果明确属于团队，不能归成本人的独立成果。出现规则禁用的拔高词也在本项判。"
     "同一条目因同一职责夸大同时违反固定说法和禁词只记一处；人数写错只在 RW-fact 记。不得把别人的动作挪给本人。"
     "改前列和前后说明中的词不判本项。"),
    ("RW-format", "standard", "交付格式：只有规则指定的标题和 Markdown 表格，表头/列数/条目顺序符合规则，原句逐字照抄，"
     "最多条数符合规则。错误表头整体记一处；每个原句抄错记一处；条目顺序错误整体记一处；超过上限记一处。漏条目只由"
     "RW-writing 记，不因相应原句或来源缺失再记。R3 的每一行事实出处须准确列出用于该行的全部可用事实编号，漏写、多写、"
     "错写该行来源合计记一处；R1/R2 不要求出处。前后多余说明不管出现几处只记一处，其中数字、关键词、字数不在其他项重复判。"),
]


def rules_text(rule):
    r = RULES[rule]
    team = r["team"].format(n="N")
    extra = ("只采用事实表中状态为“已确认”的行；状态为“待核实”的行不作简历依据，哪怕数字更好看也不用。"
             "如果同一条目有已确认行和待核实行，就只用已确认行；本次每条条目都有可用的已确认结果。" if r["confirmed"] else
             "采用事实表中的已确认行；本次事实表所有行都已经核对，原简历里的自述不替代事实表。")
    source = ("每行“事实出处”列按编号顺序列出该条目用于改写的全部已确认事实编号，用中文逗号隔开（只有一个时直接写一个）。"
              "不得写别的条目的编号、待核实编号，也不写其他文字。" if r["sources"] else "不增加出处列，也不附核对清单。")
    return "\n".join([
        f"# {r['advisor']} · 简历优化工作规则", "",
        "1. 这次只改写原简历中的 E1–E5，按 E1、E2、E3、E4、E5 的顺序，每条恰好一行，不能合并或省略。"
        "完整简历里的教育、任职时间、岗位名和技能自述供了解背景，不需另改或另写个人总结。",
        "2. 改写的数字、工作动作和成果只能来自事实表。等值写法算同一个数，例如“8.6万”与“86000”、“两人”与“2人”、"
        "“3.6%”与“百分之三点六”；可增减数字与单位之间的空格。不得用表中数字算出新数字：差值、增长率、倍数、人均值均不推算。"
        "但如果事实表直接提供某个比例，就可以原义引用该比例。原简历或 JD 里的数字不是新增数字的依据。",
        "3. 每条改写都写成“本人动作 + 结果”：具体说做了什么及对象，再写对应结果，保留该条目所有可用事实行中的每个结果指标。"
        "改写可以换词，不要求套句型；动作次数和成果指标分别保留。不把单篇最高写成平均，不把累计写成单次，不改所属项目、期间、"
        "指标、单位或范围。“约”“余”不能删除；区间须保留上下限，不能只挑上限，也不能改成精确值。",
        "4. 目标岗位.md 中列出的关键词，只有事实表中的本人实际工作动作能支撑时才用，而且有支撑的关键词都要在改写列至少用一次，"
        "沿用原词（包括英文大小写）。没有实际工作动作支撑的关键词在改写列完全不出现，也不写“未做过某关键词”或学习计划。"
        "看报告、上过课、听同事讲解都不算该领域的实际工作经历；不能靠职位名称猜经历。",
        f"5. 事实表中负责小组排期的那条，固定写“{team}”，N 换成实际人数。数字等值写法和数字周围空格均可，其他字不能换。"
        "其他条目中事实写协助就仍写协助，整体成果要写明是团队成果，不能把它当成本人的独立成果。"
        "改写列禁用“主导”“牵头”“全面负责”“带领团队”四个说法。本次事实没有支持这些职责层级。",
        f"6. {extra}",
        f"7. 只交一段，以“## {r['section']}”开头，下面只放 Markdown 对照表。表头依次为“{'｜'.join(r['columns'])}”。"
        f"最多 {r['limit']} 条改写；改前/原句列须逐字照抄原简历 E1–E5 后面的完整原句，不含 E 编号。{source}"
        "标题、表头、原句和来源不是新写的经历，不拿它们做数字和关键词核对。",
        "8. 不加开场白、结尾说明、评分、建议、文件链接或代码围栏。表格以外多出来的说明只算一次格式问题；"
        "其中的数字、词语不算入改写内容，不据此重复记其他问题。", "",
    ])


def chinese(n):
    digits = "零一二三四五六七八九"
    if n == 0:
        return "零"
    if n >= 10000:
        q, rem = divmod(n, 10000)
        return chinese(q) + "万" + (("零" if rem < 1000 else "") + chinese(rem) if rem else "")
    out, zero = "", False
    for base, unit in ((1000, "千"), (100, "百"), (10, "十"), (1, "")):
        q, n = divmod(n, base)
        if q:
            if zero:
                out += "零"
            out += ("" if base == 10 and q == 1 and not out else digits[q]) + unit
            zero = False
        elif out and n:
            zero = True
    return out


def number(n, style):
    if style == "cn":
        if Decimal(str(n)) == int(n):
            return chinese(int(n))
        whole, frac = str(n).split(".")
        return chinese(int(whole)) + "点" + "".join("零一二三四五六七八九"[int(d)] for d in frac)
    if style == "wan" and n >= 10000:
        return f"{Decimal(n) / 10000:g}万"
    return str(n)


def metric(label, values, unit, style="digits", qualifier="", range_value=False):
    vals = values if isinstance(values, list) else [values]
    printed = [number(v, style) for v in vals]
    if range_value:
        shown = "至".join(printed) + unit
    elif qualifier == "余":
        shown = printed[0] + "余" + unit
    elif unit == "%" and style == "cn":
        shown = "百分之" + printed[0]
    else:
        shown = qualifier + printed[0] + unit
    return {"指标": label, "数值": [str(v) for v in vals], "单位": unit, "限定": "区间" if range_value else qualifier,
            "事实表写法": shown}


def data_for(index, edge, rule):
    rng = random.Random(720031 + index * 313)
    r = RULES[rule]
    brand = BRANDS[index % len(BRANDS)]
    start = rng.randrange(12, 47) * 1000
    end = start + rng.randrange(35, 81) * 1000
    high = rng.randrange(11, 24) * 10000
    articles = rng.randrange(3, 8)
    trials = rng.randrange(31, 67)
    adopted = rng.randrange(5, 11)
    team = 2 + index % 4
    plans = rng.randrange(21, 36)
    questions = rng.randrange(36, 89)
    attendees = rng.randrange(24, 78) * 10
    start_style = "cn" if edge and index % 3 == 0 else ("wan" if edge else "digits")
    end_style = "digits" if edge and index % 2 else ("cn" if edge else "digits")
    jobs = ["J2", "J2", "J2", "J2", "J1"]
    actions = [f"运营{brand}公众号，执行内容增长计划", "开展内容策划，独立完成选题、编辑和推送",
               "设计并执行标题A/B测试，将已采用写法整理进选题模板", "安排小组内容日历并复核交稿，承担项目协作中的排期职责",
               "协助活动运营，负责收集现场提问并整理问答记录；活动总负责人另有其人"]
    blocks = [
        [metric("账号关注人数起点", start, "人", start_style), metric("账号关注人数终点", end, "人", end_style)],
        [metric("单篇最高阅读", high, "次", "wan" if edge else "digits"),
         metric("阅读达到100000次的文章", articles, "篇", "cn" if edge else "digits")],
        [metric("标题A/B测试", [trials, trials + 6] if edge and index % 3 == 0 else trials, "次",
                "cn" if edge and index % 3 == 1 else "digits", "约" if edge and index % 3 == 1 else ("余" if edge else ""),
                range_value=edge and index % 3 == 0), metric("已实际采用的标题写法", adopted, "套")],
        [metric("排期小组人数", team, "人", "cn" if edge else "digits"), metric("已交付月度内容计划", plans, "篇")],
        [metric("本人整理活动问答", questions, "条"), metric("该场团队活动到场人数", attendees, "人")],
    ]
    if index % 2:
        click = Decimal(rng.randrange(21, 67)) / 10
        blocks[0].append(metric("期末菜单点击率", click, "%", "cn" if edge else "digits"))
    fact_rows = []
    for j, metrics in enumerate(blocks):
        notes = ["起点为2023年3月，终点为2025年6月；数值来自账号后台。",
                 "阅读量来自同一账号后台；“达到”含该阈值，最高值不是平均值。",
                 "采用指写法进入后续选题并实际使用；没有记录转化率。",
                 "人数含本人；工作是排期和复核交稿，无招聘、绩效或部门管理职责。",
                 "2021年5月线下读者活动；问答整理是本人产出，到场人数是整个团队的成果。"]
        fact_rows.append({"事实编号": f"F{j+1:02d}", "条目": f"E{j+1}", "所在经历": jobs[j],
                          "项目": [f"{brand}公众号增长", "公众号选题与推送", "标题实验", "内容小组排期", "线下读者活动"][j],
                          "本人动作": actions[j], "结果事实": "；".join(f"{m['指标']}：{m['事实表写法']}" for m in metrics) + "。",
                          "状态": "已确认", "补充说明": notes[j]})
    if r["confirmed"]:
        pending = dict(fact_rows[0])
        pending.update({"事实编号": "F06", "结果事实": f"账号关注人数终点：{end + 17000}人。", "状态": "待核实",
                        "补充说明": "同事口头回忆的数字，尚未与后台核对；不是已确认的更新值。"})
        fact_rows.insert(1, pending)
    unsupported = rng.sample(ABSENT, 2)
    required_keywords = list(KEYWORDS)
    rng.shuffle(required_keywords)
    jd_keywords = required_keywords + unsupported
    rng.shuffle(jd_keywords)
    prior_skill = (f"曾听同事介绍{unsupported[0]}，没有亲自做过；{unsupported[1]}没有项目或工作经历。" if edge else
                   f"{unsupported[0]}和{unsupported[1]}均无实际项目或工作经历。")
    originals = [f"负责{brand}公众号，粉丝增长显著，擅长{unsupported[0]}。",
                 "负责选题和内容制作，多篇文章取得很好的阅读表现。",
                 "尝试优化文章标题，实验很多次，沉淀了一些写法。",
                 "带领团队完成内容规划，全面负责部门管理。",
                 "主导读者活动，独立完成所有工作并吸引大量用户参加。"]
    if edge:
        derived = (Decimal(end - start) / start * 100).quantize(Decimal("0.1"))
        originals[0] = f"负责{brand}公众号，关注人数增长{derived}%，精通{unsupported[0]}。"
        originals[1] = f"内容策划能力突出，平均每篇阅读{number(high, 'wan')}次。"
        originals[2] = f"完成{trials + 6}次标题测试，转化率显著提升。"
    return {"person": NAMES[index], "brand": brand, "facts": fact_rows, "metrics": blocks, "originals": originals,
            "keywords": jd_keywords, "supported": required_keywords, "unsupported": unsupported,
            "prior_skill": prior_skill, "team": team, "start": start, "end": end, "jobs": jobs}


def csv_text(rows):
    out = io.StringIO()
    writer = csv.DictWriter(out, HEAD, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def resume_text(index, d):
    return "\n".join([
        f"# {d['person']} · 原简历", "", "## 基本信息", f"姓名：{d['person']}", "现居城市：杭州", "求职意向：内容增长经理",
        "联系方式：本次未提供。", "", "## 教育背景", f"{SCHOOLS[index % len(SCHOOLS)]}｜广告学｜本科｜2016年9月—2020年6月", "",
        "## 工作经历", f"### J2｜{d['brand']}品牌运营部｜新媒体运营｜2023年1月—2026年9月",
        *[f"E{i+1}：{d['originals'][i]}" for i in range(4)], "",
        "### J1｜青藤文化传播｜活动运营专员｜2020年7月—2022年12月", f"E5：{d['originals'][4]}", "",
        "## 技能自述", f"擅长公众号编辑、内容策划、{d['unsupported'][0]}和{d['unsupported'][1]}。", "",
        "## 补充访谈记录", d["prior_skill"], "说明：这份旧简历由求职者自行整理；经核对的工作动作及数字请以事实表为准。", "",
    ])


def jd_text(d):
    return "\n".join([
        "# 目标岗位：内容增长经理", "", "业务：消费品牌的内容获客与用户沟通。",
        "职责：维护内容日历；根据实验结果优化选题和标题；协调内容交付；配合活动团队整理现场反馈。",
        "要求：有真实可说明的内容项目，能讲清自己的职责与可核验的结果。岗位涉及的能力不要求全部已经具备。", "",
        "## 岗位关键词", *[f"- {word}" for word in d["keywords"]], "",
        "请按本次工作规则判断哪些关键词有事实支撑。JD 是目标要求，不是求职者已经拥有的经验。", "",
    ])


def rewritten(rule, d):
    m = [[v["事实表写法"] for v in metrics] for metrics in d["metrics"]]
    text = [f"运营{d['brand']}公众号并执行内容增长计划，账号关注人数从{m[0][0]}增至{m[0][1]}。",
            f"开展内容策划，完成选题、编辑和推送，单篇最高阅读{m[1][0]}，阅读达到100000次的文章有{m[1][1]}。",
            f"执行标题A/B测试{m[2][0]}，整理实验结论，已有{m[2][1]}标题写法进入后续选题并被实际采用。",
            f"{RULES[rule]['team'].format(n=m[3][0].removesuffix('人'))}，安排内容日历并复核交稿，落实项目协作，交付月度内容计划{m[3][1]}。",
            f"协助活动运营，收集现场提问并整理活动问答{m[4][0]}，该场团队活动到场人数为{m[4][1]}。"]
    if len(m[0]) == 3:
        text[0] = text[0][:-1] + f"，期末菜单点击率为{m[0][2]}。"
    return text


def table(rule, originals, after, sources=None):
    r = RULES[rule]
    lines = [f"## {r['section']}", "", "| " + " | ".join(r["columns"]) + " |", "| " + " | ".join(["---"] * len(r["columns"])) + " |"]
    for i, (before, new) in enumerate(zip(originals, after)):
        cells = [f"E{i+1}", before, new]
        if r["sources"]:
            cells.append((sources or [f"F{n:02d}" for n in range(1, 6)])[i])
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def reference(rule, d):
    rows = []
    for i, metrics in enumerate(d["metrics"]):
        f = next(f for f in d["facts"] if f["条目"] == f"E{i+1}" and f["状态"] == "已确认")
        rows.append({"条目": f"E{i+1}", "原句": d["originals"][i], "所在经历": d["jobs"][i], "项目": f["项目"],
                     "本人动作": f["本人动作"], "保留的结果": metrics, "事实出处": [f["事实编号"]], "归属补充": f["补充说明"]})
    return {"适用规则": rule, "逐条依据": rows,
            "应使用的关键词": sorted(d["supported"]), "不得进入改写的关键词": sorted(d["unsupported"]),
            "职责固定说法": RULES[rule]["team"].format(n=d["team"]),
            "团队成果归属": "E5 的到场人数是团队整体成果；本人只是协助活动并整理问答，不得写独立完成或主导活动。",
            "待核实不用的事实": [f["事实编号"] for f in d["facts"] if f["状态"] != "已确认"],
            "来源栏": "每条写其全部已确认事实编号" if RULES[rule]["sources"] else "不要求且不增加该列",
            "注意": "示例只是可行写法；按规则自由改写，数字等值算对。事实表已有的百分比可用，推算的新百分比不可用。"
                    "复制在原句列的夸大、未做过的关键词、错误或推算数字不判为改写错误。",
            "一种合规交付": table(rule, d["originals"], rewritten(rule, d))}


def package():
    (SCENARIO / "personas").mkdir(parents=True, exist_ok=True)
    (SCENARIO / "profile.md").write_text("# 简历优化顾问\n\n" + TASK + "\n")
    (SCENARIO / "onboarding.md").write_text(ONBOARDING + "\n")
    (SCENARIO / "personas" / "candidate.md").write_text(
        "# 求职者\n\n你是求职者，会交出完整原简历、事实表、目标岗位和这次工作规则，请顾问在事实边界内改写指定工作经历。"
        "不要额外给事实表没有的数字或实操经历。\n")
    (SCENARIO / "scenario.json").write_text(json.dumps({"initial": [], "criteria": [
        {"id": key, "severity": severity, "check": check} for key, severity, check in CRITERIA]}, ensure_ascii=False, indent=2) + "\n")
    (SCENARIO / "contract.json").write_text(json.dumps({"checks": {
        key: {"visibility": ["counterpart", "analyst", "curator"]} for key, *_ in CRITERIA}}, ensure_ascii=False, indent=2) + "\n")
    (HERE / "manifest.json").write_text(json.dumps({"name": "简历优化", "description": TASK,
        "owns": "依据事实表与本次工作规则改写求职简历，核对数字、职责归属和岗位关键词，并提供改前改后对照。"}, ensure_ascii=False, indent=2) + "\n")


def main():
    (HERE / "rules").mkdir(parents=True, exist_ok=True)
    for rule in RULES:
        (HERE / "rules" / f"{rule}.md").write_text(rules_text(rule))
    questions, scripts, serial = [], [], 0
    for prefix, group, count in (("t", "train", 20), ("x", "same", 10), ("y", "new", 10)):
        for num in range(1, count + 1):
            rule = "R3" if prefix == "y" else ("R1" if num % 2 else "R2")
            edge = num > (10 if prefix == "t" else 5)
            name = f"{prefix}{num:02d}"
            d = data_for(serial, edge, rule)
            assert len(d["facts"]) == (6 if rule == "R3" else 5)
            assert set(d["supported"]).isdisjoint(d["unsupported"])
            assert all(len(row["结果事实"]) < 200 for row in d["facts"])
            assert 5 <= RULES[rule]["limit"]
            if edge:
                assert any(m["限定"] for row in d["metrics"] for m in row)
                assert "增长" in d["originals"][0] and "%" in d["originals"][0]
                assert "平均" in d["originals"][1] and "单篇最高" in d["facts"][2 if rule == "R3" else 1]["结果事实"]
            files = {"工作规则.md": rules_text(rule), "原简历.md": resume_text(serial, d), "事实表.csv": csv_text(d["facts"]),
                     "目标岗位.md": jd_text(d)}
            text = (f"我是{d['person']}，准备投内容增长经理。请按这次工作规则，把完整简历里的 E1–E5 改成可直接使用的经历表述，"
                    "给我改前改后对照。数字、实际做过的事和职责边界请以核对过的事实为准。\n\n"
                    "工作目录已有：工作规则.md、原简历.md、事实表.csv、目标岗位.md。今天是2026年10月11日。")
            questions.append({"name": name, "group": group, "segment": "edge" if edge else "common", "rules": rule,
                              "text": text, "files": files, "reference": reference(rule, d)})
            scripts.append({"name": name, "title": f"{name} · {'培养' if group == 'train' else '考试'} · {d['person']}",
                            "exam": group != "train", "steps": [{"text": text, "files": files}]})
            serial += 1
    assert len({q["files"]["事实表.csv"] for q in questions}) == 40
    (HERE / "questions.json").write_text(json.dumps(questions, ensure_ascii=False, indent=1) + "\n")
    (HERE / "scripts.json").write_text(json.dumps(scripts, ensure_ascii=False, indent=1) + "\n")
    package()
    print(f"{len(questions)} questions; unique facts: 40; scenario: {SCENARIO.name}")


if __name__ == "__main__":
    main()
