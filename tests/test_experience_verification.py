"""Check independent task grouping, protected behavior and frozen inputs in method comparisons."""

import pytest

from experimental.experience.verification import Case, Result, compare_methods


def cases():
    return (
        Case("missing", "source-a", {"consumers": 2}, references=("failure-1",)),
        Case("valid", "source-b", {"consumers": 1}),
    )


async def execute(instructions, case):
    actual = case.inputs["consumers"] if instructions == "all" else 1
    return Result(
        satisfied=actual == case.inputs["consumers"],
        preserved=True,
        record=f"{instructions}-{case.id}",
        cost={"calls": 1},
    )


@pytest.mark.asyncio
async def test_comparison_keeps_all_arms_and_accepts_only_observed_improvement():
    result = await compare_methods(
        before="first", after="all", history="historical", context="fixed", cases=cases(), evaluate=execute
    )
    assert result.accepted and result.independent_cases == 2
    assert all(row.history is not None for row in result.cases)
    assert result.cases[0].references == ("failure-1",)
    unchanged = await compare_methods(before="all", after="all", context="fixed", cases=cases(), evaluate=execute)
    assert not unchanged.accepted


@pytest.mark.asyncio
async def test_renaming_or_transitive_lineage_overlap_does_not_create_independence():
    related = (
        Case("a", "one", {"consumers": 1}),
        Case("b", "two", {"consumers": 1}),
        Case("c", "two", {"consumers": 2}),
    )
    result = await compare_methods(before="first", after="all", context="fixed", cases=related, evaluate=execute)
    assert result.independent_cases == 1 and not result.accepted


@pytest.mark.asyncio
async def test_protected_regression_and_unknown_history_prevent_admission():
    async def unsafe(instructions, case):
        base = await execute(instructions, case)
        return base.model_copy(update={"preserved": instructions != "all"})

    result = await compare_methods(before="first", after="all", context="fixed", cases=cases(), evaluate=unsafe)
    assert not result.accepted

    async def unknown(instructions, case):
        base = await execute(instructions, case)
        return base.model_copy(update={"satisfied": None}) if instructions == "history" else base

    result = await compare_methods(
        before="first", after="all", history="history", context="fixed", cases=cases(), evaluate=unknown
    )
    assert not result.accepted


@pytest.mark.asyncio
async def test_an_empty_timeout_error_cannot_approve_a_partial_comparison():
    async def interrupted(instructions, case):
        if case.id == "third":
            raise TimeoutError
        return await execute(instructions, case)

    result = await compare_methods(
        before="first",
        after="all",
        context="fixed",
        cases=(*cases(), Case("third", "source-c", {"consumers": 3})),
        evaluate=interrupted,
    )
    assert len(result.cases) == 2 and result.error == "TimeoutError"
    assert not result.accepted


@pytest.mark.asyncio
async def test_mutated_task_inputs_or_source_files_make_the_study_unusable(tmp_path):
    async def mutate(instructions, case):
        case.inputs["consumers"] = 0
        return Result(satisfied=True, preserved=True, record="changed-input")

    result = await compare_methods(before="first", after="all", context="fixed", cases=cases(), evaluate=mutate)
    assert result.error and not result.accepted
    source = tmp_path / "source.txt"
    source.write_text("frozen")

    async def rewrite(instructions, case):
        source.write_text("changed")
        return await execute(instructions, case)

    result = await compare_methods(
        before="first",
        after="all",
        context="fixed",
        evaluate=rewrite,
        cases=(Case("one", "one", {"consumers": 2}, (source,)), Case("two", "two", {"consumers": 1})),
    )
    assert result.error and not result.accepted
