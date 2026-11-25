"""Filling empty slots (Studio's nightly drafter, brought over 27 Sep 2026), OFF until Wan switches it on in Settings.

FACTS FIRST (Wan, 22 Nov 2026: "after this all content is based on facts as priority rather isu semasa, I will create post isu
semasa from Hermes nous ... prioritize announcement make by regulators or government so people/viewers alert"). This reverses his
9 Nov rule that put newspaper headlines first. Now an empty slot is filled, in this order, from: (1) an ANNOUNCEMENT by a
regulator or the government (the regulator feed: a recall, a ban, a warning, a circular, a notice), newest first; (2) the other
regulator notices; (3) official publications and guidelines (papers, the websites Wan lists, MYRA's findings, his OneDrive angle
bank). The newspaper headline (isu semasa) is OFF by default (`settings.autofill.news` brings it back), and so is every social
row (Reddit, YouTube, Threads, Facebook, Instagram, experts): Hermes supplies isu semasa through the import route, and Wan can
still make an idea of any news item or social post by hand. A gap with no official item is left a gap.

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
from .ideas import ANY_DAY_DOMAINS, FAQ_SOURCE, MYT
from .log import get_logger

log = get_logger("semasa.autofill")

WATCH = "semasa_watch"
FRESH_DAYS = 21                 # an item older than this is not news any more
MAX_DAYS, MAX_PER_RUN = 7, 5
# A FLOOR OF DRAFTS (Wan, 25 Nov 2026: "make sure every hours ada at least 2 draft post, ambil dari guideline/new circular dulu
# if no idea relevant"). The gap pass above only looks `days_ahead` days out, so once the next few days are full (or Wan has
# approved everything waiting) nothing new is written and the Drafts counter reads 0 until a slot opens. The worker runs every
# 15 minutes, so after the gap pass each run counts what is WAITING for Wan (drafts not yet approved, plus ideas already being
# written into drafts) and, when that is under `min_drafts`, writes the difference for the next free positions, looking as far
# as `floor_days` ahead. What it writes from: a guideline or a new circular from the regulator feed first (the "updated
# circular/guideline" pattern LinkedIn already ranks first), then the rest of the official items in the usual order. It never
# invents: with nothing fitting, the run says it is short and writes nothing.
MIN_DRAFTS, MAX_MIN_DRAFTS = 2, 10
FLOOR_DAYS, MAX_FLOOR_DAYS = 14, 30
# FOCUS TOPICS (Wan, 25 Nov 2026: "for draft post, add more on DRGD, FAQ, FSQD"). One draft in every FOCUS_EVERY (default 3) is
# drawn from these topics when something fitting exists: DRGD (NPRA's Drug Registration Guidance Document and drug registration),
# FSQD (the Food Safety and Quality Division: the Food Act and Regulations, food labelling) and FAQ (the answers Wan keeps in his
# FAQ bank, each with its instrument). The rota, the facts-first order and every other rule still apply: this only decides which
# fitting item a position takes, and a position with no fitting focus item takes the ordinary pick. `settings.autofill.focus`
# lists the topics ([] = off) and `focus_every` the share (3 = one in three).
FOCUS_TOPICS = ("drgd", "fsqd", "faq")
FOCUS_EVERY, MAX_FOCUS_EVERY = 3, 10
FOCUS_WINDOW = 6                # how many of the latest auto-written ideas the share is read from
FAQS = "semasa_faqs"
FAQ_DOMAIN = {"halal": "halal_my", "skincare": "kosmetik", "kosmetik": "kosmetik", "makanan": "makanan",
              "farmaseutikal": "farmaseutikal"}               # web/src/lib/brand.js FAQ_CATEGORY_TO_DOMAIN
FAQ_POOL = 400                  # the newest FAQ rows read a run


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
    # the floor of waiting drafts: `min_drafts` 0 switches it off; the search reaches `floor_days` (never fewer than days_ahead)
    try:
        floor = max(0, min(MAX_MIN_DRAFTS, int(raw["min_drafts"]))) if "min_drafts" in raw else MIN_DRAFTS
    except (TypeError, ValueError):
        floor = MIN_DRAFTS
    try:
        reach = max(days, min(MAX_FLOOR_DAYS, int(raw.get("floor_days") or FLOOR_DAYS)))
    except (TypeError, ValueError):
        reach = max(days, FLOOR_DAYS)
    focus = [t for t in (raw["focus"] if isinstance(raw.get("focus"), list) else FOCUS_TOPICS) if t in FOCUS_TOPICS]
    try:
        every = max(2, min(MAX_FOCUS_EVERY, int(raw.get("focus_every") or FOCUS_EVERY)))
    except (TypeError, ValueError):
        every = FOCUS_EVERY
    return {"enabled": on, "days_ahead": days, "per_run": per, "streams": streams, "focus": focus, "focus_every": every,
            "news": raw.get("news") is True,              # the newspaper headline (isu semasa) is OFF unless Wan turns it on
            "min_drafts": floor, "floor_days": reach}


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


SLOT_FORMATS = ("video", "carousel", "poster", "single")
MOTIONS = "semasa_motions"


def auto_format(fmt: str) -> str:
    """What an auto-filled post becomes: a slot with no format is a carousel, drawn with the worker's illustrations (Wan, 23 Nov
    2026: "all post must auto appear carousel ... only if I choose single card"); only a slot Wan set to single is one 4:5 card
    (drawn in the poster looks). video, carousel and poster pass through."""
    return {"": "carousel", "single": "poster"}.get(fmt, fmt)


def slot_format(brand: dict[str, Any], stream: str, slot: str) -> str:
    """What the rota says this slot carries (Wan, 10 Nov 2026: "6 times a day, 2 motions, 2 carousel, 2 single card"):
    settings brand.<stream>.slot_formats = {"08:00": "video", ...}. "" when the slot has no format: the writer chooses."""
    raw = (brand.get(stream) or {}).get("slot_formats")
    fmt = str((raw or {}).get(slot) or "") if isinstance(raw, dict) else ""
    fmt = fmt if fmt in SLOT_FORMATS else ""
    # Wan, 11 Nov 2026: "for linkedn, no need to do motion, only carousel or single card":
    # a LinkedIn slot set to video is a single card
    return "single" if stream == "linkedin" and fmt == "video" else fmt


def film_positions(store: Any, stream: str) -> set[tuple[str, str]]:
    """Positions a Motion film was already asked for and has not been queued to a post yet: never two films for one slot.
    A film that failed or that Wan deleted holds nothing."""
    try:
        rows = (store.table(MOTIONS).select("stream,status,options,queued_post_id").is_("queued_post_id", "null")
                .in_("status", ["waiting", "pending", "working", "done"]).execute().data or [])
    except Exception as exc:  # noqa: BLE001 - the Motion table unreadable only means no film holds a slot
        log.info("film positions not read (%s)", str(exc)[:120])
        return set()
    out = set()
    for r in rows:
        pos = (r.get("options") or {}).get("position") if isinstance(r.get("options"), dict) else None
        if (r.get("stream") or "regulab") == stream and isinstance(pos, dict) and pos.get("date") and pos.get("slot"):
            out.add((str(pos["date"]), str(pos["slot"])))
    return out


def film_row(item: dict[str, Any], stream: str, date: str, slot: str) -> dict[str, Any]:
    """A Motion film WAITING in the queue for a video slot. Nothing is made until Wan taps Start and approves its
    storyboard (supabase/071), and the finished film reaches the slot only when he queues it."""
    words = " ".join(x for x in (str(item.get("title") or "").strip(),
                                 str(item.get("summary") or item.get("why") or "").strip()) if x)
    return {"brief": words[:1900], "source_url": item.get("url") or "", "stream": stream,
            "language": "en" if stream == "linkedin" else "bm",
            "resolution": "square" if stream == "linkedin" else "portrait", "status": "waiting",
            "options": {"via": "autofill", "position": {"date": date, "slot": slot},
                        "story": str(item.get("title") or "")[:300]}}


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

# Newspaper issues (isu semasa): used to come FIRST (Wan, 9 Nov 2026: "masukkan isu semasa sebagai prioriti idea dari surat khabar
# dan relatekan dengan regulatori kalau boleh"). Reversed on 22 Nov 2026 (facts first): they are OFF for auto-fill unless
# `settings.autofill.news` is true, and then they rank AFTER every official item. The scraper keeps a headline 48 hours; politics,
# crime, sport and the like are not this brand's business, so only the regulatory-adjacent categories qualify, and a headline that
# names a regulator or an instrument ranks above the rest of them.
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


# Words that name no event: dropped before two headlines are compared.
_STOP = frozenset("""yang untuk dengan adalah tidak ini itu dan atau dari dalam kepada oleh akan telah sudah baru lebih juga kata
bagi serta bahawa ialah satu kesan bernilai ahli selepas sebelum kini lagi pula the and for with from after before over new says
said about into has have was were that this their its are will not paper news hook""".split())


def story_tokens(key: str) -> frozenset[str]:
    """The words that identify an event in a story key: stop words out, a "di-" passive taken off ("disita" is "sita"), words of
    three letters or more, and any number."""
    out = set()
    for w in str(key or "").split():
        if w in _STOP:
            continue
        if w.startswith("di") and len(w) >= 6:
            w = w[2:]
        if len(w) >= 3 or w.isdigit():
            out.add(w)
    return frozenset(out)


def same_event(a: frozenset[str], b: frozenset[str]) -> bool:
    """Two headlines that are one event told in different words (Wan, 9 Nov 2026: the same halal-certificate seizure arrived as
    "Sijil halal meragukan, AKPS sita daging kerbau...", "Kesan sijil halal meragukan..." and "Sijil halal tidak sepadan dengan
    permit, daging kerbau dari India disita", and the exact-headline check let all three through). At least three identifying
    words in common AND at least 60% of the shorter headline's words: two stories that only share a regulator and a food do
    not match."""
    shared = len(a & b)
    return shared >= 3 and shared / min(len(a), len(b)) >= 0.6


# Names that say little about WHICH event: the regulators, the country, the weekdays and months.
_COMMON_NAMES = frozenset("""malaysia malaysian kementerian kesihatan kkm npra bkkm jakim fsqd kpdn moh jabatan agensi kerajaan
selangor johor perak kedah kelantan terengganu pahang sabah sarawak penang perlis melaka negeri sembilan putrajaya kuala lumpur
isnin selasa rabu khamis jumaat sabtu ahad januari februari mac april mei jun julai ogos september oktober november disember
bernama utusan harian sinar berita astro awani star""".split())
_WORD = re.compile(r"RM\s?\d[\d,.]*|[A-Za-z][A-Za-z0-9&-]+")


def story_profile(title: Any, summary: Any = "") -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    """(title words, title+summary words, names) of a story. A NAME is what actually identifies an event: a company or place
    written with a capital that is not a sentence's first word, an acronym, or an amount (RM413,728). Names are the same
    words story_tokens keeps, found from the original case, which story_key has already thrown away."""
    title_words = story_tokens(story_key(title))
    all_words = set(title_words)
    names: set[str] = set()
    firsts: dict[str, int] = {}
    for part, text in enumerate((str(title or ""), str(summary or ""))):
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            for i, w in enumerate(_WORD.findall(sentence)):
                low = re.sub(r"[^a-z0-9]", "", w.lower())
                if not low or low in _STOP:
                    continue
                if part == 1:
                    all_words.add(low)
                if low in _COMMON_NAMES or len(low) < 3:
                    continue
                if not (w.startswith("RM") or (w[0].isupper() and len(w) >= 4)
                        or (sum(c.isupper() for c in w) >= 2 and len(w) >= 3)):
                    continue
                if i == 0:
                    firsts[low] = firsts.get(low, 0) + 1
                else:
                    names.add(low)
    # a sentence's first word is capitalised by grammar, so it is a name only when it opens more than one sentence (a company
    # that opens the headline and the summary as well)
    names |= {w for w, n in firsts.items() if n >= 2}
    return title_words, frozenset(all_words), frozenset(names)


def same_story_profile(a: tuple[frozenset[str], ...], b: tuple[frozenset[str], ...]) -> bool:
    """Same event by words, with names weighing more (Wan, 9 Nov 2026): the title rule (same_event), or a NAME in common (a
    company, a place, an amount) plus three more words from the headline and summary together. A company that appears in two
    different stories shares few other words, so a name alone never decides it."""
    if same_event(a[0], b[0]):
        return True
    return bool(a[2] & b[2]) and len(a[1] & b[1]) >= 4


def one_per_story(rows: list[dict[str, Any]], spent_stories: set[str] | None = None,
                  spent_profiles: list[tuple[frozenset[str], ...]] | None = None) -> list[dict[str, Any]]:
    """Each story once: the first of its rows wins, a row with the paper's own link is preferred to a Google News redirect (the
    writer can read the article behind it), and a story an idea already used is dropped whatever its link or its wording.
    `spent_profiles` (used_profiles) adds the name-weighted comparison, with the summary, to the title one."""
    spent = set(spent_stories or ())
    spent_tokens = [story_tokens(k) for k in spent]
    spent_profiles = list(spent_profiles or [])
    best: dict[str, dict[str, Any]] = {}
    profiles: dict[str, tuple[frozenset[str], ...]] = {}
    order: list[str] = []
    for r in rows:
        key = story_key(r.get("title"))
        if not key or key in spent:
            continue
        prof = story_profile(r.get("title"), r.get("summary"))
        if key not in best and (any(same_event(prof[0], t) for t in spent_tokens)
                                or any(same_story_profile(prof, q) for q in spent_profiles)):
            continue                                       # the same event under another headline, already written up
        twin = key if key in best else next((k for k in order if same_story_profile(prof, profiles[k])), None)
        if twin is None:
            best[key], profiles[key] = r, prof
            order.append(key)
        elif "news.google.com" in str(best[twin].get("url")) and "news.google.com" not in str(r.get("url")):
            best[twin] = r
    return [best[k] for k in order]


def used_profiles(store: Any, days: int = 14, now: datetime | None = None) -> list[tuple[frozenset[str], ...]]:
    """The name-weighted profiles (title and summary) of the ideas made lately. Never raises."""
    since = ((now or datetime.now(UTC)) - timedelta(days=days)).isoformat()
    try:
        rows = (store.table(db.IDEAS).select("source_title,source_summary").gte("created_at", since).limit(1000)
                .execute().data or [])
    except Exception as exc:  # noqa: BLE001
        log.info("used profiles not read: %s", str(exc)[:100])
        return []
    return [p for p in (story_profile(r.get("source_title"), r.get("source_summary")) for r in rows) if p[0]]


def used_stories(store: Any, days: int = 14, now: datetime | None = None) -> set[str]:
    """Story keys of the ideas made lately: a headline already written up under another link is not written again.
    Never raises."""
    since = ((now or datetime.now(UTC)) - timedelta(days=days)).isoformat()
    try:
        rows = (store.table(db.IDEAS).select("source_title").gte("created_at", since).limit(1000).execute().data or [])
    except Exception as exc:  # noqa: BLE001
        log.info("used stories not read: %s", str(exc)[:100])
        return set()
    titles = [r.get("source_title") for r in rows]
    try:      # a story a film was asked for is used too, so the same headline is not also written as a post
        films = store.table(MOTIONS).select("options").gte("created_at", since).limit(500).execute().data or []
        titles += [(f.get("options") or {}).get("story") for f in films if isinstance(f.get("options"), dict)]
    except Exception as exc:  # noqa: BLE001
        log.info("film stories not read: %s", str(exc)[:100])
    return {k for k in (story_key(t) for t in titles) if k}


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


def usable_title(title: Any) -> bool:
    """A headline a writer can build on: it holds a word of three letters or more (never a bare number or a blank)."""
    return re.search(r"[^\W\d_]{3}", str(title or "")) is not None


# What each focus topic looks like: a regulator's own words, whole words only. DRGD and FSQD are also a DOMAIN: a
# drug-registration (farmaseutikal) or a food (makanan) item from an official section belongs to NPRA's or FSQD's field even
# when its title does not spell the acronym.
DRGD_RE = re.compile(r"\bDRGD\b|drug\s+registration\s+guidance|garis\s+panduan\s+pendaftaran\s+(?:ubat|produk)|"
                     r"drug\s+control\s+authority|pihak\s+berkuasa\s+kawalan\s+dadah|\bPBKD\b", re.I)
FSQD_RE = re.compile(r"\bFSQD\b|food\s+safety\s+and\s+quality|keselamatan\s+(?:dan\s+)?kualiti\s+makanan|food\s+act\s+1983|"
                     r"akta\s+makanan\s+1983|food\s+regulations\s+1985|peraturan-peraturan\s+makanan|\bFoSIM\b|\bMeSTI\b", re.I)
FOCUS_SECTIONS = ("regulatory", "website", "folder", "myra", "faq")


def topic_of(item: dict[str, Any]) -> str | None:
    """"faq", "drgd" or "fsqd" when the item belongs to one of Wan's focus topics (25 Nov 2026), else None."""
    if item.get("section") == "faq":
        return "faq"
    text = f"{item.get('title') or ''} {item.get('summary') or ''}"
    if DRGD_RE.search(text) or (item.get("domain") == "farmaseutikal" and item.get("section") in FOCUS_SECTIONS):
        return "drgd"
    if FSQD_RE.search(text) or (item.get("domain") == "makanan" and item.get("section") in FOCUS_SECTIONS):
        return "fsqd"
    return None


