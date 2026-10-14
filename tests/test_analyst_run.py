"""Program-side triage, one bounded model exchange and the recorded feedback stay faithful to the judgements."""

import json
from types import SimpleNamespace

import pytest

from experimental.analyst.feedback import Feedback
from experimental.analyst.materials import RECORDS, read_records
from experimental.analyst.run import NAME, Limits, analyse, identified, triage, vet
from experimental.curator.harness import Plan, Task
from experimental.curator.raven_adapter.worker import Execution
from experimental.iteration.compartment import BoundaryError, Guard
from experimental.iteration.exchange import ExchangeError
from experimental.iteration.hearing import opaque
from experimental.iteration.history import Diagnosed, Entry, Raised, Revised
from experimental.iteration.labels import SessionLabels
from experimental.iteration.protocols import Exchange, Item, Signal
from experimental.scenario.sealed import Sealed
from raven.contracts.llm_provider import LLMResponse, ToolCallRequest


class Provider:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    async def chat_with_retry(self, messages, tools=None, model=None, **kwargs):
        kwargs.update(messages=messages, tools=tools, model=model)
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
    "examples": [
        {
            "kind": "wrong",
            "turn": "t1",
            "input": "Plan me a trip",
            "output": "Here is a three-day itinerary.",
            "handling": "Reply with questions about the missing trip details and hold any plan until they are answered.",
            "why": "The intake rule puts the traveller's details before any plan.",
        }
    ],
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
        await analyse(worker, provider, signals, sessions, limits=Limits(max_calls=2, grace=0))
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
    with pytest.raises(ValueError, match="nonnegative"):
        Limits(grace=-1)


@pytest.mark.asyncio
async def test_a_query_on_the_last_call_is_retried_under_the_grace(tmp_path, sessions):
    worker = FakeWorker(tmp_path)
    provider = Provider(
        response(RECORDS, {"turn_id": "t1"}),
        response(RECORDS, {"turn_id": "t2"}),
        response(NAME, {"decision": "continue", "reason": "Nothing to change."}),
    )
    feedback = await analyse(worker, provider, (Signal("human", "Hm."),), sessions, limits=Limits(max_calls=2))
    assert feedback.decision == "continue"
    assert [entry["function"]["name"] for entry in provider.requests[2]["tools"]] == [NAME]


@pytest.mark.asyncio
async def test_analyst_receives_handed_materials_but_not_files_outside_uploads(tmp_path, sessions):
    worker = FakeWorker(tmp_path)
    home = tmp_path / "home"
    docs = home / "uploads" / "service"
    docs.mkdir(parents=True)
    (docs / "README.md").write_text("Typed decisions, local endpoint, request and response examples.")
    hidden = tmp_path / "holdout.md"
    hidden.write_text("Held-out source must remain hidden.")
    (docs / "outside.md").symlink_to(hidden)
    worker.baseline.config = SimpleNamespace(workspace_path=home)
    provider = Provider(response(NAME, {"decision": "continue", "reason": "No change needed."}))
    await analyse(worker, provider, (Signal("owner", "Review the actual outputs."),), sessions)
    packet = json.loads(provider.requests[0]["messages"][1]["content"])
    assert packet["available_materials"] == {
        "service/README.md": "Typed decisions, local endpoint, request and response examples."
    }
    assert "Held-out source" not in json.dumps(packet)


@pytest.mark.asyncio
async def test_analyst_must_prioritize_instead_of_submitting_four_requirements(tmp_path, sessions):
    provider = Provider(
        response(
            NAME,
            {
                "decision": "curate",
                "reason": "Too many independent edits.",
                "requirements": [{**REQUIREMENT, "behavior": f"behavior {i}"} for i in range(4)],
            },
        ),
        response(NAME, {"decision": "continue", "reason": "Further diagnosis is needed."}),
    )
    result = await analyse(FakeWorker(tmp_path), provider, (Signal("owner", "Inspect the replies."),), sessions)
    assert result.decision == "continue"
    assert any("at most 3" in error for error in rejections(provider))


