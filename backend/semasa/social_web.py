"""Facebook and Instagram read in a browser, for the viral-post feed (Wan, 13 Nov 2026: "once successful we add for fb and ig").
The same method as threads_web.py and the KKM complaint scraper (wanshah07/kkm-complaints), with what each platform allows.

What was measured on 13 Nov 2026, from a plain browser with no login:
  Facebook   facebook.com/hashtag/<tag> renders public posts (real Malaysian ones for #halalmalaysia and #sijilhalal): words,
             a time, "All reactions: 42". But only the FIRST post of a page loads; the rest stay "Loading..." until a login.
             A page's own address (facebook.com/NASA) and facebook.com/search both answer a login wall or a 404.
  Instagram  every page, hashtags and profiles alike, is a login wall.
So both read with a saved login when one exists (the secret PW_STORAGE_STATE_B64, a Playwright storage_state.json of a throwaway
account, exactly as the KKM scraper does) and Facebook also reads anonymously, thinly. Without a login Instagram says so, by name,
and makes no row. A keyword is turned into a hashtag (letters and digits, no spaces): "halal malaysia" reads #halalmalaysia.

Counts are the numbers the page showed: "42" for Facebook reactions, "1,234 likes, 56 comments" for an Instagram post (read from
the post page's own description). A number the page did not show is not claimed. Nothing here posts, approves or drafts.
"""

from __future__ import annotations

import base64
import os
import re
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from .log import get_logger
from .threads_web import parse_count

log = get_logger("semasa.social_web")

SETTLE_MS = 5000
SCROLLS = 2
SCROLL_MS = 1500
MAX_TAGS = 8
PER_TAG_IG = 6                 # Instagram: posts opened per hashtag (each is a page load)
FB_BASE = "https://www.facebook.com"
IG_BASE = "https://www.instagram.com"
_WALL_PARTS = ("/login", "accounts/login", "checkpoint")

_FB_EXTRACT = r"""
() => [...document.querySelectorAll('[role="article"]')].map((a) => {
  const text = (a.innerText || '').replace(/\s+/g, ' ').trim();
  const msg = a.querySelector('[data-ad-preview="message"], [data-ad-comet-preview="message"]');
  const link = [...a.querySelectorAll('a[href]')].find((x) =>
    /\/(posts|videos|reel)\/|story_fbid|multi_permalinks|\/permalink/.test(x.getAttribute('href') || ''));
  const when = link ? link.getAttribute('aria-label') || '' : '';
  return {text: text.slice(0, 700), message: msg ? (msg.innerText || '').replace(/\s+/g, ' ').trim() : '',
          href: link ? link.href : '', when};
}).filter((p) => p.href && p.text)
"""

_IG_LINKS = r"""
() => [...new Set([...document.querySelectorAll('a[href*="/p/"], a[href*="/reel/"]')]
  .map((a) => a.getAttribute('href')).filter((h) => /^\/([\w.]+\/)?(p|reel)\/[\w-]+\/?$/.test(h)))]
"""

_IG_POST = r"""
() => {
  const t = document.querySelector('time[datetime]');
  return {desc: (document.querySelector('meta[property="og:description"]') || {}).content || '',
          time: t ? t.getAttribute('datetime') : ''};
}
"""


def hashtag(query: Any) -> str:
    """'halal malaysia' -> 'halalmalaysia'; '#SijilHalal' -> 'sijilhalal'. Empty when nothing usable is left."""
    return "".join(ch for ch in str(query or "").lower() if ch.isalnum())[:60]


def storage_state_path() -> str | None:
    """The saved login as a file Playwright can load, from PW_STORAGE_STATE_B64 (the KKM scraper's own secret name), or None."""
    raw = (os.environ.get("PW_STORAGE_STATE_B64") or "").strip()
    if not raw:
        return None
    try:
        data = base64.b64decode(raw, validate=False)
    except ValueError:
        return None
    if b'"cookies"' not in data:
        return None
    fd, path = tempfile.mkstemp(suffix=".json", prefix="pwstate-")
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)
    return path


# --- Facebook ---------------------------------------------------------------------------------------------------------------

_FB_DATE = re.compile(r"[A-Z][a-z]+day, ([A-Z][a-z]+ \d{1,2}, \d{4}) at (\d{1,2}:\d{2} [AP]M)")
_REL = re.compile(r"^(\d+)\s*([smhdw])$")


def _fb_time(text: str, label: str, now: datetime) -> datetime | None:
    """The post's time: the full date Facebook prints (read in UTC, the browser is set to UTC), else its short label (3d, 5h)."""
    m = _FB_DATE.search(text)
    if m:
        try:
            return datetime.strptime(f"{m.group(1)} {m.group(2)}", "%B %d, %Y %I:%M %p").replace(tzinfo=UTC)
        except ValueError:
            pass
    r = _REL.match((label or "").strip())
    if r:
        step = {"s": "seconds", "m": "minutes", "h": "hours", "d": "days", "w": "weeks"}[r.group(2)]
        return now - timedelta(**{step: int(r.group(1))})
    return None


