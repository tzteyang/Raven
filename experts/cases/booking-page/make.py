"""生成离线团课预约案例：40 道任务、三套工作规则和可复核的交互参考。

只用标准库；在仓库根目录运行 uv run python experts/cases/booking-page/make.py。
测试用课程选择只保存在 reference，员工只拿规则与真实课表。
"""

import datetime as dt
import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENARIO = HERE / "wkr-booking-page"
RULES = {
    "R1": dict(brand="晨跃健身", gap=0, limit=None, prefix="chenyue", types=["瑜伽", "单车", "搏击"],
               book="预约", booked="已预约", full="已满员", success="预约成功", conflict="该时段已有预约", cap=""),
    "R2": dict(brand="岚动训练", gap=15, limit=None, prefix="landong", types=["拉伸", "杠铃", "舞蹈"],
               book="加入课程", booked="已加入", full="名额已满", success="已成功锁定名额", conflict="前后15分钟内已有预约", cap=""),
    "R3": dict(brand="森步运动", gap=10, limit=2, prefix="senbu", types=["普拉提", "核心", "动感单车"],
               book="预订团课", booked="已预订", full="本课已满", success="预约已确认", conflict="课程间隔不足10分钟", cap="当天最多预约2节课"),
}


def rules_text(rule):
    r = RULES[rule]
    interval = ("同一天的两节课，只要时间区间有重叠就冲突；前一节结束时刻等于后一节开始时刻，可以连约。"
                if r["gap"] == 0 else
                f"同一天的两节课，如果时间区间重叠，或者前一节结束到后一节开始不足 {r['gap']} 分钟，就冲突；"
                f"如果间隔正好 {r['gap']} 分钟或更长，就可以连约。")
    cap = (f"同一日期最多预约 {r['limit']} 节不同课程；第三节即使时段不冲突也不能约，提示“{r['cap']}”。不同日期分别计数。"
           if r["limit"] else "每天没有预约节数上限，只按时间冲突和名额限制判断。")
    return f"""# {r['brand']} · 离线团课预约工作规则

给前台平板做本周的单人自助预约页。工作目录的《课表.json》是唯一数据源；本页只管理当前这一位会员的预约，不做登录、会员表单、取消、后端或候补。

1. 交付一份能离线打开的 booking.html，全部 HTML、CSS、JavaScript 和课表内嵌。不用任何框架；不发起网络请求，不引用外部脚本、样式、字体、图片，也不依赖目录里的其他文件。可以在任意普通本地 HTTP 静态服务下使用，断网仍可操作。
2. 初次打开时列出课表里的全部课程，每节恰好一张卡片。卡片显示标题、类型、日期（YYYY-MM-DD）、开始与结束时刻（HH:MM）、教练和剩余名额，文字和数据对应，不能漏课或凭空加课。同名课和不同时期的课以 id 区分。
3. 类型筛选有“全部”和课表里的每个类型，选择某类型时只显示这个类型的课，选“全部”恢复全部。筛选不清除预约，不改变名额。用有可见“课程类型”标签的原生 select，id="type-filter"；“全部”的 value="all"，其余 option 的 value 就是类型原文。
4. 每张卡片设 data-course-id="这节课的id"，卡片里唯一的 [data-remaining] 元素只放当前剩余名额的十进制整数（单位写在元素外）。卡片里唯一的 [data-book] 是此课的预约按钮；可预约时文字“{r['book']}”。这是交接给前台维护时的定位约定，不要把这些属性名显示在页面文案里。
5. 初始剩余名额为 0 的课，按钮为禁用状态（真正不可操作），文字“{r['full']}”，不能扣成负数。名额大于 0 的未约课程，即使与已约课程冲突，也保留可点击按钮，让用户点后看到原因。
6. {interval}日期不同则不冲突，不能只比较开始时刻或忽略日期。冲突时显示“{r['conflict']}”，不新增预约，不改变任一节课的名额。{cap}
7. 预约成功后，这节课的剩余名额立即比课表初始值少 1，按钮文字变成“{r['booked']}”，页面显示“{r['success']}”。已预约按钮可以禁用；如果仍可点击，再点也不重复扣名额、不重复记一次预约，不改变提示。已预约且余量为 0 的课仍显示“{r['booked']}”，不能显示成满员。处理顺序：先识别已经预约的课，再处理满员；未约且有名额时先检查冲突，之后检查每日上限，最后成功。重复点击不是每日上限错误。
8. 提示写进 id="notice" 的可见状态区，设 role="status"、aria-live="polite"；不要用 alert、confirm 或跳转代替。每次失败或成功以本次提示替换上一条，不堆叠。打开或刷新时提示可以为空。
9. 用 localStorage 保存预约，键名严格为“{r['prefix']}-”加课表 week_id；值是课程 id 的 JSON 数组，例如 ["C101","C108"]。刷新后按这个数组恢复本周预约；余量从课表初始值减去本课是否已约（每课至多减 1）计算，不保存不断累减的余量。只使用当前周这个键，别的周的键不影响本页。
10. 如果存储为空、被清空、不是合法 JSON 或解析后不是数组，就按课表初始名额显示、没有已预约课，不报错；如果是数组，就仅保留课表中初始余量大于 0 的合法 id，忽略未知 id、非字符串、满员 id 和重复 id。不会给出合法 id 之间违反时间或每日上限的存储记录。如果浏览器禁止读写 localStorage，就在内存里照常预约、不报错，这种情况下刷新回到初始状态，不要求跨刷新保留。
11. 所有可用的预约按钮和筛选框都能用 Tab 到达，并有可见焦点。焦点在预约按钮时，按回车就完成与点击相同的操作；原本禁用的满员或已约按钮无需 Tab 到达。不得只绑鼠标或靠点击卡片空白处预约。
12. 只交上述一个文件；回复可为空、仅为“booking.html”，或仅给该文件的 Markdown 链接。如果无法交文件，只回复一个标注 html 的完整代码块，内容相当于 booking.html。两种方式二选一，不在前后加解释、步骤、自测说明或其他代码块。前后多出来的文字只在交付格式项算一处，不能拿里面的文字重复判页面内容或行为。
"""


