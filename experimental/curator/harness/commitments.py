"""Harness commitments: the Curator's standing statement of what a Harness does, one strategy surface per entry.

A commitment sits between the inputs a curation answers (requirement ids, handed-over materials, the reviewed
information, routed node requirements, the task) and the code of the four strategy surfaces: what one surface does,
in which situation, from what input and with what effect. A curation changes the list through operations (add,
modify, retire) instead of restating it: omitted entries stay as they are, ids are never reused, and a retired entry
keeps its reason. `native` names behavior the host provides without authored code that authored code relies on or
could stop. `check_design` holds the operations to the selected targets and their grounds, and `check_artifact`
holds the submitted artifact to the resulting list.
"""

import re
from collections.abc import Iterable, Mapping
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from experimental.audience import CURATOR, RECORD_ONLY

NATIVE = "native"
# Input keys that follow a version or a routing order: a commitment citing one may point at an input that has since
# changed. Requirement ids, materials and the task keep their meaning across rounds.
VOLATILE_INPUTS = ("information:", "node:")
_ID = re.compile(r"^H([1-9]\d*)$")


class Commitment(BaseModel):
    """What one strategy surface of the Harness does, for the inputs it serves; `retired` holds the reason it was
    withdrawn, and a retired entry stays so its id is never given again."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    # The Curator reads current entries only; the reason an entry was retired stays in the records.
    AUDIENCES: ClassVar[dict[str, frozenset[str]]] = {
        **{name: CURATOR for name in ("id", "surface", "statement", "serves")},
        "retired": RECORD_ONLY,
    }

    id: str = Field(pattern=_ID.pattern)
    surface: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    serves: tuple[str, ...] = Field(min_length=1)
    retired: str = ""

    @property
    def active(self) -> bool:
        return not self.retired


class CommitmentChange(BaseModel):
    """One operation on the commitment list, as a design submits it."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    AUDIENCES: ClassVar[dict[str, frozenset[str]]] = {
        name: RECORD_ONLY for name in ("action", "id", "surface", "statement", "serves", "reason")
    }

    action: Literal["add", "modify", "retire"] = Field(
        description="add a commitment, modify a current one, or retire a current one."
    )
    id: str = Field(
        default="",
        description="The current commitment a modify or retire refers to. Leave empty for add; the host assigns it.",
    )
    surface: str = Field(
        default="",
        description="The granted target that implements it, or native for behavior the host provides without "
        "authored code. Required for add; on modify, a new surface moves the commitment.",
    )
    statement: str = Field(
        default="",
        description="What the surface does, in which situation, from what input and with what effect; for a model "
        "judgment, what happens when it cannot be made. Required for add; on modify, the new statement.",
    )
    serves: tuple[str, ...] = Field(
        default=(),
        description="The inputs it serves, in the diagnoses' about vocabulary. Required for add; on modify, the "
        "complete new list.",
    )
    reason: str = Field(
        default="",
        description="Why it changes. Required for modify and retire; a modify with only a reason keeps the "
        "commitment and revises its implementation.",
    )

    @model_validator(mode="after")
    def complete(self) -> "CommitmentChange":
        if self.action == "add":
            if not (self.surface and self.statement.strip() and self.serves):
                raise ValueError("an added commitment needs its surface, statement and serves")
            return self
        if not self.id or not self.reason.strip():
            raise ValueError(f"{self.action} needs the id of a current commitment and a reason")
        if self.action == "retire" and (self.surface or self.statement or self.serves):
            raise ValueError("a retirement carries only the id and the reason")
        return self

    @property
    def serves_only(self) -> bool:
        """A modify that only re-points what an unchanged commitment serves; on a target left unselected it asks for
        no code change."""
        return self.action == "modify" and bool(self.serves) and not self.surface and not self.statement


def active(commitments: Iterable[Commitment]) -> tuple[Commitment, ...]:
    return tuple(item for item in commitments if item.active)


def _number(identifier: str) -> int:
    return int(_ID.match(identifier).group(1))


def assign(current: Iterable[Commitment], changes: Iterable[CommitmentChange]) -> tuple[CommitmentChange, ...]:
    """The changes with an id given to every addition: the next numbers after any id ever used. An addition that
    already names exactly that id, as a reopened design may copy it from its earlier submission, keeps it."""
    used = max((_number(item.id) for item in current), default=0)
    assigned = []
    for change in changes:
        if change.action == "add":
            used += 1
            if change.id not in ("", f"H{used}"):
                raise ValueError(f"leave the id of an added commitment empty; the host assigns it (here H{used})")
            change = change.model_copy(update={"id": f"H{used}"})
        assigned.append(change)
    return tuple(assigned)


def apply(current: Iterable[Commitment], changes: Iterable[CommitmentChange]) -> tuple[Commitment, ...]:
    """The list after `changes`, in order. Additions carry their assigned ids (`assign`)."""
    entries = {item.id: item for item in current}
    used = max((_number(identifier) for identifier in entries), default=0)
    touched = set()
    for change in changes:
        if change.id in touched:
            raise ValueError(f"commitment {change.id} is changed more than once; combine its changes")
        touched.add(change.id)
        if change.action == "add":
            if not _ID.match(change.id) or _number(change.id) != used + 1:
                raise ValueError(f"an added commitment needs the next host id H{used + 1}, not {change.id!r}")
            used += 1
            entries[change.id] = Commitment(
                id=change.id, surface=change.surface, statement=change.statement, serves=change.serves
            )
            continue
        existing = entries.get(change.id)
        if existing is None or not existing.active:
            current_ids = [item.id for item in entries.values() if item.active]
            raise ValueError(f"{change.action} names no current commitment: {change.id!r}; current: {current_ids}")
        if change.action == "retire":
            entries[change.id] = existing.model_copy(update={"retired": change.reason})
            continue
        update = {
            key: value
            for key, value in (("surface", change.surface), ("statement", change.statement), ("serves", change.serves))
            if value
        }
        entries[change.id] = existing.model_copy(update=update)
    return tuple(entries.values())


