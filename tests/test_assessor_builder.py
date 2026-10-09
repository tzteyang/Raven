"""The rubric builder writes grounded criteria, revises them only for an evidenced cause and never sees results."""

import json
from dataclasses import asdict

import pytest

from experimental.assessor.builder import RubricBuilder
from experimental.assessor.rubric import Basis, Definition, Reference, digest
from experimental.assessor.standard import Assessor, Criterion, Decidability, Standard
from experimental.iteration.protocols import Exchange
from tests.test_assessor_standard import Provider, execution, response, verdict

SOP = "Step 4: name the source of every price in the quote.\nStep 5: send the plan as a file named after the quote."
PRICES = "Prices are quoted in yuan, per person, with the season band named."
REVISE = "submit_revision"


def drafted(text, material="sop", quote="name the source of every price", section="Step 4", **extra):
    acceptance = text + ("\n" + extra.pop("acceptance") if extra.get("acceptance") else "")
    return {
        "definition": {
            "subject": "Worker output",
            "acceptance": acceptance,
            "applies_when": extra.pop("situation", ""),
        },
        "basis": {
            "references": [{"source": material, "quote": quote}],
            "derivation": "Task inference." if not quote else "",
        },
        "kind": extra.pop("kind", "quality"),
        "assessment": {
            "decision": {"method": "llm", "instruction": ""},
            "required_checks": [],
            "evidence_requirements": [],
        },
        **extra,
    }


def add(text, reason="new_norm", **extra):
    return {"op": "add", "criterion": drafted(text, **extra), "reason": reason, "explanation": "The norm states it."}


def packet(provider, index):
    return json.loads(provider.requests[index]["messages"][1]["content"])


def rejections(trace):
    return [row["error"] for row in trace if row["event"] == "output.rejected"]


@pytest.mark.parametrize("op", ["remove", "rewrite"])
def test_missing_evidence_cannot_remove_a_required_model_condition(op):
    from experimental.assessor.builder import Revision

    rule = Criterion(
        "derived-1",
        Definition("Worker output", "A receipt is produced.", ""),
        "derived",
        "gate",
        Basis((Reference("sop", "", digest(SOP)),), "Fixture interpretation."),
    )
    change = {"op": op, "id": rule.id, "reason": "undecided", "explanation": "The receipt is not visible."}
    if op == "rewrite":
        change["criterion"] = drafted("A receipt is optional.", quote="", kind="quality")
    with pytest.raises(ValueError, match="cannot remove or weaken"):
        RubricBuilder(read={"sop": digest(SOP)})._check(
            Revision.model_validate({"changes": [change]}),
            {"sop": SOP},
            Standard((rule,)),
            {rule.id: Decidability(False)},
        )


@pytest.mark.asyncio
async def test_criteria_are_written_from_the_norms_with_a_verbatim_quote():
    held = Standard.declared([("asks-budget", "Ask the budget first.")])
    builder = RubricBuilder()
    provider = Provider(
        response(REVISE, {"changes": [add("Name every price's source.", quote="name the origin of each price")]}),
        response(REVISE, {"changes": [add("Name every price's source.", material="sample-chat")]}),
        response(REVISE, {"changes": [add("Name every price's source.")], "unchecked": []}),
    )
    revised = await builder.revise(provider, {"sop": SOP}, held, {})
    errors = rejections(builder.trace)
    assert "not in 'sop' verbatim" in errors[0] and "only from the norms given" in errors[1]
    derived = revised.of("derived").criteria
    assert [(c.id, c.strength, c.basis.references[0].source, c.basis.references[0].quote) for c in derived] == [
        ("derived-1", "should", "sop", "name the source of every price")
    ]
    assert revised.criteria[0].id == "asks-budget"
    told = packet(provider, 0)
    assert told["new_norms"] == ["sop"]
    assert told["held"][0]["definition"]["acceptance"] == "Ask the budget first."
    assert told["held"][0]["authority"] == "external"
    change = builder.record()["versions"][0]["changes"][0]
    assert (change["id"], change["op"], change["reason"]) == ("derived-1", "add", "new_norm")
    assert change["criterion"]["definition"]["acceptance"] == "Name every price's source."
    assert derived[0].basis.references[0].version == digest(SOP)


