"""The web as the research stage reaches it: a search and a page reader through Raven's own web tools, on the vendors
and keys the configuration names.

Every page read is kept by its address, so a finding can be held to the words it quotes: `page` returns the text a
researcher was shown, or reads the page when the researcher ran elsewhere, such as an agent with its own web tools.
Every call is appended to `log` without the keys.
"""

import json
import time
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from raven.agent.tools.web import WebFetchTool, WebSearchTool

from ..curator.generation.context.render import tool
from ..curator.harness.declaration import schema_for

SEARCH, READ = "search", "read"
PAGE_CHARS = 12_000


class Query(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, description="What to search for, in the language the answer is likely written in.")


class Address(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, description="The page's http or https address.")


class Web:
    def __init__(self, search, fetch, *, page_chars: int = PAGE_CHARS, log: Path | None = None):
        self._search, self._fetch = search, fetch
        self.page_chars = page_chars
        self.log = Path(log) if log else None
        self.pages: dict[str, str] = {}

    @classmethod
    def of(cls, config, *, searching: bool = True, **options) -> "Web":
        """Raven's search and page reader as `config` sets them up; `searching` needs a search key."""
        web = config.tools.web
        search = WebSearchTool(
            api_key=web.vendor_key(web.search.provider) or None,
            provider=web.search.provider,
            proxy=web.proxy,
            max_results=web.search.max_results,
        )
        if searching and not search.api_key:
            raise ValueError(
                f"the research searches the web: give {web.search.provider} a key under tools.web.providers"
            )
        fetch = WebFetchTool(
            api_key=web.vendor_key(web.fetch.provider) or None, provider=web.fetch.provider, proxy=web.proxy
        )
        return cls(search, fetch, **options)

    def tools(self) -> list[dict]:
        return [
            tool(SEARCH, "Search the web; returns titles, addresses and snippets.", schema_for(Query)),
            tool(READ, "Read a web page as text. Only pages read here may be cited.", schema_for(Address)),
        ]

    def queries(self) -> dict:
        return {SEARCH: self.search, READ: self.read}

    async def search(self, arguments) -> dict:
        query = Query.model_validate(arguments).query.strip()
        results = await self._search.execute(query=query)
        self._note({"tool": SEARCH, "query": query, "chars": len(results)})
        return {"results": results}

    async def read(self, arguments) -> dict:
        url = Address.model_validate(arguments).url.strip()
        text, error = await self._read(url)
        return {"url": url, "error": error} if error else {"url": url, "text": text}

    async def page(self, url: str) -> str | None:
        """The text of a page as it was read here, reading it now when it was not; None when it cannot be read."""
        if url in self.pages:
            return self.pages[url]
        text, _ = await self._read(url)
        return text

    async def _read(self, url: str) -> tuple[str | None, str | None]:
        if not url.startswith(("http://", "https://")):
            self._note({"tool": READ, "url": url, "error": "not an http or https address"})
            return None, "give the page's http or https address"
        raw = await self._fetch.execute(url=url, maxChars=self.page_chars)
        try:
            page = json.loads(raw)
        except json.JSONDecodeError:
            page = {"error": raw[:300]}
        error = page.get("error") or ("the page has no text" if not page.get("text") else None)
        if error:
            self._note({"tool": READ, "url": url, "error": str(error)[:300]})
            return None, str(error)
        self.pages[url] = page["text"]
        self._note({"tool": READ, "url": url, "chars": len(page["text"]), "truncated": bool(page.get("truncated"))})
        return page["text"], None

    def _note(self, row: dict) -> None:
        if self.log is None:
            return
        self.log.parent.mkdir(parents=True, exist_ok=True)
        with self.log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"time": time.time(), **row}, ensure_ascii=False) + "\n")
