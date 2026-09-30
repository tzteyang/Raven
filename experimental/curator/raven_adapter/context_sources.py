"""Capture native context contributions without prescribing a generated Memory layout.

The ContextAssembler builder lists and scent object are the only private source
seams used here. Other adapters consume ContextSource and never inspect those
members or parse product-specific headings.
"""

import re
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass

from raven.context_engine.assembler import ContextAssembler
from raven.context_engine.factory import build_context_engine
from raven.contracts.context import ContextEngine
from raven.providers.prompt_cache import STABLE_PREFIX_KEY

from ..harness.context import ContextSource
from ..harness.declaration import typed
from .observe import plain

_COLLECTING: ContextVar[list | None] = ContextVar("curator_context_sources", default=None)
_KINDS = {
    "identity": "identity",
    "bootstrap": "profile",
    "memory": "memory",
    "curator": "memory",
    "skills": "skills",
    "active_skills": "skills",
}


def message_text(message):
    value = message.get("content")
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(part.get("text", "") for part in value if isinstance(part, dict))
    return ""


def replace_text(message, old, new):
    """Replace one captured text fragment without changing unrelated content blocks."""
    content = message.get("content")
    if isinstance(content, str) and old in content:
        message["content"] = content.replace(old, new, 1)
    elif isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and old in part.get("text", ""):
                part["text"] = part["text"].replace(old, new, 1)
                part.pop("cache_control", None)
                break
        else:
            return False
    else:
        return False
    message.pop(STABLE_PREFIX_KEY, None)
    message.pop("cache_control", None)
    return True


class _Builder:
    def __init__(self, source):
        self.source = source
        self.name, self.order, self.needs_prefix = source.name, source.order, source.needs_prefix
        self.stable = bool(getattr(source, "stable", False))

    def __getattr__(self, name):
        return getattr(self.source, name)

    async def build(self, context):
        value = await self.source.build(context)
        collecting = _COLLECTING.get()
        if collecting is not None:
            kind = _KINDS.get(self.name, "other")
            collecting.append(
                ContextSource(
                    name=self.name,
                    owner="native",
                    kind=kind,
                    text=value.text if value is not None else "",
                    required=kind in {"identity", "other"},
                    stable=self.stable,
                )
            )
        return value


class _Scent:
    def __init__(self, source):
        self.source = source

    async def build(self, *args, **kwargs):
        value = await self.source.build(*args, **kwargs)
        if value is not None and _COLLECTING.get() is not None:
            _COLLECTING.get().append(
                ContextSource(
                    name="skill_menu",
                    owner="native",
                    kind="skills",
                    role="user",
                    text=re.sub(r"\n{2,}", "\n", value.text.strip()),
                    required=False,
                )
            )
        return value


@dataclass
class ContextFrame:
    sources: tuple
    messages: list
    history: list
    budget: object
    structured: bool


