"""用户评价周报：三套工作规则、40 道题（20 培养 + 10 道同规则考试 + 10 道换规则考试）、参考答案和 Studio 场景包。

  python3 make.py

依据《专家自进化》11.2 的案例改写成「工作规则随题交给员工」：三家硬件品牌的评价周报口径不同（报前几名、占比的分母和小数、
原话从几星里摘、并列怎么排、一行的写法、字数上限）。培养题和同规则考试题用 R1（声咔，耳机）、R2（律动，手表）交替，换规则
考试题全用员工从没见过的 R3（清籁，音箱）。每道题一周的评价按种子生成：常见题说法都用分类表的关键词、每人一条、名次不并列；
边界题有首评加追评（同一用户要合成一条）、说法只在“典型说法”里、同一条评价把一类问题说两遍、名次并列要按规则排。
参考答案由本脚本按规则算出（每类条数、分母、占比、排序依据、哪些评价能被引用）；生成时校验名次唯一、四舍五入不落在
正中间、照规则写的一份周报不超过字数上限。check.py 只读员工看到的文件另写一遍算法复核。
"""

import json
import random
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENARIO = HERE / "wkr-review-digest"

RULES = {
    "R1": {
        "brand": "声咔", "product": "Air 3 蓝牙耳机", "top": 3, "denominator": "problem", "places": 0, "stars": (1, 2),
        "tie": "low", "quote": "any", "limit": 150,
        "categories": [
            ("连接", ("断连", "配对"), ("听着听着就断了", "连不上手机"), "固件团队"),
            ("续航", ("掉电", "充电"), ("撑不了半天", "电量掉得飞快"), "硬件团队"),
            ("佩戴", ("掉落", "胀耳", "耳朵疼"), ("耳机自己往外滑", "戴着压得慌"), "结构团队"),
            ("音质", ("底噪", "声音小"), ("沙沙的杂音", "音量开满也不响"), "声学团队"),
            ("App", ("闪退", "设置"), ("App 打不开", "找不到降噪开关"), "App 团队"),
            ("物流售后", ("发货", "客服"), ("快递一周才到", "没人回消息"), "电商运营"),
        ],
        "praise": ["音质很好，低音足，值这个价。", "降噪效果惊艳。", "颜值很高，盒子小巧。", "通透模式很自然。", "性价比不错。"],
        "text": """# 声咔 · 评价周报工作规则

1. 按《问题分类表》归类：评价里出现某类的关键词或典型说法，就算提到这一类；一条评价提到几类问题，就各算一次；只夸、不提问题的评价不算。
2. 只报条数前三的类别，从多到少排；占比 = 该类条数 ÷ 提到问题的评价条数，四舍五入取整数百分比。
3. 每类配一句原话：只从这一类的 1 到 2 星评价里，原样照抄一整条评价的内容，带评价编号。
4. 每类写明转给哪个团队，以分类表为准。
5. 全文不超过 150 字（字数按字符算，标点算，空格和换行不算），只报事实，不写原因推测和改进建议。

格式：每类一行，写成“类别 X 条（Y%）：「原话」（#编号）→ 团队”，前面不加标题和开场白，后面不加总结。

补充口径：

- 条数相同的，1 到 2 星评价多的排前面；再相同，按分类表的顺序。
- 同一用户 ID 一周内的几条评价（含追评）合成一条算：类别取并集，星级取最低的那条；分母也按合并后算。
- 一条评价里同一类问题说了几次，只算一次。
- 原话按单条评价挑：那一条评价自己要说到这一类，星级看那一条自己的星级，照抄的是那一条“评价”栏的全部内容。
""",
    },
    "R2": {
        "brand": "律动", "product": "Fit 2 智能手表", "top": 2, "denominator": "all", "places": 1, "stars": (1, 2, 3),
        "tie": "low3", "quote": "any", "limit": 120,
        "categories": [
            ("屏幕", ("花屏", "黑屏"), ("屏幕一闪一闪", "看不清字"), "显示团队"),
            ("续航", ("掉电", "充不进"), ("一天一充", "电量蹭蹭往下掉"), "电源团队"),
            ("表带", ("断裂", "过敏"), ("扣子松了", "手腕起红疹"), "结构团队"),
            ("心率", ("不准", "跳变"), ("心率乱跳", "测出来两百多"), "算法团队"),
            ("App", ("闪退", "同步"), ("数据传不上去", "App 打不开"), "App 团队"),
            ("物流售后", ("发货", "客服"), ("快递一周才到", "没人回消息"), "电商运营"),
        ],
        "praise": ["表盘好看，戴着很轻。", "睡眠监测挺准的。", "运动模式很全。", "做工精致。", "性价比高。"],
        "text": """# 律动 · 评价周报工作规则

1. 按《问题分类表》归类：评价里出现某类的关键词或典型说法，就算提到这一类；一条评价提到几类问题，就各算一次；只夸、不提问题的评价不算进类别。
2. 只报条数前两名的类别，从多到少排；占比 = 该类条数 ÷ 全部评价条数（含只夸的），四舍五入保留一位小数。
3. 每类配一句原话：从这一类的 1 到 3 星评价里，原样照抄一整条评价的内容，带评价编号。
4. 每类写明转给哪个团队，以分类表为准。
5. 全文不超过 120 字（字数按字符算，标点算，空格和换行不算），只报事实，不写原因推测和改进建议。

格式：每类一行，写成“第 N 名 类别：X 条，占 Y%，转团队；原话“原话”〔#编号〕”，前面不加标题和开场白，后面不加总结。

补充口径：

- 条数相同的，1 到 3 星评价多的排前面；再相同，按分类表的顺序。
- 同一用户 ID 一周内的几条评价（含追评）合成一条算：类别取并集，星级取最低的那条；全部评价条数也按合并后算。
- 一条评价里同一类问题说了几次，只算一次。
- 原话按单条评价挑：那一条评价自己要说到这一类，星级看那一条自己的星级，照抄的是那一条“评价”栏的全部内容。
""",
    },
    "R3": {
        "brand": "清籁", "product": "Echo Mini 智能音箱", "top": 3, "denominator": "problem", "places": 0, "stars": (1, 2),
        "tie": "one", "quote": "latest_one", "limit": 170,
        "categories": [
            ("连接", ("断连", "配网"), ("连不上 Wi-Fi", "蓝牙老是掉"), "固件团队"),
            ("唤醒", ("唤不醒", "误唤醒"), ("喊半天没反应", "自己突然说话"), "语音团队"),
            ("音质", ("破音", "底噪"), ("声音发闷", "大音量就炸"), "声学团队"),
            ("App", ("闪退", "绑定"), ("App 打不开", "设备列表找不到"), "App 团队"),
            ("外观", ("划痕", "掉漆"), ("外壳有印子", "颜色和图片不一样"), "结构团队"),
            ("物流售后", ("发货", "客服"), ("快递一周才到", "没人回消息"), "电商运营"),
        ],
        "praise": ["音质超出预期。", "外观很好看，放客厅合适。", "反应很快。", "儿童模式很实用。", "性价比不错。"],
        "text": """# 清籁 · 评价周报工作规则

1. 按《问题分类表》归类：评价里出现某类的关键词或典型说法，就算提到这一类；一条评价提到几类问题，就各算一次；只夸、不提问题的评价不算。
2. 只报条数前三的类别，从多到少排；占比 = 该类条数 ÷ 提到问题的评价条数，四舍五入取整数百分比。
3. 每类配一句原话：从这一类的 1 星评价里照抄（这一类没有 1 星评价的，从 2 星里照抄），选日期最新的那一条（日期相同选编号小的），原样照抄一整条评价的内容，带评价编号。
4. 每类写明转给哪个团队，以分类表为准。
5. 全文不超过 170 字（字数按字符算，标点算，空格和换行不算），只报事实，不写原因推测和改进建议。

格式：每类一行，写成“类别 X 条（Y%）：「原话」（#编号）→ 团队”，前面不加标题和开场白，后面不加总结。

补充口径：

- 条数相同的，1 星评价多的排前面；再相同，按分类表的顺序。
- 同一用户 ID 一周内的几条评价（含追评）合成一条算：类别取并集，星级取最低的那条；分母也按合并后算。
- 一条评价里同一类问题说了几次，只算一次。
- 原话按单条评价挑：那一条评价自己要说到这一类，星级、日期看那一条自己的，照抄的是那一条“评价”栏的全部内容。
""",
    },
}

