"""The party's decision on each item the research stage wrote down, an induced rule or a researched finding:
confirmed, amended with its right wording, rejected, or undecided.

The party decides in one of two ways: a decisions file it wrote against the items an earlier run recorded
(`Decisions.read`), or, in a simulation, a model playing it (`ModelParty`) that reads the materials the party knows,
including those it did not hand over, and judges each item by them alone. An item the party did not decide stays a
candidate: it reaches the partner marked as unconfirmed and no criterion is drawn from it
(`experimental.research.package`). An amended wording reaches the partner, so the model party's is refused when it
carries text sealed from a role that receives what the stage writes.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..curator.generation.context.render import tool
from ..curator.harness.declaration import schema_for
from ..iteration.exchange import exchange, messages
from ..scenario import Scenario
from ..scenario.sealed import Sealed
from .induction import PROMPTS, Rule, carried, package
from .inquiry import Finding

NAME = "submit_decisions"
Status = Literal["confirmed", "amended", "rejected", "undecided"]
Item = Rule | Finding


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    status: Status
    text: str = Field(default="", description="The item as it should read; required when amended.")
    situation: str = Field(default="", description="When the amended item applies, if not every time.")
    reason: str = Field(default="", description="Why, in one sentence.")

    @model_validator(mode="after")
    def amended_has_text(self) -> "Decision":
        if self.status == "amended" and not self.text.strip():
            raise ValueError(f"{self.id}: an amended item needs its wording in text")
        return self


class Decisions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decisions: list[Decision] = Field(default_factory=list)

    @classmethod
    def read(cls, path: Path) -> "Decisions":
        return cls.model_validate_json(Path(path).read_text())

    def against(self, items: Iterable[Item], *, every=False) -> "Decisions":
        """These decisions, checked to name only the items given, each once, and with `every` all of them."""
        ids = [decision.id for decision in self.decisions]
        known = [item.id for item in items]
        if len(ids) != len(set(ids)):
            raise ValueError(f"decide each item once; repeated: {sorted({id for id in ids if ids.count(id) > 1})}")
        if set(ids) - set(known):
            raise ValueError(f"decisions name items that were not recorded: {sorted(set(ids) - set(known))}")
        if every and set(ids) != set(known):
            raise ValueError(f"give exactly one decision per item id: {sorted(known)}")
        return self


def settle(items: Sequence[Item], decisions: Decisions | None) -> list[tuple[Item, Decision]]:
    """Each item with the party's decision on it; an item it did not decide is undecided."""
    given = {decision.id: decision for decision in (decisions.against(items).decisions if decisions else ())}
    return [(item, given.get(item.id, Decision(id=item.id, status="undecided"))) for item in items]


def worded(item: Item, decision: Decision) -> Item:
    """The item as the party left it: in the party's wording when it amended it."""
    return replace(item, text=decision.text, situation=decision.situation) if decision.status == "amended" else item


class ModelParty:
    """A model playing the party, deciding by the materials in `knows` (any of the scenario's, withheld or not)."""

    def __init__(
        self,
        provider,
        scenario: Scenario,
        knows: Iterable[str],
        *,
        sealed: Mapping[str, Sealed] | None = None,
        model=None,
        effort=None,
        max_calls=4,
        timeout=300,
    ):
        self.knows = tuple(knows)
        unknown = set(self.knows) - set(scenario.materials)
        if not self.knows or unknown:
            raise ValueError(f"the party must know materials of the scenario; unknown: {sorted(unknown)}")
        hidden = [name for name in self.knows if not scenario.visible(name, "party")]
        if hidden:
            raise ValueError(f"materials the party may not receive: {hidden}")
        self.provider, self.scenario, self.sealed = provider, scenario, dict(sealed or {})
        self.model, self.effort, self.max_calls, self.timeout = model, effort, max_calls, timeout

    def record(self) -> dict:
        return {
            "by": "model",
            "knows": list(self.knows),
            "model": self.model,
            "effort": self.effort,
            "max_calls": self.max_calls,
            "timeout": self.timeout,
        }

    async def decide(self, items: Sequence[Item], *, trace=None) -> Decisions:
        if not items:
            return Decisions()
        packet = {
            "profile": self.scenario.situation.profile,
            "your_materials": [package(self.scenario.materials[name]) for name in self.knows],
            "items": [
                {
                    "id": item.id,
                    "kind": item.kind,
                    "text": item.text,
                    "situation": item.situation,
                    "read_from": list(item.sources),
                    "evidence": item.evidence,
                }
                for item in items
            ],
        }

        def accept(arguments) -> Decisions:
            decisions = Decisions.model_validate(arguments).against(items, every=True)
            for decision in decisions.decisions:
                if decision.status == "amended" and carried((decision.text, decision.situation), self.sealed):
                    raise ValueError(f"{decision.id}: word the amendment by your materials alone")
            return decisions

        _, decisions = await exchange(
            self.provider,
            messages((PROMPTS / "confirm.md").read_text(), packet),
            [tool(NAME, "Submit one decision per item id.", schema_for(Decisions))],
            submit={NAME: accept},
            model=self.model,
            effort=self.effort,
            max_calls=self.max_calls,
            timeout=self.timeout,
            trace=trace,
            label="confirm",
        )
        return decisions
