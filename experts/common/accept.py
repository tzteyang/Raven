"""验收导出的 agent：用宿主 Raven 派活的同一套机制（AcpAgentBackend，宿主花名册里 kind=acp 的 subagent 就走它），
把考试题一道道派给 agents 目录里的 expert-<案例名>，每道题一个新的工作目录（放好随题文件），收它的回复和它在工作
目录里新写的文本文件，用 Studio 里同一个评审判，结果写进 <案例目录>/accept-<agent 的版本>-<时间>.json（版本 plain 是没培养过的 plain Raven）。评审判的是 agent 最后一次工具调用之后
说的话（Raven 的 closing_text，即回复本身，和 Studio 判的口径一样）；宿主拿到的整轮文字（含调用工具前的过程提示）一并存档。

  uv run python experts/common/accept.py <案例目录> <宿主 RAVEN_HOME> [题号…] [--run-id <本次验收标识>] [--no-wait-for-lock]

宿主 RAVEN_HOME 里要有 config.json（宿主的配置，agent 从它借 providers）和 agents/expert-<案例名>/。不给题号就派全部
考试题（同规则 x、新规则 y）。一次只派一道，派完再派下一道。

同一个 --run-id 从 accept-runs/<标识>/partial.json 恢复；不用这个参数时生成并打印一个新标识。
答卷在请求评审之前落盘，评审失败后只重判这份答卷；已判完的题不再执行，也不按分数重测。
每次重复验收须用不同标识，工作目录、ACP 会话和注册表也分别隔离。中断时未收到完整答卷的派活
保留为带错误的真实产出，不自动重新派活。只有全部 20 道考试题判完才写 accept-*.json；显式题号
的子集诊断写在自己的 run 目录，不进入完整验收汇总。原始答卷、交付文件、失败和评审调用记录保留。
命令行默认等待同标识的进程交还锁，取得锁后重新校验绑定；完整报告只读返回，不重复派题或评审。
等待和取得锁写入进程日志；--no-wait-for-lock 会立即拒绝正在使用的标识。
"""

import argparse
import asyncio
import base64
import fcntl
import hashlib
import json
import os
import re
import shlex
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[1]
GTM = REPOSITORY.parent  # the workspace that holds runs/ beside the checkout
sys.path.insert(0, str(REPOSITORY))
sys.path.insert(0, str(HERE))

from examiner import Case, Examiner, Scoring, judge_settings, judging  # noqa: E402
from officetext import BINARY, render  # noqa: E402

from raven.acp_client.acp_agent import AcpAgentBackend, AcpEmptyTurnError  # noqa: E402
from raven.acp_client.pool import AcpConnectionPool  # noqa: E402
from raven.acp_client.protocol import AcpError  # noqa: E402
from raven.agent.subagent.instances import InstanceRegistry  # noqa: E402
from raven.agent.subagent.mcp_grant import McpDispatchError  # noqa: E402
from raven.config.loader import load_config  # noqa: E402
from raven.contracts.subagent_backend import SubagentActionAbortedError, SubagentNoAnswerError  # noqa: E402
from raven.providers.factory import make_lazy_provider  # noqa: E402

TEXT = {".md", ".txt", ".csv", ".json", ".py", ".sql", ".html"}


class Backend(AcpAgentBackend):
    """The host's ACP backend, keeping the last turn's collector so the reply proper can be read after `run`."""

    last = None
    on_record = None

    def _record(self, span, collector, **kwargs):
        self.last = collector
        if self.on_record is not None:
            self.on_record(collector)
        return super()._record(span, collector, **kwargs)


def written(workspace: Path, given: set[str]) -> str:
    """The text files the agent left in the turn's working directory beside the ones it was given."""
    parts = []
    for path in sorted(workspace.rglob("*")):
        relative = str(path.relative_to(workspace))
        if not path.is_file() or relative in given or relative.startswith("."):
            continue
        if path.suffix.lower() in TEXT:
            parts.append(f"【交付文件 {relative}】\n{path.read_text(errors='replace')[:40000]}")
        elif path.suffix.lower() in (".docx", ".xlsx"):
            parts.append(f"【交付文件 {relative}（文字版）】\n{render(path.name, path.read_bytes())[:40000]}")
    return "\n\n".join(parts)


