"""One live cultivation session in a process of its own. The Studio server (`experimental.webui.live`) starts it for a
run directory and relays the page's steps over a pipe; it holds the employee and the loop's `Session` and answers
every message at once with its state, so the page can poll while a curation or a trial turn runs.

Each step is the Session's own (`onboard`, `trial`, `signal`, `assess`, `analyse`, `curate`, `skip`, `finish`), one
at a time, and a step the Session refuses is answered with its reason; calling a paused step again resumes it, as the
Session documents. Two steps play the scenario's scripts (`experimental.webui.live.scripts`), each on its own replica
of the employee: `script` as trials of the round and `exam` as the round's held-out trials, which the automatic
assessors score apart from the Analyst; `revert` puts back the version installed before the last curation, so a
curated version whose exam came out worse need not stay. The person on the page is the counterpart: what it writes,
the materials it hands over and its marks on the turns of the round's trials become a `Signal` from `human`, and in a trial it is the conversant, the terminal's `experimental.assessor.human.Human` reading
the page's messages instead (`PagePerson`). The run is assembled as the automated one (`experimental.simulation`)
assembles its own, from the scenario's contract, except that its boundaries warn instead of aborting: the person is
the counterpart, so what it says is its own to say, and a crossing is logged rather than refused.

The deployment the employee runs is saved beside the record after every step that changes it (`deployment.json`, and
`previous.json` for the one before the last curation), so a resumed process rehires the employee on it; an employee
that delegates cannot be saved (`employ.save`). A session may also start from a saved deployment (`start_from`).
"""

import asyncio
import base64
import importlib.util
import json
import os
import queue
import re
import time
from dataclasses import asdict, replace
from pathlib import Path

from raven.config.loader import load_config
from raven.config.mode_catalogue import build_mode_catalogue

from .. import model_roles
from ..analyst.run import Limits as AnalystLimits
from ..assessor.builder import RubricBuilder
from ..assessor.guidance import GuidanceStore
from ..assessor.human import Human
from ..assessor.reviewer import MetaReviewer
from ..assessor.standard import Assessor, Standard
from ..assessor.validation import ReplayCorpus, fingerprint
from ..curator.attribution import AttributionLimits, ModelAttributor
from ..curator.generation.run import Limits as CuratorLimits
from ..curator.harness import Task
from ..curator.raven_adapter.observe import plain
from ..experience.curator import CuratorExperience
from ..iteration.compartment import Boundaries
from ..iteration.conversation import Conversation
from ..iteration.protocols import Item, Signal
from ..iteration.records import cultivation
from ..iteration.session import Limits, Session, StepError
from ..requirements import ExternalRequirement
from ..scenario import ROLES, load
from ..scenario.sealed import sealed_for
from . import employ
from .live import MODEL_ROLES, scripts
from .process import redact
from .studio import slim_exchange

SOURCE = "human"
BACKGROUND = ("onboard", "trial", "script", "exam", "assess", "analyse", "curate", "revert")
AT_ONCE = ("signal", "skip", "finish")
DEPLOYMENT, PREVIOUS, EXAMS, INQUIRIES = "deployment.json", "previous.json", "exams.json", "inquiries.json"
# A person's mark on one turn of a trial: what it says of the reply, as the Analyst reads it.
MARKS = {"right": "right", "fix": "should have been", "wrong": "wrong", "missed": "missed"}
MAX_MARKS = 50
TRIAL = re.compile(r"trial-(\d+)")
MAX_TEXT = 20_000
REASON_KEEP = 1_500
# How much of a practice script's opening and of each reply an AI question's draft reads.
EXAMPLE, REPLY = 4_000, 6_000
# How many of the round's trials a proposal of acceptance checks reads.
TRIALS = 6
QUESTION_KEEP, ANSWERS_KEPT, INQUIRIES_AT_ONCE = 2_000, 5, 3
# Seconds a question of the information preparation waits for the person before its assumption stands.
ANSWER_WAIT = 1_800


def _written(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _reason(exc: BaseException) -> str:
    text = str(exc) if isinstance(exc, StepError) else f"{type(exc).__name__}: {exc}"
    return redact(text if len(text) <= REASON_KEEP else text[:REASON_KEEP] + "...")


def _text(value) -> str:
    text = value.strip() if isinstance(value, str) else ""
    if len(text) > MAX_TEXT:
        raise StepError(f"a message is at most {MAX_TEXT} characters")
    return text


def _names(value) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(name, str) and name for name in value):
        raise StepError("materials are a list of material names")
    return list(dict.fromkeys(value))


class PagePerson(Human):
    """The person on the page as a trial's conversant: `Human` asking the page instead of a terminal. `say` hands it
    the page's next message and `end` ends the conversation; `exchanges` is the conversation so far, `said` the
    message the employee is answering, and `waiting` whether the conversation waits for the person."""

    def __init__(self, name: str):
        self.inbox: queue.Queue = queue.Queue()
        super().__init__(ask=lambda _label: self.inbox.get(), show=lambda _text: None)
        self.name = name
        self.exchanges: list = []
        self.said: str | None = None
        self.waiting = False

    async def speak(self, exchanges):
        self.exchanges, self.said, self.waiting = exchanges, None, True
        try:
            return await super().speak(exchanges)
        finally:
            self.waiting = False

    def say(self, text: str) -> None:
        self.said, self.waiting = text, False
        self.inbox.put(text)

    def end(self) -> None:
        self.inbox.put(None)


