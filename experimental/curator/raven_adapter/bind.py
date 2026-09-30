"""Assemble generated changes through Raven's native configuration and plugin sockets."""

import json
import sys
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from inspect import Parameter, iscoroutinefunction, signature
from pathlib import Path, PurePosixPath
from typing import Any

from raven.agent.loop.bundles import HostWiring, TurnPolicy
from raven.agent.loop.recovery import limits_from_defaults
from raven.agent.tools.deliver import DeliverFilesTool
from raven.agent.tools.file_search import FindTool, GrepTool
from raven.agent.tools.filesystem import EditFileTool, ListDirTool, ReadFileTool, WriteFileTool
from raven.agent.tools.registry import admit_tool
from raven.agent.workdir import WorkdirPolicy, WorkdirResolver
from raven.contracts.loop_hooks import AgentHook
from raven.contracts.services import PluginService
from raven.contracts.session_events import SessionObserver
from raven.contracts.tool_gate import ToolGate
from raven.core.runtime import RavenRuntime, build_runtime
from raven.home import set_config_path
from raven.permissions.turn import current_turn
from raven.playbook.validate import validate_structure
from raven.plugins.context import PluginContext, ServiceLocator
from raven.providers.factory import make_lazy_provider
from raven.providers.pool import ProviderPool
from raven.session.manager import SessionManager

from ..harness import Artifact, Declaration
from ..harness.artifact import relative_path
from ..harness.interaction import InteractionScope
from ..harness.preparation import PreparationRequest
from ..harness.resources import ToolContribution
from .action.contracts import ActionBinding
from .action.runtime import BoundAction
from .capability.baseline import bind_workspace_skills
from .capability.catalog import CapabilityCatalog
from .capability.contracts import CapabilityBinding
from .capability.runtime import BoundCapability
from .content import ContentInstallation
from .context_sources import SourceContext
from .inference import Inference, supplied
from .inspection import Baseline, fingerprint, runtime_sources
from .inspection.runtime import playbook_library
from .materialize import (
    PLUGIN_ID,
    load_factory,
    native_settings,
    write_package,
)
from .memory.runtime import BoundMemory
from .memory.window import MemoryWindow
from .model_input import ModelInput
from .observe import LoopObserver, ObservedPool, ObservedProvider, Recorder
from .peers import RuntimePeers
from .planning.contracts import TARGET, PlanningBinding
from .planning.runtime import BoundPlanning
from .preparation import Preparation, PreparedHarness
from .prompts import bind_prompts
from .strategy import SESSION

_ASSEMBLY: ContextVar[Any] = ContextVar("curator_assembly", default=None)


def _no_plan():
    return None


_COMPONENT_PROTOCOLS = {
    "services": PluginService,
    "session_observers": SessionObserver,
    "tool_gates": ToolGate,
}


def conform(value, protocol):
    """Check each protocol method the way the host calls it: async where the host awaits, and the same arguments."""
    for method, contract in vars(protocol).items():
        if method.startswith("_") or not callable(contract):
            continue
        implementation = getattr(value, method, None)
        if not callable(implementation):
            raise TypeError(f"{protocol.__name__} lacks {method}")
        if iscoroutinefunction(contract) and not iscoroutinefunction(implementation):
            raise TypeError(f"{protocol.__name__}.{method} must be async; the host awaits it")
        parameters = list(signature(contract).parameters.values())[1:]
        positional = [
            object() for p in parameters if p.kind in (Parameter.POSITIONAL_ONLY, Parameter.POSITIONAL_OR_KEYWORD)
        ]
        keywords = {p.name: None for p in parameters if p.kind is Parameter.KEYWORD_ONLY}
        try:
            signature(implementation).bind(*positional, **keywords)
        except TypeError as exc:
            raise TypeError(
                f"{protocol.__name__}.{method} does not accept the host's call {method}{signature(contract)}: {exc}"
            ) from exc


