"""淘宝标题和卖点：三套工作规则、40 道题（20 培养 + 10 道同规则考试 + 10 道换规则考试）、参考答案和 Studio 场景包。

  python3 make.py

依据《专家自进化》6.1 的案例改写成「工作规则随题交给员工」：三家店的商品标题和卖点规则结构相同、口径不同（标题上限和字符数法、
必含词、卖点条数和写法、功能词表、禁用词表、品牌名单、交付段名）。培养题和同规则考试题用 R1（禾木家电淘宝店，小厨电）、
R2（澄悦个护京东店，个护小电器）交替，换规则考试题全用员工从没见过的 R3（山野户外拼多多店，户外用品；新口径：标题必须以
品牌名开头、每条卖点用【参数名】标出参数）。每道题给一个 SKU 的参数表、类目必含词、上百条的禁用词表和品牌名单（中英文名），
按种子生成并埋陷阱：常见题参数只有汉字和半角数字，参数值里夹着禁用词和其他品牌的中文名；边界题参数里有全角字母数字、带空格的
英文型号（R1 的型号里含必含词）、英文写的其他品牌名（大小写或全角不一）、参数名里带“最”“极限”，禁用词表里有“ＴＯＰ１”“第 一”
这类变体（参数值里夹的那个禁用词在表里也写成变体），必含词更多，标题要卡着上限写。参考答案由本脚本按规则算出（每个参数在卖点里
要写出的值、参数表里没有的功能词、参数里夹带的禁用词和品牌名、一份照规则写的示例和它的字符数）；生成时校验示例完全合规、陷阱有效。
check.py 只读员工看到的文件另写一遍算法复核。
"""

import json
import random
import re
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENARIO = HERE / "wkr-taobao-title"
sys.path.insert(0, str(HERE))
from measure import measure  # noqa: E402  评审用的测量值，这里拿来自检示例

# ---------------------------------------------------------------- 三套工作规则

FUNCTIONS = {
    "R1": ["预约", "保温", "自清洁", "APP", "蓝牙", "语音", "蒸汽", "旋转", "双层", "解冻", "发酵", "烘干", "断电记忆", "童锁",
           "防干烧", "翻面提醒"],
    "R2": ["防水", "无线充电", "快充", "APP", "蓝牙", "压力感应", "负离子", "恒温", "冷热风", "全身水洗", "磁吸", "数显", "智能提醒",
           "静音", "自动断电"],
    "R3": ["防水", "防风", "防晒", "速开", "自动", "充电", "充气", "感应", "伸缩", "折叠", "保温", "防蚊"],
}
RULES = {
    "R1": {"company": "禾木家电", "shop": "淘宝店", "brand": "禾木", "scheme": "byte", "max": 60, "min": None, "noun": "标题",
           "sections": ("标题", "卖点"), "count": 5, "style": "number", "point_max": None, "prefix": None},
    "R2": {"company": "澄悦个护", "shop": "京东店", "brand": "澄悦", "scheme": "hanzi", "max": 50, "min": 40, "noun": "商品名称",
           "sections": ("商品名称", "商品卖点"), "count": 3, "style": "chinese", "point_max": 30, "prefix": None},
    "R3": {"company": "山野户外", "shop": "拼多多店", "brand": "山野", "scheme": "byte", "max": 56, "min": None, "noun": "标题",
           "sections": ("商品标题", "卖点"), "count": 4, "style": "label", "point_max": None, "prefix": "山野"},
}

INTRO = "每次会给你一个商品的参数表（参数表.md）、这个类目的必含词（类目必含词.md）、禁用词表（禁用词表.md）和品牌名单（品牌名单.md）。"
COUNT_BYTE = ("字符这样数：半角字符（英文输入状态下直接打出来的字母、数字、空格和符号，例如 A、z、5、空格、-、/、+、.）每个算 1 个；"
              "其余每个字符（汉字、全角字母、全角数字、全角空格、中文标点，以及 ℃、°、× 这些键盘上没有的符号）每个算 2 个。")
COUNT_HANZI = "字符这样数：每个汉字算 2 个；空格不算（全角半角都不算）；其余每个字符（字母、数字、标点和符号，不分全角半角）每个算 1 个。"
VALUE = ("每条卖点要写出它那个参数的参数值，照参数表的写法写：可以去掉空格，全角的字母、数字和符号可以改成半角，别的不能改"
         "（例如参数表写“1-90 分钟”，卖点里写“1-90 分钟”或“1-90分钟”都算写出了参数值，写成“90 分钟”“1 到 90 分钟”都不算）。"
         "如果参数值里有禁用词表里的词或品牌名单里的名字，就把这些词删掉，剩下的照写；如果没有，就整个照写。")
MATCH = ("先把要查的文字和名单上的词都做三件事——全角的字母、数字和符号换成半角，英文字母一律当小写，去掉所有空格；"
         "然后只要名单上的词出现在文字里就算出现，哪怕它只是别的词的一部分（例如禁用词表里有“第一”，写“第一次”也算出现了“第一”）。")
NUMBER = "是连在一起的一串阿拉伯数字，中间可以有一个小数点，中间隔着空格或别的字符就是两个数，例如“1.7L”里的数字是“1.7”，“1-90 分钟”里的数字是“1”和“90”。"
TABLE = "参数表每一行是一个参数：左列是参数名，右列是参数值；最上面“# 参数表：……”那一行是表名，不是参数。"
ONLY = "交付：在回复里只写下面两段，按这个顺序；两段前后和段里都不加任何别的文字（不写开场白、说明、字数统计和自查过程）。"


def single_line(noun: str) -> str:
    return f"（这一段只写一行，就是{noun}本身：前面不加“{noun}：”这类字样，前后不加引号、书名号、括号或加粗符号。）"


