"""Hierarchical construction preserves source authority, local patch boundaries and independent judgments."""

import asyncio
import json
from dataclasses import asdict, replace

import pytest

from experimental.assessor.builder import Revision, RubricBuilder
from experimental.assessor.checks import Finding
from experimental.assessor.reviewer import Issue, MetaReviewer
from experimental.assessor.revision import Permission, RevisionScope
from experimental.assessor.rubric import (
    AssessmentPlan,
    Basis,
    Criterion,
    Definition,
    EvidenceRequirement,
    Reference,
    digest,
)
from experimental.assessor.standard import Assessor, Standard
from experimental.assessor.validation import RepairSuite, ReplayCase
from experimental.iteration.protocols import Exchange
from experimental.requirements import ExternalRequirement
from raven.contracts.llm_provider import LLMResponse
from tests.test_assessor_builder import drafted
from tests.test_assessor_standard import Provider, execution, response, verdict

POLICY = "Include all mandatory fees and taxes. The total must stay within the supplied budget."
NORMS = {"policy": POLICY}


def rule(id, parent=None):
    return Criterion(
        id,
        Definition("Quote", POLICY),
        "derived",
        "gate",
        Basis((Reference("policy", POLICY, digest(POLICY)),)),
        parent_id=parent,
    )


def addition(text, parent=None, refine="", reason="new_norm"):
    return {
        "op": "add",
        "reason": reason,
        "explanation": "A necessary part of the supplied cost obligation.",
        "refine": refine,
        "criterion": drafted(text, material="policy", quote=POLICY, kind="gate", parent_id=parent),
    }


@pytest.mark.parametrize(
    "criteria",
    [
        (rule("a"), rule("a")),
        (rule("a", "missing"),),
        (rule("a", "b"), rule("b", "a")),
    ],
)
def test_a_forest_rejects_duplicate_ids_or_missing_and_cyclic_parents(criteria):
    with pytest.raises(ValueError):
        Standard(criteria)


@pytest.mark.asyncio
async def test_dynamic_horizontal_and_vertical_construction_uses_one_type_and_stops_by_branch():
    provider = Provider(
        response(
            "submit_revision",
            {
                "changes": [
                    addition("Include all fees.", refine="Separate required cost categories."),
                    addition("Stay within budget."),
                ]
            },
        ),
        response(
            "submit_revision",
            {
                "changes": [
                    addition("Include tax.", "derived-1", reason="uncovered"),
                    addition("Include lodging.", "derived-1", "Check all nights.", "uncovered"),
                ]
            },
        ),
        response(
            "submit_revision", {"changes": [addition("Include every required night.", "derived-4", reason="uncovered")]}
        ),
    )
    builder = RubricBuilder()
    result = await builder.revise(provider, NORMS, Standard(), {})
    assert [(c.id, c.parent_id) for c in result.criteria] == [
        ("derived-1", None),
        ("derived-2", None),
        ("derived-3", "derived-1"),
        ("derived-4", "derived-1"),
        ("derived-5", "derived-4"),
    ]
    assert not builder.pending and builder.runs[-1]["calls"] == 3
    requests = [json.loads(r["messages"][1]["content"]) for r in provider.requests]
    assert requests[1]["scope"]["allow"] == [{"op": "add", "id": None, "parent_id": "derived-1", "fields": []}]
    assert requests[2]["target"] == "derived-4"
    assert "could a valid result" in provider.requests[0]["messages"][0]["content"].lower()
    assert await builder.revise(Provider(), NORMS, result, {}) is result


@pytest.mark.asyncio
async def test_budget_exhaustion_retains_pending_work_and_resume_continues_without_rebuilding_roots():
    builder = RubricBuilder(max_calls=1)
    first = await builder.revise(
        Provider(response("submit_revision", {"changes": [addition(POLICY, refine="Enumerate cost categories.")]})),
        NORMS,
        Standard(),
        {},
    )
    assert builder.runs[-1]["status"] == "call_budget_exhausted"
    assert builder.unresolved == {"derived-1": "Enumerate cost categories."}
    saved = builder.record()
    resumed = RubricBuilder(max_calls=1)
    resumed.restore(saved)
    result = await resumed.revise(
        Provider(response("submit_revision", {"changes": [addition("Include tax.", "derived-1", reason="uncovered")]})),
        NORMS,
        first,
        {},
    )
    assert result.criteria[0] is first.criteria[0]
    assert result.criteria[1].parent_id == "derived-1"
    assert not resumed.unresolved


