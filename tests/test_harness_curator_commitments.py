"""Harness commitments change by operations, keep their ids, and are held to the design and the artifact."""

import pytest

from experimental.harness.contract.commitments import (
    Commitment,
    CommitmentChange,
    apply,
    assign,
    check_artifact,
    check_design,
    coverage,
)

TARGETS = ("memory.strategy", "planning.strategy", "capability.strategy", "action.strategy")


def add(surface, *serves, statement="It does what the inputs need"):
    return CommitmentChange(action="add", surface=surface, statement=statement, serves=serves)


def current():
    """H1 supplies the norms on capability, H2 reviews deliveries on action, H3 is retired."""
    return (
        Commitment(id="H1", surface="capability.strategy", statement="Supply the norms", serves=("material:norms",)),
        Commitment(id="H2", surface="action.strategy", statement="Review deliveries", serves=("R1", "R2")),
        Commitment(id="H3", surface="action.strategy", statement="Old gate", serves=("R1",), retired="replaced"),
    )


def design(changes, *, selected, grounds=None, inputs=("R1", "R2", "R3", "material:norms"), authored=None):
    return check_design(
        current(),
        changes,
        surfaces=TARGETS,
        inputs=inputs,
        selected=selected,
        grounds=grounds or {},
        authored=authored if authored is not None else {"capability.strategy": {}, "action.strategy": {}},
    )


def test_operations_add_modify_and_retire_without_reusing_an_id():
    changes = assign(
        current(),
        [
            add("planning.strategy", "R3", statement="Track what is still owed"),
            CommitmentChange(action="modify", id="H2", serves=("R1",), reason="R2 moved to planning"),
            CommitmentChange(action="modify", id="H1", reason="implementation revised"),
        ],
    )
    assert changes[0].id == "H4"
    after = {item.id: item for item in apply(current(), changes)}
    assert after["H4"].surface == "planning.strategy" and after["H4"].serves == ("R3",)
    assert after["H2"].serves == ("R1",) and after["H2"].statement == "Review deliveries"
    assert after["H1"] == current()[0] and after["H3"].retired == "replaced"
    retired = apply(after.values(), [CommitmentChange(action="retire", id="H4", reason="no longer owed")])
    assert assign(retired, [add("memory.strategy", "R3")])[0].id == "H5"


@pytest.mark.parametrize(
    "change, message",
    [
        (CommitmentChange(action="modify", id="H3", reason="revive"), "names no current commitment"),
        (CommitmentChange(action="retire", id="H9", reason="gone"), "names no current commitment"),
        (CommitmentChange(action="add", id="H7", surface="action.strategy", statement="s", serves=("R1",)), "next"),
    ],
)
def test_apply_refuses_a_change_to_no_current_commitment_or_an_add_without_the_next_id(change, message):
    with pytest.raises(ValueError, match=message):
        apply(current(), [change])


def test_a_change_names_a_commitment_once_and_carries_what_its_action_needs():
    twice = [
        CommitmentChange(action="modify", id="H1", reason="a"),
        CommitmentChange(action="retire", id="H1", reason="b"),
    ]
    with pytest.raises(ValueError, match="more than once"):
        apply(current(), twice)
    with pytest.raises(ValueError, match="surface, statement and serves"):
        CommitmentChange(action="add", surface="action.strategy", statement="s")
    with pytest.raises(ValueError, match="id of a current commitment and a reason"):
        CommitmentChange(action="modify", id="H1")
    with pytest.raises(ValueError, match="only the id and the reason"):
        CommitmentChange(action="retire", id="H1", reason="gone", statement="still here")
    with pytest.raises(ValueError, match=r"leave the id .* \(here H4\)"):
        assign(
            current(),
            [CommitmentChange(action="add", id="H7", surface="action.strategy", statement="s", serves=("R1",))],
        )
    copied = CommitmentChange(action="add", id="H4", surface="action.strategy", statement="s", serves=("R1",))
    assert assign(current(), [copied]) == (copied,)


