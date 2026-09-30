"""The scenario reads cleanly, the owner plays drill cards, judges the drills and speaks to the Curator."""

import hashlib
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from experimental.automation.employee import AREA, HOME, hire, skills, starting_harness, withheld
from experimental.automation.traveller import Traveller
from experimental.curator.raven_adapter.exploration import _REPOSITORY, _SOURCE_PATHS, Exploration
from experimental.curator.raven_adapter.worker import Execution
from experimental.iteration.compartment import Boundaries, Guard, GuardedFactory
from experimental.iteration.exchange import ExchangeError
from experimental.iteration.protocols import Exchange
from experimental.scenario.sealed import Sealed
from experimental.simulation.__main__ import CHAINS, settings
from experimental.simulation.agency import NAME as REVIEW
from experimental.simulation.agency import Agency
from experimental.simulation.record import PLACEHOLDERS
from experimental.simulation.scenario import BUNDLED, Scenario
from raven.config.schema import Config
from raven.contracts.llm_provider import LLMResponse, ToolCallRequest

TRAVEL = BUNDLED / "travel_agency"


class Provider:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    async def chat_with_retry(self, messages=None, tools=None, model=None, **kwargs):
        given = {"messages": messages, "tools": tools, "model": model}
        self.requests.append({**{key: value for key, value in given.items() if value is not None}, **kwargs})
        return self.responses.pop(0)


def response(name, arguments):
    return LLMResponse(content=None, tool_calls=[ToolCallRequest(name, name, arguments)])


def exchange(user, reply):
    records = [{"kind": "runner.event", "event_type": "Text", "event": {"content": reply}}]
    return Exchange(user, Execution("t1", [], records, {}, "artifact-1"))


def verdicts(scenario, **overrides):
    rows = [{"id": criterion.id, "result": "pass"} for criterion in scenario.criteria]
    for row in rows:
        row.update(overrides.get(row["id"], {}))
    return rows


def test_bundled_scenario_reads_profile_materials_personas_and_criteria():
    scenario = Scenario.load(TRAVEL)
    assert scenario.profile and "#D9531E" in scenario.text("brand-design-guide")
    assert (scenario.materials["brand-design-guide"] / "brand-kit.pptx").is_file()
    assert (scenario.materials["plan-deck-template"] / "template.pptx").is_file()
    assert set(scenario.materials) == {
        "service-sop",
        "price-list",
        "value-package",
        "comfort-package",
        "premium-package",
        "booking-policy",
        "consultation-scripts",
        "plan-deck-spec",
        "brand-design-guide",
        "plan-deck-template",
        "plan-deck-sample",
        "handover-ticket",
    }
    assert [persona.name for persona in scenario.personas] == [
        "family",
        "premium",
        "professional",
        "returning",
        "student",
    ]
    assert all(persona.text for persona in scenario.personas)
    assert len({criterion.id for criterion in scenario.criteria}) == len(scenario.criteria) == 17
    assert {"intake-and-confirmation", "deck-facts-researched"} <= {
        criterion.id for criterion in scenario.criteria if criterion.severity == "red_line"
    }
    assert "brand-design-guide" not in scenario.initial and len(scenario.initial) == 11
    assert "19,000" in scenario.text("price-list")
    assert Scenario.load(TRAVEL.parent.parent / "nowhere" / "travel_agency").root == TRAVEL


def test_load_rejects_repeated_ids_and_unknown_materials(tmp_path):
    root = tmp_path / "scenario"
    shutil.copytree(TRAVEL, root)
    spec = json.loads((root / "scenario.json").read_text())
    spec["initial"] = ["brochure"]
    (root / "scenario.json").write_text(json.dumps(spec))
    with pytest.raises(ValueError, match="brochure"):
        Scenario.load(root)
    spec["initial"] = []
    renamed, spec["criteria"][1]["id"] = spec["criteria"][1]["id"], spec["criteria"][0]["id"]
    (root / "scenario.json").write_text(json.dumps(spec))
    with pytest.raises(ValueError, match=renamed):
        Scenario.load(root)
    declared = json.loads((root / "contract.json").read_text())
    declared["checks"].pop(renamed)
    (root / "contract.json").write_text(json.dumps(declared))
    with pytest.raises(ValueError, match="repeat"):
        Scenario.load(root)


async def test_traveller_speaks_in_plain_text_and_leaves_with_the_word_leave():
    scenario = Scenario.load(TRAVEL)
    student = next(persona for persona in scenario.personas if persona.name == "student")
    provider = Provider(
        LLMResponse(content="Hi, three of us want a cheap trip to Edinburgh in June."),
        LLMResponse(content="LEAVE."),
        LLMResponse(content=""),
        LLMResponse(content="Thanks, that is all.\nLEAVE"),
        LLMResponse(content="Great, see you LEAVE."),
        LLMResponse(content="Error: boom", finish_reason="error"),
    )
    traveller = Traveller(student, provider, model="sim")
    assert traveller.name == "student"
    assert await traveller.speak([]) == "Hi, three of us want a cheap trip to Edinburgh in June."
    exchanges = [exchange("Hi", "Welcome to Harbourlight. What is your budget?")]
    assert await traveller.speak(exchanges) is None
    assert await traveller.speak(exchanges) is None and len(provider.requests) == 2
    first = traveller.card
    assert await traveller.speak([]) is None
    assert await traveller.speak([]) == "Thanks, that is all."
    assert await traveller.speak(exchanges) is None and len(provider.requests) == 4
    assert await traveller.speak([]) == "Great, see you"
    with pytest.raises(ExchangeError, match="traveller:student: provider error"):
        await traveller.speak([])
    packet = json.loads(provider.requests[1]["messages"][1]["content"])
    assert packet["persona"] == first.text and first.trip.phone in packet["persona"]
    assert packet["conversation"] == [{"customer": "Hi", "assistant": "Welcome to Harbourlight. What is your budget?"}]
    assert provider.requests[1]["model"] == "sim" and "tools" not in provider.requests[1]


