"""Check database versions, source correction and atomic reviewed-candidate writes."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from experimental.harness.experience.admission import AdmissionPolicy, ProcessCheckReceipt
from experimental.harness.experience.contracts import EvidenceLink, digest, for_model
from experimental.harness.experience.state import BuildState
from experimental.harness.experience.store import ExperienceStore, StoreConflictError, StoreError
from tests.experience_helpers import accept, event, proposal, reviewed

_LEGACY_SCHEMA = (
    "CREATE TABLE events (scope TEXT, id TEXT, view_digest TEXT, source_digest TEXT, version INTEGER, payload TEXT, PRIMARY KEY(scope,id))",
    "CREATE TABLE tasks (id TEXT PRIMARY KEY, scope TEXT, input_id TEXT, identities TEXT, snapshots TEXT, state TEXT, version INTEGER, lease TEXT, expires REAL)",
    "CREATE TABLE candidates (scope TEXT, id TEXT, version INTEGER, proposal_digest TEXT, proposal TEXT, review TEXT, identities TEXT, task_id TEXT, status TEXT, PRIMARY KEY(scope,id,version))",
    "CREATE TABLE links (scope TEXT, candidate_id TEXT, candidate_version INTEGER, event_id TEXT, view_digest TEXT, relation TEXT, PRIMARY KEY(scope,candidate_id,candidate_version,event_id))",
)


def legacy_database(path):
    sources = (event("one"), event("two"))
    method = proposal(sources[0]).model_copy(
        update={
            "evidence": tuple(EvidenceLink(reference=source.view.reference, relation="supports") for source in sources)
        }
    )
    raw_method = method.model_dump(exclude={"support_kind"})
    identity = digest({"scope": "project", "condition": raw_method["condition"], "guidance": method.guidance})
    identities = {"builder": {}, "critic": {"rule": "test-critic"}}
    snapshots = {source.view.reference: digest(for_model(source.view, "builder")) for source in sources}
    with sqlite3.connect(path) as connection:
        for statement in _LEGACY_SCHEMA:
            connection.execute(statement)
        connection.execute("PRAGMA user_version=1")
        connection.execute(
            "INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "legacy-task",
                "project",
                "legacy-input",
                json.dumps(identities),
                json.dumps(snapshots),
                BuildState(status="complete").model_dump_json(),
                1,
                None,
                0,
            ),
        )
        connection.execute(
            "INSERT INTO candidates VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "project",
                identity,
                1,
                digest(raw_method),
                json.dumps(raw_method),
                accept().model_dump_json(),
                json.dumps(identities),
                "legacy-task",
                "candidate",
            ),
        )
        for source in sources:
            connection.execute(
                "INSERT INTO events VALUES (?,?,?,?,?,?)",
                (
                    "project",
                    source.view.reference,
                    snapshots[source.view.reference],
                    source.source_digest,
                    1,
                    source.model_dump_json(),
                ),
            )
            connection.execute(
                "INSERT INTO links VALUES (?,?,?,?,?,?)",
                ("project", identity, 1, source.view.reference, snapshots[source.view.reference], "supports"),
            )


def open_task(store, value, task_id="task-1"):
    return store.open_task(task_id, digest(value.view.model_dump()), {"builder": {}, "critic": {}}, (value,), ttl=60)


def test_unknown_or_foreign_database_is_not_migrated(tmp_path):
    for number, statement in enumerate(("PRAGMA user_version=99", "CREATE TABLE unrelated (value TEXT)")):
        path = tmp_path / f"unknown-{number}.sqlite"
        connection = sqlite3.connect(path)
        connection.execute(statement)
        connection.commit()
        connection.close()
        with pytest.raises(StoreError, match="schema"):
            ExperienceStore(path)


def test_source_ingestion_is_idempotent_and_updates_require_the_current_version(tmp_path):
    source = event()
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        assert store.ingest(source) == store.ingest(source) == 1
        changed = source.model_copy(update={"source_digest": digest("corrected")})
        with pytest.raises(StoreConflictError):
            store.ingest(changed)
        assert store.ingest(changed, expected_version=1) == 2
        with pytest.raises(StoreConflictError):
            store.ingest(source, expected_version=1)


def test_an_active_task_cannot_be_claimed_by_another_connection(tmp_path):
    path = tmp_path / "experience.sqlite"
    source = event()
    with ExperienceStore(path) as first, ExperienceStore(path) as second:
        open_task(first, source)
        with pytest.raises(StoreConflictError, match="active owner"):
            open_task(second, source)


def test_source_correction_retires_exact_reviewed_versions(tmp_path):
    source = event()
    method = proposal(source)
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        handle, _ = open_task(store, source)
        state = BuildState(proposals=(method,), reviews=(accept(),))
        store.save(handle, state, ttl=60, finish=True, accepted=((method, accept()),))
        assert store.candidates("project")[0]["status"] == "candidate"
        changed = source.model_copy(update={"view": source.view.model_copy(update={"situation": "Corrected context"})})
        store.ingest(changed, expected_version=1)
        assert store.candidates("project")[0]["status"] == "retired"


def test_wrong_proposal_review_pair_cannot_commit_any_candidate(tmp_path):
    source = event()
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        handle, before = open_task(store, source)
        method = proposal(source)
        state = BuildState(proposals=(method,), reviews=(accept(),))
        changed = proposal(source, "An unreviewed replacement")
        with pytest.raises(StoreError, match="exact proposal"):
            store.save(handle, state, ttl=60, accepted=((changed, accept()),))
        assert not store.candidates("project") and store.task(handle.id) == before


def test_foreign_evidence_rolls_back_candidate_and_checkpoint_together(tmp_path):
    source = event()
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        handle, before = open_task(store, source)
        foreign = proposal(event("foreign", scope="another-project"))
        state = BuildState(proposals=(foreign,), reviews=(accept(),))
        with pytest.raises(StoreConflictError, match="foreign"):
            store.save(handle, state, ttl=60, accepted=((foreign, accept()),))
        assert not store.candidates("project") and store.task(handle.id) == before


def test_concurrent_reviews_do_not_create_duplicate_candidate_versions(tmp_path):
    path = tmp_path / "experience.sqlite"
    source = event()
    method = proposal(source)
    with ExperienceStore(path):
        pass
    barrier = Barrier(2)

    def save(number):
        with ExperienceStore(path) as store:
            handle, _ = open_task(store, source, f"task-{number}")
            state = BuildState(proposals=(method,), reviews=(accept(),))
            barrier.wait(timeout=5)
            _, completed = store.save(handle, state, ttl=60, finish=True, accepted=((method, accept()),))
            return completed.accepted

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = tuple(workers.map(save, range(2)))
    assert results[0] == results[1]
    with ExperienceStore(path) as store:
        assert len(store.candidates("project")) == 1


def test_legacy_schema_requires_explicit_atomic_migration_without_granting_recommendation(tmp_path):
    path = tmp_path / "legacy.sqlite"
    legacy_database(path)
    before = path.read_bytes()
    with pytest.raises(StoreError, match="explicit migration"):
        ExperienceStore(path)
    assert path.read_bytes() == before
    policy = AdmissionPolicy(critic_digest=digest({"rule": "test-critic"}))
    with ExperienceStore(path, migrate=True) as store:
        assert store.connection.execute("PRAGMA user_version").fetchone()[0] == 2
        assessment = store.refresh_admission("project", policy)[0]
        assert assessment.status == "candidate" and assessment.reasons == ("support_kind_required",)
        assert not store.recommendations("project", policy)
        assert store.task("legacy-task").status == "complete"
    with ExperienceStore(path) as reopened:
        assert len(reopened.candidates("project")) == 1


def test_failed_legacy_migration_rolls_back_columns_and_version(tmp_path):
    path = tmp_path / "legacy.sqlite"
    legacy_database(path)
    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE tasks SET snapshots='invalid json'")
    with pytest.raises(ValueError):
        ExperienceStore(path, migrate=True)
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert "sources" not in {row[1] for row in connection.execute("PRAGMA table_info(tasks)")}


def test_private_source_change_during_review_cannot_publish_against_a_new_version(tmp_path):
    source = event()
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        handle, before = open_task(store, source)
        store.ingest(
            source.model_copy(update={"source_digest": digest("corrected private material")}), expected_version=1
        )
        method = proposal(source)
        state = BuildState(proposals=(method,), reviews=(accept(),))
        with pytest.raises(StoreConflictError, match="changed after review"):
            store.save(handle, state, ttl=60, finish=True, accepted=((method, accept()),))
        assert not store.candidates("project") and store.task(handle.id) == before


def test_revocation_during_review_cannot_publish_and_rolls_back_its_checkpoint(tmp_path):
    source = event()
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        handle, before = open_task(store, source)
        store.revoke_event("project", source.view.reference, expected_version=1)
        method = proposal(source)
        state = BuildState(proposals=(method,), reviews=(accept(),))
        with pytest.raises(StoreConflictError):
            store.save(handle, state, ttl=60, finish=True, accepted=((method, accept()),))
        assert not store.candidates("project") and store.task(handle.id) == before


def test_an_identical_payload_does_not_bypass_an_explicit_stale_source_version(tmp_path):
    source = event()
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        store.ingest(source)
        with pytest.raises(StoreConflictError, match="no longer current"):
            store.ingest(source, expected_version=0)


def test_exact_process_checks_are_immutable_and_reject_foreign_stale_or_behavior_bindings(tmp_path):
    source = event()
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        behavior = reviewed(store, (source,))
        process = reviewed(store, (source,), proposal(source).model_copy(update={"support_kind": "process"}))
        receipt = ProcessCheckReceipt(
            access_scope="project",
            method=process,
            event_reference=source.view.reference,
            event_version=1,
            passed=True,
            observations=("The fixture's exact structural property holds.",),
        )
        for invalid in (
            receipt.model_copy(update={"access_scope": "another-project"}),
            receipt.model_copy(update={"event_version": 2}),
            receipt.model_copy(update={"method": behavior}),
        ):
            with pytest.raises(StoreConflictError, match="exact reviewed"):
                store.record_process_check(invalid)
        store.record_process_check(receipt)
        changes = store.connection.total_changes
        store.record_process_check(receipt)
        assert store.connection.total_changes == changes
        with pytest.raises(StoreConflictError, match="immutable"):
            store.record_process_check(receipt.model_copy(update={"passed": False}))
