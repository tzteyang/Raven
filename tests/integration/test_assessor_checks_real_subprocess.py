"""Program evidence and missing results cannot be overridden by a model's favorable assessment."""

import pytest

from experimental.harness.assessor.checks import Finding, combine, expression, program

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_a_generated_arithmetic_check_detects_a_real_defect_after_calibration():
    spec = 'evidence["total"] == sum(evidence["costs"])'
    examples = [({"total": 110, "costs": [100, 10]}, True), ({"total": 100, "costs": [100, 10]}, False)]
    failed = await program({"total": 120, "costs": [100, 30]}, verifiers={}, examples=examples, expression_source=spec)
    passed = await program({"total": 130, "costs": [100, 30]}, verifiers={}, examples=examples, expression_source=spec)
    assert failed.result == "fail" and passed.result == "pass"
    assert combine([Finding("pass", "The model approved it."), failed]).result == "fail"


@pytest.mark.asyncio
async def test_missing_evidence_or_unvalidated_programs_remain_unknown():
    assert (await expression('evidence["missing"] == 1', {})).result == "unknown"
    assert (await program({}, expression_source="True", verifiers={})).result == "unknown"
    assert (await program({}, verifier="absent", verifiers={})).result == "unknown"
    examples = [({"total": 1}, True), ({"total": 0}, False)]
    assert (await program({}, expression_source="True", verifiers={}, examples=examples)).result == "unknown"
    assert combine([Finding("pass"), Finding("unknown")]).result == "unknown"
    assert combine([Finding("pass"), Finding("not_applicable")]).result == "unknown"


@pytest.mark.parametrize(
    "source",
    ["__import__('os').getcwd() == '/'", "evidence.__class__ is dict", "open('/tmp/secret')", "2 ** 100000000"],
)
@pytest.mark.asyncio
async def test_generated_programs_cannot_escape_the_evidence_expression(source):
    assert (await expression(source, {})).result == "unknown"


@pytest.mark.asyncio
async def test_host_verifier_errors_are_evidence_gaps_and_never_passes():
    async def broken(evidence):
        raise OSError("Artifact unavailable.")

    result = await program({}, verifier="check_artifact", verifiers={"check_artifact": broken})
    assert result.result == "unknown" and "Artifact unavailable" in result.note