async def test_the_customer_and_the_owner_speak_in_their_compartments_where_the_partners_words_are_its_own(tmp_path):
    from dataclasses import replace

    scenario = Scenario.load(TRAVEL)
    student = next(persona for persona in scenario.personas if persona.name == "student")
    secret = "The owner keeps a private margin table for every package that no customer may ever hear about."
    log = tmp_path / "boundaries.jsonl"
    boundaries = Boundaries({"conversant": Sealed.of([secret]), "party": Sealed.of([secret])}, log=log)
    told = [exchange("Hi", f"A note from us: {secret}")]
    customer = Traveller(student, Provider(LLMResponse(content="Fine, thanks.")), boundaries=boundaries)
    assert await customer.speak(told) == "Fine, thanks."
    leaking = Traveller(replace(student, text=f"{student.text}\n{secret}"), Provider(), boundaries=boundaries)
    with pytest.raises(ExchangeError, match="BoundaryError"):
        await leaking.speak([])
    provider = Provider(response(REVIEW, {"verdicts": verdicts(scenario), "remark": "All good."}))
    agency = Agency(scenario, provider, tmp_path / "skills", workdir=tmp_path, deliver="pool", boundaries=boundaries)
    agency.prepare()
    assert (await agency.evaluate({"student": told})).satisfied is True
    sealed_material = Boundaries({"party": Sealed.of([scenario.text("brand-design-guide")])}, log=log)
    owner = Agency(
        scenario, Provider(), tmp_path / "skills", workdir=tmp_path, deliver="pool", boundaries=sealed_material
    )
    owner.prepare()
    with pytest.raises(ExchangeError, match="party compartment"):
        await owner.evaluate({"student": told})
    rows = [json.loads(line) for line in log.read_text().splitlines()]
    assert {("conversant", "enter"), ("conversant", "leave"), ("party", "enter"), ("party", "leave")} <= {
        (row["role"], row["event"]) for row in rows
    }
    assert [row["role"] for row in rows if row["event"] == "violation"] == ["conversant", "party"]


async def test_agency_judges_every_criterion_and_hands_over_the_material_of_a_failed_check(tmp_path):
    scenario = Scenario.load(TRAVEL)
    skills = tmp_path / "skills"
    (skills / "brand-design-guide").mkdir(parents=True)
    (skills / "unrelated").mkdir()
    failing = verdicts(
        scenario,
        **{
            "quote-sheet-correct": {
                "result": "fail",
                "session": "student",
                "actual": "About 300 each.",
                "note": "Read the list.",
            }
        },
    )
    provider = Provider(
        response(
            REVIEW,
            {"verdicts": failing, "remark": "It made a price up for Mia.", "handover": ["brand-design-guide"]},
        ),
        response(REVIEW, {"verdicts": verdicts(scenario), "remark": "All good today."}),
    )
    agency = Agency(
        scenario,
        provider,
        skills,
        workdir=tmp_path,
        deliver="pool",
        records=tmp_path / "run",
        model="sim",
    )
    agency.prepare()
    assert sorted(path.name for path in skills.iterdir()) == sorted([*scenario.initial, "unrelated"])
    sessions = {"student": [exchange("Cheap trip?", "About 300 each.")]}

    signal = await agency.evaluate(sessions)
    assert signal.source == "agency" and signal.satisfied is False
    assert signal.text == "It made a price up for Mia."
    assert (skills / "brand-design-guide" / "SKILL.md").is_file()
    assert signal.items == () and signal.metrics == {}
    (kept,) = [json.loads(path.read_text()) for path in (tmp_path / "run" / "analysis").glob("*.json")]
    assert {item["id"] for item in kept["scorecard"]["items"]} == {criterion.id for criterion in scenario.criteria}
    failed = next(item for item in kept["scorecard"]["items"] if item["result"] == "fail")
    assert (
        failed["session"] == "student" and failed["actual"] == "About 300 each." and "price list" in failed["expected"]
    )
    packet = json.loads(provider.requests[0]["messages"][1]["content"])
    assert packet["conversations"] == {"student": [{"customer": "Cheap trip?", "assistant": "About 300 each."}]}
    assert packet["your_earlier_reviews"] == [] and packet["research"] == {}
    assert "curator_reply" not in packet
    assert {row["severity"] for row in packet["criteria"]} == {"red_line", "standard"}
    assert set(packet["materials"]) == set(scenario.materials) and packet["deliverables"] == {}
    assert packet["given_to_the_assistant"] == list(scenario.initial) and packet["withheld"] == ["brand-design-guide"]

    signal = await agency.evaluate(sessions)
    assert signal.satisfied is True and signal.text == "All good today."
    assert agency.released == [*scenario.initial, "brand-design-guide"]
    earlier = json.loads(provider.requests[1]["messages"][1]["content"])["your_earlier_reviews"]
    assert earlier == [
        {
            "round": 1,
            "remark": "It made a price up for Mia.",
            "failed": ["quote-sheet-correct"],
            "waiting_on_material": [],
            "handed_over": ["brand-design-guide"],
        }
    ]


