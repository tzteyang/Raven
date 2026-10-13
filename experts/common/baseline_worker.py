"""Run one exported baseline's three acceptance repetitions alongside the main pipeline.

Run inside tmux from the repository root: uv run python experts/common/baseline_worker.py contract-review plain
Only plain/v0 are accepted. Prepare all hosts before the main pipeline reaches this baseline;
later accept processes join by the identical run-id lock and validate the existing checkpoint.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from accept import atomic_json, run_lock
from scorecard import reports_of

# The checkout holds the code and experts/; runs/ and secrets/ sit beside it in the workspace, since an employee's
# working directory may not be inside the repository (experimental.automation.employee.workplace).
REPOSITORY = Path(__file__).resolve().parents[2]
ROOT = REPOSITORY.parent
COMMON = Path(__file__).resolve().parent
FILES = ("harness.json", "run.py", "config.json", "subagent.json")


def prepare_host(source: Path, host: Path, private: Path) -> None:
    """Publish one complete host atomically, or validate it without touching runtime state."""
    missing = [name for name in FILES if not (source / name).is_file()]
    if missing:
        raise ValueError(f"incomplete baseline export: {missing}")
    agent = host / "agents" / source.name
    if not host.exists():
        host.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=f".{host.name}-", dir=host.parent))
        try:
            shutil.copytree(source, temporary / "agents" / source.name)
            (temporary / "config.json").symlink_to(private)
            try:
                temporary.rename(host)
            except OSError:
                if not host.exists():
                    raise
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)
    for name in FILES:
        if not (agent / name).is_file() or (agent / name).read_bytes() != (source / name).read_bytes():
            raise ValueError(f"existing baseline host differs from its export: {agent / name}")
    config = host / "config.json"
    if not config.is_symlink() or config.resolve() != private.resolve():
        raise ValueError(f"baseline host must use the existing private configuration symlink: {config}")


def accepted_report(case: Path, tag: str, run_id: str) -> Path:
    """Validate this exact run's published report, independent of other repeats' order."""
    checkpoint = case / "accept-runs" / run_id / "partial.json"
    saved = json.loads(checkpoint.read_text())
    if saved.get("status") != "complete" or saved.get("run_id") != run_id:
        raise ValueError(f"incomplete acceptance checkpoint: {checkpoint}")
    report = Path(saved["report"])
    admitted, excluded = reports_of(case, tag)
    if report not in {path for path, _ in admitted}:
        issues = next((issues for path, issues in excluded if path == report), ["report missing"])
        raise ValueError(f"acceptance report was not admitted: {report.name}: {issues}")
    return report


class BaselineWorker:
    def __init__(self, case: str, version: str, *, root: Path = ROOT, repository: Path = REPOSITORY):
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", case) or version not in ("plain", "v0"):
            raise ValueError("choose a known case and one baseline: plain or v0")
        self.root, self.repository, self.name, self.version = root, repository, case, version
        delivery = root / "runs/experts/control" / f"{case}.json"
        if delivery.exists() and json.loads(delivery.read_text()).get("acceptance_source") == "user":
            raise ValueError("user accepted this expert; remaining acceptance is cancelled")
        self.case = repository / "experts/cases" / case
        if not (self.case / "live.json").is_file():
            raise ValueError(f"no case: {case}")
        self.source = root / "runs/experts" / f"host-{version}" / "agents" / f"expert-{case}"
        self.control = root / "runs/experts/control/baselines"
        self.state_file = self.control / f"{case}-{version}.json"

    def run_id(self, repeat: int) -> str:
        if repeat not in (1, 2, 3):
            raise ValueError("baseline repetitions are 1, 2 and 3")
        return f"parallel-v1-{self.version}-{repeat}"

    def host(self, repeat: int) -> Path:
        return self.root / "runs/experts/accept-hosts" / self.name / self.run_id(repeat)

    def state(self, stage: str, **extra) -> None:
        self.control.mkdir(parents=True, exist_ok=True)
        value = {"case": self.name, "version": self.version, "stage": stage,
                 "updated": time.time(), "pid": os.getpid(), **extra}
        atomic_json(self.state_file, value)
        print(time.strftime("%m-%d %H:%M:%S"), self.name, self.version, stage,
              json.dumps(extra, ensure_ascii=False), flush=True)

    def prepare(self) -> None:
        """Publish complete hosts atomically and never replace an existing runtime or export."""
        if json.loads((self.source / "harness.json").read_text()).get("revision") != self.version:
            raise ValueError("exported revision does not match the requested baseline")
        private = self.root / "secrets/raven-experts.json"
        for repeat in (1, 2, 3):
            prepare_host(self.source, self.host(repeat), private)

    def accepted(self, repeat: int) -> Path:
        return accepted_report(self.case, self.version, self.run_id(repeat))

    def command(self, repeat: int) -> int:
        log = self.control / "logs" / f"{self.name}-{self.run_id(repeat)}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        env = {**os.environ,
               "NO_PROXY": os.environ.get("NO_PROXY", "") + ",127.0.0.1,localhost",
               "no_proxy": os.environ.get("no_proxy", "") + ",127.0.0.1,localhost"}
        argv = [sys.executable, str(COMMON / "accept.py"), str(self.case), str(self.host(repeat)),
                "--run-id", self.run_id(repeat), "--wait-for-lock"]
        with log.open("a") as output:
            return subprocess.run(argv, cwd=self.repository, env=env,
                                  stdout=output, stderr=subprocess.STDOUT).returncode

    def run(self, *, prepare_only: bool = False) -> None:
        with run_lock(self.control / f"{self.name}-{self.version}"):
            try:
                self.state("preparing")
                self.prepare()
                self.state("ready", hosts=[str(self.host(repeat)) for repeat in (1, 2, 3)])
                if prepare_only:
                    return
                reports = []
                for repeat in (1, 2, 3):
                    self.state("acceptance", repeat=repeat, run_id=self.run_id(repeat))
                    code = self.command(repeat)
                    if code:
                        raise RuntimeError(f"acceptance exited {code}; resume this worker to reuse its checkpoint")
                    reports.append(str(self.accepted(repeat)))
                if len(set(reports)) != 3:
                    raise ValueError("baseline repetitions must have distinct reports")
                self.state("complete", repetitions=3, reports=reports)
            except BaseException as exc:
                self.state("failed", error=f"{type(exc).__name__}: {exc}")
                raise


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case")
    parser.add_argument("version", choices=("plain", "v0"))
    parser.add_argument("--prepare-only", action="store_true", help="prepare all three hosts without model calls")
    args = parser.parse_args(argv)
    if not args.prepare_only and not os.environ.get("TMUX"):
        parser.error("run this long-lived worker inside tmux")
    BaselineWorker(args.case, args.version).run(prepare_only=args.prepare_only)


if __name__ == "__main__":
    main()