def faq_candidates(store: Any) -> list[dict[str, Any]]:
    """Wan's FAQ bank as feed-shaped items: a READY answer that was given (not an AI guess, not flagged for a check) with the
    instrument it rests on, in a category that has a domain, that no idea has used. Never raises: no table is no FAQ."""
    try:
        rows = (store.table(FAQS).select("id,category,question_bm,question_en,raw_question,answer_bm,answer_en,instrument,"
                                         "answer_source,needs_check,status,created_at")
                .eq("status", "ready").eq("needs_check", False).order("created_at", desc=True).limit(FAQ_POOL)
                .execute().data or [])
        used = store.table(db.IDEAS).select("source_title,brief").eq("source_name", FAQ_SOURCE).execute().data or []
    except Exception as exc:  # noqa: BLE001
        log.info("faq candidates skipped: %s", str(exc)[:100])
        return []
    spent_ids = {str((u.get("brief") or {}).get("faq_id")) for u in used if isinstance(u.get("brief"), dict)}
    spent_titles = {str(u.get("source_title") or "").strip().lower() for u in used}
    out = []
    for r in rows:
        domain = FAQ_DOMAIN.get(str(r.get("category") or ""))
        question = str(r.get("question_bm") or r.get("question_en") or r.get("raw_question") or "").strip()
        answer = str(r.get("answer_bm") or r.get("answer_en") or "").strip()
        instrument = str(r.get("instrument") or "").strip()
        if (not domain or r.get("answer_source") == "ai" or not usable_title(question) or len(answer) < 40
                or len(instrument) < 4 or str(r["id"]) in spent_ids or question.lower() in spent_titles):
            continue
        out.append({"id": f"faq:{r['id']}", "section": "faq", "source": FAQ_SOURCE, "kind": "faq", "title": question,
                    "url": f"faq://{r['id']}", "summary": f"{answer}\n\nSumber: {instrument}", "why": None, "domain": domain,
                    "raw": {"faq_id": str(r["id"])}, "published_at": None, "created_at": r.get("created_at")})
    return out


