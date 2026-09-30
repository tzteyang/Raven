"""Program-side triage, one bounded model exchange and the recorded feedback stay faithful to the judgements."""

import json
from types import SimpleNamespace

import pytest

from experimental.analyst.feedback import Feedback
from experimental.analyst.materials import RECORDS, read_records
from experimental.analyst.run import NAME, Limits, analyse, triage, vet
from experimental.curator.harness import Plan, Task
from experimental.curator.raven_adapter.worker import Execution
from experimental.iteration.exchange import ExchangeError
from experimental.iteration.history import Diagnosed, Entry, Raised, Revised
from experimental.iteration.protocols import Exchange, Item, Signal
from experimental.scenario.sealed import Sealed
from raven.contracts.llm_provider import LLMResponse, ToolCallRequest


class Provider:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    async def chat_with_retry(self, **kwargs):
        self.requests.append(kwargs)
        return self.responses.pop(0)


class FakeWorker:
    def __init__(self, root, plan=None):
        self.baseline = SimpleNamespace(task=Task(text="Serve the agency's travellers"))
        self.root = root
        self.last_plan = plan

    async def inspect(self):
        return SimpleNamespace(sources={"skill.local/pricing": {}, "reference.index": {}, "skill.local/sop": {}})


def response(name, arguments):
    return LLMResponse(content=None, tool_calls=[ToolCallRequest(name, name, arguments)])


def execution(turn_id, reply, *extra):
    records = [{"kind": "runner.event", "event_type": "Text", "event": {"content": reply}}, *extra]
    return Execution(turn_id, [], records, {}, "artifact-1")


@pytest.fixture
def sessions():
    return {
        "student": [
            Exchange("Plan me a trip", execution("t1", "Here is a three-day itinerary.")),
            Exchange("How much?", execution("t2", "About 3000.", {"kind": "tool.error", "error": "no pricing tool"})),
        ]
    }


REQUIREMENT = {
    "situation": "A traveller asks for a plan before giving budget, dates, party size or departure city.",
    "behavior": "Before proposing an itinerary, ask for budget, dates, party size and departure city.",
    "observed": "In turn t1 the assistant proposed a three-day itinerary knowing only the destination.",
    "evidence": ["t1", "Here is a three-day itinerary."],
    "expectation": "new",
    "acceptance": "No itinerary appears before those four items have been asked for.",
    "strength": "must_hold",
}


def test_triage_decides_only_when_nothing_needs_interpretation():
    assert triage(()).decision == "continue"
    passed = Signal("verifier", items=(Item("asks budget", "pass"),), satisfied=True)
    assert triage((passed,)).decision == "continue"
    assert triage((Signal("verifier", items=(Item("asks budget", "fail"),), satisfied=False),)) is None
    assert triage((Signal("verifier", "Too pushy.", satisfied=True),)) is None
    assert triage((Signal("dataset", metrics={"pass_rate": 1.0}),)) is None
    assert triage((Signal("human", "Fine."),)) is None


def test_feedback_requires_requirements_exactly_for_curate():
    with pytest.raises(ValueError, match="curate requires"):
        Feedback(decision="curate", reason="r")
    with pytest.raises(ValueError, match="carry none"):
        Feedback(decision="continue", reason="r", requirements=(REQUIREMENT,))


@pytest.mark.asyncio
async def test_model_reads_records_then_submits_and_the_round_is_recorded(tmp_path, sessions):
    plan = Plan(
        understanding="u",
        design="d",
        changes=[{"target": "planning.strategy", "reason": "r", "expected": "asks first", "verification": "v"}],
    )
    worker = FakeWorker(tmp_path, plan)
    signals = (Signal("human", "It never asked my budget before recommending."),)
    provider = Provider(
        response(RECORDS, {"turn_id": "t2", "kind": "tool."}),
        response(NAME, {"decision": "curate", "reason": "The intake gap recurs.", "requirements": [REQUIREMENT]}),
    )
    previous = (Signal("dataset", metrics={"pass_rate": 0.5}),)
    history = (
        Entry(
            round=1,
            results={"verifier": {"asks-budget": "fail"}},
            revision=(Revised(target="planning.strategy", treatment="add", expected="asks first", verification="v"),),
            diagnoses=(Diagnosed(about="task", state="absent"),),
            attributor={"implementation": "model"},
        ),
    )
    feedback = await analyse(
        worker, provider, signals, sessions, previous_signals=previous, history=history, model="analyst-model"
    )
    assert feedback.decision == "curate" and feedback.requirements[0].expectation == "new"
    materials = json.loads(provider.requests[0]["messages"][1]["content"])
    assert materials["signals"][0]["text"] == "It never asked my budget before recommending."
    assert materials["previous_signals"][0]["metrics"] == {"pass_rate": 0.5}
    assert "previous_expectations" not in materials and "asks first" not in json.dumps(materials)
    assert materials["skills"] == ["skill.local/pricing", "skill.local/sop"]
    (seen,) = materials["history"]
    assert seen["results"] == {"verifier": {"asks-budget": "fail"}} and "diagnoses" not in seen
    assert seen["revision"] == [
        {"scope": "root", "target": "planning.strategy", "treatment": "add", "reason": "", "addresses": []}
    ]
    assert "attributor" not in seen
    assert materials["sessions"]["student"][1]["errors"] == ["no pricing tool"]
    assert materials["sessions"]["student"][1]["record_kinds"] == {"runner.event": 1, "tool.error": 1}
    tools = {entry["function"]["name"] for entry in provider.requests[0]["tools"]}
    assert tools == {RECORDS, NAME}
    assert provider.requests[0]["tools"][0]["function"]["parameters"]["properties"]["turn_id"]["enum"] == ["t1", "t2"]
    tool_replies = [row for row in provider.requests[1]["messages"] if row["role"] == "tool"]
    query_result = json.loads(tool_replies[0]["content"])
    assert query_result["turn_id"] == "t2" and "no pricing tool" in query_result["text"]
    assert "runner.event" not in query_result["text"]
    assert all(request["model"] == "analyst-model" for request in provider.requests)
    record = json.loads(next((tmp_path / "analysis").glob("*.json")).read_text())
    assert record["feedback"]["decision"] == "curate" and record["materials"]["task"] == worker.baseline.task.text
    assert [row["event"] for row in record["trace"]] == ["model.call", "query", "model.call", NAME]


