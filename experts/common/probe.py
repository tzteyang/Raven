"""评审探测：用手写答卷（每道题一份对的、一份错的）看评审能不能挂出该挂的验收项。

  uv run python experts/common/probe.py <案例目录> <探测答卷 json>

答卷格式见 experts/BUILDING.md 的「评审探测」。评审的模型和强度取自案例 live.json 里 assessor 角色，服务商从案例
live.json 指向的 Raven 配置里按模型名找。每份答卷打印逐项判定，末尾 `-> MATCH` 表示挂出的验收项正好是 expect。
"""

import asyncio
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

from examiner import Examiner, judging  # noqa: E402
from raven.config.loader import load_config  # noqa: E402
from raven.providers.factory import make_lazy_provider  # noqa: E402


async def main() -> None:
    case, probes = Path(sys.argv[1]).resolve(), json.loads(Path(sys.argv[2]).read_text())
    live = json.loads((case / "live.json").read_text())
    config = judging(load_config((case / live["config"]).resolve()), case)
    examiner = Examiner(make_lazy_provider(config), case / live["scenario"])
    results = await asyncio.gather(*(examiner.judge(examiner.case.bank[p["name"]], p["answer"]) for p in probes))
    for probe, (scoring, loose) in zip(probes, results):
        print(f"\n=== {probe['name']} ({probe['label']}) expect fail: {probe['expect']}")
        for v in scoring.items:
            mark = "-" if not v.applicable else ("FAIL" if v.count else "pass")
            print(f"  {v.id}: {mark} {v.count} | {v.reason[:160]}")
            for e in v.errors:
                print(f"      「{e.quote[:60]}」 {e.problem[:140]}")
        if loose:
            print("  loose quotes:", loose)
        failed = sorted(v.id for v in scoring.items if v.applicable and v.count)
        print("  -> MATCH" if failed == sorted(probe["expect"]) else f"  -> MISMATCH: failed {failed}")


if __name__ == "__main__":
    asyncio.run(main())
