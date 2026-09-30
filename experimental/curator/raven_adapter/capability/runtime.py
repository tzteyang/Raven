"""Bind public registration and selection to native tools and skill consumers."""

from copy import deepcopy

from raven.agent.hook.participant import ParticipantHook
from raven.contracts.participant import AgentParticipant

from ...harness.declaration import typed
from ...harness.interaction import InteractionScope
from ...harness.resources import (
    CapabilityContribution,
    CapabilitySelection,
    EffectiveCapabilities,
    RegistrationReceipt,
    SelectionRequest,
)
from ...harness.strategies import CapabilityStrategy
from ..observe import plain
from ..strategy import SESSION, BoundStrategy


class NativeCapability(CapabilityStrategy):
    """Use the shared registrar and preserve native selection when no policy was authored."""

    def __init__(self, registrar):
        self.registrar = registrar

    def register(self, contribution: CapabilityContribution) -> RegistrationReceipt:
        return self.registrar.register(contribution)

    async def select(self, request: SelectionRequest) -> CapabilitySelection:
        return CapabilitySelection()


class BoundCapability(BoundStrategy):
    """Share one candidate catalogue across independently checkpointed session policies."""

    def __init__(
        self,
        config,
        task,
        path,
        package,
        recorder,
        *,
        catalog,
        infer=None,
        plan=None,
        peers=None,
        scope=None,
        host=None,
    ):
        self.catalog, self.runtime = catalog, None
        self.config, self.task, self.path, self.recorder = config, task, path, recorder
        self.scope = scope or (
            lambda: InteractionScope(
                harness_id=str(path.parent),
                task_id=task.id,
                revision=catalog.candidate,
                session_key=SESSION.get(),
                turn_id=recorder.turn_id,
            )
        )
        self.plan = plan
        self.selections = {}
        self.selection_errors = {}
        self.effective_views = {}
        self.native = NativeCapability(catalog)
        if config is not None:
            super().__init__(
                "capability",
                CapabilityStrategy,
                config,
                task,
                path,
                package,
                recorder,
                infer=infer,
                plan=plan,
                registrar=catalog,
                peers=peers,
                host=host,
            )
            required = {
                "register": ([CapabilityContribution], RegistrationReceipt),
                "select": ([SelectionRequest], CapabilitySelection),
            }
            if self.types != required:
                raise TypeError(
                    "capability methods must use the public contribution, receipt, request and selection types"
                )

    def _key(self):
        scope = self.scope()
        return scope.session_key, scope.turn_id

    def _current_turn(self):
        current = self._key()
        for records in (self.selections, self.selection_errors, self.effective_views):
            for key in tuple(records):
                if key[0] == current[0] and key != current:
                    del records[key]

    def register(self, contribution):
        """Call the public policy, checking its receipt against the actual staged catalogue."""
        contribution = typed(CapabilityContribution, contribution)
        if self.catalog.closed:
            return self.native.register(contribution)
        before = (
            dict(self.catalog.contributions),
            dict(self.catalog.tools),
            dict(self.catalog.skills),
            dict(self.catalog.deferred_tools),
        )
        try:
            result = (
                self.translate("register", self.strategy.register, contribution, output=RegistrationReceipt)
                if self.config is not None
                else self.native.register(contribution)
            )
            if (result.name, result.owner, result.kind, result.candidate) != (
                contribution.name,
                contribution.owner,
                contribution.kind,
                self.catalog.candidate,
            ):
                raise ValueError("registration receipt does not identify the supplied contribution")
            key = (contribution.kind, contribution.name)
            expected = before[0] if result.status == "rejected" else {**before[0], key: contribution}
            if self.catalog.contributions != expected:
                raise ValueError("registration receipt disagrees with the actual candidate resources")
            if result.status == "unchanged" and before[0].get(key) != contribution:
                raise ValueError("unchanged registration requires an identical existing contribution")
            if result.status == "staged" and key in before[0]:
                raise ValueError("an identical existing contribution must report unchanged")
        except BaseException:
            self.catalog.contributions, self.catalog.tools, self.catalog.skills, self.catalog.deferred_tools = before
            raise
        self.recorder.add("capability.register", contribution=contribution, receipt=result)
        return result

    def require(self, contribution):
        receipt = self.register(contribution)
        if receipt.status == "rejected":
            raise ValueError(f"capability contribution {receipt.name} refused: {receipt.reason}")
        return receipt

    def stage_skills(self, root, config):
        self.catalog.stage(config)

    def install(self, runtime, *, context=None, disabled=()):
        self.catalog.install(runtime, context=context, disabled=disabled)
        self.runtime = runtime

    async def prepare(self):
        if self.config is not None:
            await super().prepare()

    async def select(self, request):
        if not self.catalog.installed:
            raise RuntimeError("capability selection requires an installed catalogue")
        self._current_turn()
        request = typed(SelectionRequest, request)
        result = (
            await self.call(
                "select",
                request,
                source="selection",
                validate=lambda value: self._validate_selection(request, value),
            )
            if self.config is not None
            else await self.native.select(request)
        )
        self._validate_selection(request, result)
        self.selections[self._key()] = result
        self.selection_errors.pop(self._key(), None)
        return result

    @staticmethod
    def _validate_selection(request, result):
        offered = {row["function"]["name"] for row in request.tools}
        if result.tools is not None and set(result.tools) - offered:
            raise ValueError("capability selection must name offered tools")
        if result.skills is not None:
            for selected in result.skills:
                matches = [
                    skill
                    for skill in request.skills
                    if skill.name == selected.name and (selected.source is None or skill.source == selected.source)
                ]
                if len(matches) != 1 or not matches[0].available:
                    raise ValueError(f"selected skill is unknown, ambiguous or unavailable: {selected.name}")

    def effective(self, tools):
        if self._key() in self.selection_errors:
            raise RuntimeError(f"capability selection failed: {self.selection_errors[self._key()]}")
        selection = self.selections.get(self._key(), CapabilitySelection())
        bodies = {(item.source, item.name) for item in selection.skills or () if item.delivery == "body"}
        skills = self.catalog.skill_views(self.runtime, bodies=bodies) if self.runtime is not None else ()
        view = EffectiveCapabilities(
            scope=self.scope(),
            tools=plain(tools),
            skills=skills,
            selection=selection.skills or (),
            native_skills=selection.skills is None,
            guidance=selection.guidance,
        )
        self.effective_views[self._key()] = view
        self.recorder.add("capability.effective", view=view)
        return view

    def read(self):
        value = self.effective_views.get(self._key())
        return value.model_copy(deep=True) if value is not None else None

    def facts(self):
        return {
            **(super().facts() if self.config is not None else {}),
            **self.catalog.facts(),
            "effective": [view.model_dump(mode="json") for view in self.effective_views.values()],
        }

    def hook(self):
        owner = self

        class CapabilityParticipant(AgentParticipant):
            async def select_tools(self, offered, step):
                try:
                    request = SelectionRequest(
                        scope=owner.scope(),
                        messages=plain(step.transcript),
                        tools=plain(offered),
                        skills=owner.catalog.skill_views(owner.runtime),
                        subagents=tuple(
                            {
                                "name": agent.name,
                                "description": agent.description,
                                "owns": agent.owns,
                                "stateful": agent.stateful,
                                "reads_local_files": agent.reads_local_files,
                                "live_progress": agent.live_progress,
                            }
                            for agent in owner.runtime.loop.subagents.list_agents()
                        ),
                        plan=owner.plan() if owner.plan else None,
                    )
                    result = await owner.select(request)
                    if result.tools is None:
                        return None
                    available = {row["function"]["name"]: row for row in offered}
                    return [deepcopy(available[name]) for name in result.tools]
                except Exception as exc:
                    owner.selection_errors[owner._key()] = str(exc)
                    owner.recorder.add("capability.error", operation="selection", error=str(exc))
                    raise

        return ParticipantHook("curator-capability", CapabilityParticipant, rolls_back=False)
