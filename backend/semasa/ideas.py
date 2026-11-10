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

from . import (
    antislop,
    compliance,
    copywriting,
    db,
    definitions,
    hook_bank,
    hook_learning,
    language,
    modes,
    my_designs,
    proofread,
    slides,
    writing_styles,
)
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

# The 25 hook shapes (docs/hook-bank, .claude/skills/hook-bank) live in hook_bank.py and are REQUIRED: the first line of every
# post is built on one of them (Wan, 6 Nov 2026: "make sure 25 hook tu wajib dalam ayat"). Re-exported for the tests and the page.
HOOK_FAMILIES = hook_bank.FAMILIES
HOOK_ORDER = hook_bank.ORDER
HOOK_FAMILY_OFF_BRAND = hook_bank.OFF_BRAND
hook_block = hook_bank.block
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

HOW IT SOUNDS (Wan, 9 Nov 2026): casual and spoken, never formal. Write the way a friend who knows the rules explains it
over teh tarik: short lines, everyday words ("korang", "senang cerita", "maksudnya", "tau"), a little warmth, no legal or
corporate phrasing, no stiff headings. Casual never means loose with facts: every fact still comes only from the SOURCE.
The FIRST LINE is the hook, built on the hook shape given below. The LAST LINE before the hashtags is ONE short, friendly
invitation to follow for more of this (for example "Follow untuk tip regulatori yang senang faham."). That follow line is
the only ask allowed.

Rules. Breaking any of them blocks the post, so follow them exactly:
1. No call to action except the one follow invitation above: never "hubungi kami", "komen", "simpan post", "kongsi", "DM/PM",
   "link in bio", "klik link", "semak kelayakan", and never a link, a website or a phone number in the follow line. Between
   the hook and the follow line, stay on the substance.
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
   most 3 hashtags; threads is a THREAD (rule 9) of 3 to 5 posts, each at most 500 characters, at most 1 hashtag in all.
