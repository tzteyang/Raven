"""Host-owned child baselines, immutable launch definitions and native registration bindings."""

import base64
import hashlib
import json
import os
import shlex
import sys
from dataclasses import dataclass, field
from pathlib import Path

from raven.config.schema import ThirdPartyAcpSubagentConfig

from ..harness import Artifact, Commitment, Plan
from ..harness.commitments import apply, withdraw
from .baselines import Baseline
from .inspection import fingerprint
from .materialize import _write


@dataclass
class Child:
    """One existing child Harness and the current implementation owned by its deployment."""

    baseline: Baseline
    artifact: Artifact = field(default_factory=lambda: Artifact(values={}))
    plan: Plan | None = None
    grants: dict = field(default_factory=dict)
    original: Artifact | None = None
    commitments: tuple[Commitment, ...] = ()

    def __post_init__(self):
        if set(self.grants) - {"names", "fields", "phases"}:
            raise ValueError("unknown child authoring grant")
        self.original = (self.artifact if self.original is None else self.original).model_copy(deep=True)
        self.baseline = Baseline.restore(self.baseline.export())
        self.baseline.hosting = "acp"
        self.baseline.allow_delegation = False

    def export(self):
        return {
            "baseline": self.baseline.export(),
            "artifact": self.artifact.model_dump(mode="json"),
            "plan": self.plan.model_dump(mode="json") if self.plan else None,
            "grants": self.grants,
            "original": self.original.model_dump(mode="json"),
            "commitments": [item.model_dump(mode="json") for item in self.commitments],
        }

    @classmethod
    def restore(cls, value):
        return cls(
            Baseline.restore(value["baseline"]),
            Artifact.model_validate(value["artifact"]),
            Plan.model_validate(value["plan"]) if value.get("plan") else None,
            value.get("grants", {}),
            Artifact.model_validate(value["original"]) if "original" in value else None,
            tuple(Commitment.model_validate(item) for item in value.get("commitments", ())),
        )


def child_directory(root, name):
    return Path(root) / "children" / fingerprint(name)[:16]


def bind_children(baseline, children, root):
    """Bind existing roster names to their checked full-Harness launch definition."""
    if not children:
        return baseline
    bound = Baseline.restore(baseline.export())
    rows = {row.name: row for row in bound.config.subagents.agents}
    repository = Path(__file__).resolve().parents[3]
    for name, child in children.items():
        directory = child_directory(root, name)
        content = {
            "baseline": child.baseline.export(),
            "artifact": child.artifact.model_dump(mode="json"),
            "state_dir": str(directory),
            "grants": child.grants,
        }
        definition = directory / "versions" / fingerprint(content) / "deployment.json"
        encoded = json.dumps(content, ensure_ascii=False, indent=2).encode()
        if definition.exists() and definition.read_bytes() != encoded:
            raise ValueError("a versioned child definition changed after preparation")
        if not definition.exists():
            _write(definition, encoded)
        previous = rows.get(name)
        inherited = dict(getattr(previous, "env", None) or {})
        inherited["PYTHONPATH"] = os.pathsep.join(filter(None, (str(repository), inherited.get("PYTHONPATH"))))
        inherited["RAVEN_HOME"] = str(directory / "native")
        command = shlex.join(
            [sys.executable, "-m", "experimental.curator.raven_adapter.hosting.acp", "--deployment", str(definition)]
        )
        update = {"command": command, "cwd": str(child.baseline.workdir), "env": inherited}
        rows[name] = (
            previous.model_copy(update=update)
            if isinstance(previous, ThirdPartyAcpSubagentConfig)
            else ThirdPartyAcpSubagentConfig(
                name=name,
                **update,
                enabled=getattr(previous, "enabled", True),
                description=getattr(previous, "description", "") or f"Task Harness for {name}",
            )
        )
    bound.config.subagents.agents = list(rows.values())
    return bound


