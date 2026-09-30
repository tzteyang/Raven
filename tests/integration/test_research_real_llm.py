"""Opt-in checks of the research stage on real models and the real web.

The first hands over the bundled travel agency without its service SOP and its deck spec, with a model playing the
owner who knows both: the stage must read rules from the consultation scripts and the deck sample alone, have the
owner decide every one, and write a scenario the loader reads with its provenance, in which the evaluation side
draws on the confirmed rules and never on the undecided ones, and the owner still holds what it held back.

The second holds back every fact of the travel agency, so the facts slot is empty, and researches it on the web
(`RESEARCH_TEST_RESEARCHER`: exchange, claude or codex; exchange by default): every finding written must stand on a
passage of a page the stage read again, and the owner, who knows the facts it held back, settles each one.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from experimental.research.inquiry import QUOTE, folded
from experimental.research.package import CANDIDATES, CONFIRMED, RESEARCHED
from experimental.scenario import load
from experimental.simulation.agency import Agency as Owner
from experimental.simulation.scenario import BUNDLED
from experimental.simulation.scenario import Scenario as Agency

pytestmark = [pytest.mark.integration, pytest.mark.real_llm, pytest.mark.slow]

REPOSITORY = Path(__file__).resolve().parents[2]
WITHHELD = ["plan-deck-spec", "service-sop"]


def test_rules_read_from_the_travel_agency_examples_are_settled_by_the_owner_who_knows_the_withheld_norms(tmp_path):
    config = os.environ.get("RESEARCH_TEST_CONFIG")
    if not config:
        pytest.skip("Set RESEARCH_TEST_CONFIG to run an authorized paid research stage.")
    out, records = tmp_path / "out", tmp_path / "records"
    command = [
        sys.executable,
        "-m",
        "experimental.research",
        "--scenario",
        str(BUNDLED / "travel_agency"),
        "--out",
        str(out),
        "--records",
        str(records),
        "--config",
        str(Path(config).expanduser().resolve()),
        "--effort",
        os.environ.get("RESEARCH_TEST_EFFORT", "low"),
        "--without",
        *WITHHELD,
        "--party-knows",
        *WITHHELD,
    ]
    done = subprocess.run(command, cwd=REPOSITORY, capture_output=True, text=True, timeout=1800)
    assert done.returncode == 0, done.stdout[-4000:] + done.stderr[-4000:]
    researched = load(out)
    record = researched.provenance.record
    assert record["input"]["without"] == WITHHELD and not set(WITHHELD) & set(researched.handed)
    assert all(researched.materials[name].visibility == frozenset({"party"}) for name in WITHHELD)
    assert record["rules"], "the scripts and the sample show rules the remaining norms do not state"
    assert all(set(rule["sources"]) <= {"consultation-scripts", "plan-deck-sample"} for rule in record["rules"])
    assert record["calls"]["confirmation"] == {**record["calls"]["confirmation"], "by": "model", "knows": WITHHELD}
    agency = Agency.of(researched)
    standing = agency.standing_norms(agency.handed)
    assert (CONFIRMED in standing) == (CONFIRMED in researched.materials) and CANDIDATES not in standing
    assert Owner(agency, None, tmp_path / "skills", workdir=tmp_path, deliver="pool").rules is not None
    calls = [json.loads(line)["kind"] for line in (records / "provider.jsonl").read_text().splitlines()]
    assert calls.count("provider.request") >= 2 and "provider.error" not in calls


FACTS = ["handover-ticket", "price-list", "value-package", "comfort-package", "premium-package", "plan-deck-template"]


def test_the_travel_agencys_empty_facts_slot_is_researched_on_the_web_and_settled_by_the_owner(tmp_path):
    config = os.environ.get("RESEARCH_TEST_CONFIG")
    if not config:
        pytest.skip("Set RESEARCH_TEST_CONFIG, with web search keys, to run an authorized paid research stage.")
    researcher = os.environ.get("RESEARCH_TEST_RESEARCHER", "exchange")
    out, records = tmp_path / "out", tmp_path / "records"
    command = [
        sys.executable,
        "-m",
        "experimental.research",
        "--scenario",
        str(BUNDLED / "travel_agency"),
        "--out",
        str(out),
        "--records",
        str(records),
        "--config",
        str(Path(config).expanduser().resolve()),
        "--effort",
        os.environ.get("RESEARCH_TEST_EFFORT", "low"),
        "--without",
        *FACTS,
        "--party-knows",
        *FACTS,
        "--research",
        researcher,
        "--findings",
        "4",
    ]
    done = subprocess.run(command, cwd=REPOSITORY, capture_output=True, text=True, timeout=3600)
    assert done.returncode == 0, done.stdout[-4000:] + done.stderr[-4000:]
    researched = load(out)
    record = researched.provenance.record
    assert record["findings"], "the web tells something the travel agency's work depends on"
    pages = {}
    for row in (json.loads(line) for line in (records / "web.jsonl").read_text().splitlines()):
        pages.setdefault(row["url"], row) if row["tool"] == "read" else None
    for finding in record["findings"]:
        assert set(finding["sources"]) <= set(pages) and finding["decision"]["status"] in (
            "confirmed",
            "amended",
            "rejected",
            "undecided",
        )
        written = [name for name, origin in record["materials"].items() if finding["id"] in origin.get("items", ())]
        assert written or finding["decision"]["status"] == "rejected"
    assert all(len(folded(finding["evidence"])) >= QUOTE for finding in record["findings"])
    assert all(row["reasons"] for row in record["refused"])
    assert {name for name in researched.materials if name in RESEARCHED.values()} <= set(researched.handed)
    assert record["calls"]["research"]["researcher"] == researcher
    assert not set(FACTS) & set(researched.handed)
