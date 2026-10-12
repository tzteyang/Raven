"""The regional review case's owner: the generic `Owner` with the facts the sales-operations head judges a page by.

A drill delivers one web page for a monthly business review. The facts are measured, never judged: what the page's
source declares (fonts, colours, external references, gradients, shadows, filters, motion, the title and the points),
how it renders at the meeting-room projector's resolution (scrolling, text outside the screen, clipped, hidden or
overlapping lines, the size every text shows at once scaling is applied, the source line, the logo, decoration, what
the warning colour marks), whether each figure on the page is in the finance table that applies on the card's date or
is a figure finance later corrected, which items the data block has to carry and which are there, which cities miss
their target and what the page says about them, how many page versions were handed over and what changed between them
or against the page the director handed over, and whether the reconciliation sheet was filed. The owner reads them
the way a person uses a calculator and a ruler; the words and the per-card rulers come from the scenario's
`reference.md`, and the figures from its finance-table materials.

Text is measured by block: a page's visible text is read one block element (a heading, a point, a cell, a paragraph)
per line, whatever inline markup sits inside it, and the rendering is measured per text node for size and colour but
per block for what a line says and per line box for what overlaps what.
"""

import concurrent.futures
import datetime
import difflib
import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from html.parser import HTMLParser
from pathlib import Path

from experimental.cultivation.counterpart.owner import Owner
from experimental.cultivation.counterpart.rulers import CONFIG, browser_executable, tables, words
from experimental.harness.participation.render import cached
from experimental.harness.scenario.contract import frontmatter

from .delivery import delivered_as_requested

PAGE_SUFFIXES = (".html", ".htm")
RENDER_TIMEOUT = 90
SETTLE_MS = 1200
SNIPPET = 60
LISTED = 12
CARD_PREFIX = re.compile(r"^(?:holdout-|s\d+-)+")
REPEAT = re.compile(r"-\d+$")
AMOUNT_CELL = re.compile(r"^\d{1,3}(?:,\d{3})+$|^\d+$")
RATE_CELL = re.compile(r"^(\d+(?:\.\d+)?)%$")
# A figure wherever it stands, a Chinese character right before it included; only a digit, a letter or a
# separator in front rules it out (part of a code, a date or a longer number).
FIGURE = re.compile(r"(?<![0-9.,])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?(?![\d,])")
HTML_BLOCK = re.compile(r"```html\s*\n(.*?)```", re.S)
TIMES = chr(0xD7)
# Inline markup joins the text around it into one line; every other tag starts a line of its own.
INLINE_TAGS = frozenset(
    "span b i strong em a u small sup sub code mark abbr time label font s del ins q cite var kbd tspan text".split()
)
CSS_KEYWORDS = frozenset({"inherit", "initial", "unset", "revert", "revert-layer"})

_STYLE = re.compile(r"<style[^>]*>(.*?)</style>", re.S | re.I)
_INLINE = re.compile(r"""\sstyle\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)
_FONT_DECL = re.compile(r"font-family\s*:\s*([^;}]+)", re.I)
_FONT_ATTR = re.compile(r"""font-family\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)
_HEX = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})\b")
_FUNC = re.compile(r"\b(?:rgba?|hsla?)\([^)]*\)", re.I)
_PAINT = re.compile(r"""\s(?:fill|stroke|stop-color|flood-color|color|bgcolor)\s*=\s*(?:"([^"]*)"|'([^']*)')""", re.I)
_DECL = re.compile(r"([a-zA-Z-]+)\s*:\s*([^;{}]+)")
_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
_GRADIENT = re.compile(r"(?:repeating-)?(?:linear|radial|conic)-gradient\s*\(|<(?:linear|radial)Gradient\b", re.I)
_SHADOW = re.compile(r"(?:box-shadow|text-shadow)\s*:\s*(?!\s*none)[^;}\"']+|drop-shadow\s*\(", re.I)
_FILTER = re.compile(r"(?:^|[\s;{])(?:backdrop-)?filter\s*:\s*(?!\s*none\b)[^;}\"']+", re.I)
_PSEUDO = re.compile(r"::?(?:before|after)\b", re.I)
_MOTION = {
    "keyframes": re.compile(r"@keyframes\b", re.I),
    "animation": re.compile(r"\banimation(?:-name)?\s*:\s*(?!\s*none\b)[^;}\"']+", re.I),
    "transition": re.compile(r"\btransition(?:-property|-duration)?\s*:\s*(?!\s*(?:none|0s?|all 0s)\b)[^;}\"']+", re.I),
    "script animation": re.compile(r"requestAnimationFrame|\.animate\s*\(|setInterval\s*\(", re.I),
}
_REFS = (
    re.compile(r"""<link\b[^>]*\bhref\s*=\s*["']([^"']+)["']""", re.I),
    re.compile(r"""<(?:script|img|iframe|video|audio|source|embed|track)\b[^>]*\bsrc\s*=\s*["']([^"']+)["']""", re.I),
    re.compile(r"""<object\b[^>]*\bdata\s*=\s*["']([^"']+)["']""", re.I),
    re.compile(r"""url\(\s*["']?([^"')]+)["']?\s*\)""", re.I),
    re.compile(r"""@import\s+["']([^"']+)["']""", re.I),
)
_TITLE = re.compile(r"<(h1|title)\b[^>]*>(.*?)</\1>", re.S | re.I)
_TAGS = re.compile(r"<[^>]+>")
_SLIDES = re.compile(r"""class\s*=\s*["'][^"']*\bslide\b""", re.I)
_NAVIGATION = re.compile(r"keydown|ArrowRight|ArrowLeft", re.I)
_NAMED = {
    "white": "#FFFFFF",
    "black": "#000000",
    "red": "#FF0000",
    "blue": "#0000FF",
    "green": "#008000",
    "gray": "#808080",
    "grey": "#808080",
    "orange": "#FFA500",
    "yellow": "#FFFF00",
    "purple": "#800080",
    "navy": "#000080",
    "silver": "#C0C0C0",
    "gold": "#FFD700",
    "pink": "#FFC0CB",
    "teal": "#008080",
}
_COLOURED = re.compile(r"colou?r|background|border|fill|stroke|outline|shadow|caret|decoration")

