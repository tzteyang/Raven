"""Role-scoped native setup services called by generated strategy prepare methods."""

import json
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, create_model

from raven.config.raven import ContextConfig, MemoryConfig, SkillForgeConfig, TokenWiseConfig
from raven.config.schema import AgentDefaults, MCPServerConfig, ToolsConfig
from raven.context_engine.segments.render import BOOTSTRAP_FILES
from raven.playbook.store import PlaybookStore
from raven.playbook.types import PlaybookSpec

from ...requirements import Requirement
from ..harness.artifact import ArtifactPath
from ..harness.declaration import schema_for, typed
from ..harness.prompts import Prompt
from .materialize import load_object, merge


def _policy(name, native, fields):
    """Keep native field validation while exposing only an owner's explicit slice."""
    return create_model(
        name,
        __config__=ConfigDict(extra="forbid", frozen=True, populate_by_name=True),
        **{key: (native.model_fields[key].annotation, deepcopy(native.model_fields[key])) for key in fields},
    )


ContextPolicy = _policy(
    "ContextPolicy",
    ContextConfig,
    (
        "drop_segments",
        "fast_path_threshold",
        "curator_model",
        "curator_provider",
        "curator_timeout_seconds",
        "relevance_decay",
        "relevance_reference_boost",
        "protect_first_n",
    ),
)
WindowPolicy = _policy(
    "WindowPolicy",
    AgentDefaults,
    ("context_window_tokens", "compaction", "image_window_budget_bytes", "memory_window", "enable_personalization"),
)
TokenPolicy = _policy(
    "TokenPolicy",
    TokenWiseConfig,
    ("cache_optimization", "max_cache_breakpoints", "cache_ttl", "tool_result_lifecycle", "budget"),
)
BackendPolicy = _policy("BackendPolicy", MemoryConfig, ("backend", "memory_top_k"))
GenerationPolicy = _policy(
    "GenerationPolicy",
    AgentDefaults,
    ("model", "provider", "temperature", "reasoning_effort", "model_overrides"),
)
ExecutionPolicy = _policy(
    "ExecutionPolicy",
    AgentDefaults,
    (
        "llm_call_timeout",
        "stream_idle_timeout",
        "llm_first_byte_timeout",
        "max_tool_iterations",
        "empty_recovery_enabled",
        "post_tool_empty_max_nudges",
        "thinking_prefill_max_retries",
        "empty_content_max_retries",
        "llm_error_retry_delays",
        "llm_retry_after_output",
    ),
)
ToolPolicy = _policy(
    "ToolPolicy",
    ToolsConfig,
    ("web", "exec", "browser", "ask_user", "media", "tool_search", "connection_add", "disabled_tools"),
)
SkillPolicy = _policy(
    "SkillPolicy",
    SkillForgeConfig,
    (
        "enabled",
        "discovery",
        "blocklist",
        "auto_install",
        "router",
        "scan_max_depth",
        "top_k",
        "local_pool_top_k",
        "mass_pool_top_k",
        "local_weight",
        "mass_reranker_overfetch",
        "rewrite_enabled",
        "rewrite_max_tokens",
        "injection_mode",
        "inject_max",
        "disable_always",
        "always_max",
        "llm_gate_enabled",
        "llm_gate_max_select",
        "llm_gate_pool_size",
        "llm_gate_model",
        "llm_gate_provider",
        "llm_gate_temperature",
        "llm_gate_max_tokens",
    ),
)


class NativeComponent(BaseModel):
    """An owner-selected dependency, constructed and released by native hosting."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    owner: Literal["memory", "planning", "capability", "action"]
    kind: Literal["memory_backends", "session_observers", "services"]
    name: str = Field(min_length=1)
    factory: str = Field(pattern=r"^[a-zA-Z_][a-zA-Z0-9_.]*:[a-zA-Z_][a-zA-Z0-9_]*$")


class PreparedHarness(BaseModel):
    """Host-produced effects of running candidate code; never an authoring payload."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    config: dict[str, JsonValue] = Field(default_factory=dict)
    extensions: dict[str, JsonValue] = Field(default_factory=dict)
    content: dict[str, dict[ArtifactPath, str]] = Field(default_factory=dict)
    components: tuple[NativeComponent, ...] = ()
    context_engine: str | None = None
    prompts: tuple[str, ...] = ()

    def files(self) -> dict[str, str]:
        result = {}
        for owner, files in self.content.items():
            for path, text in files.items():
                if path in result:
                    raise ValueError(f"multiple strategies own the same content path: {path}")
                result[path] = text
        return result