@pytest.mark.asyncio
async def test_rejected_submissions_consume_the_actual_call_budget():
    builder = RubricBuilder(max_calls=2)
    provider = Provider(
        response("submit_revision", {"wrong": True}),
        response("submit_revision", {"wrong": True}),
        response("submit_revision", {"changes": [addition(POLICY)]}),
    )
    result = await builder.revise(provider, NORMS, Standard(), {})
    assert not result.criteria
    assert len(provider.requests) == 2
    assert builder.runs[-1]["calls"] == 2 and builder.pending


@pytest.mark.asyncio
async def test_cut_output_retries_are_charged_and_node_limits_reject_whole_patches():
    provider = Provider(
        LLMResponse(content="", finish_reason="length"), LLMResponse(content="", finish_reason="length")
    )
    builder = RubricBuilder(max_calls=2)
    assert not (await builder.revise(provider, NORMS, Standard(), {})).criteria
    assert len(provider.requests) == 2
    assert all(row["charged"] for row in builder.trace if row.get("cut"))
    provider = Provider(
        response("submit_revision", {"changes": [addition("Include fees."), addition("Include tax.")]}),
        response("submit_revision", {"changes": [addition(POLICY)]}),
    )
    builder = RubricBuilder(max_nodes=1)
    result = await builder.revise(provider, NORMS, Standard(), {})
    assert len(result.criteria) == 1 and result.criteria[0].id == "derived-1"
    assert any("node budget" in row.get("error", "") for row in builder.trace)


@pytest.mark.parametrize("reason", ["imprecise", "beyond_norm", "review"])
def test_a_reason_cannot_expand_a_review_patch_scope(reason):
    first, other = rule("c1"), rule("c2")
    baseline = Standard((first, other))
    issue = Issue(
        criterion="c1",
        target="check",
        evidence="The amount parser reads the wrong field.",
        correction="Correct the parser.",
        allow=(Permission(op="rewrite", id="c1", fields=("assessment",)),),
    )
    change = {
        "op": "rewrite",
        "id": "c2",
        "reason": reason,
        "explanation": "Clarify another criterion.",
        "criterion": drafted("List all fees.", material="policy", quote=POLICY, kind="gate"),
    }
    builder = RubricBuilder(read={"policy": digest(POLICY)})
    with pytest.raises(ValueError, match="scope|review requires"):
        builder._check(Revision(changes=[change]), NORMS, baseline, {}, (issue,))
    assert baseline.criteria == (first, other) and not builder.versions


def test_checker_only_scope_preserves_definition_and_rejects_stale_inputs():
    baseline = Standard((rule("c1"),))
    scope = RevisionScope.bind(baseline, NORMS, [Permission(op="rewrite", id="c1", fields=("assessment",))])
    change = {
        "op": "rewrite",
        "id": "c1",
        "reason": "imprecise",
        "explanation": "Change the acceptance instead.",
        "criterion": drafted("Any quote is sufficient.", material="policy", quote=POLICY, kind="gate"),
    }
    builder = RubricBuilder(read={"policy": digest(POLICY)})
    with pytest.raises(ValueError, match="scope"):
        builder._check(Revision(changes=[change]), NORMS, baseline, {}, scope=scope)
    with pytest.raises(ValueError, match="changed"):
        builder._check(Revision(), {"policy": POLICY + " Cite prices."}, baseline, {}, scope=scope)
    change["criterion"] = {
        key: value
        for key, value in asdict(baseline.criteria[0]).items()
        if key in {"definition", "basis", "kind", "assessment", "parent_id"}
    }
    change["criterion"]["basis"]["references"] = [{"source": "policy", "quote": POLICY}]
    change["criterion"]["assessment"]["decision"]["instruction"] = "Check the supplied cost evidence."
    change["refine"] = "Add a new obligation after this checker change."
    with pytest.raises(ValueError, match="refinement follow-up"):
        builder._check(Revision(changes=[change]), NORMS, baseline, {}, scope=scope)


