"""What a live session borrows from the automation and simulation packages: hiring the employee on the person's task,
setting up the session's process the way an automated run sets up its own, handing the scenario's materials over the
way a counterpart uploads them, the norms an automatic assessor may draw criteria from, and the AI's draft of the next
message of a trial the person holds and its proposed acceptance checks, from what the counterpart may see. This is
the one module of the Studio that imports those packages; the session's process (`experimental.webui.session_host`) reaches them only
through it, and the server not at all.

Resuming a session after its process ended hires the employee of the run directory again (`rehire`) and loads the
deployment the session saved (`load`); only an employee that works alone (no `delegation`) has a deployment that can be
saved, so a session whose employee delegates lasts as long as its process once it has changed its harness.
"""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from experimental.cultivation.counterpart.owner import attached
from experimental.cultivation.employee import Together, hire_task, starting_harness, withheld, workplace
from experimental.cultivation.employee import replicate as replica_of
from experimental.harness.assessor.standard import TEXT_FILES
from experimental.harness.experience.model import ModelClient, ModelLimits
from experimental.harness.participation.protocols import Handover
from experimental.harness.raven_adapter import deployment
from experimental.simulation.bench import caching
from experimental.simulation.bench.scenario import Scenario

REPOSITORY = Path(__file__).resolve().parents[2]
MATERIAL_FILE = 20_000
REFERENCE_FILE = 80_000
QUESTION = (
    "You draft the next message a person sends an AI employee in a trial they hold, so they can see how it handles "
    "one hard case. The packet holds the employee's job, the counterpart it works for, the materials it was handed, "
    "the checks its work is judged by, the requirements an analyst raised after earlier trials, example messages the "
    "counterpart sends, this trial so far, and the drafts written earlier in it.\n\n"
    "Write one message the counterpart would really send in this job, aimed at one weakness: a requirement that may "
    "not hold yet, or a case the materials and checks cover that this trial has not reached. The person can only send "
    "text, so put everything the employee needs into the message itself and never point to files or attachments. Do "
    "not reveal what the message tests. If the trial has begun, continue it the way the counterpart would. Make it "
    "different from every earlier draft. Write in the language of the job.\n\n"
    "Submit `message`, the text to send; `aim`, one sentence on what it tests; and `good`, what a good answer does, in "
    "one to three short points, for the person to judge the reply by."
)


PROPOSE = (
    "You help a person set the acceptance checks for an AI employee's work without writing them. The packet holds the "
    "employee's job, the counterpart it works for, the materials it was handed, the checks already in force (the "
    "scenario's own and those the person chose), this round's trials (each request and the employee's reply) and the "
    "person's remarks and marks.\n\n"
    "Find at most three matters the person would care about that no check in force covers and that only the person can "
    "settle: taste or policy, such as what to stress, what may be claimed, how long, what tone, what format, for which "
    "audience. Never a matter of fact the materials settle. For each, write `topic`, a short question the person "
    "answers; `why`, one sentence on what in this round's replies raised it; and exactly two `options`, each an "
    "`example`, a short fragment of a reply as it would read (taken from or modelled on this round's replies), and the "
    "`rule` it stands for, one sentence a judge could apply to any reply. The two options differ in that one matter "
    "only. Write in the language of the job. Fewer, sharper questions beat more; submit none when nothing is open."
)


class Option(BaseModel):
    """One answer to a proposed check: how a reply would read, and the rule that answer stands for."""

    model_config = ConfigDict(extra="forbid")

    example: str = Field(min_length=1, description="A short fragment of a reply as it would read")
    rule: str = Field(min_length=1, description="The rule this answer stands for, one sentence a judge can apply")


class Proposal(BaseModel):
    """A matter only the person can settle, put as a choice between two answers."""

    model_config = ConfigDict(extra="forbid")

    topic: str = Field(min_length=1, description="A short question the person answers")
    why: str = Field(min_length=1, description="What in this round's replies raised it")
    options: list[Option] = Field(min_length=2, max_length=2)


class Proposals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[Proposal] = Field(max_length=3)


