"""The daily comic series (Wan, 17 Nov 2026: "can start create comic series storyboard and after approve create motion - this
series will comeout everyday which contain about isu semasa>halal>regulatory>fatwa").

One episode a day, ws.regulab only, and NOTHING is paid for before Wan approves the storyboard:

  1. PLAN (`plan_today`, called at the start of every Motion run, OFF until `settings.comic_series.enabled`): look for the day's
     item in the lanes in Wan's order (isu semasa, halal, regulatori, fatwa), take the first fitting one, and queue ONE Motion
     film for it (`options.template = "comic"`, status pending). A day with no fitting item in any lane makes no episode and
     says so (the log row and the page). A re-run the same Malaysian day makes nothing new.
  2. STORYBOARD (`write_storyboard`, run by Motion's template path): ONE text call writes the four-panel script (the same writer
     and checks every comic has) and the film goes to 'review'. This is the existing Motion storyboard gate
     (supabase/071, motion_review.py): the page's Motion storyboard review and the Telegram message are the approval. Nothing
     is drawn, voiced or rendered until Wan approves.
  3. AFTER THE APPROVAL (comic_film.py): the comic is drawn (comic_job, once), cut into its four panels and made into a film
     (a camera move over each panel, the bubbles appearing in reading order, the title card, the outro), and a DRAFT ws.regulab
     post is made with the film on the next free slot (`queue_post`). Nothing is approved, scheduled or posted here.

HALAL AND FATWA ARE SENSITIVE. A character never issues a ruling and the writer never invents one. A ruling appears only as a
reported position: the row must give the issuing body AND its date (`ruling_source`), the bubble that reports it names that
body, and the source line printed under the comic is built here from the row, never by the writer. A row that talks about a
ruling and does not give both is not used. No Quran verse or hadith is ever typed in a bubble.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from . import autofill, caption_fit, comic, comic_library, comic_writer, compliance, db, ideas, motion_captions
from .log import get_logger

log = get_logger("semasa.comic_daily")

MOTIONS = "semasa_motions"
KEY = "comic_series"                    # Wan's settings (the page writes it): enabled, paused, lanes, at, series, words_mode
STATE_KEY = "comic_series_log"          # the worker's own record (the page only reads it): last, log
RULES: dict[str, Any] = comic_library.RULES["daily"]
LANE_IDS: tuple[str, ...] = tuple(d["id"] for d in RULES["lane_defs"])
LOG_KEEP = 30
MYT = timedelta(hours=8)
TEMPLATE = "comic"

# What each lane may read. The social sections (Threads, Facebook, Instagram, Reddit, YouTube, experts) are never a source: an
# idea's source never reaches the post, and a brand's own contest post is not a ruling.
WATCH_SECTIONS = {
    "halal": ("regulatory", "myra", "folder", "publication"),
    "regulatori": ("regulatory", "myra"),
    "fatwa": ("folder", "regulatory", "publication"),
}
SECTION_RANK = {"regulatory": 0, "myra": 1, "folder": 2, "publication": 3}
NEWS_HALAL = ("halal",)


class Skip(Exception):
    """A day that makes no episode, with the reason for the page."""


# ------------------------------------------------------------------------------------------------------------- settings

def hhmm(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    return text if re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", text) else fallback


def config(settings: dict[str, Any]) -> dict[str, Any]:
    """Wan's row `comic_series` with the file's defaults: {enabled, paused, lanes: [ids in order], at, series, words_mode,
    style, make_now}. The switch is OFF unless it is exactly true; a lane the list does not name is off."""
    raw = settings.get(KEY) if isinstance(settings.get(KEY), dict) else {}
    given = raw.get("lanes")
    lanes: list[str] = []
    for lane in (given if isinstance(given, list) else RULES["lanes"]):
        if lane in LANE_IDS and lane not in lanes:
            lanes.append(lane)
    lib = comic_library.library(settings.get("comic"))
    series = str(raw.get("series") or RULES["series"])
    if not any(s["id"] == series for s in lib["series"]):
        series = RULES["series"]
    mode = str(raw.get("words_mode") or RULES["words_mode"])
    style = str(raw.get("style") or "")
    return {"enabled": raw.get("enabled") is True, "paused": raw.get("paused") is True, "lanes": lanes,
            "at": hhmm(raw.get("at"), RULES["at"]), "series": series, "words_mode": mode if mode in ("art", "auto") else "art",
            "style": style if any(x["id"] == style for x in lib["styles"]) else "", "make_now": str(raw.get("make_now") or "")}


def myt_day(now: datetime) -> str:
    return (now + MYT).date().isoformat()


def myt_clock(now: datetime) -> str:
    return (now + MYT).strftime("%H:%M")


def read_state(store: Any) -> dict[str, Any]:
    try:
        rows = store.table(db.SETTINGS).select("value").eq("key", STATE_KEY).limit(1).execute().data or []
    except Exception as exc:  # noqa: BLE001 - before 086 there is no row: the day is still planned
        log.info("series state not read (%s)", str(exc)[:100])
        return {}
    value = rows[0].get("value") if rows else None
    return dict(value) if isinstance(value, dict) else {}


def write_state(store: Any, state: dict[str, Any]) -> None:
    """The worker's own row. Upsert, so a database without 086 still keeps the record (the page then reads it from here)."""
    try:
        store.table(db.SETTINGS).upsert({"key": STATE_KEY, "value": state}, on_conflict="key").execute()
    except Exception as exc:  # noqa: BLE001 - the episode is made either way; only the page's list of days is missing
        log.warning("series state not written (%s)", str(exc)[:120])


