"""网课退款客服：三套工作规则、40 道题（20 培养 + 10 道同规则考试 + 10 道换规则考试）、参考答案和 Studio 场景包。

  python3 make.py

依据《专家自进化》1.1 的案例改写成「工作规则随题交给员工」：三家机构的规则结构相同、数值和说法不同；
培养题和同规则考试题用 R1、R2 交替，换规则考试题全用员工从没见过的 R3。每道题的数据逐条写在 SPECS 里，
参考答案由本脚本按规则算出；check.py 另写一遍算法独立复核，生成后还要人工逐题过目。
"""

import json
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENARIO = HERE / "wkr-refund-desk"
TYPES = ("语言考试冲刺", "职业技能", "中小学同步", "兴趣素养", "学历提升", "编程实战")
COURSES = {
    "雅思冲刺课": "语言考试冲刺", "托福强化班": "语言考试冲刺", "四六级突破营": "语言考试冲刺",
    "Excel 高效办公": "职业技能", "短视频运营实战": "职业技能", "剪辑入门": "职业技能",
    "初二数学同步": "中小学同步", "小学英语自然拼读": "中小学同步", "高一物理同步": "中小学同步",
    "国画入门": "兴趣素养", "少儿围棋": "兴趣素养", "吉他弹唱": "兴趣素养",
    "专升本英语": "学历提升", "考研政治全程": "学历提升", "自考会计基础": "学历提升",
    "Python 数据分析": "编程实战", "Java 后端训练营": "编程实战", "前端开发实战": "编程实战",
}

# 每套规则：机构、政策表（全额退天数、全额退节数、手续费比例）、数天的起点、手续费下限、到账说法、转人工关键词和告知、称呼、字数上限、不许推荐的场景
RULES = {
    "R1": {
        "org": "青禾网课", "prefix": "QH",
        "table": {"语言考试冲刺": (7, 3, 10), "职业技能": (7, 2, 10), "中小学同步": (14, 4, 5),
                  "兴趣素养": (3, 1, 15), "学历提升": (10, 3, 8), "编程实战": (7, 3, 12)},
        "first_day": "购课当天算第 1 天", "same_day_is_one": True, "min_fee": None,
        "arrival": "3 到 5 个工作日",
        "keywords": ("投诉", "12315", "媒体"), "notice": "工单号会短信发送",
        "address": "称呼学员用“同学”，不用“亲”。", "address_short": "同学",
        "limit": 150, "upsell": "投诉场景不推荐任何课程。",
    },
    "R2": {
        "org": "知行学堂", "prefix": "ZX",
        "table": {"语言考试冲刺": (5, 2, 8), "职业技能": (10, 3, 10), "中小学同步": (7, 3, 6),
                  "兴趣素养": (5, 2, 12), "学历提升": (14, 4, 10), "编程实战": (7, 2, 15)},
        "first_day": "购课次日算第 1 天（购课当天不算）", "same_day_is_one": False, "min_fee": None,
        "arrival": "1 到 3 个工作日",
        "keywords": ("投诉", "举报", "曝光"), "notice": "工单号会通过邮件发给学员",
        "address": "称呼学员用“学员”，例如“学员您好”；不用“亲”“宝”。", "address_short": "学员",
        "limit": 120, "upsell": "任何回复都不推荐课程。",
    },
    "R3": {
        "org": "远帆教育", "prefix": "YF",
        "table": {"语言考试冲刺": (10, 4, 12), "职业技能": (7, 3, 8), "中小学同步": (10, 2, 5),
                  "兴趣素养": (7, 2, 10), "学历提升": (7, 3, 6), "编程实战": (14, 4, 10)},
        "first_day": "购课当天算第 1 天", "same_day_is_one": True, "min_fee": Decimal("20"),
        "arrival": "5 到 7 个工作日",
        "keywords": ("投诉", "12315", "律师"), "notice": "工单号会短信发送，24 小时内会有专人联系学员",
        "address": "称呼学员用姓名加“同学”，例如“张敏同学”；不用“亲”。", "address_short": "姓名加同学",
        "limit": 180, "upsell": "投诉场景不推荐任何课程，也不发优惠券或其他补偿。",
    },
}

