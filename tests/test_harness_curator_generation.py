"""Bounded planning, source queries and repair operate on host-owned contracts."""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from experimental.harness.contract import Attributed, Attribution, Declaration, Diagnosis, Validation
from experimental.harness.curator.generation.context.collect import collect
from experimental.harness.curator.generation.context.render import REREAD
from experimental.harness.curator.generation.run import GenerationError, Limits
from experimental.harness.curator.generation.run import generate as generate_from
from experimental.harness.raven_adapter.targets import catalogue
from raven.contracts.llm_provider import LLMResponse, RunMeta, ToolCallRequest
from raven.contracts.tool import RAW_ARGUMENTS_KEY


class Provider:
    def __init__(self, *responses, auto_consistency_review=True):
        self.responses = list(responses)
        self.requests = []
        self.auto_consistency_review = auto_consistency_review

    async def chat_with_retry(self, **kwargs):
        self.requests.append(kwargs)
        if self.auto_consistency_review and (reviewed := consistency_review_response(kwargs["messages"])) is not None:
            return reviewed
        value = self.responses.pop(0)
        return value(kwargs) if callable(value) else value


def consistency_review_response(
    messages, *, issues=(), limitations=("Replay validates mechanics, not model consistency judgment.",)
):
    """Supply a consistency review response to replay tests that do not test consistency judgment."""
    if len(messages) < 4:
        return None
    content = messages[3].get("content")
    if not isinstance(content, str) or not content.startswith("{"):
        return None
    materials = json.loads(content).get("consistency_review")
    if materials is None:
        return None
    return response(
        "submit_consistency_review",
        {
            "candidate_id": materials["candidate_id"],
            "surfaces": {
                name: "The supplied replay scenario retains compatible behavior." for name in materials["surfaces"]
            },
            "interactions": "No additional conflict is specified by this replay scenario.",
            "issues": list(issues),
            "limitations": list(limitations),
        },
    )


@pytest.mark.asyncio
async def test_consistency_review_covers_retained_consumers_and_rechecks_repaired_candidate(context):
    from dataclasses import replace

    authored = {
        "values": {"memory.strategy": {"factory": "memory:create"}},
        "files": {
            "memory.py": "from .shared import read\n",
            "shared.py": "def read(): return 'kept'\n",
            "rules.py": "",
        },
    }
    context = replace(context, facts={**context.facts, "authored": authored})
    draft = {
        "values": {"action.strategy": {"factory": "rules:create"}},
        "files": {"shared.py": "def read(): return None\n"},
    }
    identifiers = []

    def inspect_candidate(request):
        whole = packet(request)["consistency_review"]
        identifiers.append(whole["candidate_id"])
        assert whole["effective_artifact"]["values"]["memory.strategy"] == authored["values"]["memory.strategy"]
        assert whole["effective_artifact"]["files"]["memory.py"] == authored["files"]["memory.py"]
        assert set(whole["surfaces"]) == {target.name for target in context.declaration.targets}
        assert "None" in whole["effective_artifact"]["files"]["shared.py"]
        return consistency_review_response(
            request["messages"],
            issues=[
                {
                    "surfaces": ["memory.strategy", "action.strategy"],
                    "evidence": "shared.read now returns None to the retained Memory consumer.",
                    "correction": "Preserve the existing string result for retained consumers.",
                    "blocking": True,
                }
            ],
        )

    def inspect_repair(request):
        whole = packet(request)["consistency_review"]
        identifiers.append(whole["candidate_id"])
        assert "'kept'" in whole["effective_artifact"]["files"]["shared.py"]
        return consistency_review_response(request["messages"])

    provider = Provider(
        response("submit_selection", selection("action.strategy")),
        response("submit_plan", plan("action.strategy")),
        response("submit_artifact", draft),
        inspect_candidate,
        response("submit_artifact", {**draft, "files": {"shared.py": authored["files"]["shared.py"]}}),
        inspect_repair,
        auto_consistency_review=False,
    )
    validate = AsyncMock(return_value=Validation([], [{"kind": "runtime.bound"}]))
    result = await generate(context, provider, validate=validate)
    assert validate.await_count == 2 and len(set(identifiers)) == 2
    assert result.consistency_review.candidate_id == identifiers[-1]
    assert "shared.read now returns None" in str(packet(provider.requests[4])["validation_errors"])
    assert [row["stage"] for row in result.trace if row["event"] == "model.call"] == [
        "select",
        "design",
        "implement",
        "consistency_review",
        "repair",
        "consistency_review",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["identity", "coverage", "edit"])
async def test_consistency_review_rejects_stale_or_incomplete_reports_and_cannot_edit(context, fault):
    def invalid(request):
        value = consistency_review_response(request["messages"])
        if fault == "edit":
            return response("stage_file", {"path": "bypass.py", "content": "BYPASS = True\n"})
        arguments = value.tool_calls[0].arguments
        if fault == "identity":
            arguments["candidate_id"] = "another-version"
        else:
            arguments["surfaces"].pop("memory.strategy")
        return value

    provider = Provider(
        response("submit_selection", selection()),
        invalid,
        lambda request: consistency_review_response(request["messages"]),
        auto_consistency_review=False,
    )
    validate = AsyncMock(return_value=Validation([], []))
    result = await generate(context, provider, validate=validate)
    assert result.consistency_review and "bypass.py" not in result.candidate.artifact.files
    event = "action.unavailable" if fault == "edit" else "output.rejected"
    assert any(row["stage"] == "consistency_review" and row["event"] == event for row in result.trace)
    assert validate.await_count == 1


@pytest.mark.asyncio
async def test_pending_consistency_review_resumes_without_replaying_implementation_or_validation(context):
    from experimental.harness.curator.generation.run import GenerationPausedError
    from experimental.harness.curator.generation.state import GenerationState

    provider = Provider(
        response("submit_selection", selection("action.strategy")),
        response("submit_plan", plan("action.strategy")),
        response("submit_artifact", {"values": {"action.strategy": {"factory": "rules:create"}}}),
    )
    validate = AsyncMock(return_value=Validation([], []))
    with pytest.raises(GenerationPausedError) as paused:
        await generate(context, provider, validate=validate, limits=Limits(max_calls=3))
    assert paused.value.state.stage == "consistency_review"
    state = GenerationState.model_validate_json(paused.value.state.model_dump_json())
    resumed = Provider()
    result = await generate(context, resumed, validate=validate, limits=Limits(max_calls=4), resume=state)
    assert result.consistency_review and len(resumed.requests) == 1 and validate.await_count == 1


@pytest.mark.asyncio
async def test_blocking_consistency_review_cannot_bypass_the_repair_budget(context):
    provider = Provider(
        response("submit_selection", selection()),
        lambda request: consistency_review_response(
            request["messages"],
            issues=[
                {
                    "surfaces": ["memory.strategy"],
                    "evidence": "A retained consumer loses required input.",
                    "correction": "Preserve the input.",
                    "blocking": True,
                }
            ],
        ),
        auto_consistency_review=False,
    )
    with pytest.raises(GenerationError, match="repair budget exhausted: consistency review"):
        await generate(
            context, provider, validate=AsyncMock(return_value=Validation([], [])), limits=Limits(max_repairs=0)
        )


def packet(request):
    """A stage request's data: the curation's materials, then the stage's own data."""
    import json

    messages = request["messages"]
    return {**json.loads(messages[1]["content"]), **json.loads(messages[3]["content"])}


def instructions(request):
    """A stage request's host instructions: the shared rules, then the stage's instructions and actions."""
    return request["messages"][0]["content"] + "\n\n" + request["messages"][2]["content"]


def response(name, arguments):
    return LLMResponse(content=None, tool_calls=[ToolCallRequest(name, name, arguments)])


ATTRIBUTED = Attributed(
    attribution=Attribution(diagnoses=(Diagnosis(about="task", state="absent", evidence=("task",)),)),
    identity={"implementation": "test"},
)


async def generate(context, provider, **options):
    """A generation from the task's attribution unless a test supplies another."""
    return await generate_from(context, provider, **{"attribution": ATTRIBUTED, **options})


def diagnosis(*abouts):
    """The attribution's submission covering `abouts`, or the task alone."""
    return {
        "diagnoses": [
            {"about": about, "state": "absent", "evidence": ["task"], "mechanism": ""}
            for about in (abouts or ("task",))
        ]
    }


def selection(*targets, grounds=("task",)):
    return {
        "understanding": "Current task, observed need and candidate rationale",
        "targets": list(targets),
        "grounds": {target: list(grounds) for target in targets},
    }


def plan(*targets, serves=("task",)):
    return {
        "understanding": "Current task and native mechanisms",
        "design": "Connect the chosen operations to native consumers and preserve task-owned state.",
        "changes": [
            {
                "target": name,
                "reason": "Observed need",
                "expected": "Improve behavior",
                "verification": "Inspect actual calls",
                "treatment": "add",
            }
            for name in targets
        ],
        "commitments": [
            {
                "action": "add",
                "surface": name,
                "statement": f"{name} carries out the observed need",
                "serves": list(serves),
            }
            for name in targets
        ],
    }


def assigned(declaration, *targets, current=()):
    """A plan as the design stage returns it: its added commitments carry their host ids."""
    from experimental.harness.contract.commitments import assign

    parsed = declaration.parse_plan(plan(*targets))
    return parsed.model_copy(update={"commitments": assign(current, parsed.commitments)})


def designed(context, *targets):
    return assigned(context.declaration, *targets, current=context.commitments)