@pytest.mark.asyncio
async def test_invalid_submissions_are_returned_and_the_budget_is_final(tmp_path, sessions):
    worker = FakeWorker(tmp_path)
    signals = (Signal("human", "Not good."),)
    provider = Provider(
        response(NAME, {"decision": "curate", "reason": "r"}),
        LLMResponse(content="Let me think."),
    )
    with pytest.raises(ExchangeError, match="analyst: submission budget exhausted") as info:
        await analyse(worker, provider, signals, sessions, limits=Limits(max_calls=2))
    assert [row["event"] for row in info.value.trace] == [
        "model.call",
        "output.rejected",
        "model.call",
        "output.missing",
    ]
    missing = info.value.trace[-1]
    assert missing["content_chars"] == len("Let me think.") and {"finish_reason", "usage"} <= missing.keys()
    rejection = json.loads(next(row for row in provider.requests[1]["messages"] if row["role"] == "tool")["content"])
    assert "curate requires" in rejection["error"]
    record = json.loads(next((tmp_path / "analysis").glob("*.json")).read_text())
    assert record["error"].startswith("analyst: submission budget exhausted") and "feedback" not in record


def test_record_query_filters_by_kind_and_bounds_offsets(sessions):
    result = read_records(sessions, {"turn_id": "t2", "kind": "runner", "length": 40})
    assert result["next_offset"] == 40 and result["total_characters"] > 40
    assert read_records(sessions, {"turn_id": "t1"})["next_offset"] is None
    with pytest.raises(ValueError, match="offset exceeds"):
        read_records(sessions, {"turn_id": "t1", "offset": 10**6})
    with pytest.raises(ValueError, match="no turn in this round has the id 'missing'"):
        read_records(sessions, {"turn_id": "missing"})
    assert json.loads(read_records(sessions, {"turn_id": "t2", "kind": "tool."})["text"])[0]["kind"] == "tool.error"


def test_limits_reject_non_positive_bounds():
    for bad in ({"max_calls": 0}, {"call_timeout": 0}, {"call_timeout": float("inf")}):
        with pytest.raises(ValueError, match="finite positive"):
            Limits(**bad)


@pytest.mark.asyncio
async def test_the_last_call_offers_only_the_submission_tool(tmp_path, sessions):
    worker = FakeWorker(tmp_path)
    provider = Provider(
        response(RECORDS, {"turn_id": "t1"}),
        response(NAME, {"decision": "continue", "reason": "Nothing to change."}),
    )
    feedback = await analyse(worker, provider, (Signal("human", "Hm."),), sessions, limits=Limits(max_calls=2))
    assert feedback.decision == "continue"
    assert [entry["function"]["name"] for entry in provider.requests[0]["tools"]] == [RECORDS, NAME]
    assert [entry["function"]["name"] for entry in provider.requests[1]["tools"]] == [NAME]
    nudges = [
        row for row in provider.requests[1]["messages"] if row["role"] == "user" and "last call" in str(row["content"])
    ]
    assert len(nudges) == 1


def rejections(provider) -> list[str]:
    """The errors the model was given back, in order, read from the last request's tool messages."""
    return [json.loads(row["content"])["error"] for row in provider.requests[-1]["messages"] if row["role"] == "tool"]