def construct_component(kind, name, reference, context):
    """Called by native plugin factories, retaining failures the native host may silence."""
    package, objects, recorder, dependencies = _ASSEMBLY.get()
    recorder.add("component.call", kind_name=kind, name=name, factory=reference)
    try:
        factory = load_factory(reference, package)
        value = factory(context, **supplied(factory, dependencies))
        if value is None:
            raise TypeError("the requested factory declined construction")
        if kind == "tools":
            admit_tool(value)
        elif kind == "hooks":
            for method, contract in vars(AgentHook).items():
                if iscoroutinefunction(contract) and not callable(getattr(value, method, None)):
                    raise TypeError(f"hook lacks {method}")
            if not isinstance(getattr(value, "name", None), str):
                raise TypeError("hook lacks a native name")
        elif kind == "memory_backends":
            # recall_session, delete and health are optional on Raven's memory path.
            for method in ("recall", "store", "feedback", "start", "stop"):
                if not callable(getattr(value, method, None)):
                    raise TypeError(f"memory backend lacks {method}")
        else:
            conform(value, _COMPONENT_PROTOCOLS[kind])
        objects[kind, name] = value
        recorder.add(
            "component.constructed",
            kind_name=kind,
            name=name,
            factory=reference,
            implementation=f"{type(value).__module__}:{type(value).__qualname__}",
            runtime_name=getattr(value, "name", None),
        )
        return value
    except Exception as exc:
        recorder.add("component.error", kind_name=kind, name=name, error=f"{type(exc).__name__}: {exc}")
        raise


def _plugin(root, artifact, declaration, package, prepared):
    rows = [(item.kind, item.model_dump()) for item in prepared.components]
    action = artifact.values.get("action.strategy")
    if action is not None and ActionBinding.model_validate(action).dispatch:
        if any(kind == "tool_gates" and row["name"] == "curator-action" for kind, row in rows):
            raise ValueError("curator-action is reserved for the selected Action dispatch binding")
        rows.append(
            (
                "tool_gates",
                {
                    "name": "curator-action",
                    "factory": "experimental.curator.raven_adapter.action.runtime:build_gate",
                },
            )
        )
    if not rows:
        return None
    wrapper_name = f"_bindings_{package.name}"
    wrapper = ["from experimental.curator.raven_adapter.bind import construct_component"]
    manifest = ["[plugin]", f"id = {json.dumps(PLUGIN_ID)}", 'version = "0.1.0"']
    for i, (kind, entry) in enumerate(rows):
        wrapper.extend(
            [
                f"def build_{i}(context):",
                f"    return construct_component({kind!r}, {entry['name']!r}, {entry['factory']!r}, context)",
            ]
        )
        manifest.extend(
            [
                f"[[plugin.contributes.{kind}]]",
                f"name = {json.dumps(entry['name'])}",
                f"factory = {json.dumps(f'{wrapper_name}:build_{i}')}",
            ]
        )
    (root / f"{wrapper_name}.py").write_text("\n".join(wrapper) + "\n")
    plugin = root / "plugins" / PLUGIN_ID
    plugin.mkdir(parents=True, exist_ok=True)
    (plugin / "raven-plugin.toml").write_text("\n".join(manifest) + "\n")
    return plugin.parent


@dataclass
class Bound:
    runtime: RavenRuntime
    baseline: Baseline
    artifact: Artifact
    recorder: Recorder
    observer: LoopObserver
    components: dict
    sources: dict
    planning: BoundPlanning | None = None
    strategies: dict = field(default_factory=dict)
    prompts: dict = field(default_factory=dict)
    capability: BoundCapability | None = None
    context_sources: SourceContext | None = None
    inference: Inference | None = None
    prepared: PreparedHarness = field(default_factory=PreparedHarness)
    content_installation: ContentInstallation | None = None

    async def prepare(self):
        if self.planning:
            await self.planning.prepare()
        for strategy in self.strategies.values():
            await strategy.prepare()

    async def start(self):
        await self.runtime.loop._connect_mcp()
        manager = self.runtime.loop.mcp_manager_if_started
        states = manager.status() if manager is not None else []
        self.recorder.add("mcp.status", servers=states)
        requested = self.prepared.config.get("tools", {}).get("mcp_servers", {})
        for name in requested:
            if self.baseline.config.tools.mcp_servers[name].enabled:
                state = next((row for row in states if row["name"] == name), None)
                if state is None or not state["connected"]:
                    raise RuntimeError(f"MCP server did not connect: {name}: {state}")
        if self.runtime.backend is not None:
            await self.runtime.backend.start()
            self.recorder.add("backend.started", implementation=type(self.runtime.backend).__name__)
        if self.baseline.resident:
            await self.runtime.loop.start_plugin_services()
            started = self.runtime.loop._started_services
            failed = [
                service
                for service in self.runtime.loop.plugin_services
                if not any(service is active for active in started)
            ]
            for service in failed:
                try:
                    await service.stop()
                except Exception as exc:
                    self.recorder.add("service.error", error=f"failed-start cleanup: {exc}")
            for (kind, name), value in self.components.items():
                if kind == "services" and any(value is service for service in failed):
                    raise RuntimeError(f"service did not start: {name}")
            self.recorder.add(
                "services.started", count=len(started), observers=len(self.runtime.loop.session_observers)
            )

    async def close(self):
        await self.runtime.dispose()
        self.recorder.add("runtime.closed")


