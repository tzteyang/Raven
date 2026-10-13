"""五份手写探测答卷；只用 check.output 打包 Office 文件，不从参考答案取风险内容。

uv run --no-project python probes.py
"""

import copy
import json
from pathlib import Path

from check import output

HERE = Path(__file__).resolve().parent
DESTINATION = HERE / "probes" / "probe-contract-sheet.json"

R2_ROWS = [
    ["CG-01", "第三条", "第三条 合同签订后 5 日内，甲方预付合同总价的百分之五十，余款在设备到货后 10 日内付清。",
     "预付50%超过20%；尾款在到货后支付，未以验收合格为前提。", "高", "预付合同总价20%，其余价款在验收合格后支付。"],
    ["CG-02", "附件一第 2 条", "2. 甲方应在设备到货后 5 个工作日内完成验收，逾期未提出书面异议的，视为验收合格。",
     "验收只有5个工作日，少于15个工作日；不提出异议就视为合格，不符合规则。", "高",
     "甲方在设备到货后15个工作日内完成验收；逾期未验收不视为验收合格。"],
    ["CG-03", "缺失", "无", "合同缺少质保条款。", "中", "设备质保期18个月，从验收合格之日起算。"],
    ["CG-05", "缺失", "无", "没有约定保密义务。", "中", "双方对合同内容及履行中知悉的对方商业信息承担保密义务。"],
]

R3_ROWS = [
    ["XQ2", "第五条", "第五条 甲方应在设备到货后 3 个工作日内完成验收，逾期未提出书面异议的，视为验收合格。",
     "验收只有3个工作日，未达到7个工作日；默认验收合格违反工作规则。", "中",
     "甲方在到货后7个工作日内完成验收；逾期未验收不视为验收合格。"],
    ["XQ3", "缺失", "无", "合同没有质保条款。", "中", "质保期24个月，从验收合格之日起算。"],
    ["XQ4", "第九条", "第九条 乙方逾期交货的，每逾期一日按合同总价¥204,000的 0.01% 支付违约金。",
     "逾期交货违约金为每天0.01%，低于规则下限0.05%。", "低", "乙方逾期交货，每日按合同总价的0.05%支付违约金。"],
    ["XQ5", "缺失", "无", "保密条款缺失。", "高", "双方对合同内容及履行中知悉的对方商业信息承担保密义务。"],
    ["XQ6", "缺失", "无", "缺少付款前开具增值税专用发票的约定。", "低", "甲方每次付款前，乙方先开具等额增值税专用发票。"],
]


def main() -> None:
    bank = {q["name"]: q for q in json.loads((HERE / "questions.json").read_text())}
    t12, y07 = bank["t12"], bank["y07"]
    right2, _, _ = output(t12, R2_ROWS)
    right3, _, _ = output(y07, R3_ROWS)

    # 漏报缺失的保密条款；另一行错误降级；一条现有风险的批注遗漏。
    # 信息页和一句话按交付行数填，验证“漏报”不会再连带变成数值和批注错误。
    wrong_rows2 = copy.deepcopy(R2_ROWS[:3])
    wrong_rows2[0][4] = "中"
    wrong_notes2 = [("第三条", "CG-01：预付款50%过高，尾款应在验收合格后支付。"),
                    ("2. ", "CG-02：验收期不足15个工作日，且逾期未异议被视为验收合格。")]
    wrong2, _, _ = output(t12, wrong_rows2, notes=wrong_notes2)

    # R3 低风险错写成中风险，建议仍低于门槛；照搬R2的Sheet名，作者写错；回复的数字与交付不同。
    wrong_rows3 = copy.deepcopy(R3_ROWS)
    wrong_rows3[2][4] = "中"
    wrong_rows3[2][5] = "乙方逾期交货，每日按合同总价的0.01%支付违约金。"
    wrong3, _, _ = output(y07, wrong_rows3, author="审合君", sheet_names=["风险明细", "审查信息"],
                         reply="报了 6 项风险，其中 2 项高风险。")

    wrapper, _, _ = output(t12, R2_ROWS, reply="以下为核对结果，R999 属于高风险。\n报了 4 项风险，其中 2 项高风险。\n两个文件已检查完毕。")
    probes = [
        {"name": "t12", "label": "right", "expect": [], "answer": right2},
        {"name": "t12", "label": "wrong", "expect": ["S-items", "S-level", "S-comment"], "answer": wrong2},
        {"name": "y07", "label": "right", "expect": [], "answer": right3},
        {"name": "y07", "label": "wrong", "expect": ["S-level", "S-sheet", "S-comment", "S-reply"], "answer": wrong3},
        {"name": "t12", "label": "right-plus-wrapper", "expect": ["S-reply"], "answer": wrapper},
    ]
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    DESTINATION.write_text(json.dumps(probes, ensure_ascii=False, indent=2) + "\n")
    print(f"5 hand-written probes -> {DESTINATION}")


if __name__ == "__main__":
    main()
