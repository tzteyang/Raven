"""自检：另写一遍算法，只读员工看到的文件（工作规则、本周记录、上周周报、指标口径表），重算每个指标的本周数、上周数和
变化，以及要总监决定的事和下周计划，和参考答案逐题比对。

  python3 check.py
"""

import json
import re
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent


def catalog(text):
    out = {}
    for name, aliases, unit, kind in re.findall(r"^\| (\S+) \| (\S+) \| (\S+) \| (\S+) \|$", text, re.M)[1:]:
        for word in [name, *aliases.split("、")]:
            out[word] = (name, unit, kind)
    return out


def number(text: str) -> Decimal:
    text = text.strip().rstrip("%")
    if text.endswith("万"):
        return Decimal(text[:-1].strip()) * 10000
    return Decimal(text)


def main():
    wrong = []
    for q in json.loads((HERE / "questions.json").read_text()):
        f, ref = q["files"], q["reference"]
        names = catalog(f["指标口径表.md"])
        words = sorted(names, key=len, reverse=True)
        now = {}
        for label, value in re.findall(r"汇总：本周(\S+?) ?([\d.]+ ?万?%?)$", f["本周记录.md"], re.M):
            now[names[label][0]] = number(value)
        last = {}
        body = f["上周周报.md"].split("本周结果：", 1)[1].strip().rstrip("。")
        for part in body.split("；"):
            label = next(w for w in words if part.startswith(w))
            last[names[label][0]] = number(part[len(label):].strip().split()[0])
        for metric, value in now.items():
            item = ref["指标"].get(metric)
            if item is None:
                wrong.append((q["name"], metric, "missing"))
                continue
            kind = names[metric][2]
            if metric not in last:
                expected = "—"
            elif kind == "比率类":
                expected = f"{(value - last[metric]).quantize(Decimal('0.0001'))}pp"
            else:
                expected = f"{((value / last[metric] - 1) * 100).quantize(Decimal('0.0001'))}%"
            if item["变化（未取舍）"] != expected:
                wrong.append((q["name"], metric, item["变化（未取舍）"], expected))
        if set(now) != set(ref["指标"]):
            wrong.append((q["name"], "metric set", sorted(now), sorted(ref["指标"])))
        asks = re.findall(r"(?:要总监拍板|需要总监决定|请总监确认)(.+)$", f["本周记录.md"], re.M)
        plans = re.findall(r"：(下周.+)$", f["本周记录.md"], re.M)
        if sorted(asks) != sorted(ref["要总监决定的事（都要写）"]) or sorted(plans) != sorted(ref["下周要做的事（都要写）"]):
            wrong.append((q["name"], "asks/plans", asks, plans))
    print("mismatches:", wrong or "none")
    assert not wrong


if __name__ == "__main__":
    main()
