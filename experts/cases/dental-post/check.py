"""自检：另写一遍算法，只读员工看到的文件（工作规则、配图清单、医生名册、审查证明表）和题面，重算推文里的第 1 条词语、
推广项目、每位医生该怎么写、能用的配图、每个推广项目该用的审查编号和最后一行、要删的项目、价格句和交付段落，和参考答案
逐题比对。

  python3 check.py
"""

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent


def rows(text: str) -> list[list[str]]:
    """Body rows of the one Markdown table in a file."""
    lines = [line for line in text.splitlines() if line.startswith("|") and not line.startswith("|---")]
    return [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines[1:]]


def main() -> None:
    wrong = []
    for q in json.loads((HERE / "questions.json").read_text()):
        rules, ref = q["files"]["工作规则.md"], q["reference"]
        item = {int(line[0]): line for line in rules.splitlines() if re.match(r"^\d\. ", line)}
        day = re.search(r"计划 (\d{4}-\d{2}-\d{2}) 发布", q["text"]).group(1)
        post = re.search(r"「(.+)」", q["text"], re.S).group(1)
        got, expected = {}, {}

        banned = re.findall(r"“([^”]+)”", item[1].split("：", 2)[2].split("。")[0])
        got["词"], expected["词"] = [w for w in banned if w in post], ref["原推文里出现的第 1 条词语"]

        certs = [{"number": n, "covered": c.split("、"), "start": v.split(" 至 ")[0], "end": v.split(" 至 ")[1]}
                 for n, c, v in rows(q["files"]["审查证明表.md"])]
        names = {p for c in certs for p in c["covered"]}
        projects = sorted((p for p in names if p in post), key=post.index)
        got["项目"], expected["项目"] = projects, ref["推广项目"]

        form = re.search(r"写成“([^”]+)”", item[2]).group(1)
        qualify = "美容主诊医师" in item[2]
        named = sorted((row for row in rows(q["files"]["医生名册.md"]) if row[1] + row[0] in post),
                       key=lambda row: post.index(row[1] + row[0]))
        got["医生"] = ["（整句删掉）" if qualify and row[3] == "否" else
                       form.replace("姓名", row[0]).replace("科室", row[1]).replace("职称", row[2]) for row in named]
        expected["医生"] = [d["该写"] for d in ref["医生"]]

        labels = re.findall(r"“([^”]+)”", re.search(r"标签是(.+?)的能用", item[3]).group(1))
        keys = re.findall(r"“([^”]+)”", re.search(r"文件名里有(.+?)的能用", item[3]).group(1))
        got["配图"] = [f for f, label in rows(q["files"]["配图清单.md"])
                       if (label in labels if label else any(k in f for k in keys))]
        expected["配图"] = next(v for k, v in ref["配图"].items() if k.startswith("能用的图"))

        template = re.search(r"最后一行写“([^”]+)”", item[4]).group(1)
        sep = re.search(r"用“([^”]+)”隔开", item[4]).group(1)
        drop = "没有有效证明" in item[4]
        picked, dropped = [], []
        for p in projects:
            good = [c for c in certs if p in c["covered"] and c["start"] <= day <= c["end"]]
            if len(good) == 1:
                picked.append(good[0])
            elif not good and drop:
                dropped.append(p)
            else:
                wrong.append((q["name"], p, "no unique certificate", good))
        head, each = template.split("：", 1)
        got["编号行"] = f"{head}：" + sep.join(each.replace("编号", c["number"]).replace("YYYY-MM-DD", c["end"]) for c in picked)
        expected["编号行"] = ref["审查编号"]["最后一行该写"]
        got["审查结论"] = ("删掉的项目：" + ("、".join(dropped) or "无")) if drop else None
        expected["审查结论"] = ref.get("## 审查结论该写")

        got["价格句"] = re.search(r"价格只写一句“([^”]+)”", item[5]).group(1)
        expected["价格句"] = ref["价格句"]["该写（逐字）"]
        got["段落"] = [f"## {s}" for s in dict.fromkeys(re.findall(r"“## ([^”]+)”", item[6]))]
        expected["段落"] = ref["交付格式"]["段落（按顺序）"]

        if got != expected:
            wrong.append((q["name"], {k: (got[k], expected[k]) for k in got if got[k] != expected[k]}))
    print("mismatches:", wrong or "none")
    assert not wrong


if __name__ == "__main__":
    main()
