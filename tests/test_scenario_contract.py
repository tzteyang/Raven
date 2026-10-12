"""A scenario directory reads into the closed categories, every file claimed, and each item says who may see it."""

import json
import shutil
from pathlib import Path

import pytest

from experimental.harness.scenario import KINDS, ROLES, VIEWS, Scenario, default_visibility, load
from experimental.harness.scenario.contract import frontmatter
from experimental.harness.scenario.sealed import sealed_for
from experimental.simulation.bench.scenario import BUNDLED

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
    """Take materials out of what the counterpart hands over, as the contract requires of one the partner may not receive."""
    path = root / "scenario.json"
    spec = json.loads(path.read_text())
    spec["initial"] = [name for name in spec.get("initial", []) if name not in names]
    spec["plans"] = {
        name: {**plan, "steps": [[item for item in step if item not in names] for step in plan["steps"]]}
        for name, plan in spec.get("plans", {}).items()
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
        ("service-sop", {"partner", "counterpart", "analyst", "curator"}),
        ("plan-deck-sample", {"partner", "counterpart", "analyst", "curator"}),
        ("case:family", {"conversant", "counterpart"}),
        ("case.expected:family", {"counterpart", "analyst"}),
        ("check:quote-sheet-correct", {"counterpart", "analyst"}),
        ("exchange", {"counterpart"}),
        ("prior", {"counterpart", "analyst"}),
        ("aids", {"counterpart"}),
    ],
)
def test_default_visibility_keeps_the_standard_and_the_cases_from_the_partner_and_the_curator(item, expected):
    scenario = load(TRAVEL)
    assert {role for role in ROLES if scenario.visible(item, role)} == expected
    assert not scenario.visible("check:quote-sheet-correct", "curator")
    assert not scenario.visible("case:family", "partner")
    with pytest.raises(KeyError):
        scenario.visible("check:missing", "counterpart")
    with pytest.raises(ValueError, match="unknown role"):
        scenario.visible("profile", "owner")


def test_the_contract_narrows_or_widens_visibility_per_item(tmp_path):
    root = copy(tmp_path)
    contract(
        root,
        materials={
            "price-list": {"kind": "fact", "visibility": ["counterpart"]},
            "plan-deck-sample": {"kind": "exemplar"},
        },
        checks={
            "deck-structure": {"derived_from": ["plan-deck-spec"], "visibility": ["counterpart", "analyst", "curator"]}
        },
        cases={
            "student": {
                "expected": "A quote within the budget.",
                "visibility": ["conversant", "counterpart", "analyst"],
            }
        },
        observability=["conversations", "deliverables"],
    )
    held_back(root, "price-list")
    scenario = load(root)
    assert not scenario.visible("price-list", "partner") and scenario.visible("price-list", "counterpart")
    assert "price-list" in scenario.materials and "price-list" not in scenario.handed
    assert scenario.visible("check:deck-structure", "curator")
    student = next(case for case in scenario.situation.cases if case.id == "student")
    assert student.expected == "A quote within the budget." and scenario.visible("case:student", "analyst")
    assert scenario.exchange.observability == ("conversations", "deliverables")
    assert scenario.statements.norms == ("booking-policy", "brand-design-guide", "plan-deck-spec", "service-sop")
    assert default_visibility("check") == frozenset({"counterpart", "analyst"})


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
    from experimental.simulation.bench.scenario import Scenario as Simulated
    from experimental.simulation.cases.travel_agency.owner import attached

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


def test_a_lab_folder_belongs_to_the_machine_it_is_placed_on_and_is_never_a_material(tmp_path):
    root = tmp_path / "travel_agency"
    shutil.copytree(TRAVEL, root)
    (root / "lab").mkdir()
    (root / "lab" / "console.py").write_text("print('reading')\n")
    (root / "lab" / "readings.md").write_text("| at | value |\n|---|---|\n| 0 | 12 |\n")
    read = load(root)
    assert not any(material.path.is_relative_to(root / "lab") for material in read.materials.values())
    (root / "labs").mkdir()
    (root / "labs" / "stray.md").write_text("stray")
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
    contract(root, materials={"price-list": {"kind": "fact", "visibility": ["counterpart", "analyst"]}})
    held_back(root, "price-list")
    sealed = sealed_for(load(root), "curator")
    assert sealed.hits("Quote: winter family package for two adults and one child, 26800 yuan per person.")


def test_what_the_partner_may_not_receive_is_never_scheduled_to_be_handed_over(tmp_path):
    root = copy(tmp_path)
    contract(root, materials={"price-list": {"kind": "fact", "visibility": ["counterpart"]}})
    with pytest.raises(ValueError, match="partner may not receive"):
        load(root)
    spec = json.loads((root / "scenario.json").read_text())
    spec["initial"] = [name for name in spec["initial"] if name != "price-list"]
    (root / "scenario.json").write_text(json.dumps(spec))
    with pytest.raises(ValueError, match="every material exactly once"):
        load(root)
    held_back(root, "price-list")
    assert "price-list" not in load(root).handed


def _with_card_file(tmp_path):
    root = tmp_path / "travel_agency"
    shutil.copytree(TRAVEL, root)
    (root / "handouts").mkdir()
    (root / "handouts" / "itinerary.md").write_text("Saturday: lake walk, Sunday: tea farm.\n")
    card = root / "personas" / "family.md"
    head, body = frontmatter(card.read_text())
    card.write_text("---\n" + json.dumps({**head, "files": ["handouts/itinerary.md"]}) + "\n---\n" + body)
    return root


