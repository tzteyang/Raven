"""Typed Action events, requests, control intentions and host application receipts."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from .interaction import InteractionRequest, InteractionScope
from .resources import EffectiveCapabilities

Control = Literal["continue", "reject", "revise", "finish"]
EventKind = Literal["input", "progress", "proposal", "outcome", "failure", "control"]


class GenerationOverrides(BaseModel):
    """Native-supported changes to one resampled call, within the reserved output allowance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    temperature: float | None = None
    max_tokens: int | None = Field(default=None, gt=0)
    reasoning_effort: str | None = None


class ProposedCall(BaseModel):
    """An intended call, never proof of execution.

    call_id is absent when the native per-call gate does not supply it. Identities
    belong to their host scope and batch, not to an entire historical archive.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    arguments: dict[str, JsonValue]
    call_id: str | None = None


class ActionDecision(BaseModel):
    """A control intention with separate diagnostics and model-visible guidance.

    continue is no intervention, not a permission grant. reject refuses the
    current dispatch; revise requests a bounded native resample; finish supplies
    a truthful terminal reply. The event/request states which are supported.
    A valid decision is still not evidence that the host applied it.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    control: Control = "continue"
    reason: str | None = None
    feedback: str | None = None
    reply: str | None = None
    guidance: str | None = None
    generation: GenerationOverrides | None = None

    @model_validator(mode="after")
    def meaningful_effect(self):
        if self.generation is not None and self.control != "revise":
            raise ValueError("generation overrides belong only to a native resample")
        if self.control in {"reject", "revise"} and not (self.feedback and self.feedback.strip()):
            raise ValueError("reject and revise require model-visible feedback")
        if self.control == "finish" and not (self.reply and self.reply.strip()):
            raise ValueError("finish requires a nonempty terminal reply")
        if self.control != "finish" and self.reply is not None:
            raise ValueError("a terminal reply belongs only to finish")
        if self.control not in {"reject", "revise"} and self.feedback is not None:
            raise ValueError("correction feedback belongs only to reject or revise")
        if self.control != "continue" and self.guidance is not None:
            raise ValueError("guidance requires a continuing model-input consumer")
        return self


class ControlReceipt(BaseModel):
    """The host's actual result for one requested control, separate from policy judgment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scope: InteractionScope
    control_id: str
    source_id: str
    control: Control
    status: Literal["requested", "applied", "rejected", "unsupported"]
    reason: str | None = None


class Event(BaseModel):
    """Host identity, applicable control effects and the evidence's current plan view."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scope: InteractionScope
    event_id: str
    allowed_controls: tuple[Control, ...]
    can_guide: bool = False
    plan: JsonValue = None


class ProgressEvent(Event):
    """A pre-decision observation. Offered definitions may still be normalized.

    previous_capabilities is the most recent actual model-call snapshot, not a
    promise about this next call. The request boundary publishes its final view
    separately; missing previous evidence is represented by None.
    """

    kind: Literal["progress"] = "progress"
    messages: list[dict[str, JsonValue]]
    offered_tools: list[dict[str, JsonValue]]
    previous_capabilities: EffectiveCapabilities | None = None
    iteration: int


class InputEvent(Event):
    """Native inbound text before model input assembly; only supported early controls apply."""

    kind: Literal["input"] = "input"
    text: str


class ProposalEvent(Event):
    """A proposed batch, one validated dispatch, or a candidate reply."""

    kind: Literal["proposal"] = "proposal"
    stage: Literal["batch", "dispatch", "reply"]
    calls: tuple[ProposedCall, ...] = ()
    text: str | None = None
    capabilities: EffectiveCapabilities | None = None

    @model_validator(mode="after")
    def proposal_shape(self):
        if self.stage == "reply" and (self.calls or self.text is None):
            raise ValueError("a reply proposal requires text and no tool calls")
        if self.stage == "dispatch" and len(self.calls) != 1:
            raise ValueError("a dispatch proposal contains exactly one call")
        if self.stage == "batch" and not self.calls:
            raise ValueError("a batch proposal requires tool calls")
        return self


class OutcomeEvent(Event):
    """Actual transcript evidence after tool execution; inspect results rather than inferring success."""

    kind: Literal["outcome"] = "outcome"
    messages: list[dict[str, JsonValue]]
    proposed_calls: tuple[ProposedCall, ...]
    capabilities: EffectiveCapabilities | None = None


class FailureEvent(Event):
    """A host-reported interruption; terminal recovery may support only a reply."""

    kind: Literal["failure"] = "failure"
    reason: str
    terminal: bool
    messages: list[dict[str, JsonValue]]


class ControlEvent(Event):
    """Report applied/rejected control without recursively scheduling another control."""

    kind: Literal["control"] = "control"
    receipt: ControlReceipt


ActionEvent = Annotated[
    InputEvent | ProgressEvent | ProposalEvent | OutcomeEvent | FailureEvent | ControlEvent, Field(discriminator="kind")
]


class ActionInteraction[CommandT](InteractionRequest[CommandT]):
    """An agent/peer request with the host's supported control effects.

    The tool exposes CommandT alone. reply in ActionResponse is the domain
    answer; its decision is a request to the host, whose receipt states whether
    it has been applied. Requests cannot choose their own control allowance.
    """

    allowed_controls: tuple[Control, ...]


class ActionResponse[ReplyT](BaseModel):
    """A domain answer plus an optional control request, validated independently."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reply: ReplyT
    decision: ActionDecision = Field(default_factory=ActionDecision)
