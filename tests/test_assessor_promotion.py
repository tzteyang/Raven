"""Only independent, unchanged verification of the actual current revision supports harness promotion."""

import pytest

from experimental.harness.assessor.dataset import Case, Dataset
from experimental.harness.assessor.validation import promotion
from experimental.harness.loop.session import Session
from experimental.harness.participation.protocols import Item, Signal
from tests.test_iteration_run import CONTINUE, FakeWorker, Verifier, passing
from tests.test_iteration_run import analyses as analyses  # noqa: F401 -- scripted Analyst fixture
from tests.test_iteration_session import (
    curations as curations,  # noqa: F401 -- records real session curation boundaries
)
from tests.test_iteration_session import student


async def ready(tmp_path, analyses):
    analyses.scripted.append(CONTINUE)
    session = Session.open(FakeWorker(tmp_path), object())
    await session.onboard()
    await session.trial(student("Training input"))
    await session.assess(Verifier(passing()))
    return session


def independent():
    return Dataset([Case("held", "Held-out input", "Reply to Held-out input")])


@pytest.mark.asyncio
async def test_a_self_generated_pass_does_not_promote_a_harness(tmp_path, curations, analyses):
    session = await ready(tmp_path, analyses)
    await session.analyse()
    assert session.record["promotion"]["status"] == "candidate"
    assert "stable_revision" not in session.record


@pytest.mark.asyncio
async def test_frozen_independent_replay_promotes_only_the_verified_revision(tmp_path, curations, analyses):
    session = await ready(tmp_path, analyses)
    dataset = independent()
    await session.holdout([dataset], [dataset])
    await session.analyse()
    assert session.record["promotion"]["status"] == "accepted"
    assert session.record["stable_revision"]["revision"] == session.worker.artifact_id
    resumed = Session.resume(session.worker, object(), session.path)
    assert resumed.record["promotion"]["status"] == "candidate"
    assert resumed.record["stable_revision"] == session.record["stable_revision"]
    session.worker.artifact_id = "an-unverified-revision"
    session.save()
    assert session.record["promotion"]["status"] == "candidate"
    assert session.record["stable_revision"]["revision"] != session.worker.artifact_id


@pytest.mark.asyncio
async def test_mutating_verification_policy_cannot_make_a_failure_pass(tmp_path, curations, analyses):
    session = await ready(tmp_path, analyses)
    dataset = independent()

    def weaken(actual, expected):
        dataset.threshold = 0
        return False

    dataset.score = weaken
    await session.holdout([dataset], [dataset])
    await session.analyse()
    assert session.record["promotion"]["status"] == "candidate"
    assert "changed its frozen policy" in session.record["promotion"]["witnesses"][0]["error"]


@pytest.mark.asyncio
async def test_replay_evidence_cannot_be_replaced_after_verification(tmp_path, curations, analyses):
    session = await ready(tmp_path, analyses)
    dataset = independent()
    await session.holdout([dataset], [dataset])
    session.held_out["case:held"][0].execution.records.clear()
    await session.analyse()
    assert session.record["promotion"]["status"] == "candidate"


@pytest.mark.asyncio
async def test_training_inputs_are_not_relabelled_as_held_out(tmp_path, curations, analyses):
    session = await ready(tmp_path, analyses)
    dataset = Dataset([Case("held", "Training input", "Reply to Training input")])
    await session.holdout([dataset], [dataset])
    await session.analyse()
    assert session.record["promotion"]["status"] == "candidate"
    assert "overlap" in session.record["promotion"]["witnesses"][0]["error"]


@pytest.mark.asyncio
async def test_resume_requires_fresh_verification(tmp_path, curations, analyses):
    session = await ready(tmp_path, analyses)
    dataset = independent()
    await session.holdout([dataset], [dataset])
    resumed = Session.resume(session.worker, object(), session.path)
    await resumed.analyse()
    assert resumed.record["promotion"]["status"] == "candidate"
    assert "Resume" in resumed.record["promotion"]["witnesses"][0]["error"]


def test_an_unknown_hard_condition_is_not_canceled_by_another_sources_pass():
    result = promotion(
        revision="r",
        context="c",
        witnesses=[{"revision": "r", "context": "c", "satisfied": True}],
        signals=[
            Signal("one", items=(Item("costs", "unknown", strength="must_hold"),)),
            Signal("two", items=(Item("costs", "pass", strength="must_hold"),), satisfied=True),
        ],
        feedback=CONTINUE,
        external_requirements=(),
    )
    assert result["status"] == "candidate"


def test_external_rejection_blocks_adoption_but_an_advisory_self_signal_does_not():
    arguments = dict(
        revision="r",
        context="c",
        witnesses=[{"revision": "r", "context": "c", "satisfied": True}],
        feedback=CONTINUE,
        external_requirements=(),
    )
    advisory = Signal("self", items=(Item("reflection", "unknown"),))
    assert promotion(**arguments, signals=[advisory])["status"] == "accepted"
    rejection = Signal("human", text="This does not meet my needs.", satisfied=False, authority="external")
    assert promotion(**arguments, signals=[advisory, rejection])["status"] == "candidate"


@pytest.mark.asyncio
async def test_a_permissive_dataset_threshold_cannot_turn_a_missing_case_into_a_pass():
    dataset = Dataset([Case("missing", "Task", "Answer")], threshold=0)
    signal = await dataset.evaluate({})
    assert signal.satisfied is None and signal.items[0].result == "unknown"