RULE_TEXT = {
    "R1": f"""# 禾木家电 · 淘宝店商品标题和卖点工作规则

{INTRO}按下面的规则写一个商品标题和 5 条卖点。

1. 标题长度：标题不超过 60 个字符。{COUNT_BYTE}
2. 必含词：类目必含词.md 里的每个词都要写进标题，照表里的写法原样写（全角还是半角、大写还是小写，都和表里一样）。同一个必含词不重复堆：每个必含词在标题里只能出现一次（不是必含词的词，这一条不管）。数出现次数时不分全角半角和大小写、不管空格，必含词作为别的词的一部分出现也算一次（例如必含词有“5L”，标题里写了“5L”又写了型号“AF5L”，“5L”就出现了两次）。
3. 卖点：写 5 条，每条写参数表里的一个参数，5 条写 5 个不同的参数。
   - {VALUE}
   - 一条卖点里只写它那一个参数的参数值，不写别的参数的参数值。
   - 卖点里的阿拉伯数字（全角半角都算，行首的编号不算）只能是它那个参数的参数值里有的数字。
4. 不写参数表里没有的功能：下面这张功能词表里的词，参数表里没有的，标题和卖点里都不能出现：{"、".join(FUNCTIONS["R1"])}。功能词表里没有的词，这一条不管。另外，标题里的阿拉伯数字也必须是参数表某个参数值里有的数字。
5. 禁用词：标题和卖点里不出现禁用词表里的任何词。“最”“第一”“国家级”和“0油”“健康”这些健康宣称用语都在表里；以表为准，表里没有的词这一条不管。
6. 品牌名：标题和卖点里不出现品牌名单里的任何名字，中文名、英文名都算。我们自己的品牌“禾木”不在名单里，可以写，也可以不写。

补充口径：

- 第 2 条数必含词的次数、第 4 条查功能词、第 5 条查禁用词、第 6 条查品牌名，都用同一个比对办法：{MATCH}
- 第 4 条说的“参数表里有”，是指这个功能词出现在参数表某一行的参数名或参数值里（用上面的比对办法查）。
- {TABLE}
- 第 3、4 条说的数字，{NUMBER}

{ONLY}

## 标题
{single_line("标题")}

## 卖点
（5 行，一行一条，依次以“1. ”“2. ”“3. ”“4. ”“5. ”开头。）
""",
    "R2": f"""# 澄悦个护 · 京东店商品名称和卖点工作规则

{INTRO}按下面的规则写一个商品名称和 3 条卖点。

1. 商品名称长度：不少于 40 个字符，也不超过 50 个字符。{COUNT_HANZI}
2. 必含词：类目必含词.md 里的每个词都要写进商品名称，照表里的写法原样写（全角还是半角、大写还是小写，都和表里一样）。同一个必含词不重复堆：每个必含词在商品名称里只能出现一次（不是必含词的词，这一条不管）。数出现次数时不分全角半角和大小写、不管空格，必含词作为别的词的一部分出现也算一次（例如必含词有“IPX7”，商品名称里写了“IPX7”又写了“IPX7防水”，“IPX7”就出现了两次）。
3. 卖点：写 3 条，每条写参数表里的一个参数，3 条写 3 个不同的参数。
   - {VALUE}
   - 一条卖点里只写它那一个参数的参数值，不写别的参数的参数值。
   - 卖点里的阿拉伯数字（全角半角都算）只能是它那个参数的参数值里有的数字。
   - 每条卖点不超过 30 个字符（按第 1 条的数法数；行首的“卖点一：”这类前缀不算在内）。
4. 不写参数表里没有的功能：下面这张功能词表里的词，参数表里没有的，商品名称和卖点里都不能出现：{"、".join(FUNCTIONS["R2"])}。功能词表里没有的词，这一条不管。另外，商品名称里的阿拉伯数字也必须是参数表某个参数值里有的数字。
5. 禁用词：商品名称和卖点里不出现禁用词表里的任何词。“最”“第一”“医用级”和“美白”“护龈”这些功效宣称用语都在表里；以表为准，表里没有的词这一条不管。
6. 品牌名：商品名称和卖点里不出现品牌名单里的任何名字，中文名、英文名都算。我们自己的品牌“澄悦”不在名单里，可以写，也可以不写。

补充口径：

- 第 2 条数必含词的次数、第 4 条查功能词、第 5 条查禁用词、第 6 条查品牌名，都用同一个比对办法：{MATCH}
- 第 4 条说的“参数表里有”，是指这个功能词出现在参数表某一行的参数名或参数值里（用上面的比对办法查）。
- {TABLE}
- 第 3、4 条说的数字，{NUMBER}

{ONLY}

## 商品名称
{single_line("商品名称")}

## 商品卖点
（3 行，一行一条，依次以“卖点一：”“卖点二：”“卖点三：”开头。）
""",
    "R3": f"""# 山野户外 · 拼多多店商品标题和卖点工作规则

{INTRO}按下面的规则写一个商品标题和 4 条卖点。

1. 标题长度：标题不超过 56 个字符。{COUNT_BYTE}
2. 标题开头：标题必须以我们的品牌名“山野”开头，也就是标题的头两个字就是“山野”，前面不加任何字符。“山野”算进标题长度，不算必含词。
3. 必含词：类目必含词.md 里的每个词都要写进标题，照表里的写法原样写（全角还是半角、大写还是小写，都和表里一样）。同一个必含词不重复堆：每个必含词在标题里只能出现一次（不是必含词的词，这一条不管）。数出现次数时不分全角半角和大小写、不管空格，必含词作为别的词的一部分出现也算一次（例如必含词有“户外”，标题里写了“户外”又写了“户外用品”，“户外”就出现了两次）。
4. 卖点：写 4 条，每条写参数表里的一个参数，4 条写 4 个不同的参数。
   - 每条卖点以“【参数名】”开头，标出这条写的是哪个参数：【】里照参数表左列的参数名原样写，一个字都不改；“】”后面接着写卖点内容。
   - {VALUE.replace("每条卖点要写出", "卖点内容里要写出")}
   - 一条卖点里只写它那一个参数的参数值，不写别的参数的参数值。
   - 卖点里的阿拉伯数字（全角半角都算）只能是它那个参数的参数值里有的数字。
   - 【】里的参数名也算卖点的文字，同样要守第 5、6、7 条。如果一个参数的参数名里有禁用词表里的词或品牌名单里的名字，就不拿这个参数写卖点；如果没有，就可以拿来写。
5. 不写参数表里没有的功能：下面这张功能词表里的词，参数表里没有的，标题和卖点里都不能出现：{"、".join(FUNCTIONS["R3"])}。功能词表里没有的词，这一条不管。另外，标题里的阿拉伯数字也必须是参数表某个参数值里有的数字。
6. 禁用词：标题和卖点里不出现禁用词表里的任何词。“最”“第一”“极限”“军工级”这些夸大用语都在表里；以表为准，表里没有的词这一条不管。
7. 品牌名：标题和卖点里不出现品牌名单里的任何名字，中文名、英文名都算。我们自己的品牌“山野”不在名单里。

补充口径：

- 第 3 条数必含词的次数、第 5 条查功能词、第 6 条查禁用词、第 7 条查品牌名，都用同一个比对办法：{MATCH}
- 第 5 条说的“参数表里有”，是指这个功能词出现在参数表某一行的参数名或参数值里（用上面的比对办法查）。
- {TABLE}
- 第 4、5 条说的数字，{NUMBER}

{ONLY}

## 商品标题
{single_line("标题")}

## 卖点
（4 行，一行一条，每行以“【参数名】”开头，前面不加编号或符号。）
""",
}

# ---------------------------------------------------------------- 禁用词表、品牌名单

BANNED = {
    "R1": {
        "极限用语": ["最", "第一", "国家级", "世界级", "顶级", "顶尖", "极致", "首选", "首家", "首个", "首发", "唯一", "独家", "王牌",
                 "冠军", "销冠", "领先", "遥遥领先", "史无前例", "前所未有", "绝无仅有", "万能", "永久", "百分百", "100%", "零风险",
                 "无敌", "巅峰", "至尊", "王者", "金牌", "名牌", "特供", "专供", "免检", "秒杀", "抢爆", "爆款", "爆品", "神器",
                 "黑科技", "网红", "必备", "必买", "专业级", "医用级", "军工级", "航天级", "食品级", "母婴级", "高端", "奢华", "旗舰",
                 "正品", "官方", "TOP1", "NO.1", "BEST", "天花板", "断货王", "全网", "史上", "一流", "完美", "超值", "抢购", "限时",
                 "国货之光"],
        "健康宣称用语": ["健康", "养生", "减脂", "低脂", "减肥", "瘦身", "降糖", "控糖", "降压", "降血脂", "三高", "防癌", "抗癌", "致癌",
                   "排毒", "美容", "延年益寿", "免疫力", "零油", "无油", "0油", "少油", "低油", "不上火", "营养", "无毒", "无害",
                   "零添加", "杀菌", "除菌", "抗菌", "消毒", "除甲醛", "治疗", "滋补", "补血", "养胃", "护胃", "助消化"],
    },
    "R2": {
        "极限用语": ["最", "第一", "国家级", "世界级", "顶级", "顶尖", "极致", "首选", "首家", "唯一", "独家", "王牌", "冠军", "领先",
                 "遥遥领先", "万能", "永久", "百分百", "100%", "无敌", "巅峰", "至尊", "王者", "金牌", "特供", "秒杀", "爆款", "神器",
                 "黑科技", "网红", "必备", "必入", "专业级", "医用级", "医疗级", "院线级", "沙龙级", "军工级", "高端", "奢华", "旗舰",
                 "正品", "官方", "TOP1", "NO.1", "天花板", "全网", "史上", "完美", "超值", "限时", "零伤害", "无副作用", "立竿见影",
                 "速效", "根治"],
        "功效宣称用语": ["美白", "祛斑", "淡斑", "去黄", "亮白", "防蛀", "护龈", "牙周", "消炎", "止痛", "止血", "治疗", "修复", "防脱",
                   "生发", "固发", "养发", "护发", "不伤发", "抗衰", "去皱", "紧致", "祛痘", "除螨", "杀菌", "抑菌", "除菌", "抗菌",
                   "消毒", "减肥", "瘦身", "燃脂", "排毒", "美容", "助眠", "改善睡眠", "缓解疲劳", "缓解疼痛", "理疗", "健康", "养生",
                   "医生推荐", "牙医推荐"],
    },
    "R3": {
        "夸大用语": ["最", "第一", "国家级", "世界级", "顶级", "顶尖", "极致", "极限", "首选", "唯一", "独家", "王牌", "冠军", "领先",
                 "万能", "永久", "永不", "终身", "一辈子", "百分百", "100%", "零风险", "无敌", "巅峰", "王者", "金牌", "秒杀", "爆款",
                 "神器", "黑科技", "网红", "必备", "专业级", "军工级", "军用", "军规", "航天级", "特种兵", "防弹", "刀枪不入", "高端",
                 "旗舰", "正品", "官方", "TOP1", "NO.1", "天花板", "全网", "史上", "完美", "超值", "限时", "保命", "救命", "零失误",
                 "绝对"],
        "安全和功效宣称用语": ["防辐射", "负离子", "抗菌", "抑菌", "除螨", "保健", "理疗", "祛湿", "驱寒", "防风湿", "关节炎"],
    },
}
VARIANTS = {"TOP1": "ＴＯＰ１", "第一": "第 一", "NO.1": "Ｎｏ．１", "爆款": "爆 款", "黑科技": "黑 科 技", "0油": "０油", "健康": "健 康",
            "少油": "少 油", "BEST": "Ｂｅｓｔ", "首选": "首 选", "营养": "营 养", "神器": "神 器", "食品级": "食 品 级",
            "医用级": "医 用 级", "沙龙级": "沙 龙 级", "军工级": "军 工 级", "航天级": "航 天 级", "专业级": "专 业 级", "顶级": "顶 级",
            "极限": "极 限", "美白": "美 白", "护发": "护 发", "网红": "网 红", "100%": "１００％"}
