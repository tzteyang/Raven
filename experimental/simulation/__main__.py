"""Run the travel-agency cultivation: each round the agency plays customers from its drill cards against the
digital employee, reviews the drills and speaks to the Curator, and the loop curates the employee's Harness. The
agency is the loop's assessor: it only speaks, and the base Analyst turns its words into the Curator's requirements
(see `experimental.simulation.cases.travel_agency.owner`).

The owner knows all of the scenario's materials from the start; what varies is when it hands them over, which is how
cultivation runs are told apart and what mining searches over. `--disclose` names the schedule (everything at once,
nothing ever, the initial set and then as the owner decides, or a scenario's named partition), `--partition` gives any
other partition as JSON, and `--deliver` says how a material reaches the employee (see
`experimental.harness.scenario.disclosure`). The run's settings, with its command line but without any credential or
configuration path, are written to `settings.json` beside the records.

Each model role runs on the model and effort `--model ROLE=MODEL` and `--effort ROLE=LEVEL` name for it, and a role
not named on the partner's, from `--config` (see `experimental.harness.participation.model_roles`); the resolved map is in `settings.json`.

Each round plays every drill card with freshly drawn values (see `experimental.simulation.bench.cards`) from `--seed`, so a
rule counts as held only on values the employee has not met before; arms given one seed meet the same values.
`--without` leaves materials out of the scenario altogether, for arms that differ only in what the agency owns.
Every drill runs on its own replica of the employee, made from it as the round begins and kept under `replicas/`
beside the records (see `experimental.cultivation.employee.Together`), so no drill sees another's files;
`--concurrent-drills` plays that many of a round's drills at once.

With `--isolate-as USER` the employee's process tree (its shell, children and the strategy code the Curator installs)
runs as that user from a code image and can reach only its own area of the run (`--state-dir`, which is then
required): the run refuses to start when the user can reach the run's records, the runs beside it, the repository,
the scenario or any path of `--closed` (see the cultivation-loop design, section 4.2, and `experimental/README.md`).

The agency copies the scenario's materials into the employee's skill pool as the disclosure plan releases them;
directories there with a scenario material's name are owned by the scenario and reset at the start of a run.
"""

import argparse
import asyncio
import importlib
import json
import os
import random
import sys
import tempfile
import time
from pathlib import Path

from experimental.cultivation.collector.collection import CollectionLimits
from experimental.cultivation.collector.information import Result as InformationResult
from experimental.cultivation.collector.scenario import scenario_preparer, scenario_researcher
from experimental.cultivation.counterpart.owner import SOURCE as OWNER
from experimental.cultivation.employee import (
    REPLICAS,
    baseline,
    hire,
    replicate,
    seal,
    skills,
    starting_harness,
    unseal,
    unsealed,
    workplace,
)
from experimental.harness.analyst.run import Limits as AnalystLimits
from experimental.harness.assessor.builder import RubricBuilder
from experimental.harness.assessor.guidance import GuidanceStore
from experimental.harness.assessor.introspect import Introspection
from experimental.harness.assessor.reviewer import MetaReviewer
from experimental.harness.assessor.standard import SOURCES, Assessor, Standard
from experimental.harness.assessor.validation import ReplayCorpus, fingerprint
from experimental.harness.curator.attribution import AttributionLimits, ModelAttributor
from experimental.harness.curator.generation.run import GenerationError
from experimental.harness.curator.generation.run import Limits as CuratorLimits
from experimental.harness.experience.curator import CuratorExperience
from experimental.harness.loop.records import cultivation
from experimental.harness.loop.run import run
from experimental.harness.loop.session import Limits
from experimental.harness.participation import model_roles
from experimental.harness.participation.compartment import Boundaries
from experimental.harness.participation.exchange import ExchangeError
from experimental.harness.raven_adapter.confinement import Confinement
from experimental.harness.raven_adapter.probe import exercise_translations
from experimental.harness.raven_adapter.worker import WorkerError
from experimental.harness.scenario import ROLES
from experimental.harness.scenario.digest import digest
from experimental.harness.scenario.sealed import sealed_for
from experimental.simulation.bench import caching
from experimental.simulation.bench.attribution import write as attribute_run
from experimental.simulation.bench.drills import enlist, grouped
from experimental.simulation.bench.information import CounterpartAnswers, gap_answerers
from experimental.simulation.bench.lab import lab_placement, replica_lab
from experimental.simulation.bench.record import PLACEHOLDERS, keep_scenario, placed
from experimental.simulation.bench.scenario import Scenario, handed_evidence
from experimental.simulation.cases.travel_agency.owner import Agency
from raven.config.loader import load_config
from raven.config.mode_catalogue import build_mode_catalogue
from raven.observability import execution


