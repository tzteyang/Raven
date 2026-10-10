"""Coordinate bounded construction, independent review and durable candidate storage."""

import asyncio
import math
from dataclasses import dataclass

from .admission import AdmissionPolicy
from .builder import ProposalSubmission, validate_proposals
from .contracts import BuildRequest, ExperienceEvent, ExperienceProposal, RepairRequest, digest, for_model
from .critic import ReviewSubmission, validate_reviews
from .model import ModelCallError
from .roles import ExperienceBuilder, ExperienceCritic
from .state import BuildResult
from .store import BindingMismatchError, ExperienceStore, StoreConflictError, StoreError


@dataclass(frozen=True)
class BuildLimits:
    max_calls: int = 4
    max_builder_calls: int = 2
    max_critic_calls: int = 2
    call_timeout: float = 60

    def __post_init__(self):
        if (
            any(
                type(value) is not int or value < 1
                for value in (self.max_calls, self.max_builder_calls, self.max_critic_calls)
            )
            or not math.isfinite(self.call_timeout)
            or self.call_timeout <= 0
        ):
            raise ValueError("build limits require positive finite bounds")


def _identity(role) -> dict:
    identity = getattr(role, "identity", None)
    return identity() if identity else {"implementation": type(role).__module__ + "." + type(role).__qualname__}


def _revision_preserved(proposals, previous, reviews) -> None:
    hashes = {digest(proposal.model_dump()) for proposal in proposals}
    for review in reviews:
        original = digest(previous[review.proposal_index].model_dump())
        if review.decision == "accept" and original not in hashes:
            raise ModelCallError("invalid_submission", "Preserve every accepted previous proposal exactly.")
        if review.decision == "reject" and original in hashes:
            raise ModelCallError("invalid_submission", "Omit the unchanged rejected proposals.")


