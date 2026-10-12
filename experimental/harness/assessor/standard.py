"""The evaluation side's standard and the automatic Assessor that holds each round to it.

A `Standard` retains three origins. Each criterion has one definition, a version-bound basis and a measurement plan:

- declared: the scenario's own checks, must_hold;
- derived: model-owned gates, guardrails and quality criteria constructed from the task and materials;
  explicit counterpart confirmation protects them as external requirements (`Standard.confirmed`);
- sedimented: every requirement raised so far, kept as a resident regression check with the requirement's own
  strength and original authority (`Standard.sedimented`), including when the counterpart is silent.

`Assessor` judges a round's sessions against the standard with a model and returns its verdicts as a `Signal`
for the Analyst to translate; it has no voice of its own. All applicable must_hold criteria need evidence of passing;
unknowns block acceptance and quality cannot offset a failure. Model gates do not establish independent promotion. The
loop hands it the history before each assessment (`sediment`). The standard is evaluation apparatus: its fields reach
the counterpart and the Analyst only, and the assessor runs in the Analyst's compartment when it is given the boundaries.
"""

import copy
import hashlib
import inspect
import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from contextlib import nullcontext
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from experimental.harness.assessor.checks import VERIFIERS, Finding, combine, program
from experimental.harness.assessor.rubric import (
    ORIGINS,
    Basis,
    Criterion,
    Definition,
    LLMCheck,
    Origin,
    Reference,
    digest,
)
from experimental.harness.contract.declaration import schema_for
from experimental.harness.curator.generation.context.render import tool
from experimental.harness.experience.governance import fingerprint
from experimental.harness.participation.allowance import excerpt, reading_budget
from experimental.harness.participation.audience import EVALUATION, Role, audience
from experimental.harness.participation.exchange import exchange, messages
from experimental.harness.participation.protocols import Item, Sessions, Signal
from experimental.harness.participation.requirements import ExternalRequirement
from experimental.harness.participation.views import actions, back_office, execution_digest, reports
from experimental.harness.raven_adapter.materialize import _write

if TYPE_CHECKING:
    from experimental.harness.assessor.builder import RubricBuilder
    from experimental.harness.assessor.guidance import GuidanceStore
    from experimental.harness.assessor.reviewer import MetaReviewer

Strength = Literal["must_hold", "should"]
SOURCES = ORIGINS
BASIS = {"declared": "check", "derived": "material", "sedimented": "requirement"}
NAME = "assessor"
JUDGE = "submit_verdicts"
PROMPTS = Path(__file__).resolve().parent / "prompts"
TEXT_FILES = frozenset({".md", ".txt", ".csv", ".json", ".yaml", ".yml", ".html"})
CHILD_ACTIONS = 60


@dataclass(frozen=True)
class Standard:
    """The criteria a round is held to, the counterpart's first; ids are unique across the sources."""

    criteria: tuple[Criterion, ...] = field(default=(), metadata=audience(*EVALUATION))

    def __post_init__(self):
        ids = [criterion.id for criterion in self.criteria]
        if len(ids) != len(set(ids)):
            raise ValueError(f"criterion ids must be unique: {sorted(id for id in ids if ids.count(id) > 1)}")
        parents = {criterion.id: criterion.parent_id for criterion in self.criteria}
        visited = set()
        for id in parents:
            path = set()
            while id is not None and id not in visited:
                if id not in parents:
                    raise ValueError(f"criterion parent {id!r} does not exist")
                if id in path:
                    raise ValueError("criterion parent relationships contain a cycle")
                path.add(id)
                id = parents[id]
            visited.update(path)

    @property
    def version(self) -> str:
        return digest([asdict(criterion) for criterion in self.criteria])

    def select(self, ids) -> "Standard":
        ids = set(ids)
        # A restricted evaluator must not import a hidden ancestor merely to display its tree.
        return Standard(
            tuple(
                replace(criterion, parent_id=None) if criterion.parent_id not in ids else criterion
                for criterion in self.criteria
                if criterion.id in ids
            )
        )

    @classmethod
    def declared(
        cls, checks: Iterable[tuple[str, str]], *, applies_when: Mapping[str, str] | None = None
    ) -> "Standard":
        """The scenario's checks, as (id, text) pairs, with their explicitly declared applicability conditions."""
        return cls(
            tuple(
                Criterion(
                    id,
                    Definition("Worker output and execution", text, (applies_when or {}).get(id, "")),
                    "declared",
                    "gate",
                    Basis((Reference(f"check:{id}", text, digest(text)),)),
                    authority="external",
                )
                for id, text in checks
            )
        )

    def of(self, *sources: Origin) -> "Standard":
        return self.select(criterion.id for criterion in self.criteria if criterion.origin in sources)

    def sedimented(self, history: Sequence[Mapping]) -> "Standard":
        """This standard with every requirement raised in `history` (entries as the Analyst reads them) as a
        regression check; a requirement raised again keeps its id and its latest wording."""
        raised: dict[str, Criterion] = {}
        for entry in history:
            for requirement in entry.get("requirements", ()):
                authority = requirement.get("authority", "model")
                previous = raised.get(requirement["id"])
                if previous is not None and previous.authority == "external" and authority != "external":
                    continue
                acceptance = requirement["behavior"]
                if requirement.get("acceptance") and requirement["acceptance"] not in acceptance:
                    acceptance += "\n" + requirement["acceptance"]
                raised[requirement["id"]] = Criterion(
                    requirement["id"],
                    Definition("Worker behavior", acceptance, requirement.get("situation", "")),
                    "sedimented",
                    "gate" if requirement.get("strength") == "must_hold" else "quality",
                    Basis(
                        (Reference(f"requirement:{requirement['id']}", requirement["behavior"], digest(requirement)),),
                        f"Raised in round {entry.get('round')}; grounds: {', '.join(requirement.get('grounds', ())) or 'unspecified'}",
                    ),
                    authority=authority,
                )
        kept = tuple(
            criterion
            for criterion in self.criteria
            if criterion.origin != "sedimented"
            or (
                criterion.authority == "external"
                and (criterion.id not in raised or raised[criterion.id].authority != "external")
            )
        )
        taken = {criterion.id for criterion in kept}
        return Standard((*kept, *(criterion for id, criterion in raised.items() if id not in taken)))

    def confirmed(self, ids: Iterable[str]) -> "Standard":
        """The counterpart confirmed these derived criteria: they now hold every time."""
        ids = set(ids)
        unknown = ids - {criterion.id for criterion in self.criteria if criterion.origin == "derived"}
        if unknown:
            raise ValueError(f"only derived criteria are confirmed; not derived: {sorted(unknown)}")
        return Standard(
            tuple(
                replace(
                    criterion,
                    kind="gate" if criterion.kind == "quality" else criterion.kind,
                    authority="external",
                )
                if criterion.id in ids
                else criterion
                for criterion in self.criteria
            )
        )


