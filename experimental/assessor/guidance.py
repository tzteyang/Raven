"""Persist scoped construction principles and procedures with evidence-backed adoption and rollback history."""

import copy
import fcntl
import json
from collections.abc import Mapping
from pathlib import Path

from experimental.assessor.reviewer import GuidanceProposal
from experimental.assessor.validation import Validation, compare, fingerprint, input_identity
from experimental.curator.raven_adapter.materialize import _write
from experimental.experience import render
from experimental.experience.governance import Check, Decision, Diagnosis, Experience, Governance, Issue

POLICY = fingerprint({"domain": "rubric", "rule": "independent-improvement-without-regression", "version": 2})


def _proposal(value: GuidanceProposal) -> dict:
    content = value.model_dump(mode="json")
    if value.correction is None:
        content.pop("correction", None)
    return content


class GuidanceStore:
    """Local construction guidance; episode content remains in the existing evaluation records."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else None
        self.entries: dict[str, dict] = {}
        self.history: list[dict] = []
        self.used: set[str] = set()
        self.governance = Governance()
        self._disk_version = fingerprint(None)
        if self.path is not None and self.path.exists():
            value = json.loads(self.path.read_text())
            self._disk_version = fingerprint(value)
            self.entries = value["entries"]
            self.history = value["history"]
            self.used = set(value["used"])
            for id, row in self.entries.items():
                proposal = GuidanceProposal.model_validate(row["proposal"])
                if fingerprint(_proposal(proposal)) != id or row["state"] not in {
                    "candidate",
                    "active",
                    "retired",
                }:
                    raise ValueError("guidance contains an invalid identity or lifecycle state")
            if "governance" in value:
                if value.get("schema") != 2:
                    raise ValueError("unsupported governed guidance schema")
                self.governance = Governance(value["governance"])
                for id in self.entries:
                    self._reference(id)
            else:
                for row in self.entries.values():
                    proposal = GuidanceProposal.model_validate(row["proposal"])
                    entry = Experience(
                        domain="rubric",
                        scope=proposal.scope,
                        content={"kind": proposal.kind, "text": proposal.text},
                        sources=self._sources(proposal, row.get("episodes", {})),
                    )
                    row["governance_id"] = self.governance.propose(entry)
                    row["legacy_state"] = row["state"]
                    if row["state"] == "retired":
                        self.governance.deactivate(entry.id, reason="legacy_inactive", evidence=(id,))
                    else:
                        row["state"] = "candidate"

    @staticmethod
    def _sources(proposal, episodes):
        return {f"rubric:{id}": fingerprint(episodes.get(id, {"id": id})) for id in proposal.episodes}

    def _reference(self, id):
        row = self.entries[id]
        proposal = GuidanceProposal.model_validate(row["proposal"])
        entry = self.governance.experience(row["governance_id"])
        state = self.governance.data["entries"][entry.id]["state"]
        if (
            fingerprint(_proposal(proposal)) != id
            or entry.content != {"kind": proposal.kind, "text": proposal.text}
            or entry.scope != proposal.scope
            or entry.sources != self._sources(proposal, row.get("episodes", {}))
            or row["state"] != ("retired" if state == "inactive" else state)
        ):
            raise ValueError("validation does not identify a current guidance candidate")
        return entry.id

    @property
    def version(self) -> str:
        for id in self.entries:
            self._reference(id)
        return fingerprint(
            {
                "policy": POLICY,
                "rendering": render.version(),
                "active": {id: row["proposal"] for id, row in self.entries.items() if row["state"] == "active"},
            }
        )

    def propose(self, proposal: GuidanceProposal, *, episodes: set[str]) -> str:
        if set(proposal.episodes) - set(episodes):
            raise ValueError("guidance must refer to retained evaluation episodes")
        if proposal.replaces is not None and (
            proposal.replaces not in self.entries or self.entries[proposal.replaces]["state"] == "candidate"
        ):
            raise ValueError("guidance can replace only an active, previously validated entry")
        for id, row in self.entries.items():
            old = row["proposal"]
            if row["state"] != "retired" and (old["kind"], old["scope"], " ".join(old["text"].split())) == (
                proposal.kind,
                proposal.scope,
                " ".join(proposal.text.split()),
            ):
                return id
        content = _proposal(proposal)
        id = fingerprint(content)
        if id not in self.entries:
            retained = (
                {key: copy.deepcopy(episodes[key]) for key in proposal.episodes}
                if isinstance(episodes, Mapping)
                else {}
            )
            governance = self.governance.clone()
            replaces, diagnoses = (), ()
            if proposal.replaces is not None:
                target = self._reference(proposal.replaces)
                prior = governance.experience(target)
                correction = proposal.correction
                choices = [
                    (id, row)
                    for id, row in governance.data["diagnoses"].items()
                    if row["target"] == target and row["baseline"] == governance.version(prior.domain, prior.scope)
                ]
                if choices:
                    permission, allowed = choices[-1]
                    requested = (
                        {"scope" if name == "scope" else "content." + name for name in correction.fields}
                        if correction
                        else set()
                    )
                    if correction and (correction.cause != allowed["cause"] or requested - set(allowed["fields"])):
                        raise ValueError("an inline correction cannot expand the recorded diagnosis")
                elif correction is not None:
                    if correction.cause == "scope" and any(field != "scope" for field in correction.fields):
                        raise ValueError("a scope correction cannot rewrite guidance content")
                    fields = tuple("scope" if name == "scope" else "content." + name for name in correction.fields)
                    if correction.cause in {"content", "scope"}:
                        fields = (*fields, "sources")
                    diagnosis = Diagnosis(
                        target=target,
                        baseline=governance.version(prior.domain, prior.scope),
                        cause=correction.cause,
                        evidence=proposal.episodes,
                        reason=correction.reason,
                        fields=fields,
                    )
                    permission = governance.diagnose(diagnosis)
                else:
                    raise ValueError("a guidance revision needs an evidenced diagnosis and permitted fields")
                replaces, diagnoses = (target,), (permission,)
            elif proposal.correction is not None:
                raise ValueError("a guidance correction must identify the method it revises")
            entry = Experience(
                domain="rubric",
                scope=proposal.scope,
                content={"kind": proposal.kind, "text": proposal.text},
                sources=self._sources(proposal, retained),
                replaces=replaces,
                diagnoses=diagnoses,
            )
            reference = governance.propose(entry)
            self._store(
                {
                    **self.entries,
                    id: {"proposal": content, "state": "candidate", "episodes": retained, "governance_id": reference},
                },
                self.history,
                self.used,
                governance=governance,
            )
        return id

    def diagnose(self, issue: Issue, *, episodes: set[str]) -> str:
        if set(issue.evidence) - set(episodes) or set(issue.fields) - {"content.text", "content.kind", "scope"}:
            raise ValueError("guidance diagnoses require known episodes and role-owned fields")
        if issue.cause == "scope" and any(field != "scope" for field in issue.fields):
            raise ValueError("a guidance scope diagnosis cannot rewrite the method")
        target = self._reference(issue.target)
        entry = self.governance.experience(target)
        fields = (*issue.fields, "sources") if issue.cause in {"content", "scope"} else issue.fields
        diagnosis = Diagnosis(
            **{**issue.model_dump(), "target": target, "fields": fields},
            baseline=self.governance.version(entry.domain, entry.scope),
        )
        governance = self.governance.clone()
        identity = governance.diagnose(diagnosis)
        entries = copy.deepcopy(self.entries)
        if isinstance(episodes, Mapping):
            for id in issue.evidence:
                entries[issue.target].setdefault("episodes", {}).setdefault(id, copy.deepcopy(episodes[id]))
        self._store(entries, self.history, self.used, governance=governance)
        return identity

    def selected(self, scope: str, *, candidate: str | None = None) -> list[dict]:
        for id in self.entries:
            self._reference(id)
        rows = {
            id: row["proposal"]
            for id, row in self.entries.items()
            if row["state"] == "active" and row["proposal"]["scope"] in (scope, "*")
        }
        if candidate is not None:
            proposed = self.entries[candidate]["proposal"]
            if proposed["scope"] not in (scope, "*"):
                raise ValueError("candidate guidance does not apply to this scope")
            rows.pop(proposed["replaces"], None)
            rows[candidate] = proposed
        ordered = sorted(rows, key=lambda id: (rows[id]["kind"] == "procedure", id))
        if candidate is not None and candidate not in ordered[:8]:
            raise ValueError("candidate exceeds the instruction selection budget; consolidate existing guidance")
        return [{"id": id, **rows[id]} for id in ordered[:8]]

    def open_issues(self, scope: str):
        references = {
            row["governance_id"]: id for id, row in self.entries.items() if row["proposal"]["scope"] in {scope, "*"}
        }
        latest = {}
        for row in self.governance.data["diagnoses"].values():
            if row["target"] not in references:
                continue
            state = self.governance.data["entries"][row["target"]]
            if state.get("replacement") in self.governance.active("rubric", scope):
                continue
            id = references[row["target"]]
            latest[id] = {
                "target": id,
                "cause": row["cause"],
                "evidence": row["evidence"],
                "reason": row["reason"],
                "method": self.entries[id]["proposal"],
                "state": state["state"],
            }
        return list(latest.values())[-8:]

    def review_history(self, scope: str, history):
        archived = {
            id: value
            for row in self.entries.values()
            if row["proposal"]["scope"] in {scope, "*"}
            for id, value in row.get("episodes", {}).items()
        }
        requested = [id for issue in self.open_issues(scope) for id in issue["evidence"]]
        selected = {row["id"]: row for row in history[-3:]}
        for id in requested:
            if id in archived:
                selected[id] = archived[id]
        return list(selected.values())[-3:]

    def render(self, scope: str, *, candidate: str | None = None) -> str:
        return render.guidance(self.selected(scope, candidate=candidate))

    def adopt(self, validation: Validation, *, input_suite: str | None = None, scope: str | None = None) -> bool:
        if validation.baseline != self.version:
            raise ValueError("guidance changed since validation; the receipt is stale")
        row = self.entries[validation.candidate]
        if fingerprint(row["proposal"]) != validation.candidate or row["state"] != "candidate":
            raise ValueError("validation does not identify a current guidance candidate")
        if (row["proposal"]["scope"] == "*") != validation.cross_task:
            raise ValueError("validation did not cover the proposed scope")
        scope = scope or row["proposal"]["scope"]
        if row["proposal"]["scope"] not in {scope, "*"}:
            raise ValueError("the verification consumer is outside the guidance scope")
        if (validation.before_instructions, validation.after_instructions) != (
            fingerprint(self.render(scope)),
            fingerprint(self.render(scope, candidate=validation.candidate)),
        ):
            raise ValueError("validation did not evaluate the actual guidance instructions")
        entries = copy.deepcopy(self.entries)
        reference = self._reference(validation.candidate)
        governance = self.governance.clone()
        proposal = GuidanceProposal.model_validate(row["proposal"])
        check_record = fingerprint(validation.record())
        accepted = governance.decide(
            Decision(
                candidate=reference,
                baseline=governance.version("rubric", proposal.scope),
                policy=POLICY,
                context=fingerprint({"comparison": validation.record(), "rendering": render.version()}),
                checks=(
                    Check(name="grounding", result="pass", evidence=proposal.episodes),
                    Check(name="applicability", result="pass", evidence=(check_record,)),
                    Check(
                        name="effect",
                        result="pass" if validation.accepted else "unknown",
                        evidence=(check_record,),
                        reason="Independent positive and negative replays must improve without regression.",
                    ),
                ),
            )
        )
        receipt = validation.record()
        if input_suite is not None:
            receipt["input_suite"] = input_suite
        used = {key for row in validation.comparisons for key in (row.evidence, row.input_key) if key}
        self._store(entries, [*self.history, receipt], self.used | used, governance=governance)
        return accepted

    def rollback_instructions(self, id: str) -> str:
        row = self.entries[id]
        previous = row["proposal"]["replaces"]
        rows = [item for item in self.selected(row["proposal"]["scope"]) if item["id"] != id]
        if previous is not None:
            rows.append({"id": previous, **self.entries[previous]["proposal"]})
        return render.guidance(rows)

    def rollback(self, id: str, *, validation: Validation | None = None) -> None:
        row = self.entries[id]
        if row["state"] != "active":
            raise ValueError("only active guidance can be rolled back")
        entries = copy.deepcopy(self.entries)
        reference = self._reference(id)
        scope = row["proposal"]["scope"]
        previous = row["proposal"]["replaces"]
        evidence = (self.version,)
        if previous is not None:
            if (
                validation is None
                or not validation.accepted
                or validation.baseline != self.version
                or validation.candidate != previous
                or any(item.after != item.expected for item in validation.comparisons)
                or validation.before_instructions != fingerprint(self.render(scope))
                or validation.after_instructions != fingerprint(self.rollback_instructions(id))
                or validation.cross_task != (self.entries[previous]["proposal"]["scope"] == "*")
            ):
                raise ValueError("restoring a predecessor requires current independent verification")
            evidence = (fingerprint(validation.record()),)
        governance = self.governance.clone()
        governance.rollback(
            reference,
            baseline=governance.version("rubric", scope),
            policy=POLICY,
            applicability=Check(name="applicability", result="pass", evidence=evidence),
        )
        receipt = {"rollback": id, "restored": previous}
        if validation is not None:
            receipt["validation"] = validation.record()
        self._store(entries, [*self.history, receipt], self.used, governance=governance)

    def capture(self, scope: str, *, task: str, inputs: str) -> dict:
        governance = self.governance.clone()
        selected = self.selected(scope)
        snapshot = governance.capture(
            domain="rubric",
            scope=scope,
            task=task,
            phase="construct",
            inputs=inputs,
            policy=POLICY,
            identities=tuple(self._reference(row["id"]) for row in selected),
            text=self.render(scope),
            rendering=render.version(),
        )
        self._store(self.entries, self.history, self.used, governance=governance)
        return snapshot

    def validate_usage(self, snapshot: dict, *, scope: str, inputs: str) -> None:
        current = self
        if self.path is not None and fingerprint(json.loads(self.path.read_text())) != self._disk_version:
            current = GuidanceStore(self.path)
        current.governance.validate_use(
            snapshot, domain="rubric", scope=scope, inputs=inputs, policy=POLICY, rendering=render.version()
        )

    def revoke_episode(self, id: str, *, reason: str) -> None:
        governance = self.governance.clone()
        for row in self.entries.values():
            source = "rubric:" + id
            entry = governance.experience(row["governance_id"])
            if source in entry.sources:
                governance.revoke(source, entry.sources[source], reason=reason)
        self._store(self.entries, self.history, self.used, governance=governance)

    def record(self) -> dict:
        return {
            "schema": 2,
            "entries": copy.deepcopy(self.entries),
            "history": copy.deepcopy(self.history),
            "used": sorted(self.used),
            "version": self.version,
            "governance": self.governance.record(),
        }

    def _store(self, entries, history, used, *, governance=None) -> None:
        governance = governance or self.governance
        entries = copy.deepcopy(entries)
        for row in entries.values():
            state = governance.data["entries"][row["governance_id"]]["state"]
            row["state"] = "retired" if state == "inactive" else state
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.with_suffix(".lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                current = json.loads(self.path.read_text()) if self.path.exists() else None
                if fingerprint(current) != self._disk_version:
                    raise ValueError("guidance was updated by another run; reopen the store before learning")
                value = {
                    "schema": 2,
                    "entries": entries,
                    "history": history,
                    "used": sorted(used),
                    "governance": governance.record(),
                }
                _write(self.path, json.dumps(value, ensure_ascii=False, indent=2).encode())
                self._disk_version = fingerprint(value)
        self.entries, self.history, self.used = entries, history, set(used)
        self.governance = governance

    async def consider(self, proposals, *, episodes, scope, cases, evaluate, task=None, diagnoses=()) -> None:
        known = {
            id: value
            for row in self.entries.values()
            if row["proposal"]["scope"] in {scope, "*"}
            for id, value in row.get("episodes", {}).items()
        }
        known.update({episode["id"]: episode for episode in episodes})
        for issue in diagnoses:
            self.diagnose(issue, episodes=known)
        for proposal in proposals:
            self.propose(proposal, episodes=known)
        pending = [
            id
            for id, row in self.entries.items()
            if row["state"] == "candidate" and row["proposal"]["scope"] in (scope, "*")
        ]
        if not pending or not cases:
            return
        for id in pending:
            selected = tuple(
                case
                for case in cases
                if task is None or self.entries[id]["proposal"]["scope"] == "*" or case.task == task
            )
            suite = fingerprint([{"id": case.id, "evidence": case.evidence()} for case in selected])
            if selected and not any(
                row.get("candidate") == id and row.get("input_suite") == suite and row.get("baseline") == self.version
                for row in self.history
            ):
                break
        else:
            return
        validation = await compare(
            candidate=id,
            baseline=self.version,
            before=self.render(scope),
            after=self.render(scope, candidate=id),
            cases=selected,
            evaluate=evaluate,
            cross_task=self.entries[id]["proposal"]["scope"] == "*",
            seen={
                key
                for episode in episodes
                for key in (fingerprint(episode["evidence"]), input_identity(episode["evidence"]))
            },
            used=self.used,
        )
        self.adopt(validation, input_suite=suite, scope=scope)
