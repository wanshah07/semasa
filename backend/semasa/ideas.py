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

from . import compliance, db, my_designs, slides
from .fetch import get
from .llm import LLM
from .log import get_logger

log = get_logger("semasa.ideas")

MYT = timedelta(hours=8)
STALE_MINUTES = 30
CATEGORY_TO_DOMAIN = {"kosmetik": "kosmetik", "halal": "halal_my", "makanan": "makanan",
                      "farmaseutikal": "farmaseutikal", "kesihatan": "farmaseutikal"}
# a case study is a FORMAT, not a subject (Studio, 22 Sep 2026: "make sure everyday got case study"): any posting day
# takes one, whatever pair the rota gives that day. web/src/lib/slots.js carries the same list.
ANY_DAY_DOMAINS = {"kajian_kes"}
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
    if "pdf" in (r.headers.get("content-type") or "").lower() or r.content[:5] == b"%PDF-":
        # a regulator's circular or directive is often a PDF (pasted in Regulatory, then made an idea)
        from .watch import pdf_text
        try:
            out["title"], out["text"] = pdf_text(r.content, SOURCE_TEXT_MAX)
        except Exception as exc:  # noqa: BLE001
            out["why"] = f"the PDF could not be read: {type(exc).__name__}: {str(exc)[:160]}"
            return out
        out["ok"] = bool(out["text"])
        if not out["ok"]:
            out["why"] = "the PDF has no text layer (a scan)"
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


STORED_SCHEMES = ("onedrive://", "myra://")
STORED_HOSTS = ("reddit.com", "youtube.com", "youtu.be")


def stored_source(idea: dict[str, Any]) -> dict[str, Any] | None:
    """An idea made from Wan's own sources (supabase/024): a Reddit thread or YouTube video, a file in his OneDrive
    library, a finding in MYRA's sheet with no link. None of them has a page the writer should fetch (Reddit and YouTube
    refuse the fetch, and their addresses must never reach a post; the others are not web addresses), so the row's own
    words are the source, exactly as an FAQ entry's answer is. The address is withheld from the writer on purpose."""
    url = str(idea.get("source_url") or "")
    host = urlparse(url).netloc.lower()
    if not (url.startswith(STORED_SCHEMES) or any(host == h or host.endswith("." + h) for h in STORED_HOSTS)):
        return None
    text = str(idea.get("source_summary") or "").strip()
    label = ("an argument people are having in public (never name the platform, a subreddit, a channel or a person)"
             if not url.startswith(STORED_SCHEMES) else "an angle from Wan's own reference library")
    return {"ok": bool(text), "url": None, "title": str(idea.get("source_title") or ""), "description": "",
            "image": None, "text": text[:SOURCE_TEXT_MAX], "label": label,
            **({} if text else {"why": "the row carried no summary"})}


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
4. Facts: no fee, duration, circular, entry number, date or figure unless it is in the SOURCE below. If the source
   does not give one, leave it out and write around it: never guess one, and never write a placeholder or a note in
   brackets.
5. No em dash. Do not open with "Tahukah anda". No superlatives, no promise of approval, no "tiada kesan sampingan",
   no "halal-friendly" or "patuh syariah" claims.
6. A fatwa post says whether the fatwa is diwartakan, and where.
7. Lengths: instagram up to 2200 characters (aim about 900) with at most 8 hashtags; facebook aim about 500 with at
   most 3 hashtags; threads at most 500 characters with at most 1 hashtag.
