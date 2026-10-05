"""Information collection preserves evidence, review decisions and focused updates before curation."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from experimental.research.collection import (
    ASK,
    GUIDANCE,
    READ,
    RESEARCH,
    REVIEW,
    SUBMIT,
    CollectionLimits,
    collect_information,
)
from experimental.research.curator import INFORMATION_FILE, handover_information
from experimental.research.information import (
    DIMENSIONS,
    Description,
    Evidence,
    Question,
    Request,
    ResearchGuide,
    Result,
    Review,
    Snapshot,
    render,
)
from raven.agent.tools.filesystem import ReadFileTool
from raven.agent.tools.registry import ToolRegistry
from raven.contracts.llm_provider import RunMeta, TruncationInfo
from tests.research_helpers import Provider, research_brief, response


def description(*, evidence=("evidence-1",), text="Use the stated professional scope.", unresolved=()):
    return {
        "title": "Project evidence expert",
        "sections": [
            {
                "dimension": dimension,
                "text": text,
                "coverage": "sufficient",
                "reason": "The cited input establishes it.",
                "evidence": evidence,
            }
            for dimension in DIMENSIONS
        ],
        "resources": [],
        "unresolved": list(unresolved),
    }


def accepted():
    return {"accepted": True, "reason": "The description is supported within its stated limits.", "issues": []}


def snapshot():
    return Snapshot(
        description=Description.model_validate(description()),
        evidence=(
            Evidence(
                id="evidence-1", channel="user", origin="initial request", content="Use the stated professional scope."
            ),
        ),
    )


def test_the_contract_distinguishes_missing_content_from_sufficient_content():
    data = description()
    data["sections"][2].update(text="", evidence=(), coverage="missing", reason="No domain knowledge is supplied.")
    assert Description.model_validate(data).sections[2].coverage == "missing"
    data["sections"][2]["coverage"] = "sufficient"
    with pytest.raises(ValidationError, match="content and evidence"):
        Description.model_validate(data)
    with pytest.raises(ValidationError, match="each dimension exactly once"):
        Description.model_validate({**description(), "sections": description()["sections"][:-1]})
    with pytest.raises(ValidationError, match="initial collection"):
        Request(objective="Research pricing only", focus=("knowledge",))


@pytest.mark.asyncio
async def test_native_reads_research_delegation_and_user_answers_share_real_evidence(tmp_path):
    (tmp_path / "method.md").write_text("Verify claims against the supplied project evidence.")
    registry = ToolRegistry()
    registry.register(ReadFileTool(workspace=tmp_path, allowed_dirs=(tmp_path,), follow_binding=False))
    delegated, asked = [], []

    async def research(task):
        delegated.append(task)
        return {"finding": "Record uncertainty explicitly.", "sources": ["https://example.org/method"]}

    async def ask(question):
        asked.append(question)
        return "Use our project evidence; do not invent missing results."

    provider = Provider(
        response("read_file", {"path": "method.md"}),
        response(
            RESEARCH,
            {
                "dimensions": ["knowledge", "methods"],
                "brief": research_brief(
                    "How should uncertainty be recorded?", deliverable="Source-backed methods and limitations."
                ),
            },
        ),
        response(
            ASK,
            {
                "dimension": "methods",
                "question": "What evidence may be used?",
                "reason": "Define the organisation's boundary.",
                "blocking": True,
            },
        ),
        response(SUBMIT, description(evidence=("evidence-3", "evidence-4", "evidence-5"))),
        response(REVIEW, accepted()),
    )
    result = await collect_information(
        provider,
        Request(objective="Construct a project evidence expert."),
        registry=registry,
        research=research,
        ask=ask,
        records=tmp_path / "records",
    )
    assert result.ready and result.status == "ready"
    assert [source.channel for source in result.snapshot.evidence] == ["request", "request", "tool", "research", "user"]
    assert delegated[0].brief.deliverable == "Source-backed methods and limitations."
    assert asked[0].question == "What evidence may be used?"
    assert "https://example.org/method" in render(result.snapshot)
    review_input = json.loads(provider.requests[-1]["messages"][1]["content"])
    assert len(review_input["evidence"]) == 3
    assert "Verify claims" in review_input["evidence"][0]["content"]
    record = json.loads((tmp_path / "records/status.json").read_text())
    assert record["version"] == result.snapshot.identity and record["status"] == "ready"


@pytest.mark.asyncio
async def test_semantic_review_receives_evidence_and_can_return_a_contradiction_for_repair(tmp_path):
    (tmp_path / "hours.md").write_text("Afternoon tea is served from two to five.")
    registry = ToolRegistry()
    registry.register(ReadFileTool(workspace=tmp_path, allowed_dirs=(tmp_path,), follow_binding=False))
    provider = Provider(
        response("read_file", {"path": "hours.md"}),
        response(SUBMIT, description(evidence=("evidence-3",), text="Afternoon tea is served at midnight.")),
        response(
            REVIEW,
            {
                "accepted": False,
                "reason": "The claim contradicts its evidence.",
                "issues": ["The knowledge section says midnight; the source says two to five."],
            },
        ),
        response(SUBMIT, description(evidence=("evidence-3",), text="Afternoon tea is served from two to five.")),
        response(REVIEW, accepted()),
    )
    result = await collect_information(
        provider, Request(objective="Describe service hours."), registry=registry, records=tmp_path / "records"
    )
    assert result.ready
    assert result.snapshot.description.sections[2].text == "Afternoon tea is served from two to five."
    first_review = json.loads(provider.requests[2]["messages"][1]["content"])
    assert "two to five" in first_review["evidence"][0]["content"]
    correction = next(
        row for row in provider.requests[3]["messages"] if row["role"] == "user" and '"review"' in row["content"]
    )
    assert correction["role"] == "user" and "contradicts" in correction["content"]
    assert not json.loads((tmp_path / "records/review-1.json").read_text())["accepted"]
    assert json.loads((tmp_path / "records/review-2.json").read_text())["accepted"]


@pytest.mark.asyncio
async def test_unanswered_user_questions_cannot_disappear_or_reach_curator(tmp_path):
    question = {
        "dimension": "methods",
        "question": "Who approves exceptions?",
        "reason": "Approval authority is missing.",
        "blocking": True,
    }
    provider = Provider(
        response(ASK, question),
        response(SUBMIT, description()),
        lambda kwargs: response(
            SUBMIT,
            description(
                unresolved=(
                    next(
                        json.loads(row["content"])["unanswered"]
                        for row in kwargs["messages"]
                        if row["role"] == "tool" and "unanswered" in json.loads(row["content"])
                    ),
                )
            ),
        ),
        response(REVIEW, accepted()),
    )
    result = await collect_information(provider, Request(objective="Define exception handling."))
    assert result.status == "needs_input" and not result.ready
    errors = [json.loads(row["content"]) for row in provider.requests[2]["messages"] if row["role"] == "tool"]
    assert any("preserve unanswered" in row.get("error", "") for row in errors)
    worker = SimpleNamespace(baseline=SimpleNamespace(config=SimpleNamespace(workspace_path=tmp_path)))
    with pytest.raises(ValueError, match="not ready"):
        handover_information(worker, result)
    assert not (tmp_path / "uploads").exists()


@pytest.mark.asyncio
async def test_unknown_evidence_is_rejected_before_review():
    provider = Provider(
        response(SUBMIT, description(evidence=("invented-source",))),
        response(SUBMIT, description()),
        response(REVIEW, accepted()),
    )
    assert (await collect_information(provider, Request(objective="Define the expert's scope."))).ready
    assert any(
        "unknown evidence" in row.get("content", "")
        for row in provider.requests[1]["messages"]
        if row["role"] == "tool"
    )


@pytest.mark.asyncio
async def test_truncated_native_calls_and_submissions_are_rejected_before_use(tmp_path):
    (tmp_path / "method.md").write_text("Only complete reads can support the description.")
    registry = ToolRegistry()
    registry.register(ReadFileTool(workspace=tmp_path, allowed_dirs=(tmp_path,), follow_binding=False))
    cut_read = response("read_file", {"path": "method.md"})
    cut_read.tool_calls[0].run_meta = RunMeta(truncation=TruncationInfo(at_tokens=100))
    cut_submit = response(SUBMIT, description())
    cut_submit.tool_calls[0].run_meta = RunMeta(arguments_repaired=True)
    provider = Provider(cut_read, cut_submit, response(SUBMIT, description()), response(REVIEW, accepted()))
    result = await collect_information(provider, Request(objective="Describe the project expert."), registry=registry)
    assert result.ready
    assert all(source.channel != "tool" for source in result.snapshot.evidence)
    messages = provider.requests[2]["messages"]
    errors = [
        json.loads(row["content"])["error"]
        for row in messages
        if row["role"] == "tool" and "error" in json.loads(row["content"])
    ]
    assert any("truncated" in error for error in errors)
    assert any("valid JSON" in error for error in errors)


@pytest.mark.asyncio
async def test_a_blocking_native_refusal_stops_other_acquisitions_in_the_same_batch():
    class Refusal(str):
        blocks_call = True

    class Registry:
        def get_definitions(self):
            return [{"type": "function", "function": {"name": "read_file", "parameters": {}}}]

        async def execute(self, *args, **kwargs):
            return Refusal("Error: access denied")

    combined = response("read_file", {"path": "private"})
    combined.tool_calls.extend(
        response(
            RESEARCH,
            {
                "question": "Bypass the refusal?",
                "dimensions": ["knowledge"],
                "context": "A private source.",
                "deliverable": "Its contents.",
            },
        ).tool_calls
    )
    delegated = []

    async def research(task):
        delegated.append(task)
        return {}

    provider = Provider(combined, response(SUBMIT, description()), response(REVIEW, accepted()))
    result = await collect_information(
        provider, Request(objective="Inspect permitted evidence."), registry=Registry(), research=research
    )
    assert result.ready and not delegated
    assert any(
        "blocked this batch" in row.get("content", "")
        for row in provider.requests[1]["messages"]
        if row["role"] == "tool"
    )


@pytest.mark.asyncio
async def test_focused_collection_preserves_other_sections_and_keeps_prior_evidence():
    previous = snapshot()
    changed = description(text="New requirements apply.")
    focused = previous.description.model_dump(mode="json")
    focused["sections"][2]["text"] = "New requirements apply."
    focused["sections"][2]["evidence"] = ["evidence-2"]
    provider = Provider(
        response(SUBMIT, changed),
        response(SUBMIT, focused),
        response(REVIEW, accepted()),
    )
    result = await collect_information(
        provider, Request(objective="New requirements apply.", previous=previous, focus=("knowledge",))
    )
    assert result.ready and result.previous == previous.identity
    assert result.snapshot.description.sections[0] == previous.description.sections[0]
    assert result.snapshot.description.sections[2].text == "New requirements apply."
    assert result.snapshot.evidence[0] == previous.evidence[0]
    assert result.snapshot.identity != previous.identity


@pytest.mark.asyncio
async def test_review_budget_exhaustion_remains_incomplete():
    provider = Provider(
        response(SUBMIT, description()),
        response(
            REVIEW,
            {
                "accepted": False,
                "reason": "Only a role declaration is present.",
                "issues": ["Research the knowledge and methods required by the task."],
            },
        ),
    )
    result = await collect_information(
        provider, Request(objective="Construct a complete expert."), limits=CollectionLimits(reviews=1)
    )
    assert not result.ready and result.status == "incomplete"


def test_handover_keeps_reference_transcripts_out_of_the_worker_workspace(tmp_path):
    original = snapshot()
    raw = Evidence(
        id="reference-data",
        channel="tool",
        origin="reference product",
        content="Original customer identity, secret example values, and product-specific installation instructions.",
    )
    information = original.model_copy(update={"evidence": (*original.evidence, raw)})
    result = Result(snapshot=information, review=Review.model_validate(accepted()))
    worker = SimpleNamespace(baseline=SimpleNamespace(config=SimpleNamespace(workspace_path=tmp_path)))
    assert handover_information(worker, result) == INFORMATION_FILE
    text = (tmp_path / INFORMATION_FILE).read_text()
    assert "Professional knowledge" in text and "Original customer identity" not in text
    assert set(path.name for path in (tmp_path / "uploads/information").iterdir()) == {"expert.md", "version.json"}


def research_group(question="How should evidence and uncertainty be handled?", **overrides):
    return {
        "dimensions": ["knowledge", "methods"],
        "brief": research_brief(question),
        **overrides,
    }


def guide():
    return ResearchGuide(
        topic="Evidence handling",
        dimensions=("knowledge", "methods"),
        questions=("What information is needed before deciding?",),
        rationale="A product case suggests investigating missing evidence.",
        sources=("guide-only-source",),
    )


@pytest.mark.parametrize(
    "channel,status", [("user", "needs_input"), ("research", "incomplete"), ("native", "incomplete")]
)
def test_blocking_acquisition_channels_are_not_all_user_questions(channel, status):
    original = snapshot()
    question = Question(
        id="pending",
        dimension="methods",
        question="Which evidence is missing?",
        reason="The current objective needs it.",
        channel=channel,
    )
    proposal = original.model_copy(
        update={"description": original.description.model_copy(update={"unresolved": (question,)})}
    )
    result = Result(snapshot=proposal, review=Review.model_validate(accepted()))
    assert result.status == status and not result.ready


@pytest.mark.asyncio
async def test_group_budget_is_visible_before_planning_and_after_each_delivery():
    async def research(task):
        return {"finding": "A supported method."}

    provider = Provider(
        response(RESEARCH, research_group()),
        response(RESEARCH, research_group()),
        response(SUBMIT, description(evidence=("evidence-3", "evidence-4"))),
        response(REVIEW, accepted()),
    )
    await collect_information(
        provider,
        Request(objective="Describe the complete expert."),
        research=research,
        limits=CollectionLimits(research_tasks=2),
    )
    packet = json.loads(provider.requests[0]["messages"][1]["content"])
    assert packet["acquisition_allowance"]["research_groups"] == 2
    remaining = [
        json.loads(row["content"])["research_groups_remaining"]
        for row in provider.requests[-2]["messages"]
        if row["role"] == "tool" and "research_groups_remaining" in json.loads(row["content"])
    ]
    assert remaining == [1, 0]


@pytest.mark.asyncio
async def test_guidance_extraction_is_bounded_without_an_independent_audit_loop(tmp_path):
    from experimental.research.guidance import SUBMIT as GUIDE_SUBMIT
    from experimental.research.guidance import derive_guidance

    source = tmp_path / "reference.md"
    source.write_text("The example accepts transcripts and written notes as alternatives.")
    registry = ToolRegistry()
    registry.register(ReadFileTool(workspace=tmp_path, allowed_dirs=(tmp_path,), follow_binding=False))
    exploration = SimpleNamespace(
        root=tmp_path,
        registry=registry,
        sources={"reference": {"snapshot_path": str(source), "digest": "fixed"}},
        describe=lambda: {"root": str(tmp_path)},
        verify=lambda: None,
    )
    good = {
        "groups": [
            {
                "topic": "Record interpretation",
                "dimensions": ["methods"],
                "questions": ["How should notes and transcripts be interpreted?"],
                "rationale": "Both input types are accepted; the distinction needs research.",
                "sources": ["reference"],
            }
        ]
    }
    provider = Provider(
        response("read_file", {"path": str(source)}),
        response(GUIDE_SUBMIT, good),
    )
    groups = await derive_guidance(
        provider,
        "Describe record interpretation.",
        exploration,
        records=tmp_path / "records",
        limits=CollectionLimits(guidance_calls=4),
    )
    assert groups[0].rationale == good["groups"][0]["rationale"]
    assert len(provider.requests) == 2
    assert not list((tmp_path / "records").glob("review-*.json"))


@pytest.mark.parametrize("guided", [False, True])
@pytest.mark.asyncio
async def test_sufficient_interaction_material_needs_no_research_or_guidance(tmp_path, guided):
    (tmp_path / "provided.md").write_text("The user supplied the complete method for this task.")
    registry = ToolRegistry()
    registry.register(ReadFileTool(workspace=tmp_path, allowed_dirs=(tmp_path,), follow_binding=False))

    async def unused(*args):
        pytest.fail("sufficient interaction information must not trigger extra acquisition")

    provider = Provider(
        response("read_file", {"path": "provided.md"}),
        response(SUBMIT, description(evidence=("evidence-3",))),
        response(REVIEW, accepted()),
    )
    result = await collect_information(
        provider,
        Request(objective="Use the supplied method."),
        registry=registry,
        research=unused,
        guidance=unused if guided else None,
    )
    assert result.ready and all(source.channel != "research" for source in result.snapshot.evidence)


@pytest.mark.asyncio
async def test_research_groups_span_dimensions_reuse_evidence_and_share_lazy_guidance(tmp_path):
    tasks, guidance_calls = [], []

    async def guidance():
        guidance_calls.append(True)
        return (guide(),)

    async def research(task):
        tasks.append(task)
        return {"finding": "Explain which claims remain uncertain.", "sources": ["https://example.org/evidence"]}

    provider = Provider(
        response(RESEARCH, research_group(known_evidence=["evidence-1"])),
        response(RESEARCH, research_group(question="How should the method be checked?", known_evidence=["evidence-3"])),
        response(SUBMIT, description(evidence=("evidence-3", "evidence-4"))),
        response(REVIEW, accepted()),
    )
    provider.responses.insert(
        0,
        response(
            GUIDANCE, {"question": "Research the missing evidence method", "dimensions": ["knowledge", "methods"]}
        ),
    )
    result = await collect_information(
        provider,
        Request(objective="Construct an evidence expert."),
        research=research,
        guidance=guidance,
        records=tmp_path / "records",
    )
    assert result.ready and len(guidance_calls) == 1
    assert tasks[0].dimensions == ("knowledge", "methods")
    assert tasks[0].known_information[0].channel == "request"
    assert tasks[1].known_information[0].channel == "research"
    assert tasks[0].guidance == tasks[1].guidance == (guide(),)
    assert result.snapshot.evidence[-1].dimensions == ("knowledge", "methods")
    assert not any("guide-only-source" in item.content for item in result.snapshot.evidence)
    assert len(json.loads((tmp_path / "records/research-tasks.json").read_text())) == 2


@pytest.mark.parametrize("use_guidance", [False, True])
@pytest.mark.asyncio
async def test_research_can_use_or_decline_prepared_guidance(use_guidance):
    tasks = []

    async def research(task):
        tasks.append(task)
        return {"finding": "Check the original evidence."}

    provider = Provider(
        response(RESEARCH, research_group(use_guidance=use_guidance)),
        response(SUBMIT, description(evidence=("evidence-3",))),
        response(REVIEW, accepted()),
    )
    if use_guidance:
        provider.responses.insert(
            0,
            response(
                GUIDANCE, {"question": "Research the missing evidence method", "dimensions": ["knowledge", "methods"]}
            ),
        )
    result = await collect_information(
        provider, Request(objective="Construct an evidence expert.", guidance=(guide(),)), research=research
    )
    assert result.ready and tasks[0].guidance == ((guide(),) if use_guidance else ())


@pytest.mark.asyncio
async def test_optional_guidance_failure_falls_back_to_unguided_research(tmp_path):
    tasks = []

    async def unavailable():
        raise ValueError("the optional case cannot be interpreted")

    async def research(task):
        tasks.append(task)
        return {"finding": "Research the stated gap directly."}

    provider = Provider(
        response(RESEARCH, research_group()),
        response(SUBMIT, description(evidence=("evidence-3",))),
        response(REVIEW, accepted()),
    )
    provider.responses.insert(
        0,
        response(
            GUIDANCE, {"question": "Research the missing evidence method", "dimensions": ["knowledge", "methods"]}
        ),
    )
    result = await collect_information(
        provider,
        Request(objective="Construct an evidence expert."),
        research=research,
        guidance=unavailable,
        records=tmp_path / "records",
    )
    assert result.ready and not tasks[0].guidance
    assert any(
        item["event"] == "guidance.unavailable" for item in json.loads((tmp_path / "records/trace.json").read_text())
    )


@pytest.mark.asyncio
async def test_timeout_is_visible_to_the_collector_without_admitting_evidence():
    async def timed_out(task):
        raise TimeoutError

    def preserve_gap(request):
        failure = json.loads(request["messages"][-1]["content"])
        assert failure["error_type"] == "TimeoutError" and failure["error"]
        assert failure["research_groups_remaining"] == 0
        return response(
            SUBMIT,
            description(
                unresolved=[
                    {
                        "id": "research-pending",
                        "dimension": "methods",
                        "question": "What method is supported?",
                        "reason": "The research did not complete.",
                        "channel": "research",
                        "blocking": True,
                    }
                ]
            ),
        )

    provider = Provider(response(RESEARCH, research_group()), preserve_gap, response(REVIEW, accepted()))
    result = await collect_information(
        provider,
        Request(objective="Describe the expert."),
        research=timed_out,
        limits=CollectionLimits(research_tasks=1),
    )
    assert result.status == "incomplete"
    assert not any(item.channel == "research" for item in result.snapshot.evidence)


@pytest.mark.asyncio
async def test_group_scope_and_known_evidence_are_checked_before_delegation():
    previous = snapshot()
    provider = Provider(
        response(RESEARCH, research_group()),
        response(RESEARCH, research_group(dimensions=["knowledge"], known_evidence=["unknown"])),
        response(SUBMIT, previous.description.model_dump(mode="json")),
        response(REVIEW, accepted()),
    )

    async def unused(task):
        pytest.fail("invalid research groups must not spend a research call")

    result = await collect_information(
        provider, Request(objective="Check knowledge.", focus=("knowledge",), previous=previous), research=unused
    )
    assert result.ready and result.changed_dimensions == ()


@pytest.mark.asyncio
async def test_focused_followup_accepts_answers_and_preserves_other_pending_questions(tmp_path):
    questions = (
        Question(
            id="question-1", dimension="methods", question="Who approves exceptions?", reason="Authority is unknown."
        ),
        Question(
            id="question-2",
            dimension="cases",
            question="Are there historical cases?",
            reason="Additional examples would help.",
            blocking=False,
        ),
    )
    previous = snapshot()
    previous = Snapshot(
        description=previous.description.model_copy(update={"unresolved": questions}), evidence=previous.evidence
    )
    data = previous.description.model_dump(mode="json")
    data["unresolved"] = [questions[1].model_dump(mode="json")]
    data["sections"][4].update(text="The team lead approves exceptions.", evidence=["evidence-4"])
    provider = Provider(response(SUBMIT, data), response(REVIEW, accepted()))
    result = await collect_information(
        provider,
        Request(
            objective="Resolve approval authority.",
            previous=previous,
            focus=("methods",),
            answers={"question-1": "The team lead approves exceptions."},
            answers_version=previous.identity,
        ),
        records=tmp_path / "records",
    )
    assert result.ready and result.changed_dimensions == ("methods",)
    assert result.snapshot.description.unresolved == (questions[1],)
    assert result.snapshot.evidence[-1].channel == "user"
    assert Snapshot.model_validate_json((tmp_path / "records/snapshot.json").read_text()) == result.snapshot
    with pytest.raises(ValidationError, match="known questions inside"):
        Request(objective="Resolve methods.", previous=previous, focus=("methods",), answers={"question-2": "Yes"})


def test_information_handoff_checks_base_version_content_and_pending_curation(tmp_path):
    worker = SimpleNamespace(
        root=tmp_path / "run", baseline=SimpleNamespace(config=SimpleNamespace(workspace_path=tmp_path / "home"))
    )
    initial = Result(snapshot=snapshot(), review=Review.model_validate(accepted()))
    handover_information(worker, initial)
    changed = Snapshot(
        description=Description.model_validate(description(text="An updated description.")),
        evidence=initial.snapshot.evidence,
    )
    stale = Result(snapshot=changed, review=initial.review, previous="another-version")
    with pytest.raises(ValueError, match="base version changed"):
        handover_information(worker, stale)
    updated = stale.model_copy(update={"previous": initial.snapshot.identity})
    handover_information(worker, updated)
    assert handover_information(worker, updated) == INFORMATION_FILE
    pending = worker.root / "curation/pending.json"
    pending.parent.mkdir(parents=True)
    pending.write_text("{}")
    with pytest.raises(ValueError, match="paused curation"):
        handover_information(worker, updated)
    pending.unlink()
    (worker.baseline.config.workspace_path / INFORMATION_FILE).write_text("Unversioned edit")
    with pytest.raises(ValueError, match="changed outside"):
        handover_information(worker, updated)


@pytest.mark.asyncio
async def test_uncited_user_constraints_are_still_visible_to_review():
    answer = "Do not process restricted project data."
    provider = Provider(
        response(ASK, {"dimension": "role", "question": "What is excluded?", "reason": "Establish scope."}),
        response(SUBMIT, description()),
        response(REVIEW, accepted()),
    )
    result = await collect_information(provider, Request(objective="Build a project reviewer."), ask=lambda q: answer)
    reviewed = json.loads(provider.requests[-1]["messages"][1]["content"])
    assert any(row["channel"] == "user" and row["content"] == answer for row in reviewed["evidence"])
    assert result.snapshot.evidence[-1].id not in result.snapshot.description.references


@pytest.mark.asyncio
async def test_guidance_is_read_before_grouping_and_can_change_the_group():
    tasks = []

    async def research(task):
        tasks.append(task)
        return {"finding": "Record scope and uncertainty together."}

    provider = Provider(
        response(RESEARCH, research_group()),
        response(GUIDANCE, {"question": "How to review uncertain evidence?", "dimensions": ["knowledge", "methods"]}),
        response(RESEARCH, research_group(question="How should scope and uncertainty be reviewed together?")),
        response(SUBMIT, description(evidence=("evidence-3",))),
        response(REVIEW, accepted()),
    )
    await collect_information(provider, Request(objective="Review evidence.", guidance=(guide(),)), research=research)
    assert len(tasks) == 1 and "together" in tasks[0].brief.questions[0]
    messages = provider.requests[2]["messages"]
    assert any("prepare_research" in row.get("content", "") for row in messages if row["role"] == "tool")
    assert any("guide-only-source" in row.get("content", "") for row in messages if row["role"] == "tool")


@pytest.mark.asyncio
async def test_resource_and_question_changes_are_reported_without_section_changes():
    prior = snapshot()
    pending = Question(id="known", dimension="methods", question="Which service?", reason="Access is unknown.")
    prior = Snapshot(
        description=prior.description.model_copy(update={"unresolved": (pending,)}), evidence=prior.evidence
    )
    data = prior.description.model_dump(mode="json")
    data["unresolved"] = []
    data["resources"] = [
        {
            "name": "Registry",
            "purpose": "Check evidence",
            "availability": "unavailable",
            "requirements": ["User access is needed."],
        }
    ]
    provider = Provider(response(SUBMIT, data), response(REVIEW, accepted()))
    result = await collect_information(
        provider,
        Request(
            objective="Clarify prerequisites.",
            previous=prior,
            focus=("methods",),
            answers={"known": "The registry is unavailable; use supplied evidence only."},
            answers_version=prior.identity,
        ),
    )
    assert result.changed_dimensions == ()
    assert result.resources_changed and result.questions_changed


@pytest.mark.parametrize("checkpoint", ["composition.json", "attribution-scope/root/curation/pending.json"])
def test_publication_refuses_composite_and_nested_checkpoints(tmp_path, checkpoint):
    worker = SimpleNamespace(
        root=tmp_path / "run", baseline=SimpleNamespace(config=SimpleNamespace(workspace_path=tmp_path / "home"))
    )
    path = worker.root / "curation" / checkpoint
    path.parent.mkdir(parents=True)
    path.write_text("{}")
    with pytest.raises(ValueError, match="paused curation"):
        handover_information(worker, Result(snapshot=snapshot(), review=Review.model_validate(accepted())))
    assert not (tmp_path / "home").exists()


def test_interrupted_publication_recovers_the_same_version(tmp_path, monkeypatch):
    from experimental.research import curator

    worker = SimpleNamespace(
        root=tmp_path / "run", baseline=SimpleNamespace(config=SimpleNamespace(workspace_path=tmp_path / "home"))
    )
    result = Result(snapshot=snapshot(), review=Review.model_validate(accepted()))
    write = curator._write
    failed = []

    def interrupted(path, content):
        if path.name == "version.json" and not failed:
            failed.append(True)
            raise OSError("Interrupted between content and version publication")
        write(path, content)

    monkeypatch.setattr(curator, "_write", interrupted)
    with pytest.raises(OSError):
        handover_information(worker, result)
    target = tmp_path / "home" / INFORMATION_FILE
    assert (target.parent / "publication.json").exists()
    handover_information(worker, result)
    assert not (target.parent / "publication.json").exists()
    assert json.loads((target.parent / "version.json").read_text())["version"] == result.snapshot.identity


def test_review_cannot_be_reused_after_changing_its_snapshot(tmp_path):
    result = Result(snapshot=snapshot(), review=Review.model_validate(accepted()))
    data = result.model_dump(mode="json")
    data["snapshot"]["description"]["sections"][0]["text"] = "Different unsupported role."
    with pytest.raises(ValueError, match="another information version"):
        Result.model_validate(data)


@pytest.mark.asyncio
async def test_adoption_answers_are_tied_to_the_exact_proposal_and_question():
    seen = []

    def answer(question):
        seen.append(question)
        return "Adopt this proposal for the review team."

    provider = Provider(
        response(
            ASK,
            {
                "dimension": "methods",
                "question": "Adopt this workflow?",
                "proposal": "Require a second reviewer for uncertain claims.",
                "reason": "This is an organisational choice.",
            },
        ),
        response(SUBMIT, description(evidence=("evidence-3",))),
        response(REVIEW, accepted()),
    )
    result = await collect_information(provider, Request(objective="Define the workflow."), ask=answer)
    origin = json.loads(result.snapshot.evidence[-1].origin)
    assert origin["id"] == seen[0].id
    assert origin["proposal"] == "Require a second reviewer for uncertain claims."
    assert "Adopt this proposal" in render(result.snapshot)


def test_abandoned_composition_scope_does_not_block_new_information(tmp_path):
    worker = SimpleNamespace(
        root=tmp_path / "run", baseline=SimpleNamespace(config=SimpleNamespace(workspace_path=tmp_path / "home"))
    )
    abandoned = worker.root / "curation/scopes/old/child/curation/pending.json"
    abandoned.parent.mkdir(parents=True)
    abandoned.write_text("{}")
    assert (
        handover_information(worker, Result(snapshot=snapshot(), review=Review.model_validate(accepted())))
        == INFORMATION_FILE
    )


def test_answers_refuse_another_snapshot_even_when_question_ids_match():
    base = snapshot()
    question = Question(
        id="known-question",
        dimension="methods",
        question="Adopt this method?",
        proposal="Use two reviewers.",
        reason="An organisational decision is needed.",
    )
    previous = Snapshot(
        description=base.description.model_copy(update={"unresolved": (question,)}), evidence=base.evidence
    )
    with pytest.raises(ValueError, match="exact previous information version"):
        Request(
            objective="Resolve adoption.",
            previous=previous,
            answers={question.id: "Yes"},
            answers_version="another-version",
        )


def test_recorded_information_restores_source_scope_on_a_new_worker():
    from experimental.curator.raven_adapter.exploration import Withheld
    from experimental.curator.workflow import information_scope

    worker = SimpleNamespace(withheld=Withheld(paths=("evaluation/*",)))
    feedback = {"information": {"version": "recorded", "excluded_sources": ["docs/research-case.md"]}}
    information_scope(worker, feedback)
    information_scope(worker, feedback)
    assert worker.withheld.paths == ("evaluation/*", "docs/research-case.md")


@pytest.mark.asyncio
async def test_review_repair_acknowledges_the_prior_submission_before_next_model_call():
    def revise(kwargs):
        messages = kwargs["messages"]
        submitted = next(
            index for index, row in enumerate(messages) if row["role"] == "assistant" and row.get("tool_calls")
        )
        acknowledgement = messages[submitted + 1]
        assert acknowledgement["role"] == "tool"
        assert acknowledgement["tool_call_id"] == messages[submitted]["tool_calls"][0]["id"]
        assert json.loads(acknowledgement["content"])["status"] == "submitted_for_review"
        return response(SUBMIT, description(text="A corrected description."))

    provider = Provider(
        response(SUBMIT, description()),
        response(REVIEW, {"accepted": False, "reason": "Clarify scope", "issues": ["State the limitation."]}),
        revise,
        response(REVIEW, accepted()),
    )
    result = await collect_information(provider, Request(objective="Describe the expert."))
    assert result.ready
    review_input = json.loads(provider.requests[-1]["messages"][1]["content"])
    assert review_input["previous_reviews"][0]["issues"] == ["State the limitation."]


@pytest.mark.asyncio
async def test_collector_owns_repair_and_rejected_content_never_becomes_evidence(tmp_path):
    tasks = []

    async def research(task):
        tasks.append(task)
        if len(tasks) == 1:
            return {
                "synthesis": "Unsupported operational claim.",
                "review": {
                    "accepted": False,
                    "reason": "Missing conditions.",
                    "issues": ["Qualify when the method applies."],
                },
            }
        assert task.previous_attempt == tasks[0].attempt
        assert task.brief.questions == ("When is the method applicable?",)
        return {"findings": [], "synthesis": "A qualified method.", "review": accepted()}

    def repair(request):
        feedback = json.loads(request["messages"][-1]["content"])
        assert not feedback["review"]["accepted"]
        assert "Unsupported operational claim" not in json.dumps(feedback)
        assert feedback["research_groups_remaining"] == 0
        return response(
            RESEARCH, research_group(question="When is the method applicable?", previous_attempt=feedback["attempt"])
        )

    provider = Provider(
        response(RESEARCH, research_group()),
        repair,
        response(SUBMIT, description(evidence=("evidence-3",))),
        response(REVIEW, accepted()),
    )
    result = await collect_information(
        provider,
        Request(objective="Describe the expert."),
        research=research,
        limits=CollectionLimits(research_tasks=1),
        records=tmp_path / "run",
    )
    assert result.ready and len(tasks) == 2
    assert "Unsupported operational claim" not in result.snapshot.model_dump_json()
    state = json.loads((tmp_path / "run/research-attempts.json").read_text())
    assert state["research-1"]["superseded"] and state["research-2"]["accepted"]


@pytest.mark.asyncio
async def test_collector_cannot_branch_from_an_old_attempt_to_reset_revision_allowance():
    tasks = []

    async def research(task):
        tasks.append(task)
        return {"review": {"accepted": False, "reason": "Unsupported.", "issues": ["Find supporting evidence."]}}

    provider = Provider(
        response(RESEARCH, research_group()),
        response(RESEARCH, research_group(previous_attempt="research-1")),
        response(RESEARCH, research_group(previous_attempt="research-1")),
        response(RESEARCH, research_group(previous_attempt="research-2")),
        response(
            SUBMIT,
            description(
                unresolved=[
                    {
                        "id": "method",
                        "dimension": "methods",
                        "question": "What method is supported?",
                        "reason": "Research remains incomplete.",
                        "channel": "research",
                        "blocking": True,
                    }
                ]
            ),
        ),
        response(REVIEW, accepted()),
    )
    result = await collect_information(
        provider,
        Request(objective="Describe the expert."),
        research=research,
        limits=CollectionLimits(research_tasks=1, research_revisions=1),
    )
    assert len(tasks) == 2 and result.status == "incomplete"
    errors = [
        json.loads(row["content"]).get("error", "")
        for row in provider.requests[-2]["messages"]
        if row["role"] == "tool"
    ]
    assert any("latest unaccepted" in error for error in errors)
    assert any("revision allowance exhausted" in error for error in errors)


@pytest.mark.asyncio
async def test_overall_deadline_cancels_nested_research_and_retains_unfinished_snapshot(tmp_path):
    cancelled = []

    async def research(task):
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.append(task.attempt)

    provider = Provider(response(RESEARCH, research_group()))
    result = await collect_information(
        provider,
        Request(objective="Describe the expert."),
        research=research,
        limits=CollectionLimits(total_timeout=0.02, reserve=0, research_minimum=0.001, verification_reserve=0),
        records=tmp_path / "run",
    )
    assert cancelled == ["research-1"]
    assert result.status == "incomplete" and result.stop_reason == "time_limit"
    assert not any(e.channel == "research" for e in result.snapshot.evidence)
    assert (tmp_path / "run/conversation.json").exists()
    assert Result.model_validate_json((tmp_path / "run/result.json").read_text()).stop_reason == "time_limit"


@pytest.mark.asyncio
async def test_call_exhaustion_returns_an_incomplete_result_instead_of_losing_evidence():
    provider = Provider(response("unknown_tool", {}))
    result = await collect_information(
        provider, Request(objective="Describe the expert."), limits=CollectionLimits(calls=1)
    )
    assert result.stop_reason == "call_limit" and not result.ready
    assert result.snapshot.evidence[0].content == "Describe the expert."


@pytest.mark.asyncio
async def test_deadline_preserves_focused_state_and_reports_actual_changes():
    class Slow:
        async def chat_with_retry(self, **kwargs):
            await asyncio.sleep(10)

    previous = snapshot()
    result = await collect_information(
        Slow(),
        Request(objective="Recheck knowledge.", previous=previous, focus=("knowledge",)),
        limits=CollectionLimits(total_timeout=0.01),
    )
    assert result.snapshot.description == previous.description
    assert result.changed_dimensions == () and not result.resources_changed and not result.questions_changed
    assert result.stop_reason == "time_limit" and not result.ready


@pytest.mark.asyncio
async def test_default_hour_budget_is_shared_and_elapsed_time_is_not_refunded(monkeypatch):
    from experimental.research import collection

    clock = [100.0]
    monkeypatch.setattr(collection, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    remaining = []

    async def research(task):
        remaining.append(task.remaining_seconds)
        clock[0] += 901
        return {"finding": "A supported method."}

    provider = Provider(
        response(RESEARCH, research_group()),
        response(RESEARCH, research_group()),
        response(SUBMIT, description(evidence=("evidence-3", "evidence-4"))),
        response(REVIEW, accepted()),
    )
    result = await collect_information(provider, Request(objective="Describe the expert."), research=research)
    assert result.ready
    assert remaining == [3000, 2099]
    packet = json.loads(provider.requests[0]["messages"][1]["content"])
    assert packet["acquisition_allowance"]["total_timeout_seconds"] == 3600
    assert packet["acquisition_allowance"]["submission_reserve_seconds"] == 600


@pytest.mark.asyncio
async def test_research_is_refused_once_the_submission_reserve_begins():
    async def unused(task):
        pytest.fail("no research may start inside the submission reserve")

    def preserve_gap(request):
        error = json.loads(request["messages"][-1]["content"])["error"]
        assert "submission reserve" in error and "submit" in error
        return response(SUBMIT, description())

    provider = Provider(response(RESEARCH, research_group()), preserve_gap, response(REVIEW, accepted()))
    result = await collect_information(
        provider,
        Request(objective="Describe the expert."),
        research=unused,
        limits=CollectionLimits(total_timeout=100, reserve=70, research_minimum=60, verification_reserve=20),
    )
    assert result.ready
    packet = json.loads(provider.requests[0]["messages"][1]["content"])
    assert packet["acquisition_allowance"]["submission_reserve_seconds"] == 70
    assert packet["acquisition_allowance"]["questions_per_group"] == 2


@pytest.mark.asyncio
async def test_research_time_excludes_the_reserve_and_groups_are_capped_by_questions():
    delegated = []

    async def research(task):
        delegated.append(task)
        return {"finding": "A supported method.", "sources": ["https://example.org/method"]}

    def narrowed(request):
        error = json.loads(request["messages"][-1]["content"])["error"]
        assert "at most 2 questions" in error
        return response(RESEARCH, research_group(brief=research_brief(questions=["One?", "Two?"])))

    provider = Provider(
        response(RESEARCH, research_group(brief=research_brief(questions=["One?", "Two?", "Three?"]))),
        narrowed,
        response(SUBMIT, description(evidence=("evidence-3",))),
        response(REVIEW, accepted()),
    )
    result = await collect_information(
        provider,
        Request(objective="Describe the expert."),
        research=research,
        limits=CollectionLimits(total_timeout=1000, reserve=400, research_timeout=3600),
    )
    assert result.ready and len(delegated) == 1
    assert 590 < delegated[0].remaining_seconds <= 600
    replies = [json.loads(row["content"]) for row in provider.requests[2]["messages"] if row["role"] == "tool"]
    delivered = next(reply for reply in replies if "evidence" in reply)
    assert 0 < delivered["research_seconds_available"] <= 600


@pytest.mark.asyncio
async def test_read_sources_reads_listed_sources_together_as_separate_evidence(tmp_path):
    (tmp_path / "role.md").write_text("The role prompt.")
    (tmp_path / "skill.md").write_text("x" * 30_500)
    context = {
        "interaction_sources": {
            "material.1.role.md": {
                "path": str(tmp_path / "role.md"),
                "source_path": "/home/uploads/role.md",
                "digest": "a",
            },
            "material.1.skill.md": {
                "path": str(tmp_path / "skill.md"),
                "source_path": "/home/uploads/skill.md",
                "digest": "b",
            },
        }
    }

    def submit(request):
        rejection, reply = (json.loads(row["content"]) for row in request["messages"] if row["role"] == "tool")
        assert "unknown: ['missing']" in rejection["error"]
        assert [row["name"] for row in reply["sources"]] == ["material.1.role.md", "material.1.skill.md"]
        assert reply["sources"][0]["result"] == "The role prompt." and not reply["sources"][0]["truncated"]
        assert reply["sources"][1]["truncated"] and "truncated at 30000" in reply["sources"][1]["result"]
        return response(SUBMIT, description(evidence=("evidence-3", "evidence-4")))

    provider = Provider(
        response(READ, {"names": ["material.1.role.md", "missing"]}),
        response(READ, {"names": ["material.1.role.md", "material.1.skill.md"]}),
        submit,
        response(REVIEW, accepted()),
    )
    result = await collect_information(provider, Request(objective="Read the material.", context=context))
    assert result.ready
    read = [source for source in result.snapshot.evidence if source.channel == "tool"]
    assert len(read) == 2 and read[0].sources == ("/home/uploads/role.md#sha256=a",)
    assert json.loads(read[1].origin)["source"] == "material.1.skill.md"
    assert READ in {entry["function"]["name"] for entry in provider.requests[0]["tools"]}
    bare = Provider(response(SUBMIT, description()), response(REVIEW, accepted()))
    await collect_information(bare, Request(objective="No listed sources."))
    assert READ not in {entry["function"]["name"] for entry in bare.requests[0]["tools"]}


def test_the_researcher_keeps_time_for_verification_and_review_inside_its_window():
    limits = CollectionLimits()
    assert limits.acquisition_window(600) == 450
    assert limits.acquisition_window(320) == 170
    assert limits.acquisition_window(limits.research_minimum) == 150
    with pytest.raises(ValueError, match="verification reserve"):
        CollectionLimits(research_minimum=100, verification_reserve=100)
