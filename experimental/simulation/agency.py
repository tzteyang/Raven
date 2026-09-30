"""The agency: a model plays the owner who cultivates the digital employee through the Curator.

Each round the owner plays customers from its drill cards, then steps out of the role to judge the drills and
speaks to the Curator: what went wrong, what matters most, what came back after it was fixed, and which
materials it now hands over. It judges only what the employee did: nothing of the Curator's reaches it.

What the owner knows is fixed: all of the scenario's materials. What varies is when each reaches the employee: all at
onboarding, as the owner decides after each round, or on a fixed partition of the materials into steps. Whatever the
plan, everything has been handed over by the review before the last round, so the last round tries an employee that
was told everything.

The owner reviews each drill against the card it played this round, with figures computed from its own materials for
that card and facts read from the delivered deck's structure (`references`); it still decides every verdict itself.

The agency is this scenario's assessor (`experimental.iteration.protocols.Assessor`): it holds the standard and only
speaks, the way a real owner would: a remark in its own words and the materials it hands over. The base Analyst reads
those words against the sessions and the execution records, with exactly the materials it reads for any assessor, and
writes the requirements. The owner still keeps a scorecard, one verdict per criterion, but only the value judge reads
it (from the analysis record under `records`): the criteria, the cards and the references never reach the Analyst or
the Curator.
"""

import base64
import json
import re
from contextlib import nullcontext
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from ..automation.channel import said
from ..automation.files import page_images, read_delivered
from ..automation.traveller import transcript
from ..curator.generation.context.render import tool
from ..curator.harness.declaration import schema_for
from ..curator.raven_adapter.materialize import _write
from ..curator.raven_adapter.observe import plain
from ..iteration.compartment import texts_of
from ..iteration.exchange import exchange, messages
from ..iteration.protocols import Handover, Item, Signal
from ..scenario import Disclosure
from .reference import Rules, references
from .scenario import Scenario

NAME = "submit_review"
DELIVERABLE_LIMIT = 120_000
RESEARCH_LIMIT = 40_000
FILED_LIMIT = 20_000
TASK_LIMIT = 1_500
PAGES = 24
REPORT = re.compile(
    r"\[BEGIN UNTRUSTED subagent #(?P<tag>\w+)[^\]]*\]\n?(?P<body>.*?)\n?\[END UNTRUSTED subagent #(?P=tag)\]", re.S
)
# Other marked blocks (a skill catalog, say) may quote the start of a report's marker.
OTHER_BLOCK = re.compile(
    r"\[BEGIN UNTRUSTED (?!subagent )[^\]#]*#(?P<tag>\w+)[^\]]*\].*?\[END UNTRUSTED [^\]#]*#(?P=tag)\]", re.S
)
TASK_LABEL, ANSWER_LABEL = "The task the sub-agent was given:", "What it returned as its answer:"
TAIL_LABEL = "Tail of what the sub-agent did"
LOOKS = frozenset({"read_file", "list_dir", "grep", "find", "web_search", "web_fetch", "load_skill", "read_skill"})
TEXT_FILES = frozenset({".md", ".txt", ".csv", ".json", ".yaml", ".yml"})
PRIVATE = frozenset({"sessions", "subagents", "uploads", "skills", "memory", "agent_memory", "user_memory", "decks"})
SOURCE = "agency"
REFERENCES = "references.jsonl"
# The parts of the review packet that are the partner's own work: what it said, delivered, researched and filed.
PARTNER_WORK = ("conversations", "deliverables", "research", "colleague_reports", "filed", "back_office", "deck_pages")
Delivery = Literal["pool", "dialog"]
_PROMPT = Path(__file__).resolve().parent / "prompts" / "owner.md"


class Verdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    result: Literal["pass", "fail", "unknown"]
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


def waiting(review: Spoken) -> dict[str, str]:
    """Each failed criterion the owner said only waits on a material it still holds back, with that material."""
    return {verdict.id: verdict.waits_on for verdict in review.verdicts if verdict.waits_on}


