"""The owner: a model plays the business owner who cultivates the digital employee through the Curator.

Each round the owner, having had its drill cards played against the employee, steps out of the role to judge the
drills and speaks to the Curator: what went wrong, what matters most, what came back after it was fixed, and which
materials it now hands over. It judges only what the employee did: nothing of the Curator's reaches it.

What the owner knows is fixed: all of the scenario's materials. What varies is when each reaches the employee: all at
onboarding, as the owner decides after each round, or on a fixed partition of the materials into steps. Whatever the
plan, everything has been handed over by the review before the last round, so the last round tries an employee that
was told everything.

The owner reviews each drill against the card it played this round and the `facts` the case computes from its own
materials for that card and from the delivered files; it still decides every verdict itself. A case that delivers
files a model must look at rather than read (a deck's pages) gives them through `pictures`; they reach the owner only
when its model is known to take images, and otherwise the packet says they were not shown.

The owner is a case's assessor (`experimental.harness.assessor.role.AssessorProtocol`): it holds the standard and only speaks, the way
a real owner would: a remark in its own words and the materials it hands over. The base Analyst reads those words
against the sessions and the execution records, with exactly the materials it reads for any assessor, and writes
the requirements. The owner still keeps a scorecard, one verdict per criterion, but only the value judge reads it
(from the analysis record under `records`): the criteria, the cards and the facts never reach the Analyst or the
Curator.
"""

import hashlib
import json
from contextlib import nullcontext
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from experimental.cultivation.collector.curator import INFORMATION_FILE
from experimental.harness.assessor.rubric import digest
from experimental.harness.contract.declaration import schema_for
from experimental.harness.curator.generation.context.render import tool
from experimental.harness.participation.allowance import reading_budget
from experimental.harness.participation.channel import said
from experimental.harness.participation.compartment import texts_of
from experimental.harness.participation.exchange import exchange, messages
from experimental.harness.participation.files import read_delivered
from experimental.harness.participation.protocols import Handover, Item, Signal
from experimental.harness.participation.views import (
    PRIVATE,
    back_office,
    cut,
    execution_digest,
    reports,
    transcript,
    written,
)
from experimental.harness.raven_adapter.materialize import _write
from experimental.harness.raven_adapter.observe import plain
from experimental.harness.scenario import Disclosure
from experimental.harness.scenario.digest import digest as scenario_digest
from raven.providers.capabilities import vision_verdict
from raven.providers.rates import warm_catalog_in_background

if TYPE_CHECKING:
    from experimental.cultivation.counterpart.scenario import Scenario

NAME = "submit_review"
# Raven fences a report on lines of its own; a request that quotes one inside JSON (a strategy's inference input)
# has escaped line breaks there, so it is not read as a report reaching the employee.
# A delegation's result as Raven announces it to the employee (`raven/agent/subagent/manager.py`): the task the
# employee wrote, then optional instance and working-directory lines, then the fenced result.
# Raven's tally of a delegation's failed tool calls, fenced after the result it belongs to.
# Other marked blocks (a skill catalog, say) may quote the start of a report's marker.
SOURCE = "agency"
REFERENCES = "references.jsonl"
# The parts of the review packet the partner was free to show: what it said, delivered, researched and filed, and the
# information it was briefed with.
PARTNER_WORK = (
    "conversations",
    "deliverables",
    "research",
    "colleague_reports",
    "filed",
    "back_office",
    "pictures",
    "information",
)
Delivery = Literal["pool", "dialog"]
_PROMPT = Path(__file__).resolve().parent / "prompts" / "owner.md"


class Verdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    result: Literal["pass", "fail", "unknown", "not_applicable"]
    session: str | None = None
    actual: str = ""
    note: str = ""


class Mark(Verdict):
    """A verdict on the owner's own scorecard, which only the value judge reads."""

    waits_on: str | None = Field(
        default=None, description="For a fail covered only by a material you still hold back: that material."
    )


class Spoken(BaseModel):
    """What the owner submits: its scorecard, its remark to the trainer and its handover."""

    model_config = ConfigDict(extra="forbid")

    verdicts: list[Mark] = Field(min_length=1)
    remark: str = Field(min_length=1)
    handover: list[str] = Field(default_factory=list)


