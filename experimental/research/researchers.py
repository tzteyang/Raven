"""Who researches a brief (`experimental.research.inquiry`): an agent on its own web tools, or a model on this stage's.

`Agent` runs Claude Code or Codex without a terminal, in an empty directory of its own, and hands it the brief with
the research instructions; it answers in the inquiry's schema. Claude Code runs restricted to its web search and page
reader, with no user, project or local settings and no MCP server, so it reads nothing on this machine; Codex runs
in its read-only sandbox with live web search, which still lets its shell read files, so Claude Code is the default.
An agent runs once, and the trace keeps how it ran, its cost and the end of its output; the stage then refuses
what does not hold (`experimental.research.inquiry.verify`).

`Exchange` is one bounded exchange of this stage's own model with the stage's search and reader
(`experimental.research.web.Web`): its submission is refused with the reasons while a finding fails its check, so the
model corrects it before the stage verifies it again.
"""

import asyncio
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

from ..curator.generation.context.render import tool
from ..curator.harness.declaration import schema_for
from ..iteration.exchange import exchange, messages
from .inquiry import NAME, PROMPT, Inquiry

AGENTS = ("claude", "codex")
OUTPUT = 20_000
_AGENT_END = (
    "Search the web and read pages with the tools you have; when a page reader lets you say what to extract, ask "
    "for the exact wording of the passages you need, and copy `evidence` from that exact wording. Your final answer "
    "is the JSON object the output schema describes, and nothing else."
)
_EXCHANGE_END = (
    "Search with `search` and read pages with `read`. Answer by calling `submit_findings` exactly once; a plain text "
    "reply is not delivered."
)


class ResearchError(RuntimeError):
    pass


def strict(schema: dict) -> dict:
    """The schema with every property required, as strict structured outputs demand; optional fields may be empty."""
    if isinstance(schema, dict):
        schema = {key: strict(value) for key, value in schema.items()}
        if schema.get("type") == "object" and "properties" in schema:
            schema["required"] = list(schema["properties"])
            schema["additionalProperties"] = False
        for key in ("default",):
            schema.pop(key, None)
    elif isinstance(schema, list):
        schema = [strict(value) for value in schema]
    return schema


def instructions(end: str) -> str:
    return f"{PROMPT.read_text().strip()}\n\n{end}"


