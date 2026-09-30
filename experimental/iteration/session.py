"""One cultivation driven a step at a time: trial, assessment, analysis, curation, each one call.

A `Session` is the loop's steps for a caller that decides between them, such as a person on a page; `run` is the
loop deciding for itself, on the same steps. The session keeps its record file current after every step, so a reader
can follow it and a new process can resume it, and runs each model role inside its compartment when boundaries are
given. `Outcome` says after each analysis what the loop would do next, and the caller may do otherwise.
"""

import json
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal
from uuid import uuid4

from ..analyst.feedback import Feedback
from ..analyst.role import Analyst
from ..analyst.run import Limits as AnalystLimits
from ..audience import project
from ..curator.generation.run import GapReportedError, GenerationInterruptedError
from ..curator.generation.run import Limits as CuratorLimits
from ..curator.raven_adapter.materialize import _write
from ..curator.raven_adapter.observe import plain
from ..curator.raven_adapter.worker import Execution
from ..curator.workflow import PENDING, improve
from .compartment import Boundaries, Compartment
from .hearing import heard, heard_activity, heard_history, heard_observations, heard_prior
from .history import Entry, entry
from .ledger import mark
from .protocols import Exchange, Handover, Item, Sessions, Signal
from .records import Cultivation


@dataclass(frozen=True)
class Limits:
    max_rounds: int = 3
    analyst: AnalystLimits = field(default_factory=AnalystLimits)
    curator: CuratorLimits = field(default_factory=CuratorLimits)

    def __post_init__(self):
        if not isinstance(self.max_rounds, int) or self.max_rounds < 1:
            raise ValueError("the round budget must be a positive integer")


@dataclass(frozen=True)
class Round:
    """One round, with the analysis, attribution and curation record files it produced under the worker root;
    `feedback` is None when the analysis failed. `holdout` and `holdout_signals` are the held-out trials of the
    round and their assessment: recorded and measured, never read by the Analyst or cited to the Curator."""

    sessions: Sessions
    signals: tuple[Signal, ...]
    feedback: Feedback | None
    curated: bool
    analysis: tuple[str, ...] = ()
    curation: tuple[str, ...] = ()
    attribution: tuple[str, ...] = ()
    holdout: Sessions = field(default_factory=dict)
    holdout_signals: tuple[Signal, ...] = ()


class _Records:
    """Name the record files a step adds to a directory, so rounds can be joined to them later."""

    def __init__(self, directory: Path, exclude=()):
        self.directory, self.exclude = directory, frozenset(exclude)
        self.seen = self._names()

    def _names(self):
        if not self.directory.is_dir():
            return set()
        return {path.name for path in self.directory.glob("*.json")} - self.exclude

    def added(self) -> tuple[str, ...]:
        current = self._names()
        new = tuple(sorted(current - self.seen))
        self.seen = current
        return new


def satisfied(signals) -> bool:
    return bool(signals) and all(signal.satisfied is True for signal in signals)


async def trial_sessions(worker, trials) -> Sessions:
    sessions = {}
    for trial in trials:
        produced = await trial.run(worker)
        if sessions.keys() & produced.keys():
            raise ValueError(f"trials produced the same session key: {sorted(sessions.keys() & produced.keys())}")
        sessions.update(produced)
    return sessions


async def assess(assessors, sessions, history=()) -> tuple[Signal, ...]:
    """Every assessor's signal on the sessions. An assessor that keeps a standard of its own is first handed the
    history as the Analyst reads it (`sediment`, see `experimental.assessor.standard`), so the requirements raised so
    far become its regression checks."""
    signals = []
    for assessor in assessors:
        sediment = getattr(assessor, "sediment", None)
        if sediment is not None:
            sediment(project(tuple(history), "analyst"))
        signal = await assessor.evaluate(sessions)
        if signal is not None:
            signals.append(signal)
    return tuple(signals)


class StepError(RuntimeError):
    """A step called when the session is not at the point it belongs to."""


@dataclass(frozen=True)
class Outcome:
    """What the loop would do after a round's analysis, with the loop's own words for it."""

    next: Literal["curate", "continue", "stop"]
    reason: str = ""


def _signal(value: dict) -> Signal:
    items = tuple(Item(**item) for item in value.get("items", ()))
    attachments = tuple(Handover(**item) for item in value.get("attachments", ()))
    return Signal(**{**value, "items": items, "attachments": attachments})


def _sessions(value: dict) -> Sessions:
    return {
        key: [Exchange(row["user"], Execution(**row["execution"])) for row in exchanges]
        for key, exchanges in value.items()
    }


