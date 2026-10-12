"""Bind each interactive or automatic loop step to its run, round and revision."""

from functools import wraps

from raven.observability import execution
from raven.observability.ledger import FILENAME, Ledger


def step(function):
    @wraps(function)
    async def observed(self, *args, **kwargs):
        context = execution.current() or execution.Context(
            Ledger(self.worker.root / FILENAME), self.record.get("execution_run_id", self.path.stem)
        )
        round_index = len(self.rounds) + (function.__name__ != "curate")
        if function.__name__ in ("onboard", "baseline"):
            round_index = 0
        self.record["execution_run_id"] = context.run_id
        self.save()
        with (
            execution.bind(context),
            execution.scope(
                function.__name__, round_index=round_index, revision=self._revision(), stage=function.__name__
            ),
        ):
            return await function(self, *args, **kwargs)

    return observed