async def test_in_a_dialog_the_owner_uploads_its_opening_materials_and_pastes_later_ones(tmp_path):
    scenario = Scenario.load(TRAVEL)
    skills, uploads = tmp_path / "home" / "skills", tmp_path / "home" / "uploads"
    failing = verdicts(
        scenario,
        **{
            "deck-aesthetics": {
                "result": "fail",
                "session": "student",
                "note": "Too busy.",
                "waits_on": "brand-design-guide",
            }
        },
    )
    provider = Provider(
        response(REVIEW, {"verdicts": failing, "remark": "Slides are too busy.", "handover": ["brand-design-guide"]})
    )
    shared = tmp_path / "work" / "uploads"
    agency = Agency(scenario, provider, skills, workdir=tmp_path, uploads=uploads, shared=shared)
    agency.prepare()
    assert not skills.exists() or not any(skills.iterdir())
    for place in (uploads, shared):
        assert (place / "service-sop" / "SKILL.md").read_bytes() == (
            scenario.materials["service-sop"] / "SKILL.md"
        ).read_bytes()
        assert (place / "plan-deck-template" / "template.pptx").is_file()
        assert not (place / "brand-design-guide").exists()
    (opening,) = agency.opening()
    handed = {item.name: item for item in opening.attachments}
    assert "uploads/service-sop/SKILL.md" in handed["service-sop"].files and handed["service-sop"].kind == "norm"
    assert "uploads/plan-deck-template/template.pptx" in handed["plan-deck-template"].files
    assert handed["plan-deck-template"].kind == "fact"
    assert "- uploads/price-list/SKILL.md\n" in opening.text and "{files}" not in opening.text
    signal = await agency.evaluate({"student": [exchange("Cheap trip?", "Here is the deck.")]})
    assert (
        signal.text.startswith("Slides are too busy.")
        and scenario.document("brand-design-guide").strip() in signal.text
    )
    assert "name: brand-design-guide" not in signal.text and not (skills / "brand-design-guide").exists()
    assert agency.released[-1] == "brand-design-guide"
    assert Agency(scenario, provider, skills, workdir=tmp_path, deliver="pool").opening() == ()
    with pytest.raises(ValueError, match="uploads folder"):
        Agency(scenario, provider, skills, workdir=tmp_path)


async def test_on_a_fixed_partition_the_plan_hands_materials_over_whatever_the_owner_picks(tmp_path):
    """The second step carries the deck template, whose binary file reaches the uploads folder beside its text."""
    scenario = Scenario.load(TRAVEL)
    everything = list(scenario.materials)
    index = everything.index("plan-deck-template")
    steps = (tuple(everything[:index]), tuple(everything[index : index + 2]), tuple(everything[index + 2 :]))
    skills, uploads = tmp_path / "home" / "skills", tmp_path / "home" / "uploads"
    reviews = [
        {"verdicts": verdicts(scenario), "remark": "Here is more.", "handover": [everything[-1]]},
        {"verdicts": verdicts(scenario), "remark": "And the rest."},
    ]
    provider = Provider(*(response(REVIEW, review) for review in reviews))
    agency = Agency(
        scenario,
        provider,
        skills,
        workdir=tmp_path,
        disclosure=scenario.disclosure(steps, rounds=4),
        deliver="dialog",
        uploads=uploads,
    )
    agency.prepare()
    assert agency.released == list(steps[0]) and not agency.chooses
    sessions = {"student": [exchange("Cheap trip?", "Here.")]}
    first = await agency.evaluate(sessions)
    packet = json.loads(provider.requests[0]["messages"][1]["content"])
    assert packet["handing_over_now"] == list(steps[1]) and packet["you_choose_handover"] is False
    assert agency.released == [*steps[0], *steps[1]]
    assert all(scenario.document(name).strip() in first.text for name in steps[1])
    for name in steps[1]:
        assert (uploads / name / "SKILL.md").read_bytes() == (scenario.materials[name] / "SKILL.md").read_bytes()
        assert f"uploads/{name}/SKILL.md" in [path for item in first.attachments for path in item.files]
        assert f"- uploads/{name}/SKILL.md" in first.text
    assert "{files}" not in first.text
    await agency.evaluate(sessions)
    assert agency.released == everything and agency.withheld == []


async def test_by_need_the_owner_chooses_and_the_rest_comes_before_the_last_round(tmp_path):
    scenario = Scenario.load(TRAVEL)
    skills = tmp_path / "skills"
    remaining = [name for name in scenario.materials if name not in scenario.initial]
    provider = Provider(*(response(REVIEW, {"verdicts": verdicts(scenario), "remark": "ok"}) for _ in range(2)))
    agency = Agency(
        scenario, provider, skills, workdir=tmp_path, disclosure=scenario.disclosure("staged", rounds=3), deliver="pool"
    )
    agency.prepare()
    sessions = {"student": [exchange("Cheap trip?", "Here.")]}
    await agency.evaluate(sessions)
    assert agency.withheld == remaining and agency.chooses
    await agency.evaluate(sessions)
    packets = [json.loads(request["messages"][1]["content"]) for request in provider.requests]
    assert packets[0]["handing_over_now"] == [] and packets[1]["handing_over_now"] == remaining
    assert agency.withheld == [] and all((skills / name / "SKILL.md").is_file() for name in remaining)


def test_the_starting_harness_fingerprint_changes_only_when_a_products_files_do(tmp_path):
    product = tmp_path / "agents" / "raven-ppt"
    (product / "__pycache__").mkdir(parents=True)
    (product / "run.py").write_text("print('deck')")
    first = starting_harness(tmp_path)
    (product / "__pycache__" / "run.cpython.pyc").write_bytes(b"cache")
    assert starting_harness(tmp_path)["products"] == first["products"]
    (product / "run.py").write_text("print('deck v2')")
    assert starting_harness(tmp_path)["products"]["raven-ppt"] != first["products"]["raven-ppt"]
    assert first["raven_commit"] is None and first["raven_modified"] is False
    assert first["raven_diff"] == hashlib.sha256(b"").hexdigest()


