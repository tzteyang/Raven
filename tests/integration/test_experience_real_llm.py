"""Validate experience construction and review with real models and approved archived cases."""

import json
import os
from pathlib import Path

import pytest

from experimental.experience.admission import AdmissionPolicy
from experimental.experience.build import ExperiencePipeline
from experimental.experience.builder import ModelExperienceBuilder
from experimental.experience.contracts import BuildRequest, ExperienceCondition, RecordOrigin, digest
from experimental.experience.critic import ModelExperienceCritic
from experimental.experience.model import ModelLimits
from experimental.experience.records import RecordAccess, RecordRejectedError, read_record
from experimental.experience.retrieve import ExperienceRetriever, GuidanceQuery
from experimental.experience.state import BuildState
from experimental.experience.store import ExperienceStore
from raven.core.config_stack import load_runtime_config
from raven.providers.factory import make_lazy_provider
from tests.experience_helpers import event, process_checked, proposal

pytestmark = [pytest.mark.integration, pytest.mark.real_llm, pytest.mark.slow]


def configured():
    path = os.environ.get("EXPERIENCE_TEST_CONFIG")
    if not path:
        pytest.skip("Set EXPERIENCE_TEST_CONFIG to run the authorized real-model checks.")
    config = load_runtime_config(path)
    return make_lazy_provider(config), config.agents.defaults.model, config.agents.defaults.reasoning_effort


def clients(provider, model, effort):
    limits = ModelLimits()
    return (
        ModelExperienceBuilder(provider, model=model, effort=effort, limits=limits),
        ModelExperienceCritic(provider, model=model, effort=effort, limits=limits),
    )


@pytest.mark.asyncio
async def test_real_critic_diagnoses_a_method_without_granting_metadata_edits(tmp_path):
    provider, model, effort = configured()
    _, critic = clients(provider, model, effort)
    issues = await critic.audit(
        methods=[
            {
                "target": "method-under-test",
                "method": {
                    "condition": {"situation": "Two mandatory consumers need the same result.", "phase": "design"},
                    "guidance": "Route the result only to the first consumer and skip every remaining consumer.",
                    "support_kind": "behavior",
                },
            }
        ],
        evidence=[
            {
                "reference": "observed-failure",
                "observation": {
                    "loaded": True,
                    "actual": "The first consumer ran. The second mandatory consumer received no input.",
                    "required": "Both mandatory consumers must receive the result.",
                },
            }
        ],
    )
    (tmp_path / "audit.json").write_text(
        json.dumps({"issues": [issue.model_dump(mode="json") for issue in issues], "trace": critic.trace}, indent=2)
    )
    assert issues and all(issue.target == "method-under-test" for issue in issues)
    assert any(issue.cause == "content" and "content.guidance" in issue.fields for issue in issues)
    assert all(set(issue.evidence) == {"observed-failure"} for issue in issues)
    assert all(
        set(issue.fields) <= {"content.guidance", "content.condition", "content.support_kind"} for issue in issues
    )


