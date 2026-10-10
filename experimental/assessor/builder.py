"""Construct grounded rubric forests with bounded, host-authorized revisions.

New source requirements, fresh undecidability or reviewer diagnoses determine the permitted patch scope. Model
responses never expand that scope by naming another reason. Parent relationships, source bindings and complete
candidate patches are validated before application. Ordinary construction sees decidability; corrective work can
inspect the review evidence. Pending refinement tasks and every applied or refused construction run are retained.
"""

import asyncio
import copy
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, replace
from itertools import cycle
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from experimental.assessor.revision import Permission, RevisionScope
from experimental.assessor.rubric import AssessmentPlan, Basis, Criterion, Definition, digest
from experimental.assessor.standard import Decidability, Standard
from experimental.curator.generation.context.render import tool
from experimental.curator.harness.declaration import schema_for
from experimental.iteration.exchange import ExchangeError, exchange, messages
from experimental.requirements import CriterionKind

PROMPT = Path(__file__).resolve().parent / "prompts" / "builder.md"
REVISE = "submit_revision"
QUOTE_MINIMUM = 6
# Quotation marks a model swaps freely when it copies a passage (single for double, curly for straight, corner brackets
# for either); every one compares as the same mark on both sides, so a quote is refused for its words and never for its
# quotation-mark style.
QUOTE_MARKS = str.maketrans(
    dict.fromkeys("'\u201c\u201d\u201e\u201f\u00ab\u00bb\u300c\u300d\u2018\u2019\u201a\u201b\u300e\u300f", '"')
    | dict.fromkeys("*`|")
)
# Markdown a model drops when it copies a passage out of a norm: a line's list, heading or quote marker and its
# checkbox; with the emphasis, code and table marks above, a quote is compared for its words, not its layout.
LINE_MARKUP = re.compile(r"^[ \t]*(?:[-+]\s+|\d+[.)]\s+|#+\s+|>\s*)?(?:\[[ xX]\]\s*)?", re.MULTILINE)

AddReason = Literal["new_norm", "uncovered", "review"]
RewriteReason = Literal["new_norm", "undecided", "imprecise", "beyond_norm", "review"]
RemoveReason = Literal["undecided", "duplicate", "beyond_norm", "review"]


class Drafted(BaseModel):
    """A criterion as the builder writes it, with the norm passage it rests on."""

    model_config = ConfigDict(extra="forbid")

    definition: Definition
    basis: Basis
    kind: CriterionKind
    assessment: AssessmentPlan
    parent_id: str | None = None


