"""营销海报审查：三套工作规则、40 道题（20 培养 + 10 道同规则考试 + 10 道换规则考试）、参考答案和 Studio 场景包。

  python3 make.py

依据《专家自进化》2.1 的案例改写成「工作规则随题交给员工」：三家门店的营销文案规则结构相同、口径不同（参考价怎么取、
赠品价值怎么写、效果承诺怎么处理、截止日期怎么写、交付分几段）。培养题和同规则考试题用 R1（燃点健身）、R2（青蔓瑜伽）
交替，换规则考试题全用员工从没见过的 R3（蓝湾游泳）。每道题给一份海报文案、活动开始日期和截止日期、60 天成交记录
（多种卡，含退款单、作废单、线上和门店两个渠道）、赠品门市价表、几百条的极限词表。成交记录按种子生成并埋陷阱：
窗口里更低的价出现在退款或作废单上、窗口外一天有更低的成交价；R3 的线上渠道还有更低价。参考答案由本脚本按规则算出；
check.py 只读员工看到的文件另写一遍算法复核。
"""

import csv
import io
import json
import random
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENARIO = HERE / "wkr-poster-review"
URGENCY = ["仅限前 100 名", "仅剩 50 份", "最后 3 天", "手慢无", "仅限前 50 名", "仅剩 20 个名额"]
STEMS = ["最低", "最便宜", "最好", "最强", "最大", "最快", "最优", "最全", "最佳", "最热", "最火", "最划算", "最专业", "最先进",
         "第一", "领先", "顶级", "顶尖", "极致", "王牌", "首选", "无敌", "独家", "首家", "首个", "唯一", "绝对"]
SCOPES = ["全网", "全城", "全国", "全市", "全行业", "史上", "业界", "本地", "宇宙", "行业"]
EXTRA = ["国家级", "世界级", "最高级", "百分之百", "100%", "万能", "永久", "秒杀全网", "零风险", "史无前例", "前所未有", "遥遥领先",
         "销量冠军", "全网爆款", "排名第一", "TOP1", "NO.1", "金牌", "王者", "巅峰"]


def word_list() -> list[str]:
    words = list(EXTRA) + STEMS + [scope + stem for scope in SCOPES for stem in STEMS[:14]]
    return sorted(set(words), key=lambda w: (len(w), w))


RULES = {
    "R1": {
        "brand": "燃点健身", "anniversary": 5, "price_word": "门市价", "window": 7, "how": "min", "channel": None,
        "cards": {"年卡": 2980, "季卡": 1180, "20 次卡": 1380},
        "gifts": {"私教课": (200, "节"), "毛巾礼包": (39, "份"), "体测": (99, "次"), "储物柜月租": (50, "个月")},
        "gift_rate": None, "promise": "3 个月瘦不下来全额退款",
        "promise_rule": "only_conditional", "conditions": ("每月到店体测、由教练记录", "在会员小程序“售后”入口申请"),
        "deadline": "活动截止日期：{m} 月 {d} 日", "sections": ("改后文案", "修改清单"),
    },
    "R2": {
        "brand": "青蔓瑜伽", "anniversary": 3, "price_word": "日常价", "window": 14, "how": "avg", "channel": None,
        "cards": {"年卡": 3680, "半年卡": 2080, "10 次卡": 980},
        "gifts": {"私教课": (260, "节"), "瑜伽垫": (129, "张"), "普拉提体验课": (180, "节"), "精油": (88, "瓶")},
        "gift_rate": None, "promise": "练不出马甲线全额退款",
        "promise_rule": "delete", "conditions": (),
        "deadline": "活动截至 {m} 月 {d} 日 24:00", "sections": ("修改后文案", "改动说明"),
    },
    "R3": {
        "brand": "蓝湾游泳", "anniversary": 8, "price_word": "门店价", "window": 7, "how": "min", "channel": "门店",
        "cards": {"年卡": 3280, "季卡": 1280, "儿童游泳班": 1680},
        "gifts": {"游泳课": (100, "节"), "泳镜": (69, "副"), "泳帽": (29, "顶"), "储物柜月租": (40, "个月")},
        "gift_rate": Decimal("0.8"), "promise": "学不会全额退款",
        "promise_rule": "only_conditional", "conditions": ("8 节课全勤", "在前台申请"),
        "deadline": "{m} 月 {d} 日截止", "sections": ("审查结论", "改后文案", "修改清单"),
    },
}