def atomic_json(path: Path, value) -> None:
    """A crash leaves either the previous complete file or the next one."""
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=1)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def run_lock(directory: Path, *, wait: bool = False):
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "run.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            if not wait:
                raise RuntimeError(f"this acceptance run is already active: {directory.name}") from exc
            print(f"WAITING_FOR_RUN {directory.name} pid={os.getpid()}", flush=True)
            fcntl.flock(lock, fcntl.LOCK_EX)
            print(f"JOINED_RUN {directory.name} pid={os.getpid()}", flush=True)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inputs(case: Case, host: Path, names: list[str]) -> dict:
    """Only evaluation inputs and the exported artifact, never changing logs/config credentials."""
    files = {case.root / "questions.json", case.scenario / "scenario.json"}
    files.update(case.root / "rules" / f"{case.bank[name]['rules']}.md" for name in names)
    if (case.root / "measure.py").exists():
        files.add(case.root / "measure.py")
    folder = host / "agents" / f"expert-{case.root.name}"
    harness = folder / "harness.json"
    revision = json.loads(harness.read_text())["revision"]
    return {"case": str(case.root), "host": str(host), "revision": revision, "names": names,
            "judge": dict(zip(("model", "effort"), judge_settings(case.root))),
            "files": {str(p.relative_to(case.root)): digest(p) for p in sorted(files)},
            "harness": digest(harness), "agent_entry": digest(folder / "run.py")}


def verdicts(value: list, criteria: list[dict]) -> Scoring:
    """Check completeness/shape only; correctness remains the model judge's decision."""
    scoring = Scoring.model_validate({"items": value})
    ids = [c["id"] for c in criteria]
    if sorted(v.id for v in scoring.items) != sorted(ids) or len(set(ids)) != len(ids):
        raise ValueError("verdicts do not contain each criterion exactly once")
    if any(v.count != len(v.errors) or (not v.applicable and v.count) for v in scoring.items):
        raise ValueError("verdict counts disagree with the judge's listed errors")
    return scoring


