"""The RSI Studio's server side: a run cut down to its shape, a kept record served on request, the cached index, the
opaque label each session goes by, and what the run directory keeps beside the record (the standard and the
compartment log)."""

import json
import threading
from dataclasses import asdict

import pytest

from experimental.assessor.rubric import (
    AssessmentPlan,
    Basis,
    Criterion,
    Definition,
    EvidenceRequirement,
    ProgramCheck,
    Reference,
)
from experimental.iteration.hearing import opaque
from experimental.webui import studio
from experimental.webui.rundir import RecordError, annex, joined, labels, verdicts


def _run(tmp_path):
    root = tmp_path / "runs" / "w"
    (root / "iteration").mkdir(parents=True)
    record = {
        "task": "job",
        "status": "finished",
        "rounds": [
            {
                "sessions": {
                    "family": [
                        {
                            "user": "hi",
                            "execution": {
                                "turn_id": "t",
                                "events": [{"big": "x" * 100}],
                                "records": [
                                    {
                                        "kind": "provider.request",
                                        "turn_id": "t",
                                        "parameters": {
                                            "model": "m",
                                            "messages": [{"role": "user", "content": "sk-" + "a" * 40}],
                                            "tools": [{}, {}],
                                        },
                                    },
                                    {
                                        "kind": "child.execution",
                                        "harness": "Raven",
                                        "records": [
                                            {"kind": "provider.request", "parameters": {}},
                                            {"kind": "action.result", "operation": "assess"},
                                            tool_event("start", "c1", name="exec", arguments={"command": "read"}),
                                            tool_event("start", "c2", name="ops_check_later", arguments={}),
                                            tool_event("complete", "c2", result_preview="wake set", ok=True),
                                            tool_event("complete", "c1", result_preview="x" * 900, ok=False),
                                            {
                                                "kind": "runner.event",
                                                "event_type": "Text",
                                                "event": {"content": "done"},
                                            },
                                        ],
                                    },
                                    {"kind": "runner.event", "event_type": "Text", "event": {"content": "hello"}},
                                ],
                            },
                        }
                    ]
                },
                "signals": [],
                "feedback": None,
                "curated": False,
                "analysis": [],
                "curation": [],
            }
        ],
        "initial_curation": [],
        "pending": {
            "sessions": {"family": [{"user": "next", "execution": {"turn_id": "p", "records": [request("p")]}}]}
        },
    }
    record["rounds"][0]["holdout"] = {
        "quiet": [{"user": "held", "execution": {"turn_id": "h", "records": [request("h")]}}]
    }
    path = root / "iteration" / "r.json"
    path.write_text(json.dumps(record))
    return tmp_path / "runs", path


def tool_event(phase, call, **event):
    return {
        "kind": "runner.event",
        "event_type": "ToolEvent",
        "event": {"phase": phase, "tool_call_id": call, "name": "", **event},
    }


def request(model):
    return {"kind": "provider.request", "turn_id": model, "parameters": {"model": model, "messages": [], "tools": []}}


def test_slim_keeps_the_shape_and_leaves_a_reference_for_each_cut_record(tmp_path):
    _, path = _run(tmp_path)
    run = studio.studio_run(path)
    execution = run["rounds"][0]["sessions"]["family"][0]["execution"]
    request, child, text = execution["records"]
    assert "events" not in execution
    assert request == {
        "kind": "provider.request",
        "turn_id": "t",
        "model": "m",
        "reasoning_effort": None,
        "messages": {"count": 1, "chars": 45},
        "tools": 2,
        "ref": {"round": 0, "part": "sessions", "session": "family", "turn": 0, "index": 0},
    }
    assert child["records"] == [{"kind": "action.result", "operation": "assess"}]
    assert child["counts"] == {"provider.request": 1, "action.result": 1, "runner.event": 5}
    assert child["steps"] == [
        {"tool": "exec", "arguments": '{"command": "read"}', "result": "x" * 400 + "...", "ok": False},
        {"tool": "ops_check_later", "arguments": "{}", "result": "wake set", "ok": True},
        {"text": "done"},
    ]
    assert child["steps_omitted"] == 0
    assert text["event"]["content"] == "hello"
    (held,) = run["rounds"][0]["holdout"]["quiet"][0]["execution"]["records"]
    assert held["ref"] == {"round": 0, "part": "holdout", "session": "quiet", "turn": 0, "index": 0}
    (pending,) = run["pending"]["sessions"]["family"][0]["execution"]["records"]
    assert pending["ref"] == {"round": "pending", "part": "sessions", "session": "family", "turn": 0, "index": 0}
    assert (run["standard"], run["boundaries"]) == (None, None)
    assert run["labels"] == {"family": opaque("family"), "quiet": opaque("quiet")}