def _bind_capability(
    baseline,
    artifact,
    effective,
    root,
    package,
    recorder,
    planning,
    strategies,
    hooks,
    *,
    state_root,
    infer,
    dependencies,
    peers,
    scope,
    preparation,
):
    """Assemble one candidate catalogue for all declared resource and interaction producers."""
    capability = None
    if strategies or "capability.strategy" in artifact.values or (planning and planning.config.tool):

        def resolve_interaction(operation):
            if operation == "planning.interact" and planning and planning.config.tool:
                return planning.tool()
            name = operation.split(".")[0]
            owner = strategies.get(name)
            if owner is None or not getattr(owner.config, "tool", None):
                raise ValueError(f"interaction is not provided by this candidate: {operation}")
            return owner.tool()

        catalog = CapabilityCatalog(
            fingerprint(artifact.model_dump(mode="json")),
            package,
            root,
            material_base=baseline.config.workspace_path,
            material_roots=(
                baseline.config.workspace_path / "uploads",
                baseline.config.workspace_path / "skills",
                *(Path(row.path) for row in effective.extensions.skill_forge.local_dirs),
            ),
            resolve_interaction=resolve_interaction,
            recorder=recorder,
        )
        configuration = (
            CapabilityBinding.model_validate(artifact.values["capability.strategy"])
            if "capability.strategy" in artifact.values
            else None
        )
        if configuration is not None and baseline.task is None:
            raise ValueError("a capability strategy requires a host task binding")
        capability = BoundCapability(
            configuration,
            baseline.task,
            state_root / "capability.json",
            package,
            recorder,
            catalog=catalog,
            infer=infer,
            plan=dependencies["plan"],
            scope=scope,
            host=preparation.host("capability"),
            peers=peers,
        )
        if configuration is not None:
            strategies["capability"] = capability
            hooks.append(capability.hook())
            capability.prepare_candidate(
                PreparationRequest(
                    harness_id=str(baseline.config.workspace_path),
                    revision=catalog.candidate,
                    task=baseline.task,
                    assets=artifact.files,
                    material_roots=tuple(str(path) for path in catalog.material_roots),
                )
            )
        if planning and planning.config.tool:
            capability.require(
                ToolContribution(name=planning.config.tool.name, owner="planning", interaction="planning.interact")
            )
        for name in ("memory", "action"):
            owner = strategies.get(name)
            if owner is not None and getattr(owner.config, "tool", None):
                operation = "interact" if name == "memory" else "handle_request"
                capability.require(
                    ToolContribution(name=owner.config.tool.name, owner=name, interaction=f"{name}.{operation}")
                )
    return capability


def _validate_bindings(artifact, declaration):
    for name, value in artifact.values.items():
        target = declaration.target(name)
        if target.binding not in {"memory.strategy", "planning.strategy", "capability.strategy", "action.strategy"}:
            raise ValueError(f"unsupported authoring entry: {name}; implement its owning strategy")
        target.parse(value)


