"""评审用的测量值：员工交付里以“## ”开头的段名，按出现顺序。只作评审依据，判定由评审做。"""

import re


def measure(question: dict, product: str) -> dict:
    return {"交付里的段名（按顺序）": re.findall(r"^\s*##(?!#)\s*(.+?)\s*$", product, re.M)}


if __name__ == "__main__":
    got = measure({}, "## 投诉分析\n内容\n## 回复草稿\n### 小标题\n## CRM 更新\n")
    assert got == {"交付里的段名（按顺序）": ["投诉分析", "回复草稿", "CRM 更新"]}, got
    print("ok")
