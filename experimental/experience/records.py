"""Adapt approved curation records without importing an alternative cultivation loop."""

import json
import unicodedata
from pathlib import Path
from typing import Literal

from experimental.experience.contracts import (
    RECORD_ONLY,
    Contract,
    EvidenceView,
    ExperienceEvent,
    NonemptyText,
    OutcomeReceipt,
    ProcessResult,
    RecordOrigin,
    digest,
)

type RecordField = Literal[
    "plan.understanding",
    "plan.design",
    "change.target",
    "change.reason",
    "change.treatment",
    "requirement.behavior",
    "requirement.observed",
    "requirement.acceptance",
    "feedback.reason",
    "outcome.held",
    "outcome.observations",
]


class RecordAccess(Contract):
    AUDIENCES = {"access_scope": RECORD_ONLY, "fields": RECORD_ONLY, "blocked_text": RECORD_ONLY}

    access_scope: NonemptyText
    fields: frozenset[RecordField] = frozenset()
    blocked_text: tuple[NonemptyText, ...] = ()

    @property
    def identity(self) -> str:
        return digest({"scope": self.access_scope, "fields": sorted(self.fields), "blocked": sorted(self.blocked_text)})


class RecordRejectedError(ValueError):
    """A source cannot be safely interpreted under its declared access."""


def _mapping(value) -> dict:
    return value if isinstance(value, dict) else {}


def _text(value) -> str:
    return value if isinstance(value, str) else ""


def _approved(access: RecordAccess, field: RecordField, value) -> str:
    return _text(value) if field in access.fields else ""


def _check_access(origin: RecordOrigin, access: RecordAccess) -> None:
    if origin.access_scope != access.access_scope or not access.fields:
        raise RecordRejectedError("a matching explicit source grant is required")


def _situation(plan: dict, feedback: dict, access: RecordAccess) -> str:
    parts = [_approved(access, "plan.understanding", plan.get("understanding"))]
    requirements = feedback.get("requirements", ())
    if isinstance(requirements, (list, tuple)):
        for value in requirements:
            requirement = _mapping(value)
            for name in ("behavior", "observed", "acceptance"):
                parts.append(_approved(access, f"requirement.{name}", requirement.get(name)))
    parts.append(_approved(access, "feedback.reason", feedback.get("reason")))
    return "\n".join(dict.fromkeys(part for part in parts if part.strip()))


def _treatment(plan: dict, access: RecordAccess) -> str:
    parts = []
    changes = plan.get("changes", ())
    if isinstance(changes, (list, tuple)):
        for value in changes:
            change = _mapping(value)
            fields = (
                _approved(access, "change.target", change.get("target")),
                _approved(access, "change.treatment", change.get("treatment")),
                _approved(access, "change.reason", change.get("reason")),
            )
            if any(fields):
                parts.append(": ".join(part for part in fields if part.strip()))
    if not parts:
        parts.append(_approved(access, "plan.design", plan.get("design")))
    return "\n".join(part for part in parts if part.strip())


def _process(record: dict, generated: dict, plan: dict) -> ProcessResult:
    if record.get("paused"):
        return "paused"
    if record.get("gap"):
        return "gap"
    if record.get("error"):
        return "failed"
    validation = _mapping(generated.get("validation"))
    errors = validation.get("errors")
    if isinstance(errors, (list, tuple)) and errors:
        return "failed"
    if "changes" in plan and not plan["changes"]:
        return "retained"
    if isinstance(errors, (list, tuple)):
        return "checked"
    return "generated"


def _activation(record: dict, candidate: dict, origin: RecordOrigin, process: ProcessResult) -> str:
    if process == "failed":
        return "unknown"
    if process in {"paused", "gap", "retained"}:
        return "not_applied"
    after = _text(record.get("active_artifact_id"))
    artifact = candidate.get("artifact")
    if not origin.revision_before or not after or not isinstance(artifact, dict) or record.get("composition"):
        return "unknown"
    if digest(artifact) == after and after != origin.revision_before:
        return "applied"
    return "not_applied" if after == origin.revision_before else "unknown"


