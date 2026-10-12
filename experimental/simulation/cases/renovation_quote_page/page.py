"""A delivered quote page used the way a salesperson uses it on a phone, for the owner's facts.

The page is opened from its file in a headless Chromium with a phone's viewport, the phone's clock set to the day
being tried and every request to the network refused, as in a customer's flat without a signal. For each input set the
page is loaded afresh, the area typed, the tier and the two options chosen and the button pressed, each control found
the way a person finds it, by the words beside it; then the text the page shows is read: the amount on the total line
of the quote sheet, or the prompt for a refused area, and any alert it raised. The words are the case's
`reference.md` values. Nothing here judges: the owner compares the readings with its reference figures and decides.

Playwright's synchronous API refuses to run inside an event loop, and the owner computes its facts from inside one,
so a page is examined on a worker thread.
"""

import hashlib
import re
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from experimental.simulation.cases.renovation_quote_page.quote import HALF, Case

VIEWPORT = {"width": 390, "height": 844}
# The phone's zone; China keeps no daylight saving time, so a fixed offset names the same clock without tz data.
ZONE = "Asia/Shanghai"
OFFSET = timezone(timedelta(hours=8))
SETTLE_MS = 250
TIMEOUT_MS = 4000
# A page that never settles (a script stuck in a loop) is given up on rather than holding the review.
LIMIT_S = 300
# A total written in ten-thousands, which the finance rules forbid, still reads as its amount.
TEN_THOUSAND = chr(0x4E07)
AMOUNT = re.compile(
    r"(?<![\d.,+-])([+-]?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+))(?:\.([0-9]+))?"
    r"(\s*" + TEN_THOUSAND + r")?(?![\d.,])"
)
# A quote number, a date or a percentage is never the total, whatever line it stands on.
NOT_MONEY = re.compile(r"[A-Za-z]+\d[\d-]*|\d{4}\D{1,2}\d{1,2}\D{1,2}\d{1,2}|\d+(?:\.\d+)?\s*%")
EXTERNAL = re.compile(
    r"""(?:src|href)\s*=\s*["']?\s*((?:https?:)?//[^"'\s>]+)|url\(\s*["']?((?:https?:)?//[^"')\s]+)|@import\s+["']((?:https?:)?//[^"']+)""",
    re.I,
)
LOCAL = re.compile(
    r"""<(?:script|link|img|iframe)\b[^>]*?(?:src|href)\s*=\s*["']?(?!https?:|//|data:|#|javascript:)([^"'\s>]+)""",
    re.I,
)