def _round(value: dict) -> Round:
    return Round(
        _sessions(value["sessions"]),
        tuple(_signal(signal) for signal in value["signals"]),
        Feedback.model_validate(value["feedback"]) if value["feedback"] else None,
        value["curated"],
        tuple(value.get("analysis", ())),
        tuple(value.get("curation", ())),
        tuple(value.get("attribution", ())),
        _sessions(value.get("holdout", {})),
        tuple(_signal(signal) for signal in value.get("holdout_signals", ())),
    )


class Session:
    """The steps of one run on a worker bound to its task; `open` a new one or `resume` one from its record."""

    def __init__(
        self,
        worker,
        provider,
        *,
        analyst=None,
        curator=None,
        analyst_model=None,
        curator_model=None,
        limits=Limits(),
        probe=None,
        path=None,
        boundaries: Boundaries | None = None,
        attributor=None,
        prior=(),
    ):
        if worker.baseline.task is None:
            raise ValueError("a session requires a worker bound to a current task")
        self.worker, self.provider = worker, provider
        self.curator = improve if curator is None else curator
        if boundaries is not None and boundaries.log is None:
            boundaries = replace(boundaries, log=worker.root / "boundaries.jsonl")
        self.boundaries = boundaries
        if analyst is None:
            analyst = Analyst(
                self._guarded(provider, "analyst"),
                model=analyst_model,
                limits=limits.analyst,
                sealed=boundaries.sealed.get("curator") if boundaries is not None else None,
            )
        self.analyst = analyst
        self.curator_model, self.limits, self.probe, self.attributor = curator_model, limits, probe, attributor
        self.rounds: list[Round] = []
        self.history: list[Entry] = []
        self.prior: tuple[Cultivation, ...] = tuple(prior)
        if self.prior and boundaries is not None:
            guard = boundaries.compartment("curator", spoken=self._prior_spoken()).guard
            guard.check(heard_prior(self.prior), "admit:prior")
        self.previous_signals: tuple[Signal, ...] = ()
        self.previous_feedback: Feedback | None = None
        self.analyses = _Records(worker.root / "analysis")
        self.curations = _Records(worker.root / "curation", exclude={PENDING, "composition.json"})
        self.attributions = _Records(worker.root / "attribution")
        self.path = Path(path) if path else worker.root / "iteration" / f"{uuid4().hex}.json"
        self.record = {
            "task_id": worker.baseline.task.id,
            "task": worker.baseline.task.text,
            "status": "running",
            "curator": self.curator.__name__,
            "opening": [],
            "rounds": self.rounds,
            "history": self.history,
            **({"prior": [cultivation.record() for cultivation in self.prior]} if self.prior else {}),
        }
        self.sessions: Sessions = {}
        self.signals: list[Signal] = []
        self.held_out: Sessions = {}
        self.held_out_signals: list[Signal] = []
        self.review = None
        self.outcome: Outcome | None = None

    @classmethod
    def open(cls, worker, provider, **options) -> "Session":
        session = cls(worker, provider, **options)
        session.save()
        return session

    @classmethod
    def resume(cls, worker, provider, path, **options) -> "Session":
        """Continue the run a record describes: its rounds, history and any round in progress come back as they were."""
        record = json.loads(Path(path).read_text())
        prior = [Cultivation.of(value) for value in record.get("prior", ())]
        session = cls(worker, provider, path=path, **{"prior": prior, **options})
        if record["task_id"] != session.record["task_id"]:
            raise ValueError("the record belongs to another task")
        session.rounds.extend(_round(item) for item in record["rounds"])
        session.history.extend(Entry.model_validate(row) for row in record.get("history", ()))
        session.record.update(
            {
                key: record[key]
                for key in ("opening", "initial_curation", "initial_attribution", "questions", "error")
                if key in record
            }
        )
        session.record["curator"] = record.get("curator", session.record["curator"])
        pending = record.get("pending") or {}
        session.sessions = _sessions(pending.get("sessions", {}))
        session.signals = [_signal(signal) for signal in pending.get("signals", ())]
        session.held_out = _sessions(pending.get("holdout", {}))
        session.held_out_signals = [_signal(signal) for signal in pending.get("holdout_signals", ())]
        if session.rounds:
            last = session.rounds[-1]
            session.previous_signals, session.previous_feedback = last.signals, last.feedback
            if "review" in pending and last.feedback is not None:
                session.review = _Pending(last.feedback, tuple(pending["review"].get("activity", ())))
                session.outcome = Outcome("curate")
        session.record["status"] = record["status"]
        if "stop" in record:
            session.record["stop"] = record["stop"]
        return session

    @property
    def status(self) -> str:
        return self.record["status"]

    @property
    def onboarded(self) -> bool:
        return "initial_curation" in self.record

    def save(self) -> None:
        record = dict(self.record)
        if self.sessions or self.signals or self.held_out or self.review is not None:
            record["pending"] = {"sessions": self.sessions, "signals": self.signals}
            if self.held_out:
                record["pending"].update(holdout=self.held_out, holdout_signals=self.held_out_signals)
            if self.review is not None:
                record["pending"]["review"] = {"activity": list(self.review.activity)}
        _write(self.path, json.dumps(plain(record), ensure_ascii=False).encode())

    def _require(self, condition: bool, message: str, *, resuming: bool = False) -> None:
        if self.record["status"] in ("finished", "error"):
            raise StepError(f"the session is {self.record['status']}")
        if self.record["status"] == "paused" and not resuming:
            raise StepError("the paused curation resumes first: call the step that paused again")
        if not condition:
            raise StepError(message)

    def _compartment(self, role: str, *, spoken=()) -> Compartment:
        if self.boundaries is None:
            return Compartment(role)
        return self.boundaries.compartment(role, spoken=spoken)

    def _guarded(self, provider, role: str):
        return provider if self.boundaries is None else self.boundaries.compartment(role).provider(provider)

    def _spoken(self, current: Sessions | None = None) -> list[tuple[str, ...]]:
        """What every conversant said in the rounds so far, one stream per session, `current` included: the Analyst
        reads it and the party may quote any of it to the Curator, so neither compartment seals it."""
        rounds = [round.sessions for round in self.rounds]
        if current is not None and all(current is not sessions for sessions in rounds):
            rounds.append(current)
        return [
            tuple(exchange.user for exchange in exchanges) for sessions in rounds for exchanges in sessions.values()
        ]

    def _prior_spoken(self) -> list[tuple[str, ...]]:
        """What the prior's conversants said, which its own Curator compartment spared."""
        return [stream for cultivation in self.prior for stream in cultivation.spoken]

    def _heard(self, feedback: dict | None) -> dict | None:
        """The feedback of a curation with the prior the party brought, when it brought one."""
        if not self.prior:
            return feedback
        return {**(feedback or {}), "prior": heard_prior(self.prior)}

    async def _curate(self, feedback, observations=None, spoken=(), attribution=None) -> str:
        """One call of the curator inside its compartment; the feedback, the observations and every request it
        makes are checked. `spoken` are the conversants' words so far (see `_spoken`), which the compartment does
        not seal, and neither does it seal what the prior's conversants said; `attribution` is one made elsewhere
        that the curator takes instead of attributing itself.

        Returns `done`, `paused` (the call may be repeated to resume) or `asked`: the Curator reported a gap it
        cannot close with what it was given, nothing was revised, and its question waits in the record's
        `questions` for whoever can answer it, a person on the page or the party's next handover."""
        self.record["status"] = "running"
        self.record.pop("stop", None)
        feedback = self._heard(feedback)
        spoken = [*spoken, *self._prior_spoken()]
        try:
            async with self._compartment("curator", spoken=spoken) as scope:
                await self.curator(
                    self.worker,
                    scope.provider(self.provider),
                    feedback=None if feedback is None else scope.admit(feedback, "feedback"),
                    model=self.curator_model,
                    limits=self.limits.curator,
                    probe=self.probe,
                    **({} if observations is None else {"observations": scope.admit(observations, "observations")}),
                    **({} if self.attributor is None else {"attributor": self.attributor}),
                    **({} if attribution is None else {"attribution": attribution}),
                )
        except GenerationInterruptedError as exc:
            self.record["status"], self.record["stop"] = "paused", str(exc)
            return "paused"
        except GapReportedError as exc:
            self.record.setdefault("questions", []).append(
                {"round": len(self.rounds), "stage": exc.stage, "question": exc.reason}
            )
            return "asked"
        except Exception as exc:
            self.record["status"], self.record["error"] = "error", str(exc)
            raise
        return "done"

    async def onboard(self, opening=()) -> bool:
        """The first curation, from the task and whatever `opening` hands over; False when it paused and may be called again."""
        self._require(
            not self.rounds and (not self.onboarded or self.status == "paused"), "onboarding comes first", resuming=True
        )
        if not self.onboarded:
            self.record["opening"] = plain(tuple(opening))
            self.save()
        try:
            status = await self._curate({"signals": plain(heard(opening))} if opening else None)
        finally:
            self.record["initial_curation"] = [*self.record.get("initial_curation", ()), *self.curations.added()]
            self.record["initial_attribution"] = [
                *self.record.get("initial_attribution", ()),
                *self.attributions.added(),
            ]
            self.save()
        if status == "done" and self.record["initial_curation"] and self.worker.last_plan is not None:
            self.history.append(
                entry(
                    0,
                    (),
                    None,
                    self.worker.last_plan,
                    attribution=self._last("attribution"),
                    selection=self._last("selection"),
                    children=self._last("children"),
                )
            )
            self.save()
        return status != "paused"

    async def trial(self, *trials) -> Sessions:
        """Play trials on the worker as it stands; their sessions join the round in progress."""
        self._require(self.onboarded and self.review is None, "a trial runs after onboarding and before the analysis")
        produced = await trial_sessions(self.worker, trials)
        if self.sessions.keys() & produced.keys():
            raise ValueError(f"trials produced the same session key: {sorted(self.sessions.keys() & produced.keys())}")
        self.sessions.update(produced)
        self.save()
        return produced

    async def holdout(self, trials, assessors) -> tuple[Signal, ...]:
        """Play held-out trials on the worker as it stands and assess them apart from the round: their sessions
        and signals join the round's record, never the Analyst's reading or the Curator's citations.

        The trials must leave nothing behind in the worker (play them on replicas the way the simulation plays its
        cards), or what they said would reach the Curator through the worker's own state."""
        self._require(self.onboarded and self.review is None, "a held-out trial runs before the round's analysis")
        produced = await trial_sessions(self.worker, trials)
        if self.held_out.keys() & produced.keys():
            raise ValueError(f"trials produced the same session key: {sorted(self.held_out.keys() & produced.keys())}")
        self.held_out.update(produced)
        signals = await assess(assessors, produced, self.history)
        self.held_out_signals.extend(signals)
        self.save()
        return signals

    def signal(self, signal: Signal) -> None:
        """An assessment given directly, such as a person's words about the round's trials."""
        self._require(self.review is None, "a signal joins the round before its analysis")
        self.signals.append(signal)
        self.save()

    async def assess(self, *assessors) -> tuple[Signal, ...]:
        self._require(self.review is None, "assessment comes before the analysis")
        try:
            signals = await assess(assessors, self.sessions, self.history)
        except Exception as exc:
            self._abort(exc, self.signals)
            raise
        self.signals.extend(signals)
        self.save()
        return signals

    async def analyse(self) -> Outcome:
        """The Analyst reads the round; the round is recorded, and the outcome says what the loop would do next."""
        self._require(self.sessions and self.review is None, "the analysis needs trials and runs once per round")
        signals = tuple(self.signals)
        try:
            async with self._compartment("analyst", spoken=self._spoken(self.sessions)):
                review = await self.analyst.review(
                    self.worker,
                    self.sessions,
                    signals,
                    previous_signals=self.previous_signals,
                    previous_feedback=self.previous_feedback,
                    history=tuple(self.history),
                    spoken=[*self._spoken(self.sessions), *self._prior_spoken()],
                )
        except Exception as exc:
            self._abort(exc, signals)
            raise
        feedback = review.feedback
        if self.history:
            self.history[-1] = mark(self.history[-1], feedback, signals)
        wanted = feedback.decision == "curate" or any(signal.attachments for signal in signals)
        curated = wanted and feedback.decision != "stop" and len(self.rounds) + 1 < self.limits.max_rounds
        self.rounds.append(
            Round(
                self.sessions,
                signals,
                feedback,
                curated,
                self.analyses.added(),
                holdout=self.held_out,
                holdout_signals=tuple(self.held_out_signals),
            )
        )
        self.previous_signals, self.previous_feedback = signals, feedback
        # The round now holds its sessions and signals; only the review waits for the curation.
        self.sessions, self.signals, self.held_out, self.held_out_signals = {}, [], {}, []
        self.review = review
        if curated:
            self.outcome = Outcome("curate")
        elif feedback.decision == "stop":
            self.outcome = Outcome("stop", "the analyst stopped the run")
        elif not signals:
            self.outcome = Outcome("stop", "no assessor produced a signal")
        elif satisfied(signals):
            self.outcome = Outcome("stop", "every assessor is satisfied")
        elif len(self.rounds) >= self.limits.max_rounds:
            self.outcome = Outcome(
                "stop",
                "rounds exhausted" + ("; the last review was not curated, no round would test it" if wanted else ""),
            )
        else:
            self.outcome = Outcome("continue")
        if not curated:
            self._close(plan=None)
        self.save()
        return self.outcome

    async def curate(self, attribution=None) -> bool:
        """Revise the Harness from the analysed round; False when the Curator paused and may be called again. A
        reported gap ends the round unrevised with its question kept (see `_curate`).

        The Curator attributes the round's requirements before it changes anything; `attribution` supplies an
        attribution made elsewhere instead, such as diagnoses a person reviewed."""
        self._require(
            self.review is not None and self.rounds[-1].curated,
            "curation follows an analysis that asked for it",
            resuming=True,
        )
        sessions, signals, feedback = self.rounds[-1].sessions, self.rounds[-1].signals, self.rounds[-1].feedback
        try:
            status = await self._curate(
                {
                    "signals": plain(heard(signals)),
                    "history": heard_history(self.history),
                    "mechanism_activity": heard_activity(self.review.activity),
                    **project(feedback, "curator"),
                },
                heard_observations(sessions, feedback, self.record["task_id"]),
                self._spoken(),
                attribution,
            )
        finally:
            self.rounds[-1] = replace(
                self.rounds[-1],
                curation=(*self.rounds[-1].curation, *self.curations.added()),
                attribution=(*self.rounds[-1].attribution, *self.attributions.added()),
            )
            self.save()
        if status == "paused":
            return False
        if status == "asked":
            self.rounds[-1] = replace(self.rounds[-1], curated=False)
        curated = status == "done" and bool(self.rounds[-1].curation)
        self._close(
            plan=self.worker.last_plan if curated else None,
            attribution=self._last("attribution") if curated else None,
            selection=self._last("selection") if curated else None,
            children=self._last("children") if curated else None,
        )
        self.save()
        return True

    def extend(self, curator: CuratorLimits) -> None:
        """Give the Curator a larger budget from here on, such as to resume a curation that paused on its budget.
        A budget counts across a paused call and its resumptions, so no limit may shrink. An attribution's budget is
        its attributor's: resume with an attributor given larger limits."""
        current = self.limits.curator
        smaller = [
            name
            for name in ("calls", "queries", "checks", "repairs")
            if getattr(curator, f"max_{name}") < getattr(current, f"max_{name}")
        ]
        if smaller:
            raise ValueError(f"a budget only grows; smaller than now: {smaller}")
        self.limits = replace(self.limits, curator=curator)

    def skip(self) -> None:
        """Leave the analysed round uncurated, the way the loop leaves a last round: its review stays on record."""
        self._require(self.review is not None, "there is no analysed round to leave")
        self.rounds[-1] = replace(self.rounds[-1], curated=False)
        self.outcome = Outcome("continue")
        self._close(plan=None)
        self.save()

    def finish(self, reason: str | None = None) -> None:
        """End the run; without a reason, the loop's own reason from the last outcome stands."""
        self._require(self.review is None, "finish after the round's curation or skip")
        self.record["status"] = "finished"
        stop = reason if reason is not None else (self.outcome.reason if self.outcome else "")
        if stop:
            self.record["stop"] = stop
        self.save()

    def _abort(self, exc, signals) -> None:
        """A failed assessment or analysis ends the run; the round is recorded without feedback."""
        self.rounds.append(
            Round(
                self.sessions,
                tuple(signals),
                None,
                False,
                self.analyses.added(),
                holdout=self.held_out,
                holdout_signals=tuple(self.held_out_signals),
            )
        )
        self.record["status"], self.record["error"] = "error", str(exc)
        self.sessions, self.signals, self.held_out, self.held_out_signals = {}, [], {}, []
        self.save()

    def _last(self, name):
        """What the worker's last activation came from: its `attribution`, its `selection`, or the `children`
        candidates it installed."""
        return getattr(self.worker, f"last_{name}", None)

    def _close(self, *, plan, attribution=None, selection=None, children=None) -> None:
        self.history.append(
            entry(
                len(self.rounds),
                self.rounds[-1].signals,
                self.rounds[-1].feedback,
                plan,
                self.review.activity,
                attribution,
                selection,
                children,
            )
        )
        self.sessions, self.signals, self.review = {}, [], None
        self.held_out, self.held_out_signals = {}, []


@dataclass(frozen=True)
class _Pending:
    """The review of a resumed record's last round, whose curation had not completed."""

    feedback: Feedback
    activity: tuple = ()
