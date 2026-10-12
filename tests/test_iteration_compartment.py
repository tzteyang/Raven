"""Every loop type declares its audiences, projection keeps only a role's fields, and a compartment's guard stops
sealed information at the provider whatever code assembled the request."""

import json
import pickle
from dataclasses import dataclass, field, fields
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

import pytest

from experimental.analyst.feedback import Feedback
from experimental.audience import ROLES, UndeclaredAudienceError, audience, audiences_of, project
from experimental.curator.harness.artifact import Change, Plan, Selection
from experimental.curator.harness.attribution import Attributed, Attribution, Diagnosis
from experimental.curator.harness.commitments import Commitment, CommitmentChange
from experimental.curator.raven_adapter.worker import Execution
from experimental.iteration.compartment import (
    Boundaries,
    BoundaryError,
    Compartment,
    Guard,
    GuardedFactory,
    GuardedProvider,
)
from experimental.iteration.conversation import Conversation
from experimental.iteration.exchange import messages
from experimental.iteration.hearing import opaque
from experimental.iteration.protocols import Exchange, Handover, Item, Signal
from experimental.iteration.session import Limits, Session
from experimental.requirements import Requirement
from experimental.scenario import load
from experimental.scenario.sealed import Sealed, sealed_for, weight, windows
from experimental.simulation.scenario import BUNDLED
from raven.contracts.llm_provider import LLMResponse
from raven.spine.message import ChatType, Source
from raven.spine.turn import Origin, TurnRequest
from tests.test_iteration_run import CURATE, FakeWorker, Scripted, Verifier, failing
from tests.test_iteration_run import analyses as analyses  # noqa: F401 -- the loop test's Analyst stand-in

TRAVEL = BUNDLED / "travel_agency"
LOOP_TYPES = (
    Exchange,
    Item,
    Signal,
    Execution,
    Requirement,
    Feedback,
    Change,
    Plan,
    Commitment,
    CommitmentChange,
    Diagnosis,
    Attribution,
    Attributed,
    Selection,
    Handover,
)


def signal():
    return Signal(
        "verifier",
        "Never asked the budget.",
        items=(Item("asks-budget", "fail", "student", expected="A budget question", note="Reply to Plan"),),
        metrics={"pass_rate": 0.0},
        satisfied=False,
        attachments=(Handover("sop", "norm", ("uploads/sop/sop.md",)),),
    )


class Provider:
    def __init__(self):
        self.calls = []
        self.generation = "settings"

    async def chat_with_retry(self, messages, tools=None, model=None, **kwargs):
        self.calls.append(("retry", messages, tools, model, kwargs))
        return LLMResponse(content="ok", tool_calls=[])

    async def chat(self, messages, tools=None, model=None, **kwargs):
        self.calls.append(("chat", messages, tools, model, kwargs))
        return LLMResponse(content="ok", tool_calls=[])

    async def chat_stream(self, messages, tools=None, model=None, **kwargs):
        self.calls.append(("stream", messages, tools, model, kwargs))
        yield "delta"

    def classify_error(self, exc):
        return "classified"

    def get_default_model(self):
        return "fake/model"

    def can_serve(self, model):
        return model == "fake/model"

    def wire_model_id(self, model):
        return f"wire:{model}"

    def emits_unparsed_reasoning(self):
        return True

    def supports_prompt_caching(self, model):
        return True

    def supports_assistant_prefill(self, model=None):
        return True

    def extra(self):
        return "delegated"


def make_provider():
    return Provider()


