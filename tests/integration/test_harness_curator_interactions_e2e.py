"""Native execution of source-based context and registered cross-strategy interactions."""

import json
from functools import partial
from pathlib import Path

import pytest

from experimental.curator.harness import Task
from experimental.curator.raven_adapter.worker import Worker
from raven.contracts.llm_provider import LLMResponse
from tests.fixtures.harness_curator.authoring import capability
from tests.integration.test_harness_curator_e2e import baseline as baseline
from tests.integration.test_harness_curator_e2e import plan_for, replay_provider
from tests.integration.test_harness_curator_planning_e2e import response

pytestmark = pytest.mark.integration

MEMORY = """import json
from experimental.curator.harness.preparation import PreparationRequest
from pydantic import BaseModel
from experimental.curator.harness.context import InitialContext, ContextRequest, ContextView
from experimental.curator.harness.interaction import InteractionRequest
from experimental.curator.harness.strategies import MemoryStrategy

class Layout(BaseModel):
    order: list[str]
class Note(BaseModel):
    text: str
class Receipt(BaseModel):
    count: int

class Memory(MemoryStrategy[Layout, Note, Receipt]):
    def __init__(self, state, shared, host):
        self.state, self.shared, self.host = state, shared, host
    async def initialize(self, initial: InitialContext) -> Layout:
        self.state.setdefault("session", initial.scope.session_key)
        self.shared.setdefault("notes", [])
        order = ["bootstrap", *[source.name for source in initial.sources if source.name != "bootstrap"]]
        return Layout(order=order)
    async def interact(self, request: InteractionRequest[Note]) -> Receipt:
        if request.command.text not in self.shared["notes"]:
            self.shared["notes"].append(request.command.text)
        return Receipt(count=len(self.shared["notes"]))
    async def compose(self, request: ContextRequest) -> ContextView:
        sources = {source.name: source for source in request.sources if source.role == "system"}
        ordered = [name for name in request.initialization["order"] if name in sources]
        ordered += [name for name in sources if name not in ordered]
        text = "\\n\\n".join(sources[name].text for name in ordered)
        text += "\\nWorking notes: " + ", ".join(self.shared["notes"])
        return ContextView(messages=[
            {"role": "system", "content": text},
            *[message for message in request.messages if message["role"] != "system"],
        ])

    def prepare(self, request: PreparationRequest) -> None:
        if "memory_profile.json" in request.assets:
            self.host.profile(json.loads(request.assets["memory_profile.json"]))

def create(state, task, *, shared, host):
    return Memory(state, shared, host)
"""

CAPABILITY = """from experimental.curator.harness.strategies import CapabilityStrategy
from experimental.curator.harness.resources import (
    CapabilityContribution, RegistrationReceipt, SelectionRequest, CapabilitySelection, SkillSelection,
)
from raven.contracts.tool import Tool

class Probe(Tool):
    name = "receipt_probe"
    description = "Return an actual local receipt."
    parameters = {"type": "object", "properties": {}}
    async def execute(self, **kwargs):
        return "TRUTH:cobalt"

def probe():
    return Probe()

class Capability(CapabilityStrategy):
    def __init__(self, state, registrar):
        self.state, self.registrar = state, registrar
    def register(self, contribution: CapabilityContribution) -> RegistrationReceipt:
        return self.registrar.register(contribution)
    async def select(self, request: SelectionRequest) -> CapabilitySelection:
        self.state["selections"] = self.state.get("selections", 0) + 1
        return CapabilitySelection(
            tools=("receipt_probe",), skills=(SkillSelection(name="evidence", delivery="body"),),
        )

def create(state, task, *, registrar):
    return Capability(state, registrar)
"""

