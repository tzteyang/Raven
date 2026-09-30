"""Bind cross-strategy operations without exposing owner state or a reflective dispatcher."""

from ..harness.peers import StrategyPeers
from .calls import OperationGroup, interaction_mode, require_writable
from .observe import plain


class RuntimePeers(StrategyPeers):
    def __init__(self, recorder):
        self.recorder = recorder
        self.operations = OperationGroup()
        self._planning = None
        self._memory = None
        self._capability = None
        self._action = None

    def bind(self, *, planning=None, memory=None, capability=None, action=None):
        self._planning, self._memory, self._capability = planning, memory, capability
        self._action = action

    def read_plan(self):
        return self._planning.read() if self._planning is not None else None

    async def interact_planning(self, command, *, mode="command"):
        mode = interaction_mode(mode)
        if self._planning is None:
            raise ValueError("this Harness has no planning interaction operation")
        self.recorder.add(
            "strategy.peer_request", target="planning", operation="interact", arguments=command, mode=mode
        )
        result = await self._planning.interact(command, origin="strategy", mode=mode)
        self.recorder.add("strategy.peer_result", target="planning", operation="interact", result=result.reply)
        return plain(result.reply)

    async def interact_memory(self, command, *, mode="command"):
        mode = interaction_mode(mode)
        if self._memory is None:
            raise ValueError("this Harness has no memory interaction operation")
        self.recorder.add("strategy.peer_request", target="memory", operation="interact", arguments=command, mode=mode)
        result = await self._memory.interact(command, origin="strategy", mode=mode)
        self.recorder.add("strategy.peer_result", target="memory", operation="interact", result=result)
        return plain(result)

    def capabilities(self):
        return self._capability.read() if self._capability is not None else None

    async def request_action(self, command):
        require_writable()
        if self._action is None:
            raise ValueError("this Harness has no Action request operation")
        self.recorder.add("strategy.peer_request", target="action", operation="handle_request", arguments=command)
        result = await self._action.request(command, origin="strategy")
        self.recorder.add("strategy.peer_result", target="action", operation="handle_request", result=result)
        return plain(result)
