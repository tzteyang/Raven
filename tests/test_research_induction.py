"""The research stage induces rules only from what every reader of a norm may receive, and the party settles each."""

import json
from pathlib import Path

import pytest

from experimental.research import Decisions, ModelParty, induce, settle, worded
from experimental.research.confirm import NAME as DECIDE
from experimental.research.induction import AUDIENCE, NAME
from experimental.scenario import load
from experimental.scenario.sealed import sealed_for
from raven.contracts.llm_provider import LLMResponse, ToolCallRequest

CHECK = "Every quote the assistant sends states the total price of the whole order as one figure."


class Provider:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    async def chat_with_retry(self, **kwargs):
        self.requests.append(kwargs)
        answer = self.responses.pop(0)
        return answer(kwargs) if callable(answer) else answer


def response(name, arguments):
    return LLMResponse(content=None, tool_calls=[ToolCallRequest(name, name, arguments)])


def rejections(request) -> list[str]:
    return [json.loads(row["content"])["error"] for row in request["messages"] if row["role"] == "tool"]


def make_scenario(root: Path, *, facts=True, instances=True, checks=True, norms=True) -> Path:
    """A shop scenario: a norm, a norm only the party holds, a fact, an exemplar with a binary file beside its
    document, a counterexample, one check and a two-step plan of what the party hands over."""
    (root / "personas").mkdir(parents=True)
    (root / "profile.md").write_text("You answer the tea shop's customers.\n")
    (root / "personas" / "walk-in.md").write_text("A customer asks what an afternoon tea for two would cost.\n")

    def material(name, text, kind, **extra):
        folder = root / "materials" / name
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text(f"---\nname: {name}\ndescription: The shop's {name}.\n---\n\n{text}\n")
        for file, content in extra.items():
            (folder / file.replace("_", ".")).write_bytes(content)
        return kind

    kinds = {}
    if norms:
        kinds["sop"] = {"kind": material("sop", "Greet the customer and quote from the price list only.", "norm")}
        kinds["owner-policy"] = {
            "kind": material("owner-policy", "Discounts above ten percent need the owner's approval.", "norm"),
            "visibility": ["party"],
        }
    if facts:
        kinds["prices"] = {"kind": material("prices", "Tea costs three. Cake costs five.", "fact")}
    if instances:
        kinds["good-reply"] = {
            "kind": material(
                "good-reply",
                "Hello, I am the shop's assistant. Tea for two: six. Cake for two: ten. Together: sixteen.",
                "exemplar",
                reply_pdf=b"%PDF-1.4",
            )
        }
        kinds["bad-reply"] = {
            "kind": material("bad-reply", "Sure, I can give you half off everything!", "counterexample")
        }
    handed = [name for name in kinds if name != "owner-policy"]
    contract, spec = {"materials": kinds}, {"initial": sorted(handed)}
    first = [name for name in ("sop", "prices") if name in kinds]
    spec["plans"] = {"two": [first, [name for name in handed if name not in first]]} if instances and first else {}
    if checks:
        spec["criteria"] = [{"id": "quote-total", "check": CHECK}]
        contract["checks"] = {"quote-total": {"derived_from": ["sop", "owner-policy"] if norms else []}}
    (root / "contract.json").write_text(json.dumps(contract))
    (root / "scenario.json").write_text(json.dumps(spec))
    return root


def seals(scenario):
    return {role: sealed_for(scenario, role) for role in AUDIENCE}


RULE = {
    "text": "Name the price of each item and the total.",
    "sources": ["good-reply"],
    "evidence": "Together: sixteen.",
}


