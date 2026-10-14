"""One scoped execution boundary for workers, validation probes and ACP hosting."""

from dataclasses import replace
from uuid import uuid4

from raven.spine.events import Text
from raven.spine.scheduler import conversation_id

from ...iteration.compartment import Compartment
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
    scope = None

    async def observed(event):
        bound.recorder.add("runner.event", event_type=type(event).__name__, event=event)
        await emit(event)
        if isinstance(event, Text):
            emitted.append(event.content)

    try:
        ledger = getattr(bound, "disclosures", None)
        spoken = ledger.receive(request) if ledger is not None else ()
        scope = Compartment("partner", spoken=[spoken])
        scope.__enter__()

        def disclosed_drain():
            incoming = drain()
            for injected in incoming:
                if conversation_id(injected) != conversation_id(request):
                    raise ValueError("an injected disclosure belongs to another conversation")
                scope.spoken = (ledger.receive(injected),)
            return incoming

        if bound.planning is not None:
            await bound.planning.prepare()
        if bound.inference is not None:
            bound.inference.observe_window(bound.runtime.loop.context_window_tokens)
        outcome = await bound.runtime.loop.run_turn(
            request,
            observed,
            disclosed_drain if ledger is not None and drain is not None else drain,
            stream=stream,
            usage_sink=usage_sink,
            text_sink=text_sink,
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
            if scope is not None:
                scope.__exit__(None, None, None)
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
