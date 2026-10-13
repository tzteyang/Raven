"""评审用的测量值：交付的段名和段外文字；各段逐行字数（按规则的算法：空格和换行不算，一个 emoji 算 2，其余每个字符算 1）；
标题的字数和明细、认出的 emoji、标题必带参数在不在、标题里带数字的写法；正文字数、行数、前几行、要原样写出的文字在正文第几行；
禁用字词、网址和导流词逐处列出（所在段、第几行、上下文）；话题段里的话题、个数、必带话题的位置、标题和正文里的“#”；合作标注
那一段的内容和规定写法出现的位置。只作评审依据，判定由评审做。"""

import re
import unicodedata

URL_MARK = re.compile(r"http|www|\.com|\.cn", re.I)
URL_RUN = re.compile(r"[A-Za-z0-9:/._\-~?=&%+]+")
# 默认按 emoji 显示的基本平面字符（Emoji_Presentation），和常被当 emoji 用、默认按文字显示的符号（☀❤✔✈……）
EMOJI_DEFAULT = {0x231A, 0x231B, 0x23E9, 0x23EA, 0x23EB, 0x23EC, 0x23F0, 0x23F3, 0x25FD, 0x25FE, 0x2614, 0x2615,
                 *range(0x2648, 0x2654), 0x267F, 0x2693, 0x26A1, 0x26AA, 0x26AB, 0x26BD, 0x26BE, 0x26C4, 0x26C5,
                 0x26CE, 0x26D4, 0x26EA, 0x26F2, 0x26F3, 0x26F5, 0x26FA, 0x26FD, 0x2705, 0x270A, 0x270B, 0x2728,
                 0x274C, 0x274E, 0x2753, 0x2754, 0x2755, 0x2757, 0x2795, 0x2796, 0x2797, 0x27B0, 0x27BF, 0x2B1B,
                 0x2B1C, 0x2B50, 0x2B55}
EMOJI_TEXT = set("☀☁☂☃☄☎☑☘☝☠☢☣☦☪☮☯☸☹☺♀♂♟♠♣♥♦♨♻♾⚒⚔⚕⚖⚗⚙⚛⚜⚠⚧⚰⚱⛈⛏⛑⛓⛩⛰⛱⛴⛷⛸⛹✂✈✉✌✍✏✒✔✖✝✡✳✴❄❇❣❤➡⬅⬆⬇")
JOINERS = {"︎", "️", "⃣"}
SECTION_WORDS = ("标题", "正文", "话题", "合作")
HEADING = re.compile(r"^\s*#{1,6}\s+(.+?)\s*#*\s*$")
LOOSE_HEADING = re.compile(r"^\s*(?:\*\*|【)?\s*(标题|正文|话题|合作标注|合作声明)\s*(?:\*\*|】)?\s*[:：]?\s*$")
NUMBER = re.compile(r"[A-Za-z]*[-+−]?\d[\d.+×]*\s?[A-Za-z℃°%]*")


def _pictograph(ch: str) -> bool:
    cp = ord(ch)
    return (0x1F000 <= cp <= 0x1FAFF and not 0x1F3FB <= cp <= 0x1F3FF) or cp in EMOJI_DEFAULT or ch in EMOJI_TEXT


def emoji_spans(text: str) -> list[tuple[int, int]]:
    """Where the emoji are: one span per emoji, however many code points it uses (variation selector, skin tone,
    zero-width-joiner sequence, flag pair, keycap)."""
    spans, i, n = [], 0, len(text)
    while i < n:
        ch, cp = text[i], ord(text[i])
        if 0x1F1E6 <= cp <= 0x1F1FF:
            end = i + 2 if i + 1 < n and 0x1F1E6 <= ord(text[i + 1]) <= 0x1F1FF else i + 1
        elif ch in "0123456789#*" and text[i + 1:i + 3] == "️⃣":
            end = i + 3
        elif ch in "0123456789#*" and text[i + 1:i + 2] == "⃣":
            end = i + 2
        elif _pictograph(ch) or (text[i + 1:i + 2] == "️" and not ch.isspace()):
            end = i + 1
            while end < n:
                nxt = text[end]
                if nxt in JOINERS or 0x1F3FB <= ord(nxt) <= 0x1F3FF:
                    end += 1
                elif nxt == "‍" and end + 1 < n:
                    end += 2
                else:
                    break
        else:
            i += 1
            continue
        spans.append((i, end))
        i = end
    return spans


def _kind(ch: str) -> str:
    cp = ord(ch)
    if 0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF or 0xF900 <= cp <= 0xFAFF or 0x20000 <= cp <= 0x2FA1F:
        return "汉字"
    category = unicodedata.category(ch)
    if category == "Nd":
        return "数字"
    if category.startswith("L"):
        return "字母"
    if category in ("Cf", "Mn") or ch in JOINERS or ch == "‍":
        return "看不见的字符（不算）"
    return "标点和符号"


