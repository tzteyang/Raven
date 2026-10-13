"""竞品对比表：三套工作规则、40 道题（20 培养 + 10 道同规则考试 + 10 道换规则考试）、参考答案和 Studio 场景包。

  python3 make.py

依据《专家自进化》11.1 的案例改写成「工作规则随题交给员工」：三家公司各有一套竞品对比口径（价格折算口径、功能格用词、
定位语的叫法和写法、表格版式都不同）。培养题和同规则考试题用 R1（云笺 · 协同文档）、R2（简舟 · 项目管理）交替，换规则
考试题全用员工从没见过的 R3（汇客 · CRM）。R1、R2 的 30 道题的竞品结构沿用 bench/bench.py 的 30 道题（R2 换成项目管理的
功能名和竞品名，个别价格为避开并列改过），R3 的 10 道题另写。每道题生成时校验：唯一领先项恰好一个、折算后最便宜的
不并列、四舍五入不落在正中间、名字不重复。check.py 另写一遍算法，只读员工看到的文件独立复核。
"""

import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENARIO = HERE / "wkr-compete-table"
VALUES = {"有", "无", "部分", "—"}
CODE = {"美元": "USD", "欧元": "EUR", "港元": "HKD", "日元": "JPY"}


def seat(price, disc=None, cur="人民币"):
    return {"kind": "seat", "price": str(price), "disc": disc, "cur": cur}


def monthly(price, cur="人民币"):
    return {"kind": "monthly", "price": str(price), "cur": cur}


def annual(price, cur="人民币"):
    return {"kind": "annual", "price": str(price), "cur": cur}


def team(tiers, disc=None, cur="人民币"):
    return {"kind": "team", "tiers": tiers, "disc": disc, "cur": cur}


def tiered(tiers, disc=None, cur="人民币"):
    return {"kind": "tiered", "tiers": tiers, "disc": disc, "cur": cur}


def freemium(*versions):
    """Versions in order; the one given as a pricing dict is the 对标版本, the others are text only."""
    return {"kind": "freemium", "versions": list(versions), "cur": "人民币"}


RULES = {
    "R1": {
        "company": "云笺", "category": "协同文档 SaaS", "price": seat(30, "8"),
        "cells": {"实时协作": "有", "离线编辑": "有", "版本历史": "有", "表格公式": "部分", "审批流": "有", "开放 API": "有",
                  "国产化适配": "有", "权限与审计": "有", "白板": "无", "AI 写作": "部分", "电子签章": "有"},
        "fx": {"人民币": Decimal("1"), "美元": Decimal("7.10"), "欧元": Decimal("7.80"), "港元": Decimal("0.91"),
               "日元": Decimal("0.048")},
        "discount": True, "year": False, "places": 1, "unit": "元/人/月",
        "words": {"有": "有", "无": "无", "部分": "部分", "—": "未知"},
        "call": "定位语", "prefix": "定位语：", "where": "表格上方", "banned": ("最", "第一"), "mention": "may",
        "rows": "feature",
        "text": """# 云笺 · 竞品对比工作规则

我方产品：云笺（协同文档 SaaS）。

1. 价格统一折算成“年付、每人每月”的人民币价，按本次给的团队人数算，四舍五入保留一位小数（整数也写成 24.0 这样），单位“元/人/月”。
2. 功能格只写“有”“无”“部分”“未知”，和资料表逐格一致；资料表里写“—”的格写“未知”。
3. 定位语只能用我方唯一领先的那一项（我方是“有”、其他各家都是“无”或“部分”的那一项）；不写“最”“第一”；折算后我方不是最便宜的，就不提价格。
4. 只陈列事实，不评价竞品好坏。
5. 回复里只放定位语和一张对比表，不加别的文字：定位语在表格上方单独一行，以“定位语：”开头；表格的行是功能、列是产品（我方放第一列），最后一行放各家折算价；竞品不超过 5 列，功能不超过 8 行，不加规则没要求的行和列。

补充口径：

- 按团队计费的，先按团队人数落到对应档位，再除以人数。
- 阶梯价按整队人数所在档位的单价算。
- 外币按汇率表换算成人民币。
- 只有月付的按月付价算；只有年付的，年付价除以 12。
- 有免费版和付费版的，取资料表标了“对标版本”的那一档。
""",
    },
    "R2": {
        "company": "简舟", "category": "项目管理 SaaS", "price": seat(26, "8"),
        "cells": {"看板": "有", "甘特图": "有", "工时统计": "有", "自动化规则": "部分", "审批流": "有", "开放 API": "有",
                  "私有部署": "有", "权限与审计": "有", "白板": "无", "AI 助手": "部分", "资源排期": "有"},
        "fx": {"人民币": Decimal("1"), "美元": Decimal("7.20"), "欧元": Decimal("7.90"), "港元": Decimal("0.92"),
               "日元": Decimal("0.050")},
        "discount": False, "year": False, "places": 0, "unit": "元/人/月",
        "words": {"有": "支持", "无": "不支持", "部分": "部分支持", "—": "未公开"},
        "call": "一句话卖点", "prefix": "一句话卖点：", "where": "表格下方", "banned": ("最", "第一", "唯一", "领先"),
        "mention": "never", "rows": "product",
        "text": """# 简舟 · 竞品对比工作规则

我方产品：简舟（项目管理 SaaS）。

1. 价格统一折算成“月付、每人每月”的人民币价：按月付标价算，不算年付折扣；按本次给的团队人数算，四舍五入到整数，不写小数，单位“元/人/月”。
2. 功能格只写“支持”“不支持”“部分支持”“未公开”：资料表里的“有”“无”“部分”“—”依次对应，逐格一致。
3. 一句话卖点只写我方唯一领先的那一项（我方是“有”、其他各家都是“无”或“部分”的那一项）；不写“最”“第一”“唯一”“领先”；不提价格。
4. 只陈列事实，不评价竞品好坏。
5. 回复里只放一张对比表和一句话卖点，不加别的文字：表格的行是产品（我方放第一行）、列是功能，最后一列放各家折算价；一句话卖点在表格下方单独一行，以“一句话卖点：”开头；竞品不超过 5 行，功能不超过 8 列，不加规则没要求的行和列。

补充口径：

- 按团队计费的，先按团队人数落到对应档位，再除以人数。
- 阶梯价按整队人数所在档位的单价算。
- 外币按汇率表换算成人民币。
- 只有年付的，年付价除以 12。
- 有免费版和付费版的，取资料表标了“对标版本”的那一档。
""",
    },
    "R3": {
        "company": "汇客", "category": "CRM SaaS", "price": seat(45, "8.5"),
        "cells": {"线索管理": "有", "商机管道": "有", "报价单": "有", "合同管理": "有", "回款跟踪": "有", "销售预测": "部分",
                  "外呼集成": "无", "企业微信集成": "有", "开放 API": "有", "私有部署": "有", "移动端": "有"},
        "fx": {"人民币": Decimal("1"), "美元": Decimal("7.15"), "欧元": Decimal("7.70"), "港元": Decimal("0.915"),
               "日元": Decimal("0.049")},
        "discount": True, "year": True, "places": 0, "unit": "元/人/年",
        "words": {"有": "具备", "无": "不具备", "部分": "部分具备", "—": "待核实"},
        "call": "定位", "prefix": "定位：", "where": "表格上方", "banned": ("最", "第一", "首家", "独家"), "mention": "must",
        "rows": "feature",
        "text": """# 汇客 · 竞品对比工作规则

我方产品：汇客（CRM SaaS）。

1. 价格统一折算成“年付、每人每年”的人民币价：有年付折扣的按折后价，按本次给的团队人数算，四舍五入到整数，不写小数，单位“元/人/年”。
2. 功能格只写“具备”“不具备”“部分具备”“待核实”：资料表里的“有”“无”“部分”“—”依次对应，逐格一致。
3. 定位只用我方唯一领先的那一项（我方是“有”、其他各家都是“无”或“部分”的那一项）；不写“最”“第一”“首家”“独家”。折算后我方最便宜的，定位里要写出我方的折算价；不是最便宜的，不提价格。
4. 只陈列事实，不评价竞品好坏。
5. 回复里只放定位和一张对比表，不加别的文字：定位在表格上方单独一行，以“定位：”开头；表格的行是功能、列是产品（我方放第一列），最后一行放各家折算价；竞品不超过 5 列，功能不超过 8 行，不加规则没要求的行和列。

补充口径：

- 按团队计费的，先按团队人数落到对应档位，再除以人数。
- 阶梯价按整队人数所在档位的单价算。
- 外币按汇率表换算成人民币。
- 只有月付的，月付价乘 12；只有年付的，直接用年付价。
- 有免费版和付费版的，取资料表标了“对标版本”的那一档。
""",
    },
}

