"""Curate supplied expert packages through the normal employee and managed child deployment."""

import argparse
import asyncio
import hashlib
import json
import math
import shutil
from dataclasses import dataclass
from pathlib import Path

from raven.core.config_stack import load_runtime_config
from raven.providers.factory import make_lazy_provider

from ..automation.employee import AREA, HOME, hire_task
from ..curator.generation.run import Limits
from ..curator.harness import Task
from ..curator.raven_adapter.exploration import Withheld
from ..curator.raven_adapter.observe import ObservedProvider, Recorder, plain
from ..curator.workflow import improve


@dataclass(frozen=True)
class Expert:
    """Original package identity and neutral entry references, without translated behavior."""

    root: Path
    name: str
    entries: dict[str, list[str]]
    description: str = ""
    manifest: str = ""

    @classmethod
    def load(cls, root: Path) -> "Expert":
        """The package at `root`, from its manifest: the one `plugin.json` in a hidden `.<product>-plugin` folder."""
        root = root.expanduser().resolve()
        found = sorted(root.glob(".*-plugin/plugin.json"))
        if len(found) != 1:
            raise ValueError(f"an expert package holds one .<product>-plugin/plugin.json manifest; found {len(found)}")
        manifest = json.loads(found[0].read_text())
        name = manifest["name"]
        if not isinstance(name, str) or not name or name in {".", ".."} or "/" in name or "\\" in name:
            raise ValueError("expert name must be one directory segment")
        entries = {}
        for kind in ("agents", "rules", "skills"):
            items = manifest.get(kind, [])
            if not isinstance(items, list) or any(not isinstance(item, str) for item in items):
                raise ValueError(f"expert {kind} entries must be a list of paths")
            entries[kind] = []
            for item in items:
                path = (root / item).resolve()
                if not path.is_relative_to(root) or not path.exists():
                    raise ValueError(f"expert {kind} entry is absent or outside its package: {item}")
                entries[kind].append(path.relative_to(root).as_posix())
        if not entries["agents"] and not entries["rules"]:
            raise ValueError("an expert needs an agent or rules entry")
        description = manifest.get("description", "")
        if not isinstance(description, str):
            raise ValueError("expert description must be text")
        return cls(root, name, entries, description, found[0].relative_to(root).as_posix())

    @property
    def material_path(self) -> str:
        return f"uploads/experts/{self.name}"

    def task(self) -> Task:
        """Bind the worker's business mission, without Curator construction instructions."""
        return Task(text=self.description.strip() or f"Assist users according to the supplied {self.name} profile.")

    def curation_request(self, objective: str | None = None) -> str:
        """Ask Curator to build the harness; this text is not a customer deliverable."""
        text = (
            f"Build the {self.name} expert from the complete product package at {self.material_path}.\n"
            f"Read its manifest {self.manifest}, referenced agent/rule documents, supplied Skills and "
            "relevant supporting files. Preserve their intended methods, workflow and reusable resources in "
            "the resulting expert. Treat product-specific commands and dependencies according to this "
            "deployment's actual capabilities; report unsupported requirements explicitly.\n"
            "Decide the division of work using the available root and child Harnesses. Explain what runs "
            "locally, what uses existing capabilities and what needs customization. The package is input "
            "material; do not run its original product installer.\n"
            f"Manifest entry paths: {json.dumps(self.entries, ensure_ascii=False)}"
        )
        if objective:
            text += f"\nOwner objective:\n{objective}"
        return text

    def stage(self, home: Path) -> dict:
        """Copy the complete package into uploads; no native Skill/profile is activated."""
        files = []
        for path in sorted(self.root.rglob("*")):
            if path.is_symlink() or not (path.is_file() or path.is_dir()):
                raise ValueError(f"expert packages require regular files/directories: {path}")
            if path.is_file():
                files.append(
                    {
                        "path": path.relative_to(self.root).as_posix(),
                        "digest": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "bytes": path.stat().st_size,
                        "mode": path.stat().st_mode & 0o777,
                    }
                )
        target = home / self.material_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(self.root, target)
        return {
            "expert": self.name,
            "source": str(self.root),
            "staged": self.material_path,
            "entries": self.entries,
            "files": files,
        }


def _save(root: Path, name: str, value) -> None:
    (root / name).write_text(json.dumps(plain(value), ensure_ascii=False, indent=2))


async def _snapshot(worker, root: Path, name: str) -> dict:
    inspection = await worker.inspect()
    children = {}
    for child_name, child in worker.children.items():
        view = await worker.inspect_agent(child_name)
        children[child_name] = {
            "identity": view.declaration.baseline,
            "facts": view.facts,
            "sources": view.sources,
            "artifact": child.artifact,
            "plan": child.plan,
        }
    _save(
        root,
        name,
        {
            "revision": worker.revision_id,
            "facts": inspection.facts,
            "context_window": inspection.facts["context_window"],
            "sources": inspection.sources,
            "artifact": worker.artifact,
            "plan": worker.last_plan,
            "children": children,
        },
    )
    return inspection.facts