class Focus:
    """Keeps one draft in every `every` on a focus topic, read from the latest auto-written ideas (brief.focus) so the share holds
    across runs. `prefer()` is what the next position should draw from (the topics, or None), `wrote()` records an idea."""

    def __init__(self, topics: list[str], every: int, recent: list[dict[str, Any]] | None = None) -> None:
        self.topics, self.every = set(topics), max(2, every)
        self.total = len(recent or [])
        self.focused = sum(1 for r in (recent or []) if isinstance((r.get("brief") or {}).get("focus"), str))

    def prefer(self) -> set[str] | None:
        return self.topics if self.topics and self.focused * self.every < self.total + 1 else None

    def wrote(self, item: dict[str, Any]) -> None:
        self.total += 1
        self.focused += int(topic_of(item) in self.topics)

    @classmethod
    def load(cls, store: Any, cfg: dict[str, Any]) -> Focus:
        recent: list[dict[str, Any]] = []
        if cfg.get("focus"):
            try:
                rows = (store.table(db.IDEAS).select("brief,created_at").order("created_at", desc=True).limit(60)
                        .execute().data or [])
                recent = [r for r in rows if isinstance(r.get("brief"), dict) and r["brief"].get("auto")][:FOCUS_WINDOW]
            except Exception as exc:  # noqa: BLE001
                log.info("focus share not read: %s", str(exc)[:100])
        return cls(cfg.get("focus") or [], int(cfg.get("focus_every") or FOCUS_EVERY), recent)