# name, group, segment, rules, start date, deadline, cards [(card, promo price, fake original)], gifts [(gift, qty)],
# poster's claimed gift value, promise?, absolute words picked from the list, urgency phrase
SPECS = [
    ("t01", "train", "common", "R1", "2026-10-12", "2026-10-31", [("年卡", 999, 3999)], [("私教课", 10)], 2000, True, ["全城最低"], "仅限前 100 名"),
    ("t02", "train", "common", "R2", "2026-10-20", "2026-11-05", [("年卡", 1999, 4999)], [("私教课", 4)], 1500, True, ["全网最低"], "仅剩 50 份"),
    ("t03", "train", "common", "R1", "2026-09-20", "2026-10-10", [("季卡", 599, 1999)], [("体测", 2)], 300, False, ["史上最强"], "最后 3 天"),
    ("t04", "train", "common", "R2", "2026-09-15", "2026-09-30", [("半年卡", 1299, 2999)], [("瑜伽垫", 1)], 199, True, ["顶级"], "手慢无"),
    ("t05", "train", "common", "R1", "2026-11-11", "2026-11-30", [("20 次卡", 699, 1680)], [("毛巾礼包", 2)], 100, True, ["第一"], "仅限前 50 名"),
    ("t06", "train", "common", "R2", "2026-11-20", "2026-12-10", [("10 次卡", 599, 1280)], [("精油", 2)], 200, False, ["全城最划算"], "仅剩 20 个名额"),
    ("t07", "train", "common", "R1", "2026-12-12", "2026-12-31", [("年卡", 1288, 3999)], [("私教课", 6)], 1200, True, ["全网最便宜"], "仅剩 50 份"),
    ("t08", "train", "common", "R2", "2026-12-18", "2027-01-05", [("年卡", 2280, 5999)], [("普拉提体验课", 2)], 400, True, ["业界领先"], "最后 3 天"),
    ("t09", "train", "common", "R1", "2026-10-15", "2026-11-05", [("季卡", 699, 1599)], [("储物柜月租", 3)], 200, False, ["顶尖"], "手慢无"),
    ("t10", "train", "common", "R2", "2026-10-20", "2026-11-10", [("半年卡", 1399, 3299)], [("私教课", 2)], 600, True, ["独家"], "仅限前 100 名"),
    ("t11", "train", "edge", "R1", "2026-10-03", "2026-10-31", [("年卡", 999, 3999), ("季卡", 499, 1999)], [("私教课", 4), ("毛巾礼包", 1)], 1000, True, ["全城最低", "王牌"], "仅限前 100 名"),
    ("t12", "train", "edge", "R2", "2026-11-02", "2026-11-20", [("年卡", 1999, 4999), ("10 次卡", 499, 1280)], [("瑜伽垫", 1), ("精油", 1)], 300, True, ["全网最低", "首选"], "仅剩 50 份"),
    ("t13", "train", "edge", "R1", "2026-12-02", "2026-12-25", [("年卡", 1288, 3999), ("20 次卡", 599, 1680)], [("体测", 1), ("储物柜月租", 2)], 300, False, ["史上最划算", "极致"], "最后 3 天"),
    ("t14", "train", "edge", "R2", "2026-10-04", "2026-10-22", [("半年卡", 1299, 2999), ("10 次卡", 599, 1280)], [("私教课", 2), ("普拉提体验课", 1)], 800, True, ["遥遥领先"], "手慢无"),
    ("t15", "train", "edge", "R1", "2026-11-05", "2026-11-28", [("季卡", 599, 1999), ("20 次卡", 699, 1680), ("年卡", 1199, 3999)], [("私教课", 2), ("体测", 1), ("毛巾礼包", 1)], 600, True, ["全国第一"], "仅剩 20 个名额"),
    ("t16", "train", "edge", "R2", "2026-12-03", "2026-12-24", [("年卡", 2280, 5999), ("半年卡", 1399, 3299)], [("瑜伽垫", 2), ("精油", 1)], 400, False, ["最佳", "王者"], "仅限前 50 名"),
    ("t17", "train", "edge", "R1", "2026-09-05", "2026-09-30", [("年卡", 999, 3999), ("20 次卡", 599, 1680)], [("私教课", 5), ("储物柜月租", 1)], 1200, True, ["行业首选"], "仅限前 100 名"),
    ("t18", "train", "edge", "R2", "2026-09-06", "2026-09-28", [("10 次卡", 499, 1280), ("年卡", 1888, 4999), ("半年卡", 1199, 2999)], [("私教课", 1), ("瑜伽垫", 1), ("精油", 2)], 600, True, ["全城最专业"], "最后 3 天"),
    ("t19", "train", "edge", "R1", "2027-01-02", "2027-01-25", [("季卡", 599, 1999), ("年卡", 1288, 3999)], [("体测", 2), ("毛巾礼包", 2)], 400, True, ["销量冠军"], "手慢无"),
    ("t20", "train", "edge", "R2", "2027-01-03", "2027-01-20", [("半年卡", 1299, 2999), ("年卡", 2088, 4999)], [("普拉提体验课", 2), ("精油", 1)], 600, True, ["国家级"], "仅剩 50 份"),
    ("x01", "same", "common", "R1", "2026-10-08", "2026-10-30", [("年卡", 1099, 3999)], [("私教课", 8)], 2000, True, ["全网第一"], "仅剩 20 个名额"),
    ("x02", "same", "common", "R2", "2026-11-22", "2026-12-10", [("年卡", 1888, 4999)], [("瑜伽垫", 2)], 300, True, ["顶尖"], "仅限前 50 名"),
    ("x03", "same", "common", "R1", "2026-12-20", "2027-01-10", [("20 次卡", 599, 1680)], [("体测", 1)], 199, False, ["极致"], "手慢无"),
    ("x04", "same", "common", "R2", "2026-09-22", "2026-10-12", [("10 次卡", 499, 1280)], [("普拉提体验课", 1)], 300, True, ["全城最低"], "最后 3 天"),
    ("x05", "same", "common", "R1", "2026-11-25", "2026-12-15", [("季卡", 599, 1999)], [("储物柜月租", 2)], 150, True, ["第一"], "仅限前 100 名"),
    ("x06", "same", "edge", "R2", "2026-12-05", "2026-12-28", [("年卡", 1999, 4999), ("半年卡", 1299, 2999)], [("私教课", 1), ("精油", 2)], 500, True, ["全网最低", "王牌"], "仅剩 50 份"),
    ("x07", "same", "edge", "R1", "2026-10-02", "2026-10-26", [("年卡", 999, 3999), ("季卡", 499, 1999)], [("私教课", 3), ("体测", 1)], 1000, True, ["全城最低", "首家"], "仅限前 100 名"),
    ("x08", "same", "edge", "R2", "2026-11-03", "2026-11-25", [("10 次卡", 599, 1280), ("年卡", 2088, 4999)], [("瑜伽垫", 1), ("普拉提体验课", 1)], 500, False, ["业界领先"], "手慢无"),
    ("x09", "same", "edge", "R1", "2026-12-04", "2026-12-30", [("20 次卡", 699, 1680), ("年卡", 1199, 3999), ("季卡", 599, 1999)], [("毛巾礼包", 1), ("储物柜月租", 3)], 300, True, ["史上最低"], "最后 3 天"),
    ("x10", "same", "edge", "R2", "2027-01-05", "2027-01-26", [("半年卡", 1399, 3299), ("10 次卡", 499, 1280)], [("私教课", 2), ("瑜伽垫", 1)], 800, True, ["首选", "巅峰"], "仅剩 20 个名额"),
    ("y01", "new", "common", "R3", "2026-10-09", "2026-10-31", [("年卡", 1288, 3999)], [("游泳课", 4)], 500, True, ["全城最低"], "仅限前 100 名"),
    ("y02", "new", "common", "R3", "2026-11-14", "2026-12-05", [("季卡", 599, 1599)], [("泳镜", 1)], 100, False, ["顶级"], "仅剩 50 份"),
    ("y03", "new", "common", "R3", "2026-12-16", "2027-01-08", [("儿童游泳班", 999, 2399)], [("游泳课", 2)], 300, True, ["第一"], "手慢无"),
    ("y04", "new", "common", "R3", "2026-09-18", "2026-10-08", [("年卡", 1388, 3999)], [("泳帽", 2)], 80, True, ["史上最划算"], "最后 3 天"),
    ("y05", "new", "common", "R3", "2026-10-24", "2026-11-15", [("季卡", 699, 1599)], [("储物柜月租", 2)], 100, False, ["全网第一"], "仅限前 50 名"),
    ("y06", "new", "edge", "R3", "2026-11-04", "2026-11-28", [("年卡", 1288, 3999), ("季卡", 599, 1599)], [("游泳课", 2), ("泳镜", 1)], 400, True, ["全城最低", "王牌"], "仅限前 100 名"),
    ("y07", "new", "edge", "R3", "2026-12-03", "2026-12-26", [("儿童游泳班", 999, 2399), ("季卡", 599, 1599)], [("泳帽", 2), ("泳镜", 1)], 200, True, ["独家"], "仅剩 50 份"),
    ("y08", "new", "edge", "R3", "2027-01-02", "2027-01-24", [("年卡", 1288, 3999), ("儿童游泳班", 1099, 2399)], [("游泳课", 3), ("储物柜月租", 1)], 500, False, ["业界领先"], "手慢无"),
    ("y09", "new", "edge", "R3", "2026-10-05", "2026-10-28", [("季卡", 599, 1599), ("年卡", 1388, 3999), ("儿童游泳班", 999, 2399)], [("游泳课", 2), ("泳帽", 1), ("泳镜", 1)], 400, True, ["行业首选"], "最后 3 天"),
    ("y10", "new", "edge", "R3", "2026-09-04", "2026-09-27", [("年卡", 1188, 3999), ("季卡", 499, 1599)], [("游泳课", 4), ("泳镜", 2)], 800, True, ["遥遥领先", "首家"], "仅剩 20 个名额"),
]