class SourceContext(ContextEngine):
    """Preserve the native lifecycle and retain actual source snapshots per session."""

    name = "curator-sources"

    def __init__(self, base=None, *, initialized=None):
        self.base = base
        self.initialized = initialized
        self.frames = {}
        self.structured = False
        self.expected_identity = False

    @property
    def owns_compaction(self):
        return self.base.owns_compaction if self.base is not None else True

    @property
    def skills_router(self):
        return getattr(self.base, "skills_router", None)

    def bind(self, runtime, config):
        loop = runtime.loop
        if self.base is None:
            self.base = build_context_engine(
                workspace=loop.workspace,
                config=loop.context_config,
                builder=loop.context,
                provider=loop.provider,
                model=loop.model,
                context_window_tokens=loop.context_window_tokens,
                get_tool_definitions=loop.tools.get_definitions,
                list_subagents=lambda: loop.subagents.list_agents(),
                get_tool_notices=loop._mcp_tool_notices,
                now_fn=loop._now_fn,
                backend=loop.backend,
                memory_config=loop.memory_config,
                skill_forge_config=config.skill_forge,
                skill_forge_router_config=config.skill_forge.router,
                skill_hub_client=loop._skill_hub_client,
                provider_pool=loop._provider_pool,
                blocklist_reader=loop._skill_blocklist_reader,
            )
        if isinstance(self.base, ContextAssembler):
            builders = [_Builder(source) for source in self.base._builders]
            names = [builder.name for builder in builders]
            self.expected_identity = "identity" in names
            if len(names) != len(set(names)):
                raise ValueError("context source identities must be unique")
            self.base._builders = builders
            self.base._phase_a = [builder for builder in builders if not builder.needs_prefix]
            self.base._phase_b = [builder for builder in builders if builder.needs_prefix]
            if self.base._scent is not None:
                self.base._scent = _Scent(self.base._scent)
            self.structured = True
        else:
            self.structured = callable(getattr(self.base, "context_sources", None))

    async def assemble(self, session_key, session_messages, budget, *, turn):
        collected = []
        token = _COLLECTING.set(collected)
        try:
            result = await self.base.assemble(session_key, session_messages, budget, turn=turn)
        finally:
            _COLLECTING.reset(token)
        if not isinstance(self.base, ContextAssembler) and self.structured:
            collected = list(typed(tuple[ContextSource, ...], self.base.context_sources(session_key)))
        if self.expected_identity and not any(
            source.name == "identity" and source.text.strip() for source in collected
        ):
            raise ValueError("the required native identity source was unavailable during assembly")
        messages = plain(result.messages)
        if not self.structured:
            collected = [
                ContextSource(
                    name=f"opaque:{index}", owner="native", kind="other", role=row["role"], text=message_text(row)
                )
                for index, row in enumerate(messages)
                if row.get("role") in {"system", "developer"}
            ]
        frame = ContextFrame(tuple(collected), messages, plain(session_messages), budget, self.structured)
        self.frames[session_key] = frame
        if self.initialized is not None:
            await self.initialized(session_key, frame)
        return result

    def frame(self, session_key):
        try:
            return self.frames[session_key]
        except KeyError as exc:
            raise RuntimeError("model input requires an actual context assembly for this session") from exc

    def strip_native_skills(self, messages, frame):
        if not frame.structured:
            raise ValueError("explicit skill selection requires a context source provider")
        result = deepcopy(messages)
        for source in frame.sources:
            if source.kind != "skills" or not source.text:
                continue
            matching = [row for row in result if row.get("role") == source.role]
            if source.role == "user":
                anchor = next((message_text(row) for row in reversed(frame.messages) if row.get("role") == "user"), "")
                matching = [row for row in matching if anchor and message_text(row).startswith(anchor)]
            if not any(replace_text(row, source.text, "") for row in matching):
                raise ValueError(f"native skill contribution changed outside its source boundary: {source.name}")
        return result

    def projection_sources(self, messages, frame, *, native_skills):
        sources = [source for source in frame.sources if native_skills or source.kind != "skills"]
        original = frame.messages if native_skills else self.strip_native_skills(frame.messages, frame)
        original_system = [message_text(row) for row in original if row.get("role") in {"system", "developer"}]
        for index, row in enumerate(messages):
            if row.get("role") not in {"system", "developer"}:
                continue
            text = message_text(row)
            for prefix in original_system:
                if prefix and prefix in text:
                    text = text.replace(prefix, "", 1)
                    break
            if text.strip():
                sources.append(
                    ContextSource(
                        name=f"runtime:{index}",
                        owner="runtime",
                        kind="guidance",
                        role=row["role"],
                        text=text,
                    )
                )
        return tuple(sources)

    async def after_turn(self, session_key, outcome):
        await self.base.after_turn(session_key, outcome)

    def set_provider(self, provider, model):
        if self.base is not None:
            self.base.set_provider(provider, model)

    def set_context_window(self, tokens):
        if self.base is not None:
            self.base.set_context_window(tokens)
