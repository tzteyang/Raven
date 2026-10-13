"""评审用的测量值：全文字数（空格和换行不算）、每行引的原话和编号对不对得上（是不是那条评价的全部内容、那条几星、哪天、
里面出现了分类表的哪些词）。只作评审依据，判定由评审做。"""

import re

QUOTE = re.compile(r"[「“\"](.+?)[」”\"]")


def table(markdown: str) -> list[list[str]]:
    lines = [line for line in markdown.splitlines() if line.startswith("|") and not line.startswith("|---")]
    return [[cell.strip() for cell in line.strip("|").split("|")] for line in lines[1:]]


def measure(question: dict, product: str) -> dict:
    files = question["files"]
    reviews = {row[0]: {"类型": row[2], "星级": int(row[3]), "日期": row[4], "评价": row[5]} for row in table(files["本周评价.md"])}
    words = [(name, word) for name, keys, phrases, _ in table(files["问题分类表.md"])
             for word in keys.split("、") + phrases.split("、")]
    quoted = []
    for line in product.splitlines():
        found = QUOTE.findall(line)
        numbers = re.findall(r"#\d+", line)
        if not found and not numbers:
            continue
        text = max(found, key=len) if found else ""
        row = {"这一行": line.strip(), "引的原话": text, "写的编号": numbers}
        for number in numbers:
            review = reviews.get(number)
            if review is None:
                row[number] = "本周评价里没有这个编号"
                continue
            row[number] = {
                **review,
                "原话和这条评价的全部内容一字不差": text == review["评价"],
                "原话是这条评价的一部分": bool(text) and text in review["评价"],
                "这条评价里出现的分类表用词": [f"{word}（{name}）" for name, word in words if word in review["评价"]],
            }
        if text:
            row["一字不差是哪几条评价的全部内容"] = [n for n, r in reviews.items() if r["评价"] == text]
        quoted.append(row)
    return {
        "全文字数（字符都算，空格和换行不算）": len(re.sub(r"\s", "", product)),
        "这套规则的字数上限": question["reference"]["字数上限"],
        "各行引的原话核对": quoted,
    }


if __name__ == "__main__":
    q = {"files": {
        "本周评价.md": "| 编号 | 用户 ID | 类型 | 星级 | 日期 | 评价 |\n|---|---|---|---|---|---|\n"
                     "| #1 | U1 | 首评 | 1 | 2026-09-21 | 掉电太快。 |\n| #2 | U2 | 首评 | 5 | 2026-09-21 | 降噪效果惊艳。 |\n",
        "问题分类表.md": "| 类别 | 关键词 | 典型说法 | 转给 |\n|---|---|---|---|\n| 续航 | 掉电、充电 | 撑不了半天 | 硬件团队 |\n"},
        "reference": {"字数上限": 150}}
    got = measure(q, "续航 1 条（100%）：「掉电太快。」（#1）→ 硬件团队\n续航：「掉电太快」（#2）")
    first, second = got["各行引的原话核对"]
    assert first["#1"]["原话和这条评价的全部内容一字不差"] and first["#1"]["星级"] == 1, first
    assert not second["#2"]["原话是这条评价的一部分"] and second["一字不差是哪几条评价的全部内容"] == [], second
    assert got["全文字数（字符都算，空格和换行不算）"] == 40, got
    print("ok")