class Run:
    """One frozen evaluation, with durable answers before any call to the judge."""

    def __init__(self, case: Case, host: Path, names: list[str], run_id: str):
        self.case, self.host, self.names, self.run_id = case, host, names, run_id
        self.directory = case.root / "accept-runs" / run_id
        self.path = self.directory / "partial.json"
        identity = inputs(case, host, names)
        exam = sorted(n for n, q in case.bank.items() if q["group"] in ("same", "new"))
        self.full = sorted(names) == exam and len(exam) == 20
        if self.path.exists():
            self.data = json.loads(self.path.read_text())
            if self.data.get("version") != 1 or self.data.get("inputs") != identity:
                raise ValueError("run-id inputs changed (questions/rules/criteria/measure/agent/host); use a new run-id")
            if self.data.get("run_id") != run_id:
                raise ValueError("checkpoint run-id mismatch")
        else:
            scratch = Path(tempfile.mkdtemp(prefix=f"accept-{case.root.name}-{run_id[:32]}-"))
            revision = identity["revision"][:12]
            if not re.fullmatch(r"[A-Za-z0-9_-]+", revision):
                raise ValueError("unsafe agent revision")
            suffix = hashlib.sha256(run_id.encode()).hexdigest()[:10]
            filename = f"accept-{revision}-{time.strftime('%m%d-%H%M%S')}-{suffix}.json"
            report = case.root / filename if self.full else self.directory / "subset.json"
            self.data = {"version": 1, "run_id": run_id, "inputs": identity, "scratch": str(scratch),
                         "report": str(report), "status": "running", "items": {}, "events": []}
            self.event("created")
        if set(self.data["items"]) - set(names):
            raise ValueError("checkpoint contains unrequested questions")

    def save(self):
        atomic_json(self.path, self.data)

    def event(self, event: str, **fields):
        self.data["events"].append({"time": time.time(), "event": event, **fields})
        self.save()

    def rows(self) -> list[dict]:
        if set(self.data["items"]) != set(self.names):
            raise ValueError("not every requested question has a result")
        rows = []
        for name in self.names:
            item = self.data["items"][name]
            if item.get("stage") != "scored":
                raise ValueError(f"{name}: no complete model verdict")
            row = item["result"]
            if row["name"] != name or row["group"] != self.case.bank[name]["group"]:
                raise ValueError(f"{name}: result identity mismatch")
            scoring = verdicts(row["verdicts"], self.case.criteria)
            if row["failed"] != [v.id for v in scoring.items if v.applicable and v.count] or row["judged"] != [
                v.id for v in scoring.items if v.applicable
            ]:
                raise ValueError(f"{name}: summaries differ from the stored model verdict")
            rows.append(row)
        return rows

    def publish(self) -> tuple[Path, list[dict]]:
        results = self.rows()
        if self.full and (len(results) != 20 or any(sum(r["group"] == g for r in results) != 10 for g in ("same", "new"))):
            raise ValueError("a full acceptance report requires exactly 10 same-rule and 10 new-rule answers")
        out = Path(self.data["report"])
        if out.exists():
            if json.loads(out.read_text()) != results:
                raise ValueError(f"existing report differs from checkpoint: {out}")
        elif self.data["status"] == "complete":
            raise ValueError(f"completed acceptance report is missing: {out}")
        else:
            atomic_json(out, results)
        if self.data["status"] != "complete":
            self.data["status"] = "complete"
            self.event("complete", report=str(out), full=self.full)
        return out, results


