"""Shared, storage-independent admission, usage and bounded revision of role-owned experience."""

import copy
import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Check(Record):
    name: Literal["grounding", "applicability", "effect"]
    result: Literal["pass", "fail", "unknown"]
    evidence: tuple[str, ...] = ()
    reason: str = ""

    @model_validator(mode="after")
    def witnessed(self):
        if self.result == "pass" and (not self.evidence or any(not item.strip() for item in self.evidence)):
            raise ValueError("a passing admission check requires inspectable evidence")
        return self


class Experience(Record):
    domain: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    content: dict[str, JsonValue]
    sources: dict[str, str] = Field(min_length=1)
    replaces: tuple[str, ...] = ()
    diagnoses: tuple[str, ...] = ()

    @property
    def id(self) -> str:
        return fingerprint(self.model_dump(mode="json"))


class Issue(Record):
    target: str
    cause: Literal["content", "scope", "selection", "loading", "application", "execution", "evaluation", "evidence"]
    evidence: tuple[str, ...] = Field(min_length=1)
    reason: str = Field(min_length=1)
    fields: tuple[str, ...] = ()

    @model_validator(mode="after")
    def edit_authority(self):
        if self.cause not in {"content", "scope", "evidence"} and self.fields:
            raise ValueError("this diagnosis does not authorize changing experience content")
        if any(not item.strip() for item in self.evidence):
            raise ValueError("a diagnosis must name actual supporting records")
        if any(field not in {"scope", "sources"} and not field.startswith("content.") for field in self.fields):
            raise ValueError("revision fields must identify content, scope or source dependencies")
        if self.cause == "scope" and any(
            field not in {"scope", "sources"} and not field.startswith("content.") for field in self.fields
        ):
            raise ValueError("a scope diagnosis can change only applicability")
        if self.cause == "evidence" and any(field != "sources" for field in self.fields):
            raise ValueError("an evidence diagnosis can refresh only source dependencies")
        return self


class Diagnosis(Issue):
    baseline: str


class Decision(Record):
    candidate: str
    baseline: str
    policy: str = Field(min_length=1)
    context: str = Field(min_length=1)
    checks: tuple[Check, ...]

    @property
    def accepted(self) -> bool:
        return (
            len(self.checks) == 3
            and {check.name for check in self.checks} == {"grounding", "applicability", "effect"}
            and all(check.result == "pass" for check in self.checks)
        )


_MISSING = object()


def changed_fields(before, after, prefix="") -> set[str]:
    if isinstance(before, dict) and isinstance(after, dict):
        return {
            field
            for key in before.keys() | after.keys()
            for field in changed_fields(
                before.get(key, _MISSING), after.get(key, _MISSING), f"{prefix}.{key}" if prefix else key
            )
        }
    if before is _MISSING or after is _MISSING:
        return set() if before is after else {prefix}
    return set() if fingerprint(before) == fingerprint(after) else {prefix}