def candidates(store: Any, now: datetime | None = None, news: bool = False, faq: bool = False) -> list[dict[str, Any]]:
    """Feed items an idea has not used yet. A regulator's notice is fresh for FRESH_DAYS; the OneDrive angle bank is not news and
    has no age limit (its rows are written once, when a file is first read, and wait until they are used). Only OFFICIAL sections
    are read, and the newspaper headlines with them only when `news` is on (settings.autofill.news): facts first."""
    since = ((now or datetime.now(UTC)) - timedelta(days=FRESH_DAYS)).isoformat()
    rows = (store.table(WATCH).select(SELECT).eq("relevant", True).eq("dismissed", False).gte("created_at", since)
            .neq("section", "folder").order("created_at", desc=True).limit(200).execute().data or [])
    bank = (store.table(WATCH).select(SELECT).eq("section", "folder").eq("relevant", True).eq("dismissed", False)
            .order("created_at", desc=True).limit(300).execute().data or [])
    if not news:
        rows = [r for r in rows if r.get("section") in OFFICIAL_SECTIONS]            # no Reddit, YouTube, Threads or expert post
    rows = (news_candidates(store, now) if news else []) + rows + bank + (faq_candidates(store) if faq else [])
    # a row with no words to write from is no candidate: the OneDrive angle bank carried spreadsheet cells titled "40" and "0"
    # (25 Nov 2026), and the floor spent two of its first three ideas on them, each one failing "no fit" at the writer
    rows = [r for r in rows if usable_title(r.get("title"))]
    if not rows:
        return []
    urls = [r["url"] for r in rows]
    spent: set[str] = set()
    for chunk in db._in_filter_chunks(urls):
        spent |= {r.get("source_url") for r in (store.table(db.IDEAS).select("source_url").in_("source_url", chunk)
                                                .execute().data or [])}
    return one_per_story([r for r in rows if r["url"] not in spent], used_stories(store, now=now),
                         used_profiles(store, now=now))