ACTION = """from experimental.curator.raven_adapter.preparation import ExecutionPolicy
import json
from experimental.curator.harness.preparation import PreparationRequest
from pydantic import BaseModel
from experimental.curator.harness.strategies import ActionStrategy
from experimental.curator.harness.action import (
    ActionEvent, ActionDecision, ActionInteraction, ActionResponse,
)
from raven.contracts.tool import Tool

REQUIRE_SECONDARY = False

class Request(BaseModel):
    note: str = ""
    finish: bool = False
class Reply(BaseModel):
    ready: bool

class Action(ActionStrategy[Request, Reply]):
    def __init__(self, state, peers, host):
        self.state, self.peers, self.host = state, peers, host
    async def handle_event(self, event: ActionEvent) -> ActionDecision:
        if event.kind == "proposal" and event.stage == "dispatch" and event.calls[0].name == "publish":
            ready = self.state.get("verified", False)
            if REQUIRE_SECONDARY:
                ready = ready and self.state.get("secondary", False)
            if not ready:
                return ActionDecision(control="reject", feedback="Complete required verification before publication.")
        if event.kind == "proposal" and event.stage == "reply" and event.text == "UNVERIFIED_DELIVERY":
            return ActionDecision(control="finish", reply="Publication has not been verified.")
        if event.kind == "outcome":
            results = [row for row in event.messages if row.get("role") == "tool"]
            if results:
                latest = results[-1]
                if latest.get("name") == "verify" and "VERIFIED_PRIMARY" in str(latest.get("content")):
                    self.state["verified"] = True
                if latest.get("name") == "verify_secondary" and "VERIFIED_SECONDARY" in str(latest.get("content")):
                    self.state["secondary"] = True
                if latest.get("name") == "publish" and "PUBLISHED_RECEIPT" in str(latest.get("content")):
                    self.state["published_turn"] = event.scope.turn_id
        if event.kind == "control" and event.receipt.status == "applied":
            self.state.setdefault("applied_controls", []).append(event.receipt.control)
        return ActionDecision()
    async def handle_request(self, request: ActionInteraction[Request]) -> ActionResponse[Reply]:
        if request.command.note:
            await self.peers.interact_memory({"text": request.command.note})
        ready = self.state.get("published_turn") == request.scope.turn_id
        decision = ActionDecision()
        if request.command.finish and ready:
            decision = ActionDecision(control="finish", reply="Validated publication is complete.")
        return ActionResponse(reply=Reply(ready=ready), decision=decision)

    def prepare(self, request: PreparationRequest) -> None:
        self.host.execution(ExecutionPolicy(**json.loads(request.assets.get("action_budget.json", "{}"))))

def create(state, task, *, peers, host):
    return Action(state, peers, host)

class Operation(Tool):
    name = "operation"
    description = "Perform a local test operation and return its actual receipt."
    parameters = {"type": "object", "properties": {}}
    def __init__(self, name, result):
        self.name, self.result = name, result
    async def execute(self, **kwargs):
        return self.result

def verify():
    return Operation("verify", "VERIFIED_PRIMARY")
def publish():
    return Operation("publish", "PUBLISHED_RECEIPT")
def verify_secondary():
    return Operation("verify_secondary", "VERIFIED_SECONDARY")
"""


def skill(name, body):
    return {
        "kind": "skill",
        "name": name,
        "source": "Owner-supplied procedure",
        "files": {"SKILL.md": f"---\nname: {name}\ndescription: Obtain actual evidence.\n---\n{body}\n"},
    }


