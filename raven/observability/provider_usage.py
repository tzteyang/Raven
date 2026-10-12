"""Preserve absent wire counters while adapting usage for execution accounting."""

from raven.providers.usage import reported_cost, responses_usage, token_count


def mapping(raw):
    """The provider's usage object as JSON data, without parsing or discarding its extra counters."""
    if isinstance(raw, dict):
        return raw
    return raw.model_dump(mode="json") if callable(getattr(raw, "model_dump", None)) else {}


def media(raw):
    if not isinstance(raw, dict):
        return {}
    return chat(raw) if "prompt_tokens" in raw else responses_usage(raw)


def capture_error(accounting, response, normalize):
    """Keep a failed HTTP response's reported usage before the adapter raises or retries."""
    if not accounting or response is None or not callable(getattr(response, "json", None)):
        return
    try:
        payload = response.json()
    except (ValueError, RuntimeError):
        return
    if isinstance(payload, dict) and isinstance(payload.get("usage"), dict):
        accounting.usage(
            normalize(payload["usage"]),
            raw=payload["usage"],
            response_id=payload.get("id"),
            served_model=payload.get("model"),
            complete=True,
        )


def summarize(raw):
    """Normalize one cumulative report without inventing missing counters or fresh input."""
    prompt = token_count(raw.get("prompt_tokens"))
    output = token_count(raw.get("completion_tokens"))
    read = token_count(raw.get("cache_read_input_tokens"))
    write = token_count(raw.get("cache_creation_input_tokens"))
    inclusive = raw.get("prompt_tokens_include_cache", True)
    split = None not in (prompt, read, write)
    inconsistent = bool(inclusive and split and prompt < read + write)
    fresh = prompt if not inclusive else prompt - read - write if split and not inconsistent else None
    total_input = prompt if inclusive else prompt + read + write if split else None
    total = token_count(raw.get("total_tokens"))
    if total is None and total_input is not None and output is not None:
        total = total_input + output
    return {
        "input_tokens": fresh,
        "input_total_tokens": total_input,
        "output_tokens": output,
        "cache_read_tokens": read,
        "cache_write_tokens": write,
        "reasoning_tokens": token_count(raw.get("reasoning_tokens")),
        "total_tokens": total,
        "cost_usd": reported_cost(raw.get("cost_usd")),
        "quota_usd": reported_cost(raw.get("quota_usd")),
        "inconsistent": inconsistent,
    }


def chat(raw):
    if raw is None:
        return {}
    get = raw.get if isinstance(raw, dict) else lambda key, default=None: getattr(raw, key, default)
    details = get("prompt_tokens_details") or {}
    details = details if isinstance(details, dict) else details.model_dump() if hasattr(details, "model_dump") else {}
    output = get("completion_tokens_details") or {}
    output = output if isinstance(output, dict) else output.model_dump() if hasattr(output, "model_dump") else {}
    return {
        "prompt_tokens": token_count(get("prompt_tokens")),
        "completion_tokens": token_count(get("completion_tokens")),
        "cache_read_input_tokens": token_count(details.get("cached_tokens")),
        "cache_creation_input_tokens": token_count(details.get("cache_write_tokens")),
        "reasoning_tokens": token_count(output.get("reasoning_tokens")),
        "prompt_tokens_include_cache": True,
        "cost_usd": reported_cost(get("cost")),
    }


def anthropic(raw):
    if not isinstance(raw, dict):
        return {}
    write = token_count(raw.get("cache_creation_input_tokens"))
    creation = raw.get("cache_creation")
    if write is None and isinstance(creation, dict) and creation:
        counts = [token_count(value) for value in creation.values()]
        if all(value is not None for value in counts):
            write = sum(counts)
    return {
        "prompt_tokens": token_count(raw.get("input_tokens")),
        "completion_tokens": token_count(raw.get("output_tokens")),
        "cache_read_input_tokens": token_count(raw.get("cache_read_input_tokens")),
        "cache_creation_input_tokens": write,
        "prompt_tokens_include_cache": False,
        "cost_usd": reported_cost(raw.get("cost")),
    }