SENTENCES = {'R1': {'连接': ['右耳隔几分钟就断连一次', '重新配对也没用', '左右耳经常断连', '每次开盒都要重新配对'], '续航': ['掉电太快', '充电盒充一晚上还是红灯', '听一小时就掉电一半', '充电要三个多小时'], '佩戴': ['跑步时容易掉落', '戴久了耳朵疼', '耳塞有点胀耳', '已经掉落过一只'], '音质': ['有明显底噪', '开到最大声音小', '安静的时候底噪很重', '通话时对方说我声音小'], 'App': ['App 一打开就闪退', '设置里的降噪选项没反应', '改个设置就闪退', 'App 里设置项太乱'], '物流售后': ['发货拖了五天', '客服电话打不通', '下单三天才发货', '问客服一直转人工']}, 'R2': {'屏幕': ['抬腕经常黑屏', '屏幕偶尔花屏', '运动时黑屏', '开机就花屏'], '续航': ['一天就掉电到两成', '充电器经常充不进', '开着心率一晚上掉电一半', '插上也充不进'], '表带': ['表带用了一周就断裂', '表带材质让我过敏', '表带扣断裂了', '戴久了皮肤过敏'], '心率': ['心率测得不准', '心率数据跳变', '静坐心率也不准', '跑步时心率跳变'], 'App': ['App 同步要好几分钟', 'App 一打开就闪退', '同步一次失败三次', '看数据时闪退'], '物流售后': ['发货慢了三天', '客服一直不回', '下单四天才发货', '找客服要排队']}, 'R3': {'连接': ['经常断连', '配网失败好几次', '播着歌突然断连', '换了路由器要重新配网'], '唤醒': ['叫了好几声唤不醒', '半夜误唤醒', '离两米就唤不醒', '看电视时总误唤醒'], '音质': ['大声放歌会破音', '安静时有底噪', '低音一重就破音', '关着音乐也有底噪'], 'App': ['App 闪退', '绑定设备总失败', '改设置时闪退', '换手机后绑定不上'], '外观': ['到手就有划痕', '边角掉漆', '顶盖有划痕', '用了一周就掉漆'], '物流售后': ['发货太慢', '客服不理人', '下单三天才发货', '客服回复很慢']}}
TAILS = ["", "，有点失望", "，退了算了", "，希望改进", ""]
SPECS = []
for i in range(1, 21):
    SPECS.append((f"t{i:02d}", "train", "edge" if i > 10 else "common", "R1" if i % 2 else "R2"))
