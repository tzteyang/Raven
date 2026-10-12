"""The categories of a cultivation scenario, their items' visibility, and the reading of a scenario directory.

Roles: the partner (the worker being cultivated), the conversant (whoever the partner works with in a trial), the
counterpart (whoever holds the materials and the standard and speaks to the Curator), the analyst and the curator. Each
kind of item has a default visibility, the set of roles that may receive it; a scenario may narrow or widen it per
item in `contract.json`. Visibility is a declaration the assembly, the hearing and the exploration enforce; nothing
here reads a file into a role.

The directory layout is the one `experimental/simulation/cases/<name>/` uses: `profile.md`, `materials/<name>/`
packages (a skill with its SKILL.md, or a folder whose one top-level markdown file is its document),
`personas/*.md` drill cards (frontmatter: drawn `values`, handed-over `files`, a labelled card's `expected` answer),
`scenario.json` with the checks, the disclosure plans and the card schedule, the counterpart's `onboarding.md`
and `handover.md`, the evaluation-side `reference.md` and `record.md`, `contract.json` for what this module adds
(each material's kind, each check's derivation, and the counterpart's observation views), and `provenance.json`, which a
research stage writes (`experimental.cultivation.collector`) to say where each material came from and whether the counterpart stands
behind it. A `lab/` folder holds what a launcher places on a registered machine for an on-call colleague to run (a
read-only script and the data it reveals over time); it is no material, so no role is handed it.
"""

import json
import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from experimental.harness.scenario.disclosure import Plan, partition

Role = Literal["partner", "conversant", "counterpart", "analyst", "curator"]
ROLES: tuple[Role, ...] = ("partner", "conversant", "counterpart", "analyst", "curator")

Kind = Literal["norm", "fact", "exemplar", "counterexample"]
KINDS: tuple[Kind, ...] = ("norm", "fact", "exemplar", "counterexample")

# What the counterpart may observe of the partner's work beyond the conversation, as the counterpart's review names them.
VIEWS = ("conversations", "deliverables", "research", "colleague_reports", "filed", "back_office")

SKILL_FILE = "SKILL.md"
PROVENANCE = "provenance.json"
LAB = "lab"
CLAIMED = (
    "profile.md",
    "onboarding.md",
    "handover.md",
    "scenario.json",
    "contract.json",
    "reference.md",
    "record.md",
    PROVENANCE,
)
# Text a package may carry besides its markdown: a price table, a template, a data file handed over as written.
TEXT_SUFFIXES = frozenset({".md", ".txt", ".csv", ".tsv", ".json", ".yaml", ".yml", ".html", ".xml"})

_EVERYONE = frozenset(ROLES)
_HANDED = frozenset({"partner", "counterpart", "analyst", "curator"})
_EVALUATION = frozenset({"counterpart", "analyst"})
_DEFAULTS: dict[str, frozenset[str]] = {
    "profile": _EVERYONE,
    "case": frozenset({"conversant", "counterpart"}),
    "case.expected": _EVALUATION,
    "check": _EVALUATION,
    "norm": _HANDED,
    "fact": _HANDED,
    "exemplar": _HANDED,
    "counterexample": _HANDED,
    "exchange": frozenset({"counterpart"}),
    "prior": _EVALUATION,
    "aids": frozenset({"counterpart"}),
}


def default_visibility(kind: str) -> frozenset[str]:
    """The roles that may receive an item of this kind unless the scenario says otherwise."""
    return _DEFAULTS[kind]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _roles(value) -> frozenset[str]:
    roles = frozenset(value)
    unknown = roles - _EVERYONE
    if unknown:
        raise ValueError(f"unknown roles: {sorted(unknown)}")
    return roles


class Case(_Model):
    """One situation the partner is drilled in: a persona with drawn values, the files the person hands over as the
    conversation opens (paths inside the scenario directory), and for a labelled case its expected answer."""

    id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    values: dict = Field(default_factory=dict)
    files: tuple[str, ...] = ()
    expected: str | None = None
    visibility: frozenset[str] = Field(default_factory=lambda: default_visibility("case"))


