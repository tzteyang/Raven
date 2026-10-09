"""Define separate source evidence, reviewed guidance and host-owned identities."""

import json
from hashlib import sha256
from typing import Annotated, ClassVar, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

type ModelRole = Literal["builder", "critic", "curator"]
type Phase = Literal["understand", "diagnose", "select", "design", "implement", "repair"]
type MechanismState = Literal[
    "absent", "not_exposed", "not_triggered", "not_consumed", "wrong_logic", "blocked", "model_ignored", "uncovered"
]
type EvidenceBasis = Literal["observation", "indirect", "unknown"]
type Activation = Literal["applied", "not_applied", "unknown"]
type Comparability = Literal["comparable", "changed", "unknown"]
type ProcessResult = Literal["generated", "checked", "retained", "paused", "failed", "gap"]
type SupportKind = Literal["process", "behavior"]
type OpaqueReference = Annotated[str, Field(pattern=r"^(event|evidence)-[0-9a-f]{64}$")]


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("experience text must contain non-whitespace characters")
    return value


type NonemptyText = Annotated[str, Field(min_length=1), AfterValidator(_nonblank)]

SOURCE = frozenset({"builder", "critic"})
GUIDANCE = frozenset({"curator"})
EVERY_MODEL = SOURCE | GUIDANCE
RECORD_ONLY: frozenset[str] = frozenset()


