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
import time
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
WATCH = "semasa_watch"             # intake.WATCH (intake imports this module, so the name is repeated, not imported)
PLATFORMS = ("threads", "facebook", "instagram")
NAMES = {"threads": "Threads", "facebook": "Facebook", "instagram": "Instagram"}
# One sweep's budget is counted in PAGE LOADS, not profiles: an Instagram profile is its grid and six post pages, a Threads or
# Facebook profile is one page. Twenty Instagram profiles used to count as twenty and were about 140 loads, on top of the other
# parts of the Sources run and inside its 30 minutes. The time budget is the second guard: the part stops cleanly when it has
# run this long and the handles not reached go first next sweep (the rotation below).
LOAD_COST = {"threads": 1, "facebook": 1, "instagram": 7}
MAX_LOADS = 60
TIME_BUDGET_S = 12 * 60
MAX_BRAIN = 10                 # posts filed in the AI brain in one sweep
MAX_SUGGESTIONS = 12           # kept per category
DISCOVER_EVERY = timedelta(hours=20)
HANDLE = re.compile(r"[\w.\-]{1,60}")

DEFAULTS: dict[str, Any] = {
    # discover_request: the time Wan last pressed "Search again" on the page; a search runs when it is newer than the last one
    "enabled": True, "hours": 14 * 24, "per_handle": 5, "discover_request": None,
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
            # one owner can use a different username on each platform (Wan, 15 Nov 2026): `handle` is the owner's main name and
            # `names` holds only the platforms where the account is called something else
            names = {p: clean_handle(v) for p, v in ((h.get("names") if isinstance(h, dict) else None) or {}).items()
                     if p in plats and clean_handle(v) and clean_handle(v).lower() != name.lower()}
            if name and plats and name.lower() not in seen:
                seen.add(name.lower())
                handles.append({"handle": name, "platforms": plats, **({"names": names} if names else {})})
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


def account_of(h: dict[str, Any], platform: str) -> str:
    """The username this owner has on that platform."""
    return (h.get("names") or {}).get(platform) or h["handle"]


def _mine(post: dict[str, Any], handle: str, platform: str) -> bool:
    """A profile page also shows what the account reposted or quoted: only its own posts are the expert's words."""
    user = str(post.get("username") or "").lower()
    if platform == "facebook":
        return True                                   # a Facebook post row carries no author; the page read is the author's
    return not user or user == handle.lower()


NOT_FOUND = "account not found or private"
POST_CAP = 4000                # characters of one post kept (a Threads post is 500, a text attachment is far longer)
CHAIN_WINDOW = timedelta(minutes=30)   # posts of one author this close to a first part are candidates for its chain


def _same_user(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return str(a.get("username") or "").lower() == str(b.get("username") or "").lower()


def merge_chains(page: Any, posts: list[dict[str, Any]], read: Callable[..., Any] = threads_web.read_url) -> list[dict[str, Any]]:
    """A Threads chain (an author's post carried on in their own next posts) is one permalink per part on the profile, and read
    part by part each part looks like a post of its own with half the argument gone. The profile lists a chain in its own order
    (its timestamps are not reliable: parts of one chain can carry the same second, or the later part an earlier one), so the
    first part listed is the candidate root and the author's other posts within half an hour of it are candidates for the
    rest. The root's own page decides, because there the author's continuation stands right under it before anyone else's
    reply. Confirmed parts become ONE post: the root's address and numbers, every part's words in order. A part the page does
    not confirm stays a post of its own, and a page that cannot be read leaves the posts as read."""
    times = {p["permalink"]: _when(p.get("timestamp")) or NOW_MIN for p in posts}
    left = list(posts)
    out: list[dict[str, Any]] = []
    while left:
        root = left.pop(0)
        near = [p for p in left if _same_user(p, root) and abs(times[p["permalink"]] - times[root["permalink"]]) <= CHAIN_WINDOW]
        if not near:
            out.append(root)
            continue
        want = {p["permalink"] for p in near}
        got, err = read(page, root["permalink"], 0, POST_CAP, True)
        rows = got if not err else []
        at = next((i for i, r in enumerate(rows) if r["permalink"] == root["permalink"]), None)
        parts = [rows[at]] if at is not None else [root]
        for r in rows[at + 1:] if at is not None else []:
            if not _same_user(r, root) or r["permalink"] not in want:
                break                                                   # the first other voice ends the author's own chain
            parts.append(r)
        if len(parts) < 2:
            if err:
                log.info("chain not confirmed for %s: %s", root["permalink"], err)
            out.append(root)
            continue
        joined = parts[0]["text"]
        for i, part in enumerate(parts[1:], 2):
            joined += f"\n\n— {i}/{len(parts)} —\n\n{part['text']}"
        used = {p["permalink"] for p in parts}
        left = [p for p in left if p["permalink"] not in used]
        out.append({**root, "text": joined, "parts": len(parts), "chain_urls": [p["permalink"] for p in parts]})
    return out


NOW_MIN = datetime.min.replace(tzinfo=UTC)


def read_threads(page: Any, handle: str, now: datetime) -> tuple[list[dict[str, Any]], str]:
    got, err = threads_web.read_url(page, f"{threads_web.BASE}/@{handle}", cap=POST_CAP, keep_lines=True)
    if err == "Threads asked for a login":
        # Threads sends a visitor to its login page for a profile that does not exist or is private (checked live, 15 Nov 2026),
        # while a real public profile opens. Reported as a wall, one mistyped name stopped every other Threads read of the sweep.
        return [], f"{NOT_FOUND}: Threads shows its login page for @{handle}. Check the username"
    if err:
        return got, err
    own = [p for p in got if _same_user(p, {"username": handle})]
    rest = [p for p in got if not _same_user(p, {"username": handle})]
    return merge_chains(page, own) + rest, ""


def read_instagram(page: Any, handle: str, now: datetime) -> tuple[list[dict[str, Any]], str]:
    return social_web.read_instagram_account(page, handle, now, POST_CAP)


def read_facebook(page: Any, handle: str, now: datetime) -> tuple[list[dict[str, Any]], str]:
    return social_web.read_facebook_account(page, handle, now, POST_CAP)             # every "See more" opened, paragraphs kept


READERS: dict[str, Callable[[Any, str, datetime], tuple[list[dict[str, Any]], str]]] = {
    "threads": read_threads, "instagram": read_instagram, "facebook": read_facebook}


def _age(now: datetime, when: datetime) -> str:
    days = (now - when).days
    return f"{days} days" if days >= 2 else f"{int((now - when).total_seconds() // 3600)} hours"


def collect(pages: dict[str, Any], cats: list[dict[str, Any]], cfg: dict[str, Any], now: datetime,
            readers: dict[str, Any] | None = None, clock: Callable[[], float] = time.monotonic,
            budget_s: float = TIME_BUDGET_S) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Every registered handle on every platform ticked for it. (posts, stats). `pages` maps a platform to the browser page
    that reads it (None when that platform cannot be read this run, e.g. no saved login). stats["notes"] says, for a handle
    that gave nothing, why: no post on the profile, or the newest one older than the window."""
    readers = readers or READERS
    started = clock()
    hours = max(24, min(60 * 24, int(cfg.get("hours") or 14 * 24)))
    per = max(1, min(15, int(cfg.get("per_handle") or 5)))
    posts: list[dict[str, Any]] = []
    stats: dict[str, Any] = {"reads": 0, "loads": 0, "found": 0, "errors": [], "skipped": 0, "by_handle": {}, "notes": {},
                             "stopped": ""}
    seen: set[str] = set()
    walled: set[str] = set()
    todo = [(cat, h, platform) for cat in cats for h in cat["handles"] for platform in h["platforms"]]
    opened: set[tuple[str, str]] = set()                 # one account on one platform is read once, whoever lists it
    unique = []
    for t in todo:
        key = (t[2], account_of(t[1], t[2]).lower())
        if key not in opened:
            opened.add(key)
            unique.append(t)
    todo = unique
    if sum(LOAD_COST[t[2]] for t in todo) > MAX_LOADS:
        # more pages than one sweep opens: start somewhere else each sweep, so the same handles are not the ones left out
        at = int(now.timestamp() // (6 * 3600)) % len(todo)
        todo = todo[at:] + todo[:at]
    for cat, h, platform in todo:
        name = account_of(h, platform)
        label = f"@{name} ({NAMES[platform]})"
        page = pages.get(platform)
        if page is None or platform in walled:
            stats["errors"].append(f"{label}: {pages.get(platform + '_error') or 'not read: the platform asked for a login'}")
            continue
        if stats["loads"] + LOAD_COST[platform] > MAX_LOADS or clock() - started > budget_s:
            stats["stopped"] = stats["stopped"] or ("time" if clock() - started > budget_s else "pages")
            stats["skipped"] += 1
            continue
        stats["reads"] += 1
        stats["loads"] += LOAD_COST[platform]
        got, err = readers[platform](page, name, now)
        if err:
            stats["errors"].append(f"{label}: {err}")
            if "asked for a login" in err:
                walled.add(platform)                   # every other page of that platform will say the same
            continue
        mine = []
        newest: datetime | None = None                       # of the account's own posts, whatever their age
        for p in got:
            when = _when(p.get("timestamp"))
            link = str(p.get("permalink") or "")
            if when and _mine(p, name, platform) and (newest is None or when > newest):
                newest = when
            if not link or link in seen or not when or now - when > timedelta(hours=hours) or not _mine(p, name, platform):
                continue
            mine.append({**p, "when": when})
        if not mine:
            stats["notes"][label] = (f"newest post is {_age(now, newest)} old, outside the {hours // 24}-day window" if newest
                                     else "the profile showed no post of its own")
        stats["loads"] += sum(1 for p in mine if p.get("parts"))          # each confirmed chain cost one more page
        mine.sort(key=lambda p: p["when"], reverse=True)
        for p in mine[:per]:
            seen.add(p["permalink"])
            posts.append({**p, "category": cat["id"], "category_name": cat["name"], "niche": cat["niche"],
                          "handle": name, "owner": h["handle"], "platform": platform, "brain": cat["brain"]})
        stats["by_handle"][label] = len(mine[:per])
        stats["found"] += len(mine[:per])
    return posts, stats


def metrics_of(p: dict[str, Any]) -> str | None:
    return threads_web.metrics_text(p) if p["platform"] == "threads" else social_web.metrics_text(p)


def annotate(llm: Any, posts: list[dict[str, Any]], batch: int = 5) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(kept, rejected): the posts the writer answered. A post it never answered is in neither, and is tried again next sweep.
    NOTHING IS HIDDEN (Wan, 27 Nov 2026: "do not hide, use all idea from expert"): a post the writer judged off the niche is kept
    like the rest, with the first line of the post as its title and the post's own words as its summary when the writer gave
    none, and `off_niche` set so it is never filed in the AI brain. `rejected` stays in the signature and is always empty."""
    if not posts or not llm or not getattr(llm, "configured", False):
        return [], []
    kept: list[dict[str, Any]] = []
    misses = 0
    for start in range(0, len(posts), batch):
        if misses >= 2:
            log.warning("the writer stopped answering; %d expert post(s) left unread", len(posts) - start)
            break
        chunk = posts[start:start + batch]
        user = "Items:\n" + "\n".join(
            json.dumps({"i": k, "niche": p["niche"] or p["category_name"], "post": p["text"][:POST_CAP * 2]}, ensure_ascii=False)
            for k, p in enumerate(chunk))
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
            on_niche = ans.get("relevant") in (True, "true", "yes")
            title, summary = str(ans.get("title") or "").strip(), str(ans.get("summary") or "").strip()
            text = str(chunk[i].get("text") or "").strip()
            if not on_niche:
                title = title or (text.splitlines()[0] if text else "")
                summary = summary or " ".join(text.split())
            if title and summary:
                kept.append({**chunk[i], "title": title[:200], "summary": summary[:900],
                             "why": str(ans.get("why") or "").strip()[:400], **({} if on_niche else {"off_niche": True})})
    return kept, []


def to_row(p: dict[str, Any], brain: bool = False) -> dict[str, Any]:
    seen = metrics_of(p)
    raw = {"category": p["category"], "category_name": p["category_name"], "handle": p["handle"],
           "owner": p.get("owner") or p["handle"], "platform": p["platform"], "original": p["text"][:8000],
           **({"metrics": seen} if seen else {}),
           **({"parts": p["parts"], "chain_urls": p["chain_urls"]} if p.get("parts") else {}),
           **({"brain": True} if brain else {}), **({"off_niche": True} if p.get("off_niche") else {})}
    return {"section": SECTION, "source": f"{NAMES[p['platform']]} · @{p['handle']}", "kind": p["category_name"], "country": None,
            "title": p["title"], "url": p["permalink"], "summary": p["summary"], "why": p.get("why") or None, "domain": None,
            "relevant": True, "lang": "ms", "summary_source": "llm", "raw": raw, "published_at": p["when"].isoformat(),
            "dismissed": bool(p.get("was_hidden"))}          # a chain Wan had hidden stays hidden when it is read again


def tombstone(p: dict[str, Any]) -> dict[str, Any]:
    """A hidden marker for a post off the niche: its link only, so the next sweep knows it has been read."""
    return {"section": SECTION, "source": f"{NAMES[p['platform']]} · @{p['handle']}", "kind": p["category_name"], "country": None,
            "title": p["text"].splitlines()[0][:200], "url": p["permalink"], "summary": None, "why": None, "domain": None,
            "relevant": False, "lang": "ms", "summary_source": "llm", "published_at": p["when"].isoformat(), "dismissed": False,
            "raw": {"category": p["category"], "handle": p["handle"], "owner": p.get("owner") or p["handle"]}}


def brain_url(p: dict[str, Any]) -> str:
    """A chain that replaces rows already read (part by part, or a shorter chain) is filed under an address of its own, which
    carries its length, so the brain does not skip it as already there."""
    return p["permalink"] + (f"#thread-{p['parts']}" if p.get("healed") else "")


def brain_row(p: dict[str, Any]) -> dict[str, Any]:
    """The AI brain's inbox row for one post: the expert's own words first, then the summary, filed as a reference."""
    chain = f" (a chain of {p['parts']} posts)" if p.get("parts") else ""
    who = f"@{p['handle']} on {NAMES[p['platform']]} ({p['category_name']})"
    body = (f"Expert: {who}\n\nOriginal post{chain}:\n{p['text'][:8000]}\n\n"
            f"Summary: {p['summary']}" + (f"\nTakeaway: {p['why']}" if p.get("why") else ""))
    return {"source_kind": "text", "title": p["title"][:200], "url": brain_url(p), "body": body, "hint": "reference",
            "note": f"Expert content ({p['category_name']}): a reference only, the view of one expert, not a verified fact."}


def file_in_brain(store: Any, posts: list[dict[str, Any]], dry: bool) -> int:
    """File each post in the brain's inbox, skipping a link already there. Returns how many went in. Never raises."""
    todo = [p for p in posts if p.get("brain")][:MAX_BRAIN]
    if not todo or dry:
        return len(todo)
    try:
        urls = [brain_url(p) for p in todo]
        known = {r["url"] for r in (store.table(db.BRAIN_INBOX).select("url").in_("url", urls).execute().data or [])}
        rows = [brain_row(p) for p in todo if brain_url(p) not in known]
        if rows:
            store.table(db.BRAIN_INBOX).insert(rows).execute()
        return len(rows)
    except Exception as exc:  # noqa: BLE001 - the feed rows are already written; the brain is a copy
        log.warning("expert posts not filed in the AI brain: %s", str(exc)[:160])
        return 0


# --- accounts worth following -------------------------------------------------------------------------------------------

def _known(cat: dict[str, Any]) -> set[str]:
    """Every name already followed or dismissed in a category: an owner's main name and each platform's own username."""
    names = {h["handle"].lower() for h in cat["handles"]}
    for h in cat["handles"]:
        names |= {v.lower() for v in (h.get("names") or {}).values()}
    return names | set(cat["dismissed"])


def candidates(found: list[dict[str, Any]], cat: dict[str, Any], own: list[str], limit: int = 8) -> list[dict[str, Any]]:
    """Authors seen in the keyword search, loudest first, without the handles already registered, dismissed or Wan's own."""
    skip = _known(cat) | {str(o).lower().lstrip("@") for o in own}
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
    skip = _known(cat)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for s in [*new, *(old or [])]:
        h = clean_handle(s.get("handle")).lower() if isinstance(s, dict) else ""
        if h and h not in skip and h not in seen:
            seen.add(h)
            out.append(s)
    return out[:MAX_SUGGESTIONS]


def _due(last: datetime | None, now: datetime, requested: Any = None) -> bool:
    """A search is due once a day, or when Wan asked for one (the page's "Search again") after the last one ran."""
    asked = _when(requested)
    return not last or now - last >= DISCOVER_EVERY or bool(asked and asked > last)


def discovery_due(store: Any, now: datetime, requested: Any = None) -> bool:
    rows = store.table(db.SETTINGS).select("value").eq("key", SUGGEST_KEY).execute().data or []
    return _due(_when(((rows[0].get("value") if rows else None) or {}).get("at")), now, requested)


def discover(store: Any, llm: Any, page: Any, cats: list[dict[str, Any]], own: list[str], now: datetime, dry: bool,
             read: Callable[..., Any] = threads_web.read_url, requested: Any = None) -> dict[str, Any]:
    """Once a day, or when asked: search Threads for each category's keywords and keep the authors the writer judges worth
    following. The answer also says what the search saw (`seen`: authors found, and how many were already followed), so an
    empty list on the page can say why it is empty."""
    rows = store.table(db.SETTINGS).select("value").eq("key", SUGGEST_KEY).execute().data or []
    value = dict((rows[0].get("value") if rows else None) or {})
    last = _when(value.get("at"))
    due = page is not None and _due(last, now, requested)
    lists = dict(value.get("lists") or {})
    seen = dict(value.get("seen") or {})
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
            cands = candidates(found, cat, own)
            fresh = judge(llm, cands, cat, now)
            added += len(fresh)
            authors = {str(p.get("username") or "").lower() for p in found if p.get("username")}
            seen[cat["id"]] = {"posts": len(found), "authors": len(authors), "known": len(authors & _known(cat)),
                               "judged": len(cands), "worth": len(fresh)}
        lists[cat["id"]] = merge_suggestions(lists.get(cat["id"]) or [], fresh, cat)     # also prunes added/dismissed names
    out = {"at": now.isoformat() if due else value.get("at"), "lists": lists, **({"seen": seen} if seen else {})}
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


BRAIN_NOTE = "Expert content ("          # how brain_row's note starts: the mark of a reference this sweep filed itself


def forget_fragments(store: Any, urls: list[str]) -> int:
    """Take the sweep's own old references to these addresses out of the AI brain: the inbox rows it filed (told by their note)
    and the entries read from them, EXCEPT an entry Wan edited or pinned, which is his now and stays. Returns the entries
    removed. Never raises: the brain is a copy, the feed is already right."""
    try:
        rows = store.table(db.BRAIN_INBOX).select("id,url,note").in_("url", urls).execute().data or []
        ids = [r["id"] for r in rows if str(r.get("note") or "").startswith(BRAIN_NOTE)]
        if not ids:
            return 0
        gone = (store.table(db.BRAIN_ENTRIES).delete().in_("inbox_id", ids).eq("edited", False).eq("pinned", False)
                .execute().data or [])
        store.table(db.BRAIN_INBOX).delete().in_("id", ids).execute()
        return len(gone)
    except Exception as exc:  # noqa: BLE001
        log.warning("old chain references not removed from the AI brain: %s", str(exc)[:160])
        return 0


def heal_chains(store: Any, posts: list[dict[str, Any]], dry: bool) -> list[dict[str, Any]]:
    """A chain read now can already be in the feed in an older, shorter shape: one row a part (read before chains were joined: a
    4-part guide shown as four posts, the later parts judged off the niche because they lost their opening), a single post that
    has since been carried on, or a chain that has grown a part. Such a chain replaces what is stored: those expert rows are
    deleted so it is read whole this sweep, it is marked `healed`, a row Wan had hidden stays hidden, and the sweep's own old
    references to the pieces leave the AI brain (forget_fragments). Returns the posts with the mark; a dry run changes nothing
    and only says what would be."""
    chains = [p for p in posts if p.get("parts")]
    if not chains:
        return posts
    urls = sorted({u for p in chains for u in p["chain_urls"]})
    try:
        rows = store.table(WATCH).select("url,raw,dismissed").eq("section", SECTION).in_("url", urls).execute().data or []
    except Exception as exc:  # noqa: BLE001 - not healing is the old behaviour, not a failed sweep
        log.warning("chains not checked against the feed: %s", str(exc)[:160])
        return posts
    stored = {r["url"]: r for r in rows}
    stale: dict[str, list[str]] = {}
    hidden: set[str] = set()
    for p in chains:
        old = [u for u in p["chain_urls"] if u in stored]
        had = int(((stored.get(p["permalink"]) or {}).get("raw") or {}).get("parts") or 0)
        if old and had < p["parts"]:
            stale[p["permalink"]] = old
            if (stored.get(p["permalink"]) or {}).get("dismissed"):
                hidden.add(p["permalink"])
    if stale and not dry:
        try:
            gone = sorted({u for old in stale.values() for u in old})
            store.table(WATCH).delete().eq("section", SECTION).in_("url", gone).execute()
        except Exception as exc:  # noqa: BLE001
            log.warning("old chain rows not removed: %s", str(exc)[:160])
            return posts
        by = {p["permalink"]: p for p in chains}
        pieces = sorted({u for root, old in stale.items() for u in old}
                        | {f"{root}#thread-{k}" for root in stale for k in range(2, by[root]["parts"])})
        forget_fragments(store, pieces)
    return [{**p, "healed": True, **({"was_hidden": True} if p["permalink"] in hidden else {})} if p["permalink"] in stale else p
            for p in posts]


def foreign_rows(store: Any, urls: list[str]) -> dict[str, str]:
    """{address: its section} for the known addresses a section OTHER than the experts' wrote and Wan has not hidden."""
    out: dict[str, str] = {}
    for chunk in db._in_filter_chunks(urls):
        rows = store.table(WATCH).select("url,section,dismissed").in_("url", chunk).execute().data or []
        out.update({r["url"]: r.get("section") or "" for r in rows if r.get("section") != SECTION and not r.get("dismissed")})
    return out


def adopt(store: Any, rows: list[dict[str, Any]], dry: bool) -> int:
    """Rewrite the feed rows another section wrote so they belong to the expert (their address stays the key)."""
    if dry:
        return len(rows)
    for r in rows:
        store.table(WATCH).update({k: v for k, v in r.items() if k != "url"}).eq("url", r["url"]).execute()
    return len(rows)


def sweep(store: Any, llm: Any, cfg: dict[str, Any], own: list[str], now: datetime, dry: bool, have: Callable[..., set[str]],
          write: Callable[..., int], pages: dict[str, Any], readers: dict[str, Any] | None = None,
          search: Callable[..., Any] = threads_web.read_url) -> dict[str, Any]:
    cats = categories(cfg)
    posts, stats = collect(pages, cats, cfg, now, readers)
    posts = heal_chains(store, posts, dry)
    known = have(store, [p["permalink"] for p in posts])
    # A post the COMMUNITY sweep already wrote under its own section is not "known" to the experts: the address is unique across
    # the feed, so whoever wrote it first owned it, and an expert's account that is also a watched Instagram account never showed
    # under its category (26 Nov 2026: "why cosmetic science expert still not scrape": @labmuffinbeautyscience read 2 posts, 0
    # new, 0 shown). Such a row is adopted: its section, summary and category become the expert's. A row Wan hid stays hidden.
    foreign = foreign_rows(store, sorted(known))
    known -= set(foreign)
    fresh = [p for p in posts if p["permalink"] not in known or (dry and p.get("healed"))]
    kept, rejected = annotate(llm, fresh)
    # an off-niche post is shown but never filed in the AI brain as a reference (a personal post is no reference)
    brainable = [k for k in kept if not k.get("off_niche")]
    filed = file_in_brain(store, brainable, dry)
    in_brain = {p["permalink"] for p in [k for k in brainable if k.get("brain")][:MAX_BRAIN]} if filed else set()
    rows = [to_row(p, p["permalink"] in in_brain) for p in kept] + [tombstone(p) for p in rejected]
    write(store, [r for r in rows if r["url"] not in foreign], dry)
    adopt(store, [r for r in rows if r["url"] in foreign], dry)
    found = discover(store, llm, pages.get("threads"), cats, own, now, dry, search, cfg.get("discover_request"))
    return {"handles": sum(len(c["handles"]) for c in cats), "reads": stats["reads"], "read": stats["found"], "new": len(fresh),
            "shown": len(kept), "hidden": len(rejected), "brain": filed, "suggested": found["suggested"],
            "chains": sum(1 for p in posts if p.get("parts")), "healed": sum(1 for p in posts if p.get("healed")) or None,
            "skipped": stats["skipped"] or None, "stopped": stats["stopped"] or None, "loads": stats["loads"],
            "errors": stats["errors"][:12] or None, "by_handle": stats["by_handle"], "notes": stats["notes"] or None,
            "by_category": {c["id"]: sum(1 for k in kept if k["category"] == c["id"]) for c in cats}}