INQUIRE = (
    "You answer a person's question about one step in cultivating an AI employee. The packet names the `role` you "
    "stand in for: the analyst, who reads a round's trials and judgements, decides what happens next and raises "
    "requirements; or the curator, who changes the employee's harness to meet them. It holds the employee's `job`, "
    "the `round` (0 is the onboarding), the `record` of what that role decided in that round and why, the "
    "`question`, and the questions answered `earlier` about the same step.\n\n"
    "Answer from the record only, in the first person as that role. Say plainly what was decided and on what "
    "evidence; when the record does not say, say so rather than guess. Use plain words for someone who does not know "
    "the system's internals, and quote the record where it helps. Do not promise to change anything: the person "
    "changes the next curation by leaving a remark before it. Answer in the language of the question, and submit "
    "`answer`."
)


class Answer(BaseModel):
    """The answer to a person's question about one role's step of a round."""

    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, description="The answer, in the language of the question")


class Question(BaseModel):
    """A drafted trial message, with what it tests and what a good answer does, for the person to judge the reply by."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, description="The message to send, as the counterpart writes it")
    aim: str = Field(min_length=1, description="One sentence on what the message tests")
    good: str = Field(min_length=1, description="What a good answer does, in one to three short points")


def prepare() -> None:
    """Set up the session's process before anything is hired, as an automated run does: the gateway cache
    breakpoints (`experimental.simulation.bench.caching`)."""
    caching.install()


def starting() -> dict:
    """Which code every harness of the session starts from (`experimental.cultivation.employee.starting_harness`)."""
    return starting_harness(REPOSITORY)


def hire(contract, config: Path, *, task, workdir: Path, root: Path, subagent_model, timeout, guard, delegation=True):
    """The employee of a new live run: a plain Raven baseline on `task` (a `Task`), in its own home under `root` and a
    new working directory, behind the partner's guard, whose Curator may not read the evaluation side (`withheld`)."""
    return hire_task(
        task,
        config,
        workdir=workplace(workdir),
        root=root,
        subagent_model=subagent_model,
        timeout=timeout,
        withheld=withheld(contract),
        guard=guard,
        delegation=delegation,
    )


def rehire(contract, config: Path, *, task, workdir: Path, root: Path, subagent_model, timeout, guard, delegation=True):
    """The employee of an existing run directory, in the home and working directory it had, on the run's task (its id
    too, which its saved state is bound to); `load` then puts back the revision the session saved."""
    Path(workdir).mkdir(parents=True, exist_ok=True)
    return hire_task(
        task,
        config,
        workdir=Path(workdir),
        root=root,
        subagent_model=subagent_model,
        timeout=timeout,
        withheld=withheld(contract),
        guard=guard,
        delegation=delegation,
        existing=True,
    )


def replicate(employee, config: Path, root: Path, *, subagent_model, timeout):
    """A replica of the started employee as it stands, in `root`, to play a scripted trial on and close: what the trial
    leaves in the employee's home or working directory stays in the replica."""
    return replica_of(employee, config, root, subagent_model=subagent_model, timeout=timeout)


def together(trials: dict, spawn, placed: dict):
    """`trials` by name, each played on its own replica `spawn` makes, all at once (`automation.employee.Together`);
    `placed` receives the working directory each plays in."""
    return Together(trials, spawn, placed)


async def save(employee, path: Path) -> bool:
    """Save the employee's active deployment to `path`; False when it delegates, whose deployment cannot be kept."""
    if employee.children:
        return False
    await deployment.save(employee, path)
    return True


async def load(employee, path: Path) -> None:
    """Put a deployment `save` wrote back into the started employee."""
    await deployment.load(employee, path)


def hand_over(contract, names, *, uploads: Path, shared: Path) -> tuple[Handover, ...]:
    """Upload the named materials the way the counterpart uploads files, into the employee's `uploads` folder and the
    working directory's (`shared`), and name them as a signal's handovers; only the materials the counterpart may hand over
    (`handed`) are."""
    scenario = Scenario.of(contract, judged=False)
    unknown = sorted(set(names) - set(scenario.handed))
    if unknown:
        raise ValueError(f"the scenario hands over no materials named {unknown}")
    return attached(scenario.upload(list(names), uploads, shared=shared), scenario.kinds)


