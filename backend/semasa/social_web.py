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
import json
import os
import re
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

from .log import get_logger
from .threads_web import parse_count

log = get_logger("semasa.social_web")

SETTLE_MS = 5000
SCROLLS = 2
SCROLL_MS = 1500
MAX_TAGS = 5                   # fewer pages per sweep keeps a saved login alive longer (Wan, 26 Nov 2026: "add limit"; was 8)
PER_TAG_IG = 2                 # Instagram: posts opened per hashtag (each is a page load; was 4)
PER_ACCOUNT_IG = 3             # and per watched account (was 6)
MAX_ACCOUNTS = 6               # (was 10)
LAST: dict[str, dict[str, Any]] = {}       # what the last collect() saw per platform: the sweep's report, the watchdog light
_NOTES: list[str] = []                     # one short line per page read: the address, its title, what was found on it
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
  // `lines` is the same message with its own line breaks kept, for a reader that wants the post as written (experts.py)
  return {text: text.slice(0, 700), message: msg ? (msg.innerText || '').replace(/\s+/g, ' ').trim() : '',
          lines: msg ? (msg.innerText || '').replace(/[ \t]+/g, ' ').replace(/\n{3,}/g, '\n\n').trim() : '',
          href: link ? link.href : '', when};
}).filter((p) => p.href && p.text)
"""

# runs in the page: opens every post that Facebook cut with "See more", so the message read after it is the whole post
_FB_EXPAND = r"""
() => {
  let n = 0;
  for (const b of document.querySelectorAll('[role="article"] [role="button"]')) {
    if (n >= 15) break;
    if (/^(see more|lihat lagi|lihat selengkapnya)$/i.test((b.innerText || '').trim())) { b.click(); n++; }
  }
  return n;
}
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


def _where(page: Any) -> str:
    """'/hashtag/halalmalaysia "Facebook"': the page's path and title, so a read of nothing can say what it was looking at."""
    try:
        path = re.sub(r"^https?://[^/]+", "", str(getattr(page, "url", "") or ""))[:50]
        title = str(page.title() or "")[:40]
    except Exception:  # noqa: BLE001 - a note must never fail a read
        return "?"
    return f'{path} "{title}"'


def hashtag(query: Any) -> str:
    """'halal malaysia' -> 'halalmalaysia'; '#SijilHalal' -> 'sijilhalal'. Empty when nothing usable is left."""
    return "".join(ch for ch in str(query or "").lower() if ch.isalnum())[:60]


IG_DOMAIN = "instagram.com"


GZIP_MAGIC = b"\x1f\x8b"
MAX_STATE_BYTES = 5_000_000        # a saved login is kilobytes: anything that unpacks beyond this is not one


def _unpack(data: bytes) -> bytes:
    """The JSON bytes of a saved login: plain, or gzip (the KKM helper session_pack.py writes base64 of a gzip), with a leading
    byte-order mark dropped. A gzip that unpacks past MAX_STATE_BYTES is refused rather than expanded."""
    import zlib
    if data[:2] == GZIP_MAGIC:
        box = zlib.decompressobj(wbits=31)
        try:
            data = box.decompress(data, MAX_STATE_BYTES)
        except zlib.error as exc:                  # a corrupt or truncated gzip: not a ValueError, so it is normalised here
            raise ValueError("saved login is not a readable gzip") from exc
        if box.unconsumed_tail:
            raise ValueError("saved login too large")
    return data.lstrip(b"\xef\xbb\xbf")