def test_a_card_hands_over_files_of_the_scenario_which_are_claimed_and_visible_to_everyone(tmp_path):
    root = _with_card_file(tmp_path)
    read = load(root)
    (family,) = [case for case in read.situation.cases if case.id == "family"]
    assert family.files == ("handouts/itinerary.md",)
    assert not sealed_for(read, "partner").hits("Saturday: lake walk, Sunday: tea farm.")
    card = root / "personas" / "family.md"
    head, body = frontmatter(card.read_text())
    card.write_text("---\n" + json.dumps({**head, "files": ["handouts/missing.md"]}) + "\n---\n" + body)
    with pytest.raises(ValueError, match="hands over a file the scenario does not have"):
        load(root)
    card.write_text("---\n" + json.dumps({**head, "files": ["../outside.md"]}) + "\n---\n" + body)
    with pytest.raises(ValueError, match="hands over a file the scenario does not have"):
        load(root)
    card.write_text("---\n" + json.dumps({k: v for k, v in head.items() if k != "files"}) + "\n---\n" + body)
    with pytest.raises(ValueError, match="files outside every category"):
        load(root)


@pytest.mark.parametrize(
    ("schedule", "message"),
    [
        ({"rounds": [["family"], ["nobody"]]}, "does not have"),
        ({"rounds": [["family"], []]}, "at least one case"),
        ({"rounds": [["family"]], "holdout": ["family"]}, "not also played"),
        ({"rounds": [["family"]], "holdout_rounds": [1]}, "holds cases out"),
        ({"rounds": [["family"]], "holdout": ["returning"], "holdout_rounds": [-1]}, "0 before onboarding"),
    ],
)
def test_a_schedule_names_known_cases_plays_something_each_round_and_keeps_the_exam_apart(tmp_path, schedule, message):
    root = tmp_path / "travel_agency"
    shutil.copytree(TRAVEL, root)
    spec = json.loads((root / "scenario.json").read_text())
    (root / "scenario.json").write_text(json.dumps({**spec, "schedule": schedule}))
    with pytest.raises(ValueError, match=message):
        load(root)
    (root / "scenario.json").write_text(
        json.dumps(
            {
                **spec,
                "schedule": {
                    "rounds": [["family"], ["student", "premium"]],
                    "holdout": ["returning"],
                    "holdout_rounds": [0, 2],
                },
            }
        )
    )
    read = load(root).situation.schedule
    assert (read.round(1), read.round(2), read.round(5), read.holdout, read.holdout_rounds) == (
        ("family",),
        ("student", "premium"),
        ("student", "premium"),
        ("returning",),
        (0, 2),
    )


def test_a_card_may_carry_its_expected_answer_which_only_the_evaluation_side_may_receive(tmp_path):
    root = tmp_path / "travel_agency"
    shutil.copytree(TRAVEL, root)
    card = root / "personas" / "family.md"
    head, body = frontmatter(card.read_text())
    answer = "The quote totals 18,420 yuan for the party, insurance excluded, valid for 48 hours from the quote time."
    card.write_text("---\n" + json.dumps({**head, "expected": answer}) + "\n---\n" + body)
    read = load(root)
    (family,) = [case for case in read.situation.cases if case.id == "family"]
    assert family.expected == answer
    assert read.visible("case.expected:family", "counterpart") and read.visible("case.expected:family", "analyst")
    assert not read.visible("case.expected:family", "curator") and not read.visible("case.expected:family", "partner")
    assert not any(sealed_for(read, role).hits(f"Done: {answer}") for role in ("partner", "curator", "analyst"))
    (root / "contract.json").write_text(
        json.dumps({**json.loads((root / "contract.json").read_text()), "cases": {"family": {"expected": answer}}})
    )
    with pytest.raises(ValueError, match="expected answer twice"):
        load(root)


def test_a_held_out_case_keeps_its_handed_over_files_from_whoever_improves_the_partner(tmp_path):
    root = _with_card_file(tmp_path)
    scenario = json.loads((root / "scenario.json").read_text())
    played = [path.stem for path in (root / "personas").glob("*.md") if path.stem != "family"]
    scenario["schedule"] = {"rounds": [played], "holdout": ["family"]}
    (root / "scenario.json").write_text(json.dumps(scenario))
    read = load(root)
    text = "Saturday: lake walk, Sunday: tea farm."
    assert not sealed_for(read, "partner").hits(text) and not sealed_for(read, "counterpart").hits(text)
    assert sealed_for(read, "curator").hits(text) and sealed_for(read, "analyst").hits(text)


def test_explicit_check_applicability_reaches_the_counterpart_view(tmp_path):
    from experimental.cultivation.counterpart.scenario import Scenario as CounterpartScenario

    root = copy(tmp_path)
    path = root / "scenario.json"
    spec = json.loads(path.read_text())
    condition = "Only when a customer asks for a group booking."
    spec["criteria"][0]["applies_when"] = condition
    path.write_text(json.dumps(spec))
    assert load(root).statements.checks[0].applies_when == condition
    assert CounterpartScenario.of(load(root)).criteria[0].applies_when == condition