8. The citation names the regulator and the instrument (for example "NPRA, Guidelines for Control of Cosmetic Products
   in Malaysia"), never a news portal, blog or social platform. If only a news report supports a fact, leave that
   fact out.

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
4. No fact without a source in the SOURCE below: a fact it does not give is left out, never guessed, and never
   replaced by a placeholder or a note in brackets.
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
  and no fact that is not in the SOURCE. The source line is added to the last
  slide from "citation" automatically, so do not write it into a slide.""",
    "linkedin": """

SLIDES WANTED. Also return "slides": a carousel of 5 to 7 slides in English, drawn as 1080x1350 cards:
[{"title": "...", "points": ["...", "..."]}, ...]
- Slide 1 is the cover: a headline of at most 10 words, "points" empty or one short line.
- Each middle slide carries ONE idea: a title of at most 9 words and at most 3 points of at most 22 words each.
- The last slide is the takeaway. Never a question, never a call to action.
- Mark the one key word of a title with *asterisks* for emphasis, at most once per title.
- No company identity, no URL, no blog or aggregator, and no fact the SOURCE does not give. The citation is added
  to the last slide automatically.""",
}


POSTER_RULES = {
    "regulab": """

POSTER WANTED. Also return "poster": ONE 4:5 poster in Malaysian Malay: {"title": "a headline of at most 10 words",
"points": [up to 5 points of at most 22 words each]}. Mark the one key word of the title with *asterisks*. The same
rules apply to every word: no call to action, no URL, no fact the SOURCE does not give.
The citation is drawn at its foot automatically.""",
    "linkedin": """

POSTER WANTED. Also return "poster": ONE 4:5 poster in English: {"title": "a headline of at most 10 words",
"points": [up to 5 points of at most 22 words each]}. Mark the one key word of the title with *asterisks*. No
company identity, no URL, no blog or aggregator, no fact the SOURCE does not give. The
citation is drawn at its foot automatically.""",
}


def format_of(idea: dict[str, Any]) -> str:
    """What the idea should become besides its caption: 'post' (a picture), 'carousel' (slides) or 'poster' (one 4:5
    artwork). make_slides (006) still means a carousel; the choice itself rides in the idea's brief."""
    fmt = str(((idea.get("brief") or {}) if isinstance(idea.get("brief"), dict) else {}).get("format") or "")
    if fmt in ("carousel", "poster"):
        return fmt
    return "carousel" if idea.get("make_slides") else "post"


# Studio's pillars: what KIND of post it is, named by the writer (settings "writer".regulab.pillars, per domain)
PILLAR_HINT = {
    "kajian_kes": "a real case: what happened to a product or company and what the rule did about it",
    "mitos": "a common belief corrected against the instrument", "urutan": "the steps in order",
    "silap": "a mistake people make, and the right way",
    "kos_tempoh": "what it costs or how long it takes (sourced figures only)",
    "dokumen": "the documents needed", "soal_jawab": "one real question answered",
    "kajian_sains": "a new paper and what it found",
}


def pillars_for(writer: dict[str, Any] | None, stream: str, domain: str | None) -> list[str]:
    w = ((writer or {}).get(stream) or {}) if isinstance(writer, dict) else {}
    table = w.get("pillars") if isinstance(w, dict) and isinstance(w.get("pillars"), dict) else {}
    got = table.get(domain or "") if domain else sorted({p for v in table.values() if isinstance(v, list) for p in v})
    return [str(p) for p in (got or []) if re.fullmatch(r"[a-z_]{2,30}", str(p))][:12]


def pillar_line(writer: dict[str, Any] | None, stream: str, domain: str | None) -> str:
    opts = pillars_for(writer, stream, domain)
    if not opts:
        return ""
    return ("\n- PILLAR: the post is ONE of these kinds; write it as that kind and name it in \"pillar\": "
            + "; ".join(f"{p} = {PILLAR_HINT.get(p, p)}" for p in opts))


def writer_block(writer: dict[str, Any] | None, stream: str) -> str:
    """Wan's own words for the writer, from Settings (Studio's voice, never-list and hashtag lists; 021). Empty
    settings add nothing: the rules above still hold. These can only add to the rules, never lift one."""
    w = ((writer or {}).get(stream) or {}) if isinstance(writer, dict) else {}
    if not isinstance(w, dict):
        return ""
    lines: list[str] = []
    # Semasa has no [SAHKAN] marker and nothing looks for one (Wan, 26 Sep 2026): a Settings line asking for it would
    # put markers into drafts that pass approval unseen, so such a line is never handed to the writer.
    ok = lambda x: "sahkan" not in str(x).lower()  # noqa: E731
    if str(w.get("voice") or "").strip() and ok(w.get("voice")):
        lines.append(f"VOICE (Wan's words, follow them): {str(w['voice']).strip()[:1200]}")
    never = [str(x).strip() for x in (w.get("never") or []) if str(x).strip() and ok(x)][:30]
    if never:
        lines.append("NEVER write: " + "; ".join(never))
    tags = [str(x).strip() for x in (w.get("hashtags_core") or w.get("hashtags") or []) if str(x).strip()][:12]
    if tags:
        lines.append("HASHTAGS to use (within each platform's limit): " + " ".join(tags))
    rot = [str(x).strip() for x in (w.get("hashtags_rotate") or []) if str(x).strip()][:20]
    if rot:
        lines.append("ROTATE one or two of these as fits the story: " + " ".join(rot))
    if stream == "regulab" and str(w.get("fatwa_warning") or "").strip() and ok(w.get("fatwa_warning")):
        lines.append("A FATWA post carries this line word for word: " + str(w["fatwa_warning"]).strip()[:400])
    if not lines:
        return ""
    return "\n\nHOUSE STYLE (from Settings). It adds to the rules above and never lifts one:\n- " + "\n- ".join(lines)


def build_request(idea: dict[str, Any], source: dict[str, Any], brand: dict[str, Any],
                  avoid: str = "", writer: dict[str, Any] | None = None) -> tuple[str, str]:
    stream = idea.get("stream") or "regulab"
    if stream == "linkedin":
        angles = (brand.get("linkedin") or {}).get("angles") or {}
        system = LINKEDIN_SYSTEM % "; ".join(f"{k} = {v}" for k, v in sorted(angles.items()))
    else:
        system = REGULAB_SYSTEM % DOMAINS
    from . import watch
    issuer = watch.is_issuer(idea.get("source_name"))
    lines = [
        f"HEADLINE: {idea.get('source_title') or ''}",
        (f"ISSUER: {idea.get('source_name')} (the regulator or the journal itself: cite it by name, with the notice's "
         "reference or the paper's authors, journal, year and DOI)" if issuer else
         f"PUBLISHER: {idea.get('source_name') or ''} (for your understanding only; never name it in the post)"),
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
                     f"({source.get('why') or 'no article'}). Use only the facts they give; leave out any specific they do not.")
    return system + avoid + writer_block(writer, stream) + pillar_line(writer, stream, idea.get("domain")), "\n\n".join(lines)


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

def asked_position(idea: dict[str, Any], stream: str, store: Any) -> tuple[str, str] | None:
    """The date and slot an idea was made FOR (the Schedule tab's empty slot, or a rejected post's own slot when Reject
    writes a replacement, as Studio did), when it is still in the future and still free; otherwise None."""
    b = idea.get("brief") if isinstance(idea.get("brief"), dict) else {}
    pos = b.get("position") if isinstance(b.get("position"), dict) else {}
    date, slot = str(pos.get("date") or ""), str(pos.get("slot") or "")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date) or not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", slot):
        return None
    now = (datetime.now(UTC) + MYT).strftime("%Y-%m-%d %H:%M")
    if f"{date} {slot}" <= now or (date, slot) in taken_positions(store, stream):
        return None
    return date, slot


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
            if domain and allow and domain not in allow and domain not in ANY_DAY_DOMAINS:
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
    return db.requeue_stale(store, db.IDEAS, working="working", back="new", cutoff=cutoff, max_attempts=3, what="idea")


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