# name, group(train/same/new), segment(common/edge), rules, team size, features, [(competitor, pricing, cells in feature order)]
SPECS = [
    # ---------------- 培养 1–10：常见（都按人计费、人民币，年付折扣只有一种）；奇数 R1、偶数 R2 ----------------
    ("t01", "train", "common", "R1", 10, ["实时协作", "离线编辑", "版本历史", "表格公式", "审批流", "开放 API"], [
        ("书契", seat(32, "8"), "有 无 有 有 无 有"),
        ("笔录", seat(28), "有 无 有 部分 无 —"),
        ("云简", seat(40, "7.5"), "有 部分 部分 有 有 有"),
    ]),
    ("t02", "train", "common", "R2", 30, ["看板", "甘特图", "工时统计", "自动化规则", "开放 API", "权限与审计", "AI 助手"], [
        ("行舟", seat(36, "7.5"), "有 有 有 有 部分 无 有"),
        ("象限", seat(30), "有 无 有 部分 有 部分 无"),
        ("栈桥", seat(42, "7"), "有 部分 部分 有 有 无 —"),
        ("节拍", seat(28, "9"), "有 — 有 有 无 部分 有"),
        ("里程", seat(50, "8"), "有 无 有 有 有 无 部分"),
    ]),
    ("t03", "train", "common", "R1", 6, ["实时协作", "离线编辑", "版本历史", "审批流", "开放 API", "权限与审计", "白板"], [
        ("墨河", seat(25, "8"), "有 有 有 无 部分 — 有"),
        ("青札", seat(36, "8.5"), "有 无 有 部分 有 有 无"),
        ("云岫", seat(30), "有 部分 — 无 有 有 有"),
        ("清页", seat(45, "7"), "有 无 有 无 无 部分 —"),
    ]),
    ("t04", "train", "common", "R2", 12, ["看板", "甘特图", "审批流", "开放 API", "私有部署", "权限与审计"], [
        ("方舟", seat(23, "9"), "有 有 无 无 有 有"),
        ("衡器", seat(31, "8"), "有 无 有 部分 — 有"),
        ("驿站", seat(26), "有 部分 有 无 有 部分"),
        ("航标", seat(39, "8"), "有 无 部分 部分 无 有"),
    ]),
    ("t05", "train", "common", "R1", 20, ["实时协作", "版本历史", "表格公式", "开放 API", "国产化适配", "AI 写作"], [
        ("衡文", seat(35, "8"), "有 有 有 有 无 有"),
        ("知序", seat(27), "有 部分 部分 — 部分 有"),
        ("拾页", seat(30, "9"), "有 有 有 部分 无 —"),
    ]),
    ("t06", "train", "common", "R2", 5, ["看板", "甘特图", "工时统计", "自动化规则", "审批流", "开放 API", "白板"], [
        ("罗盘", seat(29, "9"), "有 有 有 有 无 有 —"),
        ("拾阶", seat(35), "有 无 部分 有 部分 无 有"),
        ("筑基", seat(32, "8.5"), "有 部分 有 — 无 有 有"),
    ]),
    ("t07", "train", "common", "R1", 15,
     ["实时协作", "离线编辑", "版本历史", "表格公式", "审批流", "开放 API", "权限与审计", "白板"], [
        ("合墨", seat(26, "8.5"), "有 有 部分 有 无 — 有 有"),
        ("简牍", seat(38, "7.5"), "有 无 无 有 有 有 有 无"),
        ("澄文", seat(29), "有 部分 部分 部分 无 有 — 有"),
        ("览卷", seat(33, "8"), "有 无 无 有 部分 有 部分 —"),
    ]),
    ("t08", "train", "common", "R2", 25, ["看板", "甘特图", "工时统计", "自动化规则", "审批流", "开放 API", "私有部署", "AI 助手"], [
        ("积木", seat(27, "8"), "有 有 有 部分 有 有 无 有"),
        ("齿轮", seat(33, "9"), "有 部分 有 有 部分 有 部分 —"),
        ("轨道", seat(30, "7.5"), "有 无 部分 有 有 无 无 有"),
        ("坐标", seat(36), "有 无 有 有 无 部分 部分 无"),
        ("刻度", seat(25), "有 — 有 部分 有 有 无 部分"),
    ]),
    ("t09", "train", "common", "R1", 8, ["实时协作", "离线编辑", "版本历史", "审批流", "国产化适配", "白板"], [
        ("叠页", seat(22), "有 无 有 无 有 有"),
        ("方格", seat(34, "8"), "有 部分 有 有 无 无"),
        ("同书", seat(48, "6"), "有 无 — 有 有 部分"),
    ]),
    ("t10", "train", "common", "R2", 18, ["看板", "甘特图", "工时统计", "审批流", "权限与审计", "白板"], [
        ("经纬", seat(30, "8.5"), "有 无 有 有 部分 有"),
        ("棋盘", seat(28), "有 部分 部分 无 有 无"),
        ("沙漏", seat(34, "8"), "有 无 有 部分 有 —"),
        ("灯塔", seat(40, "6.5"), "有 无 — 有 部分 有"),
    ]),
    # ---------------- 培养 11–20：边界（团队计费、阶梯价、外币、只有年付或只有月付、免费版加付费版） ----------------
    ("t11", "train", "edge", "R1", 9, ["实时协作", "离线编辑", "版本历史", "审批流", "开放 API", "国产化适配"], [
        ("典章", team([(1, 10, 199), (11, 20, 520)]), "有 部分 有 无 有 有"),
        ("澜书", annual(348), "有 无 有 部分 — 有"),
        ("青柚", seat(35, "8"), "有 有 部分 无 有 无"),
        ("墨岩", monthly(26), "有 无 — 无 部分 部分"),
    ]),
    ("t12", "train", "edge", "R2", 16,
     ["看板", "甘特图", "工时统计", "自动化规则", "审批流", "开放 API", "私有部署", "权限与审计"], [
        ("节点", tiered([(1, 15, 32), (16, 60, 27)], "9"), "有 有 有 有 无 有 有 有"),
        ("脉络", freemium(("免费版", "0 元，最多 2 人"), ("标准版", "20 元/人/月"), ("专业版", seat(45, "8"))),
         "有 无 有 有 部分 有 无 有"),
        ("链路", annual(264), "有 部分 — 部分 无 无 有 部分"),
        ("回廊", seat(30, "8.5"), "有 无 有 有 部分 — 部分 有"),
    ]),
    ("t13", "train", "edge", "R1", 11, ["实时协作", "离线编辑", "版本历史", "表格公式", "审批流", "国产化适配", "权限与审计"], [
        ("衡章", team([(1, 10, 199), (11, 20, 520)]), "有 无 有 有 有 部分 有"),
        ("Quillset", seat(5, cur="美元"), "有 有 有 有 部分 无 部分"),
        ("栖云", freemium(("免费版", "0 元，最多 3 人"), ("专业版", seat(40, "7.5")), ("企业版", "65 元/人/月，年付打 8 折")),
         "有 部分 部分 — 无 无 有"),
    ]),
    ("t14", "train", "edge", "R2", 6, ["看板", "甘特图", "工时统计", "审批流", "私有部署", "白板"], [
        ("Taskline", team([(1, 10, 35), (11, 25, 79)], cur="美元"), "有 有 有 有 无 有"),
        ("Sprintly", annual(48, cur="欧元"), "有 无 有 部分 无 —"),
        ("驼峰", monthly(31), "有 部分 部分 无 部分 无"),
    ]),
    ("t15", "train", "edge", "R1", 25, ["实时协作", "离线编辑", "版本历史", "审批流", "开放 API", "权限与审计"], [
        ("青简", tiered([(1, 20, 36), (21, 100, 28)], "8"), "有 有 有 有 有 部分"),
        ("Pagewell", seat(4, "9", cur="欧元"), "有 部分 有 无 有 无"),
        ("Scrivio", annual(60, cur="美元"), "有 无 — 部分 有 无"),
        ("云崖", seat(32, "8.5"), "有 无 有 部分 — 部分"),
    ]),
    ("t16", "train", "edge", "R2", 50, ["看板", "甘特图", "工时统计", "自动化规则", "开放 API", "权限与审计", "AI 助手"], [
        ("前哨", team([(1, 20, 399), (21, 50, 999), (51, 200, 2499)], "9"), "有 有 部分 有 有 有 有"),
        ("长缨", tiered([(1, 30, 30), (31, 200, 26)]), "有 无 无 有 有 部分 —"),
        ("跃迁", freemium(("免费版", "0 元"), ("专业版", seat(35, "8")), ("旗舰版", "60 元/人/月")), "有 部分 部分 部分 无 有 有"),
        ("弧光", seat(33, "9"), "有 无 无 — 有 部分 无"),
        ("晨钟", annual(300), "有 无 部分 有 部分 无 部分"),
    ]),
    ("t17", "train", "edge", "R1", 40, ["实时协作", "离线编辑", "版本历史", "表格公式", "审批流", "开放 API", "白板"], [
        ("汇章", team([(1, 15, 299), (16, 50, 899), (51, None, 1599)], "8"), "有 无 有 有 有 有 无"),
        ("叶声", monthly(29), "有 部分 有 部分 无 有 有"),
        ("简帛", freemium(("免费版", "0 元，最多 5 人"), ("团队版", annual(336)), ("企业版", "50 元/人/月")),
         "有 无 部分 有 有 — 有"),
        ("拾卷", seat(38, "7"), "有 无 有 — 部分 有 无"),
    ]),
    ("t18", "train", "edge", "R2", 3, ["看板", "甘特图", "工时统计", "审批流", "开放 API", "白板"], [
        ("暮鼓", team([(1, 5, 99), (6, 20, 299)]), "有 无 有 有 有 无"),
        ("帆影", freemium(("免费版", "0 元，最多 5 人"), ("专业版", seat(28))), "有 部分 有 部分 有 有"),
        ("Planwise", seat(5, "8", cur="美元"), "有 无 有 有 — 有"),
        ("桥头", monthly(27), "有 无 — 无 部分 部分"),
    ]),
    ("t19", "train", "edge", "R1", 10, ["实时协作", "版本历史", "表格公式", "审批流", "开放 API", "国产化适配"], [
        ("合章", team([(1, 10, 268), (11, 30, 688)]), "有 有 有 有 无 有"),
        ("Notara", seat(40, "8", cur="港元"), "有 有 部分 无 部分 无"),
        ("Leafdesk", seat(600, cur="日元"), "有 部分 有 有 无 —"),
    ]),
    ("t20", "train", "edge", "R2", 21,
     ["看板", "甘特图", "工时统计", "自动化规则", "审批流", "开放 API", "私有部署", "权限与审计"], [
        ("码头", team([(1, 20, 459), (21, 60, 1099)], "8.5"), "有 有 有 有 有 有 有 部分"),
        ("Boardly", annual(360, cur="港元"), "有 部分 有 有 无 有 无 无"),
        ("远航", freemium(("免费版", "0 元"), ("专业版", annual(276)), ("企业版", "48 元/人/月")), "有 无 有 部分 有 — 有 部分"),
        ("青云", seat(27, "9"), "有 无 — 有 部分 有 部分 无"),
    ]),
    # ---------------- 同规则考试：x01–x05 常见、x06–x10 边界；奇数 R1、偶数 R2 ----------------
    ("x01", "same", "common", "R1", 14, ["实时协作", "离线编辑", "版本历史", "表格公式", "审批流", "开放 API", "权限与审计"], [
        ("砚池", seat(31, "8"), "有 有 有 有 部分 无 有"),
        ("编鹿", seat(27), "有 无 有 部分 有 部分 —"),
        ("落笔", seat(36, "7.5"), "有 部分 — 有 无 无 部分"),
        ("简页", seat(42, "7"), "有 无 有 有 有 部分 有"),
    ]),
    ("x02", "same", "common", "R2", 9, ["看板", "甘特图", "工时统计", "开放 API", "权限与审计", "白板"], [
        ("锚点", seat(25, "9"), "有 有 有 有 无 有"),
        ("枢纽", seat(37, "8"), "有 无 有 部分 部分 无"),
        ("蓝图", seat(28), "有 部分 — 有 无 有"),
        ("磐石", seat(34, "8.5"), "有 无 有 有 部分 —"),
    ]),
    ("x03", "same", "common", "R1", 7, ["实时协作", "离线编辑", "版本历史", "审批流", "国产化适配", "AI 写作"], [
        ("文渊", seat(24, "8.5"), "有 有 无 有 有 有"),
        ("墨痕", seat(33, "8"), "有 无 部分 部分 有 —"),
        ("纸间", seat(29), "有 部分 无 有 无 有"),
    ]),
    ("x04", "same", "common", "R2", 12, ["看板", "甘特图", "工时统计", "审批流", "开放 API", "私有部署", "资源排期"], [
        ("启明", seat(30, "8.5"), "有 有 有 有 部分 有 无"),
        ("星图", seat(22), "有 无 有 部分 有 — 部分"),
        ("拓扑", seat(36, "8"), "有 部分 — 有 有 有 无"),
        ("矩阵", seat(40, "7"), "有 无 有 有 无 部分 部分"),
    ]),
    ("x05", "same", "common", "R1", 22,
     ["实时协作", "离线编辑", "版本历史", "表格公式", "审批流", "开放 API", "国产化适配", "白板"], [
        ("拾叶", seat(38, "7.5"), "有 有 有 有 无 有 有 有"),
        ("衡书", seat(30, "9"), "有 无 有 部分 部分 有 无 无"),
        ("页林", seat(26), "有 部分 部分 有 无 — 有 有"),
        ("清墨", seat(35, "8"), "有 无 有 有 部分 有 部分 —"),
        ("典藏", seat(44, "6"), "有 无 — 有 无 部分 无 有"),
    ]),
    ("x06", "same", "edge", "R2", 4, ["看板", "甘特图", "工时统计", "审批流", "开放 API", "白板"], [
        ("跬步", team([(1, 5, 128), (6, 15, 368)]), "有 有 有 有 无 有"),
        ("峰值", freemium(("免费版", "0 元，最多 5 人"), ("专业版", seat(34, "8.5"))), "有 部分 有 部分 部分 有"),
        ("Kanbo", seat(700, "8", cur="日元"), "有 无 — 有 无 无"),
        ("云帆", annual(300), "有 无 有 无 部分 —"),
    ]),
    ("x07", "same", "edge", "R1", 12, ["实时协作", "离线编辑", "版本历史", "表格公式", "审批流", "权限与审计"], [
        ("汇岸", team([(1, 10, 229), (11, 30, 599)], "8.5"), "有 无 有 有 有 有"),
        ("Penmark", seat("3.5", cur="欧元"), "有 部分 有 有 部分 —"),
        ("云台", freemium(("免费版", "0 元，最多 10 人"), ("专业版", seat(38, "7.5")), ("企业版", "58 元/人/月")),
         "有 无 部分 — 有 部分"),
    ]),
    ("x08", "same", "edge", "R2", 60,
     ["看板", "甘特图", "工时统计", "自动化规则", "审批流", "开放 API", "私有部署", "权限与审计"], [
        ("高塔", team([(1, 20, 499), (21, 50, 1199), (51, 200, 1999)], "8"), "有 有 有 有 无 有 有 有"),
        ("长桥", tiered([(1, 50, 31), (51, 500, 25)], "9"), "有 无 有 有 部分 有 无 部分"),
        ("远山", freemium(("免费版", "0 元"), ("团队版", annual(348)), ("企业版", "52 元/人/月")), "有 部分 部分 — 无 有 有 有"),
        ("Trackforge", seat(36, "8", cur="港元"), "有 无 有 有 无 — 无 部分"),
        ("平川", seat(32, "8.5"), "有 无 — 部分 部分 部分 部分 无"),
    ]),
    ("x09", "same", "edge", "R1", 35, ["实时协作", "离线编辑", "版本历史", "审批流", "开放 API", "国产化适配", "AI 写作"], [
        ("书舫", tiered([(1, 30, 34), (31, 100, 29)], "8"), "有 有 部分 有 有 有 有"),
        ("Docuvia", annual(45, cur="美元"), "有 有 无 部分 有 无 有"),
        ("墨涧", monthly(25), "有 部分 无 无 — 有 部分"),
        ("汇泉", team([(1, 50, 1180), (51, None, 1980)]), "有 无 部分 有 部分 — 无"),
    ]),
    ("x10", "same", "edge", "R2", 10, ["看板", "甘特图", "工时统计", "自动化规则", "开放 API", "私有部署", "权限与审计"], [
        ("Milepost", team([(1, 10, 32), (11, 25, 79)], "9", cur="美元"), "有 有 有 有 有 无 有"),
        ("Ganttery", annual(42, cur="欧元"), "有 部分 有 — 有 无 部分"),
        ("石阶", monthly(28), "有 无 — 部分 部分 部分 有"),
        ("天梯", freemium(("免费版", "0 元，最多 3 人"), ("专业版", seat(36, "8"))), "有 无 有 有 无 无 —"),
    ]),
    # ---------------- 新规则考试（R3，员工从没见过）：y01–y05 常见、y06–y10 边界 ----------------
    ("y01", "new", "common", "R3", 12, ["线索管理", "商机管道", "报价单", "回款跟踪", "外呼集成", "私有部署"], [
        ("客源", seat(40, "8"), "有 有 部分 无 有 无"),
        ("商脉", seat(48), "有 部分 有 部分 无 —"),
        ("拓客", seat(55, "7"), "有 有 有 无 部分 有"),
    ]),
    ("y02", "new", "common", "R3", 8, ["线索管理", "商机管道", "合同管理", "销售预测", "企业微信集成", "开放 API", "移动端"], [
        ("销途", seat(50, "9"), "有 有 部分 有 无 有 有"),
        ("成单", seat(42), "有 部分 有 部分 部分 — 有"),
        ("聚客", seat(60, "8"), "有 有 无 无 部分 有 部分"),
        ("链客", seat(39), "有 无 有 有 无 部分 有"),
    ]),
    ("y03", "new", "common", "R3", 20,
     ["线索管理", "商机管道", "报价单", "合同管理", "回款跟踪", "外呼集成", "开放 API", "私有部署"], [
        ("盈客", seat(36, "8"), "有 有 无 有 部分 有 有 无"),
        ("客满", seat(33), "有 部分 有 部分 无 有 — 部分"),
        ("汇单", seat(45, "7.5"), "有 有 部分 无 无 无 有 有"),
        ("销库", seat(52, "8"), "有 无 有 有 部分 部分 部分 —"),
        ("金穗", seat(30), "有 有 部分 部分 无 无 有 无"),
    ]),
    ("y04", "new", "common", "R3", 6, ["线索管理", "商机管道", "报价单", "销售预测", "企业微信集成", "移动端"], [
        ("恒信", seat(48, "8.5"), "有 有 无 有 有 部分"),
        ("远客", seat(40), "有 部分 部分 部分 有 —"),
        ("迎客", seat(58, "7"), "有 无 部分 有 部分 有"),
    ]),
    ("y05", "new", "common", "R3", 15, ["线索管理", "商机管道", "合同管理", "回款跟踪", "外呼集成", "企业微信集成", "私有部署"], [
        ("客流", seat(35, "9"), "有 有 部分 有 有 无 部分"),
        ("营帆", seat(44, "8"), "有 部分 有 部分 无 部分 有"),
        ("卓客", seat(38), "有 有 有 — 部分 部分 无"),
        ("合拓", seat(50, "7.5"), "有 无 部分 部分 有 部分 部分"),
    ]),
    ("y06", "new", "edge", "R3", 9, ["线索管理", "商机管道", "报价单", "回款跟踪", "开放 API", "私有部署"], [
        ("联商", team([(1, 10, 399), (11, 30, 999)], "9"), "有 有 无 部分 有 无"),
        ("Leadbase", seat(6, cur="美元"), "有 部分 有 无 部分 有"),
        ("鼎客", monthly(36), "有 有 部分 部分 — 部分"),
        ("拾单", annual(468), "有 无 无 无 有 部分"),
    ]),
    ("y07", "new", "edge", "R3", 25, ["线索管理", "商机管道", "报价单", "合同管理", "销售预测", "企业微信集成", "开放 API"], [
        ("顺销", tiered([(1, 20, 52), (21, 100, 48)], "8"), "有 有 有 无 有 部分 有"),
        ("Dealflow", annual(60, cur="欧元"), "有 部分 部分 有 部分 无 有"),
        ("客台", freemium(("免费版", "0 元，最多 3 人"), ("专业版", seat(50, "8")), ("企业版", "80 元/人/月")),
         "有 有 部分 部分 无 部分 —"),
        ("信达", monthly(41), "有 无 有 有 部分 无 部分"),
    ]),
    ("y08", "new", "edge", "R3", 4, ["线索管理", "商机管道", "合同管理", "回款跟踪", "外呼集成", "移动端"], [
        ("客圈", team([(1, 5, 158), (6, 20, 498)]), "有 有 部分 无 有 部分"),
        ("Closely", seat(48, "8", cur="港元"), "有 无 有 部分 部分 有"),
        ("商栈", annual(420), "有 部分 无 部分 无 —"),
    ]),
    ("y09", "new", "edge", "R3", 50,
     ["线索管理", "商机管道", "报价单", "合同管理", "回款跟踪", "销售预测", "企业微信集成", "私有部署"], [
        ("销云", team([(1, 20, 980), (21, 60, 2400), (61, None, 3500)], "8.5"), "有 有 有 无 部分 有 部分 有"),
        ("Prospera", annual(66, cur="美元"), "有 部分 有 有 部分 部分 无 无"),
        ("客道", tiered([(1, 30, 45), (31, 200, 43)], "9"), "有 有 部分 有 无 部分 部分 —"),
        ("商桥", freemium(("免费版", "0 元"), ("团队版", annual(498)), ("企业版", "65 元/人/月")), "有 无 无 部分 部分 有 有 有"),
        ("Quotient", seat(1000, "8", cur="日元"), "有 有 有 部分 无 无 部分 部分"),
    ]),
    ("y10", "new", "edge", "R3", 10, ["线索管理", "商机管道", "报价单", "合同管理", "外呼集成", "开放 API", "移动端"], [
        ("Pipewise", team([(1, 10, 45), (11, 25, 99)], "9", cur="美元"), "有 有 部分 有 部分 无 有"),
        ("汇融", annual(52, cur="欧元"), "有 部分 有 部分 无 部分 —"),
        ("暖客", monthly(30), "有 无 无 无 有 部分 部分"),
        ("启客", freemium(("免费版", "0 元，最多 3 人"), ("专业版", seat(38, "8"))), "有 有 部分 部分 无 部分 有"),
    ]),
]

