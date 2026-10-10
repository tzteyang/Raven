"""Source-backed research findings and quote verification for a delegated work problem."""

import html
import json
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from experimental.scenario.sealed import Sealed, carried

NAME = "submit_findings"
PROMPT = Path(__file__).resolve().parent / "prompts" / "research.md"
QUOTE = 20
_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_ADDRESS = re.compile(r"https?://\S+")
_TAG = re.compile(r"</?[A-Za-z][^>]*>")
_WRAPPED_WORD = re.compile(r"(?<=[A-Za-z])-(?:[ \t]+|\r?\n[ \t]*)(?=[A-Za-z])")


@dataclass(frozen=True)
class Finding:
    """One finding: `kind` is `fact` or `norm`, `sources` the pages that hold `evidence`, the passage that states
    it; `unmatched_sources` are the addresses the researcher also listed where the passage was not found;
    `conflicts` explain tensions with supplied information in words."""

    id: str
    text: str
    kind: str
    question: str
    sources: tuple[str, ...]
    evidence: str
    situation: str = ""
    conflicts: tuple[str, ...] = ()
    unmatched_sources: tuple[str, ...] = ()

    def record(self) -> dict:
        return asdict(self)


class Found(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, description="The question it answers.")
    kind: Literal["fact", "norm"] = Field(
        description="`fact`: what the source reports; `norm`: a source-recommended practice, not an adopted company rule."
    )
    text: str = Field(min_length=1, description="The finding as its source states it, in the materials' language.")
    situation: str = Field(default="", description="When it applies, if not always; empty otherwise.")
    sources: list[str] = Field(min_length=1, description="The addresses of the pages read that state it.")
    evidence: str = Field(
        min_length=1, description="A passage copied exactly from one of those pages, with nothing added or left out."
    )
    conflicts: list[str] = Field(
        default_factory=list,
        description="Substantive tensions with supplied known information, described in words; empty if none.",
    )


class Unanswered(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1)
    why: str = Field(min_length=1, description="Why this investigation did not answer it; do not imply impossibility.")
    channel: Literal["research", "user", "native"] = Field(
        default="research", description="Where this need can next be addressed; a search miss is not a user-only fact."
    )


class Inquiry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    findings: list[Found] = Field(default_factory=list)
    unanswered: list[Unanswered] = Field(default_factory=list)
    synthesis: str = Field(default="", description="Supported synthesis, limitations and proposed transfers.")
    disagreements: list[str] = Field(default_factory=list, description="Source disagreements or differences of scope.")


@dataclass(frozen=True)
class Researched:
    """A research's outcome: the findings that held, the questions left for the counterpart, the findings refused with
    their reasons, and how the researcher ran (who, on what model, at what cost)."""

    findings: tuple[Finding, ...]
    unanswered: tuple[dict, ...]
    refused: tuple[dict, ...]
    run: dict
    synthesis: str = ""
    disagreements: tuple[str, ...] = ()


def folded(text: str) -> str:
    """The words of a text in order: link addresses dropped, and case, width and punctuation folded away."""
    text = html.unescape(_TAG.sub(" ", text))
    words = _ADDRESS.sub(" ", _LINK.sub(r"\1", unicodedata.normalize("NFKC", text)))
    return re.sub(r"[\W_]+", " ", words.casefold()).strip()


def weight(quote: str) -> int:
    """How much a folded passage says, in Latin characters: a CJK character carries a word's worth, not a letter's."""
    return sum(3 if unicodedata.east_asian_width(char) in "WF" and char.isalpha() else 1 for char in quote)


def quoted(evidence: str, page: str) -> bool:
    """Whether the page holds the passage whole, once both are folded, from a word's start to a word's end (so
    "fee is 5" is not a passage of "fee is 50"); a passage of a few words proves nothing, in any script."""
    quote = folded(evidence)
    if weight(quote) < QUOTE:
        return False
    pattern = re.compile(rf"(?<![a-z0-9]){re.escape(quote)}(?![a-z0-9])")

    def contains(value):
        unwrapped = _WRAPPED_WORD.sub("", value.replace("\u00ad", ""))
        return any(pattern.search(folded(view)) for view in (value, unwrapped))

    structured = page
    if page.startswith("Title:") and "\n\nURL Source:" in page:
        _, separator, content = page.partition("\n\nMarkdown Content:\n")
        if separator:
            structured = content
    if structured.lstrip().startswith(("{", "[")):
        try:
            document = json.loads(structured)
        except ValueError:
            pass
        else:

            def strings(value):
                if isinstance(value, str):
                    yield value
                elif isinstance(value, dict):
                    for item in value.values():
                        yield from strings(item)
                elif isinstance(value, list):
                    for item in value:
                        yield from strings(item)

            return any(contains(value) for value in strings(document))
    return contains(page)


