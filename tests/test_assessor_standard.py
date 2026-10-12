"""The evaluation side's standard keeps its three sources apart and its automatic Assessor judges faithfully."""

import json

import pytest

from experimental.cultivation.conversation import Conversation
from experimental.harness.assessor.rubric import (
    AssessmentPlan,
    Basis,
    Definition,
    EvidenceRequirement,
    LLMCheck,
    ProgramCheck,
    Reference,
    digest,
)
from experimental.harness.assessor.standard import Assessor, Criterion, Standard, conversations, satisfied
from experimental.harness.loop.session import Limits, Session
from experimental.harness.participation.compartment import Boundaries
from experimental.harness.participation.exchange import ExchangeError
from experimental.harness.participation.protocols import Exchange, Item
from experimental.harness.participation.requirements import Requirement
from experimental.harness.raven_adapter.worker import Execution
from experimental.harness.scenario.sealed import Sealed
from raven.contracts.llm_provider import LLMResponse, ToolCallRequest
from tests.test_iteration_run import CURATE, REQUIREMENT, FakeWorker, Scripted
from tests.test_iteration_run import analyses as analyses  # noqa: F401 -- the loop test's Analyst stand-in


@pytest.mark.asyncio
async def test_unreadable_deliverables_remain_unknown_and_programs_receive_execution_evidence(tmp_path):

    path = tmp_path / "missing.txt"
    provider = Provider()
    rule = Criterion(
        "file",
        Definition("Worker output", "The delivered document is readable.", ""),
        "declared",
        "gate",
        Basis((Reference("check:file", "The delivered document is readable.", ""),), ""),
        authority="external",
        assessment=AssessmentPlan(decision=None, required_checks=(ProgramCheck(verifier="readable_deliverables"),)),
    )
    assessor = Assessor(provider, Standard((rule,)), sources=("declared",))
    signal = await assessor.evaluate(
        {"delivery": [Exchange("Deliver it.", execution("turn", "Attached.", [str(path)]))]}
    )
    assert signal.satisfied is None and signal.items[0].result == "unknown"
    assert "FileNotFoundError" in signal.items[0].note
    episode = assessor.assessments[0]
    assert episode["evidence"]["executions"]["delivery"][0]["turn_id"] == "turn"
    assert not provider.requests


@pytest.mark.asyncio
async def test_resume_preserves_rubric_episodes_builder_and_meta_review(tmp_path):
    from experimental.harness.assessor.builder import RubricBuilder
    from experimental.harness.assessor.reviewer import MetaReviewer
    from experimental.harness.participation.requirements import ExternalRequirement

    rule = Criterion(
        "derived-1",
        Definition("Worker output", "A reply is produced.", ""),
        "derived",
        "gate",
        Basis((Reference("$task", "", digest("Reply.")),), "Fixture interpretation."),
        assessment=AssessmentPlan(decision=None, required_checks=(ProgramCheck(verifier="completed_turns"),)),
    )
    assessor = Assessor(
        Provider(response("submit_evaluation_review", {})),
        Standard((rule,)),
        task="Reply.",
        builder=RubricBuilder(read={"$task": digest("Reply.")}),
        reviewer=MetaReviewer(),
        keep=tmp_path / "standard.json",
    )
    await assessor.evaluate({"task": [Exchange("Reply.", execution("first", "Done."))]})
    assessor.constrain([ExternalRequirement(source="human", quote="A reply is required.", kind="gate")])
    assessor.keep.write_text(json.dumps(assessor.record()))
    resumed = Assessor(
        Provider(
            response(
                "submit_revision", {"note": "Keep the requirement until a complete decision method is available."}
            ),
            response("submit_verdicts", {"verdicts": [verdict(assessor.standard.criteria[-1].id, "pass")]}),
            response("submit_evaluation_review", {}),
        ),
        task="Reply.",
        builder=RubricBuilder(),
        reviewer=MetaReviewer(),
        keep=assessor.keep,
    )
    resumed.restore()
    assert resumed.standard == assessor.standard
    assert resumed.builder.record() == assessor.builder.record()
    assert resumed.reviewer.record() == assessor.reviewer.record()
    assert resumed.evidence == assessor.evidence
    await resumed.evaluate({"task": [Exchange("Reply.", execution("second", "Again."))]})
    assert len({row["id"] for row in resumed.assessments}) == 2
    assert resumed.assessments[0] == json.loads(json.dumps(assessor.assessments[0]))
    assert len(resumed.reviewer.reviews) == 2


