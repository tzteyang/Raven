"""Validate native model call arguments before execution or structured submission."""

import json

from raven.contracts.tool import RAW_ARGUMENTS_KEY


def argument_errors(response):
    invalid_calls = []
    for call in response.tool_calls:
        meta = call.run_meta
        if response.truncated or response.finish_reason == "length" or (meta and meta.truncation):
            error = (
                "The response or tool arguments were truncated at the per-call output limit, which counts your "
                "reasoning too. Resubmit a complete call that fits; split large submissions across calls and "
                "keep draft reasoning out of tool arguments."
            )
        elif RAW_ARGUMENTS_KEY in call.arguments or (meta and meta.arguments_repaired):
            error = "Tool arguments were not a valid JSON object. Resubmit with correctly encoded arguments."
            raw = call.arguments.get(RAW_ARGUMENTS_KEY)
            if isinstance(raw, str):
                try:
                    json.loads(raw)
                except json.JSONDecodeError as exc:
                    error += f" Parser: {exc}"
        else:
            continue
        invalid_calls.append({"tool_call_id": call.id, "tool": call.name, "error": error})
    return invalid_calls
