"""The Studio's model endpoints: registered on the page with their keys kept private, chosen for a new session's
employee and model roles, and reached through configurations of their own."""

import json
import stat

import pytest

from experimental import model_roles
from experimental.webui.endpoints import (
    Endpoint,
    EndpointError,
    Endpoints,
    SearchService,
    choices,
    employee_config,
    probe_search,
    route_config,
    routes,
    write_employee_config,
)
from raven.agent.tools.web import WebSearchTool
from raven.config.loader import load_config
from raven.config.schema import Config
from raven.providers.lazy import LazyProvider

KEY = "sk-test-0123456789abcdef"
SEARCH_KEY = "serper-test-9876543210fedcba"
ROLES = ("curator", "attribution", "analyst", "assessor", "sub-harness")


def registered(tmp_path):
    store = Endpoints(tmp_path / "secrets" / "studio-endpoints.json")
    store.save({"name": "gateway", "base": "https://gw.example.com/v1/", "key": KEY, "models": ["gpt-x", "gpt-y"]})
    return store


def test_registered_endpoints_keep_their_keys_private_and_a_change_without_a_key_keeps_it(tmp_path):
    store = registered(tmp_path)
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    [shown] = store.public()
    assert shown == {
        "name": "gateway",
        "base": "https://gw.example.com/v1",
        "protocol": "chat",
        "models": ["gpt-x", "gpt-y"],
        "key": "...cdef",
    }
    assert KEY not in json.dumps(store.public())
    store.save({"name": "gateway", "base": "https://gw.example.com/v2", "protocol": "responses", "models": ["gpt-z"]})
    endpoint = store.get("gateway")
    assert endpoint.key == KEY and endpoint.base == "https://gw.example.com/v2" and endpoint.protocol == "responses"
    assert store.delete("gateway") and store.public() == [] and not store.delete("gateway")


@pytest.mark.parametrize(
    "body, reason",
    [
        ({"name": "", "base": "https://a.example", "key": KEY}, "a name"),
        ({"name": "has space", "base": "https://a.example", "key": KEY}, "letters, digits"),
        ({"name": "a", "base": "ftp://a.example", "key": KEY}, "http or https"),
        ({"name": "a", "base": "https://a.example", "key": KEY, "protocol": "grpc"}, "protocol"),
        ({"name": "a", "base": "https://a.example"}, "a key is required"),
        ({"name": "a", "base": "https://a.example", "key": KEY, "models": [""]}, "a model name"),
    ],
)
def test_a_registration_the_studio_cannot_use_is_refused(tmp_path, body, reason):
    with pytest.raises(EndpointError, match=reason):
        Endpoints(tmp_path / "endpoints.json").save(body)


def test_a_sessions_choices_name_registered_endpoints_and_one_endpoint_per_model(tmp_path):
    store = registered(tmp_path)
    store.save({"name": "other", "base": "https://other.example/v1", "key": KEY})
    found = store.all()
    picked = choices(
        {
            "partner": {"endpoint": "gateway", "model": "gpt-x"},
            "curator": {"endpoint": "gateway", "model": "gpt-y", "effort": "high"},
        },
        found,
        ROLES,
    )
    assert picked == {
        "partner": {"endpoint": "gateway", "model": "gpt-x"},
        "curator": {"endpoint": "gateway", "model": "gpt-y", "effort": "high"},
    }
    assert choices(None, found, ROLES) == {} and choices({}, found, ROLES) == {}
    for given, reason in (
        ({"nobody": {"endpoint": "gateway", "model": "gpt-x"}}, "not a model role"),
        ({"curator": {"endpoint": "missing", "model": "gpt-x"}}, "no endpoint named"),
        ({"curator": {"endpoint": "gateway", "model": " "}}, "curator's model"),
        ({"curator": {"endpoint": "gateway", "model": "gpt-x", "effort": "max"}}, "effort"),
        (
            {"curator": {"endpoint": "gateway", "model": "gpt-x"}, "analyst": {"endpoint": "other", "model": "gpt-x"}},
            "one endpoint within a session",
        ),
    ):
        with pytest.raises(EndpointError, match=reason):
            choices(given, found, ROLES)


def test_the_employee_configuration_sends_its_model_to_the_endpoint_and_keeps_the_rest(tmp_path):
    endpoint = registered(tmp_path).get("gateway")
    base = {
        "agents": {
            "defaults": {"provider": "openrouter", "model": "z-ai/glm", "reasoningEffort": "medium", "temperature": 0.1}
        },
        "providers": {
            "openrouter": {"apiKey": "or-key"},
            "custom": {"apiKey": "old", "apiBase": "https://old.example"},
        },
        "tools": {"restrictToWorkspace": False},
    }
    made = employee_config(base, endpoint, "gpt-x", "high")
    assert made["agents"]["defaults"] == {
        "provider": "custom",
        "model": "gpt-x",
        "reasoningEffort": "high",
        "temperature": 0.1,
    }
    assert made["providers"]["custom"] == {
        "apiKey": KEY,
        "apiBase": "https://gw.example.com/v1",
        "protocol": "chat",
        "models": ["gpt-x"],
    }
    assert made["providers"]["openrouter"] == {"apiKey": "or-key"} and made["tools"] == base["tools"]
    assert base["agents"]["defaults"]["model"] == "z-ai/glm" and base["providers"]["custom"]["apiKey"] == "old"
    assert employee_config(base, endpoint, "gpt-x", None)["agents"]["defaults"]["reasoningEffort"] == "medium"

    (tmp_path / "raven.json").write_text(json.dumps(base))
    written = write_employee_config(
        Endpoints(endpoint_file := tmp_path / "secrets" / "studio-endpoints.json").session_config("live-1"),
        tmp_path / "raven.json",
        endpoint,
        "gpt-x",
        None,
    )
    assert written.parent == endpoint_file.parent / "studio-sessions" and written.name == "live-1.json"
    assert stat.S_IMODE(written.stat().st_mode) == 0o600 and stat.S_IMODE(written.parent.stat().st_mode) == 0o700
    assert json.loads(written.read_text())["providers"]["custom"]["apiKey"] == KEY