class ScriptPerson:
    """A scenario's script as a trial's conversant: before each step it writes the step's files into the working
    directory its replica plays in (`placed`, filled as the replicas are made), then says the step's text; `end`
    stops it after the turn under way. `exchanges` is the conversation so far, for the page."""

    def __init__(self, script: dict, placed: dict):
        self.name, self.steps, self.placed = script["name"], script["steps"], placed
        self.exchanges: list = []
        self.stopped = False

    async def speak(self, exchanges):
        self.exchanges = exchanges
        if self.stopped or len(exchanges) >= len(self.steps):
            return None
        step = self.steps[len(exchanges)]
        workdir = Path(self.placed[self.name]["workdir"])
        for name, text in step.get("files", {}).items():
            path = workdir / name
            path.parent.mkdir(parents=True, exist_ok=True)
            if text.startswith("base64:"):  # a binary file (a .docx or .xlsx the person hands over)
                path.write_bytes(base64.b64decode(text[len("base64:") :]))
            else:
                path.write_text(text)
        return step["text"]

    def end(self) -> None:
        self.stopped = True


class Host:
    """The session behind one run directory, as `spec` describes it (see `experimental.webui.live.LiveConfig`):
    `boot` hires the employee and opens the Session, or with a `record` rehires it and resumes that record; `handle`
    answers one message from the server. `employ` hires and hands materials over (`experimental.webui.employ`)."""

    def __init__(self, spec: dict, employ=employ):
        self.spec, self.employ = spec, employ
        self.root, self.workdir = Path(spec["run_dir"]), Path(spec["workdir"])
        self.session: Session | None = None
        self.employee = self.contract = self.standard = None
        self.experience = None
        self.step: str | None = "starting"
        self.since = time.time()
        self.error: str | None = None
        self.failed: str | None = None
        self.opening: tuple[Signal, ...] = ()
        self.person: PagePerson | None = None
        self.turns: list[dict] = []
        self.task: asyncio.Task | None = None
        self.ended = False
        self.scripts = {script["name"]: script for script in scripts(spec.get("scripts"))}
        self.playing: list[ScriptPerson] = []
        self.plugin = None
        self.roles: dict = {}
        self.saved = False
        self.previous: str | None = None
        self.provider = None
        self.question: dict | None = None
        self.asking: asyncio.Task | None = None
        self.asked: dict[str, list[str]] = {}
        self.proposals: dict | None = None
        self.proposing: asyncio.Task | None = None
        self.inquiries: list[dict] = []
        self.inquiring: set[asyncio.Task] = set()
        self.asker: PageAsker | None = None

    async def boot(self) -> None:
        try:
            await self._boot()
        except Exception as exc:  # noqa: BLE001 -- a session that cannot start says why on the page
            self.error, self.failed = _reason(exc), "starting"
        finally:
            self.step = None

    async def _boot(self) -> None:
        spec = self.spec
        self.employ.prepare()
        self.contract = contract = load(Path(spec["scenario"]))
        boundaries = Boundaries(
            {role: sealed_for(contract, role) for role in ROLES}, policy="warn", log=self.root / "boundaries.jsonl"
        )
        roles = model_roles.resolve(
            spec["models"],
            spec["efforts"],
            model_roles.partner_of(load_config(Path(spec["config"]))),
            roles=MODEL_ROLES,
        )
        self.roles = roles
        record = json.loads(Path(spec["record"]).read_text()) if spec.get("record") else None
        if record is not None:
            task = Task(id=record["task_id"], text=record["task"])
        elif spec.get("start_from"):
            task = Task.model_validate(json.loads(Path(spec["start_from"]).read_text())["task"])
        else:
            task = Task(text=spec["task"])
        hiring = self.employ.rehire if record is not None else self.employ.hire
        self.employee = hiring(
            contract,
            Path(spec["config"]),
            task=task,
            workdir=self.workdir,
            root=self.root,
            subagent_model=roles["sub-harness"].model,
            timeout=spec["timeout"],
            guard=boundaries.compartment("partner").guard,
            delegation=spec.get("delegation", True),
        )
        if record is None:
            self._settings(roles)
        await self.employee.start()
        saved = self.root / DEPLOYMENT
        if record is not None and saved.is_file():
            await self.employ.load(self.employee, saved)
            self.saved = True
        elif record is not None and (
            record.get("initial_curation") or any(r.get("curation") for r in record["rounds"])
        ):
            raise StepError("the session's harness was never saved (its employee delegates), so it cannot be resumed")
        elif spec.get("start_from"):
            await self.employ.load(self.employee, Path(spec["start_from"]))
            self.saved = await self.employ.save(self.employee, saved)
        self.previous = self._read(PREVIOUS).get("revision")
        for item in self._read(INQUIRIES).get("items", []):
            if isinstance(item, dict):
                if item.pop("busy", None):
                    item["error"] = "the answer was interrupted when the session stopped"
                self.inquiries.append(item)
        provider = self.provider = model_roles.provider(self.employee.baseline.config, roles)
        assessor_role, builder_role = roles["assessor"], roles["rubric_builder"]
        if spec.get("standard"):
            memory = (
                Path(spec["evaluation_memory"]) if spec.get("evaluation_memory") else self.root / "evaluation-memory"
            )
            derived = "derived" in spec["standard"]
            self.standard = Assessor(
                provider,
                Standard.declared(
                    (check.id, check.check) for check in contract.statements.checks if "analyst" in check.visibility
                ),
                sources=spec["standard"],
                # A built scenario's checks are judged against what the person handed over, its facts among them.
                norms=(
                    lambda: self.employ.references(
                        contract, self.handed(), self.employee.baseline.config.workspace_path
                    )
                )
                if spec.get("built")
                else (lambda: self.employ.standing_norms(contract, self.handed())),
                task=self.employee.baseline.task.text,
                model=assessor_role.model,
                effort=assessor_role.effort,
                timeout=spec["timeout"],
                boundaries=boundaries,
                builder=(
                    RubricBuilder(model=builder_role.model, effort=builder_role.effort, timeout=spec["timeout"])
                    if "derived" in spec["standard"]
                    else None
                ),
                keep=self.root / "standard.json",
                reviewer=MetaReviewer(
                    model=roles["meta_reviewer"].model, effort=roles["meta_reviewer"].effort, timeout=spec["timeout"]
                )
                if derived
                else None,
                guidance_store=GuidanceStore(memory / "guidance.json") if derived else None,
                replay_corpus=ReplayCorpus(memory / "replays.json") if derived else None,
                scope=fingerprint({"task": self.employee.baseline.task.text}),
            )
            if spec.get("record"):
                self.standard.restore()
        if spec.get("experience_memory"):
            self.experience = CuratorExperience.from_provider(
                Path(spec["experience_memory"]),
                provider,
                access_scope=spec.get("experience_scope", "local"),
                model=roles["curator"].model,
                effort=roles["curator"].effort,
                migrate=spec.get("experience_migrate", False),
                writable_roots=(self.employee.root, self.employee.baseline.config.workspace_path),
            )
        if spec.get("assessor"):
            self.plugin = _plugin(spec["assessor"])(spec, self.employee)
        options = {
            **({"experience": self.experience} if self.experience is not None else {}),
            "assessors": self._assessors(),
            "analyst_model": roles["analyst"].model,
            "analyst_effort": roles["analyst"].effort,
            "curator_model": roles["curator"].model,
            "boundaries": boundaries,
            "attributor": ModelAttributor(
                model=roles["attribution"].model,
                effort=roles["attribution"].effort,
                limits=AttributionLimits(
                    call_timeout=spec["timeout"],
                    max_calls=spec["attribution_calls"],
                    max_queries=spec["attribution_queries"],
                ),
            ),
            "limits": Limits(
                max_rounds=spec["rounds"],
                analyst=AnalystLimits(call_timeout=spec["timeout"], max_calls=8),
                curator=CuratorLimits(
                    call_timeout=spec["timeout"], max_calls=spec["curator_calls"], max_queries=spec["curator_queries"]
                ),
            ),
        }
        if spec.get("information"):
            self.asker = PageAsker()
            options["prepare"] = self.employ.preparer(
                contract,
                self.handed,
                self.employee.baseline.config.workspace_path / "uploads",
                records=self.root / "information",
                model=roles["collector"].model,
                effort=roles["collector"].effort,
                ask=self.asker,
                research=spec["information"] == "research",
            )
        if spec.get("record"):
            self.session = Session.resume(self.employee, provider, Path(spec["record"]), **options)
        else:
            prior = [cultivation(path) for path in contract.prior.records]
            self.session = Session.open(self.employee, provider, prior=prior, **options)

    def _settings(self, roles: dict) -> None:
        """How the live run was set up, for readers of its directory; never a credential or the configuration's
        path."""
        spec = self.spec
        settings = {
            "chain": "live",
            "scenario": self.contract.root.name,
            "rounds": spec["rounds"],
            "turns": spec["turns"],
            "curator_budget": {"calls": spec["curator_calls"], "queries": spec["curator_queries"]},
            "attribution_budget": {"calls": spec["attribution_calls"], "queries": spec["attribution_queries"]},
            "standard": list(spec.get("standard") or ()) or None,
            **model_roles.recorded(roles),
            "partner_tier": build_mode_catalogue(self.employee.baseline.config).default,
            "starting_harness": self.employ.starting(),
            "start_from": spec.get("start_name"),
            "delegation": spec.get("delegation", True),
            "scripts": sorted(self.scripts) or None,
            "assessor": Path(spec["assessor"].rpartition(":")[0]).name if spec.get("assessor") else None,
            "provenance": self.contract.provenance.record or None,
            "started": time.time(),
        }
        (self.root / "settings.json").write_text(_written(settings))

    def handed(self) -> list[str]:
        """The materials handed over so far, in the order they first were."""
        session = self.session
        names = [
            handover["name"]
            for signal in session.record.get("opening", ())
            for handover in signal.get("attachments", ())
        ]
        for signal in [*(signal for round_ in session.rounds for signal in round_.signals), *session.signals]:
            names.extend(handover.name for handover in signal.attachments)
        return list(dict.fromkeys(names))

    def _open_trial(self) -> dict | None:
        """The trial in progress as the page shows it: its exchanges so far, each slimmed once, and what the person
        said that the employee is answering."""
        person = self.person
        if person is None:
            return None
        for exchange in person.exchanges[len(self.turns) :]:
            ref = {"round": "pending", "part": "sessions", "session": person.name, "turn": len(self.turns)}
            self.turns.append(redact(slim_exchange(plain(exchange), ref)))
        return {"name": person.name, "exchanges": list(self.turns), "said": person.said, "waiting": person.waiting}

    def _assessors(self) -> tuple:
        return tuple(assessor for assessor in (self.standard, self.plugin) if assessor is not None)

    def _read(self, name: str) -> dict:
        try:
            value = json.loads((self.root / name).read_text())
        except (OSError, ValueError):
            return {}
        return value if isinstance(value, dict) else {}

    def _exam_state(self, revision: str | None) -> dict | None:
        """The exam scores of the version installed and of the one before the last curation, by revision."""
        if revision is None or not any(script["exam"] for script in self.scripts.values()):
            return None
        exams = self._read(EXAMS)
        return {"current": exams.get(revision), "previous": exams.get(self.previous) if self.previous else None}

    def state(self) -> dict:
        session = self.session
        revision = getattr(self.employee, "revision_id", None) if session else None
        return {
            "step": self.step,
            "since": self.since,
            "error": self.error,
            "failed": self.failed,
            "status": session.status if session else None,
            "onboarded": bool(session and session.onboarded),
            "reviewing": bool(session and session.review is not None),
            "outcome": asdict(session.outcome) if session and session.outcome else None,
            "rounds": len(session.rounds) if session else 0,
            "pending": {"sessions": len(session.sessions), "signals": len(session.signals)} if session else None,
            "trial": self._open_trial(),
            "assessor": bool(self._assessors()),
            "assessed": bool(session) and any(signal.source in self._sources() for signal in session.signals),
            "scripts": [
                {"name": person.name, "done": len(person.exchanges), "steps": len(person.steps)}
                for person in self.playing
            ],
            "exam": self._exam_state(revision),
            "revision": revision,
            "revertible": self.previous is not None and self.previous != revision,
            "saved": self.saved,
            "question": self._drafted(),
            "proposals": self.proposals,
            "adopted": [r.quote for r in session.external_requirements if r.source == SOURCE] if session else [],
            "inquiries": self.inquiries,
            "information": self.asker.state() if self.asker is not None else None,
            "ended": self.ended,
        }

    def _drafted(self) -> dict | None:
        """The AI question asked for in the trial the person holds, drafted or still being drafted."""
        question, person = self.question, self.person
        return question if person is not None and question is not None and question["trial"] == person.name else None

    def _sources(self) -> set[str]:
        return {"standard", *(getattr(assessor, "name", "") for assessor in self._assessors())}

    async def handle(self, command) -> dict:
        op = command.get("op") if isinstance(command, dict) else None
        try:
            if op == "state":
                pass
            elif op == "say":
                self._say(_text(command.get("text")))
            elif op == "close":
                self._close_trial()
            elif op == "question":
                self._question()
            elif op == "propose":
                self._propose()
            elif op == "adopt":
                self._adopt(command)
            elif op == "inquire":
                self._inquire(command)
            elif op == "answer":
                self._answer(command)
            elif op == "finish":
                self._idle()
                await self._finish(command)
            elif op in AT_ONCE:
                self._ready()
                await getattr(self, f"_{op}")(command)
            elif op in BACKGROUND:
                self._ready()
                await self._start(op, command)
                if self.failed == op:
                    return {"ok": False, "error": self.error, "state": self.state()}
            else:
                raise StepError(f"unknown step: {op}")
        except (StepError, ValueError) as exc:
            return {"ok": False, "error": _reason(exc), "state": self.state()}
        return {"ok": True, "state": self.state()}

    def _idle(self) -> None:
        if self.step is not None:
            raise StepError(f"the session is busy: {self.step}")

    def _ready(self) -> None:
        self._idle()
        if self.session is None:
            raise StepError("the session could not start")

    async def _start(self, op: str, command: dict) -> None:
        self.step, self.since, self.error, self.failed = op, time.time(), None, None
        self.task = asyncio.create_task(self._background(op, getattr(self, f"_{op}")(command)))
        # The Session checks a step before its first await, so one pass of the loop answers a refused step as refused.
        await asyncio.sleep(0)

    async def _background(self, op: str, step) -> None:
        try:
            await step
        except Exception as exc:  # noqa: BLE001 -- a failed step is shown on the page; the Session kept what it records
            self.error, self.failed = _reason(exc), op
        finally:
            self.step, self.person = None, None

    def _handovers(self, command: dict):
        names = _names(command.get("materials"))
        if not names:
            return ()
        return self.employ.hand_over(
            self.contract,
            names,
            uploads=self.employee.baseline.config.workspace_path / "uploads",
            shared=self.employee.baseline.workdir / "uploads",
        )

    async def _onboard(self, command: dict) -> None:
        if not self.session.onboarded:
            text, handovers = _text(command.get("text")), self._handovers(command)
            self.opening = (
                (Signal(SOURCE, text, attachments=handovers, authority="external"),) if text or handovers else ()
            )
        try:
            await self.session.onboard(self.opening)
        finally:
            await self._keep()

    def _people(self, names, exam: bool) -> tuple[list[ScriptPerson], dict]:
        if not isinstance(names, list) or not names or not all(isinstance(name, str) for name in names):
            raise StepError("name the scripts to play")
        unknown = [name for name in names if self.scripts.get(name, {}).get("exam", not exam) != exam]
        if unknown:
            raise StepError(f"the scenario has no {'exam' if exam else 'practice'} scripts named {unknown}")
        placed: dict = {}
        return [ScriptPerson(self.scripts[name], placed) for name in dict.fromkeys(names)], placed

    def _scripted(self, people: list[ScriptPerson], placed: dict):
        """The scripts as one trial: each on its own replica of the employee as it stands, all at once."""

        def spawn(worker, label):
            return self.employ.replicate(
                worker,
                Path(self.spec["config"]),
                self.root / "replicas" / f"{label}-{int(time.time())}",
                subagent_model=self.roles["sub-harness"].model,
                timeout=self.spec["timeout"],
            )

        self.playing = people
        trials = {person.name: Conversation(person, max_turns=len(person.steps)) for person in people}
        return self.employ.together(trials, spawn, placed)

    async def _script(self, command: dict) -> None:
        people, placed = self._people(command.get("names"), exam=False)
        try:
            await self.session.trial(self._scripted(people, placed))
        finally:
            self.playing = []

    async def _exam(self, command: dict) -> None:
        """The scenario's exam scripts as the round's held-out trials, scored by its automatic assessors, the standard
        one judging each question on its own (`EachQuestion`); the score of the installed revision is kept, so the
        page can set it beside the version before the last curation."""
        assessors = self._assessors()
        if not assessors:
            raise StepError("no automatic assessor is configured to score an exam")
        assessors = tuple(EachQuestion(item) if item is self.standard else item for item in assessors)
        names = command.get("names") or [name for name, script in self.scripts.items() if script["exam"]]
        people, placed = self._people(names, exam=True)
        revision = self.employee.revision_id
        pending = self.session.pending_holdout
        if pending is not None and set(pending["sessions"]) != {person.name for person in people}:
            raise StepError("retry the same questions from the unfinished exam")
        if pending is None and self.session.held_out.keys() & {person.name for person in people}:
            raise StepError("these questions already have a completed exam in this round")
        try:
            signals = await self.session.holdout(
                [] if pending is not None else [self._scripted(people, placed)],
                assessors,
                retry=pending is not None,
            )
        finally:
            self.playing = []
        items = [item for signal in signals for item in signal.items]
        exams = self._read(EXAMS)
        exams[revision] = {
            "failed": sum(item.result == "fail" for item in items),
            "judged": sum(item.result in ("pass", "fail") for item in items),
            "scripts": sorted(person.name for person in people),
            "at": time.time(),
        }
        (self.root / EXAMS).write_text(_written(exams))

    async def _revert(self, command: dict) -> None:
        """Put back the version installed before the last curation, once; the Curator hears it in the round's
        signals and the history marks the undone change."""
        previous = self.root / PREVIOUS
        if not previous.is_file():
            raise StepError("there is no earlier version to go back to")
        if self.session.review is not None:
            raise StepError("curate or skip the analysed round before going back")
        if self.previous == self.employee.revision_id:
            raise StepError("the version before the last curation is the one installed")
        await self.employ.load(self.employee, previous)
        os.replace(previous, self.root / DEPLOYMENT)
        self.previous = None
        note = "The last change to the harness was undone: the employee is back on the version installed before it."
        history = self.session.history
        if history:
            history[-1] = history[-1].model_copy(
                update={"understanding": f"{history[-1].understanding}\n\n[undone] {note}"}
            )
        self.session.signal(Signal(SOURCE, note, authority="external"))

    async def _keep(self) -> None:
        """Save the deployment the employee now runs, for a resumed process to load."""
        self.saved = await self.employ.save(self.employee, self.root / DEPLOYMENT)

    async def _trial(self, command: dict) -> None:
        sessions = [*(round_.sessions for round_ in self.session.rounds), self.session.sessions]
        taken = {int(match[1]) for played in sessions for name in played if (match := TRIAL.fullmatch(name))}
        self.person, self.turns = PagePerson(f"trial-{max(taken, default=0) + 1}"), []
        await self.session.trial(Conversation(self.person, max_turns=self.spec["turns"]))

    def _say(self, text: str) -> None:
        if self.person is None:
            raise StepError("no trial is open")
        if not self.person.waiting:
            raise StepError("the employee is still answering")
        if not text:
            raise StepError("the message is empty")
        self.person.say(text)

    def _question(self) -> None:
        """Have the AI draft the next message of the trial the person holds; the draft, or why there is none, lands in
        the state beside the trial (`employ.question`)."""
        person = self.person
        if person is None or self.playing:
            raise StepError("an AI question is drafted for a trial you hold yourself")
        if not person.waiting:
            raise StepError("the employee is still answering")
        if self.asking is not None and not self.asking.done():
            raise StepError("the AI is still drafting a question")
        self.question = {"trial": person.name, "at": time.time(), "busy": True}
        self.asking = asyncio.create_task(self._ask(person))

    async def _ask(self, person: PagePerson) -> None:
        """Draft from what the counterpart may see, the requirements the Analyst raised last and the trial so far; never
        an exam script, whose cases must stay unseen by the Analyst this trial goes to."""
        asked = self.asked.setdefault(person.name, [])
        raised = next((r.feedback.requirements for r in reversed(self.session.rounds) if r.feedback), ())
        packet = {
            "job": self.employee.baseline.task.text,
            **self.employ.counterpart_view(self.contract, self.handed()),
            "requirements": [{"situation": r.situation, "behavior": r.behavior} for r in raised],
            "examples": [s["steps"][0]["text"][:EXAMPLE] for s in self.scripts.values() if not s["exam"]][:2],
            "trial": [{"said": x.user, "reply": (x.assistant or "")[:REPLY]} for x in person.exchanges],
            "earlier": list(asked),
        }
        role = self.roles["analyst"]
        try:
            drafted = await self.employ.question(
                self.provider, packet, model=role.model, effort=role.effort, timeout=self.spec["timeout"]
            )
        except Exception as exc:  # noqa: BLE001 -- a failed draft says why beside the trial; the trial goes on
            self.question = {"trial": person.name, "at": time.time(), "error": _reason(exc)}
            return
        asked.append(drafted["message"])
        self.question = {"trial": person.name, "at": time.time(), **drafted}

    def _inquire(self, command: dict) -> None:
        """Ask the analyst or the curator about its step of a round (`employ.inquire`): it answers from that step's
        record in the background, `INQUIRIES_AT_ONCE` questions at most at a time, and the question with its answer,
        or why there is none, is kept with the session."""
        if self.session is None:
            raise StepError("the session could not start")
        role, number, text = command.get("role"), command.get("round"), _text(command.get("question"))
        if role not in ("analyst", "curator"):
            raise StepError("ask the analyst or the curator")
        if not isinstance(number, int) or isinstance(number, bool):
            raise StepError("name the round the question is about")
        if not text or len(text) > QUESTION_KEEP:
            raise StepError(f"a question is 1 to {QUESTION_KEEP} characters")
        if len(self.inquiring) >= INQUIRIES_AT_ONCE:
            raise StepError(f"{INQUIRIES_AT_ONCE} questions are being answered; ask more once one is")
        record = self._step_record(role, number)
        entry = {"role": role, "round": number, "question": text, "at": time.time(), "busy": True}
        self.inquiries.append(entry)
        (self.root / INQUIRIES).write_text(_written({"items": self.inquiries}))
        task = asyncio.create_task(self._inquired(entry, record))
        self.inquiring.add(task)
        task.add_done_callback(self.inquiring.discard)

    def _answer(self, command: dict) -> None:
        """The person's answer to a question the information preparation is waiting on (`id`), or `skip` to leave the
        point to its stated assumption."""
        if self.asker is None:
            raise StepError("this session prepares no information")
        id, text, skip = command.get("id"), _text(command.get("text")), command.get("skip") is True
        if not isinstance(id, str):
            raise StepError("name the question answered")
        if not text and not skip:
            raise StepError("answer the question or skip it")
        if len(text) > QUESTION_KEEP:
            raise StepError(f"an answer is at most {QUESTION_KEEP} characters")
        self.asker.reply(id, None if skip else text)

    def _step_record(self, role: str, number: int) -> dict:
        """What the role decided in round `number` (0 is the onboarding) and why, as the session keeps it."""
        session = self.session
        if role == "analyst":
            done = session.rounds[number - 1] if 1 <= number <= len(session.rounds) else None
            if done is None or done.feedback is None:
                raise StepError("that round has no analysis to ask about")
            return {
                "analysis": done.feedback.model_dump(mode="json"),
                "signals": [
                    {
                        "source": signal.source,
                        "text": signal.text[:REPLY],
                        "failed": [f"{item.id}: {item.note[:600]}" for item in signal.items if item.result == "fail"][
                            :30
                        ],
                    }
                    for signal in done.signals
                ][:12],
                "trials": [
                    {
                        "trial": name,
                        "turns": [{"said": x.user[:EXAMPLE], "reply": (x.assistant or "")[:REPLY]} for x in turns],
                    }
                    for name, turns in list(done.sessions.items())[:TRIALS]
                ],
            }
        entry = next((item for item in session.history if item.round == number), None)
        if entry is None:
            raise StepError("that round has no finished curation to ask about")
        return {
            "curation": entry.model_dump(
                mode="json", include={"understanding", "revision", "diagnoses", "requirements"}
            )
        }

    async def _inquired(self, entry: dict, record: dict) -> None:
        earlier = [
            {"question": item["question"], "answer": item["answer"]}
            for item in self.inquiries
            if item is not entry
            and "answer" in item
            and (item["role"], item["round"]) == (entry["role"], entry["round"])
        ][-ANSWERS_KEPT:]
        packet = {
            "job": self.employee.baseline.task.text,
            "role": entry["role"],
            "round": entry["round"],
            "record": record,
            "question": entry["question"],
            "earlier": earlier,
        }
        role = self.roles[entry["role"]]
        try:
            entry["answer"] = await self.employ.inquire(
                self.provider, packet, model=role.model, effort=role.effort, timeout=self.spec["timeout"]
            )
        except asyncio.CancelledError:
            entry["error"] = "the answer was interrupted when the session stopped"
            raise
        except Exception as exc:  # noqa: BLE001 -- a failed answer says why beside the question; nothing else changes
            entry["error"] = _reason(exc)
        finally:
            entry.pop("busy", None)
            (self.root / INQUIRIES).write_text(_written({"items": self.inquiries}))

    def _propose(self) -> None:
        """Have the AI put what the person has not settled yet as choices (`employ.propose`); the choices, or why there
        are none, land in the state."""
        self._ready()
        if not self.session.onboarded:
            raise StepError("acceptance checks are proposed once the employee is onboarded")
        if not self.session.sessions:
            raise StepError("acceptance checks are proposed from this round's trials: open a trial first")
        if self.proposing is not None and not self.proposing.done():
            raise StepError("the AI is still proposing acceptance checks")
        self.proposals = {"at": time.time(), "busy": True}
        self.proposing = asyncio.create_task(self._proposed())

    async def _proposed(self) -> None:
        """Propose from what the counterpart may see, the checks already chosen, this round's trials and the person's
        remarks and marks on them."""
        session = self.session
        mine = [signal for signal in session.signals if signal.source == SOURCE]
        packet = {
            "job": self.employee.baseline.task.text,
            **self.employ.counterpart_view(self.contract, self.handed()),
            "chosen": [r.quote for r in session.external_requirements],
            "trials": [
                {
                    "trial": name,
                    "turns": [{"said": x.user[:EXAMPLE], "reply": (x.assistant or "")[:REPLY]} for x in turns],
                }
                for name, turns in list(session.sessions.items())[:TRIALS]
            ],
            "remarks": [signal.text for signal in mine if signal.text][-10:],
            "marks": [f"{item.id}: {item.note}" for signal in mine for item in signal.items][-20:],
        }
        role = self.roles["analyst"]
        try:
            items = await self.employ.propose(
                self.provider, packet, model=role.model, effort=role.effort, timeout=self.spec["timeout"]
            )
        except Exception as exc:  # noqa: BLE001 -- a failed proposal says why on the page; nothing else changes
            self.proposals = {"at": time.time(), "error": _reason(exc)}
            return
        self.proposals = {"at": time.time(), "items": [{**item, "chosen": None} for item in items]}

    def _adopt(self, command: dict) -> None:
        """The person settles a proposed check with one of its two answers or a rule in their own words. The rule joins
        the session's external requirements, which every automatic assessment from then on holds the trials to, and the
        round hears it as the person's words while its analysis has not begun."""
        self._ready()
        items = (self.proposals or {}).get("items") or []
        index = command.get("index")
        if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(items):
            raise StepError("an adoption names one of the proposed checks")
        item, own, option = items[index], command.get("rule"), command.get("option")
        if item["chosen"] is not None:
            raise StepError("this check is already settled")
        if own is not None:
            rule, option = _text(own), None
        elif option in (0, 1) and not isinstance(option, bool):
            rule = item["options"][option]["rule"]
        else:
            raise StepError("an adoption takes one of the two answers or a rule of your own")
        if not rule:
            raise StepError("the rule is empty")
        session = self.session
        requirement = ExternalRequirement(source=SOURCE, quote=rule, kind="gate", situation=item["topic"])
        if all(held.id != requirement.id for held in session.external_requirements):
            session.external_requirements.append(requirement)
        if session.review is None:
            session.signal(Signal(SOURCE, rule, authority="external"))
        else:
            session.save()
        item["chosen"] = {"option": option, "rule": rule}

    def _close_trial(self) -> None:
        if self.playing:
            for person in self.playing:
                person.end()
            return
        if self.person is None:
            raise StepError("no trial is open")
        self.person.end()

    def _marks(self, value) -> tuple[Item, ...]:
        """The person's marks on turns of the round's trials, as items the Analyst reads with the turn's reply."""
        if value is None:
            return ()
        if not isinstance(value, list) or len(value) > MAX_MARKS or not all(isinstance(mark, dict) for mark in value):
            raise StepError(f"marks are a list of at most {MAX_MARKS} turns")
        items = []
        for mark in value:
            exchanges = self.session.sessions.get(mark.get("session"))
            if exchanges is None:
                raise StepError("a mark names a trial of the round in progress")
            turn = mark.get("turn")
            if not isinstance(turn, int) or isinstance(turn, bool) or not 0 <= turn < len(exchanges):
                raise StepError("a mark names a turn of its trial")
            kind, text = mark.get("kind"), _text(mark.get("note"))
            if kind not in MARKS:
                raise StepError(f"a mark is one of {sorted(MARKS)}")
            exchange = exchanges[turn]
            items.append(
                Item(
                    id=f"{mark['session']}#{turn + 1}:{kind}",
                    result="pass" if kind == "right" else "fail",
                    session=mark["session"],
                    expected=text if kind in ("fix", "missed") else "",
                    actual=(exchange.assistant or "")[:MAX_TEXT],
                    note=f"[{MARKS[kind]}] turn {exchange.execution.turn_id}" + (f": {text}" if text else ""),
                    authority="external",
                )
            )
        return tuple(items)

    async def _signal(self, command: dict) -> None:
        """The person's words: on the round's trials before its analysis, or on the analysis before its curation,
        which the Curator then hears with the round's other signals."""
        text, handovers, items = _text(command.get("text")), self._handovers(command), self._marks(command.get("marks"))
        if not text and not handovers and not items:
            raise StepError("the message is empty")
        said = Signal(SOURCE, text, items=items, attachments=handovers, authority="external")
        if self.session.review is not None:
            self.session.remark(said)
        else:
            self.session.signal(said)

    async def _assess(self, command: dict) -> None:
        assessors = self._assessors()
        if not assessors:
            raise StepError("no automatic assessor is configured for live sessions")
        await self.session.assess(*assessors)

    async def _analyse(self, command: dict) -> None:
        await self.session.analyse()

    async def _curate(self, command: dict) -> None:
        if (self.root / DEPLOYMENT).is_file() and self._read(DEPLOYMENT).get("revision") == self.employee.revision_id:
            (self.root / PREVIOUS).write_bytes((self.root / DEPLOYMENT).read_bytes())
            self.previous = self.employee.revision_id
        try:
            await self.session.curate()
        finally:
            await self._keep()

    async def _skip(self, command: dict) -> None:
        self.session.skip()

    async def _finish(self, command: dict) -> None:
        """End the run, or only the process when the run cannot take another step: it never started, failed or
        finished."""
        session = self.session
        if session is not None and session.status not in ("finished", "error"):
            session.finish(_text(command.get("reason")) or None)
        self.ended = True

    async def close(self) -> None:
        if self.person is not None:
            self.person.end()
        for person in self.playing:
            person.end()
        for task in (self.task, self.asking, self.proposing, *self.inquiring):
            if task is not None and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        try:
            if self.employee is not None:
                await self.employee.close()
        finally:
            if self.experience is not None:
                self.experience.close()


