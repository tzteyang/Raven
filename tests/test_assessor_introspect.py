"""The worker's self-review: one replica per session, verdicts parsed, labels opaque, reviews recorded."""

import json
from dataclasses import dataclass, field

import pytest

from experimental.assessor.introspect import SOURCE, Introspection, parse, request
from experimental.audience import project
from experimental.iteration.hearing import opaque
from experimental.iteration.protocols import Exchange


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
    return Exchange(user, _Execution(assistant, deliverables=tuple(delivered)))


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
@pytest.mark.parametrize("entrypoint", ["batch", "session"])
@pytest.mark.parametrize("owner_fails", [False, True])
async def test_self_review_precedes_next_round_handover_even_when_the_owner_is_listed_first(
    tmp_path, entrypoint, owner_fails
):
    from experimental.iteration.protocols import Signal
    from experimental.iteration.session import Session, assess
    from tests.test_iteration_run import FakeWorker

    material = tmp_path / "next-round-norm.md"
    worker = FakeWorker(tmp_path)
    sessions = {"case": [exchange("Create the three-file package.", "The files are ready.")]}
    order, log = [], []

    class Owner:
        async def evaluate(self, sessions):
            order.append("owner")
            material.write_text("The next round requires five files.")
            if owner_fails:
                raise ValueError("owner unavailable")
            return Signal("owner", "Here is the next-round norm.")

    class Independent:
        async def evaluate(self, sessions):
            order.append("independent")
            assert material.exists()
            return Signal("independent")

    def spawn(employee, label):
        order.append("self")
        assert employee is worker and not material.exists()
        return _Replica(label, {label: "VERDICT: pass\nDEFECTS: none\nNOTE: old norm only"}, log)

    self_review = Introspection(worker, spawn, records=tmp_path)
    assessors = (Owner(), self_review, Independent())
    session = Session.open(worker, object()) if entrypoint == "session" else None
    if session is not None:
        session.sessions = sessions

    async def evaluate():
        return await session.assess(*assessors) if session is not None else await assess(assessors, sessions)

    if owner_fails:
        with pytest.raises(ValueError, match="owner unavailable"):
            await evaluate()
        assert order[:2] == ["self", "owner"]
        assert order[2:] in ([], ["independent"])
        if session is not None:
            assert session.rounds[-1].signals[0].source == SOURCE
    else:
        assert [signal.source for signal in await evaluate()] == [SOURCE, "owner", "independent"]
        assert order == ["self", "owner", "independent"]
    assert [entry[0] for entry in log] == ["start", "run", "close"]
    reviews = [json.loads(path.read_text()) for path in (tmp_path / "analysis").glob("*.json")]
    assert any(review.get("source") == SOURCE and review["reviews"][0]["result"] == "pass" for review in reviews)


@pytest.mark.asyncio
async def test_each_rounds_self_replica_keeps_prior_materials_but_excludes_its_new_handover(tmp_path):
    from experimental.iteration.protocols import Signal
    from experimental.iteration.session import assess
    from tests.test_iteration_run import FakeWorker

    worker, log, observed = FakeWorker(tmp_path), [], []
    materials = [tmp_path / "cost-update.md", tmp_path / "five-file-update.md"]

    class Owner:
        rounds = 0

        async def evaluate(self, sessions):
            materials[self.rounds].write_text("Next-round requirements.")
            self.rounds += 1
            return Signal("owner")

    def spawn(employee, label):
        assert employee is worker
        observed.append([path.name for path in materials if path.exists()])
        return _Replica(label, {label: "VERDICT: pass\nDEFECTS: none\nNOTE: reviewed"}, log)

    owner, self_review = Owner(), Introspection(worker, spawn)
    sessions = {"case": [exchange("Maintain the package.", "Here is the current package.")]}
    await assess((owner, self_review), sessions)
    await assess((owner, self_review), sessions)
    assert observed == [[], ["cost-update.md"]]
    assert self_review.rounds == owner.rounds == 2 and all(path.exists() for path in materials)


@pytest.mark.asyncio
async def test_self_replica_is_closed_when_startup_fails():
    log = []

    class FailedReplica(_Replica):
        async def start(self):
            await super().start()
            raise ValueError("startup failed")

    self_review = Introspection(object(), lambda worker, label: FailedReplica(label, {}, log))
    with pytest.raises(ValueError, match="startup failed"):
        await self_review.evaluate({"case": [exchange("Review it.", "Done.")]})
    assert [entry[0] for entry in log] == ["start", "close"]