def note(store: Any, entry: dict[str, Any]) -> dict[str, Any]:
    """One line in the series' record (the page shows the last 30) and one row in the log. `entry`: {day, status: planned |
    skipped | off, lane, title, reason, motion_id}."""
    state = read_state(store)
    lines = [x for x in (state.get("log") or []) if isinstance(x, dict)]
    stamped = {**entry, "at": datetime.now(UTC).isoformat(timespec="seconds")}
    lines = [x for x in lines if not (x.get("day") == entry.get("day") and x.get("status") == entry.get("status"))] + [stamped]
    write_state(store, {**state, "last": stamped, "log": lines[-LOG_KEEP:]})
    status = entry.get("status")
    if status == "planned":
        db.log_event(store, "info", "comic", "comic.daily.planned",
                     f"Siri komik harian: storyboard episod {entry.get('episode')} ({entry.get('lane')}) ditulis, "
                     f"menunggu kelulusan: {str(entry.get('title') or '')[:100]}", ref_table=MOTIONS,
                     ref_id=entry.get("motion_id"),
                     detail={k: v for k, v in entry.items() if k != "title"})
    elif status == "skipped":
        db.log_event(store, "info", "comic", "comic.daily.skipped",
                     f"Siri komik harian: tiada episod pada {entry.get('day')}: {str(entry.get('reason') or '')[:220]}",
                     detail={k: v for k, v in entry.items() if k != "reason"} | {"reason": str(entry.get("reason") or "")[:600]})
    return stamped


# --------------------------------------------------------------------------------------------------- the ruling rules

# who may be named as the body that issued a position. Each pattern keeps the phrase as the row wrote it (a bureau's own name).
_CAP = r"(?-i:[A-Z][\w'-]*)"           # a capitalised word: the rest of a bureau's name, never the verb after it
ISSUERS = [re.compile(p, re.I) for p in (
    rf"(?:Pejabat|Jabatan) Mufti(?: Negeri| Wilayah)?(?: {_CAP}){{0,3}}",
    r"(?:Jawatankuasa )?Muzakarah(?: Jawatankuasa Fatwa)?(?: Majlis Kebangsaan| Kebangsaan)?(?: Hal Ehwal Agama Islam)?",
    rf"Majlis Fatwa(?: Kebangsaan| Negeri)?(?: {_CAP}){{0,2}}",
    rf"Jawatankuasa Fatwa(?: Negeri| Kebangsaan)?(?: {_CAP}){{0,2}}",
    rf"Majlis Agama Islam(?: Negeri| Wilayah)?(?: {_CAP}){{0,3}}",
    rf"Jabatan Agama Islam(?: Negeri| Wilayah)?(?: {_CAP}){{0,3}}",
    r"Jabatan Kemajuan Islam Malaysia", r"Bahagian Pengurusan Halal(?: JAKIM)?", r"Halal Development Corporation",
    r"\b(?:JAKIM|JAIS|JAWI|JAIP|JAIN|JAIK|MAIWP|MAIS|MAINS|HDC|MUIS|BKKM|FSQD|NPRA|KPDN|KKM|KPKM|HSA|EFSA|OPSS|SCCS|NMPA|"
    r"ANVISA|MFDS|TGA|SFDA|MPOB)\b",
    r"Kementerian Kesihatan Malaysia", r"Kementerian Perdagangan Dalam Negeri(?: dan Kos Sara Hidup)?",
    r"Bahagian Keselamatan dan Kualiti Makanan", r"Pihak Berkuasa Kawalan Dadah",
    r"Biro Pengawalan Farmaseutikal Kebangsaan", r"European Commission", r"Health Sciences Authority",
)]
YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
DATE_TEXT = re.compile(r"\b\d{1,2}[ /.-](?:\d{1,2}|[A-Za-z]{3,9})[ /.-](?:19|20)\d{2}\b")

# what makes a row (or a bubble) a RULING: a position on what is permitted or forbidden by religion. "halal" alone is not one
# (a halal logo, a halal certificate), a predicate on it is.
RULING_WORDS = re.compile(
    r"\b(?:fatwa|difatwakan|irsyad|muzakarah|hukum(?:nya)?|haram|diharamkan|mengharamkan|dihalalkan|najis|syubhah|makruh|"
    r"(?:adalah|ialah|memang|tetap|jadi|tentu|pasti|sah|tak|tidak|bukan|dah|sudah|masih|pun)\s+(?:halal|harus|mubah)|"
    r"halal\s+(?:ke|kah|atau)\b)", re.I)
FIRST_PERSON = re.compile(
    r"\b(?:saya|aku|kami|kita)\s+(?:putuskan|fatwakan|haramkan|halalkan|tetapkan|rasa\s+(?:ini\s+)?(?:haram|halal))\b|"
    r"\bhukumnya\s+(?:ialah|adalah|=)", re.I)
SCRIPTURE = re.compile(
    r"[؀-ۿ]|\b(?:al-?quran|quran|al-?qur'?an|surah|surah?\s+\w+\s+ayat|ayat\s+\d|hadis|hadith|firman\s+allah|sabda\s+nabi)\b",
    re.I)
GENERIC = frozenset("""pejabat jabatan majlis jawatankuasa bahagian kebangsaan negeri agama islam malaysia kementerian
persekutuan fatwa muzakarah hal ehwal dan the of""".split())


def is_ruling_text(text: str) -> bool:
    return bool(RULING_WORDS.search(text or ""))


def _item_text(item: dict[str, Any]) -> str:
    raw = item.get("raw") if isinstance(item.get("raw"), dict) else {}
    return " ".join(str(x or "") for x in (item.get("title"), item.get("summary"), raw.get("cite")))


