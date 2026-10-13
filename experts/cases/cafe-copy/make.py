"""咖啡新品介绍：三套工作规则、40 道题（20 培养 + 10 道同规则考试 + 10 道换规则考试）、参考答案和 Studio 场景包。

  python3 make.py

依据《专家自进化》5.1 的案例改写成「工作规则随题交给员工」：三家咖啡品牌给新批次写一段官网和公众号通用的产品介绍，
口径不同（自称、禁用词、风味词能不能带后缀、字数区间、每段句数、冲煮建议的写法）。培养题和同规则考试题用 R1（山隅）、
R2（北窗）交替，换规则考试题全用员工从没见过的 R3（林间：风味栏的词要写全、按烘焙度选手冲或冷萃）。每题一张杯测表按种子
生成：常见题的风味词没有容易写岔的近亲词、冲煮参数是品牌常用的那组；边界题的风味词都有近亲词（蜜桃—水蜜桃、茉莉—
茉莉花、红茶—伯爵红茶……）、备注里提到风味栏没有的词、冲煮参数换成这一批专门的。参考答案写出能写和不能写的风味词、
冲煮建议原句、事实项，并附一份照规则写的示例（生成时用和 measure.py 同样的口径校验示例合规）。check.py 只读员工看到的
文件另算一遍。
"""

import json
import random
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENARIO = HERE / "wkr-cafe-copy"

WHEEL = [
    ("花香", ["茉莉", "茉莉花", "玫瑰", "橙花", "洋甘菊", "桂花"]),
    ("桃杏", ["蜜桃", "水蜜桃", "白桃", "黄桃", "杏桃"]),
    ("柑橘", ["柠檬", "青柠", "柑橘", "橘子", "葡萄柚"]),
    ("莓果", ["莓果", "草莓", "蓝莓", "树莓", "黑醋栗", "樱桃"]),
    ("热带水果", ["荔枝", "芒果", "菠萝", "百香果"]),
    ("其他水果", ["葡萄", "青提", "苹果", "青苹果", "西洋梨", "李子", "西梅"]),
    ("甜感", ["蜂蜜", "焦糖", "红糖", "黑糖", "枫糖", "太妃糖", "蔗糖"]),
    ("坚果可可", ["杏仁", "榛果", "花生", "可可", "巧克力", "黑巧克力", "牛奶巧克力"]),
    ("茶与香料", ["红茶", "伯爵红茶", "乌龙", "绿茶", "肉桂", "丁香", "雪松"]),
    ("其他", ["奶油", "黄油", "朗姆酒", "红酒"]),
]
WORDS = [w for _, ws in WHEEL for w in ws]
# 边界题用的风味词：每个都有容易写岔的近亲词（写成近亲词就是写了总表里的另一个词）
TRAPS = {"蜜桃": ["水蜜桃", "白桃", "黄桃"], "茉莉": ["茉莉花"], "柠檬": ["青柠"], "莓果": ["草莓", "蓝莓", "树莓"],
         "葡萄": ["葡萄柚", "青提"], "苹果": ["青苹果"], "红茶": ["伯爵红茶"], "可可": ["巧克力", "黑巧克力"]}
PLAIN = ["玫瑰", "橙花", "洋甘菊", "桂花", "杏桃", "柑橘", "黑醋栗", "樱桃", "芒果", "百香果", "西洋梨", "李子", "西梅",
         "蜂蜜", "焦糖", "红糖", "枫糖", "蔗糖", "杏仁", "榛果", "乌龙", "绿茶", "肉桂", "雪松", "奶油", "红酒"]
ORIGINS = ["云南保山", "云南普洱", "云南临沧", "云南德宏", "埃塞俄比亚耶加雪菲", "埃塞俄比亚古吉", "肯尼亚涅里",
           "哥伦比亚慧兰", "巴拿马波奎特", "危地马拉安提瓜", "哥斯达黎加塔拉珠", "卢旺达尼亚玛加贝"]
PROCESSES = ["日晒", "水洗", "蜜处理", "厌氧日晒", "厌氧水洗"]
ROASTS = ["浅烘", "中浅烘", "中烘", "中深烘"]
GRINDS = ["中细", "中等", "中粗"]