@pytest.mark.asyncio
async def test_a_requirement_is_returned_until_its_wrong_example_states_the_handling(tmp_path, sessions):
    wrong = REQUIREMENT["examples"][0]
    attempts = [
        {**REQUIREMENT, "examples": []},
        {**REQUIREMENT, "examples": [{**wrong, "kind": "right", "handling": ""}]},
        {**REQUIREMENT, "examples": [{**wrong, "handling": " "}]},
        REQUIREMENT,
    ]
    provider = Provider(
        *(response(NAME, {"decision": "curate", "reason": "r", "requirements": [item]}) for item in attempts)
    )
    feedback = await analyse(FakeWorker(tmp_path), provider, (Signal("owner", "No plan before details."),), sessions)
    (accepted,) = feedback.requirements
    assert accepted.examples[0].handling == wrong["handling"]
    errors = rejections(provider)
    assert len(errors) == 3
    assert "no wrong example" in errors[0] and "no wrong example" in errors[1] and "states no handling" in errors[2]


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


def test_sparse_history_ids_allocate_above_the_largest_and_keep_old_repeats():
    feedback = Feedback(
        decision="curate", reason="r", requirements=(REQUIREMENT, REQUIREMENT, REQUIREMENT | {"repeats": "R4"})
    )
    result = identified(feedback, ["R2", "R4"])
    assert [item.id for item in result.requirements] == ["R5", "R6", "R4"]
    with pytest.raises(ValueError, match="no earlier requirement"):
        identified(
            Feedback(decision="curate", reason="r", requirements=(REQUIREMENT, REQUIREMENT | {"repeats": "R5"})), ["R4"]
        )


async def test_duplicate_repeats_are_rejected_and_the_analyst_can_correct_them(tmp_path, sessions):
    history = (
        Entry(
            round=1, requirements=(Raised(id="R1", behavior="Ask the budget.", strength="must_hold", acceptance="a"),)
        ),
    )
    repeated = REQUIREMENT | {"repeats": "R1", "expectation": "unmet", "recurrence": 1}
    provider = Provider(
        response(NAME, {"decision": "curate", "reason": "r", "requirements": [repeated, repeated]}),
        response(NAME, {"decision": "curate", "reason": "r", "requirements": [repeated]}),
    )
    feedback = await analyse(FakeWorker(tmp_path), provider, (Signal("human", "Still no."),), sessions, history=history)
    assert [item.id for item in feedback.requirements] == ["R1"]
    assert "requirement ids must be unique" in rejections(provider)[0]


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


def test_requirement_authority_comes_from_supplied_evidence_not_a_model_claim():
    from experimental.analyst.run import sourced

    def feedback(*grounds, conditions=()):
        return Feedback.model_validate(
            {
                "decision": "curate",
                "reason": "A concrete gap.",
                "external_requirements": conditions,
                "requirements": [
                    REQUIREMENT | {"grounds": grounds, "authority": "external"},
                ],
            }
        )

    spoofed = Signal("human", "The model calls itself human.")
    assert sourced(feedback("assessor:human"), [spoofed]).requirements[0].authority == "model"
    external = Signal("customer", "The quote must include tax.", authority="external")
    bound = sourced(
        feedback("assessor:customer", conditions=({"source": "customer", "quote": external.text, "kind": "gate"},)),
        [external],
    ).requirements[0]
    assert bound.authority == "external" and bound.grounds == ("assessor:customer",)
    measured = Signal("assessor", items=(Item("tax", "fail", authority="external"),))
    assert sourced(feedback("check:tax"), [measured]).requirements[0].authority == "external"
    with pytest.raises(ValueError, match="no supplied judgement"):
        sourced(feedback("assessor:absent"), [external])