@pytest.fixture
def context():
    declaration = Declaration("worker@0", catalogue())
    return collect(
        "Complete the current task",
        declaration,
        facts={
            "backend": "AgentLoop",
            "tools": [],
            "configuration": {"config": {"agents": {"defaults": {"temperature": 0.1}}}},
            "authored": {"values": {}, "files": {"rules.py": "", "shared.py": ""}},
        },
        sources={"loop": {"start": 1, "end": 30}},
        read_source=lambda **kwargs: {"source": kwargs["name"], "text": "native protocol"},
        feedback={"source": "human", "text": "The prior behavior needs a reliable check."},
    )


@pytest.mark.asyncio
async def test_plan_queries_native_materials_then_generates_combined_artifacts(context):
    provider = Provider(
        response("read_source", {"name": "loop", "length": 1000}),
        response("read_fact", {"name": "configuration", "path": ["config", "agents", "defaults"]}),
        response("submit_selection", selection("action.strategy", "capability.strategy")),
        response("submit_plan", plan("action.strategy", "capability.strategy")),
        response(
            "submit_artifact",
            {
                "values": {
                    "action.strategy": {"factory": "rules:policy_0_2"},
                    "capability.strategy": {"factory": "rules:create"},
                }
            },
        ),
    )
    checked = []

    async def validate(candidate):
        checked.append(candidate)
        return Validation([], [{"kind": "runtime.bound"}])

    result = await generate(context, provider, validate=validate)
    assert result.candidate is checked[0]
    assert set(result.candidate.artifact.values) == {"action.strategy", "capability.strategy"}
    assert [event["tool"] for event in result.trace if event["event"] == "query"] == ["read_source", "read_fact"]
    assert "human" in provider.requests[0]["messages"][1]["content"]
    assert "Background" in provider.requests[0]["messages"][0]["content"]
    assert "Select the necessary" in provider.requests[0]["messages"][2]["content"]
    assert "Understand the current task" not in provider.requests[0]["messages"][2]["content"]


@pytest.mark.asyncio
async def test_validation_can_change_the_mechanism_instead_of_only_rewriting_code(context):
    provider = Provider(
        response("submit_selection", selection("planning.strategy")),
        response("submit_plan", plan("planning.strategy")),
        response("submit_artifact", {"values": {"planning.strategy": {"factory": "rules:Participant"}}}),
        response("revise_selection", selection("action.strategy")),
        response("submit_plan", plan("action.strategy")),
        response(
            "submit_artifact",
            {
                "values": {"action.strategy": {"factory": "checks:Participant"}},
                "files": {"checks.py": "class Participant: pass"},
            },
        ),
    )
    calls = []

    async def validate(candidate):
        calls.append(candidate)
        if len(calls) == 1:
            return Validation(["Guidance did not enforce the required condition."], [{"kind": "observed.gap"}])
        return Validation([], [{"kind": "runtime.bound"}])

    result = await generate(context, provider, validate=validate)
    assert result.candidate.plan.changes[0].target == "action.strategy"
    repair_request = json.dumps(packet(provider.requests[3]), ensure_ascii=False)
    assert "Guidance did not enforce" in repair_request
    assert "observed.gap" in repair_request
    assert any(event["event"] == "revise_selection" for event in result.trace)


@pytest.mark.asyncio
async def test_empty_plan_retains_the_existing_harness_only_after_host_validation(context):
    provider = Provider(response("submit_selection", selection()))
    checked = []

    async def validate(candidate):
        checked.append(candidate)
        return Validation([], [{"kind": "probe.passed"}])

    result = await generate(context, provider, validate=validate)
    assert not result.candidate.plan.changes
    assert result.candidate.artifact.values == {}
    assert checked == [result.candidate]
    assert result.validation.observations == [{"kind": "probe.passed"}]


@pytest.mark.asyncio
async def test_failed_unchanged_candidate_enters_repair_and_can_reselect(context):
    provider = Provider(
        response("submit_selection", selection()),
        response("revise_selection", selection("action.strategy")),
        response("submit_plan", plan("action.strategy")),
        response("submit_artifact", {"values": {"action.strategy": {"factory": "rules:policy_0_2"}}}),
    )
    checked = []
    evidence = {"kind": "action.error", "operation": "decision", "arguments": [{"status": "ready"}]}

    async def validate(candidate):
        checked.append(candidate)
        return Validation(["recorded contract failure"], [evidence]) if len(checked) == 1 else Validation([], [])

    result = await generate(context, provider, validate=validate)
    assert len(checked) == 2
    assert not checked[0].artifact.values
    assert result.candidate.artifact.values == {"action.strategy": {"factory": "rules:policy_0_2"}}
    assert "recorded contract failure" in str(provider.requests[1]["messages"])
    assert "ready" in str(provider.requests[1]["messages"])
    assert [event["stage"] for event in result.trace if event["event"] == "model.call"] == [
        "select",
        "repair",
        "design",
        "implement",
        "consistency_review",
    ]


@pytest.mark.asyncio
async def test_failed_unchanged_candidate_cannot_bypass_repair_budget(context):
    async def validate(candidate):
        return Validation(["recorded contract failure"], [])

    with pytest.raises(GenerationError, match="repair budget exhausted"):
        await generate(
            context,
            Provider(response("submit_selection", selection())),
            validate=validate,
            limits=Limits(max_repairs=0),
        )


@pytest.mark.asyncio
async def test_native_commitments_are_explicit_surfaces_in_consistency_review(context):
    from dataclasses import replace

    from experimental.harness.contract import Commitment

    native = Commitment(
        id="H1", surface="native", statement="Preserve native execution authorization.", serves=("task",)
    )
    context = replace(context, commitments=(native,))
    provider = Provider(response("submit_selection", selection()))
    result = await generate(context, provider, validate=AsyncMock(return_value=Validation([], [])))
    assert "native" in result.consistency_review.surfaces
    assert packet(provider.requests[-1])["consistency_review"]["commitments_after"][0]["surface"] == "native"


@pytest.mark.asyncio
async def test_review_indexes_large_validation_evidence_and_can_read_its_complete_tail(context):
    payload = "x" * 1_000_000 + "VALIDATION_TAIL"

    def read_tail(request):
        data = packet(request)
        assert len(json.dumps(request["messages"])) < len(payload)
        validated = next(row for row in data["history"] if row["event"] == "validation")
        assert validated["observations"][0]["bytes"] > 1_000_000
        return response(
            "read_observation",
            {
                "trace_index": validated["trace_index"],
                "index": 0,
                "path": ["payload"],
                "offset": 1_000_000,
                "length": 40,
            },
        )

    def approve(request):
        result = next(row for row in reversed(request["messages"]) if row["role"] == "tool")
        assert "VALIDATION_TAIL" in result["content"]
        return consistency_review_response(request["messages"])

    provider = Provider(response("submit_selection", selection()), read_tail, approve, auto_consistency_review=False)
    validation = Validation([], [{"kind": "model.input", "payload": payload}])
    result = await generate(context, provider, validate=AsyncMock(return_value=validation))
    assert result.consistency_review and result.validation.observations[0]["payload"] == payload


@pytest.mark.asyncio
async def test_invalid_selection_is_returned_to_the_model_and_still_cannot_expand_grants(context):
    context = collect(
        context.task,
        context.declaration.restrict(["planning.strategy"]),
        facts=context.facts,
        sources=context.sources,
        read_source=context.read_source,
    )
    provider = Provider(
        response("submit_selection", selection("action.strategy")),
        response("submit_selection", selection("planning.strategy")),
        response("submit_plan", plan("planning.strategy")),
        response("submit_artifact", {"values": {"planning.strategy": {"factory": "rules:Participant"}}}),
    )

    async def validate(candidate):
        return Validation([], [])

    result = await generate(context, provider, validate=validate)
    assert result.candidate.plan.changes[0].target == "planning.strategy"
    assert any(event["event"] == "output.rejected" for event in result.trace)


@pytest.mark.asyncio
async def test_query_budget_refuses_more_reads_without_discarding_the_generation(context):
    from dataclasses import replace

    def unexpected_read(**kwargs):
        pytest.fail("the exhausted query budget must not execute the reader")

    context = replace(context, read_source=unexpected_read)
    provider = Provider(
        response("read_source", {"name": "not-registered"}),
        response("read_source", {"name": "loop"}),
        response("submit_selection", selection("action.strategy")),
        response("submit_plan", plan("action.strategy")),
        response("submit_artifact", {"values": {"action.strategy": {"factory": "rules:policy_0_2"}}}),
    )

    async def validate(candidate):
        return Validation([], [])

    result = await generate(context, provider, validate=validate, limits=Limits(max_queries=1))
    reads = [row for row in result.trace if row["event"] == "query"]
    assert len(reads) == 1 and "error" in reads[0]["result"]
    refused = [row for row in result.trace if row["event"] == "query.rejected"]
    assert len(refused) == 1 and "budget exhausted" in refused[0]["result"]["error"]
    assert result.validation.passed


@pytest.mark.asyncio
async def test_cancellation_is_not_converted_into_model_repair(context):
    class Cancelled:
        async def chat_with_retry(self, **kwargs):
            raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await generate(context, Cancelled(), validate=None)


@pytest.mark.asyncio
async def test_mixed_read_and_submission_is_rejected_as_an_ambiguous_handoff(context):
    provider = Provider(
        LLMResponse(
            content=None,
            tool_calls=[
                ToolCallRequest("q", "read_fact", {"name": "configuration"}),
                ToolCallRequest("p", "submit_selection", selection()),
            ],
        ),
        response("submit_selection", selection()),
    )
    result = await generate(context, provider, validate=AsyncMock(return_value=Validation([], [])))
    assert not result.candidate.plan.changes
    assert any(event["event"] == "output.rejected" for event in result.trace)