class ExperiencePipeline:
    def __init__(
        self,
        store: ExperienceStore,
        builder: ExperienceBuilder,
        critic: ExperienceCritic,
        *,
        limits: BuildLimits = BuildLimits(),
    ):
        self.store, self.builder, self.critic, self.limits = store, builder, critic, limits

    async def run(
        self,
        events: tuple[ExperienceEvent, ...],
        *,
        task_id: str | None = None,
        related: tuple[ExperienceProposal, ...] = (),
        capabilities: tuple[str, ...] = (),
        contract_ids: tuple[str, ...] = (),
        repair: RepairRequest | None = None,
    ) -> BuildResult:
        events = tuple(ExperienceEvent.model_validate(event.model_dump(mode="json")) for event in events)
        request = BuildRequest(
            events=tuple(event.view for event in events),
            related=related,
            capabilities=capabilities,
            contract_ids=contract_ids,
            repair=repair,
        )
        identities = {"builder": _identity(self.builder), "critic": _identity(self.critic)}
        if related:
            permitted = self.store.related_methods(
                events[0].origin.access_scope,
                AdmissionPolicy(critic_digest=digest(identities["critic"])),
                include_history=True,
            )
            if any(proposal not in permitted for proposal in request.related):
                raise StoreError("related methods need current scoped reviews and sources")
        input_id = digest(
            {"scope": events[0].origin.access_scope, "request": for_model(request, "builder"), "roles": identities}
        )
        task_id = task_id or input_id
        ttl = self.limits.call_timeout * self.limits.max_calls + 30
        handle, state = self.store.open_task(task_id, input_id, identities, events, ttl=ttl)
        if handle is None:
            return BuildResult(task_id=task_id, state=state)
        if (
            state.builder_calls > self.limits.max_builder_calls
            or state.critic_calls > self.limits.max_critic_calls
            or state.builder_calls + state.critic_calls > self.limits.max_calls
        ):
            self.store.save(handle, state, ttl=ttl, finish=True)
            raise BindingMismatchError("continuation budgets cannot be below consumed attempts")
        state = state.model_copy(update={"status": "running", "error": None})
        try:
            while state.stage != "finished":
                role = "critic" if state.stage == "review" else "builder"
                count = getattr(state, role + "_calls")
                limit = getattr(self.limits, "max_" + role + "_calls")
                if count >= limit or state.builder_calls + state.critic_calls >= self.limits.max_calls:
                    state = state.model_copy(update={"status": "exhausted", "error": "attempt_budget"})
                    handle, state = self.store.save(handle, state, ttl=ttl, finish=True)
                    return BuildResult(task_id=task_id, state=state)
                state = state.model_copy(
                    update={
                        role + "_calls": count + 1,
                        "trace": (*state.trace, {"event": "role.attempt", "role": role, "attempt": count + 1}),
                    }
                )
                handle, state = self.store.save(handle, state, ttl=ttl)
                try:
                    async with asyncio.timeout(self.limits.call_timeout):
                        if role == "builder":
                            values = await self.builder.build(
                                request,
                                previous=state.previous if state.stage == "revise" else (),
                                reviews=state.previous_reviews if state.stage == "revise" else (),
                                correction=state.correction,
                            )
                            proposals = ProposalSubmission(proposals=values).proposals
                            validate_proposals(proposals, request)
                            if state.stage == "revise":
                                _revision_preserved(proposals, state.previous, state.previous_reviews)
                            state = state.model_copy(
                                update={
                                    "proposals": proposals,
                                    "reviews": (),
                                    "correction": None,
                                    "error": None,
                                    "stage": "review" if proposals else "finished",
                                    "status": "running" if proposals else "complete",
                                }
                            )
                            handle, state = self.store.save(handle, state, ttl=ttl, finish=not proposals)
                        else:
                            values = await self.critic.review(state.proposals, request, correction=state.correction)
                            reviews = ReviewSubmission(reviews=values).reviews
                            validate_reviews(reviews, len(state.proposals))
                            accepted = tuple(
                                (state.proposals[review.proposal_index], review)
                                for review in reviews
                                if review.decision == "accept"
                            )
                            revise = any(review.decision == "revise" for review in reviews) and not state.revised
                            state = state.model_copy(
                                update={
                                    "reviews": reviews,
                                    "correction": None,
                                    "error": None,
                                    "previous": state.proposals if revise else state.previous,
                                    "previous_reviews": reviews if revise else state.previous_reviews,
                                    "revised": state.revised or revise,
                                    "stage": "revise" if revise else "finished",
                                    "status": "running" if revise else "complete",
                                    "trace": (
                                        *state.trace,
                                        {
                                            "event": "review.completed",
                                            "decisions": [review.decision for review in reviews],
                                        },
                                    ),
                                }
                            )
                            handle, state = self.store.save(
                                handle, state, ttl=ttl, finish=not revise, accepted=accepted
                            )
                except ModelCallError as exc:
                    state = state.model_copy(update={"error": exc.kind, "correction": str(exc)})
                    if exc.kind in {"invalid_submission", "truncated"}:
                        handle, state = self.store.save(handle, state, ttl=ttl)
                        continue
                    state = state.model_copy(
                        update={"status": "rejected" if exc.kind == "input_limit" else "interrupted"}
                    )
                    handle, state = self.store.save(handle, state, ttl=ttl, finish=True)
                    return BuildResult(task_id=task_id, state=state)
            return BuildResult(task_id=task_id, state=state)
        except asyncio.CancelledError:
            state = state.model_copy(update={"status": "interrupted", "error": "cancelled"})
            self.store.save(handle, state, ttl=ttl, finish=True)
            raise
        except (TimeoutError, StoreConflictError) as exc:
            state = state.model_copy(
                update={
                    "status": "interrupted",
                    "error": "timeout" if isinstance(exc, TimeoutError) else "source_conflict",
                }
            )
            self.store.save(handle, state, ttl=ttl, finish=True)
            return BuildResult(task_id=task_id, state=state)
        except Exception:
            state = state.model_copy(update={"status": "interrupted", "error": "role_error"})
            self.store.save(handle, state, ttl=ttl, finish=True)
            raise
