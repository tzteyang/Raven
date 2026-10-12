"""The worker's self-review: one replica per session, verdicts parsed, labels opaque, reviews recorded."""

import json
import shutil
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from experimental.harness.assessor.introspect import SOURCE, Introspection, parse, request
from experimental.harness.participation.audience import project
from experimental.harness.participation.hearing import opaque
from experimental.harness.participation.protocols import Exchange


@dataclass
class _Execution:
    text: str
    turn_id: str = "turn-1"
    deliverables: tuple = ()
    records: list = field(default_factory=list)
    outcome: dict = field(default_factory=dict)
    events: list = field(default_factory=list)
    artifact_id: str = ""

    @property
    def errors(self):
        return []


class _Replica:
    def __init__(self, label, answers, log):
        self.label, self.answers, self.log, self.started = label, answers, log, False

    async def start(self):
        self.started = True
        self.log.append(("start", self.label))

    async def run(self, text, *, session_key):
        assert self.started
        self.log.append(("run", self.label, text, session_key))
        return _Execution(self.answers[self.label])

    async def close(self):
        self.log.append(("close", self.label))


def exchange(user, assistant, delivered=()):
    records = [{"kind": "runner.event", "event_type": "Text", "event": {"content": assistant}}]
    return Exchange(user, _Execution(assistant, deliverables=tuple(delivered), records=records))


def test_parse_reads_the_three_lines_and_tolerates_a_free_reply():
    review = parse("VERDICT: fail\nDEFECTS: the file is missing\nmore\nNOTE: deliver it")
    assert review == {"result": "fail", "defects": "the file is missing\nmore", "note": "deliver it"}
    assert parse("I think it went fine.") == {"result": "unknown", "defects": "", "note": "I think it went fine."}
    assert parse("VERDICT: pass\nDEFECTS: none\nNOTE: holds up")["defects"] == "none"


def test_request_carries_the_conversation_and_the_delivered_files(tmp_path):
    delivered = tmp_path / "plan.md"
    delivered.write_text("# plan")
    text = request([exchange("hello", "here is the plan", [str(delivered)])])
    assert "VERDICT" in text and "# plan" in text and '"user": "hello"' in text and '"plan.md"' in text


@pytest.mark.asyncio
async def test_each_session_is_reviewed_on_its_own_replica_and_recorded(tmp_path):
    log, employee = [], object()
    sessions = {"family": [exchange("hi", "quote A")], "student": [exchange("hey", "quote B")]}
    answers = {
        f"1-self-{opaque('family')}": "VERDICT: pass\nDEFECTS: none\nNOTE: fine",
        f"1-self-{opaque('student')}": "VERDICT: fail\nDEFECTS: no file delivered\nNOTE: deliver the quote as a file",
    }
    assessor = Introspection(employee, lambda worker, label: _Replica(label, answers, log), records=tmp_path)
    signal = await assessor.evaluate(sessions)
    assert signal.source == SOURCE and signal.satisfied is None
    assert [item.result for item in signal.items] == ["pass", "fail"]
    assert [item.session for item in signal.items] == ["family", "student"]
    assert signal.items[1].actual == "no file delivered" and signal.items[1].note == "deliver the quote as a file"
    assert opaque("student") in signal.text and "student" not in signal.text and "no file delivered" in signal.text
    assert {entry[0] for entry in log} == {"start", "run", "close"}
    runs = [entry for entry in log if entry[0] == "run"]
    assert len(runs) == 2 and all(key.startswith("curator:") and ":self:" in key for _, _, _, key in runs)
    heard = project(signal, "curator")
    assert "items" not in heard and heard["text"] == signal.text
    recorded = [json.loads(path.read_text()) for path in (tmp_path / "analysis").glob("*.json")]
    assert len(recorded) == 1 and recorded[0]["source"] == SOURCE and recorded[0]["round"] == 1
    assert {review["session"] for review in recorded[0]["reviews"]} == {"family", "student"}


@pytest.mark.asyncio
async def test_an_empty_round_has_no_self_signal():
    assessor = Introspection(object(), lambda worker, label: pytest.fail("no replica for no session"))
    assert await assessor.evaluate({}) is None


def test_reviews_run_at_least_one_at_a_time():
    with pytest.raises(ValueError):
        Introspection(object(), lambda worker, label: None, concurrency=0)


@pytest.mark.asyncio
async def test_self_review_carries_only_its_original_customers_entitled_speech(tmp_path):
    from experimental.harness.participation.compartment import CURRENT, BoundaryError, Guard
    from experimental.harness.scenario.sealed import Sealed

    customer = "The customer asked for the original approved version with the confirmed schedule and account."
    hidden = "The hidden evaluation card demands an undisclosed special branch that this customer never mentioned."
    guard = Guard("partner", Sealed.of([customer, hidden]))
    calls = []

    class CheckedReplica(_Replica):
        async def run(self, text, *, session_key):
            scope = CURRENT.get()
            assert scope is not None and scope.role == "partner"
            calls.append(scope.spoken)
            guard.check_request([{"role": "user", "content": text}], [], {}, "self-review", spared=scope.spoken)
            return _Execution("VERDICT: pass\nDEFECTS: none\nNOTE: checked")

    assessor = Introspection(object(), lambda worker, label: CheckedReplica(label, {}, []))
    assert guard.scan(request([exchange(customer, "Here is the requested document.")]))
    signal = await assessor.evaluate({"one": [exchange(customer, "Here is the requested document.")]})
    assert signal.items[0].result == "pass" and calls == [((customer,),)]
    assert CURRENT.get() is None
    with pytest.raises(BoundaryError):
        await assessor.evaluate({"one": [exchange(customer, hidden)]})
    assert CURRENT.get() is None
    delivered = tmp_path / "delivery.md"
    delivered.write_text(hidden)
    with pytest.raises(BoundaryError):
        await assessor.evaluate({"one": [exchange(customer, "Please see the file.", [str(delivered)])]})
    assert CURRENT.get() is None
    with pytest.raises(BoundaryError):
        await assessor.evaluate({"one": [exchange(hidden, "Acknowledged.")], "two": [exchange(customer, hidden)]})
    assert CURRENT.get() is None


