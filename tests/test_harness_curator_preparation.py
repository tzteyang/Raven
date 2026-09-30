"""Typed preparation applies role-owned choices while preserving unrelated native configuration."""

import pytest

from experimental.curator.harness import Artifact, Task
from experimental.curator.raven_adapter.baselines import Baseline
from experimental.curator.raven_adapter.materialize import native_settings, write_package
from experimental.curator.raven_adapter.observe import Recorder
from experimental.curator.raven_adapter.preparation import (
    BackendPolicy,
    ContextPolicy,
    ExecutionPolicy,
    GenerationPolicy,
    Preparation,
    SkillPolicy,
    ToolPolicy,
)
from raven.config.raven import RavenConfig
from raven.config.schema import Config
from raven.playbook import NodeSpec, PlaybookSpec, PlaybookStore


def prepare(tmp_path, *, resident=True, leaf=False):
    config = Config()
    config.agents.defaults.workspace = str(tmp_path / "home")
    config.agents.defaults.model = "example/baseline-model"
    config.agents.defaults.max_tool_iterations = 17
    config.tools.disabled_tools = ["exec"]
    extension = RavenConfig(memory={"backend": None})
    extension.context.relevance_decay = 0.77
    baseline = Baseline(
        config, extension, tmp_path, task=Task(text="Prepare the task"), resident=resident, allow_delegation=not leaf
    )
    artifact = Artifact(values={})
    package = write_package(tmp_path / "package", artifact)
    return Preparation(baseline, artifact, package, Recorder(tmp_path / "records.jsonl"))


def test_sparse_policy_updates_preserve_native_defaults_and_other_strategy_choices(tmp_path):
    prepared = prepare(tmp_path)
    prepared.host("memory").context(ContextPolicy(drop_segments=["memory"]))
    prepared.host("action").generation(GenerationPolicy(temperature=0.2))
    prepared.host("capability").tools(ToolPolicy(disabled_tools=["ask_user"]))
    effects = prepared.freeze()
    effective = native_settings(prepared.baseline, effects)
    assert effective.config.agents.defaults.temperature == 0.2
    assert effective.config.agents.defaults.model == "example/baseline-model"
    assert effective.config.agents.defaults.max_tool_iterations == 17
    assert effective.extensions.context.relevance_decay == 0.77
    assert effective.extensions.context.drop_segments == ["memory"]
    assert effective.config.tools.disabled_tools == ["exec", "ask_user"]
    assert effective.extensions.base is effective.config
    assert prepared.baseline.config.tools.disabled_tools == ["exec"]
    assert effects.config["agents"]["defaults"] == {"temperature": 0.2}


def test_closed_setup_services_do_not_mutate_a_running_generation(tmp_path):
    preparation = prepare(tmp_path)
    memory = preparation.host("memory")
    memory.profile({"TOOLS.md": "Initial rules"})
    effects = preparation.freeze()
    with pytest.raises(ValueError, match="closed"):
        memory.profile({"TOOLS.md": "Late rules"})
    assert effects.files() == {"TOOLS.md": "Initial rules"}


def test_role_services_have_no_ambient_cross_role_configuration_setter(tmp_path):
    preparation = prepare(tmp_path)
    assert not hasattr(preparation.host("capability"), "generation")
    assert not hasattr(preparation.host("action"), "profile")
    with pytest.raises(ValueError):
        BackendPolicy(user_id="another identity")
    with pytest.raises(ValueError):
        ToolPolicy(restrict_to_workspace=False)
    with pytest.raises(ValueError):
        SkillPolicy(auto_evolve=True)
    with pytest.raises(TypeError, match="GenerationPolicy"):
        preparation.host("action").generation(ExecutionPolicy(max_tool_iterations=4))


def test_prepared_playbook_and_requirements_use_the_native_format(tmp_path):
    preparation = prepare(tmp_path)
    spec = PlaybookSpec(
        name="verify-task",
        description="Verify task evidence",
        task_summary="Verify task",
        mode="dag",
        confirm=False,
        triggers={"keywords": ["verify"]},
        nodes=[NodeSpec(id="verify", subagent="Reviewer", node_summary="Verify", prompt_template="Check evidence.")],
    )
    preparation.host("planning").playbook(spec)
    effects = preparation.freeze()
    path = tmp_path / "native" / "verify-task" / "playbook.md"
    path.parent.mkdir(parents=True)
    path.write_text(effects.files()["playbooks/verify-task/playbook.md"])
    loaded = PlaybookStore(path.parent.parent, builtin_root=tmp_path / "empty").load("verify-task")
    assert loaded.nodes[0].id == "verify" and loaded.nodes[0].subagent == "Reviewer"


def test_hosting_reachability_is_checked_before_recording_a_usable_component(tmp_path):
    preparation = prepare(tmp_path, resident=False, leaf=True)
    with pytest.raises(ValueError, match="resident"):
        preparation.host("memory").session_observer("cleanup", "module:observer")
    with pytest.raises(ValueError, match="resident"):
        preparation.host("action").service("watch", "module:watch")
    with pytest.raises(ValueError, match="leaf"):
        preparation.host("planning").playbook(None)
    assert preparation.freeze().components == ()
