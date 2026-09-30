"""Native Raven adaptation preserves grants, resources and observable result semantics."""

import json
import os
from pathlib import Path

import pytest

from experimental.curator.harness import Artifact, Declaration, Target, Task
from experimental.curator.raven_adapter.bind import assemble
from experimental.curator.raven_adapter.content import ContentInstallation
from experimental.curator.raven_adapter.inspection import (
    Baseline,
    Inspection,
    declaration_for,
    file_source,
    redact,
)
from experimental.curator.raven_adapter.materialize import load_factory, native_settings, write_package
from experimental.curator.raven_adapter.observe import Recorder
from experimental.curator.raven_adapter.preparation import PreparedHarness, describe_preparation
from experimental.curator.raven_adapter.targets import catalogue
from raven.config.raven import RavenConfig
from raven.config.schema import Config
from raven.contracts.llm_provider import LLMResponse
from raven.contracts.participant import AgentParticipant, StepView
from raven.spine.turn import Origin


@pytest.fixture
def declaration():
    return Declaration("worker", catalogue())


@pytest.fixture
def baseline(tmp_path):
    config = Config()
    config.agents.defaults.workspace = str(tmp_path / "agent")
    return Baseline(config, RavenConfig(memory={"backend": None}), tmp_path)


def step(phase="iteration"):
    return StepView(
        session_key="s",
        iteration=1,
        response=LLMResponse(content="original"),
        transcript=({"role": "assistant", "content": [{"text": "original"}]},),
        history=(),
        turn_base=0,
        question="task",
        rollbacks=0,
        mode=None,
        mode_overlay=None,
        phase=phase,
    )


def test_configuration_patches_preserve_defaults_and_share_the_native_base(baseline, declaration):
    old_model = baseline.config.agents.defaults.model
    prepared = PreparedHarness(
        config={"agents": {"defaults": {"temperature": 0}}},
        extensions={"context": {"drop_segments": ["memory"]}, "skill_forge": {"enabled": False}},
    )
    effective = native_settings(baseline, prepared)
    assert effective.config.agents.defaults.temperature == 0
    assert effective.config.agents.defaults.model == old_model
    assert not effective.extensions.skill_forge.enabled
    assert effective.extensions.base is effective.config
    assert baseline.extensions.skill_forge.enabled
    assert baseline.config.agents.defaults.temperature != 0


def test_an_authored_disabled_tools_list_adds_to_the_hosts_and_never_enables_a_tool_it_disabled(baseline, declaration):
    """e2e0925h onboarding: the Curator disabled the browser tools and its list replaced the host's, so the employee
    got exec, web_search, web_fetch and ask_user back."""
    baseline.config.tools.disabled_tools = ["exec", "ask_user"]
    prepared = PreparedHarness(config={"tools": {"disabled_tools": ["deep_research", "exec"]}})
    effective = native_settings(baseline, prepared)
    assert effective.config.tools.disabled_tools == ["exec", "ask_user", "deep_research"]
    assert baseline.config.tools.disabled_tools == ["exec", "ask_user"]


def test_owned_content_rollback_restores_files_symlinks_and_permissions(tmp_path, declaration):
    home = tmp_path / "home"
    home.mkdir()
    outside = tmp_path / "template.md"
    outside.write_text("shared template")
    target = home / "TOOLS.md"
    target.symlink_to(outside)
    script = home / "skills" / "old" / "run.sh"
    script.parent.mkdir(parents=True)
    script.write_text("old")
    script.chmod(0o755)
    prepared = PreparedHarness(
        content={
            "memory": {
                "TOOLS.md": "new",
                "skills/old/run.sh": "new script",
                "skills/new/SKILL.md": "new skill",
            }
        }
    )
    transaction = ContentInstallation(home, tmp_path / "runtime", prepared, Recorder(tmp_path / "events.jsonl"))
    transaction.apply()
    assert not target.is_symlink()
    assert target.read_text() == "new"
    assert outside.read_text() == "shared template"
    assert script.stat().st_mode & 0o777 == 0o755
    transaction.rollback()
    assert target.is_symlink() and target.read_text() == "shared template"
    assert script.read_text() == "old"
    assert script.stat().st_mode & 0o777 == 0o755
    assert not (home / "skills/new/SKILL.md").exists()


