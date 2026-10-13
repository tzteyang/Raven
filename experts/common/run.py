"""全自动跑一个案例：对着这个案例自己的 Studio 服务，走完入职、考试、四轮培养（每轮 5 道题）和每轮之后的考试。

  python3 experts/common/run.py <端口> <案例目录> [会话 id] [追加轮次]

不给会话 id 就新建一个；给了就从它停下的地方接着跑（已做完的步骤看记录跳过）。追加轮次写成
"t01,t02,…;t01,…"（分号隔开轮次、逗号隔开题号）：在已有轮次之后照样一轮轮跑这些题，不跳过。每一步的开始、结束和用时写进
<案例目录>/run.log。某一步失败就停下，等人看过再接着跑。分析没有要求改造时这一轮不改造，直接考试进入下一轮。
"""

import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# The Studio token sits in secrets/ beside the checkout (experts/common/run.py -> checkout -> its parent).
TOKEN = Path(__file__).resolve().parents[3] / "secrets" / "experts.token"
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
ROUNDS = [["t01", "t02", "t03", "t04", "t05"], ["t06", "t07", "t08", "t09", "t10"],
          ["t11", "t12", "t13", "t14", "t15"], ["t16", "t17", "t18", "t19", "t20"]]
POLL = 10
TRANSIENT = re.compile(r"HTTP (?:429|50[234])|GATEWAY_CONCURRENCY_FULL|Invalid EOF|timed?\s*out|ConnectionError", re.I)
RECOVERY_STOP = 75


class AnalysisRecoveryError(RuntimeError):
    """A rejected or exhausted recovery must stop the outer pipeline too."""


class Studio:
    def __init__(self, port: int, log: Path):
        self.base, self.log_file = f"http://127.0.0.1:{port}/api/studio/live", log

    def call(self, path: str, body: dict | None = None):
        data = None if body is None else json.dumps(body).encode()
        headers = {"Content-Type": "application/json", "Cookie": f"studio_access={TOKEN.read_text().strip()}"}
        request = urllib.request.Request(self.base + path, data=data, headers=headers)
        for attempt in range(5):
            try:
                with OPENER.open(request, timeout=120) as response:
                    return response.status, json.loads(response.read() or b"{}")
            except urllib.error.HTTPError as exc:
                return exc.code, json.loads(exc.read() or b"{}")
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                time.sleep(10 * (attempt + 1))
        raise RuntimeError(f"the Studio at {self.base} does not answer")

    def log(self, line: str) -> None:
        stamp = time.strftime("%m-%d %H:%M:%S")
        print(f"{stamp} {line}", flush=True)
        with self.log_file.open("a") as f:
            f.write(f"{stamp} {line}\n")

    def state(self, session: str) -> dict:
        status, body = self.call(f"/{session}")
        if status != 200:
            raise RuntimeError(f"no state for {session}: {status} {body}")
        return body

    def recover_analysis(self, session: str, snapshot: dict) -> bool:
        """Ask the framework to restore a transiently failed analysis; its validation is authoritative."""
        if not transient_analysis(snapshot):
            return False
        record = snapshot["record"]
        number = len(record["rounds"])
        attempts = sum(item.get("round") == number for item in record.get("analysis_failures", ()))
        if attempts >= 8:
            raise AnalysisRecoveryError(f"analysis recovery exhausted for round {number}")
        self.log(f"analysis interrupted; restoring its saved evidence in 60s (attempt {attempts + 1}/8)")
        time.sleep(60)
        attached = snapshot.get("attached")
        op, body = ("retry_analysis", {}) if attached else ("resume", {"retry": "analyse"})
        status, answer = self.call(f"/{session}/{op}", body)
        if status != (200 if attached else 202) or answer.get("ok") is False:
            raise AnalysisRecoveryError(f"analysis recovery refused ({status}): {answer.get('error')}")
        for _ in range(60):
            resumed = self.state(session)
            state = resumed.get("state") or {}
            if resumed.get("attached") and state and not state.get("step"):
                try:
                    check_record(resumed)
                except RuntimeError as exc:
                    raise AnalysisRecoveryError(f"analysis recovery failed: {exc}") from exc
                if state.get("failed") or state.get("status") != "running":
                    raise AnalysisRecoveryError(f"analysis recovery failed: {state.get('error') or state}")
                self.log("failed analysis restored; saved answers and judgements will be reused")
                return True
            time.sleep(2)
        raise AnalysisRecoveryError("analysis recovery did not become ready")

    def step(self, session: str, op: str, body: dict | None = None, *, resumes: int = 8) -> dict:
        """Take a step and wait until the session is idle again; the state it ended in. A step that pauses (a curation
        whose model call failed, for example when the shared gateway is full) is called again after a wait to resume it."""
        started = time.time()
        status, answer = self.call(f"/{session}/{op}", body or {})
        self.log(f"{op} posted {status} ok={answer.get('ok')} error={answer.get('error')}")
        if status != 200 or answer.get("ok") is False:
            raise RuntimeError(f"{op} refused: {answer.get('error')}")
        while True:
            snapshot = self.state(session)
            state = snapshot.get("state") or {}
            if snapshot.get("attached") and state and not state.get("step"):
                break
            if not snapshot.get("attached"):
                raise RuntimeError(f"the session's process ended during {op}")
            time.sleep(POLL)
        if op == "analyse" and resumes > 0 and self.recover_analysis(session, snapshot):
            return self.step(session, op, body, resumes=resumes - 1)
        check_record(snapshot)
        if state.get("status") == "paused" and resumes > 0:
            self.log(f"{op} paused ({state.get('error')}); resuming in 90s")
            time.sleep(90)
            return self.step(session, op, body, resumes=resumes - 1)
        if state.get("status") == "paused":
            raise RuntimeError(f"{op} is still paused after its resume attempts")
        if state.get("failed"):
            transient = TRANSIENT.search(str(state.get("error")))
            if op == "exam" and transient and resumes > 0:
                self.log(f"exam assessment interrupted; retrying saved answers in 60s ({resumes} retries left)")
                time.sleep(60)
                return self.step(session, op, body, resumes=resumes - 1)
            raise RuntimeError(f"{op} failed: {state.get('error')}")
        exam = (state.get("exam") or {}).get("current")
        self.log(f"{op} done in {time.time() - started:.0f}s revision={str(state.get('revision'))[:12]}"
                 + (f" exam={exam['failed']}/{exam['judged']}" if op == "exam" and exam else ""))
        return state