@pytest.mark.asyncio
async def test_missing_native_capability_is_reported_without_a_fake_success(context):
    provider = Provider(
        response("report_gap", {"reason": "The required host binding is unavailable.", "kind": "private"})
    )
    with pytest.raises(GenerationError, match="binding is unavailable") as caught:
        await generate(context, provider, validate=None)
    assert caught.value.trace[-1]["event"] == "report_gap"


@pytest.mark.asyncio
async def test_stage_requests_keep_shared_consumers_readings_and_actual_actions(context):
    import re
    from dataclasses import replace

    authored = {
        "values": {"planning.strategy": {"factory": "shared:Guide"}, "action.strategy": {"factory": "shared:Review"}},
        "files": {"shared.py": "class Guide: pass\nclass Review: pass\n"},
    }
    context = replace(context, facts={**context.facts, "authored": authored})
    provider = Provider(
        response("read_source", {"name": "loop"}),
        response("submit_selection", selection("planning.strategy")),
        response("submit_plan", plan("planning.strategy")),
        response("submit_artifact", {"values": {"planning.strategy": {"factory": "shared:Guide"}}}),
        response("submit_artifact", {"values": {"planning.strategy": {"factory": "shared:Guide"}}}),
    )
    calls = 0

    async def validate(candidate):
        nonlocal calls
        calls += 1
        return Validation(["A shared consumer is incompatible"] if calls == 1 else [], [])

    await generate(context, provider, validate=validate)
    for request in provider.requests:
        data = packet(request)
        assert data["current_authored"] == authored
        text = instructions(request)
        actions = text.split("# Available actions\n\n", 1)[1]
        names = re.findall(r"^- `([^`]+)`:", actions, re.M)
        assert set(names) <= {entry["function"]["name"] for entry in request["tools"]}
        assert request["tools"] == provider.requests[0]["tools"]
        assert request["messages"][:2] == provider.requests[0]["messages"][:2]
        assert "shared.py" not in text
    planning_text = instructions(provider.requests[0])
    implementation_text = instructions(provider.requests[3])
    repair_text = instructions(provider.requests[4])
    assert "# Select the necessary authoring entries" in planning_text
    assert "# Implement the selected plan" not in planning_text
    assert "# Repair from host validation" not in implementation_text
    assert "# Implement the selected plan" in repair_text and "# Repair from host validation" in repair_text
    for request in provider.requests[2:]:
        data = packet(request)
        read = next(row for row in data["history"] if row["event"] == "query")
        assert read["result"] == {"indexed": True, "chars": len("native protocol"), "reread": REREAD}
        if "consistency_review" in data:
            assert {item["target"] for item in data["consistency_review"]["contracts"]} == {
                target.name for target in context.declaration.targets
            }
        else:
            assert [item["target"] for item in data["selected_contracts"]] == ["planning.strategy"]
    assert packet(provider.requests[4])["validation_errors"]


def test_orientation_is_complete_and_uses_the_inspected_source_version(context, tmp_path):
    from dataclasses import replace

    from experimental.harness.curator.generation.stages.shared import materials
    from experimental.harness.raven_adapter.inspection import Inspection, file_source

    text = "Host mechanism background.\n" * 1500 + "FINAL_REQUIRED_CONDITION"
    path = tmp_path / "index.md"
    path.write_text(text)
    inspection = Inspection(context.declaration, {}, {"reference.index": file_source(path)})
    context = replace(context, sources=inspection.sources, read_source=inspection.read_source)
    data = materials(context)
    assert data["orientation"]["text"] == text
    assert data["orientation"]["digest"] == inspection.sources["reference.index"]["digest"]
    path.write_text("Changed after inspection")
    with pytest.raises(ValueError, match="source changed"):
        materials(context)


def test_dynamic_control_uses_host_inputs_and_keeps_task_materials_in_the_data_message():
    import json

    from experimental.harness.curator.generation.context.render import messages, tool

    material = {
        "task": "USER_TASK_MARKER ${actions}",
        "feedback": "FEEDBACK_MARKER",
        "selected_contracts": [{"knowledge": [{"content": "REFERENCE_MARKER"}]}],
    }
    action = tool("host_delivery", "Deliver through ${literal_host_text}.", {"type": "object"})
    stage = {"selected_contracts": material.pop("selected_contracts")}
    result = messages(("implement", "repair"), material, stage, tools=[action], available={"host_delivery"})
    assert [message["role"] for message in result] == ["system", "user", "user", "user"]
    assert "implement → repair" in result[2]["content"]
    assert "Deliver through ${literal_host_text}." in result[2]["content"]
    for marker in ("USER_TASK_MARKER", "FEEDBACK_MARKER", "REFERENCE_MARKER"):
        assert marker not in result[0]["content"] and marker not in result[2]["content"]
    assert json.loads(result[1]["content"]) == material and json.loads(result[3]["content"]) == stage


def test_artifact_wire_normalization_preserves_file_text_and_authority(context):
    import json

    from experimental.harness.curator.generation.stages.implement import parse

    selected = designed(context, "action.strategy")
    file_text = '{"keep": "this is file content, not a container to decode"}'
    candidate = parse(
        context.declaration,
        selected,
        {
            "values": json.dumps({"action.strategy": {"factory": "rules:policy_0_2"}}),
            "files": json.dumps({"data.json": file_text, "rules.py": "def policy_0_2(): pass"}),
        },
    )
    assert candidate.artifact.values == {"action.strategy": {"factory": "rules:policy_0_2"}}
    assert candidate.artifact.files["data.json"] == file_text
    with pytest.raises(ValueError):
        parse(context.declaration, selected, {"values": json.dumps({"capability.strategy": []})})
    with pytest.raises(ValueError):
        parse(context.declaration, selected, {"values": "not JSON"})
    with pytest.raises(ValueError):
        parse(context.declaration, selected, {"values": "[]"})


def test_design_sends_knowledge_shared_by_several_selected_contracts_once(context):
    from experimental.harness.curator.generation.stages.design import materials

    chosen = context.declaration.parse_selection(
        selection("action.strategy", "capability.strategy"), ATTRIBUTED.attribution
    )
    data = materials(context, chosen)
    shared = [item["source"] for item in data["shared_knowledge"]]
    assert shared and len(shared) == len(set(shared))
    for contract in data["selected_contracts"]:
        assert contract["shared_knowledge"] and set(contract["shared_knowledge"]) <= set(shared)
        assert not {item["source"] for item in contract["knowledge"]} & set(shared)
    own = [item["source"] for contract in data["selected_contracts"] for item in contract["knowledge"]]
    assert len(own) == len(set(own))
    shared_references = [item["source"] for item in data["shared_references"]]
    assert shared_references and len(shared_references) == len(set(shared_references))
    for contract in data["selected_contracts"]:
        assert not {item["source"] for item in contract["references"]} & set(shared_references)
        assert all(item["name"] and item["purpose"] for item in contract["references"])
    assert all(item["name"] and item["purpose"] for item in data["shared_references"])
    inlined = {item["source"] for contract in data["selected_contracts"] for item in contract["knowledge"]}
    inlined |= {item["source"] for item in data["shared_knowledge"]}
    listed = {item["source"] for contract in data["selected_contracts"] for item in contract["references"]}
    listed |= {item["source"] for item in data["shared_references"]}
    assert inlined.isdisjoint(listed) and any(source.endswith("state:Task") for source in inlined)
    alone = materials(
        context, context.declaration.parse_selection(selection("action.strategy"), ATTRIBUTED.attribution)
    )
    assert alone["shared_knowledge"] == [] and alone["shared_references"] == []
    assert alone["selected_contracts"][0]["knowledge"] and alone["selected_contracts"][0]["references"]


def test_a_handed_over_expert_description_travels_as_a_material_of_every_stage(context, tmp_path):
    from dataclasses import replace

    from experimental.harness.curator.generation.stages.shared import materials

    page = tmp_path / "expert.md"
    page.write_text("# Expert\n\nWhat the expert does.\n")
    source = {"path": str(page), "start": 1, "end": 3, "digest": "d"}

    def read_source(name, offset=0, length=12000, find=None):
        text = page.read_text()
        return {"source": name, "text": text[offset : offset + length], "next_offset": None}

    handed = replace(
        context,
        sources={**context.sources, "upload.information/expert.md": source},
        read_source=read_source,
        feedback={"text": "build", "information": {"file": "uploads/information/expert.md", "version": "sha256:v"}},
    )
    information = materials(handed)["information"]
    assert information["text"] == page.read_text() and information["version"] == "sha256:v"
    assert information["source"] == "upload.information/expert.md" and information["digest"] == "d"
    assert materials(context)["information"] is None
    assert materials(replace(handed, feedback={"information": {"file": "elsewhere/expert.md"}}))["information"] is None


def test_implementation_sees_only_the_selected_contracts_while_selection_lists_every_target(context):
    from experimental.harness.curator.generation.stages.implement import materials

    selected = designed(context, "action.strategy")
    from experimental.harness.curator.generation.stages.select import materials as catalogue_of

    data = materials(
        context, context.declaration.parse_selection(selection("action.strategy"), ATTRIBUTED.attribution), selected
    )
    assert [row["target"] for row in data["selected_contracts"]] == ["action.strategy"]
    assert data["selected_contracts"][0]["knowledge"] and data["plan"]["changes"][0]["target"] == "action.strategy"
    assert "available_targets" not in data
    available = catalogue_of(context.declaration)
    assert "capability.strategy" in {row["target"] for row in available}
    assert all("knowledge" not in row for row in available)


