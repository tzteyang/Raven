"""What a run is judged by that differs between cases: the delivery predicate.

`deck_delivered` and `files_delivered` are the two predicates the value judge (`experimental.simulation.bench.value`) holds a
run's last round to: a deck in every drill for the travel agency, a delivered file in every drill for a case whose
deliverables are documents. `delivered_for` picks one by the scenario's name.
"""

from collections.abc import Callable

DECK = ".pptx"


def _delivered_files(item: dict):
    for drill in item.get("drills", []):
        yield (
            drill,
            [str(file.get("name", "")) for turn in drill.get("exchanges", []) for file in turn.get("delivered", [])],
        )


def deck_delivered(item: dict) -> bool:
    """Every drill of the round handed over a deck."""
    drills = list(_delivered_files(item))
    return bool(drills) and all(any(name.lower().endswith(DECK) for name in names) for _, names in drills)


def files_delivered(item: dict) -> bool:
    """Every drill of the round handed over at least one file."""
    drills = list(_delivered_files(item))
    return bool(drills) and all(names for _, names in drills)


# Scenarios whose deliverables are documents rather than decks; the deck is the judge's historical default, so a
# record without a scenario name (an older record, a synthetic one) is still judged as the travel agency's.
DELIVERED: dict[str, Callable[[dict], bool]] = {"brand_strategist": files_delivered}


def delivered_for(scenario: str | None) -> Callable[[dict], bool]:
    """The delivery predicate a scenario is judged by: a file in every drill for a document case, else a deck."""
    return DELIVERED.get(scenario or "", deck_delivered)
