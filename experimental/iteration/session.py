"""One cultivation driven a step at a time: trial, assessment, analysis, curation, each one call.

A `Session` is the loop's steps for a caller that decides between them, such as a person on a page; `run` is the
loop deciding for itself, on the same steps. The session keeps its record file current after every step, so a reader
can follow it and a new process can resume it, and runs each model role inside its compartment when boundaries are
given. `Outcome` says after each analysis what the loop would do next, and the caller may do otherwise.
"""

import asyncio
import json
from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from ..analyst.feedback import Feedback
from ..analyst.role import Analyst
from ..analyst.run import Limits as AnalystLimits
from ..analyst.run import sourced
from ..assessor.validation import evidence_fingerprint, fingerprint, promotion
from ..audience import project
from ..curator.generation.run import GapReportedError, GenerationInterruptedError
from ..curator.generation.run import Limits as CuratorLimits
from ..curator.raven_adapter.materialize import _write
from ..curator.raven_adapter.observe import plain
from ..curator.raven_adapter.worker import Execution
from ..curator.workflow import PENDING, improve
from ..requirements import ExternalRequirement
from .compartment import Boundaries, Compartment
from .hearing import heard, heard_activity, heard_history, heard_observations, heard_prior
from .history import Entry, entry
from .labels import SessionLabels
from .ledger import mark
from .protocols import Exchange, Handover, Item, Sessions, Signal
from .records import RETRYABLE, Cultivation, retryable_step


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


def _assessment_batches(assessors):
    """Finish unchanged-worker reviews before other assessors may release next-round materials."""
    assessors = tuple(assessors)
    before = tuple(assessor for assessor in assessors if getattr(assessor, "before_handover", False) is True)
    after = tuple(assessor for assessor in assessors if getattr(assessor, "before_handover", False) is not True)
    return tuple(batch for batch in (before, after) if batch)


async def assess(assessors, sessions, history=(), external_requirements=(), verifications=None) -> tuple[Signal, ...]:
    """Assessors judge concurrently within each handover phase; unchanged-worker reviews finish first. The first
    to fail stops its phase and is raised. An assessor that keeps a standard of its own first receives the history
    as the Analyst reads it (`sediment`, see `experimental.assessor.standard`), so requirements raised so far become
    its regression checks."""
    tasks = []
    try:
        for batch in _assessment_batches(assessors):
            async with asyncio.TaskGroup() as group:
                tasks.extend(
                    group.create_task(_assessed(assessor, sessions, history, external_requirements, verifications))
                    for assessor in batch
                )
    except ExceptionGroup as failed:
        raise failed.exceptions[0] from failed
    return tuple(signal for task in tasks if (signal := task.result()) is not None)


