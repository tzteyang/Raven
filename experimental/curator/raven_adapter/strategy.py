"""Shared typed calls and checkpoints kept per session or per task; strategy behavior stays in its owner."""

import asyncio
import json
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import dataclass
from functools import wraps
from inspect import iscoroutinefunction, signature
from pathlib import Path
from typing import Any, TypeVar, get_args, get_type_hints

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from raven.permissions.turn import current_turn

from ..harness.declaration import parse_as, schema_for, typed
from ..harness.preparation import PreparationRequest
from .calls import OperationGroup, owner_operation
from .inference import strategy_factory
from .materialize import _write
from .observe import _copy_observation
from .targets import EntryPoint

SESSION: ContextVar[str | None] = ContextVar("curator_session", default=None)
"""The session (conversation) the current turn belongs to; the worker sets it around each turn it runs."""


class TaskBinding(BaseModel):
    """A generated owner constructed with explicit task identity and owned state."""

    model_config = ConfigDict(extra="forbid")

    model_config = ConfigDict(extra="forbid")

    factory: EntryPoint = Field(
        description="create(state: dict[str, JsonValue], task: Task) returns a concrete instance explicitly inheriting "
        "the selected public strategy protocol. Structural method matching alone is not accepted. "
        "Task is experimental.curator.harness.state.Task. Construct inert objects; bind dependencies explicitly. "
        "The mutable mapping is the sole adapter-managed checkpoint, preserved across turns and revisions; "
        "strategies receive one mapping per session (conversation); Memory may additionally declare "
        "keyword-only shared for task-wide information, kept separately from session working state. "
        "Initialize missing data without resetting progress; migrations are explicit. Private attributes and "
        "external side effects are not checkpointed. An optional keyword-only infer dependency is supplied "
        "by the host for a typed single-step worker-model judgment within an active strategy operation. "
        "It accepts instruction/data/output_type and shares one attempt across the peer chain. "
        "Deterministic factories need not accept it. Methods need concrete input and return annotations."
    )


def concrete(annotation):
    seen = set()

    def check(item):
        if item is Any or isinstance(item, TypeVar):
            raise TypeError("strategy method types must be concrete")
        if item in seen:
            return
        seen.add(item)
        for child in get_args(item):
            if isinstance(child, type) or get_args(child) or isinstance(child, TypeVar):
                check(child)
        if isinstance(item, type) and issubclass(item, BaseModel):
            for value in item.model_fields.values():
                check(value.annotation)

    check(annotation)
    schema_for(annotation)
    return annotation


def method_types(owner, operation, method, count):
    """Resolve concrete operation types with actionable authoring diagnostics."""
    try:
        annotations = get_type_hints(method, include_extras=True)
    except (NameError, TypeError) as exc:
        raise TypeError(f"{owner}.{operation} annotations could not be resolved: {exc}") from exc
    parameters = list(signature(method).parameters)[:count]
    missing = [name for name in (*parameters, "return") if name not in annotations]
    if missing:
        raise TypeError(f"{owner}.{operation} requires concrete annotations for: {', '.join(missing)}")
    return [concrete(annotations[name]) for name in parameters], concrete(annotations["return"])


@dataclass
class Scope:
    state: dict
    owner: Any
    resuming: bool