# What the page shows in the meeting-room browser. Every text node is measured for size (transforms, zoom and, inside
# SVG, the screen transform applied), colour, font, visibility and clipping; each is tied to the nearest block element
# it sits in and carries its line boxes, so a line of a block is compared with lines of other blocks, never with the
# rest of its own wrapped text. Lists, the logo, empty coloured boxes and motion are reported beside.
PROBE = """(args) => {
  const W = innerWidth, H = innerHeight;
  const SKIP = ['SCRIPT', 'STYLE', 'TEMPLATE', 'NOSCRIPT', 'TITLE'];
  const scaleOf = (el) => {
    if (el.closest('svg')) {
      const m = typeof el.getScreenCTM === 'function' ? el.getScreenCTM() : null;
      return m ? Math.hypot(m.a, m.b) : 1;
    }
    let scale = 1;
    for (let a = el; a && a.nodeType === 1; a = a.parentElement) {
      const s = getComputedStyle(a);
      if (s.transform && s.transform !== 'none') {
        const m = new DOMMatrixReadOnly(s.transform);
        scale *= Math.hypot(m.a, m.b);
      }
      scale *= parseFloat(s.zoom) || 1;
    }
    return scale;
  };
  const hidden = (el) => {
    for (let a = el; a && a.nodeType === 1; a = a.parentElement) {
      const s = getComputedStyle(a);
      if (s.display === 'none' || s.visibility === 'hidden' || s.visibility === 'collapse' || parseFloat(s.opacity) === 0) return true;
    }
    return false;
  };
  const clipper = (el, r) => {
    for (let a = el; a && a !== document.body && a !== document.documentElement; a = a.parentElement) {
      const s = getComputedStyle(a);
      if (/(hidden|clip|auto|scroll)/.test(s.overflowX + ' ' + s.overflowY)) {
        const b = a.getBoundingClientRect();
        if (r.left < b.left - 1 || r.right > b.right + 1 || r.top < b.top - 1 || r.bottom > b.bottom + 1) {
          return a.tagName.toLowerCase() + (typeof a.className === 'string' && a.className ? '.' + a.className.split(/\\s+/)[0] : '');
        }
      }
    }
    return null;
  };
  const blockOf = (el) => {
    const svg = el.closest('svg');
    if (svg) return svg;
    for (let a = el; a && a !== document.body; a = a.parentElement) {
      const d = getComputedStyle(a).display;
      if (!d.startsWith('inline') && d !== 'contents') return a;
    }
    return document.body;
  };
  const logoEl = [...document.querySelectorAll('svg, img')].find(e => {
    const r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && r.left < W * 0.25 && r.top < H * 0.25;
  }) || null;
  const box = (r) => [Math.round(r.left), Math.round(r.top), Math.round(r.right), Math.round(r.bottom)];
  const blocks = [], index = new Map(), texts = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node = walker.currentNode;
    const raw = node.textContent.replace(/\\s+/g, ' ');
    const el = node.parentElement;
    if (!raw.trim() || !el || SKIP.includes(el.tagName)) continue;
    const owner = blockOf(el);
    if (!index.has(owner)) {
      index.set(owner, blocks.length);
      const tag = owner.tagName.toLowerCase();
      blocks.push({parts: [], tag, kind: owner.closest('table') ? 'table' : (tag === 'li' ? 'li' : tag), lines: []});
    }
    const which = index.get(owner);
    const range = document.createRange();
    range.selectNodeContents(node);
    const r = range.getBoundingClientRect();
    const lines = [...range.getClientRects()].filter(q => q.width > 0 && q.height > 0).map(box);
    const s = getComputedStyle(el);
    const svg = !!el.closest('svg');
    blocks[which].parts.push(raw);
    blocks[which].lines.push(...lines);
    texts.push({
      text: raw.trim(),
      block: which,
      px: Math.round(parseFloat(s.fontSize) * scaleOf(el) * 10) / 10,
      color: s.color,
      font: s.fontFamily,
      box: box(r),
      lines,
      hidden: hidden(el) || r.width === 0 || r.height === 0,
      painted_overlap_candidates: [...document.querySelectorAll('body *')].filter(other => {
        if (other === el || other.contains(el) || el.contains(other)) return false;
        const style = getComputedStyle(other), q = other.getBoundingClientRect();
        const painted = style.backgroundImage !== 'none' || !/^rgba\\(0, 0, 0, 0\\)$|^transparent$/.test(style.backgroundColor);
        return painted && style.display !== 'none' && style.visibility !== 'hidden' && parseFloat(style.opacity) > 0
          && q.right > r.left && q.left < r.right && q.bottom > r.top && q.top < r.bottom;
      }).map(other => ({html: other.outerHTML, z_index: getComputedStyle(other).zIndex, box: box(other.getBoundingClientRect())})),
      occlusion_candidates: [...range.getClientRects()].filter(q => q.width > 0 && q.height > 0).map(q => {
        const x = Math.max(0, Math.min(W - 1, (q.left + q.right) / 2));
        const y = Math.max(0, Math.min(H - 1, (q.top + q.bottom) / 2));
        const top = document.elementFromPoint(x, y);
        return top && top !== el && !el.contains(top) && !top.contains(el) ? top.outerHTML : null;
      }).filter(Boolean),
      outside: lines.some(q => q[2] > W + 1 || q[3] > H + 1 || q[0] < -1 || q[1] < -1),
      clipped: clipper(el, r),
      ellipsis: s.textOverflow === 'ellipsis' && el.scrollWidth > el.clientWidth + 1,
      svg,
      logo: !!logoEl && (el === logoEl || logoEl.contains(el)),
    });
  }
  const done = blocks.map(b => ({
    text: b.parts.join('').replace(/\\s+/g, ' ').trim(),
    kind: b.kind,
    box: b.lines.length ? [Math.min(...b.lines.map(l => l[0])), Math.min(...b.lines.map(l => l[1])),
      Math.max(...b.lines.map(l => l[2])), Math.max(...b.lines.map(l => l[3]))] : null,
  }));
  const lists = [...document.querySelectorAll('ul, ol')].filter(l => !l.closest('table'))
    .map(l => [...l.children].filter(c => c.tagName === 'LI').map(li => li.innerText.replace(/\\s+/g, ' ').trim()).filter(Boolean))
    .filter(items => items.length);
  const root = document.scrollingElement || document.documentElement;
  const decor = {empty_coloured_boxes: [], svgs_besides_the_logo: 0, canvases: document.querySelectorAll('canvas').length};
  for (const e of document.querySelectorAll('body *')) {
    if (e.closest('svg')) { if (e.tagName.toLowerCase() === 'svg' && e !== logoEl) decor.svgs_besides_the_logo += 1; continue; }
    if (['SCRIPT', 'STYLE', 'TEMPLATE', 'IMG', 'CANVAS', 'BR', 'HR'].includes(e.tagName)) continue;
    if ((e.innerText || '').trim()) continue;
    const s = getComputedStyle(e), r = e.getBoundingClientRect();
    const painted = s.backgroundImage !== 'none' || !/^rgba\\(0, 0, 0, 0\\)$|^transparent$/.test(s.backgroundColor);
    if (painted && r.width * r.height >= 400 && decor.empty_coloured_boxes.length < 8) {
      decor.empty_coloured_boxes.push(e.tagName.toLowerCase() + (typeof e.className === 'string' && e.className ? '.' + e.className.split(/\\s+/)[0] : '') + ' ' + Math.round(r.width) + 'x' + Math.round(r.height));
    }
  }
  let transitions = 0;
  for (const e of document.querySelectorAll('*')) {
    if (getComputedStyle(e).transitionDuration.split(',').some(d => parseFloat(d) > 0)) transitions += 1;
  }
  const logoBox = logoEl ? logoEl.getBoundingClientRect() : null;
  return {
    scroll: [root.scrollWidth, root.scrollHeight],
    rendered_text: document.body.innerText,
    rendered_dom: document.body.outerHTML,
    tables: [...document.querySelectorAll('table')].map(table => [...table.rows].map(row => [...row.cells].map(cell => cell.innerText))),
    texts,
    blocks: done,
    lists,
    logo: logoBox ? [Math.round(logoBox.left), Math.round(logoBox.top), Math.round(logoBox.width), Math.round(logoBox.height)] : null,
    decor,
    animations: document.getAnimations().length,
    transitions,
  };
}"""


