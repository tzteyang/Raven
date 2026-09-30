"""When the party hands each material over: the disclosure schedule of one cultivation.

The contract declares what a scenario allows (`Exchange.initial` and the named `Exchange.plans`); a run chooses one,
and `Disclosure.of` turns that choice into the one rule every party follows. `all` hands everything over at
onboarding; `staged` hands over the initial set, then whatever the party chooses with each review; a named plan or an
explicit partition gives step 0 at onboarding and step k with the review of round k. With `rounds`, whatever is still
withheld is due with the review before the last round, so the last round tries a partner that has everything.

The schedule is the party's: the loop never reads it and only carries what the party hands over
(`Signal.attachments`), so a person in the Studio and the simulated owner follow the same schedule the same way.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass


def partition(steps, materials: Iterable[str]) -> tuple[tuple[str, ...], ...]:
    """`steps` as a partition of `materials`: every material exactly once, and something at onboarding."""
    steps, materials = tuple(tuple(step) for step in steps), set(materials)
    named = [name for step in steps for name in step]
    if not steps or not steps[0]:
        raise ValueError("a partition gives something at onboarding")
    if len(named) != len(set(named)) or set(named) != materials:
        raise ValueError(f"a partition must give every material exactly once; materials: {sorted(materials)}")
    return steps


@dataclass(frozen=True)
class Disclosure:
    """`plan` names the choice (`all`, `staged`, a plan's name, or `partition`); `opening` is handed over at
    onboarding, `steps[k]` with the review of round k; `chooses` says the party picks what else to hand over."""

    plan: str
    materials: tuple[str, ...]
    opening: tuple[str, ...]
    steps: tuple[tuple[str, ...], ...] = ()
    chooses: bool = False
    rounds: int | None = None

    @classmethod
    def of(
        cls,
        plan,
        *,
        materials: Iterable[str],
        initial: Iterable[str] = (),
        plans: Mapping[str, tuple[tuple[str, ...], ...]] | None = None,
        rounds: int | None = None,
    ) -> "Disclosure":
        """The schedule `plan` gives over `materials`: `all`, `staged` (from `initial`), a name in `plans`, or a
        partition given as steps."""
        materials, plans = tuple(materials), plans or {}
        if plan == "all":
            return cls("all", materials, materials, rounds=rounds)
        if plan == "staged":
            unknown = set(initial) - set(materials)
            if unknown:
                raise ValueError(f"the initial release names materials the scenario does not have: {sorted(unknown)}")
            return cls("staged", materials, tuple(initial), chooses=True, rounds=rounds)
        if isinstance(plan, str):
            if plan not in plans:
                raise ValueError(f"the scenario has no plan named {plan}: {sorted(plans)}")
            name, steps = plan, plans[plan]
        else:
            name, steps = "partition", plan
        steps = partition(steps, materials)
        if rounds is not None and len(steps) > rounds:
            raise ValueError(f"a partition of {len(steps)} steps does not finish before the last of {rounds} rounds")
        return cls(name, materials, steps[0], steps, rounds=rounds)

    def due(self, review: int, released: Iterable[str] = ()) -> list[str]:
        """What the schedule hands over with the review of round `review`, leaving out what is already released,
        whatever the party chooses besides."""
        released = set(released)
        due = list(self.steps[review]) if review < len(self.steps) else []
        if self.rounds is not None and review >= self.rounds - 1:
            due += [name for name in self.materials if name not in due]
        return [name for name in due if name not in released]

    def record(self) -> dict:
        """The schedule as the run settings keep it."""
        return {
            "plan": self.plan,
            "opening": list(self.opening),
            "steps": [list(step) for step in self.steps],
            "chooses": self.chooses,
            "rounds": self.rounds,
        }
