"""Exercise completed-record learning and delayed outcomes without reusing held-out validation data."""

from copy import deepcopy

import pytest

from experimental.harness.experience.admission import AdmissionPolicy
from experimental.harness.experience.build import ExperiencePipeline
from experimental.harness.experience.contracts import (
    EvidenceLink,
    ExperienceCondition,
    ExperienceProposal,
    ExperienceReview,
    OutcomeReceipt,
    digest,
)
from experimental.harness.experience.curator import CuratorExperience
from experimental.harness.experience.store import ExperienceStore, StoreConflictError
from experimental.harness.experience.verification import Case, Result, compare_methods
from tests.test_experience_records import access, origin, record  # noqa: F401 -- approved source fixtures


class Builder:
    def __init__(self):
        self.calls = 0

    def identity(self):
        return {"role": "deterministic-builder"}

    async def build(self, request, **kwargs):
        self.calls += 1
        return (
            ExperienceProposal(
                condition=ExperienceCondition(situation="A consumer needs the produced result.", phase="design"),
                guidance="Inspect the result and its actual consumer, then verify application.",
                evidence=tuple(EvidenceLink(reference=row.reference, relation="supports") for row in request.events),
            ),
        )


class Critic:
    def identity(self):
        return {"role": "deterministic-critic"}

    async def review(self, proposals, request, **kwargs):
        return tuple(ExperienceReview(proposal_index=i, decision="accept") for i in range(len(proposals)))


def learning(tmp_path, grant):
    store = ExperienceStore(tmp_path / "experience.sqlite")
    builder, critic = Builder(), Critic()
    return CuratorExperience(
        store,
        AdmissionPolicy(critic_digest=digest(critic.identity())),
        grant,
        pipeline=ExperiencePipeline(store, builder, critic),
    )


def outcome(source, artifact):
    return OutcomeReceipt(
        access_scope=source.access_scope,
        revision_id=artifact,
        scope=source.scope,
        held=True,
        basis="observation",
        comparability="comparable",
        observations=("The independent observer saw the consumer use the produced result.",),
    )


@pytest.mark.asyncio
async def test_later_observations_qualify_experience_only_for_later_tasks(tmp_path, access, origin, record):
    owner = learning(tmp_path, access)
    with owner.store:
        frozen = owner.prepare(task="current", situation="A consumer needs a result.", inputs="current-inputs")
        first = await owner.learn(record, origin=origin)
        assert first["status"] == "complete" and first["accepted_candidates"]
        assert not first["admission"]["active"]
        await owner.outcome(first["event"], outcome(origin, record["active_artifact_id"]), held_out=False)
        second_record = deepcopy(record)
        second_record["generated"]["candidate"]["plan"]["understanding"] = (
            "A different persistent consumer missed its result."
        )
        second_origin = origin.model_copy(update={"run_id": "run-2", "lineage_id": "case-2", "record_id": "record-2"})
        second = await owner.learn(second_record, origin=second_origin)
        assert not second["admission"]["active"]
        supported = await owner.outcome(
            second["event"], outcome(second_origin, second_record["active_artifact_id"]), held_out=False
        )
        assert supported["admission"]["active"]
        assert (
            owner.prepare(
                task="current", situation="A consumer needs a result.", inputs="current-inputs", previous=frozen
            )
            == frozen
        )
        assert frozen["stages"] == {}
        next_task = owner.prepare(task="next", situation="A consumer needs a result.", inputs="next-inputs")
        assert next_task["stages"]["design"]
        calls = owner.pipeline.builder.calls
        await owner.learn(record, origin=origin)
        assert owner.pipeline.builder.calls == calls
        assert owner.store.event(access.access_scope, first["event"])[0].view.held is True


@pytest.mark.asyncio
async def test_held_out_results_do_not_change_the_training_episode(tmp_path, access, origin, record):
    owner = learning(tmp_path, access)
    with owner.store:
        learned = await owner.learn(record, origin=origin)
        before = owner.store.event(access.access_scope, learned["event"])
        calls = owner.pipeline.builder.calls
        result = await owner.outcome(learned["event"], outcome(origin, record["active_artifact_id"]), held_out=True)
        assert result["status"] == "validation_only"
        assert owner.store.event(access.access_scope, learned["event"]) == before
        assert owner.pipeline.builder.calls == calls


@pytest.mark.asyncio
async def test_method_comparisons_cannot_feed_the_learning_corpus(tmp_path, access, origin, record):
    owner = learning(tmp_path, access)
    with owner.store:
        learned = await owner.learn(record, origin=origin)
        before = owner.store.event(access.access_scope, learned["event"])
        calls = owner.pipeline.builder.calls

        async def evaluate(instructions, case):
            captured = await owner.learn(record, origin=origin)
            observed = await owner.outcome(
                learned["event"], outcome(origin, record["active_artifact_id"]), held_out=False
            )
            assert captured["status"] == observed["status"] == "validation_only"
            return Result(satisfied=True, preserved=True, record=f"{instructions}-{case.id}")

        result = await compare_methods(
            before="original",
            after="candidate",
            context="frozen",
            evaluate=evaluate,
            cases=(Case("one", "one", {"input": 1}), Case("two", "two", {"input": 2})),
        )
        assert not result.error
        assert owner.store.event(access.access_scope, learned["event"]) == before
        assert owner.pipeline.builder.calls == calls
        updated = await owner.outcome(learned["event"], outcome(origin, record["active_artifact_id"]), held_out=False)
        assert updated["status"] != "validation_only"


@pytest.mark.asyncio
async def test_wrong_revision_or_revoked_source_cannot_supply_behavior_credit(tmp_path, access, origin, record):
    owner = learning(tmp_path, access)
    with owner.store:
        learned = await owner.learn(record, origin=origin)
        with pytest.raises(ValueError, match="actually applied"):
            await owner.outcome(learned["event"], outcome(origin, "another-revision"), held_out=False)
        owner.store.revoke_event(access.access_scope, learned["event"], expected_version=1)
        with pytest.raises(StoreConflictError, match="revoked"):
            await owner.outcome(learned["event"], outcome(origin, record["active_artifact_id"]), held_out=False)