@dataclass(frozen=True)
class Vocabulary:
    """The words and rulers the owner's facts use, from the scenario's `reference.md` table."""

    found: dict

    @classmethod
    def load(cls, root) -> "Vocabulary":
        return cls(words(Path(root) / CONFIG))

    def one(self, key: str) -> str:
        return self.found[key][0]

    def all(self, key: str) -> tuple[str, ...]:
        return self.found.get(key, ())

    @property
    def projector(self) -> tuple[int, int]:
        width, height = self.found["projector"]
        return int(width), int(height)

    @property
    def floor(self) -> float:
        return float(self.one("body_floor"))

    @property
    def limits(self) -> tuple[int, int]:
        count, chars = self.found["points"]
        return int(count), int(chars)

    @property
    def palette(self) -> frozenset[str]:
        return frozenset(value.upper() for value in self.all("palette"))

    @property
    def amount_units(self) -> tuple[str, ...]:
        return tuple(unit for unit in self.all("units") if unit != "%")


@dataclass(frozen=True)
class Card:
    """One card's rulers: its region, the reported period (`YYYY-MM`), the finance table that applies (`q3`, the
    October table's `first` issue or its `second`), the draft's figures finance corrected or a later issue replaced,
    the business figures the director confirms and the handout carrying the page to start from."""

    name: str
    region: str
    period: str
    issue: str
    stale: tuple[str, ...] = ()
    confirmed: tuple[str, ...] = ()
    base: str = ""


def cards(root) -> dict[str, Card]:
    """The per-card table of `reference.md`: a row per card whose first cell is the card's name."""
    found = {}
    for table in tables((Path(root) / CONFIG).read_text()):
        header, *rows = table
        if len(header) < 7:
            continue
        for row in rows:
            if not re.fullmatch(r"[a-z]+", row[0]) or len(row) < 7:
                continue
            ticks = [re.findall(r"`([^`]+)`", cell) for cell in row]
            found[row[0]] = Card(
                name=row[0],
                region=ticks[1][0],
                period=ticks[2][0],
                issue=ticks[3][0],
                stale=tuple(ticks[4]),
                confirmed=tuple(ticks[5]),
                base=ticks[6][0] if ticks[6] else "",
            )
    return found


@dataclass
class Book:
    """One finance-table material read into rows: per region and per (region, city) the amounts (10k yuan) and rates
    of its row in table order, each region's flash-report figures, and the first-issue Q4 values a revision replaced."""

    regions: dict[str, tuple[list[int], list[Decimal]]] = field(default_factory=dict)
    cities: dict[tuple[str, str], tuple[list[int], list[Decimal]]] = field(default_factory=dict)
    flash: dict[tuple[str, str], int] = field(default_factory=dict)
    revised: dict[str, tuple[list[int], list[Decimal]]] = field(default_factory=dict)


def _cells(row) -> tuple[list[int], list[Decimal]]:
    amounts = [int(cell.replace(",", "")) for cell in row if AMOUNT_CELL.match(cell)]
    rates = [Decimal(found.group(1)) for cell in row if (found := RATE_CELL.match(cell))]
    return amounts, rates


def book(text: str, vocabulary: Vocabulary) -> Book:
    """The rows of one finance table, told apart by their headers: the region table, the city table, the table of
    differences from the sales-system flash report and the table of what the second issue changed."""
    regions, out = set(vocabulary.all("regions")), Book()
    region_header, city_header = vocabulary.one("region_header"), vocabulary.one("city_header")
    flash_mark, first_mark = vocabulary.one("flash_mark"), vocabulary.one("first_issue_mark")
    for header, *rows in tables(frontmatter(text)[1]):
        if not header or header[0] != region_header:
            continue
        flashed = any(flash_mark in cell for cell in header)
        revision = any(first_mark in cell for cell in header)
        for row in rows:
            if row[0] not in regions:
                continue
            if flashed and len(row) > 2:
                amounts, _ = _cells(row[2:3])
                if amounts:
                    out.flash[(row[0], row[1])] = amounts[0]
            elif revision:
                out.revised[row[0]] = _cells(row[1:])
            elif len(header) > 1 and header[1] == city_header:
                out.cities[(row[0], row[1])] = _cells(row[2:])
            else:
                amounts, rates = _cells(row[1:])
                if rates:
                    out.regions[row[0]] = (amounts, rates)
    return out


def yi(amount: int) -> Decimal:
    """10k yuan in 100-million yuan, two decimals, half up."""
    return (Decimal(amount) / 10000).quantize(Decimal("0.01"), ROUND_HALF_UP)


def whole(rate: Decimal) -> Decimal:
    return rate.quantize(Decimal("1"), ROUND_HALF_UP)


@dataclass(frozen=True)
class Allowed:
    """What a page for this card may show: rates (`pct`), amounts in 100-million yuan (`dec`) and amounts in 10k
    yuan (`int`); the figures finance corrected or a later issue replaced (`stale`); the director's figures; and the
    cities below their target with the region's own rate."""

    pct: frozenset[Decimal]
    dec: frozenset[Decimal]
    int: frozenset[Decimal]
    stale: frozenset[tuple[str, Decimal]]
    director: frozenset[tuple[str, Decimal]]
    below: tuple[tuple[str, Decimal], ...]
    region_rate: Decimal | None = None

    def kind(self, kind: str) -> frozenset[Decimal]:
        return {"pct": self.pct, "dec": self.dec, "int": self.int}[kind]


def shown(kind: str, value: Decimal) -> str:
    """A figure as a person writes it: thousands separated, a percent sign on a rate."""
    if kind == "pct":
        return f"{value}%"
    return f"{value:,}" if kind == "int" else str(value)


def tokens(text: str) -> list[tuple[str, Decimal]]:
    """Figures written in a ruler cell (`1.83`, `91.6%`, `18,326`) as (kind, value)."""
    out = []
    for found in FIGURE.finditer(text):
        kind, value = _kind(found, text)
        out.append((kind, value))
    return out


def _kind(found: re.Match, text: str) -> tuple[str, Decimal]:
    whole_part, decimals = found.group(1), found.group(2)
    value = Decimal(whole_part.replace(",", "") + (f".{decimals}" if decimals else ""))
    after = text[found.end() :].lstrip()
    if after.startswith("%"):
        return "pct", value
    return ("dec" if decimals else "int"), value


def region_row(card: Card, books: dict[str, Book]) -> tuple[list[int], list[Decimal]] | None:
    """The region's row of the table that applies: for a card on the October table's first issue, the Q4 target and
    progress of that issue put back in place of the second issue's."""
    table = books["q3" if card.issue == "q3" else "oct"]
    region = table.regions.get(card.region)
    revision = table.revised.get(card.region)
    if region is None:
        return None
    amounts, rates = list(region[0]), list(region[1])
    if revision and card.issue == "first":
        (first, second), (first_rate, second_rate) = revision
        amounts = [first if amount == second else amount for amount in amounts]
        rates = [first_rate if rate == second_rate else rate for rate in rates]
    return amounts, rates


def city_rows(card: Card, books: dict[str, Book]) -> list[tuple[str, tuple[list[int], list[Decimal]]]]:
    table = books["q3" if card.issue == "q3" else "oct"]
    return [(city, row) for (name, city), row in table.cities.items() if name == card.region]


