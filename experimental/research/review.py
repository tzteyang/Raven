"""Acquire and review one research attempt; the collector owns any subsequent repair decision."""

import asyncio
import json
import time
from pathlib import Path

from .information import Review
from .inquiry import check, verify

PROMPT = Path(__file__).resolve().parent / "prompts" / "review_research.md"


async def review_research(
    researcher, brief, web, reviewer, *, records, timeout=3600, admit=None, limit=8, previous=None
):
    """Return acceptance or actionable rejection without starting another research attempt."""
    records = Path(records)
    records.mkdir(parents=True, exist_ok=False)
    packet = {**brief.model_dump(mode="json"), "at_most": limit, "time_budget_seconds": timeout}
    reviews = []
    started = time.monotonic()

    def save(name, value):
        (records / name).write_text(json.dumps(value, ensure_ascii=False, indent=2))

    def admitted(value, stage):
        if admit is not None:
            admit(value, stage)

    if previous is not None:
        previous = Path(previous)

        def prior(name, default):
            path = previous / name
            return json.loads(path.read_text()) if path.exists() else default

        reviews = prior("prior-reviews.json", [])
        if review := prior("review.json", None):
            reviews.append(Review.model_validate(review).model_dump(mode="json"))
        packet["revision"] = {
            "previous_delivery": prior("candidate.json", None),
            "review": reviews[-1] if reviews else None,
            "previous_reviews": reviews,
            "verification_failures": prior("verification.json", {}).get("refused", []),
            "source_views": prior("sources.json", {}),
            "previous_status": prior("status.json", {}),
        }
    save("brief.json", brief.model_dump(mode="json"))
    save("request.json", packet)
    save("prior-reviews.json", reviews)
    trace = []
    try:
        async with asyncio.timeout(timeout):
            admitted(packet, "research.request")
            inquiry, run = await researcher.research(
                packet,
                web,
                lambda value: check(value, web.pages, {}, limit),
                trace=trace,
                records=records / "acquisition",
            )
            admitted(inquiry.model_dump(mode="json"), "research.result")
            save("candidate.json", inquiry.model_dump(mode="json"))
            checked = await verify(inquiry, web, limit=limit, run=run)
            delivery = {
                "findings": [finding.record() for finding in checked.findings],
                "unanswered": list(checked.unanswered),
                "synthesis": checked.synthesis,
                "disagreements": list(checked.disagreements),
            }
            urls = {url for finding in inquiry.findings for url in finding.sources}
            pages = {url: web.pages[url] for url in sorted(urls) if url in web.pages}
            review_input = {
                "brief": {**brief.model_dump(mode="json"), "at_most": limit},
                "delivery": delivery,
                "refused": list(checked.refused),
                "source_views": pages,
                "truncated_sources": [url for url in sorted(urls) if getattr(web, "truncated", {}).get(url)],
                "previous_reviews": reviews,
                "time_budget_seconds": max(0, timeout - (time.monotonic() - started)),
            }
            admitted(review_input, "research.review")
            save("verification.json", {**delivery, "refused": list(checked.refused)})
            save("sources.json", pages)
            review = Review.model_validate(await reviewer(review_input, records / "review"))
            save("review.json", review.model_dump(mode="json"))
            result = {
                **delivery,
                "review": review.model_dump(mode="json"),
                "review_history": [*reviews, review.model_dump(mode="json")],
                "run": run,
                "refused": [{"question": item.get("question"), "reasons": item["reasons"]} for item in checked.refused],
            }
            save("result.json", result)
            save(
                "status.json",
                {"status": "accepted" if review.accepted else "rejected", "seconds": time.monotonic() - started},
            )
            return result
    except BaseException as exc:
        save(
            "status.json",
            {
                "status": "incomplete",
                "error_type": type(exc).__name__,
                "error": str(exc) or type(exc).__name__,
                "seconds": time.monotonic() - started,
            },
        )
        raise
    finally:
        save("trace.json", trace)
