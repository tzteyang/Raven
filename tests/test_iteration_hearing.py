"""What reaches the Curator of a round: projected signals, the cited turns under opaque session keys, and the words
it hears from the conversant not sealed against it."""

import json

from experimental.analyst.feedback import Feedback
from experimental.curator.raven_adapter.worker import Execution
from experimental.iteration.hearing import cited, heard, heard_activity, heard_history, heard_observations, opaque
from experimental.iteration.history import Diagnosed, Entry, Raised, Revised
from experimental.iteration.protocols import Exchange, Handover, Item, Signal
from experimental.requirements import Requirement
from experimental.scenario.sealed import Sealed


def exchange(turn, user, records=()):
    return Exchange(user, Execution(turn, [], list(records), {"status": "ok"}, "artifact-1"))


def curate(*evidence, observed="The reply recommended without asking."):
    return Feedback(
        decision="curate",
        reason="Intake gap.",
        requirements=(
            Requirement(
                behavior="Ask for the budget before recommending.",
                observed=observed,
                evidence=evidence,
                expectation="new",
                acceptance="The first recommendation follows a budget question.",
                strength="must_hold",
            ),
        ),
    )


def test_the_curator_hears_words_and_satisfaction_never_items_or_metrics():
    signal = Signal(
        "verifier",
        "Never asked the budget.",
        items=(Item("asks-budget", "fail", "family", expected="A budget question", note="Reply to Plan"),),
        metrics={"pass_rate": 0.0},
        satisfied=False,
        attachments=(Handover("sop", "norm", ("uploads/sop/sop.md",)),),
    )
    assert heard([signal]) == [
        {
            "source": "verifier",
            "text": "Never asked the budget.",
            "satisfied": False,
            "attachments": [{"name": "sop", "kind": "norm", "files": ["uploads/sop/sop.md"]}],
        }
    ]
    round_one = Entry(
        round=1,
        satisfied={"verifier": False},
        results={"verifier": {"S2.1": "fail"}},
        failed_in={"verifier": {"S2.1": "family-of-three"}},
        requirements=(
            Raised(
                id="R1",
                behavior="Ask the budget first.",
                strength="must_hold",
                acceptance="A budget question comes first.",
                grounds=("check:S2.1",),
                held=False,
            ),
        ),
        understanding="Intake skips the budget.",
        revision=(
            Revised(
                target="planning.strategy",
                treatment="add",
                reason="Budget first.",
                addresses=("R1",),
                expected="Asks first.",
                verification="Read the first reply.",
            ),
        ),
        diagnoses=(Diagnosed(about="R1", state="absent"),),
        attributor={"implementation": "model"},
    )
    (seen,) = heard_history([round_one])
    assert seen == {
        "round": 1,
        "satisfied": {"verifier": False},
        "requirements": [
            {
                "id": "R1",
                "situation": "",
                "behavior": "Ask the budget first.",
                "strength": "must_hold",
                "acceptance": "A budget question comes first.",
                "repeats": None,
                "materials": [],
                "held": False,
            }
        ],
        "mechanisms_acted": [],
        "understanding": "Intake skips the budget.",
        "revision": [
            {
                "scope": "root",
                "target": "planning.strategy",
                "treatment": "add",
                "reason": "Budget first.",
                "addresses": ["R1"],
            }
        ],
        "diagnoses": [{"about": "R1", "state": "absent", "mechanism": "", "earlier": "", "scope": "root"}],
    }


