"""评审用的测量值：只量交付本身——标题段的那一行标题和卖点段的各行，不判对错。

- 标题：原样那一行、去掉首尾包裹符号（引号、书名号、括号、Markdown 加粗/代码符号、列表符号、“标题：”字样）后的标题、按本题规则数的
  字符数和明细、每个必含词的原样次数和规范化后次数、开头几个字、里面的阿拉伯数字和功能词表词语（各自在不在参数表里）。
- 卖点段：逐行列出行首写法、【】里的名字、正文（去掉行首编号或前缀和 Markdown 符号）里写出了哪些参数的值、数字和功能词，R2 还有每行
  正文的字符数。
- 禁用词和品牌名：按规则的比对办法（全角转半角、小写、去空格，包含就算）在标题和卖点段每一行里命中的词和原文。
- 两段之外的文字（第一个段名之前的、另加的段、标题段第 2 行起）只列出来，不量里面的词和数字。
"""

import re

RULESETS = {
    "R1": {"scheme": "byte", "max": 60, "min": None, "title": "标题", "points": "卖点", "count": 5,
           "lead": r"\d+\. ", "point_max": None, "prefix": None},
    "R2": {"scheme": "hanzi", "max": 50, "min": 40, "title": "商品名称", "points": "商品卖点", "count": 3,
           "lead": r"卖点[一二三四五六七八九十]+：", "point_max": 30, "prefix": None},
    "R3": {"scheme": "byte", "max": 56, "min": None, "title": "商品标题", "points": "卖点", "count": 4,
           "lead": r"【[^】]+】", "point_max": None, "prefix": "山野"},
}
PAIRS = [("**", "**"), ("__", "__"), ("`", "`"), ("“", "”"), ('"', '"'), ("‘", "’"), ("'", "'"), ("「", "」"), ("『", "』"),
         ("《", "》"), ("【", "】"), ("（", "）"), ("(", ")"), ("[", "]"), ("*", "*"), ("_", "_")]
LABEL = re.compile(r"^(?:商品标题|商品名称|标题)\s*[:：]\s*")
BULLET = re.compile(r"^(?:[-*+•·]\s+|>\s*)")
FENCE = re.compile(r"^\s*(```|~~~|---+|\*\*\*+|___+)\s*$")
HEAD = re.compile(r"^\s*#{1,6}\s*(.+?)\s*#*\s*$")
BOLD_HEAD = re.compile(r"^\s*\*\*\s*(.+?)\s*[:：]?\s*\*\*\s*[:：]?\s*$")
NUMBERING = re.compile(r"^\s*(?:[-*+•·]\s+)?(\d+\s*[\.．、)）](?!\d)\s*|卖点\s*[一二三四五六七八九十\d]+\s*[:：]\s*)")
KNOWN = {"标题", "商品标题", "商品名称", "卖点", "商品卖点"}
MARK = re.compile(r"^\s*(?:[-*+•·]\s*|\d+\s*[\.．、)）](?!\d)|[（(]\d+[）)]|卖点\s*[一二三四五六七八九十\d]+|【)")
NOTE = re.compile(r"^\s*(?:[-*+•·>]\s*)?(?:\d+\s*[\.．、)）]\s*)?[（(]?(?:注|说明|自查|备注|以上|核对|检查|字数|字符数|共\s*\d)")


def norm(text: str) -> str:
    out = []
    for ch in text:
        if 0xFF01 <= ord(ch) <= 0xFF5E:
            ch = chr(ord(ch) - 0xFEE0)
        if not ch.isspace():
            out.append(ch.lower())
    return "".join(out)


def vnorm(text: str) -> str:
    return "".join(chr(ord(ch) - 0xFEE0) if 0xFF01 <= ord(ch) <= 0xFF5E else ch for ch in text if not ch.isspace())


def unmark(text: str) -> str:
    """去掉 Markdown 的加粗、斜体、代码符号（** __ `），文字本身不动。"""
    return re.sub(r"\*\*|__|`", "", text)


def hanzi(ch: str) -> bool:
    return "一" <= ch <= "鿿" or "㐀" <= ch <= "䶿"


def length(text: str, scheme: str) -> int:
    if scheme == "byte":
        return sum(1 if " " <= ch <= "~" else 2 for ch in text)
    return sum(2 if hanzi(ch) else 0 if ch.isspace() else 1 for ch in text)