def kept_media(store: Any, brief: dict[str, Any]) -> list[str]:
    """Pictures a replacement keeps from the draft it replaces (brief.keep_media_ids, written by Reject & replace):
    only those still there and finished, in their order. Never raises: a failed look-up keeps nothing and the worker
    makes new pictures as usual."""
    ids = [str(x) for x in (brief.get("keep_media_ids") or []) if isinstance(x, str)][:10]
    if not ids:
        return []
    try:
        rows = store.table(db.MEDIA).select("id,status,mode,generated_media_url").in_("id", ids).execute().data or []
    except Exception:  # noqa: BLE001
        return []
    # a drawn slide set carries the OLD words: the replacement's slides are drawn again from its own
    ok = {r["id"] for r in rows if r.get("status") == "done" and r.get("generated_media_url") and r.get("mode") != "slides"}
    return [i for i in ids if i in ok]


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
    source = faq_source(idea) or stored_source(idea) or read_source(idea.get("source_url"))
    system, user = build_request(idea, source, brand, avoid=compliance.avoid_line(indo_extra), writer=settings.get("writer"))
    fmt = format_of(idea)
    want_slides = fmt == "carousel"
    want_poster = fmt == "poster"
    if want_slides:
        system += SLIDES_RULES.get(stream, SLIDES_RULES["regulab"])
    if want_poster:
        system += POSTER_RULES.get(stream, POSTER_RULES["regulab"])
    # A retry after a failure part-way (the draft written, then the picture jobs or the idea's own update failed) must
    # finish THAT draft, not write a second one holding a second slot. The draft's id is noted on the idea the moment
    # it exists, so the retry finds it.
    brief0 = idea.get("brief") if isinstance(idea.get("brief"), dict) else {}
    earlier = str(brief0.get("partial_post_id") or "")
    still = (store.table(db.POSTS).select("id,status").eq("id", earlier).limit(1).execute().data or []) if earlier else []
    reuse = bool(still and still[0].get("status") == "draft")
    if reuse and store.table(db.MEDIA).select("id").eq("post_id", earlier).limit(1).execute().data:
        # its pictures and slides are already queued from the words written then: writing again would pay the writer
        # and leave the carousel drawn from words the post no longer carries. Only the idea's own update is missing.
        store.table(db.IDEAS).update({"status": "drafted", "error": None, "brief": {
            **{k: v for k, v in brief0.items() if k != "partial_post_id"}, "post_id": earlier, "media_jobs": 0,
            "written_at": datetime.now(UTC).isoformat()}}).eq("id", idea["id"]).execute()
        return earlier
    out = llm.chat_json(system, user, max_tokens=5000 if (want_slides or want_poster) else 3500)
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
    date, slot = asked_position(idea, stream, store) or next_free_position(stream, domain, brand, taken_positions(store, stream))
    post = {
        "idea_id": idea["id"], "stream": stream, "domain": domain, "angle": angle, "lang": lang,
        "hook": str(out.get("hook") or "")[:300], "text": text, "citation": str(out.get("citation") or "")[:1000],
        "date": date, "slot": slot, "status": "draft", "created_by": idea.get("created_by"),
    }
    pillar = str(out.get("pillar") or "").strip()
    if pillar and pillar in pillars_for(settings.get("writer"), stream, domain or None):
        post["pillar"] = pillar          # only with a pillar list, which only exists once 021 (and its column) ran
    kept = kept_media(store, brief0)
    if kept:
        post["media_ids"] = kept         # Reject & replace kept the rejected draft's own pictures (Studio did the same)
    if want_slides:
        # only when asked: the column arrives with 006_slides.sql, and an idea that never asked
        # for slides must still be written on a database that has not run it
        post["slides"] = slides.normalise(out.get("slides"))
    reg = brand.get("regulab") or {}
    if kept:
        from . import publisher
        shown = [publisher.scan_entry(m) for m in publisher.media_for(store, kept)]
    else:
        shown = []
    flags = compliance.scan({**post, "media": shown}, brand=reg, schedule=reg.get("schedule"),
                            indo_extra=indo_extra)
    post["flags"] = flags
    post["hard_flags"] = compliance.hard_count(flags)
    if reuse:
        post_id = earlier
        store.table(db.POSTS).update({k: v for k, v in post.items() if k not in ("created_by", "date", "slot")}) \
            .eq("id", post_id).eq("status", "draft").execute()
        has_jobs = False                   # a draft with jobs already returned above, before the writer was asked
    else:
        post_id = store.table(db.POSTS).insert(post).execute().data[0]["id"]
        has_jobs = False
        store.table(db.IDEAS).update({"brief": {**brief0, "partial_post_id": post_id}}) \
            .eq("id", idea["id"]).execute()

    chosen = my_designs.for_idea(store, idea)      # the idea's look, or the default "My design" when it asked for none
    jobs = [] if has_jobs or kept else media_jobs(idea, source, out, post_id)
    if want_slides and post.get("slides") and not has_jobs:
        jobs.append(slide_job(idea, post, post_id, bg="post_image" if jobs or kept else "none", chosen=chosen))
    poster = slides.normalise([out.get("poster")] if isinstance(out.get("poster"), dict) else [])[:1] if want_poster else []
    if poster and not has_jobs:
        jobs.append(poster_job(idea, post, post_id, poster, bg="post_image" if jobs or kept else "none", chosen=chosen))
    if jobs:
        store.table(db.MEDIA).insert(jobs).execute()
    brief = {"source": {k: source.get(k) for k in ("ok", "why", "url", "title", "image")},
             "post_id": post_id, "media_jobs": len(jobs), "written_at": datetime.now(UTC).isoformat(),
             "model": getattr(llm, "last_model", "") or llm.s.model}
    if look_of(idea) != "classic":
        brief["look"] = look_of(idea)      # the carousel look Wan chose on the idea (Studio's designs), kept
    if fmt != "post":
        brief["format"] = fmt              # carousel or poster, kept for the page
    for k in ("position", "replaces", "keep_media_ids"):
        if k in brief0:
            brief[k] = brief0[k]           # what the idea was made for stays readable on it
    store.table(db.IDEAS).update({"status": "drafted", "brief": brief, "error": None}).eq("id", idea["id"]).execute()
    return post_id