def test_every_chain_names_a_valid_way_to_cultivate_and_settings_carry_no_credential(tmp_path):
    for chain in CHAINS.values():
        assert chain["deliver"] == "dialog" and chain["disclose"] in ("all", "staged", *Scenario.load(TRAVEL).plans)
    config = tmp_path / "config.json"
    args = SimpleNamespace(
        argv=[f"--config={config}", "--chain", "staged", "--home", str(tmp_path / "home"), "--seed", "7"],
        chain="staged",
        scenario=TRAVEL,
        deliver="dialog",
        disclose="staged",
        curator="improve",
        targets="all",
        rounds=4,
        turns=14,
        repeats=1,
        cards=["family"],
        concurrent_drills=3,
        seed=7,
        without=["plan-deck-sample"],
        curator_model="z-ai/glm-5.3",
        analyst_model=None,
        simulation_model=None,
        traveller_model="deepseek/deepseek-flash",
        subagent_model="z-ai/glm-5.3-flashx",
        curator_effort="high",
        simulation_effort="low",
        traveller_effort="low",
        config=config,
        home=tmp_path / "home",
    )
    (tmp_path / "home" / "playbooks" / "plan").mkdir(parents=True)
    (tmp_path / "home" / "playbooks" / "plan" / "playbook.md").write_text("spec")
    (tmp_path / "home" / "sessions").mkdir()
    (tmp_path / "home" / "sessions" / "old.jsonl").write_text("{}")
    written = settings(args, "z-ai/glm-5.3-flashx", "low", "medium")
    assert written["efforts"] == {
        "employee": "low",
        "employee_tier": "medium",
        "curator": "high",
        "simulation": "low",
        "traveller": "low",
    }
    assert written["baseline"] == {"playbooks/plan/playbook.md": hashlib.sha256(b"spec").hexdigest()}
    start = written["starting_harness"]
    assert {"raven-research", "raven-ppt"} <= set(start["products"]) and start["raven_commit"]
    assert written["chain"] == "staged" and written["scenario"] == "travel_agency"
    assert written["argv"] == [
        f"--config={PLACEHOLDERS['--config']}",
        "--chain",
        "staged",
        "--home",
        str(tmp_path / "home"),
        "--seed",
        "7",
    ]
    assert written["seed"] == 7 and written["without"] == ["plan-deck-sample"] and written["concurrent_drills"] == 3
    assert written["models"] == {
        "employee": "z-ai/glm-5.3-flashx",
        "curator": "z-ai/glm-5.3",
        "analyst": "z-ai/glm-5.3",
        "attribution": "z-ai/glm-5.3",
        "simulation": "z-ai/glm-5.3",
        "traveller": "deepseek/deepseek-flash",
        "subagents": "z-ai/glm-5.3-flashx",
    }
    assert written["attribution_catalogue"] is False
    assert str(config) not in json.dumps(written)


def owner(tmp_path, provider, **options):
    """The agency as the loop's assessor, recording beside a run, with a dialog handover into its own uploads."""
    scenario = Scenario.load(TRAVEL)
    home = tmp_path / "home"
    agency = Agency(
        scenario,
        provider,
        home / "skills",
        workdir=tmp_path / "work",
        deliver="dialog",
        uploads=home / "uploads",
        records=tmp_path / "run",
        **options,
    )
    agency.prepare()
    return scenario, agency


def scorecard(scenario, failed=(), waits=None, handover=(), remark="The price was guessed again."):
    rows = [
        {"id": criterion.id, "result": "fail" if criterion.id in failed else "pass", "session": "student"}
        for criterion in scenario.criteria
    ]
    for row in rows:
        row["waits_on"] = (waits or {}).get(row["id"])
    return {"verdicts": rows, "remark": remark, "handover": list(handover)}


async def test_the_owner_keeps_a_scorecard_and_hands_over_what_a_miss_waits_on(tmp_path):
    """The owner's verdicts stay on a scorecard of its own beside the run's analyses; its signal carries only its
    words, what it hands over, and whether it is satisfied. It never writes the Curator's requirements."""
    from experimental.analyst.role import Analyst

    scenario = Scenario.load(TRAVEL)
    quote, deck = "quote-sheet-correct", "deck-aesthetics"
    waits = {deck: "brand-design-guide"}
    provider = Provider(
        response(REVIEW, scorecard(scenario, {quote}, waits)),
        response(REVIEW, scorecard(scenario, {quote, deck}, waits)),
        response(REVIEW, scorecard(scenario, {quote, deck}, waits, ["brand-design-guide"])),
    )
    scenario, agency = owner(tmp_path, provider, max_calls=4)
    assert not isinstance(agency, Analyst)
    spoken = await agency.evaluate({"student": [exchange("Cheap trip?", "About 300 each.")]})
    errors = [message["content"] for message in provider.requests[2]["messages"] if message["role"] == "tool"]
    assert "only a failed verdict waits on a material" in errors[0]
    assert "hand over 'brand-design-guide'" in errors[1]
    assert spoken.items == () and spoken.metrics == {} and spoken.satisfied is False
    assert spoken.text.startswith("The price was guessed again.")
    assert scenario.document("brand-design-guide").strip() in spoken.text
    assert [(item.name, item.kind) for item in spoken.attachments] == [("brand-design-guide", "norm")]
    assert "uploads/brand-design-guide/SKILL.md" in spoken.attachments[0].files
    assert agency.reviews[0]["waiting_on_material"] == ["brand-design-guide"] and "raised" not in agency.reviews[0]
    (kept,) = [json.loads(path.read_text()) for path in (tmp_path / "run" / "analysis").glob("*.json")]
    assert kept["source"] == "agency" and kept["waiting_on_material"] == waits
    assert {item["id"] for item in kept["scorecard"]["items"]} == {criterion.id for criterion in scenario.criteria}


async def test_a_failed_owner_call_is_recorded_beside_the_analyses(tmp_path):
    provider = Provider(response(REVIEW, {"verdicts": [], "remark": ""}))
    scenario, agency = owner(tmp_path, provider, max_calls=1)
    with pytest.raises(ExchangeError, match="budget"):
        await agency.evaluate({"student": [exchange("Cheap trip?", "Here.")]})
    (record,) = [json.loads(path.read_text()) for path in (tmp_path / "run" / "analysis").glob("*.json")]
    assert record["source"] == "agency" and record["error"]


