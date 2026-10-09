"""Run rounds of trial, evaluation, analysis and curation on one worker task: the loop deciding for itself.

`run` is `Session` orchestrated by the loop's own outcomes: after each analysis it takes the step the outcome names,
curates or goes on, and stops when the session says so or a curation pauses. What each role receives and what is
recorded are the session's.
"""

import asyncio

from .session import Limits, Session


async def run(
    worker,
    provider,
    trials,
    assessors,
    *,
    analyst=None,
    curator=None,
    analyst_model=None,
    analyst_effort=None,
    curator_model=None,
    limits=Limits(),
    probe=None,
    opening=(),
    boundaries=None,
    attributor=None,
    holdout=None,
    prior=(),
    prepare=None,
    measuring=frozenset(),
):
    """Curate once from the task, then iterate until every assessor is satisfied, the analyst stops, or rounds run out.

    Optional `prepare` runs only before onboarding. An unready information result stops the run before any trial;
    its reviewed version is carried into subsequent curation without automatic later collection.

    `opening` signals, such as an owner handing over its materials, reach that first curation as its feedback. Each
    round every assessor measures the sessions into a `Signal`, the Analyst (on `analyst_model` and
    `analyst_effort` unless `analyst` is supplied) reads them and decides, and a `curate` outcome reaches the curator (`workflow.improve`
    unless another arm is supplied). The last round is never curated: no later round would test that revision. With
    `boundaries`, each model role runs inside its compartment; `attributor` is the version of the attribution
    mechanism the Curator diagnoses with. `holdout`, a pair of trials and assessors, is played and assessed every
    round after the trials and kept from the Analyst and the Curator (`Session.holdout`). `prior` are the histories of
    earlier cultivations the counterpart brings, heard by every curation (`hearing.heard_prior`). The signals of a
    `measuring` source (an assessor's name) measure each round in its record and are kept from the Analyst, the decision
    to stop and the Curator (`Session._acted`), such as an owner who watches without speaking. The rounds are returned; the
    record says how the run ended: finished, paused (a curation was interrupted and can be resumed), stopped (the run
    was interrupted from outside, such as by a spend cap) or error.
    """
    session = Session.open(
        worker,
        provider,
        analyst=analyst,
        curator=curator,
        analyst_model=analyst_model,
        analyst_effort=analyst_effort,
        curator_model=curator_model,
        limits=limits,
        probe=probe,
        boundaries=boundaries,
        attributor=attributor,
        prior=prior,
        prepare=prepare,
        measuring=measuring,
    )
    try:
        if not await session.onboard(opening):
            return session.rounds
        for _ in range(limits.max_rounds):
            await session.trial(*trials)
            await session.assess(*assessors)
            if holdout is not None:
                await session.holdout(*holdout)
            outcome = await session.analyse()
            if outcome.next == "curate":
                if not await session.curate():
                    return session.rounds
            elif outcome.next == "stop":
                break
        if session.status == "running":
            session.finish()
    except asyncio.CancelledError:
        if session.status == "running":
            session.record["status"], session.record["stop"] = "stopped", "interrupted before the run ended"
            session.save()
        raise
    except Exception as exc:
        if session.status != "error":
            session.record["status"], session.record["error"] = "error", str(exc)
            session.save()
        raise
    return session.rounds
