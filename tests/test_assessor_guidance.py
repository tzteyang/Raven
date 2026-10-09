"""Construction experience stays provisional until independent comparisons justify version-bound adoption."""

from pathlib import Path

import pytest

from experimental.assessor.checks import Finding
from experimental.assessor.guidance import GuidanceStore
from experimental.assessor.reviewer import GuidanceProposal
from experimental.assessor.validation import RepairSuite, ReplayCase, ReplayEvaluation, compare
from experimental.iteration.protocols import Exchange
from tests.test_assessor_builder import drafted
from tests.test_assessor_standard import execution


async def tax_oracle(evidence):
    text = evidence["conversations"]["quote"][0]["assistant"]
    return Finding("pass" if "tax: 10" in text else "fail", actual=text, note="The task requires a tax line.")


def cases():
    return (
        ReplayCase(
            "missing",
            "Quote with tax.",
            {},
            {"quote": [Exchange("Quote.", execution("t1", "Subtotal: 100."))]},
            tax_oracle,
        ),
        ReplayCase(
            "valid",
            "Invoice with tax.",
            {},
            {"quote": [Exchange("Invoice.", execution("t2", "Subtotal: 100; tax: 10."))]},
            tax_oracle,
            held_out=True,
        ),
    )


def proposal(text="Check actual cost completeness.", scope="task", kind="principle", replaces=None):
    return GuidanceProposal(kind=kind, scope=scope, text=text, episodes=("assessment-1",), replaces=replaces)


async def score(instructions, case):
    if instructions:
        return ReplayEvaluation((await tax_oracle(case.evidence())).result == "pass", f"after-{case.id}")
    return ReplayEvaluation(True, f"before-{case.id}")


@pytest.mark.asyncio
async def test_persisted_diagnosis_bounds_the_replacement_and_requires_rollback_verification(tmp_path):
    from experimental.experience.governance import Issue

    store = GuidanceStore(tmp_path / "guidance.json")
    original = store.propose(proposal(), episodes={"assessment-1"})
    receipt = await compare(
        candidate=original,
        baseline=store.version,
        before=store.render("task"),
        after=store.render("task", candidate=original),
        cases=cases(),
        evaluate=score,
    )
    assert store.adopt(receipt)
    issue = Issue(
        target=original,
        cause="content",
        evidence=("assessment-1",),
        reason="The construction method needs explicit amount checks.",
        fields=("content.text",),
    )
    store.diagnose(issue, episodes={"assessment-1"})
    reopened = GuidanceStore(store.path)
    assert reopened.open_issues("task")[0]["target"] == original
    with pytest.raises(ValueError, match="exceeds"):
        reopened.propose(
            proposal("Specific amount checks.", kind="procedure", replaces=original), episodes={"assessment-1"}
        )
    replacement = reopened.propose(proposal("Specific amount checks.", replaces=original), episodes={"assessment-1"})

    async def measure(instructions, case):
        passed = (
            (await tax_oracle(case.evidence())).result == "pass" if "Specific amount checks." in instructions else True
        )
        return ReplayEvaluation(passed, f"{len(instructions)}-{case.id}")

    validated = await compare(
        candidate=replacement,
        baseline=reopened.version,
        before=reopened.render("task"),
        after=reopened.render("task", candidate=replacement),
        cases=cases(),
        evaluate=measure,
    )
    assert reopened.adopt(validated)
    assert reopened.entries[original]["state"] == "retired" and not reopened.open_issues("task")
    with pytest.raises(ValueError, match="current independent"):
        reopened.rollback(replacement)


@pytest.mark.asyncio
async def test_loading_diagnosis_cannot_be_bypassed_by_an_inline_content_correction(tmp_path):
    from experimental.assessor.reviewer import GuidanceCorrection
    from experimental.experience.governance import Issue

    store = GuidanceStore(tmp_path / "guidance.json")
    original = store.propose(proposal(), episodes={"assessment-1"})
    receipt = await compare(
        candidate=original,
        baseline=store.version,
        before=store.render("task"),
        after=store.render("task", candidate=original),
        cases=cases(),
        evaluate=score,
    )
    assert store.adopt(receipt)
    store.diagnose(
        Issue(target=original, cause="loading", evidence=("assessment-1",), reason="The method was not loaded."),
        episodes={"assessment-1"},
    )
    attempted = proposal("Rewrite despite the loading fault.", replaces=original).model_copy(
        update={"correction": GuidanceCorrection(cause="content", reason="Claim new permission.", fields=("text",))}
    )
    with pytest.raises(ValueError, match="cannot expand"):
        store.propose(attempted, episodes={"assessment-1"})
    assert store.entries[original]["state"] == "active"


