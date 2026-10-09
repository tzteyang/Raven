"""The standard critic writes grounded criteria, revises them only for an evidenced cause and never sees results."""

import json

import pytest

from experimental.assessor.critic import Critic
from experimental.assessor.standard import Criterion, Decidability, Standard, StandardAssessor
from experimental.iteration.protocols import Exchange
from tests.test_assessor_standard import Provider, execution, response, verdict

SOP = "Step 4: name the source of every price in the quote.\nStep 5: send the plan as a file named after the quote."
PRICES = "Prices are quoted in yuan, per person, with the season band named."
REVISE = "submit_revision"


def drafted(text, material="sop", quote="name the source of every price", section="Step 4", **extra):
    return {"text": text, "material": material, "quote": quote, "section": section, **extra}


def add(text, reason="new_norm", **extra):
    return {"op": "add", "criterion": drafted(text, **extra), "reason": reason, "explanation": "The norm states it."}


def packet(provider, index):
    return json.loads(provider.requests[index]["messages"][1]["content"])


def rejections(trace):
    return [row["error"] for row in trace if row["event"] == "output.rejected"]


@pytest.mark.asyncio
async def test_criteria_are_written_from_the_norms_with_a_verbatim_quote():
    held = Standard.declared([("asks-budget", "Ask the budget first.")])
    critic = Critic()
    provider = Provider(
        response(REVISE, {"changes": [add("Name every price's source.", quote="name the origin of each price")]}),
        response(REVISE, {"changes": [add("Name every price's source.", material="sample-chat")]}),
        response(REVISE, {"changes": [add("Name every price's source.")], "unchecked": []}),
    )
    revised = await critic.revise(provider, {"sop": SOP}, held, {})
    errors = rejections(critic.trace)
    assert "not in 'sop' verbatim" in errors[0] and "only from the norms given" in errors[1]
    derived = revised.of("derived").criteria
    assert [(c.id, c.strength, c.provenance, c.quote) for c in derived] == [
        ("derived-1", "should", "material:sop Step 4", "name the source of every price")
    ]
    assert revised.criteria[0].id == "asks-budget"
    told = packet(provider, 0)
    assert told["new_norms"] == ["sop"] and told["held"] == [{"text": "Ask the budget first.", "situation": ""}]
    assert critic.record()["versions"][0]["changes"][0] == {
        "id": "derived-1",
        "op": "add",
        "reason": "new_norm",
        "explanation": "The norm states it.",
        "criterion": drafted("Name every price's source.") | {"situation": "", "acceptance": ""},
    }


@pytest.mark.asyncio
async def test_a_revision_needs_a_cause_the_evidence_shows_and_keeps_ids_and_strength():
    first = Criterion(
        "derived-1",
        "Name every price's source.",
        "derived",
        "must_hold",
        "material:sop Step 4",
        quote="name the source of every price",
    )
    second = Criterion(
        "derived-2", "Send the plan.", "derived", "should", "material:sop Step 5", quote="send the plan as a file"
    )
    standard = Standard((first, second))
    critic = Critic(read={"sop"})
    rewrite = {
        "op": "rewrite",
        "id": "derived-2",
        "criterion": drafted(
            "Send the plan as a file named after the quote.",
            quote="send the plan as a file named after the quote",
            section="Step 5",
        ),
        "reason": "undecided",
        "explanation": "The judge could not tell a file from a pasted plan.",
    }
    unchanged = {**rewrite, "id": "derived-1", "criterion": drafted("Name every price's source.")}
    provider = Provider(
        response(REVISE, {"changes": [{**rewrite, "id": "derived-1"}]}),
        response(REVISE, {"changes": [unchanged | {"reason": "imprecise"}]}),
        response(REVISE, {"changes": [add("A rule.", reason="new_norm")]}),
        response(
            REVISE,
            {
                "changes": [
                    rewrite,
                    {"op": "retire", "id": "derived-1", "reason": "duplicate", "explanation": "Same as Step 5."},
                ]
            },
        ),
    )
    evidence = {"derived-1": Decidability(True), "derived-2": Decidability(False, "No file was named.")}
    revised = await critic.revise(provider, {"sop": SOP}, standard, evidence)
    errors = rejections(critic.trace)
    assert "was decided in the last round" in errors[0]
    assert "changes nothing" in errors[1]
    assert "new_norm applies only to a norm handed over since" in errors[2]
    assert [(c.id, c.strength, c.text) for c in revised.criteria] == [
        ("derived-2", "should", "Send the plan as a file named after the quote.")
    ]
    told = packet(provider, 0)
    assert told["new_norms"] == [] and {row["id"]: row["last_round"] for row in told["criteria"]} == {
        "derived-1": {"decided": True, "note": ""},
        "derived-2": {"decided": False, "note": "No file was named."},
    }
    assert "pass" not in json.dumps(told) and "fail" not in json.dumps(told)
    applied = critic.record()["versions"][0]["changes"]
    assert [(row["id"], row["op"], row["before"]) for row in applied] == [
        ("derived-2", "rewrite", "Send the plan."),
        ("derived-1", "retire", "Name every price's source."),
    ]