def _read_secret(name: str) -> tuple[dict[str, Any] | None, str]:
    """(the saved login, how it was read) from one environment secret. The second part says WHY there is none: 'absent' (not
    set), 'unreadable' (set, but not base64 of JSON or of a gzip of it) or 'no cookies' (JSON without a cookies list), or how it
    was read ('plain', 'gzip'). Never a value."""
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return None, "absent"
    try:
        data = base64.b64decode(raw, validate=False)
        gz = data[:2] == GZIP_MAGIC
        state = json.loads(_unpack(data))
    except (ValueError, TypeError, OSError):
        return None, "unreadable"
    if not isinstance(state, dict) or not isinstance(state.get("cookies"), list):
        return None, "no cookies"
    # a malformed entry (null, a string...) is dropped, never iterated: the optional secret must not be able to fail the sweep
    return {**state, "cookies": [c for c in state["cookies"] if isinstance(c, dict)]}, "gzip" if gz else "plain"


def _state_of(name: str) -> dict[str, Any] | None:
    """One saved login from the environment (base64 of a Playwright storage_state.json, plain or gzipped), or None."""
    return _read_secret(name)[0]


def _is_ig(cookie: dict[str, Any]) -> bool:
    return IG_DOMAIN in str(cookie.get("domain") or "")


def describe_login(base: dict[str, Any] | None, ig: dict[str, Any] | None, merged: list[dict[str, Any]],
                   now: float | None = None, how: tuple[str, str] = ("", "")) -> str:
    """One line for the run log that says what the saved login holds, so a login wall can be told from a login that never
    arrived (Wan, 24 Nov 2026: "diagnostic"). COUNTS AND COOKIE NAMES ONLY, never a value: the names (sessionid, csrftoken,
    ds_user_id) are public protocol, the values are the login."""
    import time
    now = time.time() if now is None else now

    def count(state: dict[str, Any] | None, match: Callable[[dict[str, Any]], bool]) -> int:
        return sum(1 for c in (state or {}).get("cookies", []) if match(c))
    fb = count(base, lambda c: "facebook.com" in str(c.get("domain") or ""))
    if base is None:
        base_text = how[0] or "absent"
    else:
        base_text = f"{len(base['cookies'])} cookie(s), {count(base, _is_ig)} instagram, {fb} facebook" + (
            f" (read {how[0]})" if how[0] else "")
    if ig is None:
        ig_text = how[1] if how[1] and how[1] != "plain" and how[1] != "gzip" else "absent or without an instagram cookie"
        if how[1] in ("plain", "gzip"):
            ig_text = f"read {how[1]}, but no instagram cookie in it"
    else:
        ig_text = f"{count(ig, _is_ig)} instagram cookie(s)" + (f" (read {how[1]})" if how[1] else "")
    parts = [f"base secret: {base_text}", f"instagram secret: {ig_text}"]
    ig_now = [c for c in merged if _is_ig(c)]
    names = {str(c.get("name")): c for c in ig_now}
    seen = []
    for name in ("sessionid", "ds_user_id", "csrftoken"):
        c = names.get(name)
        if c is None:
            seen.append(f"{name} absent")
            continue
        exp = c.get("expires")
        days = f", {round((float(exp) - now) / 86400, 1)} day(s) left" if isinstance(exp, (int, float)) and exp > 0 else ""
        seen.append(f"{name} present{days}")
    parts.append(f"merged: {len(merged)} cookie(s), {len(ig_now)} instagram ({'; '.join(seen)})")
    return "saved login: " + " | ".join(parts)


