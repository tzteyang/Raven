"""Complete shared observation knowledge from native definitions, without copying their schemas."""

from pathlib import Path

from raven.contracts.llm_provider import (
    CallRecord,
    ErrorClassification,
    LLMResponse,
    RunMeta,
    ToolCallRequest,
    TruncationInfo,
)
from raven.contracts.participant import StepView
from raven.contracts.tool import Tool
from raven.providers.tool_calls import openai_tool_call

from ...harness.declaration import Reference
from ...harness.prompts import Prompt
from ...harness.state import Task
from ..observe import plain
from ..planning.contracts import PlanningObservation, PlanReader
from ..strategy import TaskBinding

_HARNESS = Path(__file__).resolve().parents[2] / "harness"
_PROMPTING = "read when the design adds or changes a model-facing prompt"
PROMPT = Reference(Prompt, f"The Prompt type an authored prompt resource uses, with its one input model; {_PROMPTING}.")
PROMPT_RESOURCES = Reference(
    _HARNESS / "reference/prompt-resources.md",
    f"How to author a Prompt resource: input model, template and registration; {_PROMPTING}.",
)
STRATEGY_PROMPTS = Reference(
    _HARNESS / "reference/strategy-prompts.md",
    "What each strategy's runtime prompts carry and how they are organised; read when the design changes what the "
    "worker model is told.",
)
INTERACTION = Reference(
    _HARNESS / "interaction.py",
    "Shared interaction identities, typed envelopes and model-facing declarations; read when the strategy publishes "
    "or handles commands from the model.",
)
PEERS = Reference(
    _HARNESS / "peers.py",
    "Narrow cross-strategy operations resolved in the current host scope; read when one strategy needs another's "
    "state or result.",
)
RESOURCES = Reference(
    _HARNESS / "resources.py",
    "Serializable capability contributions and their candidate/active lifetimes; read when the strategy contributes "
    "tools, skills or files through capability.",
)
STEP_VIEW = Reference(
    StepView, "What a participant sees of the turn when asked; read when a decision depends on the turn's state."
)
PLAN_READER = Reference(
    PlanReader,
    "Read-only access to the session's latest committed plan; read when a strategy other than planning consults it.",
)
TASK = Reference(Task, "Host-owned task identity and initial goal; read when the factory binds task identity.")
TASK_BINDING = Reference(
    TaskBinding,
    "A generated owner constructed with explicit task identity and owned state; read when the factory needs it.",
)
TOOL = Reference(
    Tool, "Raven's tool base class; read when the design authors an executable tool rather than exposing one."
)

_REFERENCE = Reference(
    Path(__file__).resolve().parents[1] / "reference/observations.md",
    "What the opaque fields of step views, planning observations and model responses mean at runtime; read when "
    "the design inspects call records, tool calls or model output.",
)
_PLAIN = Reference(
    plain,
    "How observed values are flattened to JSON before they reach a strategy; read when a planning observation's "
    "shape is in question.",
)
_DEPENDENCIES = {
    StepView: (LLMResponse, openai_tool_call, _REFERENCE),
    PlanningObservation: (LLMResponse, _PLAIN, openai_tool_call, _REFERENCE),
    LLMResponse: (ToolCallRequest, ErrorClassification, CallRecord),
    ToolCallRequest: (RunMeta,),
    RunMeta: (TruncationInfo,),
}


def complete(knowledge, references):
    """The references plus the known runtime meaning of opaque fields in any of the items, as further references.

    A nested type or document an inlined or listed item depends on is listed once, after the declared references,
    unless the target already carries it."""
    found = {}

    def include(item):
        key = item.item if isinstance(item, Reference) else item
        if key in found:
            return
        found[key] = item
        for dependency in _DEPENDENCIES.get(key, ()):
            include(dependency)

    for item in (*knowledge, *references):
        include(item)
    listed = {reference.item for reference in references}
    return (
        *references,
        *(
            item if isinstance(item, Reference) else Reference(item)
            for key, item in found.items()
            if key not in knowledge and key not in listed
        ),
    )
