"""A research result is a scenario directory the loader reads like any other, with each material's origin on record,
the materials held back still held by the party, and the evaluation side drawing only on what the party stands
behind."""

import argparse
import json

import pytest

import experimental.research.__main__ as entry
from experimental.research import Decision, Finding, Rule
from experimental.research.confirm import NAME as DECIDE
from experimental.research.induction import NAME as INDUCE
from experimental.research.package import CANDIDATES, CONFIRMED, RESEARCHED, add, copy, digest
from experimental.scenario import default_visibility, load
from experimental.simulation.agency import Agency as Owner
from experimental.simulation.scenario import BUNDLED
from experimental.simulation.scenario import Scenario as Agency
from tests.test_research_induction import Provider, make_scenario, response

RULES = [
    Rule("induced-1", "Name the price of each item.", ("good-reply",), "Tea for two: six."),
    Rule("induced-2", "Greet first.", ("good-reply",), "Hello"),
    Rule("induced-3", "Never offer a discount.", ("bad-reply",), "half off"),
    Rule("induced-4", "Say six.", ("good-reply",), "six"),
]
DECISIONS = [
    Decision(id="induced-1", status="amended", text="Name each item's price and the total."),
    Decision(id="induced-2", status="confirmed"),
    Decision(id="induced-3", status="undecided"),
    Decision(id="induced-4", status="rejected", reason="That order's price."),
]
PAGE = "https://tea.example/guide"
FINDINGS = [
    Finding("researched-1", "Afternoon tea is served from two to five.", "fact", "When?", (PAGE,), "served from two"),
    Finding(
        "researched-2",
        "Tell customers about allergens when they ask.",
        "norm",
        "What do tea rooms tell customers?",
        (PAGE,),
        "tell customers about allergens",
    ),
    Finding(
        "researched-3", "Tea costs four.", "fact", "What does tea cost?", (PAGE,), "tea costs four", "", ("prices",)
    ),
]
SETTLED_FINDINGS = [
    Decision(id="researched-1", status="undecided"),
    Decision(id="researched-2", status="confirmed"),
    Decision(id="researched-3", status="rejected", reason="Our tea costs three."),
]


def researched(tmp_path, without=("sop",)):
    source = load(make_scenario(tmp_path / "shop"))
    copy(source, tmp_path / "out", without)
    handed = load(tmp_path / "out")
    settled = [*zip(RULES, DECISIONS, strict=True), *zip(FINDINGS, SETTLED_FINDINGS, strict=True)]
    add(
        tmp_path / "out", source, handed, settled, without=without, unanswered=[{"question": "Our prices?", "why": "x"}]
    )
    return source, load(tmp_path / "out")


def test_the_researched_scenario_holds_the_settled_items_and_says_where_each_material_came_from(tmp_path):
    source, out = researched(tmp_path)
    assert out.materials["sop"].visibility == frozenset({"party"}) and "sop" not in out.handed
    assert out.statements.checks[0].derived_from == ("sop", "owner-policy")
    written = {
        name: out.materials[name].kind
        for name in (CONFIRMED, CANDIDATES, *RESEARCHED.values())
        if name in out.materials
    }
    assert written == {
        CONFIRMED: "norm",
        CANDIDATES: "norm",
        RESEARCHED[("norm", True)]: "norm",
        RESEARCHED[("fact", False)]: "fact",
    }
    assert all(out.materials[name].visibility == default_visibility(kind) for name, kind in written.items())
    assert [out.confirmed(name) for name in written] == [True, False, True, False]
    assert out.confirmed("prices")
    confirmed = (out.materials[CONFIRMED].path / "SKILL.md").read_text()
    candidates = (out.materials[CANDIDATES].path / "SKILL.md").read_text()
    assert "Name each item's price and the total." in confirmed and "Greet first." in confirmed
    assert "Name the price of each item." not in confirmed and "Never offer a discount." in candidates
    assert "not confirmed" in candidates and "Say six." not in confirmed + candidates
    facts = (out.materials[RESEARCHED[("fact", False)]].path / "SKILL.md").read_text()
    assert "Afternoon tea is served from two to five." in facts and f"Sources: {PAGE}" in facts
    assert "> served from two" in facts and "Read on " in facts and "check prices" in facts
    assert "Tea costs four." not in facts
    spec = json.loads((tmp_path / "out" / "scenario.json").read_text())
    assert {CONFIRMED, CANDIDATES, RESEARCHED[("norm", True)]} <= set(spec["initial"]) and "sop" not in spec["initial"]
    assert spec["plans"]["two"] == [
        ["prices", RESEARCHED[("fact", False)], RESEARCHED[("norm", True)]],
        ["good-reply", "bad-reply", CONFIRMED, CANDIDATES],
    ]
    provenance = out.provenance.record
    assert provenance["input"] == {"scenario": "shop", "digest": digest(source.root), "without": ["sop"]}
    assert provenance["materials"][CONFIRMED] == {
        "origin": "induced",
        "confirmed": True,
        "items": ["induced-1", "induced-2"],
    }
    assert provenance["materials"][RESEARCHED[("fact", False)]] == {
        "origin": "researched",
        "confirmed": False,
        "items": ["researched-1"],
    }
    kept = {row["id"]: row for row in (*provenance["rules"], *provenance["findings"])}
    assert kept["induced-4"]["decision"]["status"] == "rejected" and kept["researched-3"]["conflicts"] == ["prices"]
    assert provenance["unanswered"] == [{"question": "Our prices?", "why": "x"}]


