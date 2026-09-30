"""Each category of a handed-over scenario is one slot, and a gap says how it could be filled."""

from experimental.research import slots
from experimental.scenario import load
from tests.test_research_induction import make_scenario


def by_category(scenario):
    return {slot.category: slot for slot in slots(scenario)}


def test_with_instances_the_norms_are_inducible_and_missing_facts_are_researchable(tmp_path):
    found = by_category(load(make_scenario(tmp_path / "shop", facts=False)))
    assert list(found) == [
        "profile",
        "cases",
        "norms",
        "facts",
        "exemplars",
        "counterexamples",
        "checks",
        "wording",
        "prior",
    ]
    assert (found["norms"].given, found["norms"].gap) == (("sop",), "inducible")
    assert (found["facts"].given, found["facts"].gap) == ((), "researchable")
    assert (found["exemplars"].given, found["counterexamples"].given) == (("good-reply",), ("bad-reply",))
    assert (found["checks"].given, found["checks"].gap) == (("quote-total",), None)
    assert all(found[category].gap is None for category in ("profile", "cases", "wording", "prior"))


def test_without_instances_the_norms_are_no_gap_and_a_missing_standard_only_the_party_can_give(tmp_path):
    found = by_category(load(make_scenario(tmp_path / "shop", instances=False, checks=False)))
    assert (found["norms"].gap, found["facts"].gap) == (None, None)
    assert (found["checks"].given, found["checks"].gap) == ((), "party")


def test_with_neither_norms_nor_instances_the_trades_practice_is_researchable(tmp_path):
    found = by_category(load(make_scenario(tmp_path / "shop", norms=False, instances=False)))
    assert (found["norms"].given, found["norms"].gap) == ((), "researchable")
    assert found["facts"].gap is None


def test_a_fact_the_party_holds_back_leaves_the_facts_slot_to_research(tmp_path):
    from experimental.research import package

    source = make_scenario(tmp_path / "shop")
    package.copy(load(source), tmp_path / "handed", ["prices"])
    found = by_category(load(tmp_path / "handed"))
    assert (found["facts"].given, found["facts"].gap) == ((), "researchable")
