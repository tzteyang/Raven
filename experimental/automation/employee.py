"""The digital employee of an automated cultivation: the real Raven worker, hired with the scenario's profile as its
task, and what it starts from.

Every drill runs on its own replica of the employee (see `replicate` and `Together`); drills of a round can run at once.
The employee's process works in the area `AREA` of its root (its home, deployment, generations and saved state) and
each replica's in the area of its own root under `REPLICAS`; the root keeps the loop's records beside the area, and
a confined employee (`confinement`) runs as a user that can reach only its area (see the design's section 4.2).
`withheld` keeps the evaluation side of the repository from its Curator; `baseline`, `starting_harness` and
`workplace` record and check what the employee starts from.
"""

import asyncio
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

from raven.agent.subagent.builtin_agents import GENERIC_AGENT
from raven.agent.subagent.vendored_agents import discover_product_rows, product_folder
from raven.config.schema import ThirdPartyAcpSubagentConfig
from raven.providers.factory import make_lazy_provider

from ..curator.harness import Task
from ..curator.raven_adapter.baselines.prepare import prepare
from ..curator.raven_adapter.deployment import child_directory
from ..curator.raven_adapter.exploration import Withheld
from ..curator.raven_adapter.hosting.prepare import prepare_children
from ..curator.raven_adapter.targets import catalogue
from ..curator.raven_adapter.worker import Worker
from ..iteration.compartment import Guard, GuardedFactory
from ..iteration.hearing import opaque
from ..scenario import Scenario

AREA = "employee"
HOME = "home"
WORKDIR = "workdir"
REPLICAS = "replicas"
SUBAGENTS = "subagents"
HOUSED = {"Raven-Research": "RESEARCH_NG_ACP_HOME", "Raven-PPT": "PPT_ACP_HOME"}
FORWARDED = ("PYTHONTZPATH",)
UNATTENDED = ("ask_user",)
# A product's shell reaches whatever its process can: the employee's is confined to its workspace, a product's is not,
# and its file tools must still reach the drill's workdir, so products run without a shell.
SHELLS = ("exec",)


EVALUATION_PATHS = (
    "experimental/iteration/*",
    "experimental/assessor/*",
    "experimental/analyst/*",
    "experimental/scenario/*",
    "experimental/research/*",
    "experimental/automation/*",
    "experimental/simulation/*",
    "tests/test_iteration_*",
    "tests/test_assessor_*",
    "tests/test_analyst_*",
    "tests/test_scenario_*",
    "tests/test_research_*",
    "tests/test_automation_*",
    "tests/test_simulation_*",
)


def withheld(scenario: Scenario) -> Withheld:
    """What the employee's Curator may not read: the evaluation side of the repository (`EVALUATION_PATHS`) and any
    repository file that names one of its packages or the scenario."""
    return Withheld(
        paths=EVALUATION_PATHS,
        markers=(
            b"experimental.iteration",
            b"experimental/iteration",
            b"experimental.assessor",
            b"experimental/assessor",
            b"experimental.analyst",
            b"experimental/analyst",
            b"experimental.scenario",
            b"experimental/scenario",
            b"experimental.research",
            b"experimental/research",
            b"experimental.automation",
            b"experimental/automation",
            b"experimental.simulation",
            b"experimental/simulation",
            scenario.root.name.encode(),
        ),
    )


def confined(children: dict, parent) -> dict:
    """Keep each child to its own home, the drill's working directory and what its parent hands it.

    The drill's workdir (the parent's) is read and written: tickets and decks pass through it. The parent's home is
    read only: uploaded materials, the skill pool and playbook node outputs are read there, nothing written. Other
    drills, earlier rounds, the run's records and the repository stay out of reach of the file tools and of
    `deliver_files`. A child's shell, where it has one, is restricted to the child's own home; products run without
    one (`SHELLS`).
    """
    for child in children.values():
        child.baseline.file_roots = (parent.workdir,)
        child.baseline.read_roots = (parent.config.workspace_path,)
        child.baseline.config.tools.restrict_to_workspace = True
    return children


