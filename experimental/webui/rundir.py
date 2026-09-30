"""What the pages read of one run directory besides the Studio's slimmed view: the joined record, guarded so a record
that fails to load is a clear error rather than a traceback, with each round's verdicts; the opaque label each of its
sessions goes by where the Curator sees it; what a run keeps beside its iteration record that no role reads: the
standard assessor's record (`standard.json`), the compartment log (`boundaries.jsonl`, see
`experimental.iteration.compartment`) and where each material came from (the `provenance` of `settings.json`); and
how a curation in progress stands (its progress file) or where a paused one stopped (its checkpoint)."""

import json
from pathlib import Path

from ..iteration.hearing import opaque
from ..iteration.records import load
from .process import redact

BOUNDARY_ROWS = 2000
ERROR_KEEP = 1500
STANDARD_LIMIT = 8_000_000


class RecordError(Exception):
    """A run record that exists but cannot be read or joined, with why."""


def _reason(exc: Exception) -> str:
    text = f"{type(exc).__name__}: {exc}"
    return redact(text if len(text) <= ERROR_KEEP else text[:ERROR_KEEP] + "...")


def verdicts(round_: dict, analysis) -> list[dict]:
    """The round's verdicts by assessor: each signal that carries its items, and for an assessor whose signal carries
    none the scorecard it kept among the round's `analysis` records. An assessor that only speaks, such as the
    simulated owner (`experimental.simulation.agency`), keeps its verdicts there, where no role reads them; a scorecard
    whose every item names one of the round's held-out drills belongs to their assessment, not the round's."""
    carried = [signal for signal in round_.get("signals") or () if isinstance(signal, dict) and signal.get("items")]
    spoken = {signal.get("source") for signal in carried}
    held = set(round_.get("holdout") or ())
    kept = []
    for record in analysis or ():
        card = record.get("scorecard") if isinstance(record, dict) else None
        if not isinstance(card, dict) or card.get("source") in spoken or not isinstance(card.get("items"), list):
            continue
        sessions = {item.get("session") for item in card["items"] if isinstance(item, dict)}
        if held and sessions and sessions <= held:
            continue
        kept.append(card)
    return [*carried, *kept]


def joined(path: Path) -> dict:
    """`records.load(path)`: the run with its analysis, attribution and curation records and its ledger, each round
    with its `verdicts`."""
    try:
        run = load(path)
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
        raise RecordError(f"the run record {Path(path).name} could not be loaded: {_reason(exc)}") from exc
    for round_ in run.get("rounds") or ():
        if isinstance(round_, dict):
            round_["verdicts"] = verdicts(round_, round_.get("analysis"))
    return run


def labels(run: dict) -> dict[str, str]:
    """Each session the record names (a round's trials and held-out trials, and the round in progress) with the opaque
    label it goes by in the cited turns, the activity rows, its session key and its replica folder
    (`experimental.iteration.hearing.opaque`)."""
    names = set()
    for holder in (*(run.get("rounds") or ()), run.get("pending")):
        for part in ("sessions", "holdout"):
            value = holder.get(part) if isinstance(holder, dict) else None
            if isinstance(value, dict):
                names.update(str(name) for name in value)
    return {name: opaque(name) for name in sorted(names)}


def standard(worker_root: Path) -> dict | None:
    """The standard the automatic assessor held the rounds to, as the simulation wrote it when the run ended: each
    criterion with its source, strength and provenance, the norms it was derived from, and its model calls by label.
    None when the run kept no standard (yet)."""
    path = Path(worker_root) / "standard.json"
    if not path.is_file() or path.is_symlink():
        return None
    if path.stat().st_size > STANDARD_LIMIT:
        return {"error": f"standard.json is larger than {STANDARD_LIMIT} bytes", "criteria": [], "derived_from": []}
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        return {"error": _reason(exc), "criteria": [], "derived_from": []}
    if not isinstance(value, dict):
        return {"error": "standard.json holds no object", "criteria": [], "derived_from": []}
    calls: dict[str, int] = {}
    for row in value.get("trace") or ():
        if isinstance(row, dict) and row.get("event") == "model.call":
            label = str(row.get("label") or "")
            calls[label] = calls.get(label, 0) + 1
    fields = ("id", "text", "source", "strength", "provenance", "situation", "acceptance")
    return redact(
        {
            "criteria": [
                {key: row.get(key, "") for key in fields}
                for row in value.get("criteria") or ()
                if isinstance(row, dict) and row.get("id")
            ],
            "derived_from": [str(name) for name in value.get("derived_from") or ()],
            "calls": calls,
        }
    )