def assemble(
    baseline: Baseline,
    artifact: Artifact,
    declaration: Declaration,
    root: Path,
    recorder: Recorder,
    provider_factory=None,
    planning_state: Path | None = None,
) -> Bound:
    """Construct a generation; callers own process isolation and start/stop."""
    _validate_bindings(artifact, declaration)
    root.mkdir(parents=True, exist_ok=True)
    package = write_package(root, artifact)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    prompts = {}
    effective = Baseline.restore(baseline.export())
    if effective.config.workspace_path != baseline.config.workspace_path:
        raise ValueError("the agent home is a host resource; a Harness change must preserve current task storage")
    preparation = Preparation(baseline, artifact, package, recorder)
    infer = Inference(None, recorder)
    peers = RuntimePeers(recorder)

    def prepare_owner(owner):
        owner.prepare_candidate(
            PreparationRequest(
                harness_id=str(baseline.config.workspace_path),
                revision=fingerprint(artifact.model_dump(mode="json")),
                task=baseline.task,
                assets=artifact.files,
                material_roots=(str(baseline.config.workspace_path / "uploads"),),
            )
        )

    def scope():
        return InteractionScope(
            harness_id=str(baseline.config.workspace_path),
            task_id=baseline.task.id if baseline.task else None,
            revision=fingerprint(artifact.model_dump(mode="json")),
            session_key=SESSION.get() or current_turn().conversation_id or None,
            turn_id=recorder.turn_id,
        )

    planning = None
    if TARGET in artifact.values:
        if baseline.task is None:
            raise ValueError("a planning strategy requires a host task binding")
        planning = BoundPlanning(
            PlanningBinding.model_validate(artifact.values[TARGET]),
            baseline.task,
            planning_state or root / "planning.json",
            package,
            recorder,
            infer=infer,
            peers=peers,
            host=preparation.host("planning"),
            scope=scope,
        )
        prepare_owner(planning)
    dependencies = {"plan": planning.read if planning else _no_plan}
    observer = LoopObserver(recorder)
    hooks = [observer]
    if planning:
        hooks.append(planning.hook())

    strategies = {}
    for name, implementation in (("memory", BoundMemory), ("action", BoundAction)):
        target_name = f"{name}.strategy"
        if target_name not in artifact.values:
            continue
        if baseline.task is None:
            raise ValueError(f"a {name} strategy requires a host task binding")
        strategy = implementation(
            declaration.target(target_name).parse(artifact.values[target_name]),
            baseline.task,
            (planning_state.parent if planning_state else root) / f"{name}.json",
            package,
            recorder,
            infer=infer,
            plan=dependencies["plan"],
            peers=peers,
            scope=scope,
            host=preparation.host(name),
        )
        from raven.agent.loop.turn_path import _SKIP_AFTER_SEND_ORIGINS, _SKIP_USER_INBOUND_ORIGINS

        if name == "memory":
            if strategy.config.intake and baseline.origin in _SKIP_USER_INBOUND_ORIGINS:
                raise ValueError("this origin does not reach Memory intake")
            if strategy.config.archive and baseline.origin in _SKIP_AFTER_SEND_ORIGINS:
                raise ValueError("this origin does not reach Memory archive")
        elif "input" in strategy.config.events and baseline.origin in _SKIP_USER_INBOUND_ORIGINS:
            raise ValueError("this origin does not reach Action input events")
        prepare_owner(strategy)
        strategies[name] = strategy
        if name != "action":
            hooks.append(strategy.hook())
    capability = _bind_capability(
        baseline,
        artifact,
        effective,
        root,
        package,
        recorder,
        planning,
        strategies,
        hooks,
        state_root=planning_state.parent if planning_state else root,
        infer=infer,
        dependencies=dependencies,
        peers=peers,
        scope=scope,
        preparation=preparation,
    )
    prepared = preparation.freeze()
    effective = native_settings(baseline, prepared)
    for server in effective.config.tools.mcp_servers.values():
        if server.command in artifact.files:
            server.command = str(package / server.command)
        server.args = [str(package / argument) if argument in artifact.files else argument for argument in server.args]
    plugin_root = _plugin(root, artifact, declaration, package, prepared)
    if plugin_root is not None:
        effective.extensions.plugins.dirs = [*effective.extensions.plugins.dirs, str(plugin_root)]
    effective.extensions.base = effective.config
    if capability:
        capability.stage_skills(root, effective.extensions)
    prompts.update(bind_prompts(artifact, package, references=prepared.prompts))
    provider = ObservedProvider((provider_factory or make_lazy_provider)(effective.config), recorder)
    router = None
    if baseline.hosting == "acp":
        from raven.core.provider_stack import build_model_routing

        router, provider = build_model_routing(effective.config, provider)
    infer.provider = provider
    action = strategies.get("action")
    if action is not None:
        hooks.append(action.hook())
        if action.config.dispatch:
            dependencies["action_gate"] = action.gate()
    peers.bind(planning=planning, memory=strategies.get("memory"), capability=capability, action=action)

    raw = {
        **effective.config.model_dump(mode="json", by_alias=True),
        **effective.extensions.model_dump(mode="json", by_alias=True, exclude={"base"}),
    }
    config_path = root / "config.json"
    config_path.write_text(json.dumps(raw, ensure_ascii=False))
    config_path.chmod(0o600)
    set_config_path(config_path)

    context_engine = None
    engine_factory = prepared.context_engine
    if engine_factory:
        context = PluginContext(
            config=effective.extensions.context.model_dump(),
            services=ServiceLocator(
                workspace=effective.config.workspace_path,
                user_id=effective.extensions.memory.user_id,
                agent_id=effective.extensions.memory.agent_id,
                provider=provider,
            ),
        )
        context_engine = load_factory(engine_factory, package)(context)
        for method in ("assemble", "after_turn", "set_provider"):
            if not callable(getattr(context_engine, method, None)):
                raise TypeError(f"context engine lacks {method}")
        if not hasattr(context_engine, "name") or not hasattr(context_engine, "owns_compaction"):
            raise TypeError("context engine lacks its native identity or compaction declaration")

    memory = strategies.get("memory")
    source_context = (
        SourceContext(
            context_engine,
            initialized=memory.initialize_context if memory else None,
        )
        if capability
        else None
    )
    if source_context is not None:
        context_engine = source_context

    if baseline.hosting == "acp":
        from raven.core.engine_stack import build_local_sessions

        from .hosting.lifecycle import local_host

        sessions, workdir = build_local_sessions(effective.config, workspace=None)
        host = local_host(effective.config)
        host.hooks = [*(host.hooks or ()), *hooks]
    else:
        sessions = SessionManager(effective.config.workspace_path)
        workdir = WorkdirResolver(
            WorkdirPolicy.LAUNCH_DIR,
            agent_home=effective.config.workspace_path,
            launch_dir=effective.workdir,
            sessions=sessions,
        )
        host = HostWiring(hooks=hooks)
    objects = {}
    runtime = None
    installation = ContentInstallation(effective.config.workspace_path, root, prepared, recorder)
    prepared = installation.prepared
    token = _ASSEMBLY.set((package, objects, recorder, dependencies))
    try:
        installation.apply()
        runtime = build_runtime(
            effective.config,
            effective.extensions,
            provider=provider,
            router=router,
            session_manager=sessions,
            provider_pool=ObservedPool(ProviderPool(effective.config), recorder),
            workdir_resolver=workdir,
            context_engine=context_engine,
            policy=TurnPolicy(
                max_iterations=effective.config.agents.defaults.max_tool_iterations,
                empty_recovery=limits_from_defaults(effective.config.agents.defaults),
                interactive=baseline.hosting == "acp",
            ),
            host=host,
        )
        if baseline.hosting == "acp":
            from raven.proactive_engine.schedulers.cron.tool import CronTool

            cron_tool = runtime.loop.tools.get("cron")
            if isinstance(cron_tool, CronTool):
                cron_tool.set_context("acp", "default")
        baseline_skills = bind_workspace_skills(runtime, root)
        if baseline.file_roots or baseline.read_roots or effective.config.tools.restrict_to_workspace:
            managed = (capability.catalog.skill_root,) if capability and capability.catalog.skill_root else ()
            _confine_files(runtime, baseline.file_roots, (*baseline.read_roots, baseline_skills, *managed))
        if source_context is not None:
            source_context.bind(runtime, effective.extensions)
            if memory is not None:
                memory.bind(runtime, source_context)
        if capability:
            capability.install(
                runtime,
                context=PluginContext(
                    config={},
                    services=ServiceLocator(
                        workspace=effective.config.workspace_path,
                        user_id=effective.extensions.memory.user_id,
                        agent_id=effective.extensions.memory.agent_id,
                        provider=provider,
                    ),
                ),
                disabled=effective.config.tools.disabled_tools,
            )
            if action is not None:
                action.bind(runtime)
            runtime.loop.harness = replace(
                runtime.loop.harness,
                action=ModelInput(runtime.loop.harness.action, capability, source_context, memory, action),
                memory=MemoryWindow(runtime.loop.harness.memory, memory, capability, runtime.loop)
                if memory is not None
                else runtime.loop.harness.memory,
            )
        if not baseline.allow_delegation:
            from .capability.leaf import bind_leaf

            bind_leaf(runtime)
        _verify_bindings(runtime, prepared, objects, effective.extensions.memory.backend)
        _verify_playbooks(runtime, prepared)
        recorder.add("runtime.bound", package=str(package), targets=list(artifact.values))
        return Bound(
            runtime,
            effective,
            artifact,
            recorder,
            observer,
            objects,
            runtime_sources(runtime, package, effective.extensions),
            planning,
            strategies,
            prompts,
            capability,
            source_context,
            infer,
            prepared,
            installation,
        )
    except BaseException:
        installation.rollback()
        if runtime is not None:
            runtime.loop.context.skills.stop_file_watcher()
        raise
    finally:
        _ASSEMBLY.reset(token)


