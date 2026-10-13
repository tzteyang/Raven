"""自检：另写一遍算法，只读员工看到的文件（工作规则、参数表、类目必含词、禁用词表、品牌名单）和题面，逐题重算：
标题上限和数法（从规则原文读）、示例标题的字符数和必含词次数、每个参数在卖点里要写出的值（删掉夹带的禁用词和品牌名）、参数表里有没有
的功能词、参数里夹带的禁用词和品牌名、禁用词表里的变体写法、必含词在参数表里的不同写法、标题能用的数字；再核对示例交付逐条合规、
边界题的陷阱确实存在，并拿 measure.py 量示例，看测量值和这里算的一致。和参考答案逐题比对。

  python3 check.py
"""

import json
import re
from pathlib import Path

from measure import RULESETS, measure

HERE = Path(__file__).resolve().parent
WIDE = {0xFF01 + i: 0x21 + i for i in range(94)} | {0x3000: 0x20}
PARAMS_KEY = "各参数（卖点里要写出“卖点里要写出的值”；值里的空格可以去掉，全角可以改半角）"
EXAMPLE_KEY = "示例交付（一份完全符合规则的写法；员工的标题和卖点可以和它不同，只要符合规则）"


def half(text: str) -> str:
    return text.translate(WIDE)


def flat(text: str) -> str:
    return "".join(half(text).lower().split())


def count_chars(text: str, scheme: str) -> int:
    total = 0
    for ch in text:
        if scheme == "byte":
            total += 1 if 32 <= ord(ch) <= 126 else 2
        elif ch.isspace():
            continue
        else:
            total += 2 if re.match(r"[㐀-䶿一-鿿]", ch) else 1
    return total


def digits(text: str) -> list[str]:
    return re.findall(r"\d+(?:\.\d+)?", half(text), re.ASCII)


def contains(text: str, word: str) -> bool:
    return bool(flat(word)) and flat(word) in flat(text)


def remove_words(value: str, words: list[str]) -> str:
    chars = [(i, half(ch).lower()) for i, ch in enumerate(value) if not ch.isspace()]
    joined = "".join(c for _, c in chars)
    gone = set()
    for word in words:
        key = flat(word)
        for m in re.finditer(re.escape(key), joined) if key else ():
            gone.update(chars[k][0] for k in range(m.start(), m.end()))
    return " ".join("".join(ch for i, ch in enumerate(value) if i not in gone).split())


def read_rules(text: str) -> dict:
    limits = re.search(r"(?:不少于 (\d+) 个字符，也)?不超过 (\d+) 个字符。字符这样数", text)
    sections = re.findall(r"^## (.+)$", text, re.M)
    return {
        "min": int(limits.group(1)) if limits.group(1) else None, "max": int(limits.group(2)),
        "scheme": "hanzi" if "每个汉字算 2 个；空格不算" in text else "byte",
        "count": int(re.search(r"写 (\d+) 条，每条写参数表里的一个参数", text).group(1)),
        "functions": re.search(r"参数表里没有的，\S+?都不能出现：(.+?)。功能词表里没有的词", text).group(1).split("、"),
        "title": sections[0], "points": sections[1],
        "prefix": (m.group(1) if (m := re.search(r"必须以我们的品牌名“(.+?)”开头", text)) else None),
        "point_max": (int(m.group(1)) if (m := re.search(r"每条卖点不超过 (\d+) 个字符", text)) else None),
        "label": "每条卖点以“【参数名】”开头" in text,
        "numbered": "依次以“1. ”" in text,
    }


