"""门店客单价：三套工作规则、40 道题（20 培养 + 10 道同规则考试 + 10 道换规则考试）、参考答案和 Studio 场景包。

  python3 make.py

依据《专家自进化》3.1 的案例改写成「工作规则随题交给员工」：三家连锁的客单价口径不同（公式、渠道怎么算、默认比上月
还是比去年同月、结论写几位小数、推测怎么标）。培养题和同规则考试题用 R1（青柚茶铺）、R2（麦穗烘焙）交替，换规则考试题
全用员工从没见过的 R3（拾光咖啡）。每道题一份按种子生成的门店日报（12 家店、每天每个渠道一行），按 SPECS 埋下原因
（优惠加大、团购单变少、外卖占比上升）和陷阱（渠道混算、零元单不剔、重复行、新开的店、环比同比用错、部分退款）。
生成时校验：按规则算出的下降最多的门店唯一且领先第二名至少 2 个百分点、结果离四舍五入的分界够远；每个陷阱都验证过
用错方法确实会得出别的门店。check.py 只读员工看到的文件另写一遍算法复核。
"""

import calendar
import csv
import hashlib
import io
import json
import random
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENARIO = HERE / "wkr-store-ticket"
CENT = Decimal("0.01")
CHANNELS = ("堂食", "外卖")
FIELDS = ["日期", "门店", "渠道", "订单数", "零元单数", "退款单数", "全额退款单数", "实收金额", "退款金额", "优惠金额", "团购订单数"]
OLD_FIELDS = ["营业日期", "店铺", "销售渠道", "单量", "0元单", "退单数", "整单退数", "实收", "退款额", "优惠额", "团购单量"]
OLD_CHANNEL = {"堂食": "店内", "外卖": "外送"}
GROUP = 3.0

RULES = {
    "R1": {
        "brand": "青柚茶铺", "kind": "茶饮",
        "stores": ["春熙路店", "太古里店", "天府广场店", "高新店", "双流店", "温江店", "郫都店", "龙泉店", "新都店", "金牛店",
                   "武侯店", "锦江店"],
        "new": "青羊店", "formula": "valid", "scope": "split", "places": 1, "amount": False, "default": "环比",
        "marker": "待确认",
        "levels": {"堂食": ((140, 300), (14, 19)), "外卖": ((70, 180), (22, 29))},
        "text": """# 青柚茶铺 · 门店客单价分析工作规则

1. 客单价 =（实收金额 − 退款金额）÷ 有效订单数；有效订单数 = 订单数 − 零元单数 − 全额退款单数。部分退款的订单仍算有效订单。
2. 默认比上月（环比）；只有问“同比”才比去年同月。
3. 外卖和堂食分开算、分开排名，不能混在一起：两个渠道各给一个下降最多的门店。
4. 第一句直接给结论：两个渠道各自下降最多的门店名和下降幅度（百分比，保留一位小数）。
5. 原因只写数据里看得到的，并写出数字（例如优惠金额占比、团购订单占比的变化）；推测的内容要标“待确认”。

补充口径：

- 下降幅度 =（基期客单价 − 本期客单价）÷ 基期客单价；计算过程中不取舍，最后结果再保留小数。
- 同一门店同一天同一渠道出现重复行的，只算一次。
- 基期没有数据的门店（例如新开的店）不参与排名，在结论里单独说明。
- 优惠金额占比 = 优惠金额 ÷（实收金额 + 优惠金额）；团购订单占比 = 团购订单数 ÷ 有效订单数。
- 去年的日报字段名和渠道名跟今年不一样，按《字段对照表》对应。
""",
    },
    "R2": {
        "brand": "麦穗烘焙", "kind": "烘焙",
        "stores": ["南京西路店", "徐家汇店", "陆家嘴店", "五角场店", "静安寺店", "中山公园店", "虹桥店", "七宝店", "莘庄店", "张江店",
                   "世纪大道店", "人民广场店"],
        "new": "前滩店", "formula": "gross", "scope": "combined", "places": 2, "amount": True, "default": "环比",
        "marker": "（推测）",
        "levels": {"堂食": ((120, 260), (30, 42)), "外卖": ((50, 120), None)},
        "text": """# 麦穗烘焙 · 门店客单价分析工作规则

1. 客单价 = 实收金额 ÷（订单数 − 零元单数）；退款不扣减，全额退款的订单也照常计入订单数。
2. 默认比上月（环比）；只有问“同比”才比去年同月。
3. 外卖和堂食合并算：同一门店两个渠道的数加总后再算客单价，只给一个排名。
4. 第一句直接给结论：下降最多的门店名、下降金额（元，保留两位小数）和下降幅度（百分比，保留两位小数）。
5. 原因要有数据依据并写出数字（例如外卖订单占比、优惠金额占比、团购订单占比的变化）；推测的内容要标“（推测）”。

补充口径：

- 下降金额 = 基期客单价 − 本期客单价；下降幅度 = 下降金额 ÷ 基期客单价；计算过程中不取舍，最后结果再保留小数。
- 同一门店同一天同一渠道出现重复行的，只算一次。
- 基期没有数据的门店（例如新开的店）不参与排名，在结论里单独说明。
- 外卖订单占比 = 外卖的（订单数 − 零元单数）÷ 两个渠道合计的（订单数 − 零元单数）；优惠金额占比 = 优惠金额 ÷（实收金额 + 优惠金额）；团购订单占比 = 团购订单数 ÷（订单数 − 零元单数）。
- 去年的日报字段名和渠道名跟今年不一样，按《字段对照表》对应。
""",
    },
    "R3": {
        "brand": "拾光咖啡", "kind": "咖啡",
        "stores": ["西湖店", "滨江店", "武林店", "钱江新城店", "萧山店", "余杭店", "拱墅店", "上城店", "下沙店", "临平店", "富阳店",
                   "桐庐店"],
        "new": "未来科技城店", "formula": "net", "scope": "dine", "places": 0, "amount": False, "default": "同比",
        "marker": "待核实",
        "levels": {"堂食": ((150, 320), (26, 34)), "外卖": ((60, 160), (30, 40))},
        "text": """# 拾光咖啡 · 门店客单价分析工作规则

1. 客单价 =（实收金额 − 退款金额）÷（订单数 − 零元单数）；全额退款的订单也计入订单数。
2. 默认比去年同月（同比）；只有问“环比”才比上月。
3. 只看堂食：客单价排名只算堂食，外卖不参与排名。
4. 第一句直接给结论：下降最多的门店名和下降幅度（百分比，四舍五入到整数）。
5. 原因只写数据里看得到的，并写出数字；推测的内容要标“待核实”。

补充口径：

- 下降幅度 =（基期客单价 − 本期客单价）÷ 基期客单价；计算过程中不取舍，最后结果再取整。
- 同一门店同一天同一渠道出现重复行的，只算一次。
- 基期没有数据的门店（例如新开的店）不参与排名，在结论里单独说明。
- 优惠金额占比 = 优惠金额 ÷（实收金额 + 优惠金额）；团购订单占比 = 团购订单数 ÷（订单数 − 零元单数）。
- 去年的日报字段名和渠道名跟今年不一样，按《字段对照表》对应。
""",
    },
}

