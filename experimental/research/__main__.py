"""Research a scenario before a cultivation: `python -m experimental.research --scenario DIR --out DIR --records DIR`.

The stage copies the scenario with the materials `--without` names held by the party alone, the ones a simulated
party did not hand over; reports its slots; induces the rules its exemplars and counterexamples show; with
`--research`, researches on the web what its empty slots need (`experimental.research.inquiry`), by Claude Code,
Codex or this stage's own model; has the party settle every item; and writes the result to `--out` (see
`experimental.research`). A model that knows the materials `--party-knows` names settles the items, or the party's
decisions file does (`--decisions`), which names the items an earlier run recorded: with `--from-records` the stage
takes that run's items instead of inducing and researching again, so a decision always meets the item it was
written for. With neither, every item stays an unconfirmed candidate. `--records` keeps every provider call, every
page read, the slots, the items, the refused findings, the decisions and the settings, which leave the configuration
out since it holds credentials.
"""

import argparse
import asyncio
import json
import shutil
import time
from pathlib import Path

from raven.core.config_stack import load_runtime_config
from raven.providers.factory import make_lazy_provider, make_resolving_provider

from ..curator.raven_adapter.observe import ObservedProvider, Recorder
from ..iteration.exchange import ExchangeError
from ..scenario import load
from ..scenario.sealed import sealed_for
from . import package
from .confirm import Decisions, ModelParty, settle
from .induction import AUDIENCE, INSTANCES, Rule, induce, readable
from .inquiry import Finding, inquire
from .researchers import AGENTS, Agent, Exchange, ResearchError
from .slots import slots
from .web import Web

EFFORTS = ("low", "medium", "high")
RESEARCHERS = (*AGENTS, "exchange")


def _new(path: Path, what: str) -> Path:
    path = Path(path).resolve()
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise ValueError(f"{what} must be a new or empty directory: {path}")
    return path