@pytest.mark.asyncio
async def test_memory_initial_organization_same_turn_interaction_and_revision(baseline, tmp_path):
    baseline.task = Task(id="context-task", text="Organize supplied profile and retain working notes.")
    baseline.config.permissions.tools["context_note"] = "allow"
    actions = [
        response("context_note", {"request": {"text": "ACTUAL_NOTE"}}),
        LLMResponse(content="The note is retained."),
        LLMResponse(content="The new profile is active."),
    ]
    async with Worker(
        baseline,
        tmp_path / "worker",
        timeout=30,
        provider_factory=partial(replay_provider, responses=actions),
    ) as worker:
        proposed = {
            "values": {
                "memory.strategy": {
                    "factory": "context_memory:create",
                    "tool": {"name": "context_note", "description": "Record a working note."},
                },
            },
            "files": {
                "context_memory.py": MEMORY,
                "memory_profile.json": json.dumps({"agent_memory/profile/agent.md": "PROFILE_STYLE: brief"}),
            },
        }
        view = await worker.inspect()
        await worker.install(view.declaration.accept(plan_for(*proposed["values"]), proposed))
        first = await worker.run("Record the note and acknowledge it.")
        assert not first.errors, first.errors
        requests = [row["parameters"] for row in first.records if row["kind"] == "provider.request"]
        assert len(requests) == 2
        system = requests[0]["messages"][0]["content"]
        assert system.index("PROFILE_STYLE: brief") < system.index("# Raven")
        assert "ACTUAL_NOTE" not in str(requests[0]["messages"])
        assert "Working notes: ACTUAL_NOTE" in str(requests[1]["messages"])
        assert sum(row["kind"] == "memory.call" and row["operation"] == "initialize" for row in first.records) == 1
        view = await worker.inspect()
        assert view.facts["memory"]["shared"]["notes"] == ["ACTUAL_NOTE"]
        assert view.facts["memory"]["sessions"]["curator:task"]["session"] == "curator:task"
        change = {
            "values": {"memory.strategy": proposed["values"]["memory.strategy"]},
            "files": {"memory_profile.json": json.dumps({"agent_memory/profile/agent.md": "PROFILE_STYLE: detailed"})},
        }
        await worker.install(view.declaration.accept(plan_for("memory.strategy"), change))
        second = await worker.run("Use the updated profile and retain the note.")
        assert not second.errors, second.errors
        requests = [row["parameters"] for row in second.records if row["kind"] == "provider.request"]
        text = str(requests[0]["messages"])
        assert "PROFILE_STYLE: detailed" in text and "PROFILE_STYLE: brief" not in text
        assert "Working notes: ACTUAL_NOTE" in text


@pytest.mark.asyncio
async def test_capability_body_delivery_execution_and_resource_retirement(baseline, tmp_path):
    baseline.task = Task(id="capability-task", text="Use the supplied evidence procedure.")
    baseline.config.permissions.tools["receipt_probe"] = "allow"
    actions = [response("receipt_probe", {}), LLMResponse(content="The receipt is available.")]
    async with Worker(
        baseline,
        tmp_path / "worker",
        timeout=30,
        provider_factory=partial(replay_provider, responses=actions),
    ) as worker:
        proposed = capability(
            [
                {"kind": "tool", "name": "receipt_probe", "factory": "capabilities:probe"},
                skill("evidence", "PROCEDURE_ORIGINAL: call receipt_probe for evidence."),
                skill("obsolete", "This procedure will be retired."),
            ],
            source=CAPABILITY,
            module="capabilities",
        ).model_dump(mode="json")
        view = await worker.inspect()
        await worker.install(view.declaration.accept(plan_for(*proposed["values"]), proposed))
        first = await worker.run("Get actual evidence.")
        assert not first.errors, first.errors
        requests = [row["parameters"] for row in first.records if row["kind"] == "provider.request"]
        assert len(requests) == 2
        assert {row["function"]["name"] for row in requests[0]["tools"]} == {"receipt_probe"}
        assert "PROCEDURE_ORIGINAL" in str(requests[0]["messages"])
        assert any(
            row.get("role") == "tool" and "TRUTH:cobalt" in str(row.get("content")) for row in requests[1]["messages"]
        )
        view = await worker.inspect()
        before = view.facts["capability"]["sessions"]["curator:task"]["selections"]
        revised = capability(
            [
                {"kind": "tool", "name": "receipt_probe", "factory": "capabilities:probe"},
                skill("evidence", "PROCEDURE_CORRECTED: use the new receipt."),
            ],
            source=CAPABILITY.replace("TRUTH:cobalt", "TRUTH:amber"),
            module="capabilities",
        ).model_dump(mode="json")
        await worker.install(view.declaration.accept(plan_for("capability.strategy"), revised))
        second = await worker.run("Get evidence using the corrected procedure.")
        assert not second.errors, second.errors
        requests = [row["parameters"] for row in second.records if row["kind"] == "provider.request"]
        assert "PROCEDURE_CORRECTED" in str(requests[0]["messages"])
        assert "PROCEDURE_ORIGINAL" not in str(requests[0]["messages"])
        assert any(
            row.get("role") == "tool" and "TRUTH:amber" in str(row.get("content")) for row in requests[1]["messages"]
        )
        view = await worker.inspect()
        assert "obsolete" not in {row["name"] for row in view.facts["skills"]}
        assert view.facts["capability"]["sessions"]["curator:task"]["selections"] > before