def test_content_writes_reject_an_escaping_parent(tmp_path, declaration):
    home = tmp_path / "home"
    home.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (home / "skills").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="escapes"):
        ContentInstallation(
            home,
            tmp_path / "runtime",
            PreparedHarness(content={"memory": {"skills/new/SKILL.md": "text"}}),
            Recorder(tmp_path / "events.jsonl"),
        )


def test_generated_packages_do_not_reuse_a_previous_modules_code(tmp_path):
    first = Artifact(
        values={},
        files={"factory.py": "from .helper import VALUE\ndef make(): return VALUE", "helper.py": "VALUE = 'first'"},
    )
    second = Artifact(values={}, files={"factory.py": first.files["factory.py"], "helper.py": "VALUE = 'second'"})
    one = write_package(tmp_path, first)
    two = write_package(tmp_path, second)
    assert load_factory("factory:make", one)() == "first"
    assert load_factory("factory:make", two)() == "second"
    (one / "helper.py").write_text("VALUE = 'changed'")
    with pytest.raises(ValueError, match="content changed"):
        write_package(tmp_path, first)


def test_source_search_and_paging_cover_long_lines_and_detect_staleness(tmp_path):
    path = tmp_path / "source.py"
    original = "x" * 26000 + "NEEDLE\n"
    path.write_text(original)
    view = Inspection(Declaration("b", ()), {}, {"source": file_source(path)})
    first = view.read_source("source", length=24000)
    second = view.read_source("source", offset=first["next_offset"])
    assert first["text"] + second["text"] == original.rstrip("\n")
    found = view.read_source("source", find="NEEDLE")
    assert "NEEDLE" in found["matches"][0]["text"]
    with pytest.raises(ValueError, match="unknown source"):
        view.read_source("../outside")
    path.write_text("changed")
    with pytest.raises(ValueError, match="source changed"):
        view.read_source("source")


def test_redaction_preserves_operational_settings_and_removes_secrets():
    value = {
        "apiKey": "secret",
        "context_window_tokens": 8192,
        "env": {"TOKEN": "secret", "MODE": "local"},
        "headers": {"Authorization": "secret"},
    }
    safe = redact(value)
    assert safe["apiKey"] == "<configured>"
    assert safe["context_window_tokens"] == 8192
    assert "secret" not in str(safe)
    assert value["apiKey"] == "secret"


def test_empty_authority_is_not_reopened_by_default():
    assert declaration_for("b", {}, names=[]).targets == ()


def test_origin_and_residency_limits_come_from_the_actual_native_path(baseline):
    """Raven's turn path runs the inbound hook and the after_send chain for user, cron and heartbeat turns, and
    skips both for sentinel and subagent turns, whose output is system-originated."""
    for origin in Origin:
        baseline.origin = origin
        support = describe_preparation(baseline)
        assert support["input"] == support["archive"] == (origin not in {Origin.SENTINEL, Origin.SUBAGENT})
    baseline.resident = False
    support = describe_preparation(baseline)
    assert not support["resident_services"] and not support["session_retirement"]


def test_unknown_bindings_are_rejected_before_loading_code(tmp_path, baseline):
    target = Target("action.future", AgentParticipant.review, "unknown.binding", dict, (), "unknown")
    declaration = Declaration("b", (target,))
    root = tmp_path / "runtime"
    with pytest.raises(ValueError, match="unsupported authoring entry"):
        assemble(
            baseline, Artifact(values={"action.future": {}}), declaration, root, Recorder(tmp_path / "records.jsonl")
        )
    assert not root.exists()


@pytest.mark.asyncio
async def test_model_pool_bindings_keep_native_settings_and_emit_observations(tmp_path):
    from experimental.curator.raven_adapter.observe import ObservedPool
    from raven.providers.binding import ModelBinding

    class Provider:
        async def chat_with_retry(self, **kwargs):
            return LLMResponse(content="pinned result")

    provider = Provider()
    binding = ModelBinding(provider, "pinned/model", configured_window=8000)

    class Pool:
        def bind(self, *args):
            return binding

        def bind_pin(self, *args):
            return binding if args[0] else None

    recorder = Recorder(tmp_path / "records.jsonl")
    pool = ObservedPool(Pool(), recorder)
    observed = pool.bind("pinned/model")
    assert observed.model == binding.model and observed.configured_window == binding.configured_window
    assert pool.bind_pin(None) is None
    answer = await observed.provider.chat_with_retry(messages=[])
    assert answer.content == "pinned result"
    assert [row["kind"] for row in recorder.rows] == ["provider.request", "provider.response"]


