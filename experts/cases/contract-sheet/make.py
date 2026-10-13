"""采购合同风险清单：三套工作规则、40 道题（20 培养 + 10 道同规则考试 + 10 道换规则考试）、参考答案和 Studio 场景包。

  python3 make.py

依据《专家自进化》8.2 的案例改写成「工作规则随题交给员工」：连锁品牌（甲方，采购方）收到供应商发来的采购合同 .docx，法务要
按当次采购审查清单交两份文件：Excel 风险清单（两个 Sheet、表头写死）和 Word 批注稿（只加批注、不改原文）。三套清单编号、门槛和
风险等级不同。培养题和同规则考试题用 R1（沁茶，采购制冰机）、R2（麦乐烘焙，采购烤箱）交替，换规则考试题全用员工从没见过的 R3
（鲜趣超市，采购冷柜：多一条发票要求、风险等级三档）。每题一份合同按种子生成：常见题条款里都是阿拉伯数字、最多缺一条条款；
边界题写成“百分之五十”“叁拾日”“半年”、工作日和自然日混用、关键条款写在附件里、缺不止一条、要批注的段落里有加粗金额。每题都有
一条对甲方有利的条款当干扰（不该报）。参考答案逐条写出该报的编号、等级、条款位置和不该报的条款；check.py 只读员工看到的文件
另判一遍，并真的用标准库做出一份全对的 Excel 和批注稿让 measure.py 量一遍。
"""

import base64
import importlib.util
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENARIO = HERE / "wkr-contract-sheet"
sys.path.insert(0, str(HERE.parents[1] / "common"))
from officetext import docx_text  # noqa: E402

_spec = importlib.util.spec_from_file_location("contract_review_make", HERE.parent / "contract-review" / "make.py")
_cr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cr)
package, para, table, upper_amount = _cr.package, _cr.para, _cr.table, _cr.upper_amount

CN_NUM = {1: "一", 2: "二", 3: "三", 5: "五", 6: "六", 7: "七", 9: "九", 10: "十", 12: "十二", 14: "十四", 15: "十五", 18: "十八",
          20: "二十", 21: "二十一", 24: "二十四", 30: "三十", 50: "五十", 60: "六十", 40: "四十"}
CAP_NUM = {3: "叁", 5: "伍", 7: "柒", 10: "拾", 14: "拾肆", 15: "拾伍", 20: "贰拾", 21: "贰拾壹", 30: "叁拾"}

RULES = {
    "R1": {
        "buyer": "沁茶", "item": "商用制冰机", "units": "台", "author": "沁茶法务", "levels": ("高", "中"),
        "prepay": 30, "accept_days": 10, "warranty": 12, "penalty": 0.05, "invoice": False,
        "codes": {"prepay": ("R001", "高"), "accept": ("R002", "中"), "warranty": ("R003", "中"), "penalty": ("R004", "中"),
                  "secret": ("R005", "高")},
        "sheet": ("风险项", "审查说明"), "header": ["编号", "条款位置", "合同原文", "问题", "风险等级", "修改建议"],
        "files": ("风险清单.xlsx", ".批注稿.docx"),
    },
    "R2": {
        "buyer": "麦乐烘焙", "item": "商用烤箱", "units": "台", "author": "麦乐烘焙法务部", "levels": ("高", "中"),
        "prepay": 20, "accept_days": 15, "warranty": 18, "penalty": 0.1, "invoice": False,
        "codes": {"prepay": ("CG-01", "高"), "accept": ("CG-02", "高"), "warranty": ("CG-03", "中"), "penalty": ("CG-04", "中"),
                  "secret": ("CG-05", "中")},
        "sheet": ("风险明细", "审查信息"), "header": ["清单编号", "所在条款", "原文摘录", "风险说明", "等级", "建议改法"],
        "files": ("采购合同风险清单.xlsx", "-法务批注.docx"),
    },
    "R3": {
        "buyer": "鲜趣超市", "item": "立式冷柜", "units": "台", "author": "鲜趣法务", "levels": ("高", "中", "低"),
        "prepay": 30, "accept_days": 7, "warranty": 24, "penalty": 0.05, "invoice": True,
        "codes": {"prepay": ("XQ1", "高"), "accept": ("XQ2", "中"), "warranty": ("XQ3", "中"), "penalty": ("XQ4", "低"),
                  "secret": ("XQ5", "高"), "invoice": ("XQ6", "低")},
        "sheet": ("风险项", "审查说明"), "header": ["编号", "条款位置", "合同原文", "问题", "风险等级", "修改建议"],
        "files": ("风险清单.xlsx", ".批注稿.docx"),
    },
}


