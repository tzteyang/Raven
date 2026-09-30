"""Opt-in end-to-end check of the compartments: one real simulated round leaves no boundary violation.

The run goes through the simulation entry as a separate process, on the bundled travel agency with one drill card:
onboarding, one drill on a replica, the owner's review, the automatic assessor and the Analyst. Its boundaries log
must show the Curator's and the Analyst's compartments entered and left, the customer's and the owner's entered, and
no violation from any guard, the partner's included.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.real_llm, pytest.mark.slow]

REPOSITORY = Path(__file__).resolve().parents[2]


def test_one_simulated_round_crosses_no_boundary(tmp_path):
    config = os.environ.get("SIMULATION_TEST_CONFIG")
    if not config:
        pytest.skip("Set SIMULATION_TEST_CONFIG to run an authorized paid simulated round.")
    state = tmp_path / "run"
    command = [
        sys.executable,
        "-m",
        "experimental.simulation",
        "--config",
        str(Path(config).expanduser().resolve()),
        "--state-dir",
        str(state),
        "--workdir",
        str(tmp_path / "work"),
        "--scenario",
        "travel_agency",
        "--chain",
        "documents",
        "--rounds",
        "1",
        "--turns",
        "2",
        "--cards",
        "student",
        "--curator-effort",
        os.environ.get("SIMULATION_TEST_EFFORT", "low"),
        "--simulation-effort",
        "low",
        "--traveller-effort",
        "low",
        "--standard",
        "declared",
        "--curator-calls",
        os.environ.get("SIMULATION_TEST_CURATOR_CALLS", "120"),
        "--curator-queries",
        os.environ.get("SIMULATION_TEST_CURATOR_QUERIES", "160"),
        "--timeout",
        "600",
    ]
    done = subprocess.run(command, cwd=REPOSITORY, capture_output=True, text=True, timeout=3600)
    assert done.returncode == 0, done.stdout[-4000:] + done.stderr[-4000:]
    rows = [json.loads(line) for line in (state / "boundaries.jsonl").read_text().splitlines()]
    assert not [row for row in rows if row["event"] == "violation"], rows
    (record,) = (state / "iteration").glob("*.json")
    run = json.loads(record.read_text())
    assert run["status"] == "finished" and len(run["rounds"]) == 1, (run["status"], run.get("stop"), run.get("error"))
    entered = {(row["role"], row["event"]) for row in rows}
    assert {("curator", "enter"), ("curator", "leave"), ("analyst", "enter"), ("analyst", "leave")} <= entered
    assert {("conversant", "enter"), ("party", "enter")} <= entered, "the customer and the owner call in their own"
    assert run["history"][0]["diagnoses"], "the onboarding entry keeps the Curator's diagnoses"
