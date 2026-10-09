"""Prepare reviewed expert information offline from a task or an explicit Scenario release."""

import argparse
import asyncio
import json
from pathlib import Path

from raven.providers.factory import make_lazy_provider, make_resolving_provider

from ..automation.employee import hire_task, withheld
from ..curator.harness import Task
from ..curator.raven_adapter.observe import ObservedProvider, Recorder
from ..scenario import Disclosure, load
from .calls import AgentCalls, SpendLimit
from .collection import CollectionLimits
from .curator import collect_for_curator, stage_materials
from .guidance import Guidance
from .information import DIMENSIONS, Answers, Request, Snapshot
from .researchers import Agent
from .scenario import release_guard, scenario_request, stage_released
from .terminal import answer as terminal_answer


async def research(args):
    root = args.output.expanduser().resolve()
    inputs = [*args.material, *args.research_reference]
    if args.scenario:
        inputs.append(args.scenario)
    for path in inputs:
        path = path.resolve()
        if root.is_relative_to(path) or path.is_relative_to(root):
            raise ValueError("output and input materials must be separate trees")
    previous = (
        Snapshot.model_validate_json(args.previous_information.read_text()) if args.previous_information else None
    )
    answer_set = Answers.model_validate_json(args.answers_file.read_text()) if args.answers_file else None
    answers = answer_set.answers if answer_set else {}
    answers_version = answer_set.version if answer_set else None
    scenario = load(args.scenario) if args.scenario else None
    released = ()
    if scenario is not None:
        released = (
            tuple(args.release)
            if args.release is not None
            else Disclosure.of(
                args.disclose,
                materials=scenario.handed,
                initial=scenario.exchange.initial,
                plans=scenario.exchange.plans,
            ).opening
        )
        request = scenario_request(
            scenario,
            released,
            previous=previous,
            answers=answers,
            answers_version=answers_version,
            focus=tuple(args.focus),
        )
        task = Task(text=scenario.situation.profile)
    else:
        task = Task(text=args.task_file.read_text().strip())
        request = Request(
            objective=f"Prepare expert information for this task: {task.text}",
            context={"business_task": task.text},
            previous=previous,
            answers=answers,
            answers_version=answers_version,
            focus=tuple(args.focus),
        )
    if args.research_guidance:
        request = request.model_copy(
            update={"guidance": Guidance.model_validate_json(args.research_guidance.read_text()).groups}
        )
    root.mkdir(parents=True, mode=0o700, exist_ok=False)
    (root / "workdir").mkdir()
    worker = hire_task(
        task, args.config, workdir=root / "workdir", root=root, **({"withheld": withheld(scenario)} if scenario else {})
    )
    materials = stage_released(scenario, released, worker.baseline.config.workspace_path) if scenario else ()
    materials += stage_materials(args.material, worker.baseline.config.workspace_path)
    guard = release_guard(scenario, released, log=root / "boundaries.jsonl") if scenario else None
    factory = (
        make_resolving_provider
        if args.model or (args.research == "exchange" and args.research_model)
        else make_lazy_provider
    )
    native = (
        AgentCalls(
            Agent(args.collector, model=args.model, effort=args.collection_effort, timeout=args.timeout),
            root / "model-calls",
        )
        if args.collector != "provider"
        else ObservedProvider(
            SpendLimit(factory(worker.baseline.config), args.spend_limit)
            if args.spend_limit
            else factory(worker.baseline.config),
            Recorder(root / "provider.jsonl"),
        )
    )
    provider = native
    if guard is not None:
        provider = guard.provider(provider)

    answerer = terminal_answer if args.interactive else None
    if getattr(args, "answer_material", None):
        from ..simulation.information import CounterpartAnswers

        if scenario is None:
            raise ValueError("simulated answers require a Scenario")
        answerer = CounterpartAnswers(
            native,
            scenario,
            args.answer_material,
            released,
            records=root / "counterpart-answers",
            model=args.model,
            timeout=args.timeout,
        )

    async with worker:
        result = await collect_for_curator(
            worker,
            provider,
            request,
            materials=materials,
            research_references=tuple(args.research_reference),
            records=root / "information",
            model=args.model,
            effort=args.collection_effort,
            researcher=None if args.research == "none" else args.research,
            research_model=args.research_model,
            research_effort=getattr(args, "research_effort", None),
            research_budget=args.research_budget,
            ask=answerer,
            wait_for_input=args.wait_for_input,
            admit=guard.check if guard else None,
            limits=CollectionLimits(
                research_tasks=args.research_tasks,
                timeout=args.timeout,
                research_window=args.research_window,
                research_waves=args.research_waves,
                total_timeout=args.collection_timeout,
                research_revisions=args.research_revisions,
                research_questions=args.research_questions,
                reserve=args.submission_reserve,
            ),
        )
    (root / "result.json").write_text(result.model_dump_json(indent=2))
    spent = getattr(getattr(native, "_provider", None), "spent", None)
    return {
        "status": result.status,
        "stop_reason": result.stop_reason,
        **({"collector_cost_usd": round(spent, 4)} if isinstance(spent, float) else {}),
        "version": result.snapshot.identity,
        "result": str(root / "result.json"),
    }


