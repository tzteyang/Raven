"""Project actual completed tool evidence into the Memory command vocabulary."""

from .task_memory import Evidence


def observe(observation) -> Evidence | None:
    for row in reversed(observation.messages):
        if row.get("role") == "tool" and row.get("name") == "evidence_probe":
            lines = [line for line in row.get("content", "").splitlines() if line.startswith("FACT:")]
            if len(lines) == 1:
                return Evidence(call_id=row["tool_call_id"], value=lines[0].removeprefix("FACT:"))
    return None
