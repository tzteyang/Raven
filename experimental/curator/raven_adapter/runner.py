"""One scoped execution boundary for workers, validation probes and ACP hosting."""

from dataclasses import replace
from uuid import uuid4

from raven.spine.events import Text
from raven.spine.scheduler import conversation_id

from .strategy import SESSION


async def run_turn(bound, request, emit, drain, *, stream=False, usage_sink=None, text_sink=None):
    """Delegate native execution with task-local identity and completed control observation."""
    if request.turn_id is None:
        request = replace(request, turn_id=uuid4().hex)
    token = SESSION.set(conversation_id(request))
    previous = bound.recorder.turn_id
    bound.recorder.turn_id = request.turn_id
    emitted = []
    completed = False

    async def observed(event):
        bound.recorder.add("runner.event", event_type=type(event).__name__, event=event)
        await emit(event)
        if isinstance(event, Text):
            emitted.append(event.content)

    try:
        if bound.planning is not None:
            await bound.planning.prepare()
        outcome = await bound.runtime.loop.run_turn(
            request, observed, drain, stream=stream, usage_sink=usage_sink, text_sink=text_sink
        )
        completed = True
        return outcome
    finally:
        try:
            action = bound.strategies.get("action")
            if action is not None:
                await action.finish(emitted_reply="".join(emitted) if completed else None)
            bound.observer.finish()
            if bound.inference is not None:
                bound.inference.release(request.turn_id)
        finally:
            bound.recorder.turn_id = previous
            SESSION.reset(token)


class ScopedLoop:
    """Mount the same native loop in RPC while routing run_turn through the shared boundary."""

    __slots__ = ("_bound",)

    def __init__(self, bound):
        object.__setattr__(self, "_bound", bound)

    def __getattr__(self, name):
        return getattr(self._bound.runtime.loop, name)

    def __setattr__(self, name, value):
        setattr(self._bound.runtime.loop, name, value)

    async def run_turn(self, request, emit, drain, *, stream=False, usage_sink=None, text_sink=None):
        return await run_turn(
            self._bound, request, emit, drain, stream=stream, usage_sink=usage_sink, text_sink=text_sink
        )