@pytest.mark.asyncio
async def test_a_revision_needs_a_cause_the_evidence_shows_and_keeps_ids_and_strength():
    first = Criterion(
        "derived-1",
        Definition("Worker output", "Name every price's source.", ""),
        "derived",
        "gate",
        Basis((Reference("sop", "name the source of every price", digest(SOP)),), ""),
    )
    second = Criterion(
        "derived-2",
        Definition("Worker output", "Send the plan.", ""),
        "derived",
        "quality",
        Basis((Reference("sop", "send the plan as a file", digest(SOP)),), ""),
    )
    standard = Standard((first, second))
    builder = RubricBuilder(read={"sop": digest(SOP)}, max_calls=5)
    rewrite = {
        "op": "rewrite",
        "id": "derived-2",
        "criterion": drafted(
            "Send the plan as a file named after the quote.",
            quote="send the plan as a file named after the quote",
            section="Step 5",
        ),
        "reason": "undecided",
        "explanation": "The assessor could not tell a file from a pasted plan.",
    }
    unchanged = {**rewrite, "id": "derived-1", "criterion": drafted("Name every price's source.", kind="gate")}
    check_only = {
        key: value
        for key, value in asdict(second).items()
        if key in ("definition", "basis", "assessment", "kind", "parent_id")
    }
    check_only["basis"]["references"] = [{"source": "sop", "quote": "send the plan as a file"}]
    check_only["assessment"]["decision"]["instruction"] = "Read the delivered filename and verify the plan content."
    provider = Provider(
        response(REVISE, {"changes": [{**rewrite, "id": "derived-1"}]}),
        response(REVISE, {"changes": [unchanged | {"reason": "imprecise"}]}),
        response(REVISE, {"changes": [add("A rule.", reason="new_norm")]}),
        response(
            REVISE,
            {
                "changes": [
                    rewrite,
                    {"op": "remove", "id": "derived-1", "reason": "duplicate", "explanation": "Same as Step 5."},
                ]
            },
        ),
        response(REVISE, {"changes": [{**rewrite, "criterion": check_only}]}),
    )
    evidence = {"derived-1": Decidability(True), "derived-2": Decidability(False, "No file was named.")}
    revised = await builder.revise(provider, {"sop": SOP}, standard, evidence)
    errors = rejections(builder.trace)
    assert "was decided in the last round" in errors[0]
    assert "changes nothing" in errors[1]
    assert "new_norm applies only to a norm handed over since" in errors[2]
    assert "host patch scope" in errors[3]
    assert [(c.id, c.strength, c.definition.acceptance) for c in revised.criteria] == [
        ("derived-1", "must_hold", "Name every price's source."),
        ("derived-2", "should", "Send the plan."),
    ]
    assert revised.criteria[0] is first
    assert revised.criteria[1].assessment.decision.instruction == check_only["assessment"]["decision"]["instruction"]
    told = packet(provider, 0)
    assert told["new_norms"] == [] and {row["id"]: row["last_round"] for row in told["criteria"]} == {
        "derived-1": {"decided": True, "note": ""},
        "derived-2": {"decided": False, "note": "No file was named."},
    }
    assert "pass" not in json.dumps(told) and "fail" not in json.dumps(told)
    applied = builder.record()["versions"][0]["changes"]
    assert [(row["id"], row["op"], row["before"]["definition"]["acceptance"]) for row in applied] == [
        ("derived-2", "rewrite", "Send the plan."),
    ]


@pytest.mark.asyncio
async def test_a_norm_handed_over_is_drawn_on_or_listed_unchecked_and_only_then_may_a_revision_be_empty():
    builder = RubricBuilder()
    priced = {"material": "prices", "reason": "A held criterion checks it."}
    provider = Provider(
        response(REVISE, {}),
        response(REVISE, {"changes": [add("Name every price's source.")]}),
        response(REVISE, {"changes": [add("Name every price's source.")], "unchecked": [priced]}),
    )
    norms = {"sop": SOP, "prices": PRICES}
    revised = await builder.revise(provider, norms, Standard(), {})
    errors = rejections(builder.trace)
    assert len(errors) == 2
    assert "needs a criterion drawn from it or an unchecked entry saying why none: ['prices', 'sop']" in errors[0]
    assert "needs a criterion drawn from it or an unchecked entry saying why none: ['prices']" in errors[1]
    assert [criterion.id for criterion in revised.of("derived").criteria] == ["derived-1"]
    assert builder.record()["versions"][0]["unchecked"] == [priced | {"section": ""}]
    kept = await builder.revise(Provider(response(REVISE, {})), norms, revised, {})
    assert kept.criteria == revised.criteria and rejections(builder.trace) == errors


@pytest.mark.asyncio
async def test_the_assessor_revises_its_derived_criteria_each_round_from_what_the_assessor_could_decide(tmp_path):
    with pytest.raises(ValueError, match="needs a builder"):
        Assessor(Provider(), Standard(), sources=("derived",))
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
    assessor = Assessor(
        provider, Standard(), sources=("derived",), norms=lambda: handed, builder=RubricBuilder(), keep=kept
    )
    sessions = {"family": [Exchange("Hi", execution("t1", "Hello"))]}
    first = await assessor.evaluate(sessions)
    assert [(item.id, item.result) for item in first.items] == [("derived-1", "unknown")]
    assert [version["version"] for version in json.loads(kept.read_text())["rubric_builder"]["versions"]] == [1]
    handed["prices"] = PRICES
    second = await assessor.evaluate(sessions)
    assert [item.id for item in second.items] == ["derived-1", "derived-2"]
    later = packet(provider, 2)
    assert later["new_norms"] == ["prices"] and later["version"] == 1
    assert later["criteria"][0]["last_round"] == {"decided": False, "note": "No price was quoted."}
    record = assessor.record()
    assert json.loads(kept.read_text()) == json.loads(json.dumps(record))
    assert [version["version"] for version in record["rubric_builder"]["versions"]] == [1, 2]
    assert record["rubric_builder"]["read"] == {"prices": digest(PRICES), "sop": digest(SOP)}
    assert assessor.evidence == {"derived-1": Decidability(True), "derived-2": Decidability(True)}


