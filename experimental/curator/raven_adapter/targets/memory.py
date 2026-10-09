"""Memory authoring entries for model inputs, context assembly and retained records."""

from pathlib import Path

from raven.contracts.harness import MemoryModule

from ...harness.context import CompactionRequest, ContextRequest, ContextSource, ContextView, InitialContext
from ...harness.declaration import Target
from ...harness.interaction import InteractionRequest, InteractionScope, InteractionTool
from ...harness.state import StateUse
from ...harness.strategies import MemoryStrategy
from ..memory.contracts import TARGET, MemoryBinding
from .knowledge import (
    PEERS,
    PLAN_READER,
    PROMPT,
    PROMPT_RESOURCES,
    RESOURCES,
    STEP_VIEW,
    STRATEGY_PROMPTS,
    TASK,
    TASK_BINDING,
)

CONTRACT = MemoryModule


TARGETS = (
    Target(
        roles=("memory",),
        name=TARGET,
        contract=MemoryStrategy,
        binding=TARGET,
        payload=MemoryBinding,
        channels=("model_input", "tool_interaction", "execution_control"),
        effect="Own native profile, context/storage setup through prepare, then initialize session context, "
        "interact with information and compose each model input after capability normalization. "
        "Supporting assets need an explicit consumer; session progress survives revisions.",
        state=(
            StateUse(
                resource="Memory checkpoint",
                scope="session",
                access="Factory-injected session JSON mapping and an optional explicit shared task knowledge mapping.",
                lifecycle="Copied for validation; successful calls persist; failed installation restores it.",
            ),
        ),
        knowledge=(
            MemoryStrategy,
            Path(__file__).resolve().parents[2] / "harness/context.py",
            InitialContext,
            ContextSource,
            CompactionRequest,
            InteractionScope,
            InteractionRequest,
            InteractionTool,
            ContextRequest,
            ContextView,
            MemoryBinding,
            Path(__file__).resolve().parents[1] / "memory/contracts.py",
            Path(__file__).resolve().parents[2] / "harness/reference/memory.md",
            Path(__file__).resolve().parents[1] / "reference/memory.md",
        ),
        references=(
            PROMPT,
            PROMPT_RESOURCES,
            RESOURCES,
            PEERS,
            TASK_BINDING,
            PLAN_READER,
            TASK,
            STEP_VIEW,
            STRATEGY_PROMPTS,
        ),
    ),
)
