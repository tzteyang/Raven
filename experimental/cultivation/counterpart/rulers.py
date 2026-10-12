"""Measures an owner takes of a drill, the way a person uses a word search and a ruler.

A case keeps its words in the table of its `reference.md` (`words`): one row per key, the backticked values in the
second cell. Its owner computes facts with these measures over what the employee said and delivered, and the owner's
model still decides every verdict. Nothing here knows a case.
"""

import re
from pathlib import Path

from experimental.harness.participation.channel import said
from experimental.harness.participation.files import read_delivered

CONFIG = "reference.md"
SNIPPET = 60


def tables(text: str) -> list[list[list[str]]]:
    """Every markdown table in `text` as rows of stripped cells, the separator rows left out."""
    found, rows = [], []
    for line in [*text.splitlines(), ""]:
        if line.strip().startswith("|"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                rows.append(cells)
        elif rows:
            found.append(rows)
            rows = []
    return found


def words(path: Path) -> dict[str, tuple[str, ...]]:
    """A case's reference words: each table row's key and the backticked values in its second cell."""
    found = {}
    for table in tables(Path(path).read_text()):
        for row in table:
            values = re.findall(r"`([^`]+)`", row[1]) if len(row) > 1 else []
            if values and re.fullmatch(r"[a-z_]+", row[0]):
                found[row[0]] = tuple(values)
    return found


def around(line: str, word: str) -> str:
    """The stretch of `line` around the first `word`, at most `SNIPPET` characters."""
    start = max(0, min(line.index(word) - (SNIPPET - len(word)) // 2, len(line) - SNIPPET))
    return line[start : start + SNIPPET]


def occurrences(text: str, terms) -> dict[str, list[str]]:
    """Each term found in `text`, in the order of `terms`, with the stretch of every line it stands on."""
    found = {}
    for term in terms:
        lines = [around(line.strip(), term) for line in (text or "").splitlines() if term in line]
        if lines:
            found[term] = lines
    return found


def delivered(exchanges) -> dict[str, str]:
    """The files a drill delivered, by name, the last version of each, read as text."""
    files = {}
    for turn in exchanges:
        for path in turn.execution.deliverables:
            if Path(path).is_file():
                files[Path(path).name] = read_delivered(path)
    return files


def messages(exchanges) -> list[str]:
    """What the employee said in each turn of a drill, in order."""
    return [said(turn) for turn in exchanges]


def _han(*codes: int) -> str:
    return "".join(chr(code) for code in codes)


# The Chinese numerals, spelled by code point so the source stays in ASCII: zero to nine, the unit words ten, hundred,
# thousand, ten thousand and hundred million, and the decimal point word.
_DIGITS = _han(0x96F6, 0x4E00, 0x4E8C, 0x4E09, 0x56DB, 0x4E94, 0x516D, 0x4E03, 0x516B, 0x4E5D)
_SMALL = ("", _han(0x5341), _han(0x767E), _han(0x5343))
_LARGE = ("", _han(0x4E07), _han(0x4EBF))
_POINT = _han(0x70B9)


def chinese_number(figure: str) -> str:
    """How a figure written in digits is read aloud in Chinese: `99` as nine-ten-nine, `19.9` with a spoken point and
    the decimals digit by digit, `10` as ten without a leading one; thousands separators are ignored."""
    whole, _, decimals = figure.replace(",", "").partition(".")
    if not whole.isdigit() or (decimals and not decimals.isdigit()):
        raise ValueError(f"not a figure: {figure!r}")
    spoken = _integer(int(whole))
    return spoken + (_POINT + "".join(_DIGITS[int(digit)] for digit in decimals) if decimals else "")


def _integer(number: int) -> str:
    if number == 0:
        return _DIGITS[0]
    groups, parts, zero = [], [], False
    while number:
        groups.append(number % 10000)
        number //= 10000
    for index in range(len(groups) - 1, -1, -1):
        group = groups[index]
        if group == 0:
            zero = bool(parts)
            continue
        if parts and (zero or group < 1000):
            parts.append(_DIGITS[0])
        parts.append(_group(group) + _LARGE[index])
        zero = False
    text = "".join(parts)
    return text[1:] if text.startswith(_DIGITS[1] + _SMALL[1]) else text


def _group(number: int) -> str:
    out, zero = [], False
    for position in range(3, -1, -1):
        digit = number // 10**position % 10
        if digit == 0:
            zero = bool(out)
            continue
        if zero:
            out.append(_DIGITS[0])
            zero = False
        out.append(_DIGITS[digit] + _SMALL[position])
    return "".join(out)


def browser_executable() -> str | None:
    """The headless Chromium a local Playwright install keeps, for an owner that renders a delivered page; None when
    there is none, and the owner then says the page was not rendered."""
    cache = Path.home() / ".cache" / "ms-playwright"
    found = sorted(cache.glob("chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell"))
    return str(found[-1]) if found else None