def hire(
    scenario: Scenario,
    config: Path,
    *,
    workdir: Path,
    root: Path,
    home: Path | None = None,
    subagent_model: str | None = None,
    timeout=180,
    guard: Guard | None = None,
    confinement=None,
) -> Worker:
    """A plain Raven baseline that knows only its job description, the scenario's profile; the Curator shapes
    everything else.

    The employee works from its own copy of the agent home in its area under `root` (without past sessions), so the
    materials the party hands over never touch the caller's home and two runs never share a skill pool.
    The Curator may author every declared Harness target.
    `subagent_model` runs the housed subagents on that model, through the employee's provider, instead of its own.
    """
    return hire_task(
        Task(text=scenario.situation.profile),
        config,
        workdir=workdir,
        root=root,
        home=home,
        subagent_model=subagent_model,
        timeout=timeout,
        withheld=withheld(scenario),
        guard=guard,
        confinement=confinement,
    )


def hire_task(
    task: Task,
    config: Path,
    *,
    workdir: Path,
    root: Path,
    home: Path | None = None,
    subagent_model: str | None = None,
    timeout=180,
    withheld: Withheld = Withheld(),
    guard: Guard | None = None,
    confinement=None,
) -> Worker:
    """Prepare the normal employee and child pool for either a scenario or a supplied expert.

    With `guard`, the partner's guard, every provider the employee's process makes is guarded: the guard travels
    with the worker as plain data (`GuardedFactory`) into the process it spawns.

    The host supplies available baselines. Curator chooses their customization
    and business decomposition; runtime agents choose actual delegation. This
    entry does not install business materials or prescribe a strategy artifact.
    """
    area = Path(root) / AREA
    workspace = area / HOME
    if home is None:
        workspace.mkdir(parents=True)
    else:
        shutil.copytree(home, workspace, ignore=shutil.ignore_patterns("sessions", ".lock"))
    baseline = prepare(config, workdir=workdir, task=task, home=workspace)
    housed = house(baseline, model=subagent_model, deployment=area / "deployment")
    return Worker(
        baseline,
        root,
        provider_factory=None if guard is None else GuardedFactory(make_lazy_provider, guard),
        timeout=timeout,
        children=lambda current: confined(prepare_children(current, area, ["Raven", *housed]), current),
        withheld=withheld,
        area=area,
        confinement=confinement,
    )


def replicate(
    employee: Worker,
    config: Path,
    root: Path,
    *,
    subagent_model: str | None = None,
    timeout=180,
) -> Worker:
    """A replica of the started employee as it stands now, in a new `root`, with processes of its own.

    It gets a copy of the employee's home (without past sessions) and workdir, the state its strategies saved, and
    the revision installed in the employee and in each child harness, so it starts a drill where a drill played on
    the employee next would start. It keeps the employee's task, whose id the saved strategy state is bound to, and
    its provider factory, so a drill runs behind the partner's guard as the employee would. The replica is not
    started; its revision is compared again once it is.
    """
    root = Path(root)
    area = root / AREA
    workspace, workdir = area / HOME, area / WORKDIR
    shutil.copytree(
        employee.baseline.config.workspace_path,
        workspace,
        ignore=shutil.ignore_patterns("sessions", ".lock"),
        symlinks=True,
    )
    shutil.copytree(employee.baseline.workdir, workdir, symlinks=True)
    baseline = prepare(config, workdir=workdir, task=employee.baseline.task, home=workspace)
    housed = house(baseline, model=subagent_model, deployment=area / "deployment")
    children = confined(prepare_children(baseline, area, ["Raven", *housed]), baseline)
    if children.keys() != employee.children.keys():
        raise ValueError(f"a replica has child harnesses {sorted(children)}, the employee {sorted(employee.children)}")
    for name, child in children.items():
        child.artifact, child.plan = employee.children[name].artifact, employee.children[name].plan
    replica = Replica(
        employee.revision_id,
        baseline,
        root,
        provider_factory=employee.provider_factory,
        timeout=timeout,
        children=children,
        withheld=employee.withheld,
        area=area,
        confinement=employee.confinement,
    )
    if employee.confinement is not None:
        root.chmod(0o711)
    replica.artifact, replica.last_plan = employee.artifact, employee.last_plan
    saved = {f"{target.name.split('.')[0]}.json" for target in catalogue() if target.binding.endswith(".strategy")}
    folders = [
        (employee.area, area),
        *((child_directory(employee.area, name), child_directory(area, name)) for name in children),
    ]
    for source, target in folders:
        for name in saved:
            if (source / name).is_file() and not (source / name).is_symlink():
                target.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source / name, target / name)
        source_assembly, target_assembly = source / "assembly", target / "assembly"
        ledger = source_assembly / "content-state.json"
        if ledger.is_file() and not ledger.is_symlink():
            target_assembly.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ledger, target_assembly / ledger.name)
        for name in ("skill-inputs", "baseline-skills"):
            if (source_assembly / name).is_dir() and not (source_assembly / name).is_symlink():
                shutil.copytree(source_assembly / name, target_assembly / name, symlinks=True)
    same_revision(employee, replica)
    return replica