def digest(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    AUDIENCES: ClassVar[dict[str, frozenset[str]]] = {}


def for_model(value: Contract, role: ModelRole) -> dict:
    """Project only declared fields, without giving a source grant or a publication approval."""
    if role not in EVERY_MODEL:
        raise ValueError("unknown experience model role")
    declared = value.AUDIENCES
    unmatched = set(type(value).model_fields) ^ set(declared)
    if unmatched:
        raise ValueError(f"undeclared or unknown experience fields: {sorted(unmatched)}")
    if any(not roles <= EVERY_MODEL for roles in declared.values()):
        raise ValueError("experience fields declare an unknown model role")
    return {name: _project(getattr(value, name), role) for name, roles in declared.items() if role in roles}


def _project(value, role: ModelRole):
    if isinstance(value, Contract):
        return for_model(value, role)
    if isinstance(value, tuple):
        return [_project(item, role) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError("experience projections require declared contracts or scalar fields")


class ExperienceCondition(Contract):
    AUDIENCES = {
        name: EVERY_MODEL
        for name in (
            "situation",
            "phase",
            "scope_kind",
            "mechanism_states",
            "required_capabilities",
            "contract_ids",
            "limits",
        )
    }

    situation: NonemptyText = Field(max_length=1200)
    phase: Phase
    scope_kind: Literal["any", "root", "child"] = "any"
    mechanism_states: tuple[MechanismState, ...] = ()
    required_capabilities: tuple[NonemptyText, ...] = ()
    contract_ids: tuple[NonemptyText, ...] = ()
    limits: tuple[NonemptyText, ...] = ()


class EvidenceView(Contract):
    AUDIENCES = {
        name: SOURCE
        for name in (
            "reference",
            "situation",
            "treatment",
            "scope_kind",
            "process_result",
            "mechanism_state",
            "held",
            "basis",
            "activation",
            "comparability",
            "observations",
        )
    }

    reference: OpaqueReference
    situation: NonemptyText = Field(max_length=12000)
    treatment: NonemptyText = Field(max_length=12000)
    scope_kind: Literal["root", "child"] = "root"
    process_result: ProcessResult
    mechanism_state: MechanismState | None = None
    held: bool | None = None
    basis: EvidenceBasis = "unknown"
    activation: Activation = "unknown"
    comparability: Comparability = "unknown"
    observations: tuple[NonemptyText, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def justified_outcome(self) -> "EvidenceView":
        if self.held is None and self.basis != "unknown":
            raise ValueError("an undecided behavior outcome has an unknown evidence basis")
        if self.held is not None and (self.activation != "applied" or self.basis == "unknown"):
            raise ValueError("a behavior verdict requires an applied revision and an evidence basis")
        if self.basis == "observation" and (self.held is None or not self.observations):
            raise ValueError("observational support requires a verdict and actual observations")
        return self


class RecordOrigin(Contract):
    AUDIENCES = {
        name: RECORD_ONLY
        for name in ("access_scope", "run_id", "lineage_id", "record_id", "scope", "input_key", "revision_before")
    }

    access_scope: NonemptyText
    run_id: NonemptyText
    lineage_id: NonemptyText
    record_id: NonemptyText
    scope: str = Field(default="root", pattern=r"^(root|child/[^/]+(?:/[^/]+)*)$")
    input_key: NonemptyText = "curation"
    revision_before: NonemptyText | None = None

    def event_id(self) -> str:
        return digest(self.model_dump(exclude={"revision_before"}))


class OutcomeReceipt(Contract):
    AUDIENCES = {
        name: RECORD_ONLY
        for name in (
            "access_scope",
            "revision_id",
            "scope",
            "input_key",
            "held",
            "basis",
            "comparability",
            "observations",
        )
    }

    access_scope: NonemptyText
    revision_id: NonemptyText
    scope: str = Field(default="root", pattern=r"^(root|child/[^/]+(?:/[^/]+)*)$")
    input_key: NonemptyText = "curation"
    held: bool
    basis: Literal["observation", "indirect"] = "indirect"
    comparability: Comparability = "unknown"
    observations: tuple[NonemptyText, ...] = Field(default=(), max_length=32)

    @model_validator(mode="after")
    def observations_required(self) -> "OutcomeReceipt":
        if self.basis == "observation" and not self.observations:
            raise ValueError("an observation receipt requires observations")
        return self


class ExperienceEvent(Contract):
    AUDIENCES = {
        "origin": RECORD_ONLY,
        "source_digest": RECORD_ONLY,
        "revision_after": RECORD_ONLY,
        "view": SOURCE,
    }

    origin: RecordOrigin
    source_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    revision_after: NonemptyText | None = None
    view: EvidenceView

    @model_validator(mode="after")
    def linked_identity(self) -> "ExperienceEvent":
        if self.view.reference != "event-" + self.origin.event_id():
            raise ValueError("the evidence reference must identify its host-owned origin")
        expected_scope = "root" if self.origin.scope == "root" else "child"
        if self.view.scope_kind != expected_scope:
            raise ValueError("the evidence scope must match its origin")
        if self.view.activation == "applied" and (
            self.origin.revision_before is None
            or self.revision_after is None
            or self.origin.revision_before == self.revision_after
        ):
            raise ValueError("an applied revision requires distinct known before and after identities")
        return self


class EvidenceLink(Contract):
    AUDIENCES = {"reference": SOURCE, "relation": SOURCE}

    reference: OpaqueReference
    relation: Literal["supports", "contradicts", "context"]


class ExperienceProposal(Contract):
    AUDIENCES = {"condition": SOURCE, "guidance": SOURCE, "evidence": SOURCE, "support_kind": SOURCE}

    condition: ExperienceCondition
    guidance: NonemptyText = Field(max_length=1200)
    evidence: tuple[EvidenceLink, ...] = Field(min_length=1, max_length=16)
    support_kind: SupportKind = "behavior"

    @model_validator(mode="after")
    def unique_evidence(self) -> "ExperienceProposal":
        references = [item.reference for item in self.evidence]
        if len(references) != len(set(references)):
            raise ValueError("each evidence reference may occur once per proposal")
        return self


class ReviewIssue(Contract):
    AUDIENCES = {"kind": SOURCE, "field": SOURCE, "reason": SOURCE}

    kind: Literal["case_detail", "too_specific", "too_vague", "unsupported", "scope_violation"]
    field: Literal["condition", "guidance", "evidence", "support_kind"]
    reason: NonemptyText = Field(max_length=1200)


class ExperienceReview(Contract):
    AUDIENCES = {"proposal_index": SOURCE, "decision": SOURCE, "issues": SOURCE}

    proposal_index: int = Field(ge=0)
    decision: Literal["accept", "revise", "reject"]
    issues: tuple[ReviewIssue, ...] = Field(default=(), max_length=16)

    @model_validator(mode="after")
    def explained_decision(self) -> "ExperienceReview":
        if (self.decision == "accept") == bool(self.issues):
            raise ValueError("accept carries no issues; revise and reject require specific issues")
        return self


class RepairRequest(Contract):
    AUDIENCES = {name: SOURCE for name in ("target", "current", "fields", "reason", "evidence")}

    target: NonemptyText
    current: ExperienceProposal
    fields: tuple[NonemptyText, ...] = Field(min_length=1)
    reason: NonemptyText
    evidence: tuple[NonemptyText, ...] = Field(min_length=1)


class BuildRequest(Contract):
    AUDIENCES = {name: SOURCE for name in ("events", "related", "capabilities", "contract_ids", "repair")}

    events: tuple[EvidenceView, ...] = Field(min_length=1, max_length=16)
    related: tuple[ExperienceProposal, ...] = Field(default=(), max_length=8)
    capabilities: tuple[NonemptyText, ...] = ()
    contract_ids: tuple[NonemptyText, ...] = ()
    repair: RepairRequest | None = None

    @model_validator(mode="after")
    def unique_events(self) -> "BuildRequest":
        references = [item.reference for item in self.events]
        if len(references) != len(set(references)):
            raise ValueError("a build request cannot repeat an event")
        return self


class GuidanceItem(Contract):
    AUDIENCES = {name: GUIDANCE for name in ("id", "version", "condition", "guidance", "evidence_refs", "support_kind")}

    id: NonemptyText
    version: int = Field(ge=1)
    condition: ExperienceCondition
    guidance: NonemptyText = Field(max_length=1200)
    evidence_refs: tuple[OpaqueReference, ...] = Field(min_length=1, max_length=16)
    support_kind: SupportKind = "behavior"


class GuidanceBundle(Contract):
    AUDIENCES = {"snapshot_id": GUIDANCE, "format_version": GUIDANCE, "items": GUIDANCE}

    snapshot_id: NonemptyText
    format_version: Literal[1] = 1
    items: tuple[GuidanceItem, ...] = Field(max_length=4)

    @model_validator(mode="after")
    def unique_items(self) -> "GuidanceBundle":
        identities = [item.id for item in self.items]
        if len(identities) != len(set(identities)):
            raise ValueError("a guidance bundle cannot contain multiple versions of one experience")
        return self
