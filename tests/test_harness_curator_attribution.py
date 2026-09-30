"""Attribution is a step of its own before every curation: it covers each input, runs in its own exchange on the
Curator's model by default, pauses and resumes on its own checkpoint, is recorded on its own, and the generation
grounds every target on it."""

import json
from pathlib import Path

import pytest

from experimental.curator import workflow
from experimental.curator.attribution import (
    NAME,
    PROMPT_FILES,
    PROMPTS,
    AttributionLimits,
    AttributionPausedError,
    ModelAttributor,
    SuppliedAttributor,
    parse,
    subjects,
)
from experimental.curator.generation.run import GapReportedError, GenerationPausedError, Limits, generate
from experimental.curator.generation.stages import design
from experimental.curator.harness import Attributed, Attribution, Declaration, Validation
from experimental.curator.harness.artifact import Selection
from experimental.curator.raven_adapter.targets import catalogue
from tests.test_harness_curator_generation import (
    Provider,
    context,  # noqa: F401 -- the generation tests' curation context
    diagnosis,
    instructions,
    packet,
    plan,
    response,
    selection,
)
from tests.test_harness_curator_workflow import worker  # noqa: F401 -- a worker the workflow can curate


def names(request) -> set[str]:
    return {entry["function"]["name"] for entry in request["tools"]}


def test_what_must_be_diagnosed_is_every_input_of_the_curation_or_the_task_alone():
    assert subjects(None) == ("task",) and subjects({"source": "human", "text": "Not good."}) == ("task",)
    root = {
        "requirements": [{"id": "R1"}, {"id": ""}, {"id": "R1"}],
        "signals": [
            {"attachments": [{"name": "brand-design-guide", "kind": "norm", "files": []}]},
            {"attachments": ["uploads/price-list/SKILL.md"]},
        ],
    }
    assert subjects(root) == ("R1", "R2", "material:brand-design-guide", "material:price-list")
    child = {
        "parent_materials": {},
        "requirements": {"work/step": [{"behavior": "Follow the procedure"}, {"id": "R4"}]},
        "feedback": {"requirements": [{"id": "R2"}]},
    }
    assert subjects(child) == ("node:work/step#1", "R4", "R2")


def test_a_diagnosis_covers_every_required_input_once_with_a_state_from_the_closed_set():
    with pytest.raises(ValueError, match=r"no diagnosis for \['R2'\]"):
        parse(diagnosis("R1"), ("R1", "R2"))
    with pytest.raises(ValueError, match="one diagnosis"):
        Attribution.model_validate({"diagnoses": [*diagnosis("R1")["diagnoses"], *diagnosis("R1")["diagnoses"]]})
    with pytest.raises(ValueError, match="state"):
        Attribution.model_validate({"diagnoses": [{"about": "R1", "state": "somehow"}]})
    extra = parse(diagnosis("R1", "R2", "expectation:round-1"), ("R1", "R2"))
    assert extra.abouts == {"R1", "R2", "expectation:round-1"} and extra.missing(("R3",)) == ["R3"]


def test_selection_grounds_every_target_on_a_diagnosis_and_design_names_each_treatment():
    declaration = Declaration("worker@0", catalogue())
    attribution = parse(diagnosis("R1", "material:sop"), ("R1",))
    accepted = declaration.parse_selection(selection("action.strategy", grounds=("R1", "material:sop")), attribution)
    assert accepted.grounds == {"action.strategy": ("R1", "material:sop")}
    with pytest.raises(ValueError, match="cites no diagnosis"):
        declaration.parse_selection({**selection("action.strategy"), "grounds": {}}, attribution)
    with pytest.raises(ValueError, match=r"not submitted: \['R9'\]"):
        declaration.parse_selection(selection("action.strategy", grounds=("R9",)), attribution)
    with pytest.raises(ValueError, match="not selected"):
        Selection(understanding="u", targets=(), grounds={"action.strategy": ("R1",)})
    assert declaration.parse_selection({"understanding": "keep", "targets": []}, attribution).targets == ()
    chosen = declaration.parse_selection(selection("action.strategy", grounds=("R1",)), attribution)
    untreated = plan("action.strategy")
    untreated["changes"][0].pop("treatment")
    with pytest.raises(ValueError, match="treatment"):
        design.parse(declaration, chosen, untreated)
    change = declaration.plan_schema()["$defs"]["Change"]
    assert "treatment" in change["required"]


