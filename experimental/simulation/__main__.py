"""Run the travel-agency cultivation: each round the agency plays customers from its drill cards against the
digital employee, reviews the drills and speaks to the Curator, and the loop curates the employee's Harness. The
agency is the loop's assessor: it only speaks, and the base Analyst turns its words into the Curator's requirements
(see `experimental.simulation.agency`).

The owner knows all of the scenario's materials from the start and has handed every one over by the review before the
last round; what varies is the partition of the materials into steps, which is how cultivation runs are told apart and
what mining searches over. A chain names one such plan (all at once, as the owner decides, or a scenario's named
partition), and `--partition` gives any other as JSON. The run's settings, with its command line but without any
credential or configuration path, are written to `settings.json` beside the records.

Each round plays every drill card with freshly drawn values (see `experimental.simulation.cards`) from `--seed`, so a
rule counts as held only on values the employee has not met before; arms given one seed meet the same values.
`--without` leaves materials out of the scenario altogether, for arms that differ only in what the agency owns.
Every drill runs on its own replica of the employee, made from it as the round begins and kept under `replicas/`
beside the records (see `experimental.automation.employee.Together`), so no drill sees another's files;
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
import json
import random
import sys
import tempfile
import time
from pathlib import Path

from raven.config.mode_catalogue import build_mode_catalogue
from raven.providers.factory import make_lazy_provider, make_resolving_provider

from ..analyst.run import Limits as AnalystLimits
from ..assessor.standard import SOURCES, Standard, StandardAssessor
from ..automation import caching
from ..automation.employee import (
    REPLICAS,
    Together,
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
from ..automation.traveller import Traveller
from ..curator.attribution import AttributionLimits, ModelAttributor
from ..curator.generation.run import GenerationError
from ..curator.generation.run import Limits as CuratorLimits
from ..curator.raven_adapter.confinement import Confinement
from ..curator.raven_adapter.worker import WorkerError
from ..iteration.compartment import Boundaries
from ..iteration.conversation import Conversation
from ..iteration.exchange import ExchangeError
from ..iteration.records import cultivation
from ..iteration.run import run
from ..iteration.session import Limits
from ..research.package import digest
from ..scenario import ROLES
from ..scenario.sealed import sealed_for
from .agency import Agency
from .attribution import write as attribute_run
from .record import PLACEHOLDERS, placed
from .scenario import Scenario

EFFORTS = ("low", "medium", "high")
CHAINS = {
    "documents": {"deliver": "dialog", "disclose": "all"},
    "staged": {"deliver": "dialog", "disclose": "staged"},
    "by-stage": {"deliver": "dialog", "disclose": "by-stage"},
}


def settings(args, employee_model: str, employee_effort=None, employee_tier=None) -> dict:
    """What a reader needs to know about how this run was set up; never a credential or a local config path.

    `argv` is the command line as given, with the configuration's path replaced: a reader reproduces the run from it.
    """
    return {
        "argv": placed(args.argv, {"--config": PLACEHOLDERS["--config"]}),
        "chain": args.chain,
        "scenario": Path(args.scenario).name,
        "deliver": args.deliver,
        "disclose": [list(step) for step in args.disclose] if isinstance(args.disclose, tuple) else args.disclose,
        "rounds": args.rounds,
        "turns": args.turns,
        "repeats": args.repeats,
        "cards": args.cards,
        "concurrent_drills": args.concurrent_drills,
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
        "models": {
            "employee": employee_model,
            "curator": args.curator_model or employee_model,
            "analyst": args.analyst_model or args.curator_model or employee_model,
            "attribution": getattr(args, "attribution_model", None) or args.curator_model or employee_model,
            "simulation": args.simulation_model or args.curator_model or employee_model,
            "traveller": args.traveller_model or args.simulation_model or args.curator_model or employee_model,
            "subagents": args.subagent_model,
        },
        "efforts": {
            "employee": employee_effort,
            "employee_tier": employee_tier,
            "curator": args.curator_effort,
            "simulation": args.simulation_effort,
            "traveller": args.traveller_effort,
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
    disclosure = scenario.disclosure(args.disclose, rounds=args.rounds)
    contract = scenario.contract
    # The contract's prior and the command line's, read before anything is hired so a bad record fails fast.
    args.prior_records = [*contract.prior.records, *(args.prior or ())]
    prior = [cultivation(path) for path in args.prior_records]
    boundaries = Boundaries({role: sealed_for(contract, role) for role in ROLES}, log=root / "boundaries.jsonl")
    employee = hire(
        contract,
        args.config,
        workdir=workplace(args.workdir),
        root=root,
        home=args.home,
        subagent_model=args.subagent_model,
        timeout=args.timeout,
        guard=boundaries.compartment("partner").guard,
        confinement=confinement,
    )
    defaults = employee.baseline.config.agents.defaults
    if not defaults.reasoning_effort:
        raise ValueError("set agents.defaults.reasoningEffort explicitly; a provider default is not a run setting")
    tier = build_mode_catalogue(employee.baseline.config).default
    (root / "settings.json").write_text(
        json.dumps(
            {
                **settings(args, defaults.model, defaults.reasoning_effort, tier),
                "disclosure": disclosure.record(),
                "provenance": contract.provenance.record or None,
                "scenario_dir": str(scenario.root),
                "scenario_digest": digest(scenario.root),
                "isolation": None
                if confinement is None
                else {"user": confinement.user, "image": str(confinement.image)},
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    model_config = employee.baseline.config.model_copy(deep=True)
    overridden = args.curator_model or args.analyst_model or args.simulation_model or args.traveller_model
    if overridden:
        model_config.agents.defaults.provider = "auto"
    if args.curator_model:
        model_config.agents.defaults.model = args.curator_model
    if args.curator_effort:
        model_config.agents.defaults.reasoning_effort = args.curator_effort
    # With a role on another model, each call's vendor follows its model id: the Curator and the owner can run on a
    # gateway while the customers stay on the employee's own vendor.
    provider = make_resolving_provider(model_config) if overridden else make_lazy_provider(model_config)
    travellers, placed = {}, {}
    analyst_limits = AnalystLimits(call_timeout=args.timeout, max_calls=8)
    agency = Agency(
        scenario,
        provider,
        skills(employee),
        workdir=employee.baseline.workdir,
        disclosure=disclosure,
        deliver=args.deliver,
        uploads=employee.baseline.config.workspace_path / "uploads",
        shared=employee.baseline.workdir / "uploads",
        cards=lambda: {name: traveller.card for name, traveller in travellers.items() if traveller.card},
        records=root,
        workdirs=placed,
        model=args.simulation_model,
        effort=args.simulation_effort,
        timeout=args.timeout,
        boundaries=boundaries,
    )
    agency.prepare()
    cards, held = drills(scenario.personas, args.cards, args.holdout)

    def enlist(personas, prefix=""):
        enlisted = {}
        for persona in personas:
            for repeat in range(1, args.repeats + 1):
                traveller = Traveller(
                    persona,
                    provider,
                    name=f"{prefix}{persona.name}" + (f"-{repeat}" if args.repeats > 1 else ""),
                    model=args.traveller_model or args.simulation_model,
                    effort=args.traveller_effort,
                    timeout=args.timeout,
                    seed=args.seed,
                    boundaries=boundaries,
                )
                enlisted[traveller.name] = traveller
        return enlisted

    travellers.update(enlist(cards))

    def spawn(worker, label):
        return replicate(
            worker,
            args.config,
            root / REPLICAS / label,
            subagent_model=args.subagent_model,
            timeout=args.timeout,
        )

    assessors = [agency]
    standard = None
    if args.standard:
        standard = StandardAssessor(
            provider,
            Standard.declared(
                (check.id, check.check) for check in contract.statements.checks if "analyst" in check.visibility
            ),
            sources=args.standard,
            norms=lambda: scenario.standing_norms(agency.released),
            model=args.simulation_model,
            effort=args.simulation_effort,
            timeout=args.timeout,
            boundaries=boundaries,
        )
        assessors.append(standard)
    size = args.concurrent_drills

    def together(played, where):
        named = [(name, Conversation(traveller, max_turns=args.turns)) for name, traveller in played.items()]
        return [Together(dict(named[start : start + size]), spawn, where) for start in range(0, len(named), size)]

    trials = together(travellers, placed)
    holdout = None
    if held:
        judge = StandardAssessor(
            provider,
            Standard.declared(
                (check.id, check.check) for check in contract.statements.checks if "analyst" in check.visibility
            ),
            sources=("declared",),
            model=args.simulation_model,
            effort=args.simulation_effort,
            timeout=args.timeout,
            boundaries=boundaries,
            name="holdout",
        )
        holdout = (together(enlist(held, prefix="holdout-"), {}), [judge])
    if confinement is not None:
        problems = unsealed(employee, closed=[scenario.root, *args.closed])
        if problems:
            raise PermissionError("the isolated employee could reach what it must not: " + "; ".join(problems))
    try:
        async with employee:
            print(f"Task records: {root}")
            print(
                f"Scenario: {scenario.root.name}; chain: {args.chain}; disclosure: {args.disclose}; delivery: {args.deliver}; "
                f"cards: {', '.join(card.name for card in cards)}; skills: {skills(employee)}"
            )
            try:
                await run(
                    employee,
                    provider,
                    trials,
                    assessors,
                    model=args.analyst_model or args.curator_model,
                    opening=agency.opening(),
                    curator_model=args.curator_model,
                    boundaries=boundaries,
                    prior=prior,
                    holdout=holdout,
                    attributor=ModelAttributor(
                        model=args.attribution_model,
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
                            call_timeout=args.timeout, max_calls=args.curator_calls, max_queries=args.curator_queries
                        ),
                    ),
                )
            except (GenerationError, ExchangeError, WorkerError, ValueError) as exc:
                print(f"Could not complete this operation: {exc}")
                for row in getattr(exc, "trace", ()):
                    print(f"  {row}")
            finally:
                if standard is not None:
                    (root / "standard.json").write_text(json.dumps(standard.record(), ensure_ascii=False, indent=2))
            try:
                attributed = await attribute_run(
                    root, provider, scenario_dir=scenario.root, model=args.simulation_model, timeout=args.timeout
                )
                print(
                    f"Read {len(attributed['requirements'])} requirements and {attributed['interventions']} intervention "
                    "reasons against the owner's rules"
                )
            except Exception as exc:  # noqa: BLE001 -- without an attribution the judge credits no intervention
                print(f"Could not attribute interventions: {exc!r}")
    finally:
        if confinement is not None:
            unseal(root)


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
        choices=("all", "staged"),
        default="staged",
        help="Hand every material over at onboarding, or the scenario's initial set first and the rest as the owner "
        "chooses after each round",
    )
    parser.add_argument("--curator-model", help="Override the model used for curation")
    parser.add_argument("--attribution-model", help="Override the model the Curator diagnoses with")
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
    parser.add_argument("--analyst-model", help="Override the base Analyst's model")
    parser.add_argument("--simulation-model", help="Override the model playing the agency and its customers")
    parser.add_argument("--traveller-model", help="Override the model playing the customers only")
    parser.add_argument(
        "--curator-calls",
        type=int,
        default=48,
        help="Model calls one curation may make, shared by the root and every child harness it revises",
    )
    parser.add_argument("--curator-queries", type=int, default=72, help="Exploration tool calls one curation may make")
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
        "--curator-effort",
        choices=EFFORTS,
        default="high",
        help="Reasoning effort of the Curator and the Analyst (the employee keeps its own)",
    )
    parser.add_argument(
        "--simulation-effort",
        choices=EFFORTS,
        default="low",
        help="Reasoning effort of the agency's review and the automatic assessor; a reasoning model at high effort "
        "can spend a scorecard's whole output budget thinking",
    )
    parser.add_argument(
        "--traveller-effort", choices=EFFORTS, default="low", help="Reasoning effort of the simulated customers"
    )
    parser.add_argument(
        "--subagent-model",
        help="Run the employee's Research and PPT subagents on this model, through the employee's own provider and "
        "key, instead of their own",
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
    parser.add_argument("--rounds", type=int, default=4, help="Maximum feedback rounds")
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
        "--chain",
        choices=sorted(CHAINS),
        help="How the owner cultivates the employee; sets delivery and disclosure, overriding --deliver and --disclose",
    )
    parser.add_argument(
        "--partition",
        type=json.loads,
        help='A partition of the materials into steps as JSON, e.g. [["service-sop", "price-list"], ["handover-ticket"]]: '
        "step 0 at onboarding, step k with the review of round k; overrides --chain and --disclose",
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
    if args.seed is None:
        args.seed = random.randrange(2**31)
    if args.chain:
        args.deliver, args.disclose = CHAINS[args.chain]["deliver"], CHAINS[args.chain]["disclose"]
    if args.partition is not None:
        args.chain, args.deliver = "partition", "dialog"
        args.disclose = tuple(tuple(step) for step in args.partition)
    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    cli()
