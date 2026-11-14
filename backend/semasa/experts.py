"""Expert Content (Wan, 14 Nov 2026: "add another segment Expert Content, under it put AI Expert, Halal Expert ... in every
subsegment I can add handler username and you will scrape their post (threads, fb, ig) ... put original post and summary ... can
put as Idea ... automatically send to AI brain as reference only for AI expert ... list handler that worth to follow").

What it does, once a sweep (a part of intake.py, so it runs with the Sources workflow and its "Sweep now"):
  1. reads the newest posts of every handle Wan registered, on the platforms he ticked for it: a Threads profile in a plain
     browser (threads_web), an Instagram profile and a Facebook page with the saved login (social_web);
  2. asks the writer to analyse each new post: is it about the category's niche, what is its point (a title), a summary, and
     what to take from it. The post's own words are kept beside the summary (raw.original): nothing is invented, and a post
     that is off the niche (a holiday photo, a giveaway) becomes a hidden marker so it is not judged again;
  3. writes the rows to the feed (semasa_watch, section 'expert', raw.category). Wan turns one into an idea himself;
  4. for a category with "brain" on (AI Expert by default), files each new relevant post in the AI brain's inbox as a
     REFERENCE (semasa_brain_inbox, hint 'reference'): the brain worker reads it like anything else dropped in;
  5. once a day, looks for accounts worth following: it searches Threads for the category's keywords, groups what it finds by
     author, and asks the writer which authors teach the niche, judged ONLY on the posts read. Those are suggestions
     (settings.expert_suggestions): Wan adds one with a click, and a handle he added or dismissed never comes back.

The page owns settings.experts (categories, handles, keywords, the brain switch, dismissed handles) and only the page writes it;
this module only reads it. This module owns settings.expert_suggestions. So a save in the page and a sweep can never overwrite
each other. Nothing here posts, approves or drafts a thing, and no handle is ever made up: a suggestion is an account whose
posts were actually read.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

from . import db, social_web, threads_web
from .log import get_logger

log = get_logger("semasa.experts")

KEY = "experts"
SUGGEST_KEY = "expert_suggestions"
SECTION = "expert"
PLATFORMS = ("threads", "facebook", "instagram")
NAMES = {"threads": "Threads", "facebook": "Facebook", "instagram": "Instagram"}
MAX_READS = 20                 # handle-and-platform pages opened in one sweep (an Instagram profile is seven page loads)
MAX_BRAIN = 10                 # posts filed in the AI brain in one sweep
MAX_SUGGESTIONS = 12           # kept per category
DISCOVER_EVERY = timedelta(hours=20)
HANDLE = re.compile(r"[\w.\-]{1,60}")

DEFAULTS: dict[str, Any] = {
    "enabled": True, "hours": 14 * 24, "per_handle": 5,
    "categories": [
        {"id": "ai", "name": "AI Expert", "brain": True, "handles": [], "dismissed": [],
         "niche": "artificial intelligence in practice: AI tools, large language models, agents, prompting, automation",
         "keywords": ["AI agent", "prompt engineering", "LLM"]},
        {"id": "halal", "name": "Halal Expert", "brain": False, "handles": [], "dismissed": [],
         "niche": "halal certification and compliance in Malaysia: JAKIM, MPPHM, MS 1500, halal assurance, ingredients",
         "keywords": ["sijil halal", "halal JAKIM", "pensijilan halal"]},
    ],
}

SYSTEM = """You read social-media posts written by subject experts, for ws.regulab, a Malaysian regulatory consultancy.
Each item names the expert's field ("niche"). Use ONLY the words of the post: no fact, number, name or claim that is not in it.
For each item decide:
- "relevant": true when the post teaches, explains, argues or reports something inside the niche. False for personal life,
  greetings, giveaways, pure promotion with no substance, and posts about something else.
- "title": the post's main point in one line, at most 90 characters, in Malaysian Malay (keep English technical terms).
  Never the account name, the platform or a link. Never Bahasa Indonesia.
