"""Action authoring entries for model behavior, judgments and execution control."""

from pathlib import Path

from raven.contracts.harness import ActionModule
from raven.contracts.participant import StepView

from ...harness.declaration import Target
from ...harness.prompts import Prompt
from ...harness.state import StateUse, Task
from ...harness.strategies import ActionStrategy
from ..action.contracts import TARGET, ActionBinding
from ..planning.contracts import PlanReader
from ..strategy import TaskBinding

CONTRACT = ActionModule


TARGETS = (
    Target(
        roles=("action",),
        name=TARGET,
        contract=ActionStrategy,
        binding=TARGET,
        payload=ActionBinding,
        phases=("input", "progress", "proposal", "outcome", "failure", "control"),
        channels=("model_decision", "tool_interaction", "execution_control"),
        effect="Prepare native generation/execution policies and handle typed host events and optional agent "
        "requests with one session owner. Use deterministic rules or one typed worker-model judgment through "
        "the optional infer dependency; author its judgment prompt, input selection, result type and control mapping. "
        "Declare mandatory per-call checks through dispatch; model requests use shared capability registration. "
        "Native consumers apply supported controls and report actual application separately from policy judgments.",
        state=(
            StateUse(
                resource="Action checkpoint",
                scope="session",
                access="Factory-injected mutable JSON mapping, one per session, owned by this strategy.",
                lifecycle="Copied for validation; successful calls persist; failed installation restores it.",
            ),
        ),
        knowledge=(
            Prompt,
            Path(__file__).resolve().parents[2] / "harness/reference/prompt-resources.md",
            ActionStrategy,
            ActionBinding,
            Path(__file__).resolve().parents[2] / "harness/action.py",
            Path(__file__).resolve().parents[2] / "harness/interaction.py",
            Path(__file__).resolve().parents[2] / "harness/peers.py",
            TaskBinding,
            Task,
            StepView,
            PlanReader,
            Path(__file__).resolve().parents[2] / "harness/reference/action.md",
            Path(__file__).resolve().parents[2] / "harness/reference/strategy-prompts.md",
            Path(__file__).resolve().parents[1] / "reference/action.md",
        ),
    ),
)