BRANDS = {
    "R1": [("美的", "Midea"), ("九阳", "Joyoung"), ("苏泊尔", "SUPOR"), ("小熊", "Bear"), ("飞利浦", "Philips"), ("格兰仕", "Galanz"),
           ("摩飞", "Morphy Richards"), ("东菱", "Donlim"), ("北鼎", "Buydeem"), ("松下", "Panasonic"), ("象印", "Zojirushi"),
           ("虎牌", "Tiger"), ("德龙", "DeLonghi"), ("博世", "Bosch"), ("西门子", "Siemens"), ("小米", "Xiaomi"), ("米家", "Mijia"),
           ("利仁", "Liven"), ("荣事达", "Royalstar"), ("海尔", "Haier"), ("长帝", "Changdi"), ("福库", "Cuckoo"),
           ("双立人", "Zwilling"), ("特氟龙", "Teflon"), ("斯曲克斯", "Strix"), ("肖特", "SCHOTT"), ("日本电产", "Nidec"),
           ("杜邦", "DuPont"), ("康宁", "Corning")],
    "R2": [("飞利浦", "Philips"), ("欧乐B", "Oral-B"), ("松下", "Panasonic"), ("博朗", "Braun"), ("戴森", "Dyson"), ("飞科", "FLYCO"),
           ("徕芬", "Laifen"), ("素士", "Soocas"), ("舒客", "Saky"), ("笑容加", "usmile"), ("罗曼", "ROAMAN"), ("小米", "Xiaomi"),
           ("米家", "Mijia"), ("华为", "Huawei"), ("奔腾", "POVOS"), ("超人", "SID"), ("康夫", "Kangfu"), ("雷瓦", "RIWA"),
           ("倍至", "Bixdo"), ("力博得", "Lebond"), ("艾优", "ApiYoo"), ("扉乐", "Fairywill"), ("博皓", "Prooral"), ("美的", "Midea"),
           ("海尔", "Haier"), ("杜邦", "DuPont"), ("日本电产", "Nidec"), ("东芝", "Toshiba"), ("三洋", "Sanyo")],
    "R3": [("牧高笛", "MobiGarden"), ("骆驼", "CAMEL"), ("北面", "The North Face"), ("探路者", "Toread"), ("凯乐石", "Kailas"),
           ("迪卡侬", "Decathlon"), ("挪客", "Naturehike"), ("黑冰", "Blackice"), ("火枫", "Fire-Maple"), ("哥伦比亚", "Columbia"),
           ("始祖鸟", "Arcteryx"), ("狼爪", "Jack Wolfskin"), ("伯希和", "Pelliot"), ("萨洛蒙", "Salomon"), ("奥索卡", "Ozark"),
           ("科勒曼", "Coleman"), ("戈尔", "GORE-TEX"), ("吉田", "YKK"), ("考杜拉", "Cordura"), ("波拉特克", "Polartec"),
           ("科锐", "Cree"), ("杜邦", "DuPont"), ("普利马洛夫特", "PrimaLoft")],
}

# ---------------------------------------------------------------- 商品模板

