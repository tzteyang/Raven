"""Prepare expert information offline with the simulated counterpart answering the collector's questions.

The collector's own entry (`experimental.cultivation.collector`) takes answers from a terminal; this one lets a case's
owner answer from the materials named by `--answer-material`, the way a run on the bench does.
"""

import asyncio
import json

from experimental.cultivation.collector.__main__ import build_parser, check, research
from experimental.simulation.bench.information import CounterpartAnswers


def cli():
    parser = build_parser()
    parser.add_argument(
        "--answer-material",
        nargs="+",
        required=True,
        help="Scenario material the simulated counterpart may answer from",
    )
    args = parser.parse_args()
    check(parser, args)
    if not args.scenario:
        parser.error("--answer-material requires --scenario")
    if args.interactive:
        parser.error("--answer-material and --interactive exclude each other")

    def answerer(provider, scenario, released, root):
        return CounterpartAnswers(
            provider,
            scenario,
            args.answer_material,
            released,
            records=root / "counterpart-answers",
            model=args.model,
            timeout=args.timeout,
        )

    print(json.dumps(asyncio.run(research(args, answerer_factory=answerer)), indent=2))


if __name__ == "__main__":
    cli()
