"""Preserve actual studio delivery batches, file occurrences and rendered mobile evidence."""

import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from experimental.cultivation.counterpart.rulers import browser_executable
from experimental.harness.raven_adapter.observe import delivered_files

CHROMIUM = browser_executable()


def deliveries(exchanges):
    """Retain ordered occurrences and match successful native delivery batches by names and byte hashes."""
    last = {
        str(path): (turn, ordinal)
        for turn, exchange in enumerate(exchanges, 1)
        for ordinal, path in enumerate(exchange.execution.deliverables, 1)
    }
    versions, groups = [], []
    for turn, exchange in enumerate(exchanges, 1):
        current = []
        for ordinal, path in enumerate(exchange.execution.deliverables, 1):
            entry = {"turn": turn, "ordinal": ordinal, "name": Path(path).name, "path": str(path)}
            try:
                if last[str(path)] != (turn, ordinal):
                    raise ValueError("A reused path does not retain its earlier delivery.")
                raw = Path(path).read_bytes()
                entry["sha256"] = hashlib.sha256(raw).hexdigest()
                entry.update(content=raw.decode("utf-8"), status="read")
            except (OSError, UnicodeError, ValueError) as exc:
                entry.update(status="unavailable", reason=str(exc))
            current.append(entry)
        available = list(current)
        native = []
        for row in exchange.execution.records:
            files = delivered_files(row)
            if not files:
                continue
            group = {"turn": turn, "call_id": row.get("event", {}).get("tool_call_id"), "files": [], "verified": True}
            for file in files:
                sha = (file.get("retained") or {}).get("sha256")
                match = next(
                    (
                        entry
                        for entry in available
                        if entry.get("sha256") == sha and sha and entry["name"] == Path(file["path"]).name
                    ),
                    None,
                )
                if match is None:
                    group["verified"] = False
                    group["files"].append({"name": Path(file["path"]).name, "status": "unavailable"})
                else:
                    group["files"].append(match)
                    available.remove(match)
            native.append(group)
        if available:
            native.append(
                {
                    "turn": turn,
                    "files": available,
                    "verified": False,
                    "reason": "Delivery occurrences are not bound to complete native manifests.",
                }
            )
        groups.extend(native)
        versions.extend(current)
    return versions, groups


PROBE = """() => {
  const texts = [], walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node = walker.currentNode, el = node.parentElement, text = node.textContent.trim();
    if (!text || !el || el.closest('script,style,template')) continue;
    const range = document.createRange(); range.selectNodeContents(node);
    const box = range.getBoundingClientRect(), style = getComputedStyle(el);
    let scale = 1, hidden = false;
    for (let at = el; at; at = at.parentElement) {
      const s = getComputedStyle(at);
      if (s.transform && s.transform !== 'none') { const m = new DOMMatrixReadOnly(s.transform); scale *= Math.hypot(m.a,m.b); }
      scale *= parseFloat(s.zoom) || 1;
      hidden ||= s.display === 'none' || s.visibility === 'hidden' || parseFloat(s.opacity) === 0;
    }
    texts.push({text, font_px: parseFloat(style.fontSize) * scale, color: style.color, align: style.textAlign,
      hidden: hidden || !box.width || !box.height, box: [box.x,box.y,box.width,box.height]});
  }
  return {viewport: [innerWidth,innerHeight], content_width: document.documentElement.scrollWidth,
    horizontal_scroll: document.documentElement.scrollWidth > innerWidth + 1,
    text: document.body.innerText, dom: document.body.outerHTML, text_nodes: texts,
    headings: [...document.querySelectorAll('h1,h2,h3')].map(el => el.innerText),
    tables: [...document.querySelectorAll('table')].map(table => [...table.rows].map(row => [...row.cells].map(cell => cell.innerText)))};
}"""


def _render(html):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=CHROMIUM, args=["--no-sandbox"])
        try:
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page.route("**/*", lambda route: route.abort())
            page.set_content(html, wait_until="load", timeout=15000)
            page.wait_for_timeout(300)
            return page.evaluate(PROBE)
        finally:
            browser.close()


def render(html):
    """Expose actual text, styles, layout and DOM; complex visual appearance remains a semantic obligation."""
    if CHROMIUM is None:
        return {"status": "unavailable", "reason": "No Chromium executable is available."}
    with ThreadPoolExecutor(max_workers=1) as pool:
        try:
            return {"status": "rendered", **pool.submit(_render, html).result(timeout=30)}
        except Exception as exc:
            return {"status": "unavailable", "reason": str(exc)}
