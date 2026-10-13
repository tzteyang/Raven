"""为评审列出对照表、改写数字、限定词、关键词和来源；不决定通过或失败。

只量表格中的改写列。照抄的原句与表格外说明另列，不混进改写统计。
"""

import csv
import io
import re
from decimal import Decimal

CHARS = "零〇一二两三四五六七八九十百千万亿点壹贰叁肆伍陆柒捌玖拾佰仟萬億"
DIGITS = {word: value for value, words in enumerate(("零〇", "一壹", "二两贰", "三叁", "四肆", "五伍", "六陆", "七柒", "八捌", "九玖")) for word in words}
UNITS = {"十": 10, "拾": 10, "百": 100, "佰": 100, "千": 1000, "仟": 1000}
NUMBERS = re.compile(
    rf"百分之(?:[{CHARS}]+|\d+(?:\.\d+)?)|"
    rf"(?<![A-Za-z0-9.])\d[\d,]*(?:\.\d+)?\s*(?:万|萬|亿|億|千)?\s*(?:余|\+)?\s*(?:%|％|人|次|篇|条|套|倍|年|个月)?|"
    rf"[{CHARS}]+\s*(?:余|\+)?\s*(?:%|％|人|次|篇|条|套|倍|年|个月)"
)
RAISE_WORDS = ["主导", "牵头", "全面负责", "带领团队"]


def chinese_number(text):
    text = text.replace("萬", "万").replace("億", "亿")
    for symbol, scale in (("亿", 100000000), ("万", 10000)):
        if symbol in text:
            high, low = text.split(symbol, 1)
            return chinese_number(high) * scale + (chinese_number(low) if low else Decimal(0))
    if "点" in text:
        whole, fraction = text.split("点", 1)
        return chinese_number(whole) + Decimal("0." + "".join(str(DIGITS[d]) for d in fraction))
    if text.isdigit():
        return Decimal(text)
    total, current = 0, 0
    for ch in text:
        if ch in DIGITS:
            current = DIGITS[ch]
        elif ch in UNITS:
            total += (current or 1) * UNITS[ch]
            current = 0
        else:
            raise ValueError(text)
    return Decimal(total + current)


def normalized(raw):
    compact = re.sub(r"\s+", "", raw).replace("％", "%")
    percent = compact.startswith("百分之") or compact.endswith("%")
    core = compact.removeprefix("百分之")
    core = re.sub(r"(?:余|\+)?(?:%|人|次|篇|条|套|倍|年|个月)?$", "", core)
    if re.match(r"\d", core):
        scale = {"万": 10000, "萬": 10000, "亿": 100000000, "億": 100000000, "千": 1000}.get(core[-1], 1)
        value = Decimal((core[:-1] if scale != 1 else core).replace(",", "")) * scale
    else:
        value = chinese_number(core)
    display = format(value, "f").rstrip("0").rstrip(".") if "." in format(value, "f") else format(value, "f")
    return display, "%" if percent else (re.search(r"(?:人|次|篇|条|套|倍|年|个月)$", compact).group(0)
                                           if re.search(r"(?:人|次|篇|条|套|倍|年|个月)$", compact) else "")


def numbers(text):
    found = []
    for m in NUMBERS.finditer(text):
        raw = m.group(0).strip()
        try:
            value, unit = normalized(raw)
        except (ValueError, KeyError):
            value, unit = "未归一", ""
        found.append({"原文": raw, "归一数值": value, "单位": unit,
                      "附近原文": text[max(0, m.start() - 12):min(len(text), m.end() + 12)]})
    return found


def sentences(text):
    return [piece.strip() for piece in re.split(r"[。！？!?]+", text) if re.search(r"[\w\u4e00-\u9fff]", piece)]


