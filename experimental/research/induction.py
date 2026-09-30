"""Rules the party's exemplars and counterexamples show and its norms leave unstated, induced in one bounded exchange.

An exemplar is read for its form, never its content: how good work is ordered, phrased and laid out, not the
customer, dates or prices it happened to carry; a counterexample shows what must not be done. The model receives the
profile, the norms as the party wrote them and the instances, each package's text files whole and its other files
by name, and submits the rules no norm already states, each naming the instances that show it.

The rules become norms that the partner, the Analyst and the Curator receive, so only materials all of them may
receive are read, and a rule whose wording carries text sealed from any of them is refused (`sealed`, computed on the
scenario as the party holds it, withheld materials included). Checks are never read: a rule restating one would hand
the partner the test.
"""

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from ..curator.generation.context.render import tool
from ..curator.harness.declaration import schema_for
from ..iteration.exchange import exchange, messages
from ..scenario import Material, Scenario, contents, default_visibility
from ..scenario.sealed import Sealed

NAME = "submit_rules"
AUDIENCE = default_visibility("norm")
PROMPTS = Path(__file__).resolve().parent / "prompts"
INSTANCES = ("exemplar", "counterexample")


@dataclass(frozen=True)
class Rule:
    """One induced rule: `sources` are the instances that show it and `evidence` what in them does."""

    kind: ClassVar[str] = "norm"

    id: str
    text: str
    sources: tuple[str, ...]
    evidence: str
    situation: str = ""

    def record(self) -> dict:
        return asdict(self)


class Induced(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, description="What the assistant must or must not do, in the materials' language.")
    situation: str = Field(default="", description="When it applies, if not every time.")
    sources: list[str] = Field(min_length=1, description="The exemplars or counterexamples that show it, by name.")
    evidence: str = Field(min_length=1, description="What in them shows it: a short quotation or the feature.")


class Induction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rules: list[Induced] = Field(default_factory=list)


def readable(scenario: Scenario) -> dict[str, Material]:
    """The materials every role that receives a norm may receive; only these are read."""
    return {name: material for name, material in scenario.materials.items() if AUDIENCE <= material.visibility}


def package(material: Material) -> dict:
    texts, others = contents(material.path)
    return {"name": material.name, "description": material.description, "files": texts, "other_files": list(others)}


def carried(rule_texts, sealed: Mapping[str, Sealed]) -> list[str]:
    """The roles whose sealed fingerprints occur in these texts."""
    return [role for role, seal in sealed.items() if any(seal.hits(text) for text in rule_texts if text)]


async def induce(
    provider,
    scenario: Scenario,
    *,
    sealed: Mapping[str, Sealed] | None = None,
    limit: int = 12,
    model=None,
    effort=None,
    max_calls=4,
    timeout=300,
    trace=None,
) -> tuple[Rule, ...]:
    """At most `limit` rules the scenario's instances show and its norms do not state, ids `induced-1` on."""
    read = readable(scenario)
    instances = {name for name, material in read.items() if material.kind in INSTANCES}
    if not instances:
        return ()
    packet = {
        "profile": scenario.situation.profile,
        "norms": [package(material) for material in read.values() if material.kind == "norm"],
        "exemplars": [package(material) for material in read.values() if material.kind == "exemplar"],
        "counterexamples": [package(material) for material in read.values() if material.kind == "counterexample"],
        "at_most": limit,
    }

    def accept(arguments) -> Induction:
        induction = Induction.model_validate(arguments)
        if len(induction.rules) > limit:
            raise ValueError(f"submit at most {limit} rules, the ones that matter most to the work")
        for number, rule in enumerate(induction.rules, 1):
            stray = set(rule.sources) - instances
            if stray:
                raise ValueError(
                    f"rule {number} names sources that are not the instances given {sorted(instances)}: {sorted(stray)}"
                )
            if carried((rule.text, rule.situation), sealed or {}):
                raise ValueError(f"rule {number} says what the materials given do not; state only what they show")
        return induction

    _, induction = await exchange(
        provider,
        messages((PROMPTS / "induce.md").read_text(), packet),
        [tool(NAME, "Submit the rules the instances show and no norm states.", schema_for(Induction))],
        submit={NAME: accept},
        model=model,
        effort=effort,
        max_calls=max_calls,
        timeout=timeout,
        trace=trace,
        label="induce",
    )
    return tuple(
        Rule(f"induced-{number}", rule.text, tuple(rule.sources), rule.evidence, rule.situation)
        for number, rule in enumerate(induction.rules, 1)
    )
