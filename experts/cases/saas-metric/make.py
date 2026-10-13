"""SaaS 指标取数：三套工作规则、40 道题（20 培养 + 10 道同规则考试 + 10 道换规则考试）、参考答案和 Studio 场景包。

  python3 make.py

依据《专家自进化》3.2 的案例改写成「工作规则随题交给员工」：三家 SaaS 公司对「月活跃付费企业」的口径不同（活跃按不同
自然日、按登录次数还是按不同工作日；付费看月末那天、当月任意一天，还是排除某个套餐；交付的段名不同）。员工交一段
SQLite 能直接跑的 SQL（原案例是 DuckDB，这台机器上没有 DuckDB，SQLite 是 Python 自带的）、结果数字、口径说明和数据
问题。培养题和同规则考试题用 R1（简账云）、R2（云签宝）交替，换规则考试题全用员工从没见过的 R3（慧算账）。每道题一份按种子
生成的库（users、subscriptions、merges 三张 CSV 和建表语句），按规则埋试用企业、多账号企业、差一天不够活跃的企业；边界题再埋
UTC 登录时间、试用月中转正、企业合并、订阅重叠、结束日早于开始日的订阅。生成时校验：每个陷阱忽略掉都会算出别的数。
check.py 用另一套写法的 SQL 在 SQLite 里重算每道题。
"""

import calendar
import csv
import io
import json
import random
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENARIO = HERE / "wkr-saas-metric"
PLANS = ("基础版", "专业版", "旗舰版")
SCHEMA = """CREATE TABLE users (company_id TEXT, account_id TEXT, login_at TEXT);
CREATE TABLE subscriptions (company_id TEXT, plan TEXT, start_date TEXT, end_date TEXT, is_trial INTEGER);
CREATE TABLE merges (old_company_id TEXT, new_company_id TEXT, merged_on TEXT);
"""