# name, group(train/same/new), segment(common/boundary), rules, today, student, course, buy, list, coupon,
# installments (periods, per period, paid periods) or None, total lessons, attended, message
SPECS = [
    ("t01", "train", "common", "R1", "2026-09-25", "王雨桐", "雅思冲刺课", "2026-09-20", 1999, 0, None, 20, 3,
     "你好，我 9 月 20 日买了 1999 元的雅思冲刺课，听了 3 节觉得不适合，能全额退吗？客服电话一直打不通，再不处理我就去 12315 投诉。"),
    ("t02", "train", "common", "R2", "2026-09-22", "陈嘉怡", "Excel 高效办公", "2026-09-01", 1600, 0, None, 20, 8,
     "老师好，Excel 高效办公这门课我听了 8 节，最近工作太忙实在跟不上了，想申请退款，能退多少？"),
    ("t03", "train", "common", "R1", "2026-09-25", "刘子航", "托福强化班", "2026-09-10", 2400, 0, None, 24, 6,
     "我 9 月 10 号报的托福强化班，一共 24 节听了 6 节，打算改成线下班了，剩下的能退吗？"),
    ("t04", "train", "common", "R2", "2026-09-21", "赵梦琪", "初二数学同步", "2026-09-18", 1280, 0, None, 32, 1,
     "孩子的初二数学同步课才上了 1 节，老师讲得太快孩子完全听不懂，我要退款。你们再推脱我就去教育局举报。"),
    ("t05", "train", "common", "R1", "2026-09-26", "孙浩然", "国画入门", "2026-09-12", 960, 0, None, 16, 4,
     "国画入门的课跟宣传完全两回事，听了 4 节就不想听了。你们要是不给退，我就把聊天记录发给媒体。"),
    ("t06", "train", "common", "R2", "2026-09-24", "周欣然", "Python 数据分析", "2026-09-03", 4800, 0, None, 40, 10,
     "请问 Python 数据分析还能退吗？我 9 月 3 日报的名，现在听了 10 节，后面的内容用不上了。"),
    ("t07", "train", "common", "R1", "2026-09-26", "吴俊杰", "考研政治全程", "2026-09-22", 2680, 0, None, 40, 2,
     "你好，考研政治全程班我 9 月 22 号买的，听了 2 节，发现学校给我们发了同样的课，想退掉。"),
    ("t08", "train", "common", "R2", "2026-09-25", "郑雅婷", "吉他弹唱", "2026-09-05", 1200, 0, None, 12, 6,
     "吉他弹唱的老师连着两次没来上课，我已经听了 6 节，剩下的我要退。再不给我处理我就上网曝光你们。"),
    ("t09", "train", "common", "R1", "2026-09-27", "冯一鸣", "Java 后端训练营", "2026-09-15", 6000, 0, None, 30, 5,
     "Java 后端训练营的助教一直不回消息，我交了 6000 块才上了 5 节，我要投诉，并且申请退款。"),
    ("t10", "train", "common", "R2", "2026-09-26", "何思琪", "专升本英语", "2026-09-20", 1880, 0, None, 30, 2,
     "专升本英语我 9 月 20 号报的，听了 2 节，家里有事今年不考了，可以退吗？"),
    ("t11", "train", "boundary", "R1", "2026-09-25", "林晓雯", "雅思冲刺课", "2026-09-19", 2000, 300, None, 20, 2,
     "我 9 月 19 号买的雅思冲刺课，标价 2000 元，听了 2 节，现在不想学了，能退 2000 吗？"),
    ("t12", "train", "boundary", "R2", "2026-09-25", "高子轩", "短视频运营实战", "2026-09-15", 1500, 0, None, 15, 3,
     "短视频运营实战我是 9 月 15 号买的，到今天已经第 11 天了，听了 3 节，还能全额退吗？"),
    ("t13", "train", "boundary", "R1", "2026-09-26", "马婧怡", "自考会计基础", "2026-08-30", 3600, 0, (12, 300, 4), 36, 9,
     "自考会计基础我是分期付的，已经付了 4 期，课听了 9 节，你们一直不给我开退款入口，再这样我打 12315。"),
    ("t14", "train", "boundary", "R2", "2026-09-26", "罗嘉豪", "托福强化班", "2026-09-22", 2400, 200, None, 24, 2,
     "托福强化班我 9 月 22 号买的，听了 2 节，跟我想的不一样。我要退 2400，你们客服之前说不能退，我要投诉这个客服。"),
    ("t15", "train", "boundary", "R1", "2026-09-25", "梁诗涵", "剪辑入门", "2026-09-18", 1200, 0, None, 12, 1,
     "剪辑入门我 9 月 18 号买的，就听了 1 节，应该还能全额退吧？"),
    ("t16", "train", "boundary", "R2", "2026-09-25", "宋文博", "前端开发实战", "2026-09-01", 4800, 480, (6, 720, 2), 48, 8,
     "前端开发实战我是分期买的，听了 8 节发现跟不上，想把课退了。你们要是拖着不办，我就去网上曝光。"),
    ("t17", "train", "boundary", "R1", "2026-09-25", "唐语嫣", "高一物理同步", "2026-09-12", 1680, 100, None, 32, 4,
     "高一物理同步是 9 月 12 号给孩子买的，听了 4 节，孩子说学校进度不一样，能全额退吗？"),
    ("t18", "train", "boundary", "R2", "2026-09-25", "韩宇航", "少儿围棋", "2026-09-23", 900, 0, None, 18, 3,
     "少儿围棋才买了两天，孩子上了 3 节就哭着不想去了，我要全额退款，不退我就举报你们虚假宣传。"),
    ("t19", "train", "boundary", "R1", "2026-09-26", "曹梓涵", "考研政治全程", "2026-09-20", 2400, 0, (12, 200, 1), 40, 1,
     "考研政治全程我分期买的，一共 2400，现在想退，能退 2400 吗？不给退的话我就找媒体。"),
    ("t20", "train", "boundary", "R2", "2026-09-25", "许晨阳", "Excel 高效办公", "2026-08-28", 1600, 160, None, 16, 4,
     "Excel 高效办公我听了 4 节，剩下 12 节不想上了，按 1600 算的话应该退 1200 吧？"),
    ("x01", "same", "common", "R1", "2026-09-24", "邓佳琪", "四六级突破营", "2026-09-21", 899, 0, None, 18, 2,
     "四六级突破营我 9 月 21 号买的，才听了 2 节，你们的助教态度很差，我要投诉，课也要退。"),
    ("x02", "same", "common", "R2", "2026-09-25", "彭俊熙", "小学英语自然拼读", "2026-09-02", 1500, 0, None, 20, 10,
     "小学英语自然拼读孩子上了 10 节，最近转学了没时间上，剩下的课能退吗？"),
    ("x03", "same", "common", "R1", "2026-09-25", "蒋雨萱", "Python 数据分析", "2026-09-08", 4000, 0, None, 40, 8,
     "Python 数据分析的录播课有一半打不开，我听了 8 节就没法继续了，今天不给我退款我就打 12315。"),
    ("x04", "same", "common", "R2", "2026-09-25", "沈浩宇", "国画入门", "2026-09-23", 960, 0, None, 16, 1,
     "国画入门 9 月 23 号买的，听了 1 节，发现时间和工作冲突，想退款。"),
    ("x05", "same", "common", "R1", "2026-09-26", "袁梦瑶", "专升本英语", "2026-09-10", 2500, 0, None, 25, 5,
     "专升本英语承诺的直播答疑一次都没有，我听了 5 节，要求退剩下的钱，不然我就联系媒体。"),
    ("x06", "same", "boundary", "R2", "2026-09-25", "潘子豪", "托福强化班", "2026-09-20", 2400, 240, None, 24, 2,
     "托福强化班 9 月 20 号买的，原价 2400，听了 2 节。今天已经第 6 天了，我要全额退 2400，你们不退我就投诉。"),
    ("x07", "same", "boundary", "R1", "2026-09-26", "杜欣怡", "前端开发实战", "2026-08-25", 5400, 0, (6, 900, 3), 36, 9,
     "前端开发实战我分 6 期买的，付了 3 期，课听了 9 节，现在想退，剩下的钱能退多少？"),
    ("x08", "same", "boundary", "R2", "2026-09-25", "姚俊豪", "剪辑入门", "2026-09-14", 1200, 0, None, 12, 3,
     "剪辑入门我才买了 10 天，听了 3 节，你们说只能部分退？我要全额退，不然就去举报你们。"),
    ("x09", "same", "boundary", "R1", "2026-09-25", "范雨桐", "短视频运营实战", "2026-09-19", 1800, 200, None, 18, 2,
     "短视频运营实战 9 月 19 号买的，标价 1800，我听了 2 节，能退 1800 吗？"),
    ("x10", "same", "boundary", "R2", "2026-09-26", "方子涵", "自考会计基础", "2026-09-15", 3600, 0, (12, 300, 2), 36, 4,
     "自考会计基础分期买的，一共 3600，已经付了 2 期，听了 4 节，我要求全部退掉，不然就在网上曝光你们。"),
    ("y01", "new", "common", "R3", "2026-09-25", "张敏", "雅思冲刺课", "2026-09-18", 1999, 0, None, 20, 3,
     "雅思冲刺课 9 月 18 号买的，听了 3 节，老师水平太差，我要退款，已经咨询过律师了。"),
    ("y02", "new", "common", "R3", "2026-09-25", "李浩", "Excel 高效办公", "2026-09-01", 1600, 0, None, 20, 6,
     "Excel 高效办公听了 6 节，最近换工作用不上了，剩下的课能退吗？"),
    ("y03", "new", "common", "R3", "2026-09-25", "王芳", "初二数学同步", "2026-09-20", 1280, 0, None, 32, 3,
     "初二数学同步孩子上了 3 节，内容和学校不一样，我要退款，不给退我就打 12315。"),
    ("y04", "new", "common", "R3", "2026-09-25", "刘洋", "吉他弹唱", "2026-09-22", 1200, 0, None, 12, 1,
     "吉他弹唱 9 月 22 号买的，上了 1 节，手指受伤了没法练，想退款。"),
    ("y05", "new", "common", "R3", "2026-09-26", "陈静", "Java 后端训练营", "2026-09-01", 6000, 0, None, 30, 12,
     "Java 后端训练营的项目课一直没更新，我听了 12 节，要投诉你们，剩下的钱退给我。"),
    ("y06", "new", "boundary", "R3", "2026-09-25", "杨帆", "国画入门", "2026-09-01", 240, 0, None, 12, 6,
     "国画入门我听了 6 节，剩下 6 节不想上了，能退多少？"),
    ("y07", "new", "boundary", "R3", "2026-09-25", "黄磊", "托福强化班", "2026-09-16", 2400, 300, None, 24, 4,
     "托福强化班 9 月 16 号买的，原价 2400，听了 4 节，我要求全额退 2400，不然我会让律师处理。"),
    ("y08", "new", "boundary", "R3", "2026-09-25", "周婷", "考研政治全程", "2026-07-01", 2400, 0, (12, 200, 6), 30, 15,
     "考研政治全程我分期付了 6 期，课听了一半，想退掉剩下的，能退多少？"),
    ("y09", "new", "boundary", "R3", "2026-09-25", "吴昊", "剪辑入门", "2026-09-18", 1200, 120, None, 12, 1,
     "剪辑入门 9 月 18 号买的，只听了 1 节就发现画质很差，我要投诉，并且要全额退款。"),
    ("y10", "new", "boundary", "R3", "2026-09-26", "徐丽", "前端开发实战", "2026-09-14", 4800, 0, (6, 800, 1), 48, 4,
     "前端开发实战一共 4800，我分期付的，听了 4 节，现在要退，退 4800 对吧？不对的话我就打 12315。"),
]

