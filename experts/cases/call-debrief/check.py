"""自检：另写一遍，只读员工看到的文件（工作规则.md、通话记录.md、竞品名单.md），从规则原文读优先级和日期写法，
按通话记录逐句认出每类问题、该报的改进点、销售答应客户的事、下一步日期，和参考答案比对。

  python3 check.py
"""

import calendar
import json
import re
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
DAYS = "一二三四五六日"


def problems(rules: str, call: list[str]) -> dict:
    seller = [i for i, line in enumerate(call) if line.startswith("销售：")]
    found = {"开场": not ("占用您" in call[seller[0]] and "分钟" in call[seller[0]])}
    pain = next(i for i, line in enumerate(call) if line.startswith("客户：") and ("一整天" in line or "复购" in line or "一个礼拜" in line))
    after_pain = call[pain + 1]
    if "需求确认" in re.search(r"^1\. .+$", rules, re.M).group(0):
        found["需求确认"] = not ("每个月" in after_pain and "多少" in after_pain)
    objection = next((i for i, line in enumerate(call) if line.startswith("客户：") and "贵了" in line), None)
    if objection is None:
        found["价格异议"] = False
    else:
        reply = call[objection + 1]
        standard = "预算" in reply if "预算范围" in re.search(r"^2\. .+$", rules, re.M).group(0) else ("对比的" in reply and "包含哪些功能" in reply)
        found["价格异议"] = not standard
    found["下一步承诺"] = not any(re.search(r"(下下周|下周|这周).|月底前", line) for line in call if line.startswith("客户："))
    return found


def when(call_day: date, call: list[str]) -> tuple[str, date] | None:
    for line in call:
        if not line.startswith("客户："):
            continue
        m = re.search(r"(下下周|下周|这周)(.)|月底前", line)
        if m:
            if m.group(0) == "月底前":
                return "月底前", date(call_day.year, call_day.month, calendar.monthrange(call_day.year, call_day.month)[1])
            shift = {"这周": 0, "下周": 7, "下下周": 14}[m.group(1)]
            start = call_day - timedelta(days=call_day.isoweekday() - 1)
            return m.group(0), start + timedelta(days=shift + DAYS.index(m.group(2)))
    return None


def main() -> None:
    wrong = []
    for q in json.loads((HERE / "questions.json").read_text()):
        files, ref = q["files"], q["reference"]
        rules = files["工作规则.md"]
        order = re.search(r"按手册优先级选：(.+?)。", rules).group(1).split(" → ")
        record = files["通话记录.md"]
        call_day = date.fromisoformat(re.search(r"通话日期：(\d{4}-\d\d-\d\d)", record).group(1))
        call = [line for line in record.split("## 通话内容")[1].splitlines() if line.startswith(("销售：", "客户："))]
        found = problems(rules, call)
        listed = [k for k in order if found.get(k)]
        promises = sum(1 for line in call if line.startswith("销售：") and ("折" in line or "off" in line or "就能上线" in line or "送您" in line))
        due = when(call_day, call)
        if due:
            day = due[1]
            said = day.isoformat() if "YYYY-MM-DD" in rules else f"{day.month} 月 {day.day} 日（周{DAYS[day.weekday()]}）"
        mine = (listed, listed[0], promises, said if due else None)
        theirs_next = ref["下一步"]["换算后的日期"] if isinstance(ref["下一步"], dict) else None
        theirs_promises = ref["销售答应客户的事（都要写进规则指定的那一段）"]
        theirs = (ref["通话里有的问题（按这次规则的优先级）"], ref["该报的改进点"],
                  len(theirs_promises) if isinstance(theirs_promises, list) else 0, theirs_next)
        competitors = [cell.strip() for line in files["竞品名单.md"].splitlines()[4:] for cell in line.strip("|").split("|")[:3:2]]
        example = ref["一份照规则写的示例（措辞可以不同）"]
        mail = example.split("## 跟进邮件")[1]
        leaks = [c for c in competitors if c in mail] + [w for w in ref["邮件里不能出现的写法（举例，换成别的写法也算）"] if w in mail]
        if mine != theirs or leaks or (due and said not in mail):
            wrong.append((q["name"], mine, theirs, leaks))
    print("mismatches:", wrong or "none")
    assert not wrong


if __name__ == "__main__":
    main()