@pytest.mark.asyncio
async def test_induction_reads_what_every_norm_reader_may_receive_and_refuses_what_they_may_not(tmp_path):
    scenario = load(make_scenario(tmp_path / "shop"))
    provider = Provider(
        response(NAME, {"rules": [{**RULE, "sources": ["prices"]}]}),
        response(NAME, {"rules": [{**RULE, "text": CHECK}]}),
        response(
            NAME,
            {"rules": [RULE, {"text": "Never offer a discount.", "sources": ["bad-reply"], "evidence": "half off"}]},
        ),
    )
    rules = await induce(provider, scenario, sealed=seals(scenario))
    assert [(rule.id, rule.sources) for rule in rules] == [
        ("induced-1", ("good-reply",)),
        ("induced-2", ("bad-reply",)),
    ]
    told = json.loads(provider.requests[0]["messages"][1]["content"])
    assert [row["name"] for row in told["norms"]] == ["sop"]
    assert [(row["name"], row["other_files"]) for row in told["exemplars"]] == [("good-reply", ["reply.pdf"])]
    assert [row["name"] for row in told["counterexamples"]] == ["bad-reply"]
    assert "facts" not in told and "Discounts above" not in json.dumps(told) and CHECK not in json.dumps(told)
    first, second = rejections(provider.requests[2])
    assert "not the instances given" in first and "the materials given do not" in second


@pytest.mark.asyncio
async def test_without_an_instance_nothing_is_induced_and_no_model_is_asked(tmp_path):
    provider = Provider()
    assert await induce(provider, load(make_scenario(tmp_path / "shop", instances=False))) == ()
    assert provider.requests == []


@pytest.mark.asyncio
async def test_the_model_party_decides_every_rule_by_the_materials_it_knows(tmp_path):
    scenario = load(make_scenario(tmp_path / "shop"))
    provider = Provider(
        response(NAME, {"rules": [RULE, {**RULE, "text": "Greet first."}, {**RULE, "text": "Say six."}]})
    )
    rules = await induce(provider, scenario)
    decided = [
        {"id": "induced-1", "status": "amended", "text": "Quote each item and the total, from the price list."},
        {"id": "induced-2", "status": "confirmed"},
        {"id": "induced-3", "status": "rejected", "reason": "Six was that one order's price."},
    ]
    party = ModelParty(
        Provider(
            response(DECIDE, {"decisions": decided[:2]}),
            response(DECIDE, {"decisions": [{**decided[0], "text": CHECK}, *decided[1:]]}),
            response(DECIDE, {"decisions": decided}),
        ),
        scenario,
        ["owner-policy", "sop"],
        sealed=seals(scenario),
    )
    decisions = await party.decide(rules)
    told = json.loads(party.provider.requests[0]["messages"][1]["content"])
    assert [row["name"] for row in told["your_materials"]] == ["owner-policy", "sop"]
    assert [(row["id"], row["kind"]) for row in told["items"]] == [
        ("induced-1", "norm"),
        ("induced-2", "norm"),
        ("induced-3", "norm"),
    ]
    assert told["items"][0]["read_from"] == ["good-reply"] and told["items"][0]["evidence"] == RULE["evidence"]
    first, second = rejections(party.provider.requests[2])
    assert "exactly one decision per item id" in first and "by your materials alone" in second
    settled = settle(rules, decisions)
    assert [decision.status for _, decision in settled] == ["amended", "confirmed", "rejected"]
    assert worded(*settled[0]).text == decided[0]["text"] and settled[0][0].text == RULE["text"]
    with pytest.raises(ValueError, match="must know materials"):
        ModelParty(Provider(), scenario, ["no-such-material"])


def test_a_decisions_file_names_only_recorded_items_and_what_it_leaves_out_stays_undecided(tmp_path):
    from experimental.research import Rule

    rules = [
        Rule("induced-1", "Greet first.", ("good-reply",), "Hello"),
        Rule("induced-2", "Say it.", ("good-reply",), ""),
    ]
    path = tmp_path / "decisions.json"
    path.write_text(json.dumps({"decisions": [{"id": "induced-2", "status": "confirmed"}]}))
    assert [decision.status for _, decision in settle(rules, Decisions.read(path))] == ["undecided", "confirmed"]
    path.write_text(json.dumps({"decisions": [{"id": "induced-9", "status": "confirmed"}]}))
    with pytest.raises(ValueError, match="not recorded"):
        settle(rules, Decisions.read(path))
    path.write_text(json.dumps({"decisions": [{"id": "induced-1", "status": "amended"}]}))
    with pytest.raises(ValueError, match="needs its wording"):
        Decisions.read(path)