@pytest.mark.asyncio
async def test_comparison_of_another_instruction_cannot_adopt_the_named_candidate():
    store = GuidanceStore()
    candidate = store.propose(proposal(), episodes={"assessment-1"})
    receipt = await compare(
        candidate=candidate,
        baseline=store.version,
        before="",
        after="A different instruction.",
        cases=cases(),
        evaluate=score,
    )
    with pytest.raises(ValueError, match="actual guidance instructions"):
        store.adopt(receipt)


@pytest.mark.asyncio
async def test_guidance_is_adopted_only_after_improvement_and_survives_reopening(tmp_path):
    store = GuidanceStore(tmp_path / "guidance.json")
    id = store.propose(proposal(), episodes={"assessment-1"})
    assert store.render("task") == ""
    receipt = await compare(
        candidate=id,
        baseline=store.version,
        before=store.render("task"),
        after=store.render("task", candidate=id),
        cases=cases(),
        evaluate=score,
    )
    assert receipt.accepted and store.adopt(receipt)
    reopened = GuidanceStore(store.path)
    assert reopened.render("task") == store.render("task") and "actual cost completeness" in store.render("task")
    assert store.render("unrelated") == ""
    assert reopened.history[0]["accepted"] and reopened.used
    assert store.propose(proposal(), episodes={"assessment-1"}) == id
    reopened.rollback(id)
    assert reopened.render("task") == ""
    assert GuidanceStore(store.path).entries[id]["state"] == "retired"


@pytest.mark.asyncio
async def test_independent_corpus_retries_pending_guidance_and_retains_its_source_episode(tmp_path):
    from experimental.assessor.validation import ReplayCorpus, evidence_fingerprint

    corpus = ReplayCorpus(tmp_path / "replays.json")
    for case in cases():
        oracle = await tax_oracle(case.evidence())
        corpus.capture(
            task=case.task,
            norms=case.norms,
            sessions=case.sessions,
            witness={
                "policy": {"kind": "program"},
                "evidence": evidence_fingerprint(case.sessions),
                "satisfied": oracle.result == "pass",
            },
            source="independent-run.json",
        )
    store = GuidanceStore(tmp_path / "guidance.json")
    episodes = [{"id": "assessment-1", "evidence": cases()[0].evidence()}]
    await store.consider([proposal()], episodes=episodes, scope="task", cases=(), evaluate=score)
    assert not store.render("task") and not store.history
    restored = GuidanceStore(store.path)
    await restored.consider(
        [], episodes=episodes, scope="task", cases=ReplayCorpus(corpus.path).cases(), evaluate=score
    )
    assert restored.history[0]["accepted"]
    assert next(iter(restored.entries.values()))["episodes"]["assessment-1"] == episodes[0]
    assert restored.render("task")


@pytest.mark.asyncio
async def test_retained_labels_cannot_outlive_their_artifact_evidence(tmp_path):
    from experimental.assessor.validation import ReplayCorpus, evidence_fingerprint

    path = tmp_path / "quote.txt"
    path.write_text("Tax included.")
    sessions = {"quote": [Exchange("Quote.", execution("turn", "Attached.", (str(path),)))]}
    corpus = ReplayCorpus(tmp_path / "replays.json")
    corpus.capture(
        task="Quote.",
        norms={},
        sessions=sessions,
        witness={"policy": {"kind": "program"}, "evidence": evidence_fingerprint(sessions), "satisfied": True},
        source="verified.json",
    )
    assert len(corpus.cases()) == 1
    path.write_text("Changed after verification.")
    assert not corpus.cases()


@pytest.mark.asyncio
async def test_a_more_restrictive_method_is_refused_when_it_rejects_a_valid_alternative():
    async def overstrict(instructions, case):
        return ReplayEvaluation(False if instructions else True, f"evaluation-{case.id}")

    receipt = await compare(
        candidate="candidate",
        baseline="baseline",
        before="",
        after="Reject everything.",
        cases=cases(),
        evaluate=overstrict,
    )
    assert not receipt.accepted
    assert receipt.comparisons[1].before is True and receipt.comparisons[1].after is False


