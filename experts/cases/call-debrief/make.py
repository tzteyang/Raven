"""销售通话复盘：三套工作规则、40 道题（20 培养 + 10 道同规则考试 + 10 道换规则考试）、参考答案和 Studio 场景包。

  python3 make.py

依据《专家自进化》10.1 的案例改写成「工作规则随题交给员工」：三家 SaaS 公司的销售主管要一份通话复盘和一封跟进邮件，
口径不同（问题的优先级、标准话术、话术句数、邮件字数和写法、邮件里不许出现什么、段名）。培养题和同规则考试题用 R1（智排
科技，门店排班）、R2（客流通，会员营销）交替，换规则考试题全用员工从没见过的 R3（账易通，财务软件：多一类“需求确认”问题、
邮件要写客户那边谁参加）。每题一通电话按种子拼出：常见题价格、折扣、上线时长、竞品都是规范写法，日期只说“下周X”；
边界题写成“三万六”“3.6w”“八五折”“15% off”“半个月”、竞品用简称，日期说成“下下周X”“月底前”并跨月，通话里同时有几个
问题要按优先级挑。参考答案写出该报的改进点、销售答应客户的事、下一步和换算好的日期、邮件里不能出现的写法，并附一份照
规则写的示例；check.py 只读员工看到的文件另算一遍。
"""

import calendar
import json
import random
import re
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENARIO = HERE / "wkr-call-debrief"
WEEK = "一二三四五六日"