OPENINGS = [
    "我是销售部的林悦，下周要去见一个 {n} 人团队的客户，帮我出一份竞品对比。",
    "官网的竞品对比页要更新了，页面上按 {n} 人的团队来比。",
    "投标文件里要附一份竞品对比，这个项目的客户团队是 {n} 人。",
    "渠道商要一份对比材料，拿去给一个 {n} 人的团队讲。",
    "下周沙龙要放一页竞品对比，现场按 {n} 人的团队来讲。",
    "客户成功那边要一份对比，客户团队 {n} 人，续约前在比价。",
]
TASK = (
    "你是 SaaS 公司产品市场部的竞品分析助手。销售、官网、标书和渠道的同事会发来竞品对比的需求，工作目录里有这次适用的"
    "工作规则、竞品资料和汇率表。按这次给的工作规则出一张竞品对比表，配一句话的定位（叫法和写法以工作规则为准），"
    "同事会直接拿去用；只输出工作规则要求的内容本身，不要附加任何说明。"
)
ONBOARDING = "以后每次要做竞品对比，我都会把这次适用的工作规则、竞品资料和汇率表一起发给你。不同公司的口径不一样，以当次给的为准。"
CRITERIA = [
    ("C-price", "red_line",
     "价格：表里每家产品的折算价按这次工作规则的口径算对，并按规则的小数位数写（参考答案给出了每家该写的值）。"
     "每家价格算错、小数位数不对（例如规则要一位小数却写成 24，规则要整数却写成 26.0）或漏了哪家的价格，每家记一处；"
     "单位写在格里或写在价格这一行（列）的表头里都行，两处都没有单位记一处。"),
    ("C-cells", "standard",
     "功能格：表里每个功能格用这次工作规则规定的词，和资料表逐格一致（参考答案列出了每格该写什么）。每个写错的格记一处，"
     "用错了词（例如规则要“未公开”却写“未知”）也算。表里缺了或多了的功能、产品不在这里记，记在表格版式里。"),
    ("C-position", "standard",
     "定位语（规则里可能叫一句话卖点、定位）：按这次工作规则，放在规定的位置、单独一行、以规定的开头写法开头"
     "（Markdown 加粗之类的格式符号不算违反）；只用参考答案里的那一项唯一领先项；不出现规则禁用的词；"
     "价格该不该提、提了数值对不对，以参考答案为准。每处不符记一处；没有定位语记一处。"),
    ("C-facts", "standard",
     "只陈列事实：回复里不评价竞品好坏（例如“更好用”“落后”“性价比低”），不写资料里没有的说法（例如资料没写的功能、"
     "价格、客户案例）。每处记一处。"),
    ("C-layout", "standard",
     "表格版式：按这次工作规则的行列方向、我方的位置、价格放在哪一行（列）；表里的产品和功能要和资料一致、不多不少"
     "（顺序不限）；回复里只放规则要求的内容，不加别的行、列和文字（例如标题、注释、口径说明）。每处不符记一处。"),
]


