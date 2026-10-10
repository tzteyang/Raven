"""Verify evidence eligibility, actual stage guidance and recovery against changed sources."""

import asyncio
import json

import pytest

from experimental.harness.experience.admission import AdmissionPolicy
from experimental.harness.experience.contracts import digest
from experimental.harness.experience.curator import CuratorExperience, stage_guidance
from experimental.harness.experience.records import RecordAccess
from experimental.harness.experience.store import ExperienceStore, StoreError
from tests.experience_helpers import event, proposal, reviewed
from tests.test_harness_curator_generation import Provider, diagnosis, response, selection
from tests.test_harness_curator_workflow import worker  # noqa: F401 -- the actual workflow's local worker fixture


def consumer(tmp_path):
    store = ExperienceStore(tmp_path / "experience.sqlite")
    policy = AdmissionPolicy(critic_digest=digest({"rule": "test-critic"}))
    access = RecordAccess(access_scope="project", fields=frozenset({"plan.understanding", "change.reason"}))
    return CuratorExperience(store, policy, access)


def prepare(owner, **kwargs):
    return owner.prepare(
        task="task-2",
        situation="The actual consumer did not consume a mechanism result.",
        inputs="frozen-current-context",
        **kwargs,
    )


def test_domain_support_does_not_bypass_shared_admission_or_leak_original_evidence(tmp_path):
    owner = consumer(tmp_path)
    with owner.store:
        reviewed(owner.store, (event("one"),))
        reviewed(owner.store, (event("two"),))
        owner.store.refresh_admission("project", owner.policy)
        assert prepare(owner)["stages"] == {}
        assert owner.refresh()["active"]
        snapshot = prepare(owner)
        packet = stage_guidance(snapshot, "design")
        assert packet and "A principle states" in packet["text"]
        assert "A procedure organizes" in packet["text"]
        assert "Evidence supports: behavior" in packet["text"]
        assert stage_guidance(snapshot, "implement") is None
        assert "episode" not in packet and "sources" not in packet
        owner.validate(snapshot, inputs="frozen-current-context")
        owner.observe(snapshot, record="actual-curation-record")
        ledger = owner.journal.read()
        usage = ledger.data["uses"][packet["usage"]]
        assert usage["observations"][0]["result"] == "unknown"


def test_resume_uses_the_original_packet_and_refuses_source_revocation(tmp_path):
    owner = consumer(tmp_path)
    with owner.store:
        reviewed(owner.store, (event("one"),))
        reviewed(owner.store, (event("two"),))
        owner.refresh()
        snapshot = prepare(owner)
        assert prepare(owner, previous=snapshot) == snapshot
        owner.store.revoke_event("project", event("one").view.reference, expected_version=1)
        with pytest.raises(StoreError, match="no longer eligible"):
            prepare(owner, previous=snapshot)
        assert not owner.refresh()["active"]


def test_frozen_guidance_cannot_change_consumer_inputs_or_text(tmp_path):
    owner = consumer(tmp_path)
    with owner.store:
        reviewed(owner.store, (event("one"),))
        reviewed(owner.store, (event("two"),))
        owner.refresh()
        snapshot = prepare(owner)
        with pytest.raises(ValueError, match="inputs or owner"):
            owner.validate(snapshot, inputs="different-task-inputs")
        snapshot["stages"]["design"]["usage"]["text"] = "Unreviewed instructions."
        with pytest.raises(ValueError, match="inputs or owner"):
            owner.validate(snapshot, inputs="frozen-current-context")


def test_journal_failure_does_not_publish_domain_eligible_methods(tmp_path, monkeypatch):
    from experimental.harness.experience import journal

    owner = consumer(tmp_path)
    with owner.store:
        reviewed(owner.store, (event("one"),))
        reviewed(owner.store, (event("two"),))

        def unavailable(*args):
            raise OSError("Unavailable storage.")

        with monkeypatch.context() as patch:
            patch.setattr(journal.os, "replace", unavailable)
            with pytest.raises(OSError, match="Unavailable"):
                owner.refresh()
        assert not owner.journal.read().active("curator", "project")
        assert prepare(owner)["stages"] == {}


def test_runtime_experience_cannot_live_in_the_worker_writable_area(tmp_path):
    owner = consumer(tmp_path)
    with owner.store, pytest.raises(ValueError, match="Worker writable"):
        prepare(owner, worker_root=tmp_path)


