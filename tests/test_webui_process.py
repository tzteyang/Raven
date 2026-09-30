"""The web view's reading of playbook nodes: sub-agent steps from transcripts, frame journals and model calls, and the housed sub-harness homes."""

import json
import os
import time

from experimental.webui import serve
from experimental.webui.process import node_process, redact, subharness_homes

KEY = "sk-" + "a" * 30
HEX = "0123456789abcdef" * 2 + "01234567"


def build(tmp_path, *, finished=False, subagent="Raven-PPT"):
    root = tmp_path / "runs"
    worker = root / "run"
    (worker / "iteration").mkdir(parents=True)
    (worker / "iteration" / "r1.json").write_text(json.dumps({"status": "running", "rounds": []}))
    sub = worker / "employee" / "home" / "sessions" / "curator" / "conv" / "subagents"
    (sub / "mas_dag" / "dag-1").mkdir(parents=True)
    (sub / "nodes").mkdir()
    (sub / "mas_dag" / "dag-1" / "graph.json").write_text(
        json.dumps({"nodes": [{"id": "deck", "subagent": subagent, "node_summary": "Build", "prompt_template": "T"}]})
    )
    (sub / "nodes" / "deck.prompt.md").write_text("Build the deck " + KEY)
    log = worker / "employee" / "gen" / "observations.jsonl"
    log.parent.mkdir()
    rows = [
        {
            "kind": "dag.progress",
            "name": "dag_run_started",
            "payload": {"run_id": "dag-1", "nodes": [{"id": "deck", "subagent": subagent}]},
        },
        {
            "kind": "dag.progress",
            "name": "dag_node_updated",
            "payload": {"run_id": "dag-1", "node": "deck", "status": "running", "started_at": 1_000},
        },
    ]
    log.write_text("".join(json.dumps(row) + "\n" for row in rows))
    state = tmp_path / "homes"
    frames = state / "run" / "traces" / "logs" / "acp-frames" / "2026-09-24"
    frames.mkdir(parents=True)
    (state / "run" / "config.json").write_text(json.dumps({"api_key": KEY}))
    return root, worker, sub, log, state, frames


def frame(update, time="2026-09-24T06:54:30.000000"):
    return {
        "_type": "acp_frame",
        "timestamp": time,
        "dir": "in",
        "session": "s",
        "frame": {"method": "session/update", "params": {"update": update}},
    }