RULES = {
    "R1": {
        "seller": "智排科技", "product": "门店排班系统", "rep": "李然", "priority": ["价格异议", "下一步承诺", "开场"],
        "sections": ["## 改进点", "## 建议话术", "## 给主管的风险", "## 跟进邮件"], "script": 2, "mail": 120,
        "date": "md", "forbid": ["价格", "折扣", "上线时长", "竞品"], "greet": False, "people": False,
        "competitors": [("排班宝", "上海排班宝信息技术有限公司", "班宝"), ("智慧班表", "杭州智慧班表科技有限公司", "慧班"),
                        ("排排乐", "广州排排乐软件有限公司", "排排")],
        "prices": [("基础版", "2.4 万元/年"), ("专业版", "3.6 万元/年")],
        "customers": [("蜀味鲜火锅", "连锁火锅", "运营总监"), ("一品面馆", "连锁面馆", "运营副总"), ("鲜果时光", "连锁果切", "运营总监"),
                      ("老街烧烤", "连锁烧烤", "运营负责人")],
        "text": """# 智排科技 · 销售通话复盘工作规则

销售主管要一份通话复盘和一封给客户的跟进邮件。题面给通话日期和通话记录；工作目录里的《价目表》是我们的报价，《竞品名单》列了竞品的全称和简称。

1. 复盘只给一个改进点，按手册优先级选：价格异议 → 下一步承诺 → 开场。通话里有几个问题时，只报排在最前的那一个。
2. 价格异议的标准动作：先问对方在和谁比、对方报价包含什么，再讲差异，不能主动降价。
3. 建议话术针对这个改进点，是销售下次可以直接对客户说的原话，不超过两句：价格异议按第 2 条的标准动作问；下一步承诺要当场约定具体哪天、做什么；开场要同时说明来意和这次通话大概多久。
4. 跟进邮件不超过 120 字，写明客户答应的下一步和日期，日期写成“M 月 D 日（周X）”。
5. 邮件里不写价格、折扣和上线时长，不提竞品名字。
6. 通话里销售答应客户的这三类事——降价或折扣、上线时长、赠送——写进“## 给主管的风险”，一行一条，写清答应了什么；约时间、发方案这类不算，不写进这一段；三类都没有就写“无”。

格式：交四段，按顺序：“## 改进点”（一句话，写明销售哪句话、哪里不对）、“## 建议话术”、“## 给主管的风险”、“## 跟进邮件”（邮件正文）。只交这四段，四段前后不加别的文字。

补充口径：

- 问题怎么认（只看下面三种）：
  - 价格异议：客户嫌贵或拿别家的价格比之后，销售接下来那句话不是第 2 条的标准动作（先问在和谁比、对方报价包含什么），就算价格异议没处理好，例如降价、给折扣、直接讲我们更好，或者先问了别的。销售接下来那句话按标准动作问了，不算问题。
  - 下一步承诺：通话结束时，没有和客户约定“哪天、做什么”的具体下一步（例如客户说“回头再说”“我们内部商量下”，销售没追问具体哪天）。客户说了“下周三”“月底前”这类能换算成日期的说法，算约定了。
  - 开场：销售开场的第一句话没有同时说明来意和这次通话大概多久。
- 日期换算：“这周X”是通话日期所在自然周（周一到周日）的周X；“下周X”是下一个自然周的周X；“下下周X”再往后一周；“月底前”取通话当月的最后一天。
- 价格、折扣、上线时长换成任何写法写进邮件都算写了（例如“3.6 万”“三万六”“3.6w”“85 折”“八五折”“15% off”“两周”“14 天”“半个月”）；竞品的全称和简称都算竞品名字。邮件里的日期不算上线时长。
- 客户没答应具体日期的，邮件里写一句“请您定一个方便的时间”，不自己编日期。
- 句子以“。”“！”“？”结尾算一句；字数按字符算，标点算，空格和换行不算。
""",
    },
    "R2": {
        "seller": "客流通", "product": "会员营销系统", "rep": "陈晨", "priority": ["下一步承诺", "价格异议", "开场"],
        "sections": ["## 本次最该改的一点", "## 建议这样说", "## 需主管确认的承诺", "## 跟进邮件"], "script": 1, "mail": 100,
        "date": "iso", "forbid": ["价格", "折扣", "赠送", "竞品"], "greet": True, "people": False,
        "competitors": [("会员宝", "深圳会员宝网络科技有限公司", "会宝"), ("客多多", "成都客多多信息技术有限公司", "客多"),
                        ("积分通", "南京积分通软件有限公司", "积通")],
        "prices": [("标准版", "1.98 万元/年"), ("旗舰版", "2.98 万元/年")],
        "customers": [("茶语时光", "连锁茶饮", "市场总监"), ("麦香坊", "连锁烘焙", "会员运营负责人"), ("优家便利", "连锁便利店", "市场副总"),
                      ("悦动健身", "连锁健身房", "运营总监")],
        "text": """# 客流通 · 销售通话复盘工作规则

销售主管要一份通话复盘和一封给客户的跟进邮件。题面给通话日期和通话记录；工作目录里的《价目表》是我们的报价，《竞品名单》列了竞品的全称和简称。

1. 复盘只给一个改进点，按手册优先级选：下一步承诺 → 价格异议 → 开场。通话里有几个问题时，只报排在最前的那一个。
2. 价格异议的标准动作：先问客户今年在会员营销上的预算范围，再讲投入能带回多少，不能主动降价。
3. 建议话术针对这个改进点，是销售下次可以直接对客户说的原话，只写一句：下一步承诺要当场约定具体哪天、做什么；价格异议按第 2 条的标准动作问；开场要同时说明来意和这次通话大概多久。
4. 跟进邮件不超过 100 字：第一句写“X 总您好”（X 是客户联系人的姓），写明客户答应的下一步和日期，日期写成“YYYY-MM-DD”，最后一行署名“客流通 陈晨”。
5. 邮件里不写价格、折扣和赠送，不提竞品名字。
6. 通话里销售答应客户的这三类事——降价或折扣、上线时长、赠送——写进“## 需主管确认的承诺”，一行一条，写清答应了什么；约时间、发方案这类不算，不写进这一段；三类都没有就写“无”。

格式：交四段，按顺序：“## 本次最该改的一点”（一句话，写明销售哪句话、哪里不对）、“## 建议这样说”、“## 需主管确认的承诺”、“## 跟进邮件”（邮件正文）。只交这四段，四段前后不加别的文字。

补充口径：

- 问题怎么认（只看下面三种）：
  - 下一步承诺：通话结束时，没有和客户约定“哪天、做什么”的具体下一步（例如客户说“回头再说”“我们内部商量下”，销售没追问具体哪天）。客户说了“下周三”“月底前”这类能换算成日期的说法，算约定了。
  - 价格异议：客户嫌贵或拿别家的价格比之后，销售接下来那句话不是第 2 条的标准动作（先问客户的预算范围），就算价格异议没处理好，例如降价、给折扣、直接讲我们更好，或者先问了别的。销售接下来那句话按标准动作问了，不算问题。
  - 开场：销售开场的第一句话没有同时说明来意和这次通话大概多久。
- 日期换算：“这周X”是通话日期所在自然周（周一到周日）的周X；“下周X”是下一个自然周的周X；“下下周X”再往后一周；“月底前”取通话当月的最后一天。
- 价格、折扣、赠送换成任何写法写进邮件都算写了（例如“1.98 万”“一万九千八”“2w”“85 折”“八五折”“15% off”“送三个月”“免费多用三个月”）；竞品的全称和简称都算竞品名字。上线时长可以写。
- 客户没答应具体日期的，邮件里写一句“请您定一个方便的时间”，不自己编日期。
- 句子以“。”“！”“？”结尾算一句；字数按字符算，标点算，空格和换行不算。
""",
    },
    "R3": {
        "seller": "账易通", "product": "财务费控系统", "rep": "赵宁", "priority": ["价格异议", "需求确认", "下一步承诺", "开场"],
        "sections": ["## 改进点", "## 建议话术", "## 给主管的风险", "## 跟进邮件"], "script": 2, "mail": 150,
        "date": "md", "forbid": ["价格", "折扣", "上线时长", "竞品"], "greet": False, "people": True,
        "competitors": [("账管家", "北京账管家科技有限公司", "账管"), ("云财通", "武汉云财通信息技术有限公司", "云财"),
                        ("易记账", "西安易记账软件有限公司", "易记")],
        "prices": [("标准版", "4.8 万元/年"), ("集团版", "8.8 万元/年")],
        "customers": [("顺达物流", "物流", "财务总监"), ("华成制造", "制造", "财务副总"), ("味佳餐饮", "连锁餐饮", "财务经理"),
                      ("安居物业", "物业", "财务总监")],
        "text": """# 账易通 · 销售通话复盘工作规则

销售主管要一份通话复盘和一封给客户的跟进邮件。题面给通话日期和通话记录；工作目录里的《价目表》是我们的报价，《竞品名单》列了竞品的全称和简称。

1. 复盘只给一个改进点，按手册优先级选：价格异议 → 需求确认 → 下一步承诺 → 开场。通话里有几个问题时，只报排在最前的那一个。
2. 价格异议的标准动作：先问对方在和谁比、对方报价包含什么，再讲差异，不能主动降价。需求确认的标准动作：客户说出痛点后，先问这个痛点每月影响多少（多花多少人、多少时间或多少钱），再讲产品。
3. 建议话术针对这个改进点，是销售下次可以直接对客户说的原话，不超过两句：价格异议、需求确认按第 2 条的标准动作问；下一步承诺要当场约定具体哪天、做什么；开场要同时说明来意和这次通话大概多久。
4. 跟进邮件不超过 150 字，写明客户答应的下一步和日期，日期写成“M 月 D 日（周X）”；客户在通话里说了下一步谁一起参加的（例如“财务总监”），邮件里写上这个人，没说的不用写。
5. 邮件里不写价格、折扣和上线时长，不提竞品名字。
6. 通话里销售答应客户的这三类事——降价或折扣、上线时长、赠送——写进“## 给主管的风险”，一行一条，写清答应了什么；约时间、发方案这类不算，不写进这一段；三类都没有就写“无”。

格式：交四段，按顺序：“## 改进点”（一句话，写明销售哪句话、哪里不对）、“## 建议话术”、“## 给主管的风险”、“## 跟进邮件”（邮件正文）。只交这四段，四段前后不加别的文字。

补充口径：

- 问题怎么认（只看下面四种）：
  - 价格异议：客户嫌贵或拿别家的价格比之后，销售接下来那句话不是第 2 条的标准动作（先问在和谁比、对方报价包含什么），就算价格异议没处理好，例如降价、给折扣、直接讲我们更好，或者先问了别的。销售接下来那句话按标准动作问了，不算问题。
  - 需求确认：客户说出痛点后，销售接下来那句话没有先问这个痛点每月影响多少（多花多少人、多少时间或多少钱），而是直接介绍产品或说别的。销售接下来那句话先问了影响，不算问题。
  - 下一步承诺：通话结束时，没有和客户约定“哪天、做什么”的具体下一步（例如客户说“回头再说”“我们内部商量下”，销售没追问具体哪天）。客户说了“下周三”“月底前”这类能换算成日期的说法，算约定了。
  - 开场：销售开场的第一句话没有同时说明来意和这次通话大概多久。
- 日期换算：“这周X”是通话日期所在自然周（周一到周日）的周X；“下周X”是下一个自然周的周X；“下下周X”再往后一周；“月底前”取通话当月的最后一天。
- 价格、折扣、上线时长换成任何写法写进邮件都算写了（例如“4.8 万”“四万八”“4.8w”“85 折”“八五折”“15% off”“两周”“14 天”“半个月”）；竞品的全称和简称都算竞品名字。邮件里的日期不算上线时长。
- 客户没答应具体日期的，邮件里写一句“请您定一个方便的时间”，不自己编日期。
- 句子以“。”“！”“？”结尾算一句；字数按字符算，标点算，空格和换行不算。
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
    "你是 SaaS 公司销售团队的复盘助理。销售打完客户电话，你根据通话记录写一份给销售主管的复盘和一封给客户的跟进邮件。"
    "工作目录里有这次适用的通话复盘工作规则、我们的价目表和竞品名单。按这次给的工作规则写，主管看完会直接把邮件发给客户。"
    "只输出规则要求的内容。"
)
ONBOARDING = "以后每通销售电话的复盘，我都会把通话日期、通话记录，连同这次适用的复盘工作规则、价目表和竞品名单一起发给你。不同公司的口径不一样，以当次给的为准。"
CRITERIA = [
    ("D-point", "red_line",
     "改进点：按这次规则的优先级，只报排在最前的那一个问题（参考答案写明了通话里有哪些问题、该报哪个）；报错了类别、报了不止一个、"
     "或没写明销售哪句话哪里不对，每处记一处。"),
    ("D-script", "standard",
     "建议话术：针对该报的改进点、按规则的标准动作写（价格异议按这次规则的问法、不降价；下一步承诺要约到具体哪天做什么；开场要同时说"
     "来意和时长；需求确认要先问痛点每月影响多少），是能直接对客户说的原话；句数不超过规则上限（测量值给出句数）。每处不符记一处。"),
    ("D-risk", "standard",
     "答应客户的事：参考答案列出的销售答应客户的事（只有降价或折扣、上线时长、赠送三类）都要写进规则指定的那一段（漏一条记一处）；"
     "这一段写了这三类以外的事（例如约时间、发方案）或通话里没有的事，每条记一处；三类都没有时要写“无”。"),
    ("D-mail", "standard",
     "跟进邮件：字数不超过上限（以测量值为准）；写明客户答应的下一步和换算对的日期、日期写法按规则（没答应具体日期的写“请您定一个"
     "方便的时间”）；规则要求的称呼、署名、参加人写到；规则不许写的内容（价格、折扣、上线时长或赠送、竞品全称或简称）任何写法都不能"
     "出现（测量值列出了邮件里可疑的数字和词，由你判断）。每处不符记一处。日期里数字和“月”“日”之间有没有空格、括号全角半角不同，"
     "都不算错。"),
    ("D-format", "standard",
     "格式：按这次规则的段名和顺序交四段，四段前后没有别的文字；每处不符记一处。"),
]


def monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def resolve(call: date, phrase: str) -> date | None:
    if phrase == "月底前":
        return date(call.year, call.month, calendar.monthrange(call.year, call.month)[1])
    m = re.fullmatch(r"(这|下|下下)周(.)", phrase)
    if not m:
        return None
    weeks = {"这": 0, "下": 1, "下下": 2}[m.group(1)]
    return monday(call) + timedelta(weeks=weeks, days=WEEK.index(m.group(2)))


def say_date(rule: str, day: date) -> str:
    if RULES[rule]["date"] == "iso":
        return day.isoformat()
    return f"{day.month} 月 {day.day} 日（周{WEEK[day.weekday()]}）"


def build(spec, rng, issue):
    """One call where `issue` is the top problem by this rule's priority, with some lower-priority problems too
    (edge questions always have at least one), and the transcript lines and facts the reference needs."""
    name, group, segment, rule = spec
    r = RULES[rule]
    edge = segment == "edge"
    company, trade, title = rng.choice(r["customers"])
    surname = rng.choice("王张刘陈杨黄周吴徐孙马朱胡郭何林")
    comp = rng.choice(r["competitors"])
    price_plan, price_text = rng.choice(r["prices"])
    amount = price_text.split()[0]
    call = rng.choice([date(2026, 9, 15), date(2026, 9, 22), date(2026, 10, 13), date(2026, 10, 20), date(2026, 11, 10),
                       date(2026, 11, 17), date(2026, 12, 8)] if not edge else
                      [date(2026, 9, 24), date(2026, 9, 28), date(2026, 10, 26), date(2026, 10, 29), date(2026, 11, 23),
                       date(2026, 11, 26), date(2026, 12, 21)])
    lower_kinds = r["priority"][r["priority"].index(issue) + 1:]
    if edge:
        # 边界题至少再有一个排在后面的问题；“下一步承诺”只在三分之一的题里陪跑，留出约到日期（下下周X、月底前）的题
        lower = {k for k in lower_kinds if k != "下一步承诺" and rng.random() < 0.7}
        if "下一步承诺" in lower_kinds and rng.random() < 0.33:
            lower.add("下一步承诺")
        if not lower:
            lower.add(rng.choice(lower_kinds))
        if rule == "R2" and issue == "下一步承诺":
            lower.add("价格异议")  # 背了 R1 优先级的会报价格异议
    else:
        lower = set(rng.sample(lower_kinds, 1)) if lower_kinds and rng.random() < 0.4 else set()
    problems = {k: k == issue or k in lower for k in r["priority"]}
    contact = f"{surname}总"
    lines, promises, mail_banned, evidence = [], [], [], {}
    topic = {"R1": "排班", "R2": "会员运营", "R3": "报销和费用"}[rule]
    if problems["开场"]:
        lines.append(rng.choice([f"销售：{contact}您好，我是{r['seller']}的{r['rep']}。",
                                 f"销售：{contact}您好，我是{r['seller']}的{r['rep']}，想跟您聊聊贵司{topic}的事。"]))
        evidence["开场"] = lines[-1]
    else:
        lines.append(f"销售：{contact}您好，我是{r['seller']}的{r['rep']}，今天占用您 {rng.choice([10, 15, 20])} 分钟，"
                     f"想了解一下贵司现在{topic}是怎么做的。")
    lines.append("客户：你说吧。")
    pain = {"R1": "现在店长每周排班要花一整天，还老出错", "R2": "会员办了卡就不来了，复购上不去",
            "R3": "每月报销单要财务三个人核一个礼拜"}[rule]
    lines.append(f"客户：{pain}。")
    if problems.get("需求确认") or (rule != "R3" and rng.random() < 0.5):
        lines.append(rng.choice([f"销售：我们的{r['product']}能一键搞定，特别快。",
                                 f"销售：明白，我们的{r['product']}主要就是解决这个问题的。"]))
        evidence["需求确认"] = lines[-1]
    else:
        lines.append("销售：这个情况每个月大概要多花多少人、多少时间？")
        lines.append(rng.choice(["客户：三个人，差不多一周吧。", "客户：两个人，前后得四五天。"]))
    standard = ("理解，您今年在会员营销上大概有多少预算？我按这个帮您算算投入能带回多少。" if rule == "R2" else
                "您对比的{comp}一年多少钱、包含哪些功能？我们先看看差在哪里。")
    other = ("您对比的{comp}一年多少钱、包含哪些功能？我们先看看差在哪里。" if rule == "R2" else
             "理解，您今年在这块大概有多少预算？我按这个帮您算算投入能带回多少。")
    if problems["价格异议"] or rng.random() < 0.5:
        said_price = rng.choice([chinese_amount(amount), f"{amount}w"]) if edge else f"{amount} 万"
        comp_name = comp[2] if edge else comp[0]
        lines.append(f"客户：你们{price_plan}一年{' ' if said_price[0].isdigit() else ''}{said_price}，比{comp_name}贵了快一万。")
        mail_banned += [f"{amount} 万", said_price, comp[0], comp[2]]
        if problems["价格异议"]:
            way = rng.choice(["discount", "discount", "brag"] + (["other"] if edge else []))
            if way == "discount":
                discount = rng.choice(["八五折", "15% off"]) if edge else "85 折"
                lines.append(f"销售：这个我可以去申请，给您打{' ' if discount[0].isdigit() else ''}{discount}。")
                promises.append(f"答应去申请{' 85 折' if '折' in discount else ' 15% 的折扣'}"
                                f"（原话“给您打{' ' if discount[0].isdigit() else ''}{discount}”）")
                mail_banned += [discount, "85 折", "八五折", "15%"]
            elif way == "brag":
                lines.append(f"销售：我们功能比{comp_name}全多了，贵是有道理的。")
            else:
                lines.append("销售：" + other.format(comp=comp_name))
                lines.append("客户：回头再说吧。")
            evidence["价格异议"] = next(l for l in reversed(lines) if l.startswith("销售："))
        else:
            lines.append("销售：" + standard.format(comp=comp_name))
            lines.append("客户：回头我把他们的报价单发你。")
    if rng.random() < (0.7 if edge else 0.5):
        lines.append("客户：上线要多久？我们下个月要开两家新店。")
        launch = rng.choice(["半个月", "14 天"]) if edge else "两周"
        lines.append(f"销售：{launch}就能上线，没问题。")
        promises.append(f"答应{' ' if launch[0].isdigit() else ''}{launch}上线（原话“{launch}就能上线”）")
        if rule != "R2":
            mail_banned += [launch, "两周", "14 天", "半个月"]
    if rng.random() < 0.35:
        lines.append("销售：签约的话首年我再送您三个月。")
        promises.append("答应签约首年再送三个月（原话“首年我再送您三个月”）")
        if rule == "R2":
            mail_banned += ["送您三个月", "送三个月", "赠送", "免费"]
    people, when, phrase, step = None, None, None, None
    if problems["下一步承诺"]:
        lines.append(rng.choice(["客户：行，我们内部再商量商量，回头联系你。", "客户：方案你先发我看看，回头再说。"]))
        lines.append(rng.choice(["销售：好的，等您消息。", "销售：好的，那我先把方案发您。"]))
        evidence["下一步承诺"] = lines[-1]
    else:
        phrase = rng.choice(["下下周三", "下下周四", "月底前"]) if edge else rng.choice(["下周二", "下周三", "下周四"])
        when = resolve(call, phrase)
        if phrase == "月底前":
            lines.append("客户：方案我们看过了，月底前给你答复。")
            lines.append("销售：好的，那月底前我等您消息，有问题随时找我。")
            step = "客户给答复"
        else:
            people = rng.choice(["财务总监", "老板", "IT 负责人"])
            lines.append(f"客户：行，{phrase}我约{people}一起听一下方案。")
            lines.append(f"销售：好的，{phrase}我把方案准备好。")
            step = f"和{people}一起听方案"
    assert next(k for k in r["priority"] if problems[k]) == issue
    return {
        "call": call, "company": company, "trade": trade, "title": title, "contact": contact, "surname": surname,
        "competitor": comp, "price": (price_plan, price_text), "lines": lines, "problems": problems,
        "issue": issue, "promises": promises, "phrase": phrase, "when": when, "people": people,
        "step": step, "banned": sorted(set(mail_banned)), "evidence": evidence,
    }


def chinese_amount(amount: str) -> str:
    digits = "零一二三四五六七八九"
    whole, _, tenth = amount.partition(".")
    out = digits[int(whole)] + "万"
    if tenth:
        out += digits[int(tenth[0])] + ("千" + digits[int(tenth[1])] if len(tenth) > 1 else "")
    return out


def transcript(call, rule, data) -> str:
    r = RULES[rule]
    head = [f"# 通话记录", "", f"通话日期：{call.isoformat()}（周{WEEK[call.weekday()]}）",
            f"客户公司：{data['company']}（{data['trade']}），联系人是{data['title']}，姓{data['surname']}（通话里称“{data['contact']}”）",
            f"我方销售：{r['seller']} {r['rep']}", "", "## 通话内容", ""]
    return "\n".join(head + data["lines"]) + "\n"


def prices_text(rule) -> str:
    r = RULES[rule]
    rows = ["# 价目表", "", f"{r['seller']} {r['product']}", "", "| 版本 | 报价 |", "|---|---|"]
    rows += [f"| {plan} | {price} |" for plan, price in r["prices"]]
    return "\n".join(rows) + "\n\n折扣和赠送都要销售主管审批，销售不能当场答应。\n"


def competitors_text(rule) -> str:
    rows = ["# 竞品名单", "", "| 竞品 | 全称 | 常见简称 |", "|---|---|---|"]
    rows += [f"| {a} | {b} | {c} |" for a, b, c in RULES[rule]["competitors"]]
    return "\n".join(rows) + "\n"


SCRIPTS = {
    ("R1", "价格异议"): "您对比的{comp}一年多少钱、包含哪些功能？我们先一起看看差在哪里。",
    ("R3", "价格异议"): "您对比的{comp}一年多少钱、包含哪些功能？我们先一起看看差在哪里。",
    ("R2", "价格异议"): "您今年在会员营销上大概有多少预算，我按这个帮您算算投入能带回多少？",
    ("R1", "下一步承诺"): "{contact}，我们定在下周三下午，我把方案带过来给您和团队一起过一遍，您看行吗？",
    ("R3", "下一步承诺"): "{contact}，我们定在下周三下午，我把方案带过来给您和团队一起过一遍，您看行吗？",
    ("R2", "下一步承诺"): "{contact}，我们约下周三下午一起过一遍方案，您看行吗？",
    ("R1", "开场"): "{contact}您好，我是智排科技的李然，今天占用您 15 分钟，想了解一下门店排班现在是怎么做的。",
    ("R2", "开场"): "{contact}您好，我是客流通的陈晨，今天占用您 15 分钟，想了解一下贵司会员运营现在是怎么做的。",
    ("R3", "开场"): "{contact}您好，我是账易通的赵宁，今天占用您 15 分钟，想了解一下贵司报销和费用现在是怎么做的。",
    ("R3", "需求确认"): "这件事每个月大概要多花多少人、多少时间？您先帮我估一下，我再看我们能帮上哪一块。",
}


def example(rule, data) -> str:
    r = RULES[rule]
    issue = data["issue"]
    seller_line = data["evidence"][issue]
    what = {"价格异议": "客户嫌贵后没先问对方在和谁比、报价包含什么" if rule != "R2" else "客户嫌贵后没先问客户的预算范围",
            "下一步承诺": "客户说回头再联系时没追问具体哪天、做什么", "开场": "开场没说明来意和通话时长",
            "需求确认": "客户说出痛点后没先问每月影响多少"}[issue]
    point = f"销售说“{seller_line[3:]}”，{what}。"
    script = SCRIPTS[(rule, issue)].format(comp=data["competitor"][0], contact=data["contact"])
    risks = "\n".join(f"- {p}" for p in data["promises"]) or "无"
    if data["when"]:
        step = f"按约定，{say_date(rule, data['when'])}{'我们' if data['people'] else ''}{data['step'] if data['people'] else '等您的答复'}"
        step = (f"按约定，{say_date(rule, data['when'])}我们和您、{data['people']}一起听一下方案" if data["people"] else
                f"按约定，您会在{say_date(rule, data['when'])}前给我们答复")
    else:
        step = "我们这边随时可以把方案再细讲一遍，请您定一个方便的时间"
    if rule == "R2":
        mail = f"{data['surname']}总您好，感谢今天的沟通。{step}。\n客流通 陈晨"
    else:
        mail = f"{data['contact']}您好，感谢今天的沟通。{step}，期待和您再聊。"
    sections = r["sections"]
    return "\n\n".join([f"{sections[0]}\n\n{point}", f"{sections[1]}\n\n{script}", f"{sections[2]}\n\n{risks}",
                        f"{sections[3]}\n\n{mail}"])


def check(rule, data, text) -> None:
    r = RULES[rule]
    mail = text.split(r["sections"][3])[1].strip()
    assert len(re.sub(r"\s", "", mail)) <= r["mail"] - 10, (rule, mail)
    for word in data["banned"]:
        assert word not in mail, (word, mail)
    script = text.split(r["sections"][1])[1].split(r["sections"][2])[0].strip()
    assert len([s for s in re.split(r"(?<=[。！？])", script) if s.strip()]) <= r["script"], script
    if data["when"]:
        assert say_date(rule, data["when"]) in mail
    # 邮件里出现的竞品名、价格、折扣都不能有
    for a, b, c in r["competitors"]:
        assert a not in mail and c not in mail
    assert "意外" not in text


def reference(spec, data, text) -> dict:
    name, group, segment, rule = spec
    r = RULES[rule]
    found = [k for k in r["priority"] if data["problems"].get(k)]
    return {
        "规则集": f"{rule}（{r['seller']}）",
        "通话日期": f"{data['call'].isoformat()}（周{WEEK[data['call'].weekday()]}）",
        "通话里有的问题（按这次规则的优先级）": found,
        "该报的改进点": data["issue"],
        "能说明这个问题的销售原话": data["evidence"][data["issue"]][3:],
        "不是问题的（处理得对或没出现）": [k for k in r["priority"] if not data["problems"].get(k)],
        "销售答应客户的事（都要写进规则指定的那一段）": data["promises"] or "无",
        "下一步": ({"客户原话里的说法": data["phrase"], "换算后的日期": say_date(rule, data["when"]), "做什么": data["step"],
                  "客户那边参加的人": data["people"] or "通话里没说"} if data["when"] else
                 "客户没答应具体日期：邮件里写“请您定一个方便的时间”，不能自己编日期"),
        "邮件里不能出现的写法（举例，换成别的写法也算）": data["banned"] + [c[0] for c in r["competitors"] if c[0] not in data["banned"]],
        "邮件规则": {
            "字数上限": r["mail"],
            "不许写": r["forbid"],
            "日期写法": "M 月 D 日（周X）" if r["date"] == "md" else "YYYY-MM-DD",
            "称呼和署名": f"第一句“{data['surname']}总您好”，最后一行“客流通 陈晨”" if r["greet"] else "规则没要求",
            "参加人": ("要写上“" + data["people"] + "”" if data["people"] else "通话里没说，不用写") if r["people"] else "规则没要求",
        },
        "建议话术句数上限": r["script"],
        "段名（按顺序）": r["sections"],
        "一份照规则写的示例（措辞可以不同）": text,
    }


def scenario_package():
    (SCENARIO / "personas").mkdir(parents=True, exist_ok=True)
    (SCENARIO / "profile.md").write_text(TASK + "\n")
    (SCENARIO / "onboarding.md").write_text(ONBOARDING + "\n")
    (SCENARIO / "personas" / "manager.md").write_text("销售主管每通重要电话后要一份复盘和一封跟进邮件；每道题的通话、价目表、竞品名单和规则由脚本给出。\n")
    (SCENARIO / "scenario.json").write_text(json.dumps({
        "initial": [],
        "criteria": [{"id": i, "check": text, "severity": severity} for i, severity, text in CRITERIA],
    }, ensure_ascii=False, indent=1) + "\n")
    visible = ["counterpart", "analyst", "curator"]
    (SCENARIO / "contract.json").write_text(json.dumps(
        {"checks": {i: {"visibility": visible} for i, _, _ in CRITERIA}}, ensure_ascii=False, indent=1) + "\n")


def main():
    assert len({s[0] for s in SPECS}) == 40
    assert resolve(date(2026, 9, 15), "下周三") == date(2026, 9, 23)
    assert resolve(date(2026, 9, 28), "下下周四") == date(2026, 10, 15)
    assert resolve(date(2026, 11, 26), "月底前") == date(2026, 11, 30)
    assert chinese_amount("3.6") == "三万六" and chinese_amount("2.98") == "二万九千八", chinese_amount("3.6")
    (HERE / "rules").mkdir(exist_ok=True)
    bank, scripts, retries = [], [], 0
    seen = {rule: {"common": 0, "edge": 0} for rule in RULES}
    for spec in SPECS:
        name, group, segment, rule = spec
        kinds = RULES[rule]["priority"] if segment == "common" else RULES[rule]["priority"][:-1]
        if rule == "R3" and segment == "edge":
            kinds = ["需求确认", "价格异议", "需求确认", "下一步承诺", "需求确认"]
        issue = kinds[seen[rule][segment] % len(kinds)]
        seen[rule][segment] += 1
        for salt in range(300):
            rng = random.Random(f"{name}:{salt}")
            data = build(spec, rng, issue)
            text = example(rule, data)
            try:
                check(rule, data, text)
                if segment == "edge":
                    # 边界题：至少两个问题同时出现，日期说法是“下下周X”或“月底前”（或没约到日期），且跨月或价格写法不规范
                    assert sum(data["problems"].values()) >= 2
                    assert data["when"] is None or data["when"].month != data["call"].month or data["phrase"] == "月底前"
                    assert data["banned"] or data["issue"] != "价格异议"
                break
            except AssertionError:
                retries += 1
        else:
            raise RuntimeError(f"{name}: no seed passes the checks")
        files = {"工作规则.md": RULES[rule]["text"], "通话记录.md": transcript(data["call"], rule, data),
                 "价目表.md": prices_text(rule), "竞品名单.md": competitors_text(rule)}
        task = (f"{RULES[rule]['rep']}刚和{data['company']}的{data['contact']}通完电话（{data['call'].isoformat()}），"
                "帮我出一份通话复盘和一封跟进邮件。\n\n这次适用的复盘工作规则、通话记录、价目表和竞品名单在工作目录：工作规则.md、"
                "通话记录.md、价目表.md、竞品名单.md。")
        bank.append({"name": name, "group": group, "segment": segment, "rules": rule, "text": task, "files": files,
                     "reference": reference(spec, data, text)})
        label = {"train": "培养", "same": "考试·同规则", "new": "考试·新规则"}[group]
        scripts.append({"name": name, "title": f"{name} · {label} · {RULES[rule]['seller']}", "exam": group != "train",
                        "steps": [{"text": task, "files": files}]})
    for rule, r in RULES.items():
        (HERE / "rules" / f"{rule}.md").write_text(r["text"])
    (HERE / "questions.json").write_text(json.dumps(bank, ensure_ascii=False, indent=1) + "\n")
    (HERE / "scripts.json").write_text(json.dumps(scripts, ensure_ascii=False, indent=1) + "\n")
    scenario_package()
    print(f"{len(bank)} questions, {retries} seed retries, scenario at {SCENARIO.name}")


if __name__ == "__main__":
    main()
