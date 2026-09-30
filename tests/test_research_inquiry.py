"""A research is held to what it read, whoever researched it: a finding stands only on a passage of a page the stage
can read again, names only materials that were handed over, and carries nothing sealed from a reader of norms."""

import json
import os
import stat
import sys

import pytest

from experimental.research import inquire
from experimental.research.induction import AUDIENCE
from experimental.research.inquiry import NAME, Inquiry, brief, quoted, verify
from experimental.research.researchers import Agent, Exchange, ResearchError, strict
from experimental.research.web import READ
from experimental.scenario import load
from experimental.scenario.sealed import sealed_for
from tests.test_research_induction import CHECK, Provider, make_scenario, response

PAGE = "https://tea.example/guide"
TEXT = "Afternoon Tea\n\nAfternoon tea is served from two to five, and scones come with clotted cream."
FOUND = {
    "question": "When is afternoon tea served?",
    "kind": "fact",
    "text": "Afternoon tea is served from two to five.",
    "situation": "",
    "sources": [PAGE],
    "evidence": "afternoon tea is served from two to five",
    "conflicts": [],
}


def rejections(request) -> list[str]:
    rows = [json.loads(row["content"]) for row in request["messages"] if row["role"] == "tool"]
    return [row["error"] for row in rows if "error" in row]


class Pages:
    """A web whose pages are given; `read` and `search` answer like the stage's own."""

    def __init__(self, pages=None):
        self.known, self.pages, self.asked = dict(pages or {}), {}, []

    def tools(self):
        return [
            {"type": "function", "function": {"name": "search", "parameters": {}}},
            {"type": "function", "function": {"name": READ, "parameters": {}}},
        ]

    def queries(self):
        return {"search": self.search, READ: self.read}

    async def search(self, arguments):
        return {"results": f"1. Tea guide\n   {PAGE}"}

    async def read(self, arguments):
        text = await self.page(arguments["url"])
        return {"url": arguments["url"], "text": text} if text else {"url": arguments["url"], "error": "no page"}

    async def page(self, url):
        self.asked.append(url)
        if url in self.known:
            self.pages[url] = self.known[url]
        return self.pages.get(url)


def seals(scenario):
    return {role: sealed_for(scenario, role) for role in AUDIENCE}


def test_a_passage_is_quoted_when_the_page_holds_it_whole_whatever_its_case_width_punctuation_or_links():
    assert quoted("Afternoon tea is served from two to five", TEXT)
    assert quoted("AFTERNOON TEA \u2014 is served, from two to five\uff01", TEXT)
    assert quoted("see the tea menu for scones", "See [the tea menu](https://tea.example/menu) for scones.")
    assert not quoted("afternoon tea is served from two to five. This means a short visit fits the afternoon.", TEXT)
    assert not quoted("afternoon tea is served from two to five and scones come with cream", TEXT)
    assert not quoted("tea is served from noon", TEXT) and not quoted("two to five", TEXT)
    assert quoted("the entry fee is 50 euros", "The entry fee is 50 euros.")
    assert not quoted("the entry fee is 5 euros", "The entry fee is 50 euros.")
    assert not quoted("the entry fee is 50", "The entry fee is 500 euros.")


def test_the_brief_holds_what_every_norm_reader_may_receive_and_never_a_check_or_a_case(tmp_path):
    scenario = load(make_scenario(tmp_path / "shop"))
    told = brief(scenario, ["When is tea served?"], 3)
    assert sorted((row["name"], row["kind"]) for row in told["materials"]) == [
        ("bad-reply", "counterexample"),
        ("good-reply", "exemplar"),
        ("prices", "fact"),
        ("sop", "norm"),
    ]
    assert told["questions"] == ["When is tea served?"] and told["at_most"] == 3
    text = json.dumps(told)
    assert CHECK not in text and "afternoon tea for two" not in text and "Discounts above" not in text


@pytest.mark.asyncio
async def test_only_findings_on_a_passage_of_a_page_read_again_stand_and_the_rest_are_refused_with_why(tmp_path):
    scenario = load(make_scenario(tmp_path / "shop"))
    web = Pages({PAGE: TEXT})
    inquiry = Inquiry.model_validate(
        {
            "findings": [
                FOUND,
                {**FOUND, "sources": ["https://gone.example"]},
                {**FOUND, "evidence": "Tea is served all day long, every day."},
                {**FOUND, "conflicts": ["owner-policy"]},
                {**FOUND, "text": CHECK},
                {
                    **FOUND,
                    "kind": "norm",
                    "text": "Serve scones with clotted cream.",
                    "evidence": "scones come with clotted cream",
                },
            ],
            "unanswered": [{"question": "What does the shop charge?", "why": "only the shop knows its prices"}],
        }
    )
    found = await verify(inquiry, web, materials=["sop", "prices"], sealed=seals(scenario), limit=1, prefix="answer")
    assert [(finding.id, finding.kind) for finding in found.findings] == [("answer-1", "fact")]
    reasons = [row["reasons"] for row in found.refused]
    assert "not read or could not be read" in reasons[0][0] and "not a passage" in reasons[1][0]
    assert "not handed over" in reasons[2][0] and "neither the pages" in reasons[3][0]
    assert reasons[4] == ["over the limit of 1 findings"]
    assert found.unanswered == ({"question": "What does the shop charge?", "why": "only the shop knows its prices"},)
    assert web.asked.count(PAGE) == 1 and "https://gone.example" in web.asked