def test_journal_steps_merge_chunks_and_follow_the_node_call(tmp_path):
    root, worker, sub, log, state, frames = build(tmp_path)
    journal = frames / "Raven-PPT-065427000000.jsonl"
    rows = [
        {"_type": "acp_frame", "timestamp": "2026-09-24T06:54:28", "dir": "err", "text": "[run] llm: own key " + KEY},
        {"_type": "acp_call", "timestamp": "2026-09-24T06:54:29", "task_id": "other", "agent": "Raven-PPT"},
        frame({"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "not mine"}}),
        {"_type": "acp_call", "timestamp": "2026-09-24T06:54:29", "task_id": "deck", "agent": "Raven-PPT"},
        frame({"sessionUpdate": "agent_thought_chunk", "content": {"type": "text", "text": "Think "}}),
        frame({"sessionUpdate": "agent_thought_chunk", "content": {"type": "text", "text": "more"}}),
        frame(
            {
                "sessionUpdate": "tool_call",
                "toolCallId": "c1",
                "title": "web_search: hotels",
                "kind": "search",
                "status": "in_progress",
                "rawInput": {"query": "hotels"},
                "_meta": {"raven.toolName": "web_search"},
            }
        ),
        frame(
            {
                "sessionUpdate": "tool_call_update",
                "toolCallId": "c1",
                "status": "completed",
                "content": [{"type": "content", "content": {"type": "text", "text": "Hotel A token " + HEX}}],
            }
        ),
        {
            "_type": "acp_frame",
            "timestamp": "2026-09-24T06:54:31",
            "dir": "in",
            "frame": {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "elicitation/create",
                "params": {"message": "Who reads it?"},
            },
        },
        {
            "_type": "acp_frame",
            "timestamp": "2026-09-24T06:54:31",
            "dir": "out",
            "frame": {"jsonrpc": "2.0", "id": 1, "result": {"action": "decline"}},
        },
        frame({"sessionUpdate": "tool_call", "toolCallId": "c2", "title": "ppt_build", "status": "in_progress"}),
    ]
    journal.write_text("".join(json.dumps(row) + "\n" for row in rows) + '{"_type": "acp_fr')
    reply = node_process(worker, [state], "dag-1", "deck")
    assert reply["source"] == "journal" and reply["lane"] == "acp" and reply["status"] == "running"
    kinds = [step["kind"] for step in reply["steps"]]
    assert kinds == ["thought", "tool", "question", "tool"]
    assert reply["steps"][0]["text"] == "Think more"
    assert reply["steps"][1]["status"] == "completed" and "<redacted>" in reply["steps"][1]["result"]
    assert reply["steps"][2]["status"] == "decline"
    assert reply["steps"][3]["status"] == "running"
    assert reply["counts"]["tools"] == 2 and reply["last"] == "ppt_build"
    assert KEY not in json.dumps(reply) and "<redacted>" in reply["prompt"]
    with journal.open("a") as stream:
        stream.write(
            'ame", "timestamp": "2026-09-24T06:54:40", "dir": "in", "frame": {"method": "session/update", "params": {"update": {"sessionUpdate": "tool_call_update", "toolCallId": "c2", "status": "failed"}}}}\n'
        )
    again = node_process(worker, [state], "dag-1", "deck", summary=True)
    assert again["counts"]["failed"] == 1 and "steps" not in again and "prompt" not in again


def test_the_first_node_of_a_connection_keeps_its_handshake_stderr(tmp_path):
    root, worker, sub, log, state, frames = build(tmp_path)
    rows = [
        {"_type": "acp_frame", "timestamp": "2026-09-24T06:54:28", "dir": "err", "text": "[run] web: proxy=own"},
        {
            "_type": "acp_frame",
            "timestamp": "2026-09-24T06:54:28",
            "dir": "err",
            "text": "Traceback (most recent call last)",
        },
        {"_type": "acp_call", "timestamp": "2026-09-24T06:54:29", "task_id": "deck"},
    ]
    (frames / "Raven-PPT-065427000000.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    steps = node_process(worker, [state], "dag-1", "deck")["steps"]
    assert steps == [dict(steps[0], kind="stderr", level="error")] and steps[0]["text"].count("\n") == 1


def test_a_finished_node_reads_its_transcript_output_and_verdict(tmp_path):
    root, worker, sub, log, state, frames = build(tmp_path)
    transcript = [
        {
            "role": "assistant",
            "content": "",
            "reasoning_content": "Plan",
            "tool_calls": [
                {"id": "c1", "type": "function", "function": {"name": "read_file", "arguments": '{"path": "a.md"}'}}
            ],
            "timestamp": "2026-09-24T06:55:00",
        },
        {
            "role": "tool",
            "tool_call_id": "c1",
            "content": "[BEGIN UNTRUSTED read_file #1]\n[failed] Error: nope\n[END UNTRUSTED read_file #1]",
            "timestamp": "2026-09-24T06:55:01",
        },
        {
            "role": "assistant",
            "content": "Done",
            "tool_calls": [{"id": "c2", "function": {"name": "write_file", "arguments": "{}"}}],
        },
    ]
    (sub / "nodes" / "deck.transcript.jsonl").write_text("".join(json.dumps(row) + "\n" for row in transcript))
    (sub / "nodes" / "deck.out.md").write_text("# Deck built")
    (sub / "nodes" / "deck.attempt-1.out.md").write_text("first")
    (sub / "nodes" / "deck.attempt-1.prompt.md").write_text("first prompt")
    prompt = "Build the deck " + KEY
    with log.open("a") as stream:
        for row in (
            {
                "kind": "dag.progress",
                "name": "dag_node_updated",
                "payload": {
                    "run_id": "dag-1",
                    "node": "deck",
                    "status": "completed",
                    "started_at": 1_000,
                    "ended_at": 9_000,
                },
            },
            {
                "kind": "provider.request",
                "parameters": {
                    "messages": [
                        {"role": "system", "content": "You decide whether a sub-agent accomplished the task"},
                        {
                            "role": "user",
                            "content": f"The task the sub-agent was given:\n[BEGIN UNTRUSTED subagent #9]\n{prompt}\n[END UNTRUSTED subagent #9]",
                        },
                    ]
                },
            },
            {
                "kind": "provider.response",
                "response": {
                    "content": "It did.",
                    "tool_calls": [{"id": "v", "name": "report_verdict", "arguments": {"outcome": "accomplished"}}],
                    "call_record": {"headers": {"authorization": "Bearer " + "x" * 30}},
                },
            },
        ):
            stream.write(json.dumps(row) + "\n")
    reply = node_process(worker, [state], "dag-1", "deck")
    assert reply["source"] == "transcript" and reply["status"] == "completed"
    assert [step["kind"] for step in reply["steps"]] == ["thought", "tool", "message", "tool"]
    assert reply["steps"][1]["status"] == "failed" and reply["steps"][1]["result"].startswith("[failed] Error")
    assert reply["steps"][3]["status"] == "no result"
    assert reply["output"] == "# Deck built" and reply["attempts"] == [1]
    assert reply["verdicts"] == [{"outcome": "accomplished", "reason": "It did."}]
    assert "authorization" not in json.dumps(reply) and "Bearer" not in json.dumps(reply)
    first = node_process(worker, [state], "dag-1", "deck", attempt=1)
    assert first["output"] == "first" and first["prompt"] == "first prompt" and first["attempt"] == 1


def test_an_in_process_node_reads_its_latest_model_call(tmp_path):
    root, worker, sub, log, state, frames = build(tmp_path, subagent="Raven")
    prompt = "Build the deck " + KEY

    def call(extra):
        messages = [{"role": "system", "content": "# Subagent\n\nctx"}, {"role": "user", "content": prompt}, *extra]
        return {"kind": "provider.request", "parameters": {"messages": messages}}

    first = [
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "c1", "function": {"name": "list_dir", "arguments": '{"path": "out"}'}}],
        }
    ]
    second = first + [{"role": "tool", "tool_call_id": "c1", "content": "deck.pptx"}]
    with log.open("a") as stream:
        stream.write(json.dumps(call(first)) + "\n" + json.dumps(call(second)) + "\n")
    reply = node_process(worker, [state], "dag-1", "deck")
    assert reply["source"] == "provider" and reply["lane"] == "in-process"
    assert [(step["kind"], step["status"]) for step in reply["steps"]] == [("tool", "completed")]
    assert reply["steps"][0]["title"] == "list_dir: out"


