"""Run rounds of trial, evaluation, analysis and curation on one worker task: the loop deciding for itself.

`run` is `Session` orchestrated by the loop's own outcomes: after each analysis it takes the step the outcome names,
curates or goes on, and stops when the session says so or a curation pauses. What each role receives and what is
recorded are the session's.
"""

import asyncio

from experimental.harness.loop.session import Limits, Session


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
    holdout_rounds=None,
    prior=(),
    prepare=None,
    measuring=frozenset(),
    experience=None,
    gaps=None,
):
    """Curate once from the task, then iterate until every assessor is satisfied, the analyst stops, or rounds run out.

    Optional `prepare` runs only before onboarding. An unready information result stops the run before any trial;
    its reviewed version is carried into subsequent curation without automatic later collection.

    `opening` signals, such as an owner handing over its materials, reach that first curation as its feedback. Each
    round every assessor measures the sessions into a `Signal`, the Analyst (on `analyst_model` and
    `analyst_effort` unless `analyst` is supplied) reads them and decides, and a `curate` outcome reaches the curator (`workflow.improve`
    unless another arm is supplied). The last round is never curated: no later round would test that revision. With
    `boundaries`, each model role runs inside its compartment; `attributor` is the version of the attribution
    mechanism the Curator diagnoses with. `trials` are the same every round, or a function of the round number
    (1-based) giving that round's. `holdout`, a pair of trials and assessors, is played and assessed after the trials
    and before the round's assessment (so an owner handing a material over with its review does not reach that
    round's exam), in every round or in the rounds `holdout_rounds` names, and kept from the Analyst and the Curator
    (`Session.holdout`); a run that stops before a named round skips that round's exam. Round 0 among `holdout_rounds`
    plays them once more before onboarding (`Session.baseline`), the measure every curation is compared with. `prior`
    are the histories of earlier cultivations the counterpart brings, heard by every curation (`hearing.heard_prior`). The signals of a
    `measuring` source (an assessor's name) measure each round in its record and are kept from the Analyst, the decision
    to stop and the Curator (`Session._acted`), such as an owner who watches without speaking. `gaps` answers the
    questions a curation leaves open (`experimental.harness.loop.gaps`); without it they stay in the record. The rounds are returned; the
    record says how the run ended: finished, paused (a curation was interrupted and can be resumed), stopped (the run
    was interrupted from outside, such as by a spend cap) or error.
    """
    assessors = tuple(assessors)
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
        assessors=assessors,
        measuring=measuring,
        experience=experience,
        gaps=gaps,
    )
    try:
        if holdout is not None and holdout_rounds and 0 in holdout_rounds and "baseline" not in session.record:
            await session.baseline(*holdout)
        if not await session.onboard(opening):
            return session.rounds
        for index in range(1, limits.max_rounds + 1):
            await session.trial(*(trials(index) if callable(trials) else trials))
            if holdout is not None and (holdout_rounds is None or index in holdout_rounds):
                await session.holdout(*holdout)
            await session.assess(*assessors)
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
