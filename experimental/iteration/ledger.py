"""Whether each requirement held after the revision that followed it, and the loop's chain joined into rows.

A requirement does not hold in the round after its revision when the Analyst raised something that repeats it (a
repeating requirement takes the earlier id, see `experimental.analyst.run.identified`), or a check or case it was
grounded on failed, or an item carrying its own id failed (the regression check `experimental.assessor.standard`
keeps for it). It holds when one of those items passed, or, when nothing measures it item by item, when the
Analyst did not raise it again. When its items were all judged unknown the round did not exercise it, and with no
signal nothing can be said; both leave it undecided, so an untested requirement never counts as held. This is the
one rule: the Session writes it into the history the Curator reads (`mark`), and the ledger reads it back.

`rows` joins, per requirement, the round it was raised in, the Curator's diagnosis of it (the root's, beside every
scope's of a composite curation) and the attributor that made it, the changes grounded on it in any scope with
their treatment, and whether it held. `summary` groups the judged rows by
attributor identity and by (state, treatment), so versions of attribution can be compared across runs. `held_out`
reads each round's held-out assessment, which no role saw, as the measure of what generalised.
"""

import json

from .history import Entry, Raised

ITEM_GROUNDS = ("check:", "case:")


def held(raised: Raised, feedback, signals) -> bool | None:
    """Whether `raised` held in the round judged by `signals` and analysed into `feedback`."""
    if not signals:
        return None
    if feedback is not None and any(requirement.id == raised.id for requirement in feedback.requirements):
        return False
    grounded = {ground.split(":", 1)[1] for ground in raised.grounds if ground.startswith(ITEM_GROUNDS)}
    results = [item.result for signal in signals for item in signal.items if item.id in {raised.id, *grounded}]
    if "fail" in results:
        return False
    if "pass" in results:
        return True
    return None if results else True


def mark(entry: Entry, feedback, signals) -> Entry:
    """The entry with every requirement's `held` decided by the round after it."""
    return entry.model_copy(
        update={
            "requirements": tuple(
                raised.model_copy(update={"held": held(raised, feedback, signals)}) for raised in entry.requirements
            )
        }
    )


def rows(history) -> list[dict]:
    """One row per requirement raised in `history` (entries or their recorded form), with its diagnosis, the
    changes grounded on it and whether it held."""
    out = []
    for value in history:
        entry = value if isinstance(value, Entry) else Entry.model_validate(value)
        diagnoses: dict[str, list] = {}
        for diagnosis in entry.diagnoses or ():
            diagnoses.setdefault(diagnosis.about, []).append(diagnosis)
        for raised in entry.requirements:
            scoped = diagnoses.get(raised.id, [])
            diagnosis = next((item for item in scoped if item.scope == "root"), scoped[0] if scoped else None)
            out.append(
                {
                    "round": entry.round,
                    "requirement": raised.id,
                    "situation": raised.situation,
                    "strength": raised.strength,
                    "repeats": raised.repeats,
                    "state": diagnosis.state if diagnosis else None,
                    "mechanism": diagnosis.mechanism if diagnosis else None,
                    "diagnoses": [{"scope": item.scope, "state": item.state} for item in scoped],
                    "attributor": entry.attributor,
                    "curated": entry.revision is not None,
                    "changes": [
                        {"scope": change.scope, "target": change.target, "treatment": change.treatment}
                        for change in entry.revision or ()
                        if raised.id in change.addresses
                    ],
                    "held": raised.held,
                }
            )
    return out


def summary(ledger_rows) -> list[dict]:
    """Judged rows counted per attributor identity and (state, treatment); a requirement no change addressed counts
    under the treatment None."""
    groups: dict[tuple, dict] = {}
    for row in ledger_rows:
        if row["held"] is None:
            continue
        identity = json.dumps(row["attributor"], sort_keys=True) if row["attributor"] else None
        for treatment in {change["treatment"] for change in row["changes"]} or {None}:
            key = (identity, row["state"], treatment)
            group = groups.setdefault(
                key,
                {
                    "attributor": row["attributor"],
                    "state": row["state"],
                    "treatment": treatment,
                    "judged": 0,
                    "held": 0,
                },
            )
            group["judged"] += 1
            group["held"] += int(row["held"])
    return list(groups.values())


def held_out(rounds) -> list[dict]:
    """Per recorded round, each held-out assessor's verdict and its items' results counted."""
    out = []
    for number, value in enumerate(rounds, 1):
        for signal in value.get("holdout_signals", ()):
            results = [item["result"] for item in signal.get("items", ())]
            out.append(
                {
                    "round": number,
                    "source": signal["source"],
                    "satisfied": signal.get("satisfied"),
                    "items": len(results),
                    "passed": results.count("pass"),
                    "failed": results.count("fail"),
                }
            )
    return out