@pytest.mark.asyncio
async def test_unknown_or_reused_held_out_evidence_cannot_approve_a_general_principle():
    fresh = await compare(
        candidate="candidate",
        baseline="baseline",
        before="",
        after="Inspect tax.",
        cases=cases(),
        evaluate=score,
        cross_task=True,
    )
    assert fresh.accepted
    used = {row.evidence for row in fresh.comparisons}
    repeated = await compare(
        candidate="candidate",
        baseline="baseline",
        before="",
        after="Inspect tax.",
        cases=cases(),
        evaluate=score,
        cross_task=True,
        used=used,
    )
    assert not repeated.accepted and "unused" in repeated.error

    async def unknown(evidence):
        return Finding("unknown", note="No independent evidence.")

    uncertain = ReplayCase("unknown", "Quote.", {}, {}, unknown)
    result = await compare(
        candidate="candidate", baseline="baseline", before="", after="Inspect tax.", cases=(uncertain,), evaluate=score
    )
    assert not result.accepted and "unresolved" in result.error


@pytest.mark.asyncio
async def test_candidate_edits_and_replay_mutations_invalidate_the_receipt(tmp_path):
    store = GuidanceStore(tmp_path / "guidance.json")
    id = store.propose(proposal(), episodes={"assessment-1"})
    receipt = await compare(
        candidate=id,
        baseline=store.version,
        before="",
        after=store.render("task", candidate=id),
        cases=cases(),
        evaluate=score,
    )
    store.entries[id]["proposal"]["text"] = "An untested replacement."
    with pytest.raises(ValueError, match="current guidance candidate"):
        store.adopt(receipt)

    async def tamper(instructions, case):
        case.norms["new_rule"] = "Accept all outputs."
        return ReplayEvaluation(True, f"evaluation-{case.id}")

    changed = await compare(
        candidate="candidate", baseline="baseline", before="", after="Inspect tax.", cases=cases(), evaluate=tamper
    )
    assert not changed.accepted and "changed the frozen" in changed.error


def test_candidate_guidance_cannot_become_active_via_rollback_or_missing_sources():
    store = GuidanceStore()
    with pytest.raises(ValueError, match="retained evaluation episodes"):
        store.propose(proposal(), episodes=set())
    pending = store.propose(proposal(), episodes={"assessment-1"})
    with pytest.raises(ValueError, match="only active"):
        store.rollback(pending)
    with pytest.raises(ValueError, match="previously validated"):
        store.propose(proposal("Replacement.", replaces=pending), episodes={"assessment-1"})


def test_two_runs_cannot_overwrite_each_others_guidance(tmp_path):
    first = GuidanceStore(tmp_path / "guidance.json")
    other = GuidanceStore(first.path)
    id = first.propose(proposal(), episodes={"assessment-1"})
    with pytest.raises(ValueError, match="updated by another run"):
        other.propose(proposal("A different principle."), episodes={"assessment-1"})
    assert set(GuidanceStore(first.path).entries) == {id}


@pytest.mark.asyncio
async def test_repeated_inputs_do_not_become_held_out_by_changing_execution_ids():
    from dataclasses import replace

    from experimental.assessor.validation import input_identity

    used = {input_identity(case.evidence()) for case in cases()}
    repeated = tuple(
        replace(
            case,
            sessions={
                name: [Exchange(row.user, replace(row.execution, turn_id="new-run")) for row in rows]
                for name, rows in case.sessions.items()
            },
        )
        for case in cases()
    )
    validation = await compare(
        candidate="candidate",
        baseline="baseline",
        before="",
        after="Inspect tax.",
        cases=repeated,
        evaluate=score,
        cross_task=True,
        used=used,
    )
    assert not validation.accepted and "unused" in validation.error