def rules_text(rule: str) -> str:
    r = RULES[rule]
    c = r["codes"]
    sheet1, sheet2 = r["sheet"]
    head = " | ".join(r["header"])
    xlsx, docx_suffix = r["files"]
    lines = [f"# {r['buyer']} · 采购合同审查工作规则", "",
             f"供应商发来的采购合同（.docx），按下面的采购审查清单审，交两份文件：Excel 风险清单和 Word 批注稿。", "",
             "## 采购审查清单", ""]
    lines.append(f"1. {c['prepay'][0]} 预付款不超过合同总价的 {r['prepay']}%；尾款在验收合格后支付。（{c['prepay'][1]}风险）")
    lines.append(f"2. {c['accept'][0]} 验收期不少于 {r['accept_days']} 个工作日；逾期未验收不视为验收合格。（{c['accept'][1]}风险）")
    lines.append(f"3. {c['warranty'][0]} 质保期不少于 {r['warranty']} 个月，从验收合格之日起算。（{c['warranty'][1]}风险）")
    lines.append(f"4. {c['penalty'][0]} 乙方逾期交货的违约金每日不低于合同总价的 {r['penalty']}%。（{c['penalty'][1]}风险）")
    lines.append(f"5. {c['secret'][0]} 采购合同必须有保密条款。（{c['secret'][1]}风险）")
    if r["invoice"]:
        lines.append(f"6. {c['invoice'][0]} 甲方付款前，乙方须开具增值税专用发票（合同里要写明）。（{c['invoice'][1]}风险）")
    lines += [
        "",
        "## 交付",
        "",
        f"1. Excel 风险清单，文件名“{xlsx}”，两个 Sheet：",
        f"   - 第一个 Sheet 名为“{sheet1}”，第一行是表头，列和顺序固定为：{head}。合同里违反清单的每一条（包括整条缺失的）各写一行；"
        "同一编号有几个问题也只写一行，行的先后不限。“" + r["header"][0] + "”写清单编号，“" + r["header"][4] + "”写清单给的等级（"
        + "、".join(r["levels"]) + "），条款缺失的“" + r["header"][1] + "”写“缺失”、“" + r["header"][2] + "”写“无”。",
        "   - 原文摘录要来自原合同，覆盖本行指出的问题，可以摘整条或相关原句；问题栏写清这个编号的全部不合规点；修改建议给出满足该编号全部要求的具体条款文字。措辞可不同，数值和条件必须满足清单。",
        f"   - 第二个 Sheet 名为“{sheet2}”，第一行表头为“项目 | 内容”，下面依次写四行：合同名称（原合同标题，书名号可省）、审查依据（写“{r['buyer']}采购审查清单”）、风险项数、审查结论。风险项数是第一个 Sheet 的风险行数；没有风险写“可以签署”，有风险写“需修改后签署”。",
        f"2. Word 批注稿，文件名是原合同文件名去掉“.docx”后加“{docx_suffix}”：在原合同上只加批注、不改原文（不加修订）。风险清单里"
        "的每一行在批注稿里都有一条批注：批在违反清单的那一条条款上，内容写清单编号和问题；条款整条缺失的，批注挂在合同标题上。批注"
        f"作者写“{r['author']}”。段落文字和顺序、页眉、表格以及原有加粗格式均保留；不覆盖原文件。",
        "3. 不违反清单的条款不报、不批注（例如对甲方有利的条款）。清单以外的问题不报。",
        "4. 只交这两份文件，回复里只写一句话：报了几项风险、其中几项高风险。两项数字都按实际交付的 Excel 风险行统计；前后不加开场白、核对过程或其他说明。",
        "",
        "## 补充口径",
        "",
        "- 合同里的数字可能写成中文（例如“百分之五十”“叁拾日”“半年”），换算后再和清单比：半年按 6 个月、一年按 12 个月算。",
        f"- 验收期：合同写的是工作日就直接比；写的是自然日（“日”“天”“自然日”）的，按 7 个自然日等于 5 个工作日换算，换算后少于 "
        f"{r['accept_days']} 个工作日就报。天数取整数时，至少要 {(r['accept_days'] * 7 + 4) // 5} 个自然日才达到门槛；换算中间不四舍五入。",
        "- 验收条款没写逾期视同合格的约定，就只按验收期限审；如果写了逾期视同合格，即使期限够长也要报。尾款没有约定验收合格后支付的，也违反预付款这一编号。",
        "- 质保期从发货之日、交货之日或签订之日起算的，不符合“从验收合格之日起算”，要报。",
        "- 合同附件里的条款和正文一样审；条款写在附件里的，“条款位置”写附件里的条款编号（例如“附件一第 2 条”）。",
        "- 一条条款违反清单里的两个不同编号，就报两行；一条编号的条款整条缺失，问题写清缺少什么，建议补齐对应条款。",
    ]
    return "\n".join(lines) + "\n"