def test_labels_name_each_session_of_the_rounds_and_the_round_in_progress_by_the_loops_opaque_label():
    record = {
        "rounds": [{"sessions": {"family": []}, "holdout": {"quiet": []}}, {"sessions": {"family": [], "solo": []}}],
        "pending": {"sessions": {"late": []}},
    }
    assert labels(record) == {name: opaque(name) for name in ("family", "late", "quiet", "solo")}
    assert labels({"rounds": [{"sessions": None}], "pending": None}) == {}
    assert opaque("family").startswith("session-") and opaque("family") != opaque("solo")


def test_raw_serves_the_kept_record_with_secrets_redacted(tmp_path):
    _, path = _run(tmp_path)
    record = studio.raw_record(path, 0, "family", 0, 0)
    assert record["parameters"]["tools"] == [{}, {}]
    assert "sk-aaaa" not in json.dumps(record)
    assert studio.raw_record(path, 0, "family", 0, 9) is None
    assert studio.raw_record(path, 3, "family", 0, 0) is None
    assert studio.raw_record(path, 0, "quiet", 0, 0, part="holdout")["parameters"]["model"] == "h"
    assert studio.raw_record(path, None, "family", 0, 0)["parameters"]["model"] == "p"
    assert studio.raw_record(path, 0, "quiet", 0, 0) is None
    assert studio.raw_record(path, 0, "family", 0, 0, part="elsewhere") is None


def test_a_record_that_fails_to_load_is_an_error_that_names_it(tmp_path):
    _, path = _run(tmp_path)
    path.write_text(json.dumps({"task": "job", "rounds": [{"sessions": "not a mapping"}]}))
    with pytest.raises(RecordError, match="the run record r.json could not be loaded"):
        studio.studio_run(path)
    with pytest.raises(RecordError):
        studio.raw_record(path, 0, "family", 0, 0)
    path.write_text("{")
    with pytest.raises(RecordError, match="JSONDecodeError"):
        joined(path)


def test_index_is_built_once_and_refreshed_in_the_background_when_a_record_changes(tmp_path):
    root, path = _run(tmp_path)
    calls = []
    done = threading.Event()

    def build(folder):
        calls.append(folder)
        if len(calls) > 1:
            done.set()
        return [{"n": len(calls)}]

    assert studio.studio_index(root, build) == [{"n": 1}]
    assert studio.studio_index(root, build) == [{"n": 1}]
    assert len(calls) == 1
    path.write_text(path.read_text() + " ")
    assert studio.studio_index(root, build) == [{"n": 1}]
    assert done.wait(5)
    for _ in range(50):
        if studio.studio_index(root, build) == [{"n": 2}]:
            break
        threading.Event().wait(0.02)
    assert studio.studio_index(root, build) == [{"n": 2}]