# params: (参数名, 可选值, 示例卖点句子)；optional: 一半的题有；banned_slots: (参数名, 夹进去的禁用词[, 夹在哪个字之前])；
# brand_slots: (参数名, 中文名, 英文名)；rename: 边界题把参数名换成带禁用词的名字（可同时换值）；fullwidth: 边界题改成全角的参数；
# model: 边界题加的型号；title: 示例标题用的词（必含词和可选的词，按顺序，放不下就从后往前删可选的）。
TEMPLATES = {
    "airfryer": dict(
        rule="R1", category="空气炸锅",
        must=["空气炸锅", "{容量}", "可视"], must_edge=["空气炸锅", "{容量}", "可视", "家用", "大容量", "电炸锅"],
        title=["空气炸锅", "家用", "{容量}", "大容量", "可视", "电炸锅", "{功率}", "多功能", "不粘", "烤箱一体", "智能"],
        params=[("容量", ["4L", "5L", "6L"], "{v}大容量，一家人的分量一锅做好"),
                ("功率", ["1350W", "1500W"], "{v}大功率，热风足，上色快"),
                ("窗口", ["可视窗口"], "{v}，不用拉开炸篮也能看到上色"),
                ("预设菜单", ["6 个", "8 个"], "{v}预设菜单，选好按一下就开始"),
                ("定时", ["1-60 分钟", "1-90 分钟"], "{v}定时，到点自动停止加热"),
                ("温度范围", ["80-200℃"], "{v}可调，按食材选合适的温度"),
                ("涂层", ["不粘涂层"], "{v}，用完擦一擦就干净"),
                ("炸篮", ["可拆洗炸篮"], "{v}，清洗省事"),
                ("颜色", ["奶油白", "薄荷绿"], "{v}机身，摆在厨房很耐看")],
        optional=[("提醒功能", ["翻面提醒"], "{v}，到点提示翻一下食材")],
        banned_slots=[("涂层", "食品级"), ("炸篮", "食品级")], brand_slots=[("涂层", "特氟龙", "Teflon")],
        rename=("温度范围", "最高温度", ["200℃"]), fullwidth=["容量", "功率"], model="HM-AF{容量} Pro"),
    "ricecooker": dict(
        rule="R1", category="电饭煲",
        must=["电饭煲", "{容量}", "家用"], must_edge=["电饭煲", "{容量}", "IH", "家用", "智能", "多功能"],
        title=["电饭煲", "家用", "{容量}", "IH", "智能", "多功能", "电饭锅", "{功率}", "煮饭锅", "不粘内胆"],
        params=[("容量", ["3L", "4L", "5L"], "{v}容量，一家人吃饭一锅就够"),
                ("功率", ["860W", "1000W"], "{v}功率，煮饭不用久等"),
                ("加热方式", ["IH 电磁加热"], "{v}，整锅米受热均匀"),
                ("内胆", ["2mm 厚釜内胆", "3mm 厚釜内胆"], "{v}，米饭粒粒分明"),
                ("内胆涂层", ["不粘涂层"], "{v}，米饭不粘锅，好清洗"),
                ("预约", ["24 小时预约"], "{v}，早上起床就有热饭"),
                ("烹饪菜单", ["8 种", "12 种"], "{v}烹饪菜单，煮饭煮粥都能选"),
                ("适用人数", ["2-4 人", "3-6 人"], "{v}用，日常三餐都够"),
                ("颜色", ["米白色", "浅灰色"], "{v}外壳，耐脏好打理")],
        banned_slots=[("内胆", "食品级"), ("内胆涂层", "食品级")], brand_slots=[("内胆涂层", "特氟龙", "Teflon")],
        rename=("容量", "最大容量", None), fullwidth=["加热方式", "容量"], model="HM-FB{容量} Plus"),
    "kettle": dict(
        rule="R1", category="电热水壶",
        must=["电热水壶", "{容量}", "不锈钢"], must_edge=["电热水壶", "{容量}", "304", "不锈钢", "家用", "烧水壶"],
        title=["电热水壶", "家用", "{容量}", "304", "不锈钢", "烧水壶", "大容量", "{功率}", "防干烧", "开水壶"],
        params=[("容量", ["1.5L", "1.7L", "1.8L"], "{v}容量，一次烧够全家喝"),
                ("功率", ["1500W", "1800W"], "{v}功率，烧水快"),
                ("内胆", ["304 不锈钢内胆"], "{v}，用久了也好清洗"),
                ("温控", ["双重温控"], "{v}，水开自动断电"),
                ("安全保护", ["防干烧"], "{v}，空壶通电也不怕"),
                ("底座", ["360° 旋转底座"], "{v}，从哪个方向都能放回去"),
                ("开盖方式", ["一键开盖"], "{v}，单手就能加水"),
                ("颜色", ["象牙白", "雾霾蓝"], "{v}壶身，干净耐看")],
        banned_slots=[("内胆", "食品级")], brand_slots=[("温控", "斯曲克斯", "STRIX")],
        rename=("功率", "最大功率", None), fullwidth=["容量", "功率"], model="HM-K{容量} Lite"),
    "blender": dict(
        rule="R1", category="破壁机",
        must=["破壁机", "{容量}", "家用"], must_edge=["破壁机", "{容量}", "家用", "多功能", "料理机", "加热"],
        title=["破壁机", "家用", "{容量}", "多功能", "料理机", "加热", "{功率}", "豆浆机", "辅食", "榨汁"],
        params=[("容量", ["1.2L", "1.5L", "1.75L"], "{v}杯体容量，一次打出全家的量"),
                ("功率", ["1000W", "1200W"], "{v}功率，打得细"),
                ("转速", ["30000 转/分钟", "35000 转/分钟"], "{v}，豆子坚果都能打碎"),
                ("刀片", ["6 叶刀", "8 叶刀"], "{v}，搅打更均匀"),
                ("杯体", ["高硼硅玻璃杯"], "{v}，冷的热的都能装"),
                ("电机", ["纯铜电机"], "{v}，长时间打也稳"),
                ("预设程序", ["8 个", "10 个"], "{v}预设程序，豆浆米糊一键选"),
                ("加热功能", ["可加热"], "{v}，热豆浆直接打好")],
        optional=[("清洗", ["一键自清洁"], "{v}，加水按一下就洗好")],
        banned_slots=[("杯体", "医用级")], brand_slots=[("杯体", "肖特", "SCHOTT"), ("电机", "日本电产", "Nidec")],
        rename=("转速", "最高转速", None), fullwidth=["容量", "功率"], model="HM-PB{容量} Max"),
    "oven": dict(
        rule="R1", category="电烤箱",
        must=["电烤箱", "{容量}", "家用"], must_edge=["电烤箱", "{容量}", "家用", "多功能", "烘焙", "大容量"],
        title=["电烤箱", "家用", "{容量}", "大容量", "多功能", "烘焙", "{功率}", "发酵", "上下独立控温", "搪瓷"],
        params=[("容量", ["32L", "40L"], "{v}大容量，整只烤鸡也放得下"),
                ("功率", ["1600W", "1800W"], "{v}功率，预热快"),
                ("温度范围", ["40-230℃"], "{v}可调，烤肉烘焙都能用"),
                ("控温方式", ["上下管独立控温"], "{v}，上色更均匀"),
                ("定时", ["120 分钟"], "{v}定时，到点自动停止"),
                ("发酵档", ["低温发酵"], "{v}，在家也能做面包"),
                ("烤叉", ["旋转烤叉"], "{v}，烤鸡受热更匀"),
                ("内胆", ["搪瓷内胆"], "{v}，油污好擦"),
                ("炉门", ["双层玻璃门"], "{v}，外面不烫手")],
        banned_slots=[("内胆", "食品级")], brand_slots=[("炉门", "肖特", "SCHOTT")],
        rename=("温度范围", "最高温度", ["230℃"]), fullwidth=["容量", "功率"], model="HM-KX{容量} Pro"),
    "stewer": dict(
        rule="R1", category="电炖锅",
        must=["电炖锅", "{容量}", "陶瓷"], must_edge=["电炖锅", "{容量}", "陶瓷", "隔水炖", "家用", "煲汤"],
        title=["电炖锅", "家用", "{容量}", "陶瓷", "隔水炖", "煲汤", "全自动", "燕窝", "炖盅", "宝宝辅食"],
        params=[("容量", ["1.5L", "2.5L", "3.5L"], "{v}容量，一锅汤够一家人喝"),
                ("功率", ["200W", "300W"], "{v}，小火慢炖"),
                ("内胆", ["白陶瓷内胆"], "{v}，炖汤不串味"),
                ("炖法", ["隔水炖"], "{v}，汤水清亮"),
                ("预约", ["12 小时预约"], "{v}，下班回家汤就好了"),
                ("火力档位", ["3 档", "4 档"], "{v}火力可选，炖肉炖甜品都合适"),
                ("炖盅", ["玻璃小炖盅 2 个", "玻璃小炖盅 3 个"], "配{v}，一次能炖几样"),
                ("颜色", ["奶白色", "豆沙粉"], "{v}外观，摆着好看")],
        banned_slots=[("内胆", "医用级")], brand_slots=[("炖盅", "康宁", "Corning")],
        rename=("功率", "最大功率", None), fullwidth=["容量", "功率"], model="HM-DG{容量} Mini"),
    "toothbrush": dict(
        rule="R2", category="电动牙刷",
        must=["电动牙刷", "声波", "成人"], must_edge=["电动牙刷", "声波", "成人", "软毛", "情侣款", "IPX7"],
        title=["电动牙刷", "声波", "成人", "软毛", "情侣款", "IPX7", "充电式", "男女", "全自动", "学生党"],
        params=[("振动频率", ["31000 次/分钟", "38000 次/分钟"], "{v}高频振动"),
                ("清洁模式", ["3 种", "5 种"], "{v}清洁模式，按需要切换"),
                ("续航", ["30 天", "60 天"], "充满一次用{v}"),
                ("防水等级", ["IPX7 防水"], "{v}，刷完直接冲洗"),
                ("刷头", ["软毛刷头"], "{v}，刷着不扎"),
                ("提醒", ["2 分钟智能提醒"], "{v}，刷够时间心里有数"),
                ("充电方式", ["磁吸充电"], "{v}，放上去就充"),
                ("电机", ["磁悬浮电机"], "{v}，运行平稳"),
                ("颜色", ["珍珠白", "暮光紫"], "{v}机身，干净好看")],
        banned_slots=[("刷头", "医用级")], brand_slots=[("刷头", "杜邦", "DuPont"), ("电机", "日本电产", "Nidec")],
        rename=("续航", "最长续航", None), fullwidth=["防水等级", "振动频率"], model="CY-T{n} Pro"),
    "flosser": dict(
        rule="R2", category="冲牙器",
        must=["冲牙器", "便携", "家用"], must_edge=["冲牙器", "便携", "家用", "水牙线", "{水箱容量}", "电动"],
        title=["冲牙器", "便携", "家用", "水牙线", "{水箱容量}", "电动", "洗牙器", "口腔冲洗器", "充电式", "大水箱"],
        params=[("水箱容量", ["200ml", "300ml"], "{v}水箱，一次冲完全口"),
                ("冲洗档位", ["3 档", "5 档"], "{v}水压可调"),
                ("脉冲频率", ["1400 次/分钟", "1600 次/分钟"], "{v}脉冲水流"),
                ("防水等级", ["IPX7 防水"], "{v}，整机可冲洗"),
                ("续航", ["30 天", "45 天"], "充满一次用{v}"),
                ("喷头", ["4 支喷头", "5 支喷头"], "标配{v}，家人分开用"),
                ("充电方式", ["Type-C 充电"], "{v}，出门一根线就够"),
                ("电机", ["直流电机"], "{v}，水流稳定")],
        banned_slots=[("喷头", "医用级", "喷头")], brand_slots=[("电机", "日本电产", "Nidec")],
        rename=("续航", "最长续航", None), fullwidth=["水箱容量", "脉冲频率"], model="CY-WF{n}00 Pro"),
    "dryer": dict(
        rule="R2", category="吹风机",
        must=["吹风机", "高速", "家用"], must_edge=["吹风机", "高速", "家用", "大风力", "电吹风", "速干"],
        title=["吹风机", "高速", "家用", "大风力", "电吹风", "速干", "{功率}", "负离子", "宿舍用", "便携"],
        params=[("功率", ["1600W", "1800W"], "{v}功率，出风足"),
                ("风速", ["20m/s", "22m/s"], "{v}风速，头发干得快"),
                ("转速", ["11 万转/分钟", "13 万转/分钟"], "{v}，出风有劲"),
                ("电机", ["无刷电机"], "{v}，运行稳定"),
                ("负离子", ["2 亿负离子"], "{v}，吹完头发顺"),
                ("温度", ["恒温 57℃"], "{v}，吹着不烫"),
                ("风力档位", ["3 档", "4 档"], "{v}风力可调"),
                ("重量", ["350g", "400g"], "机身{v}，举着不累"),
                ("风嘴", ["磁吸风嘴"], "{v}，换风嘴方便")],
        banned_slots=[("风嘴", "沙龙级")], brand_slots=[("电机", "日本电产", "Nidec")],
        rename=("风速", "最大风速", None), fullwidth=["风速", "功率"], model="CY-HD{n} Pro"),
    "curler": dict(
        rule="R2", category="卷发棒",
        must=["卷发棒", "{管径}", "大卷"], must_edge=["卷发棒", "{管径}", "大卷", "陶瓷", "懒人", "卷发器"],
        title=["卷发棒", "{管径}", "大卷", "陶瓷", "懒人", "卷发器", "女士", "电卷棒", "蛋卷", "宿舍"],
        params=[("管径", ["28mm", "32mm"], "{v}管径，卷出自然大卷"),
                ("温度范围", ["120-210℃"], "{v}可调，按发质选温度"),
                ("温度档位", ["4 档", "5 档"], "{v}温度可选"),
                ("涂层", ["陶瓷釉涂层"], "{v}，夹着顺滑"),
                ("加热速度", ["30 秒速热"], "{v}，出门前来得及"),
                ("电源线", ["360° 旋转电源线"], "{v}，卷发时线不打结"),
                ("防烫设计", ["防烫尖头"], "{v}，手扶着更放心")],
        optional=[("自动断电", ["60 分钟自动断电"], "{v}，忘关也放心")],
        banned_slots=[("涂层", "沙龙级"), ("防烫设计", "专业级")], brand_slots=[("涂层", "杜邦", "DuPont")],
        rename=("温度范围", "最高温度", ["210℃"]), fullwidth=["管径"], model="CY-JF{管径} Pro"),
    "shaver": dict(
        rule="R2", category="剃须刀",
        must=["剃须刀", "电动", "男士"], must_edge=["剃须刀", "电动", "男士", "刮胡刀", "便携", "IPX7"],
        title=["剃须刀", "电动", "男士", "刮胡刀", "便携", "IPX7", "{刀头}", "充电式", "须刨", "礼盒"],
        params=[("刀头", ["3 刀头", "4 刀头"], "{v}浮动贴面"),
                ("续航", ["60 分钟", "90 分钟"], "充满一次用{v}"),
                ("充电时间", ["1 小时"], "{v}充满"),
                ("防水等级", ["IPX7 防水"], "{v}，刀头能直接冲洗"),
                ("显示", ["LED 数显"], "{v}，电量一眼看清"),
                ("鬓角刀", ["弹出式鬓角刀"], "{v}，修鬓角方便"),
                ("刀网", ["不锈钢刀网"], "{v}，剃得干净"),
                ("电机", ["高速电机"], "{v}，剃得干脆")],
        banned_slots=[("刀网", "医用级")], brand_slots=[("电机", "日本电产", "Nidec")],
        rename=("续航", "最长续航", None), fullwidth=["防水等级", "刀头"], model="CY-S{n}00 Pro"),
    "massager": dict(
        rule="R2", category="筋膜枪",
        must=["筋膜枪", "肌肉", "便携"], must_edge=["筋膜枪", "肌肉", "便携", "迷你", "{档位}", "运动"],
        title=["筋膜枪", "肌肉", "便携", "迷你", "{档位}", "运动", "健身", "按摩器", "小型", "男女"],
        params=[("档位", ["20 档", "30 档"], "{v}力度可调"),
                ("枪头", ["4 个枪头", "6 个枪头"], "配{v}，不同部位换着用"),
                ("振幅", ["10mm", "12mm"], "{v}振幅，打得到位"),
                ("续航", ["8 小时", "10 小时"], "充满一次用{v}"),
                ("重量", ["450g", "600g"], "机身{v}，单手握得住"),
                ("电机", ["无刷电机"], "{v}，运行稳"),
                ("噪音", ["45dB"], "运行噪音{v}"),
                ("机身材质", ["铝合金机身"], "{v}，耐摔")],
        optional=[("显示", ["LED 数显"], "{v}，档位看得清")],
        banned_slots=[("机身材质", "军工级")], brand_slots=[("电机", "日本电产", "Nidec")],
        rename=("续航", "最长续航", None), fullwidth=["振幅", "档位"], model="CY-JM{n} Mini"),
    "tent": dict(
        rule="R3", category="帐篷",
        must=["帐篷", "户外", "露营"], must_edge=["帐篷", "户外", "露营", "加厚", "防雨", "{适用人数}"],
        title=["帐篷", "户外", "露营", "加厚", "防雨", "{适用人数}", "全自动", "速开", "野营", "便携式", "公园", "沙滩"],
        params=[("适用人数", ["2-3 人", "3-4 人"], "{v}，一家人出游够住"),
                ("防水指数", ["PU3000mm", "PU4000mm"], "{v}，下雨天也能住"),
                ("帐杆", ["铝合金帐杆"], "{v}，轻又结实"),
                ("面料", ["210T 涤纶布"], "{v}，耐磨"),
                ("搭建方式", ["自动速开"], "{v}，到营地很快搭好"),
                ("重量", ["2.5kg", "3.2kg"], "整顶{v}，背着走不累"),
                ("门窗", ["双门双窗"], "{v}，通风好"),
                ("拉链", ["双向拉链"], "{v}，进出方便"),
                ("抗风等级", ["6 级", "8 级"], "{v}抗风，山顶也能扎营")],
        banned_slots=[("帐杆", "军工级")], brand_slots=[("拉链", "吉田", "YKK")],
        rename=("抗风等级", "最高抗风等级", None), fullwidth=["适用人数", "重量"], model="SY-ZP{n} Plus"),
    "sleepingbag": dict(
        rule="R3", category="睡袋",
        must=["睡袋", "成人", "户外"], must_edge=["睡袋", "成人", "户外", "加厚", "秋冬", "羽绒"],
        title=["睡袋", "成人", "户外", "加厚", "秋冬", "羽绒", "露营", "便携", "单人", "隔脏", "午休", "保暖"],
        params=[("舒适温度", ["8℃", "3℃"], "{v}舒适温度，春秋夜里也暖和"),
                ("填充物", ["白鸭绒"], "{v}填充，蓬松暖和"),
                ("充绒量", ["800g", "1000g"], "充绒量{v}"),
                ("重量", ["1.5kg", "1.8kg"], "整袋{v}，背着轻"),
                ("拉链", ["双向拉链"], "{v}，热了能拉开透气"),
                ("面料", ["防泼水面料"], "{v}，沾了露水擦擦就干"),
                ("收纳尺寸", ["38×20cm"], "收起来只有{v}"),
                ("拼接", ["可双人拼接"], "{v}，两个人出行方便")],
        extra=("极限温度", ["-5℃", "-7℃"], "{v}也能睡"),
        banned_slots=[("填充物", "顶级")], brand_slots=[("拉链", "吉田", "YKK")],
        rename=None, fullwidth=["充绒量", "重量"], model="SY-SD{n} Pro"),
    "headlamp": dict(
        rule="R3", category="头灯",
        must=["头灯", "强光", "户外"], must_edge=["头灯", "强光", "户外", "超亮", "夜钓", "头戴式"],
        title=["头灯", "强光", "户外", "超亮", "夜钓", "头戴式", "充电", "LED", "钓鱼", "夜跑", "登山", "应急"],
        params=[("亮度", ["800 流明", "1200 流明"], "{v}，夜路看得清"),
                ("续航", ["8 小时", "12 小时"], "充满一次亮{v}"),
                ("充电方式", ["Type-C 充电"], "{v}，手机线就能充"),
                ("防水等级", ["IPX6 防水"], "{v}，下雨也能用"),
                ("照射距离", ["150 米", "200 米"], "能照到{v}远"),
                ("重量", ["68g", "85g"], "整灯{v}，戴久了不压头"),
                ("灯珠", ["LED 灯珠"], "{v}，光线稳定"),
                ("外壳", ["铝合金外壳"], "{v}，耐摔")],
        optional=[("开关方式", ["挥手感应开关"], "{v}，戴着手套也好开")],
        banned_slots=[("外壳", "航天级")], brand_slots=[("灯珠", "科锐", "Cree")],
        rename=("照射距离", "最远照射距离", None), fullwidth=["亮度", "重量"], model="SY-HL{n} Pro"),
    "chair": dict(
        rule="R3", category="折叠椅",
        must=["折叠椅", "便携", "户外"], must_edge=["折叠椅", "便携", "户外", "靠背", "钓鱼", "月亮椅"],
        title=["折叠椅", "便携", "户外", "靠背", "钓鱼", "月亮椅", "露营", "椅子", "沙滩", "写生", "午休"],
        params=[("承重", ["120kg", "150kg"], "承重{v}，坐着稳"),
                ("支架", ["铝合金支架"], "{v}，轻便不生锈"),
                ("面料", ["600D 牛津布"], "{v}，耐磨好擦"),
                ("重量", ["1.2kg", "1.5kg"], "整椅{v}，单手拎走"),
                ("收纳尺寸", ["35×12×10cm"], "收起来只有{v}"),
                ("靠背", ["高靠背"], "{v}，坐久了腰不累"),
                ("折叠方式", ["一键折叠"], "{v}，几秒就收好"),
                ("扶手", ["带扶手"], "{v}，起身方便")],
        banned_slots=[("支架", "航天级")], brand_slots=[("面料", "考杜拉", "Cordura")],
        rename=("承重", "最大承重", None), fullwidth=["承重", "重量"], model="SY-YL{n} Lite"),
    "jacket": dict(
        rule="R3", category="冲锋衣",
        must=["冲锋衣", "男女", "户外"], must_edge=["冲锋衣", "男女", "户外", "三合一", "登山服", "外套"],
        title=["冲锋衣", "男女", "户外", "三合一", "登山服", "外套", "秋冬", "防水", "加绒", "情侣款", "旅行"],
        params=[("防水指数", ["10000mm", "15000mm"], "防水指数{v}，小雨不怕"),
                ("透湿量", ["5000g", "8000g"], "透湿量{v}，走热了也不闷"),
                ("面料", ["三层压胶面料"], "{v}，挡风挡雨"),
                ("帽子", ["可拆卸帽子"], "{v}，天晴了能摘"),
                ("拉链", ["防水拉链"], "{v}，雨水不往里渗"),
                ("内胆", ["抓绒内胆"], "{v}，冷天穿上就暖"),
                ("袖口", ["魔术贴袖口"], "{v}，松紧能调"),
                ("颜色", ["墨绿", "藏青"], "{v}配色，耐脏")],
        banned_slots=[("面料", "专业级")],
        brand_slots=[("面料", "戈尔", "GORE-TEX"), ("拉链", "吉田", "YKK"), ("内胆", "波拉特克", "Polartec")],
        rename=None, fullwidth=["防水指数", "透湿量"], model="SY-CF{n} Pro"),
}

