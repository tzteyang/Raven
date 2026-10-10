"""The worker's self-review: one replica per session, verdicts parsed, labels opaque, reviews recorded."""

import json
from dataclasses import dataclass, field

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