@dataclass(frozen=True)
class Decidability:
    """Whether the last judging could decide a derived criterion, and the assessor's note when it could not."""

    decided: bool
    note: str = ""


def decidability(items: Sequence[Item], standard: "Standard") -> dict[str, Decidability]:
    """Per derived criterion of `standard`, whether the round's verdicts decided it; never whether it passed."""
    derived = {criterion.id for criterion in standard.criteria if criterion.origin == "derived"}
    return {
        item.id: Decidability(item.result != "unknown", item.note if item.result == "unknown" else "")
        for item in items
        if item.id in derived
    }


class Verdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    result: Literal["pass", "fail", "unknown", "not_applicable"]
    session: str | None = Field(default=None, description="The session that decided the verdict, if one did.")
    actual: str = Field(default="", description="The assistant's words or file content the verdict rests on.")
    note: str = Field(default="", description="What should have happened instead, for a fail.")


class Verdicts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdicts: list[Verdict] = Field(min_length=1)


def satisfied(standard: Standard, items: Sequence[Item]) -> bool | None:
    """Hard failures win; every applicable hard criterion needs evidence before the standard can pass."""
    must = {criterion.id for criterion in standard.criteria if criterion.strength == "must_hold"}
    measured = [item for item in items if item.id in must]
    if any(item.result == "fail" for item in measured):
        return False
    if must - {item.id for item in measured}:
        return None
    applicable = [item.result for item in measured if item.result != "not_applicable"]
    return True if applicable and all(result == "pass" for result in applicable) else None


def _rate(items: Sequence[Item], ids: set[str]) -> float | None:
    judged = [item.result for item in items if item.id in ids and item.result in ("pass", "fail")]
    return sum(result == "pass" for result in judged) / len(judged) if judged else None


def _delivered(path: str, tokens: int) -> tuple[str, str]:
    file = Path(path)
    if file.suffix.lower() not in TEXT_FILES:
        return "", "This file format needs a dedicated verifier; its content is unavailable here."
    try:
        text = file.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return "", f"File content is unavailable: {type(exc).__name__}."
    shown = excerpt(text, tokens)
    return (
        shown,
        "" if shown == text else f"File content is cut to about {tokens} tokens; the cut says how much is left out.",
    )


def conversations(sessions: Sessions, *, tokens: int | None = None) -> dict[str, list[dict]]:
    """Each session as the assessor reads it: the user's messages, the assistant's replies, the text of any text
    file handed over with a reply (other files by name, each cut to `tokens`, by default the share of the host's
    default window that `experimental.harness.participation.allowance.reading_budget` gives), and why a reply never came, if it did not."""
    tokens = reading_budget() if tokens is None else tokens
    told = {}
    for name, exchanges in sessions.items():
        rows = []
        for exchange_ in exchanges:
            row = {"user": exchange_.user, "assistant": exchange_.assistant}
            files, unavailable = {}, {}
            for path in exchange_.execution.deliverables:
                filename = Path(path).name
                files[filename], reason = _delivered(path, tokens)
                if reason:
                    unavailable[filename] = reason
            if files:
                row["delivered"] = files
            if unavailable:
                row["unavailable"] = unavailable
            if exchange_.stopped:
                row["stopped"] = exchange_.stopped
            rows.append(row)
        told[name] = rows
    return told


def executions(sessions: Sessions) -> dict[str, list[dict]]:
    """Each turn's execution as a reviewer reads it (`experimental.cultivation.counterpart`): every action besides talking, in
    order and with whether it succeeded, what each colleague was asked and reported, the calls of any child harness
    the turn ran (`children`) and the files delivered. The raw records stay in the run's own record; a few drills
    hold tens of megabytes of them, past any model's input."""
    return {
        name: [
            {
                "turn_id": row.execution.turn_id,
                "actions": [
                    {key: value for key, value in action.items() if key != "turn"} for action in back_office([row])
                ],
                "reports": reports([row]),
                **({"children": ran} if (ran := children(row.execution.records)) else {}),
                "delivered": [Path(path).name for path in row.execution.deliverables],
            }
            for row in rows
        ]
        for name, rows in sessions.items()
    }


def children(records) -> list[dict]:
    """Each child harness execution in a turn's records: which harness ran and the calls it made in order, the first
    `CHILD_ACTIONS` of them with the rest counted in `omitted`, so what a colleague reported doing can be held to
    what it did without its whole record."""
    found = []
    for row in records:
        if row.get("kind") != "child.execution":
            continue
        made = actions(row.get("records") or ())
        child = {"harness": str(row.get("harness") or ""), "actions": made[:CHILD_ACTIONS]}
        if len(made) > CHILD_ACTIONS:
            child["omitted"] = len(made) - CHILD_ACTIONS
        found.append(child)
    return found


def observations(sessions: Sessions, task: str = "", *, tokens: int | None = None) -> dict:
    """The same retained evidence packet for judging, program checks and replay validation."""
    return {
        "task": task,
        "conversations": conversations(sessions, tokens=tokens),
        "executions": executions(sessions),
    }