SPECS = [
    ("t01", "train", "common", "airfryer"), ("t02", "train", "common", "toothbrush"), ("t03", "train", "common", "ricecooker"),
    ("t04", "train", "common", "flosser"), ("t05", "train", "common", "kettle"), ("t06", "train", "common", "dryer"),
    ("t07", "train", "common", "blender"), ("t08", "train", "common", "curler"), ("t09", "train", "common", "oven"),
    ("t10", "train", "common", "shaver"), ("t11", "train", "edge", "airfryer"), ("t12", "train", "edge", "toothbrush"),
    ("t13", "train", "edge", "ricecooker"), ("t14", "train", "edge", "flosser"), ("t15", "train", "edge", "kettle"),
    ("t16", "train", "edge", "dryer"), ("t17", "train", "edge", "blender"), ("t18", "train", "edge", "curler"),
    ("t19", "train", "edge", "oven"), ("t20", "train", "edge", "shaver"),
    ("x01", "same", "common", "stewer"), ("x02", "same", "common", "massager"), ("x03", "same", "common", "airfryer"),
    ("x04", "same", "common", "toothbrush"), ("x05", "same", "common", "kettle"), ("x06", "same", "edge", "massager"),
    ("x07", "same", "edge", "stewer"), ("x08", "same", "edge", "dryer"), ("x09", "same", "edge", "ricecooker"),
    ("x10", "same", "edge", "curler"),
    ("y01", "new", "common", "tent"), ("y02", "new", "common", "sleepingbag"), ("y03", "new", "common", "headlamp"),
    ("y04", "new", "common", "chair"), ("y05", "new", "common", "jacket"), ("y06", "new", "edge", "sleepingbag"),
    ("y07", "new", "edge", "tent"), ("y08", "new", "edge", "headlamp"), ("y09", "new", "edge", "chair"),
    ("y10", "new", "edge", "jacket"),
]

TASK = ("你是电商店铺的运营，负责给新上架的商品写标题和卖点。每次会给你这次适用的工作规则、商品参数表、类目必含词、禁用词表和品牌名单，"
        "按这次给的工作规则写出标题和卖点，写好的内容会直接贴进商品后台。")
