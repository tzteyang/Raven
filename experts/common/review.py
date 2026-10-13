"""把一次考试的逐题判定和员工答卷、参考答案排在一起，给人逐条核对。

  python3 experts/common/review.py <会话的 iteration json> <案例目录> [pending|轮次序号] > 核对.md

pending 是还没进入轮次记录的那次考试（分析之前）；轮次序号从 0 开始，取那一轮记录里的考试。
"""

import json
import sys
from pathlib import Path


def reply(exchange: dict) -> str:
    """The reply text the way Execution.text reads it: the worker's Text events, joined."""
    rows = (exchange.get("execution") or {}).get("records") or ()
    return "\n".join(r["event"]["content"] for r in rows if r.get("kind") == "runner.event" and r.get("event_type") == "Text")


def main() -> None:
    record = json.loads(Path(sys.argv[1]).read_text())
    bank = {q["name"]: q for q in json.loads((Path(sys.argv[2]) / "questions.json").read_text())}
    which = sys.argv[3] if len(sys.argv) > 3 else "pending"
    part = record["pending"] if which == "pending" else record["rounds"][int(which)]
    sessions, signals = part["holdout"], part["holdout_signals"]
    items = [item for signal in signals for item in signal["items"]]
    for name in sorted(sessions):
        question = bank[name]
        print(f"======== {name}（{question['group']} · {question['rules']}）\n")
        print("参考答案：" + json.dumps(question["reference"], ensure_ascii=False) + "\n")
        for exchange in sessions[name]:
            print("员工回复：\n\n" + (reply(exchange) or "（空）") + "\n")
            for path in (exchange.get("execution") or {}).get("deliverables") or ():
                print(f"交付文件：{path}\n")
        for item in items:
            if item["session"] == name:
                print(f"- 【{item['result']}】{item['id']}：{item['note']}")
        print()


if __name__ == "__main__":
    main()
