"""One live cultivation session in a process of its own. The Studio server (`experimental.webui.live`) starts it for a
run directory and relays the page's steps over a pipe; it holds the employee and the loop's `Session` and answers
every message at once with its state, so the page can poll while a curation or a trial turn runs.

Each step is the Session's own (`onboard`, `trial`, `signal`, `assess`, `analyse`, `curate`, `skip`, `finish`), one
at a time, and a step the Session refuses is answered with its reason; calling a paused step again resumes it, as the
Session documents. The person on the page is the party: what it writes and the materials it hands over become a
`Signal` from `human`, and in a trial it is the conversant, the terminal's `experimental.assessor.human.Human` reading
the page's messages instead (`PagePerson`). The run is assembled as the automated one (`experimental.simulation`)
assembles its own, from the scenario's contract, except that its boundaries warn instead of aborting: the person is
the party, so what it says is its own to say, and a crossing is logged rather than refused.
"""

import asyncio
import json
import os
import queue
import re
import time
from dataclasses import asdict
from pathlib import Path

from raven.config.mode_catalogue import build_mode_catalogue
from raven.providers.factory import make_lazy_provider, make_resolving_provider

from ..analyst.run import Limits as AnalystLimits
from ..assessor.human import Human
from ..assessor.standard import Standard, StandardAssessor
from ..curator.attribution import AttributionLimits, ModelAttributor
from ..curator.generation.run import Limits as CuratorLimits
from ..curator.raven_adapter.observe import plain
from ..iteration.compartment import Boundaries
from ..iteration.conversation import Conversation
from ..iteration.protocols import Signal
from ..iteration.records import cultivation
from ..iteration.session import Limits, Session, StepError
from ..scenario import ROLES, load
from ..scenario.sealed import sealed_for
from . import employ
from .process import redact
from .studio import slim_exchange

SOURCE = "human"
BACKGROUND = ("onboard", "trial", "assess", "analyse", "curate")
AT_ONCE = ("signal", "skip", "finish")
TRIAL = re.compile(r"trial-(\d+)")
MAX_TEXT = 20_000
REASON_KEEP = 1_500


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