def cli():
    parser = argparse.ArgumentParser(
        description="Prepare expert information; output is a reviewed result, not a Scenario directory."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--scenario", type=Path)
    source.add_argument("--task-file", type=Path)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--material", type=Path, action="append", default=[])
    parser.add_argument("--release", nargs="*", help="Explicit eligible Scenario materials for this preparation")
    parser.add_argument("--disclose", default="staged", help="Scenario opening disclosure when --release is absent")
    parser.add_argument("--research-reference", type=Path, action="append", default=[])
    parser.add_argument("--research-guidance", type=Path)
    parser.add_argument("--previous-information", type=Path)
    parser.add_argument("--answers-file", type=Path)
    parser.add_argument("--focus", nargs="+", choices=DIMENSIONS, default=list(DIMENSIONS))
    parser.add_argument("--research", choices=("exchange", "claude", "codex", "none"), default="exchange")
    parser.add_argument("--model")
    parser.add_argument("--collector", choices=("provider", "claude", "codex"), default="provider")
    parser.add_argument(
        "--spend-limit",
        type=float,
        help="Dollar cap on the provider collector's reported cost; the run stops with its records when reached",
    )
    parser.add_argument("--collection-effort", choices=("low", "medium", "high", "xhigh", "max"), default="high")
    parser.add_argument(
        "--collection-timeout",
        type=float,
        default=3600,
        help="Overall collection deadline, including research and review",
    )
    parser.add_argument("--research-revisions", type=int, default=1)
    parser.add_argument("--research-questions", type=int, default=2, help="Questions one research group may carry")
    parser.add_argument(
        "--submission-reserve",
        type=float,
        default=900,
        help="Seconds of the collection deadline kept for submitting the description and its review",
    )
    parser.add_argument("--research-model")
    parser.add_argument("--research-effort", choices=("low", "medium", "high", "xhigh", "max"))
    parser.add_argument(
        "--research-budget", type=float, help="Optional Claude CLI monetary cap; omitted for subscription use"
    )
    parser.add_argument("--research-tasks", type=int, default=3, help="Maximum concurrent research groups")
    parser.add_argument("--research-window", type=float, default=1800, help="Seconds each research group may take")
    parser.add_argument("--research-waves", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument(
        "--wait-for-input", action="store_true", help="Stop with needs_input while asked user questions are unanswered"
    )
    answers = parser.add_mutually_exclusive_group()
    answers.add_argument("--interactive", action="store_true")
    answers.add_argument(
        "--answer-material", nargs="+", help="Scenario material the simulated counterpart may use to answer questions"
    )
    args = parser.parse_args()
    if not args.scenario and args.release is not None:
        parser.error("--release requires --scenario")
    if args.answer_material and not args.scenario:
        parser.error("--answer-material requires --scenario")
    print(json.dumps(asyncio.run(research(args)), indent=2))


if __name__ == "__main__":
    cli()