def _checked(jobs, sessions: Sessions, arguments) -> Verdicts:
    verdicts = Verdicts.model_validate(arguments)
    expected = sorted(job["id"] for job in jobs)
    got = sorted(verdict.id for verdict in verdicts.verdicts)
    if got != expected:
        raise ValueError(f"give exactly one verdict per criterion; expected {expected}, got {got}")
    unknown = {verdict.session for verdict in verdicts.verdicts if verdict.session} - sessions.keys()
    if unknown:
        raise ValueError(f"verdicts name sessions that did not happen: {sorted(unknown)}")
    if any(verdict.result == "not_applicable" and not verdict.note.strip() for verdict in verdicts.verdicts):
        raise ValueError("not_applicable requires an evidenced explanation")
    return verdicts


class Assessor:
    """An Assessor that holds each round to a `Standard` with a model; see the module docstring.

    `sources` names which sources it keeps: the declared ones it is given, the derived ones its `builder` writes and
    revises before every assessment from the norms handed over so far (`norms`, a mapping or a callable returning one,
    read each time, so a norm handed over later is read from then) and the last judging's decidability, and the
    sedimented ones the loop hands it through `sediment`. `boundaries`, when given, run its model calls, the builder's
    included, in the Analyst's compartment (or the one `compartment` names: a judge of held-out cases sits on the
    evaluation side, the counterpart's, since those cases are sealed from the Analyst), sparing the round's user
    messages and the criteria it holds, which were vetted where they came from. With `keep`, its `record` is written there after every assessment, finished or not,
    so a run stopped between rounds keeps every revision and judging so far. `references`, when given, maps the
    sessions to the figures a case computes for each of them (and a labelled case's expected answer); they join the
    evidence the model judges with, the way an owner's facts join its review.
    `materials` supplies adopted supporting evidence without widening the builder's `norms`; each assessment
    retains the actual material text so a replay does not silently read a newer source.
    """

    def __init__(
        self,
        provider,
        standard: Standard = Standard(),
        *,
        sources: Iterable[Origin] = SOURCES,
        norms: Mapping[str, str] | Callable[[], Mapping[str, str]] | None = None,
        materials: Mapping[str, str] | Callable[[], Mapping[str, str]] | None = None,
        task: str = "",
        model=None,
        effort=None,
        max_calls=4,
        timeout=300,
        boundaries=None,
        compartment: Role = "analyst",
        name=NAME,
        builder: "RubricBuilder | None" = None,
        verifiers=None,
        calibrations=None,
        reviewer: "MetaReviewer | None" = None,
        guidance_store: "GuidanceStore | None" = None,
        validation_cases=(),
        repair_suites=None,
        replay_corpus=None,
        scope: str | None = None,
        keep: Path | None = None,
        references: Callable[[Sessions], Mapping[str, Mapping]] | None = None,
    ):
        self.sources = tuple(sources)
        self.references = references
        unknown = set(self.sources) - set(SOURCES)
        if unknown:
            raise ValueError(f"unknown sources: {sorted(unknown)}")
        if "derived" in self.sources and builder is None and not standard.of("derived").criteria:
            raise ValueError("the derived source needs a builder to write it")
        self.builder = builder
        self.task = task
        self.verifiers = dict(VERIFIERS if verifiers is None else verifiers)
        self.calibrations = dict(calibrations or {})
        self.assessments: list[dict] = []
        self.run_id = uuid4().hex
        self.reviewer = reviewer
        self.instructions = (PROMPTS / "assess.md").read_text()
        self.guidance_store = guidance_store
        self.guidance_usage = None
        self.validation_cases = tuple(validation_cases)
        self.repair_suites = dict(repair_suites or {})
        self.replay_corpus = replay_corpus
        self.validation_runs: dict[str, dict] = {}
        self.open_issues: dict[str, dict] = {}
        self.scope = scope or ("task:" + hashlib.sha256(task.encode()).hexdigest()[:16] if task else "task")
        self.evidence: dict[str, Decidability] = {}
        self.provider, self.standard = provider, standard.of(*self.sources)
        fixed = {} if norms is None or callable(norms) else dict(norms)
        self.norms = norms if callable(norms) else lambda: fixed
        supporting = {} if materials is None or callable(materials) else dict(materials)
        self.materials = materials if callable(materials) else lambda: supporting
        self.model, self.effort, self.max_calls, self.timeout = model, effort, max_calls, timeout
        self.boundaries, self.compartment, self.name, self.keep = boundaries, compartment, name, keep
        self.trace: list[dict] = []

    def restore(self) -> None:
        """Resume this host-owned record without fabricating authority for older criteria."""
        if self.keep is None or not self.keep.exists():
            return
        record = json.loads(self.keep.read_text())
        if record.get("task", self.task) != self.task:
            raise ValueError("the evaluation record belongs to another task")
        self.run_id = record.get("run_id", self.run_id)
        if record.get("schema") not in (2, 3):
            raise ValueError(
                "this saved rubric predates semantic contracts; it remains readable but must be rebuilt before execution"
            )
        self.standard = Standard(tuple(Criterion.read(row) for row in record["criteria"]))
        self.assessments = list(record.get("assessments", ()))
        self.trace = list(record.get("trace", ()))
        self.validation_runs = dict(record.get("validation_runs", {}))
        self.open_issues = {key: {**value, "allow": []} for key, value in record.get("open_issues", {}).items()}
        self.evidence = {key: Decidability(**value) for key, value in record.get("decidability", {}).items()}
        if self.builder is not None:
            current_instructions = self.builder.instructions
            self.builder.restore(record.get("rubric_builder", {}))
            if record["schema"] == 2 and self.builder.instructions != current_instructions:
                self.builder.runs.append(
                    {
                        "status": "protocol_updated",
                        "previous_instructions": self.builder.instructions,
                        "reason": "Semantic records were loaded as a flat forest; future construction uses the current protocol.",
                    }
                )
                self.builder.instructions = current_instructions
        if self.reviewer is not None:
            self.reviewer.restore(record.get("meta_reviewer", {}))

    def twin(self) -> "Assessor":
        """An assessor holding sessions to this very standard with records of its own, so twins may judge at once;
        `adopt` takes their records back. Only an assessor whose judging leaves its standard and review state as they
        are has twins: one without a builder, a reviewer or open review issues."""
        if self.builder is not None or self.reviewer is not None or self.open_issues:
            raise ValueError("an assessor that revises its standard while judging has no twins")
        twin = copy.copy(self)
        twin.assessments, twin.trace, twin.keep = [], [], None
        return twin

    def adopt(self, twins: Iterable["Assessor"]) -> None:
        """The twins' judging joins this assessor's record, numbered after its own, and is kept."""
        for twin in twins:
            self.trace.extend(twin.trace)
            for episode in twin.assessments:
                episode["id"] = f"{self.run_id}:assessment-{len(self.assessments) + 1}"
                episode["version"] = len(self.assessments) + 1
                self.assessments.append(episode)
        if self.keep is not None:
            _write(Path(self.keep), json.dumps(self.record(), ensure_ascii=False, indent=2).encode())

    def sediment(self, history: Sequence[Mapping]) -> None:
        """The loop's history so far, as the Analyst reads it."""
        if "sedimented" in self.sources:
            self.standard = self.standard.sedimented(history)

    def verification_policy(self) -> dict | None:
        """A fixed external rubric may verify held-out output; a self-generated rubric cannot certify itself."""
        if self.builder is not None or self.reviewer is not None or not self.standard.criteria:
            return None
        if any(criterion.authority != "external" for criterion in self.standard.criteria):
            return None
        return {
            "kind": "external_rubric",
            "task": self.task,
            "norms": dict(self.norms()),
            "materials": dict(self.materials()),
            "criteria": [asdict(criterion) for criterion in self.standard.criteria],
            "instructions": self.instructions,
            "model": self.model,
            "effort": self.effort,
            "verifiers": {
                name: f"{check.__module__}.{getattr(check, '__qualname__', type(check).__qualname__)}"
                for name, check in self.verifiers.items()
            },
            "calibrations": self.calibrations,
        }

    def constrain(self, requirements: Sequence[ExternalRequirement]) -> None:
        """Retain explicit external conditions even when this assessment selected only model-derived sources."""
        held = {criterion.id: criterion for criterion in self.standard.criteria}
        for requirement in requirements:
            held.setdefault(
                requirement.id,
                Criterion(
                    requirement.id,
                    Definition("Worker output and execution", requirement.quote, requirement.situation),
                    "sedimented",
                    requirement.kind,
                    Basis(
                        (
                            Reference(
                                f"external:{requirement.source}",
                                requirement.quote,
                                digest(requirement.model_dump(mode="json")),
                            ),
                        )
                    ),
                    authority="external",
                ),
            )
        self.standard = Standard(tuple(held.values()))

    async def assess_external(self, requirements: Sequence[ExternalRequirement], sessions: Sessions) -> Signal | None:
        """Check newly supplied requirements on the existing output, without another construction or review cycle."""
        self.constrain(requirements)
        ids = {requirement.id for requirement in requirements}
        evaluator = Assessor(
            self.provider,
            self.standard.select(ids),
            sources=("sedimented",),
            materials=self.materials,
            task=self.task,
            model=self.model,
            effort=self.effort,
            max_calls=self.max_calls,
            timeout=self.timeout,
            boundaries=self.boundaries,
            compartment=self.compartment,
            name=f"{self.name}.external",
            verifiers=self.verifiers,
            calibrations=self.calibrations,
        )
        try:
            return await evaluator.evaluate(sessions)
        finally:
            self.trace.extend(evaluator.trace)
            for episode in evaluator.assessments:
                episode["id"] = f"{self.run_id}:assessment-{len(self.assessments) + 1}"
                episode["version"] = len(self.assessments) + 1
                episode["reason"] = "external_requirement_update"
                self.assessments.append(episode)
            if self.keep is not None:
                _write(Path(self.keep), json.dumps(self.record(), ensure_ascii=False, indent=2).encode())

    def _scope(self, sessions: Sessions):
        if self.boundaries is None:
            return nullcontext(None)
        spoken = [tuple(exchange_.user for exchange_ in exchanges) for exchanges in sessions.values()]
        # A sedimented criterion is the Analyst's own requirement and a derived one restates a handed-over norm;
        # a declared one is a check, which the contract may seal from the Analyst, so it is never spared.
        handed = [
            text
            for criterion in self.standard.criteria
            if criterion.origin != "declared"
            for text in (
                criterion.definition.subject,
                criterion.definition.acceptance,
                criterion.definition.applies_when,
            )
            if text
        ]
        return self.boundaries.compartment(self.compartment, spoken=[*spoken, *handed])

    async def evaluate(self, sessions: Sessions) -> Signal | None:
        try:
            return await self._evaluate(sessions)
        finally:
            if self.keep is not None:
                _write(Path(self.keep), json.dumps(self.record(), ensure_ascii=False, indent=2).encode())

    async def _evaluate(self, sessions: Sessions) -> Signal | None:
        norms = dict(self.norms())
        if not sessions or not (norms or self.task or self.standard.criteria):
            return None
        with self._scope(sessions) as scope:
            provider = self.provider if scope is None else scope.provider(self.provider)
            if self.builder is not None and (norms or self.task):
                if self.guidance_store is not None:
                    guidance_inputs = fingerprint({"task": self.task, "norms": norms})
                    self.guidance_usage = self.guidance_store.capture(
                        self.scope, task=f"{fingerprint(self.task)}:{len(self.assessments)}", inputs=guidance_inputs
                    )
                    self.builder.guidance = self.guidance_usage["text"]
                baseline = self.standard
                candidate = await self.builder.revise(
                    provider,
                    norms,
                    self.standard,
                    self.evidence,
                    task=self.task,
                    verifiers={name: inspect.getdoc(check) or name for name, check in self.verifiers.items()},
                )
                if self.standard.version != baseline.version:
                    raise ValueError("the rubric changed during construction; the stale candidate was not installed")
                if self.guidance_store is not None:
                    self.guidance_store.validate_usage(self.guidance_usage, scope=self.scope, inputs=guidance_inputs)
                self.standard = candidate
            if not self.standard.criteria and self.reviewer is None and not (self.builder and self.builder.unresolved):
                return None
            items = await self._measure(provider, sessions)
            if self.reviewer is not None:
                items = await self._audit(provider, norms, sessions, items)
            elif self.open_issues:
                items = self._uncertain(
                    items,
                    {issue["criterion"]: issue["correction"] for issue in self.open_issues.values()},
                    self.assessments[-1],
                )
            if self.builder is not None and self.builder.unresolved:
                items = self._uncertain(items, self.builder.unresolved, self.assessments[-1])
        if self.builder is not None:
            measurement = next(
                (
                    row
                    for row in reversed(self.assessments)
                    if row["rubric_version"] == self.standard.version and "items" in row
                ),
                None,
            )
            # Pending construction and review uncertainty must not authorize unrelated checker edits.
            self.evidence = (
                decidability(tuple(Item(**row) for row in measurement["items"]), self.standard) if measurement else {}
            )
        criteria = {criterion.id: criterion for criterion in self.standard.criteria}
        must = {id for id, criterion in criteria.items() if criterion.strength == "must_hold"}
        rates = {"must_hold_pass_rate": _rate(items, must), "should_pass_rate": _rate(items, set(criteria) - must)}
        metrics = (
            {key: rate for key, rate in rates.items() if rate is not None}
            if not any(criterion.parent_id is not None for criterion in criteria.values())
            else {}
        )
        unresolved = (
            self.assessments[-1].get("blocking_unresolved")
            or self.assessments[-1].get("review_error")
            or any(item.strength == "must_hold" and item.result == "unknown" for item in items)
        )
        decision = satisfied(self.standard, items)
        return Signal(
            self.name,
            items=items,
            metrics=metrics,
            satisfied=None if unresolved and decision is not False else decision,
        )

    async def _audit(self, provider, norms, sessions, items):
        assessment = self.assessments[-1]
        measured = assessment
        baseline = self.standard
        if assessment["rubric_version"] != baseline.version:
            assessment["review_error"] = "The rubric changed during measurement; reevaluate the current version."
            return self._uncertain(items, {"": assessment["review_error"]}, assessment)
        before = {criterion.id: criterion for criterion in self.standard.criteria}
        failed = {
            row["criterion"] for row in assessment["checks"] if row["method"] == "program" and row["result"] == "fail"
        }
        failures = {item.id: item for item in items if item.id in failed}
        try:
            review = await self.reviewer.review(
                provider,
                task=self.task,
                norms=norms,
                assessment=assessment,
                history=(
                    self.guidance_store.review_history(self.scope, self.assessments[:-1])
                    if self.guidance_store is not None
                    else self.assessments[:-1]
                ),
                scope=self.scope,
                guidance=self.guidance_store.selected(self.scope) if self.guidance_store is not None else (),
                open_issues=tuple(self.open_issues.values()),
                open_guidance_issues=self.guidance_store.open_issues(self.scope)
                if self.guidance_store is not None
                else (),
            )
        except Exception as exc:
            assessment["review_error"] = str(exc)
            return self._uncertain(
                items,
                {
                    "": "Meta review could not complete.",
                    **{item.id: "Meta review could not complete." for item in items},
                },
                measured,
            )
        assessment["review"] = review.model_dump(mode="json")
        if self.standard.version != baseline.version:
            assessment["review_error"] = "The rubric changed during review; stale repair permissions were refused."
            return self._uncertain(items, {"": assessment["review_error"]}, assessment)
        for issue in review.issues:
            key = f"{issue.criterion}:{issue.target}"
            episode = self.open_issues.get(key, {}).get("episode", issue.episode)
            self.open_issues[key] = {**issue.model_dump(mode="json"), "episode": episode}
        if self.guidance_store is not None and self.builder is not None:
            try:
                await self.guidance_store.consider(
                    review.guidance,
                    diagnoses=review.guidance_issues,
                    episodes=self.assessments,
                    scope=self.scope,
                    task=self.task,
                    cases=self.replay_corpus.cases() if self.replay_corpus is not None else self.validation_cases,
                    evaluate=self._replay,
                )
            except Exception as exc:
                assessment["learning_error"] = str(exc)
        corrections = tuple(issue for issue in review.issues if issue.target != "evidence" and issue.allow)
        candidate = None
        if corrections and self.builder is not None:
            try:
                candidate = await self.builder.revise(
                    provider,
                    norms,
                    self.standard,
                    decidability(items, self.standard),
                    task=self.task,
                    corrections=corrections,
                    verifiers={name: inspect.getdoc(check) or name for name, check in self.verifiers.items()},
                )
                if self.standard.version != baseline.version:
                    raise ValueError("the rubric changed during repair; the stale candidate was not installed")
                self.standard = candidate
                if self.standard.criteria != tuple(before.values()):
                    items = await self._measure(provider, sessions, evidence=assessment["evidence"], norms=norms)
                    measured = self.assessments[-1]
            except Exception as exc:
                if candidate is not None and self.standard.version == candidate.version:
                    self.standard = baseline
                assessment["repair_error"] = str(exc)
                if self.assessments[-1] is not assessment:
                    self.assessments[-1]["error"] = str(exc)
        validated = set()
        if self.standard.version not in {
            baseline.version,
            candidate.version if candidate is not None else baseline.version,
        }:
            measured["repair_error"] = "The rubric changed during repair; the concurrent version was preserved."
            return self._uncertain(items, {"": measured["repair_error"]}, measured)
        repair_version = self.standard.version
        episodes = {row["id"]: row for row in self.assessments}
        for issue in self.open_issues.values():
            target = issue["criterion"]
            original = episodes.get(issue["episode"])
            if original is None:
                continue
            if issue["target"] == "evidence" and original.get("evidence_gaps", {}).get(target):
                previous = next((c for c in original["criteria"] if c["id"] == target), None)
                current = next((asdict(c) for c in self.standard.criteria if c.id == target), None)
                if (
                    previous is not None
                    and current is not None
                    and digest(asdict(Criterion.read(previous))) == digest(current)
                    and not measured.get("evidence_gaps", {}).get(target)
                    and any(item.id == target and item.result in ("pass", "fail") for item in items)
                ):
                    measured.setdefault("evidence_restored", []).append(target)
                    validated.add(target)
            reference = Standard(tuple(Criterion.read(row) for row in original["criteria"]))
            removed = next((c for c in reference.criteria if c.id == target), None)
            if (
                removed is not None
                and target not in failures
                and self.standard.criteria == tuple(c for c in reference.criteria if c.id != target)
            ):
                equivalent = next((c for c in self.standard.criteria if replace(c, id=target) == removed), None)
                if equivalent is not None:
                    measured.setdefault("repair_validation", {})[target] = {
                        "accepted": True,
                        "kind": "equivalent_duplicate_removal",
                        "witness": equivalent.id,
                        "baseline": reference.version,
                        "candidate": self.standard.version,
                    }
                    validated.add(target)
            if target in self.repair_suites and target not in validated and reference.version != self.standard.version:
                if issue["target"] == "check" and self.repair_suites[target].criterion != target:
                    measured["repair_error"] = (
                        "A checker defect needs an oracle for that criterion, not a whole-task label."
                    )
                    continue
                related = {target}
                for tree in (reference, self.standard):
                    parents = {c.id: c.parent_id for c in tree.criteria}
                    ancestor = parents.get(target)
                    while ancestor is not None:
                        related.add(ancestor)
                        ancestor = parents.get(ancestor)
                if target and self.repair_suites[target].criterion not in {*related, None}:
                    measured["repair_error"] = (
                        "Repair verification must cover the affected property or its parent scope."
                    )
                    continue
                receipt = await self._validate_repair(target, reference, self.standard)
                measured.setdefault("repair_validation", {})[target] = receipt
                if receipt["accepted"]:
                    validated.add(target)
        if self.standard.version != repair_version:
            measured["repair_error"] = "The rubric changed during validation; no repair receipt was adopted."
            return self._uncertain(items, {"": measured["repair_error"]}, measured)
        if failures:
            current = {item.id: item for item in items}
            if any(id not in validated and (id not in current or current[id].result != "fail") for id in failures):
                self.standard = baseline
                items = tuple(Item(**row) for row in assessment["items"])
                validated.clear()
                measured["repair_rejected"] = "A repair cannot erase an independently observed program failure."
                if self.builder is not None:
                    self.builder.pending = []
                    self.builder.pending_version = baseline.version
            measured["retained_program_failures"] = [id for id in failures if id not in validated]
            measured["final_items"] = [asdict(item) for item in items]
        self.open_issues = {
            key: issue for key, issue in self.open_issues.items() if issue["criterion"] not in validated
        }
        unresolved = {issue["criterion"]: issue["correction"] for issue in self.open_issues.values()}
        if self.standard != baseline and not validated:
            measured["repair_status"] = "candidate"
        return self._uncertain(items, unresolved, measured)

    async def _validate_repair(self, target, before, after):
        from experimental.harness.assessor.validation import ReplayEvaluation, _snapshot, compare, fingerprint

        versions = {before.version: before, after.version: after}
        suite = self.repair_suites[target]
        signature = fingerprint(_snapshot(suite.cases))
        for episode in reversed(self.assessments):
            receipt = episode.get("repair_validation", {}).get(target)
            if receipt and (
                receipt["baseline"],
                receipt["candidate"],
                receipt.get("suite"),
                receipt.get("property"),
            ) == (
                before.version,
                after.version,
                signature,
                suite.criterion,
            ):
                return receipt

        async def evaluate(version, case):
            standard = versions[version]
            if suite.criterion is not None:
                ids = {suite.criterion}
                while additions := {c.id for c in standard.criteria if c.parent_id in ids} - ids:
                    ids.update(additions)
                standard = standard.select(ids)
            if not standard.criteria:
                id = self._keep_validation(
                    "repair",
                    {
                        "case": case.id,
                        "rubric_version": version,
                        "target": target,
                        "property": suite.criterion,
                        "error": "The verification property has no remaining criterion.",
                    },
                )
                return ReplayEvaluation(None, id)
            evaluator = Assessor(
                self.provider,
                standard,
                sources={c.origin for c in standard.criteria},
                task=case.task,
                norms=case.norms,
                model=self.model,
                effort=self.effort,
                max_calls=self.max_calls,
                timeout=self.timeout,
                boundaries=self.boundaries,
                compartment=self.compartment,
                verifiers=self.verifiers,
                calibrations=self.calibrations,
            )
            signal = await evaluator.evaluate(case.sessions)
            record = {
                "case": case.id,
                "target": target,
                "property": suite.criterion,
                "rubric_version": version,
                "evaluation": evaluator.record(),
            }
            id = self._keep_validation("repair", record)
            decision = signal.satisfied if signal is not None else None
            if suite.criterion is not None and signal is not None:
                results = [item.result for item in signal.items if item.result != "not_applicable"]
                decision = (
                    False if "fail" in results else True if results and all(r == "pass" for r in results) else None
                )
            return ReplayEvaluation(decision, id)

        result = await compare(
            candidate=after.version,
            baseline=before.version,
            before=before.version,
            after=after.version,
            cases=suite.cases,
            evaluate=evaluate,
        )
        return {
            **result.record(),
            "property": suite.criterion,
            "accepted": result.accepted and all(row.after == row.expected for row in result.comparisons),
        }

    async def _replay(self, instructions, case):
        from experimental.harness.assessor.validation import ReplayEvaluation

        builder = replace(
            self.builder,
            guidance=instructions,
            read={},
            versions=[],
            trace=[],
            pending=[],
            pending_version="",
            inputs="",
            attempted={},
            runs=[],
        )
        assessor = Assessor(
            self.provider,
            task=case.task,
            norms=case.norms,
            builder=builder,
            model=self.model,
            effort=self.effort,
            max_calls=self.max_calls,
            timeout=self.timeout,
            verifiers=self.verifiers,
            calibrations=self.calibrations,
            boundaries=self.boundaries,
            compartment=self.compartment,
        )
        decision, error = None, None
        try:
            signal = await assessor.evaluate(case.sessions)
            decision = signal.satisfied if signal is not None else None
        except Exception as exc:
            error = str(exc)
        record = {"case": case.id, "task": case.task, "norms": case.norms, "evaluation": assessor.record()}
        if error is not None:
            record["error"] = error
        return ReplayEvaluation(decision, self._keep_validation("validation", record))

    def _keep_validation(self, prefix, record):
        from experimental.harness.assessor.validation import fingerprint

        id = prefix + "-" + fingerprint(record)
        root = (
            self.keep.parent
            if self.keep is not None
            else (
                self.guidance_store.path.parent
                if self.guidance_store is not None and self.guidance_store.path is not None
                else None
            )
        )
        if root is not None:
            path = root / "evaluation-validation" / f"{id}.json"
            _write(path, json.dumps(record, ensure_ascii=False, indent=2).encode())
            self.validation_runs[id] = {"path": str(path)}
        else:
            self.validation_runs[id] = record
        return id

    def _uncertain(self, items, unresolved, assessment):
        unresolved = {**assessment.get("unresolved", {}), **unresolved}
        optional = {criterion.id for criterion in self.standard.criteria if criterion.kind == "quality"}
        episodes = {row["id"]: row for row in self.assessments}
        for issue in self.open_issues.values():
            original = episodes.get(issue["episode"], {})
            previous = next((row for row in original.get("criteria", ()) if row["id"] == issue["criterion"]), None)
            if previous is not None:
                if previous["kind"] != "quality":
                    optional.discard(issue["criterion"])
                elif not any(c.id == issue["criterion"] and c.kind != "quality" for c in self.standard.criteria):
                    optional.add(issue["criterion"])
        blocking = bool(set(unresolved) - optional)
        failed_programs = {
            row["criterion"] for row in assessment["checks"] if row["method"] == "program" and row["result"] == "fail"
        } | set(assessment.get("retained_program_failures", ()))
        final = tuple(
            replace(item, result="unknown", note=f"Evaluation review unresolved: {unresolved[item.id]}")
            if item.id in unresolved and item.id not in failed_programs
            else item
            for item in items
        )
        existing = {item.id for item in final}
        if blocking and f"{self.name}:review" not in existing:
            final = (
                *final,
                Item(
                    f"{self.name}:review",
                    "unknown",
                    expected="Evaluation issues must be resolved before adoption.",
                    note="An evaluation defect remains unresolved; this is not evidence of a worker defect.",
                    strength="must_hold",
                ),
            )
        assessment["unresolved"] = unresolved
        assessment["blocking_unresolved"] = blocking
        assessment["final_items"] = [asdict(item) for item in final]
        return final

    def _evidence_gaps(self, criterion, evidence, norms) -> tuple[list[str], list[str]]:
        """What keeps `criterion` from being judged, and notes on how its evidence requirements were read.

        A delivered_text reference locates a file by the name it was delivered under, or by the path of a file a
        session left behind (`references[session]["filed"]`, when the case supplies them). A reference that locates
        neither, a description of the files or a name the worker never used, is judged against all delivered text
        with a note saying so: whether a required file is missing is part of the judgment, not a gap in the evidence.
        Only having neither delivered nor filed text, or a located file that cannot be read, is a gap.
        """
        gaps, notes = [], []
        supplied = {**evidence.get("materials", {}), **norms}
        rows = [row for turns in evidence["conversations"].values() for row in turns]
        filed = {
            path
            for found in evidence.get("references", {}).values()
            if isinstance(found, Mapping) and isinstance(found.get("filed"), Mapping)
            for path in found["filed"]
        }
        for need in criterion.assessment.evidence_requirements:
            if need.kind == "material" and need.reference not in supplied:
                gaps.append(f"Required material {need.reference!r} is unavailable.")
            elif need.kind == "delivered_text":
                files = {name: text for row in rows for name, text in row.get("delivered", {}).items()}
                unavailable = {name: reason for row in rows for name, reason in row.get("unavailable", {}).items()}
                reference = need.reference
                if reference and reference not in files:
                    if any(path == reference or path.endswith("/" + reference) for path in filed):
                        continue
                    notes.append(
                        f"Evidence reference {reference!r} names no delivered or filed file; judged against all "
                        + ("delivered text and filed files." if filed else "delivered text.")
                    )
                    reference = ""
                wanted = [reference] if reference else list(files)
                if not wanted and not filed:
                    gaps.append("No delivered text is available for this content judgment.")
                gaps.extend(f"{name}: {unavailable[name]}" for name in wanted if name in unavailable)
            elif need.kind == "conversation" and not rows:
                gaps.append("Conversation evidence is unavailable.")
            elif need.kind == "execution" and not any(evidence["executions"].values()):
                gaps.append("Execution evidence is unavailable.")
        for ref in criterion.basis.references:
            if criterion.origin == "derived" and (ref.source not in norms or ref.version != digest(norms[ref.source])):
                gaps.append(f"Source {ref.source!r} changed or is unavailable; rebuild its interpretation.")
        return gaps, notes

    async def _measure(self, provider, sessions: Sessions, *, evidence=None, norms=None) -> tuple[Item, ...]:
        standard = self.standard
        if evidence is not None:
            evidence = copy.deepcopy(evidence)
        else:
            evidence = observations(sessions, self.task)
            computed = self.references(sessions) if self.references is not None else {}
            figures = {name: dict(found) for name, found in computed.items() if found}
            if figures:
                evidence["references"] = figures
        norms = dict(self.norms() if norms is None else norms)
        if self.task:
            norms = {"$task": self.task, **norms}
        if "materials" not in evidence:
            evidence["materials"] = copy.deepcopy({**self.materials(), **norms})
        record = {
            "id": f"{self.run_id}:assessment-{len(self.assessments) + 1}",
            "version": len(self.assessments) + 1,
            "rubric_version": standard.version,
            "criteria": [asdict(criterion) for criterion in standard.criteria],
            "evidence": evidence,
            "evidence_digest": digest(evidence),
            "execution_digest": execution_digest(sessions),
            "guidance": self.builder.guidance if self.builder is not None else "",
            "guidance_usage": self.guidance_usage,
            "checks": [],
            "construction": {"pending": self.builder.unresolved} if self.builder is not None else {},
        }
        self.assessments.append(record)
        jobs, checks, gaps, notes = [], {}, {}, {}
        for criterion in standard.criteria:
            gaps[criterion.id], notes[criterion.id] = self._evidence_gaps(criterion, evidence, norms)
            checks[criterion.id] = [
                (criterion.id, "decision", criterion.assessment.decision),
                *(
                    (f"{criterion.id}:required-{i}", "required", check)
                    for i, check in enumerate(criterion.assessment.required_checks, 1)
                ),
            ]
            for id, role, check in checks[criterion.id]:
                if isinstance(check, LLMCheck):
                    jobs.append(
                        {
                            "id": id,
                            "criterion": criterion.id,
                            "role": role,
                            "definition": asdict(criterion.definition),
                            "kind": criterion.kind,
                            "parent_id": criterion.parent_id,
                            "basis": asdict(criterion.basis),
                            "evidence_requirements": [
                                asdict(need) for need in criterion.assessment.evidence_requirements
                            ],
                            "evidence_gaps": gaps[criterion.id],
                            "evidence_notes": notes[criterion.id],
                            "instruction": check.instruction,
                        }
                    )
        record["evidence_gaps"] = gaps
        record["evidence_notes"] = {id: found for id, found in notes.items() if found}
        if len({job["id"] for job in jobs}) != len(jobs):
            raise ValueError("criterion ids collide with generated local-check ids")
        judged = {}
        if jobs:
            _, verdicts = await exchange(
                provider,
                messages(self.instructions, {**evidence, "criteria": jobs}),
                [tool(JUDGE, "Submit one verdict per requested check id.", schema_for(Verdicts))],
                submit={JUDGE: lambda arguments: _checked(jobs, sessions, arguments)},
                model=self.model,
                effort=self.effort,
                max_calls=self.max_calls,
                timeout=self.timeout,
                trace=self.trace,
                label="assessor",
            )
            judged = {
                verdict.id: Finding(verdict.result, verdict.actual, verdict.note, verdict.session)
                for verdict in verdicts.verdicts
            }
        items, programs = [], 0
        for criterion in standard.criteria:
            findings = []
            for id, role, check in checks[criterion.id]:
                if check is None:
                    finding = Finding(
                        "unknown",
                        note="No whole-criterion decision method is configured; local passes are insufficient.",
                    )
                elif isinstance(check, LLMCheck):
                    finding = judged[id]
                    if finding.result == "not_applicable" and not criterion.definition.applies_when:
                        finding = Finding("unknown", note="An unconditional criterion cannot be marked not_applicable.")
                    stale = criterion.origin == "derived" and any(
                        ref.source not in norms or ref.version != digest(norms[ref.source])
                        for ref in criterion.basis.references
                    )
                    # A violation seen in the evidence at hand stands despite a gap elsewhere; a stale source
                    # leaves no current interpretation to have been violated.
                    if gaps[criterion.id] and finding.result == "fail" and not stale:
                        finding = replace(finding, note="\n".join(filter(None, (finding.note, *gaps[criterion.id]))))
                    elif gaps[criterion.id] and (finding.result != "not_applicable" or stale):
                        finding = Finding("unknown", note="; ".join(gaps[criterion.id]))
                elif gaps[criterion.id]:
                    finding = Finding("unknown", note="; ".join(gaps[criterion.id]))
                else:
                    programs += 1
                    finding = (
                        await program(
                            evidence,
                            verifier=check.verifier,
                            expression_source=check.expression,
                            verifiers=self.verifiers,
                            examples=self.calibrations.get(criterion.calibration_key(check), ()),
                            complete=role == "decision",
                        )
                        if programs <= 16
                        else Finding("unknown", note="Program check budget exhausted.")
                    )
                findings.append(finding)
                record["checks"].append(
                    {
                        "criterion": criterion.id,
                        "check": id,
                        "role": role,
                        **(asdict(check) if check is not None else {"method": "missing"}),
                        **asdict(finding),
                    }
                )
            result = combine(findings)
            items.append(
                Item(
                    criterion.id,
                    result.result,
                    result.session,
                    criterion.definition.acceptance,
                    result.actual,
                    "\n".join(filter(None, (result.note, *notes[criterion.id]))),
                    BASIS[criterion.origin],
                    criterion.authority,
                    criterion.strength,
                    criterion.parent_id,
                )
            )
        record["items"] = [asdict(item) for item in items]
        return tuple(items)

    def record(self) -> dict:
        """The standard as it stands, the trace of its judging calls and, with a builder, the builder's revisions."""
        return {
            "schema": 3,
            "open_issues": copy.deepcopy(self.open_issues),
            "run_id": self.run_id,
            "task": self.task,
            "decidability": {key: asdict(value) for key, value in self.evidence.items()},
            "criteria": [asdict(criterion) for criterion in self.standard.criteria],
            "trace": list(self.trace),
            "assessments": list(self.assessments),
            "validation_runs": dict(self.validation_runs),
            **({"meta_reviewer": self.reviewer.record()} if self.reviewer is not None else {}),
            **({"guidance": self.guidance_store.record()} if self.guidance_store is not None else {}),
            **({"rubric_builder": self.builder.record()} if self.builder is not None else {}),
        }
