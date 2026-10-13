"""独立核对材料：只由员工能看到的规则、事实 CSV、原简历和 JD 重建参考依据。

不导入 make.py，不用生成器的数值转换；另外核对测量器与 40 份可行答卷。
此处检查的是出题材料，不给 Raven 答卷评分；正式判卷全部由模型做。
"""

import copy
import csv
import io
import json
import re
from collections import Counter
from decimal import Decimal
from pathlib import Path

from measure import measure, numbers, selftest

HERE = Path(__file__).resolve().parent


def read_number(text):
    """独立的中文位权解析，不复用 make/measure 的函数。"""
    text = text.strip().replace(",", "").replace("两", "二")
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        return Decimal(text)
    if "万" in text:
        high, low = text.split("万", 1)
        return read_number(high) * 10000 + (read_number(low) if low else Decimal(0))
    if "点" in text:
        high, low = text.split("点", 1)
        digits = "零一二三四五六七八九"
        return read_number(high) + Decimal("0." + "".join(str(digits.index(c)) for c in low))
    digits = "零一二三四五六七八九"
    # 每个大单位从左至右拆；一千零二十 -> 一千 + 零二十。
    for unit, value in (("千", 1000), ("百", 100), ("十", 10)):
        if unit in text:
            high, low = text.split(unit, 1)
            high = high.lstrip("零")
            low = low.lstrip("零")
            return (read_number(high) if high else Decimal(1)) * value + (read_number(low) if low else Decimal(0))
    return Decimal(digits.index(text))


def canonical(value):
    return format(value, "f").rstrip("0").rstrip(".") if "." in format(value, "f") else str(value)


def read_results(text):
    result = []
    for part in text.removesuffix("。").split("；"):
        label, raw = part.split("：", 1)
        number = raw
        qualifier = ""
        if raw.startswith("百分之"):
            unit, number = "%", raw[3:]
        else:
            unit = re.search(r"[%人次篇条套]$", raw).group(0)
            number = raw[:-1]
        if number.startswith("约"):
            qualifier, number = "约", number[1:]
        elif number.endswith("余"):
            qualifier, number = "余", number[:-1]
        pieces = number.split("至")
        if len(pieces) == 2:
            qualifier = "区间"
        result.append({"指标": label, "数值": [canonical(read_number(p)) for p in pieces], "单位": unit,
                       "限定": qualifier, "事实表写法": raw})
    return result