def storage_state_path() -> str | None:
    """The saved login as a file Playwright can load, or None.

    PW_STORAGE_STATE_B64 (the KKM scraper's own secret name) is the base: whatever it holds, Facebook included. A SECOND secret,
    PW_STORAGE_STATE_IG_B64 (Wan, 24 Nov 2026: "add instagram live without kacau other platforms"), holds an Instagram login on
    its own and is merged over the base: its Instagram cookies replace the base's Instagram cookies and nothing else is touched.
    So adding Instagram never means rewriting the secret Facebook already reads with, and a bad Instagram secret is ignored."""
    base, base_how = _read_secret("PW_STORAGE_STATE_B64")
    ig, ig_how = _read_secret("PW_STORAGE_STATE_IG_B64")
    if ig is not None and not any(IG_DOMAIN in str(c.get("domain") or "") for c in ig["cookies"]):
        ig = None                                       # a file with no Instagram cookie in it adds nothing
    if base is None and ig is None:
        return None
    state = dict(base or {"cookies": [], "origins": []})
    cookies = list(state.get("cookies") or [])
    if ig is not None:
        cookies = [c for c in cookies if IG_DOMAIN not in str(c.get("domain") or "")]
        cookies += [c for c in ig["cookies"] if IG_DOMAIN in str(c.get("domain") or "")]
    state["cookies"] = cookies
    try:
        log.info(describe_login(base, ig, cookies, how=(base_how, ig_how)))
    except Exception as exc:  # noqa: BLE001 - a diagnostic line must never fail the sweep
        log.info("saved login: not described (%s)", str(exc)[:80])
    fd, path = tempfile.mkstemp(suffix=".json", prefix="pwstate-")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(state, fh)
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


_FB_TAIL = re.compile(r"\s*(…|\.\.\.)?\s*(See more|See less|See translation|See original|Lihat lagi)$", re.I)


def facebook_post(raw: dict[str, Any], now: datetime, cap: int = 500, keep_lines: bool = False) -> dict[str, Any] | None:
    """`keep_lines`: the message with its paragraphs kept (experts.py); `cap`: how much of it is kept."""
    link = _fb_link(str(raw.get("href") or ""))
    text = str((raw.get("lines") if keep_lines and raw.get("lines") else raw.get("message")) or "").strip()
    for _ in range(3):                                   # the page's own labels at the end of a message are not its words
        text = _FB_TAIL.sub("", text).strip()
    when = _fb_time(str(raw.get("text") or ""), str(raw.get("when") or ""), now)
    if not link or len(text) < 15 or not when:
        return None
    m = re.search(r"All reactions:\s*([\d.,]+\s*[KkMm]?)", str(raw.get("text") or ""))
    shown = {"reactions": m.group(1).replace(" ", "")} if m else {}
    return {"id": link[1], "text": text[:cap], "permalink": link[0], "timestamp": when.isoformat(),
            "counts": {k: parse_count(v) for k, v in shown.items()} or {"reactions": None}, "shown": shown}


def _fb_rows(page: Any, scrolls: int = SCROLLS, expand: bool = False) -> list[dict[str, Any]]:
    for _ in range(scrolls):
        page.mouse.wheel(0, 2500)
        page.wait_for_timeout(SCROLL_MS)
    if expand:
        try:
            if page.evaluate(_FB_EXPAND):
                page.wait_for_timeout(1200)
        except Exception as exc:  # noqa: BLE001 - a post left cut is still a post
            log.info("Facebook posts not expanded: %s", str(exc)[:100])
    return page.evaluate(_FB_EXTRACT) or []


