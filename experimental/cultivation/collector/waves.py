"""Run one wave of research groups concurrently; the host decides each group's single repair by rule.

A group is acquired, verified and reviewed once. When the review withholds part of it, the group is repaired once
if its window still holds the editorial or acquisition minimum, on the path the review named (`needs_new_sources`);
nothing retries beyond that. Admitted findings are retained as evidence one by one, the admitted synthesis as one more
entry, so the description can cite the finding it relies on.
"""

import asyncio
import json
import time

from pydantic import Field

from experimental.cultivation.collector.information import (
    Dimension,
    Evidence,
    ResearchBrief,
    ResearchGroup,
    ResearchGuide,
    ResearchReview,
    _Model,
)
from experimental.cultivation.collector.researchers import ResearchError
from experimental.harness.participation.compartment import BoundaryError
from experimental.harness.participation.exchange import ExchangeError


class ResearchAssignment(_Model):
    """A research group with host-resolved evidence and optional guidance attached, bound to one attempt handle."""

    dimensions: tuple[Dimension, ...] = Field(min_length=1)
    brief: ResearchBrief
    known_information: tuple[Evidence, ...] = ()
    guidance: tuple[ResearchGuide, ...] = ()
    attempt: str
    previous_attempt: str | None = None
    remaining_seconds: float = Field(gt=0)


class Attempts:
    """Hand out attempt handles in order across waves and repairs."""

    def __init__(self):
        self.count = 0

    def next(self) -> str:
        self.count += 1
        return f"research-{self.count}"


async def _call(research, assignment):
    result = research(assignment)
    return await result if asyncio.iscoroutine(result) or hasattr(result, "__await__") else result


def _retain(result, assignment, retain):
    """Keep each admitted finding and the admitted synthesis as evidence; return what was kept."""
    kept = []
    for finding in result.get("findings", []):
        origin = json.dumps(
            {"attempt": assignment.attempt, "finding": finding["id"], "question": finding.get("question", "")},
            ensure_ascii=False,
        )
        entry = retain(
            "research",
            origin,
            json.dumps(finding, ensure_ascii=False),
            tuple(finding.get("sources", ())),
            assignment.dimensions,
        )
        kept.append({"evidence": entry["evidence"], "finding": finding["id"], "question": finding.get("question", "")})
    if result.get("synthesis"):
        origin = json.dumps({"attempt": assignment.attempt, "synthesis": True}, ensure_ascii=False)
        content = {
            key: result.get(key, [] if key != "synthesis" else "")
            for key in ("synthesis", "disagreements", "unanswered")
        }
        entry = retain("research", origin, json.dumps(content, ensure_ascii=False), (), assignment.dimensions)
        kept.append({"evidence": entry["evidence"], "synthesis": True})
    return kept


async def _attempt(assignment, research, retain, outcome, trace):
    result = await _call(research, assignment)
    review = ResearchReview.from_record(result["review"])
    outcome["attempts"].append(
        {
            "attempt": assignment.attempt,
            "previous_attempt": assignment.previous_attempt,
            "status": result.get("status"),
            "review": result["review"],
        }
    )
    outcome["admitted"].extend(_retain(result, assignment, retain))
    outcome["withheld"] = [
        {key: item.get(key) for key in ("id", "question", "reasons")} for item in result.get("withheld", [])
    ]
    outcome["leads"] = result.get("leads", [])
    outcome["unanswered"] = result.get("unanswered", [])
    outcome["refused"] = result.get("refused", [])
    trace.append(
        {
            "label": "research",
            "event": "attempt.reviewed",
            "attempt": assignment.attempt,
            "admitted": len(result.get("findings", [])),
            "withheld": len(outcome["withheld"]),
            "status": result.get("status"),
        }
    )
    return review