def error_text(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"


def transport_error_reply(reply: str) -> str | None:
    """ACP may expose a failed provider turn as text; it is transport evidence, not a scored answer."""
    if reply.lstrip().startswith("turn_failed APIError:"):
        return "ProviderTransportError: " + reply[:800]
    return None


def employee_transport(run: Run) -> dict:
    """The employee's route as the exported agent names it, unless runs/experts/control/employee-transport/current.json
    records an operator's override (a provider swapped behind the same model name)."""
    path = GTM / "runs/experts/control/employee-transport/current.json"
    if path.exists():
        return json.loads(path.read_text())
    agent = run.host / "agents" / f"expert-{run.case.root.name}" / "config.json"
    defaults = json.loads(agent.read_text())["agents"]["defaults"]
    return {"provider": defaults.get("provider") or "auto", "model": defaults["model"]}


class AuditedProvider:
    """Record each call inside Examiner's existing bounded retry loop, without changing its judgments."""

    def __init__(self, provider, run: Run):
        self.provider, self.run, self.question = provider, run, None

    def __getattr__(self, name):
        return getattr(self.provider, name)

    async def chat(self, *args, **kwargs):
        call = uuid.uuid4().hex
        self.run.event("judge_call_started", name=self.question, call=call)
        try:
            response = await self.provider.chat(*args, **kwargs)
        except BaseException as exc:
            self.run.event("judge_call_error", name=self.question, call=call, error=error_text(exc))
            raise
        self.run.event("judge_call_response", name=self.question, call=call,
                       finish_reason=response.finish_reason, truncated=response.truncated,
                       error_category=response.error_classification.category if response.error_classification else None,
                       content=response.content,
                       submissions=[{"name": c.name, "arguments": c.arguments} for c in response.tool_calls])
        return response


DISPATCH_ERRORS = (AcpError, AcpEmptyTurnError, SubagentNoAnswerError, SubagentActionAbortedError, McpDispatchError,
                   TimeoutError, ConnectionError)


async def dispatch(run: Run, backend, question: dict, item: dict) -> None:
    name = question["name"]
    dispatch_name = name + ("-" + item["dispatch_suffix"] if item.get("dispatch_suffix") else "")
    workspace = Path(run.data["scratch"]) / dispatch_name
    workspace.mkdir(parents=True, exist_ok=True)
    for file, text in question["files"].items():
        target = workspace / file
        if not target.resolve().is_relative_to(workspace.resolve()):
            raise ValueError(f"question file escapes workspace: {file}")
        target.parent.mkdir(parents=True, exist_ok=True)
        if text.startswith(BINARY):
            target.write_bytes(base64.b64decode(text[len(BINARY):]))
        else:
            target.write_text(text)
    started = time.time()
    item.update({"stage": "dispatching", "started": started})
    run.event("dispatch_started", name=name)
    backend.last = None

    def collected(collector):
        item["collected"] = {"reply": collector.closing_text, "full_reply": collector.text}
        run.event("dispatch_reply_recorded", name=name)

    async def delta(text):
        with (run.directory / f"{name}-stream.txt").open("a", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())

    backend.on_record = collected
    error = None
    try:
        full = await backend.run(question["text"], task_id=dispatch_name, workspace=workspace, executor=None,
                                 session_key=f"accept:{run.case.root.name}:{run.run_id}:{dispatch_name}", on_delta=delta)
    except DISPATCH_ERRORS as exc:
        full = backend.last.text if backend.last is not None else ""
        error = error_text(exc)
    except BaseException as exc:
        if not isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
            item["fatal"] = error_text(exc)
        run.event("dispatch_interrupted", name=name, error=error_text(exc))
        raise
    finally:
        backend.on_record = None
    reply = backend.last.closing_text if backend.last is not None else full
    error = error or transport_error_reply(reply)
    item.update({"stage": "answered", "answer": {"name": name, "group": question["group"],
                 "seconds": round(time.time() - started), "error": error, "reply": reply, "full_reply": full,
                 "transport": employee_transport(run)}})
    run.event("answer_saved", name=name, error=error)


def recover_dispatch(run: Run, question: dict, item: dict) -> None:
    """Uncertain/incomplete dispatches stay in the sample; never rerun them hoping for a better answer."""
    if item.get("fatal"):
        raise RuntimeError(f"{question['name']}: previous unexpected dispatch error needs repair: {item['fatal']}")
    name = question["name"]
    stream = run.directory / f"{name}-stream.txt"
    collected = item.get("collected", {})
    item.update({"stage": "answered", "answer": {"name": name, "group": question["group"],
                 "seconds": round(time.time() - item["started"]),
                 "error": "InterruptedError: dispatch ended before its result was saved; not redispatched",
                 "reply": collected.get("reply", ""),
                 "full_reply": collected.get("full_reply", stream.read_text() if stream.exists() else "")}})
    run.event("interrupted_answer_preserved", name=name)


async def evaluate(run: Run, backend, examiner, audit=None) -> tuple[Path, list[dict]]:
    if run.data["status"] == "complete":
        return run.publish()
    for name in run.names:
        question = run.case.bank[name]
        item = run.data["items"].setdefault(name, {"stage": "pending"})
        if item["stage"] == "scored":
            verdicts(item["result"]["verdicts"], run.case.criteria)
            continue
        if item["stage"] == "pending":
            await dispatch(run, backend, question, item)
        elif item["stage"] == "dispatching":
            recover_dispatch(run, question, item)
        if item["stage"] == "answered":
            dispatch_name = name + ("-" + item["dispatch_suffix"] if item.get("dispatch_suffix") else "")
            workspace = Path(run.data["scratch"]) / dispatch_name
            item["answer"]["product"] = "\n\n".join(part for part in (
                item["answer"]["reply"], written(workspace, set(question["files"]))
            ) if part)
            item["stage"] = "judging"
            run.event("product_saved", name=name)
        if item["stage"] != "judging":
            raise ValueError(f"{name}: unknown checkpoint stage {item['stage']}")
        if audit is not None:
            audit.question = name
        run.event("judge_started", name=name)
        try:
            scoring, loose = await examiner.judge(question, item["answer"]["product"])
            stored = [v.model_dump() for v in scoring.items]
            verdicts(stored, run.case.criteria)
        except BaseException as exc:
            run.event("judge_failed", name=name, error=error_text(exc))
            raise
        answer = item["answer"]
        failed = [v.id for v in scoring.items if v.applicable and v.count]
        judged = [v.id for v in scoring.items if v.applicable]
        item["result"] = {k: v for k, v in answer.items() if k != "reply"} | {
            "failed": failed, "judged": judged, "verdicts": stored, "loose": loose}
        item["stage"] = "scored"
        run.event("scored", name=name)
        print(f"{name}: {len(failed)}/{len(judged)} failed in {answer['seconds']}s {failed}"
              f"{' ERROR ' + answer['error'] if answer['error'] else ''}", flush=True)
    return run.publish()


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", type=Path)
    parser.add_argument("host", type=Path)
    parser.add_argument("names", nargs="*")
    parser.add_argument("--run-id")
    parser.add_argument("--wait-for-lock", action=argparse.BooleanOptionalAction, default=True,
                        help="wait for an active run-id, then validate and reuse its saved progress (default)")
    args = parser.parse_intermixed_args(argv)
    args.run_id = args.run_id or f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:10]}"
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,119}", args.run_id):
        parser.error("--run-id must be 1–120 ASCII letters/digits/dots/underscores/hyphens, starting with a letter/digit")
    return args


