"""Collect and independently review expert information through three acquisition channels."""

import asyncio
import inspect
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from pydantic import Field

from raven.agent.tools.registry import call_failed

from ..curator.generation.context.render import tool
from ..curator.harness.declaration import schema_for
from ..iteration.exchange import ExchangeError, exchange, messages
from ..model_calls import argument_errors
from .information import (
    Description,
    Dimension,
    Evidence,
    Question,
    Request,
    ResearchBrief,
    ResearchGuide,
    Result,
    Review,
    Section,
    Snapshot,
    _Model,
)
from .researchers import ResearchError

PROMPTS = Path(__file__).resolve().parent / "prompts"
SUBMIT = "submit_information"
REVIEW = "review_information"
RESEARCH = "delegate_research"
GUIDANCE = "prepare_research"
ASK = "ask_user"
READ = "read_sources"


@dataclass(frozen=True)
class CollectionLimits:
    calls: int = 16
    queries: int = 32
    research_tasks: int = 6
    reviews: int = 3
    review_calls: int = 3
    guidance_calls: int = 3
    timeout: float = 300
    research_timeout: float = 3600
    research_revisions: int = 1
    total_timeout: float = 3600
    reserve: float = 600
    research_minimum: float = 300
    verification_reserve: float = 150
    research_questions: int = 2

    def __post_init__(self):
        if any(value < 1 for value in (self.calls, self.queries, self.reviews, self.review_calls, self.guidance_calls)):
            raise ValueError("collection call, query and review limits must be positive")
        if self.research_tasks < 0 or not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ValueError("research tasks must be nonnegative and timeout positive and finite")
        if self.research_revisions < 0 or not math.isfinite(self.research_timeout) or self.research_timeout <= 0:
            raise ValueError("research revisions must be nonnegative and research timeout positive and finite")
        if not math.isfinite(self.total_timeout) or self.total_timeout <= 0:
            raise ValueError("total collection timeout must be positive and finite")
        if not math.isfinite(self.reserve) or self.reserve < 0:
            raise ValueError("the submission reserve must be nonnegative and finite")
        if not math.isfinite(self.research_minimum) or self.research_minimum <= 0 or self.research_questions < 1:
            raise ValueError("the research minimum must be positive and finite and a group needs at least one question")
        if not math.isfinite(self.verification_reserve) or not 0 <= self.verification_reserve < self.research_minimum:
            raise ValueError("the verification reserve must be nonnegative and smaller than the research minimum")

    def research_window(self, elapsed: float) -> float:
        """Seconds one research may still take before the submission reserve begins."""
        return min(self.research_timeout, self.total_timeout - elapsed - self.reserve)

    def acquisition_window(self, window: float) -> float:
        """The part of a research window the researcher may spend; the rest verifies quotes and reviews."""
        return max(self.research_minimum - self.verification_reserve, window - self.verification_reserve)


class ResearchTask(_Model):
    dimensions: tuple[Dimension, ...] = Field(min_length=1)
    brief: ResearchBrief
    known_evidence: tuple[str, ...] = ()
    use_guidance: bool = True
    previous_attempt: str | None = Field(
        default=None, description="A returned attempt handle to revise; null for a new group."
    )


class ResearchAssignment(ResearchTask):
    """A research group with host-resolved evidence and optional guidance attached."""

    known_information: tuple[Evidence, ...] = ()
    guidance: tuple[ResearchGuide, ...] = ()
    attempt: str
    remaining_seconds: float = Field(gt=0)


class UserQuestion(_Model):
    dimension: Dimension
    question: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    blocking: bool = True
    proposal: str | None = None


class ResearchNeed(_Model):
    question: str = Field(min_length=1)
    dimensions: tuple[Dimension, ...] = Field(min_length=1)


class SourceRead(_Model):
    names: tuple[str, ...] = Field(
        min_length=1, max_length=12, description="Names of listed interaction or host sources to read together."
    )


SOURCE_CHARS = 30_000


async def _answer(callback, value):
    answer = callback(value)
    return await answer if inspect.isawaitable(answer) else answer


def _source_addresses(result):
    addresses = []
    if isinstance(result, dict):
        for finding in result.get("findings", ()):
            if isinstance(finding, dict):
                addresses.extend(finding.get("sources", ()))
        addresses.extend(result.get("sources", ()))
    return tuple(
        dict.fromkeys(
            address for address in addresses if isinstance(address, str) and address.startswith(("https://", "http://"))
        )
    )