async def _group(number, group, *, research, limits, window, known, guides, retain, trace, attempts):
    started = time.monotonic()
    outcome = {
        "group": number,
        "dimensions": list(group.dimensions),
        "questions": list(group.brief.questions),
        "window_seconds": window,
        "attempts": [],
        "admitted": [],
        "withheld": [],
        "leads": [],
        "unanswered": [],
        "refused": [],
        "status": "failed",
    }
    assignment = ResearchAssignment(
        dimensions=group.dimensions,
        brief=group.brief,
        known_information=tuple(known[id] for id in group.known_evidence),
        guidance=tuple(
            guide for guide in guides if group.use_guidance and set(guide.dimensions) & set(group.dimensions)
        ),
        attempt=attempts.next(),
        remaining_seconds=window,
    )
    running = assignment
    try:
        async with asyncio.timeout(window):
            review = await _attempt(assignment, research, retain, outcome, trace)
            if not review.accepted and limits.research_revisions >= 1:
                left = window - (time.monotonic() - started)
                needed = limits.acquisition_minimum if review.needs_new_sources else limits.editorial_minimum
                if left >= needed:
                    running = assignment.model_copy(
                        update={
                            "attempt": attempts.next(),
                            "previous_attempt": assignment.attempt,
                            "remaining_seconds": left,
                        }
                    )
                    review = await _attempt(running, research, retain, outcome, trace)
                else:
                    trace.append(
                        {
                            "label": "research",
                            "event": "repair.skipped",
                            "attempt": assignment.attempt,
                            "seconds_left": round(left, 1),
                            "seconds_needed": needed,
                        }
                    )
            outcome["status"] = "accepted" if review.accepted else ("partial" if outcome["admitted"] else "withheld")
    # A group whose pages or findings meet a sealed passage was stopped before the Curator read them; its research is
    # withheld like any failed group, and the boundary log keeps the hit, rather than ending the whole preparation.
    except (BoundaryError, ExchangeError, ResearchError, OSError, TimeoutError, ValueError, KeyError) as exc:
        outcome["error"] = str(exc) or type(exc).__name__
        outcome["error_type"] = type(exc).__name__
        if not any(row["attempt"] == running.attempt for row in outcome["attempts"]):
            outcome["attempts"].append(
                {
                    "attempt": running.attempt,
                    "previous_attempt": running.previous_attempt,
                    "status": "failed",
                    "error": outcome["error"],
                }
            )
        if outcome["admitted"]:
            outcome["status"] = "partial"
        trace.append(
            {
                "label": "research",
                "event": "group.failed",
                "group": number,
                "error_type": type(exc).__name__,
                "error": outcome["error"][:600],
            }
        )
    outcome["seconds"] = round(time.monotonic() - started, 1)
    return outcome


async def run_wave(
    groups: tuple[ResearchGroup, ...],
    *,
    wave,
    research,
    limits,
    window,
    evidence,
    guides,
    retain,
    record,
    trace,
    attempts,
):
    """Run the groups concurrently inside one window each and return their outcomes in plan order."""
    known = {source.id: source for source in evidence}
    trace.append({"label": "research", "event": "wave.started", "wave": wave, "groups": len(groups), "window": window})
    outcomes = await asyncio.gather(
        *(
            _group(
                number,
                group,
                research=research,
                limits=limits,
                window=window,
                known=known,
                guides=guides,
                retain=retain,
                trace=trace,
                attempts=attempts,
            )
            for number, group in enumerate(groups, 1)
        )
    )
    record(f"wave-{wave}.json", list(outcomes))
    return list(outcomes)


def gaps(outcomes) -> list[dict]:
    """What a wave left open: withheld findings, unanswered questions and failed groups, for a replan or the composer."""
    rows = []
    for outcome in outcomes:
        for item in outcome.get("withheld", []):
            rows.append({"group": outcome["group"], "kind": "withheld", **item})
        for item in outcome.get("unanswered", []):
            rows.append(
                {
                    "group": outcome["group"],
                    "kind": "unanswered",
                    **(item if isinstance(item, dict) else {"question": item}),
                }
            )
        if outcome.get("error"):
            rows.append(
                {
                    "group": outcome["group"],
                    "kind": "failed",
                    "error": outcome["error"],
                    "questions": outcome["questions"],
                }
            )
    return rows