class Preparation:
    """Collect one candidate's typed effects, then freeze the setup services."""

    def __init__(self, baseline, artifact, package, recorder):
        self.baseline, self.artifact, self.package, self.recorder = baseline, artifact, package, recorder
        self.config, self.extensions, self.content = {}, {}, {}
        self.components, self.prompts = [], []
        self.context_engine = None
        self.closed = False

    def record(self, owner, operation, value):
        if self.closed:
            raise ValueError("candidate preparation is closed")
        self.recorder.add("strategy.setup", owner=owner, operation=operation, value=value)

    def freeze(self) -> PreparedHarness:
        self.closed = True
        result = PreparedHarness(
            config=self.config,
            extensions=self.extensions,
            content=self.content,
            components=tuple(self.components),
            context_engine=self.context_engine,
            prompts=tuple(self.prompts),
        )
        result.files()
        return result

    def host(self, owner):
        return {"memory": MemoryHost, "planning": PlanningHost, "capability": CapabilityHost, "action": ActionHost}[
            owner
        ](self, owner)


class StrategyHost:
    """Common, candidate-only facilities; no active runtime or configuration setter."""

    def __init__(self, preparation, owner):
        self._preparation, self._owner = preparation, owner

    def _patch(self, policy, expected, root, path):
        if not isinstance(policy, expected):
            raise TypeError(f"expected {expected.__name__}")
        if policy.model_fields_set - expected.model_fields.keys():
            raise ValueError("policy contains fields outside its declared owner slice")
        value = typed(expected, policy).model_dump(mode="json", include=policy.model_fields_set)
        self._preparation.record(self._owner, expected.__name__, value)
        node = getattr(self._preparation, root)
        for key in path[:-1]:
            node = node.setdefault(key, {})
        node[path[-1]] = merge(node.get(path[-1], {}), value)

    def _component(self, kind, name, factory):
        value = NativeComponent(owner=self._owner, kind=kind, name=name, factory=factory)
        self._preparation.record(self._owner, kind, value)
        if not self._preparation.baseline.resident and kind in {"services", "session_observers"}:
            raise ValueError(f"{kind} require resident hosting")
        if any(item.kind == kind and item.name == name for item in self._preparation.components):
            raise ValueError(f"duplicate native component: {kind}/{name}")
        self._preparation.components.append(value)

    def service(self, name: str, factory: str) -> None:
        """Request a native generation service owned by this strategy; never start it here."""
        self._component("services", name, factory)

    def prompt(self, reference: str) -> None:
        """Validate and index an authored Prompt; its actual consumers stay in strategy code."""
        preparation = self._preparation
        preparation.record(self._owner, "prompt", reference)
        value = load_object(reference, preparation.package)
        if not isinstance(value, Prompt) or not value.path.is_relative_to(preparation.package.resolve()):
            raise ValueError("a prompt must reference a template in the candidate package")
        relative = value.path.relative_to(preparation.package.resolve()).as_posix()
        if preparation.artifact.files.get(relative) != value.template:
            raise ValueError("prompt template differs from its candidate asset")
        if reference not in preparation.prompts:
            preparation.prompts.append(reference)


class MemoryHost(StrategyHost):
    """Native context/storage dependencies requested by Memory.prepare."""

    def context(self, policy: ContextPolicy) -> None:
        self._patch(policy, ContextPolicy, "extensions", ("context",))

    def window(self, policy: WindowPolicy) -> None:
        self._patch(policy, WindowPolicy, "config", ("agents", "defaults"))

    def tokens(self, policy: TokenPolicy) -> None:
        self._patch(policy, TokenPolicy, "extensions", ("token_wise",))

    def backend(self, policy: BackendPolicy) -> None:
        self._patch(policy, BackendPolicy, "extensions", ("memory",))

    def profile(self, files: dict[str, str]) -> None:
        """Own native bootstrap files; omission from a full prepared revision withdraws them."""
        files = typed(dict[str, str], files)
        if files.keys() - set(BOOTSTRAP_FILES):
            raise ValueError("profile content must use native bootstrap paths")
        self._preparation.record(self._owner, "profile", files)
        self._preparation.content.setdefault(self._owner, {}).update(files)

    def engine(self, factory: str) -> None:
        """Choose a native ContextEngine delegate whose lifecycle and sources remain checked."""
        self._preparation.record(self._owner, "context_engine", factory)
        if self._preparation.context_engine is not None:
            raise ValueError("a candidate can choose only one context engine")
        self._preparation.context_engine = factory

    def backend_factory(self, name: str, factory: str) -> None:
        self._component("memory_backends", name, factory)

    def session_observer(self, name: str, factory: str) -> None:
        """Request native nonblocking retirement cleanup, not an active-turn interaction."""
        self._component("session_observers", name, factory)


