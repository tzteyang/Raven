"""A round as later rounds see it: what each assessor concluded, the requirements raised, the Curator's diagnoses of
them, the revision that followed and whether each requirement held in the round after.

Each field declares who may read it (`experimental.audience`): an assessor's per-item results reach the Analyst only,
the diagnoses the Curator only, and a change's predicted effect and verification the record only, so the Curator's
and the Analyst's views are projections of the same entries. `held` is filled in once the next round is analysed,
by the rule in `experimental.iteration.ledger`.
"""

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from ..audience import ANALYST, CURATOR, INTERNAL, RECORD_ONLY


class Raised(BaseModel):
    """A requirement raised in the round; `held` is None until the round after its revision is judged."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    AUDIENCES: ClassVar[dict[str, frozenset[str]]] = {
        **{
            name: INTERNAL
            for name in ("id", "situation", "behavior", "strength", "acceptance", "repeats", "materials", "held")
        },
        "grounds": ANALYST,
    }

    id: str
    situation: str = ""
    behavior: str
    strength: str
    acceptance: str
    repeats: str | None = None
    materials: tuple[str, ...] = ()
    grounds: tuple[str, ...] = ()
    held: bool | None = None


class Diagnosed(BaseModel):
    """The Curator's diagnosis of one input of the curation that followed the round, in the harness `scope` whose
    attribution made it (`root`, or `child/<name>` for a child harness of a composite curation)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    AUDIENCES: ClassVar[dict[str, frozenset[str]]] = {
        name: CURATOR for name in ("about", "state", "mechanism", "earlier", "scope")
    }

    about: str
    state: str
    mechanism: str = ""
    earlier: str = ""
    scope: str = "root"


class Revised(BaseModel):
    """One change of the revision: its target in its harness `scope` (`root`, or `child/<name>`), how it treats the
    diagnosed mechanism, why, and the inputs it addresses (the selection's grounds for the target)."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    AUDIENCES: ClassVar[dict[str, frozenset[str]]] = {
        **{name: INTERNAL for name in ("target", "treatment", "reason", "addresses", "scope")},
        "expected": RECORD_ONLY,
        "verification": RECORD_ONLY,
    }

    scope: str = "root"
    target: str
    treatment: str | None = None
    reason: str = ""
    addresses: tuple[str, ...] = ()
    expected: str = ""
    verification: str = ""


class Entry(BaseModel):
    """One round of the history; `revision` is None when nothing was revised after it, `attributor` the identity of
    the attributor behind its diagnoses."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    AUDIENCES: ClassVar[dict[str, frozenset[str]]] = {
        "round": INTERNAL,
        "satisfied": INTERNAL,
        "results": ANALYST,
        "failed_in": ANALYST,
        "requirements": INTERNAL,
        "mechanisms_acted": INTERNAL,
        "understanding": INTERNAL,
        "revision": INTERNAL,
        "diagnoses": CURATOR,
        "attributor": RECORD_ONLY,
    }

    round: int = Field(ge=0)
    satisfied: dict[str, bool | None] = Field(default_factory=dict)
    results: dict[str, dict[str, JsonValue]] = Field(default_factory=dict)
    failed_in: dict[str, dict[str, str]] = Field(default_factory=dict)
    requirements: tuple[Raised, ...] = ()
    mechanisms_acted: tuple[dict[str, JsonValue], ...] = ()
    understanding: str = ""
    revision: tuple[Revised, ...] | None = None
    diagnoses: tuple[Diagnosed, ...] | None = None
    attributor: dict[str, JsonValue] | None = None


def _revised(scope, plan, selection) -> tuple[Revised, ...]:
    grounds = selection.grounds if selection is not None else {}
    return tuple(
        Revised(
            scope=scope,
            target=change.target,
            treatment=change.treatment,
            reason=change.reason,
            addresses=tuple(grounds.get(change.target, ())),
            expected=change.expected,
            verification=change.verification,
        )
        for change in plan.changes
    )


def _diagnosed(scope, attribution) -> tuple[Diagnosed, ...]:
    return tuple(
        Diagnosed(
            about=diagnosis.about,
            state=diagnosis.state,
            mechanism=diagnosis.mechanism,
            earlier=diagnosis.earlier,
            scope=scope,
        )
        for diagnosis in attribution.attribution.diagnoses
    )


def entry(number, signals, feedback, plan, activity=(), attribution=None, selection=None, children=None) -> Entry:
    """The history entry of round `number` (0 is onboarding): its signals and feedback, the mechanisms that acted,
    and, when it was curated, the plan installed after it with the attribution and selection it came from.
    `children` are the child harnesses' candidates a composite curation installed with it, by name, whose changes
    and diagnoses join the entry under their scope."""
    children = {name: candidate for name, candidate in (children or {}).items() if candidate is not None}
    return Entry(
        round=number,
        satisfied={signal.source: signal.satisfied for signal in signals},
        results={signal.source: {item.id: item.result for item in signal.items} for signal in signals if signal.items},
        failed_in={
            signal.source: {item.id: item.session for item in signal.items if item.result == "fail" and item.session}
            for signal in signals
            if signal.items
        },
        requirements=tuple(
            Raised(
                id=requirement.id,
                situation=requirement.situation,
                behavior=requirement.behavior,
                strength=requirement.strength,
                acceptance=requirement.acceptance,
                repeats=requirement.repeats,
                materials=requirement.materials,
                grounds=requirement.grounds,
            )
            for requirement in (feedback.requirements if feedback else ())
        ),
        mechanisms_acted=tuple(row for row in activity if row.get("acted")),
        understanding=plan.understanding if plan else "",
        revision=(
            _revised("root", plan, selection)
            + tuple(
                change
                for name, candidate in children.items()
                for change in _revised(f"child/{name}", candidate.plan, candidate.selection)
            )
        )
        if plan
        else None,
        diagnoses=(
            (_diagnosed("root", attribution) if attribution else ())
            + tuple(
                diagnosis
                for name, candidate in children.items()
                if candidate.attribution is not None
                for diagnosis in _diagnosed(f"child/{name}", candidate.attribution)
            )
        )
        or None
        if attribution or children
        else None,
        attributor=dict(attribution.identity) if attribution else None,
    )
