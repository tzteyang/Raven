"""自检：另写一遍，只读员工看到的文件（工作规则.md、产品参数表.md、话题表.md）。从规则原文读口径（标题上限、正文区间、前几行
要原样写出哪几项、要不要写使用限制、禁用字词、导流词、话题上限和顺序、段名和合作标注），从参数表和话题表重算标题必带参数、
emoji 要求、要原样写出的文字、参数表里不能照抄的文字和必带话题，和参考答案比对；再用另一套写法量一遍示例，确认示例本身合规。

  python3 check.py
"""

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
LINES = ["帐篷", "帐篷配件", "睡袋", "炉具", "灯具", "背包"]


def table_rows(markdown: str) -> list[list[str]]:
    return [[cell.strip() for cell in line.strip().strip("|").split("|")]
            for line in markdown.splitlines() if line.startswith("|") and not line.startswith("|---")]


def quoted(text: str) -> list[str]:
    return re.findall(r"“(.+?)”", text)


def solve(files: dict) -> dict:
    rules, sheet, table = files["工作规则.md"], files["产品参数表.md"], files["话题表.md"]
    items = re.findall(r"^\d\. (.+)$", rules, re.M)
    item = lambda key: next(body for body in items if key in body)  # noqa: E731
    first, fields = re.search(r"正文前 (\d) 行里要原样写出参数表(.+?)的文字", rules).groups()
    ban = item("标题、正文、话题里都不出现")
    fmt = item("交付格式")
    info = dict(re.findall(r"^- (.+?)：(.*)$", sheet, re.M))
    params = [r for r in table_rows(sheet.split("## 参数")[1].split("## 其他")[0]) if r[0] != "参数"]
    other = {r[0]: r[1] for r in table_rows(sheet.split("## 其他")[1]) if r[0] != "项目"}
    row = [r for r in table_rows(table) if r[0] == info["产品线"]]
    assert len(row) == 1, info["产品线"]
    got = {
        "title_max": int(re.search(r"标题不超过 (\d+) 字", rules).group(1)),
        "body": [int(x) for x in re.search(r"正文 (\d+) 到 (\d+) 字", rules).groups()],
        "first": int(first),
        "needed": [info[f] for f in quoted(fields)],
        "caution": info["使用限制"] if "原样写出参数表“使用限制”" in rules else None,
        "banned": (["最"] if "都不出现“最”字" in ban else []) + quoted(re.search(r"这.个词：(.+?)。", ban).group(1)),
        "lead": quoted(re.search(r"也不出现这.个词：(.+?)（", item("不放外链")).group(1)),
        "tags_max": int(re.search(r"话题最多 (\d+) 个", rules).group(1)),
        "ordered": "先写这一行“品牌话题”" in rules,
        "sections": [name[3:] for name in quoted(re.search(r"段名是(.+?)：", fmt).group(1))],
        "label": re.search(r"“## (合作..)”下只写“(.+?)”", fmt).groups(),
        "must": [r[1] for r in params if r[2] == "是"],
        "emoji": info["标题 emoji"],
        "line": info["产品线"],
        "required": row[0][1].split() + row[0][2].split(),
        "name": info["产品"],
    }
    marks = lambda s: [w for w in got["banned"] + got["lead"] if w in s] + [u for u in ("http", "www", ".com", ".cn") if u in s.lower()]  # noqa: E731
    got["copy_traps"] = [where for where in ("卖点", "购买渠道") if marks(other[where])]
    return got


def size(text: str) -> int:
    """Count as the rules do, written differently: every visible character once, plus one more for each emoji."""
    visible = re.sub(r"\s", "", text)
    return len(visible) + sum(1 for c in visible if ord(c) > 0xFFFF or c in "⛺☕✨")