TASK = (
    "你是在线教育机构的在线客服，专门回复学员的退款咨询。每次任务会告诉你今天的日期和学员发来的消息，"
    "工作目录里另有三份文件：这名学员的订单记录、机构的退款政策表、这家机构的客服工作规则。"
    "按这次给的工作规则写出要发给学员的那条回复，只输出这条回复本身，不要附加任何说明。"
)
ONBOARDING = "以后每次退款咨询，我都会把这次适用的客服工作规则、退款政策表和学员的订单记录一起发给你。不同机构的规则不一样，以当次给的为准。"
CRITERIA = [
    ("A-amount", "red_line",
     "退款判断和金额：按这次的工作规则和退款政策表，判断该全额退还是按比例退，回复里写出的应退金额与参考答案一致。"
     "金额只看数值，和参考答案相等就算对（例如 2160 元和 2160.00 元都算对）。"
     "退法判断错、应退金额写错、没写出应退金额（转人工的也要写），或答应了超出规则的退款（例如按标价或按没付的分期退），每处记一处；"
     "回复里写到的退款依据（今天是购课后第几天、已听节数、退款基数、按比例退的金额、手续费）和参考答案不一致的，也每处记一处。"),
    ("A-arrival", "standard",
     "到账时间：回复要告诉学员到账时间，并且只能用这次工作规则规定的说法。没写到账时间、到账时间写成别的说法或别的天数，"
     "或者回复里任何地方出现了“马上”“今天”“尽快”，每处记一处。"),
    ("A-escalate", "standard",
     "转人工：学员消息里出现这次工作规则列出的关键词时，回复必须写明转人工处理，并按规则告诉学员工单号怎么发给他（规则还要求说别的，也要说到）；"
     "漏了任何一样记一处。消息里没有这些关键词时，本项不适用。"),
    ("A-address", "standard",
     "称呼：按这次工作规则称呼学员；称呼不对，或用了规则不允许的称呼（如“亲”），记一处。"),
    ("A-length", "standard",
     "字数和推荐：回复字数不超过这次工作规则的上限（以测量值为准，超了记一处）；规则不许推荐课程（或不许发券、补偿）的场景里推荐了或发了，记一处。"),
]