@pytest.mark.asyncio
async def test_the_attribution_is_an_exchange_of_its_own_on_the_curators_model(context):
    provider = Provider(
        response("submit_selection", selection("action.strategy")),
        response("read_source", {"name": "loop"}),
        response(NAME, diagnosis("R7")),
        response(NAME, diagnosis()),
    )
    state = await ModelAttributor().attribute(context, provider, model="curator-model")
    assert state.attribution.abouts == {"task"} and state.subjects == ("task",)
    assert state.calls == 4 and state.queries == 2
    assert state.identity["implementation"] == "model" and state.identity["model"] == "curator-model"
    assert state.identity["catalogue"] is False and len(state.identity["prompts"]) == 64
    first = provider.requests[0]
    assert NAME in names(first) and "report_gap" in names(first) and "read_source" in names(first)
    assert not names(first) & {"submit_selection", "submit_plan", "submit_artifact", "check_candidate"}
    assert all(request["model"] == "curator-model" for request in provider.requests)
    assert packet(first)["required_diagnoses"] == ["task"] and "available_targets" not in packet(first)
    text = instructions(first)
    assert "Understand the current task" in text and "Diagnose each input" in text
    assert "# Remaining attribution budget" in first["messages"][-1]["content"]
    assert "Select the necessary" not in text
    errors = [row.get("error") or row.get("result", {}).get("error", "") for row in state.trace]
    assert any("unknown read-only query: submit_selection" in str(error) for error in errors)
    assert any("no diagnosis for ['task']" in str(error) for error in errors)
    alone = Provider(response(NAME, diagnosis()))
    other = await ModelAttributor(model="diagnoser", catalogue=True).attribute(context, alone, model="curator")
    assert alone.requests[0]["model"] == "diagnoser" and "available_targets" in packet(alone.requests[0])
    assert other.identity["model"] == "diagnoser" and other.identity["catalogue"] is True
    assert other.identity["prompts"] == state.identity["prompts"]


@pytest.mark.asyncio
async def test_an_attribution_pauses_on_its_own_budget_and_resumes_with_the_same_attributor(context):
    attributor = ModelAttributor(limits=AttributionLimits(max_calls=1))
    with pytest.raises(AttributionPausedError) as paused:
        await attributor.attribute(context, Provider(response("read_source", {"name": "loop"})), model="m")
    state = paused.value.state
    assert state.calls == 1 and state.queries == 1 and state.attribution is None
    with pytest.raises(ValueError, match="attributor changed"):
        await ModelAttributor(model="other", limits=AttributionLimits(max_calls=2)).attribute(
            context, Provider(), model="m", resume=state
        )
    resumed = Provider(response(NAME, diagnosis()))
    done = await ModelAttributor(limits=AttributionLimits(max_calls=2)).attribute(
        context, resumed, model="m", resume=state
    )
    assert done.calls == 2 and done.attribution.abouts == {"task"}
    assert resumed.requests[0]["messages"][:-1] == state.messages


@pytest.mark.asyncio
async def test_a_diagnosis_refused_on_the_last_call_is_corrected_on_one_more_and_may_say_what_is_left_open(context):
    slipped = {"diagnoses": [{**diagnosis()["diagnoses"][0], "confidence": "partly checked"}]}
    corrected = {"diagnoses": [{**diagnosis()["diagnoses"][0], "uncertain": "Only one of the turns was read."}]}
    provider = Provider(response("read_source", {"name": "loop"}), response(NAME, slipped), response(NAME, corrected))
    done = await ModelAttributor(limits=AttributionLimits(max_calls=2)).attribute(context, provider, model="m")
    assert done.calls == 3 and done.attribution.diagnoses[0].uncertain == "Only one of the turns was read."
    assert "Model calls, including this response: 1\n" in provider.requests[2]["messages"][-1]["content"]
    again = Provider(response(NAME, slipped), response(NAME, slipped), response(NAME, corrected))
    with pytest.raises(AttributionPausedError, match="after 2 calls") as paused:
        await ModelAttributor(limits=AttributionLimits(max_calls=1)).attribute(context, again, model="m")
    assert len(again.requests) == 2
    state = paused.value.state
    with pytest.raises(AttributionPausedError):
        await ModelAttributor(limits=AttributionLimits(max_calls=1)).attribute(
            context, Provider(), model="m", resume=state
        )
    more = Provider(response(NAME, corrected))
    resumed = await ModelAttributor(limits=AttributionLimits(max_calls=3)).attribute(
        context, more, model="m", resume=state
    )
    assert len(more.requests) == 1 and resumed.calls == 3