def audit(got: dict, text: str) -> list[str]:
    """Problems with an example note under the recomputed rules."""
    problems = []
    blocks = text.split("\n\n## ")
    blocks[0] = blocks[0].removeprefix("## ")
    names = [b.split("\n", 1)[0] for b in blocks]
    if names != got["sections"]:
        return [f"sections {names}"]
    part = {b.split("\n", 1)[0]: b.split("\n", 1)[1] for b in blocks}
    title, body, tags = part["标题"], part["正文"], part["话题"].split(" ")
    odd = set(re.sub(r"[\s\w.\-+℃×｜，！]", "", title)) - {"⛺", "☕", "✨"} - {c for c in title if ord(c) > 0xFFFF}
    if "\n" in title or odd:
        problems.append(f"title shape {odd}")
    if size(title) > got["title_max"]:
        problems.append(f"title size {size(title)}")
    problems += [f"title lacks {v}" for v in got["must"] if v not in title]
    icons = [c for c in title if ord(c) > 0xFFFF or c in "⛺☕✨"]
    if icons != ([] if got["emoji"] == "无" else [got["emoji"]]):
        problems.append(f"title emoji {icons}")
    lines = [line for line in body.split("\n") if line.strip()]
    if not got["body"][0] <= size(body) <= got["body"][1]:
        problems.append(f"body size {size(body)}")
    problems += [f"not in first lines: {v}" for v in got["needed"] if not any(v in line for line in lines[:got["first"]])]
    if got["caution"] and not any(got["caution"] in line for line in lines):
        problems.append("no caution")
    for piece in (title, body, part["话题"]):
        problems += [f"banned {w}" for w in got["banned"] + got["lead"] if w in piece]
        problems += [f"url {u}" for u in ("http", "www", ".com", ".cn") if u in piece.lower()]
    if "#" in title + body:
        problems.append("# outside topics")
    if len(tags) > got["tags_max"] or not all(t.startswith("#") and t.count("#") == 1 for t in tags):
        problems.append(f"tags {tags}")
    problems += [f"missing tag {t}" for t in got["required"] if t not in tags]
    if got["ordered"] and tags[:len(got["required"])] != got["required"]:
        problems.append(f"tag order {tags}")
    if part[got["label"][0]] != got["label"][1]:
        problems.append("label")
    return problems


def compare(got: dict, ref: dict) -> list[str]:
    """Where the reference differs from what the visible files say."""
    title, body, clean, tags, fmt = ref["标题"], ref["正文"], ref["禁用说法和导流"], ref["话题"], ref["交付格式"]
    traps = clean["参数表里带禁用字词、网址或导流词，不能照抄的文字"]
    looks = [line for line in LINES if line != got["line"] and line in got["name"]]
    pairs = [
        ("sections", fmt["段名和顺序"], [f"## {s}" for s in got["sections"]]),
        ("label", fmt["合作标注的写法"], got["label"][1]),
        ("title max", title["字数上限"], got["title_max"]),
        ("must", title["标题必带参数（照参数表“数值”一栏原样写）"], got["must"]),
        ("emoji", "写“无”" in title["emoji 要求"] if got["emoji"] == "无" else f"“{got['emoji']}”" in title["emoji 要求"], True),
        ("body", body["字数区间（含两端）"], got["body"]),
        ("first", body["前几行（空行不算）"], got["first"]),
        ("needed", body["前几行里要原样写出的文字"], got["needed"]),
        ("caution", body["正文里要原样写出的使用限制"] if got["caution"] else "不要求",
         got["caution"] or ("不要求" if body["正文里要原样写出的使用限制"].startswith("这套规则不要求") else "?")),
        ("banned", clean["禁用字词（是别的词的一部分也算）"], got["banned"]),
        ("lead", clean["导流词（是别的词的一部分也算）"], got["lead"]),
        ("traps", [] if traps == "无" else [t["位置"] for t in traps], got["copy_traps"]),
        ("line", tags["参数表的产品线"], got["line"]),
        ("required", tags["必带话题"], got["required"]),
        ("tags max", tags["个数上限"], got["tags_max"]),
        ("order", tags["顺序要求"].startswith("有"), got["ordered"]),
        ("name trap", tags["产品名里像别的产品线的字"] != "无", bool(looks)),
    ]
    return [f"{what}: reference {theirs!r} vs files {mine!r}" for what, theirs, mine in pairs if theirs != mine]


def mismatches(bank: list[dict]) -> list:
    wrong = []
    for q in bank:
        got, ref = solve(q["files"]), q["reference"]
        example = ref["一份照规则写的示例（措辞可以不同）"]
        problems = compare(got, ref) + audit(got, example)
        part = dict(b.split("\n", 1) for b in example.removeprefix("## ").split("\n\n## "))
        if size(part["标题"]) != ref["标题"]["示例标题字数"] or size(part["正文"]) != ref["正文"]["示例正文字数"]:
            problems.append("example sizes")
        if problems:
            wrong.append((q["name"], problems))
    return wrong


def main() -> None:
    wrong = mismatches(json.loads((HERE / "questions.json").read_text()))
    print("mismatches:", wrong or "none")
    assert not wrong


if __name__ == "__main__":
    main()