def allowed(card: Card, books: dict[str, Book], vocabulary: Vocabulary) -> Allowed:
    """The figures the applicable table gives for the card's region, as a page may write them: the region's amounts
    in 100-million yuan, a city's in 10k yuan, rates to one decimal or whole, and a gap or surplus taken from the
    10k-yuan figures before conversion (the requirements' 3.5)."""
    table = books["q3" if card.issue == "q3" else "oct"]
    pct, dec, ints, below = set(), set(), set(), []
    region = region_row(card, books)
    rows = [(card.region, region)] if region else []
    rows += city_rows(card, books)
    stale = {item for value in card.stale for item in tokens(value)}
    revision = table.revised.get(card.region)
    if revision and card.issue == "first":
        (_, second), (_, second_rate) = revision
        stale |= {("int", Decimal(second)), ("dec", yi(second)), ("pct", second_rate), ("pct", whole(second_rate))}
    elif revision and card.issue == "second":
        stale |= {("int", Decimal(revision[0][0])), ("dec", yi(revision[0][0]))}
        stale |= {("pct", revision[1][0]), ("pct", whole(revision[1][0]))}
    elif card.issue == "q3" and (later := books["oct"].revised.get(card.region)):
        stale |= {("int", Decimal(later[0][1])), ("dec", yi(later[0][1]))}
    region_rate = None
    for index, (name, (amounts, rates)) in enumerate(rows):
        ints |= {Decimal(amount) for amount in amounts}
        if index == 0:
            dec |= {yi(amount) for amount in amounts}
        for start in range(0, len(amounts) - 1, 2):
            gap = abs(amounts[start] - amounts[start + 1])
            ints.add(Decimal(gap))
            if index == 0:
                dec.add(yi(gap))
        pct |= {whole(rate) for rate in rates}
        if index == 0:
            region_rate = whole(rates[0]) if rates else None
        elif rates and rates[0] < 100:
            below.append((name, whole(rates[0])))
    director = {item for value in card.confirmed for item in tokens(value)}
    known = {("pct", value) for value in pct} | {("dec", value) for value in dec} | {("int", value) for value in ints}
    return Allowed(
        frozenset(pct),
        frozenset(dec),
        frozenset(ints),
        frozenset(stale - known),
        frozenset(director),
        tuple(below),
        region_rate,
    )


def figures(text: str, vocabulary: Vocabulary) -> list[tuple[str, Decimal, str]]:
    """The figures a page states, as (kind, value, the line they stand on); dates, quarter names, sizes and small
    bare counts are not figures."""
    dates = vocabulary.all("date_words")
    out = []
    for line in (text or "").splitlines():
        for found in FIGURE.finditer(line):
            before, after = line[: found.start()].rstrip(), line[found.end() :].lstrip()
            if any(after.startswith(word) for word in dates) or after[:2].lower() in ("px", "pt"):
                continue
            if before.endswith(("Q", "q", "V", "v", "x", TIMES)) or after.startswith(("x", TIMES)):
                continue
            kind, value = _kind(found, line)
            if kind == "int" and value < 100 and not after.startswith(tuple(vocabulary.all("units"))):
                continue
            out.append((kind, value, line.strip()))
    return out


def figure_facts(text: str, card: Card, books: dict, vocabulary: Vocabulary) -> dict:
    """Each figure on the page against the applicable table: matched, a corrected or replaced figure, the
    director's own figure (with whether the forecast mark stands on its line), or found nowhere."""
    rules = allowed(card, books, vocabulary)
    forecast = vocabulary.one("forecast")
    stale, director, unmatched, matched = [], [], [], 0
    for kind, value, line in figures(text, vocabulary):
        if value in rules.kind(kind):
            matched += 1
        elif (kind, value) in rules.stale:
            stale.append(f"{shown(kind, value)} in: {line}")
        elif (kind, value) in rules.director:
            director.append({"figure": shown(kind, value), "line": line, "forecast_mark": forecast in line})
        else:
            unmatched.append(f"{shown(kind, value)} in: {line}")
    found = {"scalar_values_found_in_table": matched}
    if stale:
        found["corrected_or_replaced_figures"] = stale[:LISTED]
    if director:
        found["director_figures"] = director[:LISTED]
    if unmatched:
        found["figures_not_in_the_table"] = unmatched[:LISTED]
    return found


def data_block(text: str, card: Card, books: dict, vocabulary: Vocabulary) -> dict:
    """The items the requirements' 3.4 asks the data block to carry for the reported period, and which of them the
    page states somewhere: the region's figures in 100-million yuan, each city's in 10k yuan, rates whole or to one
    decimal (the Q4 cumulative of October is the month's own figure and is not listed twice)."""
    on_page = {(kind, value) for kind, value, _ in figures(text, vocabulary)}
    region = region_row(card, books)
    required: list[tuple[str, set[tuple[str, Decimal]]]] = []

    def rate(label, value):
        required.append((f"{label} {value}%", {("pct", whole(value))}))

    if region:
        amounts, rates = region
        period = "quarter" if card.issue == "q3" else "month"
        required.append((f"{card.region} {period} target {yi(amounts[0])}", {("dec", yi(amounts[0]))}))
        required.append((f"{card.region} {period} actual {yi(amounts[1])}", {("dec", yi(amounts[1]))}))
        rate(f"{card.region} {period} rate", rates[0])
        if card.issue != "q3" and len(amounts) > 2 and len(rates) > 1:
            required.append((f"{card.region} Q4 target {yi(amounts[2])}", {("dec", yi(amounts[2]))}))
            required.append((f"{card.region} Q4 cumulative actual {yi(amounts[3])}", {("dec", yi(amounts[3]))}))
            rate(f"{card.region} Q4 progress", rates[1])
    for city, (amounts, rates) in city_rows(card, books):
        required.append((f"{city} target {amounts[0]:,}", {("int", Decimal(amounts[0]))}))
        required.append((f"{city} actual {amounts[1]:,}", {("int", Decimal(amounts[1]))}))
        rate(f"{city} rate", rates[0])
    missing = [label for label, forms in required if not forms & on_page]
    return {
        "required": len(required),
        "scalar_present": len(required) - len(missing),
        "scalar_missing": missing,
        "required_items": [
            {"label": label, "allowed_scalar_forms": [shown(kind, value) for kind, value in sorted(forms)]}
            for label, forms in required
        ],
        "scope": "Scalar presence does not bind a value to its row, label, unit, period or required occurrence. Region amounts need two decimals in yi; cities need wan; rates need whole percentages. Q4 cumulative must be explicitly labeled even when equal to the month actual.",
    }


def later_months(line: str, card: Card, vocabulary: Vocabulary) -> list[int]:
    """Months a line names other than as a date or the meeting's own month: the months a recovery is promised for."""
    year, month = vocabulary.all("date_words")[:2]
    meeting = vocabulary.one("meeting").split("{month}")[1]
    reported = int(card.period.split("-")[1])
    found = []
    for match in re.finditer(rf"(?<![\d{year}])(\d{{1,2}})\s*{month}", line):
        if (
            line[: match.start()].rstrip().endswith(year)
            or line[match.start() :].replace(" ", "").find(match.group(1) + meeting) == 0
        ):
            continue
        if int(match.group(1)) != reported:
            found.append(int(match.group(1)))
    return found


def names_an_amount(line: str, vocabulary: Vocabulary) -> bool:
    units = "|".join(re.escape(unit) for unit in vocabulary.amount_units)
    return bool(re.search(rf"\d\s*(?:{units})", line))