ONBOARDING = "以后每个新品，我都会把这次适用的工作规则、参数表、类目必含词、禁用词表和品牌名单一起发给你。不同店铺、不同平台的规则不一样，以当次给的为准。"
CRITERIA = [
    ("T-title", "standard",
     "标题（有的规则叫商品名称）：只看标题段里那一行标题本身；这一行前后如果加了引号、书名号、括号、加粗符号或“标题：”这类字样，"
     "去掉它们再判（这些符号和字样只在 T-format 记）。要求：按这次工作规则的数法，字符数在规则规定的范围里（以测量值的标题字符数为准；"
     "规则有下限的也不能少于下限）；类目必含词每个都照必含词表的写法原样出现，而且只出现一次（次数按规则的比对办法数，测量值列了原样次数和"
     "规范化后的次数）；规则要求以品牌名开头的，标题的开头必须正好是这个品牌名；标题里不出现参数表里没有的功能词表词语；标题里的阿拉伯数字"
     "都是参数表参数值里有的数字。超出范围或不够长、缺必含词或写法和表里不同、必含词重复、开头不对、多了参数表里没有的功能词或数字，"
     "每处记一处。禁用词和品牌名记在 T-words，不在这里记。"),
    ("T-words", "red_line",
     "禁用词和品牌名：只看交付本身——标题那一行和卖点段里的每条卖点（含卖点开头【】里的参数名）；两段前后或段里多出来的说明文字只在 "
     "T-format 记，里面出现的词不在这里记。按这次规则的比对办法（全角转半角、不分大小写、去掉空格后，名单上的词只要出现在文字里就算，"
     "哪怕是别的词的一部分），标题和卖点里不出现禁用词表里的词和品牌名单里的名字（中文名、英文名都算；我们自己的品牌名不算）。测量值列出了"
     "命中的词和所在的原文。每命中一处记一处；参数值里夹带的禁用词或品牌名被照抄进来也算。"),
    ("T-points", "standard",
     "卖点和参数：只看卖点段里的卖点行（多出来的说明行不算卖点，只在 T-format 记）。卖点条数符合这次规则；每条写参数表里的一个参数，并写出"
     "它的参数值（照参数表写，只许去空格、全角改半角、删掉值里夹带的禁用词和品牌名；参考答案列了每个参数应写出的值）；不同的卖点写不同的参数；"
     "一条卖点里不写别的参数的值；卖点里的阿拉伯数字（不算行首编号）只能是它那个参数的参数值里有的数字；卖点里不出现参数表里没有的功能词表"
     "词语（只看规则里那张功能词表）；规则要求每条用“【参数名】”开头的，【】里必须是这条所写参数在参数表里的原名（缺了【参数名】或名字不对"
     "都记在这里）。条数不对、没写出参数值或写法改了、一条写了两个参数的值、两条写同一个参数、数字或功能词不在参数表里、【】里的参数名缺"
     "或不对，每处记一处。禁用词和品牌名记在 T-words，不在这里记。"),
    ("T-format", "standard",
     "交付格式：回复里只有规则要求的两段，段名（每段以“## 段名”开头）和顺序照规则。两段前后或段里多出来的文字（开场白、说明、字数统计、"
     "自查过程、另加的段，不管有几处、有多长）合起来只记一处，而且只在本项记。标题段只有一行标题，前面不加“标题：”这类字样，前后不加引号、"
     "书名号、括号或加粗符号；卖点每行一条，行首写法照规则（“1. ”这样的编号、“卖点一：”这样的前缀，或者直接以“【”开头、前面不加编号；"
     "【】里的参数名对不对记在 T-points）；规则对单条卖点有长度上限的，按规则的数法不超过上限（以测量值为准；没有上限的规则这一部分不适用）。"
     "段名或顺序不对、有多余文字、标题加了字样或符号、卖点行首写法不对、单条卖点超长，每处记一处。"),
]

# ---------------------------------------------------------------- 文字工具（和规则的口径一一对应）


def norm(text: str) -> str:
    """规则的比对办法：全角字母数字符号换半角，英文字母当小写，去掉所有空格。"""
    out = []
    for ch in text:
        if 0xFF01 <= ord(ch) <= 0xFF5E:
            ch = chr(ord(ch) - 0xFEE0)
        if not ch.isspace():
            out.append(ch.lower())
    return "".join(out)


def narrow(text: str) -> str:
    return "".join(chr(ord(ch) - 0xFEE0) if 0xFF01 <= ord(ch) <= 0xFF5E else ch for ch in text)


def wide(text: str) -> str:
    return "".join(chr(ord(ch) + 0xFEE0) if ch.isascii() and (ch.isalnum() or ch in "./%") else ch for ch in text)


def vnorm(text: str) -> str:
    """参数值的比对：只许去空格、全角改半角（大小写不许改）。"""
    return "".join(ch for ch in narrow(text) if not ch.isspace())


def hanzi(ch: str) -> bool:
    return "一" <= ch <= "鿿" or "㐀" <= ch <= "䶿"


def length(text: str, scheme: str) -> int:
    if scheme == "byte":
        return sum(1 if " " <= ch <= "~" else 2 for ch in text)
    return sum(2 if hanzi(ch) else 0 if ch.isspace() else 1 for ch in text)


def numbers(text: str) -> list[str]:
    """连在一起的一串阿拉伯数字（全角先换半角；空格隔开的是两个数）。"""
    return re.findall(r"[0-9]+(?:\.[0-9]+)?", narrow(text))


def hits(text: str, words) -> list[str]:
    plain = norm(text)
    return [w for w in words if norm(w) and norm(w) in plain]


def strip_words(value: str, words) -> str:
    """把参数值里出现的名单词（按比对办法找）删掉，剩下的原样保留。"""
    spots = [i for i, ch in enumerate(value) if not ch.isspace()]
    flat = norm(value)
    assert len(flat) == len(spots), value
    drop = set()
    for word in words:
        key, start = norm(word), 0
        while key and (found := flat.find(key, start)) >= 0:
            drop.update(spots[found:found + len(key)])
            start = found + 1
    kept = "".join(ch for i, ch in enumerate(value) if i not in drop)
    return re.sub(r"\s+", " ", kept).strip()


def join(tokens) -> str:
    out = ""
    for token in tokens:
        if out and out[-1].isascii() and out[-1].isalnum() and token[0].isascii() and token[0].isalnum():
            out += " "
        out += token
    return out


# ---------------------------------------------------------------- 一道题


def banned_entries(rule: str) -> list[tuple[str, str]]:
    return [(group, word) for group, words in BANNED[rule].items() for word in words]


def build(spec, rng) -> dict:
    name, group, segment, key = spec
    t = TEMPLATES[key]
    rule = t["rule"]
    r = RULES[rule]
    edge = segment == "edge"
    rows = [{"key": p, "name": p, "value": rng.choice(pool), "sentence": s} for p, pool, s in t["params"]]
    for p, pool, s in t.get("optional", ()):
        if rng.random() < 0.5:
            rows.append({"key": p, "name": p, "value": rng.choice(pool), "sentence": s})
    if name == "t01":  # 文档里的样例：容量 5L、可视窗口、功率 1500W、8 个预设菜单、定时 1 到 90 分钟
        fixed = {"容量": "5L", "功率": "1500W", "预设菜单": "8 个", "定时": "1-90 分钟"}
        for row in rows:
            row["value"] = fixed.get(row["key"], row["value"])
    plain = {row["key"]: row["value"].replace(" ", "") for row in rows}
    must = [w.format(**plain) for w in (t["must_edge"] if edge else t["must"])]
    by_key = {row["key"]: row for row in rows}
    entries = banned_entries(rule)
    pairs = [(b, s) for b in t["banned_slots"] for s in t["brand_slots"] if b[0] in by_key and s[0] in by_key and b[0] != s[0]]
    banned_slot, brand_slot = rng.choice(pairs)
    notes = {}
    # 参数值里夹带的禁用词
    row = by_key[banned_slot[0]]
    word = banned_slot[1]
    if len(banned_slot) > 2:
        at = row["value"].index(banned_slot[2])
        row["value"] = row["value"][:at] + word + row["value"][at:]
    else:
        row["value"] = word + row["value"]
    variants = {}
    if edge:
        pool = [w for _, w in entries if w in VARIANTS and w not in ("TOP1", "第一", word)]
        chosen = ["TOP1", "第一"] + ([word] if word in VARIANTS else []) + rng.sample(pool, 4)
        variants = {w: VARIANTS[w] for w in chosen}
    listed = [(g, variants.get(w, w)) for g, w in entries]
    notes.setdefault(row["key"], []).append(
        f"参数值里夹着禁用词“{word}”" + (f"（禁用词表里写成“{variants[word]}”）" if word in variants else "") + "，写这条参数时要删掉")
    # 参数值里夹带的其他品牌名
    row = by_key[brand_slot[0]]
    cn, en = brand_slot[1], brand_slot[2]
    if edge:
        shown = rng.choice([en, en.upper(), en.lower(), wide(en)])
        row["value"] = f"{shown} {row['value']}"
    else:
        shown = cn
        row["value"] = cn + row["value"]
    notes.setdefault(row["key"], []).append(f"参数值里夹着其他品牌名“{shown}”（品牌名单：{cn} / {en}），写这条参数时要删掉")
    renamed = None
    if edge:
        for k in t["fullwidth"]:
            by_key[k]["value"] = wide(by_key[k]["value"])
            notes.setdefault(k, []).append("参数值是全角写法，卖点里可以照写，也可以改成半角")
        if t.get("rename"):
            k, new, pool = t["rename"]
            by_key[k]["name"] = new
            if pool:
                by_key[k]["value"] = rng.choice(pool)
            renamed = new
        if t.get("extra"):
            p, pool, s = t["extra"]
            rows.insert(1, {"key": p, "name": p, "value": rng.choice(pool), "sentence": s})
            renamed = p
        rows.insert(0, {"key": "型号", "name": "型号", "value": t["model"].format(n=rng.randint(2, 9), **plain), "sentence": None})
    words = [w for _, w in listed] + [n for pair in BRANDS[rule] for n in pair]
    for row in rows:
        row["clean"] = strip_words(row["value"], words)
        assert row["clean"], (name, row)
    return {"name": name, "group": group, "segment": segment, "key": key, "rule": rule, "rows": rows, "must": must,
            "listed": listed, "variants": variants, "words": words, "notes": notes, "renamed": renamed,
            "traps": {"banned": banned_slot, "brand": (brand_slot[0], shown, cn, en)}}