async def test_agency_sends_back_incomplete_misattributed_or_overreaching_reviews(tmp_path):
    scenario = Scenario.load(TRAVEL)
    partial = verdicts(scenario)[:-1]
    wrong = verdicts(scenario, **{"deck-delivered-and-consistent": {"result": "fail", "session": "ghost"}})
    provider = Provider(
        response(REVIEW, {"verdicts": partial, "remark": "Fine."}),
        response(REVIEW, {"verdicts": wrong, "remark": "Fine."}),
        response(REVIEW, {"verdicts": verdicts(scenario), "remark": "Fine.", "handover": ["price-list"]}),
        response(REVIEW, {"verdicts": verdicts(scenario), "remark": "Fine."}),
    )
    agency = Agency(
        scenario, provider, tmp_path / "skills", workdir=tmp_path, disclosure=scenario.disclosure("all"), deliver="pool"
    )
    agency.prepare()
    assert sorted(agency.released) == sorted(scenario.materials) and agency.withheld == []
    signal = await agency.evaluate({"student": [exchange("Hi", "Hello")]})
    assert signal.satisfied is True
    errors = [json.loads(m["content"])["error"] for m in provider.requests[3]["messages"] if m["role"] == "tool"]
    assert "one verdict per criterion" in errors[0] and "ghost" in errors[1]
    assert "withheld" in errors[2]


async def test_agency_gives_up_within_its_call_budget(tmp_path):
    scenario = Scenario.load(TRAVEL)
    provider = Provider(*(response(REVIEW, {"verdicts": [], "remark": ""}) for _ in range(2)))
    agency = Agency(scenario, provider, tmp_path / "skills", workdir=tmp_path, deliver="pool", max_calls=2)
    with pytest.raises(ExchangeError, match="budget"):
        await agency.evaluate({})
    handed = tmp_path / "handed"
    shutil.copytree(TRAVEL, handed)
    spec = json.loads((handed / "scenario.json").read_text())
    (handed / "scenario.json").write_text(json.dumps({key: value for key, value in spec.items() if key != "plans"}))
    (handed / "materials" / "expert-profile").mkdir()
    (handed / "materials" / "expert-profile" / "profile.md").write_text("# The expert\nRules as written.")
    with pytest.raises(ValueError, match=r"SKILL.md, which \['expert-profile'\] lack"):
        Agency(Scenario.load(handed), provider, tmp_path / "skills", workdir=tmp_path, deliver="pool")
    with pytest.raises(ValueError, match="other materials"):
        Agency(
            scenario.without(["price-list"]),
            provider,
            tmp_path / "skills",
            workdir=tmp_path,
            disclosure=scenario.disclosure("all"),
        )


def test_the_curator_snapshot_does_not_carry_the_scenario_or_the_experiment_docs():
    mounted = [_REPOSITORY / relative for relative in _SOURCE_PATHS]
    hidden = [TRAVEL, _REPOSITORY / "experimental" / "docs", _REPOSITORY / "experimental" / "simulation" / "cases"]
    assert not any(path.is_relative_to(mount) for path in hidden for mount in mounted)
    assert (_REPOSITORY / "experimental" / "curator") in mounted
    showcase = [path for path in (_REPOSITORY / "experimental" / "simulation" / "cases").rglob("*") if path.is_file()]
    assert showcase and not any(path.is_relative_to(mount) for path in showcase for mount in mounted)


def test_a_registered_source_that_climbs_to_the_experimental_package_does_not_widen_the_snapshot(tmp_path):
    """A module under experimental/ resolves its package root to experimental/ itself, which holds the simulation, the
    judges and the showcase; the mount of experimental/curator must keep that root out."""
    repository = tmp_path / "repository"
    for relative, text in {
        "experimental/__init__.py": "",
        "experimental/curator/__init__.py": "",
        "experimental/curator/strategy.py": "def create(): pass\n",
        "experimental/simulation/cases/showcase/transcript/3-round-1.md": "# round 1\n\nquote-sheet-correct: fail\n",
    }.items():
        (repository / relative).parent.mkdir(parents=True, exist_ok=True)
        (repository / relative).write_text(text)
    inspection = SimpleNamespace(
        facts={},
        sources={
            "strategy.create": {
                "path": str(repository / "experimental/curator/strategy.py"),
                "root": str(repository / "experimental"),
                "digest": hashlib.sha256((repository / "experimental/curator/strategy.py").read_bytes()).hexdigest(),
            }
        },
    )
    exploration = Exploration(
        Config(), inspection, repository=repository, source_paths=("experimental/curator",), root=tmp_path / "x"
    )
    assert set(exploration.mounts) == {"source/experimental/curator"}
    assert not (exploration.root / "source" / "experimental" / "simulation").exists()


def test_the_employees_curator_is_kept_from_the_simulation_its_judges_and_the_scenario(tmp_path):
    repository = tmp_path / "repository"
    files = {
        "raven/helper.py": "VALUE = 1\n",
        "tests/test_raven_helper.py": "def test_value(): pass\n",
        "tests/test_simulation_cards.py": "def test_cards(): pass\n",
        "tests/test_analyst_run.py": "def test_run(): pass\n",
        "tests/test_cards_again.py": "from experimental.simulation.cards import draw\n",
        "tests/test_loop.py": "from experimental.iteration.run import run\n",
        "tests/test_named.py": f"SCENARIO = '{TRAVEL.name}'\n",
        "tests/test_scenario_contract.py": "def test_contract(): pass\n",
        "tests/test_assessor_human.py": "def test_human(): pass\n",
        "tests/test_sealed_again.py": "from experimental.scenario.sealed import Sealed\n",
        "tests/test_judging.py": "import experimental.assessor.role\n",
    }
    for relative, text in files.items():
        (repository / relative).parent.mkdir(parents=True, exist_ok=True)
        (repository / relative).write_text(text)
    inspection = SimpleNamespace(facts={}, sources={})
    exploration = Exploration(
        Config(),
        inspection,
        repository=repository,
        source_paths=("raven", "tests"),
        withheld=withheld(Scenario.load(TRAVEL)),
        root=tmp_path / "x",
    )
    assert {path.name for path in (exploration.root / "source" / "tests").iterdir()} == {"test_raven_helper.py"}


