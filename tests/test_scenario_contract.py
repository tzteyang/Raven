"""A scenario directory reads into the closed categories, every file claimed, and each item says who may see it."""

import json
import shutil
from pathlib import Path

import pytest

from experimental.scenario import KINDS, ROLES, VIEWS, Scenario, default_visibility, load
from experimental.scenario.contract import frontmatter
from experimental.scenario.sealed import sealed_for
from experimental.simulation.scenario import BUNDLED

TRAVEL = BUNDLED / "travel_agency"


def copy(tmp_path, name="travel_agency"):
    target = tmp_path / name
    shutil.copytree(TRAVEL, target)
    return target


def contract(root, **sections):
    path = root / "contract.json"
    data = json.loads(path.read_text()) if path.is_file() else {}
    for key, value in sections.items():
        if isinstance(value, dict) and isinstance(data.get(key), dict):
            data[key] = {**data[key], **value}
        else:
            data[key] = value
    path.write_text(json.dumps(data))


def held_back(root, *names):
    """Take materials out of what the party hands over, as the contract requires of one the partner may not receive."""
    path = root / "scenario.json"
    spec = json.loads(path.read_text())
    spec["initial"] = [name for name in spec.get("initial", []) if name not in names]
    spec["plans"] = {
        plan: [[name for name in step if name not in names] for step in steps]
        for plan, steps in spec.get("plans", {}).items()
    }
    path.write_text(json.dumps(spec))


def test_the_travel_agency_reads_into_the_categories_with_every_file_claimed():
    scenario = load(TRAVEL)
    assert isinstance(scenario, Scenario) and scenario.root == TRAVEL.resolve()
    assert len(scenario.situation.profile) > 100
    assert [case.id for case in scenario.situation.cases] == [
        "family",
        "premium",
        "professional",
        "returning",
        "student",
    ]
    family = scenario.situation.cases[0]
    assert family.values["nights"] == 4 and "budget" in family.values and family.expected is None
    assert family.text and not family.text.startswith("---")
    assert set(scenario.materials) == {
        "booking-policy",
        "brand-design-guide",
        "comfort-package",
        "consultation-scripts",
        "handover-ticket",
        "plan-deck-sample",
        "plan-deck-spec",
        "plan-deck-template",
        "premium-package",
        "price-list",
        "service-sop",
        "value-package",
    }
    assert {material.kind for material in scenario.materials.values()} <= set(KINDS)
    assert scenario.materials["plan-deck-sample"].kind == "exemplar"
    assert scenario.materials["price-list"].kind == "fact" and scenario.materials["price-list"].description
    assert scenario.statements.norms == ("booking-policy", "brand-design-guide", "plan-deck-spec", "service-sop")
    assert len(scenario.statements.checks) == 17
    quote = next(check for check in scenario.statements.checks if check.id == "quote-sheet-correct")
    assert quote.severity == "red_line" and quote.derived_from == ("service-sop", "booking-policy")
    assert scenario.exchange.initial[0] == "service-sop" and "by-stage" in scenario.exchange.plans
    assert scenario.exchange.observability == VIEWS and "{files}" in scenario.exchange.onboarding
    assert scenario.aids.rulers and scenario.aids.rulers.startswith("# ")
    assert scenario.aids.labels and scenario.prior.records == ()


@pytest.mark.parametrize(
    "item,expected",
    [
        ("profile", set(ROLES)),
        ("service-sop", {"partner", "party", "analyst", "curator"}),
        ("plan-deck-sample", {"partner", "party", "analyst", "curator"}),
        ("case:family", {"conversant", "party"}),
        ("case.expected:family", {"party", "analyst"}),
        ("check:quote-sheet-correct", {"party", "analyst"}),
        ("exchange", {"party"}),
        ("prior", {"party", "analyst"}),
        ("aids", {"party"}),
    ],
)
def test_default_visibility_keeps_the_standard_and_the_cases_from_the_partner_and_the_curator(item, expected):
    scenario = load(TRAVEL)
    assert {role for role in ROLES if scenario.visible(item, role)} == expected
    assert not scenario.visible("check:quote-sheet-correct", "curator")
    assert not scenario.visible("case:family", "partner")
    with pytest.raises(KeyError):
        scenario.visible("check:missing", "party")
    with pytest.raises(ValueError, match="unknown role"):
        scenario.visible("profile", "owner")