def boundaries(worker_root: Path) -> dict | None:
    """The compartment log: every enter, admit, violation and leave row, the last `BOUNDARY_ROWS` of them, with each
    role's counts and every violation however old. None when the run kept no log."""
    path = Path(worker_root) / "boundaries.jsonl"
    if not path.is_file() or path.is_symlink():
        return None
    rows, violations, counts = [], [], {}
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError as exc:
        return {"error": _reason(exc), "rows": [], "violations": [], "counts": {}, "total": 0}
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict):
            continue
        kept = {
            "time": row.get("time") if isinstance(row.get("time"), (int, float)) else None,
            "role": str(row.get("role") or ""),
            "event": str(row.get("event") or ""),
            "where": str(row.get("where") or ""),
            "hits": [str(hit) for hit in row.get("hits") or ()],
        }
        role = counts.setdefault(kept["role"], {})
        role[kept["event"]] = role.get(kept["event"], 0) + 1
        rows.append(kept)
        if kept["event"] == "violation":
            violations.append(kept)
    return redact({"rows": rows[-BOUNDARY_ROWS:], "violations": violations, "counts": counts, "total": len(rows)})


def origins(worker_root: Path) -> dict[str, dict]:
    """Each material the run's scenario did not take as given, by name, with its origin (induced or researched), whether
    the party confirmed it and the ids of the rules or findings it holds, as the run's settings keep the research
    stage's provenance. A material it does not name was given by the party."""
    path = Path(worker_root) / "settings.json"
    if not path.is_file() or path.is_symlink() or path.stat().st_size > STANDARD_LIMIT:
        return {}
    try:
        settings = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    provenance = settings.get("provenance") if isinstance(settings, dict) else None
    materials = provenance.get("materials") if isinstance(provenance, dict) else None
    return {
        str(name): {
            "origin": str(row.get("origin") or "given"),
            "confirmed": row.get("confirmed") is not False,
            "items": [str(item) for item in row.get("items") or ()],
        }
        for name, row in (materials or {}).items()
        if isinstance(row, dict)
    }


def annex(worker_root: Path) -> dict:
    """The run directory's files beside the record, under the keys the pages read them by."""
    return {"standard": standard(worker_root), "boundaries": boundaries(worker_root), "origins": origins(worker_root)}


def _scoped(worker_root: Path, relative: str) -> list[Path] | None:
    """`relative` under the worker root, or under every scope of a composite curation in progress; None when its
    checkpoint cannot be read."""
    checkpoint = worker_root / "curation" / "composition.json"
    paths = [worker_root / relative]
    if checkpoint.is_file() and checkpoint.resolve().is_relative_to(worker_root.resolve()):
        try:
            directory = Path(json.loads(checkpoint.read_text())["directory"])
            if directory.resolve().is_relative_to(worker_root.resolve()):
                paths = list(directory.glob(f"*/{relative}"))
        except (OSError, ValueError, KeyError, TypeError):
            return None
    return [path for path in paths if path.is_file() and path.resolve().is_relative_to(worker_root.resolve())]


def progress_path(worker_root: Path) -> Path | None:
    """The Curator's live progress file: the root's, or in a composite curation the scope's written last."""
    paths = _scoped(worker_root, "progress/curation.json")
    return max(paths, key=lambda path: path.stat().st_mtime) if paths else None


def pending_stage(worker_root: Path) -> str | None:
    """The stage a paused curation stopped at, from its checkpoint: `diagnose` while it holds a paused attribution,
    else its generation's stage."""
    paths = _scoped(worker_root, "curation/pending.json")
    if not paths:
        return None
    try:
        pending = json.loads(max(paths, key=lambda path: path.stat().st_mtime).read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(pending, dict):
        return None
    if pending.get("attribution_state"):
        return "diagnose"
    return (pending.get("state") or {}).get("stage")


def _scope_name(worker_root: Path, folder: str) -> str:
    """The harness a composite curation's scope folder revises: the child its checkpoint maps the folder to, or the
    folder's own name (`root`)."""
    try:
        scopes = json.loads((worker_root / "curation" / "composition.json").read_text()).get("scopes")
    except (OSError, ValueError, AttributeError):
        scopes = None
    named = (
        {value: name for name, value in scopes.items() if isinstance(value, str)} if isinstance(scopes, dict) else {}
    )
    return named.get(folder, folder)


def curator_progress(worker_root: Path) -> dict | None:
    """The Curator's live progress file, which it rewrites before every model call and after every validation; in a
    composite curation, the scope written last, named by the harness it revises, with the counts of every scope."""
    path = progress_path(worker_root)
    if path is None:
        return None
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(value, dict):
        return None
    if path.parent.parent != worker_root:
        scope = path.parent.parent
        value["scope"] = _scope_name(worker_root, scope.name)
        rows = []
        for other in scope.parent.glob("*/progress/curation.json"):
            if not other.resolve().is_relative_to(worker_root.resolve()):
                continue
            try:
                rows.append(json.loads(other.read_text()))
            except (OSError, ValueError):
                continue
        for counter in ("calls", "queries", "checks", "repairs"):
            value[counter] = sum(row.get(counter, 0) for row in rows if isinstance(row, dict))
    return value
