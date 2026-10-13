"""需求追问清单：三套工作规则、40 道题（20 培养 + 10 道同规则考试 + 10 道换规则考试）、参考答案和 Studio 场景包。

  python3 make.py

依据《专家自进化》10.2 的案例改写成「工作规则随题交给员工」：三家 SaaS 公司的销售明天要和客户做第一次需求沟通，要一份追问
清单。口径不同（各类问题的数量要求、必问的事、清单格式和题数上限、结尾写法）。培养题和同规则考试题用 R1（牙易约，卖给连锁
口腔诊所）、R2（课满满，卖给连锁培训机构）交替，换规则考试题全用员工从没见过的 R3（店小二，卖给连锁餐饮和零售：按类别顺序
排、一题只问一件事）。每题一条线索按种子生成：常见题线索里的已知信息写成字段，和人会问的说法一样；边界题已知信息藏在表单留言
和公开信息里、换了说法（“十二家”“门店规模”），留言里还带着容易顺口问的事。参考答案写出哪些是已知信息（以及换了说法也算的问法）、
必问的事各属哪一类、数量要求，并附一份照规则写的清单；check.py 只读员工看到的文件另算一遍。
"""

import json
import random
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENARIO = HERE / "wkr-discovery-coach"
CN = "零一二三四五六七八九十"

CATEGORY_TEXT = """- 类别只有四种，按问题问的是什么来定：
  - 背景：问现状事实（人员多少、流程怎么走、在用什么系统），以及谁拍板、预算、采购流程。
  - 难点：问现在遇到什么问题、问题本身有多频繁或多严重（问题发生的次数、比率，例如爆约率、续费率、巡检发现的问题数）、现在的办法哪里不够。
  - 影响：问问题造成的损失（多花的钱、时间、人力，流失的客户，错过的收入）。
  - 需求回报：问解决之后希望达到什么、为什么现在要解决。"""
CLOSED_TEXT = """- 封闭问法指只能用“是”或“否”回答的问题：带“是不是”“对不对”“有没有”“是否”“能否”“可否”“会不会”“要不要”“能不能”“行不行”，或者以“吗”结尾的问题，都算封闭问法。"""
KNOWN_TEXT = """- 已知信息以《线索》里写到的内容为准（字段、表单留言、公开信息都算）。换了说法问同一件事也算问了已知信息，例如线索写了门店数，问“门店规模”“几家店”“店多不多”都算。"""

