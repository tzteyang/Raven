"""A research result written as a scenario directory the contract loader reads like any other.

`copy` writes the scenario as the party handed it over into a new directory: the materials it held back stay, since
the party still holds and judges by them, but only the party may receive them and they leave the opening set and the
disclosure plans. `add` writes what the party settled into it as packages: the induced rules as `induced-norms` and
`induced-candidates`, and the researched findings as `researched-norms`, `researched-norm-candidates`,
`researched-facts` and `researched-fact-candidates`, the confirmed or amended ones apart from those the party left
undecided, whose documents say they are unconfirmed; a rejected item is written nowhere. Every package has its kind's
default visibility, since what the partner reads reaches the Analyst through the partner's replies anyway. What
keeps an unconfirmed item off the evaluation side is `provenance.json`, which records each material's origin and
whether the party stands behind it: the evaluation side draws only on the materials it stands behind
(`experimental.scenario.contract.Scenario.confirmed`). An induced package is disclosed with the earliest of the
instances its rules were read from; a researched one with the opening, since it answers what the work needs from the
start.
"""

import hashlib
import json
import shutil
import time
from collections.abc import Iterable, Sequence
from pathlib import Path

import yaml

from ..scenario import Scenario
from ..scenario.contract import PROVENANCE, SKILL_FILE
from .confirm import Decision, Item, worded
from .induction import Rule
from .slots import Slot

CONFIRMED, CANDIDATES = "induced-norms", "induced-candidates"
RESEARCHED = {
    ("norm", True): "researched-norms",
    ("norm", False): "researched-norm-candidates",
    ("fact", True): "researched-facts",
    ("fact", False): "researched-fact-candidates",
}
_CHECK_AGAIN = "check prices, dates, opening hours and rules again before relying on them"
_ABOUT = {
    CONFIRMED: (
        "Rules read from the exemplars and counterexamples handed over, each confirmed by the party.",
        "They hold like any other norm.",
    ),
    CANDIDATES: (
        "Rules read from the exemplars and counterexamples handed over, which the party has not confirmed.",
        "Each is a likely reading of the examples, not a rule the party states: where one conflicts with a norm or "
        "with what the party says, the norm and the party win.",
    ),
    "researched-norms": (
        "Rules of the trade found on the web, each confirmed by the party.",
        "They hold like any other norm.",
    ),
    "researched-norm-candidates": (
        "Rules of the trade found on the web, which the party has not confirmed.",
        "Each is common practice elsewhere, not a rule the party states: where one conflicts with a norm or with "
        "what the party says, the norm and the party win.",
    ),
    "researched-facts": (
        "Facts the work depends on, found on the web and confirmed by the party.",
        f"They were true when they were read: {_CHECK_AGAIN}.",
    ),
    "researched-fact-candidates": (
        "Facts the work depends on, found on the web, which the party has not confirmed.",
        f"They are what their sources said when they were read, not what the party states: {_CHECK_AGAIN}, and "
        "where one conflicts with a material or with what the party says, the material and the party win.",
    ),
}


def digest(root: Path) -> str:
    """The SHA-256 of a directory's files, their paths included, so a researched package names its input exactly."""
    hashed = hashlib.sha256()
    for file in sorted(path for path in Path(root).rglob("*") if path.is_file()):
        hashed.update(file.relative_to(root).as_posix().encode() + b"\0")
        hashed.update(file.read_bytes() + b"\0")
    return f"sha256:{hashed.hexdigest()}"


def _json(path: Path, change) -> None:
    if not path.is_file():
        return
    value = json.loads(path.read_text())
    change(value)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def copy(source: Scenario, out: Path, without: Iterable[str] = ()) -> None:
    """The scenario at `out`, a new directory, with the materials in `without` held by the party alone."""
    without = set(without)
    unknown = without - set(source.materials)
    if unknown:
        raise ValueError(f"the scenario has no materials named {sorted(unknown)}")
    if (source.root / PROVENANCE).exists():
        raise ValueError(f"{source.root.name} was written by a research stage; research the scenario it came from")
    unheld = sorted(name for name in without if "party" not in source.materials[name].visibility)
    if unheld:
        raise ValueError(f"the party does not hold {unheld}, so it cannot hold them back")
    emptied = [plan for plan, steps in source.exchange.plans.items() if steps and not set(steps[0]) - without]
    if emptied:
        raise ValueError(f"holding back {sorted(without)} leaves nothing to hand over at onboarding in {emptied}")
    shutil.copytree(source.root, out, symlinks=True)

    def contract(value):
        for name in without:
            value.setdefault("materials", {}).setdefault(name, {"kind": source.materials[name].kind})
            value["materials"][name]["visibility"] = ["party"]
        if "prior" in value:
            value["prior"] = [
                path
                if (source.root / path).resolve().is_relative_to(source.root)
                else str((source.root / path).resolve())
                for path in value["prior"]
            ]

    def spec(value):
        if "initial" in value:
            value["initial"] = [name for name in value["initial"] if name not in without]
        for plan, steps in value.get("plans", {}).items():
            value["plans"][plan] = [[name for name in step if name not in without] for step in steps]

    if not (out / "contract.json").is_file():
        (out / "contract.json").write_text("{}\n")
    _json(out / "contract.json", contract)
    _json(out / "scenario.json", spec)