RULES = {
    "R1": {
        "brand": "山隅咖啡", "self": "我们", "not_self": ["本品牌"], "banned": ["极致", "匠心", "顶级", "赋能", "甄选"],
        "suffix": "allowed", "cover": False, "range": (180, 220), "sentences": 3, "brew": (15, 92, "中细"),
        "text": """# 山隅咖啡 · 产品文案工作规则

1. 自称用“我们”，全文至少用一次；不用“本品牌”。
2. 不用“极致”“匠心”“顶级”“赋能”“甄选”这五个词。
3. 风味只用这一批杯测表“风味”栏里的词，不自己加：写到《风味词总表》里的词，必须是风味栏里有的。风味栏的词原样写，后面可以紧跟“香”“味”“调”中的一个字（例如“茉莉香”“蜜桃味”）。
4. 全文 180 到 220 字；一行算一段，每段不超过 3 句。
5. 最后一句写冲煮建议，写成“冲煮建议：粉水比 1:X，水温 Y°C。”，X、Y 用这一批杯测表里的数；这一句后面不再写别的（不喊口号、不加话题）。
6. 产地、处理法、海拔、烘焙度四项都要写到，内容和杯测表一致；文中的阿拉伯数字都要能在杯测表里找到（不写评分、产量、价格这类杯测表里没有的数）。

补充口径：

- 字数按字符算，标点算，空格和换行不算；句子以“。”“！”“？”结尾算一句，一段最后没有这三个标点的那部分也算一句。
- 认风味词按《风味词总表》里最长的那个词认：写“水蜜桃”算写了“水蜜桃”，不算“蜜桃”；写“茉莉花香”算写了“茉莉花”。所以风味栏只有“蜜桃”时，“水蜜桃”“白桃”都不能写；只有“茉莉”时，“茉莉花”不能写。
- 风味只看杯测表的“风味”栏；“备注”里提到的词不算风味栏的词，不能写。
- 只出现在总表外的说法（例如“甜感”“酸质”“花香”“果香”）不算风味词，可以写。
- 只交这段介绍本身，前后不加标题、说明或别的文字。
""",
    },
    "R2": {
        "brand": "北窗咖啡", "self": "北窗", "not_self": ["我们", "本品牌"], "banned": ["完美", "天花板", "必喝", "神级", "爆款"],
        "suffix": "none", "cover": False, "range": (150, 190), "sentences": 2, "brew": (16, 90, "中等"),
        "text": """# 北窗咖啡 · 产品文案工作规则

1. 自称用“北窗”（例如“北窗这次带来……”），全文至少用一次；不用“我们”“本品牌”。
2. 不用“完美”“天花板”“必喝”“神级”“爆款”这五个词。
3. 风味只用这一批杯测表“风味”栏里的词，不自己加：写到《风味词总表》里的词，必须是风味栏里有的。风味栏的词原样写，后面不能紧跟“香”“味”“调”“感”这四个字（写“蜜桃的甜感”可以，写“蜜桃香”“蜜桃感”不行）。
4. 全文 150 到 190 字；一行算一段，每段不超过 2 句。
5. 最后一行只写冲煮参数，写成“粉水比 1:X ／ 水温 Y°C ／ 研磨度 Z”，三项都用这一批杯测表里的；这一行后面不再写别的。
6. 产地、处理法、海拔、烘焙度四项都要写到，内容和杯测表一致；文中的阿拉伯数字都要能在杯测表里找到（不写评分、产量、价格这类杯测表里没有的数）。

补充口径：

- 字数按字符算，标点算，空格和换行不算；句子以“。”“！”“？”结尾算一句，一段最后没有这三个标点的那部分也算一句。
- 认风味词按《风味词总表》里最长的那个词认：写“水蜜桃”算写了“水蜜桃”，不算“蜜桃”；写“伯爵红茶”算写了“伯爵红茶”，不算“红茶”。
- 风味只看杯测表的“风味”栏；“备注”里提到的词不算风味栏的词，不能写。
- 只出现在总表外的说法（例如“甜感”“酸质”“花香”“果香”）不算风味词，可以写。
- 只交这段介绍本身，前后不加标题、说明或别的文字。
""",
    },
    "R3": {
        "brand": "林间咖啡", "self": "我们", "not_self": ["本店", "本品牌", "小编"], "banned": ["极致", "臻选", "顶配", "惊艳", "治愈"],
        "suffix": "allowed", "cover": True, "range": (200, 260), "sentences": 3, "brew": (15, 93, "中细"),
        "text": """# 林间咖啡 · 产品文案工作规则

1. 自称用“我们”，全文至少用一次；不用“本店”“本品牌”“小编”。
2. 不用“极致”“臻选”“顶配”“惊艳”“治愈”这五个词。
3. 风味只用这一批杯测表“风味”栏里的词，不自己加：写到《风味词总表》里的词，必须是风味栏里有的；风味栏里的词要全部写到。风味栏的词原样写，后面可以紧跟“香”“味”“调”中的一个字（例如“茉莉香”“蜜桃味”）。
4. 全文 200 到 260 字；一行算一段，每段不超过 3 句。
5. 最后一句写冲煮建议，按杯测表的烘焙度选方法：浅烘、中浅烘写手冲，写成“冲煮建议（手冲）：粉水比 1:X，水温 Y°C。”；中烘、中深烘写冷萃，写成“冲煮建议（冷萃）：粉水比 1:X，冷藏浸泡 Z 小时。”。数用杯测表里对应那种方法的；这一句后面不再写别的。
6. 产地、处理法、海拔、烘焙度四项都要写到，内容和杯测表一致；文中的阿拉伯数字都要能在杯测表里找到（不写评分、产量、价格这类杯测表里没有的数）。

补充口径：

- 字数按字符算，标点算，空格和换行不算；句子以“。”“！”“？”结尾算一句，一段最后没有这三个标点的那部分也算一句。
- 认风味词按《风味词总表》里最长的那个词认：写“水蜜桃”算写了“水蜜桃”，不算“蜜桃”；写“茉莉花香”算写了“茉莉花”。所以风味栏只有“蜜桃”时，“水蜜桃”“白桃”都不能写；只有“茉莉”时，“茉莉花”不能写。
- 风味只看杯测表的“风味”栏；“备注”里提到的词不算风味栏的词，不能写。
- 只出现在总表外的说法（例如“甜感”“酸质”“花香”“果香”）不算风味词，可以写。
- 只交这段介绍本身，前后不加标题、说明或别的文字。
""",
    },
}