RULES = {
    "R1": {
        "seller": "牙易约", "product": "预约与回访系统", "buyer": "连锁口腔诊所", "max": 12, "background": 2,
        "impact": 3, "payoff": 0, "label": "bracket", "closing": "下一步：", "order": False, "single": False,
        "must": [("现在的爆约率", "难点"), ("一个爆约空档损失多少钱", "影响"), ("谁拍板、预算周期是怎样的", "背景"),
                 ("为什么现在要解决", "需求回报")],
        "text": """# 牙易约 · 首次需求沟通追问清单工作规则

销售明天要和客户做第一次需求沟通（30 分钟），要一份追问清单。题面给客户和联系人；工作目录里的《线索》是客户在线索表单里填的内容和公开信息。

1. 不问《线索》里已经有的信息（换了说法也算问了）。
2. 每题标一个类别：背景、难点、影响、需求回报（类别怎么定见补充口径）。背景类不超过 2 题，影响类至少 3 题。
3. 必须问到这四件事：现在的爆约率、一个爆约空档损失多少钱、谁拍板和预算周期是怎样的、为什么现在要解决。
4. 全部用开放式问法，不用封闭问法（见补充口径）。
5. 清单不超过 12 题；清单后面单独一行写这次通话要达成的下一步，写清做什么、什么时候，以“下一步：”开头。

格式：每题一行，写成“序号.【类别】问题”（例如“1.【难点】现在一个月爆约的大概有多少？”），最后一行是“下一步：……”。只交清单和下一步这一行，前后不加别的文字。

补充口径：

""" + CATEGORY_TEXT + "\n" + CLOSED_TEXT + "\n" + KNOWN_TEXT + "\n- 一题可以问一件事，也可以把紧密相关的两件事放在一句里问；必问的四件事各自要在清单里有对应的题。\n",
    },
    "R2": {
        "seller": "课满满", "product": "排课与续费系统", "buyer": "连锁培训机构", "max": 10, "background": 1,
        "impact": 2, "payoff": 2, "label": "paren", "closing": "本次目标：", "order": False, "single": False,
        "must": [("现在的续费率", "难点"), ("流失一个学员损失多少钱", "影响"), ("谁拍板、采购流程是怎样的", "背景"),
                 ("现在的办法哪里不够用", "难点")],
        "text": """# 课满满 · 首次需求沟通追问清单工作规则

销售明天要和客户做第一次需求沟通（30 分钟），要一份追问清单。题面给客户和联系人；工作目录里的《线索》是客户在线索表单里填的内容和公开信息。

1. 不问《线索》里已经有的信息（换了说法也算问了）。
2. 每题标一个类别：背景、难点、影响、需求回报（类别怎么定见补充口径）。背景类不超过 1 题，影响类至少 2 题，需求回报类至少 2 题。
3. 必须问到这四件事：现在的续费率、流失一个学员损失多少钱、谁拍板和采购流程是怎样的、现在的办法哪里不够用。
4. 全部用开放式问法，不用封闭问法（见补充口径）。
5. 清单不超过 10 题；清单后面单独一行写这次通话要达成的目标，写清做什么、什么时候，以“本次目标：”开头。

格式：每题一行，写成“序号. 问题（类别）”（例如“1. 现在学员的续费率大概是多少？（难点）”），最后一行是“本次目标：……”。只交清单和本次目标这一行，前后不加别的文字。

补充口径：

""" + CATEGORY_TEXT + "\n" + CLOSED_TEXT + "\n" + KNOWN_TEXT + "\n- 一题可以问一件事，也可以把紧密相关的两件事放在一句里问；必问的四件事各自要在清单里有对应的题。\n",
    },
    "R3": {
        "seller": "店小二", "product": "门店巡检系统", "buyer": "连锁餐饮和零售", "max": 12, "background": 2,
        "impact": 3, "payoff": 0, "label": "bracket", "closing": "下一步：", "order": True, "single": True,
        "must": [("每个月巡检发现的问题有多少", "难点"), ("一次问题没检查出来损失多少钱", "影响"), ("谁拍板、预算周期是怎样的", "背景"),
                 ("为什么现在要解决", "需求回报")],
        "text": """# 店小二 · 首次需求沟通追问清单工作规则

销售明天要和客户做第一次需求沟通（30 分钟），要一份追问清单。题面给客户和联系人；工作目录里的《线索》是客户在线索表单里填的内容和公开信息。

1. 不问《线索》里已经有的信息（换了说法也算问了）。
2. 每题标一个类别：背景、难点、影响、需求回报（类别怎么定见补充口径）。背景类不超过 2 题，影响类至少 3 题。
3. 必须问到这四件事：每个月巡检发现的问题有多少、一次问题没检查出来损失多少钱、谁拍板和预算周期是怎样的、为什么现在要解决。
4. 全部用开放式问法，不用封闭问法（见补充口径）。
5. 清单不超过 12 题；清单后面单独一行写这次通话要达成的下一步，写清做什么、什么时候，以“下一步：”开头。
6. 清单按类别排：先全部背景题，再难点题，再影响题，最后需求回报题。
7. 一题只问一件事：每题只有一个问号，不用“和”“以及”“还有”把两个问题连成一句。

格式：每题一行，写成“序号.【类别】问题”（例如“1.【难点】现在每个月巡检能发现多少问题？”），最后一行是“下一步：……”。只交清单和下一步这一行，前后不加别的文字。

补充口径：

""" + CATEGORY_TEXT + "\n" + CLOSED_TEXT + "\n" + KNOWN_TEXT + "\n",
    },
}

