"""What the job needs that the materials handed over leave unsaid and the web can tell: one research, held to what it
read.

A researcher (`experimental.research.researchers`) receives the brief: the profile, the materials every reader of a
norm may receive (the induction's reading, never a check or a case), the questions to research (the Curator's when
the stage answers one, none when it looks for what the work needs) and how many findings to give. It returns
findings, each a fact about the world or a rule of the trade as a page states it, with the pages it was read from and
a passage copied from one of them, and the questions the web cannot answer, such as the business's own prices, with
why.

The stage then holds every finding to what was read, whoever researched it (`verify`): its passage must occur whole in
one of its pages, read here (`experimental.research.web.Web.page`) and compared with link addresses dropped and case,
width and punctuation folded, from a word's start to a word's end, so a changed number or a word left out fails;
the materials it contradicts must be materials handed over, which win over it; and its wording must carry no text
sealed from a reader of norms, since a finding reaches the partner, the Analyst and the Curator once the party
settles it. A finding that fails is refused with its reasons and kept on record, never written.
"""

import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..scenario import Scenario
from ..scenario.sealed import Sealed
from .induction import carried, package, readable

NAME = "submit_findings"
PROMPT = Path(__file__).resolve().parent / "prompts" / "research.md"
QUOTE = 20
_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_ADDRESS = re.compile(r"https?://\S+")


@dataclass(frozen=True)
class Finding:
    """One finding: `kind` is `fact` or `norm`, `sources` the pages it was read from and `evidence` the passage of
    one of them that states it; `conflicts` are the materials handed over that say otherwise."""

    id: str
    text: str
    kind: str
    question: str
    sources: tuple[str, ...]
    evidence: str
    situation: str = ""
    conflicts: tuple[str, ...] = ()

    def record(self) -> dict:
        return asdict(self)


class Found(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, description="The question it answers.")
    kind: Literal["fact", "norm"] = Field(
        description="`fact`: how the world is; `norm`: what the assistant should do, as the trade commonly does it."
    )
    text: str = Field(min_length=1, description="The finding as its source states it, in the materials' language.")
    situation: str = Field(default="", description="When it applies, if not always; empty otherwise.")
    sources: list[str] = Field(min_length=1, description="The addresses of the pages read that state it.")
    evidence: str = Field(
        min_length=1, description="A passage copied exactly from one of those pages, with nothing added or left out."
    )
    conflicts: list[str] = Field(
        default_factory=list, description="The materials handed over that say otherwise, by name; empty if none."
    )


class Unanswered(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1)
    why: str = Field(min_length=1, description="Why the web cannot answer it, such as: only the business knows.")


class Inquiry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    findings: list[Found] = Field(default_factory=list)
    unanswered: list[Unanswered] = Field(default_factory=list)


@dataclass(frozen=True)
class Researched:
    """A research's outcome: the findings that held, the questions left for the party, the findings refused with
    their reasons, and how the researcher ran (who, on what model, at what cost)."""

    findings: tuple[Finding, ...]
    unanswered: tuple[dict, ...]
    refused: tuple[dict, ...]
    run: dict


def brief(scenario: Scenario, questions: Sequence[str] = (), limit: int = 8) -> dict:
    """What a researcher receives: never a check or a case, only what every reader of a norm may receive."""
    return {
        "profile": scenario.situation.profile,
        "materials": [{**package(material), "kind": material.kind} for material in readable(scenario).values()],
        "questions": list(questions),
        "at_most": limit,
    }


def folded(text: str) -> str:
    """The words of a text in order: link addresses dropped, and case, width and punctuation folded away."""
    words = _ADDRESS.sub(" ", _LINK.sub(r"\1", unicodedata.normalize("NFKC", text)))
    return re.sub(r"[\W_]+", " ", words.casefold()).strip()