class Schedule(_Model):
    """Which cases are played when: `rounds[k]` in round k + 1 (the last entry for every later round), the held-out
    cases, judged but kept from whoever improves the partner, and `holdout_rounds`, the rounds they are played in (every
    round when empty; 0 is before onboarding). Empty when every case is played each round."""

    rounds: tuple[tuple[str, ...], ...] = ()
    holdout: tuple[str, ...] = ()
    holdout_rounds: tuple[int, ...] = ()

    def round(self, index: int) -> tuple[str, ...]:
        """The cases of round `index` (1-based); empty when the schedule names no rounds."""
        return self.rounds[min(index, len(self.rounds)) - 1] if self.rounds else ()


class Situation(_Model):
    """The work and the world it happens in: the partner's job, the cases it meets and when it meets them."""

    profile: str = Field(min_length=1)
    cases: tuple[Case, ...] = Field(min_length=1)
    schedule: Schedule = Field(default_factory=Schedule)

    @model_validator(mode="after")
    def distinct_cases(self) -> "Situation":
        ids = [case.id for case in self.cases]
        if len(set(ids)) != len(ids):
            raise ValueError(f"case ids repeat: {sorted({i for i in ids if ids.count(i) > 1})}")
        scheduled = {name for step in self.schedule.rounds for name in step} | set(self.schedule.holdout)
        unknown = scheduled - set(ids)
        if unknown:
            raise ValueError(f"the schedule names cases the scenario does not have: {sorted(unknown)}")
        if any(not step for step in self.schedule.rounds):
            raise ValueError("every scheduled round plays at least one case")
        both = {name for step in self.schedule.rounds for name in step} & set(self.schedule.holdout)
        if both:
            raise ValueError(f"a held-out case is not also played for feedback: {sorted(both)}")
        if self.schedule.holdout_rounds and (
            not self.schedule.holdout or any(number < 0 for number in self.schedule.holdout_rounds)
        ):
            raise ValueError("held-out rounds are rounds (0 before onboarding) of a schedule that holds cases out")
        return self


# Ids the loop gives its own criteria: a raised requirement (R1, R2, ...) and a criterion drawn from a norm.
RESERVED = re.compile(r"^(R\d+|derived-\d+)$")


class Check(_Model):
    """One item of the counterpart's standard, derived from the norms it holds the partner to; evaluation-side only. Its
    id may not take the form the loop gives a requirement or a drawn criterion, whose regression items would then be
    read as this check's."""

    id: str = Field(min_length=1)
    check: str = Field(min_length=1)
    severity: Literal["red_line", "standard"] = "standard"
    applies_when: str = ""
    derived_from: tuple[str, ...] = ()
    visibility: frozenset[str] = Field(default_factory=lambda: default_visibility("check"))

    @model_validator(mode="after")
    def unreserved(self) -> "Check":
        if RESERVED.match(self.id):
            raise ValueError(f"check id {self.id} takes the form the loop gives its own criteria (R1, derived-1)")
        return self


class _Criterion(_Model):
    id: str
    check: str
    severity: Literal["red_line", "standard"] = "standard"
    applies_when: str = ""


class _Plan(_Model):
    """A named plan in `scenario.json`: its steps, and a label per step saying what that step is meant to give."""

    steps: tuple[tuple[str, ...], ...]
    labels: tuple[str, ...] = ()


class _Spec(_Model):
    """`scenario.json`: the checks and the disclosure schedule; an unknown key is a misspelling, never ignored."""

    initial: tuple[str, ...] = ()
    plans: dict[str, _Plan] = Field(default_factory=dict)
    criteria: tuple[_Criterion, ...] = ()
    schedule: Schedule = Field(default_factory=Schedule)


class Statements(_Model):
    """What the counterpart states: the norms it hands over as documents, and the checks it keeps to judge by."""

    norms: tuple[str, ...] = ()
    checks: tuple[Check, ...] = ()

    @model_validator(mode="after")
    def checks_derive_from_norms(self) -> "Statements":
        ids = [check.id for check in self.checks]
        if len(set(ids)) != len(ids):
            raise ValueError(f"check ids repeat: {sorted({i for i in ids if ids.count(i) > 1})}")
        for check in self.checks:
            unknown = set(check.derived_from) - set(self.norms)
            if unknown:
                raise ValueError(f"check {check.id} derives from materials that are not norms: {sorted(unknown)}")
        return self


class Material(_Model):
    """One package the counterpart holds and may hand over: a norm, a fact, an exemplar or a counterexample."""

    name: str = Field(min_length=1)
    kind: Kind
    path: Path
    description: str = ""
    visibility: frozenset[str] = Field(default_factory=lambda: default_visibility("fact"))