# name, group, segment, rules, month, asked ("环比" / "同比" / None 用规则默认), plants {排名: (门店序号, 原因)},
# decoys [(陷阱, 门店序号, 渠道)], extras {"new": 有新开的店, "partial": 有部分退款, "last": 另给去年同月的日报}
# 原因：优惠 = 优惠加大；团购 = 团购单变少；外卖占比 = 外卖单占比上升（只用于合并算的 R2）
# 陷阱：mix 渠道混算会选它；zero 零元单不剔会选它；dup 不去重会选它；prev 用环比会选它；last 用同比会选它；
#       refund 扣了退款会选它（R2）；takeout 排外卖会选它（R3）
SPECS = [
    ("t01", "train", "common", "R1", "2026-08", None, {"外卖": (2, "优惠"), "堂食": (7, "团购")}, [("mix", 4, None)], {}),
    ("t02", "train", "common", "R2", "2026-07", None, {"合并": (5, "外卖占比")}, [("zero", 9, None)], {}),
    ("t03", "train", "common", "R1", "2026-06", None, {"外卖": (10, "团购"), "堂食": (1, "优惠")}, [("zero", 6, "外卖")], {}),
    ("t04", "train", "common", "R2", "2026-05", None, {"合并": (3, "优惠")}, [("zero", 0, None)], {}),
    ("t05", "train", "common", "R1", "2026-04", None, {"外卖": (8, "优惠"), "堂食": (5, "优惠")}, [("mix", 11, None)], {}),
    ("t06", "train", "common", "R2", "2026-09", None, {"合并": (7, "团购")}, [("zero", 2, None)], {}),
    ("t07", "train", "common", "R1", "2026-03", None, {"外卖": (0, "团购"), "堂食": (9, "团购")}, [("zero", 3, "堂食")], {}),
    ("t08", "train", "common", "R2", "2026-06", None, {"合并": (11, "外卖占比")}, [("zero", 4, None)], {}),
    ("t09", "train", "common", "R1", "2026-09", None, {"外卖": (6, "优惠"), "堂食": (2, "团购")}, [("mix", 8, None)], {}),
    ("t10", "train", "common", "R2", "2026-04", None, {"合并": (1, "优惠")}, [("zero", 10, None)], {}),
    ("t11", "train", "edge", "R1", "2026-08", None, {"外卖": (3, "优惠"), "堂食": (11, "团购")}, [("dup", 5, "堂食")],
     {"new": True, "partial": True}),
    ("t12", "train", "edge", "R2", "2026-07", "同比", {"合并": (8, "优惠")}, [("prev", 2, None)],
     {"new": True, "partial": True, "last": True}),
    ("t13", "train", "edge", "R1", "2026-05", "同比", {"外卖": (9, "团购"), "堂食": (4, "优惠")}, [("prev", 0, "外卖")],
     {"partial": True, "last": True}),
    ("t14", "train", "edge", "R2", "2026-06", None, {"合并": (4, "团购")}, [("dup", 10, None), ("refund", 6, None)],
     {"partial": True}),
    ("t15", "train", "edge", "R1", "2026-07", None, {"外卖": (1, "团购"), "堂食": (8, "优惠")},
     [("dup", 2, "外卖"), ("mix", 6, None)], {"partial": True}),
    ("t16", "train", "edge", "R2", "2026-08", "同比", {"合并": (0, "外卖占比")}, [("prev", 7, None), ("dup", 3, None)],
     {"partial": True, "last": True}),
    ("t17", "train", "edge", "R1", "2026-09", "同比", {"外卖": (5, "优惠"), "堂食": (0, "团购")}, [("prev", 10, "堂食")],
     {"new": True, "partial": True, "last": True}),
    ("t18", "train", "edge", "R2", "2026-05", None, {"合并": (9, "优惠")}, [("zero", 5, None)], {"new": True, "partial": True}),
    ("t19", "train", "edge", "R1", "2026-06", None, {"外卖": (11, "优惠"), "堂食": (3, "团购")},
     [("dup", 9, "堂食"), ("zero", 7, "外卖")], {"new": True, "partial": True}),
    ("t20", "train", "edge", "R2", "2026-09", "同比", {"合并": (6, "团购")}, [("prev", 11, None), ("refund", 1, None)],
     {"partial": True, "last": True}),
    ("x01", "same", "common", "R1", "2026-07", None, {"外卖": (4, "团购"), "堂食": (10, "优惠")}, [("mix", 1, None)], {}),
    ("x02", "same", "common", "R2", "2026-08", None, {"合并": (2, "团购")}, [("zero", 8, None)], {}),
    ("x03", "same", "common", "R1", "2026-05", None, {"外卖": (7, "优惠"), "堂食": (6, "团购")}, [("zero", 2, "堂食")], {}),
    ("x04", "same", "common", "R2", "2026-03", None, {"合并": (10, "外卖占比")}, [("zero", 3, None)], {}),
    ("x05", "same", "common", "R1", "2026-09", None, {"外卖": (9, "团购"), "堂食": (0, "优惠")}, [("mix", 5, None)], {}),
    ("x06", "same", "edge", "R2", "2026-06", None, {"合并": (11, "团购")}, [("dup", 4, None)], {"new": True, "partial": True}),
    ("x07", "same", "edge", "R1", "2026-08", "同比", {"外卖": (2, "团购"), "堂食": (7, "优惠")}, [("prev", 11, "外卖")],
     {"partial": True, "last": True}),
    ("x08", "same", "edge", "R2", "2026-04", "同比", {"合并": (5, "优惠")}, [("prev", 0, None)], {"partial": True, "last": True}),
    ("x09", "same", "edge", "R1", "2026-06", None, {"外卖": (8, "优惠"), "堂食": (4, "团购")}, [("dup", 1, "外卖")],
     {"new": True, "partial": True}),
    ("x10", "same", "edge", "R2", "2026-07", None, {"合并": (3, "团购")}, [("refund", 9, None), ("dup", 7, None)],
     {"partial": True}),
    ("y01", "new", "common", "R3", "2026-08", "环比", {"堂食": (3, "优惠")}, [("takeout", 8, "外卖")], {}),
    ("y02", "new", "common", "R3", "2026-06", "环比", {"堂食": (9, "团购")}, [("zero", 1, "堂食")], {}),
    ("y03", "new", "common", "R3", "2026-04", "环比", {"堂食": (0, "优惠")}, [("takeout", 5, "外卖")], {}),
    ("y04", "new", "common", "R3", "2026-09", "环比", {"堂食": (6, "团购")}, [("zero", 10, "堂食")], {}),
    ("y05", "new", "common", "R3", "2026-05", "环比", {"堂食": (11, "优惠")}, [("takeout", 2, "外卖")], {}),
    ("y06", "new", "edge", "R3", "2026-08", None, {"堂食": (4, "团购")}, [("prev", 7, "堂食")],
     {"new": True, "partial": True, "last": True}),
    ("y07", "new", "edge", "R3", "2026-07", None, {"堂食": (10, "优惠")}, [("prev", 3, "堂食"), ("dup", 1, "堂食")],
     {"partial": True, "last": True}),
    ("y08", "new", "edge", "R3", "2026-09", None, {"堂食": (2, "团购")}, [("prev", 9, "堂食"), ("zero", 6, "堂食")],
     {"partial": True, "last": True}),
    ("y09", "new", "edge", "R3", "2026-06", None, {"堂食": (8, "优惠")}, [("prev", 0, "堂食"), ("dup", 11, "堂食")],
     {"new": True, "partial": True, "last": True}),
    ("y10", "new", "edge", "R3", "2026-05", "环比", {"堂食": (5, "团购")}, [("last", 1, "堂食"), ("dup", 9, "堂食")],
     {"new": True, "partial": True, "last": True}),
]