# Finds the controls for one input set and marks each with `data-probe`, so the driver then acts on it with
# Playwright's own fill, select, check and click and the page sees a person's events.
LOCATE = r"""
(a) => {
  const visible = (el) => {
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
  };
  const ownText = (node, skip) => {
    let out = '';
    const walk = (n) => {
      if (n === skip) return;
      if (n.nodeType === 3) { out += n.textContent; return; }
      if (n.nodeType !== 1 || ['SELECT', 'OPTION', 'SCRIPT', 'STYLE', 'TEXTAREA'].includes(n.tagName)) return;
      for (const c of n.childNodes) walk(c);
    };
    walk(node);
    return out.replace(/\s+/g, ' ').trim();
  };
  const near = (el) => {
    const parts = [];
    if (el.labels) for (const l of el.labels) parts.push(ownText(l, el));
    for (const k of ['aria-label', 'title']) { const v = el.getAttribute(k); if (v) parts.push(v); }
    const by = el.getAttribute('aria-labelledby');
    if (by) for (const id of by.split(/\s+/)) { const n = document.getElementById(id); if (n) parts.push(n.innerText); }
    let sib = el.nextSibling, hops = 0;
    while (sib && hops < 3 && !parts.join('').trim()) {
      if (sib.nodeType === 3) parts.push(sib.textContent);
      else if (sib.nodeType === 1 && !['INPUT', 'SELECT', 'BUTTON', 'TEXTAREA'].includes(sib.tagName)) parts.push(sib.innerText || '');
      else break;
      sib = sib.nextSibling; hops += 1;
    }
    return parts.join(' ').replace(/\s+/g, ' ').trim();
  };
  const context = (el) => {
    let node = el;
    for (let i = 0; i < 3 && node.parentElement; i++) {
      node = node.parentElement;
      const t = ownText(node, el);
      if (t) return t;
    }
    return '';
  };
  const label = (el) => {
    const own = near(el);
    const extra = ['placeholder', 'name', 'id'].map((k) => el.getAttribute(k) || '').join(' ');
    return (own + ' ' + extra + ' ' + (own ? '' : context(el))).trim();
  };
  const negative = (t) => a.negations.some((n) => t.includes(n));
  const blank = (t) => !t.trim() || a.placeholders.some((p) => t.includes(p));
  const mark = (el, role) => { el.setAttribute('data-probe', role); };
  const found = { area: false, tier: { kind: 'none' }, toggles: {}, go: false, controls: [] };

  const boxes = [...document.querySelectorAll('input, textarea')].filter((el) => {
    const t = (el.getAttribute('type') || 'text').toLowerCase();
    return el.tagName === 'TEXTAREA' || ['text', 'number', 'tel', 'search', 'decimal'].includes(t);
  }).filter(visible);
  const area = boxes.find((el) => a.area.some((w) => label(el).includes(w))) || (boxes.length === 1 ? boxes[0] : null);
  if (area) { mark(area, 'area'); found.area = true; found.controls.push('area ' + (area.getAttribute('type') || 'text') + ' box'); }
  found.others = [];
  for (const box of boxes) {
    if (box === area || box.value.trim()) continue;
    const phone = ['tel', 'number'].includes((box.getAttribute('type') || '').toLowerCase())
      || (box.getAttribute('inputmode') || '').toLowerCase() === 'tel' || /^\d+$/.test(box.getAttribute('maxlength') || '')
      || a.phoneWords.some((w) => label(box).includes(w));
    const role = 'other-' + found.others.length;
    mark(box, role);
    found.others.push({ role: role, phone: phone });
  }
  if (found.others.length) found.controls.push('filled ' + found.others.length + ' other box(es) with neutral values');

  const tierPick = () => {
    for (const s of document.querySelectorAll('select')) {
      const opts = [...s.options];
      const named = a.tiers.filter((n) => opts.some((o) => o.text.includes(n)));
      const hit = opts.find((o) => o.text.includes(a.tier));
      if (hit && named.length >= 2) { mark(s, 'tier'); return { kind: 'select', value: hit.value }; }
    }
    for (const r of document.querySelectorAll('input[type=radio]')) {
      const own = near(r) || r.value || '';
      if (own.includes(a.tier) && !a.tiers.some((n) => n !== a.tier && own.includes(n))) { mark(r, 'tier'); return { kind: 'radio' }; }
    }
    const items = [...document.querySelectorAll('button, [role=button], [role=radio], [role=tab], [role=option], label, li, a, span, div')]
      .filter(visible).filter((el) => {
        const t = (el.innerText || '').trim();
        return t.includes(a.tier) && t.length <= a.tier.length + 12 && !a.tiers.some((n) => n !== a.tier && t.includes(n));
      });
    const deepest = items.filter((el) => !items.some((o) => o !== el && el.contains(o)));
    if (deepest.length) { mark(deepest[0], 'tier'); return { kind: 'click' }; }
    return { kind: 'none' };
  };
  found.tier = tierPick();
  found.controls.push('tier ' + found.tier.kind);

  const state = (el) => {
    for (const k of ['aria-checked', 'aria-pressed', 'aria-selected']) {
      const v = el.getAttribute(k); if (v === 'true') return true; if (v === 'false') return false;
    }
    const box = el.querySelector && el.querySelector('input[type=checkbox]');
    if (box) return box.checked;
    if (/(^|[\s_-])(active|on|checked|selected|is-active|is-on)($|[\s_-])/.test(el.className || '')) return true;
    return null;
  };
  const toggle = (word, want, role, other) => {
    for (const c of document.querySelectorAll('input[type=checkbox]')) {
      if (label(c).includes(word)) { mark(c, role); return { kind: 'checkbox' }; }
    }
    for (const s of document.querySelectorAll('select')) {
      const opts = [...s.options].filter((o) => !blank(o.text));
      if (opts.length < 2 || !(label(s).includes(word) || opts.some((o) => o.text.includes(word)))) continue;
      if (a.tiers.filter((n) => opts.some((o) => o.text.includes(n))).length >= 2) continue;
      const pick = want ? opts.find((o) => !negative(o.text)) : opts.find((o) => negative(o.text));
      if (pick) { mark(s, role); return { kind: 'select', value: pick.value }; }
    }
    const radios = [...document.querySelectorAll('input[type=radio]')];
    const own = (r) => near(r) || r.value || '';
    const groups = [...new Set(radios.map((r) => r.name || r))].map((key) => radios.filter((r) => (r.name || r) === key));
    const around = (group) => {
      let node = group[0].parentElement;
      while (node && !group.every((r) => node.contains(r))) node = node.parentElement;
      for (let i = 0; node && i < 3; i++, node = node.parentElement) {
        const t = ownText(node, null);
        if (t.includes(word)) return t.includes(other) ? '' : t;
      }
      return '';
    };
    for (const group of groups) {
      if (group.some((r) => a.tiers.some((n) => own(r).includes(n)))) continue;
      if (!(group.some((r) => own(r).includes(word)) || around(group))) continue;
      const pick = want ? group.find((r) => !negative(own(r))) : group.find((r) => negative(own(r)));
      if (pick) { mark(pick, role); return { kind: 'radio' }; }
    }
    const items = [...document.querySelectorAll('[role=switch], button, [role=button], label, span, div, li, a')]
      .filter(visible).filter((el) => { const t = (el.innerText || '').trim(); return t.includes(word) && t.length <= word.length + 8; });
    const deepest = items.filter((el) => !items.some((o) => o !== el && el.contains(o)));
    const yes = deepest.filter((el) => !negative(el.innerText || '')), no = deepest.filter((el) => negative(el.innerText || ''));
    if (yes.length && no.length) { mark(want ? yes[0] : no[0], role); return { kind: 'click', needed: true }; }
    if (yes.length) {
      const now = state(yes[0]);
      mark(yes[0], role);
      return { kind: 'click', needed: now === null ? want : now !== want };
    }
    return { kind: 'none' };
  };
  for (const [word, want, role, other] of [[a.demolition, a.demolish, 'demolish', a.custom], [a.custom, a.customWanted, 'custom', a.demolition]]) {
    found.toggles[role] = toggle(word, want, role, other);
    found.controls.push(role + ' ' + found.toggles[role].kind);
  }

  const buttons = [...document.querySelectorAll('button, input[type=button], input[type=submit], [role=button], a')].filter(visible)
    .filter((el) => el.getAttribute('data-probe') === null);
  for (const w of a.go) {
    const b = buttons.find((el) => { const t = (el.innerText || el.value || '').trim(); return t.includes(w) && !a.skip.some((s) => t.includes(s)); });
    if (b) { mark(b, 'go'); found.go = true; found.controls.push('button ' + (b.innerText || b.value || '').trim()); break; }
  }
  if (!found.go) found.controls.push('no button (computes as typed)');
  return found;
}
"""