# ---------------- 价格折算（评价侧的标准算法） ----------------

def _unit(cur):
    return "元" if cur == "人民币" else cur


def _tier(tiers, n):
    hit = [t for t in tiers if t[0] <= n and (t[1] is None or n <= t[1])]
    assert len(hit) == 1, (tiers, n)
    return hit[0]


def _tier_text(t, unit, per):
    span = f"{t[0]}–{t[1]} 人" if t[1] is not None else f"{t[0]} 人及以上"
    return f"{span} {t[2]} {unit}{per}"


def _bench_version(p):
    found = [(name, v) for name, v in p["versions"] if isinstance(v, dict)]
    assert len(found) == 1
    return found[0]


def rate(p, n, r):
    """(未取舍的人民币价, 推导步骤)，按规则集 r 的口径：年付或月付、每人每月或每人每年。"""
    k, cur = p["kind"], p.get("cur", "人民币")
    if k == "freemium":
        name, v = _bench_version(p)
        value, steps = rate({**v, "cur": cur}, n, r)
        return value, [f"取对标的{name}"] + steps
    unit, steps = _unit(cur), []
    disc = Decimal(p["disc"]) / 10 if r["discount"] and p.get("disc") else Decimal(1)
    months = 12 if r["year"] else 1
    if k == "seat":
        value = Decimal(p["price"]) * disc * months
        steps.append(f"{p['price']} {unit}/人/月")
    elif k == "monthly":
        value = Decimal(p["price"]) * months
        steps.append(f"只有月付 {p['price']} {unit}/人/月")
    elif k == "annual":
        value = Decimal(p["price"]) if r["year"] else Decimal(p["price"]) / 12
        steps.append(f"只有年付 {p['price']} {unit}/人/年" + ("" if r["year"] else " ÷ 12"))
    elif k == "team":
        t = _tier(p["tiers"], n)
        value = Decimal(t[2]) * disc * months / n
        steps.append(f"{n} 人落在 {_tier_text(t, unit, '/月')} 这一档，÷ {n} 人")
    elif k == "tiered":
        t = _tier(p["tiers"], n)
        value = Decimal(t[2]) * disc * months
        steps.append(f"{n} 人落在 {_tier_text(t, unit, '/人/月')} 这一档")
    else:
        raise ValueError(k)
    if k in ("seat", "team", "tiered"):
        if not r["discount"]:
            steps.append("按月付标价，不算年付折扣")
        else:
            steps.append(f"× {p['disc']} 折" if p.get("disc") else "年付不打折")
    if r["year"] and k != "annual":
        steps.append("× 12 个月")
    if cur != "人民币":
        steps.append(f"× 汇率 {r['fx'][cur]}")
    return value * r["fx"][cur], steps