def when_of(item: dict[str, Any]) -> str:
    """The row's own date as the poster says it ("17 Nov 2026"), or the year the row names, or ""."""
    stamp = str(item.get("published_at") or "")
    if stamp:
        try:
            d = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            if d.year < 2100:
                return f"{d.day} {d.strftime('%b %Y')}"
        except ValueError:
            pass
    raw = item.get("raw") if isinstance(item.get("raw"), dict) else {}
    cite = str(raw.get("cite") or "")
    text = _item_text(item)
    m = DATE_TEXT.search(cite) or DATE_TEXT.search(text) or YEAR.search(cite) or YEAR.search(text)
    return m.group(0) if m else ""


def body_of(item: dict[str, Any]) -> str:
    """The body the row names as the one that issued the position, as the row writes it: the citation first (it is the
    instrument), then the title, then the summary. "" when none is named."""
    raw = item.get("raw") if isinstance(item.get("raw"), dict) else {}
    for text in (str(raw.get("cite") or ""), str(item.get("title") or ""), str(item.get("summary") or "")):
        for rx in ISSUERS:
            m = rx.search(text)
            if m:
                return " ".join(m.group(0).split())
    return ""


def ruling_source(item: dict[str, Any]) -> dict[str, str] | None:
    """{body, statement, date} for a row that reports a position, or None when the row does not give the issuing body AND its
    date. The statement is what was said or decided: the row's citation (a fatwa's series and number), else its title."""
    body, date = body_of(item), when_of(item)
    if not body or not date:
        return None
    raw = item.get("raw") if isinstance(item.get("raw"), dict) else {}
    statement = " ".join(str(raw.get("cite") or "").split()) or statement_of(item)
    return {"body": body, "statement": statement[:160], "date": date}


def statement_of(item: dict[str, Any]) -> str:
    """What the row says, short: its title, except a MYRA row whose title is a fragment of the sheet (its first sentence)."""
    title = " ".join(str(item.get("title") or "").split())
    if item.get("section") == "myra" or len(title) < 12:
        first = re.split(r"(?<=[.!?])\s+", " ".join(str(item.get("summary") or "").split()))[0]
        return first[:140] or title
    return title[:140]


def sensitive(item: dict[str, Any], lane: str) -> bool:
    return lane == "fatwa" or is_ruling_text(_item_text(item))


def source_line(item: dict[str, Any], ruling: dict[str, str] | None) -> str:
    """The source printed under the comic, BUILT FROM THE ROW (the writer never writes it): who issued it, what it is, when.
    Short enough for the frame (comic.MAX_SOURCE; the frame fits it in at most three rows)."""
    raw = item.get("raw") if isinstance(item.get("raw"), dict) else {}
    cite = " ".join(str(raw.get("cite") or "").split())
    if ruling:
        if cite and ruling["body"].casefold() in cite.casefold() and YEAR.search(cite):
            return cite[:200]                                      # "Irsyad al-Fatwa Siri Ke-281, Pejabat Mufti ... (2019)"
        return f"{ruling['body']}: {ruling['statement'][:110]}, {ruling['date']}"[:200]
    when = when_of(item)
    source = str(item.get("source") or "").strip()
    if item.get("section") == "news":
        return f"{source}, {when}"[:200] if source and when else (source or when)
    who = body_of(item) or source
    if item.get("section") == "publication":
        journal = re.sub(r"^PubMed\s*[·-]\s*", "", source)
        doi = f", DOI {raw['doi']}" if raw.get("doi") else ""
        return f"{journal}, {when}{doi}"[:200]
    text = f"{who}: {statement_of(item)}"
    return (f"{text[:130].rstrip()}, {when}" if when else text[:140])[:200]


def issuer_aliases(body: str) -> list[str]:
    """What a bubble may call the issuing body: the full name, or any distinctive word of it ("Mufti Wilayah", "JAKIM")."""
    full = " ".join(body.split()).casefold()
    words = [w.casefold() for w in re.findall(r"[\w'-]+", body) if len(w) >= 3 and w.casefold() not in GENERIC]
    return [full] + words if full else []


def names_issuer(text: str, body: str) -> bool:
    low = (text or "").casefold()
    return any(a and a in low for a in issuer_aliases(body))


def ruling_problems(units: list[str], ruling: dict[str, str] | None) -> list[str]:
    """Why the words of an episode (the title, then every bubble, or a caption) are refused, one sentence each, or [].
    * a verse or a hadith is never typed in a bubble (the verse path, quran.py, is the only way a verse appears);
    * a character never rules ("saya putuskan", "hukumnya ialah");
    * a unit that states a ruling (haram, fatwa, hukum...) must name the body the ROW says issued it, and without such a body
      in the row no unit may state a ruling at all."""
    out: list[str] = []
    for unit in units:
        text = " ".join(str(unit or "").split())
        if not text:
            continue
        if SCRIPTURE.search(text):
            out.append(f'"{text[:70]}" quotes or names a verse or a hadith: scripture appears only through the verse path')
        if FIRST_PERSON.search(text):
            out.append(f'"{text[:70]}" is a character giving a ruling: a character only reports what an authority stated')
        elif is_ruling_text(text):
            if not ruling:
                out.append(f'"{text[:70]}" states a ruling, and the source row gives no issuing body and date: write around it')
            elif not names_issuer(text, ruling["body"]):
                out.append(f'"{text[:70]}" states a ruling without naming who issued it ({ruling["body"]}): '
                           "report it as that body's statement")
    return out[:6]