def _packet(text):
    return json.loads(text[text.index("{") :])


def test_request_without_the_sessions_replica_is_the_conversation_and_the_deliveries_only(tmp_path):
    delivered = tmp_path / "plan.md"
    delivered.write_text("# plan")
    packet = _packet(request([exchange("hello", "here is the plan", [str(delivered)])]))
    assert set(packet) == {"conversation", "delivered"}
    packet = _packet(request([exchange("hello", "ok")], attachments={"uploads/a.md": "a"}, filed={}))
    assert packet["attachments"] == {"uploads/a.md": "a"} and packet["filed"] == {}


def _employee(root):
    workdir, home = root / "employee" / "workdir", root / "employee" / "home"
    (workdir / "uploads" / "pack").mkdir(parents=True)
    (workdir / "uploads" / "pack" / "SKILL.md").write_text("shared material handed before the session")
    (workdir / "brief.md").write_text("the worker's standing brief")
    (home / "uploads").mkdir(parents=True)
    (home / "uploads" / "material.md").write_text("owner material")
    (home / "notes.md").write_text("standing notes")
    baseline = SimpleNamespace(workdir=workdir, config=SimpleNamespace(workspace_path=home))
    return SimpleNamespace(baseline=baseline)


def _played(employee, root):
    workdir, home = root / "replica" / "workdir", root / "replica" / "home"
    shutil.copytree(employee.baseline.workdir, workdir)
    shutil.copytree(employee.baseline.config.workspace_path, home)
    (workdir / "uploads" / "history-sheet.md").write_text("Internship at a regional firm, 2024")
    (workdir / "records").mkdir()
    (workdir / "records" / "consultation.md").write_text("Consultation record: goals agreed")
    (workdir / "decks").mkdir()
    (workdir / "decks" / "build.json").write_text("{}")
    (home / "notes.md").write_text("standing notes, plus the client's deadline")
    (home / "sessions").mkdir()
    (home / "sessions" / "turns.jsonl").write_text("{}")
    (home / ".raven").mkdir()
    (home / ".raven" / "checkpoint.json").write_text("{}")
    return {"workdir": workdir, "home": home}


@pytest.mark.asyncio
async def test_the_review_packet_carries_what_the_session_was_handed_and_filed_beyond_the_baseline(tmp_path):
    employee, log = _employee(tmp_path), []
    placed = {"family": _played(employee, tmp_path)}
    answers = {
        f"1-self-{opaque('family')}": "VERDICT: pass\nDEFECTS: none\nNOTE: fine",
        f"1-self-{opaque('student')}": "VERDICT: pass\nDEFECTS: none\nNOTE: fine",
    }
    assessor = Introspection(employee, lambda worker, label: _Replica(label, answers, log), placed=placed)
    await assessor.evaluate({"family": [exchange("hi", "noted")], "student": [exchange("hey", "noted")]})
    asked = {entry[1]: _packet(entry[2]) for entry in log if entry[0] == "run"}
    family, student = asked[f"1-self-{opaque('family')}"], asked[f"1-self-{opaque('student')}"]
    assert family["attachments"] == {"uploads/history-sheet.md": "Internship at a regional firm, 2024"}
    assert family["filed"] == {
        "workdir/records/consultation.md": "Consultation record: goals agreed",
        "home/notes.md": "standing notes, plus the client's deadline",
    }
    assert set(student) == {"conversation", "delivered"}
    texts = [entry[2] for entry in log if entry[0] == "run"]
    assert not any(
        hidden in text
        for text in texts
        for hidden in ("shared material handed before", "the worker's standing brief", "owner material")
    )


@pytest.mark.asyncio
async def test_a_handed_attachment_passes_the_partner_guard_and_a_sealed_one_does_not(tmp_path):
    from experimental.harness.participation.compartment import BoundaryError, Guard
    from experimental.harness.scenario.sealed import Sealed

    hidden = "The hidden evaluation card demands an undisclosed special branch that this customer never mentioned."
    guard = Guard("partner", Sealed.of([hidden]))

    class CheckedReplica(_Replica):
        async def run(self, text, *, session_key):
            from experimental.harness.participation.compartment import CURRENT

            guard.check_request([{"role": "user", "content": text}], [], {}, "self-review", spared=CURRENT.get().spoken)
            return _Execution("VERDICT: pass\nDEFECTS: none\nNOTE: checked")

    employee = _employee(tmp_path)
    placed = {"one": _played(employee, tmp_path)}
    assessor = Introspection(employee, lambda worker, label: CheckedReplica(label, {}, []), placed=placed)
    signal = await assessor.evaluate({"one": [exchange("Please use my sheet.", "Done.")]})
    assert signal.items[0].result == "pass"
    (placed["one"]["workdir"] / "uploads" / "leak.md").write_text(hidden)
    with pytest.raises(BoundaryError):
        await assessor.evaluate({"one": [exchange("Please use my sheet.", "Done.")]})