def _verify_bindings(runtime, prepared, objects, backend_name):
    registry, loop = runtime.plugin_registry, runtime.loop
    for entry in prepared.components:
        kind, name = entry.kind, entry.name
        registered = getattr(
            registry,
            {
                "services": "service_names",
                "memory_backends": "memory_backend_names",
                "session_observers": "session_observer_names",
            }[kind],
        )()
        if name not in registered:
            raise ValueError(f"{entry.owner}: native component was not registered: {name}")
        if kind == "memory_backends":
            if name == backend_name and (runtime.backend is None or objects.get((kind, name)) is not runtime.backend):
                raise ValueError(f"selected memory backend was not bound: {name}")
            continue
        value = objects.get((kind, name))
        active = loop.plugin_services if kind == "services" else loop.session_observers
        if value is None or not any(value is item for item in active):
            raise ValueError(f"{entry.owner}: requested component was not bound: {name}")
    if prepared.extensions.get("memory", {}).get("backend") is not None and runtime.backend is None:
        raise ValueError("selected memory backend was not constructed")


def _confine_files(runtime, roots, read_roots=()):
    """Rebuild Raven's file tools: reads reach the agent home, the session's working directory, `roots` and
    `read_roots`; writes and edits reach the home, the working directory and `roots` only; delivering a file counts
    as reading it.

    A tool the configuration disabled stays absent. The shell is not rebuilt here: it follows the configuration's
    `restrict_to_workspace`.
    """
    loop = runtime.loop
    writable = (Path(loop.workspace).resolve(), *roots)
    readable = (*writable, *read_roots)
    reaches = {ReadFileTool: readable, ListDirTool: readable, GrepTool: readable, FindTool: readable}
    reaches |= {WriteFileTool: writable, EditFileTool: writable}
    for implementation, allowed in reaches.items():
        tool = implementation(workspace=loop.workspace, allowed_dirs=allowed)
        if loop.tools.get(tool.name) is not None:
            loop.tools.register(tool)
    if loop.tools.get("deliver_files") is not None and loop.deliverables is not None:
        loop.tools.register(DeliverFilesTool(loop.deliverables, workspace=loop.workspace, allowed_dirs=readable))


