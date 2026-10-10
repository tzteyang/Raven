"""Acquire and review one research attempt; the collector owns any subsequent repair decision.

Admission is per finding: the review names the findings it withholds and whether the synthesis stands, so what
passed stays available while the withheld parts wait for a revision. A revision whose review needed no new sources
is editorial: the researcher rewrites from the views it already has, without searching.
"""

import asyncio
import json
import time
from pathlib import Path

from experimental.cultivation.collector.information import ResearchReview
from experimental.cultivation.collector.inquiry import check, verify

PROMPT = Path(__file__).resolve().parent / "prompts" / "review_research.md"
UNREADABLE = "not read or could not be read"
VIEW_CHARS = 20_000


def leads(refused) -> list[dict]:
    """Findings refused only because the host could not read a cited page: kept for a person to check by hand."""
    return [
        {
            **{key: item.get(key) for key in ("question", "text", "sources", "evidence")},
            "reason": "the host could not read a cited page; check the passage by hand",
        }
        for item in refused
        if any(UNREADABLE in reason for reason in item.get("reasons", ()))
    ]


def _trimmed(views: dict) -> dict:
    return {
        url: text if len(text) <= VIEW_CHARS else text[:VIEW_CHARS] + f"\n[view trimmed at {VIEW_CHARS} characters]"
        for url, text in views.items()
    }


async def review_research(
    researcher, brief, web, reviewer, *, records, timeout=3600, admit=None, limit=8, previous=None
):
    """Return the admitted findings, the withheld parts with their reasons and the review, without starting another
    research attempt."""
    records = Path(records)
    records.mkdir(parents=True, exist_ok=False)
    packet = {**brief.model_dump(mode="json"), "at_most": limit, "time_budget_seconds": timeout}
    reviews = []
    editorial = False
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
            reviews.append(review)
        last = reviews[-1] if reviews else None
        editorial = bool(last) and last.get("accepted") is False and not last.get("needs_new_sources", True)
        views = prior("sources.json", {})
        packet["revision"] = {
            "editorial": editorial,
            "previous_delivery": prior("candidate.json", None),
            "admitted_findings": prior("result.json", {}).get("findings", []),
            "review": last,
            "previous_reviews": reviews,
            "verification_failures": prior("verification.json", {}).get("refused", []),
            "source_views": _trimmed(views) if editorial else views,
            "previous_status": prior("status.json", {}),
        }
    save("brief.json", brief.model_dump(mode="json"))
    save("request.json", packet)
    save("prior-reviews.json", reviews)
    trace = []
    try:
        async with asyncio.timeout(timeout):
            admitted(packet, "research.request")

            def checked_by_host(value):
                return check(value, web.pages, {}, limit)

            if editorial:
                inquiry, run = await researcher.revise(
                    packet, checked_by_host, trace=trace, records=records / "acquisition"
                )
            else:
                inquiry, run = await researcher.research(
                    packet, web, checked_by_host, trace=trace, records=records / "acquisition"
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
            truncated = getattr(web, "truncated", {})
            found_leads = leads(checked.refused)
            review_input = {
                "brief": {**brief.model_dump(mode="json"), "at_most": limit},
                "delivery": delivery,
                "refused": list(checked.refused),
                "leads": found_leads,
                "admitted_earlier": packet.get("revision", {}).get("admitted_findings", []),
                "source_views": pages,
                "source_view_sizes": {
                    url: {"chars": len(text), "truncated": bool(truncated.get(url))} for url, text in pages.items()
                },
                "truncated_sources": [url for url in sorted(urls) if truncated.get(url)],
                "previous_reviews": reviews,
                "time_budget_seconds": max(0, timeout - (time.monotonic() - started)),
            }
            admitted(review_input, "research.review")
            save("verification.json", {**delivery, "refused": list(checked.refused)})
            save("sources.json", pages)
            save("leads.json", found_leads)
            review = ResearchReview.model_validate(await reviewer(review_input, records / "review"))
            delivered = {finding["id"] for finding in delivery["findings"]}
            if {verdict.id for verdict in review.findings} != delivered:
                raise ValueError(f"review verdicts must cover exactly the delivered findings: {sorted(delivered)}")
            withheld = {verdict.id: verdict.reason for verdict in review.findings if not verdict.admit}
            kept = [finding for finding in delivery["findings"] if finding["id"] not in withheld]
            held = [
                {**finding, "reasons": [withheld[finding["id"]]]}
                for finding in delivery["findings"]
                if finding["id"] in withheld
            ]
            synthesis = delivery["synthesis"] if review.synthesis_admitted else ""
            disagreements = delivery["disagreements"] if review.synthesis_admitted else []
            status = "accepted" if review.accepted else ("partial" if kept or synthesis else "rejected")
            save("review.json", review.record())
            result = {
                "findings": kept,
                "withheld": held,
                "unanswered": delivery["unanswered"],
                "synthesis": synthesis,
                "disagreements": disagreements,
                "review": review.record(),
                "review_history": [*reviews, review.record()],
                "run": run,
                "refused": [{"question": item.get("question"), "reasons": item["reasons"]} for item in checked.refused],
                "leads": found_leads,
                "status": status,
            }
            save("result.json", result)
            save("status.json", {"status": status, "seconds": time.monotonic() - started})
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
