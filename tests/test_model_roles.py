"""The role map of a cultivation run: which model and effort each model role runs on."""

import pytest

from experimental import model_roles
from experimental.model_roles import Choice
from raven.config.schema import Config

PARTNER = Choice("deepseek/deepseek-v4-flash", "low")


def test_a_role_not_named_runs_on_the_partners_model_and_effort_never_on_another_roles():
    roles = model_roles.resolve(
        model_roles.pairs(["curator=openai/gpt-6.1-sol"]), {"curator": "high", "judge": "medium"}, PARTNER
    )
    assert roles["partner"] == PARTNER
    assert roles["curator"] == Choice("openai/gpt-6.1-sol", "high")
    assert roles["attribution"] == roles["analyst"] == roles["collector"] == PARTNER
    assert roles["judge"] == Choice(PARTNER.model, "medium")
    assert roles["sub-harness"] == Choice(PARTNER.model, None)
    assert list(roles) == ["partner", *model_roles.ROLES]


@pytest.mark.parametrize(
    ("models", "efforts", "message"),
    [
        (["partner=x"], [], "configuration"),
        (["traveller=x"], [], "not a model role"),
        (["curator=x", "curator=y"], [], "twice"),
        (["curator"], [], "role=value"),
        (["curator="], [], "role=value"),
        ([], ["curator=max"], "one of"),
        ([], ["sub-harness=low"], "its own configuration"),
    ],
)
def test_a_role_map_is_refused_when_it_cannot_be_read_one_way(models, efforts, message):
    with pytest.raises(ValueError, match=message):
        model_roles.resolve(model_roles.pairs(models), model_roles.pairs(efforts), PARTNER)


def test_a_run_without_some_roles_refuses_to_name_them():
    with pytest.raises(ValueError, match="not a model role of this run"):
        model_roles.resolve({"counterpart": "x"}, {}, PARTNER, roles=("curator", "analyst"))


def test_the_record_keeps_every_roles_model_and_leaves_out_an_effort_the_run_does_not_set():
    kept = model_roles.recorded(model_roles.resolve({"sub-harness": "z"}, {}, PARTNER))
    assert kept["models"]["sub-harness"] == "z" and kept["models"]["partner"] == PARTNER.model
    assert "sub-harness" not in kept["efforts"] and kept["efforts"]["critic"] == "low"


def config() -> Config:
    return Config.model_validate(
        {
            "providers": {"openrouter": {"apiKey": "k"}},
            "agents": {"defaults": {"model": PARTNER.model, "provider": "openrouter", "reasoningEffort": "low"}},
        }
    )


@pytest.mark.parametrize(
    ("models", "resolving"),
    [([], False), (["sub-harness=other/model"], False), (["analyst=other/model"], True)],
)
def test_the_provider_runs_on_the_curators_choice_and_resolves_vendors_once_a_role_has_its_own_model(
    monkeypatch, models, resolving
):
    made = []
    monkeypatch.setattr(model_roles, "make_lazy_provider", lambda config: made.append(("lazy", config)))
    monkeypatch.setattr(model_roles, "make_resolving_provider", lambda config: made.append(("resolving", config)))
    source = config()
    model_roles.provider(source, model_roles.resolve(model_roles.pairs(models), {"curator": "high"}, PARTNER))
    [(kind, used)] = made
    assert kind == ("resolving" if resolving else "lazy")
    assert used.agents.defaults.reasoning_effort == "high" and used.agents.defaults.model == PARTNER.model
    assert used.agents.defaults.provider == ("auto" if resolving else "openrouter")
    assert source.agents.defaults.reasoning_effort == "low"


def test_the_partner_needs_an_explicit_effort():
    unset = config()
    unset.agents.defaults.reasoning_effort = None
    with pytest.raises(ValueError, match="reasoningEffort"):
        model_roles.partner_of(unset)
    assert model_roles.partner_of(config()) == PARTNER
