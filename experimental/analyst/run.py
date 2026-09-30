"""Filter a round's signals, interpret the rest, and record the resulting feedback."""

import json
import re
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from uuid import uuid4

from ..audience import project
from ..curator.generation.context.render import tool
from ..curator.harness.declaration import schema_for
from ..curator.raven_adapter.materialize import _write
from ..curator.raven_adapter.observe import plain
from ..curator.raven_adapter.targets import catalogue
from ..iteration.exchange import exchange, messages
from ..scenario.sealed import WINDOW, Sealed, weight
from .feedback import Feedback
from .materials import RECORDS, materials, read_records, record_tool

NAME = "submit_feedback"
_PROMPT = Path(__file__).resolve().parent / "prompts" / "analyst.md"


@dataclass(frozen=True)
class Limits:
    max_calls: int = 4
    call_timeout: float = 120

    def __post_init__(self):
        if (
            not isinstance(self.max_calls, int)
            or self.max_calls < 1
            or not isfinite(self.call_timeout)
            or self.call_timeout <= 0
        ):
            raise ValueError("analyst limits must be finite positive bounds")


def known_ids(history) -> list[str]:
    """The requirement ids raised in earlier rounds, in order, each once."""
    return list(dict.fromkeys(raised.id for entry in history for raised in entry.requirements if raised.id))


def identified(feedback: Feedback, known) -> Feedback:
    """The feedback with its requirements' ids assigned: the earlier id when one repeats, the next number otherwise."""
    known = list(known)
    requirements = []
    for requirement in feedback.requirements:
        if requirement.repeats is not None:
            if requirement.repeats not in known:
                raise ValueError(f"repeats names no earlier requirement: {requirement.repeats!r}; known ids: {known}")
            requirements.append(requirement.model_copy(update={"id": requirement.repeats}))
            continue
        known.append(f"R{len(known) + 1}")
        requirements.append(requirement.model_copy(update={"id": known[-1]}))
    return feedback.model_copy(update={"requirements": tuple(requirements)})


# Criteria whose wording restates what the Curator already holds: an earlier requirement, or a handed-over norm.
SHARED = frozenset({"requirement", "material"})


def vet(feedback: Feedback, signals, sessions, *, sealed: Sealed | None = None, targets=(), spoken=None) -> None:
    """Refuse feedback whose Curator-facing part carries what the Curator may not receive, or a requirement that
    names no turn of this round or no situation.

    From the round itself the check knows the item ids, the session names, the target names and the short
    reference answers and notes; a reference answer is the evaluation side's own unless its item restates an earlier
    requirement or a handed-over norm (`Item.basis`), and none of it counts where the Curator hears it anyway, in a
    signal's words or a conversant's. A long reference text is left to `sealed`, the run's fingerprints, which know
    what the Curator may see: a requirement legitimately restates the norm a check restates, and only the
    differential sealing of the run can tell that wording from the check's own. `spoken` are the streams of words
    the Curator's compartment spares (by default this round's conversants): a requirement may quote the customer."""
    if spoken is None:
        spoken = [tuple(exchange.user for exchange in exchanges) for exchanges in sessions.values()]
    hidden = [
        text
        for signal in signals
        for item in signal.items
        for text in ((item.note,) if item.basis in SHARED else (item.expected, item.note))
        if text and weight(text) < WINDOW
    ]
    tokens = [*(item.id for signal in signals for item in signal.items), *sessions, *targets]
    visible = [*(signal.text for signal in signals if signal.text), *(text for stream in spoken for text in stream)]
    fingerprints = Sealed.of(hidden, visible=visible, tokens=tokens)
    heard = json.dumps(project(feedback, "curator"), ensure_ascii=False)
    if sealed:
        sealed = sealed.without(spoken)
    hits = list(dict.fromkeys([*fingerprints.hits(heard), *(sealed.hits(heard) if sealed else [])]))
    if hits:
        raise ValueError(
            "the feedback carries what the Curator may not receive (an item id, a session name, a reference answer "
            f"or a target name): {', '.join(hits)}; state the behavior in observable terms instead"
        )
    turns = [exchange.execution.turn_id for exchanges in sessions.values() for exchange in exchanges]
    for requirement in feedback.requirements:
        if not requirement.situation.strip():
            raise ValueError(f"requirement {requirement.id} states no situation")
        cited = " ".join((*requirement.evidence, requirement.observed))
        if not any(re.search(rf"(?<![\w-]){re.escape(turn)}(?![\w-])", cited) for turn in turns if turn):
            raise ValueError(
                f"requirement {requirement.id} cites no turn of this round in its evidence or observed; "
                f"the round's turn ids are {turns}"
            )


