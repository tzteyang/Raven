"""The evaluation side's standard keeps its three sources apart and its automatic Assessor judges faithfully."""

import json

import pytest

from experimental.assessor.standard import Criterion, Standard, StandardAssessor, conversations, derive, satisfied
from experimental.curator.raven_adapter.worker import Execution
from experimental.iteration.compartment import Boundaries
from experimental.iteration.conversation import Conversation
from experimental.iteration.exchange import ExchangeError
from experimental.iteration.protocols import Exchange, Item
from experimental.iteration.session import Limits, Session
from experimental.requirements import Requirement
from experimental.scenario.sealed import Sealed
from raven.contracts.llm_provider import LLMResponse, ToolCallRequest
from tests.test_iteration_run import CURATE, REQUIREMENT, FakeWorker, Scripted
from tests.test_iteration_run import analyses as analyses  # noqa: F401 -- the loop test's Analyst stand-in


class Provider:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    async def chat_with_retry(self, messages=None, tools=None, model=None, **kwargs):
        self.requests.append({"messages": messages, "tools": tools, "model": model, **kwargs})
        return self.responses.pop(0)

    def get_default_model(self):
        return "judge/default"


def response(name, arguments):
    return LLMResponse(content=None, tool_calls=[ToolCallRequest(name, name, arguments)])


def execution(turn_id, reply, deliverables=()):
    records = [{"kind": "runner.event", "event_type": "Text", "event": {"content": reply}}]
    return Execution(turn_id, [], records, {}, "artifact-1", tuple(deliverables))


def history(*rounds):
    return [{"round": number, "requirements": list(raised)} for number, raised in enumerate(rounds, 1)]


def raised(id, behavior, strength="must_hold", situation="", acceptance="It is done."):
    return {"id": id, "behavior": behavior, "strength": strength, "situation": situation, "acceptance": acceptance}


def verdict(id, result, session=None, actual="", note=""):
    return {"id": id, "result": result, "session": session, "actual": actual, "note": note}


def test_the_standard_keeps_its_sources_apart_and_the_party_first():
    declared = Standard.declared([("asks-budget", "Ask the budget first."), ("no-booking", "Never book.")])
    assert [(c.id, c.source, c.strength, c.provenance) for c in declared.criteria] == [
        ("asks-budget", "declared", "must_hold", "check:asks-budget"),
        ("no-booking", "declared", "must_hold", "check:no-booking"),
    ]
    earlier = history(
        [raised("R1", "Quote in yuan."), raised("R2", "Offer one alternative.", "should", "A plan is given.")],
        [raised("R1", "Quote every price in yuan with its basis.")],
    )
    kept = declared.sedimented(earlier)
    by_id = {criterion.id: criterion for criterion in kept.criteria}
    assert [criterion.id for criterion in kept.criteria] == ["asks-budget", "no-booking", "R1", "R2"]
    assert by_id["R1"].text == "Quote every price in yuan with its basis." and by_id["R1"].provenance.endswith(
        "round 2"
    )
    assert (by_id["R2"].strength, by_id["R2"].situation, by_id["R2"].source) == (
        "should",
        "A plan is given.",
        "sedimented",
    )
    assert kept.sedimented(earlier[:1]).of("sedimented").criteria[0].text == "Quote in yuan."
    drawn = (Criterion("derived-1", "Name the source of every price.", "derived", "should", "material:sop Step 4"),)
    grown = kept.derived((*drawn, Criterion("R1", "A clash.", "derived", "should", "material:sop")))
    assert [criterion.id for criterion in grown.criteria][-1] == "derived-1" and len(grown.criteria) == 5
    assert grown.confirmed(["derived-1"]).criteria[-1].strength == "must_hold"
    with pytest.raises(ValueError, match="only derived criteria"):
        grown.confirmed(["asks-budget"])
    with pytest.raises(ValueError, match="unique"):
        Standard((drawn[0], drawn[0]))
    assert grown.of("declared", "derived").criteria[-1].id == "derived-1" and len(grown.of("sedimented").criteria) == 2


