"""Collect and review expert information through fixed stages the host runs in order.

Read the supplied material, assess it, ask the user once when a user channel exists, plan research groups when a
research channel exists, run the groups concurrently in bounded waves, compose the description, review it and repair
it once. Each stage is one structured exchange with its own call cap and timeout; the model decides content, never the
sequence, and a channel that is not configured has no stage.
"""

import asyncio
import inspect
import json
import math
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from raven.agent.tools.registry import call_failed

from ..curator.generation.context.render import tool
from ..curator.harness.declaration import schema_for
from ..iteration.exchange import ExchangeError, exchange, messages
from ..model_calls import MalformedArgumentsError, argument_errors
from .information import (
    Assessment,
    Description,
    Evidence,
    Question,
    Request,
    ResearchGuide,
    ResearchPlan,
    Result,
    Review,
    Section,
    Snapshot,
)
from .researchers import ResearchError
from .voice import prompt
from .waves import Attempts, gaps, run_wave

ASSESS = "submit_assessment"
PLAN = "submit_research_plan"
SUBMIT = "submit_information"
REVIEW = "review_information"
SOURCE_CHARS = 30_000
SOURCES_CHARS = 240_000


@dataclass(frozen=True)
class CollectionLimits:
    """Per-stage caps; `total_timeout` bounds the whole collection and `reserve` is kept for composing and review.

    A stage's time cap covers its retried replies too: a planning call at high effort on a large evidence packet,
    retried once for malformed arguments, outlasted two minutes, and a planning stage that times out skips research.

    `grace_calls` is how many undelivered replies a stage retries without charging its cap: a reply with no tool
    call, or a submission whose arguments could not be parsed or do not fit the tool's schema
    (`experimental.iteration.exchange.undelivered`).
    """

    total_timeout: float = 3600
    timeout: float = 300
    reserve: float = 900
    assessment_calls: int = 4
    assessment_timeout: float = 300
    native_queries: int = 6
    plan_calls: int = 2
    plan_timeout: float = 300
    research_tasks: int = 3
    research_questions: int = 2
    research_window: float = 1800
    research_waves: int = 1
    wave_minimum: float = 600
    research_revisions: int = 1
    verification_reserve: float = 150
    editorial_minimum: float = 300
    acquisition_minimum: float = 600
    compose_calls: int = 3
    compose_timeout: float = 600
    reviews: int = 2
    review_calls: int = 3
    guidance_calls: int = 3
    guidance_queries: int = 12
    grace_calls: int = 2

    def __post_init__(self):
        counts = (
            self.assessment_calls,
            self.plan_calls,
            self.compose_calls,
            self.reviews,
            self.review_calls,
            self.guidance_calls,
            self.guidance_queries,
            self.research_questions,
        )
        if any(value < 1 for value in counts):
            raise ValueError("stage call, review and question limits must be positive")
        if min(self.research_tasks, self.research_waves, self.research_revisions, self.native_queries) < 0:
            raise ValueError("research tasks, waves, revisions and native queries must be nonnegative")
        if self.grace_calls < 0:
            raise ValueError("grace calls must be nonnegative")
        seconds = (
            self.total_timeout,
            self.timeout,
            self.assessment_timeout,
            self.plan_timeout,
            self.compose_timeout,
            self.research_window,
            self.wave_minimum,
            self.editorial_minimum,
            self.acquisition_minimum,
        )
        if any(not math.isfinite(value) or value <= 0 for value in seconds):
            raise ValueError("stage timeouts and research windows must be positive and finite")
        if any(not math.isfinite(value) or value < 0 for value in (self.reserve, self.verification_reserve)):
            raise ValueError("reserves must be nonnegative and finite")
        if self.verification_reserve >= self.editorial_minimum:
            raise ValueError("the verification reserve must be smaller than the editorial minimum")

    def wave_window(self, elapsed: float) -> float:
        """Seconds each group of a wave may take before the reserve begins."""
        return min(self.research_window, self.total_timeout - elapsed - self.reserve)

    def acquisition_window(self, window: float) -> float:
        """The part of a research window the researcher may spend; the rest verifies quotes and reviews."""
        return max(window - self.verification_reserve, window / 2)