def test_the_contract_narrows_or_widens_visibility_per_item(tmp_path):
    root = copy(tmp_path)
    contract(
        root,
        materials={"price-list": {"kind": "fact", "visibility": ["party"]}, "plan-deck-sample": {"kind": "exemplar"}},
        checks={"deck-structure": {"derived_from": ["plan-deck-spec"], "visibility": ["party", "analyst", "curator"]}},
        cases={"student": {"expected": "A quote within the budget.", "visibility": ["conversant", "party", "analyst"]}},
        observability=["conversations", "deliverables"],
    )
    held_back(root, "price-list")
    scenario = load(root)
    assert not scenario.visible("price-list", "partner") and scenario.visible("price-list", "party")
    assert "price-list" in scenario.materials and "price-list" not in scenario.handed
    assert scenario.visible("check:deck-structure", "curator")
    student = next(case for case in scenario.situation.cases if case.id == "student")
    assert student.expected == "A quote within the budget." and scenario.visible("case:student", "analyst")
    assert scenario.exchange.observability == ("conversations", "deliverables")
    assert scenario.statements.norms == ("booking-policy", "brand-design-guide", "plan-deck-spec", "service-sop")
    assert default_visibility("check") == frozenset({"party", "analyst"})


@pytest.mark.parametrize(
    "spoil,message",
    [
        (lambda root: (root / "notes.txt").write_text("stray"), "outside every category"),
        (lambda root: (root / "personas" / "notes.txt").write_text("stray"), "personas/notes.txt"),
        (lambda root: contract(root, materials={"price-list": {"kind": "rule"}}), "unknown kind"),
        (lambda root: contract(root, materials={"nothing": {"kind": "fact"}}), "does not have"),
        (lambda root: contract(root, checks={"deck-structure": {"derived_from": ["price-list"]}}), "not norms"),
        (lambda root: contract(root, checks={"missing": {}}), "checks the scenario does not have"),
        (lambda root: contract(root, observability=["thoughts"]), "unknown observation views"),
        (
            lambda root: contract(root, materials={"price-list": {"kind": "fact", "visibility": ["owner"]}}),
            "unknown roles",
        ),
        (lambda root: contract(root, extra={}), "unknown sections"),
        (lambda root: (root / "profile.md").write_text(""), "profile is missing or empty"),
    ],
)
def test_a_scenario_outside_the_categories_is_refused(tmp_path, spoil, message):
    root = copy(tmp_path)
    spoil(root)
    with pytest.raises(ValueError, match=message):
        load(root)


def test_a_material_package_keeps_its_nested_files_inside_its_category(tmp_path):
    root = copy(tmp_path)
    (root / "materials" / "plan-deck-template" / "assets").mkdir()
    (root / "materials" / "plan-deck-template" / "assets" / "logo.png").write_bytes(b"png")
    assert load(root).materials["plan-deck-template"].path == root.resolve() / "materials" / "plan-deck-template"
    with pytest.raises(ValueError, match="not found"):
        load(tmp_path / "nowhere")


def test_a_document_handed_over_as_written_is_a_material_and_a_folder_without_one_is_not(tmp_path):
    from experimental.simulation.agency import attached
    from experimental.simulation.scenario import Scenario as Simulated

    root = copy(tmp_path)
    spec = json.loads((root / "scenario.json").read_text())
    (root / "scenario.json").write_text(json.dumps({key: value for key, value in spec.items() if key != "plans"}))
    profile = root / "materials" / "expert-profile"
    profile.mkdir()
    (profile / "travel-expert.md").write_text("---\nname: travel-expert\ndescription: The expert's profile\n---\nBody")
    broken = root / "materials" / "service-sop" / "SKILL.md"
    broken.write_text("---\ndescription: TL;DR: rules: steps\n---\n" + broken.read_text().split("---", 2)[2])
    (profile / "plugin.json").write_text("{}")
    contract(root, materials={"expert-profile": {"kind": "norm"}})
    loaded = load(root)
    assert loaded.materials["expert-profile"].kind == "norm"
    assert loaded.materials["expert-profile"].description == "The expert's profile"
    assert Simulated.load(root).text("expert-profile").endswith("Body")
    assert loaded.materials["service-sop"].description == ""
    handovers = attached(
        ["uploads/expert-profile/travel-expert.md", "uploads/service-sop/references/steps/a.md"],
        {"expert-profile": "norm", "service-sop": "norm"},
    )
    assert [(item.name, item.files) for item in handovers] == [
        ("expert-profile", ("uploads/expert-profile/travel-expert.md",)),
        ("service-sop", ("uploads/service-sop/references/steps/a.md",)),
    ]
    (profile / "second.md").write_text("Another document")
    with pytest.raises(ValueError, match=r"declares materials the scenario does not have: \['expert-profile'\]"):
        load(root)
    data = json.loads((root / "contract.json").read_text())
    del data["materials"]["expert-profile"]
    (root / "contract.json").write_text(json.dumps(data))
    with pytest.raises(ValueError, match="files outside every category"):
        load(root)