def detail(text: str) -> dict:
    """The count by the rules and what it is made of."""
    spans = emoji_spans(text)
    inside = {k for start, end in spans for k in range(start, end)}
    parts = {"汉字": 0, "字母": 0, "数字": 0, "标点和符号": 0}
    symbols, unseen, spaces = [], 0, 0
    for k, ch in enumerate(text):
        if k in inside:
            continue
        if ch.isspace():
            spaces += 1
            continue
        kind = _kind(ch)
        if kind == "看不见的字符（不算）":
            unseen += 1
            continue
        parts[kind] += 1
        if kind == "标点和符号":
            symbols.append(ch)
    total = sum(parts.values()) + 2 * len(spans)
    return {"字数": total, **{k: v for k, v in parts.items()}, "标点和符号是哪些": "".join(symbols),
            "emoji 个数（每个算 2）": len(spans), "认出的 emoji": [text[s:e] for s, e in spans],
            "空格（不算）": spaces, "看不见的字符（不算）": unseen}


def count(text: str) -> int:
    return detail(text)["字数"]


def split(product: str) -> tuple[list[str], list[dict]]:
    """Lines before the first section name, and the sections in order with their non-empty lines."""
    before, sections = [], []
    for line in product.splitlines():
        found = HEADING.match(line) or LOOSE_HEADING.match(line)
        if found:
            sections.append({"段名": found.group(1).strip(), "行": []})
        elif line.strip():
            (sections[-1]["行"] if sections else before).append(line.strip())
    return before, sections


def _roles(names: list[str], sections: list[dict]) -> dict:
    """The section that plays each required part: same name first, else a name sharing its key word."""
    roles = {}
    for name in names:
        exact = next((s for s in sections if s["段名"] == name), None)
        loose = next((s for s in sections for w in SECTION_WORDS if w in name and w in s["段名"]), None)
        if exact or loose:
            roles[name] = exact or loose
    return roles


def _context(line: str, start: int, end: int) -> str:
    return line[max(0, start - 8):end + 8]


def _where(zone: str, no: int, line: str) -> str:
    """Where a line is, flagging lines that are not the title line or not a topic line."""
    note = ""
    if zone == "“标题”段" and no > 1:
        note = "（标题段多出来的行，不是标题）"
    elif zone == "“话题”段" and not line.startswith("#"):
        note = "（这一行不以“#”开头，不是话题）"
    return f"{zone} 第 {no} 行{note}"


def _scan(zones: list[tuple[str, list[str]]], words: list[str]) -> list[dict]:
    out = []
    for zone, lines in zones:
        for no, line in enumerate(lines, 1):
            for word in words:
                for m in re.finditer(re.escape(word), line):
                    out.append({"字词": word, "位置": _where(zone, no, line), "上下文": _context(line, m.start(), m.end())})
    return out


def _urls(zones: list[tuple[str, list[str]]]) -> list[dict]:
    out = []
    for zone, lines in zones:
        for no, line in enumerate(lines, 1):
            for m in URL_RUN.finditer(line):
                marks = [x.group() for x in URL_MARK.finditer(m.group())]
                if marks:
                    out.append({"网址": m.group(), "里面的标记": marks, "位置": _where(zone, no, line),
                                "上下文": _context(line, m.start(), m.end())})
    return out


