"""Candidate capability lifetimes, complete packages and native installation boundaries."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from experimental.curator.harness import Artifact, Task
from experimental.curator.harness.preparation import PreparationRequest
from experimental.curator.harness.resources import SkillContribution, SkillPackage, ToolContribution
from experimental.curator.raven_adapter.capability.catalog import CapabilityCatalog, inspect_package
from experimental.curator.raven_adapter.capability.contracts import CapabilityBinding
from experimental.curator.raven_adapter.capability.runtime import BoundCapability
from experimental.curator.raven_adapter.materialize import write_package
from experimental.curator.raven_adapter.observe import Recorder
from raven.agent.tools.registry import ToolRegistry
from raven.config.raven import RavenConfig
from raven.contracts.tool import Tool
from raven.memory_engine.skill_local.registry import SkillRegistry


class ProbeTool(Tool):
    name = "remember"
    description = "Read the current isolated owner."
    parameters = {"type": "object", "properties": {}, "additionalProperties": False}

    def __init__(self, owner):
        self.owner = owner

    async def execute(self, **kwargs):
        return self.owner()["value"]


def catalog(tmp_path, *, candidate="first", resolver=None):
    package = write_package(tmp_path / "package", Artifact(values={}, files={}))
    return CapabilityCatalog(
        candidate,
        package,
        tmp_path / "assembly",
        material_base=tmp_path,
        material_roots=(tmp_path / "uploads",),
        resolve_interaction=resolver,
    )


def native_runtime(tmp_path, resources, config):
    registry = SkillRegistry(
        tmp_path / "home",
        builtin_skills_dir=tmp_path / "no-builtins",
        extra_dirs=[(Path(row.path), row.name, False) for row in config.skill_forge.local_dirs],
    )
    return SimpleNamespace(
        loop=SimpleNamespace(
            tools=ToolRegistry(),
            context=SimpleNamespace(skills=SimpleNamespace(registry=registry)),
        )
    )


@pytest.mark.parametrize("method, missing", [("register", "contribution"), ("select", "return")])
def test_missing_annotations_report_the_actual_strategy_operation(tmp_path, method, missing):
    from tests.fixtures.harness_curator.authoring import CAPABILITY

    code = CAPABILITY
    if method == "register":
        code = code.replace("contribution: CapabilityContribution", "contribution")
    else:
        code = code.replace(" -> CapabilitySelection:", ":")
    package = write_package(tmp_path / "authored", Artifact(values={}, files={"policy.py": code}))
    with pytest.raises(TypeError, match=f"capability.{method} requires concrete annotations for: {missing}"):
        BoundCapability(
            CapabilityBinding(factory="policy:create"),
            Task(text="Describe invalid annotations."),
            tmp_path / "state.json",
            package,
            Recorder(tmp_path / "records.jsonl"),
            catalog=catalog(tmp_path),
        )


@pytest.mark.parametrize("adopt", [False, True])
def test_strategy_preparation_controls_whether_packaged_skill_assets_become_active(tmp_path, adopt):
    code = f"""from experimental.curator.harness.preparation import PreparationRequest
from experimental.curator.harness.resources import (
    CapabilityContribution, CapabilitySelection, RegistrationReceipt,
    SelectionRequest, SkillContribution,
)
from experimental.curator.harness.strategies import CapabilityStrategy

class Policy(CapabilityStrategy):
    def __init__(self, registrar):
        self.registrar = registrar

    def _prepare_skills(self, request: PreparationRequest) -> tuple[SkillContribution, ...]:
        if not {adopt!r}:
            return ()
        return (SkillContribution(
            name="evidence", source="Owner material",
            files={{name.removeprefix("skill/"): text for name, text in request.assets.items()
                   if name.startswith("skill/")}},
        ),)

    def register(self, contribution: CapabilityContribution) -> RegistrationReceipt:
        return self.registrar.register(contribution)

    async def select(self, request: SelectionRequest) -> CapabilitySelection:
        return CapabilitySelection()

def create(state, task, *, registrar):
    return Policy(registrar)
