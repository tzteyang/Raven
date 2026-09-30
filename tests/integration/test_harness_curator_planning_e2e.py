"""Semantic planning generation, native execution and feedback revision share one task."""

import json
from copy import deepcopy
from functools import partial
from pathlib import Path

import pytest

from experimental.curator.harness import Artifact, Task
from experimental.curator.raven_adapter.planning.contracts import TARGET
from experimental.curator.raven_adapter.worker import Worker
from experimental.curator.workflow import improve
from raven.contracts.llm_provider import LLMResponse, ToolCallRequest
from tests.fixtures.harness_curator.authoring import capability, combine
from tests.integration.test_harness_curator_e2e import ReplayProvider, plan_for, replay_provider
from tests.integration.test_harness_curator_e2e import baseline as baseline
from tests.test_harness_curator_generation import diagnosis, packet, selection

TOOL_NAME = "curator_planning"

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/harness_curator"


def artifact():
    resources = [
        {"kind": "tool", "name": "planning_probe", "factory": "planning_bindings:probe", "native_context": True},
        {
            "kind": "skill",
            "name": "planning",
            "source": "Planning procedure",
            "files": {
                "SKILL.md": "---\nname: planning\ndescription: Use the task plan\nalways: true\n---\nPLANNING_SKILL_RUNTIME",
            },
        },
    ]
    plan = Artifact(
        values={
            TARGET: {
                "factory": "task_planning:create",
                "tool": {"name": TOOL_NAME, "description": "Read or update the task plan."},
                "context": True,
                "observe": ["after_iteration"],
            }
        },
        files={name: (FIXTURES / name).read_text() for name in ("task_planning.py", "planning_bindings.py")},
    )
    return combine(plan, capability(resources)).model_dump(mode="json")


def response(name, arguments):
    return LLMResponse(content=None, tool_calls=[ToolCallRequest(name, name, arguments)])


class CuratorProvider(ReplayProvider):
    def __init__(self, responses):
        super().__init__(responses)
        self.requests = []

    async def chat(self, messages, **kwargs):
        self.requests.append(deepcopy(messages))
        return await super().chat(messages, **kwargs)


def bind_task(baseline):
    baseline.task = Task(id="planning-task", text="Verify")
    baseline.config.permissions.tools[TOOL_NAME] = "allow"
    baseline.config.permissions.tools["planning_probe"] = "allow"
    return baseline


