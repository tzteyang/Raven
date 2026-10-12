"""Validate evidence independence, scoped conclusions and recommendation state transitions."""

import pytest

from experimental.harness.experience.admission import AdmissionPolicy
from experimental.harness.experience.contracts import EvidenceLink, ExperienceEvent, digest
from experimental.harness.experience.store import ExperienceStore, StoreConflictError
from tests.experience_helpers import event, process_checked, proposal, reviewed

POLICY = AdmissionPolicy(critic_digest=digest({"rule": "test-critic"}))


def changed_origin(source, **updates):
    origin = source.origin.model_copy(update=updates)
    view = source.view.model_copy(
        update={"reference": "event-" + origin.event_id(), "scope_kind": "root" if origin.scope == "root" else "child"}
    )
    return ExperienceEvent(
        origin=origin, source_digest=source.source_digest, revision_after=source.revision_after, view=view
    )


def unknown_outcome(source):
    return source.model_copy(
        update={
            "view": source.view.model_copy(
                update={"activation": "unknown", "held": None, "basis": "unknown", "observations": ()}
            )
        }
    )


def method_with(sources, **updates):
    return proposal(sources[0]).model_copy(
        update={
            "evidence": tuple(EvidenceLink(reference=source.view.reference, relation="supports") for source in sources),
            **updates,
        }
    )


def test_policy_cannot_bypass_independence_with_a_one_run_minimum():
    with pytest.raises(ValueError):
        AdmissionPolicy(critic_digest=POLICY.critic_digest, min_independent_runs=1)
    with pytest.raises(ValueError):
        AdmissionPolicy(critic_digest="a model confidence score")


def test_one_reviewed_run_stays_candidate_then_independent_evidence_accumulates(tmp_path):
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        first = reviewed(store, (event("one"),))
        initial = store.refresh_admission("project", POLICY)[0]
        assert initial.status == "candidate" and initial.independent_runs == 1
        second = reviewed(store, (event("two"),))
        assert first.id == second.id and second.version == 2
        assert not store.recommendations("project", POLICY)
        qualified = store.refresh_admission("project", POLICY)[0]
        assert qualified.status == "supported" and qualified.independent_runs == 2
        assert qualified.reference == second and len(qualified.evidence_refs) == 2
        assert len(store.recommendations("project", POLICY)) == 1
        assert store.refresh_admission("project", POLICY)[0] == qualified
        duplicate = reviewed(store, (event("two"),))
        assert duplicate == second and len(store.candidates("project")) == 2
        assert store.refresh_admission("project", POLICY)[0] == qualified


@pytest.mark.parametrize("identity", ["run", "lineage", "source"])
def test_shared_identity_prevents_independent_credit(tmp_path, identity):
    first, second = event("one"), event("two")
    if identity == "run":
        second = changed_origin(second, run_id=first.origin.run_id)
    elif identity == "lineage":
        second = changed_origin(second, lineage_id=first.origin.lineage_id)
    else:
        second = second.model_copy(update={"source_digest": first.source_digest})
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        reviewed(store, (first, second), method_with((first, second)))
        assessment = store.refresh_admission("project", POLICY)[0]
        assert assessment.status == "candidate" and assessment.independent_runs == 1


def test_root_child_and_multiple_inputs_in_one_run_do_not_add_credit(tmp_path):
    first = event("one")
    second = changed_origin(event("two"), run_id=first.origin.run_id, scope="child/helper", input_key="another-input")
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        reviewed(store, (first, second), method_with((first, second)))
        assert store.refresh_admission("project", POLICY)[0].independent_runs == 1


def test_transitive_duplicate_bridge_cannot_create_two_independent_groups(tmp_path):
    first, second = event("one"), event("two")
    bridge = changed_origin(event("bridge"), run_id=first.origin.run_id, lineage_id=second.origin.lineage_id)
    method = method_with((first, second)).model_copy(
        update={
            "evidence": (
                *method_with((first, second)).evidence,
                EvidenceLink(reference=bridge.view.reference, relation="context"),
            )
        }
    )
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        reviewed(store, (first, second, bridge), method)
        assert store.refresh_admission("project", POLICY)[0].independent_runs == 1


