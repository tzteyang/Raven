"""The run's evaluation reads which owner rules its requirements restate before it reads its interventions, and the
record links a requirement without a check ground only through that recorded reading."""

import json

import pytest

from experimental.simulation.attribution import CONCERNS, NAME, RESULT, read_requirements, write
from experimental.simulation.record import build_record
from raven.contracts.llm_provider import LLMResponse, ToolCallRequest
from tests.test_simulation_record import by_id, make_run


class Provider:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    async def chat_with_retry(self, **kwargs):
        self.requests.append(kwargs)
        answer = self.responses.pop(0)
        return answer(kwargs) if callable(answer) else answer


def response(name, arguments):
    return LLMResponse(content=None, tool_calls=[ToolCallRequest(name, name, arguments)])


@pytest.mark.asyncio
async def test_only_requirements_without_a_check_ground_are_read_and_the_reading_names_known_rules(tmp_path):
    run, scenario = make_run(tmp_path)
    record = build_record(run, scenario)
    provider = Provider(
        response(CONCERNS, {"requirements": [{"id": "R3", "rules": ["no-such-rule"]}]}),
        response(CONCERNS, {"requirements": [{"id": "R3", "rules": ["tone-warm"]}, {"id": "R1", "rules": []}]}),
        response(CONCERNS, {"requirements": [{"id": "R3", "rules": ["question-limit"]}]}),
    )
    assert await read_requirements(record, provider) == {"R3": ["question-limit"]}
    told = json.loads(provider.requests[0]["messages"][1]["content"])
    assert [row["id"] for row in told["requirements"]] == ["R3"] and told["requirements"][0][
        "behavior"
    ] == "Sound warm."
    assert {rule["id"] for rule in told["rules"]} == {entry["criterion"] for entry in record["ledger"]}
    rejected = [
        json.loads(row["content"])["error"] for row in provider.requests[2]["messages"] if row["role"] == "tool"
    ]
    assert "may name only the rules given" in rejected[0] and "exactly one entry per requirement id" in rejected[1]


@pytest.mark.asyncio
async def test_the_record_links_a_requirement_by_reading_and_the_interventions_are_read_after_it(tmp_path):
    run, scenario = make_run(tmp_path)
    (run / RESULT).write_text(json.dumps({"requirements": {"R3": ["question-limit"]}}))
    read = {
        requirement["id"]: requirement
        for requirement in build_record(run, scenario)["rounds"][0]["analysis"]["requirements"]
    }
    assert (read["R3"]["link"], read["R3"]["criteria"]) == ("reading", ["question-limit"])
    assert (read["R1"]["link"], read["R2"]["link"]) == ("grounds", "grounds")
    (run / RESULT).unlink()
    assert by_id(build_record(run, scenario)["rounds"][0]["analysis"]["requirements"], "id")["R3"]["link"] == "none"

    def enforces_nothing(request):
        asked = json.loads(request["messages"][1]["content"])["interventions"]
        return response(NAME, {"links": [{"id": row["id"], "rules": []} for row in asked]})

    provider = Provider(
        response(CONCERNS, {"requirements": [{"id": "R3", "rules": ["question-limit"]}]}), enforces_nothing
    )
    result = await write(run, provider, scenario_dir=scenario)
    saved = json.loads((run / RESULT).read_text())
    assert saved["requirements"] == result["requirements"] == {"R3": ["question-limit"]}
    assert saved["interventions"] == result["interventions"] > 0 and all(not rules for rules in saved["links"].values())
    assert [request["tools"][0]["function"]["name"] for request in provider.requests] == [CONCERNS, NAME]
