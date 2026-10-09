"""Check read-only filtering, whole-item budgets, snapshot stability and withdrawal."""

import json

import pytest

from experimental.experience.admission import AdmissionPolicy
from experimental.experience.contracts import digest, for_model
from experimental.experience.retrieve import ExperienceRetriever, GuidanceQuery, RetrievalLimits, export_bundle
from experimental.experience.store import ExperienceStore, StoreError
from tests.experience_helpers import event, proposal, reviewed

POLICY = AdmissionPolicy(critic_digest=digest({"rule": "test-critic"}))


def query(**updates):
    return GuidanceQuery(
        **{
            "access_scope": "project",
            "situation": "A mechanism result is not consumed by its consumer.",
            "phase": "design",
            "scope_kind": "root",
            **updates,
        }
    )


def supported(store, guidance=None, **conditions):
    sources = (event("one"), event("two"))
    method = proposal(sources[0]) if guidance is None else proposal(sources[0], guidance)
    if conditions:
        method = method.model_copy(update={"condition": method.condition.model_copy(update=conditions)})
    for source in sources:
        reviewed(
            store,
            (source,),
            proposal(source).model_copy(update={"condition": method.condition, "guidance": method.guidance}),
        )
    store.refresh_admission("project", POLICY)


def test_guidance_is_an_immutable_anonymous_projection_and_retrieval_does_not_write(tmp_path):
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        supported(store)
        changes = store.connection.total_changes
        reader = ExperienceRetriever(store, POLICY)
        bundle = reader.retrieve(query())
        assert len(bundle.items) == 1 and len(bundle.items[0].evidence_refs) == 2
        assert reader.retrieve(query()) == bundle
        reader.validate(bundle, query())
        assert store.connection.total_changes == changes
        public = export_bundle(bundle).decode()
        assert json.loads(public) == for_model(bundle, "curator")
        assert not any(
            word in public for word in ("observations", "treatment", "test-critic", '"project"', '"one"', '"two"')
        )


@pytest.mark.parametrize(
    "updates",
    [
        {"access_scope": "another-project"},
        {"phase": "repair"},
        {"scope_kind": "child"},
        {"situation": "Unrelated scheduling deadlines"},
    ],
)
def test_scope_stage_scope_kind_and_situation_filter_incompatible_methods(tmp_path, updates):
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        supported(store, scope_kind="root")
        assert not ExperienceRetriever(store, POLICY).retrieve(query(**updates)).items


def test_contract_capability_and_mechanism_requirements_are_checked_before_ranking(tmp_path):
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        supported(
            store,
            required_capabilities=("native-consumer",),
            contract_ids=("contract-v1",),
            mechanism_states=("not_consumed",),
        )
        reader = ExperienceRetriever(store, POLICY)
        assert not reader.retrieve(query()).items
        assert not reader.retrieve(query(capabilities=("native-consumer",), contract_ids=("contract-v1",))).items
        matching = query(
            capabilities=("native-consumer",), contract_ids=("contract-v1",), mechanism_states=("not_consumed",)
        )
        assert len(reader.retrieve(matching).items) == 1
        assert not reader.retrieve(
            query(capabilities=("native-consumer",), contract_ids=("contract-v2",), mechanism_states=("not_consumed",))
        ).items


def test_candidates_need_an_explicit_current_admission_before_retrieval(tmp_path):
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        reviewed(store, (event("one"),))
        reviewed(store, (event("two"),))
        reader = ExperienceRetriever(store, POLICY)
        assert not reader.retrieve(query()).items
        store.refresh_admission("project", POLICY)
        assert len(reader.retrieve(query()).items) == 1
        changed_policy = AdmissionPolicy(critic_digest=POLICY.critic_digest, min_independent_runs=3)
        assert not ExperienceRetriever(store, changed_policy).retrieve(query()).items


def test_count_and_utf8_byte_limits_drop_whole_items_without_truncating_methods(tmp_path):
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        for number in range(6):
            supported(store, guidance=f"Verify the consumer’s mechanism and its applied effect using check {number}.")
        full = ExperienceRetriever(store, POLICY).retrieve(query())
        assert len(full.items) == 4
        assert len(export_bundle(full)) > len(export_bundle(full).decode())
        assert len(ExperienceRetriever(store, POLICY, limits=RetrievalLimits(max_items=2)).retrieve(query()).items) == 2
        first_bytes = len(export_bundle(full.model_copy(update={"items": full.items[:1]})))
        limited = ExperienceRetriever(store, POLICY, limits=RetrievalLimits(max_bytes=first_bytes)).retrieve(query())
        assert limited.items == full.items[:1] and len(export_bundle(limited)) <= first_bytes
        for item in limited.items:
            assert item.condition and item.guidance.endswith(".") and item.evidence_refs
        empty = ExperienceRetriever(store, POLICY, limits=RetrievalLimits(max_bytes=150)).retrieve(query())
        assert not empty.items


def test_oversized_top_item_is_skipped_and_a_smaller_complete_item_can_fit(tmp_path):
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        supported(store, guidance="consumer mechanism applied effect " + "verify " * 120)
        supported(store, guidance="Check the consumer.")
        bundle = ExperienceRetriever(store, POLICY, limits=RetrievalLimits(max_bytes=1000)).retrieve(query())
        assert len(bundle.items) == 1 and bundle.items[0].guidance == "Check the consumer."


def test_default_export_stays_within_8_kib_even_when_four_methods_would_overflow(tmp_path):
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        for number in range(4):
            supported(
                store,
                guidance=f"Verify consumer {number}. " + "Observe the consumer’s actual result. " * 25,
                situation="The consumer does not consume the mechanism output. " * 20,
                limits=("Check the current host contract before using this method. " * 25,),
            )
        bundle = ExperienceRetriever(store, POLICY).retrieve(query())
        assert 0 < len(bundle.items) < 4 and len(export_bundle(bundle)) <= 8192


def test_withdrawal_invalidates_a_pinned_bundle_even_if_other_support_remains(tmp_path):
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        supported(store)
        reviewed(store, (event("three"),))
        store.refresh_admission("project", POLICY)
        reader = ExperienceRetriever(store, POLICY)
        previous = reader.retrieve(query())
        store.revoke_event("project", event("one").view.reference, expected_version=1)
        assert not reader.retrieve(query()).items
        with pytest.raises(StoreError, match="no longer eligible"):
            reader.validate(previous, query())
        store.refresh_admission("project", POLICY)
        current = reader.retrieve(query())
        assert current.items and current.snapshot_id != previous.snapshot_id
        assert event("one").view.reference not in current.items[0].evidence_refs


def test_changed_or_forged_guidance_payload_cannot_pass_snapshot_validation(tmp_path):
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        supported(store)
        reader = ExperienceRetriever(store, POLICY)
        bundle = reader.retrieve(query())
        altered = bundle.model_copy(
            update={"items": (bundle.items[0].model_copy(update={"guidance": "Unreviewed replacement"}),)}
        )
        with pytest.raises(StoreError, match="payload"):
            reader.validate(altered, query())
        with pytest.raises(StoreError, match="eligible"):
            reader.validate(bundle, query(access_scope="another-project"))


@pytest.mark.parametrize(
    "kwargs", [{"max_items": 0}, {"max_items": 5}, {"max_bytes": 10}, {"max_bytes": 8193}, {"max_items": True}]
)
def test_export_limits_cannot_exceed_transport_bounds(kwargs):
    with pytest.raises(ValueError):
        RetrievalLimits(**kwargs)