def _name(item: Item, confirmed: bool) -> str:
    if isinstance(item, Rule):
        return CONFIRMED if confirmed else CANDIDATES
    return RESEARCHED[(item.kind, confirmed)]


def _document(name: str, settled: Sequence[tuple[Item, Decision]], read_on: str) -> str:
    description, lead = _ABOUT[name]
    head = yaml.safe_dump({"name": name, "description": description}, allow_unicode=True, sort_keys=False)
    lines = ["---", head.strip(), "---", "", f"# {name}", "", f"{description} {lead}", ""]
    if name in RESEARCHED.values():
        lines += [f"Read on {read_on}.", ""]
    for item in (worded(item, decision) for item, decision in settled):
        lines += [f"## {item.id}", "", item.text, ""]
        if item.situation:
            lines += [f"When: {item.situation}", ""]
        if isinstance(item, Rule):
            lines += [f"Read from: {', '.join(item.sources)}", ""]
            continue
        lines += [f"Sources: {', '.join(item.sources)}", "", *(f"> {line}" for line in item.evidence.splitlines()), ""]
        if item.conflicts:
            lines += [f"The materials say otherwise, and they win: {', '.join(item.conflicts)}", ""]
    return "\n".join(lines)


def add(
    out: Path,
    source: Scenario,
    handed: Scenario,
    settled: Sequence[tuple[Item, Decision]],
    *,
    without: Iterable[str] = (),
    slots: Sequence[Slot] = (),
    calls: dict | None = None,
    unanswered: Sequence[dict] = (),
    refused: Sequence[dict] = (),
) -> None:
    """Write the settled items into `out`, the copy `handed` was loaded from, and its `provenance.json`."""
    origins = {name: {"origin": "given", "confirmed": True} for name in handed.materials}
    groups: dict[str, list[tuple[Item, Decision]]] = {}
    for item, decision in settled:
        if decision.status != "rejected":
            groups.setdefault(_name(item, decision.status != "undecided"), []).append((item, decision))
    read_on = time.strftime("%Y-%m-%d")
    for name, rows in groups.items():
        if name in handed.materials:
            raise ValueError(f"the scenario already has a material named {name}")
        folder = out / "materials" / name
        folder.mkdir(parents=True)
        (folder / SKILL_FILE).write_text(_document(name, rows, read_on))
        induced = isinstance(rows[0][0], Rule)
        origins[name] = {
            "origin": "induced" if induced else "researched",
            "confirmed": name in (CONFIRMED, *(RESEARCHED[(kind, True)] for kind in ("norm", "fact"))),
            "items": [item.id for item, _ in rows],
        }
        sources = {source_name for item, _ in rows for source_name in item.sources}

        def contract(value, name=name, kind=rows[0][0].kind):
            value.setdefault("materials", {})[name] = {"kind": kind}

        def spec(value, name=name, sources=sources, induced=induced):
            if not induced:
                value.setdefault("initial", []).append(name)
                for steps in value.get("plans", {}).values():
                    steps[0].append(name)
                return
            if sources & set(value.get("initial", ())):
                value["initial"].append(name)
            for steps in value.get("plans", {}).values():
                first = next(index for index, step in enumerate(steps) if sources & set(step))
                steps[first].append(name)

        _json(out / "contract.json", contract)
        _json(out / "scenario.json", spec)
    provenance = {
        "input": {"scenario": source.root.name, "digest": digest(source.root), "without": sorted(set(without))},
        "materials": origins,
        "rules": [{**item.record(), "decision": d.model_dump()} for item, d in settled if isinstance(item, Rule)],
        "findings": [
            {**item.record(), "decision": d.model_dump()} for item, d in settled if not isinstance(item, Rule)
        ],
        "unanswered": list(unanswered),
        "refused": list(refused),
        "slots": [slot.record() for slot in slots],
        "calls": calls or {},
    }
    (out / PROVENANCE).write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n")