def test_slim_cuts_the_interaction_records_and_serves_a_child_record_by_its_reference(tmp_path):
    scope = {"harness_id": "h", "turn_id": "t"}
    big = "x" * 3000
    records = [
        {
            "kind": "model.input",
            "turn_id": "t",
            "scope": scope,
            "messages": [{"role": "system", "content": big}],
            "tools": [{}],
        },
        {
            "kind": "capability.effective",
            "turn_id": "t",
            "view": {
                "scope": scope,
                "tools": [{"type": "function", "function": {"name": "read_file"}}],
                "skills": [{"name": "deck"}],
            },
        },
        {
            "kind": "memory.context",
            "turn_id": "t",
            "estimated_tokens": 10,
            "allowance": 99,
            "sources": ["identity"],
            "capabilities": big,
        },
        {
            "kind": "action.call",
            "turn_id": "t",
            "operation": "handle_event",
            "source": "proposal",
            "arguments": [
                {
                    "kind": "proposal",
                    "stage": "reply",
                    "event_id": "e",
                    "text": "draft",
                    "calls": [],
                    "capabilities": big,
                }
            ],
        },
        {"kind": "action.call", "turn_id": "t", "operation": "handle_request", "arguments": [{"command": "small"}]},
        {
            "kind": "action.control",
            "turn_id": "t",
            "receipt": {"control_id": "c", "control": "finish", "status": "applied"},
        },
        {
            "kind": "child.execution",
            "harness": "Raven",
            "records": [{"kind": "runner.event"}, {"kind": "model.input", "messages": [], "tools": []}],
        },
    ]
    root = tmp_path / "runs" / "w"
    (root / "iteration").mkdir(parents=True)
    path = root / "iteration" / "r.json"
    exchange = {"user": "hi", "execution": {"turn_id": "t", "records": records}}
    path.write_text(json.dumps({"task": "job", "rounds": [{"sessions": {"s": [exchange]}}], "initial_curation": []}))
    kept = studio.slim(joined(path))["rounds"][0]["sessions"]["s"][0]["execution"]["records"]
    model, view, context, event, request, control, child = kept
    assert model["messages"] == {"count": 1, "chars": 3002} and model["tools"] == 1 and "scope" not in model
    assert (view["tools"], view["skills"]) == (["read_file"], ["deck"])
    assert context == {
        "kind": "memory.context",
        "turn_id": "t",
        "estimated_tokens": 10,
        "allowance": 99,
        "sources": ["identity"],
        "ref": context["ref"],
    }
    assert (
        event["arguments"]["kind"] == "proposal"
        and event["arguments"]["stage"] == "reply"
        and "capabilities" not in event["arguments"]
    )
    assert request == records[4] and control == records[5]
    assert child["records"] == [
        {
            "kind": "model.input",
            "turn_id": None,
            "ref": {"round": 0, "part": "sessions", "session": "s", "turn": 0, "index": 6, "child": 1},
            "messages": {"count": 0, "chars": 0},
            "tools": 0,
        }
    ]
    assert studio.raw_record(path, 0, "s", 0, 6, 1) == {"kind": "model.input", "messages": [], "tools": []}
    assert studio.raw_record(path, 0, "s", 0, 6, 9) is None


def test_a_long_agent_request_keeps_its_id_and_short_command():
    call = {
        "kind": "action.call",
        "operation": "handle_request",
        "arguments": [{"request_id": "r", "command": {"finish": True}, "capabilities": "x" * 3000}],
    }
    kept = studio._slim_record(call, {"index": 0})
    assert kept["arguments"]["request_id"] == "r"
    assert kept["arguments"]["command"] == {"finish": True}
    assert "capabilities" not in kept["arguments"]


def test_a_long_strategy_result_keeps_its_small_fields_and_a_reference():
    compose = {"kind": "memory.result", "operation": "compose", "result": {"messages": ["x" * 5000], "order": ["a"]}}
    kept = studio._slim_record(compose, {"index": 3})
    size = len(json.dumps(compose["result"]))
    assert kept == {
        "kind": "memory.result",
        "operation": "compose",
        "result": {"size": size, "order": ["a"]},
        "ref": {"index": 3},
    }
    decision = {
        "kind": "action.result",
        "operation": "handle_event",
        "result": {"control": "revise", "feedback": "y" * 5000},
    }
    assert studio._slim_record(decision, {"index": 4}) == decision