SPECS = []
for i in range(1, 21):
    SPECS.append((f"t{i:02d}", "train", "edge" if i > 10 else "common", "R1" if i % 2 else "R2"))
for i in range(1, 11):
    SPECS.append((f"x{i:02d}", "same", "edge" if i > 5 else "common", "R1" if i % 2 else "R2"))
for i in range(1, 11):
    SPECS.append((f"y{i:02d}", "new", "edge" if i > 5 else "common", "R3"))

TASK = (
    "你是咖啡豆品牌的文案，负责给每个新批次写一段官网和公众号通用的产品介绍。工作目录里有这次适用的文案工作规则、这一批的"
    "杯测表和风味词总表。按这次给的工作规则写出这段介绍，写完直接上官网和公众号。只输出这段介绍本身。"
)
ONBOARDING = "以后每个新批次的产品介绍，我都会把这次适用的文案工作规则、这一批的杯测表和风味词总表一起发给你。不同品牌的要求不一样，以当次给的为准。"
CRITERIA = [
    ("F-flavor", "red_line",
     "风味词：介绍本身里写到的《风味词总表》里的词（按总表里最长的词认，测量值已逐个列出），都必须在这一批杯测表“风味”栏里；"
     "写了栏外的词（包括备注里提到的词、写成总表里的近亲词）每个记一处。规则不许风味词后面紧跟某些字的（例如“蜜桃香”），"
     "每处记一处；规则要求风味栏的词全部写到的，漏一个记一处。介绍前后多出来的说明文字里提到的词不在这一项记（归 F-shape）。"),
    ("F-voice", "standard",
     "自称和禁用词：介绍本身里按规则用指定的自称且至少一次，不出现规则不许的自称；规则列的禁用词一个都不出现。每处不符记一处"
     "（介绍前后多出来的文字归 F-shape，不在这一项记）。"),
    ("F-shape", "standard",
     "篇幅和格式：只交介绍本身——介绍前后加了标题、开场说明、核对说明之类的文字，记一处（不管加了几段都只记这一处，里面的数字、"
     "风味词、字数不在别的项重复记）。字数和每段句数按介绍本身算：测量值给了每一行的字数和句数，去掉多出来的那几行再加总；"
     "字数不在规则区间记一处，每个句数超了的段记一处。"),
    ("F-brew", "standard",
     "冲煮建议：是介绍本身的最后一句或最后一行，用规则的写法，数值和这一批杯测表一致（规则要按烘焙度选方法的，方法要选对）。数值错、"
     "方法选错、写法不符、介绍本身里冲煮建议后面还有别的句子，每处记一处（介绍后面多出来的说明文字归 F-shape，不在这一项记；"
     "°C 写成 ℃、冒号或斜杠全角半角不同、数字和单位之间有没有空格，都不算错）。"),
    ("F-facts", "standard",
     "事实：介绍本身里产地、处理法、海拔、烘焙度四项都写到且内容和杯测表一致；介绍本身里的阿拉伯数字都能在杯测表里找到（测量值逐行"
     "列出了数字和杯测表里有没有）。漏写一项、写错一项、写了杯测表里没有的数，每处记一处；介绍前后多出来的说明文字里的数字不在这一项记。"),
]
FILLERS = [
    "这支豆子的甜感干净，酸质明亮。",
    "放凉之后，甜感会更明显。",
    "入口柔和，收尾干净。",
    "适合在早晨慢慢喝一杯。",
    "整体轻盈，层次清楚。",
    "热的时候香气更足。",
    "第一口先闻香，再小口慢慢喝。",
    "配一块原味司康也很合适。",
    "温度降下来以后，酸甜会更协调。",
    "喜欢清爽口感的朋友，可以先从这一支开始。",
    "豆子密封避光保存，风味能保持得更久。",
    "注水慢一点，甜感会更饱满。",
    "这一批的整体风格干净清爽。",
    "每一口的变化都值得留意。",
]