def test_a_relative_prior_is_read_from_the_scenario_directory_and_its_files_belong_to_it(tmp_path):
    root = copy(tmp_path)
    kept = root / "records" / "earlier" / "iteration" / "run.json"
    kept.parent.mkdir(parents=True)
    kept.write_text(json.dumps({"history": [], "rounds": []}))
    contract(root, prior=["records/earlier", "/absolute/run"])
    scenario = load(root)
    assert scenario.prior.records == (root.resolve() / "records/earlier", Path("/absolute/run"))
    contract(root, prior=[])
    with pytest.raises(ValueError, match="files outside every category"):
        load(root)


def test_scenario_json_refuses_a_misspelled_key_and_a_check_that_takes_a_loop_id(tmp_path):
    root = copy(tmp_path)
    spec = json.loads((root / "scenario.json").read_text())
    for spoiled, message in (
        ({**spec, "initail": spec["initial"]}, "initail"),
        ({**spec, "criteria": [{**spec["criteria"][0], "severty": "red_line"}]}, "severty"),
        ({**spec, "criteria": [{**spec["criteria"][0], "id": "R1"}]}, "form the loop gives"),
        ({**spec, "criteria": [{**spec["criteria"][0], "id": "derived-2"}]}, "form the loop gives"),
    ):
        (root / "scenario.json").write_text(json.dumps(spoiled))
        with pytest.raises(ValueError, match=message):
            load(root)


def test_frontmatter_is_only_a_leading_yaml_mapping_and_everything_else_is_body():
    assert frontmatter("---\nname: sop\ndescription: Rules\n---\nBody\n") == (
        {"name": "sop", "description": "Rules"},
        "Body",
    )
    ruled = "---\n# Price list\n\n| item | price |\n|---|---|\n| tea | 5 |\n"
    assert frontmatter(ruled) == ({}, ruled.strip())
    opened = "---\nIntro paragraph.\n---\nMore text."
    assert frontmatter(opened) == ({}, opened.strip())
    assert frontmatter("No frontmatter at all.") == ({}, "No frontmatter at all.")


def test_a_hidden_package_seals_its_data_files_too(tmp_path):
    root = copy(tmp_path)
    table = "season,price\nwinter family package for two adults and one child,26800 yuan per person all inclusive\n"
    (root / "materials" / "price-list" / "rates.csv").write_text(table)
    contract(root, materials={"price-list": {"kind": "fact", "visibility": ["party", "analyst"]}})
    held_back(root, "price-list")
    sealed = sealed_for(load(root), "curator")
    assert sealed.hits("Quote: winter family package for two adults and one child, 26800 yuan per person.")


def test_what_the_partner_may_not_receive_is_never_scheduled_to_be_handed_over(tmp_path):
    root = copy(tmp_path)
    contract(root, materials={"price-list": {"kind": "fact", "visibility": ["party"]}})
    with pytest.raises(ValueError, match="partner may not receive"):
        load(root)
    spec = json.loads((root / "scenario.json").read_text())
    spec["initial"] = [name for name in spec["initial"] if name != "price-list"]
    (root / "scenario.json").write_text(json.dumps(spec))
    with pytest.raises(ValueError, match="every material exactly once"):
        load(root)
    held_back(root, "price-list")
    assert "price-list" not in load(root).handed
