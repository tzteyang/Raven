"""自检：另写一遍算法，只读员工看到的文件（工作规则、成交记录、赠品门市价表、极限词表）和题面，重算每种卡的参考价、
赠品价值合计和海报里的极限词，和参考答案逐题比对。

  python3 check.py
"""

import csv
import io
import json
import re
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> None:
    wrong = []
    for q in json.loads((HERE / "questions.json").read_text()):
        rules, ref = q["files"]["工作规则.md"], q["reference"]
        word, days = re.search(r"写“(\S+?) X 元”，X 是这种卡在活动开始前 (\d+) 天里", rules).groups()
        average = "平均实际成交价" in rules
        store_only = "“线上”的不算" in rules
        start = date.fromisoformat(re.search(r"活动 (\S+) 开始", q["text"]).group(1))
        poster = re.search(r"「(.+)」", q["text"], re.S).group(1)
        rows = list(csv.DictReader(io.StringIO(q["files"]["成交记录.csv"])))
        first, last = start - timedelta(days=int(days)), start - timedelta(days=1)
        for card in sorted({row["卡种"] for row in rows}):
            if not re.search(rf"[，！]{re.escape(card)}只要", poster):
                continue
            picked = [Decimal(row["成交价"]) for row in rows if row["卡种"] == card and row["状态"] == "成交"
                      and first.isoformat() <= row["日期"] <= last.isoformat() and (not store_only or row["渠道"] == "门店")]
            value = (sum(picked) / len(picked)).quantize(Decimal(1), rounding=ROUND_HALF_UP) if average else min(picked)
            if ref["各卡参考价"].get(card, {}).get("该写") != f"{word} {value} 元":
                wrong.append((q["name"], card, f"{word} {value} 元", ref["各卡参考价"].get(card)))
        prices = {name: Decimal(price) for name, price in re.findall(r"^\| (\S+) \| (\d+) 元/\S+ \|$", q["files"]["赠品门市价表.md"], re.M)}
        rate = re.search(r"再打 (\d+) 折", rules)
        listed = re.search(r"的(.+?)[，！]", poster[poster.index("办卡送价值"):]).group(1)
        total = Decimal(0)
        for part in listed.split(" + "):
            name, qty = re.match(r"(\S+) (\d+) ", part).groups()
            total += prices[name] * int(qty) * (Decimal(rate.group(1)) / 10 if rate else 1)
        shown = f"{total.quantize(Decimal(1))}" if total == total.to_integral_value() else f"{total.normalize():f}"
        if ref["赠品价值"]["该写"] != f"{shown} 元":
            wrong.append((q["name"], "gift", shown, ref["赠品价值"]["该写"]))
        words = [line.strip() for line in q["files"]["极限词表.md"].splitlines()[2:] if line.strip()]
        found = sorted(w for w in words if w in poster)
        if found != sorted(ref["海报里能找到的极限词表词语"]):
            wrong.append((q["name"], "words", found, ref["海报里能找到的极限词表词语"]))
    print("mismatches:", wrong or "none")
    assert not wrong


if __name__ == "__main__":
    main()
