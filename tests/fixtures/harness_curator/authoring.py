"""Small code-producing fixtures for tests that exercise real strategy ownership."""

import ast
import json

from experimental.curator.harness import Artifact

CAPABILITY = """from experimental.curator.harness.strategies import CapabilityStrategy
from experimental.curator.harness.resources import CapabilityContribution, RegistrationReceipt, SelectionRequest, CapabilitySelection

class Capability(CapabilityStrategy):
    def __init__(self, state, registrar):
        self.state, self.registrar = state, registrar
    def register(self, contribution: CapabilityContribution) -> RegistrationReceipt:
        return self.registrar.register(contribution)
    async def select(self, request: SelectionRequest) -> CapabilitySelection:
        return CapabilitySelection()

def create(state, task, *, registrar):
    return Capability(state, registrar)
"""


MEMORY = """from experimental.curator.harness.strategies import MemoryStrategy
from experimental.curator.harness.context import InitialContext, ContextRequest, ContextView
from experimental.curator.harness.preparation import PreparationRequest

class Memory(MemoryStrategy[dict, str, str]):
    def __init__(self, state, host):
        self.state, self.host = state, host
    async def initialize(self, initial: InitialContext) -> dict:
        return {"sources": [source.name for source in initial.sources]}
    async def compose(self, request: ContextRequest) -> ContextView:
        return ContextView(messages=request.messages)

def create(state, task, *, host):
    return Memory(state, host)
"""


def add_method(source, class_name, method):
    """Insert a concrete method into the authored class, preserving its factory and helpers."""
    node = next(node for node in ast.parse(source).body if isinstance(node, ast.ClassDef) and node.name == class_name)
    lines = source.splitlines(keepends=True)
    lines.insert(
        node.end_lineno, "\n" + "\n".join("    " + line if line else "" for line in method.splitlines()) + "\n"
    )
    return "".join(lines)


def capability(resources, *, source=CAPABILITY, module="capability_impl", class_name="Capability", files=None):
    source = (
        "import json\nfrom pydantic import TypeAdapter\nfrom experimental.curator.harness.preparation import PreparationRequest\n"
        + source
    )
    source = add_method(
        source,
        class_name,
        """def prepare(self, request: PreparationRequest) -> None:
    for row in json.loads(request.assets["capability_resources.json"]):
        receipt = self.register(TypeAdapter(CapabilityContribution).validate_python(row))
        if receipt.status == "rejected":
            raise ValueError(receipt.reason)
""",
    )
    return Artifact(
        values={"capability.strategy": {"factory": f"{module}:create"}},
        files={
            **(files or {}),
            f"{module}.py": source,
            "capability_resources.json": json.dumps(resources),
        },
    )


def profile(content, *, module="memory_impl", files=None):
    source = "import json\n" + add_method(
        MEMORY,
        "Memory",
        """def prepare(self, request: PreparationRequest) -> None:
    self.host.profile(json.loads(request.assets["memory_profile.json"]))
""",
    )
    return Artifact(
        values={"memory.strategy": {"factory": f"{module}:create"}},
        files={
            **(files or {}),
            f"{module}.py": source,
            "memory_profile.json": json.dumps(content),
        },
    )


def combine(*artifacts):
    values, files = {}, {}
    for artifact in artifacts:
        if values.keys() & artifact.values.keys():
            raise ValueError("test artifacts choose the same strategy twice")
        values.update(artifact.values)
        files.update(artifact.files)
    return Artifact(values=values, files=files)


PLANNING = """import json
from experimental.curator.harness.strategies import PlanningStrategy
from experimental.curator.harness.preparation import PreparationRequest
from experimental.curator.harness.interaction import InteractionRequest
from experimental.curator.harness.planning import PlanningInitialization, PlanningProjection, PlanningResult
from experimental.requirements import Requirement
from raven.playbook import PlaybookSpec

class Planning(PlanningStrategy[dict, dict, dict]):
    def __init__(self, state, host):
        self.state, self.host = state, host
    def prepare(self, request: PreparationRequest) -> None:
        for item in json.loads(request.assets["procedures.json"]):
            self.host.playbook(PlaybookSpec.model_validate(item["spec"]), {
                name: [Requirement.model_validate(row) for row in rows]
                for name, rows in item["requirements"].items()
            })
    def _projection(self) -> PlanningProjection[dict]:
        return PlanningProjection[dict](view=dict(self.state))
    async def initialize(self, initial: PlanningInitialization) -> PlanningProjection[dict]:
        self.state.setdefault("task", initial.task)
        return self._projection()
    async def interact(self, request: InteractionRequest[dict]) -> PlanningResult[dict, dict]:
        if request.mode == "command":
            self.state.update(request.command)
        projection = self._projection()
        return PlanningResult[dict, dict](reply=projection.view, projection=projection)
def create(state, *, host):
    return Planning(state, host)
"""


def planning(procedures, *, module="planning_impl"):
    return Artifact(
        values={"planning.strategy": {"factory": f"{module}:create"}},
        files={f"{module}.py": PLANNING, "procedures.json": json.dumps(procedures)},
    )


ACTION = """import json
from experimental.curator.harness.strategies import ActionStrategy
from experimental.curator.harness.preparation import PreparationRequest
from experimental.curator.raven_adapter.preparation import GenerationPolicy, ExecutionPolicy

class Action(ActionStrategy[str, str]):
    def __init__(self, host):
        self.host = host
    def prepare(self, request: PreparationRequest) -> None:
        values = json.loads(request.assets["action_policy.json"])
        self.host.generation(GenerationPolicy(**values.get("generation", {})))
        self.host.execution(ExecutionPolicy(**values.get("execution", {})))
def create(state, task, *, host):
    return Action(host)
"""


def action(*, generation=None, execution=None, module="action_impl"):
    return Artifact(
        values={"action.strategy": {"factory": f"{module}:create", "events": []}},
        files={
            f"{module}.py": ACTION,
            "action_policy.json": json.dumps({"generation": generation or {}, "execution": execution or {}}),
        },
    )


def setup(role, statements, *, files=None, binding=None):
    """Generate a role-owned setup method; statements call only that role's host facilities."""
    if role == "memory":
        source = MEMORY
    elif role == "capability":
        source = CAPABILITY.replace(
            "def __init__(self, state, registrar):", "def __init__(self, state, registrar, host):"
        )
        source = source.replace(
            "self.state, self.registrar = state, registrar",
            "self.state, self.registrar, self.host = state, registrar, host",
        )
        source = source.replace(
            "def create(state, task, *, registrar):", "def create(state, task, *, registrar, host):"
        )
        source = source.replace("return Capability(state, registrar)", "return Capability(state, registrar, host)")
    elif role == "action":
        source = """from experimental.curator.harness.strategies import ActionStrategy
class Action(ActionStrategy[str, str]):
    def __init__(self, host):
        self.host = host
def create(state, task, *, host):
    return Action(host)
"""
    else:
        raise ValueError("unsupported setup fixture role")
    source = "from experimental.curator.harness.preparation import PreparationRequest\n" + source
    source = add_method(
        source,
        role.title(),
        "def prepare(self, request: PreparationRequest) -> None:\n"
        + "\n".join("    " + line for line in statements.splitlines()),
    )
    module = f"{role}_setup"
    values = {"factory": f"{module}:create", **({"events": []} if role == "action" else {}), **(binding or {})}
    return Artifact(values={f"{role}.strategy": values}, files={**(files or {}), f"{module}.py": source})
