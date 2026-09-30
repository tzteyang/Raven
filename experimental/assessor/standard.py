"""The evaluation side's standard and the automatic Assessor that holds each round to it.

A `Standard` has three legitimate sources, and each criterion carries its source, strength and provenance:

- declared: the scenario's own checks, must_hold;
- derived: checkable items a model draws from the handed-over norms (`derive`), should until the party confirms them
  (`Standard.confirmed`); only norms are read, never exemplars nor the partner's own output, and the derivation is
  shown the party's criteria and asked only for what they leave uncovered, so the party's come first;
- sedimented: every requirement raised so far, kept as a resident regression check with the requirement's own
  strength (`Standard.sedimented`), so the loop keeps guarding what was confirmed even when the party is silent.

`StandardAssessor` judges a round's sessions against the standard with a model and returns its verdicts as a `Signal`
for the Analyst to translate; it has no voice of its own. Only must_hold criteria decide whether it is satisfied, so
satisfying derived criteria alone never ends a run, and with no must_hold criterion exercised it does not judge. The
loop hands it the history before each assessment (`sediment`). The standard is evaluation apparatus: its fields reach
the party and the Analyst only, and the assessor runs in the Analyst's compartment when it is given the boundaries.
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from contextlib import nullcontext
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..audience import EVALUATION, audience
from ..curator.generation.context.render import tool
from ..curator.harness.declaration import schema_for
from ..iteration.exchange import exchange, messages
from ..iteration.protocols import Item, Sessions, Signal

Source = Literal["declared", "derived", "sedimented"]
Strength = Literal["must_hold", "should"]
SOURCES: tuple[Source, ...] = ("declared", "derived", "sedimented")
BASIS = {"declared": "check", "derived": "material", "sedimented": "requirement"}
NAME = "standard"
JUDGE, DERIVE = "submit_verdicts", "submit_criteria"
PROMPTS = Path(__file__).resolve().parent / "prompts"
TEXT_FILES = frozenset({".md", ".txt", ".csv", ".json", ".yaml", ".yml", ".html"})
FILE_LIMIT = 40_000


@dataclass(frozen=True)
class Criterion:
    """One checkable statement: `situation` says when it applies and `acceptance` what counts as meeting it, when the
    text itself does not."""

    id: str = field(metadata=audience(*EVALUATION))
    text: str = field(metadata=audience(*EVALUATION))
    source: Source = field(metadata=audience(*EVALUATION))
    strength: Strength = field(metadata=audience(*EVALUATION))
    provenance: str = field(metadata=audience(*EVALUATION))
    situation: str = field(default="", metadata=audience(*EVALUATION))
    acceptance: str = field(default="", metadata=audience(*EVALUATION))


@dataclass(frozen=True)
class Standard:
    """The criteria a round is held to, the party's first; ids are unique across the sources."""

    criteria: tuple[Criterion, ...] = field(default=(), metadata=audience(*EVALUATION))

    def __post_init__(self):
        ids = [criterion.id for criterion in self.criteria]
        if len(ids) != len(set(ids)):
            raise ValueError(f"criterion ids must be unique: {sorted(id for id in ids if ids.count(id) > 1)}")

    @classmethod
    def declared(cls, checks: Iterable[tuple[str, str]]) -> "Standard":
        """The scenario's checks, as (id, text) pairs."""
        return cls(tuple(Criterion(id, text, "declared", "must_hold", f"check:{id}") for id, text in checks))

    def of(self, *sources: Source) -> "Standard":
        return Standard(tuple(criterion for criterion in self.criteria if criterion.source in sources))

    def sedimented(self, history: Sequence[Mapping]) -> "Standard":
        """This standard with every requirement raised in `history` (entries as the Analyst reads them) as a
        regression check; a requirement raised again keeps its id and its latest wording."""
        raised: dict[str, Criterion] = {}
        for entry in history:
            for requirement in entry.get("requirements", ()):
                raised[requirement["id"]] = Criterion(
                    requirement["id"],
                    requirement["behavior"],
                    "sedimented",
                    "must_hold" if requirement.get("strength") == "must_hold" else "should",
                    f"requirement {requirement['id']}, round {entry.get('round')}",
                    situation=requirement.get("situation", ""),
                    acceptance=requirement.get("acceptance", ""),
                )
        kept = tuple(criterion for criterion in self.criteria if criterion.source != "sedimented")
        taken = {criterion.id for criterion in kept}
        return Standard((*kept, *(criterion for id, criterion in raised.items() if id not in taken)))

    def derived(self, criteria: Iterable[Criterion]) -> "Standard":
        """This standard with derived criteria added after the party's; an id already taken is not replaced."""
        taken = {criterion.id for criterion in self.criteria}
        return Standard((*self.criteria, *(criterion for criterion in criteria if criterion.id not in taken)))

    def confirmed(self, ids: Iterable[str]) -> "Standard":
        """The party confirmed these derived criteria: they now hold every time."""
        ids = set(ids)
        unknown = ids - {criterion.id for criterion in self.criteria if criterion.source == "derived"}
        if unknown:
            raise ValueError(f"only derived criteria are confirmed; not derived: {sorted(unknown)}")
        return Standard(
            tuple(
                replace(criterion, strength="must_hold") if criterion.id in ids else criterion
                for criterion in self.criteria
            )
        )


class Verdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    result: Literal["pass", "fail", "unknown"]
    session: str | None = Field(default=None, description="The session that decided the verdict, if one did.")
    actual: str = Field(default="", description="The assistant's words or file content the verdict rests on.")
    note: str = Field(default="", description="What should have happened instead, for a fail.")


class Verdicts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdicts: list[Verdict] = Field(min_length=1)


class Drawn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, description="The checkable statement, in the norm's own language.")
    situation: str = Field(default="", description="When it applies, if not every time.")
    material: str = Field(description="The norm it comes from, by name.")
    section: str = Field(default="", description="Where in that norm, such as a heading or a step.")


class Criteria(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criteria: list[Drawn] = Field(default_factory=list)


def satisfied(standard: Standard, items: Sequence[Item]) -> bool | None:
    """Whether every must_hold criterion that was exercised passed; None when none was exercised."""
    must = {criterion.id for criterion in standard.criteria if criterion.strength == "must_hold"}
    judged = [item.result for item in items if item.id in must and item.result != "unknown"]
    return all(result == "pass" for result in judged) if judged else None


def _rate(items: Sequence[Item], ids: set[str]) -> float | None:
    judged = [item.result for item in items if item.id in ids and item.result != "unknown"]
    return sum(result == "pass" for result in judged) / len(judged) if judged else None


def _delivered(path: str) -> str:
    file = Path(path)
    if file.suffix.lower() not in TEXT_FILES or not file.is_file():
        return ""
    return file.read_text(errors="replace")[:FILE_LIMIT]


def conversations(sessions: Sessions) -> dict[str, list[dict]]:
    """Each session as the judge reads it: the user's messages, the assistant's replies, the text of any text
    file handed over with a reply (other files by name), and whether a reply never came in time."""
    told = {}
    for name, exchanges in sessions.items():
        rows = []
        for exchange_ in exchanges:
            row = {"user": exchange_.user, "assistant": exchange_.assistant}
            files = {Path(path).name: _delivered(path) for path in exchange_.execution.deliverables}
            if files:
                row["delivered"] = files
            outcome = exchange_.execution.outcome
            if outcome.get("timed_out"):
                row["stopped"] = f"no reply within {outcome.get('timeout')} seconds; the turn was stopped"
            rows.append(row)
        told[name] = rows
    return told


def _checked(standard: Standard, sessions: Sessions, arguments) -> Verdicts:
    verdicts = Verdicts.model_validate(arguments)
    expected = sorted(criterion.id for criterion in standard.criteria)
    got = sorted(verdict.id for verdict in verdicts.verdicts)
    if got != expected:
        raise ValueError(f"give exactly one verdict per criterion; expected {expected}, got {got}")
    unknown = {verdict.session for verdict in verdicts.verdicts if verdict.session} - sessions.keys()
    if unknown:
        raise ValueError(f"verdicts name sessions that did not happen: {sorted(unknown)}")
    return verdicts


async def derive(
    provider,
    norms: Mapping[str, str],
    standard: Standard,
    *,
    model=None,
    effort=None,
    max_calls=4,
    timeout=180,
    trace=None,
) -> tuple[Criterion, ...]:
    """Checkable criteria drawn from the handed-over norms (name to text) that `standard` leaves uncovered, each of
    strength should with the norm and section it comes from."""
    if not norms:
        return ()
    packet = {
        "norms": dict(norms),
        "party_criteria": [
            {"text": criterion.text, "situation": criterion.situation}
            for criterion in standard.criteria
            if criterion.source != "derived"
        ],
    }

    def parse(arguments) -> Criteria:
        drawn = Criteria.model_validate(arguments)
        stray = {item.material for item in drawn.criteria} - set(norms)
        if stray:
            raise ValueError(f"criteria may come only from the norms given {sorted(norms)}; got {sorted(stray)}")
        return drawn

    _, drawn = await exchange(
        provider,
        messages((PROMPTS / "derive.md").read_text(), packet),
        [
            tool(
                DERIVE,
                "Submit the checkable criteria the norms state and the party's criteria miss.",
                schema_for(Criteria),
            )
        ],
        submit={DERIVE: parse},
        model=model,
        effort=effort,
        max_calls=max_calls,
        timeout=timeout,
        trace=trace,
        label="derive",
    )
    taken, made, number = {criterion.id for criterion in standard.criteria}, [], 0
    for item in drawn.criteria:
        number += 1
        while f"derived-{number}" in taken:
            number += 1
        provenance = f"material:{item.material}" + (f" {item.section}" if item.section else "")
        made.append(Criterion(f"derived-{number}", item.text, "derived", "should", provenance, item.situation))
    return tuple(made)


class StandardAssessor:
    """An Assessor that holds each round to a `Standard` with a model; see the module docstring.

    `sources` names which sources it keeps: the declared ones it is given, the derived ones it draws from the norms
    handed over so far (`norms`, a mapping or a callable returning one, read before every assessment, so a norm handed
    over later is derived from then), and the sedimented ones the loop hands it through `sediment`. `boundaries`, when
    given, run its model calls in the Analyst's compartment, sparing the round's user messages and the criteria it
    holds, which were vetted where they came from.
    """

    def __init__(
        self,
        provider,
        standard: Standard = Standard(),
        *,
        sources: Iterable[Source] = SOURCES,
        norms: Mapping[str, str] | Callable[[], Mapping[str, str]] | None = None,
        model=None,
        effort=None,
        max_calls=4,
        timeout=300,
        boundaries=None,
        name=NAME,
    ):
        self.sources = tuple(sources)
        unknown = set(self.sources) - set(SOURCES)
        if unknown:
            raise ValueError(f"unknown sources: {sorted(unknown)}")
        self.provider, self.standard = provider, standard.of(*self.sources)
        fixed = {} if norms is None or callable(norms) else dict(norms)
        self.norms = norms if callable(norms) else lambda: fixed
        self.drawn_from: set[str] = set()
        self.model, self.effort, self.max_calls, self.timeout = model, effort, max_calls, timeout
        self.boundaries, self.name = boundaries, name
        self.trace: list[dict] = []

    def sediment(self, history: Sequence[Mapping]) -> None:
        """The loop's history so far, as the Analyst reads it."""
        if "sedimented" in self.sources:
            self.standard = self.standard.sedimented(history)

    def _scope(self, sessions: Sessions):
        if self.boundaries is None:
            return nullcontext(None)
        spoken = [tuple(exchange_.user for exchange_ in exchanges) for exchanges in sessions.values()]
        # A sedimented criterion is the Analyst's own requirement and a derived one restates a handed-over norm;
        # a declared one is a check, which the contract may seal from the Analyst, so it is never spared.
        handed = [
            text
            for criterion in self.standard.criteria
            if criterion.source != "declared"
            for text in (criterion.text, criterion.situation, criterion.acceptance)
            if text
        ]
        return self.boundaries.compartment("analyst", spoken=[*spoken, *handed])

    async def evaluate(self, sessions: Sessions) -> Signal | None:
        fresh = {}
        if "derived" in self.sources:
            fresh = {name: text for name, text in self.norms().items() if name not in self.drawn_from}
        if not sessions or not (fresh or self.standard.criteria):
            return None
        with self._scope(sessions) as scope:
            provider = self.provider if scope is None else scope.provider(self.provider)
            if fresh:
                drawn = await derive(
                    provider,
                    fresh,
                    self.standard,
                    model=self.model,
                    effort=self.effort,
                    timeout=self.timeout,
                    trace=self.trace,
                )
                self.standard = self.standard.derived(drawn)
                self.drawn_from |= fresh.keys()
            if not self.standard.criteria:
                return None
            packet = {
                "criteria": [
                    {
                        "id": criterion.id,
                        "text": criterion.text,
                        "situation": criterion.situation,
                        "acceptance": criterion.acceptance,
                        "strength": criterion.strength,
                    }
                    for criterion in self.standard.criteria
                ],
                "conversations": conversations(sessions),
            }
            _, verdicts = await exchange(
                provider,
                messages((PROMPTS / "judge.md").read_text(), packet),
                [tool(JUDGE, "Submit one verdict per criterion.", schema_for(Verdicts))],
                submit={JUDGE: lambda arguments: _checked(self.standard, sessions, arguments)},
                model=self.model,
                effort=self.effort,
                max_calls=self.max_calls,
                timeout=self.timeout,
                trace=self.trace,
                label="standard",
            )
        criteria = {criterion.id: criterion for criterion in self.standard.criteria}
        items = tuple(
            Item(
                verdict.id,
                verdict.result,
                verdict.session,
                criteria[verdict.id].text,
                verdict.actual,
                verdict.note,
                BASIS[criteria[verdict.id].source],
            )
            for verdict in verdicts.verdicts
        )
        must = {id for id, criterion in criteria.items() if criterion.strength == "must_hold"}
        rates = {"must_hold_pass_rate": _rate(items, must), "should_pass_rate": _rate(items, set(criteria) - must)}
        metrics = {key: rate for key, rate in rates.items() if rate is not None}
        return Signal(self.name, items=items, metrics=metrics, satisfied=satisfied(self.standard, items))

    def record(self) -> dict:
        """The standard as it stands, the norms it was derived from and the trace of its model calls."""
        return {
            "criteria": [asdict(criterion) for criterion in self.standard.criteria],
            "derived_from": sorted(self.drawn_from),
            "trace": list(self.trace),
        }