def owner_of(scenario) -> type:
    """The owner a case is judged by: `OWNER` in the bundled case of the scenario directory's name, so a copy of a case
    (a frozen run's, a test's) keeps its owner; the travel agency's for a scenario no bundled case is named after. A
    directory carrying an `owner.py` the bundled cases do not have is refused rather than judged by another owner."""
    module = f"experimental.simulation.cases.{scenario.root.name}.owner"
    try:
        found = importlib.import_module(module)
    except ModuleNotFoundError as exc:
        if exc.name not in (module, module.rpartition(".")[0]):
            raise
        if (scenario.root / "owner.py").is_file():
            raise ValueError(f"the owner of {scenario.root} is not a bundled case's ({module})") from exc
        return Agency
    if not hasattr(found, "OWNER"):
        raise ValueError(f"{module} names no OWNER")
    return found.OWNER


def settings(args, roles: dict, partner_tier=None) -> dict:
    """What a reader needs to know about how this run was set up; never a credential or a local config path.

    `argv` is the command line as given, with the configuration's path replaced: a reader reproduces the run from it.
    `roles` is the resolved map of `experimental.harness.participation.model_roles`; `research` is the research channel of the collector.
    """
    return {
        "argv": placed(args.argv, {"--config": PLACEHOLDERS["--config"]}),
        "owner_feedback": getattr(args, "owner_feedback", "spoken"),
        "scenario": Path(args.scenario).name,
        "deliver": args.deliver,
        "disclose": args.disclose,
        "partition": [list(step) for step in args.partition] if getattr(args, "partition", None) else None,
        "completes": not getattr(args, "no_completion", False),
        "rounds": args.rounds,
        "turns": args.turns,
        "repeats": args.repeats,
        "cards": args.cards,
        "holdout_rounds": sorted(args.holdout_rounds) if getattr(args, "holdout_rounds", None) else None,
        "concurrent_drills": args.concurrent_drills,
        "introspection": getattr(args, "introspection", True),
        "curator_budget": {
            "calls": getattr(args, "curator_calls", None),
            "queries": getattr(args, "curator_queries", None),
        },
        "attribution_budget": {
            "calls": getattr(args, "attribution_calls", None),
            "queries": getattr(args, "attribution_queries", None),
        },
        "attribution_catalogue": bool(getattr(args, "attribution_catalogue", False)),
        "attribution_prompts": str(args.attribution_prompts) if getattr(args, "attribution_prompts", None) else None,
        "standard": getattr(args, "standard", None),
        "prior": [str(path) for path in getattr(args, "prior_records", ())],
        "seed": args.seed,
        "without": args.without,
        **model_roles.recorded(roles),
        "partner_tier": partner_tier,
        "research": {
            "channel": getattr(args, "information_research", "exchange"),
            "model": getattr(args, "information_research_model", None),
            "effort": getattr(args, "information_research_effort", None),
            "budget": getattr(args, "information_research_budget", None),
            "reviews": getattr(args, "information_reviews", None),
            "answers_from": getattr(args, "information_answer_material", None),
            "replayed": bool(getattr(args, "information", None)),
            "gap_answers": getattr(args, "gap_answers", "both"),
        },
        "baseline": baseline(args.home),
        "starting_harness": starting_harness(Path(__file__).resolve().parents[2]),
        "started": time.time(),
    }


async def main(args):
    caching.install()
    scenario = Scenario.load(args.scenario)
    if args.without:
        scenario = scenario.without(args.without)
    confinement = None
    if args.isolate_as:
        if args.state_dir is None:
            raise ValueError("an isolated run needs --state-dir, a folder beside the runs it is kept from")
        confinement = Confinement.of(args.isolate_as, Path(__file__).resolve().parents[2])
    root = args.state_dir or Path(tempfile.mkdtemp(prefix="raven-simulation-task-"))
    if root.exists() and any(root.iterdir()):
        raise ValueError("state-dir must be a new or empty task directory")
    if confinement is not None:
        root.mkdir(parents=True, exist_ok=True)
        seal(root)
    with execution.run(root):
        await _run(args, scenario, root, confinement)


