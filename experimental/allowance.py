"""Measure model input in tokens, as a band rather than a number, for every participant's calls and readings.

Tokenizers differ between models and the host cannot run each model's own, so an input is admitted against a band
`(clear, refuse)`: an estimate below `clear` passes, one at or above `refuse` is refused, and one between passes as
`near` so the record shows the margin was thin. The estimate is tiktoken's `o200k_base` count scaled by a
calibration ratio learned from the token counts providers report back; where tiktoken cannot load (an isolated
worker without its cache), a character heuristic stands in and the measure says so. Bands default to fractions of
the model's context window, taken from Raven's rate tables; a model those tables do not know falls back to the
configured window.
"""

import re
from dataclasses import dataclass
from functools import cache
from math import isfinite

from raven.providers.rates import DEFAULT_CONTEXT_WINDOW_TOKENS, resolve_context_window

_CJK = re.compile("[\u3000-\u9fff\uf900-\ufaff\uff00-\uffef]")
NOTE = "\n[... {left} more characters not shown]"
READ_SHARE = 1 / 16


@cache
def _encoder():
    try:
        import tiktoken

        return tiktoken.get_encoding("o200k_base")
    except Exception:
        return None


def measure_name() -> str:
    return "tiktoken o200k_base" if _encoder() is not None else "character heuristic"


def estimate_tokens(text: str) -> int:
    """Tokens of `text` as the host counts them before a call; a provider's reported usage is the real figure."""
    encoder = _encoder()
    if encoder is not None:
        return len(encoder.encode(text, disallowed_special=()))
    cjk = len(_CJK.findall(text))
    return cjk + (len(text) - cjk + 3) // 4


def context_window(model: str | None, *, configured: int | None = None) -> int:
    """The model's context window in tokens: the configured value wins, then Raven's rate tables (read without a
    network fetch), then the host default."""
    if configured is not None:
        return configured
    known = resolve_context_window(model, allow_fetch=False) if model else None
    return known or DEFAULT_CONTEXT_WINDOW_TOKENS


def reading_budget(model: str | None = None, *, share: float = READ_SHARE, configured: int | None = None) -> int:
    """Tokens one document may take in a packet the model reads: `share` of its context window."""
    if not isfinite(share) or share <= 0:
        raise ValueError("a reading share must be positive and finite")
    return max(1, int(context_window(model, configured=configured) * share))


@dataclass(frozen=True)
class Band:
    """Lower and upper bounds in tokens: below `clear` an input passes, from `refuse` on it is refused."""

    clear: int
    refuse: int

    def __post_init__(self):
        if type(self.clear) is not int or type(self.refuse) is not int or not 0 < self.clear <= self.refuse:
            raise ValueError("a band needs integer bounds with 0 < clear <= refuse")

    @classmethod
    def of(cls, window: int, fractions: tuple[float, float]) -> "Band":
        low, high = fractions
        if not all(isfinite(value) and value > 0 for value in (low, high)) or low > high:
            raise ValueError("band fractions must be positive, finite and ordered")
        return cls(max(1, int(window * low)), max(1, int(window * high)))

    def verdict(self, tokens: int) -> str:
        """`clear`, `near` or `over` for an input of `tokens`."""
        if tokens >= self.refuse:
            return "over"
        return "near" if tokens >= self.clear else "clear"

    def describe(self) -> dict:
        return {"clear": self.clear, "refuse": self.refuse}


class Calibration:
    """The ratio of tokens providers report to tokens the host estimated, learned per model across calls, so the
    next estimate lands nearer the provider's own count."""

    def __init__(self):
        self.ratios: dict[str, float] = {}
        self.samples: dict[str, int] = {}

    def ratio(self, model: str | None) -> float:
        return self.ratios.get(model or "", 1.0)

    def scaled(self, model: str | None, estimate: int) -> int:
        return max(1, int(round(estimate * self.ratio(model))))

    def learn(self, model: str | None, estimate: int, reported: int | None) -> None:
        if reported is None or estimate < 1 or reported < 1:
            return
        key = model or ""
        seen = self.samples.get(key, 0)
        self.ratios[key] = (self.ratios.get(key, 1.0) * seen + reported / estimate) / (seen + 1)
        self.samples[key] = seen + 1


def excerpt(text: str, tokens: int) -> str:
    """`text` cut to about `tokens` tokens; a cut text ends with how many characters were left out, so a reader
    never takes an excerpt for the whole."""
    if tokens < 1:
        raise ValueError("an excerpt needs a positive token budget")
    if estimate_tokens(text) <= tokens:
        return text
    encoder = _encoder()
    if encoder is not None:
        kept = encoder.decode(encoder.encode(text, disallowed_special=())[:tokens])
        if not text.startswith(kept):
            kept = kept[: len(kept) - 1]
        while kept and not text.startswith(kept):
            kept = kept[:-1]
    else:
        kept = text[: tokens * 4]
        while kept and estimate_tokens(kept) > tokens:
            kept = kept[: max(1, len(kept) * 9 // 10)] if len(kept) > 1 else ""
    return kept + NOTE.format(left=len(text) - len(kept))