def handles(criteria) -> dict[str, str]:
    """The neutral name the owner knows each criterion by, in the criteria's order. The owner's remark goes to the
    trainer, who must not learn the criteria; an owner never shown their ids cannot cite one there, so it gives its
    verdicts by handle and `Owner` maps them back to the ids."""
    return {criterion.id: f"check-{number}" for number, criterion in enumerate(criteria, 1)}


def waiting(review: Spoken) -> dict[str, str]:
    """Each failed criterion the owner said only waits on a material it still holds back, with that material."""
    return {verdict.id: verdict.waits_on for verdict in review.verdicts if verdict.waits_on}


def deliverables(exchanges, *, tokens: int | None = None) -> dict[str, str]:
    """The last version of each file a conversation handed over, a deck read slide by slide with its styling."""
    files = {}
    for turn in exchanges:
        for path in turn.execution.deliverables:
            if Path(path).is_file():
                files[Path(path).name] = cut(read_delivered(path, style=True), tokens)
    return files


def no_facts(name, exchanges, card) -> dict:
    """The default `facts` hook: a case whose materials define no figures to compute."""
    return {}


def delivery_versions(exchanges, *, tokens: int | None = None) -> list[dict]:
    """Keep each retained delivery tied to its turn; reused mutable paths cannot prove an earlier version."""
    last = {str(path): index for index, exchange_ in enumerate(exchanges) for path in exchange_.execution.deliverables}
    versions = []
    for index, exchange_ in enumerate(exchanges):
        if not exchange_.execution.deliverables:
            continue
        files = deliverables([exchange_], tokens=tokens)
        unavailable = {}
        delivered_versions = []
        for path in exchange_.execution.deliverables:
            if last[str(path)] != index:
                name = Path(path).name
                files.pop(name, None)
                unavailable[name] = "An earlier delivery reused this path without a separately retained snapshot."
            elif Path(path).is_file():
                delivered_versions.append(
                    {
                        "name": Path(path).name,
                        "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                        "content": cut(read_delivered(path, style=True), tokens),
                    }
                )
        versions.append({"turn": index + 1, "files": files, "versions": delivered_versions, "unavailable": unavailable})
    return versions


UNSEEN = (
    "The rendered pages were not shown: the model reviewing this round is not known to take images. Judge the decks "
    "from their text and [style] lines under deliverables, and leave a criterion only their look decides unknown."
)


def no_pictures(sessions) -> tuple[dict, list[dict], str]:
    """The default `pictures` hook: nothing to look at beyond the text of the delivered files."""
    return {}, [], ""


def research(exchanges, *, tokens: int | None = None) -> dict[str, str]:
    """What the research colleague reported in each playbook run of a conversation, read from the run manifest."""
    found = {}
    for turn in exchanges:
        for row in turn.execution.records:
            if row["kind"] != "dag.progress" or row.get("name") != "dag_run_completed":
                continue
            for node in ((row.get("payload") or {}).get("manifest") or {}).get("files", []):
                path = Path(str(node.get("output_file") or ""))
                if "Research" in str(node.get("subagent")) and path.is_file():
                    found[str(node["node"])] = cut(path.read_text(errors="replace"), tokens)
    return found


def attached(paths, kinds) -> tuple[Handover, ...]:
    """Uploaded files as a signal's handovers, one per material, its files relative to the agent home as
    `uploads/<material>/...` however deep they sit in the package; `kinds` gives each material's kind."""
    files: dict[str, list[str]] = {}
    for path in paths:
        parts = Path(path).parts
        start = parts.index("uploads")
        files.setdefault(parts[start + 1], []).append(Path(*parts[start:]).as_posix())
    return tuple(Handover(name, kinds[name], tuple(items)) for name, items in files.items())


