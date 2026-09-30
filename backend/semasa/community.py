"""What people are arguing about right now: Reddit and YouTube, read through Composio For You (Studio's ideas sweep, 3rd
pass, brought over 30 Sep 2026: "port all three before Friday").

Studio's rule, kept: the SOURCE never reaches a post. A row here is the wrong (or half-right) belief itself, written
neutrally; it never names the platform, a subreddit or a handle, and every count on it is one the platform actually
returned. The feed row still carries the link and "Reddit"/"YouTube" so Wan can go back to it, exactly as Studio's idea
kept `evidence`; the shared compliance rules block a draft that names either.

  Reddit   REDDIT_SEARCH_ACROSS_SUBREDDITS, `subreddit:malaysia (halal OR ...)`, top of the week, ranked by comments
           (a thread with 260 comments outranks one with 1,000 upvotes and 4). The `subreddit` argument does NOT filter
           (measured 30 Sep 2026: it returned r/nba); the restriction has to be in the query text.
  YouTube  YOUTUBE_SEARCH_YOU_TUBE (viewCount, MY, last 14 days) then YOUTUBE_GET_VIDEO_DETAILS_BATCH for the real view
           counts. Never `relevanceLanguage: "ms"` (it returns nothing). Composio's shared Google project ran out of its
           daily search quota on 30 Sep 2026: that is reported in the run and Reddit carries on.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from .log import get_logger

log = get_logger("semasa.community")

DOMAINS = ("kosmetik", "makanan", "halal_my", "farmaseutikal", "fatwa", "sains_kosmetik", "kajian_kes", "lain")

_CELL = '''
OUT = {"posts": [], "videos": [], "reddit_error": "", "youtube_error": ""}
q = "subreddit:" + P["subreddit"] + " (" + " OR ".join(P["terms"]) + ")"
res, err = call("REDDIT_SEARCH_ACROSS_SUBREDDITS",
                {"search_query": q, "sort": "top", "time_filter": P["window"], "limit": P["limit"], "result_type": ["link"]})
if err:
    OUT["reddit_error"] = str(err)[:200]
for p in ((res.get("data") or {}).get("posts") or []):
    OUT["posts"].append({"id": p.get("id"), "title": str(p.get("title") or "")[:300], "score": p.get("score"),
                         "num_comments": p.get("num_comments"), "permalink": p.get("permalink"),
                         "created": p.get("created_datetime"), "subreddit": p.get("subreddit"),
                         "text": str(p.get("selftext") or "")[:500]})
if P["youtube"]["enabled"]:
    import datetime as _dt
    after = (_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=P["youtube"]["days"])).strftime("%Y-%m-%dT%H:%M:%SZ")
    ids = []
    for yq in P["youtube"]["queries"]:
        if left() < 40:
            break
        r, e = call("YOUTUBE_SEARCH_YOU_TUBE", {"q": yq, "type": "video", "order": "viewCount",
                                               "maxResults": P["youtube"]["max_results"], "regionCode": "MY",
                                               "publishedAfter": after})
        if e:
            OUT["youtube_error"] = ("quota" if ("429" in str(e) or "uota" in str(e)) else str(e)[:200])
            break
        d = r.get("data") or {}
        for it in (d.get("items") or (d.get("response_data") or {}).get("items") or []):
            vid = (it.get("id") or {}).get("videoId") if isinstance(it.get("id"), dict) else it.get("id")
            if vid and vid not in ids:
                ids.append(vid)
    if ids:
        r, e = call("YOUTUBE_GET_VIDEO_DETAILS_BATCH", {"id": ids[:40], "parts": ["snippet", "statistics"]})
        if e:
            OUT["youtube_error"] = str(e)[:200]
        for it in ((r.get("data") or {}).get("items") or []):
            sn, st = it.get("snippet") or {}, it.get("statistics") or {}
            OUT["videos"].append({"id": it.get("id"), "title": str(sn.get("title") or "")[:300],
                                  "channel": sn.get("channelTitle"), "published": sn.get("publishedAt"),
                                  "views": st.get("viewCount"), "comments": st.get("commentCount"),
                                  "text": str(sn.get("description") or "")[:400]})
'''

SYSTEM = """You read public online arguments (a Reddit thread, a YouTube video) for ws.regulab, a Malaysian regulatory
consultancy (cosmetics, halal, food, pharmaceuticals; clients are Malaysian SMEs). Each item is something people are
loudly discussing. For each one decide:
- "relevant": true only when the argument turns on cosmetics, skincare, sunscreen, supplements, halal, food, drugs,
  labels, claims or a regulator's rule, so that a chemist or regulatory adviser could correct or clarify it. False for
  memes, politics, sport, travel, celebrity, jokes, and threads where the topic word appears by chance.
- "title": the wrong or half-right BELIEF itself, in Malaysian Malay (English product words are fine), at most 90
  characters. Never the platform, a subreddit, a channel or user name, "netizen", "viral di" or a link. Never Bahasa
  Indonesia.
- "summary": two sentences in Malaysian Malay saying what people are arguing, using ONLY what is given. No fact, number,
  product or company that is not in the item.