@pytest.mark.asyncio
async def test_a_norm_handed_over_is_drawn_on_or_listed_unchecked_and_only_then_may_a_revision_be_empty():
    critic = Critic()
    priced = {"material": "prices", "reason": "A held criterion checks it."}
    provider = Provider(
        response(REVISE, {}),
        response(REVISE, {"changes": [add("Name every price's source.")]}),
        response(REVISE, {"changes": [add("Name every price's source.")], "unchecked": [priced]}),
    )
    norms = {"sop": SOP, "prices": PRICES}
    revised = await critic.revise(provider, norms, Standard(), {})
    errors = rejections(critic.trace)
    assert len(errors) == 2
    assert "needs a criterion drawn from it or an unchecked entry saying why none: ['prices', 'sop']" in errors[0]
    assert "needs a criterion drawn from it or an unchecked entry saying why none: ['prices']" in errors[1]
    assert [criterion.id for criterion in revised.of("derived").criteria] == ["derived-1"]
    assert critic.record()["versions"][0]["unchecked"] == [priced | {"section": ""}]
    kept = await critic.revise(Provider(response(REVISE, {})), norms, revised, {})
    assert kept.criteria == revised.criteria and rejections(critic.trace) == errors


@pytest.mark.asyncio
async def test_the_assessor_revises_its_derived_criteria_each_round_from_what_the_judge_could_decide(tmp_path):
    with pytest.raises(ValueError, match="needs a critic"):
        StandardAssessor(Provider(), Standard(), sources=("derived",))
    handed = {"sop": SOP}
    provider = Provider(
        response(REVISE, {"changes": [add("Name every price's source.")]}),
        response("submit_verdicts", {"verdicts": [verdict("derived-1", "unknown", note="No price was quoted.")]}),
        response(
            REVISE,
            {"changes": [add("Quote in yuan per person.", material="prices", quote="quoted in yuan, per person")]},
        ),
        response("submit_verdicts", {"verdicts": [verdict("derived-1", "fail"), verdict("derived-2", "pass")]}),
    )
    kept = tmp_path / "standard.json"
    assessor = StandardAssessor(
        provider, Standard(), sources=("derived",), norms=lambda: handed, critic=Critic(), keep=kept
    )
    sessions = {"family": [Exchange("Hi", execution("t1", "Hello"))]}
    first = await assessor.evaluate(sessions)
    assert [(item.id, item.result) for item in first.items] == [("derived-1", "unknown")]
    assert [version["version"] for version in json.loads(kept.read_text())["critic"]["versions"]] == [1]
    handed["prices"] = PRICES
    second = await assessor.evaluate(sessions)
    assert [item.id for item in second.items] == ["derived-1", "derived-2"]
    later = packet(provider, 2)
    assert later["new_norms"] == ["prices"] and later["version"] == 1
    assert later["criteria"][0]["last_round"] == {"decided": False, "note": "No price was quoted."}
    record = assessor.record()
    assert json.loads(kept.read_text()) == json.loads(json.dumps(record))
    assert [version["version"] for version in record["critic"]["versions"]] == [1, 2]
    assert record["critic"]["read"] == ["prices", "sop"]
    assert assessor.evidence == {"derived-1": Decidability(True), "derived-2": Decidability(True)}


@pytest.mark.asyncio
async def test_a_quote_matches_whatever_quotation_marks_it_was_copied_with():
    norm = 'Never call the product "an all-round assistant" in a headline.'
    critic = Critic()
    provider = Provider(
        response(
            REVISE, {"changes": [add("No all-round claim.", material="norm", quote="call the product an all-round")]}
        ),
        response(
            REVISE,
            {
                "changes": [
                    add("No all-round claim.", material="norm", quote="\u201can all-round assistant\u201d"),
                    add("No all-round headline.", material="norm", quote="'an all-round assistant' in a headline"),
                ]
            },
        ),
    )
    revised = await critic.revise(provider, {"norm": norm}, Standard(), {})
    assert packet(provider, 0)["norms"] == {
        "norm": "Never call the product \u201can all-round assistant\u201d in a headline."
    }
    assert "not in 'norm' verbatim" in rejections(critic.trace)[0]
    assert [criterion.quote for criterion in revised.criteria] == [
        "\u201can all-round assistant\u201d",
        "'an all-round assistant' in a headline",
    ]


@pytest.mark.asyncio
async def test_a_quote_matches_whatever_markdown_it_was_copied_without():
    norm = (
        "- **G4 Outside facts**: use only researched facts with a source.\n"
        "- [ ] Every price matches the last quote;\n"
        "- [ ] every outside fact is in the research.\n\n"
        "| Platform | Audience | Tone |\n| --- | --- | --- |\n| Douyin | students | casual |\n| Bilibili | makers | detailed |"
    )
    critic = Critic()
    provider = Provider(
        response(
            REVISE,
            {
                "changes": [
                    add(
                        "Outside facts are researched.",
                        material="norm",
                        quote="Outside facts: use only researched facts",
                    ),
                    add("Prices match.", material="norm", quote="matches the last quote;\n- every outside fact is in"),
                    add("Tone per platform.", material="norm", quote="Douyin | students | casual\nBilibili | makers"),
                ]
            },
        ),
    )
    revised = await critic.revise(provider, {"norm": norm}, Standard(), {})
    assert rejections(critic.trace) == [] and len(revised.criteria) == 3