class Provider:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    async def chat_with_retry(self, messages=None, tools=None, model=None, **kwargs):
        self.requests.append({"messages": messages, "tools": tools, "model": model, **kwargs})
        return self.responses.pop(0)

    def get_default_model(self):
        return "assessor/default"


def response(name, arguments):
    return LLMResponse(content=None, tool_calls=[ToolCallRequest(name, name, arguments)])


def execution(turn_id, reply, deliverables=()):
    records = [{"kind": "runner.event", "event_type": "Text", "event": {"content": reply}}]
    return Execution(turn_id, [], records, {}, "artifact-1", tuple(deliverables))


def history(*rounds):
    return [{"round": number, "requirements": list(raised)} for number, raised in enumerate(rounds, 1)]


def raised(id, behavior, strength="must_hold", situation="", acceptance=""):
    return {
        "id": id,
        "behavior": behavior,
        "strength": strength,
        "situation": situation,
        "acceptance": acceptance or behavior,
    }


def verdict(id, result, session=None, actual="", note=""):
    return {"id": id, "result": result, "session": session, "actual": actual, "note": note}


async def test_factual_evidence_reaches_the_judge_without_becoming_builder_norms(tmp_path):
    facts = {"listing": "The voucher is valid for 90 days."}
    rule = Criterion(
        "validity",
        Definition("Voucher claim", "Match the supplied validity period."),
        "declared",
        "gate",
        Basis((Reference("check:validity", "Match the supplied validity period."),)),
        assessment=AssessmentPlan(evidence_requirements=(EvidenceRequirement("material", "listing"),)),
    )
    provider = Provider(*[response("submit_verdicts", {"verdicts": [verdict("validity", "pass")]}) for _ in range(2)])
    assessor = Assessor(
        provider,
        Standard((rule,)),
        sources=("declared",),
        norms={"policy": "Claims must match the adopted source."},
        materials=lambda: facts,
        keep=tmp_path / "standard.json",
    )
    sessions = {"one": [Exchange("How long?", execution("turn", "90 days."))]}
    result = await assessor.evaluate(sessions)
    assert result.items[0].result == "pass"
    packet = json.loads(provider.requests[0]["messages"][1]["content"])
    assert packet["materials"]["listing"] == facts["listing"]
    assert packet["criteria"][0]["evidence_gaps"] == []
    assert assessor.norms() == {"policy": "Claims must match the adopted source."}
    frozen = assessor.assessments[0]["evidence"]
    facts["listing"] = "The voucher is valid for 30 days."
    await assessor._measure(provider, sessions, evidence=frozen)
    replay = json.loads(provider.requests[1]["messages"][1]["content"])
    assert replay["materials"]["listing"] == "The voucher is valid for 90 days."
    saved = json.loads(assessor.keep.read_text())
    assert saved["assessments"][0]["evidence"]["materials"]["listing"] == "The voucher is valid for 90 days."


