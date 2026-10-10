"""Run one experimental task with a person conversing and judging each round.

The person is the counterpart and every conversant, so the run's model roles are the Curator's side alone (`ROLES`);
`--model` and `--effort` name them as `experimental.model_roles` reads them.
"""

import argparse
import asyncio
import tempfile
from pathlib import Path

from experimental import model_roles
from experimental.assessor.human import DONE, Human
from experimental.curator.attribution import ModelAttributor
from experimental.curator.generation.run import GenerationError
from experimental.curator.harness import Task
from experimental.curator.raven_adapter.inspection import Baseline
from experimental.curator.raven_adapter.worker import Worker, WorkerError
from experimental.experience.curator import CuratorExperience
from experimental.iteration.conversation import Conversation
from experimental.iteration.exchange import ExchangeError
from experimental.iteration.run import run
from experimental.iteration.session import Limits
from raven.config.raven import load_raven_config
from raven.core.config_stack import load_runtime_config

ROLES = ("curator", "attribution", "analyst")


async def main(args):
    config = load_runtime_config(str(args.config), str(args.home) if args.home else None)
    extensions = load_raven_config(args.config)
    root = args.state_dir or Path(tempfile.mkdtemp(prefix="raven-iteration-task-"))
    if root.exists() and any(root.iterdir()):
        raise ValueError("state-dir must be a new or empty task directory")
    baseline = Baseline(config, extensions, args.workdir, task=Task(text=args.task))
    roles = model_roles.resolve(
        model_roles.pairs(args.model), model_roles.pairs(args.effort), model_roles.partner_of(config), roles=ROLES
    )
    provider = model_roles.provider(config, roles)
    human = Human()
    async with Worker(baseline, root, timeout=args.timeout) as worker:
        print(f"Task records: {root}")
        print(f"Talk to the assistant; {DONE} ends a conversation, then leave feedback empty to finish.")
        experience = None
        try:
            if getattr(args, "experience_memory", None):
                experience = CuratorExperience.from_provider(
                    args.experience_memory,
                    provider,
                    access_scope=getattr(args, "experience_scope", "local"),
                    model=roles["curator"].model,
                    effort=roles["curator"].effort,
                    migrate=getattr(args, "experience_migrate", False),
                    writable_roots=(worker.root, worker.baseline.config.workspace_path),
                )
            await run(
                worker,
                provider,
                [Conversation(human, max_turns=args.turns)],
                [human],
                experience=experience,
                analyst_model=roles["analyst"].model,
                analyst_effort=roles["analyst"].effort,
                curator_model=roles["curator"].model,
                attributor=ModelAttributor(model=roles["attribution"].model, effort=roles["attribution"].effort),
                limits=Limits(max_rounds=args.rounds),
            )
        except (GenerationError, ExchangeError, WorkerError, ValueError) as exc:
            print(f"Could not complete this operation: {exc}")
        finally:
            if experience is not None:
                experience.close()


def cli():
    parser = argparse.ArgumentParser(description="Iterate an experimental Curator task with a person in the loop.")
    parser.add_argument("--config", type=Path, required=True, help="Raven JSON configuration")
    parser.add_argument("--task", required=True, help="Current task goal")
    parser.add_argument("--workdir", type=Path, default=Path.cwd())
    parser.add_argument("--home", type=Path, help="Override the agent home")
    parser.add_argument("--state-dir", type=Path, help="New task directory; defaults to a temporary directory")
    parser.add_argument(
        "--model",
        action="append",
        default=[],
        metavar="ROLE=MODEL",
        help=f"Run a model role ({', '.join(ROLES)}) on this model; repeatable; a role not named runs on --config's",
    )
    parser.add_argument(
        "--effort",
        action="append",
        default=[],
        metavar="ROLE=LEVEL",
        help=f"Run a model role at this reasoning effort ({', '.join(model_roles.EFFORTS)}); repeatable",
    )
    parser.add_argument("--rounds", type=int, default=5, help="Maximum feedback rounds")
    parser.add_argument(
        "--experience-memory", type=Path, help="Host-owned Curator experience directory outside Worker writable areas"
    )
    parser.add_argument(
        "--experience-scope", default="local", help="Explicit access scope within the experience collection"
    )
    parser.add_argument(
        "--experience-migrate", action="store_true", help="Permit the documented legacy experience database migration"
    )
    parser.add_argument("--turns", type=int, default=20, help="Maximum messages per conversation")
    parser.add_argument("--timeout", type=float, default=120, help="Timeout for each worker operation in seconds")
    args = parser.parse_args()
    args.config = args.config.expanduser().resolve()
    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    cli()
