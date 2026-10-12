"""Share identical source excerpts while preserving each Harness's actual source references."""

from copy import deepcopy


def execution_turns(*snapshots):
    """Keep captured turns across process restarts and detect new or revised turn evidence.

    Assembly and hosting rows have no turn identity; their process-specific
    fields are not new task input. A current process can report only its own
    turns, so absence never erases evidence already captured for this curation.
    """
    turns = {}
    for rows in snapshots:
        current = {}
        for row in rows:
            if turn_id := row.get("turn_id"):
                current.setdefault(turn_id, []).append(row)
        turns.update(current)
    return deepcopy(turns)


def child_observations(rows, name):
    """Select only this child's actual evidence, retaining parent session/turn association."""
    selected = []

    def visit(row, parent):
        context = {**parent, **{key: row[key] for key in ("session", "turn_id", "artifact_id") if key in row}}
        if row.get("kind") == "child.execution":
            if row.get("harness") == name:
                selected.append({**context, **deepcopy(row), "source": "trial.child"})
            return
        for child in row.get("records", ()):
            visit(child, context)

    for row in rows or ():
        visit(row, {})
    return selected


def merge_sources(sources, incoming, prefix):
    """Return the source names visible in this context; different excerpts never share an alias."""

    def identity(entry):
        return tuple(entry[key] for key in ("path", "digest", "start", "end"))

    held = {identity(entry): name for name, entry in sources.items()}
    aliases = {}
    for name, entry in incoming.items():
        key = identity(entry)
        if key not in held:
            alias = f"{prefix}.{name}"
            if alias in sources:
                raise ValueError(f"source alias collision: {alias}")
            sources[alias] = entry
            held[key] = alias
        aliases[name] = held[key]
    return aliases