def test_routed_models_reach_their_endpoint_and_other_models_their_vendor(tmp_path):
    endpoint = registered(tmp_path).get("gateway")
    config = Config()
    config.agents.defaults.model = "deepseek/deepseek-flash"
    config.agents.defaults.reasoning_effort = "low"
    config.providers.deepseek.api_key = "placeholder"
    routed = route_config(config, endpoint, "gpt-x")
    assert routed.get_provider_name("gpt-x") == "custom" and routed.get_api_base("gpt-x") == "https://gw.example.com/v1"
    assert routed.get_api_key("gpt-x") == KEY and config.providers.custom.api_key == ""

    chosen = {"curator": {"endpoint": "gateway", "model": "gpt-x"}}
    roles = model_roles.resolve({"curator": "gpt-x"}, {}, model_roles.partner_of(config), roles=ROLES)
    provider = model_roles.provider(config, roles, routes=routes(config, {"gateway": endpoint}, chosen))
    assert isinstance(provider, model_roles.Routed) and provider.get_default_model() == "gpt-x"
    sub = provider._pick("gpt-x")
    assert isinstance(sub, LazyProvider) and sub.get_default_model() == "gpt-x" and provider._pick("gpt-x") is sub
    assert provider._pick("deepseek/deepseek-flash") is not sub
    with pytest.raises(EndpointError, match="is gone"):
        routes(config, {}, chosen)
    plain = model_roles.resolve({}, {}, model_roles.partner_of(config), roles=ROLES)
    assert not isinstance(model_roles.provider(config, plain), model_roles.Routed)


def test_an_endpoint_with_a_short_key_shows_none_of_it():
    assert Endpoint("a", "https://a.example", "short").public()["key"] == "****"


def test_the_search_service_is_kept_beside_the_endpoints_with_its_key_private(tmp_path):
    store = registered(tmp_path)
    assert store.search() is None
    assert store.save_search({"provider": "serper", "key": SEARCH_KEY}).public() == {
        "provider": "serper",
        "key": "...dcba",
    }
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600 and list(store.all()) == ["gateway"]
    store.save({"name": "other", "base": "https://other.example/v1", "key": KEY})
    assert store.search() == SearchService("serper", SEARCH_KEY) and list(store.all()) == ["gateway", "other"]
    assert store.save_search({"provider": "serper"}).key == SEARCH_KEY
    for body, reason in (({"provider": "tavily"}, "a key is required"), ({"provider": "google", "key": KEY}, "vendor")):
        with pytest.raises(EndpointError, match=reason):
            store.save_search(body)
    assert store.delete_search() and store.search() is None and list(store.all()) == ["gateway", "other"]
    assert not store.delete_search()


def test_the_employee_configuration_searches_through_the_registered_service(tmp_path):
    base = {
        "agents": {"defaults": {"provider": "openrouter", "model": "z-ai/glm"}},
        "providers": {"openrouter": {"apiKey": "or-key"}},
        "tools": {
            "restrictToWorkspace": False,
            "web": {"search": {"maxResults": 3}, "providers": {"jina": {"apiKey": "j"}}},
        },
    }
    search = SearchService("serper", SEARCH_KEY)
    made = employee_config(base, search=search)
    assert made["agents"] == base["agents"] and made["providers"] == base["providers"]
    assert made["tools"]["web"] == {
        "search": {"maxResults": 3, "provider": "serper"},
        "providers": {"jina": {"apiKey": "j"}, "serper": {"apiKey": SEARCH_KEY}},
    }
    assert "serper" not in json.dumps(base)
    endpoint = registered(tmp_path).get("gateway")
    both = employee_config(base, endpoint, "gpt-x", None, search)
    assert (
        both["agents"]["defaults"]["model"] == "gpt-x"
        and both["tools"]["web"]["providers"]["serper"]["apiKey"] == SEARCH_KEY
    )

    (tmp_path / "raven.json").write_text(json.dumps(base))
    written = write_employee_config(tmp_path / "own.json", tmp_path / "raven.json", search=search)
    loaded = load_config(written)
    assert loaded.tools.web.search.provider == "serper" and loaded.tools.web.search.max_results == 3
    assert loaded.tools.web.providers.key_for("serper") == SEARCH_KEY and loaded.agents.defaults.model == "z-ai/glm"


async def test_a_search_probe_answers_with_the_tools_own_verdict_and_never_the_key(monkeypatch):
    seen = []

    async def answered(tool, query="raven ai agent"):
        seen.append((tool.provider, tool.api_key))
        return True, "1 result(s)"

    monkeypatch.setattr(WebSearchTool, "probe", answered)
    found = await probe_search(SearchService("serper", SEARCH_KEY))
    assert found["ok"] and found["reply"] == "1 result(s)" and seen == [("serper", SEARCH_KEY)]

    async def refused(tool, query="raven ai agent"):
        raise RuntimeError(f"rejected {tool.api_key}")

    monkeypatch.setattr(WebSearchTool, "probe", refused)
    failed = await probe_search(SearchService("serper", SEARCH_KEY))
    assert not failed["ok"] and SEARCH_KEY not in failed["error"] and "<key>" in failed["error"]