def test_removing_a_parent_never_implicitly_removes_or_reparents_children():
    baseline = Standard((rule("a"), rule("b", "a")))
    builder = RubricBuilder(read={"policy": digest(POLICY)})
    scope = RevisionScope.bind(baseline, NORMS, [Permission(op="remove", id="a")])
    patch = Revision(changes=[{"op": "remove", "id": "a", "reason": "duplicate", "explanation": "Merge a duplicate."}])
    with pytest.raises(ValueError, match="parent"):
        builder._check(patch, NORMS, baseline, {}, scope=scope)
    assert baseline.criteria[1].parent_id == "a"


@pytest.mark.asyncio
async def test_children_passing_does_not_establish_a_parent_and_tree_metrics_do_not_count_duplicates():
    standard = Standard((rule("all"), rule("tax", "all")))
    provider = Provider(
        response(
            "submit_verdicts",
            {"verdicts": [verdict("all", "fail", note="A mandatory cost is absent."), verdict("tax", "pass")]},
        )
    )
    assessor = Assessor(provider, standard, norms=NORMS)
    signal = await assessor.evaluate({"run": [Exchange("Quote.", execution("one", "Tax included; lodging omitted."))]})
    assert signal.satisfied is False
    assert signal.items[1].parent_id == "all"
    assert signal.metrics == {}
    assert assessor.assessments[0]["rubric_version"] == standard.version


@pytest.mark.asyncio
async def test_a_review_cannot_authorize_unrelated_nodes_or_definitions_for_a_checker():
    reviewer = MetaReviewer()
    provider = Provider(
        response(
            "submit_evaluation_review",
            {
                "issues": [
                    {
                        "criterion": "a",
                        "target": "check",
                        "evidence": "Bad parser.",
                        "correction": "Fix it.",
                        "allow": [{"op": "rewrite", "id": "a", "fields": ["definition"]}],
                    }
                ]
            },
        ),
        response("submit_evaluation_review", {"issues": []}),
    )
    result = await reviewer.review(
        provider, task="Quote.", norms=NORMS, assessment={"id": "run:1", "criteria": [asdict(rule("a"))]}
    )
    assert not result.issues
    assert any("only assessment" in row.get("error", "") for row in reviewer.trace)


@pytest.mark.asyncio
async def test_schema_two_resumes_flat_and_source_projection_hides_ancestors(tmp_path):
    path = tmp_path / "standard.json"
    stored = Assessor(Provider(), Standard((rule("a"),)), norms=NORMS).record()
    stored["schema"] = 2
    stored["criteria"][0].pop("parent_id")
    path.write_text(json.dumps(stored))
    assessor = Assessor(Provider(), sources=("declared",), keep=path)
    assessor.restore()
    assert assessor.standard.criteria[0].parent_id is None
    assert assessor.record()["schema"] == 3
    assert json.loads(path.read_text())["schema"] == 2
    changed = replace(assessor.standard.criteria[0], authority="external", origin="declared")
    visible = Standard((changed, rule("child", "a"))).of("derived")
    assert [(c.id, c.parent_id, c.authority) for c in visible.criteria] == [("child", None, "model")]


def test_schema_two_retains_the_previous_method_but_uses_the_current_construction_protocol(tmp_path):
    stored = Assessor(Provider(), Standard((rule("a"),)), norms=NORMS).record()
    stored["schema"] = 2
    stored["rubric_builder"] = {
        "instructions": "Legacy flat generation with retire operations.",
        "read": {"policy": digest(POLICY)},
    }
    path = tmp_path / "standard.json"
    path.write_text(json.dumps(stored))
    resumed = Assessor(Provider(), norms=NORMS, builder=RubricBuilder(), keep=path)
    resumed.restore()
    assert "parent_id" in resumed.builder.instructions and "scope.allow" in resumed.builder.instructions
    assert resumed.builder.runs[-1]["previous_instructions"] == stored["rubric_builder"]["instructions"]
    assert resumed.standard.criteria == (rule("a"),)


