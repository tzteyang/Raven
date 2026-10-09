"""Check conservative adaptation, source grants and post-revision outcome correlation."""

import json
from copy import deepcopy

import pytest

from experimental.curator.raven_adapter.inspection import fingerprint
from experimental.experience.contracts import OutcomeReceipt, RecordOrigin, digest, for_model
from experimental.experience.records import RecordAccess, RecordRejectedError, normalize, read_record

FIELDS = frozenset({"plan.understanding", "change.target", "change.reason", "outcome.held", "outcome.observations"})
ARTIFACT = {"values": {"action.config": {"temperature": 0.2}}, "files": {}}


@pytest.fixture
def origin():
    return RecordOrigin(
        access_scope="project-1", run_id="run-1", lineage_id="run-1", record_id="record-1", revision_before="before"
    )


@pytest.fixture
def access():
    return RecordAccess(access_scope="project-1", fields=FIELDS)


@pytest.fixture
def record():
    return {
        "task_id": "private-task",
        "active_artifact_id": fingerprint(ARTIFACT),
        "feedback": {
            "items": [{"reference": "private-standard", "expected": "private-answer"}],
            "metrics": {"private-score": 1},
        },
        "generated": {
            "candidate": {
                "artifact": ARTIFACT,
                "plan": {
                    "understanding": "A produced result did not reach its consumer.",
                    "changes": [
                        {
                            "target": "action.config",
                            "reason": "Connect the result to its consumer.",
                            "expected": "private-expected",
                            "verification": "private-verification",
                        },
                        {"target": "memory.config", "reason": "Preserve the committed result."},
                    ],
                },
            },
            "validation": {"errors": [], "warnings": []},
            "trace": [{"expected": "private-trace"}],
        },
    }


def test_native_artifact_identity_matches_the_independent_digest():
    assert digest(ARTIFACT) == fingerprint(ARTIFACT)


def test_joint_child_changes_remain_one_applied_curation_without_child_behavior_credit(record, origin, access):
    child = deepcopy(record["generated"])
    record["generated"]["candidate"]["plan"]["changes"] = []
    record["child_changes"] = {"one": child, "two": deepcopy(child)}
    record["active_artifact_id"] = "joint-revision"
    record["changed"] = True
    event = normalize(record, origin=origin, access=access)
    assert event.view.activation == "applied" and event.view.process_result == "checked"
    assert event.view.held is None and event.view.scope_kind == "root"
    assert "Delegated treatment" in event.view.treatment


def test_joint_changes_remain_one_event_and_restricted_fields_are_dropped(record, origin, access):
    event = normalize(record, origin=origin, access=access)
    shown = json.dumps(for_model(event, "builder"))
    assert "Connect the result" in shown and "Preserve the committed result" in shown
    assert "private-" not in shown and "expected" not in shown and "verification" not in shown
    assert event.view.activation == "applied" and event.view.process_result == "checked"
    assert event.view.held is None and event.view.basis == "unknown"


def test_absent_or_foreign_source_grants_are_rejected(record, origin):
    for access in (RecordAccess(access_scope="project-1"), RecordAccess(access_scope="project-2", fields=FIELDS)):
        with pytest.raises(RecordRejectedError, match="grant"):
            normalize(record, origin=origin, access=access)


def test_grants_do_not_expand_to_sibling_fields(record, origin):
    access = RecordAccess(access_scope="project-1", fields=frozenset({"plan.understanding", "change.reason"}))
    event = normalize(record, origin=origin, access=access)
    assert "action.config" not in event.view.treatment and "memory.config" not in event.view.treatment
    assert "Connect the result" in event.view.treatment


def test_legacy_joint_changes_are_not_relabelled_as_an_individual_requirement(record, origin, access):
    with pytest.raises(RecordRejectedError, match="per-input"):
        normalize(record, origin=origin.model_copy(update={"input_key": "requirement-1"}), access=access)


def test_before_state_is_required_to_claim_activation(record, origin, access):
    event = normalize(record, origin=origin.model_copy(update={"revision_before": None}), access=access)
    assert event.view.activation == "unknown" and event.view.held is None


def test_a_proposal_retaining_the_old_revision_has_no_behavior_credit(record, origin, access):
    record["active_artifact_id"] = "before"
    receipt = OutcomeReceipt(access_scope="project-1", revision_id="before", held=True)
    event = normalize(record, origin=origin, access=access, outcome=receipt)
    assert event.view.activation == "not_applied" and event.view.held is None


@pytest.mark.parametrize("field", ["error", "paused", "gap"])
def test_incomplete_or_failed_curation_is_not_a_success(record, origin, access, field):
    record[field] = "Stopped before completion"
    receipt = OutcomeReceipt(access_scope="project-1", revision_id=record["active_artifact_id"], held=True)
    event = normalize(record, origin=origin, access=access, outcome=receipt)
    assert event.view.activation == ("unknown" if field == "error" else "not_applied")
    assert event.view.held is None


