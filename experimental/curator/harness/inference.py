"""Typed single-step model inference supplied to generated strategy operations."""

from typing import Literal, Protocol

from pydantic import BaseModel, JsonValue


class InferenceError(RuntimeError):
    """No usable judgment; callers may explicitly degrade optional guidance only.

    This is not a negative domain verdict. Required execution checks must keep
    the failure visible. Cancellation propagates separately to the host.
    """

    def __init__(self, kind: Literal["scope", "budget", "timeout", "provider", "result"], message: str):
        self.kind = kind
        super().__init__(message)


class StrategyInference(Protocol):
    """One runtime judgment, without tools, delegated work or a model repair loop.

    Curator authors the instruction, input selection, result model and consumer.
    The host supplies the worker model, operation identity and budgets. A root
    strategy operation and its sequential peer calls share one attempt, which
    remains spent after failure. Only active-turn operations may invoke it.
    Factories, preparation, background tasks and escaped callbacks cannot.

    output_type is a concrete BaseModel with extra='forbid'. The host supplies
    its JSON schema and validates the returned JSON strictly. The result is
    domain data, not execution permission. Strategies map it to their existing
    public results; Action still obeys allowed_controls and can_guide.
    """

    async def __call__[ResultT: BaseModel](
        self, *, instruction: str, data: JsonValue, output_type: type[ResultT]
    ) -> ResultT: ...
