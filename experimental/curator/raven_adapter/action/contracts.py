"""Select Action events, a model request entry and optional mandatory dispatch checks."""

from pydantic import Field, model_validator

from ...harness.action import EventKind
from ...harness.interaction import InteractionTool
from ..strategy import TaskBinding

TARGET = "action.strategy"


class ActionBinding(TaskBinding):
    """Bind the selected public operations to their actual native consumers.

    review can request bounded resampling but is not fail-closed enforcement.
    dispatch installs a native ToolGate calling the same live owner; gate errors
    refuse the call. Requests queue supported controls for the post-tool boundary,
    with requested/applied/rejected receipts rather than an invented execution.
    """

    events: tuple[EventKind, ...] = ("proposal",)
    tool: InteractionTool | None = None
    requests: bool = Field(
        default=False, description="Enable typed peer requests without requiring a model-facing tool."
    )
    dispatch: bool = Field(
        default=False,
        description="Install a native per-call ToolGate for mandatory dispatch checks. "
        "Requires proposal in events. The dispatch event supports continue/reject; "
        "native permissions remain independent and earlier refusals may prevent the gate from running.",
    )

    @model_validator(mode="after")
    def usable_operations(self):
        if len(self.events) != len(set(self.events)):
            raise ValueError("action event kinds must be unique")
        if self.dispatch and "proposal" not in self.events:
            raise ValueError("action dispatch checks require proposal events")
        return self
