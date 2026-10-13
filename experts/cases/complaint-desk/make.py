"""售后投诉处理：三套工作规则、40 道题（20 培养 + 10 道同规则考试 + 10 道换规则考试）、参考答案和 Studio 场景包。

  python3 make.py

依据《专家自进化》1.2 的案例改写成「工作规则随题交给员工」：三家电商的售后规则结构相同、数值和说法不同（质量问题
几天内能换能退、客服能直接给的补偿额度、迟到补券、第几起同款问题算系统性问题、回复分几段）。培养题和同规则考试题用
R1（栖木家居）、R2（启明电器）交替，换规则考试题全用员工从没见过的 R3（蓓乐母婴）。每道题的订单、本月 CRM 投诉记录
按 SPECS 生成：同款第几起由 SPECS 指定，边界题里有不同颜色后缀、分类为空只写描述、同一订单的重复工单、上月的工单、
这个订单之前发过补偿。参考答案由本脚本按规则算出；check.py 只读员工看到的文件另写一遍算法复核。
"""

import json
import random
from datetime import datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENARIO = HERE / "wkr-complaint-desk"
CENT = Decimal("0.01")
CATEGORIES = {
    "开裂": ("开裂", "裂缝", "裂纹"),
    "破损": ("磕碰", "掉漆", "划痕"),
    "异响": ("异响", "吱呀响", "一动就响"),
    "缺件": ("缺件", "少了零件", "配件不全"),
    "变形": ("变形", "翘起来", "不平"),
}

RULES = {
    "R1": {
        "brand": "栖木家居", "kind": "家具", "unit": "款号", "prefix": "QM",
        "window_h": 48, "options": ("免费换新", "全额退款"), "outside": "只提交质检申请",
        "rate": Decimal("0.05"), "cap": None, "late_days": 3, "late_inclusive": False, "coupon": Decimal("50"),
        "coupon_in_quota": True, "systemic": 3, "mark": "系统性问题", "notify": "品控",
        "sections": ("投诉分析", "回复草稿", "处理方式", "CRM 更新"),
        "products": {"DT": "实木餐桌", "CY": "餐椅", "SF": "布艺沙发", "CG": "床头柜", "SJ": "书架", "YG": "衣柜"},
        "colors": ("WN", "OK", "BK", "GY"),
    },
    "R2": {
        "brand": "启明电器", "kind": "小家电", "unit": "型号", "prefix": "QD",
        "window_h": 168, "options": ("换新", "退货退款"), "outside": "只安排上门检测",
        "rate": Decimal("0.04"), "cap": None, "late_days": 2, "late_inclusive": False, "coupon": Decimal("20"),
        "coupon_in_quota": True, "systemic": 2, "mark": "批次风险", "notify": "质检",
        "sections": ("情况判断", "给客户的回复", "内部处理"),
        "products": {"KF": "咖啡机", "XC": "吸尘器", "JS": "加湿器", "DF": "电饭煲", "KZ": "空气炸锅", "JH": "净化器"},
        "colors": ("W", "B", "S"),
    },
    "R3": {
        "brand": "蓓乐母婴", "kind": "母婴用品", "unit": "款号", "prefix": "BL",
        "window_h": 360, "options": ("换新", "退款", "免费维修"), "outside": "只提供免费维修",
        "rate": Decimal("0.08"), "cap": Decimal("100"), "late_days": 5, "late_inclusive": True, "coupon": Decimal("80"),
        "coupon_in_quota": False, "systemic": 4, "mark": "重点跟进", "notify": "供应链",
        "sections": ("问题判断", "客户回复", "处理方案", "补偿明细", "CRM 更新"),
        "products": {"TC": "婴儿推车", "AZ": "安全座椅", "CC": "婴儿床", "CY": "餐椅", "WN": "温奶器", "XD": "消毒柜"},
        "colors": ("PK", "BL", "GN"),
    },
}
OPENINGS = {"R1": "你好，", "R2": "客服在吗？", "R3": "你好客服，"}