def test_the_standard_keeps_its_sources_apart_and_the_counterpart_first():
    declared = Standard.declared([("asks-budget", "Ask the budget first."), ("no-booking", "Never book.")])
    assert [(c.id, c.origin, c.strength, c.basis.references[0].source) for c in declared.criteria] == [
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
    assert (
        by_id["R1"].definition.acceptance == "Quote every price in yuan with its basis."
        and by_id["R1"].basis.derivation.find("round 2") >= 0
    )
    assert (by_id["R2"].strength, by_id["R2"].definition.applies_when, by_id["R2"].origin) == (
        "should",
        "A plan is given.",
        "sedimented",
    )
    assert kept.sedimented(earlier[:1]).of("sedimented").criteria[0].definition.acceptance == "Quote in yuan."
    drawn = (
        Criterion(
            "derived-1",
            Definition("Worker output", "Name the source of every price.", ""),
            "derived",
            "quality",
            Basis((Reference("sop", "", ""),), "Fixture interpretation."),
        ),
    )
    grown = Standard((*kept.criteria, *drawn))
    assert [criterion.id for criterion in grown.criteria][-1] == "derived-1" and len(grown.criteria) == 5
    assert grown.confirmed(["derived-1"]).criteria[-1].strength == "must_hold"
    with pytest.raises(ValueError, match="only derived criteria"):
        grown.confirmed(["asks-budget"])
    with pytest.raises(ValueError, match="unique"):
        Standard((drawn[0], drawn[0]))
    assert grown.of("declared", "derived").criteria[-1].id == "derived-1" and len(grown.of("sedimented").criteria) == 2


def test_only_must_hold_criteria_decide_whether_the_standard_is_met():
    standard = Standard(
        (
            *Standard.declared([("asks-budget", "Ask the budget first.")]).criteria,
            Criterion(
                "derived-1",
                Definition("Worker output", "Name every source.", ""),
                "derived",
                "quality",
                Basis((Reference("sop", "", ""),), "Fixture interpretation."),
            ),
        )
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
    assessor = Assessor(provider, standard, sources=("declared",), model="assessor/model", effort="low")
    signal = await assessor.evaluate(sessions)
    assert [(item.id, item.result, item.expected) for item in signal.items] == [
        ("asks-budget", "pass", "Ask the budget first."),
        ("no-booking", "fail", "Never book."),
    ]
    assert signal.source == "assessor" and signal.text == "" and signal.satisfied is False
    assert signal.metrics == {"must_hold_pass_rate": 0.5}
    rejected = [row["error"] for row in assessor.trace if row["event"] == "output.rejected"]
    assert "exactly one verdict per criterion" in rejected[0] and "did not happen" in rejected[1]
    told = json.loads(provider.requests[0]["messages"][1]["content"])
    assert [criterion["id"] for criterion in told["criteria"]] == ["asks-budget", "no-booking"]
    assert told["conversations"]["family"][1]["delivered"] == {"plan.md": plan.read_text(), "deck.pptx": ""}
    assert provider.requests[0]["model"] == "assessor/model" and provider.requests[0]["reasoning_effort"] == "low"
    late = Execution("t3", [], [], {"timed_out": True, "timeout": 600, "explicit_reply": False})
    assert conversations({"late": [Exchange("Still there?", late)]})["late"][0]["stopped"] == (
        "no reply within 600 seconds; the turn was stopped"
    )
    assert await Assessor(Provider(), Standard(), sources=("declared",)).evaluate(sessions) is None


@pytest.mark.asyncio
async def test_the_loop_hands_its_history_to_an_assessor_that_keeps_a_standard(tmp_path, analyses):
    card = "We are a family of two adults and one child with a budget of 8000 for the first week of October."
    requirement = Requirement(**{**REQUIREMENT, "id": "R1", "situation": "A traveller asks for a plan."})
    analyses.scripted.extend([CURATE.model_copy(update={"requirements": (requirement,)}), CURATE])

    async def curator(worker, provider, *, feedback=None, **_):
        return None

    provider = Provider(response("submit_verdicts", {"verdicts": [verdict("R1", "fail", "student", "Here.", "Ask.")]}))
    boundaries = Boundaries({"analyst": Sealed.of([card], tokens=["case-7"])}, log=tmp_path / "boundaries.jsonl")
    assessor = Assessor(provider, sources=("sedimented",), boundaries=boundaries)
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
    assert [(item.id, item.result, item.expected) for item in signal.items] == [
        ("R1", "fail", REQUIREMENT["behavior"] + "\n" + REQUIREMENT["acceptance"])
    ]
    assert signal.satisfied is False and assessor.standard.criteria[0].basis.references[0].source == "requirement:R1"
    assert [item.basis for item in signal.items] == ["requirement"]
    told = json.loads(provider.requests[0]["messages"][1]["content"])
    assert told["criteria"][0]["definition"]["applies_when"] == "A traveller asks for a plan."
    events = [json.loads(line) for line in (tmp_path / "boundaries.jsonl").read_text().splitlines()]
    assert not [row for row in events if row["event"] == "violation"]
    assert [row["where"] for row in events if row["event"] == "enter"].count("analyst") == 2


@pytest.mark.asyncio
async def test_a_declared_criterion_is_never_spared_while_a_sedimented_one_may_quote_a_customer(tmp_path):
    check = "Quote the seasonal surcharge of twelve percent before any total price reaches the traveller at all."
    card = "We are two adults and one child flying from Hangzhou to Reykjavik in the first week of December."
    boundaries = Boundaries({"analyst": Sealed.of([check, card])}, log=tmp_path / "boundaries.jsonl")
    sessions = {"family": [Exchange("Hi there", execution("t1", "Hello, where to?"))]}
    quoted = raised("R1", f"Confirm the counterpart when the traveller writes: {card}", situation="A family writes in.")
    hidden = Assessor(
        Provider(), Standard.declared([("surcharge", check)]), sources=("declared",), boundaries=boundaries
    )
    with pytest.raises(ExchangeError, match="analyst compartment: sealed information"):
        await hidden.evaluate(sessions)
    kept = Assessor(
        Provider(response("submit_verdicts", {"verdicts": [verdict("R1", "unknown")]})),
        sources=("sedimented",),
        boundaries=boundaries,
    )
    kept.sediment(history([quoted]))
    assert [item.id for item in (await kept.evaluate(sessions)).items] == ["R1"]


@pytest.mark.asyncio
async def test_a_judge_of_held_out_cases_runs_on_the_evaluation_side_where_their_files_are_not_sealed(tmp_path):
    handout = "Itinerary draft: two adults, one child, Reykjavik, the first week of December, budget open."
    boundaries = Boundaries(
        {"analyst": Sealed.of([handout]), "counterpart": Sealed.of([])}, log=tmp_path / "boundaries.jsonl"
    )
    sessions = {"holdout-family": [Exchange("Please check this", execution("t1", f"I read it: {handout}"))]}
    standard = Standard.declared([("surcharge", "Quote the seasonal surcharge first.")])
    analyst_side = Assessor(Provider(), standard, sources=("declared",), boundaries=boundaries)
    with pytest.raises(ExchangeError, match="analyst compartment: sealed information"):
        await analyst_side.evaluate(sessions)
    judge = Assessor(
        Provider(response("submit_verdicts", {"verdicts": [verdict("surcharge", "pass")]})),
        standard,
        sources=("declared",),
        boundaries=boundaries,
        compartment="counterpart",
    )
    assert [item.result for item in (await judge.evaluate(sessions)).items] == ["pass"]


@pytest.mark.parametrize(
    ("items", "expected"),
    [
        ([Item("complete", "pass"), Item("budget", "unknown")], None),
        ([Item("complete", "pass")], None),
        ([Item("complete", "fail"), Item("budget", "unknown")], False),
        ([Item("complete", "pass"), Item("budget", "not_applicable")], True),
        ([Item("complete", "not_applicable"), Item("budget", "not_applicable")], None),
    ],
)
def test_a_hard_gate_needs_all_applicable_evidence(items, expected):
    standard = Standard.declared([("complete", "Include required costs."), ("budget", "Stay within the budget.")])
    assert satisfied(standard, items) is expected


def test_sedimentation_does_not_upgrade_model_inference_or_weaken_an_external_requirement():
    model = raised("R1", "Include tax.") | {"authority": "model", "grounds": ["check:derived-1"]}
    external = raised("R1", "Include local tax.") | {"authority": "external", "grounds": ["assessor:human"]}
    weakening = raised("R1", "Tax is optional.", strength="should") | {"authority": "model"}
    standard = Standard().sedimented(history([model]))
    assert standard.criteria[0].authority == "model" and standard.criteria[0].strength == "must_hold"
    standard = standard.sedimented(history([model], [external], [weakening]))
    assert standard.criteria[0].authority == "external"
    assert (
        standard.criteria[0].definition.acceptance == "Include local tax."
        and standard.criteria[0].strength == "must_hold"
    )
    assert "assessor:human" in standard.criteria[0].basis.derivation
    updated = raised("R1", "Include regional tax.") | {"authority": "external"}
    assert (
        standard.sedimented(history([external], [updated])).criteria[0].definition.acceptance == "Include regional tax."
    )


@pytest.mark.asyncio
async def test_all_necessary_checks_run_and_the_program_failure_survives_a_model_pass():
    from experimental.harness.assessor.checks import Finding

    seen = []

    async def cost_check(evidence):
        seen.append(evidence["conversations"]["quote"][0]["assistant"])
        return Finding("fail", "Subtotal: 100.", "Tax was not included.", "quote")

    criterion = Criterion(
        "costs",
        Definition("Worker output", "Include all costs.", ""),
        "declared",
        "gate",
        Basis((Reference("check:costs", "Include all costs.", ""),), ""),
        authority="external",
        assessment=AssessmentPlan(decision=LLMCheck(), required_checks=(ProgramCheck(verifier="cost_check"),)),
    )
    provider = Provider(response("submit_verdicts", {"verdicts": [verdict("costs", "pass", "quote")]}))
    assessor = Assessor(provider, Standard((criterion,)), sources=("declared",), verifiers={"cost_check": cost_check})
    signal = await assessor.evaluate({"quote": [Exchange("Quote it.", execution("t1", "Subtotal: 100."))]})
    assert seen == ["Subtotal: 100."] and signal.satisfied is False
    assert signal.items[0].actual == "Subtotal: 100." and signal.items[0].authority == "external"
    assert [check["result"] for check in assessor.record()["assessments"][0]["checks"]] == ["pass", "fail"]


@pytest.mark.asyncio
async def test_local_passes_do_not_establish_a_complete_semantic_claim():
    from experimental.harness.assessor.checks import Finding

    async def a_number_exists(evidence):
        return Finding("pass", actual="Subtotal: 100.")

    criterion = Criterion(
        "complete",
        Definition("Final quote", "Include every necessary cost and applicable tax."),
        "declared",
        "gate",
        Basis((Reference("check:complete", "Include every necessary cost and applicable tax."),)),
        assessment=AssessmentPlan(decision=None, required_checks=(ProgramCheck(verifier="number_exists"),)),
    )
    assessor = Assessor(
        Provider(), Standard((criterion,)), sources=("declared",), verifiers={"number_exists": a_number_exists}
    )
    signal = await assessor.evaluate({"quote": [Exchange("Quote.", execution("t", "Subtotal: 100."))]})
    assert signal.satisfied is None and "local passes are insufficient" in signal.items[0].note
    assert [row["role"] for row in assessor.assessments[0]["checks"]] == ["decision", "required"]


@pytest.mark.asyncio
async def test_a_program_decision_requires_calibration_bound_to_its_exact_contract():
    from dataclasses import replace

    from experimental.harness.assessor.checks import Finding
    from experimental.harness.assessor.standard import observations

    async def all_costs(evidence):
        text = evidence["conversations"]["quote"][0]["assistant"]
        return Finding("pass" if "tax: 10" in text else "fail", actual=text)

    check = ProgramCheck(verifier="costs")
    criterion = Criterion(
        "tax",
        Definition("Final quote", "Include the required tax."),
        "declared",
        "gate",
        Basis((Reference("task", "Include the required tax.", "source-v1"),)),
        assessment=AssessmentPlan(decision=check),
    )
    invalid = {"quote": [Exchange("Quote.", execution("bad", "Subtotal: 100."))]}
    valid = {"quote": [Exchange("Quote.", execution("good", "Subtotal: 100; tax: 10."))]}
    examples = ((observations(valid), True), (observations(invalid), False))
    assessor = Assessor(Provider(), Standard((criterion,)), sources=("declared",), verifiers={"costs": all_costs})
    assert (await assessor.evaluate(valid)).satisfied is None
    assessor.calibrations[criterion.calibration_key(check)] = examples
    assert (await assessor.evaluate(valid)).satisfied is True
    assert (await assessor.evaluate(invalid)).satisfied is False
    changed = replace(criterion, basis=Basis((Reference("task", "Include the required tax.", "source-v2"),)))
    assessor.standard = Standard((changed,))
    assert (await assessor.evaluate(valid)).satisfied is None


@pytest.mark.asyncio
async def test_required_evidence_blocks_a_model_pass_and_is_visible_to_the_judge(tmp_path):
    from experimental.harness.assessor.rubric import EvidenceRequirement

    definition = Definition("Final quote document", "Cover every required fee.", "A quote was requested.")
    criterion = Criterion(
        "content",
        definition,
        "declared",
        "gate",
        Basis((Reference("task", "Cover every required fee."),)),
        assessment=AssessmentPlan(evidence_requirements=(EvidenceRequirement("delivered_text", "quote.md"),)),
    )
    provider = Provider(response("submit_verdicts", {"verdicts": [verdict("content", "pass")]}))
    assessor = Assessor(provider, Standard((criterion,)), sources=("declared",))
    signal = await assessor.evaluate(
        {"quote": [Exchange("Quote.", execution("t", "Attached.", (str(tmp_path / "quote.md"),)))]}
    )
    assert signal.satisfied is None and "FileNotFoundError" in signal.items[0].note
    packet = json.loads(provider.requests[0]["messages"][1]["content"])["criteria"][0]
    assert packet["definition"]["subject"] == "Final quote document"
    assert packet["evidence_requirements"] == [{"kind": "delivered_text", "reference": "quote.md"}]
    assert packet["evidence_gaps"]


def test_legacy_records_remain_read_only_instead_of_inventing_semantic_contracts(tmp_path):
    path = tmp_path / "standard.json"
    value = {
        "criteria": [
            {"id": "old", "text": "Do the task.", "source": "declared", "strength": "must_hold", "provenance": "task"}
        ]
    }
    path.write_text(json.dumps(value))
    assessor = Assessor(Provider(), sources=("declared",), keep=path)
    with pytest.raises(ValueError, match="must be rebuilt"):
        assessor.restore()
    assert json.loads(path.read_text()) == value


@pytest.mark.asyncio
async def test_case_references_join_the_evidence_the_assessor_judges_with():
    standard = Standard.declared([("send-date", "Send on the date the calendar gives.")])
    provider = Provider(response("submit_verdicts", {"verdicts": [verdict("send-date", "pass", "exam")]}))
    sessions = {"exam": [Exchange("When will it go out?", execution("t1", "On 14 October at 10:00."))]}
    computed = {"exam": {"expected": "14 October, between 10:00 and 20:00", "dates": ["10-14"]}, "idle": {}}
    assessor = Assessor(provider, standard, sources=("declared",), references=lambda given: computed)
    signal = await assessor.evaluate(sessions)
    assert signal.items[0].result == "pass"
    told = json.loads(provider.requests[0]["messages"][1]["content"])
    assert told["references"] == {"exam": computed["exam"]}
    plain = Provider(response("submit_verdicts", {"verdicts": [verdict("send-date", "pass", "exam")]}))
    await Assessor(plain, standard, sources=("declared",)).evaluate(sessions)
    assert "references" not in json.loads(plain.requests[0]["messages"][1]["content"])


async def test_declared_applicability_survives_judgment_and_retained_standard(tmp_path):
    condition = "The requested publication date is on or after 2026-10-28."
    standard = Standard.declared(
        [("citation", "Include the publication citation.")], applies_when={"citation": condition}
    )
    provider = Provider(
        response(
            "submit_verdicts",
            {"verdicts": [verdict("citation", "not_applicable", note="The request is dated 2026-10-20.")]},
        )
    )
    assessor = Assessor(provider, standard, sources=("declared",), keep=tmp_path / "standard.json")
    sessions = {"earlier": [Exchange("Publish on 2026-10-20.", execution("date", "Confirmed."))]}
    signal = await assessor.evaluate(sessions)
    assert signal.items[0].result == "not_applicable" and signal.satisfied is None
    packet = json.loads(provider.requests[0]["messages"][1]["content"])
    assert packet["criteria"][0]["definition"]["applies_when"] == condition
    saved = json.loads(assessor.keep.read_text())
    assert saved["criteria"][0]["definition"]["applies_when"] == condition


def _named(*points):
    return "".join(map(chr, points))


SCRIPT = _named(0x53E3, 0x64AD, 0x7A3F)
LEDGER = _named(0x53D1, 0x5E03, 0x53F0, 0x8D26)
SCRIPT_NORMS = "Deliver every script as a file and register it in the shared ledger."


def _script_rule(id, reference):
    return Criterion(
        id,
        Definition("Script files and ledger", SCRIPT_NORMS, "A script is requested."),
        "derived",
        "gate",
        Basis((Reference("script-norms", SCRIPT_NORMS, digest(SCRIPT_NORMS)),)),
        assessment=AssessmentPlan(
            evidence_requirements=(
                EvidenceRequirement("conversation"),
                EvidenceRequirement("execution"),
                EvidenceRequirement("delivered_text", reference),
                EvidenceRequirement("material", "script-norms"),
            )
        ),
    )


def _script_sessions(tmp_path):
    first, revised = tmp_path / f"{SCRIPT}-KB-1020-01.md", tmp_path / f"{SCRIPT}-KB-1020-01-v2.md"
    first.write_text("# KB-1020-01 v1\n1. First line.")
    revised.write_text("# KB-1020-01 v2\n1. Revised line.")
    sessions = {
        "s1": [
            Exchange("Write the script.", execution("t1", "Attached.", [str(first)])),
            Exchange("Revise it.", execution("t2", "Attached.", [str(revised)])),
        ]
    }
    filed = {
        "s1": {
            "filed": {
                f"workdir/{LEDGER}/{LEDGER}.md": "| date | id |\n| 2026-10-20 | KB-1020-01 |",
                f"workdir/{SCRIPT}/{first.name}": first.read_text(),
            }
        }
    }
    return sessions, filed


async def test_a_descriptive_delivered_text_reference_is_read_as_all_delivered_text(tmp_path):
    # Shaped after a recorded run whose references described the files instead of naming them.
    rules = (
        _script_rule("derived-12", "All initial and revised script files"),
        _script_rule("derived-13", f"Script versions and the updated {LEDGER}/{LEDGER}.md"),
    )
    sessions, filed = _script_sessions(tmp_path)
    provider = Provider(
        response("submit_verdicts", {"verdicts": [verdict("derived-12", "pass"), verdict("derived-13", "pass")]})
    )
    assessor = Assessor(
        provider,
        Standard(rules),
        sources=("derived",),
        norms={"script-norms": SCRIPT_NORMS},
        references=lambda given: filed,
    )
    signal = await assessor.evaluate(sessions)
    assert [item.result for item in signal.items] == ["pass", "pass"] and signal.satisfied is True
    packet = json.loads(provider.requests[0]["messages"][1]["content"])
    assert [job["evidence_gaps"] for job in packet["criteria"]] == [[], []]
    assert all("names no delivered or filed file" in job["evidence_notes"][0] for job in packet["criteria"])
    assert all("judged against all delivered text and filed files" in item.note for item in signal.items)
    assert set(assessor.assessments[0]["evidence_notes"]) == {"derived-12", "derived-13"}


async def test_a_reference_naming_a_filed_path_needs_no_delivery_and_no_text_at_all_is_still_a_gap(tmp_path):
    sessions, filed = _script_sessions(tmp_path)
    provider = Provider(response("submit_verdicts", {"verdicts": [verdict("ledger", "pass")]}))
    assessor = Assessor(
        provider,
        Standard((_script_rule("ledger", f"{LEDGER}/{LEDGER}.md"),)),
        sources=("derived",),
        norms={"script-norms": SCRIPT_NORMS},
        references=lambda given: filed,
    )
    assert (await assessor.evaluate(sessions)).items[0].result == "pass"
    job = json.loads(provider.requests[0]["messages"][1]["content"])["criteria"][0]
    assert (job["evidence_gaps"], job["evidence_notes"]) == ([], [])

    silent = {"s1": [Exchange("Write the script.", execution("t1", "I will send it later."))]}
    provider = Provider(response("submit_verdicts", {"verdicts": [verdict("files", "pass")]}))
    assessor = Assessor(
        provider,
        Standard((_script_rule("files", "All initial and revised script files"),)),
        sources=("derived",),
        norms={"script-norms": SCRIPT_NORMS},
    )
    item = (await assessor.evaluate(silent)).items[0]
    assert item.result == "unknown" and "No delivered text is available" in item.note


def _resume_rule(*, required=(), reference="", sources=None):
    acceptance = (
        "Keep the page within the line limit, cut over-long drafts in the stated order, and describe skills concretely."
    )
    return Criterion(
        "derived-5",
        Definition("Resume structure and one-page format", acceptance, "A resume revision is requested."),
        "derived",
        "gate",
        Basis(tuple(Reference(name, acceptance, digest(acceptance)) for name in (sources or ("resume-template",)))),
        assessment=AssessmentPlan(
            required_checks=tuple(LLMCheck(text) for text in required),
            evidence_requirements=(EvidenceRequirement("delivered_text", reference),),
        ),
    )


async def test_an_observed_failure_is_not_hidden_by_an_undecidable_condition_or_an_evidence_gap(tmp_path):
    # Shaped after a recorded run where one unobservable condition masked a failing one.
    acceptance = _resume_rule().definition.acceptance
    norms = {"resume-template": acceptance}
    resume = tmp_path / "resume.md"
    resume.write_text("# Name\n## Skills\n- Good at computers")
    sessions = {"s1": [Exchange("Revise my resume.", execution("t1", "Attached.", [str(resume)]))]}
    undecided = verdict("derived-5", "unknown", note="The order of cuts is not observable.")
    failing = verdict(
        "derived-5:required-1", "fail", "s1", "- Good at computers", "Name an exam or software functions."
    )
    rule = _resume_rule(required=("Each computer-skills line names an exam or concrete software functions.",))
    provider = Provider(response("submit_verdicts", {"verdicts": [undecided, failing]}))
    signal = await Assessor(provider, Standard((rule,)), sources=("derived",), norms=norms).evaluate(sessions)
    assert (signal.items[0].result, signal.items[0].actual, signal.satisfied) == ("fail", "- Good at computers", False)

    gapped = _resume_rule(reference="resume.pdf")
    pdf = tmp_path / "resume.pdf"
    pdf.write_bytes(b"%PDF")
    sessions = {"s1": [Exchange("Revise my resume.", execution("t1", "Attached.", [str(resume), str(pdf)]))]}
    observed = verdict("derived-5", "fail", "s1", "- Good at computers", "Name an exam or software functions.")
    provider = Provider(response("submit_verdicts", {"verdicts": [observed]}))
    item = (await Assessor(provider, Standard((gapped,)), sources=("derived",), norms=norms).evaluate(sessions)).items[
        0
    ]
    assert item.result == "fail" and "dedicated verifier" in item.note

    provider = Provider(response("submit_verdicts", {"verdicts": [observed]}))
    changed = {"resume-template": acceptance + " Revised."}
    stale = await Assessor(provider, Standard((gapped,)), sources=("derived",), norms=changed).evaluate(sessions)
    assert stale.items[0].result == "unknown" and "rebuild its interpretation" in stale.items[0].note