TASK = (
    "你是连锁门店市场部的文案审查员。市场部同事会把海报文案发给你审，工作目录里有这次适用的营销文案审查工作规则、"
    "近 60 天的成交记录、赠品门市价表和极限词表。按这次给的工作规则改好文案并列出修改，同事改完直接发布。"
)
ONBOARDING = "以后每份海报文案，我都会把这次适用的审查工作规则、成交记录、赠品门市价表和极限词表一起发给你。不同品牌的规则不一样，以当次给的为准。"
CRITERIA = [
    ("P-price", "red_line",
     "价格：改后文案里每种卡的参考价按这次工作规则的叫法和口径写对（数值以参考答案为准），不再出现“原价”这类规则不许的写法；"
     "某种卡的参考价算错、叫法不对、漏写，或文案里还留着“原价”，每处记一处。"),
    ("P-gift", "standard",
     "赠品：赠品价值按这次工作规则的写法写出算法（单价 × 数量，规则要求打折的也要写出），组合赠品逐项写出再相加，合计和参考答案"
     "一致；算法缺项、单价或数量错、合计错、没按规则写法写，每处记一处。"),
    ("P-claims", "standard",
     "承诺和截止日期：效果承诺按这次工作规则处理（该改成有条件退款的要把规则列的条件写全，该删的要删掉；海报里没有效果承诺时这一部分不适用）；"
     "截止日期按规则写法写上。每处不符记一处。"),
    ("P-words", "standard",
     "极限词和紧迫感说法：海报里出现的《极限词表》里的词和制造紧迫感的说法，在改后文案里都要删掉，也不能新加（测量值列出了改后文案里"
     "还能找到的极限词表词语）；留下或新加的，每处记一处。"),
    ("P-format", "standard",
     "交付格式：按这次工作规则要求的段数、段名（每段以“## 段名”开头）和清单格式交付，改过的地方都在清单里列出；段名或段数不对、"
     "清单格式不对、改了却没列，每处记一处。"),
]


