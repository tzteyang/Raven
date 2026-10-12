"""The customer: a model plays one persona, reads the conversation so far, then says the next thing or leaves.

In a cultivation round each persona is one of the counterpart's drill cards, played as the customer it describes; the
module keeps its first scenario's name, a travel agency's conversant. A card is anything with a `name` whose `play`
draws one playing of it with the persona's `text` (see `experimental.simulation.bench.scenario.Persona`).
"""

import asyncio
import random
import re
from contextlib import nullcontext
from pathlib import Path
from typing import Protocol

from experimental.harness.participation.allowance import excerpt, reading_budget
from experimental.harness.participation.channel import said
from experimental.harness.participation.exchange import ExchangeError, messages
from experimental.harness.participation.files import read_delivered
from experimental.harness.participation.views import opened, transcript

LEAVE = "LEAVE"
TRAILING = re.compile(r"\s+\W*LEAVE\W*$")
# A line that opens a speaker's turn with a role label, as a model writing the whole dialogue marks each side.
TURN = re.compile(r"^\W*(?:user|assistant|customer|human|system)\W{0,2}[:\uff1a][\s*_]*", re.IGNORECASE)
_PROMPT = Path(__file__).resolve().parent / "prompts" / "conversant.md"


class Card(Protocol):
    name: str

    def play(self, rng: random.Random): ...


def own_turn(text: str) -> str:
    """The speaker's own message out of a reply: a role-playing model sometimes goes on to write the dialogue, both
    sides of it, under role labels; everything from the first labelled line after the message is dropped, and a label
    in front of the message itself is taken off."""
    lines = (text or "").strip().splitlines()
    if lines and TURN.match(lines[0]):
        lines[0] = TURN.sub("", lines[0], count=1)
    cut = next((at for at, line in enumerate(lines) if at and TURN.match(line)), len(lines))
    return "\n".join(lines[:cut]).strip()


def parting(text: str) -> tuple[str | None, bool]:
    """(message, leaving): the word LEAVE on a line of its own, or closing the last line, marks leaving and is never
    sent; what else was written is the parting message, or None when nothing was."""
    lines = (text or "").strip().splitlines()
    kept = [line for line in lines if line.strip(" .!*_\"'").upper() != LEAVE]
    closing = bool(kept) and bool(TRAILING.search(kept[-1]))
    if closing:
        kept[-1] = TRAILING.sub("", kept[-1])
    message = "\n".join(kept).strip() or None
    return message, closing or len(kept) < len(lines) or message is None


async def say(provider, prompt: Path, packet, *, label: str, model=None, effort=None, timeout=120) -> str:
    """One plain-text reply from a role-playing model, as written (see `parting` for how it says it is done).

    `effort` is the reasoning effort of this call; without one the provider's own setting applies.
    """
    extra = {"reasoning_effort": effort} if effort else {}
    try:
        async with asyncio.timeout(timeout):
            response = await provider.chat_with_retry(
                messages=messages(prompt.read_text(), packet), model=model, **extra
            )
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        raise ExchangeError(f"{label}: model call failed: {exc!r}") from exc
    if response.finish_reason == "error":
        raise ExchangeError(f"{label}: provider error: {response.content}")
    return (response.content or "").strip()


class Conversant:
    """Speaks in plain text, the way a person types into a chat; the word LEAVE on a line of its own ends the
    conversation, after anything else written with it has been sent as a parting message.

    Each conversation plays the card afresh: its values are drawn from `seed`, the conversant's name and how many
    conversations it has had, so every round meets new dates, party, budget and phone, and two runs with one seed
    meet the same ones. `card` is the playing of the current conversation.

    With `boundaries`, every call is made in the conversant's compartment: what the partner sent, its replies and
    the files it delivered, is the partner's to say, so only the rest of the request is held to the seal.
    """

    def __init__(
        self, persona: Card, provider, *, name=None, model=None, effort=None, timeout=120, seed=0, boundaries=None
    ):
        self.persona, self.provider, self.model, self.timeout = persona, provider, model, timeout
        self.effort, self.seed, self.played, self.card = effort, seed, 0, None
        self.leaving = False
        self.name = name or persona.name
        self.boundaries = boundaries

    @property
    def pause(self) -> float:
        """Seconds the person is away after each answer: a card whose `values` set `wait_seconds` plays someone who
        comes back after a while, as a requester checking on work in progress does. The conversation spends them on
        the worker's background work (see `experimental.cultivation.conversation.Conversant`)."""
        value = (getattr(self.persona, "values", None) or {}).get("wait_seconds", 0)
        return float(value) if isinstance(value, (int, float)) else 0.0

    @property
    def handed(self) -> tuple[Path, ...]:
        """The files this person hands over as the conversation opens (the card's `files`); the person knows them."""
        return tuple(getattr(self.persona, "files", ()) or ())

    @property
    def reading(self) -> int:
        """Tokens one opened file may take in what the person reads: a share of the model's window."""
        default = getattr(self.provider, "get_default_model", None)
        return reading_budget(self.model or (default() if default else None))

    async def speak(self, exchanges) -> str | None:
        if not exchanges or self.card is None:
            self.card = self.persona.play(random.Random(f"{self.seed}:{self.name}:{self.played}"))
            self.played += 1
            self.leaving = False
        if self.leaving:
            return None
        packet = {
            "persona": self.card.text,
            **(
                {"handed": {path.name: excerpt(read_delivered(path), self.reading) for path in self.handed}}
                if self.handed
                else {}
            ),
            "conversation": transcript(exchanges),
            "opened": opened(exchanges, tokens=self.reading),
        }
        partner = [tuple(said(exchange) for exchange in exchanges), *packet["opened"].values()]
        scope = nullcontext() if self.boundaries is None else self.boundaries.compartment("conversant", spoken=partner)
        with scope as entered:
            text = await say(
                self.provider if entered is None else entered.provider(self.provider),
                _PROMPT,
                packet,
                label=f"conversant:{self.name}",
                model=self.model,
                effort=self.effort,
                timeout=self.timeout,
            )
        message, self.leaving = parting(own_turn(text))
        return message
