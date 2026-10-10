"""Read execution shards into inclusive stage totals without counting parent aggregates."""

from collections import defaultdict
from math import fsum

from raven.observability.ledger import LedgerError, merge, read_tree

FIELDS = (
    "input_total_tokens",
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "reasoning_tokens",
    "cost_usd",
    "quota_usd",
    "total_tokens",
)


def totals(attempts):
    result = {
        "attempts": sum(row["kind"] == "attempt" for row in attempts),
        "external_calls": sum(row["kind"] == "external" for row in attempts),
        "inconsistent_usage": sum(row.get("usage", {}).get("inconsistent", False) for row in attempts),
        "unfinished": sum(row["status"] == "running" for row in attempts),
        "failed": sum(row["status"] in {"error", "cancelled"} for row in attempts),
        "partial_usage": sum(not row.get("usage_complete", False) for row in attempts),
        "attempt_duration_ms": fsum(row["duration_ms"] or 0 for row in attempts),
        "missing": {},
    }
    for field in FIELDS:
        values = [row.get("usage", {}).get(field) for row in attempts]
        known = [value for value in values if value is not None]
        result[field] = (fsum(known) if field.endswith("usd") else sum(known)) if known else None
        result["missing"][field] = len(values) - len(known)
    return result


def part(row):
    """Who a request belongs to: an external invocation is research; a native request is the employee's when it ran
    under one of its sessions, a subagent's under a hosted (`acp:`) session, and the simulation's with no session."""
    session = str(row["attributes"].get("session_key") or "")
    if row["kind"] == "external":
        return "research"
    if session.startswith("acp:"):
        return "subagents"
    return "employee" if session else "simulation"


def build(rows, *, run_id=None):
    rows = merge(row for row in rows if run_id is None or row["run_id"] == run_id)
    index = {row["id"]: row for row in rows}
    attempts = [row for row in rows if row["kind"] in {"attempt", "external"}]
    descendants = defaultdict(list)
    orphans = set()
    for row in attempts:
        parent, visited = row["parent_id"], {row["id"]}
        while parent and parent not in visited:
            visited.add(parent)
            if parent not in index:
                orphans.add(parent)
                break
            descendants[parent].append(row)
            parent = index[parent]["parent_id"]
    return {
        "available": bool(rows),
        "run_ids": sorted({row["run_id"] for row in rows}),
        "totals": totals(attempts),
        "missing_parents": sorted(orphans),
        "spans": [{**row, "totals": totals(descendants[row["id"]])} for row in rows if row["kind"] == "span"],
        "attempts": [{**row, "part": part(row)} for row in attempts],
    }


def read(root, *, run_id=None):
    try:
        return build(read_tree(root), run_id=run_id)
    except (KeyError, TypeError, ValueError) as exc:
        raise LedgerError(f"Invalid execution accounting under {root}: {exc}") from exc


def cost(report):
    """One reported-money view for the run page, durable report and budget reader."""
    groups = defaultdict(list)
    for row in report["attempts"]:
        groups[row["part"]].append(row)
    parts = {name: totals(rows) for name, rows in groups.items()}
    return {
        "total": report["totals"]["cost_usd"],
        "by_part": {part: values["cost_usd"] for part, values in parts.items() if values["cost_usd"] is not None},
        "quota": {part: values["quota_usd"] for part, values in parts.items() if values["quota_usd"] is not None},
        "missing_calls": sum(
            row.get("usage", {}).get("cost_usd") is None and row.get("usage", {}).get("quota_usd") is None
            for row in report["attempts"]
        ),
        "source": "execution ledger",
    }
