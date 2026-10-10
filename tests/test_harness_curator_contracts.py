"""Four code entrypoints, projected grants and owned asset updates share one checked schema."""

from dataclasses import replace
from importlib import import_module

import pytest
from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict

from experimental.harness.contract import Artifact, Change, Declaration, Plan, Target
from experimental.harness.contract.action import ActionDecision
from experimental.harness.contract.artifact import Selection
from experimental.harness.contract.attribution import Attributed, Attribution, Diagnosis
from experimental.harness.raven_adapter.materialize import extend_artifact
from experimental.harness.raven_adapter.preparation import ContextPolicy, GenerationPolicy, WindowPolicy
from experimental.harness.raven_adapter.targets import catalogue


@pytest.fixture
def host():
    return Declaration("worker:revision-0", catalogue())


def plan_for(*names):
    return Plan(
        understanding="Implement the observed requirement in its owning strategy.",
        design="Execute code-owned decisions through actual native consumers.",
        changes=tuple(
            Change(target=name, reason="Requirement", expected="Actual effect", verification="Observe execution")
            for name in names
        ),
    )


def validator(schema):
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def test_catalogue_exposes_only_four_strategy_implementations_and_preparation_knowledge(host):
    assert {target.name for target in host.targets} == {
        "memory.strategy",
        "planning.strategy",
        "capability.strategy",
        "action.strategy",
    }
    for row in host.describe():
        module, name = row["contract"].split(":")
        referenced = import_module(module)
        for part in name.split("."):
            referenced = getattr(referenced, part)
        assert referenced is host.target(row["target"]).contract
        validator(row["schema"])
        assert "factory" in row["schema"]["properties"]
        assert any(item["source"].endswith("pitfalls/artifact.md") for item in row["knowledge"])
        listed = {item["source"]: item for item in row["references"]}
        for source in ("preparation:PreparationRequest", "inference:StrategyInference"):
            item = next(item for name, item in listed.items() if name.endswith(source))
            assert item["purpose"] and item["chars"] > 0 and item["name"].startswith(f"{row['target']}.knowledge.")
        assert any(name.endswith("reference/inference.md") for name in listed)
        assert any(name.endswith("reference/preparation.md") for name in listed)
        target = host.target(row["target"])
        assert {item["name"] for item in row["references"]} <= set(target.sources())


@pytest.mark.parametrize(
    "name",
    [
        "memory.prompt",
        "memory.context_config",
        "memory.context_engine",
        "memory.backends",
        "memory.intake",
        "memory.archive",
        "planning.skills",
        "planning.playbooks",
        "planning.advise",
        "capability.resources",
        "capability.tools",
        "capability.mcp",
        "capability.plugins",
        "action.config",
        "action.review",
        "action.hooks",
        "action.tool_gates",
        "action.services",
        "prompt.resources",
    ],
)
def test_removed_native_payloads_are_not_alternative_submission_routes(host, name):
    with pytest.raises(ValueError, match="not granted"):
        host.target(name)
    assert not validator(host.plan_schema()).is_valid(plan_for(name).model_dump(mode="json"))


def test_model_and_host_reject_ungranted_strategy_selection(host):
    scope = host.restrict(["planning.strategy"])
    good = plan_for("planning.strategy").model_dump(mode="json")
    assert validator(scope.plan_schema()).is_valid(good)
    assert scope.parse_plan(good).changes[0].target == "planning.strategy"
    bad = plan_for("capability.strategy").model_dump(mode="json")
    assert not validator(scope.plan_schema()).is_valid(bad)
    with pytest.raises(ValueError, match="not granted"):
        scope.parse_plan(bad)


def test_field_and_event_grants_are_identical_in_submission_schema_and_parser(host):
    scope = host.restrict(
        ["action.strategy"], fields={"action.strategy": ["factory", "events"]}, phases={"action.strategy": ["input"]}
    )
    plan = plan_for("action.strategy")
    schema = validator(scope.artifact_schema(plan))
    good = {"values": {"action.strategy": {"factory": "policy:create", "events": ["input"]}}}
    schema.validate(good)
    scope.accept(plan, good)
    for payload in (
        {"factory": "policy:create", "events": ["proposal"]},
        {"factory": "policy:create", "events": ["input"], "requests": True},
        {"factory": "policy:create"},
    ):
        value = {"values": {"action.strategy": payload}}
        assert not schema.is_valid(value)
        with pytest.raises(ValueError):
            scope.accept(plan, value)
    with pytest.raises(ValueError, match="cannot add fields"):
        scope.restrict(["action.strategy"], fields={"action.strategy": ["factory", "requests"]})
    with pytest.raises(ValueError, match="cannot add phases"):
        scope.restrict(["action.strategy"], phases={"action.strategy": ["proposal"]})
    with pytest.raises(ValueError, match="required"):
        host.restrict(["action.strategy"], fields={"action.strategy": ["events"]})


def test_binding_cannot_carry_resources_or_native_configuration(host):
    for name, extra in (
        ("capability.strategy", {"resources": []}),
        ("action.strategy", {"temperature": 0.2}),
        ("memory.strategy", {"TOOLS.md": "Bypass"}),
    ):
        plan = plan_for(name)
        value = {"values": {name: {"factory": "policy:create", **extra}}}
        assert not validator(host.artifact_schema(plan)).is_valid(value)
        with pytest.raises(ValueError):
            host.accept(plan, value)