# The vertical stretch the quote sheet takes on the phone, from its first marker line to its last, and whether the
# page scrolls sideways at the phone's width.
LAYOUT = r"""
(marks) => {
  const tops = [], bottoms = [];
  const all = [...document.querySelectorAll('body *')].filter((el) => {
    const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0;
  });
  for (const m of marks) {
    const test = new RegExp(m);
    const hits = all.filter((el) => test.test(el.innerText || ''));
    const leaf = hits.filter((el) => !hits.some((o) => o !== el && el.contains(o)));
    for (const el of leaf) {
      const r = el.getBoundingClientRect();
      tops.push(r.top + window.scrollY); bottoms.push(r.bottom + window.scrollY);
    }
  }
  return {
    overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
    height: tops.length ? Math.round(Math.max(...bottoms) - Math.min(...tops)) : null,
  };
}
"""


@dataclass(frozen=True)
class Words:
    """What the driver looks for on a page, from the case's `reference.md`."""

    area: tuple[str, ...]
    tiers: tuple[str, ...]
    demolition: str
    custom: str
    negations: tuple[str, ...]
    placeholders: tuple[str, ...]
    go: tuple[str, ...]
    skip: tuple[str, ...]
    totals: tuple[str, ...]
    gross: str
    prompt: str
    money_marks: tuple[str, ...] = ()
    phone_words: tuple[str, ...] = ()
    neutral_text: str = ""
    neutral_phone: str = ""
    sheet_marks: tuple[str, ...] = field(default=())
    title: str = ""
    amount_labels: tuple[str, ...] = ()
    extra_fields: dict = field(default_factory=dict)

    @classmethod
    def of(cls, words: dict) -> "Words":
        return cls(
            area=words["area_label"],
            tiers=words["tier_names"],
            demolition=words["demolition_label"][0],
            custom=words["custom_label"][0],
            negations=words["negations"],
            placeholders=words["placeholders"],
            go=words["compute_buttons"],
            skip=words["skip_buttons"],
            totals=words["total_labels"],
            gross=words["gross_label"][0],
            prompt=words["error_prompt"][0],
            money_marks=words["money_marks"],
            phone_words=words["phone_words"],
            neutral_text=words["neutral_text"][0],
            neutral_phone=words["neutral_phone"][0],
            sheet_marks=(
                re.escape(words["quote_prefix"][0]) + r"\d{8}",
                re.escape(words["total_labels"][0]),
                re.escape(words["measure_note"][0]),
            ),
            title=words["sheet_title"][0],
            amount_labels=words["sheet_fields"][6:],
            extra_fields={
                key: words.get(key + "_labels", ()) for key in ("advisor", "advisor_phone", "customer", "community")
            },
        )


