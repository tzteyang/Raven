"""A scenario as the bench plays it: the counterpart's scenario (`experimental.cultivation.counterpart.scenario`) with
the personas of the people it simulates, found by name among the bundled cases."""

import random
from dataclasses import dataclass, field, replace
from pathlib import Path

from experimental.cultivation.counterpart.scenario import Criterion
from experimental.cultivation.counterpart.scenario import Scenario as CounterpartScenario
from experimental.harness.scenario import Scenario as Contract
from experimental.harness.scenario import load as read_contract
from experimental.simulation.bench.cards import Drawn, draw

BUNDLED = Path(__file__).resolve().parents[1] / "cases"


@dataclass(frozen=True)
class Persona:
    """A drill card: `text` names its values in braces and `values` says how each is drawn (see `cards`)."""

    name: str
    text: str
    values: dict = field(default_factory=dict, compare=False)

    def play(self, rng: random.Random) -> Drawn:
        return draw(self.name, self.values, self.text, rng)


@dataclass(frozen=True)
class Scenario(CounterpartScenario):
    """The counterpart's scenario with `personas`, the drill cards of the people the bench plays."""

    personas: tuple[Persona, ...] = ()

    @classmethod
    def load(cls, root: Path) -> "Scenario":
        root = Path(root).resolve()
        if not root.is_dir():
            root = BUNDLED / root.name
        return cls.of(read_contract(root))

    @classmethod
    def of(cls, read: Contract) -> "Scenario":
        return replace(
            super().of(read), personas=tuple(Persona(case.id, case.text, case.values) for case in read.situation.cases)
        )


__all__ = ["BUNDLED", "Criterion", "Persona", "Scenario"]