def table_text(q) -> str:
    t = TEMPLATES[q["key"]]
    lines = [f"# 参数表：{RULES[q['rule']]['brand']}{t['category']}", "", "| 参数名 | 参数值 |", "|---|---|"]
    lines += [f"| {row['name']} | {row['value']} |" for row in q["rows"]]
    return "\n".join(lines) + "\n"


def must_text(q) -> str:
    noun = RULES[q["rule"]]["noun"]
    return "\n".join([f"# 类目必含词：{TEMPLATES[q['key']]['category']}", "", f"{noun}里要有下面每个词：", ""]
                     + [f"- {w}" for w in q["must"]]) + "\n"


def banned_text(q) -> str:
    lines = ["# 禁用词表", "", f"共 {len(q['listed'])} 个词。", ""]
    for group in BANNED[q["rule"]]:
        lines += [f"## {group}", ""] + [f"- {w}" for g, w in q["listed"] if g == group] + [""]
    return "\n".join(lines)


def brand_text(q) -> str:
    pairs = BRANDS[q["rule"]]
    lines = ["# 品牌名单", "", f"下面是其他品牌，共 {len(pairs)} 个。", "", "| 中文名 | 英文名 |", "|---|---|"]
    return "\n".join(lines + [f"| {cn} | {en} |" for cn, en in pairs]) + "\n"


def question_text(q) -> str:
    r, t = RULES[q["rule"]], TEMPLATES[q["key"]]
    what = "商品名称" if q["rule"] == "R2" else "商品标题"
    text = f"{r['company']}{r['shop']}要上新一款{t['category']}，帮我写{what}和卖点。"
    if q["segment"] == "edge":
        text += f"{what}尽量把长度用足，多放几个搜索词。"
    return (text + "\n\n这次适用的工作规则、商品参数表、类目必含词、禁用词表和品牌名单在工作目录：工作规则.md、参数表.md、"
            "类目必含词.md、禁用词表.md、品牌名单.md。")


def point_line(rule: str, index: int, row: dict, sentence: str) -> str:
    style = RULES[rule]["style"]
    if style == "number":
        return f"{index}. {sentence}"
    if style == "chinese":
        return f"卖点{'一二三四五'[index - 1]}：{sentence}"
    return f"【{row['name']}】{sentence}"


def example(q, rng) -> tuple[str, str, list[str], list[dict]]:
    r, t = RULES[q["rule"]], TEMPLATES[q["key"]]
    table = " ".join(f"{row['name']} {row['value']}" for row in q["rows"])
    absent = [w for w in FUNCTIONS[q["rule"]] if not hits(table, [w])]
    plain = {row["key"]: narrow(row["clean"]).replace(" ", "") for row in q["rows"]}
    tokens = [r["brand"]] + [tok.format(**plain) for tok in t["title"]]
    tokens = [tok for tok in tokens if not hits(tok, absent)]
    required = {r["brand"], *q["must"]}
    while length(join(tokens), r["scheme"]) > r["max"]:
        drop = max(i for i, tok in enumerate(tokens) if tok not in required)
        del tokens[drop]
    title = join(tokens)
    usable = [row for row in q["rows"] if row["sentence"] and row["name"] == row["key"] and not hits(row["name"], q["words"])]
    traps = [row for row in usable if row["clean"] != row["value"]]
    others = [row for row in usable if row not in traps]
    rng.shuffle(others)
    chosen = (traps[:2] + others)[:r["count"]]
    chosen.sort(key=q["rows"].index)
    lines = [point_line(q["rule"], i, row, row["sentence"].format(v=narrow(row["clean"]))) for i, row in enumerate(chosen, 1)]
    text = f"## {r['sections'][0]}\n{title}\n\n## {r['sections'][1]}\n" + "\n".join(lines) + "\n"
    return text, title, lines, chosen


def audit(q, title: str, lines: list[str], chosen: list[dict]) -> None:
    """示例必须完全符合规则；不符合就 assert（换种子重试）。"""
    r = RULES[q["rule"]]
    table = " ".join(f"{row['name']} {row['value']}" for row in q["rows"])
    present = [w for w in FUNCTIONS[q["rule"]] if hits(table, [w])]
    absent = [w for w in FUNCTIONS[q["rule"]] if w not in present]
    pool = {n for row in q["rows"] for n in numbers(row["value"])}
    size = length(title, r["scheme"])
    assert size <= r["max"] and (r["min"] is None or size >= r["min"]), (q["name"], title, size)
    assert r["max"] - size <= 6, (q["name"], "example title not near the limit", size)
    for word in q["must"]:
        assert title.count(word) == 1 and norm(title).count(norm(word)) == 1, (q["name"], word, title)
    assert not r["prefix"] or title.startswith(r["prefix"]), title
    assert not hits(title, q["words"]) and not hits(title, absent), (q["name"], title)
    assert set(numbers(title)) <= pool, (q["name"], numbers(title), pool)
    assert len(lines) == r["count"] and len({row["key"] for row in chosen}) == r["count"]
    for line, row in zip(lines, chosen):
        body = re.sub(r"^(\d+\. |卖点[一二三四五]：)", "", line)
        assert not hits(body, q["words"]) and not hits(body, absent), (q["name"], line)
        written = [other["key"] for other in q["rows"] if vnorm(other["clean"]) in vnorm(body)]
        assert written == [row["key"]], (q["name"], line, written)
        assert set(numbers(body)) <= set(numbers(row["value"])), (q["name"], line)
        if r["point_max"]:
            assert length(body, r["scheme"]) <= r["point_max"], (q["name"], line, length(body, r["scheme"]))


def trap_checks(q, title: str) -> None:
    """陷阱有效：照抄参数值会命中禁用词/品牌名；边界题的全角、型号、变体、参数名里的禁用词确实存在。"""
    r = RULES[q["rule"]]
    words = q["words"]
    table = "\n".join(f"{row['name']} {row['value']}" for row in q["rows"])  # 只看参数行，不看表名
    raw_values = [row["value"] for row in q["rows"]]
    assert sum(bool(hits(v, words)) for v in raw_values) >= 2, q["name"]
    for row in q["rows"]:
        assert not hits(row["clean"], words), (q["name"], row)
    assert not [w for w in q["must"] if hits(w, words)], q["name"]
    assert len(title) != length(title, r["scheme"]), q["name"]  # 按字数数和按规则数不一样
    if q["segment"] == "common":
        assert not re.search(r"[！-～]", table) and not any(row["key"] == "型号" for row in q["rows"]), q["name"]
        assert all(w == norm(w) or w.isupper() or "." in w for _, w in q["listed"] if w.isascii()), q["name"]
    else:
        assert re.search(r"[！-～]", table), q["name"]
        model = q["rows"][0]["value"]
        assert " " in model and re.search(r"[A-Za-z]", model), model
        assert "ＴＯＰ１" in [w for _, w in q["listed"]] and "第 一" in [w for _, w in q["listed"]], q["name"]
        word = q["traps"]["banned"][1]
        listed = [w for _, w in q["listed"]]
        if word in q["variants"]:
            assert word not in listed and q["variants"][word] in listed, q["name"]
        _, shown, cn, en = q["traps"]["brand"]
        assert cn not in table and en not in table.replace(shown, "") and norm(en) in norm(table), q["name"]
        if q["rule"] == "R1":
            assert any(norm(w) in norm(model) for w in q["must"]), (q["name"], model)
        changed = [w for w in q["must"] for row in q["rows"] if row["key"] in TEMPLATES[q["key"]]["fullwidth"]
                   and norm(w) in norm(row["value"])]
        assert all(w not in row["value"] for w in changed for row in q["rows"]
                   if row["key"] in TEMPLATES[q["key"]]["fullwidth"] and norm(w) in norm(row["value"])), q["name"]
        if q["renamed"]:
            assert hits(q["renamed"], words), q["name"]