# name, group, segment, rules, now, customer, product code, color, amount, promised, delivered, signed hours before now,
# prior compensation on this order, issue, demand (元 or None), crm: (k 本月同款同问题的其他订单数, dup 本单已有同问题工单,
# alt 其中不同颜色的个数, blank 其中分类为空的个数, twice 其中重复工单的个数, old 上月同款同问题的工单数)
SPECS = [
    ("t01", "train", "common", "R1", "2026-09-27 10:30", "周敏", "DT08", "WN", 3280, "2026-09-22", "2026-09-26", 20, 0, "开裂", 500, (2, False, 0, 0, 0, 0)),
    ("t02", "train", "common", "R2", "2026-09-26 15:10", "陈立", "KF20", "W", 1599, "2026-09-20", "2026-09-23", 70, 0, "异响", 200, (1, False, 0, 0, 0, 0)),
    ("t03", "train", "common", "R1", "2026-09-25 09:00", "王岚", "SF03", "GY", 4599, "2026-09-18", "2026-09-19", 30, 0, "破损", 300, (0, False, 0, 0, 0, 0)),
    ("t04", "train", "common", "R2", "2026-09-27 11:20", "李航", "XC11", "B", 2199, "2026-09-21", "2026-09-22", 100, 0, "缺件", 100, (0, False, 0, 0, 0, 0)),
    ("t05", "train", "common", "R1", "2026-09-26 16:40", "赵婷", "CY12", "OK", 1299, "2026-09-20", "2026-09-25", 10, 0, "开裂", 100, (3, False, 0, 0, 0, 0)),
    ("t06", "train", "common", "R2", "2026-09-25 10:00", "孙悦", "JS05", "S", 699, "2026-09-15", "2026-09-17", 200, 0, "异响", 50, (2, False, 0, 0, 0, 0)),
    ("t07", "train", "common", "R1", "2026-09-27 14:00", "吴凯", "CG07", "WN", 1299, "2026-09-23", "2026-09-24", 72, 0, "破损", 200, (1, False, 0, 0, 0, 0)),
    ("t08", "train", "common", "R2", "2026-09-26 09:30", "郑楠", "DF09", "W", 1299, "2026-09-20", "2026-09-24", 30, 0, "变形", 20, (0, False, 0, 0, 0, 0)),
    ("t09", "train", "common", "R1", "2026-09-25 20:15", "冯琪", "SJ02", "BK", 1999, "2026-09-18", "2026-09-22", 40, 0, "变形", 50, (1, False, 0, 0, 0, 0)),
    ("t10", "train", "common", "R2", "2026-09-27 13:45", "何畅", "KZ03", "B", 999, "2026-09-22", "2026-09-26", 18, 0, "破损", 300, (1, False, 0, 0, 0, 0)),
    ("t11", "train", "edge", "R1", "2026-09-27 10:00", "林涛", "DT08", "OK", 3280, "2026-09-21", "2026-09-26", 22, 0, "开裂", 500, (2, False, 1, 1, 0, 1)),
    ("t12", "train", "edge", "R2", "2026-09-26 18:00", "高远", "KF20", "B", 1599, "2026-09-19", "2026-09-22", 90, 20, "异响", 100, (1, False, 1, 1, 1, 0)),
    ("t13", "train", "edge", "R1", "2026-09-26 11:00", "马骁", "SF03", "WN", 4599, "2026-09-17", "2026-09-22", 46, 100, "破损", 300, (1, True, 0, 1, 1, 1)),
    ("t14", "train", "edge", "R2", "2026-09-27 09:40", "罗静", "XC11", "W", 2199, "2026-09-20", "2026-09-24", 60, 0, "缺件", 66, (0, True, 0, 0, 1, 1)),
    ("t15", "train", "edge", "R1", "2026-09-25 15:30", "梁宇", "CY12", "GY", 1999, "2026-09-19", "2026-09-24", 26, 20, "开裂", 30, (2, False, 2, 1, 1, 0)),
    ("t16", "train", "edge", "R2", "2026-09-26 12:00", "宋扬", "JS05", "B", 699, "2026-09-18", "2026-09-21", 150, 0, "异响", 50, (1, True, 1, 1, 0, 1)),
    ("t17", "train", "edge", "R1", "2026-09-27 16:20", "唐瑶", "CG07", "BK", 1299, "2026-09-21", "2026-09-26", 49, 0, "破损", 100, (2, False, 1, 2, 1, 1)),
    ("t18", "train", "edge", "R2", "2026-09-25 19:00", "韩雪", "DF09", "S", 1299, "2026-09-18", "2026-09-22", 66, 30, "变形", 10, (0, False, 0, 0, 0, 2)),
    ("t19", "train", "edge", "R1", "2026-09-26 08:50", "曹阳", "SJ02", "OK", 1999, "2026-09-18", "2026-09-25", 18, 30, "变形", 200, (1, True, 1, 1, 1, 0)),
    ("t20", "train", "edge", "R2", "2026-09-27 17:30", "许诺", "KZ03", "W", 999, "2026-09-21", "2026-09-25", 40, 0, "破损", 200, (1, False, 1, 1, 1, 1)),
    ("x01", "same", "common", "R1", "2026-09-27 12:00", "邓欣", "DT08", "BK", 3280, "2026-09-21", "2026-09-25", 40, 0, "开裂", 500, (1, False, 0, 0, 0, 0)),
    ("x02", "same", "common", "R2", "2026-09-26 10:20", "彭程", "KF20", "S", 1599, "2026-09-20", "2026-09-21", 120, 0, "异响", 30, (1, False, 0, 0, 0, 0)),
    ("x03", "same", "common", "R1", "2026-09-25 17:00", "蒋悦", "SF03", "OK", 4599, "2026-09-19", "2026-09-23", 60, 0, "破损", 200, (2, False, 0, 0, 0, 0)),
    ("x04", "same", "common", "R2", "2026-09-27 08:30", "沈航", "XC11", "S", 2199, "2026-09-18", "2026-09-22", 180, 0, "缺件", 100, (0, False, 0, 0, 0, 0)),
    ("x05", "same", "common", "R1", "2026-09-26 14:10", "袁梦", "CY12", "WN", 899, "2026-09-20", "2026-09-23", 30, 0, "开裂", 40, (2, False, 0, 0, 0, 0)),
    ("x06", "same", "edge", "R2", "2026-09-26 16:00", "潘越", "JS05", "W", 699, "2026-09-19", "2026-09-23", 50, 5, "异响", 20, (1, False, 1, 1, 1, 1)),
    ("x07", "same", "edge", "R1", "2026-09-27 11:00", "杜鹃", "CG07", "OK", 1299, "2026-09-20", "2026-09-25", 30, 10, "破损", 100, (1, True, 1, 1, 1, 1)),
    ("x08", "same", "edge", "R2", "2026-09-25 13:30", "姚斌", "DF09", "B", 1299, "2026-09-17", "2026-09-20", 110, 0, "变形", 20, (1, False, 1, 1, 0, 1)),
    ("x09", "same", "edge", "R1", "2026-09-26 19:40", "范琳", "SJ02", "GY", 1999, "2026-09-19", "2026-09-24", 47, 40, "变形", 300, (2, False, 2, 1, 1, 1)),
    ("x10", "same", "edge", "R2", "2026-09-27 15:15", "方哲", "KZ03", "S", 999, "2026-09-20", "2026-09-24", 30, 10, "破损", 10, (0, True, 0, 0, 1, 1)),
    ("y01", "new", "common", "R3", "2026-09-27 10:00", "张敏", "TC01", "PK", 2680, "2026-09-18", "2026-09-24", 60, 0, "异响", 500, (2, False, 0, 0, 0, 0)),
    ("y02", "new", "common", "R3", "2026-09-26 14:30", "李浩", "AZ06", "BL", 1890, "2026-09-20", "2026-09-22", 300, 0, "破损", 100, (3, False, 0, 0, 0, 0)),
    ("y03", "new", "common", "R3", "2026-09-25 11:00", "王芳", "CC03", "GN", 990, "2026-09-15", "2026-09-20", 100, 0, "变形", 60, (1, False, 0, 0, 0, 0)),
    ("y04", "new", "common", "R3", "2026-09-27 09:20", "刘洋", "CY02", "PK", 599, "2026-09-16", "2026-09-19", 400, 0, "开裂", 50, (0, False, 0, 0, 0, 0)),
    ("y05", "new", "common", "R3", "2026-09-26 17:45", "陈静", "WN08", "BL", 329, "2026-09-18", "2026-09-25", 30, 0, "缺件", 30, (2, False, 0, 0, 0, 0)),
    ("y06", "new", "edge", "R3", "2026-09-27 15:00", "杨帆", "TC01", "BL", 2680, "2026-09-17", "2026-09-22", 80, 40, "异响", 300, (3, False, 1, 1, 1, 1)),
    ("y07", "new", "edge", "R3", "2026-09-26 10:40", "黄磊", "AZ06", "GN", 1890, "2026-09-19", "2026-09-24", 350, 0, "破损", 200, (2, True, 1, 1, 1, 0)),
    ("y08", "new", "edge", "R3", "2026-09-25 16:00", "周婷", "CC03", "PK", 990, "2026-09-16", "2026-09-21", 70, 30, "变形", 50, (3, False, 1, 2, 1, 1)),
    ("y09", "new", "edge", "R3", "2026-09-27 12:30", "吴昊", "XD04", "GN", 1280, "2026-09-18", "2026-09-23", 20, 0, "开裂", 100, (2, False, 1, 1, 0, 2)),
    ("y10", "new", "edge", "R3", "2026-09-26 09:10", "徐丽", "WN08", "PK", 329, "2026-09-17", "2026-09-26", 12, 10, "缺件", 40, (1, True, 1, 1, 1, 1)),
]

