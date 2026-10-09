"""Check durable budgets, bounded review repair and isolated construction ownership."""

import asyncio

import pytest

from experimental.experience.admission import AdmissionPolicy
from experimental.experience.build import BuildLimits, ExperiencePipeline
from experimental.experience.builder import ModelExperienceBuilder
from experimental.experience.contracts import ExperienceReview, ReviewIssue, digest
from experimental.experience.critic import ModelExperienceCritic
from experimental.experience.retrieve import ExperienceRetriever, GuidanceQuery
from experimental.experience.store import BindingMismatchError, ExperienceStore, StoreError
from tests.experience_helpers import Provider, accept, event, proposal, response, reviewed


def pipeline(store, provider, **kwargs):
    return ExperiencePipeline(store, ModelExperienceBuilder(provider), ModelExperienceCritic(provider), **kwargs)


def build_reply(method):
    return response("submit_experience", {"proposals": [method.model_dump(mode="json")]})


def review_reply(review):
    return response("submit_reviews", {"reviews": [review.model_dump(mode="json")]})


@pytest.mark.asyncio
async def test_complete_flow_is_cached_and_accepted_candidates_remain_unpublished(tmp_path):
    source = event()
    provider = Provider(build_reply(proposal(source)), review_reply(accept()))
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        worker = pipeline(store, provider)
        first = await worker.run((source,))
        second = await worker.run((source,))
        assert first == second and len(provider.requests) == 2
        assert first.state.status == "complete" and len(first.state.accepted) == 1
        assert store.candidates("project")[0]["status"] == "candidate"
        assert not store.candidates("another-project")


@pytest.mark.asyncio
async def test_one_semantic_revision_gets_its_own_review(tmp_path):
    source = event()
    weak = proposal(source, "Validate carefully.")
    fixed = proposal(source)
    issue = ReviewIssue(kind="too_vague", field="guidance", reason="Supply an observable action.")
    revise = ExperienceReview(proposal_index=0, decision="revise", issues=(issue,))
    provider = Provider(build_reply(weak), review_reply(revise), build_reply(fixed), review_reply(accept()))
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        result = await pipeline(store, provider).run((source,))
        assert result.state.revised and result.state.builder_calls == result.state.critic_calls == 2
        assert store.candidates("project")[0]["proposal"]["guidance"] == fixed.guidance
        assert "revision" in provider.requests[2]["messages"][1]["content"]


@pytest.mark.asyncio
async def test_a_second_revision_request_does_not_loop_or_publish(tmp_path):
    source = event()
    issue = ReviewIssue(kind="too_vague", field="guidance", reason="Supply an observable action.")
    revise = ExperienceReview(proposal_index=0, decision="revise", issues=(issue,))
    method = proposal(source)
    provider = Provider(build_reply(method), review_reply(revise), build_reply(method), review_reply(revise))
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        result = await pipeline(store, provider).run((source,))
        assert result.state.status == "complete" and len(provider.requests) == 4
        assert not result.state.accepted and not store.candidates("project")


@pytest.mark.asyncio
async def test_format_repair_consumes_the_same_builder_budget(tmp_path):
    source = event()
    invalid = response("submit_experience", {"proposals": [{}]})
    provider = Provider(invalid, build_reply(proposal(source)), review_reply(accept()))
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        result = await pipeline(store, provider).run((source,))
        assert result.state.builder_calls == 2 and len(provider.requests) == 3
        assert "Submission correction" in provider.requests[1]["messages"][-1]["content"]


@pytest.mark.asyncio
async def test_budget_pause_continues_after_restart_without_repeating_builder(tmp_path):
    source = event()
    path = tmp_path / "experience.sqlite"
    first = Provider(build_reply(proposal(source)))
    with ExperienceStore(path) as store:
        stopped = await pipeline(store, first, limits=BuildLimits(max_calls=1)).run((source,))
        assert stopped.state.status == "exhausted" and stopped.state.builder_calls == 1
    second = Provider(review_reply(accept()))
    with ExperienceStore(path) as store:
        result = await pipeline(store, second).run((source,), task_id=stopped.task_id)
        assert result.state.status == "complete" and len(second.requests) == 1
        assert second.requests[0]["tools"][0]["function"]["name"] == "submit_reviews"


@pytest.mark.asyncio
async def test_provider_failure_releases_ownership_but_preserves_consumed_attempts(tmp_path):
    source = event()
    provider = Provider(RuntimeError("private failure"), build_reply(proposal(source)), review_reply(accept()))
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        worker = pipeline(store, provider)
        stopped = await worker.run((source,))
        assert stopped.state.status == "interrupted" and stopped.state.builder_calls == 1
        result = await worker.run((source,), task_id=stopped.task_id)
        assert result.state.status == "complete" and result.state.builder_calls == 2


