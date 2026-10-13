"""小红书品牌合作笔记：三套工作规则、40 道题（20 培养 + 10 道同规则考试 + 10 道换规则考试）、参考答案和 Studio 场景包。

  python3 make.py

依据《专家自进化》5.2 的案例改写成「工作规则随题交给员工」：三家户外品牌给新品写一篇小红书品牌合作笔记，口径不同（标题字数
上限、正文字数区间、正文开头几行要原样写出什么、禁用的比较说法、导流词、话题上限、合作标注的写法和位置、交付的段名和顺序）。
培养题和同规则考试题用 R1（岚径户外）、R2（松屿户外）交替，换规则考试题全用员工从没见过的 R3（青溪户外：正文要原样写出
“使用限制”，话题要品牌话题在前）。每题一张产品参数表按种子生成：常见题都是帐篷、标题不带 emoji、标题必带参数是“1.2kg”这样
的简单写法、卖点和购买渠道里没有坑；边界题换成睡袋、炉具、灯具、背包、帐篷配件（必带话题和帐篷不同；灯具和帐篷配件的产品名
里带“帐篷”两个字），标题要带参数表指定的 emoji（算 2 字），标题必带参数是“1200g”“-5℃”“2800W”这类写法、卖点里有换算后的
写法，一部分题要带两个参数，示例标题卡在上限或差 1 字；卖点里有这套规则禁用的说法，购买渠道里有网址和导流词。参考答案写出
标题必带参数、emoji 要求、正文前几行要原样写出的文字、禁用字词和导流词、必带话题、交付格式，并附一份照规则写的示例（生成时
校验示例合规）。check.py 只读员工看到的文件另算一遍。
"""

import json
import random
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENARIO = HERE / "wkr-xhs-note"
CN = {4: "四", 5: "五", 6: "六", 7: "七", 8: "八"}
URL_MARKS = ("http", "www", ".com", ".cn")
# 基本多文种平面里默认按 emoji 显示的单个码位；另加 U+1F000–1FAFF。示例只用单码位 emoji
EMOJI_BMP = {0x231A, 0x231B, 0x23E9, 0x23EA, 0x23EB, 0x23EC, 0x23F0, 0x23F3, 0x25FD, 0x25FE, 0x2614, 0x2615,
             *range(0x2648, 0x2654), 0x267F, 0x2693, 0x26A1, 0x26AA, 0x26AB, 0x26BD, 0x26BE, 0x26C4, 0x26C5,
             0x26CE, 0x26D4, 0x26EA, 0x26F2, 0x26F3, 0x26F5, 0x26FA, 0x26FD, 0x2705, 0x270A, 0x270B, 0x2728,
             0x274C, 0x274E, 0x2753, 0x2754, 0x2755, 0x2757, 0x2795, 0x2796, 0x2797, 0x27B0, 0x27BF, 0x2B1B,
             0x2B1C, 0x2B50, 0x2B55}

RULES = {
    "R1": {
        "brand": "岚径户外", "title": 20, "body": (300, 500), "first": 3, "fields": ["目标人群"], "limit": False,
        "most": False, "banned": ["全网", "最轻", "最强", "第一", "秒杀", "碾压"],
        "lead": ["链接", "二维码", "点击购买", "私信", "淘宝", "天猫", "京东"], "tags": 5, "order": False,
        "sections": ["标题", "正文", "话题", "合作标注"], "label": ("合作标注", "品牌合作"),
        "label_says": "“## 合作标注”下只写“品牌合作”这四个字",
        "table": {"帐篷": (["#岚径露营"], ["#轻量化徒步"]), "帐篷配件": (["#岚径露营"], ["#露营装备清单"]),
                  "睡袋": (["#岚径露营"], ["#冬季露营", "#睡袋推荐"]), "炉具": (["#岚径野炊"], ["#户外做饭"]),
                  "灯具": (["#岚径夜营"], ["#露营灯"]), "背包": (["#岚径徒步"], ["#徒步背包"])},
        "baits": ["同价位最轻的{noun}", "露营圈公认第一的{noun}", "秒杀同价位的{noun}", "碾压同级别的{noun}", "全网好评的{noun}"],
        "channel": "岚径户外天猫旗舰店（链接：https://lanjing.tmall.com）",
    },
    "R2": {
        "brand": "松屿户外", "title": 16, "body": (200, 350), "first": 2, "fields": ["目标人群", "推荐场景"], "limit": False,
        "most": True, "banned": ["第一", "首选", "天花板", "吊打", "完胜"],
        "lead": ["链接", "主页", "评论区", "店铺", "下单", "私信"], "tags": 4, "order": False,
        "sections": ["标题", "合作声明", "正文", "话题"], "label": ("合作声明", "本篇为松屿户外合作笔记"),
        "label_says": "“## 合作声明”下只写“本篇为松屿户外合作笔记”这一句（句末加不加句号都行）",
        "table": {"帐篷": (["#松屿户外"], ["#轻量帐篷"]), "帐篷配件": (["#松屿户外"], ["#露营好物"]),
                  "睡袋": (["#松屿户外"], ["#睡袋测评", "#冬季露营"]), "炉具": (["#松屿户外", "#松屿野炊"], ["#露营做饭"]),
                  "灯具": (["#松屿户外"], ["#营地灯"]), "背包": (["#松屿户外"], ["#徒步装备"])},
        "baits": ["同价位最轻的{noun}", "{noun}里的天花板", "完胜同价位的{noun}", "露营首选的{noun}", "吊打同级别的{noun}"],
        "channel": "松屿户外京东自营店铺（https://mall.jd.com/songyu）",
    },
    "R3": {
        "brand": "青溪户外", "title": 18, "body": (400, 600), "first": 3, "fields": ["目标人群"], "limit": True,
        "most": False, "banned": ["全网", "最好", "最轻", "最强", "第一", "唯一", "顶级"],
        "lead": ["链接", "二维码", "淘宝", "天猫", "京东", "拼多多", "私信"], "tags": 6, "order": True,
        "sections": ["标题", "正文", "话题", "合作标注"], "label": ("合作标注", "青溪户外品牌合作"),
        "label_says": "“## 合作标注”下只写“青溪户外品牌合作”这八个字",
        "table": {"帐篷": (["#青溪户外", "#青溪露营"], ["#轻量化露营"]), "帐篷配件": (["#青溪户外"], ["#露营装备", "#帐篷配件"]),
                  "睡袋": (["#青溪户外", "#青溪露营"], ["#睡袋推荐"]), "炉具": (["#青溪户外"], ["#户外炉具", "#野炊"]),
                  "灯具": (["#青溪户外", "#青溪夜营"], ["#露营灯"]), "背包": (["#青溪户外"], ["#徒步背包", "#轻装徒步"])},
        "baits": ["全网独一份的{noun}", "唯一做到这个重量的{noun}", "顶级用料的{noun}", "同价位最好的{noun}", "露营圈公认第一的{noun}"],
        "channel": "青溪户外淘宝店（www.qingxi-outdoor.cn）",
    },
}
LINES = ["帐篷", "帐篷配件", "睡袋", "炉具", "灯具", "背包"]
EDGE_LINES = ["睡袋", "炉具", "灯具", "背包", "帐篷配件"]