RULES = {
    "R1": {
        "brand": "简账云", "active": "days", "need": 3, "paid": "month_end", "excluded_plan": None,
        "sections": ("SQL", "结果", "口径说明", "数据问题"),
        "text": """# 简账云 · 指标口径工作规则

1. “活跃”：当月至少 3 个不同自然日有登录。一家企业任何一个账号的登录都算这家企业的登录。
2. “付费”：当月最后一天有生效中的正式订阅：start_date ≤ 当月最后一天 ≤ end_date，并且 is_trial = 0。试用不算。
3. 按企业去重：一家企业多个账号、多条订阅，都只算一家。
4. 交付四段，段名照写：“## SQL”（一个 ```sql 代码块，SQLite 能直接跑，表和字段按 schema.sql）、“## 结果”（只写一个数字）、
   “## 口径说明”（一句话）、“## 数据问题”（列出发现的问题；没有就写“无”）。只交这四段，四段前后不加别的文字。
5. 发现数据问题（例如订阅结束日早于开始日）在“## 数据问题”里报告，不静默丢弃。数据问题只指数据本身有错；规则里已经交代怎么算的情况（试用、转正、合并、套餐限定、没有合并记录等）照规则处理，不算数据问题。

补充口径：

- 登录时间按北京时间算自然日。先看数据说明里 login_at 的时区：写的是 UTC，就先加 8 小时再算日期；写的是北京时间，直接算，不加。
- 企业合并后按合并记录归到新 ID：旧 ID 的登录和订阅都算到新 ID 上（不管发生在合并前还是合并后）。
- 试用转正的企业从转正日起算付费：转正后是一条 is_trial = 0 的新订阅。
- 结束日早于开始日的订阅不算，在“## 数据问题”里报告（写出企业 ID 和起止日）。
- 问题里限定了套餐的（例如“只算专业版”），付费只看那个套餐的订阅。
""",
    },
    "R2": {
        "brand": "云签宝", "active": "logins", "need": 5, "paid": "any_day", "excluded_plan": None,
        "sections": ("查询", "答案", "说明", "异常数据"),
        "text": """# 云签宝 · 指标口径工作规则

1. “活跃”：当月登录记录至少 5 条（一条 users 记录算一次登录；一家企业各个账号的登录合起来数）。
2. “付费”：当月任意一天有生效中的正式订阅：start_date ≤ 当月最后一天，并且 end_date ≥ 当月第一天，并且 is_trial = 0。试用不算。
3. 按企业去重：一家企业多个账号、多条订阅（包括时间重叠的订阅），都只算一家。
4. 交付四段，段名照写：“## 查询”（一个 ```sql 代码块，SQLite 能直接跑，表和字段按 schema.sql）、“## 答案”（只写一个数字）、
   “## 说明”（不超过两句）、“## 异常数据”（列出发现的问题；没有就写“无”）。只交这四段，四段前后不加别的文字。
5. 发现数据问题（例如订阅结束日早于开始日）在“## 异常数据”里报告，不静默丢弃。数据问题只指数据本身有错；规则里已经交代怎么算的情况（试用、转正、合并、套餐限定、没有合并记录等）照规则处理，不算数据问题。

补充口径：

- 登录时间按北京时间算属于哪个月。先看数据说明里 login_at 的时区：写的是 UTC，就先加 8 小时再算；写的是北京时间，直接算，不加。
- 企业合并后按合并记录归到新 ID：旧 ID 的登录和订阅都算到新 ID 上（不管发生在合并前还是合并后）。
- 结束日早于开始日的订阅不算，在“## 异常数据”里报告（写出企业 ID 和起止日）。
- 问题里限定了套餐的（例如“只算专业版”），付费只看那个套餐的订阅。
""",
    },
    "R3": {
        "brand": "慧算账", "active": "workdays", "need": 3, "paid": "month_end", "excluded_plan": "基础版",
        "sections": ("SQL", "结果", "口径说明", "数据问题"),
        "text": """# 慧算账 · 指标口径工作规则

1. “活跃”：当月至少 3 个不同的工作日有登录。工作日指周一到周五（不看法定节假日和调休）；周六、周日的登录不算。一家企业任何一个账号的登录都算这家企业的登录。
2. “付费”：当月最后一天有生效中的正式订阅，并且套餐不是“基础版”：start_date ≤ 当月最后一天 ≤ end_date，is_trial = 0，plan ≠ '基础版'。试用不算。
3. 按企业去重：一家企业多个账号、多条订阅，都只算一家。
4. 交付四段，段名照写：“## SQL”（一个 ```sql 代码块，SQLite 能直接跑，表和字段按 schema.sql）、“## 结果”（只写一个数字）、
   “## 口径说明”（一句话）、“## 数据问题”（列出发现的问题；没有就写“无”）。只交这四段，四段前后不加别的文字。
5. 发现数据问题（例如订阅结束日早于开始日）在“## 数据问题”里报告，不静默丢弃。数据问题只指数据本身有错；规则里已经交代怎么算的情况（试用、转正、合并、套餐限定、没有合并记录等）照规则处理，不算数据问题。

补充口径：

- 登录时间按北京时间算自然日、算星期几。先看数据说明里 login_at 的时区：写的是 UTC，就先加 8 小时再算；写的是北京时间，直接算，不加。
- 企业合并后按合并记录归到新 ID：旧 ID 的登录和订阅都算到新 ID 上（不管发生在合并前还是合并后）。
- 试用转正的企业从转正日起算付费：转正后是一条 is_trial = 0 的新订阅。
- 结束日早于开始日的订阅不算，在“## 数据问题”里报告（写出企业 ID 和起止日）。
- 问题里限定了套餐的，付费只看那个套餐的订阅（限定的套餐是“基础版”时，以规则第 2 条为准，结果为 0）。
""",
    },
}

