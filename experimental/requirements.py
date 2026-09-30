"""Behavior requirements shared by the Analyst's feedback, simulation reviews and planning node requirements."""

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field


class Requirement(BaseModel):
    """One behavior the worker should show, with the evidence that it currently does not.

    `id` is the loop's, not the Analyst's: sequential within a run, and reused when `repeats` names the earlier
    requirement this one raises again. `grounds` name the judgements it rests on and stay on the evaluation side;
    `materials` name the handed-over materials it draws on and travel with it.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    # Who may receive each field (experimental.audience): a requirement is written for the Curator, its
    # grounds for the party and the Analyst only.
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
            )
        },
        "grounds": frozenset({"party", "analyst"}),
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
