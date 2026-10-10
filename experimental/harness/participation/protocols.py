"""Contracts between the iteration loop and whatever runs the worker or measures the result.

The measuring side's protocol is `experimental.harness.assessor.role.AssessorProtocol`; the data it returns is defined here. Each
field names the roles that may receive it (see `experimental.harness.participation.audience`): what an assessor measured stays
with the counterpart and the Analyst, what it said may reach the Curator (`experimental.harness.participation.hearing` applies it).
"""

from dataclasses import dataclass, field
from typing import Literal, Protocol

from experimental.harness.participation.audience import EVALUATION, HEARD, audience
from experimental.harness.participation.requirements import Authority
from experimental.harness.raven_adapter.worker import Execution


@dataclass(frozen=True)
class Exchange:
    user: str = field(metadata=audience(*HEARD))
    execution: Execution = field(metadata=audience(*HEARD))

    @property
    def assistant(self) -> str:
        return self.execution.text

    @property
    def stopped(self) -> str | None:
        """Why the turn ended without a reply, as the conversant met it, or None when the worker answered."""
        outcome = self.execution.outcome
        if outcome.get("timed_out"):
            return f"no reply within {outcome.get('timeout')} seconds; the turn was stopped"
        if outcome.get("answerless"):
            return "no reply: the assistant ended the turn without answering"
        return None


@dataclass(frozen=True)
class Item:
    """One measured item: a criterion, a dataset case or a session, with a verdict or a score.

    `basis` says where the criterion behind `expected` comes from: a counterpart's `check`, a dataset `case`, an earlier
    `requirement` held as a regression check, or a handed-over `material` it was drawn from. The last two restate
    what the Curator already holds, so their wording is not the evaluation side's own."""

    id: str = field(metadata=audience(*EVALUATION))
    result: Literal["pass", "fail", "unknown", "not_applicable"] | float = field(metadata=audience(*EVALUATION))
    session: str | None = field(default=None, metadata=audience(*EVALUATION))
    expected: str = field(default="", metadata=audience(*EVALUATION))
    actual: str = field(default="", metadata=audience(*EVALUATION))
    note: str = field(default="", metadata=audience(*EVALUATION))
    basis: Literal["", "check", "case", "requirement", "material"] = field(default="", metadata=audience(*EVALUATION))
    authority: Authority = field(default="model", metadata=audience(*EVALUATION))
    strength: Literal["must_hold", "should"] | None = field(default=None, metadata=audience(*EVALUATION))
    parent_id: str | None = field(default=None, metadata=audience(*EVALUATION))


@dataclass(frozen=True)
class Handover:
    """One material handed over with a signal: its name, its kind in the scenario's terms (see
    `experimental.harness.scenario.KINDS`) and its files as paths relative to the worker's agent home."""

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
    authority: Authority = field(default="model", metadata=audience(*EVALUATION))


Sessions = dict[str, list[Exchange]]


class Trial(Protocol):
    """Whatever puts the worker through its paces: a conversation, a dataset, a simulation."""

    async def run(self, worker) -> Sessions: ...
