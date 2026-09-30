"""Generated memory, capability and action run together on the real Raven loop."""

import json
from copy import deepcopy
from functools import partial

import pytest

from experimental.curator.harness import Task
from experimental.curator.raven_adapter.worker import Worker, WorkerError
from experimental.curator.workflow import improve
from raven.contracts.llm_provider import LLMResponse
from tests.fixtures.harness_curator.authoring import add_method, capability
from tests.integration.test_harness_curator_e2e import baseline as baseline
from tests.integration.test_harness_curator_e2e import plan_for, replay_provider
from tests.integration.test_harness_curator_planning_e2e import CuratorProvider, response
from tests.test_harness_curator_generation import diagnosis, packet, selection
from tests.test_harness_curator_strategies import files, values


def setup(baseline):
    baseline.task = Task(id="strategies-task", text="Obtain actual evidence before making a factual claim.")
    baseline.config.permissions.tools["evidence_probe"] = "allow"


def artifact():
    return {"values": values(), "files": files()}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_generation_feedback_and_actual_three_strategy_execution(baseline, tmp_path):
    setup(baseline)
    actions = [
        LLMResponse(content="An unsupported assertion."),
        response("evidence_probe", {}),
        LLMResponse(content="The evidence says cobalt."),
    ]
    proposed = artifact()
    proposed["files"]["task_action.py"] = proposed["files"]["task_action.py"].replace(
        "REQUIRE_EVIDENCE = True", "REQUIRE_EVIDENCE = False"
    )
    curator = CuratorProvider(
        [
            response("submit_diagnosis", diagnosis()),
            response("submit_selection", selection(*proposed["values"])),
            response("submit_plan", plan_for(*proposed["values"]).model_dump(mode="json")),
            response("submit_artifact", proposed),
        ]
    )
    async with Worker(
        baseline, tmp_path / "runtime", timeout=30, provider_factory=partial(replay_provider, responses=actions)
    ) as worker:
        await improve(worker, curator)
        materials = packet({"messages": curator.requests[2]})
        for role in ("memory", "capability", "action"):
            contract = next(row for row in materials["selected_contracts"] if row["target"] == f"{role}.strategy")
            knowledge = str(contract["knowledge"])
            assert f"class {role.title()}Strategy" in knowledge
            assert f"# {role.title()} strategy on Raven" in knowledge
            assert "class TaskBinding" in knowledge and "class StepView" in knowledge
        first = await worker.run("Make a factual claim.", session_key="curator:strategies")
        assert not first.errors
        assert not any(row["kind"] == "memory.result" and row["operation"] == "interact" for row in first.records)
        second = await worker.run("Obtain evidence.", session_key="curator:strategies")
        assert not second.errors
        requests = [row for row in second.records if row["kind"] == "provider.request"]
        assert "CAPABILITY_SKILL_RUNTIME" in str(requests)
        assert "CAPABILITY_USAGE:evidence_probe" in str(requests)
        assert "MEMORY_CONTEXT:cobalt" in str(requests)
        inspected = await worker.inspect()
        assert inspected.facts["memory"]["shared"]["facts"] == {"evidence_probe": "cobalt"}
        assert inspected.facts["capability"]["tools"][0]["function"]["name"] == "evidence_probe"
        assert "evidence" in inspected.facts["capability"]["skills"]
        before = (worker.root / "memory.json").read_bytes()
        revised = artifact()
        revised["values"] = {"action.strategy": revised["values"]["action.strategy"]}
        feedback = CuratorProvider(
            [
                response("submit_diagnosis", diagnosis()),
                response("submit_selection", selection("action.strategy")),
                response("submit_plan", plan_for("action.strategy").model_dump(mode="json")),
                response("submit_artifact", revised),
            ]
        )
        await improve(worker, feedback, feedback={"source": "human", "text": "Require actual evidence in each turn."})
        assert (worker.root / "memory.json").read_bytes() == before
        materials = json.loads(feedback.requests[1][1]["content"])
        assert materials["worker"]["memory"]["shared"]["facts"]
        assert "capability.strategy" in materials["current_authored"]["values"]
        result = await worker.run("Make a new factual claim.", session_key="curator:strategies")
        assert not result.errors
        calls = [row for row in result.records if row["kind"] == "provider.request"]
        assert len(calls) == 3
        assert "Call evidence_probe before finishing." in str(calls[1])
        assert any(row["kind"] == "action.result" and row["result"]["control"] == "revise" for row in result.records)
        assert (await worker.inspect()).facts["action"]["sessions"]["curator:strategies"]["retries"] >= 1
        records = [json.loads(path.read_text()) for path in (worker.root / "curation").glob("*.json")]
        assert len(records) == 2 and any(row["turn_id"] == second.turn_id for row in records)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_all_strategy_checkpoints_are_isolated_and_restored_on_failed_activation(baseline, tmp_path):
    from tests.integration.test_harness_curator_planning_e2e import artifact as planning_artifact

    setup(baseline)
    async with Worker(baseline, tmp_path / "runtime", provider_factory=replay_provider, timeout=30) as worker:
        proposed = artifact()
        planning = planning_artifact()
        proposed["values"]["planning.strategy"] = planning["values"]["planning.strategy"]
        proposed["files"].update(planning["files"])
        inspected = await worker.inspect()
        await worker.install(inspected.declaration.accept(plan_for(*proposed["values"]), proposed))
        roles = ("planning", "memory", "capability", "action")
        before = {role: (worker.root / f"{role}.json").read_bytes() for role in roles}
        bad = deepcopy(proposed)
        for role in before:
            bad["files"][f"task_{role}.py"] = bad["files"][f"task_{role}.py"].replace(
                f"return {role.title()}(",
                f'state.setdefault("migration", "candidate")\n    return {role.title()}(',
            )
        bad["files"]["failure.py"] = """class Service:
    name = "failed_activation"
    async def start(self, handles):
        raise RuntimeError("activation failed")
    async def stop(self):
        pass

def create(context):
    return Service()
"""
        source = (
            "from experimental.curator.harness.preparation import PreparationRequest\n" + bad["files"]["task_action.py"]
        )
        source = add_method(
            source,
            "Action",
            'def prepare(self, request: PreparationRequest) -> None:\n    self.host.service("failed_activation", "failure:create")',
        )
        source += "\n_original_create = create\ndef create(state, task, *, host):\n    value = _original_create(state, task)\n    value.host = host\n    return value\n"
        bad["files"]["task_action.py"] = source
        inspection = await worker.inspect()
        candidate = inspection.declaration.accept(plan_for(*bad["values"]), bad)
        report = await worker.check(candidate)
        assert report.passed, report.errors
        assert any(
            row["kind"] == "component.constructed" and row.get("name") == "failed_activation"
            for row in report.observations
        )
        assert all((worker.root / f"{role}.json").read_bytes() == value for role, value in before.items())
        with pytest.raises(WorkerError, match="service did not start"):
            await worker.install(candidate)
        assert all((worker.root / f"{role}.json").read_bytes() == value for role, value in before.items())
        assert worker.artifact.values == proposed["values"]
        assert "migration" not in (await worker.inspect()).facts["planning"]["state"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_native_permission_denial_still_applies_to_strategy_provided_tools(baseline, tmp_path):
    setup(baseline)
    baseline.config.permissions.tools["evidence_probe"] = "deny"
    actions = [response("evidence_probe", {}), LLMResponse(content="The tool was denied.")]
    proposed = artifact()
    proposed["values"] = {"capability.strategy": proposed["values"]["capability.strategy"]}
    async with Worker(
        baseline, tmp_path / "runtime", timeout=30, provider_factory=partial(replay_provider, responses=actions)
    ) as worker:
        inspection = await worker.inspect()
        await worker.install(inspection.declaration.accept(plan_for(*proposed["values"]), proposed))
        result = await worker.run("Get evidence")
        requests = [row for row in result.records if row["kind"] == "provider.request"]
        assert "FACT:cobalt" not in str(requests)
        assert "blocked by a deny rule" in str(requests).lower()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_four_strategy_composition_preserves_planning_and_rejects_stale_candidates(baseline, tmp_path):
    from tests.integration.test_harness_curator_planning_e2e import artifact as planning_artifact

    setup(baseline)
    baseline.config.permissions.tools["curator_planning"] = "allow"
    baseline.config.agents.defaults.max_tool_iterations = 6
    proposed = artifact()
    planning = planning_artifact()
    proposed["values"]["planning.strategy"] = planning["values"]["planning.strategy"]
    proposed["files"].update(planning["files"])
    actions = [
        response("evidence_probe", {}),
        response("curator_planning", {"request": {"operation": "complete", "item": baseline.task.text}}),
        LLMResponse(content="Evidence obtained and planning updated."),
    ]
    async with Worker(
        baseline, tmp_path / "runtime", timeout=30, provider_factory=partial(replay_provider, responses=actions)
    ) as worker:
        inspection = await worker.inspect()
        await worker.install(inspection.declaration.accept(plan_for(*proposed["values"]), proposed))
        inspection = await worker.inspect()
        stale = inspection.declaration.accept(
            plan_for("memory.strategy"), {"values": {"memory.strategy": proposed["values"]["memory.strategy"]}}
        )
        execution = await worker.run("Obtain evidence, then complete the task's plan item.")
        assert not execution.errors
        after = await worker.inspect()
        assert after.facts["planning"]["view"]["items"] == {baseline.task.text: True}
        for role in ("planning", "memory", "capability", "action"):
            assert any(row["kind"] == f"{role}.call" for row in execution.records)
            assert (worker.root / f"{role}.json").is_file()
        with pytest.raises(ValueError, match="baseline"):
            await worker.install(stale)


async def exercise_tool_guard(bound):
    from tests.integration.test_harness_curator_e2e import exercise_turn

    await exercise_turn(bound)
    results = [
        message
        for row in bound.recorder.rows
        if row["kind"] == "provider.request"
        for message in row.get("parameters", {}).get("messages", [])
        if message.get("role") == "tool"
    ]
    assert not any("blocked_probe_EXECUTED" in str(message) for message in results), "forbidden proposal executed"
    assert any("safe_probe_EXECUTED" in str(message) for message in results), "permitted proposal did not execute"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_semantic_translation_failure_reaches_repair_through_native_execution(baseline, tmp_path):
    from pathlib import Path

    from experimental.curator.generation.context.collect import collect
    from tests.test_harness_curator_generation import generate

    baseline.task = Task(id="guard", text="Refuse blocked_probe and allow safe_probe.")
    baseline.config.permissions.tools.update(blocked_probe="allow", safe_probe="allow")
    code = (Path(__file__).parents[1] / "fixtures/harness_curator/tool_guard.py").read_text()
    proposed = {
        "values": {
            "action.strategy": {
                "factory": "tool_guard:create",
                "events": ["proposal"],
            },
        },
        "files": {"tool_guard.py": code},
    }
    tools = capability(
        [
            {"kind": "tool", "name": "blocked_probe", "factory": "tool_guard:blocked", "native_context": True},
            {"kind": "tool", "name": "safe_probe", "factory": "tool_guard:safe", "native_context": True},
        ]
    )
    proposed["values"].update(tools.values)
    proposed["files"].update(tools.files)
    broken = deepcopy(proposed)
    broken["files"]["tool_guard.py"] = code.replace(
        "[call.name for call in event.calls]",
        "[getattr(call.function, 'name') for call in event.calls if getattr(call, 'function', None) is not None]",
    )
    actions = [response("blocked_probe", {}), response("safe_probe", {}), LLMResponse(content="done")]
    plan = plan_for(*proposed["values"])
    curator = CuratorProvider(
        [
            response("submit_selection", selection(*proposed["values"])),
            response("submit_plan", plan.model_dump(mode="json")),
            response("submit_artifact", broken),
            response("submit_artifact", proposed),
        ]
    )
    async with Worker(
        baseline, tmp_path / "runtime", timeout=30, provider_factory=partial(replay_provider, responses=actions)
    ) as worker:
        inspection = await worker.inspect()
        candidate = inspection.declaration.accept(plan, broken)
        assembly = await worker.check(candidate)
        assert assembly.passed
        assert any(row.get("status") == "not_supplied" for row in assembly.observations)
        current = worker.revision_id
        context = collect(
            baseline.task.text,
            inspection.declaration,
            facts=inspection.facts,
            sources=inspection.sources,
            read_source=inspection.read_source,
        )
        result = await generate(context, curator, validate=partial(worker.check, probe=exercise_tool_guard))
        failed = [row for row in result.trace if row["event"] == "validation" and row["errors"]]
        assert failed and "forbidden proposal executed" in str(failed)
        assert any(row["kind"] == "validation.error" for row in failed[0]["observations"])
        assert result.validation.passed
        assert any(row.get("status") == "completed" for row in result.validation.observations)
        assert worker.revision_id == current and not worker.artifact.values
        materials = packet({"messages": curator.requests[1]})
        contract = next(row for row in materials["selected_contracts"] if row["target"] == "action.strategy")
        assert "class ProposedCall" in str(contract["knowledge"])