"""
    artifact = Artifact(
        values={},
        files={
            "policy.py": code,
            "skill/SKILL.md": "---\nname: evidence\ndescription: Inspect supplied evidence.\n---\nRead references/fact.md.",
            "skill/references/fact.md": "The verification code is amber-72.",
        },
    )
    package = write_package(tmp_path / "authored", artifact)
    resources = catalog(tmp_path)
    task = Task(text="Use only adopted evidence.")
    owner = BoundCapability(
        CapabilityBinding(factory="policy:create"),
        task,
        tmp_path / "state.json",
        package,
        Recorder(tmp_path / "records.jsonl"),
        catalog=resources,
    )
    assert resources.skills == {}
    owner.prepare_candidate(PreparationRequest(harness_id="test", revision="first", task=task, assets=artifact.files))
    config = RavenConfig()
    resources.stage(config)
    runtime = native_runtime(tmp_path, resources, config)
    resources.install(runtime)
    discovered = runtime.loop.context.skills.registry.list_all()
    assert [row.name for row in discovered] == (["evidence"] if adopt else [])
    if adopt:
        assert (discovered[0].path.parent / "references/fact.md").read_text() == "The verification code is amber-72."
    assert owner.state == {}


@pytest.mark.parametrize("status", ["unchanged", "staged"])
def test_policy_receipts_cannot_forge_registration_or_bypass_closure(tmp_path, status):
    code = f"""from experimental.curator.harness.strategies import CapabilityStrategy
from experimental.curator.harness.resources import (
    CapabilityContribution, RegistrationReceipt, SelectionRequest, CapabilitySelection,
)
class Policy(CapabilityStrategy):
    def __init__(self, registrar):
        self.registrar = registrar
        self.calls = 0
    def register(self, contribution: CapabilityContribution) -> RegistrationReceipt:
        self.calls += 1
        if {status!r} == "staged":
            self.registrar.register(contribution)
        return RegistrationReceipt(
            kind=contribution.kind, name=contribution.name, owner=contribution.owner,
            candidate=self.registrar.candidate, status={status!r},
        )
    async def select(self, request: SelectionRequest) -> CapabilitySelection:
        return CapabilitySelection()
def create(state, task, *, registrar):
    return Policy(registrar)
