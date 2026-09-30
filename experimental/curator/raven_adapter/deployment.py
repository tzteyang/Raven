"""Host-owned child baselines, immutable launch definitions and native registration bindings."""

import json
import os
import shlex
import sys
from dataclasses import dataclass, field
from pathlib import Path

from raven.config.schema import ThirdPartyAcpSubagentConfig

from ..harness import Artifact, Plan
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
        }

    @classmethod
    def restore(cls, value):
        return cls(
            Baseline.restore(value["baseline"]),
            Artifact.model_validate(value["artifact"]),
            Plan.model_validate(value["plan"]) if value.get("plan") else None,
            value.get("grants", {}),
            Artifact.model_validate(value["original"]) if "original" in value else None,
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
            elif submitted is not None:
                child.plan = submitted.plan
        if proposed == worker.artifact and all(
            revised[name].artifact == child.artifact for name, child in previous.items()
        ):
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
        worker.last_plan = candidate.plan
        worker.last_attribution = getattr(candidate, "attribution", None)
        worker.last_selection = getattr(candidate, "selection", None)
        worker.last_children = {
            name: submitted for name, submitted in (children or {}).items() if submitted is not None
        }
        worker._preview = None
        return installed


def child_artifact(child, candidate, inspection, *, restoring=False):
    """Resolve one proposed child version for both copied validation and real activation."""
    from .materialize import extend_artifact

    if candidate is not None:
        inspection.declaration.validate(candidate)
    delta = child.original if restoring else (candidate.artifact if candidate else Artifact(values={}))
    proposed = child.original if restoring else extend_artifact(child.artifact, delta)
    return proposed
