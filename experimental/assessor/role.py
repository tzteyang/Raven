"""The Assessor protocol; `experimental.iteration.run` calls every assessor once per round."""

from typing import Protocol

from ..iteration.protocols import Sessions, Signal


class Assessor(Protocol):
    """Whoever holds a standard the worker never sees and measures a round's sessions against it.

    The standard (criteria, materials, references, held-out cases) is the assessor's own state; the loop sees only the
    `Signal`, whose `attachments` name whatever material the assessor hands over with it. None means nothing to say.
    """

    async def evaluate(self, sessions: Sessions) -> Signal | None: ...
