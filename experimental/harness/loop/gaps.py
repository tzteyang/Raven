"""Who answers the questions a curation leaves open: the counterpart for the business's own facts, research for
public knowledge, and nobody invents the rest.

A curation that reports a gap (`GapReportedError`) names the kind of source that can settle it: `private` (only the
business can state, decide or grant it), `public` (published sources can) or `unclear`. The session keeps each
question in its record's `questions` and routes it through the `Gaps` its host supplies:

- a private or unclear question waits for the counterpart's next contact, the review of the next round, where
  `answer` is asked; a reply with text answers it, and an unclear one left unanswered, or any the counterpart refers
  to public sources, goes on to research;
- a public question, or an unclear one with nobody to ask, is researched right away through `research`, at most
  `research_tasks` of them between two analyses, the rest at the next opportunity;
- a question no configured source can settle, or still open when the run finishes, is `unanswered`.

Every answer carries its provenance: `counterpart` (as the counterpart stated it) or `research` (findings with their
public sources). The next curation reads the settled questions with its information (`heard_answers`).
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

Kind = Literal["private", "public", "unclear"]
KINDS: tuple[Kind, ...] = ("private", "public", "unclear")


@dataclass(frozen=True)
class Reply:
    """The counterpart's reply to one question: its `text`, None when it leaves the question open, and whether it
    says `public` sources settle the question rather than the business."""

    text: str | None = None
    public: bool = False


@dataclass(frozen=True)
class Gaps:
    """The answerers a host supplies. `answer(question)` is the counterpart, a simulated one or a person, given the
    question's `id`, `question` and `kind`, returning a `Reply`. `research(worker, provider, questions, *, admit)`
    researches public questions inside the Curator's compartment and returns, by question id, `findings` and a
    `synthesis` when anything was admitted, or a `reason` when nothing was."""

    answer: Callable[[dict], Awaitable[Reply]] | None = None
    research: Callable[..., Awaitable[dict]] | None = None
    research_tasks: int = 3

    def __post_init__(self):
        if self.answer is None and self.research is None:
            raise ValueError("gap answers need the counterpart, research or both")
        if self.research is not None and (not isinstance(self.research_tasks, int) or self.research_tasks < 1):
            raise ValueError("research needs a positive task allowance")

    def route(self, kind: str, *, declined: bool = False, referred: bool = False) -> str:
        """Where a question goes next: `counterpart`, `research` or `unanswered`. A `declined` question is one the
        counterpart left open; `referred` means it pointed to public sources, which overrides the Curator's kind."""
        if kind not in KINDS:
            raise ValueError(f"unknown question kind: {kind}")
        if not declined and kind != "public" and self.answer is not None:
            return "counterpart"
        if self.research is not None and (kind != "private" or referred):
            return "research"
        return "unanswered"


def heard_answers(questions) -> list[dict]:
    """The settled questions as the Curator reads them: each answered one with its provenance and answer, each
    unanswered one with the reason; questions still waiting for an answerer are left out."""
    rows = []
    for row in questions:
        if row.get("status") == "answered":
            rows.append({key: row[key] for key in ("id", "question", "kind", "status", "answer")})
        elif row.get("status") == "unanswered":
            rows.append({key: row.get(key) for key in ("id", "question", "kind", "status", "reason")})
    return rows