async def run(
    expert: Expert,
    config: Path,
    root: Path,
    *,
    objective: str | None = None,
    requests: tuple[str, ...] = (),
    limits: Limits = Limits(),
    curation_timeout: float = 900,
    request_timeout: float = 300,
) -> dict:
    """Run one fresh, bounded curation and optional real tasks; failures retain their evidence."""
    root = root.expanduser().resolve()
    if any(not math.isfinite(value) or value <= 0 for value in (curation_timeout, request_timeout)):
        raise ValueError("timeouts must be finite and positive")
    if root.is_relative_to(expert.root) or expert.root.is_relative_to(root):
        raise ValueError("run output and source expert must be separate trees")
    root.mkdir(parents=True, mode=0o700, exist_ok=False)
    work = root / "workdir"
    work.mkdir()
    withheld = Withheld(
        paths=("tests/test_simulation_*", "experimental/docs/expert-package*", "experimental/docs/curator-docs*"),
        markers=(b"experimental.simulation", b"experimental/simulation", expert.name.encode()),
    )
    stage = "prepare"
    report = {"expert": expert.name, "requests_completed": 0, "observed_child_executions": []}
    _save(root, "status.json", {**report, "stage": stage})
    try:
        model = load_runtime_config(str(config.resolve()), str(root / AREA / HOME)).agents.defaults.model
        report["model"] = model
        worker = hire_task(
            expert.task(),
            config,
            workdir=work,
            root=root,
            subagent_model=model,
            timeout=request_timeout,
            withheld=withheld,
        )
        _save(root, "inputs.json", expert.stage(worker.baseline.config.workspace_path))
        setup = {
            **report,
            "limits": limits,
            "task": worker.baseline.task,
            "curation_request": expert.curation_request(objective),
            "configured_subagents": [
                {"name": row.name, "kind": row.kind, "enabled": row.enabled}
                for row in worker.baseline.config.subagents.agents
            ],
        }
        _save(root, "setup.json", setup)
        async with worker:
            if not worker.children:
                raise RuntimeError("the normal employee deployment did not provide managed children")
            report["prepared_children"] = list(worker.children)
            await _snapshot(worker, root, "before.json")
            report["available_children"] = list(worker.children)
            _save(root, "setup.json", {**setup, **report})
            stage = "curation"
            _save(root, "status.json", {**report, "stage": stage})
            provider = ObservedProvider(make_lazy_provider(worker.baseline.config), Recorder(root / "provider.jsonl"))
            async with asyncio.timeout(curation_timeout):
                generated = await improve(
                    worker,
                    provider,
                    model=model,
                    limits=limits,
                    feedback={"source": "owner", "text": expert.curation_request(objective)},
                )
            _save(root, "generation.json", generated)
            after = await _snapshot(worker, root, "after.json")
            report["children_requested_for_curation"] = sorted(
                {
                    node["node"]["subagent"]
                    for node in after.get("composition", {}).get("nodes", {}).values()
                    if node["requirements"]
                }
            )
            report["root_targets"] = list(worker.artifact.values)
            report["child_targets"] = {name: list(child.artifact.values) for name, child in worker.children.items()}
            stage = "execution"
            for index, request in enumerate(requests, 1):
                _save(root, "status.json", {**report, "stage": stage, "request": index})
                async with asyncio.timeout(request_timeout):
                    execution = await worker.run(request, session_key=f"expert:{expert.name}")
                _save(root, f"execution-{index}.json", {"request": request, "execution": execution})
                report["requests_completed"] = index
                report["observed_child_executions"] = sorted(
                    set(report["observed_child_executions"])
                    | {row["harness"] for row in execution.records if row["kind"] == "child.execution"}
                )
            _save(root, "observations.json", worker.records())
            report["status"] = "completed"
            report["task_validation"] = "recorded" if requests else "not_run"
    except Exception as exc:
        report.update(status="failed", stage=stage, error=f"{type(exc).__name__}: {exc}")
        _save(root, "result.json", report)
        _save(root, "status.json", report)
        raise
    _save(root, "result.json", report)
    _save(root, "status.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expert", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--objective-file", type=Path)
    parser.add_argument("--request-file", type=Path, action="append", default=[])
    parser.add_argument("--curator-calls", type=int, default=24)
    parser.add_argument("--curator-queries", type=int, default=24)
    parser.add_argument("--curator-checks", type=int, default=2)
    parser.add_argument("--curator-repairs", type=int, default=2)
    parser.add_argument("--curation-timeout", type=float, default=900)
    parser.add_argument("--request-timeout", type=float, default=300)
    args = parser.parse_args()
    result = asyncio.run(
        run(
            Expert.load(args.expert),
            args.config,
            args.output,
            objective=args.objective_file.read_text() if args.objective_file else None,
            requests=tuple(path.read_text() for path in args.request_file),
            limits=Limits(
                max_calls=args.curator_calls,
                max_queries=args.curator_queries,
                max_checks=args.curator_checks,
                max_repairs=args.curator_repairs,
                max_output=14000,
            ),
            curation_timeout=args.curation_timeout,
            request_timeout=args.request_timeout,
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