def problems(found: Found, pages: Mapping[str, str | None], sealed: Mapping[str, Sealed]) -> list[str]:
    """Why a finding does not hold, given the text of each page it cites (None when it was not or could not be read).

    `pages` may hold every page the research read: a passage found in one of those instead of a listed source is
    reported with its address, since a misattributed quote is corrected by changing the citation, not by
    researching again."""
    said = []
    unread = [source for source in found.sources if not pages.get(source)]
    if unread:
        said.append(f"its sources were not read or could not be read: {unread}")
    if not any(quoted(found.evidence, pages[source]) for source in found.sources if pages.get(source)):
        elsewhere = [
            url for url, text in pages.items() if url not in found.sources and text and quoted(found.evidence, text)
        ]
        if elsewhere:
            said.append(
                f"its evidence is a passage of {elsewhere[:3]}, not of the sources it lists; cite the page that holds it"
            )
        else:
            said.append("its evidence is not a passage of its sources; copy the passage exactly, with nothing added")
    if carried((found.text, found.situation, found.evidence, *found.conflicts), sealed):
        said.append("its wording says what neither the pages nor the materials say")
    return said


def check(inquiry: Inquiry, pages: Mapping[str, str | None], sealed, limit: int) -> list[str]:
    """Every reason the inquiry does not hold, finding by finding, for a researcher that can correct it."""
    said = [f"give at most {limit} findings, the ones the work needs most"] if len(inquiry.findings) > limit else []
    for number, found in enumerate(inquiry.findings, 1):
        said += [f"finding {number}: {reason}" for reason in problems(found, pages, sealed)]
    for number, row in enumerate(inquiry.unanswered, 1):
        if carried((row.question, row.why), sealed):
            said.append(f"unanswered question {number} says what the materials do not")
    if carried((inquiry.synthesis, *inquiry.disagreements), sealed):
        said.append("the synthesis or source disagreements say what the materials do not")
    return said


async def verify(
    inquiry: Inquiry,
    web,
    *,
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
        for source in found.sources:
            while not quoted(found.evidence, pages.get(source) or "") and getattr(web, "can_expand", lambda _: False)(
                source
            ):
                pages[source] = await web.expand(source)
        reasons = problems(found, {**getattr(web, "pages", {}), **pages}, sealed)
        if not reasons and len(kept) >= limit:
            reasons = [f"over the limit of {limit} findings"]
        if reasons:
            refused.append({**found.model_dump(), "reasons": reasons})
            continue
        matched = tuple(source for source in found.sources if quoted(found.evidence, pages.get(source) or ""))
        kept.append(
            Finding(
                f"{prefix}-{number}",
                found.text,
                found.kind,
                found.question,
                matched,
                found.evidence,
                found.situation,
                tuple(found.conflicts),
                tuple(source for source in found.sources if source not in matched),
            )
        )
    unanswered = []
    for row in inquiry.unanswered:
        if carried((row.question, row.why), sealed):
            refused.append({**row.model_dump(), "reasons": ["it says what the materials do not"]})
        else:
            unanswered.append(row.model_dump())
    synthesis, disagreements = inquiry.synthesis, tuple(inquiry.disagreements)
    if carried((synthesis, *disagreements), sealed):
        refused.append({"section": "synthesis", "reasons": ["it says what the materials do not"]})
        synthesis, disagreements = "", ()
    return Researched(tuple(kept), tuple(unanswered), tuple(refused), dict(run or {}), synthesis, disagreements)


async def inquire(
    researcher,
    packet: dict,
    web,
    *,
    sealed: Mapping[str, Sealed] | None = None,
    limit: int = 8,
    prefix: str = "researched",
    trace=None,
) -> Researched:
    """Run acquisition and quote checks; semantic admission belongs to review_research."""
    inquiry, run = await researcher.research(
        packet,
        web,
        lambda value: check(value, web.pages, sealed or {}, limit),
        trace=trace,
    )
    return await verify(inquiry, web, sealed=sealed, limit=limit, prefix=prefix, run=run)
