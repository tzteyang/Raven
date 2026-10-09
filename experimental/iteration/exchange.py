"""One bounded model exchange that may query and must end in exactly one structured submission."""

import asyncio
import inspect
import json

from pydantic import ValidationError

from raven.contracts.llm_provider import REASONING_EFFORT_LADDER

from ..curator.generation.context.render import ECHOED_CHARS, assistant_message
from ..model_calls import MalformedArgumentsError

# Every call asks for as much output as the model accepts; the provider bounds the ask by the model's own ceiling.
# Left unasked, a call gets the reservation an agent loop keeps per iteration (32768 tokens), and a reasoning model
# judging a long packet can think past it and deliver nothing: an owner's review on DeepSeek V4.1 Flash took 53950.
OUTPUT_TOKENS = 131_072

# The pydantic error types of arguments without the declared shape (a field missing or extra, a value of the wrong JSON
# type): nothing the model meant was delivered. A value the shape allows but a constraint or rule refuses (a length, a
# range, an allowed value, a validator) is something it said.
SHAPE_ERRORS = frozenset(
    {
        "missing",
        "extra_forbidden",
        "model_type",
        "model_attributes_type",
        "dict_type",
        "list_type",
        "tuple_type",
        "string_type",
        "int_type",
        "int_parsing",
        "float_type",
        "float_parsing",
        "bool_type",
        "bool_parsing",
        "none_required",
        "json_invalid",
        "json_type",
    }
)


# The efforts a call falls back to after a reply that ran into its output ceiling: the same effort once more (a second
# sample often fits; an owner's review on DeepSeek V4.1 Flash came through on its third), then low, then no reasoning.
# The rungs between are skipped: on V4.1 Flash high, medium, low and minimal reason alike (measured on the official
# endpoint and three OpenRouter upstreams), and each extra rung is one more call spent to the ceiling.
FLOOR = "none"


def descent(effort: str | None) -> list[str | None]:
    """The efforts of the calls after each successive cut reply, ending at `FLOOR`."""
    rungs: list[str | None] = [effort]
    if effort is None or (
        effort in REASONING_EFFORT_LADDER
        and REASONING_EFFORT_LADDER.index(effort) < REASONING_EFFORT_LADDER.index("low")
    ):
        rungs.append("low")
    return [*rungs, FLOOR] if effort != FLOOR else rungs


def cut(response) -> bool:
    """Whether a reply stopped at its output ceiling: the provider flagged it, or its output count reached the ceiling
    the request carried (some upstreams report a normal finish on a reply they cut, arguments and all)."""
    if getattr(response, "truncated", False):
        return True
    ceiling = getattr(response, "max_tokens", None)
    used = (getattr(response, "usage", None) or {}).get("completion_tokens")
    return bool(ceiling and isinstance(used, int) and used >= ceiling)


class ExchangeError(RuntimeError):
    def __init__(self, message, trace=()):
        super().__init__(message)
        self.trace = tuple(trace)


def messages(system: str, materials: dict) -> list[dict]:
    return [
        {"role": "system", "content": system.strip()},
        {"role": "user", "content": json.dumps(materials, ensure_ascii=False, indent=2)},
    ]


def undelivered(exc: Exception) -> bool:
    """Whether a refused submission never got as far as its content: its arguments could not be parsed
    (`MalformedArgumentsError`), or they lack the tool's declared shape (`SHAPE_ERRORS`, which a strict provider would
    have refused itself)."""
    if isinstance(exc, MalformedArgumentsError):
        return True
    return isinstance(exc, ValidationError) and all(error["type"] in SHAPE_ERRORS for error in exc.errors())