OPENINGS = ["我是运营经理，", "周会要用：", "老板刚问我：", "区域督导想知道：", "月度复盘要用："]
TASK = (
    "你是连锁门店的数据分析助手。运营的同事会发来门店经营数据的问题，工作目录里有这次适用的工作规则和门店日报（CSV）。"
    "按这次给的工作规则算清楚、写结论，同事会直接拿去用。"
)
ONBOARDING = "以后每次分析门店数据，我都会把这次适用的工作规则和门店日报一起发给你。不同品牌的口径不一样，以当次给的为准。"
CRITERIA = [
    ("D-answer", "red_line",
     "结论：按这次工作规则（客单价公式、比上月还是比去年同月、渠道怎么算、重复行只算一次、基期没有数据的门店不排名）算出的"
     "下降最多的门店和下降幅度（规则要求时还有下降金额），与参考答案一致，并按规则的小数位数写。门店错、数值错、"
     "规则要求的排名没给（例如分渠道却只给了一个渠道）、给了规则不要的排名（例如只看堂食却还给了外卖或合并的排名），"
     "每处记一处；回复里写到的客单价、下降幅度等数字和参考答案对不上的，也每处记一处（四舍五入后一致就算对得上）。"),
    ("D-first", "standard",
     "第一句：回复的第一句话就是结论，包含规则第 4 条要求的内容；第一句是铺垫、复述问题或缺了要求的内容，记一处。"
     "这一项只看第一句的写法，第一句里的数算错记在“结论”里，不在这里重复记。"),
    ("D-reason", "standard",
     "原因：写的原因要是数据里看得到的并写出数字，数字和参考答案给的指标对得上（四舍五入后一致就算对得上）；"
     "没写原因、原因的数字对不上、把数据里看不到的推测当事实写（没按规则标注），每处记一处。"),
    ("D-scope", "standard",
     "基期没有数据的门店：不参与排名，并在结论里单独说明；没说明或把它排进去了，记一处。题里没有这类门店时本项不适用。"),
]


