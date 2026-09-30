"""What an attribution must cover: every input of the curation it precedes.

A root curation's inputs are the Analyst's requirements (by id), the materials handed over with the signals and,
when there is neither, the task. A child Harness's curation also carries the node requirements its parent routed
to it, each addressed as `node:<playbook>/<node>#<n>`, and the parent's feedback routed to that child.
"""


def _material(item) -> str | None:
    if isinstance(item, dict):
        return item.get("name") or None
    if isinstance(item, str) and item.count("/") >= 2:
        return item.split("/")[-2]
    return None


def _collect(feedback, found: list[str]) -> None:
    if not isinstance(feedback, dict):
        return
    requirements = feedback.get("requirements")
    if isinstance(requirements, list):
        for number, row in enumerate(requirements, 1):
            if isinstance(row, dict):
                found.append(row.get("id") or f"R{number}")
    elif isinstance(requirements, dict):
        for node, rows in requirements.items():
            for number, row in enumerate(rows or (), 1):
                found.append((row.get("id") if isinstance(row, dict) else None) or f"node:{node}#{number}")
    for signal in feedback.get("signals") or ():
        if isinstance(signal, dict):
            for item in signal.get("attachments") or ():
                if name := _material(item):
                    found.append(f"material:{name}")
    _collect(feedback.get("feedback"), found)


def subjects(feedback) -> tuple[str, ...]:
    """The inputs to diagnose, each once, in the order the feedback gives them; `task` alone when there are none."""
    found: list[str] = []
    _collect(feedback, found)
    return tuple(dict.fromkeys(found)) or ("task",)
