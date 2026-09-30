"""Record actual provider calls and enforce declared Participant boundaries."""

import json
from collections.abc import Mapping
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import fields, is_dataclass, replace
from inspect import iscoroutinefunction
from pathlib import Path

from pydantic import BaseModel

from raven.contracts.loop_hooks import AgentHook, HookDecision
from raven.contracts.participant import StepView
from raven.permissions.turn import current_turn


def plain(value):
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: plain(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    return str(value)


def _copy_observation(value):
    if isinstance(value, Mapping):
        return {key: _copy_observation(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return tuple(_copy_observation(item) for item in value)
    if isinstance(value, list):
        return [_copy_observation(item) for item in value]
    if isinstance(value, StepView):
        return replace(value, **{field.name: _copy_observation(getattr(value, field.name)) for field in fields(value)})
    return deepcopy(value)


def observed_errors(records):
    """Project recorded failures, retaining child attribution across the process boundary."""
    found = []
    for row in records:
        if row["kind"].endswith(".error"):
            found.append(row)
        elif row["kind"] == "child.execution":
            found.extend(
                {**error, "harness": row["harness"], "revision": row["revision"]}
                for error in observed_errors(row["records"])
            )
    return found


class Recorder:
    def __init__(self, path: Path):
        self.path = path
        self.rows: list[dict] = []
        self._turn_id = ContextVar("curator_recorded_turn", default=None)
        path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def turn_id(self):
        return self._turn_id.get()

    @turn_id.setter
    def turn_id(self, value):
        self._turn_id.set(value)

    def add(self, kind: str, **data) -> None:
        turn = current_turn()
        row = {"kind": kind, "turn_id": self.turn_id or turn.turn_id or None, **plain(data)}
        if turn.conversation_id:
            row.setdefault("conversation", turn.conversation_id)
        self.rows.append(row)
        with self.path.open("a") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")


class ObservedProvider:
    """Forward every native provider capability while observing its Loop-facing calls."""

    def __init__(self, provider, recorder: Recorder):
        self._provider, self._recorder = provider, recorder

    def __getattr__(self, name):
        return getattr(self._provider, name)

    async def _call(self, method, *args, **kwargs):
        self._recorder.add(
            "provider.request",
            method=method,
            arguments=args,
            parameters=kwargs,
            defaults=getattr(self._provider, "generation", None),
        )
        try:
            result = await getattr(self._provider, method)(*args, **kwargs)
        except Exception as exc:
            self._recorder.add("provider.error", error=f"{type(exc).__name__}: {exc}")
            raise
        self._recorder.add("provider.response", response=result)
        if result.finish_reason == "error":
            self._recorder.add(
                "provider.error",
                error=result.content or "Provider returned an error response",
                classification=result.error_classification,
            )
        return result

    async def chat(self, *args, **kwargs):
        return await self._call("chat", *args, **kwargs)

    async def chat_with_retry(self, *args, **kwargs):
        return await self._call("chat_with_retry", *args, **kwargs)

    async def chat_stream(self, *args, **kwargs):
        self._recorder.add(
            "provider.request",
            method="chat_stream",
            arguments=args,
            parameters=kwargs,
            defaults=getattr(self._provider, "generation", None),
        )
        try:
            async for delta in self._provider.chat_stream(*args, **kwargs):
                self._recorder.add("provider.delta", delta=delta)
                yield delta
        except Exception as exc:
            self._recorder.add("provider.error", error=f"{type(exc).__name__}: {exc}")
            raise


class ObservedPool:
    """Observe bindings resolved by native routing and subsystem model pins."""

    def __init__(self, pool, recorder: Recorder):
        self._pool, self._recorder = pool, recorder

    def __getattr__(self, name):
        return getattr(self._pool, name)

    def _wrap(self, binding):
        if binding is None or isinstance(binding.provider, ObservedProvider):
            return binding
        return replace(binding, provider=ObservedProvider(binding.provider, self._recorder))

    def bind(self, *args, **kwargs):
        return self._wrap(self._pool.bind(*args, **kwargs))

    def bind_pin(self, *args, **kwargs):
        return self._wrap(self._pool.bind_pin(*args, **kwargs))


class LoopObserver(AgentHook):
    """Keep the native turn metadata reference so honored/refused rollbacks are observable."""

    def __init__(self, recorder: Recorder):
        self.recorder = recorder
        self._metadata = {}

    @property
    def metadata(self):
        return self._metadata.get(self.recorder.turn_id or current_turn().turn_id)

    @metadata.setter
    def metadata(self, value):
        key = self.recorder.turn_id or current_turn().turn_id
        if value is None:
            self._metadata.pop(key, None)
        else:
            self._metadata[key] = value

    async def capture(self, ctx):
        self.metadata = ctx.metadata
        return HookDecision()

    def finish(self):
        meta = self.metadata or {}
        self.recorder.add(
            "loop.control",
            rollbacks=meta.get("hook_rollbacks", 0),
            rollbacks_refused=meta.get("rollbacks_refused", 0),
            mode=meta.get("mode"),
            mode_overlay=meta.get("mode_overlay", {}),
        )
        self.metadata = None


for _phase, _method in vars(AgentHook).items():
    if iscoroutinefunction(_method):
        setattr(LoopObserver, _phase, LoopObserver.capture)