REVISE_ASK = """REWRITE THIS POST on the SAME subject. Wan read it and wants a change:
WAN'S NOTE: %s

Keep every fact the current post and its citation carry, and add none: the note changes how it is said, what it leads
with or what it leaves out, never what the source says. Every rule above still applies. Answer in the same JSON shape
("fit" true). Do not return "slides": the slides stay as they are.

CURRENT HOOK: %s
CURRENT CITATION: %s
CURRENT CAPTION (%s):
%s"""
REVISE_STALE_MINUTES = 30


def stamp() -> str:
    return datetime.now(UTC).isoformat()


def revise_posts(store: Any, llm: LLM, limit: int = 3) -> str:
    """"Revise with a note" (Studio's revise): the post keeps its slot, its idea and its pictures; its caption, hook and
    citation are written again with Wan's note, and the words it had go into `versions`. Slides are NOT rewritten: they
    carry Wan's per-slide designs and the pictures already drawn from them, and "Build from the caption" in the slides
    editor redoes them on purpose. Only a draft is rewritten: an approved post is what Wan approved. The worker never
    approves anything."""
    try:
        cutoff = (datetime.now(UTC) - timedelta(minutes=REVISE_STALE_MINUTES)).isoformat()
        store.table(db.POSTS).update({"revise_state": "new"}).eq("revise_state", "working").lt("updated_at", cutoff).execute()
        rows = (store.table(db.POSTS).select("*").eq("revise_state", "new").order("updated_at").limit(limit)
                .execute().data or [])
    except Exception as exc:  # noqa: BLE001 - 021 not run yet: nothing to revise
        return f"Revise: skipped ({str(exc)[:100]})"
    if not rows:
        return "Revise: none waiting"
    settings = load_settings(store)
    done = 0
    for post in rows:
        got = (store.table(db.POSTS).update({"revise_state": "working", "revise_error": None}).eq("id", post["id"])
               .eq("revise_state", "new").execute().data or [])
        if not got:
            continue                      # another run took it
        try:
            revise_one(store, llm, post, settings)
            done += 1
        except Exception as exc:  # noqa: BLE001 - recorded on the post for the page
            msg = str(exc) if isinstance(exc, IdeaError) else f"{type(exc).__name__}: {str(exc)[:400]}"
            log.error("revise %s: %s", post["id"], msg)
            store.table(db.POSTS).update({"revise_state": "error", "revise_error": msg[:800]}).eq("id", post["id"]).execute()
    return f"Revise: {done}/{len(rows)} rewritten"


