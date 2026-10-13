"""自检：另写一遍算法，只读员工看到的三份文件（工作规则、竞品资料、汇率表）和题面里的团队人数，重算每家折算价、
折算后最便宜的一家、唯一领先项和每个功能格该写的词，和参考答案逐题比对。

  python3 check.py
"""

import json
import re
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
MONEY = r"([\d.]+) (元|美元|欧元|港元|日元)"


def read_rules(text: str) -> dict:
    paid, per = re.search(r"折算成“(年付|月付)、每人每(月|年)”", text).groups()
    places = 1 if "保留一位小数" in text else 0
    assert places == 1 or "四舍五入到整数" in text
    second = re.search(r"^2\. (.+)$", text, re.M).group(1)
    if "依次对应" in second:
        said, source = second.split("：", 1)
        words = dict(zip(re.findall(r"“(.+?)”", source), re.findall(r"“(.+?)”", said)))
    else:
        words = {"有": "有", "无": "无", "部分": "部分", "—": re.search(r"写“—”的格写“(.+?)”", second).group(1)}
    return {"ours": re.search(r"我方产品：(.+?)（", text).group(1), "discount": "不算年付折扣" not in text,
            "year": per == "年", "places": places, "words": words}


def read_fx(text: str) -> dict:
    found = dict(re.findall(r"^\| (\S+) [A-Z]{3} \| ([\d.]+) \|$", text, re.M))
    return {"元": Decimal(1), **{name: Decimal(value) for name, value in found.items()}}


def read_material(text: str) -> tuple[dict, list, dict]:
    pricing = dict(re.findall(r"^- (\S+?)(?:（我方）)?：(.+)。$", text, re.M))
    rows = [[c.strip() for c in line.strip("|").split("|")] for line in text.splitlines() if line.startswith("| ")]
    header, body = rows[0], rows[1:]
    cells = {row[0]: dict(zip(header[1:], row[1:])) for row in body}
    return pricing, header[1:], cells


def yearly_or_monthly(desc: str, n: int, rules: dict, fx: dict) -> Decimal:
    """One product's price per person, per month or per year as the rules say, in yuan, unrounded."""
    if "（对标版本）：" in desc:
        desc = next(part for part in desc.split("；") if "（对标版本）：" in part).split("（对标版本）：", 1)[1]
    off = re.search(r"年付打 ([\d.]+) 折", desc)
    rate = Decimal(off.group(1)) / 10 if off and rules["discount"] else Decimal(1)
    months = 12 if rules["year"] else 1
    if desc.startswith("按团队计费"):
        tiers = re.findall(r"(\d+)(?:–(\d+) 人| 人及以上) " + MONEY + r"/月", desc)
        low, high, price, unit = next(t for t in tiers if int(t[0]) <= n and (not t[1] or n <= int(t[1])))
        return Decimal(price) * rate * months / n * fx[unit]
    if "阶梯价" in desc:
        tiers = re.findall(r"(\d+)(?:–(\d+) 人| 人及以上) " + MONEY + r"/人/月", desc)
        low, high, price, unit = next(t for t in tiers if int(t[0]) <= n and (not t[1] or n <= int(t[1])))
        return Decimal(price) * rate * months * fx[unit]
    price, unit = re.search(MONEY, desc).groups()
    if "只有年付" in desc:
        return Decimal(price) * fx[unit] / (1 if rules["year"] else 12)
    if "只有月付" in desc:
        return Decimal(price) * months * fx[unit]
    assert desc.startswith("按人计费，"), desc
    return Decimal(price) * rate * months * fx[unit]


def main() -> None:
    wrong = []
    for question in json.loads((HERE / "questions.json").read_text()):
        files, ref = question["files"], question["reference"]
        rules, fx = read_rules(files["工作规则.md"]), read_fx(files["汇率表.md"])
        pricing, products, cells = read_material(files["竞品资料.md"])
        n = int(re.search(r"这次按 (\d+) 人的团队来比", question["text"]).group(1))
        step = Decimal(1).scaleb(-rules["places"])
        prices = {p: yearly_or_monthly(pricing[p], n, rules, fx).quantize(step, rounding=ROUND_HALF_UP) for p in products}
        expected = {p: Decimal(v.split()[0]) for p, v in ref["各家折算价"].items()}
        if prices != expected or any(str(prices[p]) != ref["各家折算价"][p].split()[0] for p in products):
            wrong.append((question["name"], "prices", prices, expected))
        cheapest = min(prices, key=prices.get)
        if not ref["折算后最便宜"].startswith(cheapest + "（"):
            wrong.append((question["name"], "cheapest", cheapest))
        ours = rules["ours"]
        leads = [f for f, row in cells.items() if row[ours] == "有" and all(row[p] in ("无", "部分") for p in products if p != ours)]
        if len(leads) != 1 or not ref["唯一领先项"].startswith(leads[0] + "（"):
            wrong.append((question["name"], "lead", leads))
        words = {f: {p: rules["words"][v] for p, v in row.items()} for f, row in cells.items()}
        if words != ref["功能格（每格该写的词）"]:
            wrong.append((question["name"], "cells"))
        if ("必须写出我方折算价" in ref["定位语要求"]) != (cheapest == ours and rules["year"]):
            wrong.append((question["name"], "price mention"))
    print("mismatches:", wrong or "none")
    assert not wrong


if __name__ == "__main__":
    main()
