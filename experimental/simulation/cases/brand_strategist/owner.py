"""The brand strategist's owner: the generic `Owner` with the facts the marketing lead judges a drill by.

The facts are computed from the norms, never judged: which forbidden words appear in what the assistant said and
delivered, each with the line it stands on so the owner can tell copy from the assistant's own talk, whether the slogan line of a delivered file is repeated word for word, which figures lack a source on
their line, and what the records show of the on-call colleague (the watch's child executions, the campaign tools
called, the report file delivered). The owner reads them the way a person uses a word search and a ruler. The
words themselves (the forbidden list, the slogan marker, the figure units, the source mark, the report prefix) are
the scenario's, read from its `reference.md` like the travel agency's price words.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from experimental.cultivation.counterpart.owner import Owner
from experimental.cultivation.counterpart.rulers import CONFIG, delivered, messages, occurrences, words

ONCALL = "Raven-Oncall"
CAMPAIGN_TOOLS = ("ops_declare", "ops_submit", "ops_check_later", "ops_finish", "ops_ask_owner")
SNIPPET = 60


@dataclass(frozen=True)
class Vocabulary:
    """The words the marketing lead's facts are computed with, from the scenario's `reference.md` table."""

    forbidden: tuple[str, ...]
    slogan_markers: tuple[str, ...]
    figure_units: tuple[str, ...]
    source_marks: tuple[str, ...]
    report_prefix: str

    @classmethod
    def load(cls, scenario) -> "Vocabulary":
        found = words(Path(scenario.root) / CONFIG)
        return cls(
            forbidden=found["forbidden"],
            slogan_markers=found["slogan_marker"],
            figure_units=found["figure_units"],
            source_marks=found["source_marks"],
            report_prefix=found["report_prefix"][0],
        )

    @property
    def slogan(self) -> re.Pattern:
        markers = "|".join(re.escape(marker) for marker in self.slogan_markers)
        return re.compile(rf"^\s*(?:{markers})\s*(.+?)\s*$", re.M)

    @property
    def figure(self) -> re.Pattern:
        units = "|".join(re.escape(unit) for unit in self.figure_units)
        return re.compile(rf"\d[\d,.]*\s*(?:{units})")

    @property
    def report(self) -> re.Pattern:
        return re.compile(rf"^{re.escape(self.report_prefix)}.*\.md$")


def forbidden_words(text: str, vocabulary: Vocabulary) -> dict[str, list[str]]:
    """Each forbidden word found, in the order of the list, with the stretch of every line it stands on."""
    return occurrences(text, vocabulary.forbidden)


def slogan_lines(text: str, vocabulary: Vocabulary) -> list[str]:
    """Every slogan line's slogan, in order; a delivered file with more than one distinct value is inconsistent."""
    return [match.group(1) for match in vocabulary.slogan.finditer(text or "")]


def unsourced_figures(text: str, vocabulary: Vocabulary) -> list[str]:
    """Lines carrying a figure (a count or a percentage in the scenario's units) without a source mark on the line."""
    return [
        line.strip()[:SNIPPET]
        for line in (text or "").splitlines()
        if vocabulary.figure.search(line) and not any(mark in line for mark in vocabulary.source_marks)
    ]


def oncall_evidence(exchanges, vocabulary: Vocabulary) -> dict:
    """What the records show of the on-call colleague: child executions of the on-call harness, the campaign tools
    its records name, and whether a watch report was delivered."""
    executions, tools = 0, set()
    for turn in exchanges:
        for row in turn.execution.records:
            if row.get("kind") == "child.execution" and ONCALL in str(row.get("harness", "")):
                executions += 1
                for item in row.get("records") or ():
                    text = str(item)
                    tools.update(name for name in CAMPAIGN_TOOLS if name in text)
            elif row.get("kind") == "runner.event":
                name = str((row.get("event") or {}).get("name") or "")
                if name in CAMPAIGN_TOOLS:
                    tools.add(name)
    reported = [name for name in delivered(exchanges) if vocabulary.report.match(name)]
    return {"oncall_executions": executions, "campaign_tools": sorted(tools), "watch_reports": reported}


def facts(exchanges, vocabulary: Vocabulary) -> dict:
    """The owner's facts for one drill, keyed by what each measures."""
    files = delivered(exchanges)
    said = messages(exchanges)
    found = {}
    hits = {
        f"message {index}": found_words
        for index, text in enumerate(said, 1)
        if (found_words := forbidden_words(text, vocabulary))
    } | {
        f"file {file}": found_words
        for file, text in files.items()
        if (found_words := forbidden_words(text, vocabulary))
    }
    if hits:
        found["forbidden_words"] = hits
    slogans = {file: lines for file, text in files.items() if (lines := slogan_lines(text, vocabulary))}
    if slogans:
        found["slogan_lines"] = {
            file: {"distinct": sorted(set(lines)), "consistent": len(set(lines)) == 1}
            for file, lines in slogans.items()
        }
    figures = {
        f"message {index}": rows for index, text in enumerate(said, 1) if (rows := unsourced_figures(text, vocabulary))
    } | {f"file {file}": rows for file, text in files.items() if (rows := unsourced_figures(text, vocabulary))}
    if figures:
        found["unsourced_figures"] = figures
    evidence = oncall_evidence(exchanges, vocabulary)
    if evidence["oncall_executions"] or evidence["campaign_tools"] or evidence["watch_reports"]:
        found["on_call"] = evidence
    if files:
        found["delivered_files"] = sorted(files)
    return found


class BrandOwner(Owner):
    """The marketing lead of the brand strategist scenario, judging with the norms' word search and ruler."""

    def __init__(self, scenario, provider, skills, **options):
        super().__init__(scenario, provider, skills, facts=self._facts, **options)
        self.vocabulary = Vocabulary.load(scenario)

    def _facts(self, name, exchanges, card) -> dict:
        return facts(exchanges, self.vocabulary)


# The owner the simulation entry judges this case by (`experimental.simulation.__main__.owner_of`).
OWNER = BrandOwner