@pytest.mark.asyncio
async def test_schema_three_resumes_the_pending_branch_without_synthetic_checker_permission(tmp_path):
    assessor = Assessor(
        Provider(
            response("submit_revision", {"changes": [addition(POLICY, refine="Check tax coverage.")]}),
            response("submit_verdicts", {"verdicts": [verdict("derived-1", "pass")]}),
        ),
        norms=NORMS,
        builder=RubricBuilder(max_calls=1),
        keep=tmp_path / "standard.json",
    )
    sessions = {"run": [Exchange("Quote.", execution("one", "All required charges are included."))]}
    assert (await assessor.evaluate(sessions)).satisfied is None
    resumed = Assessor(
        Provider(
            response("submit_revision", {"changes": [addition("Include tax.", "derived-1", reason="uncovered")]}),
            response("submit_verdicts", {"verdicts": [verdict("derived-1", "pass"), verdict("derived-2", "pass")]}),
        ),
        norms=NORMS,
        builder=RubricBuilder(),
        keep=assessor.keep,
    )
    resumed.restore()
    assert (await resumed.evaluate(sessions)).satisfied is True
    assert resumed.standard.criteria[1].parent_id == "derived-1"
    scope = json.loads(resumed.provider.requests[0]["messages"][1]["content"])["scope"]
    assert [permission["op"] for permission in scope["allow"]] == ["add"]
    assert not resumed.builder.pending


@pytest.mark.asyncio
async def test_an_unvalidated_downgrade_keeps_the_original_gate_blocking():
    first, second = rule("first"), rule("second")
    draft = {
        key: value
        for key, value in asdict(first).items()
        if key in {"definition", "basis", "kind", "assessment", "parent_id"}
    }
    draft["basis"]["references"] = [{"source": "policy", "quote": POLICY}]
    draft["kind"] = "quality"
    assessor = Assessor(
        Provider(
            response("submit_verdicts", {"verdicts": [verdict("first", "pass"), verdict("second", "pass")]}),
            response(
                "submit_evaluation_review",
                {
                    "issues": [
                        {
                            "criterion": "first",
                            "target": "rubric",
                            "evidence": "The reviewer suspects an overstrict classification.",
                            "correction": "Review its mandatory status.",
                            "allow": [{"op": "rewrite", "id": "first", "fields": ["kind"]}],
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
                            "id": "first",
                            "reason": "review",
                            "explanation": "Propose optional status.",
                            "criterion": draft,
                        }
                    ]
                },
            ),
            response("submit_verdicts", {"verdicts": [verdict("first", "pass"), verdict("second", "pass")]}),
        ),
        Standard((first, second)),
        norms=NORMS,
        builder=RubricBuilder(read={"policy": digest(POLICY)}),
        reviewer=MetaReviewer(),
    )
    signal = await assessor.evaluate({"run": [Exchange("Quote.", execution("one", "All costs included."))]})
    assert signal.satisfied is None
    assert any(item.id == "assessor:review" and item.strength == "must_hold" for item in signal.items)
    assert assessor.open_issues["first:rubric"]


@pytest.mark.asyncio
async def test_pending_permissions_expire_when_the_rubric_changes():
    builder = RubricBuilder(max_calls=1)
    baseline = await builder.revise(
        Provider(response("submit_revision", {"changes": [addition(POLICY, refine="Check cost components.")]})),
        NORMS,
        Standard(),
        {},
    )
    restored = RubricBuilder()
    restored.restore(builder.record())
    protected = baseline.confirmed([baseline.criteria[0].id])
    provider = Provider()
    assert await restored.revise(provider, NORMS, protected, {}) == protected
    assert not provider.requests and not restored.pending
    assert restored.runs[-1]["status"] == "invalidated" and not restored.unresolved
    assert restored.runs[-1]["pending"][0]["target"] == "derived-1"


