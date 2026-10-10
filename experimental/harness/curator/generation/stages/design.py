"""Develop selected entries into a checked mechanism before generating code."""

import json
from collections import Counter

from experimental.harness.contract import Declaration, Plan
from experimental.harness.contract.artifact import Selection
from experimental.harness.contract.attribution import Attribution
from experimental.harness.contract.commitments import check_design
from experimental.harness.curator.generation.context.collect import Context
from experimental.harness.curator.generation.context.render import tool

NAME = "submit_plan"


def _decoded(value):
    """A list some models send as JSON text instead of a list; anything else is left to validation."""
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except ValueError:
            return value
        return decoded if isinstance(decoded, list) else value
    return value


def materials(context: Context, selection: Selection) -> dict:
    """What design adds to the curation's materials: the current selection and its expanded contracts.

    A knowledge document that several selected contracts carry travels once, under `shared_knowledge`; each contract
    names it and keeps the full text only of what it alone carries. Listed references are deduplicated the same way
    under `shared_references`, each keeping one name to read it by, and a reference another selected contract
    inlines in full is not listed at all."""
    contracts = [context.declaration.target(name).describe() for name in selection.targets]
    carriers = Counter(item["source"] for contract in contracts for item in contract["knowledge"])
    shared = {}
    for contract in contracts:
        for item in contract["knowledge"]:
            if carriers[item["source"]] > 1:
                shared.setdefault(item["source"], item)
        contract["shared_knowledge"] = [item["source"] for item in contract["knowledge"] if item["source"] in shared]
        contract["knowledge"] = [item for item in contract["knowledge"] if item["source"] not in shared]
    inlined = set(carriers)
    listed = Counter(item["source"] for contract in contracts for item in contract["references"])
    shared_references = {}
    for contract in contracts:
        for item in contract["references"]:
            if listed[item["source"]] > 1 and item["source"] not in inlined:
                shared_references.setdefault(item["source"], item)
        contract["references"] = [
            item
            for item in contract["references"]
            if item["source"] not in shared_references and item["source"] not in inlined
        ]
    return {
        "selection": selection.model_dump(mode="json"),
        "selected_contracts": contracts,
        "shared_knowledge": list(shared.values()),
        "shared_references": list(shared_references.values()),
    }


def schema(declaration: Declaration, selection: Selection) -> dict:
    return declaration.restrict(selection.targets).plan_schema()


def output(declaration: Declaration) -> dict:
    """The design submission for the shared tool list; its schema admits any declared target."""
    return tool(
        NAME,
        "Submit a concrete design for exactly the selected targets, including effects and verification.",
        declaration.plan_schema(),
    )


def parse(context: Context, selection: Selection, attribution: Attribution, arguments: dict) -> Plan:
    """A design checked against the selection, with its commitment changes checked against the current
    commitments and the diagnosed inputs, and every added commitment given its id."""
    if isinstance(arguments, dict):
        arguments = {
            key: _decoded(value) if key in ("changes", "state", "commitments") else value
            for key, value in arguments.items()
        }
    declaration = context.declaration
    plan = declaration.parse_plan(arguments)
    if {change.target for change in plan.changes} != set(selection.targets):
        raise ValueError("design must cover exactly the current selection; revise selection first")
    untreated = [change.target for change in plan.changes if change.treatment is None]
    if untreated:
        raise ValueError(
            f"say for every change whether it modifies, replaces or adds a mechanism (treatment): {untreated}"
        )
    commitments = check_design(
        context.commitments,
        plan.commitments,
        surfaces=[target.name for target in declaration.targets],
        inputs=[diagnosis.about for diagnosis in attribution.diagnoses],
        selected=selection.targets,
        grounds=selection.grounds,
        authored=(context.facts.get("authored") or {}).get("values") or {},
    )
    return plan.model_copy(update={"commitments": commitments})
