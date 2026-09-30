"""Require observed evidence in the current turn before accepting a final claim."""

from experimental.curator.harness.action import ActionDecision, ActionEvent
from experimental.curator.harness.strategies import ActionStrategy

REQUIRE_EVIDENCE = True


class Action(ActionStrategy[None, None]):
    def __init__(self, state):
        self.state = state

    async def handle_event(self, event: ActionEvent) -> ActionDecision:
        if event.kind == "outcome" and any(call.name == "evidence_probe" for call in event.proposed_calls):
            for row in reversed(event.messages):
                if row.get("role") == "tool" and row.get("name") == "evidence_probe":
                    if any(line.startswith("FACT:") for line in row.get("content", "").splitlines()):
                        self.state["evidence_turn"] = event.scope.turn_id
                    break
        if event.kind == "proposal" and event.stage == "reply" and REQUIRE_EVIDENCE:
            if event.scope.turn_id is None or self.state.get("evidence_turn") != event.scope.turn_id:
                if "revise" in event.allowed_controls:
                    self.state["retries"] = self.state.get("retries", 0) + 1
                    return ActionDecision(control="revise", feedback="Call evidence_probe before finishing.")
                return ActionDecision(control="finish", reply="Evidence was not obtained; the task remains incomplete.")
        if event.kind == "failure":
            self.state["recoveries"] = self.state.get("recoveries", 0) + 1
            return ActionDecision(control="finish", reply="Evidence was not obtained; the task remains incomplete.")
        return ActionDecision()


def create(state, task):
    return Action(state)
