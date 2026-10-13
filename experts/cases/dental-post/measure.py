"""评审用的测量值：员工交付的段名，以及推文那一段（段名里带“推文”）里的最后一行、“配图：”行、出现的配图文件名和审查证明
编号、还能找到的第 1 条和第 5 条词语、金额、价格句有没有逐字写出、出现的推广项目名和名册医生姓名。只作评审依据，判定由评审做。"""

import re


def cells(text: str, column: int) -> list[str]:
    lines = [line for line in text.splitlines() if line.startswith("|") and not line.startswith("|---")]
    return [line.strip().strip("|").split("|")[column].strip() for line in lines[1:]]


def measure(question: dict, product: str) -> dict:
    ref, files = question["reference"], question["files"]
    parts = re.split(r"^\s*##(?!#)\s*(.+?)\s*$", product, flags=re.M)
    sections = dict(zip(parts[1::2], parts[2::2]))
    found = {"交付里的段名（按顺序）": list(sections)}
    post = next((text for name, text in sections.items() if "推文" in name), None)
    if post is None:
        found["推文段"] = "没找到名字里带“推文”的段"
        return found
    lines = [line.strip() for line in post.strip().splitlines() if line.strip()]
    found["推文段最后一行"] = lines[-1] if lines else "（推文段是空的）"
    found["推文段里以“配图”开头的行"] = [line for line in lines if line.lstrip("*").startswith("配图")]
    found["推文段里出现的配图文件名"] = [f for f in cells(files["配图清单.md"], 0) if f in post]
    found["推文段里出现的审查证明编号"] = [n for n in cells(files["审查证明表.md"], 0) if n in post]
    found["推文段里还能找到的第 1 条词语"] = [w for w in ref["第 1 条的词（全表）"] if w in post]
    found["推文段里的金额"] = re.findall(r"\d[\d,.]*\s*元", post)
    found["推文段里还能找到的第 5 条词语"] = [w for w in ref["价格句"]["第 5 条不许出现的词（全表）"] if w in post]
    found["推文段里有没有逐字写出第 5 条的价格句"] = "有" if ref["价格句"]["该写（逐字）"] in post else "没有"
    found["推文段里出现的推广项目名"] = [p for p in ref["推广项目"] if p in post]
    found["推文段里出现的名册医生姓名"] = list(dict.fromkeys(n for n in cells(files["医生名册.md"], 0) if n in post))
    return found


if __name__ == "__main__":
    q = {"reference": {"第 1 条的词（全表）": ["终身", "100%"], "推广项目": ["种植牙"],
                       "价格句": {"该写（逐字）": "具体费用以面诊方案为准", "第 5 条不许出现的词（全表）": ["立减", "名额有限"]}},
         "files": {"配图清单.md": "| 文件名 | 标签 |\n|---|---|\n| 前台.jpg | 诊所环境 |\n| 术后.jpg |  |\n",
                   "医生名册.md": "| 姓名 | 科室 | 职称 |\n|---|---|---|\n| 李建国 | 种植科 | 副主任医师 |\n| 李建国 | 修复科 | 主任医师 |\n",
                   "审查证明表.md": "| 编号 | 覆盖项目 | 有效期 |\n|---|---|---|\n| A1 号 | 种植牙 | 2026-01-01 至 2026-12-31 |\n"}}
    got = measure(q, "## 改后推文\n种植牙终身质保。主诊医生：李建国 副主任医师。立减 300 元。\n配图：前台.jpg\n医疗广告审查证明编号：A1 号\n"
                     "## 修改说明\n| 原文 | 改成 | 依据第几条 |\n| 100% | 删除 | 第 1 条 |")
    assert got == {"交付里的段名（按顺序）": ["改后推文", "修改说明"], "推文段最后一行": "医疗广告审查证明编号：A1 号",
                   "推文段里以“配图”开头的行": ["配图：前台.jpg"], "推文段里出现的配图文件名": ["前台.jpg"],
                   "推文段里出现的审查证明编号": ["A1 号"], "推文段里还能找到的第 1 条词语": ["终身"],
                   "推文段里的金额": ["300 元"], "推文段里还能找到的第 5 条词语": ["立减"],
                   "推文段里有没有逐字写出第 5 条的价格句": "没有", "推文段里出现的推广项目名": ["种植牙"],
                   "推文段里出现的名册医生姓名": ["李建国"]}, got
    print("ok")
