"""The worker's own review of its round: a self-assessment beside what the counterpart and the standard measured.

After the drills, the worker is shown, on a replica of itself, each conversation it had, the files it handed over, and,
when the replica each session played on is known, the files the requester handed in during it and what the worker filed
in its workdir and home beside its replies; it is asked to judge its final reply and its deliverables against the task it holds and the norms it was given: whether
they meet them, and the concrete defects it finds. The verdicts are the worker's own, made with the Harness as it
stands, so they improve or fail with it. The Analyst reads them beside the external verdicts: what the worker passed
but the counterpart faulted is a blind spot of its own review, and what it faulted but still delivered shows it does not act
on its own review. Its words reach the Curator the way any signal's text does, under the sessions' opaque labels; the
per-session verdicts stay with the Analyst (`Item`).

The review is played on a replica made by `spawn` and closed afterwards, so nothing of it enters the worker's state,
the same way held-out drills are played. That replica is fresh, so the session's own replica is read for what it held
beyond the worker's baseline: only that difference travels, never the baseline itself or anything the session never saw.
"""

import asyncio
import json
import re
from pathlib import Path
from uuid import uuid4

from experimental.harness.participation.compartment import Compartment
from experimental.harness.participation.hearing import opaque
from experimental.harness.participation.protocols import Item, Signal
from experimental.harness.participation.views import PRIVATE, handed, opened, transcript, written
from experimental.harness.raven_adapter.materialize import _write
from experimental.harness.raven_adapter.observe import plain

SOURCE = "self"
VERDICT = re.compile(r"^\s*VERDICT\s*:\s*(pass|fail|unknown)\b", re.I | re.M)
DEFECTS = re.compile(r"^\s*DEFECTS\s*:\s*(.*?)(?=^\s*NOTE\s*:|\Z)", re.I | re.M | re.S)
NOTE = re.compile(r"^\s*NOTE\s*:\s*(.*)\Z", re.I | re.M | re.S)
_PROMPT = Path(__file__).resolve().parent / "prompts" / "introspect.md"


def request(exchanges, *, attachments=None, filed=None, tokens: int | None = None) -> str:
    """What the worker is asked: the prompt with the conversation it had and the files it handed over, each cut to
    `tokens` (`experimental.harness.participation.allowance.reading_budget` by default). `attachments` are the files
    the requester handed in during the session and `filed` what the worker filed there for colleagues, each keyed by
    its place (see `Introspection.evidence`); either is left out of the packet when None."""
    packet = {"conversation": transcript(exchanges, speaker="user"), "delivered": opened(exchanges, tokens=tokens)}
    if attachments is not None:
        packet["attachments"] = attachments
    if filed is not None:
        packet["filed"] = filed
    return _PROMPT.read_text() + "\n\n" + json.dumps(packet, ensure_ascii=False, indent=2)


def parse(text: str) -> dict:
    """The worker's review as a verdict, its defects and its note; a reply without a verdict is `unknown`."""
    verdict = VERDICT.search(text or "")
    defects = DEFECTS.search(text or "")
    note = NOTE.search(text or "")
    return {
        "result": verdict.group(1).lower() if verdict else "unknown",
        "defects": defects.group(1).strip() if defects else "",
        "note": note.group(1).strip() if note else ("" if verdict else (text or "").strip()),
    }


class Introspection:
    """`evaluate` asks the worker, on a fresh replica per session, to review its own work in that session.

    `employee` is the worker the replicas are made from and `spawn(employee, label)` makes one (see
    `experimental.cultivation.employee.replicate`); at most `concurrency` reviews run at once. With `records`, each
    round's reviews are written to its `analysis` folder beside the owner's scorecard, where the record reader finds
    them. The signal does not judge the round (`satisfied` is None): it is the worker's view, for the Analyst to weigh.
    `placed` maps each session to the `workdir` and `home` of the replica it played on, filled as the drills are
    played (see `experimental.cultivation.employee.Together`); with it, each review also carries that session's
    `evidence`. Without it, or for a session it does not name, the review sees the conversation and deliveries only.
    """

    def __init__(
        self, employee, spawn, *, records: Path | None = None, concurrency: int = 2, placed: dict | None = None
    ):
        if concurrency < 1:
            raise ValueError("reviews run at least one at a time")
        self.employee, self.spawn, self.concurrency = employee, spawn, concurrency
        self.records = Path(records) if records else None
        self.placed = placed
        self.rounds = 0

    def evidence(self, name: str) -> dict:
        """What session `name`'s replica held beyond the worker's baseline, as `request` takes it: `attachments`, the
        files new in its workdir's `uploads` (what the requester handed in during the session), and `filed`, the files
        the worker wrote or changed in its workdir (besides `uploads` and the deck engine's `decks`) and its home
        (besides the host's private folders). A replica starts from the worker's own workdir and home, so whatever
        both hold alike, such as materials handed over before the session, is not repeated. Empty when the session's
        replica is not known."""
        place = (self.placed or {}).get(name)
        if place is None:
            return {}
        workdir, home = Path(place["workdir"]), Path(place["home"])
        baseline = self.employee.baseline
        return {
            "attachments": handed(workdir / "uploads", Path(baseline.workdir) / "uploads", label="uploads"),
            "filed": {
                **written(workdir, baseline.workdir, label="workdir", skip=frozenset({"uploads", "decks"})),
                **written(home, baseline.config.workspace_path, label="home", skip=PRIVATE),
            },
        }

    async def _review(self, name: str, exchanges, gate: asyncio.Semaphore) -> dict:
        label = opaque(name)
        asked = request(exchanges, **self.evidence(name))
        async with gate:
            replica = self.spawn(self.employee, f"{self.rounds}-self-{label}")
            await replica.start()
            try:
                with Compartment("partner", spoken=[tuple(exchange.user for exchange in exchanges)]):
                    execution = await replica.run(asked, session_key=f"curator:{label}:self:{uuid4().hex}")
            finally:
                await replica.close()
        return {
            "session": name,
            "label": label,
            "turn_id": execution.turn_id,
            "text": execution.text,
            **parse(execution.text),
        }

    async def evaluate(self, sessions) -> Signal | None:
        if not sessions:
            return None
        self.rounds += 1
        gate = asyncio.Semaphore(self.concurrency)
        reviews = await asyncio.gather(*(self._review(name, exchanges, gate) for name, exchanges in sessions.items()))
        if self.records is not None:
            _write(
                self.records / "analysis" / f"{uuid4().hex}.json",
                json.dumps(
                    plain({"source": SOURCE, "round": self.rounds, "reviews": reviews}), ensure_ascii=False
                ).encode(),
            )
        items = tuple(
            Item(
                f"self-review:{review['label']}",
                review["result"],
                review["session"],
                actual=review["defects"],
                note=review["note"],
            )
            for review in reviews
        )
        text = "\n\n".join(
            f"[{review['label']}] own verdict: {review['result']}\n"
            + (f"defects: {review['defects']}\n" if review["defects"] else "")
            + (f"note: {review['note']}" if review["note"] else "")
            for review in reviews
        ).strip()
        return Signal(SOURCE, text, items, satisfied=None)
