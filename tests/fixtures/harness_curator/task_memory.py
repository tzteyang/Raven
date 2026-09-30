"""Task-shared evidence and session context expressed through the public Memory operations."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

from experimental.curator.harness.context import ContextRequest, ContextView, InitialContext
from experimental.curator.harness.interaction import InteractionRequest
from experimental.curator.harness.strategies import MemoryStrategy
from experimental.curator.raven_adapter.memory.contracts import MemoryObservation


class Query(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["query"] = "query"
    text: str = ""


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["evidence"] = "evidence"
    call_id: str
    value: str


class Context(BaseModel):
    model_config = ConfigDict(extra="forbid")
    facts: list[str]


class Receipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stored: bool


class Layout(BaseModel):
    prefix: str


class Memory(MemoryStrategy[Layout, Query | Evidence, Context | Receipt]):
    def __init__(self, state, shared):
        self.state, self.shared = state, shared

    def _observe(self, observation: MemoryObservation) -> Query | Evidence | None:
        from .strategy_bindings import observe

        return observe(observation)

    async def initialize(self, initial: InitialContext) -> Layout:
        self.shared.setdefault("facts", {})
        return Layout(prefix="MEMORY_CONTEXT:")

    async def interact(self, request: InteractionRequest[Query | Evidence]) -> Context | Receipt:
        command = request.command
        if isinstance(command, Query):
            return Context(
                facts=[value for value in self.shared["facts"].values() if not command.text or command.text in value]
            )
        if self.shared["facts"].get(command.call_id) == command.value:
            return Receipt(stored=False)
        self.shared["facts"][command.call_id] = command.value
        return Receipt(stored=True)

    async def compose(self, request: ContextRequest) -> ContextView:
        content = request.initialization["prefix"] + ",".join(self.shared["facts"].values())
        return ContextView(
            messages=[request.messages[0], {"role": "system", "content": content}, *request.messages[1:]]
        )


def create(state, task, *, shared):
    return Memory(state, shared)
