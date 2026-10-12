"""A scenario as the bench plays it: the counterpart's scenario (`experimental.cultivation.counterpart.scenario`) with
the personas of the people it simulates, found by name among the bundled cases."""

import random
from dataclasses import dataclass, field, replace
from pathlib import Path

from experimental.cultivation.counterpart.scenario import Criterion
from experimental.cultivation.counterpart.scenario import Scenario as CounterpartScenario
from experimental.harness.participation.allowance import excerpt, reading_budget
from experimental.harness.participation.files import read_delivered
from experimental.harness.scenario import Scenario as Contract
from experimental.harness.scenario import load as read_contract
from experimental.simulation.bench.cards import Drawn, draw

BUNDLED = Path(__file__).resolve().parents[1] / "cases"


def handed_evidence(sessions, conversants, *, tokens: int | None = None) -> dict[str, dict]:
    """The files actually supplied by each played card, without its private persona or expected answer."""
    budget = reading_budget() if tokens is None else tokens
    return {
        name: {"handouts": {path.name: excerpt(read_delivered(path), budget) for path in conversants[name].handed}}
        for name in sessions
        if name in conversants and conversants[name].handed
    }


@dataclass(frozen=True)
class Persona:
    """A drill card: `text` names its values in braces and `values` says how each is drawn (see `cards`); `files` are
    what the person hands over as the conversation opens; `expected` is a labelled card's answer, which only the
    evaluation side reads."""

    name: str
    text: str
    values: dict = field(default_factory=dict, compare=False)
    files: tuple[Path, ...] = field(default=(), compare=False)
    expected: str | None = field(default=None, compare=False)

    def play(self, rng: random.Random) -> Drawn:
        return replace(draw(self.name, self.values, self.text, rng), expected=self.expected)


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
    def of(cls, read: Contract, **options) -> "Scenario":
        return replace(
            super().of(read, **options),
            personas=tuple(
                Persona(case.id, case.text, case.values, tuple(read.root / item for item in case.files), case.expected)
                for case in read.situation.cases
            ),
        )


__all__ = ["BUNDLED", "Criterion", "Persona", "Scenario"]