# ---------------- 数据生成 ----------------

def months(month: str) -> dict:
    y, m = map(int, month.split("-"))
    return {"cur": (y, m), "prev": (y, m - 1) if m > 1 else (y - 1, 12), "last": (y - 1, m)}


def days(period):
    y, m = period
    return [date(y, m, d) for d in range(1, calendar.monthrange(y, m)[1] + 1)]


def money(x: float) -> Decimal:
    return Decimal(f"{x:.2f}")


def base_params(rng, rule: str, partial: bool) -> dict:
    """Each store's level per channel: orders a day, ticket, zero, refund, group and discount shares."""
    r = RULES[rule]
    params = {}
    for store in r["stores"] + [r["new"]]:
        params[store] = {}
        dine_ticket = None
        for channel in CHANNELS:
            (lo, hi), tickets = r["levels"][channel]
            ticket = rng.uniform(*tickets) if tickets else dine_ticket * rng.uniform(0.58, 0.68)
            if channel == "堂食":
                dine_ticket = ticket
            params[store][channel] = {
                "orders": rng.uniform(lo, hi), "ticket": ticket, "zero": rng.uniform(0.01, 0.03),
                "full": rng.uniform(0.005, 0.012), "part": rng.uniform(0.01, 0.03) if partial else 0.0,
                "part_share": rng.uniform(0.3, 0.6), "group": rng.uniform(0.04, 0.08), "discount": rng.uniform(0.03, 0.07),
            }
    return params


def drifted(rng, p: dict) -> dict:
    return {**p, "orders": p["orders"] * rng.uniform(0.95, 1.05), "ticket": p["ticket"] * rng.uniform(0.985, 1.015),
            "group": max(0.0, p["group"] + rng.uniform(-0.005, 0.005)),
            "discount": max(0.0, p["discount"] + rng.uniform(-0.005, 0.005))}