# name, group, segment, rules, month, plan filter, edge features
SPECS = [
    ("t01", "train", "common", "R1", "2026-09", None, ()),
    ("t02", "train", "common", "R2", "2026-08", None, ()),
    ("t03", "train", "common", "R1", "2026-07", "专业版", ()),
    ("t04", "train", "common", "R2", "2026-06", "专业版", ()),
    ("t05", "train", "common", "R1", "2026-05", None, ()),
    ("t06", "train", "common", "R2", "2026-04", "旗舰版", ()),
    ("t07", "train", "common", "R1", "2026-03", "旗舰版", ()),
    ("t08", "train", "common", "R2", "2026-09", None, ()),
    ("t09", "train", "common", "R1", "2026-10", None, ()),
    ("t10", "train", "common", "R2", "2026-07", None, ()),
    ("t11", "train", "edge", "R1", "2026-09", None, ("bad", "utc")),
    ("t12", "train", "edge", "R2", "2026-08", None, ("bad", "overlap")),
    ("t13", "train", "edge", "R1", "2026-07", None, ("convert", "merge")),
    ("t14", "train", "edge", "R2", "2026-06", None, ("utc", "merge")),
    ("t15", "train", "edge", "R1", "2026-05", "专业版", ("overlap", "utc")),
    ("t16", "train", "edge", "R2", "2026-04", "专业版", ("bad", "utc", "merge")),
    ("t17", "train", "edge", "R1", "2026-03", None, ("bad", "convert", "merge")),
    ("t18", "train", "edge", "R2", "2026-09", None, ("overlap", "utc", "bad")),
    ("t19", "train", "edge", "R1", "2026-10", None, ("utc", "convert", "overlap", "bad")),
    ("t20", "train", "edge", "R2", "2026-05", None, ("merge", "bad", "overlap")),
    ("x01", "same", "common", "R1", "2026-08", None, ()),
    ("x02", "same", "common", "R2", "2026-10", None, ()),
    ("x03", "same", "common", "R1", "2026-06", "专业版", ()),
    ("x04", "same", "common", "R2", "2026-03", "专业版", ()),
    ("x05", "same", "common", "R1", "2026-04", None, ()),
    ("x06", "same", "edge", "R2", "2026-07", None, ("bad", "utc", "merge")),
    ("x07", "same", "edge", "R1", "2026-08", None, ("utc", "convert", "bad")),
    ("x08", "same", "edge", "R2", "2026-10", "专业版", ("overlap", "merge")),
    ("x09", "same", "edge", "R1", "2026-06", None, ("merge", "overlap", "bad")),
    ("x10", "same", "edge", "R2", "2026-03", None, ("utc", "bad", "overlap")),
    ("y01", "new", "common", "R3", "2026-09", None, ()),
    ("y02", "new", "common", "R3", "2026-07", "专业版", ()),
    ("y03", "new", "common", "R3", "2026-05", None, ()),
    ("y04", "new", "common", "R3", "2026-08", "旗舰版", ()),
    ("y05", "new", "common", "R3", "2026-04", None, ()),
    ("y06", "new", "edge", "R3", "2026-09", None, ("bad", "utc", "convert")),
    ("y07", "new", "edge", "R3", "2026-06", None, ("merge", "overlap", "utc")),
    ("y08", "new", "edge", "R3", "2026-10", "专业版", ("bad", "merge")),
    ("y09", "new", "edge", "R3", "2026-03", None, ("convert", "utc", "bad")),
    ("y10", "new", "edge", "R3", "2026-08", None, ("overlap", "merge", "bad")),
]

OPENINGS = ["CFO 问：", "财务月报要用：", "董事会材料要一个数：", "运营周会问：", "投资人问："]
TASK = (
    "你是 SaaS 公司的数据分析师。同事会问一个业务指标的数，工作目录里有这次适用的指标口径工作规则、数据库的建表语句、"
    "数据说明和几张表的 CSV。按这次给的工作规则写 SQL、算出结果、说明口径、报告数据问题。"
)
ONBOARDING = "以后每次取数，我都会把这次适用的指标口径工作规则、建表语句、数据说明和数据一起发给你。不同公司的口径不一样，以当次给的为准。"
CRITERIA = [
    ("Q-number", "red_line",
     "结果数字：按这次工作规则算出的企业数和参考答案一致（写了别的数、没写数、写了多个互相矛盾的数，记一处）。"),
    ("Q-sql", "standard",
     "SQL：交付的 SQL 在按 schema.sql 建好并导入 CSV 的 SQLite 库上能跑通，跑出的数和参考答案一致（测量值给出了实际运行结果）；"
     "SQL 要真的按规则从表里算，不能把结果写死。跑不通、跑出的数不对、或写死结果，每处记一处。"),
    ("Q-issues", "standard",
     "数据问题：参考答案列出的数据问题（结束日早于开始日的订阅）都要在规则要求的那一段报告出来（写出企业 ID）；漏报一条记一处，"
     "把正常数据说成有问题也记一处。题里没有这类问题时，只要那一段写“无”或没有错报就算对。"),
    ("Q-format", "standard",
     "口径说明和格式：按这次工作规则的段数、段名（每段以“## 段名”开头）和长度要求交付；口径说明里写的活跃、付费、去重口径要和这次"
     "规则一致。段名或段数不对、口径说明写错或超长，每处记一处。"),
]


