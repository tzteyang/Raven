"""Independently recompute the key from employee-visible rules and CSV files.

No generator imports; exact rational arithmetic deliberately differs from the
generator's Decimal arithmetic. Also verify every reference example is feasible.
"""

import copy
import csv
import io
import json
import re
from fractions import Fraction
from pathlib import Path

from measure import content, measure, self_test

HERE = Path(__file__).resolve().parent


def rows(text):
    return list(csv.DictReader(io.StringIO(text)))


def plain(number):
    value = Fraction(number)
    return str(value.numerator) if value.denominator == 1 else f"{float(value):.6f}".rstrip("0").rstrip(".")


def fixed(number, places):
    value = Fraction(number) * 10 ** places
    integer = value.numerator // value.denominator
    if value - integer >= Fraction(1, 2):
        integer += 1
    integer_text = str(integer).zfill(places + 1)
    return integer_text[:-places] + "." + integer_text[-places:]


def quantity(text):
    number, unit = text.rsplit(" ", 1)
    return Fraction(number), unit


def independent(q):
    files, rule = q["files"], q["files"]["工作规则.md"]
    source = {r["字段"]: r["值"] for r in rows(files["参数表.csv"])}
    factors = {r["关系"]: Fraction(r["数值"]) for r in rows(files["单位换算.csv"])}
    spelling = {r["英式"]: r["美式"] for r in rows(files["美英拼写.csv"])}
    cap_unit = re.search(r"容量一律写 (\w+) 和 cups", rule).group(1)
    size_unit = re.search(r"三边尺寸一律写 (\w+) 和 inches", rule).group(1)
    mass_unit = re.search(r"净重一律写 (\w+) 和 lb", rule).group(1)
    places = int(re.search(r"保留 (\d+) 位小数", rule).group(1))
    title_max = int(re.search(r"标题：不超过 (\d+) 个字符", rule).group(1))
    bullet_max = int(re.search(r"每条不超过 (\d+) 个字符", rule).group(1))
    section_names = re.findall(r"^## (.+)$", rule, re.M)
    separator = re.search(r"紧跟“(.*?)”再写正文", rule).group(1)
    banned = re.search(r"下面这些写法：(.+?)。列表是闭合", rule).group(1).split("、")
    amount, unit = quantity(source["容量"])
    ml = amount * factors["1 L 的 mL 数"] if unit == "L" else amount
    metric_cap = ml / factors["1 L 的 mL 数"] if cap_unit == "L" else ml
    facts = {"品牌": source["品牌"], "SKU": source["目标 SKU"], "容量": plain(metric_cap) + " " + cap_unit,
             "粒径": source["适用干粮粒径"], "每日最多餐数": int(source["每日最多餐数"]), "录音秒数": int(source["录音秒数"]),
             "颜色": spelling.get(source["颜色"], source["颜色"]), "供电": source["供电方式"], "机身尺寸": None, "净重": None}
    imperial = {"容量": fixed(ml / factors["1 cup 的 mL 数"], places) + " cups", "机身尺寸": None, "净重": None}
    if "机身尺寸（长 x 宽 x 高）" in source:
        lengths, unit = source["机身尺寸（长 x 宽 x 高）"].rsplit(" ", 1)
        cm = [Fraction(v) / factors["1 cm 的 mm 数"] if unit == "mm" else Fraction(v) for v in lengths.split(" x ")]
        facts["机身尺寸"] = " x ".join(plain(v * factors["1 cm 的 mm 数"] if size_unit == "mm" else v) for v in cm) + " " + size_unit
        imperial["机身尺寸"] = " x ".join(fixed(v / factors["1 inch 的 cm 数"], places) for v in cm) + " inches"
        weight, unit = quantity(source["净重"])
        kg = weight / factors["1 kg 的 g 数"] if unit == "g" else weight
        facts["净重"] = plain(kg * factors["1 kg 的 g 数"] if mass_unit == "g" else kg) + " " + mass_unit
        imperial["净重"] = fixed(kg / factors["1 lb 的 kg 数"], places) + " lb"
    canonical = {alias.lower(): row["项目"] for row in rows(files["认证写法.csv"]) for alias in row["常见别名（分号隔开）"].split(";")}
    allowed = set()
    for row in rows(files["认证记录.csv"]):
        if row["SKU"] != source["目标 SKU"] or row["状态"] != "已取得":
            continue
        if "认证记录还要在有效期内" in rule and (not row["有效至"] or row["有效至"] < source["上架日期"]):
            continue
        allowed.add(canonical[row["认证名称"].lower()])
    cert_rows = rows(files["认证写法.csv"])
    phrases = [row["准许成句"] for row in cert_rows if row["项目"] in allowed]
    forbidden = [row["项目"] for row in cert_rows if row["项目"] not in allowed]
    restriction = source["使用限制"] if "使用限制’必须原样写在第一条" in rule else "不适用"
    return dict(facts=facts, imperial=imperial, places=places, title_max=title_max, bullet_max=bullet_max,
                allowed=[row["项目"] for row in cert_rows if row["项目"] in allowed], phrases=phrases, forbidden=forbidden,
                restriction=restriction, spelling=spelling, section_names=section_names, separator=separator,
                banned=banned, required_title=[source["品牌"], source["目标 SKU"], "Automatic Pet Feeder"],
                absent_features=[key for key, value in source.items() if value == "无"])