def money(value) -> str:
    """An amount as exactly as it is: 55.2, not 55; 160, not 160.0."""
    value = Decimal(value)
    return f"{value.quantize(Decimal(1))}" if value == value.to_integral_value() else f"{value.normalize():f}"


def rules_text(rule: str) -> str:
    r = RULES[rule]
    word = r["price_word"]
    if r["how"] == "min":
        price = (f"1. 价格：写“{word} X 元”，X 是这种卡在活动开始前 {r['window']} 天里（不含开始当天）"
                 + (f"{r['channel']}渠道（不含线上）" if r["channel"] else "") + "的最低实际成交价；不写“原价”。")
    else:
        price = (f"1. 价格：写“{word} X 元”，X 是这种卡在活动开始前 {r['window']} 天里（不含开始当天）的平均实际成交价，"
                 "四舍五入到元；不写“原价”“门市价”。")
    first_gift = next(iter(r["gifts"]))
    unit_price, unit = r["gifts"][first_gift]
    if r["gift_rate"] is None and rule == "R1":
        gift = (f"2. 赠品写价值必须注明算法，写成“价值 X 元（{first_gift}单{unit}门市价 {unit_price} 元 × 10 {unit}）”；"
                "组合赠品逐项写出算法再相加。单价看《赠品门市价表》。")
    elif r["gift_rate"] is None:
        gift = (f"2. 赠品写价值时写成“总价值 X 元，含：{first_gift} {unit_price} 元 × 2 {unit} = {unit_price * 2} 元；…”，"
                "逐项写出单价 × 数量再相加。单价看《赠品门市价表》。")
    else:
        rate = int(r["gift_rate"] * 10)
        gift = (f"2. 赠品写价值时每项按门市价 × 数量再打 {rate} 折，写成“价值 X 元（{first_gift}单{unit}门市价 {unit_price} 元 × 2 {unit}"
                f" × {rate} 折）”；组合赠品逐项写出算法再相加。单价看《赠品门市价表》。")
    if r["promise_rule"] == "delete":
        promise = "3. 效果承诺（如“练不出马甲线全额退款”）一律删掉，不改写。"
    else:
        a, b = r["conditions"]
        promise = (f"3. 效果承诺（如“{r['promise']}”）只能写成有条件的退款：写明“{a}”和“{b}”；两样写不全就删掉这句承诺。")
    deadline = "4. 活动必须写截止日期（见题面），写成“" + r["deadline"].format(m="X", d="X") + "”。"
    words = "5. 《极限词表》里的词和制造紧迫感的说法（如“仅限前 N 名”“仅剩 N 份”“最后 N 天”“手慢无”）一律删掉，不换成别的极限或紧迫说法。"
    if len(r["sections"]) == 2 and rule == "R1":
        sections = "6. 交付两段：“## 改后文案”（直接能发布的完整文案）和“## 修改清单”（表格，三列：原文 | 改成 | 依据第几条）。"
    elif len(r["sections"]) == 2:
        sections = "6. 交付两段：“## 修改后文案”（直接能发布的完整文案）和“## 改动说明”（编号列表，每条写成：原文 → 改成（依据第几条））。"
    else:
        sections = ("6. 交付三段：“## 审查结论”（一句话：一共改了几处）、“## 改后文案”（直接能发布的完整文案）和“## 修改清单”"
                    "（表格，三列：原文 | 改成 | 依据第几条）。")
    supplement = ["- 实际成交价只看状态为“成交”的记录；“退款”“作废”的不算。", "- 参考价按卡种分别算；海报里有几种卡就写几种。",
                  f"- {r['window']} 天窗口可以跨月，例如活动 10 月 3 日开始、看前 7 天，就是 9 月 26 日到 10 月 2 日。"]
    if r["channel"]:
        supplement.append("- 成交记录里“渠道”为“线上”的不算，只看“门店”。")
    return "\n".join([f"# {r['brand']} · 营销文案审查工作规则", "", price, gift, promise, deadline, words, sections, "", "补充口径：", "",
                      *supplement, ""])


