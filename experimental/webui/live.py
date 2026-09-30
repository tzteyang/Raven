"""The Studio's live cultivation sessions, served only when the server is given `--live-config`.

Each session is a run directory under the configuration's `root` (`runs/<id>`, with its employee's working directory
at `workdirs/<id>`), driven by a process of its own (`experimental.webui.session_host`): the server starts it, relays
the page's steps to it over a pipe and stops it. The page reads a session the way it reads a recorded run, the slim
record (`studio.studio_run`) plus what the process reports it is doing, and polls both. The Curator's progress and
where a paused curation stopped come from the run directory (`rundir.curator_progress`, `rundir.pending_stage`).

A session lasts as long as its process: the loop cannot yet rebuild the employee of an existing run directory
(`employ.rehire`), so a session whose process is gone, such as after the server restarted, stays readable, and
resuming it reports why it cannot. The server process never imports the loop: only a session's process does.
"""

import json
import multiprocessing
import re
import secrets
import threading
import time
from dataclasses import dataclass, fields
from functools import lru_cache
from pathlib import Path

from ..iteration.records import runs
from ..scenario import load as load_contract
from .process import redact
from .rundir import curator_progress, pending_stage
from .studio import studio_run

BUNDLED = Path(__file__).resolve().parents[1] / "simulation" / "scenarios" / "travel_agency"
META = "studio.json"
STEPS = ("onboard", "trial", "say", "close", "signal", "assess", "analyse", "curate", "skip", "finish")
SESSION_ID = re.compile(r"live-[0-9]{14}-[0-9a-f]{6}")
# Seconds the server waits for a session's process: a poll gets the last state it had when the process is busy.
POLL_WAIT = 5
STEP_WAIT = 60
STOP_WAIT = 30
TITLE_KEEP = 80
TASK_KEEP = 20_000
NAME_KEEP = 120


@dataclass(frozen=True)
class LiveConfig:
    """What `--live-config` names, a JSON object: the Raven `config` every session hires its employee with (read by
    the session's process only, never shown or recorded), the `root` the sessions are kept under, the `scenario`
    directory whose contract bounds them and whose materials a person may hand over, and the run's settings, named as
    the automated run's command line names them. A relative path is read from the file's own directory."""

    config: Path
    root: Path
    scenario: Path = BUNDLED
    rounds: int = 4
    turns: int = 8
    timeout: float = 600
    curator_model: str | None = None
    curator_effort: str | None = "high"
    curator_calls: int = 48
    curator_queries: int = 72
    analyst_model: str | None = None
    attribution_model: str | None = None
    attribution_calls: int = 8
    attribution_queries: int = 24
    subagent_model: str | None = None
    standard: tuple[str, ...] = ()
    standard_effort: str | None = "low"

    @classmethod
    def load(cls, path: Path) -> "LiveConfig":
        path = Path(path).expanduser().resolve()
        raw = json.loads(path.read_text())
        if not isinstance(raw, dict):
            raise ValueError("the live configuration must be a JSON object")
        unknown = sorted(set(raw) - {item.name for item in fields(cls)})
        if unknown:
            raise ValueError(f"the live configuration has unknown keys: {unknown}")
        missing = sorted({"config", "root"} - set(raw))
        if missing:
            raise ValueError(f"the live configuration needs {missing}")
        values = dict(raw)
        for key in ("config", "root", "scenario"):
            if key in values:
                values[key] = (path.parent / Path(values[key]).expanduser()).resolve()
        if "standard" in values:
            values["standard"] = tuple(values["standard"] or ())
        config = cls(**values)
        config.check()
        return config

    def check(self) -> None:
        if not Path(self.config).is_file():
            raise ValueError("the Raven configuration the live configuration names is not a file")
        counts = ("rounds", "turns", "curator_calls", "curator_queries", "attribution_calls", "attribution_queries")
        for name in counts:
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if isinstance(self.timeout, bool) or not isinstance(self.timeout, (int, float)) or self.timeout <= 0:
            raise ValueError("timeout must be a positive number of seconds")
        load_contract(self.scenario)

    def spec(self, run_dir: Path, workdir: Path, task: str, record: Path | None = None) -> dict:
        """What a session's process is started with (`session_host.Host`)."""
        own = {item.name: getattr(self, item.name) for item in fields(self)}
        return {
            **{key: str(value) if isinstance(value, Path) else value for key, value in own.items()},
            "standard": list(self.standard),
            "run_dir": str(run_dir),
            "workdir": str(workdir),
            "task": task,
            "record": str(record) if record else None,
        }