# ------------------------------------------------------------------------------------------------------------ the feed

def _story_keys(store: Any) -> tuple[set[str], set[str]]:
    """(story keys, urls) of every episode ever planned, a rejected storyboard's too: a story is told once."""
    keys: set[str] = set()
    urls: set[str] = set()
    try:
        rows = (store.table(MOTIONS).select("options,status").eq("options->>template", TEMPLATE).limit(2000).execute().data or [])
    except Exception as exc:  # noqa: BLE001
        log.info("earlier episodes not read (%s)", str(exc)[:100])
        return keys, urls
    for r in rows:
        item = (((r.get("options") or {}).get("series") or {}).get("item") or {}) if isinstance(r.get("options"), dict) else {}
        if item.get("title"):
            keys.add(autofill.story_key(item["title"]))
        if item.get("url"):
            urls.add(str(item["url"]))
    return keys, urls


def _used_by_ideas(store: Any, urls: list[str]) -> set[str]:
    spent: set[str] = set()
    try:
        for chunk in db._in_filter_chunks([u for u in urls if u]):
            spent |= {r.get("source_url") for r in (store.table(db.IDEAS).select("source_url").in_("source_url", chunk)
                                                    .execute().data or [])}
    except Exception as exc:  # noqa: BLE001 - only the preference for an unused story is lost
        log.info("ideas not read (%s)", str(exc)[:100])
    return spent


