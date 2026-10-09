"""A worker turn keeps its outcome, an unanswered one included, then waits for the sub-agents it started and runs
their announcements as follow-up turns; a conversant who is away only for a while comes back when that time is up."""

import asyncio
from dataclasses import dataclass

from experimental.curator.raven_adapter.worker import follow_up, trial_turn
from raven.spine.turn import AnswerlessTurnError


@dataclass(frozen=True)
class Announcement:
    text: str
    turn_id: str | None = None


class Background:
    """In flight until each pending result has been announced."""

    def __init__(self, announcements, results):
        self.announcements, self.results = announcements, list(results)

    def __call__(self):
        if self.results:
            self.announcements.put_nowait(self.results.pop(0))
            return True
        return False


async def test_announcements_run_in_order_and_the_turn_ends_when_nothing_is_left():
    announcements, ran = asyncio.Queue(), []
    busy = Background(announcements, [Announcement("page ready")])

    async def run_turn(request):
        ran.append(request)
        if request.text == "page ready":
            announcements.put_nowait(Announcement("follow-up of the follow-up", "t2"))

    await follow_up(busy, announcements, run_turn, poll=0)
    assert [request.text for request in ran] == ["page ready", "follow-up of the follow-up"]
    assert ran[0].turn_id and ran[1].turn_id == "t2"


async def test_a_turn_that_started_nothing_returns_at_once():
    ran = []
    await follow_up(Background(asyncio.Queue(), []), asyncio.Queue(), ran.append, poll=0)
    assert ran == []


async def test_a_conversant_away_for_a_while_gets_what_was_announced_meanwhile_and_leaves_the_rest_running():
    announcements, ran = asyncio.Queue(), []
    announcements.put_nowait(Announcement("first look done"))

    async def run_turn(request):
        ran.append(request.text)

    loop = asyncio.get_running_loop()
    started = loop.time()
    await follow_up(lambda: True, announcements, run_turn, poll=0.01, away=0.2)
    assert ran == ["first look done"] and loop.time() - started >= 0.2
    announcements.put_nowait(Announcement("second look done"))
    await follow_up(lambda: True, announcements, run_turn, poll=0.01, away=0)
    assert ran == ["first look done", "second look done"]


async def test_a_conversant_away_for_a_while_is_away_that_long_even_when_nothing_runs():
    loop = asyncio.get_running_loop()
    started = loop.time()
    await follow_up(lambda: False, asyncio.Queue(), [].append, poll=0.01, away=0.1)
    assert loop.time() - started >= 0.1


async def test_a_turn_the_model_never_answered_is_its_outcome_and_nothing_follows_it():
    followed = []

    async def follow():
        followed.append(True)

    async def silent(turn):
        raise AnswerlessTurnError("The model returned no content on 2 attempt(s).")

    async def answered(turn):
        return {"explicit_reply": True}

    outcome = await trial_turn(silent, "turn", follow)
    assert outcome == {
        "answerless": True,
        "error": "The model returned no content on 2 attempt(s).",
        "explicit_reply": False,
    }
    assert followed == []
    assert await trial_turn(answered, "turn", follow) == {"explicit_reply": True} and followed == [True]
