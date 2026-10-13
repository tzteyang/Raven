"""Generate the 40 deterministic English-listing tasks and their Studio scenario.

Only the standard library is used. These are supplied seller work rules, not a
claim about a marketplace's current policies. Run with: uv run python make.py
"""

import csv
import io
import json
import random
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENARIO = HERE / "wkr-amazon-listing"
RULES = {
    "R1": dict(brand="PawNest", prefix="PN", title=150, bullet=250, places=1, capacity="L", length="cm", mass="kg",
               sections=["Title", "Bullet Points"], separator=": ", bans=["best", "#1", "no. 1", "number one", "guarantee", "guarantees", "guaranteed", "guaranteeing"]),
    "R2": dict(brand="TailHaven", prefix="TH", title=120, bullet=210, places=2, capacity="mL", length="mm", mass="g",
               sections=["Listing Title", "Key Features"], separator=" — ", bans=["ultimate", "#1", "no. 1", "number one", "risk-free", "guarantee", "guarantees", "guaranteed", "guaranteeing"]),
    "R3": dict(brand="WhiskerWay", prefix="WW", title=135, bullet=230, places=2, capacity="L", length="cm", mass="kg",
               sections=["Product Title", "Highlights"], separator=": ", bans=["best", "ultimate", "perfect", "#1", "no. 1", "number one", "guarantee", "guarantees", "guaranteed", "guaranteeing"]),
}
SPELLING = [("colour", "color"), ("colours", "colors"), ("grey", "gray"), ("programme", "program"),
            ("programmes", "programs"), ("customise", "customize"), ("customised", "customized"),
            ("centre", "center"), ("litre", "liter"), ("litres", "liters")]
CERTS = [
    ("FCC", ["FCC", "FCC Part 15", "F.C.C. Part 15"], "FCC Part 15 compliant"),
    ("UL", ["UL", "UL Listed", "U.L. Listed"], "UL Listed"),
    ("ETL", ["ETL", "ETL Listed", "E.T.L. Listed"], "ETL Listed"),
    ("RoHS", ["RoHS", "RoHS 2", "RoHS-2"], "RoHS compliant"),
    ("CE", ["CE", "CE Mark", "CE marked"], "CE marked"),
]
LIMITS = ["For dry kibble only; keep the feeder indoors.",
          "Not for wet food; place the feeder on a level indoor surface.",
          "For dry food only; keep the power connector dry."]


def csv_text(columns, rows):
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    writer.writerows(rows)
    return buffer.getvalue()


def compact(value):
    return format(Decimal(value).normalize(), "f")


def rounded(value, places):
    return f"{Decimal(value).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP):.{places}f}"