def user_turn(text, conversation="case-a", **kwargs):
    return TurnRequest(
        origin=Origin.USER,
        source=Source("test", conversation, "owner", ChatType.DM),
        text=text,
        conversation=conversation,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_disclosures_survive_context_truncation_and_restart_but_not_other_sessions(tmp_path):
    from experimental.iteration.disclosure import Disclosures

    text = "The family has two adults and one child with a budget of eight thousand for October."
    guard = Guard("partner", Sealed.of([text], tokens=["case-a"]))
    provider = guard.provider(make_provider())
    ledger = Disclosures(tmp_path / "disclosures.json")
    ledger.receive(user_turn(text))
    ledger = Disclosures(ledger.path)
    spoken = ledger.receive(user_turn("Please check the earlier quote."))
    with Compartment("partner", spoken=[spoken]):
        await provider.chat([{"role": "tool", "content": json.dumps({"earlier_user": text})}])
        with pytest.raises(BoundaryError, match="case-a"):
            await provider.chat([{"role": "tool", "content": "case-a"}])
    with Compartment("partner", spoken=[ledger.receive(user_turn("Check it.", "case-b"))]):
        with pytest.raises(BoundaryError):
            await provider.chat([{"role": "tool", "content": text}])


@pytest.mark.asyncio
async def test_generated_user_messages_and_delegated_results_cannot_grant_disclosure(tmp_path):
    from experimental.iteration.disclosure import Disclosures

    text = "The hidden persona demands a refund only after the second rejected booking request."
    provider = Guard("partner", Sealed.of([text])).provider(make_provider())
    ledger = Disclosures(tmp_path / "disclosures.json")
    spoken = ledger.receive(user_turn(text, delegated={"kind": "spawn", "label": "helper"}))
    assert spoken == ()
    with Compartment("partner", spoken=[spoken]):
        with pytest.raises(BoundaryError):
            await provider.chat([{"role": "user", "content": text}])
    assert not ledger.path.exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["chat", "chat_with_retry", "chat_stream"])
async def test_hidden_identifiers_in_mapping_keys_are_guarded(method):
    provider = Guard("analyst", Sealed.of([], tokens=["case-a"])).provider(make_provider())
    payload = [{"role": "tool", "content": json.dumps({"case-a": "innocuous value"})}]
    with pytest.raises(BoundaryError, match="case-a"):
        if method == "chat_stream":
            async for _ in provider.chat_stream(payload):
                pass
        else:
            await getattr(provider, method)(payload)


@pytest.mark.asyncio
async def test_native_runner_retains_ingress_before_planning_and_restores_scope(tmp_path):
    from experimental.curator.raven_adapter.runner import run_turn
    from experimental.iteration.compartment import CURRENT
    from experimental.iteration.disclosure import Disclosures

    text = "The customer needs eight seats and a complete annual price including support and storage."
    provider = Guard("partner", Sealed.of([text])).provider(make_provider())

    async def call(*args, **kwargs):
        await provider.chat([{"role": "tool", "content": text}])
        return {"ok": True}

    recorder = SimpleNamespace(turn_id=None, add=lambda *a, **k: None)
    bound = SimpleNamespace(
        recorder=recorder,
        planning=SimpleNamespace(prepare=call),
        inference=None,
        strategies={},
        runtime=SimpleNamespace(loop=SimpleNamespace(run_turn=call)),
        observer=SimpleNamespace(finish=lambda: None),
        disclosures=Disclosures(tmp_path / "disclosures.json"),
    )
    await run_turn(bound, user_turn(text), call, lambda: [])
    await run_turn(bound, user_turn("Check the saved file."), call, lambda: [])
    assert CURRENT.get() is None and recorder.turn_id is None
    with pytest.raises(BoundaryError):
        await run_turn(bound, user_turn("Another task.", "case-b"), call, lambda: [])
    assert CURRENT.get() is None


@pytest.mark.asyncio
@pytest.mark.parametrize("ingress", ["user", "delegated", "subagent", "other-session"])
async def test_native_runner_authenticates_mid_turn_disclosures_before_model_calls(tmp_path, ingress):
    from dataclasses import replace

    from experimental.curator.raven_adapter.runner import run_turn
    from experimental.iteration.disclosure import Disclosures

    text = "The customer needs eight seats and annual support included in the price."
    provider = Guard("partner", Sealed.of([text])).provider(make_provider())
    ledger = Disclosures(tmp_path / "disclosures.json")

    async def native(request, emit, drain, **options):
        (injected,) = drain()
        await provider.chat([{"role": "user", "content": injected.text}])

    async def emit(event):
        pass

    bound = SimpleNamespace(
        recorder=SimpleNamespace(turn_id=None, add=lambda *a, **k: None),
        planning=None,
        inference=None,
        strategies={},
        runtime=SimpleNamespace(loop=SimpleNamespace(run_turn=native)),
        observer=SimpleNamespace(finish=lambda: None),
        disclosures=ledger,
    )
    injected = user_turn(text)
    if ingress == "delegated":
        injected = replace(injected, delegated={"kind": "spawn", "label": "helper"})
    elif ingress == "subagent":
        injected = replace(injected, origin=Origin.SUBAGENT)
    elif ingress == "other-session":
        injected = replace(injected, conversation="case-b")
    if ingress == "user":
        await run_turn(bound, user_turn("Please quote."), emit, lambda: [injected])
        assert text in Disclosures(ledger.path).receive(user_turn("Continue."))
    else:
        with pytest.raises(ValueError if ingress == "other-session" else BoundaryError):
            await run_turn(bound, user_turn("Please quote."), emit, lambda: [injected])
        assert text not in Disclosures(ledger.path).receive(user_turn("Continue."))


