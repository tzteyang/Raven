"""Derive model tool schemas from concrete commands and dispatch to live owners."""

import json

from pydantic import ConfigDict, create_model

from experimental.harness.contract.declaration import parse_as, schema_for
from experimental.harness.contract.interaction import InteractionMode
from experimental.harness.raven_adapter.observe import plain
from raven.contracts.tool import Tool


def interaction_tool(binding, command_type, invoke, *, modes=False):
    """Expose only business arguments; the receiver constructs the trusted envelope."""
    request_type = create_model(
        f"{binding.name.title()}Arguments",
        __config__=ConfigDict(extra="forbid"),
        request=(command_type, ...),
        **({"mode": (InteractionMode, "command")} if modes else {}),
    )

    class StrategyTool(Tool):
        name = binding.name
        description = binding.description
        parameters = schema_for(request_type)

        async def execute(self, **kwargs):
            # Models often send the nested command as a JSON string. The schema names the command by $ref, and the
            # registry's argument casting only parses strings declared "type": "object", so decode it here.
            if isinstance(kwargs.get("request"), str):
                try:
                    decoded = json.loads(kwargs["request"])
                except ValueError:
                    decoded = None
                if isinstance(decoded, dict):
                    kwargs = {**kwargs, "request": decoded}
            request = parse_as(request_type, kwargs, strict=True)
            options = {"mode": request.mode} if modes else {}
            return json.dumps(plain(await invoke(request.request, **options)), ensure_ascii=False)

    return StrategyTool()
