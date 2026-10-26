"""A measured no-overlap test (Wan, 25 Oct 2026: "the text not overlap").

`hyperframes check` did not flag a film whose photo was squeezed into a strip touching the heading and the subtitle, so the
worker measures the film itself: it opens index.html in Chrome, seeks the timeline to moments when each scene has settled,
and compares the boxes of every visible line of text and every photo frame. Two boxes that cross, text over a photo, or text
outside the frame are findings; the worker sends them back to the writer and, failing that, builds the safe layout.

It reads rendered geometry, not the source, so it is blind to nothing the viewer would see. Where Chrome or Playwright is
missing it says so as a WARNING and blocks nothing.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from .log import get_logger

log = get_logger("semasa.motion_probe")

MARGIN = 0.06              # a text rect shrinks by this share of its height top and bottom (font boxes are taller than lines)
MIN_AREA = 6.0             # square pixels of crossing that count
MAX_SAMPLES = 16

JS = r"""
([t, W, H, margin, minArea]) => {
  const tl = window.__timelines && window.__timelines.main;
  document.querySelectorAll('.clip').forEach(c => {
    const s = parseFloat(c.dataset.start), d = parseFloat(c.dataset.duration);
    c.style.display = (t >= s - 1e-6 && t < s + d) ? '' : 'none';
  });
  if (tl) { tl.seek(t); tl.pause(); }
  const seen = el => {
    for (let e = el; e && e !== document.documentElement; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.display === 'none' || cs.visibility === 'hidden' || parseFloat(cs.opacity) < 0.2) return false;
    }
    return true;
  };
  const clipped = (el, r) => {            // what a viewer sees of a box: cut by every ancestor that hides its overflow
    let x1 = r.left, y1 = r.top, x2 = r.right, y2 = r.bottom;
    for (let e = el.parentElement; e && e !== document.documentElement; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.overflow === 'visible' && cs.overflowX === 'visible' && cs.overflowY === 'visible') continue;
      const b = e.getBoundingClientRect();
      x1 = Math.max(x1, b.left); y1 = Math.max(y1, b.top); x2 = Math.min(x2, b.right); y2 = Math.min(y2, b.bottom);
    }
    return {left: x1, top: y1, width: Math.max(0, x2 - x1), height: Math.max(0, y2 - y1)};
  };
  const boxes = [];
  const label = el => (el.id || el.className || el.tagName).toString().slice(0, 40);
  document.querySelectorAll('#root *').forEach(el => {
    if (['AUDIO', 'SCRIPT', 'STYLE'].includes(el.tagName) || !seen(el)) return;
    const own = [...el.childNodes].filter(n => n.nodeType === 3 && n.textContent.trim());
    for (const node of own) {
      const range = document.createRange();
      range.selectNodeContents(node);
      for (const r of range.getClientRects()) {
        if (r.width < 2 || r.height < 2) continue;
        const m = r.height * margin;
        boxes.push({owner: el, name: label(el), kind: 'text', x: r.left, y: r.top + m, w: r.width, h: r.height - 2 * m,
                    text: node.textContent.trim().slice(0, 24)});
      }
    }
    if (!own.length && getComputedStyle(el).backgroundImage.includes('url(')) {
      const r = clipped(el, el.getBoundingClientRect());
      if (r.width > 20 && r.height > 20) {
        boxes.push({owner: el, name: label(el), kind: 'photo', x: r.left, y: r.top, w: r.width, h: r.height, text: ''});
      }
    }
  });
  const found = [];
  document.querySelectorAll('#root .sc').forEach(sc => {
    // visible words below the scene's own box are cut off or sit in the next lane (a hidden, scaled element does not count)
    if (!seen(sc)) return;
    const box = sc.getBoundingClientRect();
    let over = 0;
    for (const b of boxes) {
      if (b.kind === 'text' && sc.contains(b.owner)) over = Math.max(over, b.y + b.h - box.bottom, box.top - b.y);
    }
    if (over > 3) {
      found.push({code: 'container_overflow',
                  message: `${label(sc)} has words ${Math.round(over)}px outside its box at ${t.toFixed(1)}s`});
    }
  });
  for (const b of boxes) {
    if (b.kind === 'text' && (b.x < -2 || b.y < -2 || b.x + b.w > W + 2 || b.y + b.h > H + 2)) {
      found.push({code: 'text_off_frame', message: `"${b.text}" (${b.name}) leaves the frame at ${t.toFixed(1)}s`});
    }
  }
  for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
    const a = boxes[i], b = boxes[j];
    if (a.owner === b.owner || (a.kind === 'photo' && b.kind === 'photo')) continue;
    const ox = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
    const oy = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
    if (ox > 2 && oy > 2 && ox * oy > minArea) {
      const what = a.kind === 'text' && b.kind === 'text' ? 'text_overlap' : 'text_on_photo';
      found.push({code: what, message: `"${a.text || a.name}" (${a.name}) and "${b.text || b.name}" (${b.name}) cross by ` +
                  `${Math.round(ox)}x${Math.round(oy)}px at ${t.toFixed(1)}s`});
    }
  }
  return found;
}
"""


_GSAP: dict[str, bytes] = {}


def gsap_body(html: str) -> tuple[str, bytes]:
    """The film's GSAP script, fetched here (with this process's own proxy and certificates) so the test browser, which has
    neither, never needs the network."""
    import re

    import requests
    m = re.search(r'<script[^>]+src="([^"]*gsap[^"]*)"', html)
    if not m:
        return "", b""
    url = m.group(1)
    if url not in _GSAP:
        r = requests.get(url, timeout=25)
        r.raise_for_status()
        _GSAP[url] = r.content
    return url, _GSAP[url]


def chrome_path() -> str:
    for p in (os.environ.get("PUPPETEER_EXECUTABLE_PATH"), shutil.which("google-chrome"), shutil.which("chromium"),
              "/opt/pw-browsers/chromium-1243/chrome-linux64/chrome"):
        if p and Path(p).exists():
            return p
    return ""


def sample_times(clips: list[tuple[float, float]], total: float) -> list[float]:
    """Moments when each timed element has settled: a little way in, and just before it leaves."""
    out: set[float] = set()
    for start, dur in clips:
        if dur < 0.8:
            continue
        out.add(round(start + min(1.8, dur * 0.55), 2))
        if dur > 2.4:
            out.add(round(start + dur - 0.7, 2))
    return sorted(t for t in out if 0 < t < total)[:MAX_SAMPLES]


def overlaps(folder: Path, w: int, h: int, total: float) -> list[dict[str, Any]]:
    """Findings [{code, message, section}] for the film in `folder`; [] when clean. A probe that cannot run returns one
    finding with severity 'warning' in its code (probe_unavailable) so the caller does not treat it as a failure."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        return [{"code": "probe_unavailable", "message": f"playwright is not installed: {str(exc)[:80]}", "section": "probe"}]
    chrome = chrome_path()
    if not chrome:
        return [{"code": "probe_unavailable", "message": "no Chrome found for the overlap test", "section": "probe"}]
    found: list[dict[str, Any]] = []
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=chrome, args=["--no-sandbox"])
            page = browser.new_page(viewport={"width": w, "height": h})
            url, body = gsap_body((folder / "index.html").read_text(encoding="utf-8"))
            if url:
                page.route(url, lambda route: route.fulfill(status=200, content_type="application/javascript", body=body))
            page.goto((folder / "index.html").resolve().as_uri(), wait_until="load")
            page.wait_for_function("!!(window.__timelines && window.__timelines.main)", polling=100, timeout=20000)
            clips = page.evaluate("[...document.querySelectorAll('.clip')].filter(c => c.tagName !== 'AUDIO')"
                                  ".map(c => [parseFloat(c.dataset.start), parseFloat(c.dataset.duration)])")
            for t in sample_times([(a, b) for a, b in clips if a == a and b == b], total):
                found += page.evaluate(JS, [t, w, h, MARGIN, MIN_AREA])
            browser.close()
    except Exception as exc:  # noqa: BLE001 - never block a film on the probe itself
        log.warning("overlap probe failed: %s", str(exc)[:200])
        return [{"code": "probe_unavailable", "message": f"the overlap test could not run: {str(exc)[:120]}", "section": "probe"}]
    seen, out = set(), []
    for f in found:
        key = (f["code"], f["message"].split(" at ")[0])
        if key not in seen and len(out) < 8:
            seen.add(key)
            out.append({**f, "section": "probe"})
    return out