@pytest.mark.asyncio
async def test_changed_resume_input_is_rejected_without_model_calls_or_state_loss(tmp_path):
    source = event()
    provider = Provider(build_reply(proposal(source)))
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        stopped = await pipeline(store, provider, limits=BuildLimits(max_calls=1)).run((source,))
        changed = source.model_copy(update={"view": source.view.model_copy(update={"situation": "Different context"})})
        before = store.task(stopped.task_id)
        with pytest.raises(BindingMismatchError):
            await pipeline(store, Provider()).run((changed,), task_id=stopped.task_id)
        assert store.task(stopped.task_id) == before


@pytest.mark.asyncio
async def test_cancellation_records_the_attempt_and_releases_the_task(tmp_path):
    source = event()
    started = asyncio.Event()
    provider = Provider()

    async def wait(**kwargs):
        started.set()
        await asyncio.Event().wait()

    provider.chat = wait
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        worker = pipeline(store, provider)
        task = asyncio.create_task(worker.run((source,), task_id="cancelled-task"))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert store.task("cancelled-task").status == "interrupted"
        resumed = Provider(build_reply(proposal(source)), review_reply(accept()))
        result = await pipeline(store, resumed).run((source,), task_id="cancelled-task")
        assert result.state.status == "complete" and result.state.builder_calls == 2


def related_for(store, worker, scope="project"):
    policy = AdmissionPolicy(critic_digest=digest(worker.critic.identity()))
    query = GuidanceQuery(
        access_scope=scope, situation="A mechanism result was not consumed.", phase="design", scope_kind="root"
    )
    return ExperienceRetriever(store, policy).related(query)


@pytest.mark.asyncio
async def test_reviewed_related_methods_reuse_wording_with_only_current_evidence_credit(tmp_path):
    first, second = event("one"), event("two")
    provider = Provider(build_reply(proposal(second)), review_reply(accept()))
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        worker = pipeline(store, provider)
        reviewed(store, (first,), critic=worker.critic.identity())
        related = related_for(store, worker)
        assert len(related) == 1 and related[0] == proposal(first)
        result = await worker.run((second,), related=related)
        assert result.state.status == "complete"
        packet = provider.requests[0]["messages"][1]["content"]
        assert first.view.reference in packet and second.view.reference in packet
        policy = AdmissionPolicy(critic_digest=digest(worker.critic.identity()))
        assert store.refresh_admission("project", policy)[0].independent_runs == 2


@pytest.mark.asyncio
async def test_foreign_related_proposals_are_rejected_before_model_calls(tmp_path):
    provider = Provider()
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        worker = pipeline(store, provider)
        foreign = event("foreign", scope="another-project")
        reviewed(store, (foreign,), critic=worker.critic.identity())
        with pytest.raises(StoreError, match="scoped reviews"):
            await worker.run((event(),), related=related_for(store, worker, "another-project"))
        assert not provider.requests


@pytest.mark.asyncio
async def test_old_related_references_cannot_be_submitted_as_new_evidence(tmp_path):
    first, second = event("one"), event("two")
    provider = Provider(build_reply(proposal(first)))
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        worker = pipeline(store, provider, limits=BuildLimits(max_calls=1))
        reviewed(store, (first,), critic=worker.critic.identity())
        result = await worker.run((second,), related=related_for(store, worker))
        assert result.state.status == "exhausted" and not result.state.accepted
        assert len(store.candidates("project")) == 1


@pytest.mark.asyncio
async def test_changed_related_packet_cannot_resume_the_saved_task(tmp_path):
    first, second = event("one"), event("two")
    provider = Provider(build_reply(proposal(second)))
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        worker = pipeline(store, provider, limits=BuildLimits(max_calls=1))
        reviewed(store, (first,), critic=worker.critic.identity())
        related = related_for(store, worker)
        stopped = await worker.run((second,), related=related)
        replacement = proposal(first, "Inspect the current consumer and verify the actual applied result.")
        reviewed(store, (first,), replacement, critic=worker.critic.identity())
        with pytest.raises(BindingMismatchError):
            await worker.run((second,), related=(replacement,), task_id=stopped.task_id)
        assert store.task(stopped.task_id) == stopped.state and len(provider.requests) == 1


@pytest.mark.asyncio
async def test_truncated_submission_gets_one_concise_format_repair_within_the_same_budget(tmp_path):
    source = event()
    truncated = build_reply(proposal(source))
    truncated.truncated = True
    provider = Provider(truncated, build_reply(proposal(source)), review_reply(accept()))
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        result = await pipeline(store, provider).run((source,))
        assert result.state.status == "complete" and result.state.builder_calls == 2 and result.state.critic_calls == 1
        assert len(provider.requests) == 3
        schema = provider.requests[1]["tools"][0]["function"]["parameters"]
        assert schema["properties"]["proposals"]["maxItems"] == 1