def row(rng, store, channel, day, p, event=False):
    orders = round(p["orders"] * (1.2 if day.weekday() >= 5 else 1.0) * rng.uniform(0.85, 1.15) * (1.5 if event else 1.0))
    zero = round(orders * p["zero"] * rng.uniform(0.7, 1.3))
    full = round(orders * p["full"] * rng.uniform(0.5, 1.5))
    valid = orders - zero - full
    part = min(valid, round(orders * p["part"] * rng.uniform(0.5, 1.5)))
    group = min(valid, round(valid * (0.5 if event else p["group"]) * rng.uniform(0.8, 1.2)))
    ticket = p["ticket"] * rng.uniform(0.96, 1.04)
    listed_valid = (valid - group) * ticket + group * ticket * GROUP
    listed_full = full * ticket
    d = p["discount"]
    paid = money((listed_valid + listed_full) * (1 - d))
    refund = money(listed_full * (1 - d)) + money(part * ticket * p["part_share"] * (1 - d))
    return {"日期": day.isoformat(), "门店": store, "渠道": channel, "订单数": orders, "零元单数": zero,
            "退款单数": full + part, "全额退款单数": full, "实收金额": paid, "退款金额": refund,
            "优惠金额": money((listed_valid + listed_full) * d), "团购订单数": group}


def generate(spec, salt=0) -> tuple[list, list, list, dict]:
    """(this year's rows, duplicated rows appended, last year's rows, notes) for one question."""
    name, group, segment, rule, month, asked, plants, decoys, extras = spec
    r = RULES[rule]
    rng = random.Random(int(hashlib.sha256(f"{name}:{salt}".encode()).hexdigest()[:12], 16))
    compare = asked or r["default"]
    period = months(month)
    params = base_params(rng, rule, extras.get("partial", False))
    for ranking, (index, cause) in plants.items():
        if cause == "团购":
            for channel in (CHANNELS if ranking == "合并" else (ranking,)):
                params[r["stores"][index]][channel]["group"] = 0.12
    for kind, index, channel in decoys:
        if kind == "mix":
            levels = r["levels"]
            params[r["stores"][index]]["堂食"]["ticket"] = levels["堂食"][1][0]
            params[r["stores"][index]]["外卖"]["ticket"] = levels["外卖"][1][1]
    # plants hit the current month; against last year they also hit last month, so comparing with last month shows nothing
    hit = {"cur"} if compare == "环比" else {"prev", "cur"}
    per = {key: {s: {c: drifted(rng, p) for c, p in chans.items()} for s, chans in params.items()} for key in period}
    for ranking, (index, cause) in plants.items():
        store = r["stores"][index]
        for key in hit:
            for channel in (CHANNELS if ranking == "合并" else (ranking,)):
                q = per[key][store][channel]
                if cause == "优惠":
                    q["discount"] += 0.12
                elif cause == "团购":
                    q["group"] = 0.01
            if cause == "外卖占比":
                per[key][store]["外卖"]["orders"] *= 2.2
                per[key][store]["堂食"]["orders"] *= 0.7
    base_key = "prev" if compare == "环比" else "last"
    events = {}
    for kind, index, channel in decoys:
        store = r["stores"][index]
        if kind == "mix":
            per["cur"][store]["堂食"]["orders"] *= 2.2
            per["cur"][store]["外卖"]["orders"] *= 0.2
        elif kind == "zero":
            for c in (CHANNELS if channel is None else (channel,)):
                per["cur"][store][c]["zero"] = 0.30
        elif kind == "refund":
            for c in CHANNELS:
                per["cur"][store][c]["part"], per["cur"][store][c]["part_share"] = 0.35, 0.7
        elif kind == "takeout":
            per["cur"][store]["外卖"]["discount"] += 0.12
        elif kind == "prev":
            for c in (CHANNELS if channel is None else (channel,)):
                per["prev"][store][c]["group"] = 0.22
        elif kind == "last":
            per["last"][store][channel]["group"] = 0.22
        elif kind == "dup":
            for c in (CHANNELS if channel is None else (channel,)):
                events[(store, c)] = {days(period[base_key])[9], days(period[base_key])[19]}
    new = r["new"] if extras.get("new") else None
    this_year, dups, last_year, last_dups = [], [], [], []
    for key in ("prev", "cur", "last"):
        if key == "last" and not extras.get("last"):
            continue
        for day in days(period[key]):
            for store in r["stores"] + ([new] if new else []):
                if store == new and (key == "last" or (compare == "环比" and (key == "prev" or day.day < 16))):
                    continue
                for channel in CHANNELS:
                    event = day in events.get((store, channel), ())
                    one = row(rng, store, channel, day, per[key][store][channel], event)
                    (last_year if key == "last" else this_year).append(one)
                    if event:
                        (last_dups if key == "last" else dups).extend(dict(one) for _ in range(5))
    if new and compare == "同比":
        opened = f"{new}今年 {period['prev'][1]} 月之前开业，去年 {period['last'][1]} 月没有数据"
    elif new:
        opened = f"{new}{period['cur'][1]} 月 16 日新开，{period['prev'][1]} 月没有数据"
    else:
        opened = None
    return this_year, dups, last_year + last_dups, {"compare": compare, "period": period, "base": base_key, "new": new, "opened": opened,
                                                  "dup": bool(dups or last_dups)}