class Change(BaseModel):
    """One change to the derived criteria and its cause."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["add", "rewrite", "remove"]
    id: str | None = Field(default=None, description="The derived criterion rewritten or removed; none for add.")
    criterion: Drafted | None = Field(default=None, description="The criterion added, or the rewritten one whole.")
    reason: Literal["new_norm", "uncovered", "undecided", "imprecise", "beyond_norm", "duplicate", "review"]
    explanation: str = Field(min_length=1, description="Why, in terms of the norm and the evidence given.")
    refine: str = Field(
        default="", description="Why this resulting node needs a subsequent local refinement; empty stops."
    )

    @model_validator(mode="after")
    def _shape(self) -> "Change":
        allowed = {"add": AddReason, "rewrite": RewriteReason, "remove": RemoveReason}[self.op].__args__
        if self.reason not in allowed:
            raise ValueError(f"{self.op} takes a reason among {list(allowed)}, not {self.reason!r}")
        if self.op == "add" and (self.id is not None or self.criterion is None):
            raise ValueError("add gives a criterion and no id")
        if self.op == "rewrite" and (self.id is None or self.criterion is None):
            raise ValueError("rewrite names the id and gives the rewritten criterion")
        if self.op == "remove" and (self.id is None or self.criterion is not None):
            raise ValueError("remove names the id and gives no criterion")
        if self.op == "remove" and self.refine:
            raise ValueError("a removed criterion cannot be queued for refinement")
        return self


class Unchecked(BaseModel):
    model_config = ConfigDict(extra="forbid")

    material: str
    section: str = ""
    reason: str = Field(
        min_length=1,
        description="Why no criterion checks it: not a rule, not visible in records, or a held criterion checks it.",
    )


class Revision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    changes: list[Change] = Field(default_factory=list)
    unchecked: list[Unchecked] = Field(default_factory=list)
    note: str = Field(default="", description="Why this target can stop or why no evidenced change is needed.")


def _flat(text: str) -> str:
    return " ".join(LINE_MARKUP.sub("", unicodedata.normalize("NFKC", text)).translate(QUOTE_MARKS).split())


def _shown(text: str) -> str:
    """`text` as the builder reads it: each line's straight double quotes as curly pairs.

    The builder copies norm passages verbatim into its tool arguments, and a straight double quote copied into a JSON
    string has to be escaped; models drop the escape often enough to break every attempt of a revision. Curly marks
    need no escape, and `_flat` compares every quotation mark as the same one, so grounding is unchanged.
    """
    return "\n".join(re.sub('"', lambda _, marks=cycle("\u201c\u201d"): next(marks), line) for line in text.split("\n"))


def _grounded(drafted: Drafted, norms: Mapping[str, str]) -> str | None:
    """Validate quotations and references; semantic entailment remains a review responsibility."""
    for ref in drafted.basis.references:
        if ref.version:
            return "source versions are assigned by the host"
        if ref.source not in norms:
            return f"criteria may come only from the norms given {sorted(norms)}; got {ref.source!r}"
        quote = _flat(ref.quote)
        if ref.quote and len(quote) < QUOTE_MINIMUM:
            return f"quote the passage of {ref.source!r}, at least {QUOTE_MINIMUM} characters"
        if ref.quote and quote not in _flat(norms[ref.source]):
            return f"the quote is not in {ref.source!r} verbatim: {ref.quote[:120]!r}"
    for need in drafted.assessment.evidence_requirements:
        if need.kind == "material" and need.reference not in norms:
            return f"required material evidence is not supplied: {need.reference!r}"
    return None


def _bound(basis: Basis, norms: Mapping[str, str]) -> Basis:
    return replace(basis, references=tuple(replace(ref, version=digest(norms[ref.source])) for ref in basis.references))


def _target_state(standard, target):
    if not target:
        return standard.version
    criteria = {criterion.id: criterion for criterion in standard.criteria}
    if target not in criteria:
        return None
    lineage = []
    while target is not None:
        lineage.append(asdict(criteria[target]))
        target = criteria[target].parent_id
    return digest(lineage)


@dataclass
class RubricBuilder:
    """A bounded queue of local construction work, executed in the assessor's compartment."""

    model: str | None = None
    effort: str | None = None
    max_calls: int = 4
    max_nodes: int = 16
    timeout: float = 300
    instructions: str = field(default_factory=PROMPT.read_text)
    guidance: str = ""
    read: dict[str, str] = field(default_factory=dict)
    versions: list[dict] = field(default_factory=list)
    trace: list[dict] = field(default_factory=list)
    pending: list[dict] = field(default_factory=list)
    pending_version: str = ""
    inputs: str = ""
    attempted: dict[str, str] = field(default_factory=dict)
    runs: list[dict] = field(default_factory=list)

    @property
    def unresolved(self):
        return {work["target"]: work["reason"] or "Construction remains unfinished." for work in self.pending}

    def _permissions(self, norms, standard, evidence, corrections=()):
        if corrections:
            return tuple(permission for issue in corrections for permission in issue.allow)
        fresh = {name for name, value in norms.items() if self.read.get(name) != digest(value)}
        allow = [Permission(op="add")] if fresh else []
        for criterion in standard.criteria:
            if criterion.origin != "derived" or criterion.authority == "external":
                continue
            if {ref.source for ref in criterion.basis.references} & fresh:
                allow.extend(
                    (
                        Permission(op="rewrite", id=criterion.id, fields=("definition", "basis", "assessment", "kind")),
                        Permission(op="add", parent_id=criterion.id),
                    )
                )
            elif not evidence.get(criterion.id, Decidability(True)).decided:
                allow.append(Permission(op="rewrite", id=criterion.id, fields=("assessment",)))
        return tuple(allow)

    def _check(
        self,
        revision: Revision,
        norms,
        standard: Standard,
        evidence: Mapping[str, Decidability],
        corrections=(),
        *,
        scope: RevisionScope | None = None,
    ) -> Revision:
        scope = scope or RevisionScope.bind(standard, norms, self._permissions(norms, standard, evidence, corrections))
        scope.check_base(standard, norms)
        derived = {criterion.id: criterion for criterion in standard.criteria if criterion.origin == "derived"}
        fresh = {name for name, text in norms.items() if self.read.get(name) != digest(text)}
        problems, touched = [], set()
        for number, change in enumerate(revision.changes, 1):
            where = f"change {number}"
            reviewed = {issue.criterion for issue in corrections or ()}
            target = change.id if change.id is not None else (change.criterion.parent_id or "")
            if change.reason == "review" and target not in reviewed:
                problems.append(f"{where}: review requires a supplied correction for this criterion")
            if change.id is not None:
                if change.id not in derived:
                    problems.append(f"{where}: {change.id!r} is not a derived criterion; derived are {sorted(derived)}")
                    continue
                if derived[change.id].authority == "external":
                    problems.append(f"{where}: {change.id!r} is a protected external requirement")
                    continue
                if derived[change.id].strength == "must_hold" and change.reason in ("undecided", "imprecise"):
                    if change.op == "remove" or (change.criterion and change.criterion.kind == "quality"):
                        problems.append(f"{where}: missing evidence cannot remove or weaken a required condition")
                if change.id in touched:
                    problems.append(f"{where}: {change.id!r} is changed twice")
                touched.add(change.id)
            refused = _grounded(change.criterion, norms) if change.criterion is not None else None
            if refused:
                problems.append(f"{where}: {refused}")
            if change.criterion is not None:
                parent = change.criterion.parent_id
                if parent is not None and parent not in {criterion.id for criterion in standard.criteria}:
                    problems.append(f"{where}: the parent must exist in the patch's base version")
            if (
                change.reason == "new_norm"
                and change.criterion
                and not {ref.source for ref in change.criterion.basis.references} & fresh
            ):
                problems.append(f"{where}: new_norm applies only to a norm handed over since the last revision")
            if change.reason == "undecided" and evidence.get(change.id, Decidability(True)).decided:
                problems.append(f"{where}: {change.id!r} was decided in the last round, so undecided is no cause")
            if change.op == "rewrite" and change.criterion and change.id in derived and not refused:
                before = derived[change.id]
                if (before.definition, before.kind, before.assessment, before.basis, before.parent_id) == (
                    change.criterion.definition,
                    change.criterion.kind,
                    change.criterion.assessment,
                    _bound(change.criterion.basis, norms),
                    change.criterion.parent_id,
                ):
                    problems.append(f"{where}: the rewrite of {change.id!r} changes nothing")
        stray = {item.material for item in revision.unchecked} - set(norms)
        if stray:
            problems.append(f"unchecked names norms that were not given: {sorted(stray)}")
        drawn = {
            ref.source
            for change in revision.changes
            if change.criterion is not None
            for ref in change.criterion.basis.references
        }
        if silent := sorted(fresh - drawn - {item.material for item in revision.unchecked}):
            problems.append(
                f"each norm in new_norms needs a criterion drawn from it or an unchecked entry saying why none: {silent}"
            )
        if problems:
            raise ValueError("; ".join(problems))
        if not revision.changes and not revision.unchecked and not revision.note.strip():
            raise ValueError("keeping a queued target requires an explicit stopping reason")
        if sum(change.op == "add" for change in revision.changes) > scope.additions:
            raise ValueError("the patch exceeds the remaining node budget")
        candidate, applied = self._apply(standard, revision, norms)
        before = {criterion.id: criterion for criterion in standard.criteria}
        after = {criterion.id: criterion for criterion in candidate.criteria}
        for change, row in zip(revision.changes, applied, strict=True):
            scope.check_change(change, before.get(row["id"]), after.get(row["id"]))
            if change.refine and (
                corrections
                or (change.op != "add" and not any(p.op == "add" and p.parent_id == change.id for p in scope.allow))
            ):
                raise ValueError("this patch scope does not authorize a refinement follow-up")
        return revision

    async def revise(
        self,
        provider,
        norms: Mapping[str, str],
        standard: Standard,
        evidence: Mapping[str, Decidability],
        *,
        task="",
        verifiers: Mapping[str, str] | None = None,
        corrections=(),
        guidance: str | None = None,
    ) -> Standard:
        """Apply bounded, authorized patches; ordinary calls receive decidability, never worker scores."""
        norms = dict(norms)
        if task:
            if "$task" in norms:
                raise ValueError("$task is reserved for the host's task description")
            norms = {"$task": task, **norms}
        if not norms:
            return standard
        if self.max_calls < 1 or self.max_nodes < 1:
            raise ValueError("construction budgets must be positive")
        prior_state = (
            dict(self.read),
            copy.deepcopy(self.pending),
            self.pending_version,
            self.inputs,
            dict(self.attempted),
            len(self.versions),
        )
        effective_guidance = self.guidance if guidance is None else guidance
        current_inputs = digest({"norms": dict(norms), "guidance": effective_guidance})
        if self.pending and (self.inputs != current_inputs or self.pending_version != standard.version):
            retained = [
                work
                for work in self.pending
                if self.inputs == current_inputs
                and work.get("target_state") is not None
                and work.get("target_state") == _target_state(standard, work["target"])
            ]
            invalidated = [work for work in self.pending if work not in retained]
            if invalidated:
                self.runs.append(
                    {
                        "status": "invalidated",
                        "pending": invalidated,
                        "reason": "The source, guidance or target context changed; old permissions were discarded.",
                    }
                )
            self.pending = retained
        self.inputs = current_inputs
        allow = self._permissions(norms, standard, evidence, corrections)
        if corrections:
            work = [
                {
                    "target": issue.criterion,
                    "reason": issue.correction,
                    "target_state": _target_state(standard, issue.criterion),
                    "allow": [p.model_dump(mode="json") for p in issue.allow],
                }
                for issue in corrections
                if issue.allow
            ]
            addressed = {issue.criterion for issue in corrections}
            suspended = [work for work in self.pending if work["target"] not in addressed]
            self.pending = work
        else:
            suspended = []
            fresh = any(self.read.get(name) != digest(value) for name, value in norms.items())
            undecided = {
                id: digest([asdict(value), asdict(next(c for c in standard.criteria if c.id == id)), current_inputs])
                for id, value in evidence.items()
                if not value.decided and any(c.id == id and c.authority == "model" for c in standard.criteria)
            }
            changed = {id for id, key in undecided.items() if self.attempted.get(id) != key}
            self.attempted.update(undecided)
            if fresh:
                self.pending.insert(
                    0,
                    {
                        "target": "",
                        "reason": "New or changed source requirements.",
                        "target_state": standard.version,
                        "allow": [p.model_dump(mode="json") for p in allow],
                    },
                )
            else:
                for id in sorted(changed):
                    permissions = [p.model_dump(mode="json") for p in allow if p.id == id]
                    if permissions:
                        self.pending.append(
                            {
                                "target": id,
                                "target_state": _target_state(standard, id),
                                "reason": evidence[id].note,
                                "allow": permissions,
                            }
                        )
        if not self.pending:
            return standard

        class Budget:
            def __init__(self, remaining):
                self.remaining, self.calls = remaining, 0

            async def chat_with_retry(self, **kwargs):
                if self.remaining <= 0:
                    raise ValueError("construction call budget exhausted")
                self.remaining -= 1
                self.calls += 1
                return await provider.chat_with_retry(**kwargs)

        budget = Budget(self.max_calls)
        added = 0
        run = {
            "base_version": standard.version,
            "inputs": current_inputs,
            "guidance": effective_guidance,
            "steps": [],
            "status": "complete",
        }
        schema = schema_for(Revision)
        schema["$defs"]["Reference"]["properties"].pop("version", None)
        while self.pending and budget.remaining:
            optional = {c.id for c in standard.criteria if c.kind == "quality"}
            self.pending.sort(key=lambda work: work["target"] in optional)
            work = self.pending[0]
            permissions = tuple(Permission.model_validate(p) for p in work["allow"])
            patch_scope = RevisionScope.bind(standard, norms, permissions, additions=self.max_nodes - added)
            derived = [c for c in standard.criteria if c.origin == "derived" and c.authority == "model"]
            packet = {
                "version": len(self.versions),
                "scope": patch_scope.record(),
                "target": work["target"],
                "reason": work["reason"],
                "available_verifiers": dict(verifiers or {}),
                "corrections": [issue.model_dump(mode="json") for issue in corrections or ()],
                "guidance": effective_guidance,
                "norms": {name: _shown(text) for name, text in norms.items()},
                "new_norms": sorted(name for name, text in norms.items() if self.read.get(name) != digest(text)),
                "held": [asdict(c) for c in standard.criteria if c not in derived],
                "criteria": [
                    {**asdict(c), "last_round": asdict(evidence[c.id]) if c.id in evidence else None} for c in derived
                ],
            }
            try:
                _, revision = await exchange(
                    budget,
                    messages(self.instructions, packet),
                    [tool(REVISE, "Submit only the changes allowed by the host scope, or keep the target.", schema)],
                    submit={
                        REVISE: lambda arguments: self._check(
                            Revision.model_validate(arguments),
                            norms,
                            standard,
                            evidence,
                            corrections,
                            scope=patch_scope,
                        )
                    },
                    model=self.model,
                    effort=self.effort,
                    max_calls=budget.remaining,
                    timeout=self.timeout,
                    trace=self.trace,
                    label="rubric_builder",
                    grace=0,
                    strict_budget=True,
                )
            except asyncio.CancelledError:
                previous_read, previous_pending, previous_version, previous_inputs, attempted, count = prior_state
                self.runs.append(
                    {**run, "status": "interrupted", "calls": budget.calls, "discarded": self.versions[count:]}
                )
                self.read, self.pending, self.pending_version = previous_read, previous_pending, previous_version
                self.inputs, self.attempted, self.versions = previous_inputs, attempted, self.versions[:count]
                raise
            except ExchangeError as exc:
                run.update(status="call_budget_exhausted" if not budget.remaining else "rejected", error=str(exc))
                break
            patch_scope.check_base(standard, norms)
            standard, applied = self._apply(standard, revision, norms)
            self.pending.pop(0)
            added += sum(change.op == "add" for change in revision.changes)
            self.versions.append(
                {
                    "version": len(self.versions) + 1,
                    "base_version": patch_scope.base_version,
                    "rubric_version": standard.version,
                    "scope": patch_scope.record(),
                    "new_norms": packet["new_norms"],
                    "changes": applied,
                    "note": revision.note,
                    "unchecked": [item.model_dump() for item in revision.unchecked],
                }
            )
            run["steps"].append(
                {
                    "target": work["target"],
                    "version": len(self.versions),
                    "status": "changed" if applied else "kept",
                    "note": revision.note,
                }
            )
            self.read.update({name: digest(text) for name, text in norms.items()})
            if not corrections:
                for change, row in zip(revision.changes, applied, strict=True):
                    if change.refine:
                        self.pending.append(
                            {
                                "target": row["id"],
                                "reason": change.refine,
                                "target_state": _target_state(standard, row["id"]),
                                "allow": [Permission(op="add", parent_id=row["id"]).model_dump(mode="json")],
                            }
                        )
            if added >= self.max_nodes and self.pending:
                run["status"] = "node_budget_exhausted"
                break
        if self.pending and run["status"] == "complete":
            run["status"] = "call_budget_exhausted"
        run.update(calls=budget.calls, added=added, rubric_version=standard.version, pending=list(self.pending))
        self.runs.append(run)
        self.pending.extend(suspended)
        self.pending_version = standard.version
        return standard

    def _apply(self, standard: Standard, revision: Revision, norms) -> tuple[Standard, list[dict]]:
        criteria = list(standard.criteria)
        index = {criterion.id: position for position, criterion in enumerate(criteria)}
        taken = set(index) | {row["id"] for version in self.versions for row in version["changes"]}
        number, applied, removed = 0, [], set()
        for change in revision.changes:
            if change.id in index and criteria[index[change.id]].authority == "external":
                raise ValueError(f"{change.id!r} is a protected external requirement")
            drafted = change.criterion
            row = {"op": change.op, "reason": change.reason, "explanation": change.explanation}
            if change.op == "add":
                number += 1
                while f"derived-{number}" in taken:
                    number += 1
                id = f"derived-{number}"
                taken.add(id)
                criteria.append(
                    Criterion(
                        id,
                        drafted.definition,
                        "derived",
                        drafted.kind,
                        _bound(drafted.basis, norms),
                        assessment=drafted.assessment,
                        parent_id=drafted.parent_id,
                    )
                )
            elif change.op == "rewrite":
                id = change.id
                before = criteria[index[id]]
                criteria[index[id]] = replace(
                    before,
                    definition=drafted.definition,
                    basis=_bound(drafted.basis, norms),
                    kind=drafted.kind,
                    assessment=drafted.assessment,
                    parent_id=drafted.parent_id,
                )
                row["before"] = asdict(before)
            else:
                id = change.id
                removed.add(id)
                row["before"] = asdict(criteria[index[id]])
            applied.append({"id": id, **row, **({"criterion": drafted.model_dump(mode="json")} if drafted else {})})
        return Standard(tuple(criterion for criterion in criteria if criterion.id not in removed)), applied

    def record(self) -> dict:
        """Every revision, numbered from one, and the trace of the builder's model calls."""
        return {
            "read": dict(self.read),
            "versions": list(self.versions),
            "trace": list(self.trace),
            "instructions": self.instructions,
            "guidance": self.guidance,
            "model": self.model,
            "effort": self.effort,
            "pending": list(self.pending),
            "pending_version": self.pending_version,
            "inputs": self.inputs,
            "attempted": dict(self.attempted),
            "runs": list(self.runs),
        }

    def restore(self, record: dict) -> None:
        """Continue the saved construction method and its revision history."""
        self.read = dict(record.get("read", {}))
        self.versions = list(record.get("versions", ()))
        self.trace = list(record.get("trace", ()))
        self.instructions = record.get("instructions", self.instructions)
        self.guidance = record.get("guidance", "")
        self.pending = list(record.get("pending", ()))
        self.pending_version = record.get("pending_version", "")
        self.inputs = record.get("inputs", "")
        self.attempted = dict(record.get("attempted", {}))
        self.runs = list(record.get("runs", ()))


__all__ = ["Change", "RubricBuilder", "Drafted", "Revision"]