@pytest.mark.asyncio
async def test_hosted_child_restores_parent_guard():
    from pydantic import TypeAdapter

    from experimental.curator.raven_adapter.hosting.acp import guarded_factory

    guard = Guard("partner", Sealed.of([], tokens=["case-a"]))
    factory = guarded_factory({"guard": TypeAdapter(Guard).dump_python(guard, mode="json")}, make_provider)
    with pytest.raises(BoundaryError, match="case-a"):
        await factory().chat([{"role": "tool", "content": "case-a"}])
    assert factory.guard == guard


def test_boundary_violations_never_retry_fallback_or_compress():
    provider = Guard("partner").provider(make_provider())
    verdict = provider.classify_error(BoundaryError("partner", "chat_stream", ["case-a"]))
    assert verdict.category == "compartment_violation"
    assert not verdict.retryable and not verdict.should_fallback and not verdict.should_compress


@pytest.mark.parametrize("cls", LOOP_TYPES)
def test_every_loop_type_declares_an_audience_for_every_field(cls):
    declared = audiences_of(cls)
    names = set(cls.model_fields) if hasattr(cls, "model_fields") else {item.name for item in fields(cls)}
    assert set(declared) == names
    assert all(roles <= set(ROLES) for roles in declared.values())


def test_projection_keeps_only_the_fields_a_role_may_receive():
    for_curator = project(signal(), "curator")
    assert for_curator == {
        "source": "verifier",
        "text": "Never asked the budget.",
        "satisfied": False,
        "attachments": [{"name": "sop", "kind": "norm", "files": ["uploads/sop/sop.md"]}],
    }
    for_analyst = project(signal(), "analyst")
    assert for_analyst["items"][0] == {
        "id": "asks-budget",
        "result": "fail",
        "session": "student",
        "expected": "A budget question",
        "actual": "",
        "note": "Reply to Plan",
        "basis": "",
        "authority": "model",
        "strength": None,
        "parent_id": None,
    }
    assert for_analyst["metrics"] == {"pass_rate": 0.0}
    assert project(signal(), "partner") == {} and project((signal(),), "curator") == [for_curator]
    plan = Plan(
        understanding="Intake is missing.",
        design="Track intake.",
        changes=(Change(target="planning.strategy", reason="r", expected="Budget asked", verification="state"),),
    )
    assert project(plan, "curator") == {
        "understanding": "Intake is missing.",
        "design": "Track intake.",
        "changes": [{"target": "planning.strategy", "reason": "r", "treatment": None}],
        "state": [],
        "node_reasons": {},
    }
    assert project(plan, "analyst") == {
        "understanding": "Intake is missing.",
        "changes": [{"target": "planning.strategy", "reason": "r", "treatment": None}],
    }
    assert project(CURATE, "curator")["requirements"][0]["behavior"] == CURATE.requirements[0].behavior
    assert project(Exchange("hi", Execution("t", [], [], {"a": 1})), "curator")["execution"]["outcome"] == {"a": 1}