def _review_evidence(snapshot, research_tasks):
    referenced = snapshot.description.references | {id for task in research_tasks for id in task["known_evidence"]}
    return [
        source.model_dump(mode="json")
        for source in snapshot.evidence
        if source.channel != "request" or source.id in referenced
    ]


def _locations(request, arguments):
    origins, addresses = dict(arguments), []
    for source in request.context.get("interaction_sources", {}).values():
        path = source["path"]
        if not any(isinstance(value, str) and path in value for value in arguments.values()):
            continue
        stable = source.get("worker_path") or source.get("source_path")
        if stable:
            addresses.append(f"{stable}#sha256={source['digest']}")
            origins = {
                key: value.replace(path, stable) if isinstance(value, str) else value for key, value in origins.items()
            }
    return origins, tuple(addresses)


def _submission(request, evidence, pending, arguments):
    description = Description.model_validate(arguments)
    snapshot = Snapshot(description=description, evidence=tuple(evidence), manifest=request.manifest)
    unanswered = {item.id: item for item in description.unresolved}
    for id, item in pending.items():
        if unanswered.get(id) != item:
            raise ValueError(f"preserve unanswered user question {id} exactly")
    if request.previous is not None:
        previous = {section.dimension: section for section in request.previous.description.sections}
        for section in description.sections:
            if section.dimension not in request.focus and section != previous[section.dimension]:
                raise ValueError(f"preserve the section outside focus: {section.dimension}")
        for item in request.previous.description.unresolved:
            if item.dimension not in request.focus and unanswered.get(item.id) != item:
                raise ValueError(f"preserve unresolved question outside focus: {item.id}")
    return snapshot


def _reviewed_result(request, snapshot, review):
    previous_sections = (
        {section.dimension: section for section in request.previous.description.sections} if request.previous else {}
    )
    return Result(
        snapshot=snapshot,
        review=review,
        previous=request.previous.identity if request.previous else None,
        changed_dimensions=tuple(
            section.dimension
            for section in snapshot.description.sections
            if section != previous_sections.get(section.dimension)
        ),
        resources_changed=request.previous is None
        or snapshot.description.resources != request.previous.description.resources,
        questions_changed=request.previous is None
        or snapshot.description.unresolved != request.previous.description.unresolved,
    )


def _unfinished_result(request, snapshot, evidence, pending, reason, error):
    base = snapshot or request.previous
    description = (
        base.description
        if base
        else Description(
            title="Unfinished expert information",
            sections=tuple(
                Section(dimension=dimension, coverage="missing", reason="Not assessed before execution ended.")
                for dimension in request.focus
            ),
        )
    )
    questions = {question.id: question for question in description.unresolved}
    questions.update(pending)
    description = description.model_copy(update={"unresolved": tuple(questions.values())})
    snapshot = Snapshot(description=description, evidence=tuple(evidence), manifest=request.manifest)
    review = Review(accepted=False, reason=error, issues=("Complete collection and review before handoff.",))
    return _reviewed_result(request, snapshot, review).model_copy(update={"stop_reason": reason})


def _research_window(task, limits, elapsed):
    """The seconds this group may take, or a refusal when it is too broad or the submission reserve has begun."""
    if len(task.brief.questions) > limits.research_questions:
        raise ValueError(
            f"a research group takes at most {limits.research_questions} questions; narrow this one or split it"
        )
    window = limits.research_window(elapsed)
    if window < limits.research_minimum:
        raise ValueError(
            f"only {max(0, round(window))} seconds remain before the {round(limits.reserve)} second submission "
            "reserve; submit the supported description with explicit gaps instead of researching"
        )
    return window


def _source_reader(request, listed, calls, count_query, retain, allowance):
    """One query reading several listed sources; each file becomes its own evidence entry, truncated at a bound."""

    async def read_sources(arguments):
        calls.check(arguments)
        names = SourceRead.model_validate(arguments).names
        unknown = [name for name in names if name not in listed]
        if unknown or len(set(names)) != len(names):
            raise ValueError(f"read_sources takes distinct listed source names; unknown: {unknown}")
        count_query()
        rows = []
        for name in names:
            path = Path(listed[name]["path"])
            try:
                text = path.read_text(errors="replace")
            except OSError as exc:
                rows.append({"name": name, "error": f"{type(exc).__name__}: {exc}"})
                continue
            truncated = len(text) > SOURCE_CHARS
            if truncated:
                text = text[:SOURCE_CHARS] + f"\n[truncated at {SOURCE_CHARS} characters; read_file reads the rest]"
            origin, sources = _locations(request, {"path": str(path)})
            kept = retain(
                "tool",
                json.dumps({"tool": READ, "source": name, "arguments": origin}, ensure_ascii=False),
                text,
                sources,
            )
            rows.append({"name": name, "evidence": kept["evidence"], "truncated": truncated, "result": text})
        return {"sources": rows, **allowance()}

    return read_sources