@pytest.mark.asyncio
async def test_three_stages_preserve_diagnosis_queries_failures_and_concrete_design(context):

    chosen = selection("action.strategy")
    chosen["understanding"] = "Sampling is unstable; retain task state. Check the temperature reader."
    designed = plan("action.strategy")
    designed["design"] = "Set temperature to 0.2 through native defaults; preserve every other setting."
    note = "The first lookup failed; the registered loop source supplies the needed reader."
    provider = Provider(
        response("read_source", {"name": "missing"}),
        response("submit_selection", chosen),
        LLMResponse(content=note, tool_calls=[ToolCallRequest("read", "read_source", {"name": "loop"})]),
        response("submit_plan", designed),
        response("submit_artifact", {"values": {"action.strategy": {"factory": "rules:policy_0_2"}}}),
    )

    async def validate(candidate):
        assert candidate.plan.design == designed["design"]
        return Validation([], [])

    result = await generate(context, provider, validate=validate)
    assert [row["stage"] for row in result.trace if row["event"] == "model.call"] == [
        "select",
        "select",
        "design",
        "design",
        "implement",
        "consistency_review",
    ]
    initial, design_request, implementation = (provider.requests[i] for i in (0, 2, 4))
    assert initial["tools"] == design_request["tools"] == implementation["tools"]
    initial_actions, design_actions = instructions(initial), instructions(design_request)
    assert "`submit_selection`" in initial_actions and "`submit_plan`" not in initial_actions
    assert "`submit_plan`" in design_actions and "`submit_artifact`" not in design_actions
    initial_data = packet(initial)
    assert all("knowledge" not in target for target in initial_data["available_targets"])
    for request in (design_request, implementation):
        data = packet(request)
        assert data["task"] == context.task and data["feedback"] == context.feedback
        assert data["selection"] == chosen
        assert "error" in data["history"][0]["result"]
        assert data["history"][1]["output"] == chosen
    data = packet(implementation)
    assert data["plan"]["design"] == designed["design"]
    assert any(row.get("content") == note for row in data["history"])
    assert any(row.get("result", {}).get("indexed") for row in data["history"])
    assert not any(row.get("result", {}).get("text") == "native protocol" for row in data["history"])


@pytest.mark.asyncio
async def test_design_cannot_change_targets_or_skip_the_concrete_mechanism(context):
    missing_design = plan("action.strategy")
    missing_design.pop("design")
    provider = Provider(
        response("submit_selection", selection("action.strategy")),
        response("submit_plan", plan("memory.strategy")),
        response("submit_plan", missing_design),
        response("submit_plan", plan("action.strategy")),
        response("submit_artifact", {"values": {"action.strategy": {"factory": "rules:policy_0_2"}}}),
    )

    async def validate(candidate):
        return Validation([], [])

    result = await generate(context, provider, validate=validate)
    errors = [row["error"] for row in result.trace if row["event"] == "output.rejected"]
    assert len(errors) == 2
    assert "exactly the current selection" in errors[0]
    assert "concrete design" in errors[1]


@pytest.mark.asyncio
async def test_design_can_reselect_dependencies_but_must_design_the_new_selection(context):

    provider = Provider(
        response("submit_selection", selection("action.strategy")),
        response("revise_selection", selection("action.strategy", "capability.strategy")),
        response("submit_plan", plan("action.strategy")),
        response("submit_plan", plan("action.strategy", "capability.strategy")),
        response(
            "submit_artifact",
            {
                "values": {
                    "action.strategy": {"factory": "rules:create"},
                    "capability.strategy": {"factory": "rules:capability"},
                }
            },
        ),
    )

    async def validate(candidate):
        return Validation([], [])

    result = await generate(context, provider, validate=validate)
    data = packet(provider.requests[2])
    assert {row["target"] for row in data["selected_contracts"]} == {"action.strategy", "capability.strategy"}
    assert "plan" not in data and "candidate" not in data
    assert len(result.candidate.plan.changes) == 2
    assert any(row["event"] == "output.rejected" for row in result.trace)


@pytest.mark.asyncio
async def test_redesign_retains_failed_candidate_evidence_but_clears_active_draft(context, tmp_path):

    from experimental.harness.raven_adapter.exploration import Exploration
    from experimental.harness.raven_adapter.inspection import Inspection
    from raven.config.schema import Config

    previous = plan("action.strategy")
    previous["design"] = "OLD_DESIGN"
    revised = {**previous, "design": "NEW_DESIGN addresses the observed failure"}
    old = {"values": {"action.strategy": {"factory": "rules:policy_0_4"}}, "files": {"old.py": "OLD_DRAFT = True\n"}}
    fixed = {"values": {"action.strategy": {"factory": "rules:policy_0_2"}}}
    probe_evidence = {"kind": "probe.failed", "details": "OLD_EVIDENCE"}
    provider = Provider(
        response("submit_selection", selection("action.strategy")),
        response("submit_plan", previous),
        response("check_candidate", old),
        response("submit_artifact", old),
        response("revise_plan", {"reason": "The design did not account for the observed condition."}),
        response("submit_plan", revised),
        response("submit_artifact", fixed),
    )
    checks = 0

    async def validate(candidate):
        nonlocal checks
        checks += 1
        return Validation(["OLD_FAILURE"], [probe_evidence]) if checks <= 2 else Validation([], [])

    inspection = Inspection(context.declaration, {}, {})
    async with Exploration(Config(), inspection, repository=tmp_path, source_paths=()) as exploration:

        def stage(candidate):
            result = exploration.stage_candidate(candidate)
            if candidate is None:
                assert not (exploration.root / "candidate").exists()
            return result

        result = await generate(context, provider, validate=validate, stage_candidate=stage)
        assert result.candidate.plan.design == revised["design"]
        assert not list((exploration.root / "candidate").rglob("old.py"))
    data = packet(provider.requests[5])
    assert "plan" not in data and "candidate" not in data
    history = data["history"]
    assert any(
        row["event"] == "submit_artifact" and row["output"]["artifact"] == {**old, "remove": [], "remove_files": []}
        for row in history
    )
    from experimental.harness.curator.generation.context import query

    evidence = next(row for row in history if row["event"] == "validation")
    recovered = query.execute(
        context, "read_observation", {"trace_index": evidence["trace_index"], "index": 0}, trace=result.trace
    )
    assert json.loads(recovered["text"]) == probe_evidence
    assert any(row["event"] == "preflight" and row["arguments"] == old for row in history)
    assert history[-1]["event"] == "revise_plan"
    assert result.validation.passed and checks == 3


@pytest.mark.asyncio
async def test_reselection_remains_inside_grants_and_backtracking_uses_total_budget(context):
    from dataclasses import replace

    restricted = replace(context, declaration=context.declaration.restrict(["action.strategy"]))
    provider = Provider(
        response("submit_selection", selection("action.strategy")),
        response("revise_selection", selection("memory.strategy")),
        response("revise_selection", selection("action.strategy")),
    )
    with pytest.raises(GenerationError, match="call budget") as caught:
        await generate(restricted, provider, validate=None, limits=Limits(max_calls=3))
    assert any(row["event"] == "output.rejected" and "not granted" in row["error"] for row in caught.value.trace)
    assert [row["stage"] for row in caught.value.trace if row["event"] == "model.call"] == [
        "select",
        "design",
        "design",
    ]


@pytest.mark.asyncio
async def test_remaining_budget_tracks_queries_checks_and_repairs_across_stages(context):
    class BudgetProvider(Provider):
        def __init__(self, *responses):
            super().__init__(*responses)
            self.budgets = []
            self.sent = []

        async def chat_with_retry(self, **kwargs):
            sent = kwargs["messages"]
            assert "# Remaining generation budget" not in sent[0]["content"]
            notes = sum("# Remaining generation budget" in str(row.get("content")) for row in sent)
            assert notes == 1 + sum(1 for earlier in self.sent if earlier[2] == sent[2])
            assert sent[-1]["role"] == "user" and sent[-1]["content"].startswith("# Remaining generation budget")
            self.budgets.append(sent[-1]["content"].split("# Remaining generation budget", 1)[1])
            self.sent.append(sent)
            return await super().chat_with_retry(**kwargs)

    artifact = {"values": {"action.strategy": {"factory": "rules:policy_0_2"}}}
    provider = BudgetProvider(
        response("submit_selection", selection("action.strategy")),
        response("read_source", {"name": "loop"}),
        response("submit_plan", plan("action.strategy")),
        response("check_candidate", artifact),
        response("submit_artifact", artifact),
        response("submit_artifact", artifact),
    )
    checks = 0

    async def validate(candidate):
        nonlocal checks
        checks += 1
        return Validation(["repair this candidate"] if checks == 2 else [], [])

    await generate(
        context, provider, validate=validate, limits=Limits(max_calls=8, max_queries=4, max_checks=2, max_repairs=2)
    )
    for earlier, later in zip(provider.sent, provider.sent[1:]):
        assert later[:2] == earlier[:2]
        if earlier[2] == later[2]:
            assert later[: len(earlier)] == earlier
    for index, budget in enumerate(provider.budgets):
        assert f"including this response: {8 - index}" in budget
        assert f"Exploration tool calls: {4 if index < 2 else 3}" in budget
        assert f"Draft preflight checks: {2 if index < 4 else 1}" in budget
        assert f"failed final validation: {2 if index < 5 else 1}" in budget


