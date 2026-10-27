"""The Studio's model endpoints: services a person registers on the page, each an address, a key, the wire protocol
and the model names it serves, kept in one private file beside the employee's Raven configuration (`LiveConfig`'s
`endpoints`).

A new session may put the employee and any model role on a model of an endpoint. The employee then runs on a Raven
configuration of its own (`employee_config`), written beside the endpoints file, never in the run directory; a role
reaches its model through a configuration that sends that one model to the endpoint (`route_config`), which
`model_roles.provider` routes by model name. A model name is served by one endpoint within a session, since a role
names only its model on each call.

The page also registers one web search service, a vendor and its key (`SearchService`), kept in the same file. Every
session's employee configuration carries it under `tools.web`, where the employee's own search and its research
colleague read it, so a session that registers a search service runs on a configuration of its own even when its
employee keeps the configured model.

Keys never leave the server: the page sees each key's last four characters (`Endpoint.public`), and nothing written
to a session's record, settings or exported employee carries one.
"""

import copy
import json
import os
import re
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import get_args
from urllib.parse import urlsplit

from raven.config.schema import WebSearchProvider
from raven.utils.atomic_io import remove_with_lock

FILE = "studio-endpoints.json"
SESSIONS = "studio-sessions"
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,39}")
PROTOCOLS = ("chat", "responses", "anthropic")
EFFORTS = ("low", "medium", "high")
SEARCH_VENDORS = get_args(WebSearchProvider)
KEEP = {"name": 40, "base": 500, "key": 500, "model": 200, "models": 50}
PROBE_TIMEOUT = 60


@dataclass(frozen=True)
class Endpoint:
    name: str
    base: str
    key: str
    protocol: str = "chat"
    models: tuple[str, ...] = field(default=())

    def public(self) -> dict:
        """What the page may see: everything but the key, of which only the last four characters."""
        return {
            "name": self.name,
            "base": self.base,
            "protocol": self.protocol,
            "models": list(self.models),
            "key": _tail(self.key),
        }

    def stored(self) -> dict:
        return {
            "name": self.name,
            "base": self.base,
            "key": self.key,
            "protocol": self.protocol,
            "models": list(self.models),
        }


@dataclass(frozen=True)
class SearchService:
    """The web search every session's employee and its research colleague use: a vendor Raven routes, and its key."""

    provider: str
    key: str

    def public(self) -> dict:
        return {"provider": self.provider, "key": _tail(self.key)}

    def stored(self) -> dict:
        return {"provider": self.provider, "key": self.key}


def _tail(key: str) -> str:
    """What the page may see of a key: its last four characters, or none of a key too short to spare them."""
    return f"...{key[-4:]}" if len(key) > 8 else "****"


class EndpointError(ValueError):
    """A registration or a session's choice the Studio refuses, with the reason the page shows."""


