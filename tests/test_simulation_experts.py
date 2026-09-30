"""Expert materials and deployment stay faithful before Curator chooses their implementation."""

import json
from pathlib import Path

import pytest

from experimental.automation.employee import hire, hire_task
from experimental.curator.harness import Task
from experimental.curator.raven_adapter.baselines import Baseline
from experimental.simulation.experts import Expert
from experimental.simulation.scenario import BUNDLED, Scenario
from raven.config.raven import RavenConfig
from raven.config.schema import Config, ThirdPartyAcpSubagentConfig


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
    manifest = expert.stage(home)
    staged = home / expert.material_path
    for entry in manifest["files"]:
        original, copied = expert.root / entry["path"], staged / entry["path"]
        assert copied.read_bytes() == original.read_bytes()
        assert copied.stat().st_mode & 0o777 == entry["mode"]
    assert (staged / "skills/method/empty").is_dir()
    assert {path.name for path in home.iterdir()} == {"uploads"}
    assert expert.entries["rules"] == ["rules/process.md"]
    assert expert.material_path in expert.curation_request()
    assert "Original expert identity" not in expert.task().text
    assert not (home / "skills").exists()


def test_construction_objective_does_not_become_the_worker_business_task(tmp_path):
    expert = expert_package(tmp_path / "input")
    objective = "Add an internal single-step review with a typed model result."
    assert expert.task().text == "Help customers assess their project evidence."
    assert objective in expert.curation_request(objective)
    assert objective not in expert.task().text
    assert expert.material_path not in expert.task().text


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
