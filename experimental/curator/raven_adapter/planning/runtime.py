"""Bind typed planning interactions, session projections and ordered native callbacks."""

import asyncio
from copy import deepcopy
from inspect import iscoroutinefunction, signature
from typing import get_type_hints
from uuid import uuid4

from raven.agent.hook.participant import ParticipantHook
from raven.contracts.loop_hooks import HookDecision
from raven.contracts.participant import AgentParticipant, Intake

from ...harness.declaration import schema_for, typed
from ...harness.interaction import InteractionRequest, InteractionScope
from ...harness.planning import PlanningInitialization, PlanningProjection, PlanningResult
from ...harness.preparation import PreparationRequest
from ...harness.strategies import PlanningStrategy
from ..calls import OperationGroup, interaction_mode, owner_operation, read_only_operation, strategy_method
from ..inference import strategy_factory
from ..inspection import fingerprint
from ..interaction_tools import interaction_tool
from ..observe import plain
from ..strategy import Scopes, concrete, method_types
from .contracts import PlanningObservation


class BoundPlanning:
    """One state owner per session, publishing projections only after valid checkpoints."""

    def __init__(self, config, task, path, package, recorder, *, infer=None, peers=None, host=None, scope=None):
        self.config, self.task, self.path, self.recorder = config, task, path, recorder
        self.lock = asyncio.Lock()
        self.operations = peers.operations if peers is not None else OperationGroup()
        self.projections = {}
        self.initialized = set()
        self.latest_projection = None
        self.factory = lambda state: strategy_factory(
            config.factory,
            package,
            state,
            protocol=PlanningStrategy,
            infer=infer,
            plan=self.read,
            peers=peers,
            host=host,
        )
        self.scopes = Scopes("planning", task, path, self.factory, per_session=True)
        self.scope = scope or (
            lambda: InteractionScope(
                harness_id=str(path.parent),
                task_id=task.id,
                revision=package.name,
                session_key=self.scopes.key(),
                turn_id=recorder.turn_id,
            )
        )
        annotations = {}
        for name in ("initialize", "interact"):
            method = getattr(self.strategy, name, None)
            if not iscoroutinefunction(method) or getattr(type(self.strategy), name, None) is getattr(
                PlanningStrategy, name
            ):
                raise TypeError(f"planning strategy must implement async {name}")
            signature(method).bind(object())
            inputs, output = method_types("planning", name, method, 1)
            annotations[name] = (inputs[0], output)
        initial, self.initial_projection_type = annotations["initialize"]
        self.request_type, self.result_type = annotations["interact"]
        if initial is not PlanningInitialization:
            raise TypeError("planning initialize must accept PlanningInitialization")
        for value, expected in (
            (self.initial_projection_type, PlanningProjection),
            (self.request_type, InteractionRequest),
            (self.result_type, PlanningResult),
        ):
            if not isinstance(value, type) or not issubclass(value, expected):
                raise TypeError(f"planning requires a concrete {expected.__name__}")
        result_projection = self.result_type.model_fields["projection"].annotation
        for projection in (self.initial_projection_type, result_projection):
            if not isinstance(projection, type) or not issubclass(projection, PlanningProjection):
                raise TypeError("planning results must contain a concrete PlanningProjection")
            if set(projection.model_fields) != {"view", "guidance"} or projection.model_computed_fields:
                raise TypeError("planning projections contain only view and guidance; put domain fields in ViewT")
        self.view_type = concrete(self.initial_projection_type.model_fields["view"].annotation)
        if result_projection.model_fields["view"].annotation != self.view_type:
            raise TypeError("planning initialization and interactions must use the same view type")
        self.projection_type = PlanningProjection[self.view_type]
        self.command_type = concrete(self.request_type.model_fields["command"].annotation)
        self.reply_type = concrete(self.result_type.model_fields["reply"].annotation)
        if config.observe:
            strategy_method(self.strategy, "_observe", 2)

    @property
    def state(self):
        return self.scopes.current().state

    @property
    def strategy(self):
        return self.scopes.current().owner

    @property
    def current_view(self):
        return plain(deepcopy(self.latest_projection.view)) if self.latest_projection is not None else None

    def _restore(self, before):
        scope = self.scopes.current()
        scope.state.clear()
        scope.state.update(before)
        scope.owner = self.factory(scope.state)
        self.initialized.discard(self.scopes.key())

    def _translate(self, operation, function, *args, output):
        before = deepcopy(self.state)
        try:
            with read_only_operation():
                result = function(*(deepcopy(value) for value in args))
            if self.state != before:
                raise ValueError("planning translations must not mutate state")
            return typed(output, result)
        except BaseException as exc:
            self._restore(before)
            self.recorder.add(
                "planning.error",
                operation=operation,
                arguments=args,
                state=before,
                error=f"{type(exc).__name__}: {exc}",
            )
            raise

    def prepare_candidate(self, request: PreparationRequest):
        method = self.strategy.prepare
        parameters = list(signature(method).parameters)
        hints = get_type_hints(method)
        if (
            iscoroutinefunction(method)
            or len(parameters) != 1
            or hints.get(parameters[0]) is not PreparationRequest
            or hints.get("return") is not type(None)
        ):
            raise TypeError("planning.prepare must accept PreparationRequest and return None synchronously")
        self.recorder.add("planning.preparation", status="started", revision=request.revision)
        self._translate("prepare", method, request, output=type(None))
        self.recorder.add("planning.preparation", status="completed", revision=request.revision)

    def _publish(self, projection, source_id=None):
        self.projections[self.scopes.key()] = deepcopy(projection)
        self.latest_projection = deepcopy(projection)
        self.recorder.add("planning.projection", scope=self.scope(), source_id=source_id, projection=projection)

    def _projection(self, value):
        return self.projection_type(view=deepcopy(value.view), guidance=value.guidance)

    async def prepare(self):
        if self.scopes.key() in self.initialized:
            return
        async with owner_operation("planning", self.lock, group=self.operations, operation="initialize"):
            if self.scopes.key() in self.initialized:
                return
            scope = self.scopes.current()
            before = deepcopy(self.state)
            initial = PlanningInitialization(scope=self.scope(), task=self.task.text, restored=scope.resuming)
            self.recorder.add("planning.call", operation="initialize", source="task", arguments=[initial])
            try:
                with read_only_operation(scope.resuming):
                    projection = self._projection(
                        typed(self.initial_projection_type, await self.strategy.initialize(initial))
                    )
                if projection.view is None:
                    raise ValueError("a planning view cannot be None")
                if scope.resuming and self.state != before:
                    raise ValueError("planning initialize changed existing state")
                self.scopes.save()
            except BaseException as exc:
                self._restore(before)
                self.recorder.add(
                    "planning.error",
                    operation="initialize",
                    source="task",
                    arguments=[initial],
                    state=before,
                    error=f"{type(exc).__name__}: {exc}",
                )
                raise
            scope.resuming = True
            self.initialized.add(self.scopes.key())
            self._publish(projection)
            self.recorder.add("planning.result", operation="initialize", source="task", result=projection)

    def read(self):
        projection = self.projections.get(self.scopes.key())
        return plain(deepcopy(projection.view)) if projection is not None else None

    async def interact(self, command, *, origin="agent", mode="command", request_id=None):
        if origin == "agent" and self.config.tool is None:
            raise ValueError("planning has no selected Agent interaction")
        if origin == "strategy" and not (self.config.requests or self.config.tool):
            raise ValueError("planning has no selected peer interaction")
        mode = interaction_mode(mode)
        request = self.request_type(
            scope=self.scope(),
            request_id=request_id or uuid4().hex,
            origin=origin,
            mode=mode,
            command=typed(self.command_type, command),
        )
        await self.prepare()
        async with owner_operation(
            "planning",
            self.lock,
            group=self.operations,
            readonly=mode == "query",
            operation="interact",
            source_id=request.request_id,
        ):
            before = deepcopy(self.state)
            projection = deepcopy(self.projections[self.scopes.key()])
            self.recorder.add("planning.call", operation="interact", source=origin, arguments=[request])
            try:
                result = typed(self.result_type, await self.strategy.interact(request))
                published = self._projection(result.projection)
                if published.view is None:
                    raise ValueError("a planning view cannot be None")
                if mode == "query" and (self.state != before or plain(published) != plain(projection)):
                    raise ValueError("planning query changed retained state or the published projection")
                if mode == "command":
                    self.scopes.save()
            except BaseException as exc:
                self._restore(before)
                self.recorder.add(
                    "planning.error",
                    operation="interact",
                    source=origin,
                    arguments=[request],
                    state=before,
                    error=f"{type(exc).__name__}: {exc}",
                )
                raise
            if mode == "command":
                self._publish(published, request.request_id)
            self.recorder.add("planning.result", operation="interact", source=origin, result=result)
            return result

    async def tool_call(self, command, *, mode="command"):
        return (await self.interact(command, mode=mode)).reply

    def tool(self):
        if self.config.tool is None:
            raise ValueError("planning has no selected model interaction")
        return interaction_tool(self.config.tool, self.command_type, self.tool_call, modes=True)

    async def addendum(self):
        if not self.config.context:
            return None
        await self.prepare()
        content = self.projections[self.scopes.key()].guidance
        self.recorder.add("planning.context", scope=self.scope(), content=content)
        return content

    async def observe(self, observation):
        if observation.phase not in self.config.observe:
            return
        await self.prepare()
        async with self.operations.enter():
            async with owner_operation(
                "planning", self.lock, group=self.operations, operation="observe", source_id=observation.event_id
            ):
                view = self.projections[self.scopes.key()].view
                self.recorder.add("planning.observation", observation=observation)
                command = self._translate(
                    "observe",
                    strategy_method(self.strategy, "_observe", 2),
                    view,
                    observation,
                    output=self.command_type | None,
                )
            if command is not None:
                await self.interact(command, origin="observation", request_id=observation.event_id)

    async def observe_step(self, step, phase):
        if phase not in self.config.observe:
            return
        data = dict(
            scope=self.scope(),
            phase=phase,
            iteration=step.iteration,
            messages=plain(step.transcript[step.turn_base :]),
            response=plain(step.response),
            tools=plain(step.tools),
        )
        await self.observe(PlanningObservation(event_id=fingerprint(plain(data)), **data))

    def hook(self):
        owner = self

        class PlanningParticipant(AgentParticipant):
            async def system_addendum(self, step):
                content = await owner.addendum()
                return Intake(content) if content is not None else None

        class PlanningHook(ParticipantHook):
            async def _observe_phase(self, ctx, phase):
                try:
                    await owner.prepare()
                    await owner.observe_step(self._step(ctx, phase=phase), phase)
                except Exception as exc:
                    owner.recorder.add("planning.error", operation=phase, error=f"{type(exc).__name__}: {exc}")
                    return HookDecision(
                        short_circuit_result="The task could not continue because its planning update failed."
                    )
                return None

            async def before_iteration(self, ctx):
                failure = await self._observe_phase(ctx, "before_model")
                return failure if failure is not None else await super().before_iteration(ctx)

            async def after_iteration(self, ctx):
                failure = await self._observe_phase(ctx, "after_iteration")
                return failure if failure is not None else await super().after_iteration(ctx)

        return PlanningHook("curator-planning", PlanningParticipant, rolls_back=False)

    def facts(self):
        projection = self.latest_projection
        return dict(
            task_id=self.task.id,
            view=self.current_view,
            projection=plain(projection),
            state=deepcopy(self.state),
            sessions=self.scopes.sessions(),
            view_schema=schema_for(self.view_type),
            command_schema=schema_for(self.command_type),
            reply_schema=schema_for(self.reply_type),
            binding=self.config.model_dump(mode="json"),
        )