def revise_one(store: Any, llm: LLM, post: dict[str, Any], settings: dict[str, Any]) -> None:
    from . import publisher
    if not llm.configured:
        raise IdeaError(llm.why_off())
    if post.get("status") != "draft":
        raise IdeaError("only a draft is rewritten: put the post back to draft first, then ask again")
    stream = post.get("stream") or "regulab"
    lang = post.get("lang") or ("en" if stream == "linkedin" else "bm")
    brand = settings.get("brand") or {}
    indo_extra = (settings.get("bahasa") or {}).get("indo")
    if stream == "linkedin":
        angles = (brand.get("linkedin") or {}).get("angles") or {}
        system = LINKEDIN_SYSTEM % "; ".join(f"{k} = {v}" for k, v in sorted(angles.items()))
    else:
        system = REGULAB_SYSTEM % DOMAINS
    system += compliance.avoid_line(indo_extra) + writer_block(settings.get("writer"), stream)
    plat = "linkedin" if stream == "linkedin" else "instagram"
    caption = ((post.get("text") or {}).get(lang) or {}).get(plat) or ""
    user = REVISE_ASK % (str(post.get("revise_note") or "").strip()[:800], post.get("hook") or "", post.get("citation") or "",
                         lang, caption)
    out = llm.chat_json(system, user, max_tokens=3500)
    if not out:
        raise IdeaError("the writer did not answer (see the run log); ask again")
    text = normalise_text(out.get("text"), stream, lang)
    if not text.get(lang):
        raise IdeaError(f"the writer returned no {lang.upper()} caption; the post is unchanged")
    before = {k: post.get(k) for k in ("hook", "text", "citation")}
    update: dict[str, Any] = {
        "text": text, "hook": str(out.get("hook") or post.get("hook") or "")[:300],
        "citation": str(out.get("citation") or post.get("citation") or "")[:1000],
        "versions": [*(post.get("versions") or []), {**before, "at": stamp(), "why": post.get("revise_note") or ""}][-20:],
        "decisions": [*(post.get("decisions") or []), {"at": stamp(), "by": "bot", "action": "revised",
                                                       "note": str(post.get("revise_note") or "")[:400]}][-50:],
        "revise_state": None, "revise_note": None, "revise_error": None,
    }
    media = publisher.media_for(store, list(post.get("media_ids") or []))
    reg = brand.get("regulab") or {}
    flags = compliance.scan({**post, **update, "media": [publisher.scan_entry(m) for m in media if m.get("status") == "done"]},
                            brand=reg, schedule=reg.get("schedule"), indo_extra=indo_extra)
    update["flags"], update["hard_flags"] = flags, compliance.hard_count(flags)
    got = (store.table(db.POSTS).update(update).eq("id", post["id"]).eq("status", "draft").eq("revise_state", "working")
           .execute().data or [])
    if not got:
        raise IdeaError("the post changed while it was being rewritten (approved, or edited): nothing was written")
    db.log_event(store, "info", "post", "post.revised", f"Ditulis semula dengan nota: {update['hook'][:80]}",
                 ref_table="semasa_posts", ref_id=post["id"])