def _text(value, what: str, keep: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > keep:
        raise EndpointError(f"{what} is required, at most {keep} characters")
    return value.strip()


def _parsed(item: dict) -> Endpoint:
    name = _text(item.get("name"), "a name", KEEP["name"])
    if not NAME.fullmatch(name):
        raise EndpointError("a name is letters, digits, '.', '_' or '-', starting with a letter or digit")
    base = _text(item.get("base"), "an address", KEEP["base"]).rstrip("/")
    parts = urlsplit(base)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise EndpointError("the address is an http or https URL, such as https://api.example.com/v1")
    protocol = item.get("protocol") or "chat"
    if protocol not in PROTOCOLS:
        raise EndpointError(f"the protocol is one of {', '.join(PROTOCOLS)}")
    models = item.get("models") or []
    if not isinstance(models, list) or len(models) > KEEP["models"]:
        raise EndpointError(f"models are a list of at most {KEEP['models']} names")
    names = tuple(dict.fromkeys(_text(model, "a model name", KEEP["model"]) for model in models))
    key = item.get("key")
    return Endpoint(name, base, key if isinstance(key, str) else "", protocol, names)


class Endpoints:
    """The registered endpoints, read from and written to one file the server alone may read (mode 0600)."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.lock = threading.Lock()

    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text())
        except FileNotFoundError:
            return {}
        except ValueError as exc:
            raise EndpointError(f"the endpoints file is not JSON: {exc}") from exc
        return data if isinstance(data, dict) else {}

    def all(self) -> dict[str, Endpoint]:
        items = self._read().get("endpoints")
        found = {}
        for item in items if isinstance(items, list) else []:
            endpoint = _parsed(item)
            found[endpoint.name] = endpoint
        return found

    def get(self, name) -> Endpoint | None:
        return self.all().get(name) if isinstance(name, str) else None

    def public(self) -> list[dict]:
        return [endpoint.public() for endpoint in self.all().values()]

    def save(self, body: dict) -> Endpoint:
        """Add an endpoint or change one; a change that gives no key keeps the one registered."""
        endpoint = _parsed(body)
        with self.lock:
            found = self.all()
            known = found.get(endpoint.name)
            key = endpoint.key.strip() or (known.key if known else "")
            if not key or len(key) > KEEP["key"]:
                raise EndpointError(f"a key is required, at most {KEEP['key']} characters")
            endpoint = Endpoint(endpoint.name, endpoint.base, key, endpoint.protocol, endpoint.models)
            found[endpoint.name] = endpoint
            self._write(found, self.search())
        return endpoint

    def delete(self, name) -> bool:
        with self.lock:
            found = self.all()
            if not isinstance(name, str) or found.pop(name, None) is None:
                return False
            self._write(found, self.search())
        return True

    def search(self) -> SearchService | None:
        item = self._read().get("search")
        if item is None:
            return None
        if not isinstance(item, dict) or item.get("provider") not in SEARCH_VENDORS or not item.get("key"):
            raise EndpointError("the search service in the endpoints file is not usable; register it again")
        return SearchService(item["provider"], item["key"])

    def save_search(self, body: dict) -> SearchService:
        """Register the search service, or change it; a change that keeps the vendor and gives no key keeps the key."""
        provider = body.get("provider") or "serper"
        if provider not in SEARCH_VENDORS:
            raise EndpointError(f"the search vendor is one of {', '.join(SEARCH_VENDORS)}")
        given = body.get("key")
        with self.lock:
            known = self.search()
            key = (given.strip() if isinstance(given, str) else "") or (
                known.key if known and known.provider == provider else ""
            )
            if not key or len(key) > KEEP["key"]:
                raise EndpointError(f"a key is required, at most {KEEP['key']} characters")
            service = SearchService(provider, key)
            self._write(self.all(), service)
        return service

    def delete_search(self) -> bool:
        with self.lock:
            if self.search() is None:
                return False
            self._write(self.all(), None)
        return True

    def _write(self, found: dict[str, Endpoint], search: SearchService | None) -> None:
        body = {
            "endpoints": [item.stored() for item in found.values()],
            **({"search": search.stored()} if search else {}),
        }
        _private_write(self.path, json.dumps(body, ensure_ascii=False, indent=2))

    def session_config(self, session: str) -> Path:
        """Where a session's own employee configuration is written: beside the endpoints file, out of the run."""
        return self.path.parent / SESSIONS / f"{session}.json"

    def forget(self, session: str) -> None:
        """Remove a session's employee configuration with what Raven keeps beside a configuration it read: the
        loader's migration stamp (`raven.config.loader._stamp_path`) and the lock sidecars of both."""
        own = self.session_config(session)
        for path in (own, own.with_name(f"{own.stem}.migrations.json")):
            remove_with_lock(path)


def _private_write(path: Path, text: str) -> None:
    """Write a file only its owner may read, replacing it atomically, so no reader ever sees half a key."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.name == SESSIONS:
        os.chmod(path.parent, 0o700)
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        os.fchmod(handle, 0o600)
        with os.fdopen(handle, "w") as file:
            file.write(text)
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def choices(given, endpoints: dict[str, Endpoint], roles) -> dict[str, dict]:
    """A new session's choices, `{role: {"endpoint", "model", "effort"}}` for the partner and the model roles, checked
    against the registered endpoints; a model name may be served by one endpoint only."""
    if given in (None, {}):
        return {}
    if not isinstance(given, dict):
        raise EndpointError("models map each role to its endpoint and model")
    out, served = {}, {}
    for role, choice in given.items():
        if role != "partner" and role not in roles:
            raise EndpointError(f"{role}: not a model role of a session")
        if not isinstance(choice, dict):
            raise EndpointError(f"{role}: a choice is its endpoint, model and effort")
        endpoint = choice.get("endpoint")
        if endpoint not in endpoints:
            raise EndpointError(f"{role}: no endpoint named {endpoint!r}")
        model = _text(choice.get("model"), f"{role}'s model", KEEP["model"])
        effort = choice.get("effort") or None
        if effort is not None and effort not in EFFORTS:
            raise EndpointError(f"{role}: the effort is one of {', '.join(EFFORTS)}")
        if served.setdefault(model, endpoint) != endpoint:
            raise EndpointError(
                f"{model} is served by one endpoint within a session, not by {served[model]} and {endpoint}"
            )
        out[role] = {"endpoint": endpoint, "model": model, **({"effort": effort} if effort else {})}
    return out


def employee_config(
    base: dict,
    endpoint: Endpoint | None = None,
    model: str | None = None,
    effort: str | None = None,
    search: SearchService | None = None,
) -> dict:
    """The employee's Raven configuration (as its JSON): the base one, on `model` of `endpoint` when one is given (the
    employee's vendor, model and effort replaced and the generic OpenAI-compatible section pointed at the endpoint),
    and searching through `search` when one is given."""
    data = copy.deepcopy(base)
    if endpoint is not None:
        defaults = data.setdefault("agents", {}).setdefault("defaults", {})
        defaults["provider"], defaults["model"] = "custom", model
        if effort:
            defaults.pop("reasoning_effort", None)
            defaults["reasoningEffort"] = effort
        providers = data.setdefault("providers", {})
        providers["custom"] = {
            "apiKey": endpoint.key,
            "apiBase": endpoint.base,
            "protocol": endpoint.protocol,
            "models": [model],
        }
    if search is not None:
        web = data.setdefault("tools", {}).setdefault("web", {})
        web.setdefault("search", {})["provider"] = search.provider
        web.setdefault("providers", {})[search.provider] = {"apiKey": search.key}
    return data


def write_employee_config(
    path: Path,
    base: Path,
    endpoint: Endpoint | None = None,
    model: str | None = None,
    effort: str | None = None,
    search: SearchService | None = None,
) -> Path:
    """Write `employee_config` of the configuration at `base` to `path`, readable by its owner alone."""
    made = employee_config(json.loads(Path(base).read_text()), endpoint, model, effort, search)
    _private_write(path, json.dumps(made, indent=2))
    return path


def route_config(config, endpoint: Endpoint, model: str):
    """A copy of a loaded Raven `Config` that sends `model`, and nothing else, to `endpoint`."""
    from raven.config.schema import ProviderConfig

    routed = config.model_copy(deep=True)
    routed.agents.defaults.provider = "custom"
    routed.agents.defaults.model = model
    routed.providers.custom = ProviderConfig(
        api_key=endpoint.key, api_base=endpoint.base, protocol=endpoint.protocol, models=[model]
    )
    return routed


def routes(config, endpoints: dict[str, Endpoint], chosen: dict[str, dict]) -> dict:
    """Each model a session's choices put on an endpoint, with the configuration that reaches it."""
    out = {}
    for choice in chosen.values():
        endpoint = endpoints.get(choice["endpoint"])
        if endpoint is None:
            raise EndpointError(f"the endpoint {choice['endpoint']!r} this session was started on is gone")
        out[choice["model"]] = route_config(config, endpoint, choice["model"])
    return out


async def probe(config, endpoint: Endpoint, model: str) -> dict:
    """One short request to `model` through `endpoint`, the way a session reaches it; what came back, or why not."""
    import asyncio

    from raven.providers.factory import make_provider

    started = time.monotonic()
    try:
        provider = make_provider(route_config(config, endpoint, model), model)
        reply = await asyncio.wait_for(
            provider.chat([{"role": "user", "content": "Reply with the word ok."}], model=model, max_tokens=16),
            PROBE_TIMEOUT,
        )
    except Exception as exc:  # noqa: BLE001 -- any failure is the probe's answer
        return {"ok": False, "seconds": round(time.monotonic() - started, 1), "error": _clean(str(exc), endpoint)}
    text = (getattr(reply, "content", None) or "").strip()
    failed = getattr(reply, "finish_reason", None) == "error"
    return {
        "ok": not failed,
        "seconds": round(time.monotonic() - started, 1),
        **({"error": _clean(text, endpoint)} if failed else {"reply": text[:200]}),
    }


async def probe_search(service: SearchService) -> dict:
    """One real search through `service`, the way a session's employee would search; what came back, or why not."""
    import asyncio

    from raven.agent.tools.web import WebSearchTool

    started = time.monotonic()
    try:
        ok, detail = await asyncio.wait_for(
            WebSearchTool(api_key=service.key, provider=service.provider).probe(), PROBE_TIMEOUT
        )
    except Exception as exc:  # noqa: BLE001 -- any failure is the probe's answer
        ok, detail = False, f"{type(exc).__name__}: {exc}"
    detail = detail.replace(service.key, "<key>")[:500]
    return {
        "ok": ok,
        "seconds": round(time.monotonic() - started, 1),
        **({"reply": detail} if ok else {"error": detail}),
    }


def _clean(text: str, endpoint: Endpoint) -> str:
    return text.replace(endpoint.key, "<key>")[:500] if endpoint.key else text[:500]
