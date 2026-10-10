"""Store source snapshots, bounded tasks and reviewed candidates with transactional ownership."""

import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from experimental.experience.admission import (
    AdmissionAssessment,
    AdmissionPolicy,
    LinkedEvidence,
    ProcessCheckReceipt,
    ReviewedVersion,
    assess_family,
    method_id,
)
from experimental.experience.contracts import ExperienceEvent, ExperienceProposal, ExperienceReview, digest, for_model
from experimental.experience.state import BuildState, CandidateRef

SCHEMA_VERSION = 2
_SCHEMA = (
    "CREATE TABLE events (scope TEXT, id TEXT, view_digest TEXT, source_digest TEXT, version INTEGER, payload TEXT, revoked INTEGER DEFAULT 0, PRIMARY KEY(scope,id))",
    "CREATE TABLE tasks (id TEXT PRIMARY KEY, scope TEXT, input_id TEXT, identities TEXT, snapshots TEXT, state TEXT, version INTEGER, lease TEXT, expires REAL, sources TEXT)",
    "CREATE TABLE candidates (scope TEXT, id TEXT, version INTEGER, proposal_digest TEXT, proposal TEXT, review TEXT, identities TEXT, task_id TEXT, status TEXT, PRIMARY KEY(scope,id,version))",
    "CREATE TABLE links (scope TEXT, candidate_id TEXT, candidate_version INTEGER, event_id TEXT, view_digest TEXT, relation TEXT, event_version INTEGER, PRIMARY KEY(scope,candidate_id,candidate_version,event_id))",
    "CREATE TABLE admissions (scope TEXT, id TEXT, version INTEGER, policy_id TEXT, assessment TEXT, PRIMARY KEY(scope,id,version))",
    "CREATE TABLE process_checks (scope TEXT, method_id TEXT, event_id TEXT, event_version INTEGER, receipt TEXT, PRIMARY KEY(scope,method_id,event_id,event_version))",
)
_COLUMNS = {
    "events": ("scope", "id", "view_digest", "source_digest", "version", "payload", "revoked"),
    "tasks": ("id", "scope", "input_id", "identities", "snapshots", "state", "version", "lease", "expires", "sources"),
    "candidates": (
        "scope",
        "id",
        "version",
        "proposal_digest",
        "proposal",
        "review",
        "identities",
        "task_id",
        "status",
    ),
    "links": ("scope", "candidate_id", "candidate_version", "event_id", "view_digest", "relation", "event_version"),
    "admissions": ("scope", "id", "version", "policy_id", "assessment"),
    "process_checks": ("scope", "method_id", "event_id", "event_version", "receipt"),
}


class StoreError(RuntimeError):
    """A task or source cannot be changed under the current store state."""


class BindingMismatchError(StoreError):
    """A continuation changed the inputs or model identity of its saved task."""


class StoreConflictError(StoreError):
    """An active owner, newer source or unexpected version blocks this write."""


@dataclass(frozen=True)
class TaskHandle:
    id: str
    scope: str
    version: int
    lease: str
    snapshots: dict[str, str]
    identities: dict
    sources: dict[str, int]