def banned(rule: str) -> list[str]:
    """Every banned piece of a rule set, the single character “最” first when the rule bans it."""
    return (["最"] if RULES[rule]["most"] else []) + RULES[rule]["banned"]


def rule_text(rule: str) -> str:
    r = RULES[rule]
    low, high = r["body"]
    first = r["first"]
    items = [
        f"标题不超过 {r['title']} 字（字数按补充口径算）。标题必须带上参数表里“标题必带”一栏写“是”的每一个参数，写法照抄这个参数的"
        "“数值”一栏：数字、小数点、正负号、单位、大小写都一样，中间不加空格，不换算。参数表写“1.2kg”，标题就写“1.2kg”；写“1200g”，"
        "标题就写“1200g”。写成“1200 g”“1.2 kg”“1.2KG”“1.2公斤”，或者把“-5℃”写成“-5°C”“零下5℃”，都算没带。“标题必带”写“否”"
        "的参数，标题里写不写都行。",
        "标题里的 emoji 看参数表的“标题 emoji”：写了一个 emoji 的，标题里要带上这个 emoji，只放一次，不放别的 emoji；写“无”的，"
        "标题里不放 emoji。正文里用不用 emoji 不限。",
    ]
    if r["fields"] == ["目标人群"]:
        items.append(f"正文 {low} 到 {high} 字（含 {low} 和 {high}，字数按补充口径算）。正文前 {first} 行里要原样写出参数表“目标人群”"
                     f"的文字：一字不改，完整地出现在前 {first} 行的某一行里，前后可以加字（例如参数表写“春秋季徒步露营的两人组”，"
                     "可以写成“适合春秋季徒步露营的两人组”）。")
    else:
        items.append(f"正文 {low} 到 {high} 字（含 {low} 和 {high}，字数按补充口径算）。正文前 {first} 行里要原样写出参数表“目标人群”"
                     f"和“推荐场景”的文字：两项都一字不改，各自完整地出现在前 {first} 行的某一行里（两项可以在同一行，也可以各占一行），"
                     "前后可以加字。")
    if r["limit"]:
        items.append("正文里要写清这款产品用不了的场景：原样写出参数表“使用限制”的文字，一字不改，完整地出现在正文的某一行里"
                     "（哪一行都行），前后可以加字。")
    words, n = "".join(f"“{w}”" for w in r["banned"]), CN[len(r["banned"])]
    if r["most"]:
        items.append(f"标题、正文、话题里都不出现“最”字（“最适合”“最后”“最近”里的“最”也算），也不出现这{n}个词：{words}。"
                     f"是别的词的一部分也算（例如“第一次”里有“第一”）。参数表里带“最”字或这{n}个词的文字（例如“卖点”）不能照抄。"
                     f"这一条只管“最”字和这{n}个词，别的说法不按这一条判。")
    else:
        items.append(f"标题、正文、话题里都不出现这{n}个词：{words}。是别的词的一部分也算（例如“最轻松”里有“最轻”，“第一次”里有"
                     f"“第一”）。参数表里带这{n}个词的文字（例如“卖点”）不能照抄。这一条只管这{n}个词，别的说法不按这一条判。")
    words, n = "".join(f"“{w}”" for w in r["lead"]), CN[len(r["lead"])]
    items.append("不放外链、不导流：标题、正文、话题里不出现网址（出现“http”“www”“.com”“.cn”中的任何一个就算网址，不分大小写），"
                 f"也不出现这{n}个词：{words}（是别的词的一部分也算）。参数表“购买渠道”里带网址或这{n}个词的，不能照抄。"
                 f"这一条只管网址和这{n}个词。")
    tags = (f"话题最多 {r['tags']} 个。必带话题按话题表查：拿参数表“产品线”的写法，在话题表里找“产品线”一栏和它完全相同的那一行"
            "（只看“产品线”，不看产品名里有什么字），这一行“品牌话题”和“品类话题”两栏里的每个话题都要带上，写法一字不差。"
            f"自己加的话题也算在 {r['tags']} 个里。")
    if not r["order"]:
        tags += "话题的先后不限。"
    else:
        tags += ("话题按这个顺序写：先写这一行“品牌话题”一栏的话题，再写“品类话题”一栏的话题（一栏里有两个的，按表里从左到右的"
                 "顺序），自己加的话题放在最后（可以不加）。")
    items.append(tags)
    says = {"标题": "“## 标题”下只写一行标题", "正文": "“## 正文”下写正文",
            "话题": "“## 话题”下把全部话题写在一行，每个话题以“#”开头，话题之间空一格", r["label"][0]: r["label_says"]}
    items.append("交付格式：笔记直接写在回复里，不另存文件。按顺序交四段，段名是" + "".join(f"“## {s}”" for s in r["sections"])
                 + "：" + "；".join(says[s] for s in r["sections"]) + "。只交这四段：第一段前、最后一段后不加别的文字（开场白、"
                 "字数核对、说明都不加），段里也不夹规则没要求的文字（例如“标题：”“（正文 420 字）”）。")
    lines = [f"# {r['brand']} · 小红书品牌合作笔记工作规则", "",
             f"每篇笔记按这次的产品参数表和话题表写，交{'、'.join(r['sections'])}四部分。", ""]
    lines += [f"{i}. {item}" for i, item in enumerate(items, 1)]
    lines += ["", "补充口径：", "",
              "- 字数（标题和正文都这样算）：空格和换行不算；一个 emoji（例如⛺🔥✨）算 2；其余每个字符都算 1，汉字、字母、数字、"
              "标点（包括引号、括号）和“.”“-”“+”“×”“℃”“*”这些符号都是一个算 1（Markdown 的“**”算 2，行首的“- ”算 1）。",
              f"- 正文里一行算一行，空行不算；“前 {first} 行”就是正文开头的 {first} 行。",
              "- 话题只写在“## 话题”段里：标题和正文的文字里不写话题，也不出现“#”（段名前面的“##”不算）。",
              "- 原样写出参数表里的文字时，多加的空格不算改字（标题必带参数除外，见第 1 条）。"]
    return "\n".join(lines) + "\n"


