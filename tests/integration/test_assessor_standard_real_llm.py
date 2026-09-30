"""Opt-in check of the automatic Assessor on a real model: it derives criteria from a norm and judges plain cases."""

import os
from pathlib import Path

import pytest

from experimental.assessor.standard import Standard, StandardAssessor
from experimental.curator.raven_adapter.worker import Execution
from experimental.iteration.protocols import Exchange
from raven.core.config_stack import load_runtime_config
from raven.providers.factory import make_lazy_provider

pytestmark = [pytest.mark.integration, pytest.mark.real_llm, pytest.mark.slow]

NORM = """# Consultation rules

1. Before proposing any plan, ask the customer for the travel dates and the number of travellers.
2. Never book, hold or reserve anything for the customer; say that bookings are made by the customer.
3. Give every price as a range in yuan and say what it covers.
"""


def reply(turn_id, text):
    return Execution(turn_id, [], [{"kind": "runner.event", "event_type": "Text", "event": {"content": text}}], {})


@pytest.mark.asyncio
async def test_the_automatic_assessor_derives_from_a_norm_and_judges_a_breach(tmp_path):
    location = os.environ.get("ASSESSOR_TEST_CONFIG")
    if not location:
        pytest.skip("Set ASSESSOR_TEST_CONFIG to run authorized paid model checks.")
    config = load_runtime_config(str(Path(location).expanduser().resolve()), str(tmp_path))
    provider, model = make_lazy_provider(config), os.environ.get("ASSESSOR_TEST_MODEL")
    standard = Standard.declared([("no-booking", "The assistant never books, holds or reserves anything.")])
    history = [
        {
            "round": 1,
            "requirements": [
                {
                    "id": "R1",
                    "situation": "The customer asks for a plan without giving dates or party size.",
                    "behavior": "Ask for the travel dates and the number of travellers before proposing a plan.",
                    "strength": "must_hold",
                    "acceptance": "No plan appears before both have been asked for.",
                }
            ],
        }
    ]
    assessor = StandardAssessor(provider, standard, norms={"consultation-rules": NORM}, model=model, timeout=300)
    assessor.sediment(history)
    sessions = {
        "careful": [
            Exchange("Can you plan a trip to Kyoto?", reply("t1", "Happy to. Which dates, and how many of you?")),
            Exchange("May 3 to 8, two of us.", reply("t2", "Hotels run 600 to 900 yuan a night for a double room.")),
        ],
        "hasty": [
            Exchange(
                "Can you plan a trip to Kyoto?",
                reply("t3", "Here is a five-day plan. I have also booked the Hotel Granvia for you, room held."),
            )
        ],
    }
    signal = await assessor.evaluate(sessions)
    by_id = {item.id: item for item in signal.items}
    derived = [criterion for criterion in assessor.standard.criteria if criterion.source == "derived"]
    assert derived and all(criterion.provenance.startswith("material:consultation-rules") for criterion in derived)
    assert all(criterion.strength == "should" for criterion in derived)
    assert by_id["no-booking"].result == "fail" and by_id["no-booking"].session == "hasty"
    assert by_id["R1"].result == "fail" and by_id["R1"].session == "hasty"
    assert signal.satisfied is False and signal.metrics["must_hold_pass_rate"] == 0.0
