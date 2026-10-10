"""Exercise information collection with native Raven file and subprocess tools before Curator handoff."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from experimental.curator.harness import Declaration, Task
from experimental.curator.raven_adapter.exploration import Exploration, Withheld
from experimental.curator.raven_adapter.inspection import Inspection, file_source
from experimental.curator.raven_adapter.targets import catalogue
from experimental.research import curator
from experimental.research.collection import ASSESS, PLAN, REVIEW, SUBMIT
from experimental.research.guidance import SUBMIT as SUBMIT_GUIDANCE
from experimental.research.information import Request, Result, Review, Snapshot
from experimental.research.inquiry import Inquiry
from raven.config.schema import Config
from tests.research_helpers import Provider, response
from tests.test_harness_curator_exploration import Executor
from tests.test_research_collection import accepted, assessment, description, group, need, plan, snapshot
from tests.test_research_inquiry import FOUND, PAGE, TEXT, Pages

pytestmark = pytest.mark.integration


def research_review(*admitted, withheld=(), issues=(), needs_new_sources=False, reason="The delivery is supported."):
    return {
        "reason": reason,
        "findings": [{"id": id, "admit": True} for id in admitted]
        + [{"id": id, "admit": False, "reason": why} for id, why in withheld],
        "synthesis_admitted": not issues,
        "issues": list(issues),
        "needs_new_sources": needs_new_sources,
    }


def host(tmp_path, monkeypatch):
    repository = tmp_path / "repository"
    (repository / "raven").mkdir(parents=True)
    source = repository / "raven/evidence.py"
    source.write_text('"""Stable task evidence."""\nVALUE = 42\n')
    reference = tmp_path / "reference"
    reference.mkdir()
    (reference / "expert.md").write_text("A reference persona with invented customer history.")
    config = Config()
    config.agents.defaults.workspace = str(tmp_path / "worker")
    config.permissions.tools["exec"] = "allow"
    task = Task(text="Describe a project evidence expert.")
    inspection = Inspection(
        Declaration("baseline", catalogue()),
        {"task": task.model_dump(), "authored": {"values": {}}},
        {"reference.host_contract": file_source(source)},
    )
    executor = Executor()
    explorations = []

    def exploration(config, inspected, **kwargs):
        source_paths = kwargs.pop("source_paths", ("raven",))
        kwargs.pop("repository", None)
        value = Exploration(
            config, inspected, repository=repository, source_paths=source_paths, executor=executor, **kwargs
        )
        explorations.append(value)
        return value

    monkeypatch.setattr(curator, "Exploration", exploration)
    monkeypatch.setattr(curator, "SOURCE_ROOT", repository)

    class Worker:
        baseline = SimpleNamespace(config=config, task=task)
        withheld = Withheld()

        async def inspect(self):
            return inspection

    return Worker(), reference, executor, explorations


@pytest.mark.asyncio
async def test_native_file_and_shell_evidence_is_reviewed_without_deploying_the_reference(tmp_path, monkeypatch):
    worker, reference, executor, explorations = host(tmp_path, monkeypatch)
    provider = Provider(
        response("read_file", {"path": "source/raven/evidence.py"}),
        response("exec", {"command": "cat source/raven/evidence.py"}),
        response(ASSESS, assessment(evidence=("evidence-3", "evidence-4"))),
        response(
            SUBMIT, description(evidence=("evidence-3", "evidence-4"), text="The inspected module defines VALUE as 42.")
        ),
        response(REVIEW, accepted()),
    )
    result = await curator.collect_for_curator(
        worker,
        provider,
        Request(objective="Inspect local code to support the expert description."),
        research_references=(reference,),
        records=tmp_path / "records",
        researcher=None,
    )
    assert result.ready
    assert executor.starts == executor.stops == 1
    assert not explorations[0].root.exists()
    packet = json.loads(provider.requests[0]["messages"][1]["content"])
    context = json.loads(packet["context"]["result"])
    assert "reference.host_contract" in context["host_sources"]
    assert not context["interaction_sources"]
    assert str(reference) not in json.dumps(context)
    assert any(source.channel == "tool" and "VALUE = 42" in source.content for source in result.snapshot.evidence)
    curator.handover_information(worker, result)
    assert (worker.baseline.config.workspace_path / curator.INFORMATION_FILE).is_file()
    assert not (worker.baseline.config.workspace_path / "expert.md").exists()


@pytest.mark.asyncio
async def test_modified_source_snapshot_invalidates_even_an_accepted_collection(tmp_path, monkeypatch):
    worker, reference, executor, _ = host(tmp_path, monkeypatch)
    provider = Provider(
        response("exec", {"command": "printf changed > source/raven/evidence.py"}),
        response(ASSESS, assessment()),
        response(SUBMIT, description()),
        response(REVIEW, accepted()),
    )
    with pytest.raises(ValueError, match="input changed"):
        await curator.collect_for_curator(
            worker,
            provider,
            Request(objective="Inspect the current code."),
            research_references=(reference,),
            records=tmp_path / "records",
            researcher=None,
        )
    record = json.loads((tmp_path / "records/result.json").read_text())
    assert record["status"] == "invalid"
    assert executor.starts == executor.stops == 1
    assert not (worker.baseline.config.workspace_path / "uploads").exists()


@pytest.mark.parametrize("has_guidance", [False, True])
@pytest.mark.asyncio
async def test_supplied_interaction_content_can_satisfy_collection_without_research(
    tmp_path, monkeypatch, has_guidance
):
    worker, reference, _, _ = host(tmp_path, monkeypatch)
    material = tmp_path / "provided.md"
    material.write_text("Use the evidence checklist supplied by the owner.")

    async def unused(*args, **kwargs):
        pytest.fail("optional guidance must not be extracted before a research need exists")

    monkeypatch.setattr(curator, "derive_guidance", unused)
    provider = Provider(
        response(ASSESS, assessment(evidence=("evidence-3",))),
        response(SUBMIT, description(evidence=("evidence-3",))),
        response(REVIEW, accepted()),
    )
    result = await curator.collect_for_curator(
        worker,
        provider,
        Request(objective="Apply the provided checklist."),
        materials=(material,),
        research_references=(reference,) if has_guidance else (),
        records=tmp_path / "records",
        researcher=None,
    )
    assert result.ready and "owner" in result.snapshot.evidence[-1].content
    packet = json.loads(provider.requests[0]["messages"][1]["content"])
    assert packet["sources"][0]["evidence"] == "evidence-3" and "owner" in packet["sources"][0]["text"]
    assert not (tmp_path / "records/guidance").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("relative_read", [False, True])
async def test_research_only_case_is_isolated_and_guides_a_multi_dimension_research_group(
    tmp_path, monkeypatch, relative_read
):
    worker, _, _, explorations = host(tmp_path, monkeypatch)
    reference = tmp_path / "repository/raven/product_case"
    case = reference / ".plugin" / "instructions.md"
    case.parent.mkdir(parents=True)
    case.write_text("UNVERIFIED_PRODUCT_RULE: serve at midnight. Consider how service hours affect planning.")
    tasks = []
    pages = Pages({PAGE: TEXT})

    class Researcher:
        def __init__(self, *args, **kwargs):
            pass

        async def research(self, packet, web, check, *, trace=None, records=None):
            tasks.append(packet)
            return Inquiry.model_validate({"findings": [FOUND]}), {"researcher": "controlled"}

    monkeypatch.setattr(curator, "Exchange", Researcher)
    monkeypatch.setattr(curator.Web, "of", lambda *args, **kwargs: pages)

    def read_guidance(kwargs):
        packet = json.loads(kwargs["messages"][1]["content"])
        source = next(iter(packet["sources"].values()))
        path = source["path"]
        if relative_read:
            path = str(Path(path).relative_to(explorations[1].root))
        return response("read_file", {"path": path})

    def submit_guidance(kwargs):
        result = json.loads(kwargs["messages"][-1]["content"])
        assert result["source_ids"] == ["research.example.1..plugin/instructions.md"]
        return response(
            SUBMIT_GUIDANCE,
            {
                "groups": [
                    {
                        "topic": "Time constraints",
                        "dimensions": ["knowledge", "methods"],
                        "questions": ["Which service hours constrain a plan?"],
                        "rationale": "A product case suggests verifying timing constraints.",
                        "sources": result["source_ids"],
                    }
                ]
            },
        )

    provider = Provider(
        response(ASSESS, assessment(research_needs=[need("Missing service hours")])),
        read_guidance,
        submit_guidance,
        response(PLAN, plan(group("How should service hours affect planning?", known_evidence=["evidence-1"]))),
        response("review_research", research_review("researched-1")),
        response(SUBMIT, description(evidence=("evidence-3",), text=FOUND["text"])),
        response(REVIEW, accepted()),
    )
    result = await curator.collect_for_curator(
        worker,
        provider,
        Request(objective="Plan using verified service information."),
        research_references=(reference,),
        records=tmp_path / "records",
    )
    assert result.ready and len(tasks) == 1 and len(explorations) == 2
    assert tasks[0]["questions"] == ["How should service hours affect planning?", "Missing service hours"]
    assert 0 < tasks[0]["time_budget_seconds"] < 3600
    assert "dimensions" not in tasks[0] and "guidance" not in tasks[0]
    assert "evidence-1" not in json.dumps(tasks[0])
    review_request = next(
        request
        for request in provider.requests
        if any(tool["function"]["name"] == "review_research" for tool in request.get("tools", []))
    )
    assert json.loads(review_request["messages"][1]["content"])["source_views"][PAGE] == TEXT
    assert "UNVERIFIED_PRODUCT_RULE" not in result.snapshot.model_dump_json()
    assert case not in explorations[0].originals and case in explorations[1].originals
    assert (tmp_path / "records/guidance/guidance.json").is_file()
    assert not (worker.baseline.config.workspace_path / "uploads").exists()


@pytest.mark.asyncio
async def test_explicit_interaction_file_is_not_hidden_by_a_research_reference_parent(tmp_path, monkeypatch):
    worker, _, _, explorations = host(tmp_path, monkeypatch)
    reference = tmp_path / "repository/raven/case"
    reference.mkdir()
    provided = reference / "provided.md"
    hidden = reference / "research-only.md"
    provided.write_text("This checklist was supplied in the interaction.")
    hidden.write_text("This separate case is for research guidance only.")

    def assess(kwargs):
        packet = json.loads(kwargs["messages"][1]["content"])
        context = json.loads(packet["context"]["result"])
        source = next(iter(context["interaction_sources"].values()))
        assert source["source_path"] == str(provided) and source["worker_path"] is None
        assert "supplied in the interaction" in packet["sources"][0]["text"]
        return response(ASSESS, assessment(evidence=("evidence-3",)))

    provider = Provider(assess, response(SUBMIT, description(evidence=("evidence-3",))), response(REVIEW, accepted()))
    result = await curator.collect_for_curator(
        worker,
        provider,
        Request(objective="Use the given checklist."),
        materials=(provided,),
        research_references=(reference,),
        records=tmp_path / "records",
        researcher=None,
    )
    assert result.ready and provided in explorations[0].originals and hidden not in explorations[0].originals


@pytest.mark.parametrize("stale", [False, True])
@pytest.mark.asyncio
async def test_existing_information_requires_the_current_snapshot_before_any_model_call(tmp_path, monkeypatch, stale):
    worker, _, _, _ = host(tmp_path, monkeypatch)
    initial = Result(snapshot=snapshot(), review=Review.model_validate(accepted()))
    curator.handover_information(worker, initial)
    previous = (
        Snapshot(
            description=initial.snapshot.description.model_copy(update={"title": "Stale description"}),
            evidence=initial.snapshot.evidence,
        )
        if stale
        else None
    )
    provider = Provider()
    with pytest.raises(ValueError, match="current snapshot before collection"):
        await curator.collect_for_curator(
            worker,
            provider,
            Request(objective="Update the expert.", previous=previous),
            records=tmp_path / "records",
            researcher=None,
        )
    assert not provider.requests


@pytest.mark.asyncio
async def test_frozen_result_replays_without_model_calls_but_refuses_changed_inputs(tmp_path, monkeypatch):
    worker, material, _, _ = host(tmp_path, monkeypatch)
    request = Request(objective="Review the current project.")
    first = await curator.collect_for_curator(
        worker,
        Provider(response(ASSESS, assessment()), response(SUBMIT, description()), response(REVIEW, accepted())),
        request,
        materials=(material,),
        records=tmp_path / "first",
    )
    empty = Provider()
    second = await curator.collect_for_curator(
        worker, empty, request, materials=(material,), replay=first, records=tmp_path / "replay"
    )
    assert second == first and not empty.requests
    (material / "expert.md").write_text("The professional scope changed.")
    with pytest.raises(ValueError, match="does not match"):
        await curator.collect_for_curator(
            worker, empty, request, materials=(material,), replay=first, records=tmp_path / "changed"
        )
    assert not empty.requests


@pytest.mark.asyncio
@pytest.mark.parametrize("model", [None, "alternate/test"])
async def test_offline_entry_returns_reviewed_information_without_curation(tmp_path, monkeypatch, model):
    from argparse import Namespace

    from experimental.research import __main__ as entry
    from experimental.scenario import load
    from experimental.scenario.digest import digest
    from tests.research_helpers import make_scenario

    worker, _, _, _ = host(tmp_path, monkeypatch)
    worker.root = tmp_path / "run"
    source = load(make_scenario(tmp_path / "shop"))
    worker.baseline.task = Task(text=source.situation.profile)
    before = digest(source.root)

    async def enter(self):
        return self

    async def leave(self, *args):
        return None

    monkeypatch.setattr(type(worker), "__aenter__", enter, raising=False)
    monkeypatch.setattr(type(worker), "__aexit__", leave, raising=False)
    monkeypatch.setattr(entry, "hire_task", lambda *args, **kwargs: worker)
    provider = Provider(response(ASSESS, assessment()), response(SUBMIT, description()), response(REVIEW, accepted()))
    factories = []
    monkeypatch.setattr(entry, "make_lazy_provider", lambda config: factories.append("lazy") or provider)
    monkeypatch.setattr(entry, "make_resolving_provider", lambda config: factories.append("resolving") or provider)
    args = Namespace(
        output=worker.root,
        scenario=source.root,
        task_file=None,
        config=tmp_path / "config.json",
        material=[],
        research_reference=[],
        previous_information=None,
        answers_file=None,
        release=["prices"],
        disclose="staged",
        focus=list(curator.Request.model_fields["focus"].default),
        research_guidance=None,
        model=model,
        research="none",
        research_model=None,
        research_budget=2,
        research_tasks=0,
        timeout=30,
        research_window=1800,
        research_waves=1,
        collector="provider",
        collection_effort="high",
        spend_limit=None,
        collection_timeout=3600,
        submission_reserve=600,
        research_questions=2,
        research_revisions=1,
        interactive=False,
        wait_for_input=False,
    )
    result = await entry.research(args)
    assert provider.requests[0]["model"] == model
    assert factories == (["resolving"] if model else ["lazy"])
    assert result["status"] == "ready"
    assert Result.model_validate_json((worker.root / "result.json").read_text()).ready
    assert not (worker.root / "curation").exists()
    assert not (worker.root / "scenario.json").exists() and digest(source.root) == before
    assert {p.name for p in (worker.baseline.config.workspace_path / "uploads").iterdir()} == {"prices"}


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked", [False, True])
async def test_scenario_onboarding_uses_the_shared_flow_and_release_boundary(tmp_path, monkeypatch, blocked):
    from experimental.iteration.session import Session
    from experimental.research.scenario import scenario_preparer, stage_released
    from experimental.scenario import load
    from tests.research_helpers import CHECK, make_scenario

    worker, _, _, explorations = host(tmp_path, monkeypatch)
    worker.root = tmp_path / "run"
    worker.last_plan = None
    source = load(make_scenario(tmp_path / "shop"))
    worker.baseline.task = Task(text=source.situation.profile)
    stage_released(source, ("prices",), worker.baseline.config.workspace_path)

    def compose(kwargs):
        pending = json.loads(kwargs["messages"][1]["content"])["open_user_questions"]
        return response(SUBMIT, description(unresolved=pending))

    asked = {"dimension": "methods", "question": "Who authorizes this method?", "reason": "A decision is missing."}
    provider = Provider(
        response(ASSESS, assessment(questions=[asked] if blocked else [])), compose, response(REVIEW, accepted())
    )
    curated = []

    async def curate(worker, provider, **kwargs):
        curated.append(kwargs["feedback"])
        assert (worker.baseline.config.workspace_path / curator.INFORMATION_FILE).is_file()
        assert kwargs["feedback"]["information"]["version"]

    session = Session.open(
        worker,
        provider,
        analyst=object(),
        curator=curate,
        prepare=scenario_preparer(
            source,
            ("prices",),
            worker.baseline.config.workspace_path / "uploads",
            records=worker.root / "information",
            researcher=None,
            ask=lambda question: None,
            wait_for_input=blocked,
        ),
    )
    assert await session.onboard() is not blocked
    assert bool(curated) is not blocked
    assert session.record["information"]["status"] == ("needs_input" if blocked else "ready")
    model_input = json.dumps(provider.requests[0]["messages"])
    assert CHECK not in model_input and "Discounts above ten percent" not in model_input
    assert all(not path.is_relative_to(source.root) for path in explorations[0].originals)


def test_environment_binding_ignores_run_locations_but_not_permissions(tmp_path):
    from experimental.research.curator import _environment

    first = SimpleNamespace(
        root=tmp_path / "a", baseline=SimpleNamespace(workdir=tmp_path / "a/work", task=Task(text="Review evidence."))
    )
    second = SimpleNamespace(
        root=tmp_path / "b", baseline=SimpleNamespace(workdir=tmp_path / "b/work", task=Task(text="Review evidence."))
    )

    def inspection(worker, permission):
        return SimpleNamespace(
            sources={},
            facts={
                "configuration": {
                    "workspace": str(worker.root / "home"),
                    "workdir": str(worker.baseline.workdir),
                    "task": worker.baseline.task.id,
                    "permission": permission,
                }
            },
        )

    a = _environment(first, inspection(first, "read"), first.root / "home")
    b = _environment(second, inspection(second, "read"), second.root / "home")
    assert a == b
    assert a != _environment(second, inspection(second, "deny"), second.root / "home")


@pytest.mark.parametrize("model", ["child/model", "other/model"])
def test_environment_binding_follows_a_childs_definition_not_the_version_its_run_paths_give_it(tmp_path, model):
    import hashlib

    from experimental.research.curator import _environment

    def worker(name, child_model):
        root = tmp_path / model / name
        worker = SimpleNamespace(
            root=root, baseline=SimpleNamespace(workdir=root / "work", task=Task(text="Review evidence."))
        )
        content = json.dumps(
            {"workdir": str(worker.baseline.workdir), "task": worker.baseline.task.id, "model": child_model}
        )
        definition = root / "children/c1/versions" / hashlib.sha256(content.encode()).hexdigest() / "deployment.json"
        definition.parent.mkdir(parents=True)
        definition.write_text(content)
        facts = {"configuration": {"command": f"python -m acp --deployment {definition}"}}
        return worker, SimpleNamespace(sources={}, facts=facts)

    (first, seen), (second, again) = worker("a", "child/model"), worker("b", model)
    same = _environment(first, seen, first.root / "home") == _environment(second, again, second.root / "home")
    assert same == (model == "child/model")


@pytest.mark.asyncio
async def test_replay_cannot_ignore_new_answers(tmp_path, monkeypatch):
    from experimental.research.information import Question

    worker, material, _, _ = host(tmp_path, monkeypatch)
    base = snapshot()
    question = Question(
        id="optional",
        dimension="methods",
        question="Adopt a second reviewer?",
        proposal="Require two reviewers.",
        reason="Optional policy choice.",
        blocking=False,
    )
    previous = Snapshot(
        description=base.description.model_copy(update={"unresolved": (question,)}), evidence=base.evidence
    )
    request = Request(objective="Review project evidence.", previous=previous)
    first = await curator.collect_for_curator(
        worker,
        Provider(
            response(ASSESS, assessment()),
            response(SUBMIT, previous.description.model_dump(mode="json")),
            response(REVIEW, accepted()),
        ),
        request,
        materials=(material,),
        records=tmp_path / "first",
    )
    updated = Request(
        objective=request.objective,
        previous=previous,
        answers={question.id: "Adopt the proposal."},
        answers_version=previous.identity,
    )
    empty = Provider()
    with pytest.raises(ValueError, match="does not match"):
        await curator.collect_for_curator(
            worker, empty, updated, materials=(material,), replay=first, records=tmp_path / "replay"
        )
    assert not empty.requests


@pytest.mark.asyncio
async def test_research_only_source_exclusion_survives_handoff_and_replay(tmp_path, monkeypatch):
    worker, _, _, _ = host(tmp_path, monkeypatch)
    case = tmp_path / "repository/raven/product_case.md"
    case.write_text("A research-only example, not an adopted operating rule.")
    request = Request(objective="Review project evidence.")
    result = await curator.collect_for_curator(
        worker,
        Provider(response(ASSESS, assessment()), response(SUBMIT, description()), response(REVIEW, accepted())),
        request,
        research_references=(case,),
        records=tmp_path / "first",
    )
    assert result.snapshot.manifest.excluded_sources == ("raven/product_case.md",)
    empty = Provider()
    replayed = await curator.collect_for_curator(worker, empty, request, replay=result, records=tmp_path / "replay")
    curator.handover_information(worker, replayed)
    assert "raven/product_case.md" in worker.withheld.paths
    assert not empty.requests


@pytest.mark.asyncio
async def test_collector_requests_repair_through_the_shared_curator_path(tmp_path, monkeypatch):
    worker, _, _, _ = host(tmp_path, monkeypatch)
    requests = []

    class Researcher:
        def __init__(self, *args, **kwargs):
            pass

        async def research(self, packet, web, check, **kwargs):
            requests.append(packet)
            return Inquiry(findings=[{**FOUND, "text": "Tea is served at midnight."}]), {"researcher": "controlled"}

        async def revise(self, packet, check, **kwargs):
            requests.append(packet)
            return Inquiry(findings=[FOUND]), {"researcher": "controlled", "editorial": True}

    monkeypatch.setattr(curator, "Exchange", Researcher)
    monkeypatch.setattr(curator.Web, "of", lambda *args, **kwargs: Pages({PAGE: TEXT}))

    provider = Provider(
        response(ASSESS, assessment(research_needs=[need("When is tea served?")])),
        response(PLAN, plan(group("When is tea served?"))),
        response(
            "review_research",
            research_review(
                withheld=(("researched-1", "The passage says two to five."),),
                issues=["Correct the serving time."],
                reason="The claim contradicts the quote.",
            ),
        ),
        response("review_research", research_review("researched-1")),
        response(SUBMIT, description(evidence=("evidence-3",), text=FOUND["text"])),
        response(REVIEW, accepted()),
    )
    result = await curator.collect_for_curator(
        worker, provider, Request(objective="Describe the service."), records=tmp_path / "records"
    )
    assert result.ready and len(requests) == 2
    assert requests[1]["revision"]["editorial"] and requests[1]["revision"]["source_views"][PAGE] == TEXT
    assert requests[1]["revision"]["previous_reviews"][0]["issues"] == ["Correct the serving time."]
    assert "midnight" not in result.snapshot.model_dump_json()
    composed = json.loads(provider.requests[4]["messages"][1]["content"])
    assert "midnight" not in json.dumps(composed["evidence"])
    assert json.loads((tmp_path / "records/research-1/status.json").read_text())["status"] == "rejected"
    assert json.loads((tmp_path / "records/research-2/status.json").read_text())["status"] == "accepted"