async def _run(args, scenario, root, confinement):
    disclosure = scenario.disclosure(
        args.partition or args.disclose, rounds=args.rounds, completes=not getattr(args, "no_completion", False)
    )
    contract = scenario.contract
    judge = owner_of(scenario)
    exams = exam_rounds(contract.situation.schedule, args.holdout_rounds, args.rounds)
    # The contract's prior and the command line's, read before anything is hired so a bad record fails fast.
    args.prior_records = [*contract.prior.records, *(args.prior or ())]
    prior = [cultivation(path) for path in args.prior_records]
    boundaries = Boundaries({role: sealed_for(contract, role) for role in ROLES}, log=root / "boundaries.jsonl")
    roles = model_roles.resolve(
        model_roles.pairs(args.model),
        model_roles.pairs(args.effort),
        model_roles.partner_of(load_config(args.config)),
    )
    counterpart, conversant, assessor_role = roles["counterpart"], roles["conversant"], roles["assessor"]
    lab_root = None
    lab_registry = None
    if (scenario.root / "lab").is_dir():
        if not os.environ.get("RAVEN_CONNECTIONS"):
            raise ValueError("a scenario lab needs RAVEN_CONNECTIONS with a local-lab machine")
        lab_registry = Path(os.environ["RAVEN_CONNECTIONS"])
        lab_root = Path(tempfile.mkdtemp(prefix="raven-simulation-labs-"))
        if confinement is not None:
            confinement.hand_over(lab_root)
    employee = hire(
        contract,
        args.config,
        workdir=workplace(args.workdir),
        root=root,
        home=args.home,
        subagent_model=roles["sub-harness"].model,
        timeout=args.timeout,
        guard=boundaries.compartment("partner").guard,
        confinement=confinement,
    )
    tier = build_mode_catalogue(employee.baseline.config).default
    (root / "settings.json").write_text(
        json.dumps(
            {
                **settings(args, roles, tier),
                "owner": f"{judge.__module__}.{judge.__qualname__}",
                "exam_rounds": sorted(exams) if exams else None,
                "disclosure": disclosure.record(),
                "provenance": contract.provenance.record or None,
                "scenario_dir": str(scenario.root),
                "scenario_digest": digest(scenario.root),
                "scenario_digest_format": "source-v2",
                "lab_root": str(lab_root) if lab_root is not None else None,
                "isolation": None
                if confinement is None
                else {"user": confinement.user, "image": str(confinement.image)},
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    provider = model_roles.provider(employee.baseline.config, roles)
    conversants, placed = {}, {}
    analyst_limits = AnalystLimits(call_timeout=args.timeout, max_calls=8)
    agency = judge(
        scenario,
        provider,
        skills(employee),
        workdir=employee.baseline.workdir,
        disclosure=disclosure,
        deliver=args.deliver,
        uploads=employee.baseline.config.workspace_path / "uploads",
        shared=employee.baseline.workdir / "uploads",
        cards=lambda: {name: conversant.card for name, conversant in conversants.items() if conversant.card},
        handouts=lambda sessions: {
            name: evidence["handouts"] for name, evidence in handed_evidence(sessions, conversants).items()
        },
        records=root,
        workdirs=placed,
        model=counterpart.model,
        effort=counterpart.effort,
        timeout=args.timeout,
        boundaries=boundaries,
    )
    agency.prepare()
    rounds, held = scheduled(scenario.personas, contract.situation.schedule, args.cards, args.holdout)
    sets = list(dict.fromkeys(tuple(card.name for card in cards) for cards in rounds))
    for index, names in enumerate(sets, 1):
        conversants.update(
            enlist(
                [card for card in scenario.personas if card.name in names],
                provider,
                repeats=args.repeats,
                prefix=f"s{index}-" if len(sets) > 1 else "",
                model=conversant.model,
                effort=conversant.effort,
                timeout=args.timeout,
                seed=args.seed,
                boundaries=boundaries,
            )
        )

    def spawn(worker, label):
        connections = (
            replica_lab(scenario.root / "lab", lab_root / label, lab_registry) if lab_root is not None else None
        )
        if connections is not None and confinement is not None:
            confinement.hand_over(connections.parent)
        replica = replicate(
            worker,
            args.config,
            root / REPLICAS / label,
            subagent_model=roles["sub-harness"].model,
            timeout=args.timeout,
            connections=connections,
        )
        if connections is not None:
            replica.lab = lab_placement(connections)
        return replica

    assessors = [agency]

    def supplied_evidence(sessions, speakers):
        found = handed_evidence(sessions, speakers)
        for name in sessions:
            found.setdefault(name, {})["scenario_digest"] = digest(scenario.root)
            if filed := agency._filed(name):
                found.setdefault(name, {})["filed"] = filed
        return found

    if args.introspection:
        assessors.append(
            Introspection(employee, spawn, records=root, concurrency=args.concurrent_drills, placed=placed)
        )
    standard = None
    if args.standard:
        memory = getattr(args, "evaluation_memory", None) or root / "evaluation-memory"
        derived = "derived" in args.standard
        standard = Assessor(
            provider,
            Standard.declared(
                ((check.id, check.check) for check in contract.statements.checks if "analyst" in check.visibility),
                applies_when={check.id: check.applies_when for check in contract.statements.checks},
            ),
            sources=args.standard,
            norms=lambda: scenario.standing_norms(agency.released),
            materials=lambda: scenario.evidence_materials(agency.released),
            references=lambda sessions: supplied_evidence(sessions, conversants),
            task=employee.baseline.task.text,
            model=assessor_role.model,
            effort=assessor_role.effort,
            timeout=args.timeout,
            boundaries=boundaries,
            builder=(
                RubricBuilder(
                    model=roles["rubric_builder"].model, effort=roles["rubric_builder"].effort, timeout=args.timeout
                )
                if "derived" in args.standard
                else None
            ),
            keep=root / "standard.json",
            reviewer=MetaReviewer(
                model=roles["meta_reviewer"].model, effort=roles["meta_reviewer"].effort, timeout=args.timeout
            )
            if derived
            else None,
            guidance_store=GuidanceStore(memory / "guidance.json") if derived else None,
            replay_corpus=ReplayCorpus(memory / "replays.json") if derived else None,
            scope=fingerprint({"task": employee.baseline.task.text}),
        )
        assessors.append(standard)
    played = [
        grouped(
            {name: one for name, one in conversants.items() if name.startswith(f"s{index}-") or len(sets) == 1},
            spawn,
            size=args.concurrent_drills,
            turns=args.turns,
            placed=placed,
        )
        for index in range(1, len(sets) + 1)
    ]
    by_round = [played[sets.index(tuple(card.name for card in cards))] for cards in rounds]
    trials = by_round[0] if len(by_round) == 1 else (lambda index: by_round[min(index, len(by_round)) - 1])
    holdout = None
    if held:
        holdout_assessor = Assessor(
            provider,
            Standard.declared(
                ((check.id, check.check) for check in contract.statements.checks if "analyst" in check.visibility),
                applies_when={check.id: check.applies_when for check in contract.statements.checks},
            ),
            sources=("declared",),
            task=employee.baseline.task.text,
            norms=lambda: scenario.standing_norms(scenario.kinds),
            materials=lambda: scenario.evidence_materials(scenario.kinds, role="counterpart"),
            model=assessor_role.model,
            effort=assessor_role.effort,
            timeout=args.timeout,
            boundaries=boundaries,
            compartment="counterpart",
            name="holdout",
            keep=root / "holdout-standard.json",
            references=lambda sessions: {name: examined(name, exchanges) for name, exchanges in sessions.items()},
        )
        held_out = enlist(
            held,
            provider,
            repeats=args.repeats,
            prefix="holdout-",
            model=conversant.model,
            effort=conversant.effort,
            timeout=args.timeout,
            seed=args.seed,
            boundaries=boundaries,
        )

        def examined(name, exchanges) -> dict:
            """What the exam judge holds a held-out drill to beside the checks: the case's facts and its answer."""
            card = held_out[name].card if name in held_out else None
            found = dict(agency.facts(name, exchanges, card) or {})
            found.update(supplied_evidence({name: exchanges}, held_out).get(name, {}))
            if getattr(card, "expected", None):
                found["expected"] = card.expected
            return found

        holdout = (
            grouped(held_out, spawn, size=args.concurrent_drills, turns=args.turns, placed=placed),
            [holdout_assessor],
        )
    if confinement is not None:
        problems = unsealed(employee, closed=[scenario.root, *args.closed])
        if problems:
            raise PermissionError("the isolated employee could reach what it must not: " + "; ".join(problems))
    experience = None
    try:
        async with employee:
            if getattr(args, "experience_memory", None):
                experience = CuratorExperience.from_provider(
                    args.experience_memory,
                    provider,
                    access_scope=getattr(args, "experience_scope", "local"),
                    model=roles["curator"].model,
                    effort=roles["curator"].effort,
                    migrate=getattr(args, "experience_migrate", False),
                    writable_roots=(employee.root, employee.baseline.config.workspace_path),
                )
            print(f"Task records: {root}")
            print(
                f"Scenario: {scenario.root.name}; disclosure: {disclosure.plan}; delivery: {args.deliver}; "
                f"cards: {' | '.join(', '.join(card.name for card in cards) for cards in rounds)}"
                f"{'; held out: ' + ', '.join(card.name for card in held) if held else ''}; skills: {skills(employee)}"
            )
            answers = (
                CounterpartAnswers(
                    provider,
                    contract,
                    args.information_answer_material,
                    lambda: agency.released,
                    records=root / "counterpart-answers",
                    model=counterpart.model,
                    effort=counterpart.effort,
                    timeout=args.timeout,
                )
                if getattr(args, "information_answer_material", None)
                else None
            )
            researcher = getattr(args, "information_research", "exchange")
            researcher = researcher if researcher != "none" else None
            research_limits = CollectionLimits(timeout=args.timeout, reviews=getattr(args, "information_reviews", 2))
            gaps = gap_answerers(
                getattr(args, "gap_answers", "both"),
                answers,
                scenario_researcher(
                    contract,
                    lambda: agency.released,
                    records=root / "gap-research",
                    researcher=researcher,
                    model=roles["collector"].model,
                    research_model=getattr(args, "information_research_model", None),
                    research_effort=getattr(args, "information_research_effort", None),
                    research_budget=getattr(args, "information_research_budget", None),
                    limits=research_limits,
                )
                if researcher is not None
                else None,
                research_tasks=research_limits.research_tasks,
            )
            try:
                await run(
                    employee,
                    provider,
                    trials,
                    assessors,
                    experience=experience,
                    measuring={OWNER} if getattr(args, "owner_feedback", "spoken") == "silent" else frozenset(),
                    probe=exercise_translations,
                    analyst_model=roles["analyst"].model,
                    analyst_effort=roles["analyst"].effort,
                    opening=agency.opening(),
                    prepare=scenario_preparer(
                        contract,
                        lambda: agency.released,
                        employee.baseline.config.workspace_path / "uploads"
                        if args.deliver == "dialog"
                        else skills(employee),
                        records=root / "information",
                        model=roles["collector"].model,
                        effort=roles["collector"].effort,
                        ask=answers,
                        researcher=researcher,
                        research_model=getattr(args, "information_research_model", None),
                        research_effort=getattr(args, "information_research_effort", None),
                        research_budget=getattr(args, "information_research_budget", None),
                        limits=research_limits,
                        replay=InformationResult.model_validate_json(args.information.read_text())
                        if getattr(args, "information", None)
                        else None,
                    ),
                    curator_model=roles["curator"].model,
                    boundaries=boundaries,
                    gaps=gaps,
                    prior=prior,
                    holdout=holdout,
                    holdout_rounds=exams,
                    attributor=ModelAttributor(
                        model=roles["attribution"].model,
                        effort=roles["attribution"].effort,
                        catalogue=args.attribution_catalogue,
                        **({"prompts": args.attribution_prompts} if args.attribution_prompts else {}),
                        limits=AttributionLimits(
                            call_timeout=args.timeout,
                            max_calls=args.attribution_calls,
                            max_queries=args.attribution_queries,
                        ),
                    ),
                    limits=Limits(
                        max_rounds=args.rounds,
                        analyst=analyst_limits,
                        curator=CuratorLimits(
                            call_timeout=args.timeout,
                            max_calls=args.curator_calls,
                            max_queries=args.curator_queries,
                            stage_queries=args.curator_stage_queries,
                        ),
                    ),
                )
            except (GenerationError, ExchangeError, WorkerError, ValueError) as exc:
                print(f"Could not complete this operation: {exc}")
                for row in getattr(exc, "trace", ()):
                    print(f"  {row}")
            try:
                attributed = await attribute_run(
                    root,
                    provider,
                    scenario_dir=scenario.root,
                    model=assessor_role.model,
                    effort=assessor_role.effort,
                    timeout=args.timeout,
                )
                print(
                    f"Read {len(attributed['requirements'])} requirements and {attributed['interventions']} intervention "
                    "reasons against the owner's rules"
                )
            except Exception as exc:  # noqa: BLE001 -- without an attribution the judge credits no intervention
                print(f"Could not attribute interventions: {exc!r}")
        if not keep_scenario(root, scenario.root):
            print(f"The scenario at {scenario.root} changed during the run; its copy was not kept")
    finally:
        if experience is not None:
            experience.close()
        if confinement is not None:
            unseal(root)


def scheduled(personas, schedule, cards=None, holdout=None) -> tuple[list[list], list]:
    """The cards of each round and the held-out ones. Cards named on the command line are played every round in place
    of the schedule's rounds, and cards held out on the command line replace its held-out ones, each independently;
    without rounds every card not held out is played every round (see `drills`)."""
    held = list(holdout) if holdout else list(schedule.holdout)
    if cards or not schedule.rounds:
        played, kept = drills(personas, cards, held)
        return [played], kept
    named = {persona.name: persona for persona in personas}
    missing = set(held) - set(named)
    if missing:
        raise ValueError(f"the scenario has no drill cards named {sorted(missing)}")
    both = {name for step in schedule.rounds for name in step} & set(held)
    if both:
        raise ValueError(f"a held-out card is not also played for feedback: {sorted(both)}")
    return [[named[name] for name in step] for step in schedule.rounds], [named[name] for name in held]


def exam_rounds(schedule, given, rounds: int) -> frozenset[int] | None:
    """The rounds the held-out cards are played in: those named on the command line, else the schedule's, else every
    round (None); 0 is before onboarding, and a round past the last one is refused rather than silently never
    played."""
    chosen = frozenset(given or schedule.holdout_rounds)
    outside = sorted(number for number in chosen if not 0 <= number <= rounds)
    if outside:
        raise ValueError(f"held-out cards scheduled for rounds {outside} of a run of {rounds}")
    return chosen or None


def drills(personas, cards=None, holdout=None) -> tuple[list, list]:
    """The drill cards played for feedback each round and the ones held out: the cards named (every card when none
    is), less the held-out ones, which are played and judged against the scenario's declared checks but kept from the
    owner's review, the Analyst and the Curator (`Session.holdout`)."""
    names = {persona.name for persona in personas}
    missing = (set(cards or ()) | set(holdout or ())) - names
    if missing:
        raise ValueError(f"the scenario has no drill cards named {sorted(missing)}")
    both = set(cards or ()) & set(holdout or ())
    if both:
        raise ValueError(f"a held-out card is not also played for feedback: {sorted(both)}")
    held = [persona for persona in personas if persona.name in set(holdout or ())]
    played = [persona for persona in personas if (not cards or persona.name in cards) and persona not in held]
    if not played:
        raise ValueError("holding out every card leaves nothing to play for feedback")
    return played, held


def cli():
    # Without abbreviations every option in the stored command line is spelled out, so its paths can be found.
    parser = argparse.ArgumentParser(
        description="Cultivate a digital employee: a simulated agency drills it, reviews it and speaks to the Curator.",
        allow_abbrev=False,
    )
    parser.add_argument("--config", type=Path, required=True, help="Raven JSON configuration")
    parser.add_argument("--information", type=Path, help="Reviewed offline result matching the current opening inputs")
    parser.add_argument(
        "--information-research",
        choices=("exchange", "claude", "codex", "none"),
        default="exchange",
        help="Research channel of initial information preparation and of the public questions a curation leaves open",
    )
    parser.add_argument(
        "--information-research-model",
        help="Model of the research channel; for claude or codex, that agent's own model name",
    )
    parser.add_argument("--information-research-effort", help="Reasoning effort of the research channel")
    parser.add_argument(
        "--information-research-budget",
        type=float,
        help="Dollar cap of each Claude Code research or review call (claude channel only)",
    )
    parser.add_argument(
        "--information-reviews",
        type=int,
        default=2,
        help="Compose-and-review attempts of initial preparation before it stops unaccepted",
    )
    parser.add_argument(
        "--information-answer-material",
        nargs="+",
        help="Materials the simulated counterpart may use to answer questions, of initial preparation and of curations",
    )
    parser.add_argument(
        "--gap-answers",
        choices=("counterpart", "research", "both", "none"),
        default="both",
        help="Who answers the questions a curation leaves open: the counterpart (with --information-answer-material) "
        "for private and unclear ones at its next review, research (on --information-research) for public ones and "
        "those the counterpart leaves open; both uses whichever is configured; none leaves them unanswered",
    )
    parser.add_argument(
        "--scenario", type=Path, default=Path("travel_agency"), help="Scenario directory or bundled name"
    )
    parser.add_argument(
        "--workdir", type=Path, help="The employee's working directory, new or empty; defaults to a temporary one"
    )
    parser.add_argument("--home", type=Path, help="Override the agent home; its skills folder receives the materials")
    parser.add_argument("--state-dir", type=Path, help="New task directory; defaults to a temporary directory")
    parser.add_argument(
        "--disclose",
        default="staged",
        metavar="PLAN",
        help="When the owner hands its materials over: all (every material at onboarding), none (never), staged (the "
        "scenario's initial set at onboarding, the rest as the owner chooses after each round), or the name of one "
        "of the scenario's plans (step 0 at onboarding, step k with the review of round k)",
    )
    parser.add_argument(
        "--no-completion",
        action="store_true",
        help="Keep withholding what the plan never hands over, instead of handing everything over before the last round",
    )
    parser.add_argument(
        "--model",
        action="append",
        default=[],
        metavar="ROLE=MODEL",
        help=f"Run a model role on this model; repeatable. Roles: {', '.join(model_roles.ROLES)}; a role not named "
        "runs on the partner's model, from --config",
    )
    parser.add_argument(
        "--effort",
        action="append",
        default=[],
        metavar="ROLE=LEVEL",
        help=f"Run a model role at this reasoning effort ({', '.join(model_roles.EFFORTS)}); repeatable. A role not "
        "named runs at the partner's effort, from --config; the sub-harness keeps its own",
    )
    parser.add_argument(
        "--attribution-catalogue",
        action="store_true",
        help="Diagnose with the target catalogue in the request; by default it stays out",
    )
    parser.add_argument(
        "--attribution-prompts",
        type=Path,
        help="A directory holding another version of the attribution prompts (understand.md, diagnose.md, budget.md)",
    )
    parser.add_argument(
        "--curator-calls",
        type=int,
        default=48,
        help="Model calls one curation may make, shared by the root and every child harness it revises",
    )
    parser.add_argument("--curator-queries", type=int, default=72, help="Exploration tool calls one curation may make")
    parser.add_argument(
        "--curator-stage-queries",
        type=int,
        help="Exploration tool calls one Curator stage may spend out of --curator-queries; unset leaves only the pool",
    )
    parser.add_argument(
        "--attribution-calls",
        type=int,
        default=8,
        help="Model calls one attribution may make, apart from the curation's own; each scope of a composite curation "
        "attributes its own inputs with this budget",
    )
    parser.add_argument(
        "--attribution-queries", type=int, default=24, help="Exploration tool calls one attribution may make"
    )
    parser.add_argument(
        "--no-introspection",
        dest="introspection",
        action="store_false",
        help="Skip the employee's own review of each round (the self signal the Analyst reads beside the owner's)",
    )
    parser.add_argument(
        "--standard",
        nargs="+",
        choices=SOURCES,
        help="Also hold each round to a standard judged by a model, from these sources: the scenario's checks "
        "(declared), criteria drawn from the norms handed over (derived) and every requirement raised so far "
        "(sedimented)",
    )
    parser.add_argument(
        "--prior",
        type=Path,
        nargs="+",
        help="Records of earlier cultivations the owner brings, besides the scenario's own (an iteration record or a "
        "run's task directory); every curation hears their history",
    )
    parser.add_argument(
        "--evaluation-memory",
        type=Path,
        help="Reuse evaluation guidance and independent replays from this host-owned directory",
    )
    parser.add_argument("--rounds", type=int, default=4, help="Maximum feedback rounds")
    parser.add_argument(
        "--experience-memory", type=Path, help="Host-owned Curator experience directory outside Worker writable areas"
    )
    parser.add_argument(
        "--experience-scope", default="local", help="Explicit access scope within the experience collection"
    )
    parser.add_argument(
        "--experience-migrate", action="store_true", help="Permit the documented legacy experience database migration"
    )
    parser.add_argument("--turns", type=int, default=8, help="Maximum customer messages per drill")
    parser.add_argument("--repeats", type=int, default=1, help="Times each drill card is played per round")
    parser.add_argument(
        "--deliver",
        choices=("pool", "dialog"),
        default="dialog",
        help="Hand materials to the Curator through the conversation (uploads, then pasted text), or copy them "
        "straight into the employee's skill pool",
    )
    parser.add_argument("--cards", nargs="+", help="Drill cards to play each round; defaults to every card")
    parser.add_argument(
        "--holdout",
        nargs="+",
        help="Drill cards held out: played each round and judged against the declared checks, never reviewed by the "
        "owner nor seen by the Analyst or the Curator",
    )
    parser.add_argument(
        "--holdout-rounds",
        type=int,
        nargs="+",
        help="Rounds (1-based; 0 is once before onboarding) in which the held-out cards are played; every round "
        "when not given",
    )
    parser.add_argument(
        "--concurrent-drills",
        type=int,
        default=1,
        help="Play this many of a round's drills at once (each drill always runs on its own replica of the employee)",
    )
    parser.add_argument(
        "--seed", type=int, help="Seed of the values drawn for the drill cards each round; drawn at random if absent"
    )
    parser.add_argument(
        "--without", nargs="+", help="Leave these materials out of the scenario, as if the agency never had them"
    )
    parser.add_argument(
        "--owner-feedback",
        choices=("spoken", "silent"),
        default="spoken",
        help="spoken: the owner's remark and verdicts after each round reach the Analyst and the Curator; silent: the "
        "owner still judges every round, as its measurement in the record, but nothing of it reaches the loop, which "
        "then improves from the employee's own review and any --standard alone (needs every material at onboarding)",
    )
    parser.add_argument(
        "--partition",
        type=json.loads,
        help='A partition of the materials into steps as JSON, e.g. [["service-sop", "price-list"], ["handover-ticket"]]: '
        "step 0 at onboarding, step k with the review of round k; overrides --disclose",
    )
    parser.add_argument(
        "--timeout", type=float, default=180, help="Timeout for each worker or model operation in seconds"
    )
    parser.add_argument(
        "--isolate-as",
        metavar="USER",
        help="Run the employee's process as this user from a code image, able to reach only its own area of the run",
    )
    parser.add_argument(
        "--closed",
        type=Path,
        nargs="+",
        default=[],
        help="Further paths an isolated employee must not reach; the run refuses to start if it can",
    )
    args = parser.parse_args()
    args.argv = sys.argv[1:]
    args.config = args.config.expanduser().resolve()
    if args.concurrent_drills < 1:
        parser.error("--concurrent-drills must be at least 1")
    try:
        model_roles.resolve(
            model_roles.pairs(args.model), model_roles.pairs(args.effort), model_roles.Choice("partner")
        )
    except ValueError as exc:
        parser.error(str(exc))
    if args.seed is None:
        args.seed = random.randrange(2**31)
    if args.partition is not None:
        args.partition = tuple(tuple(step) for step in args.partition)
        args.disclose = "partition"
    if args.owner_feedback == "silent" and args.disclose != "all":
        # A material handed over later arrives with the owner's remark, which a silent owner keeps from the loop.
        parser.error("--owner-feedback silent needs every material at onboarding: --disclose all")
    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    cli()