def test_undeclared_types_and_bare_mappings_are_refused():
    @dataclass(frozen=True)
    class Undeclared:
        value: str

    @dataclass(frozen=True)
    class Partial:
        seen: str = field(metadata=audience("curator"))
        hidden: str = ""

    with pytest.raises(UndeclaredAudienceError, match="declares no audience"):
        project(Undeclared("x"), "curator")
    with pytest.raises(UndeclaredAudienceError, match="Partial.hidden"):
        project(Partial("a", "b"), "curator")
    with pytest.raises(UndeclaredAudienceError, match="bare mapping"):
        project({"text": "x"}, "curator")
    with pytest.raises(UndeclaredAudienceError):
        project(object(), "curator")
    with pytest.raises(ValueError, match="unknown role"):
        project(signal(), "owner")
    with pytest.raises(ValueError, match="unknown roles"):
        audience("owner")

    @dataclass(frozen=True)
    class Declared:
        AUDIENCES: ClassVar[dict[str, frozenset[str]]] = {"value": frozenset({"curator"})}
        value: str

    @dataclass(frozen=True)
    class Short:
        AUDIENCES: ClassVar[dict[str, frozenset[str]]] = {"value": frozenset({"curator"})}
        value: str
        extra: str = ""

    assert project(Declared("x"), "curator") == {"value": "x"}
    assert project(Declared("x"), "analyst") == {}
    with pytest.raises(UndeclaredAudienceError, match=r"Short declares no audience for \['extra'\]"):
        project(Short("x"), "curator")


def test_sealing_is_differential_between_what_a_role_may_and_may_not_see():
    norm = "Ask for the budget before recommending any product, and restate the counterpart in one sentence."
    check = f"S2.1: {norm} The assistant fails this check when the budget question comes after a product name."
    sealed = Sealed.of([check], visible=[norm], tokens=["quote-sheet-correct", "family", "abc"])
    assert sealed.tokens == frozenset({"quote-sheet-correct"})
    assert sealed.hits("Please ask for the budget before recommending any product, and restate the counterpart.") == []
    assert sealed.hits("It fails this check when the budget question comes after a product name.") == ["<sealed text>"]
    assert sealed.hits("Fails this check when the budget question comes.") == []
    assert sealed.hits("The verdict on quote-sheet-correct was fail.") == ["quote-sheet-correct"]
    assert sealed.hits("quote-sheet-correctness is a word") == []
    assert sealed.hits("The family asked nothing.") == []
    assert not windows("Short id.") and not Sealed()
    assert Sealed.of([], tokens=["case-1"]).tokens == frozenset({"case-1"})
    assert not Sealed.of(["short phrase"], visible=["a short phrase here"])
    assert Sealed.of(["short phrase"]).hits("A SHORT-phrase, hidden") == ["<sealed text>"]
    assert Sealed.of(["short phrase"]).hits("shortphrase or short phrases") == []


def test_a_spoken_line_quoted_with_the_words_that_introduce_it_in_the_card_is_not_a_leak():
    line = "From now on keep an eye on the six rivals in the store and file the watch report when done."
    card = f"You run the marketing team. Open with: {line} Only when asked: the six rivals are the ones in the brief."
    sealed = Sealed.of([card]).without([(line,)])
    assert sealed.hits(f"The customer opened with: {line}") == []
    assert sealed.hits("Only when asked: the six rivals are the ones in the brief.") == ["<sealed text>"]
    assert Sealed.of([card]).hits(f"Open with: {line}") == ["<sealed text>"]


def test_a_text_sealed_against_copying_is_found_only_as_a_copied_run():
    held = "The handover form is filed for holds, planning calls, complaints, groups and checks."
    later = (
        "The handover form template: holds, planning calls, complaints, groups and checks each have their fields, "
        "folder and naming rule. A hold is filed before any seat is promised to the guest and names the quote, the "
        "dates and the party it rests on."
    )
    sealed = Sealed.of([], tokens=["case-7"]).copying([later, "Never promise a seat."], visible=[held])
    assert sealed.passages and sealed.span == 10
    assert sealed.hits("The handover form template: holds, planning calls and complaints are filed with it.") == []
    copied = "A hold is filed before any seat is promised to the guest and names the quote, the dates and the party."
    assert sealed.hits(f"Note: {copied}") == ["<sealed text>"]
    assert sealed.hits("We never promise a seat.") == ["<sealed text>"]
    assert sealed.hits("case-7 is open") == ["case-7"]
    assert not sealed.without([copied, "Never promise a seat."]).hits(f"Note: {copied} We never promise a seat.")


