"""Filling empty slots (Studio's nightly drafter, brought over 27 Sep 2026), OFF until Wan switches it on in Settings.

Semasa's rule so far is that no idea is written without Wan's click. This step keeps that rule while it is off, which is
how it ships (supabase/022 seeds settings "autofill" with enabled false). Switched on, each worker run looks at the next
`days_ahead` days, finds positions no post holds and no waiting idea is already written for, and writes an idea FOR that
position from the Regulatory and Latest publication feed (semasa_watch): an item the writer judged relevant, that Wan
did not hide, that no idea has used, and, for ws.regulab, whose domain the rota gives that day. The ideas step then
writes the draft in the same run. Everything stays a DRAFT: nothing here approves, schedules or posts, and the publisher
is still a dry run. A gap with no fitting item is left a gap and said so, never filled with something off-rota.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from . import buffer_queue, db
from .ideas import ANY_DAY_DOMAINS, MYT
from .log import get_logger

log = get_logger("semasa.autofill")

WATCH = "semasa_watch"
FRESH_DAYS = 21                 # an item older than this is not news any more
MAX_DAYS, MAX_PER_RUN = 7, 5


def config(settings: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    raw = settings.get("autofill") if isinstance(settings.get("autofill"), dict) else {}
    on = raw.get("enabled") is True
    if not on and raw.get("enabled_from"):
        # the same self-opening switch as publishing (supabase/023): autofill starts the night Studio's drafter stops
        try:
            at = datetime.fromisoformat(str(raw["enabled_from"]).replace("Z", "+00:00"))
            on = at.tzinfo is not None and (now or datetime.now(UTC)) >= at
        except ValueError:
            on = False
    days = max(1, min(MAX_DAYS, int(raw.get("days_ahead") or 3)))
    per = max(1, min(MAX_PER_RUN, int(raw.get("per_run") or 2)))
    streams = [s for s in (raw.get("streams") or ["regulab", "linkedin"]) if s in ("regulab", "linkedin")]
    return {"enabled": on, "days_ahead": days, "per_run": per, "streams": streams}


def gaps(stream: str, brand: dict[str, Any], taken: set[tuple[str, str]], days: int,
         now: datetime | None = None) -> list[tuple[str, str, list[str] | None]]:
    """(date, slot, the rota's domains that day) for every free position from tomorrow, Malaysia time. Today is left
    alone: a draft written now still needs Wan to read and approve it before its slot."""
    cfg = brand.get(stream) or {}
    slots = sorted(cfg.get("slots") or (["08:00", "13:00", "21:00"] if stream == "regulab" else ["06:00"]))
    today = ((now or datetime.now(UTC)) + MYT).date()
    out = []
    for i in range(1, days + 1):
        d = today + timedelta(days=i)
        dow = (d.weekday() + 1) % 7
        allow = None
        if stream == "regulab":
            allow = (cfg.get("schedule") or {}).get(str(dow))
            if isinstance(allow, str):
                allow = [allow]
            if allow is not None and not allow:
                continue                                       # a no-posting day
        else:
            ds = cfg.get("days")
            if ds and dow not in ds:
                continue
        out += [(d.isoformat(), s, allow) for s in slots if (d.isoformat(), s) not in taken]
    return out


def held(store: Any, stream: str, now: datetime | None = None) -> set[tuple[str, str]]:
    """Positions a post already holds (a rejected one holds nothing), read on the same clock as the gaps."""
    today = ((now or datetime.now(UTC)) + MYT).date().isoformat()
    rows = (store.table(db.POSTS).select("date,slot,status").eq("stream", stream).gte("date", today)
            .neq("status", "rejected").execute().data or [])
    return {(str(r["date"]), r["slot"]) for r in rows if r.get("date") and r.get("slot")}


def asked_for(store: Any, stream: str) -> set[tuple[str, str]]:
    """Positions a waiting idea is already being written for: never two ideas for one slot."""
    rows = (store.table(db.IDEAS).select("stream,status,brief").in_("status", ["new", "working"]).execute().data or [])
    out = set()
    for r in rows:
        pos = (r.get("brief") or {}).get("position") if isinstance(r.get("brief"), dict) else None
        if (r.get("stream") or "regulab") == stream and isinstance(pos, dict) and pos.get("date") and pos.get("slot"):
            out.add((str(pos["date"]), str(pos["slot"])))
    return out


SELECT = "id,section,source,kind,title,url,summary,why,domain,raw,published_at,created_at"

# Current newspaper issues (isu semasa) come FIRST (Wan, 9 Nov 2026: "masukkan isu semasa sebagai prioriti idea dari surat khabar
# dan relatekan dengan regulatori kalau boleh"). The scraper keeps a headline 48 hours; politics, crime, sport and the like are
# not this brand's business, so only the regulatory-adjacent categories qualify, and a headline that names a regulator or an
# instrument ranks above the rest of them.
TRENDS = "isu_semasa_trends"
NEWS_HOURS = 48
NEWS_CATEGORIES = ("kosmetik", "halal", "makanan", "farmaseutikal", "kesihatan")
NEWS_DOMAIN = {"kosmetik": "kosmetik", "halal": "halal_my", "makanan": "makanan", "farmaseutikal": "farmaseutikal",
               "kesihatan": "farmaseutikal"}
REGULATORY = (
    "npra", "kkm", "bkkm", "jakim", "jawi", "fsqd", "kpdn", "moh", "kementerian kesihatan", "akta", "peraturan", "garis panduan",
    "notifikasi", "pendaftaran", "sijil", "pensijilan", "penguatkuasaan", "tarik balik", "recall", "diharamkan", "larangan",
    "dilarang", "label", "pelabelan", "halal", "bahan terlarang", "racun berjadual", "hidrokuinon", "merkuri", "tretinoin",
    "steroid", "sibutramin", "pendedahan", "amaran", "ecosmetic", "quest3", "mesti dikawal", "poison", "regulation", "ban",
    "warning", "licence", "license")


def regulatory_link(item: dict[str, Any]) -> bool:
    """True when the headline or summary names a regulator, an instrument or an enforcement step: the stories that can honestly be
    tied to a rule. Words, not a guess about popularity."""
    text = f" {item.get('title') or ''} {item.get('summary') or ''} ".lower()
    return any(w in text for w in REGULATORY)


def story_key(title: Any) -> str:
    """One story under any link: the headline lowered, the " - Paper" tail of a Google News title cut off, letters and digits
    only. The same story reaches the feed as a Google News link and as the paper's own link (the two LinkedIn ideas for 13 Nov
    were both "Jakim investigating The Weeknd's concerts"), and the link is all the used-check compared."""
    text = str(title or "").lower().strip()
    text = re.sub(r"\s+[-|\u2013\u2014]\s+[^-|\u2013\u2014]{2,40}$", "", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def one_per_story(rows: list[dict[str, Any]], spent_stories: set[str] | None = None) -> list[dict[str, Any]]:
    """Each story once: the first of its rows wins, a row with the paper's own link is preferred to a Google News redirect (the
    writer can read the article behind it), and a story an idea already used is dropped whatever its link."""
    spent = set(spent_stories or ())
    best: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for r in rows:
        key = story_key(r.get("title"))
        if not key or key in spent:
            continue
        if key not in best:
            best[key] = r
            order.append(key)
        elif "news.google.com" in str(best[key].get("url")) and "news.google.com" not in str(r.get("url")):
            best[key] = r
    return [best[k] for k in order]


def used_stories(store: Any, days: int = 14, now: datetime | None = None) -> set[str]:
    """Story keys of the ideas made lately: a headline already written up under another link is not written again.
    Never raises."""
    since = ((now or datetime.now(UTC)) - timedelta(days=days)).isoformat()
    try:
        rows = (store.table(db.IDEAS).select("source_title").gte("created_at", since).limit(1000).execute().data or [])
    except Exception as exc:  # noqa: BLE001
        log.info("used stories not read: %s", str(exc)[:100])
        return set()
    return {k for k in (story_key(r.get("source_title")) for r in rows) if k}


def news_candidates(store: Any, now: datetime | None = None) -> list[dict[str, Any]]:
    """Newspaper headlines from the last NEWS_HOURS in a regulatory-adjacent category that no idea has used, shaped like feed
    items. Never raises: no table yet, or a failed read, is no news and the feed still fills the gaps."""
    since = ((now or datetime.now(UTC)) - timedelta(hours=NEWS_HOURS)).isoformat()
    try:
        rows = (store.table(TRENDS).select("id,title,source,url,summary,category,published_at,created_at")
                .in_("category", list(NEWS_CATEGORIES)).gte("created_at", since).order("created_at", desc=True)
                .limit(120).execute().data or [])
        if not rows:
            return []
        spent: set[str] = set()
        for chunk in db._in_filter_chunks([r["url"] for r in rows]):
            spent |= {r.get("source_url") for r in (store.table(db.IDEAS).select("source_url").in_("source_url", chunk)
                                                    .execute().data or [])}
    except Exception as exc:  # noqa: BLE001
        log.info("news candidates skipped: %s", str(exc)[:100])
        return []
    out = []
    for r in rows:
        if r["url"] in spent:
            continue
        item = {"id": r["id"], "section": "news", "source": r.get("source"), "kind": "news", "title": r.get("title"),
                "url": r["url"], "summary": r.get("summary"), "why": None, "domain": NEWS_DOMAIN.get(r.get("category")),
                "raw": {}, "published_at": r.get("published_at"), "created_at": r.get("created_at"), "trend_id": r["id"]}
        item["regulatory_link"] = regulatory_link(item)
        out.append(item)
    return out


def candidates(store: Any, now: datetime | None = None) -> list[dict[str, Any]]:
    """Feed items an idea has not used yet. News is fresh for FRESH_DAYS; the OneDrive angle bank is not news and has no
    age limit (its rows are written once, when a file is first read, and wait until they are used)."""
    since = ((now or datetime.now(UTC)) - timedelta(days=FRESH_DAYS)).isoformat()
    rows = (store.table(WATCH).select(SELECT).eq("relevant", True).eq("dismissed", False).gte("created_at", since)
            .neq("section", "folder").order("created_at", desc=True).limit(200).execute().data or [])
    bank = (store.table(WATCH).select(SELECT).eq("section", "folder").eq("relevant", True).eq("dismissed", False)
            .order("created_at", desc=True).limit(300).execute().data or [])
    rows = news_candidates(store, now) + rows + bank
    if not rows:
        return []
    urls = [r["url"] for r in rows]
    spent: set[str] = set()
    for chunk in db._in_filter_chunks(urls):
        spent |= {r.get("source_url") for r in (store.table(db.IDEAS).select("source_url").in_("source_url", chunk)
                                                .execute().data or [])}
    return one_per_story([r for r in rows if r["url"] not in spent], used_stories(store, now=now))


def rank_candidates(pool: list[dict[str, Any]], now: datetime | None = None) -> list[dict[str, Any]]:
    """Current newspaper issues first (those that name a regulator or an instrument before the rest), then the regulator and
    paper feed, newer and regulator-facing first, without inventing a viral score."""
    now = now or datetime.now(UTC)

    def key(item: dict[str, Any]) -> tuple[int, int, float]:
        title = f"{item.get('title') or ''} {item.get('summary') or ''}".lower()
        timely = int(any(word in title for word in ("recall", "regulator", "npra", "jakim", "hsa", "efsa", "update", "warning")))
        try:
            age = -datetime.fromisoformat(str(item.get("created_at")).replace("Z", "+00:00")).timestamp()
        except (TypeError, ValueError):
            age = float("inf")
        if item.get("section") == "news":
            return (0, 0 if item.get("regulatory_link") else 1, age)
        return (1, -timely, age)
    return sorted(pool, key=key)


def pick(pool: list[dict[str, Any]], stream: str, allow: list[str] | None, day: str) -> dict[str, Any] | None:
    """An urgent file for THIS date first (Studio's `urgent post/DDMMYY` override), then the first item that fits."""
    for x in pool:
        if (x.get("raw") or {}).get("urgent_for") == day:
            return x
    return next((x for x in pool if fits(x, stream, allow)), None)


def fits(item: dict[str, Any], stream: str, allow: list[str] | None) -> bool:
    if stream == "linkedin":
        return True                                            # every section reads as a chemist's post
    dom = item.get("domain")
    if not allow:
        return True
    return dom in allow or dom in ANY_DAY_DOMAINS


def run(store: Any, settings: dict[str, Any], now: datetime | None = None) -> str:
    cfg = config(settings, now)
    if not cfg["enabled"]:
        return "Autofill: off (switch it on in Settings)"
    try:
        # what Buffer already holds: a full queue pauses new ideas and every post in it is a taken slot (None = unknown, carry on)
        queue = buffer_queue.snapshot(store, settings, now) if "regulab" in cfg["streams"] else None
        if queue and queue["is_full"]:
            streams = [s for s in cfg["streams"] if s != "regulab"]
            if not streams:
                return ("Autofill: paused, the Buffer queue is full (" + ", ".join(queue["full"])
                        + f" at {queue['limit']}); ideas resume when a post goes out")
        else:
            streams = cfg["streams"]
        pool = rank_candidates(candidates(store, now), now)
        brand = settings.get("brand") or {}
        made, empty = 0, 0
        for stream in streams:
            busy = held(store, stream, now) | asked_for(store, stream)
            if stream == "regulab" and queue:
                busy |= {tuple(p) for p in queue["taken"]}
            for date, slot, allow in gaps(stream, brand, busy, cfg["days_ahead"], now):
                if made >= cfg["per_run"]:
                    break
                item = pick(pool, stream, allow, date)
                if not item:
                    empty += 1
                    continue
                key = story_key(item.get("title"))
                # the story leaves the pool whole, under every link
                pool = [x for x in pool if x is not item and not (key and story_key(x.get("title")) == key)]
                domain = None
                urgent = (item.get("raw") or {}).get("urgent_for") == date
                if stream == "regulab":
                    domain = item.get("domain") if item.get("domain") and (urgent or fits(item, stream, allow)) else None
                    if allow and domain not in allow and domain not in ANY_DAY_DOMAINS and not urgent:
                        domain = allow[0]
                news = item.get("section") == "news"
                brief = {"position": {"date": date, "slot": slot}, "auto": True, "watch_id": item["id"],
                         "hook_required": True, "story_mode": True, "source_priority": "current"}
                if news:
                    brief["relate_regulatory"] = True      # a newspaper story: the writer ties it to a rule where one is real
                    brief.pop("watch_id")                 # not a regulator-feed row: trend_id says where it came from
                    brief["news"] = True
                store.table(db.IDEAS).insert({
                    **({"trend_id": item["trend_id"]} if news else {}),
                    "source_title": str(item.get("title") or "")[:500], "source_url": item["url"],
                    "source_name": item.get("source") or None,
                    "source_summary": (str(item.get("summary") or item.get("why") or "")
                                       + (f" (Rujukan dalam dokumen: {(item.get('raw') or {}).get('cite')})"
                                          if (item.get("raw") or {}).get("cite") else ""))[:4000] or None,
                    "stream": stream, "domain": domain,
                    "angle": ("F" if item.get("section") == "publication" else "A") if stream == "linkedin" else None,
                    "make_media": "image", "status": "new", "created_by": None,
                    # no note: the writer reads a note as Wan's words, and a note also lifts the already-published
                    # guard (ideas.process_idea). What this idea is for rides in the brief, shown as a pill.
                    "note": "",
                    "brief": brief,
                }).execute()
                made += 1
        if made:
            db.log_event(store, "info", "idea", "idea.autofill",
                         f"{made} idea ditulis untuk slot kosong (auto-isi); draf menunggu kelulusan",
                         detail={"made": made, "no_fitting_item": empty})
        return f"Autofill: {made} idea(s) written for empty slots" + (f"; {empty} gap(s) had no fitting item" if empty else "")
    except Exception as exc:  # noqa: BLE001 - a missing table or setting must not stop the worker
        log.warning("autofill skipped: %s", exc)
        return f"Autofill: skipped ({str(exc)[:120]})"