def found_words(text: str) -> list[tuple[str, int]]:
    """Wheel words in the text, longest first at each position: (word, index)."""
    out, i = [], 0
    ordered = sorted(WORDS, key=len, reverse=True)
    while i < len(text):
        hit = next((w for w in ordered if text.startswith(w, i)), None)
        if hit:
            out.append((hit, i))
            i += len(hit)
        else:
            i += 1
    return out


def size(text: str) -> int:
    return len(re.sub(r"\s", "", text))


def sentences(line: str) -> int:
    parts = [p for p in re.split(r"(?<=[。！？])", line.strip()) if p.strip()]
    return len(parts)


def brew_line(rule: str, sheet: dict) -> str:
    if rule == "R1":
        return f"冲煮建议：粉水比 1:{sheet['pour'][0]}，水温 {sheet['pour'][1]}°C。"
    if rule == "R2":
        return f"粉水比 1:{sheet['pour'][0]} ／ 水温 {sheet['pour'][1]}°C ／ 研磨度 {sheet['pour'][2]}"
    if sheet["roast"] in ("浅烘", "中浅烘"):
        return f"冲煮建议（手冲）：粉水比 1:{sheet['pour'][0]}，水温 {sheet['pour'][1]}°C。"
    return f"冲煮建议（冷萃）：粉水比 1:{sheet['cold'][0]}，冷藏浸泡 {sheet['cold'][1]} 小时。"


def build(spec, rng):
    name, group, segment, rule = spec
    r = RULES[rule]
    edge = segment == "edge"
    if edge:
        flavors = rng.sample(sorted(TRAPS), 2) + rng.sample(PLAIN, 1)
        note_pool = [w for w in WORDS if w not in flavors and not any(w in f or f in w for f in flavors)]
        note = rng.choice(note_pool)
        pour = (rng.choice([14, 16, 17]), rng.choice([88, 89, 90, 91, 93, 94]), rng.choice(GRINDS))
        if pour[:2] == r["brew"][:2]:
            pour = (pour[0] + 1, pour[1], pour[2])
    else:
        flavors = rng.sample(PLAIN, 3)
        note = None
        pour = r["brew"]
    rng.shuffle(flavors)
    sheet = {
        "batch": f"{rng.choice(['春分', '谷雨', '立夏', '白露', '霜降', '小雪'])} {rng.randint(1, 9)} 号批次",
        "origin": rng.choice(ORIGINS), "process": rng.choice(PROCESSES),
        "altitude": rng.choice(range(1200, 2201, 50)),
        # R3 按烘焙度选手冲或冷萃：单号题浅烘一侧、双号题中烘一侧，两种方法都考到
        "roast": rng.choice(ROASTS if rule != "R3" else ROASTS[:2] if int(name[1:]) % 2 else ROASTS[2:]),
        "flavors": flavors, "note": note, "pour": pour,
        "cold": (rng.choice([8, 10, 12]), rng.choice([12, 14, 16, 18])),
    }
    return sheet