# ---------------- 口径（评价侧的标准算法） ----------------

def sums(rows, store, channels, period, dedup=True) -> dict | None:
    seen, total = set(), None
    prefix = f"{period[0]}-{period[1]:02d}-"
    for one in rows:
        if one["门店"] != store or one["渠道"] not in channels or not one["日期"].startswith(prefix):
            continue
        key = (one["日期"], one["门店"], one["渠道"])
        if dedup and key in seen:
            continue
        seen.add(key)
        total = total or {f: 0 for f in FIELDS[3:]}
        for f in FIELDS[3:]:
            total[f] += one[f]
    return total


def ticket(t: dict, formula: str, zero_out=True) -> Decimal:
    zero = t["零元单数"] if zero_out else 0
    if formula == "valid":
        return (t["实收金额"] - t["退款金额"]) / Decimal(t["订单数"] - zero - t["全额退款单数"])
    if formula == "gross":
        return t["实收金额"] / Decimal(t["订单数"] - zero)
    if formula == "net":
        return (t["实收金额"] - t["退款金额"]) / Decimal(t["订单数"] - zero)
    raise ValueError(formula)


def rankings(rows, stores, base, cur, formula, scope, dedup=True, zero_out=True) -> dict:
    groups = {"split": {"外卖": ("外卖",), "堂食": ("堂食",)}, "combined": {"合并": CHANNELS}, "dine": {"堂食": ("堂食",)},
              "takeout": {"外卖": ("外卖",)}}[scope]
    out = {}
    for key, channels in groups.items():
        ranked, skipped = [], []
        for store in stores:
            before, after = sums(rows, store, channels, base, dedup), sums(rows, store, channels, cur, dedup)
            if before is None or after is None:
                skipped.append(store)
                continue
            b, a = ticket(before, formula, zero_out), ticket(after, formula, zero_out)
            ranked.append({"store": store, "base": b, "cur": a, "drop": (b - a) / b, "before": before, "after": after})
        ranked.sort(key=lambda x: -x["drop"])
        out[key] = {"ranked": ranked, "skipped": skipped}
    return out


def safe(value: Decimal, places: int) -> bool:
    """True when value rounds the same way under any small error: its next digit is clear of the half."""
    scaled = value * Decimal(10) ** places
    frac = scaled - scaled.to_integral_value(rounding="ROUND_FLOOR")
    return abs(frac - Decimal("0.5")) >= Decimal("0.05")


def pct(value: Decimal, places: int) -> str:
    return f"{(value * 100).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)}%"


def shares(t: dict, formula: str, takeout: dict | None = None) -> dict:
    valid = t["订单数"] - t["零元单数"] - (t["全额退款单数"] if formula == "valid" else 0)
    out = {"优惠金额占比": t["优惠金额"] / (t["实收金额"] + t["优惠金额"]), "团购订单占比": Decimal(t["团购订单数"]) / valid}
    if takeout is not None:
        out["外卖订单占比"] = Decimal(takeout["订单数"] - takeout["零元单数"]) / (t["订单数"] - t["零元单数"])
    return out


# ---------------- 员工看到的文件 ----------------

def csv_text(rows, fields, rename=None) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(fields)
    for one in rows:
        values = [one[f] for f in FIELDS]
        if rename:
            values[2] = rename[values[2]]
        writer.writerow(values)
    return buffer.getvalue()


def mapping_text() -> str:
    lines = ["# 字段对照表（去年的日报 → 今年的日报）", "", "| 去年字段 | 今年字段 |", "|---|---|"]
    lines += [f"| {old} | {new} |" for old, new in zip(OLD_FIELDS, FIELDS)]
    lines += ["", "渠道名：去年的“店内”就是今年的“堂食”，去年的“外送”就是今年的“外卖”。", ""]
    return "\n".join(lines)


def question_text(spec, index, files) -> str:
    name, group, segment, rule, month, asked = spec[:6]
    m = int(month.split("-")[1])
    return (
        f"{OPENINGS[index % len(OPENINGS)]}{m} 月哪家门店客单价{asked or ''}下降最多？原因是什么？\n\n"
        "这次适用的工作规则和数据在工作目录：" + "、".join(files) + "。"
    )


