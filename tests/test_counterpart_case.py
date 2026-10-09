"""The counterpart layer's delivery predicates: what a run's last round must have handed over, by scenario."""

from experimental.counterpart.case import deck_delivered, delivered_for, files_delivered


def round_with(*drills):
    return {
        "drills": [
            {"exchanges": [{"delivered": [{"name": name} for name in names]} for names in drill]} for drill in drills
        ]
    }


def test_a_deck_in_every_drill_is_what_the_deck_predicate_asks_and_any_file_what_the_file_one_asks():
    both = round_with([["plan.pptx"]], [["notes.md"], ["Deck.PPTX"]])
    assert deck_delivered(both) and files_delivered(both)
    documents = round_with([["plan.pptx"]], [["notes.md"]])
    assert not deck_delivered(documents) and files_delivered(documents)


def test_a_drill_without_a_file_fails_both_and_so_does_an_empty_round():
    assert not files_delivered(round_with([["a.md"]], [[]]))
    assert not deck_delivered(round_with([["a.pptx"]], [[]]))
    assert not files_delivered({"drills": []}) and not deck_delivered({})


def test_the_predicate_follows_the_scenario_name_and_defaults_to_the_deck():
    assert delivered_for("brand_strategist") is files_delivered
    assert delivered_for("travel_agency") is deck_delivered
    assert delivered_for(None) is deck_delivered