def measure(question: dict, product: str) -> dict:
    ref = question["reference"]
    names = [s.replace("## ", "") for s in ref["交付格式"]["段名和顺序"]]
    label_name = next(n for n in names if n.startswith("合作"))
    before, sections = split(product)
    roles = _roles(names, sections)
    zones = ([("第一个段名之前", before)] if before else []) + [(f"“{s['段名']}”段", s["行"]) for s in sections]

    title_lines = roles["标题"]["行"] if "标题" in roles else []
    title = re.sub(r"^(?:标题|题目)\s*[:：]\s*", "", title_lines[0]) if title_lines else ""
    must = ref["标题"]["标题必带参数（照参数表“数值”一栏原样写）"]
    body = roles["正文"]["行"] if "正文" in roles else []
    first = ref["正文"]["前几行（空行不算）"]
    needed = ref["正文"]["前几行里要原样写出的文字"]
    caution = ref["正文"]["正文里要原样写出的使用限制"]
    squeeze = [re.sub(r"\s", "", line) for line in body]
    tag_lines = roles["话题"]["行"] if "话题" in roles else []
    topic_lines = [line for line in tag_lines if line.startswith("#")]
    tags = re.findall(r"#[^\s#]+", " ".join(topic_lines))
    required = ref["话题"]["必带话题"]
    label = ref["交付格式"]["合作标注的写法"]
    clean = ref["禁用说法和导流"]
    return {
        "段名（按顺序）": [s["段名"] for s in sections],
        "规则要求的段名（按顺序）": names,
        "第一个段名之前的文字": before or "无",
        "各段逐行字数（空行不算；字数按规则算：空格不算，emoji 算 2，其余每个字符算 1）": [
            {"段": zone, "整段字数": sum(count(line) for line in lines),
             "逐行": [{"第几行": no, "字数": count(line), "内容": line[:40] + ("…" if len(line) > 40 else "")}
                     for no, line in enumerate(lines, 1)]} for zone, lines in zones],
        "标题": {
            "标题段的行数": len(title_lines),
            "标题（标题段第一行，去掉开头的“标题：”）": title,
            "字数明细": detail(title),
            "规则上限": ref["标题"]["字数上限"],
            "标题必带参数在标题里有没有（原样，区分大小写和空格）": {v: v in title for v in must},
            "标题里带数字的写法": [m.group().strip() for m in NUMBER.finditer(title)],
        },
        "正文": {
            "字数（整段）": sum(count(line) for line in body),
            "行数（空行不算）": len(body),
            f"前 {first} 行": body[:first],
            "要原样写出的文字在正文第几行（去掉空格后比）": {
                s: [no for no, line in enumerate(squeeze, 1) if re.sub(r"\s", "", s) in line] or "没有" for s in needed},
            "使用限制在正文第几行（去掉空格后比）": (
                [no for no, line in enumerate(squeeze, 1) if re.sub(r"\s", "", caution) in line] or "没有"
                if not caution.startswith("这套规则不要求") else "这套规则不要求"),
        },
        "禁用字词（逐处，含段外）": _scan(zones, clean["禁用字词（是别的词的一部分也算）"]) or "无",
        "网址（一串连续的英文字母数字符号算一个，逐个列出，含段外）": _urls(zones) or "无",
        "导流词（逐处，含段外）": _scan(zones, clean["导流词（是别的词的一部分也算）"]) or "无",
        "话题": {
            "话题段的行数（空行不算）": len(tag_lines),
            "以“#”开头的行数（话题行）": len(topic_lines),
            "话题段里不以“#”开头的行（不算话题，可能是夹进来的说明）": [line for line in tag_lines if not line.startswith("#")] or "无",
            "话题行里的话题（按顺序）": tags,
            "个数": len(tags),
            "规则上限": ref["话题"]["个数上限"],
            "必带话题在第几个": {t: [i for i, x in enumerate(tags, 1) if x == t] or "没有" for t in required},
            "话题之间没空格的地方": [line for line in topic_lines if re.search(r"[^\s#]#", line)] or "无",
            "话题行里不以“#”开头的文字": [w for w in " ".join(topic_lines).split() if not w.startswith("#")] or "无",
            "标题和正文里的“#”": [f"{zone}：{line[:40]}" for zone, lines in (("标题", title_lines), ("正文", body))
                               for line in lines if "#" in line] or "无",
        },
        "合作标注": {
            "规则要求": ref["交付格式"]["合作标注"],
            f"“{label_name}”段的内容": roles[label_name]["行"] if label_name in roles else "没有这一段",
            "规定写法出现在哪里": [f"{zone} 第 {no} 行" for zone, lines in zones for no, line in enumerate(lines, 1)
                              if label in line] or "没有",
        },
    }


