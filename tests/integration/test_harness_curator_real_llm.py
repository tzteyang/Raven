"""Opt-in protocol checks with real models; full expert cases use simulation.experts."""

import json
import os
from pathlib import Path
from uuid import uuid4

import pytest

from experimental.curator.generation.run import Limits
from experimental.curator.harness import Task
from experimental.curator.raven_adapter.inspection import Baseline
from experimental.curator.raven_adapter.worker import Worker
from experimental.curator.workflow import improve
from raven.config.raven import load_raven_config
from raven.core.config_stack import load_runtime_config
from raven.core.plugin_stack import discover_plugins
from raven.providers.factory import make_lazy_provider

pytestmark = [pytest.mark.integration, pytest.mark.real_llm, pytest.mark.slow]

SCENARIOS = {
    "memory": {
        "targets": ["memory.strategy"],
        "instruction": "Implement memory.strategy using initialize/interact/compose. The supplied task preference "
        "is cobalt. initialize establishes context organization from actual sources; compose renders the current "
        "preference as MEMORY:cobalt in system context and preserves required sources. Expose curator_memory_fact "
        "through the binding's tool. Its concrete command records a supplied text fact; retain committed facts in "
        "shared task knowledge and render them in system context on the next model call. Only committed facts "
        "belong in that knowledge block; do not copy a raw user request there or pre-invent facts. Initialization "
        "must preserve existing records across turns and revisions. Use a concrete initialization view that compose uses.",
        "request": "Use curator_memory_fact to record the exact text {nonce}, then report the current preference and retained fact.",
        "second": "State the current preference and the fact previously retained in memory. Do not record another fact.",
        "marker": "MEMORY:cobalt",
        "operations": {"initialize", "interact", "compose"},
    },
    "capability": {
        "targets": ["capability.strategy"],
        "instruction": "Implement capability.strategy with prepare/register/select. Delegate accepted contributions to "
        "the supplied registrar. Explicitly declare a no-argument inert tool factory producing curator_live_probe, "
        "whose execution returns exactly CAPABILITY:cobalt. Author a Skill named evidence_method from this "
        "procedure: PROCEDURE: call curator_live_probe and report its actual receipt. Register the tool and Skill, "
        "select that tool and request the Skill body so the actual worker input contains its procedure. Selection "
        "state is per session. Do not run any external service or execute anything at installation.",
        "request": "Call curator_live_probe and report its actual receipt.",
        "second": "Call curator_live_probe again using the revised procedure and report its receipt.",
        "marker": "CAPABILITY:cobalt",
        "operations": {"select"},
    },
    "action": {
        "targets": ["action.strategy", "capability.strategy"],
        "instruction": "Implement action.strategy with handle_event and handle_request. Provide an inert local "
        "tool action_gate_probe accepting a required string token and returning EXECUTED_TOKEN:<token>. Install "
        "the Action dispatch gate: only token cobalt may execute; refuse every other token with useful feedback. "
        "Use actual outcome evidence to remember a permitted execution in the current turn. Expose "
        "curator_action_status with a concrete finish boolean command. Report status; when finish is requested "
        "after actual permitted execution in that turn, request finish with truthful reply ACTION:cobalt. "
        "Before that, return an incomplete status without claiming success. Use control receipts honestly and "
        "inspect allowed_controls. Do not mistake batch proposals for executed results. Terminal failure must "
        "remain truthful. Register the probe through Capability.prepare and register; it performs no external effects.",
        "request": "This is a local guard test. First call action_gate_probe with token invalid to verify refusal, "
        "then call it with token cobalt, then ask curator_action_status to finish. Follow this order.",
        "second": "Test the revised guard: first call action_gate_probe with the former token cobalt to verify "
        "refusal, then with token amber, then ask curator_action_status to finish.",
        "marker": "ACTION:cobalt",
        "operations": {"handle_event", "handle_request"},
    },
}