@pytest.mark.asyncio
async def test_unrelated_regression_conditions_do_not_discard_a_pending_branch():
    builder = RubricBuilder(max_calls=1)
    first = await builder.revise(
        Provider(response("submit_revision", {"changes": [addition(POLICY, refine="Check tax coverage.")]})),
        NORMS,
        Standard(),
        {},
    )
    expanded = Standard((*first.criteria, replace(rule("history"), origin="sedimented")))
    result = await builder.revise(
        Provider(response("submit_revision", {"changes": [addition("Include tax.", "derived-1", reason="uncovered")]})),
        NORMS,
        expanded,
        {},
    )
    assert result.criteria[-1].parent_id == "derived-1" and not builder.pending
    assert result.criteria[1] is expanded.criteria[1]


@pytest.mark.asyncio
async def test_interrupted_construction_rolls_back_unpublished_work_and_can_resume(tmp_path):
    class Interrupted(Provider):
        async def chat_with_retry(self, **kwargs):
            self.requests.append(kwargs)
            if len(self.requests) == 1:
                return response("submit_revision", {"changes": [addition(POLICY, refine="Check tax coverage.")]})
            raise asyncio.CancelledError()

    assessor = Assessor(Interrupted(), norms=NORMS, builder=RubricBuilder(), keep=tmp_path / "standard.json")
    sessions = {"run": [Exchange("Quote.", execution("one", "All costs included."))]}
    with pytest.raises(asyncio.CancelledError):
        await assessor.evaluate(sessions)
    assert not assessor.standard.criteria and not assessor.builder.read and not assessor.builder.pending
    assert assessor.builder.runs[-1]["status"] == "interrupted"
    assert assessor.builder.runs[-1]["discarded"][0]["changes"]
    resumed = Assessor(
        Provider(
            response("submit_revision", {"changes": [addition(POLICY)]}),
            response("submit_verdicts", {"verdicts": [verdict("derived-1", "pass")]}),
        ),
        norms=NORMS,
        builder=RubricBuilder(),
        keep=assessor.keep,
    )
    resumed.restore()
    assert (await resumed.evaluate(sessions)).satisfied is True


@pytest.mark.asyncio
async def test_gate_refinement_precedes_quality_and_optional_pending_work_does_not_block_acceptance():
    optional = addition("Explain the quote clearly.", refine="Inspect optional presentation details.")
    optional["criterion"]["kind"] = "quality"
    builder = RubricBuilder(max_calls=2)
    provider = Provider(
        response("submit_revision", {"changes": [optional, addition(POLICY, refine="Check mandatory costs.")]}),
        response("submit_revision", {"changes": [], "note": "The mandatory condition can already be judged."}),
        response("submit_verdicts", {"verdicts": [verdict("derived-1", "pass"), verdict("derived-2", "pass")]}),
    )
    assessor = Assessor(provider, norms=NORMS, builder=builder)
    signal = await assessor.evaluate({"run": [Exchange("Quote.", execution("one", "All fees included."))]})
    second = json.loads(provider.requests[1]["messages"][1]["content"])
    assert second["target"] == "derived-2"
    assert builder.pending[0]["target"] == "derived-1"
    assert signal.satisfied is True
    assert signal.items[0].result == "unknown" and signal.items[0].strength == "should"


@pytest.mark.asyncio
async def test_an_unresolved_diagnosis_survives_restore_and_an_empty_later_review(tmp_path):
    provider = Provider(
        response("submit_verdicts", {"verdicts": [verdict("a", "pass")]}),
        response(
            "submit_evaluation_review",
            {
                "issues": [
                    {
                        "criterion": "a",
                        "target": "rubric",
                        "evidence": "A required charge is not covered.",
                        "correction": "Verify the missing requirement before acceptance.",
                    }
                ]
            },
        ),
    )
    assessor = Assessor(
        provider, Standard((rule("a"),)), norms=NORMS, reviewer=MetaReviewer(), keep=tmp_path / "standard.json"
    )
    sessions = {"run": [Exchange("Quote.", execution("one", "Subtotal only."))]}
    assert (await assessor.evaluate(sessions)).satisfied is None
    resumed = Assessor(
        Provider(
            response("submit_verdicts", {"verdicts": [verdict("a", "pass")]}),
            response("submit_evaluation_review", {}),
        ),
        sources=("declared",),
        norms=NORMS,
        reviewer=MetaReviewer(),
        keep=assessor.keep,
    )
    resumed.restore()
    assert (await resumed.evaluate(sessions)).satisfied is None
    assert resumed.open_issues["a:rubric"]["allow"] == []


