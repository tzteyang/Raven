"""What the Curator hears of a round: the round's values projected onto the curator audience.

An assessor's per-item results, metrics, references and notes reach the Analyst only: a reference that reached the
Curator would be copied into the Harness and score the same cases next round without the worker improving, and a
criterion's name alone tells the Curator the standard it is measured against. Which fields go is declared on the
types (`protocols`, `history`, `experimental.requirements`); this module applies the projection, so the loop passes every
signal, history entry and execution observation bound for the Curator through here, whoever the assessor is.

Earlier cultivations the party brings (the scenario's prior) reach the Curator the same way: their histories,
projected, under opaque labels (`heard_prior`).

Of the round's executions the Curator receives the turns the Analyst cited: a requirement's evidence names turn ids,
and only those turns' exchanges go. A session goes by an opaque label (`opaque`) wherever the Curator can see it,
in the cited turns, in the mechanisms' activity rows and in the history, since a trial's name would say which
situation the round played; the label is the same for the same trial in every round, so those views line up.
"""

import hashlib
import re

from ..audience import project


def opaque(name: str) -> str:
    """The label a trial's session goes by wherever the Curator can see it: stable across rounds, never its name."""
    return "session-" + hashlib.blake2b(name.encode(), digest_size=3).hexdigest()


def heard_activity(rows) -> list[dict]:
    """The mechanisms' activity rows with each session under its opaque label."""
    return [{**row, "session": opaque(str(row["session"]))} if row.get("session") else dict(row) for row in rows]


def heard(signals) -> list[dict]:
    """The signals as the Curator may receive them: who spoke, its words, its satisfaction, what it handed over."""
    return project(tuple(signals), "curator")


def heard_history(entries) -> list[dict]:
    """The rounds as the Curator sees them: each assessor's satisfaction but never its per-item results, the
    revisions without their predicted effects (`experimental.iteration.history`), and the mechanisms that acted under
    opaque session labels."""
    return [
        {**entry, "mechanisms_acted": heard_activity(entry["mechanisms_acted"])}
        if "mechanisms_acted" in entry
        else entry
        for entry in project(tuple(entries), "curator")
    ]


def heard_prior(cultivations) -> list[dict]:
    """Earlier cultivations the party brings (`experimental.iteration.records.Cultivation`) as the Curator may hear
    them: each one's history projected like this run's under an opaque label, and nothing else of its record (no
    scorecard, judgement, session name or path)."""
    return [
        {"cultivation": f"prior-{number}", "history": heard_history(cultivation.history)}
        for number, cultivation in enumerate(cultivations, 1)
    ]


def cited(sessions, feedback) -> list[tuple[str, object]]:
    """The exchanges whose turn id a requirement of `feedback` names in its evidence or observation, each with the
    opaque key of its session; nothing when there is no feedback."""
    if feedback is None:
        return []
    text = " ".join(" ".join((*requirement.evidence, requirement.observed)) for requirement in feedback.requirements)
    found = []
    for key, exchanges in sessions.items():
        for exchange in exchanges:
            turn = exchange.execution.turn_id
            if turn and re.search(rf"(?<![\w-]){re.escape(turn)}(?![\w-])", text):
                found.append((opaque(key), exchange))
    return found


def heard_observations(sessions, feedback, task_id) -> list[dict]:
    """Execution observations of the cited turns, under opaque session keys, in the rows the Curator reads."""
    rows = []
    for key, exchange in cited(sessions, feedback):
        seen = project(exchange, "curator")
        rows.append(
            {
                "kind": "task.execution",
                "task_id": task_id,
                "session": key,
                "turn_id": seen["execution"]["turn_id"],
                "artifact_id": seen["execution"]["artifact_id"],
                "source": "trial",
                "user": seen["user"],
                "outcome": seen["execution"]["outcome"],
                "records": seen["execution"]["records"],
            }
        )
    return rows