for i in range(1, 11):
    SPECS.append((f"x{i:02d}", "same", "edge" if i > 5 else "common", "R1" if i % 2 else "R2"))
for i in range(1, 11):
    SPECS.append((f"y{i:02d}", "new", "edge" if i > 5 else "common", "R3"))
WEEK = ["2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24", "2026-09-25", "2026-09-26", "2026-09-27"]

TASK = (
    "你是硬件品牌的产品市场助理，每周一给上市群发一份用户评价周报。工作目录里有这次适用的评价周报工作规则、这一周的用户"
    "评价和问题分类表。按这次给的工作规则写出周报，直接发到群里。只输出周报本身。"
)
ONBOARDING = "以后每周的评价周报，我都会把这次适用的工作规则、本周评价和问题分类表一起发给你。不同品牌的口径不一样，以当次给的为准。"
CRITERIA = [
    ("R-rank", "red_line",
     "类别、条数和占比：按这次工作规则报的类别个数、顺序（含并列时的排法）、每类条数和占比，与参考答案一致（占比按规则的分母和"
     "小数位）。报错类别、顺序不对、条数或占比不对、多报少报，每处记一处。"),
    ("R-quote", "standard",
     "原话：每类引的原话必须原样出自那条评价（一整条内容，标点也一样），编号对得上，星级和选法符合规则（测量值核对了每句引文在"
     "评价里能不能找到、那条是几星）；原话不在规则允许的那几条里、改了字、编号错，每处记一处。"),
    ("R-team", "standard",
     "团队：每类转给的团队与分类表一致；写错或漏写，每处记一处。"),
    ("R-form", "standard",
     "格式和事实：按规则的一行写法输出，不加标题、开场白和总结；全文不超过字数上限（以测量值为准）；不写原因推测和改进建议。"
     "每处不符记一处。"),
]