def main() -> None:
    wrong = []
    for q in json.loads((HERE / "questions.json").read_text()):
        name, files, ref = q["name"], q["files"], q["reference"]
        rules = read_rules(files["工作规则.md"])
        mine = RULESETS[q["rules"]]
        for key in ("min", "max", "scheme", "count", "title", "points", "prefix", "point_max"):
            if mine[key] != rules[key]:
                wrong.append((name, "measure.py RULESETS", key, mine[key], rules[key]))
        rows = [tuple(c.strip() for c in line.strip().strip("|").split("|"))
                for line in files["参数表.md"].splitlines() if line.startswith("| ") and not line.startswith("| 参数名")]
        musts = [line[2:] for line in files["类目必含词.md"].splitlines() if line.startswith("- ")]
        banned = [line[2:] for line in files["禁用词表.md"].splitlines() if line.startswith("- ")]
        brands = [n for line in files["品牌名单.md"].splitlines()[6:] for n in line.strip("| \n").split(" | ")]
        if len(banned) != int(re.search(r"共 (\d+) 个词", files["禁用词表.md"]).group(1)):
            wrong.append((name, "banned count"))
        names = banned + brands
        whole = " ".join(f"{p} {v}" for p, v in rows)
        present = [w for w in rules["functions"] if contains(whole, w)]
        absent = [w for w in rules["functions"] if w not in present]
        clean = {p: remove_words(v, names) for p, v in rows}
        pool = {n for _, v in rows for n in digits(v)}
        # 参考答案里的关键值
        listed = {item["参数名"]: item for item in ref["卖点要求"][PARAMS_KEY]}
        if list(listed) != [p for p, _ in rows]:
            wrong.append((name, "params", list(listed)))
        for p, v in rows:
            if listed[p]["卖点里要写出的值"] != clean[p] or listed[p]["参数表里的值"] != v:
                wrong.append((name, "clean value", p, clean[p], listed[p]["卖点里要写出的值"]))
        if ref["功能词"]["参数表里有的（可以写）"] != (present or "无") or ref["功能词"]["参数表里没有的（标题和卖点都不能写）"] != absent:
            wrong.append((name, "functions", present, absent))
        carried = [f"{p}：{'、'.join(w for w in names if contains(p + ' ' + v, w))}" for p, v in rows
                   if any(contains(p + " " + v, w) for w in names)]
        if carried != ref["参数表里夹带的禁用词和品牌名"]:
            wrong.append((name, "carried", carried, ref["参数表里夹带的禁用词和品牌名"]))
        odd = {w: flat(w) for w in banned if " " in w or re.search(r"[！-～]", w)}
        if odd != (ref["禁用词表里写法特殊的词（比对时先规范化）"] if odd else odd):
            wrong.append((name, "variants", odd))
        title_ref = ref["商品名称要求" if q["rules"] == "R2" else "标题要求"]
        differ = {w: [f"{p}写作“{v}”" for p, v in rows if contains(v, w) and w not in v] for w in musts}
        differ = {w: x for w, x in differ.items() if x}
        if (differ or "无") != title_ref["必含词在参数表里写法不同的（标题里要照必含词表写）"]:
            wrong.append((name, "must differ", differ))
        if title_ref["必含词（照这个写法原样写，各只出现一次）"] != musts:
            wrong.append((name, "musts"))
        if sorted(title_ref["标题里能用的数字（参数表参数值里的全部数字）"], key=float) != sorted(pool, key=float):
            wrong.append((name, "number pool", sorted(pool)))
        # 示例交付逐条合规
        example = ref[EXAMPLE_KEY]
        lines = [line for line in example.splitlines() if line.strip()]
        if lines[0] != f"## {rules['title']}" or lines[2] != f"## {rules['points']}" or len(lines) != 3 + rules["count"]:
            wrong.append((name, "example layout", lines[:3]))
        title, points = lines[1], lines[3:]
        size = count_chars(title, rules["scheme"])
        if size != ref["示例标题字符数"]["按本题规则的字符数"] or size > rules["max"] or (rules["min"] and size < rules["min"]):
            wrong.append((name, "title size", size))
        for w in musts:
            if title.count(w) != 1 or flat(title).count(flat(w)) != 1:
                wrong.append((name, "must count", w))
        if rules["prefix"] and not title.startswith(rules["prefix"]):
            wrong.append((name, "prefix"))
        if any(contains(title, w) for w in names + absent) or not set(digits(title)) <= pool:
            wrong.append((name, "title words or numbers"))
        used = []
        for i, line in enumerate(points, 1):
            if rules["numbered"]:
                head = f"{i}. "
            elif rules["label"]:
                head = re.match(r"【[^】]+】", line).group(0)
            else:
                head = f"卖点{'一二三四五'[i - 1]}："
            body = line[len(head):] if line.startswith(head) else None
            if body is None:
                wrong.append((name, "point head", line))
                continue
            hit = [p for p, _ in rows if "".join(half(clean[p]).split()) in "".join(half(body).split())]
            if len(hit) != 1:
                wrong.append((name, "point params", line, hit))
                continue
            used.append(hit[0])
            value = dict(rows)[hit[0]]
            if rules["label"] and (head != f"【{hit[0]}】" or any(contains(hit[0], w) for w in names)):
                wrong.append((name, "label", line))
            if any(contains(line, w) for w in names + absent) or not set(digits(body)) <= set(digits(value)):
                wrong.append((name, "point words or numbers", line))
            if rules["point_max"] and count_chars(body, rules["scheme"]) > rules["point_max"]:
                wrong.append((name, "point size", line))
        if len(set(used)) != len(used) or used != ref["示例卖点对应的参数"]:
            wrong.append((name, "point params differ", used))
        # 陷阱确实存在
        if sum(any(contains(v, w) for w in names) for _, v in rows) < 2:
            wrong.append((name, "value traps"))
        if q["segment"] == "edge":
            english = [v for _, v in rows if any(contains(v, en) for en in brands[1::2]) and re.search(r"[A-Za-zＡ-ｚ]", v)]
            if not ("ＴＯＰ１" in banned and "第 一" in banned and english and rows[0][0] == "型号" and " " in rows[0][1]
                    and any(re.search(r"[０-ｚ]", v) for _, v in rows)):
                wrong.append((name, "edge traps"))
        elif any(re.search(r"[！-～]", p + v) for p, v in rows) or rows[0][0] == "型号":
            wrong.append((name, "common has full-width or model"))
        # measure.py 量示例，结果和这里算的一致
        got = measure(q, example)
        if got["标题"]["按本题规则的字符数"] != size or got["禁用词和品牌名（规范化后命中，只量交付本身）"]:
            wrong.append((name, "measure title/hits", got["标题"]["按本题规则的字符数"]))
        if [row["写出了值的参数"] for row in got["卖点段各行"]] != [[p] for p in used]:
            wrong.append((name, "measure points", [row["写出了值的参数"] for row in got["卖点段各行"]]))
        if not all(row["行首符合本规则的卖点写法"] for row in got["卖点段各行"]):
            wrong.append((name, "measure heads"))
    print("mismatches:", wrong or "none")
    assert not wrong


if __name__ == "__main__":
    main()