def test_only_the_cited_turns_go_to_the_curator_under_opaque_session_keys():
    sessions = {
        "family-of-three": [
            exchange("turn-1", "We are two adults and one child.", [{"kind": "runner.event"}]),
            exchange("turn-10", "Anything cheaper?"),
        ],
        "honeymoon": [exchange("turn-2", "Just the two of us.")],
    }
    rows = heard_observations(sessions, curate("turn-1"), "task-1")
    assert [(row["session"], row["turn_id"]) for row in rows] == [(opaque("family-of-three"), "turn-1")]
    assert rows[0]["user"] == "We are two adults and one child." and rows[0]["records"] == [{"kind": "runner.event"}]
    assert rows[0]["kind"] == "task.execution" and rows[0]["source"] == "trial"
    assert rows[0]["task_id"] == "task-1" and rows[0]["artifact_id"] == "artifact-1"
    assert rows[0]["outcome"] == {"status": "ok"}
    told = json.dumps(rows)
    assert "family" not in told and "honeymoon" not in told and "turn-10" not in told
    by_observation = heard_observations(sessions, curate("the reply", observed="turn-2 answered at once."), "t")
    assert [(row["session"], row["turn_id"]) for row in by_observation] == [(opaque("honeymoon"), "turn-2")]
    assert heard_observations(sessions, None, "task-1") == []
    assert heard_observations(sessions, curate("no turn named"), "task-1") == []
    assert [key for key, _ in cited(sessions, curate("turn-1", "turn-2"))] == [
        opaque("family-of-three"),
        opaque("honeymoon"),
    ]
    assert opaque("honeymoon") == opaque("honeymoon") != opaque("family-of-three")
    rows = [{"session": "honeymoon", "target": "action.tool_gates", "decision": "refused", "acted": True}]
    assert heard_activity(rows) == [{**rows[0], "session": opaque("honeymoon")}] and rows[0]["session"] == "honeymoon"
    entry = Entry(round=1, mechanisms_acted=tuple(rows))
    assert "honeymoon" not in json.dumps(heard_history([entry]))


def test_what_the_conversant_said_is_not_sealed_against_whoever_heard_it():
    card = "A family of two adults and one child with a budget of 8000 for the first week of October."
    sealed = Sealed.of([card, "Check C1: the deck lists every price."], tokens=["case-7"])
    spoken = "We are a family of two adults and one child with a budget of 8000."
    assert sealed.hits(spoken) == ["<sealed text>"]
    heard_words = sealed.without([spoken])
    assert heard_words.hits(spoken) == []
    assert heard_words.hits("Two adults and one child with a budget of 8000, noted.") == []
    assert heard_words.hits("They said with a budget of 8000 for the first week of October.") == ["<sealed text>"]
    assert heard_words.hits("Check C1: the deck lists every price.") == ["<sealed text>"]
    assert heard_words.hits("This is case-7.") == ["case-7"]
    wide = "\uff43\uff41\uff53\uff45-7"
    assert heard_words.hits("This is CASE\u20117.") == heard_words.hits(f"This is {wide}.") == ["case-7"]
    assert Sealed.of(["a short one"]).without(["said a short one"]).hits("a short one") == []
    first, second = (
        "We are a family of two adults and one child",
        "with a budget of 8000 for the first week of October.",
    )
    assert sealed.without([(first, second)]).hits(f"{first} {second}") == []
    assert sealed.without([(first,), (second,)]).hits(f"{first} {second}") == ["<sealed text>"]


def test_the_prior_is_heard_as_its_histories_under_opaque_labels():
    from experimental.iteration.hearing import heard_prior
    from experimental.iteration.history import Entry, Raised
    from experimental.iteration.records import Cultivation

    first = Entry(
        round=1,
        satisfied={"agency": False},
        requirements=(Raised(id="R1", behavior="Ask the budget.", strength="must_hold", acceptance="Asked."),),
        results={"agency": {"asks-budget": "fail"}},
        failed_in={"agency": {"asks-budget": "family"}},
        attributor={"implementation": "model"},
    )
    heard = heard_prior([Cultivation((first,)), Cultivation(())])
    assert [item["cultivation"] for item in heard] == ["prior-1", "prior-2"] and heard[1]["history"] == []
    (entry,) = heard[0]["history"]
    assert entry["requirements"][0]["id"] == "R1" and "grounds" not in entry["requirements"][0]
    assert not {"results", "failed_in", "attributor"} & set(entry)
