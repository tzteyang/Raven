"""Answer preparation questions as the simulated party without exposing its private sources."""

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from ..curator.generation.context.render import tool
from ..curator.harness.declaration import schema_for
from ..iteration.compartment import BoundaryError, Guard
from ..iteration.exchange import exchange, messages
from ..research.scenario import release_guard
from ..scenario import contents
from ..scenario.sealed import Sealed, sealed_for


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str | None = None
    reason: str


class PartyAnswers:
    """An optional user-answer callback; adoption is a party choice, never an information review verdict."""

    def __init__(self, provider, scenario, knows, released, *, records: Path, model=None, timeout=300):
        for name in knows:
            if name not in scenario.materials or not scenario.visible(name, "party"):
                raise ValueError(f"party cannot answer from material: {name}")
        self.provider = Guard("party", sealed_for(scenario, "party")).provider(provider)
        self.scenario, self.knows, self.released = scenario, tuple(knows), released
        self.records, self.model, self.timeout = Path(records), model, timeout

    async def __call__(self, question):
        packet = {
            "question": question.model_dump(mode="json"),
            "materials": {name: contents(self.scenario.materials[name].path)[0] for name in self.knows},
        }
        _, answer = await exchange(
            self.provider,
            messages(
                "Answer this preparation question as the interacting party, using only your supplied material. "
                "For adoption, address the exact proposal, with limits if needed. Do not invent an organisational "
                "choice or confirm a public claim merely because it sounds plausible. Return null text when you "
                "cannot answer. Give only the answer, not private documents, tests or their identifiers.",
                packet,
            ),
            [tool("answer_question", "Answer or leave the question unresolved.", schema_for(Answer))],
            submit={"answer_question": Answer.model_validate},
            model=self.model,
            timeout=self.timeout,
        )
        names = self.released() if callable(self.released) else self.released
        hidden, visible = [], []
        for name, material in self.scenario.materials.items():
            rows = visible if name in names else hidden
            for text in contents(material.path)[0].values():
                rows.extend(text.splitlines())
        try:
            release_guard(self.scenario, names).check(answer.text, "party.answer")
            if answer.text and Sealed.of(hidden, visible=visible).hits(answer.text):
                raise BoundaryError("curator", "party.answer", ["<private source line>"])
        except BoundaryError:
            answer = Answer(text=None, reason="The proposed answer contains information outside the release scope.")
        self.records.mkdir(parents=True, exist_ok=True)
        identity = hashlib.sha256(question.model_dump_json().encode()).hexdigest()
        (self.records / f"{identity}.json").write_text(
            json.dumps({"question": question.model_dump(mode="json"), "answer": answer.model_dump(mode="json")})
        )
        return answer.text
