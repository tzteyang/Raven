"""Delegate native Memory while handling explicitly selected text pressure paths."""

from raven.agent.window.compaction import should_compact
from raven.agent.window.shrink import MAX_COMPRESS_RETRIES
from raven.contracts.harness import ShrinkResult
from raven.utils.tokens import estimate_prompt_tokens


class MemoryWindow:
    """Use the native trigger settings and shared retry count without taking over the loop."""

    def __init__(self, native, owner, capability, loop):
        self.native, self.owner, self.capability, self.loop = native, owner, capability, loop

    @property
    def owns_compaction(self):
        return self.native.owns_compaction

    def candidate_messages(self, session):
        return self.native.candidate_messages(session)

    def token_budget(self, selected_skills=None):
        return self.native.token_budget(selected_skills)

    async def assemble(self, *args, **kwargs):
        return await self.native.assemble(*args, **kwargs)

    async def after_turn(self, *args, **kwargs):
        return await self.native.after_turn(*args, **kwargs)

    async def ask_system_addendum(self, *args, **kwargs):
        return await self.native.ask_system_addendum(*args, **kwargs)

    async def ask_archive(self, *args, **kwargs):
        return await self.native.ask_archive(*args, **kwargs)

    async def ask_intake(self, *args, **kwargs):
        return await self.native.ask_intake(*args, **kwargs)

    async def shrink(self, messages, *, pressure, state, model):
        kind = str(getattr(pressure, "value", pressure))
        if kind not in self.owner.config.compact or kind not in {"proactive", "overflow"}:
            return await self.native.shrink(messages, pressure=pressure, state=state, model=model)
        if state.compress_retries >= MAX_COMPRESS_RETRIES:
            self.owner.recorder.add("memory.compaction", pressure=kind, status="exhausted")
            return ShrinkResult(messages, False)
        if kind == "proactive":
            budget = self.native.token_budget()
            observed = state.last_context_used or estimate_prompt_tokens(messages, self.loop.tools.get_definitions())
            if not should_compact(
                observed, budget.context_length, budget.reserved_output, self.loop._compaction.trigger_ratio
            ):
                return ShrinkResult(messages, False)
        state.compress_retries += 1
        try:
            projected = await self.owner.compact_window(messages, self.capability.read(), kind)
        except Exception as exc:
            self.owner.recorder.add("memory.compaction", pressure=kind, status="failed", error=str(exc))
            return ShrinkResult(messages, False)
        state.last_context_used = 0
        self.owner.recorder.add("memory.compaction", pressure=kind, status="applied")
        return ShrinkResult(projected, True)