def matches(rule: str, text: str) -> set[str]:
    found = set()
    for name, keys, phrases, team in RULES[rule]["categories"]:
        if any(word in text for word in keys + phrases):
            found.add(name)
    return found


def build(spec, rng):
    name, group, segment, rule = spec
    r = RULES[rule]
    edge = segment == "edge"
    cats = [c[0] for c in r["categories"]]
    words = {c[0]: (c[1], c[2]) for c in r["categories"]}
    n_users = rng.randint(34, 52)
    weights = sorted(rng.sample(range(2, 14), len(cats)), reverse=True)
    rng.shuffle(cats)
    weight = dict(zip(cats, weights))
    users = []
    for number in rng.sample(range(10000, 100000), n_users):
        uid = f"U{number}"
        if rng.random() < 0.2:
            users.append({"uid": uid, "cats": [], "stars": rng.choice([4, 5, 5])})
            continue
        k = 1 if rng.random() < 0.65 else 2
        chosen = []
        while len(chosen) < k:
            pick = rng.choices(cats, [weight[c] for c in cats])[0]
            if pick not in chosen:
                chosen.append(pick)
        stars = rng.choices([1, 2, 3, 4], [0.4, 0.3, 0.2, 0.1])[0]
        users.append({"uid": uid, "cats": chosen, "stars": stars})
    reviews, serial = [], 0

    def say(cat, typical):
        keys, phrases = words[cat]
        return rng.choice(phrases) if typical else rng.choice(SENTENCES[rule][cat])

    def sentence(cat_list, typical, double=False):
        parts = [say(c, typical and rng.random() < 0.6) for c in cat_list]
        if double and cat_list:
            first = cat_list[0]
            parts.append(next(x for x in rng.sample(SENTENCES[rule][first] + list(words[first][1]), 6) if x not in parts))
        return "，".join(parts) + rng.choice(TAILS) + "。"

    for user in users:
        if not user["cats"]:
            serial += 1
            reviews.append({"id": f"#{serial}", "uid": user["uid"], "stars": user["stars"], "date": rng.choice(WEEK),
                            "text": rng.choice(r["praise"])})
            continue
        follow = edge and len(user["cats"]) == 2 and rng.random() < 0.5
        double = edge and rng.random() < 0.15
        if follow:
            first, second = user["cats"][0], user["cats"][1]
            day = rng.randint(0, 4)
            serial += 1
            reviews.append({"id": f"#{serial}", "uid": user["uid"], "stars": min(4, user["stars"] + rng.choice([0, 1])),
                            "date": WEEK[day], "text": sentence([first], edge)})
            serial += 1
            reviews.append({"id": f"#{serial}", "uid": user["uid"], "stars": user["stars"], "date": WEEK[day + rng.randint(1, 2)],
                            "kind": "追评", "text": sentence([second, first] if rng.random() < 0.5 else [second], edge)})
        else:
            serial += 1
            reviews.append({"id": f"#{serial}", "uid": user["uid"], "stars": user["stars"], "date": rng.choice(WEEK),
                            "text": sentence(user["cats"], edge, double)})
    designed = {user["uid"]: set(user["cats"]) for user in users}
    seen = {}
    for review in reviews:
        seen.setdefault(review["uid"], set()).update(matches(rule, review["text"]))
    assert all(seen[uid] == cats for uid, cats in designed.items()), [(uid, cats, seen[uid]) for uid, cats in designed.items() if seen[uid] != cats][:3]
    order = list(range(len(reviews)))
    rng.shuffle(order)
    shuffled = [reviews[i] for i in order]
    for index, review in enumerate(shuffled, 1):
        review["id"] = f"#{index}"
    return shuffled


def units(rule, reviews):
    """Reviews merged by user: categories united, stars the lowest."""
    merged = {}
    for review in reviews:
        unit = merged.setdefault(review["uid"], {"cats": set(), "stars": 5, "reviews": []})
        unit["cats"] |= matches(rule, review["text"])
        unit["stars"] = min(unit["stars"], review["stars"])
        unit["reviews"].append(review)
    return merged