@dataclass(frozen=True)
class Reading:
    """What the page showed for one input set."""

    case: Case
    total: Decimal | None
    line: str
    prompt: bool
    alerts: tuple[str, ...]
    refused: str | None
    text: str
    controls: tuple[str, ...] = ()
    rendered: dict = field(default_factory=dict)


def squeeze(text: str) -> str:
    return "".join((text or "").split())


def _amount(candidate: str, words: Words, *, marked: bool) -> Decimal | None:
    """The amount in `candidate`, quote numbers and dates left out; with `marked`, only one written as money (a
    currency mark beside it or thousands separators), the way an amount on a line of its own is told from a count."""
    cleaned = NOT_MONEY.sub(" ", candidate.translate(HALF).replace("\u2212", "-"))
    for found in AMOUNT.finditer(cleaned):
        whole, decimals, wan = found.groups()
        tail = cleaned[found.end() : found.end() + 3]
        head = cleaned[max(0, found.start() - 2) : found.start()]
        if marked and not ("," in whole or any(mark in head + tail for mark in words.money_marks)):
            continue
        value = Decimal(whole.replace(",", "") + (f".{decimals}" if decimals else ""))
        return value * 10000 if wan else value
    return None


def total_of(text: str, words: Words) -> tuple[Decimal | None, str]:
    """The amount on the quote sheet's total line, the labels tried in their order; a bare total label skips a line
    that is the gross with tax. The amount may stand on the label's line, or written as money on the line before or
    after it (a large figure above its caption)."""
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    for label in words.totals:
        for index, line in enumerate(lines):
            if label not in line or (label != words.gross and words.gross in line and words.gross not in label):
                continue
            value = _amount(line[line.index(label) + len(label) :], words, marked=False)
            if value is not None:
                return value, line[:80]
            for near in (lines[index + 1] if index + 1 < len(lines) else "", lines[index - 1] if index else ""):
                if any(other in near for other in (*words.totals, words.gross)):
                    continue
                value = _amount(near, words, marked=True)
                if value is not None:
                    return value, line[:80]
    return None, ""


def unparsed_total(text: str, words: Words) -> bool:
    """A visibly written money result the supported total parser cannot read, rather than an empty result."""
    lines = [line.strip().translate(HALF) for line in text.splitlines() if line.strip()]
    numerals = r"[\u96f6\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u767e\u5343\u4e07]+"
    money = "|".join(re.escape(mark) for mark in words.money_marks)
    labelled = [line for line in lines if any(label in line for label in words.totals) and words.gross not in line]
    if labelled:
        return any(re.search(rf"{numerals}\s*(?:{money})|[0-9]", NOT_MONEY.sub("", line)) for line in labelled)
    return any(re.search(rf"(?:\d[\d,.]*|{numerals})\s*(?:{money})", line) for line in lines)


def source_facts(html: str, words: dict) -> dict:
    """What the file itself shows: references outside it, and internal cost data anywhere in its source."""
    external = sorted({next(group for group in found.groups() if group) for found in EXTERNAL.finditer(html)})
    local = sorted(set(LOCAL.findall(html)))
    costs = {}
    for word in words["cost_words"]:
        lines = [line for line in html.splitlines() if word in line]
        if lines:
            costs[word] = lines
    english = [
        line for line in html.splitlines() if re.search(r"cost|margin|profit|internal|discount.?floor", line, re.I)
    ]
    if english:
        costs["English internal-data candidates"] = english
    for figure in words["cost_figures"]:
        pattern = re.compile(rf"(?<![\d.,]){re.escape(figure)}(?![\d.,]|px|%)")
        lines = [line for line in html.splitlines() if pattern.search(line)]
        if lines:
            costs[figure] = lines
    local += [
        value.strip().strip("\"'")
        for group in re.findall(r"url\(([^)]+)\)|@import\s+([\"'][^\"']+[\"'])", html, re.I)
        for value in group
        if value and not value.strip().strip("\"'").startswith(("http:", "https:", "//", "data:", "#"))
    ]
    return {
        "external_references": external,
        "local_references": sorted(set(local)),
        "cost_data": costs,
        "source": html,
        "source_complete": True,
        "source_sha256": hashlib.sha256(html.encode()).hexdigest(),
        "cost_candidates_are_not_a_verdict": True,
    }


