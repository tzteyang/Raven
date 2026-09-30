"""Selected class helpers and native dependencies are checked against their actual callers."""

import pytest

from experimental.curator.raven_adapter.bind import conform
from experimental.curator.raven_adapter.calls import strategy_method
from experimental.curator.raven_adapter.inference import supplied
from experimental.curator.raven_adapter.planning.contracts import PlanReader
from experimental.curator.raven_adapter.targets import catalogue
from raven.contracts.tool_gate import ToolGate


class Gate:
    async def adjudicate(self, name, params, *, session_workdir=None):
        return None


class SyncGate:
    def adjudicate(self, name, params):
        return None


class NarrowGate:
    async def adjudicate(self, name, params=None):
        return None


def test_native_components_match_the_form_and_arguments_used_by_the_host():
    conform(Gate(), ToolGate)
    with pytest.raises(TypeError, match="must be async"):
        conform(SyncGate(), ToolGate)
    with pytest.raises(TypeError, match="does not accept the host's call"):
        conform(NarrowGate(), ToolGate)


def test_selected_helpers_are_real_methods_with_the_required_call_shape():
    class Owner:
        def _render_context(self, view):
            return f"View: {view}"

        async def _intake(self, request):
            return request.text

    owner = Owner()
    assert strategy_method(owner, "_render_context", 1)({"step": 1}) == "View: {'step': 1}"
    with pytest.raises(TypeError, match="synchronous"):
        strategy_method(owner, "_intake", 1)
    with pytest.raises(TypeError, match="must implement"):
        strategy_method(owner, "_missing", 1)
    with pytest.raises(TypeError):
        strategy_method(owner, "_render_context", 2)


def test_factories_receive_only_declared_keyword_dependencies():
    host, plan = object(), lambda: {"stage": "intake"}

    def factory(state, task, *, host, plan):
        return state, task, host, plan

    assert supplied(factory, {"host": host, "plan": plan}) == {"host": host, "plan": plan}
    with pytest.raises(TypeError, match="host-supplied keyword-only"):
        supplied(factory, {"plan": plan})

    def positional(state, task, host):
        return state, task, host

    with pytest.raises(TypeError, match="keyword-only"):
        supplied(positional, {"host": host})


def test_strategy_reading_path_includes_plan_access_and_preparation_consumers():
    for target in catalogue():
        assert PlanReader in target.knowledge or target.name == "planning.strategy"
        knowledge = target.describe()["knowledge"]
        assert any("Role-owned setup" in row["content"] for row in knowledge)
        assert any("PreparationRequest" in row["content"] for row in knowledge)