def operated_surfaces(current: Iterable[Commitment], changes: Iterable[CommitmentChange]) -> set[str]:
    """The authored surfaces the changes operate on: every surface an operation adds to, retires from, modifies on
    or moves between. The native surface has no code."""
    entries = {item.id: item for item in current}
    surfaces = set()
    for change in changes:
        if change.action != "add" and change.id in entries:
            surfaces.add(entries[change.id].surface)
        if change.surface:
            surfaces.add(change.surface)
    return surfaces - {NATIVE}


def touched_surfaces(current: Iterable[Commitment], changes: Iterable[CommitmentChange]) -> set[str]:
    """The authored surfaces whose code the changes ask for: those operated on by anything but a serves-only
    modify."""
    return operated_surfaces(current, (change for change in changes if not change.serves_only))


def check_design(
    current: Iterable[Commitment],
    changes: Iterable[CommitmentChange],
    *,
    surfaces: Iterable[str],
    inputs: Iterable[str],
    selected: Iterable[str],
    grounds: Mapping[str, Iterable[str]],
    authored: Iterable[str] = (),
) -> tuple[CommitmentChange, ...]:
    """The changes with ids assigned, once they agree with the design they belong to.

    `surfaces` are the granted target names, `inputs` this curation's diagnosed inputs, `selected` the selected
    targets, `grounds` the inputs each of them addresses and `authored` the targets that currently have code. Every
    operation that asks for code needs its surface selected, and a selected target needs an operation on it (a
    serves-only modify counts there), unless its current code has no commitment at all: code installed without a
    design, which `check_artifact` then lets the artifact keep only with added commitments. After the changes, the
    grounds of a selected target are served by its current commitments, unless the changes retire every commitment
    on it or it is such earlier code left without one."""
    current = tuple(current)
    changes = assign(current, changes)
    granted = {*surfaces, NATIVE}
    known = {*inputs, *(value for item in active(current) for value in item.serves)}
    for change in changes:
        if change.surface and change.surface not in granted:
            raise ValueError(f"commitment surface {change.surface!r} is not granted; use one of {sorted(granted)}")
        unknown = [value for value in change.serves if value not in known]
        if unknown:
            raise ValueError(
                f"commitment {change.id or '(new)'} serves inputs that were not diagnosed: {unknown}; "
                f"the inputs are {sorted(known)}"
            )
    after = apply(current, changes)
    selected = set(selected)
    asked = touched_surfaces(current, changes)
    unselected = sorted(asked - selected)
    if unselected:
        raise ValueError(
            f"commitment changes ask for code on targets that are not selected: {unselected}; select them or "
            "drop those changes (a modify that only changes serves needs no selection)"
        )
    holding = {item.surface for item in active(current)}
    earlier = set(authored) - holding
    silent = sorted(selected - operated_surfaces(current, changes) - earlier)
    if silent:
        raise ValueError(
            f"selected targets carry no commitment change: {silent}; add, retire or modify the commitments on "
            "them (a modify with only a reason keeps a commitment and revises its implementation)"
        )
    for target in sorted(selected):
        served = {value for item in active(after) if item.surface == target for value in item.serves}
        if not served and (target in holding or target in earlier):
            continue
        missing = [value for value in grounds.get(target, ()) if value not in served]
        if missing:
            raise ValueError(
                f"the selection grounds {target} on {missing}, which no current commitment on {target} serves "
                "after this plan; list them in the serves of the commitment that addresses them"
            )
    return changes


def withdraw(commitments: Iterable[Commitment], reason: str) -> tuple[Commitment, ...]:
    """The list with every current entry retired for `reason`, as when a Harness returns to its original version;
    the ids stay taken."""
    return tuple(item if item.retired else item.model_copy(update={"retired": reason}) for item in commitments)


def check_artifact(after: Iterable[Commitment], *, valued: Iterable[str], removed: Iterable[str]) -> None:
    """A submitted artifact agrees with the commitment list it will run under: a target that keeps or gets code
    has a current commitment, and a target retired from the Harness has none left."""
    surfaces = {item.surface for item in active(after)}
    bare = sorted(set(valued) - surfaces)
    if bare:
        raise ValueError(
            f"targets with code but no current commitment: {bare}; revise the plan to add a commitment for each, "
            "or remove the target"
        )
    kept = sorted(set(removed) & surfaces)
    if kept:
        raise ValueError(
            f"removed targets still carry current commitments: {kept}; revise the plan to retire them, or keep "
            "the target's value"
        )


def coverage(commitments: Iterable[Commitment], inputs: Iterable[str]) -> dict[str, list[str]]:
    """What the current list leaves open against this curation's inputs: `unserved`, the diagnosed inputs no
    current commitment serves, and `stale_serves`, versioned or routed input keys the list still cites that this
    curation no longer has."""
    inputs = list(dict.fromkeys(inputs))
    cited = list(dict.fromkeys(value for item in active(commitments) for value in item.serves))
    return {
        "unserved": [value for value in inputs if value not in cited],
        "stale_serves": [value for value in cited if value.startswith(VOLATILE_INPUTS) and value not in inputs],
    }