SPECS = []
for i in range(1, 21):
    SPECS.append((f"t{i:02d}", "train", "edge" if i > 10 else "common", "R1" if i % 2 else "R2"))
for i in range(1, 11):
    SPECS.append((f"x{i:02d}", "same", "edge" if i > 5 else "common", "R1" if i % 2 else "R2"))
for i in range(1, 11):
    SPECS.append((f"y{i:02d}", "new", "edge" if i > 5 else "common", "R3"))

TASK = (
    "你是连锁品牌法务部的合同审查助理。供应商发来的采购合同（.docx）在工作目录里，按这次适用的采购合同审查工作规则审，交付 Excel "
    "风险清单和 Word 批注稿两份文件。工作目录里有工作规则和合同原件。"
)
ONBOARDING = "以后供应商发来的采购合同，我都会把这次适用的采购合同审查工作规则和合同 .docx 一起给你，你审完交 Excel 风险清单和 Word 批注稿。不同品牌的清单不一样，以当次给的为准。"
CRITERIA = [
    ("S-items", "red_line",
     "该报的都报、不该报的不报：风险清单第一个 Sheet 里的行，和参考答案列出的违反清单的各条一一对上（编号写对；整条缺失的也要报）；"
     "参考答案列出的不该报的条款（例如对甲方有利的条款、本来合规的条款）不能出现。漏报、编号写错、多报，每处记一处。"
     "同一编号的几个问题只报一行。漏行导致批注也漏、错编号同步出现在批注里的，均只在本项记。若没有可读取的 Excel，只在 S-sheet 记缺文件，本项不再记。"),
    ("S-level", "standard",
     "风险行内容：对正确识别且实际写出的风险行，等级按清单，位置按原合同（附件写附件条款编号、缺失写“缺失”），原文摘录来自对应条款"
     "并覆盖本行问题（缺失写“无”），问题写全该编号所有不合规点，建议是能满足该编号全部要求的具体条款；参考答案给了问题要点和合规改法示例，"
     "措辞可不同。每个不符单元格记一处；同一错误原因不重复记。漏行、多报、错编号只在 S-items 记，本项不连带记。没有 Excel 时本项不记。"),
    ("S-sheet", "standard",
     "Excel 结构：文件名对；两个 Sheet 的名字、顺序对；第一个 Sheet 的表头列和顺序照规则；第二个 Sheet 四行写对（风险项数、审查结论和"
     "第一个 Sheet 对得上）。每处不符记一处（测量值列出了 Sheet 名、表头和各行）。没交可读 Excel 只记一处缺文件。"
     "第二个 Sheet 的项数、结论按实际风险行核对，漏报导致总数比参考答案少不在本项重复记；正文前后说明不在本项记。"),
    ("S-comment", "standard",
     "Word 批注稿：文件名对；只加批注、没改原文、没加修订（测量值核对了）；风险清单每一行都有一条批注批在对应条款上（缺失的批在合同"
     "标题上）、内容写了清单编号和问题；批注作者对；没有单独多加的无关批注。每处不符记一处。没交可读 Word 只记一处缺文件。"
     "只按 Excel 实际写出的风险行检查对应批注；Excel 本身的漏报、多报、错编号、错位置或问题表述，同样错误传到 Word 的不再记，分别归 S-items 或 S-level。"
     "正文直接被改和格式丢失按受影响段落各记一处；同一段因加了修订导致原文变动只记一处。"),
    ("S-reply", "standard",
     "回复：只有一句话，报的风险项数和高风险项数和实际 Excel 对得上。数对不上记一处。前后加的开场白、核对过程或其他说明合计只在本项记一处，"
     "其中的数字、编号、建议不计入交付内容、不在别项重复记。只交规定的两份文件，多交其他文件记一处；两份规定文件缺失已分别在 S-sheet 或 S-comment 记，不重复记。"),
]
SUPPLIERS = ["广州冰域制冷设备有限公司", "佛山雪狮厨房设备有限公司", "宁波凯冷电器有限公司", "苏州恒焙机械有限公司", "青岛海凌冷链设备有限公司"]