# 每套规则的客户、可能出现在线索里的已知信息（字段名、值、换了说法的问法）
LEADS = {
    "R1": {
        "companies": ["笑颜口腔", "皓齿口腔", "贝洁齿科", "康美口腔", "微笑牙科"],
        "titles": ["运营副总裁", "运营总监", "客服负责人"],
        "facts": [
            ("门店数", lambda r: f"{r.randint(8, 18)} 家", ["门店数", "几家店", "门店规模", "多少家门店"]),
            ("今年新开门店", lambda r: f"{r.randint(2, 5)} 家", ["新开", "开了几家", "扩张"]),
            ("现在用的预约工具", lambda r: r.choice(["Excel", "微信群接龙", "纸质预约本"]), ["用什么工具", "用什么系统", "怎么排预约", "预约工具"]),
            ("前台人数（每店）", lambda r: f"{r.randint(2, 4)} 人", ["前台几个人", "前台人数", "前台配置"]),
        ],
        "pain": "爆约的病人太多，前台追不过来",
    },
    "R2": {
        "companies": ["启明教育", "乐学少儿编程", "星海美术", "博雅英语", "跃动体能"],
        "titles": ["校长", "运营总监", "教务负责人"],
        "facts": [
            ("校区数", lambda r: f"{r.randint(5, 14)} 个", ["校区数", "几个校区", "校区规模", "多少个校区"]),
            ("在读学员", lambda r: f"{r.randint(8, 30) * 100} 人", ["多少学员", "学员规模", "在读人数"]),
            ("现在排课的方式", lambda r: r.choice(["Excel", "老师各自用微信排", "纸质课表"]), ["怎么排课", "用什么工具", "用什么系统", "排课方式"]),
            ("教务人数", lambda r: f"{r.randint(3, 8)} 人", ["教务几个人", "教务人数", "教务配置"]),
        ],
        "pain": "续费季学员流失多，教务排课改课忙不过来",
    },
    "R3": {
        "companies": ["老街面馆", "鲜果到家", "一品烧烤", "邻家便利", "蜀香火锅"],
        "titles": ["运营总监", "品控负责人", "督导经理"],
        "facts": [
            ("门店数", lambda r: f"{r.randint(15, 60)} 家", ["门店数", "几家店", "门店规模", "多少家门店"]),
            ("督导人数", lambda r: f"{r.randint(3, 9)} 人", ["督导几个人", "督导人数", "督导配置"]),
            ("现在的巡检方式", lambda r: r.choice(["纸质检查表", "微信群拍照打卡", "Excel 表格"]), ["怎么巡检", "用什么工具", "用什么系统", "巡检方式"]),
            ("巡检频率", lambda r: r.choice(["每月一次", "每两周一次", "每周一次"]), ["多久巡检一次", "巡检频率", "多久去一次"]),
        ],
        "pain": "门店卫生和陈列问题总是事后才发现，督导跑不过来",
    },
}

# 已知信息藏进表单留言时的自然说法（{v} 是值，数字已换成中文）
SAID = {
    "门店数": "我们{v}店", "今年新开门店": "今年又新开了{v}", "现在用的预约工具": "现在用{v}排预约",
    "前台人数（每店）": "每家店前台就{v}", "校区数": "我们有{v}校区", "在读学员": "在读学员{v}",
    "现在排课的方式": "现在排课是{v}", "教务人数": "教务就{v}", "督导人数": "督导只有{v}",
    "现在的巡检方式": "现在巡检用的是{v}", "巡检频率": "督导{v}巡店",
}

SPECS = []
for i in range(1, 21):
    SPECS.append((f"t{i:02d}", "train", "edge" if i > 10 else "common", "R1" if i % 2 else "R2"))
for i in range(1, 11):
    SPECS.append((f"x{i:02d}", "same", "edge" if i > 5 else "common", "R1" if i % 2 else "R2"))
for i in range(1, 11):
    SPECS.append((f"y{i:02d}", "new", "edge" if i > 5 else "common", "R3"))