def money(value) -> str:
    return f"{Decimal(value).quantize(Decimal('0.01'))}"


def compute(spec: tuple) -> dict:
    """参考答案：这道题按它的工作规则该怎么退、退多少，以及回复要满足的其他规则。"""
    name, group, segment, rule, today, student, course, buy, price, coupon, plan, total, attended, message = spec
    r = RULES[rule]
    kind = COURSES[course]
    days, lessons, rate = r["table"][kind]
    elapsed = (date.fromisoformat(today) - date.fromisoformat(buy)).days
    day = elapsed + 1 if r["same_day_is_one"] else elapsed
    paid_total = Decimal(price - coupon)
    if plan:
        periods, each, paid_periods = plan
        assert periods * each == price - coupon, f"{name}: installments do not add up to the paid price"
        base = Decimal(each * paid_periods)
    else:
        base = paid_total
    full = day <= days and attended <= lessons
    ref = {
        "规则集": f"{rule}（{r['org']}）",
        "课程类型": kind,
        "这一档": {"全额退天数": days, "全额退节数": lessons, "手续费比例": f"{rate}%"},
        "今天是购课后第几天（按这套规则的数法）": day,
        "已听节数": attended,
        "退款基数（实付或已付分期）": money(base),
    }
    if full:
        ref.update({"退法": "全额退", "应退金额": money(base)})
    else:
        prorated = base * (total - attended) / total
        fee = (prorated * rate / 100).quantize(Decimal("0.01"), ROUND_HALF_UP)
        note = ""
        if r["min_fee"] is not None and fee < r["min_fee"]:
            note = f"（按比例算的手续费 {money(fee)} 元不足 {money(r['min_fee'])} 元，按 {money(r['min_fee'])} 元收）"
            fee = r["min_fee"]
        assert prorated == prorated.quantize(Decimal("0.01")), f"{name}: prorated refund is not exact to the cent"
        ref.update({
            "退法": "按比例退",
            "按比例退的金额": f"{money(base)} × {total - attended} ÷ {total} = {money(prorated)}",
            "手续费": money(fee) + note,
            "应退金额": money(prorated - fee),
        })
    hits = [word for word in r["keywords"] if word in message]
    others = [word for other in RULES.values() for word in other["keywords"] if word in message and word not in r["keywords"]]
    assert not others, f"{name}: the message holds another rule set's keyword {others}"
    ref.update({
        "到账说法": r["arrival"],
        "需转人工": bool(hits),
        "消息里的关键词": hits or "无",
        "转人工时要告诉学员": r["notice"] if hits else "不适用",
        "称呼": r["address"] + (f"本题学员姓名：{student}。" if rule == "R3" else ""),
        "字数上限": r["limit"],
        "不许推荐": r["upsell"] + ("本题是投诉场景。" if hits else "本题不是投诉场景。"),
    })
    return ref