def _host(connection, spec: dict) -> None:
    # Imported here, in the session's process, so the server's own process never loads the loop.
    from .session_host import main

    main(connection, spec)


def spawn(spec: dict):
    """Start a session's process; it is not a daemon, since the employee starts processes of its own."""
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe()
    process = context.Process(target=_host, args=(child, spec), name=f"studio-{Path(spec['run_dir']).name}")
    process.start()
    child.close()
    return process, parent


class Handle:
    """A session's process and the pipe to it, one message at a time; `last` is the state it last answered with."""

    def __init__(self, process, connection):
        self.process, self.connection = process, connection
        self.lock = threading.Lock()
        self.seq = 0
        self.last: dict | None = None

    @property
    def alive(self) -> bool:
        return self.process.is_alive()

    def ask(self, command: dict, wait: float) -> dict | None:
        """Send `command` and wait up to `wait` seconds for its answer; None when the process is gone or still busy
        by then. A late answer is dropped when the next one is read."""
        with self.lock:
            if not self.process.is_alive():
                return None
            self.seq += 1
            try:
                self.connection.send({**command, "seq": self.seq})
                deadline = time.monotonic() + wait
                while (left := deadline - time.monotonic()) > 0 and self.connection.poll(left):
                    reply = self.connection.recv()
                    if isinstance(reply, dict) and reply.get("seq") == self.seq:
                        self.last = reply.get("state")
                        return reply
            except (EOFError, OSError):
                return None
            return None

    def stop(self, wait: float = STOP_WAIT) -> None:
        """Ask the process to close its employee and end, and end it if it does not within `wait` seconds."""
        self.ask({"op": "shutdown"}, wait)
        self.process.join(wait)
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(5)
        self.connection.close()