# What an official announcement looks like in a title or a summary: a recall, a ban, a warning, a circular or a notice. Whole
# words only ("ban" is not "urban" or "bank").
ANNOUNCEMENT = re.compile(
    r"\b(?:recall(?:s|ed)?|tarik\s+balik|ditarik\s+balik|pembatalan|dibatalkan|cancell?ed|cancell?ation|ban(?:s|ned)?|larangan|dilarang|"
    r"diharamkan|warning|alert|amaran|circular|pekeliling|notice|notis|announcement|pengumuman|kenyataan\s+(?:media|akhbar)|"
    r"directive|direktif|penarikan|suspend(?:ed)?|digantung|penggantungan|enforcement|penguatkuasaan)\b", re.I)
# Official sections, best first: a regulator's own notice, a paper, an official website, MYRA's finding, Wan's own angle bank.
OFFICIAL_SECTIONS = ("regulatory", "publication", "website", "myra", "folder")


def is_announcement(item: dict[str, Any]) -> bool:
    """A notice from a regulator or the government (the regulator feed), as opposed to a paper, a website or an angle."""
    return item.get("section") == "regulatory"


def tier(item: dict[str, Any]) -> int:
    """0 an announcement that says what it is (recall, ban, warning, circular, notice); 1 any other regulator notice; 2 to 5 the
    other official sections in OFFICIAL_SECTIONS order; 6 a newspaper headline (only when Wan switched them on); 7 the rest."""
    section = item.get("section")
    if section == "regulatory":
        return 0 if ANNOUNCEMENT.search(f"{item.get('title') or ''} {item.get('summary') or ''}") else 1
    if section in OFFICIAL_SECTIONS:
        return 1 + OFFICIAL_SECTIONS.index(str(section))
    return 6 if section == "news" else 7


