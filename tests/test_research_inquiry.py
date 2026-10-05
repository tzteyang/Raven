"""A research is held to what it read, whoever researched it: a finding stands only on a passage of a page the stage
can read again, names only materials that were handed over, and carries nothing sealed from a reader of norms."""

import json
import os
import stat
import sys

import pytest

from experimental.research import inquire
from experimental.scenario import default_visibility

AUDIENCE = default_visibility("norm")
from experimental.research.information import Review
from experimental.research.inquiry import NAME, Found, Inquiry, problems, quoted, verify
from experimental.research.researchers import Agent, Exchange, ResearchError, strict
from experimental.research.web import READ
from experimental.scenario import load
from experimental.scenario.sealed import sealed_for
from tests.research_helpers import CHECK, Provider, make_scenario, research_brief, response

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


def test_a_short_chinese_clause_is_a_passage_while_a_fragment_of_a_few_characters_is_not():
    page = "第十三条 符合下列情形之一的，个人信息处理者方可处理个人信息：（一）取得个人的同意；（二）为订立合同所必需。"
    assert quoted("（一）取得个人的同意；", page)
    assert quoted("取得个人的同意", page)
    assert not quoted("个人的同意", page)
    assert not quoted("取得个人的拒绝", page)
    assert not quoted("fee is five", "the fee is five")


def test_pdf_word_wrapping_does_not_refuse_an_intact_passage_or_join_unrelated_text():
    passage = "services, activities or circumstances of a competitor"
    for wrapped in ("activi- ties", "activi-\nties", "activi\u00adties"):
        page = passage.replace("activities", wrapped)
        assert quoted(passage, page)
        assert quoted(passage, json.dumps({"text": page}))
    assert not quoted(passage, passage.replace("activities", "activi ties"))
    assert not quoted(passage, passage.replace("activities", "activi-\n\nties"))
    assert quoted("a high-quality coaching process", "a high- quality coaching process")


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
                {**FOUND, "conflicts": [CHECK]},
                {**FOUND, "text": CHECK},
                {
                    **FOUND,
                    "kind": "norm",
                    "text": "Serve scones with clotted cream.",
                    "evidence": "scones come with clotted cream",
                },
            ],
            "unanswered": [
                {"question": "What does the shop charge?", "why": "only the shop knows its prices", "channel": "user"}
            ],
        }
    )
    found = await verify(inquiry, web, sealed=seals(scenario), limit=1, prefix="answer")
    assert [(finding.id, finding.kind) for finding in found.findings] == [("answer-1", "fact")]
    reasons = [row["reasons"] for row in found.refused]
    assert "not read or could not be read" in reasons[0][0] and "not a passage" in reasons[1][0]
    assert "neither the pages" in reasons[2][0] and "neither the pages" in reasons[3][0]
    assert reasons[4] == ["over the limit of 1 findings"]
    assert found.unanswered == (
        {"question": "What does the shop charge?", "why": "only the shop knows its prices", "channel": "user"},
    )
    assert web.asked.count(PAGE) == 1 and "https://gone.example" in web.asked


@pytest.mark.asyncio
async def test_a_passage_quoted_from_a_page_the_research_read_but_did_not_cite_is_refused_naming_that_page(tmp_path):
    scenario = load(make_scenario(tmp_path / "shop"))
    other = "https://tea.example/hours"
    web = Pages({PAGE: TEXT, other: "Opening Hours\n\nThe shop opens at nine and closes at six."})
    await web.page(other)
    misattributed = {**FOUND, "sources": [PAGE], "evidence": "the shop opens at nine and closes at six"}
    nowhere = {**FOUND, "sources": [PAGE], "evidence": "the shop opens at midnight and never closes"}
    found = await verify(
        Inquiry.model_validate({"findings": [misattributed, nowhere], "unanswered": []}), web, sealed=seals(scenario)
    )
    assert found.findings == ()
    first, second = (row["reasons"][0] for row in found.refused)
    assert other in first and "not of the sources it lists" in first and PAGE not in first
    assert "not a passage of its sources" in second
    assert problems(Found.model_validate(misattributed), {PAGE: TEXT}, seals(scenario))[0].startswith(
        "its evidence is not a passage"
    )