def _write(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def _config(args):
    if args.config is None:
        raise ValueError("a model or the web is needed: give --config")
    config = load_runtime_config(str(args.config)).model_copy(deep=True)
    overridden = args.model or args.party_model
    if args.model:
        config.agents.defaults.model = args.model
    if overridden:
        config.agents.defaults.provider = "auto"
    return config, overridden


def _provider(args, records: Path):
    config, overridden = _config(args)
    native = make_resolving_provider(config) if overridden else make_lazy_provider(config)
    return ObservedProvider(native, Recorder(records / "provider.jsonl"))


def _recorded(args, source) -> tuple[list[Rule], list[Finding]]:
    """The items an earlier run of the stage recorded, when it researched this same scenario the same way."""
    earlier = Path(args.from_records).resolve()
    settings = json.loads((earlier / "settings.json").read_text())
    if settings.get("digest") != package.digest(source.root) or sorted(settings.get("without", ())) != sorted(
        args.without
    ):
        raise ValueError(f"{earlier} recorded another scenario or other held-back materials; research again")
    rules = [
        Rule(**{**row, "sources": tuple(row["sources"])}) for row in json.loads((earlier / "rules.json").read_text())
    ]
    found = earlier / "findings.json"
    findings = [
        Finding(**{**row, "sources": tuple(row["sources"]), "conflicts": tuple(row.get("conflicts", ()))})
        for row in (json.loads(found.read_text()) if found.is_file() else ())
    ]
    return rules, findings


def _researcher(args, provider):
    if args.research == "exchange":
        return Exchange(
            provider,
            model=args.model,
            effort=args.effort,
            max_calls=args.research_calls,
            timeout=args.timeout,
        )
    return Agent(args.research, model=args.research_model, budget=args.research_budget, timeout=args.research_timeout)


async def research(args) -> dict:
    decisions = Decisions.read(args.decisions) if args.decisions else None
    if decisions is not None and not args.from_records:
        raise ValueError("a decisions file settles the items an earlier run recorded: give --from-records")
    source = load(args.scenario)
    out, records = _new(args.out, "--out"), _new(args.records, "--records")
    for path, what in ((out, "--out"), (records, "--records")):
        if path.is_relative_to(source.root):
            raise ValueError(f"{what} must lie outside the scenario directory")
    if out == records or out.is_relative_to(records) or records.is_relative_to(out):
        raise ValueError("--out and --records must be apart")
    partial = out.with_name(out.name + ".partial")
    if partial.exists():
        raise ValueError(f"a partial build is in the way, from a run that did not finish: {partial}")
    records.mkdir(parents=True, exist_ok=True)
    effective = _config(args)[0].agents.defaults.model if args.config else args.model
    _write(
        records / "settings.json",
        {
            "scenario": str(source.root),
            "digest": package.digest(source.root),
            "out": str(out),
            "without": list(args.without),
            "party_knows": list(args.party_knows),
            "decisions": str(Path(args.decisions).resolve()) if args.decisions else None,
            "from_records": str(Path(args.from_records).resolve()) if args.from_records else None,
            "research": args.research,
            "models": {
                "induction": effective,
                "research": args.research_model if args.research in AGENTS else effective,
                "party": args.party_model or effective,
            },
            "efforts": {"induction": args.effort, "party": args.party_effort or args.effort},
            "limits": {
                "rules": args.limit,
                "findings": args.findings,
                "calls": args.max_calls,
                "research_calls": args.research_calls,
                "research_budget": args.research_budget,
                "timeout": args.timeout,
            },
            "started": time.time(),
        },
    )
    trace: list[dict] = []
    researched = None
    try:
        package.copy(source, partial, args.without)
        handed = load(partial)
        found = slots(handed)
        _write(records / "slots.json", [slot.record() for slot in found])
        # Sealed on what was handed over: a material held back is sealed from every reader of norms, even when the
        # source scenario would let the partner receive it.
        sealed = {role: sealed_for(handed, role) for role in AUDIENCE}
        gaps = {slot.gap for slot in found}
        instances = any(material.kind in INSTANCES for material in readable(handed).values())
        inducing = "inducible" in gaps and instances and not args.from_records
        researching = args.research is not None and "researchable" in gaps and not args.from_records
        modelled = inducing or args.research == "exchange" and researching or bool(args.party_knows)
        provider = _provider(args, records) if modelled else None
        calls = {"induction": None, "research": None, "confirmation": None}
        rules, findings = [], []
        if args.from_records:
            rules, findings = _recorded(args, source)
            calls["recorded"] = str(Path(args.from_records).resolve())
        if inducing:
            calls["induction"] = {
                "model": effective,
                "effort": args.effort,
                "rules": args.limit,
                "max_calls": args.max_calls,
                "timeout": args.timeout,
            }
            rules = list(
                await induce(
                    provider,
                    handed,
                    sealed=sealed,
                    limit=args.limit,
                    model=args.model,
                    effort=args.effort,
                    max_calls=args.max_calls,
                    timeout=args.timeout,
                    trace=trace,
                )
            )
            _write(records / "rules.json", [rule.record() for rule in rules])
        if researching:
            config, _ = _config(args)
            web = Web.of(config, searching=args.research == "exchange", log=records / "web.jsonl")
            researched = await inquire(
                _researcher(args, provider),
                handed,
                web,
                sealed=sealed,
                limit=args.findings,
                trace=trace,
            )
            findings = list(researched.findings)
            calls["research"] = researched.run
            _write(records / "findings.json", [finding.record() for finding in findings])
            _write(records / "unanswered.json", list(researched.unanswered))
            _write(records / "refused.json", list(researched.refused))
        items = [*rules, *findings]
        if decisions is not None:
            calls["confirmation"] = {"by": "decisions", "file": str(Path(args.decisions).resolve())}
        elif args.party_knows and items:
            party = ModelParty(
                provider,
                source,
                args.party_knows,
                sealed=sealed,
                model=args.party_model or args.model,
                effort=args.party_effort or args.effort,
                max_calls=args.max_calls,
                timeout=args.timeout,
            )
            decisions = await party.decide(items, trace=trace)
            calls["confirmation"] = {**party.record(), "model": args.party_model or effective}
        _write(records / "rules.json", [rule.record() for rule in rules])
        _write(records / "findings.json", [finding.record() for finding in findings])
        unanswered = list(researched.unanswered) if researched else []
        refused = list(researched.refused) if researched else []
        _write(records / "unanswered.json", unanswered)
        _write(records / "refused.json", refused)
        settled = settle(items, decisions)
        _write(records / "decisions.json", [decision.model_dump() for _, decision in settled])
        package.add(
            partial,
            source,
            handed,
            settled,
            without=args.without,
            slots=found,
            calls=calls,
            unanswered=unanswered,
            refused=refused,
        )
        load(partial)
        if out.exists():
            out.rmdir()
        partial.rename(out)
    finally:
        _write(records / "trace.json", trace)
        if partial.exists():
            shutil.rmtree(partial, ignore_errors=True)
    counts: dict[str, int] = {}
    for _, decision in settled:
        counts[decision.status] = counts.get(decision.status, 0) + 1
    summary = {
        "out": str(out),
        "gaps": {slot.category: slot.gap for slot in found if slot.gap},
        "rules": len(rules),
        "findings": len(findings),
        "refused": len(refused),
        "unanswered": len(unanswered),
        "decisions": counts,
    }
    _write(records / "summary.json", summary)
    return summary


def cli():
    parser = argparse.ArgumentParser(description="Research a scenario before a cultivation.")
    parser.add_argument("--scenario", type=Path, required=True, help="The scenario directory the party handed over")
    parser.add_argument("--out", type=Path, required=True, help="New directory for the researched scenario")
    parser.add_argument("--records", type=Path, required=True, help="New directory for the stage's records")
    parser.add_argument("--config", type=Path, help="Raven JSON configuration: models, and the web tools' keys")
    parser.add_argument("--model", help="Override the model that induces the rules and, by exchange, researches")
    parser.add_argument("--effort", choices=EFFORTS, default="high", help="Reasoning effort of this stage's model")
    parser.add_argument("--without", nargs="+", default=[], help="Materials the party did not hand over")
    parser.add_argument(
        "--research",
        choices=RESEARCHERS,
        help="Research the empty slots on the web: by Claude Code, Codex, or this stage's model (exchange)",
    )
    parser.add_argument("--research-model", help="The model of the research agent")
    parser.add_argument("--research-budget", type=float, default=2.0, help="Dollars one Claude Code research may use")
    parser.add_argument("--research-timeout", type=int, default=900, help="Seconds one research agent may take")
    parser.add_argument("--research-calls", type=int, default=16, help="Model calls a research by exchange may make")
    parser.add_argument("--findings", type=int, default=8, help="Most findings one research may keep")
    settle_by = parser.add_mutually_exclusive_group()
    settle_by.add_argument("--decisions", type=Path, help="The party's decisions on the items --from-records names")
    settle_by.add_argument(
        "--party-knows", nargs="+", default=[], help="Materials a model playing the party decides by"
    )
    parser.add_argument("--from-records", type=Path, help="An earlier run's records: settle its items again")
    parser.add_argument("--party-model", help="Override the model playing the party")
    parser.add_argument(
        "--party-effort", choices=EFFORTS, help="Reasoning effort of the party; the induction's by default"
    )
    parser.add_argument("--limit", type=int, default=12, help="Most rules the induction may submit")
    parser.add_argument("--max-calls", type=int, default=4, help="Model calls one induction or settling may make")
    parser.add_argument("--timeout", type=int, default=300, help="Seconds one model call may take")
    args = parser.parse_args()
    try:
        summary = asyncio.run(research(args))
    except (ExchangeError, ResearchError, ValueError) as exc:
        print(f"Could not complete the research: {exc}")
        raise SystemExit(1) from exc
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    cli()
