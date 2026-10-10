"""Retrieve bounded current guidance without model calls or database mutations."""

import json
import re
import unicodedata
from dataclasses import dataclass

from pydantic import Field

from experimental.experience.admission import AdmissionPolicy
from experimental.experience.contracts import (
    RECORD_ONLY,
    Contract,
    ExperienceProposal,
    GuidanceBundle,
    GuidanceItem,
    MechanismState,
    NonemptyText,
    Phase,
    digest,
    for_model,
)
from experimental.experience.store import ExperienceStore, StoreError

_STOP_WORDS = frozenset("a an the of to and or in for when with from then is are be its that this".split())


class GuidanceQuery(Contract):
    AUDIENCES = {
        name: RECORD_ONLY
        for name in (
            "access_scope",
            "situation",
            "phase",
            "scope_kind",
            "mechanism_states",
            "capabilities",
            "contract_ids",
        )
    }

    access_scope: NonemptyText
    situation: NonemptyText = Field(max_length=12000)
    phase: Phase
    scope_kind: str = Field(pattern=r"^(root|child)$")
    mechanism_states: tuple[MechanismState, ...] = ()
    capabilities: tuple[NonemptyText, ...] = ()
    contract_ids: tuple[NonemptyText, ...] = ()


def _bundle(items: tuple[GuidanceItem, ...]) -> GuidanceBundle:
    payload = {"format_version": 1, "items": [for_model(item, "curator") for item in items]}
    return GuidanceBundle(snapshot_id=digest(payload), items=items)


def export_bundle(bundle: GuidanceBundle) -> bytes:
    return json.dumps(for_model(bundle, "curator"), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


@dataclass(frozen=True)
class RetrievalLimits:
    max_items: int = 4
    max_bytes: int = 8192

    def __post_init__(self):
        if (
            type(self.max_items) is not int
            or not 1 <= self.max_items <= 4
            or type(self.max_bytes) is not int
            or not len(export_bundle(_bundle(()))) <= self.max_bytes <= 8192
        ):
            raise ValueError("retrieval limits must fit an empty bundle and stay within four items and 8 KiB")


def _words(value: str) -> set[str]:
    return set(re.findall(r"\w+", unicodedata.normalize("NFKC", value).casefold())) - _STOP_WORDS


def _relevance(item: GuidanceItem | ExperienceProposal, query: GuidanceQuery) -> int | None:
    condition = item.condition
    if (
        condition.phase != query.phase
        or condition.scope_kind not in {"any", query.scope_kind}
        or not set(condition.required_capabilities) <= set(query.capabilities)
        or not set(condition.contract_ids) <= set(query.contract_ids)
    ):
        return None
    mechanism_match = set(condition.mechanism_states) & set(query.mechanism_states)
    if condition.mechanism_states and not mechanism_match:
        return None
    overlap = len(_words(query.situation) & _words(condition.situation + " " + item.guidance))
    return overlap + 4 * len(mechanism_match) if overlap or mechanism_match else None


class ExperienceRetriever:
    def __init__(self, store: ExperienceStore, policy: AdmissionPolicy, *, limits: RetrievalLimits = RetrievalLimits()):
        self.store, self.policy, self.limits = store, policy, limits

    def _items(self, query: GuidanceQuery) -> tuple[tuple[int, int, GuidanceItem], ...]:
        ranked = []
        for proposal, assessment in self.store.recommendations(query.access_scope, self.policy):
            item = GuidanceItem(
                id=assessment.reference.id,
                version=assessment.reference.version,
                condition=proposal.condition,
                guidance=proposal.guidance,
                support_kind=proposal.support_kind,
                evidence_refs=assessment.evidence_refs,
            )
            score = _relevance(item, query)
            if score is not None:
                ranked.append((score, assessment.independent_runs, item))
        return tuple(sorted(ranked, key=lambda entry: (-entry[0], -entry[1], entry[2].id)))

    def retrieve(self, query: GuidanceQuery) -> GuidanceBundle:
        query = GuidanceQuery.model_validate(query.model_dump())
        items: tuple[GuidanceItem, ...] = ()
        for _, _, item in self._items(query):
            if len(items) == self.limits.max_items:
                break
            proposed = _bundle((*items, item))
            if len(export_bundle(proposed)) <= self.limits.max_bytes:
                items = proposed.items
        return _bundle(items)

    def related(self, query: GuidanceQuery, *, max_items: int = 8) -> tuple[ExperienceProposal, ...]:
        query = GuidanceQuery.model_validate(query.model_dump())
        if type(max_items) is not int or not 1 <= max_items <= 8:
            raise ValueError("related methods must stay within eight reviewed source proposals")
        ranked = []
        for proposal in self.store.related_methods(query.access_scope, self.policy):
            score = _relevance(proposal, query)
            if score is not None:
                ranked.append((score, digest(proposal.model_dump()), proposal))
        return tuple(entry[2] for entry in sorted(ranked, key=lambda entry: (-entry[0], entry[1]))[:max_items])

    def validate(self, bundle: GuidanceBundle, query: GuidanceQuery) -> None:
        bundle = GuidanceBundle.model_validate(bundle.model_dump())
        query = GuidanceQuery.model_validate(query.model_dump())
        if (
            bundle.snapshot_id != _bundle(bundle.items).snapshot_id
            or len(bundle.items) > self.limits.max_items
            or len(export_bundle(bundle)) > self.limits.max_bytes
        ):
            raise StoreError("the guidance payload or its export limits changed")
        available = {item.id: item for _, _, item in self._items(query)}
        if any(available.get(item.id) != item for item in bundle.items):
            raise StoreError("guidance evidence, review, scope or version is no longer eligible")
