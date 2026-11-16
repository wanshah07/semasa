"""Two sources for LinkedIn ideas that Wan lists himself (16 Nov 2026), both parts of the own-sources sweep (intake.py):

  websites  "add segment in linkedn that I can add url website to scrape such as https://lom.agc.gov.my/index.php". Any page
            that lists what is new: each run reads the page, takes the links it shows in its body, and puts the ones not seen
            before in the feed (section `website`). The writer says in one line what each is and whether it matters; an item
            it judges irrelevant is kept, hidden, like a regulator's.
  linkedin  "for linkedn other than scrape from threads, fb, ig, tt, scrape also from linkedns based on recent case, and big
            impression". Two lists: post links Wan pasted, always shown; and company pages to watch, of which only recent posts
            with many reactions are shown (section `linkedin`).

WHAT LINKEDIN SHOWS A VISITOR WHO IS NOT SIGNED IN (measured 16 Nov 2026, and the reason the lists are these two):
  - a post's own page: the text, the author, the date, and how many reactions and comments it has;
  - a COMPANY page (also /school/ and /showcase/): its last eight to ten posts with their reaction counts, in a browser;
  - a PERSON's profile or activity page: a sign-in wall. So a personal profile cannot be watched, and one put in the list
    is reported as such instead of silently reading nothing.
Nothing here signs in, and nothing is read that LinkedIn does not show a visitor. The address of a post is kept for Wan; it
never reaches a post of his own (the idea writer's standing rule for every social source).
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from . import db, fetch, watch
from .log import get_logger

log = get_logger("semasa.own_links")

SEEN_KEY = "sources_seen"           # semasa_settings row, written by this module only: what each website has already shown
MAX_SITES, MAX_NEW, SEEN_KEEP = 12, 20, 600
MAX_POSTS, MAX_PAGES, PER_PAGE = 30, 12, 5
MIGRATION = "supabase/083_linkedin_sources.sql has not been run in the SQL editor yet"
_WS = re.compile(r"\s+")
_LD = re.compile(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', re.S | re.I)
_COMPANY = re.compile(r"^/(company|school|showcase)/([^/?#]+)", re.I)
_POST = re.compile(r"^/(posts/[^/?#]+|feed/update/urn:li:[a-zA-Z]+:\d+|pulse/[^/?#]+)", re.I)
_SKIP_TAGS = ("nav", "header", "footer", "script", "style", "aside", "form", "noscript")


def _clean(text: Any) -> str:
    return _WS.sub(" ", str(text or "")).strip()


def web_url(raw: Any) -> str:
    """An http(s) address with no fragment, or "" for anything else (a mailto, a javascript link, a bare word)."""
    try:
        p = urlsplit(str(raw or "").strip())
    except ValueError:
        return ""
    if p.scheme not in ("http", "https") or not p.netloc:
        return ""
    return urlunsplit((p.scheme, p.netloc.lower(), p.path or "/", p.query, ""))


# --- websites ---------------------------------------------------------------------------------------------------------

def site_links(html: str, base: str) -> tuple[str, list[dict[str, str]]]:
    """(the page's own title, the links its body shows as [{title, url}], in page order).

    A link is kept when its words read as a headline: 20 to 300 characters, outside the menus, header and footer. A page
    often lists the same item twice (lom.agc.gov.my: "P.U. (A) 392/2026 - TRADE DESCRIPTIONS ..." under What's New and
    "TRADE DESCRIPTIONS ..." under latest), so a title that is the tail of one already kept is the same item and is dropped."""
    soup = BeautifulSoup(html or "", "html.parser")
    name = _clean(soup.title.string if soup.title and soup.title.string else "")[:80]
    for tag in soup(_SKIP_TAGS):
        tag.decompose()
    out: list[dict[str, str]] = []
    urls: set[str] = set()
    for a in soup.find_all("a", href=True):
        title = _clean(a.get_text(" ", strip=True))
        url = web_url(urljoin(base, a["href"]))
        if not url or url in urls or not 20 <= len(title) <= 300:
            continue
        low = title.lower()
        if any(k["title"].lower() == low or k["title"].lower().endswith(" " + low) or k["title"].lower().endswith("- " + low)
               for k in out):
            continue
        urls.add(url)
        out.append({"title": title, "url": url})
    return name, out


def _digest(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def _load_seen(store: Any) -> dict[str, list[str]]:
    rows = store.table(db.SETTINGS).select("value").eq("key", SEEN_KEY).execute().data or []
    value = (rows[0].get("value") if rows else None) or {}
    return {k: [str(x) for x in v][-SEEN_KEEP:] for k, v in value.items() if isinstance(v, list)}


def _save_seen(store: Any, value: dict[str, list[str]], now: datetime) -> None:
    store.table(db.SETTINGS).upsert({"key": SEEN_KEY, "value": value, "updated_at": now.isoformat()},
                                    on_conflict="key").execute()


def do_websites(store: Any, llm: Any, client: Any, cfg: dict[str, Any], now: datetime, dry: bool,
                get: Any = None) -> dict[str, Any]:
    """Read each listed page and put what it newly shows in the feed. A page's first read takes its first `max_new` links
    (20 unless set: the one that matters is rarely the first, and on lom.agc.gov.my the halal marking order stood sixth
    behind five appointments) and remembers the rest; after that only links it has not shown before are new. The writer
    judges each, and what it calls irrelevant is stored hidden, so a long list does not flood the page. What a page has
    shown is remembered apart from the feed (SEEN_KEY), because the feed is pruned."""
    from . import intake
    get = get or (lambda url: fetch.get(url, timeout=30).text)
    sites = [u for u in dict.fromkeys(web_url(s) for s in (cfg.get("sites") or [])) if u][:MAX_SITES]
    limit = max(1, min(int(cfg.get("max_new") or MAX_NEW), 30))
    seen = _load_seen(store)
    read: dict[str, int] = {}
    errors: dict[str, str] = {}
    fresh: list[dict[str, Any]] = []
    for site in sites:
        try:
            name, links = site_links(get(site), site)
        except Exception as exc:  # noqa: BLE001 - one site that does not answer must not stop the others
            errors[site] = f"{type(exc).__name__}: {str(exc)[:140]}"
            continue
        read[site] = len(links)
        host = urlsplit(site).netloc.removeprefix("www.")
        known = set(seen.get(site) or [])
        have = intake.have(store, [k["url"] for k in links]) if links else set()
        new = [k for k in links if _digest(k["url"]) not in known and k["url"] not in have][:limit]
        seen[site] = [*(seen.get(site) or []), *(_digest(k["url"]) for k in links if _digest(k["url"]) not in known)][-SEEN_KEEP:]
        fresh += [{"section": "website", "source": name or host, "title": k["title"][:500], "url": k["url"], "summary": "",
                   "kind": "Laman web", "country": "", "lang": "", "published_at": None, "raw": {"site": site, "host": host}}
                  for k in new]
    watch.annotate(llm, fresh)             # one line on what each is, its domain, and whether it matters (not relevant = hidden)
    try:
        written = intake.write(store, [watch.to_row(r) for r in fresh], dry)
    except intake.NeedsMigration as exc:
        raise RuntimeError(MIGRATION) from exc
    if not dry and sites:
        # a site taken off the list is forgotten, so putting it back starts it afresh; the LinkedIn memory is kept as it is
        keep = {k: v for k, v in seen.items() if k in sites or k == "linkedin"}
        _save_seen(store, keep, now)
    return {"sites": len(sites), "read": read, "new": written, "shown": sum(1 for r in fresh if r.get("relevant") is not False),
            **({"errors": errors} if errors else {})}


# --- LinkedIn ---------------------------------------------------------------------------------------------------------

def linkedin_kind(raw: Any) -> tuple[str, str]:
    """("post" | "page" | "profile" | "", the address to read). A post or an article is read as it is; a company, school or
    showcase page is read at its root; a person's profile cannot be read without signing in."""
    url = web_url(raw)
    p = urlsplit(url) if url else None
    if not p or not (p.netloc == "linkedin.com" or p.netloc.endswith(".linkedin.com")):
        return "", ""
    if _POST.match(p.path):
        return "post", urlunsplit(("https", "www.linkedin.com", p.path.rstrip("/"), "", ""))
    m = _COMPANY.match(p.path)
    if m:
        return "page", f"https://www.linkedin.com/{m.group(1).lower()}/{m.group(2)}/"
    if p.path.startswith("/in/"):
        return "profile", url
    return "", ""


def _count(v: Any) -> int:
    try:
        return int(str(v).replace(",", "").strip() or 0)
    except ValueError:
        return 0


def _counts(stat: Any, extra_comments: Any = None) -> dict[str, int]:
    out = {"reactions": 0, "comments": _count(extra_comments)}
    for s in stat if isinstance(stat, list) else [stat] if isinstance(stat, dict) else []:
        kind = str(s.get("interactionType") or "")
        if "Like" in kind:
            out["reactions"] = _count(s.get("userInteractionCount"))
        elif "Comment" in kind:
            out["comments"] = out["comments"] or _count(s.get("userInteractionCount"))
    return out


def _when(v: Any) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def postings(html: str) -> list[dict[str, Any]]:
    """Every post LinkedIn describes on a page (its schema.org SocialMediaPosting blocks), as
    {url, author, text, headline, when, reactions, comments}. A post's own page has one; a company page has its last few."""
    out: list[dict[str, Any]] = []
    for block in _LD.findall(html or ""):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        items = data.get("@graph") if isinstance(data, dict) and isinstance(data.get("@graph"), list) else [data]
        for it in items:
            if not isinstance(it, dict) or it.get("@type") not in ("SocialMediaPosting", "Article", "DiscussionForumPosting"):
                continue
            kind, url = linkedin_kind(it.get("url") or it.get("@id") or it.get("mainEntityOfPage"))
            text = str(it.get("articleBody") or it.get("text") or "").strip()
            if kind != "post" or not text:
                continue
            author = it.get("author") if isinstance(it.get("author"), dict) else {}
            out.append({"url": url, "author": _clean(author.get("name"))[:120], "text": text,
                        "headline": _clean(it.get("headline"))[:300], "when": _when(it.get("datePublished")),
                        **_counts(it.get("interactionStatistic"), it.get("commentCount"))})
    return out


def metrics(p: dict[str, Any]) -> str:
    return " · ".join(x for x in (f"{p['reactions']:,} reactions" if p.get("reactions") else "",
                                  f"{p['comments']:,} comments" if p.get("comments") else "") if x)


def _row(p: dict[str, Any], pasted: bool) -> dict[str, Any]:
    title = p["headline"] or p["text"].splitlines()[0]
    return {"section": "linkedin", "source": f"LinkedIn · {p['author']}" if p["author"] else "LinkedIn", "kind": "Post",
            "title": title[:300], "url": p["url"], "summary": p["text"][:900], "country": "", "lang": "",
            "published_at": p["when"].date() if p["when"] else None,
            "raw": {"metrics": metrics(p), "reactions": p["reactions"], "comments": p["comments"], "author": p["author"],
                    "original": p["text"][:4000], **({"pasted": True} if pasted else {})}}


def do_linkedin(store: Any, llm: Any, client: Any, cfg: dict[str, Any], now: datetime, dry: bool,
                get: Any = None, browse: Any = None) -> dict[str, Any]:
    """Pasted posts are read one by one and always shown. A watched page's posts are shown when they are recent (`days`) and
    carry at least `min_reactions`, loudest first, PER_PAGE at most from one page. `get(url)` reads a post's page over plain
    HTTP; `browse(url)` reads a page in a browser (LinkedIn answers a company page only to one)."""
    from . import intake
    get = get or (lambda url: fetch.get(url, timeout=30).text)
    wanted = [linkedin_kind(u) for u in (cfg.get("posts") or [])]
    posts = list(dict.fromkeys(u for k, u in wanted if k == "post"))[:MAX_POSTS]
    listed = [linkedin_kind(u) for u in (cfg.get("pages") or [])]
    pages = list(dict.fromkeys(u for k, u in listed if k == "page"))[:MAX_PAGES]
    profiles = sum(1 for k, _ in wanted + listed if k == "profile")
    floor = max(0, int(cfg.get("min_reactions") or 0))
    since = now - timedelta(days=max(1, int(cfg.get("days") or 30)))
    errors: dict[str, str] = {}
    found: list[tuple[dict[str, Any], bool]] = []
    seen = _load_seen(store)
    known = set(seen.get("linkedin") or [])           # posts already put in the feed once: the feed is pruned, this is not
    have = intake.have(store, posts) if posts else set()
    for url in posts:
        if url in have or _digest(url) in known:
            continue
        try:
            got = [p for p in postings(get(url)) if p["url"] == url] or postings(get(url))[:1]
        except Exception as exc:  # noqa: BLE001 - one link that does not answer must not stop the others
            errors[url] = f"{type(exc).__name__}: {str(exc)[:140]}"
            continue
        if not got:
            errors[url] = "LinkedIn did not show this post to a visitor who is not signed in"
            continue
        found.append(({**got[0], "url": url}, True))
    read: dict[str, int] = {}
    if pages:
        opened = None
        try:
            if browse is None:
                opened = fetch.Browser()
                opened.start()
                browse = lambda url: opened.page_html(url, settle_ms=2500)   # noqa: E731
            for url in pages:
                try:
                    seen_here = postings(browse(url))
                except Exception as exc:  # noqa: BLE001
                    errors[url] = f"{type(exc).__name__}: {str(exc)[:140]}"
                    continue
                read[url] = len(seen_here)
                if not seen_here:
                    errors[url] = "LinkedIn showed no posts on this page to a visitor who is not signed in"
                loud = [p for p in seen_here if p["reactions"] >= floor and (p["when"] is None or p["when"] >= since)]
                loud.sort(key=lambda p: p["reactions"], reverse=True)
                found += [(p, False) for p in loud[:PER_PAGE]]
        except Exception as exc:  # noqa: BLE001 - no browser on this machine: the pasted posts still go in
            errors["browser"] = f"{type(exc).__name__}: {str(exc)[:140]}"
        finally:
            if opened is not None:
                opened.stop()
    urls = [p["url"] for p, _ in found]
    have = intake.have(store, urls) if urls else set()
    rows, taken = [], set()
    for p, pasted in found:
        if p["url"] in have or p["url"] in taken or _digest(p["url"]) in known:
            continue
        taken.add(p["url"])
        rows.append(_row(p, pasted))
    watch.annotate(llm, rows)
    for r in rows:
        if r["raw"].get("pasted"):
            r["relevant"] = True               # Wan chose this one himself: it is shown whatever the writer made of it
    try:
        written = intake.write(store, [watch.to_row(r) for r in rows], dry)
    except intake.NeedsMigration as exc:
        raise RuntimeError(MIGRATION) from exc
    if not dry and rows:
        seen["linkedin"] = [*(seen.get("linkedin") or []), *(_digest(r["url"]) for r in rows)][-SEEN_KEEP:]
        _save_seen(store, seen, now)
    return {"posts": len(posts), "pages": len(pages), "read": read, "new": written,
            "shown": sum(1 for r in rows if r.get("relevant") is not False),
            **({"profiles_skipped": profiles} if profiles else {}), **({"errors": errors} if errors else {})}
