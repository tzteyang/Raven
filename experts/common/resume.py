"""接着跑一个停下的会话：由 run.py 按记录恢复未完成的入职、改造、考试或培养轮次。

  python3 experts/common/resume.py <端口> <案例目录>
"""

import sys
from pathlib import Path

from run import RECOVERY_STOP, AnalysisRecoveryError
from run import main as run_main


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    port, case = int(args[0]), Path(args[1]).resolve()
    session = (case / "session.txt").read_text().strip()
    run_main([str(port), str(case), session])


if __name__ == "__main__":
    try:
        main()
    except AnalysisRecoveryError as exc:
        print(f"STOPPED: {type(exc).__name__}: {exc}", flush=True)
        raise SystemExit(RECOVERY_STOP) from exc
    except Exception as exc:
        print(f"STOPPED: {type(exc).__name__}: {exc}", flush=True)
        raise
