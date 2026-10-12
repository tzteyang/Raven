"""Load synchronous host translations while keeping decisions in strategies."""

import asyncio
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps
from inspect import iscoroutinefunction, signature
from uuid import uuid4

from experimental.harness.raven_adapter.checkpoints import Checkpoints

_OWNERS: ContextVar[tuple[str, ...]] = ContextVar("curator_operation_owners", default=())
_READ_ONLY: ContextVar[bool] = ContextVar("curator_read_only_operation", default=False)
_GROUPS: ContextVar[tuple] = ContextVar("curator_operation_groups", default=())


@dataclass
class Operation:
    """Host-owned identity and the inference allowance a sequential peer chain shares: the calls it made and when
    the first one started."""

    id: str
    owner: str
    name: str
    source_id: str | None
    task: asyncio.Task
    active: bool = True
    inference_calls: int = 0
    inference_started: float | None = None


_OPERATION: ContextVar[Operation | None] = ContextVar("curator_strategy_operation", default=None)


def current_operation() -> Operation:
    current = _OPERATION.get()
    if current is None or not current.active or current.task is not asyncio.current_task():
        raise RuntimeError("inference requires the current host strategy operation")
    return current


@contextmanager
def operation_scope(owner, name, source_id):
    if _OPERATION.get() is not None:
        yield current_operation()
        return
    current = Operation(uuid4().hex, owner, name, source_id, asyncio.current_task())
    token = _OPERATION.set(current)
    try:
        yield current
    finally:
        current.active = False
        _OPERATION.reset(token)


class OperationGroup:
    """Serialize and atomically checkpoint one Harness's complete peer call chain."""

    def __init__(self):
        self.lock = asyncio.Lock()
        self.owners = []
        self.checkpoints = None
        self.snapshots = None
        self.task = None
        self.failure = None

    def storage(self, path, task_id):
        if self.checkpoints is None:
            self.checkpoints = Checkpoints(path.parent, task_id)
        if self.checkpoints.path.parent != path.parent or self.checkpoints.task_id != task_id:
            raise ValueError("peer strategies must share one Harness checkpoint directory and task")
        return self.checkpoints

    def save(self):
        if self.checkpoints is not None:
            self.checkpoints.save({owner.scopes.name: owner.scopes.record() for owner in self.owners})

    def visible(self, owner, name):
        if self.snapshots is not None and self.task is not asyncio.current_task():
            return self.snapshots[owner][name]
        return getattr(owner, name)

    @asynccontextmanager
    async def enter(self):
        active = _GROUPS.get()
        for group, task in active:
            if group is self:
                if task is not asyncio.current_task():
                    raise RuntimeError("parallel strategy requests within an ownership chain are unsupported")
                if self.failure is not None:
                    raise RuntimeError("a failed strategy operation invalidated the peer chain") from self.failure
                try:
                    yield
                except BaseException as exc:
                    self.failure = exc
                    raise
                return
        async with self.lock:
            token = _GROUPS.set((*active, (self, asyncio.current_task())))
            self.task = asyncio.current_task()
            try:
                self.snapshots = {owner: owner.snapshot() for owner in self.owners}
                yield
                if self.failure is not None:
                    raise RuntimeError("a failed strategy operation invalidated the peer chain") from self.failure
                self.save()
            except BaseException:
                for owner, snapshot in reversed((self.snapshots or {}).items()):
                    owner.restore_snapshot(snapshot)
                raise
            finally:
                self.snapshots = None
                self.task = None
                self.failure = None
                _GROUPS.reset(token)


def transactional(function):
    @wraps(function)
    async def wrapped(self, *args, **kwargs):
        async with self.operations.enter():
            return await function(self, *args, **kwargs)

    return wrapped


def require_writable():
    if _READ_ONLY.get():
        raise ValueError("a read-only strategy operation cannot request state changes")


def interaction_mode(mode):
    """Keep query constraints across peers even if a nested caller requests writes."""
    if mode not in ("query", "command"):
        raise ValueError("interaction mode must be query or command")
    return "query" if _READ_ONLY.get() else mode


@contextmanager
def read_only_operation(enabled=True):
    token = _READ_ONLY.set(_READ_ONLY.get() or enabled)
    try:
        yield
    finally:
        _READ_ONLY.reset(token)


@asynccontextmanager
async def owner_operation(name, lock, *, group, readonly=False, operation="operation", source_id=None):
    """Reject an awaited ownership cycle before trying to acquire its lock."""
    path = _OWNERS.get()
    if name in path:
        raise RuntimeError(f"cyclic strategy operation: {' -> '.join((*path, name))}")
    token = _OWNERS.set((*path, name))
    try:
        if not readonly:
            require_writable()
        with read_only_operation(readonly):
            async with group.enter():
                async with lock:
                    with operation_scope(name, operation, source_id):
                        yield
    finally:
        _OWNERS.reset(token)


def strategy_method(owner, name, count, *, asynchronous=False):
    """Resolve a selected protected method on the current live strategy owner."""
    method = getattr(owner, name, None)
    if not callable(method) or iscoroutinefunction(method) != asynchronous:
        form = "async" if asynchronous else "synchronous"
        raise TypeError(f"strategy must implement {form} {name}")
    signature(method).bind(*[object() for _ in range(count)])
    return method
