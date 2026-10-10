"""A scenario as the counterpart works it: its profile, the materials it owns and may hand over, and the checks it
judges by, read through the contract loader (`experimental.harness.scenario`), which also says each material's kind
and who may receive what. The simulated people who play it are the bench's (`experimental.simulation.bench.scenario`)."""

import shutil
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from experimental.harness.scenario import Disclosure
from experimental.harness.scenario import Scenario as Contract
from experimental.harness.scenario.contract import document, frontmatter


class Criterion(BaseModel):
    """One check the counterpart applies to a round's conversations; a red line is one the owner never tolerates missing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    check: str = Field(min_length=1)
    severity: Literal["red_line", "standard"] = "standard"


@dataclass(frozen=True)
class Scenario:
    """A scenario as the counterpart works it. Materials are skill directories the counterpart owns; releasing one copies it into the employee's skill pool.

    `initial` is what the employee has before the first round under the staged plan; the counterpart hands over the rest.
    `plans` are named partitions of the materials into steps: step 0 at onboarding, step k with the review of round k.
    `onboarding` and `handover` are the owner's words around uploaded files, each listing them at `{files}`. `kinds`
    are the materials' kinds in the contract's terms, and `contract` the loaded contract itself, whole even when
    `without` leaves materials out. `handed` are the materials the counterpart may hand over, those the partner may
    receive; the others it only holds and judges by, such as a procedure it never handed over."""

    root: Path
    profile: str
    materials: dict[str, Path]
    criteria: tuple[Criterion, ...]
    initial: tuple[str, ...]
    onboarding: str = ""
    handover: str = ""
    plans: dict[str, tuple[tuple[str, ...], ...]] = field(default_factory=dict)
    kinds: dict[str, str] = field(default_factory=dict)
    contract: Contract = field(compare=False, repr=False, kw_only=True)
    handed: tuple[str, ...] = ()

    @classmethod
    def of(cls, read: Contract) -> "Scenario":
        """The counterpart's view of a loaded contract: the materials and checks it may receive. The counterpart judges
        by checks, so a scenario without any it may read is refused."""
        checks = [check for check in read.statements.checks if "counterpart" in check.visibility]
        if not checks:
            raise ValueError(f"the scenario has no checks for the counterpart to judge by: {read.root}")
        held = {name: material for name, material in read.materials.items() if "counterpart" in material.visibility}
        return cls(
            read.root,
            read.situation.profile,
            {name: material.path for name, material in held.items()},
            tuple(Criterion(id=check.id, check=check.check, severity=check.severity) for check in checks),
            read.exchange.initial,
            read.exchange.onboarding,
            read.exchange.handover,
            dict(read.exchange.plans),
            {name: material.kind for name, material in held.items()},
            handed=tuple(name for name in read.handed if name in held),
            contract=read,
        )

    def without(self, names) -> "Scenario":
        """The scenario as if the counterpart never had these materials: gone from its materials, opening set and plans."""
        names = set(names)
        unknown = names - self.materials.keys()
        if unknown:
            raise ValueError(f"the scenario has no materials named {sorted(unknown)}")
        return replace(
            self,
            materials={name: path for name, path in self.materials.items() if name not in names},
            kinds={name: kind for name, kind in self.kinds.items() if name not in names},
            handed=tuple(name for name in self.handed if name not in names),
            initial=tuple(name for name in self.initial if name not in names),
            plans={
                plan: tuple(tuple(name for name in step if name not in names) for step in steps)
                for plan, steps in self.plans.items()
            },
        )

    def disclosure(self, plan="staged", rounds: int | None = None) -> Disclosure:
        """The schedule `plan` gives over this scenario's materials (see `experimental.harness.scenario.disclosure`)."""
        return Disclosure.of(plan, materials=self.handed, initial=self.initial, plans=self.plans, rounds=rounds)

    def text(self, material: str) -> str:
        """A material's own document (see `experimental.harness.scenario.contract.document`)."""
        return document(self.materials[material]).read_text()

    def stands_behind(self, material: str) -> bool:
        """Whether the owner adopts this material; an unconfirmed reference may be handed over but does not
        supply an evaluation norm (`experimental.harness.scenario.contract.Scenario.confirmed`)."""
        return self.contract.confirmed(material)

    def standing_norms(self, names) -> dict[str, str]:
        """The norms among `names` the evaluation side may draw criteria from, by name to text: those the owner
        stands behind and the Analyst may read."""
        return {
            name: self.text(name)
            for name in names
            if self.kinds.get(name) == "norm" and self.stands_behind(name) and self.contract.visible(name, "analyst")
        }

    def release(self, names, skills: Path) -> None:
        for name in names:
            shutil.copytree(self.materials[name], Path(skills) / name, dirs_exist_ok=True)

    def withdraw(self, *places: Path) -> None:
        """Reset every contract-owned material path, including materials excluded from this run."""
        for place in places:
            for name in self.contract.materials:
                path = Path(place) / name
                if path.is_symlink() or path.is_file():
                    path.unlink()
                elif path.exists():
                    shutil.rmtree(path)

    def document(self, material: str) -> str:
        """A material as the owner's own document: its text without the skill frontmatter."""
        return frontmatter(self.text(material))[1] + "\n"

    def upload(self, names, uploads: Path, *, shared: Path | None = None) -> list[str]:
        """Put materials in an uploads folder the way an owner uploads files, one folder per material.

        Each complete package keeps SKILL.md, frontmatter and all nested/binary assets. With `shared` (the `uploads` folder of the
        working directory), the same folders are also put there and the returned paths are relative to the working
        directory: every drill works in its own copy of it, where those relative paths resolve, while an absolute
        path would name one drill's copy only. Otherwise they are relative to the uploads folder's parent.
        """
        places = [Path(uploads), *([Path(shared)] if shared is not None else [])]
        paths = []
        for place in places:
            written = []
            for name in names:
                folder = place / name
                shutil.rmtree(folder, ignore_errors=True)
                shutil.copytree(self.materials[name], folder, symlinks=True)
                written.extend(path for path in sorted(folder.rglob("*")) if path.is_file())
            paths = written
        base = Path(shared if shared is not None else uploads).parent
        return [path.relative_to(base).as_posix() for path in paths]