def test_the_employee_works_from_its_own_copy_of_the_home(tmp_path):
    scenario = Scenario.load(TRAVEL)
    home = tmp_path / "shared-home"
    (home / "skills" / "brand-design-guide").mkdir(parents=True)
    (home / "skills" / "brand-design-guide" / "personal.txt").write_text("mine")
    (home / "sessions").mkdir()
    (home / "sessions" / "old.jsonl").write_text("{}")
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "providers": {"deepseek": {"api_key": "k"}},
                "agents": {"defaults": {"model": "deepseek/x", "provider": "deepseek"}},
            }
        )
    )
    root = tmp_path / "run"
    contract = scenario.contract
    worker = hire(contract, config, workdir=tmp_path, root=root, home=home, guard=Guard("partner", Sealed.of(["x"])))
    assert worker.withheld == withheld(contract)
    assert isinstance(worker.provider_factory, GuardedFactory) and worker.provider_factory.guard.role == "partner"
    assert hire(contract, config, workdir=tmp_path, root=tmp_path / "plain", home=home).provider_factory is None
    pool = skills(worker)
    assert pool == root / AREA / HOME / "skills" and (pool / "brand-design-guide" / "personal.txt").is_file()
    assert not (root / AREA / HOME / "sessions").exists()
    Agency(scenario, Provider(), pool, workdir=tmp_path, deliver="pool").prepare()
    assert not (pool / "brand-design-guide").exists() and (pool / "service-sop" / "SKILL.md").is_file()
    assert (home / "skills" / "brand-design-guide" / "personal.txt").read_text() == "mine"


def test_the_employee_houses_its_external_subagents_homes_beside_its_own_harness(tmp_path, monkeypatch):
    from experimental.automation import employee
    from raven.config.schema import ThirdPartyAcpSubagentConfig

    def row(name, enabled=True):
        return ThirdPartyAcpSubagentConfig(name=name, kind="acp", command="run", enabled=enabled, env={"A": "1"})

    monkeypatch.setattr(employee, "discover_product_rows", lambda: [row("Raven-PPT"), row("Raven-Research", False)])
    monkeypatch.setenv("PYTHONTZPATH", "/zones")
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "providers": {"deepseek": {"api_key": "k"}},
                "agents": {"defaults": {"model": "deepseek/x", "provider": "deepseek"}},
            }
        )
    )
    worker = hire(Scenario.load(TRAVEL).contract, config, workdir=tmp_path, root=tmp_path / "run")
    rows = {item.name: item for item in worker.baseline.config.subagents.agents}
    housed = tmp_path / "run" / AREA / HOME / "subagents" / "Raven-PPT"
    assert rows["Raven-PPT"].env == {"A": "1", "PYTHONTZPATH": "/zones", "PPT_ACP_HOME": str(housed)}
    assert housed.is_dir() and "Raven-Research" not in rows


def test_the_housed_subagents_run_on_a_model_of_their_own_through_the_employees_provider(tmp_path, monkeypatch):
    from experimental.automation import employee
    from raven.config.schema import ThirdPartyAcpSubagentConfig

    def row(name):
        return ThirdPartyAcpSubagentConfig(name=name, kind="acp", command=f"py /agents/{name}/run.py", enabled=True)

    folder = tmp_path / "product"
    folder.mkdir()
    shipped = {
        "agents": {"defaults": {"model": "vendor/other", "provider": "ppt", "maxTokens": 9, "reasoningEffort": "max"}},
        "providers": {"ppt": {"apiBase": "https://gateway.example/v1"}},
        "acp": {
            "modes": {"medium": {"reasoningEffort": "low"}, "high": {"reasoningEffort": "high"}},
            "defaultMode": "high",
        },
        "tools": {"disabledTools": ["spawn"]},
        "plugins": {"config": {"research-flow": {"verify": {"reasoningEffort": "low", "maxTokens": 16384}}}},
    }
    (folder / "config.json").write_text(json.dumps(shipped))
    monkeypatch.setattr(employee, "discover_product_rows", lambda: [row("Raven-PPT"), row("Raven-Research")])
    monkeypatch.setattr(employee, "product_folder", lambda name: folder)
    settings = {
        "providers": {"deepseek": {"apiKey": "ds-key"}},
        "permissions": {"mode": "full", "judgeTimeoutSeconds": 60},
        "acp": {"defaultMode": "medium"},
        "agents": {
            "defaults": {
                "model": "deepseek/deepseek-flash",
                "provider": "deepseek",
                "reasoningEffort": "low",
                "contextWindowTokens": 1048576,
            }
        },
    }
    config = tmp_path / "config.json"
    config.write_text(json.dumps(settings))
    worker = hire(
        Scenario.load(TRAVEL).contract,
        config,
        workdir=tmp_path,
        root=tmp_path / "run",
        subagent_model="deepseek/deepseek-flash",
    )
    rows = {item.name: item for item in worker.baseline.config.subagents.agents}
    for name, secret in (("Raven-PPT", "PPT_API_KEY"), ("Raven-Research", "RESEARCH_API_KEY")):
        copy = tmp_path / "run" / AREA / "deployment" / f"{name.lower()}.json"
        written = json.loads(copy.read_text())
        assert rows[name].env[secret] == "ds-key" and rows[name].command.endswith(f"--config {copy}")
        assert written["agents"]["defaults"] == {
            "model": "deepseek/deepseek-flash",
            "provider": "deepseek",
            "maxTokens": 9,
            "reasoningEffort": "low",
            "contextWindowTokens": 1048576,
        }
        assert written["providers"]["deepseek"] == {"apiKey": "ds-key"} and copy.stat().st_mode & 0o777 == 0o600
        assert written["permissions"] == {"mode": "full", "judgeTimeoutSeconds": 60.0}
        # The shipped high tier would run every deck call at high effort over the pinned low one.
        assert written["acp"]["defaultMode"] == "medium"
        # A product's shell reaches past the run's bounds, so products run without one.
        assert written["tools"]["disabledTools"] == ["spawn", "ask_user", "exec"]
        # A thinking DeepSeek model refuses the verify gate's forced verdict call, and the gate then passes every draft.
        verify = written["plugins"]["config"]["research-flow"]["verify"]
        assert verify == {"reasoningEffort": "none", "maxTokens": 16384}
    assert "PPT_ACP_HOME" in rows["Raven-PPT"].env
    settings["agents"]["defaults"].pop("reasoningEffort")
    config.write_text(json.dumps(settings))
    with pytest.raises(ValueError, match="reasoning effort"):
        hire(
            Scenario.load(TRAVEL).contract,
            config,
            workdir=tmp_path,
            root=tmp_path / "again",
            subagent_model="deepseek/x",
        )