def say_percent(n, edge, rng):
    if edge and rng.random() < 0.5 and n in CN_NUM:
        return f"百分之{CN_NUM[n]}"
    return f"{n}%"


def say_days(n, edge, rng, unit="日"):
    if edge and rng.random() < 0.5 and n in CAP_NUM:
        return f"{CAP_NUM[n]}{unit}"
    return f"{n} {unit}" if unit != "个工作日" else f"{n} 个工作日"


def build(spec, rng):
    name, group, segment, rule = spec
    r = RULES[rule]
    edge = segment == "edge"
    kinds = ["prepay", "accept", "warranty", "penalty", "secret"] + (["invoice"] if r["invoice"] else [])
    want = min(rng.randint(3, 4) if not edge else rng.randint(4, 5), len(kinds) - 1)
    broken = set(rng.sample(kinds, want))
    if not edge and "secret" in broken and "invoice" in broken:
        broken.discard("invoice")  # 常见题最多缺一条条款
    if name == "y06":
        broken.add("accept")
        if len(broken) == len(kinds):
            broken.remove("penalty")
    elif name == "y08":
        broken.discard("accept")
    supplier = rng.choice(SUPPLIERS)
    count = rng.choice([20, 30, 40, 60])
    unit_price = rng.choice([3800, 4500, 5200, 6800, 8800])
    total = count * unit_price
    annex = edge and rng.random() < 0.6
    facts, lines = {}, {}
    # 第三条 付款
    if "prepay" in broken:
        pct = rng.choice([p for p in (40, 50, 60) if p > r["prepay"]])
        said = say_percent(pct, edge, rng)
        lines["prepay"] = f"第三条 合同签订后 5 日内，甲方预付合同总价的{' ' if said[0].isdigit() else ''}{said}，余款在设备到货后 10 日内付清。"
    else:
        pct = rng.choice([p for p in (10, 20, 30) if p <= r["prepay"]])
        said = say_percent(pct, edge, rng)
        lines["prepay"] = f"第三条 合同签订后 5 日内，甲方预付合同总价的{' ' if said[0].isdigit() else ''}{said}，余款在验收合格后 15 日内付清。"
    facts["prepay"] = pct
    # 第五条 验收
    if "accept" in broken:
        if edge and rng.random() < 0.5:
            days, unit = rng.choice([d for d in (7, 9, 10, 14) if d * 5 < r["accept_days"] * 7]), "日"
        else:
            days, unit = rng.choice([d for d in (3, 5) if d < r["accept_days"]]), "个工作日"
        tail = "，逾期未提出书面异议的，视为验收合格。"
    else:
        if edge and rng.random() < 0.5:
            days, unit = rng.choice([d for d in (10, 14, 21, 30) if d * 5 >= r["accept_days"] * 7]), "日"
        else:
            days, unit = rng.choice([d for d in (10, 15, 20) if d >= r["accept_days"]]), "个工作日"
        tail = "。"
    if name in ("y06", "y08"):
        days, unit, tail = (9 if name == "y06" else 10), "日", "。"
    lines["accept"] = f"第五条 甲方应在设备到货后 {say_days(days, edge, rng, unit) if unit == '日' else f'{days} 个工作日'}内完成验收{tail}"
    facts["accept"] = (days, unit)
    # 第七条 质保
    if "warranty" in broken:
        if rng.random() < 0.5:
            months, start = rng.choice([m for m in (6, 9, 12) if m < r["warranty"]]), "验收合格之日"
        else:
            months, start = rng.choice([r["warranty"], r["warranty"] + 6]), rng.choice(["设备发货之日", "合同签订之日"])
    else:
        months, start = rng.choice([r["warranty"], r["warranty"] + 12]), "验收合格之日"
    said_months = "半年" if edge and months == 6 and rng.random() < 0.7 else ("一年" if edge and months == 12 and rng.random() < 0.5 else f"{months} 个月")
    lines["warranty"] = f"第七条 质保期 {said_months}，自{start}起计算。"
    facts["warranty"] = (months, start)
    # 第九条 违约
    if "penalty" in broken:
        rate = rng.choice([x for x in (0.01, 0.02, 0.03) if x < r["penalty"]])
    else:
        rate = rng.choice([x for x in (0.05, 0.1, 0.2) if x >= r["penalty"]])
    lines["penalty"] = f"第九条 乙方逾期交货的，每逾期一日按合同总价的 {rate}% 支付违约金。"
    facts["penalty"] = rate
    # 保密
    lines["secret"] = None if "secret" in broken else "第十条 保密：双方对本合同内容及履行中知悉的对方商业信息负有保密义务。"
    # 发票（R3）
    if r["invoice"]:
        lines["invoice"] = None if "invoice" in broken else "第四条 甲方每次付款前，乙方应先开具等额增值税专用发票。"
    if edge and name not in ("y06", "y08") and rng.random() < 0.5:
        absent = rng.choice([kind for kind in ("accept", "warranty", "penalty") if kind in broken])
        lines[absent] = None
    # 干扰：对甲方有利的管辖、对甲方有利的付款
    lure = "第十二条 因本合同引起的争议，由甲方所在地人民法院管辖。"
    clause_order = ["prepay", "invoice", "accept", "warranty", "penalty", "secret"]
    body = [("b", f"《{r['item']}采购合同》")]
    blocks = [para(body), para([f"甲方（采购方）：{r['buyer']}"]), para([f"乙方（供应方）：{supplier}"]),
              para([f"第一条 乙方向甲方供应{r['item']} {count} {r['units']}，型号和配置见报价表。"]),
              para(["第二条 合同总价为人民币", ("b", f"{upper_amount(total)}（¥{total:,}）") if edge else f"{upper_amount(total)}（¥{total:,}）", "，含 13% 增值税。"])]
    rows = [["设备", "数量", "单价", "金额"], [r["item"], f"{count} {r['units']}", f"¥{unit_price:,}", f"¥{total:,}"]]
    blocks.append(table(rows))
    in_annex = set()
    candidates = [k for k in ("warranty", "accept") if lines.get(k)]
    if annex and candidates:
        moved = rng.choice(candidates)
        in_annex.add(moved)
    for kind in clause_order:
        text = lines.get(kind)
        if kind in in_annex:
            blocks.append(para([f"第{'五' if kind == 'accept' else '七'}条 {'验收' if kind == 'accept' else '质保'}按附件一执行。"]))
            continue
        if text is None:
            continue
        if kind == "penalty" and edge:
            blocks.append(para(["第九条 乙方逾期交货的，每逾期一日按合同总价", ("b", f"¥{total:,}"), f"的 {rate}% 支付违约金。"]))
            lines[kind] = f"第九条 乙方逾期交货的，每逾期一日按合同总价¥{total:,}的 {rate}% 支付违约金。"
        else:
            blocks.append(para([text]))
    blocks.append(para([lure]))
    blocks.append(para(["第十三条 本合同一式两份，自双方签字盖章之日起生效。"]))
    annex_text = None
    if in_annex:
        moved = next(iter(in_annex))
        annex_text = lines[moved].replace("第五条 ", "").replace("第七条 ", "")
        blocks += [para([("b", "附件一 质量和验收约定")]), para(["1. 设备到货后乙方负责安装调试。"]), para([f"2. {annex_text}"])]
    data = package(f"{r['buyer']}采购合同 · {supplier}", blocks, [])
    file = f"{r['item']}采购合同.docx"
    return {"broken": broken, "kinds": kinds, "facts": facts, "lines": lines, "in_annex": in_annex, "docx": data, "file": file,
            "supplier": supplier, "total": total, "edge": edge, "lure": lure}