@pytest.mark.asyncio
async def test_external_updates_during_construction_cannot_be_overwritten():
    class ConcurrentProvider(Provider):
        async def chat_with_retry(self, **kwargs):
            assessor.constrain([ExternalRequirement(source="human", quote="Never omit applicable tax.", kind="gate")])
            return response("submit_revision", {"changes": [addition(POLICY)]})

    assessor = Assessor(ConcurrentProvider(), norms=NORMS, builder=RubricBuilder())
    with pytest.raises(ValueError, match="stale candidate"):
        await assessor.evaluate({"run": [Exchange("Quote.", execution("one", "Subtotal only."))]})
    assert len(assessor.standard.criteria) == 1 and assessor.standard.criteria[0].authority == "external"


def test_sedimentation_retains_explicit_external_parents_and_their_children():
    parent = replace(rule("external"), authority="external", origin="sedimented")
    child = rule("detail", parent.id)
    assert Standard((parent, child)).sedimented(()).criteria == (parent, child)


@pytest.mark.asyncio
async def test_restored_evidence_closes_a_factual_gap_without_rewriting_the_criterion(tmp_path):
    path = tmp_path / "quote.txt"
    criterion = replace(
        rule("quote"),
        assessment=AssessmentPlan(evidence_requirements=(EvidenceRequirement("delivered_text", "quote.txt"),)),
    )
    sessions = {"quote": [Exchange("Quote.", execution("one", "Attached.", [str(path)]))]}
    assessor = Assessor(
        Provider(
            response("submit_verdicts", {"verdicts": [verdict("quote", "pass")]}),
            response(
                "submit_evaluation_review",
                {
                    "issues": [
                        {
                            "criterion": "quote",
                            "target": "evidence",
                            "evidence": "The required quote file cannot be read.",
                            "correction": "Read the retained quote before deciding.",
                        }
                    ]
                },
            ),
        ),
        Standard((criterion,)),
        norms=NORMS,
        reviewer=MetaReviewer(),
        keep=tmp_path / "standard.json",
    )
    assert (await assessor.evaluate(sessions)).satisfied is None
    path.write_text("All mandatory fees and tax are included, within the supplied budget.")
    resumed = Assessor(
        Provider(
            response("submit_verdicts", {"verdicts": [verdict("quote", "pass")]}),
            response("submit_evaluation_review", {}),
        ),
        sources=("declared",),
        norms=NORMS,
        reviewer=MetaReviewer(),
        keep=assessor.keep,
    )
    resumed.restore()
    assert (await resumed.evaluate(sessions)).satisfied is True
    assert resumed.standard.criteria == (criterion,) and not resumed.open_issues
    assert resumed.assessments[0]["evidence_gaps"]["quote"]
    assert resumed.assessments[-1]["evidence_restored"] == ["quote"]