def transient_analysis(snapshot: dict) -> bool:
    record = snapshot.get("record") or {}
    error = str(record.get("error", ""))
    stage = record.get("error_step")
    rounds = record.get("rounds") or []
    return bool(
        record.get("status") == "error" and rounds and rounds[-1].get("feedback") is None
        and (stage == "analyse" or (stage is None and error.startswith("analyst: provider error:")))
        and TRANSIENT.search(error)
    )


def check_record(snapshot: dict) -> None:
    """A recorded failure is terminal even when the process has lost its transient `failed` flag."""
    state, record = snapshot.get("state") or {}, snapshot.get("record") or {}
    if record.get("status") == "error" or state.get("status") == "error":
        raise RuntimeError(f"session record is error: {record.get('error') or state.get('error') or 'inspect the record'}")


def exam_complete(record: dict) -> bool:
    """An exam belongs to the pending round, not to the revision's display-score cache."""
    pending = record.get("pending") or {}
    return bool(pending.get("holdout") and pending.get("holdout_signals")) and not pending.get("holdout_assessment")


def cultivate(studio: Studio, session: str, onboarding: str, extra: list[list[str]] | None = None) -> None:
    """Choose each next step from the persisted record, including an interrupted round's tail."""
    start = None
    while True:
        snapshot = studio.state(session)
        if transient_analysis(snapshot) and studio.recover_analysis(session, snapshot):
            continue
        check_record(snapshot)
        if not snapshot.get("attached"):
            raise RuntimeError("the session's process is not attached")
        state, record = snapshot.get("state") or {}, snapshot.get("record")
        if snapshot.get("busy") or state.get("step"):
            time.sleep(POLL)
            continue
        if not state or not isinstance(record, dict) or "rounds" not in record:
            raise RuntimeError("the Studio did not return the state and iteration record")
        done = len(record["rounds"])
        if start is None:
            start = done if extra else 0
        rounds = extra if extra is not None else ROUNDS
        target = start + len(rounds)
        pending = record.get("pending") or {}
        paused = state.get("status") == "paused" or record.get("status") == "paused"
        # A paused initial curation already has initial_curation in its record and therefore
        # reports onboarded=True. It must resume through onboard, not curate or exam.
        if not state.get("onboarded") or (paused and not record["rounds"]):
            studio.step(session, "onboard", {"text": onboarding})
            continue
        if state.get("reviewing") or "review" in pending:
            studio.step(session, "curate")
            continue
        if paused:
            raise RuntimeError("the session is paused without an onboarding or curation to resume")
        if not exam_complete(record):
            studio.step(session, "exam")
            continue
        if done >= target:
            if pending.get("sessions"):
                raise RuntimeError("unanalysed practice sessions remain after the requested rounds")
            studio.log("ALL ROUNDS DONE")
            return
        names = rounds[done - start]
        played = set(pending.get("sessions") or {})
        if played - set(names):
            raise RuntimeError(f"round {done + 1} has unexpected practice sessions: {sorted(played - set(names))}")
        missing = [name for name in names if name not in played]
        if missing:
            studio.log(f"round {done + 1}: {names}")
            studio.step(session, "script", {"names": missing})
        elif state.get("assessor") and not state.get("assessed"):
            studio.step(session, "assess")
        else:
            state = studio.step(session, "analyse")
            outcome = state.get("outcome") or {}
            studio.log(f"round {done + 1} analysed: next={outcome.get('next')} reviewing={state.get('reviewing')}")


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    port, case = int(args[0]), Path(args[1]).resolve()
    studio = Studio(port, case / "run.log")
    if len(args) > 2:
        session = args[2]
    else:
        status, info = studio.call("")
        status, made = studio.call("", {"task": info["task"], "title": f"{case.name} · 自动培养"})
        if status != 201:
            raise RuntimeError(f"no session: {made}")
        session = made["id"]
        studio.log(f"new session {session}")
        (case / "session.txt").write_text(session + "\n")
        time.sleep(15)
    onboarding = next(case.glob("*/onboarding.md")).read_text().strip()
    extra = [part.split(",") for part in args[3].split(";")] if len(args) > 3 else None
    cultivate(studio, session, onboarding, extra)


if __name__ == "__main__":
    try:
        main()
    except AnalysisRecoveryError as exc:
        print(f"STOPPED: {type(exc).__name__}: {exc}", flush=True)
        raise SystemExit(RECOVERY_STOP) from exc
    except Exception as exc:
        print(f"STOPPED: {type(exc).__name__}: {exc}", flush=True)
        raise
