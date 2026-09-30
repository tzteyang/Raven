"""A scenario as the simulated agency works it: the owner's profile, its material folders, the customer personas and
the owner's checks, read through the contract loader (`experimental.scenario`), which also says each material's kind
and who may receive what."""

import random
import shutil
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..scenario import Disclosure
from ..scenario import Scenario as Contract
from ..scenario import load as read_contract
from ..scenario.contract import document, frontmatter
from .cards import Drawn, draw

BUNDLED = Path(__file__).resolve().parent / "scenarios"


class Criterion(BaseModel):
    """One check the agency applies to a round's conversations; a red line is one the owner never tolerates missing."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    check: str = Field(min_length=1)
    severity: Literal["red_line", "standard"] = "standard"


@dataclass(frozen=True)
class Persona:
    """A drill card: `text` names its values in braces and `values` says how each is drawn (see `cards`)."""

    name: str
    text: str
    values: dict = field(default_factory=dict, compare=False)

    def play(self, rng: random.Random) -> Drawn:
        return draw(self.name, self.values, self.text, rng)


@dataclass(frozen=True)
class Scenario:
    """Materials are skill directories the agency owns; releasing one copies it into the employee's skill pool.

    `initial` is what the employee has before the first round under the staged plan; the agency hands over the rest.
    `plans` are named partitions of the materials into steps: step 0 at onboarding, step k with the review of round k.
    `onboarding` and `handover` are the owner's words around uploaded files, each listing them at `{files}`. `kinds`
    are the materials' kinds in the contract's terms, and `contract` the loaded contract itself, whole even when
    `without` leaves materials out. `handed` are the materials the agency may hand over, those the partner may
    receive; the others it only holds and judges by, such as a procedure it never handed over."""

    root: Path
    profile: str
    materials: dict[str, Path]
    personas: tuple[Persona, ...]
    criteria: tuple[Criterion, ...]
    initial: tuple[str, ...]
    onboarding: str = ""
    handover: str = ""
    plans: dict[str, tuple[tuple[str, ...], ...]] = field(default_factory=dict)
    kinds: dict[str, str] = field(default_factory=dict)
    contract: Contract | None = field(default=None, compare=False, repr=False)
    handed: tuple[str, ...] = ()

    @classmethod
    def load(cls, root: Path) -> "Scenario":
        root = Path(root).resolve()
        if not root.is_dir():
            root = BUNDLED / root.name
        return cls.of(read_contract(root))

    @classmethod
    def of(cls, read: Contract) -> "Scenario":
        """The agency's view of a loaded contract: the materials and checks the party may receive. The agency judges
        by checks, so a scenario without any it may read is refused."""
        checks = [check for check in read.statements.checks if "party" in check.visibility]
        if not checks:
            raise ValueError(f"the scenario has no checks for the agency to judge by: {read.root}")
        held = {name: material for name, material in read.materials.items() if "party" in material.visibility}
        return cls(
            read.root,
            read.situation.profile,
            {name: material.path for name, material in held.items()},
            tuple(Persona(case.id, case.text, case.values) for case in read.situation.cases),
            tuple(Criterion(id=check.id, check=check.check, severity=check.severity) for check in checks),
            read.exchange.initial,
            read.exchange.onboarding,
            read.exchange.handover,
            dict(read.exchange.plans),
            {name: material.kind for name, material in held.items()},
            read,
            tuple(name for name in read.handed if name in held),
        )

    def without(self, names) -> "Scenario":
        """The scenario as if the agency never had these materials: gone from its materials, opening set and plans."""
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
        """The schedule `plan` gives over this scenario's materials (see `experimental.scenario.disclosure`)."""
        return Disclosure.of(plan, materials=self.handed, initial=self.initial, plans=self.plans, rounds=rounds)

    def text(self, material: str) -> str:
        """A material's own document (see `experimental.scenario.contract.document`)."""
        return document(self.materials[material]).read_text()

    def stands_behind(self, material: str) -> bool:
        """Whether the owner holds the partner to this material: it gave it, or confirmed it after a research stage
        induced it (`experimental.scenario.contract.Scenario.confirmed`); an unconfirmed one is handed over as a
        candidate and judged by no one."""
        return self.contract is None or self.contract.confirmed(material)

    def standing_norms(self, names) -> dict[str, str]:
        """The norms among `names` the evaluation side may draw criteria from, by name to text: those the owner
        stands behind and the Analyst may read."""
        return {
            name: self.text(name)
            for name in names
            if self.kinds.get(name) == "norm"
            and self.stands_behind(name)
            and (self.contract is None or self.contract.visible(name, "analyst"))
        }

    def release(self, names, skills: Path) -> None:
        for name in names:
            shutil.copytree(self.materials[name], Path(skills) / name, dirs_exist_ok=True)

    def withdraw(self, skills: Path) -> None:
        """Remove every scenario-owned skill from the pool, so a run starts from the plan it declares."""
        for name in self.materials:
            shutil.rmtree(Path(skills) / name, ignore_errors=True)

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

    def withdraw_uploads(self, *places: Path) -> None:
        for place in places:
            for name in self.materials:
                shutil.rmtree(Path(place) / name, ignore_errors=True)
