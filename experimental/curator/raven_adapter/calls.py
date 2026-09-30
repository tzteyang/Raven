"""Load synchronous host translations while keeping decisions in strategies."""

import asyncio
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from inspect import iscoroutinefunction, signature
from uuid import uuid4

_OWNERS: ContextVar[tuple[str, ...]] = ContextVar("curator_operation_owners", default=())
_READ_ONLY: ContextVar[bool] = ContextVar("curator_read_only_operation", default=False)
_GROUPS: ContextVar[tuple] = ContextVar("curator_operation_groups", default=())


@dataclass
class Operation:
    """Host-owned identity and one inference allowance across a sequential peer chain."""

    id: str
    owner: str
    name: str
    source_id: str | None
    task: asyncio.Task
    active: bool = True
    inference_used: bool = False


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
    """Serialize a Harness's complete peer call chain to avoid cross-task lock cycles."""

    def __init__(self):
        self.lock = asyncio.Lock()

    @asynccontextmanager
    async def enter(self):
        active = _GROUPS.get()
        for group, task in active:
            if group is self:
                if task is not asyncio.current_task():
                    raise RuntimeError("parallel strategy requests within an ownership chain are unsupported")
                yield
                return
        async with self.lock:
            token = _GROUPS.set((*active, (self, asyncio.current_task())))
            try:
                yield
            finally:
                _GROUPS.reset(token)


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
