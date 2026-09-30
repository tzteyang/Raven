"""Read one worker root's iteration, analysis, attribution and curation records as a single joined run, with its
ledger (`experimental.iteration.ledger`)."""

import json
from dataclasses import dataclass
from pathlib import Path

from .history import Entry
from .ledger import held_out, rows, summary


def runs(root: Path) -> list[Path]:
    """Iteration record files under a worker root, oldest first."""
    directory = Path(root) / "iteration"
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.json"), key=lambda path: path.stat().st_mtime)


@dataclass(frozen=True)
class Cultivation:
    """An earlier cultivation brought as a prior: its typed history, and what its conversants said, one stream per
    session of each round, which is all its own Curator compartment spared."""

    history: tuple[Entry, ...]
    spoken: tuple[tuple[str, ...], ...] = ()

    def record(self) -> dict:
        return {"history": [entry.model_dump(mode="json") for entry in self.history], "spoken": self.spoken}

    @classmethod
    def of(cls, value: dict) -> "Cultivation":
        return cls(
            tuple(Entry.model_validate(row) for row in value["history"]),
            tuple(tuple(stream) for stream in value.get("spoken", ())),
        )


def cultivation(path: Path) -> Cultivation:
    """An earlier run as a prior: an iteration record file, or a worker root's latest one. A held-out session was
    never heard by that run's Curator, so its words are not among those spared."""
    path = Path(path)
    if path.is_dir():
        found = runs(path)
        if not found:
            raise ValueError(f"no iteration record under {path}")
        path = found[-1]
    record = json.loads(path.read_text())
    if not isinstance(record, dict) or not isinstance(record.get("history"), list):
        raise ValueError(f"not an iteration record, it keeps no history: {path}")
    spoken = [
        tuple(exchange["user"] for exchange in exchanges)
        for item in record.get("rounds", ())
        for exchanges in item.get("sessions", {}).values()
    ]
    return Cultivation(tuple(Entry.model_validate(row) for row in record["history"]), tuple(spoken))


def load(path: Path) -> dict:
    """The run record with each round's analysis, attribution and curation records read in beside it, and the
    ledger joined from its history and held-out assessments."""
    path = Path(path)
    root = path.parents[1]
    run = json.loads(path.read_text())
    run["initial_curation"] = [_read(root / "curation" / name) for name in run.get("initial_curation", [])]
    run["initial_attribution"] = [_read(root / "attribution" / name) for name in run.get("initial_attribution", [])]
    for item in run["rounds"]:
        for exchanges in (*item.get("sessions", {}).values(), *item.get("holdout", {}).values()):
            for exchange in exchanges:
                execution = exchange["execution"]
                execution["deliverables"] = [_here(path, root) for path in execution.get("deliverables", [])]
        item["analysis"] = [_read(root / "analysis" / name) for name in item.get("analysis", [])]
        item["curation"] = [_read(root / "curation" / name) for name in item.get("curation", [])]
        item["attribution"] = [_read(root / "attribution" / name) for name in item.get("attribution", [])]
    joined = rows(run.get("history", ()))
    run["ledger"] = {"rows": joined, "summary": summary(joined), "holdout": held_out(run["rounds"])}
    return run


def _here(path: str, root: Path) -> str:
    """A kept deliverable's path under this worker root, so a moved or copied run still finds its files: the longest
    tail of the recorded path, from a `deliverables` folder or above, that exists under the root, which keeps the
    folder of a replica that kept it; a file found nowhere is placed where the root keeps its own."""
    parts = Path(path).parts
    if "deliverables" not in parts:
        return path
    last = len(parts) - 1 - parts[::-1].index("deliverables")
    for start in range(1 if Path(path).is_absolute() else 0, last + 1):
        candidate = root.joinpath(*parts[start:])
        if candidate.exists():
            return str(candidate)
    return str(root.joinpath(*parts[parts.index("deliverables") :]))


def _read(path: Path) -> dict:
    if not path.is_file():
        return {"missing": path.name}
    return {"file": path.name, **json.loads(path.read_text())}