def rule_text(key):
    r = RULES[key]
    extra = ("认证记录还要在有效期内：以参数表的‘上架日期’为准，如果有效至日期不早于上架日期，就仍有效；"
             "否则不准写这项认证。有效至当天也有效。日期缺失的也不准写。" if key == "R3" else
             "本批记录的日期都在有效期内，不需要额外筛日期。")
    restriction = ("参数表的‘使用限制’必须原样写在第一条要点里，大小写、空格、标点都不改；不允许用同义句代替。"
                   if key == "R3" else "本规则没有‘使用限制必须原样引用’的要求。")
    return f"""# {r['brand']} · 美国站英文 Listing 工作规则

这是本次卖家的内部工作规范。每次只处理参数表里的目标 SKU，不把它当作其他卖家或平台的通用政策。依据工作目录中的工作规则.md、参数表.csv、认证记录.csv、认证写法.csv、美英拼写.csv、单位换算.csv 和待改草稿.txt 交付英文标题和五条要点。待改草稿只是未经核实的营销草稿；其中与参数表或工作规则冲突的文字要删改，不能当作参数或认证证据。

1. 标题：不超过 {r['title']} 个字符，必须以参数表的品牌开头，并包含目标 SKU 和短语 Automatic Pet Feeder；三者都照参数表/本条的写法原样写，各出现一次。除了这三项外，没有必须塞进标题的参数；正文要点里的必写内容见第 2 条。标题只写一行，不加引号、加粗、编号或 Title: 这类前缀。
2. 商品事实：五条要点合起来必须写全容量、适用干粮粒径范围、每日最多餐数、录音秒数、颜色和供电方式。若参数表里有机身尺寸和净重，还必须写全三边尺寸（顺序为长、宽、高）及净重；若没有，不写尺寸和重量。毛重与包装尺寸只是物流信息，标题和要点里都不写，也不能用来代替净重与机身尺寸。粒径只用 mm，不换算成 inches。参数值必须和表相符，不把‘最多’写成固定餐数；参数表没有的功能不写。具体功能只核对以下闭合词表：Wi-Fi、Bluetooth、app control、camera、dishwasher safe、battery backup；表里列为无的，标题和要点里不出现，否定句里也不提。表外未要求的泛泛形容词不算缺失；禁用词按第 5 条另查。
3. 双单位：要点里的容量一律写 {r['capacity']} 和 cups；机身三边尺寸一律写 {r['length']} 和 inches；净重一律写 {r['mass']} 和 lb。单位大小写照本条写，数值和单位之间留一个半角空格。先把参数换成指定公制单位，再依单位换算.csv 换出美制数值；cups、inches、lb 的每个数都用四舍五入（5 进）保留 {r['places']} 位小数，末尾 0 也保留。公制数值不留多余的尾数 0；公制与美制可以用括号或斜线连接。三边用 x 连接，顺序都是长 x 宽 x 高；三边后共用一个单位（例如 20 x 15 x 30 cm）。标题若写参数也要真实，但标题不强制双单位。粒径、餐数、录音秒数不受双单位与小数位要求约束。
4. 认证依据：认证写法.csv 给出认证项目、常见别名和准许的成句写法。先按目标 SKU 筛认证记录，再把别名映射回认证项目。只有状态是‘已取得’的项目可以写；‘申请中’和‘未取得’都不能写；别的 SKU 即使‘已取得’也不能写。{extra}满足条件的每个项目都必须在要点里按‘准许成句’原样写一次，不能多写其他认证项目、不能把申请中写成已取得。如果没有符合条件的项目，就不写认证名；可以用不含认证名的普通商品事实补足第五条要点。不能用‘not UL Listed’之类否定句提及不准写的认证。认证别名核对时不分大小写，字母数字间的空格、点号和连字符可以不同；用最长别名匹配，同一次提及归为一个认证项目，不把 FCC Part 15 再数成一个 FCC。认证名必须是独立片段，color、schedule 这类普通单词里碰巧含有字母组合不算认证。
5. 禁用与拼写：标题、要点里都不能出现下面这些写法：{'、'.join(r['bans'])}。列表是闭合的，不外推其他词形；纯英文词按完整单词、不分大小写匹配（best 不匹配 bestow）；多词短语中的连续空格视为一个空格，no. 1 中点号后可无空格；#1 不能借 #10 触发。美英拼写.csv 左列的每个英式写法都改成右列对应的美式写法，按完整单词、不分大小写匹配，不扩展表里没有的词形。参数表颜色一栏如果是英式拼写，同样换成表里的美式拼写。
6. 要点：恰好五条，每条占一行并以“- ”开头；内容以 2 到 4 个全大写英文单词构成的短语开头，紧跟“{r['separator']}”再写正文。每条不超过 {r['bullet']} 个字符，开头的大写短语和分隔符算在内，行首“- ”不算。五条的主题和先后可自行安排。{restriction}
7. 计数和交付：标题和每条要点的字母、数字、空格、标点每个都算一个字符，换行不算；Markdown 符号如果写进内容也计数。只交下面两段，段名和顺序照写；每段以 ## 开头。不要写文件，不加代码围栏、开场白、分析、字数统计或结尾说明。标题段只放标题，要点段只放五条要点。交付前后或段间多出的说明只在格式项记一处，说明里的数字、禁用词、认证、拼写不再在内容项重复计数；六条以上要点属于多要点，不把多出来的要点当作说明忽略。

## {r['sections'][0]}
（只写一行英文标题）

## {r['sections'][1]}
（五行英文要点，每行以“- ”开头）
"""