def rules_text(rule: str) -> str:
    r = RULES[rule]
    fee = "手续费 = 按比例退的金额 × 这一档的手续费比例"
    if r["min_fee"] is not None:
        fee += f"；算出来不足 {money(r['min_fee'])} 元的，按 {money(r['min_fee'])} 元收"
    return "\n".join([
        f"# {r['org']} · 客服退款工作规则",
        "",
        "1. 先查订单的课程类型，在《退款政策表》里找到这一档：购课后在“全额退天数”以内、并且已听节数不超过“全额退节数”的，全额退款；"
        "否则按未上的节数比例退款，再扣这一档的手续费。回复里写明退法（全额退还是按比例退）和应退金额，转人工的也要写。",
        f"2. 回复要告诉学员到账时间，只说“{r['arrival']}”；整条回复里不出现“马上”“今天”“尽快”这几个词。",
        "3. 学员消息里出现" + "、".join(f"“{w}”" for w in r["keywords"]) + f"中的任何一个，必须转人工处理，并告诉学员{r['notice']}。",
        f"4. {r['address']}",
        f"5. 回复不超过 {r['limit']} 字（字数按字符算，标点算，空格和换行不算）；{r['upsell']}",
        "",
        "补充口径：",
        "",
        f"- {r['first_day']}；“全额退天数”含当天，例如 7 天就是第 1 天到第 7 天。",
        "- 退款按实付金额算：用了优惠券的，按券后实际支付的金额；分期订单只算已经付了的期数，没付的期数直接取消，不用再付。",
        "- 按比例退的金额 = 退款基数 × 未上节数 ÷ 总节数；" + fee + "；应退金额 = 按比例退的金额 − 手续费。",
        "- 金额算到分（四舍五入到分）。",
        "",
    ])