def _collection_tools(definitions, handlers, *, researching, guided):
    """Append the collection's own tools to the native definitions and return the handlers that are offered."""
    offered = {}
    if READ in handlers:
        offered[READ] = handlers[READ]
        definitions.append(
            tool(
                READ,
                "Read several listed sources in one call; each becomes its own evidence entry.",
                schema_for(SourceRead),
            )
        )
    offered[ASK] = handlers[ASK]
    definitions.append(
        tool(
            ASK, "Ask the user for missing information; unanswered questions remain explicit.", schema_for(UserQuestion)
        )
    )
    if researching:
        offered[RESEARCH] = handlers[RESEARCH]
        definitions.append(
            tool(
                RESEARCH, "Delegate a focused external research task and return its evidence.", schema_for(ResearchTask)
            )
        )
        if guided:
            offered[GUIDANCE] = handlers[GUIDANCE]
            definitions.append(
                tool(
                    GUIDANCE,
                    "Inspect optional guidance for an identified research need before grouping.",
                    schema_for(ResearchNeed),
                )
            )
    definitions.append(
        tool(SUBMIT, "Submit the supported expert description and its remaining questions.", schema_for(Description))
    )
    return offered


def _native_definitions(registry):
    definitions = registry.get_definitions() if registry is not None else []
    reserved = {SUBMIT, REVIEW, RESEARCH, ASK, GUIDANCE, READ}
    if reserved & {entry["function"]["name"] for entry in definitions}:
        raise ValueError("native tools collide with information collection tools")

    return definitions


class _Calls:
    """Preserve native call metadata across an exchange whose callbacks receive only argument dictionaries."""

    def __init__(self, provider):
        self.provider = provider
        self.calls, self.errors = {}, {}
        self.blocked = False

    async def chat_with_retry(self, **kwargs):
        response = await self.provider.chat_with_retry(**kwargs)
        self.blocked = False
        self.calls = {id(call.arguments): call for call in response.tool_calls}
        errors = {row["tool_call_id"]: row["error"] for row in argument_errors(response)}
        self.errors = {key: errors[call.id] for key, call in self.calls.items() if call.id in errors}
        return response

    def check(self, arguments):
        if self.blocked:
            raise ValueError("an earlier native call blocked this batch; inspect its refusal before continuing")
        if id(arguments) in self.errors:
            raise ValueError(self.errors[id(arguments)])

    def metadata(self, arguments):
        call = self.calls.get(id(arguments))
        return call.run_meta if call is not None else None


class _ResearchAttempts:
    """Keep attempt handles and revision allowances under host control."""

    def __init__(self, limits):
        self.limits = limits
        self.entries = {}
        self.groups = 0

    def allocate(self, previous_attempt):
        previous = self.entries.get(previous_attempt) if previous_attempt else None
        if previous_attempt and previous is None:
            raise ValueError("unknown research attempt; use a handle returned by delegate_research")
        if previous is not None:
            if previous["superseded"] or previous["accepted"]:
                raise ValueError("only the latest unaccepted attempt of a group can be revised")
            group, revision = previous["group"], previous["revision"] + 1
            if revision > self.limits.research_revisions:
                raise ValueError(
                    "research revision allowance exhausted; preserve the gap or change acquisition channel"
                )
            previous["superseded"] = True
        else:
            if self.groups >= self.limits.research_tasks:
                raise ValueError("research task budget exhausted; preserve the unanswered question")
            self.groups += 1
            group, revision = self.groups, 0
        attempt = f"research-{len(self.entries) + 1}"
        state = {"group": group, "revision": revision, "accepted": False, "superseded": False}
        self.entries[attempt] = state
        return attempt, state

    async def acquire(self, assignment, research, retain, record, allowance, trace):
        attempt = assignment.attempt
        state = self.entries[attempt]
        feedback = {"attempt": attempt, "revisions_remaining": self.limits.research_revisions - state["revision"]}
        try:
            result = await _answer(research, assignment)
            review = (
                Review.model_validate(result["review"]) if isinstance(result, dict) and "review" in result else None
            )
        except (ExchangeError, ResearchError, OSError, TimeoutError, ValueError) as exc:
            failure = {"error": str(exc) or type(exc).__name__, "error_type": type(exc).__name__}
            state.update(failure)
            record("research-attempts.json", self.entries)
            trace.append({"label": "collect", "event": "research.failed", **failure})
            return {
                **failure,
                **feedback,
                "questions": assignment.brief.questions,
                **allowance(),
            }
        if review is not None:
            state["review"] = review.model_dump(mode="json")
            record("research-attempts.json", self.entries)
        if review is not None and not review.accepted:
            return {
                **feedback,
                "review": review.model_dump(mode="json"),
                "refused": result.get("refused", []),
                "unanswered": result.get("unanswered", []),
                "instruction": "Decide whether to revise this attempt, use another channel, or retain an explicit gap.",
                **allowance(),
            }
        state["accepted"] = True
        record("research-attempts.json", self.entries)
        retained = retain(
            "research",
            assignment.brief.model_dump_json(),
            json.dumps(result, ensure_ascii=False),
            _source_addresses(result),
            assignment.dimensions,
        )
        return {**retained, **feedback}