def build(name, group, segment, key, seed):
    rng, r = random.Random(seed), RULES[key]
    edge = segment == "edge"
    sku = f"{r['prefix']}-{seed % 900 + 100}"
    liters = rng.choice(["2.5", "3", "3.5", "4", "4.5", "5", "5.5", "6"])
    meals, seconds = rng.choice([4, 5, 6, 8]), rng.choice([6, 8, 10, 12])
    low, high = rng.choice([(2, 10), (2, 12), (3, 12), (4, 14), (3, 15)])
    color = rng.choice(["white", "black", "grey", "blue"])
    power = rng.choice(["USB powered", "DC adapter powered"])
    raw_cap_unit = "mL" if (edge and key != "R2") or (not edge and key == "R2") else "L"
    raw_cap = compact(Decimal(liters) * (1000 if raw_cap_unit == "mL" else 1))
    params = [("品牌", r["brand"]), ("目标 SKU", sku), ("上架日期", "2026-10-11"),
              ("容量", f"{raw_cap} {raw_cap_unit}"), ("适用干粮粒径", f"{low}-{high} mm"),
              ("每日最多餐数", str(meals)), ("录音秒数", str(seconds)), ("颜色", color), ("供电方式", power)]
    dims_cm, net_kg = None, None
    if edge:
        dims_cm = [Decimal(rng.randrange(a, b)) / 10 for a, b in ((180, 285), (140, 240), (280, 380))]
        net_kg = Decimal(rng.randrange(110, 230)) / 100
        source_mm = seed % 2 == 0
        source_g = seed % 3 != 0
        params += [("机身尺寸（长 x 宽 x 高）", " x ".join(compact(n * (10 if source_mm else 1)) for n in dims_cm) + (" mm" if source_mm else " cm")),
                   ("包装尺寸（长 x 宽 x 高）", " x ".join(compact(n + 4) for n in dims_cm) + " cm"),
                   ("净重", compact(net_kg * (1000 if source_g else 1)) + (" g" if source_g else " kg")),
                   ("毛重", compact(net_kg + Decimal("0.35")) + " kg")]
    feature_rows = [(feature, "无") for feature in ["Wi-Fi", "Bluetooth", "app control", "camera", "dishwasher safe", "battery backup"]]
    params += feature_rows
    limit = LIMITS[(seed + 1) % len(LIMITS)] if key == "R3" else None
    if limit:
        params.append(("使用限制", limit))

    current = []
    for index, (family, aliases, phrase) in enumerate(CERTS):
        # Several states remain present in every question, and all-approved is impossible.
        status = ["已取得", "申请中", "未取得"][(index + seed) % 3]
        date = "2027-10-11"
        if key == "R3":
            date = ["2026-10-10", "2026-10-11", "2026-10-12", "", "2027-06-30"][(index + seed) % 5]
        shown = aliases[(seed + index) % len(aliases)] if edge else aliases[0]
        current.append((sku, shown, status, date))
    # R3 explicitly exercises an expired, a same-day valid, and a missing-date record.
    if key == "R3":
        current[0] = (sku, current[0][1], "已取得", ["2026-10-10", "2026-10-11"][seed % 2])
        current[3] = (sku, current[3][1], "已取得", "2026-10-11")
        current[4] = (sku, current[4][1], "已取得", "")
    records = list(current)
    if edge:
        records += [(f"{r['prefix']}-OTHER", aliases[-1], "已取得", "2028-12-31") for _, aliases, _ in CERTS]
        rng.shuffle(records)
    allowed = [family for (family, _, _), (_, _, status, until) in zip(CERTS, current)
               if status == "已取得" and (key != "R3" or bool(until) and until >= "2026-10-11")]
    forbidden = [family for family, _, _ in CERTS if family not in allowed]
    phrases = [phrase for family, _, phrase in CERTS if family in allowed]
    output_cap = Decimal(liters) * (1000 if r["capacity"] == "mL" else 1)
    facts = {"品牌": r["brand"], "SKU": sku, "容量": f"{compact(output_cap)} {r['capacity']}",
             "粒径": f"{low}-{high} mm", "每日最多餐数": meals, "录音秒数": seconds,
             "颜色": dict(SPELLING).get(color, color), "供电": power, "机身尺寸": None, "净重": None}
    converted = {"容量": rounded(Decimal(liters) * 1000 / Decimal("236.588"), r["places"]) + " cups",
                 "机身尺寸": None, "净重": None}
    if edge:
        facts["机身尺寸"] = " x ".join(compact(n * (10 if r["length"] == "mm" else 1)) for n in dims_cm) + f" {r['length']}"
        facts["净重"] = compact(net_kg * (1000 if r["mass"] == "g" else 1)) + f" {r['mass']}"
        converted["机身尺寸"] = " x ".join(rounded(n / Decimal("2.54"), r["places"]) for n in dims_cm) + " inches"
        converted["净重"] = rounded(net_kg / Decimal("0.45359237"), r["places"]) + " lb"
        # Logistics values really differ; the trap is not a cosmetic duplicate.
        assert net_kg != net_kg + Decimal("0.35") and len(set(dims_cm)) == 3
    ref = {"标题": {"上限": r["title"], "必含一次": [r["brand"], sku, "Automatic Pet Feeder"], "开头": r["brand"]},
           "商品事实": facts, "美制换算": converted, "美制小数位": r["places"],
           "认证": {"必须原样写的成句": phrases, "允许项目": allowed, "不能提及的项目": forbidden,
                    "逐条来源": [{"SKU": row[0], "认证写法": row[1], "状态": row[2], "有效至": row[3]} for row in records]},
           "禁用写法": r["bans"], "拼写": dict(SPELLING),
           "格式": {"段名": r["sections"], "要点条数": 5, "每条上限": r["bullet"], "大写开头分隔符": r["separator"]},
           "第一条要点必须原样引用": limit or "不适用", "不得写的功能": [n for n, _ in feature_rows],
           "物流口径": "只写机身三边和净重，不写包装尺寸或毛重" if edge else "未提供尺寸和重量，不得补造"}
    size_words = f"{facts['容量']}, {facts['颜色'].title()} Color, Dry Food Dispenser with Timed Meals and Voice Recording"
    title = f"{r['brand']} {sku} Automatic Pet Feeder, {size_words}"
    if len(title) > r["title"]:
        title = title.replace(" with Timed Meals and Voice Recording", " with Timed Meals")
    assert len(title) <= r["title"], (name, title)
    first = f"Stores {facts['容量']} ({converted['容量']}) of dry food."
    if limit:
        first += " " + limit
    bullets = [("FOOD CAPACITY", first),
               ("KIBBLE AND MEALS", f"For dry kibble {facts['粒径']}; schedule up to {meals} meals per day."),
               ("VOICE MESSAGE", f"Record your {seconds}-second message; {facts['颜色']} color; {power}."),
               ("BODY AND WEIGHT", f"Dimensions (L x W x H): {facts['机身尺寸']} ({converted['机身尺寸']}); net weight: {facts['净重']} ({converted['净重']}).")
               if edge else ("DAILY SCHEDULE", f"Program up to {meals} meals per day for dry kibble {facts['粒径']}."),
               ("DOCUMENTED DETAILS", "; ".join(phrases) + ".") if phrases else ("FOOD TYPE", f"Use with dry kibble {facts['粒径']}.")]
    lines = [header + r["separator"] + body for header, body in bullets]
    assert all(len(line) <= r["bullet"] for line in lines), (name, [(len(l), l) for l in lines])
    example = f"## {r['sections'][0]}\n{title}\n\n## {r['sections'][1]}\n" + "\n".join("- " + line for line in lines) + "\n"
    ref["示例交付"] = example
    ref["示例字符数"] = {"标题": len(title), "要点": [len(line) for line in lines]}
    files = {
        "工作规则.md": rule_text(key), "参数表.csv": csv_text(["字段", "值"], params),
        "认证记录.csv": csv_text(["SKU", "认证名称", "状态", "有效至"], records),
        "认证写法.csv": csv_text(["项目", "常见别名（分号隔开）", "准许成句"], [(f, ";".join(a), p) for f, a, p in CERTS]),
        "美英拼写.csv": csv_text(["英式", "美式"], SPELLING),
        "单位换算.csv": csv_text(["关系", "数值"], [("1 L 的 mL 数", "1000"), ("1 cup 的 mL 数", "236.588"),
                                                      ("1 inch 的 cm 数", "2.54"), ("1 cm 的 mm 数", "10"),
                                                      ("1 lb 的 kg 数", "0.45359237"), ("1 kg 的 g 数", "1000")]),
        "待改草稿.txt": f"{r['brand']} {sku}: The {'ultimate' if key == 'R2' else 'BEST'} Automatic Pet Feeder, {raw_cap} {raw_cap_unit}, "
                      + f"Guaranteed Convenience, UL Listed, {color} colour, customised programme, Wi-Fi and camera control. "
                      + ("No.1 food dispenser with battery backup. Use shipping weight and package size for the product listing.\n" if edge else "\n"),
    }
    text = (f"{r['brand']} 要为 {sku} 上架美国站英文 Listing，帮我把营销草稿改成可直接粘贴的标题和五条要点。"
            + ("尽可能在标题中放进有用的搜索词。" if edge else "")
            + "\n\n工作目录里有工作规则.md、参数表.csv、认证记录.csv、认证写法.csv、美英拼写.csv、单位换算.csv 和待改草稿.txt。请以当次工作规则和已核实材料为准。")
    return dict(name=name, group=group, segment=segment, rules=key, text=text, files=files, reference=ref)