def triage(signals) -> Feedback | None:
    """Decide without the model when the signals plainly say nothing needs analysis."""
    if not signals:
        return Feedback(decision="continue", reason="No assessor produced a signal this round.")
    if all(signal.satisfied is True and not signal.text.strip() for signal in signals):
        return Feedback(decision="continue", reason="Every assessor is satisfied and none added a remark.")
    return None


async def analyse(
    worker,
    provider,
    signals,
    sessions,
    *,
    previous_signals=(),
    previous_feedback=None,
    history=(),
    model=None,
    limits=Limits(),
    sealed: Sealed | None = None,
    spoken=None,
) -> Feedback:
    """Produce this round's feedback; `curate` decisions are what the caller hands to workflow.improve.

    `sealed` are the Curator's sealed fingerprints of the run, checked against the feedback's Curator-facing part
    at submission (see `vet`), so the model corrects a leak instead of the curation aborting on it; `spoken` are the
    words the Curator's compartment spares, which the check spares the same way."""
    trace = []
    record = {"signals": plain(signals), "trace": trace}
    try:
        feedback = triage(signals)
        if feedback is None:
            inspection = await worker.inspect()
            skills = sorted(name for name in inspection.sources if name.startswith("skill."))
            packet = materials(
                worker.baseline.task.text,
                signals,
                sessions,
                previous_signals=previous_signals,
                previous_feedback=previous_feedback,
                skills=skills,
                history=history,
            )
            if getattr(worker, "children", None):
                packet["composition"] = inspection.facts.get("composition", {})
                packet["child_plans"] = {
                    name: project(child.plan, "analyst") if child.plan else None
                    for name, child in worker.children.items()
                }
            locations = ["root", *(f"child/{name}" for name in getattr(worker, "children", {}))]
            packet["locations"] = locations
            schema = schema_for(Feedback)
            requirement = schema["$defs"]["Requirement"]
            requirement["properties"]["locations"]["items"]["enum"] = locations
            del requirement["properties"]["id"]
            requirement["required"] = sorted({*requirement.get("required", ()), "situation"})
            known = known_ids(history)
            targets = [target.name for target in catalogue()]

            def accept(arguments):
                parsed = Feedback.model_validate(arguments)
                if any(set(item.locations) - set(locations) for item in parsed.requirements):
                    raise ValueError("feedback names a location outside the supplied deployment")
                parsed = identified(parsed, known)
                vet(parsed, signals, sessions, sealed=sealed, targets=targets, spoken=spoken)
                return parsed

            record["materials"] = packet
            _, feedback = await exchange(
                provider,
                messages(_PROMPT.read_text(), packet),
                [
                    record_tool(sessions),
                    tool(NAME, "Submit this round's decision and requirements.", schema),
                ],
                submit={NAME: accept},
                query={RECORDS: lambda arguments: read_records(sessions, arguments)},
                model=model,
                max_calls=limits.max_calls,
                timeout=limits.call_timeout,
                trace=trace,
                label="analyst",
            )
        record["feedback"] = feedback
        return feedback
    except Exception as exc:
        record["error"] = str(exc)
        raise
    finally:
        _write(worker.root / "analysis" / f"{uuid4().hex}.json", json.dumps(plain(record), ensure_ascii=False).encode())
