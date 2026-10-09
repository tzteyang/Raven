"""Raven-supported targets and factory references for the shared declaration."""

from dataclasses import replace
from typing import Annotated

from pydantic import Field, RootModel

from raven.plugins.manifest import _FACTORY_REF_RE

from ...harness.declaration import Reference
from ...harness.state import StateUse


class EntryPoint(RootModel[Annotated[str, Field(pattern=_FACTORY_REF_RE)]]):
    """A supplied or generated module:symbol reference; each binding checks the loaded kind.

    A strategy binding names a synchronous factory returning its explicit public
    strategy implementation. Supporting objects follow their owning code's contracts.
    """


PARTICIPANT_STATE = StateUse(
    resource="AgentParticipant instance",
    scope="turn",
    access="Own instance attributes; StepView is a read-only observation.",
    lifecycle="ParticipantHook creates one instance per turn; its attributes do not survive the turn.",
)

PLUGIN_STATE = StateUse(
    resource="Plugin instance and granted services",
    scope="generation",
    access="PluginContext and explicitly granted RuntimeHandles; no mutation of host assembly.",
    lifecycle="Constructed with the runtime generation; the host starts and releases applicable resources.",
)


def catalogue():
    """Return candidates; actual reachability and the manual determine grants."""
    from pathlib import Path

    from ...harness.inference import InferenceError, StrategyInference
    from ...harness.preparation import PreparationRequest, StrategyPreparation
    from ..preparation import ActionHost, CapabilityHost, MemoryHost, PlanningHost, StrategyHost
    from . import action, capability, memory, planning
    from .knowledge import complete

    targets = (*memory.TARGETS, *planning.TARGETS, *capability.TARGETS, *action.TARGETS)
    hosts = {"memory": MemoryHost, "planning": PlanningHost, "capability": CapabilityHost, "action": ActionHost}
    pitfalls = Path(__file__).resolve().parents[1] / "reference/pitfalls/artifact.md"
    preparation = (
        "How a candidate prepares its profile, resources, native policies and playbooks before a session, and how "
        "candidate and session lifetimes stay apart; read when the design implements prepare or changes native "
        "assembly."
    )
    inference = (
        "The optional single-step infer dependency: its trigger, authored prompt, typed result, evidence and failure "
        "behaviour; read when the design needs a model judgement at runtime instead of a rule."
    )
    common = (
        Reference(Path(__file__).resolve().parents[1] / "reference/preparation.md", preparation),
        Reference(PreparationRequest, preparation),
        Reference(StrategyPreparation, preparation),
        Reference(StrategyHost, preparation),
        Reference(Path(__file__).resolve().parents[2] / "harness/reference/inference.md", inference),
        Reference(StrategyInference, inference),
        Reference(InferenceError, inference),
    )
    return tuple(
        replace(
            target,
            knowledge=(*target.knowledge, hosts[target.roles[0]], pitfalls),
            references=complete((*target.knowledge, hosts[target.roles[0]], pitfalls), (*target.references, *common)),
        )
        for target in targets
    )