def test_slim_cuts_the_curators_and_the_attributors_records():
    query = {"stage": "diagnose", "event": "query", "tool": "read_observation", "arguments": {"index": 0}}
    trace = [
        {**query, "result": {"text": "t" * 2000, "index": 0, "records": ["r" * 5000]}},
        {"stage": "diagnose", "event": "submit_diagnosis", "output": {"diagnoses": [{"about": "R1"}]}},
    ]
    child = {"kind": "child.execution", "harness": "Raven", "records": [{"kind": "model.input"}] * 3, "big": "x" * 3000}
    generated = {
        "candidate": {"plan": {"changes": []}, "artifact": {"values": {}, "files": {}}},
        "validation": {"errors": [], "observations": [child, {"kind": "runtime.bound", "targets": []}]},
        "trace": trace,
    }
    run = {
        "task": "job",
        "rounds": [
            {
                "sessions": {},
                "curation": [
                    {
                        "generated": generated,
                        "child_changes": {"Raven": generated},
                        "composition": {"input_id": "i", "scopes": {"Raven": "child-1"}, "state": {"x": "y" * 9000}},
                    }
                ],
                "attribution": [
                    {"file": "a.json", "request": [{"content": "abc"}], "feedback": {"f": 1}, "trace": trace}
                ],
            }
        ],
        "initial_curation": [],
        "initial_attribution": [{"file": "b.json", "request": [], "trace": []}],
    }
    out = studio.slim(run)["rounds"][0]
    (curation,) = out["curation"]
    assert curation["composition"] == {"input_id": "i", "scopes": {"Raven": "child-1"}}
    for kept in (curation["generated"], curation["child_changes"]["Raven"]):
        first, submitted = kept["trace"]
        assert first["result"] == {"text": "t" * 600 + "...", "index": 0} and submitted == trace[1]
        assert kept["validation"]["observations"] == [
            {"kind": "child.execution", "harness": "Raven", "counts": {"model.input": 3}},
            {"kind": "runtime.bound", "targets": []},
        ]
    (attribution,) = out["attribution"]
    assert attribution["request"] == {"count": 1, "chars": 5} and "feedback" not in attribution
    assert attribution["trace"][0]["result"] == {"text": "t" * 600 + "...", "index": 0}
    assert studio.slim(run)["initial_attribution"] == [
        {"file": "b.json", "request": {"count": 0, "chars": 0}, "trace": []}
    ]


def test_a_speaking_assessors_kept_scorecard_stands_in_for_its_signal_among_the_verdicts():
    item = {"id": "wbt-daily", "result": "fail", "session": "family"}
    card = {"source": "agency", "text": "Three things.", "items": [item], "metrics": {}, "satisfied": False}
    standard = {"source": "standard", "text": "", "items": [{"id": "S1", "result": "pass", "session": "family"}]}
    round_ = {
        "signals": [{"source": "agency", "text": "Three things.", "items": []}, standard],
        "holdout": {"unseen": []},
    }
    held = {**card, "items": [{**item, "session": "unseen"}]}
    analysis = [{"source": "agency", "scorecard": card}, {"source": "agency", "scorecard": held}, {"trace": []}]
    assert verdicts(round_, analysis) == [standard, card]
    assert verdicts({"signals": [{**card}]}, [{"scorecard": {**card, "items": []}}]) == [card]
    assert verdicts({"signals": []}, [{"source": "agency", "error": "judge failed"}]) == []


def test_joined_rounds_carry_their_verdicts(tmp_path):
    root = tmp_path / "w"
    (root / "iteration").mkdir(parents=True)
    (root / "analysis").mkdir()
    card = {"source": "agency", "text": "", "items": [{"id": "C1", "result": "pass", "session": "family"}]}
    (root / "analysis" / "a.json").write_text(json.dumps({"source": "agency", "scorecard": card}))
    signal = {"source": "agency", "text": "Fine.", "items": [], "metrics": {}, "satisfied": True, "attachments": []}
    record = {"task": "job", "task_id": "t", "status": "finished", "initial_curation": [], "history": []}
    record["rounds"] = [
        {"sessions": {}, "signals": [signal], "feedback": None, "curated": False, "analysis": ["a.json"]}
    ]
    path = root / "iteration" / "r.json"
    path.write_text(json.dumps(record))
    assert joined(path)["rounds"][0]["verdicts"] == [card]


