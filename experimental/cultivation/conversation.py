"""A trial that is one conversation: a conversant speaks, the worker answers, until the conversant stops."""

from typing import Protocol
from uuid import uuid4

from experimental.harness.participation.compartment import Compartment
from experimental.harness.participation.hearing import opaque
from experimental.harness.participation.protocols import Exchange, Sessions
from experimental.harness.raven_adapter.worker import TurnTimeoutError


class Conversant(Protocol):
    """Whoever talks to the worker; None ends the conversation. One that has a `pause` is away that many seconds after
    each answer before it speaks again, and the worker's background work runs meanwhile (see `Worker.run`)."""

    name: str

    async def speak(self, exchanges: list[Exchange]) -> str | None: ...


class Conversation:
    def __init__(self, conversant: Conversant, *, max_turns: int = 6):
        if not isinstance(max_turns, int) or max_turns < 1:
            raise ValueError("a conversation needs a positive turn budget")
        self.conversant, self.max_turns = conversant, max_turns

    async def run(self, worker) -> Sessions:
        """Each run is a fresh worker session, so rounds do not continue one another's history; its key carries the
        conversant's opaque label, not its name, since the worker's records reach the Curator. A turn that ran
        past the worker's timeout, or that the worker ended without answering, ends the conversation with that turn
        kept as it got: the conversant had no answer, which is for the assessors to judge (`Exchange.stopped`).
        Only this conversation's actual user exchanges authorize speech in the partner compartment."""
        exchanges, session_key = [], f"curator:{opaque(self.conversant.name)}:{uuid4().hex}"
        away = {"away": pause} if (pause := getattr(self.conversant, "pause", 0)) else {}
        for _ in range(self.max_turns):
            text = await self.conversant.speak(exchanges)
            if text is None:
                break
            try:
                with Compartment("partner", spoken=[tuple([*(exchange.user for exchange in exchanges), text])]):
                    execution = await worker.run(text, session_key=session_key, **away)
            except TurnTimeoutError as exc:
                exchanges.append(Exchange(text, exc.execution))
                break
            exchanges.append(Exchange(text, execution))
            if exchanges[-1].stopped:
                break
        return {self.conversant.name: exchanges}
