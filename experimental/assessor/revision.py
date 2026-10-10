"""Host-owned permissions bind rubric patches to a specific input and criterion version."""

from dataclasses import asdict, dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from .rubric import digest

EDIT_FIELDS = frozenset(
    {
        "definition",
        "definition.subject",
        "definition.applies_when",
        "definition.acceptance",
        "basis",
        "basis.references",
        "basis.derivation",
        "assessment",
        "assessment.decision",
        "assessment.required_checks",
        "assessment.evidence_requirements",
        "kind",
        "parent_id",
    }
)


class Permission(BaseModel):
    """One allowed operation; rewrite fields are paths into the canonical criterion."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    op: Literal["add", "rewrite", "remove"]
    id: str | None = None
    parent_id: str | None = None
    fields: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _shape(self):
        if self.op == "add":
            if self.id is not None or self.fields:
                raise ValueError("addition permissions specify only a parent scope")
        elif not self.id or self.parent_id is not None:
            raise ValueError("rewrite and removal permissions name an existing criterion")
        if self.op == "rewrite" and (not self.fields or set(self.fields) - EDIT_FIELDS):
            raise ValueError("rewrites need explicit editable criterion fields")
        if self.op == "remove" and self.fields:
            raise ValueError("removal permissions do not specify fields")
        return self


def changed_paths(before, after, prefix="") -> set[str]:
    if isinstance(before, dict) and isinstance(after, dict):
        return {
            path
            for key in before.keys() | after.keys()
            for path in changed_paths(before.get(key), after.get(key), f"{prefix}.{key}" if prefix else key)
        }
    return {prefix} if before != after else set()


@dataclass(frozen=True)
class RevisionScope:
    """A frozen capability for one patch, issued independently of its claimed reason."""

    base_version: str
    inputs: str
    allow: tuple[Permission, ...]
    additions: int = 16

    @classmethod
    def bind(cls, standard, norms, allow, *, additions=16):
        return cls(standard.version, digest(dict(norms)), tuple(allow), additions)

    def check_base(self, standard, norms):
        if self.base_version != standard.version or self.inputs != digest(dict(norms)):
            raise ValueError("the rubric or source inputs changed since this patch scope was issued")

    def check_change(self, change, before=None, after=None):
        if change.op == "add":
            accepted = any(p.op == "add" and p.parent_id == after.parent_id for p in self.allow)
        elif change.op == "remove":
            accepted = any(p.op == "remove" and p.id == change.id for p in self.allow)
        else:
            fields = {field for p in self.allow if p.op == "rewrite" and p.id == change.id for field in p.fields}
            changed = changed_paths(asdict(before), asdict(after))
            accepted = bool(fields) and all(
                any(path == field or path.startswith(field + ".") for field in fields) for path in changed
            )
        if not accepted:
            raise ValueError(
                f"{change.op} of {change.id or after.parent_id or 'task scope'!r} exceeds the host patch scope"
            )

    def record(self):
        return {
            "base_version": self.base_version,
            "inputs": self.inputs,
            "allow": [p.model_dump(mode="json") for p in self.allow],
            "additions": self.additions,
        }
