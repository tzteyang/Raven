"""Meta-review repairs evaluation defects once, preserves evidence and cannot approve its own guidance."""

import json
from dataclasses import asdict

import pytest

from experimental.assessor.builder import RubricBuilder
from experimental.assessor.checks import Finding
from experimental.assessor.reviewer import REVIEW, MetaReviewer
from experimental.assessor.rubric import AssessmentPlan, Basis, Definition, LLMCheck, ProgramCheck, Reference, digest
from experimental.assessor.standard import Assessor, Criterion, Standard
from experimental.assessor.validation import RepairSuite, ReplayCase
from experimental.iteration.protocols import Exchange
from tests.test_assessor_builder import drafted
from tests.test_assessor_standard import Provider, execution, response, verdict


@pytest.mark.asyncio
@pytest.mark.parametrize("independent", [False, True])
async def test_a_superficial_rubric_is_repaired_once_and_needs_independent_validation(independent):
    rule = "A quotation includes every required cost and applicable tax."
    weak = Criterion(
        "derived-1",
        Definition("Worker output", "A quote exists.", ""),
        "derived",
        "gate",
        Basis((Reference("sop", "", digest(rule)),), "Fixture interpretation."),
    )
    provider = Provider(
        response("submit_verdicts", {"verdicts": [verdict("derived-1", "pass", "quote")]}),
        response(
            REVIEW,
            {
                "issues": [
                    {
                        "criterion": "derived-1",
                        "target": "rubric",
                        "evidence": "The quote contains a subtotal without tax.",
                        "correction": "Check required costs and tax, not only the existence of a quote.",
                        "allow": [{"op": "rewrite", "id": "derived-1", "fields": ["definition", "basis"]}],
                    }
                ],
                "guidance": [
                    {
                        "kind": "principle",
                        "scope": "task",
                        "text": "Check semantic completeness instead of existence alone.",
                        "episodes": ["test:assessment-1"],
                    }
                ],
            },
        ),
        response(
            "submit_revision",
            {
                "changes": [
                    {
                        "op": "rewrite",
                        "id": "derived-1",
                        "reason": "review",
                        "explanation": "Existence omitted a required cost.",
                        "criterion": drafted(
                            "Include all required costs and tax.", material="sop", quote=rule, kind="gate"
                        ),
                    }
                ]
            },
        ),
        response(
            "submit_verdicts", {"verdicts": [verdict("derived-1", "fail", "quote", "Subtotal: 100.", "Include tax.")]}
        ),
    )
    cases = []
    if independent:
        for index, passed in enumerate((False, True)):
            text = "Subtotal: 100; tax: 10." if passed else "Subtotal: 100."

            async def oracle(evidence, passed=passed):
                return Finding("pass" if passed else "fail", "Independent tax coverage check.")

            cases.append(
                ReplayCase(
                    str(index), "", {"sop": rule}, {"quote": [Exchange("Quote.", execution(str(index), text))]}, oracle
                )
            )
            provider.responses.extend(
                [
                    response("submit_verdicts", {"verdicts": [verdict("derived-1", "pass", "quote", text)]}),
                    response(
                        "submit_verdicts",
                        {"verdicts": [verdict("derived-1", "pass" if passed else "fail", "quote", text)]},
                    ),
                ]
            )
    assessor = Assessor(
        provider,
        Standard((weak,)),
        norms={"sop": rule},
        builder=RubricBuilder(read={"sop": digest(rule)}),
        reviewer=MetaReviewer(),
        repair_suites={"derived-1": RepairSuite("derived-1", tuple(cases))} if independent else None,
    )
    assessor.run_id = "test"
    signal = await assessor.evaluate({"quote": [Exchange("Please quote.", execution("t1", "Subtotal: 100."))]})
    assert signal.satisfied is (False if independent else None)
    assert signal.items[0].result == ("fail" if independent else "unknown")
    assert len(provider.requests) == (8 if independent else 4) and len(assessor.reviewer.reviews) == 1
    record = assessor.record()
    assert [episode["items"][0]["result"] for episode in record["assessments"]] == ["pass", "fail"]
    assert record["meta_reviewer"]["reviews"][0]["guidance"][0]["kind"] == "principle"
    assert "active" not in record["meta_reviewer"]["reviews"][0]["guidance"][0]
    if not independent:
        preserved = assessor.standard
        later_cases = []
        provider.responses.extend(
            [
                response("submit_verdicts", {"verdicts": [verdict("derived-1", "fail", "quote")]}),
                response(REVIEW, {}),
            ]
        )
        for index, passed in enumerate((False, True)):
            output = "Subtotal: 100; tax: 10." if passed else "Subtotal: 100."

            async def oracle(evidence, passed=passed):
                return Finding("pass" if passed else "fail", "Independent tax coverage.")

            later_cases.append(
                ReplayCase(
                    str(index),
                    "",
                    {"sop": rule},
                    {"quote": [Exchange("Quote.", execution(str(index), output))]},
                    oracle,
                )
            )
            provider.responses.extend(
                [
                    response("submit_verdicts", {"verdicts": [verdict("derived-1", "pass", "quote")]}),
                    response(
                        "submit_verdicts", {"verdicts": [verdict("derived-1", "pass" if passed else "fail", "quote")]}
                    ),
                ]
            )
        assessor.repair_suites["derived-1"] = RepairSuite("derived-1", tuple(later_cases))
        assert (
            await assessor.evaluate({"quote": [Exchange("Please quote.", execution("t1", "Subtotal: 100."))]})
        ).satisfied is False
        assert not assessor.open_issues and assessor.standard == preserved