def test_the_design_must_change_commitments_exactly_on_the_selected_targets():
    with pytest.raises(ValueError, match=r"not selected: \['planning.strategy'\]"):
        design([add("planning.strategy", "R3")], selected=())
    with pytest.raises(ValueError, match=r"carry no commitment change: \['action.strategy'\]"):
        design([], selected=("action.strategy",))
    with pytest.raises(ValueError, match=r"carry no commitment change: \['memory.strategy'\]"):
        design([], selected=("memory.strategy",))
    moved = CommitmentChange(action="modify", id="H2", surface="planning.strategy", reason="planning owns it")
    with pytest.raises(ValueError, match="not selected"):
        design([moved], selected=("planning.strategy",))
    assert design([moved], selected=("planning.strategy", "action.strategy"))[0].id == "H2"
    revised = CommitmentChange(action="modify", id="H2", reason="the gate read the wrong file")
    assert design([revised], selected=("action.strategy",)) == (revised,)


def test_serves_only_changes_and_native_behavior_need_no_selection():
    repointed = CommitmentChange(action="modify", id="H1", serves=("material:norms", "R3"), reason="also serves R3")
    native = add("native", "R2", statement="The host's delivery tool hands the files over")
    changes = design([repointed, native], selected=())
    assert changes[1].id == "H4"
    selected = design([repointed], selected=("capability.strategy",), grounds={"capability.strategy": ("R3",)})
    assert selected == (repointed,)


def test_code_installed_without_a_design_is_kept_only_with_added_commitments():
    legacy = {"memory.strategy": {}, "capability.strategy": {}, "action.strategy": {}}
    assert design([], selected=("memory.strategy",), grounds={"memory.strategy": ("R3",)}, authored=legacy) == ()
    with pytest.raises(ValueError, match=r"code but no current commitment: \['memory.strategy'\]"):
        check_artifact(current(), valued=("memory.strategy",), removed=())
    check_artifact(current(), valued=(), removed=("memory.strategy",))
    kept = design([add("memory.strategy", "R3")], selected=("memory.strategy",), authored=legacy)
    check_artifact(apply(current(), kept), valued=("memory.strategy",), removed=())


def test_each_selected_targets_grounds_are_served_by_its_commitments_unless_all_are_retired():
    gate = add("action.strategy", "R3", statement="Check figures before delivery")
    with pytest.raises(ValueError, match=r"grounds action.strategy on \['material:norms'\]"):
        design([gate], selected=("action.strategy",), grounds={"action.strategy": ("R3", "material:norms")})
    assert design([gate], selected=("action.strategy",), grounds={"action.strategy": ("R1", "R3")})
    retire = CommitmentChange(action="retire", id="H2", reason="the gate stopped legitimate deliveries")
    assert design([retire], selected=("action.strategy",), grounds={"action.strategy": ("R2",)}) == (retire,)


def test_surfaces_and_served_inputs_come_from_the_grant_and_the_diagnoses():
    with pytest.raises(ValueError, match="not granted"):
        design([add("prompt.resource", "R1")], selected=())
    with pytest.raises(ValueError, match=r"not diagnosed: \['R9'\]"):
        design([add("action.strategy", "R9")], selected=("action.strategy",))
    kept = CommitmentChange(action="modify", id="H2", serves=("R2",), reason="R1 is served elsewhere")
    assert design([kept], selected=(), inputs=("task",))


def test_the_artifact_must_agree_with_the_list_it_runs_under():
    after = apply(current(), [CommitmentChange(action="retire", id="H2", reason="gone")])
    with pytest.raises(ValueError, match=r"code but no current commitment: \['action.strategy'\]"):
        check_artifact(after, valued=("action.strategy",), removed=())
    with pytest.raises(ValueError, match=r"still carry current commitments: \['capability.strategy'\]"):
        check_artifact(after, valued=(), removed=("capability.strategy",))
    check_artifact(after, valued=("capability.strategy",), removed=("action.strategy",))


def test_coverage_shows_unserved_inputs_and_stale_versioned_keys():
    listed = (
        *current(),
        Commitment(id="H4", surface="capability.strategy", statement="Read the facts", serves=("information:v1",)),
    )
    assert coverage(listed, ["R1", "R3", "material:norms", "information:v2", "task"]) == {
        "unserved": ["R3", "information:v2", "task"],
        "stale_serves": ["information:v1"],
    }