def _try(page, url: str, case: Case, words: Words, wanted: str, *, reload=True, fill_other=True) -> Reading:
    alerts: list[str] = []

    def answer(dialog):
        alerts.append(dialog.message)
        dialog.accept()

    page.on("dialog", answer)
    try:
        if reload:
            page.goto(url, wait_until="load", timeout=TIMEOUT_MS)
        page.evaluate("document.querySelectorAll('[data-probe]').forEach((el)=>el.removeAttribute('data-probe'))")
        found = page.evaluate(
            LOCATE,
            {
                "area": list(words.area),
                "tiers": list(words.tiers),
                "tier": wanted,
                "demolition": words.demolition,
                "custom": words.custom,
                "demolish": case.demolish,
                "customWanted": case.custom,
                "negations": list(words.negations),
                "placeholders": list(words.placeholders),
                "go": list(words.go),
                "skip": list(words.skip),
                "phoneWords": list(words.phone_words),
            },
        )
        refused = None
        if not found["area"]:
            refused = "no area box found"
        else:
            try:
                page.locator('[data-probe="area"]').fill(case.area, timeout=TIMEOUT_MS)
            except Exception as exc:  # noqa: BLE001 -- a box that refuses the text is what a person meets, not a failure
                refused = f"the area box did not take the text: {str(exc).splitlines()[0][:80]}"
        for other in found["others"]:
            if not fill_other:
                continue
            value = words.neutral_phone if other["phone"] else words.neutral_text
            page.locator(f'[data-probe="{other["role"]}"]').fill(value, timeout=TIMEOUT_MS)
        tier = found["tier"]
        if tier["kind"] == "select":
            page.locator('[data-probe="tier"]').select_option(value=tier["value"], timeout=TIMEOUT_MS)
        elif tier["kind"] in ("radio", "click"):
            page.locator('[data-probe="tier"]').first.click(timeout=TIMEOUT_MS)
        for role, want in (("demolish", case.demolish), ("custom", case.custom)):
            toggle, target = found["toggles"][role], page.locator(f'[data-probe="{role}"]').first
            if toggle["kind"] == "checkbox":
                target.set_checked(want, timeout=TIMEOUT_MS)
            elif toggle["kind"] == "select":
                target.select_option(value=toggle["value"], timeout=TIMEOUT_MS)
            elif toggle["kind"] == "radio":
                target.check(timeout=TIMEOUT_MS)
            elif toggle["kind"] == "click" and toggle.get("needed"):
                target.click(timeout=TIMEOUT_MS)
        if found["go"]:
            page.locator('[data-probe="go"]').first.click(timeout=TIMEOUT_MS)
        page.wait_for_timeout(SETTLE_MS)
        text = page.evaluate("document.body.innerText")
        snapshot = rendered(page, words)
    finally:
        page.remove_listener("dialog", answer)
    total, line = total_of(text, words)
    prompt = squeeze(words.prompt) in squeeze(text) or any(squeeze(words.prompt) in squeeze(alert) for alert in alerts)
    if total is None and not prompt and (unparsed_total(text, words) or snapshot.get("nontext_surfaces")):
        refused = "could not parse the displayed total; inspect the page text"
    return Reading(case, total, line, prompt, tuple(alerts), refused, text, tuple(found["controls"]), snapshot)