def rounded(value, places):
    beyond = value * Decimal(10) ** (places + 1)
    assert not (beyond == beyond.to_integral_value() and int(beyond) % 10 == 5), f"落在正中间：{value}"
    return str(value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP))


# ---------------- 员工看到的文件 ----------------

def pricing_text(p):
    k, unit = p["kind"], _unit(p.get("cur", "人民币"))
    disc = f"年付打 {p['disc']} 折" if p.get("disc") else "年付不打折"
    if k == "seat":
        return f"按人计费，{p['price']} {unit}/人/月，{disc}"
    if k == "monthly":
        return f"按人计费，只有月付，{p['price']} {unit}/人/月"
    if k == "annual":
        return f"按人计费，只有年付，{p['price']} {unit}/人/年"
    if k == "team":
        return "按团队计费：" + "；".join(_tier_text(t, unit, "/月") for t in p["tiers"]) + f"；{disc}"
    if k == "tiered":
        return "按人计费，阶梯价：" + "；".join(_tier_text(t, unit, "/人/月") for t in p["tiers"]) + f"（整队按所在档位计价）；{disc}"
    if k == "freemium":
        parts = []
        for name, v in p["versions"]:
            parts.append(f"{name}（对标版本）：{pricing_text({**v, 'cur': p['cur']})}" if isinstance(v, dict) else f"{name}（{v}）")
        return "；".join(parts)
    raise ValueError(k)