def hhmm(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def make_data(name, segment, rule):
    seed = int(name[1:]) + {"t": 0, "x": 100, "y": 200}[name[0]]
    rng, r = random.Random(92100 + seed), RULES[rule]
    monday = dt.date(2026, 11, 2) + dt.timedelta(weeks=seed)
    day = monday + dt.timedelta(days=rng.randrange(2))
    start = rng.choice([8 * 60 + 30, 9 * 60, 15 * 60, 17 * 60])
    duration = rng.choice([45, 60])
    finish = start + duration
    codes = rng.sample(range(101, 990), 14)
    roles, rows = {}, []
    trainers = rng.sample(["林安", "周宁", "赵晴", "沈禾", "王珂", "李岚", "陈星"], 7)
    def course(role, date, begin, end, kind, remaining, duplicate_title=False):
        cid = f"C{codes[len(rows)]}"
        title = f"{kind}·{rng.choice(['舒展', '力量', '入门', '进阶'])}"
        if duplicate_title:
            title = rows[0]["title"]
        rows.append(dict(id=cid, title=title, type=kind, date=date.isoformat(), start=hhmm(begin), end=hhmm(end),
                         coach=trainers[len(rows) % len(trainers)], remaining=remaining))
        roles[role] = cid
    a_left = 1 if segment == "edge" else rng.randint(2, 8)
    course("first", day, start, finish, r["types"][0], a_left)
    offset = 0 if segment == "common" else rng.choice([15, 30])
    course("overlap", day, start + offset, finish + offset, r["types"][1], rng.randint(2, 6))
    near_start = start if segment == "common" else finish + r["gap"] - 5
    course("near", day, near_start, near_start + 45, r["types"][2], rng.randint(2, 6))
    course("boundary", day, finish + r["gap"], finish + r["gap"] + 45, r["types"][2], rng.randint(2, 6))
    course("next_day", day + dt.timedelta(days=1), start, finish, r["types"][0], rng.randint(2, 6), segment == "edge")
    course("third_today", day, 6 * 60, 6 * 60 + 30, r["types"][1], rng.randint(2, 6))
    for i in range(2):
        course(f"full{i}", monday + dt.timedelta(days=2), 12 * 60 + i * 90, 13 * 60 + i * 90, r["types"][i], 0)
    for i in range(rng.randint(1, 4)):
        course(f"extra{i}", monday + dt.timedelta(days=3), 8 * 60 + i * 90, 9 * 60 + i * 90,
               r["types"][i % 3], rng.randint(1, 8))
    rng.shuffle(rows)
    data = dict(week_id=f"{monday:%Y%m%d}", venue=r["brand"] + rng.choice(["江湾店", "湖畔店", "城西店"]), courses=rows)
    assert len({c["id"] for c in rows}) == len(rows)
    assert all(c["start"] < c["end"] and c["remaining"] >= 0 for c in rows)
    return data, roles


def stamp(c, field):
    return dt.datetime.fromisoformat(c["date"] + "T" + c[field])


def overlap(a, b, gap):
    if a["date"] != b["date"]:
        return False
    buffer = dt.timedelta(minutes=gap)
    return stamp(a, "start") < stamp(b, "end") + buffer and stamp(b, "start") < stamp(a, "end") + buffer


def reference(data, roles, rule):
    r = RULES[rule]
    by_id = {c["id"]: c for c in data["courses"]}
    first = by_id[roles["first"]]
    assert overlap(first, by_id[roles["overlap"]], r["gap"])
    assert overlap(first, by_id[roles["near"]], r["gap"])
    assert not overlap(first, by_id[roles["boundary"]], r["gap"])
    assert not overlap(first, by_id[roles["next_day"]], r["gap"])
    initial = {c["id"]: c["remaining"] for c in data["courses"]}
    booked, notice, steps = [], "", []
    for action in ["first", "repeat", "overlap", "near", "boundary", "next_day", "third_today"]:
        cid = roles["first"] if action == "repeat" else roles[action]
        c = by_id[cid]
        if cid in booked:
            result = "保持，不能重复扣名额"
        elif any(overlap(c, by_id[i], r["gap"]) for i in booked):
            result, notice = "拒绝，时间冲突", r["conflict"]
        elif r["limit"] and sum(by_id[i]["date"] == c["date"] for i in booked) >= r["limit"]:
            result, notice = "拒绝，达到当日上限", r["cap"]
        else:
            booked.append(cid)
            result, notice = "成功", r["success"]
        steps.append(dict(action=action, click=cid, result=result, notice=notice, booked=sorted(booked),
                          remaining={i: n - int(i in booked) for i, n in initial.items()}))
    assert len(booked) == (3 if r["limit"] else 4)
    return {
        "浏览器动作": roles,
        "规则参数": r,
        "当前存储键": r["prefix"] + "-" + data["week_id"],
        "初始名额": initial,
        "筛选后可见id": {t: sorted(c["id"] for c in data["courses"] if c["type"] == t) for t in r["types"]},
        "满员id": sorted(c["id"] for c in data["courses"] if c["remaining"] == 0),
        "顺序操作": steps,
        "刷新后": {"booked": sorted(booked), "remaining": steps[-1]["remaining"]},
        "存储清空、坏JSON、非数组、只有其他周记录": {"booked": [], "remaining": initial},
        "混合存储": {"input": ["UNKNOWN-COURSE", roles["first"], roles["first"], 42, roles["full0"]],
                     "booked": [roles["first"]], "remaining": {i: n - int(i == roles["first"]) for i, n in initial.items()}},
        "禁用存储": "页面无错误，首次仍显示初始课表；内存预约first成功且减1；刷新又回初始值。",
        "键盘": "初始所有有名额课的按钮和筛选均可Tab到达，有可见焦点；Tab到first后回车，结果与首次点击相同。",
        "判定边界": "页内课程和行为只看浏览器观测及HTML。前后说明只记BP-delivery一处。页面定位缺失导致步骤无法测量时，根因只记BP-view；不可把未观测当作多个功能失败。",
    }


CRITERIA = [
    ("BP-view", "standard", "课表显示与筛选：按工作规则2—4、8检查课程信息和DOM定位约定，初始课程id、标题、类型、日期、起止、教练、余量与参考一致；每课的数据错误合记一处。筛选控件有可见标签，选各类型恰好只显对应课程，选全部恢复；每种错误筛选结果记一处。状态区缺失/属性不符记一处。定位元素缺失导致后续步骤无法观测，根因只在本项记，不能据无法测量再判预约/存储/键盘错误。"),
    ("BP-reserve", "red_line", "预约行为：只依据实际浏览器点击观测，对照工作规则5—8与参考顺序操作。满员是否真正禁用；成功是否只扣1且按钮/提示正确；重复预约是否不重复扣且不改变提示；重叠/缓冲不足是否拒绝且不扣；正好达到间隔阈值、不同日期是否可约；R3每日上限及提示是否正确。每种独立行为缺陷记一处，相同根因在连续步骤造成的后果不反复记。每日上限仅R3适用。不能因为源码看起来正确就忽略实际失败，也不能把交付前后说明当页面行为。"),
    ("BP-storage", "standard", "存储行为：按工作规则9—10，实际刷新应恢复已约与名额，存储键和值形状符合规定；清空、坏JSON、非数组恢复初始；混合数组仅保留合法id并去重；其他周不影响本周；禁用存储时不报错且仍能内存预约，刷新回初始。每种独立缺陷记一处。如果预约本来就没成功，不因后续无法恢复它而重复记存储错误。缺少观测不等于通过，结合可用记录说明。"),
    ("BP-keyboard", "standard", "键盘：依据浏览器真实Tab和Enter记录，初始可用预约按钮及筛选能Tab到达且焦点可见，Enter完成与点击相同的预约；每种独立缺陷记一处。满员/禁用按钮不要求能Tab到达。点击也失败且根因相同的错误只归BP-reserve，不能在此重复。不得只从源码存在button就推断键盘可用。"),
    ("BP-delivery", "standard", "交付与离线：按工作规则1、12交一份booking.html或仅一个完整html代码块，无其他文件依赖、框架和外部资源/网络请求。浏览器拦到外部请求就是使用外部资源的证据；同一外部依赖仅记一次。格式有多余说明/其他文件/额外代码块时共记一处，正确交付加前后说明只挂本项一处。前后说明里的词、数字、代码片段不在其他项重复记。若完全没HTML，只在本项记一处，不给其余项重复记页面缺失。"),
]

TASK = ("你是前端开发工程师，为门店制作可直接离线使用的单文件团课预约页。每次任务的工作规则和课表都在工作目录。"
        "按当次规则实现课程展示、筛选、名额与冲突判断、持久化和键盘操作，只交要求的HTML文件或完整代码块。")


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1) + "\n")


