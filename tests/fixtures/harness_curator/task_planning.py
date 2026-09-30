"""Example generated planning code with explicit task checkpoint ownership."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, JsonValue

from experimental.curator.harness.interaction import InteractionRequest
from experimental.curator.harness.planning import PlanningInitialization, PlanningProjection, PlanningResult
from experimental.curator.harness.strategies import PlanningStrategy
from experimental.curator.raven_adapter.planning.contracts import PlanningObservation

GUARD_COMPLETION = False


class View(BaseModel):
    items: dict[str, bool]
    guarded: bool


class Complete(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["complete"] = "complete"
    item: str


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["evidence"] = "evidence"
    item: str
    call_id: str
    succeeded: bool


type Change = Complete | Evidence


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["view", "complete"]
    item: str | None = None


class Planning(PlanningStrategy[View, Command | Evidence, View]):
    def __init__(self, state: dict[str, JsonValue]):
        self.state = state

    def _observe(self, view: View, observation: PlanningObservation) -> Command | Evidence | None:
        from .planning_bindings import observe

        return observe(view, observation)

    def _projection(self) -> PlanningProjection[View]:
        from .planning_bindings import context

        view = View(items=dict(self.state["items"]), guarded=GUARD_COMPLETION)
        return PlanningProjection[View](view=view, guidance=context(view))

    async def initialize(self, initial: PlanningInitialization) -> PlanningProjection[View]:
        if not self.state:
            self.state.update(items={initial.task: False}, seen=[], verified=[])
        return self._projection()

    async def interact(self, request: InteractionRequest[Command | Evidence]) -> PlanningResult[View, View]:
        change = request.command
        if isinstance(change, Command) and change.operation == "view":
            projection = self._projection()
            return PlanningResult[View, View](reply=projection.view, projection=projection)
        if change.item not in self.state["items"]:
            raise ValueError("unknown planning item")
        if isinstance(change, Command):
            if GUARD_COMPLETION and change.item not in self.state["verified"]:
                raise ValueError("completion requires verified execution evidence")
            self.state["items"][change.item] = True
        elif request.origin != "observation":
            raise ValueError("execution evidence requires host observation provenance")
        elif change.call_id not in self.state["seen"]:
            self.state["seen"].append(change.call_id)
            self.state["items"][change.item] = change.succeeded
            if change.succeeded:
                self.state["verified"].append(change.item)
        projection = self._projection()
        return PlanningResult[View, View](reply=projection.view, projection=projection)


def create(state: dict[str, JsonValue]) -> Planning:
    return Planning(state)
