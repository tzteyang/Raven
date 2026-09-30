"""Fingerprints of what a role must not receive, derived from a scenario's visibility declarations.

A guard cannot judge meaning; it can only recognise what it was told is hidden. `Sealed` holds two kinds of
fingerprint: exact identifier tokens (check ids, paths, a scenario's name) and hashed windows of normalised text.
The windows are differential: a window that also occurs in something the role may see is not sealed, so a check
that restates a norm the role holds is recognised only by its own wording. `sealed_for` derives a role's
fingerprints from a loaded scenario; the compartments in `experimental.iteration.compartment` scan with them.

Text is read as units, a CJK character or a word of any other script, and a window is a run of units weighing
`WINDOW`: a CJK character weighs one and a word two, so a window is about twenty characters of Chinese or ten
words of English. Counting characters alike for both scripts would make an English window three words long, and
any phrase a role says in its own words, such as "the itinerary template", would read as a leak. Scripts written
without spaces other than CJK (Thai) read as long words, and combining marks split words of scripts such as
Devanagari; no scenario uses them yet, and their windows would be coarser.
"""

import hashlib
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

from .contract import ROLES, Role, Scenario, contents

WINDOW = 20
_CJK = "\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uac00-\ud7af\U00020000-\U0002ffff"
_UNITS = re.compile(rf"[{_CJK}]|[^\W_{_CJK}]+")
_CHARACTER = re.compile(rf"[{_CJK}]")
_SEPARATOR = "\x1f"
# A token is sealable only when it reads as an identifier rather than a word: a plain word such as a case named
# "family" would match ordinary speech, and the opaque session keys handle those names instead.
_IDENTIFIER = re.compile(r"^[\w-]*[-_:.\d][\w-]*$")


# Hyphens NFKC keeps apart from the ASCII one: an id written with any of them is the same id.
_HYPHENS = str.maketrans({code: "-" for code in (0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2015, 0x2212)})


def fold(text: str) -> str:
    """Text as identifiers are compared: width-, case- and hyphen-folded."""
    return unicodedata.normalize("NFKC", text).casefold().translate(_HYPHENS)


def units(text: str) -> list[str]:
    """The text's CJK characters and words, case- and width-folded, without punctuation or spacing."""
    return _UNITS.findall(unicodedata.normalize("NFKC", text).lower())


def _weight(unit: str) -> int:
    return 1 if _CHARACTER.fullmatch(unit) else 2


def weight(text: str) -> int:
    return sum(_weight(unit) for unit in units(text))


def normalize(text: str) -> str:
    """The units joined by a separator that also closes both ends, so a phrase matches whole units only."""
    found = units(text)
    return _SEPARATOR + _SEPARATOR.join(found) + _SEPARATOR if found else ""


def _digest(piece: str) -> int:
    return int.from_bytes(hashlib.blake2b(piece.encode(), digest_size=8).digest(), "big")


def windows(text: str, size: int = WINDOW) -> frozenset[int]:
    """Hashes of every shortest run of units weighing at least `size`; a lighter text has none (see `phrases`)."""
    found = units(text)
    weights = [_weight(unit) for unit in found]
    hashes: set[int] = set()
    end = total = 0
    for start in range(len(found)):
        while end < len(found) and total < size:
            total += weights[end]
            end += 1
        if total < size:
            break
        hashes.add(_digest(_SEPARATOR.join(found[start:end])))
        total -= weights[start]
    return frozenset(hashes)


def sealable(token: str) -> bool:
    return bool(_IDENTIFIER.match(token)) and len(token) >= 4