if __name__ == "__main__":
    # 真实写法自测：引号、括号、Markdown 标记、各种 emoji（变体符、肤色、零宽连接、国旗、键帽）
    cases = {
        "“轻”到忘记它（1200g）": 14,
        "**🌙1200g睡袋**": 13,
        "- 拉链顺滑✔️": 7,
        "👨‍👩‍👧 一家三口 🇨🇳": 8,
        "1️⃣ 先看重量": 6,
        "❤ 爱了": 4,
        "👍🏻好用": 4,
        "（正文 420 字）": 8,
        "> 引用一句": 5,
        "⛺-5℃ 45+5L｜210×140cm！": 21,
        "“这是第一次吗？”她问。": 12,
    }
    for text, want in cases.items():
        assert count(text) == want, (text, count(text), detail(text))
    assert detail("🌙-10℃ 1050g睡袋｜钻进去就暖和")["认出的 emoji"] == ["🌙"]
    ref = {"交付格式": {"段名和顺序": ["## 标题", "## 正文", "## 话题", "## 合作标注"], "合作标注": "只写“品牌合作”",
                    "合作标注的写法": "品牌合作"},
           "标题": {"标题必带参数（照参数表“数值”一栏原样写）": ["1200g"], "字数上限": 20},
           "正文": {"前几行（空行不算）": 3, "前几行里要原样写出的文字": ["春秋季徒步露营的两人组"],
                  "正文里要原样写出的使用限制": "这套规则不要求（参数表里的使用限制写不写都行）"},
           "话题": {"必带话题": ["#岚径露营", "#睡袋推荐"], "个数上限": 5},
           "禁用说法和导流": {"禁用字词（是别的词的一部分也算）": ["全网", "最轻", "第一"],
                       "导流词（是别的词的一部分也算）": ["链接", "天猫"]}}
    product = ("好的，按规则写好了（标题 13 字，第一次用这么轻的）：\n\n## 标题\n标题：**🌙1.2kg睡袋**\n\n## 正文\n"
               "姐妹们！\n“最轻松”的一次露营\n适合春秋季 徒步露营的两人组\n天猫有链接 https://lanjing.tmall.com #岚径露营\n\n"
               "## 话题\n#岚径露营#冬季露营 #户外\n\n## 合作标注\n品牌合作\n说明：话题 #睡袋推荐 没放，www.x.cn 也没放。")
    got = measure({"reference": ref}, product)
    assert got["段名（按顺序）"] == ["标题", "正文", "话题", "合作标注"], got
    assert got["第一个段名之前的文字"] == ["好的，按规则写好了（标题 13 字，第一次用这么轻的）："], got
    assert got["标题"]["标题（标题段第一行，去掉开头的“标题：”）"] == "**🌙1.2kg睡袋**", got
    assert got["标题"]["字数明细"]["字数"] == 13 and got["标题"]["标题必带参数在标题里有没有（原样，区分大小写和空格）"] == {"1200g": False}
    assert got["标题"]["标题里带数字的写法"] == ["1.2kg"], got["标题"]
    assert got["正文"]["要原样写出的文字在正文第几行（去掉空格后比）"] == {"春秋季徒步露营的两人组": [3]}, got["正文"]
    assert got["正文"]["字数（整段）"] == count("姐妹们！“最轻松”的一次露营适合春秋季徒步露营的两人组天猫有链接https://lanjing.tmall.com#岚径露营")
    where = [(x["字词"], x["位置"]) for x in got["禁用字词（逐处，含段外）"]]
    assert where == [("第一", "第一个段名之前 第 1 行"), ("最轻", "“正文”段 第 2 行")], where
    assert [(x["网址"], x["位置"]) for x in got["网址（一串连续的英文字母数字符号算一个，逐个列出，含段外）"]] == [
        ("https://lanjing.tmall.com", "“正文”段 第 4 行"), ("www.x.cn", "“合作标注”段 第 2 行")], got
    assert [x["字词"] for x in got["导流词（逐处，含段外）"]] == ["链接", "天猫"], got
    tags = got["话题"]
    assert tags["话题行里的话题（按顺序）"] == ["#岚径露营", "#冬季露营", "#户外"] and tags["个数"] == 3, tags
    assert tags["必带话题在第几个"] == {"#岚径露营": [1], "#睡袋推荐": "没有"}, tags
    assert tags["话题之间没空格的地方"] == ["#岚径露营#冬季露营 #户外"] and len(tags["标题和正文里的“#”"]) == 1, tags
    assert got["合作标注"]["“合作标注”段的内容"] == ["品牌合作", "说明：话题 #睡袋推荐 没放，www.x.cn 也没放。"], got
    assert got["合作标注"]["规定写法出现在哪里"] == ["“合作标注”段 第 1 行"], got
    loose = measure({"reference": ref}, "**标题**\n🌙1200g睡袋\n【正文】\n一行\n话题：\n#岚径露营\n合作标注\n品牌合作")
    assert loose["段名（按顺序）"] == ["标题", "正文", "话题", "合作标注"], loose
    r2 = dict(ref, 交付格式={"段名和顺序": ["## 标题", "## 合作声明", "## 正文", "## 话题"], "合作标注": "只写“本篇为松屿户外合作笔记”",
                               "合作标注的写法": "本篇为松屿户外合作笔记"})
    tail = measure({"reference": r2}, "## 标题\n✨600lm 挂灯\n候选：600lm 挂灯真亮\n\n## 合作声明\n本篇为松屿户外合作笔记\n\n## 正文\n一行"
                                    "\n\n## 话题\n#岚径露营 #户外\n\n说明：话题 2 个（含 #岚径露营），卖点里的“最轻”没照抄。")
    assert tail["话题"]["话题行里的话题（按顺序）"] == ["#岚径露营", "#户外"] and tail["话题"]["个数"] == 2, tail["话题"]
    assert tail["禁用字词（逐处，含段外）"][0]["位置"] == "“话题”段 第 2 行（这一行不以“#”开头，不是话题）", tail
    assert tail["标题"]["标题段的行数"] == 2 and tail["标题"]["标题（标题段第一行，去掉开头的“标题：”）"] == "✨600lm 挂灯", tail
    assert tail["合作标注"]["“合作声明”段的内容"] == ["本篇为松屿户外合作笔记"], tail
    print("ok")