def split_table(product):
    headers, rows, tables, outside, separator = [], [], [], [], []
    current = None
    for n, line in enumerate(product.splitlines(), 1):
        stripped = line.strip()
        if not stripped:
            continue
        title = re.fullmatch(r"##\s+(.+)", stripped)
        if title:
            headers.append(title.group(1))
            current = None
        elif stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in re.split(r"(?<!\\)\|", stripped[1:-1])]
            if all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                separator.append(n)
                continue
            if any(c in {"条目", "原编号", "改后", "新句", "改写"} for c in cells):
                tables.append(cells)
                current = cells
            else:
                rows.append({"行号": n, "列值": cells, "表头": current})
        else:
            outside.append({"行号": n, "文字": stripped})
    return headers, tables, rows, outside, separator


def measure(question, product):
    files = question["files"]
    facts = list(csv.DictReader(io.StringIO(files["事实表.csv"])))
    jd = [line[2:].strip() for line in files["目标岗位.md"].splitlines() if line.startswith("- ")]
    original = dict(re.findall(r"^(E\d+)：(.+)$", files["原简历.md"], re.M))
    headers, tables, rows, outside, separators = split_table(product)
    measured = []
    for row in rows:
        cells = row["列值"]
        if len(cells) < 3:
            measured.append({**row, "备注": "不足三列，未抽取改写文本"})
            continue
        item, before, after = cells[:3]
        source = cells[3] if len(cells) >= 4 else ""
        relevant = [f for f in facts if f["条目"] == item]
        fact_numbers = [{"事实编号": f["事实编号"], "状态": f["状态"], "数字": numbers(f["结果事实"])} for f in relevant]
        measured.append({"行号": row["行号"], "条目": item, "原句列": before, "原简历对应句": original.get(item, "没找到"),
                         "改写列": after, "字符数（不含空白）": len(re.sub(r"\s", "", after)), "句数": len(sentences(after)),
                         "改写里的数字": numbers(after), "本条事实表里的数字": fact_numbers,
                         "出现的岗位关键词": [kw for kw in jd if kw in after],
                         "出现的限定词": [kw for kw in ("约", "余", "最高", "平均", "累计", "至", "团队", "协助", "独立") if kw in after],
                         "出现的拔高词": [kw for kw in RAISE_WORDS if kw in after],
                         "来源列原文": source, "来源编号": re.findall(r"F\d+", source), "本条事实编号与状态": {
                             f["事实编号"]: f["状态"] for f in relevant}})
    after_all = "\n".join(row.get("改写列", "") for row in measured)
    return {"段名（按顺序）": headers, "表头列表": tables, "表格分隔线数量": len(separators), "数据行数": len(rows),
            "逐行测量": measured, "改写列关键词出现次数": {word: after_all.count(word) for word in jd},
            "表格外的文字（只供格式项判断）": outside,
            "提示": "本工具只列事实、文本和数量，不判断是否违反规则；数字在表里出现过也不代表指标、归属、限定或期间相同。"}


def selftest():
    cases = {"8.6万": "86000", "86000": "86000", "二万一千人": "21000", "两人": "2", "四十余次": "40",
             "百分之三点六": "3.6", "8,600人": "8600", "八万六千人": "86000", "叁拾贰人": "32"}
    for raw, expected in cases.items():
        assert normalized(raw)[0] == expected, (raw, normalized(raw))
    assert len(sentences('“完成了什么？”（整理记录。）**已交付。**')) == 3
    assert len(sentences('“完成了什么？”')) == 1
    assert [x["归一数值"] for x in numbers("实施约四十次；覆盖36至42次；达到10万+；点击率百分之三点六。")] == ["40", "36", "42", "100000", "3.6"]
    title, cols, rows, outside, sep = split_table("开场：999人。\n## 改前改后\n| 条目 | 改前 | 改后 |\n|---|---|---|\n| E1 | SEO999% | **执行A/B测试两次。** |\n结尾SEO999%")
    assert len(rows) == 1 and len(outside) == 2 and len(sep) == 1
    assert rows[0]["列值"][2] == "**执行A/B测试两次。**"
    assert numbers("F01 E2") == []
    print("measure selftest: ok")


if __name__ == "__main__":
    selftest()
