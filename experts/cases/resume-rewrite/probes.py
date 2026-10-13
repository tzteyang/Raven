"""写出五份作者构造答卷，供独立评审模型探测；本脚本不打分。"""

import json
import sys
from pathlib import Path

from make import table
from measure import measure

HERE = Path(__file__).resolve().parent


def rows(q):
    got = measure(q, q["reference"]["一种合规交付"])
    return [r["原句列"] for r in got["逐行测量"]], [r["改写列"] for r in got["逐行测量"]]


def main():
    bank = {q["name"]: q for q in json.loads((HERE / "questions.json").read_text())}
    q = bank["t11"]
    before, good = rows(q)
    # 正确答卷使用事实里的等值数；叙述略作人工变式。
    good[0] = good[0].replace("执行内容增长计划", "推进内容增长计划")
    good[1] = good[1].replace("完成选题、编辑和推送", "负责选题、编辑及推送")
    right_t = table("R1", before, good)
    bad = list(good)
    bad[0] = bad[0].rstrip("。") + "，关注人数增长310%。"
    bad[2] = bad[2].rstrip("。") + f"，完成{q['reference']['不得进入改写的关键词'][0]}项目。"
    team = q["reference"]["职责固定说法"]
    # 保留人数和其他结果，故意只夸大职责，避免由数字丢失造成额外记错。
    source_team = next(r for r in q["reference"]["逐条依据"] if r["条目"] == "E4")["保留的结果"][0]["事实表写法"]
    bad[3] = bad[3].replace("带 " + source_team.removesuffix("人") + " 人小组", "带领团队（" + source_team + "）")
    right_y_q = bank["y06"]
    y_before, y_good = rows(right_y_q)
    right_y = table("R3", y_before, y_good)
    y_bad = list(y_good)
    end_value = right_y_q["reference"]["逐条依据"][0]["保留的结果"][1]["事实表写法"]
    confirmed_end = int(right_y_q["reference"]["逐条依据"][0]["保留的结果"][1]["数值"][0])
    y_bad[0] = y_bad[0].replace(end_value, f"{confirmed_end + 17000}人")
    y_bad[1] = "开展内容策划，完成选题、编辑和推送。"
    wrong_y = table("R3", y_before, y_bad, ["F01", "F02", "F02", "F04", "F05"])
    probes = [
        {"name": "t11", "label": "right", "expect": [], "answer": right_t},
        {"name": "t11", "label": "wrong", "expect": ["RW-fact", "RW-keyword", "RW-role"], "answer": table("R1", before, bad)},
        {"name": "y06", "label": "right", "expect": [], "answer": right_y},
        {"name": "y06", "label": "wrong", "expect": ["RW-fact", "RW-writing", "RW-format"], "answer": wrong_y},
        {"name": "t11", "label": "right-plus-wrapper", "expect": ["RW-format"],
         "answer": "下面是改写，我有999年SEO经验，会带领团队。\n\n" + right_t + "\n\n补充说明：增长999%。"},
    ]
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "probes" / "probe-resume-rewrite.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(probes, ensure_ascii=False, indent=2) + "\n")
    print(f"5 probes -> {target}")


if __name__ == "__main__":
    main()