class EachQuestion:
    """The standard assessor on an exam: it reads a set of sessions as one and gives one verdict per check over all
    of them, so here each exam question is judged apart, all at once, by a twin of it (`Assessor.twin`), and each
    verdict names its question (`C1:e02`), which lets the exam score and compare questions. An assessor without twins
    is refused before the exam plays a question. Held-out signals never reach the history, whose readings keep a
    requirement's verdict under its own id."""

    def __init__(self, inner):
        inner.twin()
        self.inner = inner

    def __getattr__(self, name):
        return getattr(self.inner, name)

    async def evaluate(self, sessions):
        twins = [self.inner.twin() for _ in sessions]
        try:
            async with asyncio.TaskGroup() as group:
                tasks = [
                    group.create_task(twin.evaluate({key: turns}))
                    for twin, (key, turns) in zip(twins, sessions.items(), strict=True)
                ]
        except ExceptionGroup as failed:
            raise failed.exceptions[0] from failed
        finally:
            self.inner.adopt(twins)
        given = [(key, task.result()) for key, task in zip(sessions, tasks, strict=True) if task.result() is not None]
        if not given:
            return None
        items = tuple(
            replace(item, id=f"{item.id}:{key}", session=key) for key, signal in given for item in signal.items
        )
        satisfied = [signal.satisfied for _, signal in given]
        return replace(
            given[0][1],
            items=items,
            metrics={},
            satisfied=False if False in satisfied else (True if all(value is True for value in satisfied) else None),
        )


