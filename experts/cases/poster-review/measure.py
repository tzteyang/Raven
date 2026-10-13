"""评审用的测量值：员工交付的段名，以及“文案”那一段里还能找到的极限词表词语和“原价”。只作评审依据，判定由评审做。"""

import re


def measure(question: dict, product: str) -> dict:
    words = [line.strip() for line in question["files"]["极限词表.md"].splitlines()[2:] if line.strip()]
    parts = re.split(r"^\s*##(?!#)\s*(.+?)\s*$", product, flags=re.M)
    sections = dict(zip(parts[1::2], parts[2::2]))
    copy = next((text for name, text in sections.items() if "文案" in name), None)
    found = {"交付里的段名（按顺序）": list(sections)}
    if copy is None:
        found["文案段"] = "没找到名字里带“文案”的段"
    else:
        found["文案段里还能找到的极限词表词语"] = sorted(w for w in words if w in copy)
        found["文案段里“原价”出现的次数"] = copy.count("原价")
    return found


if __name__ == "__main__":
    q = {"files": {"极限词表.md": "# 极限词表\n\n最低\n第一\n"}}
    got = measure(q, "## 改后文案\n年卡门市价 2460 元，全城最低。\n## 修改清单\n| 原文 | 改成 | 依据 |\n最低 原价")
    assert got == {"交付里的段名（按顺序）": ["改后文案", "修改清单"], "文案段里还能找到的极限词表词语": ["最低"],
                   "文案段里“原价”出现的次数": 0}, got
    print("ok")
