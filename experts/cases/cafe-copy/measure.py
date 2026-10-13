"""评审用的测量值：全文字数、每段（一行）句数、最后一行、自称和禁用词出现次数、风味词总表里的词逐个出现情况（按最长词认，
带后面紧跟的那个字，以及在不在这一批风味栏里）、文中的阿拉伯数字在不在杯测表里。只作评审依据，判定由评审做。"""

import re


def sentences(text: str) -> int:
    """Sentences end with 。！？; a piece with no letter or character, such as a closing quote, is not one."""
    return len([piece for piece in re.split(r"(?<=[。！？])", text) if re.search(r"\w", piece)])


def measure(question: dict, product: str) -> dict:
    files = question["files"]
    rules = files["工作规则.md"]
    wheel = sorted({w for line in files["风味词总表.md"].splitlines()[4:] for w in line.strip("|").split("|")[1].strip().split("、")},
                   key=len, reverse=True)
    column = re.search(r"\| 风味 \| (.+?) \|", files["杯测表.md"]).group(1).split("、")
    words, i = [], 0
    while i < len(product):
        hit = next((w for w in wheel if product.startswith(w, i)), None)
        if hit:
            words.append({"词": hit, "后面紧跟的字": product[i + len(hit):i + len(hit) + 1], "在这一批风味栏里": hit in column,
                          "上下文": product[max(0, i - 6):i + len(hit) + 6]})
            i += len(hit)
        else:
            i += 1
    lines = [line.strip() for line in product.splitlines() if line.strip()]
    selves = re.findall(r"“(.+?)”", re.search(r"^1\. (.+)$", rules, re.M).group(1))
    banned = re.findall(r"“(.+?)”", re.search(r"^2\. 不用(.+?)这五个词", rules, re.M).group(1))
    numbers = re.findall(r"\d+", product)
    sheet_numbers = set(re.findall(r"\d+", files["杯测表.md"]))
    return {
        "全文字数（字符都算，空格和换行不算）": len(re.sub(r"\s", "", product)),
        "每段句数（一行算一段）": [sentences(line) for line in lines],
        "逐行（字数、句数、这一行里的阿拉伯数字）": [
            {"行": line[:40] + ("…" if len(line) > 40 else ""), "字数": len(re.sub(r"\s", "", line)),
             "句数": sentences(line), "数字": re.findall(r"\d+", line)} for line in lines],
        "第一行": lines[0] if lines else "",
        "最后一行": lines[-1] if lines else "",
        "规则里出现的自称写法各出现几次": {s: product.count(s) for s in selves},
        "出现的禁用词": [b for b in banned if b in product],
        "风味词总表里的词（按出现顺序）": words,
        "风味栏的词各出现几次（按最长词认）": {c: sum(1 for w in words if w["词"] == c) for c in column},
        "文中的阿拉伯数字和杯测表里有没有": [f"{n}（{'有' if n in sheet_numbers else '没有'}）" for n in numbers],
    }


if __name__ == "__main__":
    q = {"files": {
        "工作规则.md": "1. 自称用“我们”，全文至少用一次；不用“本品牌”。\n2. 不用“极致”“匠心”“顶级”“赋能”“甄选”这五个词。\n",
        "杯测表.md": "| 海拔 | 1600 米 |\n| 风味 | 茉莉、蜜桃 |\n| 手冲 | 1:15 | 92°C | 中细 | — |\n",
        "风味词总表.md": "# 风味词总表\n\n| 类别 | 风味词 |\n|---|---|\n| 花香 | 茉莉、茉莉花 |\n| 桃杏 | 蜜桃、水蜜桃 |\n"}}
    got = measure(q, "我们的豆子有茉莉花香和水蜜桃，极致。\n冲煮建议：粉水比 1:15，水温 92°C，评分 88。")
    assert [w["词"] for w in got["风味词总表里的词（按出现顺序）"]] == ["茉莉花", "水蜜桃"], got
    assert got["风味栏的词各出现几次（按最长词认）"] == {"茉莉": 0, "蜜桃": 0} and got["出现的禁用词"] == ["极致"], got
    assert got["文中的阿拉伯数字和杯测表里有没有"][-1] == "88（没有）" and got["每段句数（一行算一段）"] == [1, 1], got
    assert sentences("我们叫它“春天的第一口。”放凉后更甜。") == 2
    print("ok")