class Agent:
    """Claude Code (`claude`) or Codex (`codex`) as the researcher; `model` and, for Claude Code, `budget` in dollars
    bound one research, and `timeout` in seconds ends it."""

    def __init__(self, name: str = "claude", *, model: str | None = None, budget: float | None = 2.0, timeout=900):
        if name not in AGENTS:
            raise ValueError(f"unknown research agent {name!r}; one of {AGENTS}")
        if shutil.which(name) is None:
            raise ValueError(f"the research agent {name!r} is not installed here")
        self.name, self.model, self.budget, self.timeout = name, model, budget, timeout

    def record(self) -> dict:
        return {"researcher": self.name, "model": self.model, "budget": self.budget, "timeout": self.timeout}

    async def research(self, brief: dict, web, check=None, *, trace=None) -> tuple[Inquiry, dict]:
        prompt = f"{instructions(_AGENT_END)}\n\n{json.dumps(brief, ensure_ascii=False, indent=2)}"
        schema = strict(schema_for(Inquiry))
        with tempfile.TemporaryDirectory(prefix=f"raven-research-{self.name}-") as place:
            place = Path(place)
            command = self._claude(schema) if self.name == "claude" else self._codex(schema, place)
            started = time.time()
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=place,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "NO_COLOR": "1"},
            )
            try:
                async with asyncio.timeout(self.timeout):
                    out, err = await process.communicate(prompt.encode())
            except TimeoutError as exc:
                process.kill()
                await process.wait()
                raise ResearchError(f"{self.name}: no answer within {self.timeout} seconds") from exc
            run = {**self.record(), "seconds": round(time.time() - started, 1), "exit": process.returncode}
            try:
                if process.returncode != 0:
                    raise ResearchError(
                        f"{self.name} exited with {process.returncode}: {err.decode(errors='replace')[-800:]}"
                    )
                value = self._claude_answer(out, run) if self.name == "claude" else self._codex_answer(place, run)
            finally:
                if trace is not None:
                    trace.append(
                        {
                            "label": "research",
                            "event": "agent",
                            **run,
                            "stdout": out.decode(errors="replace")[-OUTPUT:],
                            "stderr": err.decode(errors="replace")[-OUTPUT:],
                        }
                    )
        try:
            return Inquiry.model_validate(value), run
        except ValueError as exc:
            raise ResearchError(f"{self.name} answered outside the schema: {exc}") from exc

    def _claude(self, schema: dict) -> list[str]:
        return [
            "claude",
            "-p",
            "--restricted",
            "--tools",
            "WebSearch",
            "WebFetch",
            "--allowedTools",
            "WebSearch",
            "WebFetch",
            "--strict-mcp-config",
            "--no-session-persistence",
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(schema),
            *(["--model", self.model] if self.model else []),
            *(["--max-budget-usd", str(self.budget)] if self.budget else []),
        ]

    def _claude_answer(self, out: bytes, run: dict) -> dict:
        try:
            answer = json.loads(out)
        except json.JSONDecodeError as exc:
            raise ResearchError(f"claude printed no JSON result: {out[-500:]!r}") from exc
        run.update(
            cost_usd=answer.get("total_cost_usd"),
            turns=answer.get("num_turns"),
            outcome=answer.get("subtype"),
        )
        if answer.get("is_error") or not isinstance(answer.get("structured_output"), dict):
            raise ResearchError(f"claude gave no structured answer: {str(answer.get('result'))[:800]}")
        return answer["structured_output"]

    def _codex(self, schema: dict, place: Path) -> list[str]:
        (place / "schema.json").write_text(json.dumps(schema))
        return [
            "codex",
            "exec",
            "--search",
            "--skip-git-repo-check",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "-C",
            str(place),
            "--output-schema",
            str(place / "schema.json"),
            "-o",
            str(place / "answer.json"),
            *(["-m", self.model] if self.model else []),
            "-",
        ]

    def _codex_answer(self, place: Path, run: dict) -> dict:
        answer = place / "answer.json"
        if not answer.is_file():
            raise ResearchError("codex wrote no final answer")
        try:
            return json.loads(answer.read_text())
        except json.JSONDecodeError as exc:
            raise ResearchError(f"codex answered without JSON: {answer.read_text()[:500]}") from exc


class Exchange:
    """This stage's model as the researcher, on the stage's own search and reader."""

    name = "exchange"

    def __init__(self, provider, *, model=None, effort=None, max_calls=16, timeout=300):
        self.provider, self.model, self.effort, self.max_calls, self.timeout = (
            provider,
            model,
            effort,
            max_calls,
            timeout,
        )

    def record(self) -> dict:
        return {
            "researcher": self.name,
            "model": self.model,
            "effort": self.effort,
            "max_calls": self.max_calls,
            "timeout": self.timeout,
        }

    async def research(self, brief: dict, web, check, *, trace=None) -> tuple[Inquiry, dict]:
        def accept(arguments) -> Inquiry:
            inquiry = Inquiry.model_validate(arguments)
            reasons = check(inquiry)
            if reasons:
                raise ValueError("; ".join(reasons))
            return inquiry

        started = time.time()
        _, inquiry = await exchange(
            self.provider,
            messages(instructions(_EXCHANGE_END), brief),
            [
                *web.tools(),
                tool(NAME, "Submit the findings and the questions the web cannot answer.", schema_for(Inquiry)),
            ],
            submit={NAME: accept},
            query=web.queries(),
            model=self.model,
            effort=self.effort,
            max_calls=self.max_calls,
            timeout=self.timeout,
            trace=trace,
            label="research",
        )
        return inquiry, {**self.record(), "seconds": round(time.time() - started, 1)}