def sheet_text(sheet: dict) -> str:
    rows = [
        "# 杯测表", "", f"批次：{sheet['batch']}", "",
        "| 项目 | 内容 |", "|---|---|",
        f"| 产地 | {sheet['origin']} |", f"| 处理法 | {sheet['process']} |", f"| 海拔 | {sheet['altitude']} 米 |",
        f"| 烘焙度 | {sheet['roast']} |", f"| 风味 | {'、'.join(sheet['flavors'])} |",
        f"| 备注 | {'杯测师：放凉后有一点' + sheet['note'] + '的感觉，没有写进风味栏。' if sheet['note'] else '无'} |",
        "", "## 冲煮参数", "", "| 方法 | 粉水比 | 水温 | 研磨度 | 冷藏浸泡 |", "|---|---|---|---|---|",
        f"| 手冲 | 1:{sheet['pour'][0]} | {sheet['pour'][1]}°C | {sheet['pour'][2]} | — |",
        f"| 冷萃 | 1:{sheet['cold'][0]} | — | 中粗 | {sheet['cold'][1]} 小时 |",
    ]
    return "\n".join(rows) + "\n"


def wheel_text() -> str:
    lines = ["# 风味词总表", "", "| 类别 | 风味词 |", "|---|---|"]
    lines += [f"| {cat} | {'、'.join(ws)} |" for cat, ws in WHEEL]
    return "\n".join(lines) + "\n"


def example(rule: str, sheet: dict, rng) -> str:
    r = RULES[rule]
    me = r["self"]
    tail = "香" if r["suffix"] == "allowed" else ""
    f = sheet["flavors"]
    lines = [
        f"{me}这次带来{sheet['origin']}的{sheet['process']}批次，咖啡生长在海拔 {sheet['altitude']} 米的山地。",
        f"烘焙度是{sheet['roast']}，喝起来有{f[0]}{tail}和{f[1]}的味道。",
        f"尾段留下{f[2]}的余韵。",
    ]
    low, high = r["range"]
    fillers = FILLERS[:]
    rng.shuffle(fillers)
    body = lines[:]
    while size("\n".join(body) + brew_line(rule, sheet)) < low + 8 and fillers:
        add = fillers.pop()
        # 加到句数还没满的段后面，满了就另起一段
        for index, line in enumerate(body):
            if sentences(line) < r["sentences"] and size("\n".join(body) + add + brew_line(rule, sheet)) <= high - 8:
                body[index] = line + add
                break
        else:
            body.append(add)
    body = [line for line in body]
    # 把太长的段拆开，保证每段句数不超
    split = []
    for line in body:
        parts = [p for p in re.split(r"(?<=[。！？])", line) if p]
        for start in range(0, len(parts), r["sentences"]):
            split.append("".join(parts[start:start + r["sentences"]]))
    text = "\n".join(split + [brew_line(rule, sheet)])
    return text


def check_example(rule: str, sheet: dict, text: str) -> None:
    r = RULES[rule]
    low, high = r["range"]
    assert low + 5 <= size(text) <= high - 5, (rule, size(text), text)
    assert all(sentences(line) <= r["sentences"] for line in text.splitlines() if line.strip()), text
    words = [w for w, _ in found_words(text)]
    assert set(words) <= set(sheet["flavors"]), (words, sheet["flavors"])
    if r["cover"]:
        assert set(sheet["flavors"]) <= set(words), (words, sheet["flavors"])
    assert r["self"] in text and not any(x in text for x in r["not_self"]) and not any(b in text for b in r["banned"])
    assert text.splitlines()[-1] == brew_line(rule, sheet)
    numbers = set(re.findall(r"\d+", text))
    allowed = set(re.findall(r"\d+", sheet_text(sheet)))
    assert numbers <= allowed, (numbers - allowed)
    if r["suffix"] == "none":
        for w, i in found_words(text):
            assert text[i + len(w): i + len(w) + 1] not in ("香", "味", "调", "感"), text