def age_of(item: dict[str, Any]) -> float:
    """Newest first sorts lowest: minus the item's created_at as a timestamp; an item with no readable date sorts last."""
    try:
        return -datetime.fromisoformat(str(item.get("created_at")).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return float("inf")


def rank_candidates(pool: list[dict[str, Any]], now: datetime | None = None) -> list[dict[str, Any]]:
    """Official first (Wan, 22 Nov 2026): a regulator's or the government's announcement, then its other notices, then official
    publications, websites and the angle bank; a newspaper headline only after every official item (and only when switched on).
    Newest first inside a tier, without inventing a viral score. An item with no section at all ranks last, announcements
    first among those."""

    def key(item: dict[str, Any]) -> tuple[int, int, float]:
        age = age_of(item)
        text = f"{item.get('title') or ''} {item.get('summary') or ''}"
        said = int(not (ANNOUNCEMENT.search(text) or item.get("regulatory_link"))) if tier(item) >= 6 else 0
        return (tier(item), said, age)
    return sorted(pool, key=key)


def pick(pool: list[dict[str, Any]], stream: str, allow: list[str] | None, day: str,
         prefer: set[str] | None = None) -> dict[str, Any] | None:
    """An urgent file for THIS date first (Studio's `urgent post/DDMMYY` override), then the first item that fits. `prefer` (the
    focus topics, when this position is due one) keeps only the fitting items on those topics, if there are any."""
    for x in pool:
        if (x.get("raw") or {}).get("urgent_for") == day:
            return x
    fitting = [x for x in pool if fits(x, stream, allow)]
    if prefer:
        fitting = [x for x in fitting if topic_of(x) in prefer] or fitting
    if stream == "linkedin":
        # the subject Wan wants most, then the best tier inside it, then the newest item
        return min(fitting, key=lambda x: (linkedin_subject(x), linkedin_tier(x), age_of(x)), default=None)
    return fitting[0] if fitting else None


# LinkedIn writes from FACTS in a guideline, a regulation or an official website (Wan, 20 Nov 2026: "for linkedn change direction
# to fact from guideline or official website rather than isu semasa viral"): the regulator feed, the papers, the websites Wan
# lists himself and his angle bank. A newspaper headline, another person's LinkedIn post and an expert's post are what is loud,
# not what is official, so they never fill a LinkedIn slot by themselves (Wan can still make an idea of any of them by hand).
LINKEDIN_SECTIONS = ("regulatory", "publication", "website", "folder")


# LinkedIn's own order (Wan, 23 Nov 2026: "for linkedn now, start scrape updated circular/guideline > existing guideline >
# research"): an UPDATED circular or guideline from a regulator first, then the other regulator notices, then the EXISTING
# guidelines (the official websites Wan lists, then his angle bank of reference documents), and a research paper last. ws.regulab
# keeps the order above.
UPDATED_GUIDELINE = re.compile(
    r"\b(?:guidelines?|garis\s+panduan|updated?|revis(?:ed|ion|ions)|amend(?:ed|ment|ments)|pindaan|dikemas\s*kini|dipinda|"
    r"circulars?|pekeliling|directives?|direktif|regulations?|peraturan)\b", re.I)
LINKEDIN_LATER = {"website": 2, "folder": 3, "publication": 4}


def linkedin_tier(item: dict[str, Any]) -> int:
    """0 an updated circular, guideline or other announcement by a regulator; 1 any other regulator notice; 2 an existing
    guideline on an official website; 3 the angle bank of reference documents; 4 a research paper; 5 anything else."""
    section = item.get("section")
    if section == "regulatory":
        text = f"{item.get('title') or ''} {item.get('summary') or ''}"
        return 0 if (ANNOUNCEMENT.search(text) or UPDATED_GUIDELINE.search(text)) else 1
    return LINKEDIN_LATER.get(str(section), 5)


# LinkedIn's subject order (Wan, 23 Nov 2026: "for linkedn, add more about halal>cosmetic>pharma>research"): halal first, then
# cosmetics, then pharmaceuticals, then research; any other subject (food, an unlabelled notice) after all four. It comes BEFORE
# the tier above, so a halal guideline on an official website beats an updated cosmetic circular; inside one subject the tier
# order and then the newest item still decide.
LINKEDIN_SUBJECTS = {"halal_my": 0, "fatwa": 0, "kosmetik": 1, "farmaseutikal": 2, "sains_kosmetik": 3}


def linkedin_subject(item: dict[str, Any]) -> int:
    """0 halal (and fatwa), 1 cosmetics, 2 pharmaceuticals, 3 research (a paper), 4 anything else."""
    if item.get("section") == "publication":
        return 3
    return LINKEDIN_SUBJECTS.get(str(item.get("domain") or ""), 4)


def linkedin_angle(item: dict[str, Any]) -> str:
    """The writer's angle: F for a paper, B (halal) for a halal or fatwa item, else A (a regulatory change)."""
    return "F" if item.get("section") == "publication" else ("B" if linkedin_subject(item) == 0 else "A")


def fits(item: dict[str, Any], stream: str, allow: list[str] | None) -> bool:
    if stream == "linkedin":
        return item.get("section") in LINKEDIN_SECTIONS
    dom = item.get("domain")
    if not allow:
        return True
    return dom in allow or dom in ANY_DAY_DOMAINS


def spend(pool: list[dict[str, Any]], item: dict[str, Any]) -> list[dict[str, Any]]:
    """The story leaves the pool whole, under every link."""
    key = story_key(item.get("title"))
    return [x for x in pool if x is not item and not (key and story_key(x.get("title")) == key)]


def write_idea(store: Any, brand: dict[str, Any], stream: str, item: dict[str, Any], date: str, slot: str,
               allow: list[str] | None) -> bool:
    """Write the idea (or, for a video slot, the waiting Motion film) FOR one position. True when it was a film."""
    domain = None
    urgent = (item.get("raw") or {}).get("urgent_for") == date
    if stream == "regulab":
        domain = item.get("domain") if item.get("domain") and (urgent or fits(item, stream, allow)) else None
        if allow and domain not in allow and domain not in ANY_DAY_DOMAINS and not urgent:
            domain = allow[0]
    fmt = slot_format(brand, stream, slot)
    if fmt == "video":
        store.table(MOTIONS).insert(film_row(item, stream, date, slot)).execute()
        return True
    fmt = auto_format(fmt)
    news = item.get("section") == "news"
    # facts first (22 Nov 2026): a regulator's or an official source's own words are "official"; only a newspaper
    # headline or a social post (both off unless Wan switched `news` on) is "current". An announcement by a regulator
    # or the government is flagged so the writer opens with who announced what and from when.
    faq = item.get("section") == "faq"
    official = item.get("section") in OFFICIAL_SECTIONS or faq               # an FAQ answer rests on its instrument
    brief = {"position": {"date": date, "slot": slot}, "auto": True, "watch_id": item["id"],
             "hook_required": True, "story_mode": True, "source_priority": "official" if official else "current"}
    topic = topic_of(item)
    if topic:
        brief["focus"] = topic                 # read back by Focus.load so the share of focus drafts holds across runs
    if faq:
        brief.pop("watch_id")                 # not a regulator-feed row: faq_id says where it came from
        brief["faq_id"] = (item.get("raw") or {}).get("faq_id")
    if is_announcement(item):
        brief["announcement"] = True
    if news:
        brief["relate_regulatory"] = True      # a newspaper story: a rule where a real one governs it
        brief.pop("watch_id")                 # not a regulator-feed row: trend_id says where it came from
        brief["news"] = True
    if fmt:
        brief["slot_format"] = fmt             # the rota's format for this slot, shown on the idea
    if fmt in ("carousel", "poster"):
        brief["format"] = fmt                  # a poster is ONE 4:5 artwork (ideas.format_of), not a slide set
    store.table(db.IDEAS).insert({
        **({"trend_id": item["trend_id"]} if news else {}),
        "source_title": str(item.get("title") or "")[:500], "source_url": None if faq else item["url"],
        "source_name": FAQ_SOURCE if faq else (item.get("source") or None),
        "source_summary": (str(item.get("summary") or item.get("why") or "")
                           + (f" (Rujukan dalam dokumen: {(item.get('raw') or {}).get('cite')})"
                              if (item.get("raw") or {}).get("cite") else ""))[:4000] or None,
        "stream": stream, "domain": domain,
        "angle": linkedin_angle(item) if stream == "linkedin" else None,
        "make_media": "image", "status": "new", "created_by": None,
        **({"make_slides": True} if fmt == "carousel" else {}),
        # no note: the writer reads a note as Wan's words, and a note also lifts the already-published
        # guard (ideas.process_idea). What this idea is for rides in the brief, shown as a pill.
        "note": "",
        "brief": brief,
    }).execute()
    return False


def waiting(store: Any, streams: list[str], now: datetime | None = None) -> int:
    """How many posts are waiting for Wan right now: drafts not yet approved, dated today or later, plus ideas the worker is
    still turning into drafts (they become drafts within this or the next run). Never raises: unreadable counts as full, so a
    failed read can never flood the queue."""
    today = ((now or datetime.now(UTC)) + MYT).date().isoformat()
    try:
        drafts = (store.table(db.POSTS).select("id,stream").eq("status", "draft").gte("date", today)
                  .in_("stream", streams).execute().data or [])
        ideas = (store.table(db.IDEAS).select("id,stream").in_("status", ["new", "working"])
                 .in_("stream", streams).execute().data or [])
    except Exception as exc:  # noqa: BLE001
        log.info("waiting drafts not counted (%s)", str(exc)[:120])
        return 10**6
    return len(drafts) + len(ideas)


def guideline_first(pool: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A guideline or a new circular from a regulator first (Wan, 25 Nov 2026), the rest in their existing order."""
    def guide(item: dict[str, Any]) -> int:
        text = f"{item.get('title') or ''} {item.get('summary') or ''}"
        return 0 if item.get("section") == "regulatory" and (UPDATED_GUIDELINE.search(text) or ANNOUNCEMENT.search(text)) else 1
    return sorted(pool, key=guide)


def fill_floor(store: Any, brand: dict[str, Any], streams: list[str], taken: dict[str, set[tuple[str, str]]],
               pool: list[dict[str, Any]], cfg: dict[str, Any], now: datetime | None = None,
               focus: Focus | None = None) -> tuple[int, int]:
    """Top the drafts waiting for Wan up to `min_drafts`, looking as far ahead as `floor_days` (the 25 Nov 2026 floor). Returns
    (ideas written, still short). Streams take turns, nearest free position first, the rota and each stream's own pick order kept;
    a guideline or a new circular from a regulator is drawn first. A video slot is skipped (a film waits for Start, it is no
    draft), a position with no fitting item is skipped for the next one, and nothing is approved, scheduled or posted."""
    short = cfg["min_drafts"] - waiting(store, streams, now)
    if short <= 0:
        return 0, 0
    pool = guideline_first(pool)
    reach = {s: [g for g in gaps(s, brand, taken.get(s, set()), cfg["floor_days"], now) if slot_format(brand, s, g[1]) != "video"]
             for s in streams}
    written = 0
    while short > 0 and any(reach.values()):
        for stream in streams:
            if short <= 0:
                break
            while reach[stream]:
                date, slot, allow = reach[stream].pop(0)
                item = pick(pool, stream, allow, date, focus.prefer() if focus else None)
                if not item:
                    continue
                pool = spend(pool, item)
                write_idea(store, brand, stream, item, date, slot, allow)
                if focus:
                    focus.wrote(item)
                taken.setdefault(stream, set()).add((date, slot))
                written += 1
                short -= 1
                break
    return written, max(0, short)


def run(store: Any, settings: dict[str, Any], now: datetime | None = None) -> str:
    cfg = config(settings, now)
    if not cfg["enabled"]:
        return "Autofill: off (switch it on in Settings)"
    try:
        # what the queue already holds: a full queue pauses new ideas and every post in it is a taken slot (None = unknown: carry
        # on). The queue read is the route's: Buffer's, or Zernio's while Zernio carries ws.regulab and Buffer is the idle backup
        # (Wan, 10 Nov 2026: the same pause applies to Zernio, against his own cap, since Zernio's plan has none)
        from . import publisher
        backup = publisher.buffer_is_backup(settings)
        queue = None
        if "regulab" in cfg["streams"]:
            if backup:
                buffer_queue.rest(store, settings, now)
                queue = buffer_queue.snapshot_zernio(store, settings, now)
            else:
                queue = buffer_queue.snapshot(store, settings, now)
        if queue and queue["is_full"]:
            streams = [s for s in cfg["streams"] if s != "regulab"]
            if not streams:
                return (f"Autofill: paused, the {queue.get('name', 'Buffer')} queue is full (" + ", ".join(queue["full"])
                        + f" at {queue['limit']}); ideas resume when a post goes out")
        else:
            streams = cfg["streams"]
        pool = rank_candidates(candidates(store, now, cfg["news"], "faq" in cfg["focus"]), now)
        focus = Focus.load(store, cfg)
        brand = settings.get("brand") or {}
        made, empty, films = 0, 0, 0
        taken: dict[str, set[tuple[str, str]]] = {}
        for stream in streams:
            busy = taken[stream] = held(store, stream, now) | asked_for(store, stream) | film_positions(store, stream)
            if stream == "regulab" and queue:
                busy |= {tuple(p) for p in queue["taken"]}
            for date, slot, allow in gaps(stream, brand, busy, cfg["days_ahead"], now):
                if made >= cfg["per_run"]:
                    break
                item = pick(pool, stream, allow, date, focus.prefer())
                if not item:
                    empty += 1
                    continue
                pool = spend(pool, item)
                if write_idea(store, brand, stream, item, date, slot, allow):
                    films += 1
                focus.wrote(item)
                busy.add((date, slot))
                made += 1
        floored, short = 0, 0
        if cfg["min_drafts"]:
            floored, short = fill_floor(store, brand, streams, taken, pool, cfg, now, focus)
        if made or floored:
            db.log_event(store, "info", "idea", "idea.autofill",
                         f"{made - films + floored} idea ditulis untuk slot kosong (auto-isi); draf menunggu kelulusan"
                         + (f"; {films} filem Motion menunggu Start untuk slot video" if films else "")
                         + (f"; {floored} untuk lantai {cfg['min_drafts']} draf menunggu" if floored else ""),
                         detail={"made": made - films, "films": films, "no_fitting_item": empty, "floor": floored,
                                 "floor_short": short})
        return (f"Autofill: {made - films} idea(s) written for empty slots"
                + (f"; {films} Motion film(s) waiting for Start" if films else "")
                + (f"; {empty} gap(s) had no fitting item" if empty else "")
                + (f"; floor: {floored} idea(s) so {cfg['min_drafts']} drafts are waiting" if floored else "")
                + (f"; still {short} short of {cfg['min_drafts']} waiting drafts (nothing fitting in the next "
                   f"{cfg['floor_days']} days)" if short else ""))
    except Exception as exc:  # noqa: BLE001 - a missing table or setting must not stop the worker
        log.warning("autofill skipped: %s", exc)
        return f"Autofill: skipped ({str(exc)[:120]})"