@pytest.mark.parametrize("builder_key", ["rubric_builder", "critic"])
def test_annex_reads_the_standard_and_the_compartment_log_beside_the_record(tmp_path, builder_key):
    assert annex(tmp_path) == {"standard": None, "boundaries": None, "origins": {}, "research": None}
    induced = {"origin": "induced", "confirmed": False, "items": ["induced-1"]}
    settings = {"provenance": {"materials": {"induced-candidates": induced, "odd": "not a row"}, "items": []}}
    (tmp_path / "settings.json").write_text(json.dumps(settings))
    assert annex(tmp_path)["origins"] == {"induced-candidates": induced}
    (tmp_path / "settings.json").write_text(json.dumps({"provenance": None}))
    assert annex(tmp_path)["origins"] == {}
    criterion = {"id": "C1", "text": "Quote from the list", "source": "declared", "strength": "must_hold"}
    label = "assessor" if builder_key == "rubric_builder" else "standard"
    trace = [{"event": "model.call", "label": label}, {"event": "x"}]
    change = {
        "id": "derived-1",
        "op": "add",
        "reason": "new_norm",
        "explanation": "The norm states it.",
        "criterion": {"text": "Name every source.", "quote": "name the source", "material": "sop", "section": "4"},
    }
    builder = {
        "read": ["sop"],
        "versions": [{"version": 1, "new_norms": ["sop"], "changes": [change, "odd"], "unchecked": []}],
        "trace": [{"event": "model.call", "label": builder_key}],
    }
    standard = {"criteria": [{**criterion, "provenance": "check:C1"}, {"text": "no id"}], builder_key: builder}
    (tmp_path / "standard.json").write_text(json.dumps({**standard, "trace": trace}))
    rows = [
        {"time": 1.0, "role": "curator", "event": "enter", "where": "curator", "hits": []},
        {"time": 2.0, "role": "curator", "event": "violation", "where": "admit:feedback", "hits": ["<sealed text>"]},
        "not a row",
        {"time": 3.0, "role": "analyst", "event": "enter", "where": "analyst", "hits": []},
    ]
    (tmp_path / "boundaries.jsonl").write_text("\n".join(json.dumps(row) for row in rows) + "\n{broken\n")
    read = annex(tmp_path)
    assert read["standard"] == {
        "criteria": [{**criterion, "provenance": "check:C1", "situation": "", "acceptance": "", "quote": ""}],
        "derived_from": ["sop"],
        "revisions": [
            {
                "version": 1,
                "new_norms": ["sop"],
                "changes": [
                    {
                        "id": "derived-1",
                        "op": "add",
                        "reason": "new_norm",
                        "explanation": "The norm states it.",
                        "before": "",
                        "text": "Name every source.",
                        "quote": "name the source",
                        "material": "sop",
                    }
                ],
                "unchecked": [],
            }
        ],
        "calls": {"assessor": 1, "rubric_builder": 1},
    }
    earlier = {"criteria": [], "derived_from": ["sop"], "trace": [{"event": "model.call", "label": "derive"}]}
    (tmp_path / "standard.json").write_text(json.dumps(earlier))
    assert annex(tmp_path)["standard"] == {
        "criteria": [],
        "derived_from": ["sop"],
        "revisions": [],
        "calls": {"derive": 1},
    }
    audit = read["boundaries"]
    assert audit["total"] == 3 and [row["event"] for row in audit["rows"]] == ["enter", "violation", "enter"]
    assert audit["violations"] == [rows[1]]
    assert audit["counts"] == {"curator": {"enter": 1, "violation": 1}, "analyst": {"enter": 1}}
    (tmp_path / "standard.json").write_text("[")
    assert annex(tmp_path)["standard"]["error"].startswith("JSONDecodeError")