@pytest.mark.asyncio
async def test_a_revised_prompt_directory_is_another_attributor_version(context, tmp_path):
    for name in PROMPT_FILES:
        (tmp_path / name).write_text((PROMPTS / name).read_text())
    (tmp_path / "diagnose.md").write_text("# Diagnose each input\n\nREVISED_ATTRIBUTION_PROMPT")
    revised = ModelAttributor(prompts=tmp_path)
    assert revised.identity("m")["prompts"] != ModelAttributor().identity("m")["prompts"]
    provider = Provider(response(NAME, diagnosis()))
    done = await revised.attribute(context, provider, model="m")
    assert "REVISED_ATTRIBUTION_PROMPT" in instructions(provider.requests[0])
    with pytest.raises(ValueError, match="attributor changed"):
        await ModelAttributor(limits=AttributionLimits(max_calls=2)).attribute(
            context, Provider(), model="m", resume=done
        )
    (tmp_path / "budget.md").unlink()
    with pytest.raises(ValueError, match=r"lack \['budget.md'\]"):
        ModelAttributor(prompts=tmp_path)


@pytest.mark.asyncio
async def test_a_reported_gap_ends_the_attribution_with_its_question(context):
    provider = Provider(response("report_gap", {"reason": "The owner never said who approves refunds."}))
    with pytest.raises(GapReportedError) as gap:
        await ModelAttributor().attribute(context, provider)
    assert gap.value.stage == "diagnose" and "approves refunds" in gap.value.reason


@pytest.mark.asyncio
async def test_a_supplied_attribution_must_cover_every_input(context):
    supplied = Attribution.model_validate(diagnosis("task"))
    state = await SuppliedAttributor(supplied, by="owner").attribute(context, None)
    assert state.attribution == supplied and state.calls == 0
    assert state.identity["implementation"] == "supplied" and state.identity["by"] == "owner"
    with pytest.raises(ValueError, match="no diagnosis for"):
        await SuppliedAttributor(Attribution.model_validate(diagnosis("R1"))).attribute(context, None)


@pytest.mark.asyncio
async def test_a_generation_starts_from_its_attribution_and_its_reads_and_keeps_them(context):
    attributed = Attributed(attribution=Attribution.model_validate(diagnosis()), identity={"implementation": "x"})
    investigation = [{"stage": "diagnose", "event": "query", "tool": "read_source", "result": {"text": "read"}}]
    provider = Provider(
        response("submit_selection", selection("action.strategy")),
        response("submit_plan", plan("action.strategy")),
        response("submit_artifact", {"values": {"action.strategy": {"factory": "rules:policy_0_2"}}}),
    )

    async def validate(candidate):
        return Validation([], [])

    result = await generate(context, provider, attribution=attributed, investigation=investigation, validate=validate)
    assert result.candidate.attribution == attributed and result.trace[0] == investigation[0]
    assert packet(provider.requests[0])["diagnosis"]["diagnoses"][0]["about"] == "task"
    assert packet(provider.requests[0])["history"][0]["result"]["text"] == "read"
    assert "Select the necessary" in instructions(provider.requests[0])
    paused = Provider(response("read_source", {"name": "loop"}))
    from experimental.curator.generation.run import GenerationPausedError, Limits

    with pytest.raises(GenerationPausedError) as stopped:
        await generate(context, paused, attribution=attributed, validate=validate, limits=Limits(max_calls=1))
    other = Attributed(attribution=Attribution.model_validate(diagnosis("task", "R1")))
    with pytest.raises(ValueError, match="attribution changed"):
        await generate(context, Provider(), attribution=other, validate=validate, resume=stopped.value.state)


