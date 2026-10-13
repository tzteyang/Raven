"""Observe a Listing; leave all pass/fail decisions to the model examiner.

Measurements deliberately separate title/bullets from extra wrapper text.
"""

import csv
import io
import re

HEADING = re.compile(r"^\s*#{1,6}\s+(.+?)\s*#*\s*$")
BULLET = re.compile(r"^\s*(?:[-*•]\s+|\d+[.)]\s+)(.*)$")
NUMBER_UNIT = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?:\s*x\s*\d+(?:\.\d+)?){0,2}\s*(?:cups|inches|mm|cm|mL|kg|lb|L|g)\b")


def read_csv(text):
    return list(csv.DictReader(io.StringIO(text)))


def word_pattern(word):
    if word.lower() == "no. 1":
        body = r"no\.\s*1"
    else:
        body = r"\s+".join(re.escape(part) for part in word.split())
    return re.compile(r"(?<![A-Za-z0-9])" + body + r"(?![A-Za-z0-9])", re.I)


def cert_pattern(alias):
    # The source permits whitespace/dots/hyphens between letters/numbers.
    chars = re.sub(r"[\s.\-]", "", alias)
    return re.compile(r"(?<![A-Za-z0-9])" + r"[\s.\-]*".join(re.escape(c) for c in chars) + r"(?![A-Za-z0-9])", re.I)


def scan_certs(text, rows):
    candidates = []
    for row in rows:
        for alias in row["常见别名（分号隔开）"].split(";"):
            for match in cert_pattern(alias).finditer(text):
                candidates.append((match.start(), match.end(), row["项目"], match.group()))
    candidates.sort(key=lambda item: (item[0], -(item[1] - item[0])))
    out, end = [], -1
    for start, stop, family, found in candidates:
        if start < end:
            continue
        out.append(dict(项目=family, 原文=found, 起点=start))
        end = stop
    return out


def split(product):
    before, sections = [], []
    for raw in product.splitlines():
        heading = HEADING.match(raw)
        if heading:
            sections.append({"段名": heading.group(1), "段名原文": raw, "行": []})
        elif raw.strip():
            (sections[-1]["行"] if sections else before).append(raw)
    return before, sections


def content(question, product):
    before, sections = split(product)
    expected = question["reference"]["格式"]["段名"]
    title_section = next((s for s in sections if s["段名"] == expected[0]), None)
    bullet_section = next((s for s in sections if s["段名"] == expected[1]), None)
    # Recognize common alternative headings for observation, without calling them valid.
    if title_section is None:
        title_section = next((s for s in sections if "title" in s["段名"].lower() or "标题" in s["段名"]), None)
    if bullet_section is None:
        bullet_section = next((s for s in sections if any(w in s["段名"].lower() for w in ("bullet", "feature", "highlight", "要点"))), None)
    title_raw = title_section["行"][0] if title_section and title_section["行"] else ""
    title = re.sub(r"^(?:Title|Listing Title|Product Title|标题)\s*[:：]\s*", "", title_raw.strip(), flags=re.I)
    title = title.strip('"“”')
    if title.startswith("**") and title.endswith("**"):
        title = title[2:-2]
    bullets, extra = [], list(before)
    if title_section:
        extra += title_section["行"][1:]
    if bullet_section:
        for raw in bullet_section["行"]:
            matched = BULLET.match(raw)
            if matched:
                bullets.append((raw, matched.group(1)))
            else:
                extra.append(raw)
    for section in sections:
        if section is not title_section and section is not bullet_section:
            extra += [section["段名原文"], *section["行"]]
    return sections, title_raw, title, bullets, extra


def measure(question, product):
    ref = question["reference"]
    sections, title_raw, title, bullets, extra = content(question, product)
    records, certs = read_csv(question["files"]["认证记录.csv"]), read_csv(question["files"]["认证写法.csv"])
    zones = [("标题", title)] + [(f"要点 {i}", body) for i, (_, body) in enumerate(bullets, 1)]
    bans, spell, cert_hits, features = [], [], [], []
    for zone, body in zones:
        for word in ref["禁用写法"]:
            bans += [{"位置": zone, "词表写法": word, "原文": m.group(), "起点": m.start()} for m in word_pattern(word).finditer(body)]
        for british, american in ref["拼写"].items():
            spell += [{"位置": zone, "原文": m.group(), "对应美式": american, "起点": m.start()} for m in word_pattern(british).finditer(body)]
        cert_hits += [dict(位置=zone, **item) for item in scan_certs(body, certs)]
        for word in ref["不得写的功能"]:
            features += [{"位置": zone, "原文": m.group()} for m in word_pattern(word).finditer(body)]
    separator = ref["格式"]["大写开头分隔符"]
    points = []
    for i, (raw, body) in enumerate(bullets, 1):
        prefix = body.split(separator, 1)[0] if separator in body else None
        points.append({"第几条": i, "原文": raw, "去行首后的内容": body, "字符数（不含行首编号或符号）": len(body),
                       "实际行首": raw[:len(raw) - len(body)], "规定分隔符": separator,
                       "规定分隔符前的内容": prefix, "该内容的英文单词": re.findall(r"[A-Za-z]+", prefix or ""),
                       "数值单位片段": NUMBER_UNIT.findall(body), "第一条引用限制的位置": body.find(ref["第一条要点必须原样引用"]) if ref["第一条要点必须原样引用"] != "不适用" else "不适用"})
    all_bullets = "\n".join(body for _, body in bullets)
    return {"段名和顺序": [s["段名"] for s in sections], "段落逐行原文": sections,
            "标题原始行": title_raw, "标题内容（去常见前缀/包裹，格式仍由评审检查）": title,
            "标题字符数": len(title), "标题原始行字符数": len(title_raw),
            "标题规定内容的原样出现次数": {v: title.count(v) for v in ref["标题"]["必含一次"]},
            "要点条数": len(bullets), "要点逐条": points, "交付外的说明": extra,
            "交付内的禁用词命中": bans, "交付内的英式拼写命中": spell, "交付内的认证提及": cert_hits,
            "交付内的功能词提及": features,
            "准许成句在要点里的原样出现次数": {v: all_bullets.count(v) for v in ref["认证"]["必须原样写的成句"]},
            "认证原始记录": records,
            "参考公制片段在要点里的原样出现次数（同义写法由评审看原文）": {k: all_bullets.count(v) for k, v in ref["商品事实"].items() if k in ("容量", "粒径", "机身尺寸", "净重") and isinstance(v, str)},
            "参考美制片段在要点里的原样出现次数": {k: all_bullets.count(v) for k, v in ref["美制换算"].items() if isinstance(v, str)}}


def self_test():
    assert not word_pattern("best").search("bestow")
    assert word_pattern("best").search('("BEST")')
    assert not word_pattern("#1").search("#10")
    assert word_pattern("no. 1").search("No.1")
    assert word_pattern("guaranteed").search("**guaranteed**")
    rows = [{"项目": "FCC", "常见别名（分号隔开）": "FCC;FCC Part 15;F.C.C. Part 15"},
            {"项目": "UL", "常见别名（分号隔开）": "UL;UL Listed"}, {"项目": "CE", "常见别名（分号隔开）": "CE;CE marked"}]
    assert [x["项目"] for x in scan_certs("FCC Part 15 compliant; U.L. Listed", rows)] == ["FCC", "UL"]
    assert scan_certs("color schedule useful voice message", rows) == []
    assert len('("VOICE MESSAGE")') == 17
    print("measure self-test: ok")


if __name__ == "__main__":
    self_test()
