"""Planning authoring entries for guidance and reusable procedural knowledge."""

from pathlib import Path

from experimental.curator.harness.declaration import Target
from experimental.curator.harness.interaction import InteractionRequest, InteractionTool
from experimental.curator.harness.planning import PlanningInitialization, PlanningProjection, PlanningResult
from experimental.curator.harness.state import StateUse
from experimental.curator.harness.strategies import PlanningStrategy
from experimental.curator.raven_adapter.planning.contracts import TARGET, PlanningBinding, PlanningObservation
from experimental.curator.raven_adapter.targets.knowledge import PROMPT, PROMPT_RESOURCES, STRATEGY_PROMPTS
from raven.contracts.harness import PlanningModule

CONTRACT = PlanningModule

TARGETS = (
    Target(
        roles=("planning",),
        name=TARGET,
        contract=PlanningStrategy,
        binding="planning.strategy",
        payload=PlanningBinding,
        channels=("model_input", "tool_interaction", "execution_control"),
        effect="Own session plans through initialize/interact and committed view/guidance projections; "
        "publish Agent tools through Capability and synchronize current input before capability selection. "
        "Support partial plans, queries, proposals, evidence and replanning with domain-defined commands. "
        "Prepare reusable native Playbooks through prepare. "
        "A root may organize existing child Harnesses and supply node requirements for their independent "
        "curation; requirements do not themselves invoke children. Session progress is checkpointed across "
        "turns and revisions. Task identity, available child baselines and execution grants remain host-owned.",
        state=(
            StateUse(
                resource="Planning checkpoint",
                scope="session",
                access="Factory-injected mutable JSON mapping, one per session; the strategy owns its meaning and mutations.",
                lifecycle="Copied for validation, saved after "
                "successful operations, restored on failed installation; factory migrations are explicit.",
            ),
        ),
        knowledge=(
            PlanningStrategy,
            PlanningInitialization,
            PlanningProjection,
            PlanningResult,
            InteractionRequest,
            InteractionTool,
            PlanningBinding,
            PlanningObservation,
            Path(__file__).resolve().parents[2] / "harness/reference/planning.md",
            Path(__file__).resolve().parents[1] / "reference/planning.md",
            Path(__file__).resolve().parents[1] / "reference/pitfalls/planning.md",
        ),
        references=(PROMPT, PROMPT_RESOURCES, STRATEGY_PROMPTS),
    ),
)