def expected(rule, d) -> list[dict]:
    r = RULES[rule]
    where = {"prepay": "第三条", "accept": "第五条", "warranty": "第七条", "penalty": "第九条", "secret": "缺失", "invoice": "缺失"}
    labels = {"prepay": "付款", "accept": "验收", "warranty": "质保", "penalty": "逾期交货违约金", "secret": "保密", "invoice": "付款前开票"}
    suggestions = {
        "prepay": f"甲方预付合同总价的 {r['prepay']}%，余款在验收合格后支付。",
        "accept": f"甲方应在设备到货后 {r['accept_days']} 个工作日内完成验收，逾期未验收不视为验收合格。",
        "warranty": f"质保期为 {r['warranty']} 个月，自验收合格之日起计算。",
        "penalty": f"乙方逾期交货，每日按合同总价的 {r['penalty']}% 支付违约金。",
        "secret": "双方对本合同内容及履行中知悉的对方商业信息负有保密义务。",
        "invoice": "甲方每次付款前，乙方须开具等额增值税专用发票。",
    }
    out = []
    for kind in d["kinds"]:
        if kind not in d["broken"]:
            continue
        code, level = r["codes"][kind]
        clause = d["lines"].get(kind)
        place = "缺失" if clause is None else "附件一第 2 条" if kind in d["in_annex"] else where[kind]
        issues = []
        if clause is None:
            issues.append(f"合同缺少{labels[kind]}条款")
        elif kind == "prepay":
            if d["facts"][kind] > r["prepay"]:
                issues.append(f"预付 {d['facts'][kind]}%，超过 {r['prepay']}%")
            if "验收合格后" not in clause:
                issues.append("尾款按设备到货支付，没约定在验收合格后支付")
        elif kind == "accept":
            days, unit = d["facts"][kind]
            workdays = days if unit == "个工作日" else days * 5 / 7
            if workdays < r["accept_days"]:
                issues.append(f"验收期 {days} {unit}，折合 {workdays:.4f} 个工作日，少于 {r['accept_days']} 个工作日")
            if "视为验收合格" in clause:
                issues.append("逾期未提出异议被视为验收合格")
        elif kind == "warranty":
            months, start = d["facts"][kind]
            if months < r["warranty"]:
                issues.append(f"质保 {months} 个月，少于 {r['warranty']} 个月")
            if start != "验收合格之日":
                issues.append(f"从{start}起算，不是从验收合格之日起算")
        elif kind == "penalty":
            issues.append(f"违约金每日 {d['facts'][kind]}%，低于 {r['penalty']}%")
        assert issues, (kind, clause, d["facts"])
        quote = clause or "无"
        if kind in d["in_annex"]:
            quote = "2. " + quote.split(" ", 1)[1]
        out.append({"编号": code, "等级": level, "条款位置": place,
                    "合同原文": quote, "问题要点": issues, "为什么": "；".join(issues), "合规改法示例": suggestions[kind]})
    return out


