"""Task-local execution scopes and durable request attempts, enabled by an experimental run."""

from __future__ import annotations

import asyncio
import contextlib
import functools
import inspect
import os
import time
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from raven.observability.ledger import FILENAME, Ledger, LedgerError
from raven.observability.provider_usage import summarize
from raven.providers.usage import merge_usage


@dataclass(frozen=True)
class Context:
    ledger: Ledger
    run_id: str
    parent_id: str | None = None
    attributes: tuple = ()


_current: ContextVar[Context | None] = ContextVar("execution_context", default=None)


def current() -> Context | None:
    return _current.get()


def carrier() -> dict | None:
    context = current()
    if context is None:
        return None
    return {"run_id": context.run_id, "parent_id": context.parent_id, "attributes": dict(context.attributes)}


@contextlib.contextmanager
def bind(context):
    token = _current.set(context)
    try:
        yield
    finally:
        _current.reset(token)


@contextlib.contextmanager
def receive(payload, directory):
    """Restore identity into a receiver-owned shard; a carrier never chooses a file path."""
    context = None
    if isinstance(payload, dict) and isinstance(payload.get("run_id"), str) and payload["run_id"]:
        attributes = payload.get("attributes")
        attributes = attributes if isinstance(attributes, dict) else {}
        context = Context(
            Ledger(Path(directory) / FILENAME), payload["run_id"], payload.get("parent_id"), tuple(attributes.items())
        )
    with bind(context):
        yield


def _now():
    return datetime.now(timezone.utc).isoformat()


class Record:
    """A monotonic snapshot sequence with a durable start before any external work."""

    def __init__(self, context, name, kind, attributes):
        self.context, self.started = context, time.monotonic()
        self.row = {
            "schema_version": 1,
            "id": uuid4().hex,
            "version": 0,
            "run_id": context.run_id,
            "parent_id": context.parent_id,
            "kind": kind,
            "name": name,
            "pid": os.getpid(),
            "started_at": _now(),
            "ended_at": None,
            "duration_ms": None,
            "status": "running",
            "attributes": {**dict(context.attributes), **attributes},
        }
        self.normalized = {}
        if kind != "span":
            self.row.update(raw_usage={}, usage=summarize({}), usage_complete=False)
        self.closed = False
        self.save()

    def save(self):
        self.row["version"] += 1
        self.context.ledger.put(self.row)

    def usage(self, usage, *, raw=None, response_id=None, served_model=None, complete=False):
        if usage:
            self.normalized = merge_usage(self.normalized, usage)
        changes = dict(
            raw_usage=merge_usage(
                self.row.get("raw_usage"), raw if isinstance(raw, dict) else usage or {}, preserve_nulls=True
            ),
            usage=summarize(self.normalized),
            usage_complete=(
                complete
                and any(
                    value is not None for key, value in self.normalized.items() if key != "prompt_tokens_include_cache"
                )
            )
            or self.row.get("usage_complete", False),
        )
        if response_id:
            changes["response_id"] = response_id
        if served_model:
            changes["served_model"] = served_model
        if any(self.row.get(key) != value for key, value in changes.items()):
            self.row.update(changes)
            self.save()

    def status(self, status):
        if isinstance(status, int):
            self.row["http_status"] = status
            if status >= 400:
                self.row["status"] = "error"
        elif status == "error":
            self.row["status"] = "error"

    def finish(self, exc=None):
        if self.closed:
            return
        self.row.update(ended_at=_now(), duration_ms=(time.monotonic() - self.started) * 1000)
        if exc is not None:
            self.row["status"] = "cancelled" if isinstance(exc, (asyncio.CancelledError, GeneratorExit)) else "error"
            self.row["error_type"] = type(exc).__name__
        elif self.row["status"] == "running":
            self.row["status"] = "ok"
        try:
            self.save()
        except LedgerError as failure:
            if isinstance(exc, (asyncio.CancelledError, GeneratorExit)):
                exc.add_note(str(failure))
                raise exc from failure
            raise
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, kind, exc, tb):
        self.finish(exc)


class _NoRecord:
    def __bool__(self):
        return False

    def status(self, *args):
        pass

    def usage(self, *args, **kwargs):
        pass

    def finish(self, *args):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


@contextlib.contextmanager
def scope(name, **attributes):
    context = current()
    if context is None:
        yield
        return
    with Record(context, name, "span", attributes) as record:
        nested = Context(context.ledger, context.run_id, record.row["id"], tuple(record.row["attributes"].items()))
        with bind(nested):
            yield record


@contextlib.contextmanager
def run(directory, *, run_id=None, name="experiment"):
    context = Context(Ledger(Path(directory) / FILENAME), run_id or uuid4().hex)
    with bind(context), scope(name) as record:
        yield record


def attempt(provider, model, *, external=False, **attributes):
    """No context is held across a stream yield: the attempt captures its ownership once."""
    context = current()
    if context is None:
        return _NoRecord()
    kind = "external" if external else "attempt"
    return Record(context, f"llm.{kind}", kind, {"provider": provider, "model": model, **attributes})


def stage(name=None, *, argument=None, failed=None):
    """Thin async-function syntax for the same scope lifecycle."""

    def decorate(function):
        signature = inspect.signature(function)

        @functools.wraps(function)
        async def observed(*args, **kwargs):
            if current() is None:
                return await function(*args, **kwargs)
            label = name or function.__name__
            if argument:
                bound = signature.bind(*args, **kwargs)
                bound.apply_defaults()
                label = f"{label}.{bound.arguments[argument]}"
            with scope(label) as record:
                result = await function(*args, **kwargs)
                if failed is not None and failed(result):
                    record.status("error")
                return result

        return observed

    return decorate


def turn(function):
    @functools.wraps(function)
    async def observed(self, request, *args, **kwargs):
        from raven.config.loader import raven_home
        from raven.spine.scheduler import conversation_id

        session = conversation_id(request)
        pending = getattr(self, "_execution_contexts", {})
        payload = pending.pop(session, None)
        restored = receive(payload, raven_home()) if payload else contextlib.nullcontext()
        with restored, scope("session.turn", session_key=session, turn_id=request.turn_id):
            return await function(self, request, *args, **kwargs)

    return observed


def acp_prompt(function):
    @functools.wraps(function)
    async def observed(self, params):
        from raven.config.loader import raven_home

        meta = params.get("_meta")
        payload = meta.get("raven.execution") if isinstance(meta, dict) else None
        with receive(payload, raven_home()), scope("acp.prompt", session_key=self._session_for(params).session_key):
            return await function(self, params)

    return observed