class ExperienceStore:
    def __init__(self, path: Path, *, timeout: float = 1, migrate: bool = False):
        path = Path(path)
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, timeout=timeout)
        self.connection.row_factory = sqlite3.Row
        try:
            with self._transaction():
                version = self.connection.execute("PRAGMA user_version").fetchone()[0]
                tables = {
                    row[0] for row in self.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
                }
                if version not in (0, 1, SCHEMA_VERSION) or (version == 0 and tables):
                    raise StoreError("unsupported experience database schema; no migration was performed")
                if version == 0:
                    for statement in _SCHEMA:
                        self.connection.execute(statement)
                    self.connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
                elif version == 1:
                    if not migrate:
                        raise StoreError("experience schema 1 requires explicit migration")
                    self._check_schema(legacy=True)
                    self._migrate()
                self._check_schema()
        except BaseException:
            self.connection.close()
            raise

    def _check_schema(self, *, legacy: bool = False) -> None:
        expected = dict(_COLUMNS)
        if legacy:
            expected.pop("admissions")
            expected.pop("process_checks")
            for table in ("events", "tasks", "links"):
                expected[table] = expected[table][:-1]
        tables = {row[0] for row in self.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if tables != set(expected) or any(
            tuple(row[1] for row in self.connection.execute(f"PRAGMA table_info({table})")) != columns
            for table, columns in expected.items()
        ):
            raise StoreError("experience database tables do not match its schema")

    def _migrate(self) -> None:
        self.connection.execute("ALTER TABLE events ADD COLUMN revoked INTEGER DEFAULT 0")
        self.connection.execute("ALTER TABLE tasks ADD COLUMN sources TEXT")
        self.connection.execute("ALTER TABLE links ADD COLUMN event_version INTEGER")
        self.connection.execute(_SCHEMA[-2])
        self.connection.execute(_SCHEMA[-1])
        self.connection.execute(
            "UPDATE links SET event_version=(SELECT version FROM events WHERE events.scope=links.scope AND events.id=links.event_id)"
        )
        for task in self.connection.execute("SELECT id,scope,snapshots FROM tasks").fetchall():
            sources = {}
            for reference in json.loads(task["snapshots"]):
                row = self.connection.execute(
                    "SELECT version FROM events WHERE scope=? AND id=?", (task["scope"], reference)
                ).fetchone()
                sources[reference] = row[0] if row else 0
            self.connection.execute("UPDATE tasks SET sources=? WHERE id=?", (json.dumps(sources), task["id"]))
        self.connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    def close(self) -> None:
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def event_version(self, event: ExperienceEvent) -> int | None:
        row = self.connection.execute(
            "SELECT version FROM events WHERE scope=? AND id=?", (event.origin.access_scope, event.view.reference)
        ).fetchone()
        return row[0] if row else None

    def event(self, access_scope: str, reference: str) -> tuple[ExperienceEvent, int] | None:
        row = self.connection.execute(
            "SELECT payload,version,revoked FROM events WHERE scope=? AND id=?", (access_scope, reference)
        ).fetchone()
        if row is None:
            return None
        if row["revoked"]:
            raise StoreConflictError("a revoked source cannot be used for learning")
        event = ExperienceEvent.model_validate_json(row["payload"])
        if event.origin.access_scope != access_scope or event.view.reference != reference:
            raise StoreError("the source record identity changed")
        return event, row["version"]

    @contextmanager
    def _transaction(self):
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.connection.commit()
        except BaseException:
            self.connection.rollback()
            raise

    def ingest(self, event: ExperienceEvent, *, expected_version: int | None = None) -> int:
        with self._transaction():
            return self._ingest(event, expected_version=expected_version)

    def _ingest(self, event: ExperienceEvent, *, expected_version: int | None = None) -> int:
        event = ExperienceEvent.model_validate(event.model_dump(mode="json"))
        scope, reference = event.origin.access_scope, event.view.reference
        view_digest = digest(for_model(event.view, "builder"))
        payload = event.model_dump_json()
        row = self.connection.execute("SELECT * FROM events WHERE scope=? AND id=?", (scope, reference)).fetchone()
        if row and row["revoked"]:
            raise StoreConflictError("a revoked source cannot be restored by ingestion")
        if row and expected_version is not None and expected_version != row["version"]:
            raise StoreConflictError("the expected source version is no longer current")
        if row and row["payload"] == payload:
            return row["version"]
        if row:
            if expected_version != row["version"]:
                raise StoreConflictError("source changed; an explicit current event version is required")
            version = row["version"] + 1
            self._invalidate_source(scope, reference)
            changed = self.connection.execute(
                "UPDATE events SET view_digest=?,source_digest=?,version=?,payload=? WHERE scope=? AND id=? AND version=?",
                (view_digest, event.source_digest, version, payload, scope, reference, row["version"]),
            ).rowcount
            if changed != 1:
                raise StoreConflictError("the source was updated concurrently")
            return version
        if expected_version is not None:
            raise StoreConflictError("the expected source version does not exist")
        self.connection.execute(
            "INSERT INTO events VALUES (?,?,?,?,?,?,?)",
            (scope, reference, view_digest, event.source_digest, 1, payload, 0),
        )
        return 1

    def open_task(
        self, task_id: str, input_id: str, identities: dict, events: tuple[ExperienceEvent, ...], *, ttl: float
    ) -> tuple[TaskHandle | None, BuildState]:
        scope = events[0].origin.access_scope
        if any(event.origin.access_scope != scope for event in events):
            raise StoreError("a construction task cannot mix access scopes")
        snapshots = {event.view.reference: digest(for_model(event.view, "builder")) for event in events}
        with self._transaction():
            row = self.connection.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row and (row["input_id"] != input_id or row["scope"] != scope):
                raise BindingMismatchError("task inputs or model identities changed; its saved progress was preserved")
            if row:
                state = BuildState.model_validate_json(row["state"])
                if row["lease"] and row["expires"] > time.time():
                    raise StoreConflictError("the construction task already has an active owner")
                sources = json.loads(row["sources"])
                for reference, view_digest in snapshots.items():
                    current = self.connection.execute(
                        "SELECT view_digest,version,revoked,payload FROM events WHERE scope=? AND id=?",
                        (scope, reference),
                    ).fetchone()
                    event = next(event for event in events if event.view.reference == reference)
                    if (
                        current is None
                        or current["view_digest"] != view_digest
                        or current["version"] != sources.get(reference)
                        or current["revoked"]
                        or current["payload"] != event.model_dump_json()
                    ):
                        raise StoreConflictError("task evidence changed; saved progress cannot publish against it")
                if state.status in {"complete", "rejected"}:
                    return None, state
                version = row["version"]
            else:
                sources = {}
                for event in events:
                    sources[event.view.reference] = self._ingest(event)
                state, version = BuildState(), 0
                self.connection.execute(
                    "INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        task_id,
                        scope,
                        input_id,
                        json.dumps(identities),
                        json.dumps(snapshots),
                        state.model_dump_json(),
                        version,
                        None,
                        0,
                        json.dumps(sources),
                    ),
                )
            lease = uuid4().hex
            changed = self.connection.execute(
                "UPDATE tasks SET lease=?,expires=?,version=version+1 WHERE id=? AND version=? AND (lease IS NULL OR expires<=?)",
                (lease, time.time() + ttl, task_id, version, time.time()),
            ).rowcount
            if changed != 1:
                raise StoreConflictError("the construction task was claimed concurrently")
        return TaskHandle(task_id, scope, version + 1, lease, snapshots, identities, sources), state

    def save(
        self,
        handle: TaskHandle,
        state: BuildState,
        *,
        ttl: float,
        finish: bool = False,
        accepted: tuple[tuple[ExperienceProposal, ExperienceReview], ...] = (),
    ) -> tuple[TaskHandle, BuildState]:
        with self._transaction():
            row = self.connection.execute("SELECT version,lease FROM tasks WHERE id=?", (handle.id,)).fetchone()
            if row is None or row["version"] != handle.version or row["lease"] != handle.lease:
                raise StoreConflictError("task ownership or version changed before save")
            references = list(state.accepted)
            for proposal, review in accepted:
                index = review.proposal_index
                if index >= len(state.proposals) or state.proposals[index] != proposal or review not in state.reviews:
                    raise StoreError("a review must match its exact proposal in the saved submission")
                reference = self._candidate(handle, proposal, review)
                if reference not in references:
                    references.append(reference)
            state = state.model_copy(update={"accepted": tuple(references)})
            changed = self.connection.execute(
                "UPDATE tasks SET state=?,version=version+1,lease=?,expires=? WHERE id=? AND version=? AND lease=?",
                (
                    state.model_dump_json(),
                    None if finish else handle.lease,
                    0 if finish else time.time() + ttl,
                    handle.id,
                    handle.version,
                    handle.lease,
                ),
            ).rowcount
            if changed != 1:
                raise StoreConflictError("the task changed concurrently")
        updated = TaskHandle(
            handle.id,
            handle.scope,
            handle.version + 1,
            handle.lease,
            handle.snapshots,
            handle.identities,
            handle.sources,
        )
        return updated, state

    def _candidate(self, handle: TaskHandle, proposal: ExperienceProposal, review: ExperienceReview) -> CandidateRef:
        if review.decision != "accept":
            raise StoreError("only an accepting exact-version review can enter the candidate store")
        links = []
        for link in proposal.evidence:
            view_digest = handle.snapshots.get(link.reference)
            row = self.connection.execute(
                "SELECT view_digest,version,revoked FROM events WHERE scope=? AND id=?", (handle.scope, link.reference)
            ).fetchone()
            if (
                view_digest is None
                or row is None
                or row["view_digest"] != view_digest
                or row["version"] != handle.sources.get(link.reference)
                or row["revoked"]
            ):
                raise StoreConflictError("candidate evidence is missing, foreign or changed after review")
            links.append((link.reference, view_digest, link.relation, row["version"]))
        candidate_id = method_id(handle.scope, proposal)
        proposal_digest = digest(
            {"proposal": proposal.model_dump(), "views": links, "critic": handle.identities["critic"]}
        )
        existing = self.connection.execute(
            "SELECT version FROM candidates WHERE scope=? AND id=? AND proposal_digest=? AND status!='retired'",
            (handle.scope, candidate_id, proposal_digest),
        ).fetchone()
        if existing:
            return CandidateRef(id=candidate_id, version=existing[0])
        version = self.connection.execute(
            "SELECT COALESCE(MAX(version),0)+1 FROM candidates WHERE scope=? AND id=?", (handle.scope, candidate_id)
        ).fetchone()[0]
        self.connection.execute(
            "INSERT INTO candidates VALUES (?,?,?,?,?,?,?,?,?)",
            (
                handle.scope,
                candidate_id,
                version,
                proposal_digest,
                proposal.model_dump_json(),
                review.model_dump_json(),
                json.dumps(handle.identities),
                handle.id,
                "candidate",
            ),
        )
        for reference, view_digest, relation, event_version in links:
            self.connection.execute(
                "INSERT INTO links VALUES (?,?,?,?,?,?,?)",
                (handle.scope, candidate_id, version, reference, view_digest, relation, event_version),
            )
        self._invalidate_method(handle.scope, candidate_id)
        return CandidateRef(id=candidate_id, version=version)

    def _invalidate_method(self, access_scope: str, candidate_id: str) -> None:
        self.connection.execute("DELETE FROM admissions WHERE scope=? AND id=?", (access_scope, candidate_id))
        self.connection.execute(
            "UPDATE candidates SET status='candidate' WHERE scope=? AND id=? AND status!='retired'",
            (access_scope, candidate_id),
        )

    def _invalidate_source(self, access_scope: str, reference: str) -> None:
        identities = self.connection.execute(
            "SELECT DISTINCT candidate_id FROM links WHERE scope=? AND event_id=?", (access_scope, reference)
        ).fetchall()
        self.connection.execute(
            "UPDATE candidates SET status='retired' WHERE scope=? AND (id,version) IN "
            "(SELECT candidate_id,candidate_version FROM links WHERE scope=? AND event_id=?)",
            (access_scope, access_scope, reference),
        )
        for row in identities:
            self._invalidate_method(access_scope, row[0])

    def revoke_event(self, access_scope: str, reference: str, *, expected_version: int) -> int:
        with self._transaction():
            changed = self.connection.execute(
                "UPDATE events SET revoked=1,version=version+1 WHERE scope=? AND id=? AND version=? AND revoked=0",
                (access_scope, reference, expected_version),
            ).rowcount
            if changed != 1:
                raise StoreConflictError("the source is missing, already revoked or its version changed")
            self._invalidate_source(access_scope, reference)
        return expected_version + 1

    def retire_candidate(self, access_scope: str, reference: CandidateRef) -> None:
        with self._transaction():
            current = self.connection.execute(
                "SELECT MAX(version) FROM candidates WHERE scope=? AND id=?", (access_scope, reference.id)
            ).fetchone()[0]
            if current != reference.version:
                raise StoreConflictError("the current candidate version is required for retirement")
            self.connection.execute(
                "UPDATE candidates SET status='retired' WHERE scope=? AND id=?", (access_scope, reference.id)
            )
            self._invalidate_method(access_scope, reference.id)

    def record_process_check(self, receipt: ProcessCheckReceipt) -> None:
        receipt = ProcessCheckReceipt.model_validate(receipt.model_dump())
        with self._transaction():
            row = self.connection.execute(
                "SELECT c.proposal,c.status,e.revoked,e.payload,e.version,l.event_version "
                "FROM candidates c JOIN links l ON l.scope=c.scope AND l.candidate_id=c.id AND l.candidate_version=c.version "
                "JOIN events e ON e.scope=l.scope AND e.id=l.event_id "
                "WHERE c.scope=? AND c.id=? AND c.version=? AND l.event_id=? AND l.relation='supports'",
                (receipt.access_scope, receipt.method.id, receipt.method.version, receipt.event_reference),
            ).fetchone()
            if (
                row is None
                or row["status"] == "retired"
                or row["revoked"]
                or row["version"] != receipt.event_version
                or row["event_version"] != receipt.event_version
                or json.loads(row["proposal"]).get("support_kind") != "process"
                or ExperienceEvent.model_validate_json(row["payload"]).view.process_result != "checked"
            ):
                raise StoreConflictError("a process check needs the exact reviewed method and a current checked source")
            key = (receipt.access_scope, receipt.method.id, receipt.event_reference, receipt.event_version)
            existing = self.connection.execute(
                "SELECT receipt FROM process_checks WHERE scope=? AND method_id=? AND event_id=? AND event_version=?",
                key,
            ).fetchone()
            if existing:
                saved = ProcessCheckReceipt.model_validate_json(existing[0])
                if saved.model_dump(exclude={"method"}) != receipt.model_dump(exclude={"method"}):
                    raise StoreConflictError(
                        "a recorded process check is immutable; changed observations need a new source version"
                    )
                return
            self.connection.execute("INSERT INTO process_checks VALUES (?,?,?,?,?)", (*key, receipt.model_dump_json()))
            self._invalidate_method(receipt.access_scope, receipt.method.id)

    def _families(self, access_scope: str) -> dict[str, tuple[ReviewedVersion, ...]]:
        rows = self.connection.execute(
            "SELECT * FROM candidates WHERE scope=? ORDER BY id,version", (access_scope,)
        ).fetchall()
        linked = self.connection.execute(
            "SELECT l.*,e.payload,e.version AS current_version,e.view_digest AS current_digest,e.revoked,p.receipt "
            "FROM links l LEFT JOIN events e ON e.scope=l.scope AND e.id=l.event_id "
            "LEFT JOIN process_checks p ON p.scope=l.scope AND p.method_id=l.candidate_id AND p.event_id=l.event_id "
            "AND p.event_version=l.event_version WHERE l.scope=?",
            (access_scope,),
        ).fetchall()
        evidence: dict[tuple[str, int], list[LinkedEvidence]] = {}
        families: dict[str, list[ReviewedVersion]] = {}
        try:
            for row in linked:
                event = ExperienceEvent.model_validate_json(row["payload"])
                if event.origin.access_scope != access_scope or event.view.reference != row["event_id"]:
                    raise ValueError("source identity mismatch")
                if row["relation"] not in {"supports", "contradicts", "context"}:
                    raise ValueError("invalid evidence relation")
                receipt = ProcessCheckReceipt.model_validate_json(row["receipt"]) if row["receipt"] else None
                if receipt and (
                    receipt.access_scope != access_scope
                    or receipt.method.id != row["candidate_id"]
                    or receipt.event_reference != row["event_id"]
                    or receipt.event_version != row["event_version"]
                ):
                    raise ValueError("process check binding mismatch")
                link = LinkedEvidence(
                    event,
                    row["relation"],
                    not row["revoked"]
                    and row["current_version"] == row["event_version"]
                    and row["current_digest"] == row["view_digest"],
                    receipt.passed if receipt else None,
                )
                evidence.setdefault((row["candidate_id"], row["candidate_version"]), []).append(link)
            for row in rows:
                raw_proposal = json.loads(row["proposal"])
                proposal = ExperienceProposal.model_validate(raw_proposal)
                links = tuple(evidence.get((row["id"], row["version"]), ()))
                typed = "support_kind" in raw_proposal
                if (
                    (typed and method_id(access_scope, proposal) != row["id"])
                    or row["status"] not in {"candidate", "supported", "contested", "retired"}
                    or {(link.event.view.reference, link.relation) for link in links}
                    != {(link.reference, link.relation) for link in proposal.evidence}
                ):
                    raise ValueError("candidate binding mismatch")
                version = ReviewedVersion(
                    CandidateRef(id=row["id"], version=row["version"]),
                    proposal,
                    ExperienceReview.model_validate_json(row["review"]),
                    digest(json.loads(row["identities"])["critic"]),
                    row["status"],
                    typed,
                    links,
                )
                families.setdefault(row["id"], []).append(version)
        except (ValidationError, ValueError, TypeError, KeyError) as exc:
            raise StoreError("stored experience evidence or review has invalid bindings") from exc
        return {identity: tuple(versions) for identity, versions in families.items()}

    def refresh_admission(self, access_scope: str, policy: AdmissionPolicy) -> tuple[AdmissionAssessment, ...]:
        with self._transaction():
            assessments = []
            for identity, versions in self._families(access_scope).items():
                assessment = assess_family(versions, policy)
                self.connection.execute(
                    "UPDATE candidates SET status=? WHERE scope=? AND id=? AND version=?",
                    (assessment.status, access_scope, identity, assessment.reference.version),
                )
                self.connection.execute(
                    "INSERT OR REPLACE INTO admissions VALUES (?,?,?,?,?)",
                    (access_scope, identity, assessment.reference.version, policy.id, assessment.model_dump_json()),
                )
                assessments.append(assessment)
        return tuple(assessments)

    def recommendations(
        self, access_scope: str, policy: AdmissionPolicy
    ) -> tuple[tuple[ExperienceProposal, AdmissionAssessment], ...]:
        self.connection.execute("BEGIN")
        try:
            stored = {
                (row["id"], row["version"]): AdmissionAssessment.model_validate_json(row["assessment"])
                for row in self.connection.execute(
                    "SELECT * FROM admissions WHERE scope=? AND policy_id=?", (access_scope, policy.id)
                )
            }
            recommendations = []
            for identity, versions in self._families(access_scope).items():
                assessment = assess_family(versions, policy)
                if (
                    assessment.status != "supported"
                    or stored.get((identity, assessment.reference.version)) != assessment
                ):
                    continue
                latest = max(versions, key=lambda version: version.reference.version)
                recommendations.append((latest.proposal, assessment))
            return tuple(recommendations)
        except (ValidationError, ValueError, TypeError) as exc:
            raise StoreError("stored experience admission has invalid bindings") from exc
        finally:
            self.connection.rollback()

    def related_methods(
        self, access_scope: str, policy: AdmissionPolicy, *, include_history: bool = False
    ) -> tuple[ExperienceProposal, ...]:
        self.connection.execute("BEGIN")
        try:
            proposals = []
            for versions in self._families(access_scope).values():
                assessment = assess_family(versions, policy)
                if assessment.status in {"retired", "contested"}:
                    continue
                selected = (
                    versions if include_history else (max(versions, key=lambda version: version.reference.version),)
                )
                for version in selected:
                    if (
                        version.status != "retired"
                        and version.typed_support
                        and version.critic_digest == policy.critic_digest
                        and version.review.decision == "accept"
                        and all(link.current for link in version.evidence)
                        and version.proposal not in proposals
                    ):
                        proposals.append(version.proposal)
            return tuple(proposals)
        finally:
            self.connection.rollback()

    def task(self, task_id: str) -> BuildState:
        row = self.connection.execute("SELECT state FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise StoreError("the construction task does not exist")
        return BuildState.model_validate_json(row[0])

    def candidates(self, access_scope: str) -> tuple[dict, ...]:
        rows = self.connection.execute(
            "SELECT id,version,proposal,review,status,task_id FROM candidates WHERE scope=? ORDER BY id,version",
            (access_scope,),
        ).fetchall()
        return tuple(
            {**dict(row), "proposal": json.loads(row["proposal"]), "review": json.loads(row["review"])} for row in rows
        )

    def binding(self, access_scope: str, reference: CandidateRef, policy: AdmissionPolicy) -> dict:
        """Bind a domain verdict to its exact method, reviews and all contributing source versions."""
        self.connection.execute("BEGIN")
        try:
            versions = self._families(access_scope).get(reference.id, ())
            current = next((row for row in versions if row.reference == reference), None)
            if current is None:
                raise StoreError("the experience reference does not identify a retained method")
            assessment = assess_family(versions, policy)
            sources = {}
            for version in versions:
                sources[f"curator-review:{access_scope}:{version.reference.id}:{version.reference.version}"] = digest(
                    {
                        "proposal": version.proposal.model_dump(),
                        "review": version.review.model_dump(),
                        "critic": version.critic_digest,
                        "current": all(link.current for link in version.evidence),
                    }
                )
                for link in version.evidence:
                    source = self.connection.execute(
                        "SELECT version,revoked FROM events WHERE scope=? AND id=?",
                        (access_scope, link.event.view.reference),
                    ).fetchone()
                    sources[f"curator-source:{access_scope}:{link.event.view.reference}"] = digest(
                        {"event": link.event.model_dump(), "version": source["version"], "revoked": source["revoked"]}
                    )
            return {
                "reference": reference.model_dump(mode="json"),
                "proposal": current.proposal.model_dump(mode="json"),
                "review": current.review.model_dump(mode="json"),
                "sources": sources,
                "assessment": assessment.model_dump(mode="json"),
                "current": reference == assessment.reference,
                "policy": policy.id,
            }
        finally:
            self.connection.rollback()