TASK = (
    "你是电商的售后客服，处理客户的投诉。每次任务会告诉你现在的时间和客户发来的消息，工作目录里另有四份文件：这家店的"
    "售后工作规则、客户的订单记录、本月的 CRM 投诉记录和问题分类表。按这次给的工作规则处理这起投诉，按规则要求的分段"
    "交出结果。"
)
ONBOARDING = "以后每起售后投诉，我都会把这次适用的售后工作规则、订单记录、本月 CRM 投诉记录和问题分类表一起发给你。不同店的规则不一样，以当次给的为准。"
CRITERIA = [
    ("B-resolution", "red_line",
     "处理方式：按这次工作规则判断这起质量问题在不在可换可退的时限内（以参考答案为准）。在时限内的，回复里要把规则列出的"
     "几种处理方式都给客户，不能只给优惠券或只给其中一种；超出时限的，只能给规则写的那一种做法，不能答应换新或退款。"
     "每处不符记一处。"),
    ("B-money", "red_line",
     "补偿：迟到补券给没给对（该给没给、不该给却给、面额错）；补偿额度算没算对（回复或分段里写到的额度、已用、剩余和参考答案"
     "对不上）；客户要的补偿超出客服能直接给的额度时，回复里先答应了、或没说明要主管审批；没超出时却拒绝了。每处记一处。"),
    ("B-systemic", "standard",
     "同款问题计数：写到的“本月同款同问题第几起”和参考答案一致；到了规则的起数要在 CRM 更新里按规则标记并通知规则写的部门，"
     "没到就不能标。计数错、该标没标、不该标却标了、标记用词或通知部门不对，每处记一处。"),
    ("B-format", "standard",
     "分段：严格按这次工作规则要求的段数、段名和顺序输出（每段以“## 段名”开头）；多段、少段、段名不对、顺序不对，每处记一处。"),
]