SPECS = []
for i in range(1, 21):
    SPECS.append((f"t{i:02d}", "train", "edge" if i > 10 else "common", "R1" if i % 2 else "R2"))
for i in range(1, 11):
    SPECS.append((f"x{i:02d}", "same", "edge" if i > 5 else "common", "R1" if i % 2 else "R2"))
for i in range(1, 11):
    SPECS.append((f"y{i:02d}", "new", "edge" if i > 5 else "common", "R3"))

TASK = (
    "你是户外品牌的小红书运营，负责给新品写品牌合作种草笔记。工作目录里有这次适用的笔记工作规则、这款产品的参数表和按产品线分的"
    "必带话题表。按这次给的工作规则写出这篇笔记（标题、正文、话题和合作标注），写完直接发布。只输出这篇笔记本身。"
)
ONBOARDING = "以后每款新品的小红书合作笔记，我都会把这次适用的笔记工作规则、产品参数表和必带话题表一起发给你。不同品牌的要求不一样，以当次给的为准。"
CRITERIA = [
    ("XN-title", "standard",
     "标题：只看“## 标题”下的标题本身（标题前面多写的“标题：”、标题段里多写的候选标题或说明归 XN-format，算字数时去掉）。字数按这次"
     "工作规则的算法算（空格不算，一个 emoji 算 2，其余每个字符算 1；测量值已按这个算法算好并列出明细，以测量值为准），超过这次规则的"
     "上限记一处。参考答案列出的标题必带参数要原样出现在标题里：和参数表“数值”一栏一模一样（单位、大小写、正负号、℃ 都一样，中间"
     "没有空格），写成换算后的写法或别的写法都算没带，每缺一个记一处。参数表“标题 emoji”写了 emoji 的：标题里没有这个 emoji 记一处，"
     "另外多放了别的 emoji 或把这个 emoji 放了不止一次，再记一处；写“无”的：标题里出现 emoji 记一处。标题里的禁用字词、网址和导流词归 XN-clean，“#”归 XN-tags，"
     "不在这一项记。"),
    ("XN-body", "standard",
     "正文和人群：只看“## 正文”下的笔记正文。正文段里夹的说明（例如“（正文 420 字）”）或合作标注那句话不算正文，归 XN-format，"
     "数字数和数行时都先去掉（测量值给了正文逐行字数和行号）。正文字数按这次规则的算法（空格和换行不算，一个 emoji 算 2，其余每个"
     "字符算 1）不在规则区间（含两端）记一处。参考答案列出的“前几行里要原样写出的文字”（目标人群；规则要求时还有推荐场景），每一项"
     "都要一字不差、完整地出现在正文前几行（行数以参考答案为准，空行不算）的某一行里；没写、改了字、只写了一部分、写在规定行数以后，"
     "每项记一处（多加空格不算改字）。参考答案写明要原样写出“使用限制”的，正文里没有一字不差地完整写出，记一处；参考答案写明不要求的，"
     "这一部分不判。正文里的禁用字词、网址和导流词归 XN-clean，“#”归 XN-tags，不在这一项记。"),
    ("XN-clean", "red_line",
     "禁用说法和外链导流：只看标题、正文、话题这三段本身（交付前后多出来的文字、段里夹的说明归 XN-format，里面出现的词不在这一项记；"
     "合作标注段不在这一项判）。参考答案列出的禁用字词，每出现一次记一处，是别的词的一部分也算（例如“最轻松”里的“最轻”、“第一次”里的"
     "“第一”；测量值已逐处列出所在段和上下文）；网址（一串连续的英文字母、数字和符号里出现“http”“www”“.com”“.cn”任一个，不分"
     "大小写）每个记一处，一个网址里有几个标记也只记一处（测量值已逐个列出）；参考答案列出的导流词每出现一次记一处。只按这次规则列出的字词判：别的规则里的词和列表外的说法（例如“扫码”“旗舰店”“更轻”）都不记。"),
    ("XN-tags", "standard",
     "话题：只看“## 话题”段里的话题（每个以“#”开头的算一个）。个数超过这次规则的上限记一处；参考答案列出的必带话题（按参数表"
     "“产品线”在话题表里查到的那一行）每缺一个记一处，写法要一字不差；参考答案写明有顺序要求的，顺序不对记一处（只记这一处）；"
     "话题分成几行写、没用“#”开头或话题之间没空格，记一处；标题或正文的文字里出现“#”，记一处。话题段里夹的说明文字（例如“共 4 个"
     "话题”）和交付前后多出来的文字里提到的话题，都归 XN-format，不在这一项记。"),
    ("XN-format", "standard",
     "交付格式和合作标注：按这次规则的段名和顺序交（每段以“## 段名”开头，以参考答案为准），段名写错、缺段、多段、顺序不对，记一处；"
     "第一段前、最后一段后多了文字（开场白、字数核对、说明……），或段里夹了规则没要求的文字（例如“标题：”前缀、“（正文 420 字）”），"
     "或笔记另存成文件交（产出里有【交付文件】），记一处——不管多了几处都只记这一处，里面的数字、禁用字词、网址、话题、字数不在别的项"
     "重复记。合作标注按参考答案的写法写在规定的那一段：漏写、写错字、放错段、那一段的段名写错，都只记这一处（这时不再按段名、"
     "缺段或顺序另记）。"),
]

