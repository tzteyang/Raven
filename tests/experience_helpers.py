"""Create local evidence and provider responses for experience behavior tests."""

from uuid import uuid4

from experimental.harness.experience.admission import ProcessCheckReceipt
from experimental.harness.experience.contracts import (
    EvidenceLink,
    EvidenceView,
    ExperienceCondition,
    ExperienceEvent,
    ExperienceProposal,
    ExperienceReview,
    RecordOrigin,
    digest,
)
from experimental.harness.experience.state import BuildState
from raven.contracts.llm_provider import LLMResponse, ToolCallRequest


def event(number="one", scope="project"):
    origin = RecordOrigin(
        access_scope=scope, run_id=number, lineage_id=number, record_id=number, revision_before="before"
    )
    view = EvidenceView(
        reference="event-" + origin.event_id(),
        situation="A mechanism produced a result that was not consumed.",
        treatment="Connected the result to the actual consumer.",
        process_result="checked",
        activation="applied",
        held=True,
        basis="observation",
        comparability="comparable",
        observations=("The consumer applied the result.",),
    )
    return ExperienceEvent(origin=origin, source_digest=digest(number), revision_after="after", view=view)


def proposal(value, guidance="Verify and repair the actual consumer path, then observe its applied effect."):
    return ExperienceProposal(
        condition=ExperienceCondition(situation="A mechanism runs but its result is not consumed.", phase="design"),
        guidance=guidance,
        evidence=(EvidenceLink(reference=value.view.reference, relation="supports"),),
    )


def accept(index=0):
    return ExperienceReview(proposal_index=index, decision="accept")


def reviewed(store, sources, method=None, *, critic=None):
    method = method or proposal(sources[0])
    identities = {"builder": {}, "critic": {"rule": "test-critic"} if critic is None else critic}
    handle, _ = store.open_task(
        uuid4().hex, digest([source.model_dump() for source in sources]), identities, sources, ttl=60
    )
    state = BuildState(status="complete", proposals=(method,), reviews=(accept(),))
    _, completed = store.save(handle, state, ttl=60, finish=True, accepted=((method, accept()),))
    return completed.accepted[0]


def process_checked(store, reference, sources, *, passed=True):
    for source in sources:
        store.record_process_check(
            ProcessCheckReceipt(
                access_scope=source.origin.access_scope,
                method=reference,
                event_reference=source.view.reference,
                event_version=store.event_version(source),
                passed=passed,
                observations=("The fixture's exact method property was checked against the recorded artifact.",),
            )
        )


def response(name, arguments):
    return LLMResponse(
        content=None, tool_calls=[ToolCallRequest("call-1", name, arguments)], usage={"total_tokens": 12}
    )


class Provider:
    def __init__(self, *responses):
        self.responses, self.requests = list(responses), []

    def get_default_model(self):
        return "local-test-model"

    async def chat(self, **kwargs):
        self.requests.append(kwargs)
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value
