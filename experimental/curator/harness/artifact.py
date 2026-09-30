"""Plans and native payloads passed between generation, checks and assembly."""

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Annotated, ClassVar, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, JsonValue, model_validator

from ...audience import CURATOR, INTERNAL, RECORD_ONLY
from .attribution import Attributed
from .state import StateUse


def relative_path(value: str) -> str:
    """Accept a canonical path within an artifact, without touching the filesystem."""
    if (
        not value
        or PurePosixPath(value).is_absolute()
        or any(part in {"", ".", ".."} for part in value.split("/"))
        or any(char in value for char in ("\\", ":", "\x00"))
    ):
        raise ValueError("expected a relative POSIX artifact path without empty, dot or parent segments")
    return value


ArtifactPath = Annotated[str, AfterValidator(relative_path)]

# Who may receive each field of the plan types (experimental.audience). A plan's understanding is the Curator's
# answer to the feedback, which the Analyst reads back next round; the design, the state, the grounds and the node
# reasons are the Curator's own; a change's expected behavior and verification go to the record only, where their
# accuracy can be measured before any role is shown them.


class Change(BaseModel):
    """One selected host target and the behavior its change should improve."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    AUDIENCES: ClassVar[dict[str, frozenset[str]]] = {
        "target": INTERNAL,
        "reason": INTERNAL,
        "expected": RECORD_ONLY,
        "verification": RECORD_ONLY,
        "treatment": INTERNAL,
    }

    target: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    expected: str = Field(min_length=1)
    verification: str = Field(min_length=1)
    treatment: Literal["modify", "replace", "add"] | None = Field(
        default=None,
        description="Whether the change modifies the diagnosed mechanism, replaces it, or adds one beside it.",
    )


class Selection(BaseModel):
    """The chosen entries, each grounded on the diagnoses it addresses, before their mechanism is designed."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    AUDIENCES: ClassVar[dict[str, frozenset[str]]] = {
        "understanding": CURATOR,
        "targets": INTERNAL,
        "grounds": CURATOR,
    }

    understanding: str = Field(
        min_length=1, description="The reason for each choice and the open questions for design."
    )
    targets: tuple[str, ...] = ()
    grounds: dict[str, tuple[str, ...]] = Field(
        default_factory=dict,
        description="For each selected target, the diagnosed inputs (their about values) it addresses.",
    )

    @model_validator(mode="after")
    def unique_targets(self) -> "Selection":
        if len(self.targets) != len(set(self.targets)):
            raise ValueError("each selected target must occur once")
        stray = set(self.grounds) - set(self.targets)
        if stray:
            raise ValueError(f"grounds name targets that were not selected: {sorted(stray)}")
        return self


class Plan(BaseModel):
    """Selection lives in changes; state descriptions belong to the proposed mechanism."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    AUDIENCES: ClassVar[dict[str, frozenset[str]]] = {
        "understanding": INTERNAL,
        "design": CURATOR,
        "changes": INTERNAL,
        "state": CURATOR,
        "node_reasons": CURATOR,
    }

    understanding: str = Field(min_length=1)
    design: str = Field(
        default="", description="Concrete mechanism, collaboration, state ownership and failure behavior."
    )
    changes: tuple[Change, ...] = ()
    state: tuple[StateUse, ...] = ()
    node_reasons: dict[ArtifactPath, Annotated[str, Field(min_length=1)]] = Field(
        default_factory=dict,
        description="For a composed root, explain every current, added and retired Playbook node using its exact "
        "playbook_name/node_id key. Read existing keys from composition.nodes and derive new keys from the "
        "prepared Playbooks. Use an empty mapping when both node sets are empty, even if child Harnesses exist. "
        "Child Harness names belong in the design narrative, not these keys. Nonempty node requirements request "
        "child customization; runtime invocation is a separate decision. Reasons explain decisions, not another switch.",
    )

    @model_validator(mode="after")
    def unique_targets(self) -> "Plan":
        if self.changes and not self.design.strip():
            raise ValueError("a changed Harness requires a concrete design")
        names = [change.target for change in self.changes]
        if len(names) != len(set(names)):
            raise ValueError("each target must occur once; combine its changes in one payload")
        resources = [state.resource for state in self.state]
        if len(resources) != len(set(resources)):
            raise ValueError("each state resource must have one description")
        return self


class Artifact(BaseModel):
    """Native values and supporting files; this model does not load or execute them."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    values: dict[str, JsonValue] = Field(
        description="All selected target payloads belong inside this object, keyed by their exact target names. "
        "Target names must not be siblings of values.",
    )
    files: dict[ArtifactPath, str] = Field(
        default_factory=dict,
        description="Supporting files of the authored package: relative path to complete content, for example "
        "'planning_impl.py' to its full Python source. Every module a value references as module:attribute must be "
        "here or already authored; files omitted from an update stay as they are.",
    )
    remove: tuple[str, ...] = Field(
        default=(),
        description="Explicitly retire selected, currently authored target bindings. Omission preserves an existing binding.",
    )

    remove_files: tuple[ArtifactPath, ...] = Field(
        default=(),
        description="Explicitly retire supporting source or asset files. Other omitted files remain authored. "
        "Strategy preparation defines the complete desired resource/content set for the revised implementation.",
    )

    @model_validator(mode="after")
    def distinct_file_paths(self) -> "Artifact":
        supplied = self.values.model_fields_set if isinstance(self.values, BaseModel) else self.values.keys()
        if len(self.remove) != len(set(self.remove)) or set(self.remove) & supplied:
            raise ValueError("retire each target once and do not also supply its value")
        if len(self.remove_files) != len(set(self.remove_files)) or set(self.remove_files) & self.files.keys():
            raise ValueError("retired supporting files must be unique and cannot also be supplied")
        for path in self.files:
            parents = PurePosixPath(path).parents
            if any(str(parent) in self.files for parent in parents):
                raise ValueError(f"artifact file conflicts with a parent file: {path}")
        return self


@dataclass(frozen=True)
class Candidate:
    """Host-attached baseline identity alongside a plan and its schema-checked artifact; `attribution` is the
    attribution the plan was chosen from, with the identity of the attributor that made it, and `selection` the
    selection that grounded each target on it."""

    baseline: str
    contract_id: str
    plan: Plan
    artifact: Artifact
    attribution: Attributed | None = None
    selection: Selection | None = None


@dataclass(frozen=True)
class Validation:
    """Host check failures and observed evidence, shared with generation."""

    errors: list[str]
    observations: list[dict]

    @property
    def passed(self) -> bool:
        return not self.errors