def breakdown(text: str, scheme: str) -> dict:
    if scheme == "byte":
        kinds = {"汉字（各算 2）": 0, "全角字母数字（各算 2）": 0, "其他非半角字符，如中文标点、全角空格、℃（各算 2）": 0,
                 "半角字母数字（各算 1）": 0, "半角空格（各算 1）": 0, "半角符号（各算 1）": 0}
        for ch in text:
            if hanzi(ch):
                kinds["汉字（各算 2）"] += 1
            elif "０" <= ch <= "９" or "Ａ" <= ch <= "Ｚ" or "ａ" <= ch <= "ｚ":
                kinds["全角字母数字（各算 2）"] += 1
            elif not " " <= ch <= "~":
                kinds["其他非半角字符，如中文标点、全角空格、℃（各算 2）"] += 1
            elif ch.isalnum():
                kinds["半角字母数字（各算 1）"] += 1
            elif ch == " ":
                kinds["半角空格（各算 1）"] += 1
            else:
                kinds["半角符号（各算 1）"] += 1
    else:
        kinds = {"汉字（各算 2）": sum(hanzi(ch) for ch in text), "空格（不算）": sum(ch.isspace() for ch in text)}
        kinds["其余字符（各算 1）"] = len(text) - kinds["汉字（各算 2）"] - kinds["空格（不算）"]
    return {k: v for k, v in kinds.items() if v}


def numbers(text: str) -> list[str]:
    """连在一起的一串阿拉伯数字（全角先换半角；空格隔开的是两个数）。"""
    narrow = "".join(chr(ord(ch) - 0xFEE0) if 0xFF01 <= ord(ch) <= 0xFF5E else ch for ch in text)
    return re.findall(r"[0-9]+(?:\.[0-9]+)?", narrow)


def spans(text: str, word: str) -> list[str]:
    """名单词在原文里命中的那一段原文（按比对办法找）。"""
    spots = [i for i, ch in enumerate(text) if not ch.isspace()]
    flat, key, found, start = norm(text), norm(word), [], 0
    if len(flat) != len(spots):
        return [word] if key in flat else []
    while key and (at := flat.find(key, start)) >= 0:
        found.append(text[spots[at]:spots[at + len(key) - 1] + 1])
        start = at + 1
    return found


def table(markdown: str) -> list[tuple[str, str]]:
    rows = [line for line in markdown.splitlines() if line.startswith("|") and not line.startswith("|---")]
    return [tuple(cell.strip() for cell in line.strip().strip("|").split("|")) for line in rows[1:]]


def listed(markdown: str) -> list[str]:
    return [line[2:].strip() for line in markdown.splitlines() if line.startswith("- ")]


def unwrap(line: str) -> tuple[str, list[str]]:
    """标题行去掉列表符号、“标题：”字样和成对的包裹符号（只去首尾成对、里面不再出现的）。"""
    removed, text = [], line.strip()
    while True:
        before = text
        if m := BULLET.match(text):
            removed.append(m.group(0).strip())
            text = text[m.end():].strip()
        if m := LABEL.match(text):
            removed.append(m.group(0).strip())
            text = text[m.end():].strip()
        for left, right in PAIRS:
            inner = text[len(left):len(text) - len(right)]
            if (len(text) > len(left) + len(right) and text.startswith(left) and text.endswith(right)
                    and left not in inner and right not in inner):
                removed.append(f"{left}…{right}")
                text = inner.strip()
                break
        if text == before:
            return text, removed


def sections(product: str) -> list[tuple[str, str, list[str]]]:
    """（段名行原样, 段名, 这一段的行）；第一个段名之前的行段名记为空。"""
    found = [("", "", [])]
    for line in product.splitlines():
        m, bold = HEAD.match(line), BOLD_HEAD.match(line)
        if m and len(m.group(1)) <= 12:
            found.append((line.strip(), m.group(1).strip("*：: "), []))
        elif bold and bold.group(1).strip("*：: ") in KNOWN:
            found.append((line.strip(), bold.group(1).strip("*：: "), []))
        else:
            found[-1][2].append(line)
    return found