@pytest.mark.asyncio
async def test_a_stage_that_spends_its_allowance_is_told_to_submit_and_the_next_stage_starts_afresh(context):
    class BudgetProvider(Provider):
        def __init__(self, *responses):
            super().__init__(*responses)
            self.budgets = []

        async def chat_with_retry(self, **kwargs):
            self.budgets.append(kwargs["messages"][-1]["content"])
            return await super().chat_with_retry(**kwargs)

    artifact = {"values": {"action.strategy": {"factory": "rules:policy_0_2"}}}
    provider = BudgetProvider(
        response("read_source", {"name": "loop"}),
        response("read_source", {"name": "loop"}),
        response("read_source", {"name": "loop"}),
        response("submit_selection", selection("action.strategy")),
        response("read_source", {"name": "loop"}),
        response("submit_plan", plan("action.strategy")),
        response("submit_artifact", artifact),
    )

    async def validate(candidate):
        return Validation([], [])

    result = await generate(
        context, provider, validate=validate, limits=Limits(max_calls=10, max_queries=6, stage_queries=2)
    )
    refused = [row for row in result.trace if row["event"] == "query.rejected"]
    assert len(refused) == 1 and "stage's exploration allowance of 2" in refused[0]["result"]["error"]
    assert [row["stage"] for row in result.trace if row["event"] == "query"] == ["select", "select", "design"]
    assert "left in this stage: 2 of 2" in provider.budgets[0] and "More than half" not in provider.budgets[0]
    assert "left in this stage: 1 of 2" in provider.budgets[1] and "More than half" in provider.budgets[1]
    assert "left in this stage: 0 of 2" in provider.budgets[2]
    assert "left in this stage: 2 of 2" in provider.budgets[4] and "Exploration tool calls: 4" in provider.budgets[4]


@pytest.mark.asyncio
async def test_the_stage_line_never_promises_more_queries_than_the_pool_holds(context):
    class BudgetProvider(Provider):
        def __init__(self, *responses):
            super().__init__(*responses)
            self.budgets = []

        async def chat_with_retry(self, **kwargs):
            self.budgets.append(kwargs["messages"][-1]["content"])
            return await super().chat_with_retry(**kwargs)

    provider = BudgetProvider(
        response("read_source", {"name": "loop"}),
        response("read_source", {"name": "loop"}),
        response("submit_selection", selection("action.strategy")),
        response("submit_plan", plan("action.strategy")),
        response("submit_artifact", {"values": {"action.strategy": {"factory": "rules:policy_0_2"}}}),
    )

    async def validate(candidate):
        return Validation([], [])

    await generate(context, provider, validate=validate, limits=Limits(max_calls=8, max_queries=3, stage_queries=5))
    assert "left in this stage: 3 of 5" in provider.budgets[0]
    assert "left in this stage: 1 of 5" in provider.budgets[2]
    assert "left in this stage: 1 of 5" in provider.budgets[3] and "Exploration tool calls: 1" in provider.budgets[3]


def test_an_unset_stage_allowance_leaves_the_pool_as_the_only_cap():
    assert Limits(max_queries=5).stage_allowance == 5 and Limits(max_queries=5, stage_queries=2).stage_allowance == 2
    with pytest.raises(ValueError):
        Limits(stage_queries=-1)


def test_history_indexes_repeatable_reads_and_keeps_everything_else():
    from experimental.harness.curator.generation.context.render import history

    trace = [
        {"stage": "diagnose", "event": "model.call", "call": 1},
        {
            "stage": "diagnose",
            "event": "query",
            "tool": "read_source",
            "arguments": {"name": "loop"},
            "result": {"text": "abc"},
        },
        {
            "stage": "diagnose",
            "event": "query",
            "tool": "grep",
            "arguments": {"pattern": "x"},
            "result": {"text": "m", "failed": False},
        },
        {
            "stage": "diagnose",
            "event": "query",
            "tool": "read_file",
            "arguments": {"path": "p"},
            "result": {"text": "missing", "failed": True},
        },
        {
            "stage": "diagnose",
            "event": "query",
            "tool": "read_source",
            "arguments": {"name": "zz"},
            "result": {"error": "unknown source"},
        },
        {
            "stage": "diagnose",
            "event": "query",
            "tool": "exec",
            "arguments": {"command": "ls"},
            "result": {"text": "a.py", "failed": False},
        },
        {
            "stage": "diagnose",
            "event": "query",
            "tool": "read_source",
            "arguments": {"name": "f"},
            "result": {"source": "f", "matches": [{"text": "hit"}]},
        },
        {"stage": "validate", "event": "validation", "errors": ["e"], "observations": []},
        {"stage": "implement", "event": "preflight", "arguments": {"values": {}}, "result": {"passed": False}},
        {"stage": "select", "event": "submit_selection", "output": {"targets": []}},
    ]
    rows = history(trace)
    assert [row["event"] for row in rows] == [e["event"] for e in trace if e["event"] != "model.call"]
    assert rows[0]["result"] == {"indexed": True, "chars": 3, "reread": REREAD} and rows[0]["arguments"] == {
        "name": "loop"
    }
    assert rows[1]["result"]["indexed"] and rows[1]["result"]["chars"] == 1
    assert rows[2]["result"] == {"text": "missing", "failed": True}
    assert rows[3]["result"] == {"error": "unknown source"}
    assert rows[4]["result"] == {"text": "a.py", "failed": False}
    assert rows[5]["result"]["indexed"] and rows[5]["result"]["chars"] > 0
    assert rows[6] == {**trace[7], "trace_index": 7}
    assert rows[7:] == trace[8:]


@pytest.mark.asyncio
@pytest.mark.parametrize("stage_index", [0, 1, 2])
async def test_invalid_arguments_preserve_stage_and_context_before_resubmission(context, stage_index):
    outputs = [
        response("submit_selection", selection("action.strategy")),
        response("submit_plan", plan("action.strategy")),
        response("submit_artifact", {"values": {"action.strategy": {"factory": "rules:policy_0_2"}}}),
    ]
    raw = '{"description": "Use verdict="resample" here"}'
    name = outputs[stage_index].tool_calls[0].name
    invalid = LLMResponse(
        content=None,
        tool_calls=[
            ToolCallRequest("invalid", name, {RAW_ARGUMENTS_KEY: raw}, run_meta=RunMeta(arguments_repaired=True))
        ],
    )
    outputs.insert(stage_index, invalid)
    provider = Provider(*outputs)
    checked = []

    async def validate(candidate):
        checked.append(candidate)
        return Validation([], [])

    result = await generate(context, provider, validate=validate, limits=Limits(max_calls=5))
    assert len(checked) == 1 and result.candidate is checked[0]
    events = [event for event in result.trace if event["event"] == "output.rejected"]
    assert len(events) == 1
    assert events[0]["stage"] == ("select", "design", "implement")[stage_index]
    assert events[0]["calls"][0]["function"]["arguments"] == raw
    messages = provider.requests[stage_index + 1]["messages"]
    assistant = next(m for m in messages if m.get("tool_calls", [{}])[0].get("id") == "invalid")
    assert assistant["tool_calls"][0]["function"]["arguments"] == raw
    feedback = next(m for m in messages if m.get("tool_call_id") == "invalid")
    assert "Parser:" in feedback["content"] and "No tools" in feedback["content"]
    assert context.task in messages[1]["content"]
    assert len(provider.requests) == 5


def test_provider_reasoning_and_tool_metadata_survive_native_message_building():
    from experimental.harness.curator.generation.context.render import assistant_message

    response = LLMResponse(
        content=None,
        tool_calls=[ToolCallRequest("id", "query", {}, provider_specific_fields={"tag": "opaque"})],
        reasoning_content="synthetic reasoning",
        thinking_blocks=[{"type": "thinking", "signature": "opaque"}],
    )
    message = assistant_message(response)
    assert message["reasoning_content"] == "synthetic reasoning"
    assert message["thinking_blocks"] == response.thinking_blocks
    assert message["tool_calls"][0]["provider_specific_fields"] == {"tag": "opaque"}


def test_a_degenerate_reply_text_goes_back_into_the_conversation_capped():
    from experimental.harness.curator.generation.context.render import ECHOED_CHARS, assistant_message

    markup = "<invoke name=submit>" * 50_000
    message = assistant_message(LLMResponse(content=markup, tool_calls=[ToolCallRequest("id", "query", {})]))
    assert message["content"].startswith(markup[:ECHOED_CHARS]) and len(message["content"]) < ECHOED_CHARS + 100
    assert message["tool_calls"][0]["function"]["name"] == "query"
    assert assistant_message(LLMResponse(content="short", tool_calls=[]))["content"] == "short"


@pytest.mark.asyncio
async def test_invalid_call_blocks_entire_tool_batch_without_spending_query_budget(context):
    from unittest.mock import AsyncMock, Mock

    registry = Mock()
    registry.get_definitions.return_value = []
    registry.execute = AsyncMock()
    provider = Provider(
        LLMResponse(
            content=None,
            tool_calls=[
                ToolCallRequest("valid", "native_probe", {"path": "."}),
                ToolCallRequest(
                    "invalid", "native_probe", {RAW_ARGUMENTS_KEY: "[1]"}, run_meta=RunMeta(arguments_repaired=True)
                ),
            ],
        ),
        response("read_source", {"name": "loop"}),
        response("submit_selection", selection()),
    )

    async def validate(candidate):
        assert not candidate.artifact.values
        return Validation([], [])

    registry.get.return_value = None
    result = await generate(context, provider, validate=validate, tool_registry=registry, limits=Limits(max_queries=1))
    registry.execute.assert_not_awaited()
    assert len([event for event in result.trace if event["event"] == "query"]) == 1
    feedback = [m for m in provider.requests[1]["messages"] if m.get("tool_call_id") in ("valid", "invalid")]
    assert len(feedback) == 2 and all("No tools" in m["content"] for m in feedback)
    assert not any(event["event"] == "query.rejected" for event in result.trace)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["raw", "repaired", "truncated"])
