"""Serializable capability contributions and their candidate/active lifetimes.

Curator authors these declarations. Registration stages a contribution; the host
resolves its implementation or package and activates a complete candidate.
Registration, model visibility, execution permission and actual use are separate
facts. Nothing in this module loads a package or executes a tool.
"""

from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from .artifact import ArtifactPath
from .interaction import InteractionScope


class ToolContribution(BaseModel):
    """Reference an inert native tool factory or a declared strategy interaction.

    factory is a candidate module:function accepting no positional arguments
    by default. native_context=True defers construction and supplies the actual
    native PluginContext after runtime services exist.
    Strategy interactions resolve their live owner at invocation, never at
    registration. The host derives schemas from the actual implementation.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["tool"] = "tool"
    name: str = Field(min_length=1, pattern=r"^[a-zA-Z_][a-zA-Z0-9_-]*$")
    owner: Literal["capability", "memory", "planning", "action"] = "capability"
    factory: str | None = None
    native_context: bool = False
    interaction: Literal["memory.interact", "planning.interact", "action.handle_request"] | None = None

    @model_validator(mode="after")
    def one_implementation(self):
        if (self.factory is None) == (self.interaction is None):
            raise ValueError("a tool contribution needs exactly one factory or interaction")
        if self.factory is not None and (self.owner != "capability" or ":" not in self.factory):
            raise ValueError("a tool factory must be a capability-owned module:attribute reference")
        if self.interaction is not None and self.interaction.split(".")[0] != self.owner:
            raise ValueError("an interaction must belong to its declared owner")
        if self.native_context and self.factory is None:
            raise ValueError("native construction context belongs to a tool factory")
        return self


class SkillPackage(BaseModel):
    """A complete inspected input package, pinned by its relative-file digest.

    root must resolve inside a host-supplied material root. The host copies
    nested and binary files, verifies digest again and never executes package
    scripts during adoption. A temporary exploration copy is not a durable root.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    root: str = Field(min_length=1)
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class SkillContribution(BaseModel):
    """Adopt a package, author text files, or apply explicit text edits to a package.

    The resource name is its directory and native discovered Skill name.
    Files are package-relative; SKILL.md and native discovery remain required.
    Supplying a revised complete contribution replaces that managed package.
    Omitting an authoring target preserves it through the existing Artifact rules.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["skill"] = "skill"
    name: str = Field(min_length=1, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")
    owner: Literal["capability"] = "capability"
    package: SkillPackage | None = None
    files: dict[ArtifactPath, str] = Field(default_factory=dict)
    remove_paths: tuple[ArtifactPath, ...] = ()
    source: str = Field(min_length=1)

    @model_validator(mode="after")
    def meaningful_package(self):
        if self.package is None and not self.files:
            raise ValueError("a skill requires an inspected package or authored files")
        if self.package is None and "SKILL.md" not in self.files:
            raise ValueError("an authored skill requires SKILL.md")
        if self.package is None and self.remove_paths:
            raise ValueError("path retirement requires an adopted package")
        if len(self.remove_paths) != len(set(self.remove_paths)) or set(self.remove_paths) & self.files.keys():
            raise ValueError("skill paths cannot be written and retired together")
        for path in self.files:
            if any(path.startswith(parent + "/") for parent in self.files if parent != path):
                raise ValueError("a skill file conflicts with a parent file")
        return self


CapabilityContribution = Annotated[ToolContribution | SkillContribution, Field(discriminator="kind")]


class RegistrationReceipt(BaseModel):
    """Report candidate registration, never claim that the worker can already use it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    owner: str
    kind: Literal["tool", "skill"]
    candidate: str
    status: Literal["staged", "unchanged", "rejected"]
    reason: str | None = None

    @model_validator(mode="after")
    def rejected_reason(self):
        if self.status == "rejected" and not self.reason:
            raise ValueError("rejected registration requires a reason")
        return self


class CapabilityRegistrar(Protocol):
    """The narrow, candidate-scoped dependency supplied to a capability factory."""

    def register(self, contribution: CapabilityContribution) -> RegistrationReceipt: ...


class SkillView(BaseModel):
    """An actually discovered skill, including its native availability and body."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    source: str
    path: str
    available: bool
    description: str = ""
    content: str | None = None
    digest: str | None = None


class SkillSelection(BaseModel):
    """Choose an available skill and how its information reaches the model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    source: str | None = None
    delivery: Literal["body", "catalog"] = "body"


class SelectionRequest(BaseModel):
    """Choose from this runtime's active capabilities for the current decision.

    tools is the offered schema set at this selection point, not a permission
    grant. The host normalizes subsequent native restrictions/protection before
    publishing EffectiveCapabilities to Memory and Action.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    scope: InteractionScope
    messages: list[dict[str, JsonValue]]
    tools: list[dict[str, JsonValue]]
    skills: tuple[SkillView, ...] = ()
    subagents: tuple[dict[str, JsonValue], ...] = ()
    plan: JsonValue = None
    need: str | None = None


class CapabilitySelection(BaseModel):
    """Select tool names and skills; None explicitly delegates the corresponding native choice.

    Empty tuples select nothing. Selection neither constructs a resource nor
    executes it. Unknown, duplicate or unavailable selections are errors.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    tools: tuple[str, ...] | None = None
    skills: tuple[SkillSelection, ...] | None = None
    guidance: str | None = None

    @model_validator(mode="after")
    def unique_resources(self):
        if self.tools is not None and len(self.tools) != len(set(self.tools)):
            raise ValueError("selected tool names must be unique")
        names = [(skill.source, skill.name) for skill in self.skills or ()]
        if len(names) != len(set(names)):
            raise ValueError("selected skill names must be unique")
        return self


class EffectiveCapabilities(BaseModel):
    """The actual definitions delivered to one model call and its skill selection.

    Permissions are checked at dispatch. native_skills distinguishes delegation
    from an explicit empty selection. This view never contains staged resources.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    scope: InteractionScope
    tools: list[dict[str, JsonValue]]
    skills: tuple[SkillView, ...] = ()
    selection: tuple[SkillSelection, ...] = ()
    native_skills: bool = True
    guidance: str | None = None
