"""Who researches a brief (`experimental.research.inquiry`): an agent on its own web tools, or a model on this stage's.

`Agent` runs Claude Code or Codex without a terminal, in an empty directory of its own, and hands it the brief with
the research instructions; it answers in the inquiry's schema. Claude Code runs restricted to its web search and page
reader, with no user, project or local settings and no MCP server, so it reads nothing on this machine; Codex runs
in its read-only sandbox without the user's configuration, with web search only for research, which still lets its
shell read files, so Claude Code is the default. An agent runs once, and the trace keeps how it ran, its cost or token
count and the end of its output; the stage then refuses what does not hold (`experimental.research.inquiry.verify`).
Either agent also serves the other structured stages (`stage`): a collection call, a guidance extraction or a review.

`Exchange` is one bounded exchange of this stage's own model with the stage's search and reader
(`experimental.research.web.Web`): its submission is refused with the reasons while a finding fails its check, so the
model corrects it before the stage verifies it again.
"""

import asyncio
import json
import math
import os
import shutil
import tempfile
import time
from pathlib import Path

from ..curator.generation.context.render import tool
from ..curator.harness.declaration import schema_for
from ..iteration.exchange import exchange, messages
from .inquiry import NAME, Inquiry
from .voice import prompt

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
_REVISE_END = (
    "This is an editorial revision: do not search or read anything new. Repair only the withheld findings and the "
    "synthesis from the supplied source views; deliver the repaired findings and the corrected synthesis, not the "
    "findings admitted earlier; copy every passage exactly from a supplied view."
)
_AGENT_REVISE_END = _REVISE_END + " Your final answer is the JSON object the output schema describes, and nothing else."
_EXCHANGE_REVISE_END = (
    _REVISE_END + " Answer by calling `submit_findings` exactly once; a plain text reply is not delivered."
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
    return f"{prompt('research.md')}\n\n{end}"


def _codex_tokens(out: bytes) -> int | None:
    """The total `codex exec` prints under `tokens used` (on stderr), the only usage a subscription run reports."""
    lines = out.decode(errors="replace").splitlines()
    for index, line in enumerate(lines[:-1]):
        if line.strip() == "tokens used":
            digits = lines[index + 1].strip().replace(",", "")
            if digits.isdigit():
                return int(digits)
    return None


def correction_prompt(value, error):
    """Request an explicit contract correction without silently changing an agent's judgement."""
    return (
        "Correct the structured submission below to satisfy the output contract and validation error. "
        "Preserve its intended assessment, evidence, uncertainty and limitations; do not invent facts or repeat research. "
        "For a review, accepted=true requires issues=[]; put nonblocking suggestions in the reason. "
        "If any listed issue is actually blocking, return accepted=false with those issues. "
        "Do not discard required repairs merely to force acceptance. Submit the corrected structure.\n\n"
        + json.dumps({"previous_submission": value, "validation_error": error}, ensure_ascii=False)
    )


class Agent:
    """Claude Code (`claude`) or Codex (`codex`) as the researcher; `model` and, for Claude Code, `budget` in dollars
    bound one research, and `timeout` in seconds ends it."""

    def __init__(
        self,
        name: str = "claude",
        *,
        model: str | None = None,
        effort: str | None = None,
        budget: float | None = None,
        timeout=3600,
    ):
        if name not in AGENTS:
            raise ValueError(f"unknown research agent {name!r}; one of {AGENTS}")
        if shutil.which(name) is None:
            raise ValueError(f"the research agent {name!r} is not installed here")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("research timeout must be positive and finite")
        if budget is not None and (not math.isfinite(budget) or budget <= 0):
            raise ValueError("research budget must be positive and finite when supplied")
        self.name, self.model, self.budget, self.timeout = name, model, budget, timeout
        if effort is not None and effort not in {"low", "medium", "high", "xhigh", "max"}:
            raise ValueError(f"unsupported {name} research effort: {effort}")
        self.effort = effort

    def record(self) -> dict:
        return {
            "researcher": self.name,
            "model": self.model,
            "effort": self.effort,
            "budget": self.budget,
            "timeout": self.timeout,
        }

    async def stage(self, prompt, output, *, web=False, records=None, trace=None, corrections=1):
        """Run one isolated agent stage, retaining its activity even on timeout or cancellation."""
        if self.name == "codex":
            return await self._codex_stage(
                prompt, output, web=web, records=records, trace=trace, corrections=corrections
            )
        records = Path(records) if records is not None else None
        if records is not None:
            records.mkdir(parents=True, exist_ok=False)
            (records / "prompt.txt").write_text(prompt)
        command = self._claude(strict(schema_for(output)), web=web)
        if records is not None:
            (records / "command.json").write_text(json.dumps(command))
        started = time.monotonic()
        run = {**self.record(), "events": 0, "tool_calls": 0}
        envelope, out, err = None, bytearray(), bytearray()
        with tempfile.TemporaryDirectory(prefix="raven-research-claude-") as place:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=place,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=16 * 1024 * 1024,
                env={**os.environ, "NO_COLOR": "1"},
            )

            async def stdout():
                nonlocal envelope
                while line := await process.stdout.readline():
                    out.extend(line)
                    del out[:-OUTPUT]
                    if records is not None:
                        with (records / "events.jsonl").open("ab") as stream:
                            stream.write(line)
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(item, dict):
                        continue
                    run["events"] += 1
                    run["last_event"] = item.get("type")
                    run["last_event_seconds"] = round(time.monotonic() - started, 2)
                    if item.get("type") == "result":
                        envelope = item
                    if item.get("type") == "assistant":
                        run["tool_calls"] += sum(
                            block.get("type") == "tool_use"
                            for block in item.get("message", {}).get("content", [])
                            if isinstance(block, dict)
                        )

            async def stderr():
                while chunk := await process.stderr.read(8192):
                    err.extend(chunk)
                    del err[:-OUTPUT]
                    if records is not None:
                        with (records / "stderr.txt").open("ab") as stream:
                            stream.write(chunk)

            readers = asyncio.gather(stdout(), stderr(), process.wait())
            try:
                process.stdin.write(prompt.encode())
                await process.stdin.drain()
                process.stdin.close()
                await asyncio.wait_for(asyncio.shield(readers), self.timeout)
                if envelope is None:
                    if process.returncode:
                        raise ResearchError(
                            f"claude exited with {process.returncode}: {err.decode(errors='replace')[-800:]}"
                        )
                    raise ResearchError("claude printed no JSON result envelope")
                value = self._claude_answer(json.dumps(envelope).encode(), run)
                if process.returncode:
                    raise ResearchError(f"claude exited with {process.returncode}")
                try:
                    return output.model_validate(value), run
                except ValueError as exc:
                    run["validation_error"] = str(exc)
                    if corrections:
                        remaining = self.timeout - (time.monotonic() - started)
                        budget = self.budget
                        if budget is not None:
                            if not isinstance(run.get("cost_usd"), (int, float)):
                                raise ResearchError("cannot budget a correction without reported usage") from exc
                            budget -= run["cost_usd"]
                        if remaining <= 0 or (budget is not None and budget <= 0):
                            raise ResearchError("no execution allowance remains for a contract correction") from exc
                        corrected, correction = await Agent(
                            "claude", model=self.model, effort=self.effort, budget=budget, timeout=remaining
                        ).stage(
                            correction_prompt(value, str(exc)),
                            output,
                            records=records / "correction" if records is not None else None,
                            corrections=corrections - 1,
                        )
                        run["correction"] = correction
                        run["output_corrected"] = True
                        if isinstance(run.get("cost_usd"), (int, float)) and isinstance(
                            correction.get("cost_usd"), (int, float)
                        ):
                            run["initial_cost_usd"] = run["cost_usd"]
                            run["cost_usd"] += correction["cost_usd"]
                        return corrected, run
                    raise ResearchError(f"claude answered outside the schema: {exc}") from exc
            except (TimeoutError, asyncio.CancelledError) as exc:
                run["outcome"] = "cancelled" if isinstance(exc, asyncio.CancelledError) else "timeout"
                if isinstance(exc, asyncio.CancelledError):
                    raise
                raise ResearchError(f"claude: no answer within {self.timeout} seconds") from exc
            finally:
                if process.returncode is None:
                    process.kill()
                await readers
                run.update(seconds=round(time.monotonic() - started, 2), exit=process.returncode)
                if records is not None:
                    (records / "run.json").write_text(json.dumps(run, indent=2))
                    if envelope is not None:
                        (records / "result-envelope.json").write_text(json.dumps(envelope, ensure_ascii=False))
                if trace is not None:
                    trace.append(
                        {
                            "label": "research",
                            "event": "agent",
                            **run,
                            "stdout": out.decode(errors="replace"),
                            "stderr": err.decode(errors="replace"),
                        }
                    )

    async def _codex_stage(self, prompt, output, *, web, records, trace, corrections):
        """One `codex exec` in an empty directory; the answer file is the only thing read back."""
        records = Path(records) if records is not None else None
        if records is not None:
            records.mkdir(parents=True, exist_ok=False)
            (records / "prompt.txt").write_text(prompt)
        started = time.monotonic()
        run = self.record()
        out = err = b""
        with tempfile.TemporaryDirectory(prefix="raven-research-codex-") as place:
            place = Path(place)
            command = self._codex(strict(schema_for(output)), place, web=web)
            if records is not None:
                (records / "command.json").write_text(json.dumps(command))
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=place,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "NO_COLOR": "1"},
            )
            try:
                try:
                    async with asyncio.timeout(self.timeout):
                        out, err = await process.communicate(prompt.encode())
                except (TimeoutError, asyncio.CancelledError) as exc:
                    if process.returncode is None:
                        process.kill()
                    await process.wait()
                    run["outcome"] = "cancelled" if isinstance(exc, asyncio.CancelledError) else "timeout"
                    if isinstance(exc, asyncio.CancelledError):
                        raise
                    raise ResearchError(f"codex: no answer within {self.timeout} seconds") from exc
                if process.returncode != 0:
                    run["outcome"] = "failed"
                    raise ResearchError(
                        f"codex exited with {process.returncode}: {err.decode(errors='replace')[-800:]}"
                    )
                value = self._codex_answer(place, run)
                run["outcome"] = "success"
            finally:
                run.update(
                    seconds=round(time.monotonic() - started, 2),
                    exit=process.returncode,
                    tokens=_codex_tokens(err) or _codex_tokens(out),
                )
                if records is not None:
                    (records / "run.json").write_text(json.dumps(run, indent=2))
                    (records / "stdout.txt").write_bytes(out[-OUTPUT:])
                    (records / "stderr.txt").write_bytes(err[-OUTPUT:])
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
            return output.model_validate(value), run
        except ValueError as exc:
            run["validation_error"] = str(exc)
            remaining = self.timeout - (time.monotonic() - started)
            if not corrections or remaining <= 0:
                raise ResearchError(f"codex answered outside the schema: {exc}") from exc
            corrected, correction = await Agent("codex", model=self.model, effort=self.effort, timeout=remaining).stage(
                correction_prompt(value, str(exc)),
                output,
                records=records / "correction" if records is not None else None,
                trace=trace,
                corrections=corrections - 1,
            )
            run["correction"] = correction
            run["output_corrected"] = True
            if records is not None:
                (records / "run.json").write_text(json.dumps(run, indent=2))
            return corrected, run

    async def research(self, brief: dict, web, check=None, *, trace=None, records=None) -> tuple[Inquiry, dict]:
        prompt = f"{instructions(_AGENT_END)}\n\n{json.dumps(brief, ensure_ascii=False, indent=2)}"
        return await self.stage(prompt, Inquiry, web=True, records=records, trace=trace)

    async def revise(self, packet: dict, check=None, *, trace=None, records=None) -> tuple[Inquiry, dict]:
        """Rewrite a delivery from the supplied source views, without web access; the host verifies it again."""
        prompt = f"{instructions(_AGENT_REVISE_END)}\n\n{json.dumps(packet, ensure_ascii=False, indent=2)}"
        return await self.stage(prompt, Inquiry, web=False, records=records, trace=trace)

    def _claude(self, schema: dict, *, web=True) -> list[str]:
        return [
            "claude",
            "-p",
            "--restricted",
            "--tools",
            *(["WebSearch", "WebFetch"] if web else [""]),
            *(["--allowedTools", "WebSearch", "WebFetch"] if web else []),
            "--strict-mcp-config",
            "--no-session-persistence",
            "--output-format",
            "stream-json",
            "--verbose",
            "--include-partial-messages",
            "--json-schema",
            json.dumps(schema),
            *(["--model", self.model] if self.model else []),
            *(["--effort", self.effort] if self.effort else []),
            *(["--max-budget-usd", str(self.budget)] if self.budget else []),
        ]

    def _claude_answer(self, out: bytes, run: dict) -> dict:
        try:
            answer = json.loads(out)
        except json.JSONDecodeError as exc:
            raise ResearchError(f"claude printed no JSON result: {out[-500:]!r}") from exc
        if not isinstance(answer, dict):
            raise ResearchError("claude returned a non-object JSON result")
        run.update(
            cost_usd=answer.get("total_cost_usd"),
            turns=answer.get("num_turns"),
            outcome=answer.get("subtype"),
            actual_models=list(answer.get("modelUsage") or {}),
            model_usage=answer.get("modelUsage") or {},
        )
        if answer.get("is_error") or not isinstance(answer.get("structured_output"), dict):
            detail = answer.get("errors") or answer.get("result") or answer.get("subtype")
            raise ResearchError(
                f"claude gave no structured answer ({answer.get('subtype', 'unknown')}): {str(detail)[:800]}"
            )
        return answer["structured_output"]

    def _codex(self, schema: dict, place: Path, *, web=True) -> list[str]:
        (place / "schema.json").write_text(json.dumps(schema))
        return [
            "codex",
            *(["--search"] if web else []),
            "exec",
            "--ignore-user-config",
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
            *(["-c", f'model_reasoning_effort="{self.effort}"'] if self.effort else []),
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

    async def research(self, brief: dict, web, check, *, trace=None, records=None) -> tuple[Inquiry, dict]:
        return await self._exchange(_EXCHANGE_END, brief, check, tools=web.tools(), query=web.queries(), trace=trace)

    async def revise(self, packet: dict, check, *, trace=None, records=None) -> tuple[Inquiry, dict]:
        """Rewrite a delivery from the supplied source views with no search or reader offered."""
        return await self._exchange(_EXCHANGE_REVISE_END, packet, check, tools=[], query={}, trace=trace)

    async def _exchange(self, end, packet, check, *, tools, query, trace):
        def accept(arguments) -> Inquiry:
            inquiry = Inquiry.model_validate(arguments)
            reasons = check(inquiry)
            if reasons:
                raise ValueError("; ".join(reasons))
            return inquiry

        started = time.time()
        _, inquiry = await exchange(
            self.provider,
            messages(instructions(end), packet),
            [*tools, tool(NAME, "Submit the findings and the questions the web cannot answer.", schema_for(Inquiry))],
            submit={NAME: accept},
            query=query,
            model=self.model,
            effort=self.effort,
            max_calls=self.max_calls if query else min(self.max_calls, 4),
            timeout=self.timeout,
            trace=trace,
            label="research",
        )
        return inquiry, {**self.record(), "seconds": round(time.time() - started, 1)}