def records(spec, rng) -> tuple[list[dict], dict]:
    """60 days of sales before the start, per card on the poster plus one other card; traps planted per card."""
    name, group, segment, rule, start = spec[:5]
    r = RULES[rule]
    begin = date.fromisoformat(start)
    rows, notes = [], {}
    cards = [c[0] for c in spec[6]]
    others = [c for c in r["cards"] if c not in cards][:1]
    serial = 0
    for card in cards + others:
        listed = r["cards"][card]
        for back in range(60, 0, -1):
            day = begin - timedelta(days=back)
            for _ in range(rng.randint(1, 3)):
                serial += 1
                price = int(round(listed * rng.uniform(0.82, 1.0) / 10) * 10)
                rows.append({"日期": day.isoformat(), "订单号": f"S{day.strftime('%m%d')}{serial:04d}", "卡种": card,
                             "成交价": price, "状态": rng.choices(["成交", "退款", "作废"], [0.86, 0.08, 0.06])[0],
                             "渠道": rng.choice(["门店", "门店", "线上"])})
        if card not in cards:
            continue
        window = [row for row in rows if row["卡种"] == card and 1 <= (begin - date.fromisoformat(row["日期"])).days <= r["window"]]
        valid = [row for row in window if row["状态"] == "成交" and (r["channel"] is None or row["渠道"] == r["channel"])]
        floor = min(row["成交价"] for row in valid)
        trap_in = rng.choice(window)
        serial += 1
        rows.append({**trap_in, "订单号": f"S{date.fromisoformat(trap_in['日期']).strftime('%m%d')}{serial:04d}",
                     "成交价": floor - rng.choice([60, 80, 100]), "状态": rng.choice(["退款", "作废"])})
        outside = begin - timedelta(days=r["window"] + rng.randint(1, 3))
        serial += 1
        rows.append({"日期": outside.isoformat(), "订单号": f"S{outside.strftime('%m%d')}{serial:04d}", "卡种": card,
                     "成交价": floor - rng.choice([50, 70, 90]), "状态": "成交", "渠道": "门店"})
        if r["channel"]:
            day = begin - timedelta(days=rng.randint(1, r["window"]))
            serial += 1
            rows.append({"日期": day.isoformat(), "订单号": f"S{day.strftime('%m%d')}{serial:04d}", "卡种": card,
                         "成交价": floor - rng.choice([40, 60]), "状态": "成交", "渠道": "线上"})
    rows.sort(key=lambda row: (row["日期"], row["订单号"]))
    return rows, notes