def test_a_sealed_text_written_over_several_lines_is_found_inside_a_packet_sent_as_json():
    lines = "\u62a5\u4ef7\u5355\u5fc5\u987b\u5217\u51fa\u6bcf\u4f4d\u5ba2\u4eba\u7684\n\u673a\u7968\u3001\u9152\u5e97\u3001\u95e8\u7968\u4e0e\u4fdd\u9669\u7684\n\u5355\u4ef7\u548c\u603b\u4ef7\uff0c\u4e0d\u5f97\u6253\u5305\u62a5\u4ef7\u3002"
    guard = Guard("conversant", Sealed.of([lines.replace("\n", "")], tokens=["quote-total"]))
    packet = messages("You play a customer.", {"persona": lines, "notes": "see\nquote-total"})
    assert set(guard.scan(packet)) == {"quote-total", "<sealed text>"}
    assert guard.scan([{"role": "user", "content": "{not json at all"}]) == []


def test_a_window_weighs_as_much_in_chinese_as_in_english():
    check = "Every day follows the itinerary template with morning, afternoon and evening blocks and a backup."
    assert Sealed.of([check]).hits("The plan should use the itinerary template for every day.") == []
    assert Sealed.of([check]).hits("follows the itinerary template with morning, afternoon and evening blocks") != []
    persona = "\u4f60\u5988\u5988\u6bcf\u5929\u8d70\u8def\u6700\u597d\u4e0d\u8d85\u8fc7\u56db\u516c\u91cc"
    persona += "\uff0c\u513f\u5b50\u4e2d\u5348\u8981\u7761\u5348\u89c9\u3002"
    sealed = Sealed.of([persona])
    assert sealed.hits("\u5988\u5988\u6bcf\u5929\u8d70\u8def") == []
    assert sealed.hits("\u5ba2\u4eba" + persona[1:]) == ["<sealed text>"]
    assert weight(persona) == len(persona) - 2 and weight("ten words") == 4
    assert windows("\uff15\uff0e\uff15\u4e07 " * 8) == windows("5.5\u4e07 " * 8)


def test_the_travel_agency_seals_its_checks_and_cases_from_the_curator_but_not_what_the_counterpart_says():
    scenario = load(TRAVEL)
    curator = sealed_for(scenario, "curator")
    assert "quote-sheet-correct" in curator.tokens and "travel_agency" in curator.tokens and curator.windows
    check = next(check for check in scenario.statements.checks if check.id == "deck-structure")
    assert curator.hits(check.check) == ["<sealed text>"]
    assert curator.hits(scenario.materials["service-sop"].path.joinpath("SKILL.md").read_text()) == []
    assert curator.hits(scenario.situation.profile) == []
    assert curator.hits(scenario.situation.cases[0].text) == ["<sealed text>"]
    opening = scenario.exchange.onboarding.replace("{files}", "- uploads/service-sop/SKILL.md")
    handover = scenario.exchange.handover.replace("{files}", "- uploads/price-list/SKILL.md")
    for role in ("curator", "analyst", "partner"):
        assert sealed_for(scenario, role).hits(opening) == [] and sealed_for(scenario, role).hits(handover) == []
    counterpart = sealed_for(scenario, "counterpart")
    assert counterpart.hits(check.check) == [] and counterpart.hits(scenario.situation.cases[0].text) == []
    assert counterpart.tokens == frozenset({"travel_agency"})
    with pytest.raises(ValueError, match="unknown role"):
        sealed_for(scenario, "owner")


