"""一次考试按验收项、按题组（同规则 x / 新规则 y）数判错：python3 tally.py <iteration json> [pending|轮次序号]"""

import collections
import json
import sys

record = json.load(open(sys.argv[1]))
which = sys.argv[2] if len(sys.argv) > 2 else "pending"
part = record["pending"] if which == "pending" else record["rounds"][int(which)]
items = [i for s in part["holdout_signals"] for i in s["items"]]
by = collections.defaultdict(lambda: [0, 0])
for i in (i for i in items if ":" in i["id"]):
    criterion, name = i["id"].split(":")
    key = (criterion, name[0])
    by[key][1] += 1
    by[key][0] += i["result"] == "fail"
for (criterion, group), (failed, judged) in sorted(by.items()):
    print(f"{criterion:14s} {group}: {failed}/{judged}")
x = sum(v[0] for k, v in by.items() if k[1] == "x"), sum(v[1] for k, v in by.items() if k[1] == "x")
y = sum(v[0] for k, v in by.items() if k[1] == "y"), sum(v[1] for k, v in by.items() if k[1] == "y")
print(f"same rules x: {x[0]}/{x[1]}   new rules y: {y[0]}/{y[1]}")