def test_node_lookups_refuse_traversal_and_unknown_names(tmp_path):
    root, worker, sub, log, state, frames = build(tmp_path)
    for dag, node in (
        ("../dag-1", "deck"),
        ("dag-1", "../deck"),
        ("dag-1", "de/ck"),
        ("dag-1", ".."),
        ("", "deck"),
        ("dag-1", "nope"),
    ):
        assert node_process(worker, [state], dag, node) is None
    assert serve.node(root, "../run/r1", [state], "dag-1", "deck") is None
    assert serve.node(root, "run/r1", [state], "dag-1", "deck")["node"] == "deck"


def test_journals_are_read_only_under_the_state_root(tmp_path):
    root, worker, sub, log, state, frames = build(tmp_path)
    outside = tmp_path / "elsewhere" / "Raven-PPT-065427000000.jsonl"
    outside.parent.mkdir()
    outside.write_text(json.dumps({"_type": "acp_call", "task_id": "deck"}) + "\n")
    (frames / "Raven-PPT-065428000000.jsonl").symlink_to(outside)
    manifest = {"deck": {"status": "running", "acp_frames": {"path": str(outside)}}}
    (sub / "mas_dag" / "dag-1" / "manifest.json").write_text(json.dumps(manifest))
    reply = node_process(worker, [state], "dag-1", "deck")
    assert reply["available"]["journal"] is False and reply["lane"] is None