def test_the_evaluation_side_holds_the_partner_only_to_norms_the_owner_stands_behind(tmp_path):
    _, out = researched(tmp_path)
    agency = Agency.of(out)
    assert sorted(agency.standing_norms(agency.handed)) == [CONFIRMED, RESEARCHED[("norm", True)]]
    assert agency.stands_behind("prices") and not agency.stands_behind(CANDIDATES)
    assert "sop" in agency.materials and "sop" not in agency.handed and "sop" not in agency.disclosure().materials


def test_a_researched_scenario_is_not_researched_again_and_its_provenance_states_every_standing(tmp_path):
    _, out = researched(tmp_path)
    with pytest.raises(ValueError, match="written by a research stage"):
        copy(out, tmp_path / "again")
    provenance = json.loads((out.root / "provenance.json").read_text())
    provenance["materials"]["unknown"] = {"origin": "given"}
    (out.root / "provenance.json").write_text(json.dumps(provenance))
    with pytest.raises(ValueError, match="materials the scenario does not have"):
        load(out.root)
    for origin, match in (
        ({"origin": "given", "confirmed": False}, "stands behind"),
        ({"origin": "researched"}, "say"),
    ):
        provenance["materials"] = {"prices": origin}
        (out.root / "provenance.json").write_text(json.dumps(provenance))
        with pytest.raises(ValueError, match=match):
            load(out.root)


def test_the_party_still_holds_what_it_held_back_so_a_researched_travel_agency_can_be_simulated(tmp_path):
    source = load(BUNDLED / "travel_agency")
    held = ["plan-deck-spec", "service-sop"]
    copy(source, tmp_path / "out", held)
    agency = Agency.of(load(tmp_path / "out"))
    assert set(held) <= set(agency.materials) and not set(held) & set(agency.handed)
    owner = Owner(agency, Provider(), tmp_path / "skills", workdir=tmp_path, deliver="pool")
    assert owner.rules is not None and not set(held) & set(owner.withheld)
    assert not set(held) & {name for step in agency.plans["by-stage"] for name in step}


def test_holding_back_the_whole_onboarding_or_what_the_party_does_not_hold_is_refused_before_anything_runs(tmp_path):
    source = load(BUNDLED / "travel_agency")
    first = list(source.exchange.plans["by-stage"][0])
    with pytest.raises(ValueError, match="nothing to hand over at onboarding"):
        copy(source, tmp_path / "out", first)
    shop = load(make_scenario(tmp_path / "shop"))
    unheld = shop.model_copy(
        update={
            "materials": {
                **shop.materials,
                "sop": shop.materials["sop"].model_copy(update={"visibility": frozenset({"partner"})}),
            }
        }
    )
    with pytest.raises(ValueError, match="does not hold"):
        copy(unheld, tmp_path / "other", ["sop"])
    assert not (tmp_path / "out").exists() and not (tmp_path / "other").exists()


def arguments(tmp_path, source, **given):
    values = dict(
        scenario=source,
        out=tmp_path / "out",
        records=tmp_path / "records",
        config=None,
        model=None,
        effort="low",
        without=["sop"],
        decisions=None,
        party_knows=["sop"],
        from_records=None,
        research=None,
        research_model=None,
        research_budget=None,
        research_timeout=60,
        research_calls=4,
        findings=8,
        party_model=None,
        party_effort=None,
        limit=12,
        max_calls=4,
        timeout=60,
    )
    return argparse.Namespace(**{**values, **given})