@pytest.mark.asyncio
async def test_action_dispatch_requests_cross_memory_and_feedback_revision(baseline, tmp_path):
    baseline.task = Task(id="action-task", text="Verify before publishing and retain review notes.")
    for name in ("publish", "verify", "verify_secondary", "review_action"):
        baseline.config.permissions.tools[name] = "allow"
    actions = [
        response("publish", {}),
        response("review_action", {"request": {"note": "REVIEW_NOTE"}}),
        response("verify", {}),
        response("publish", {}),
        response("review_action", {"request": {"finish": True}}),
    ]
    resources = [{"kind": "tool", "name": name, "factory": f"action_logic:{name}"} for name in ("verify", "publish")]
    async with Worker(
        baseline,
        tmp_path / "worker",
        timeout=30,
        provider_factory=partial(replay_provider, responses=actions),
    ) as worker:
        proposed = {
            "values": {
                "memory.strategy": {
                    "factory": "context_memory:create",
                    "tool": {"name": "context_note", "description": "Retain a review note."},
                },
                "action.strategy": {
                    "factory": "action_logic:create",
                    "events": ["proposal", "outcome", "control"],
                    "dispatch": True,
                    "tool": {"name": "review_action", "description": "Review progress or request verified completion."},
                },
            },
            "files": {
                "context_memory.py": MEMORY,
                "action_logic.py": ACTION,
                "action_budget.json": json.dumps({"max_tool_iterations": 8}),
            },
        }
        prepared_resources = capability(resources)
        proposed["values"].update(prepared_resources.values)
        proposed["files"].update(prepared_resources.files)
        view = await worker.inspect()
        await worker.install(view.declaration.accept(plan_for(*proposed["values"]), proposed))
        first = await worker.run("Verify the publication and record the review note.")
        assert not first.errors, first.errors
        calls = [row["parameters"] for row in first.records if row["kind"] == "provider.request"]
        assert len(calls) == 5
        first_result = [row for row in calls[1]["messages"] if row.get("role") == "tool"][-1]
        assert "Action refused" in first_result["content"]
        assert "PUBLISHED_RECEIPT" not in first_result["content"]
        assert "Working notes: REVIEW_NOTE" in str(calls[2]["messages"])
        controls = [row["receipt"] for row in first.records if row["kind"] == "action.control"]
        assert any(row["control"] == "reject" and row["status"] == "applied" for row in controls)
        requested = next(row for row in controls if row["control"] == "finish" and row["status"] == "requested")
        assert any(row["control_id"] == requested["control_id"] and row["status"] == "applied" for row in controls)
        view = await worker.inspect()
        state = view.facts["action"]["sessions"]["curator:task"]
        assert state["verified"] and state["published_turn"] == first.turn_id
        assert view.facts["memory"]["shared"]["notes"] == ["REVIEW_NOTE"]
        worker.provider_factory = partial(
            replay_provider,
            responses=[
                response("publish", {}),
                response("verify_secondary", {}),
                response("publish", {}),
                response("review_action", {"request": {"finish": True}}),
            ],
        )
        revised = capability(
            [
                *resources,
                {"kind": "tool", "name": "verify_secondary", "factory": "action_logic:verify_secondary"},
            ]
        ).model_dump(mode="json")
        revised["values"]["action.strategy"] = proposed["values"]["action.strategy"]
        revised["files"]["action_logic.py"] = ACTION.replace("REQUIRE_SECONDARY = False", "REQUIRE_SECONDARY = True")
        await worker.install(view.declaration.accept(plan_for(*revised["values"]), revised))
        second = await worker.run("Apply the added secondary verification requirement.")
        assert not second.errors, second.errors
        calls = [row["parameters"] for row in second.records if row["kind"] == "provider.request"]
        assert len(calls) == 4
        assert "Action refused" in [row for row in calls[1]["messages"] if row.get("role") == "tool"][-1]["content"]
        assert "PUBLISHED_RECEIPT" in [row for row in calls[3]["messages"] if row.get("role") == "tool"][-1]["content"]
        view = await worker.inspect()
        state = view.facts["action"]["sessions"]["curator:task"]
        assert state["verified"] and state["secondary"] and state["published_turn"] == second.turn_id
        assert view.facts["memory"]["shared"]["notes"] == ["REVIEW_NOTE"]


