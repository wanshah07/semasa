"""Threads read in a plain browser, no login (Wan, 13 Nov 2026: "can you scrape social media like kkm complaint mechanism?").

The KKM complaint scraper (wanshah07/kkm-complaints) opens a profile in Playwright and reads the newest posts off the page. This
is the same method for the viral-post feed: threads.com/search?q=<keyword> and threads.com/@<handle> both render public posts
to an anonymous browser, each with the counts Threads itself shows (measured 13 Nov 2026: a post read "9K 280 1K 158"). It needs
no Meta app and no review, so it is the fallback after Composio (no search permission) and Wan's own app (supabase/080).

What a post's counts are: the four numbers under it, read from the buttons whose icon is titled Like, Comment, Repost and Share.
Threads shows them abbreviated ("9K", "1.3K"), and shows nothing at all for zero, so a count is kept as the text the page
showed and a count that is not shown is None: nothing here claims a number the platform did not display.

A post is anchored on its own <time datetime> link. A quoted copy inside another post has none, so it is never read as a post
and a quote is never counted twice. A login wall is reported by name; it never becomes a row.
Nothing here posts, approves or drafts a thing.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

from .log import get_logger

log = get_logger("semasa.threads_web")

BASE = "https://www.threads.com"
SETTLE_MS = 4000
SCROLLS = 3
MAX_QUERIES = 8        # keywords read per sweep (the page editor allows the same: web/src/lib/threadsKeywords.js)
MAX_ACCOUNTS = 10
SCROLL_MS = 1500
LABELS = {"Like": "likes", "Comment": "replies", "Repost": "reposts", "Share": "shares"}
_WALL = ("/login", "accounts/login")

# runs in the page: one dict per post that has its own timestamp
_EXTRACT = r"""
() => {
  const out = [], seen = new Set();
  const titled = (n) => [...n.querySelectorAll('[role="button"]')].filter((b) => b.querySelector('svg title')).length;
  // a post is anchored on ITS OWN timestamp link: a quoted copy inside it has no <time>, so it can never be read as a post
  for (const time of document.querySelectorAll('time[datetime]')) {
    const link = time.closest('a[href*="/post/"]');
    const href = link ? link.getAttribute('href') || '' : '';
    if (!/\/post\/[\w-]+$/.test(href) || seen.has(href)) continue;
    let el = link;
    for (let i = 0; i < 14 && el.parentElement; i++) { el = el.parentElement; if (titled(el) >= 4) break; }
    if (titled(el) < 4) continue;
    seen.add(href);
    const counts = {};
    for (const b of el.querySelectorAll('[role="button"]')) {
      const t = b.querySelector('svg title');
      if (t) counts[(t.textContent || '').trim()] = (b.innerText || '').trim();
    }
    const nodes = [...el.querySelectorAll('[dir="auto"]')]
      .filter((n) => !n.parentElement.closest('[dir="auto"]') && !n.closest('[role="button"]'));
    const at = nodes.findIndex((n) => n.contains(time));
    const body = nodes.slice(at + 1).map((n) => (n.innerText || '').replace(/\s+/g, ' ').trim()).filter(Boolean);
    out.push({href, datetime: time.getAttribute('datetime'), counts, body});
  }
  return out;
}
"""


def parse_count(text: Any) -> int | None:
    """'158' -> 158, '1.3K' -> 1300, '9K' -> 9000, '2.1M' -> 2100000; '' or anything else -> None (the page showed no number)."""
    m = re.fullmatch(r"\s*([\d.,]+)\s*([KkMm]?)\s*", str(text or ""))
    if not m:
        return None
    try:
        n = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    return int(round(n * {"": 1, "k": 1_000, "m": 1_000_000}[m.group(2).lower()]))


def _post(raw: dict[str, Any], cap: int = 500) -> dict[str, Any] | None:
    href = str(raw.get("href") or "")
    m = re.fullmatch(r"/@([\w.]+)/post/([\w-]+)", href)
    if not m:
        return None
    body = [t for t in (raw.get("body") or []) if t]
    if len(body) > 1 and re.fullmatch(r"[\w.]{1,30}", body[-1]):           # the quoted author's name trails a quote post
        body = body[:-1]
    text = "\n".join(body).strip()
    if not text:
        return None
    shown = {key: str((raw.get("counts") or {}).get(label) or "").strip() for label, key in LABELS.items()}
    counts = {k: parse_count(v) for k, v in shown.items()}
    return {"id": m.group(2), "username": m.group(1), "text": text[:cap], "permalink": BASE + href,
            "timestamp": raw.get("datetime"), "counts": counts, "shown": {k: v for k, v in shown.items() if v}}


def score(p: dict[str, Any]) -> int:
    """How loud a post is: replies first (an argument), then reposts, then likes. Only numbers the page showed are used."""
    c = p.get("counts") or {}
    return int((c.get("replies") or 0) + 2 * (c.get("reposts") or 0) + (c.get("likes") or 0) // 10)


def metrics_text(p: dict[str, Any]) -> str | None:
    """The line the feed shows, built from the page's own words ('9K likes · 280 replies · 1K reposts'), or None."""
    shown = p.get("shown") or {}
    parts = [f"{shown[k]} {k}" for k in ("likes", "replies", "reposts") if shown.get(k)]
    return " · ".join(parts) or None


