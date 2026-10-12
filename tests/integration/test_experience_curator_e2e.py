"""Compare experience arms on isolated native Workers using actual provider settings as the oracle."""

import json
import os
from copy import deepcopy

import pytest

from experimental.harness.contract import Task
from experimental.harness.curator.attribution import AttributionLimits, ModelAttributor
from experimental.harness.curator.generation.run import Limits
from experimental.harness.curator.workflow import improve
from experimental.harness.experience.admission import AdmissionPolicy
from experimental.harness.experience.build import ExperiencePipeline
from experimental.harness.experience.contracts import (
    EvidenceLink,
    ExperienceCondition,
    ExperienceProposal,
    ExperienceReview,
    OutcomeReceipt,
    digest,
)
from experimental.harness.experience.curator import CuratorExperience
from experimental.harness.experience.records import RecordAccess
from experimental.harness.experience.store import ExperienceStore
from experimental.harness.experience.verification import Case, Result, compare_methods
from experimental.harness.raven_adapter.inspection import Baseline
from experimental.harness.raven_adapter.worker import Worker
from tests.fixtures.harness_curator.authoring import action, profile
from tests.integration.test_harness_curator_e2e import (  # noqa: F401 -- isolated baseline fixture
    baseline,
    plan_for,
    replay_provider,
)
from tests.test_harness_curator_generation import diagnosis, response, selection

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
LESSON = "Use the Action generation policy to set provider sampling parameters, then inspect the actual provider request. A prompt alone does not set temperature."


class LessonBuilder:
    def identity(self):
        return {"implementation": "controlled-mechanism-lesson"}

    async def build(self, request, **kwargs):
        return (
            ExperienceProposal(
                condition=ExperienceCondition(situation="Configure the provider temperature.", phase="diagnose"),
                guidance=LESSON,
                support_kind="behavior",
                evidence=tuple(EvidenceLink(reference=row.reference, relation="supports") for row in request.events),
            ),
        )


class LessonCritic:
    def identity(self):
        return {"implementation": "controlled-content-review"}

    async def review(self, proposals, request, **kwargs):
        return tuple(ExperienceReview(proposal_index=index, decision="accept") for index in range(len(proposals)))


class Planner:
    def __init__(self, temperature, *, force=False, real=None):
        self.temperature, self.force, self.real = temperature, force, real
        self.requests = []

    def get_default_model(self):
        return self.real.get_default_model() if self.real is not None else "controlled-curator"

    async def chat_with_retry(self, **kwargs):
        self.requests.append(deepcopy(kwargs))
        if self.real is not None:
            return await self.real.chat_with_retry(**kwargs)
        names = {tool["function"]["name"] for tool in kwargs["tools"]}
        if "submit_diagnosis" in names:
            return response("submit_diagnosis", diagnosis())
        data = json.loads(kwargs["messages"][3]["content"])
        if "selection" not in data:
            return response("submit_selection", selection("action.strategy"))
        if "plan" not in data:
            plan = plan_for("action.strategy").model_copy(
                update={"understanding": f"Set provider temperature to {self.temperature}."}
            )
            return response("submit_plan", plan.model_dump(mode="json"))
        if "plan" in data:
            informed = self.force or any(
                LESSON in str(row.get("content", "")) for request in self.requests for row in request["messages"]
            )
            artifact = (
                action(generation={"temperature": self.temperature})
                if informed
                else profile({"TOOLS.md": f"Use temperature {self.temperature}."})
            )
            return response("submit_artifact", artifact.model_dump(mode="json"))
        raise AssertionError(f"Unexpected Curator request: {names}")


def isolated(baseline, directory, label, temperature):
    config = deepcopy(baseline.config)
    config.agents.defaults.workspace = str(directory / "home")
    config.agents.defaults.temperature = 0.7
    config.agents.defaults.max_tool_iterations = 2
    work = directory / "work"
    work.mkdir(parents=True)
    return Baseline(
        config,
        deepcopy(baseline.extensions),
        work,
        task=Task(
            id=label,
            text=f"Set the worker's effective provider temperature to {temperature}. Preserve its ability to reply.",
        ),
    )


def temperature(execution):
    requests = [row for row in execution.records if row["kind"] == "provider.request"]
    assert requests, "the oracle requires an actual provider invocation"
    row = requests[-1]
    value = row["parameters"].get("temperature")
    return row["defaults"].get("temperature") if value is None else value


