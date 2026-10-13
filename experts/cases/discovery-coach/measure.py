"""评审用的测量值：清单逐题拆开（序号、员工标的类别、问题本身、问号个数、可疑的封闭问法写法、问题里出现的线索字眼）、
按员工标注数出来的各类题数、最后一行，以及清单前后多出来的行。只作评审依据，判定由评审做。"""

import json
import re

CLOSED = r"是不是|对不对|有没有|是否|能否|可否|会不会|要不要|能不能|行不行|吗[？?]?\s*$"
ITEM = re.compile(r"^\s*(?:\*\*)?(\d+)[.、）)]\s*(?:\*\*)?\s*(?:【(背景|难点|影响|需求回报)】)?\s*(.+?)\s*(?:[（(](背景|难点|影响|需求回报)[)）])?\s*$")


def measure(question: dict, product: str) -> dict:
    lead = json.loads(question["files"]["线索.md"].split("```json")[1].split("```")[0])
    words = set()
    for field, value in lead["表单字段"].items():
        words.add(str(value).split()[0])
    for text in [lead["表单留言"]] + list(lead["公开信息（公众号、官网）"]):
        words.update(w for w in re.findall(r"[一-鿿A-Za-z]{2,}", text) if len(w) <= 6)
    lines = [line.strip() for line in product.splitlines() if line.strip()]
    items, other = [], []
    for line in lines:
        m = ITEM.match(line)
        if m:
            body = m.group(3)
            items.append({
                "序号": int(m.group(1)), "标的类别": m.group(2) or m.group(4) or "（没标）", "问题": body,
                "问号个数": body.count("？") + body.count("?"),
                "可疑的封闭写法": re.findall(CLOSED, body),
                "带“和/以及/还有”": [w for w in ("和", "以及", "还有") if w in body],
                "问题里出现的线索字眼": sorted(w for w in words if w in body),
            })
        else:
            other.append(line)
    counts = {c: sum(1 for i in items if i["标的类别"] == c) for c in ("背景", "难点", "影响", "需求回报")}
    return {
        "题数": len(items),
        "按员工标注数的各类题数": counts,
        "逐题": items,
        "不是题目的行（含结尾一行和清单前后多出来的文字）": other,
        "最后一行": lines[-1] if lines else "",
    }


if __name__ == "__main__":
    q = {"files": {"线索.md": "# 线索\n\n```json\n" + json.dumps({"表单字段": {"门店数": "12 家"}, "表单留言": "爆约太多，现在用Excel排预约。",
                                                                "公开信息（公众号、官网）": ["今年新开门店：四家"]}, ensure_ascii=False) + "\n```\n"}}
    got = measure(q, "好的，清单如下：\n1.【背景】你们门店规模多大？\n2. 爆约率现在是多少？（难点）\n3.【影响】是否影响营收吗？\n下一步：约下周三演示。")
    assert got["题数"] == 3 and got["按员工标注数的各类题数"]["影响"] == 1 and got["逐题"][1]["标的类别"] == "难点", got
    assert got["逐题"][2]["可疑的封闭写法"] and got["不是题目的行（含结尾一行和清单前后多出来的文字）"][0].startswith("好的"), got
    print("ok")
