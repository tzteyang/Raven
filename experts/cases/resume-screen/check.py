"""自检：另写一遍，只读员工看到的文件（工作规则.md、岗位硬性条件.md、简历.md）和题面的出题日期，从规则原文读口径
（兼职怎么算、下级班组算不算、5 年窗口、结论说法），重算相关年限、带团队人数、系统和结论，和参考答案比对；再核对示例里的结论、
数和追问个数，引用简历原话的要一字不差。

  python3 check.py
"""

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent


def month_index(text: str) -> int:
    y, m = map(int, text.split("."))
    return y * 12 + m - 1


def solve(files: dict, today: str) -> dict:
    rules, req, resume = files["工作规则.md"], files["岗位硬性条件.md"], files["简历.md"]
    years_need = int(re.search(r"相关年限 \| (\d+) 年以上", req).group(1))
    team_need = int(re.search(r"带团队人数 \| (\d+) 人以上", req).group(1))
    system = re.search(r"系统 \| 熟练使用 (\S+) \|", req).group(1)
    keywords = re.search(r"相关职位关键词 \| (.+?) \|", req).group(1).split("、")
    half = "兼职的经历按一半月数算" in rules
    only_direct = "只算本人的直接下属" in rules
    window = 60 if "出题日前 5 年内" in rules else None
    passed, failed = re.search(r"结论只写“(.+?)”或“(.+?)”", rules).groups()
    now = int(today[:4]) * 12 + int(today[5:7]) - 1
    full, part, team, used = set(), set(), 0, False
    for line in resume.splitlines():
        m = re.match(r"- (\d{4}\.\d\d) — (\d{4}\.\d\d|至今)：(.+)$", line)
        if not m:
            continue
        start = month_index(m.group(1))
        end = now if m.group(2) == "至今" else month_index(m.group(2))
        body = m.group(3)
        title = body.split("，")[1]
        is_part = "（兼职）" in title
        span = set(range(start, end + 1))
        if window:
            span &= set(range(now - window + 1, now + 1))
        if any(k in title for k in keywords):
            (part if is_part else full).update(span)
        if system in body:
            used = True
        levels = re.search(r"直接带 (\d+) 名班组长，下面 \d+ 个班组另有 (\d+) 名组员", body)
        plain = re.search(r"(?<!管理 )带 (\d+)(?: 到 \d+)? 人", body)
        if levels:
            team = max(team, int(levels.group(1)) + (0 if only_direct else int(levels.group(2))))
        elif plain and "协助" not in body.split("，")[2]:
            team = max(team, int(plain.group(1)))
    months = len(full) + (len(part - full) / 2 if half else 0)
    years = months / 12
    ok = years >= years_need and team >= team_need and used
    return {"years": years, "team": team, "used": used, "verdict": passed if ok else failed,
            "questions": int(re.search(r"给 (\d) 个面试追问", rules).group(1)), "quote": "先引用简历里的一段原文" in rules}


def main() -> None:
    wrong = []
    for q in json.loads((HERE / "questions.json").read_text()):
        today = re.search(r"今天是 (\d{4}-\d\d-\d\d)", q["text"]).group(1)
        got = solve(q["files"], today)
        ref = q["reference"]
        ref_years = float(ref["相关年限"].split(" 年")[0])
        ref_team = int(ref["带团队人数"].split(" 人")[0])
        example = ref["一份照规则写的示例（措辞可以不同）"]
        problems = []
        if got["verdict"] != ref["结论"] or abs(got["years"] - ref_years) > 1e-3 or got["team"] != ref_team:
            problems.append(("numbers", got, ref_years, ref_team, ref["结论"]))
        if f"结论：{got['verdict']}" not in example or f"{got['years']:.1f} 年" not in example or f"{got['team']} 人" not in example:
            problems.append("example numbers")
        asks = re.findall(r"^(?:\d\. |（\d）)(.+)$", example, re.M)
        if len(asks) != got["questions"]:
            problems.append(("asks", len(asks)))
        if got["quote"]:
            for ask in asks:
                quote = re.match(r"“(.+?)”", ask)
                if not quote or quote.group(1) not in q["files"]["简历.md"]:
                    problems.append(("quote", ask))
        for k, v in (line.split("：", 1) for line in ref["简历里的敏感信息（交付里不能出现）"]):
            if v in example:
                problems.append(("sensitive", v))
        if problems:
            wrong.append((q["name"], problems))
    print("mismatches:", wrong or "none")
    assert not wrong


if __name__ == "__main__":
    main()