CRITERIA = [
    {"id": "AL-title", "severity": "standard", "check": "只判标题本身：字符数不超过当题上限，以品牌原样开头，品牌、目标 SKU、Automatic Pet Feeder 各按规定写法出现一次。每个独立不符记一处。标题完全缺失只在本项记一处，不因缺失再在格式项扣一次；段名或标题前缀/引号/加粗归格式项。标题中的参数真假归 AL-facts，认证/禁词/拼写归 AL-safe。交付以外说明中的文字不计入标题。"},
    {"id": "AL-facts", "severity": "standard", "check": "只判标题和要点中的商品事实：要点合起来须覆盖参考答案商品事实里的容量、粒径、每日最多餐数、录音秒数、颜色、供电，有机身尺寸及净重时还要覆盖它们；公制单位/数值、干粮范围、最多含义须对；不能用包装/毛重替换，也不能编造。六个闭合功能词中未提供的不能写。R3 第一条要点须原样包含使用限制，缺失或未照写只记一处。不要求与示例措辞相同、不要扩展闭合功能表。每个参数或功能的独立错误记一处，同一错误值重复写只记一处。颜色使用英式拼写只归 AL-safe；同一参数用了错误的输入数导致公制/美制一起错，只在本项记一处；公制对、美制换算或格式错才归 AL-units。整份交付缺失时只在 AL-title 记一处，其他项不连带累计。"},
    {"id": "AL-units", "severity": "standard", "check": "只判要点中的双单位：容量 cups，有尺寸的三边 inches，有净重的 lb，均须按当题表算对且固定规定小数位，数值和单位间空一格，三边按长宽高用 x 连接并共用单位。没有尺寸/净重时对应子项不适用。每个参数（容量/三边尺寸/净重）最多记一处，三边错多处也只记一处；美制漏写、取舍或格式错在本项。公制事实错导致美制一起错不重复扣，归 AL-facts。公制和美制都没写只归 AL-facts。标题不强制双单位；粒径必须只用 mm，不得额外转 inches，若转换在本项记一处。交付之外的说明不判。"},
    {"id": "AL-safe", "severity": "red_line", "check": "只判标题和要点中的认证、闭合禁用词和美英拼写表。认证只能按目标 SKU、状态以及 R3 日期口径筛选；参考答案每个允许项目须在要点按准许成句原样出现一次，其他项目完全不提。一个认证项目有任何问题最多记一处，同项目别名/重复提及不另数；认证换个说法虽真假对但没原样也在本项。禁用词按规则的完整词与短语匹配逐处计数，不扩展未列词形；英式拼写按表逐处计数，不把普通词内部字母当认证（color/schedule 都正常）。禁用或认证出现在否定句也算。前后说明不纳入，不因内容缺失而重复扣格式。"},
    {"id": "AL-format", "severity": "standard", "check": "按当题规定只交两段，段名/顺序、标题一行、五条要点各占一行且以“- ”开头、每条 2 到 4 个全大写英文单词开头后接规定分隔符、各条不超字符上限。段名/顺序错误合计一处，要点条数错误合计一处，每条前缀/开头/分隔符视作同一处格式错误，每条超长各一处；标题引号/加粗/Title: 前缀视作一处。交付前后/段间多出来的说明（包括文件/代码围栏）合计只记一处，说明里的内容不在其他项重复扣；超出五条的实际要点仍要检查事实。漏掉整个标题只在 AL-title 记一处，整体无产出同理；缺失要点造成的格式与内容缺失只在格式项记一处，避免连锁计数。除 R3 使用限制位置以外，五条主题及顺序自由。"},
]