@pytest.mark.asyncio
async def test_the_stages_own_model_corrects_a_finding_until_it_quotes_a_page_it_read(tmp_path):
    scenario = load(make_scenario(tmp_path / "shop"))
    provider = Provider(
        response(NAME, {"findings": [FOUND]}),
        response(READ, {"url": PAGE}),
        response(NAME, {"findings": [FOUND]}),
    )
    found = await inquire(Exchange(provider, max_calls=4), scenario, Pages({PAGE: TEXT}), sealed=seals(scenario))
    assert [finding.text for finding in found.findings] == [FOUND["text"]] and not found.refused
    assert "sources were not read" in rejections(provider.requests[1])[0]
    told = json.loads(provider.requests[0]["messages"][1]["content"])
    assert told["questions"] == [] and CHECK not in json.dumps(told)
    assert {tool["function"]["name"] for tool in provider.requests[0]["tools"]} == {"search", READ, NAME}
    assert found.run["researcher"] == "exchange"


def test_a_strict_schema_requires_every_field_and_allows_no_other():
    schema = strict({"type": "object", "properties": {"a": {"type": "string", "default": ""}}, "required": []})
    assert schema == {
        "type": "object",
        "properties": {"a": {"type": "string"}},
        "required": ["a"],
        "additionalProperties": False,
    }


def fake(tmp_path, monkeypatch, name, script):
    folder = tmp_path / "bin"
    folder.mkdir(exist_ok=True)
    path = folder / name
    path.write_text(f"#!{sys.executable}\n{script}")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{folder}{os.pathsep}{os.environ['PATH']}")
    return tmp_path / f"{name}.args"


@pytest.mark.asyncio
async def test_claude_code_researches_restricted_to_the_web_and_answers_in_the_schema(tmp_path, monkeypatch):
    scenario = load(make_scenario(tmp_path / "shop"))
    answer = {"type": "result", "subtype": "success", "is_error": False, "total_cost_usd": 0.2, "num_turns": 5}
    kept = fake(
        tmp_path,
        monkeypatch,
        "claude",
        "import json, os, sys\n"
        f"open({str(tmp_path / 'claude.args')!r}, 'w').write(json.dumps({{'argv': sys.argv[1:], 'cwd': os.getcwd(), "
        "'prompt': sys.stdin.read()}))\n"
        f"print(json.dumps({{**{answer!r}, 'structured_output': {{'findings': [{FOUND!r}], 'unanswered': []}}}}))\n",
    )
    found = await inquire(Agent("claude", model="sonnet", budget=1.5), scenario, Pages({PAGE: TEXT}))
    assert [finding.id for finding in found.findings] == ["researched-1"] and found.run["cost_usd"] == 0.2
    ran = json.loads(kept.read_text())
    argv = ran["argv"]
    assert argv[:2] == ["-p", "--restricted"] and argv[argv.index("--tools") + 1 : argv.index("--tools") + 3] == [
        "WebSearch",
        "WebFetch",
    ]
    assert {"--strict-mcp-config", "--no-session-persistence"} <= set(argv)
    assert argv[argv.index("--model") + 1] == "sonnet" and argv[argv.index("--max-budget-usd") + 1] == "1.5"
    schema = json.loads(argv[argv.index("--json-schema") + 1])
    assert schema["required"] == ["findings", "unanswered"]
    assert "raven-research-claude-" in ran["cwd"] and '"questions": []' in ran["prompt"] and CHECK not in ran["prompt"]


@pytest.mark.asyncio
async def test_a_research_agent_that_fails_or_answers_outside_the_schema_ends_the_research(tmp_path, monkeypatch):
    scenario = load(make_scenario(tmp_path / "shop"))
    fake(
        tmp_path,
        monkeypatch,
        "claude",
        "import json\nprint(json.dumps({'is_error': True, 'result': 'budget exceeded', 'subtype': 'error_max_budget_usd'}))\n",
    )
    with pytest.raises(ResearchError, match="budget exceeded"):
        await inquire(Agent("claude"), scenario, Pages())
    fake(tmp_path, monkeypatch, "claude", "import sys\nsys.exit(3)\n")
    with pytest.raises(ResearchError, match="exited with 3"):
        await inquire(Agent("claude"), scenario, Pages())
    with pytest.raises(ValueError, match="unknown research agent"):
        Agent("gemini")


@pytest.mark.asyncio
async def test_codex_researches_with_live_search_in_its_read_only_sandbox(tmp_path, monkeypatch):
    scenario = load(make_scenario(tmp_path / "shop"))
    kept = fake(
        tmp_path,
        monkeypatch,
        "codex",
        "import json, sys\n"
        "argv = sys.argv[1:]\n"
        f"open({str(tmp_path / 'codex.args')!r}, 'w').write(json.dumps(argv))\n"
        "sys.stdin.read()\n"
        f"open(argv[argv.index('-o') + 1], 'w').write(json.dumps({{'findings': [{FOUND!r}], 'unanswered': []}}))\n",
    )
    found = await inquire(Agent("codex"), scenario, Pages({PAGE: TEXT}))
    assert [finding.text for finding in found.findings] == [FOUND["text"]]
    argv = json.loads(kept.read_text())
    assert argv[0] == "exec" and "--search" in argv and argv[argv.index("--sandbox") + 1] == "read-only"
    assert "--output-schema" in argv and argv[-1] == "-"