async def _assessed(assessor, sessions, history, external_requirements, verifications) -> Signal | None:
    sediment = getattr(assessor, "sediment", None)
    if sediment is not None:
        sediment(project(tuple(history), "analyst"))
    constrain = getattr(assessor, "constrain", None)
    if constrain is not None:
        constrain(external_requirements)
    policy = deepcopy(getattr(assessor, "verification_policy", lambda: None)()) if verifications is not None else None
    evidence = evidence_fingerprint(sessions) if policy is not None else None
    signal = await assessor.evaluate(sessions)
    if policy is not None:
        witness = {
            "policy": fingerprint(policy),
            "kind": policy.get("kind"),
            "evidence": evidence,
            "source": signal.source if signal is not None else "",
            "satisfied": signal.satisfied if signal is not None else None,
        }
        if (
            signal is None
            or type(signal.satisfied) is not bool
            or evidence_fingerprint(sessions) != evidence
            or assessor.verification_policy() != policy
        ):
            witness["error"] = "The normal-task verifier or its frozen evidence is unresolved."
        verifications.append(witness)
    return signal


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
        analyst_effort=None,
        curator_model=None,
        limits=Limits(),
        probe=None,
        path=None,
        boundaries: Boundaries | None = None,
        attributor=None,
        prior=(),
        prepare=None,
        assessors=(),
        measuring=frozenset(),
        experience=None,
    ):
        if worker.baseline.task is None:
            raise ValueError("a session requires a worker bound to a current task")
        self.worker, self.provider = worker, provider
        self.assessors = list(assessors)
        self.measuring = frozenset(measuring)
        self.curator = improve if curator is None else curator
        self.prepare = prepare
        self.experience = experience
        if boundaries is not None and boundaries.log is None:
            boundaries = replace(boundaries, log=worker.root / "boundaries.jsonl")
        self.boundaries = boundaries
        if analyst is None:
            analyst = Analyst(
                self._guarded(provider, "analyst"),
                model=analyst_model,
                effort=analyst_effort,
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
        self.external_requirements: list[ExternalRequirement] = []
        self.analyses = _Records(worker.root / "analysis")
        self.curations = _Records(worker.root / "curation", exclude={PENDING, "composition.json"})
        self.attributions = _Records(worker.root / "attribution")
        self.path = Path(path) if path else worker.root / "iteration" / f"{uuid4().hex}.json"
        self.record: dict = {
            "task_id": worker.baseline.task.id,
            "task": worker.baseline.task.text,
            "status": "running",
            "curator": self.curator.__name__,
            "opening": [],
            "rounds": self.rounds,
            "history": self.history,
            "external_requirements": self.external_requirements,
            **({"measuring": sorted(self.measuring)} if self.measuring else {}),
            **({"prior": [cultivation.record() for cultivation in self.prior]} if self.prior else {}),
            **({"experience": experience.identity} if experience is not None else {}),
        }
        self.sessions: Sessions = {}
        self.signals: list[Signal] = []
        self.held_out: Sessions = {}
        self.held_out_signals: list[Signal] = []
        self.pending_holdout: dict | None = None
        self.verification: list[dict] = []
        self.record["promotion"] = {"status": "candidate", "reason": "Independent verification has not run."}
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
        session = cls(
            worker, provider, path=path, **{"prior": prior, "measuring": record.get("measuring", ()), **options}
        )
        if record["task_id"] != session.record["task_id"]:
            raise ValueError("the record belongs to another task")
        if record.get("experience") != session.record.get("experience"):
            raise ValueError("the session must resume with its original experience scope and policy")
        session.rounds.extend(_round(item) for item in record["rounds"])
        session.history.extend(Entry.model_validate(row) for row in record.get("history", ()))
        session.external_requirements.extend(
            ExternalRequirement.model_validate(row) for row in record.get("external_requirements", ())
        )
        session.record.update(
            {
                key: record[key]
                for key in (
                    "opening",
                    "initial_curation",
                    "initial_attribution",
                    "questions",
                    "gap_resolutions",
                    "gap_retry",
                    "error",
                    "error_step",
                    "error_revision",
                    "error_context",
                    "analysis_failures",
                    "assessment_failures",
                    "information",
                    "experience_pending",
                )
                if key in record
            }
        )
        session.record["curator"] = record.get("curator", session.record["curator"])
        pending = record.get("pending") or {}
        session.sessions = _sessions(pending.get("sessions", {}))
        session.signals = [_signal(signal) for signal in pending.get("signals", ())]
        session.held_out = _sessions(pending.get("holdout", {}))
        session.held_out_signals = [_signal(signal) for signal in pending.get("holdout_signals", ())]
        session.pending_holdout = pending.get("holdout_assessment")
        session.verification = list(pending.get("verification", ()))
        for witness in session.verification:
            witness["error"] = "Resume requires a fresh verification with the current verifier policy."
        if "promotion" in record:
            session.record["promotion"] = record["promotion"]
        if "stable_revision" in record:
            session.record["stable_revision"] = record["stable_revision"]
        if record["status"] != "finished" and session.record["promotion"].get("status") == "accepted":
            session.record["promotion"] = {
                "status": "candidate",
                "revision": session._revision(),
                "reason": "Resume requires fresh independent verification; the previously verified revision is retained.",
            }
        if session.rounds:
            last = session.rounds[-1]
            session.previous_signals, session.previous_feedback = session._acted(last.signals), last.feedback
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
        accepted = self.record.get("promotion", {})
        if accepted.get("status") == "accepted" and (
            accepted["revision"] != self._revision() or accepted["context"] != self._verification_context()
        ):
            self.record["promotion"] = {
                "status": "candidate",
                "revision": self._revision(),
                "reason": "The current revision or requirements differ from the verified version.",
            }
        record = dict(self.record)
        if self.sessions or self.signals or self.held_out or self.review is not None:
            record["pending"] = {"sessions": self.sessions, "signals": self.signals}
            if self.held_out:
                record["pending"].update(holdout=self.held_out, holdout_signals=self.held_out_signals)
            if self.pending_holdout is not None:
                record["pending"]["holdout_assessment"] = self.pending_holdout
            if self.verification:
                record["pending"]["verification"] = self.verification
            if self.review is not None:
                record["pending"]["review"] = {"activity": list(self.review.activity)}
        _write(self.path, json.dumps(plain(record), ensure_ascii=False).encode())

    def _acted(self, signals) -> tuple[Signal, ...]:
        """The signals the loop acts on: all but those of a measuring source, which stay with the round as its
        measurement and reach neither the Analyst, the decision to stop, the history nor the Curator."""
        return tuple(signal for signal in signals if signal.source not in self.measuring)

    def _require(self, condition: bool, message: str, *, resuming: bool = False) -> None:
        if self.record["status"] in ("finished", "error"):
            raise StepError(f"the session is {self.record['status']}")
        if self.record["status"] == "blocked":
            raise StepError("the curation is blocked; resolve its reported gap before continuing")
        if "gap_retry" in self.record and not resuming:
            raise StepError("retry the resolved curation gap before continuing")
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
        reads it and the counterpart may quote any of it to the Curator, so neither compartment seals it."""
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
        """The curation's feedback, prior cultivations and gaps reported by earlier curations."""
        additions = {}
        if self.prior:
            additions["prior"] = heard_prior(self.prior)
        if self.record.get("questions"):
            additions["previous_gaps"] = deepcopy(self.record["questions"])
        if self.record.get("gap_resolutions"):
            additions["gap_resolutions"] = deepcopy(self.record["gap_resolutions"])
        return {**(feedback or {}), **additions} if additions else feedback

    async def _curate(self, feedback, observations=None, spoken=(), attribution=None) -> str:
        """One call of the curator inside its compartment; the feedback, the observations and every request it
        makes are checked. `spoken` are the conversants' words so far (see `_spoken`), which the compartment does
        not seal, and neither does it seal what the prior's conversants said; `attribution` is one made elsewhere
        that the curator takes instead of attributing itself.

        Returns `done`, `paused` (the call may be repeated to resume) or `blocked`: the Curator reported a gap it
        cannot close with what it was given. Nothing was revised; resolve the recorded question before retrying."""
        self.record["status"] = "running"
        self.record.pop("stop", None)
        self.record.pop("gap_retry", None)
        feedback = self._heard(feedback)
        if self.record.get("information", {}).get("status") == "ready":
            feedback = {**(feedback or {}), "information": self.record["information"]["handoff"]}
        spoken = [*spoken, *self._prior_spoken()]
        experience_before = self.curations._names() if self.experience is not None else set()
        experience_context = self._verification_context() if self.experience is not None else None
        experience_policies = [
            fingerprint(policy)
            for assessor in self.assessors
            if self.experience is not None
            and (policy := getattr(assessor, "verification_policy", lambda: None)()) is not None
        ]
        try:
            async with self._compartment("curator", spoken=spoken) as scope:
                provider = scope.provider(self.provider)
                names = set(self.sessions)
                for round in self.rounds:
                    names.update(round.sessions)
                for item in (*self.history, *(entry for prior in self.prior for entry in prior.history)):
                    names.update(row["session"] for row in item.mechanisms_acted if row.get("session"))
                labels = SessionLabels.protected(provider, names)
                feedback = labels.encode(plain(feedback))
                observations = labels.encode(plain(observations))
                if attribution is not None:
                    projected = scope.admit(labels.encode(plain(attribution)), "attribution")
                    attribution = type(attribution).model_validate(projected)
                await self.curator(
                    self.worker,
                    provider,
                    feedback=None if feedback is None else scope.admit(feedback, "feedback"),
                    model=self.curator_model,
                    limits=self.limits.curator,
                    probe=self.probe,
                    **({} if observations is None else {"observations": scope.admit(observations, "observations")}),
                    **({} if self.attributor is None else {"attributor": self.attributor}),
                    **({} if attribution is None else {"attribution": attribution}),
                    **({"experience": self.experience} if self.experience is not None else {}),
                )
        except GenerationInterruptedError as exc:
            self.record["status"], self.record["stop"] = "paused", str(exc)
            return "paused"
        except GapReportedError as exc:
            self.record.setdefault("questions", []).append(
                {"round": len(self.rounds), "stage": exc.stage, "question": exc.reason}
            )
            self.record["status"], self.record["stop"] = "blocked", str(exc)
            return "blocked"
        except Exception as exc:
            self.record["status"], self.record["error"] = "error", str(exc)
            raise
        if self.experience is not None:
            for name in self.curations._names() - experience_before:
                record = json.loads((self.curations.directory / name).read_text())
                learned = record.get("experience_learning", {})
                if learned.get("event") and learned.get("origin"):
                    self.record.setdefault("experience_pending", []).append(
                        {
                            "event": learned["event"],
                            "revision": record.get("active_artifact_id"),
                            "context": experience_context,
                            "policies": experience_policies,
                            "origin": learned["origin"],
                        }
                    )
        return "done"

    async def onboard(self, opening=()) -> bool:
        """Prepare inputs, then curate once; False when preparation is unready or curation pauses or is blocked."""
        self._require(
            not self.rounds and (not self.onboarded or self.status == "paused" or self.record.get("gap_retry") == 0),
            "onboarding comes first",
            resuming=True,
        )
        if not self.onboarded:
            self.record["opening"] = plain(tuple(opening))
            self.save()
        else:
            opening = tuple(_signal(signal) for signal in self.record.get("opening", ()))
        if self.prepare is not None and self.record.get("information", {}).get("status") != "ready":
            async with self._compartment("curator", spoken=self._prior_spoken()) as scope:
                result = await self.prepare(
                    self.worker,
                    scope.provider(self.provider),
                    feedback=scope.admit(self._heard({"signals": plain(heard(opening))}), "information.input"),
                    admit=scope.admit,
                )
                from ..research.curator import information_feedback

                self.record["information"] = {
                    "status": result.status,
                    "version": result.snapshot.identity,
                    "handoff": information_feedback(result) if result.ready else None,
                    "questions": [item.model_dump(mode="json") for item in result.snapshot.description.unresolved],
                }
            if not result.ready:
                self.record["status"] = result.status
                self.save()
                return False
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
        return status == "done"

    async def trial(self, *trials) -> Sessions:
        """Play trials on the worker as it stands; their sessions join the round in progress."""
        self._require(self.onboarded and self.review is None, "a trial runs after onboarding and before the analysis")
        produced = await trial_sessions(self.worker, trials)
        if self.sessions.keys() & produced.keys():
            raise ValueError(f"trials produced the same session key: {sorted(self.sessions.keys() & produced.keys())}")
        self.sessions.update(produced)
        self.save()
        return produced

    async def holdout(self, trials, assessors, *, retry: bool = False) -> tuple[Signal, ...]:
        """Play held-out trials on the worker as it stands and assess them apart from the round: their sessions
        and signals join the round's record, never the Analyst's reading or the Curator's citations.

        The trials must leave nothing behind in the worker (play them on replicas the way the simulation plays its
        cards), or what they said would reach the Curator through the worker's own state. With `retry`, only the
        unfinished assessment is retried, on the saved answers and unchanged employee; no trials may be supplied."""
        self._require(self.onboarded and self.review is None, "a held-out trial runs before the round's analysis")
        trials = tuple(trials)
        revision, context = self._revision(), self._verification_context()
        if retry:
            pending = self.pending_holdout
            self._require(pending is not None and not trials, "retry only an unfinished held-out assessment")
            self._require(
                pending["revision"] == revision and pending["context"] == context,
                "the employee or requirements changed since the unfinished held-out assessment",
            )
            produced = {name: self.held_out[name] for name in pending["sessions"]}
        else:
            self._require(self.pending_holdout is None, "retry the unfinished held-out assessment first")
        assessors = tuple(assessors)
        policies = []
        for assessor in assessors:
            constrain = getattr(assessor, "constrain", None)
            if constrain is not None:
                constrain(self.external_requirements)
            policy = deepcopy(getattr(assessor, "verification_policy", lambda: None)())
            policies.append(policy)
        if not retry:
            produced = await trial_sessions(self.worker, trials)
            if self.held_out.keys() & produced.keys():
                raise ValueError(
                    f"trials produced the same session key: {sorted(self.held_out.keys() & produced.keys())}"
                )
            self.held_out.update(produced)
            self.pending_holdout = {"sessions": list(produced), "revision": revision, "context": context}
            self.save()
        evidence = evidence_fingerprint(produced)
        signals = await assess(assessors, produced, self.history, self.external_requirements)
        self.held_out_signals.extend(signals)
        matched = {signal.source: signal for signal in signals}
        training_inputs = {
            exchange.user
            for played in [self.sessions, *(round_.sessions for round_ in self.rounds)]
            for exchanges in played.values()
            for exchange in exchanges
        }
        for assessor, policy in zip(assessors, policies):
            if policy is None:
                continue
            signal = matched.get(getattr(assessor, "name", ""))
            witness = {
                "revision": revision,
                "context": context,
                "policy": policy,
                "evidence": evidence,
                "sessions": list(produced),
                "satisfied": signal.satisfied if signal is not None else None,
            }
            executions = [exchange.execution for exchanges in produced.values() for exchange in exchanges]
            if signal is None or sum(other.source == signal.source for other in signals) != 1:
                witness["error"] = "The independent verifier needs an unambiguous signal."
            elif any(exchange.user in training_inputs for exchanges in produced.values() for exchange in exchanges):
                witness["error"] = "Held-out inputs overlap the observed training conversations."
            elif not revision or not executions or any(execution.artifact_id != revision for execution in executions):
                witness["error"] = "Held-out executions do not establish the current revision."
            elif self._revision() != revision or evidence_fingerprint(produced) != evidence:
                witness["error"] = "The revision or verification evidence changed during replay."
            elif getattr(assessor, "verification_policy")() != policy:
                witness["error"] = "The verifier changed its frozen policy."
            self.verification.append(witness)
            if not witness.get("error"):
                for adaptive in self.assessors:
                    corpus = getattr(adaptive, "replay_corpus", None)
                    if corpus is not None:
                        try:
                            corpus.capture(
                                task=self.worker.baseline.task.text,
                                norms=adaptive.norms(),
                                sessions=produced,
                                witness=witness,
                                source=self.path,
                            )
                        except (OSError, ValueError) as exc:
                            witness["learning_error"] = str(exc)
        self.pending_holdout = None
        self.save()
        return signals

    def _revision(self):
        return getattr(self.worker, "revision_id", getattr(self.worker, "artifact_id", None))

    def _verification_context(self):
        return fingerprint(
            {
                "task": self.worker.baseline.task.text,
                "external_requirements": plain(self.external_requirements),
                "baseline": self.worker.baseline.export() if hasattr(self.worker.baseline, "export") else None,
            }
        )

    def signal(self, signal: Signal) -> None:
        """An assessment given directly, such as a person's words about the round's trials."""
        self._require(self.review is None, "a signal joins the round before its analysis")
        self.signals.append(signal)
        self.save()

    def remark(self, signal: Signal) -> None:
        """A person's words on the analysed round before its curation, such as a requirement they reject: the round
        keeps them with its signals, so the Curator hears them with the rest and the next analysis reads them."""
        self._require(
            self.review is not None and self.rounds[-1].curated, "a remark on the analysis comes before its curation"
        )
        self.rounds[-1] = replace(self.rounds[-1], signals=(*self.rounds[-1].signals, signal))
        self.previous_signals = self._acted(self.rounds[-1].signals)
        self.save()

    async def assess(self, *assessors) -> tuple[Signal, ...]:
        """Each assessor's signal joins the round and the record as soon as it is given, so one that fails after
        others have spoken ends the run with their words kept in the round. Reviews requiring the unchanged
        worker run before an assessor can hand over next-round materials."""
        self._require(self.review is None, "assessment comes before the analysis")
        witnesses = [] if self.experience is not None else None
        for assessor in assessors:
            if not any(assessor is registered for registered in self.assessors):
                self.assessors.append(assessor)
        start = len(self.signals)

        async def judged(assessor):
            signal = await _assessed(assessor, self.sessions, self.history, self.external_requirements, witnesses)
            signals = () if signal is None else (signal,)
            self.signals.extend(signals)
            self.save()
            return signals

        tasks = []
        try:
            for batch in _assessment_batches(assessors):
                async with asyncio.TaskGroup() as group:
                    tasks.extend(group.create_task(judged(assessor)) for assessor in batch)
        except ExceptionGroup as failed:
            self._abort(failed.exceptions[0], self.signals, step="assess")
            raise failed.exceptions[0] from failed
        given = tuple(signal for task in tasks for signal in task.result())
        self.signals[start:] = given
        if self.experience is not None:
            await self._experience_outcomes(witnesses)
        self.save()
        return given

    async def _experience_outcomes(self, witnesses):
        from ..experience.contracts import OutcomeReceipt

        ignored = {row["policy"] for row in witnesses if row["source"] in self.measuring}
        relevant = [row for row in witnesses if row["source"] not in self.measuring]
        if not relevant or any(row.get("error") for row in relevant) or not self.sessions:
            return
        revision, context = self._revision(), self._verification_context()
        evidence = evidence_fingerprint(self.sessions)
        if any(row["evidence"] != evidence for row in relevant) or any(
            exchange.execution.artifact_id != revision for values in self.sessions.values() for exchange in values
        ):
            return
        policies = {row["policy"] for row in relevant}
        observed = fingerprint({"revision": revision, "evidence": evidence, "policies": sorted(policies)})
        for pending in self.record.get("experience_pending", ()):
            if pending["revision"] != revision or pending.get("observed") == observed:
                continue
            comparable = pending["context"] == context and policies == set(pending["policies"]) - ignored
            origin = pending["origin"]
            receipt = OutcomeReceipt(
                access_scope=self.experience.access.access_scope,
                revision_id=revision,
                scope=origin["scope"],
                input_key=origin["input_key"],
                held=all(row["satisfied"] for row in relevant),
                basis="observation",
                comparability="comparable" if comparable else "unknown",
                observations=(f"Frozen independent normal-task verification {observed}; evidence {evidence}.",),
            )
            try:
                result = await self.experience.outcome(pending["event"], receipt, held_out=False)
                pending.update(observed=observed, result=result)
            except Exception as exc:
                pending["error"] = str(exc)

    async def _review(self, signals):
        signals = self._acted(signals)
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
            return replace(review, feedback=sourced(review.feedback, signals, self.history))

    def _retain_external(self, feedback):
        held = {requirement.id for requirement in self.external_requirements}
        added = tuple(requirement for requirement in feedback.external_requirements if requirement.id not in held)
        self.external_requirements.extend({requirement.id: requirement for requirement in added}.values())
        return added

    async def analyse(self) -> Outcome:
        """The Analyst reads the round; the round is recorded, and the outcome says what the loop would do next."""
        self._require(self.sessions and self.review is None, "the analysis needs trials and runs once per round")
        signals = tuple(self.signals)
        acted = self._acted(signals)
        phase = "analyse"
        try:
            review = await self._review(signals)
            added = self._retain_external(review.feedback)
            checked = []
            if added:
                for assessor in self.assessors:
                    reassess = getattr(assessor, "assess_external", None)
                    if reassess is not None:
                        phase = "assess"
                        signal = await reassess(added, self.sessions)
                        if signal is not None:
                            checked.append(signal)
                self.signals.extend(checked)
                signals = tuple(self.signals)
                if any(item.result in ("fail", "unknown") for signal in checked for item in signal.items):
                    phase = "analyse"
                    review = await self._review(signals)
                    self._retain_external(review.feedback)
            feedback = review.feedback
        except Exception as exc:
            self._abort(exc, signals, step=phase)
            raise
        if self.history:
            self.history[-1] = mark(self.history[-1], feedback, self._acted(signals))
        acted = self._acted(signals)
        wanted = feedback.decision == "curate" or any(signal.attachments for signal in acted)
        for witness in self.verification:
            names = witness.get("sessions", ())
            current = {name: self.held_out[name] for name in names if name in self.held_out}
            if len(current) != len(names) or evidence_fingerprint(current) != witness["evidence"]:
                witness["error"] = "Held-out evidence changed after verification."
        self.record["promotion"] = promotion(
            revision=self._revision(),
            context=self._verification_context(),
            witnesses=self.verification,
            signals=acted,
            feedback=feedback,
            external_requirements=self.external_requirements,
        )
        if self.record["promotion"]["status"] == "accepted":
            self.record["stable_revision"] = self.record["promotion"]
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
        self.previous_signals, self.previous_feedback = acted, feedback
        # The round now holds its sessions and signals; only the review waits for the curation.
        self.sessions, self.signals, self.held_out, self.held_out_signals = {}, [], {}, []
        self.pending_holdout = None
        self.verification = []
        self.review = review
        if curated:
            self.outcome = Outcome("curate")
        elif feedback.decision == "stop":
            self.outcome = Outcome("stop", "the analyst stopped the run")
        elif not acted:
            self.outcome = Outcome("stop", "no assessor produced a signal")
        elif satisfied(acted):
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
        """Revise the Harness from the analysed round; False when the Curator pauses or reports a gap. A
        reported gap blocks the round unrevised with its question kept (see `_curate`).

        The Curator attributes the round's requirements before it changes anything; `attribution` supplies an
        attribution made elsewhere instead, such as diagnoses a person reviewed."""
        self._require(
            self.review is not None and self.outcome is not None and self.outcome.next == "curate",
            "curation follows an analysis that asked for it",
            resuming=True,
        )
        sessions, signals, feedback = (
            self.rounds[-1].sessions,
            self._acted(self.rounds[-1].signals),
            self.rounds[-1].feedback,
        )
        try:
            status = await self._curate(
                {
                    "signals": plain(heard(self._acted(signals))),
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
        if status == "blocked":
            self.rounds[-1] = replace(self.rounds[-1], curated=False)
            self.save()
            return False
        self.rounds[-1] = replace(self.rounds[-1], curated=True)
        curated = status == "done" and bool(self.rounds[-1].curation)
        if curated:
            self.record["promotion"] = {
                "status": "candidate",
                "revision": self._revision(),
                "reason": "The installed revision needs independent verification.",
            }
        self._close(
            plan=self.worker.last_plan if curated else None,
            attribution=self._last("attribution") if curated else None,
            selection=self._last("selection") if curated else None,
            children=self._last("children") if curated else None,
        )
        self.save()
        return True

    def resolve_gap(self, answer: str) -> None:
        """Supply new information for a blocked curation; the same round is retried with this answer on record."""
        if self.status != "blocked":
            raise StepError("there is no blocked curation to resolve")
        if not answer.strip():
            raise ValueError("a gap resolution must supply new information")
        self.record.setdefault("gap_resolutions", []).append(
            {"question": deepcopy(self.record["questions"][-1]), "answer": answer}
        )
        self.record["status"] = "running"
        self.record["gap_retry"] = self.record["questions"][-1]["round"]
        self.record.pop("stop", None)
        self.save()

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

    def retry_analysis(self) -> None:
        """`retry` held to a failed analysis."""
        self.retry("analyse")

    def retry(self, step: str | None = None) -> str:
        """Reopen the round whose analysis or assessment failed (`records.retryable_step`), or only that `step`, on
        the evidence it recorded, keeping the failed attempt beside the run; the step is returned for the person to
        take again. The trials, the person's own signals and the held-out exam stay; a failed assessment also drops
        the signals its assessors gave before it failed, so taking it again judges the round whole once."""
        found = retryable_step(plain(self.record))
        name = RETRYABLE.get(step, "analysis or assessment")
        if (
            found is None
            or step not in (None, found)
            or self.sessions
            or self.signals
            or self.held_out
            or self.review is not None
        ):
            raise StepError(f"only an unfinished failed {name} can be retried")
        failed = self.rounds[-1]
        revision = self._revision()
        executions = [exchange.execution for values in failed.sessions.values() for exchange in values]
        if not revision or not executions or any(execution.artifact_id != revision for execution in executions):
            raise StepError(f"the employee changed since the failed {RETRYABLE[found]}")
        if (
            self.record.get("error_revision", revision) != revision
            or self.record.get("error_context", self._verification_context()) != self._verification_context()
        ):
            raise StepError(f"the employee or requirements changed since the failed {RETRYABLE[found]}")
        failures = f"{RETRYABLE[found]}_failures"
        self.record.setdefault(failures, []).append(
            {
                "round": len(self.rounds),
                "error": self.record["error"],
                "error_step": self.record.get("error_step"),
                "error_context": self.record.get("error_context"),
                "revision": revision,
                "recovered_at": datetime.now(timezone.utc).isoformat(),
                "evidence_ref": f"iteration/{self.path.name}#/{failures}/{len(self.record[failures])}/failed_round",
                "failed_round": plain(failed),
            }
        )
        automatic = {getattr(assessor, "name", None) for assessor in self.assessors} if found == "assess" else set()
        self.rounds.pop()
        self.sessions = failed.sessions
        self.signals = [signal for signal in failed.signals if signal.source not in automatic]
        self.held_out, self.held_out_signals = failed.holdout, list(failed.holdout_signals)
        self.previous_signals = self._acted(self.rounds[-1].signals) if self.rounds else ()
        self.previous_feedback = self.rounds[-1].feedback if self.rounds else None
        self.pending_holdout, self.verification, self.outcome = None, [], None
        self.record["status"] = "running"
        for key in ("error", "error_step", "error_revision", "error_context", "stop"):
            self.record.pop(key, None)
        self.save()
        return found

    def _abort(self, exc, signals, *, step) -> None:
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
        self.record.update(error_step=step, error_revision=self._revision(), error_context=self._verification_context())
        self.sessions, self.signals, self.held_out, self.held_out_signals = {}, [], {}, []
        self.pending_holdout = None
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
        self.pending_holdout = None


@dataclass(frozen=True)
class _Pending:
    """The review of a resumed record's last round, whose curation had not completed."""

    feedback: Feedback
    activity: tuple = ()