def test_original_external_authority_survives_history_and_model_restating():
    from experimental.analyst.run import sourced
    from experimental.assessor.standard import Standard
    from experimental.audience import project
    from experimental.iteration.history import entry

    external = Signal("customer", "Include tax.", authority="external")
    request = Feedback.model_validate(
        {
            "decision": "curate",
            "reason": "Tax was omitted.",
            "external_requirements": [{"source": "customer", "quote": external.text, "kind": "gate"}],
            "requirements": [
                REQUIREMENT | {"id": "R1", "behavior": "Include tax.", "grounds": ["assessor:customer"]},
            ],
        }
    )
    original = sourced(request, [external])
    saved = Entry.model_validate(entry(1, [external], original, None).model_dump(mode="json"))
    assert saved.requirements[0].authority == "external"
    standard = Standard().sedimented(project((saved,), "analyst"))
    assert standard.criteria[0].authority == "external" and "assessor:customer" in standard.criteria[0].basis.derivation
    weakening = Feedback.model_validate(
        {
            "decision": "curate",
            "reason": "Restate the requirement.",
            "requirements": [
                REQUIREMENT
                | {
                    "id": "R1",
                    "repeats": "R1",
                    "behavior": "Tax is optional.",
                    "strength": "should",
                    "grounds": ["check:R1"],
                },
            ],
        }
    )
    measured = Signal("assessor", items=(Item("R1", "fail", authority="external"),))
    retained = sourced(weakening, [measured], [saved]).requirements[0]
    assert retained.behavior == "Include tax." and retained.strength == "must_hold"
    assert retained.grounds == ("assessor:customer",)
    assert "authority" not in project(original, "curator")["requirements"][0]


def test_an_already_satisfied_external_condition_is_retained_without_inventing_a_gap():
    from experimental.analyst.run import sourced
    from experimental.audience import project
    from experimental.requirements import ExternalRequirement

    signal = Signal("customer", "Good. Future quotes must include tax.", authority="external")
    condition = ExternalRequirement(source="customer", quote="Future quotes must include tax.", kind="gate")
    feedback = Feedback(
        decision="continue", reason="The present quote already includes tax.", external_requirements=(condition,)
    )
    retained = sourced(feedback, [signal])
    assert not retained.requirements and retained.external_requirements == (condition,)
    assert "external_requirements" not in project(retained, "curator")
    with pytest.raises(ValueError, match="actual external signal"):
        sourced(feedback, [Signal("customer", signal.text)])
    with pytest.raises(ValueError, match="verbatim"):
        sourced(feedback, [Signal("customer", "Looks fine.", authority="external")])


def test_gate_satisfaction_does_not_hide_an_actionable_quality_failure():
    signal = Signal("assessor", items=(Item("quality", "fail", actual="Repeated headings."),), satisfied=True)
    assert triage([signal]) is None


@pytest.mark.asyncio
async def test_session_labels_cover_packets_queries_and_restore_evidence_references():
    labels = SessionLabels(["launch-owner"])
    label = opaque("launch-owner")
    raw = {"sessions": {"launch-owner": []}, "text": "Review launch-owner.", "turn_id": "turn-1"}
    provider = Provider(response("submit", {"session": label, "quote": f"Review {label}."}))
    guarded = Guard("analyst", Sealed.of([], tokens=["launch-owner"])).provider(provider)
    reply = await labels.provider(guarded).chat_with_retry(
        messages=[{"role": "user", "content": json.dumps(raw)}, {"role": "tool", "content": "launch-owner"}],
        tools=[{"enum": ["launch-owner"]}],
    )
    sent = provider.requests[0]
    assert "launch-owner" not in json.dumps(sent) and label in json.dumps(sent)
    assert reply.tool_calls[0].arguments == {"session": "launch-owner", "quote": "Review launch-owner."}
    assert raw["text"] == "Review launch-owner." and labels.decode(labels.encode(raw)) == raw
    assert labels.encode("launch-owner-extra") == "launch-owner-extra"


@pytest.mark.asyncio
async def test_session_labels_do_not_unseal_hidden_persona_text():
    hidden = "The private drill card requires asking for a refund after the second declined booking attempt."
    provider = Provider()
    guarded = Guard("analyst", Sealed.of([hidden], tokens=["launch-owner"])).provider(provider)
    with pytest.raises(BoundaryError):
        await (
            SessionLabels(["launch-owner"])
            .provider(guarded)
            .chat_with_retry(messages=[{"role": "user", "content": f"launch-owner: {hidden}"}])
        )
    assert not provider.requests