- "why": one sentence in Malaysian Malay: what a Malaysian business or consumer should know because of it.
- "domain": one of kosmetik, makanan, halal_my, farmaseutikal, fatwa, sains_kosmetik, kajian_kes, lain.
Answer with ONE JSON object:
{"items": [{"i": 0, "relevant": true, "domain": "...", "title": "...", "summary": "...", "why": "..."}]}"""


def _int(v: Any) -> int:
    try:
        return int(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return 0


def _when(v: Any) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


MAX_TERMS = 20        # measured: 19 terms match as OR; 27 return the subreddit's general top (3 of 25 mention any term)


def fetch(client: Any, cfg: dict[str, Any]) -> dict[str, Any]:
    yt = cfg.get("youtube") or {}
    return client.cell(_CELL, {
        "subreddit": str(cfg.get("subreddit") or "malaysia"), "terms": list(cfg.get("terms") or ["halal"])[:MAX_TERMS],
        "window": cfg.get("window") if cfg.get("window") in ("day", "week", "month") else "week",
        "limit": max(1, min(25, int(cfg.get("limit") or 15))),
        "youtube": {"enabled": yt.get("enabled") is not False, "queries": list(yt.get("queries") or [])[:4],
                    "days": max(1, min(14, int(yt.get("days") or 14))),
                    "max_results": max(1, min(10, int(yt.get("max_results") or 8)))}},
        thought="Semasa: what Malaysians are arguing about this week", budget=120)


def candidates(raw: dict[str, Any], now: datetime | None = None, days: int = 14) -> list[dict[str, Any]]:
    """Reddit threads and videos as rows, most-discussed first. A row with no link or no title is dropped."""
    now = now or datetime.now(UTC)
    out: list[dict[str, Any]] = []
    for p in raw.get("posts") or []:
        url, title, when = p.get("permalink"), str(p.get("title") or "").strip(), _when(p.get("created"))
        if not url or not title or (when and now - when > timedelta(days=days + 1)):
            continue
        n = _int(p.get("num_comments"))
        out.append({"platform": "reddit", "source": "Reddit", "kind": "Hujah", "url": str(url), "title": title,
                    "text": str(p.get("text") or ""), "published_at": when, "weight": n,
                    "metrics": f"{n} komen" if n else None,
                    "raw": {"platform": "reddit", "original_title": title, "comments": n, "score": _int(p.get("score"))}})
    for v in raw.get("videos") or []:
        vid, title, when = v.get("id"), str(v.get("title") or "").strip(), _when(v.get("published"))
        if not vid or not title or (when and now - when > timedelta(days=days + 1)):
            continue
        views = _int(v.get("views"))
        out.append({"platform": "youtube", "source": "YouTube", "kind": "Hujah",
                    "url": f"https://www.youtube.com/watch?v={vid}", "title": title, "text": str(v.get("text") or ""),
                    "published_at": when, "weight": views // 200,      # a video's views are not a thread's comments
                    "metrics": f"{views:,} tontonan" if views else None,
                    "raw": {"platform": "youtube", "original_title": title, "views": views,
                            "channel_seen": bool(v.get("channel"))}})
    out.sort(key=lambda r: r["weight"], reverse=True)
    return out


def annotate(llm: Any, rows: list[dict[str, Any]],
             batch: int = 6) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(kept, rejected). Kept: the rows the writer answered and judged relevant, with a neutral title. Rejected: rows it
    answered as not relevant, which the caller remembers as hidden markers so they are not judged again tomorrow. A row
    the writer never answered is in neither (it is tried again next run). Unlike a regulator's notice, an argument with
    no neutral rewrite is useless (its own title names the thread), so it is never shown unread."""
    if not rows or not llm or not getattr(llm, "configured", False):
        return [], []
    import json
    kept: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    misses = 0
    for start in range(0, len(rows), batch):
        if misses >= 2:
            log.warning("the writer stopped answering; %d argument(s) left unread", len(rows) - start)
            break
        chunk = rows[start:start + batch]
        user = "Items:\n" + "\n".join(json.dumps({"i": k, "where": r["source"], "title": r["title"],
                                                   "text": r["text"][:400], "metrics": r["metrics"]}, ensure_ascii=False)
                                        for k, r in enumerate(chunk))
        out = llm.chat_json(SYSTEM, user, max_tokens=300 * len(chunk) + 120)
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
            title, summary = str(ans.get("title") or "").strip(), str(ans.get("summary") or "").strip()
            if ans.get("relevant") not in (True, "true", "yes"):
                rejected.append(chunk[i])
                continue
            if not title or not summary:
                continue
            r = chunk[i]
            dom = str(ans.get("domain") or "").strip().lower()
            kept.append({**r, "title": title[:120], "summary": summary[:600],
                         "why": str(ans.get("why") or "").strip()[:300] or None,
                         "domain": dom if dom in DOMAINS else "lain"})
    return kept, rejected


def tombstone(r: dict[str, Any]) -> dict[str, Any]:
    """A hidden marker for an argument the writer judged not relevant: the link and the platform's own title, nothing
    the page shows, so the next sweep knows it has seen it."""
    when = r.get("published_at")
    return {"section": r["platform"], "source": r["source"], "kind": r["kind"], "country": "MY", "title": r["title"][:200],
            "url": r["url"], "summary": None, "why": None, "domain": None, "relevant": False, "lang": "ms",
            "summary_source": "llm", "raw": {}, "published_at": when.isoformat() if isinstance(when, (datetime, date)) else None}


def to_row(r: dict[str, Any]) -> dict[str, Any]:
    when = r.get("published_at")
    raw = {**r["raw"], **({"metrics": r["metrics"]} if r.get("metrics") else {})}
    # Reddit and YouTube are two sections, so the page can show them on two tabs (Wan, 30 Sep 2026)
    return {"section": r["platform"], "source": r["source"], "kind": r["kind"], "country": "MY", "title": r["title"],
            "url": r["url"], "summary": r["summary"], "why": r.get("why"), "domain": r.get("domain"), "relevant": True,
            "lang": "ms", "summary_source": "llm", "raw": raw,
            "published_at": when.isoformat() if isinstance(when, (datetime, date)) else None}
