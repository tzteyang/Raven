"""Expert information and evidence exchanged before one Curator invocation."""

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Dimension = Literal["role", "tasks", "knowledge", "abilities", "methods", "judgement", "cases", "performance"]
DIMENSIONS: tuple[Dimension, ...] = (
    "role",
    "tasks",
    "knowledge",
    "abilities",
    "methods",
    "judgement",
    "cases",
    "performance",
)
LABELS = {
    "role": "Professional role and boundaries",
    "tasks": "Tasks and working context",
    "knowledge": "Professional knowledge",
    "abilities": "Required abilities",
    "methods": "Working methods and rules",
    "judgement": "Experienced judgement",
    "cases": "Practice cases and examples",
    "performance": "Performance and learning",
}


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Section(_Model):
    dimension: Dimension
    text: str = ""
    coverage: Literal["sufficient", "partial", "missing", "not_applicable"]
    reason: str = Field(min_length=1)
    evidence: tuple[str, ...] = ()

    @model_validator(mode="after")
    def supported_content(self):
        if self.coverage == "sufficient" and (not self.text.strip() or not self.evidence):
            raise ValueError("a sufficient section needs content and evidence")
        return self


class Resource(_Model):
    name: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    requirements: tuple[str, ...] = ()
    availability: Literal["available", "unavailable", "unknown"]
    evidence: tuple[str, ...] = ()


class Question(_Model):
    id: str = Field(min_length=1)
    dimension: Dimension
    question: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    blocking: bool = True
    channel: Literal["user", "research", "native"] = "user"
    proposal: str | None = None


class Description(_Model):
    title: str = Field(min_length=1)
    sections: tuple[Section, ...]
    resources: tuple[Resource, ...] = ()
    unresolved: tuple[Question, ...] = ()

    @model_validator(mode="after")
    def complete_dimensions(self):
        dimensions = [section.dimension for section in self.sections]
        if len(dimensions) != len(DIMENSIONS) or set(dimensions) != set(DIMENSIONS):
            raise ValueError(f"describe each dimension exactly once: {', '.join(DIMENSIONS)}")
        ids = [question.id for question in self.unresolved]
        if len(ids) != len(set(ids)):
            raise ValueError("unresolved question ids must be unique")
        return self

    @property
    def references(self) -> frozenset[str]:
        return frozenset(ref for row in (*self.sections, *self.resources) for ref in row.evidence)


class Evidence(_Model):
    id: str = Field(min_length=1)
    channel: Literal["request", "tool", "research", "user"]
    origin: str = Field(min_length=1)
    content: str = Field(min_length=1)
    sources: tuple[str, ...] = ()
    dimensions: tuple[Dimension, ...] = ()


class Manifest(_Model):
    """Bind a reviewed result to its task, released inputs and observed environment."""

    task: str
    objective: str
    scope: str = "root"
    sources: dict[str, str] = Field(default_factory=dict)
    context: str = ""
    environment: str = ""
    excluded_sources: tuple[str, ...] = ()


class ResearchBrief(_Model):
    """Semantic work handed to a researcher without collection bookkeeping."""

    background: str = Field(min_length=1)
    known_information: tuple[str, ...] = ()
    questions: tuple[str, ...] = Field(min_length=1)
    scope: str = Field(min_length=1)
    deliverable: str = Field(min_length=1)
    acceptance: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def meaningful_content(self):
        if any(not value.strip() for value in (*self.questions, *self.acceptance)):
            raise ValueError("research questions and acceptance criteria must not be blank")
        return self


class ResearchGuide(_Model):
    """Optional questions for a research group, never evidence establishing an expert's knowledge."""

    topic: str = Field(min_length=1)
    dimensions: tuple[Dimension, ...] = Field(min_length=1)
    questions: tuple[str, ...] = Field(min_length=1)
    rationale: str = Field(min_length=1)
    sources: tuple[str, ...] = ()

    @model_validator(mode="after")
    def meaningful_group(self):
        if len(self.dimensions) != len(set(self.dimensions)) or any(
            not question.strip() for question in self.questions
        ):
            raise ValueError("guidance needs distinct dimensions and nonempty questions")
        return self


class Review(_Model):
    accepted: bool
    reason: str = Field(min_length=1)
    issues: tuple[str, ...] = ()

    @model_validator(mode="after")
    def consistent_verdict(self):
        if self.accepted and self.issues:
            raise ValueError("an accepted review cannot carry unresolved revision issues")
        if not self.accepted and not self.issues:
            raise ValueError("a rejected review must explain what needs revision")
        return self