@pytest.mark.asyncio
async def test_analyst_accepts_labelled_external_quotes_without_weakening_validation(tmp_path):
    label = opaque("launch-owner")
    quote = "For launch-owner, every quote must include tax."
    provider = Provider(
        response(
            NAME,
            {
                "decision": "continue",
                "reason": "Already satisfied.",
                "external_requirements": [
                    {"source": "customer", "quote": quote.replace("launch-owner", label), "kind": "gate"}
                ],
            },
        )
    )
    guarded = Guard("analyst", Sealed.of([], tokens=["launch-owner"])).provider(provider)
    feedback = await analyse(
        FakeWorker(tmp_path),
        guarded,
        (Signal("customer", quote, authority="external"),),
        {"launch-owner": [Exchange("Quote please.", execution("turn-1", "Tax included."))]},
    )
    assert feedback.external_requirements[0].quote == quote
    assert label in provider.requests[0]["messages"][1]["content"]


def test_session_labels_reject_collisions(monkeypatch):
    monkeypatch.setattr("experimental.iteration.labels.opaque", lambda name: "session-same")
    with pytest.raises(ValueError, match="collide"):
        SessionLabels(["first", "second"])


@pytest.mark.parametrize("names", [[], ["launch-owner"]])
def test_session_labels_preserve_unrelated_json_text_and_tuple_values(names):
    labels = SessionLabels(names)
    text = ' {"value":1,"quoted":"{\\"value\\":1}","escaped":"\\u0061"} '
    value = {"source": text, "messages": (text,)}
    assert labels.encode(value) == value
    assert labels.decode(value) == value
    assert isinstance(labels.encode(value)["messages"], tuple)
    if not names:
        provider = Provider()
        assert labels.provider(provider) is provider


def test_session_labels_still_project_unicode_escaped_identities_in_json():
    labels = SessionLabels(["launch-owner"])
    value = '{"session":"\\u006caunch-owner","source":"{\\"value\\":1}"}'
    projected = json.loads(labels.encode(value))
    assert projected["session"] == labels.labels["launch-owner"]
    assert projected["source"] == '{"value":1}'


def test_session_labels_match_the_guards_case_width_and_hyphen_normalization():
    guarded = Guard("analyst", Sealed.of([], tokens=["launch-owner"])).provider(Provider())
    labels = SessionLabels.protected(guarded, ["Launch-Owner"])
    for name in (
        "Launch-Owner",
        "LAUNCH-OWNER",
        "launch\u2011owner",
        "\uff4c\uff41\uff55\uff4e\uff43\uff48\uff0d\uff4f\uff57\uff4e\uff45\uff52",
    ):
        assert labels.encode(name) == opaque("Launch-Owner")
        assert json.loads(labels.encode(json.dumps({"session": name})))["session"] == opaque("Launch-Owner")
    assert labels.decode(labels.encode("Launch-Owner")) == "Launch-Owner"


@pytest.mark.asyncio
async def test_assessor_projects_hidden_sessions_and_restores_verdict_references():
    from experimental.assessor.standard import Assessor, Standard
    from experimental.iteration.compartment import Boundaries

    provider = Provider(
        response(
            "submit_verdicts",
            {
                "verdicts": [
                    {
                        "id": "tax",
                        "result": "pass",
                        "session": opaque("launch-owner"),
                        "actual": "Tax included.",
                        "note": "",
                    }
                ]
            },
        )
    )
    assessor = Assessor(
        provider,
        Standard.declared([("tax", "Include tax.")]),
        sources=("declared",),
        boundaries=Boundaries({"analyst": Sealed.of([], tokens=["launch-owner"])}),
    )
    signal = await assessor.evaluate({"launch-owner": [Exchange("Quote please.", execution("t1", "Tax included."))]})
    assert signal.items[0].session == "launch-owner" and signal.items[0].result == "pass"
    assert "launch-owner" not in json.dumps(provider.requests)