def reference(spec, d) -> dict:
    name, group, segment, rule = spec
    r = RULES[rule]
    rows = expected(rule, d)
    high = sum(1 for x in rows if x["等级"] == "高")
    fine = [k for k in d["kinds"] if k not in d["broken"]]
    labels = {"prepay": "第三条（预付款）", "accept": "第五条（验收）", "warranty": "第七条（质保）", "penalty": "第九条（违约金）",
              "secret": "保密条款", "invoice": "第四条（发票）"}
    return {
        "规则集": f"{rule}（{r['buyer']}）",
        "原合同文件": d["file"],
        "该报的风险（一条一行）": rows,
        "风险项数": len(rows),
        "其中高风险": high,
        "审查结论": "需修改后签署",
        "不该报的条款": [("附件一第 2 条" if k in d["in_annex"] else labels[k]) + "：已合规" for k in fine]
                        + ["第十二条（争议由甲方所在地人民法院管辖）：对甲方有利，清单不管"],
        "Excel 文件名": r["files"][0],
        "Excel 两个 Sheet": list(r["sheet"]),
        "第一个 Sheet 表头": r["header"],
        "第二个 Sheet 四行": [["合同名称", d["file"][:-5]], ["审查依据", r["buyer"] + "采购审查清单"],
                            ["风险项数", len(rows)], ["审查结论", "需修改后签署"]],
        "批注稿文件名": d["file"][:-5] + r["files"][1],
        "批注作者": r["author"],
        "原文的文字版": docx_text(d["docx"]),
    }