TASK = (
    "你是 SaaS 公司的销售助理。销售明天要和客户做第一次需求沟通，你根据这次适用的追问清单工作规则和客户线索，写一份追问清单，"
    "销售会直接照着问。工作目录里有工作规则和线索。只输出规则要求的内容。"
)
ONBOARDING = "以后每次首次沟通前，我都会把这次适用的追问清单工作规则和客户线索一起发给你。不同公司的口径不一样，以当次给的为准。"
CRITERIA = [
    ("K-known", "red_line",
     "已知信息：清单里没有一题在问《线索》里已经有的信息（字段、表单留言、公开信息都算，换了说法也算，参考答案列出了已知信息和"
     "会被算作问它的说法）。每问一题已知信息记一处。只判清单本身，清单前后多出来的文字归 K-format。"),
    ("K-must", "standard",
     "必问的事：规则列的四件事，每件都有一题在问（措辞可以不同，意思要对上）；漏一件记一处。"),
    ("K-mix", "standard",
     "类别：每题标的类别要符合补充口径的定义（标错一题记一处），并满足规则的数量要求（背景类上限、影响类和需求回报类下限，按正确的"
     "类别数，测量值给了按员工标注数出来的各类题数），不满足的每条记一处。"),
    ("K-open", "standard",
     "开放式问法：没有封闭问法（补充口径列了算封闭的写法，测量值逐题标了可疑写法，由你判断）；规则要求一题只问一件事的，问了两件事"
     "的每题记一处。每处记一处。"),
    ("K-format", "standard",
     "格式：题数不超过上限；每题按规则的写法标类别；最后单独一行是规则要求开头的下一步或目标，写清做什么、什么时候；规则要求按类别"
     "顺序排的要排对；清单前后加了说明、标题之类的文字，不管几处只记一处。每处不符记一处。"),
]