class Live:
    """The live sessions of one configuration: the processes this server started, by session id, over the run
    directories of every session kept under the configuration's root. `start` starts a session's process (`spawn`,
    unless a test supplies another)."""

    def __init__(self, config: LiveConfig, start=spawn):
        self.config, self.start = config, start
        self.runs, self.workdirs = Path(config.root) / "runs", Path(config.root) / "workdirs"
        self.runs.mkdir(parents=True, exist_ok=True)
        self.workdirs.mkdir(parents=True, exist_ok=True)
        self.contract = load_contract(config.scenario)
        self.handles: dict[str, Handle] = {}
        self.guard = threading.Lock()

    def directory(self, session: str) -> Path | None:
        """The run directory of a session this configuration keeps, only for a well-formed id."""
        if not isinstance(session, str) or not SESSION_ID.fullmatch(session):
            return None
        path = self.runs / session
        return path if (path / META).is_file() else None

    def materials(self) -> list[dict]:
        """The materials a person may hand over (the contract's `handed`, those the partner may receive), each as the
        handover it becomes (its kind and its files as `uploads/<name>/...`) with where it came from when the party did
        not simply give it."""
        out = []
        for name in self.contract.handed:
            material = self.contract.materials[name]
            files = sorted(
                f"uploads/{name}/{path.relative_to(material.path).as_posix()}"
                for path in material.path.rglob("*")
                if path.is_file()
            )
            origin = self.contract.provenance.materials.get(name)
            out.append(
                {
                    "name": name,
                    "kind": material.kind,
                    "files": files,
                    **({"origin": origin.model_dump(mode="json")} if origin else {}),
                }
            )
        return out

    def info(self) -> dict:
        """What the page starts a session from, and every session kept."""
        config = self.config
        return {
            "enabled": True,
            "scenario": self.contract.root.name,
            "task": self.contract.situation.profile,
            "materials": self.materials(),
            "settings": {
                "rounds": config.rounds,
                "turns": config.turns,
                "curator": config.curator_model,
                "analyst": config.analyst_model or config.curator_model,
                "standard": bool(config.standard),
            },
            "sessions": self.sessions(),
        }

    def sessions(self) -> list[dict]:
        found = [path.name for path in self.runs.iterdir() if self.directory(path.name) is not None]
        return sorted((self.summary(session) for session in found), key=lambda row: row["created"], reverse=True)

    def _meta(self, directory: Path) -> dict:
        try:
            value = json.loads((directory / META).read_text())
        except (OSError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _record(directory: Path) -> Path | None:
        found = runs(directory)
        return found[-1] if found else None

    def summary(self, session: str) -> dict:
        directory = self.runs / session
        meta, record, handle = self._meta(directory), self._record(directory), self.handles.get(session)
        status = None
        if record is not None:
            stat = record.stat()
            status = _status(str(record), stat.st_mtime_ns, stat.st_size)
        return {
            "id": session,
            "title": meta.get("title") or session,
            "task": meta.get("task", ""),
            "created": meta.get("created", 0),
            "archived": meta.get("archived"),
            "run": f"{session}/{record.stem}" if record is not None else None,
            "status": status,
            "models": _models(directory),
            "attached": bool(handle and handle.alive),
            "step": (handle.last or {}).get("step") if handle and handle.alive else None,
        }

    def create(self, body: dict) -> tuple[int, dict]:
        task = body.get("task")
        title = body.get("title")
        if not isinstance(task, str) or not task.strip() or len(task) > TASK_KEEP:
            return 400, {"error": f"a session needs its task, at most {TASK_KEEP} characters"}
        if title is not None and (not isinstance(title, str) or len(title) > TITLE_KEEP):
            return 400, {"error": f"a title is at most {TITLE_KEEP} characters"}
        session = f"live-{time.strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(3)}"
        directory = self.runs / session
        directory.mkdir()
        meta = {"id": session, "title": (title or "").strip() or None, "task": task.strip(), "created": time.time()}
        (directory / META).write_text(json.dumps(meta, ensure_ascii=False, indent=2))
        self._launch(session, self.config.spec(directory, self.workdirs / session, meta["task"]))
        return 201, self.summary(session)

    def _launch(self, session: str, spec: dict) -> None:
        process, connection = self.start(spec)
        with self.guard:
            self.handles[session] = Handle(process, connection)

    def resume(self, session: str) -> tuple[int, dict]:
        """Start a process on a kept session whose process is gone; it rehires the employee and resumes the record,
        and says on the page why when it cannot."""
        directory = self.directory(session)
        if directory is None:
            return 404, {"error": "no such session"}
        handle = self.handles.get(session)
        if handle is not None and handle.alive:
            return 409, {"error": "the session is already running"}
        meta, record = self._meta(directory), self._record(directory)
        if record is None:
            return 409, {"error": "the session never opened its record, so there is nothing to resume"}
        if meta.get("archived"):
            return 409, {"error": "the session is archived"}
        stat = record.stat()
        if _status(str(record), stat.st_mtime_ns, stat.st_size) in ("finished", "error"):
            return 409, {"error": "the session's run has ended"}
        self._launch(session, self.config.spec(directory, self.workdirs / session, meta.get("task", ""), record))
        return 202, self.summary(session)

    def snapshot(self, session: str, stamp: str | None = None) -> dict | None:
        """A session as the page polls it: its summary, the state its process reports (the last one it had while it
        is busy), the Curator's progress, and the slim record with its stamp, the record only when the stamp is not
        `stamp`."""
        directory = self.directory(session)
        if directory is None:
            return None
        handle, state, busy = self.handles.get(session), None, False
        if handle is not None:
            reply = handle.ask({"op": "state"}, POLL_WAIT)
            state = reply["state"] if reply else handle.last
            busy = reply is None and handle.alive
        record = self._record(directory)
        now = _stamp(directory, record)
        body = {
            **self.summary(session),
            "state": state,
            "busy": busy,
            "stamp": now,
            "progress": redact({"curation": curator_progress(directory), "paused": pending_stage(directory)}),
        }
        if record is not None and now != stamp:
            body["record"] = studio_run(record)
        return body

    def step(self, session: str, op: str, body: dict) -> tuple[int, dict]:
        """Relay one of the page's steps (`STEPS`) to the session's process: 200 with its state when the step was
        taken or started, 409 with the reason when the session refused it."""
        if op == "resume":
            return self.resume(session)
        if op == "archive":
            return self.archive(session, body)
        directory = self.directory(session)
        if directory is None:
            return 404, {"error": "no such session"}
        if op not in STEPS:
            return 404, {"error": f"unknown step: {op}"}
        handle = self.handles.get(session)
        if handle is None or not handle.alive:
            return 410, {"error": "the session's process has ended"}
        reply = handle.ask({**body, "op": op}, STEP_WAIT)
        if reply is None:
            return 503, {"error": "the session did not answer in time; its state will show whether the step started"}
        if reply.get("state", {}).get("ended"):
            handle.process.join(STOP_WAIT)
        return (200 if reply.get("ok") else 409), redact({key: value for key, value in reply.items() if key != "seq"})

    def archive(self, session: str, body: dict) -> tuple[int, dict]:
        """Keep the session under a name: its run is finished first when its process can still finish it."""
        directory = self.directory(session)
        if directory is None:
            return 404, {"error": "no such session"}
        name, version = body.get("name"), body.get("version")
        if not isinstance(name, str) or not name.strip() or len(name) > NAME_KEEP:
            return 400, {"error": f"an archive needs a name of at most {NAME_KEEP} characters"}
        handle = self.handles.get(session)
        if handle is not None and handle.alive:
            status, reply = self.step(session, "finish", {"reason": f"archived as {name.strip()}"})
            if status != 200:
                return status, reply
        meta = self._meta(directory)
        meta["archived"] = {"name": name.strip(), "version": version if isinstance(version, str) else None}
        (directory / META).write_text(json.dumps(meta, ensure_ascii=False, indent=2))
        return 200, self.summary(session)

    def close(self) -> None:
        """Stop every session's process this server started."""
        with self.guard:
            handles, self.handles = list(self.handles.values()), {}
        threads = [threading.Thread(target=handle.stop) for handle in handles if handle.alive]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()


def _models(directory: Path) -> dict[str, str]:
    """The run's model of each role, from the settings its process wrote."""
    try:
        settings = json.loads((directory / "settings.json").read_text())
    except (OSError, ValueError):
        return {}
    models = settings.get("models") if isinstance(settings, dict) else None
    return {role: name for role, name in models.items() if isinstance(name, str)} if isinstance(models, dict) else {}


@lru_cache(maxsize=256)
def _status(path: str, mtime_ns: int, size: int) -> str | None:
    """A record's status, read once per version of the file."""
    try:
        value = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None
    return value.get("status") if isinstance(value, dict) else None


def _stamp(directory: Path, record: Path | None) -> str:
    """What changes when the record the page reads of a session's directory does, or the settings or standard beside
    it. The compartment log grows with every guarded model call, so it is read again only with the record, which every
    step saves when it ends."""
    parts = []
    for path in (record, directory / "standard.json", directory / "settings.json"):
        try:
            stat = path.stat() if path is not None else None
        except OSError:
            stat = None
        parts.append(f"{stat.st_mtime_ns}.{stat.st_size}" if stat else "-")
    return ":".join(parts)