async def exchange(
    provider,
    messages,
    tools,
    *,
    submit,
    query=None,
    model=None,
    effort=None,
    max_calls=4,
    timeout=120,
    trace=None,
    label="",
    grace=2,
):
    """Drive the model until one call in `submit` parses; `query` tools run locally, awaited when they are coroutines,
    and feed results back.

    The last allowed call offers only the submission tools, so a query-happy model still ends with a submission; a
    model may still name a query tool from the history on that call, and such a reply is refused, never run.
    `effort` is the reasoning effort of the calls; without one the provider's own setting applies. Every call asks
    for `OUTPUT_TOKENS` of output, which the provider bounds by the model's ceiling. A reply without a tool call is
    traced with its finish reason and usage: a reasoning model can spend its whole output budget thinking and return
    nothing, which only the usage shows. A reply that ran into the ceiling (`cut`) without a submission that holds is
    asked again without charge down `descent(effort)`, the same effort once more, then low, then no reasoning; every
    call is traced with its effort, and so is the submission, so an answer given without reasoning is told apart. At
    the floor a cut reply is undelivered like any other. `grace` is how many undelivered replies (no tool call, a
    query on the submission-only last call, or a submission whose arguments could not be parsed or do not fit the
    tool's schema, `undelivered`) are retried without charging `max_calls`; they are traced with `charged: False`. The
    budget stays final for everything the model did say. A reply's text goes back into the conversation capped
    (`render.assistant_message`), traced as `output.capped`."""
    query = query or {}
    trace = trace if trace is not None else []
    submissions = [entry for entry in tools if entry["function"]["name"] in submit]
    ladder = descent(effort)
    attempt, number, wasted, cuts = 0, 0, 0, 0

    def retried(row: dict, response) -> bool:
        """Whether a reply that was not taken is asked again down the ladder; traces the cut and the next effort."""
        nonlocal attempt, cuts
        if not cut(response) or cuts >= len(ladder):
            return False
        attempt, cuts = attempt - 1, cuts + 1
        row.update(cut=True, charged=False, next_effort=ladder[cuts - 1])
        return True

    while attempt < max_calls:
        attempt, number = attempt + 1, number + 1
        offered = tools
        if attempt == max_calls and query:
            offered = submissions
            messages.append(
                {"role": "user", "content": "This is the last call: submit now; no further queries are possible."}
            )
        current = effort if cuts == 0 else ladder[cuts - 1]
        extra = {"max_tokens": OUTPUT_TOKENS, **({"reasoning_effort": current} if current else {})}
        trace.append({"label": label, "event": "model.call", "call": number, "effort": current})
        try:
            async with asyncio.timeout(timeout):
                response = await provider.chat_with_retry(
                    messages=messages, tools=offered, model=model, tool_choice="auto", **extra
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise ExchangeError(f"{label}: model call failed: {exc}", trace) from exc
        if response.finish_reason == "error":
            raise ExchangeError(f"{label}: provider error: {response.content}", trace)
        messages.append(assistant_message(response))
        if len(response.content or "") > ECHOED_CHARS:
            trace.append({"label": label, "event": "output.capped", "content_chars": len(response.content)})
        if not response.tool_calls:
            names = ", ".join(f"`{name}`" for name in (*query, *submit))
            said = (
                "Your reply was cut off at the output limit before it was delivered, so nothing of it was kept."
                if cut(response)
                else "Plain text is not delivered."
            )
            messages.append({"role": "user", "content": f"{said} Reply by calling one of the tools: {names}."})
            row = {
                "label": label,
                "event": "output.missing",
                "finish_reason": response.finish_reason,
                "content_chars": len(response.content or ""),
                "usage": dict(getattr(response, "usage", None) or {}),
            }
            if retried(row, response):
                pass
            elif wasted < grace:
                attempt, wasted, row["charged"] = attempt - 1, wasted + 1, False
            trace.append(row)
            continue
        submitted = [call for call in response.tool_calls if call.name in submit]
        if offered is submissions and not submitted:
            error = "This is the last call: no further queries are possible; submit now."
            for call in response.tool_calls:
                messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps({"error": error})})
            row = {
                "label": label,
                "event": "output.rejected",
                "error": error,
                "tools": [call.name for call in response.tool_calls],
            }
            if wasted < grace:
                attempt, wasted, row["charged"] = attempt - 1, wasted + 1, False
            trace.append(row)
            continue
        if submitted:
            if len(response.tool_calls) != 1:
                error = "Submit exactly once, separately from queries."
                for call in response.tool_calls:
                    messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps({"error": error})})
                trace.append({"label": label, "event": "output.rejected", "error": error})
                continue
            call = submitted[0]
            try:
                value = submit[call.name](call.arguments)
            except (ValueError, TypeError, KeyError) as exc:
                error = str(exc)[:6000]
                if cut(response):
                    error = f"The reply was cut off at the output limit while writing this call. {error}"
                messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps({"error": error})})
                row = {"label": label, "event": "output.rejected", "error": error}
                if retried(row, response):
                    pass
                elif undelivered(exc) and wasted < grace:
                    attempt, wasted, row["charged"] = attempt - 1, wasted + 1, False
                trace.append(row)
                continue
            trace.append({"label": label, "event": call.name, "effort": current})
            return call.name, value
        for call in response.tool_calls:
            try:
                if call.name in query:
                    result = query[call.name](call.arguments)
                    if inspect.isawaitable(result):
                        result = await result
                else:
                    result = {"error": f"unknown tool: {call.name}"}
            except (ValueError, TypeError, KeyError, IndexError) as exc:
                result = {"error": str(exc)[:4000]}
            messages.append(
                {"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, ensure_ascii=False)}
            )
            trace.append({"label": label, "event": "query", "tool": call.name, "arguments": call.arguments})
    raise ExchangeError(f"{label}: submission budget exhausted", trace)
