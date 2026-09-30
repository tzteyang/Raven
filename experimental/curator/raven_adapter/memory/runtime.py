"""Bind Memory initialization, information operations and each actual model input."""

from copy import deepcopy
from uuid import uuid4

from pydantic import JsonValue

from raven.agent.hook.participant import ParticipantHook
from raven.contracts.participant import AgentParticipant, Intake
from raven.utils.tokens import estimate_prompt_tokens

from ...harness.context import CompactionRequest, ContextRequest, ContextView, InitialContext
from ...harness.declaration import typed
from ...harness.interaction import InteractionRequest, InteractionScope
from ...harness.strategies import MemoryStrategy
from ..calls import interaction_mode, strategy_method
from ..context_sources import message_text
from ..inspection import fingerprint
from ..interaction_tools import interaction_tool
from ..observe import plain
from ..strategy import SESSION, BoundStrategy, concrete
from .context import ProjectionOverflowError, protected_positions, validate_projection
from .contracts import MemoryArchive, MemoryInput, MemoryObservation


class BoundMemory(BoundStrategy):
    """Use session owners with an explicit task-wide knowledge mapping.

    Tool callbacks route through this wrapper at invocation. compose/compact
    cannot mutate either checkpoint. Initialization uses an actual source
    snapshot once per active owner, after resources and the session are known.
    """

    def __init__(
        self, config, task, path, package, recorder, *, infer=None, plan=None, peers=None, scope=None, host=None
    ):
        operations = []
        if config.tool or config.observe or config.requests:
            operations.append("interact")
        if config.compact:
            operations.append("compact")
        super().__init__(
            "memory",
            MemoryStrategy,
            config,
            task,
            path,
            package,
            recorder,
            optional=tuple(operations),
            infer=infer,
            plan=plan,
            peers=peers,
            shared_state=True,
            host=host,
        )
        self.scope = scope or (
            lambda: InteractionScope(
                harness_id=str(path.parent),
                task_id=task.id,
                revision=package.name,
                session_key=SESSION.get(),
                turn_id=recorder.turn_id,
            )
        )
        if self.types["initialize"][0] != [InitialContext]:
            raise TypeError("memory initialize must accept InitialContext")
        if self.types["compose"] != ([ContextRequest], ContextView):
            raise TypeError("memory compose must accept ContextRequest and return ContextView")
        if config.compact and self.types["compact"] != ([CompactionRequest], ContextView):
            raise TypeError("memory compact must accept CompactionRequest and return ContextView")
        self.request_type, self.command_type = None, None
        if operations and "interact" in operations:
            request_type = self.types["interact"][0][0]
            if not isinstance(request_type, type) or not issubclass(request_type, InteractionRequest):
                raise TypeError("memory interact must accept InteractionRequest with a concrete command type")
            self.request_type = request_type
            self.command_type = concrete(request_type.model_fields["command"].annotation)
        if config.observe:
            strategy_method(self.strategy, "_observe", 1)
        if config.intake:
            self.bind_method("_intake", [MemoryInput], str | None)
        if config.archive:
            self.bind_method("_archive", [MemoryArchive], dict[str, JsonValue] | None)
        self.plan = plan
        self.initialized = {}
        self.runtime = None
        self.context_sources = None

    @property
    def observe(self):
        return strategy_method(self.strategy, "_observe", 1) if self.config.observe else None

    def bind(self, runtime, sources):
        self.runtime, self.context_sources = runtime, sources
        if self.config.require_sources and not sources.structured:
            raise ValueError("memory initialization requires a source-aware context engine")

    async def initialize_context(self, session_key, frame):
        if self.config.require_sources and not frame.structured:
            raise ValueError("memory initialization requires actual context sources")
        token = SESSION.set(session_key)
        try:
            if self.scopes.key() not in self.initialized:
                scope = self.scopes.current()
                initial = InitialContext(
                    scope=self.scope(),
                    task=self.task.text,
                    sources=frame.sources,
                    messages=frame.messages,
                    history=frame.history,
                    restored=scope.resuming,
                )
                value = await self.call("initialize", initial, source="assembly")
                self.initialized[self.scopes.key()] = deepcopy(value)
                scope.resuming = True
        finally:
            SESSION.reset(token)

    async def interact(self, command, *, origin="agent", request_id=None, mode="command"):
        if self.request_type is None:
            raise ValueError("memory interaction was not selected")
        if self.scopes.key() not in self.initialized:
            raise RuntimeError("memory interaction requires initialized context for this session")
        request = self.request_type(
            scope=self.scope(),
            request_id=request_id or uuid4().hex,
            origin=origin,
            mode=interaction_mode(mode),
            command=typed(self.command_type, command),
        )
        return await self.call(
            "interact", request, source=origin, readonly=request.mode == "query", source_id=request.request_id
        )

    def _request(self, messages, frame, sources, capabilities, *, pressure=None):
        if self.scopes.key() not in self.initialized:
            raise RuntimeError("context composition requires initialized Memory")
        baseline = frame.messages
        if (
            pressure is None
            and capabilities is not None
            and not capabilities.native_skills
            and self.context_sources is not None
        ):
            baseline = self.context_sources.strip_native_skills(baseline, frame)
        anchor = next((message_text(row) for row in reversed(baseline) if row.get("role") == "user"), "")
        start = next(
            (
                index
                for index, row in enumerate(messages)
                if row.get("role") == "user" and anchor and message_text(row).startswith(anchor)
            ),
            None,
        )
        if start is None:
            raise ValueError("memory cannot identify the current turn's protected user input")
        required = {index for index in range(start, len(messages)) if messages[index].get("role") == "user"}
        if messages:
            required.add(len(messages) - 1)
        budget = self.runtime.loop.harness.memory.token_budget() if self.runtime else frame.budget
        tools = (
            capabilities.tools
            if pressure is None and capabilities is not None
            else self.runtime.loop.tools.get_definitions()
        )
        allowance = max(0, budget.context_length - budget.reserved_output - estimate_prompt_tokens([], tools))
        request_type = CompactionRequest if pressure is not None else ContextRequest
        return request_type(
            scope=self.scope(),
            messages=plain(messages),
            budget=allowance,
            required=tuple(sorted(required)),
            turn_start=start,
            sources=sources,
            history=frame.history,
            initialization=plain(self.initialized[self.scopes.key()]),
            capabilities=capabilities,
            plan=self.plan() if self.plan else None,
            **({"pressure": pressure} if pressure is not None else {}),
        )

    async def project(self, messages, frame, sources, capabilities):
        request = self._request(messages, frame, sources, capabilities)
        result = await self.call("compose", request, source="model_input", readonly=True)
        validate_projection(request, result)
        if estimate_prompt_tokens(result.messages) > request.budget:
            if "projection" not in self.config.compact:
                raise ProjectionOverflowError(estimate_prompt_tokens(result.messages), request.budget)
            protected = [request.messages[index] for index in request.required]
            compact = CompactionRequest(
                **{
                    **request.model_dump(),
                    "messages": result.messages,
                    "required": tuple(protected_positions(result.messages, protected)),
                    "turn_start": protected_positions(result.messages, [request.messages[request.turn_start]])[0],
                },
                pressure="projection",
            )
            result = await self.call("compact", compact, source="projection", readonly=True)
            validate_projection(request, result)
        size = estimate_prompt_tokens(result.messages)
        if size > request.budget:
            raise ProjectionOverflowError(size, request.budget)
        self.recorder.add(
            "memory.context",
            scope=request.scope,
            estimated_tokens=size,
            allowance=request.budget,
            sources=[source.name for source in sources],
            capabilities=capabilities,
        )
        return result.messages

    async def compact_window(self, messages, capabilities, pressure):
        frame = self.context_sources.frame(self.scope().session_key)
        sources = self.context_sources.projection_sources(messages, frame, native_skills=True)
        request = self._request(messages, frame, sources, capabilities, pressure=pressure)
        result = await self.call(
            "compact",
            request,
            source=pressure,
            readonly=True,
            validate=lambda value: validate_projection(request, value),
        )
        before, after = estimate_prompt_tokens(messages), estimate_prompt_tokens(result.messages)
        if after >= before or after > request.budget:
            raise ValueError("memory compaction did not reduce the window within its allowance")
        return result.messages

    def tool(self):
        if self.config.tool is None or self.command_type is None:
            raise ValueError("memory has no selected model interaction")
        return interaction_tool(self.config.tool, self.command_type, self.interact, modes=True)

    def hook(self):
        owner = self

        class MemoryParticipant(AgentParticipant):
            @owner.callback
            async def intake(self, text, step):
                if not owner.config.intake:
                    return None
                value = await owner.call(
                    "_intake",
                    MemoryInput(scope=owner.scope(), text=text),
                    source="user_inbound",
                )
                return Intake(value) if value is not None else None

            @owner.callback
            async def archive(self, step, reply):
                if not owner.config.archive:
                    return None
                return await owner.call(
                    "_archive",
                    MemoryArchive(
                        scope=owner.scope(),
                        reply=reply,
                        messages=plain(step.transcript[step.turn_base :]),
                    ),
                    source="sent",
                )

            @owner.callback
            async def advise(self, step):
                if step.phase != "after_iteration" or owner.observe is None:
                    return None
                messages = plain(step.transcript[step.turn_base :])
                proposal = plain(step.response)
                identity = fingerprint(
                    {
                        "scope": plain(owner.scope()),
                        "iteration": step.iteration,
                        "messages": messages,
                        "proposal": proposal,
                    }
                )
                observation = MemoryObservation(
                    scope=owner.scope(),
                    event_id=identity,
                    iteration=step.iteration,
                    messages=messages,
                    proposal=proposal,
                )
                command = owner.translate("observe", owner.observe, observation, output=owner.command_type | None)
                if command is not None:
                    await owner.interact(command, origin="observation", request_id=identity)
                return None

        return ParticipantHook("curator-memory", MemoryParticipant, rolls_back=False)

    def facts(self):
        return {
            **super().facts(),
            "initialized": {str(key): plain(value) for key, value in self.initialized.items()},
        }