def dates(spec) -> tuple[str, str, datetime, int]:
    """(promised, delivered, signed, days late): the spec's two dates only set how late it came; delivery is the day the
    customer signed (now − hours), so the order record never has a signature before the delivery."""
    now, promised, delivered, hours = spec[4], spec[9], spec[10], spec[11]
    late = (datetime.fromisoformat(delivered) - datetime.fromisoformat(promised)).days
    signed = datetime.strptime(now, "%Y-%m-%d %H:%M") - timedelta(hours=hours)
    return (signed.date() - timedelta(days=late)).isoformat(), signed.date().isoformat(), signed, late


def money(value) -> str:
    return f"{Decimal(value).quantize(CENT)}"


def rules_text(rule: str) -> str:
    r = RULES[rule]
    window = f"{r['window_h']} 小时" if r["window_h"] < 168 else f"{r['window_h'] // 24} 天"
    options = "、".join(r["options"])
    quota = f"订单金额的 {int(r['rate'] * 100)}%" + (f"，并且最多 {money(r['cap'])} 元" if r["cap"] else "")
    late = f"{r['late_days']} 天以上（{'含' if r['late_inclusive'] else '不含'} {r['late_days']} 天）"
    coupon = f"补 {money(r['coupon'])} 元无门槛券，" + ("计入补偿额度" if r["coupon_in_quota"] else "这张券不计入补偿额度")
    sections = "、".join(r["sections"])
    return "\n".join([
        f"# {r['brand']} · 售后投诉工作规则",
        "",
        f"1. 质量问题在签收后 {window}内的，客户可选{options}，回复里要把这几种都给客户；只给优惠券不算处理。"
        f"签收超过 {window}的，{r['outside']}，回复里不直接答应换新或退款。",
        f"2. 客服能直接给的补偿不超过{quota}；超过的要主管审批，回复里不能先答应。",
        f"3. 送货比承诺日期晚了 {late}，{coupon}。",
        f"4. 同{r['unit']}同问题本月第 {r['systemic']} 起起，CRM 标“{r['mark']}”并通知{r['notify']}。",
        f"5. 按 {len(r['sections'])} 段输出：{sections}；每段以“## 段名”开头，不加别的段。",
        "",
        "补充口径：",
        "",
        f"- 同{r['unit']}按{r['unit']}判断，不看颜色后缀：{r['unit']}最后一段是颜色，例如 {r['prefix']}-DT08-WN 和 "
        f"{r['prefix']}-DT08-OK 是同一{r['unit']}。",
        "- 同一问题按 CRM 的问题分类判断；分类为空的，按《问题分类表》里的说法归类。",
        "- 同一订单的重复工单只算一起；这次投诉也算一起，但这个订单本月已经有同一问题的工单的，不再多算。只算本月的工单。",
        "- 补偿额度按订单累计：这个订单之前已经发过的补偿要从额度里扣掉。金额算到分。",
        f"- 晚了几天 = 实际送达日期 − 承诺送达日期；签收后过了多久按签收时间到现在的时间算。",
        "",
    ])