@pytest.mark.asyncio
async def test_a_model_review_cannot_vote_away_an_observed_program_failure():
    async def arithmetic(evidence):
        return Finding("fail", "Required total: 110; delivered total: 100.", "Tax was omitted.", "quote")

    criterion = Criterion(
        "tax",
        Definition("Worker output", "Include tax.", ""),
        "declared",
        "gate",
        Basis((Reference("check:tax", "Include tax.", ""),), ""),
        authority="external",
        assessment=AssessmentPlan(decision=None, required_checks=(ProgramCheck(verifier="arithmetic"),)),
    )
    provider = Provider(
        response(
            REVIEW,
            {
                "issues": [
                    {
                        "criterion": "tax",
                        "target": "check",
                        "evidence": "The model considers the subtotal sufficient.",
                        "correction": "Ignore the failed check.",
                    }
                ]
            },
        )
    )
    assessor = Assessor(
        provider,
        Standard((criterion,)),
        sources=("declared",),
        verifiers={"arithmetic": arithmetic},
        reviewer=MetaReviewer(),
    )
    signal = await assessor.evaluate({"quote": [Exchange("Please quote.", execution("t1", "Subtotal: 100."))]})
    assert signal.satisfied is False and signal.items[0].result == "fail"
    assert len(provider.requests) == 1 and assessor.standard.criteria == (criterion,)


@pytest.mark.asyncio
async def test_guidance_cannot_cite_an_invented_episode():
    provider = Provider(
        response(
            REVIEW,
            {
                "guidance": [
                    {"kind": "procedure", "scope": "task", "text": "Inspect evidence.", "episodes": ["invented"]}
                ]
            },
        ),
        response(REVIEW, {}),
    )
    reviewer = MetaReviewer()
    result = await reviewer.review(provider, task="Quote.", norms={}, assessment={"id": "assessment-1", "criteria": []})
    assert not result.guidance
    assert any("supplied evaluation episodes" in row.get("error", "") for row in reviewer.trace)


@pytest.mark.asyncio
@pytest.mark.parametrize("reassessment_passes", [False, True])
async def test_a_failed_program_survives_reassessment_or_a_model_only_repair(reassessment_passes):
    async def missing_cost(evidence):
        return Finding("fail", "Subtotal: 100.", "Tax missing.", "quote")

    original = Criterion(
        "derived-1",
        Definition("Worker output", "Include costs.", ""),
        "derived",
        "gate",
        Basis((Reference("sop", "", digest("Include tax.")),), "Fixture interpretation."),
        assessment=AssessmentPlan(decision=LLMCheck(), required_checks=(ProgramCheck(verifier="cost_check"),)),
    )
    provider = Provider(
        response("submit_verdicts", {"verdicts": [verdict("derived-1", "pass")]}),
        response(
            REVIEW,
            {
                "issues": [
                    {
                        "criterion": "derived-1",
                        "target": "rubric",
                        "evidence": "Costs are not enumerated.",
                        "correction": "Include tax explicitly.",
                        "allow": [
                            {"op": "rewrite", "id": "derived-1", "fields": ["definition", "basis", "assessment"]}
                        ],
                    }
                ]
            },
        ),
        response(
            "submit_revision",
            {
                "changes": [
                    {
                        "op": "rewrite",
                        "id": "derived-1",
                        "reason": "review",
                        "explanation": "Make the tax condition explicit.",
                        "criterion": drafted("Include tax.", material="sop", quote="Include tax.", kind="gate"),
                    }
                ]
            },
        ),
    )
    assessor = Assessor(
        provider,
        Standard((original,)),
        norms={"sop": "Include tax."},
        builder=RubricBuilder(read={"sop": digest("Include tax.")}),
        reviewer=MetaReviewer(),
        verifiers={"cost_check": missing_cost},
    )
    if reassessment_passes:
        provider.responses.append(response("submit_verdicts", {"verdicts": [verdict("derived-1", "pass")]}))
    signal = await assessor.evaluate({"quote": [Exchange("Quote it.", execution("t1", "Subtotal: 100."))]})
    assert assessor.standard.criteria == (original,)
    assert signal.satisfied is False and signal.items[0].note == "Tax missing."
    if not reassessment_passes:
        assert "repair_error" in assessor.assessments[0] and "error" in assessor.assessments[1]
    else:
        assert assessor.assessments[1]["retained_program_failures"] == ["derived-1"]


