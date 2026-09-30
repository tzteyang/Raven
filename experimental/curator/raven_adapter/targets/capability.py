"""Capability authoring entries for tool exposure, implementations and resources."""

from pathlib import Path

from raven.agent.tools.registry import admit_tool
from raven.contracts.harness import CapabilityModule
from raven.contracts.participant import StepView
from raven.contracts.tool import Tool

from ...harness.declaration import Target
from ...harness.prompts import Prompt
from ...harness.state import StateUse, Task
from ...harness.strategies import CapabilityStrategy
from ..capability.contracts import TARGET, CapabilityBinding
from ..planning.contracts import PlanReader
from ..strategy import TaskBinding

CONTRACT = CapabilityModule

TARGETS = (
    Target(
        roles=("capability",),
        name=TARGET,
        contract=CapabilityStrategy,
        binding=TARGET,
        payload=CapabilityBinding,
        channels=("model_input", "tool_interaction"),
        effect="Prepare and register complete supplied or authored Skills and tool implementations; configure "
        "supported native capability policies, MCP connections and existing plugins through host services. "
        "Select actual active tools and Skill delivery per session. Registration is not activation, "
        "dependency readiness or permission, and does not create arbitrary child Harness baselines.",
        state=(
            StateUse(
                resource="Capability checkpoint",
                scope="session",
                access="Factory-injected mutable JSON mapping, one per session, owned by this strategy.",
                lifecycle="Copied for validation; successful calls persist; failed installation restores it.",
            ),
        ),
        knowledge=(
            Prompt,
            Path(__file__).resolve().parents[2] / "harness/reference/prompt-resources.md",
            CapabilityStrategy,
            CapabilityBinding,
            TaskBinding,
            PlanReader,
            Task,
            StepView,
            Path(__file__).resolve().parents[2] / "harness/resources.py",
            Path(__file__).resolve().parents[2] / "harness/interaction.py",
            Path(__file__).resolve().parents[2] / "harness/peers.py",
            Tool,
            admit_tool,
            Path(__file__).resolve().parents[2] / "harness/reference/capability.md",
            Path(__file__).resolve().parents[2] / "harness/reference/strategy-prompts.md",
            Path(__file__).resolve().parents[1] / "reference/capability.md",
        ),
    ),
)