class StageTimeoutError(TimeoutError):
    def __init__(self, stage):
        super().__init__(f"the {stage} stage exceeded its time cap")
        self.stage = stage


async def _answer(callback, value):
    answer = callback(value)
    return await answer if inspect.isawaitable(answer) else answer


async def _together(jobs) -> list:
    """The jobs' results, run at once; the first to fail stops the others and is raised."""
    try:
        async with asyncio.TaskGroup() as group:
            tasks = [group.create_task(job) for job in jobs]
    except ExceptionGroup as failed:
        raise failed.exceptions[0] from failed
    return [task.result() for task in tasks]


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


def _native_definitions(registry):
    definitions = registry.get_definitions() if registry is not None else []
    reserved = {ASSESS, PLAN, SUBMIT, REVIEW}
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
            raise MalformedArgumentsError(self.errors[id(arguments)])

    def metadata(self, arguments):
        call = self.calls.get(id(arguments))
        return call.run_meta if call is not None else None


async def _stage(name, timeout, awaitable):
    try:
        async with asyncio.timeout(timeout):
            return await awaitable
    except TimeoutError as exc:
        raise StageTimeoutError(name) from exc


QUOTES = str.maketrans(dict.fromkeys("'\u2018\u2019\u201c\u201d\u300c\u300d\u300e\u300f", '"'))


def _plain(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).translate(QUOTES).split())


def _asking(group, offered):
    """`group` with the question of every need it serves in its brief, as the assessment wrote it, after the
    planner's own questions. A group answers the needs it names: a planner that sharpens a need's question keeps
    the original beside it, and one that names a need but asks about something else still has it asked. A question
    the planner already wrote out, in other quotes or with its reason after it, is not asked twice."""
    asked = [_plain(question) for question in group.brief.questions]
    added = tuple(
        offered[ref]
        for ref in group.serves
        if offered[ref] is not None and not any(_plain(offered[ref]) in question for question in asked)
    )
    if not added:
        return group
    return group.model_copy(
        update={"brief": group.brief.model_copy(update={"questions": (*group.brief.questions, *added)})}
    )