def material_text(spec):
    name, group, segment, rule, n, features, comps = spec
    r = RULES[rule]
    names = [r["company"]] + [c[0] for c in comps]
    lines = [f"# 竞品资料（{r['category']}）", "", "## 各家价格与计费方式", ""]
    lines.append(f"- {r['company']}（我方）：{pricing_text(r['price'])}。")
    lines += [f"- {cname}：{pricing_text(p)}。" for cname, p, _ in comps]
    lines += ["", "## 功能对照（来自各家公开资料；“—”表示资料里没写）", ""]
    lines.append("| 功能 | " + " | ".join(names) + " |")
    lines.append("|" + "---|" * (len(names) + 1))
    cells = {cname: c.split() for cname, _, c in comps}
    for i, f in enumerate(features):
        lines.append(f"| {f} | " + " | ".join([r["cells"][f]] + [cells[cname][i] for cname, _, _ in comps]) + " |")
    return "\n".join(lines) + "\n"


def fx_text(rule):
    r = RULES[rule]
    rows = [f"| {c} {CODE[c]} | {r['fx'][c]} |" for c in ("美元", "欧元", "港元", "日元")]
    return "\n".join(["# 汇率表（财务部当期）", "", "| 币种 | 1 单位折合人民币 |", "|---|---|", *rows, ""])


