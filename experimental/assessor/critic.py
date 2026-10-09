"""The standard critic: writes and revises, round after round, the derived criteria of a `Standard` from the norms.

Without a counterpart to say what good work is, the criteria come from the business's own documents. The critic keeps
them: before each assessment it reads every norm handed over so far, the derived criteria it wrote earlier and, for
each, only whether the last round's judge could decide it, and submits a revision of three kinds of change: `add` a
criterion a norm states and none checks yet, `rewrite` one, or `retire` one. An empty revision keeps the standard,
but a norm handed over since the last revision must be drawn on by a change or listed as unchecked with the reason,
so a revision cut short or never written cannot pass for one that found nothing to change.

Three rules keep the revision honest without anyone checking the critic:
- grounding: every criterion it writes quotes, verbatim, the passage of the named norm it rests on, and a quote the
  norm does not contain is refused;
- a stated cause: each change names its reason from a closed set, and a reason that depends on evidence is accepted
  only when the evidence shows it (a criterion is rewritten or retired as `undecided` only after a round left it
  undecided, and `new_norm` names a norm handed over since the last revision);
- no view of results: the critic never sees whether a criterion passed or failed, so it cannot ease a criterion the
  worker misses; it sees whether the criterion could be decided, which is about the criterion and not the worker.

Every revision is kept with its version, the changes as applied and the norm passages the critic found no checkable
rule in (`record`). The critic is the derived source of `experimental.assessor.standard`; it writes no other source.
"""

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from itertools import cycle
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..curator.generation.context.render import tool
from ..curator.harness.declaration import schema_for
from ..iteration.exchange import exchange, messages
from .standard import Criterion, Decidability, Standard

PROMPT = Path(__file__).resolve().parent / "prompts" / "critic.md"
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

AddReason = Literal["new_norm", "uncovered"]
RewriteReason = Literal["undecided", "imprecise", "beyond_norm"]
RetireReason = Literal["undecided", "duplicate", "beyond_norm"]