async def main(argv=None) -> None:
    args = arguments(argv)
    case, host = args.case.resolve(), args.host.resolve()
    if not (case / "live.json").is_file():
        raise ValueError(f"acceptance case requires live.json: {case}")
    with run_lock(case / "accept-runs" / args.run_id, wait=args.wait_for_lock):
        live = json.loads((case / "live.json").read_text())
        spec = Case(case / live["scenario"])
        exams = sorted(n for n, q in spec.bank.items() if q["group"] in ("same", "new"))
        names = sorted(args.names) if args.names else exams
        if len(names) != len(set(names)) or any(n not in spec.bank or not re.fullmatch(r"[A-Za-z0-9_-]+", n) for n in names):
            raise ValueError("question names must be known, unique safe identifiers")
        if not args.names and (len(exams) != 20 or any(sum(spec.bank[n]["group"] == g for n in exams) != 10 for g in ("same", "new"))):
            raise ValueError("default acceptance requires exactly 10 same-rule and 10 new-rule questions")
        run = Run(spec, host, names, args.run_id)
        print(f"RUN_ID {args.run_id} checkpoint={run.path}", flush=True)
        if run.data["status"] == "complete":
            out, results = run.publish()
        else:
            config = judging(load_config(host / "config.json"), case)
            audit = AuditedProvider(make_lazy_provider(config), run)
            examiner = Examiner(audit, spec.scenario)
            folder = host / "agents" / f"expert-{case.name}"
            env = {"RAVEN_HOME": str(host), "NO_PROXY": os.environ.get("NO_PROXY", ""), "no_proxy": os.environ.get("no_proxy", "")}
            backend = Backend(
                name=f"expert-{case.name}", command=shlex.join([sys.executable, str(folder / "run.py")]), cwd=str(folder),
                env=env, ready_timeout_ms=180000, max_output_chars=60000, pool=AcpConnectionPool(),
                registry=InstanceRegistry(run.directory / "instances.json"),
            )
            try:
                out, results = await evaluate(run, backend, examiner, audit)
            except BaseException as exc:
                run.event("run_failed", error=error_text(exc))
                raise
            finally:
                await backend.pool.close_all()
    by = {}
    for row in results:
        f, j = by.get(row["group"], (0, 0))
        by[row["group"]] = (f + len(row["failed"]), j + len(row["judged"]))
    print("ACCEPT" if run.full else "ACCEPT_SUBSET", json.dumps({g: f"{f}/{j}" for g, (f, j) in by.items()}), "errors:",
          sum(1 for row in results if row["error"]), "->", out, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
