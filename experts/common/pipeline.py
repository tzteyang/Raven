"""Manage one expert from approved materials through training and repeated Raven acceptance."""

import argparse
import json
import os
import shlex
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

from baseline_worker import accepted_report
from domains import DOMAINS
from run import Studio
from scorecard import reports_of

# The checkout holds the code and experts/; runs/ and secrets/ sit beside it in the workspace, since an employee's
# working directory may not be inside the repository (experimental.automation.employee.workplace).
REPOSITORY = Path(__file__).resolve().parents[2]
ROOT = REPOSITORY.parent
COMMON = REPOSITORY / "experts/common"
CONTROL = ROOT / "runs/experts/control"
PORTS = dict(zip([
    "refund-desk", "compete-table", "store-ticket", "complaint-desk", "poster-review", "saas-metric",
    "weekly-report", "review-digest", "dental-post", "cafe-copy", "call-debrief", "meeting-actions",
    "discovery-coach", "resume-screen", "taobao-title", "contract-review", "contract-sheet", "xhs-note",
    "amazon-listing", "resume-rewrite", "landing-page", "booking-page",
], [*range(8811, 8830), 8831, 8832, 8833]))
ALIASES = {"refund-desk": "refund", "compete-table": "compete", "store-ticket": "store", "complaint-desk": "complaint", "poster-review": "poster"}
ENV = {**os.environ, "NO_PROXY": os.environ.get("NO_PROXY", "") + ",127.0.0.1,localhost", "no_proxy": os.environ.get("no_proxy", "") + ",127.0.0.1,localhost"}


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    temporary.replace(path)