def quoted(evidence: str, page: str) -> bool:
    """Whether the page holds the passage whole, once both are folded, from a word's start to a word's end (so
    "fee is 5" is not a passage of "fee is 50"); a passage of a few words proves nothing."""
    quote = folded(evidence)
    if len(quote) < QUOTE:
        return False
    return re.search(rf"(?<![a-z0-9]){re.escape(quote)}(?![a-z0-9])", folded(page)) is not None


def problems(
    found: Found, pages: Mapping[str, str | None], materials: Sequence[str], sealed: Mapping[str, Sealed]
) -> list[str]:
    """Why a finding does not hold, given the text of each page it cites (None when it was not or could not be read)."""
    said = []
    unread = [source for source in found.sources if not pages.get(source)]
    if unread:
        said.append(f"its sources were not read or could not be read: {unread}")
    if not any(quoted(found.evidence, pages[source]) for source in found.sources if pages.get(source)):
        said.append("its evidence is not a passage of its sources; copy the passage exactly, with nothing added")
    stray = sorted(set(found.conflicts) - set(materials))
    if stray:
        said.append(f"it names as conflicting materials that were not handed over: {stray}")
    if carried((found.text, found.situation, found.evidence), sealed):
        said.append("its wording says what neither the pages nor the materials say")
    return said


def check(inquiry: Inquiry, pages: Mapping[str, str | None], materials, sealed, limit: int) -> list[str]:
    """Every reason the inquiry does not hold, finding by finding, for a researcher that can correct it."""
    said = [f"give at most {limit} findings, the ones the work needs most"] if len(inquiry.findings) > limit else []
    for number, found in enumerate(inquiry.findings, 1):
        said += [f"finding {number}: {reason}" for reason in problems(found, pages, materials, sealed)]
    for number, row in enumerate(inquiry.unanswered, 1):
        if carried((row.question, row.why), sealed):
            said.append(f"unanswered question {number} says what the materials do not")
    return said


async def verify(
    inquiry: Inquiry,
    web,
    *,
    materials: Sequence[str],
    sealed: Mapping[str, Sealed] | None = None,
    limit: int = 8,
    prefix: str = "researched",
    run: dict | None = None,
) -> Researched:
    """The findings that hold, ids `<prefix>-1` on, and the refused ones with why; the pages they cite are read here
    when the researcher read them elsewhere."""
    sealed = sealed or {}
    pages = {}
    for found in inquiry.findings:
        for source in found.sources:
            if source not in pages:
                pages[source] = await web.page(source)
    kept, refused = [], []
    for number, found in enumerate(inquiry.findings, 1):
        reasons = problems(found, pages, materials, sealed)
        if not reasons and len(kept) >= limit:
            reasons = [f"over the limit of {limit} findings"]
        if reasons:
            refused.append({**found.model_dump(), "reasons": reasons})
            continue
        kept.append(
            Finding(
                f"{prefix}-{len(kept) + 1}",
                found.text,
                found.kind,
                found.question,
                tuple(found.sources),
                found.evidence,
                found.situation,
                tuple(found.conflicts),
            )
        )
    unanswered = []
    for row in inquiry.unanswered:
        if carried((row.question, row.why), sealed):
            refused.append({**row.model_dump(), "reasons": ["it says what the materials do not"]})
        else:
            unanswered.append(row.model_dump())
    return Researched(tuple(kept), tuple(unanswered), tuple(refused), dict(run or {}))


async def inquire(
    researcher,
    scenario: Scenario,
    web,
    *,
    questions: Sequence[str] = (),
    sealed: Mapping[str, Sealed] | None = None,
    limit: int = 8,
    prefix: str = "researched",
    trace=None,
) -> Researched:
    """Research the brief of `scenario` with `researcher` and keep what holds (see the module's description)."""
    packet = brief(scenario, questions, limit)
    materials = [row["name"] for row in packet["materials"]]
    inquiry, run = await researcher.research(
        packet,
        web,
        lambda value: check(value, web.pages, materials, sealed or {}, limit),
        trace=trace,
    )
    return await verify(inquiry, web, materials=materials, sealed=sealed, limit=limit, prefix=prefix, run=run)