@pytest.mark.asyncio
async def test_the_stages_own_model_corrects_a_finding_until_it_quotes_a_page_it_read(tmp_path):
    scenario = load(make_scenario(tmp_path / "shop"))
    provider = Provider(
        response(NAME, {"findings": [FOUND]}),
        response(READ, {"url": PAGE}),
        response(NAME, {"findings": [FOUND]}),
    )
    found = await inquire(
        Exchange(provider, max_calls=4),
        {"profile": "Tea service", "questions": [], "known_information": []},
        Pages({PAGE: TEXT}),
        sealed=seals(scenario),
    )
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
    found = await inquire(
        Agent("claude", model="sonnet", effort="xhigh", budget=1.5),
        {"profile": "Tea service", "questions": [], "known_information": []},
        Pages({PAGE: TEXT}),
    )
    assert [finding.id for finding in found.findings] == ["researched-1"] and found.run["cost_usd"] == 0.2
    ran = json.loads(kept.read_text())
    argv = ran["argv"]
    assert argv[argv.index("--effort") + 1] == "xhigh"
    assert found.run["effort"] == "xhigh"
    assert argv[:2] == ["-p", "--restricted"] and argv[argv.index("--tools") + 1 : argv.index("--tools") + 3] == [
        "WebSearch",
        "WebFetch",
    ]
    assert {"--strict-mcp-config", "--no-session-persistence"} <= set(argv)
    assert argv[argv.index("--model") + 1] == "sonnet" and argv[argv.index("--max-budget-usd") + 1] == "1.5"
    schema = json.loads(argv[argv.index("--json-schema") + 1])
    assert schema["required"] == ["findings", "unanswered", "synthesis", "disagreements"]
    assert argv[argv.index("--output-format") + 1] == "stream-json"
    assert "raven-research-claude-" in ran["cwd"] and '"questions": []' in ran["prompt"] and CHECK not in ran["prompt"]


@pytest.mark.asyncio
async def test_a_research_agent_that_fails_or_answers_outside_the_schema_ends_the_research(tmp_path, monkeypatch):
    scenario = load(make_scenario(tmp_path / "shop"))
    fake(
        tmp_path,
        monkeypatch,
        "claude",
        "import json\nprint(json.dumps({'type': 'result', 'is_error': True, 'result': 'budget exceeded', 'subtype': 'error_max_budget_usd'}))\n",
    )
    with pytest.raises(ResearchError, match="budget exceeded"):
        await inquire(Agent("claude"), {"profile": "Tea service", "questions": [], "known_information": []}, Pages())
    fake(tmp_path, monkeypatch, "claude", "import sys\nsys.exit(3)\n")
    with pytest.raises(ResearchError, match="exited with 3"):
        await inquire(Agent("claude"), {"profile": "Tea service", "questions": [], "known_information": []}, Pages())
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
    found = await inquire(
        Agent("codex"), {"profile": "Tea service", "questions": [], "known_information": []}, Pages({PAGE: TEXT})
    )
    assert [finding.text for finding in found.findings] == [FOUND["text"]]
    argv = json.loads(kept.read_text())
    assert argv[:2] == ["--search", "exec"] and argv[argv.index("--sandbox") + 1] == "read-only"
    assert "--ignore-user-config" in argv and "--output-schema" in argv and argv[-1] == "-"


@pytest.mark.asyncio
async def test_claude_budget_failure_keeps_usage_and_does_not_misclassify_stderr_warning(tmp_path, monkeypatch):
    payload = {
        "type": "result",
        "subtype": "error_max_budget_usd",
        "is_error": True,
        "total_cost_usd": 3.96,
        "num_turns": 43,
        "modelUsage": {"claude-sonnet-5-5": {"costBasis": "unknown", "outputTokens": 35000}},
        "errors": ["Reached maximum budget ($3.5)"],
    }
    fake(
        tmp_path,
        monkeypatch,
        "claude",
        "import json,sys\n"
        + f"print(json.dumps({payload!r}))\n"
        + "print('[claude-code:unrecognized_model]', file=sys.stderr)\nsys.exit(1)\n",
    )
    trace = []
    with pytest.raises(ResearchError, match="error_max_budget_usd"):
        await Agent("claude", model="claude-sonnet-5-5", effort="xhigh", budget=3.5).research({}, None, trace=trace)
    assert trace[0]["cost_usd"] == 3.96 and trace[0]["turns"] == 43
    assert trace[0]["actual_models"] == ["claude-sonnet-5-5"]
    assert trace[0]["model_usage"] == payload["modelUsage"]


@pytest.mark.asyncio
async def test_streamed_cli_events_survive_a_timeout_without_a_final_result(tmp_path, monkeypatch):
    fake(
        tmp_path,
        monkeypatch,
        "claude",
        "import json,sys,time\nsys.stdin.read()\n"
        "print(json.dumps({'type':'system','subtype':'init'}),flush=True)\ntime.sleep(10)\n",
    )
    trace = []
    with pytest.raises(ResearchError, match="no answer within"):
        await Agent("claude", timeout=0.3).stage("Inspect the input.", Inquiry, records=tmp_path / "stage", trace=trace)
    assert json.loads((tmp_path / "stage/events.jsonl").read_text())["subtype"] == "init"
    assert trace[0]["outcome"] == "timeout" and trace[0]["events"] == 1
    assert json.loads((tmp_path / "stage/run.json").read_text())["exit"] is not None


