"""自检：另写一遍算法，只读员工看到的四份文件（工作规则、订单记录、CRM 投诉记录、问题分类表）和题面，重算时限、迟到券、
补偿额度和剩余、要求超没超、本月同款同问题第几起和要不要标记，和参考答案逐题比对。

  python3 check.py
"""

import json
import re
from datetime import datetime
from decimal import ROUND_DOWN, Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent


def field(text: str, key: str) -> str:
    return re.search(rf"^- {key}：(.+)$", text, re.M).group(1).strip()


def main() -> None:
    wrong = []
    for q in json.loads((HERE / "questions.json").read_text()):
        rules, order, crm, table = (q["files"][n] for n in ("工作规则.md", "订单记录.md", "CRM投诉记录.md", "问题分类表.md"))
        ref = q["reference"]
        now = datetime.strptime(re.search(r"现在是 (\S+ \S+)。", q["text"]).group(1), "%Y-%m-%d %H:%M")
        size, unit = re.search(r"签收后 (\d+) (小时|天)内的", rules).groups()
        window = int(size) * (24 if unit == "天" else 1)
        signed = datetime.strptime(field(order, "签收时间"), "%Y-%m-%d %H:%M")
        within = (now - signed).total_seconds() / 3600 <= window
        late = (datetime.fromisoformat(field(order, "实际送达日期")) - datetime.fromisoformat(field(order, "承诺送达日期"))).days
        days, inclusive = re.search(r"晚了 (\d+) 天以上（(含|不含) ", rules).groups()
        coupon = late >= int(days) if inclusive == "含" else late > int(days)
        face = Decimal(re.search(r"补 ([\d.]+) 元无门槛券", rules).group(1))
        counted = "这张券不计入补偿额度" not in rules
        amount = Decimal(field(order, "订单金额").split()[0])
        quota = (amount * Decimal(re.search(r"不超过订单金额的 (\d+)%", rules).group(1)) / 100).quantize(
            Decimal("0.01"), rounding=ROUND_DOWN)
        if cap := re.search(r"并且最多 ([\d.]+) 元", rules):
            quota = min(quota, Decimal(cap.group(1)))
        left = quota - Decimal(field(order, "这个订单之前已发补偿").split()[0]) - (face if coupon and counted else 0)
        demand = re.search(r"赔我 (\d+) 块钱", q["text"])
        over = bool(demand) and Decimal(demand.group(1)) > left
        unit_name = re.search(r"^4\. 同(\S+?)同问题本月第 (\d+) 起起", rules, re.M)
        threshold = int(unit_name.group(2))
        style = field(order, unit_name.group(1)).rsplit("-", 1)[0]
        words = {cat: said.split("、") for cat, said in re.findall(r"^\| (\S+) \| (\S+) \|$", table, re.M)[1:]}
        issue = next(cat for cat, said in words.items() if any(w in q["text"] for w in said))
        orders = set()
        for line in crm.splitlines()[4:]:
            cells = [c.strip() for c in line.strip("|").split("|")]
            day, number, code, category, said = cells[1], cells[2], cells[3], cells[4], cells[5]
            if not day.startswith(now.strftime("%Y-%m")) or code.rsplit("-", 1)[0] != style:
                continue
            category = category or next(cat for cat, ws in words.items() if any(w in said for w in ws))
            if category == issue:
                orders.add(number)
        count = len(orders | {field(order, "订单号")})
        got = {"在不在可换可退的时限内": "在" if within else "不在", "晚了几天": late,
               "迟到补券": coupon, "还能直接给的补偿": f"{left} 元", "超出": over, "本月同款同问题第几起": count,
               "标记": count >= threshold}
        expected = {"在不在可换可退的时限内": ref["在不在可换可退的时限内"], "晚了几天": ref["晚了几天"],
                    "迟到补券": ref["迟到补券"].startswith("补 "), "还能直接给的补偿": ref["还能直接给的补偿"],
                    "超出": ref["客户要的补偿超没超出"].startswith("超出"), "本月同款同问题第几起": ref["本月同款同问题第几起"],
                    "标记": ref["要不要标记"].startswith("要")}
        if got != expected:
            wrong.append((q["name"], {k: (got[k], expected[k]) for k in got if got[k] != expected[k]}))
    print("mismatches:", wrong or "none")
    assert not wrong


if __name__ == "__main__":
    main()