async def test_repeated_invalid_submissions_stop_at_call_budget(context, kind):
    invalid = response("submit_selection", selection())
    if kind == "raw":
        invalid.tool_calls[0].arguments = {RAW_ARGUMENTS_KEY: "{"}
    elif kind == "repaired":
        invalid.tool_calls[0].run_meta = RunMeta(arguments_repaired=True)
    else:
        invalid.truncated = True
    provider = Provider(invalid, invalid, invalid)

    async def validate(candidate):
        pytest.fail("Invalid submission must not reach validation")

    with pytest.raises(GenerationError, match="call budget exhausted") as failure:
        await generate(context, provider, validate=validate, limits=Limits(max_calls=2))
    assert len(provider.requests) == 3, "a submission refused on the last call gets one call to be corrected"
    assert len([event for event in failure.value.trace if event["event"] == "output.rejected"]) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [TimeoutError("transport timeout"), RuntimeError("provider implementation bug")])
async def test_provider_failures_do_not_become_model_output_repairs(context, error):
    from unittest.mock import AsyncMock

    provider = Provider()
    provider.chat_with_retry = AsyncMock(side_effect=error)
    with pytest.raises(GenerationError, match="model call failed") as failure:
        await generate(context, provider, validate=AsyncMock())
    assert failure.value.__cause__ is error
    assert provider.chat_with_retry.await_count == 1
    assert not any(event["event"] == "output.rejected" for event in failure.value.trace)


@pytest.mark.asyncio
async def test_a_failure_that_is_not_resumable_ends_the_generation_instead_of_pausing_it(context):
    from unittest.mock import AsyncMock

    # A stand-in for the loop's boundary error: this file stays free of evaluation-side imports, which would
    # withhold it from the Curator's exploration snapshot.
    class SealedError(RuntimeError):
        resumable = False

    provider = Provider()
    violation = SealedError("curator compartment: sealed information in chat_with_retry")
    provider.chat_with_retry = AsyncMock(side_effect=violation)
    with pytest.raises(SealedError) as failure:
        await generate(context, provider, validate=AsyncMock())
    assert failure.value is violation and provider.chat_with_retry.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("pause_after", [1, 2, 3, 4, 5, 6])
async def test_serialized_resume_preserves_every_stage_and_does_not_replay_work(context, pause_after):
    from experimental.harness.curator.generation.run import GenerationPausedError
    from experimental.harness.curator.generation.state import GenerationState

    draft = {"values": {"action.strategy": {"factory": "rules:policy_0_2"}}}
    provider = Provider(
        response("read_source", {"name": "loop"}),
        response("submit_selection", selection("action.strategy")),
        response("read_fact", {"name": "configuration"}),
        response("submit_plan", plan("action.strategy")),
        response("check_candidate", draft),
        response("submit_artifact", draft),
        response("submit_artifact", {"values": {"action.strategy": {"factory": "rules:policy_0_4"}}}),
    )
    checks = []

    async def validate(candidate):
        checks.append(candidate)
        return Validation(["Adjust temperature"] if len(checks) == 2 else [], [])

    with pytest.raises(GenerationPausedError) as paused:
        await generate(context, provider, validate=validate, limits=Limits(max_calls=pause_after))
    state = GenerationState.model_validate_json(paused.value.state.model_dump_json())
    assert state.calls == pause_after
    assert (
        state.stage == {1: "select", 2: "design", 3: "design", 4: "implement", 5: "implement", 6: "repair"}[pause_after]
    )
    if pause_after == 5:
        assert state.checks == 1
    if pause_after == 6:
        assert state.repairs == 1 and state.validation.errors == ["Adjust temperature"]
    saved_messages = state.model_copy(deep=True).messages
    resumed = Provider(*provider.responses)
    result = await generate(context, resumed, validate=validate, limits=Limits(max_calls=8), resume=state)
    assert result.candidate.artifact.values["action.strategy"] == {"factory": "rules:policy_0_4"}
    assert len(checks) == 3
    assert len(provider.requests) + len(resumed.requests) == 8
    assert state.calls == pause_after and state.messages == saved_messages
    sent = resumed.requests[0]["messages"]
    assert sent[:-1] == saved_messages and "# Remaining generation budget" in sent[-1]["content"]
    assert len([event for event in result.trace if event["event"] == "query"]) == 2
    assert [event["call"] for event in result.trace if event["event"] == "model.call"] == list(range(1, 9))


@pytest.mark.asyncio
async def test_resumption_does_not_implicitly_refill_any_budget(context):
    from experimental.harness.curator.generation.run import GenerationPausedError

    provider = Provider(response("read_source", {"name": "loop"}))
    with pytest.raises(GenerationPausedError) as paused:
        await generate(context, provider, validate=None, limits=Limits(max_calls=1, max_queries=1))
    state = paused.value.state
    with pytest.raises(GenerationPausedError):
        await generate(context, Provider(), validate=None, limits=Limits(max_calls=1, max_queries=1), resume=state)
    resumed = Provider(response("read_source", {"name": "loop"}), response("submit_selection", selection()))
    result = await generate(
        context,
        resumed,
        validate=AsyncMock(return_value=Validation([], [])),
        limits=Limits(max_calls=4, max_queries=1),
        resume=state,
    )
    assert len([event for event in result.trace if event["event"] == "query"]) == 1
    assert len([event for event in result.trace if event["event"] == "query.rejected"]) == 1
    with pytest.raises(ValueError, match="consumed budgets"):
        await generate(context, Provider(), validate=None, limits=Limits(max_calls=2, max_queries=0), resume=state)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["task", "feedback", "facts", "sources", "declaration"])
async def test_resume_refuses_changed_inputs_before_any_model_call(context, change):
    from dataclasses import replace

    from experimental.harness.curator.generation.run import GenerationPausedError

    provider = Provider(response("read_source", {"name": "loop"}))
    with pytest.raises(GenerationPausedError) as paused:
        await generate(context, provider, validate=None, limits=Limits(max_calls=1))
    value = {
        "task": "Another task",
        "feedback": "New feedback",
        "facts": {"changed": True},
        "sources": {"new": {"start": 1, "end": 2}},
        "declaration": context.declaration.restrict(["action.strategy"]),
    }[change]
    resumed = Provider()
    with pytest.raises(ValueError, match="inputs changed"):
        await generate(replace(context, **{change: value}), resumed, validate=None, resume=paused.value.state)
    assert not resumed.requests


@pytest.mark.asyncio
@pytest.mark.parametrize("revision", ["revise_plan", "revise_selection"])
async def test_pause_after_backtracking_resumes_design_without_a_stale_plan(context, revision):
    from experimental.harness.curator.generation.run import GenerationPausedError

    target = "memory.strategy" if revision == "revise_selection" else "action.strategy"
    arguments = selection(target) if revision == "revise_selection" else {"reason": "Reconsider the mechanism"}
    provider = Provider(
        response("submit_selection", selection("action.strategy")),
        response("submit_plan", plan("action.strategy")),
        response(revision, arguments),
    )
    staged = []
    with pytest.raises(GenerationPausedError) as paused:
        await generate(context, provider, validate=None, stage_candidate=staged.append, limits=Limits(max_calls=3))
    state = paused.value.state
    assert state.stage == "design" and state.plan is None and state.candidate is None
    assert state.selection.targets == (target,) and staged == [None]
    values = (
        {"memory.strategy": {"factory": "rules:create"}}
        if target == "memory.strategy"
        else {"action.strategy": {"factory": "rules:policy_0_2"}}
    )
    resumed = Provider(response("submit_plan", plan(target)), response("submit_artifact", {"values": values}))

    async def validate(candidate):
        return Validation([], [])

    result = await generate(context, resumed, validate=validate, limits=Limits(max_calls=6), resume=state)
    assert result.candidate.artifact.values == values


@pytest.mark.asyncio
async def test_staged_files_join_the_artifact_and_the_artifacts_own_files_win(context):
    provider = Provider(
        response("submit_selection", selection("action.strategy")),
        response("submit_plan", plan("action.strategy")),
        response("stage_file", {"path": "rules.py", "content": "def create(state, task):\n    return None\n"}),
        response("stage_file", {"path": "notes.md", "content": "draft"}),
        response("stage_file", {"path": "../escape.py", "content": "x"}),
        response(
            "submit_artifact",
            {"values": {"action.strategy": {"factory": "rules:create"}}, "files": {"notes.md": "final"}},
        ),
    )
    checked = []

    async def validate(candidate):
        checked.append(candidate)
        return Validation([], [{"kind": "runtime.bound"}])

    result = await generate(context, provider, validate=validate)
    assert result.candidate.artifact.files == {
        "rules.py": "def create(state, task):\n    return None\n",
        "notes.md": "final",
    }
    staged = [event for event in result.trace if event["event"] == "file.staged"]
    assert [event["result"].get("staged") for event in staged] == ["rules.py", "notes.md", None]
    assert "error" in staged[2]["result"]
    assert "`stage_file`" in instructions(provider.requests[2]) and "`stage_file`" not in instructions(
        provider.requests[1]
    )
    assert provider.requests[2]["tools"] == provider.requests[1]["tools"]


@pytest.mark.asyncio
async def test_a_value_naming_a_module_no_file_provides_is_sent_back_before_validation(context):
    provider = Provider(
        response("submit_selection", selection("action.strategy")),
        response("submit_plan", plan("action.strategy")),
        response("submit_artifact", {"values": {"action.strategy": {"factory": "planning_impl:create"}}}),
        response("stage_file", {"path": "planning_impl.py", "content": "def create(state, task):\n    return None\n"}),
        response("submit_artifact", {"values": {"action.strategy": {"factory": "planning_impl:create"}}}),
    )
    checked = []

    async def validate(candidate):
        checked.append(candidate)
        return Validation([], [{"kind": "runtime.bound"}])

    result = await generate(context, provider, validate=validate)
    assert len(checked) == 1 and "planning_impl.py" in result.candidate.artifact.files
    rejected = next(event for event in result.trace if event["event"] == "output.rejected")
    assert "'planning_impl'" in rejected["error"] and "stage_file" in rejected["error"]
    assert result.validation.passed


