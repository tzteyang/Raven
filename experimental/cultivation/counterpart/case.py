"""What a run is judged by that differs between cases: the delivery predicate.

`deck_delivered` and `files_delivered` are the two predicates a value judge can hold a run's last round to: a deck
in every drill for a case whose deliverable is a deck, a delivered file in every drill for a case whose deliverables
are documents. Which case takes which is the bench's knowledge (`experimental.simulation.bench.value`).
"""

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