def reference_price(rows, card, rule, start) -> tuple[Decimal, str]:
    r = RULES[rule]
    begin = date.fromisoformat(start)
    picked = [row for row in rows if row["卡种"] == card and 1 <= (begin - date.fromisoformat(row["日期"])).days <= r["window"]
              and row["状态"] == "成交" and (r["channel"] is None or row["渠道"] == r["channel"])]
    first, last = begin - timedelta(days=r["window"]), begin - timedelta(days=1)
    span = f"{first.isoformat()} 到 {last.isoformat()}"
    if r["how"] == "min":
        value = Decimal(min(row["成交价"] for row in picked))
        return value, f"{span}{('、' + r['channel'] + '渠道') if r['channel'] else ''}的 {len(picked)} 笔成交里最低 {value} 元"
    total = Decimal(sum(row["成交价"] for row in picked))
    exact = total / len(picked)
    assert abs(exact - exact.to_integral_value(rounding="ROUND_FLOOR") - Decimal("0.5")) > Decimal("0.01"), (card, exact)
    return exact.quantize(Decimal("1"), rounding=ROUND_HALF_UP), f"{span}的 {len(picked)} 笔成交合计 {total} 元，平均 {exact:.4f} 元"


def gift_value(spec) -> tuple[Decimal, list[str]]:
    r = RULES[spec[3]]
    total, parts = Decimal(0), []
    for gift, qty in spec[7]:
        unit_price, unit = r["gifts"][gift]
        value = Decimal(unit_price) * qty * (r["gift_rate"] or 1)
        total += value
        parts.append(f"{gift}单{unit}门市价 {unit_price} 元 × {qty} {unit}" + (f" × {int(r['gift_rate'] * 10)} 折" if r["gift_rate"] else "")
                     + f" = {money(value)} 元")
    return total, parts


