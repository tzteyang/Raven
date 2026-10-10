"""Construct an expert from interaction inputs with optional guidance for grouped research."""

import argparse
import asyncio
import json
import math
from dataclasses import dataclass
from pathlib import Path

from experimental.cultivation.collector.collection import CollectionLimits
from experimental.cultivation.collector.curator import (
    INFORMATION_FILE,
    collect_for_curator,
    handover_information,
    information_feedback,
    stage_materials,
)
from experimental.cultivation.collector.guidance import Guidance
from experimental.cultivation.collector.information import (
    DIMENSIONS,
    Answers,
    Dimension,
    Request,
    ResearchGuide,
    Result,
    Snapshot,
)
from experimental.cultivation.collector.terminal import answer as terminal_answer
from experimental.cultivation.employee import AREA, HOME, hire_task
from experimental.harness.contract import Task
from experimental.harness.curator.generation.run import Limits
from experimental.harness.curator.workflow import improve
from experimental.harness.raven_adapter.exploration import Withheld
from experimental.harness.raven_adapter.observe import ObservedProvider, Recorder, plain
from experimental.harness.raven_adapter.probe import exercise_translations
from raven.core.config_stack import load_runtime_config
from raven.providers.factory import make_lazy_provider, make_resolving_provider


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

    def task(self) -> Task:
        """Bind the worker's business mission, without Curator construction instructions."""
        return Task(text=self.description.strip() or f"Assist users according to the supplied {self.name} profile.")

    @staticmethod
    def curation_request(objective: str | None = None) -> str:
        """Ask Curator to build the harness; this text is not a customer deliverable."""
        text = (
            f"Build the expert from the reviewed information at {INFORMATION_FILE}.\n"
            "Use its professional scope, knowledge, methods, judgement, cases and performance expectations. "
            "Respect stated evidence limits, unresolved questions and operating prerequisites. "
            "Interaction inputs remain available for inspection and informed adoption. "
            "Research-only guidance suggests questions and is not established expert knowledge.\n"
            "Decide the division of work using the available root and child Harnesses. Explain what runs "
            "locally, what uses existing capabilities and what needs customization. "
            "Report unsupported requirements explicitly.\n"
            "Deliverables the user asks for as files are produced as files and handed over with the file "
            "delivery tool; a reply that carries the content inline, or that describes a file not delivered, "
            "is not delivery. Make the Harness hold this: a reply claiming delivery without a delivered file is "
            "refused or revised, not a stylistic preference."
        )
        if objective:
            text += f"\nOwner objective:\n{objective}"
        return text


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
    expert: Expert | None,
    config: Path,
    root: Path,
    *,
    objective: str | None = None,
    requests: tuple[str, ...] = (),
    limits: Limits = Limits(),
    curation_timeout: float = 900,
    request_timeout: float = 300,
    collection_limits: CollectionLimits = CollectionLimits(),
    researcher: str | None = "exchange",
    research_model: str | None = None,
    research_effort: str | None = None,
    research_budget: float | None = None,
    ask=None,
    wait_for_input: bool = False,
    task: Task | None = None,
    materials: tuple[Path, ...] = (),
    research_references: tuple[Path, ...] = (),
    guidance: tuple[ResearchGuide, ...] = (),
    previous: Snapshot | None = None,
    focus: tuple[Dimension, ...] = DIMENSIONS,
    answers: dict[str, str] | None = None,
    answers_version: str | None = None,
    prepared: Result | None = None,
) -> dict:
    """Run one fresh, bounded curation and optional real tasks; failures retain their evidence."""
    root = root.expanduser().resolve()
    if any(not math.isfinite(value) or value <= 0 for value in (curation_timeout, request_timeout)):
        raise ValueError("timeouts must be finite and positive")
    if task is None:
        if expert is None:
            raise ValueError("provide a business task or an expert package as an interaction input")
        task = expert.task()
    if not task.text.strip():
        raise ValueError("the business task must not be empty")
    material_paths = tuple(dict.fromkeys((*((expert.root,) if expert else ()), *materials)))
    for source in (*material_paths, *research_references):
        source = Path(source).resolve()
        if root.is_relative_to(source) or source.is_relative_to(root):
            raise ValueError("run output and input sources must be separate trees")
    collection_request = Request(
        objective=objective or f"Prepare expert information for this task: {task.text}",
        context={"business_task": task.text},
        previous=previous,
        focus=focus,
        answers=answers or {},
        answers_version=answers_version,
        guidance=guidance,
    )
    root.mkdir(parents=True, mode=0o700, exist_ok=False)
    work = root / "workdir"
    work.mkdir()
    withheld = Withheld(
        paths=("tests/test_simulation_*", "experimental/docs/expert-package*", "experimental/docs/curator-docs*"),
        markers=(b"experimental.simulation", b"experimental/simulation", *((expert.name.encode(),) if expert else ())),
    )
    stage = "prepare"
    report = {"expert": expert.name if expert else "custom", "requests_completed": 0, "observed_child_executions": []}
    _save(root, "status.json", {**report, "stage": stage})
    try:
        model = load_runtime_config(str(config.resolve()), str(root / AREA / HOME)).agents.defaults.model
        report["model"] = model
        worker = hire_task(
            task,
            config,
            workdir=work,
            root=root,
            subagent_model=model,
            timeout=request_timeout,
            withheld=withheld,
        )
        staged = stage_materials(material_paths, worker.baseline.config.workspace_path)
        _save(
            root,
            "inputs.json",
            {
                "materials": [
                    {"source": str(source), "staged": str(target), "purpose": "interaction"}
                    for source, target in zip(material_paths, staged)
                ],
                "research_references": [
                    {"source": str(path), "purpose": "research_guidance"} for path in research_references
                ],
            },
        )
        setup = {
            **report,
            "limits": limits,
            "task": worker.baseline.task,
            "curation_request": Expert.curation_request(objective),
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
            stage = "information"
            _save(root, "status.json", {**report, "stage": stage})
            factory = make_resolving_provider if researcher == "exchange" and research_model else make_lazy_provider
            provider = ObservedProvider(factory(worker.baseline.config), Recorder(root / "provider.jsonl"))
            information = await collect_for_curator(
                worker,
                provider,
                collection_request,
                materials=staged,
                research_references=research_references,
                records=root / "information",
                ask=ask,
                model=model,
                researcher=researcher,
                research_model=research_model,
                research_effort=research_effort,
                research_budget=research_budget,
                limits=collection_limits,
                wait_for_input=wait_for_input,
                replay=prepared,
            )
            report["information_version"] = information.snapshot.identity
            report["information_status"] = information.status
            if not information.ready:
                report.update(status=information.status, stage=stage)
                _save(root, "result.json", report)
                _save(root, "status.json", report)
                return report
            handover_information(worker, information)
            stage = "curation"
            _save(root, "status.json", {**report, "stage": stage})
            async with asyncio.timeout(curation_timeout):
                generated = await improve(
                    worker,
                    provider,
                    model=model,
                    limits=limits,
                    probe=exercise_translations,
                    feedback={
                        "source": "owner",
                        "text": Expert.curation_request(objective),
                        "information": information_feedback(information),
                    },
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
                    execution = await worker.run(request, session_key=f"expert:{worker.baseline.task.id}")
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
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--expert", type=Path, help="Product package supplied as an interaction input")
    target.add_argument("--task-file", type=Path, help="The expert's business task, independently of any product case")
    parser.add_argument(
        "--material", type=Path, action="append", default=[], help="Interaction input file or directory"
    )
    parser.add_argument(
        "--research-reference",
        type=Path,
        action="append",
        default=[],
        help="Optional product-case material used only to guide research",
    )
    parser.add_argument("--research-guidance", type=Path, help="Prepared guidance.json from an earlier research step")
    parser.add_argument(
        "--information", type=Path, help="Reviewed offline result matching this task, inputs and environment"
    )
    parser.add_argument(
        "--previous-information", type=Path, help="An existing snapshot.json for focused supplementation"
    )
    parser.add_argument("--focus", choices=DIMENSIONS, nargs="+", default=list(DIMENSIONS))
    parser.add_argument(
        "--answers-file", type=Path, help="JSON object with version and answers for the previous snapshot"
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--objective-file", type=Path)
    parser.add_argument("--request-file", type=Path, action="append", default=[])
    parser.add_argument("--curator-calls", type=int, default=24)
    parser.add_argument("--curator-queries", type=int, default=24)
    parser.add_argument(
        "--curator-stage-queries",
        type=int,
        default=12,
        help="Exploration calls one Curator stage may spend out of --curator-queries before it must submit",
    )
    parser.add_argument("--curator-checks", type=int, default=2)
    parser.add_argument("--curator-repairs", type=int, default=2)
    parser.add_argument(
        "--curator-call-timeout",
        type=float,
        default=600,
        help="Seconds one Curator model call may take; a design call over a large context exceeds the 180 s default",
    )
    parser.add_argument("--curation-timeout", type=float, default=900)
    parser.add_argument("--request-timeout", type=float, default=300)
    parser.add_argument("--information-reviews", type=int, default=2)
    parser.add_argument(
        "--research-tasks", type=int, default=3, help="Maximum concurrent research groups, not a required count"
    )
    parser.add_argument(
        "--guidance-calls", type=int, default=3, help="Maximum calls for optional case-guidance extraction"
    )
    parser.add_argument("--research", choices=("exchange", "claude", "codex", "none"), default="exchange")
    parser.add_argument("--research-model")
    parser.add_argument("--research-effort", choices=("low", "medium", "high", "xhigh", "max"))
    parser.add_argument(
        "--research-budget", type=float, help="Optional Claude CLI monetary cap; omitted for subscription use"
    )
    parser.add_argument("--research-window", type=float, default=1800, help="Seconds each research group may take")
    parser.add_argument("--research-waves", type=int, default=1)
    parser.add_argument("--collection-timeout", type=float, default=3600)
    parser.add_argument("--research-revisions", type=int, default=1)
    parser.add_argument("--research-questions", type=int, default=2)
    parser.add_argument("--submission-reserve", type=float, default=900)
    parser.add_argument("--interactive", action="store_true", help="Answer information questions on the terminal")
    parser.add_argument(
        "--wait-for-input", action="store_true", help="Stop with needs_input while asked user questions are unanswered"
    )
    args = parser.parse_args()
    answer_set = Answers.model_validate_json(args.answers_file.read_text()) if args.answers_file else None

    result = asyncio.run(
        run(
            Expert.load(args.expert) if args.expert else None,
            args.config,
            args.output,
            objective=args.objective_file.read_text() if args.objective_file else None,
            requests=tuple(path.read_text() for path in args.request_file),
            limits=Limits(
                max_calls=args.curator_calls,
                max_queries=args.curator_queries,
                stage_queries=args.curator_stage_queries,
                max_checks=args.curator_checks,
                max_repairs=args.curator_repairs,
                call_timeout=args.curator_call_timeout,
                max_output=14000,
            ),
            curation_timeout=args.curation_timeout,
            request_timeout=args.request_timeout,
            collection_limits=CollectionLimits(
                reviews=args.information_reviews,
                research_tasks=args.research_tasks,
                guidance_calls=args.guidance_calls,
                research_window=args.research_window,
                research_waves=args.research_waves,
                total_timeout=args.collection_timeout,
                research_revisions=args.research_revisions,
                research_questions=args.research_questions,
                reserve=args.submission_reserve,
            ),
            wait_for_input=args.wait_for_input,
            researcher=None if args.research == "none" else args.research,
            research_model=args.research_model,
            research_effort=args.research_effort,
            research_budget=args.research_budget,
            ask=terminal_answer if args.interactive else None,
            task=Task(text=args.task_file.read_text().strip()) if args.task_file else None,
            materials=tuple(args.material),
            research_references=tuple(args.research_reference),
            guidance=Guidance.model_validate_json(args.research_guidance.read_text()).groups
            if args.research_guidance
            else (),
            previous=Snapshot.model_validate_json(args.previous_information.read_text())
            if args.previous_information
            else None,
            focus=tuple(args.focus),
            answers=answer_set.answers if answer_set else None,
            answers_version=answer_set.version if answer_set else None,
            prepared=Result.model_validate_json(args.information.read_text()) if args.information else None,
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
