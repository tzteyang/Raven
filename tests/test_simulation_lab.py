"""A drill's lab copy is named where the on-call colleague looks, and lab script runs are recognised as written."""

import asyncio
import json
import sys
from pathlib import Path

import pytest

from experimental.simulation.bench.lab import declared_runs, invokes, lab_placement, replica_lab, script_run
from raven.agent.tools.machine_exec import run_on_machine

PLUGIN_DIR = Path(__file__).resolve().parents[1] / "agents" / "raven-oncall" / "plugins" / "oncall-flow"
sys.path.insert(0, str(PLUGIN_DIR))

from oncall_flow import connections  # noqa: E402

SCRIPT = "probe.py"


@pytest.fixture
def lab(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / SCRIPT).write_text("import os, sys\nprint(os.getcwd(), *sys.argv[1:])\n")
    registry = tmp_path / "template.json"
    registry.write_text(
        json.dumps(
            {
                "connections": [
                    {
                        "id": "local-lab",
                        "display_name": "Local lab",
                        "transport": "local",
                        "software": "Python 3 (run it as python3)",
                        "paths": ["/original"],
                    }
                ]
            }
        )
    )
    return source, registry


def test_each_replica_names_its_own_lab_path_in_the_listing_the_colleague_reads(lab, tmp_path, monkeypatch):
    source, registry = lab
    first, second = (replica_lab(source, tmp_path / name, registry) for name in ("first", "second"))
    first_work, second_work = lab_placement(first)["workdir"], lab_placement(second)["workdir"]
    assert first_work != second_work
    monkeypatch.setenv("RAVEN_CONNECTIONS", str(first))
    listing = connections.describe()
    assert f"The department's scripts live in {first_work};" in listing
    assert str(second_work) not in listing
    monkeypatch.setenv("RAVEN_CONNECTIONS", str(second))
    assert f"The department's scripts live in {second_work};" in connections.describe()
    assert "note" not in json.loads(registry.read_text())["connections"][0]


def test_the_named_path_runs_the_script_where_the_bare_command_cannot(lab, tmp_path, monkeypatch):
    source, registry = lab
    work = lab_placement(replica_lab(source, tmp_path / "drill", registry))["workdir"]
    monkeypatch.setenv("RAVEN_CONNECTIONS", str(tmp_path / "drill" / "connections.json"))
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    bare = asyncio.run(run_on_machine(f"python3 {SCRIPT} read", connection="local-lab"))
    placed = asyncio.run(run_on_machine(f"python3 {SCRIPT} read", connection="local-lab", cwd=str(work)))
    assert "(exit 2)" in bare
    assert "(exit 0)" in placed and f"{work} read" in placed


@pytest.mark.parametrize(
    ("command", "working_dir", "script_path", "arguments"),
    [
        ("python3 probe.py read a.md", "/lab", "/lab/probe.py", ("read", "a.md")),
        ("cd /lab && python3 probe.py read a.md", None, "/lab/probe.py", ("read", "a.md")),
        ("cd /lab; python3 probe.py read a.md", None, "/lab/probe.py", ("read", "a.md")),
        ("python3 /lab/probe.py read a.md 2>&1", None, "/lab/probe.py", ("read", "a.md")),
        ("sleep 55 && python3 -u probe.py read a.md", "/lab", "/lab/probe.py", ("read", "a.md")),
        ("sleep 40; cd /lab && python3 probe.py --queue q 2>/dev/null", None, "/lab/probe.py", ("--queue", "q")),
        ("cd lab && python3 probe.py read a.md", "/base", "/base/lab/probe.py", ("read", "a.md")),
        ("python3 probe.py read a.md", None, None, ("read", "a.md")),
        ('cd "/my lab" && python3 probe.py read "a b.md"', None, "/my lab/probe.py", ("read", "a b.md")),
    ],
)
def test_a_reading_is_recognised_in_the_spellings_a_colleague_uses(command, working_dir, script_path, arguments):
    run = script_run(command, SCRIPT, working_dir)
    assert run is not None and run.arguments == arguments
    assert run.script_path == (Path(script_path) if script_path else None)


def test_relative_arguments_resolve_against_the_directory_the_script_ran_in():
    run = script_run("cd /lab && python3 probe.py --queue shared/queue", SCRIPT, "/elsewhere")
    assert run.path("shared/queue") == Path("/lab/shared/queue")
    assert run.path("/abs/queue") == Path("/abs/queue")
    assert script_run("python3 /lab/probe.py --queue q", SCRIPT).path("q") is None


@pytest.mark.parametrize(
    "command",
    [
        "python3 probe.py read a.md | head",
        "cat feed.md; python3 probe.py read a.md",
        "python3 probe.py read a.md; python3 probe.py read b.md",
        "python3 probe.py read a.md > out.txt",
        "python3 probe.py read a.md 2 >&1",
        "python3 other.py read a.md",
        "echo python3 probe.py read a.md",
        "echo ';' python3 probe.py read a.md",
    ],
)
def test_a_command_doing_anything_else_is_not_a_reading(command):
    assert script_run(command, SCRIPT, "/lab") is None


def test_attempts_and_campaign_readings_are_found_without_being_bound():
    assert invokes("python3 probe.py read a.md | head", SCRIPT)
    assert not invokes("echo python3 probe.py", SCRIPT)
    assert not invokes("echo ';' python3 probe.py", SCRIPT)
    table = {
        "readings": [
            {"name": "board", "command": "cd /lab && python3 probe.py read a.md", "when": "each_wake"},
            {"name": "disk", "command": "df -h", "when": "each_wake"},
        ]
    }
    assert declared_runs(table, SCRIPT) == ["cd /lab && python3 probe.py read a.md"]
    assert declared_runs({}, SCRIPT) == []