def adopted_diagnosis(owner):
    for name in ("one", "two"):
        source = event(name)
        method = proposal(source)
        condition = method.condition.model_copy(
            update={"phase": "diagnose", "situation": "Improve a mechanism's consumer."}
        )
        reviewed(owner.store, (source,), method.model_copy(update={"condition": condition}))
    owner.refresh()


@pytest.mark.asyncio
async def test_workflow_delivers_only_the_stage_method_and_records_actual_loading(worker, tmp_path):
    from experimental.harness.curator.workflow import improve

    owner = consumer(tmp_path)
    with owner.store:
        adopted_diagnosis(owner)
        provider = Provider(response("submit_diagnosis", diagnosis()), response("submit_selection", selection()))
        await improve(worker, provider, experience=owner)
        assert any("Experience usage" in str(row["content"]) for row in provider.requests[0]["messages"])
        assert not any("Experience usage" in str(row["content"]) for row in provider.requests[1]["messages"])
        worker.install.assert_awaited_once()
        record = json.loads(next((worker.root / "curation").glob("*.json")).read_text())
        usage = record["experience"]["stages"]["diagnose"]["usage"]["id"]
        assert record["experience_loaded"] == [usage]
        observed = owner.journal.read().data["uses"][usage]["observations"]
        assert observed and "was loaded" in observed[-1]["note"]


@pytest.mark.asyncio
async def test_cancelled_learning_preserves_the_successful_install_record(worker, tmp_path, monkeypatch):
    from experimental.harness.curator.workflow import improve

    owner = consumer(tmp_path)

    async def cancel(*args, **kwargs):
        raise asyncio.CancelledError

    with owner.store:
        monkeypatch.setattr(owner, "learn", cancel)
        provider = Provider(response("submit_diagnosis", diagnosis()), response("submit_selection", selection()))
        with pytest.raises(asyncio.CancelledError):
            await improve(worker, provider, experience=owner)
        worker.install.assert_awaited_once()
        record = json.loads(next((worker.root / "curation").glob("*.json")).read_text())
        assert record["active_artifact_id"] and not record.get("error")
        assert record["experience_learning"]["status"] == "interrupted"


@pytest.mark.asyncio
async def test_workflow_refuses_revoked_guidance_before_resumed_model_calls(worker, tmp_path):
    from experimental.harness.curator.generation.run import GenerationPausedError, Limits
    from experimental.harness.curator.workflow import improve

    owner = consumer(tmp_path)
    with owner.store:
        adopted_diagnosis(owner)
        first = Provider(response("submit_diagnosis", diagnosis()), response("read_file", {"path": "facts.json"}))
        with pytest.raises(GenerationPausedError):
            await improve(worker, first, experience=owner, limits=Limits(max_calls=1))
        checkpoint = worker.root / "curation/pending.json"
        original = checkpoint.read_bytes()
        assert json.loads(original)["experience"]["stages"]["diagnose"]
        owner.store.revoke_event("project", event("one").view.reference, expected_version=1)
        resumed = Provider()
        with pytest.raises(StoreError, match="no longer eligible"):
            await improve(worker, resumed, experience=owner, limits=Limits(max_calls=2))
        assert checkpoint.read_bytes() == original
        assert not resumed.requests
        worker.install.assert_not_awaited()


@pytest.mark.asyncio
async def test_unavailable_optional_memory_stays_disabled_for_the_frozen_curation(worker, tmp_path, monkeypatch):
    from experimental.harness.curator.generation.run import GenerationPausedError, Limits
    from experimental.harness.curator.workflow import improve

    owner = consumer(tmp_path)
    with owner.store:
        adopted_diagnosis(owner)

        def unavailable(**kwargs):
            raise OSError("Memory is temporarily unavailable.")

        first = Provider(response("submit_diagnosis", diagnosis()), response("read_file", {"path": "facts.json"}))
        with monkeypatch.context() as patch:
            patch.setattr(owner, "prepare", unavailable)
            with pytest.raises(GenerationPausedError):
                await improve(worker, first, experience=owner, limits=Limits(max_calls=1))
        path = worker.root / "curation/pending.json"
        assert "experience_unavailable" in json.loads(path.read_text())
        resumed = Provider(response("submit_selection", selection()))
        await improve(worker, resumed, experience=owner, limits=Limits(max_calls=3))
        assert not any(
            "Experience usage" in str(row["content"]) for request in resumed.requests for row in request["messages"]
        )
        worker.install.assert_awaited_once()