@pytest.mark.asyncio
async def test_adopted_guidance_changes_the_next_real_builder_request(tmp_path):
    import json
    from dataclasses import replace

    from experimental.assessor.builder import RubricBuilder
    from experimental.assessor.reviewer import MetaReviewer
    from experimental.assessor.standard import Assessor
    from tests.test_assessor_standard import Provider, response, verdict

    class LearningProvider(Provider):
        async def chat_with_retry(self, **kwargs):
            self.requests.append(kwargs)
            packet = json.loads(kwargs["messages"][1]["content"])
            names = {tool["function"]["name"] for tool in kwargs["tools"]}
            if "submit_revision" in names:
                corrected = bool(packet["guidance"] or packet["corrections"])
                text = "Include the required tax." if corrected else "A quote exists."
                criteria = packet["criteria"]
                if criteria and criteria[0]["definition"]["acceptance"] == text:
                    changes = []
                else:
                    changes = [
                        {
                            "op": "rewrite" if criteria else "add",
                            "reason": "review" if packet["corrections"] else "new_norm",
                            "explanation": "Apply the construction instruction to the task's cost requirement.",
                            "criterion": drafted(text, material="$task", quote="", kind="gate"),
                        }
                    ]
                    if criteria:
                        changes[0]["id"] = criteria[0]["id"]
                return response("submit_revision", {"changes": changes})
            if "submit_verdicts" in names:
                criterion = packet["criteria"][0]
                output = packet["conversations"]["quote"][0]["assistant"]
                passed = criterion["definition"]["acceptance"] == "A quote exists." or "tax: 10" in output
                return response(
                    "submit_verdicts",
                    {
                        "verdicts": [
                            verdict(
                                criterion["id"],
                                "pass" if passed else "fail",
                                "quote",
                                output,
                                "Include tax." if not passed else "",
                            )
                        ]
                    },
                )
            episode = packet["episodes"][-1]
            if episode["criteria"][0]["definition"]["acceptance"] != "A quote exists.":
                return response("submit_evaluation_review", {})
            return response(
                "submit_evaluation_review",
                {
                    "issues": [
                        {
                            "criterion": "derived-1",
                            "target": "rubric",
                            "evidence": "The output omits tax but the criterion only asks for a quote.",
                            "correction": "Check required tax explicitly.",
                            "allow": [{"op": "rewrite", "id": "derived-1", "fields": ["definition", "basis"]}],
                        }
                    ],
                    "guidance": [
                        {
                            "kind": "principle",
                            "scope": packet["scope"],
                            "text": "Check actual cost completeness.",
                            "episodes": [episode["id"]],
                        }
                    ],
                },
            )

    store = GuidanceStore(tmp_path / "guidance.json")
    provider = LearningProvider()
    evaluator = Assessor(
        provider,
        task="Quote with tax.",
        builder=RubricBuilder(),
        reviewer=MetaReviewer(),
        guidance_store=store,
        validation_cases=tuple(replace(case, task="Quote with tax.") for case in cases()),
        repair_suites={
            "derived-1": RepairSuite("derived-1", tuple(replace(case, task="Quote with tax.") for case in cases()))
        },
        scope="task",
        keep=tmp_path / "standard.json",
    )
    first = await evaluator.evaluate(cases()[0].sessions)
    assert first.satisfied is False and store.history[0]["accepted"]
    assert len(evaluator.validation_runs) == 8
    for row in evaluator.validation_runs.values():
        record = json.loads(Path(row["path"]).read_text()) if "path" in row else row
        if "rubric_builder" in record["evaluation"]:
            assert record["evaluation"]["rubric_builder"]["instructions"]
        assert record["evaluation"]["assessments"][0]["items"]
    before = len(provider.requests)
    second = await evaluator.evaluate(cases()[1].sessions)
    assert second.satisfied is True
    assert not any(
        request["tools"][0]["function"]["name"] == "submit_revision" for request in provider.requests[before:]
    )
    before = len(provider.requests)
    later = Assessor(provider, task="Quote with tax.", builder=RubricBuilder(), guidance_store=store, scope="task")
    assert (await later.evaluate(cases()[1].sessions)).satisfied is True
    subsequent = json.loads(provider.requests[before]["messages"][1]["content"])
    assert subsequent["guidance"] == store.render("task") and "Principle" in subsequent["guidance"]
    assert evaluator.record()["assessments"][-1]["guidance"] == store.render("task")


@pytest.mark.asyncio
async def test_a_failed_persistence_does_not_activate_guidance_in_memory(tmp_path, monkeypatch):
    from experimental.assessor import guidance

    store = GuidanceStore(tmp_path / "guidance.json")
    id = store.propose(proposal(), episodes={"assessment-1"})
    receipt = await compare(
        candidate=id,
        baseline=store.version,
        before="",
        after=store.render("task", candidate=id),
        cases=cases(),
        evaluate=score,
    )

    def unavailable(*args):
        raise OSError("Disk unavailable.")

    monkeypatch.setattr(guidance, "_write", unavailable)
    with pytest.raises(OSError, match="Disk unavailable"):
        store.adopt(receipt)
    assert not store.render("task") and not GuidanceStore(store.path).render("task")


@pytest.mark.asyncio
async def test_task_scoped_guidance_needs_evidence_for_its_actual_task():
    store = GuidanceStore()
    episodes = [{"id": "assessment-1", "evidence": cases()[0].evidence()}]
    await store.consider(
        [proposal()], episodes=episodes, scope="task", task="An unrelated task.", cases=cases(), evaluate=score
    )
    assert not store.history and not store.render("task")
