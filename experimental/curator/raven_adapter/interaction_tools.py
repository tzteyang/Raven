"""Derive model tool schemas from concrete commands and dispatch to live owners."""

import json

from pydantic import ConfigDict, create_model

from raven.contracts.tool import Tool

from ..harness.declaration import parse_as, schema_for
from ..harness.interaction import InteractionMode
from .observe import plain


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
            request = parse_as(request_type, kwargs, strict=True)
            options = {"mode": request.mode} if modes else {}
            return json.dumps(plain(await invoke(request.request, **options)), ensure_ascii=False)

    return StrategyTool()