def configured(tmp_path, instruction):
    location = os.environ.get("CURATOR_TEST_CONFIG")
    if not location:
        pytest.skip("Set CURATOR_TEST_CONFIG to run authorized paid model checks.")
    path = Path(location).expanduser().resolve()
    home, work = tmp_path / "home", tmp_path / "work"
    home.mkdir()
    work.mkdir()
    config = load_runtime_config(str(path), str(home))
    extensions = load_raven_config(path)
    extensions.plugins.disabled = [item.manifest.id for item in discover_plugins(extensions)]
    extensions.memory.backend = None
    extensions.skill_forge.router.hub.endpoint = ""
    extensions.session_title.enabled = False
    config.agents.defaults.max_tool_iterations = 12
    for name in (
        "curator_memory_fact",
        "curator_live_probe",
        "action_gate_probe",
        "curator_action_status",
        "read_file",
    ):
        config.permissions.tools[name] = "allow"
    model = os.environ.get("CURATOR_TEST_MODEL")
    if model:
        config.agents.defaults.model = model
    return Baseline(config, extensions, work, task=Task(text=instruction)), make_lazy_provider(config), model


def model_inputs(execution):
    return [row["parameters"] for row in execution.records if row["kind"] == "provider.request"]


def system_text(request):
    return "\n".join(str(row.get("content", "")) for row in request["messages"] if row.get("role") == "system")


def assert_memory_execution(execution, preference, nonce, *, recording):
    inputs = model_inputs(execution)
    assert f"MEMORY:{preference}" in system_text(inputs[0])
    assert preference in execution.text.casefold() and nonce in execution.text
    if recording:
        assert nonce not in system_text(inputs[0])
        assert any(nonce in system_text(request) for request in inputs[1:])
    else:
        assert nonce in system_text(inputs[0])


def tool_results(execution, name):
    return [
        row
        for request in model_inputs(execution)
        for row in request["messages"]
        if row.get("role") == "tool" and row.get("name") == name
    ]


LIMITS = Limits(max_calls=40, max_queries=24, max_checks=8, max_repairs=6, call_timeout=180, max_output=12000)