class PageAsker:
    """The person as the information preparation's user channel: its questions wait on the page together
    (`together`), each until the person answers or skips it, in any order, or `wait` seconds pass, which leaves the
    point to the assumption the collector stated."""

    together = True

    def __init__(self, wait: float = ANSWER_WAIT):
        self.wait, self.asked = wait, []
        self.waiting: dict[str, tuple] = {}

    async def __call__(self, question) -> str | None:
        reply = asyncio.get_running_loop().create_future()
        self.waiting[question.id] = (question, reply)
        answer = None
        try:
            answer = await asyncio.wait_for(reply, self.wait)
        except TimeoutError:
            pass
        finally:
            del self.waiting[question.id]
            self.asked.append({**question.model_dump(mode="json"), "answer": answer})
        return answer

    def reply(self, id: str, answer: str | None) -> None:
        _, reply = self.waiting.get(id, (None, None))
        if reply is None or reply.done():
            raise StepError("that question of the information preparation is not waiting")
        reply.set_result(answer)

    def state(self) -> dict:
        return {
            "questions": [question.model_dump(mode="json") for question, _ in self.waiting.values()],
            "asked": self.asked,
        }


def _plugin(named: str):
    """The factory `path/to/file.py:name` names: called with the session's spec and its employee, it makes an
    automatic assessor (`experimental.assessor.role.AssessorProtocol`) whose `name` is its signals' source."""
    file, _, factory = named.rpartition(":")
    found = importlib.util.spec_from_file_location(f"studio_assessor_{Path(file).stem}", file)
    if found is None or found.loader is None:
        raise StepError(f"the assessor module cannot be read: {Path(file).name}")
    module = importlib.util.module_from_spec(found)
    found.loader.exec_module(module)
    return getattr(module, factory)


async def serve(connection, spec: dict, employ=employ) -> None:
    """Answer the server's messages, each echoing the `seq` it came with, until the server closes the pipe or asks to
    shut down, or the run has ended."""
    host = Host(spec, employ)
    booting = asyncio.create_task(host.boot())
    try:
        while not host.ended:
            try:
                command = await asyncio.to_thread(connection.recv)
            except (EOFError, OSError):
                break
            seq = command.get("seq") if isinstance(command, dict) else None
            if isinstance(command, dict) and command.get("op") == "shutdown":
                connection.send({"ok": True, "seq": seq, "state": host.state()})
                break
            connection.send({**await host.handle(command), "seq": seq})
    finally:
        if not booting.done():
            booting.cancel()
            await asyncio.gather(booting, return_exceptions=True)
        await host.close()


def main(connection, spec: dict) -> None:
    """The process entry: its output goes to `session.log` in the run directory."""
    with open(Path(spec["run_dir"]) / "session.log", "ab", buffering=0) as log:
        os.dup2(log.fileno(), 1)
        os.dup2(log.fileno(), 2)
        asyncio.run(serve(connection, spec))
