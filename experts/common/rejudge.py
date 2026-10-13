"""离线补判一次考试：把会话记录里某次考试的答卷（held-out 会话）拿出来，用同一个评审逐题判，打印判错数并存档。
用于考试已经作答、但评审中途失败（例如网关超时）的那一次。

  uv run python experts/common/rejudge.py <iteration json> <案例目录> <pending|轮次序号> [输出 json]
"""

import asyncio
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
sys.path.insert(0, str(REPOSITORY))
sys.path.insert(0, str(HERE))

from examiner import FILE_LIMIT, Examiner, judging  # noqa: E402
from raven.config.loader import load_config  # noqa: E402
from raven.providers.factory import make_lazy_provider  # noqa: E402
from officetext import render  # noqa: E402
from review import reply  # noqa: E402

TEXT = {".md", ".txt", ".csv", ".json", ".yaml", ".yml", ".html"}


def product(exchanges: list[dict]) -> str:
    """What the examiner would have judged: each turn's reply text, then the text files it delivered."""
    parts = []
    for exchange in exchanges:
        parts.append(reply(exchange))
        for path in (exchange.get("execution") or {}).get("deliverables") or ():
            file = Path(path)
            if file.suffix.lower() in TEXT and file.is_file():
                parts.append(f"【交付文件 {file.name}】\n{file.read_text(errors='replace')[:FILE_LIMIT]}")
            elif file.suffix.lower() in (".docx", ".xlsx") and file.is_file():
                parts.append(f"【交付文件 {file.name}（文字版）】\n{render(file.name, file.read_bytes())[:FILE_LIMIT]}")
    return "\n\n".join(part for part in parts if part)


async def main() -> None:
    record = json.loads(Path(sys.argv[1]).read_text())
    case = Path(sys.argv[2]).resolve()
    part = record["pending"] if sys.argv[3] == "pending" else record["rounds"][int(sys.argv[3])]
    live = json.loads((case / "live.json").read_text())
    config = judging(load_config((case / live["config"]).resolve()), case)
    examiner = Examiner(make_lazy_provider(config), case / live["scenario"])
    sessions = part["holdout"]
    names = sorted(name for name in sessions if name in examiner.case.bank)
    results = await asyncio.gather(*(examiner.judge(examiner.case.bank[n], product(sessions[n])) for n in names))
    rows, failed, judged = [], {"x": [0, 0], "y": [0, 0]}, 0
    for name, (scoring, loose) in zip(names, results):
        applicable = [v for v in scoring.items if v.applicable]
        bad = [v.id for v in applicable if v.count]
        failed[name[0]][0] += len(bad)
        failed[name[0]][1] += len(applicable)
        rows.append({"name": name, "failed": bad, "judged": [v.id for v in applicable],
                     "verdicts": [v.model_dump() for v in scoring.items], "loose": loose})
        print(f"{name}: {len(bad)}/{len(applicable)} {bad}", flush=True)
    total = sum(v[0] for v in failed.values()), sum(v[1] for v in failed.values())
    print(f"REJUDGED same rules x {failed['x'][0]}/{failed['x'][1]}, new rules y {failed['y'][0]}/{failed['y'][1]}, "
          f"all {total[0]}/{total[1]}", flush=True)
    if len(sys.argv) > 4:
        Path(sys.argv[4]).write_text(json.dumps(rows, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
