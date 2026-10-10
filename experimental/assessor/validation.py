"""Compare construction instructions against frozen replay cases and host-supplied independent verifiers."""

import asyncio
import copy
import fcntl
import hashlib
import json
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from experimental.assessor.checks import Finding, Verifier
from experimental.assessor.standard import observations
from experimental.curator.raven_adapter.materialize import _write
from experimental.curator.raven_adapter.observe import plain
from experimental.curator.raven_adapter.worker import Execution
from experimental.iteration.protocols import Exchange, Sessions


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def input_identity(evidence: dict) -> str:
    """Repeated inputs stay exposed even when a new run assigns different session and execution identifiers."""
    return fingerprint(
        {
            "task": evidence.get("task", ""),
            "inputs": sorted(tuple(row["user"] for row in rows) for rows in evidence.get("conversations", {}).values()),
        }
    )


def evidence_fingerprint(sessions: Sessions) -> str:
    """Bind a verification to execution records and retained artifact bytes, not just their filenames."""
    artifacts = {}
    for exchanges in sessions.values():
        for exchange in exchanges:
            for name in exchange.execution.deliverables:
                path = Path(name)
                if path.is_file():
                    with path.open("rb") as stream:
                        artifacts[name] = hashlib.file_digest(stream, "sha256").hexdigest()
                else:
                    artifacts[name] = None
    return fingerprint({"sessions": plain(sessions), "artifacts": artifacts})


def promotion(*, revision, context, witnesses, signals, feedback, external_requirements) -> dict:
    """Adoption requires independent frozen evidence for this revision and no unresolved applicable gate."""
    record = {"revision": revision, "context": context, "witnesses": witnesses, "status": "candidate"}
    if not witnesses:
        return {**record, "reason": "No independent verification is available."}
    if any(
        witness.get("error") or witness["revision"] != revision or witness["context"] != context
        for witness in witnesses
    ):
        return {**record, "reason": "Verification is incomplete or belongs to another revision or requirement set."}
    if any(witness["satisfied"] is False for witness in witnesses):
        return {**record, "status": "rejected", "reason": "An independent verification failed."}
    if any(witness["satisfied"] is not True for witness in witnesses):
        return {**record, "reason": "Independent verification is unresolved."}
    required = {requirement.id for requirement in external_requirements if requirement.kind != "quality"}
    measured = [item for signal in signals for item in signal.items]
    required.update(item.id for item in measured if item.strength == "must_hold")
    unresolved = bool(required - {item.id for item in measured}) or any(
        item.id in required and item.result not in ("pass", "not_applicable") for item in measured
    )
    if (
        unresolved
        or any(signal.satisfied is False for signal in signals)
        or feedback.decision in ("curate", "clarify", "supplement")
    ):
        return {**record, "reason": "Current feedback or a required condition still needs resolution."}
    return {
        **record,
        "status": "accepted",
        "reason": "The frozen independent checks passed without an unresolved gate.",
    }


@dataclass(frozen=True)
class ReplayCase:
    """A host-owned captured task/output and an independent oracle, never a label supplied by the candidate."""

    id: str
    task: str
    norms: dict[str, str]
    sessions: Sessions
    verifier: Verifier
    held_out: bool = False

    def evidence(self) -> dict:
        return observations(self.sessions, self.task)


@dataclass(frozen=True)
class RepairSuite:
    """Host-labeled cases for a specific property subtree, or the whole rubric when criterion is None."""

    criterion: str | None
    cases: tuple[ReplayCase, ...]

    def __post_init__(self):
        if self.criterion == "" or len(self.cases) > 6 or len({case.id for case in self.cases}) != len(self.cases):
            raise ValueError("a repair suite needs an explicit property scope and at most six unique cases")


