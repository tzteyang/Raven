"""自检：另写一遍算法，只读员工看到的文件（工作规则.md、本周评价.md、问题分类表.md），从规则原文读出口径，
重算每道题报哪几类、顺序、条数、占比、转给谁、哪些评价能引用，和参考答案（make.py 算的）逐题比对。

  python3 check.py
"""

import json
import re
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOP = {"前三": 3, "前两名": 2}


def rows(markdown: str) -> list[list[str]]:
    out = []
    for line in markdown.splitlines():
        if line.startswith("|") and not line.startswith("|---"):
            out.append([cell.strip() for cell in line.strip("|").split("|")])
    return out[1:]


def rounded(value: Fraction, places: int) -> str:
    scaled = value * 10 ** places
    whole = int(scaled)
    if scaled - whole >= Fraction(1, 2):
        whole += 1
    text = str(whole).rjust(places + 1, "0")
    return (text[:-places] + "." + text[-places:] if places else text) + "%"


def solve(files: dict) -> dict:
    rules = files["工作规则.md"]
    top = TOP[re.search(r"只报条数(前三|前两名)", rules).group(1)]
    over_all = "÷ 全部评价条数" in rules
    places = 1 if "保留一位小数" in rules else 0
    if "1 星评价多的排前面" in rules and "1 到" not in rules.split("条数相同的")[1].split("\n")[0]:
        low = {1}
    else:
        low = set(range(1, int(re.search(r"条数相同的，1 到 (\d) 星", rules).group(1)) + 1))
    latest = "选日期最新的那一条" in rules
    quote_stars = set(range(1, int(re.search(r"这一类的 1 到 (\d) 星评价里", rules).group(1)) + 1)) if not latest else None
    table = [(name, keys.split("、") + phrases.split("、"), team) for name, keys, phrases, team in rows(files["问题分类表.md"])]
    reviews = [{"id": r[0], "uid": r[1], "stars": int(r[3]), "date": r[4], "text": r[5]} for r in rows(files["本周评价.md"])]
    for review in reviews:
        review["cats"] = {name for name, words, _ in table if any(word in review["text"] for word in words)}
    people = defaultdict(lambda: {"cats": set(), "stars": 9})
    for review in reviews:
        person = people[review["uid"]]
        person["cats"] |= review["cats"]
        person["stars"] = min(person["stars"], review["stars"])
    count = {name: sum(name in p["cats"] for p in people.values()) for name, _, _ in table}
    lows = {name: sum(name in p["cats"] and p["stars"] in low for p in people.values()) for name, _, _ in table}
    base = len(people) if over_all else sum(1 for p in people.values() if p["cats"])
    order = [name for name, _, _ in table]
    ranked = sorted(order, key=lambda n: (-count[n], -lows[n], order.index(n)))[:top]
    teams = {name: team for name, _, team in table}
    out = []
    for name in ranked:
        mine = [r for r in reviews if name in r["cats"]]
        if latest:
            pool = [r for r in mine if r["stars"] == 1] or [r for r in mine if r["stars"] == 2]
            pool.sort(key=lambda r: (r["date"], -int(r["id"][1:])))
            allowed = [pool[-1]["id"]] if pool else []
        else:
            allowed = [r["id"] for r in mine if r["stars"] in quote_stars]
        out.append((name, count[name], rounded(Fraction(count[name] * 100, base), places), teams[name], sorted(allowed)))
    return {"top": out, "base": base, "counts": count}


def main() -> None:
    wrong = []
    for q in json.loads((HERE / "questions.json").read_text()):
        got = solve(q["files"])
        ref = q["reference"]
        want = [(e["类别"], e["条数"], e["占比（按规则取舍）"], e["转给"],
                 sorted(item.split("：")[0] for item in e["可以引用的评价（编号：星级）"])) for e in ref["报的类别（按顺序）"]]
        if got["top"] != want or got["counts"] != ref["各类条数（全部类别）"] or got["base"] != int(ref["占比分母"].split("（")[0]):
            wrong.append((q["name"], got, want))
    print("mismatches:", wrong or "none")
    assert not wrong


if __name__ == "__main__":
    main()