class Drafted(BaseModel):
    """A criterion as the critic writes it, with the norm passage it rests on."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, description="The checkable statement, in the norm's own language.")
    situation: str = Field(default="", description="When it applies, if not every time.")
    acceptance: str = Field(default="", description="What counts as meeting it, when the text alone does not say.")
    material: str = Field(description="The norm it comes from, by name.")
    section: str = Field(default="", description="Where in that norm, such as a heading or a step.")
    quote: str = Field(description="The passage of that norm it rests on, copied verbatim.")


class Change(BaseModel):
    """One change to the derived criteria and its cause."""

    model_config = ConfigDict(extra="forbid")

    op: Literal["add", "rewrite", "retire"]
    id: str | None = Field(default=None, description="The derived criterion rewritten or retired; none for add.")
    criterion: Drafted | None = Field(default=None, description="The criterion added, or the rewritten one whole.")
    reason: Literal["new_norm", "uncovered", "undecided", "imprecise", "beyond_norm", "duplicate"]
    explanation: str = Field(min_length=1, description="Why, in terms of the norm and the evidence given.")

    @model_validator(mode="after")
    def _shape(self) -> "Change":
        allowed = {"add": AddReason, "rewrite": RewriteReason, "retire": RetireReason}[self.op].__args__
        if self.reason not in allowed:
            raise ValueError(f"{self.op} takes a reason among {list(allowed)}, not {self.reason!r}")
        if self.op == "add" and (self.id is not None or self.criterion is None):
            raise ValueError("add gives a criterion and no id")
        if self.op == "rewrite" and (self.id is None or self.criterion is None):
            raise ValueError("rewrite names the id and gives the rewritten criterion")
        if self.op == "retire" and (self.id is None or self.criterion is not None):
            raise ValueError("retire names the id and gives no criterion")
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


def _flat(text: str) -> str:
    return " ".join(LINE_MARKUP.sub("", unicodedata.normalize("NFKC", text)).translate(QUOTE_MARKS).split())


def _shown(text: str) -> str:
    """`text` as the critic reads it: each line's straight double quotes as curly pairs.

    The critic copies norm passages verbatim into its tool arguments, and a straight double quote copied into a JSON
    string has to be escaped; models drop the escape often enough to break every attempt of a revision. Curly marks
    need no escape, and `_flat` compares every quotation mark as the same one, so grounding is unchanged.
    """
    return "\n".join(re.sub('"', lambda _, marks=cycle("\u201c\u201d"): next(marks), line) for line in text.split("\n"))


def _grounded(drafted: Drafted, norms: Mapping[str, str]) -> str | None:
    """The reason a drafted criterion is refused for its grounding, or None."""
    if drafted.material not in norms:
        return f"criteria may come only from the norms given {sorted(norms)}; got {drafted.material!r}"
    quote = _flat(drafted.quote)
    if len(quote) < QUOTE_MINIMUM:
        return f"quote the passage of {drafted.material!r} the criterion rests on, at least {QUOTE_MINIMUM} characters"
    if quote not in _flat(norms[drafted.material]):
        return f"the quote is not in {drafted.material!r} verbatim: {drafted.quote[:120]!r}"
    return None


@dataclass
class Critic:
    """Keeps the derived criteria of a standard (see the module docstring); one model call per revision, made with
    the provider the assessor hands it, so the call runs in the assessor's compartment."""

    model: str | None = None
    effort: str | None = None
    max_calls: int = 4
    timeout: float = 300
    read: set[str] = field(default_factory=set)
    versions: list[dict] = field(default_factory=list)
    trace: list[dict] = field(default_factory=list)

    def _check(self, revision: Revision, norms, standard: Standard, evidence: Mapping[str, Decidability]) -> Revision:
        derived = {criterion.id: criterion for criterion in standard.criteria if criterion.source == "derived"}
        fresh = set(norms) - self.read
        problems, touched = [], set()
        for number, change in enumerate(revision.changes, 1):
            where = f"change {number}"
            if change.id is not None:
                if change.id not in derived:
                    problems.append(f"{where}: {change.id!r} is not a derived criterion; derived are {sorted(derived)}")
                    continue
                if change.id in touched:
                    problems.append(f"{where}: {change.id!r} is changed twice")
                touched.add(change.id)
            if change.criterion is not None and (refused := _grounded(change.criterion, norms)):
                problems.append(f"{where}: {refused}")
            if change.reason == "new_norm" and change.criterion and change.criterion.material not in fresh:
                problems.append(f"{where}: new_norm applies only to a norm handed over since the last revision")
            if change.reason == "undecided" and evidence.get(change.id, Decidability(True)).decided:
                problems.append(f"{where}: {change.id!r} was decided in the last round, so undecided is no cause")
            if change.op == "rewrite" and change.criterion and change.id in derived:
                before = derived[change.id]
                if (before.text, before.situation, before.acceptance) == (
                    change.criterion.text,
                    change.criterion.situation,
                    change.criterion.acceptance,
                ):
                    problems.append(f"{where}: the rewrite of {change.id!r} changes nothing")
        stray = {item.material for item in revision.unchecked} - set(norms)
        if stray:
            problems.append(f"unchecked names norms that were not given: {sorted(stray)}")
        drawn = {change.criterion.material for change in revision.changes if change.criterion is not None}
        if silent := sorted(fresh - drawn - {item.material for item in revision.unchecked}):
            problems.append(
                f"each norm in new_norms needs a criterion drawn from it or an unchecked entry saying why none: {silent}"
            )
        if problems:
            raise ValueError("; ".join(problems))
        return revision

    async def revise(
        self, provider, norms: Mapping[str, str], standard: Standard, evidence: Mapping[str, Decidability]
    ) -> Standard:
        """`standard` with its derived criteria revised against every norm handed over so far (name to text) and the
        last judging's `evidence` per derived criterion; the other sources are shown as already held and kept."""
        if not norms:
            return standard
        derived = [criterion for criterion in standard.criteria if criterion.source == "derived"]
        packet = {
            "version": len(self.versions),
            "norms": {name: _shown(text) for name, text in norms.items()},
            "new_norms": sorted(set(norms) - self.read),
            "held": [
                {"text": criterion.text, "situation": criterion.situation}
                for criterion in standard.criteria
                if criterion.source != "derived"
            ],
            "criteria": [
                {
                    "id": criterion.id,
                    "text": criterion.text,
                    "situation": criterion.situation,
                    "acceptance": criterion.acceptance,
                    "material": criterion.provenance.removeprefix("material:").split(" ", 1)[0],
                    "quote": criterion.quote,
                    "last_round": (
                        {"decided": evidence[criterion.id].decided, "note": evidence[criterion.id].note}
                        if criterion.id in evidence
                        else None
                    ),
                }
                for criterion in derived
            ],
        }
        _, revision = await exchange(
            provider,
            messages(PROMPT.read_text(), packet),
            [tool(REVISE, "Submit the revision of the derived criteria.", schema_for(Revision))],
            submit={
                REVISE: lambda arguments: self._check(Revision.model_validate(arguments), norms, standard, evidence)
            },
            model=self.model,
            effort=self.effort,
            max_calls=self.max_calls,
            timeout=self.timeout,
            trace=self.trace,
            label="critic",
        )
        revised, applied = self._apply(standard, revision)
        self.versions.append(
            {
                "version": len(self.versions) + 1,
                "new_norms": packet["new_norms"],
                "changes": applied,
                "unchecked": [item.model_dump() for item in revision.unchecked],
            }
        )
        self.read |= set(norms)
        return revised

    @staticmethod
    def _apply(standard: Standard, revision: Revision) -> tuple[Standard, list[dict]]:
        criteria = list(standard.criteria)
        index = {criterion.id: position for position, criterion in enumerate(criteria)}
        taken, number, applied, retired = set(index), 0, [], set()
        for change in revision.changes:
            drafted = change.criterion
            provenance = (
                ""
                if drafted is None
                else f"material:{drafted.material}" + (f" {drafted.section}" if drafted.section else "")
            )
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
                        drafted.text,
                        "derived",
                        "should",
                        provenance,
                        drafted.situation,
                        drafted.acceptance,
                        drafted.quote,
                    )
                )
            elif change.op == "rewrite":
                id = change.id
                before = criteria[index[id]]
                criteria[index[id]] = replace(
                    before,
                    text=drafted.text,
                    situation=drafted.situation,
                    acceptance=drafted.acceptance,
                    provenance=provenance,
                    quote=drafted.quote,
                )
                row["before"] = before.text
            else:
                id = change.id
                retired.add(id)
                row["before"] = criteria[index[id]].text
            applied.append({"id": id, **row, **({"criterion": drafted.model_dump()} if drafted else {})})
        return Standard(tuple(criterion for criterion in criteria if criterion.id not in retired)), applied

    def record(self) -> dict:
        """Every revision, numbered from one, and the trace of the critic's model calls."""
        return {"read": sorted(self.read), "versions": list(self.versions), "trace": list(self.trace)}


__all__ = ["Change", "Critic", "Drafted", "Revision"]
