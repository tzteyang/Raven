"""自检：另写一遍算法，只读员工看到的四份文件（工作规则、会议记录、参会人名单、公司日历）和题面，从会议记录里重新认出每件事
（按规则原文里的闭合说法）、按名单定负责人、按规则参数和日历推截止日期、分到表里或单列的那一段，再和参考答案逐题比对：
该记的事和不该写的事的关键词、每件事的负责人（协作人）、截止日期、负责人没说清的事、单列那一段的条目。另外核对会议记录里
每一句带“答应、点名、认领、撤回、完成、改期”说法的话都归到了参考答案的某件事上，参考答案没有漏事。

  python3 check.py
"""

import json
import re
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
WEEK = "一二三四五六日"
TIME = re.compile(r"下个月底前?|月底前?|下周[一二三四五六日]前?|周[一二三四五六日]前?|明天|\d+ 个工作日内|(?:中秋|国庆)?节后第一天|尽快|抓紧")
ACTION = re.compile(r"我来|交给我|我负责|你来|谁来|谁跟|看一下|了解一下|考虑一下|牵头|一起|不用做了|先不做了|取消|已经|改到|排不开"
                    r"|(?<!邀)请\S+来|你\S{1,3}一下|先放着|会后再定")
REPLY = re.compile(r"^(好的|没问题|行|收到|好|可以)。$|^我.*(看一下|了解一下|考虑一下)吧?。$|会后再定|^先放着，|^我这周排不开，"
                   r"|^(行|可以)，交给我。$|^行，那我不弄了。$")


def params(rules: str) -> dict:
    return {
        "shift": 1 if "顺延到之后的第一个工作日" in rules else -1,
        "makeup": "类型是“工作日”或“调休上班”的算工作日" in rules,
        "from_next": "“N 个工作日内”：从会议次日开始数工作日" in rules,
        "last_day": "会议所在月份的最后一天" in rules,
        "vague_second": "如果只说了“尽快”或“抓紧”：从会议次日开始数工作日，数到的第 2 个工作日" in rules,
        "look": "all" if "也算自己答应（不管带没带时间）" in rules else "timed" if "如果他回话时说了时间" in rules else "none",
        "shelved_claim": "说了“先放着”或“回头再说”的事，也记进“待认领”" in rules,
        "unclear": "host" if "负责人写会议主持人" in rules else "placeholder" if "负责人写“待认领”" in rules else "list",
        "dept_always": "每一行都写成“全名（部门）”" in rules,
        "twin_by": "title" if "写成“全名（职位）”" in rules else "dept",
        "style": "iso" if "YYYY-MM-DD" in rules else "cn" if "M月D日（周X）" in rules else "slash",
        "confirm_undated": "截止日期待确认" in rules or "要确认什么写“截止日期”" in rules,
    }


def table_rows(text: str) -> list:
    return [[c.strip() for c in line.strip().strip("|").split("|")] for line in text.splitlines()
            if line.startswith("|") and not line.startswith("|---")]


def deadline(phrase, meeting, p, kinds, notes):
    def work(d):
        return kinds[d] == "工作日" or (kinds[d] == "调休上班" and p["makeup"])

    def adjust(d):
        while not work(d):
            d += timedelta(days=p["shift"])
        return d

    def nth(start, n):
        d = start
        while True:
            if work(d):
                n -= 1
                if n == 0:
                    return d
            d += timedelta(days=1)

    if not phrase or phrase == "回头":
        return None
    if phrase in ("尽快", "抓紧"):
        return nth(meeting + timedelta(days=1), 2) if p["vague_second"] else None
    if phrase == "明天":
        return adjust(meeting + timedelta(days=1))
    week = re.fullmatch(r"(下)?周(.)前?", phrase)
    if week:
        wd = WEEK.index(week.group(2))
        if week.group(1):
            return adjust(meeting + timedelta(days=7 - meeting.weekday() + wd))
        d = meeting + timedelta(days=1)
        while d.weekday() != wd:
            d += timedelta(days=1)
        return adjust(d)
    month = re.fullmatch(r"(下个)?月底前?", phrase)
    if month:
        first = (meeting.replace(day=1) + timedelta(days=32)).replace(day=1)
        if month.group(1):
            first = (first + timedelta(days=32)).replace(day=1)
        last = first - timedelta(days=1)
        if p["last_day"]:
            return adjust(last)
        while not work(last):
            last -= timedelta(days=1)
        return last
    count = re.fullmatch(r"(\d+) 个工作日内", phrase)
    if count:
        return nth(meeting + timedelta(days=1 if p["from_next"] else 0), int(count.group(1)))
    after = re.fullmatch(r"(中秋|国庆)?节后第一天", phrase)
    if after:
        d = meeting + timedelta(days=1)
        while not (kinds[d] == "节假日" and notes.get(d, "").startswith(after.group(1) or "")):
            d += timedelta(days=1)
        while kinds[d] == "节假日":
            d += timedelta(days=1)
        while not work(d):
            d += timedelta(days=1)
        return d
    raise ValueError(phrase)


