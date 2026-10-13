"""评审用的测量值：周报字数（字符都算，空格和换行不算）、段名、第一行、出现的禁用词。只作评审依据，判定由评审做。"""

import re


def measure(question: dict, product: str) -> dict:
    rules = question["files"]["工作规则.md"]
    banned = re.findall(r"“(.+?)”", re.search(r"^4\. 不用(.+?)这", rules, re.M).group(1))
    lines = [line.strip() for line in product.splitlines() if line.strip()]
    return {
        "全文字数（字符都算，空格和换行不算）": len(re.sub(r"\s", "", product)),
        "这套规则的字数上限": question["reference"]["字数上限"],
        "交付里的段名（按顺序）": re.findall(r"^\s*##(?!#)\s*(.+?)\s*$", product, re.M),
        "第一行": lines[0] if lines else "",
        "出现的禁用词": [word for word in banned if word in product],
    }


if __name__ == "__main__":
    q = {"files": {"工作规则.md": "4. 不用“赋能”“抓手”这两个词。\n"}, "reference": {"字数上限": 300}}
    got = measure(q, "本周不错。\n## 本周结果\n新客 1 人 赋能")
    assert got["全文字数（字符都算，空格和换行不算）"] == 17 and got["出现的禁用词"] == ["赋能"], got
    print("ok")