# ---------------- 参考答案 ----------------

def compute(spec, this_year, dups, last_year, notes) -> dict:
    name, group, segment, rule, month, asked, plants, decoys, extras = spec
    r = RULES[rule]
    rows = this_year + dups + last_year
    period, compare = notes["period"], notes["compare"]
    base, cur = period[notes["base"]], period["cur"]
    stores = r["stores"] + ([notes["new"]] if notes["new"] else [])
    right = rankings(rows, stores, base, cur, r["formula"], r["scope"])
    assert set(right) == set(plants), name
    out = {}
    for key, result in right.items():
        ranked = result["ranked"]
        top, second = ranked[0], ranked[1]
        index, cause = plants[key]
        assert top["store"] == r["stores"][index], (name, key, top["store"], [(x["store"], round(float(x["drop"]), 4)) for x in ranked[:3]])
        assert Decimal("0.08") <= top["drop"] <= Decimal("0.25"), (name, key, top["drop"])
        assert top["drop"] - second["drop"] >= Decimal("0.02"), (name, key, top["drop"], second["drop"])
        assert safe(top["drop"] * 100, r["places"]), (name, key, top["drop"])
        if r["amount"]:
            assert safe(top["base"] - top["cur"], 2), (name, key)
        assert result["skipped"] == ([notes["new"]] if notes["new"] else []), (name, result["skipped"])
        channels = CHANNELS if key == "合并" else (key,)
        takeout = (lambda p: sums(rows, top["store"], ("外卖",), p)) if key == "合并" else (lambda p: None)
        before = shares(top["before"], r["formula"], takeout(base))
        after = shares(top["after"], r["formula"], takeout(cur))
        moved = {k: after[k] - before[k] for k in before}
        main = {"优惠": "优惠金额占比", "团购": "团购订单占比", "外卖占比": "外卖订单占比"}[cause]
        assert abs(moved[main]) >= Decimal("0.05"), (name, key, moved)
        assert all(abs(v) < Decimal("0.02") for k, v in moved.items() if k != main), (name, key, moved)
        entry = {
            "下降最多的门店": top["store"],
            "下降幅度（按规则取舍后）": pct(top["drop"], r["places"]),
            "下降幅度（未取舍，供核对四舍五入）": pct(top["drop"], 4),
            "基期客单价（未取舍）": f"{top['base'].quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)} 元",
            "本期客单价（未取舍）": f"{top['cur'].quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)} 元",
            "第二名": f"{second['store']}（下降 {pct(second['drop'], 4)}）",
            "原因（数据里看得到的变化）": f"{main}从 {pct(before[main], 4)} 变成 {pct(after[main], 4)}",
            "这家店的其他指标（基期 → 本期）": {k: f"{pct(before[k], 4)} → {pct(after[k], 4)}" for k in before if k != main},
            "各店下降幅度（未取舍，负数是上升）": {x["store"]: pct(x["drop"], 4) for x in ranked},
        }
        if r["amount"]:
            entry["下降金额（按规则取舍后）"] = f"{(top['base'] - top['cur']).quantize(CENT, rounding=ROUND_HALF_UP)} 元"
            entry["下降金额（未取舍）"] = f"{(top['base'] - top['cur']).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)} 元"
        out[key] = entry
        del channels
    traps = []
    for kind, index, channel in decoys:
        store = r["stores"][index]
        if kind == "mix":
            wrong = rankings(rows, stores, base, cur, r["formula"], "combined")["合并"]["ranked"]
            note = f"{store}：两个渠道混在一起算会排第一（它的堂食单多了、外卖单少了，单个渠道的客单价没怎么变）"
        elif kind == "zero":
            wrong = rankings(rows, stores, base, cur, r["formula"], r["scope"], zero_out=False)
            wrong = wrong.get(channel if r["scope"] != "combined" else "合并", {"ranked": []})["ranked"]
            note = f"{store}：本期{channel or '两个渠道的'}零元单大增，零元单不剔除会排第一"
        elif kind == "dup":
            wrong = rankings(rows, stores, base, cur, r["formula"], r["scope"], dedup=False)
            wrong = wrong[channel if r["scope"] == "split" else next(iter(wrong))]["ranked"]
            note = f"{store}：基期有两天的{channel or '两个渠道的'}行各多出 5 行一模一样的重复行（都是团购多的日子），不去重会排第一"
        elif kind == "prev":
            wrong = rankings(rows, stores, period["prev"], cur, r["formula"], r["scope"])
            wrong = wrong[channel if r["scope"] == "split" else next(iter(wrong))]["ranked"]
            note = f"{store}：上个月团购单特别多，用环比会排第一"
        elif kind == "last":
            wrong = rankings(rows, stores, period["last"], cur, r["formula"], r["scope"])
            wrong = wrong[next(iter(wrong))]["ranked"]
            note = f"{store}：去年同月团购单特别多，用同比会排第一"
        elif kind == "refund":
            wrong = rankings(rows, stores, base, cur, "valid", r["scope"])["合并"]["ranked"]
            note = f"{store}：本期部分退款大增，把退款扣掉会排第一"
        elif kind == "takeout":
            wrong = rankings(rows, stores, base, cur, r["formula"], "takeout")["外卖"]["ranked"]
            note = f"{store}：外卖客单价下降最多，排外卖会选到它（这套规则只看堂食）"
        else:
            raise ValueError(kind)
        assert wrong and wrong[0]["store"] == store, (name, kind, store, [(x["store"], round(float(x["drop"]), 4)) for x in wrong[:3]])
        traps.append(note)
    files_note = "今年的日报（上月和本月）" + ("，另有去年同月的日报（字段名不同）和字段对照表" if extras.get("last") else "")
    reference = {
        "规则集": f"{rule}（{r['brand']}）",
        "比较": f"{compare}：{cur[0]} 年 {cur[1]} 月比 {base[0]} 年 {base[1]} 月",
        "排名": out,
        "不参与排名的门店": notes["opened"] or "无（本题所有门店基期都有数据）",
        "数据里的情况": [files_note]
        + (["有重复行（同一门店同一天同一渠道多于一行），去重后只算一次"] if notes["dup"] else [])
        + (["有部分退款（退款单数大于全额退款单数）"] if extras.get("partial") else []),
        "这道题的陷阱（用错口径会得出的门店）": traps or ["无"],
        "推测的标注": f"“{r['marker']}”",
    }
    return reference