@pytest.mark.asyncio
async def test_a_curation_records_its_attribution_on_its_own_and_uses_a_supplied_one_as_is(worker):  # noqa: F811
    provider = Provider(
        response(NAME, diagnosis()),
        response("submit_selection", selection("action.strategy")),
        response("submit_plan", plan("action.strategy")),
        response("submit_artifact", {"values": {"action.strategy": {"factory": "rules:policy_0_2"}}}),
    )
    result = await workflow.improve(worker, provider, model="curator-model")
    (recorded,) = list((worker.root / "attribution").glob("*.json"))
    body = json.loads(recorded.read_text())
    assert body["identity"]["implementation"] == "model" and body["identity"]["model"] == "curator-model"
    assert body["subjects"] == ["task"] and body["attribution"]["diagnoses"][0]["about"] == "task"
    assert body["calls"] == 1 and len(body["request"]) == 4
    assert result.candidate.attribution.record == recorded.name
    (curation,) = [json.loads(path.read_text()) for path in (worker.root / "curation").glob("*.json")]
    assert curation["attribution"] == recorded.name and curation["attributor"]["implementation"] == "model"
    installed = worker.install.await_args.args[0]
    assert installed.attribution.identity["model"] == "curator-model"
    supplied = Attribution.model_validate(diagnosis())
    again = Provider(
        response("submit_selection", selection("action.strategy")),
        response("submit_plan", plan("action.strategy")),
        response("submit_artifact", {"values": {"action.strategy": {"factory": "rules:policy_0_2"}}}),
    )
    taken = await workflow.improve(worker, again, attribution=supplied)
    assert taken.candidate.attribution.attribution == supplied
    assert taken.candidate.attribution.identity["implementation"] == "supplied"
    assert len(again.requests) == 3 and "submit_selection" in names(again.requests[0])
    assert all(NAME not in names(request) for request in again.requests)


@pytest.mark.asyncio
async def test_a_paused_attribution_is_the_curations_checkpoint_and_resumes_there(worker):  # noqa: F811
    attributor = ModelAttributor(limits=AttributionLimits(max_calls=1))
    with pytest.raises(AttributionPausedError):
        await workflow.improve(worker, Provider(response("read_source", {"name": "task"})), attributor=attributor)
    pending = json.loads((worker.root / "curation/pending.json").read_text())
    assert "attribution_state" in pending and "state" not in pending
    (paused,) = [json.loads(path.read_text()) for path in (worker.root / "attribution").glob("*.json")]
    assert "paused" in paused and "attribution" not in paused
    resumed = Provider(
        response(NAME, diagnosis()),
        response("submit_selection", selection("action.strategy")),
        response("submit_plan", plan("action.strategy")),
        response("submit_artifact", {"values": {"action.strategy": {"factory": "rules:policy_0_2"}}}),
    )
    result = await workflow.improve(worker, resumed, attributor=ModelAttributor(limits=AttributionLimits(max_calls=2)))
    assert result.candidate.attribution.attribution.abouts == {"task"}
    assert not (worker.root / "curation/pending.json").exists()


@pytest.mark.asyncio
async def test_attributing_alone_records_the_attribution_and_nothing_else(worker):  # noqa: F811
    attributed = await workflow.attribute(worker, Provider(response(NAME, diagnosis())), model="m")
    assert attributed.attribution.abouts == {"task"} and attributed.identity["model"] == "m"
    assert (worker.root / "attribution" / attributed.record).is_file()
    assert not list((worker.root / "curation").glob("*.json")) and not worker.install.await_count


SELECTED = (
    response("submit_selection", selection("action.strategy")),
    response("submit_plan", plan("action.strategy")),
    response("submit_artifact", {"values": {"action.strategy": {"factory": "rules:policy_0_2"}}}),
)


@pytest.mark.asyncio
async def test_a_refused_resume_keeps_the_paused_attribution_and_spends_nothing(worker):  # noqa: F811
    with pytest.raises(AttributionPausedError):
        await workflow.improve(
            worker,
            Provider(response("read_source", {"name": "task"})),
            attributor=ModelAttributor(limits=AttributionLimits(max_calls=1)),
        )
    pending = worker.root / "curation/pending.json"
    workspace = Path(json.loads(pending.read_text())["workspace"])
    untouched = Provider()
    with pytest.raises(ValueError, match="attributor changed"):
        await workflow.improve(
            worker, untouched, attributor=ModelAttributor(model="other", limits=AttributionLimits(max_calls=2))
        )
    with pytest.raises(AttributionPausedError):
        await workflow.improve(worker, untouched, attributor=ModelAttributor(limits=AttributionLimits(max_calls=1)))
    assert pending.is_file() and workspace.is_dir() and not untouched.requests
    progress = json.loads((worker.root / "progress/curation.json").read_text())
    assert progress["stage"] == "diagnose" and progress["calls"] == 1 and progress["finished"] is True


