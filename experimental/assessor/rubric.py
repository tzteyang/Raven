"""One semantic rubric definition shared by construction, assessment and review."""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Annotated, ClassVar, Literal

from pydantic import ConfigDict, Field, TypeAdapter

from experimental.audience import EVALUATION
from experimental.requirements import Authority, CriterionKind

Origin = Literal["declared", "derived", "sedimented"]
ORIGINS: tuple[Origin, ...] = ("declared", "derived", "sedimented")


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


@dataclass(frozen=True)
class Definition:
    """The evaluated subject, applicability and sole acceptance statement."""

    __pydantic_config__ = ConfigDict(extra="forbid")
    AUDIENCES: ClassVar = dict.fromkeys(("subject", "acceptance", "applies_when"), EVALUATION)
    subject: str
    acceptance: str
    applies_when: str = ""

    def __post_init__(self):
        if not self.subject.strip() or not self.acceptance.strip():
            raise ValueError("a definition needs a subject and an acceptance condition")


@dataclass(frozen=True)
class Reference:
    """An input reference and quotation, bound to its content version by the host."""

    __pydantic_config__ = ConfigDict(extra="forbid")
    AUDIENCES: ClassVar = dict.fromkeys(("source", "quote", "version"), EVALUATION)
    source: str
    quote: str = ""
    version: str = ""

    def __post_init__(self):
        if not self.source.strip():
            raise ValueError("a reference needs a source")


@dataclass(frozen=True)
class Basis:
    """Source evidence and an explanation when a condition is inferred rather than quoted."""

    __pydantic_config__ = ConfigDict(extra="forbid")
    AUDIENCES: ClassVar = dict.fromkeys(("references", "derivation"), EVALUATION)
    references: tuple[Reference, ...]
    derivation: str = ""

    def __post_init__(self):
        if not self.references:
            raise ValueError("a criterion must cite its basis")
        if not any(ref.quote for ref in self.references) and not self.derivation.strip():
            raise ValueError("an inferred condition needs a derivation")


@dataclass(frozen=True)
class LLMCheck:
    """A semantic judgment; an empty instruction judges the complete definition."""

    __pydantic_config__ = ConfigDict(extra="forbid")
    AUDIENCES: ClassVar = dict.fromkeys(("instruction", "method"), EVALUATION)
    instruction: str = ""
    method: Literal["llm"] = "llm"

    def __post_init__(self):
        if self.method != "llm":
            raise ValueError("an LLM check uses the llm method")


@dataclass(frozen=True)
class ProgramCheck:
    """One named host verifier or restricted expression, with no ambiguous string convention."""

    __pydantic_config__ = ConfigDict(extra="forbid")
    AUDIENCES: ClassVar = dict.fromkeys(("verifier", "expression", "method"), EVALUATION)
    verifier: str | None = None
    expression: str | None = None
    method: Literal["program"] = "program"

    def __post_init__(self):
        if self.method != "program":
            raise ValueError("a program check uses the program method")
        if bool(self.verifier and self.verifier.strip()) == bool(self.expression and self.expression.strip()):
            raise ValueError("a program check names exactly one verifier or expression")


Check = Annotated[LLMCheck | ProgramCheck, Field(discriminator="method")]


@dataclass(frozen=True)
class EvidenceRequirement:
    """A required observation channel, optionally narrowed to a material or delivered filename."""

    __pydantic_config__ = ConfigDict(extra="forbid")
    AUDIENCES: ClassVar = dict.fromkeys(("kind", "reference"), EVALUATION)
    kind: Literal["conversation", "execution", "delivered_text", "material"]
    reference: str = ""

    def __post_init__(self):
        if self.kind not in ("conversation", "execution", "delivered_text", "material"):
            raise ValueError("unknown evidence channel")
        if self.kind == "material" and not self.reference:
            raise ValueError("material evidence must name the supplied material")
        if self.kind in ("conversation", "execution") and self.reference:
            raise ValueError("conversation and execution evidence cover the supplied sessions")


@dataclass(frozen=True)
class AssessmentPlan:
    """A whole-criterion judgment plus necessary checks; passing only local checks is insufficient."""

    __pydantic_config__ = ConfigDict(extra="forbid")
    AUDIENCES: ClassVar = dict.fromkeys(("decision", "required_checks", "evidence_requirements"), EVALUATION)
    decision: Check | None = field(default_factory=LLMCheck)
    required_checks: tuple[Check, ...] = ()
    evidence_requirements: tuple[EvidenceRequirement, ...] = ()

    def __post_init__(self):
        if any(isinstance(check, LLMCheck) and not check.instruction.strip() for check in self.required_checks):
            raise ValueError("a local LLM check must state the necessary condition it checks")
        if len(set(self.evidence_requirements)) != len(self.evidence_requirements):
            raise ValueError("evidence requirements must be distinct")


@dataclass(frozen=True)
class Criterion:
    """The sole normative definition and its replaceable, separately inspectable measurement plan."""

    __pydantic_config__ = ConfigDict(extra="forbid")
    AUDIENCES: ClassVar = dict.fromkeys(
        ("id", "definition", "origin", "kind", "basis", "authority", "assessment", "parent_id"), EVALUATION
    )
    id: str
    definition: Definition
    origin: Origin
    kind: CriterionKind
    basis: Basis
    authority: Authority = "model"
    assessment: AssessmentPlan = field(default_factory=AssessmentPlan)
    parent_id: str | None = None

    def __post_init__(self):
        if not self.id.strip() or self.origin not in ORIGINS or self.kind not in ("gate", "guardrail", "quality"):
            raise ValueError("a criterion needs an id, known origin and kind")
        if self.authority not in ("model", "external"):
            raise ValueError("unknown criterion authority")
        if self.parent_id is not None and (not self.parent_id.strip() or self.parent_id == self.id):
            raise ValueError("a parent must name another criterion")

    @property
    def strength(self) -> Literal["must_hold", "should"]:
        return "should" if self.kind == "quality" else "must_hold"

    def calibration_key(self, check: ProgramCheck) -> str:
        return digest(
            {
                "definition": asdict(self.definition),
                "kind": self.kind,
                "basis": asdict(self.basis),
                "assessment": asdict(self.assessment),
                "check": asdict(check),
            }
        )

    @classmethod
    def read(cls, record: dict) -> "Criterion":
        return TypeAdapter(cls).validate_python(record)
