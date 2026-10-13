"""自检：另写一遍算法，只读员工看到的三份文件（订单记录、政策表、工作规则），重算每道题该怎么退、退多少，和参考答案逐题比对。

  python3 check.py
"""

import json
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent


def field(text: str, key: str) -> str:
    found = re.search(rf"^- {key}：(.+)$", text, re.M)
    assert found, key
    return found.group(1).strip()


def yuan(text: str) -> Decimal:
    return Decimal(re.search(r"([\d.]+) 元", text).group(1))


def recompute(question: dict) -> tuple[str, Decimal, bool]:
    order, table, rules = (question["files"][name] for name in ("订单记录.md", "退款政策表.md", "工作规则.md"))
    kind = field(order, "课程类型")
    row = re.search(rf"^\| {kind} \| (\d+) 天 \| (\d+) 节 \| (\d+)% \|$", table, re.M)
    days, lessons, rate = (int(x) for x in row.groups())
    buy = date.fromisoformat(field(order, "购课日期"))
    today = date.fromisoformat(re.search(r"今天是 (\d{4}-\d{2}-\d{2})", question["text"]).group(1))
    day = (today - buy).days + (0 if "购课次日算第 1 天" in rules else 1)
    attended, total = int(field(order, "已听节数")), int(field(order, "总节数"))
    pay = field(order, "付款方式")
    if pay.startswith("全款"):
        base = yuan(pay)
    else:
        each, paid = re.search(r"每期 ([\d.]+) 元；已付 (\d+) 期", pay).groups()
        base = Decimal(each) * int(paid)
    if day <= days and attended <= lessons:
        return "全额退", base, False
    part = base * (total - attended) / total
    fee = (part * rate / 100).quantize(Decimal("0.01"))
    floor = re.search(r"不足 ([\d.]+) 元的，按", rules)
    if floor and fee < Decimal(floor.group(1)):
        fee = Decimal(floor.group(1))
    return "按比例退", part - fee, True


def main() -> None:
    bank = json.loads((HERE / "questions.json").read_text())
    wrong = []
    for question in bank:
        method, amount, _ = recompute(question)
        ref = question["reference"]
        if (method, f"{amount.quantize(Decimal('0.01'))}") != (ref["退法"], ref["应退金额"]):
            wrong.append((question["name"], method, amount, ref["退法"], ref["应退金额"]))
        words = re.search(r"出现(.+?)中的任何一个", question["files"]["工作规则.md"]).group(1)
        keywords = re.findall(r"“(.+?)”", words)
        message = re.search(r"「(.+)」", question["text"], re.S).group(1)
        if any(word in message for word in keywords) != ref["需转人工"]:
            wrong.append((question["name"], "escalation", keywords, ref["需转人工"]))
    groups = {}
    for question in bank:
        groups.setdefault((question["group"], question["rules"]), []).append(question["name"])
    print(json.dumps({f"{g}/{r}": len(n) for (g, r), n in sorted(groups.items())}, ensure_ascii=False))
    print("mismatches:", wrong or "none")
    assert not wrong


if __name__ == "__main__":
    main()