async def test_the_agency_reads_the_last_version_of_each_delivered_file(tmp_path, monkeypatch):
    from experimental.automation.traveller import opened, transcript
    from experimental.curator.raven_adapter.worker import Execution

    if shutil.which("soffice") is None:
        from pptx import Presentation

        from experimental.automation import files
        from experimental.automation.render import cached

        def draw(file, out, width):
            for number in range(1, len(Presentation(file).slides) + 1):
                (out / f"page-{number:02d}.png").write_bytes(b"png")

        monkeypatch.setattr(files, "cached", lambda file, cache, width: cached(file, cache, width, draw))
    scenario = Scenario.load(TRAVEL)
    first, second = tmp_path / "t1" / "trip.html", tmp_path / "t2" / "trip.html"
    final = '<style>h1{color:red}</style><h1>final</h1><img src="data:image/png;base64,' + "A" * 300 + '">'
    for path, text in ((first, "<h1>draft</h1>"), (second, final)):
        path.parent.mkdir()
        path.write_text(text)
    deck = tmp_path / "t3" / "plan.pptx"
    deck.parent.mkdir()
    shutil.copy(scenario.materials["plan-deck-template"] / "template.pptx", deck)
    records = [{"kind": "runner.event", "event_type": "Text", "event": {"content": "Here it is."}}]
    exchanges = [
        Exchange("Plan it", Execution("t1", [], records, {}, "a", (str(first),))),
        Exchange("Fix it", Execution("t2", [], records, {}, "a", (str(second),))),
        Exchange("The deck?", Execution("t3", [], records, {}, "a", (str(deck),))),
    ]
    provider = Provider(response(REVIEW, {"verdicts": verdicts(scenario), "remark": "Good page."}))
    await Agency(scenario, provider, tmp_path / "skills", workdir=tmp_path, deliver="pool").evaluate(
        {"student": exchanges}
    )
    packet = json.loads(provider.requests[0]["messages"][1]["content"])
    delivered = packet["deliverables"]["student"]
    assert packet["references"]["student"]["deck"]["template_placeholders_left"]
    assert delivered["trip.html"] == "final"
    assert (
        delivered["plan.pptx"].startswith("19 slides, aspect 1.78") and "[style] background" in delivered["plan.pptx"]
    )
    assert packet["deck_pages"] == {"student": {"plan.pptx": 19}}
    pictures = provider.requests[0]["messages"][2]["content"]
    images = [part for part in pictures if part["type"] == "image_url"]
    assert len(images) == 19 and images[0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert (deck.parent / "plan.pptx.thumbs" / "page-01.png").is_file()
    assert transcript(exchanges)[0]["delivered"] == ["trip.html"] and "stopped" not in transcript(exchanges)[0]
    late = Execution("t9", [], [], {"timed_out": True, "timeout": 600, "explicit_reply": False})
    assert transcript([Exchange("Hello?", late)])[0]["stopped"] == "no reply within 600 seconds; the turn was stopped"
    seen = opened(exchanges)
    assert seen["trip.html"] == "final" and "--- slide 1\n" in seen["plan.pptx"] and "[style]" not in seen["plan.pptx"]


def test_the_agency_reads_what_the_research_colleague_reported_in_each_playbook_run(tmp_path):
    from experimental.curator.raven_adapter.worker import Execution
    from experimental.simulation.agency import research

    found, drafted = tmp_path / "research.out.md", tmp_path / "brief.out.md"
    found.write_text("G7311 Shanghai to Huangshan, 3h (source: 12306)")
    drafted.write_text("brief")
    manifest = {
        "files": [
            {"node": "p-research", "subagent": "Raven-Research", "output_file": str(found)},
            {"node": "p-brief", "subagent": "Raven", "output_file": str(drafted)},
        ]
    }
    records = [{"kind": "dag.progress", "name": "dag_run_completed", "payload": {"manifest": manifest}}]
    exchanges = [Exchange("Deck please", Execution("t1", [], records, {}, "a"))]
    assert research(exchanges) == {"p-research": "G7311 Shanghai to Huangshan, 3h (source: 12306)"}


async def test_the_owner_gets_the_played_card_and_its_figures_and_still_decides_every_verdict(tmp_path):
    from experimental.simulation.cards import Drawn, Trip

    scenario = Scenario.load(TRAVEL)
    sheet = scenario.text("service-sop").split("```")[1].strip()
    guest = Trip("guest", "origin", "somewhere", (12, 2), (12, 6), 4, 4, (), (), 20_000, "139 0571 6628")
    card = Drawn("student", "card text", guest)
    provider = Provider(response(REVIEW, {"verdicts": verdicts(scenario), "remark": "Fine."}))
    agency = Agency(
        scenario,
        provider,
        tmp_path / "skills",
        workdir=tmp_path,
        disclosure=scenario.disclosure("all"),
        deliver="pool",
        cards=lambda: {"student": card},
        records=tmp_path / "records",
    )
    agency.prepare()
    signal = await agency.evaluate({"student": [exchange("Quote please", sheet)]})
    packet = json.loads(provider.requests[0]["messages"][1]["content"])
    assert packet["cards"] == {"student": "card text"}
    comfort = list(packet["references"]["student"]["prices"]["by_product"].values())[1]
    assert comfort["party_total"] == 12_800 and "deck" not in packet["references"]["student"]
    assert signal.satisfied is True and len(provider.requests) == 1
    rows = [json.loads(line) for line in (tmp_path / "records" / "references.jsonl").read_text().splitlines()]
    assert rows[0]["drill"] == "student" and rows[0]["trip"]["adults"] == 4 and rows[0]["card"] == "card text"
    assert rows[0]["references"]["prices"]["persons"] == 4


def test_a_scenario_without_a_material_loses_it_from_its_materials_opening_set_and_plans():
    scenario = Scenario.load(TRAVEL)
    control = scenario.without(["plan-deck-sample"])
    assert "plan-deck-sample" in scenario.materials and "plan-deck-sample" not in control.materials
    assert "plan-deck-sample" not in control.initial and len(control.initial) == len(scenario.initial) - 1
    assert all("plan-deck-sample" not in step for steps in control.plans.values() for step in steps)
    assert control.disclosure("by-stage").steps == control.plans["by-stage"]
    with pytest.raises(ValueError, match="brochure"):
        scenario.without(["brochure"])


def test_the_employees_workdir_is_new_and_never_the_repository(tmp_path):
    from experimental.automation.employee import workplace

    repository = Path(__file__).resolve().parents[1]
    for bad in (repository, repository / "experimental", repository.parent):
        with pytest.raises(ValueError, match="repository"):
            workplace(bad)
    (tmp_path / "used").mkdir()
    (tmp_path / "used" / "notes.md").write_text("x")
    with pytest.raises(ValueError, match="new or empty"):
        workplace(tmp_path / "used")
    assert workplace(tmp_path / "fresh").is_dir() and not any(workplace(None).iterdir())


def test_each_child_reaches_only_its_own_home_and_what_its_parent_hands_it(tmp_path, monkeypatch):
    """The children `hire` wires are prepared as the worker would prepare them on start."""
    from experimental.automation import employee

    monkeypatch.setattr(employee, "discover_product_rows", lambda: [])
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {
                "providers": {"deepseek": {"api_key": "k"}},
                "agents": {"defaults": {"model": "deepseek/x", "provider": "deepseek"}},
            }
        )
    )
    worker = hire(Scenario.load(TRAVEL).contract, config, workdir=tmp_path / "work", root=tmp_path / "run")
    children = worker._prepare_children(worker.baseline)
    assert set(children) == {"Raven"}
    child = children["Raven"].baseline
    assert child.config.workspace_path == worker.baseline.config.workspace_path / "subagents" / "Raven"
    assert child.file_roots == (worker.baseline.workdir,) == (tmp_path / "work",)
    assert child.read_roots == (worker.baseline.config.workspace_path,) == (tmp_path / "run" / AREA / HOME,)
    assert child.config.tools.restrict_to_workspace is True
    assert worker.baseline.file_roots == () and worker.baseline.read_roots == ()


