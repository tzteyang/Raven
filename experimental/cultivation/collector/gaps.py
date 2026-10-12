"""Research the public questions a curation left open, on the collector's research channel and within its limits.

Each question becomes a research group of its own whose brief asks it as the Curator wrote it, so no planning call is
made; the groups run concurrently in one wave, each inside the collector's research window, and are reviewed and
repaired as a collection's are (`experimental.cultivation.collector.waves`). The admitted findings answer a question
with their public sources. Nothing is composed into the information snapshot: the loop hands the findings to the next
curation labelled as research (`experimental.harness.loop.gaps`).
"""

import json
from pathlib import Path

from experimental.cultivation.collector.collection import CollectionLimits
from experimental.cultivation.collector.curator import research_channel
from experimental.cultivation.collector.information import ResearchBrief, ResearchGroup
from experimental.cultivation.collector.waves import Attempts, run_wave

SCOPE = (
    "Public sources only: regulation, platform rules and the published practice of the field. The business's own "
    "rules, prices and decisions cannot be researched; say so instead of inferring them."
)
DELIVERABLE = (
    "Findings that answer the question, each with the public source that states it, and what stays unanswered."
)
ACCEPTANCE = (
    "Every finding quotes a page that states it.",
    "A recommended practice is a norm of the field, never presented as this business's own rule.",
)


def _group(task: str, question: dict) -> ResearchGroup:
    return ResearchGroup(
        # The researcher never reads dimensions; a group needs one, and the description's categories do not apply.
        dimensions=("knowledge",),
        serves=(question["id"],),
        brief=ResearchBrief(
            background=f"An assistant is being prepared for this task: {task}\nWhile changing how it works, this "
            "question arose, and what the business supplied does not settle it.",
            questions=(question["question"],),
            scope=SCOPE,
            deliverable=DELIVERABLE,
            acceptance=ACCEPTANCE,
        ),
        use_guidance=False,
    )


def _answer(outcome: dict, kept: dict) -> dict:
    findings, synthesis = [], ""
    for row in outcome["admitted"]:
        content = json.loads(kept[row["evidence"]])
        if row.get("synthesis"):
            synthesis = content.get("synthesis", "")
        else:
            findings.append({key: content.get(key) for key in ("text", "kind", "situation", "sources")})
    if findings:
        return {"findings": findings, "synthesis": synthesis}
    if outcome.get("error"):
        return {"reason": f"Research failed: {outcome['error']}"}
    why = [item.get("why", "") if isinstance(item, dict) else str(item) for item in outcome.get("unanswered", ())]
    return {"reason": " ".join(text for text in why if text) or "Research admitted no finding."}


async def research_gaps(
    worker,
    provider,
    questions,
    *,
    records: Path,
    admit=None,
    researcher="exchange",
    model=None,
    review_model=None,
    research_model=None,
    research_effort=None,
    research_budget=None,
    limits=CollectionLimits(),
) -> dict[str, dict]:
    """Research `questions` (each with an `id` and its `question`), at most `limits.research_tasks` of them, and
    return by id the admitted `findings` with a `synthesis`, or the `reason` none was admitted. Each call keeps its
    attempts, web log, wave and trace in a new numbered folder under `records`."""
    questions = list(questions)
    if len(questions) > limits.research_tasks:
        raise ValueError(f"at most {limits.research_tasks} research tasks at a time")
    records = Path(records)
    records.mkdir(parents=True, exist_ok=True)
    folder = records / f"call-{len(list(records.glob('call-*'))) + 1}"
    folder.mkdir()
    (folder / "questions.json").write_text(json.dumps(questions, ensure_ascii=False, indent=2))
    research = research_channel(
        worker,
        provider,
        records=folder,
        researcher=researcher,
        model=model,
        review_model=review_model,
        research_model=research_model,
        research_effort=research_effort,
        research_budget=research_budget,
        limits=limits,
        admit=admit,
    )
    kept, trace = {}, []

    def retain(channel, origin, content, sources=(), dimensions=()):
        identity = f"evidence-{len(kept) + 1}"
        kept[identity] = content
        return {"evidence": identity, "result": content}

    def record(name, value):
        (folder / name).write_text(json.dumps(value, ensure_ascii=False, indent=2))

    task = worker.baseline.task.text
    outcomes = await run_wave(
        tuple(_group(task, question) for question in questions),
        wave=1,
        research=research,
        limits=limits,
        window=limits.research_window,
        evidence=[],
        guides=[],
        retain=retain,
        record=record,
        trace=trace,
        attempts=Attempts(),
    )
    record("trace.json", trace)
    return {question["id"]: _answer(outcome, kept) for question, outcome in zip(questions, outcomes)}
