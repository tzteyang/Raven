"""Contracts between the iteration loop and whatever runs the worker or measures the result.

The measuring side's protocol is `experimental.assessor.role.Assessor`; the data it returns is defined here. Each
field names the roles that may receive it (see `experimental.audience`): what an assessor measured stays
with the party and the Analyst, what it said may reach the Curator (`experimental.iteration.hearing` applies it).
"""

from dataclasses import dataclass, field
from typing import Literal, Protocol

from ..audience import EVALUATION, HEARD, audience
from ..curator.raven_adapter.worker import Execution


@dataclass(frozen=True)
class Exchange:
    user: str = field(metadata=audience(*HEARD))
    execution: Execution = field(metadata=audience(*HEARD))

    @property
    def assistant(self) -> str:
        return self.execution.text


@dataclass(frozen=True)
class Item:
    """One measured item: a criterion, a dataset case or a session, with a verdict or a score.

    `basis` says where the criterion behind `expected` comes from: a party's `check`, a dataset `case`, an earlier
    `requirement` held as a regression check, or a handed-over `material` it was drawn from. The last two restate
    what the Curator already holds, so their wording is not the evaluation side's own."""

    id: str = field(metadata=audience(*EVALUATION))
    result: Literal["pass", "fail", "unknown"] | float = field(metadata=audience(*EVALUATION))
    session: str | None = field(default=None, metadata=audience(*EVALUATION))
    expected: str = field(default="", metadata=audience(*EVALUATION))
    actual: str = field(default="", metadata=audience(*EVALUATION))
    note: str = field(default="", metadata=audience(*EVALUATION))
    basis: Literal["", "check", "case", "requirement", "material"] = field(default="", metadata=audience(*EVALUATION))


@dataclass(frozen=True)
class Handover:
    """One material handed over with a signal: its name, its kind in the scenario's terms (see
    `experimental.scenario.KINDS`) and its files as paths relative to the worker's agent home."""

    name: str = field(metadata=audience(*HEARD))
    kind: str = field(metadata=audience(*HEARD))
    files: tuple[str, ...] = field(default=(), metadata=audience(*HEARD))


@dataclass(frozen=True)
class Signal:
    """What one assessor measured this round. `satisfied` is its own threshold verdict; None means it does not judge.

    `attachments` are the materials handed over with the text.
    """

    source: str = field(metadata=audience(*HEARD))
    text: str = field(default="", metadata=audience(*HEARD))
    items: tuple[Item, ...] = field(default=(), metadata=audience(*EVALUATION))
    metrics: dict[str, float] = field(default_factory=dict, metadata=audience(*EVALUATION))
    satisfied: bool | None = field(default=None, metadata=audience(*HEARD))
    attachments: tuple[Handover, ...] = field(default=(), metadata=audience(*HEARD))


Sessions = dict[str, list[Exchange]]


class Trial(Protocol):
    """Whatever puts the worker through its paces: a conversation, a dataset, a simulation."""

    async def run(self, worker) -> Sessions: ...