def test_only_must_hold_criteria_decide_whether_the_standard_is_met():
    standard = Standard.declared([("asks-budget", "Ask the budget first.")]).derived(
        [Criterion("derived-1", "Name every source.", "derived", "should", "material:sop")]
    )
    assert satisfied(standard.of("derived"), [Item("derived-1", "pass")]) is None
    assert satisfied(standard, [Item("asks-budget", "unknown"), Item("derived-1", "fail")]) is None
    assert satisfied(standard, [Item("asks-budget", "pass"), Item("derived-1", "fail")]) is True
    assert satisfied(standard, [Item("asks-budget", "fail"), Item("derived-1", "pass")]) is False


@pytest.mark.asyncio
async def test_the_assessor_judges_every_criterion_and_refuses_a_partial_scorecard(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("Day 1: Reykjavik. Price: about 7000.")
    sessions = {
        "family": [
            Exchange("Plan a week in Iceland", execution("t1", "What is your budget?")),
            Exchange("About 70000", execution("t2", "Here is the plan.", [str(plan), str(tmp_path / "deck.pptx")])),
        ]
    }
    standard = Standard.declared([("asks-budget", "Ask the budget first."), ("no-booking", "Never book.")])
    provider = Provider(
        response("submit_verdicts", {"verdicts": [verdict("asks-budget", "pass")]}),
        response(
            "submit_verdicts",
            {"verdicts": [verdict("asks-budget", "pass", "family"), verdict("no-booking", "unknown", "nobody")]},
        ),
        response(
            "submit_verdicts",
            {
                "verdicts": [
                    verdict("asks-budget", "pass", "family", "What is your budget?"),
                    verdict("no-booking", "fail", "family", "Price: about 7000.", "Say prices follow booking time."),
                ]
            },
        ),
    )
    assessor = StandardAssessor(provider, standard, sources=("declared",), model="judge/model", effort="low")
    signal = await assessor.evaluate(sessions)
    assert [(item.id, item.result, item.expected) for item in signal.items] == [
        ("asks-budget", "pass", "Ask the budget first."),
        ("no-booking", "fail", "Never book."),
    ]
    assert signal.source == "standard" and signal.text == "" and signal.satisfied is False
    assert signal.metrics == {"must_hold_pass_rate": 0.5}
    rejected = [row["error"] for row in assessor.trace if row["event"] == "output.rejected"]
    assert "exactly one verdict per criterion" in rejected[0] and "did not happen" in rejected[1]
    told = json.loads(provider.requests[0]["messages"][1]["content"])
    assert [criterion["id"] for criterion in told["criteria"]] == ["asks-budget", "no-booking"]
    assert told["conversations"]["family"][1]["delivered"] == {"plan.md": plan.read_text(), "deck.pptx": ""}
    assert provider.requests[0]["model"] == "judge/model" and provider.requests[0]["reasoning_effort"] == "low"
    late = Execution("t3", [], [], {"timed_out": True, "timeout": 600, "explicit_reply": False})
    assert conversations({"late": [Exchange("Still there?", late)]})["late"][0]["stopped"] == (
        "no reply within 600 seconds; the turn was stopped"
    )
    assert await StandardAssessor(Provider(), Standard(), sources=("declared",)).evaluate(sessions) is None


@pytest.mark.asyncio
async def test_derivation_reads_only_the_norms_handed_over_and_fills_what_the_party_leaves():
    norms = {"sop": "Step 4: name the source of every price."}
    standard = Standard.declared([("asks-budget", "Ask the budget first.")])
    stray = {"criteria": [{"text": "Be kind.", "material": "sample-chat"}]}
    good = {"criteria": [{"text": "Name the source of every price.", "material": "sop", "section": "Step 4"}]}
    provider = Provider(response("submit_criteria", stray), response("submit_criteria", good))
    trace = []
    drawn = await derive(provider, norms, standard, trace=trace)
    assert [(c.id, c.source, c.strength, c.provenance) for c in drawn] == [
        ("derived-1", "derived", "should", "material:sop Step 4")
    ]
    assert "only from the norms given" in next(row["error"] for row in trace if row["event"] == "output.rejected")
    told = json.loads(provider.requests[0]["messages"][1]["content"])
    assert told == {"norms": norms, "party_criteria": [{"text": "Ask the budget first.", "situation": ""}]}
    assert await derive(Provider(), {}, standard) == ()
    handed = {"sop": norms["sop"]}
    later = Provider(
        response("submit_criteria", good),
        response("submit_verdicts", {"verdicts": [verdict("derived-1", "pass")]}),
        response("submit_criteria", {"criteria": []}),
        response("submit_verdicts", {"verdicts": [verdict("derived-1", "unknown")]}),
    )
    assessor = StandardAssessor(later, standard, sources=("derived",), norms=lambda: handed)
    sessions = {"family": [Exchange("Hi", execution("t1", "Hello"))]}
    first = await assessor.evaluate(sessions)
    assert [item.id for item in first.items] == ["derived-1"] and first.satisfied is None
    handed["price-rules"] = "Prices are quoted in yuan."
    await assessor.evaluate(sessions)
    derived_from = [json.loads(request["messages"][1]["content"]) for request in later.requests[::2]]
    assert [sorted(packet["norms"]) for packet in derived_from] == [["sop"], ["price-rules"]]
    assert assessor.record()["derived_from"] == ["price-rules", "sop"]
    with pytest.raises(ExchangeError, match="submission budget exhausted"):
        await derive(Provider(*[response("submit_criteria", stray)] * 2), norms, standard, max_calls=2)


@pytest.mark.asyncio
async def test_the_loop_hands_its_history_to_an_assessor_that_keeps_a_standard(tmp_path, analyses):
    card = "We are a family of two adults and one child with a budget of 8000 for the first week of October."
    requirement = Requirement(**{**REQUIREMENT, "id": "R1", "situation": "A traveller asks for a plan."})
    analyses.scripted.extend([CURATE.model_copy(update={"requirements": (requirement,)}), CURATE])

    async def curator(worker, provider, *, feedback=None, **_):
        return None

    provider = Provider(response("submit_verdicts", {"verdicts": [verdict("R1", "fail", "student", "Here.", "Ask.")]}))
    boundaries = Boundaries({"analyst": Sealed.of([card], tokens=["case-7"])}, log=tmp_path / "boundaries.jsonl")
    assessor = StandardAssessor(provider, sources=("sedimented",), boundaries=boundaries)
    session = Session.open(
        FakeWorker(tmp_path), Provider(), curator=curator, limits=Limits(max_rounds=3), boundaries=boundaries
    )
    await session.onboard()
    await session.trial(Conversation(Scripted("student", card), max_turns=1))
    assert await session.assess(assessor) == ()
    await session.analyse()
    assert await session.curate()
    await session.trial(Conversation(Scripted("student", card), max_turns=1))
    (signal,) = await session.assess(assessor)
    assert [(item.id, item.result, item.expected) for item in signal.items] == [("R1", "fail", REQUIREMENT["behavior"])]
    assert signal.satisfied is False and assessor.standard.criteria[0].provenance == "requirement R1, round 1"
    assert [item.basis for item in signal.items] == ["requirement"]
    told = json.loads(provider.requests[0]["messages"][1]["content"])
    assert told["criteria"][0]["situation"] == "A traveller asks for a plan."
    events = [json.loads(line) for line in (tmp_path / "boundaries.jsonl").read_text().splitlines()]
    assert not [row for row in events if row["event"] == "violation"]
    assert [row["where"] for row in events if row["event"] == "enter"].count("analyst") == 2


@pytest.mark.asyncio
async def test_a_declared_criterion_is_never_spared_while_a_sedimented_one_may_quote_a_customer(tmp_path):
    check = "Quote the seasonal surcharge of twelve percent before any total price reaches the traveller at all."
    card = "We are two adults and one child flying from Hangzhou to Reykjavik in the first week of December."
    boundaries = Boundaries({"analyst": Sealed.of([check, card])}, log=tmp_path / "boundaries.jsonl")
    sessions = {"family": [Exchange("Hi there", execution("t1", "Hello, where to?"))]}
    quoted = raised("R1", f"Confirm the party when the traveller writes: {card}", situation="A family writes in.")
    hidden = StandardAssessor(
        Provider(), Standard.declared([("surcharge", check)]), sources=("declared",), boundaries=boundaries
    )
    with pytest.raises(ExchangeError, match="analyst compartment: sealed information"):
        await hidden.evaluate(sessions)
    kept = StandardAssessor(
        Provider(response("submit_verdicts", {"verdicts": [verdict("R1", "unknown")]})),
        sources=("sedimented",),
        boundaries=boundaries,
    )
    kept.sediment(history([quoted]))
    assert [item.id for item in (await kept.evaluate(sessions)).items] == ["R1"]