def scenario_package():
    (SCENARIO / "personas").mkdir(parents=True, exist_ok=True)
    (SCENARIO / "profile.md").write_text(TASK + "\n")
    (SCENARIO / "onboarding.md").write_text(ONBOARDING + "\n")
    (SCENARIO / "personas" / "manager.md").write_text("运营同事发来门店数据问题；每道题的问题、日报和工作规则由脚本给出。\n")
    (SCENARIO / "scenario.json").write_text(json.dumps({
        "initial": [],
        "criteria": [{"id": i, "check": text, "severity": severity} for i, severity, text in CRITERIA],
    }, ensure_ascii=False, indent=1) + "\n")
    visible = ["counterpart", "analyst", "curator"]
    (SCENARIO / "contract.json").write_text(json.dumps(
        {"checks": {i: {"visibility": visible} for i, _, _ in CRITERIA}}, ensure_ascii=False, indent=1) + "\n")


def main():
    names = [spec[0] for spec in SPECS]
    assert len(names) == len(set(names)) == 40
    (HERE / "rules").mkdir(exist_ok=True)
    for rule, r in RULES.items():
        (HERE / "rules" / f"{rule}.md").write_text(r["text"])
    bank, scripts, misses = [], [], []
    for index, spec in enumerate(SPECS):
        name, group, segment, rule = spec[:4]
        for salt in range(40):
            this_year, dups, last_year, notes = generate(spec, salt)
            try:
                reference = compute(spec, this_year, dups, last_year, notes)
                break
            except AssertionError as exc:
                misses.append((name, salt, str(exc)[:160]))
        else:
            raise RuntimeError(f"{name}: no seed passes the checks")
        files = {"工作规则.md": RULES[rule]["text"], "门店日报.csv": csv_text(this_year + dups, FIELDS)}
        if last_year:
            files["去年同月日报.csv"] = csv_text(last_year, OLD_FIELDS, OLD_CHANNEL)
            files["字段对照表.md"] = mapping_text()
        text = question_text(spec, index, list(files))
        bank.append({"name": name, "group": group, "segment": segment, "rules": rule, "text": text, "files": files,
                     "reference": reference})
        label = {"train": "培养", "same": "考试·同规则", "new": "考试·新规则"}[group]
        scripts.append({"name": name, "title": f"{name} · {label} · {RULES[rule]['brand']} {spec[4]}", "exam": group != "train",
                        "steps": [{"text": text, "files": files}]})
    (HERE / "questions.json").write_text(json.dumps(bank, ensure_ascii=False, indent=1) + "\n")
    (HERE / "scripts.json").write_text(json.dumps(scripts, ensure_ascii=False, indent=1) + "\n")
    scenario_package()
    size = sum(len(text) for q in bank for text in q["files"].values())
    for miss in misses:
        print("retried:", *miss)
    print(f"{len(bank)} questions, {len(RULES)} rule sets, files {size // 1024} KB, scenario at {SCENARIO.name}")


if __name__ == "__main__":
    main()
