"""A requirement holds when the round after its revision neither raises it again nor fails a check it rests on, and
stays undecided when that round never exercised it; the session writes that into the history the Curator reads, and the ledger joins requirement, diagnosis, change and
outcome by id, grouped by the attributor that diagnosed them."""

import pytest

from experimental.analyst.feedback import Feedback
from experimental.iteration.conversation import Conversation
from experimental.iteration.history import Diagnosed, Entry, Raised, Revised
from experimental.iteration.ledger import held, mark, rows, summary
from experimental.iteration.protocols import Item, Signal
from experimental.iteration.run import run
from experimental.iteration.session import Limits
from tests.test_iteration_run import (
    REQUIREMENT,
    FakeWorker,
    Scripted,
    Verifier,
    analyses,  # noqa: F401 -- the loop test's Analyst stand-in
    curations,  # noqa: F401 -- the loop test's Curator stand-in
    failing,
    passing,
)

BUDGET = Raised(
    id="R1", behavior="Ask the budget first.", strength="must_hold", acceptance="a", grounds=("check:asks budget",)
)
MODEL = {"implementation": "model", "prompts": "p1", "model": "m", "catalogue": True}


def feedback(*ids):
    return Feedback(
        decision="curate" if ids else "continue",
        reason="r",
        requirements=tuple({**REQUIREMENT, "id": number, "grounds": ["check:asks budget"]} for number in ids),
    )


def test_a_requirement_holds_unless_raised_again_or_its_regression_check_or_a_check_it_rests_on_fails():
    assert held(BUDGET, feedback(), (passing(),)) is True
    assert held(BUDGET, feedback("R1"), (passing(),)) is False
    assert held(BUDGET, feedback("R2"), (failing(),)) is False
    assert held(BUDGET, None, (Signal("human", "Better."),)) is True
    assert held(BUDGET, feedback(), ()) is None
    case = Raised(id="R2", behavior="b", strength="should", acceptance="a", grounds=("case:c7", "assessor:owner"))
    assert held(case, feedback(), (Signal("data", items=(Item("c7", "fail"),)),)) is False
    assert held(case, feedback(), (Signal("data", items=(Item("c8", "fail"),)),)) is True
    regression = (Signal("standard", items=(Item("R2", "fail"),)),)
    assert held(case, feedback(), regression) is False and held(BUDGET, feedback(), regression) is True
    unexercised = (Signal("standard", items=(Item("R2", "unknown"), Item("c7", "unknown"))),)
    assert held(case, feedback(), unexercised) is None
    assert held(case, feedback(), (Signal("standard", items=(Item("R2", "pass"), Item("c7", "unknown"))),)) is True


def test_the_ledger_joins_each_requirement_to_its_diagnosis_its_changes_and_whether_it_held():
    first = Entry(
        round=1,
        requirements=(BUDGET, Raised(id="R2", behavior="Quote the list.", strength="should", acceptance="a")),
        revision=(
            Revised(target="planning.strategy", treatment="add", addresses=("R1",)),
            Revised(target="memory.strategy", treatment="modify", addresses=("R1", "material:sop")),
        ),
        diagnoses=(Diagnosed(about="R1", state="absent"), Diagnosed(about="R2", state="model_ignored")),
        attributor=MODEL,
    )
    judged = mark(first, feedback("R2"), (passing(),))
    assert [raised.held for raised in judged.requirements] == [True, False]
    joined = rows([judged, Entry(round=2, requirements=(BUDGET,)).model_dump(mode="json")])
    assert [(row["round"], row["requirement"], row["state"], row["held"]) for row in joined] == [
        (1, "R1", "absent", True),
        (1, "R2", "model_ignored", False),
        (2, "R1", None, None),
    ]
    assert joined[0]["changes"] == [
        {"scope": "root", "target": "planning.strategy", "treatment": "add"},
        {"scope": "root", "target": "memory.strategy", "treatment": "modify"},
    ]
    assert joined[0]["diagnoses"] == [{"scope": "root", "state": "absent"}]
    assert joined[1]["changes"] == [] and joined[1]["attributor"] == MODEL and not joined[2]["curated"]
    grouped = {(row["state"], row["treatment"]): (row["judged"], row["held"]) for row in summary(joined)}
    assert grouped == {("absent", "add"): (1, 1), ("absent", "modify"): (1, 1), ("model_ignored", None): (1, 0)}
    other = [{**row, "attributor": {**MODEL, "prompts": "p2"}} for row in joined]
    assert len(summary(joined + other)) == 2 * len(summary(joined))


@pytest.mark.asyncio
async def test_the_next_rounds_analysis_decides_whether_the_last_rounds_requirements_held(
    tmp_path, curations, analyses
):
    analyses.scripted.extend([feedback("R1"), feedback("R2"), feedback()])
    verifier = Verifier(failing(), failing(), passing())
    trial = Conversation(Scripted("student", "Hi", "Hi again", "Hi once more"), max_turns=1)
    await run(FakeWorker(tmp_path), object(), [trial], [verifier], limits=Limits(max_rounds=3))
    heard = curations[2]["feedback"]["history"]
    (first,) = [entry for entry in heard if entry["round"] == 1]
    assert [(row["id"], row["held"]) for row in first["requirements"]] == [("R1", False)]
    assert "grounds" not in first["requirements"][0]
    assert analyses.calls[1]["history"][-1].requirements[0].held is None


def test_a_composite_curations_child_changes_and_diagnoses_join_the_entry_under_their_scope():
    from types import SimpleNamespace

    from experimental.curator.harness import Change, Plan
    from experimental.curator.harness.artifact import Selection
    from experimental.curator.harness.attribution import Attributed, Attribution, Diagnosis
    from experimental.iteration.history import entry

    def plan(target):
        change = Change(target=target, reason="r", expected="e", verification="v", treatment="add")
        return Plan(understanding="u", design="d", changes=(change,))

    def attributed(state):
        return Attributed(attribution=Attribution(diagnoses=(Diagnosis(about="R1", state=state, evidence=("t1",)),)))

    child = SimpleNamespace(
        plan=plan("action.review"),
        selection=Selection(understanding="u", targets=("action.review",), grounds={"action.review": ("R1",)}),
        attribution=attributed("uncovered"),
    )
    root_selection = Selection(understanding="u", targets=("memory.strategy",), grounds={"memory.strategy": ("R1",)})
    made = entry(
        1,
        (),
        feedback("R1"),
        plan("memory.strategy"),
        attribution=attributed("not_exposed"),
        selection=root_selection,
        children={"Raven-PPT": child, "Raven": None},
    )
    assert [(change.scope, change.target, change.addresses) for change in made.revision] == [
        ("root", "memory.strategy", ("R1",)),
        ("child/Raven-PPT", "action.review", ("R1",)),
    ]
    assert [(diagnosis.scope, diagnosis.state) for diagnosis in made.diagnoses] == [
        ("root", "not_exposed"),
        ("child/Raven-PPT", "uncovered"),
    ]
    (row,) = rows([made])
    assert row["state"] == "not_exposed" and [change["scope"] for change in row["changes"]] == [
        "root",
        "child/Raven-PPT",
    ]