class Exchange(_Model):
    """How the exchange is conducted: what is handed over when, what the counterpart observes, and its wording. The
    schedule and the observability are the counterpart's alone; the wording is what the counterpart says, so whoever it is said
    to hears it once it is said."""

    initial: tuple[str, ...] = ()
    plans: dict[str, Plan] = Field(default_factory=dict)
    observability: tuple[str, ...] = VIEWS
    onboarding: str = ""
    handover: str = ""

    @model_validator(mode="after")
    def known_views(self) -> "Exchange":
        unknown = set(self.observability) - set(VIEWS)
        if unknown:
            raise ValueError(f"unknown observation views: {sorted(unknown)}")
        return self


class Prior(_Model):
    """Records of earlier cultivations the counterpart brings, each an iteration record or a run's worker root; a relative
    path in `contract.json` is read from the scenario directory. Nothing by default."""

    records: tuple[Path, ...] = ()


class Aids(_Model):
    """Evaluation-side helpers the counterpart alone uses: the rulers' declaration and the record's labels."""

    rulers: str | None = None
    labels: str | None = None


class Origin(_Model):
    """Where one material came from: given by the counterpart, or induced or researched before the cultivation, with the
    ids of the rules or findings it holds. `confirmed` records adoption independently of who supplied the material;
    generated materials must declare it explicitly."""

    origin: Literal["given", "induced", "researched"] = "given"
    confirmed: bool | None = None
    items: tuple[str, ...] = ()

    @model_validator(mode="after")
    def standing_is_stated(self) -> "Origin":
        if self.origin == "given":
            object.__setattr__(self, "confirmed", True if self.confirmed is None else self.confirmed)
            return self
        if self.confirmed is None:
            raise ValueError(f"say whether the counterpart confirmed this {self.origin} material")
        return self


class Provenance(_Model):
    """`provenance.json`: each material's origin (a material it does not name was given by the counterpart) and, in
    `record`, the file as the research stage wrote it, for a run's settings."""

    materials: dict[str, Origin] = Field(default_factory=dict)
    record: dict = Field(default_factory=dict)


class Scenario(_Model):
    """A scenario read into the categories; `visible` answers whether a role may receive an item."""

    root: Path
    situation: Situation
    statements: Statements
    materials: dict[str, Material]
    exchange: Exchange
    prior: Prior = Prior()
    aids: Aids = Aids()
    provenance: Provenance = Provenance()

    @model_validator(mode="after")
    def consistent(self) -> "Scenario":
        unknown = set(self.provenance.materials) - set(self.materials)
        if unknown:
            raise ValueError(f"the provenance names materials the scenario does not have: {sorted(unknown)}")
        for name in self.statements.norms:
            if name not in self.materials or self.materials[name].kind != "norm":
                raise ValueError(f"norm {name} is not a material of kind norm")
        unknown = set(self.exchange.initial) - set(self.materials)
        if unknown:
            raise ValueError(f"the initial release names materials the scenario does not have: {sorted(unknown)}")
        kept = sorted(set(self.exchange.initial) - set(self.handed))
        if kept:
            raise ValueError(f"the initial release names materials the partner may not receive: {kept}")
        for name, plan in self.exchange.plans.items():
            try:
                partition(plan.steps, self.handed)
            except ValueError as exc:
                raise ValueError(f"plan {name}: {exc}") from exc
        return self

    @property
    def handed(self) -> tuple[str, ...]:
        """The materials the counterpart may hand over, those the partner may receive; the others only the counterpart holds."""
        return tuple(name for name, material in self.materials.items() if "partner" in material.visibility)

    def visible(self, item: str, role: Role) -> bool:
        """Whether `role` may receive the item: a material by name, a case by `case:<id>`, a check by `check:<id>`,
        or one of `profile`, `exchange`, `prior`, `aids`."""
        if role not in _EVERYONE:
            raise ValueError(f"unknown role: {role}")
        if item in self.materials:
            return role in self.materials[item].visibility
        kind, _, key = item.partition(":")
        if kind == "case" and key:
            case = next((case for case in self.situation.cases if case.id == key), None)
            if case is None:
                raise KeyError(item)
            return role in case.visibility
        if kind == "case.expected" and key:
            if not any(case.id == key for case in self.situation.cases):
                raise KeyError(item)
            return role in default_visibility("case.expected")
        if kind == "check" and key:
            check = next((check for check in self.statements.checks if check.id == key), None)
            if check is None:
                raise KeyError(item)
            return role in check.visibility
        if item in ("profile", "exchange", "prior", "aids"):
            return role in default_visibility(item)
        raise KeyError(item)

    def confirmed(self, material: str) -> bool:
        """Whether the counterpart adopts this material; supplied references may explicitly remain unconfirmed.

        Only adopted material may be held against the partner (`experimental.simulation.bench.scenario`)."""
        if material not in self.materials:
            raise KeyError(material)
        origin = self.provenance.materials.get(material)
        return origin is None or origin.confirmed


