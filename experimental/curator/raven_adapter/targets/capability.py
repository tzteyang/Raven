"""Capability authoring entries for tool exposure, implementations and resources."""

from pathlib import Path

from experimental.curator.harness.declaration import Target
from experimental.curator.harness.state import StateUse
from experimental.curator.harness.strategies import CapabilityStrategy
from experimental.curator.raven_adapter.capability.contracts import TARGET, CapabilityBinding
from experimental.curator.raven_adapter.strategy import TaskBinding
from experimental.curator.raven_adapter.targets.knowledge import (
    INTERACTION,
    PEERS,
    PLAN_READER,
    PROMPT,
    PROMPT_RESOURCES,
    STEP_VIEW,
    STRATEGY_PROMPTS,
    TASK,
    TOOL,
)
from raven.agent.tools.registry import admit_tool
from raven.contracts.harness import CapabilityModule

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
            CapabilityStrategy,
            CapabilityBinding,
            TaskBinding,
            Path(__file__).resolve().parents[2] / "harness/resources.py",
            admit_tool,
            Path(__file__).resolve().parents[2] / "harness/reference/capability.md",
            Path(__file__).resolve().parents[1] / "reference/capability.md",
        ),
        references=(
            PROMPT,
            PROMPT_RESOURCES,
            PLAN_READER,
            TASK,
            STEP_VIEW,
            INTERACTION,
            PEERS,
            TOOL,
            STRATEGY_PROMPTS,
        ),
    ),
)