@pytest.mark.asyncio
async def test_a_quote_matches_whatever_quotation_marks_it_was_copied_with():
    norm = 'Never call the product "an all-round assistant" in a headline.'
    builder = RubricBuilder()
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
    revised = await builder.revise(provider, {"norm": norm}, Standard(), {})
    assert packet(provider, 0)["norms"] == {
        "norm": "Never call the product \u201can all-round assistant\u201d in a headline."
    }
    assert "not in 'norm' verbatim" in rejections(builder.trace)[0]
    assert [criterion.basis.references[0].quote for criterion in revised.criteria] == [
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
    builder = RubricBuilder()
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
    revised = await builder.revise(provider, {"norm": norm}, Standard(), {})
    assert rejections(builder.trace) == [] and len(revised.criteria) == 3


@pytest.mark.asyncio
async def test_the_task_alone_can_generate_and_exercise_a_model_gate():
    task = "Prepare a quote that includes tax and stays within the customer's budget."
    gate = add("Include tax in the quoted total.", material="$task", quote="", section="", kind="gate")
    gate["explanation"] = "A budget comparison needs the payable total, so tax must be included."
    provider = Provider(
        response(REVISE, {"changes": [gate]}),
        response(
            "submit_verdicts", {"verdicts": [verdict("derived-1", "fail", "quote", "Subtotal: 100.", "Include tax.")]}
        ),
    )
    assessor = Assessor(provider, task=task, builder=RubricBuilder(), sources=("derived",))
    signal = await assessor.evaluate({"quote": [Exchange("Please quote.", execution("t1", "Subtotal: 100."))]})
    criterion = assessor.standard.criteria[0]
    assert (criterion.kind, criterion.strength, criterion.authority) == ("gate", "must_hold", "model")
    assert signal.satisfied is False and signal.items[0].actual == "Subtotal: 100."
    assert packet(provider, 0)["norms"] == {"$task": task}
    assert assessor.record()["rubric_builder"]["versions"][0]["changes"][0]["explanation"] == gate["explanation"]


@pytest.mark.parametrize("op", ["rewrite", "remove"])
@pytest.mark.asyncio
async def test_confirmation_protects_a_generated_criterion_against_builder_edits(op):
    criterion = Criterion(
        "derived-1",
        Definition("Worker output", "Name every source.", ""),
        "derived",
        "quality",
        Basis((Reference("sop", "", digest(SOP)),), "Fixture interpretation."),
    )
    standard = Standard((criterion,)).confirmed([criterion.id])
    change = {"op": op, "id": criterion.id, "reason": "beyond_norm", "explanation": "It is inconvenient."}
    if op == "rewrite":
        change["criterion"] = drafted("Name sources when convenient.")
    provider = Provider(response(REVISE, {"changes": [change]}), response(REVISE, {"changes": []}))
    builder = RubricBuilder(read={"sop": digest(SOP)})
    assert await builder.revise(provider, {"sop": SOP}, standard, {}) == standard
    assert not provider.requests
    from experimental.assessor.builder import Revision

    with pytest.raises(ValueError, match="protected external requirement"):
        builder._check(Revision.model_validate({"changes": [change]}), {"sop": SOP}, standard, {})
    assert standard.criteria[0].authority == "external" and standard.criteria[0].kind == "gate"


@pytest.mark.asyncio
async def test_source_versions_are_host_owned_and_changed_contents_are_new_inputs():
    initial = drafted("Name each source.")
    forged = drafted("Name each source.")
    forged["basis"]["references"][0]["version"] = "model-declared-version"
    provider = Provider(
        response(
            REVISE, {"changes": [{"op": "add", "criterion": forged, "reason": "new_norm", "explanation": "Bind it."}]}
        ),
        response(
            REVISE,
            {"changes": [{"op": "add", "criterion": initial, "reason": "new_norm", "explanation": "Ground the rule."}]},
        ),
    )
    builder = RubricBuilder()
    first = await builder.revise(provider, {"sop": SOP}, Standard(), {})
    assert "assigned by the host" in rejections(builder.trace)[0]
    assert first.criteria[0].basis.references[0].version == digest(SOP)
    updated = SOP + "\nUse the latest published source."
    correction = {
        "op": "rewrite",
        "id": "derived-1",
        "criterion": drafted("Name each source."),
        "reason": "new_norm",
        "explanation": "The source was updated.",
    }
    provider.responses.append(response(REVISE, {"changes": [correction]}))
    revised = await builder.revise(provider, {"sop": updated}, first, {})
    assert packet(provider, 2)["new_norms"] == ["sop"]
    assert revised.criteria[0].basis.references[0].version == digest(updated)