def below_target(text: str, card: Card, books: dict, vocabulary: Vocabulary) -> dict:
    """The cities of the applicable table below target, each with the page lines that name it and whether such a
    line promises a later month, names an amount or carries the forecast mark; beside them every line of the page
    that promises a later month, since a reason and its recovery may stand on separate lines. The region's own
    shortfall is accounted for through its cities."""
    forecast = vocabulary.one("forecast")
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    rules = allowed(card, books, vocabulary)
    cities = []
    for name, rate in rules.below:
        named = [line for line in lines if name in line]
        cities.append(
            {
                "name": name,
                "rate": f"{rate}%",
                "lines": named,
                "a_line_names_a_later_month": any(later_months(line, card, vocabulary) for line in named),
                "a_line_names_an_amount": any(names_an_amount(line, vocabulary) for line in named),
                "a_line_has_the_forecast_mark": any(forecast in line for line in named),
            }
        )
    recovery = [
        {
            "line": line,
            "months": later_months(line, card, vocabulary),
            "amount": names_an_amount(line, vocabulary),
            "forecast_mark": forecast in line,
        }
        for line in lines
        if later_months(line, card, vocabulary)
    ]
    found = {"region_rate": f"{rules.region_rate}%" if rules.region_rate is not None else None, "cities": cities}
    if recovery:
        found["recovery_lines"] = recovery[:LISTED]
    return found


def _hex(token: str) -> tuple[str, bool]:
    """A colour as #RRGGBB and whether it carries transparency."""
    token = token.strip()
    if token.startswith("#"):
        digits = token[1:]
        if len(digits) in (3, 4):
            digits = "".join(char * 2 for char in digits)
        return "#" + digits[:6].upper(), len(digits) == 8 and digits[6:].upper() != "FF"
    if token.lower().startswith("rgb"):
        parts = re.findall(r"[\d.]+%?", token)
        if len(parts) >= 3:
            channels = [round(float(p[:-1]) * 2.55) if p.endswith("%") else round(float(p)) for p in parts[:3]]
            alpha = len(parts) > 3 and float(parts[3].rstrip("%")) < (100 if parts[3].endswith("%") else 1)
            return "#" + "".join(f"{max(0, min(255, c)):02X}" for c in channels), alpha
    return token.lower(), "hsla" in token.lower()


def _external(reference: str) -> bool:
    """A reference that leaves the file: not a fragment of the page itself (`url(#gradient)`, `href="#top"`) and
    not an inline data URL."""
    return not reference.startswith(("#", "data:"))


def source_facts(html: str, vocabulary: Vocabulary) -> dict:
    """What a page's source declares: fonts, references outside the file, colours (read from declaration values and
    SVG paint attributes, never from selectors), gradients, shadows, filters, decorated pseudo-elements, motion,
    slides and navigation, and its title."""
    css = [*_STYLE.findall(html), *(a or b for a, b in _INLINE.findall(html))]
    css_text = "\n".join(css)
    families = set()
    for value in [*_FONT_DECL.findall(css_text), *(a or b for a, b in _FONT_ATTR.findall(html))]:
        families |= {
            part.strip().strip("\"'").strip()
            for part in value.split(",")
            if part.strip() and part.strip().strip("\"'").strip().lower() not in CSS_KEYWORDS
        }
    allowed_fonts = {font.lower() for font in vocabulary.all("fonts")}
    colours, translucent = Counter(), set()
    for text in css:
        for prop, value in _DECL.findall(text):
            for token in [*_HEX.findall(value), *_FUNC.findall(value)]:
                colour, alpha = _hex(token)
                colours[colour] += 1
                if alpha:
                    translucent.add(token)
            if _COLOURED.search(prop.lower()):
                for word in re.findall(r"[a-zA-Z]+", value):
                    if word.lower() in _NAMED:
                        colours[_NAMED[word.lower()]] += 1
    for a, b in _PAINT.findall(html):
        value = (a or b).strip()
        if value.startswith("#") or value.lower().startswith(("rgb", "hsl")):
            colour, alpha = _hex(value)
            colours[colour] += 1
            if alpha:
                translucent.add(value)
        elif value.lower() in _NAMED:
            colours[_NAMED[value.lower()]] += 1
    references = sorted({ref for pattern in _REFS for ref in pattern.findall(html) if _external(ref)})
    decorated = 0
    for selector, body in _RULE.findall(css_text):
        if _PSEUDO.search(selector) and re.search(r"background|border|content\s*:\s*(?!\s*(?:none|\"\"|''))", body):
            decorated += 1
    found = {
        "fonts_declared": sorted(families),
        "fonts_outside_the_rule": sorted(font for font in families if font.lower() not in allowed_fonts),
        "web_fonts": "@font-face" in css_text.lower(),
        "references_outside_the_file": references,
        "colours_outside_the_palette": {
            colour: count for colour, count in sorted(colours.items()) if colour not in vocabulary.palette
        },
        "translucent_colours": sorted(translucent),
        "gradients": len(_GRADIENT.findall(html)),
        "shadows": len(_SHADOW.findall(css_text)),
        "filters": len(_FILTER.findall(css_text)),
        "pseudo_element_decorations": decorated,
        "motion": {name: len(pattern.findall(html)) for name, pattern in _MOTION.items() if pattern.search(html)},
        "slide_sections": len(_SLIDES.findall(html)),
        "keyboard_navigation": bool(_NAVIGATION.search(html)),
        "editable": "contenteditable" in html.lower(),
    }
    titles = {}
    for tag, text in _TITLE.findall(html):
        titles.setdefault(tag.lower(), _TAGS.sub("", text).strip())
    if titles.get("h1"):
        found["h1"] = titles["h1"]
    if titles.get("title"):
        found["document_title"] = titles["title"]
    return {key: value for key, value in found.items() if value not in ((), [], {}, 0, False, "")}


def chars(text: str) -> int:
    """A point's length as the meeting rules count it: every character but whitespace."""
    return len(re.sub(r"\s", "", text))


def _rgb(value: str) -> str:
    return _hex(value)[0] if value.lower().startswith("rgb") else value


def _render(path: Path, vocabulary: Vocabulary, shot: Path | None) -> dict:
    from playwright.sync_api import sync_playwright

    width, height = vocabulary.projector
    blocked = []

    def route(request_route):
        url = request_route.request.url
        if url.startswith(("file:", "data:", "about:")):
            request_route.continue_()
        else:
            blocked.append(url[:120])
            request_route.abort()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=browser_executable(), args=["--no-sandbox"])
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.route("**/*", route)
            page.goto(Path(path).resolve().as_uri(), timeout=30000)
            page.wait_for_timeout(SETTLE_MS)
            probed = page.evaluate(PROBE, {})
            if shot is not None:
                page.screenshot(path=str(shot))
        finally:
            browser.close()
    probed["blocked"] = blocked
    return probed


def rendered(path: Path, vocabulary: Vocabulary, shot: Path | None = None) -> dict:
    """The page as the meeting-room browser shows it, measured in a worker thread (the owner judges inside an event
    loop, where Playwright's synchronous API cannot run); a page that cannot be rendered says why."""
    if browser_executable() is None:
        return {"error": "no headless Chromium on this machine; the page was not rendered"}
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        try:
            return pool.submit(_render, path, vocabulary, shot).result(timeout=RENDER_TIMEOUT)
        except Exception as exc:  # noqa: BLE001 -- a page that cannot be rendered is reported, not fatal
            return {"error": f"the page could not be rendered: {exc}"[:300]}