@pytest.mark.integration
@pytest.mark.asyncio
async def test_curator_runs_and_revises_a_real_planning_strategy(baseline, tmp_path):
    bind_task(baseline)
    actions = [
        response(TOOL_NAME, {"request": {"operation": "complete", "item": "Verify"}}),
        response("planning_probe", {}),
        LLMResponse(content="Verification has failed."),
        response(TOOL_NAME, {"request": {"operation": "view"}}),
        LLMResponse(content="Continue with the retained plan."),
    ]
    worker = Worker(
        baseline, tmp_path / "runtime", provider_factory=partial(replay_provider, responses=actions), timeout=30
    )
    proposed = artifact()
    curator = CuratorProvider(
        [
            response("read_source", {"name": TARGET, "find": "initialize"}),
            response("submit_diagnosis", diagnosis()),
            response("submit_selection", selection(*proposed["values"])),
            response("submit_plan", plan_for(*proposed["values"]).model_dump(mode="json")),
            response("submit_artifact", proposed),
        ]
    )
    async with worker:
        await improve(worker, curator)
        assert any("initialize" in str(row) and "history" in str(row) for row in curator.requests[2:])
        materials = packet({"messages": curator.requests[3]})
        contract = next(row for row in materials["selected_contracts"] if row["target"] == TARGET)
        assert "class PlanningStrategy" in str(contract["knowledge"])
        initial_packet = json.loads(curator.requests[0][1]["content"])
        assert initial_packet["orientation"]["source"] == "reference.index"
        assert "reference.planning" in initial_packet["sources"]
        assert initial_packet["orientation"]["text"]
        assert "Factory and session state" in str(contract["knowledge"])
        assert "completed-iteration evidence" in str(contract["knowledge"])
        assert any("explicitly inheriting PlanningStrategy" in str(request) for request in curator.requests)
        first = await worker.run("Verify using the task plan.")
        assert not first.errors
        assert any(row["kind"] == "planning.result" and row["source"] == "agent" for row in first.records)
        assert any(row["kind"] == "planning.result" and row["source"] == "observation" for row in first.records)
        requests = [row for row in first.records if row["kind"] == "provider.request"]
        assert all("CURRENT_TASK_PLAN" in str(row) for row in requests)
        assert any("PLANNING_SKILL_RUNTIME" in str(row) for row in requests)
        inspected = await worker.inspect()
        assert inspected.facts["planning"]["view"]["items"] == {"Verify": False}
        assert inspected.facts["planning"]["sessions"]["curator:task"]["seen"] == ["planning_probe"]
        before = (worker.root / "planning.json").read_bytes()
        pid = worker._process.pid
        continuation = await worker.run("Continue without changing the Harness.")
        assert not continuation.errors and worker._process.pid == pid
        assert (worker.root / "planning.json").read_bytes() == before
        assert len(curator.requests) == 5
        revised = deepcopy(proposed)
        revised["values"] = {TARGET: revised["values"][TARGET]}
        revised["files"]["task_planning.py"] = revised["files"]["task_planning.py"].replace(
            "GUARD_COMPLETION = False", "GUARD_COMPLETION = True"
        )
        feedback = CuratorProvider(
            [
                response("submit_diagnosis", diagnosis()),
                response("submit_selection", selection(TARGET)),
                response("submit_plan", plan_for(TARGET).model_dump(mode="json")),
                response("submit_artifact", revised),
            ]
        )
        await improve(
            worker,
            feedback,
            feedback={"source": "human", "text": "Require execution evidence before accepting completion."},
        )
        revision = json.loads(feedback.requests[1][1]["content"])
        assert "class Planning" in revision["current_authored"]["files"]["task_planning.py"]
        assert revision["worker"]["planning"]["sessions"]["curator:task"]["seen"] == ["planning_probe"]
        assert revision["previous_plan"]["changes"] and "Native effect" not in json.dumps(revision["previous_plan"])
        assert any(row.get("artifact_id") == continuation.artifact_id for row in revision["observations"])
        logs = [json.loads(path.read_text()) for path in (worker.root / "curation").glob("*.json")]
        assert len(logs) == 2
        assert any(row["feedback"] and row["turn_id"] == continuation.turn_id for row in logs)
        assert all(row["task_id"] == baseline.task.id for row in logs)
        after = await worker.inspect()
        assert after.facts["planning"]["view"]["guarded"]
        assert after.facts["planning"]["view"]["items"] == {"Verify": False}
        assert (worker.root / "planning.json").read_bytes() == before
        second = await worker.run("Try the revised behavior.")
        assert any("verified execution evidence" in str(row) for row in second.records)
        assert (await worker.inspect()).facts["planning"]["view"]["items"] == {"Verify": False}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_current_input_updates_plan_before_capability_and_withdraws_guidance(baseline, tmp_path):
    from tests.fixtures.harness_curator.authoring import profile

    bind_task(baseline)
    proposed = artifact()
    proposed["values"][TARGET]["observe"] = ["before_model", "after_iteration"]
    proposed["files"]["task_planning.py"] = proposed["files"]["task_planning.py"].replace(
        "        return observe(view, observation)",
        '        if observation.phase == "before_model":\n'
        '            if observation.iteration == 1 and any("CURRENT_CUSTOMER" in str(row) for row in observation.messages):\n'
        '                return Command(operation="complete", item=next(iter(view.items)))\n'
        "            return None\n"
        "        return observe(view, observation)",
    )
    proposed["files"]["planning_bindings.py"] = proposed["files"]["planning_bindings.py"].replace(
        'return "CURRENT_TASK_PLAN: " + view.model_dump_json()',
        'return "CURRENT_TASK_PLAN: " + view.model_dump_json() if all(view.items.values()) else None',
    )
    proposed["files"]["capability_impl.py"] = proposed["files"]["capability_impl.py"].replace(
        "return CapabilitySelection()",
        'return CapabilitySelection(tools=("planning_probe",) if request.plan["items"]["Verify"] else (), skills=())',
    )
    memory = profile({"TOOLS.md": "Use the current business plan."})
    proposed["values"].update(memory.values)
    proposed["files"].update(memory.files)
    actions = [response("planning_probe", {}), LLMResponse(content="The check failed; the plan remains incomplete.")]
    async with Worker(
        baseline, tmp_path / "runtime", provider_factory=partial(replay_provider, responses=actions), timeout=30
    ) as worker:
        inspection = await worker.inspect()
        await worker.install(inspection.declaration.accept(plan_for(*proposed["values"]), proposed))
        result = await worker.run("CURRENT_CUSTOMER: verify the task before delivery.")
        assert not result.errors
        requests = [row["parameters"] for row in result.records if row["kind"] == "provider.request"]
        assert len(requests) == 2
        assert "planning_probe" in str(requests[0]["tools"])
        assert "planning_probe" not in str(requests[1]["tools"])
        assert "CURRENT_TASK_PLAN" in str(requests[0]["messages"])
        assert "CURRENT_TASK_PLAN" not in str(requests[1]["messages"])
        inputs = [
            row["arguments"][0]
            for row in result.records
            if row["kind"] == "memory.call" and row["operation"] == "compose"
        ]
        assert [row["plan"]["items"]["Verify"] for row in inputs] == [True, False]
        assert any(
            row["kind"] == "planning.observation" and row["observation"]["phase"] == "before_model"
            for row in result.records
        )