def _news(store: Any, now: datetime, hours: int, *, need_rule: bool,
          categories: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
    """Newspaper headlines of the last `hours` (the scraper keeps them 48), shaped like feed items. `need_rule`: only those that
    name a regulator, an instrument or an enforcement step (autofill.regulatory_link)."""
    since = (now - timedelta(hours=hours)).isoformat()
    cats = list(categories or autofill.NEWS_CATEGORIES)
    try:
        rows = (store.table(db.TRENDS).select("id,title,source,url,summary,category,published_at,created_at")
                .in_("category", cats).gte("created_at", since).order("created_at", desc=True).limit(200).execute().data or [])
    except Exception as exc:  # noqa: BLE001
        log.info("news not read (%s)", str(exc)[:100])
        return []
    out = []
    for r in rows:
        item = {"id": r["id"], "section": "news", "source": r.get("source"), "kind": "news", "title": r.get("title"),
                "url": r.get("url"), "summary": r.get("summary"), "why": None,
                "domain": autofill.NEWS_DOMAIN.get(r.get("category")), "raw": {}, "published_at": r.get("published_at"),
                "created_at": r.get("created_at"), "category": r.get("category")}
        item["regulatory_link"] = autofill.regulatory_link(item)
        if not need_rule or item["regulatory_link"]:
            out.append(item)
    return out


def _watch(store: Any, lane: str, now: datetime, days: int) -> list[dict[str, Any]]:
    since = (now - timedelta(days=days)).isoformat()
    sections = list(WATCH_SECTIONS.get(lane, ()))
    if not sections:
        return []
    q = (store.table(autofill.WATCH).select(autofill.SELECT).eq("relevant", True).eq("dismissed", False).in_("section", sections))
    if lane == "halal":
        q = q.eq("domain", "halal_my")
    elif lane == "fatwa":
        q = q.eq("domain", "fatwa")
    elif lane == "regulatori":
        q = q.neq("domain", "lain")
    try:
        rows = q.order("created_at", desc=True).limit(300).execute().data or []
    except Exception as exc:  # noqa: BLE001
        log.info("feed not read for %s (%s)", lane, str(exc)[:100])
        return []
    # the OneDrive bank is not news: it has no age limit (autofill.candidates does the same); everything else is fresh for `days`
    return [r for r in rows if r.get("section") == "folder" or str(r.get("created_at") or "") >= since]


def lane_pool(store: Any, lane: str, now: datetime) -> list[dict[str, Any]]:
    """Every feed item the lane READS, before any judging, newest first (a bank row last):
      isu_semasa  newspaper headlines (48 h) that name a regulator, a rule or enforcement;
      halal       halal newspaper headlines (48 h) + halal feed rows (regulator pages, MYRA, the OneDrive bank, papers);
      regulatori  regulator notices in the regulatory feed and MYRA's daily sweep;
      fatwa       rows tagged fatwa (today the OneDrive Fatwa folder bank; there is no live fatwa feed)."""
    hours, days = int(RULES["news_hours"]), int(RULES["watch_days"])
    if lane == "isu_semasa":
        return _news(store, now, hours, need_rule=True)
    if lane == "halal":
        return _news(store, now, hours, need_rule=False, categories=NEWS_HALAL) + _watch(store, "halal", now, days)
    if lane in ("regulatori", "fatwa"):
        rows = _watch(store, lane, now, days)
        return sorted(rows, key=lambda r: (SECTION_RANK.get(r.get("section") or "", 9)))
    return []


def refusal(item: dict[str, Any], lane: str, *, keys: set[str], urls: set[str], store: Any = None) -> str:
    """Why this item cannot be today's episode, or "" when it can (the reason is kept for the day's record)."""
    title = " ".join(str(item.get("title") or "").split())
    summary = " ".join(str(item.get("summary") or "").split())
    if not title or len(summary) < 30:
        return "no_text"
    if item.get("section") not in ("news", *SECTION_RANK):
        return "social_source"
    if autofill.story_key(title) in keys or (item.get("url") and item["url"] in urls):
        return "already_told"
    earlier = {"id": "", "stream": "regulab", "source_url": item.get("url"),
               "trend_id": item.get("id") if item.get("section") == "news" else None}
    if store is not None and ideas.already_published(store, earlier):
        return "already_published"
    if sensitive(item, lane) and not ruling_source(item):
        return "no_issuing_body_and_date"
    if lane == "fatwa" and not is_ruling_text(_item_text(item)):
        return "not_a_ruling"
    return ""


def pick(store: Any, cfg: dict[str, Any], now: datetime) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """(the day's item with its `lane`, the trail): lanes in Wan's order, the first item that passes. The trail says for every
    lane how many items it read and why the rest were refused, so a day with no episode can say exactly why."""
    keys, urls = _story_keys(store)
    trail: list[dict[str, Any]] = []
    for lane in cfg["lanes"]:
        pool = autofill.one_per_story(lane_pool(store, lane, now))
        spent = _used_by_ideas(store, [str(x.get("url") or "") for x in pool])
        # a story nobody has made an idea of comes first; a used one is still allowed (a comic tells it another way)
        pool.sort(key=lambda x: 1 if x.get("url") in spent else 0)
        why: dict[str, int] = {}
        for item in pool:
            reason = refusal(item, lane, keys=keys, urls=urls, store=store)
            if not reason:
                trail.append({"lane": lane, "read": len(pool), "refused": why, "picked": True})
                return {**item, "lane": lane}, trail
            why[reason] = why.get(reason, 0) + 1
        trail.append({"lane": lane, "read": len(pool), "refused": why, "picked": False})
    return None, trail


def trail_words(trail: list[dict[str, Any]], lanes: list[str]) -> str:
    """The skipped day in one sentence: each lane, what it read and why nothing fitted."""
    if not lanes:
        return "no lane is switched on in the lane list"
    names = {d["id"]: d["name"]["en"] for d in RULES["lane_defs"]}
    parts = []
    for t in trail:
        refused = ", ".join(f"{n} {k.replace('_', ' ')}" for k, n in sorted(t["refused"].items()))
        parts.append(f"{names.get(t['lane'], t['lane'])}: read {t['read']}" + (f", refused {refused}" if refused else ""))
    return "; ".join(parts) or "nothing was read"


# ----------------------------------------------------------------------------------------------------------- the plan

def episodes_of(store: Any, day: str | None = None) -> list[dict[str, Any]]:
    """The series' Motion rows (any day, or one MYT day), newest first. A rejected storyboard is returned too."""
    try:
        q = (store.table(MOTIONS).select("id,status,options,title,created_at,queued_post_id,error,stage")
             .eq("options->>template", TEMPLATE))
        if day:
            q = q.eq("options->series->>day", day)
        rows = q.order("created_at", desc=True).limit(400).execute().data or []
    except Exception as exc:  # noqa: BLE001
        log.info("episodes not read (%s)", str(exc)[:100])
        return []
    return rows


def episode_number(store: Any, series_id: str) -> int:
    """The series' count so far + 1 (comic_job.episodes_so_far counts the drawn comics), never below the highest number an
    episode already planned (a storyboard still waiting holds its number), so two planned episodes never share one."""
    from . import comic_job
    drawn = comic_job.episodes_so_far(store, series_id, "")
    planned = 0
    for r in episodes_of(store):
        s = ((r.get("options") or {}).get("series") or {}) if isinstance(r.get("options"), dict) else {}
        if s.get("id") == series_id and r.get("status") != "rejected":
            planned = max(planned, int(s.get("episode") or 0))
    return max(drawn, planned) + 1


def brief_of(item: dict[str, Any], ruling: dict[str, str] | None) -> str:
    """The writer's whole world for the episode: the row's own words and nothing else (a figure the row lacks is invented)."""
    raw = item.get("raw") if isinstance(item.get("raw"), dict) else {}
    parts = [f"ISU: {' '.join(str(item.get('title') or '').split())}",
             f"RINGKASAN DARIPADA SUMBER: {' '.join(str(item.get('summary') or '').split())[:1200]}"]
    if raw.get("cite"):
        parts.append(f"RUJUKAN DALAM SUMBER: {' '.join(str(raw['cite']).split())[:300]}")
    if when_of(item):
        parts.append(f"TARIKH SUMBER: {when_of(item)}")
    if ruling:
        parts.append(f"KEDUDUKAN YANG DILAPORKAN: {ruling['statement']} (dikeluarkan oleh {ruling['body']}, {ruling['date']})")
    return "\n".join(parts)[:3800]


def snapshot(item: dict[str, Any]) -> dict[str, Any]:
    raw = item.get("raw") if isinstance(item.get("raw"), dict) else {}
    return {"id": str(item.get("id") or ""), "section": item.get("section"), "source": item.get("source"),
            "title": " ".join(str(item.get("title") or "").split())[:300], "url": item.get("url") or "",
            "summary": " ".join(str(item.get("summary") or "").split())[:1500], "domain": item.get("domain"),
            "published_at": item.get("published_at"), "lane": item.get("lane"),
            "raw": {k: raw[k] for k in ("cite", "doi") if raw.get(k)}}


def plan_today(store: Any, settings: dict[str, Any], now: datetime | None = None, *, force: bool = False,
               via: str = "schedule") -> dict[str, Any]:
    """Queue today's episode (one Motion film waiting for its storyboard), or say why not. Returns {status, reason, ...}:
    status is "planned", "skipped", "exists", "off", "paused" or "early". Never raises.

    `force` is Wan's own button or Telegram tap ("Buat episod hari ini sekarang"): it skips the switch, the pause and the
    clock, but never the one-a-day rule: a day that already has an episode (not a rejected one) makes none."""
    now = now or datetime.now(UTC)
    day = myt_day(now)
    try:
        cfg = config(settings)
        if not force:
            if not cfg["enabled"]:
                return {"status": "off", "reason": "the daily series is switched off"}
            if cfg["paused"]:
                return {"status": "paused", "reason": "the daily series is paused"}
            if myt_clock(now) < cfg["at"]:
                return {"status": "early", "reason": f"not before {cfg['at']} (Malaysia time)"}
        have = [r for r in episodes_of(store, day) if r.get("status") != "rejected"]
        if have:
            return {"status": "exists", "reason": f"today's episode already exists ({have[0].get('status')})",
                    "motion_id": have[0]["id"]}
        if not force and any(x.get("day") == day and x.get("status") == "skipped" for x in (read_state(store).get("log") or [])):
            return {"status": "exists", "reason": "today was already looked at and no fitting item was found"}
        item, trail = pick(store, cfg, now)
        if not item:
            reason = trail_words(trail, cfg["lanes"])
            entry = {"day": day, "status": "skipped", "reason": reason, "trail": trail, "via": via}
            note(store, entry)
            return {"status": "skipped", "reason": reason, "trail": trail}
        ruling = ruling_source(item) if sensitive(item, item["lane"]) else None
        series_id = cfg["series"]
        number = episode_number(store, series_id)
        row = {"brief": brief_of(item, ruling)[:1900], "source_url": "", "stream": "regulab", "language": "bm",
               "resolution": "portrait", "status": "pending", "voice": "off", "ai_background": False,
               "options": {"template": TEMPLATE, "via": "comic_daily", "story": item["title"][:300],
                           "series": {"id": series_id, "episode": number, "day": day, "lane": item["lane"],
                                      "words_mode": cfg["words_mode"], "style": cfg["style"], "item": snapshot(item),
                                      "ruling": ruling,
                                      "source": source_line(item, ruling), "requested": via, "trail": trail}}}
        made = store.table(MOTIONS).insert(row).execute().data[0]
        note(store, {"day": day, "status": "planned", "lane": item["lane"], "title": item["title"], "episode": number,
                     "motion_id": made["id"], "via": via})
        return {"status": "planned", "reason": "", "motion_id": made["id"], "lane": item["lane"], "episode": number,
                "title": item["title"], "trail": trail}
    except Exception as exc:  # noqa: BLE001 - a day that failed to plan must never stop the Motion run
        log.warning("daily comic not planned (%s)", str(exc)[:200])
        return {"status": "error", "reason": str(exc)[:200]}


def make_now_due(store: Any, settings: dict[str, Any]) -> bool:
    """Has Wan pressed "Buat episod hari ini sekarang" since the worker last answered? (the page writes
    `comic_series.make_now` = a timestamp; the worker records the one it answered in its own row)."""
    asked = config(settings)["make_now"]
    if not asked:
        return False
    return asked > str(read_state(store).get("make_now_done") or "")


def say(res: dict[str, Any], lang: str = "bm") -> str:
    """What the button's answer says, in Wan's language: the storyboard is on its way, or why no episode was made."""
    bm = lang != "en"
    status = res.get("status")
    if status == "planned":
        return (f"Episod {res.get('episode')} (lorong {res.get('lane')}) sedang ditulis storyboardnya. Saya hantar di sini untuk "
                "anda luluskan; tiada gambar dibayar sebelum itu." if bm else
                f"Episode {res.get('episode')} (lane {res.get('lane')}) is having its storyboard written. I send it here for "
                "your approval; no picture is paid for before that.")
    if status == "exists":
        return (f"Episod hari ini sudah ada: {res.get('reason')}. Satu episod sehari sahaja." if bm else
                f"Today's episode already exists: {res.get('reason')}. One episode a day at most.")
    if status == "skipped":
        return (f"Tiada item yang sesuai hari ini, jadi tiada episod: {res.get('reason')}" if bm else
                f"Nothing fitting today, so no episode: {res.get('reason')}")
    why = res.get("reason") or status
    return f"Episod tidak dibuat: {why}" if bm else f"No episode was made: {why}"


def run(store: Any, settings: dict[str, Any], now: datetime | None = None) -> str:
    """Motion's hook: answer a button press, plan the day, and draft the post a done film still waits for. One log line."""
    now = now or datetime.now(UTC)
    out: list[str] = []
    try:
        if make_now_due(store, settings):
            res = plan_today(store, settings, now, force=True, via="page")
            state = read_state(store)
            write_state(store, {**state, "make_now_done": config(settings)["make_now"], "make_now_result": res["status"],
                                "make_now_reason": str(res.get("reason") or "")[:300]})
            out.append(f"make now: {res['status']}")
        else:
            res = plan_today(store, settings, now)
            if res["status"] in ("planned", "skipped", "error"):
                out.append(f"daily: {res['status']}")
        queued = queue_finished(store, settings)
        if queued:
            out.append(f"{queued} post(s) drafted")
    except Exception as exc:  # noqa: BLE001
        log.warning("daily comic step failed (%s)", str(exc)[:200])
        out.append("error")
    return "; ".join(out)


# ---------------------------------------------------------------------------------------------------- the storyboard

SENSITIVE_RULES = """HALAL, FATWA AND RELIGION ARE SENSITIVE. These rules outrank everything else:
- Nobody in this comic is a religious authority and nobody issues a ruling. A character never says that something is haram, halal
  (as a verdict), najis, syubhah, makruh or harus on their own account, never says "hukumnya", and never says "saya putuskan".
- A ruling or a fatwa appears ONLY as a position REPORTED from the BRIEF: "menurut <the issuing body in the BRIEF>", "<body>
  menyatakan ...". The bubble that reports it names that body. If the BRIEF does not name who issued a position and when, say
  nothing about the position: write around it and keep to the facts the BRIEF does give.
- Never type a verse of the Quran or a hadith, never name a surah or an ayat, never write Arabic script, never put words in the
  mouth of God or the Prophet.
- B (the one who reads the notice) is not a religious officer: if A asks "so is it haram?", B says that is not hers to answer and
  reads what the authority stated, naming it. Nobody mocks a belief, a practice or a person.
- The source line under the comic is printed by the system from the BRIEF; do not write one into a bubble."""

TODAY_RULES = """TODAY'S EPISODE ("isu semasa"): the BRIEF is one real item of the day. The comic tells ONLY what the BRIEF
says, in four panels: panel 1 the question a shop owner would ask, panels 2 and 3 what the notice or news actually
says, panel 4 the plain takeaway the BRIEF supports. Every name, number, date and body appears in a bubble only as
the BRIEF writes it. Never add advice, a prediction, a blame or a call to action. The episode is in the series' fixed
cast; keep each person's manner."""


def writer_brief(sx: dict[str, Any]) -> tuple[str, str]:
    """(the brief for the writer, the source line) of a planned episode, rebuilt from the item the plan snapshotted."""
    item = dict(sx.get("item") or {})
    ruling = sx.get("ruling") if isinstance(sx.get("ruling"), dict) else None
    return brief_of(item, ruling), str(sx.get("source") or source_line(item, ruling))


def check_script(script: dict[str, Any], ruling: dict[str, str] | None) -> str:
    """The daily series' own judge, over the title and every bubble: "" or the reason (sent back to the writer once)."""
    problems = ruling_problems(comic_writer.units(script), ruling)
    return "; ".join(problems[:3])


def write_storyboard(store: Any, row: dict[str, Any], llm: Any,
                     settings: dict[str, Any] | None = None) -> tuple[dict[str, Any], str]:
    """The episode's storyboard (ONE text call, two at most when the first script is refused) and its note. Raises
    comic.ComicError with the reason when the writer is off or refuses twice: the film then fails with that reason and
    nothing is drawn."""
    settings = settings if settings is not None else ideas.load_settings(store)
    options = row.get("options") if isinstance(row.get("options"), dict) else {}
    sx = dict(options.get("series") or {})
    lib = comic_library.library(settings.get("comic"))
    series = comic_library.series_of(lib, sx.get("id") or RULES["series"])
    if not series:
        raise comic.ComicError("the series is not in the library any more: pick another in the series settings")
    reg = ((settings.get("brand") or {}).get("regulab") or {})
    brief, source = writer_brief(sx)
    ruling = sx.get("ruling") if isinstance(sx.get("ruling"), dict) else None
    rules = SENSITIVE_RULES + "\n\n" + TODAY_RULES + (
        f"\n\nTHE REPORTED POSITION in the BRIEF was issued by {ruling['body']} on {ruling['date']}: a bubble that "
        f"reports it names {ruling['body']}." if ruling else "\n\nThe BRIEF reports no ruling: no bubble states one.")
    written = comic_writer.write(llm, brief, "regulab", series, source=source, brand=reg, extra_rules=rules,
                                 check=lambda script: check_script(script, ruling))
    script = comic_writer.assemble(written, series, "regulab", source)
    sb = {"series": series["id"], "series_name": series["name"], "episode": int(sx.get("episode") or 0),
          "lane": sx.get("lane"), "day": sx.get("day"), "title": script["title"], "setting": script["setting"],
          "panels": [{"scene": p["scene"], "lines": [{"who": ln["who"], "text": ln["text"]} for ln in p["lines"]]}
                     for p in script["panels"]],
          "source": source, "ruling": ruling, "words_mode": sx.get("words_mode") or RULES["words_mode"],
          "style": sx.get("style") or "", "names": comic_library.names_of(series)}
    lane = {d["id"]: d["name"]["bm"] for d in RULES["lane_defs"]}.get(str(sx.get("lane")), str(sx.get("lane") or ""))
    return sb, f"Siri {series['name']} · Episod {sb['episode']} · lorong {lane} · {source}"[:300]


def recheck(sb: Any, settings: dict[str, Any]) -> dict[str, Any]:
    """The approved storyboard (usually as Wan edited it), checked again with the same rules the writer's script went through.
    Returns the checked storyboard; raises motion_templates.StoryboardError naming what is wrong (the film then goes back to
    review with the reason and nothing is drawn). The source line is not editable: it is rebuilt from the item."""
    from .motion_templates import StoryboardError
    if not isinstance(sb, dict):
        raise StoryboardError("there is no comic storyboard")
    lib = comic_library.library(settings.get("comic"))
    series = comic_library.series_of(lib, sb.get("series") or RULES["series"])
    if not series:
        raise StoryboardError("the series is not in the library any more")
    reg = ((settings.get("brand") or {}).get("regulab") or {})
    ruling = sb.get("ruling") if isinstance(sb.get("ruling"), dict) else None
    try:
        script = comic_writer.assemble({"title": sb.get("title"), "setting": sb.get("setting"), "panels": sb.get("panels")},
                                       series, "regulab", str(sb.get("source") or ""))
    except comic.ComicError as exc:
        raise StoryboardError(str(exc)) from exc
    why = comic_writer.refusal(comic_writer.flags(script, "regulab", reg)) or check_script(script, ruling)
    if why:
        raise StoryboardError(f"the comic breaks a rule: {why}")
    return {**sb, "title": script["title"], "setting": script["setting"], "names": comic_library.names_of(series),
            "source": script["source"].removeprefix("Sumber: "),
            "panels": [{"scene": p["scene"], "lines": [{"who": ln["who"], "text": ln["text"]} for ln in p["lines"]]}
                       for p in script["panels"]]}


def script_of(sb: dict[str, Any]) -> list[dict[str, Any]]:
    """The storyboard as the film row's `script` (what the Motion card shows and what the captions are written from)."""
    return [{"id": "title", "role": "hook", "heading": sb["title"], "lines": [f"Episod {sb.get('episode')}"]}] + [
        {"id": f"p{i + 1}", "role": "scene", "heading": f"Panel {i + 1}",
         "lines": [f"{ln['who']}: {ln['text']}" for ln in p["lines"]], "shot": p["scene"]}
        for i, p in enumerate(sb["panels"])] + [
        {"id": "end", "role": "end", "heading": str(sb.get("source") or ""), "lines": []}]


# ------------------------------------------------------------------------------------------------------- the draft post

def queue_post(store: Any, row: dict[str, Any], settings: dict[str, Any] | None = None) -> str | None:
    """The finished film as a DRAFT ws.regulab post on the next free slot (what the page's "queue to post" does, by the
    worker: supabase/051 needs a signed-in person, so it is done here with the same rows). The post starts as a draft with
    the page's own scan on it: nothing is approved, scheduled or posted, and Wan's Approve click is the only gate. Returns the
    post id, or None when the film is not finished, was already queued, or a draft already exists for it. Never raises."""
    try:
        got = store.table(MOTIONS).select("*").eq("id", row["id"]).limit(1).execute().data or []
        film = got[0] if got else None
        if not film or film.get("status") != "done" or not film.get("video_url") or film.get("queued_post_id"):
            return None
        settings = settings if settings is not None else ideas.load_settings(store)
        brand = settings.get("brand") or {}
        reg = brand.get("regulab") or {}
        sx = ((film.get("options") or {}).get("series") or {}) if isinstance(film.get("options"), dict) else {}
        sb = (film.get("storyboard") or {}).get("sb") or {}
        captions = {p: caption_fit.fit(str(t or "").strip(), p, "regulab") for p, t in (film.get("captions") or {}).items()
                    if p in compliance.film_platforms_for("regulab") and str(t or "").strip()}
        if not captions:
            return None                          # no caption yet: the next run tries again
        channels = [p for p in motion_captions.platforms_of("regulab") if p in captions]
        taken = ideas.taken_positions(store, "regulab") | autofill.film_positions(store, "regulab")
        date, slot = ideas.next_free_position("regulab", None, brand, taken)
        media = store.table(db.MEDIA).insert({
            "reference_url": film["video_url"], "generated_media_url": film.get("social_url") or film["video_url"],
            "type": "video", "status": "done", "mode": "clip", "prompt": str(film.get("title") or ""),
            "provider": "semasa", "model": "motion",
            "idea_id": film.get("idea_id"),
            "meta": {"flow": "motion", "motion_id": film["id"], "poster_url": film.get("poster_url"), "width": film.get("width"),
                     "height": film.get("height"), "seconds": film.get("duration_s"),
                     "bytes": film.get("social_bytes") if film.get("social_url") else film.get("bytes"),
                     "compressed": bool(film.get("social_url")), "alt": str(film.get("title") or ""),
                     "series": {"id": sx.get("id"), "episode": sx.get("episode")}}}).execute().data[0]
        title = str(film.get("title") or sb.get("title") or "")
        citation = str(sb.get("source") or sx.get("source") or "")
        post = {"idea_id": film.get("idea_id"), "stream": "regulab", "lang": "bm", "hook": title[:300], "text": {"bm": captions},
                "citation": citation[:1000], "media_ids": [media["id"]], "date": date, "slot": slot, "status": "draft",
                "channels": channels, "created_by": None,
                "decisions": [{"at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z"), "by": "worker",
                               "action": f"queued from the daily comic series (episod {sx.get('episode')})"}]}
        flags = compliance.scan({**post, "media": [{"alt": title}]}, brand=reg, schedule=reg.get("schedule"))
        post["flags"], post["hard_flags"] = flags, compliance.hard_count(flags)
        made = store.table(db.POSTS).insert(post).execute().data[0]
        store.table(db.MEDIA).update({"post_id": made["id"]}).eq("id", media["id"]).execute()
        store.table(MOTIONS).update({"queued_post_id": made["id"], "queued_at": datetime.now(UTC).isoformat()}) \
            .eq("id", film["id"]).execute()
        db.log_event(store, "info", "comic", "comic.daily.drafted",
                     f"Siri komik harian: episod {sx.get('episode')} sudah jadi draf pos ({date} {slot}); menunggu Lulus anda",
                     ref_table=db.POSTS, ref_id=made["id"], detail={"motion_id": film["id"], "date": date, "slot": slot})
        return str(made["id"])
    except Exception as exc:  # noqa: BLE001 - the film stays done and unqueued; the next run tries again
        log.warning("daily comic post not drafted (%s)", str(exc)[:200])
        return None


def queue_finished(store: Any, settings: dict[str, Any]) -> int:
    """Draft the post of every finished episode that has none yet (a step that failed leaves the film done and the next run
    finishes the job). Counts the drafts made."""
    n = 0
    for r in episodes_of(store):
        if r.get("status") == "done" and not r.get("queued_post_id") and queue_post(store, r, settings):
            n += 1
    return n