def styled(d, style) -> str:
    if d is None:
        return "待定"
    if style == "iso":
        return d.isoformat()
    if style == "cn":
        return f"{d.month}月{d.day}日（周{WEEK[d.weekday()]}）"
    return f"{d.year}/{d.month:02d}/{d.day:02d}"


def recompute(q: dict) -> dict:
    rules, record, roster, cal = (q["files"][n] for n in ("工作规则.md", "会议记录.md", "参会人名单.md", "公司日历.md"))
    p = params(rules)
    people = [dict(zip(("name", "nick", "dept", "title"), row)) for row in table_rows(roster)[1:]]
    twins = {x["name"] for x in people if sum(y["name"] == x["name"] for y in people) > 1}
    kinds, notes = {}, {}
    for row in table_rows(cal)[1:]:
        kinds[date.fromisoformat(row[0])] = row[2]
        if row[3]:
            notes[date.fromisoformat(row[0])] = row[3]
    meeting = date.fromisoformat(re.search(r"会议日期：(\d{4}-\d{2}-\d{2})", record).group(1))
    assert meeting.isoformat() in q["text"]
    host_label = re.search(r"^- 主持人：(.+)$", record, re.M).group(1)

    def person(label):
        found = re.fullmatch(r"(.+?)（(.+)）", label)
        hits = [x for x in people if x["name"] == (found.group(1) if found else label)
                and (not found or x["dept"] == found.group(2))]
        assert len(hits) == 1, label
        return hits[0]

    def resolve(call):
        found = re.fullmatch(r"(.+部)的(.+)", call)
        if found:
            hits = [x for x in people if x["dept"] == found.group(1) and x["name"] == found.group(2)]
        else:
            hits = ([x for x in people if x["name"] == call] or [x for x in people if x["nick"] == call]
                    or [x for x in people if x["title"] == call])
        return hits[0] if len(hits) == 1 else None

    def owner(x):
        if p["dept_always"]:
            return f"{x['name']}（{x['dept']}）"
        if x["name"] in twins:
            return f"{x['name']}（{x['dept'] if p['twin_by'] == 'dept' else x['title']}）"
        return x["name"]

    lines = [(m.group(1), m.group(2)) for m in re.finditer(r"^([^-#\s][^：]*)：(.+)$", record, re.M)]
    ref = q["reference"]
    keep_ref = next(v for k, v in ref.items() if k.startswith("该记的事"))
    drop_ref = next(v for k, v in ref.items() if k.startswith("不该写的事"))
    keywords = [e["关键词"] for e in keep_ref] + ([e["关键词"] for e in drop_ref] if isinstance(drop_ref, list) else [])
    chains, used, last = {k: [] for k in keywords}, set(), None
    for i, (who, text) in enumerate(lines):
        hits = [k for k in keywords if k in text]
        assert len(hits) <= 1, text
        if hits:
            chains[hits[0]].append([(who, text)])
            used.add(i)
            last = hits[0]
        elif last and REPLY.search(text) and i - 1 in used:
            chains[last][-1].append((who, text))
            used.add(i)
        else:
            assert not ACTION.search(text), ("a line with an action phrase belongs to no item", q["name"], text)
            last = None

    got = {}
    for kw, parts in chains.items():
        first = parts[0]
        who, text = first[0]
        phrase = (TIME.search(text) or [""])[0] if TIME.search(text) else ""
        item = {"owner": None, "co": None, "kind": None, "phrase": phrase}
        if re.search(r"已经(做完了|发了|上线了)", text):
            item["kind"] = "done"
        elif re.match(r"^那.+谁跟？$", text):
            shelf = re.match(r"^先放着，(.+)再说。$", first[1][1])
            item.update(kind="shelved", phrase=shelf.group(1) if shelf.group(1) != "回头" else "")
        elif "谁来" in text:
            item["kind"] = "unclaimed"
        elif re.search(r"能\S+吗？$", text):
            answer = first[1]
            found = TIME.search(answer[1])
            item.update(kind="look", owner=person(answer[0]), phrase=found[0] if found else "")
        elif "牵头" in text or "一起" in text:
            lead = re.search(r"，([^，]+?)牵头", text)
            helper = re.search(r"，([^，]+?)配合", text)
            both = re.search(r"，([^，]+?)和([^，]+?)一起", text)
            a, b = (lead.group(1), helper.group(1)) if lead else (both.group(1), both.group(2))
            item.update(kind="pair", owner=resolve(a), co=resolve(b))
        elif re.search(r"(?<!邀)请(\S+?)来", text):
            item.update(kind="assign", owner=resolve(re.search(r"(?<!邀)请(\S+?)来", text).group(1)))
        elif re.match(r"^([^，]+)，.+?(你来|你\S{1,3}一下)", text):
            item.update(kind="assign", owner=resolve(re.match(r"^([^，]+)，", text).group(1)))
            for who2, reply in first[1:]:
                passed = re.match(r"^我这周排不开，让(.+?)来吧。$", reply)
                if passed:
                    item["owner"] = resolve(passed.group(1))
        elif re.search(r"我来|交给我|我负责", text):
            item.update(kind="self", owner=person(who))
        else:
            raise AssertionError((q["name"], kw, text))
        for later in parts[1:]:
            for _, said in later:
                if re.search(r"不用做了|先不做了|取消", said):
                    item["kind"] = "withdrawn"
                moved = re.search(r"改到(.+?)(吧|行吗)", said)
                if moved:
                    item["phrase"] = moved.group(1)
                if re.search(r"已经(做完了|发了|上线了)", said):
                    item["kind"] = "done"
        if item["kind"] in ("done", "withdrawn") or (item["kind"] == "look" and p["look"] == "none") \
                or (item["kind"] == "look" and p["look"] == "timed" and not item["phrase"]) \
                or (item["kind"] == "shelved" and not p["shelved_claim"]):
            got[kw] = {"place": "drop"}
            continue
        unclear = item["kind"] in ("unclaimed", "shelved") or item["owner"] is None
        d = deadline(item["phrase"], meeting, p, kinds, notes)
        assert d is None or d > meeting, (q["name"], kw, d)
        got[kw] = {"place": "unclear" if unclear else "row", "date": styled(d, p["style"]),
                   "owner": None if unclear else owner(item["owner"]),
                   "co": (owner(item["co"]) if item["co"] else "无"), "undated": d is None}
    host = owner(person(host_label))
    return {"got": got, "p": p, "host": host}


