"""自检：另写一遍算法，只读员工看到的文件（工作规则、门店日报、去年同月日报和字段对照表）和题面，重算每个排名下降最多的
门店、下降幅度（和下降金额）、基期没有数据的门店，和参考答案逐题比对。

  python3 check.py
"""

import csv
import io
import json
import re
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
NUMBERS = ["订单数", "零元单数", "退款单数", "全额退款单数", "实收金额", "退款金额", "优惠金额", "团购订单数"]


def read_rules(text: str) -> dict:
    first = re.search(r"^1\. (.+)$", text, re.M).group(1)
    if first.startswith("客单价 = 实收金额 ÷（订单数 − 零元单数）"):
        formula = lambda t: t["实收金额"] / (t["订单数"] - t["零元单数"])  # noqa: E731
    elif "有效订单数 = 订单数 − 零元单数 − 全额退款单数" in first:
        formula = lambda t: (t["实收金额"] - t["退款金额"]) / (t["订单数"] - t["零元单数"] - t["全额退款单数"])  # noqa: E731
    else:
        assert first.startswith("客单价 =（实收金额 − 退款金额）÷（订单数 − 零元单数）"), first
        formula = lambda t: (t["实收金额"] - t["退款金额"]) / (t["订单数"] - t["零元单数"])  # noqa: E731
    third = re.search(r"^3\. (.+)$", text, re.M).group(1)
    scope = ({"外卖": ("外卖",), "堂食": ("堂食",)} if "分开排名" in third
             else {"合并": ("堂食", "外卖")} if "合并算" in third else {"堂食": ("堂食",)})
    fourth = re.search(r"^4\. (.+)$", text, re.M).group(1)
    places = 1 if "保留一位小数" in fourth else 2 if "保留两位小数" in fourth else 0
    default = "同比" if "默认比去年同月" in text else "环比"
    return {"formula": formula, "scope": scope, "places": places, "amount": "下降金额" in fourth, "default": default}


def read_rows(text: str, mapping: dict | None = None, channels: dict | None = None) -> list[dict]:
    rows = []
    for raw in csv.DictReader(io.StringIO(text)):
        one = {(mapping or {}).get(k, k): v for k, v in raw.items()}
        one["渠道"] = (channels or {}).get(one["渠道"], one["渠道"])
        rows.append({**one, **{k: Decimal(one[k]) for k in NUMBERS}})
    return rows


def totals(rows: list[dict]) -> dict:
    """Per (month, store, channel group key) sums after dropping repeated (date, store, channel) rows."""
    seen, out = set(), {}
    for one in rows:
        key = (one["日期"], one["门店"], one["渠道"])
        if key in seen:
            continue
        seen.add(key)
        slot = out.setdefault((one["日期"][:7], one["门店"], one["渠道"]), {k: Decimal(0) for k in NUMBERS})
        for k in NUMBERS:
            slot[k] += one[k]
    return out


def main() -> None:
    wrong = []
    for question in json.loads((HERE / "questions.json").read_text()):
        files, ref = question["files"], question["reference"]
        rules = read_rules(files["工作规则.md"])
        month = int(re.search(r"(\d+) 月哪家门店", question["text"]).group(1))
        compare = "同比" if "客单价同比" in question["text"] else "环比" if "客单价环比" in question["text"] else rules["default"]
        rows = read_rows(files["门店日报.csv"])
        year = max(int(r["日期"][:4]) for r in rows)
        if "去年同月日报.csv" in files:
            pairs = re.findall(r"^\| (\S+) \| (\S+) \|$", files["字段对照表.md"], re.M)[1:]
            channel_names = dict(re.findall(r"去年的“(.+?)”就是今年的“(.+?)”", files["字段对照表.md"]))
            rows += read_rows(files["去年同月日报.csv"], dict(pairs), channel_names)
        cur = f"{year}-{month:02d}"
        base = f"{year - 1}-{month:02d}" if compare == "同比" else (f"{year}-{month - 1:02d}" if month > 1 else f"{year - 1}-12")
        sums = totals(rows)
        stores = sorted({r["门店"] for r in rows if r["日期"].startswith(cur)})
        for key, channels in rules["scope"].items():
            drops = {}
            for store in stores:
                parts = {}
                for period in (base, cur):
                    found = [sums[(period, store, c)] for c in channels if (period, store, c) in sums]
                    if found:
                        parts[period] = {k: sum(t[k] for t in found) for k in NUMBERS}
                if base in parts and cur in parts:
                    b, a = rules["formula"](parts[base]), rules["formula"](parts[cur])
                    drops[store] = (b, a, (b - a) / b)
            missing = [s for s in stores if s not in drops]
            top = max(drops, key=lambda s: drops[s][2])
            b, a, d = drops[top]
            got = {"下降最多的门店": top,
                   "下降幅度（按规则取舍后）": f"{(d * 100).quantize(Decimal(1).scaleb(-rules['places']), rounding=ROUND_HALF_UP)}%"}
            if rules["amount"]:
                got["下降金额（按规则取舍后）"] = f"{(b - a).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)} 元"
            entry = ref["排名"].get(key, {})
            if any(entry.get(k) != v for k, v in got.items()):
                wrong.append((question["name"], key, got, {k: entry.get(k) for k in got}))
            if bool(missing) != (not ref["不参与排名的门店"].startswith("无")) or any(m not in ref["不参与排名的门店"] for m in missing):
                wrong.append((question["name"], key, "missing", missing))
        if set(rules["scope"]) != set(ref["排名"]):
            wrong.append((question["name"], "rankings", list(rules["scope"]), list(ref["排名"])))
    print("mismatches:", wrong or "none")
    assert not wrong


if __name__ == "__main__":
    main()