class Snapshot(_Model):
    description: Description
    evidence: tuple[Evidence, ...]
    manifest: Manifest | None = None

    @model_validator(mode="after")
    def known_evidence(self):
        ids = [source.id for source in self.evidence]
        if len(ids) != len(set(ids)):
            raise ValueError("evidence ids must be unique")
        unknown = self.description.references - set(ids)
        if unknown:
            raise ValueError(f"unknown evidence: {sorted(unknown)}")
        return self

    @property
    def identity(self) -> str:
        payload = json.dumps(self.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
        return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


class Answers(_Model):
    """User answers addressed to questions in one exact information snapshot."""

    version: str
    answers: dict[str, str]


class Request(_Model):
    objective: str = Field(min_length=1)
    focus: tuple[Dimension, ...] = DIMENSIONS
    previous: Snapshot | None = None
    context: dict = Field(default_factory=dict)
    guidance: tuple[ResearchGuide, ...] = ()
    answers: dict[str, str] = Field(default_factory=dict)
    answers_version: str | None = None
    scope: str = "root"
    manifest: Manifest | None = None

    @model_validator(mode="after")
    def focused_request(self):
        if not self.focus or len(self.focus) != len(set(self.focus)):
            raise ValueError("focus must name distinct dimensions")
        if self.previous is None and set(self.focus) != set(DIMENSIONS):
            raise ValueError("initial collection must consider every dimension")
        questions = (
            {question.id: question for question in self.previous.description.unresolved} if self.previous else {}
        )
        for id, text in self.answers.items():
            if id not in questions or questions[id].dimension not in self.focus or not text.strip():
                raise ValueError("answers must address known questions inside the current focus with nonempty text")
        if self.answers and self.previous is not None and self.answers_version != self.previous.identity:
            raise ValueError("answers must name the exact previous information version")
        return self


class Result(_Model):
    snapshot: Snapshot
    review: Review
    previous: str | None = None
    changed_dimensions: tuple[Dimension, ...] = DIMENSIONS
    resources_changed: bool = True
    questions_changed: bool = True
    reviewed_version: str = ""
    stop_reason: Literal["completed", "time_limit", "call_limit", "review_limit", "error", "cancelled"] = "completed"

    @model_validator(mode="after")
    def bind_review(self):
        if self.reviewed_version and self.reviewed_version != self.snapshot.identity:
            raise ValueError("review belongs to another information version")
        object.__setattr__(self, "reviewed_version", self.snapshot.identity)
        return self

    @property
    def ready(self) -> bool:
        return (
            self.stop_reason == "completed"
            and self.review.accepted
            and not any(q.blocking for q in self.snapshot.description.unresolved)
        )

    @property
    def status(self) -> str:
        if self.stop_reason != "completed" or not self.review.accepted:
            return "incomplete"
        if any(q.blocking and q.channel != "user" for q in self.snapshot.description.unresolved):
            return "incomplete"
        return "ready" if self.ready else "needs_input"


def render(snapshot: Snapshot) -> str:
    """Render the reviewed description without copying packages or raw acquisition transcripts."""
    description = snapshot.description
    sections = {section.dimension: section for section in description.sections}
    lines = [f"# {description.title}", "", f"Information version: {snapshot.identity}", ""]
    for dimension in DIMENSIONS:
        section = sections[dimension]
        lines.extend([f"## {LABELS[dimension]}", "", section.text or section.reason, ""])
        lines.extend([f"Coverage: {section.coverage}. {section.reason}", ""])
        if section.evidence:
            lines.extend([f"Evidence: {', '.join(section.evidence)}.", ""])
    if description.resources:
        lines.extend(["## Tools and operating prerequisites", ""])
        for resource in description.resources:
            lines.extend(
                [
                    f"### {resource.name}",
                    "",
                    resource.purpose,
                    f"Availability: {resource.availability}.",
                    f"Evidence: {', '.join(resource.evidence) or 'not supplied'}.",
                    *(f"- {item}" for item in resource.requirements),
                    "",
                ]
            )
    if description.unresolved:
        lines.extend(["## Remaining questions", ""])
        for question in description.unresolved:
            lines.extend([f"- [{question.channel}] {question.question} {question.reason}"])
    lines.extend(["", "## Evidence references", ""])
    for source in snapshot.evidence:
        if source.id in description.references:
            lines.extend([f"### {source.id}", "", f"Acquisition channel: {source.channel}."])
            lines.append(f"Origin: {source.origin}")
            if source.channel == "user":
                lines.append(f"User answer: {source.content}")
            lines.extend(f"- {address}" for address in source.sources)
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"