def question_text(spec, index):
    n = spec[4]
    return (
        OPENINGS[index % len(OPENINGS)].format(n=n) + f"\n\n这次按 {n} 人的团队来比。这次适用的工作规则、竞品资料和汇率表在工作目录："
        "工作规则.md、竞品资料.md、汇率表.md。"
    )


# ---------------- 参考答案 ----------------

def compute(spec):
    name, group, segment, rule, n, features, comps = spec
    r = RULES[rule]
    ours = r["company"]
    assert 6 <= len(features) <= 8 and 3 <= len(comps) <= 5, name
    assert set(features) <= set(r["cells"]), name
    if segment == "common":
        assert all(p["kind"] == "seat" and p["cur"] == "人民币" for _, p, _ in comps), name
    else:
        assert any(p["kind"] != "seat" or p["cur"] != "人民币" for _, p, _ in comps), name
    products = [ours] + [c[0] for c in comps]
    raw = {ours: {f: r["cells"][f] for f in features}}
    for cname, _, c in comps:
        vals = c.split()
        assert len(vals) == len(features) and set(vals) <= VALUES, (name, cname)
        raw[cname] = dict(zip(features, vals))
    leads = [f for f in features if raw[ours][f] == "有" and all(raw[c][f] in ("无", "部分") for c in products[1:])]
    others = [f for f in features
              if raw[ours][f] == "有" and f not in leads and not any(raw[c][f] == "有" for c in products[1:])]
    assert len(leads) == 1 and not others, (name, leads, others)
    lead = leads[0]
    prices, how = {}, {}
    for pname, p in [(ours, r["price"])] + [(c[0], c[1]) for c in comps]:
        value, steps = rate(p, n, r)
        prices[pname] = rounded(value, r["places"])
        shown = value.quantize(Decimal("0.0001"))
        how[pname] = "，".join(steps) + f" {'=' if shown == value else '≈'} {shown.normalize():f} → {prices[pname]}"
    low = min(Decimal(v) for v in prices.values())
    cheapest = [p for p, v in prices.items() if Decimal(v) == low]
    assert len(cheapest) == 1, (name, cheapest)
    cheapest = cheapest[0]
    shown = {p: f"{v} {r['unit']}" for p, v in prices.items()}
    if r["mention"] == "never":
        price_rule = "不提价格（这套规则一律不提）"
    elif cheapest == ours:
        price_rule = (f"我方折算后最便宜（{shown[ours]}），可以提价格也可以不提；提的话不能和折算结果矛盾" if r["mention"] == "may"
                      else f"我方折算后最便宜，必须写出我方折算价 {shown[ours]}")
    else:
        price_rule = f"我方不是最便宜（最便宜的是 {cheapest}），不能提价格"
    if r["rows"] == "feature":
        layout = (f"行是功能、列是产品（{ours}放第一列），最后一行放各家折算价；产品列 {len(products)} 个："
                  + "、".join(products) + f"（竞品顺序不限）；功能行 {len(features)} 个：" + "、".join(features) + "（顺序不限）")
    else:
        layout = (f"行是产品（{ours}放第一行）、列是功能，最后一列放各家折算价；产品行 {len(products)} 个："
                  + "、".join(products) + f"（竞品顺序不限）；功能列 {len(features)} 个：" + "、".join(features) + "（顺序不限）")
    return {
        "规则集": f"{rule}（{ours}）",
        "团队人数": n,
        "各家折算价": shown,
        "折算过程": how,
        "折算后最便宜": f"{cheapest}（{shown[cheapest]}）",
        "唯一领先项": f"{lead}（{ours}是“有”；" + "、".join(f"{c} {raw[c][lead]}" for c in products[1:]) + "）",
        "定位语要求": (f"叫“{r['call']}”，放在{r['where']}单独一行，以“{r['prefix']}”开头；只用“{lead}”这一项；不出现"
                     + "、".join(f"“{w}”" for w in r["banned"]) + f"；{price_rule}"),
        "功能格（每格该写的词）": {f: {p: r["words"][raw[p][f]] for p in products} for f in features},
        "表格版式": layout + "；回复里不加别的行、列和文字",
        "我方最便宜": cheapest == ours,
    }