@pytest.mark.asyncio
async def test_the_stage_writes_the_package_and_keeps_its_whole_process(tmp_path, monkeypatch):
    source = make_scenario(tmp_path / "shop")
    rule = {"text": "Name each item's price.", "sources": ["good-reply"], "evidence": "Tea for two: six."}
    provider = Provider(
        response(INDUCE, {"rules": [rule]}),
        response(DECIDE, {"decisions": [{"id": "induced-1", "status": "confirmed", "reason": "The SOP says so."}]}),
    )
    monkeypatch.setattr(entry, "_provider", lambda args, records: provider)
    args = arguments(tmp_path, source)
    summary = await entry.research(args)
    assert summary == {
        "out": str((tmp_path / "out").resolve()),
        "gaps": {"norms": "inducible"},
        "rules": 1,
        "findings": 0,
        "refused": 0,
        "unanswered": 0,
        "decisions": {"confirmed": 1},
    }
    out = load(tmp_path / "out")
    assert out.confirmed(CONFIRMED) and CANDIDATES not in out.materials and not (tmp_path / "out.partial").exists()
    assert out.provenance.record["calls"]["confirmation"]["knows"] == ["sop"]
    told = json.loads(provider.requests[1]["messages"][1]["content"])
    assert [row["name"] for row in told["your_materials"]] == ["sop"]
    kept = {path.name for path in (tmp_path / "records").iterdir()}
    assert kept == {
        "settings.json",
        "slots.json",
        "rules.json",
        "findings.json",
        "unanswered.json",
        "refused.json",
        "decisions.json",
        "trace.json",
        "summary.json",
    }
    settings = json.loads((tmp_path / "records" / "settings.json").read_text())
    assert "config" not in settings and settings["digest"] == digest(load(source).root)
    with pytest.raises(ValueError, match="new or empty"):
        await entry.research(args)


@pytest.mark.asyncio
async def test_a_decisions_file_settles_the_items_an_earlier_run_recorded_and_no_other(tmp_path, monkeypatch):
    source = make_scenario(tmp_path / "shop")
    provider = Provider(
        response(INDUCE, {"rules": [{"text": "Greet first.", "sources": ["good-reply"], "evidence": "Hello"}]})
    )
    monkeypatch.setattr(entry, "_provider", lambda args, records: provider)
    await entry.research(arguments(tmp_path, source, party_knows=[]))
    decisions = tmp_path / "decisions.json"
    decisions.write_text(json.dumps({"decisions": [{"id": "induced-1", "status": "confirmed"}]}))
    with pytest.raises(ValueError, match="give --from-records"):
        await entry.research(
            arguments(tmp_path, source, out=tmp_path / "x", records=tmp_path / "y", decisions=decisions)
        )
    again = arguments(
        tmp_path,
        source,
        out=tmp_path / "settled",
        records=tmp_path / "settled-records",
        decisions=decisions,
        party_knows=[],
        from_records=tmp_path / "records",
    )
    summary = await entry.research(again)
    assert summary["decisions"] == {"confirmed": 1} and len(provider.requests) == 1
    assert "Greet first." in (load(tmp_path / "settled").materials[CONFIRMED].path / "SKILL.md").read_text()
    other = arguments(
        tmp_path,
        source,
        out=tmp_path / "other",
        records=tmp_path / "other-records",
        decisions=decisions,
        party_knows=[],
        from_records=tmp_path / "records",
        without=[],
    )
    with pytest.raises(ValueError, match="other held-back materials"):
        await entry.research(other)
    broken = tmp_path / "broken.json"
    broken.write_text("{")
    with pytest.raises(ValueError):
        await entry.research(arguments(tmp_path, source, out=tmp_path / "b", records=tmp_path / "c", decisions=broken))
    assert len(provider.requests) == 1 and not (tmp_path / "b").exists()


@pytest.mark.asyncio
async def test_the_stage_refuses_to_write_inside_the_scenario_or_over_a_partial_build(tmp_path):
    source = make_scenario(tmp_path / "shop")
    with pytest.raises(ValueError, match="outside the scenario"):
        await entry.research(arguments(tmp_path, source, out=source / "out"))
    (tmp_path / "out.partial").mkdir()
    with pytest.raises(ValueError, match="partial build"):
        await entry.research(arguments(tmp_path, source))


@pytest.mark.asyncio
async def test_a_held_back_material_is_sealed_so_the_party_cannot_hand_it_over_in_an_amendment(tmp_path, monkeypatch):
    source = make_scenario(tmp_path / "shop")
    rule = {"text": "Name each item's price.", "sources": ["good-reply"], "evidence": "Tea for two: six."}
    verbatim = "Greet the customer and quote from the price list only."
    provider = Provider(
        response(INDUCE, {"rules": [rule]}),
        response(DECIDE, {"decisions": [{"id": "induced-1", "status": "amended", "text": verbatim, "reason": "SOP"}]}),
        response(
            DECIDE,
            {"decisions": [{"id": "induced-1", "status": "amended", "text": "Quote prices.", "reason": "Mine."}]},
        ),
    )
    monkeypatch.setattr(entry, "_provider", lambda args, records: provider)
    await entry.research(arguments(tmp_path, source))
    refused = [
        json.loads(row["content"]).get("error", "") for row in provider.requests[2]["messages"] if row["role"] == "tool"
    ]
    assert any(refused), "the verbatim amendment of the held-back SOP is refused"
    written = (tmp_path / "out" / "materials" / "induced-norms" / "SKILL.md").read_text()
    assert "Quote prices." in written and verbatim not in written