def errors(q):
    ref, got = q["reference"], independent(q)
    pairs = [("facts", ref["商品事实"], got["facts"]), ("units", ref["美制换算"], got["imperial"]),
             ("places", ref["美制小数位"], got["places"]), ("title_max", ref["标题"]["上限"], got["title_max"]),
             ("bullet_max", ref["格式"]["每条上限"], got["bullet_max"]),
             ("allowed", ref["认证"]["允许项目"], got["allowed"]), ("phrases", ref["认证"]["必须原样写的成句"], got["phrases"]),
             ("forbidden", ref["认证"]["不能提及的项目"], got["forbidden"]),
             ("restriction", ref["第一条要点必须原样引用"], got["restriction"]), ("spelling", ref["拼写"], got["spelling"]),
             ("sections", ref["格式"]["段名"], got["section_names"]), ("separator", ref["格式"]["大写开头分隔符"], got["separator"]),
             ("bans", ref["禁用写法"], got["banned"]), ("title words", ref["标题"]["必含一次"], got["required_title"]),
             ("title start", ref["标题"]["开头"], got["facts"]["品牌"]), ("features", ref["不得写的功能"], got["absent_features"])]
    return [(key, a, b) for key, a, b in pairs if a != b]


def check_example(q):
    ref = q["reference"]
    observed = measure(q, ref["示例交付"])
    _, _, title, bullets, extra = content(q, ref["示例交付"])
    body = "\n".join(b for _, b in bullets)
    assert not extra and observed["段名和顺序"] == ref["格式"]["段名"]
    assert len(title) <= ref["标题"]["上限"] and title.startswith(ref["标题"]["开头"])
    assert all(count == 1 for count in observed["标题规定内容的原样出现次数"].values())
    assert observed["要点条数"] == 5
    for point in observed["要点逐条"]:
        assert point["实际行首"] == "- " and point["字符数（不含行首编号或符号）"] <= ref["格式"]["每条上限"]
        assert re.fullmatch(r"[A-Z]+(?: [A-Z]+){1,3}", point["规定分隔符前的内容"] or "")
    assert not observed["交付内的禁用词命中"] and not observed["交付内的英式拼写命中"] and not observed["交付内的功能词提及"]
    assert {item["项目"] for item in observed["交付内的认证提及"]} == set(ref["认证"]["允许项目"])
    assert all(v == 1 for v in observed["准许成句在要点里的原样出现次数"].values())
    assert all(v >= 1 for v in observed["参考公制片段在要点里的原样出现次数（同义写法由评审看原文）"].values())
    assert all(v >= 1 for v in observed["参考美制片段在要点里的原样出现次数"].values())
    facts = ref["商品事实"]
    assert f"up to {facts['每日最多餐数']} meals" in body and f"{facts['录音秒数']}-second" in body
    assert facts["颜色"] in body and facts["供电"] in body
    if ref["第一条要点必须原样引用"] != "不适用":
        assert ref["第一条要点必须原样引用"] in bullets[0][1]
    assert ref["示例字符数"] == {"标题": len(title), "要点": [len(b) for _, b in bullets]}
    wrapper = "已核对 guaranteed 和 UL；以下是结果。\n" + ref["示例交付"] + "\n补充：colour，999 cups。\n"
    wrapped = measure(q, wrapper)
    for key in ("标题字符数", "交付内的禁用词命中", "交付内的英式拼写命中", "交付内的认证提及", "要点逐条"):
        assert wrapped[key] == observed[key], (q["name"], key)


def main():
    bank = json.loads((HERE / "questions.json").read_text())
    wrong = []
    for q in bank:
        wrong += [(q["name"], issue) for issue in errors(q)]
        check_example(q)
    assert len(bank) == 40 and len({q["name"] for q in bank}) == 40
    for q in bank:
        number = int(q["name"][1:])
        assert q["group"] == {"t": "train", "x": "same", "y": "new"}[q["name"][0]]
        assert q["rules"] == ("R3" if q["name"].startswith("y") else "R1" if number % 2 else "R2")
        assert q["segment"] == ("common" if number <= (10 if q["group"] == "train" else 5) else "edge")
    probes = [(["商品事实", "容量"], "999 L"), (["美制换算", "容量"], "999 cups"),
              (["认证", "允许项目"], ["NONE"]), (["认证", "必须原样写的成句"], ["NOT REAL"]),
              (["认证", "不能提及的项目"], []), (["格式", "每条上限"], 999), (["美制小数位"], 7),
              (["第一条要点必须原样引用"], "wrong"), (["商品事实", "净重"], "999 kg"), (["商品事实", "每日最多餐数"], 99),
              (["标题", "必含一次"], ["wrong"]), (["格式", "段名"], ["wrong"]), (["禁用写法"], ["unlisted"]),
              (["不得写的功能"], []), (["格式", "大写开头分隔符"], " ? ")]
    for path, value in probes:
        q = copy.deepcopy(bank[-1])
        target = q["reference"]
        for step in path[:-1]:
            target = target[step]
        target[path[-1]] = value
        assert errors(q), path
    self_test()
    print("mismatches:", wrong or "none")
    print(f"examples checked: {len(bank)}; independent-key mutations caught: {len(probes)}")
    assert not wrong


if __name__ == "__main__":
    main()