class Host:
    """The session behind one run directory, as `spec` describes it (see `experimental.webui.live.LiveConfig`):
    `boot` hires the employee and opens the Session, or with a `record` rehires it and resumes that record; `handle`
    answers one message from the server. `employ` hires and hands materials over (`experimental.webui.employ`)."""

    def __init__(self, spec: dict, employ=employ):
        self.spec, self.employ = spec, employ
        self.root, self.workdir = Path(spec["run_dir"]), Path(spec["workdir"])
        self.session: Session | None = None
        self.employee = self.contract = self.standard = None
        self.step: str | None = "starting"
        self.since = time.time()
        self.error: str | None = None
        self.failed: str | None = None
        self.opening: tuple[Signal, ...] = ()
        self.person: PagePerson | None = None
        self.turns: list[dict] = []
        self.task: asyncio.Task | None = None
        self.ended = False

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
        hiring = self.employ.rehire if spec.get("record") else self.employ.hire
        self.employee = hiring(
            contract,
            Path(spec["config"]),
            task=spec["task"],
            workdir=self.workdir,
            root=self.root,
            subagent_model=spec.get("subagent_model"),
            timeout=spec["timeout"],
            guard=boundaries.compartment("partner").guard,
        )
        defaults = self.employee.baseline.config.agents.defaults
        if not defaults.reasoning_effort:
            raise ValueError("set agents.defaults.reasoningEffort explicitly; a provider default is not a run setting")
        if not spec.get("record"):
            self._settings(defaults.model, defaults.reasoning_effort)
        await self.employee.start()
        provider = self._provider()
        if spec.get("standard"):
            self.standard = StandardAssessor(
                provider,
                Standard.declared(
                    (check.id, check.check) for check in contract.statements.checks if "analyst" in check.visibility
                ),
                sources=spec["standard"],
                norms=lambda: self.employ.standing_norms(contract, self.handed()),
                effort=spec.get("standard_effort"),
                timeout=spec["timeout"],
                boundaries=boundaries,
            )
        options = {
            "analyst_model": spec.get("analyst_model") or spec.get("curator_model"),
            "curator_model": spec.get("curator_model"),
            "boundaries": boundaries,
            "attributor": ModelAttributor(
                model=spec.get("attribution_model"),
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
        if spec.get("record"):
            self.session = Session.resume(self.employee, provider, Path(spec["record"]), **options)
        else:
            prior = [cultivation(path) for path in contract.prior.records]
            self.session = Session.open(self.employee, provider, prior=prior, **options)

    def _provider(self):
        """The provider of the model roles, as an automated run makes it: the employee's configuration, on the
        Curator's model and effort when the configuration names them, each call's vendor following its model id once
        any role runs on a model of its own."""
        spec = self.spec
        config = self.employee.baseline.config.model_copy(deep=True)
        overridden = spec.get("curator_model") or spec.get("analyst_model") or spec.get("attribution_model")
        if overridden:
            config.agents.defaults.provider = "auto"
        if spec.get("curator_model"):
            config.agents.defaults.model = spec["curator_model"]
        if spec.get("curator_effort"):
            config.agents.defaults.reasoning_effort = spec["curator_effort"]
        return make_resolving_provider(config) if overridden else make_lazy_provider(config)

    def _settings(self, employee: str, effort: str) -> None:
        """How the live run was set up, for readers of its directory; never a credential or the configuration's
        path."""
        spec = self.spec
        curator = spec.get("curator_model") or employee
        settings = {
            "chain": "live",
            "scenario": self.contract.root.name,
            "rounds": spec["rounds"],
            "turns": spec["turns"],
            "curator_budget": {"calls": spec["curator_calls"], "queries": spec["curator_queries"]},
            "attribution_budget": {"calls": spec["attribution_calls"], "queries": spec["attribution_queries"]},
            "standard": list(spec.get("standard") or ()) or None,
            "models": {
                "employee": employee,
                "curator": curator,
                "analyst": spec.get("analyst_model") or curator,
                "attribution": spec.get("attribution_model") or curator,
                "subagents": spec.get("subagent_model"),
            },
            "efforts": {
                "employee": effort,
                "employee_tier": build_mode_catalogue(self.employee.baseline.config).default,
                "curator": spec.get("curator_effort"),
                "standard": spec.get("standard_effort"),
            },
            "starting_harness": self.employ.starting(),
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

    def state(self) -> dict:
        session = self.session
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
            "assessor": self.standard is not None,
            "ended": self.ended,
        }

    async def handle(self, command) -> dict:
        op = command.get("op") if isinstance(command, dict) else None
        try:
            if op == "state":
                pass
            elif op == "say":
                self._say(_text(command.get("text")))
            elif op == "close":
                self._close_trial()
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
            self.opening = (Signal(SOURCE, text, attachments=handovers),) if text or handovers else ()
        await self.session.onboard(self.opening)

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

    def _close_trial(self) -> None:
        if self.person is None:
            raise StepError("no trial is open")
        self.person.end()

    async def _signal(self, command: dict) -> None:
        text, handovers = _text(command.get("text")), self._handovers(command)
        if not text and not handovers:
            raise StepError("the message is empty")
        self.session.signal(Signal(SOURCE, text, attachments=handovers))

    async def _assess(self, command: dict) -> None:
        if self.standard is None:
            raise StepError("no automatic assessor is configured for live sessions")
        try:
            await self.session.assess(self.standard)
        finally:
            (self.root / "standard.json").write_text(_written(self.standard.record()))

    async def _analyse(self, command: dict) -> None:
        await self.session.analyse()

    async def _curate(self, command: dict) -> None:
        await self.session.curate()

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
        if self.task is not None and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        if self.employee is not None:
            await self.employee.close()


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