def _outcome(
    origin: RecordOrigin, access: RecordAccess, after: str, activation: str, receipt: OutcomeReceipt | None
) -> dict:
    if receipt is None or activation != "applied" or "outcome.held" not in access.fields:
        return {}
    if (receipt.access_scope, receipt.revision_id, receipt.scope, receipt.input_key) != (
        origin.access_scope,
        after,
        origin.scope,
        origin.input_key,
    ):
        return {}
    observations = receipt.observations if "outcome.observations" in access.fields else ()
    basis = receipt.basis if receipt.basis == "indirect" or observations else "indirect"
    return {
        "held": receipt.held,
        "basis": basis,
        "comparability": receipt.comparability,
        "observations": observations,
    }


def _check_text(view: EvidenceView, access: RecordAccess) -> None:
    text = unicodedata.normalize("NFKC", json.dumps(view.model_dump(mode="json"), ensure_ascii=False)).casefold()
    if any(unicodedata.normalize("NFKC", item).casefold() in text for item in access.blocked_text):
        raise RecordRejectedError("the projected evidence contains blocked source text")


def normalize(
    record: dict, *, origin: RecordOrigin, access: RecordAccess, outcome: OutcomeReceipt | None = None
) -> ExperienceEvent:
    """Preserve one curation's joint treatment; absent before-state or outcome evidence stays unknown."""
    _check_access(origin, access)
    if origin.input_key != "curation":
        raise RecordRejectedError("legacy curation records do not prove per-input treatment associations")
    if not isinstance(record, dict):
        raise RecordRejectedError("a curation record must be an object")
    generated = _mapping(record.get("generated"))
    candidate = _mapping(generated.get("candidate"))
    plan = _mapping(candidate.get("plan"))
    feedback = _mapping(record.get("feedback"))
    situation, treatment = _situation(plan, feedback, access), _treatment(plan, access)
    children = record.get("child_changes")
    if isinstance(children, dict) and children:
        child_plans = [_mapping(_mapping(_mapping(value).get("candidate")).get("plan")) for value in children.values()]
        treatment = "\n".join(
            part
            for part in [
                treatment,
                *(
                    "Delegated treatment: " + _treatment(child, access)
                    for child in child_plans
                    if _treatment(child, access)
                ),
            ]
            if part
        )
        if not situation:
            situation = "\n".join(filter(None, (_situation(child, {}, access) for child in child_plans)))
        plan = {**plan, "changes": [*plan.get("changes", ()), *({} for _ in children)]}
    if not situation or not treatment:
        raise RecordRejectedError("approved context and treatment are required; missing history is not inferred")
    process = _process(record, generated, plan)
    activation = _activation(record, candidate, origin, process)
    after = _text(record.get("active_artifact_id"))
    if (
        isinstance(children, dict)
        and children
        and record.get("changed") is True
        and origin.revision_before
        and after
        and after != origin.revision_before
        and process not in {"failed", "paused", "gap"}
    ):
        activation = "applied"
    view = EvidenceView(
        reference="event-" + origin.event_id(),
        situation=situation,
        treatment=treatment,
        scope_kind="root" if origin.scope == "root" else "child",
        process_result=process,
        activation=activation,
        **_outcome(origin, access, after, activation, outcome),
    )
    _check_text(view, access)
    return ExperienceEvent(origin=origin, source_digest=digest(record), revision_after=after or None, view=view)


def read_record(
    path: Path,
    *,
    root: Path,
    origin: RecordOrigin,
    access: RecordAccess,
    outcome: OutcomeReceipt | None = None,
    max_bytes: int = 16 * 1024 * 1024,
) -> ExperienceEvent:
    """Read only explicitly rooted files; metadata and full source bodies remain outside model projections."""
    _check_access(origin, access)
    if type(max_bytes) is not int or max_bytes < 1:
        raise ValueError("the record byte limit must be positive")
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(Path(root).resolve()):
        raise RecordRejectedError("the curation record is outside its approved root")
    try:
        with resolved.open("rb") as stream:
            payload = stream.read(max_bytes + 1)
        if len(payload) > max_bytes:
            raise RecordRejectedError("the curation record exceeds its byte limit")
        record = json.loads(payload)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RecordRejectedError("the curation record is missing or unreadable") from exc
    return normalize(record, origin=origin, access=access, outcome=outcome)
