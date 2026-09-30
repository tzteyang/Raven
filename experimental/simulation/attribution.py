"""Which owner rules a finished run's requirements and interventions concern, read by a model against the rules.

The owner's verdicts are private (`experimental.simulation.agency`), so the Analyst grounds its requirements on the
owner's words, and a requirement names a rule's id only when an assessor the Analyst can see measured that rule.
For the others a model reads each requirement against the rules and names the rules it restates
(`read_requirements`); the record links them with kind `reading`, and a change that addresses the requirement
answers those rules. The value judge then credits a rule with an intervention only when the intervention was for
that rule (see `experimental.simulation.value`): a mechanism's reasons are its own words, so a model reads each
reason against the rules its target was sedimented for and names the rules it enforces (`attribute`); a block for
another rule, or a block of work the rule allows, enforces none. Both readings are kept in `attribution.json` beside
the records; without it no requirement links by reading and the judge credits no intervention to any rule.
"""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from ..curator.generation.context.render import tool
from ..curator.harness.declaration import schema_for
from ..iteration.exchange import exchange, messages
from .value import candidates

NAME = "submit_attribution"
CONCERNS = "submit_requirement_rules"
RESULT = "attribution.json"
_PROMPT = Path(__file__).resolve().parent / "prompts" / "attribution.md"
_REQUIREMENTS = Path(__file__).resolve().parent / "prompts" / "requirements.md"


class Concern(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    rules: list[str] = Field(description="Ids of the rules this requirement restates; empty when it restates none.")


class Concerns(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirements: list[Concern]


async def read_requirements(record: dict, provider, *, model=None, timeout=180) -> dict[str, list[str]]:
    """The rules each requirement restates, by requirement id, for the requirements whose grounds name no rule; a
    repeated requirement is read in its latest wording."""
    rules = [{"id": entry["criterion"], "rule": entry.get("rule", "")} for entry in record.get("ledger", [])]
    asked: dict[str, dict] = {}
    for item in record.get("rounds", []):
        for requirement in item["analysis"]["requirements"]:
            if requirement.get("id") and requirement.get("link") != "grounds":
                asked[requirement["id"]] = {
                    key: requirement.get(key, "") for key in ("id", "situation", "behavior", "acceptance")
                }
    if not asked or not rules:
        return {}
    known = {rule["id"] for rule in rules}

    def accept(arguments):
        parsed = Concerns.model_validate(arguments)
        if sorted(concern.id for concern in parsed.requirements) != sorted(asked):
            raise ValueError(f"give exactly one entry per requirement id: {sorted(asked)}")
        for concern in parsed.requirements:
            if set(concern.rules) - known:
                raise ValueError(f"{concern.id} may name only the rules given: {sorted(known)}")
        return parsed

    _, parsed = await exchange(
        provider,
        messages(_REQUIREMENTS.read_text(), {"rules": rules, "requirements": list(asked.values())}),
        [tool(CONCERNS, "Submit, for every requirement id, the rules it restates.", schema_for(Concerns))],
        submit={CONCERNS: accept},
        model=model,
        max_calls=4,
        timeout=timeout,
        label="requirements",
    )
    return {concern.id: sorted(concern.rules) for concern in parsed.requirements}


class Link(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    rules: list[str] = Field(description="Ids of the rules this intervention enforces; empty when it enforces none.")


class Links(BaseModel):
    model_config = ConfigDict(extra="forbid")

    links: list[Link]


async def attribute(record: dict, provider, *, model=None, timeout=180) -> dict:
    """`links` maps each intervention reason (by `value.reason_key`) to the rules it enforces."""
    found = candidates(record)
    if not found:
        return {"links": {}, "interventions": 0}
    ids = {f"r{index}": key for index, key in enumerate(sorted(found), start=1)}
    asked = {rule for slot in found.values() for rule in slot["rules"]}
    packet = {
        "rules": [
            {"id": entry["criterion"], "rule": entry.get("rule", "")}
            for entry in record.get("ledger", [])
            if entry["criterion"] in asked
        ],
        "interventions": [
            {
                "id": number,
                "mechanism": found[key]["target"],
                "harness": found[key]["scope"],
                "reason": found[key]["reason"],
                "times": found[key]["count"],
                "may_enforce": sorted(found[key]["rules"]),
            }
            for number, key in ids.items()
        ],
    }

    def accept(arguments):
        parsed = Links.model_validate(arguments)
        if sorted(link.id for link in parsed.links) != sorted(ids):
            raise ValueError(f"give exactly one entry per intervention id: {sorted(ids)}")
        for link in parsed.links:
            allowed = found[ids[link.id]]["rules"]
            if set(link.rules) - allowed:
                raise ValueError(f"{link.id} may name only {sorted(allowed)}")
        return parsed

    _, parsed = await exchange(
        provider,
        messages(_PROMPT.read_text(), packet),
        [tool(NAME, "Submit, for every intervention id, the rules it enforces.", schema_for(Links))],
        submit={NAME: accept},
        model=model,
        max_calls=4,
        timeout=timeout,
        label="attribution",
    )
    return {"links": {ids[link.id]: sorted(link.rules) for link in parsed.links}, "interventions": len(ids)}


async def write(root: Path, provider, *, scenario_dir=None, model=None, timeout=180) -> dict:
    """Read a finished run's requirements, then its interventions, against the rules of the scenario it ran and keep
    both beside its records; the interventions are read on the record the requirement reading already links, since
    only a mechanism sedimented for a rule is asked about it."""
    from .record import build_record

    root = Path(root)
    concerns = await read_requirements(build_record(root, scenario_dir), provider, model=model, timeout=timeout)
    (root / RESULT).write_text(json.dumps({"requirements": concerns}, ensure_ascii=False, indent=2))
    record = build_record(root, scenario_dir)
    result = {"requirements": concerns, **await attribute(record, provider, model=model, timeout=timeout)}
    (root / RESULT).write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result
