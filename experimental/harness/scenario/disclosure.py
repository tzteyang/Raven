"""When the counterpart hands each material over: the disclosure schedule of one cultivation.

The contract declares what a scenario allows (`Exchange.initial` and the named `Exchange.plans`); a run chooses one,
and `Disclosure.of` turns that choice into the one rule every counterpart follows. `all` hands everything over at
onboarding; `none` hands nothing over, ever, so the partner works from the profile and the conversations alone;
`staged` hands over the initial set, then whatever the counterpart chooses with each review; a named plan or an
explicit partition gives step 0 at onboarding and step k with the review of round k. With `rounds`, a schedule that
`completes` hands whatever is still withheld over with the review before the last round, so the last round tries a
partner that has everything; `none` never completes, and a run may ask any other schedule not to.

A named plan may label its steps (`Plan.labels`), so a record says what each step was meant to give, not just which
files; the labels are the case's own words and change nothing about the schedule.

The schedule is the counterpart's: the loop never reads it and only carries what the counterpart hands over
(`Signal.attachments`), so a person in the Studio and the simulated owner follow the same schedule the same way.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

KINDS = ("all", "none", "staged")


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
class Plan:
    """A named partition of the materials into steps, each step optionally labelled with what it is meant to give."""

    steps: tuple[tuple[str, ...], ...]
    labels: tuple[str, ...] = ()

    def __post_init__(self):
        steps = tuple(tuple(step) for step in self.steps)
        labels = tuple(self.labels)
        if labels and len(labels) != len(steps):
            raise ValueError(f"a plan labels every step or none; {len(steps)} steps, {len(labels)} labels")
        object.__setattr__(self, "steps", steps)
        object.__setattr__(self, "labels", labels)

    def without(self, names: Iterable[str]) -> "Plan":
        """The plan with these materials left out of every step; the labels stay with their steps."""
        names = set(names)
        return Plan(tuple(tuple(name for name in step if name not in names) for step in self.steps), self.labels)

    def record(self) -> dict:
        return {"steps": [list(step) for step in self.steps], "labels": list(self.labels)}


@dataclass(frozen=True)
class Disclosure:
    """`plan` names the choice (`all`, `none`, `staged`, a plan's name, or `partition`); `opening` is handed over at
    onboarding, `steps[k]` with the review of round k; `chooses` says the counterpart picks what else to hand over;
    `completes` says whatever is still withheld is due with the review before the last of `rounds`."""

    plan: str
    materials: tuple[str, ...]
    opening: tuple[str, ...]
    steps: tuple[tuple[str, ...], ...] = ()
    labels: tuple[str, ...] = ()
    chooses: bool = False
    rounds: int | None = None
    completes: bool = True

    @classmethod
    def of(
        cls,
        plan,
        *,
        materials: Iterable[str],
        initial: Iterable[str] = (),
        plans: Mapping[str, Plan] | None = None,
        rounds: int | None = None,
        completes: bool = True,
    ) -> "Disclosure":
        """The schedule `plan` gives over `materials`: `all`, `none`, `staged` (from `initial`), a name in `plans`,
        or a partition given as steps."""
        materials, plans = tuple(materials), plans or {}
        if plan == "all":
            return cls("all", materials, materials, rounds=rounds, completes=completes)
        if plan == "none":
            return cls("none", materials, (), rounds=rounds, completes=False)
        if plan == "staged":
            unknown = set(initial) - set(materials)
            if unknown:
                raise ValueError(f"the initial release names materials the scenario does not have: {sorted(unknown)}")
            return cls("staged", materials, tuple(initial), chooses=True, rounds=rounds, completes=completes)
        if isinstance(plan, str):
            if plan not in plans:
                raise ValueError(f"the scenario has no plan named {plan}: {sorted(plans)}")
            name, steps, labels = plan, plans[plan].steps, plans[plan].labels
        else:
            name, steps, labels = "partition", plan, ()
        steps = partition(steps, materials)
        if rounds is not None and len(steps) > rounds:
            raise ValueError(f"a partition of {len(steps)} steps does not finish before the last of {rounds} rounds")
        return cls(name, materials, steps[0], steps, labels, rounds=rounds, completes=completes)

    def due(self, review: int, released: Iterable[str] = ()) -> list[str]:
        """What the schedule hands over with the review of round `review`, leaving out what is already released,
        whatever the counterpart chooses besides."""
        released = set(released)
        due = list(self.steps[review]) if review < len(self.steps) else []
        if self.completes and self.rounds is not None and review >= self.rounds - 1:
            due += [name for name in self.materials if name not in due]
        return [name for name in due if name not in released]

    def step_of(self, material: str) -> int | None:
        """The step that hands `material` over, 0 being onboarding; None when the schedule never names it."""
        return next((index for index, step in enumerate(self.steps) if material in step), None)

    def record(self) -> dict:
        """The schedule as the run settings keep it."""
        return {
            "plan": self.plan,
            "opening": list(self.opening),
            "steps": [list(step) for step in self.steps],
            "labels": list(self.labels),
            "chooses": self.chooses,
            "rounds": self.rounds,
            "completes": self.completes,
        }