def poster(spec) -> str:
    name, group, segment, rule, start, deadline, cards, gifts, claimed, promise, words, urgency = spec
    r = RULES[rule]
    begin = date.fromisoformat(start)
    prices = "，".join(f"{card}只要 {promo} 元（原价 {fake} 元）" for card, promo, fake in cards)
    gift_text = " + ".join(f"{gift} {qty} {r['gifts'][gift][1]}" for gift, qty in gifts)
    bits = [f"{r['brand']} {r['anniversary']} 周年庆！{words[0]}，{prices}，{urgency}！",
            f"办卡送价值 {claimed} 元的{gift_text}" + (f"，{r['promise']}！" if promise else "！")]
    if len(words) > 1:
        bits.append(f"{words[1]}服务，")
    bits.append(f"{begin.month} 月 {begin.day} 日起开抢。")
    return "".join(bits)


def sales_csv(rows) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["日期", "订单号", "卡种", "成交价", "状态", "渠道"], lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def gift_table(rule) -> str:
    lines = ["# 赠品门市价表", "", "| 赠品 | 门市价 |", "|---|---|"]
    lines += [f"| {gift} | {price} 元/{unit} |" for gift, (price, unit) in RULES[rule]["gifts"].items()]
    return "\n".join(lines) + "\n"


def words_text() -> str:
    return "# 极限词表（文案里不能出现）\n\n" + "\n".join(word_list()) + "\n"


def question_text(spec) -> str:
    start, deadline = date.fromisoformat(spec[4]), date.fromisoformat(spec[5])
    return (
        f"市场部发来一张海报的文案，活动 {start.isoformat()} 开始、{deadline.isoformat()} 截止：\n\n「{poster(spec)}」\n\n"
        "这次适用的审查工作规则、近 60 天成交记录、赠品门市价表和极限词表在工作目录：工作规则.md、成交记录.csv、"
        "赠品门市价表.md、极限词表.md。请按规则审改。"
    )