async def collect_information(
    provider,
    request: Request,
    *,
    registry=None,
    research=None,
    guidance=None,
    ask=None,
    model=None,
    review_model=None,
    effort="high",
    limits=CollectionLimits(),
    records: Path | None = None,
) -> Result:
    """Return reviewed information or explicit incompleteness; never install or modify a Harness.

    `registry` is the host's native Raven tool registry. `research` receives a ResearchAssignment and returns a
    serializable, source-backed result. Optional `guidance` is called lazily once when a research group uses it.
    `ask` receives a Question and returns text or None when unanswered.
    The caller owns visibility, tool resources and their lifecycle.
    """
    trace, evidence, pending = [], list(request.previous.evidence if request.previous else ()), {}
    started = time.monotonic()
    snapshot = None
    attempts = _ResearchAttempts(limits)
    result = None
    queries_used = 0
    calls = _Calls(provider)
    guides, guidance_loaded, research_tasks = list(request.guidance), False, []
    if records is not None:
        records = Path(records)
        records.mkdir(parents=True, exist_ok=False)
        (records / "request.json").write_text(request.model_dump_json(indent=2))

    def record(name, value):
        if records is not None:
            (records / name).write_text(json.dumps(value, ensure_ascii=False, indent=2))

    def allowance():
        elapsed = time.monotonic() - started
        return {
            "research_groups_remaining": limits.research_tasks - attempts.groups,
            "seconds_remaining": max(0, round(limits.total_timeout - elapsed, 2)),
            "research_seconds_available": max(0, round(limits.research_window(elapsed), 2)),
        }

    def retain(channel, origin, content, sources=(), dimensions=()):
        known = {source.id for source in evidence}
        number = len(evidence) + 1
        while f"evidence-{number}" in known:
            number += 1
        source = Evidence(
            id=f"evidence-{number}",
            channel=channel,
            origin=origin,
            content=content,
            sources=sources,
            dimensions=dimensions,
        )
        evidence.append(source)
        record("evidence.json", [item.model_dump(mode="json") for item in evidence])
        return {"evidence": source.id, "result": content, **allowance()}

    objective = retain("request", "collection objective", request.objective)
    context = retain("request", "host context", json.dumps(request.context, ensure_ascii=False))
    answers = []
    if request.previous:
        questions = {question.id: question for question in request.previous.description.unresolved}
        for id, text in request.answers.items():
            answers.append(retain("user", questions[id].model_dump_json(), text, dimensions=(questions[id].dimension,)))
    definitions = _native_definitions(registry)

    def count_query():
        nonlocal queries_used
        if queries_used >= limits.queries:
            raise ValueError("acquisition budget exhausted; submit supported information and remaining questions")
        queries_used += 1

    def native(name):
        async def run(arguments):
            calls.check(arguments)
            count_query()
            try:
                async with asyncio.timeout(limits.timeout):
                    output = await registry.execute(name, arguments, run_meta=calls.metadata(arguments))
            except TimeoutError:
                output = f"Error: {name} exceeded the acquisition timeout"
            text = str(output)
            if getattr(output, "blocks_call", False):
                calls.blocked = True
            if call_failed(output):
                trace.append({"label": "collect", "event": "acquisition.failed", "tool": name, "error": text})
                return {"error": text}
            origin, sources = _locations(request, arguments)
            return retain("tool", json.dumps({"tool": name, "arguments": origin}, ensure_ascii=False), text, sources)

        return run

    async def prepare(arguments):
        nonlocal guidance_loaded
        calls.check(arguments)
        need = ResearchNeed.model_validate(arguments)
        if not set(need.dimensions) <= set(request.focus):
            raise ValueError("research preparation must stay inside the current focus")
        count_query()
        if not guidance_loaded:
            guidance_loaded = True
            try:
                if guidance is not None:
                    result = guidance()
                    result = await result if inspect.isawaitable(result) else result
                    guides.extend(ResearchGuide.model_validate(item) for item in result)
            except (ExchangeError, ResearchError, ValueError, OSError, TimeoutError) as exc:
                trace.append(
                    {
                        "label": "collect",
                        "event": "guidance.unavailable",
                        "error_type": type(exc).__name__,
                        "error": str(exc) or type(exc).__name__,
                    }
                )
        return {
            "guidance": [item.model_dump(mode="json") for item in guides],
            "purpose": "questions_only",
            **allowance(),
        }

    async def delegate(arguments):
        calls.check(arguments)
        task = ResearchTask.model_validate(arguments)
        if len(task.dimensions) != len(set(task.dimensions)) or not set(task.dimensions) <= set(request.focus):
            raise ValueError("research groups must name distinct dimensions within the current focus")
        available = {source.id: source for source in evidence}
        unknown = set(task.known_evidence) - available.keys()
        if unknown:
            raise ValueError(f"unknown research evidence: {sorted(unknown)}")
        if task.use_guidance and (guidance is not None or request.guidance) and not guidance_loaded:
            raise ValueError("call prepare_research and inspect its guidance before forming this group")
        window = _research_window(task, limits, time.monotonic() - started)
        count_query()
        attempt, _ = attempts.allocate(task.previous_attempt)
        assignment = ResearchAssignment(
            **task.model_dump(),
            known_information=tuple(available[id] for id in task.known_evidence),
            guidance=tuple(
                guide for guide in guides if task.use_guidance and set(guide.dimensions) & set(task.dimensions)
            ),
            attempt=attempt,
            remaining_seconds=window,
        )
        research_tasks.append(assignment.model_dump(mode="json"))
        record("research-tasks.json", research_tasks)
        record("research-attempts.json", attempts.entries)
        return await attempts.acquire(assignment, research, retain, record, allowance, trace)

    async def question(arguments):
        calls.check(arguments)
        question = UserQuestion.model_validate(arguments)
        count_query()
        item = Question(id=f"question-{uuid4().hex}", **question.model_dump())
        answer = await _answer(ask, item) if ask is not None else None
        if answer is None or not str(answer).strip():
            pending[item.id] = item
            record("questions.json", [item.model_dump(mode="json") for item in pending.values()])
            return {"unanswered": item.model_dump(mode="json")}
        return retain("user", item.model_dump_json(), str(answer))

    listed = {
        **request.context.get("interaction_sources", {}),
        **request.context.get("host_sources", {}),
    }

    handlers = {ASK: question, RESEARCH: delegate, GUIDANCE: prepare}
    if listed:
        handlers[READ] = _source_reader(request, listed, calls, count_query, retain, allowance)
    query = {entry["function"]["name"]: native(entry["function"]["name"]) for entry in definitions}
    query.update(
        _collection_tools(
            definitions,
            handlers,
            researching=research is not None and limits.research_tasks > 0,
            guided=guidance is not None or bool(request.guidance),
        )
    )
    conversation = messages(
        (PROMPTS / "collect.md").read_text(),
        {
            "objective": objective,
            "context": context,
            "focus": request.focus,
            "previous": request.previous.model_dump(mode="json") if request.previous else None,
            "answers": answers,
            "research_guidance_available": bool(request.guidance or guidance),
            "acquisition_allowance": {
                "research_groups": limits.research_tasks,
                "questions_per_group": limits.research_questions,
                "research_timeout_seconds": limits.research_timeout,
                "native_and_user_queries": limits.queries,
                "revisions_per_group": limits.research_revisions,
                "total_timeout_seconds": limits.total_timeout,
                "submission_reserve_seconds": limits.reserve,
            },
            "available_channels": {
                "native": registry is not None,
                "research": research is not None,
                "user": ask is not None,
            },
        },
    )

    def submit(arguments):
        calls.check(arguments)
        return _submission(request, evidence, pending, arguments)

    def reviewed(arguments):
        calls.check(arguments)
        return Review.model_validate(arguments)

    async def run():
        nonlocal result, snapshot
        reviews = []
        for attempt in range(1, limits.reviews + 1):
            spent = sum(row.get("label") == "collect" and row.get("event") == "model.call" for row in trace)
            if spent >= limits.calls:
                break
            _, snapshot = await exchange(
                calls,
                conversation,
                definitions,
                submit={SUBMIT: submit},
                query=query,
                model=model,
                effort=effort,
                max_calls=limits.calls - spent,
                timeout=limits.timeout,
                trace=trace,
                label="collect",
            )
            submission_id = conversation[-1]["tool_calls"][0]["id"]
            conversation.append(
                {"role": "tool", "tool_call_id": submission_id, "content": '{"status":"submitted_for_review"}'}
            )
            record(f"proposal-{attempt}.json", snapshot.model_dump(mode="json"))
            review_input = {
                "objective": request.objective,
                "context": request.context,
                "focus": request.focus,
                "previous": request.previous.description.model_dump(mode="json") if request.previous else None,
                "description": snapshot.description.model_dump(mode="json"),
                "evidence": _review_evidence(snapshot, research_tasks),
                "unanswered_user_questions": [item.model_dump(mode="json") for item in pending.values()],
                "answers": request.answers,
                "research_attempts": attempts.entries,
                "previous_reviews": reviews.copy(),
                "research_tasks": [
                    {key: value for key, value in task.items() if key != "known_information"} for task in research_tasks
                ],
            }
            _, review = await exchange(
                calls,
                messages((PROMPTS / "review_information.md").read_text(), review_input),
                [
                    tool(
                        REVIEW,
                        "Accept the description or identify concrete defects requiring revision.",
                        schema_for(Review),
                    )
                ],
                submit={REVIEW: reviewed},
                model=review_model or model,
                effort=effort,
                max_calls=limits.review_calls,
                timeout=limits.timeout,
                trace=trace,
                label="information.review",
            )
            record(f"review-{attempt}.json", review.model_dump(mode="json"))
            reviews.append(review.model_dump(mode="json"))
            record("reviews.json", reviews)
            result = _reviewed_result(request, snapshot, review)
            record("result.json", result.model_dump(mode="json"))
            record("status.json", {"status": result.status, "version": snapshot.identity})
            record("snapshot.json", snapshot.model_dump(mode="json"))
            if review.accepted:
                return result
            conversation.append(
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "review": review.model_dump(mode="json"),
                            "instruction": "Revise the description to address these defects.",
                        }
                    ),
                }
            )
        if result is not None:
            return result.model_copy(update={"stop_reason": "call_limit" if spent >= limits.calls else "review_limit"})
        raise ExchangeError("information collection exhausted its budget without a reviewed description", trace)

    try:
        async with asyncio.timeout(limits.total_timeout):
            result = await run()
        return result
    except TimeoutError:
        result = _unfinished_result(
            request,
            snapshot,
            evidence,
            pending,
            "time_limit",
            "The overall information collection deadline was reached.",
        )
        return result
    except (ExchangeError, ResearchError) as exc:
        spent = sum(row.get("label") == "collect" and row.get("event") == "model.call" for row in trace)
        result = _unfinished_result(
            request, snapshot, evidence, pending, "call_limit" if spent >= limits.calls else "error", str(exc)
        )
        return result
    except asyncio.CancelledError:
        result = _unfinished_result(
            request, snapshot, evidence, pending, "cancelled", "Information collection was cancelled before completion."
        )
        raise
    finally:
        record("trace.json", trace)
        record("conversation.json", conversation)
        record("research-attempts.json", attempts.entries)
        if result is not None:
            record("result.json", result.model_dump(mode="json"))
            record("snapshot.json", result.snapshot.model_dump(mode="json"))
            record(
                "status.json",
                {
                    "status": result.status,
                    "stop_reason": result.stop_reason,
                    "version": result.snapshot.identity,
                    "seconds": time.monotonic() - started,
                },
            )
        record("evidence.json", [item.model_dump(mode="json") for item in evidence])
