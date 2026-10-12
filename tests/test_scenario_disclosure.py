"""The disclosure schedule is one rule over the contract's plans, whichever counterpart follows it."""

import json
import shutil

import pytest

from experimental.harness.scenario import Disclosure, Plan, load
from experimental.harness.scenario.disclosure import partition
from experimental.simulation.bench.scenario import BUNDLED

TRAVEL = BUNDLED / "travel_agency"


def test_every_choice_gives_its_opening_and_the_rest_is_due_before_the_last_round():
    read = load(TRAVEL)
    materials, initial, plans = tuple(read.materials), read.exchange.initial, read.exchange.plans
    everything = Disclosure.of("all", materials=materials, rounds=3)
    assert everything.opening == materials and not everything.chooses and everything.due(2, materials) == []
    staged = Disclosure.of("staged", materials=materials, initial=initial, rounds=3)
    later = [name for name in materials if name not in initial]
    assert staged.opening == initial and staged.chooses
    assert staged.due(1, initial) == [] and staged.due(2, [*initial, later[0]]) == later[1:]
    stage = plans["by-stage"].steps
    named = Disclosure.of("by-stage", materials=materials, plans=plans, rounds=4)
    assert (named.plan, named.opening, named.steps, named.chooses) == ("by-stage", stage[0], stage, False)
    assert named.labels == plans["by-stage"].labels and len(named.labels) == len(stage)
    assert named.due(1, stage[0]) == list(stage[1]) and named.due(3, [*stage[0], *stage[1]]) == list(stage[2])
    assert named.step_of(stage[2][0]) == 2 and named.step_of("not-a-material") is None
    assert named.record() == {
        "plan": "by-stage",
        "opening": list(stage[0]),
        "steps": [list(step) for step in stage],
        "labels": list(plans["by-stage"].labels),
        "chooses": False,
        "rounds": 4,
        "completes": True,
    }
    given = Disclosure.of(stage, materials=materials)
    assert given.plan == "partition" and given.labels == ()


def test_none_hands_nothing_over_and_a_schedule_may_be_asked_not_to_complete():
    materials = tuple(load(TRAVEL).materials)
    nothing = Disclosure.of("none", materials=materials, rounds=3)
    assert nothing.opening == () and nothing.steps == () and not nothing.chooses and not nothing.completes
    assert nothing.due(0) == [] and nothing.due(2) == [] and nothing.due(5) == []
    assert nothing.record()["plan"] == "none" and nothing.record()["completes"] is False
    kept = Disclosure.of("staged", materials=materials, initial=materials[:2], rounds=3, completes=False)
    assert kept.chooses and not kept.completes and kept.due(2, materials[:2]) == []
    completed = Disclosure.of("staged", materials=materials, initial=materials[:2], rounds=3)
    assert completed.completes and completed.due(2, materials[:2]) == list(materials[2:])


def test_a_plan_labels_every_step_or_none():
    plan = Plan((("a", "b"), ("c",)), ("first", "second"))
    assert plan.without(["b"]).steps == (("a",), ("c",)) and plan.without(["b"]).labels == ("first", "second")
    assert plan.record() == {"steps": [["a", "b"], ["c"]], "labels": ["first", "second"]}
    assert Plan((("a",), ("b",))).labels == ()
    with pytest.raises(ValueError, match="labels every step or none"):
        Plan((("a",), ("b",)), ("only one",))


def test_a_schedule_gives_every_material_once_from_onboarding_and_finishes_before_the_last_round():
    materials = tuple(load(TRAVEL).materials)
    with pytest.raises(ValueError, match="exactly once"):
        partition((materials[:-1],), materials)
    with pytest.raises(ValueError, match="exactly once"):
        partition((materials, materials[:1]), materials)
    with pytest.raises(ValueError, match="onboarding"):
        partition(((), materials), materials)
    with pytest.raises(ValueError, match="before the last"):
        Disclosure.of(tuple((name,) for name in materials), materials=materials, rounds=4)
    with pytest.raises(ValueError, match="no plan named later"):
        Disclosure.of("later", materials=materials, plans={})
    with pytest.raises(ValueError, match="does not have"):
        Disclosure.of("staged", materials=materials[1:], initial=materials[:1])


def test_the_contract_refuses_a_plan_that_is_not_a_schedule_or_mislabels_its_steps(tmp_path):
    root = tmp_path / "travel_agency"
    shutil.copytree(TRAVEL, root)
    spec = json.loads((root / "scenario.json").read_text())
    spec["plans"]["by-stage"]["steps"] = spec["plans"]["by-stage"]["steps"][1:]
    spec["plans"]["by-stage"]["labels"] = spec["plans"]["by-stage"]["labels"][1:]
    (root / "scenario.json").write_text(json.dumps(spec))
    with pytest.raises(ValueError, match="plan by-stage: .*onboarding|plan by-stage: .*exactly once"):
        load(root)
    spec = json.loads((TRAVEL / "scenario.json").read_text())
    spec["plans"]["by-stage"]["labels"] = spec["plans"]["by-stage"]["labels"][:1]
    (root / "scenario.json").write_text(json.dumps(spec))
    with pytest.raises(ValueError, match="labels every step or none"):
        load(root)