def render_facts(probed: dict, vocabulary: Vocabulary, floor_in_force: bool) -> dict:
    """The rendering's facts: what does not fit, what is hidden, every size against the floor (the logo and the
    source line's block left out), the title, the source line, the logo, the lists, decoration and what the warning
    colour marks."""
    if "error" in probed:
        return {"rendered": probed["error"]}
    width, height = vocabulary.projector
    source, warning = vocabulary.one("source_mark"), vocabulary.one("warning").upper()
    texts, blocks = probed["texts"], probed.get("blocks", [])
    shown_ = [text for text in texts if not text["hidden"]]
    source_blocks = {index for index, block in enumerate(blocks) if source in block["text"]}
    body = [text for text in shown_ if not text["logo"]]
    others = [text for text in body if text["block"] not in source_blocks]
    title = max((text for text in others if not text["svg"]), key=lambda text: text["px"], default=None)
    found = {
        "viewport": f"{width}x{height}",
        "page_scrolls": probed["scroll"][0] > width + 1 or probed["scroll"][1] > height + 1,
        "content_size": probed["scroll"],
        "text_outside_the_screen": [text["text"][:40] for text in shown_ if text["outside"]][:LISTED],
        "clipped_text": [f"{text['text'][:40]} (by {text['clipped']})" for text in shown_ if text["clipped"]][:LISTED],
        "ellipsis_text": [text["text"][:40] for text in shown_ if text["ellipsis"]][:LISTED],
        "hidden_text": [text["text"][:40] for text in texts if text["hidden"]][:LISTED],
        "overlapping_text": overlaps(body),
        "blocked_requests": probed.get("blocked", []),
        "occlusion_candidates": [
            {"text": text["text"], "covering_elements": text.get("occlusion_candidates")}
            for text in texts
            if text.get("occlusion_candidates")
        ],
        "painted_overlap_candidates": [
            {"text": text["text"], "painted_elements": text.get("painted_overlap_candidates")}
            for text in texts
            if text.get("painted_overlap_candidates")
        ],
        "visibility_scope": "Text-node rectangles, clipping and sampled hit tests are partial observations. Empty occlusion candidates do not prove visibility, especially pointer-events:none, canvas, pseudo-elements or complex masks. Use screenshots/full DOM; otherwise unresolved visual criteria remain unknown.",
        "running_animations": probed["animations"],
        "elements_with_transitions": probed["transitions"],
    }
    if title:
        found["largest_text"] = {"text": title["text"][:SNIPPET], "px": title["px"]}
    if source_blocks:
        index = min(source_blocks)
        block = blocks[index]
        sizes = [text["px"] for text in body if text["block"] == index]
        box = block["box"] or [0, 0, 0, 0]
        found["source_line"] = {
            "text": block["text"][:SNIPPET],
            "px": min(sizes) if sizes else None,
            "box": box,
            "at_bottom_right": box[2] >= width * 0.7 and box[3] >= height * 0.8,
        }
    else:
        found["source_line"] = None
    if others:
        found["smallest_text_px"] = min(text["px"] for text in others)
    found["size_floor_in_force"] = floor_in_force
    small = [f"{text['text'][:30]} ({text['px']}px)" for text in others if text["px"] < vocabulary.floor - 0.5]
    if small:
        found["text_below_the_floor"] = small[:LISTED]
        found["text_below_the_floor_count"] = len(small)
    found["logo_box_top_left"] = probed.get("logo")
    found["warning_colour_texts"] = [text["text"][:30] for text in body if _rgb(text["color"]) == warning][:LISTED]
    found["text_colours_outside_the_palette"] = sorted({_rgb(text["color"]) for text in body} - vocabulary.palette)
    found["rendered_fonts"] = sorted({text["font"].split(",")[0].strip("\"' ") for text in body if not text["svg"]})
    count, longest = vocabulary.limits
    lists = probed.get("lists") or []
    main = max(lists, key=lambda items: sum(chars(item) for item in items), default=[])
    found["points"] = [{"text": point[:SNIPPET], "chars": chars(point)} for point in main]
    found["points_over_length"] = [point["text"] for point in found["points"] if point["chars"] > longest]
    if len(lists) > 1:
        found["other_lists"] = [len(items) for items in lists if items is not main]
    if not found["points"]:
        loose = [block for index, block in enumerate(blocks) if block["kind"] not in ("li", "table", "svg")]
        found["other_text_blocks"] = [
            {"text": block["text"][:SNIPPET], "chars": chars(block["text"])} for block in loose
        ][:LISTED]
    decor = probed.get("decor") or {}
    decorations = {key: value for key, value in decor.items() if value}
    if decorations:
        found["decorations"] = decorations
    return {key: value for key, value in found.items() if value not in ([], {}, "")}


def overlaps(texts: list[dict]) -> list[str]:
    """Pairs of texts from different blocks whose line boxes cover each other by more than a third of the smaller
    line; the lines of one wrapped block never overlap each other."""
    found = []
    for index, first in enumerate(texts):
        for second in texts[index + 1 :]:
            if first["block"] == second["block"]:
                continue
            if any(_covers(a, b) for a in first["lines"] for b in second["lines"]):
                found.append(f"{first['text'][:20]} / {second['text'][:20]}")
            if len(found) >= 5:
                return found
    return found


def _covers(a, b) -> bool:
    wide, high = min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1])
    if wide <= 0 or high <= 0:
        return False
    smaller = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1])) or 1
    return wide * high > smaller / 3


def pages(exchanges) -> list[tuple[int, Path]]:
    """Every web page handed over, in order, as (turn, the copy kept for that turn)."""
    return [
        (number, Path(path))
        for number, turn in enumerate(exchanges, 1)
        for path in turn.execution.deliverables
        if Path(path).suffix.lower() in PAGE_SUFFIXES and Path(path).is_file()
    ]


def written(records) -> dict[str, str | None]:
    """The files a drill's records show written, by path, with their last content where the record carries it."""
    found: dict[str, str | None] = {}
    for row in records:
        if row.get("kind") == "child.execution":
            found.update({path: text for path, text in written(row.get("records") or ()).items()})
            continue
        event = row.get("event") or {}
        if row.get("kind") != "runner.event" or event.get("phase") != "complete" or event.get("ok") is not True:
            continue
        change = event.get("file_change") or {}
        if change.get("path") and isinstance(change.get("after"), str):
            found[str(change["path"])] = change["after"]
        for item in event.get("file_written") or ():
            if isinstance(item, dict) and item.get("path"):
                found.setdefault(str(item["path"]), None)
    return found


def tool_history(exchanges):
    """Preserve full native write/delivery evidence for reconciliation at each handoff, including child calls."""
    result = []

    def visit(rows, turn, actor, scope):
        for row in rows:
            if row.get("kind") == "child.execution":
                visit(
                    row.get("records") or (),
                    turn,
                    row.get("harness"),
                    {key: row.get(key) for key in ("launch", "pid", "log", "omitted")},
                )
            elif row.get("kind") == "runner.event" and row.get("event_type", "ToolEvent") == "ToolEvent":
                result.append(
                    {
                        "collected_turn": turn,
                        "actor": actor,
                        "scope": scope,
                        "event": row.get("event"),
                        "observed_at": row.get("observed_at"),
                        "monotonic_ns": row.get("monotonic_ns"),
                    }
                )

    for number, exchange in enumerate(exchanges, 1):
        visit(exchange.execution.records, number, "assistant", "root")
    return result