def main():
    (HERE / "rules").mkdir(parents=True, exist_ok=True)
    for rule in RULES:
        (HERE / "rules" / f"{rule}.md").write_text(rules_text(rule))
    bank, scripts = [], []
    for prefix, group, number in [("t", "train", 20), ("x", "same", 10), ("y", "new", 10)]:
        for i in range(1, number + 1):
            name = f"{prefix}{i:02d}"
            segment = "common" if i <= number // 2 else "edge"
            rule = "R3" if prefix == "y" else ("R1" if i % 2 else "R2")
            data, roles = make_data(name, segment, rule)
            files = {"工作规则.md": rules_text(rule), "课表.json": json.dumps(data, ensure_ascii=False, indent=2)}
            text = (f"请给{data['venue']}做这周的团课预约页。前台平板断网时也要能约课。"
                    "工作目录有工作规则.md、课表.json。按工作规则实现完整交互并交booking.html；无法交文件时只交一个完整html代码块。")
            q = dict(name=name, group=group, segment=segment, rules=rule, text=text, files=files,
                     reference=reference(data, roles, rule))
            bank.append(q)
            scripts.append(dict(name=name, title=f"{name} · {data['venue']} · 团课预约", exam=group != "train", steps=[dict(text=text, files=files)]))
    assert len(bank) == 40 and len({q["files"]["课表.json"] for q in bank}) == 40
    dump(HERE / "questions.json", bank)
    dump(HERE / "scripts.json", scripts)
    (SCENARIO / "personas").mkdir(parents=True, exist_ok=True)
    (SCENARIO / "profile.md").write_text(TASK + "\n")
    (SCENARIO / "onboarding.md").write_text("以后每次会把本店当期工作规则和课表一起给你。各店规则不同，以当次材料为准；页面供前台平板上的会员直接使用。\n")
    (SCENARIO / "personas" / "manager.md").write_text("店长需要单人自助团课预约页，每道题的课表和工作规则由脚本提供。\n")
    dump(SCENARIO / "scenario.json", {"initial": [], "criteria": [dict(id=i, check=c, severity=s) for i, s, c in CRITERIA]})
    dump(SCENARIO / "contract.json", {"checks": {i: {"visibility": ["counterpart", "analyst", "curator"]} for i, _, _ in CRITERIA}})
    template = json.loads((HERE.parent / "refund-desk" / "live.json").read_text())
    template.update(root="../../../../runs/experts/booking-page", scenario="wkr-booking-page")
    dump(HERE / "live.json", template)
    dump(HERE / "manifest.json", dict(name="预约交互页面", description="为门店制作离线团课预约HTML页，按工作规则处理筛选、名额、时间冲突、存储与键盘交互。",
                                       owns="负责单文件团课预约页面，实现并用浏览器验证交互。"))
    print("40 questions, 3 rule sets; common/edge 20/20; scenario:", SCENARIO.name)


if __name__ == "__main__":
    main()
