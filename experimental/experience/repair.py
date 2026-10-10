"""Diagnose and replace Curator methods under host-bound fields and independent targeted comparisons."""

from . import render
from .contracts import ExperienceProposal, RepairRequest, for_model
from .governance import Check, Decision, Diagnosis, Issue, fingerprint
from .state import CandidateRef
from .verification import Study, compare_methods

FIELDS = frozenset(
    {
        "content.guidance",
        "content.support_kind",
        "content.condition",
        *(
            "content.condition." + name
            for name in (
                "situation",
                "phase",
                "scope_kind",
                "mechanism_states",
                "required_capabilities",
                "contract_ids",
                "limits",
            )
        ),
    }
)


def diagnose(owner, issue: Issue, *, evidence: set[str]) -> str:
    if set(issue.evidence) - evidence or set(issue.fields) - FIELDS:
        raise ValueError("experience diagnosis needs supplied evidence and Curator-owned fields")
    if issue.cause == "scope" and any(not field.startswith("content.condition") for field in issue.fields):
        raise ValueError("an applicability issue cannot rewrite the method")

    def record(ledger):
        target = ledger.experience(issue.target)
        if target.domain != "curator" or target.scope != owner.access.access_scope:
            raise ValueError("the diagnosis targets another role or access scope")
        fields = (*issue.fields, "content.method", "sources") if issue.fields else ()
        bound = Diagnosis(
            **{**issue.model_dump(), "fields": fields}, baseline=ledger.version(target.domain, target.scope)
        )
        return ledger.diagnose(bound)

    return owner.journal.update(record)


async def audit(owner, snapshot, events):
    if owner.pipeline is None or not hasattr(owner.pipeline.critic, "audit"):
        return ()
    ledger = owner.journal.read()
    snapshots = snapshot if isinstance(snapshot, list) else [snapshot]
    for snapshot in snapshots:
        if not any(row.get("curator_usage") == snapshot for row in ledger.data["decisions"]):
            raise ValueError("an audit must use a host-recorded guidance snapshot")
    if any(event.origin.access_scope != owner.access.access_scope for event in events):
        raise ValueError("an audit cannot read another source scope")
    stages = [stage for snapshot in snapshots for stage in snapshot.get("stages", {}).values()]
    identities = {id for stage in stages for id in stage["usage"]["identities"]}
    methods = [{"target": id, "method": ledger.experience(id).content} for id in sorted(identities)[:8]]
    if any(ledger.experience(id).scope != owner.access.access_scope for id in identities):
        raise ValueError("an audit cannot target another experience scope")
    evidence = [for_model(event.view, "critic") for event in events]
    for stage in stages:
        use = ledger.data["uses"].get(stage["usage"]["id"])
        if use is None:
            raise ValueError("an experience audit must identify recorded usage")
        evidence.extend(
            {"reference": "evidence-" + fingerprint(row), "observation": row} for row in use["observations"]
        )
    if not methods or not evidence:
        return ()
    issues = await owner.pipeline.critic.audit(methods=methods, evidence=evidence)
    known = {row["reference"] for row in evidence}
    return tuple(diagnose(owner, issue, evidence=known) for issue in issues)


def attempts(ledger):
    return [row["repair_attempt"] for row in ledger.data["decisions"] if "repair_attempt" in row]


def pending_methods(owner, ledger):
    task_ids = {row["task"] for row in attempts(ledger)}
    return {row["id"] for row in owner.store.candidates(owner.access.access_scope) if row["task_id"] in task_ids} | {
        row["repair_candidate"]["native"]["id"] for row in ledger.data["decisions"] if "repair_candidate" in row
    }


async def propose(owner, diagnosis_id, events, *, capabilities=(), contract_ids=()):
    if owner.pipeline is None:
        raise ValueError("experience repair requires a configured construction and review pipeline")
    ledger = owner.journal.read()
    diagnosis = Diagnosis.model_validate(ledger.data["diagnoses"][diagnosis_id])
    target = ledger.experience(diagnosis.target)
    if target.scope != owner.access.access_scope or target.domain != "curator":
        raise ValueError("the repair belongs to another experience scope")
    if diagnosis.baseline != ledger.version(target.domain, target.scope):
        raise ValueError("the experience repair diagnosis is stale")
    fields = tuple(name.removeprefix("content.") for name in diagnosis.fields if name in FIELDS)
    if not fields:
        return {"status": "investigate", "diagnosis": diagnosis_id, "reason": "The diagnosis grants no method edits."}
    binding = owner._binding(CandidateRef.model_validate(target.content["method"]))
    request = RepairRequest(
        target=diagnosis.target,
        current=ExperienceProposal.model_validate(binding["proposal"]),
        fields=fields,
        reason=diagnosis.reason,
        evidence=diagnosis.evidence,
    )
    task = fingerprint(
        {
            "repair": diagnosis_id,
            "events": [event.model_dump(mode="json") for event in events],
            "capabilities": list(capabilities),
            "contracts": list(contract_ids),
        }
    )
    attempt = {"task": task, "diagnosis": diagnosis_id, "target": diagnosis.target, "baseline": diagnosis.baseline}

    def start(current):
        if current.version(target.domain, target.scope) != diagnosis.baseline:
            raise ValueError("the repair baseline changed before construction")
        if attempt not in attempts(current):
            current.data["decisions"].append({"repair_attempt": attempt})

    owner.journal.update(start)
    result = await owner.pipeline.run(
        tuple(events), task_id=task, repair=request, capabilities=tuple(capabilities), contract_ids=tuple(contract_ids)
    )
    if not result.state.accepted:
        return {"status": result.state.status, "diagnosis": diagnosis_id, "candidates": []}
    if len(result.state.accepted) != 1:
        raise ValueError("one bounded repair cannot publish several independent replacements")
    reference = result.state.accepted[0]
    replacement = owner._entry(owner._binding(reference)).model_copy(
        update={"replaces": (target.id,), "diagnoses": (diagnosis_id,)}
    )

    def register(current):
        identity = current.propose(replacement)
        row = {"task": task, "diagnosis": diagnosis_id, "candidate": identity, "native": reference.model_dump()}
        if not any(old.get("repair_candidate") == row for old in current.data["decisions"]):
            current.data["decisions"].append({"repair_candidate": row})
        return identity

    candidate = owner.journal.update(register)
    return {
        "status": "candidate",
        "diagnosis": diagnosis_id,
        "candidate": candidate,
        "native": reference.model_dump(),
        "task": task,
    }