async def run_case(baseline, directory, label, target, *, owner=None, history=None, force=False, real=None):
    directory.mkdir(parents=True)
    base = isolated(baseline, directory, label, target)
    planner = Planner(target, force=force, real=real)
    async with Worker(base, directory / "worker", provider_factory=replay_provider, timeout=45) as worker:
        before = await worker.run("Report readiness.")
        error = None
        try:
            await improve(
                worker,
                planner,
                experience=owner,
                feedback={"text": history} if history else None,
                limits=Limits(
                    max_calls=12, max_queries=8, max_checks=3, max_repairs=2, call_timeout=90, max_output=8000
                ),
                attributor=ModelAttributor(
                    limits=AttributionLimits(max_calls=5, max_queries=5, call_timeout=90, max_output=8000)
                ),
            )
        except Exception as exc:
            error = str(exc)
        after = await worker.run("Report readiness again.")
        measured = temperature(after)
        records = [
            json.loads(path.read_text())
            for path in (worker.root / "curation").glob("*.json")
            if path.name not in {"pending.json", "candidate.json"}
        ]
        report = {
            "target": target,
            "before_temperature": temperature(before),
            "after_temperature": measured,
            "before": before.model_dump() if hasattr(before, "model_dump") else None,
            "execution": after.records,
            "curations": records,
            "requests": planner.requests,
            "error": error,
        }
        path = directory / "comparison.json"
        path.write_text(json.dumps(report, default=str, indent=2))
        result = Result(
            satisfied=measured == target and error is None,
            preserved=not after.errors,
            record=str(path),
            cost={
                "calls": float(len(planner.requests)),
                "input_chars": float(
                    sum(len(str(row["content"])) for req in planner.requests for row in req["messages"])
                ),
            },
        )
        return result, records


async def study(baseline, tmp_path, *, real=None):
    store = ExperienceStore(tmp_path / "memory" / "experience.sqlite")
    builder, critic = LessonBuilder(), LessonCritic()
    access = RecordAccess(
        access_scope="native-study",
        fields=frozenset(
            {
                "plan.understanding",
                "plan.design",
                "change.target",
                "change.reason",
                "change.treatment",
                "outcome.held",
                "outcome.observations",
            }
        ),
    )
    owner = CuratorExperience(
        store,
        AdmissionPolicy(critic_digest=digest(critic.identity())),
        access,
        pipeline=ExperiencePipeline(store, builder, critic),
    )
    try:
        history = []
        for index, value in enumerate((0.2, 0.4)):
            result, records = await run_case(
                baseline, tmp_path / f"source-{index}", f"source-{index}", value, owner=owner, force=True
            )
            assert result.satisfied, result.record
            record = next(row for row in records if row.get("experience_learning", {}).get("event"))
            learned = record["experience_learning"]
            await owner.outcome(
                learned["event"],
                OutcomeReceipt(
                    access_scope=access.access_scope,
                    revision_id=record["active_artifact_id"],
                    held=True,
                    basis="observation",
                    comparability="comparable",
                    observations=(
                        f"Independent native provider request measured temperature {value}; record {result.record}.",
                    ),
                ),
                held_out=False,
            )
            history.append(
                {
                    "task": record["task_id"],
                    "plan": record["generated"]["candidate"]["plan"],
                    "observed_temperature": value,
                }
            )
        assert owner.journal.read().active("curator", access.access_scope)
        version = owner.journal.read().version("curator", access.access_scope)
        count = store.connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        raw = "Historical records for reference only:\n" + json.dumps(history, indent=2)

        async def evaluate(instructions, case):
            arm = "guidance" if instructions == LESSON else "history" if instructions == raw else "none"
            result, _ = await run_case(
                baseline,
                tmp_path / f"{case.id}-{arm}",
                f"{case.id}-{arm}",
                case.inputs["temperature"],
                owner=owner if arm == "guidance" else None,
                history=raw if arm == "history" else None,
                real=real,
            )
            return result

        result = await compare_methods(
            before="",
            after=LESSON,
            history=raw,
            context=digest({"library": version, "baseline": baseline.task.text, "real_model": real is not None}),
            cases=(Case("new-a", "unseen-a", {"temperature": 0.1}), Case("new-b", "unseen-b", {"temperature": 0.6})),
            evaluate=evaluate,
            timeout=600,
        )
        (tmp_path / "study.json").write_text(json.dumps(result.record(), indent=2))
        assert not result.error, result.error
        assert owner.journal.read().version("curator", access.access_scope) == version
        assert store.connection.execute("SELECT COUNT(*) FROM events").fetchone()[0] == count
        return result
    finally:
        owner.close()


async def test_frozen_experience_changes_real_native_execution_on_new_tasks(baseline, tmp_path):
    result = await study(baseline, tmp_path)
    assert result.accepted
    assert all(row.before.satisfied is False and row.after.satisfied is True for row in result.cases)


@pytest.mark.real_llm
@pytest.mark.slow
async def test_real_curator_three_arm_study_records_actual_outcomes_without_assuming_improvement(baseline, tmp_path):
    path = os.environ.get("EXPERIENCE_TEST_CONFIG")
    if not path:
        pytest.skip("Set EXPERIENCE_TEST_CONFIG for the authorized real Curator comparison.")
    from raven.core.config_stack import load_runtime_config
    from raven.providers.factory import make_lazy_provider

    provider = make_lazy_provider(load_runtime_config(path))
    result = await study(baseline, tmp_path, real=provider)
    assert len(result.cases) == 2
    assert all(row.history is not None and row.after.preserved is True for row in result.cases)
