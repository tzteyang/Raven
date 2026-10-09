"""Make bounded single-submission model calls without execution tools or hidden retries."""

import asyncio
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from raven.contracts.llm_provider import LLMProvider
from raven.contracts.tool import RAW_ARGUMENTS_KEY
from raven.security.trust import wrap_untrusted

from .contracts import digest

T = TypeVar("T", bound=BaseModel)
PROMPTS = Path(__file__).parent / "prompts"


@dataclass(frozen=True)
class ModelLimits:
    max_input_bytes: int = 65536
    max_output: int = 12000
    timeout: float = 60

    def __post_init__(self):
        if (
            type(self.max_input_bytes) is not int
            or self.max_input_bytes < 1
            or type(self.max_output) is not int
            or self.max_output < 1
            or not math.isfinite(self.timeout)
            or self.timeout <= 0
        ):
            raise ValueError("model limits require positive finite bounds")


class ModelCallError(RuntimeError):
    def __init__(self, kind: str, correction: str, *, called: bool = False):
        super().__init__(correction)
        self.kind, self.called = kind, called


class ModelClient:
    def __init__(
        self,
        provider: LLMProvider,
        prompt: str,
        *,
        model: str | None = None,
        limits: ModelLimits = ModelLimits(),
        effort: str | None = None,
        trace: list | None = None,
    ):
        self.provider, self.prompt = provider, prompt
        default = getattr(provider, "get_default_model", None)
        self.model = model or (default() if default else None)
        self.limits, self.effort = limits, effort
        self.trace = trace if trace is not None else []

    def identity(self, schema: type[BaseModel], tool_name: str) -> dict:
        return {
            "implementation": type(self).__name__,
            "model": self.model,
            "effort": self.effort,
            "prompt_digest": digest(self.prompt),
            "schema_digest": digest(schema.model_json_schema()),
            "tool": tool_name,
            "max_output": self.limits.max_output,
            "tool_choice": "auto",
        }

    async def submit(
        self,
        packet: dict,
        schema: type[T],
        name: str,
        *,
        correction: str | None = None,
        submission_schema: dict | None = None,
    ) -> T:
        messages = [
            {"role": "system", "content": self.prompt},
            {
                "role": "user",
                "content": wrap_untrusted(json.dumps(packet, ensure_ascii=False), source="experience evidence"),
            },
        ]
        if correction:
            messages.append({"role": "user", "content": "Submission correction: " + correction})
        tools = [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": "Submit one complete structured result.",
                    "parameters": schema.model_json_schema() if submission_schema is None else submission_schema,
                },
            }
        ]
        payload = {"messages": messages, "tools": tools}
        size = len(json.dumps(payload, ensure_ascii=False).encode())
        if size > self.limits.max_input_bytes:
            raise ModelCallError("input_limit", "The complete input exceeds its byte budget; split the batch.")
        audit = {
            "event": "model.call",
            "tool": name,
            "input_id": digest(packet),
            "input_bytes": size,
            "model": self.model,
        }
        self.trace.append(audit)
        try:
            async with asyncio.timeout(self.limits.timeout):
                response = await self.provider.chat(
                    messages=messages,
                    tools=tools,
                    model=self.model,
                    max_tokens=self.limits.max_output,
                    temperature=0.0,
                    reasoning_effort=self.effort,
                    tool_choice="auto",
                )
        except asyncio.CancelledError:
            audit["error"] = "cancelled"
            raise
        except TimeoutError as exc:
            audit["error"] = "timeout"
            raise ModelCallError("timeout", "The model call timed out.", called=True) from exc
        except Exception as exc:
            audit["error"] = "provider_error"
            raise ModelCallError("provider_error", "The model provider failed.", called=True) from exc
        audit["usage"] = dict(response.usage or {})
        audit["finish_reason"] = response.finish_reason
        record = response.call_record
        audit["served_model"] = record.served_model if record else None
        if response.finish_reason == "error":
            audit["error_category"] = (
                response.error_classification.category if response.error_classification else "unknown"
            )
            raise ModelCallError("provider_error", "The model provider reported an error.", called=True)
        if response.truncated or response.finish_reason == "length":
            raise ModelCallError(
                "truncated", "Return a shorter complete submission within the output limit.", called=True
            )
        usable = len(response.tool_calls) == 1 and response.tool_calls[0].name == name
        if usable:
            call = response.tool_calls[0]
            usable = RAW_ARGUMENTS_KEY not in call.arguments and not (
                call.run_meta and (call.run_meta.arguments_repaired or call.run_meta.truncation)
            )
        completion_tokens = response.usage.get("completion_tokens") if response.usage else None
        if not usable and isinstance(completion_tokens, int) and completion_tokens >= self.limits.max_output:
            audit["error"] = "output_limit"
            raise ModelCallError(
                "truncated",
                "The response reached its output limit without a usable submission. Return concise complete JSON; "
                "preserve required reviews and accepted prior proposals, and omit optional speculative proposals.",
                called=True,
            )
        if len(response.tool_calls) != 1 or response.tool_calls[0].name != name:
            raise ModelCallError(
                "invalid_submission", "Call only the supplied submission tool, exactly once.", called=True
            )
        call = response.tool_calls[0]
        if RAW_ARGUMENTS_KEY in call.arguments or (
            call.run_meta and (call.run_meta.arguments_repaired or call.run_meta.truncation)
        ):
            raise ModelCallError(
                "invalid_submission", "Submit valid complete JSON without repaired arguments.", called=True
            )
        try:
            result = schema.model_validate(call.arguments)
        except ValidationError as exc:
            fields = [
                ".".join(map(str, item["loc"])) for item in exc.errors(include_input=False, include_context=False)
            ]
            raise ModelCallError(
                "invalid_submission", "Correct the submission fields: " + ", ".join(fields), called=True
            ) from exc
        audit["output_digest"] = digest(result.model_dump(mode="json"))
        return result
