"""Every bundled case reads as a scenario, schedules only its own cards and brings the owner that judges it."""

import pytest

from experimental.harness.scenario.contract import load
from experimental.simulation.__main__ import owner_of
from experimental.simulation.bench.scenario import BUNDLED, Scenario

CASES = sorted(path.name for path in BUNDLED.iterdir() if (path / "scenario.json").is_file())


@pytest.mark.parametrize("name", CASES)
def test_a_bundled_case_loads_and_is_judged_by_its_own_owner(name):
    read = load(BUNDLED / name)
    scenario = Scenario.load(BUNDLED / name)
    assert scenario.personas and read.materials
    scheduled = {case for step in read.situation.schedule.rounds for case in step} | set(
        read.situation.schedule.holdout
    )
    assert scheduled <= {case.id for case in read.situation.cases}
    if (BUNDLED / name / "owner.py").is_file():
        assert owner_of(scenario).__module__ == f"experimental.simulation.cases.{name}.owner"