async def test_the_owner_hands_over_a_candidate_it_never_confirmed_as_files_and_never_voices_it(tmp_path):
    from experimental.research.package import CANDIDATES, CONFIRMED
    from experimental.scenario import load
    from tests.test_research_package import researched

    _, out = researched(tmp_path)
    scenario = Scenario.of(load(out.root))
    provider = Provider(response(REVIEW, {"verdicts": verdicts(scenario), "remark": "Fine so far."}))
    uploads = tmp_path / "home" / "uploads"
    agency = Agency(
        scenario,
        provider,
        tmp_path / "home" / "skills",
        workdir=tmp_path,
        uploads=uploads,
        disclosure=scenario.disclosure("two"),
    )
    agency.prepare()
    signal = await agency.evaluate({"walk-in": [exchange("Tea for two?", "Six.")]})
    handed = {item.name for item in signal.attachments}
    assert {CONFIRMED, CANDIDATES} <= handed and (uploads / CANDIDATES / "SKILL.md").is_file()
    assert scenario.document(CONFIRMED).strip() in signal.text
    assert scenario.document(CANDIDATES).strip() not in signal.text and "Never offer a discount." not in signal.text


def test_held_out_cards_are_played_apart_from_the_cards_played_for_feedback():
    from experimental.simulation.__main__ import drills

    personas = Scenario.load(TRAVEL).personas
    names = [persona.name for persona in personas]
    played, held = drills(personas, None, [names[0]])
    assert [persona.name for persona in held] == [names[0]] and [persona.name for persona in played] == names[1:]
    played, held = drills(personas, names[1:2], None)
    assert [persona.name for persona in played] == names[1:2] and held == []
    with pytest.raises(ValueError, match="not also played for feedback"):
        drills(personas, names[:1], names[:1])
    with pytest.raises(ValueError, match="no drill cards named"):
        drills(personas, None, ["nobody"])
    with pytest.raises(ValueError, match="leaves nothing to play"):
        drills(personas, None, names)