@pytest.mark.asyncio
async def test_the_guarded_provider_stops_sealed_requests_before_they_leave(tmp_path):
    sealed = Sealed.of(
        ["The hidden persona only reveals the budget when asked twice and never before."], tokens=["case-7"]
    )
    log = tmp_path / "boundaries.jsonl"
    inner = make_provider()
    guarded = Guard("curator", sealed, "abort", log).provider(inner)
    assert isinstance(guarded, GuardedProvider)
    clean = [{"role": "user", "content": "Improve the intake."}]
    assert (await guarded.chat_with_retry(clean, tools=[{"name": "t"}], model="m", tool_choice="auto")).content == "ok"
    assert inner.calls[-1] == ("retry", clean, [{"name": "t"}], "m", {"tool_choice": "auto"})
    with pytest.raises(BoundaryError, match="case-7"):
        await guarded.chat_with_retry([{"role": "user", "content": [{"type": "text", "text": "verdict on case-7"}]}])
    with pytest.raises(BoundaryError, match="sealed text"):
        await guarded.chat([{"role": "tool", "content": "persona only reveals the budget when asked twice and never"}])
    with pytest.raises(BoundaryError):
        async for _ in guarded.chat_stream([{"role": "user", "content": "case-7"}]):
            pass
    assert len(inner.calls) == 1
    rows = [json.loads(line) for line in log.read_text().splitlines()]
    assert [row["where"] for row in rows] == ["chat_with_retry", "chat", "chat_stream"]
    assert rows[0]["hits"] == ["case-7"] and rows[0]["role"] == "curator"
    assert guarded.get_default_model() == "fake/model" and guarded.can_serve("fake/model")
    assert guarded.wire_model_id("x") == "wire:x" and guarded.classify_error(None) == "classified"
    assert guarded.emits_unparsed_reasoning() and guarded.supports_prompt_caching("m")
    assert guarded.supports_assistant_prefill() and guarded.extra() == "delegated"
    assert guarded.generation == "settings"
    guarded.generation = "other"
    assert inner.generation == "other"
    persona = "The hidden persona only reveals the budget when asked twice and never before."
    with Compartment("curator"):
        with pytest.raises(BoundaryError, match="case-7"):
            await guarded.chat_with_retry([{"role": "user", "content": "case-7"}])
    with Compartment("curator", spoken=[(persona,)]):
        assert (await guarded.chat_with_retry([{"role": "user", "content": persona}])).content == "ok"
        with pytest.raises(BoundaryError, match="case-7"):
            await guarded.chat_with_retry([{"role": "user", "content": f"{persona} case-7"}])
    warning = Guard("counterpart", sealed, "warn", log).provider(make_provider())
    assert (await warning.chat_with_retry([{"role": "user", "content": "case-7"}])).content == "ok"
    assert json.loads(log.read_text().splitlines()[-1])["event"] == "violation"
    with pytest.raises(ValueError, match="unknown policy"):
        Guard("curator", sealed, "drop")
    with pytest.raises(ValueError, match="unknown role"):
        Guard("owner", sealed)


def test_a_guarded_factory_survives_the_trip_to_a_spawned_process(tmp_path):
    factory = GuardedFactory(
        make_provider, Guard("partner", Sealed.of(["hidden text of a case"]), "abort", tmp_path / "b")
    )
    restored = pickle.loads(pickle.dumps(factory))
    provider = restored()
    assert isinstance(provider, GuardedProvider) and provider.guard == factory.guard
    assert provider.guard.scan({"messages": [{"content": "the hidden text of a case"}]}) == ["<sealed text>"]


def test_a_compartment_admits_projected_values_and_logs_its_boundary(tmp_path):
    log = tmp_path / "boundaries.jsonl"
    sealed = Sealed.of(["A budget question"], tokens=["asks-budget"])
    with Compartment("curator", sealed, log=log) as scope:
        heard = scope.project(signal(), "signal")
        assert heard == {
            "source": "verifier",
            "text": "Never asked the budget.",
            "satisfied": False,
            "attachments": [{"name": "sop", "kind": "norm", "files": ["uploads/sop/sop.md"]}],
        }
        with pytest.raises(BoundaryError, match="admit:signal"):
            scope.admit({"verdict": "asks-budget: fail"}, "signal")
        assert scope.admit({"text": "fine"}) == {"text": "fine"}
    events = [(row["event"], row["where"]) for row in map(json.loads, log.read_text().splitlines())]
    assert events == [
        ("enter", "curator"),
        ("admit", "signal"),
        ("violation", "admit:signal"),
        ("admit", "value"),
        ("leave", "curator"),
    ]
    boundaries = Boundaries({"curator": sealed}, policy="warn", log=log)
    assert boundaries.compartment("curator").guard.policy == "warn"
    assert not boundaries.compartment("analyst").guard.sealed