@pytest.mark.asyncio
async def test_exact_duplicate_removal_preserves_the_obligation_and_its_history():
    first, duplicate = rule("first"), rule("duplicate")
    provider = Provider(
        response("submit_verdicts", {"verdicts": [verdict("first", "pass"), verdict("duplicate", "pass")]}),
        response(
            "submit_evaluation_review",
            {
                "issues": [
                    {
                        "criterion": "duplicate",
                        "target": "rubric",
                        "evidence": "The complete definition and measurement plan duplicate first.",
                        "correction": "Keep the first condition once.",
                        "allow": [{"op": "remove", "id": "duplicate"}],
                    }
                ]
            },
        ),
        response(
            "submit_revision",
            {
                "changes": [
                    {
                        "op": "remove",
                        "id": "duplicate",
                        "reason": "duplicate",
                        "explanation": "The identical first condition remains enforced.",
                    }
                ]
            },
        ),
        response("submit_verdicts", {"verdicts": [verdict("first", "pass")]}),
    )
    assessor = Assessor(
        provider,
        Standard((first, duplicate)),
        norms=NORMS,
        builder=RubricBuilder(read={"policy": digest(POLICY)}),
        reviewer=MetaReviewer(),
    )
    signal = await assessor.evaluate({"run": [Exchange("Quote.", execution("one", "All required costs included."))]})
    assert signal.satisfied is True and assessor.standard.criteria == (first,)
    assert not assessor.open_issues
    receipt = assessor.assessments[-1]["repair_validation"]["duplicate"]
    assert receipt["kind"] == "equivalent_duplicate_removal" and receipt["witness"] == "first"
    assert assessor.builder.versions[0]["changes"][0]["before"]["id"] == "duplicate"


@pytest.mark.asyncio
async def test_a_parent_counterexample_repositions_budget_without_weakening_the_budget_requirement():
    cost = replace(rule("cost"), definition=Definition("Quote", "Include every mandatory fee and tax."))
    budget = replace(rule("budget", "cost"), definition=Definition("Quote", "Stay within the supplied budget."))

    class PlacementProvider(Provider):
        async def chat_with_retry(self, **kwargs):
            self.requests.append(kwargs)
            data = json.loads(kwargs["messages"][1]["content"])
            names = {entry["function"]["name"] for entry in kwargs["tools"]}
            if "submit_verdicts" in names:
                output = data["conversations"]["run"][0]["assistant"]
                return response(
                    "submit_verdicts",
                    {
                        "verdicts": [
                            verdict(c["id"], "pass" if f"{c['criterion']}_ok" in output else "fail")
                            for c in data["criteria"]
                        ]
                    },
                )
            if "submit_evaluation_review" in names:
                return response(
                    "submit_evaluation_review",
                    {
                        "issues": [
                            {
                                "criterion": "budget",
                                "target": "rubric",
                                "evidence": "A complete cost list can exceed the budget, so cost satisfaction does not imply this condition.",
                                "correction": "Keep budget as an independent task obligation.",
                                "allow": [{"op": "rewrite", "id": "budget", "fields": ["parent_id"]}],
                            }
                        ]
                    },
                )
            changed = {
                key: value
                for key, value in asdict(budget).items()
                if key in {"definition", "basis", "kind", "assessment", "parent_id"}
            }
            changed["basis"]["references"] = [{"source": "policy", "quote": POLICY}]
            changed["parent_id"] = None
            return response(
                "submit_revision",
                {
                    "changes": [
                        {
                            "op": "rewrite",
                            "id": "budget",
                            "reason": "review",
                            "explanation": "The obligations are independent; preserve both meanings.",
                            "criterion": changed,
                        }
                    ]
                },
            )

    cases = []
    for id, output, result in (
        ("complete_over_budget", "cost_ok budget_bad", "pass"),
        ("incomplete_within_budget", "cost_bad budget_ok", "fail"),
    ):

        async def oracle(evidence, result=result):
            return Finding(result, "Independent verification of cost coverage only.")

        cases.append(ReplayCase(id, "", NORMS, {"run": [Exchange("Quote.", execution(id, output))]}, oracle))
    assessor = Assessor(
        PlacementProvider(),
        Standard((cost, budget)),
        norms=NORMS,
        builder=RubricBuilder(read={"policy": digest(POLICY)}),
        reviewer=MetaReviewer(),
        repair_suites={"budget": RepairSuite("cost", tuple(cases))},
    )
    signal = await assessor.evaluate(cases[0].sessions)
    assert signal.satisfied is False
    assert assessor.standard.criteria == (cost, replace(budget, parent_id=None))
    assert assessor.assessments[-1]["repair_validation"]["budget"]["accepted"]
    assert not assessor.open_issues