"""
    package = write_package(tmp_path / "authored", Artifact(values={}, files={"policy.py": code}))
    resources = catalog(tmp_path, resolver=lambda _: ProbeTool(lambda: {"value": "valid"}))
    owner = BoundCapability(
        CapabilityBinding(factory="policy:create"),
        Task(text="Register valid resources."),
        tmp_path / "state.json",
        package,
        Recorder(tmp_path / "records.jsonl"),
        catalog=resources,
    )
    contribution = ToolContribution(name="remember", owner="memory", interaction="memory.interact")
    if status == "staged":
        assert owner.register(contribution).status == "staged"
    before = dict(resources.contributions)
    with pytest.raises(ValueError, match="registration receipt|report unchanged"):
        owner.register(contribution)
    assert resources.contributions == before
    calls = owner.strategy.calls
    resources.closed = True
    assert owner.register(contribution).status == "rejected"
    assert owner.strategy.calls == calls


@pytest.mark.asyncio
async def test_registration_is_staged_and_invocation_uses_the_active_owner(tmp_path):
    current = {"value": "before"}
    resolutions = []

    def resolve(operation):
        resolutions.append(operation)
        return ProbeTool(lambda: current)

    resources = catalog(tmp_path, resolver=resolve)
    contribution = ToolContribution(name="remember", owner="memory", interaction="memory.interact")
    config = RavenConfig()
    runtime = native_runtime(tmp_path, resources, config)
    assert resources.register(contribution).status == "staged"
    assert runtime.loop.tools.get("remember") is None
    assert resources.register(contribution).status == "unchanged"
    assert resolutions == ["memory.interact"]
    resources.stage(config)
    resources.install(runtime)
    current = {"value": "after"}
    assert await runtime.loop.tools.execute("remember", {}) == "after"
    assert resources.register(contribution).status == "rejected"
    assert resources.facts()["installed"]


def test_identity_conflict_does_not_replace_a_staged_handler(tmp_path):
    original = ProbeTool(lambda: {"value": "original"})
    resources = catalog(tmp_path, resolver=lambda _: original)
    first = ToolContribution(name="remember", owner="memory", interaction="memory.interact")
    second = ToolContribution(name="remember", owner="action", interaction="action.handle_request")
    assert resources.register(first).status == "staged"
    refusal = resources.register(second)
    assert refusal.status == "rejected" and "conflicts" in refusal.reason
    assert resources.tools["remember"] is original


def test_adopted_package_preserves_binary_nested_and_empty_resources_without_execution(tmp_path):
    source = tmp_path / "uploads" / "evidence"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text(
        "---\nname: evidence\ndescription: Read supplied evidence.\n---\nRead references/data.bin.\n"
    )
    (source / "references").mkdir()
    (source / "references/data.bin").write_bytes(bytes(range(256)))
    (source / "empty").mkdir()
    (source / "scripts").mkdir()
    sentinel = tmp_path / "executed"
    script = source / "scripts/check.sh"
    script.write_text(f"#!/bin/sh\ntouch {sentinel}\n")
    script.chmod(0o755)
    inspected = inspect_package(source)
    resources = catalog(tmp_path)
    receipt = resources.register(
        SkillContribution(
            name="evidence",
            source="Owner-provided package",
            package=SkillPackage(root="uploads/evidence", digest=inspected["digest"]),
        )
    )
    assert receipt.status == "staged"
    config = RavenConfig()
    resources.stage(config)
    installed = resources.skill_root / "evidence"
    assert (installed / "references/data.bin").read_bytes() == bytes(range(256))
    assert (installed / "empty").is_dir()
    assert (installed / "scripts/check.sh").stat().st_mode & 0o777 == 0o755
    assert not sentinel.exists()
    runtime = native_runtime(tmp_path, resources, config)
    resources.install(runtime)
    assert [row.name for row in runtime.loop.context.skills.registry.list_all()] == ["evidence"]
    assert not sentinel.exists()


def test_revision_uses_the_new_complete_skill_set_and_keeps_the_previous_source(tmp_path):
    def skill(name, content):
        return SkillContribution(
            name=name,
            source="Supplied task requirements",
            files={"SKILL.md": f"---\nname: {name}\ndescription: Task procedure.\n---\n{content}\n"},
        )

    first = catalog(tmp_path)
    for item in (skill("alpha", "Original"), skill("beta", "Retire this")):
        assert first.register(item).status == "staged"
    first_config = RavenConfig()
    first.stage(first_config)
    original = first.skill_root
    second = catalog(tmp_path, candidate="second")
    assert second.register(skill("alpha", "Corrected")).status == "staged"
    second_config = RavenConfig()
    second.stage(second_config)
    current = native_runtime(tmp_path, second, second_config)
    second.install(current)
    assert [row.name for row in current.loop.context.skills.registry.list_all()] == ["alpha"]
    assert "Corrected" in current.loop.context.skills.registry.get_body("alpha")
    assert second.skill_root != original
    assert (original / "beta/SKILL.md").is_file()
    assert "Original" in (original / "alpha/SKILL.md").read_text()


def test_changed_package_and_outside_source_are_refused_before_materialization(tmp_path):
    source = tmp_path / "uploads" / "input"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text("Supplied procedure")
    digest = inspect_package(source)["digest"]
    (source / "SKILL.md").write_text("Changed after inspection")
    resources = catalog(tmp_path)
    changed = resources.register(
        SkillContribution(
            name="input",
            source="Input",
            package=SkillPackage(root="uploads/input", digest=digest),
        )
    )
    assert changed.status == "rejected" and "changed" in changed.reason
    outside = resources.register(
        SkillContribution(
            name="outside",
            source="Unregistered input",
            package=SkillPackage(root="../outside", digest=digest),
        )
    )
    assert outside.status == "rejected" and "material roots" in outside.reason
    assert resources.contributions == {} and resources.skills == {}
    assert not (tmp_path / "assembly/capability-skills").exists()


def test_native_tool_conflict_is_checked_before_any_candidate_tool_is_registered(tmp_path):
    def resolve(operation):
        tool = ProbeTool(lambda: {"value": "candidate"})
        tool.name = "free" if operation == "memory.interact" else "occupied"
        return tool

    resources = catalog(tmp_path, resolver=resolve)
    assert (
        resources.register(ToolContribution(name="free", owner="memory", interaction="memory.interact")).status
        == "staged"
    )
    assert (
        resources.register(
            ToolContribution(name="occupied", owner="action", interaction="action.handle_request")
        ).status
        == "staged"
    )
    config = RavenConfig()
    resources.stage(config)
    runtime = native_runtime(tmp_path, resources, config)
    original = ProbeTool(lambda: {"value": "native"})
    original.name = "occupied"
    runtime.loop.tools.register(original)
    with pytest.raises(ValueError, match="replace an existing"):
        resources.install(runtime)
    assert runtime.loop.tools.get("free") is None
    assert runtime.loop.tools.get("occupied") is original
    assert not resources.installed


def test_symlink_package_entries_are_rejected_without_following_them(tmp_path):
    source = tmp_path / "uploads/input"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text("Procedure")
    (source / "external").symlink_to(tmp_path / "private")
    with pytest.raises(ValueError, match="symlinks"):
        inspect_package(source)
