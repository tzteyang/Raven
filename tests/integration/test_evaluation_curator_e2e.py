"""A generated rubric drives real native Harness curation and independently verified output improvement."""

import json
import shutil
from copy import deepcopy

import pytest

from experimental.harness.assessor.builder import RubricBuilder
from experimental.harness.assessor.dataset import Case, Dataset
from experimental.harness.assessor.guidance import GuidanceStore
from experimental.harness.assessor.reviewer import MetaReviewer
from experimental.harness.assessor.standard import Assessor
from experimental.harness.assessor.validation import ReplayCorpus
from experimental.harness.contract import Task
from experimental.harness.loop.session import Session
from experimental.harness.participation.protocols import Exchange, Signal
from experimental.harness.raven_adapter.worker import Worker
from raven.contracts.llm_provider import LLMResponse
from tests.fixtures.harness_curator.authoring import profile
from tests.integration.test_harness_curator_e2e import ReplayProvider, plan_for
from tests.integration.test_harness_curator_e2e import baseline as baseline
from tests.test_assessor_builder import drafted
from tests.test_assessor_standard import Provider, response
from tests.test_harness_curator_generation import diagnosis, packet, selection

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

COMPLETE = "Subtotal: 100; tax: 10; total: 110."


class QuoteProvider(ReplayProvider):
    async def chat(self, messages, **kwargs):
        fixed = any("QUOTE_WITH_TAX" in str(row.get("content", "")) for row in messages if row["role"] == "system")
        return LLMResponse(content=COMPLETE if fixed else "Subtotal: 100.")


def quote_provider(config):
    return QuoteProvider([])


class Roles(Provider):
    def __init__(self):
        super().__init__()
        self.curations = 0
        self.subjects = ("task",)

    async def chat_with_retry(self, messages=None, tools=None, model=None, **kwargs):
        kwargs = {**kwargs, "messages": messages, "tools": tools, "model": model}
        self.requests.append(deepcopy(kwargs))
        names = {tool["function"]["name"] for tool in kwargs["tools"]}
        data = json.loads(kwargs["messages"][1]["content"])
        if "submit_revision" in names:
            changes = (
                []
                if data["criteria"]
                else [
                    {
                        "op": "add",
                        "reason": "new_norm",
                        "explanation": "The task requires a complete payable quote.",
                        "refine": "Separate tax coverage from the payable total.",
                        "criterion": drafted(
                            "Include the tax and payable total.", material="$task", quote="", kind="gate"
                        ),
                    }
                ]
            )
            if data["target"] == "derived-1":
                changes = [
                    {
                        "op": "add",
                        "reason": "uncovered",
                        "explanation": "A necessary part of the payable quote.",
                        "criterion": drafted(text, material="$task", quote="", kind="gate", parent_id="derived-1"),
                    }
                    for text in ("Include the applicable tax.", "State the final payable total.")
                ]
            return response("submit_revision", {"changes": changes})
        if "submit_verdicts" in names:
            passed = all("tax: 10" in row["assistant"] for rows in data["conversations"].values() for row in rows)
            return response(
                "submit_verdicts",
                {
                    "verdicts": [
                        {
                            "id": criterion["id"],
                            "result": "pass" if passed else "fail",
                            "note": "" if passed else "Mandatory charge absent.",
                        }
                        for criterion in data["criteria"]
                    ]
                },
            )
        if "submit_evaluation_review" in names:
            return response("submit_evaluation_review", {})
        if "submit_feedback" in names:
            if any(signal["source"] == "human" for signal in data["signals"]):
                return response(
                    "submit_feedback",
                    {
                        "decision": "continue",
                        "reason": "Retain the explicit requirement; the current quote meets it.",
                        "external_requirements": [
                            {"source": "human", "quote": "Every quote must include tax.", "kind": "gate"}
                        ],
                    },
                )
            turn = next(iter(data["sessions"].values()))[0]["turn_id"]
            return response(
                "submit_feedback",
                {
                    "decision": "curate",
                    "reason": "The payable amount omits a mandatory charge.",
                    "requirements": [
                        {
                            "situation": "When providing a payable quote.",
                            "behavior": "Include tax in the payable quote.",
                            "observed": f"Turn {turn} supplied only the subtotal.",
                            "evidence": [turn],
                            "expectation": "new",
                            "acceptance": "The response states the tax and final payable amount.",
                            "strength": "must_hold",
                            "grounds": ["check:derived-2"],
                        }
                    ],
                },
            )
        data = packet(kwargs)
        names = set(data["submission_schemas"]) or names
        if "submit_diagnosis" in names:
            self.subjects = tuple(data["required_diagnoses"])
            return response("submit_diagnosis", diagnosis(*self.subjects))
        if "submit_selection" in names:
            return response("submit_selection", selection("memory.strategy", grounds=self.subjects))
        if "submit_plan" in names:
            return response("submit_plan", plan_for("memory.strategy").model_dump(mode="json"))
        if "submit_artifact" in names:
            content = "QUOTE_WITH_TAX: include the tax and payable total." if self.curations else "Prepare a quote."
            self.curations += 1
            return response("submit_artifact", profile({"TOOLS.md": content}).model_dump(mode="json"))
        raise AssertionError(f"Unexpected role request: {sorted(names)}")


