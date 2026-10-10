"""Check experience role boundaries, immutable guidance and evidence integrity."""

import json

import pytest
from pydantic import ValidationError

from experimental.experience.contracts import (
    BuildRequest,
    EvidenceLink,
    EvidenceView,
    ExperienceCondition,
    ExperienceEvent,
    ExperienceProposal,
    ExperienceReview,
    GuidanceBundle,
    GuidanceItem,
    OutcomeReceipt,
    RecordOrigin,
    ReviewIssue,
    digest,
    for_model,
)


@pytest.fixture
def event():
    origin = RecordOrigin(
        access_scope="private-project",
        run_id="private-run",
        lineage_id="private-lineage",
        record_id="private-record.json",
        revision_before="before",
    )
    view = EvidenceView(
        reference="event-" + origin.event_id(),
        situation="A mechanism result was not consumed.",
        treatment="Connect the result to its native consumer.",
        process_result="checked",
    )
    return ExperienceEvent(origin=origin, source_digest=digest({"hidden": "private-evaluation"}), view=view)


def condition():
    return ExperienceCondition(
        situation="A mechanism result is not consumed.", phase="design", mechanism_states=("not_consumed",)
    )


def proposal(event):
    return ExperienceProposal(
        condition=condition(),
        guidance="Verify the result consumer and its applied effect.",
        evidence=(EvidenceLink(reference=event.view.reference, relation="supports"),),
    )


@pytest.mark.parametrize("role", ["builder", "critic"])
def test_source_views_do_not_export_host_identities(event, role):
    text = json.dumps(for_model(event, role))
    assert "native consumer" in text and event.view.reference in text
    assert "private-project" not in text and "private-record.json" not in text and "private-evaluation" not in text


def test_curator_cannot_receive_source_events_or_unreviewed_proposals(event):
    assert for_model(event, "curator") == {}
    assert for_model(event.view, "curator") == {}
    assert for_model(proposal(event), "curator") == {}


def test_guidance_exports_only_methods_and_opaque_references(event):
    item = GuidanceItem(
        id="method-1",
        version=1,
        condition=condition(),
        guidance="Verify the actual result consumer.",
        evidence_refs=(event.view.reference,),
    )
    bundle = GuidanceBundle(snapshot_id="snapshot-1", items=(item,))
    shown = for_model(bundle, "curator")
    assert shown["items"][0]["evidence_refs"] == [event.view.reference]
    assert "treatment" not in json.dumps(shown) and "private-run" not in json.dumps(shown)
    assert for_model(bundle, "builder") == {}
    shown["items"][0]["guidance"] = "Changed outside the contract"
    assert item.guidance == "Verify the actual result consumer."
    with pytest.raises(ValidationError):
        item.version = 2


def test_guidance_refuses_raw_event_payloads_and_case_identifiers(event):
    values = dict(id="method-1", version=1, condition=condition(), guidance="Check the consumer.")
    with pytest.raises(ValidationError):
        GuidanceItem(**values, evidence_refs=("private-record.json",))
    with pytest.raises(ValidationError):
        GuidanceItem(**values, evidence_refs=(event.view.reference,), evidence=event.view.model_dump())


@pytest.mark.parametrize("decision", ["revise", "reject"])
def test_non_accepting_reviews_require_specific_issues(decision):
    with pytest.raises(ValidationError):
        ExperienceReview(proposal_index=0, decision=decision)
    issue = ReviewIssue(kind="too_vague", field="guidance", reason="Identify a condition and an observable action.")
    assert ExperienceReview(proposal_index=0, decision=decision, issues=(issue,)).issues == (issue,)
    with pytest.raises(ValidationError):
        ExperienceReview(proposal_index=0, decision="accept", issues=(issue,))


def test_duplicate_events_and_evidence_cannot_inflate_a_build_request(event):
    with pytest.raises(ValidationError):
        BuildRequest(events=(event.view, event.view))
    with pytest.raises(ValidationError):
        ExperienceProposal(condition=condition(), guidance="Check the consumer.", evidence=proposal(event).evidence * 2)


def test_a_bundle_cannot_mix_two_versions_of_one_method(event):
    first = GuidanceItem(
        id="method-1",
        version=1,
        condition=condition(),
        guidance="Check the consumer.",
        evidence_refs=(event.view.reference,),
    )
    with pytest.raises(ValidationError):
        GuidanceBundle(snapshot_id="snapshot-1", items=(first, first.model_copy(update={"version": 2})))


def test_behavior_support_requires_activation_and_real_observations(event):
    values = event.view.model_dump(exclude={"held", "basis", "activation"})
    with pytest.raises(ValidationError):
        EvidenceView(**values, held=True, basis="indirect", activation="unknown")
    with pytest.raises(ValidationError):
        EvidenceView(**values, held=True, basis="observation", activation="applied")
    with pytest.raises(ValidationError):
        OutcomeReceipt(access_scope="scope", revision_id="revision", held=True, basis="observation")


def test_applied_events_require_distinct_known_revisions(event):
    view = event.view.model_copy(update={"activation": "applied"})
    with pytest.raises(ValidationError):
        ExperienceEvent(origin=event.origin, source_digest=event.source_digest, revision_after="before", view=view)
    with pytest.raises(ValidationError):
        ExperienceEvent(
            origin=event.origin.model_copy(update={"revision_before": None}),
            source_digest=event.source_digest,
            revision_after="after",
            view=view,
        )


def test_projection_refuses_undeclared_subclass_fields(event):
    class Undeclared(EvidenceView):
        private_material: str

    value = Undeclared(**event.view.model_dump(), private_material="evaluation material")
    with pytest.raises(ValueError, match="undeclared"):
        for_model(value, "builder")


def test_conditions_reject_unsupported_states_and_stages():
    with pytest.raises(ValidationError):
        ExperienceCondition(situation="A result failed.", phase="design", mechanism_states=("needs_work",))
    with pytest.raises(ValidationError):
        ExperienceCondition(situation="A result failed.", phase="runtime")


def test_blank_guidance_is_not_a_valid_method(event):
    with pytest.raises(ValidationError):
        ExperienceProposal(condition=condition(), guidance=" \n ", evidence=proposal(event).evidence)


def test_projection_refuses_declarations_of_non_fields(event):
    class InvalidDeclaration(EvidenceView):
        AUDIENCES = {**EvidenceView.AUDIENCES, "model_config": frozenset({"builder"})}

    with pytest.raises(ValueError, match="unknown experience fields"):
        for_model(InvalidDeclaration(**event.view.model_dump()), "builder")