@pytest.mark.asyncio
async def test_after_staging_a_file_another_stages_submission_is_still_refused_as_unavailable(context):
    provider = Provider(
        response("submit_selection", selection("action.strategy")),
        response("submit_plan", plan("action.strategy")),
        response("stage_file", {"path": "planning_impl.py", "content": "def create(state, task):\n    return None\n"}),
        response("submit_plan", plan("action.strategy")),
        response("submit_artifact", {"values": {"action.strategy": {"factory": "planning_impl:create"}}}),
    )

    async def validate(candidate):
        return Validation([], [])

    result = await generate(context, provider, validate=validate)
    refused = next(event for event in result.trace if event["event"] == "action.unavailable")
    assert refused["tool"] == "submit_plan" and "not available in the implement stage" in refused["result"]["error"]
    assert not any(event["event"] == "query" and event.get("tool") == "submit_plan" for event in result.trace)


def test_observations_reach_a_request_as_an_index_and_are_read_on_demand():
    import json

    from experimental.harness.curator.generation.context import query, render
    from experimental.harness.curator.generation.context.collect import Context

    huge = {"kind": "child.execution", "turn_id": "t1", "records": [{"kind": "tool", "text": "x" * 1000}] * 100}
    rows = [{"kind": "task.execution", "turn_id": "t1"}, huge]
    index = render.observation_index(rows)
    assert index[0] == {
        "index": 0,
        "bytes": len(json.dumps(rows[0]).encode()),
        "kind": "task.execution",
        "turn_id": "t1",
    }
    assert index[1]["records_kinds"] == {"tool": 100} and index[1]["bytes"] > 100_000
    assert len(json.dumps(index).encode()) < 400
    long = {"kind": "task.execution", "reply": "r" * 3000, "user": "u" * 3000}
    (entry,) = render.observation_index([long])
    assert entry["reply"] == long["reply"] and "user" not in entry
    context = Context.__new__(Context)
    object.__setattr__(context, "observations", tuple(rows))
    first = query.execute(context, "read_observation", {"index": 1, "path": ["records", 0], "length": 30})
    assert first["text"].startswith("{") and first["next_offset"] == 30 and first["total_characters"] > 1000
    with pytest.raises(ValueError, match="there are 2"):
        query.execute(context, "read_observation", {"index": 2})
    many = [{"kind": "row", "n": number, "note": "z" * 200} for number in range(20_000)]
    assert render.observation_index(many) == {
        "rows": 20_000,
        "kinds": {"row": 20_000},
        "read": "read_observation by index",
    }
    assert render.observations(rows, row_bytes=2000)[1]["cut"] > 100_000


@pytest.mark.asyncio
async def test_a_call_that_spent_its_output_thinking_is_followed_by_a_short_thinking_call(context):
    provider = Provider(
        LLMResponse(content="Still thinking.", finish_reason="length"),
        # A provider can spend the whole output on reasoning and still report `stop` with no content.
        LLMResponse(content=None, finish_reason="stop"),
        LLMResponse(content=None, finish_reason="stop"),
        response("submit_selection", selection()),
    )

    async def validate(candidate):
        return Validation([], [])

    result = await generate(context, provider, validate=validate, limits=Limits(max_calls=6, max_output=65536))
    assert result.validation.passed and len(provider.requests) == 5
    assert all(request["max_tokens"] == 65536 for request in provider.requests)
    efforts = [request.get("reasoning_effort") for request in provider.requests[:4]]
    assert efforts == [None, "low", "none", "none"]
    assert "ran out of output" in provider.requests[1]["messages"][-2]["content"]
    with pytest.raises(ValueError):
        Limits(max_output=0)


@pytest.mark.asyncio
async def test_a_curator_call_on_a_model_that_needs_breakpoints_marks_the_tail_so_the_next_call_reads_it(context):
    """Without breakpoints each call is written to the cache again and never read; with marks only on the tail, each
    new stage writes the curation's materials again. The tail mark sits on the budget note, which stays in the
    conversation, so the next call reads everything this one sent."""
    provider = Provider(
        response("submit_selection", selection("action.strategy")),
        response("submit_plan", plan("action.strategy")),
        response("submit_artifact", {"values": {"action.strategy": {"factory": "rules:policy_0_2"}}}),
    )

    async def validate(candidate):
        return Validation([], [])

    result = await generate(
        context,
        provider,
        validate=validate,
        model="openrouter/anthropic/claude-opus-5.5",
        limits=Limits(max_calls=4),
    )
    assert result.validation.passed and len(provider.requests) == 4
    for request in provider.requests:
        messages = request["messages"]
        marked = [index for index, message in enumerate(messages) if "cache_control" in json.dumps(message)]
        assert marked == [0, 1, len(messages) - 1] and messages[0].get("cache_marks_placed")
        assert messages[-1]["content"][0]["text"].startswith("# Remaining generation budget")
        assert "cache_control" in json.dumps(request["tools"][-1])
    plain = Provider(response("submit_selection", selection("action.strategy")))
    with pytest.raises(GenerationError):
        await generate(context, plain, validate=validate, model="deepseek/deepseek-flash", limits=Limits(max_calls=1))
    assert "cache_control" not in json.dumps(plain.requests[0]["messages"])


@pytest.mark.asyncio
async def test_design_records_commitment_changes_with_host_ids_and_each_stage_sees_its_part_of_the_list(context):
    silent = plan("action.strategy")
    silent.pop("commitments")
    provider = Provider(
        response("submit_selection", selection("action.strategy")),
        response("submit_plan", silent),
        response("submit_plan", plan("action.strategy")),
        response("submit_artifact", {"values": {"action.strategy": {"factory": "rules:policy_0_2"}}}),
    )

    async def validate(candidate):
        return Validation([], [])

    result = await generate(context, provider, validate=validate)
    refused = next(event for event in result.trace if event["event"] == "output.rejected")
    assert "carry no commitment change: ['action.strategy']" in refused["error"]
    (added,) = result.candidate.plan.commitments
    assert (added.id, added.surface, added.serves) == ("H1", "action.strategy", ("task",))
    choosing, designing, _, implementing, reviewing = (packet(request) for request in provider.requests)
    assert reviewing["consistency_review"]["commitments_after"] == implementing["commitments_after"]
    assert choosing["commitments"] == [] and implementing["commitments"] == []
    assert (
        choosing["commitment_coverage"]
        == designing["commitment_coverage"]
        == {
            "unserved": ["task"],
            "stale_serves": [],
        }
    )
    assert "commitment_coverage" not in implementing
    assert implementing["commitments_after"] == [
        {"id": "H1", "surface": "action.strategy", "statement": added.statement, "serves": ["task"]}
    ]


@pytest.fixture
def authored(context):
    from dataclasses import replace

    files = {"rules.py": "def create(state, task):\n    return None\n", "shared.py": "X = 1\nX = 1\n"}
    facts = {
        **context.facts,
        "authored": {"values": {"memory.strategy": {"factory": "shared:create"}}, "files": files},
    }
    return replace(context, facts=facts)


@pytest.mark.asyncio
async def test_edit_file_changes_an_installed_file_through_a_unique_excerpt(authored):
    values = {"action.strategy": {"factory": "rules:create"}}
    provider = Provider(
        response("submit_selection", selection("action.strategy")),
        response("submit_plan", plan("action.strategy")),
        response("edit_file", {"path": "rules.py", "old": "return None", "new": "return {}"}),
        response("edit_file", {"path": "shared.py", "old": "X = 1", "new": "X = 2"}),
        response("edit_file", {"path": "missing.py", "old": "x", "new": "y"}),
        response("check_candidate", {"values": values}),
        response("submit_artifact", {"values": values, "files": {"rules.py": "def create(state, task): ...\n"}}),
        response("submit_artifact", {"values": values}),
    )

    async def validate(candidate):
        return Validation([], [])

    result = await generate(authored, provider, validate=validate)
    assert result.candidate.artifact.files == {"rules.py": "def create(state, task):\n    return {}\n"}
    edits = [event["result"] for event in result.trace if event["event"] == "file.edited"]
    assert edits[0]["edited"] == "rules.py"
    assert "occurs 2 times" in edits[1]["error"] and "stage_file" in edits[2]["error"]
    (preflight,) = [event["result"] for event in result.trace if event["event"] == "preflight"]
    assert preflight["changes"] == [{"path": "rules.py", "kept": 1, "removed": 1, "added": 1}]
    refused = next(event for event in result.trace if event["event"] == "output.rejected")
    assert "changed with edit_file" in refused["error"]
    assert "`edit_file`" in instructions(provider.requests[2])


@pytest.mark.asyncio
async def test_the_change_report_names_unselected_targets_whose_module_changed(authored):
    from dataclasses import replace

    installed = authored.facts["authored"]
    facts = {
        **authored.facts,
        "authored": {
            "values": {
                "memory.strategy": {"factory": "shared:create", "prompt": "shared:PROMPT"},
                "capability.strategy": {"factory": "kit:create"},
            },
            "files": {**installed["files"], "kit/__init__.py": "Y = 1\n"},
        },
    }
    values = {"action.strategy": {"factory": "rules:create"}}
    provider = Provider(
        response("submit_selection", selection("action.strategy")),
        response("submit_plan", plan("action.strategy")),
        response("stage_file", {"path": "shared.py", "content": "X = 3\n"}),
        response("stage_file", {"path": "kit/__init__.py", "content": "Y = 2\n"}),
        response("submit_artifact", {"values": values}),
    )

    async def validate(candidate):
        return Validation([], [])

    result = await generate(replace(authored, facts=facts), provider, validate=validate)
    validation = next(event for event in result.trace if event["event"] == "validation")
    assert validation["changes"] == [
        {"path": "kit/__init__.py", "kept": 0, "removed": 1, "added": 1, "used_by_unselected": ["capability.strategy"]},
        {"path": "shared.py", "kept": 0, "removed": 2, "added": 1, "used_by_unselected": ["memory.strategy"]},
    ]