def last_day(month: str) -> date:
    y, m = map(int, month.split("-"))
    return date(y, m, calendar.monthrange(y, m)[1])


def first_day(month: str) -> date:
    y, m = map(int, month.split("-"))
    return date(y, m, 1)


def build(spec, rng):
    """(users, subscriptions, merges, utc, plan_of_interest): one question's tables, before any rule is applied."""
    name, group, segment, rule, month, plan, features = spec
    r = RULES[rule]
    start, end = first_day(month), last_day(month)
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    weekdays = [d for d in days if d.weekday() < 5]
    weekend = [d for d in days if d.weekday() >= 5]
    utc = "utc" in features
    users, subs, merges = [], [], []
    sizes = {"good": rng.randint(9, 19), "good_multi": rng.randint(1, 4), "trial_only": rng.randint(2, 5),
             "ended_mid": rng.randint(2, 5), "two_days": rng.randint(2, 5), "paid_idle": rng.randint(2, 6),
             "other_plan": rng.randint(2, 5) if plan else 0, "weekend_heavy": rng.randint(2, 5), "few_logins": rng.randint(2, 5)}
    count = sum(sizes.values()) + rng.randint(4, 10)
    companies = [f"C{rng.randint(100, 999)}{i:02d}" for i in range(count)]
    focus = plan or "专业版"

    def stamp(day, hour=None, minute=None):
        """A login on this Beijing day, written in the timezone the data uses."""
        moment = datetime(day.year, day.month, day.day, hour if hour is not None else rng.randint(8, 21),
                          minute if minute is not None else rng.randint(0, 59), rng.randint(0, 59))
        if utc:
            moment -= timedelta(hours=8)
        return moment.strftime("%Y-%m-%d %H:%M:%S")

    def logins(company, n_days, per_day=(1, 2), accounts=1, pool=None):
        pool = pool or days
        picked = rng.sample(pool, n_days)
        for k, day in enumerate(picked):
            for _ in range(rng.randint(*per_day)):
                users.append({"company_id": company, "account_id": f"{company}-A{(k % accounts) + 1}", "login_at": stamp(day)})
        return picked

    def subscribe(company, plan_name, s, e, trial=0):
        subs.append({"company_id": company, "plan": plan_name, "start_date": s.isoformat(), "end_date": e.isoformat(),
                     "is_trial": trial})

    def other_plan():
        return rng.choice([p for p in PLANS if p != focus])

    long_start, long_end = start - timedelta(days=rng.randint(30, 200)), end + timedelta(days=rng.randint(30, 300))
    kinds = [kind for kind, size in sizes.items() for _ in range(size)]
    rng.shuffle(kinds)
    for company, kind in zip(companies, kinds + ["filler"] * (count - len(kinds))):
        if kind == "good":
            logins(company, rng.randint(4, 9), per_day=(1, 2), pool=weekdays)
            subscribe(company, focus if plan else rng.choice(PLANS), long_start, long_end)
        elif kind == "good_multi":
            picked = rng.sample(weekdays, 4)
            for k, day in enumerate(picked):
                for _ in range(2):
                    users.append({"company_id": company, "account_id": f"{company}-A{k % 2 + 1}", "login_at": stamp(day)})
            subscribe(company, focus if plan else rng.choice(PLANS), long_start, long_end)
        elif kind == "trial_only":
            logins(company, rng.randint(5, 9), pool=weekdays)
            subscribe(company, focus, start - timedelta(days=10), end + timedelta(days=20), trial=1)
        elif kind == "ended_mid":
            logins(company, rng.randint(5, 8), pool=weekdays)
            subscribe(company, focus if plan else rng.choice(PLANS), start - timedelta(days=200), start + timedelta(days=rng.randint(8, 18)))
        elif kind == "two_days":
            logins(company, 2, per_day=(3, 4), pool=weekdays)
            subscribe(company, focus if plan else rng.choice(PLANS), long_start, long_end)
        elif kind == "paid_idle":
            logins(company, rng.randint(0, 1), pool=weekdays)
            subscribe(company, focus if plan else rng.choice(PLANS), long_start, long_end)
        elif kind == "other_plan":
            logins(company, rng.randint(4, 8), pool=weekdays)
            subscribe(company, other_plan(), long_start, long_end)
        elif kind == "weekend_heavy":
            logins(company, 2, per_day=(1, 1), pool=weekdays)
            logins(company, 2, per_day=(1, 1), pool=weekend)
            subscribe(company, focus if plan else rng.choice(PLANS), long_start, long_end)
        elif kind == "few_logins":
            logins(company, 3, per_day=(1, 1), pool=weekdays)
            subscribe(company, focus if plan else rng.choice(PLANS), long_start, long_end)
        else:
            logins(company, rng.randint(0, 6))
            if rng.random() < 0.6:
                subscribe(company, rng.choice(PLANS), long_start - timedelta(days=400), start - timedelta(days=rng.randint(5, 60)))
    spare = iter(f"C{rng.randint(100, 999)}{i:02d}" for i in range(count, count + 40))
    notes = []
    if "bad" in features:
        for _ in range(2):
            company = next(spare)
            logins(company, rng.randint(5, 8), pool=weekdays)
            # inside the month, the dates swapped: under 当月任意一天 it would count unless dropped; under 月末那天 it
            # can never count, so there it only tests the report
            subscribe(company, focus if plan else rng.choice(PLANS), start + timedelta(days=12), start + timedelta(days=4))
            notes.append(company)
    if "overlap" in features:
        for _ in range(2):
            company = next(spare)
            logins(company, rng.randint(5, 8), pool=weekdays)
            p = focus if plan else rng.choice(PLANS)
            subscribe(company, p, long_start, end + timedelta(days=40))
            subscribe(company, p, start + timedelta(days=5), long_end)
    if "convert" in features:
        for _ in range(2):
            company = next(spare)
            logins(company, rng.randint(5, 8), pool=weekdays)
            switch = start + timedelta(days=rng.randint(10, 18))
            subscribe(company, focus, start - timedelta(days=15), switch - timedelta(days=1), trial=1)
            subscribe(company, focus, switch, long_end)
    if "utc" in features:
        # Beijing early-morning logins on the 1st sit in the previous month in UTC; late-evening UTC logins on the last
        # day are the next month in Beijing. Without the shift, the counts on the threshold move.
        for _ in range(3):
            company = next(spare)
            picked = rng.sample([d for d in weekdays if d.day > 2 and d != end], 2)
            for day in picked:
                users.append({"company_id": company, "account_id": f"{company}-A1", "login_at": stamp(day)})
            users.append({"company_id": company, "account_id": f"{company}-A1", "login_at": stamp(start, hour=1, minute=rng.randint(0, 59))})
            if r["active"] == "logins":
                for _ in range(2):
                    users.append({"company_id": company, "account_id": f"{company}-A1", "login_at": stamp(rng.choice(picked))})
            subscribe(company, focus if plan else rng.choice(PLANS), long_start, long_end)
        for _ in range(2):
            company = next(spare)
            picked = rng.sample([d for d in weekdays if d != end], 2)
            for day in picked:
                users.append({"company_id": company, "account_id": f"{company}-A1", "login_at": stamp(day)})
            after = end + timedelta(days=1)
            users.append({"company_id": company, "account_id": f"{company}-A1", "login_at": stamp(after, hour=6, minute=rng.randint(0, 59))})
            if r["active"] == "logins":
                for _ in range(2):
                    users.append({"company_id": company, "account_id": f"{company}-A1", "login_at": stamp(rng.choice(picked))})
            subscribe(company, focus if plan else rng.choice(PLANS), long_start, long_end)
    if "merge" in features:
        for _ in range(2):
            old, new = next(spare), next(spare)
            shared = rng.sample(weekdays, 4)
            for day in shared[:2]:
                users.append({"company_id": old, "account_id": f"{old}-A1", "login_at": stamp(day)})
            for day in shared[2:]:
                users.append({"company_id": new, "account_id": f"{new}-A1", "login_at": stamp(day)})
            if r["active"] == "logins":
                for day in shared:
                    users.append({"company_id": new, "account_id": f"{new}-A2", "login_at": stamp(day)})
            subscribe(old, focus if plan else rng.choice(PLANS), long_start, long_end)
            merges.append({"old_company_id": old, "new_company_id": new,
                           "merged_on": (start + timedelta(days=rng.randint(3, 20))).isoformat()})
    rng.shuffle(users)
    rng.shuffle(subs)
    return users, subs, merges, utc, notes