def measure(question: dict, product: str) -> dict:
    rule = RULESETS[question["rules"]]
    files = question["files"]
    params = table(files["参数表.md"])
    musts = listed(files["类目必含词.md"])
    banned = listed(files["禁用词表.md"])
    brands = [name for pair in table(files["品牌名单.md"]) for name in pair]
    ref = question["reference"]
    clean = {item["参数名"]: item["卖点里要写出的值"] for item in ref["卖点要求"]["各参数（卖点里要写出“卖点里要写出的值”；值里的空格可以去掉，全角可以改半角）"]}
    present = ref["功能词"]["参数表里有的（可以写）"]
    present = [] if present == "无" else present
    functions = present + ref["功能词"]["参数表里没有的（标题和卖点都不能写）"]
    pool = {n for _, value in params for n in numbers(value)}
    parts = sections(product)
    names = [name for _, name, _ in parts[1:]]
    title_part = next((p for p in parts[1:] if p[1] == rule["title"]), None) or next(
        (p for p in parts[1:] if "标题" in p[1] or "名称" in p[1]), None)
    point_part = next((p for p in parts[1:] if p[1] == rule["points"]), None) or next(
        (p for p in parts[1:] if "卖点" in p[1]), None)
    result = {
        "交付里的段名行（按顺序，原样）": [head for head, _, _ in parts[1:]] or "没有找到段名行",
        "第一个段名之前的文字（不算交付）": "\n".join(line for line in parts[0][2] if line.strip())[:300] or "无",
        "规则要求的两段之外的段（不算交付）": [name for name in names if name not in (rule["title"], rule["points"])] or "无",
    }
    hits = []

    def scan(where: str, text: str):
        for word in banned + brands:
            for piece in spans(text, word):
                hits.append({"在哪": where, "名单上的写法": word, "命中的原文": piece,
                             "是": "品牌名" if word in brands else "禁用词"})

    title_lines = [line for line in (title_part[2] if title_part else []) if line.strip() and not FENCE.match(line)]
    if not title_lines:
        loose = [m.group(2) for line in product.splitlines()
                 if (m := re.match(r"^\s*(?:\*\*)?(标题|商品标题|商品名称)(?:\*\*)?\s*[:：]\s*(.+)$", line))]
        title_lines = loose[:1]
    if title_lines:
        raw = title_lines[0]
        title, removed = unwrap(raw)
        if title != unmark(title):
            title = unmark(title)
            removed.append("段中的 Markdown 符号")
        size = length(title, rule["scheme"])
        found_funcs = [w for w in functions if norm(w) in norm(title)]
        info = {
            "标题这一行（原样）": raw.strip(),
            "去掉的包裹符号或字样": removed or "无",
            "标题（去掉包裹后，以下各项都按它量）": title,
            "按本题规则的字符数": size,
            "本题规则的范围": (f"{rule['min']} 到 {rule['max']}" if rule["min"] else f"不超过 {rule['max']}"),
            "字符数明细": breakdown(title, rule["scheme"]),
            "必含词出现次数": {w: {"原样": title.count(w), "规范化后（不分全半角大小写、去空格）": norm(title).count(norm(w))}
                        for w in musts},
            "标题开头": title[:6],
            "阿拉伯数字": numbers(title) or "无",
            "其中参数表参数值里没有的数字": [n for n in numbers(title) if n not in pool] or "无",
            "功能词表词语": found_funcs or "无",
            "其中参数表里没有的功能词": [w for w in found_funcs if w not in present] or "无",
            "标题段里第 2 行起的文字（不算交付）": [line.strip() for line in title_lines[1:]] or "无",
        }
        if rule["prefix"]:
            info["开头是不是品牌名“%s”" % rule["prefix"]] = title.startswith(rule["prefix"])
        result["标题"] = info
        scan("标题", title)
    else:
        result["标题"] = "没找到标题段，也没找到“标题：”开头的行"
    rows = []
    section = [line for line in (point_part[2] if point_part else []) if line.strip() and not FENCE.match(line)]
    marked = [line for line in section if MARK.match(unmark(line)) and not NOTE.match(unmark(line))]
    point_lines = marked or [line for line in section if not NOTE.match(unmark(line))]
    for number, line in enumerate(point_lines, 1):
        text = unmark(line).strip()
        lead = re.match(r"^\s*(?:[-*+•·]\s+)?", text).group(0)
        rest = text[len(lead):]
        head = re.match(rule["lead"], rest)
        numbering = NUMBERING.match(text)
        body = text[numbering.end():] if numbering else rest
        label = re.match(r"^\s*【([^】]*)】\s*", body)
        row = {"第几条": number, "这一行（原样）": line.strip(),
               "行首": ((lead.strip() + " " if lead.strip() else "")
                        + (head.group(0) if head else numbering.group(1) if numbering else rest[:4])).strip(),
               "行首符合本规则的卖点写法": bool(head) and not lead.strip()}
        if label:
            row["【】里的名字"] = label.group(1)
            row["【】里的名字是参数表里的参数名"] = label.group(1) in [name for name, _ in params]
            body = body[label.end():]
        elif rule["lead"].startswith("【"):
            row["【】里的名字"] = "这一行开头没有【】"
        written = [name for name, _ in params if clean.get(name) and vnorm(clean[name]) in vnorm(body)]
        found_funcs = [w for w in functions if norm(w) in norm(body)]
        row.update({
            "正文（去掉行首编号或前缀、【】和 Markdown 符号）": body.strip(),
            "写出了值的参数": written or "无",
            "出现的参数名": [name for name, _ in params if name in body] or "无",
            "阿拉伯数字": numbers(body) or "无",
            "这些数字在哪些参数的值里": {n: [name for name, value in params if n in numbers(value)] or "参数表里没有"
                                for n in numbers(body)} or "无",
            "功能词表词语": found_funcs or "无",
            "其中参数表里没有的功能词": [w for w in found_funcs if w not in present] or "无",
        })
        if rule["point_max"]:
            row["正文字符数（按本题规则）"] = length(body.strip(), rule["scheme"])
            row["单条上限"] = rule["point_max"]
        rows.append(row)
        scan(f"第 {number} 条卖点", text)
    result["卖点段非空行数"] = len(section) if point_part else "没找到卖点段"
    result["卖点段里当作卖点来量的行数"] = len(point_lines)
    result["卖点段里不当作卖点量的行（开头没有编号、前缀或【】，或是说明、自查这类；只按格式项看）"] = (
        [line.strip() for line in section if line not in point_lines] or "无")
    result["本规则要求的卖点条数"] = rule["count"]
    result["卖点段各行"] = rows
    result["禁用词和品牌名（规范化后命中，只量交付本身）"] = hits
    return result