def cut(text: str, limit: int) -> str:
    """`text` up to `limit` characters; a longer one says how much was left out, so the owner never takes a cut
    document for the whole of it."""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[... {len(text) - limit} more characters not shown]"


def deliverables(exchanges) -> dict[str, str]:
    """The last version of each file a conversation handed over, a deck read slide by slide with its styling."""
    files = {}
    for turn in exchanges:
        for path in turn.execution.deliverables:
            if Path(path).is_file():
                files[Path(path).name] = cut(read_delivered(path, style=True), DELIVERABLE_LIMIT)
    return files


def looks(sessions) -> tuple[dict, list[dict]]:
    """Per drill, the page count of each deck it delivered (last version), and those pages as image message parts.

    The owner flips through the rendered pages the way a customer would; a deck that cannot be rendered says so.
    """
    shown, parts = {}, []
    for name, exchanges in sessions.items():
        decks = {
            Path(path).name: Path(path)
            for turn in exchanges
            for path in turn.execution.deliverables
            if Path(path).suffix.lower() == ".pptx" and Path(path).is_file()
        }
        for deck, path in decks.items():
            try:
                images = page_images(path)[:PAGES]
            except Exception as exc:  # noqa: BLE001 -- a deck that cannot be rendered is reported, not fatal
                shown.setdefault(name, {})[deck] = f"could not be rendered: {exc}"[:200]
                continue
            shown.setdefault(name, {})[deck] = len(images)
            parts.append({"type": "text", "text": f"[{name}] {deck}"})
            for number, image in enumerate(images, start=1):
                url = "data:image/png;base64," + base64.b64encode(image.read_bytes()).decode()
                parts += [{"type": "text", "text": f"page {number}"}, {"type": "image_url", "image_url": {"url": url}}]
    return shown, parts


def research(exchanges) -> dict[str, str]:
    """What the research colleague reported in each playbook run of a conversation, read from the run manifest."""
    found = {}
    for turn in exchanges:
        for row in turn.execution.records:
            if row["kind"] != "dag.progress" or row.get("name") != "dag_run_completed":
                continue
            for node in ((row.get("payload") or {}).get("manifest") or {}).get("files", []):
                path = Path(str(node.get("output_file") or ""))
                if "Research" in str(node.get("subagent")) and path.is_file():
                    found[str(node["node"])] = cut(path.read_text(errors="replace"), RESEARCH_LIMIT)
    return found