def evaluate(spec, users, subs, merges, utc, *, shift=True, use_merges=True, drop_bad=True, trial_out=True,
             distinct=True, rule_override=None):
    """The rule's answer, or a variant with one safeguard switched off (to prove each trap matters)."""
    name, group, segment, rule, month, plan, features = spec
    r = RULES[rule_override or rule]
    start, end = first_day(month), last_day(month)
    owner = {m["old_company_id"]: m["new_company_id"] for m in merges} if use_merges else {}
    activity = {}
    for row in users:
        moment = datetime.strptime(row["login_at"], "%Y-%m-%d %H:%M:%S") + (timedelta(hours=8) if utc and shift else timedelta(0))
        day = moment.date()
        if not start <= day <= end:
            continue
        company = owner.get(row["company_id"], row["company_id"])
        activity.setdefault(company, []).append(day)
    active = set()
    for company, seen in activity.items():
        if r["active"] == "days":
            value = len(set(seen)) if distinct else len(seen)
        elif r["active"] == "workdays":
            value = len({d for d in seen if d.weekday() < 5})
        else:
            value = len(seen)
        if value >= r["need"]:
            active.add(company)
    paid = set()
    for row in subs:
        s, e = date.fromisoformat(row["start_date"]), date.fromisoformat(row["end_date"])
        if drop_bad and e < s:
            continue
        if trial_out and row["is_trial"]:
            continue
        if plan and row["plan"] != plan:
            continue
        if r["excluded_plan"] and row["plan"] == r["excluded_plan"]:
            continue
        if r["paid"] == "month_end" and not (s <= end <= e):
            continue
        if r["paid"] == "any_day" and not (s <= end and e >= start):
            continue
        paid.add(owner.get(row["company_id"], row["company_id"]))
    return sorted(active & paid)