@pytest.mark.asyncio
async def test_a_paused_generation_resumes_only_on_the_attribution_it_started_from(worker):  # noqa: F811
    with pytest.raises(GenerationPausedError):
        await workflow.improve(
            worker,
            Provider(response(NAME, diagnosis()), response("read_source", {"name": "task"})),
            limits=Limits(max_calls=1),
        )
    pending = worker.root / "curation/pending.json"
    untouched = Provider()
    supplied = Attribution.model_validate(diagnosis())
    with pytest.raises(ValueError, match="attribution or its attributor changed"):
        await workflow.improve(worker, untouched, attribution=supplied, limits=Limits(max_calls=4))
    with pytest.raises(ValueError, match="attribution or its attributor changed"):
        await workflow.improve(worker, untouched, attributor=ModelAttributor(model="other"), limits=Limits(max_calls=4))
    with pytest.raises(ValueError, match="paused generation is pending"):
        await workflow.attribute(worker, untouched)
    assert pending.is_file() and not untouched.requests
    result = await workflow.improve(
        worker, Provider(*SELECTED), attributor=ModelAttributor(), limits=Limits(max_calls=4)
    )
    assert result.candidate.attribution.identity["implementation"] == "model"


@pytest.mark.asyncio
async def test_attributing_alone_continues_its_own_pause_and_hands_its_result_to_a_curation(worker):  # noqa: F811
    with pytest.raises(AttributionPausedError):
        await workflow.attribute(
            worker,
            Provider(response("read_source", {"name": "task"})),
            attributor=ModelAttributor(limits=AttributionLimits(max_calls=1)),
        )
    attributed = await workflow.attribute(
        worker, Provider(response(NAME, diagnosis())), attributor=ModelAttributor(limits=AttributionLimits(max_calls=2))
    )
    assert attributed.attribution.abouts == {"task"} and not (worker.root / "curation/pending.json").exists()
    taken = await workflow.improve(worker, Provider(*SELECTED), attribution=attributed)
    identity = taken.candidate.attribution.identity
    assert identity["implementation"] == "supplied"
    assert identity["origin"] == {"identity": attributed.identity, "record": attributed.record}
    bodies = [json.loads(path.read_text()) for path in (worker.root / "attribution").glob("*.json")]
    assert len(bodies) == 3 and len({body["input_key"] for body in bodies}) == 1
    assert len({body["input_id"] for body in bodies}) == 2 and all(body["revision"] for body in bodies)


@pytest.mark.asyncio
async def test_an_attribution_that_reports_a_gap_is_recorded_with_what_it_attributed(worker):  # noqa: F811
    with pytest.raises(GapReportedError):
        await workflow.improve(worker, Provider(response("report_gap", {"reason": "No refund policy was given."})))
    (body,) = [json.loads(path.read_text()) for path in (worker.root / "attribution").glob("*.json")]
    assert body["subjects"] == ["task"] and body["calls"] == 1 and len(body["request"]) == 4
    assert "No refund policy" in body["error"] and body["input_key"] and body["revision"]


def test_an_attributor_version_is_everything_its_request_is_written_from(tmp_path, monkeypatch):
    from experimental.curator.attribution import model

    before = ModelAttributor().identity("m")
    shared = [tmp_path / path.name for path in model.prompt_files()]
    for source, copy in zip(model.prompt_files(), shared, strict=True):
        copy.write_text(source.read_text() + "\nREVISED")
    monkeypatch.setattr(model, "prompt_files", lambda: shared)
    assert ModelAttributor().identity("m")["prompts"] != before["prompts"]

    class Defaulting(Provider):
        def get_default_model(self):
            return "provider-default"

    assert model.effective_model(Defaulting(), None) == "provider-default"
    assert model.effective_model(Defaulting(), "named") == "named" and model.effective_model(Provider(), None) is None
