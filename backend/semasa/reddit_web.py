"""Reddit read with Wan's OWN saved login, in a browser (Wan, 24 Nov 2026: "yes set up reddit login").

Why: the sweep read Reddit through Composio's shared Reddit app, and Reddit answers that app `429 Too Many Requests` (every run
on 24 Nov 2026, retries included): one rate limit shared by everybody who uses the app. A logged-in browser session is its own
visitor with its own allowance, the same road the Instagram read already takes (social_web.py).

  secret   PW_STORAGE_STATE_REDDIT_B64: base64 of a Playwright storage_state.json holding the reddit.com cookies of a THROWAWAY
           account (ops/instagram_login.py reddit writes it; plain or gzipped, read by social_web._read_secret)
  read     https://www.reddit.com/r/<sub>/search.json?q=(a OR b ...)&restrict_sr=1&sort=top&t=<window>: Reddit's own JSON for
           the same search the Composio cell ran, opened as a page so the request is the browser's own
  shape    the cell's: {id, title, score, num_comments, permalink, created, subreddit, text}; community.candidates reads either

It only reads. Nothing is posted, voted on or followed, and the cookies never leave the runner. Without the secret this module
says so and the Composio road is used as before; with it, a failed read is reported by name and Composio is still asked.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

from . import social_web
from .log import get_logger

log = get_logger("semasa.reddit_web")

SECRET = "PW_STORAGE_STATE_REDDIT_B64"
DOMAIN = "reddit.com"
BASE = "https://www.reddit.com"
LOGIN_COOKIES = ("reddit_session", "token_v2")       # either proves a login; reddit_session is the long-lived one
MAX_TERMS = 20                                       # community.MAX_TERMS: past ~20 OR-terms Reddit stops matching


def _is_reddit(cookie: dict[str, Any]) -> bool:
    return DOMAIN in str(cookie.get("domain") or "")


def saved_login() -> tuple[dict[str, Any] | None, str]:
    """(the storage state holding only reddit.com cookies, how the secret was read). None when the secret is absent, unreadable or
    carries no Reddit login cookie; the second part says which ('absent', 'unreadable', 'no cookies', 'no reddit login')."""
    state, how = social_web._read_secret(SECRET)
    if state is None:
        return None, how
    cookies = [c for c in state["cookies"] if _is_reddit(c)]
    if not any(c.get("name") in LOGIN_COOKIES and c.get("value") for c in cookies):
        return None, "no reddit login"
    return {"cookies": cookies, "origins": []}, how


def configured() -> bool:
    return saved_login()[0] is not None


def describe(state: dict[str, Any] | None, how: str, now: datetime | None = None) -> str:
    """One log line about the saved Reddit login: how many cookies, which login cookies are there and how long they last.
    Names and days only, never a value."""
    if state is None:
        return f"reddit login: not used ({how})"
    now = now or datetime.now(UTC)
    seen = []
    for name in LOGIN_COOKIES:
        c = next((x for x in state["cookies"] if x.get("name") == name and x.get("value")), None)
        if c is None:
            seen.append(f"{name} missing")
            continue
        exp = c.get("expires")
        days = None if not isinstance(exp, (int, float)) or exp <= 0 else round((float(exp) - now.timestamp()) / 86400.0, 1)
        seen.append(f"{name} present, " + ("this browser session only" if days is None else f"{days} day(s) left"))
    return f"reddit login: {len(state['cookies'])} reddit cookie(s) (read {how}); " + "; ".join(seen)


def search_url(subreddit: str, terms: list[str], window: str, limit: int) -> str:
    q = "(" + " OR ".join(str(t) for t in terms[:MAX_TERMS]) + ")"
    params = {"q": q, "restrict_sr": 1, "sort": "top", "t": window, "limit": limit, "type": "link", "raw_json": 1}
    return f"{BASE}/r/{subreddit}/search.json?" + urlencode(params)


def parse(body: str) -> tuple[list[dict[str, Any]], str]:
    """(posts in the Composio cell's shape, error). The page text of the search.json address: a Listing, or whatever Reddit showed
    instead (a block page, a login page), which is reported by its first words."""
    try:
        j = json.loads(body)
    except (ValueError, TypeError):
        words = " ".join(str(body or "").split())[:120]
        return [], f"Reddit did not answer with its search list ({words or 'an empty page'})"
    if isinstance(j, dict) and j.get("error"):
        return [], f"Reddit answered {j.get('error')}: {str(j.get('message') or j.get('reason') or '')[:120]}"
    children = ((j.get("data") or {}).get("children") if isinstance(j, dict) else None) or []
    out = []
    for ch in children:
        d = ch.get("data") if isinstance(ch, dict) else None
        if not isinstance(d, dict) or not d.get("id") or not d.get("permalink"):
            continue
        try:
            created = datetime.fromtimestamp(float(d.get("created_utc")), UTC).isoformat()
        except (TypeError, ValueError, OSError):
            created = None
        link = str(d["permalink"])
        out.append({"id": str(d["id"]), "title": str(d.get("title") or "")[:300], "score": d.get("score"),
                    "num_comments": d.get("num_comments"), "permalink": link if link.startswith("http") else BASE + link,
                    "created": created, "subreddit": d.get("subreddit"), "text": str(d.get("selftext") or "")[:500]})
    return out, ""


def read(page: Any, url: str) -> tuple[list[dict[str, Any]], str]:
    """Open the search address as a page and parse what it shows. (posts, error)."""
    resp = page.goto(url, wait_until="domcontentloaded", timeout=30_000)
    status = getattr(resp, "status", None)
    body = page.evaluate("() => document.body ? document.body.innerText : ''") or ""
    posts, err = parse(body)
    if err and status and status != 200:
        err = f"Reddit answered HTTP {status} to the saved login ({err})"
    return posts, err


def fetch(cfg: dict[str, Any], now: datetime | None = None, opener: Any = None) -> tuple[list[dict[str, Any]], str]:
    """The sweep's entry point. (posts, error); ([], "") when no login is saved, so the caller uses the Composio road silently.
    `opener(state)` yields a page for tests; the real one launches Chromium with the saved cookies."""
    state, how = saved_login()
    log.info(describe(state, how, now))
    if state is None:
        return [], "" if how == "absent" else f"the saved Reddit login was not used ({how}): record it again"
    url = search_url(str(cfg.get("subreddit") or "malaysia"), list(cfg.get("terms") or ["halal"]),
                     cfg.get("window") if cfg.get("window") in ("day", "week", "month") else "week",
                     max(1, min(25, int(cfg.get("limit") or 15))))
    if opener is not None:
        return read(opener(state), url)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return [], "Playwright is not installed"
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                ctx = browser.new_context(locale="en-MY", timezone_id="UTC", storage_state=state)
                return read(ctx.new_page(), url)
            finally:
                browser.close()
    except Exception as exc:  # noqa: BLE001 - no browser on the runner is a report, not a crash
        return [], f"no browser to read Reddit with ({type(exc).__name__}: {str(exc)[:120]})"