@pytest.mark.parametrize("inside", ["home", "work"])
def test_validation_copy_preserves_directory_relationships_and_excludes_itself(tmp_path, inside):
    from experimental.curator.raven_adapter.materialize import copy_local_state

    outer = tmp_path / "outer"
    outer.mkdir()
    inner = outer / "inner"
    inner.mkdir()
    home, work = (inner, outer) if inside == "home" else (outer, inner)
    (inner / "existing.txt").write_text("existing")
    config = Config()
    config.agents.defaults.workspace = str(home)
    baseline = Baseline(config, RavenConfig(), work)
    destination = outer / "validation"
    destination.mkdir()
    copied = copy_local_state(baseline, destination)
    if inside == "home":
        assert copied.config.workspace_path == copied.workdir / "inner"
        assert (copied.config.workspace_path / "existing.txt").read_text() == "existing"
    else:
        assert copied.workdir == copied.config.workspace_path / "inner"
        assert (copied.workdir / "existing.txt").read_text() == "existing"
    assert not list(destination.rglob("validation"))
    assert baseline.workdir == work


def test_a_reference_to_a_module_missing_from_the_package_says_where_its_source_belongs(tmp_path):
    package = write_package(tmp_path, Artifact(values={}, files={"helpers.py": "VALUE = 1\n"}))
    with pytest.raises(ModuleNotFoundError, match=r"holds helpers\.py.*files\['planning_impl\.py'\]"):
        load_factory("planning_impl:create", package)
    other = write_package(tmp_path / "other", Artifact(values={}, files={"uses.py": "import missing_dependency\n"}))
    with pytest.raises(ModuleNotFoundError, match="No module named 'missing_dependency'$"):
        load_factory("uses:create", other)


async def test_returned_provider_error_is_visible_to_execution_error_consumers(tmp_path):
    from experimental.curator.raven_adapter.observe import ObservedProvider, Recorder
    from experimental.curator.raven_adapter.worker import Execution
    from raven.contracts.llm_provider import LLMResponse

    class Failed:
        async def chat(self, **kwargs):
            return LLMResponse(content="Upstream rejected the continuation", finish_reason="error")

    recorder = Recorder(tmp_path / "observations.jsonl")
    response = await ObservedProvider(Failed(), recorder).chat(messages=[])
    execution = Execution("turn", [], recorder.rows, {})
    assert response.finish_reason == "error"
    assert execution.errors[0]["error"] == "Upstream rejected the continuation"
    assert any(row["kind"] == "provider.response" for row in execution.records)


def test_execution_errors_preserve_child_failure_attribution():
    from experimental.curator.raven_adapter.worker import Execution

    nested = {
        "kind": "child.execution",
        "harness": "Research",
        "revision": "child-v2",
        "records": [
            {"kind": "provider.error", "turn_id": "child-turn", "error": "Connection lost"},
        ],
    }
    errors = Execution("root-turn", [], [nested], {}).errors
    assert errors == [
        {
            "kind": "provider.error",
            "turn_id": "child-turn",
            "error": "Connection lost",
            "harness": "Research",
            "revision": "child-v2",
        }
    ]
    assert "harness" not in nested["records"][0]