def category_text() -> str:
    lines = ["# 问题分类表", "", "| 问题分类 | 客户常见说法 |", "|---|---|"]
    lines += [f"| {cat} | {'、'.join(words)} |" for cat, words in CATEGORIES.items()]
    return "\n".join(lines) + "\n"


def code(rule, product, color):
    return f"{RULES[rule]['prefix']}-{product}-{color}"


def crm_rows(spec, rng) -> list[dict]:
    """This month's tickets and a few of last month's: k other orders on the same style and issue (some on another
    color, some with an empty category, some ticketed twice), this order's own earlier ticket when `dup`, and noise."""
    name, group, segment, rule, now, customer, product, color, amount, promised, delivered, hours, prior, issue, demand, crm = spec
    k, dup, alt, blank, twice, old = crm
    r = RULES[rule]
    now_dt = datetime.strptime(now, "%Y-%m-%d %H:%M")
    month_start = now_dt.replace(day=1, hour=9, minute=0)
    others = [c for c in r["colors"] if c != color]
    other_products = [p for p in r["products"] if not product.startswith(p)]
    rows, serial = [], 0

    def day(within_month=True):
        if within_month:
            return month_start + timedelta(days=rng.randint(0, now_dt.day - 2), hours=rng.randint(0, 9))
        return month_start - timedelta(days=rng.randint(2, 25), hours=rng.randint(0, 9))

    def add(order, style, category, words, when, comp=0):
        nonlocal serial
        serial += 1
        rows.append({"工单号": f"T{when.strftime('%m%d')}{serial:03d}", "日期": when.strftime("%Y-%m-%d %H:%M"),
                     "订单号": order, r["unit"]: style, "问题分类": category, "问题描述": words, "已发补偿（元）": money(comp)})

    for i in range(k):
        order = f"{r['prefix']}{now_dt.strftime('%m')}{rng.randint(10000, 99999)}"
        style = code(rule, product, others[i % len(others)] if i < alt else color)
        blank_here = i < blank
        words = f"客户说{rng.choice(CATEGORIES[issue])}"
        when = day()
        add(order, style, "" if blank_here else issue, words, when, rng.choice([0, 0, 20, 30]))
        if i < twice:
            add(order, style, "" if blank_here else issue, words + "（客户再次来电）", when + timedelta(hours=5))
    if dup:
        add(spec[0].upper() + "-ORDER", code(rule, product, color), issue, f"客户说{CATEGORIES[issue][0]}", day())
    for _ in range(old):
        add(f"{r['prefix']}08{rng.randint(10000, 99999)}", code(rule, product, color), issue, f"客户说{CATEGORIES[issue][1]}",
            day(within_month=False), 20)
    noise_categories = [c for c in CATEGORIES if c != issue]
    for _ in range(rng.randint(12, 18)):
        if rng.random() < 0.45:
            style = code(rule, product, rng.choice(r["colors"]))
            category = rng.choice(noise_categories)
        else:
            style = code(rule, rng.choice(other_products) + f"{rng.randint(1, 20):02d}", rng.choice(r["colors"]))
            category = rng.choice(list(CATEGORIES))
        blank_here = rng.random() < 0.15
        add(f"{r['prefix']}{now_dt.strftime('%m')}{rng.randint(10000, 99999)}", style, "" if blank_here else category,
            f"客户说{rng.choice(CATEGORIES[category])}", day(), rng.choice([0, 0, 0, 20, 50]))
    rows.sort(key=lambda row: row["日期"])
    return rows


