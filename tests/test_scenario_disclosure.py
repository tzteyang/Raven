"""The disclosure schedule is one rule over the contract's plans, whichever party follows it."""

import json
import shutil

import pytest

from experimental.scenario import Disclosure, load
from experimental.scenario.disclosure import partition
from experimental.simulation.scenario import BUNDLED

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
    stage = plans["by-stage"]
    named = Disclosure.of("by-stage", materials=materials, plans=plans, rounds=4)
    assert (named.plan, named.opening, named.steps, named.chooses) == ("by-stage", stage[0], stage, False)
    assert named.due(1, stage[0]) == list(stage[1]) and named.due(3, [*stage[0], *stage[1]]) == list(stage[2])
    assert named.record() == {
        "plan": "by-stage",
        "opening": list(stage[0]),
        "steps": [list(step) for step in stage],
        "chooses": False,
        "rounds": 4,
    }
    assert Disclosure.of(stage, materials=materials).plan == "partition"


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


def test_the_contract_refuses_a_plan_that_is_not_a_schedule(tmp_path):
    root = tmp_path / "travel_agency"
    shutil.copytree(TRAVEL, root)
    spec = json.loads((root / "scenario.json").read_text())
    spec["plans"]["by-stage"] = spec["plans"]["by-stage"][1:]
    (root / "scenario.json").write_text(json.dumps(spec))
    with pytest.raises(ValueError, match="plan by-stage: .*onboarding|plan by-stage: .*exactly once"):
        load(root)