def slide_job(idea: dict[str, Any], post: dict[str, Any], post_id: str, bg: str = "none",
              chosen: tuple[str, dict[str, Any] | None] | None = None) -> dict[str, Any]:
    """One render job for the whole carousel, carrying a snapshot of the words. Queued after the
    picture jobs, so a picture made in the same run can be the slides' background. With no picture, a Studio look is
    drawn on Studio's default ground for the domain or angle (Wan's own photographs), as Studio did."""
    from . import cards_library, studio_cards
    look, saved = chosen or (look_of(idea), None)
    review: dict[str, Any] = {}
    if bg == "none" and saved and saved.get("bg"):
        bg = saved["bg"]                       # the saved design's own background, when the post has no picture of its own
    elif bg == "none" and saved and saved.get("bg_prompt"):
        bg, review = "from_ref", {"background": saved["bg_prompt"]}      # a design from a reference: an ORIGINAL picture
    elif bg == "none" and studio_cards.is_studio_look(look) and not (saved and saved.get("layouts")):
        bg = cards_library.default_ground(post.get("stream") or "regulab", post.get("domain"), post.get("angle")) or "none"
    return {"idea_id": idea["id"], "post_id": post_id, "type": "image", "mode": "slides", "status": "pending",
            "prompt": "", "created_by": idea.get("created_by"),
            "meta": {"flow": "A", "slides": post.get("slides") or [], "stream": post.get("stream"),
                     "citation": post.get("citation") or "", "domain": post.get("domain"),
                     "angle": post.get("angle"), "bg": bg, "look": look, "fit": look != "classic",
                     **({"review": review} if review else {}), **({"design_pack": saved} if saved else {})}}