def scenario_package():
    (SCENARIO / "personas").mkdir(parents=True, exist_ok=True)
    (SCENARIO / "profile.md").write_text(TASK + "\n")
    (SCENARIO / "onboarding.md").write_text(ONBOARDING + "\n")
    (SCENARIO / "personas" / "colleague.md").write_text("同事发来竞品对比需求；每道题的需求、竞品资料和工作规则由脚本给出。\n")
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
    competitors = [c[0] for spec in SPECS for c in spec[6]]
    taken = competitors + [r["company"] for r in RULES.values()]
    assert len(taken) == len(set(taken)), sorted({x for x in taken if taken.count(x) > 1})
    (HERE / "rules").mkdir(exist_ok=True)
    for rule, r in RULES.items():
        (HERE / "rules" / f"{rule}.md").write_text(r["text"])
    bank, scripts = [], []
    for index, spec in enumerate(SPECS):
        name, group, segment, rule = spec[:4]
        files = {"工作规则.md": RULES[rule]["text"], "竞品资料.md": material_text(spec), "汇率表.md": fx_text(rule)}
        text = question_text(spec, index)
        bank.append({"name": name, "group": group, "segment": segment, "rules": rule, "text": text, "files": files,
                     "reference": compute(spec)})
        label = {"train": "培养", "same": "考试·同规则", "new": "考试·新规则"}[group]
        scripts.append({"name": name, "title": f"{name} · {label} · {RULES[rule]['company']} {spec[4]} 人", "exam": group != "train",
                        "steps": [{"text": text, "files": files}]})
    (HERE / "questions.json").write_text(json.dumps(bank, ensure_ascii=False, indent=1) + "\n")
    (HERE / "scripts.json").write_text(json.dumps(scripts, ensure_ascii=False, indent=1) + "\n")
    scenario_package()
    ours = sum(q["reference"]["我方最便宜"] for q in bank)
    print(f"{len(bank)} questions ({ours} where ours is cheapest), {len(RULES)} rule sets, scenario at {SCENARIO.name}")


if __name__ == "__main__":
    main()
