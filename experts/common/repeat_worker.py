"""Run exactly one existing acceptance repetition, alongside the other pipeline workers.

Inside tmux, from the repository root: uv run python experts/common/repeat_worker.py CASE TAG REPEAT
TAG is plain, v0 or the first 12 characters of the current trained export's revision;
REPEAT is 1, 2 or 3. --prepare-only validates/prepares this host without model calls.
The pipeline's existing parallel-v1-TAG-REPEAT identity is retained: accept.py waits
for its lock and reuses the checkpoint, including an already completed report.
"""

import argparse
import json
import os
import re
from pathlib import Path

from accept import run_lock
from baseline_worker import REPOSITORY, ROOT, BaselineWorker, prepare_host


class RepeatWorker(BaselineWorker):
    def __init__(self, case: str, tag: str, repeat: int, *, root: Path = ROOT, repository: Path = REPOSITORY):
        if tag not in ("plain", "v0") and not re.fullmatch(r"[0-9a-f]{12}", tag):
            raise ValueError("tag must be plain, v0 or the current trained revision's first 12 characters")
        if type(repeat) is not int or repeat not in (1, 2, 3):
            raise ValueError("acceptance repetitions are 1, 2 and 3")
        # Reuse the baseline host identity, subprocess and strict completion checks.
        super().__init__(case, tag if tag in ("plain", "v0") else "plain", root=root, repository=repository)
        self.version, self.repeat = tag, repeat
        home = f"host-{tag}" if tag in ("plain", "v0") else "host"
        self.source = root / "runs/experts" / home / "agents" / f"expert-{case}"
        self.control = root / "runs/experts/control/repeats"
        self.state_file = self.control / f"{case}-{tag}-{repeat}.json"

    def prepare(self) -> None:
        revision = json.loads((self.source / "harness.json").read_text()).get("revision", "")
        if revision[:12] != self.version:
            raise ValueError("exported revision does not match the requested tag")
        prepare_host(self.source, self.host(self.repeat), self.root / "secrets/raven-experts.json")

    def run(self, *, prepare_only: bool = False) -> None:
        # This lock protects only this worker's status; accept.py owns the shared run lock.
        with run_lock(self.control / f"{self.name}-{self.version}-{self.repeat}"):
            identity = {"repeat": self.repeat, "run_id": self.run_id(self.repeat)}
            try:
                self.state("preparing", **identity)
                self.prepare()
                self.state("ready", host=str(self.host(self.repeat)), **identity)
                if prepare_only:
                    return
                self.state("acceptance", **identity)
                code = self.command(self.repeat)
                if code:
                    raise RuntimeError(f"acceptance exited {code}; resume this worker to reuse its checkpoint")
                report = self.accepted(self.repeat)
                self.state("complete", report=str(report), **identity)
            except BaseException as exc:
                self.state("failed", error=f"{type(exc).__name__}: {exc}", **identity)
                raise


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case")
    parser.add_argument("tag")
    parser.add_argument("repeat", type=int, choices=(1, 2, 3))
    parser.add_argument("--prepare-only", action="store_true", help="prepare this host without model calls")
    args = parser.parse_args(argv)
    if not args.prepare_only and not os.environ.get("TMUX"):
        parser.error("run this long-lived worker inside tmux")
    RepeatWorker(args.case, args.tag, args.repeat).run(prepare_only=args.prepare_only)


if __name__ == "__main__":
    main()
