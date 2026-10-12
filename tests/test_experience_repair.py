"""Require bounded model repair and independent reproduction before replacing an adopted Curator method."""

import pytest

from experimental.harness.experience.build import ExperiencePipeline
from experimental.harness.experience.contracts import EvidenceLink, ExperienceReview
from experimental.harness.experience.governance import Issue
from experimental.harness.experience.repair import verification_context
from experimental.harness.experience.verification import Case, Result, compare_methods
from tests.experience_helpers import event, proposal, reviewed
from tests.test_experience_curator import consumer, prepare


class Builder:
    def identity(self):
        return {"role": "repair-builder"}

    async def build(self, request, **kwargs):
        assert request.repair is not None
        return (
            request.repair.current.model_copy(
                update={
                    "guidance": "Inspect every consumer and verify each result is used.",
                    "evidence": tuple(
                        EvidenceLink(reference=row.reference, relation="supports") for row in request.events
                    ),
                }
            ),
        )


class Critic:
    def identity(self):
        return {"rule": "test-critic"}

    async def review(self, proposals, request, **kwargs):
        return tuple(ExperienceReview(proposal_index=i, decision="accept") for i in range(len(proposals)))


def adopted(owner):
    for name in ("one", "two"):
        source = event(name)
        reviewed(owner.store, (source,), proposal(source, "Inspect the first consumer and verify its result."))
    owner.refresh()
    return owner.journal.read().active("curator", "project")[0]


async def execute(instructions, case):
    actual = case.inputs["consumers"] if "Inspect every consumer" in instructions else 1
    return Result(
        satisfied=actual == case.inputs["consumers"], preserved=True, record=f"{actual}-{case.id}-{len(instructions)}"
    )


@pytest.mark.asyncio
async def test_reviewed_repair_waits_for_targeted_evidence_and_cannot_revive_old_method(tmp_path):
    owner = consumer(tmp_path)
    owner.pipeline = ExperiencePipeline(owner.store, Builder(), Critic())
    with owner.store:
        old = adopted(owner)
        prepare(owner)
        diagnosis = owner.diagnose(
            Issue(
                target=old,
                cause="content",
                evidence=("failure-1",),
                reason="A second consumer was missed.",
                fields=("content.guidance",),
            ),
            evidence={"failure-1"},
        )
        candidate = await owner.repair(diagnosis, (event("one"), event("two")))
        assert candidate["status"] == "candidate"
        owner.refresh()
        assert owner.journal.read().active("curator", "project") == (old,)
        unrelated = (Case("missing", "task-a", {"consumers": 2}), Case("valid", "task-b", {"consumers": 1}))
        refused = await owner.verify_repair(candidate["candidate"], cases=unrelated, evaluate=execute)
        assert not refused["accepted"] and not refused["reproduced"]
        targeted = (Case("missing", "task-a", {"consumers": 2}, references=("failure-1",)), unrelated[1])
        receipt = await owner.verify_repair(candidate["candidate"], cases=targeted, evaluate=execute)
        assert receipt["accepted"]
        assert owner.journal.read().data["entries"][old]["reason"] == "superseded"
        owner.refresh()
        active = owner.journal.read().active("curator", "project")
        assert active == (candidate["candidate"],)
        assert "Inspect every consumer" in prepare(owner)["stages"]["design"]["usage"]["text"]
        reviewed(
            owner.store,
            (event("three"),),
            proposal(event("three"), "Inspect the first consumer and verify its result."),
        )
        owner.refresh()
        assert owner.journal.read().active("curator", "project") == active


@pytest.mark.asyncio
async def test_usage_audit_drives_a_bounded_repair_and_the_configured_verifier(tmp_path):
    class AuditCritic(Critic):
        async def audit(self, *, methods, evidence):
            return (
                Issue(
                    target=methods[0]["target"],
                    cause="content",
                    evidence=(evidence[0]["reference"],),
                    reason="The loaded method missed a second consumer.",
                    fields=("content.guidance",),
                ),
            )

    source = event("failure")

    class Verifier:
        def identity(self):
            return {"policy": "fixed-consumer-comparison"}

        async def verify(self, owner, candidate):
            before, after, context = verification_context(owner, owner.journal.read(), candidate)
            return await compare_methods(
                before=before,
                after=after,
                context=context,
                evaluate=execute,
                cases=(
                    Case("missed", "unseen-a", {"consumers": 2}, references=(source.view.reference,)),
                    Case("preserved", "unseen-b", {"consumers": 1}),
                ),
            )

    owner = consumer(tmp_path)
    owner.pipeline = ExperiencePipeline(owner.store, Builder(), AuditCritic())
    owner.verification = Verifier()
    with owner.store:
        old = adopted(owner)
        snapshot = prepare(owner)
        owner.observe(snapshot, record="curation-with-missed-consumer")
        issues = await owner.audit(snapshot, (source,))
        assert len(issues) == 1
        result = await owner.repair(issues[0], (source,))
        assert result["status"] == "adopted" and result["verification"]["accepted"]
        assert owner.journal.read().active("curator", "project") == (result["candidate"],)
        assert owner.journal.read().data["entries"][old]["state"] == "inactive"


@pytest.mark.asyncio
async def test_loading_issue_is_retained_without_rewriting_the_method(tmp_path):
    owner = consumer(tmp_path)
    owner.pipeline = ExperiencePipeline(owner.store, Builder(), Critic())
    with owner.store:
        old = adopted(owner)
        diagnosis = owner.diagnose(
            Issue(
                target=old,
                cause="loading",
                evidence=("request-1",),
                reason="The method was omitted from the model request.",
            ),
            evidence={"request-1"},
        )
        result = await owner.repair(diagnosis, (event("one"),))
        assert result["status"] == "investigate"
        assert owner.journal.read().active("curator", "project") == (old,)