def save_report(tmp_path, builder, critic, result, store, scope):
    assessments = store.refresh_admission(scope, AdmissionPolicy(critic_digest=digest(critic.identity())))
    report = {
        "result": result.model_dump(mode="json"),
        "builder_trace": builder.trace,
        "critic_trace": critic.trace,
        "candidates": store.candidates(scope),
        "admission": [assessment.model_dump() for assessment in assessments],
    }
    (tmp_path / "validation.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))


@pytest.mark.asyncio
async def test_real_builder_and_critic_construct_a_grounded_reviewed_method(tmp_path):
    provider, model, effort = configured()
    builder, critic = clients(provider, model, effort)
    source = event("model-validation")
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        result = await ExperiencePipeline(store, builder, critic).run((source,))
        save_report(tmp_path, builder, critic, result, store, "project")
        assert result.state.status == "complete", result.state.error
        assert result.state.accepted
        assert result.state.builder_calls <= 2 and result.state.critic_calls <= 2
        assert all(candidate["status"] == "candidate" for candidate in store.candidates("project"))
        assert not store.recommendations("project", AdmissionPolicy(critic_digest=digest(critic.identity())))


@pytest.mark.asyncio
async def test_real_critic_distinguishes_specific_vague_unsupported_and_actionable_candidates(tmp_path):
    provider, model, effort = configured()
    _, critic = clients(provider, model, effort)
    source = event("critic-validation")
    methods = (
        proposal(source, "For OrchidLaneAgency, edit /private/cases/booking.py to enforce its specific quote amount."),
        proposal(source, "Improve quality and validate carefully."),
        proposal(
            source,
            "The host profile is consumed in every call by every provider; this guarantees success for every future task.",
        ),
        proposal(source),
    )
    reviews = await critic.review(methods, BuildRequest(events=(source.view,)))
    (tmp_path / "critic-validation.json").write_text(
        json.dumps({"reviews": [review.model_dump(mode="json") for review in reviews], "trace": critic.trace}, indent=2)
    )
    by_index = {review.proposal_index: review for review in reviews}
    assert all(by_index[index].decision != "accept" for index in (0, 1, 2))
    assert by_index[3].decision == "accept"
    assert {issue.kind for issue in by_index[0].issues} & {"case_detail", "too_specific", "unsupported"}
    assert "too_vague" in {issue.kind for issue in by_index[1].issues}
    assert "unsupported" in {issue.kind for issue in by_index[2].issues}


@pytest.mark.asyncio
async def test_archived_real_cases_build_review_and_store_without_case_details(tmp_path):
    location = os.environ.get("EXPERIENCE_TEST_RECORDS")
    if not location:
        pytest.skip("Set EXPERIENCE_TEST_RECORDS to the approved archived case root.")
    root = Path(location).resolve()
    sources = []
    access = RecordAccess(
        access_scope="archived-case-validation",
        fields=frozenset({"plan.understanding", "plan.design", "change.target", "change.reason"}),
    )
    for name in ("travel-itinerary-expert", "recruitment-expert", "xiaohongshu-operations-expert"):
        for path in sorted((root / name).glob("**/curation/*.json")):
            origin = RecordOrigin(
                access_scope=access.access_scope, run_id=name, lineage_id=name, record_id=str(path.relative_to(root))
            )
            try:
                source = read_record(path, root=root, origin=origin, access=access)
            except RecordRejectedError:
                continue
            sources.append(source)
            break
    assert len(sources) == 3
    provider, model, effort = configured()
    builder, critic = clients(provider, model, effort)
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        result = await ExperiencePipeline(store, builder, critic).run(tuple(sources))
        save_report(tmp_path, builder, critic, result, store, access.access_scope)
        assert result.state.status == "complete", result.state.error
        assert result.state.accepted
        for candidate in store.candidates(access.access_scope):
            text = json.dumps(candidate["proposal"], ensure_ascii=False).casefold()
            assert not any(
                marker in text
                for marker in (
                    "orchidlaneagency",
                    "xiaohongshu",
                    "recruitment-expert",
                    "travel-itinerary-expert",
                    "/tmp/",
                    "/private/",
                    "candidate a",
                    "candidate b",
                    ".pptx",
                    "the reported cases",
                )
            )
        assert all(source.view.held is None for source in sources)
        for assessment in store.refresh_admission(
            access.access_scope, AdmissionPolicy(critic_digest=digest(critic.identity()))
        ):
            assert assessment.status != "supported" and assessment.independent_runs == 0


@pytest.mark.asyncio
async def test_real_critic_limits_process_support_before_admission_and_retrieval(tmp_path):
    provider, model, effort = configured()
    _, critic = clients(provider, model, effort)
    sources = tuple(
        source.model_copy(
            update={
                "view": source.view.model_copy(
                    update={"activation": "unknown", "held": None, "basis": "unknown", "observations": ()}
                )
            }
        )
        for source in (event("process-one"), event("process-two"))
    )
    ungrounded = proposal(
        sources[0],
        "Passing structural checks establishes that the consumer applied the result and task behavior improved.",
    ).model_copy(update={"support_kind": "process"})
    structural = proposal(
        sources[1],
        "Run the current generation contract's structural checks before installation; passing supports structural validity only, and every reported mismatch requires investigation.",
    ).model_copy(
        update={
            "support_kind": "process",
            "condition": ExperienceCondition(
                situation="A generated artifact is ready for structural validation.", phase="implement"
            ),
            "evidence": (ungrounded.evidence[0], proposal(sources[1]).evidence[0]),
        }
    )
    methods = (ungrounded, structural)
    reviews = await critic.review(methods, BuildRequest(events=tuple(source.view for source in sources)))
    by_index = {review.proposal_index: review for review in reviews}
    assert by_index[0].decision != "accept"
    assert any(issue.kind == "unsupported" for issue in by_index[0].issues)
    assert by_index[1].decision == "accept"
    with ExperienceStore(tmp_path / "experience.sqlite") as store:
        identities = {"builder": {"implementation": "provided-test-proposals"}, "critic": critic.identity()}
        handle, _ = store.open_task(
            "process-review", digest([method.model_dump() for method in methods]), identities, sources, ttl=60
        )
        state = BuildState(status="complete", proposals=methods, reviews=reviews)
        _, completed = store.save(handle, state, ttl=60, finish=True, accepted=((structural, by_index[1]),))
        policy = AdmissionPolicy(critic_digest=digest(critic.identity()))
        assert store.refresh_admission("project", policy)[0].status == "candidate"
        process_checked(store, completed.accepted[0], sources)
        assessment = store.refresh_admission("project", policy)[0]
        assert assessment.status == "supported" and assessment.independent_runs == 2
        query = GuidanceQuery(
            access_scope="project",
            situation="Validate a generated artifact against its structural contract.",
            phase="implement",
            scope_kind="root",
        )
        bundle = ExperienceRetriever(store, policy).retrieve(query)
        assert len(bundle.items) == 1 and bundle.items[0].support_kind == "process"
        report = {
            "reviews": [review.model_dump() for review in reviews],
            "critic_trace": critic.trace,
            "admission": assessment.model_dump(),
            "guidance": bundle.model_dump(),
        }
        (tmp_path / "process-admission.json").write_text(json.dumps(report, indent=2))