TENT_STYLES = {
    "单人帐": (["0.9kg", "1.1kg", "1.25kg"], ["喜欢独自徒步的背包客", "周末一个人进山的徒步爱好者"]),
    "双人帐": (["1.2kg", "1.35kg", "1.5kg", "1.6kg"], ["春秋季徒步露营的两人组", "周末结伴徒步的情侣", "喜欢轻装出行的两人小队"]),
    "三人帐": (["2.1kg", "2.4kg", "2.6kg"], ["带孩子周末露营的三口之家", "结伴自驾露营的三人小队"]),
}
SERIES = {"帐篷": ["云雀", "山雀", "白桦", "远岫", "晨雾", "苍岭"], "睡袋": ["雪鸮", "冬眠", "暖岭", "松雪"],
          "炉具": ["焰心", "炊烟", "小火苗"], "灯具": ["星点", "萤火", "微光"], "背包": ["远行", "轻羽", "山径"],
          "帐篷配件": ["磐石", "厚土", "青苔"]}
EMOJIS = {"睡袋": ["🌙", "😴"], "炉具": ["🔥", "🍳", "☕"], "灯具": ["💡", "✨"], "背包": ["🎒", "🥾", "🧭"],
          "帐篷配件": ["⛺", "🌲", "💧"]}
PEOPLE = {"睡袋": ["秋冬季高海拔露营的单人玩家", "初冬山地徒步的露营爱好者", "冬季自驾露营的户外新手"],
          "炉具": ["喜欢在营地做饭的露营新手", "两三人结伴野炊的徒步小队", "爱在山里煮咖啡的徒步爱好者"],
          "灯具": ["夜里需要照明的露营家庭", "喜欢夜徒步的户外玩家", "常在营地过夜的露营爱好者"],
          "背包": ["两天一夜轻装徒步的背包客", "刚开始走长线的徒步新手", "周末短途徒步的户外玩家"],
          "帐篷配件": ["常在碎石营地扎营的露营玩家", "想保护帐篷底布的露营新手", "雨季也坚持露营的户外爱好者"]}
SCENES = {"帐篷": ["春秋季山地徒步露营", "周末近郊草地露营", "湖边营地过夜", "海边沙滩露营"],
          "睡袋": ["初冬高山营地过夜", "秋冬季自驾营地过夜", "高海拔徒步途中扎营"],
          "炉具": ["营地煮面和手冲咖啡", "徒步午休时烧水做饭", "自驾露营的早餐时间"],
          "灯具": ["营地帐篷里挂着照明", "夜里在营地周围走动", "露营晚餐时照亮餐桌"],
          "背包": ["两天一夜的山地徒步", "城市周边的周末徒步", "需要背帐篷的长线徒步"],
          "帐篷配件": ["碎石营地扎营", "潮湿草地扎营", "雨后营地扎营"]}
LIMITS = {"帐篷": ["不适合冬季雪地露营", "大风天不要在空旷山脊上搭建", "不适合连续多天的暴雨天气"],
          "睡袋": ["气温低于极限温标时不能单独使用", "不适合深冬的雪地露营"],
          "炉具": ["不能在帐篷里或密闭空间里使用", "大风里要先挡好风再点火"],
          "灯具": ["不能长时间泡在水里使用", "不适合当远距离探照灯用"],
          "背包": ["不适合背十五公斤以上的重装", "暴雨里要另外套防雨罩"],
          "帐篷配件": ["不能代替帐篷外帐单独挡雨", "不适合铺在尖锐的岩石上"]}
CLEAN_SELLING = ["双门双前厅，进出方便", "内帐通风好，夏天不闷", "地钉和风绳都配齐了", "外帐自带收纳袋，收起来很快"]
SPECIFIC = {"帐篷": ["搭建很快，天黑前一个人也能搭好。", "帐篷里的空间够用，放下背包也不挤。"],
            "睡袋": ["晚上钻进去很快就暖和起来，拉链也顺滑。", "早上起来收纳，压一压就能塞回袋子里。"],
            "炉具": ["点火很干脆，煮一锅面不用等太久。", "收起来只有手掌大小，放进锅里一起带走。"],
            "灯具": ["挂在帐篷顶上，整个空间都被照亮了。", "亮度可以调，夜里起身也不会晃眼。"],
            "背包": ["背负系统贴合后背，走久了肩膀也不酸。", "侧袋和顶包都很好用，水壶和零食伸手就能拿到。"],
            "帐篷配件": ["铺在帐篷下面，碎石和湿气都隔开了。", "收起来很薄，叠好塞进帐篷袋里正好。"]}