_FRONTMATTER = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)


def frontmatter(text: str) -> tuple[dict, str]:
    """A document's frontmatter and its body. Frontmatter is a leading block between two `---` lines whose content
    is a YAML mapping; anything else, such as an opening horizontal rule or a table's `|---|` row, is body, since a
    material is handed over as it was written and its metadata only describes it."""
    found = _FRONTMATTER.match(text)
    if found:
        try:
            head = yaml.safe_load(found.group(1))
        except yaml.YAMLError:
            head = None
        if isinstance(head, dict):
            return head, text[found.end() :].strip()
    return {}, text.strip()


def _unclaimed(
    root: Path, materials: dict[str, Path], prior: tuple[Path, ...] = (), handed: tuple[Path, ...] = ()
) -> list[str]:
    """Files under the scenario that belong to no category; a prior record kept inside it belongs to the prior, a file
    a case hands over belongs to that case, a Python module beside the materials is the case's own code (its owner,
    its reference figures), not a material, and the `lab/` folder belongs to the machine it is placed on."""
    claimed = {root / name for name in CLAIMED} | {Path(path) for path in handed}
    out = []
    for file in sorted(path for path in root.rglob("*") if path.is_file()):
        if file in claimed or "__pycache__" in file.parts or (file.parent == root and file.suffix == ".py"):
            continue
        if file.parent == root / "personas" and file.suffix == ".md":
            continue
        if any(file.is_relative_to(folder) for folder in (*materials.values(), *prior, root / LAB)):
            continue
        out.append(file.relative_to(root).as_posix())
    return out


def _cases(root: Path, contract: dict) -> tuple[Case, ...]:
    labelled = contract.get("cases", {})
    cases = []
    for path in sorted((root / "personas").glob("*.md")):
        head, body = frontmatter(path.read_text())
        values = head.get("values") or {}
        if not isinstance(values, dict):
            raise ValueError(f"the values of case {path.stem} must be a mapping")
        given = labelled.get(path.stem, {})
        expected = head.get("expected")
        if expected is not None and (not isinstance(expected, str) or "expected" in given):
            raise ValueError(f"case {path.stem} states its expected answer twice or not as text")
        files = head.get("files") or []
        if not isinstance(files, list) or not all(isinstance(item, str) for item in files):
            raise ValueError(f"the files of case {path.stem} must be a list of paths")
        for item in files:
            file = (root / item).resolve()
            if not file.is_relative_to(root) or not file.is_file():
                raise ValueError(f"case {path.stem} hands over a file the scenario does not have: {item}")
        names = [Path(item).name for item in files]
        if len(set(names)) != len(names):
            raise ValueError(f"case {path.stem} hands over two files of one name, which would land on each other")
        cases.append(
            Case(
                id=path.stem,
                text=body,
                values=values,
                files=tuple(files),
                expected=expected.strip() if expected is not None else given.get("expected"),
                visibility=_roles(given["visibility"]) if "visibility" in given else default_visibility("case"),
            )
        )
    return tuple(cases)


def contents(folder: Path) -> tuple[dict[str, str], tuple[str, ...]]:
    """A package as handed over: the text of each text file by its path inside the package, and the paths of its
    other files, which travel as they are and can only be named."""
    texts, others = {}, []
    for file in sorted(path for path in Path(folder).rglob("*") if path.is_file()):
        name = file.relative_to(folder).as_posix()
        if file.suffix.lower() in TEXT_SUFFIXES:
            try:
                texts[name] = file.read_text(encoding="utf-8")
                continue
            except UnicodeDecodeError:
                pass
        others.append(name)
    return texts, tuple(others)


