"""The research stage reaches the web through Raven's own tools, keeps every page it read and logs every call
without the keys."""

import json

import pytest

from experimental.research.web import READ, SEARCH, Web
from raven.config.schema import Config


class Search:
    def __init__(self):
        self.queries = []

    async def execute(self, query, count=None):
        self.queries.append(query)
        return f"Results for: {query}\n\n1. Tea guide\n   https://tea.example/guide"


class Fetch:
    def __init__(self, pages):
        self.pages, self.read = pages, []

    async def execute(self, url, maxChars=None):  # noqa: N803 -- the Raven tool's own parameter name
        self.read.append((url, maxChars))
        if url in self.pages:
            return json.dumps({"url": url, "text": self.pages[url][:maxChars], "truncated": False})
        return json.dumps({"error": "Jina Reader answered HTTP 404", "url": url})


@pytest.mark.asyncio
async def test_a_page_read_is_kept_and_a_page_that_cannot_be_read_is_an_answer_not_an_exception(tmp_path):
    fetch = Fetch({"https://tea.example/guide": "Afternoon tea is served from two to five."})
    web = Web(Search(), fetch, page_chars=100, log=tmp_path / "web.jsonl")
    assert (await web.search({"query": "afternoon tea hours"}))["results"].startswith("Results for")
    read = await web.read({"url": "https://tea.example/guide"})
    assert read == {"url": "https://tea.example/guide", "text": "Afternoon tea is served from two to five."}
    assert (await web.read({"url": "https://tea.example/gone"}))["error"].endswith("404")
    assert (await web.read({"url": "file:///etc/passwd"}))["error"].startswith("give the page's")
    assert await web.page("https://tea.example/guide") == "Afternoon tea is served from two to five."
    assert fetch.read == [("https://tea.example/guide", 100), ("https://tea.example/gone", 100)]
    assert set(web.pages) == {"https://tea.example/guide"}
    rows = [json.loads(line) for line in (tmp_path / "web.jsonl").read_text().splitlines()]
    assert [(row["tool"], row.get("query") or row.get("url")) for row in rows] == [
        (SEARCH, "afternoon tea hours"),
        (READ, "https://tea.example/guide"),
        (READ, "https://tea.example/gone"),
        (READ, "file:///etc/passwd"),
    ]


def test_the_web_is_built_from_the_configured_vendors_and_searching_needs_a_key(monkeypatch):
    monkeypatch.delenv("SERPER_API_KEY", raising=False)
    config = Config()
    with pytest.raises(ValueError, match="give serper a key"):
        Web.of(config)
    assert Web.of(config, searching=False).pages == {}
    config.tools.web.search.api_key = "a-key"
    web = Web.of(config)
    assert [tool["function"]["name"] for tool in web.tools()] == [SEARCH, READ]
    assert web._search.api_key == "a-key"
