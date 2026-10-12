"""Playing a case's cards: a conversant per card and repeat, grouped into trials of a bounded size."""

import pytest

from experimental.simulation.bench.drills import enlist, grouped


class Card:
    def __init__(self, name):
        self.name = name
        self.values = {}


def test_enlist_names_a_conversant_per_card_and_repeat_with_the_prefix():
    cards = [Card("proposal"), Card("watch")]
    once = enlist(cards, provider=None)
    assert list(once) == ["proposal", "watch"] and once["watch"].persona is cards[1]
    twice = enlist(cards, provider=None, repeats=2, prefix="holdout-", model="m", effort="low", timeout=5, seed=3)
    assert list(twice) == ["holdout-proposal-1", "holdout-proposal-2", "holdout-watch-1", "holdout-watch-2"]
    last = twice["holdout-watch-2"]
    assert (last.model, last.effort, last.timeout, last.seed) == ("m", "low", 5, 3)


def test_grouped_plays_at_most_size_conversations_together_with_the_turn_budget():
    conversants = enlist([Card(f"c{index}") for index in range(5)], provider=None)
    placed = {}
    spawn = object()
    groups = grouped(conversants, spawn, size=2, turns=4, placed=placed)
    assert [list(group.trials) for group in groups] == [["c0", "c1"], ["c2", "c3"], ["c4"]]
    assert all(trial.max_turns == 4 for group in groups for trial in group.trials.values())
    assert all(group.spawn is spawn and group.placed is placed for group in groups)
    with pytest.raises(ValueError):
        grouped(conversants, spawn, size=0, turns=4)
