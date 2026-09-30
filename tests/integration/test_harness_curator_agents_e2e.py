"""A rendered product profile retains its native plugins when Curator changes its harness."""

import pytest

from experimental.curator.harness import Task
from experimental.curator.raven_adapter.inspection import Baseline
from experimental.curator.raven_adapter.worker import Worker
from raven.config.loader import load_config
from raven.config.raven import load_raven_config
from raven.core.plugin_stack import discover_plugins
from tests.fixtures.harness_curator.authoring import action
from tests.integration.test_harness_curator_e2e import plan_for, replay_provider
from tests.test_agents_code_launcher import RUN_PY
from tests.test_agents_code_launcher import grounded as grounded
from tests.test_agents_code_launcher import launcher as launcher


@pytest.mark.integration
@pytest.mark.asyncio
async def test_a_rendered_code_agent_keeps_its_plugins_mechanism_and_tools_through_curator_changes(grounded, tmp_path):
    from experimental.curator.raven_adapter.exploration import Exploration

    rendered = grounded.render_acp_config(RUN_PY.parent / "config.json")
    config, extensions = load_config(rendered), load_raven_config(rendered)
    extensions.memory.backend = None
    extensions.plugins.disabled = [p.manifest.id for p in discover_plugins(extensions) if p.manifest.id != "code-flow"]
    extensions.skill_forge.router.hub.endpoint = ""
    workdir = tmp_path / "work"
    workdir.mkdir()
    baseline = Baseline(config, extensions, workdir, task=Task(id="code-task", text="Inspect project"))
    async with Worker(baseline, tmp_path / "worker", provider_factory=replay_provider) as worker:
        before = await worker.inspect()
        assert "code-flow" in {plugin["id"] for plugin in before.facts["plugins"]}
        assert "todo" in {tool["function"]["name"] for tool in before.facts["tools"]}
        mechanism = next(m for m in before.mechanisms if m.name == "code.plan")
        assert set(mechanism.roles) == {"memory", "planning", "capability"}
        async with Exploration(config, before) as exploration:
            tool = exploration.read_source(name="tool.todo")
            assert "TodoStore" in tool["text"]
            assert "code_flow" in tool["path"]
            assert any("code_flow" in str(path) for path in exploration.originals)
        candidate = before.declaration.accept(plan_for("action.strategy"), action(generation={"temperature": 0.2}))
        validation = await worker.check(candidate)
        assert validation.passed, validation.errors
        await worker.install(candidate)
        after = await worker.inspect()
        assert "code-flow" in {plugin["id"] for plugin in after.facts["plugins"]}
        assert {tool["function"]["name"] for tool in after.facts["tools"]} == {
            tool["function"]["name"] for tool in before.facts["tools"]
        }
        assert after.facts["configuration"]["config"]["agents"]["defaults"]["temperature"] == 0.2
        assert any(m.name == "code.plan" for m in after.mechanisms)
        assert any(m.name == "authored.action.strategy" for m in after.mechanisms)
        assert before.declaration.baseline != after.declaration.baseline
        removal = after.declaration.accept(plan_for("action.strategy"), {"values": {}, "remove": ["action.strategy"]})
        await worker.install(removal)
        current = await worker.inspect()
        assert not any(m.name == "authored.action.strategy" for m in current.mechanisms)
        assert any(m.name == "code.plan" for m in current.mechanisms)
