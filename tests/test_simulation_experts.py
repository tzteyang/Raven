"""Initial construction assesses interaction inputs and keeps optional research references separate."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from experimental.automation.employee import hire, hire_task
from experimental.curator.harness import Task
from experimental.curator.raven_adapter.baselines import Baseline
from experimental.simulation.experts import Expert
from experimental.simulation.scenario import BUNDLED, Scenario
from raven.config.raven import RavenConfig
from raven.config.schema import Config, ThirdPartyAcpSubagentConfig
from tests.test_research_collection import accepted, snapshot


def expert_package(root: Path) -> Expert:
    files = {
        ".example-plugin/plugin.json": json.dumps(
            {
                "name": "expert",
                "description": "Help customers assess their project evidence.",
                "agents": ["./agents/expert.md"],
                "rules": ["./rules/process.md"],
                "skills": ["./skills/method"],
            }
        ).encode(),
        "agents/expert.md": b"Original expert identity and working requirements.\r\n",
        "rules/process.md": b"Original workflow, not a generated procedure.",
        "skills/method/SKILL.md": b"---\nname: method\ndescription: Use the original method\n---\n",
        "skills/method/references/detail.md": b"Complete supporting information.",
        "skills/method/scripts/run.py": b'"""A supplied script."""\n',
        "skills/method/assets/input.bin": bytes(range(256)),
    }
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    (root / "skills/method/scripts/run.py").chmod(0o755)
    (root / "skills/method/empty").mkdir()
    return Expert.load(root)


def test_complete_package_is_staged_without_installing_expert_behavior(tmp_path):
    expert = expert_package(tmp_path / "input")
    home = tmp_path / "home"
    from experimental.research.curator import stage_materials

    (staged,) = stage_materials((expert.root,), home)
    for original in expert.root.rglob("*"):
        if original.is_file():
            copied = staged / original.relative_to(expert.root)
            assert copied.read_bytes() == original.read_bytes()
            assert copied.stat().st_mode & 0o777 == original.stat().st_mode & 0o777
    assert (staged / "skills/method/empty").is_dir()
    assert {path.name for path in home.iterdir()} == {"uploads"}
    assert expert.entries["rules"] == ["rules/process.md"]
    assert "uploads/information/expert.md" in expert.curation_request()
    assert "uploads/original-expert" not in expert.curation_request()
    assert "Original expert identity" not in expert.task().text
    assert not (home / "skills").exists()


def test_construction_objective_does_not_become_the_worker_business_task(tmp_path):
    expert = expert_package(tmp_path / "input")
    objective = "Add an internal single-step review with a typed model result."
    assert expert.task().text == "Help customers assess their project evidence."
    assert objective in expert.curation_request(objective)
    assert objective not in expert.task().text
    assert "uploads/original-expert" not in expert.task().text


def test_missing_declared_material_is_reported_before_curation(tmp_path):
    expert = expert_package(tmp_path / "input")
    (expert.root / "rules/process.md").unlink()
    with pytest.raises(ValueError, match="entry is absent"):
        Expert.load(expert.root)


def test_expert_and_scenario_share_deployment_capabilities(tmp_path):
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "agents": {"defaults": {"model": "deepseek/test", "provider": "deepseek"}},
                "tools": {"disabledTools": ["send_message"]},
            }
        )
    )
    scenario = Scenario.load(BUNDLED / "travel_agency")
    original = hire(scenario.contract, config, workdir=tmp_path / "a-work", root=tmp_path / "a")
    supplied = hire_task(
        Task(text="Apply supplied expert methods."), config, workdir=tmp_path / "b-work", root=tmp_path / "b"
    )
    assert original.baseline.config.tools == supplied.baseline.config.tools
    assert original.baseline.config.permissions == supplied.baseline.config.permissions
    assert supplied.baseline.allow_delegation
    assert not {"spawn", "run_subagent_dag", "web_search", "web_fetch"} & set(
        supplied.baseline.config.tools.disabled_tools
    )
    original_children = original._prepare_children(original.baseline)
    supplied_children = supplied._prepare_children(supplied.baseline)
    assert original_children.keys() == supplied_children.keys()
    assert "Raven" in supplied_children
    assert all(not child.baseline.allow_delegation for child in supplied_children.values())
    assert not supplied.artifact.values
    assert all(not child.artifact.values for child in supplied_children.values())


@pytest.mark.asyncio
async def test_failed_child_preparation_keeps_configuration_without_claiming_availability(tmp_path, monkeypatch):
    from experimental.simulation import experts

    expert = expert_package(tmp_path / "input")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"agents": {"defaults": {"model": "deepseek/test"}}}))
    native = Config()
    native.agents.defaults.workspace = str(tmp_path / "agent")
    native.subagents.agents = [ThirdPartyAcpSubagentConfig(name="Research", command="research-server")]
    baseline = Baseline(native, RavenConfig(), tmp_path / "work", task=expert.task())

    class UnreadyWorker:
        async def __aenter__(self):
            raise ValueError("Search credential is missing")

        async def __aexit__(self, *args):
            return None

    worker = UnreadyWorker()
    worker.baseline = baseline
    monkeypatch.setattr(experts, "hire_task", lambda *args, **kwargs: worker)
    output = tmp_path / "run"
    with pytest.raises(ValueError, match="Search credential"):
        await experts.run(expert, config, output)
    setup = json.loads((output / "setup.json").read_text())
    result = json.loads((output / "result.json").read_text())
    assert setup["configured_subagents"] == [{"name": "Research", "kind": "acp", "enabled": True}]
    assert "available_children" not in setup and "available_children" not in result
    assert result["stage"] == "prepare" and result["requests_completed"] == 0
    assert (output / "inputs.json").is_file()


@pytest.mark.parametrize("approved", [True, False])
@pytest.mark.parametrize("package_input", [True, False])
@pytest.mark.asyncio
async def test_initial_construction_reviews_information_before_curator_and_separates_material_purposes(
    tmp_path, monkeypatch, approved, package_input
):
    from experimental.research.information import Result, Review
    from experimental.simulation import experts

    expert = expert_package(tmp_path / "input")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"agents": {"defaults": {"model": "deepseek/test"}}}))
    native = Config()
    native.agents.defaults.workspace = str(tmp_path / "agent")
    baseline = Baseline(native, RavenConfig(), tmp_path / "work", task=expert.task())
    calls = []
    business_task = expert.task() if package_input else Task(text="Review current project evidence.")

    class Worker:
        artifact = SimpleNamespace(values={})
        children = {"Raven": SimpleNamespace(artifact=SimpleNamespace(values={}))}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def run(self, request, *, session_key):
            calls.append("execute")
            assert session_key.startswith("expert:")
            return SimpleNamespace(records=[])

        def records(self):
            return []

    worker = Worker()
    worker.baseline = baseline
    monkeypatch.setattr(experts, "hire_task", lambda *args, **kwargs: worker)
    monkeypatch.setattr(experts, "make_lazy_provider", lambda config: object())

    async def inspect(*args):
        return {}

    async def collect(worker, provider, request, *, materials, research_references, **kwargs):
        calls.append("collect")
        assert request.context["business_task"] == business_task.text
        if package_input:
            assert materials[0].is_relative_to(native.workspace_path / "uploads/materials")
            assert (materials[0] / "agents/expert.md").is_file()
            assert not research_references
        else:
            assert not materials and research_references == (expert.root,)
            assert not (native.workspace_path / "uploads").exists()
        review = (
            accepted()
            if approved
            else {"accepted": False, "reason": "Missing domain evidence.", "issues": ["Research the domain."]}
        )
        return Result(snapshot=snapshot(), review=Review.model_validate(review))

    async def improve(worker, provider, **kwargs):
        calls.append("curate")
        assert (native.workspace_path / "uploads/information/expert.md").is_file()
        assert (native.workspace_path / "uploads/materials/1-input/agents/expert.md").is_file() == package_input
        assert "uploads/original-expert" not in kwargs["feedback"]["text"]
        return {"installed": True}

    monkeypatch.setattr(experts, "_snapshot", inspect)
    monkeypatch.setattr(experts, "collect_for_curator", collect)
    monkeypatch.setattr(experts, "improve", improve)
    result = await experts.run(
        expert if package_input else None,
        config,
        tmp_path / "run",
        task=business_task,
        research_references=() if package_input else (expert.root,),
        requests=("Review this project",),
    )
    assert calls == (["collect", "curate", "execute"] if approved else ["collect"])
    assert result["status"] == ("completed" if approved else "incomplete")
    assert result["information_status"] == ("ready" if approved else "incomplete")


def test_cli_accepts_a_task_with_no_product_interaction_input(tmp_path, monkeypatch, capsys):
    import sys

    from experimental.simulation import experts

    mission = tmp_path / "mission.md"
    mission.write_text("Review project evidence.")
    material = tmp_path / "provided.md"
    material.write_text("Use the supplied evidence checklist.")
    guide = tmp_path / "research-case"
    guide.mkdir()
    calls = []

    async def run(expert, config, root, **kwargs):
        calls.append((expert, kwargs))
        return {"status": "completed"}

    monkeypatch.setattr(experts, "run", run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "experts",
            "--task-file",
            str(mission),
            "--config",
            str(tmp_path / "config.json"),
            "--output",
            str(tmp_path / "run"),
            "--material",
            str(material),
            "--research-reference",
            str(guide),
            "--research",
            "none",
        ],
    )
    experts.main()
    expert, options = calls[0]
    assert expert is None and options["task"].text == "Review project evidence."
    assert options["materials"] == (material,) and options["research_references"] == (guide,)
    assert json.loads(capsys.readouterr().out)["status"] == "completed"