def audit(q, inspect_example=True):
    files, ref = q["files"], q["reference"]
    facts = list(csv.DictReader(io.StringIO(files["事实表.csv"])))
    originals = dict(re.findall(r"^(E[1-5])：(.+)$", files["原简历.md"], re.M))
    jd = [s[2:] for s in files["目标岗位.md"].splitlines() if s.startswith("- ")]
    usable = [f for f in facts if f["状态"] == "已确认"]
    all_actions = "\n".join(f["本人动作"] for f in usable)
    supported = sorted(word for word in jd if word in all_actions)
    absent = sorted(word for word in jd if word not in all_actions)
    by_item = {f["条目"]: f for f in usable}
    expected = []
    for item, original in originals.items():
        if item not in by_item:
            return ["missing confirmed fact for " + item]
        fact = by_item[item]
        expected.append({"条目": item, "原句": original, "所在经历": fact["所在经历"], "项目": fact["项目"],
                         "本人动作": fact["本人动作"], "保留的结果": read_results(fact["结果事实"]),
                         "事实出处": [fact["事实编号"]], "归属补充": fact["补充说明"]})
    errors = []
    if expected != ref["逐条依据"]:
        errors.append("facts or original differ")
    if supported != ref["应使用的关键词"] or absent != ref["不得进入改写的关键词"]:
        errors.append("keywords differ")
    if [f["事实编号"] for f in facts if f["状态"] != "已确认"] != ref["待核实不用的事实"]:
        errors.append("pending sources differ")
    team = next(m["数值"][0] for e in expected for m in e["保留的结果"] if m["指标"] == "排期小组人数")
    phrase = re.search(r"固定写“(.+?)”", files["工作规则.md"]).group(1).replace("N", team)
    if phrase != ref["职责固定说法"]:
        errors.append("team phrase differs")
    # 不仅比较示例，还逐一对照两个独立算法对每个原始数的解读。
    for e in expected:
        for m in e["保留的结果"]:
            got = [n["归一数值"] for n in numbers(m["事实表写法"])]
            if got != m["数值"]:
                errors.append(("measurement", m["事实表写法"], got, m["数值"]))
    if not inspect_example:
        return errors
    product = ref["一种合规交付"]
    measured = measure(q, product)
    heading = re.search(r"以“## (.+?)”开头", files["工作规则.md"]).group(1)
    columns = re.search(r"表头依次为“(.+?)”", files["工作规则.md"]).group(1).split("｜")
    limit = int(re.search(r"最多 (\d+) 条改写", files["工作规则.md"]).group(1))
    if measured["段名（按顺序）"] != [heading] or measured["表头列表"] != [columns] or measured["数据行数"] > limit:
        errors.append("example format")
    if measured["表格外的文字（只供格式项判断）"]:
        errors.append("example wrapper")
    if [row.get("条目") for row in measured["逐行测量"]] != list(originals):
        errors.append("example item sequence")
    for row, e in zip(measured["逐行测量"], expected):
        if row["原句列"] != e["原句"]:
            errors.append("example before differs")
        if row["出现的拔高词"]:
            errors.append("example inflated role")
        source_nums = numbers(by_item[e["条目"]]["结果事实"])
        count = lambda seq: Counter((v["归一数值"], v["单位"]) for v in seq)
        if count(row["改写里的数字"]) != count(source_nums):
            errors.append(("example numeric inventory", e["条目"], row["改写里的数字"], source_nums))
        if "事实出处" in columns and row["来源编号"] != e["事实出处"]:
            errors.append("example sources")
    used = measured["改写列关键词出现次数"]
    if any(used[w] < 1 for w in supported) or any(used[w] for w in absent):
        errors.append("example keywords")
    # 说明文字不混进任何改写统计；真实标点也不能破坏分句。
    wrapped = measure(q, "以下是建议：999人、SEO、主导。\n" + product + "\n补充：增长999%。")
    if wrapped["改写列关键词出现次数"] != measured["改写列关键词出现次数"]:
        errors.append("wrapper leaked into keywords")
    for a, b in zip(wrapped["逐行测量"], measured["逐行测量"]):
        if a["改写里的数字"] != b["改写里的数字"] or a["句数"] != b["句数"]:
            errors.append("wrapper leaked into row measurements")
    return errors


def main():
    selftest()
    bank = json.loads((HERE / "questions.json").read_text())
    scripts = json.loads((HERE / "scripts.json").read_text())
    wrong = [(q["name"], errors) for q in bank if (errors := audit(q))]
    assert len(bank) == 40 and len(scripts) == 40
    for q, s in zip(bank, scripts):
        n, prefix = int(q["name"][1:]), q["name"][0]
        assert q["group"] == {"t": "train", "x": "same", "y": "new"}[prefix]
        assert q["rules"] == ("R3" if prefix == "y" else ("R1" if n % 2 else "R2"))
        assert q["segment"] == ("common" if n <= (10 if prefix == "t" else 5) else "edge")
        assert s["name"] == q["name"] and s["exam"] == (prefix != "t")
        assert s["steps"] == [{"text": q["text"], "files": q["files"]}]
        assert q["files"]["工作规则.md"] == (HERE / "rules" / f"{q['rules']}.md").read_text()
        assert all(word not in (q["text"] + "\n".join(q["files"].values())) for word in ("WorkBuddy", "安装包", "公司规则"))
    print("mismatches:", wrong or "none")
    assert not wrong
    caught = 0
    for original in (bank[10], bank[11], bank[35], bank[36]):
        for kind in range(6):
            q = copy.deepcopy(original)
            if kind == 0:
                q["reference"]["逐条依据"][0]["保留的结果"][0]["数值"] = ["999999"]
            elif kind == 1:
                q["reference"]["逐条依据"][1]["原句"] += "伪造"
            elif kind == 2:
                q["reference"]["逐条依据"][2]["事实出处"] = ["F99"]
            elif kind == 3:
                q["reference"]["应使用的关键词"].append(q["reference"]["不得进入改写的关键词"][0])
            elif kind == 4:
                q["reference"]["职责固定说法"] = "带领团队"
            else:
                q["reference"]["逐条依据"][4]["本人动作"] = "独立主导全部活动"
            assert audit(q, inspect_example=False), (original["name"], kind)
            caught += 1
    print(f"independent audit mutations caught: {caught}/24")
    print("40 references, 40 example numeric inventories, split counts and 40 wrapper isolation checks: ok")


if __name__ == "__main__":
    main()
