"""Typed single-step model inference supplied to generated strategy operations."""

from collections.abc import Sequence
from typing import Literal, NamedTuple, Protocol

from pydantic import BaseModel, JsonValue


class InferenceError(RuntimeError):
    """No usable judgment; callers may explicitly degrade optional guidance only.

    This is not a negative domain verdict. Required execution checks must keep
    the failure visible. Cancellation propagates separately to the host.
    """

    def __init__(self, kind: Literal["scope", "budget", "timeout", "provider", "result"], message: str):
        self.kind = kind
        super().__init__(message)


class InferenceRequest(NamedTuple):
    """One judgment of a batch: its instruction and the data it judges."""

    instruction: str
    data: JsonValue


class StrategyInference(Protocol):
    """Runtime judgments by the worker's own model, without tools, delegated work or a model repair loop.

    Curator authors the instruction, input selection, result model and consumer.
    The host supplies the worker model, operation identity and budgets. A root
    strategy operation and its sequential peer calls share one allowance of
    calls and time; every call, failed or not, spends from it and from the
    turn's allowance of calls and input. Only active-turn operations may invoke
    it. Factories, preparation, background tasks and escaped callbacks cannot.

    output_type is a concrete BaseModel with extra='forbid'. The host supplies
    its JSON schema and validates the returned JSON strictly. The result is
    domain data, not execution permission. Strategies map it to their existing
    public results; Action still obeys allowed_controls and can_guide.

    The strategy chooses the call's max_output_tokens and reasoning_effort;
    omitted, each follows the worker's own generation settings. Neither may
    exceed what the worker itself runs with, so a judgment is never made by a
    stronger configuration than the work it judges. A reasoning model spends its
    reasoning from the same output allowance. The host reports the accepted
    values and limits.
    """

    async def __call__[ResultT: BaseModel](
        self,
        *,
        instruction: str,
        data: JsonValue,
        output_type: type[ResultT],
        max_output_tokens: int | None = None,
        reasoning_effort: str | None = None,
    ) -> ResultT: ...

    async def each[ResultT: BaseModel](
        self,
        requests: Sequence[InferenceRequest],
        *,
        output_type: type[ResultT],
        max_output_tokens: int | None = None,
        reasoning_effort: str | None = None,
    ) -> list[ResultT | InferenceError]:
        """Several judgments of one operation at once, in order: each item is its result or the InferenceError
        that kept it from one, so one failure does not hide the others. The whole batch is admitted against the
        allowances before any call starts, or refused as a whole."""
        ...