@pytest.mark.asyncio
async def test_the_partners_guard_lets_the_conversants_words_through_but_not_a_leak_in_its_prompt(tmp_path):
    card = "A family of two adults and one child with a budget of 8000 for the first week of October."
    sealed = Sealed.of([card, "Check C1: the deck lists every price."], tokens=["case-7"])
    inner = make_provider()
    partner = Guard("partner", sealed, "abort", tmp_path / "boundaries.jsonl").provider(inner)
    spoken = "We are a family of two adults and one child with a budget of 8000."
    with Compartment("partner", spoken=[spoken]):
        await partner.chat(
            [
                {"role": "system", "content": "You are a travel consultant."},
                {"role": "user", "content": [{"type": "text", "text": spoken}]},
                {"role": "assistant", "content": "Two adults and one child with a budget of 8000, noted."},
            ]
        )
    with pytest.raises(BoundaryError, match="sealed text"):
        await partner.chat([{"role": "system", "content": f"The customer: {card}"}, {"role": "user", "content": "Hi"}])
    with pytest.raises(BoundaryError, match="case-7"):
        await partner.chat([{"role": "user", "content": "I am case-7."}])
    curator = Guard("curator", sealed).provider(inner)
    with pytest.raises(BoundaryError, match="sealed text"):
        await curator.chat([{"role": "user", "content": spoken}])
    heard = Boundaries({"curator": sealed}).compartment("curator", spoken=[spoken]).guard.sealed
    assert heard.hits(spoken) == [] and heard.hits(card) == ["<sealed text>"] and "case-7" in heard.tokens


@pytest.mark.asyncio
async def test_a_session_runs_each_model_role_inside_its_compartment(tmp_path, analyses):
    analyses.scripted.extend([CURATE])
    seen = []

    async def curator(worker, provider, *, feedback=None, model=None, limits=None, probe=None, observations=None):
        seen.append((type(provider).__name__, feedback, observations))
        if feedback is not None:
            await provider.chat_with_retry([{"role": "user", "content": json.dumps(feedback)}])

    sealed = {
        "curator": Sealed.of(["A budget question comes before any product name."], tokens=["asks-budget", "student-1"])
    }
    session = Session.open(
        FakeWorker(tmp_path),
        make_provider(),
        curator=curator,
        limits=Limits(max_rounds=3),
        boundaries=Boundaries(sealed),
    )
    assert isinstance(session.analyst.provider, GuardedProvider) and session.analyst.provider.guard.role == "analyst"
    assert session.boundaries.log == tmp_path / "boundaries.jsonl"
    await session.onboard()
    assert seen[0] == ("GuardedProvider", None, None)
    await session.trial(Conversation(Scripted("student-1", "Plan a trip"), max_turns=1))
    await session.assess(Verifier(failing("student-1 never asked the budget.")))
    await session.analyse()
    assert await session.curate()
    assert seen[1][1]["signals"][0]["text"] == f"{opaque('student-1')} never asked the budget."
    assert "items" not in seen[1][1]["signals"][0]
    assert [(row["session"], row["turn_id"]) for row in seen[1][2]] == [(opaque("student-1"), "turn-1")]
    events = [row["event"] for row in map(json.loads, (tmp_path / "boundaries.jsonl").read_text().splitlines())]
    assert events.count("enter") == 3 and "violation" not in events
    leaking = Session.open(
        FakeWorker(tmp_path / "leak"),
        make_provider(),
        curator=curator,
        limits=Limits(max_rounds=3),
        boundaries=Boundaries(sealed),
    )
    await leaking.onboard()
    await leaking.trial(Conversation(Scripted("student-1", "Plan a trip"), max_turns=1))
    leaking.signal(
        Signal(
            "human",
            "The verdict on asks-budget was fail.",
            satisfied=False,
            attachments=(Handover("x", "fact", ("uploads/x/x.md",)),),
        )
    )
    analyses.scripted.extend([CURATE])
    await leaking.analyse()
    with pytest.raises(BoundaryError, match="asks-budget"):
        await leaking.curate()
    assert leaking.status == "error" and "asks-budget" in leaking.record["error"]
    rows = [json.loads(line) for line in (tmp_path / "leak" / "boundaries.jsonl").read_text().splitlines()]
    assert rows[-2]["event"] == "violation" and rows[-2]["where"] == "admit:feedback"
    assert Path(leaking.path).is_file() and json.loads(leaking.path.read_text())["status"] == "error"