@pytest.mark.parametrize("role", SCENARIOS)
@pytest.mark.asyncio
async def test_generated_strategy_with_configured_models(role, tmp_path):
    scenario = SCENARIOS[role]
    baseline, provider, model = configured(tmp_path, scenario["instruction"])
    async with Worker(baseline, tmp_path / "runtime", names=scenario["targets"], timeout=300) as worker:
        first = await improve(worker, provider, model=model, limits=LIMITS)
        assert f"{role}.strategy" in worker.artifact.values
        nonce = "retained_" + uuid4().hex
        execution = await worker.run(scenario["request"].format(nonce=nonce))
        assert not execution.errors, execution.errors
        called = {row["operation"] for row in execution.records if row["kind"] == f"{role}.call"}
        assert scenario["operations"] <= called
        if role != "memory":
            assert scenario["marker"] in execution.text
        if role == "memory":
            assert_memory_execution(execution, "cobalt", nonce, recording=True)
        elif role == "capability":
            assert any("PROCEDURE:" in system_text(request) for request in model_inputs(execution))
            assert any(
                "CAPABILITY:cobalt" in str(row["content"]) for row in tool_results(execution, "curator_live_probe")
            )
        else:
            receipts = [row["receipt"] for row in execution.records if row["kind"] == "action.control"]
            assert any(row["control"] == "reject" and row["status"] == "applied" for row in receipts)
            assert any(row["control"] == "finish" and row["status"] == "applied" for row in receipts)
            assert not any(
                "EXECUTED_TOKEN:invalid" in str(row["content"]) for row in tool_results(execution, "action_gate_probe")
            )
            assert any(
                "EXECUTED_TOKEN:cobalt" in str(row["content"]) for row in tool_results(execution, "action_gate_probe")
            )
        before = execution.artifact_id
        revised = await improve(
            worker,
            provider,
            model=model,
            limits=LIMITS,
            feedback={
                "source": "human",
                "text": "The new supplied preference/token is amber, replacing cobalt. Revise the existing mechanism "
                "and relevant resources. Migrate retained preference or policy explicitly if needed, preserve all "
                "other committed facts and progress, and keep the existing interaction entry names. Current system "
                "knowledge must show the new preference. For Action, the old token must now be refused and only amber "
                "may execute; completion requires actual allowed execution in the current turn.",
            },
        )
        second = await worker.run(scenario["second"])
        assert not second.errors, second.errors
        assert second.artifact_id != before
        if role != "memory":
            assert scenario["marker"].replace("cobalt", "amber") in second.text
        if role == "memory":
            assert_memory_execution(second, "amber", nonce, recording=False)
            assert "MEMORY:cobalt" not in system_text(model_inputs(second)[0])
        elif role == "capability":
            assert any("CAPABILITY:amber" in str(row["content"]) for row in tool_results(second, "curator_live_probe"))
        else:
            receipts = [row["receipt"] for row in second.records if row["kind"] == "action.control"]
            assert any(row["control"] == "reject" and row["status"] == "applied" for row in receipts)
            assert any(
                "EXECUTED_TOKEN:amber" in str(row["content"]) for row in tool_results(second, "action_gate_probe")
            )
        report = {
            "role": role,
            "task_id": baseline.task.id,
            "model": baseline.config.agents.defaults.model,
            "first_trace": first.trace,
            "revision_trace": revised.trace,
            "first_turn": execution.turn_id,
            "second_turn": second.turn_id,
            "before_artifact": before,
            "after_artifact": second.artifact_id,
        }
        (tmp_path / "model-check.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))


@pytest.mark.asyncio
async def test_curator_adopts_an_uploaded_package_and_revises_it_from_new_material(tmp_path):
    instruction = (
        "Inspect the complete uploaded Skill package in worker.skill_packages and explicitly adopt it through "
        "Capability.prepare/register code. Preserve its nested and binary assets exactly. The Skill is owner-provided "
        "and named supplied_method. Do not rewrite binary bytes. Configure capability.strategy register/select "
        "to deliver the adopted Skill body so the worker can read its referenced procedure file with read_file."
    )
    baseline, provider, model = configured(tmp_path, instruction)
    source = tmp_path / "provided"
    (source / "references").mkdir(parents=True)
    (source / "SKILL.md").write_text(
        "---\nname: supplied_method\ndescription: Read the provided procedure.\n---\n"
        "Read [procedure](references/procedure.txt) using read_file and report the exact package code.\n"
    )
    (source / "references/procedure.txt").write_text("PACKAGE_CODE: cobalt")
    (source / "references/data.bin").write_bytes(bytes(range(256)))
    async with Worker(
        baseline,
        tmp_path / "runtime",
        names=["capability.strategy"],
        timeout=300,
    ) as worker:
        staged = await worker.stage_skill_package(source)
        assert "supplied_method" not in {row["name"] for row in (await worker.inspect()).facts["skills"]}
        first = await improve(
            worker, provider, model=model, limits=LIMITS, feedback={"source": "owner", "package": staged}
        )
        current = await worker.inspect()
        installed = Path(
            next(row["path"] for row in current.facts["skills"] if row["name"] == "supplied_method")
        ).parent
        assert (installed / "references/data.bin").read_bytes() == bytes(range(256))
        execution = await worker.run("Read the package's procedure file and report its exact package code.")
        assert not execution.errors, execution.errors
        assert any("PACKAGE_CODE: cobalt" in str(row["content"]) for row in tool_results(execution, "read_file"))
        (source / "references/procedure.txt").write_text("PACKAGE_CODE: amber")
        updated = await worker.stage_skill_package(source)
        revision = await improve(
            worker,
            provider,
            model=model,
            limits=LIMITS,
            feedback={
                "source": "owner",
                "text": "Replace the previously adopted package with this updated complete package; "
                "preserve its binary asset and existing selection behavior.",
                "package": updated,
            },
        )
        second = await worker.run("Read the current package procedure and report its updated package code.")
        assert not second.errors, second.errors
        assert any("PACKAGE_CODE: amber" in str(row["content"]) for row in tool_results(second, "read_file"))
        current = await worker.inspect()
        installed = Path(
            next(row["path"] for row in current.facts["skills"] if row["name"] == "supplied_method")
        ).parent
        assert (installed / "references/data.bin").read_bytes() == bytes(range(256))
        (tmp_path / "model-check.json").write_text(
            json.dumps(
                {
                    "role": "skill_adoption",
                    "first_trace": first.trace,
                    "revision_trace": revision.trace,
                    "first_turn": execution.turn_id,
                    "second_turn": second.turn_id,
                },
                ensure_ascii=False,
                indent=2,
            )
        )


@pytest.mark.asyncio
async def test_generated_strategies_share_live_owners_through_capability_registration(tmp_path):
    instruction = (
        "Implement a cooperating Memory, Capability and Action mechanism. The initial preference is cobalt. "
        "Memory initialize/compose must organize actual sources, render MEMORY:cobalt in system context, and "
        "render only committed facts there. Expose curator_memory_fact through its binding. Its concrete "
        "command supports recording a text fact and reading the current preference and latest committed fact. "
        "Keep facts in shared task knowledge across turns and revisions; initialize must not erase them. "
        "Expose curator_action_status through Action's request binding with a concrete finish boolean. On a "
        "finish request, Action must use peers.interact_memory to query the SAME active Memory owner's current "
        "preference and latest fact. If no fact is committed, return incomplete. Otherwise request finish "
        "with the exact reply JOINT:<preference>:<latest fact>, honoring allowed_controls and actual receipts. "
        "Action must not maintain a copy of Memory facts or read another owner's checkpoint files. Capability "
        "register delegates to the supplied registrar, so both interaction tools use the common registration "
        "path; select must activate both tools. Author and select the body of Skill joint_procedure describing "
        "this cooperation, including the marker JOINT_PROCEDURE: use memory then action. Implement selected "
        "public operations with concrete types. No external services or installation side effects."
    )
    baseline, provider, model = configured(tmp_path, instruction)
    targets = ["memory.strategy", "capability.strategy", "action.strategy"]
    async with Worker(baseline, tmp_path / "runtime", names=targets, timeout=300) as worker:
        first = await improve(worker, provider, model=model, limits=LIMITS)
        nonce = "joint_" + uuid4().hex
        execution = await worker.run(
            f"Use curator_memory_fact to record the exact text {nonce}, then ask curator_action_status to finish."
        )
        assert not execution.errors, execution.errors
        assert execution.text == f"JOINT:cobalt:{nonce}"
        inputs = model_inputs(execution)
        assert nonce not in system_text(inputs[0])
        assert any(nonce in system_text(request) for request in inputs[1:])
        assert "JOINT_PROCEDURE:" in system_text(inputs[0])
        assert any(
            row["kind"] == "strategy.peer_result" and row["target"] == "memory" and nonce in str(row["result"])
            for row in execution.records
        )
        revision = await improve(
            worker,
            provider,
            model=model,
            limits=LIMITS,
            feedback={
                "source": "human",
                "text": "Change the preference to amber, preserving the committed fact and all "
                "three strategies' cooperation. Revise the existing initialization or shared preference as needed. "
                "Action must still query the live Memory owner and finish with JOINT:<current preference>:<latest fact>.",
            },
            observations=list(execution.records),
        )
        second = await worker.run(
            "Ask curator_action_status to finish using the existing fact. Do not record a new fact."
        )
        assert not second.errors, second.errors
        assert second.artifact_id != execution.artifact_id
        assert second.text == f"JOINT:amber:{nonce}"
        assert nonce in system_text(model_inputs(second)[0])
        assert "MEMORY:amber" in system_text(model_inputs(second)[0])
        assert any(
            row["kind"] == "strategy.peer_result" and row["target"] == "memory" and nonce in str(row["result"])
            for row in second.records
        )
        assert any(
            row["kind"] == "action.control"
            and row["receipt"]["control"] == "finish"
            and row["receipt"]["status"] == "applied"
            for row in second.records
        )
        (tmp_path / "model-check.json").write_text(
            json.dumps(
                {
                    "role": "joint",
                    "first_trace": first.trace,
                    "revision_trace": revision.trace,
                    "first_turn": execution.turn_id,
                    "second_turn": second.turn_id,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