def test_composition_is_not_inferred_from_a_root_artifact_digest(record, origin, access):
    record["composition"] = True
    assert normalize(record, origin=origin, access=access).view.activation == "unknown"


def test_validation_failure_precedes_retention_and_has_no_behavior_credit(record, origin, access):
    record["generated"]["candidate"]["plan"]["changes"] = []
    record["generated"]["candidate"]["plan"]["design"] = "Preserve the current mechanism."
    record["generated"]["validation"]["errors"] = ["Candidate failed validation"]
    access = access.model_copy(update={"fields": access.fields | {"plan.design"}})
    event = normalize(record, origin=origin, access=access)
    assert event.view.process_result == "failed" and event.view.activation == "unknown"


def test_matching_observations_support_a_post_revision_result(record, origin, access):
    receipt = OutcomeReceipt(
        access_scope="project-1",
        revision_id=record["active_artifact_id"],
        held=True,
        basis="observation",
        comparability="comparable",
        observations=("The native consumer applied the result.",),
    )
    event = normalize(record, origin=origin, access=access, outcome=receipt)
    assert event.view.held is True and event.view.basis == "observation"
    assert event.view.observations == receipt.observations


@pytest.mark.parametrize("change", ["access_scope", "revision_id", "scope", "input_key"])
def test_another_scope_or_revision_cannot_supply_the_outcome(record, origin, access, change):
    values = dict(access_scope="project-1", revision_id=record["active_artifact_id"], held=True)
    values[change] = {
        "access_scope": "project-2",
        "revision_id": "another",
        "scope": "child/other",
        "input_key": "other",
    }[change]
    event = normalize(record, origin=origin, access=access, outcome=OutcomeReceipt(**values))
    assert event.view.held is None and event.view.observations == ()


def test_human_non_recurrence_is_kept_as_indirect_support(record, origin, access):
    receipt = OutcomeReceipt(access_scope="project-1", revision_id=record["active_artifact_id"], held=True)
    event = normalize(record, origin=origin, access=access, outcome=receipt)
    assert event.view.held is True and event.view.basis == "indirect"


def test_withheld_observations_do_not_become_strong_support(record, origin):
    access = RecordAccess(access_scope="project-1", fields=FIELDS - {"outcome.observations"})
    receipt = OutcomeReceipt(
        access_scope="project-1",
        revision_id=record["active_artifact_id"],
        held=True,
        basis="observation",
        observations=("An actual effect was observed.",),
    )
    event = normalize(record, origin=origin, access=access, outcome=receipt)
    assert event.view.held is True and event.view.basis == "indirect" and not event.view.observations


def test_denied_behavior_results_stay_unknown(record, origin):
    access = RecordAccess(access_scope="project-1", fields=FIELDS - {"outcome.held"})
    receipt = OutcomeReceipt(access_scope="project-1", revision_id=record["active_artifact_id"], held=True)
    assert normalize(record, origin=origin, access=access, outcome=receipt).view.held is None


def test_late_observations_and_source_corrections_preserve_event_identity(record, origin, access):
    first = normalize(record, origin=origin, access=access)
    receipt = OutcomeReceipt(access_scope="project-1", revision_id=record["active_artifact_id"], held=False)
    later = normalize(record, origin=origin, access=access, outcome=receipt)
    assert later.view.reference == first.view.reference and later.view.held is False
    corrected = deepcopy(record)
    corrected["generated"]["candidate"]["plan"]["understanding"] = "The trigger did not fire."
    updated = normalize(corrected, origin=origin, access=access)
    assert updated.view.reference == first.view.reference and updated.source_digest != first.source_digest


def test_explicit_blocked_text_is_checked_after_projection(record, origin, access):
    record["generated"]["candidate"]["plan"]["understanding"] = "WITHHELD evidence is present."
    with pytest.raises(RecordRejectedError, match="blocked"):
        normalize(record, origin=origin, access=access.model_copy(update={"blocked_text": ("withheld",)}))


def test_missing_context_does_not_get_invented(record, origin, access):
    del record["generated"]["candidate"]["plan"]["understanding"]
    with pytest.raises(RecordRejectedError, match="missing history"):
        normalize(record, origin=origin, access=access)


def test_reader_enforces_root_size_and_parse_boundaries(record, origin, access, tmp_path):
    root = tmp_path / "records"
    root.mkdir()
    path = root / "curation.json"
    path.write_text(json.dumps(record))
    assert read_record(path, root=root, origin=origin, access=access).view.activation == "applied"
    with pytest.raises(RecordRejectedError, match="byte limit"):
        read_record(path, root=root, origin=origin, access=access, max_bytes=10)
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps(record))
    link = root / "linked.json"
    link.symlink_to(outside)
    with pytest.raises(RecordRejectedError, match="outside"):
        read_record(link, root=root, origin=origin, access=access)
    path.write_text("{partial")
    with pytest.raises(RecordRejectedError, match="unreadable"):
        read_record(path, root=root, origin=origin, access=access)