def main() -> None:
    wrong = []
    for q in json.loads((HERE / "questions.json").read_text()):
        found = recompute(q)
        got, p, ref = found["got"], found["p"], q["reference"]
        keep_ref = next(v for k, v in ref.items() if k.startswith("该记的事"))
        drop_ref = next(v for k, v in ref.items() if k.startswith("不该写的事"))
        problems = []
        if {k for k, v in got.items() if v["place"] != "drop"} != {e["关键词"] for e in keep_ref}:
            problems.append(("keep", sorted(k for k, v in got.items() if v["place"] != "drop"),
                             sorted(e["关键词"] for e in keep_ref)))
        if {k for k, v in got.items() if v["place"] == "drop"} != {e["关键词"] for e in (drop_ref if isinstance(drop_ref, list) else [])}:
            problems.append(("drop",))
        for e in keep_ref:
            mine = got.get(e["关键词"])
            if not mine or mine["place"] == "drop":
                continue
            if mine["date"] != e["截止日期"]:
                problems.append((e["关键词"], "date", mine["date"], e["截止日期"]))
            if mine["place"] == "row" and mine["owner"] != e["负责人"]:
                problems.append((e["关键词"], "owner", mine["owner"], e["负责人"]))
            if mine["place"] == "row" and "协作人" in e and mine["co"] != e["协作人"]:
                problems.append((e["关键词"], "co", mine["co"], e["协作人"]))
            if (mine["place"] == "unclear") != e["负责人"].startswith("负责人没说清"):
                problems.append((e["关键词"], "unclear", mine["place"]))
            if mine["place"] == "unclear" and p["unclear"] == "host" and found["host"] not in e["负责人"]:
                problems.append((e["关键词"], "host", found["host"], e["负责人"]))
        confirm = ref["需要确认的事项"]
        listed = next(v for k, v in confirm.items() if k != "本规则的处理")
        listed = [] if listed and listed[0].startswith("无") else listed
        if p["unclear"] == "list":
            expected = sorted((k, v["date"]) for k, v in got.items() if v["place"] == "unclear")
            have = sorted((next(k for k in got if k in row), row.split("|")[2].strip()) for row in listed)
        else:
            expected = sorted([("负责人", k) for k, v in got.items() if v["place"] == "unclear"]
                              + [("截止日期", k) for k, v in got.items()
                                 if v["place"] == "row" and v["undated"] and p["confirm_undated"]])
            pattern = r"- (负责人|截止日期)待确认：.+（关键词：(.+)）" if p["unclear"] == "host" else r"\| .+ \| (负责人|截止日期) \|（关键词：(.+)）"
            have = sorted(re.fullmatch(pattern, row).groups() for row in listed)
        if expected != have:
            problems.append(("confirm", expected, have))
        if problems:
            wrong.append((q["name"], problems))
    print("mismatches:", wrong or "none")
    assert not wrong


if __name__ == "__main__":
    main()