if __name__ == "__main__":
    files = {
        "参数表.md": "# 参数表：禾木空气炸锅\n\n| 参数名 | 参数值 |\n|---|---|\n| 型号 | HM-AF5L Pro |\n| 容量 | ５Ｌ |\n"
                    "| 定时 | 1-90 分钟 |\n| 涂层 | Teflon 不粘涂层 |\n| 最高温度 | 200℃ |\n",
        "类目必含词.md": "# 类目必含词\n\n- 空气炸锅\n- 5L\n- 可视\n",
        "禁用词表.md": "# 禁用词表\n\n## 极限用语\n\n- 最\n- 第 一\n- ＴＯＰ１\n- 健 康\n",
        "品牌名单.md": "# 品牌名单\n\n| 中文名 | 英文名 |\n|---|---|\n| 美的 | Midea |\n| 特氟龙 | Teflon |\n",
    }
    reference = {"卖点要求": {"各参数（卖点里要写出“卖点里要写出的值”；值里的空格可以去掉，全角可以改半角）": [
        {"参数名": "型号", "卖点里要写出的值": "HM-AF5L Pro"}, {"参数名": "容量", "卖点里要写出的值": "５Ｌ"},
        {"参数名": "定时", "卖点里要写出的值": "1-90 分钟"}, {"参数名": "涂层", "卖点里要写出的值": "不粘涂层"},
        {"参数名": "最高温度", "卖点里要写出的值": "200℃"}]},
        "功能词": {"参数表里有的（可以写）": "无", "参数表里没有的（标题和卖点都不能写）": ["预约", "保温"]}}
    q = {"rules": "R1", "files": files, "reference": reference}
    # 1. 正确交付：标题 4+8+2+4+1+6+...，逐字算
    good = "## 标题\n禾木空气炸锅5L可视 不粘\n\n## 卖点\n1. 5L大容量，一家人的分量\n2. 1-90分钟定时\n"
    got = measure(q, good)
    assert got["标题"]["按本题规则的字符数"] == 4 + 8 + 2 + 4 + 1 + 4, got["标题"]
    assert got["标题"]["必含词出现次数"]["5L"] == {"原样": 1, "规范化后（不分全半角大小写、去空格）": 1}, got["标题"]
    assert got["卖点段各行"][0]["写出了值的参数"] == ["容量"] and got["卖点段各行"][1]["写出了值的参数"] == ["定时"], got
    assert got["卖点段各行"][0]["行首符合本规则的卖点写法"] and got["禁用词和品牌名（规范化后命中，只量交付本身）"] == [], got
    # 2. 引号、括号、Markdown 包裹的标题：去掉包裹再数；开场白和段里的说明行单独列出，不量里面的词
    wrapped = ("好的，下面是标题和卖点（已自查，没有“最”“第一”）：\n\n## 标题\n**“禾木空气炸锅５Ｌ可视”**\n（共 26 个字符）\n\n"
               "## 卖点\n- 1. **Teflon不粘涂层**，好清洗\n2. 最高温度200℃，TOP 1 的口感\n以上卖点都核对过参数表，没有“最”和“第一”。\n\n## 自查\n没有第一。\n")
    got = measure(q, wrapped)
    t = got["标题"]
    assert t["标题（去掉包裹后，以下各项都按它量）"] == "禾木空气炸锅５Ｌ可视" and t["按本题规则的字符数"] == 4 + 8 + 4 + 4, t
    assert t["去掉的包裹符号或字样"] == ["**…**", "“…”"], t
    assert t["必含词出现次数"]["5L"] == {"原样": 0, "规范化后（不分全半角大小写、去空格）": 1}, t
    assert t["标题段里第 2 行起的文字（不算交付）"] == ["（共 26 个字符）"], t
    assert got["第一个段名之前的文字（不算交付）"].startswith("好的") and got["规则要求的两段之外的段（不算交付）"] == ["自查"], got
    first, second = got["卖点段各行"]
    assert first["行首"] == "- 1." and not first["行首符合本规则的卖点写法"] and first["写出了值的参数"] == ["涂层"], first
    assert second["写出了值的参数"] == ["最高温度"] and second["阿拉伯数字"] == ["200", "1"], second
    assert second["这些数字在哪些参数的值里"]["1"] == ["定时"], second
    assert got["卖点段里不当作卖点量的行（开头没有编号、前缀或【】，或是说明、自查这类；只按格式项看）"] == ["以上卖点都核对过参数表，没有“最”和“第一”。"], got
    found = [(h["在哪"], h["名单上的写法"], h["命中的原文"]) for h in got["禁用词和品牌名（规范化后命中，只量交付本身）"]]
    assert found == [("第 1 条卖点", "Teflon", "Teflon"), ("第 2 条卖点", "最", "最"), ("第 2 条卖点", "ＴＯＰ１", "TOP 1")], found
    # 3. R2：汉字算 2、空格不算、其余算 1；单条卖点按正文数（不算“卖点一：”和 Markdown 符号）
    q2 = {"rules": "R2", "files": files, "reference": reference}
    got = measure(q2, "## 商品名称\n《澄悦 IPX7 牙刷》\n## 商品卖点\n卖点一：**1-90 分钟**定时，“省心”\n")
    assert got["标题"]["按本题规则的字符数"] == 4 + 4 + 4 and got["标题"]["去掉的包裹符号或字样"] == ["《…》"], got["标题"]
    point = got["卖点段各行"][0]
    assert point["行首符合本规则的卖点写法"] and point["正文字符数（按本题规则）"] == 4 + 4 + 4 + 1 + 1 + 4 + 1, point
    assert point["写出了值的参数"] == ["定时"], point
    # 4. R3：开头的品牌名和【参数名】
    q3 = {"rules": "R3", "files": files, "reference": reference}
    got = measure(q3, "## 商品标题\n【山野】空气炸锅5L可视\n\n## 卖点\n【最高温度】200℃\n1. 【容量】5L\n")
    assert got["标题"]["开头是不是品牌名“山野”"] is False and got["标题"]["标题（去掉包裹后，以下各项都按它量）"].startswith("【山野】"), got
    first, second = got["卖点段各行"]
    assert first["【】里的名字"] == "最高温度" and first["【】里的名字是参数表里的参数名"] and first["行首符合本规则的卖点写法"], first
    assert second["【】里的名字"] == "容量" and not second["行首符合本规则的卖点写法"] and second["写出了值的参数"] == ["容量"], second
    assert [h["命中的原文"] for h in got["禁用词和品牌名（规范化后命中，只量交付本身）"]] == ["最"], got
    # 5. 卖点没写编号：没有一行带编号时，除了说明行都当卖点量
    got = measure(q, "## 标题\n禾木空气炸锅5L可视\n## 卖点\n5L大容量\n1-90分钟定时，“第 一 次”用前洗一下\n（以上已自查）\n")
    assert [r["写出了值的参数"] for r in got["卖点段各行"]] == [["容量"], ["定时"]], got["卖点段各行"]
    assert [(h["在哪"], h["命中的原文"]) for h in got["禁用词和品牌名（规范化后命中，只量交付本身）"]] == [("第 2 条卖点", "第 一")], got
    print("ok")