FILLERS = [
    "这次带它出门走了两天，用下来整体很顺手。",
    "收纳以后体积不大，塞进背包也不占太多地方。",
    "做工细节挺扎实，边角和走线都处理得很干净。",
    "出发前我把它加进了装备清单，整理行李时省心不少。",
    "实际用的时候没有遇到需要折腾的地方，上手很快。",
    "说明书写得很清楚，照着步骤来不会出错。",
    "如果你和我一样喜欢轻装出行，可以把它放进下次的装备清单。",
    "对我来说，户外装备好不好用，关键看用起来是不是省心。",
    "这两天温差不小，但它的表现一直很稳定。",
    "回家以后清理也方便，擦一擦晾干就能收起来。",
    "我习惯每次出发前检查一遍装备，这次它让我少操了不少心。",
    "价格在同类装备里算是适中，预算有限的话也能考虑。",
    "整体用下来，我觉得它是一件靠谱的装备。",
    "细节上能看出品牌是认真做户外的。",
    "如果你还在纠结，可以先去线下门店上手摸一摸。",
    "这次出行天气不错，傍晚的风有点大，但没有影响使用。",
    "我身边几个常去露营的朋友，看完也都想入手。",
    "装备不在多，带对了出门才轻松。",
    "每次出发前，我都会再确认一遍天气和路线。",
    "下一次出发，我还会继续带上它。",
    "它不是那种花里胡哨的装备，胜在实用。",
    "用了几次以后，我对它越来越放心。",
]
CLOSING = "关注我，后面会继续分享更多户外装备的真实体验。"
PHRASES = {"帐篷": ["轻装出发", "说走就走", "春秋徒步刚刚好", "背着走一天不累", "周末露营好搭档", "搭起来很快"],
           "睡袋": ["真暖", "睡得香", "暖到天亮", "冬夜睡得安稳", "冬天露营不怕冷", "钻进去就暖和"],
           "炉具": ["火力足", "煮面快", "营地开饭啦", "山里也能煮咖啡", "野炊好帮手"],
           "灯具": ["够亮", "夜里安心", "照亮营地", "营地夜晚好帮手", "挂在帐篷里刚好"],
           "背包": ["好背", "轻装上路", "背着不累", "两天一夜刚刚好", "长线徒步好搭档"],
           "帐篷配件": ["防潮", "不怕磨", "帐篷底不怕磨", "碎石营地也安心", "雨后扎营不发愁"]}
OWN_TAGS = ["#户外装备", "#露营日记", "#徒步旅行", "#周末去哪儿", "#装备分享", "#户外生活"]


def is_emoji(ch: str) -> bool:
    return 0x1F000 <= ord(ch) <= 0x1FAFF or ord(ch) in EMOJI_BMP


def units(text: str) -> int:
    """Characters as the rules count them: spaces and line breaks 0, an emoji 2, anything else 1."""
    return sum(2 if is_emoji(c) else 1 for c in text if not c.isspace())


def hits(text: str, words: list[str]) -> list[str]:
    """Banned pieces found in a text, as substrings; URL marks case-insensitively."""
    found = [w for w in words if w in text]
    return found + [m for m in URL_MARKS if m in text.lower()]


def wrong_forms(value: str) -> list[str]:
    """Writings of a title parameter that do not count as carrying it (examples for the judge)."""
    if value.endswith("kg"):
        number = float(value[:-2])
        return [f"{round(number * 1000)}g", value[:-2] + " kg", value[:-2] + "KG", value[:-2] + "公斤"]
    if re.fullmatch(r"\d+g", value):
        grams = int(value[:-1])
        return [f"{grams / 1000:g}kg", f"{grams} g", f"{grams}G", f"{grams}克"]
    if value.endswith("℃"):
        return [value[:-1] + "°C", value[:-1] + " ℃"] + (["零下" + value[1:]] if value.startswith("-") else [])
    if value.endswith("W"):
        return [f"{int(value[:-1]) / 1000:g}kW", value[:-1] + "w", value[:-1] + " W"]
    if value.endswith("lm"):
        return [value[:-2] + " 流明", value[:-2] + "LM", value[:-2] + " lm"]
    if value.startswith("IPX"):
        return [value.lower(), "IPX-" + value[3:], value[3:] + " 级防水"]
    if value == "45+5L":
        return ["50L", "45L+5L", "45+5 L"]
    if value.endswith("L"):
        return [value[:-1] + " 升", value[:-1] + " L", value[:-1] + "l"]
    if value.endswith("mm"):
        return [value[:-2] + " 毫米", value[:-2] + "MM", value[:-2] + " mm"]
    raise ValueError(value)


def price(rng, low: int, high: int) -> str:
    return f"{rng.choice(range(low, high + 1, 100))} 元"


