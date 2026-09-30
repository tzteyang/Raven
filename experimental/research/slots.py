"""What a scenario directory gives in each category of the contract, and how a missing one could be filled.

A slot is one category of `experimental.scenario.contract`. A gap in the norms is `inducible` when the party gave
exemplars or counterexamples, which show rules by instance (`experimental.research.induction`), and `researchable`
when it gave neither norms nor instances: how the trade commonly does the work can be found on the web, and only
the party can confirm it as its own (`experimental.research.inquiry`). Facts are `researchable` when none were handed
over. The party's own standard can come from the party alone (`party`). The loader already refuses a scenario
without a profile or a case, and exemplars, counterexamples, the wording and the prior are inputs a scenario may do
without, so none of them is ever a gap.
"""

from dataclasses import asdict, dataclass
from typing import Literal

from ..scenario import Scenario

Gap = Literal["inducible", "researchable", "party"]


@dataclass(frozen=True)
class Slot:
    category: str
    given: tuple[str, ...]
    gap: Gap | None = None
    reason: str = ""

    def record(self) -> dict:
        return asdict(self)


def slots(scenario: Scenario) -> tuple[Slot, ...]:
    """One slot per category, in the contract's order, for the scenario as the party handed it over: a material
    only the party holds fills no slot, since the partner never receives it."""
    handed = set(scenario.handed)
    named = {
        kind: tuple(name for name, material in scenario.materials.items() if material.kind == kind and name in handed)
        for kind in ("norm", "fact", "exemplar", "counterexample")
    }
    checks = tuple(check.id for check in scenario.statements.checks)
    if named["exemplar"] or named["counterexample"]:
        norms = Slot("norms", named["norm"], "inducible", "exemplars or counterexamples may show rules no norm states")
    elif named["norm"]:
        norms = Slot("norms", named["norm"])
    else:
        norms = Slot("norms", (), "researchable", "no norm and no instance: the trade's common practice, for the party")
    wording = {"onboarding": scenario.exchange.onboarding, "handover": scenario.exchange.handover}
    return (
        Slot("profile", ("profile",)),
        Slot("cases", tuple(case.id for case in scenario.situation.cases)),
        norms,
        Slot("facts", named["fact"])
        if named["fact"]
        else Slot("facts", (), "researchable", "no fact was handed over; the web may tell what the work depends on"),
        Slot("exemplars", named["exemplar"]),
        Slot("counterexamples", named["counterexample"]),
        Slot("checks", checks) if checks else Slot("checks", (), "party", "the party's standard is its own"),
        Slot("wording", tuple(name for name, text in wording.items() if text)),
        Slot("prior", tuple(str(path) for path in scenario.prior.records)),
    )