async def activate(worker, candidate, children=None):
    """Preview code-produced effects, then atomically activate one idle deployment."""
    import asyncio

    from .content import check_owners, snapshot
    from .inspection import Inspection
    from .materialize import extend_artifact, restore_content
    from .preparation import PreparedHarness

    async with worker._lock:
        if not await worker._exchange({"operation": "idle"}):
            raise ValueError("Harness activation requires an idle root and completed child calls")
        current = await worker._inspect()
        candidate = worker._accept(candidate, current)
        proposed = extend_artifact(worker.artifact, candidate.artifact)
        commitments = apply(worker.commitments, candidate.plan.commitments)
        previous = {name: Child.restore(child.export()) for name, child in worker.children.items()}
        revised = {name: Child.restore(child.export()) for name, child in worker.children.items()}
        if set(children or {}) - set(revised):
            raise ValueError("candidate names a child Harness outside this deployment")
        old_children = {}
        for name, child in revised.items():
            report = await worker._exchange({"operation": "inspect_agent", "agent": name})
            inspection = Inspection.restore(report["inspection"])
            old_children[name] = PreparedHarness.model_validate(inspection.facts.get("prepared", {}))
            submitted = (children or {}).get(name)
            restoring = name in (children or {}) and submitted is None
            child.artifact = child_artifact(child, submitted, inspection, restoring=restoring)
            if restoring:
                child.plan = None
                child.commitments = withdraw(child.commitments, "the child Harness returned to its original version")
            elif submitted is not None:
                child.plan = submitted.plan
                child.commitments = apply(child.commitments, submitted.plan.commitments)
        if proposed == worker.artifact and all(
            revised[name].artifact == child.artifact for name, child in previous.items()
        ):
            # Nothing to restart, but the curation still happened: its plan and commitments become the current ones.
            for name, child in revised.items():
                worker.children[name].plan, worker.children[name].commitments = child.plan, child.commitments
            _settle(worker, candidate, children, commitments)
            return current
        async with worker._validation_copy(candidate, inspection=current, children=children) as trial:
            prepared = trial.prepared
            prepared_children = {}
            for name in revised:
                report = await trial.agent_state(name)
                prepared_children[name] = PreparedHarness.model_validate(
                    report["inspection"]["facts"].get("prepared", {})
                )
        check_owners(
            worker.baseline,
            prepared,
            {name: (child.baseline, prepared_children[name]) for name, child in revised.items()},
        )
        owners = [(worker.baseline, worker.prepared, prepared, worker.area)]
        owners.extend(
            (child.baseline, old_children[name], prepared_children[name], child_directory(worker.area, name))
            for name, child in revised.items()
        )
        saved = {}
        files = {}
        for baseline, old_prepared, next_prepared, directory in owners:
            saved.setdefault(baseline.config.workspace_path, {}).update(
                snapshot(baseline.config.workspace_path, old_prepared.files().keys() | next_prepared.files().keys())
            )
            for name in (
                "assembly/content-state.json",
                "memory.json",
                "planning.json",
                "capability.json",
                "action.json",
            ):
                path = directory / name
                files[path] = path.read_bytes() if path.exists() else None
        old_artifact, old_prepared = worker.artifact, worker.prepared
        try:
            try:
                await worker._close()
            finally:
                for _, _, _, directory in owners:
                    for name in ("memory.json", "planning.json", "capability.json", "action.json"):
                        path = directory / name
                        files[path] = path.read_bytes() if path.exists() else None
            worker.artifact, worker.children = proposed, revised
            await worker._start()
            installed = await worker._inspect()
            for name, child in worker.children.items():
                report = await worker._exchange({"operation": "inspect_agent", "agent": name})
                if report["revision"] != fingerprint(child.artifact.model_dump(mode="json")):
                    raise ValueError(f"child {name} did not activate the expected strategy artifact")
        except BaseException as exc:
            try:
                await worker._close()
            finally:
                for home, content in saved.items():
                    restore_content(home, content)
                for path, content in files.items():
                    if content is None:
                        path.unlink(missing_ok=True)
                    else:
                        _write(path, content)
                worker.artifact, worker.children, worker.prepared = old_artifact, previous, old_prepared
                if not isinstance(exc, asyncio.CancelledError):
                    await worker._start()
            raise
        _settle(worker, candidate, children, commitments)
        worker._preview = None
        return installed


def _settle(worker, candidate, children, commitments):
    """Make an activated curation the worker's current one: its plan, the attribution and selection it came from,
    the child candidates it installed and the commitment list it leaves."""
    worker.last_plan = candidate.plan
    worker.last_attribution = getattr(candidate, "attribution", None)
    worker.last_selection = getattr(candidate, "selection", None)
    worker.last_children = {name: submitted for name, submitted in (children or {}).items() if submitted is not None}
    worker.commitments = commitments


_STATE_FILES = ("assembly/content-state.json", "memory.json", "planning.json", "capability.json", "action.json")


@dataclass(frozen=True)
class Kept:
    """One activation as it stood, enough to return to it exactly after later activations replaced it."""

    artifact: Artifact
    prepared: object
    plan: Plan | None
    attribution: object
    selection: object
    children: dict
    commitments: tuple[Commitment, ...]
    content: dict
    files: dict


async def keep(worker) -> Kept:
    """Record the active single-layer deployment: artifact, prepared content, strategy state, the plan behind it and
    the commitments it carries out."""
    from .content import snapshot

    async with worker._lock:
        if worker.children:
            raise ValueError("keeping a deployment with child Harnesses is not supported")
        files = {}
        for name in _STATE_FILES:
            path = worker.area / name
            files[path] = path.read_bytes() if path.exists() else None
        return Kept(
            worker.artifact,
            worker.prepared,
            worker.last_plan,
            worker.last_attribution,
            worker.last_selection,
            dict(worker.last_children),
            worker.commitments,
            snapshot(worker.baseline.config.workspace_path, worker.prepared.files().keys()),
            files,
        )