def standing_norms(contract, names) -> dict[str, str]:
    """The norms among the handed-over `names` an automatic assessor may draw criteria from, by name to text."""
    return Scenario.of(contract, judged=False).standing_norms(names)


def references(contract, names, home: Path) -> dict[str, str]:
    """What the checks of a scenario without an examiner of its own are judged against: the text files of the
    handed-over `names` and the information the preparation handed the employee under `home`, as the employee holds
    them, so a verdict on a fact rests on what the employee was given."""
    from experimental.cultivation.collector.curator import INFORMATION_FILE

    scenario = Scenario.of(contract, judged=False)
    out = {}
    for name in names:
        folder = scenario.materials.get(name)
        for path in sorted(Path(folder).rglob("*")) if folder is not None else ():
            if path.is_file() and path.suffix.lower() in TEXT_FILES:
                out[f"{name}/{path.relative_to(folder)}"] = path.read_text(errors="replace")[:REFERENCE_FILE]
    prepared = Path(home) / INFORMATION_FILE
    if prepared.is_file():
        out[INFORMATION_FILE] = prepared.read_text(errors="replace")[:REFERENCE_FILE]
    return out


def counterpart_view(contract, names) -> dict:
    """What the counterpart holds that a drafted trial message may draw on: its persona cards, the text files of the
    handed-over `names` among the materials it may see (a material's own document may only list the others), and the
    checks it judges by. Nothing of the evaluation side's own, so a draft carries no held-out case into a trial."""
    scenario = Scenario.of(contract, judged=False)
    materials = {}
    for name in names:
        folder = scenario.materials.get(name)
        if folder is None:
            continue
        for path in sorted(Path(folder).rglob("*")):
            if path.is_file() and path.suffix.lower() in TEXT_FILES:
                materials[f"{name}/{path.relative_to(folder)}"] = path.read_text(errors="replace")[:MATERIAL_FILE]
    return {
        "counterpart": [persona.text for persona in scenario.personas],
        "materials": materials,
        "checks": [criterion.check for criterion in scenario.criteria],
    }


async def question(provider, packet: dict, *, model, effort, timeout) -> dict:
    """The AI's draft of the next message of a trial the person holds (`QUESTION`), from `packet`."""
    client = ModelClient(
        provider, QUESTION, model=model, effort=effort, limits=ModelLimits(timeout=timeout), source="trial materials"
    )
    return (await client.submit(packet, Question, "submit_question")).model_dump()


def preparer(contract, released, material_root: Path, *, records: Path, model, effort, ask, research: bool):
    """The information preparation run before the onboarding curation (`experimental.cultivation.collector.scenario`): it reads the
    handed materials, asks the person once through `ask` and, with `research`, searches the web, then hands the
    reviewed description to the Curator."""
    from experimental.cultivation.collector.scenario import scenario_preparer

    return scenario_preparer(
        contract,
        released,
        material_root,
        records=records,
        model=model,
        effort=effort,
        ask=ask,
        researcher="exchange" if research else None,
    )


async def inquire(provider, packet: dict, *, model, effort, timeout) -> str:
    """The answer to a person's question about the analyst's or the curator's step of a round (`INQUIRE`)."""
    client = ModelClient(
        provider, INQUIRE, model=model, effort=effort, limits=ModelLimits(timeout=timeout), source="round record"
    )
    return (await client.submit(packet, Answer, "submit_answer")).answer


async def propose(provider, packet: dict, *, model, effort, timeout) -> list[dict]:
    """The AI's proposed acceptance checks for what the person has not settled yet (`PROPOSE`), from `packet`."""
    client = ModelClient(
        provider, PROPOSE, model=model, effort=effort, limits=ModelLimits(timeout=timeout), source="trial record"
    )
    return [item.model_dump() for item in (await client.submit(packet, Proposals, "submit_proposals")).items]