def write_json(path, content):
    path.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n")


def main():
    (HERE / "rules").mkdir(parents=True, exist_ok=True)
    (SCENARIO / "personas").mkdir(parents=True, exist_ok=True)
    for key in RULES:
        (HERE / "rules" / f"{key}.md").write_text(rule_text(key))
    questions = []
    for letter, group, size, offset in [("t", "train", 20, 1000), ("x", "same", 10, 2000), ("y", "new", 10, 3000)]:
        for number in range(1, size + 1):
            key = "R3" if letter == "y" else "R1" if number % 2 else "R2"
            segment = "common" if number <= size // 2 else "edge"
            questions.append(build(f"{letter}{number:02d}", group, segment, key, offset + number))
    assert len({q['reference']['商品事实']['SKU'] for q in questions}) == 40
    write_json(HERE / "questions.json", questions)
    write_json(HERE / "scripts.json", [dict(name=q["name"], title=f"{q['name']} {q['reference']['商品事实']['SKU']} 英文 Listing", exam=q["group"] != "train",
                                             steps=[dict(text=q["text"], files=q["files"])]) for q in questions])
    write_json(SCENARIO / "scenario.json", dict(initial=[], criteria=CRITERIA))
    write_json(SCENARIO / "contract.json", dict(checks={c["id"]: dict(visibility=["counterpart", "analyst", "curator"]) for c in CRITERIA}))
    (SCENARIO / "profile.md").write_text("你是跨境电商的英文 Listing 运营。每次根据工作目录中的工作规则、SKU 参数、认证记录、拼写对照和单位换算表，把营销草稿改成可直接使用的英文标题和要点。只采用当次材料里有依据的参数与认证，遵守卖家的长度、单位、拼写和交付格式。\n")
    (SCENARIO / "onboarding.md").write_text("以后每次新品任务都会带上这次适用的工作规则和完整数据。不同卖家的标题上限、单位写法、换算精度和认证核对口径可能不同，以当次文件为准。\n")
    (SCENARIO / "personas" / "operator.md").write_text("卖家运营主管提供一个目标 SKU 的材料和未经核实的营销草稿，请你按本次工作规则交付英文 Listing。材料由脚本随题提供。\n")
    live = json.loads((HERE.parent / "refund-desk" / "live.json").read_text())
    live.update(root="../../../../runs/experts/amazon-listing", scenario="wkr-amazon-listing")
    write_json(HERE / "live.json", live)
    write_json(HERE / "manifest.json", {"name": "亚马逊英文 Listing", "description": "按每次工作规则把商品参数和认证材料写成英文标题与要点，核对认证来源和日期，换算公制/美制单位，控制长度、禁用措辞和美式拼写。", "owns": "负责有材料依据的英文商品 Listing。"})
    print(f"generated {len(questions)} questions; R1/R2 train and same, R3 new")


if __name__ == "__main__":
    main()
