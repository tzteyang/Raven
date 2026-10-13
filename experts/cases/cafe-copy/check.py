"""自检：另写一遍，只读员工看到的文件（工作规则.md、杯测表.md、风味词总表.md），从规则原文读口径，重算每题的风味栏、
冲煮建议原句、字数区间、句数上限、禁用词和事实，和参考答案比对；再用正则独立量一遍示例，确认示例本身合规。

  python3 check.py
"""

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent


def cells(markdown: str) -> dict:
    out = {}
    for line in markdown.splitlines():
        parts = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.startswith("|") and len(parts) >= 2 and not parts[0].startswith("---"):
            out.setdefault(parts[0], parts[1:])
    return out


def solve(files: dict) -> dict:
    rules, sheet = files["工作规则.md"], cells(files["杯测表.md"])
    wheel = [w for row in cells(files["风味词总表.md"]).values() for w in row[0].split("、")]
    flavors = sheet["风味"][0].split("、")
    low, high = map(int, re.search(r"全文 (\d+) 到 (\d+) 字", rules).groups())
    most = int(re.search(r"每段不超过 (\d) 句", rules).group(1))
    banned = re.findall(r"“(.+?)”", re.search(r"^2\. 不用(.+?)这五个词", rules, re.M).group(1))
    me = re.search(r"自称用“(.+?)”", rules).group(1)
    ratio, temp, grind = sheet["手冲"][0].split(":")[1], sheet["手冲"][1].rstrip("°C"), sheet["手冲"][2]
    if "冲煮建议（冷萃）" in rules:
        light = sheet["烘焙度"][0] in ("浅烘", "中浅烘")
        brew = (f"冲煮建议（手冲）：粉水比 1:{ratio}，水温 {temp}°C。" if light else
                f"冲煮建议（冷萃）：粉水比 1:{sheet['冷萃'][0].split(':')[1]}，冷藏浸泡 {sheet['冷萃'][3].split()[0]} 小时。")
    elif "研磨度 Z" in rules:
        brew = f"粉水比 1:{ratio} ／ 水温 {temp}°C ／ 研磨度 {grind}"
    else:
        brew = f"冲煮建议：粉水比 1:{ratio}，水温 {temp}°C。"
    return {"flavors": flavors, "range": (low, high), "most": most, "banned": banned, "self": me, "brew": brew,
            "wheel": wheel, "cover": "全部写到" in rules, "no_suffix": "后面不能紧跟" in rules,
            "facts": [sheet["产地"][0], sheet["处理法"][0], sheet["海拔"][0], sheet["烘焙度"][0]],
            "numbers": set(re.findall(r"\d+", files["杯测表.md"]))}


def audit(got: dict, text: str) -> list[str]:
    """Problems with a text under the recomputed rules: an independent measure of the reference's example."""
    problems = []
    size = len(re.sub(r"\s", "", text))
    if not got["range"][0] <= size <= got["range"][1]:
        problems.append(f"size {size}")
    for line in filter(str.strip, text.splitlines()):
        if len(re.findall(r"[^。！？]+[。！？]?", line.strip())) > got["most"]:
            problems.append(f"sentences in {line}")
    pattern = "|".join(sorted(map(re.escape, got["wheel"]), key=len, reverse=True))
    used = [(m.group(), text[m.end():m.end() + 1]) for m in re.finditer(pattern, text)]
    problems += [f"outside {w}" for w, _ in used if w not in got["flavors"]]
    if got["no_suffix"]:
        problems += [f"suffix {w}{after}" for w, after in used if after in "香味调感" and after]
    if got["cover"]:
        problems += [f"missing {f}" for f in got["flavors"] if f not in {w for w, _ in used}]
    problems += [f"banned {b}" for b in got["banned"] if b in text]
    if got["self"] not in text:
        problems.append("no self")
    if text.strip().splitlines()[-1].strip() != got["brew"]:
        problems.append("brew line")
    problems += [f"number {n}" for n in set(re.findall(r"\d+", text)) - got["numbers"]]
    return problems


def main() -> None:
    wrong = []
    for q in json.loads((HERE / "questions.json").read_text()):
        got, ref = solve(q["files"]), q["reference"]
        mine = (got["flavors"], got["brew"], f"{got['range'][0]} 到 {got['range'][1]}", got["most"], got["banned"],
                list(ref["事实"].values()) == got["facts"])
        theirs = (ref["风味栏的词（只能写这些）"], ref["冲煮建议"]["该写成"], ref["字数区间"], ref["每段句数上限"], ref["禁用词"], True)
        problems = audit(got, ref["一份照规则写的示例（措辞可以不同）"])
        if mine != theirs or problems:
            wrong.append((q["name"], mine, theirs, problems))
    print("mismatches:", wrong or "none")
    assert not wrong


if __name__ == "__main__":
    main()
