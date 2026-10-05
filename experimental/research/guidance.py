"""Derive optional grouped research questions from isolated product-case materials."""

import json
from pathlib import Path

from raven.agent.tools.registry import call_failed

from ..curator.generation.context.render import tool
from ..curator.harness.declaration import schema_for
from ..iteration.exchange import exchange, messages
from .collection import CollectionLimits, _Calls
from .information import ResearchGuide, _Model

SUBMIT = "submit_research_guidance"
PROMPT = Path(__file__).resolve().parent / "prompts" / "guidance.md"


class Guidance(_Model):
    groups: tuple[ResearchGuide, ...] = ()


async def derive_guidance(
    provider, objective, exploration, *, model=None, effort="high", limits=CollectionLimits(), records: Path
):
    """Read research-only sources on demand; return directions rather than knowledge or organisational rules."""
    records = Path(records)
    records.mkdir(parents=True, exist_ok=False)
    calls, trace, used = _Calls(provider), [], 0
    definitions = [
        entry
        for entry in exploration.registry.get_definitions()
        if entry["function"]["name"] in {"read_file", "list_dir", "grep", "find"}
    ]
    sources = exploration.sources
    conversation = messages(
        PROMPT.read_text(),
        {
            "objective": objective,
            "sources": {name: {"path": row["snapshot_path"], "digest": row["digest"]} for name, row in sources.items()},
            "workspace": exploration.describe(),
        },
    )

    def native(name):
        async def run(arguments):
            nonlocal used
            calls.check(arguments)
            if used >= limits.queries:
                raise ValueError("guidance read budget exhausted; submit only useful supported directions")
            used += 1
            output = await exploration.registry.execute(name, arguments, run_meta=calls.metadata(arguments))
            if getattr(output, "blocks_call", False):
                calls.blocked = True
            result = {"error" if call_failed(output) else "text": str(output)}
            if not call_failed(output) and name == "read_file":
                read_path = Path(arguments["path"])
                if not read_path.is_absolute():
                    read_path = exploration.root / read_path
                result["source_ids"] = [
                    key for key, source in sources.items() if Path(source["snapshot_path"]) == read_path.resolve()
                ]
            return result

        return run

    def submit(arguments):
        calls.check(arguments)
        guidance = Guidance.model_validate(arguments)
        for group in guidance.groups:
            unknown = set(group.sources) - sources.keys()
            if not group.sources or unknown:
                raise ValueError(f"each group must cite exact supplied source ids; unknown ids: {sorted(unknown)}")
        return guidance

    query = {entry["function"]["name"]: native(entry["function"]["name"]) for entry in definitions}
    definitions.append(
        tool(SUBMIT, "Submit useful research directions grouped by related work problems.", schema_for(Guidance))
    )
    try:
        with exploration.registry.turn_scope():
            _, result = await exchange(
                calls,
                conversation,
                definitions,
                submit={SUBMIT: submit},
                query=query,
                model=model,
                effort=effort,
                max_calls=limits.guidance_calls,
                timeout=limits.timeout,
                trace=trace,
                label="research.guidance",
            )
        exploration.verify()
        (records / "guidance.json").write_text(result.model_dump_json(indent=2))
        return result.groups
    finally:
        (records / "trace.json").write_text(json.dumps(trace, ensure_ascii=False, indent=2))
        (records / "conversation.json").write_text(json.dumps(conversation, ensure_ascii=False, indent=2))