def scenario_package():
    (SCENARIO / "personas").mkdir(parents=True, exist_ok=True)
    (SCENARIO / "profile.md").write_text(TASK + "\n")
    (SCENARIO / "onboarding.md").write_text(ONBOARDING + "\n")
    (SCENARIO / "personas" / "legal.md").write_text("法务负责人每收到供应商的采购合同就要风险清单和批注稿；每道题的合同 .docx 和规则由脚本给出。\n")
    (SCENARIO / "scenario.json").write_text(json.dumps({
        "initial": [],
        "criteria": [{"id": i, "check": text, "severity": severity} for i, severity, text in CRITERIA],
    }, ensure_ascii=False, indent=1) + "\n")
    visible = ["counterpart", "analyst", "curator"]
    (SCENARIO / "contract.json").write_text(json.dumps(
        {"checks": {i: {"visibility": visible} for i, _, _ in CRITERIA}}, ensure_ascii=False, indent=1) + "\n")


def main():
    assert len({s[0] for s in SPECS}) == 40
    (HERE / "rules").mkdir(exist_ok=True)
    bank, scripts = [], []
    for spec in SPECS:
        name, group, segment, rule = spec
        d = build(spec, random.Random(name))
        assert 3 <= len(d["broken"]) < len(d["kinds"]), (name, d["broken"])
        assert len([k for k in d["kinds"] if d["lines"].get(k) is None]) <= (1 if segment == "common" else 3)
        files = {"工作规则.md": rules_text(rule), d["file"]: "base64:" + base64.b64encode(d["docx"]).decode()}
        task = (f"{d['supplier']}发来了《{RULES[rule]['item']}采购合同》，在工作目录：{d['file']}。按这次适用的采购合同审查工作规则"
                "（工作规则.md）审，交付 Excel 风险清单和 Word 批注稿。")
        bank.append({"name": name, "group": group, "segment": segment, "rules": rule, "text": task, "files": files,
                     "reference": reference(spec, d)})
        label = {"train": "培养", "same": "考试·同规则", "new": "考试·新规则"}[group]
        scripts.append({"name": name, "title": f"{name} · {label} · {RULES[rule]['buyer']}", "exam": group != "train",
                        "steps": [{"text": task, "files": files}]})
    for rule in RULES:
        (HERE / "rules" / f"{rule}.md").write_text(rules_text(rule))
    (HERE / "questions.json").write_text(json.dumps(bank, ensure_ascii=False, indent=1) + "\n")
    (HERE / "scripts.json").write_text(json.dumps(scripts, ensure_ascii=False, indent=1) + "\n")
    scenario_package()
    print(f"{len(bank)} questions, scenario at {SCENARIO.name}")


if __name__ == "__main__":
    main()