def _examine(
    path: Path,
    runs: Sequence[tuple[date, Sequence[Case]]],
    words: Words,
    executable: str,
    field_request: str | None = None,
) -> dict:
    from playwright.sync_api import sync_playwright

    url, blocked, local_requests, errors, results = Path(path).resolve().as_uri(), set(), set(), [], {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=executable, headless=True)
        try:
            context = browser.new_context(viewport=VIEWPORT, timezone_id=ZONE, locale="zh-CN")

            def route(request_route):
                if request_route.request.url.startswith("file:"):
                    if request_route.request.url.split("#", 1)[0].split("?", 1)[0] != url:
                        local_requests.add(request_route.request.url)
                    request_route.continue_()
                else:
                    blocked.add(request_route.request.url[:120])
                    request_route.abort()

            context.route("**/*", route)
            for day, cases in runs:
                page = context.new_page()
                page.on("pageerror", lambda exc: errors.append(str(exc).splitlines()[0][:120]))
                page.clock.set_fixed_time(datetime(day.year, day.month, day.day, 10, 30, tzinfo=OFFSET))
                readings, layouts, transitions = [], {}, []
                for at, case in enumerate(cases):
                    try:
                        page.clock.set_fixed_time(
                            datetime(day.year, day.month, day.day, 10, 30, tzinfo=OFFSET) + timedelta(seconds=at * 3)
                        )
                        readings.append(_try(page, url, case, words, case.tier))
                    except Exception as exc:  # noqa: BLE001 -- a control that cannot be worked is reported, not fatal
                        readings.append(Reading(case, None, "", False, (), f"could not work the page: {exc}"[:160], ""))
                    if readings[-1].total is not None:
                        layouts[case.label] = readings[-1].rendered.get("layout") or {}
                    if readings[-1].prompt or readings[-1].refused and "did not take" in readings[-1].refused:
                        seed = next((r.case for r in readings if r.total is not None), None)
                        if seed:
                            _try(page, url, seed, words, seed.tier)
                            transitions.append(_try(page, url, case, words, case.tier, reload=False))
                issuance = {}
                valid = next((r.case for r in readings if r.total is not None), None)
                if valid:
                    page.clock.set_fixed_time(
                        datetime(day.year, day.month, day.day, 10, 30, tzinfo=OFFSET)
                        + timedelta(seconds=len(cases) * 3 + 10)
                    )
                    first = _try(page, url, valid, words, valid.tier)
                    changed = Case("repeat", "90", valid.tier, valid.demolish, valid.custom)
                    second = _try(page, url, changed, words, changed.tier, reload=False)
                    reloaded = _try(page, url, changed, words, changed.tier)
                    first_number = re.search(r"AJ[0-9]{8}-[0-9]{6}", first.text)
                    second_number = re.search(r"AJ[0-9]{8}-[0-9]{6}", second.text)
                    issuance = {
                        "first_number": first_number.group() if first_number else None,
                        "second_number": second_number.group() if second_number else None,
                        "first_clock": first.rendered.get("clock"),
                        "second_clock": second.rendered.get("clock"),
                        "first_sheet": first.rendered.get("sheet_text"),
                        "second_sheet": second.rendered.get("sheet_text"),
                        "quote_changed": first.rendered.get("sheet_text") != second.rendered.get("sheet_text"),
                        "same_second": first.rendered.get("clock") == second.rendered.get("clock"),
                        "after_reload_number": (
                            match.group() if (match := re.search(r"AJ[0-9]{8}-[0-9]{6}", reloaded.text)) else None
                        ),
                        "after_reload_sheet": reloaded.rendered.get("sheet_text"),
                        "after_reload_clock": reloaded.rendered.get("clock"),
                    }
                fields = {}
                if field_request and valid and day == runs[0][0]:
                    page.clock.set_fixed_time(
                        datetime(day.year, day.month, day.day, 10, 30, tzinfo=OFFSET)
                        + timedelta(seconds=len(cases) * 3 + 13)
                    )
                    roles = ("advisor", "advisor_phone") if field_request == "baodai" else ("customer", "community")
                    fields = field_trials(page, url, valid, words, roles, remember=field_request == "baodai")
                    if fields.get("populated_layout"):
                        layouts["requested_fields_populated"] = fields["populated_layout"]
                observed = [layout for layout in layouts.values() if layout.get("height") is not None]
                layout = {
                    "overflow": any(item.get("overflow") for item in observed),
                    "height": max((item["height"] for item in observed), default=None),
                }
                results[day] = {
                    "readings": readings,
                    "layout": layout,
                    "layouts": layouts,
                    "invalid_transitions": transitions,
                    "issuance": issuance,
                    "requested_fields": fields,
                }
                page.close()
        finally:
            browser.close()
    return {
        "runs": results,
        "blocked": sorted(blocked),
        "local_requests": sorted(local_requests),
        "errors": list(dict.fromkeys(errors))[:5],
    }


def examine(
    path: Path,
    runs: Sequence[tuple[date, Sequence[Case]]],
    words: Words,
    executable: str,
    field_request: str | None = None,
) -> dict:
    """Readings of the page for every input set on every day, the requests it tried to make and its script errors."""
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        return pool.submit(_examine, Path(path), runs, words, executable, field_request).result(timeout=LIMIT_S)
    finally:
        pool.shutdown(wait=False)