class QuoteTrial:
    def __init__(self, text="Please calculate this quote."):
        self.text = text

    async def run(self, worker):
        return {"quote": [Exchange(self.text, await worker.run(self.text, session_key="quote"))]}


class IsolatedDataset:
    def __init__(self, dataset, root):
        self.dataset, self.root = dataset, root

    async def run(self, worker):
        from experimental.cultivation.employee import Replica, same_revision

        baseline = deepcopy(worker.baseline)
        home, work = self.root / "home", self.root / "work"
        shutil.copytree(baseline.config.workspace_path, home, ignore=shutil.ignore_patterns("sessions"))
        shutil.copytree(baseline.workdir, work)
        baseline.config.agents.defaults.workspace, baseline.workdir = str(home), work
        replica = Replica(
            worker.revision_id, baseline, self.root / "runtime", provider_factory=quote_provider, timeout=30
        )
        replica.artifact, replica.last_plan = worker.artifact, worker.last_plan
        same_revision(worker, replica)
        async with replica:
            return await self.dataset.run(replica)


async def test_model_rubric_improves_native_output_and_keeps_later_external_requirements(baseline, tmp_path):
    baseline.task = Task(id="tax-quote", text="Prepare a quote with the applicable tax and payable total.")
    roles = Roles()
    memory = tmp_path / "evaluation-memory"
    assessor = Assessor(
        roles,
        task=baseline.task.text,
        builder=RubricBuilder(),
        reviewer=MetaReviewer(),
        guidance_store=GuidanceStore(memory / "guidance.json"),
        replay_corpus=ReplayCorpus(memory / "replays.json"),
        keep=tmp_path / "standard.json",
    )
    async with Worker(baseline, tmp_path / "worker", provider_factory=quote_provider, timeout=30) as worker:
        session = Session.open(worker, roles, assessors=(assessor,))
        assert await session.onboard()
        first = (await session.trial(QuoteTrial()))["quote"][0]
        assert first.assistant == "Subtotal: 100."
        assert (await session.assess(assessor))[0].satisfied is False
        assert [(c.id, c.parent_id) for c in assessor.standard.criteria] == [
            ("derived-1", None),
            ("derived-2", "derived-1"),
            ("derived-3", "derived-1"),
        ]
        assert assessor.builder.runs[-1]["calls"] == 2
        assert (await session.analyse()).next == "curate"
        assert session.review.feedback.requirements[0].authority == "model"
        assert await session.curate()
        second = (await session.trial(QuoteTrial("Calculate a new payable quote.")))["quote"][0]
        assert second.assistant == COMPLETE and second.execution.artifact_id != first.execution.artifact_id
        assert any(
            "QUOTE_WITH_TAX" in str(row) for row in second.execution.records if row["kind"] == "provider.request"
        )
        assert (await session.assess(assessor))[0].satisfied is True
        verifier = Dataset([Case("held", "Prepare the independently reserved order.", COMPLETE)])
        await session.holdout([IsolatedDataset(verifier, tmp_path / "held")], [verifier])
        await session.analyse()
        assert session.record["promotion"]["status"] == "accepted"
        assert assessor.replay_corpus.cases()
        assert roles.curations == 2
        curator_calls = [call for call in roles.requests if "submit_selection" in str(call["tools"])]
        assert all(id not in json.dumps(curator_calls) for id in ("derived-1", "derived-2", "derived-3"))
        assert "independently reserved" not in json.dumps(curator_calls)

        await session.trial(QuoteTrial("Provide another quote."))
        await session.assess(assessor)
        session.signal(Signal("human", "Every quote must include tax.", authority="external"))
        await session.analyse()
        requirement = session.external_requirements[0]
        criterion = next(rule for rule in assessor.standard.criteria if rule.id == requirement.id)
        assert criterion.authority == "external" and criterion.strength == "must_hold"
        assessor.restore()
        assert criterion in assessor.standard.criteria
        assert len(list((worker.root / "curation").glob("*.json"))) == 2