async def test_requirements_get_the_loops_ids_and_a_repeat_keeps_the_earlier_one(tmp_path, sessions):
    history = (
        Entry(
            round=1,
            requirements=(
                Raised(id="R1", behavior="Ask the budget.", strength="must_hold", acceptance="a"),
                Raised(id="R2", behavior="Quote from the list.", strength="should", acceptance="a"),
            ),
        ),
    )
    repeated = {**REQUIREMENT, "repeats": "R1", "expectation": "unmet", "recurrence": 1}
    other = {
        **REQUIREMENT,
        "situation": "A traveller names a destination without a departure city.",
        "behavior": "Confirm the departure city before quoting.",
    }
    provider = Provider(
        response(NAME, {"decision": "curate", "reason": "r", "requirements": [{**REQUIREMENT, "repeats": "R9"}]}),
        response(NAME, {"decision": "curate", "reason": "r", "requirements": [repeated, other]}),
    )
    feedback = await analyse(FakeWorker(tmp_path), provider, (Signal("human", "Still no."),), sessions, history=history)
    assert [item.id for item in feedback.requirements] == ["R1", "R3"]
    assert "repeats names no earlier requirement: 'R9'" in rejections(provider)[0]
    schema = next(t for t in provider.requests[0]["tools"] if t["function"]["name"] == NAME)["function"]["parameters"]
    requirement = schema["$defs"]["Requirement"]
    assert "id" not in requirement["properties"] and "situation" in requirement["required"]


async def test_what_is_bound_for_the_curator_may_not_carry_what_the_evaluation_side_holds(tmp_path, sessions):
    reference = "Ask for the budget, dates, party size and departure city before any itinerary."
    items = (Item("asks-budget", "fail", "student", expected=reference), Item("capital", "fail", "s", expected="Paris"))
    signals = (Signal("verifier", "", items=items, satisfied=False),)
    card = "A family of two adults and one child with a budget of 8000 for the first week of October."
    attempts = [
        {**REQUIREMENT, "observed": "In turn t1 the check asks-budget failed."},
        {**REQUIREMENT, "observed": "In turn t1 it should have said Paris.", "acceptance": reference},
        {**REQUIREMENT, "observed": "In turn t1 the planning.strategy never asked."},
        {**REQUIREMENT, "observed": f"In turn t1 it answered {card}"},
        {**REQUIREMENT, "observed": "It proposed without asking.", "evidence": ["Here is a three-day itinerary."]},
        {**REQUIREMENT, "situation": " "},
        {**REQUIREMENT, "acceptance": reference, "grounds": ["check:asks-budget"], "materials": ["service-sop"]},
    ]
    provider = Provider(
        *(response(NAME, {"decision": "curate", "reason": "r", "requirements": [item]}) for item in attempts)
    )
    feedback = await analyse(
        FakeWorker(tmp_path), provider, signals, sessions, limits=Limits(max_calls=7), sealed=Sealed.of([card])
    )
    (accepted,) = feedback.requirements
    assert accepted.id == "R1" and accepted.grounds == ("check:asks-budget",) and accepted.materials == ("service-sop",)
    errors = rejections(provider)
    assert len(errors) == 6
    assert "asks-budget" in errors[0] and "<sealed text>" in errors[1] and "planning.strategy" in errors[2]
    assert "<sealed text>" in errors[3] and "cites no turn of this round" in errors[4] and "no situation" in errors[5]


def test_what_the_curator_already_holds_or_hears_is_not_held_against_a_requirement(sessions):
    behavior = "Ask the budget before any plan."
    items = (
        Item("R1", "fail", "student", expected=behavior, basis="requirement"),
        Item("derived-1", "fail", "student", expected="Name the source of every price.", basis="material"),
        Item("asks-dates", "fail", "student", expected="Ask the dates first.", note="Dates come first.", basis="check"),
    )
    signals = (Signal("agency", "Dates come first, as I said.", items=items, satisfied=False),)

    def requirement(**fields):
        return Feedback(decision="curate", reason="r", requirements=({**REQUIREMENT, **fields, "id": "R2"},))

    vet(requirement(behavior=behavior, repeats="R1"), signals, sessions)
    vet(requirement(behavior="Name the source of every price."), signals, sessions)
    vet(requirement(acceptance="Dates come first."), signals, sessions)
    with pytest.raises(ValueError, match="<sealed text>"):
        vet(requirement(acceptance="Ask the dates first."), signals, sessions)
    card = "A family of two adults and one child with a budget of 8000 for the first week of October."
    earlier = [("Hello there", card)]
    with pytest.raises(ValueError, match="<sealed text>"):
        vet(requirement(observed=f"In turn t1 it forgot {card}"), signals, sessions, sealed=Sealed.of([card]))
    vet(
        requirement(observed=f"In turn t1 it forgot {card}"),
        signals,
        sessions,
        sealed=Sealed.of([card]),
        spoken=earlier,
    )