def poster_job(idea: dict[str, Any], post: dict[str, Any], post_id: str, words: list[dict[str, Any]],
               bg: str = "none", chosen: tuple[str, dict[str, Any] | None] | None = None) -> dict[str, Any]:
    """The idea's poster: a Design job (one 4:5 artwork) attached to its draft, in the look chosen on the idea."""
    look, saved = chosen or (look_of(idea), None)
    review: dict[str, Any] = {}
    if bg == "none" and saved and saved.get("bg"):
        bg = saved["bg"]
    elif bg == "none" and saved and saved.get("bg_prompt"):
        bg, review = "from_ref", {"background": saved["bg_prompt"]}
    return {"idea_id": idea["id"], "post_id": post_id, "type": "image", "mode": "slides", "status": "pending",
            "prompt": "", "created_by": idea.get("created_by"),
            "meta": {"flow": "A", "design": "poster", "format": "portrait", "slides": words, "stream": post.get("stream"),
                     "citation": post.get("citation") or "", "domain": post.get("domain"), "angle": post.get("angle"),
                     "bg": bg, "look": look, "fit": look != "classic",
                     **({"review": review} if review else {}), **({"design_pack": saved} if saved else {})}}


LOOKS = ("classic", "grid", "era", "photo")


def look_of(idea: dict[str, Any]) -> str:
    """The carousel look chosen on the idea, carried in its brief ({"look": ...}) until the bot writes the draft:
    Semasa's own drawing ("classic") or one of ws.regulab Studio's designs. Anything else is "classic"."""
    look = str(((idea.get("brief") or {}) if isinstance(idea.get("brief"), dict) else {}).get("look") or "classic")
    return look if look in LOOKS or my_designs.token(look) else "classic"


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


def run_all(store: Any, llm: LLM) -> str:
    """The worker's writing step: empty slots given an idea (only when Wan switched autofill on), new ideas into
    drafts, then drafts Wan asked to revise."""
    from . import autofill
    fill = autofill.run(store, load_settings(store)) if llm.configured else "Autofill: waiting for a writer"
    return "\n".join([fill, run(store, llm), revise_posts(store, llm)])
