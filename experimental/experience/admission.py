"""Qualify exact reviewed methods using independent source evidence and explicit claim scope."""

from dataclasses import dataclass
from typing import Literal

from pydantic import Field

from .contracts import (
    RECORD_ONLY,
    Contract,
    ExperienceEvent,
    ExperienceProposal,
    ExperienceReview,
    NonemptyText,
    OpaqueReference,
    digest,
)
from .state import CandidateRef

type ExperienceStatus = Literal["candidate", "supported", "contested", "retired"]


def method_id(access_scope: str, proposal: ExperienceProposal) -> str:
    return digest(
        {
            "scope": access_scope,
            "condition": proposal.condition.model_dump(),
            "guidance": proposal.guidance,
            "support_kind": proposal.support_kind,
        }
    )


@dataclass(frozen=True)
class AdmissionPolicy:
    critic_digest: str
    min_independent_runs: int = 2

    def __post_init__(self):
        if (
            len(self.critic_digest) != 64
            or any(char not in "0123456789abcdef" for char in self.critic_digest)
            or type(self.min_independent_runs) is not int
            or self.min_independent_runs < 2
        ):
            raise ValueError("admission requires a critic identity digest and at least two independent runs")

    @property
    def id(self) -> str:
        return digest({"rule_version": 1, "critic": self.critic_digest, "minimum": self.min_independent_runs})


class AdmissionAssessment(Contract):
    AUDIENCES = {
        name: RECORD_ONLY
        for name in ("reference", "status", "policy_id", "independent_runs", "evidence_refs", "reasons")
    }

    reference: CandidateRef
    status: ExperienceStatus
    policy_id: str
    independent_runs: int = Field(default=0, ge=0)
    evidence_refs: tuple[OpaqueReference, ...] = Field(default=(), max_length=16)
    reasons: tuple[str, ...] = ()


class ProcessCheckReceipt(Contract):
    AUDIENCES = {
        name: RECORD_ONLY
        for name in ("access_scope", "method", "event_reference", "event_version", "passed", "observations")
    }

    access_scope: NonemptyText
    method: CandidateRef
    event_reference: OpaqueReference
    event_version: int = Field(ge=1)
    passed: bool = Field(strict=True)
    observations: tuple[NonemptyText, ...] = Field(min_length=1, max_length=16)


@dataclass(frozen=True)
class LinkedEvidence:
    event: ExperienceEvent
    relation: Literal["supports", "contradicts", "context"]
    current: bool
    process_verdict: bool | None = None


@dataclass(frozen=True)
class ReviewedVersion:
    reference: CandidateRef
    proposal: ExperienceProposal
    review: ExperienceReview
    critic_digest: str
    status: ExperienceStatus
    typed_support: bool
    evidence: tuple[LinkedEvidence, ...]


def _explicit_outcome(event: ExperienceEvent) -> bool:
    view = event.view
    return view.activation == "applied" and view.basis == "observation" and view.comparability == "comparable"


def _independent_references(events: tuple[ExperienceEvent, ...], supporting: set[str]) -> tuple[str, ...]:
    parents = list(range(len(events)))
    identities: dict[tuple[str, str], int] = {}

    def root(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    for index, event in enumerate(events):
        for key in (
            ("run", event.origin.run_id),
            ("lineage", event.origin.lineage_id),
            ("source", event.source_digest),
        ):
            if key in identities:
                parents[root(index)] = root(identities[key])
            identities[key] = index
    groups: dict[int, list[str]] = {}
    for index, event in enumerate(events):
        if event.view.reference in supporting:
            groups.setdefault(root(index), []).append(event.view.reference)
    return tuple(sorted(min(references) for references in groups.values()))


def assess_family(versions: tuple[ReviewedVersion, ...], policy: AdmissionPolicy) -> AdmissionAssessment:
    latest = max(versions, key=lambda version: version.reference.version)

    def result(status, *reasons, references=()):
        return AdmissionAssessment(
            reference=latest.reference,
            status=status,
            policy_id=policy.id,
            independent_runs=len(references),
            evidence_refs=references[:16],
            reasons=reasons,
        )

    if latest.status == "retired":
        return result("retired", "retired")
    if not latest.typed_support:
        return result("candidate", "support_kind_required")
    if latest.critic_digest != policy.critic_digest or latest.review.decision != "accept":
        return result("candidate", "current_review_required")
    if not latest.evidence or any(not link.current for link in latest.evidence):
        return result("retired", "source_unavailable")

    events: dict[str, ExperienceEvent] = {}
    supporting: set[str] = set()
    contradicted = False
    for version in versions:
        if (
            version.status == "retired"
            or not version.typed_support
            or version.review.decision != "accept"
            or any(not link.current for link in version.evidence)
        ):
            continue
        for link in version.evidence:
            event, view = link.event, link.event.view
            events[view.reference] = event
            if link.relation == "contradicts":
                contradicted = True
            if (
                latest.proposal.support_kind == "process"
                and link.relation == "supports"
                and link.process_verdict is False
            ):
                contradicted = True
            if (
                latest.proposal.support_kind == "behavior"
                and link.relation == "supports"
                and _explicit_outcome(event)
                and view.held is False
            ):
                contradicted = True
            if version.critic_digest != policy.critic_digest:
                continue
            if link.relation != "supports":
                continue
            if latest.proposal.support_kind == "process":
                if view.process_result == "checked" and link.process_verdict is True:
                    supporting.add(view.reference)
            elif _explicit_outcome(event):
                if view.held is True and view.process_result in {"checked", "generated"}:
                    supporting.add(view.reference)

    references = _independent_references(tuple(events.values()), supporting)
    if contradicted:
        return result("contested", "contradictory_evidence", references=references)
    if len(references) < policy.min_independent_runs:
        return result("candidate", "insufficient_independent_support", references=references)
    return result("supported", references=references)
