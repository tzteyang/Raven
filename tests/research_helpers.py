"""Controlled model responses and independent Scenario fixtures for information tests."""

import json
from pathlib import Path

from raven.contracts.llm_provider import LLMResponse, ToolCallRequest

CHECK = "Every quote the assistant sends states the total price of the whole order as one figure."


class Provider:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    async def chat_with_retry(self, messages=None, tools=None, model=None, **kwargs):
        kwargs = {**kwargs, "messages": messages, "tools": tools, "model": model}
        self.requests.append(kwargs)
        answer = self.responses.pop(0)
        return answer(kwargs) if callable(answer) else answer


def response(name, arguments):
    return LLMResponse(content=None, tool_calls=[ToolCallRequest(name, name, arguments)])


def research_brief(question="How should evidence and uncertainty be handled?", **overrides):
    return {
        "background": "Project review with incomplete evidence.",
        "known_information": ["The owner needs an evidence-based expert description."],
        "questions": [question],
        "scope": "Public evidence-handling practice; organisation policy is excluded.",
        "deliverable": "Supported methods, synthesis, disagreements and limitations.",
        "acceptance": ["Claims have sources and applicable limits; missing evidence stays explicit."],
        **overrides,
    }


def rejections(request) -> list[str]:
    rows = [json.loads(row["content"]) for row in request["messages"] if row["role"] == "tool"]
    return [row["error"] for row in rows if isinstance(row, dict) and "error" in row]


def make_scenario(root: Path, *, facts=True, instances=True, checks=True, norms=True) -> Path:
    """A shop scenario: a norm, a norm only the counterpart holds, a fact, an exemplar with a binary file beside its
    document, a counterexample, one check and a two-step plan of what the counterpart hands over."""
    (root / "personas").mkdir(parents=True)
    (root / "profile.md").write_text("You answer the tea shop's customers.\n")
    (root / "personas" / "walk-in.md").write_text("A customer asks what an afternoon tea for two would cost.\n")

    def material(name, text, kind, **extra):
        folder = root / "materials" / name
        folder.mkdir(parents=True)
        (folder / "SKILL.md").write_text(f"---\nname: {name}\ndescription: The shop's {name}.\n---\n\n{text}\n")
        for file, content in extra.items():
            (folder / file.replace("_", ".")).write_bytes(content)
        return kind

    kinds = {}
    if norms:
        kinds["sop"] = {"kind": material("sop", "Greet the customer and quote from the price list only.", "norm")}
        kinds["owner-policy"] = {
            "kind": material("owner-policy", "Discounts above ten percent need the owner's approval.", "norm"),
            "visibility": ["counterpart"],
        }
    if facts:
        kinds["prices"] = {"kind": material("prices", "Tea costs three. Cake costs five.", "fact")}
    if instances:
        kinds["good-reply"] = {
            "kind": material(
                "good-reply",
                "Hello, I am the shop's assistant. Tea for two: six. Cake for two: ten. Together: sixteen.",
                "exemplar",
                reply_pdf=b"%PDF-1.4",
            )
        }
        kinds["bad-reply"] = {
            "kind": material("bad-reply", "Sure, I can give you half off everything!", "counterexample")
        }
    handed = [name for name in kinds if name != "owner-policy"]
    contract, spec = {"materials": kinds}, {"initial": sorted(handed)}
    first = [name for name in ("sop", "prices") if name in kinds]
    spec["plans"] = {"two": [first, [name for name in handed if name not in first]]} if instances and first else {}
    if checks:
        spec["criteria"] = [{"id": "quote-total", "check": CHECK}]
        contract["checks"] = {"quote-total": {"derived_from": ["sop", "owner-policy"] if norms else []}}
    (root / "contract.json").write_text(json.dumps(contract))
    (root / "scenario.json").write_text(json.dumps(spec))
    return root