def read_facebook(page: Any, tag: str, now: datetime) -> tuple[list[dict[str, Any]], str]:
    """A hashtag's page. Facebook has largely stopped rendering posts on hashtag pages (14 Nov 2026, logged in: 0 post blocks for
    #halalmalaysia and #sijilhalal), so when the page shows none the same words are searched as posts. Either way the note says
    what the page held."""
    try:
        page.goto(f"{FB_BASE}/hashtag/{tag}", wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(SETTLE_MS)
        if any(p in str(getattr(page, "url", "")) for p in _WALL_PARTS):
            return [], "Facebook asked for a login"
        rows = _fb_rows(page)
        where = _where(page)
        searched = ""
        if not rows:
            page.goto(f"{FB_BASE}/search/posts/?q={quote(tag)}", wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(SETTLE_MS)
            if any(p in str(getattr(page, "url", "")) for p in _WALL_PARTS):
                return [], "Facebook asked for a login"
            rows = _fb_rows(page)
            searched = f"; searched instead: {len(rows)} block(s) at {_where(page)}"
    except Exception as exc:  # noqa: BLE001 - one page failing must not stop the others
        return [], f"{type(exc).__name__}: {str(exc)[:160]}"
    got = [p for p in (facebook_post(r, now) for r in rows) if p]
    _NOTES.append(f"#{tag}: {len(got)} usable at {where}{searched}")
    return got, ""


def read_facebook_account(page: Any, handle: str, now: datetime, cap: int = 500) -> tuple[list[dict[str, Any]], str]:
    """A page or profile's own newest posts (facebook.com/<name>), read with the saved login. With a `cap` over the feed's
    500 the post itself is the content (experts.py): every "See more" is opened first and the paragraphs are kept."""
    whole = cap > 500
    try:
        page.goto(f"{FB_BASE}/{handle}", wait_until="domcontentloaded", timeout=30_000)
        page.wait_for_timeout(SETTLE_MS)
        if any(p in str(getattr(page, "url", "")) for p in _WALL_PARTS):
            return [], "Facebook asked for a login"
        rows = _fb_rows(page, scrolls=3, expand=whole)
    except Exception as exc:  # noqa: BLE001
        return [], f"{type(exc).__name__}: {str(exc)[:160]}"
    got = [p for p in (facebook_post(r, now, cap, whole) for r in rows) if p]
    _NOTES.append(f"@{handle}: {len(rows)} post block(s), {len(got)} usable at {_where(page)}")
    return got, ""


# --- Instagram --------------------------------------------------------------------------------------------------------------

_IG_DESC = re.compile(
    r"^(?:(?P<likes>[\d.,]+[KkMm]?) likes?)?(?:,\s*)?(?:(?P<comments>[\d.,]+[KkMm]?) comments?)?\s*-?\s*"
    r"(?P<user>[\w.]+) on (?:(?P<date>[A-Z][a-z]+ \d{1,2}, \d{4})|Instagram)\s*:\s*[\"“](?P<caption>.*)[\"”]\.?\s*$", re.S)


def parse_instagram(desc: str, time_attr: str, href: str, cap: int = 500) -> dict[str, Any] | None:
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
    return {"id": pid.group(1), "username": m.group("user"), "text": caption[:cap],
            "permalink": f"{IG_BASE}/p/{pid.group(1)}/", "timestamp": when.isoformat(),
            "counts": {k: parse_count(v) for k, v in shown.items()} or {"likes": None}, "shown": shown}


_B64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
_IG_CODE = re.compile(r"/(?:p|reel)/([\w-]{6,})/?(?:[?#].*)?$")


def ig_code_time(link: str) -> datetime | None:
    """When a post was made, read off its link: the shortcode in /p/<code>/ or /reel/<code>/ is the media id in base 64, and the
    id's upper bits are the creation time in milliseconds (since 2011-08-25 14:07:01 UTC, Instagram's epoch). None when the link
    has no readable code. Checked on posts of known dates (DOpj0zUDVSq is 16 Sep 2025, DclqrvZDyzl is 28 Aug 2026)."""
    m = _IG_CODE.search(link or "")
    if not m:
        return None
    n = 0
    for ch in m.group(1):
        i = _B64.find(ch)
        if i < 0:
            return None
        n = n * 64 + i
    try:
        when = datetime.fromtimestamp(((n >> 23) + 1_314_220_021_721) / 1000, UTC)
    except (OverflowError, OSError, ValueError):
        return None
    return when if datetime(2012, 1, 1, tzinfo=UTC) <= when <= datetime.now(UTC) + timedelta(days=2) else None


def newest_first(links: list[str], n: int) -> list[str]:
    """The `n` NEWEST posts of a grid, not the first `n` tiles. A profile grid is newest first EXCEPT that up to three PINNED
    posts sit at the top however old they are, so reading the first three tiles read exactly the three pinned ones: on 26 Nov 2026
    (when PER_ACCOUNT_IG came down from 6 to 3) @labmuffinbeautyscience gave 3 posts 3,501 hours old and nothing fresh.
    The creation time is in each link (ig_code_time), so the newest are picked from every tile the grid showed, at no extra page
    load. If any link has no readable time the grid order stands, as before."""
    times = [ig_code_time(h) for h in links]
    if not links or any(t is None for t in times):
        return links[:n]
    order = sorted(range(len(links)), key=lambda i: (-times[i].timestamp(), i))  # type: ignore[union-attr]
    return [links[i] for i in order[:n]]


def pace(page: Any, low: int, high: int) -> None:
    """A random pause between two page loads, `low` to `high` ms (social_pace.py): the same beat every time reads as a robot."""
    import random
    page.wait_for_timeout(random.randint(low, high))


def _ig_open(page: Any, links: list[str], cap: int = 500) -> tuple[list[dict[str, Any]], str]:
    """Open each post link and read its description and time. (posts, what the first unreadable post page said)."""
    out: list[dict[str, Any]] = []
    refused = ""
    for href in links:
        page.goto(IG_BASE + href, wait_until="domcontentloaded", timeout=30_000)
        pace(page, 2500, 6500)
        info = page.evaluate(_IG_POST) or {}
        post = parse_instagram(info.get("desc", ""), info.get("time", ""), href, cap)
        if post:
            out.append(post)
        elif not refused:
            refused = " ".join(str(info.get("desc") or "").split())[:70]
    return out, refused


def read_instagram(page: Any, tag: str, now: datetime) -> tuple[list[dict[str, Any]], str]:
    """A hashtag's posts. Instagram shows a hashtag's TOP posts, which were all over 18 days old on 14 Nov 2026 (the oldest from
    February 2025), so this mostly finds nothing recent: accounts (read_instagram_account) are the reliable way to fresh posts."""
    try:
        page.goto(f"{IG_BASE}/explore/tags/{tag}/", wait_until="domcontentloaded", timeout=30_000)
        pace(page, 4000, 8500)
        if any(p in str(getattr(page, "url", "")) for p in _WALL_PARTS):
            return [], "Instagram asked for a login (save one as the secret PW_STORAGE_STATE_IG_B64; see ops/SOCIAL-LOGIN.md)"
        where = _where(page)
        links = newest_first(page.evaluate(_IG_LINKS) or [], PER_TAG_IG)
        out, refused = _ig_open(page, links)
    except Exception as exc:  # noqa: BLE001
        return [], f"{type(exc).__name__}: {str(exc)[:160]}"
    _NOTES.append(f"#{tag}: {len(links)} post link(s), {len(out)} read at {where}"
                  + (f"; a post page said: {refused}" if refused and len(out) < len(links) else ""))
    return out, ""


def read_instagram_account(page: Any, handle: str, now: datetime, cap: int = 500) -> tuple[list[dict[str, Any]], str]:
    """An account's newest posts: its profile grid lists them newest first (a pinned post can sit at the top). `cap` is how
    much of a caption is kept (500 for the feed of arguments, more where the post itself is the content)."""
    try:
        page.goto(f"{IG_BASE}/{handle}/", wait_until="domcontentloaded", timeout=30_000)
        pace(page, 4000, 8500)
        if any(p in str(getattr(page, "url", "")) for p in _WALL_PARTS):
            return [], "Instagram asked for a login (save one as the secret PW_STORAGE_STATE_IG_B64; see ops/SOCIAL-LOGIN.md)"
        where = _where(page)
        links = newest_first(page.evaluate(_IG_LINKS) or [], PER_ACCOUNT_IG)
        out, refused = _ig_open(page, links, cap)
    except Exception as exc:  # noqa: BLE001
        return [], f"{type(exc).__name__}: {str(exc)[:160]}"
    _NOTES.append(f"@{handle}: {len(links)} post link(s), {len(out)} read at {where}"
                  + (f"; a post page said: {refused}" if refused and len(out) < len(links) else ""))
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
ACCOUNT_READERS: dict[str, Callable[[Any, str, datetime], tuple[list[dict[str, Any]], str]]] = {
    "facebook": read_facebook_account, "instagram": read_instagram_account}


def collect(page: Any, platform: str, cfg: dict[str, Any], now: datetime,
            read: Callable[..., Any] | None = None, read_account: Callable[..., Any] | None = None,
            account_page: Any | None = None) -> tuple[list[dict[str, Any]], str]:
    """The hashtags and the watched accounts in the settings, newest `hours` only, loudest first. (posts, error); the error
    only when nothing was read. `account_page`: the page the watched accounts are read with when it is not the hashtags' own
    (Facebook: hashtags without the login, accounts with it, see fetch)."""
    opts = cfg.get(platform) or {}
    hours = max(6, min(14 * 24, int(opts.get("hours") or 72)))
    tags = list(dict.fromkeys(t for t in (hashtag(q) for q in (opts.get("queries") or [])) if t))[:MAX_TAGS]
    handles = [h for h in dict.fromkeys(str(a).strip().lstrip("@") for a in (opts.get("accounts") or []))
               if re.fullmatch(r"[\w.\-]{1,60}", h)][:MAX_ACCOUNTS]
    if not tags and not handles:
        return [], ""
    read = read or READERS[platform]
    read_account = read_account or ACCOUNT_READERS[platform]
    seen: set[str] = set()
    posts: list[dict[str, Any]] = []
    errors: list[str] = []
    stats = {"tags": len(tags), "accounts": len(handles), "found": 0, "too_old": 0, "own": 0, "newest_h": None, "hours": hours}
    _NOTES.clear()
    jobs = [(read, t, f"#{t}", page) for t in tags] + [(read_account, h, f"@{h}", account_page or page) for h in handles]
    for fn, name, shown, on in jobs:
        got, err = fn(on, name, now)
        if err:
            errors.append(err)
            log.warning("%s %s not read: %s", platform, shown, err)
            if "asked for a login" in err and platform == "instagram":
                break                                              # every page will say the same
        for p in got:
            when = _when(p.get("timestamp"))
            if p["id"] in seen or not when:
                continue
            stats["found"] += 1
            age = (now - when).total_seconds() / 3600
            stats["newest_h"] = round(age) if stats["newest_h"] is None else min(stats["newest_h"], round(age))
            if age > hours:
                stats["too_old"] += 1
                continue
            if is_own(p, cfg.get("own_accounts") or []):
                stats["own"] += 1
                continue
            seen.add(p["id"])
            posts.append(p)
    posts.sort(key=score, reverse=True)
    LAST[platform] = {**stats, "notes": list(_NOTES)[:6]}
    if not posts and errors:
        return [], errors[0]
    return posts, ""


def stats_text(platform: str) -> str:
    """One line on what the last read saw ('found 6, 6 older than 72 h, newest 90 h old; #halal: 0 post block(s)...')."""
    st = LAST.get(platform)
    if not st:
        return ""
    bits = [f"found {st['found']} post(s)"]
    if st["too_old"]:
        bits.append(f"{st['too_old']} older than {st['hours']} h")
    if st["own"]:
        bits.append(f"{st['own']} your own")
    if st["newest_h"] is not None:
        bits.append(f"newest {st['newest_h']} h old")
    return ", ".join(bits) + ("; " + "; ".join(st["notes"][:3]) if st.get("notes") else "")


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
                if platform == "facebook" and state:
                    # A logged-in Facebook shows NO post on a hashtag page or in a post search (14 and 16 Nov 2026: 0 blocks for
                    # every tag, and the sweep went from 1-2 posts to 0 the hour a working Facebook login was saved), while the
                    # same pages without a login show one post a tag. So hashtags are read without the login and only the
                    # watched accounts, which need it, are read with it.
                    anonymous = browser.new_context(**opts).new_page()
                    logged_in = browser.new_context(**opts, storage_state=state).new_page()
                    return collect(anonymous, platform, cfg, now, account_page=logged_in)
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
