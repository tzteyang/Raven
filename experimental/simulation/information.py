"""Answer preparation questions as the simulated counterpart without exposing its private sources."""

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, field_validator

from experimental.curator.generation.context.render import tool
from experimental.curator.harness.declaration import schema_for
from experimental.iteration.compartment import BoundaryError, Guard
from experimental.iteration.exchange import exchange, messages
from experimental.research.scenario import release_guard
from experimental.scenario import contents
from experimental.scenario.sealed import Sealed, sealed_for


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str | None = None
    reason: str

    @field_validator("text")
    @classmethod
    def _unanswered(cls, text):
        """No answer, however the model spelled it: a model leaving the text null sometimes writes the string."""
        return None if text is None or text.strip().lower() in ("", "null") else text


class CounterpartAnswers:
    """An optional user-answer callback; adoption is a counterpart choice, never an information review verdict."""

    def __init__(self, provider, scenario, knows, released, *, records: Path, model=None, effort=None, timeout=300):
        for name in knows:
            if name not in scenario.materials or not scenario.visible(name, "counterpart"):
                raise ValueError(f"counterpart cannot answer from material: {name}")
        self.provider = Guard("counterpart", sealed_for(scenario, "counterpart")).provider(provider)
        self.scenario, self.knows, self.released = scenario, tuple(knows), released
        self.records, self.model, self.effort, self.timeout = Path(records), model, effort, timeout

    async def __call__(self, question):
        packet = {
            "question": question.model_dump(mode="json"),
            "materials": {name: contents(self.scenario.materials[name].path)[0] for name in self.knows},
        }
        _, answer = await exchange(
            self.provider,
            messages(
                "You are the interacting counterpart: the person who handed this work over to a new employee. The "
                "question comes from the side preparing that employee, not from a customer, so answer as the "
                "counterpart speaking to a colleague, plainly and in the language of your material, using only your "
                "supplied material. For adoption, address the exact proposal, with limits if needed. Do not invent an "
                "organisational choice or confirm a public claim merely because it sounds plausible. When your "
                "material does not answer the question, return null text and say why in the reason; text that only "
                "says you cannot answer is not an answer. Give only the answer, not private documents, tests or their "
                "identifiers.",
                packet,
            ),
            [tool("answer_question", "Answer or leave the question unresolved.", schema_for(Answer))],
            submit={"answer_question": Answer.model_validate},
            model=self.model,
            effort=self.effort,
            timeout=self.timeout,
        )
        names = self.released() if callable(self.released) else self.released
        hidden, visible = [], []
        for name, material in self.scenario.materials.items():
            rows = visible if name in names else hidden
            for text in contents(material.path)[0].values():
                rows.extend(text.splitlines())
        try:
            release_guard(self.scenario, names).check(answer.text, "counterpart.answer")
            if answer.text and Sealed.of(hidden, visible=visible).hits(answer.text):
                raise BoundaryError("curator", "counterpart.answer", ["<private source line>"])
        except BoundaryError:
            answer = Answer(text=None, reason="The proposed answer contains information outside the release scope.")
        self.records.mkdir(parents=True, exist_ok=True)
        identity = hashlib.sha256(question.model_dump_json().encode()).hexdigest()
        (self.records / f"{identity}.json").write_text(
            json.dumps({"question": question.model_dump(mode="json"), "answer": answer.model_dump(mode="json")})
        )
        return answer.text