@pytest.mark.asyncio
async def test_independent_property_cases_can_validate_a_checker_repair_without_erasing_its_failure():
    text = "Include applicable tax."
    original = Criterion(
        "tax",
        Definition("Quote", text),
        "derived",
        "gate",
        Basis((Reference("policy", text, digest(text)),)),
        assessment=AssessmentPlan(required_checks=(ProgramCheck(verifier="broken"),)),
    )

    async def broken(evidence):
        return Finding("fail", "The parser read a missing field.")

    async def fixed(evidence):
        output = evidence["conversations"]["quote"][0]["assistant"]
        return Finding("pass" if "tax: 10" in output else "fail", output)

    class RepairProvider(Provider):
        async def chat_with_retry(self, **kwargs):
            self.requests.append(kwargs)
            data = json.loads(kwargs["messages"][1]["content"])
            names = {entry["function"]["name"] for entry in kwargs["tools"]}
            if "submit_verdicts" in names:
                return response("submit_verdicts", {"verdicts": [verdict(c["id"], "pass") for c in data["criteria"]]})
            if "submit_evaluation_review" in names:
                return response(
                    "submit_evaluation_review",
                    {
                        "issues": [
                            {
                                "criterion": "tax",
                                "target": "check",
                                "evidence": "The parser reads a missing field despite tax being present.",
                                "correction": "Check the retained quote text.",
                                "allow": [{"op": "rewrite", "id": "tax", "fields": ["assessment.required_checks"]}],
                            }
                        ]
                    },
                )
            candidate = {
                key: value
                for key, value in asdict(original).items()
                if key in {"definition", "basis", "assessment", "kind", "parent_id"}
            }
            candidate["basis"]["references"] = [{"source": "policy", "quote": text}]
            candidate["assessment"]["required_checks"] = [{"method": "program", "verifier": "fixed"}]
            return response(
                "submit_revision",
                {
                    "changes": [
                        {
                            "op": "rewrite",
                            "id": "tax",
                            "reason": "review",
                            "explanation": "Use the quote field.",
                            "criterion": candidate,
                        }
                    ]
                },
            )

    cases = []
    for name, output, result in (("missing", "Subtotal: 100.", "fail"), ("valid", "Subtotal: 100; tax: 10.", "pass")):

        async def oracle(evidence, result=result):
            return Finding(result, "Independently verified tax coverage for this preserved example.")

        cases.append(
            ReplayCase(name, "", {"policy": text}, {"quote": [Exchange("Quote.", execution(name, output))]}, oracle)
        )
    assessor = Assessor(
        RepairProvider(),
        Standard((original,)),
        norms={"policy": text},
        builder=RubricBuilder(read={"policy": digest(text)}),
        reviewer=MetaReviewer(),
        verifiers={"broken": broken, "fixed": fixed},
        repair_suites={"tax": RepairSuite("tax", tuple(cases))},
    )
    signal = await assessor.evaluate(cases[1].sessions)
    assert signal.satisfied is True and not assessor.open_issues
    assert assessor.standard.criteria[0].definition == original.definition
    assert assessor.assessments[0]["checks"][-1]["result"] == "fail"
    assert assessor.assessments[1]["repair_validation"]["tax"]["accepted"] is True
    assert assessor.assessments[1]["retained_program_failures"] == []