def table_text(rule: str) -> str:
    r = RULES[rule]
    rows = [f"| {kind} | {d} 天 | {lessons} 节 | {rate}% |" for kind, (d, lessons, rate) in r["table"].items()]
    return "\n".join([
        f"# 退款政策表（{r['org']}）",
        "",
        "| 课程类型 | 全额退天数 | 全额退节数（已听不超过） | 手续费比例 |",
        "|---|---|---|---|",
        *rows,
        "",
    ])


def order_text(spec: tuple) -> str:
    name, group, segment, rule, today, student, course, buy, price, coupon, plan, total, attended, message = spec
    r = RULES[rule]
    lines = [
        "# 订单记录",
        "",
        f"- 订单号：{r['prefix']}{buy.replace('-', '')}{name.upper()}",
        f"- 学员：{student}",
        f"- 课程：{course}",
        f"- 课程类型：{COURSES[course]}",
        f"- 购课日期：{buy}",
        f"- 标价：{money(price)} 元",
        f"- 优惠券：{money(coupon) + ' 元' if coupon else '无'}",
        f"- 券后金额：{money(price - coupon)} 元",
    ]
    if plan:
        periods, each, paid = plan
        lines.append(
            f"- 付款方式：分 {periods} 期，每期 {money(each)} 元；已付 {paid} 期，共 {money(each * paid)} 元；还有 {periods - paid} 期未付"
        )
    else:
        lines.append(f"- 付款方式：全款，已付 {money(price - coupon)} 元")
    lines += [f"- 总节数：{total}", f"- 已听节数：{attended}", ""]
    return "\n".join(lines)