def _wall(page: Any) -> bool:
    url = str(getattr(page, "url", "") or "")
    return any(part in url for part in _WALL)


def read_url(page: Any, url: str, scrolls: int = SCROLLS, cap: int = 500) -> tuple[list[dict[str, Any]], str]:
    """(posts, error) for one search or profile page. A page that shows a login wall is an error, never a row. `cap` is how
    much of a post's words are kept: 500 for the feed of arguments, more where the post itself is the content (experts.py)."""
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(SETTLE_MS)
        if _wall(page):
            return [], "Threads asked for a login"
        for _ in range(scrolls):
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(SCROLL_MS)
        rows = page.evaluate(_EXTRACT) or []
    except Exception as exc:  # noqa: BLE001 - one page failing must not stop the others
        return [], f"{type(exc).__name__}: {str(exc)[:160]}"
    return [p for p in (_post(r, cap) for r in rows) if p], ""


def _own(p: dict[str, Any], names: list[str]) -> bool:
    """A post from one of Wan's own accounts is never a viral post (the names are community.own_accounts)."""
    own = {str(n).lower().lstrip("@") for n in names if str(n).strip()}
    return str(p.get("username") or "").lower() in own


def _when(v: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


def collect(page: Any, cfg: dict[str, Any], now: datetime,
            read: Callable[..., Any] = read_url) -> tuple[list[dict[str, Any]], str]:
    """Search pages for each keyword and the watchlist's profiles, newest 72 h only, loudest first. (posts, error).
    The error is set only when NOTHING could be read; a page that failed while others worked is logged."""
    th = cfg.get("threads") or {}
    hours = max(6, min(14 * 24, int(th.get("hours") or 72)))
    limit = max(1, min(25, int(th.get("max_results") or 8)))
    words = [str(q) for q in (th.get("queries") or []) if str(q).strip()][:MAX_QUERIES]
    handles = [str(h).lstrip("@") for h in (th.get("accounts") or []) if re.fullmatch(r"@?[\w.]{1,30}", str(h))][:MAX_ACCOUNTS]
    urls = [f"{BASE}/search?q={quote(q)}&serp_type=default" for q in words] + [f"{BASE}/@{h}" for h in handles]
    if not urls:
        return [], ""
    seen: set[str] = set()
    posts: list[dict[str, Any]] = []
    errors: list[str] = []
    for url in urls:
        got, err = read(page, url)
        if err:
            errors.append(err)
            log.warning("Threads page not read (%s): %s", url.split("threads.com")[-1][:60], err)
        for p in got:
            when = _when(p.get("timestamp"))
            if p["id"] in seen or not when or now - when > timedelta(hours=hours) or _own(p, cfg.get("own_accounts") or []):
                continue
            seen.add(p["id"])
            posts.append(p)
    posts.sort(key=score, reverse=True)
    if not posts and errors:
        return [], errors[0]
    return posts[: limit * max(1, len(urls))], ""


def fetch(cfg: dict[str, Any], now: datetime | None = None) -> tuple[list[dict[str, Any]], str]:
    """The sweep's entry point. (posts, error); posts are in the shape community.thread_candidates reads, with counts."""
    now = now or datetime.now(UTC)
    if (cfg.get("threads") or {}).get("web") is False:
        return [], ""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return [], "Playwright is not installed"
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                ctx = browser.new_context(locale="en-MY", viewport={"width": 1280, "height": 2200})
                page = ctx.new_page()
                return collect(page, cfg, now)
            finally:
                browser.close()
    except Exception as exc:  # noqa: BLE001 - no browser on the runner is a report, not a crash
        return [], f"no browser to read Threads with ({type(exc).__name__}: {str(exc)[:120]})"