def product(line: str, rule: str, edge: bool, rng) -> dict:
    """A product sheet for one question; edge products carry the traps."""
    two = edge and rng.random() < 0.6
    series = rng.choice(SERIES[line])
    if line == "帐篷":
        style = rng.choice(sorted(TENT_STYLES))
        weights, people = TENT_STYLES[style]
        p = {"name": f"{series}{style[:2]}轻量帐篷", "noun": style, "people": rng.choice(people),
             "params": [("款式", style, "否"), ("重量", rng.choice(weights), "是"),
                        ("防水指数", rng.choice(["2000mm", "3000mm", "4000mm"]), "否"),
                        ("搭建时间", rng.choice(["2 分钟", "3 分钟", "5 分钟"]), "否"), ("售价", price(rng, 599, 1299), "否")]}
        alt = None
    elif line == "睡袋":
        comfort, grams = rng.choice([-5, -8, -10]), rng.choice([980, 1050, 1200, 1350])
        p = {"name": f"{series}羽绒睡袋", "noun": "睡袋",
             "params": [("填充", rng.choice(["白鹅绒", "白鸭绒"]), "否"), ("蓬松度", rng.choice(["650FP", "700FP", "800FP"]), "否"),
                        ("舒适温标", f"{comfort}℃", "是" if two else "否"), ("极限温标", f"{comfort - 10}℃", "否"),
                        ("重量", f"{grams}g", "是"), ("售价", price(rng, 799, 1599), "否")]}
        alt = f"整袋约 {grams / 1000:g}kg"
    elif line == "炉具":
        kind, watts = rng.choice(["分体式气炉", "一体式炉头"]), rng.choice([2600, 2800, 3000])
        p = {"name": f"{series}{kind}", "noun": kind[-2:],
             "params": [("类型", kind, "否"), ("功率", f"{watts}W", "是"), ("重量", f"{rng.choice([95, 168, 230])}g", "是" if two else "否"),
                        ("烧开 1L 水", rng.choice(["约 3 分钟", "约 3 分 30 秒"]), "否"), ("适用气罐", "扁气罐", "否"),
                        ("售价", price(rng, 199, 599), "否")]}
        alt = f"{watts / 1000:g}kW 大火力"
    elif line == "灯具":
        lumens = rng.choice([300, 450, 600])
        p = {"name": f"{series}帐篷挂灯", "noun": "挂灯",
             "params": [("亮度", f"{lumens}lm", "是"), ("续航", rng.choice(["8 小时", "12 小时", "20 小时"]), "否"),
                        ("防水等级", rng.choice(["IPX4", "IPX5", "IPX6"]), "是" if two else "否"),
                        ("重量", f"{rng.choice([128, 150, 180])}g", "否"), ("售价", price(rng, 99, 299), "否")]}
        alt = f"{lumens} 流明"
    elif line == "背包":
        volume = rng.choice(["38L", "40L", "45+5L"])
        p = {"name": f"{series}徒步背包", "noun": "背包",
             "params": [("容量", volume, "是"), ("重量", f"{rng.choice([980, 1100, 1250])}g", "是" if two else "否"),
                        ("背负系统", "透气网架背负", "否"), ("售价", price(rng, 399, 899), "否")]}
        alt = "50L 大容量" if volume == "45+5L" else f"{volume[:-1]} 升大容量"
    else:
        grams = rng.choice([260, 320, 380])
        p = {"name": f"{series}帐篷地布", "noun": "地布",
             "params": [("尺寸", rng.choice(["210×140cm", "220×150cm"]), "否"), ("重量", f"{grams}g", "是"),
                        ("防水指数", rng.choice(["5000mm", "8000mm"]), "是" if two else "否"),
                        ("售价", f"{rng.choice([99, 129, 159, 199])} 元", "否")]}
        alt = f"约 {grams / 1000:g}kg"
    r = RULES[rule]
    p.update({
        "line": line, "series": series, "emoji": rng.choice(EMOJIS[line]) if edge else "无",
        "scene": rng.choice(SCENES[line]), "limit": rng.choice(LIMITS[line]),
        "selling": f"{alt}，{rng.choice(r['baits']).format(noun=p['noun'])}" if edge else rng.choice(CLEAN_SELLING),
        "channel": r["channel"] if edge else f"{r['brand']}线下门店", "alt": alt,
    })
    if "people" not in p:
        p["people"] = rng.choice(PEOPLE[line])
    return p


def sheet_text(rule: str, p: dict) -> str:
    rows = ["# 产品参数表", "", f"- 品牌：{RULES[rule]['brand']}", f"- 产品：{p['name']}", f"- 产品线：{p['line']}",
            f"- 标题 emoji：{p['emoji']}", f"- 目标人群：{p['people']}", f"- 推荐场景：{p['scene']}", f"- 使用限制：{p['limit']}",
            "", "## 参数", "", "| 参数 | 数值 | 标题必带 |", "|---|---|---|"]
    rows += [f"| {k} | {v} | {m} |" for k, v, m in p["params"]]
    rows += ["", "## 其他", "", "| 项目 | 内容 |", "|---|---|", f"| 卖点 | {p['selling']} |", f"| 购买渠道 | {p['channel']} |"]
    return "\n".join(rows) + "\n"


def table_text(rule: str) -> str:
    rows = [f"# 必带话题表（{RULES[rule]['brand']}）", "", "| 产品线 | 品牌话题 | 品类话题 |", "|---|---|---|"]
    rows += [f"| {line} | {' '.join(b)} | {' '.join(k)} |" for line, (b, k) in RULES[rule]["table"].items()]
    return "\n".join(rows) + "\n"


def must(p: dict) -> list[str]:
    return [v for _, v, m in p["params"] if m == "是"]


def make_title(rule: str, p: dict, edge: bool, rng) -> str | None:
    limit = RULES[rule]["title"]
    head = ("" if p["emoji"] == "无" else p["emoji"]) + " ".join(must(p)) + p["noun"]
    options = [head + sep + phrase + tail for phrase in PHRASES[p["line"]] for sep in ("｜", "，") for tail in ("", "！")
               if units(head + sep + phrase + tail) <= limit]
    if edge:
        options = [t for t in options if units(t) >= limit - 1]
    return rng.choice(options) if options else None


def make_body(rule: str, p: dict, rng) -> str:
    r = RULES[rule]
    low, high = r["body"]
    target = rng.randint(low + 30, high - 30)
    if rule == "R2":
        body = [f"{p['people']}看过来，这次聊聊{p['name']}。", f"我觉得它很适合{p['scene']}。"]
    else:
        body = [f"这篇写给{p['people']}，聊聊{p['name']}。"]
    body.append("先把参数放这里：" + "，".join(f"{k} {v}" for k, v, _ in p["params"]) + "。")
    head = len(body)
    caution = f"也要提醒一句：{p['limit']}。" if r["limit"] else ""
    size = units("".join(body)) + units(CLOSING) + units(caution)
    for line in SPECIFIC[p["line"]] + rng.sample(FILLERS, len(FILLERS)):
        if size >= target:
            break
        body.append(line)
        size += units(line)
    if caution:
        body.insert(rng.randint(head, len(body)), caution)
    return "\n".join(body + [CLOSING])


