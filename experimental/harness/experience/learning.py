"""Learn from completed Curator records and later authorized observations without reinjecting the current task."""

import fcntl
import json

from experimental.harness.experience.contracts import (
    ExperienceEvent,
    ExperienceProposal,
    OutcomeReceipt,
    RecordOrigin,
    digest,
)
from experimental.harness.experience.curator import PHASES
from experimental.harness.experience.records import RecordRejectedError, _check_text, normalize
from experimental.harness.experience.retrieve import GuidanceQuery
from experimental.harness.experience.verification import VALIDATING
from experimental.harness.raven_adapter.materialize import _write


def _episode_path(owner, reference):
    return (
        owner.store.path.parent
        / "episodes"
        / f"{digest({'scope': owner.access.access_scope, 'reference': reference})}.json"
    )


async def _extract(owner, event, *, capabilities=(), contract_ids=(), expected_version=None, usage=None):
    retained = owner.store.event(owner.access.access_scope, event.view.reference)
    previous = retained[1] if retained is not None else None
    if expected_version is not None and previous != expected_version:
        raise ValueError("the learning source changed before the new observation was recorded")
    if retained is not None and expected_version is None and retained[0] != event:
        old = retained[0]
        outcome_fields = {"held", "basis", "comparability", "observations"}
        if (
            old.origin != event.origin
            or old.source_digest != event.source_digest
            or old.view.model_dump(exclude=outcome_fields) != event.view.model_dump(exclude=outcome_fields)
        ):
            raise ValueError("changed source content requires an explicit current source version")
        event = old
    version = owner.store.ingest(event, expected_version=previous)
    episode = _episode_path(owner, event.view.reference)
    _write(
        episode,
        json.dumps(
            {
                "event": event.model_dump(mode="json"),
                "source_version": version,
                "access": owner.access.identity,
                "usage": usage,
                "capabilities": list(capabilities),
                "contract_ids": list(contract_ids),
            },
            ensure_ascii=False,
        ).encode(),
    )
    if owner.pipeline is None:
        return {"status": "recorded", "event": event.view.reference, "version": version}
    task_id = digest({"event": event.view.reference, "version": version, "scope": owner.access.access_scope})
    path = owner.store.path.parent / "learning" / f"{task_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if path.exists():
            frozen = json.loads(path.read_text())
            if frozen["event"] != event.model_dump(mode="json"):
                raise ValueError("the learning episode changed after its request was frozen")
            related = tuple(ExperienceProposal.model_validate(row) for row in frozen["related"])
            if frozen["capabilities"] != list(capabilities) or frozen["contract_ids"] != list(contract_ids):
                raise ValueError("host facts changed during experience learning recovery")
        else:
            related = []
            for phase in PHASES:
                query = GuidanceQuery(
                    access_scope=owner.access.access_scope,
                    situation=event.view.situation,
                    phase=phase,
                    scope_kind=event.view.scope_kind,
                    mechanism_states=(event.view.mechanism_state,) if event.view.mechanism_state else (),
                    capabilities=tuple(capabilities),
                    contract_ids=tuple(contract_ids),
                )
                for proposal in owner.reader.related(query):
                    if proposal not in related and len(related) < 8:
                        related.append(proposal)
            related = tuple(related)
            frozen = {
                "event": event.model_dump(mode="json"),
                "related": [row.model_dump(mode="json") for row in related],
                "capabilities": list(capabilities),
                "contract_ids": list(contract_ids),
                "usage": usage,
            }
            _write(path, json.dumps(frozen, ensure_ascii=False).encode())
    if usage is not None and hasattr(owner.pipeline.critic, "audit"):
        with path.with_suffix(".audit.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return {"status": "running", "event": event.view.reference, "stage": "audit"}
            frozen = json.loads(path.read_text())
            if not frozen.get("audit_done"):
                if frozen.get("audit_attempted"):
                    return {"status": "exhausted", "event": event.view.reference, "stage": "audit"}
                frozen["audit_attempted"] = True
                _write(path, json.dumps(frozen, ensure_ascii=False).encode())
                frozen["diagnoses"] = list(await owner.audit(usage, (event,)))
                frozen["audit_done"] = True
                _write(path, json.dumps(frozen, ensure_ascii=False).encode())
            ledger = owner.journal.read()
            actionable = [id for id in frozen.get("diagnoses", ()) if ledger.data["diagnoses"][id]["fields"]]
            if actionable:
                repaired = await owner.repair(
                    actionable[0], (event,), capabilities=tuple(capabilities), contract_ids=tuple(contract_ids)
                )
                return {"event": event.view.reference, "version": version, "audit": frozen["diagnoses"], **repaired}
    result = await owner.pipeline.run(
        (event,), task_id=task_id, related=related, capabilities=tuple(capabilities), contract_ids=tuple(contract_ids)
    )
    admission = owner.refresh()
    return {
        "status": result.state.status,
        "event": event.view.reference,
        "version": version,
        "task": result.task_id,
        "accepted_candidates": [row.model_dump() for row in result.state.accepted],
        "admission": admission,
    }


async def learn_record(owner, record: dict, *, origin: RecordOrigin, capabilities=(), contract_ids=()):
    if VALIDATING.get():
        return {"status": "validation_only", "reason": "Isolated method comparisons cannot write learning evidence."}
    if origin.access_scope != owner.access.access_scope:
        raise ValueError("a learning episode must have the consumer's explicit source grant")
    source = {
        key: record[key]
        for key in ("generated", "feedback", "error", "paused", "gap", "active_artifact_id", "changed", "child_changes")
        if key in record
    }
    try:
        event = normalize(source, origin=origin, access=owner.access)
    except RecordRejectedError as exc:
        return {"status": "not_applicable", "reason": str(exc)}
    result = await _extract(
        owner,
        event,
        capabilities=capabilities,
        contract_ids=contract_ids,
        usage=record.get("experience") or record.get("experience_scopes"),
    )
    return {**result, "origin": origin.model_dump(mode="json")}


async def observe_outcome(owner, reference: str, receipt: OutcomeReceipt, *, held_out: bool):
    if held_out or VALIDATING.get():
        return {"status": "validation_only", "reason": "Held-out observations do not enter the learning corpus."}
    path = _episode_path(owner, reference)
    packet = json.loads(path.read_text())
    if packet["access"] != owner.access.identity:
        raise ValueError("the learning source grant changed before outcome capture")
    event = ExperienceEvent.model_validate(packet["event"])
    origin = event.origin
    if (receipt.access_scope, receipt.revision_id, receipt.scope, receipt.input_key) != (
        owner.access.access_scope,
        event.revision_after,
        origin.scope,
        origin.input_key,
    ) or event.view.activation != "applied":
        raise ValueError("the outcome does not identify this actually applied curation")
    if "outcome.held" not in owner.access.fields:
        raise ValueError("the source grant does not permit learning from outcomes")
    observations = receipt.observations if "outcome.observations" in owner.access.fields else ()
    view = event.view.model_dump(mode="json")
    view.update(
        held=receipt.held,
        basis=receipt.basis if observations else "indirect",
        comparability=receipt.comparability,
        observations=observations,
    )
    updated = ExperienceEvent.model_validate({**event.model_dump(mode="json"), "view": view})
    _check_text(updated.view, owner.access)
    return await _extract(
        owner,
        updated,
        capabilities=packet["capabilities"],
        contract_ids=packet["contract_ids"],
        expected_version=packet["source_version"],
        usage=packet.get("usage"),
    )
