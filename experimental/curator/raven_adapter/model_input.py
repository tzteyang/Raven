"""Deliver effective capabilities and Memory projection at the native model-call boundary."""

from copy import deepcopy
from dataclasses import replace

from raven.contracts.llm_provider import ErrorClassification, LLMResponse

from .memory.context import ProjectionOverflowError


class ModelInput:
    """Delegate native Action while preparing a detached input for each actual call.

    Root delegation protection wraps this adapter, so its input already contains
    the effective native tool definitions. The persistent loop transcript is not
    rewritten and its rollback watermark remains valid.
    """

    def __init__(self, native, capability, sources, memory=None, action=None):
        self.native, self.capability, self.sources, self.memory = native, capability, sources, memory
        self.action = action

    async def decide(self, request):
        view = self.capability.effective(request.tools)
        frame = self.sources.frame(view.scope.session_key)
        messages = deepcopy(request.messages)
        if not view.native_skills:
            messages = self.sources.strip_native_skills(messages, frame)
        text = []
        if self.action is not None:
            guidance = self.action.model_guidance(request.on_token_delta)
            if guidance:
                text.append(guidance)
        if view.guidance:
            text.append(view.guidance)
        for selected in view.selection:
            matches = [
                skill
                for skill in view.skills
                if skill.name == selected.name and (selected.source is None or skill.source == selected.source)
            ]
            if len(matches) != 1 or not matches[0].available:
                raise ValueError(f"selected skill became unavailable before model input: {selected.name}")
            skill = matches[0]
            text.append(
                skill.content
                if selected.delivery == "body"
                else f"Skill {skill.name}: {skill.description}\nRead: {skill.path}"
            )
        if text:
            messages.insert(
                1 if messages and messages[0].get("role") == "system" else 0,
                {
                    "role": "system",
                    "content": "\n\n".join(text),
                },
            )
        if self.memory is not None:
            sources = self.sources.projection_sources(messages, frame, native_skills=view.native_skills)
            try:
                messages = await self.memory.project(messages, frame, sources, view)
            except ProjectionOverflowError as exc:
                self.capability.recorder.add(
                    "model.input.pressure",
                    scope=view.scope,
                    source="local_projection",
                    estimated_tokens=exc.size,
                    allowance=exc.allowance,
                )
                return LLMResponse(
                    content=str(exc),
                    finish_reason="error",
                    error_classification=ErrorClassification("context_overflow", should_compress=True),
                )
        self.capability.recorder.add("model.input", scope=view.scope, messages=messages, tools=view.tools)
        return await self.native.decide(replace(request, messages=messages))

    def ask_judge(self, *args, **kwargs):
        return self.native.ask_judge(*args, **kwargs)

    async def ask_review(self, *args, **kwargs):
        return await self.native.ask_review(*args, **kwargs)

    async def ask_salvage(self, *args, **kwargs):
        return await self.native.ask_salvage(*args, **kwargs)
