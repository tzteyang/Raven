"""Compartments of the loop: each model role runs inside one, and information enters it only through a guard.

A compartment is a context manager for one role. `admit` takes a value bound for that role's prompt, scans its
text for the role's sealed fingerprints (see `experimental.scenario.sealed`) and records the admission; `provider`
wraps a provider so every request is scanned before it leaves, whatever code assembled it. A guard does not judge
meaning: it recognises identifiers and text that exist only on the side the role must not see. On a hit the
policy decides: `abort` records the violation and raises, `warn` records it and lets the request through, for a
person on a page whose own words are theirs to choose. Every admission and violation is appended to a JSONL log
under the run, so a run's boundaries can be audited after the fact.

The guard and its factory are plain data, so a worker started in another process can carry them.
"""

import json
import logging
import time
from collections.abc import AsyncIterator, Callable
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from raven.contracts.llm_provider import LLMProvider

from ..audience import ROLES, Role, project
from ..curator.raven_adapter.observe import plain
from ..scenario.sealed import Sealed

CURRENT: ContextVar["Compartment | None"] = ContextVar("compartment", default=None)
Policy = Literal["abort", "warn"]
log = logging.getLogger(__name__)


class BoundaryError(RuntimeError):
    """Sealed information reached a role's compartment. It is not resumable: the same request would carry it again."""

    resumable = False

    def __init__(self, role: str, where: str, hits: list[str]):
        super().__init__(f"{role} compartment: sealed information in {where}: {', '.join(hits)}")
        self.role, self.where, self.hits = role, where, hits


def texts_of(value) -> list[str]:
    """Every string inside a value, however nested: message contents, tool results, arguments. A string that is a
    JSON object or array, such as the packet a role is sent as its message, is read as the value it encodes: in its
    encoded form a line break is the two characters of an escape, which would join the words around it and hide a
    sealed text written over several lines."""
    if isinstance(value, str):
        if value.lstrip()[:1] in ("{", "["):
            try:
                decoded = json.loads(value)
            except ValueError:
                return [value]
            if isinstance(decoded, (dict, list)):
                return texts_of(decoded)
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in texts_of(item)]
    if isinstance(value, (list, tuple)):
        return [text for item in value for text in texts_of(item)]
    return []


@dataclass(frozen=True)
class Guard:
    role: str
    sealed: Sealed = Sealed()
    policy: Policy = "abort"
    log: Path | None = None

    def __post_init__(self):
        if self.role not in ROLES:
            raise ValueError(f"unknown role: {self.role}")
        if self.policy not in ("abort", "warn"):
            raise ValueError(f"unknown policy: {self.policy}")

    def scan(self, value) -> list[str]:
        return self._scan(value, self.sealed)

    def _scan(self, value, sealed: Sealed) -> list[str]:
        found: list[str] = []
        for text in texts_of(value):
            for hit in sealed.hits(text):
                if hit not in found:
                    found.append(hit)
        return found

    def check_request(self, messages, tools, kwargs, where: str, *, spared=()) -> list[str]:
        """A provider request. `spared` are streams of words said by someone entitled to say them (see
        `Sealed.without`). For the partner, the user messages are the conversant's own words: what it says of its
        situation is not sealed against the partner, so those texts are subtracted before the scan (the identifiers
        stay). A leak in the system prompt, a tool result or the partner's own words is still caught."""
        sealed = self.sealed.without(spared) if spared else self.sealed
        if self.role == "partner":
            spoken = texts_of([row for row in messages if isinstance(row, dict) and row.get("role") == "user"])
            sealed = sealed.without([spoken])
        return self.check({"messages": messages, "tools": tools, **kwargs}, where, sealed=sealed)

    def record(self, event: str, where: str, hits: list[str] = ()) -> None:
        if self.log is None:
            return
        row = {"time": time.time(), "role": self.role, "event": event, "where": where, "hits": list(hits)}
        self.log.parent.mkdir(parents=True, exist_ok=True)
        with self.log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def check(self, value, where: str, *, sealed: Sealed | None = None) -> list[str]:
        """Scan and apply the policy; the hits are returned when the policy lets the value through."""
        hits = self.scan(value) if sealed is None else self._scan(value, sealed)
        if not hits:
            return []
        self.record("violation", where, hits)
        if self.policy == "abort":
            raise BoundaryError(self.role, where, hits)
        log.warning("%s compartment: sealed information in %s: %s", self.role, where, ", ".join(hits))
        return hits

    def provider(self, provider: LLMProvider) -> "GuardedProvider":
        return GuardedProvider(provider, self)