RENDERED = r"""
(a) => {
  const visible = (el) => {
    const r = el.getBoundingClientRect(), s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
  };
  const elements = [...document.querySelectorAll('body *')].filter(visible);
  const leaf = (test) => {
    const hits = elements.filter((el) => test(el.innerText || ''));
    return hits.find((el) => !hits.some((other) => other !== el && el.contains(other)));
  };
  const number = leaf((t) => /AJ[0-9]{8}-[0-9]{6}/.test(t));
  const total = leaf((t) => a.totals.some((w) => t.includes(w)) && !t.includes(a.gross));
  const note = leaf((t) => t.replace(/\s/g, '').includes(a.note.replace(/\s/g, '')));
  const title = leaf((t) => t.replace(/\s/g, '').includes(a.title.replace(/\s/g, '')));
  const markers = [number, total, note].filter(Boolean);
  let sheet = markers[0];
  while (sheet && !markers.every((el) => sheet.contains(el))) sheet = sheet.parentElement;
  const identified = markers.length >= 2 && sheet && sheet !== document.body && sheet !== document.documentElement;
  const text = (el) => (el.innerText || '').trim();
  const money = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const sizes = [], clipped = [], textBoxes = [];
  let node;
  while (node = walker.nextNode()) {
    const parent = node.parentElement;
    if (!node.textContent.trim() || !parent || !visible(parent) || ['SCRIPT','STYLE','OPTION','SELECT','TEXTAREA'].includes(parent.tagName)) continue;
    const range = document.createRange(); range.selectNodeContents(node);
    const box = range.getBoundingClientRect();
    if (!box.width || !box.height) continue;
    const value = node.textContent.trim(), style = getComputedStyle(parent);
    const row = parent.closest('tr');
    const surrounding = parent.parentElement ? text(parent.parentElement) : value;
    const neighbor = [parent.previousElementSibling,parent.nextElementSibling]
      .filter(Boolean).map(text).filter((t)=>t.length<=80).join(' ');
    const context = row ? text(row) : surrounding.length<=150 ? surrounding : value+' '+neighbor;
    const numeric = /[+\-\u2212]?[0-9\uff10-\uff19][0-9\uff10-\uff19.,\uff0c\uff0e]*(?:\s*\u4e07)?/.test(value);
    const area = /\u33a1|m\u00b2|\u5e73\u7c73|\u5e73\u65b9\u7c73|\u5143\s*\//.test(value);
    const amountContext = a.amounts.some((w) => context.includes(w));
    if (numeric && !area && !/AJ[0-9]{8}|[0-9]{4}[-/]/.test(value) && !/%/.test(value)
        && (amountContext || /[\u5143\u00a5\uffe5]/.test(value))) {
      money.push({text:value, context:context, align:style.textAlign, font_size_px:parseFloat(style.fontSize)});
    }
    if (identified && sheet.contains(parent)) {
      sizes.push(parseFloat(style.fontSize));
      textBoxes.push({text:value, left:box.left, right:box.right, top:box.top, bottom:box.bottom});
      let ancestor = parent;
      while (ancestor && sheet.contains(ancestor)) {
        const s = getComputedStyle(ancestor), r = ancestor.getBoundingClientRect();
        if (['hidden','clip'].includes(s.overflowX) && (box.left < r.left - 1 || box.right > r.right + 1)
            || ['hidden','clip'].includes(s.overflowY) && (box.top < r.top - 1 || box.bottom > r.bottom + 1)) {
          clipped.push(value); break;
        }
        if (ancestor === sheet) break;
        ancestor = ancestor.parentElement;
      }
    }
  }
  const bounds = identified ? sheet.getBoundingClientRect() : null;
  return {
    clock: new Date().toISOString(),
    sheet_status: identified ? 'observed' : 'unidentified',
    sheet_text: identified ? text(sheet) : '',
    body_text: document.body.innerText,
    nontext_surfaces: elements.filter((el)=>['CANVAS','IMG','SVG'].includes(el.tagName.toUpperCase())).map((el)=>({tag:el.tagName,width:el.getBoundingClientRect().width,height:el.getBoundingClientRect().height})),
    money_fields: money,
    layout: {
      overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
      height: bounds ? Math.ceil(Math.max(bounds.bottom,...textBoxes.map((r)=>r.bottom))-Math.min(bounds.top,...textBoxes.map((r)=>r.top))) : null,
      width: bounds ? Math.ceil(Math.max(bounds.right,...textBoxes.map((r)=>r.right))-Math.min(bounds.left,...textBoxes.map((r)=>r.left))) : null,
      minimum_font_px: sizes.length ? Math.min(...sizes) : null,
      clipped_text: [...new Set(clipped)],
      text_boxes: textBoxes,
      visual_image_shown: false
    }
  };
}
"""