def reference(spec, sheet, text) -> dict:
    name, group, segment, rule = spec
    r = RULES[rule]
    near = sorted({w for f in sheet["flavors"] for w in WORDS if w != f and (f in w or w in f)}
                  | {w for f in sheet["flavors"] for w in TRAPS.get(f, ())})
    method = "手冲" if rule != "R3" or sheet["roast"] in ("浅烘", "中浅烘") else "冷萃"
    return {
        "规则集": f"{rule}（{r['brand']}）",
        "风味栏的词（只能写这些）": sheet["flavors"],
        "风味词后缀": "可以紧跟“香”“味”“调”" if r["suffix"] == "allowed" else "不能紧跟“香”“味”“调”“感”",
        "风味栏的词要全部写到": "是" if r["cover"] else "否",
        "容易写岔、不能写的总表词（举例）": sorted(set(near) | ({sheet["note"]} if sheet["note"] else set())),
        "备注里提到、不能写的词": sheet["note"] or "无",
        "自称": f"用“{r['self']}”至少一次；不用{'、'.join('“' + x + '”' for x in r['not_self'])}",
        "禁用词": r["banned"],
        "字数区间": f"{r['range'][0]} 到 {r['range'][1]}",
        "每段句数上限": r["sentences"],
        "冲煮建议": {"方法": method, "该写成": brew_line(rule, sheet)},
        "事实": {"产地": sheet["origin"], "处理法": sheet["process"], "海拔": f"{sheet['altitude']} 米", "烘焙度": sheet["roast"]},
        "一份照规则写的示例（措辞可以不同）": text,
        "示例字数": size(text),
    }


def scenario_package():
    (SCENARIO / "personas").mkdir(parents=True, exist_ok=True)
    (SCENARIO / "profile.md").write_text(TASK + "\n")
    (SCENARIO / "onboarding.md").write_text(ONBOARDING + "\n")
    (SCENARIO / "personas" / "brand.md").write_text("品牌运营每上一个新批次要一段产品介绍；每道题的杯测表、风味词总表和规则由脚本给出。\n")
    (SCENARIO / "scenario.json").write_text(json.dumps({
        "initial": [],
        "criteria": [{"id": i, "check": text, "severity": severity} for i, severity, text in CRITERIA],
    }, ensure_ascii=False, indent=1) + "\n")
    visible = ["counterpart", "analyst", "curator"]
    (SCENARIO / "contract.json").write_text(json.dumps(
        {"checks": {i: {"visibility": visible} for i, _, _ in CRITERIA}}, ensure_ascii=False, indent=1) + "\n")


def main():
    assert len({s[0] for s in SPECS}) == 40 and len(WORDS) == len(set(WORDS))
    for trap, near in TRAPS.items():
        for w in near:
            assert found_words(w) == [(w, 0)], w
    for rule in RULES:
        for filler in FILLERS:
            assert not found_words(filler) and not any(b in filler for b in RULES[rule]["banned"]), filler
    (HERE / "rules").mkdir(exist_ok=True)
    bank, scripts, retries = [], [], 0
    for spec in SPECS:
        name, group, segment, rule = spec
        for salt in range(200):
            rng = random.Random(f"{name}:{salt}")
            sheet = build(spec, rng)
            text = example(rule, sheet, rng)
            try:
                check_example(rule, sheet, text)
                break
            except AssertionError:
                retries += 1
        else:
            raise RuntimeError(f"{name}: no seed passes the checks")
        files = {"工作规则.md": RULES[rule]["text"], "杯测表.md": sheet_text(sheet), "风味词总表.md": wheel_text()}
        task = (f"{RULES[rule]['brand']}的新批次「{sheet['batch']}」要上新了，帮我写一段官网和公众号通用的产品介绍。\n\n"
                "这次适用的文案工作规则、这一批的杯测表和风味词总表在工作目录：工作规则.md、杯测表.md、风味词总表.md。")
        bank.append({"name": name, "group": group, "segment": segment, "rules": rule, "text": task, "files": files,
                     "reference": reference(spec, sheet, text)})
        label = {"train": "培养", "same": "考试·同规则", "new": "考试·新规则"}[group]
        scripts.append({"name": name, "title": f"{name} · {label} · {RULES[rule]['brand']}", "exam": group != "train",
                        "steps": [{"text": task, "files": files}]})
    for rule, r in RULES.items():
        (HERE / "rules" / f"{rule}.md").write_text(r["text"])
    (HERE / "questions.json").write_text(json.dumps(bank, ensure_ascii=False, indent=1) + "\n")
    (HERE / "scripts.json").write_text(json.dumps(scripts, ensure_ascii=False, indent=1) + "\n")
    scenario_package()
    print(f"{len(bank)} questions, {retries} seed retries, scenario at {SCENARIO.name}")


if __name__ == "__main__":
    main()