- "summary": two or three sentences in Malaysian Malay saying what the expert says and how they support it.
- "why": one sentence in Malaysian Malay: what to take from it or do with it.
Answer with ONE JSON object:
{"items": [{"i": 0, "relevant": true, "title": "...", "summary": "...", "why": "..."}]}"""

SUGGEST_SYSTEM = """You judge whether social-media accounts are worth following as subject experts, for a Malaysian regulatory
consultancy. Each item is one account with a few of its own posts, and the field ("niche") wanted. Judge ONLY from the posts
given. "worth": true when the posts show real knowledge or teaching inside the niche; false for news reposts with no insight,
jokes, sellers, complaints and accounts that only mention the topic. "why": one short sentence in Malaysian Malay saying what
the account is good at, from the posts. Answer with ONE JSON object:
{"items": [{"i": 0, "worth": true, "why": "..."}]}"""


def clean_handle(v: Any) -> str:
    h = str(v or "").strip().lstrip("@").strip("/")
    return h if HANDLE.fullmatch(h) else ""


def categories(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """The categories as the sweep reads them: an id, a name, clean handles each with at least one known platform."""
    out = []
    for c in cfg.get("categories") or []:
        if not isinstance(c, dict) or not str(c.get("id") or "").strip():
            continue
        seen: set[str] = set()
        handles = []
        for h in c.get("handles") or []:
            name = clean_handle(h.get("handle") if isinstance(h, dict) else h)
            plats = [p for p in ((h.get("platforms") if isinstance(h, dict) else None) or ["threads"]) if p in PLATFORMS]
            if name and plats and name.lower() not in seen:
                seen.add(name.lower())
                handles.append({"handle": name, "platforms": plats})
        out.append({"id": str(c["id"]).strip()[:40], "name": str(c.get("name") or c["id"])[:60],
                    "niche": str(c.get("niche") or "")[:300], "brain": bool(c.get("brain")), "handles": handles,
                    "keywords": [str(k).strip()[:60] for k in (c.get("keywords") or []) if str(k).strip()][:5],
                    "dismissed": [clean_handle(d).lower() for d in (c.get("dismissed") or []) if clean_handle(d)]})
    return out


def load(store: Any) -> dict[str, Any]:
    rows = store.table(db.SETTINGS).select("value").eq("key", KEY).execute().data or []
    stored = (rows[0].get("value") if rows else None) or {}
    return {**DEFAULTS, **{k: v for k, v in stored.items() if k in DEFAULTS and v is not None}}


def _when(v: Any) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def _mine(post: dict[str, Any], handle: str, platform: str) -> bool:
    """A profile page also shows what the account reposted or quoted: only its own posts are the expert's words."""
    user = str(post.get("username") or "").lower()
    if platform == "facebook":
        return True                                   # a Facebook post row carries no author; the page read is the author's
    return not user or user == handle.lower()


def read_threads(page: Any, handle: str, now: datetime) -> tuple[list[dict[str, Any]], str]:
    return threads_web.read_url(page, f"{threads_web.BASE}/@{handle}", cap=2000)


READERS: dict[str, Callable[[Any, str, datetime], tuple[list[dict[str, Any]], str]]] = {
    "threads": read_threads, "instagram": social_web.read_instagram_account, "facebook": social_web.read_facebook_account}