FIELD_CONTROLS = r"""
(groups) => {
  const visible = (el) => {const r=el.getBoundingClientRect();return r.width>0 && r.height>0 && getComputedStyle(el).visibility!=='hidden';};
  const boxes = [...document.querySelectorAll('input,textarea,[contenteditable=true],[role=textbox]')].filter(visible).filter((el)=> !['hidden','checkbox','radio','button','submit'].includes(el.type));
  const label = (el) => {
    const labels = el.labels ? [...el.labels].map((n)=>n.innerText).join(' ') : '';
    return [labels, el.getAttribute('aria-label'),el.getAttribute('placeholder'),el.name,el.id].filter(Boolean).join(' ').toLowerCase();
  };
  const found = {};
  for (const [role,names] of Object.entries(groups)) {
    const hits = boxes.filter((el)=>names.some((w)=>label(el).includes(w.toLowerCase())));
    const pick = role==='advisor' ? hits.find((el)=>!['tel','phone','mobile'].some((w)=>label(el).includes(w)) && el.inputMode!=='tel' && !groups.advisor_phone.some((w)=>label(el).includes(w.toLowerCase()))) : hits[0];
    if (pick) {pick.setAttribute('data-field-probe',role);found[role]={value:pick.isContentEditable?pick.innerText:pick.value,type:pick.type,label:label(pick)};}
  }
  return {found:found,other_text_boxes:boxes.filter((el)=>el.getAttribute('data-probe')!=='area').length,
    unsupported_widgets:[...document.querySelectorAll('body *')].filter(visible).some((el)=>el.shadowRoot || el.tagName.includes('-') || el.tagName==='CANVAS'),
    unclassified_boxes:boxes.filter((el)=>el.getAttribute('data-probe')!=='area' && !el.hasAttribute('data-field-probe')).map(label)};
}
"""


def rendered(page, words: Words) -> dict:
    """Visible sheet, typography, monetary fields and clock from the operated document."""
    return page.evaluate(
        RENDERED,
        {
            "totals": words.totals,
            "gross": words.gross,
            "note": words.sheet_marks[2].replace("\\", ""),
            "title": words.title,
            "amounts": words.amount_labels,
        },
    )


def field_trials(page, url: str, case: Case, words: Words, roles: tuple[str, ...], *, remember: bool) -> dict:
    """Operate blank and populated requested fields and reload to observe local retention."""
    page.goto(url, wait_until="load", timeout=TIMEOUT_MS)
    page.evaluate(FIELD_CONTROLS, words.extra_fields)
    for role in roles:
        locator = page.locator(f'[data-field-probe="{role}"]')
        if locator.count():
            locator.fill("")
            locator.dispatch_event("change")
    blank = _try(page, url, case, words, case.tier, fill_other=False, reload=False)
    controls = page.evaluate(FIELD_CONTROLS, words.extra_fields)
    matched = controls["found"]
    missing = [role for role in roles if role not in matched]
    result = {
        "blank_total": str(blank.total) if blank.total is not None else None,
        "blank_text": blank.text,
        "controls": controls,
        "missing_roles": missing,
        "matched_roles_require_semantic_confirmation": True,
    }
    if missing:
        result["status"] = (
            "missing"
            if not controls["unclassified_boxes"] and not controls["unsupported_widgets"]
            else "unknown: field controls not identified"
        )
        return result
    values = {
        "advisor": "Advisor Delta",
        "advisor_phone": "13900123456",
        "customer": "Customer Delta",
        "community": "Lakeview Estate",
    }
    for role in roles:
        locator = page.locator(f'[data-field-probe="{role}"]')
        locator.fill(values[role])
        locator.dispatch_event("change")
        locator.blur()
    if blank.rendered.get("clock"):
        page.clock.set_fixed_time(
            datetime.fromisoformat(blank.rendered["clock"].replace("Z", "+00:00")) + timedelta(seconds=1)
        )
    populated = _try(page, url, case, words, case.tier, reload=False, fill_other=False)
    sheet_text = populated.rendered.get("sheet_text", "")
    result.update(
        status="observed",
        entered={role: values[role] for role in roles},
        printed={role: values[role] in sheet_text for role in roles},
        populated_text=sheet_text,
        populated_total=str(populated.total) if populated.total is not None else None,
        populated_layout=populated.rendered.get("layout"),
        populated_money_fields=populated.rendered.get("money_fields"),
    )
    page.reload(wait_until="load")
    after = page.evaluate(FIELD_CONTROLS, words.extra_fields)["found"]
    result["after_reload"] = {role: after.get(role, {}).get("value") for role in roles}
    result["body_after_reload"] = page.inner_text("body")
    result["storage_after_reload"] = page.evaluate(
        "({local:Object.entries(localStorage),session:Object.entries(sessionStorage)})"
    )
    result["retention_matches_request"] = all(
        result["after_reload"][role] == (values[role] if remember else "") for role in roles
    )
    result["remember_required"] = remember
    if not remember:
        remaining = str(result["storage_after_reload"]) + result["body_after_reload"]
        result["retention_matches_request"] = result["retention_matches_request"] and not any(
            values[role] in remaining for role in roles
        )
    return result
