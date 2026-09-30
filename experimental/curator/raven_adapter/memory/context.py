"""Validate message projections against host requirements and tool evidence pairing."""

from ..context_sources import message_text


class ProjectionOverflowError(ValueError):
    """A valid local projection needs the Loop's existing context-window recovery."""

    def __init__(self, size, allowance):
        self.size, self.allowance = size, allowance
        super().__init__(f"local memory projection exceeds host token allowance: {size} > {allowance}")


def protected_positions(messages, protected):
    positions = []
    start = 0
    for item in protected:
        index = next((i for i in range(start, len(messages)) if messages[i] == item), None)
        if index is None:
            raise ValueError(
                f"memory context removed or changed a protected message with fields {sorted(item)}; preserve the complete mapping including metadata"
            )
        positions.append(index)
        start = index + 1
    return positions


def check_tool_pairs(messages):
    pending = set()
    for message in messages:
        if message.get("role") not in {"system", "developer", "user", "assistant", "tool"}:
            raise ValueError("memory context contains an unsupported message role")
        if message.get("role") == "tool":
            identity = message.get("tool_call_id")
            if identity not in pending:
                raise ValueError("memory context contains an orphan tool result")
            pending.remove(identity)
        else:
            if pending:
                raise ValueError("memory context removed a required tool result")
            calls = message.get("tool_calls") or []
            pending = {call["id"] for call in calls}
            if len(pending) != len(calls):
                raise ValueError("memory context contains duplicate tool call IDs")
    if pending:
        raise ValueError("memory context ends with unanswered tool calls")


def validate_projection(request, result):
    """Check actual source preservation rather than treating every system byte as immutable."""
    protected_positions(result.messages, [request.messages[index] for index in request.required])
    for source in request.sources:
        if (
            source.required
            and source.text
            and not any(row.get("role") == source.role and source.text in message_text(row) for row in result.messages)
        ):
            raise ValueError(f"memory context removed or changed protected source: {source.name}")
    check_tool_pairs(result.messages)
