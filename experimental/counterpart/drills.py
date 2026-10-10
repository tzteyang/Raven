"""Playing a case's cards: one conversant per card, each conversation on its own replica of the worker.

`enlist` makes the conversants, one per card and repeat, on the given model; `grouped` wraps them in conversations
and groups the conversations so that at most `size` play at once (`experimental.automation.employee.Together`), each
on a replica `spawn` makes. The same two steps serve the round's drills and the held-out ones.
"""

from experimental.automation.employee import Together
from experimental.automation.traveller import Traveller
from experimental.iteration.conversation import Conversation


def enlist(
    cards, provider, *, repeats=1, prefix="", model=None, effort=None, timeout=120, seed=0, boundaries=None
) -> dict[str, Traveller]:
    """A conversant per card and repeat, keyed by its name (`prefix` and a repeat suffix keep names apart)."""
    enlisted = {}
    for card in cards:
        for repeat in range(1, repeats + 1):
            conversant = Traveller(
                card,
                provider,
                name=f"{prefix}{card.name}" + (f"-{repeat}" if repeats > 1 else ""),
                model=model,
                effort=effort,
                timeout=timeout,
                seed=seed,
                boundaries=boundaries,
            )
            enlisted[conversant.name] = conversant
    return enlisted


def grouped(conversants: dict, spawn, *, size: int, turns: int, placed: dict | None = None) -> list[Together]:
    """Conversations of at most `turns` messages, played `size` at a time on replicas; `placed` receives where each
    played (see `Together`)."""
    if size < 1:
        raise ValueError("drills play at least one at a time")
    named = [(name, Conversation(conversant, max_turns=turns)) for name, conversant in conversants.items()]
    return [Together(dict(named[start : start + size]), spawn, placed) for start in range(0, len(named), size)]