def _unloaded(library, name: str) -> str:
    """Why the library does not offer a playbook, in the loader's own words: Raven skips a playbook it cannot load
    or whose graph does not validate, and says so only in its log."""
    if library is None:
        return "the playbook library is not enabled"
    try:
        spec = library.store.load(name)
    except Exception as exc:  # noqa: BLE001 -- whatever the loader raised is the reason to report
        return f"{type(exc).__name__}: {exc}"
    known = getattr(library, "_known_agents", lambda: None)()
    errors = validate_structure(spec, known_agents=known, allow_blank_fillable=True)
    return "; ".join(errors) if errors else "it loads and validates now; check its node agents"


def _verify_playbooks(runtime, prepared):
    files = {name.removeprefix("playbooks/"): text for name, text in prepared.content.get("planning", {}).items()}
    if not files:
        return
    library = playbook_library(runtime.loop)
    loaded = set(library.names()) if library is not None else set()
    for name in files:
        parts = PurePosixPath(relative_path(name)).parts
        from ..composition.requirements import read_requirements, requirement_node

        if requirement_node(name):
            read_requirements(files[name])
            if (
                library is None
                or parts[0] not in loaded
                or parts[2] not in {node.id for node in library.store.load(parts[0]).nodes or ()}
            ):
                raise ValueError(f"requirements refer to a missing native playbook node: {name}")
        elif len(parts) != 2 or parts[1] != "playbook.md":
            raise ValueError(f"a playbook file must be <name>/playbook.md or a node requirements.json: {name}")
        if parts[0] not in loaded:
            raise ValueError(f"playbook was not loaded: {name}: {_unloaded(library, parts[0])}")