def page_versions(exchanges) -> list[tuple[int, Path, str | None]]:
    """Retained delivery occurrences only; earlier reuse of one mutable path remains unknown."""
    delivered = [
        (number, Path(path))
        for number, turn in enumerate(exchanges, 1)
        for path in turn.execution.deliverables
        if Path(path).suffix.lower() in PAGE_SUFFIXES
    ]
    last = {str(path): index for index, (_, path) in enumerate(delivered)}
    versions = []
    for index, (turn, path) in enumerate(delivered):
        text = None
        if last[str(path)] == index:
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError):
                pass
        versions.append((turn, path, text))
    return versions


def _declarations(html: str) -> Counter:
    css = [*_STYLE.findall(html), *(a or b for a, b in _INLINE.findall(html))]
    return Counter(
        f"{prop.strip().lower()}: {' '.join(value.split())}" for text in css for prop, value in _DECL.findall(text)
    )


def changes(before: str, after: str) -> dict:
    """What changed from one version of a page to the next: the visible lines removed and added, and the style
    declarations removed and added (rule order aside)."""
    old, new = before.splitlines(), after.splitlines()
    removed, added = [], []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if tag in ("replace", "delete"):
            removed += old[i1:i2]
        if tag in ("replace", "insert"):
            added += new[j1:j2]
    return {"text_removed": removed, "text_added": added}


def page_changes(before_html: str, after_html: str, before_text: str, after_text: str) -> dict:
    text = changes(before_text, after_text)
    old, new = _declarations(before_html), _declarations(after_html)
    gone, came = sorted((old - new).elements()), sorted((new - old).elements())
    return {
        "visible_lines_removed": [line[:SNIPPET] for line in text["text_removed"]][:LISTED],
        "visible_lines_added": [line[:SNIPPET] for line in text["text_added"]][:LISTED],
        "unchanged_visible_lines": len(set(before_text.splitlines()) & set(after_text.splitlines())),
        "style_declarations_removed": gone[:LISTED],
        "style_declarations_added": came[:LISTED],
        "style_declarations_changed": len(gone) + len(came),
        "full_source_before": before_html,
        "full_source_after": after_html,
        "source_changes": changes(before_html, after_html),
        "style_rules_before": _STYLE.findall(before_html),
        "style_rules_after": _STYLE.findall(after_html),
        "scope": "Declaration counts omit selectors, cascade order, class/DOM association and script effects. Compare complete source and rendered evidence; equivalent markup is not automatically a changed layout. Unknown prior delivery bytes do not prove unchanged appearance.",
    }


class _Visible(HTMLParser):
    """The visible text of a page, one block per line: inline markup inside a block joins its text, every other tag
    and a line break end the line."""

    HIDDEN = ("script", "style", "template", "title")

    def __init__(self):
        super().__init__()
        self.lines, self.buffer, self.hidden = [], [], 0

    def _flush(self):
        line = " ".join("".join(self.buffer).split())
        if line:
            self.lines.append(line)
        self.buffer = []

    def handle_starttag(self, tag, attrs):
        if tag in self.HIDDEN:
            self.hidden += 1
        elif tag not in INLINE_TAGS:
            self._flush()

    def handle_startendtag(self, tag, attrs):
        if tag not in INLINE_TAGS:
            self._flush()

    def handle_endtag(self, tag):
        if tag in self.HIDDEN:
            self.hidden = max(self.hidden - 1, 0)
        elif tag not in INLINE_TAGS:
            self._flush()

    def handle_data(self, data):
        if not self.hidden:
            self.buffer.append(data)

    def close(self):
        super().close()
        self._flush()


def visible(html: str) -> str:
    """A page source's visible text, one block per line, the way the owner reads a delivered page."""
    parser = _Visible()
    parser.feed(html)
    parser.close()
    return "\n".join(parser.lines)


def sheet_facts(page, files, page_text, vocabulary, *, workdir=None):
    """Read the actual contained reconciliation sheet; scalar membership is not occurrence provenance."""
    relative = Path(vocabulary.one("sheet_folder")) / (page.stem + ".md")
    if workdir is None:
        return {"status": "unavailable", "filed": None, "reason": "Replica workdir was not retained."}
    root = Path(workdir)
    path = root / relative
    try:
        if root.is_symlink() or not root.is_dir() or not path.resolve().is_relative_to(root.resolve()):
            return {"status": "unavailable", "filed": None, "reason": "The sheet escaped its replica root."}
        raw = path.read_bytes()
        text = raw.decode("utf-8")
    except FileNotFoundError:
        return {"status": "absent", "filed": False, "path": relative.as_posix()}
    except (OSError, UnicodeError, RuntimeError):
        return {"status": "unavailable", "filed": None, "reason": "The actual sheet bytes could not be read."}
    rows = tables(text)
    listed = {(kind, value) for table in rows for row in table[1:] for kind, value in tokens(row[0])}
    on_page = {(kind, value) for kind, value, _ in figures(page_text, vocabulary)}
    headers = vocabulary.all("sheet_headers")
    return {
        "status": "read",
        "filed": True,
        "path": relative.as_posix(),
        "named_after_the_page": True,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "content": text,
        "tables": rows,
        "has_required_headers": any(tuple(table[0]) == headers for table in rows),
        "rows": sum(max(len(table) - 1, 0) for table in rows),
        "page_scalars_absent_from_sheet": [shown(kind, value) for kind, value in sorted(on_page - listed)],
        "scope": "Every displayed occurrence needs a row with its location, exact source table/version/region-or-city/column or dated director confirmation, source value and consistency. Repeated equal values are distinct occurrences. A final sheet does not alone prove the sheet at an earlier delivery.",
    }


def meeting(card: Card, vocabulary: Vocabulary) -> tuple[str, str, str]:
    """The card's meeting name, page file name and the last day of the reported period."""
    year, month = (int(part) for part in card.period.split("-"))
    name = vocabulary.one("meeting").format(year=year, month=month)
    file = vocabulary.one("file_name").format(region=card.region, meeting=name)
    following = datetime.date(year + (month == 12), month % 12 + 1, 1)
    return name, file, (following - datetime.timedelta(days=1)).isoformat()


def base_page(card: Card, handouts: dict[str, Path]) -> str | None:
    """The page source a card hands over to start from (inside a markdown code block of one of its handouts)."""
    path = handouts.get(card.base)
    if not card.base or path is None or not path.is_file():
        return None
    found = HTML_BLOCK.search(path.read_text(errors="replace"))
    return found.group(1) if found else None