def _texts(owner, ledger, candidate):
    entry = ledger.experience(candidate)
    targets = set(entry.replaces)
    related = []
    for use in reversed(list(ledger.data["uses"].values())):
        selected = use["snapshot"]
        if (
            selected["domain"] == entry.domain
            and selected["scope"] == entry.scope
            and targets & set(selected["identities"])
        ):
            related = [
                id
                for id in selected["identities"]
                if id not in targets and id in ledger.active(entry.domain, entry.scope)
            ]
            break

    def text(identities):
        items = {}
        for id in identities:
            content = ledger.experience(id).content
            native_id = content["method"]["id"]
            items.setdefault(native_id, {"id": native_id, "scope": entry.scope, **content})
        return render.guidance(list(items.values()))

    return text([*entry.replaces, *related]), text([candidate, *related])


def verification_context(owner, ledger, candidate):
    entry = ledger.experience(candidate)
    binding = owner._binding(CandidateRef.model_validate(entry.content["method"]))
    if (
        owner._entry(binding).sources != entry.sources
        or binding["review"]["decision"] != "accept"
        or not binding["current"]
        or set(binding["assessment"]["reasons"])
        & {"retired", "source_unavailable", "support_kind_required", "current_review_required"}
    ):
        raise ValueError("the repair candidate's sources or exact review changed")
    before, after = _texts(owner, ledger, candidate)
    return (
        before,
        after,
        fingerprint(
            {
                "baseline": ledger.version(entry.domain, entry.scope),
                "binding": binding,
                "candidate": candidate,
                "policy": owner.policy.id,
                "owner": owner.identity,
                "rendering": render.version(),
            }
        ),
    )


async def verify(owner, candidate, *, cases, evaluate, history=None, purpose="improvement", timeout=180):
    ledger = owner.journal.read()
    before, after, context = verification_context(owner, ledger, candidate)
    study = await compare_methods(
        before=before,
        after=after,
        context=context,
        cases=cases,
        evaluate=evaluate,
        history=history,
        purpose=purpose,
        timeout=timeout,
    )
    return admit(owner, candidate, study)


def admit(owner, candidate, study: Study):
    def commit(ledger):
        entry = ledger.experience(candidate)
        if not entry.replaces or not entry.diagnoses:
            raise ValueError("targeted verification must identify a diagnosed replacement")
        before, after, context = verification_context(owner, ledger, candidate)
        if (study.baseline, study.candidate, study.context) != (fingerprint(before), fingerprint(after), context):
            raise ValueError("the method comparison is for different instructions or dependencies")
        needed = {ref for id in entry.diagnoses for ref in ledger.data["diagnoses"][id]["evidence"]}
        reproduced = {
            ref
            for row in study.cases
            for ref in row.references
            if (row.before.satisfied is False and row.after.satisfied is True)
            or (row.before.preserved is False and row.after.preserved is True)
        }
        fixed = bool(needed & reproduced)
        accepted = study.accepted and fixed
        binding = owner._binding(CandidateRef.model_validate(entry.content["method"]))
        ledger.data["decisions"].append(
            {
                "repair_verification": {
                    "candidate": candidate,
                    "binding": fingerprint(binding),
                    "rendering": render.version(),
                    "owner": owner.identity,
                    "study": study.record(),
                }
            }
        )
        decision = Decision(
            candidate=candidate,
            baseline=ledger.version(entry.domain, entry.scope),
            policy=owner.policy.id,
            context=context,
            checks=(
                Check(name="grounding", result="pass", evidence=entry.diagnoses),
                Check(name="applicability", result="pass", evidence=(fingerprint(binding),)),
                Check(
                    name="effect",
                    result="pass" if accepted else "unknown",
                    evidence=(study.id,),
                    reason="The paired study must repair the diagnosed counterexample without regressions.",
                ),
            ),
        )
        adopted = ledger.decide(decision)
        return {"candidate": candidate, "accepted": adopted, "reproduced": fixed, "study": study.record()}

    return owner.journal.update(commit)


def verified(ledger, identity, binding, *, owner):
    for row in reversed(ledger.data["decisions"]):
        record = row.get("repair_verification")
        if (
            record
            and record["candidate"] == identity
            and record["binding"] == fingerprint(binding)
            and record["rendering"] == render.version()
            and record.get("owner") == owner
        ):
            raw = {key: value for key, value in record["study"].items() if key not in {"id", "accepted"}}
            study = Study.model_validate(raw)
            return study.accepted and study.id == record["study"]["id"]
    return False