@pytest.mark.parametrize("weakness", ["unknown", "indirect", "changed", "incomparable"])
def test_weak_or_changed_outcomes_do_not_support_behavior_claims(tmp_path, weakness):
    first, second = event("one"), event("two")
    if weakness == "unknown":
        second = unknown_outcome(second)
    else:
        update = (
            {"basis": "indirect"}
            if weakness == "indirect"
            else {"comparability": "changed" if weakness == "changed" else "unknown"}
        )
        second = second.model_copy(update={"view": second.view.model_copy(update=update)})
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        reviewed(store, (first, second), method_with((first, second)))
        assessment = store.refresh_admission("project", POLICY)[0]
        assert assessment.status == "candidate" and assessment.independent_runs == 1


def test_checked_process_evidence_can_support_only_an_explicit_process_method(tmp_path):
    sources = tuple(unknown_outcome(event(name)) for name in ("one", "two"))
    process = method_with(
        sources, support_kind="process", guidance="Run the contract's structural artifact checks before installation."
    )
    behavior = method_with(sources)
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        reference = reviewed(store, sources, process)
        reviewed(store, sources, behavior)
        assert all(assessment.status == "candidate" for assessment in store.refresh_admission("project", POLICY))
        process_checked(store, reference, sources)
        assessments = {assessment.reference.id: assessment for assessment in store.refresh_admission("project", POLICY)}
        by_kind = {
            candidate["proposal"]["support_kind"]: assessments[candidate["id"]]
            for candidate in store.candidates("project")
        }
        assert by_kind["process"].status == "supported"
        assert by_kind["behavior"].status == "candidate"


@pytest.mark.parametrize("declared_relation", ["supports", "contradicts"])
def test_explicit_negative_outcome_or_declared_contradiction_blocks_recommendation(tmp_path, declared_relation):
    sources = (event("one"), event("two"))
    negative = event("negative").model_copy(update={"view": event("negative").view.model_copy(update={"held": False})})
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        reviewed(store, sources, method_with(sources))
        assert store.refresh_admission("project", POLICY)[0].status == "supported"
        method = proposal(negative).model_copy(
            update={"evidence": (EvidenceLink(reference=negative.view.reference, relation=declared_relation),)}
        )
        reviewed(store, (negative,), method)
        assert not store.recommendations("project", POLICY)
        assessment = store.refresh_admission("project", POLICY)[0]
        assert assessment.status == "contested" and assessment.independent_runs == 2
        assert not store.recommendations("project", POLICY)


def test_same_method_under_a_new_critic_requires_current_reviews_for_each_support(tmp_path):
    sources = (event("one"), event("two"))
    next_critic = {"rule": "next-critic"}
    next_policy = AdmissionPolicy(critic_digest=digest(next_critic))
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        reviewed(store, sources, method_with(sources))
        assert store.refresh_admission("project", POLICY)[0].status == "supported"
        assert not store.recommendations("project", next_policy)
        assert store.refresh_admission("project", next_policy)[0].status == "candidate"
        reviewed(store, (event("three"),), critic=next_critic)
        assessment = store.refresh_admission("project", next_policy)[0]
        assert assessment.status == "candidate" and assessment.independent_runs == 1
        assert not store.recommendations("project", POLICY)


def test_source_correction_invalidates_the_whole_method_and_retires_dependent_versions(tmp_path):
    first, second = event("one"), event("two")
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        reviewed(store, (first,))
        reviewed(store, (second,))
        assert store.refresh_admission("project", POLICY)[0].status == "supported"
        corrected = first.model_copy(update={"source_digest": digest("corrected full source")})
        store.ingest(corrected, expected_version=1)
        assert not store.recommendations("project", POLICY)
        assert store.candidates("project")[0]["status"] == "retired"
        assessment = store.refresh_admission("project", POLICY)[0]
        assert assessment.status == "candidate" and assessment.independent_runs == 1


