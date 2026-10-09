"""The model and reasoning effort each model role of a cultivation runs on.

A run names a role's model or effort as `role=value`; the partner runs on its Raven configuration's model and effort,
and a role the run does not name runs on the partner's. No role falls back to another role, so the resolved map says
in full who ran on what; a run keeps it in its `settings.json` (`recorded`).
"""

from collections.abc import Mapping
from dataclasses import dataclass

from raven.providers.factory import make_lazy_provider, make_resolving_provider

PARTNER = "partner"
ROLES = (
    "curator",
    "attribution",
    "analyst",
    "collector",
    "counterpart",
    "conversant",
    "assessor",
    "rubric_builder",
    "meta_reviewer",
    "sub-harness",
)
EFFORTS = ("low", "medium", "high")
# Roles that run inside the partner's own processes: the run sets their model, reached through the partner's provider
# and key, while their effort stays what their own configuration says.
IN_PARTNER = frozenset({"sub-harness"})


@dataclass(frozen=True)
class Choice:
    model: str
    effort: str | None = None


def partner_of(config) -> Choice:
    """The partner's model and effort as its Raven configuration sets them; an unset effort is refused, since a
    provider's default is not a run setting."""
    defaults = config.agents.defaults
    if not defaults.reasoning_effort:
        raise ValueError("set agents.defaults.reasoningEffort explicitly; a provider default is not a run setting")
    return Choice(defaults.model, defaults.reasoning_effort)


def pairs(items) -> dict[str, str]:
    """`role=value` items, as a command line gives them, as a map; a missing `=`, an empty side or a role given twice
    is refused."""
    out: dict[str, str] = {}
    for item in items or ():
        role, sep, value = (part.strip() for part in item.partition("="))
        if not sep or not role or not value:
            raise ValueError(f"{item!r} is not role=value")
        if role in out:
            raise ValueError(f"{role} is named twice")
        out[role] = value
    return out


def resolve(models: Mapping[str, str], efforts: Mapping[str, str], partner: Choice, roles=ROLES) -> dict[str, Choice]:
    """Every role's model and effort, the partner first: what the run named for the role, the partner's otherwise.
    Naming the partner, a role outside `roles`, an effort outside `EFFORTS` or the effort of a role in the partner's
    processes is refused."""
    for given in (models, efforts):
        if PARTNER in given:
            raise ValueError("the partner runs on its configuration's model and effort; set them there")
        unknown = sorted(set(given) - set(roles))
        if unknown:
            raise ValueError(f"{', '.join(unknown)}: not a model role of this run; its roles are {', '.join(roles)}")
    for role, effort in efforts.items():
        if role in IN_PARTNER:
            raise ValueError(f"{role} keeps the effort its own configuration sets")
        if effort not in EFFORTS:
            raise ValueError(f"{role}={effort}: an effort is one of {', '.join(EFFORTS)}")
    return {
        PARTNER: partner,
        **{
            role: Choice(
                models.get(role, partner.model), None if role in IN_PARTNER else efforts.get(role, partner.effort)
            )
            for role in roles
        },
    }


def recorded(choices: dict[str, Choice]) -> dict:
    """The resolved map as a run's `settings.json` keeps it, under `models` and `efforts`."""
    return {
        "models": {role: choice.model for role, choice in choices.items()},
        "efforts": {role: choice.effort for role, choice in choices.items() if role not in IN_PARTNER},
    }


def provider(config, choices: dict[str, Choice]):
    """The provider the run's model roles call through: the partner's configuration on the Curator's model and effort,
    because the Curator's generation steps its effort down from the provider's own; every other role names its model
    and effort on each call. Once a role runs on a model other than the partner's, each call's vendor follows its
    model id, so roles can run on a gateway while others stay on the partner's vendor."""
    config = config.model_copy(deep=True)
    defaults = config.agents.defaults
    own = any(choice.model != choices[PARTNER].model for role, choice in choices.items() if role not in IN_PARTNER)
    if own:
        defaults.provider = "auto"
    defaults.model, defaults.reasoning_effort = choices["curator"].model, choices["curator"].effort
    return make_resolving_provider(config) if own else make_lazy_provider(config)
