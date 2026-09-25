"""Flow A — headline → idea → post draft (+ the pictures it asks for).

Wan presses "Jadikan idea" on a headline (or writes one by hand); that inserts a
`semasa_ideas` row with status `new`. This module, run at the start of every media run:

  1. READS the source: the article page itself where it can be fetched (title, description,
     the main paragraphs, the page's own picture), otherwise the headline and summary alone —
     and says which, so a draft written from a headline never passes for one written from
     the article.
  2. WRITES a draft in the stream's voice (ws.regulab: BM-mix to SMEs; LinkedIn: a named
     chemist in English), under Studio's rules, and runs the same compliance scan the page
     runs. The draft is a DRAFT: nothing here approves, schedules or posts anything.
  3. Queues the pictures: the page's picture is READ and drawn afresh (never copied: see
     media_generator), Wan's own attached references are recreated, and with no picture at
     all one is drawn from the writer's visual description.
  4. Places the draft on the next free position on the rota — a suggestion Wan can move.
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from . import compliance, db, slides
from .fetch import get
from .llm import LLM
from .log import get_logger

log = get_logger("semasa.ideas")

MYT = timedelta(hours=8)
STALE_MINUTES = 30
CATEGORY_TO_DOMAIN = {"kosmetik": "kosmetik", "halal": "halal_my", "makanan": "makanan",
                      "farmaseutikal": "farmaseutikal", "kesihatan": "farmaseutikal"}
DOMAINS = ["kosmetik", "makanan", "halal_my", "farmaseutikal", "fatwa", "kajian_kes", "sains_kosmetik"]
ANGLES = list("ABCDEFG")
SOURCE_TEXT_MAX = 6000


class IdeaError(RuntimeError):
    """A failure the page should show on the idea."""


# --- reading ---------------------------------------------------------------------

def read_source(url: str | None, *, timeout: int = 20) -> dict[str, Any]:
    """What the page actually says. `ok` False means the draft is written from the headline."""
    out: dict[str, Any] = {"ok": False, "url": url, "title": "", "description": "", "image": None, "text": ""}
    if not url:
        out["why"] = "no link"
        return out
    host = urlparse(url).netloc.lower()
    if host.endswith("news.google.com"):
        # Google News RSS links open through a script redirect a plain fetch cannot follow
        out["why"] = "Google News link: the article behind it cannot be fetched without a browser"
        return out
    try:
        r = get(url, timeout=timeout, retries=1)
    except Exception as exc:  # noqa: BLE001
        out["why"] = f"could not fetch: {type(exc).__name__}: {str(exc)[:160]}"
        return out
    return parse_article(r.text, r.url or url, out)


FAQ_SOURCE = "FAQ Semasa"      # web/src/lib/brand.js: an idea made from an FAQ entry ("Jadikan post" in the FAQ tab)


def faq_source(idea: dict[str, Any]) -> dict[str, Any] | None:
    """An idea made from an FAQ has no page to read: its answer IS the source, so the writer works from it rather than
    treating it as a bare headline. None for any other idea."""
    if idea.get("source_name") != FAQ_SOURCE or idea.get("source_url"):
        return None
    text = str(idea.get("source_summary") or "").strip()
    return {"ok": bool(text), "url": None, "title": str(idea.get("source_title") or ""), "description": "",
            "image": None, "text": text[:SOURCE_TEXT_MAX], "label": "an entry of Wan's own FAQ",
            **({} if text else {"why": "the FAQ entry had no answer"})}


def parse_article(html: str, base_url: str, out: dict[str, Any] | None = None) -> dict[str, Any]:
    out = out or {"ok": False, "url": base_url, "title": "", "description": "", "image": None, "text": ""}
    soup = BeautifulSoup(html, "lxml")

    def meta(*names: str) -> str:
        for n in names:
            tag = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n})
            if tag and tag.get("content"):
                return str(tag["content"]).strip()
        return ""

    out["title"] = meta("og:title", "twitter:title") or (soup.title.string.strip() if soup.title and soup.title.string else "")
    out["description"] = meta("og:description", "description", "twitter:description")
    img = meta("og:image", "og:image:url", "twitter:image")
    out["image"] = urljoin(base_url, img) if img else None
    for bad in soup(["script", "style", "nav", "footer", "header", "aside", "form", "noscript"]):
        bad.decompose()
    root = soup.find("article") or soup.body or soup
    paras = [re.sub(r"\s+", " ", p.get_text(" ", strip=True)) for p in root.find_all("p")]
    paras = [p for p in paras if len(p) > 60]
    out["text"] = "\n".join(paras)[:SOURCE_TEXT_MAX]
    out["ok"] = bool(out["text"])
    if not out["ok"]:
        out["why"] = "the page carried no readable paragraphs"
    return out


# --- writing ---------------------------------------------------------------------

REGULAB_SYSTEM = """You write social posts for ws.regulab, a Malaysian regulatory-affairs brand speaking to SME owners
(cosmetics, food, halal, pharmaceuticals). Voice: Bahasa Malaysia mixed naturally with English technical terms, warm,
plain, practical. MALAYSIAN Malay only, never Bahasa Indonesia: boleh not bisa, ubat not obat, syarikat not perusahaan,
kualiti not kualitas, pembungkusan not kemasan, kebenaran not izin.