def rank(rule, reviews, *, merge=True, typical=True):
    r = RULES[rule]
    table = [c[0] for c in r["categories"]]
    if merge:
        groups = list(units(rule, reviews).values())
    else:
        groups = [{"cats": matches(rule, rv["text"]), "stars": rv["stars"], "reviews": [rv]} for rv in reviews]
    if not typical:
        for g in groups:
            g["cats"] = {c[0] for c in r["categories"] if any(any(k in rv["text"] for k in c[1]) for rv in g["reviews"])}
    counts = {c: sum(c in g["cats"] for g in groups) for c in table}
    low = {"low": (1, 2), "low3": (1, 2, 3), "one": (1,)}[r["tie"]]
    lows = {c: sum(c in g["cats"] and g["stars"] in low for g in groups) for c in table}
    denominator = sum(1 for g in groups if g["cats"]) if r["denominator"] == "problem" else len(groups)
    ordered = sorted(table, key=lambda c: (-counts[c], -lows[c], table.index(c)))
    return ordered, counts, lows, denominator


def quotes(rule, reviews, category):
    r = RULES[rule]
    candidates = [rv for rv in reviews if category in matches(rule, rv["text"])]
    if r["quote"] == "latest_one":
        ones = [rv for rv in candidates if rv["stars"] == 1] or [rv for rv in candidates if rv["stars"] == 2]
        if not ones:
            return []
        best = max(ones, key=lambda rv: (rv["date"], -int(rv["id"][1:])))
        return [best]
    return [rv for rv in candidates if rv["stars"] in r["stars"]]


def pct(value: Decimal, places: int) -> str:
    return f"{value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)}%"


def compute(spec, reviews):
    name, group, segment, rule = spec
    r = RULES[rule]
    ordered, counts, lows, denominator = rank(rule, reviews)
    top = ordered[:r["top"]]
    assert counts[top[-1]] > counts[ordered[r["top"]]] or lows[top[-1]] > lows[ordered[r["top"]]] or \
        [c[0] for c in r["categories"]].index(top[-1]) < [c[0] for c in r["categories"]].index(ordered[r["top"]]), name
    if segment == "common":
        assert all(counts[ordered[i]] > counts[ordered[i + 1]] for i in range(r["top"])), (name, [counts[c] for c in ordered])
        assert len({rv["uid"] for rv in reviews}) == len(reviews), name
    else:
        assert len({rv["uid"] for rv in reviews}) < len(reviews), name
        assert any(counts[ordered[i]] == counts[ordered[i + 1]] for i in range(r["top"])), (name, [counts[c] for c in ordered])
        assert rank(rule, reviews, merge=False)[0][:r["top"]] != top or rank(rule, reviews, merge=False)[1] != counts, name
        assert rank(rule, reviews, typical=False)[1] != counts, name
    teams = {c[0]: c[3] for c in r["categories"]}
    entries, lines = [], []
    for position, category in enumerate(top, 1):
        share = Decimal(counts[category]) * 100 / denominator
        scaled = share * Decimal(10) ** r["places"]
        assert abs(scaled - scaled.to_integral_value(rounding="ROUND_FLOOR") - Decimal("0.5")) > Decimal("0.01"), (name, share)
        allowed = quotes(rule, reviews, category)
        assert allowed, (name, category)
        pick = min(allowed, key=lambda rv: len(rv["text"]))
        if rule == "R2":
            line = f"第 {position} 名 {category}：{counts[category]} 条，占 {pct(share, 1)}，转{teams[category]}；原话“{pick['text']}”〔{pick['id']}〕"
        else:
            line = f"{category} {counts[category]} 条（{pct(share, 0)}）：「{pick['text']}」（{pick['id']}）→ {teams[category]}"
        lines.append(line)
        entries.append({
            "名次": position, "类别": category, "条数": counts[category], "低星评价数（并列时用）": lows[category],
            "占比（未取舍）": f"{share.quantize(Decimal('0.0001'))}%", "占比（按规则取舍）": pct(share, r["places"]),
            "转给": teams[category],
            "可以引用的评价（编号：星级）": [f"{rv['id']}：{rv['stars']} 星" for rv in allowed],
        })
    text = "\n".join(lines)
    size = len("".join(text.split()))
    assert size <= r["limit"] - 10, (name, size)
    merged = units(rule, reviews)
    return {
        "规则集": f"{rule}（{r['brand']}）",
        "报的类别（按顺序）": entries,
        "各类条数（全部类别）": counts,
        "占比分母": f"{denominator}（{'提到问题的评价条数' if r['denominator'] == 'problem' else '全部评价条数'}，同一用户已合并）",
        "同一用户合并的评价": [" + ".join(rv["id"] for rv in u["reviews"]) for u in merged.values() if len(u["reviews"]) > 1] or "无",
        "排序说明": "；".join(f"{c} {counts[c]} 条（低星 {lows[c]}）" for c in ordered),
        "字数上限": r["limit"],
        "一份照规则写的示例（原话可以换成别的允许的评价）": text,
    }