def reports(exchanges) -> list[dict]:
    """Every report a colleague (a subagent or a playbook step) sent back to the employee, with the task it had.

    Read from the model requests of the employee's turns, where each reaches it in marked blocks: a delegation's
    result names the task it was given, then what it returned as its answer (the tail of what it did is left out);
    a playbook step's account follows the note that names the step. Whatever the colleague was asked to do, this is
    what the employee had in hand. The same report repeats in every later request, so each is kept once.
    """
    found = {}
    for turn in exchanges:
        for row in turn.execution.records:
            if row.get("kind") != "provider.request":
                continue
            for message in (row.get("parameters") or {}).get("messages") or []:
                content = message.get("content")
                if not isinstance(content, str) or "[BEGIN UNTRUSTED subagent" not in content:
                    continue
                content, task, start = OTHER_BLOCK.sub("", content), "", 0
                for match in REPORT.finditer(content):
                    lead = content[start : match.start()].strip()
                    start = match.end()
                    label = lead.splitlines()[-1] if lead else ""
                    body = match.group("body").strip()
                    if TASK_LABEL in label:
                        task = body
                        continue
                    if label.startswith(TAIL_LABEL):
                        continue
                    asked = task if ANSWER_LABEL in label else lead.split("\n\n")[-1]
                    asked = asked.split("Working directory:", 1)[0].strip()
                    asked = "" if asked.startswith("[Runtime Context") else asked
                    if len(asked) > TASK_LIMIT:
                        asked = asked[: TASK_LIMIT * 2 // 3] + " [...] " + asked[-TASK_LIMIT // 3 :]
                    report = cut(body, RESEARCH_LIMIT)
                    found[report] = found.get(report) or asked
    return [{"task": task, "report": report} for report, task in found.items()]


def written(folder: Path, before: Path, *, label: str, skip=frozenset()) -> dict[str, str]:
    """Files under `folder` that are new or changed against `before`, keyed `label/relative path`.

    Text files come with their content; anything else (decks, scripts, build output) is listed by name only. Hidden
    entries are the host's and tools' own bookkeeping (Raven's `.raven` checkpoints, a deck engine's dot files), not
    something the employee filed.
    """
    files = {}
    if not Path(folder).is_dir():
        return files
    for path in sorted(Path(folder).rglob("*")):
        relative = path.relative_to(folder)
        if (
            not path.is_file()
            or skip & set(relative.parts[:1])
            or "__pycache__" in relative.parts
            or any(part.startswith(".") for part in relative.parts)
        ):
            continue
        old = Path(before) / relative
        if old.is_file() and old.read_bytes() == path.read_bytes():
            continue
        key = f"{label}/{relative.as_posix()}"
        if path.suffix.lower() in TEXT_FILES and not relative.parts[0] == "decks":
            files[key] = cut(path.read_text(errors="replace"), FILED_LIMIT)
        else:
            files[key] = f"[{path.suffix or 'file'}; content not shown]"
    return files


def back_office(exchanges) -> list[dict]:
    """What the employee did besides talking, turn by turn and in order: files written, commands, playbooks,
    delegations and deliveries, each with whether it succeeded (`ok`, with the tool's error when it failed), so
    the owner can see what happened before what and never takes a failed write for a filed ticket."""
    rows = []
    for index, turn in enumerate(exchanges, start=1):
        started, finished = [], {}
        for row in turn.execution.records:
            event = row.get("event") or {}
            if row.get("kind") != "runner.event" or row.get("event_type", "ToolEvent") != "ToolEvent":
                continue
            if event.get("phase") == "start" and event.get("name") and event["name"] not in LOOKS:
                started.append(event)
            elif event.get("phase") == "complete" and event.get("tool_call_id"):
                finished[event["tool_call_id"]] = event
        for event in started:
            arguments = event.get("arguments") or {}
            target = (
                arguments.get("path")
                or arguments.get("node_id")
                or arguments.get("name")
                or arguments.get("agent")
                or str(arguments.get("command") or "")[:120]
                or [Path(str(item.get("path") or "")).name for item in arguments.get("files") or []]
            )
            done = finished.get(event.get("tool_call_id"))
            outcome = {"ok": None} if done is None else {"ok": done.get("ok") is not False}
            if done is not None and done.get("ok") is False:
                outcome["error"] = str(done.get("result_preview") or "")[:300]
            rows.append({"turn": index, "action": event["name"], "target": target, **outcome})
    return rows


def attached(paths, kinds) -> tuple[Handover, ...]:
    """Uploaded files as a signal's handovers, one per material, its files relative to the agent home as
    `uploads/<material>/...` however deep they sit in the package; `kinds` gives each material's kind."""
    files: dict[str, list[str]] = {}
    for path in paths:
        parts = Path(path).parts
        start = parts.index("uploads")
        files.setdefault(parts[start + 1], []).append(Path(*parts[start:]).as_posix())
    return tuple(Handover(name, kinds[name], tuple(items)) for name, items in files.items())


class Agency:
    """`prepare` puts the plan's opening materials in place; `evaluate` judges a round, records the owner's scorecard
    and answers with what the owner says, releasing what it hands over.

    The owner judges what the employee did and knows nothing of how it is trained: no plan or reply of the Curator
    reaches it.
    `cards` returns each drill's current playing of its card (see `Traveller.card`), keyed by drill name; the owner
    reads it and the references take their trip facts from it. With `records`, each judged drill's card and references
    are appended to `references.jsonl` there. `workdirs` maps each drill to the `workdir` and `home` of the replica it
    played on (see `experimental.automation.employee.Together`); `workdir` is the employee's own, where every replica
    started.
    `deliver` says how materials reach the employee: `dialog` hands them to the Curator the way an owner would, the
    opening materials uploaded to the employee's `uploads` folder with an onboarding message (`opening`), later ones
    uploaded the same way and also pasted into the remark; `pool` copies them straight into its skill pool, bypassing
    the Curator.
    `disclosure` says when materials are given (see `experimental.scenario.disclosure`); by default the staged
    schedule, the scenario's initial set and then what the owner chooses with each review.
    `records` is the run's root: the owner's scorecard and any failed judgement go to its `analysis` folder, where the
    value judge and the record reader find them beside the Analyst's records; `references.jsonl` goes there too.
    With `boundaries`, every review is made in the party's compartment, sparing the partner's own work
    (`PARTNER_WORK`), which the partner was free to show, so the owner's own knowledge is held to the party's seal.
    """

    def __init__(
        self,
        scenario: Scenario,
        provider,
        skills: Path,
        *,
        workdir: Path,
        disclosure: Disclosure | None = None,
        deliver: Delivery = "dialog",
        uploads: Path | None = None,
        shared: Path | None = None,
        cards=None,
        records: Path | None = None,
        workdirs: dict | None = None,
        model=None,
        effort=None,
        max_calls=4,
        timeout=180,
        boundaries=None,
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
        self.records = Path(records) if records else None
        self.workdirs = workdirs if workdirs is not None else {}
        self.boundaries = boundaries
        self.rules = Rules.load(scenario)
        self.kinds = dict(scenario.kinds)
        self.released: list[str] = []
        self.reviews: list[dict] = []
        self.judged = 0

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
        return {
            **written(placed["workdir"], self.workdir, label="workdir", skip=frozenset({"uploads", "decks"})),
            **(written(placed["home"], home, label="home", skip=PRIVATE) if home else {}),
        }

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

    def prepare(self) -> None:
        self.scenario.withdraw(self.skills)
        if self.uploads:
            self.scenario.withdraw_uploads(self.uploads, *([self.shared] if self.shared else []))
        self.released, self.reviews, self.uploaded, self.judged = [], [], [], 0
        opening = list(self.disclosure.opening)
        if self.deliver == "dialog":
            self.uploaded = self.scenario.upload(opening, self.uploads, shared=self.shared)
            self.released.extend(opening)
        else:
            self._release(opening)

    def opening(self) -> tuple[Signal, ...]:
        """The owner's onboarding message with its uploaded files; nothing when materials went straight to the pool."""
        if self.deliver != "dialog":
            return ()
        files = "\n".join(f"- {path}" for path in self.uploaded)
        attachments = attached(self.uploaded, self.kinds)
        return (Signal(SOURCE, self.scenario.onboarding.replace("{files}", files), attachments=attachments),)

    def _release(self, names) -> list[str]:
        new = [name for name in names if name not in self.released]
        if self.deliver == "pool":
            self.scenario.release(new, self.skills)
        self.released.extend(new)
        return new

    def _parse(self, sessions, arguments) -> Spoken:
        review = Spoken.model_validate(arguments)
        expected = [criterion.id for criterion in self.scenario.criteria]
        got = [verdict.id for verdict in review.verdicts]
        if sorted(got) != sorted(expected):
            raise ValueError(f"give exactly one verdict per criterion; expected {expected}, got {got}")
        unknown = {verdict.session for verdict in review.verdicts if verdict.session} - sessions.keys()
        if unknown:
            raise ValueError(f"verdicts name sessions that did not happen: {sorted(unknown)}")
        stray = set(review.handover) - set(self.withheld)
        if stray:
            raise ValueError(f"handover may name only withheld materials {self.withheld}; got {sorted(stray)}")
        coming = {*review.handover, *self.due(self.judged + 1)} if self.chooses else set(self.withheld)
        for verdict in review.verdicts:
            if verdict.waits_on is None:
                continue
            if verdict.result != "fail":
                raise ValueError(f"only a failed verdict waits on a material; {verdict.id} is {verdict.result}")
            if verdict.waits_on not in self.withheld:
                raise ValueError(
                    f"a verdict waits only on a material still withheld {self.withheld}; got {verdict.waits_on!r}"
                )
            if verdict.waits_on not in coming:
                raise ValueError(f"hand over {verdict.waits_on!r}, the material a verdict waits on")
        return review

    def _record(self, sessions, drawn, found) -> None:
        if self.records is None:
            return
        self.records.mkdir(parents=True, exist_ok=True)
        with (self.records / REFERENCES).open("a") as log:
            for name in sessions:
                card = drawn.get(name)
                row = {
                    "evaluation": self.judged + 1,
                    "drill": name,
                    "card": card.text if card else None,
                    "trip": card.trip.facts() if card and card.trip else None,
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
        try:
            scorecard, judged, _ = await self._judge(sessions)
        except Exception as exc:
            self.record({"source": SOURCE, "error": str(exc)})
            raise
        self.record({"source": SOURCE, "scorecard": scorecard, "waiting_on_material": waiting(judged)})
        return Signal(SOURCE, scorecard.text, satisfied=scorecard.satisfied, attachments=scorecard.attachments)

    async def _judge(self, sessions) -> tuple[Signal, Spoken, list[str]]:
        """The owner's call: its scorecard as a signal, its submission and the materials it handed over with it."""
        drawn = self.cards()
        found = {
            name: references(self.rules, exchanges, getattr(drawn.get(name), "trip", None))
            for name, exchanges in sessions.items()
            if self.rules
        }
        self._record(sessions, drawn, found)
        delivered = {name: deliverables(exchanges) for name, exchanges in sessions.items()}
        researched = {name: research(exchanges) for name, exchanges in sessions.items()}
        packet = {
            "profile": self.scenario.profile,
            "criteria": [criterion.model_dump() for criterion in self.scenario.criteria],
            "materials": {
                name: self.scenario.text(name) for name in self.scenario.materials if self.scenario.stands_behind(name)
            },
            "given_to_the_assistant": list(self.released),
            "withheld": self.withheld,
            "handing_over_now": self.due(self.judged + 1),
            "you_choose_handover": self.chooses,
            "your_earlier_reviews": self.reviews,
            "cards": {name: drawn[name].text for name in sessions if name in drawn},
            "references": {name: facts for name, facts in found.items() if facts},
            "conversations": {name: transcript(exchanges) for name, exchanges in sessions.items()},
            "deliverables": {name: files for name, files in delivered.items() if files},
            "research": {name: notes for name, notes in researched.items() if notes},
            "colleague_reports": {name: told for name, exchanges in sessions.items() if (told := reports(exchanges))},
            "filed": {name: files for name in sessions if (files := self._filed(name))},
            "back_office": {name: rows for name, exchanges in sessions.items() if (rows := back_office(exchanges))},
        }
        packet["deck_pages"], pictures = looks(sessions)
        request = messages(_PROMPT.read_text(), packet)
        if pictures:
            lead = {"type": "text", "text": "The pages of the delivered decks, in the order `deck_pages` lists them."}
            request.append({"role": "user", "content": [lead, *pictures]})
        partner = [
            *(tuple(said(exchange_) for exchange_ in exchanges) for exchanges in sessions.values()),
            *texts_of([packet[key] for key in PARTNER_WORK]),
        ]
        scope = nullcontext() if self.boundaries is None else self.boundaries.compartment("party", spoken=partner)
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
                submit={NAME: lambda arguments: self._parse(sessions, arguments)},
                model=self.model,
                effort=self.effort,
                max_calls=self.max_calls,
                timeout=self.timeout,
                label="agency",
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
            satisfied=all(item.result == "pass" for item in items),
            attachments=attached(uploaded, self.kinds),
        )
        return signal, review, handed