@pytest.mark.asyncio
async def test_repair_edits_the_failed_candidates_own_copy_of_a_file(context):
    values = {"action.strategy": {"factory": "helper:create"}}
    source = "def create(state, task):\n    return 1\n"
    provider = Provider(
        response("submit_selection", selection("action.strategy")),
        response("submit_plan", plan("action.strategy")),
        response("submit_artifact", {"values": values, "files": {"helper.py": source}}),
        response("edit_file", {"path": "helper.py", "old": "return 1", "new": "return 2"}),
        response("submit_artifact", {"values": values}),
    )
    checked = []

    async def validate(candidate):
        checked.append(candidate)
        return Validation(["helper returns the wrong value"] if len(checked) == 1 else [], [])

    result = await generate(context, provider, validate=validate)
    assert result.candidate.artifact.files["helper.py"] == "def create(state, task):\n    return 2\n"


@pytest.mark.asyncio
async def test_repair_starts_from_the_checked_copy_of_a_staged_file(context):
    values = {"action.strategy": {"factory": "helper:create"}}
    submitted = "def create(state, task):\n    value = 1\n    return value\n"
    provider = Provider(
        response("submit_selection", selection("action.strategy")),
        response("submit_plan", plan("action.strategy")),
        response("stage_file", {"path": "helper.py", "content": "def create(state, task):\n    return 0\n"}),
        response("submit_artifact", {"values": values, "files": {"helper.py": submitted}}),
        response("edit_file", {"path": "helper.py", "old": "value = 1", "new": "value = 2"}),
        response("edit_file", {"path": "helper.py", "old": "return value", "new": "return value + 1"}),
        response("submit_artifact", {"values": values}),
    )
    checked = []

    async def validate(candidate):
        checked.append(candidate)
        return Validation(["helper returns the wrong value"] if len(checked) == 1 else [], [])

    result = await generate(context, provider, validate=validate)
    assert result.candidate.artifact.files == {
        "helper.py": "def create(state, task):\n    value = 2\n    return value + 1\n"
    }


@pytest.mark.asyncio
async def test_a_file_edited_before_the_check_may_be_rewritten_whole_in_repair(authored):
    values = {"action.strategy": {"factory": "rules:create"}}
    rewritten = "def create(state, task):\n    return []\n"
    provider = Provider(
        response("submit_selection", selection("action.strategy")),
        response("submit_plan", plan("action.strategy")),
        response("edit_file", {"path": "rules.py", "old": "return None", "new": "return {}"}),
        response("submit_artifact", {"values": values}),
        response("submit_artifact", {"values": values, "files": {"rules.py": rewritten}}),
    )
    checked = []

    async def validate(candidate):
        checked.append(candidate)
        return Validation(["rules returns the wrong value"] if len(checked) == 1 else [], [])

    result = await generate(authored, provider, validate=validate)
    assert result.candidate.artifact.files == {"rules.py": rewritten}
    assert not any(event["event"] == "output.rejected" for event in result.trace)


@pytest.mark.asyncio
async def test_a_paused_implementation_keeps_its_edits_and_a_revised_plan_drops_them(authored):
    from experimental.harness.curator.generation.run import GenerationPausedError
    from experimental.harness.curator.generation.state import GenerationState

    values = {"action.strategy": {"factory": "rules:create"}}
    provider = Provider(
        response("submit_selection", selection("action.strategy")),
        response("submit_plan", plan("action.strategy")),
        response("edit_file", {"path": "rules.py", "old": "return None", "new": "return {}"}),
        response("stage_file", {"path": "extra.py", "content": "EXTRA = 1\n"}),
        response("submit_artifact", {"values": values, "files": {"rules.py": "def create(state, task): ...\n"}}),
        response("submit_artifact", {"values": values}),
        response("revise_plan", {"reason": "The design missed the observed condition."}),
        response("submit_plan", plan("action.strategy")),
        response("submit_artifact", {"values": values}),
    )
    checked = []

    async def validate(candidate):
        checked.append(candidate)
        return Validation(["rules returns the wrong value"] if len(checked) == 1 else [], [])

    with pytest.raises(GenerationPausedError) as paused:
        await generate(authored, provider, validate=validate, limits=Limits(max_calls=4))
    state = GenerationState.model_validate_json(paused.value.state.model_dump_json())
    assert state.edited == ["rules.py"] and sorted(state.staged) == ["extra.py", "rules.py"]
    resumed = Provider(*provider.responses)
    result = await generate(authored, resumed, validate=validate, limits=Limits(max_calls=10), resume=state)
    refused = next(event for event in result.trace if event["event"] == "output.rejected")
    assert "changed with edit_file" in refused["error"]
    assert sorted(checked[0].artifact.files) == ["extra.py", "rules.py"]
    assert result.candidate.artifact.files == {}


@pytest.mark.asyncio
async def test_a_target_whose_commitments_are_retired_must_leave_with_them(context):
    from dataclasses import replace

    from experimental.harness.contract import Commitment

    gate = Commitment(id="H1", surface="action.strategy", statement="Stop unchecked deliveries", serves=("task",))
    facts = {**context.facts, "authored": {"values": {"action.strategy": {"factory": "rules:create"}}, "files": {}}}
    current = replace(context, facts=facts, commitments=(gate,))
    retiring = {
        **plan("action.strategy"),
        "commitments": [{"action": "retire", "id": "H1", "reason": "it stopped legitimate deliveries"}],
    }
    provider = Provider(
        response("submit_selection", selection("action.strategy")),
        response("submit_plan", retiring),
        response("submit_artifact", {"values": {"action.strategy": {"factory": "rules:create"}}}),
        response("submit_artifact", {"values": {}, "remove": ["action.strategy"]}),
    )

    async def validate(candidate):
        return Validation([], [])

    result = await generate(current, provider, validate=validate)
    refused = next(event for event in result.trace if event["event"] == "output.rejected")
    assert "code but no current commitment: ['action.strategy']" in refused["error"]
    assert result.candidate.artifact.remove == ("action.strategy",)


@pytest.mark.asyncio
async def test_several_edits_and_files_in_one_response_apply_in_the_order_given(authored):
    staged = "def create(state, task):\n    value = 1\n    return value\n"
    provider = Provider(
        response("submit_selection", selection("memory.strategy")),
        response("submit_plan", plan("memory.strategy")),
        LLMResponse(
            content=None,
            tool_calls=[
                ToolCallRequest("first", "edit_file", {"path": "rules.py", "old": "return None", "new": "return {}"}),
                ToolCallRequest("second", "edit_file", {"path": "rules.py", "old": "return {}", "new": "return {1}"}),
                ToolCallRequest("third", "stage_file", {"path": "helper.py", "content": staged}),
                ToolCallRequest("fourth", "edit_file", {"path": "helper.py", "old": "value = 1", "new": "value = 2"}),
            ],
        ),
        response("submit_artifact", {"values": {"memory.strategy": {"factory": "rules:create"}}}),
    )

    async def validate(candidate):
        return Validation([], [])

    result = await generate(authored, provider, validate=validate)
    files = result.candidate.artifact.files
    assert files["rules.py"] == "def create(state, task):\n    return {1}\n"
    assert files["helper.py"] == staged.replace("value = 1", "value = 2")
    edits = [event for event in result.trace if event["event"] in ("file.edited", "file.staged")]
    assert [event["path"] for event in edits] == ["rules.py", "rules.py", "helper.py", "helper.py"]
    assert all("error" not in event["result"] for event in edits)


@pytest.mark.asyncio
async def test_stage_source_copies_a_registered_source_whole_without_the_model_retyping_it(context):
    provider = Provider(
        response("submit_selection", selection("action.strategy")),
        response("submit_plan", plan("action.strategy")),
        response("stage_source", {"source": "loop", "path": "assets/loop.md"}),
        response("stage_source", {"source": "missing", "path": "assets/missing.md"}),
        response("stage_file", {"path": "planning_impl.py", "content": "def create(state, task):\n    return None\n"}),
        response("submit_artifact", {"values": {"action.strategy": {"factory": "planning_impl:create"}}}),
    )

    async def validate(candidate):
        return Validation([], [])

    result = await generate(context, provider, validate=validate)
    assert result.candidate.artifact.files["assets/loop.md"] == "native protocol"
    staged = [event for event in result.trace if event["event"] == "file.staged"]
    assert staged[0]["result"] == {
        "staged": "assets/loop.md",
        "source": "loop",
        "chars": len("native protocol"),
        "staged_files": ["assets/loop.md"],
    }
    assert "unknown registered source: missing" in staged[1]["result"]["error"]
    assert "stage_source" in instructions(provider.requests[2])


@pytest.mark.asyncio
async def test_a_building_stage_down_to_the_review_reserve_is_told_to_submit(context):
    provider = Provider(
        response("submit_selection", selection("action.strategy")),
        response("submit_plan", plan("action.strategy")),
        response("stage_file", {"path": "planning_impl.py", "content": "def create(state, task):\n    return None\n"}),
        response("submit_artifact", {"values": {"action.strategy": {"factory": "planning_impl:create"}}}),
    )

    async def validate(candidate):
        return Validation([], [])

    await generate(context, provider, validate=validate, limits=Limits(max_calls=12, review_reserve=10))
    notes = [request["messages"][-1]["content"] for request in provider.requests]
    assert all("need at the end: 10" in note for note in notes)
    assert "nearly spent" not in notes[0] and "nearly spent" not in notes[1]
    assert "nearly spent: 10 remain" in notes[2] and "nearly spent: 9 remain" in notes[3]