def _fb_link(href: str) -> tuple[str, str] | None:
    """(permalink, id): the query is dropped, except a group post's multi_permalinks which is the post's own id."""
    m = re.match(r"https://(?:www\.)?facebook\.com(/[^?#]*)(?:\?([^#]*))?", href)
    if not m:
        return None
    path, query = m.group(1), m.group(2) or ""
    mp = re.search(r"multi_permalinks=(\d+)", query)
    if mp:
        return f"{FB_BASE}{path}?multi_permalinks={mp.group(1)}", mp.group(1)
    sf = re.search(r"story_fbid=(\w+)", query)
    if sf:
        return f"{FB_BASE}{path}?story_fbid={sf.group(1)}", sf.group(1)
    tail = [s for s in path.split("/") if s]
    return (f"{FB_BASE}{path}", tail[-1]) if tail else None


def facebook_post(raw: dict[str, Any], now: datetime) -> dict[str, Any] | None:
    link = _fb_link(str(raw.get("href") or ""))
    text = str(raw.get("message") or "").strip()
    text = re.sub(r"\s*(…|\.\.\.)?\s*See more$", "", text).strip()
    when = _fb_time(str(raw.get("text") or ""), str(raw.get("when") or ""), now)
    if not link or len(text) < 15 or not when:
        return None
    m = re.search(r"All reactions:\s*([\d.,]+\s*[KkMm]?)", str(raw.get("text") or ""))
    shown = {"reactions": m.group(1).replace(" ", "")} if m else {}
    return {"id": link[1], "text": text[:500], "permalink": link[0], "timestamp": when.isoformat(),
            "counts": {k: parse_count(v) for k, v in shown.items()} or {"reactions": None}, "shown": shown}