class Scopes:
    """One owner's JSON state per session, or one for the task, saved together in a single checkpoint file.

    Outside any session (binding, inspection, tests) the default scope is used. A session's scope is opened
    on first use with its own owner instance, so conversations never read or change each other's state.
    """

    def __init__(self, name, task, path: Path, open_owner, *, per_session: bool):
        self.task, self.path, self.open_owner, self.per_session = task, path, open_owner, per_session
        saved = json.loads(path.read_text()) if path.exists() else {"task_id": task.id, "data": {}}
        if saved["task_id"] != task.id:
            raise ValueError(f"{name} checkpoint belongs to another task")
        self.saved = dict(saved.get("sessions", {}))
        self.shared = parse_as(dict[str, JsonValue], saved.get("shared", {}), strict=True)
        if path.exists():
            self.saved[None] = saved["data"]
        self.open: dict[str | None, Scope] = {}

    def key(self) -> str | None:
        if not self.per_session:
            return None
        explicit = SESSION.get()
        return explicit if explicit is not None else current_turn().conversation_id or None

    def current(self) -> Scope:
        key = self.key()
        if key not in self.open:
            state = parse_as(dict[str, JsonValue], self.saved.get(key, {}), strict=True)
            self.open[key] = Scope(state, self.open_owner(state), key in self.saved)
        return self.open[key]

    def sessions(self) -> dict[str, dict]:
        return {key: deepcopy(scope.state) for key, scope in self.open.items() if key is not None} | {
            key: deepcopy(data) for key, data in self.saved.items() if key is not None and key not in self.open
        }

    def save(self):
        for key, scope in self.open.items():
            self.saved[key] = parse_as(dict[str, JsonValue], scope.state, strict=True)
        record = {"task_id": self.task.id, "data": self.saved.get(None, {})}
        if self.shared:
            record["shared"] = parse_as(dict[str, JsonValue], self.shared, strict=True)
        if sessions := {key: data for key, data in self.saved.items() if key is not None}:
            record["sessions"] = sessions
        content = json.dumps(record, sort_keys=True, ensure_ascii=False).encode()
        if not self.path.exists() or self.path.read_bytes() != content:
            _write(self.path, content)