class Owner:
    """`prepare` puts the plan's opening materials in place; `evaluate` judges a round, records the owner's scorecard
    and answers with what the owner says, releasing what it hands over.

    The owner judges what the employee did and knows nothing of how it is trained: no plan or reply of the Curator
    reaches it.
    `facts(name, exchanges, card)` computes, from the case's own materials, the figures the owner judges a drill with
    (what the price list gives for the card, whether a forbidden word appears in a delivered file); `pictures(sessions)`
    gives, per drill, what the owner must look at rather than read and the image parts to show it, with the sentence
    that introduces them. Both default to nothing.
    `cards` returns each drill's current playing of its card (see `experimental.simulation.bench.conversant.Conversant.card`), keyed by drill name; the owner
    reads it and the facts take their values from it. With `records`, each judged drill's card and facts are
    appended to `references.jsonl` there. `workdirs` maps each drill to the `workdir` and `home` of the replica it
    played on (see `experimental.cultivation.employee.Together`); `workdir` is the employee's own, where every replica
    started.
    `deliver` says how materials reach the employee: `dialog` hands them to the Curator the way an owner would, the
    opening materials uploaded to the employee's `uploads` folder with an onboarding message (`opening`), later ones
    uploaded the same way and also pasted into the remark; `pool` copies them straight into its skill pool, bypassing
    the Curator.
    `disclosure` says when materials are given (see `experimental.harness.scenario.disclosure`); by default the staged
    schedule, the scenario's initial set and then what the owner chooses with each review.
    `records` is the run's root: the owner's scorecard and any failed judgement go to its `analysis` folder, where the
    value judge and the record reader find them beside the Analyst's records; `references.jsonl` goes there too.
    With `boundaries`, every review is made in the counterpart's compartment, sparing the partner's own work
    (`PARTNER_WORK`), which the partner was free to show, so the owner's own knowledge is held to the counterpart's seal.
    """

    def __init__(
        self,
        scenario: "Scenario",
        provider,
        skills: Path,
        *,
        workdir: Path,
        disclosure: Disclosure | None = None,
        deliver: Delivery = "dialog",
        uploads: Path | None = None,
        shared: Path | None = None,
        cards=None,
        handouts=None,
        records: Path | None = None,
        workdirs: dict | None = None,
        model=None,
        effort=None,
        max_calls=4,
        timeout=180,
        boundaries=None,
        facts=no_facts,
        pictures=no_pictures,
    ):
        disclosure = disclosure or scenario.disclosure()
        if set(disclosure.materials) != set(scenario.handed):
            raise ValueError(
                f"the disclosure schedules other materials than the scenario hands over: {sorted(scenario.handed)}"
            )
        if deliver not in ("pool", "dialog") or (deliver == "dialog" and uploads is None):
            raise ValueError(f"unknown delivery {deliver!r}, or a dialog delivery without an uploads folder")
        documents = sorted(name for name in scenario.handed if not (scenario.materials[name] / "SKILL.md").is_file())
        if deliver == "pool" and documents:
            raise ValueError(
                f"the skill pool finds a material only by its SKILL.md, which {documents} lack; deliver them by dialog"
            )
        self.scenario, self.provider, self.skills, self.workdir = scenario, provider, Path(skills), Path(workdir)
        self.deliver, self.uploads, self.uploaded = deliver, Path(uploads) if uploads else None, []
        self.shared = Path(shared) if shared else None
        self.disclosure, self.model, self.effort = disclosure, model, effort
        self.max_calls, self.timeout = max_calls, timeout
        self.cards = cards or dict
        self._provided_handouts = handouts or (lambda sessions: {})
        self.records = Path(records) if records else None
        self.workdirs = workdirs if workdirs is not None else {}
        self.boundaries = boundaries
        self.facts, self.pictures = facts, pictures
        if pictures is not no_pictures:
            # Whether the owner's model takes images is read from the gateway catalog, which a fresh home lacks.
            warm_catalog_in_background()
        self.kinds = dict(scenario.kinds)
        self.released: list[str] = []
        self.reviews: list[dict] = []
        self.judged = 0

    def sees_images(self) -> bool:
        """Whether the model judging the rounds is known to take images (Raven's gateway catalog); an unknown model is
        not sent pictures, since a model that cannot take them fails the whole review."""
        return vision_verdict(self.model or self.provider.get_default_model()) is True

    def _filed(self, name) -> dict[str, str]:
        """What a drill left for colleagues: the files new or changed in its replica's workdir and home.

        A replica starts from the employee's own workdir and home, so comparing against them finds tickets however
        they were written, moved or renamed. The deck engine's `decks` folder is its build output: a delivered deck
        reaches the owner as a deliverable. A drill that played on no replica has nothing to compare, so it filed
        nothing here.
        """
        placed = self.workdirs.get(name)
        if placed is None:
            return {}
        home = self.uploads.parent if self.uploads else None
        tokens = self.reading
        return {
            **written(
                placed["workdir"], self.workdir, label="workdir", skip=frozenset({"uploads", "decks"}), tokens=tokens
            ),
            **(written(placed["home"], home, label="home", skip=PRIVATE, tokens=tokens) if home else {}),
        }

    @property
    def reading(self) -> int:
        """Tokens one document may take in what the owner reads: a share of its model's window."""
        default = getattr(self.provider, "get_default_model", None)
        return reading_budget(self.model or (default() if default else None))

    def information(self) -> str:
        """The information snapshot the employee was briefed with (`experimental.cultivation.collector.curator`), as it stands in
        its home; empty when the run collected none."""
        path = self.uploads.parent / INFORMATION_FILE if self.uploads else None
        return cut(path.read_text(errors="replace"), self.reading) if path is not None and path.is_file() else ""

    @property
    def chooses(self) -> bool:
        """Whether the owner decides what to hand over; on a fixed partition the schedule decides."""
        return self.disclosure.chooses

    def due(self, review: int) -> list[str]:
        """What the schedule hands over with the review of round `review`, whatever the owner chooses."""
        return self.disclosure.due(review, self.released)

    @property
    def withheld(self) -> list[str]:
        return [name for name in self.scenario.handed if name not in self.released]

    @property
    def never_handed(self) -> list[str]:
        """Withheld materials this schedule never hands over (every one under `none`): a miss they cover cannot wait
        on them."""
        if self.chooses or self.disclosure.completes:
            return []
        return [name for name in self.withheld if self.disclosure.step_of(name) is None]

    def prepare(self) -> None:
        places = (self.skills, self.uploads, self.shared)
        self.scenario.withdraw(*(place for place in places if place is not None))
        self.released, self.reviews, self.uploaded, self.judged = [], [], [], 0
        opening = list(self.disclosure.opening)
        if self.deliver == "dialog":
            self.uploaded = self.scenario.upload(opening, self.uploads, shared=self.shared)
            self.released.extend(opening)
        else:
            self._release(opening)

    def opening(self) -> tuple[Signal, ...]:
        """The owner's onboarding message with its uploaded files; nothing when materials went straight to the pool
        or nothing was handed over, since the message is the handover."""
        if self.deliver != "dialog" or not self.uploaded:
            return ()
        files = "\n".join(f"- {path}" for path in self.uploaded)
        attachments = attached(self.uploaded, self.kinds)
        return (
            Signal(
                SOURCE,
                self.scenario.onboarding.replace("{files}", files),
                attachments=attachments,
                authority="external",
            ),
        )

    def _release(self, names) -> list[str]:
        new = [name for name in names if name not in self.released]
        if self.deliver == "pool":
            self.scenario.release(new, self.skills)
        self.released.extend(new)
        return new

    def _parse(self, sessions, arguments, expected) -> Spoken:
        review = Spoken.model_validate(arguments)
        got = [verdict.id for verdict in review.verdicts]
        if sorted(got) != sorted(expected):
            raise ValueError(f"give exactly one verdict per criterion; expected {expected}, got {got}")
        unknown = {verdict.session for verdict in review.verdicts if verdict.session} - sessions.keys()
        if unknown:
            raise ValueError(f"verdicts name sessions that did not happen: {sorted(unknown)}")
        stray = set(review.handover) - set(self.withheld)
        if stray:
            raise ValueError(f"handover may name only withheld materials {self.withheld}; got {sorted(stray)}")
        never = set(self.never_handed)
        coming = {*review.handover, *self.due(self.judged + 1)} if self.chooses else set(self.withheld) - never
        named = handles(self.scenario.criteria)
        definitions = {named[criterion.id]: criterion for criterion in self.scenario.criteria}
        for verdict in review.verdicts:
            if verdict.result == "not_applicable":
                definition = definitions.get(verdict.id)
                if definition is None or not definition.applies_when.strip():
                    raise ValueError("an unconditional criterion cannot be marked not_applicable")
                if not verdict.note.strip():
                    raise ValueError("not_applicable requires an evidenced explanation of the unmet condition")
            if verdict.waits_on is None:
                continue
            if verdict.result != "fail":
                raise ValueError(f"only a failed verdict waits on a material; {verdict.id} is {verdict.result}")
            if verdict.waits_on not in self.withheld:
                raise ValueError(
                    f"a verdict waits only on a material still withheld {self.withheld}; got {verdict.waits_on!r}"
                )
            if verdict.waits_on in never:
                raise ValueError(f"{verdict.waits_on!r} is never handed over: judge the miss without waiting on it")
            if verdict.waits_on not in coming:
                raise ValueError(f"hand over {verdict.waits_on!r}, the material a verdict waits on")
        return review

    def _record(self, sessions, drawn, found) -> None:
        if self.records is None:
            return
        self.records.mkdir(parents=True, exist_ok=True)
        source = scenario_digest(self.scenario.root)
        with (self.records / REFERENCES).open("a") as log:
            for name in sessions:
                card = drawn.get(name)
                trip = getattr(card, "trip", None)
                row = {
                    "evaluation": self.judged + 1,
                    "drill": name,
                    "execution_ids": [exchange_.execution.turn_id for exchange_ in sessions[name]],
                    "scenario_digest": source,
                    "card": card.text if card else None,
                    "expected": getattr(card, "expected", None),
                    "trip": trip.facts() if trip else None,
                    "references": found.get(name, {}),
                }
                log.write(json.dumps(row, ensure_ascii=False) + "\n")

    def record(self, entry: dict) -> None:
        """Keep the owner's private record beside the run's analysis records, where the value judge reads it."""
        if self.records is None:
            return
        _write(self.records / "analysis" / f"{uuid4().hex}.json", json.dumps(plain(entry), ensure_ascii=False).encode())

    async def evaluate(self, sessions) -> Signal:
        """The owner's words on the round: its remark, whether it is satisfied and what it hands over, never its
        verdicts. The scorecard is recorded first, so a failed round keeps it; a failed judgement is recorded too."""
        self._review_evidence = {}
        try:
            scorecard, judged, _ = await self._judge(sessions)
        except Exception as exc:
            self.record({"source": SOURCE, "error": str(exc), **self._review_evidence})
            raise
        self.record(
            {"source": SOURCE, "scorecard": scorecard, "waiting_on_material": waiting(judged), **self._review_evidence}
        )
        return Signal(
            SOURCE,
            scorecard.text,
            satisfied=scorecard.satisfied,
            attachments=scorecard.attachments,
            authority="external",
        )

    async def _judge(self, sessions) -> tuple[Signal, Spoken, list[str]]:
        """The owner's call: its scorecard as a signal, its submission and the materials it handed over with it."""
        drawn = self.cards()
        found = {name: self.facts(name, exchanges, drawn.get(name)) for name, exchanges in sessions.items()}
        self._record(sessions, drawn, found)
        delivered = {name: deliverables(exchanges, tokens=self.reading) for name, exchanges in sessions.items()}
        researched = {name: research(exchanges, tokens=self.reading) for name, exchanges in sessions.items()}
        named = handles(self.scenario.criteria)
        packet = {
            "profile": self.scenario.profile,
            "criteria": [{**criterion.model_dump(), "id": named[criterion.id]} for criterion in self.scenario.criteria],
            "materials": {
                name: self.scenario.text(name) for name in self.scenario.materials if self.scenario.stands_behind(name)
            },
            "material_files": self.scenario.evidence_materials(
                self.scenario.materials, role="counterpart", tokens=self.reading
            ),
            "handouts": self._provided_handouts(sessions),
            "given_to_the_assistant": list(self.released),
            "withheld": self.withheld,
            "never_handed": self.never_handed,
            "handing_over_now": self.due(self.judged + 1),
            "you_choose_handover": self.chooses,
            "your_earlier_reviews": [
                {**review, "failed": [named.get(id, id) for id in review["failed"]]} for review in self.reviews
            ],
            "cards": {name: drawn[name].text for name in sessions if name in drawn},
            "expected": {name: answer for name in sessions if (answer := getattr(drawn.get(name), "expected", None))},
            "references": {name: facts for name, facts in found.items() if facts},
            "conversations": {name: transcript(exchanges) for name, exchanges in sessions.items()},
            "deliverables": {name: files for name, files in delivered.items() if files},
            "deliveries_by_turn": {
                name: delivery_versions(exchanges, tokens=self.reading) for name, exchanges in sessions.items()
            },
            "research": {name: notes for name, notes in researched.items() if notes},
            "colleague_reports": {name: told for name, exchanges in sessions.items() if (told := reports(exchanges))},
            "information": self.information(),
            "filed": {name: files for name in sessions if (files := self._filed(name))},
            "back_office": {name: rows for name, exchanges in sessions.items() if (rows := back_office(exchanges))},
        }
        packet["pictures"], parts, lead = self.pictures(sessions)
        if parts and not self.sees_images():
            packet["pictures"] = {"not_shown": UNSEEN, "decks": packet["pictures"]}
            parts = []
        criteria = [criterion.model_dump() for criterion in self.scenario.criteria]
        self._review_evidence = {
            "assessment_id": uuid4().hex,
            "evaluation": self.judged + 1,
            "rubric_version": digest(criteria),
            "scenario_digest": scenario_digest(self.scenario.root),
            "criteria": criteria,
            "criterion_handles": named,
            "execution_ids": {
                name: [exchange_.execution.turn_id for exchange_ in exchanges] for name, exchanges in sessions.items()
            },
            "evidence": packet,
            "evidence_digest": digest(plain(packet)),
            "execution_digest": execution_digest(sessions),
            "image_inputs_shown": len(parts),
        }
        request = messages(_PROMPT.read_text(), packet)
        if parts:
            request.append({"role": "user", "content": [{"type": "text", "text": lead}, *parts]})
        partner = [
            *(tuple(said(exchange_) for exchange_ in exchanges) for exchanges in sessions.values()),
            *texts_of([packet[key] for key in PARTNER_WORK]),
        ]
        scope = nullcontext() if self.boundaries is None else self.boundaries.compartment("counterpart", spoken=partner)
        with scope as entered:
            _, review = await exchange(
                self.provider if entered is None else entered.provider(self.provider),
                request,
                [
                    tool(
                        NAME,
                        "Submit your scorecard (one verdict per criterion), your remark to the trainer, and any materials "
                        "you now hand over.",
                        schema_for(Spoken),
                    )
                ],
                submit={NAME: lambda arguments: self._parse(sessions, arguments, list(named.values()))},
                model=self.model,
                effort=self.effort,
                max_calls=self.max_calls,
                timeout=self.timeout,
                label="agency",
            )
        known = {handle: id for id, handle in named.items()}
        review = review.model_copy(
            update={"verdicts": [verdict.model_copy(update={"id": known[verdict.id]}) for verdict in review.verdicts]}
        )
        criteria = {criterion.id: criterion for criterion in self.scenario.criteria}
        items = tuple(
            Item(v.id, v.result, v.session, expected=criteria[v.id].check, actual=v.actual, note=v.note, basis="check")
            for v in review.verdicts
        )
        self.judged += 1
        handed = self._release([*(review.handover if self.chooses else ()), *self.due(self.judged)])
        text, uploaded = review.remark.strip(), []
        if self.deliver == "dialog" and handed:
            uploaded = self.scenario.upload(handed, self.uploads, shared=self.shared)
            self.uploaded.extend(uploaded)
            files = "\n".join(f"- {path}" for path in uploaded)
            note = self.scenario.handover.replace("{files}", files) if self.scenario.handover else files
            # The owner voices only what it stands behind: a candidate it never confirmed goes over as files alone,
            # or its words would carry the candidate to the Analyst as the owner's own.
            voiced = [self.scenario.document(name).strip() for name in handed if self.scenario.stands_behind(name)]
            text = "\n\n---\n\n".join([text, note, *voiced])
        entry = {
            "round": len(self.reviews) + 1,
            "remark": review.remark.strip(),
            "failed": sorted({v.id for v in review.verdicts if v.result == "fail"}),
        }
        self.reviews.append(
            {**entry, "waiting_on_material": sorted(set(waiting(review).values())), "handed_over": handed}
        )
        signal = Signal(
            SOURCE,
            text,
            items,
            satisfied=(
                all(item.result == "pass" for item in items if item.result != "not_applicable")
                if any(item.result != "not_applicable" for item in items)
                else None
            ),
            attachments=attached(uploaded, self.kinds),
            authority="external",
        )
        return signal, review, handed