@pytest.mark.asyncio
@pytest.mark.parametrize("channel", ["feedback", "observations", "attribution"])
async def test_curator_ingress_projects_trial_labels_without_admitting_hidden_content(tmp_path, channel):
    hidden = "Only when asked about procurement reveal the private budget ceiling of 87000 dollars."
    seen = []

    async def curator(worker, provider, **kwargs):
        seen.append(kwargs)
        payload = kwargs[channel]
        if isinstance(payload, Attribution):
            payload = payload.model_dump(mode="json")
        await provider.chat_with_retry([{"role": "user", "content": json.dumps(payload)}])

    session = Session.open(
        FakeWorker(tmp_path),
        make_provider(),
        curator=curator,
        boundaries=Boundaries({"curator": Sealed.of([hidden], tokens=["launch-owner", "private-check"])}),
    )
    session.sessions = {"launch-owner": ()}

    def payload(text):
        if channel == "attribution":
            return Attribution(diagnoses=(Diagnosis(about="task", state="uncovered", mechanism=text),))
        return {"launch-owner": {"quote": text, "encoded": json.dumps({"launch-owner": text})}}

    original = payload("Feedback for launch-owner")
    before = repr(original)
    assert await session._curate(**{"feedback": None, channel: original}) == "done"
    assert repr(original) == before
    rendered = repr(seen[-1][channel])
    assert "launch-owner" not in rendered and opaque("launch-owner") in rendered
    for secret in (hidden, "private-check"):
        with pytest.raises(BoundaryError):
            await session._curate(**{"feedback": None, channel: payload(secret)})
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_previous_curation_gaps_keep_the_same_identity_and_secrecy_boundary(tmp_path):
    seen = []

    async def curator(worker, provider, *, feedback=None, **kwargs):
        seen.append(feedback)
        await provider.chat_with_retry([{"role": "user", "content": json.dumps(feedback)}])

    session = Session.open(
        FakeWorker(tmp_path),
        make_provider(),
        curator=curator,
        boundaries=Boundaries({"curator": Sealed.of([], tokens=["launch-owner", "private-check"])}),
    )
    session.sessions = {"launch-owner": ()}
    question = {"round": 1, "stage": "design", "question": "The launch-owner trial needs a granted file reader."}
    session.record["questions"] = [question]
    assert await session._curate({}) == "done"
    assert seen[0]["previous_gaps"][0]["question"] == f"The {opaque('launch-owner')} trial needs a granted file reader."
    assert session.record["questions"] == [question]
    session.record["questions"] = [{**question, "question": "Inspect private-check."}]
    with pytest.raises(BoundaryError, match="private-check"):
        await session._curate({})
    assert len(seen) == 1


@pytest.mark.asyncio
async def test_the_analyst_and_the_curator_spare_whatever_the_conversants_said(tmp_path, monkeypatch):
    from experimental.analyst import role

    card = "We are a family of two adults and one child with a budget of 8000 for the first week of October."
    hidden = "Only if asked: they want a quiet hotel near the station with a pool for the child."
    sealed = Sealed.of([card, hidden], tokens=["case-7"])
    restated = "Noted: a family of two adults and one child with a budget of 8000 for the first week of October."

    async def analyse(worker, provider, signals, sessions, **_):
        said = [exchange.user for exchanges in sessions.values() for exchange in exchanges]
        await provider.chat_with_retry([{"role": "user", "content": json.dumps([*said, restated])}])
        return CURATE

    async def curator(worker, provider, *, feedback=None, **_):
        if feedback is not None:
            await provider.chat_with_retry([{"role": "user", "content": json.dumps(feedback)}])

    monkeypatch.setattr(role, "analyse", analyse)

    async def round_with(root, remark):
        session = Session.open(
            FakeWorker(root),
            make_provider(),
            curator=curator,
            limits=Limits(max_rounds=3),
            boundaries=Boundaries({"analyst": sealed, "curator": sealed}),
        )
        await session.onboard()
        one_fact_per_message = ("We are a family of two adults", card.removeprefix("We are a family of two adults "))
        await session.trial(Conversation(Scripted("student", *one_fact_per_message), max_turns=2))
        session.signal(Signal("human", remark, satisfied=False))
        await session.analyse()
        return session

    quoted = await round_with(tmp_path / "quoted", f"The customer said: {restated.removeprefix('Noted: ')}")
    assert await quoted.curate()
    events = [json.loads(line)["event"] for line in (tmp_path / "quoted" / "boundaries.jsonl").read_text().splitlines()]
    assert "violation" not in events and events.count("enter") == 3
    leaking = await round_with(tmp_path / "leaking", f"The card also says: {hidden}")
    with pytest.raises(BoundaryError, match="sealed text"):
        await leaking.curate()