async def reinstate(worker, kept: Kept):
    """Activate a kept deployment again exactly as it was. Unlike `activate`, nothing is merged into the current
    artifact: content and strategy state later revisions wrote are undone, then the worker restarts."""
    from ..harness.artifact import relative_path
    from .materialize import restore_content

    async with worker._lock:
        if not await worker._exchange({"operation": "idle"}):
            raise ValueError("reinstating a deployment requires an idle worker")
        home = worker.baseline.config.workspace_path
        stale = {home / relative_path(name): (None, 0) for name in worker.prepared.files()}
        await worker._close()
        restore_content(home, {**stale, **kept.content})
        for path, content in kept.files.items():
            if content is None:
                path.unlink(missing_ok=True)
            else:
                _write(path, content)
        worker.artifact, worker.prepared = kept.artifact, kept.prepared
        await worker._start()
        installed = await worker._inspect()
        worker.last_plan, worker.last_attribution, worker.last_selection = kept.plan, kept.attribution, kept.selection
        worker.last_children = dict(kept.children)
        worker.commitments = kept.commitments
        worker._preview = None
        return installed


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


async def save(worker, path: Path) -> dict:
    """Write the active deployment (`keep`) to `path` as JSON with its checksum, paths relative to the worker's home
    and area, so `load` can put it back in this worker or in a new one hired on the same task."""
    from .observe import plain

    kept = await keep(worker)
    home = worker.baseline.config.workspace_path

    def encoded(content):
        return None if content is None else base64.b64encode(content).decode()

    value = {
        "artifact": kept.artifact.model_dump(mode="json"),
        "prepared": kept.prepared.model_dump(mode="json"),
        "plan": kept.plan.model_dump(mode="json") if kept.plan else None,
        "attribution": plain(kept.attribution),
        "selection": plain(kept.selection),
        "children": plain(kept.children),
        "commitments": [item.model_dump(mode="json") for item in kept.commitments],
        "content": {str(name.relative_to(home)): [encoded(data), mode] for name, (data, mode) in kept.content.items()},
        "state": {str(name.relative_to(worker.area)): encoded(data) for name, data in kept.files.items()},
        "revision": worker.revision_id,
        "task": worker.baseline.task.model_dump(mode="json"),
    }
    value["sha256"] = _digest(value)
    _write(Path(path), json.dumps(value, ensure_ascii=False).encode())
    return value


async def load(worker, path: Path) -> Kept:
    """Put the deployment `save` wrote back into `worker` (`reinstate`); the worker must hold the same task, id and
    text, since the saved strategy state is bound to it."""
    from ..harness import Task
    from .preparation import PreparedHarness

    value = json.loads(Path(path).read_text())
    if _digest({key: item for key, item in value.items() if key != "sha256"}) != value.get("sha256"):
        raise ValueError("the saved deployment does not match its checksum")
    if Task.model_validate(value["task"]) != worker.baseline.task:
        raise ValueError("the saved deployment belongs to another task")
    home = worker.baseline.config.workspace_path

    def inside(root: Path, name: str) -> Path:
        found = (root / name).resolve()
        if not found.is_relative_to(root.resolve()):
            raise ValueError(f"a saved path leaves its folder: {name}")
        return found

    def decoded(content):
        return None if content is None else base64.b64decode(content)

    kept = Kept(
        artifact=Artifact.model_validate(value["artifact"]),
        prepared=PreparedHarness.model_validate(value["prepared"]),
        plan=Plan.model_validate(value["plan"]) if value["plan"] else None,
        attribution=value["attribution"],
        selection=value["selection"],
        children=value["children"],
        commitments=tuple(Commitment.model_validate(item) for item in value.get("commitments", ())),
        content={inside(home, name): (decoded(data), mode) for name, (data, mode) in value["content"].items()},
        files={inside(worker.area, name): decoded(data) for name, data in value["state"].items()},
    )
    await reinstate(worker, kept)
    if worker.revision_id != value["revision"]:
        raise ValueError("the loaded deployment is not the revision that was saved")
    return kept


def child_artifact(child, candidate, inspection, *, restoring=False):
    """Resolve one proposed child version for both copied validation and real activation."""
    from .materialize import extend_artifact

    if candidate is not None:
        inspection.declaration.validate(candidate)
    delta = child.original if restoring else (candidate.artifact if candidate else Artifact(values={}))
    proposed = child.original if restoring else extend_artifact(child.artifact, delta)
    return proposed