def compute(spec, rows) -> dict:
    name, group, segment, rule, start, deadline, cards, gifts, claimed, promise, words, urgency = spec
    r = RULES[rule]
    listed = set(word_list())
    copy = poster(spec)
    found = [w for w in word_list() if w in copy]
    assert all(any(w in phrase for w in found) for phrase in words), (name, words, found)
    prices = {}
    for card, promo, fake in cards:
        value, how = reference_price(rows, card, rule, start)
        assert value > promo, (name, card, value, promo)
        prices[card] = {"该写": f"{r['price_word']} {value} 元", "怎么算": how, "活动价": f"{promo} 元（不变）"}
    total, parts = gift_value(spec)
    end = date.fromisoformat(deadline)
    if not promise:
        promise_ref = "海报里没有效果承诺，本项这部分不适用"
    elif r["promise_rule"] == "delete":
        promise_ref = f"“{r['promise']}”要删掉，不改写"
    else:
        promise_ref = f"“{r['promise']}”改成有条件退款，写明“{r['conditions'][0]}”和“{r['conditions'][1]}”（两样都要写）"
    assert not [w for w in urgency.split() if w in listed]
    return {
        "规则集": f"{rule}（{r['brand']}）",
        "各卡参考价": prices,
        "赠品价值": {"该写": f"{money(total)} 元", "算法（逐项）": parts, "海报原来写的": f"{claimed} 元"},
        "效果承诺": promise_ref,
        "截止日期": "要写上：" + r["deadline"].format(m=end.month, d=end.day),
        "要删的说法（含极限词表里的词）": words,
        "海报里能找到的极限词表词语": found,
        "要删的紧迫感说法": [urgency],
        "交付段落": "、".join(f"## {s}" for s in r["sections"]),
        "原价": "“原价 X 元”的写法都要去掉",
    }


def scenario_package():
    (SCENARIO / "personas").mkdir(parents=True, exist_ok=True)
    (SCENARIO / "profile.md").write_text(TASK + "\n")
    (SCENARIO / "onboarding.md").write_text(ONBOARDING + "\n")
    (SCENARIO / "personas" / "marketer.md").write_text("市场部同事发来海报文案；每道题的文案、成交记录和规则由脚本给出。\n")
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
    for rule in RULES:
        (HERE / "rules" / f"{rule}.md").write_text(rules_text(rule))
    bank, scripts = [], []
    for spec in SPECS:
        name, group, segment, rule = spec[:4]
        if segment == "common":
            assert len(spec[6]) == 1 and len(spec[7]) == 1 and date.fromisoformat(spec[4]).day > RULES[rule]["window"], name
        else:
            assert len(spec[6]) > 1 and len(spec[7]) > 1 and date.fromisoformat(spec[4]).day <= RULES[rule]["window"], name
        for salt in range(20):
            rows, _ = records(spec, random.Random(f"{name}:{salt}"))
            try:
                reference = compute(spec, rows)
                break
            except AssertionError as exc:
                print("retried:", name, salt, str(exc)[:120])
        else:
            raise RuntimeError(f"{name}: no seed passes the checks")
        files = {"工作规则.md": rules_text(rule), "成交记录.csv": sales_csv(rows), "赠品门市价表.md": gift_table(rule),
                 "极限词表.md": words_text()}
        text = question_text(spec)
        bank.append({"name": name, "group": group, "segment": segment, "rules": rule, "text": text, "files": files,
                     "reference": reference})
        label = {"train": "培养", "same": "考试·同规则", "new": "考试·新规则"}[group]
        scripts.append({"name": name, "title": f"{name} · {label} · {RULES[rule]['brand']}", "exam": group != "train",
                        "steps": [{"text": text, "files": files}]})
    (HERE / "questions.json").write_text(json.dumps(bank, ensure_ascii=False, indent=1) + "\n")
    (HERE / "scripts.json").write_text(json.dumps(scripts, ensure_ascii=False, indent=1) + "\n")
    scenario_package()
    print(f"{len(bank)} questions, {len(word_list())} listed words, scenario at {SCENARIO.name}")


if __name__ == "__main__":
    main()
