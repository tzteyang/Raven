"""The Analyst role: read a round's signals against its sessions and records, and answer with a `Review`.

The base class hands the signals to `experimental.analyst.run.analyse`, which reads them against the sessions and the
execution records and writes the feedback: a decision and requirements stated in observable terms. A subclass may
review a round another way, as long as it answers with a `Review`.
"""

from dataclasses import dataclass, field

from .activity import activity
from .feedback import Feedback
from .run import Limits, analyse


@dataclass(frozen=True)
class Review:
    """What the Analyst made of a round: its feedback, and what the mechanisms did."""

    feedback: Feedback
    activity: tuple[dict, ...] = field(default=())


class Analyst:
    """Reads a round and answers with a `Review`; only a `curate` decision, or material handed over with a signal,
    reaches the Curator.

    `activity` (see `experimental.analyst.activity`) is attached to every review, counted from the records, so the
    Curator can check its own revision against what its mechanisms actually did.
    """

    def __init__(self, provider=None, *, model=None, limits=Limits(), sealed=None):
        self.provider, self.model, self.limits, self.sealed = provider, model, limits, sealed

    async def review(
        self, worker, sessions, signals, *, previous_signals=(), previous_feedback=None, history=(), spoken=None
    ) -> Review:
        """`spoken` are the conversants' words the Curator's compartment will spare (see `experimental.analyst.run.vet`)."""
        feedback = await analyse(
            worker,
            self.provider,
            signals,
            sessions,
            previous_signals=previous_signals,
            previous_feedback=previous_feedback,
            history=history,
            model=self.model,
            limits=self.limits,
            sealed=self.sealed,
            spoken=spoken,
        )
        return Review(feedback, tuple(activity(sessions)))
