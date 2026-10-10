"""What a customer on an online chat channel receives from one employee turn.

A channel shows only finished output (`raven/gateway/outlet.py`): the text replies, each file delivery with the
caption the employee wrote for it, and the short notice that an answer came without an organ. Progress lines, tool
hints and reasoning are never sent to a channel, so they are not part of what the customer, the owner or the record
treats as said to the customer.
"""

from experimental.harness.raven_adapter.observe import delivered_files

DEGRADED = "organ_degraded"


def seen(records) -> str:
    """The turn's customer-facing text in order; a delivery's caption counts once the delivery handed over a file.

    A delivery is read from its completed call, as the channel outlet reads it: a call refused before it ran, or one
    whose every file failed, carries no delivery and so sent nothing.
    """
    parts = []
    for row in records:
        if row.get("kind") != "runner.event":
            continue
        event = row.get("event") or {}
        if row.get("event_type") == "Text":
            parts.append(str(event.get("content") or ""))
        elif row.get("event_type") == "Notice" and str(event.get("kind") or "").lower() == DEGRADED:
            parts.append(str(event.get("detail") or ""))
        elif delivered_files(row):
            parts.append(str(event["metadata"]["raven_delivery"].get("message") or ""))
    return "\n".join(part for part in parts if part.strip())


def said(exchange) -> str:
    """What the customer received in reply to one message."""
    return seen(exchange.execution.records)