class PlanningHost(StrategyHost):
    """Prepare inspectable native procedures before parent/child generation."""

    def playbook(self, spec: PlaybookSpec, requirements: dict[str, list[Requirement]] | None = None) -> None:
        """Compile a complete native procedure and explicit node requirements in isolation."""
        if not self._preparation.baseline.allow_delegation:
            raise ValueError("a leaf Harness cannot contribute playbooks")
        spec = typed(PlaybookSpec, spec)
        requirements = typed(dict[str, list[Requirement]], requirements or {})
        nodes = {node.id for node in spec.nodes or ()}
        if requirements.keys() - nodes or any(not rows for rows in requirements.values()):
            raise ValueError("requirements must be nonempty and belong to declared playbook nodes")
        self._preparation.record(self._owner, "playbook", {"spec": spec, "requirements": requirements})
        with tempfile.TemporaryDirectory(prefix="raven-curator-playbook-") as temporary:
            store = PlaybookStore(Path(temporary), builtin_root=Path(temporary) / "no-builtins")
            path = store.save(spec)
            files = {f"playbooks/{spec.name}/playbook.md": path.read_text()}
        for name, rows in requirements.items():
            files[f"playbooks/{spec.name}/nodes/{name}/requirements.json"] = json.dumps(
                [row.model_dump(mode="json") for row in rows],
                ensure_ascii=False,
            )
        owned = self._preparation.content.setdefault(self._owner, {})
        if owned.keys() & files.keys():
            raise ValueError(f"playbook was prepared twice: {spec.name}")
        owned.update(files)


class CapabilityHost(StrategyHost):
    """Configure actual native capability mechanisms; admission still uses register."""

    def tools(self, policy: ToolPolicy) -> None:
        self._patch(policy, ToolPolicy, "config", ("tools",))

    def skills(self, policy: SkillPolicy) -> None:
        self._patch(policy, SkillPolicy, "extensions", ("skill_forge",))

    def pin_skills(self, names: tuple[str, ...]) -> None:
        names = typed(tuple[str, ...], names)
        self._preparation.record(self._owner, "pinned_skills", names)
        self._preparation.extensions.setdefault("context", {})["pinned_skill_ids"] = list(names)

    def mcp(self, name: str, connection: MCPServerConfig) -> None:
        """Request a connector; the host later connects, verifies readiness and closes it."""
        if not name or "/" in name or "\\" in name:
            raise ValueError("MCP connection name must be a nonempty segment")
        supplied_fields = connection.model_fields_set
        connection = typed(MCPServerConfig, connection)
        self._preparation.record(self._owner, "mcp", {"name": name, "enabled": connection.enabled})
        servers = self._preparation.config.setdefault("tools", {}).setdefault("mcp_servers", {})
        if name in servers:
            raise ValueError(f"MCP connection was prepared twice: {name}")
        servers[name] = connection.model_dump(mode="json", include=supplied_fields)

    def plugin(self, name: str, *, enabled: bool) -> None:
        """Select an existing plugin without adding roots or overriding a host opt-out."""
        from raven.core.plugin_stack import discover_plugins

        baseline = self._preparation.baseline.extensions
        known = {item.manifest.id for item in discover_plugins(baseline)}
        if name not in known or name == "experimental-curator":
            raise ValueError("plugin selection requires an existing host-supplied plugin")
        if enabled and name in baseline.plugins.disabled:
            raise ValueError("a plugin disabled by the host cannot be re-enabled by a strategy")
        self._preparation.record(self._owner, "plugin", {"name": name, "enabled": enabled})
        plugins = self._preparation.extensions.setdefault("plugins", {})
        disabled = list(plugins.get("disabled", baseline.plugins.disabled))
        if enabled:
            disabled = [item for item in disabled if item != name]
        elif name not in disabled:
            disabled.append(name)
        plugins["disabled"] = disabled


class ActionHost(StrategyHost):
    """Generation and loop policies applied before native model and budget construction."""

    def generation(self, policy: GenerationPolicy) -> None:
        self._patch(policy, GenerationPolicy, "config", ("agents", "defaults"))

    def execution(self, policy: ExecutionPolicy) -> None:
        self._patch(policy, ExecutionPolicy, "config", ("agents", "defaults"))


def describe_preparation(baseline):
    """Expose the exact current host policy schemas and lifecycle reachability."""
    from raven.agent.loop.turn_path import _SKIP_AFTER_SEND_ORIGINS, _SKIP_USER_INBOUND_ORIGINS

    return {
        "policies": {
            role: {name: schema_for(model) for name, model in models.items()}
            for role, models in {
                "memory": {
                    "context": ContextPolicy,
                    "window": WindowPolicy,
                    "tokens": TokenPolicy,
                    "backend": BackendPolicy,
                },
                "capability": {"tools": ToolPolicy, "skills": SkillPolicy, "mcp": MCPServerConfig},
                "planning": {"playbook": PlaybookSpec, "requirement": Requirement},
                "action": {"generation": GenerationPolicy, "execution": ExecutionPolicy},
            }.items()
        },
        "profile_paths": list(BOOTSTRAP_FILES),
        "resident_services": baseline.resident,
        "session_retirement": baseline.resident,
        "playbooks": baseline.allow_delegation,
        "input": baseline.origin not in _SKIP_USER_INBOUND_ORIGINS,
        "archive": baseline.origin not in _SKIP_AFTER_SEND_ORIGINS,
    }
