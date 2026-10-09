"""Compare construction methods on frozen independent tasks and preserve inspectable execution evidence."""

import asyncio
import copy
from collections.abc import Awaitable, Callable, Sequence
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from .governance import Record, fingerprint

VALIDATING = ContextVar("experience_validation", default=False)


class Result(Record):
    satisfied: bool | None = Field(strict=True)
    preserved: bool | None = Field(strict=True)
    record: str = Field(min_length=1)
    cost: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def finite_cost(self):
        import math

        if not self.record.strip():
            raise ValueError("a comparison result needs an inspectable execution reference")
        if any(not math.isfinite(value) or value < 0 for value in self.cost.values()):
            raise ValueError("experience comparisons require finite nonnegative costs")
        return self


@dataclass(frozen=True)
class Case:
    id: str
    lineage: str
    inputs: dict
    files: tuple[Path, ...] = ()
    references: tuple[str, ...] = ()

    def snapshot(self):
        import hashlib

        return {
            "inputs": self.inputs,
            "files": {str(path): hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in self.files},
        }


class Comparison(Record):
    case: str
    lineage: str
    inputs: str
    before: Result
    after: Result
    history: Result | None = None
    references: tuple[str, ...] = ()


class Study(Record):
    baseline: str
    candidate: str
    context: str
    purpose: Literal["improvement", "consolidation"] = "improvement"
    cases: tuple[Comparison, ...] = ()
    history: str | None = None
    error: str = ""

    @property
    def independent_cases(self) -> int:
        groups = []
        for row in self.cases:
            keys = {("lineage", row.lineage), ("inputs", row.inputs)}
            matched = [group for group in groups if group & keys]
            groups = [group for group in groups if not group & keys]
            groups.append(keys.union(*matched))
        return len(groups)

    @property
    def accepted(self) -> bool:
        if self.error or not self.cases or self.baseline == self.candidate:
            return False
        if self.independent_cases < 2:
            return False
        if any(row.before.record == row.after.record for row in self.cases):
            return False
        if self.history is not None and any(
            row.history is None or row.history.satisfied is None or row.history.preserved is None for row in self.cases
        ):
            return False
        if any(row.after.satisfied is None or row.after.preserved is not True for row in self.cases):
            return False
        if any(row.before.satisfied is True and row.after.satisfied is not True for row in self.cases):
            return False
        if any(row.before.satisfied is None or row.before.preserved is None for row in self.cases):
            return False
        if any(row.before.satisfied is False and row.after.satisfied is True for row in self.cases):
            return True
        if any(row.before.preserved is False and row.after.preserved is True for row in self.cases):
            return True
        if self.purpose != "consolidation":
            return False
        if any(row.before.satisfied is not True or row.after.satisfied is not True for row in self.cases):
            return False
        comparable = [row for row in self.cases if row.before.cost and row.before.cost.keys() == row.after.cost.keys()]
        return (
            len(comparable) == len(self.cases)
            and all(row.after.cost[key] <= row.before.cost[key] for row in comparable for key in row.before.cost)
            and any(row.after.cost[key] < row.before.cost[key] for row in comparable for key in row.before.cost)
        )

    @property
    def id(self):
        return fingerprint(self.model_dump(mode="json"))

    def record(self):
        return {**self.model_dump(mode="json"), "id": self.id, "accepted": self.accepted}


async def compare_methods(
    *,
    before: str,
    after: str,
    context: str,
    cases: Sequence[Case],
    evaluate: Callable[[str, Case], Awaitable[Result]],
    history: str | None = None,
    purpose: Literal["improvement", "consolidation"] = "improvement",
    timeout: float = 180,
) -> Study:
    import math

    if not context or not 2 <= len(cases) <= 6 or len({row.id for row in cases}) != len(cases):
        raise ValueError("a method comparison needs two to six distinct, context-bound cases")
    if not math.isfinite(timeout) or timeout <= 0 or any(not row.id or not row.lineage for row in cases):
        raise ValueError("method comparison identities and timeout must be explicit")
    cases = tuple(copy.deepcopy(cases))
    frozen = fingerprint([row.snapshot() for row in cases])
    comparisons = []
    error = ""
    try:
        for index, case in enumerate(cases):
            arms = {"before": before, "after": after, **({"history": history} if history is not None else {})}
            names = list(arms)
            names = names[index % len(names) :] + names[: index % len(names)]
            results = {}
            for name in names:
                invocation = copy.deepcopy(case)
                token = VALIDATING.set(True)
                try:
                    value = await asyncio.wait_for(evaluate(arms[name], invocation), timeout=timeout)
                finally:
                    VALIDATING.reset(token)
                if not isinstance(value, Result):
                    raise ValueError("a comparison must return an observed result and execution reference")
                results[name] = value
                if fingerprint([row.snapshot() for row in cases]) != frozen or invocation.snapshot() != case.snapshot():
                    raise ValueError("a method runner changed the frozen task inputs")
            comparisons.append(
                Comparison(
                    case=case.id,
                    lineage=case.lineage,
                    inputs=fingerprint(case.snapshot()),
                    before=results["before"],
                    after=results["after"],
                    history=results.get("history"),
                    references=case.references,
                )
            )
    except Exception as exc:
        error = str(exc) or type(exc).__name__
    return Study(
        baseline=fingerprint(before),
        candidate=fingerprint(after),
        context=context,
        purpose=purpose,
        cases=tuple(comparisons),
        history=fingerprint(history) if history is not None else None,
        error=error,
    )