def read_facebook(page: Any, tag: str, now: datetime) -> tuple[list[dict[str, Any]], str]:
    try:
        page.goto(f"{FB_BASE}/hashtag/{tag}", wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(SETTLE_MS)
        if any(p in str(getattr(page, "url", "")) for p in _WALL_PARTS):
            return [], "Facebook asked for a login"
        for _ in range(SCROLLS):
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(SCROLL_MS)
        rows = page.evaluate(_FB_EXTRACT) or []
    except Exception as exc:  # noqa: BLE001 - one page failing must not stop the others
        return [], f"{type(exc).__name__}: {str(exc)[:160]}"
    return [p for p in (facebook_post(r, now) for r in rows) if p], ""


# --- Instagram --------------------------------------------------------------------------------------------------------------

_IG_DESC = re.compile(
    r"^(?:(?P<likes>[\d.,]+[KkMm]?) likes?)?(?:,\s*)?(?:(?P<comments>[\d.,]+[KkMm]?) comments?)?\s*-?\s*"
    r"(?P<user>[\w.]+) on (?:(?P<date>[A-Z][a-z]+ \d{1,2}, \d{4})|Instagram)\s*:\s*[\"“](?P<caption>.*)[\"”]\.?\s*$", re.S)


def parse_instagram(desc: str, time_attr: str, href: str) -> dict[str, Any] | None:
    """One post from its page: the og:description Instagram writes ('1,234 likes, 56 comments - user on November 12, 2026:
    "caption"') and the page's own <time datetime>. None when the description is not a post's (a login wall's, an empty one)."""
    m = _IG_DESC.match(" ".join(str(desc or "").split()))
    pid = re.search(r"/(?:p|reel)/([\w-]+)", href)
    if not m or not pid:
        return None
    when = None
    if time_attr:
        try:
            when = datetime.fromisoformat(time_attr.replace("Z", "+00:00"))
        except ValueError:
            when = None
    if when is None and m.group("date"):
        try:
            when = datetime.strptime(m.group("date"), "%B %d, %Y").replace(tzinfo=UTC)
        except ValueError:
            when = None
    caption = m.group("caption").strip()
    if not when or len(caption) < 15:
        return None
    shown = {k: m.group(k) for k in ("likes", "comments") if m.group(k)}
    return {"id": pid.group(1), "username": m.group("user"), "text": caption[:500],
            "permalink": f"{IG_BASE}/p/{pid.group(1)}/", "timestamp": when.isoformat(),
            "counts": {k: parse_count(v) for k, v in shown.items()} or {"likes": None}, "shown": shown}


def read_instagram(page: Any, tag: str, now: datetime) -> tuple[list[dict[str, Any]], str]:
    try:
        page.goto(f"{IG_BASE}/explore/tags/{tag}/", wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(SETTLE_MS)
        if any(p in str(getattr(page, "url", "")) for p in _WALL_PARTS):
            return [], "Instagram asked for a login (save one as the secret PW_STORAGE_STATE_B64)"
        links = (page.evaluate(_IG_LINKS) or [])[:PER_TAG_IG]
        out: list[dict[str, Any]] = []
        for href in links:
            page.goto(IG_BASE + href, wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(2500)
            info = page.evaluate(_IG_POST) or {}
            post = parse_instagram(info.get("desc", ""), info.get("time", ""), href)
            if post:
                out.append(post)
    except Exception as exc:  # noqa: BLE001
        return [], f"{type(exc).__name__}: {str(exc)[:160]}"
    return out, ""


# --- shared -----------------------------------------------------------------------------------------------------------------

def score(p: dict[str, Any]) -> int:
    """How loud: comments, then reactions or likes a tenth as much. Only numbers the page showed."""
    c = p.get("counts") or {}
    return int((c.get("comments") or 0) + ((c.get("reactions") or 0) + (c.get("likes") or 0)) // 10)


def metrics_text(p: dict[str, Any]) -> str | None:
    """'42 reactions' or '1,234 likes · 56 comments': the page's own words, nothing it did not show."""
    shown = p.get("shown") or {}
    return " · ".join(f"{v} {k}" for k, v in shown.items() if v) or None


READERS: dict[str, Callable[[Any, str, datetime], tuple[list[dict[str, Any]], str]]] = {
    "facebook": read_facebook, "instagram": read_instagram}


def collect(page: Any, platform: str, cfg: dict[str, Any], now: datetime,
            read: Callable[..., Any] | None = None) -> tuple[list[dict[str, Any]], str]:
    """The hashtags in the settings, newest 72 h only, loudest first. (posts, error); the error only when nothing was read."""
    opts = cfg.get(platform) or {}
    hours = max(6, min(14 * 24, int(opts.get("hours") or 72)))
    tags = list(dict.fromkeys(t for t in (hashtag(q) for q in (opts.get("queries") or [])) if t))[:MAX_TAGS]
    if not tags:
        return [], ""
    read = read or READERS[platform]
    seen: set[str] = set()
    posts: list[dict[str, Any]] = []
    errors: list[str] = []
    for tag in tags:
        got, err = read(page, tag, now)
        if err:
            errors.append(err)
            log.warning("%s #%s not read: %s", platform, tag, err)
            if "asked for a login" in err and platform == "instagram":
                break                                              # every hashtag will say the same
        for p in got:
            when = _when(p.get("timestamp"))
            if p["id"] in seen or not when or now - when > timedelta(hours=hours) or is_own(p, cfg.get("own_accounts") or []):
                continue
            seen.add(p["id"])
            posts.append(p)
    posts.sort(key=score, reverse=True)
    if not posts and errors:
        return [], errors[0]
    return posts, ""


def is_own(p: dict[str, Any], names: list[str]) -> bool:
    """A post from one of Wan's own accounts or pages (the handle is the post's user or sits in its address): never viral."""
    own = {str(n).lower().lstrip("@") for n in names if str(n).strip()}
    if not own:
        return False
    user = str(p.get("username") or "").lower()
    path = [seg.lower() for seg in re.split(r"[/?]", str(p.get("permalink") or "").split("://", 1)[-1])[1:3] if seg]
    return user in own or any(seg.lstrip("@") in own for seg in path)


def _when(v: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


def fetch(platform: str, cfg: dict[str, Any], now: datetime | None = None) -> tuple[list[dict[str, Any]], str]:
    """The sweep's entry point for 'facebook' or 'instagram'. (posts, error)."""
    now = now or datetime.now(UTC)
    if (cfg.get(platform) or {}).get("web") is False:
        return [], ""
    state = storage_state_path()
    if platform == "instagram" and not state:
        return [], ("Instagram needs a saved login (the secret PW_STORAGE_STATE_B64); "
                    "it shows a login wall to every visitor without one")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return [], "Playwright is not installed"
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                opts: dict[str, Any] = {"locale": "en-MY", "timezone_id": "UTC", "viewport": {"width": 1280, "height": 2400}}
                if state:
                    opts["storage_state"] = state
                page = browser.new_context(**opts).new_page()
                return collect(page, platform, cfg, now)
            finally:
                browser.close()
    except Exception as exc:  # noqa: BLE001 - no browser on the runner is a report, not a crash
        return [], f"no browser to read {platform.title()} with ({type(exc).__name__}: {str(exc)[:120]})"
    finally:
        if state:
            try:
                os.unlink(state)
            except OSError:
                pass