def exists(session):
    return subprocess.run(["tmux", "has-session", "-t", "=" + session], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


class Pipeline:
    def __init__(self, name, repeats, port=None):
        self.name, self.repeats, self.port = name, max(3, repeats), port or PORTS[name]
        self.case = REPOSITORY / "experts/cases" / name
        self.state_file = CONTROL / (name + ".json")
        self.studio = Studio(self.port, self.case / "run.log")

    def state(self, stage, **extra):
        value = {"case": self.name, "stage": stage, "updated": time.time(), "pid": os.getpid(), **extra}
        atomic(self.state_file, value)
        print(time.strftime("%m-%d %H:%M:%S"), self.name, stage, json.dumps(extra, ensure_ascii=False), flush=True)

    def command(self, argv, log):
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a") as output:
            return subprocess.run(argv, cwd=REPOSITORY, env=ENV, stdout=output, stderr=subprocess.STDOUT).returncode

    def start_studio(self):
        try:
            with socket.create_connection(("127.0.0.1", self.port), timeout=1):
                pass
        except OSError:
            name = "experts-studio-" + self.name
            if not exists(name):
                (ROOT / "runs/experts/view").mkdir(parents=True, exist_ok=True)
                argv = [sys.executable, "-m", "experimental.webui.serve", "--runs", str(ROOT / "runs/experts/view"), "--host", "127.0.0.1", "--port", str(self.port), "--live-config", str(self.case / "live.json"), "--token-file", str(ROOT / "secrets/experts.token")]
                command = "cd " + shlex.quote(str(REPOSITORY)) + " && exec " + shlex.join(argv) + " >> " + shlex.quote(str(ROOT / "runs/experts" / ("serve-" + self.name + ".log"))) + " 2>&1"
                subprocess.run(["tmux", "new-session", "-d", "-s", name, command], env=ENV, check=True)
            time.sleep(5)
        status, info = self.studio.call("")
        if status != 200:
            raise RuntimeError(f"Studio on {self.port} did not answer")
        expected = next(self.case.glob("*/profile.md")).read_text().strip()
        if info.get("task", "").strip() != expected:
            raise RuntimeError("This port serves a different expert")

    def train(self):
        while exists("experts-run-" + self.name):
            self.state("training", detail="existing driver")
            time.sleep(30)
        log = self.case / "run.out"
        if log.exists() and "ALL ROUNDS DONE" in log.read_text(errors="replace"):
            return
        self.start_studio()
        for attempt in range(1, 9):
            session_file = self.case / "session.txt"
            if session_file.exists():
                sid = session_file.read_text().strip()
                snapshot = self.studio.state(sid)
                if not snapshot.get("attached"):
                    if not self.studio.recover_analysis(sid, snapshot):
                        code, answer = self.studio.call(f"/{sid}/resume", {})
                        if code not in (200, 202):
                            raise RuntimeError(f"Session resume refused ({code}): {answer.get('error')}")
                    for _ in range(60):
                        time.sleep(2)
                        state = self.studio.state(sid).get("state") or {}
                        if state.get("onboarded"):
                            break
                script = COMMON / "resume.py"
            else:
                script = COMMON / "run.py"
            self.state("training", attempt=attempt, port=self.port)
            code = self.command([sys.executable, str(script), str(self.port), str(self.case)], log)
            if code == 75:
                raise RuntimeError("Analysis recovery refused or exhausted; inspect run.out before retrying")
            if code == 0 and "ALL ROUNDS DONE" in log.read_text(errors="replace"):
                return
            self.state("retrying_training", attempt=attempt, exit_code=code)
            time.sleep(min(30 * attempt, 120))
        raise RuntimeError("Training failed repeatedly; inspect run.out")

    def accepted(self, tag):
        # Use the same evidence-completeness gate as the catalog and scorecard.
        return [path for path, _ in reports_of(self.case, tag)[0]]

    def acceptance_complete(self, revision):
        tags = (revision, "plain", "v0")
        if not all(len(self.accepted(tag)) >= self.repeats for tag in tags):
            return False
        # The first five experts predate parallel-v1; retain their fixed historical reports.
        if self.name in ALIASES:
            return True
        try:
            return all(len({accepted_report(self.case, tag, f"parallel-v1-{tag}-{repeat}")
                            for repeat in range(1, self.repeats + 1)}) == self.repeats for tag in tags)
        except (OSError, ValueError, KeyError):
            return False

    def accept(self):
        from export import export

        self.state("exporting")
        for label, home in [(None, "host"), ("plain", "host-plain"), ("v0", "host-v0")]:
            export(self.case, ROOT / "runs/experts" / home / "agents", label)
        revision = json.loads((ROOT / "runs/experts/host/agents" / ("expert-" + self.name) / "harness.json").read_text())["revision"][:12]
        for label, home in [(revision, "host"), ("plain", "host-plain"), ("v0", "host-v0")]:
            reports = []
            # Completion order is arbitrary: counts cannot identify a missing repeat.
            # Completed runs return read-only; in-flight runs are joined through their lock.
            for repeat in range(1, self.repeats + 1):
                run_id = f"parallel-v1-{label}-{repeat}"
                host = ROOT / "runs/experts/accept-hosts" / self.name / run_id
                agent = host / "agents" / ("expert-" + self.name)
                if not agent.exists():
                    shutil.copytree(ROOT / "runs/experts" / home / "agents" / agent.name, agent)
                config = host / "config.json"
                if not config.exists():
                    config.symlink_to(ROOT / "secrets/raven-experts.json")
                for attempt in range(1, 9):
                    self.state("acceptance", version=label, repeat=repeat, attempt=attempt, run_id=run_id)
                    log = CONTROL / "logs" / f"{self.name}-{run_id}.log"
                    code = self.command([sys.executable, str(COMMON / "accept.py"), str(self.case), str(host),
                                         "--run-id", run_id, "--wait-for-lock"], log)
                    if code == 0:
                        reports.append(accepted_report(self.case, label, run_id))
                        break
                    self.state("retrying_acceptance", version=label, repeat=repeat, attempt=attempt, exit_code=code)
                    time.sleep(min(30 * attempt, 120))
                else:
                    raise RuntimeError(f"Acceptance failed repeatedly: {run_id}")
            if len(set(reports)) != self.repeats:
                raise ValueError(f"Acceptance repetitions must have distinct reports: {label}")
        if not self.acceptance_complete(revision):
            raise RuntimeError("Acceptance does not have all required complete, error-free reports")
        self.state("complete", revision=revision, repetitions=self.repeats)

    def close_studio(self):
        names = {"experts-studio-" + self.name, "experts-studio-" + ALIASES.get(self.name, self.name)}
        rows = subprocess.run(["tmux", "list-panes", "-a", "-F", "#{session_name} #{pane_id}"], capture_output=True, text=True).stdout.splitlines()
        for row in rows:
            name, pane = row.rsplit(" ", 1)
            if name in names:
                subprocess.run(["tmux", "send-keys", "-t", pane, "C-c"], check=True)

    def run(self):
        previous = json.loads(self.state_file.read_text()) if self.state_file.exists() else {}
        if previous.get("stage") == "complete" and previous.get("acceptance_source") == "user":
            print(self.name, "user accepted; no further training or acceptance scheduled", flush=True)
            return
        exported = ROOT / "runs/experts/host/agents" / ("expert-" + self.name) / "harness.json"
        if exported.exists() and (self.case / "questions.json").exists():
            revision = json.loads(exported.read_text())["revision"][:12]
            if self.acceptance_complete(revision):
                self.state("complete", revision=revision, detail="existing three-version acceptance retained")
                self.close_studio()
                return
        self.state("waiting_materials")
        while not (CONTROL / "ready" / (self.name + ".json")).exists() or not (CONTROL / "dispatch.ready").exists():
            time.sleep(15)
        self.train()
        self.accept()
        self.close_studio()


def reconcile_cleanup():
    """Finish only the known old tmux cleanup failure, after validating all nine reports."""
    for path in sorted(CONTROL.glob("*.json")):
        state = json.loads(path.read_text())
        if state.get("stage") != "failed" or state.get("error") != "ValueError: too many values to unpack (expected 2)":
            continue
        worker = Pipeline(state["case"], 3)
        if "ALL ROUNDS DONE" not in (worker.case / "run.out").read_text():
            continue
        harness = ROOT / "runs/experts/host/agents" / ("expert-" + worker.name) / "harness.json"
        revision = json.loads(harness.read_text())["revision"][:12]
        if not all(len(reports_of(worker.case, tag)[0]) == 3 and not reports_of(worker.case, tag)[1]
                   for tag in (revision, "plain", "v0")):
            continue
        worker.close_studio()
        worker.state("complete", revision=revision, repetitions=3,
                     detail="All nine reports verified; recovered the old tmux cleanup failure without rerunning acceptance")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("case", nargs="?")
    parser.add_argument("--port", type=int, help="the case's own Studio port; required for a case missing from PORTS")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--reconcile-cleanup", action="store_true")
    parser.add_argument("--repeats", type=int, default=3)
    args = parser.parse_args()
    if args.reconcile_cleanup:
        reconcile_cleanup()
        return
    if args.all:
        for _, cases in DOMAINS:
            for name, _ in cases:
                state_path = CONTROL / (name + ".json")
                if state_path.exists() and json.loads(state_path.read_text()).get("stage") == "complete":
                    continue
                session = "experts-pipeline-" + name
                if exists(session):
                    continue
                log = CONTROL / "logs" / (name + "-pipeline.log")
                log.parent.mkdir(parents=True, exist_ok=True)
                argv = [sys.executable, str(Path(__file__)), name, "--repeats", str(args.repeats)]
                command = "cd " + shlex.quote(str(REPOSITORY)) + " && exec " + shlex.join(argv) + " >> " + shlex.quote(str(log)) + " 2>&1"
                subprocess.run(["tmux", "new-session", "-d", "-s", session, command], env=ENV, check=True)
                print("managed", name, flush=True)
        return
    if not args.case:
        parser.error("name one case or use --all")
    if not (REPOSITORY / "experts/cases" / args.case / "live.json").is_file():
        parser.error(f"no case directory experts/cases/{args.case}")
    if args.port is None and args.case not in PORTS:
        parser.error("this case has no port in PORTS: give --port")
    pipeline = Pipeline(args.case, args.repeats, args.port)
    try:
        pipeline.run()
    except Exception as exc:
        pipeline.state("failed", error=f"{type(exc).__name__}: {exc}")
        raise


if __name__ == "__main__":
    main()
