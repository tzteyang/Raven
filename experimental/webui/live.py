"""The Studio's live cultivation sessions, served only when the server is given `--live-config`.

Each session is a run directory under the configuration's `root` (`runs/<id>`, with its employee's working directory
at `workdirs/<id>`), driven by a process of its own (`experimental.webui.session_host`): the server starts it, relays
the page's steps to it over a pipe and stops it. The page reads a session the way it reads a recorded run, the slim
record (`studio.studio_run`) plus what the process reports it is doing, and polls both. The Curator's progress and
where a paused curation stopped come from the run directory (`rundir.curator_progress`, `rundir.pending_stage`).

A session whose process is gone, such as after the server restarted, stays readable and can be resumed: its process
rehires the employee on the deployment the session saved (`session_host`), which an employee that delegates does not
have once its harness changed, so resuming such a session reports why it cannot. A session may start from a saved
deployment instead of the plain baseline: one the configuration names (`versions`) or an archived session's. The
server process never imports the loop: only a session's process does.
"""

import json
import multiprocessing
import os
import re
import secrets
import shutil
import threading
import time
from contextlib import nullcontext
from dataclasses import dataclass, field, fields
from functools import lru_cache
from pathlib import Path

from .. import model_roles
from ..iteration.records import runs
from ..scenario import load as load_contract
from ..scenario.contract import SKILL_FILE as SKILL
from . import exporting
from .process import redact
from .rundir import curator_progress, pending_stage
from .studio import studio_run

BUNDLED = Path(__file__).resolve().parents[1] / "simulation" / "scenarios" / "travel_agency"
# The model roles of a live session: a person on the page is the counterpart and every conversant, and nothing is
# collected before onboarding.
MODEL_ROLES = (
    "curator",
    "attribution",
    "analyst",
    "assessor",
    "rubric_builder",
    "meta_reviewer",
    "sub-harness",
    "collector",
)
META = "studio.json"
STEPS = (
    "onboard",
    "trial",
    "script",
    "exam",
    "say",
    "close",
    "question",
    "propose",
    "adopt",
    "inquire",
    "answer",
    "signal",
    "assess",
    "analyse",
    "curate",
    "revert",
    "skip",
    "finish",
)
SESSION_ID = re.compile(r"live-[0-9]{14}-[0-9a-f]{6}")
# Seconds the server waits for a session's process: a poll gets the last state it had when the process is busy.
POLL_WAIT = 5
STEP_WAIT = 60
STOP_WAIT = 30
TITLE_KEEP = 80
# A scenario built on the page: its name, never a word the repository holds, since the Curator may not read a file that
# names its scenario (`experimental.automation.employee.withheld`), and the limits of what it is built from.
BUILT = re.compile(r"scn-[0-9a-f]{8}")
BUILT_SCRIPTS, MATERIAL = "scripts.json", "materials"
UPLOADED = frozenset({".md", ".txt", ".csv"})
PROFILE_KEEP, LINE_KEEP, CHECK_KEEP, LINES_KEPT, FILES_KEPT = 8_000, 4_000, 1_000, 40, 30
PERSONA = (
    "The person who hands out this work and judges it. They write requests in their own words, the way the job "
    "description reads, and say plainly when a reply is wrong.\n"
)
TASK_KEEP = 20_000
NAME_KEEP = 120
SCRIPT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
MANUAL = re.compile(r"trial-[0-9]+")
FACTORY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
DEPLOYMENT = "deployment.json"


