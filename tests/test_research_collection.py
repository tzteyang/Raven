"""Information collection runs fixed stages, keeps evidence and open points, and hands only reviewed results on."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from experimental.research.collection import (
    ASSESS,
    PLAN,
    REVIEW,
    SOURCE_CHARS,
    SUBMIT,
    CollectionLimits,
    collect_information,
)
from experimental.research.curator import INFORMATION_FILE, handover_information
from experimental.research.information import (
    DIMENSIONS,
    Description,
    Evidence,
    Question,
    Request,
    ResearchGuide,
    ResearchReview,
    Result,
    Review,
    Snapshot,
    render,
)
from raven.agent.tools.filesystem import ReadFileTool
from raven.agent.tools.registry import ToolRegistry
from raven.contracts.llm_provider import RunMeta, TruncationInfo
from tests.research_helpers import Provider, rejections, research_brief, response


def description(*, evidence=("evidence-1",), text="Use the stated professional scope.", unresolved=()):
    return {
        "title": "Project evidence expert",
        "sections": [
            {
                "dimension": dimension,
                "text": text,
                "coverage": "sufficient",
                "reason": "The cited input establishes it.",
                "evidence": evidence,
            }
            for dimension in DIMENSIONS
        ],
        "resources": [],
        "unresolved": list(unresolved),
    }


def accepted():
    return {"accepted": True, "reason": "The description is supported within its stated limits.", "issues": []}


def snapshot():
    return Snapshot(
        description=Description.model_validate(description()),
        evidence=(
            Evidence(
                id="evidence-1", channel="user", origin="initial request", content="Use the stated professional scope."
            ),
        ),
    )


def assessment(
    *, evidence=("evidence-1",), questions=(), research_needs=(), coverage="sufficient", dimensions=DIMENSIONS
):
    return {
        "reading": "The material describes a project evidence expert and leaves its approval path open.",
        "coverage": [
            {"dimension": dimension, "coverage": coverage, "reason": "The input states it.", "evidence": list(evidence)}
            for dimension in dimensions
        ],
        "questions": list(questions),
        "research_needs": list(research_needs),
    }


def question(dimension="methods", text="Who approves exceptions?", **extra):
    return {"dimension": dimension, "question": text, "reason": "The material does not say.", **extra}


def need(text="How should uncertainty be recorded?", dimensions=("knowledge", "methods")):
    return {"question": text, "dimensions": list(dimensions), "why": "No public method is supplied."}


def group(text="How should uncertainty be recorded?", **overrides):
    return {"dimensions": ["knowledge", "methods"], "serves": ["need-1"], "brief": research_brief(text), **overrides}


def plan(*groups, deferred=()):
    return {"rationale": "One group per open method question.", "groups": list(groups), "deferred": list(deferred)}


def finding(number=1, text="Record uncertainty next to each claim."):
    return {
        "id": f"researched-{number}",
        "text": text,
        "kind": "norm",
        "question": "How should uncertainty be recorded?",
        "sources": ["https://example.org/method"],
        "evidence": "record uncertainty next to each claim",
        "situation": "",
        "conflicts": [],
        "unmatched_sources": [],
    }


def delivery(
    *, findings=1, withheld=(), synthesis="Uncertainty is recorded next to each claim.", needs_new_sources=False
):
    admitted = [finding(number) for number in range(1, findings + 1)]
    verdicts = [{"id": row["id"], "admit": True} for row in admitted]
    verdicts += [{"id": id, "admit": False, "reason": reason} for id, reason in withheld]
    held = bool(withheld) or not synthesis
    review = ResearchReview(
        reason="Checked against the retrieved pages.",
        findings=verdicts,
        synthesis_admitted=bool(synthesis),
        issues=("Repair the withheld parts.",) if held else (),
        needs_new_sources=needs_new_sources if held else False,
    )
    return {
        "findings": admitted,
        "withheld": [{"id": id, "question": "How?", "text": "Unsupported.", "reasons": [why]} for id, why in withheld],
        "unanswered": [],
        "synthesis": synthesis,
        "disagreements": [],
        "review": review.record(),
        "leads": [],
        "refused": [],
        "status": "accepted" if review.accepted else ("partial" if admitted else "rejected"),
    }


def guide():
    return ResearchGuide(
        topic="Evidence handling",
        dimensions=("knowledge", "methods"),
        questions=("What information is needed before deciding?",),
        rationale="A product case suggests investigating missing evidence.",
        sources=("guide-only-source",),
    )


def labels(trace_path):
    return [row["label"] for row in json.loads(trace_path.read_text()) if row.get("event") == "model.call"]


def test_the_contract_distinguishes_missing_content_from_sufficient_content():
    data = description()
    data["sections"][2].update(text="", evidence=(), coverage="missing", reason="No domain knowledge is supplied.")
    assert Description.model_validate(data).sections[2].coverage == "missing"
    data["sections"][2]["coverage"] = "sufficient"
    with pytest.raises(ValidationError, match="content and evidence"):
        Description.model_validate(data)
    with pytest.raises(ValidationError, match="each dimension exactly once"):
        Description.model_validate({**description(), "sections": description()["sections"][:-1]})
    with pytest.raises(ValidationError, match="initial collection"):
        Request(objective="Research pricing only", focus=("knowledge",))


def test_only_user_questions_can_block_and_only_they_hold_the_result():
    with pytest.raises(ValidationError, match="only a user question can block"):
        Question(
            id="q", dimension="methods", question="Which method?", reason="Unknown.", channel="research", blocking=True
        )
    base = snapshot()
    open_point = Question(id="q", dimension="methods", question="Which method?", reason="Unknown.", assumption="Any.")
    proposal = base.model_copy(
        update={"description": base.description.model_copy(update={"unresolved": (open_point,)})}
    )
    assert Result(snapshot=proposal, review=Review.model_validate(accepted())).status == "ready"
    assert "Until settled: Any." in render(proposal)
    waiting = open_point.model_copy(update={"blocking": True})
    proposal = base.model_copy(update={"description": base.description.model_copy(update={"unresolved": (waiting,)})})
    result = Result(snapshot=proposal, review=Review.model_validate(accepted()))
    assert result.status == "needs_input" and not result.ready


@pytest.mark.asyncio
async def test_unconfigured_channels_have_no_stage_and_open_points_carry_assumptions(tmp_path):
    open_point = {
        "id": "scope",
        "dimension": "role",
        "question": "Which projects are in scope?",
        "reason": "The material names none.",
        "channel": "user",
    }
    provider = Provider(
        response(ASSESS, assessment(questions=[question()])),
        response(ASSESS, assessment(research_needs=[need()])),
        response(ASSESS, assessment()),
        response(SUBMIT, description(unresolved=[open_point])),
        response(SUBMIT, description(unresolved=[{**open_point, "assumption": "All projects of the team."}])),
        response(REVIEW, accepted()),
    )
    result = await collect_information(provider, Request(objective="Describe the expert."), records=tmp_path / "run")
    assert result.ready and result.status == "ready"
    assert result.snapshot.description.unresolved[0].assumption == "All projects of the team."
    assert not result.snapshot.description.unresolved[0].blocking
    assert any("no user channel" in error for error in rejections(provider.requests[2]))
    assert any("no research channel" in error for error in rejections(provider.requests[2]))
    assert any("needs the assumption" in error for error in rejections(provider.requests[4]))
    assert labels(tmp_path / "run/trace.json") == ["assess"] * 3 + ["compose"] * 2 + ["information.review"]
    assert json.loads((tmp_path / "run/assessment.json").read_text())["questions"] == []
    assert json.loads((tmp_path / "run/status.json").read_text())["status"] == "ready"
    assert not (tmp_path / "run/questions.json").exists() and not (tmp_path / "run/plan-1.json").exists()
    packet = json.loads(provider.requests[0]["messages"][1]["content"])
    assert packet["channels"] == {"native": False, "research": False, "user": False}


@pytest.mark.asyncio
@pytest.mark.parametrize("wait", [False, True])
async def test_user_questions_are_asked_once_and_unanswered_ones_become_open_points(tmp_path, wait):
    asked = []

    async def ask(item):
        asked.append(item)
        return "The team lead approves exceptions." if item.dimension == "methods" else None

    def compose(request):
        pending = json.loads(request["messages"][1]["content"])["open_user_questions"]
        assert len(pending) == 1 and pending[0]["dimension"] == "cases"
        garbled = {**pending[0], "question": "Reworded by the model", "assumption": "Treat worked examples as cases."}
        return response(SUBMIT, description(evidence=("evidence-3",), unresolved=[garbled]))

    provider = Provider(
        response(ASSESS, assessment(questions=[question(), question("cases", "Are there documented incidents?")])),
        response(SUBMIT, description(evidence=("evidence-3",))),
        compose,
        response(REVIEW, accepted()),
    )
    result = await collect_information(
        provider, Request(objective="Describe the expert."), ask=ask, wait_for_input=wait, records=tmp_path / "run"
    )
    assert [item.question for item in asked] == ["Who approves exceptions?", "Are there documented incidents?"]
    assert result.snapshot.evidence[2].channel == "user" and "team lead" in result.snapshot.evidence[2].content
    assert any("carry every open user question" in error for error in rejections(provider.requests[2]))
    point = result.snapshot.description.unresolved[0]
    assert point.question == "Are there documented incidents?" and point.assumption == "Treat worked examples as cases."
    assert point.blocking is wait and result.status == ("needs_input" if wait else "ready")
    rows = json.loads((tmp_path / "run/questions.json").read_text())
    assert [row["answered"] for row in rows] == [True, False]
    assert labels(tmp_path / "run/trace.json") == ["assess", "compose", "compose", "information.review"]


@pytest.mark.asyncio
async def test_questions_taken_together_wait_at_once_while_the_research_runs(tmp_path):
    researching = asyncio.Event()

    class Page:
        together = True

        def __init__(self):
            self.waiting, self.all = [], asyncio.Event()

        async def __call__(self, item):
            self.waiting.append(item.question)
            if len(self.waiting) == 2:
                self.all.set()
            await asyncio.wait_for(self.all.wait(), 5)
            await asyncio.wait_for(researching.wait(), 5)
            return "The team lead approves exceptions." if item.dimension == "methods" else None

    async def research(task):
        researching.set()
        await asyncio.wait_for(page.all.wait(), 5)
        return delivery()

    def compose(request):
        [pending] = json.loads(request["messages"][1]["content"])["open_user_questions"]
        carried = {**pending, "assumption": "Treat worked examples as cases."}
        return response(SUBMIT, description(evidence=("evidence-3",), unresolved=[carried]))

    page = Page()
    provider = Provider(
        response(
            ASSESS,
            assessment(
                questions=[question(), question("cases", "Are there documented incidents?")], research_needs=[need()]
            ),
        ),
        response(PLAN, plan(group())),
        compose,
        response(REVIEW, accepted()),
    )
    result = await collect_information(
        provider, Request(objective="Describe the expert."), ask=page, research=research, records=tmp_path / "run"
    )
    assert result.ready and page.waiting == ["Who approves exceptions?", "Are there documented incidents?"]
    assert {source.channel for source in result.snapshot.evidence} >= {"user", "research"}
    rows = json.loads((tmp_path / "run/questions.json").read_text())
    assert [row["answered"] for row in rows] == [True, False]


@pytest.mark.asyncio
@pytest.mark.parametrize("stop", ["time_limit", "cancelled"])
async def test_partial_answers_and_waiting_questions_survive_interruption(tmp_path, stop):
    answered = asyncio.Event()
    answer = "The team lead approves exceptions."

    class Page:
        together = True

        async def __call__(self, item):
            if item.dimension == "methods":
                answered.set()
                return answer
            await asyncio.Event().wait()

    provider = Provider(
        response(ASSESS, assessment(questions=[question("cases", "Are there documented incidents?"), question()]))
    )
    task = asyncio.create_task(
        collect_information(
            provider,
            Request(objective="Describe the expert."),
            ask=Page(),
            wait_for_input=True,
            limits=CollectionLimits(total_timeout=0.1 if stop == "time_limit" else 30),
            records=tmp_path / "run",
        )
    )
    await asyncio.wait_for(answered.wait(), 5)
    rows = json.loads((tmp_path / "run/questions.json").read_text())
    assert [row["dimension"] for row in rows] == ["cases", "methods"]
    assert [row["answered"] for row in rows] == [False, True]
    evidence = json.loads((tmp_path / "run/evidence.json").read_text())
    assert next(item["content"] for item in evidence if item["id"] == rows[1]["evidence"]) == answer
    if stop == "cancelled":
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        result = Result.model_validate_json((tmp_path / "run/result.json").read_text())
    else:
        result = await task
    assert result.stop_reason == stop and not result.ready
    assert [item.content for item in result.snapshot.evidence if item.channel == "user"] == [answer]
    assert [item.id for item in result.snapshot.description.unresolved] == [rows[0]["id"]]
    assert result.snapshot.description.unresolved[0].blocking
    assert json.loads((tmp_path / "run/questions.json").read_text()) == rows


@pytest.mark.asyncio
async def test_research_groups_run_concurrently_and_findings_become_evidence_one_by_one(tmp_path):
    timeline = []

    async def research(task):
        timeline.append(("start", task.attempt, task.remaining_seconds))
        await asyncio.sleep(0.05)
        timeline.append(("end", task.attempt))
        return delivery(findings=2)

    provider = Provider(
        response(ASSESS, assessment(research_needs=[need(), need("Which review cadence applies?", ("performance",))])),
        response(PLAN, plan(group(), group("Which review cadence applies?", serves=["need-2"]), group("Third?"))),
        response(
            PLAN,
            plan(
                group(),
                group("Which review cadence applies?", serves=["need-2"], dimensions=["performance"]),
                deferred=["Third"],
            ),
        ),
        response(SUBMIT, description(evidence=("evidence-3", "evidence-7"))),
        response(REVIEW, accepted()),
    )
    limits = CollectionLimits(research_tasks=2)
    result = await collect_information(
        provider, Request(objective="Describe the expert."), research=research, limits=limits, records=tmp_path / "run"
    )
    assert result.ready
    assert [row[0] for row in timeline] == ["start", "start", "end", "end"]
    assert {row[1] for row in timeline} == {"research-1", "research-2"}
    assert all(row[2] <= limits.research_window for row in timeline if row[0] == "start")
    assert any("at most 2 research groups" in error for error in rejections(provider.requests[2]))
    research_evidence = [source for source in result.snapshot.evidence if source.channel == "research"]
    assert len(research_evidence) == 6
    assert [json.loads(source.origin).get("finding") for source in research_evidence[:2]] == [
        "researched-1",
        "researched-2",
    ]
    assert json.loads(research_evidence[2].origin)["synthesis"] is True
    assert research_evidence[3].dimensions == ("performance",)
    wave = json.loads((tmp_path / "run/wave-1.json").read_text())
    assert [row["status"] for row in wave] == ["accepted", "accepted"]
    assert [len(row["admitted"]) for row in wave] == [3, 3]
    planned = json.loads(provider.requests[1]["messages"][1]["content"])
    assert planned["allowance"]["window_seconds_per_group"] <= 1800 and planned["previous_wave"] is None
    composed = json.loads(provider.requests[3]["messages"][1]["content"])
    assert len(composed["research"]["outcomes"]) == 2 and composed["research"]["gaps"] == []
    assert labels(tmp_path / "run/trace.json") == ["assess", "plan", "plan", "compose", "information.review"]


@pytest.mark.asyncio
async def test_plans_are_checked_for_focus_questions_and_known_evidence():
    async def research(task):
        return delivery()

    provider = Provider(
        response(ASSESS, assessment(research_needs=[need()])),
        response(PLAN, plan(group(known_evidence=["evidence-99"]))),
        response(PLAN, plan(group(brief=research_brief(questions=["One?", "Two?", "Three?"])))),
        response(PLAN, plan(group(dimensions=["knowledge", "knowledge"]))),
        response(PLAN, plan(group("Which internal form do they file?", serves=["need-2"]))),
        response(SUBMIT, description()),
        response(REVIEW, accepted()),
    )
    result = await collect_information(
        provider, Request(objective="Describe the expert."), research=research, limits=CollectionLimits(plan_calls=5)
    )
    errors = rejections(provider.requests[5])
    assert any("answers only the listed refs ['need-1'], got ['need-2']" in error for error in errors)
    assert any("unknown research evidence" in error for error in errors)
    assert any("at most 2 questions" in error for error in errors)
    assert any("each dimension once" in error for error in errors)
    assert result.stop_reason == "error" and not result.ready


@pytest.mark.asyncio
async def test_a_group_is_asked_the_question_of_every_need_it_serves(tmp_path):
    tasks = []

    async def research(task):
        tasks.append(task)
        return delivery()

    sharper = "How should uncertainty be recorded next to each claim in a project review?"
    restated = "Which ‘review cadence’  applies? -- the template asks for it."
    provider = Provider(
        response(
            ASSESS, assessment(research_needs=[need(), need("Which 'review cadence' applies?", ("performance",))])
        ),
        response(
            PLAN,
            plan(
                group(sharper),
                group("Which internal form do they file?", serves=["need-1", "need-2"]),
                group(restated, serves=["need-2"]),
            ),
        ),
        response(SUBMIT, description(evidence=("evidence-3",))),
        response(REVIEW, accepted()),
    )
    result = await collect_information(
        provider, Request(objective="Describe the expert."), research=research, records=tmp_path / "run"
    )
    assert result.ready
    assert [task.brief.questions for task in tasks] == [
        (sharper, "How should uncertainty be recorded?"),
        ("Which internal form do they file?", "How should uncertainty be recorded?", "Which 'review cadence' applies?"),
        (restated,),
    ]
    kept = json.loads((tmp_path / "run/plan-1.json").read_text())
    assert kept["groups"][1]["brief"]["questions"][1:] == [
        "How should uncertainty be recorded?",
        "Which 'review cadence' applies?",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("new_sources", [False, True])
async def test_a_withheld_group_is_repaired_once_by_host_rule(tmp_path, new_sources):
    tasks = []

    async def research(task):
        tasks.append(task)
        if task.previous_attempt is None:
            return delivery(
                findings=1, withheld=(("researched-2", "The passage says cream."),), needs_new_sources=new_sources
            )
        return delivery(findings=1)

    provider = Provider(
        response(ASSESS, assessment(research_needs=[need()])),
        response(PLAN, plan(group())),
        response(SUBMIT, description(evidence=("evidence-3",))),
        response(REVIEW, accepted()),
    )
    limits = CollectionLimits(research_window=500, wave_minimum=300, acquisition_minimum=600, editorial_minimum=300)
    result = await collect_information(
        provider, Request(objective="Describe the expert."), research=research, limits=limits, records=tmp_path / "run"
    )
    assert result.ready
    wave = json.loads((tmp_path / "run/wave-1.json").read_text())[0]
    trace = json.loads((tmp_path / "run/trace.json").read_text())
    if new_sources:
        assert [task.attempt for task in tasks] == ["research-1"]
        assert wave["status"] == "partial" and wave["withheld"][0]["id"] == "researched-2"
        assert any(row.get("event") == "repair.skipped" and row["seconds_needed"] == 600 for row in trace)
    else:
        assert [(task.attempt, task.previous_attempt) for task in tasks] == [
            ("research-1", None),
            ("research-2", "research-1"),
        ]
        assert tasks[1].remaining_seconds < 500
        assert wave["status"] == "accepted" and [row["attempt"] for row in wave["attempts"]] == [
            "research-1",
            "research-2",
        ]
    admitted = [source for source in result.snapshot.evidence if source.channel == "research"]
    assert len(admitted) == (2 if new_sources else 4)


@pytest.mark.asyncio
async def test_research_is_skipped_when_no_group_window_remains(tmp_path):
    delegated = []

    async def research(task):
        delegated.append(task)
        return delivery()

    provider = Provider(
        response(ASSESS, assessment(research_needs=[need()])),
        response(SUBMIT, description()),
        response(REVIEW, accepted()),
    )
    limits = CollectionLimits(total_timeout=1000, reserve=600, wave_minimum=600)
    result = await collect_information(
        provider, Request(objective="Describe the expert."), research=research, limits=limits, records=tmp_path / "run"
    )
    assert result.ready and not delegated
    trace = json.loads((tmp_path / "run/trace.json").read_text())
    assert any(row.get("event") == "wave.skipped" and row["window"] <= 400 for row in trace)
    assert labels(tmp_path / "run/trace.json") == ["assess", "compose", "information.review"]


@pytest.mark.asyncio
@pytest.mark.parametrize("gap", [False, True])
async def test_a_second_wave_runs_only_when_gaps_remain(tmp_path, gap):
    async def research(task):
        answer = delivery()
        if gap and task.attempt == "research-1":
            answer["unanswered"] = [
                {"question": "Which cadence?", "channel": "research", "why": "No page found."},
                {"question": "Which cadence did the board set?", "channel": "user", "why": "Only the board knows."},
            ]
        return answer

    provider = Provider(
        response(ASSESS, assessment(research_needs=[need()])),
        response(PLAN, plan(group())),
        *([response(PLAN, plan(group("Which cadence?", serves=["gap-1"])))] if gap else []),
        response(SUBMIT, description(evidence=("evidence-3",))),
        response(REVIEW, accepted()),
    )
    result = await collect_information(
        provider,
        Request(objective="Describe the expert."),
        research=research,
        limits=CollectionLimits(research_waves=2),
        records=tmp_path / "run",
    )
    assert result.ready
    plans = [path.name for path in (tmp_path / "run").iterdir() if path.name.startswith("plan-")]
    assert sorted(plans) == (["plan-1.json", "plan-2.json"] if gap else ["plan-1.json"])
    if gap:
        second = json.loads(provider.requests[2]["messages"][1]["content"])
        assert [(row["kind"], row.get("ref")) for row in second["previous_wave"]["gaps"]] == [
            ("unanswered", "gap-1"),
            ("unanswered", None),
        ]
        assert [row["ref"] for row in second["research_needs"]] == ["need-1"]
        assert (tmp_path / "run/wave-2.json").exists()


@pytest.mark.asyncio
async def test_guidance_is_loaded_once_before_planning_and_attached_to_groups(tmp_path):
    loaded, tasks = [], []

    async def guidance():
        loaded.append(True)
        return [guide().model_dump(mode="json")]

    async def research(task):
        tasks.append(task)
        return delivery()

    provider = Provider(
        response(ASSESS, assessment(research_needs=[need()])),
        response(PLAN, plan(group(), group(use_guidance=False))),
        response(SUBMIT, description(evidence=("evidence-3",))),
        response(REVIEW, accepted()),
    )
    result = await collect_information(
        provider, Request(objective="Review evidence."), research=research, guidance=guidance, records=tmp_path / "run"
    )
    assert result.ready and loaded == [True]
    planned = json.loads(provider.requests[1]["messages"][1]["content"])
    assert planned["guidance"][0]["sources"] == ["guide-only-source"]
    assert [len(task.guidance) for task in tasks] == [1, 0]


@pytest.mark.asyncio
async def test_guidance_failure_leaves_research_unguided(tmp_path):
    async def guidance():
        raise ValueError("guidance source unreadable")

    async def research(task):
        return delivery()

    provider = Provider(
        response(ASSESS, assessment(research_needs=[need()])),
        response(PLAN, plan(group())),
        response(SUBMIT, description(evidence=("evidence-3",))),
        response(REVIEW, accepted()),
    )
    result = await collect_information(
        provider, Request(objective="Review evidence."), research=research, guidance=guidance, records=tmp_path / "run"
    )
    assert result.ready
    trace = json.loads((tmp_path / "run/trace.json").read_text())
    assert any(row.get("event") == "guidance.unavailable" for row in trace)
    assert json.loads(provider.requests[1]["messages"][1]["content"])["guidance"] == []


@pytest.mark.asyncio
async def test_a_failed_group_is_a_gap_and_the_others_still_land(tmp_path):
    async def failing(task):
        if task.brief.questions[0].startswith("Which"):
            raise TimeoutError("codex: no answer")
        return delivery()

    provider = Provider(
        response(ASSESS, assessment(research_needs=[need(), need("Which review cadence applies?", ("performance",))])),
        response(PLAN, plan(group(), group("Which review cadence applies?", serves=["need-2"]))),
        response(SUBMIT, description(evidence=("evidence-3",))),
        response(REVIEW, accepted()),
    )
    result = await collect_information(
        provider, Request(objective="Describe."), research=failing, records=tmp_path / "run"
    )
    assert result.ready
    wave = json.loads((tmp_path / "run/wave-1.json").read_text())
    assert [row["status"] for row in wave] == ["accepted", "failed"] and wave[1]["error_type"] == "TimeoutError"
    assert wave[1]["attempts"] == [
        {"attempt": "research-2", "previous_attempt": None, "status": "failed", "error": "codex: no answer"}
    ]
    composed = json.loads(provider.requests[2]["messages"][1]["content"])
    assert composed["research"]["gaps"] == [
        {"group": 2, "kind": "failed", "error": "codex: no answer", "questions": ["Which review cadence applies?"]}
    ]


@pytest.mark.asyncio
async def test_review_rejection_is_repaired_once_and_then_the_review_limit_holds(tmp_path):
    rejected = {"accepted": False, "reason": "The approval path is asserted without evidence.", "issues": ["Cite it."]}
    provider = Provider(
        response(ASSESS, assessment()),
        response(SUBMIT, description()),
        response(REVIEW, rejected),
        response(SUBMIT, description(text="The approval path is left open.")),
        response(REVIEW, rejected),
    )
    result = await collect_information(provider, Request(objective="Describe."), records=tmp_path / "run")
    assert result.stop_reason == "review_limit" and not result.ready and result.status == "incomplete"
    repair = provider.requests[3]["messages"]
    assert repair[-1]["role"] == "user" and "Cite it." in repair[-1]["content"]
    assert any(row["role"] == "tool" and "submitted_for_review" in row["content"] for row in repair)
    assert (tmp_path / "run/proposal-2.json").exists() and (tmp_path / "run/review-2.json").exists()
    assert labels(tmp_path / "run/trace.json") == [
        "assess",
        "compose",
        "information.review",
        "compose",
        "information.review",
    ]


@pytest.mark.asyncio
async def test_stage_timeouts_and_group_windows_keep_the_evidence(tmp_path):
    class Slow:
        async def chat_with_retry(self, **kwargs):
            await asyncio.sleep(10)

    result = await collect_information(
        Slow(), Request(objective="Describe the expert."), limits=CollectionLimits(assessment_timeout=0.01)
    )
    assert result.stop_reason == "time_limit" and not result.ready
    assert "assessment stage" in result.review.reason and result.snapshot.evidence[0].content == "Describe the expert."
    cancelled = []

    async def research(task):
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.append(task.attempt)

    provider = Provider(
        response(ASSESS, assessment(research_needs=[need()])),
        response(PLAN, plan(group())),
        response(SUBMIT, description()),
        response(REVIEW, accepted()),
    )
    result = await collect_information(
        provider,
        Request(objective="Describe the expert."),
        research=research,
        limits=CollectionLimits(
            research_window=0.05, wave_minimum=0.01, verification_reserve=0, editorial_minimum=0.001
        ),
        records=tmp_path / "run",
    )
    assert cancelled == ["research-1"] and result.ready
    wave = json.loads((tmp_path / "run/wave-1.json").read_text())
    assert wave[0]["status"] == "failed" and wave[0]["error_type"] == "TimeoutError"
    assert not any(source.channel == "research" for source in result.snapshot.evidence)
    composed = json.loads(provider.requests[2]["messages"][1]["content"])
    assert composed["research"]["gaps"][0]["kind"] == "failed"


@pytest.mark.asyncio
async def test_deadline_preserves_focused_state_and_reports_actual_changes():
    class Slow:
        async def chat_with_retry(self, **kwargs):
            await asyncio.sleep(10)

    previous = snapshot()
    result = await collect_information(
        Slow(),
        Request(objective="Recheck knowledge.", previous=previous, focus=("knowledge",)),
        limits=CollectionLimits(total_timeout=0.01),
    )
    assert result.snapshot.description == previous.description
    assert result.changed_dimensions == () and not result.resources_changed and not result.questions_changed
    assert result.stop_reason == "time_limit" and not result.ready


def test_every_stage_at_its_cap_fits_inside_the_hour():
    limits = CollectionLimits()
    worst = (
        limits.assessment_timeout
        + limits.plan_timeout * limits.research_waves
        + limits.research_window
        + limits.reserve
    )
    assert worst <= limits.total_timeout
    assert limits.wave_window(420) == 1800 and limits.wave_window(2000) == 700
    assert limits.acquisition_window(1800) == 1650 and limits.acquisition_window(200) == 100
    with pytest.raises(ValueError, match="verification reserve"):
        CollectionLimits(editorial_minimum=100, verification_reserve=100)
    with pytest.raises(ValueError, match="nonnegative"):
        CollectionLimits(research_tasks=-1)


@pytest.mark.asyncio
async def test_native_tools_are_bounded_queries_of_the_assessment(tmp_path):
    (tmp_path / "method.md").write_text("Verify claims against the supplied project evidence.")
    (tmp_path / "other.md").write_text("Another file.")
    registry = ToolRegistry()
    registry.register(ReadFileTool(workspace=tmp_path, allowed_dirs=(tmp_path,), follow_binding=False))
    cut_read = response("read_file", {"path": "method.md"})
    cut_read.tool_calls[0].run_meta = RunMeta(truncation=TruncationInfo(at_tokens=100))
    provider = Provider(
        cut_read,
        response("read_file", {"path": "method.md"}),
        response("read_file", {"path": "other.md"}),
        response(ASSESS, assessment(evidence=("evidence-3",))),
        response(SUBMIT, description(evidence=("evidence-3",))),
        response(REVIEW, accepted()),
    )
    result = await collect_information(
        provider,
        Request(objective="Describe the project expert."),
        registry=registry,
        limits=CollectionLimits(assessment_calls=5, native_queries=1),
    )
    assert result.ready
    tools = [source for source in result.snapshot.evidence if source.channel == "tool"]
    assert len(tools) == 1 and "Verify claims" in tools[0].content
    errors = rejections(provider.requests[3])
    assert any("truncated" in error for error in errors)
    assert any("allowance exhausted" in error for error in errors)


@pytest.mark.asyncio
async def test_a_blocking_native_refusal_stops_the_rest_of_the_batch():
    class Refusal(str):
        blocks_call = True

    class Registry:
        def get_definitions(self):
            return [{"type": "function", "function": {"name": "read_file", "parameters": {}}}]

        async def execute(self, *args, **kwargs):
            return Refusal("Error: access denied")

    combined = response("read_file", {"path": "private"})
    combined.tool_calls.extend(response("read_file", {"path": "second"}).tool_calls)
    provider = Provider(
        combined, response(ASSESS, assessment()), response(SUBMIT, description()), response(REVIEW, accepted())
    )
    result = await collect_information(provider, Request(objective="Inspect permitted evidence."), registry=Registry())
    assert result.ready
    assert any("blocked this batch" in error for error in rejections(provider.requests[1]))


@pytest.mark.asyncio
async def test_listed_sources_are_read_by_the_host_before_the_assessment(tmp_path):
    (tmp_path / "expert.md").write_text("A project reviewer who checks evidence.")
    (tmp_path / "long.md").write_text("x" * (SOURCE_CHARS + 10))
    context = {
        "interaction_sources": {
            "information.material.1.expert.md": {
                "path": str(tmp_path / "expert.md"),
                "source_path": "/home/uploads/materials/1-pack/expert.md",
                "worker_path": "uploads/materials/1-pack/expert.md",
                "digest": "abc",
            },
            "information.material.1.long.md": {"path": str(tmp_path / "long.md"), "digest": "def"},
            "information.material.1.gone.md": {"path": str(tmp_path / "gone.md"), "digest": "ghi"},
        }
    }
    provider = Provider(
        response(ASSESS, assessment(evidence=("evidence-3",))),
        response(SUBMIT, description(evidence=("evidence-3",))),
        response(REVIEW, accepted()),
    )
    result = await collect_information(
        provider, Request(objective="Describe.", context=context), records=tmp_path / "run"
    )
    assert result.ready
    read = [source for source in result.snapshot.evidence if source.channel == "tool"]
    assert len(read) == 2 and read[0].sources == ("uploads/materials/1-pack/expert.md#sha256=abc",)
    assert "truncated at" in read[1].content and len(read[1].content) < SOURCE_CHARS + 200
    packet = json.loads(provider.requests[0]["messages"][1]["content"])
    assert [row.get("read", False) for row in packet["sources"]] == [True, True, False]
    assert "A project reviewer" in packet["sources"][0]["text"] and "error" in packet["sources"][2]
    recorded = json.loads((tmp_path / "run/sources.json").read_text())
    assert "text" not in recorded[0] and recorded[1]["truncated"] is True


@pytest.mark.asyncio
async def test_focused_followup_accepts_answers_and_preserves_other_pending_questions(tmp_path):
    questions = (
        Question(
            id="question-1", dimension="methods", question="Who approves exceptions?", reason="Authority is unknown."
        ),
        Question(
            id="question-2",
            dimension="cases",
            question="Are there historical cases?",
            reason="Additional examples would help.",
            assumption="Worked examples stand in for cases.",
        ),
    )
    previous = snapshot()
    previous = Snapshot(
        description=previous.description.model_copy(update={"unresolved": questions}), evidence=previous.evidence
    )
    data = previous.description.model_dump(mode="json")
    data["unresolved"] = [questions[1].model_dump(mode="json")]
    data["sections"][4].update(text="The team lead approves exceptions.", evidence=["evidence-4"])
    provider = Provider(
        response(ASSESS, assessment(dimensions=("methods",))), response(SUBMIT, data), response(REVIEW, accepted())
    )
    result = await collect_information(
        provider,
        Request(
            objective="Resolve approval authority.",
            previous=previous,
            focus=("methods",),
            answers={"question-1": "The team lead approves exceptions."},
            answers_version=previous.identity,
        ),
        records=tmp_path / "records",
    )
    assert result.ready and result.changed_dimensions == ("methods",)
    assert result.snapshot.description.unresolved == (questions[1],)
    assert result.snapshot.evidence[-1].channel == "user"
    assert Snapshot.model_validate_json((tmp_path / "records/snapshot.json").read_text()) == result.snapshot
    with pytest.raises(ValidationError, match="known questions inside"):
        Request(objective="Resolve methods.", previous=previous, focus=("methods",), answers={"question-2": "Yes"})


@pytest.mark.asyncio
async def test_sections_and_open_points_outside_focus_are_preserved():
    outside = Question(
        id="outside", dimension="cases", question="Any incidents?", reason="None supplied.", assumption="None yet."
    )
    base = snapshot()
    previous = Snapshot(
        description=base.description.model_copy(update={"unresolved": (outside,)}), evidence=base.evidence
    )
    changed = previous.description.model_dump(mode="json")
    changed["sections"][6]["text"] = "A rewritten cases section."
    dropped = previous.description.model_dump(mode="json")
    dropped["unresolved"] = []
    kept = previous.description.model_dump(mode="json")
    kept["sections"][2]["text"] = "Updated knowledge."
    provider = Provider(
        response(ASSESS, assessment(dimensions=("knowledge",))),
        response(SUBMIT, changed),
        response(SUBMIT, dropped),
        response(SUBMIT, kept),
        response(REVIEW, accepted()),
    )
    result = await collect_information(
        provider, Request(objective="Recheck knowledge.", previous=previous, focus=("knowledge",))
    )
    assert result.ready and result.changed_dimensions == ("knowledge",)
    errors = rejections(provider.requests[3])
    assert any("section outside focus: cases" in error for error in errors)
    assert any("open point outside focus: outside" in error for error in errors)


@pytest.mark.asyncio
async def test_uncited_user_constraints_are_still_visible_to_review():
    answer = "Do not process restricted project data."
    provider = Provider(
        response(ASSESS, assessment(questions=[question("role", "What is excluded?")])),
        response(SUBMIT, description()),
        response(REVIEW, accepted()),
    )
    result = await collect_information(provider, Request(objective="Build a project reviewer."), ask=lambda q: answer)
    reviewed = json.loads(provider.requests[-1]["messages"][1]["content"])
    assert any(row["channel"] == "user" and row["content"] == answer for row in reviewed["evidence"])
    assert result.snapshot.evidence[-1].id not in result.snapshot.description.references


@pytest.mark.asyncio
async def test_adoption_answers_are_tied_to_the_exact_proposal_and_question():
    seen = []

    def answer(item):
        seen.append(item)
        return "Adopt this proposal for the review team."

    provider = Provider(
        response(
            ASSESS,
            assessment(
                questions=[
                    question(text="Adopt this workflow?", proposal="Require a second reviewer for uncertain claims.")
                ]
            ),
        ),
        response(SUBMIT, description(evidence=("evidence-3",))),
        response(REVIEW, accepted()),
    )
    result = await collect_information(provider, Request(objective="Define the workflow."), ask=answer)
    origin = json.loads(result.snapshot.evidence[-1].origin)
    assert origin["id"] == seen[0].id
    assert origin["proposal"] == "Require a second reviewer for uncertain claims."
    assert "Adopt this proposal" in render(result.snapshot)


@pytest.mark.asyncio
async def test_resource_and_question_changes_are_reported_without_section_changes():
    prior = snapshot()
    pending = Question(id="known", dimension="methods", question="Which service?", reason="Access is unknown.")
    prior = Snapshot(
        description=prior.description.model_copy(update={"unresolved": (pending,)}), evidence=prior.evidence
    )
    data = prior.description.model_dump(mode="json")
    data["unresolved"] = []
    data["resources"] = [
        {
            "name": "Registry",
            "purpose": "Check evidence",
            "availability": "unavailable",
            "requirements": ["User access is needed."],
        }
    ]
    provider = Provider(
        response(ASSESS, assessment(dimensions=("methods",))), response(SUBMIT, data), response(REVIEW, accepted())
    )
    result = await collect_information(
        provider,
        Request(
            objective="Clarify prerequisites.",
            previous=prior,
            focus=("methods",),
            answers={"known": "The registry is unavailable; use supplied evidence only."},
            answers_version=prior.identity,
        ),
    )
    assert result.changed_dimensions == ()
    assert result.resources_changed and result.questions_changed


def test_handover_keeps_reference_transcripts_out_of_the_worker_workspace(tmp_path):
    original = snapshot()
    raw = Evidence(
        id="reference-data",
        channel="tool",
        origin="reference product",
        content="Original customer identity, secret example values, and product-specific installation instructions.",
    )
    information = original.model_copy(update={"evidence": (*original.evidence, raw)})
    result = Result(snapshot=information, review=Review.model_validate(accepted()))
    worker = SimpleNamespace(baseline=SimpleNamespace(config=SimpleNamespace(workspace_path=tmp_path)))
    assert handover_information(worker, result) == INFORMATION_FILE
    text = (tmp_path / INFORMATION_FILE).read_text()
    assert "Professional knowledge" in text and "Original customer identity" not in text
    assert set(path.name for path in (tmp_path / "uploads/information").iterdir()) == {"expert.md", "version.json"}


def test_information_handoff_checks_base_version_content_and_pending_curation(tmp_path):
    worker = SimpleNamespace(
        root=tmp_path / "run", baseline=SimpleNamespace(config=SimpleNamespace(workspace_path=tmp_path / "home"))
    )
    initial = Result(snapshot=snapshot(), review=Review.model_validate(accepted()))
    handover_information(worker, initial)
    changed = Snapshot(
        description=Description.model_validate(description(text="An updated description.")),
        evidence=initial.snapshot.evidence,
    )
    stale = Result(snapshot=changed, review=initial.review, previous="another-version")
    with pytest.raises(ValueError, match="base version changed"):
        handover_information(worker, stale)
    updated = stale.model_copy(update={"previous": initial.snapshot.identity})
    handover_information(worker, updated)
    assert handover_information(worker, updated) == INFORMATION_FILE
    pending = worker.root / "curation/pending.json"
    pending.parent.mkdir(parents=True)
    pending.write_text("{}")
    with pytest.raises(ValueError, match="paused curation"):
        handover_information(worker, updated)
    pending.unlink()
    (worker.baseline.config.workspace_path / INFORMATION_FILE).write_text("Unversioned edit")
    with pytest.raises(ValueError, match="changed outside"):
        handover_information(worker, updated)


@pytest.mark.parametrize("checkpoint", ["composition.json", "attribution-scope/root/curation/pending.json"])
def test_publication_refuses_composite_and_nested_checkpoints(tmp_path, checkpoint):
    worker = SimpleNamespace(
        root=tmp_path / "run", baseline=SimpleNamespace(config=SimpleNamespace(workspace_path=tmp_path / "home"))
    )
    path = worker.root / "curation" / checkpoint
    path.parent.mkdir(parents=True)
    path.write_text("{}")
    with pytest.raises(ValueError, match="paused curation"):
        handover_information(worker, Result(snapshot=snapshot(), review=Review.model_validate(accepted())))
    assert not (tmp_path / "home").exists()


def test_interrupted_publication_recovers_the_same_version(tmp_path, monkeypatch):
    from experimental.research import curator

    worker = SimpleNamespace(
        root=tmp_path / "run", baseline=SimpleNamespace(config=SimpleNamespace(workspace_path=tmp_path / "home"))
    )
    result = Result(snapshot=snapshot(), review=Review.model_validate(accepted()))
    write = curator._write
    failed = []

    def interrupted(path, content):
        if path.name == "version.json" and not failed:
            failed.append(True)
            raise OSError("Interrupted between content and version publication")
        write(path, content)

    monkeypatch.setattr(curator, "_write", interrupted)
    with pytest.raises(OSError):
        handover_information(worker, result)
    target = tmp_path / "home" / INFORMATION_FILE
    assert (target.parent / "publication.json").exists()
    handover_information(worker, result)
    assert not (target.parent / "publication.json").exists()
    assert json.loads((target.parent / "version.json").read_text())["version"] == result.snapshot.identity


def test_review_cannot_be_reused_after_changing_its_snapshot(tmp_path):
    result = Result(snapshot=snapshot(), review=Review.model_validate(accepted()))
    data = result.model_dump(mode="json")
    data["snapshot"]["description"]["sections"][0]["text"] = "Different unsupported role."
    with pytest.raises(ValueError, match="another information version"):
        Result.model_validate(data)


def test_abandoned_composition_scope_does_not_block_new_information(tmp_path):
    worker = SimpleNamespace(
        root=tmp_path / "run", baseline=SimpleNamespace(config=SimpleNamespace(workspace_path=tmp_path / "home"))
    )
    abandoned = worker.root / "curation/scopes/old/child/curation/pending.json"
    abandoned.parent.mkdir(parents=True)
    abandoned.write_text("{}")
    assert (
        handover_information(worker, Result(snapshot=snapshot(), review=Review.model_validate(accepted())))
        == INFORMATION_FILE
    )


def test_answers_refuse_another_snapshot_even_when_question_ids_match():
    base = snapshot()
    item = Question(
        id="known-question",
        dimension="methods",
        question="Adopt this method?",
        proposal="Use two reviewers.",
        reason="An organisational decision is needed.",
    )
    previous = Snapshot(description=base.description.model_copy(update={"unresolved": (item,)}), evidence=base.evidence)
    with pytest.raises(ValueError, match="exact previous information version"):
        Request(
            objective="Resolve adoption.",
            previous=previous,
            answers={item.id: "Yes"},
            answers_version="another-version",
        )


def test_recorded_information_restores_source_scope_on_a_new_worker():
    from experimental.curator.raven_adapter.exploration import Withheld
    from experimental.curator.workflow import information_scope

    worker = SimpleNamespace(withheld=Withheld(paths=("evaluation/*",)))
    feedback = {"information": {"version": "recorded", "excluded_sources": ["docs/research-case.md"]}}
    information_scope(worker, feedback)
    information_scope(worker, feedback)
    assert worker.withheld.paths == ("evaluation/*", "docs/research-case.md")
