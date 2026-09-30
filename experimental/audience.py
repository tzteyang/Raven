"""Which roles may receive each field of the loop's types, and the projection that keeps only those fields.

The roles are the cultivation loop's (experimental/docs/cultivation-loop-design.md, section 2). The visibility matrix
lives on the types themselves, the Curator's as well as the loop's: a dataclass field declares its audience in its
metadata, and a pydantic model, or a dataclass whose fields carry no metadata, in its `AUDIENCES` class attribute.
`project` turns a value into its JSON-ready form for one role, keeping a field only when that role is in its audience
and refusing a type that declares nothing, so a value reaches a role's prompt only through a declaration.
"""

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from typing import Literal

from pydantic import BaseModel

Role = Literal["partner", "conversant", "party", "analyst", "curator"]
ROLES: tuple[Role, ...] = ("partner", "conversant", "party", "analyst", "curator")

EVERYONE = frozenset(ROLES)
EVALUATION = frozenset({"party", "analyst"})
HEARD = frozenset({"party", "analyst", "curator"})
INTERNAL = frozenset({"analyst", "curator"})
CURATOR = frozenset({"curator"})
ANALYST = frozenset({"analyst"})
RECORD_ONLY: frozenset[str] = frozenset()


class UndeclaredAudienceError(TypeError):
    """A type or field reached a projection without saying who may receive it."""


def audience(*roles: Role) -> dict:
    """Field metadata naming the roles that may receive the field."""
    unknown = set(roles) - EVERYONE
    if unknown:
        raise ValueError(f"unknown roles: {sorted(unknown)}")
    return {"audience": frozenset(roles)}


def _field_names(cls: type) -> set[str]:
    if is_dataclass(cls):
        return {item.name for item in fields(cls)}
    if isinstance(cls, type) and issubclass(cls, BaseModel):
        return set(cls.model_fields)
    raise UndeclaredAudienceError(f"{cls.__name__} is neither a dataclass nor a pydantic model")


def audiences_of(cls: type) -> dict[str, frozenset[str]]:
    """The audience of every field of `cls`; a field without one is an error, never a default."""
    declared = getattr(cls, "AUDIENCES", None)
    if declared is not None and is_dataclass(cls):
        missing = _field_names(cls) - set(declared)
        if missing:
            raise UndeclaredAudienceError(f"{cls.__name__} declares no audience for {sorted(missing)}")
        return {name: frozenset(declared[name]) for name in _field_names(cls)}
    if is_dataclass(cls):
        out = {}
        for item in fields(cls):
            roles = item.metadata.get("audience")
            if roles is None:
                raise UndeclaredAudienceError(f"{cls.__name__}.{item.name} declares no audience")
            out[item.name] = frozenset(roles)
        return out
    if isinstance(cls, type) and issubclass(cls, BaseModel):
        declared = getattr(cls, "AUDIENCES", None)
        if declared is None:
            raise UndeclaredAudienceError(f"{cls.__name__} declares no AUDIENCES")
        missing = set(cls.model_fields) - set(declared)
        if missing:
            raise UndeclaredAudienceError(f"{cls.__name__} declares no audience for {sorted(missing)}")
        return {name: frozenset(declared[name]) for name in cls.model_fields}
    raise UndeclaredAudienceError(f"{cls.__name__} declares no audience")


def project(value, role: Role):
    """The JSON-ready form of `value` with only the fields `role` may receive, recursively.

    The value must be a declared type, or a list or tuple of them; a bare mapping is content of a field, never a
    value in its own right, so it is refused at the top."""
    if role not in EVERYONE:
        raise ValueError(f"unknown role: {role}")
    return _project(value, role, nested=False)


def _project(value, role: str, *, nested: bool):
    if isinstance(value, BaseModel) or (is_dataclass(value) and not isinstance(value, type)):
        allowed = audiences_of(type(value))
        return {
            name: _project(getattr(value, name), role, nested=True) for name, roles in allowed.items() if role in roles
        }
    if isinstance(value, (list, tuple)):
        return [_project(item, role, nested=nested) for item in value]
    if isinstance(value, Mapping):
        if not nested:
            raise UndeclaredAudienceError("a bare mapping has no audience; project a declared type")
        return {str(key): _project(item, role, nested=True) for key, item in value.items()}
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise UndeclaredAudienceError(f"{type(value).__name__} declares no audience")
