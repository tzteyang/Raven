"""A typed proposal guard and inert tools for behavioral validation and repair."""

from experimental.curator.harness.action import ActionDecision, ActionEvent
from experimental.curator.harness.strategies import ActionStrategy
from raven.contracts.tool import Tool


class Guard(ActionStrategy[None, None]):
    async def handle_event(self, event: ActionEvent) -> ActionDecision:
        if event.kind == "proposal" and event.stage == "batch":
            names = [call.name for call in event.calls]
            if "blocked_probe" in names:
                return ActionDecision(control="revise", feedback="Use safe_probe instead.")
        return ActionDecision()


def create(state, task):
    return Guard()


class Probe(Tool):
    description = "Record that this permitted test tool actually ran."
    parameters = {"type": "object", "properties": {}, "additionalProperties": False}

    def __init__(self, name):
        self._name = name

    @property
    def name(self):
        return self._name

    async def execute(self, **kwargs):
        return self.name + "_EXECUTED"


def blocked(context):
    return Probe("blocked_probe")


def safe(context):
    return Probe("safe_probe")