def test_annex_reads_how_the_research_stage_ended_and_what_went_wrong(tmp_path):
    folder = tmp_path / "information"
    folder.mkdir()
    (folder / "status.json").write_text(json.dumps({"status": "incomplete", "stop_reason": "error", "seconds": 276.0}))
    section = {
        "dimension": "role",
        "text": "",
        "coverage": "missing",
        "reason": "Not assessed.",
        "evidence": ["evidence-1", "evidence-3"],
    }
    evidence = [
        {"id": "evidence-1", "channel": "tool", "origin": "brand-norms", "content": "Section 2.", "sources": []},
        {"id": "evidence-2", "channel": "tool", "origin": "proposal-template", "content": "Chapters.", "sources": []},
        {
            "id": "evidence-3",
            "channel": "research",
            "origin": json.dumps({"attempt": "research-1", "finding": "researched-1", "question": "Which law?"}),
            "content": json.dumps({"id": "researched-1", "text": "Article 9 bans superlatives."}),
            "sources": ["https://example.org/law"],
            "dimensions": ["knowledge"],
        },
        {"id": "evidence-4", "channel": "user", "origin": json.dumps({"question": "Budget?"}), "content": "50k."},
        {"id": "evidence-5", "channel": "user", "origin": json.dumps({"question": "Launch date?"}), "content": "null"},
        {
            "id": "evidence-6",
            "channel": "research",
            "origin": json.dumps({"attempt": "research-2", "synthesis": True}),
            "content": json.dumps({"synthesis": "Nothing public answers it."}),
        },
    ]
    (folder / "evidence.json").write_text(json.dumps(evidence))
    wave = [
        {"group": 1, "status": "failed", "dimensions": ["knowledge"], "questions": ["Which law?"], "error": "no key"}
    ]
    (folder / "wave-1.json").write_text(json.dumps(wave))
    result = {
        "snapshot": {"description": {"title": "Unfinished", "sections": [section], "resources": [], "unresolved": []}},
        "review": {"accepted": False, "reason": "assess: submission budget exhausted", "issues": ["Complete it."]},
        "stop_reason": "error",
    }
    (folder / "result.json").write_text(json.dumps(result))
    trace = [
        {"label": "assess", "event": "model.call", "call": 1},
        {"label": "assess", "event": "query", "tool": "read_file"},
        {"label": "assess", "event": "output.rejected", "error": "last call", "tools": ["read_file"], "charged": False},
        {"label": "research", "event": "group.failed", "group": 2, "error_type": "ValueError"},
        {"label": "compose", "event": "model.call", "call": 1},
        {"label": "compose", "event": "submit_information"},
        "odd",
    ]
    (folder / "trace.json").write_text(json.dumps(trace))
    for name, models in (("acquisition", ["claude-sonnet-5-5", "claude-haiku-5-5"]), ("review", ["claude-sonnet-5-5"])):
        (folder / "research-1" / name).mkdir(parents=True)
        run = {"researcher": "claude", "model": "sonnet", "effort": "medium", "actual_models": models}
        (folder / "research-1" / name / "run.json").write_text(json.dumps(run))
    (folder / "research-1" / "notes.json").write_text(json.dumps({"model": "not a run"}))
    research = annex(tmp_path)["research"]
    assert research["status"] == "incomplete" and research["stop_reason"] == "error" and research["seconds"] == 276.0
    assert research["researchers"] == [
        {
            "agent": "claude",
            "asked": "sonnet",
            "effort": "medium",
            "models": ["claude-sonnet-5-5", "claude-haiku-5-5"],
            "calls": 2,
        }
    ]
    assert research["review"] == {
        "accepted": False,
        "reason": "assess: submission budget exhausted",
        "issues": ["Complete it."],
    }
    assert research["sections"] == [
        {
            "dimension": "role",
            "coverage": "missing",
            "text": "",
            "reason": "Not assessed.",
            "evidence": 2,
            "channels": ["research", "tool"],
        }
    ]
    assert research["channels"] == {"tool": 2, "research": 2, "user": 2}
    assert [(row["kind"], row["question"], row["text"], row["sources"]) for row in research["evidence"]] == [
        ("finding", "Which law?", "Article 9 bans superlatives.", ["https://example.org/law"]),
        ("answer", "Budget?", "50k.", []),
        ("", "Launch date?", "", []),
        ("synthesis", "", "Nothing public answers it.", []),
    ]
    assert research["groups"] == [
        {
            "wave": "1",
            "group": 1,
            "status": "failed",
            "dimensions": ["knowledge"],
            "questions": ["Which law?"],
            "error": "no key",
            "admitted": 0,
            "refused": 0,
            "withheld": 0,
            "unanswered": 0,
            "seconds": None,
        }
    ]
    assert research["stages"] == [
        {"stage": "assess", "calls": 1, "queries": 1, "submitted": False},
        {"stage": "research", "calls": 0, "queries": 0, "submitted": False},
        {"stage": "compose", "calls": 1, "queries": 0, "submitted": True},
    ]
    assert research["trouble"] == [
        {"stage": "assess", "event": "output.rejected", "error": "last call", "tools": ["read_file"], "charged": False},
        {"stage": "research", "event": "group.failed", "error": "group 2: ValueError", "tools": [], "charged": True},
    ]
    assert research["errors"] == []
    (folder / "result.json").write_text("{")
    assert annex(tmp_path)["research"]["errors"][0].startswith("result.json: JSONDecodeError")