def question_text(spec: tuple) -> str:
    today, message = spec[4], spec[-1]
    return (
        f"今天是 {today}。学员发来消息：\n\n「{message}」\n\n"
        "这名学员的订单记录、机构的退款政策表和客服工作规则在工作目录：订单记录.md、退款政策表.md、工作规则.md。"
        "请写出回复学员的那条消息。"
    )


def scenario_package() -> None:
    (SCENARIO / "personas").mkdir(parents=True, exist_ok=True)
    (SCENARIO / "profile.md").write_text(TASK + "\n")
    (SCENARIO / "onboarding.md").write_text(ONBOARDING + "\n")
    (SCENARIO / "personas" / "student.md").write_text("学员发来退款咨询；每道题的消息、订单和规则由脚本给出。\n")
    (SCENARIO / "scenario.json").write_text(json.dumps({
        "initial": [],
        "criteria": [{"id": i, "check": text, "severity": severity} for i, severity, text in CRITERIA],
    }, ensure_ascii=False, indent=1) + "\n")
    visible = ["counterpart", "analyst", "curator"]
    (SCENARIO / "contract.json").write_text(json.dumps(
        {"checks": {i: {"visibility": visible} for i, _, _ in CRITERIA}}, ensure_ascii=False, indent=1) + "\n")


def main() -> None:
    names = [spec[0] for spec in SPECS]
    assert len(names) == len(set(names)) == 40
    (HERE / "rules").mkdir(exist_ok=True)
    for rule in RULES:
        (HERE / "rules" / f"{rule}.md").write_text(rules_text(rule))
    bank, scripts = [], []
    for spec in SPECS:
        name, group, segment, rule = spec[:4]
        files = {"工作规则.md": rules_text(rule), "退款政策表.md": table_text(rule), "订单记录.md": order_text(spec)}
        reference = compute(spec)
        bank.append({"name": name, "group": group, "segment": segment, "rules": rule,
                     "text": question_text(spec), "files": files, "reference": reference})
        label = {"train": "培养", "same": "考试·同规则", "new": "考试·新规则"}[group]
        scripts.append({"name": name, "title": f"{name} · {label} · {spec[6]}", "exam": group != "train",
                        "steps": [{"text": question_text(spec), "files": files}]})
    (HERE / "questions.json").write_text(json.dumps(bank, ensure_ascii=False, indent=1) + "\n")
    (HERE / "scripts.json").write_text(json.dumps(scripts, ensure_ascii=False, indent=1) + "\n")
    scenario_package()
    full = sum(q["reference"]["退法"] == "全额退" for q in bank)
    print(f"{len(bank)} questions ({full} full refunds), {len(RULES)} rule sets, scenario at {SCENARIO.name}")


if __name__ == "__main__":
    main()