def reference(q, text: str, title: str, chosen: list[dict]) -> dict:
    r = RULES[q["rule"]]
    table = " ".join(f"{row['name']} {row['value']}" for row in q["rows"])
    present = [w for w in FUNCTIONS[q["rule"]] if hits(table, [w])]
    absent = [w for w in FUNCTIONS[q["rule"]] if w not in present]
    noun = r["noun"]
    must_notes = {}
    for word in q["must"]:
        for row in q["rows"]:
            if norm(word) in norm(row["value"]) and norm(word) != norm(row["value"]):
                must_notes.setdefault(word, []).append(f"{row['name']}“{row['value']}”")
    differ = {w: [f"{row['name']}写作“{row['value']}”" for row in q["rows"] if norm(w) in norm(row["value"]) and w not in row["value"]]
              for w in q["must"]}
    differ = {w: v for w, v in differ.items() if v}
    params = []
    for row in q["rows"]:
        item = {"参数名": row["name"], "参数表里的值": row["value"], "卖点里要写出的值": row["clean"],
                "值里的数字": numbers(row["value"]) or "无"}
        tips = list(q["notes"].get(row["key"], []))
        if row["key"] == "型号":
            inside = [other["name"] for other in q["rows"] if other is not row and vnorm(other["clean"]) in vnorm(row["clean"])]
            tips.append("型号是一个参数" + (f"；它的值里含有{('、'.join(inside))}的参数值，写型号这条卖点就同时写出了那个参数的值" if inside else ""))
        if hits(row["name"], q["words"]):
            found = hits(row["name"], q["words"])
            tips.append(f"参数名里有禁用词“{'”“'.join(found)}”，卖点里不能出现这个参数名"
                        + ("；按规则第 4 条，这个参数不能拿来写卖点" if r["style"] == "label" else ""))
        if tips:
            item["注意"] = "；".join(tips)
        params.append(item)
    breakdown = {"按本题规则的字符数": length(title, r["scheme"]), "直接数字数（不按规则）": len(title)}
    return {
        "规则集": f"{q['rule']}（{r['company']}{r['shop']}）",
        f"{noun}要求": {
            "字符数法": "半角字符算 1，其余每个字符算 2" if r["scheme"] == "byte" else "汉字算 2，空格不算，其余每个字符算 1",
            "范围": (f"不少于 {r['min']}、不超过 {r['max']} 个字符" if r["min"] else f"不超过 {r['max']} 个字符"),
            "开头": f"必须以“{r['prefix']}”开头" if r["prefix"] else "本规则对开头没有要求（T-title 的开头一项不适用）",
            "必含词（照这个写法原样写，各只出现一次）": q["must"],
            "必含词在参数表里写法不同的（标题里要照必含词表写）": differ or "无",
            "值里含有必含词的参数（标题里写了这个值，就不能再单独写这个必含词）": must_notes or "无",
            "标题里能用的数字（参数表参数值里的全部数字）": sorted({n for row in q["rows"] for n in numbers(row["value"])},
                                                    key=lambda n: float(n)),
        },
        "卖点要求": {
            "条数": r["count"],
            "行首写法": {"number": "依次以“1. ”到“5. ”开头", "chinese": "依次以“卖点一：”“卖点二：”“卖点三：”开头",
                     "label": "每行以“【参数名】”开头，不加编号"}[r["style"]],
            "单条长度上限": (f"每条不超过 {r['point_max']} 个字符（按商品名称的数法，不算行首前缀）" if r["point_max"]
                       else "本规则没有单条长度上限（T-format 的单条长度一项不适用）"),
            "【参数名】": "本规则要求，【】里照参数表原名写" if r["style"] == "label" else "本规则不要求（T-points 的【】一项不适用）",
            "各参数（卖点里要写出“卖点里要写出的值”；值里的空格可以去掉，全角可以改半角）": params,
        },
        "功能词": {"参数表里有的（可以写）": present or "无", "参数表里没有的（标题和卖点都不能写）": absent},
        "禁用词表里写法特殊的词（比对时先规范化）": {v: norm(v) for v in q["variants"].values()} or "无（常见题的禁用词表都是普通写法）",
        "参数表里夹带的禁用词和品牌名": [f"{row['name']}：{'、'.join(hits(row['name'] + ' ' + row['value'], q['words']))}"
                              for row in q["rows"] if hits(row["name"] + " " + row["value"], q["words"])],
        "交付段落": [f"## {s}" for s in r["sections"]],
        "示例交付（一份完全符合规则的写法；员工的标题和卖点可以和它不同，只要符合规则）": text,
        "示例标题字符数": breakdown,
        "示例卖点对应的参数": [row["name"] for row in chosen],
    }


def scenario_package():
    (SCENARIO / "personas").mkdir(parents=True, exist_ok=True)
    (SCENARIO / "profile.md").write_text(TASK + "\n")
    (SCENARIO / "onboarding.md").write_text(ONBOARDING + "\n")
    (SCENARIO / "personas" / "operator.md").write_text("店铺运营主管发来新品，要标题和卖点；每道题的参数表、必含词、禁用词表、品牌名单和规则由脚本给出。\n")
    (SCENARIO / "scenario.json").write_text(json.dumps({
        "initial": [],
        "criteria": [{"id": i, "check": text, "severity": severity} for i, severity, text in CRITERIA],
    }, ensure_ascii=False, indent=1) + "\n")
    visible = ["counterpart", "analyst", "curator"]
    (SCENARIO / "contract.json").write_text(json.dumps(
        {"checks": {i: {"visibility": visible} for i, _, _ in CRITERIA}}, ensure_ascii=False, indent=1) + "\n")


def static_checks():
    for rule, text in RULE_TEXT.items():
        r = RULES[rule]
        assert "、".join(FUNCTIONS[rule]) in text and f"不超过 {r['max']} 个字符" in text, rule
        assert all(f"## {s}\n" in text for s in r["sections"]) and f"写 {r['count']} 条" in text, rule
        words = [w for _, w in banned_entries(rule)] + [n for pair in BRANDS[rule] for n in pair]
        assert len(set(words)) == len(words), rule
        assert not hits(r["brand"], words) and not hits(r["company"], words), rule
    for key, t in TEMPLATES.items():
        rule = t["rule"]
        words = [w for _, w in banned_entries(rule)] + [n for pair in BRANDS[rule] for n in pair]
        for p, pool, sentence in t["params"] + t.get("optional", []):
            assert not hits(p, words) and not re.search(r"\d", p), (key, p)
            for value in pool:
                assert not hits(value, words), (key, value)
                assert not hits(sentence.replace("{v}", ""), words), (key, sentence)
                assert set(numbers(sentence.replace("{v}", ""))) == set(), (key, sentence)
        for tok in t["title"]:
            assert not hits(tok, words), (key, tok)


def main():
    static_checks()
    names = [s[0] for s in SPECS]
    assert len(names) == len(set(names)) == 40
    for spec in SPECS:
        name, group, segment, key = spec
        rule = TEMPLATES[key]["rule"]
        number = int(name[1:])
        expect = "R3" if name[0] == "y" else ("R1" if number % 2 else "R2")
        assert rule == expect, (name, rule)
        assert segment == ("common" if (name[0] == "t" and number <= 10) or (name[0] != "t" and number <= 5) else "edge"), name
    (HERE / "rules").mkdir(exist_ok=True)
    for rule, text in RULE_TEXT.items():
        (HERE / "rules" / f"{rule}.md").write_text(text)
    bank, scripts, retries = [], [], 0
    for spec in SPECS:
        name = spec[0]
        for salt in range(50):
            rng = random.Random(name if salt == 0 else f"{name}:{salt}")
            q = build(spec, rng)
            try:
                text, title, lines, chosen = example(q, rng)
                audit(q, title, lines, chosen)
                trap_checks(q, title)
                break
            except (AssertionError, ValueError) as exc:
                retries += 1
                where = traceback.extract_tb(exc.__traceback__)[-1]
                print("retried:", name, salt, f"line {where.lineno}", str(exc)[:160])
        else:
            raise RuntimeError(f"{name}: no seed passes the checks")
        files = {"工作规则.md": RULE_TEXT[q["rule"]], "参数表.md": table_text(q), "类目必含词.md": must_text(q),
                 "禁用词表.md": banned_text(q), "品牌名单.md": brand_text(q)}
        item = {"name": name, "group": spec[1], "segment": spec[2], "rules": q["rule"], "text": question_text(q), "files": files,
                "reference": reference(q, text, title, chosen)}
        got = measure(item, text)
        assert got["标题"]["按本题规则的字符数"] == length(title, RULES[q["rule"]]["scheme"]), (name, got["标题"])
        assert not got["禁用词和品牌名（规范化后命中，只量交付本身）"], (name, got)
        assert all(len(p["写出了值的参数"]) == 1 for p in got["卖点段各行"]), (name, got["卖点段各行"])
        bank.append(item)
        label = {"train": "培养", "same": "考试·同规则", "new": "考试·新规则"}[spec[1]]
        r = RULES[q["rule"]]
        scripts.append({"name": name, "title": f"{name} · {label} · {r['company']}{TEMPLATES[q['key']]['category']}",
                        "exam": spec[1] != "train", "steps": [{"text": item["text"], "files": files}]})
    (HERE / "questions.json").write_text(json.dumps(bank, ensure_ascii=False, indent=1) + "\n")
    (HERE / "scripts.json").write_text(json.dumps(scripts, ensure_ascii=False, indent=1) + "\n")
    scenario_package()
    print(f"{len(bank)} questions, {retries} seed retries, scenario at {SCENARIO.name}")


if __name__ == "__main__":
    main()