def test_revoked_sources_cannot_be_reingested_or_counted_again(tmp_path):
    first, second = event("one"), event("two")
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        reviewed(store, (first,))
        latest = reviewed(store, (second,))
        store.refresh_admission("project", POLICY)
        assert store.revoke_event("project", second.view.reference, expected_version=1) == 2
        with pytest.raises(StoreConflictError, match="revoked"):
            store.ingest(second, expected_version=2)
        assert store.refresh_admission("project", POLICY)[0].status == "retired"
        assert not store.recommendations("project", POLICY)
        with pytest.raises(StoreConflictError):
            store.retire_candidate("project", latest.model_copy(update={"version": 1}))
        store.retire_candidate("project", latest)
        assert all(candidate["status"] == "retired" for candidate in store.candidates("project"))


def test_similar_wording_is_not_merged_into_unreviewed_semantic_equivalence(tmp_path):
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        reviewed(store, (event("one"),))
        reviewed(
            store,
            (event("two"),),
            proposal(event("two"), "Inspect and connect the actual consumer, then verify its result."),
        )
        assessments = store.refresh_admission("project", POLICY)
        assert len(assessments) == 2 and all(assessment.status == "candidate" for assessment in assessments)


def test_changing_critic_cannot_erase_an_unresolved_historical_contradiction(tmp_path):
    next_critic = {"rule": "next-critic"}
    next_policy = AdmissionPolicy(critic_digest=digest(next_critic))
    negative = event("negative").model_copy(update={"view": event("negative").view.model_copy(update={"held": False})})
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        reviewed(store, (negative,))
        reviewed(store, (event("one"),), critic=next_critic)
        reviewed(store, (event("two"),), critic=next_critic)
        assessment = store.refresh_admission("project", next_policy)[0]
        assert assessment.status == "contested" and assessment.independent_runs == 2
        assert not store.recommendations("project", next_policy)


def test_process_checks_do_not_transfer_to_differently_worded_methods(tmp_path):
    sources = (event("one"), event("two"))
    first = method_with(
        sources,
        support_kind="process",
        guidance="Check the artifact's consumer declaration against its structural contract.",
    )
    second = first.model_copy(
        update={"guidance": "Check the artifact's action-gate declaration against its structural contract."}
    )
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        reference = reviewed(store, sources, first)
        reviewed(store, sources, second)
        process_checked(store, reference, sources)
        assessments = {assessment.reference.id: assessment for assessment in store.refresh_admission("project", POLICY)}
        assert assessments[reference.id].status == "supported"
        assert sum(assessment.status == "supported" for assessment in assessments.values()) == 1


def test_negative_exact_process_check_blocks_a_method_with_other_positive_checks(tmp_path):
    sources = (event("one"), event("two"))
    method = method_with(
        sources,
        support_kind="process",
        guidance="Check the consumer declaration against the generated artifact's structural contract.",
    )
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        reference = reviewed(store, sources, method)
        process_checked(store, reference, sources)
        assert store.refresh_admission("project", POLICY)[0].status == "supported"
        negative = event("negative")
        reference = reviewed(
            store, (negative,), proposal(negative, method.guidance).model_copy(update={"support_kind": "process"})
        )
        process_checked(store, reference, (negative,), passed=False)
        assessment = store.refresh_admission("project", POLICY)[0]
        assert assessment.status == "contested" and assessment.independent_runs == 2
        assert not store.recommendations("project", POLICY)


def test_guidance_reference_limit_does_not_cap_the_internal_independent_count(tmp_path):
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        for number in range(18):
            reviewed(store, (event(f"independent-{number}"),))
        assessment = store.refresh_admission("project", POLICY)[0]
        assert assessment.status == "supported" and assessment.independent_runs == 18
        assert len(assessment.evidence_refs) == 16