@pytest.mark.asyncio
async def test_fragmented_stream_result_retains_delivery_sections_without_a_default_monetary_cap(tmp_path, monkeypatch):
    payload = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "structured_output": {
            "findings": [FOUND],
            "unanswered": [],
            "synthesis": "The schedule is explicit.",
            "disagreements": ["Different service formats need separate schedules."],
        },
    }
    kept = fake(
        tmp_path,
        monkeypatch,
        "claude",
        "import json,sys,time\nsys.stdin.read()\n"
        + f"open({str(tmp_path / 'claude.args')!r},'w').write(json.dumps(sys.argv[1:]))\n"
        + "print(json.dumps({'type':'system','subtype':'init'}),flush=True)\n"
        + f"line=json.dumps({payload!r})+'\\n'\n"
        + "sys.stdout.write(line[:20]);sys.stdout.flush();time.sleep(0.02)\nsys.stdout.write(line[20:]);sys.stdout.flush()\n",
    )
    result, run = await Agent("claude").stage("Prepare the delivery.", Inquiry, records=tmp_path / "stage")
    assert result.synthesis == "The schedule is explicit." and result.disagreements
    assert run["events"] == 2 and run["outcome"] == "success"
    assert "--max-budget-usd" not in json.loads(kept.read_text())


@pytest.mark.asyncio
async def test_inconsistent_review_requires_an_explicit_bounded_resubmission(tmp_path, monkeypatch):
    fake(
        tmp_path,
        monkeypatch,
        "claude",
        "import json,sys\nprompt=sys.stdin.read()\n"
        "value=({'accepted':True,'reason':'Accepted; optional wording note retained.','issues':[]} "
        "if 'Correct the structured submission' in prompt else "
        "{'accepted':True,'reason':'Accepted.','issues':['Optional wording note.']})\n"
        "print(json.dumps({'type':'result','subtype':'success','is_error':False,'total_cost_usd':0.1,'structured_output':value}))\n",
    )
    result, run = await Agent("claude").stage("Review the content.", Review, records=tmp_path / "stage")
    assert result.accepted and not result.issues and "note retained" in result.reason
    assert run["output_corrected"] and run["cost_usd"] == 0.2
    assert (tmp_path / "stage/correction/result-envelope.json").exists()
    initial = json.loads((tmp_path / "stage/result-envelope.json").read_text())["structured_output"]
    assert initial["issues"] == ["Optional wording note."]


@pytest.mark.asyncio
async def test_quote_only_inquiry_accepts_semantic_known_information():
    provider = Provider(response(READ, {"url": PAGE}), response(NAME, {"findings": [FOUND]}))
    found = await inquire(Exchange(provider, max_calls=3), research_brief(), Pages({PAGE: TEXT}))
    assert found.findings[0].text == FOUND["text"]


@pytest.mark.asyncio
async def test_contract_correction_cannot_spend_an_exhausted_explicit_budget(tmp_path, monkeypatch):
    fake(
        tmp_path,
        monkeypatch,
        "claude",
        "import json,sys\nsys.stdin.read()\n"
        "print(json.dumps({'type':'result','subtype':'success','is_error':False,'total_cost_usd':1.0,"
        "'structured_output':{'accepted':True,'reason':'Contradictory output.','issues':['Required repair.']}}))\n",
    )
    with pytest.raises(ResearchError, match="no execution allowance"):
        await Agent("claude", budget=1.0).stage("Review the content.", Review, records=tmp_path / "stage")
    assert not (tmp_path / "stage/correction").exists()


@pytest.mark.asyncio
async def test_cancelling_a_streamed_stage_keeps_activity_and_terminates_the_child(tmp_path, monkeypatch):
    import asyncio

    fake(
        tmp_path,
        monkeypatch,
        "claude",
        "import json,sys,time\nsys.stdin.read()\n"
        "print(json.dumps({'type':'system','subtype':'init'}),flush=True)\ntime.sleep(10)\n",
    )
    task = asyncio.create_task(Agent("claude").stage("Read the input.", Inquiry, records=tmp_path / "stage"))
    async with asyncio.timeout(2):
        while not (tmp_path / "stage/events.jsonl").exists():
            await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    run = json.loads((tmp_path / "stage/run.json").read_text())
    assert run["outcome"] == "cancelled" and run["exit"] is not None and run["events"] == 1


def test_json_and_markup_passages_are_decoded_without_joining_unrelated_fields():
    page = json.dumps({"abstract": "<jats:p>A cross\u2010level analysis supports this finding.</jats:p>"})
    assert quoted("A cross-level analysis supports this finding", page)
    wrapped = "Title: Metadata\n\nURL Source: https://example.org/metadata\n\nMarkdown Content:\n" + page
    assert quoted("A cross-level analysis supports this finding", wrapped)
    assert (
        quoted("Evidence and practice are distinct concepts", "<p>Evidence &amp; practice are distinct concepts</p>")
        is False
    )
    assert quoted("Evidence & practice are distinct concepts", "<p>Evidence &amp; practice are distinct concepts</p>")
    assert not quoted(
        "Afternoon tea is served from two to five",
        json.dumps({"title": "Afternoon tea is served", "abstract": "from two to five"}),
    )


@pytest.mark.asyncio
async def test_narrative_conflicts_are_not_material_ids_and_retained_ids_do_not_shift():
    bad = {**FOUND, "evidence": "This passage is not present in the source."}
    good = {**FOUND, "conflicts": ["The supplied example assumes service is available all day."]}
    result = await verify(Inquiry(findings=[bad, good]), Pages({PAGE: TEXT}))
    assert result.findings[0].id == "researched-2"
    assert result.findings[0].conflicts == tuple(good["conflicts"])