class _Collection:
    """The state one collection carries from stage to stage: evidence, open questions, research outcomes, trace."""

    def __init__(
        self,
        provider,
        request,
        *,
        registry,
        research,
        guidance,
        ask,
        wait_for_input,
        model,
        review_model,
        effort,
        limits,
        records,
    ):
        self.request, self.registry, self.research, self.guidance, self.ask = request, registry, research, guidance, ask
        self.wait_for_input, self.model, self.review_model, self.effort, self.limits = (
            wait_for_input,
            model,
            review_model,
            effort,
            limits,
        )
        self.records = Path(records) if records is not None else None
        self.calls = _Calls(provider)
        self.started = time.monotonic()
        self.trace, self.pending, self.outcomes, self.conversation = [], {}, [], []
        self.evidence = list(request.previous.evidence if request.previous else ())
        self.guides = list(request.guidance)
        self.attempts = Attempts()
        self.snapshot = None
        self.queries_used = 0
        self.channels = {
            "native": registry is not None,
            "research": research is not None and limits.research_tasks > 0,
            "user": ask is not None,
        }
        self.definitions = _native_definitions(registry)
        if self.records is not None:
            self.records.mkdir(parents=True, exist_ok=False)
            (self.records / "request.json").write_text(request.model_dump_json(indent=2))
        self.objective = self.retain("request", "collection objective", request.objective)
        self.context = self.retain("request", "host context", json.dumps(request.context, ensure_ascii=False))
        self.answers = []
        if request.previous:
            questions = {question.id: question for question in request.previous.description.unresolved}
            for id, text in request.answers.items():
                kept = self.retain("user", questions[id].model_dump_json(), text, dimensions=(questions[id].dimension,))
                self.answers.append(kept)
        self.sources = self.read_sources()

    def record(self, name, value):
        if self.records is not None:
            (self.records / name).write_text(json.dumps(value, ensure_ascii=False, indent=2))

    def elapsed(self):
        return time.monotonic() - self.started

    def retain(self, channel, origin, content, sources=(), dimensions=()):
        known = {source.id for source in self.evidence}
        number = len(self.evidence) + 1
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
        self.evidence.append(source)
        self.record("evidence.json", [item.model_dump(mode="json") for item in self.evidence])
        return {"evidence": source.id, "result": content}

    def inventory(self):
        return [source.model_dump(mode="json") for source in self.evidence]

    def read_sources(self):
        """Read the listed interaction sources once; each becomes evidence, bounded per file and in total."""
        rows, total = [], 0
        for name, source in self.request.context.get("interaction_sources", {}).items():
            path = Path(source["path"])
            try:
                text = path.read_text(errors="replace")
            except OSError as exc:
                rows.append({"name": name, "error": f"{type(exc).__name__}: {exc}"})
                continue
            if total >= SOURCES_CHARS:
                rows.append({"name": name, "chars": len(text), "read": False, "path": str(path)})
                continue
            truncated = len(text) > SOURCE_CHARS
            if truncated:
                text = text[:SOURCE_CHARS] + f"\n[truncated at {SOURCE_CHARS} characters; read_file reads the rest]"
            total += len(text)
            origin, addresses = _locations(self.request, {"path": str(path)})
            kept = self.retain(
                "tool",
                json.dumps({"stage": "read", "source": name, "arguments": origin}, ensure_ascii=False),
                text,
                addresses,
            )
            rows.append(
                {
                    "name": name,
                    "evidence": kept["evidence"],
                    "chars": len(text),
                    "truncated": truncated,
                    "read": True,
                    "text": text,
                }
            )
        self.record("sources.json", [{key: value for key, value in row.items() if key != "text"} for row in rows])
        return rows

    def native(self, name):
        async def run(arguments):
            self.calls.check(arguments)
            if self.queries_used >= self.limits.native_queries:
                raise ValueError("native query allowance exhausted; submit the assessment from what was read")
            self.queries_used += 1
            try:
                async with asyncio.timeout(self.limits.timeout):
                    output = await self.registry.execute(name, arguments, run_meta=self.calls.metadata(arguments))
            except TimeoutError:
                output = f"Error: {name} exceeded the acquisition timeout"
            text = str(output)
            if getattr(output, "blocks_call", False):
                self.calls.blocked = True
            if call_failed(output):
                self.trace.append({"label": "assess", "event": "acquisition.failed", "tool": name, "error": text})
                return {"error": text}
            origin, addresses = _locations(self.request, arguments)
            return self.retain(
                "tool", json.dumps({"tool": name, "arguments": origin}, ensure_ascii=False), text, addresses
            )

        return run

    def assessed(self, arguments):
        self.calls.check(arguments)
        assessment = Assessment.model_validate(arguments)
        if {row.dimension for row in assessment.coverage} != set(self.request.focus):
            raise ValueError(f"assess exactly the dimensions in focus: {', '.join(self.request.focus)}")
        unknown = {id for row in assessment.coverage for id in row.evidence} - {source.id for source in self.evidence}
        if unknown:
            raise ValueError(f"unknown evidence: {sorted(unknown)}")
        if assessment.questions and not self.channels["user"]:
            raise ValueError("no user channel is open: state the assumption in the coverage reason instead of asking")
        if assessment.research_needs and not self.channels["research"]:
            raise ValueError("no research channel is open: record the gap in the coverage reason instead")
        return assessment

    async def assess(self):
        tools = [
            *self.definitions,
            tool(ASSESS, "Submit the assessment of the supplied material.", schema_for(Assessment)),
        ]
        query = {entry["function"]["name"]: self.native(entry["function"]["name"]) for entry in self.definitions}
        packet = {
            "objective": self.objective,
            "context": self.context,
            "focus": self.request.focus,
            "previous": self.request.previous.model_dump(mode="json") if self.request.previous else None,
            "answers": self.answers,
            "channels": self.channels,
            "native_queries": self.limits.native_queries if self.channels["native"] else 0,
            "sources": self.sources,
            "host_sources": self.request.context.get("host_sources", {}),
        }
        _, assessment = await exchange(
            self.calls,
            messages(prompt("assess.md"), packet),
            tools,
            submit={ASSESS: self.assessed},
            query=query,
            model=self.model,
            effort=self.effort,
            max_calls=self.limits.assessment_calls,
            grace=self.limits.grace_calls,
            timeout=self.limits.timeout,
            trace=self.trace,
            label="assess",
        )
        self.record("assessment.json", assessment.model_dump(mode="json"))
        return assessment

    async def ask_once(self, assessment):
        """Every question to the user: all at once when `ask` takes them `together` (a page listing them), otherwise
        one after another (a terminal reading one line at a time)."""
        questions = [
            Question(id=f"question-{uuid4().hex}", blocking=self.wait_for_input, **item.model_dump())
            for item in assessment.questions
        ]
        self.pending.update((question.id, question) for question in questions)
        rows = [{**question.model_dump(mode="json"), "answered": False} for question in questions]
        self.record("questions.json", rows)

        async def answered(index, question):
            answer = await _answer(self.ask, question)
            if answer is not None and str(answer).strip():
                kept = self.retain("user", question.model_dump_json(), str(answer), dimensions=(question.dimension,))
                del self.pending[question.id]
                rows[index].update(answered=True, evidence=kept["evidence"])
            self.record("questions.json", rows)

        if getattr(self.ask, "together", False):
            await _together(answered(index, question) for index, question in enumerate(questions))
        else:
            for index, question in enumerate(questions):
                await answered(index, question)
        self.trace.append({"label": "ask", "event": "asked", "questions": len(rows), "unanswered": len(self.pending)})

    async def load_guidance(self):
        if self.guidance is None:
            return
        try:
            loaded = self.guidance()
            loaded = await loaded if inspect.isawaitable(loaded) else loaded
            self.guides.extend(ResearchGuide.model_validate(item) for item in loaded)
        except (ExchangeError, ResearchError, ValueError, OSError, TimeoutError) as exc:
            self.trace.append(
                {
                    "label": "plan",
                    "event": "guidance.unavailable",
                    "error_type": type(exc).__name__,
                    "error": str(exc) or type(exc).__name__,
                }
            )

    def planned(self, arguments, offered):
        self.calls.check(arguments)
        plan = ResearchPlan.model_validate(arguments)
        if len(plan.groups) > self.limits.research_tasks:
            raise ValueError(f"at most {self.limits.research_tasks} research groups; defer the rest")
        known = {source.id for source in self.evidence}
        for group in plan.groups:
            stray = set(group.serves) - set(offered)
            if stray:
                raise ValueError(
                    f"a research group answers only the listed refs {sorted(offered)}, got {sorted(stray)}; "
                    "what only the business itself can settle is the user's to answer, not a research group's"
                )
            if not set(group.dimensions) <= set(self.request.focus):
                raise ValueError("research groups must stay inside the current focus")
            if len(group.brief.questions) > self.limits.research_questions:
                raise ValueError(f"a research group takes at most {self.limits.research_questions} questions; split it")
            unknown = set(group.known_evidence) - known
            if unknown:
                raise ValueError(f"unknown research evidence: {sorted(unknown)}")
        return plan.model_copy(update={"groups": tuple(_asking(group, offered) for group in plan.groups)})

    async def plan(self, assessment, wave, window):
        needs = [
            {"ref": f"need-{number}", **row.model_dump(mode="json")}
            for number, row in enumerate(assessment.research_needs, 1)
        ]
        open_points = [
            row if row.get("channel") == "user" else {"ref": f"gap-{number}", **row}
            for number, row in enumerate(gaps(self.outcomes), 1)
        ]
        # The question of each need a group serves goes into its brief (`_asking`); an open point carries none.
        offered = {row["ref"]: row["question"] for row in needs} | {
            row["ref"]: None for row in open_points if "ref" in row
        }
        packet = {
            "objective": self.request.objective,
            "focus": self.request.focus,
            "reading": assessment.reading,
            "coverage": [row.model_dump(mode="json") for row in assessment.coverage],
            "research_needs": needs,
            "evidence": self.inventory(),
            "guidance": [item.model_dump(mode="json") for item in self.guides],
            "allowance": {
                "groups": self.limits.research_tasks,
                "questions_per_group": self.limits.research_questions,
                "window_seconds_per_group": round(window),
                "wave": wave,
            },
            "previous_wave": {"outcomes": self.outcomes, "gaps": open_points} if self.outcomes else None,
        }
        _, plan = await exchange(
            self.calls,
            messages(prompt("plan.md"), packet),
            [tool(PLAN, "Submit the research groups to run concurrently.", schema_for(ResearchPlan))],
            submit={PLAN: lambda arguments: self.planned(arguments, offered)},
            model=self.model,
            effort=self.effort,
            max_calls=self.limits.plan_calls,
            grace=self.limits.grace_calls,
            timeout=self.limits.timeout,
            trace=self.trace,
            label="plan",
        )
        self.record(f"plan-{wave}.json", plan.model_dump(mode="json"))
        return plan

    async def research_waves(self, assessment):
        for wave in range(1, self.limits.research_waves + 1):
            if wave > 1 and not gaps(self.outcomes):
                return
            window = self.limits.wave_window(self.elapsed())
            if window < self.limits.wave_minimum:
                self.trace.append({"label": "plan", "event": "wave.skipped", "wave": wave, "window": round(window, 1)})
                return
            try:
                plan = await _stage("plan", self.limits.plan_timeout, self.plan(assessment, wave, window))
            except StageTimeoutError as exc:
                self.trace.append({"label": "plan", "event": "stage.timeout", "wave": wave, "error": str(exc)})
                return
            if not plan.groups:
                return
            self.outcomes.extend(
                await run_wave(
                    plan.groups,
                    wave=wave,
                    research=self.research,
                    limits=self.limits,
                    window=self.limits.wave_window(self.elapsed()),
                    evidence=self.evidence,
                    guides=self.guides,
                    retain=self.retain,
                    record=self.record,
                    trace=self.trace,
                    attempts=self.attempts,
                )
            )

    def submitted(self, arguments):
        self.calls.check(arguments)
        description = Description.model_validate(arguments)
        unresolved = {item.id: item for item in description.unresolved}
        missing = [id for id in self.pending if id not in unresolved]
        if missing:
            raise ValueError(f"carry every open user question with its assumption: {missing}")
        carried = {item.id for item in self.request.previous.description.unresolved} if self.request.previous else set()
        rebuilt = []
        for item in description.unresolved:
            if item.id in self.pending:
                asked = self.pending[item.id]
                item = asked.model_copy(update={"assumption": item.assumption, "blocking": self.wait_for_input})
            elif item.id not in carried:
                item = item.model_copy(update={"blocking": False})
            if item.id not in carried and not item.blocking and not item.assumption.strip():
                raise ValueError(f"open point {item.id} needs the assumption the description applies meanwhile")
            rebuilt.append(item)
        description = description.model_copy(update={"unresolved": tuple(rebuilt)})
        self.check_focus(description)
        return Snapshot(description=description, evidence=tuple(self.evidence), manifest=self.request.manifest)

    def check_focus(self, description):
        previous = self.request.previous
        if previous is None:
            return
        sections = {section.dimension: section for section in previous.description.sections}
        for section in description.sections:
            if section.dimension not in self.request.focus and section != sections[section.dimension]:
                raise ValueError(f"preserve the section outside focus: {section.dimension}")
        kept = {item.id: item for item in description.unresolved}
        for item in previous.description.unresolved:
            if item.dimension not in self.request.focus and kept.get(item.id) != item:
                raise ValueError(f"preserve the open point outside focus: {item.id}")

    def reviewed(self, arguments):
        self.calls.check(arguments)
        return Review.model_validate(arguments)

    def brief_context(self):
        """The request context without the source listings, which the evidence inventory already carries."""
        return {
            key: value
            for key, value in self.request.context.items()
            if key not in ("interaction_sources", "host_sources", "exploration")
        }

    def open_compose(self, assessment):
        self.conversation.extend(
            messages(
                prompt("compose.md"),
                {
                    "objective": self.request.objective,
                    "context": self.brief_context(),
                    "focus": self.request.focus,
                    "previous": self.request.previous.model_dump(mode="json") if self.request.previous else None,
                    "answers": self.request.answers,
                    "reading": assessment.reading,
                    "coverage": [row.model_dump(mode="json") for row in assessment.coverage],
                    "evidence": self.inventory(),
                    "research": {"outcomes": self.outcomes, "gaps": gaps(self.outcomes)},
                    "open_user_questions": [item.model_dump(mode="json") for item in self.pending.values()],
                    "user_questions_may_block": self.wait_for_input,
                    "channels": self.channels,
                },
            )
        )

    async def compose(self, attempt):
        _, self.snapshot = await _stage(
            "compose",
            self.limits.compose_timeout,
            exchange(
                self.calls,
                self.conversation,
                [tool(SUBMIT, "Submit the expert description and its open points.", schema_for(Description))],
                submit={SUBMIT: self.submitted},
                model=self.model,
                effort=self.effort,
                max_calls=self.limits.compose_calls,
                grace=self.limits.grace_calls,
                timeout=self.limits.compose_timeout,
                trace=self.trace,
                label="compose",
            ),
        )
        submission_id = self.conversation[-1]["tool_calls"][0]["id"]
        self.conversation.append(
            {"role": "tool", "tool_call_id": submission_id, "content": '{"status":"submitted_for_review"}'}
        )
        self.record(f"proposal-{attempt}.json", self.snapshot.model_dump(mode="json"))
        return self.snapshot

    async def review(self, snapshot, reviews, attempt):
        review_input = {
            "objective": self.request.objective,
            "context": self.brief_context(),
            "focus": self.request.focus,
            "previous": self.request.previous.description.model_dump(mode="json") if self.request.previous else None,
            "description": snapshot.description.model_dump(mode="json"),
            "evidence": [
                source.model_dump(mode="json")
                for source in snapshot.evidence
                if source.channel != "request" or source.id in snapshot.description.references
            ],
            "open_user_questions": [item.model_dump(mode="json") for item in self.pending.values()],
            "user_questions_may_block": self.wait_for_input,
            "answers": self.request.answers,
            "research": {"outcomes": self.outcomes, "gaps": gaps(self.outcomes)},
            "previous_reviews": reviews.copy(),
        }
        _, review = await exchange(
            self.calls,
            messages(prompt("review_information.md"), review_input),
            [
                tool(
                    REVIEW,
                    "Accept the description or identify concrete defects requiring revision.",
                    schema_for(Review),
                )
            ],
            submit={REVIEW: self.reviewed},
            model=self.review_model or self.model,
            effort=self.effort,
            max_calls=self.limits.review_calls,
            grace=self.limits.grace_calls,
            timeout=self.limits.timeout,
            trace=self.trace,
            label="information.review",
        )
        self.record(f"review-{attempt}.json", review.model_dump(mode="json"))
        reviews.append(review.model_dump(mode="json"))
        self.record("reviews.json", reviews)
        return review

    async def compose_and_review(self, assessment):
        self.open_compose(assessment)
        reviews, result = [], None
        for attempt in range(1, self.limits.reviews + 1):
            snapshot = await self.compose(attempt)
            review = await self.review(snapshot, reviews, attempt)
            result = _reviewed_result(self.request, snapshot, review)
            self.record("result.json", result.model_dump(mode="json"))
            self.record("snapshot.json", snapshot.model_dump(mode="json"))
            if review.accepted:
                return result
            self.conversation.append(
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "review": review.model_dump(mode="json"),
                            "instruction": "Correct these defects and submit again.",
                        }
                    ),
                }
            )
        return result.model_copy(update={"stop_reason": "review_limit"})

    async def run(self):
        assessment = await _stage("assessment", self.limits.assessment_timeout, self.assess())
        # Research serves what the business cannot settle (`planned`), so it need not wait for the user's answers:
        # both run at once, and a later wave's plan reads the answers kept by then.
        await _together(
            [
                *([self.ask_once(assessment)] if self.channels["user"] and assessment.questions else []),
                *([self.researched(assessment)] if self.channels["research"] and assessment.research_needs else []),
            ]
        )
        return await self.compose_and_review(assessment)

    async def researched(self, assessment):
        await self.load_guidance()
        await self.research_waves(assessment)

    def unfinished(self, reason, error):
        return _unfinished_result(self.request, self.snapshot, self.evidence, self.pending, reason, error)

    def close(self, result):
        self.record("trace.json", self.trace)
        self.record("conversation.json", self.conversation)
        if result is not None:
            self.record("result.json", result.model_dump(mode="json"))
            self.record("snapshot.json", result.snapshot.model_dump(mode="json"))
            self.record(
                "status.json",
                {
                    "status": result.status,
                    "stop_reason": result.stop_reason,
                    "version": result.snapshot.identity,
                    "seconds": self.elapsed(),
                },
            )
        self.record("evidence.json", [item.model_dump(mode="json") for item in self.evidence])