@pytest.mark.asyncio
async def test_file_roots_confine_the_native_file_tools_and_keep_disabled_ones_absent(tmp_path):
    from types import SimpleNamespace

    from experimental.curator.raven_adapter.bind import _confine_files
    from raven.agent.tools.deliver import DeliverFilesTool
    from raven.agent.tools.filesystem import ReadFileTool, WriteFileTool
    from raven.agent.tools.registry import ToolRegistry, call_failed

    home, shared, handed, elsewhere = (tmp_path / name for name in ("home", "shared", "handed", "elsewhere"))
    for folder in (home, shared, handed, elsewhere):
        folder.mkdir()
        (folder / "note.md").write_text(f"written in {folder.name}\n")
    registry = ToolRegistry()
    registry.register(ReadFileTool(workspace=home))
    registry.register(WriteFileTool(workspace=home))
    store = object()
    registry.register(DeliverFilesTool(store, workspace=home))
    loop = SimpleNamespace(workspace=home, tools=registry, deliverables=store)
    _confine_files(SimpleNamespace(loop=loop), (shared.resolve(),), (handed.resolve(),))
    assert registry.get("edit_file") is None and registry.get("grep") is None
    for folder in (home, shared, handed):
        assert f"written in {folder.name}" in await registry.execute("read_file", {"path": str(folder / "note.md")})
    refused = await registry.execute("read_file", {"path": str(elsewhere / "note.md")})
    assert call_failed(refused) and "written in elsewhere" not in str(refused)
    await registry.execute("write_file", {"path": str(shared / "made.md"), "content": "by the child"})
    assert (shared / "made.md").read_text() == "by the child"
    refused = await registry.execute("write_file", {"path": str(handed / "made.md"), "content": "by the child"})
    assert call_failed(refused) and not (handed / "made.md").exists()
    assert registry.get("deliver_files")._allowed_dirs == (home.resolve(), shared.resolve(), handed.resolve())


def test_a_copied_baseline_moves_its_file_roots_with_the_copy_and_with_its_parents(tmp_path):
    from experimental.curator.raven_adapter.materialize import copy_local_state, remap_paths

    parent_home, parent_work = tmp_path / "parent" / "home", tmp_path / "parent" / "work"
    home, work = parent_home / "subagents" / "child", tmp_path / "child-work"
    for folder in (parent_home / "uploads", parent_work, home / "own", work):
        folder.mkdir(parents=True)
    config = Config()
    config.agents.defaults.workspace = str(home)
    baseline = Baseline(
        config,
        RavenConfig(),
        work,
        file_roots=(parent_work, home / "own"),
        read_roots=(parent_home, tmp_path / "outside"),
    )
    copied_parent = tmp_path / "copy" / "parent"
    copied = copy_local_state(
        baseline,
        tmp_path / "copy" / "child",
        remap=((parent_home, copied_parent / "home"), (parent_work, copied_parent / "work")),
    )
    assert copied.file_roots == ((copied_parent / "work").resolve(), copied.config.workspace_path / "own")
    assert copied.read_roots == ((copied_parent / "home").resolve(), (tmp_path / "outside").resolve())
    assert remap_paths((parent_home / "uploads",), ((parent_home, copied_parent / "home"),)) == (
        (copied_parent / "home" / "uploads").resolve(),
    )
    assert Baseline.restore(copied.export()).read_roots == copied.read_roots


@pytest.mark.parametrize("name", ["raven-code", "raven-research", "raven-oncall", "raven-design", "raven-ppt"])
def test_existing_agent_preparation_reuses_renderer_and_isolates_host_environment(tmp_path, name):
    from experimental.curator.raven_adapter.baselines.agents import prepare_agent
    from raven.config.mode_catalogue import build_mode_catalogue

    host = tmp_path / "host"
    host.mkdir()
    (host / "config.json").write_text(
        json.dumps(
            {
                "agents": {"defaults": {"model": "openai/gpt-4o-mini", "provider": "openrouter"}},
                "providers": {"openrouter": {"apiKey": "synthetic-key"}},
            }
        )
    )
    root = tmp_path / "prepared"
    directory = Path(__file__).resolve().parents[1] / "agents" / name
    previous = dict(os.environ)
    baseline = prepare_agent(
        directory,
        root=root,
        workdir=tmp_path,
        task=Task(id="task", text="Inspect"),
        environment={"RAVEN_HOME": str(host), "RESEARCH_SERPER_API_KEY": "synthetic-search-key"},
    )
    assert os.environ == previous
    assert baseline.source_roots == (directory,)
    assert baseline.config.workspace_path.is_relative_to(root)
    assert baseline.task.id == "task"
    assert build_mode_catalogue(baseline.config).get(baseline.mode) is not None
    assert (root / "prepared.json").stat().st_mode & 0o777 == 0o600
    if name in {"raven-code", "raven-oncall", "raven-research"}:
        assert str(directory / "plugins") in baseline.extensions.plugins.dirs