class GuardedProvider(LLMProvider):
    """A provider whose every request is checked by its own guard before it leaves the compartment. While a
    compartment of the guard's role is entered, the words that compartment was told are spoken this time are spared
    too, so a provider bound before it, such as the Analyst's, spares them; the seal stays the provider's own, so no
    compartment, not even an empty one, can loosen it."""

    def __init__(self, provider: LLMProvider, guard: Guard):
        self.provider, self.guard = provider, guard
        self.api_key = getattr(provider, "api_key", None)
        self.api_base = getattr(provider, "api_base", None)

    def _check(self, messages, tools, kwargs, where: str) -> None:
        active = CURRENT.get()
        spared = active.spoken if active is not None and active.role == self.guard.role else ()
        self.guard.check_request(messages, tools, kwargs, where, spared=spared)

    async def chat_with_retry(self, messages, tools=None, model=None, *args, **kwargs):
        self._check(messages, tools, kwargs, "chat_with_retry")
        return await self.provider.chat_with_retry(messages, tools, model, *args, **kwargs)

    async def chat(self, messages, tools=None, model=None, *args, **kwargs):
        self._check(messages, tools, kwargs, "chat")
        return await self.provider.chat(messages, tools, model, *args, **kwargs)

    async def chat_stream(self, messages, tools=None, model=None, *args, **kwargs) -> AsyncIterator[Any]:
        self._check(messages, tools, kwargs, "chat_stream")
        async for delta in self.provider.chat_stream(messages, tools, model, *args, **kwargs):
            yield delta

    def classify_error(self, *args, **kwargs):
        return self.provider.classify_error(*args, **kwargs)

    def get_default_model(self) -> str:
        return self.provider.get_default_model()

    def can_serve(self, model: str) -> bool:
        return self.provider.can_serve(model)

    def wire_model_id(self, model: str) -> str:
        return self.provider.wire_model_id(model)

    def emits_unparsed_reasoning(self) -> bool:
        return self.provider.emits_unparsed_reasoning()

    def supports_prompt_caching(self, model: str) -> bool:
        return self.provider.supports_prompt_caching(model)

    def supports_assistant_prefill(self, model: str | None = None) -> bool:
        return self.provider.supports_assistant_prefill(model)

    @property
    def generation(self):
        return self.provider.generation

    @generation.setter
    def generation(self, value):
        self.provider.generation = value

    def __getattr__(self, name: str):
        if name in ("provider", "guard"):
            raise AttributeError(name)
        return getattr(self.provider, name)


@dataclass(frozen=True)
class GuardedFactory:
    """A provider factory whose products are guarded; plain data, so a spawned worker process can carry it."""

    factory: Callable[..., LLMProvider]
    guard: Guard

    def __call__(self, *args, **kwargs) -> GuardedProvider:
        return self.guard.provider(self.factory(*args, **kwargs))


class Compartment:
    """One role's compartment; enter it around the role's work and pass its values through `admit`. `spoken` are
    the streams of words its seal already spares, which providers guarded for the same role spare while it is
    entered."""

    def __init__(
        self,
        role: Role,
        sealed: Sealed = Sealed(),
        *,
        policy: Policy = "abort",
        log: Path | None = None,
        spoken=(),
    ):
        self.guard = Guard(role, sealed, policy, log)
        self.spoken = tuple(spoken)
        self._token = None

    @property
    def role(self) -> str:
        return self.guard.role

    def __enter__(self) -> "Compartment":
        self._token = CURRENT.set(self)
        self.guard.record("enter", self.role)
        return self

    def __exit__(self, *exc) -> None:
        self.guard.record("leave", self.role)
        CURRENT.reset(self._token)

    async def __aenter__(self) -> "Compartment":
        return self.__enter__()

    async def __aexit__(self, *exc) -> None:
        self.__exit__(*exc)

    def admit(self, value, label: str = "value"):
        """The JSON-ready form of a value bound for this role, checked against the sealed fingerprints."""
        payload = plain(value)
        hits = self.guard.check(payload, f"admit:{label}")
        self.guard.record("admit", label, hits)
        return payload

    def project(self, value, label: str = "value"):
        """`admit` after projecting a declared type onto this role's audience."""
        return self.admit(project(value, self.guard.role), label)

    def provider(self, provider: LLMProvider) -> GuardedProvider:
        return self.guard.provider(provider)


@dataclass(frozen=True)
class Boundaries:
    """The sealed fingerprints of each role for one run, with the policy and the log they share."""

    sealed: dict[str, Sealed]
    policy: Policy = "abort"
    log: Path | None = None

    def compartment(self, role: Role, *, spoken=()) -> Compartment:
        """The role's compartment; `spoken` are the streams of words the role receives from someone entitled to say
        them, such as each conversant's messages, which are then not sealed against it (see `Sealed.without`)."""
        sealed = self.sealed.get(role, Sealed())
        if spoken:
            sealed = sealed.without(spoken)
        return Compartment(role, sealed, policy=self.policy, log=self.log, spoken=spoken)