def make_tags(rule: str, p: dict, rng) -> list[str]:
    brand, kind = RULES[rule]["table"][p["line"]]
    required = brand + kind
    total = rng.randint(len(required), RULES[rule]["tags"])
    return required + rng.sample([t for t in OWN_TAGS if t not in required], total - len(required))


def note_text(rule: str, title: str, body: str, tags: list[str]) -> str:
    r = RULES[rule]
    parts = {"标题": title, "正文": body, "话题": " ".join(tags), r["label"][0]: r["label"][1]}
    return "\n\n".join(f"## {s}\n{parts[s]}" for s in r["sections"])


def check_example(rule: str, p: dict, text: str, edge: bool) -> None:
    """The example obeys every rule of its set (same reading as measure.py)."""
    r = RULES[rule]
    parts = re.split(r"^## (.+)$", text, flags=re.M)
    assert parts[0] == "" and [parts[i] for i in range(1, len(parts), 2)] == r["sections"], parts
    got = {parts[i]: parts[i + 1].strip("\n") for i in range(1, len(parts), 2)}
    title, body, tags = got["标题"], got["正文"], got["话题"].split(" ")
    assert "\n" not in title and units(title) <= r["title"], (title, units(title))
    if edge:
        assert units(title) >= r["title"] - 1, (title, units(title))
    assert all(v in title for v in must(p)), (title, must(p))
    emojis = [c for c in title if is_emoji(c)]
    assert emojis == ([] if p["emoji"] == "无" else [p["emoji"]]), (title, emojis)
    lines = [line for line in body.splitlines() if line.strip()]
    assert r["body"][0] <= units(body) <= r["body"][1], (rule, units(body))
    fields = {"目标人群": p["people"], "推荐场景": p["scene"]}
    assert all(any(fields[f] in line for line in lines[:r["first"]]) for f in r["fields"]), lines[:3]
    assert not r["limit"] or p["limit"] in body, body
    for section in (title, body, " ".join(tags)):
        assert not hits(section, banned(rule) + r["lead"]), (section, hits(section, banned(rule) + r["lead"]))
    assert "#" not in title + body
    brand, kind = r["table"][p["line"]]
    assert len(tags) <= r["tags"] and all(t in tags for t in brand + kind) and all(t.startswith("#") for t in tags)
    if r["order"]:
        assert tags[:len(brand + kind)] == brand + kind, tags
    assert got[r["label"][0]] == r["label"][1]


def reference(spec, p: dict, title: str, body: str, tags: list[str], text: str) -> dict:
    name, group, segment, rule = spec
    r = RULES[rule]
    brand, kind = r["table"][p["line"]]
    needed = [p["people"]] + ([p["scene"]] if "推荐场景" in r["fields"] else [])
    baits = [{"位置": where, "原文": said, "命中": hits(said, banned(rule) + r["lead"])}
             for where, said in (("卖点", p["selling"]), ("购买渠道", p["channel"])) if hits(said, banned(rule) + r["lead"])]
    looks = [line for line in LINES if line != p["line"] and line in p["name"]]
    decoys = [t for t in sum(r["table"][looks[0]], []) if t not in brand + kind] if looks else []
    return {
        "规则集": f"{rule}（{r['brand']}）",
        "交付格式": {
            "段名和顺序": [f"## {s}" for s in r["sections"]],
            "合作标注": r["label_says"],
            "合作标注的写法": r["label"][1],
            "前后不加别的文字": "第一段前、最后一段后不能有文字；段里不夹“标题：”“（正文 420 字）”这类说明；笔记写在回复里，不另存文件",
        },
        "标题": {
            "字数上限": r["title"],
            "标题必带参数（照参数表“数值”一栏原样写）": must(p),
            "写成这些都算没带（举例）": [w for v in must(p) for w in wrong_forms(v)],
            "卖点里的另一种写法（照它写也算没带）": p["alt"] or "无",
            "emoji 要求": (f"参数表写了“{p['emoji']}”：标题里要带这个 emoji，只放一次（算 2 字），不放别的 emoji" if p["emoji"] != "无"
                         else "参数表写“无”：标题里不放 emoji"),
            "示例标题": title,
            "示例标题字数": units(title),
        },
        "正文": {
            "字数区间（含两端）": list(r["body"]),
            "前几行（空行不算）": r["first"],
            "前几行里要原样写出的文字": needed,
            "正文里要原样写出的使用限制": p["limit"] if r["limit"] else "这套规则不要求（参数表里的使用限制写不写都行）",
            "示例正文字数": units(body),
        },
        "禁用说法和导流": {
            "禁用字词（是别的词的一部分也算）": banned(rule),
            "网址的认法": "出现“http”“www”“.com”“.cn”中任何一个（不分大小写）",
            "导流词（是别的词的一部分也算）": r["lead"],
            "参数表里带禁用字词、网址或导流词，不能照抄的文字": baits or "无",
        },
        "话题": {
            "参数表的产品线": p["line"],
            "话题表里这一行": {"品牌话题": brand, "品类话题": kind},
            "必带话题": brand + kind,
            "个数上限": r["tags"],
            "顺序要求": ("有：先写品牌话题（按表里从左到右），再写品类话题（按表里从左到右），自己加的放最后" if r["order"]
                       else "没有，先后不限"),
            "产品名里像别的产品线的字": (f"产品名“{p['name']}”里有“{looks[0]}”，但产品线是“{p['line']}”；话题表“{looks[0]}”那一行里的"
                                       f"{'、'.join(decoys)}不是这道题的必带话题" if looks else "无"),
        },
        "一份照规则写的示例（措辞可以不同）": text,
    }