def test_evaluation_annex_keeps_authority_evidence_and_guidance_but_omits_raw_inputs(tmp_path):
    stored = {
        "criteria": [
            {
                "id": "cost",
                "text": "Include tax.",
                "kind": "gate",
                "authority": "external",
                "checks": [{"method": "program", "spec": "tax_check"}],
            }
        ],
        "assessments": [
            {
                "id": "run:1",
                "version": 1,
                "evidence": {"private": "RAW_TASK_INPUT"},
                "checks": [{"criterion": "cost", "method": "program", "result": "fail"}],
                "review": {"issues": [{"criterion": "cost", "target": "evidence", "correction": "Read receipt."}]},
            }
        ],
        "meta_reviewer": {"trace": [{"event": "model.call", "label": "meta_reviewer"}]},
        "guidance": {
            "entries": {
                "lesson": {
                    "state": "candidate",
                    "proposal": {"kind": "principle", "text": "Check costs.", "scope": "*"},
                    "episodes": {"run:1": {"private": "RAW_TASK_INPUT"}},
                }
            },
            "history": [{"candidate": "lesson", "accepted": False}],
        },
    }
    (tmp_path / "standard.json").write_text(json.dumps(stored))
    read = annex(tmp_path)["standard"]
    assert read["criteria"][0]["authority"] == "external"
    assert read["assessments"][0]["checks"][0]["result"] == "fail"
    assert read["guidance"]["entries"][0]["state"] == "candidate"
    assert read["guidance"]["history"][0]["accepted"] is False
    assert read["calls"]["meta_reviewer"] == 1
    assert "RAW_TASK_INPUT" not in json.dumps(read)


def test_evaluation_annex_displays_contract_and_legacy_without_inventing_semantics(tmp_path):
    criterion = Criterion(
        "tax",
        Definition("Delivered quote", "Include tax.", "When a price is quoted."),
        "derived",
        "gate",
        Basis((Reference("policy", "Include tax.", "a" * 64),), "The quoted total must include tax."),
        assessment=AssessmentPlan(
            required_checks=(ProgramCheck(verifier="tax_check"),),
            evidence_requirements=(EvidenceRequirement("delivered_text", "quote.txt"),),
        ),
    )
    stored = {
        "schema": 2,
        "criteria": [asdict(criterion), {"id": "legacy", "text": "Preserve this wording."}],
        "rubric_builder": {
            "read": {"policy": "a" * 64},
            "versions": [
                {
                    "version": 1,
                    "changes": [
                        {"id": "tax", "op": "rewrite", "before": asdict(criterion), "criterion": asdict(criterion)}
                    ],
                }
            ],
        },
    }
    (tmp_path / "standard.json").write_text(json.dumps(stored))
    read = annex(tmp_path)["standard"]
    current, legacy = read["criteria"]
    assert current["subject"] == "Delivered quote"
    assert current["text"] == "Include tax."
    assert current["situation"] == "When a price is quoted."
    assert current["source"] == "derived"
    assert current["strength"] == "must_hold"
    assert current["provenance"] == "policy@aaaaaaaaaaaa"
    assert current["derivation"] == "The quoted total must include tax."
    assert current["evidence_requirements"] == [{"kind": "delivered_text", "reference": "quote.txt"}]
    assert current["checks"] == [
        {"role": "decision", "method": "llm", "spec": ""},
        {"role": "required", "method": "program", "spec": "tax_check"},
    ]
    assert read["derived_from"] == ["policy"]
    assert read["revisions"][0]["changes"][0]["before"] == "Include tax."
    assert read["revisions"][0]["changes"][0]["material"] == "policy"
    assert legacy["text"] == "Preserve this wording."
    assert "subject" not in legacy and "checks" not in legacy