def crm_text(rows, rule) -> str:
    unit = RULES[rule]["unit"]
    head = ["工单号", "日期", "订单号", unit, "问题分类", "问题描述", "已发补偿（元）"]
    lines = ["# 本月 CRM 投诉记录（含上月未结的工单）", "", "| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    lines += ["| " + " | ".join(row[h] for h in head) + " |" for row in rows]
    return "\n".join(lines) + "\n"


def order_id(spec) -> str:
    return spec[0].upper() + "-ORDER"


def order_text(spec) -> str:
    name, group, segment, rule, now, customer, product, color, amount, promised, delivered, hours, prior, issue, demand, crm = spec
    r = RULES[rule]
    promised, delivered, signed, late = dates(spec)
    return "\n".join([
        "# 订单记录", "",
        f"- 订单号：{order_id(spec)}",
        f"- 客户：{customer}",
        f"- 商品：{r['products'][product[:2]]}",
        f"- {r['unit']}：{code(rule, product, color)}",
        f"- 订单金额：{money(amount)} 元",
        f"- 承诺送达日期：{promised}",
        f"- 实际送达日期：{delivered}",
        f"- 签收时间：{signed.strftime('%Y-%m-%d %H:%M')}",
        f"- 这个订单之前已发补偿：{money(prior)} 元",
        "",
    ])


def message(spec) -> str:
    name, group, segment, rule, now, customer, product, color, amount, promised, delivered, hours, prior, issue, demand, crm = spec
    r = RULES[rule]
    late = dates(spec)[3]
    words = CATEGORIES[issue][sum(map(ord, name)) % 3]
    item = r["products"][product[:2]]
    parts = [OPENINGS[rule], f"我买的{item}到了，发现{words}"]
    if late > 0:
        parts.append(f"，而且比说好的晚了 {late} 天才送到")
    parts.append("！")
    parts.append("我要退货，" if amount > 1000 else "我要换一个新的，")
    if demand:
        parts.append(f"你们还得赔我 {demand} 块钱。")
    return "".join(parts)


def question_text(spec) -> str:
    return (
        f"现在是 {spec[4]}。客户发来消息：\n\n「{message(spec)}」\n\n"
        "这家店的售后工作规则、客户的订单记录、本月 CRM 投诉记录和问题分类表在工作目录：工作规则.md、订单记录.md、"
        "CRM投诉记录.md、问题分类表.md。请按规则处理这起投诉。"
    )


def compute(spec, rows) -> dict:
    name, group, segment, rule, now, customer, product, color, amount, promised, delivered, hours, prior, issue, demand, crm = spec
    r = RULES[rule]
    k, dup, alt, blank, twice, old = crm
    now_dt = datetime.strptime(now, "%Y-%m-%d %H:%M")
    within = hours <= r["window_h"]
    late = dates(spec)[3]
    coupon = late >= r["late_days"] if r["late_inclusive"] else late > r["late_days"]
    amount, prior = Decimal(amount), Decimal(prior)
    quota = (amount * r["rate"]).quantize(CENT, rounding=ROUND_DOWN)
    if r["cap"] is not None:
        quota = min(quota, r["cap"])
    used = prior + (r["coupon"] if coupon and r["coupon_in_quota"] else Decimal(0))
    left = quota - used
    assert left >= 0, (name, quota, used)
    base = f"{r['prefix']}-{product}"
    month = now_dt.strftime("%Y-%m")
    seen = set()
    for row in rows:
        if not row["日期"].startswith(month) or not row[r["unit"]].startswith(base + "-"):
            continue
        category = row["问题分类"] or next(c for c, words in CATEGORIES.items() if any(w in row["问题描述"] for w in words))
        if category == issue:
            seen.add(row["订单号"])
    count = len(seen | {order_id(spec)})
    assert count == k + 1, (name, count, k)
    systemic = count >= r["systemic"]
    over = demand is not None and Decimal(demand) > left
    window = f"{r['window_h']} 小时" if r["window_h"] < 168 else f"{r['window_h'] // 24} 天"
    return {
        "规则集": f"{rule}（{r['brand']}）",
        "签收后过了多久": f"{hours} 小时（时限 {window}）",
        "在不在可换可退的时限内": "在" if within else "不在",
        "处理方式": ("、".join(r["options"]) + " 都要给客户") if within else f"{r['outside']}，不能答应换新或退款",
        "晚了几天": late,
        "迟到补券": f"补 {money(r['coupon'])} 元券（{'计入' if r['coupon_in_quota'] else '不计入'}额度）" if coupon else "不补券",
        "补偿额度": f"{money(quota)} 元" + ("（8% 超过 100 元封顶）" if r["cap"] and amount * r["rate"] > r["cap"] else ""),
        "这个订单之前已发补偿": f"{money(prior)} 元",
        "额度里已经用掉（之前已发 + 计入额度的迟到券）": f"{money(used)} 元",
        "还能直接给的补偿": f"{money(left)} 元",
        "客户要的补偿": f"{demand} 元" if demand else "没提具体金额",
        "客户要的补偿超没超出": ("超出，回复里不能先答应，要说明需要主管审批" if over else "没超出，可以直接答应")
        if demand else "不适用",
        "本月同款同问题第几起": count,
        "计数说明": f"本月同{r['unit']}（{base}，不看颜色后缀）同问题（{issue}）的订单 {k} 个"
        + ("，这个订单本月已有同问题工单，不再多算" if dup else "，加上这次投诉")
        + (f"；其中 {alt} 个是别的颜色" if alt else "") + (f"、{blank} 个分类为空按描述归类" if blank else "")
        + (f"、{twice} 个订单有重复工单只算一起" if twice else "") + (f"；上月的 {old} 张同问题工单不算" if old else ""),
        "要不要标记": f"要：CRM 标“{r['mark']}”并通知{r['notify']}" if systemic else f"不标（没到第 {r['systemic']} 起）",
        "分段": "、".join(f"## {s}" for s in r["sections"]),
    }


def scenario_package() -> None:
    (SCENARIO / "personas").mkdir(parents=True, exist_ok=True)
    (SCENARIO / "profile.md").write_text(TASK + "\n")
    (SCENARIO / "onboarding.md").write_text(ONBOARDING + "\n")
    (SCENARIO / "personas" / "customer.md").write_text("客户发来售后投诉；每道题的消息、订单、CRM 记录和规则由脚本给出。\n")
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
        rng = random.Random(name)
        rows = crm_rows(spec, rng)
        if segment == "common":
            assert spec[15][2:] == (0, 0, 0, 0) and not spec[15][1] and spec[12] == 0, name
        files = {"工作规则.md": rules_text(rule), "订单记录.md": order_text(spec), "CRM投诉记录.md": crm_text(rows, rule),
                 "问题分类表.md": category_text()}
        reference = compute(spec, rows)
        bank.append({"name": name, "group": group, "segment": segment, "rules": rule, "text": question_text(spec),
                     "files": files, "reference": reference})
        label = {"train": "培养", "same": "考试·同规则", "new": "考试·新规则"}[group]
        scripts.append({"name": name, "title": f"{name} · {label} · {RULES[rule]['brand']}", "exam": group != "train",
                        "steps": [{"text": question_text(spec), "files": files}]})
    (HERE / "questions.json").write_text(json.dumps(bank, ensure_ascii=False, indent=1) + "\n")
    (HERE / "scripts.json").write_text(json.dumps(scripts, ensure_ascii=False, indent=1) + "\n")
    scenario_package()
    systemic = sum(q["reference"]["要不要标记"].startswith("要") for q in bank)
    outside = sum(q["reference"]["在不在可换可退的时限内"] == "不在" for q in bank)
    over = sum(q["reference"]["客户要的补偿超没超出"].startswith("超出") for q in bank)
    print(f"{len(bank)} questions: systemic {systemic}, outside window {outside}, demand over quota {over}")


if __name__ == "__main__":
    main()
