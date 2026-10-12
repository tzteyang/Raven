"""Behavior requirements shared by the Analyst's feedback, simulation reviews and planning node requirements."""

import hashlib
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field

Authority = Literal["external", "model"]
CriterionKind = Literal["gate", "guardrail", "quality"]


class ExternalRequirement(BaseModel):
    """An explicit reusable condition quoted from an external signal, including one already satisfied."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    AUDIENCES: ClassVar[dict[str, frozenset[str]]] = {
        name: frozenset({"analyst"}) for name in ("source", "quote", "kind", "situation")
    }

    source: str = Field(min_length=1)
    quote: str = Field(min_length=1)
    kind: CriterionKind
    situation: str = ""

    @property
    def id(self) -> str:
        return "external-" + hashlib.sha256(f"{self.source}\0{self.quote}".encode()).hexdigest()[:16]


class Example(BaseModel):
    """One concrete instance behind a requirement, so the Curator sees what right looks like and not only what failed.

    A `wrong` example pairs what the worker did with how that input should have been handled; the handling follows
    from the input's own words, the handed-over materials and the requirement's behavior alone, never from what only
    the evaluation side holds. A `right` example is a turn of the same kind the worker handled correctly.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    AUDIENCES: ClassVar[dict[str, frozenset[str]]] = {
        name: frozenset({"analyst", "curator"}) for name in ("kind", "turn", "input", "output", "handling", "why")
    }

    kind: Literal["wrong", "right"]
    turn: str = Field(min_length=1, description="The turn id of this round where the example occurred.")
    input: str = Field(min_length=1, description="The part of the input the example concerns, quoted.")
    output: str = Field(
        min_length=1, description="What the worker wrote or did there, quoted or described from the records."
    )
    handling: str = Field(
        default="",
        description="wrong examples: the decision and how to express it for this input, following from the input, "
        "the handed-over materials and the requirement's behavior alone; right examples: empty.",
    )
    why: str = Field(min_length=1, description="The rule from the materials and why the output breaks or keeps it.")


class Requirement(BaseModel):
    """One behavior the worker should show, with the evidence that it currently does not.

    `id` is the loop's, not the Analyst's: sequential within a run, and reused when `repeats` names the earlier
    requirement this one raises again. `grounds` name the judgements it rests on and stay on the evaluation side;
    `materials` name the handed-over materials it draws on and travel with it.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    # Who may receive each field (experimental.audience): a requirement is written for the Curator, its
    # grounds for the counterpart and the Analyst only.
    AUDIENCES: ClassVar[dict[str, frozenset[str]]] = {
        **{
            name: frozenset({"analyst", "curator"})
            for name in (
                "id",
                "situation",
                "behavior",
                "observed",
                "evidence",
                "expectation",
                "acceptance",
                "locations",
                "strength",
                "recurrence",
                "repeats",
                "materials",
                "examples",
            )
        },
        "grounds": frozenset({"counterpart", "analyst"}),
        "authority": frozenset({"counterpart", "analyst"}),
    }

    id: str = ""
    situation: str = Field(default="", description="The class of situation in which the behavior is expected.")
    behavior: str = Field(min_length=1)
    observed: str = Field(min_length=1)
    evidence: tuple[str, ...] = Field(min_length=1)
    expectation: Literal["new", "unmet", "met_but_rejected"]
    acceptance: str = Field(min_length=1)
    locations: tuple[str, ...] = Field(
        default=(),
        description="Observed locations from the host's supplied names; empty means unknown. This locates evidence, not the required repair scope.",
    )
    strength: Literal["must_hold", "should"] = Field(
        description="must_hold when the source or its materials state it as holding every time (a rule, a must, "
        "a prohibition, a red line); should when an occasional miss is acceptable."
    )
    recurrence: int = Field(
        default=0, ge=0, description="How many earlier rounds in history already showed this behavior failing."
    )
    repeats: str | None = Field(
        default=None, description="The id of the earlier requirement in history that this one raises again, if any."
    )
    grounds: tuple[str, ...] = Field(
        default=(),
        description="The judgements this rests on: assessor:<name>, check:<item id> or case:<id>.",
    )
    materials: tuple[str, ...] = Field(default=(), description="The handed-over materials this draws on, by name.")
    examples: tuple[Example, ...] = Field(
        default=(), description="Every wrong instance of this round, and turns of the same kind handled right."
    )
    authority: Authority = Field(default="model", description="Original requirement authority, assigned by the host.")