8. The citation names the regulator and the instrument (for example "NPRA, Guidelines for Control of Cosmetic Products
   in Malaysia"), never a news portal, blog or social platform. If only a news report supports a fact, leave that
   fact out, unless a NEWSPAPER STORY block below allows the facts the report itself states.
9. THREADS FORMAT (Wan, 10 Nov 2026): the threads caption is a thread with a continuation, never one post. Separate the
   posts with a line holding only --- . Post 1 carries the picture and has three short paragraphs: the hook line, one line
   saying what the thread gives (a count when it lists things: "5 perkara ..."), and one line telling the reader the detail
   follows in the posts below. Posts 2 to 5 each open with a short label line ending in a colon, then 3 to 6 numbered
   lines ("1. ..."), every line one complete point from the source, never a fragment; the last post names the instrument
   or rule the thread rests on. At most 500 characters a post, no call to action, no emoji, no hashtag except one on the last.

Answer with ONE JSON object:
{"fit": true or false, "why_not": "", "hook": "the first line", "hook_shape": the number of the hook shape it is built on,
 "domain": one of %s,
 "citation": "...", "text": {"bm": {"instagram": "...", "facebook": "...", "threads": "..."},
                             "en": {"instagram": "...", "facebook": "...", "threads": "..."}},
 "terms": [{"term": "a word or acronym the reader may not know", "meaning": "what it is, in one plain sentence"}],
 "visual_prompt": "an English description of one illustrative picture: no words, no logos, no real people",
 "alt": "short alt text in BM"}
Set "fit" false (and say why in "why_not") only when the story gives this audience (SME owners in cosmetics, food, halal and
pharmaceuticals) nothing to use. A story does not need a rule attached to be worth a post: judge it in its context (who reads
it, what they could take from it)."""

LINKEDIN_SYSTEM = """You write a LinkedIn post for Ts. ChM Muhammad Ridzuan, a registered chemist and senior
regulatory-affairs specialist, writing in his own name to peers (formulators, RA people, brand owners).
Hook on line one. One idea. A concrete example (ingredient, Annex entry, real figure). Short paragraphs of one or
two sentences. 120 to 220 words. Casual and human, the way he talks to a colleague, never stiff or formal. Citations below
the body, never inside it. The last line of the body is ONE short, friendly invitation to follow him for more of this (for
example "Follow me for more like this."), the only ask allowed; before it, end on a statement that lands, never a question.
3 to 5 hashtags. No em dash.

Rules. Breaking any blocks the post:
1. No company identity at all: never mention ws.regulab, KKM Halal Consultant or any website.
2. No call to action except the one follow invitation (no "comment below", "DM me", "share this", "link in bio", no link).
3. Cite the INSTRUMENT (e.g. EC 1223/2009 Annex III entry 325, SI 2026/109, ISO 24444, a WTO TBT number), never a
   blog or aggregator (ChemLinked, CIRS, CosmeticsDesign, Chemical Watch, Happi and the like), never a news portal.
4. No fact without a source in the SOURCE below: a fact it does not give is left out, never guessed, and never
   replaced by a placeholder or a note in brackets.
5. Never say the idea came from Reddit, YouTube, TikTok or a forum.

ENGLISH ONLY (Wan, 9 Nov 2026): the hook, the caption and every word on every slide (cover, titles, leads, points, last slide)
are English. The hook shapes below are written in casual Malay: translate the shape into natural English and never print the
Malay words (no "kau", "aku", "benda pasal", "takde sapa", "yg", "Tahukah anda", no "1 Hari 1 Ilmu").

Angles: %s

Answer with ONE JSON object:
{"fit": true or false, "why_not": "", "hook": "the first line, in English",
 "hook_shape": the number of the hook shape it is built on,
 "angle": one letter from the list,
 "citation": "...", "text": {"en": {"linkedin": "..."}, "bm": {"linkedin": "the same post in Malaysian Malay"}},
 "terms": [{"term": "a word or acronym the reader may not know", "meaning": "what it is, in one plain sentence"}],
 "visual_prompt": "an English description of one illustrative picture: no words, no logos, no real people",
 "alt": "short alt text in English"}
Set "fit" false (and say why) only when the story gives a chemist, RA or brand-owner peer nothing to use. A story does not need
a rule attached to be worth a post: judge it in its context (the audience, the angle, what they could take from it)."""


SLIDES_RULES = {
    "regulab": """

SLIDES WANTED. Also return "slides": a carousel in Malaysian Malay with as many slides as the story needs (no minimum,
no maximum), drawn as 1080x1080 cards:
[{"title": "...", "lead": "...", "points": ["...", "..."]}, ...]
- Slide 1 is the cover: its headline IS the hook (the same hook shape you filled for the caption's first line, no underscores,
  no figure the SOURCE does not give), at most 12 words, no "lead", "points" empty or one short line. It is drawn very large.
- Each middle slide is a FULL card, never a bare one: a title of at most 8 words, a "lead" (one sentence of at most 22 words that
  says the point plainly) and 3 to 4 "points" of at most 16 words each: one fact taken apart. Never pad: if the SOURCE gives less,
  write fewer points; a short slide is enlarged by the drawing.
- The last slide is the takeaway, stated plainly. It is NOT a call to action.
- Mark the one key word of a title with *asterisks* for emphasis, at most once per title.
- Every rule above applies to every slide: no call to action, no URL or website, no news portal or social source,
  and no fact that is not in the SOURCE. The source line is added to the last
  slide from "citation" automatically, so do not write it into a slide.""",
    "linkedin": """

SLIDES WANTED. Also return "slides": a carousel in English with as many slides as the story needs (no minimum,
no maximum), drawn as 1080x1350 cards:
[{"title": "...", "lead": "...", "points": ["...", "..."]}, ...]
- Slide 1 is the cover: its headline IS the hook (the same hook shape you filled for the caption's first line, no underscores,
  no figure the SOURCE does not give), at most 12 words, no "lead", "points" empty or one short line. It is drawn very large.
- Each middle slide is a FULL card, never a bare one: a title of at most 9 words, a "lead" (one sentence of at most 22 words that
  says the idea plainly) and 3 to 4 "points" of at most 18 words each: one idea taken apart. Never pad: if the SOURCE gives less,
  write fewer points; a short slide is enlarged by the drawing.
- The last slide is the takeaway. Never a question, never a call to action.
- Mark the one key word of a title with *asterisks* for emphasis, at most once per title.
- English only on every slide, the cover and the last slide included: the Malay hook shapes are translated, never printed.
- No company identity, no URL, no blog or aggregator, and no fact the SOURCE does not give. The citation is added
  to the last slide automatically.""",
}


POSTER_RULES = {
    "regulab": """

POSTER WANTED. Also return "poster": ONE 4:5 poster in Malaysian Malay: {"title": "the hook: the same hook shape you filled
for the caption's first line, at most 12 words", "points": [up to 5 points of at most 22 words each]}. Mark the one key word
of the title with *asterisks*. The same
rules apply to every word: no call to action, no URL, no fact the SOURCE does not give.
The citation is drawn at its foot automatically.""",
    "linkedin": """

POSTER WANTED. Also return "poster": ONE 4:5 poster in English: {"title": "the hook: the same hook shape you filled
for the caption's first line, at most 12 words", "points": [up to 5 points of at most 22 words each]}. Mark the one key word
of the title with *asterisks*. No
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
                  avoid: str = "", writer: dict[str, Any] | None = None,
                  bank: hook_bank.Bank | None = None, hint: str = "", style_block: str = "") -> tuple[str, str]:
    stream = idea.get("stream") or "regulab"
    if stream == "linkedin":
        angles = (brand.get("linkedin") or {}).get("angles") or {}
        system = LINKEDIN_SYSTEM % "; ".join(f"{k} = {v}" for k, v in sorted(angles.items()))
    else:
        system = REGULAB_SYSTEM % DOMAINS
    system += antislop.prompt_block()
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
    flags = idea.get("brief") if isinstance(idea.get("brief"), dict) else {}
    if flags.get("story_mode"):
        lines.append("STORY MODE: tell it as a small true story (who did what, what happened, what was found) in the casual "
                     "voice above, with the fact inside it. The fact is never dropped for the story.")
    if flags.get("hook_required"):
        lines.append("HOOK REQUIRED: the first line must be the hook; a caption that opens flat is not acceptable.")
    if flags.get("relate_regulatory"):
        lines.append("NEWSPAPER STORY, not a regulator's notice. A rule is NOT required (Wan, 9 Nov 2026): read the story in the "
                     "context of this stream's audience and decide what is useful to them. Where a Malaysian or ASEAN rule "
                     "genuinely governs it (NPRA, KKM/BKKM, JAKIM, the Annexes), say so and what it means for them, but ONLY "
                     "where the link is real in the SOURCE or in an instrument you can name exactly. With no rule angle, write "
                     "it from the angle that serves this audience: what happened, and why a product maker, brand owner or "
                     "formulator would care (safety, consumer trust, ingredients, health or business impact, how it is being "
                     "read). The facts the news report itself states may be used and told plainly as reported, without naming "
                     "the portal, never presented as a regulator's position and never with a figure, date or name it does not "
                     "give. Never invent a link, an entry number or a date. Set \"fit\" false only when, in this context, the "
                     "story holds nothing this audience can use (gossip, a bare event notice), and say what was missing.")
    if source.get("ok"):
        lines.append(f"SOURCE ({source.get('label') or 'the article itself'}):\n{source.get('title') or ''}\n"
                     f"{source.get('description') or ''}\n{source.get('text') or ''}")
    else:
        lines.append("SOURCE: only the headline and summary above could be read "
                     f"({source.get('why') or 'no article'}). Use only the facts they give; leave out any specific they do not.")
    family = str(idea.get("hook_family") or "").strip().lower() or None
    return (system + avoid + writer_block(writer, stream) + pillar_line(writer, stream, idea.get("domain"))
            + style_block + "\n\n" + definitions.RULE + hook_block(family, stream, bank, hint), "\n\n".join(lines))


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
            kept = {p: antislop.clean(str(inner[p]).strip()) for p in plats if isinstance(inner.get(p), str) and inner[p].strip()}
            if kept:
                out[lg] = kept
        elif isinstance(inner, str) and inner.strip() and len(plats) == 1:
            out[lg] = {plats[0]: antislop.clean(inner.strip())}
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


def english_only(llm: LLM, system: str, user: str, out: dict[str, Any], shape: int, stream: str, family: str | None,
                 bank: hook_bank.Bank | None, max_tokens: int) -> tuple[dict[str, Any], int]:
    """The LinkedIn stream is English (Wan, 9 Nov 2026). The hook shapes are casual Malay and the writer sometimes printed them on
    the hook, the cover and the last slide of an English post. One more ask names the offending fields; if the answer is still
    Malay the idea fails with a plain sentence, so a mixed-language card never leaves here. ws.regulab is not touched."""
    if stream != "linkedin":
        return out, shape
    bad = language.malay_fields(out)
    if not bad:
        return out, shape
    again = llm.chat_json(system, user + language.english_ask(bad), max_tokens=max_tokens)
    got = hook_bank.declared(again, stream, family, bank) if isinstance(again, dict) else None
    if isinstance(again, dict) and again.get("fit") is not False and got and not language.malay_fields(again):
        return again, got
    raise IdeaError("the writer left Malay on a LinkedIn post that must be English (" + ", ".join(bad[:5])
                    + "; asked twice): press Cuba lagi")


def shorter_hook(llm: LLM, hook: str, stream: str, words: int = 12) -> str:
    """The hook, kept to `words` words or fewer so it fits a cover headline (Wan, 9 Nov 2026): one small ask, never more. The
    caption keeps its own longer first line; the cover wears this one. "" when the writer gives nothing usable, and the cover is
    left as the writer drew it."""
    tongue = "natural English" if stream == "linkedin" else "casual Malaysian Malay (never Bahasa Indonesia)"
    out = llm.chat_json(
        f"Shorten a social-media hook to at most {words} words. Keep its opening pattern and its meaning, add no fact, "
        f"no figure, no em dash and no underscores. Write it in {tongue}. Answer with ONE JSON object: {{\"hook\": \"...\"}}",
        f"HOOK: {hook}", max_tokens=200)
    short = " ".join(str((out or {}).get("hook") or "").split()) if isinstance(out, dict) else ""
    if not short or "_" in short or len(short.split()) > words or (stream == "linkedin" and language.is_malay(short)):
        return ""
    return short


SAME_EVENT_SYSTEM = (
    "You compare news stories for a social-media desk. Answer with ONE JSON object: {\"same_as\": N, \"why\": \"...\"}. "
    "N is the number of an EARLIER story that reports the SAME event as the NEW one: the same incident, seizure, recall, ruling "
    "or announcement, even when the headline, the newspaper or the way the company is named differs. A follow-up that adds a new "
    "fact, a different incident of the same kind, or a different company is NOT the same event. Answer 0 when none matches or "
    "when unsure.")


def same_event_written(store: Any, llm: LLM, idea: dict[str, Any], days: int = 14, limit: int = 30) -> str:
    """The headline of an earlier idea for the SAME stream that reports the same event as this one, or "" (Wan, 9 Nov 2026).
    Words cannot link two reports of one incident that share no name (the roti complaint and the Gardenia factory check), so the
    writer is asked, once and cheaply. Only for an idea auto-fill made and nobody added a note to: a click of Wan's own, or a
    retry with a note, is a decision. It fails OPEN: a failed look-up or an answer that is not a number writes
    the post as before."""
    brief = idea.get("brief") if isinstance(idea.get("brief"), dict) else {}
    if not brief.get("auto") or str(idea.get("note") or "").strip():
        return ""
    from . import autofill
    try:
        since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        rows = (store.table(db.IDEAS).select("id,source_title,source_summary").eq("stream", idea.get("stream") or "regulab")
                .eq("status", "drafted").neq("id", idea["id"]).gte("created_at", since).order("created_at", desc=True)
                .limit(80).execute().data or [])
        seen: set[str] = set()
        earlier = []
        for r in rows:
            key = autofill.story_key(r.get("source_title"))
            if key and key not in seen:
                seen.add(key)
                earlier.append(r)
        earlier = earlier[:limit]
        if not earlier:
            return ""
        listing = "\n".join(f"{i}. {r.get('source_title')} | {str(r.get('source_summary') or '')[:160]}"
                            for i, r in enumerate(earlier, 1))
        out = llm.chat_json(SAME_EVENT_SYSTEM, f"NEW: {idea.get('source_title')} | "
                            f"{str(idea.get('source_summary') or '')[:300]}\n\nEARLIER:\n{listing}", max_tokens=150)
        n = int((out or {}).get("same_as") or 0) if isinstance(out, dict) else 0
    except Exception as exc:  # noqa: BLE001 - fail open
        log.info("same-event check skipped (%s)", str(exc)[:100])
        return ""
    return str(earlier[n - 1].get("source_title") or "") if 1 <= n <= len(earlier) else ""


def process_idea(store: Any, llm: LLM, idea: dict[str, Any], settings: dict[str, Any]) -> str:
    """Returns the new post id. Raises IdeaError with a message for the page."""
    if not llm.configured:
        raise IdeaError(llm.why_off())
    earlier = already_published(store, idea)
    if earlier and not str(idea.get("note") or "").strip():
        raise IdeaError(f"this news already has a {earlier['status']} post for this stream "
                        f"({earlier.get('hook') or earlier.get('date') or earlier['id']}), so it is not written again. "
                        "For a follow-up, add a note saying what the new post should say, then Cuba lagi.")
    twin = same_event_written(store, llm, idea)
    if twin:
        raise IdeaError(f"the same event is already written up for this stream ({twin[:90]}), so it is not written again. "
                        "For a follow-up, add a note saying what the new post should say, then Cuba lagi.")
    antislop.begin(settings.get("antislop"))
    brand = settings.get("brand") or {}
    indo_extra = (settings.get("bahasa") or {}).get("indo")
    stream = idea.get("stream") or "regulab"
    lang = "en" if stream == "linkedin" else "bm"
    source = faq_source(idea) or stored_source(idea) or read_source(idea.get("source_url"))
    bank = hook_bank.pick(store, idea, settings)        # a hook style made from screenshots, or None: the built-in 25
    hint = hook_learning.hint(store, bank)              # what has earned views and interaction so far (a hint, never a rule)
    style = writing_styles.pick(store, idea, settings)  # Wan's writing style (the voice of the caption), or None: house style
    system, user = build_request(idea, source, brand, avoid=compliance.avoid_line(indo_extra), writer=settings.get("writer"),
                                 bank=bank, hint=hint, style_block=writing_styles.block(style, stream=stream))
    fmt = format_of(idea)
    system += copywriting.block(copywriting.kind_of(idea, stream, fmt))
    # the mode of this post (Wan, 10 Nov 2026): Wan's own pick on the idea, else chosen from the content and rotated with the
    # modes used lately, the same way a film's is; it changes the arrangement of the facts, never the voice or a rule
    mode = str((idea.get("brief") or {}).get("mode") or "") if isinstance(idea.get("brief"), dict) else ""
    if mode not in modes.MODES:
        content = " ".join(str(x or "") for x in (idea.get("source_title"), idea.get("note"), source.get("title"),
                                                    source.get("description"), str(source.get("text") or "")[:1500]))
        mode, mode_why = modes.choose(content, modes.recent_modes(store))
        log.info("idea %s: mode %s, %s", str(idea.get("id"))[:8], mode, mode_why)
    system += modes.post_block(mode, stream)
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
    family = str(idea.get("hook_family") or "").strip().lower() or None
    shape = hook_bank.declared(out, stream, family, bank)
    if shape is None:
        # every post leads with one of the hook shapes (Wan, 6 Nov 2026): one more ask, then the idea fails with a reason
        again = llm.chat_json(system, user + hook_bank.asks_again(stream, family, bank),
                              max_tokens=5000 if (want_slides or want_poster) else 3500)
        if again and again.get("fit") is not False and hook_bank.declared(again, stream, family, bank):
            out = again
            shape = hook_bank.declared(out, stream, family, bank)
    if shape is None:
        which = f"the shapes of the hook style {bank.name!r}" if bank else "the 25 hook shapes"
        raise IdeaError(f"the writer did not build the hook on one of {which} (asked twice): press Cuba lagi")
    out, shape = english_only(llm, system, user, out, shape, stream, family, bank,
                              5000 if (want_slides or want_poster) else 3500)
    text = normalise_text(out.get("text"), stream, lang)
    if not text.get(lang):
        raise IdeaError(f"the writer returned no {lang.upper()} caption")
    # grammar and spelling, in the post's own language, before anything is stored (Wan, 10 Nov 2026); never changes a fact
    fixed_hook, text, fixed_slides, corrected = proofread.post(llm, out, text, lang)
    out = {**out, "hook": fixed_hook, **({"slides": fixed_slides} if fixed_slides is not None else {})}
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
    cover_state = ""                     # whether the cover or poster headline is the hook: set, kept or too_long
    kept = kept_media(store, brief0)
    if kept:
        post["media_ids"] = kept         # Reject & replace kept the rejected draft's own pictures (Studio did the same)
    if want_slides:
        # only when asked: the column arrives with 006_slides.sql, and an idea that never asked
        # for slides must still be written on a database that has not run it
        post["slides"], cover_state = hook_bank.cover(slides.normalise(out.get("slides")), post["hook"])
        if cover_state == "too_long":
            short = shorter_hook(llm, post["hook"], stream)
            if short:
                post["slides"], cover_state = hook_bank.cover(post["slides"], short)
                cover_state = "shortened" if cover_state in ("set", "kept") else "too_long"
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
    antislop.finish(store, "post", post_id)

    chosen = my_designs.for_idea(store, idea)      # the idea's look, or the default "My design" when it asked for none
    jobs = [] if has_jobs or kept else media_jobs(idea, source, out, post_id)
    if want_slides and post.get("slides") and not has_jobs:
        jobs.append(slide_job(idea, post, post_id, bg="post_image" if jobs or kept else "none", chosen=chosen))
    poster = slides.normalise([out.get("poster")] if isinstance(out.get("poster"), dict) else [])[:1] if want_poster else []
    if poster:
        poster, cover_state = hook_bank.cover(poster, post["hook"])
        if cover_state == "too_long":
            short = shorter_hook(llm, post["hook"], stream)
            if short:
                poster, cover_state = hook_bank.cover(poster, short)
                cover_state = "shortened" if cover_state in ("set", "kept") else "too_long"
    if poster and not has_jobs:
        jobs.append(poster_job(idea, post, post_id, poster, bg="post_image" if jobs or kept else "none", chosen=chosen))
    if jobs:
        store.table(db.MEDIA).insert(jobs).execute()
    caption = (text.get(lang) or {}).get("linkedin" if stream == "linkedin" else "instagram", "")
    brief = {"source": {k: source.get(k) for k in ("ok", "why", "url", "title", "image")},
             "hook_shape": shape, **({"hook_style": bank.id} if bank else {}),
             "hook_in_caption": hook_bank.lead_matches(post["hook"], caption),
             **({"hook_on_cover": cover_state} if cover_state else {}),
             "post_id": post_id, "media_jobs": len(jobs), "written_at": datetime.now(UTC).isoformat(),
             "model": getattr(llm, "last_model", "") or llm.s.model}
    if corrected:
        brief["proofread"] = len(corrected)        # how many fields the proofreader corrected, shown as a pill
    terms = definitions.clean(out.get("terms"))
    if terms:
        brief["terms"] = terms             # what the subject IS, shown on the idea card (Wan, 10 Nov 2026)
    brief["mode"] = mode                   # what the post is FOR, shown as a pill and counted when the next one is chosen
    brief["look"] = look_of(idea)          # the carousel look: Wan's choice on the idea, else the default; "classic" is kept too
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
    antislop.begin(settings.get("antislop"))
    stream = post.get("stream") or "regulab"
    lang = post.get("lang") or ("en" if stream == "linkedin" else "bm")
    brand = settings.get("brand") or {}
    indo_extra = (settings.get("bahasa") or {}).get("indo")
    if stream == "linkedin":
        angles = (brand.get("linkedin") or {}).get("angles") or {}
        system = LINKEDIN_SYSTEM % "; ".join(f"{k} = {v}" for k, v in sorted(angles.items()))
    else:
        system = REGULAB_SYSTEM % DOMAINS
    idea = {}
    if post.get("idea_id"):
        try:
            idea = (store.table(db.IDEAS).select("id,brief").eq("id", post["idea_id"]).limit(1).execute().data or [{}])[0]
        except Exception:  # noqa: BLE001 - the revision still works, with the default style
            idea = {}
    bank = hook_bank.pick(store, idea, settings)
    system += (antislop.prompt_block() + compliance.avoid_line(indo_extra) + writer_block(settings.get("writer"), stream)
               + writing_styles.block(writing_styles.pick(store, idea, settings), stream=stream)
               + copywriting.block(copywriting.kind_of(idea, stream))
               + hook_bank.block(None, stream, bank, hook_learning.hint(store, bank)))
    plat = "linkedin" if stream == "linkedin" else "instagram"
    caption = ((post.get("text") or {}).get(lang) or {}).get(plat) or ""
    user = REVISE_ASK % (str(post.get("revise_note") or "").strip()[:800], post.get("hook") or "", post.get("citation") or "",
                         lang, caption)
    out = llm.chat_json(system, user, max_tokens=3500)
    if not out:
        raise IdeaError("the writer did not answer (see the run log); ask again")
    if hook_bank.declared(out, stream, None, bank) is None:
        again = llm.chat_json(system, user + hook_bank.asks_again(stream, None, bank), max_tokens=3500)
        if again and hook_bank.declared(again, stream, None, bank):
            out = again
        else:
            which = f"the shapes of the hook style {bank.name!r}" if bank else "the 25 hook shapes"
            raise IdeaError(f"the writer did not build the hook on one of {which} (asked twice); the post is unchanged")
    out, _shape = english_only(llm, system, user, out, 0, stream, None, bank, 3500)
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
    antislop.finish(store, "post", post["id"])
    db.log_event(store, "info", "post", "post.revised", f"Ditulis semula dengan nota: {update['hook'][:80]}",
                 ref_table="semasa_posts", ref_id=post["id"])

def slide_job(idea: dict[str, Any], post: dict[str, Any], post_id: str, bg: str = "none",
              chosen: tuple[str, dict[str, Any] | None] | None = None) -> dict[str, Any]:
    """One render job for the whole carousel, carrying its text, design and picture choice."""
    from . import cards_library, studio_cards
    look, saved = chosen or (look_of(idea), None)
    requested_picture = str(((idea.get("brief") or {}) if isinstance(idea.get("brief"), dict) else {}).get("picture") or "")
    if requested_picture == "none":
        bg = "none"
    elif requested_picture == "post":
        bg = "post_image"
    review: dict[str, Any] = {}
    if bg == "none" and saved and saved.get("bg"):
        bg = saved["bg"]                       # the saved design's own background, when the post has no picture of its own
    elif bg == "none" and saved and saved.get("bg_prompt"):
        bg, review = "from_ref", {"background": saved["bg_prompt"]}      # a design from a reference: an ORIGINAL picture
    elif bg == "none" and studio_cards.is_studio_look(look) and look != "image" and not (saved and saved.get("layouts")):
        bg = cards_library.default_ground(post.get("stream") or "regulab", post.get("domain"), post.get("angle")) or "none"
    return {"idea_id": idea["id"], "post_id": post_id, "type": "image", "mode": "slides", "status": "pending",
            "prompt": "", "created_by": idea.get("created_by"),
            "meta": {"flow": "A", "slides": post.get("slides") or [], "stream": post.get("stream"),
                     **({"design": "threads", "format": "portrait"} if look == "threads" else {}),
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


LOOKS = ("classic", "grid", "era", "photo", "image", "threads")
DEFAULT_LOOK = "image"          # Wan, 8 Nov 2026: the Image look (a picture ON the slide) is the default for new posts


def look_of(idea: dict[str, Any]) -> str:
    """The carousel look chosen on the idea, carried in its brief ({"look": ...}) until the bot writes the draft:
    Semasa's own drawing ("classic"), Threads-style text + picture, or one of ws.regulab Studio's designs.
    No choice is the default look ("image"); a name nobody knows is "classic", the drawing that never needs
    a picture or the browser."""
    raw = ((idea.get("brief") or {}) if isinstance(idea.get("brief"), dict) else {}).get("look")
    look = str(raw or DEFAULT_LOOK)
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