@dataclass(frozen=True)
class Sealed:
    """`tokens` are identifiers matched whole; `windows` are hashed windows of long texts; `phrases` are texts
    lighter than a window, normalised, matched as whole runs of units."""

    tokens: frozenset[str] = frozenset()
    windows: frozenset[int] = frozenset()
    phrases: frozenset[str] = frozenset()
    size: int = WINDOW

    @classmethod
    def of(
        cls, hidden: Iterable[str], *, visible: Iterable[str] = (), tokens: Iterable[str] = (), size: int = WINDOW
    ) -> "Sealed":
        shown_windows: set[int] = set()
        shown_texts: list[str] = []
        for text in visible:
            shown_windows |= windows(text, size)
            shown_texts.append(normalize(text))
        sealed: set[int] = set()
        phrases: set[str] = set()
        for text in hidden:
            normal = normalize(text)
            if not normal:
                continue
            if weight(text) < size:
                if not any(normal in seen for seen in shown_texts):
                    phrases.add(normal)
            else:
                sealed |= windows(text, size)
        return cls(
            frozenset(fold(token) for token in tokens if sealable(token)),
            frozenset(sealed - shown_windows),
            frozenset(phrases),
            size,
        )

    def hits(self, text: str) -> list[str]:
        """The sealed tokens found in `text`, however it writes their case, width or hyphens, and `<sealed text>`
        once when a sealed window or phrase occurs in it."""
        folded = fold(text)
        found = [token for token in sorted(self.tokens) if re.search(rf"(?<![\w-]){re.escape(token)}(?![\w-])", folded)]
        normal = normalize(text)
        if (self.windows and self.windows & windows(text, self.size)) or any(
            phrase in normal for phrase in self.phrases
        ):
            found.append("<sealed text>")
        return found

    def without(self, streams: Iterable[str | Iterable[str]]) -> "Sealed":
        """This sealing minus the windows and phrases that occur in what someone entitled to say them said: each
        stream is one speaker's messages in order (a single text counts as a stream of one). What a role receives
        in such words, such as a conversant describing its own situation, is not sealed against it; the identifiers
        stay sealed. A stream also counts joined, because whoever answers one question per message is restated in
        one sentence across the message boundaries; two speakers are never joined, so halves of a hidden text said
        by two conversants stay sealed."""
        shown: set[int] = set()
        normals: list[str] = []
        for stream in streams:
            said = [stream] if isinstance(stream, str) else list(stream)
            for text in (*said, "\n".join(said)):
                shown |= windows(text, self.size)
                normals.append(normalize(text))
        return Sealed(
            self.tokens,
            frozenset(self.windows - shown),
            frozenset(phrase for phrase in self.phrases if not any(phrase in normal for normal in normals)),
            self.size,
        )

    def __bool__(self) -> bool:
        return bool(self.tokens or self.windows or self.phrases)


def sealed_for(scenario: Scenario, role: Role) -> Sealed:
    """What `role` must not receive of this scenario, minus what it may: checks, hidden cases and their expected
    answers, the evaluation aids and the scenario's own name. The onboarding and handover wording is never sealed:
    it is what the party says, heard by whoever it is said to and free to be relayed; the schedule it belongs to has
    no text of its own. A prior record is not fingerprinted here: what of it a role receives is scanned with these
    fingerprints when a session opens with it (`experimental.iteration.session`)."""
    if role not in ROLES:
        raise ValueError(f"unknown role: {role}")
    hidden: list[str] = []
    visible: list[str] = []
    tokens: list[str] = [scenario.root.name]
    for check in scenario.statements.checks:
        (visible if role in check.visibility else hidden).append(check.check)
        if role not in check.visibility:
            tokens.append(check.id)
    for case in scenario.situation.cases:
        (visible if role in case.visibility else hidden).append(case.text)
        if role not in case.visibility:
            tokens.append(case.id)
        if case.expected and not scenario.visible(f"case.expected:{case.id}", role):
            hidden.append(case.expected)
    for material in scenario.materials.values():
        (visible if role in material.visibility else hidden).extend(contents(material.path)[0].values())
    if scenario.visible("profile", role):
        visible.append(scenario.situation.profile)
    if not scenario.visible("aids", role):
        hidden.extend(text for text in (scenario.aids.rulers, scenario.aids.labels) if text)
    visible.extend(text for text in (scenario.exchange.onboarding, scenario.exchange.handover) if text)
    return Sealed.of(hidden, visible=visible, tokens=tokens)