def table_csv(rows, fields) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def data_note(spec, utc) -> str:
    return "\n".join([
        "# 数据说明", "",
        "- users：每条是一次登录。company_id 企业 ID，account_id 账号 ID，login_at 登录时间（格式 YYYY-MM-DD HH:MM:SS），"
        + ("**时区是 UTC**。" if utc else "时区是北京时间。"),
        "- subscriptions：每条是一段订阅。plan 套餐名（基础版、专业版、旗舰版），start_date、end_date 起止日（含当天，格式 YYYY-MM-DD），"
        "is_trial 是否试用（1 是试用，0 是正式订阅）。",
        "- merges：企业合并记录。old_company_id 被合并的旧企业 ID，new_company_id 合并后的新企业 ID，merged_on 合并日期。",
        "- 你的 SQL 会在一个 SQLite 库上运行：按 schema.sql 建表，三张 CSV 原样导入（表头是字段名）。", "",
    ])


def question_text(spec, index) -> str:
    name, group, segment, rule, month, plan, features = spec
    m = int(month.split("-")[1])
    scope = f"（只算{plan}）" if plan else ""
    return (
        f"{OPENINGS[index % len(OPENINGS)]}{month[:4]} 年 {m} 月的月活跃付费企业有多少家？{scope}\n\n"
        "这次适用的指标口径工作规则和数据在工作目录：工作规则.md、schema.sql、数据说明.md、users.csv、subscriptions.csv、merges.csv。"
    )