async def collect_information(
    provider,
    request: Request,
    *,
    registry=None,
    research=None,
    guidance=None,
    ask=None,
    wait_for_input=False,
    model=None,
    review_model=None,
    effort="high",
    limits=CollectionLimits(),
    records: Path | None = None,
) -> Result:
    """Return reviewed information or explicit incompleteness; never install or modify a Harness.

    `registry` is the host's native Raven tool registry, offered to the assessment stage as bounded queries.
    `research` receives a ResearchAssignment and returns the reviewed attempt. Optional `guidance` is called once
    before planning when research needs exist. `ask` receives a Question and returns text or None; without it there
    is no asking stage. `wait_for_input` keeps unanswered user questions blocking so the result waits for input.
    The caller owns visibility, tool resources and their lifecycle.
    """
    collection = _Collection(
        provider,
        request,
        registry=registry,
        research=research,
        guidance=guidance,
        ask=ask,
        wait_for_input=wait_for_input,
        model=model,
        review_model=review_model,
        effort=effort,
        limits=limits,
        records=records,
    )
    result = None
    try:
        async with asyncio.timeout(limits.total_timeout):
            result = await collection.run()
        return result
    except StageTimeoutError as exc:
        result = collection.unfinished("time_limit", str(exc))
        return result
    except TimeoutError:
        result = collection.unfinished("time_limit", "The overall information collection deadline was reached.")
        return result
    except (ExchangeError, ResearchError) as exc:
        result = collection.unfinished("error", str(exc))
        return result
    except asyncio.CancelledError:
        result = collection.unfinished("cancelled", "Information collection was cancelled before completion.")
        raise
    finally:
        collection.close(result)
