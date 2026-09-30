"""What a live session borrows from the automation and simulation packages: hiring the employee on the person's task,
setting up the session's process the way an automated run sets up its own, handing the scenario's materials over the
way a party uploads them, and the norms an automatic assessor may draw criteria from. This is the one module of the
Studio that imports those packages; the session's process (`experimental.webui.session_host`) reaches them only
through it, and the server not at all.

Resuming a session after its process ended needs the employee of an existing run directory, rebuilt on the revision
its last activation installed. The loop has no such entry yet (`rehire` says so), so a live session lasts as long as
its process.
"""

from pathlib import Path

from ..automation import caching
from ..automation.employee import hire_task, starting_harness, withheld, workplace
from ..curator.harness import Task
from ..iteration.protocols import Handover
from ..simulation.agency import attached
from ..simulation.scenario import Scenario

REPOSITORY = Path(__file__).resolve().parents[2]


class UnsupportedError(RuntimeError):
    """A live step the loop cannot take yet."""


def prepare() -> None:
    """Set up the session's process before anything is hired, as an automated run does: the gateway cache
    breakpoints (`experimental.automation.caching`)."""
    caching.install()


def starting() -> dict:
    """Which code every harness of the session starts from (`experimental.automation.employee.starting_harness`)."""
    return starting_harness(REPOSITORY)


def hire(contract, config: Path, *, task: str, workdir: Path, root: Path, subagent_model, timeout, guard):
    """The employee of a new live run: a plain Raven baseline on `task`, in its own home under `root` and a new
    working directory, behind the partner's guard, whose Curator may not read the evaluation side (`withheld`)."""
    return hire_task(
        Task(text=task),
        config,
        workdir=workplace(workdir),
        root=root,
        subagent_model=subagent_model,
        timeout=timeout,
        withheld=withheld(contract),
        guard=guard,
    )


def rehire(*_args, **_kwargs):
    """The employee of an existing run directory as its last activation left it; the loop does not provide it yet."""
    raise UnsupportedError(
        "resuming needs the employee of an existing run directory rebuilt on its installed revision, which the loop "
        "does not provide yet"
    )


def hand_over(contract, names, *, uploads: Path, shared: Path) -> tuple[Handover, ...]:
    """Upload the named materials the way the party uploads files, into the employee's `uploads` folder and the
    working directory's (`shared`), and name them as a signal's handovers; only the materials the party may hand over
    (`handed`) are."""
    scenario = Scenario.of(contract)
    unknown = sorted(set(names) - set(scenario.handed))
    if unknown:
        raise ValueError(f"the scenario hands over no materials named {unknown}")
    return attached(scenario.upload(list(names), uploads, shared=shared), scenario.kinds)


def standing_norms(contract, names) -> dict[str, str]:
    """The norms among the handed-over `names` an automatic assessor may draw criteria from, by name to text."""
    return Scenario.of(contract).standing_norms(names)