class ReplayCorpus:
    """Retain up to six independently verified outcomes for later construction comparisons.

    The host calls capture only after freezing and validating a verifier's policy. Labels never come from the
    adaptive assessor. Saved labels are usable only while their original execution records and files still match.
    """

    def __init__(self, path: Path):
        self.path = Path(path)

    def records(self) -> list[dict]:
        return json.loads(self.path.read_text()) if self.path.exists() else []

    def capture(self, *, task, norms, sessions, witness, source) -> None:
        if witness.get("error") or witness.get("satisfied") not in (True, False) or not witness.get("policy"):
            return
        digest = evidence_fingerprint(sessions)
        if digest != witness["evidence"]:
            raise ValueError("independent evidence changed before retention")
        row = {
            "task": task,
            "norms": dict(norms),
            "sessions": plain(sessions),
            "evidence": digest,
            "witness": copy.deepcopy(witness),
            "source": str(source),
        }
        row["id"] = fingerprint(row)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.with_suffix(".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            rows = [old for old in self.records() if old["id"] != row["id"]]
            rows.append(row)
            kept = {
                old["id"]
                for passed in (True, False)
                for old in [r for r in rows if r["witness"]["satisfied"] is passed][-3:]
            }
            _write(
                self.path, json.dumps([old for old in rows if old["id"] in kept], ensure_ascii=False, indent=2).encode()
            )

    def cases(self) -> tuple[ReplayCase, ...]:
        cases = []
        for row in self.records():
            content = {key: value for key, value in row.items() if key != "id"}
            if fingerprint(content) != row["id"]:
                raise ValueError("retained replay identity does not match its contents")
            sessions = {
                name: [Exchange(value["user"], Execution(**value["execution"])) for value in values]
                for name, values in row["sessions"].items()
            }
            try:
                if evidence_fingerprint(sessions) != row["evidence"]:
                    continue
            except OSError:
                continue
            expected = fingerprint(observations(sessions, row["task"]))

            async def verify(evidence, expected=expected, row=row):
                if fingerprint(evidence) != expected:
                    return Finding("unknown", note="The retained independent evidence changed.")
                return Finding(
                    "pass" if row["witness"]["satisfied"] else "fail",
                    actual=f"Fixed {row['witness']['policy']['kind']} verification; source: {row['source']}",
                )

            cases.append(ReplayCase(row["id"], row["task"], row["norms"], sessions, verify, held_out=True))
        return tuple(cases)


@dataclass(frozen=True)
class ReplayEvaluation:
    """A replay decision linked to the actual construction and assessment record that produced it."""

    satisfied: bool | None
    record: str

    def __post_init__(self):
        if (self.satisfied is not None and type(self.satisfied) is not bool) or not self.record:
            raise ValueError("replay evaluation needs a boolean or unknown decision and its record reference")


@dataclass(frozen=True)
class Comparison:
    case: str
    evidence: str
    oracle: Finding
    before: bool | None
    after: bool | None
    held_out: bool
    before_record: str = ""
    after_record: str = ""
    input_key: str = ""

    @property
    def expected(self) -> bool | None:
        return {"pass": True, "fail": False}.get(self.oracle.result)


@dataclass(frozen=True)
class Validation:
    """A version-bound comparison receipt; approval follows the evidence, not an assessor-provided flag."""

    candidate: str
    baseline: str
    suite: str
    comparisons: tuple[Comparison, ...]
    cross_task: bool = False
    error: str = ""
    before_instructions: str = ""
    after_instructions: str = ""

    @property
    def accepted(self) -> bool:
        rows = self.comparisons
        if self.error or not rows or {row.expected for row in rows} != {True, False}:
            return False
        if any(row.after is None for row in rows):
            return False
        if self.cross_task and not any(row.held_out and row.after == row.expected for row in rows):
            return False
        regression = any(row.before == row.expected and row.after != row.expected for row in rows)
        improvement = any(row.before != row.expected and row.after == row.expected for row in rows)
        return improvement and not regression

    def record(self) -> dict:
        return {**asdict(self), "accepted": self.accepted}


def _snapshot(cases: Sequence[ReplayCase]) -> dict:
    artifacts = {}
    for case in cases:
        for exchanges in case.sessions.values():
            for exchange in exchanges:
                for name in exchange.execution.deliverables:
                    path = Path(name)
                    if path.is_file():
                        with path.open("rb") as stream:
                            artifacts[name] = hashlib.file_digest(stream, "sha256").hexdigest()
                    else:
                        artifacts[name] = None
    return {
        "cases": [
            {
                "id": case.id,
                "task": case.task,
                "norms": case.norms,
                "sessions": plain(case.sessions),
                "held_out": case.held_out,
                "verifier": f"{getattr(case.verifier, '__module__', '')}.{getattr(case.verifier, '__qualname__', type(case.verifier).__qualname__)}",
            }
            for case in cases
        ],
        "artifacts": artifacts,
    }


async def compare(
    *,
    candidate: str,
    baseline: str,
    before: str,
    after: str,
    cases: Sequence[ReplayCase],
    evaluate: Callable[[str, ReplayCase], Awaitable[ReplayEvaluation]],
    cross_task=False,
    seen=(),
    used=(),
) -> Validation:
    """Fix the protocol before running either instruction version; never pass labels to the evaluator."""
    if len(cases) > 6 or len({case.id for case in cases}) != len(cases):
        raise ValueError("validation requires at most six uniquely named host cases")
    cases = copy.deepcopy(tuple(cases))
    snapshot = fingerprint(_snapshot(cases))
    prepared, rows = [], []
    instructions = {"before_instructions": fingerprint(before), "after_instructions": fingerprint(after)}
    try:
        for case in cases:
            evidence = case.evidence()
            identity = fingerprint(evidence)
            oracle = await asyncio.wait_for(case.verifier(copy.deepcopy(evidence)), timeout=10)
            if not isinstance(oracle, Finding) or oracle.result not in ("pass", "fail"):
                return Validation(
                    candidate, baseline, snapshot, (), cross_task, "Independent evidence is unresolved.", **instructions
                )
            held_out = case.held_out and not {identity, input_identity(evidence)} & {*seen, *used}
            prepared.append((case, identity, oracle, held_out))
        if fingerprint(_snapshot(cases)) != snapshot:
            raise ValueError("validation inputs changed while preparing the independent evidence")
        if cross_task and (len({case.task for case in cases}) < 2 or not any(row[3] for row in prepared)):
            return Validation(
                candidate,
                baseline,
                snapshot,
                (),
                cross_task,
                "Cross-task guidance needs an unused held-out task.",
                **instructions,
            )
        for case, identity, oracle, held_out in prepared:
            rows.append(
                Comparison(case.id, identity, oracle, None, None, held_out, input_key=input_identity(case.evidence()))
            )
            previous = await evaluate(before, case)
            proposed = await evaluate(after, case)
            if not isinstance(previous, ReplayEvaluation) or not isinstance(proposed, ReplayEvaluation):
                raise ValueError("evaluation must return its decision and an inspectable replay record")
            if fingerprint(_snapshot(cases)) != snapshot:
                raise ValueError("the evaluator changed the frozen replay inputs or artifacts")
            rows[-1] = Comparison(
                case.id,
                identity,
                oracle,
                previous.satisfied,
                proposed.satisfied,
                held_out,
                previous.record,
                proposed.record,
                input_identity(case.evidence()),
            )
        return Validation(candidate, baseline, snapshot, tuple(rows), cross_task, **instructions)
    except Exception as exc:
        return Validation(candidate, baseline, snapshot, tuple(rows), cross_task, str(exc), **instructions)
