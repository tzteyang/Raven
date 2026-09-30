"""The attributors: the Curator's model diagnosing in an exchange of its own, or diagnoses made elsewhere.

`ModelAttributor` runs on the curation's provider and, unless it names another, on the curation's model: in the
general case attribution is the Curator reasoning about its own Harness, as a separate step with its own tools,
budget, checkpoint and record. Its prompts are a directory holding `PROMPT_FILES`, so a revised version of them is
a new attributor, not a code change. `SuppliedAttributor` takes diagnoses made elsewhere, such as ones a person
reviewed, and only checks that they cover every input.

Each identity names the implementation and what makes its version, so diagnoses made by different versions can be
told apart when their outcomes are compared: for a model, the model the request actually ran on, whether it carries
the target catalogue, and one digest of everything its request is written from (its own prompts, the Curator's
shared rules and request frame, and its submission's description and schema). The budget is not part of it: a
paused attribution resumes with a larger one. `input_key` names the inputs alone, so two versions that attributed
the same inputs can be compared row by row.
"""

import json
from dataclasses import dataclass, field
from functools import partial
from hashlib import sha256
from pathlib import Path
from string import Template
from typing import Protocol

from ..generation.context import query
from ..generation.context.collect import Context
from ..generation.context.render import prompt_files, tool
from ..generation.run import GapReportedError, GenerationInterruptedError, GenerationPausedError, ask, shared_materials
from ..generation.stages import shared
from ..generation.state import GenerationState
from ..harness.attribution import Attributed, Attribution
from ..harness.declaration import schema_for
from ..raven_adapter.inspection import fingerprint
from .state import AttributionInterruptedError, AttributionLimits, AttributionPausedError, AttributionState
from .subjects import subjects

PROMPTS = Path(__file__).resolve().parent / "prompts"
STAGES = ("understand.md", "diagnose.md")
BUDGET = "budget.md"
PROMPT_FILES = (*STAGES, BUDGET)
NAME = "submit_diagnosis"
VOLATILE_SOURCE_KEYS = ("path", "snapshot_path")


def submission() -> dict:
    return tool(
        NAME,
        "Submit one diagnosis per required input: the responsible mechanism, its state, the evidence and how it was "
        "handled before. The curation that follows grounds every change on these.",
        schema_for(Attribution),
    )


def parse(arguments: dict, required) -> Attribution:
    attribution = Attribution.model_validate(arguments)
    missing = attribution.missing(required)
    if missing:
        raise ValueError(f"no diagnosis for {missing}; every required input needs one: {list(required)}")
    return attribution


def _budget(path: Path, state, limits) -> str:
    return (
        Template(path.read_text())
        .substitute(calls=limits.max_calls - state.calls, queries=limits.max_queries - state.queries)
        .strip()
    )


def effective_model(provider, model: str | None) -> str | None:
    """The model a request with `model` runs on: the one named, else the provider's default when it says."""
    if model:
        return model
    default = getattr(provider, "get_default_model", None)
    return default() if default else None


def input_id(context: Context, required, identity) -> str:
    """What a paused attribution is bound to: this curation's inputs, including its workspace, and the attributor."""
    return fingerprint({"context": GenerationState.identity(context), "subjects": list(required), "identity": identity})


def input_key(context: Context, required) -> str:
    """The attributed inputs alone, without what a curation lays out afresh (its exploration workspace and its
    sources' snapshot paths) and without the attributor: the same inputs attributed twice share it."""
    return fingerprint(
        {
            "task": context.task,
            "baseline": context.declaration.baseline,
            "contract": context.declaration.contract_id,
            "facts": context.facts,
            "sources": {
                name: {key: value for key, value in entry.items() if key not in VOLATILE_SOURCE_KEYS}
                for name, entry in context.sources.items()
            },
            "feedback": context.feedback,
            "observations": context.observations,
            "previous_plan": context.previous_plan.model_dump(mode="json") if context.previous_plan else None,
            "subjects": list(required),
        }
    )


class Attributor(Protocol):
    """What makes an attribution: an identity to record, a check that it can continue a paused attribution, and one
    attribution of a curation's context.

    `attribute` returns the finished `AttributionState`, whose `trace` rows each name their `event`. An attributor
    that stops before it submits raises `AttributionInterruptedError` (`AttributionPausedError` on its budget) with
    its state, and one that reports a gap raises `GapReportedError` with that state as its `state`. `check` raises
    ValueError when `state` cannot be continued with these inputs, before anything is spent or discarded."""

    def identity(self, model: str | None = None) -> dict: ...

    def check(self, state: AttributionState, context: Context, *, model: str | None = None) -> None: ...

    async def attribute(
        self, context: Context, provider, *, model=None, tool_registry=None, resume=None, progress=None
    ) -> AttributionState: ...