def facts(
    exchanges,
    card: Card | None,
    vocabulary: Vocabulary,
    books: dict[str, Book],
    *,
    base: str | None = None,
    filed: dict[str, str | None] | None = None,
    render=rendered,
    workdir=None,
) -> dict:
    """The owner's facts for one drill. `filed` adds files the drill left that the records do not carry; `render`
    measures a page in the browser (tests pass a stand-in)."""
    delivered = pages(exchanges)
    files = {path: text for turn in exchanges for path, text in written(turn.execution.records).items()}
    files.update(filed or {})
    found: dict = {}
    operations = tool_history(exchanges)
    if operations:
        found["tool_history"] = operations
        found["tool_history_scope"] = (
            "Pair start/completion in the same native scope and use inner host clocks, not collection order. Only strict boolean true supports successful completion. Attempts, failed/unknown writes, missing content or unobserved earlier sheet state cannot establish per-delivery reconciliation. Full final sheet contents do not erase earlier versions."
        )
    all_versions = page_versions(exchanges)
    if all_versions:
        found["delivery_versions"] = [
            {
                "turn": turn,
                "name": path.name,
                "sha256": hashlib.sha256(html.encode()).hexdigest() if html is not None else None,
                "html": html,
                "observation": "retained" if html is not None else "unavailable",
            }
            for turn, path, html in all_versions
        ]
    if delivered:
        found["pages_delivered"] = [{"turn": turn, "file": path.name} for turn, path in delivered]
    names = {path.name for _, path in delivered}
    extra = sorted({Path(path).name for path in files if Path(path).suffix.lower() in PAGE_SUFFIXES} - names)
    if extra:
        found["pages_written_not_handed_over"] = extra
    others = sorted(
        {Path(p).name for turn in exchanges for p in turn.execution.deliverables if Path(p).suffix not in PAGE_SUFFIXES}
    )
    if others:
        found["other_files_delivered"] = others
    floor_in_force = bool(card and card.period >= vocabulary.one("floor_from"))
    if card is not None:
        name, file, last = meeting(card, vocabulary)
        found["card"] = {
            "region": card.region,
            "meeting": name,
            "period_ends": last,
            "finance_table": {"q3": "Q3 table", "first": "October, first issue", "second": "October, second issue"}[
                card.issue
            ],
            "size_floor_and_recovery_rule_in_force": floor_in_force,
            "expected_file": file,
        }
        if delivered:
            found["file_named_as_expected"] = delivered[-1][1].name == file
    if not all_versions:
        return found
    if all_versions[-1][2] is None:
        found["final_page_observation"] = "unavailable; the final delivery must not fall back to an older readable page"
        return found
    page = all_versions[-1][1]
    html = all_versions[-1][2]
    source_text = visible(html)
    probed = render(page, vocabulary)
    text = probed["rendered_text"] if "rendered_text" in probed else source_text
    found["full_page_html"] = html
    found["source_text"] = source_text
    found["rendered_evidence"] = probed
    found["financial_text_source"] = (
        "rendered DOM" if "rendered_text" in probed else "source only; rendered numerical correctness unknown"
    )
    found["page"] = source_facts(html, vocabulary)
    found["render"] = render_facts(probed, vocabulary, floor_in_force)
    titles = [found["page"].get("h1", ""), (found["render"].get("largest_text") or {}).get("text", "")]
    topics = sorted({word for word in vocabulary.all("topic_words") for title in titles if word in title})
    if topics:
        found["title_topic_words"] = topics
    source = vocabulary.one("source_mark")
    cutoff = [line for line in text.splitlines() if source in line]
    if cutoff:
        year, month, day = vocabulary.all("date_words")[:3]
        dated = re.search(rf"(\d{{4}})\s*{year}\s*(\d{{1,2}})\s*{month}\s*(\d{{1,2}})\s*{day}", cutoff[0])
        if dated:
            found["source_date"] = f"{int(dated.group(1)):04d}-{int(dated.group(2)):02d}-{int(dated.group(3)):02d}"
    if card is not None:
        found["figures"] = figure_facts(text, card, books, vocabulary)
        found["data_block"] = data_block(text, card, books, vocabulary)
        found["below_target"] = below_target(text, card, books, vocabulary)
    if len(delivered) > 1:
        snapshots = page_versions(exchanges)
        found["revisions"] = [
            {
                "from": f"turn {before[0]} {before[1].name}",
                "to": f"turn {after[0]} {after[1].name}",
                "observed": before[2] is not None and after[2] is not None,
                **(
                    page_changes(before[2], after[2], visible(before[2]), visible(after[2]))
                    if before[2] is not None and after[2] is not None
                    else {}
                ),
            }
            for before, after in zip(snapshots, snapshots[1:])
        ]
    if base:
        found["against_the_page_handed_over"] = page_changes(base, html, visible(base), text)
    found["reconciliation_sheet"] = sheet_facts(page, files, text, vocabulary, workdir=workdir)
    return found


def draw(vocabulary: Vocabulary):
    """A page's picture as the projector shows it, for `cached`: one screenshot at the projector's size."""

    def shoot(file: Path, out: Path, width: int) -> None:
        probed = rendered(file, vocabulary, shot=Path(out) / "page-01.png")
        if "error" in probed:
            raise RuntimeError(probed["error"])

    return shoot


class ReviewOwner(Owner):
    """The sales-operations head of the regional review case, judging pages with the facts above."""

    def __init__(self, scenario, provider, skills, **options):
        super().__init__(scenario, provider, skills, facts=self._facts, pictures=self._pictures, **options)
        self.vocabulary = Vocabulary.load(scenario.root)
        self.cards_ruled = cards(scenario.root)
        self.books = {
            "q3": book(scenario.text(self.vocabulary.one("quarter_table")), self.vocabulary),
            "oct": book(scenario.text(self.vocabulary.one("october_table")), self.vocabulary),
        }
        self.handouts = {
            persona.name: {Path(path).name: Path(path) for path in persona.files}
            for persona in getattr(scenario, "personas", ())
        }

    def card(self, name, card) -> Card | None:
        """The card's rulers, by the playing's card or else by the drill's name (`holdout-`, set and repeat marks
        taken off)."""
        key = getattr(card, "name", None) or REPEAT.sub("", CARD_PREFIX.sub("", name))
        return self.cards_ruled.get(key)

    def _facts(self, name, exchanges, card) -> dict:
        ruled = self.card(name, card)
        base = base_page(ruled, self.handouts.get(ruled.name, {})) if ruled else None
        placed = self.workdirs.get(name) or {}
        workdir = placed.get("workdir")
        filed = self._filed(name) if workdir else {}
        try:
            return facts(exchanges, ruled, self.vocabulary, self.books, base=base, filed=filed, workdir=workdir)
        except Exception as exc:  # noqa: BLE001 -- a fact that cannot be computed is reported, never fatal
            return {"facts_error": str(exc)[:300]}

    def _pictures(self, sessions) -> tuple[dict, list[dict], str]:
        import base64

        shown_, parts = {}, []
        width = self.vocabulary.projector[0]
        for name, exchanges in sessions.items():
            latest = {path.name: path for _, path in pages(exchanges)}
            for file, path in latest.items():
                try:
                    images = cached(path, path.with_name(f"{path.name}.thumbs"), width, draw=draw(self.vocabulary))
                except Exception as exc:  # noqa: BLE001 -- a page that cannot be rendered is reported, not fatal
                    shown_.setdefault(name, {})[file] = f"could not be rendered: {exc}"[:200]
                    continue
                shown_.setdefault(name, {})[file] = len(images)
                parts.append({"type": "text", "text": f"[{name}] {file}"})
                for image in images:
                    url = "data:image/png;base64," + base64.b64encode(image.read_bytes()).decode()
                    parts.append({"type": "image_url", "image_url": {"url": url}})
        lead = "Each delivered page as the meeting-room projector shows it, full screen, in the order `pictures` lists."
        return shown_, parts, lead


# The owner the simulation entry judges this case by (`experimental.simulation.__main__.owner_of`).
DELIVERED = delivered_as_requested
OWNER = ReviewOwner
