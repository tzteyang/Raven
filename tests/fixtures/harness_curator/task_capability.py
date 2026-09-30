"""Capability policy delegates candidate registration and selects actual evidence resources."""

from experimental.curator.harness.preparation import PreparationRequest
from experimental.curator.harness.resources import (
    CapabilityContribution,
    CapabilitySelection,
    RegistrationReceipt,
    SelectionRequest,
    SkillContribution,
    SkillSelection,
    ToolContribution,
)
from experimental.curator.harness.strategies import CapabilityStrategy
from raven.contracts.tool import Tool


class Probe(Tool):
    name = "evidence_probe"
    description = "Obtain the task's local evidence."
    parameters = {"type": "object", "properties": {}, "additionalProperties": False}

    async def execute(self, **kwargs):
        return "FACT:cobalt"


def probe():
    return Probe()


class Capability(CapabilityStrategy):
    def __init__(self, state, registrar):
        self.state, self.registrar = state, registrar

    def _prepare_tools(self, request: PreparationRequest) -> tuple[ToolContribution, ...]:
        return (ToolContribution(name="evidence_probe", factory="task_capability:probe"),)

    def _prepare_skills(self, request: PreparationRequest) -> tuple[SkillContribution, ...]:
        return (
            SkillContribution(
                name="evidence",
                source="Task evidence procedure",
                files={
                    "SKILL.md": "---\nname: evidence\ndescription: Read execution evidence\n---\n"
                    "CAPABILITY_SKILL_RUNTIME: call evidence_probe before making factual claims.",
                },
            ),
        )

    def register(self, contribution: CapabilityContribution) -> RegistrationReceipt:
        return self.registrar.register(contribution)

    async def select(self, request: SelectionRequest) -> CapabilitySelection:
        self.state["selections"] = self.state.get("selections", 0) + 1
        names = [
            row["function"]["name"]
            for row in request.tools
            if row["function"]["name"] in {"evidence_probe", "curator_planning"}
        ]
        return CapabilitySelection(
            tools=tuple(names),
            skills=(SkillSelection(name="evidence"),),
            guidance="CAPABILITY_USAGE:" + ",".join(names),
        )


def create(state, task, *, registrar):
    return Capability(state, registrar)