def collect(pages: dict[str, Any], cats: list[dict[str, Any]], cfg: dict[str, Any], now: datetime,
            readers: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Every registered handle on every platform ticked for it. (posts, stats). `pages` maps a platform to the browser page
    that reads it (None when that platform cannot be read this run, e.g. no saved login)."""
    readers = readers or READERS
    hours = max(24, min(60 * 24, int(cfg.get("hours") or 14 * 24)))
    per = max(1, min(15, int(cfg.get("per_handle") or 5)))
    posts: list[dict[str, Any]] = []
    stats: dict[str, Any] = {"reads": 0, "found": 0, "errors": [], "skipped": 0, "by_handle": {}}
    seen: set[str] = set()
    walled: set[str] = set()
    todo = [(cat, h, platform) for cat in cats for h in cat["handles"] for platform in h["platforms"]]
    if len(todo) > MAX_READS:
        # more pages than one sweep opens: start somewhere else each sweep, so the same handles are not the ones left out
        at = int(now.timestamp() // (6 * 3600)) % len(todo)
        todo = todo[at:] + todo[:at]
    for cat, h, platform in todo:
        label = f"@{h['handle']} ({NAMES[platform]})"
        page = pages.get(platform)
        if page is None or platform in walled:
            stats["errors"].append(f"{label}: {pages.get(platform + '_error') or 'not read: the platform asked for a login'}")
            continue
        if stats["reads"] >= MAX_READS:
            stats["skipped"] += 1
            continue
        stats["reads"] += 1
        got, err = readers[platform](page, h["handle"], now)
        if err:
            stats["errors"].append(f"{label}: {err}")
            if "asked for a login" in err:
                walled.add(platform)                   # every other page of that platform will say the same
            continue
        mine = []
        for p in got:
            when = _when(p.get("timestamp"))
            link = str(p.get("permalink") or "")
            if not link or link in seen or not when or now - when > timedelta(hours=hours) or not _mine(p, h["handle"], platform):
                continue
            mine.append({**p, "when": when})
        mine.sort(key=lambda p: p["when"], reverse=True)
        for p in mine[:per]:
            seen.add(p["permalink"])
            posts.append({**p, "category": cat["id"], "category_name": cat["name"], "niche": cat["niche"],
                          "handle": h["handle"], "platform": platform, "brain": cat["brain"]})
        stats["by_handle"][label] = len(mine[:per])
        stats["found"] += len(mine[:per])
    return posts, stats


def metrics_of(p: dict[str, Any]) -> str | None:
    return threads_web.metrics_text(p) if p["platform"] == "threads" else social_web.metrics_text(p)


def annotate(llm: Any, posts: list[dict[str, Any]], batch: int = 5) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(kept, rejected): the posts the writer answered. A post it never answered is in neither, and is tried again next sweep."""
    if not posts or not llm or not getattr(llm, "configured", False):
        return [], []
    kept: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    misses = 0
    for start in range(0, len(posts), batch):
        if misses >= 2:
            log.warning("the writer stopped answering; %d expert post(s) left unread", len(posts) - start)
            break
        chunk = posts[start:start + batch]
        user = "Items:\n" + "\n".join(json.dumps({"i": k, "niche": p["niche"] or p["category_name"], "post": p["text"][:1200]},
                                                 ensure_ascii=False) for k, p in enumerate(chunk))
        out = llm.chat_json(SYSTEM, user, max_tokens=320 * len(chunk) + 120)
        if out is None:
            misses += 1
            continue
        misses = 0
        for ans in (out or {}).get("items") or []:
            try:
                i = int(ans.get("i"))
            except (TypeError, ValueError, AttributeError):
                continue
            if not 0 <= i < len(chunk):
                continue
            if ans.get("relevant") not in (True, "true", "yes"):
                rejected.append(chunk[i])
                continue
            title, summary = str(ans.get("title") or "").strip(), str(ans.get("summary") or "").strip()
            if title and summary:
                kept.append({**chunk[i], "title": title[:200], "summary": summary[:900],
                             "why": str(ans.get("why") or "").strip()[:400]})
    return kept, rejected


def to_row(p: dict[str, Any], brain: bool = False) -> dict[str, Any]:
    seen = metrics_of(p)
    raw = {"category": p["category"], "category_name": p["category_name"], "handle": p["handle"], "platform": p["platform"],
           "original": p["text"][:2000], **({"metrics": seen} if seen else {}), **({"brain": True} if brain else {})}
    return {"section": SECTION, "source": f"{NAMES[p['platform']]} · @{p['handle']}", "kind": p["category_name"], "country": None,
            "title": p["title"], "url": p["permalink"], "summary": p["summary"], "why": p.get("why") or None, "domain": None,
            "relevant": True, "lang": "ms", "summary_source": "llm", "raw": raw, "published_at": p["when"].isoformat()}


def tombstone(p: dict[str, Any]) -> dict[str, Any]:
    """A hidden marker for a post off the niche: its link only, so the next sweep knows it has been read."""
    return {"section": SECTION, "source": f"{NAMES[p['platform']]} · @{p['handle']}", "kind": p["category_name"], "country": None,
            "title": p["text"].splitlines()[0][:200], "url": p["permalink"], "summary": None, "why": None, "domain": None,
            "relevant": False, "lang": "ms", "summary_source": "llm", "raw": {"category": p["category"], "handle": p["handle"]},
            "published_at": p["when"].isoformat()}


def brain_row(p: dict[str, Any]) -> dict[str, Any]:
    """The AI brain's inbox row for one post: the expert's own words first, then the summary, filed as a reference."""
    body = (f"Expert: @{p['handle']} on {NAMES[p['platform']]} ({p['category_name']})\n\nOriginal post:\n{p['text'][:2000]}\n\n"
            f"Summary: {p['summary']}" + (f"\nTakeaway: {p['why']}" if p.get("why") else ""))
    return {"source_kind": "text", "title": p["title"][:200], "url": p["permalink"], "body": body, "hint": "reference",
            "note": f"Expert content ({p['category_name']}): a reference only, the view of one expert, not a verified fact."}


def file_in_brain(store: Any, posts: list[dict[str, Any]], dry: bool) -> int:
    """File each post in the brain's inbox, skipping a link already there. Returns how many went in. Never raises."""
    todo = [p for p in posts if p.get("brain")][:MAX_BRAIN]
    if not todo or dry:
        return len(todo)
    try:
        urls = [p["permalink"] for p in todo]
        known = {r["url"] for r in (store.table(db.BRAIN_INBOX).select("url").in_("url", urls).execute().data or [])}
        rows = [brain_row(p) for p in todo if p["permalink"] not in known]
        if rows:
            store.table(db.BRAIN_INBOX).insert(rows).execute()
        return len(rows)
    except Exception as exc:  # noqa: BLE001 - the feed rows are already written; the brain is a copy
        log.warning("expert posts not filed in the AI brain: %s", str(exc)[:160])
        return 0


# --- accounts worth following -------------------------------------------------------------------------------------------

def candidates(found: list[dict[str, Any]], cat: dict[str, Any], own: list[str], limit: int = 8) -> list[dict[str, Any]]:
    """Authors seen in the keyword search, loudest first, without the handles already registered, dismissed or Wan's own."""
    skip = {h["handle"].lower() for h in cat["handles"]} | set(cat["dismissed"]) | {str(o).lower().lstrip("@") for o in own}
    by: dict[str, dict[str, Any]] = {}
    for p in found:
        user = clean_handle(p.get("username"))
        if not user or user.lower() in skip:
            continue
        a = by.setdefault(user.lower(), {"handle": user, "platform": "threads", "posts": [], "score": 0})
        a["posts"].append(p["text"][:400])
        a["score"] += threads_web.score(p) + 1
    return sorted(by.values(), key=lambda a: (len(a["posts"]), a["score"]), reverse=True)[:limit]


def judge(llm: Any, cands: list[dict[str, Any]], cat: dict[str, Any], now: datetime) -> list[dict[str, Any]]:
    if not cands or not llm or not getattr(llm, "configured", False):
        return []
    user = "Items:\n" + "\n".join(json.dumps({"i": k, "niche": cat["niche"] or cat["name"], "posts": c["posts"][:3]},
                                             ensure_ascii=False) for k, c in enumerate(cands))
    out = llm.chat_json(SUGGEST_SYSTEM, user, max_tokens=120 * len(cands) + 100) or {}
    good = []
    for ans in out.get("items") or []:
        try:
            i = int(ans.get("i"))
        except (TypeError, ValueError, AttributeError):
            continue
        if 0 <= i < len(cands) and ans.get("worth") in (True, "true", "yes") and str(ans.get("why") or "").strip():
            c = cands[i]
            good.append({"handle": c["handle"], "platform": c["platform"], "why": str(ans["why"]).strip()[:240],
                         "posts": len(c["posts"]), "sample": c["posts"][0][:200], "at": now.isoformat()})
    return good


def merge_suggestions(old: list[dict[str, Any]], new: list[dict[str, Any]], cat: dict[str, Any]) -> list[dict[str, Any]]:
    """Newest first, one a handle, never one that is registered or dismissed (so an added name leaves the list)."""
    skip = {h["handle"].lower() for h in cat["handles"]} | set(cat["dismissed"])
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for s in [*new, *(old or [])]:
        h = clean_handle(s.get("handle")).lower() if isinstance(s, dict) else ""
        if h and h not in skip and h not in seen:
            seen.add(h)
            out.append(s)
    return out[:MAX_SUGGESTIONS]


def discovery_due(store: Any, now: datetime) -> bool:
    rows = store.table(db.SETTINGS).select("value").eq("key", SUGGEST_KEY).execute().data or []
    last = _when(((rows[0].get("value") if rows else None) or {}).get("at"))
    return not last or now - last >= DISCOVER_EVERY


def discover(store: Any, llm: Any, page: Any, cats: list[dict[str, Any]], own: list[str], now: datetime, dry: bool,
             read: Callable[..., Any] = threads_web.read_url) -> dict[str, Any]:
    """Once a day: search Threads for each category's keywords and keep the authors the writer judges worth following."""
    rows = store.table(db.SETTINGS).select("value").eq("key", SUGGEST_KEY).execute().data or []
    value = dict((rows[0].get("value") if rows else None) or {})
    last = _when(value.get("at"))
    due = page is not None and (not last or now - last >= DISCOVER_EVERY)
    lists = dict(value.get("lists") or {})
    added = 0
    for cat in cats:
        fresh: list[dict[str, Any]] = []
        if due and cat["keywords"]:
            found: list[dict[str, Any]] = []
            for kw in cat["keywords"][:3]:
                got, err = read(page, f"{threads_web.BASE}/search?q={quote(kw)}&serp_type=default")
                if err:
                    log.warning("expert discovery: %s not searched: %s", kw, err)
                found += got
            fresh = judge(llm, candidates(found, cat, own), cat, now)
            added += len(fresh)
        lists[cat["id"]] = merge_suggestions(lists.get(cat["id"]) or [], fresh, cat)     # also prunes added/dismissed names
    out = {"at": now.isoformat() if due else value.get("at"), "lists": lists}
    if not dry and out != value:
        store.table(db.SETTINGS).upsert({"key": SUGGEST_KEY, "value": out, "updated_at": now.isoformat()},
                                        on_conflict="key").execute()
    return {"searched": bool(due), "suggested": added}


# --- the sweep's part ----------------------------------------------------------------------------------------------------

def browse(run: Callable[[dict[str, Any]], Any]) -> Any:
    """Open one browser with a plain page for Threads and, when a login is saved, a logged-in page for Facebook and Instagram;
    call run(pages); close everything. `pages` carries '<platform>_error' for a platform that cannot be read."""
    pages: dict[str, Any] = {"threads": None, "facebook": None, "instagram": None}
    state = social_web.storage_state_path()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        for p in PLATFORMS:
            pages[p + "_error"] = "Playwright is not installed"
        return run(pages)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            try:
                pages["threads"] = browser.new_context(locale="en-MY", viewport={"width": 1280, "height": 2200}).new_page()
                if state:
                    ctx = browser.new_context(storage_state=state, locale="en-MY", timezone_id="UTC",
                                              viewport={"width": 1280, "height": 2400})
                    pages["facebook"] = pages["instagram"] = ctx.new_page()
                else:
                    why = "needs a saved login (the secret PW_STORAGE_STATE_B64; see ops/SOCIAL-LOGIN.md)"
                    pages["facebook_error"] = pages["instagram_error"] = why
                return run(pages)
            finally:
                browser.close()
    finally:
        if state:
            try:
                import os
                os.unlink(state)
            except OSError:
                pass


def sweep(store: Any, llm: Any, cfg: dict[str, Any], own: list[str], now: datetime, dry: bool, have: Callable[..., set[str]],
          write: Callable[..., int], pages: dict[str, Any], readers: dict[str, Any] | None = None,
          search: Callable[..., Any] = threads_web.read_url) -> dict[str, Any]:
    cats = categories(cfg)
    posts, stats = collect(pages, cats, cfg, now, readers)
    known = have(store, [p["permalink"] for p in posts])
    fresh = [p for p in posts if p["permalink"] not in known]
    kept, rejected = annotate(llm, fresh)
    filed = file_in_brain(store, kept, dry)
    in_brain = {p["permalink"] for p in [k for k in kept if k.get("brain")][:MAX_BRAIN]} if filed else set()
    write(store, [to_row(p, p["permalink"] in in_brain) for p in kept] + [tombstone(p) for p in rejected], dry)
    found = discover(store, llm, pages.get("threads"), cats, own, now, dry, search)
    return {"handles": sum(len(c["handles"]) for c in cats), "reads": stats["reads"], "read": stats["found"], "new": len(fresh),
            "shown": len(kept), "hidden": len(rejected), "brain": filed, "suggested": found["suggested"],
            "skipped": stats["skipped"] or None, "errors": stats["errors"][:12] or None, "by_handle": stats["by_handle"],
            "by_category": {c["id"]: sum(1 for k in kept if k["category"] == c["id"]) for c in cats}}