def line_of(name: str, segment: str) -> str:
    if segment == "common":
        return "帐篷"
    i = int(name[1:])
    if name[0] == "t":
        return EDGE_LINES[((i - 11) // 2) % 5]
    if name[0] == "x":
        return EDGE_LINES[(i - 2) % 5]
    return EDGE_LINES[(i - 6) % 5]


def check_data(spec, p: dict) -> None:
    """Traps are real and nothing the employee must copy breaks a rule."""
    name, group, segment, rule = spec
    r = RULES[rule]
    everything = sorted({w for k in RULES for w in banned(k) + RULES[k]["lead"]})
    for said in (p["name"], p["people"], p["scene"], p["limit"], r["label"][1], *sum(r["table"][p["line"]], [])):
        assert not hits(said, everything), (name, said)
    assert " " not in p["people"] + p["scene"] + p["limit"]
    values = [v for _, v, _ in p["params"]]
    assert len(values) == len(set(values))
    for v in must(p):
        assert all(v not in other for other in values if other != v), (name, v)
        assert all(v not in w for w in wrong_forms(v)), (name, v)
    if segment == "edge":
        assert p["line"] != "帐篷" and p["emoji"] != "无"
        assert any(w in p["selling"] for w in banned(rule)), (name, p["selling"])
        assert any(w in p["channel"] for w in r["lead"]) and any(m in p["channel"].lower() for m in URL_MARKS)
        assert all(v not in p["selling"] for v in must(p)), (name, p["selling"])
        assert sum(r["table"][p["line"]], []) != sum(r["table"]["帐篷"], []), (name, p["line"])
        assert units(p["emoji"]) == 2
    else:
        assert p["line"] == "帐篷" and p["emoji"] == "无" and not hits(p["selling"] + p["channel"], everything)
        assert re.fullmatch(r"\d+(\.\d+)?kg", must(p)[0]) and len(must(p)) == 1


def main():
    assert len({s[0] for s in SPECS}) == 40
    for rule in RULES:
        bad = banned(rule) + RULES[rule]["lead"]
        for said in FILLERS + [CLOSING] + sum(SPECIFIC.values(), []) + sum(PHRASES.values(), []) + OWN_TAGS:
            assert not hits(said, bad) and "#" not in said.lstrip("#"), (rule, said)
        assert all(any(w in bait for w in banned(rule)) for bait in RULES[rule]["baits"]), rule
        assert sorted(RULES[rule]["table"]) == sorted(LINES)
    (HERE / "rules").mkdir(exist_ok=True)
    texts = {rule: rule_text(rule) for rule in RULES}
    bank, scripts, retries, seen = [], [], 0, set()
    for spec in SPECS:
        name, group, segment, rule = spec
        edge = segment == "edge"
        for salt in range(300):
            rng = random.Random(f"{name}:{salt}")
            p = product(line_of(name, segment), rule, edge, rng)
            try:
                check_data(spec, p)
                # 边界题之间不重复同一产品线的同一组标题必带参数，让参数写法多一些变化
                assert not edge or (p["line"], tuple(must(p))) not in seen, "repeated parameters"
                title = make_title(rule, p, edge, rng)
                assert title, "no title fits"
                body, tags = make_body(rule, p, rng), make_tags(rule, p, rng)
                text = note_text(rule, title, body, tags)
                check_example(rule, p, text, edge)
                break
            except AssertionError:
                retries += 1
        else:
            raise RuntimeError(f"{name}: no seed passes the checks")
        seen.add((p["line"], tuple(must(p))))
        files = {"工作规则.md": texts[rule], "产品参数表.md": sheet_text(rule, p), "话题表.md": table_text(rule)}
        task = (f"{RULES[rule]['brand']}的新品「{p['name']}」要发一篇小红书品牌合作笔记，帮我写出来。\n\n"
                "这次适用的工作规则、产品参数表和必带话题表在工作目录：工作规则.md、产品参数表.md、话题表.md。")
        bank.append({"name": name, "group": group, "segment": segment, "rules": rule, "text": task, "files": files,
                     "reference": reference(spec, p, title, body, tags, text)})
        label = {"train": "培养", "same": "考试·同规则", "new": "考试·新规则"}[group]
        scripts.append({"name": name, "title": f"{name} · {label} · {RULES[rule]['brand']}", "exam": group != "train",
                        "steps": [{"text": task, "files": files}]})
    for rule in RULES:
        (HERE / "rules" / f"{rule}.md").write_text(texts[rule])
    (HERE / "questions.json").write_text(json.dumps(bank, ensure_ascii=False, indent=1) + "\n")
    (HERE / "scripts.json").write_text(json.dumps(scripts, ensure_ascii=False, indent=1) + "\n")
    scenario_package()
    print(f"{len(bank)} questions, {retries} seed retries, scenario at {SCENARIO.name}")


def scenario_package():
    (SCENARIO / "personas").mkdir(parents=True, exist_ok=True)
    (SCENARIO / "profile.md").write_text(TASK + "\n")
    (SCENARIO / "onboarding.md").write_text(ONBOARDING + "\n")
    (SCENARIO / "personas" / "brand.md").write_text("品牌运营每上一款新品要一篇小红书品牌合作笔记；每道题的产品参数表、话题表和规则由脚本给出。\n")
    (SCENARIO / "scenario.json").write_text(json.dumps({
        "initial": [],
        "criteria": [{"id": i, "check": text, "severity": severity} for i, severity, text in CRITERIA],
    }, ensure_ascii=False, indent=1) + "\n")
    visible = ["counterpart", "analyst", "curator"]
    (SCENARIO / "contract.json").write_text(json.dumps(
        {"checks": {i: {"visibility": visible} for i, _, _ in CRITERIA}}, ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    main()