def chinese(number: int) -> str:
    if number < 10:
        return CN[number]
    if number < 20:
        return "十" + (CN[number - 10] if number > 10 else "")
    return CN[number // 10] + "十" + (CN[number % 10] if number % 10 else "")


def build(spec, rng):
    name, group, segment, rule = spec
    edge = segment == "edge"
    lead = LEADS[rule]
    company = rng.choice(lead["companies"])
    title = rng.choice(lead["titles"])
    surname = rng.choice("王张刘陈杨黄周吴徐孙马朱胡郭何林")
    facts = rng.sample(lead["facts"], 3 if not edge else 4)
    values = [(field, make(rng), asks) for field, make, asks in facts]
    if edge:
        # 边界题：一部分已知信息不写成字段，藏进表单留言或公开信息，数字写成中文
        as_fields = values[:1]
        hidden = values[1:]
    else:
        as_fields, hidden = values, []
    form = lead["pain"]
    public = []
    for field, value, asks in hidden:
        shown = value
        m = re.match(r"(\d+) (家|个|人)$", value)
        if m and int(m.group(1)) < 100:
            number = int(m.group(1))
            shown = ("两" if number == 2 else chinese(number)) + ("个人" if m.group(2) == "人" else m.group(2))
        if rng.random() < 0.5:
            form += "；" + SAID[field].format(v=shown)
        else:
            public.append(f"{field}：{shown}")
    lead_doc = {
        "公司": company,
        "联系人": f"{surname}{rng.choice(['先生', '女士'])}（{title}）",
        "表单字段": {field: value for field, value, _ in as_fields},
        "表单留言": form + "。",
        "公开信息（公众号、官网）": public or ["无"],
    }
    return {"company": company, "title": title, "surname": surname, "lead": lead_doc,
            "known": [(field, value, asks) for field, value, asks in values]}


def label(rule: str, category: str, question: str, index: int) -> str:
    if RULES[rule]["label"] == "bracket":
        return f"{index}.【{category}】{question}"
    return f"{index}. {question}（{category}）"


EXTRA = {
    "R1": {
        "背景": ["现在一个爆约的病人，前台一般会怎么跟进？"],
        "难点": ["前台追爆约时，最费劲的是哪一步？"],
        "影响": ["前台每天花在打电话追病人上的时间大概有多少？", "爆约的病人里，后来流失到别家的大概占多少？"],
        "需求回报": ["如果爆约率降下来，您最希望先看到哪方面的变化？"],
    },
    "R2": {
        "背景": ["现在续费提醒一般由谁来跟进？"],
        "难点": ["续费季最让教务头疼的是哪件事？"],
        "影响": ["教务每周花在改课调课上的时间大概有多少？"],
        "需求回报": ["如果续费率提上来，您最希望先改善哪件事？", "要是排课改课不再占教务的时间，您打算让他们把精力放在哪里？"],
    },
    "R3": {
        "背景": ["现在一次巡检的结果一般怎么汇总给总部？"],
        "难点": ["督导巡店时，最难盯住的是哪类问题？"],
        "影响": ["督导每个月花在路上的时间大概有多少？", "被顾客投诉卫生问题之后，那家店的生意一般会受多大影响？"],
        "需求回报": ["如果问题能当天发现，您最希望先改善哪件事？"],
    },
}
MUST_Q = {
    "现在的爆约率": "现在一个月里爆约的病人大概占预约的多少？",
    "一个爆约空档损失多少钱": "一个爆约空出来的诊位，大概会损失多少收入？",
    "谁拍板、预算周期是怎样的": "这类系统一般由谁拍板，预算是按什么周期定的？",
    "为什么现在要解决": "为什么选在现在来解决爆约这件事？",
    "现在的续费率": "现在学员到期后的续费率大概是多少？",
    "流失一个学员损失多少钱": "流失一个学员，对校区来说大概损失多少钱？",
    "谁拍板、采购流程是怎样的": "这类系统一般由谁拍板，采购要走怎样的流程？",
    "现在的办法哪里不够用": "现在排课和续费跟进的办法，哪里最不够用？",
    "每个月巡检发现的问题有多少": "现在每个月巡检大概能发现多少问题？",
    "一次问题没检查出来损失多少钱": "一次问题没检查出来，最后大概会损失多少钱？",
}
R3_MUST_Q = {"谁拍板、预算周期是怎样的": "这类系统一般由谁拍板？", "为什么现在要解决": "为什么选在现在来解决巡检这件事？"}


def example(rule: str, data: dict) -> str:
    r = RULES[rule]
    rows = []
    for item, category in r["must"]:
        question = R3_MUST_Q.get(item, MUST_Q[item]) if rule == "R3" else MUST_Q[item]
        rows.append((category, question))
    if rule == "R3":
        rows.append(("背景", "预算一般是按什么周期定的？"))
    counts = {c: sum(1 for cat, _ in rows if cat == c) for c in ("背景", "难点", "影响", "需求回报")}
    for category, need in (("影响", r["impact"]), ("需求回报", r["payoff"])):
        for question in EXTRA[rule][category]:
            if counts[category] >= need:
                break
            rows.append((category, question))
            counts[category] += 1
    rows.append(("难点", EXTRA[rule]["难点"][0]))
    order = ["背景", "难点", "影响", "需求回报"]
    if r["order"]:
        rows.sort(key=lambda row: order.index(row[0]))
    lines = [label(rule, category, question, index) for index, (category, question) in enumerate(rows, 1)]
    step = {"R1": "约下周三下午和您、运营负责人一起看 20 分钟的爆约提醒演示。",
            "R2": "约下周二晚上和您、教务负责人一起看一次续费提醒和排课演示。",
            "R3": "约下周四上午和您、品控负责人一起看一次巡检演示。"}[rule]
    lines.append(r["closing"] + step)
    return "\n".join(lines)


CLOSED = re.compile(r"是不是|对不对|有没有|是否|能否|可否|会不会|要不要|能不能|行不行|吗[？?]?$")


def check_example(rule: str, data: dict, text: str) -> None:
    r = RULES[rule]
    lines = text.splitlines()
    questions = lines[:-1]
    assert lines[-1].startswith(r["closing"])
    assert len(questions) <= r["max"], len(questions)
    cats = [re.search(r"【(.+?)】|（(背景|难点|影响|需求回报)）$", q).group(1) or re.search(r"（(.+?)）$", q).group(1) for q in questions]
    assert cats.count("背景") <= r["background"] and cats.count("影响") >= r["impact"] and cats.count("需求回报") >= r["payoff"], cats
    for q in questions:
        body = re.sub(r"^\d+\.\s*(【.+?】)?", "", q)
        body = re.sub(r"（(背景|难点|影响|需求回报)）$", "", body)
        assert not CLOSED.search(body), q
        if r["single"]:
            assert body.count("？") == 1 and "和" not in body and "以及" not in body and "还有" not in body, q
        for field, value, asks in data["known"]:
            assert not any(a in body for a in asks), (q, field)
    if r["order"]:
        order = ["背景", "难点", "影响", "需求回报"]
        assert cats == sorted(cats, key=order.index), cats


def reference(spec, data, text) -> dict:
    name, group, segment, rule = spec
    r = RULES[rule]
    return {
        "规则集": f"{rule}（{r['seller']}）",
        "已知信息（不能问，换了说法也算）": [
            {"信息": field, "线索里写的": value, "这些问法都算问了它（举例）": asks} for field, value, asks in data["known"]],
        "必问的事和它们的类别": [{"事": item, "类别": category} for item, category in r["must"]],
        "数量要求": {"题数上限": r["max"], "背景类最多": r["background"], "影响类至少": r["impact"],
                   "需求回报类至少": r["payoff"] or "规则没要求"},
        "按类别顺序排": "要（背景→难点→影响→需求回报）" if r["order"] else "规则没要求",
        "一题只问一件事": "要（每题一个问号，不用“和”“以及”“还有”连两个问题）" if r["single"] else "规则没要求",
        "结尾一行": f"以“{r['closing']}”开头，写清做什么、什么时候",
        "题目写法": "序号.【类别】问题" if r["label"] == "bracket" else "序号. 问题（类别）",
        "一份照规则写的清单（措辞可以不同）": text,
    }


def lead_text(data) -> str:
    return "# 线索\n\n```json\n" + json.dumps(data["lead"], ensure_ascii=False, indent=2) + "\n```\n"


def scenario_package():
    (SCENARIO / "personas").mkdir(parents=True, exist_ok=True)
    (SCENARIO / "profile.md").write_text(TASK + "\n")
    (SCENARIO / "onboarding.md").write_text(ONBOARDING + "\n")
    (SCENARIO / "personas" / "sales.md").write_text("销售明天要做首次需求沟通，要一份追问清单；每道题的线索和规则由脚本给出。\n")
    (SCENARIO / "scenario.json").write_text(json.dumps({
        "initial": [],
        "criteria": [{"id": i, "check": text, "severity": severity} for i, severity, text in CRITERIA],
    }, ensure_ascii=False, indent=1) + "\n")
    visible = ["counterpart", "analyst", "curator"]
    (SCENARIO / "contract.json").write_text(json.dumps(
        {"checks": {i: {"visibility": visible} for i, _, _ in CRITERIA}}, ensure_ascii=False, indent=1) + "\n")


def main():
    assert len({s[0] for s in SPECS}) == 40 and chinese(12) == "十二" and chinese(4) == "四"
    (HERE / "rules").mkdir(exist_ok=True)
    bank, scripts = [], []
    for spec in SPECS:
        name, group, segment, rule = spec
        rng = random.Random(name)
        data = build(spec, rng)
        text = example(rule, data)
        check_example(rule, data, text)
        files = {"工作规则.md": RULES[rule]["text"], "线索.md": lead_text(data)}
        task = (f"明天上午{RULES[rule]['seller']}的销售要和{data['company']}的{data['title']}做第一次需求沟通，帮我出一份追问清单。\n\n"
                "这次适用的追问清单工作规则和客户线索在工作目录：工作规则.md、线索.md。")
        bank.append({"name": name, "group": group, "segment": segment, "rules": rule, "text": task, "files": files,
                     "reference": reference(spec, data, text)})
        label_ = {"train": "培养", "same": "考试·同规则", "new": "考试·新规则"}[group]
        scripts.append({"name": name, "title": f"{name} · {label_} · {RULES[rule]['seller']}", "exam": group != "train",
                        "steps": [{"text": task, "files": files}]})
    for rule, r in RULES.items():
        (HERE / "rules" / f"{rule}.md").write_text(r["text"])
    (HERE / "questions.json").write_text(json.dumps(bank, ensure_ascii=False, indent=1) + "\n")
    (HERE / "scripts.json").write_text(json.dumps(scripts, ensure_ascii=False, indent=1) + "\n")
    scenario_package()
    print(f"{len(bank)} questions, scenario at {SCENARIO.name}")


if __name__ == "__main__":
    main()