def document(folder: Path) -> Path | None:
    """A material's own document: its SKILL.md, or else the one markdown file at the folder's top, such as a profile
    or a rule set handed over as it was written; None when the folder has neither, so it is no material."""
    skill = folder / SKILL_FILE
    if skill.is_file():
        return skill
    top = sorted(path for path in folder.glob("*.md") if path.is_file())
    return top[0] if len(top) == 1 else None


def _materials(root: Path, contract: dict) -> dict[str, Material]:
    declared = contract.get("materials", {})
    materials = {}
    for folder in sorted(path for path in (root / "materials").glob("*") if path.is_dir()):
        own = document(folder)
        if own is None:
            continue
        name = folder.name
        head, _ = frontmatter(own.read_text())
        given = declared.get(name, {})
        kind = given.get("kind", "fact")
        if kind not in KINDS:
            raise ValueError(f"material {name} has an unknown kind: {kind}")
        materials[name] = Material(
            name=name,
            kind=kind,
            path=folder,
            description=str(head.get("description", "")),
            visibility=_roles(given["visibility"]) if "visibility" in given else default_visibility(kind),
        )
    unknown = set(declared) - set(materials)
    if unknown:
        raise ValueError(f"contract.json declares materials the scenario does not have: {sorted(unknown)}")
    return materials


def _checks(spec: _Spec, contract: dict) -> tuple[Check, ...]:
    declared = contract.get("checks", {})
    checks = []
    for row in spec.criteria:
        given = declared.get(row.id, {})
        checks.append(
            Check(
                id=row.id,
                check=row.check,
                severity=row.severity,
                applies_when=row.applies_when,
                derived_from=tuple(given.get("derived_from", ())),
                visibility=_roles(given["visibility"]) if "visibility" in given else default_visibility("check"),
            )
        )
    unknown = set(declared) - {check.id for check in checks}
    if unknown:
        raise ValueError(f"contract.json declares checks the scenario does not have: {sorted(unknown)}")
    return tuple(checks)


def _text(root: Path, name: str) -> str | None:
    path = root / name
    return path.read_text().strip() if path.is_file() else None


def _provenance(root: Path) -> Provenance:
    path = root / PROVENANCE
    if not path.is_file():
        return Provenance()
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"{PROVENANCE} must hold an object")
    return Provenance(materials=raw.get("materials", {}), record=raw)


def load(root: Path) -> Scenario:
    """Read a scenario directory into the categories; a file that belongs to no category is an error."""
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError(f"scenario directory not found: {root}")
    contract = json.loads((root / "contract.json").read_text()) if (root / "contract.json").is_file() else {}
    unknown = set(contract) - {"materials", "checks", "cases", "observability", "prior"}
    if unknown:
        raise ValueError(f"contract.json has unknown sections: {sorted(unknown)}")
    spec = _Spec.model_validate(
        json.loads((root / "scenario.json").read_text()) if (root / "scenario.json").is_file() else {}
    )
    materials = _materials(root, contract)
    prior = tuple(root / path for path in contract.get("prior", ()))
    cases = _cases(root, contract)
    handed = tuple((root / item).resolve() for case in cases for item in case.files)
    inside = sorted(
        str(file.relative_to(root))
        for file in handed
        if any(file.is_relative_to(material.path.resolve()) for material in materials.values())
    )
    if inside:
        raise ValueError(f"a case hands over files of a material, which would release it early: {inside}")
    stray = _unclaimed(root, {name: material.path for name, material in materials.items()}, prior, handed)
    if stray:
        raise ValueError(f"files outside every category: {stray}")
    profile = _text(root, "profile.md")
    if not profile:
        raise ValueError(f"scenario profile is missing or empty: {root}")
    return Scenario(
        root=root,
        situation=Situation(profile=profile, cases=cases, schedule=spec.schedule),
        statements=Statements(
            norms=tuple(name for name, material in materials.items() if material.kind == "norm"),
            checks=_checks(spec, contract),
        ),
        materials=materials,
        exchange=Exchange(
            initial=spec.initial,
            plans={name: Plan(plan.steps, plan.labels) for name, plan in spec.plans.items()},
            observability=tuple(contract.get("observability", VIEWS)),
            onboarding=_text(root, "onboarding.md") or "",
            handover=_text(root, "handover.md") or "",
        ),
        prior=Prior(records=prior),
        aids=Aids(rulers=_text(root, "reference.md"), labels=_text(root, "record.md")),
        provenance=_provenance(root),
    )