class BoundStrategy:
    """Validate operations, detach arguments and checkpoint one strategy's state.

    This is a call boundary, not a scheduler or a dependency container. A failed
    operation restores only its owned JSON mapping; external effects cannot be
    rolled back. The live owner stays in place so installed delegates retain
    their identity. Concrete adapters select which operations are read-only.
    """

    def __init__(
        self,
        name,
        protocol,
        config,
        task,
        path: Path,
        package,
        recorder,
        *,
        optional=(),
        infer=None,
        plan=None,
        registrar=None,
        peers=None,
        shared_state=False,
        per_session=True,
        host=None,
        inherited=(),
    ):
        self.name, self.config, self.task, self.path = name, config, task, path
        self.recorder = recorder
        self.lock = asyncio.Lock()
        self.operations = peers.operations if peers is not None else OperationGroup()
        self.scopes = Scopes(
            name,
            task,
            path,
            lambda state: strategy_factory(
                config.factory,
                package,
                state,
                task,
                protocol=protocol,
                infer=infer,
                plan=plan,
                registrar=registrar,
                peers=peers,
                host=host,
                shared=self.scopes.shared if shared_state else None,
            ),
            per_session=per_session,
        )
        self.types = {}
        for operation in (*protocol.__abstractmethods__, *optional):
            expected = getattr(protocol, operation)
            method = getattr(self.strategy, operation, None)
            if not callable(method) or (
                operation not in inherited and getattr(type(self.strategy), operation, None) is expected
            ):
                raise TypeError(f"{name} strategy must implement {operation}")
            if iscoroutinefunction(method) != iscoroutinefunction(expected):
                raise TypeError(f"{name}.{operation} has the wrong sync/async form")
            count = len(signature(expected).parameters) - 1
            signature(method).bind(*[object() for _ in range(count)])
            self.types[operation] = method_types(name, operation, method, count)

    def bind_method(self, name, inputs, output):
        """Validate an enabled host extension on this same strategy owner."""
        from .calls import strategy_method

        method = strategy_method(self.strategy, name, len(inputs), asynchronous=True)
        annotations = get_type_hints(method)
        actual = ([annotations.get(key) for key in signature(method).parameters], annotations.get("return"))
        if actual != (inputs, output):
            raise TypeError(f"{self.name}.{name} has an incompatible host extension signature")
        self.types[name] = (inputs, output)

    @property
    def state(self) -> dict:
        return self.scopes.current().state

    @property
    def strategy(self):
        return self.scopes.current().owner

    def restore(self, state, shared=None):
        self.state.clear()
        self.state.update(deepcopy(state))
        if shared is not None:
            self.scopes.shared.clear()
            self.scopes.shared.update(deepcopy(shared))

    def save(self):
        self.scopes.save()

    async def prepare(self):
        self.save()

    def prepare_candidate(self, request: PreparationRequest):
        """Run code-owned setup before native construction, without changing checkpoints."""
        method = self.strategy.prepare
        if iscoroutinefunction(method):
            raise TypeError(f"{self.name}.prepare must be synchronous")
        annotations = get_type_hints(method)
        parameters = list(signature(method).parameters)
        if (
            len(parameters) != 1
            or annotations.get(parameters[0]) is not PreparationRequest
            or annotations.get("return") is not type(None)
        ):
            raise TypeError(f"{self.name}.prepare must accept PreparationRequest and return None")
        self.recorder.add(f"{self.name}.preparation", status="started", revision=request.revision)
        self.translate("prepare", method, request, output=type(None))
        self.recorder.add(f"{self.name}.preparation", status="completed", revision=request.revision)

    def translate(self, operation, function, *args, output=None):
        before = deepcopy(self.state)
        shared = deepcopy(self.scopes.shared)
        try:
            result = function(*(_copy_observation(value) for value in args))
            if self.state != before or self.scopes.shared != shared:
                raise ValueError("translations must not mutate strategy state")
            return typed(output, result) if output is not None else result
        except BaseException as exc:
            self.restore(before, shared)
            self.recorder.add(
                f"{self.name}.error",
                operation=operation,
                arguments=args,
                state=before,
                error=f"{type(exc).__name__}: {exc}",
            )
            raise

    async def call(self, operation, *args, source, readonly=False, validate=None, source_id=None):
        async with owner_operation(
            self.name, self.lock, group=self.operations, readonly=readonly, operation=operation, source_id=source_id
        ):
            before = deepcopy(self.state)
            shared = deepcopy(self.scopes.shared)
            self.recorder.add(f"{self.name}.call", operation=operation, source=source, arguments=args)
            try:
                inputs, output = self.types[operation]
                values = [typed(annotation, value) for annotation, value in zip(inputs, args, strict=True)]
                result = typed(output, await getattr(self.strategy, operation)(*values))
                if validate is not None:
                    validate(result)
                if readonly and (self.state != before or self.scopes.shared != shared):
                    raise ValueError(f"read-only {self.name}.{operation} changed retained state")
                self.save()
            except BaseException as exc:
                self.restore(before, shared)
                self.recorder.add(
                    f"{self.name}.error",
                    operation=operation,
                    source=source,
                    arguments=args,
                    state=before,
                    error=f"{type(exc).__name__}: {exc}",
                )
                raise
            self.recorder.add(f"{self.name}.result", operation=operation, source=source, result=result)
            return result

    def callback(self, function):
        @wraps(function)
        async def observed(*args, **kwargs):
            try:
                result = await function(*args, **kwargs)
                self.recorder.add(
                    f"{self.name}.callback",
                    operation=function.__name__,
                    phase=getattr(args[-1], "phase", None),
                    result=result,
                )
                return result
            except Exception as exc:
                self.recorder.add(
                    f"{self.name}.error", operation=function.__name__, error=f"{type(exc).__name__}: {exc}"
                )
                raise

        return observed

    def facts(self):
        return {
            "task_id": self.task.id,
            "state": deepcopy(self.state),
            "shared": deepcopy(self.scopes.shared),
            "sessions": self.scopes.sessions(),
            "binding": self.config.model_dump(mode="json"),
            "methods": {
                name: {"inputs": [schema_for(t) for t in inputs], "output": schema_for(output)}
                for name, (inputs, output) in self.types.items()
            },
        }