def test_a_journal_without_a_call_row_is_matched_by_its_name_and_the_node_start(tmp_path):
    root, worker, sub, log, state, frames = build(tmp_path)
    from datetime import datetime

    started = int(datetime(2026, 9, 24, 6, 54, 27).timestamp() * 1000)
    rows = log.read_text().replace('"started_at": 1000', f'"started_at": {started}')
    log.write_text(rows)
    (frames / "Raven-PPT-065427500000.jsonl").write_text(
        json.dumps({"_type": "acp_frame", "timestamp": "2026-09-24T06:54:28", "dir": "err", "text": "[run] starting"})
        + "\n"
    )
    (frames / "Raven-PPT-070000000000.jsonl").write_text(
        json.dumps({"_type": "acp_frame", "dir": "err", "text": "later"}) + "\n"
    )
    reply = node_process(worker, [state], "dag-1", "deck")
    assert reply["source"] == "journal" and reply["steps"][0]["text"] == "[run] starting"


def test_subharness_homes_leave_out_sessions_hidden_and_secret_files(tmp_path):
    root, worker, sub, log, state, frames = build(tmp_path)
    home = worker / "employee" / "home" / "subagents" / "Raven-PPT"
    for path, text in {
        "TOOLS.md": "Use the template " + KEY,
        "agent_memory/profile/agent.md": "Agent",
        "sessions/x/1.jsonl": "{}",
        "memory/.curator/traces/t.jsonl": "{}",
        "config.json": "{}",
        "credentials/key.txt": KEY,
        ".env": "A=1",
        "data.json": "{}",
    }.items():
        file = home / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text)
    homes = subharness_homes(worker)
    assert [home["name"] for home in homes] == ["Raven-PPT"]
    files = {row["path"]: row for row in homes[0]["files"]}
    assert sorted(files) == ["TOOLS.md", "agent_memory/profile/agent.md", "data.json"]
    assert files["TOOLS.md"]["text"] == "Use the template <redacted>" and "text" not in files["data.json"]


def test_redact_covers_keys_tokens_and_nesting():
    assert redact({"a": [f"x {KEY} y", "jina_" + "b" * 25, HEX, "Bearer " + "c" * 20, "g" + HEX]}) == {
        "a": ["x <redacted> y", "<redacted>", "<redacted>", "<redacted>", "g" + HEX]
    }


def test_live_lists_kept_deliveries_newest_first_and_keeps_delivery_metadata(tmp_path):
    root, worker, sub, log, state, frames = build(tmp_path)
    for turn, name, age in (("t1", "deck.pptx", 100), ("t2", "plan.html", 10)):
        file = worker / "deliverables" / turn / name
        file.parent.mkdir(parents=True)
        file.write_bytes(b"x")
        os.utime(file, (time.time() - age, time.time() - age))
    (worker / "deliverables" / "t1" / "deck.pptx.thumbs").mkdir()
    reply = serve.live(root, "run/r1")
    assert [(row["turn"], row["name"]) for row in reply["deliveries"]] == [("t2", "plan.html"), ("t1", "deck.pptx")]
    row = serve.compact(
        {
            "kind": "runner.event",
            "turn_id": "t1",
            "event_type": "ToolEvent",
            "event": {
                "phase": "complete",
                "tool_call_id": "c",
                "ok": True,
                "result_preview": "Delivered",
                "metadata": {
                    "raven_delivery": {
                        "message": "Here",
                        "files": [{"path": "/tmp/work/deck.pptx", "name": "deck.pptx", "title": "Deck"}],
                    }
                },
            },
        }
    )
    assert row["event"]["delivery"] == {
        "message": "Here",
        "files": [{"name": "deck.pptx", "title": "Deck", "description": None, "size": None, "media_type": None}],
    }