def compute(spec, users, subs, merges, utc, notes) -> dict:
    name, group, segment, rule, month, plan, features = spec
    r = RULES[rule]
    answer = evaluate(spec, users, subs, merges, utc)
    traps = {}
    if utc:
        traps["不把 UTC 换成北京时间"] = evaluate(spec, users, subs, merges, utc, shift=False)
    if merges:
        traps["不按合并记录归到新 ID"] = evaluate(spec, users, subs, merges, utc, use_merges=False)
    if notes and r["paid"] == "any_day":
        traps["不剔除结束日早于开始日的订阅"] = evaluate(spec, users, subs, merges, utc, drop_bad=False)
    traps["不剔除试用"] = evaluate(spec, users, subs, merges, utc, trial_out=False)
    if r["active"] == "days":
        traps["按登录次数而不是不同自然日算活跃"] = evaluate(spec, users, subs, merges, utc, distinct=False)
    for other in ("R1", "R2", "R3"):
        if other != rule:
            traps[f"套用 {other} 的口径"] = evaluate(spec, users, subs, merges, utc, rule_override=other)
    for trap, value in traps.items():
        assert len(value) != len(answer), (name, trap, len(value), len(answer))
    bad = [s for s in subs if s["end_date"] < s["start_date"]]
    assert sorted(s["company_id"] for s in bad) == sorted(notes), (name, bad, notes)
    return {
        "规则集": f"{rule}（{r['brand']}）",
        "结果": len(answer),
        "符合条件的企业": answer,
        "数据问题（结束日早于开始日的订阅）": [f"{s['company_id']}：{s['start_date']} 到 {s['end_date']}" for s in bad] or "无",
        "login_at 时区": "UTC（要先加 8 小时）" if utc else "北京时间",
        "合并记录": [f"{m['old_company_id']} → {m['new_company_id']}" for m in merges] or "无",
        "这道题的陷阱（忽略后会算出的数）": {trap: len(value) for trap, value in traps.items()},
        "交付段落": "、".join(f"## {s}" for s in r["sections"]),
    }


def scenario_package():
    (SCENARIO / "personas").mkdir(parents=True, exist_ok=True)
    (SCENARIO / "profile.md").write_text(TASK + "\n")
    (SCENARIO / "onboarding.md").write_text(ONBOARDING + "\n")
    (SCENARIO / "personas" / "cfo.md").write_text("同事来问一个业务指标；每道题的问题、数据和口径规则由脚本给出。\n")
    (SCENARIO / "scenario.json").write_text(json.dumps({
        "initial": [],
        "criteria": [{"id": i, "check": text, "severity": severity} for i, severity, text in CRITERIA],
    }, ensure_ascii=False, indent=1) + "\n")
    visible = ["counterpart", "analyst", "curator"]
    (SCENARIO / "contract.json").write_text(json.dumps(
        {"checks": {i: {"visibility": visible} for i, _, _ in CRITERIA}}, ensure_ascii=False, indent=1) + "\n")


def main():
    names = [spec[0] for spec in SPECS]
    assert len(names) == len(set(names)) == 40
    (HERE / "rules").mkdir(exist_ok=True)
    for rule, r in RULES.items():
        (HERE / "rules" / f"{rule}.md").write_text(r["text"])
    bank, scripts, retries = [], [], []
    for index, spec in enumerate(SPECS):
        name, group, segment, rule = spec[:4]
        assert (segment == "common") == (not spec[6]), name
        for salt in range(60):
            users, subs, merges, utc, notes = build(spec, random.Random(f"{name}:{salt}"))
            try:
                reference = compute(spec, users, subs, merges, utc, notes)
                break
            except AssertionError as exc:
                retries.append((name, salt, str(exc)[:140]))
        else:
            raise RuntimeError(f"{name}: no seed passes the checks")
        files = {
            "工作规则.md": RULES[rule]["text"], "schema.sql": SCHEMA, "数据说明.md": data_note(spec, utc),
            "users.csv": table_csv(users, ["company_id", "account_id", "login_at"]),
            "subscriptions.csv": table_csv(subs, ["company_id", "plan", "start_date", "end_date", "is_trial"]),
            "merges.csv": table_csv(merges, ["old_company_id", "new_company_id", "merged_on"]),
        }
        text = question_text(spec, index)
        bank.append({"name": name, "group": group, "segment": segment, "rules": rule, "text": text, "files": files,
                     "reference": reference})
        label = {"train": "培养", "same": "考试·同规则", "new": "考试·新规则"}[group]
        scripts.append({"name": name, "title": f"{name} · {label} · {RULES[rule]['brand']} {spec[4]}", "exam": group != "train",
                        "steps": [{"text": text, "files": files}]})
    (HERE / "questions.json").write_text(json.dumps(bank, ensure_ascii=False, indent=1) + "\n")
    (HERE / "scripts.json").write_text(json.dumps(scripts, ensure_ascii=False, indent=1) + "\n")
    scenario_package()
    for retry in retries:
        print("retried:", *retry)
    print(f"{len(bank)} questions, answers {[q['reference']['结果'] for q in bank]}, scenario at {SCENARIO.name}")


if __name__ == "__main__":
    main()