def test_selected_targets_and_artifact_payloads_cannot_diverge(host):
    plan = plan_for("memory.strategy")
    for value in (
        {"values": {}},
        {"values": {"capability.strategy": {"factory": "policy:create"}}},
        {"values": {"memory.strategy": {"factory": "policy:create"}}, "remove": ["memory.strategy"]},
    ):
        with pytest.raises(ValueError):
            host.accept(plan, value)
    with pytest.raises(ValueError, match="wrong artifact level"):
        host.accept(plan, {"memory.strategy": {"factory": "policy:create"}})


def test_baseline_and_narrowed_contract_identity_prevent_candidate_rebinding(host):
    candidate = host.accept(plan_for("action.strategy"), {"values": {"action.strategy": {"factory": "policy:create"}}})
    attributed = Attributed(
        attribution=Attribution(diagnoses=(Diagnosis(about="R1", state="absent", mechanism="none yet"),)),
        identity={"attributor": "model"},
    )
    chosen = Selection(
        understanding="Gate the tool.", targets=("action.strategy",), grounds={"action.strategy": ("R1",)}
    )
    checked = host.validate(replace(candidate, attribution=attributed, selection=chosen))
    assert (checked.attribution, checked.selection) == (attributed, chosen)
    with pytest.raises(ValueError, match="baseline"):
        replace(host, baseline="different").validate(candidate)
    with pytest.raises(ValueError, match="contract"):
        host.restrict(["action.strategy"], phases={"action.strategy": ["proposal"]}).validate(candidate)


def test_supporting_file_retirement_is_explicit_and_preserves_unmodified_owners(host):
    active = Artifact(
        values={
            "memory.strategy": {"factory": "memory:create"},
            "capability.strategy": {"factory": "capability:create"},
        },
        files={"memory.py": "old", "capability.py": "retained", "old.md": "old asset"},
    )
    update = host.accept(
        plan_for("memory.strategy"),
        {
            "values": {"memory.strategy": {"factory": "memory:create"}},
            "files": {"memory.py": "new"},
            "remove_files": ["old.md"],
        },
    )
    result = extend_artifact(active, update.artifact)
    assert result.files == {"memory.py": "new", "capability.py": "retained"}
    assert result.values["capability.strategy"] == active.values["capability.strategy"]
    assert active.files["old.md"] == "old asset"
    with pytest.raises(ValueError, match="not currently authored"):
        extend_artifact(active, Artifact(values={}, remove_files=("missing.md",)))
    with pytest.raises(ValueError):
        host.accept(plan_for(), {"values": {}, "remove_files": ["old.md"]})
    for kwargs in ({"remove_files": ["old.md", "old.md"]}, {"files": {"old.md": "new"}, "remove_files": ["old.md"]}):
        with pytest.raises(ValueError):
            Artifact(values={}, **kwargs)


@pytest.mark.parametrize("path", ["/absolute.py", "../outside.py", "x/../y.py", "x//y.py", "x\\y.py", "./x.py"])
def test_asset_paths_cannot_escape_the_authored_package(path):
    with pytest.raises(ValueError):
        Artifact(values={}, files={path: "source"})


def test_native_policy_slices_reject_parameters_owned_by_another_role():
    with pytest.raises(ValueError):
        ContextPolicy(pinned_skill_ids=["example"])
    with pytest.raises(ValueError):
        GenerationPolicy(memory_window=8)
    with pytest.raises(ValueError):
        WindowPolicy(temperature=0.2)
    assert GenerationPolicy(temperature=0.2).model_fields_set == {"temperature"}


def test_action_result_requires_meaningful_control_and_resample_only_parameters():
    with pytest.raises(ValueError):
        ActionDecision(control="revise")
    with pytest.raises(ValueError):
        ActionDecision(control="finish")
    with pytest.raises(ValueError):
        ActionDecision(generation={"temperature": 0.2})
    assert ActionDecision(control="continue").reply is None


def test_generic_result_validation_remains_typed_and_phase_limited():
    class Reply(BaseModel):
        model_config = ConfigDict(extra="forbid")
        accepted: bool

    target = Target(
        name="example.strategy",
        contract=Reply,
        binding="example.strategy",
        payload=Reply,
        channels=("execution_control",),
        effect="Typed result",
        result=Reply,
        phases=("proposal",),
    )
    assert target.parse_result({"accepted": True}, phase="proposal") == {"accepted": True}
    with pytest.raises(ValueError, match="phase not granted"):
        target.parse_result({"accepted": True}, phase="sent")
    with pytest.raises(ValueError):
        target.parse_result({"accepted": "yes"}, phase="proposal")


def test_listed_references_need_a_purpose_and_read_by_the_names_the_target_gives_them(host, tmp_path):
    from experimental.harness.contract.declaration import Reference

    page = tmp_path / "page.md"
    page.write_text("# Page\n\nbody\n")
    with pytest.raises(ValueError, match="needs a purpose"):
        Reference(page)
    with pytest.raises(ValueError, match="needs a purpose"):
        Reference(lambda: None)
    listed = Reference(page, "What the page answers; read when it matters.").describe()
    assert listed == {"source": str(page), "purpose": "What the page answers; read when it matters.", "chars": 13}
    for target in host.targets:
        names = list(target.sources())
        inlined, listed = names[: len(target.knowledge)], names[len(target.knowledge) :]
        described = target.describe()
        assert [row["name"] for row in described["references"]] == listed
        assert len(inlined) == len(described["knowledge"]) and len(set(names)) == len(names)
        assert all(name.startswith(f"{target.name}.knowledge.") for name in names)
        assert not {row["source"] for row in described["knowledge"]} & {
            row["source"] for row in described["references"]
        }
