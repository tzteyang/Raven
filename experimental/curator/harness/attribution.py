"""What mechanism attribution produces: where each input of a curation stands against the Harness as it is.

An input is a requirement (by its id), a handed-over material (`material:<name>`), a node requirement routed to a
child Harness (`node:<playbook>/<node>#<n>`) or, when there is neither, the task itself (`task`). The attribution
component (`experimental.curator.attribution`) diagnoses every input before anything is chosen; selection grounds
each target on these diagnoses and the loop's history keeps them. These types carry no knowledge of how a diagnosis
was reached; `Attributed` adds the host's account of which attributor made it and where it is recorded.
"""

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from ...audience import CURATOR

State = Literal[
    "absent", "not_exposed", "not_triggered", "not_consumed", "wrong_logic", "blocked", "model_ignored", "uncovered"
]


class Diagnosis(BaseModel):
    """Where one input stands against the current Harness: its responsible mechanism, the state of that mechanism
    and the evidence for it, diagnosed before anything is chosen."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    # Who may receive each field (experimental.audience): the diagnosis is the Curator's own.
    AUDIENCES: ClassVar[dict[str, frozenset[str]]] = {
        name: CURATOR for name in ("about", "state", "mechanism", "evidence", "earlier", "placement", "uncertain")
    }

    about: str = Field(
        min_length=1,
        description="A requirement id, material:<name> for a handed-over material, node:<playbook>/<node>#<n> for a "
        "routed node requirement, or task for the task itself.",
    )
    state: State = Field(
        description="absent: no mechanism covers it. not_exposed: one exists but the model never sees it. "
        "not_triggered: it exists but its trigger did not fire. not_consumed: it fired but its result was not used. "
        "wrong_logic: it ran and decided wrongly. blocked: the host or a permission stopped it. model_ignored: the "
        "information was present and the model did not follow it. uncovered: the mechanism exists but does not "
        "reach this situation."
    )
    mechanism: str = Field(
        default="", description="The authored value, file or native mechanism responsible; empty when absent."
    )
    evidence: tuple[str, ...] = Field(
        default=(), description="Turn ids, record kinds and sources read that establish the state."
    )
    earlier: str = Field(
        default="", description="The earlier round and change that handled this, when history shows one."
    )
    placement: str = Field(
        default="", description="For a material: where its content lands and how the worker reads it."
    )
    uncertain: str = Field(
        default="", description="What the evidence leaves open about this diagnosis, if anything; empty when nothing."
    )


class Attribution(BaseModel):
    """One diagnosis per input of a curation; what an attributor submits."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    AUDIENCES: ClassVar[dict[str, frozenset[str]]] = {"diagnoses": CURATOR}

    diagnoses: tuple[Diagnosis, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def one_per_input(self) -> "Attribution":
        abouts = [diagnosis.about for diagnosis in self.diagnoses]
        if len(abouts) != len(set(abouts)):
            raise ValueError("each input has one diagnosis")
        return self

    @property
    def abouts(self) -> frozenset[str]:
        return frozenset(diagnosis.about for diagnosis in self.diagnoses)

    def missing(self, required) -> list[str]:
        return [about for about in required if about not in self.abouts]


class Attributed(BaseModel):
    """An attribution with the host's account of it: the identity of the attributor that made it (its
    implementation, version and model) and the name of its record under the worker's `attribution/` directory."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    AUDIENCES: ClassVar[dict[str, frozenset[str]]] = {"attribution": CURATOR, "identity": CURATOR, "record": CURATOR}

    attribution: Attribution
    identity: dict[str, JsonValue] = Field(default_factory=dict)
    record: str = ""