class Governance:
    """Pure transactions; callers durably save a changed copy before publishing it in memory."""

    def __init__(self, value: dict | None = None):
        self.data = copy.deepcopy(value or {"entries": {}, "decisions": [], "diagnoses": {}, "uses": {}, "revoked": {}})
        if set(self.data) != {"entries", "decisions", "diagnoses", "uses", "revoked"}:
            raise ValueError("unknown experience governance record shape")
        for identity, row in self.data["entries"].items():
            if Experience.model_validate(row["experience"]).id != identity:
                raise ValueError("experience content does not match its immutable identity")
            if row["state"] not in {"candidate", "active", "inactive"}:
                raise ValueError("invalid experience lifecycle state")
        for identity, row in self.data["diagnoses"].items():
            if fingerprint(Diagnosis.model_validate(row).model_dump(mode="json")) != identity:
                raise ValueError("experience diagnosis identity changed")
        receipts = {}
        for row in self.data["decisions"]:
            if "candidate" in row:
                decision = Decision.model_validate({key: value for key, value in row.items() if key != "accepted"})
                if decision.accepted != row["accepted"]:
                    raise ValueError("stored experience adoption disagrees with its checks")
                receipts[fingerprint(row)] = decision
        for identity, row in self.data["entries"].items():
            if row["state"] == "active":
                receipt = receipts.get(row.get("admission"))
                if receipt is None or receipt.candidate != identity or not receipt.accepted:
                    raise ValueError("active experience lacks an exact accepted admission")

    def record(self) -> dict:
        return copy.deepcopy(self.data)

    def clone(self):
        return Governance(self.record())

    def experience(self, identity: str) -> Experience:
        entry = Experience.model_validate(self.data["entries"][identity]["experience"])
        if entry.id != identity:
            raise ValueError("experience content changed without a new candidate")
        return entry

    def current(self, identity: str) -> bool:
        entry = self.experience(identity)
        return not any(version in self.data["revoked"].get(source, {}) for source, version in entry.sources.items())

    def active(self, domain: str, scope: str) -> tuple[str, ...]:
        return tuple(
            sorted(
                identity
                for identity, row in self.data["entries"].items()
                if row["state"] == "active"
                and row["experience"]["domain"] == domain
                and row["experience"]["scope"] in {scope, "*"}
                and self.current(identity)
            )
        )

    def version(self, domain: str, scope: str) -> str:
        return fingerprint(self.active(domain, scope))

    def diagnose(self, diagnosis: Diagnosis) -> str:
        entry = self.experience(diagnosis.target)
        if diagnosis.baseline != self.version(entry.domain, entry.scope):
            raise ValueError("experience diagnosis belongs to an obsolete baseline")
        identity = fingerprint(diagnosis.model_dump(mode="json"))
        self.data["diagnoses"][identity] = diagnosis.model_dump(mode="json")
        return identity

    def propose(self, experience: Experience) -> str:
        experience = Experience.model_validate(experience.model_dump(mode="json"))
        if any(not source or not version for source, version in experience.sources.items()):
            raise ValueError("experience sources require identities and versions")
        if len(set(experience.replaces)) != len(experience.replaces):
            raise ValueError("a replacement cannot name the same experience twice")
        if experience.id in self.data["entries"]:
            return experience.id
        if experience.replaces:
            diagnoses = [
                Diagnosis.model_validate(self.data["diagnoses"][identity]) for identity in experience.diagnoses
            ]
            if len(diagnoses) != len(experience.replaces) or {row.target for row in diagnoses} != set(
                experience.replaces
            ):
                raise ValueError("every revised experience requires its own diagnosed scope")
            for diagnosis in diagnoses:
                target = diagnosis.target
                previous = self.experience(target)
                if previous.domain != experience.domain:
                    raise ValueError("the revision targets another role")
                if diagnosis.baseline != self.version(previous.domain, previous.scope):
                    raise ValueError("revision permissions are stale")
                if self.data["entries"][target]["state"] == "candidate":
                    raise ValueError("an unadopted proposal cannot authorize an experience revision")
                if not any(row.get("candidate") == target and row.get("accepted") for row in self.data["decisions"]):
                    raise ValueError("a revised experience must have a prior accepted admission")
                changed = changed_fields(
                    {"content": previous.content, "scope": previous.scope, "sources": previous.sources},
                    {"content": experience.content, "scope": experience.scope, "sources": experience.sources},
                )
                if not changed or any(
                    not any(field == grant or field.startswith(grant + ".") for grant in diagnosis.fields)
                    for field in changed
                ):
                    raise ValueError("the revision exceeds its diagnosed fields or changes nothing")
        self.data["entries"][experience.id] = {
            "experience": experience.model_dump(mode="json"),
            "state": "candidate",
            "reason": "awaiting_verification",
        }
        return experience.id

    def decide(self, decision: Decision) -> bool:
        entry = self.experience(decision.candidate)
        if decision.baseline != self.version(entry.domain, entry.scope):
            raise ValueError("admission belongs to an obsolete experience baseline")
        if self.data["entries"][decision.candidate]["state"] != "candidate" or not self.current(decision.candidate):
            raise ValueError("only a current candidate can be admitted")
        for identity in entry.diagnoses:
            diagnosis = Diagnosis.model_validate(self.data["diagnoses"][identity])
            target = self.experience(diagnosis.target)
            if diagnosis.baseline != self.version(target.domain, target.scope):
                raise ValueError("revision permissions changed before admission")
        if any(
            self.data["entries"][target]["state"] == "candidate"
            or self.data["entries"][target].get("replacement") not in {None, entry.id}
            for target in entry.replaces
        ):
            raise ValueError("the replaced experience has a different successor or was never adopted")
        receipt = {**decision.model_dump(mode="json"), "accepted": decision.accepted}
        self.data["decisions"].append(receipt)
        if decision.accepted:
            for target in entry.replaces:
                self.data["entries"][target].update(state="inactive", reason="superseded", replacement=entry.id)
            self.data["entries"][entry.id].update(state="active", reason="verified", admission=fingerprint(receipt))
        return decision.accepted

    def deactivate(self, identity: str, *, reason: str, evidence: tuple[str, ...]) -> None:
        if not reason or not evidence:
            raise ValueError("deactivation requires a reason and supporting records")
        self.experience(identity)
        self.data["entries"][identity].update(state="inactive", reason=reason)
        self.data["decisions"].append({"deactivated": identity, "reason": reason, "evidence": list(evidence)})

    def revoke(self, source: str, version: str, *, reason: str) -> None:
        if not source or not version or not reason:
            raise ValueError("source revocation requires an exact source version and reason")
        self.data["revoked"].setdefault(source, {})[version] = reason
        for identity, row in self.data["entries"].items():
            if row["experience"]["sources"].get(source) == version:
                row.update(state="inactive", reason="source_revoked")
        self.data["decisions"].append({"revoked": source, "version": version, "reason": reason})

    def rollback(self, identity: str, *, baseline: str, policy: str, applicability: Check) -> None:
        entry = self.experience(identity)
        if baseline != self.version(entry.domain, entry.scope) or self.data["entries"][identity]["state"] != "active":
            raise ValueError("rollback must identify the current active experience and baseline")
        if applicability.name != "applicability" or applicability.result != "pass":
            raise ValueError("rollback requires a current applicability check")
        for previous in entry.replaces:
            old = self.data["entries"][previous]
            if old["reason"] != "superseded" or old.get("replacement") != identity or not self.current(previous):
                raise ValueError("a withdrawn or obsolete predecessor cannot be restored")
            if not any(
                row.get("candidate") == previous and row.get("policy") == policy and row.get("accepted")
                for row in self.data["decisions"]
            ):
                raise ValueError("the predecessor has no admission under the current policy")
        self.data["entries"][identity].update(state="inactive", reason="rolled_back")
        for previous in entry.replaces:
            self.data["entries"][previous].update(state="active", reason="restored")
        self.data["decisions"].append(
            {
                "rollback": identity,
                "restored": list(entry.replaces),
                "policy": policy,
                "applicability": applicability.model_dump(mode="json"),
            }
        )

    def capture(
        self,
        *,
        domain: str,
        scope: str,
        task: str,
        phase: str,
        inputs: str,
        policy: str,
        identities: tuple[str, ...],
        text: str,
        rendering: str,
    ) -> dict:
        if not all((domain, scope, task, phase, inputs, policy, rendering)):
            raise ValueError("experience usage must bind its consumer, inputs and policy")
        if len(set(identities)) != len(identities) or set(identities) - set(self.active(domain, scope)):
            raise ValueError("usage can include only distinct applicable active experiences")
        self._check_policy(identities, policy)
        value = {
            "domain": domain,
            "scope": scope,
            "task": task,
            "phase": phase,
            "inputs": inputs,
            "policy": policy,
            "identities": list(identities),
            "text": text,
            "rendering": rendering,
        }
        identity = fingerprint(value)
        self.data["uses"].setdefault(identity, {"snapshot": value, "observations": []})
        return {"id": identity, **copy.deepcopy(value)}

    def validate_use(
        self, snapshot: dict, *, domain: str, scope: str, inputs: str, policy: str, rendering: str
    ) -> None:
        content = {key: value for key, value in snapshot.items() if key != "id"}
        identity = fingerprint(content)
        if snapshot.get("id") != identity or self.data["uses"].get(identity, {}).get("snapshot") != content:
            raise ValueError("experience usage snapshot was changed or is unknown")
        if (content["domain"], content["scope"], content["inputs"], content["policy"], content["rendering"]) != (
            domain,
            scope,
            inputs,
            policy,
            rendering,
        ):
            raise ValueError("experience consumer, input or policy changed during recovery")
        if set(content["identities"]) - set(self.active(domain, scope)):
            raise ValueError("a used experience was withdrawn or is no longer applicable")
        self._check_policy(content["identities"], policy)

    def _check_policy(self, identities, policy):
        receipts = {fingerprint(row): row for row in self.data["decisions"] if "candidate" in row}
        if any(
            receipts.get(self.data["entries"][id].get("admission"), {}).get("policy") != policy for id in identities
        ):
            raise ValueError("experience was not adopted under the current policy")

    def observe(
        self, usage: str, *, evidence: str, result: Literal["applied", "not_applied", "unknown"], note: str
    ) -> None:
        if not evidence or not note or result not in {"applied", "not_applied", "unknown"}:
            raise ValueError("experience application requires an explicit observation")
        row = {"evidence": evidence, "result": result, "note": note}
        observations = self.data["uses"][usage]["observations"]
        if row not in observations:
            observations.append(row)