Rules. Breaking any of them blocks the post, so follow them exactly:
1. No call to action of any kind: no "hubungi kami", "komen", "simpan post", "kongsi", "follow/ikuti", "DM/PM",
   "link in bio", "klik link", "semak kelayakan". End on the substance.
2. No website or URL in any caption, least of all kkmhalalconsultant.com.
3. Never say where the idea came from: no Reddit, YouTube, TikTok, forum, subreddit, and do not name the news portal.
   The post stands on the regulator and the instrument.
4. Facts: no fee, duration, circular, entry number, date or figure unless it is in the SOURCE below. Where one is
   needed and the source does not give it, write [SAHKAN: <the exact missing fact, and where it would be found>].
   Never write "[SAHKAN: what to verify]" or an empty [SAHKAN].
5. No em dash. Do not open with "Tahukah anda". No superlatives, no promise of approval, no "tiada kesan sampingan",
   no "halal-friendly" or "patuh syariah" claims.
6. A fatwa post says whether the fatwa is diwartakan, and where.
7. Lengths: instagram up to 2200 characters (aim about 900) with at most 8 hashtags; facebook aim about 500 with at
   most 3 hashtags; threads at most 500 characters with at most 1 hashtag.
8. The citation names the regulator and the instrument (for example "NPRA, Guidelines for Control of Cosmetic Products
   in Malaysia"), never a news portal, blog or social platform. If only a news report supports a fact, use
   [SAHKAN: primary source for <that fact>].

Answer with ONE JSON object:
{"fit": true or false, "why_not": "", "hook": "the first line", "domain": one of %s,
 "citation": "...", "text": {"bm": {"instagram": "...", "facebook": "...", "threads": "..."},
                             "en": {"instagram": "...", "facebook": "...", "threads": "..."}},
 "visual_prompt": "an English description of one illustrative picture: no words, no logos, no real people",
 "alt": "short alt text in BM"}
Set "fit" false (and say why in "why_not") only when the story gives nothing a regulatory-affairs audience can use."""

LINKEDIN_SYSTEM = """You write a LinkedIn post for Ts. ChM Muhammad Ridzuan, a registered chemist and senior
regulatory-affairs specialist, writing in his own name to peers (formulators, RA people, brand owners).
Hook on line one. One idea. A concrete example (ingredient, Annex entry, real figure). Short paragraphs of one or
two sentences. 120 to 220 words. Casual-professional, human. Citations below the body, never inside it. End on a
statement that lands, never a question. 3 to 5 hashtags. No em dash.

Rules. Breaking any blocks the post:
1. No company identity at all: never mention ws.regulab, KKM Halal Consultant or any website.
2. No call to action (no "comment below", "follow", "DM me", "share this", "link in bio").
3. Cite the INSTRUMENT (e.g. EC 1223/2009 Annex III entry 325, SI 2026/109, ISO 24444, a WTO TBT number), never a
   blog or aggregator (ChemLinked, CIRS, CosmeticsDesign, Chemical Watch, Happi and the like), never a news portal.
4. No fact without a source in the SOURCE below; otherwise [SAHKAN: <the exact missing fact, and where to find it>].
   Never "[SAHKAN: what to verify]".
5. Never say the idea came from Reddit, YouTube, TikTok or a forum.

Angles: %s

Answer with ONE JSON object:
{"fit": true or false, "why_not": "", "hook": "the first line", "angle": one letter from the list,
 "citation": "...", "text": {"en": {"linkedin": "..."}, "bm": {"linkedin": "the same post in Malaysian Malay"}},
 "visual_prompt": "an English description of one illustrative picture: no words, no logos, no real people",
 "alt": "short alt text in English"}
Set "fit" false (and say why) only when the story gives a regulatory professional nothing to use."""


SLIDES_RULES = {
    "regulab": """

SLIDES WANTED. Also return "slides": a carousel of 5 to 7 slides in Malaysian Malay, drawn as 1080x1080 cards:
[{"title": "...", "points": ["...", "..."]}, ...]
- Slide 1 is the cover: a headline of at most 9 words, "points" empty or one short line.
- Each middle slide carries ONE fact: a title of at most 8 words and at most 3 points of at most 20 words each.
- The last slide is the takeaway, stated plainly. It is NOT a call to action.
- Mark the one key word of a title with *asterisks* for emphasis, at most once per title.
- Every rule above applies to every slide: no call to action, no URL or website, no news portal or social source,
  and [SAHKAN: <the exact missing fact>] where a fact is not in the SOURCE. The source line is added to the last
  slide from "citation" automatically, so do not write it into a slide.""",
    "linkedin": """

SLIDES WANTED. Also return "slides": a carousel of 5 to 7 slides in English, drawn as 1080x1350 cards:
[{"title": "...", "points": ["...", "..."]}, ...]
- Slide 1 is the cover: a headline of at most 10 words, "points" empty or one short line.
- Each middle slide carries ONE idea: a title of at most 9 words and at most 3 points of at most 22 words each.
- The last slide is the takeaway. Never a question, never a call to action.
- Mark the one key word of a title with *asterisks* for emphasis, at most once per title.
- No company identity, no URL, no blog or aggregator, and [SAHKAN: <the exact missing fact>] where the SOURCE does
  not give a fact. The citation is added to the last slide automatically.""",
}


def build_request(idea: dict[str, Any], source: dict[str, Any], brand: dict[str, Any],
                  avoid: str = "") -> tuple[str, str]:
    stream = idea.get("stream") or "regulab"
    if stream == "linkedin":
        angles = (brand.get("linkedin") or {}).get("angles") or {}
        system = LINKEDIN_SYSTEM % "; ".join(f"{k} = {v}" for k, v in sorted(angles.items()))
    else:
        system = REGULAB_SYSTEM % DOMAINS
    lines = [
        f"HEADLINE: {idea.get('source_title') or ''}",
        f"PUBLISHER: {idea.get('source_name') or ''} (for your understanding only; never name it in the post)",
        f"SUMMARY: {idea.get('source_summary') or ''}",
    ]
    if idea.get("domain"):
        lines.append(f"DOMAIN WANTED: {idea['domain']}")
    if idea.get("angle"):
        lines.append(f"ANGLE WANTED: {idea['angle']}")
    if (idea.get("note") or "").strip():
        lines.append(f"WHAT WAN WANTS FROM THIS: {idea['note'].strip()}")
    if source.get("ok"):
        lines.append(f"SOURCE ({source.get('label') or 'the article itself'}):\n{source.get('title') or ''}\n"
                     f"{source.get('description') or ''}\n{source.get('text') or ''}")
    else:
        lines.append("SOURCE: only the headline and summary above could be read "
                     f"({source.get('why') or 'no article'}). Every specific fact beyond them needs [SAHKAN: …].")
    return system + avoid, "\n\n".join(lines)


def normalise_text(raw: Any, stream: str, lang: str) -> dict[str, dict[str, str]]:
    """Force Studio's shape text[lang][platform]. A platform-keyed answer goes under `lang`;
    a platform key that is not this stream's is dropped rather than left where nothing reads it."""
    plats = compliance.platforms_for(stream)
    out: dict[str, dict[str, str]] = {}
    if not isinstance(raw, dict):
        return out
    if any(k in plats for k in raw):
        raw = {lang: raw}
    for lg in ("bm", "en"):
        inner = raw.get(lg)
        if isinstance(inner, dict):
            kept = {p: str(inner[p]).strip() for p in plats if isinstance(inner.get(p), str) and inner[p].strip()}
            if kept:
                out[lg] = kept
        elif isinstance(inner, str) and inner.strip() and len(plats) == 1:
            out[lg] = {plats[0]: inner.strip()}
    return out


# --- placing ---------------------------------------------------------------------

def next_free_position(stream: str, domain: str | None, brand: dict[str, Any], taken: set[tuple[str, str]],
                       now: datetime | None = None, horizon_days: int = 28) -> tuple[str | None, str | None]:
    """The first date+slot, from tomorrow (Malaysia time), that this stream posts on and nobody holds.
    ws.regulab also needs the rota to carry the domain that day."""
    cfg = brand.get(stream) or {}
    slots = sorted(cfg.get("slots") or (["08:00", "13:00", "21:00"] if stream == "regulab" else ["06:00"]))
    today = ((now or datetime.now(UTC)) + MYT).date()
    for i in range(1, horizon_days + 1):
        d = today + timedelta(days=i)
        dow = (d.weekday() + 1) % 7
        if stream == "regulab":
            allow = (cfg.get("schedule") or {}).get(str(dow))
            if allow is not None and not allow:
                continue                                  # a no-posting day
            if domain and allow and domain not in allow:
                continue
        else:
            days = cfg.get("days")
            if days and dow not in days:
                continue
        for slot in slots:
            if (d.isoformat(), slot) not in taken:
                return d.isoformat(), slot
    return None, None


# --- the worker --------------------------------------------------------------------

def load_settings(store: Any) -> dict[str, Any]:
    try:
        rows = store.table(db.SETTINGS).select("key,value").execute().data or []
        return {r["key"]: r["value"] for r in rows}
    except Exception as exc:  # noqa: BLE001
        log.warning("could not read semasa_settings: %s", exc)
        return {}


def taken_positions(store: Any, stream: str) -> set[tuple[str, str]]:
    today = (datetime.now(UTC) + MYT).date().isoformat()
    rows = (store.table(db.POSTS).select("date,slot,status").eq("stream", stream).gte("date", today)
            .neq("status", "rejected").execute().data or [])
    return {(str(r["date"]), r["slot"]) for r in rows if r.get("date") and r.get("slot")}


def recover_stale(store: Any) -> int:
    cutoff = (datetime.now(UTC) - timedelta(minutes=STALE_MINUTES)).isoformat()
    try:
        res = (store.table(db.IDEAS).update({"status": "new", "error": "worker stopped before finishing; queued again"})
               .eq("status", "working").lt("updated_at", cutoff).execute())
        return len(res.data or [])
    except Exception as exc:  # noqa: BLE001
        log.warning("could not recover stuck ideas: %s", exc)
        return 0


def claim(store: Any, limit: int) -> list[dict[str, Any]]:
    rows = store.table(db.IDEAS).select("*").eq("status", "new").order("created_at").limit(limit).execute().data or []
    got = []
    for row in rows:
        res = (store.table(db.IDEAS).update({"status": "working", "attempts": int(row.get("attempts") or 0) + 1,
                                              "error": None})
               .eq("id", row["id"]).eq("status", "new").execute())
        if res.data:
            got.append(res.data[0])
    return got


PUBLISHED = ("approved", "scheduled", "posted")


def already_published(store: Any, idea: dict[str, Any]) -> dict[str, Any] | None:
    """The approved or published post already written from the same news for the same stream, if any (Wan, 25 Sep
    2026: a posted story is never recreated as another draft). Never raises: a failed look-up blocks nothing."""
    try:
        stream = idea.get("stream") or "regulab"
        ids: set[str] = set()
        for col in ("trend_id", "source_url"):
            if idea.get(col):
                rows = (store.table(db.IDEAS).select("id,stream").eq(col, idea[col]).neq("id", idea["id"])
                        .execute().data or [])
                ids |= {r["id"] for r in rows if (r.get("stream") or "regulab") == stream}
        if not ids:
            return None
        posts = (store.table(db.POSTS).select("id,status,date,hook,idea_id").in_("idea_id", sorted(ids))
                 .in_("status", list(PUBLISHED)).execute().data or [])
        return posts[0] if posts else None
    except Exception as exc:  # noqa: BLE001
        log.info("could not check for an earlier post (%s)", str(exc)[:100])
        return None


def process_idea(store: Any, llm: LLM, idea: dict[str, Any], settings: dict[str, Any]) -> str:
    """Returns the new post id. Raises IdeaError with a message for the page."""
    if not llm.configured:
        raise IdeaError(llm.why_off())
    earlier = already_published(store, idea)
    if earlier and not str(idea.get("note") or "").strip():
        raise IdeaError(f"this news already has a {earlier['status']} post for this stream "
                        f"({earlier.get('hook') or earlier.get('date') or earlier['id']}), so it is not written again. "
                        "For a follow-up, add a note saying what the new post should say, then Cuba lagi.")
    brand = settings.get("brand") or {}
    indo_extra = (settings.get("bahasa") or {}).get("indo")
    stream = idea.get("stream") or "regulab"
    lang = "en" if stream == "linkedin" else "bm"
    source = faq_source(idea) or read_source(idea.get("source_url"))
    system, user = build_request(idea, source, brand, avoid=compliance.avoid_line(indo_extra))
    want_slides = bool(idea.get("make_slides"))
    if want_slides:
        system += SLIDES_RULES.get(stream, SLIDES_RULES["regulab"])
    out = llm.chat_json(system, user, max_tokens=5000 if want_slides else 3500)
    if not out:
        raise IdeaError("the writer did not answer (see the run log); press Cuba lagi")
    if out.get("fit") is False:
        raise IdeaError(f"the writer judged this headline no fit for {stream}: {str(out.get('why_not') or '')[:300]}. "
                        "Add a note saying what you want from it, then Cuba lagi.")
    text = normalise_text(out.get("text"), stream, lang)
    if not text.get(lang):
        raise IdeaError(f"the writer returned no {lang.upper()} caption")
    domain = idea.get("domain") or (out.get("domain") if out.get("domain") in DOMAINS else None)
    angle = idea.get("angle") or (out.get("angle") if out.get("angle") in ANGLES else None)
    if stream == "linkedin":
        domain = None
    date, slot = next_free_position(stream, domain, brand, taken_positions(store, stream))
    post = {
        "idea_id": idea["id"], "stream": stream, "domain": domain, "angle": angle, "lang": lang,
        "hook": str(out.get("hook") or "")[:300], "text": text, "citation": str(out.get("citation") or "")[:1000],
        "date": date, "slot": slot, "status": "draft", "created_by": idea.get("created_by"),
    }
    if want_slides:
        # only when asked: the column arrives with 006_slides.sql, and an idea that never asked
        # for slides must still be written on a database that has not run it
        post["slides"] = slides.normalise(out.get("slides"))
    reg = brand.get("regulab") or {}
    flags = compliance.scan({**post, "media": []}, brand=reg, schedule=reg.get("schedule"),
                            indo_extra=indo_extra)
    post["flags"] = flags
    post["hard_flags"] = compliance.hard_count(flags)
    post_id = store.table(db.POSTS).insert(post).execute().data[0]["id"]

    jobs = media_jobs(idea, source, out, post_id)
    if want_slides and post.get("slides"):
        jobs.append(slide_job(idea, post, post_id, bg="post_image" if jobs else "none"))
    if jobs:
        store.table(db.MEDIA).insert(jobs).execute()
    brief = {"source": {k: source.get(k) for k in ("ok", "why", "url", "title", "image")},
             "post_id": post_id, "media_jobs": len(jobs), "written_at": datetime.now(UTC).isoformat(),
             "model": getattr(llm, "last_model", "") or llm.s.model}
    store.table(db.IDEAS).update({"status": "drafted", "brief": brief, "error": None}).eq("id", idea["id"]).execute()
    return post_id


def slide_job(idea: dict[str, Any], post: dict[str, Any], post_id: str, bg: str = "none") -> dict[str, Any]:
    """One render job for the whole carousel, carrying a snapshot of the words. Queued after the
    picture jobs, so a picture made in the same run can be the slides' background."""
    return {"idea_id": idea["id"], "post_id": post_id, "type": "image", "mode": "slides", "status": "pending",
            "prompt": "", "created_by": idea.get("created_by"),
            "meta": {"flow": "A", "slides": post.get("slides") or [], "stream": post.get("stream"),
                     "citation": post.get("citation") or "", "domain": post.get("domain"),
                     "angle": post.get("angle"), "bg": bg}}


def media_jobs(idea: dict[str, Any], source: dict[str, Any], out: dict[str, Any], post_id: str) -> list[dict[str, Any]]:
    kind = idea.get("make_media") or "image"
    if kind == "none":
        return []
    visual = str(out.get("visual_prompt") or "").strip()
    alt = str(out.get("alt") or "").strip()
    base = {"idea_id": idea["id"], "post_id": post_id, "type": kind, "status": "pending",
            "created_by": idea.get("created_by")}
    jobs: list[dict[str, Any]] = []
    for ref in idea.get("reference_urls") or []:          # Wan's own references: recreate them
        jobs.append({**base, "mode": "recreate", "reference_url": ref, "prompt": visual,
                     "meta": {"flow": "A-own", "alt": alt}})
    if not jobs and source.get("image"):                   # the article's picture: read, then draw afresh
        jobs.append({**base, "mode": "recreate", "reference_url": source["image"], "prompt": visual,
                     # og:image is a picture by definition, though its address often has no extension
                     "meta": {"flow": "A", "alt": alt, "mime": "image/og"}})
    if not jobs and visual:
        jobs.append({**base, "mode": "prompt", "prompt": visual, "meta": {"flow": "A", "alt": alt}})
    return jobs


def run(store: Any, llm: LLM, limit: int | None = None) -> str:
    limit = limit or int(os.environ.get("IDEAS_BATCH") or 3)
    recovered = recover_stale(store)
    try:
        ideas = claim(store, limit)
    except Exception as exc:  # noqa: BLE001 - a missing table (005 not run) must not stop media
        log.warning("ideas step skipped: %s", exc)
        return f"Ideas: skipped ({str(exc)[:120]})"
    if not ideas:
        return "Ideas: none waiting" + (f"; {recovered} stuck idea(s) re-queued" if recovered else "")
    settings = load_settings(store)
    ok = 0
    for idea in ideas:
        try:
            pid = process_idea(store, llm, idea, settings)
            ok += 1
            log.info("idea %s → post %s", idea["id"], pid)
        except Exception as exc:  # noqa: BLE001 - recorded on the idea
            msg = str(exc) if isinstance(exc, IdeaError) else f"{type(exc).__name__}: {str(exc)[:400]}"
            log.error("idea %s: %s", idea["id"], msg)
            store.table(db.IDEAS).update({"status": "error", "error": msg[:800]}).eq("id", idea["id"]).execute()
    return f"Ideas: {ok}/{len(ideas)} written as drafts"