def _text_of(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def scripts(path) -> list[dict]:
    """The scripts a configuration names (`LiveConfig.scripts`): a JSON list of `{"name", "title", "exam", "steps"}`,
    each step `{"text", "files"}`, the files written (by their path in the working directory) before the text is said.
    A practice script plays as a trial of the round, an exam script only as a held-out one."""
    if not path:
        return []
    raw = json.loads(Path(path).read_text())
    if not isinstance(raw, list):
        raise ValueError("the scripts are a JSON list")
    out, seen = [], set()
    for script in raw:
        name = script.get("name") if isinstance(script, dict) else None
        if not isinstance(name, str) or not SCRIPT.fullmatch(name) or MANUAL.fullmatch(name) or name in seen:
            raise ValueError(f"a script needs its own name of letters, digits, '.', '_' or '-': {name!r}")
        seen.add(name)
        steps = script.get("steps")
        if not isinstance(steps, list) or not steps:
            raise ValueError(f"script {name} has no steps")
        for step in steps:
            text, files = (step.get("text"), step.get("files", {})) if isinstance(step, dict) else (None, None)
            if not isinstance(text, str) or not text.strip() or not isinstance(files, dict):
                raise ValueError(f"every step of script {name} says a text and names its files")
            for file, content in files.items():
                parts = Path(file).parts if isinstance(file, str) else ("..",)
                if not parts or Path(file).is_absolute() or ".." in parts or not isinstance(content, str):
                    raise ValueError(f"script {name} writes a file outside the working directory: {file!r}")
        title = script.get("title")
        out.append(
            {
                "name": name,
                "title": title if isinstance(title, str) and title.strip() else name,
                "exam": script.get("exam") is True,
                "steps": [{"text": step["text"], "files": dict(step.get("files", {}))} for step in steps],
            }
        )
    return out


@lru_cache(maxsize=64)
def _saved_task(path: str, mtime_ns: int, size: int) -> str | None:
    """The task text of a saved deployment, read once per version of the file."""
    try:
        value = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None
    task = value.get("task") if isinstance(value, dict) else None
    return task.get("text") if isinstance(task, dict) and isinstance(task.get("text"), str) else None


def saved_task(path: Path) -> str | None:
    try:
        stat = Path(path).stat()
    except OSError:
        return None
    return _saved_task(str(path), stat.st_mtime_ns, stat.st_size)


@dataclass(frozen=True)
class LiveConfig:
    """What `--live-config` names, a JSON object: the Raven `config` every session hires its employee with (read by
    the session's process only, never shown or recorded), the `root` the sessions are kept under, the `scenario`
    directory whose contract bounds them and whose materials a person may hand over, and the run's settings, named as
    the automated run's command line names them; `models` and `efforts` map a model role of `MODEL_ROLES` to its model and
    effort (`experimental.model_roles`), a role not named running on the partner's. A relative path is read from the
    file's own directory."""

    config: Path
    root: Path
    scenario: Path = BUNDLED
    rounds: int = 4
    turns: int = 8
    timeout: float = 600
    models: dict[str, str] = field(default_factory=dict)
    efforts: dict[str, str] = field(default_factory=dict)
    curator_calls: int = 48
    curator_queries: int = 72
    attribution_calls: int = 8
    attribution_queries: int = 24
    standard: tuple[str, ...] = ()
    evaluation_memory: Path | None = None
    experience_memory: Path | None = None
    experience_scope: str = "local"
    experience_migrate: bool = False
    delegation: bool = True
    scripts: Path | None = None
    assessor: str | None = None
    versions: dict[str, Path] = field(default_factory=dict)
    information: str | None = None
    title: str | None = None

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
        for key in ("config", "root", "scenario", "evaluation_memory", "experience_memory", "scripts"):
            if values.get(key) is not None:
                values[key] = (path.parent / Path(values[key]).expanduser()).resolve()
        if isinstance(values.get("versions"), dict):
            values["versions"] = {
                name: (path.parent / Path(file).expanduser()).resolve() for name, file in values["versions"].items()
            }
        if isinstance(values.get("assessor"), str) and ":" in values["assessor"]:
            file, _, factory = values["assessor"].rpartition(":")
            values["assessor"] = f"{(path.parent / Path(file).expanduser()).resolve()}:{factory}"
        if "standard" in values:
            values["standard"] = tuple(values["standard"] or ())
        config = cls(**values)
        config.check()
        return config

    def check(self) -> None:
        if not isinstance(self.experience_scope, str) or not self.experience_scope.strip():
            raise ValueError("experience_scope must name an explicit access scope")
        if not isinstance(self.experience_migrate, bool):
            raise ValueError("experience_migrate must be a boolean")
        if not Path(self.config).is_file():
            raise ValueError("the Raven configuration the live configuration names is not a file")
        counts = ("rounds", "turns", "curator_calls", "curator_queries", "attribution_calls", "attribution_queries")
        for name in counts:
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if isinstance(self.timeout, bool) or not isinstance(self.timeout, (int, float)) or self.timeout <= 0:
            raise ValueError("timeout must be a positive number of seconds")
        for name in ("models", "efforts"):
            value = getattr(self, name)
            if not isinstance(value, dict) or not all(isinstance(item, str) for item in (*value, *value.values())):
                raise ValueError(f"{name} must map model roles to names")
        model_roles.resolve(self.models, self.efforts, model_roles.Choice("partner"), roles=MODEL_ROLES)
        load_contract(self.scenario)
        if not isinstance(self.delegation, bool):
            raise ValueError("delegation must be a boolean")
        scripts(self.scripts)
        if self.assessor is not None:
            file, _, factory = str(self.assessor).rpartition(":")
            if not file or not Path(file).is_file() or not FACTORY.fullmatch(factory):
                raise ValueError("assessor names a Python file and its factory: path/to/file.py:name")
        if self.title is not None and (
            not isinstance(self.title, str) or not self.title.strip() or len(self.title) > TITLE_KEEP
        ):
            raise ValueError(f"title names the configured scenario in at most {TITLE_KEEP} characters")
        if self.information not in (None, "ask", "research"):
            raise ValueError("information is ask (read the materials and ask once) or research (also search the web)")
        if not isinstance(self.versions, dict):
            raise ValueError("versions map a name to a saved deployment")
        for name, file in self.versions.items():
            if not isinstance(name, str) or not name.strip() or len(name) > NAME_KEEP or saved_task(file) is None:
                raise ValueError(f"version {name!r} names no saved deployment")

    def spec(
        self, run_dir: Path, workdir: Path, task: str, record: Path | None = None, start: tuple[str, Path] | None = None
    ) -> dict:
        """What a session's process is started with (`session_host.Host`); `start` names the saved deployment a new
        session starts from and where it is."""
        own = {item.name: getattr(self, item.name) for item in fields(self) if item.name != "versions"}
        return {
            **{key: str(value) if isinstance(value, Path) else value for key, value in own.items()},
            "standard": list(self.standard),
            "run_dir": str(run_dir),
            "workdir": str(workdir),
            "task": task,
            "record": str(record) if record else None,
            "start_name": start[0] if start else None,
            "start_from": str(start[1]) if start else None,
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
        self.lock = threading.RLock()
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
        self.scenarios = Path(config.root) / "scenarios"
        self.handles: dict[str, Handle] = {}
        self.guard = threading.Lock()
        self.session_locks: dict[str, threading.RLock] = {}

    def _session_lock(self, session: str):
        with self.guard:
            return self.session_locks.setdefault(session, threading.RLock())

    def scenario(self, name: str | None):
        """A scenario sessions may start in, by name: the configured one (None or its own name), or one built on the
        page; None for any other name."""
        if name is None or name == self.contract.root.name:
            return self.contract
        if not isinstance(name, str) or not BUILT.fullmatch(name) or not (self.scenarios / name / name).is_dir():
            return None
        return load_contract(self.scenarios / name / name)

    def _spec(self, meta: dict, directory: Path, task: str, record=None, start=None) -> dict:
        """What a session's process starts with: the configuration's, with a built scenario's own package and scripts
        and the standard assessor on its checks and the person's chosen ones, since the configured assessor is the
        configured scenario's."""
        spec = self.config.spec(directory, self.workdirs / directory.name, task, record, start)
        name = meta.get("scenario")
        if name:
            scripts = self.scenarios / name / BUILT_SCRIPTS
            spec.update(
                scenario=str(self.scenarios / name / name),
                scripts=str(scripts) if scripts.is_file() else None,
                assessor=None,
                standard=["declared", "sedimented"],
                built=True,
            )
        return spec

    def _offered(self, contract) -> dict:
        """One scenario as the page offers it: its job, the materials a person may hand over and its scripts."""
        built = contract is not self.contract
        home = self.scenarios / contract.root.name
        title = json.loads((home / META).read_text()).get("title") if built and (home / META).is_file() else None
        title = title if built else self.config.title
        return {
            "name": contract.root.name,
            "title": title or contract.situation.profile.splitlines()[0][:TITLE_KEEP],
            "task": contract.situation.profile,
            "built": built,
            "materials": self.materials(contract),
            "scripts": [
                {"name": item["name"], "title": item["title"], "exam": item["exam"], "steps": len(item["steps"])}
                for item in scripts(home / BUILT_SCRIPTS if built else self.config.scripts)
            ],
        }

    def build(self, body: dict) -> tuple[int, dict]:
        """A scenario built from what the person gives on the page: its title, the job, text files handed over as one
        material, the requests to practise on and those kept for the exam, one per line, and the checks the work is
        judged by, one per line; written as a package under `scenarios` and read back before it is offered."""
        title, profile = _text_of(body.get("title")), _text_of(body.get("profile"))
        if not title or len(title) > TITLE_KEEP:
            return 400, {"error": f"a scenario needs a title of at most {TITLE_KEEP} characters"}
        if not profile or len(profile) > PROFILE_KEEP:
            return 400, {"error": f"a scenario needs its job description, at most {PROFILE_KEEP} characters"}
        lines = {}
        for kind, keep in (("practice", LINE_KEEP), ("exam", LINE_KEEP), ("checks", CHECK_KEEP)):
            raw = body.get(kind) or []
            if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
                return 400, {"error": f"{kind} is a list of texts"}
            lines[kind] = [item.strip() for item in raw if item.strip()]
            if len(lines[kind]) > LINES_KEPT or any(len(item) > keep for item in lines[kind]):
                return 400, {"error": f"{kind} holds at most {LINES_KEPT} lines of at most {keep} characters"}
        files = body.get("files") or []
        if not isinstance(files, list) or len(files) > FILES_KEPT:
            return 400, {"error": f"at most {FILES_KEPT} files"}
        written = {}
        for item in files:
            name = Path(item.get("name") or "").name if isinstance(item, dict) else ""
            text = item.get("text") if isinstance(item, dict) else None
            if (
                not name
                or name.startswith(".")
                or Path(name).suffix.lower() not in UPLOADED
                or not isinstance(text, str)
            ):
                return 400, {"error": f"a file is a text file named .md, .txt or .csv: {name!r}"}
            written["uploaded-" + name if name == SKILL else name] = text
        name = f"scn-{secrets.token_hex(4)}"
        home = self.scenarios / name
        package = home / name
        try:
            (package / "personas").mkdir(parents=True)
            (package / "profile.md").write_text(profile + "\n")
            (package / "personas" / "requester.md").write_text(PERSONA)
            if written:
                folder = package / "materials" / MATERIAL
                folder.mkdir(parents=True)
                for file, text in written.items():
                    (folder / file).write_text(text)
                listed = "\n".join(f"- {file}" for file in written)
                (folder / SKILL).write_text(
                    f"---\ndescription: The files handed over for this job\n---\n# Materials\n\n{listed}\n"
                )
            checks = [
                {"id": f"C{i}", "check": text, "severity": "standard"} for i, text in enumerate(lines["checks"], 1)
            ]
            (package / "scenario.json").write_text(
                json.dumps({"initial": [MATERIAL] if written else [], "criteria": checks}, ensure_ascii=False, indent=1)
            )
            seen = ["counterpart", "analyst", "curator"]
            (package / "contract.json").write_text(
                json.dumps(
                    {
                        "materials": {MATERIAL: {"kind": "fact"}} if written else {},
                        "checks": {check["id"]: {"visibility": seen} for check in checks},
                    },
                    ensure_ascii=False,
                    indent=1,
                )
            )
            played = [
                {
                    "name": f"{prefix}{i:02d}",
                    "title": f"{prefix}{i:02d} · {text[:28]}",
                    "exam": prefix == "e",
                    "steps": [{"text": text, "files": {}}],
                }
                for prefix, field in (("p", "practice"), ("e", "exam"))
                for i, text in enumerate(lines[field], 1)
            ]
            (home / BUILT_SCRIPTS).write_text(json.dumps(played, ensure_ascii=False, indent=1))
            (home / META).write_text(json.dumps({"title": title, "created": time.time()}, ensure_ascii=False, indent=1))
            contract = load_contract(package)
            scripts(home / BUILT_SCRIPTS)
        except (OSError, ValueError) as exc:
            shutil.rmtree(home, ignore_errors=True)
            return 400, {"error": f"the scenario could not be built: {exc}"}
        return 201, self._offered(contract)

    def directory(self, session: str) -> Path | None:
        """The run directory of a session this configuration keeps, only for a well-formed id."""
        if not isinstance(session, str) or not SESSION_ID.fullmatch(session):
            return None
        path = self.runs / session
        return path if (path / META).is_file() else None

    def materials(self, contract=None) -> list[dict]:
        """The materials a person may hand over (the contract's `handed`, those the partner may receive), each as the
        handover it becomes (its kind and its files as `uploads/<name>/...`) with where it came from when the counterpart did
        not simply give it."""
        contract = contract or self.contract
        out = []
        for name in contract.handed:
            material = contract.materials[name]
            files = sorted(
                f"uploads/{name}/{path.relative_to(material.path).as_posix()}"
                for path in material.path.rglob("*")
                if path.is_file()
            )
            origin = contract.provenance.materials.get(name)
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
                "curator": config.models.get("curator"),
                "analyst": config.models.get("analyst"),
                "standard": bool(config.standard or config.assessor),
            },
            "scripts": [
                {"name": item["name"], "title": item["title"], "exam": item["exam"], "steps": len(item["steps"])}
                for item in scripts(config.scripts)
            ],
            "versions": [{"name": name, "task": task} for name, (_, task) in self.versions().items()],
            "scenarios": [
                self._offered(contract)
                for contract in (
                    self.contract,
                    *(self.scenario(path.name) for path in sorted(self.scenarios.glob("scn-*"))),
                )
                if contract is not None
            ],
            "sessions": self.sessions(),
        }

    def versions(self) -> dict[str, tuple[Path, str]]:
        """The saved deployments a new session may start from, by name: the configuration's, then each archived
        session's last one, under its archive name."""
        found = {name: (Path(file), saved_task(file)) for name, file in self.config.versions.items()}
        for path in sorted(self.runs.iterdir()):
            archived = self._meta(path).get("archived") if self.directory(path.name) else None
            task = saved_task(path / DEPLOYMENT) if archived else None
            if task is not None:
                label = f"{archived['name']} {archived.get('version') or ''}".strip()
                found.setdefault(label, (path / DEPLOYMENT, task))
        return {name: (file, task) for name, (file, task) in found.items() if task is not None}

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
            "start": meta.get("start"),
            "scenario": meta.get("scenario"),
            "run": f"{session}/{record.stem}" if record is not None else None,
            "status": status,
            "models": _models(directory),
            "attached": bool(handle and handle.alive),
            "step": (handle.last or {}).get("step") if handle and handle.alive else None,
            "exportable": _exportable(directory / DEPLOYMENT),
        }

    def export(self, session: str) -> tuple[int, dict | exporting.Export]:
        """Download an idle saved revision while its process cannot receive another step."""
        with self._session_lock(session):
            return self._export(session)

    def _export(self, session: str) -> tuple[int, dict | exporting.Export]:
        directory = self.directory(session)
        if directory is None:
            return 404, {"error": "no such session"}
        handle = self.handles.get(session)
        with handle.lock if handle is not None else nullcontext():
            revision = None
            if handle is not None and handle.alive:
                reply = handle.ask({"op": "state"}, POLL_WAIT)
                state = reply.get("state") if reply else None
                if not state or state.get("step") is not None or state.get("trial") is not None:
                    return 409, {"error": "wait for the employee's current step to finish before exporting"}
                if not state.get("saved") or not state.get("revision"):
                    return 409, {"error": "the employee has no saved deployment to export"}
                revision = state["revision"]
            try:
                return 200, exporting.build(directory, self.config.config, revision=revision)
            except (OSError, ValueError, KeyError, TypeError):
                return 409, {"error": "the saved employee is unavailable or changed; finish a step and try again"}

    def create(self, body: dict) -> tuple[int, dict]:
        task, title, start = body.get("task"), body.get("title"), None
        contract = self.scenario(body.get("scenario"))
        if contract is None:
            return 400, {"error": "no such scenario"}
        if body.get("version") is not None:
            start = self.versions().get(body["version"]) if isinstance(body["version"], str) else None
            if start is None:
                return 400, {"error": "no saved version of that name"}
            task, start = start[1], (body["version"], start[0])
        if not isinstance(task, str) or not task.strip() or len(task) > TASK_KEEP:
            return 400, {"error": f"a session needs its task, at most {TASK_KEEP} characters"}
        if title is not None and (not isinstance(title, str) or len(title) > TITLE_KEEP):
            return 400, {"error": f"a title is at most {TITLE_KEEP} characters"}
        session = f"live-{time.strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(3)}"
        directory = self.runs / session
        directory.mkdir()
        meta = {
            "id": session,
            "title": (title or "").strip() or None,
            "task": task if start else task.strip(),
            "created": time.time(),
            **({"start": start[0]} if start else {}),
            **({"scenario": contract.root.name} if contract is not self.contract else {}),
        }
        (directory / META).write_text(json.dumps(meta, ensure_ascii=False, indent=2))
        self._launch(session, self._spec(meta, directory, meta["task"], start=start))
        return 201, self.summary(session)

    def _launch(self, session: str, spec: dict) -> None:
        process, connection = self.start(spec)
        with self.guard:
            self.handles[session] = Handle(process, connection)

    def resume(self, session: str) -> tuple[int, dict]:
        """Start a process on a kept session whose process is gone; it rehires the employee and resumes the record,
        and says on the page why when it cannot."""
        with self._session_lock(session):
            return self._resume(session)

    def _resume(self, session: str) -> tuple[int, dict]:
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
        self._launch(session, self._spec(meta, directory, meta.get("task", ""), record))
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
        if op == "delete":
            return self.delete(session)
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

    def delete(self, session: str) -> tuple[int, dict]:
        """Take the session off the list: its process is stopped where it stands and its run and working directories
        move to `trash` beside them, from where moving them back restores the session, to be resumed."""
        with self._session_lock(session):
            return self._delete(session)

    def _delete(self, session: str) -> tuple[int, dict]:
        directory = self.directory(session)
        if directory is None:
            return 404, {"error": "no such session"}
        with self.guard:
            handle = self.handles.pop(session, None)
        if handle is not None and handle.alive:
            handle.stop()
        trash = self.runs.parent / "trash"
        for kept, place in ((directory, trash / "runs"), (self.workdirs / session, trash / "workdirs")):
            if kept.exists():
                place.mkdir(parents=True, exist_ok=True)
                os.replace(kept, place / session)
        return 200, {"ok": True, "deleted": session}

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


def _exportable(path: Path) -> bool:
    try:
        stat = path.stat()
    except OSError:
        return False
    return _saved_exportable(str(path), stat.st_mtime_ns, stat.st_size)


@lru_cache(maxsize=128)
def _saved_exportable(path: str, mtime_ns: int, size: int) -> bool:
    return exporting.available(Path(path))


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
