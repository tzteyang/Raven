"""Review consistency across one Harness's strategies, retained behavior and executable design."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from experimental.harness.contract import Artifact
from experimental.harness.contract.declaration import schema_for
from experimental.harness.curator.generation.context.render import observation_index, tool
from experimental.harness.curator.generation.stages import design, implement
from experimental.harness.raven_adapter.inspection import fingerprint
from experimental.harness.raven_adapter.materialize import extend_artifact
from experimental.harness.raven_adapter.observe import plain

NAME = "submit_consistency_review"
Text = Annotated[str, Field(min_length=1)]


class Issue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    surfaces: tuple[str, ...] = Field(min_length=1)
    evidence: Text
    correction: Text
    blocking: bool


class ConsistencyReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    surfaces: dict[str, Text]
    interactions: Text
    issues: tuple[Issue, ...]
    limitations: tuple[Text, ...]


def output():
    return tool(
        NAME,
        "Check consistency across this Harness's strategies, retained behavior and executable design.",
        schema_for(ConsistencyReview),
    )


def materials(context, selection, candidate, validation):
    current = Artifact.model_validate(context.facts.get("authored") or {"values": {}})
    effective = extend_artifact(current, candidate.artifact)
    available = [target.name for target in context.declaration.targets]
    contracts = design.materials(context, selection.model_copy(update={"targets": tuple(available)}))
    commitments = implement.commitments_after(context, candidate.plan)
    targets = sorted(
        set(available)
        | current.values.keys()
        | effective.values.keys()
        | {item.surface for item in context.commitments if item.active}
        | {item["surface"] for item in commitments}
    )
    return {
        "candidate_id": fingerprint(
            plain(
                {
                    "candidate": candidate,
                    "effective": effective,
                    "commitments": commitments,
                    "validation": validation,
                }
            )
        ),
        "surfaces": targets,
        "selection": selection.model_dump(mode="json"),
        "plan": candidate.plan.model_dump(mode="json"),
        "effective_artifact": effective.model_dump(mode="json"),
        "commitments_after": commitments,
        "contracts": contracts["selected_contracts"],
        "shared_knowledge": contracts["shared_knowledge"],
        "shared_references": contracts["shared_references"],
        "changes": implement.changes(current.model_dump(mode="json"), candidate),
        "validation": {"errors": validation.errors, "observations": observation_index(validation.observations)},
    }


def schema(materials):
    result = schema_for(ConsistencyReview)
    result["properties"]["candidate_id"]["enum"] = [materials["candidate_id"]]
    result["properties"]["surfaces"] = {
        "type": "object",
        "properties": {name: {"type": "string", "minLength": 1} for name in materials["surfaces"]},
        "required": materials["surfaces"],
        "additionalProperties": False,
    }
    return result


def parse(value, materials):
    reviewed = ConsistencyReview.model_validate(value)
    if reviewed.candidate_id != materials["candidate_id"]:
        raise ValueError("consistency review must identify the current complete candidate")
    if set(reviewed.surfaces) != set(materials["surfaces"]):
        raise ValueError("consistency review must cover every surface, including unchanged and native behavior")
    if any(set(issue.surfaces) - reviewed.surfaces.keys() for issue in reviewed.issues):
        raise ValueError("consistency review issues must name surfaces in this Harness")
    return reviewed
