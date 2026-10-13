"""自检：另写一遍，只读员工看到的文件（工作规则.md、线索.md），从规则原文读题数上限、各类数量要求、必问的事、结尾写法、
排序和一题一问的口径，从线索里认出已知信息，和参考答案比对；再独立量一遍示例清单，确认示例本身合规。

  python3 check.py
"""

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
ORDER = ["背景", "难点", "影响", "需求回报"]
CLOSED = ("是不是", "对不对", "有没有", "是否", "能否", "可否", "会不会", "要不要", "能不能", "行不行")


def rules_of(text: str) -> dict:
    limit = int(re.search(r"清单不超过 (\d+) 题", text).group(1))
    most = int(re.search(r"背景类不超过 (\d+) 题", text).group(1))
    impact = int(re.search(r"影响类至少 (\d+) 题", text).group(1))
    payoff = re.search(r"需求回报类至少 (\d+) 题", text)
    must = re.search(r"必须问到这四件事：(.+?)。", text).group(1).split("、")
    closing = re.search(r"以“(.+?)”开头", text).group(1)
    return {"max": limit, "background": most, "impact": impact, "payoff": int(payoff.group(1)) if payoff else 0,
            "must": must, "closing": closing, "order": "按类别排" in text, "single": "一题只问一件事" in text}


def known_of(lead: dict) -> set[str]:
    """Every value the lead states, wherever it sits (fields, the form message, public notes)."""
    found = set(lead["表单字段"])
    for note in lead["公开信息（公众号、官网）"]:
        if "：" in note:
            found.add(note.split("：")[0])
    return found


def audit(r: dict, text: str) -> list[str]:
    lines = [line for line in text.splitlines() if line.strip()]
    problems = []
    if not lines[-1].startswith(r["closing"]):
        problems.append("closing")
    questions = lines[:-1]
    if len(questions) > r["max"]:
        problems.append("too many")
    cats = []
    for q in questions:
        m = re.match(r"\d+\.\s*【(.+?)】(.+)$", q) or re.match(r"\d+\.\s*(.+?)（(背景|难点|影响|需求回报)）$", q)
        if not m:
            problems.append(f"format {q}")
            continue
        cat, body = (m.group(1), m.group(2)) if q.split(".", 1)[1].strip().startswith("【") else (m.group(2), m.group(1))
        cats.append(cat)
        if any(c in body for c in CLOSED) or body.rstrip("？?").endswith("吗"):
            problems.append(f"closed {q}")
        if r["single"] and (body.count("？") != 1 or any(w in body for w in ("和", "以及", "还有"))):
            problems.append(f"two in one {q}")
    if cats.count("背景") > r["background"] or cats.count("影响") < r["impact"] or cats.count("需求回报") < r["payoff"]:
        problems.append(f"mix {cats}")
    if r["order"] and cats != sorted(cats, key=ORDER.index):
        problems.append("order")
    return problems


def main() -> None:
    wrong = []
    for q in json.loads((HERE / "questions.json").read_text()):
        r = rules_of(q["files"]["工作规则.md"])
        lead = json.loads(q["files"]["线索.md"].split("```json")[1].split("```")[0])
        ref = q["reference"]
        mine = (r["max"], r["background"], r["impact"], r["payoff"] or "规则没要求", sorted(r["must"]))
        theirs = (ref["数量要求"]["题数上限"], ref["数量要求"]["背景类最多"], ref["数量要求"]["影响类至少"],
                  ref["数量要求"]["需求回报类至少"], sorted(m["事"].replace("、", "和") for m in ref["必问的事和它们的类别"]))
        listed = {k["信息"] for k in ref["已知信息（不能问，换了说法也算）"]}
        hidden_ok = known_of(lead) <= listed and len(listed) == len(lead["表单字段"]) + len(
            [n for n in lead["公开信息（公众号、官网）"] if "：" in n]) + lead["表单留言"].count("；")
        problems = audit(r, ref["一份照规则写的清单（措辞可以不同）"])
        if mine != theirs or not hidden_ok or problems:
            wrong.append((q["name"], mine, theirs, hidden_ok, problems))
    print("mismatches:", wrong or "none")
    assert not wrong


if __name__ == "__main__":
    main()