@pytest.mark.asyncio
async def test_action_replaces_rejected_streamed_reply_before_it_becomes_visible(baseline, tmp_path):
    baseline.task = Task(text="Refuse an unverified delivery claim.")
    async with Worker(
        baseline,
        tmp_path / "worker",
        timeout=30,
        provider_factory=partial(replay_provider, responses=[LLMResponse(content="UNVERIFIED_DELIVERY")]),
    ) as worker:
        proposed = {
            "values": {"action.strategy": {"factory": "action_logic:create", "events": ["proposal", "control"]}},
            "files": {"action_logic.py": ACTION},
        }
        view = await worker.inspect()
        await worker.install(view.declaration.accept(plan_for("action.strategy"), proposed))
        result = await worker.run("Check the delivery claim.", stream=True)
        assert not result.errors, result.errors
        visible = [
            row["event"]
            for row in result.records
            if row["kind"] == "runner.event" and row["event_type"] in {"Text", "StreamDelta"}
        ]
        assert "UNVERIFIED_DELIVERY" not in str(visible)
        assert "Publication has not been verified." in str(visible)


@pytest.mark.asyncio
async def test_uploaded_skill_is_inspectable_before_curator_adoption_and_assets_are_readable(baseline, tmp_path):
    from experimental.curator.workflow import improve
    from tests.integration.test_harness_curator_planning_e2e import CuratorProvider
    from tests.test_harness_curator_generation import diagnosis, packet, selection

    baseline.task = Task(text="Adopt the supplied evidence package and read its procedure attachment.")
    baseline.file_roots = (baseline.workdir,)
    baseline.config.permissions.tools["read_file"] = "allow"
    source = tmp_path / "provided"
    (source / "references").mkdir(parents=True)
    (source / "SKILL.md").write_text(
        "---\nname: supplied\ndescription: Read provided evidence.\n---\nRead [detail](references/detail.txt).\n"
    )
    (source / "references/detail.txt").write_text("SUPPLIED_EVIDENCE: cobalt")
    (source / "references/data.bin").write_bytes(bytes(range(256)))
    async with Worker(baseline, tmp_path / "worker", provider_factory=replay_provider, timeout=30) as worker:
        staged = await worker.stage_skill_package(source)
        before = await worker.inspect()
        assert staged["root"] in {item["root"] for item in before.facts["skill_packages"]}
        assert "supplied" not in {item["name"] for item in before.facts["skills"]}
        proposed = capability(
            [
                {
                    "kind": "skill",
                    "name": "supplied",
                    "source": "Owner-provided evidence package",
                    "package": {"root": staged["root"], "digest": staged["digest"]},
                }
            ]
        ).model_dump(mode="json")
        curator = CuratorProvider(
            [
                response("submit_diagnosis", diagnosis()),
                response("submit_selection", selection("capability.strategy")),
                response("submit_plan", plan_for("capability.strategy").model_dump(mode="json")),
                response("submit_artifact", proposed),
            ]
        )
        generated = await improve(worker, curator)
        assert generated.validation.passed
        inspected = await worker.inspect()
        installed = next(row for row in inspected.facts["skills"] if row["name"] == "supplied")
        installed_dir = Path(installed["path"]).parent
        assert (installed_dir / "references/data.bin").read_bytes() == bytes(range(256))
        assert (installed_dir / "references/detail.txt").read_text() == "SUPPLIED_EVIDENCE: cobalt"
        material = packet({"messages": curator.requests[1]})
        assert "skill_packages" in str(material)
        worker.provider_factory = partial(
            replay_provider,
            responses=[
                response("read_file", {"path": str(installed_dir / "references/detail.txt")}),
                LLMResponse(content="The supplied evidence is cobalt."),
            ],
        )
        await worker.close()
        await worker.start()
        execution = await worker.run("Read the adopted package attachment.")
        assert not execution.errors, execution.errors
        requests = [row["parameters"] for row in execution.records if row["kind"] == "provider.request"]
        results = [row for request in requests for row in request["messages"] if row.get("role") == "tool"]
        assert any("SUPPLIED_EVIDENCE: cobalt" in str(row.get("content")) for row in results)
