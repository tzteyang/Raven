"""Scenario preparation consumes an explicit release and keeps evaluation and adoption separate."""

import json

import pytest

from experimental.iteration.compartment import BoundaryError
from experimental.research.scenario import (
    opening_feedback,
    release_guard,
    released_materials,
    scenario_request,
    stage_released,
)
from experimental.scenario import load
from experimental.scenario.digest import digest
from experimental.simulation.scenario import Scenario
from tests.research_helpers import CHECK, make_scenario


def test_only_released_materials_are_staged_without_rewriting_the_scenario(tmp_path):
    source = load(make_scenario(tmp_path / "shop"))
    before = digest(source.root)
    home = tmp_path / "worker"
    staged = stage_released(source, ("prices",), home)
    assert len(staged) == 1 and staged[0].name == "prices"
    assert {path.name for path in (home / "uploads").iterdir()} == {"prices"}
    assert digest(source.root) == before
    request = scenario_request(source, ("prices",))
    assert set(request.context["materials"]) == {"prices"}
    assert CHECK not in request.model_dump_json()
    with pytest.raises(ValueError, match="not available"):
        released_materials(source, ("owner-policy",))


def test_later_disclosed_material_and_checks_stay_sealed(tmp_path):
    source = load(make_scenario(tmp_path / "shop"))
    guard = release_guard(source, ("prices",))
    guard.check("Tea costs three. Cake costs five.", "released")
    with pytest.raises(BoundaryError):
        guard.check("Greet the customer and quote from the price list only.", "future")
    with pytest.raises(BoundaryError):
        guard.check(CHECK, "evaluation")


def test_given_reference_is_not_automatically_a_standing_norm(tmp_path):
    root = make_scenario(tmp_path / "shop")
    (root / "provenance.json").write_text(json.dumps({"materials": {"sop": {"origin": "given", "confirmed": False}}}))
    source = load(root)
    assert not source.confirmed("sop")
    assert "sop" not in Scenario.of(source).standing_norms(("sop",))
    assert scenario_request(source, ("sop",)).context["materials"]["sop"]["adopted"] is False


def test_offline_opening_matches_the_actual_dialog_handover(tmp_path):
    from experimental.iteration.hearing import heard
    from experimental.simulation.agency import Agency

    source = load(make_scenario(tmp_path / "shop"))
    owner = Agency(
        Scenario.of(source),
        None,
        tmp_path / "home/skills",
        workdir=tmp_path,
        uploads=tmp_path / "home/uploads",
        disclosure=Scenario.of(source).disclosure("two"),
    )
    owner.prepare()
    assert opening_feedback(source, owner.released) == {"signals": heard(owner.opening())}