def _digest(paths, tools) -> str:
    total = sha256()
    for path in paths:
        total.update(Path(path).read_bytes())
    total.update(json.dumps(tools, sort_keys=True, ensure_ascii=False).encode())
    return total.hexdigest()


@dataclass(frozen=True)
class ModelAttributor:
    """Diagnose with a model; `model` None is the curation's model, `catalogue` True puts the granted targets in the
    request (by default they stay out, so the diagnosis is not drawn toward what could be changed: in a paired real
    run without them, more requirements held at the same cost), and `prompts` is the directory of the version to
    run."""

    model: str | None = None
    catalogue: bool = False
    limits: AttributionLimits = field(default_factory=AttributionLimits)
    prompts: Path = PROMPTS

    def __post_init__(self):
        missing = [name for name in PROMPT_FILES if not (Path(self.prompts) / name).is_file()]
        if missing:
            raise ValueError(f"the attribution prompts at {self.prompts} lack {missing}")

    def identity(self, model: str | None = None) -> dict:
        own = [Path(self.prompts) / name for name in PROMPT_FILES]
        return {
            "implementation": "model",
            "prompts": _digest([*own, *prompt_files()], [submission(), shared.gap_tool()]),
            "model": self.model or model,
            "catalogue": self.catalogue,
        }

    def check(self, state: AttributionState, context: Context, *, model: str | None = None) -> None:
        state.check(input_id(context, subjects(context.feedback), self.identity(model)), self.limits)

    async def attribute(
        self, context: Context, provider, *, model=None, tool_registry=None, resume=None, progress=None
    ) -> AttributionState:
        required = subjects(context.feedback)
        identity = self.identity(effective_model(provider, self.model or model))
        if resume is not None:
            state = resume.model_copy(deep=True)
            state.check(input_id(context, required, identity), self.limits)
        else:
            state = AttributionState(
                input_id=input_id(context, required, identity), identity=identity, subjects=required
            )
        tools = [
            *query.tools(context),
            *(tool_registry.get_definitions() if tool_registry is not None else []),
            submission(),
            shared.gap_tool(),
        ]
        try:
            _, state.attribution = await ask(
                "diagnose",
                tuple(Path(self.prompts) / name for name in STAGES),
                {"required_diagnoses": list(required)},
                {NAME: schema_for(Attribution)},
                {NAME: lambda value: parse(value, required)},
                context=context,
                shared_materials=shared_materials(context, catalogue=self.catalogue),
                provider=provider,
                state=state,
                limits=self.limits,
                validate=None,
                model=self.model or model,
                tool_registry=tool_registry,
                stage_candidate=None,
                progress=progress,
                tools=tools,
                staged=frozenset({NAME}),
                budget=partial(_budget, Path(self.prompts) / BUDGET),
            )
        except GenerationPausedError as exc:
            raise AttributionPausedError(exc.state) from exc
        except GenerationInterruptedError as exc:
            if isinstance(exc, AttributionInterruptedError):
                raise
            raise AttributionInterruptedError(str(exc), exc.state) from exc
        except GapReportedError as exc:
            exc.state = state
            raise
        return state


@dataclass(frozen=True)
class SuppliedAttributor:
    """Diagnoses made elsewhere, such as ones a person reviewed on a page; they must cover every input. `origin` is
    the identity and record of the attribution they came from, when they came from one."""

    attribution: Attribution
    by: str = "supplied"
    origin: dict | None = None

    @classmethod
    def of(cls, value: Attribution | Attributed, *, by: str = "supplied") -> "SuppliedAttributor":
        """Supply `value` as it is: an attribution, or an attributed result (from `workflow.attribute`, say), whose
        identity and record become the origin."""
        if isinstance(value, Attributed):
            return cls(value.attribution, by=by, origin={"identity": value.identity, "record": value.record})
        return cls(value, by=by)

    def identity(self, model: str | None = None) -> dict:
        return {
            "implementation": "supplied",
            "by": self.by,
            "digest": fingerprint(self.attribution.model_dump(mode="json")),
            **({"origin": self.origin} if self.origin else {}),
        }

    def check(self, state: AttributionState, context: Context, *, model: str | None = None) -> None:
        raise ValueError("a supplied attribution never pauses; this checkpoint belongs to another attributor")

    async def attribute(
        self, context: Context, provider, *, model=None, tool_registry=None, resume=None, progress=None
    ) -> AttributionState:
        if resume is not None:
            self.check(resume, context, model=model)
        required = subjects(context.feedback)
        missing = self.attribution.missing(required)
        if missing:
            raise ValueError(f"the supplied attribution has no diagnosis for {missing}; required: {list(required)}")
        identity = self.identity(model)
        return AttributionState(
            input_id=input_id(context, required, identity),
            identity=identity,
            subjects=required,
            attribution=self.attribution,
        )