class Replica(Worker):
    """A worker that reports the employee's revision id on its executions.

    `Worker.revision_id` also fingerprints each child's baseline, whose paths differ between replicas; the replica
    holds the same revision (checked by `same_revision`), so its drills must name the revision the employee names.
    """

    def __init__(self, revision_id: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.employee_revision_id = revision_id

    @property
    def revision_id(self):
        return self.employee_revision_id


def revision(worker: Worker) -> dict:
    """The installed revision of the root and each child harness, without the paths that differ between replicas."""
    return {
        "root": worker.artifact.model_dump(mode="json"),
        "children": {
            name: {"artifact": child.artifact.model_dump(mode="json"), "grants": child.grants}
            for name, child in worker.children.items()
        },
    }


def bound(worker: Worker) -> str | None:
    """The authored package the worker's running generation bound, as its folder name."""
    packages = [row["package"] for row in worker.records() if row.get("kind") == "runtime.bound" and row.get("package")]
    return Path(str(packages[-1])).name if packages else None


def same_revision(employee: Worker, replica: Worker, *, running=False):
    """Refuse a replica that would play a drill on another revision than the employee's."""
    if revision(replica) != revision(employee):
        raise ValueError(f"replica {replica.root} does not hold the employee's installed revision")
    if running and bound(replica) != bound(employee):
        raise ValueError(f"replica {replica.root} bound {bound(replica)}, the employee {bound(employee)}")


def house(baseline, housed=HOUSED, *, model=None, deployment=None) -> list[str]:
    """Point each named external subagent's own Agent home into the employee's `subagents/` folder.

    Their homes sit in the employee's deployment tree, owned by their own Curator scope and never directly
    authored by the root strategy. A product's children do not inherit this process's environment, so the row forwards what they
    need from it; so does a row for the built-in Raven child, whose hosted launch keeps that row's environment.
    Subagents the configuration disables or that no product folder provides are left alone. Tools that need a
    person on the other end (`UNATTENDED`) are switched off: nobody answers them in a drill.
    With `model`, each housed subagent launches on the employee's provider and key with that model (see `pin`).
    """
    tools = baseline.config.tools
    tools.disabled_tools = [*tools.disabled_tools, *(name for name in UNATTENDED if name not in tools.disabled_tools)]
    rows = baseline.config.subagents.agents
    configured = {row.name: row for row in rows}
    extra = {name: os.environ[name] for name in FORWARDED if os.environ.get(name)}
    if extra and GENERIC_AGENT not in configured:
        rows = [
            *rows,
            ThirdPartyAcpSubagentConfig(
                name=GENERIC_AGENT, command="hosted", env=extra, description=f"Task Harness for {GENERIC_AGENT}"
            ),
        ]
    done = []
    for row in discover_product_rows():
        if row.name not in housed or not row.enabled or not getattr(configured.get(row.name), "enabled", True):
            continue
        home = baseline.config.workspace_path / SUBAGENTS / row.name
        home.mkdir(parents=True, exist_ok=True)
        env = {**(row.env or {}), **extra, housed[row.name]: str(home)}
        update = {"env": env}
        if model:
            pinned_env, command = pin(row, model, baseline.config, Path(deployment))
            update = {"env": {**env, **pinned_env}, "command": command}
        rows = [item for item in rows if item.name != row.name] + [row.model_copy(update=update)]
        done.append(row.name)
    baseline.config.subagents.agents = rows
    return done


def pin(row, model: str, config, deployment: Path) -> tuple[dict[str, str], str]:
    """Environment and command that launch a product on `model` through the employee's own provider and key.

    Each product's configuration is copied with that provider (its key in the copy, which is private to the run),
    the model, the employee's reasoning effort and its pinned context window in place, so a subagent never runs on
    a default effort or window of its own. A product whose sessions start in a tier of its own catalogue starts in
    the employee's tier instead when the catalogue has one of that name: a tier carries its own effort, which would
    otherwise override the pinned one (a shipped `high` default tier runs every call at high effort). The copy also
    carries the employee's permission settings: an unattended subagent has no one to answer an approval prompt, so it
    works under the same rules as the employee. Products run without a shell (`SHELLS`), and Raven-Research's
    end-of-turn verify gate runs without thinking: it asks for its verdict as a forced tool call, which a thinking
    DeepSeek model refuses (HTTP 400), and the gate then lets every draft through unreviewed.
    """
    defaults = config.agents.defaults
    provider = defaults.provider
    settings = getattr(config.providers, provider, None)
    key = getattr(settings, "api_key", None)
    if not key:
        raise ValueError(f"pinning a subagent model needs the employee's {provider} key")
    if not defaults.reasoning_effort:
        raise ValueError("pinning a subagent model needs the employee's reasoning effort set explicitly")
    permissions = config.permissions.model_dump(mode="json", by_alias=True, exclude_defaults=True)
    secret = {"Raven-PPT": "PPT_API_KEY", "Raven-Research": "RESEARCH_API_KEY"}.get(row.name)
    if secret is None:
        raise ValueError(f"no known way to pin the model of {row.name}")
    product = json.loads((product_folder(row.name) / "config.json").read_text())
    product.setdefault("agents", {}).setdefault("defaults", {}).update(
        {
            "model": model,
            "provider": provider,
            "reasoningEffort": defaults.reasoning_effort,
            **({"contextWindowTokens": defaults.context_window_tokens} if defaults.context_window_tokens else {}),
        }
    )
    product.setdefault("providers", {})[provider] = {"apiKey": key}
    tier = config.acp.default_mode
    if tier and tier in ((product.get("acp") or {}).get("modes") or {}):
        product["acp"]["defaultMode"] = tier
    disabled = product.setdefault("tools", {}).setdefault("disabledTools", [])
    disabled.extend(name for name in (*UNATTENDED, *SHELLS) if name not in disabled)
    verify = (((product.get("plugins") or {}).get("config") or {}).get("research-flow") or {}).get("verify")
    if isinstance(verify, dict) and str(model).startswith("deepseek/"):
        verify["reasoningEffort"] = "none"
    if permissions:
        product["permissions"] = {**product.get("permissions", {}), **permissions}
    path = deployment / f"{row.name.lower()}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(product, ensure_ascii=False, indent=2))
    path.chmod(0o600)
    return {secret: key}, f"{row.command} --config {shlex.quote(str(path))}"


class Together:
    """Trials each played on its own replica of the employee, made from it as the trials begin (see `replicate`)
    and closed when they end; trials of one group run at once.

    The employee itself plays no trial, so every drill starts from its installed revision with a clean workdir and
    home: no drill reads another's files, and nothing a drill wrote carries into the next one or the next round.
    `trials` maps each trial's name to it; `spawn(employee, label)` makes an unstarted replica, labelled with the
    trial's opaque session label rather than its name, because the replica's paths show in the records the Curator
    reads. `placed` is filled with the workdir and home each named trial played in, for readers of the files a drill
    wrote.
    """

    def __init__(self, trials: dict, spawn, placed: dict | None = None):
        if not trials:
            raise ValueError("playing trials together needs at least one trial")
        self.trials, self.spawn, self.placed, self.played = dict(trials), spawn, placed, 0

    async def run(self, worker):
        self.played += 1
        replicas = {name: self.spawn(worker, f"{self.played}-{opaque(name)}") for name in self.trials}
        if self.placed is not None:
            self.placed.update(
                {
                    name: {"workdir": replica.baseline.workdir, "home": replica.baseline.config.workspace_path}
                    for name, replica in replicas.items()
                }
            )
        tasks = []
        try:
            await asyncio.gather(*(replica.start() for replica in replicas.values()))
            for replica in replicas.values():
                same_revision(worker, replica, running=True)
            try:
                async with asyncio.TaskGroup() as group:
                    tasks = [group.create_task(trial.run(replicas[name])) for name, trial in self.trials.items()]
            except ExceptionGroup as failed:
                raise failed.exceptions[0] from failed
        finally:
            await asyncio.gather(*(replica.close() for replica in replicas.values()), return_exceptions=True)
        sessions = {}
        for task in tasks:
            produced = task.result()
            if sessions.keys() & produced.keys():
                raise ValueError(f"trials produced the same session key: {sorted(sessions.keys() & produced.keys())}")
            sessions.update(produced)
        return sessions


BOUNDARIES = "boundaries.jsonl"


def seal(root: Path) -> None:
    """Lay out a run root for a confined employee before anything is written in it: everything this process writes
    from now on is readable by root alone, the root and its replicas' folder can be passed but not listed, and the
    boundary log is one the partner's guard, inside the confined process, can write and never read."""
    os.umask(0o077)
    root = Path(root)
    (root / REPLICAS).mkdir(parents=True, exist_ok=True)
    for folder in (root, root / REPLICAS):
        folder.chmod(0o711)
    log = root / BOUNDARIES
    log.touch()
    log.chmod(0o602)


def unsealed(employee: Worker, *, closed=()) -> list[str]:
    """What a confined employee's user can reach and must not, or cannot reach and must, once it is hired (see
    `Confinement.probe`): it must write its area and nothing else of the run, list neither the run root, its
    replicas' folder, the folder holding the run nor the system's temporary folder (where other processes leave
    files anyone may read), and reach neither the repository nor any path of `closed`.

    The folders above the run that others may pass but not list are private: every entry of theirs off the path to
    the run (the runs beside it, and further up whatever else the owner keeps there) must be closed too. The first
    folder others may list ends the walk; what lies beside it is not the owner's."""
    root = employee.root
    kept = {AREA, REPLICAS, BOUNDARIES}
    private = []
    below, folder = root, root.parent
    while folder != folder.parent and not folder.stat().st_mode & 0o004:
        private.extend(path for path in sorted(folder.iterdir()) if path != below)
        below, folder = folder, folder.parent
    employee.confinement.hand_over(employee.area, employee.baseline.workdir)
    return employee.confinement.probe(
        writable=[employee.area],
        unlisted=[root, root / REPLICAS, root.parent, Path(tempfile.gettempdir())],
        closed=[
            *closed,
            employee.confinement.repository,
            *(path for path in sorted(root.iterdir()) if path.name not in kept),
            *private,
        ],
    )


def unseal(root: Path) -> None:
    """Close a finished run to the confined user, so a later run's employee cannot enter it."""
    Path(root).chmod(0o700)


def skills(worker: Worker) -> Path:
    """The employee's skill pool: materials the party puts here become sources it can read."""
    return worker.baseline.config.workspace_path / "skills"


def baseline(home: Path | None) -> dict[str, str]:
    """The employee's starting agent home as a fingerprint: each file's path and SHA-256, past sessions left out."""
    if home is None:
        return {}
    return {
        path.relative_to(home).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(Path(home).rglob("*"))
        if path.is_file() and "sessions" not in path.relative_to(home).parts and path.name != ".lock"
    }


def _digest(folder: Path) -> str:
    files = sorted(path for path in folder.rglob("*") if path.is_file() and "__pycache__" not in path.parts)
    total = hashlib.sha256()
    for path in files:
        total.update(path.relative_to(folder).as_posix().encode())
        total.update(hashlib.sha256(path.read_bytes()).digest())
    return total.hexdigest()


def starting_harness(repository: Path) -> dict:
    """Which code every harness starts from: Raven's commit, any uncommitted change to it, and each Raven-X product.

    Whatever the Curator has not touched is the starting state, so a reader can check it was the same across runs.
    """

    def git(*argv):
        executable = shutil.which("git")
        if executable is None:
            return ""
        try:
            return subprocess.run(
                [executable, *argv], cwd=repository, capture_output=True, text=True, timeout=30
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""

    agents = Path(repository) / "agents"
    return {
        "raven_commit": git("rev-parse", "HEAD") or None,
        "raven_modified": bool(git("status", "--porcelain", "--", "raven", "agents")),
        "raven_diff": hashlib.sha256(git("diff", "HEAD", "--", "raven", "agents").encode()).hexdigest(),
        "products": {folder.name: _digest(folder) for folder in sorted(agents.glob("raven-*")) if folder.is_dir()},
    }


def workplace(path: Path | None) -> Path:
    """The employee's working directory: a new empty folder, never the repository or anything holding it.

    Every drill's replica copies this folder whole, so whatever sits in it reaches the employee; the repository
    holds the scenario, its drill cards and the judges' tests.
    """
    if path is None:
        return Path(tempfile.mkdtemp(prefix="raven-simulation-workdir-"))
    path, repository = Path(path).resolve(), Path(__file__).resolve().parents[2]
    if path == repository or repository.is_relative_to(path) or path.is_relative_to(repository):
        raise ValueError(f"the employee's workdir may not be the repository, inside it or above it: {path}")
    if path.exists() and any(path.iterdir()):
        raise ValueError(f"the employee's workdir must be new or empty: {path}")
    path.mkdir(parents=True, exist_ok=True)
    return path