def reviews_text(reviews) -> str:
    lines = ["# 本周用户评价", "", "| 编号 | 用户 ID | 类型 | 星级 | 日期 | 评价 |", "|---|---|---|---|---|---|"]
    lines += [f"| {rv['id']} | {rv['uid']} | {rv.get('kind', '首评')} | {rv['stars']} | {rv['date']} | {rv['text']} |"
              for rv in reviews]
    return "\n".join(lines) + "\n"


def table_text(rule) -> str:
    lines = ["# 问题分类表", "", "| 类别 | 关键词 | 典型说法 | 转给 |", "|---|---|---|---|"]
    for name, keys, phrases, team in RULES[rule]["categories"]:
        lines.append(f"| {name} | {'、'.join(keys)} | {'、'.join(phrases)} | {team} |")
    return "\n".join(lines) + "\n"


def scenario_package():
    (SCENARIO / "personas").mkdir(parents=True, exist_ok=True)
    (SCENARIO / "profile.md").write_text(TASK + "\n")
    (SCENARIO / "onboarding.md").write_text(ONBOARDING + "\n")
    (SCENARIO / "personas" / "pmm.md").write_text("产品市场经理每周要一份评价周报；每道题的评价、分类表和规则由脚本给出。\n")
    (SCENARIO / "scenario.json").write_text(json.dumps({
        "initial": [],
        "criteria": [{"id": i, "check": text, "severity": severity} for i, severity, text in CRITERIA],
    }, ensure_ascii=False, indent=1) + "\n")
    visible = ["counterpart", "analyst", "curator"]
    (SCENARIO / "contract.json").write_text(json.dumps(
        {"checks": {i: {"visibility": visible} for i, _, _ in CRITERIA}}, ensure_ascii=False, indent=1) + "\n")


def main():
    assert len({s[0] for s in SPECS}) == 40
    (HERE / "rules").mkdir(exist_ok=True)
    for rule, r in RULES.items():
        (HERE / "rules" / f"{rule}.md").write_text(r["text"])
        for name, keys, phrases, team in r["categories"]:
            for text in r["praise"]:
                assert not matches(rule, text), (rule, text)
    bank, scripts, retries = [], [], 0
    for spec in SPECS:
        name, group, segment, rule = spec
        for salt in range(400):
            reviews = build(spec, random.Random(f"{name}:{salt}"))
            try:
                reference = compute(spec, reviews)
                break
            except AssertionError:
                retries += 1
        else:
            raise RuntimeError(f"{name}: no seed passes the checks")
        files = {"工作规则.md": RULES[rule]["text"], "本周评价.md": reviews_text(reviews), "问题分类表.md": table_text(rule)}
        text = (f"{RULES[rule]['brand']} {RULES[rule]['product']}这周的评价出来了，帮我出本周评价周报。\n\n"
                "这次适用的评价周报工作规则、本周评价和问题分类表在工作目录：工作规则.md、本周评价.md、问题分类表.md。")
        bank.append({"name": name, "group": group, "segment": segment, "rules": rule, "text": text, "files": files,
                     "reference": reference})
        label = {"train": "培养", "same": "考试·同规则", "new": "考试·新规则"}[group]
        scripts.append({"name": name, "title": f"{name} · {label} · {RULES[rule]['brand']}", "exam": group != "train",
                        "steps": [{"text": text, "files": files}]})
    (HERE / "questions.json").write_text(json.dumps(bank, ensure_ascii=False, indent=1) + "\n")
    (HERE / "scripts.json").write_text(json.dumps(scripts, ensure_ascii=False, indent=1) + "\n")
    scenario_package()
    print(f"{len(bank)} questions, {retries} seed retries, scenario at {SCENARIO.name}")


if __name__ == "__main__":
    main()
