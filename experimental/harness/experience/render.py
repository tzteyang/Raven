"""Render adopted role-specific experience through one versioned, deterministic context format."""

from pathlib import Path

from experimental.harness.experience.governance import fingerprint

DEFINITIONS = Path(__file__).with_name("prompts") / "guidance.md"


def version() -> str:
    return fingerprint({"format": 1, "definitions": DEFINITIONS.read_text()})


def guidance(items) -> str:
    if not items:
        return ""
    sections = [DEFINITIONS.read_text().strip()]
    for item in items:
        kind = item.get("kind", "procedure")
        if kind not in {"principle", "procedure"}:
            raise ValueError("textual guidance requires a declared principle or procedure")
        identity = str(item["id"])[:12]
        content = item.get("text", item.get("guidance", ""))
        if not isinstance(content, str) or not content.strip():
            raise ValueError("an adopted experience needs usable instruction text")
        lines = [f"### {kind.title()} [{identity}]", f"Scope: {item.get('scope', 'current task')}"]
        condition = item.get("condition")
        if condition:
            lines.append(f"When: {condition['situation']}")
            lines.append(f"Phase: {condition['phase']}; harness scope: {condition.get('scope_kind', 'any')}")
            for key, label in (
                ("required_capabilities", "Required capabilities"),
                ("contract_ids", "Required contracts"),
                ("limits", "Limits"),
            ):
                if condition.get(key):
                    lines.append(f"{label}: " + "; ".join(condition[key]))
        if item.get("support_kind"):
            lines.append(f"Evidence supports: {item['support_kind']}")
        lines.append(content)
        sections.append("\n\n".join(lines))
    return "\n\n".join(sections)
