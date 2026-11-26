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
    caption_fit,
    carousel,
    compliance,
    copywriting,
    db,
    definitions,
    glossary,
    hook_bank,
    hook_learning,
    language,
    lenggok,
    modes,
    my_designs,
    proofread,
    quran,
    rotation,
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
STORED_HOSTS = ("reddit.com", "youtube.com", "youtu.be", "threads.net", "threads.com")


def stored_source(idea: dict[str, Any]) -> dict[str, Any] | None:
    """An idea made from Wan's own sources (supabase/024): a Reddit thread, a YouTube video or a Threads post, a file in
    his OneDrive library, a finding in MYRA's sheet with no link. None of them has a page the writer should fetch
    (Reddit, YouTube and Threads refuse the fetch, and their addresses must never reach a post; the others are not web
    addresses), so the row's own words are the source, exactly as an FAQ entry's answer is. The address is withheld from
    the writer on purpose."""
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

# The words the page and the publisher check a post for (rules/compliance.json `vague`, compliance.vague_hits), said to both
# writers in the same sentence, so a draft is not written into a block (Wan, 16 Nov 2026: "make sure no vague content post").
# No percent sign in here: both prompts are %-formatted.
VAGUE_CHECK = """\
THIS IS CHECKED AND A VAGUE POST IS BLOCKED: wording that stands where an exact detail should be is refused unless a figure,
a date or an entry number is in the same sentence or one of the two sentences after it (on slides: the same slide or one of
the two after it). The wording: "regularly", "from time to time", "recently", "recent changes", "new rules", "latest
guidance", "several substances", "some products", "many cases", "studies show", "strict limits", "heavy fines"; in Malay
"dari semasa ke semasa", "secara berkala", "baru-baru ini", "peraturan baharu", "syarat baharu", "garis panduan terkini",
"beberapa bahan", "banyak produk", "pelbagai kajian", "kajian menunjukkan", "dikatakan", "denda berat". When the SOURCE
gives the detail, print it (how many, which entry, what limit, from what date) and the wording is fine. When the SOURCE
gives no exact detail, do not use that wording at all: say plainly what is known, and leave the rest out."""

# FACTS FIRST (Wan, 22 Nov 2026: "after this all content is based on facts as priority rather isu semasa, I will create post isu
# semasa from Hermes nous, the content must easy to understand and if got technical terms, must have small foot note for
# definition in the poster/carousel/card, and end of caption, besides that, prioritize announcement make by regulators or
# government so people/viewers alert"). Both writers get the same block; the stream decides the label of the definitions
# ("Definisi:" / "Definition:") and whether there is a follow line. The block is %-formatted by facts_first().
FACTS_FIRST = """\
FACTS FIRST (Wan, 22 Nov 2026). Semasa's own posts rest on facts, not on what is trending. This is checked by the page.
1. EVERY CLAIM IS A FACT FROM A NAMED INSTRUMENT OR ANNOUNCEMENT: who issued it, what it says, the date, and the reference number
   ONLY when the SOURCE gives one. Never invent a date, a number, a clause or a name; a fact the SOURCE does not give is left out.
2. AN ANNOUNCEMENT BY A REGULATOR OR THE GOVERNMENT COMES FIRST (NPRA, KKM, BKKM/FSQD, JAKIM, KPDN, JPJ and the like, or a
   foreign regulator). When the SOURCE is one, the post opens with WHO announced WHAT and, when the SOURCE gives it, from WHEN it
   applies, so a reader is alerted at once. The first line is still the hook built on one of the hook shapes (that rule stays):
   fill the shape so it carries the announcement, then the next sentence says who, what and when in full.
3. PLAIN LANGUAGE, so anyone can follow: short sentences, an everyday word wherever one works, and after any rule one clause
   saying what it means for the reader. Do not stack terms.
4. TECHNICAL TERMS GET A DEFINITION. A term the reader would not know (a body, a form, a list, a test, an acronym) is explained
   twice, in the same words:
   a. on the artwork: every slide (and the poster) returns "foot": "%(label)s: <term> = <what it is, at most 14 words>" with up
      to 2 terms, only terms that appear on THAT slide; "foot": "" when it has none. The cover slide and the last slide carry no
      foot.
   b. in the caption: the LAST paragraph of the body, before %(tail)s, is "%(label)s: term = meaning; term2 = meaning." with
      every term used (at most %(cap)s), each in the same words as on the artwork.
   A definition is MEANING ONLY: no figure, no claim that it works or is safe, no legal claim, no link, no brand.
5. THE GLOSSARY BELOW IS WAN'S OWN WORDING. When a term is in it, use its meaning word for word (the code puts it back if you
   reword it). Add a term of your own only when it is not listed, and only as a plain explanation of what it is.
GLOSSARY (term = meaning):
%(glossary)s"""


def facts_first(stream: str) -> str:
    """The FACTS FIRST block for a stream: the label of the definitions and what follows them differ, the rules do not."""
    lang = "en" if stream == "linkedin" else "bm"
    return FACTS_FIRST % {"label": glossary.LABEL[lang], "cap": glossary.CAPTION_TERMS, "glossary": glossary.prompt_block(lang),
                          "tail": "the hashtags" if stream == "linkedin" else "the follow line and the hashtags"}


REGULAB_SYSTEM = """You write social posts for ws.regulab, a Malaysian regulatory-affairs brand speaking to SME owners
(cosmetics, food, halal, pharmaceuticals). Voice: Bahasa Malaysia mixed naturally with English technical terms, warm,
plain, practical. MALAYSIAN Malay only, never Bahasa Indonesia: boleh not bisa, ubat not obat, syarikat not perusahaan,
kualiti not kualitas, pembungkusan not kemasan, kebenaran not izin.

HOW IT SOUNDS (Wan, 12 Nov 2026): casual and spoken, never formal, never stiff. Write the way a friend who knows the rules
explains it over teh tarik: short lines, everyday words, a little warmth, no legal or corporate phrasing, no stiff headings.
Use natural Malaysian short forms where they read naturally ("tak", "sebab", "je", "ni", "tu", "kat", "korang",
"senang cerita", "maksudnya", "tau") — never force them, and never lose a fact to them. Casual never means loose with
facts: every fact still comes only from the SOURCE.

LEAD WITH THE ANSWER. When the hook is a question, answer it plainly right after the hook (for example "Jawapan ringkas:
tidak.") before you explain why. Do not string the reader along to the last line. Then give the one thing that makes the
answer surprising or useful, then the detail, numbered if it has steps or several points ("1. ...", "2. ..."). Close with
one short practical line (for example "Nasihat mudah: ..."), not a lecture. A short list of numbered points reads better
than a wall of text; use it when there are three or more separate things. Give MORE facts, not fewer: every fact the SOURCE
states that a reader could use goes in, 5 to 8 numbered points when the SOURCE has that many.

The FIRST LINE is the hook, built on the hook shape given below. The LAST LINE before the hashtags is ONE short, friendly
invitation to follow for more of this (for example "Follow untuk tip regulatori yang senang faham."). That follow line is
the only ask allowed.

""" + lenggok.RULE + """

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
   BE SPECIFIC, NOT VAGUE (Wan, 16 Nov 2026): when the SOURCE names the product, the substance, the entry or clause number,
   the limit or the date, print it exactly. A post that only says something "berubah dari semasa ke semasa", that there are
   "syarat baharu" or that "beberapa produk" are affected, without saying which, how many or from when, is not a post.
5. No em dash. Do not open with "Tahukah anda". No superlatives, no promise of approval, no "tiada kesan sampingan",
   no "halal-friendly" or "patuh syariah" claims.
6. A fatwa post says whether the fatwa is diwartakan, and where.
7. Lengths (Wan, 21 Nov 2026: "tambahkan lagi fakta, jangan bagi caption yang pendek sangat"): instagram up to 2200 characters,
   aim about 1500 and never under 900, with at most 8 hashtags; facebook aim about 800 and never under 400, with at most 3
   hashtags; a caption under those floors is asked again. Fill the length with MORE FACTS from the SOURCE (who, what, how many,
   since when, which clause, what it means for the product), numbered "1. ... 2. ..." when there are several, never with filler;
   threads is a THREAD (rule 9) of 3 to 5 posts, each at most 500 characters, at most 1 hashtag in all.
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
 "visual_prompt": "an English description of one illustrative picture: no words, no logos, no real people, and NEVER a
 certificate, document, seal, stamp, label, packaging, screen, app or any object that has letters, numbers or symbols
 printed on it (image models garble them into nonsense).
 Draw the SUBJECT as a plain object, a scene or a simple illustration instead — for a certification or regulation story,
 draw the product, the ingredient or the setting, never the paperwork.",
 "alt": "short alt text in BM"}
Set "fit" false (and say why in "why_not") only when the story gives this audience (SME owners in cosmetics, food, halal and
pharmaceuticals) nothing to use. A story does not need a rule attached to be worth a post: judge it in its context (who reads
it, what they could take from it)."""

LINKEDIN_SYSTEM = """You write a LinkedIn post for Ts. ChM Muhammad Ridzuan, a registered chemist and senior
regulatory-affairs specialist, writing in his own name to peers (RA people, product developers, brand owners).
Hook on line one. One subject, treated in depth. The reader should finish knowing the exact facts: the instrument, the clause or
entry, the figure, the date. Casual and human, the way he talks to a colleague, never stiff or formal. Short paragraphs of one or
two sentences; the numbered facts below are the body.

DEPTH AND NUMBERING (Wan, 20 Nov 2026: "explain more facts on the caption in numbering, not brief only, people like more accurate
and deeply fact"; 21 Nov 2026: "tambahkan lagi fakta, jangan bagi caption yang pendek sangat"). 350 to 500 words, at least
1500 characters: a shorter caption is asked again. After the hook, answer it in one or two sentences, then give the facts as a
NUMBERED LIST, "1. ...", "2. ...", 6 to 10 points. Every point is one complete fact from the SOURCE with its exact detail
(the substance, the
limit, the entry or clause number, the date, who it applies to) and, where the SOURCE gives it, where it is written. A point
that only says a thing "matters" or "changed" with no detail is not a point. Order the points the way the reader needs them (what
it is, the number, who it covers, from when, what it means in practice). Then ONE short paragraph on what this means for a
product on the shelf, drawn only from those facts. Close on a statement that lands.

NO SELF-LABEL AND NO FOLLOW LINE (Wan, 20 Nov 2026: "no need mention as formulator or follow me for more"). Never write "as a
formulator", "as a chemist", "as an RA specialist" or any "as a ..." about the author, and never address the reader by job title
("formulators should ...", "brand owners need to ..."): state the fact and let the reader draw it. The post ends with no
invitation of any kind: no "follow me", no "follow for more", no "like", "share", "repost" or "comment". The body ends, then the
hashtags.

Citations below the body, never inside it. SOURCE LINK (Wan, 22 Nov 2026: "put link source but it's not mandatory"): when the
SOURCE gives the address of the regulator's, the instrument's or the journal's own page, add it on its own line under the citation
("Source: https://..."); leave it out when there is none, and never link a blog, an aggregator, a news portal or a social post.
3 to 5 hashtags. No em dash.

Rules. Breaking any blocks the post:
1. No company identity at all: never mention ws.regulab, KKM Halal Consultant or any website.
2. No call to action of any kind (no "comment below", "DM me", "share this", "follow me", "link in bio"). The only link allowed is
   the source link under the citation.
3. Cite the INSTRUMENT (e.g. EC 1223/2009 Annex III entry 325, SI 2026/109, ISO 24444, a WTO TBT number), never a
   blog or aggregator (ChemLinked, CIRS, CosmeticsDesign, Chemical Watch, Happi and the like), never a news portal.
4. No fact without a source in the SOURCE below: a fact it does not give is left out, never guessed, and never
   replaced by a placeholder or a note in brackets. More facts means every fact the SOURCE gives, not facts you add.
5. Never say the idea came from Reddit, YouTube, TikTok or a forum.

BE SPECIFIC, NOT VAGUE (Wan, 15 Nov 2026): name the exact substance, ingredient, Annex entry or clause number, the exact
figure and the effective date the SOURCE gives. Never write around the detail — "updates it regularly", "recent changes",
"several substances", "new rules", "latest guidance" and the like are vague and get called out by this audience. If the
SOURCE names the substance under review, say which substance; if it gives the entry number and date, print them exactly.
A post whose only claim is that something "changes regularly" is not a post: it must pin down what changed, by how much,
and from when.

ENGLISH ONLY (Wan, 9 Nov 2026): the hook, the caption and every word on every slide (cover, titles, leads, points, last slide)
are English. The hook shapes below are written in casual Malay: translate the shape into natural English and never print the
Malay words (no "kau", "aku", "benda pasal", "takde sapa", "yg", "Tahukah anda", no "1 Hari 1 Ilmu").

DIRECTION (Wan, 20 Nov 2026): the post states a FACT taken from a guideline, a regulation or an official website, and says
exactly where in it (the instrument, the clause or entry, the date). It is not a reaction to something that went viral: no
"everyone is talking about", no news-cycle hook. If the SOURCE is a newspaper story, write only the rule behind it, from the
instrument.

Angles: %s

Answer with ONE JSON object:
{"fit": true or false, "why_not": "", "hook": "the first line, in English",
 "hook_shape": the number of the hook shape it is built on,
 "angle": one letter from the list,
 "citation": "...", "text": {"en": {"linkedin": "..."}, "bm": {"linkedin": "the same post in Malaysian Malay"}},
 "terms": [{"term": "a word or acronym the reader may not know", "meaning": "what it is, in one plain sentence"}],
 "visual_prompt": "an English description of one illustrative picture: no words, no logos, no real people, and NEVER a
 certificate, document, seal, stamp, label, packaging, screen, app or any object that has letters, numbers or symbols
 printed on it (image models garble them into nonsense).
 Draw the SUBJECT as a plain object, a scene or a simple illustration instead — for a certification or regulation story,
 draw the product, the ingredient or the setting, never the paperwork.",
 "alt": "short alt text in English"}
Set "fit" false (and say why) only when the story gives a chemist, RA or brand-owner peer nothing to use. A story does not need
a rule attached to be worth a post: judge it in its context (the audience, the angle, what they could take from it)."""


SLIDES_RULES = {
    "regulab": """

SLIDES WANTED. Also return "slides": a carousel in Malaysian Malay of AT MOST 7 slides in all (Wan, 23 Nov 2026: a carousel is
under 10 pictures: Semasa adds the brand cover and the closing logo card, so 7 is the most you write; fewer is better), drawn as
1080x1080 cards. Compact the story: join facts that belong together into one slide instead of one slide for each, and write every
slide in short, plain, complete sentences a reader understands at once:
[{"title": "...", "lead": "...", "points": ["...", "..."], "foot": "Definisi: term = meaning"}, ...]
- Slide 1 is the cover: its headline IS the hook (the same hook shape you filled for the caption's first line, no underscores,
  no figure the SOURCE does not give), at most 12 words, no "lead", "points" empty or one short line, no "foot". It is drawn
  very large. Semasa draws it as the brand cover only, so slide 2 is page one of the story: its headline and words must say
  something NEW, never the hook again in other words.
- "foot" (FACTS FIRST rule 4a) is the slide's small definition note: "Definisi: term = meaning", up to 2 terms that appear on
  that slide, "" when none; never on the cover or the last slide.
- Each middle slide is a FULL card, never a bare one: a title of at most 8 words, a "lead" (one sentence of at most 22 words that
  says the point plainly) and 3 to 4 "points" of at most 16 words each: one fact taken apart. Never pad: if the SOURCE gives less,
  write fewer points; a short slide is enlarged by the drawing.
- The last slide is the takeaway, stated plainly. It is NOT a call to action.
- Mark the one key word of a title with *asterisks* for emphasis, at most once per title.
- Every rule above applies to every slide: no call to action, no URL or website, no news portal or social source,
  and no fact that is not in the SOURCE. The source line is added to the last
  slide from "citation" automatically, so do not write it into a slide.
- AYAT AL-QURAN, only when the idea asks for a reminder (peringatan, tazkirah) or the post is a fatwa or halal post that
  one verse genuinely anchors: ONE slide may carry "ayat": "surah:ayat" (for example "ayat": "2:168", or "2:168-169" for at
  most 3 ayat), with a short "title" such as "Peringatan" and no points. Semasa fetches the Arabic and the translation
  itself and draws them. YOU NEVER WRITE A VERSE: no Arabic script anywhere, and no translation of a verse in quotation
  marks, on a slide or in the caption. Name it by surah and number (Al-Baqarah 2:168) and say in your own words what the
  post draws from it. Use a verse only when you are certain of its surah and ayat number; when unsure, use none. Never
  more than one verse slide, never the cover, and never a verse on a post about a product, a fee or a deadline.""",
    "linkedin": """

SLIDES WANTED. Also return "slides": a carousel in English of AT MOST 9 slides in all (Wan, 23 Nov 2026: a carousel is under 10
pictures; fewer is better), drawn as 1080x1350 cards. Compact the story: join facts that belong together into one slide
instead of one slide for each, and write every slide in short, plain, complete sentences a reader understands at once:
[{"title": "...", "lead": "...", "points": ["...", "..."], "foot": "Definition: term = meaning"}, ...]
- Slide 1 is the cover: its headline IS the hook (the same hook shape you filled for the caption's first line, no underscores,
  no figure the SOURCE does not give), at most 12 words, no "lead", "points" empty or one short line, no "foot". It is drawn
  very large.
- "foot" (FACTS FIRST rule 4a) is the slide's small definition note: "Definition: term = meaning", up to 2 terms that appear on
  that slide, "" when none; never on the cover or the last slide.
- Each middle slide is a FULL card, never a bare one: a title of at most 9 words, a "lead" (one sentence of at most 22 words that
  says the idea plainly) and 3 to 4 "points" of at most 18 words each: one idea taken apart. Never pad: if the SOURCE gives less,
  write fewer points; a short slide is enlarged by the drawing.
- The last slide is the takeaway. Never a question, never a call to action.
- Mark the one key word of a title with *asterisks* for emphasis, at most once per title.
- English only on every slide, the cover and the last slide included: the Malay hook shapes are translated, never printed.
- No company identity, no URL, no blog or aggregator, and no fact the SOURCE does not give. The citation is added
  to the last slide automatically.
- AYAT AL-QURAN, only when the idea itself asks for a verse or a reminder: ONE slide may carry "ayat": "surah:ayat" (for
  example "ayat": "2:168", or "2:168-169" for at most 3 ayat), with a short "title" such as "A reminder" and no points.
  The Arabic and the translation are fetched and drawn for you. YOU NEVER WRITE A VERSE: no Arabic script anywhere, and no
  translation of a verse in quotation marks, on a slide or in the caption. Name it by surah and number (Al-Baqarah 2:168).
  Use a verse only when you are certain of its surah and ayat number; when unsure, use none. Never the cover.""",
}


# The Journal look (Wan, 23 Nov 2026): a hand-inked picture fills the middle of every slide, so a slide has room for a headline, a
# lead and one italic line, and no list of points. The set reads as one story (illustrated.py draws a picture per slide).
JOURNAL_RULES = """

JOURNAL LOOK. Every middle slide has a picture in the middle, so write the set as ONE STORY told slide by slide, and write each
middle slide ONLY as: a "title" of at most 10 words, a "lead" (one sentence of at most 20 words), "points": [] (none), and a
"note": ONE short closing line of at most 12 words that leads the reader to the next slide (the last slide's note is the plain
takeaway). Facts go in the title and the lead, with their figure, entry or date; nothing is left for a list. Keep "foot" for a
term that needs it. A slide that can be pictured (a person, a place, an object, a moment) reads better than an abstract one."""


# The Threads look (Codex review on #325): its set is checked by threads_slides.check, which refuses a set outside 2 to 5 pages, a
# cover hook over 16 words, more than 3 points on a page and a page over 420 characters, so the writer is told those limits.
THREADS_RULES = """

THREADS LOOK. This set is drawn as short Threads-style pages, so write EXACTLY 2 to 5 slides (never more than 5, whatever the
story holds: keep the strongest facts). The first slide is the cover: a "title" hook of at most 16 words. Each slide has at most 3
"points", and its "title" and "points" TOGETHER are at most 420 characters. Short plain sentences, one idea per slide."""


POSTER_RULES = {
    "regulab": """

POSTER WANTED. Also return "poster": ONE 4:5 poster in Malaysian Malay: {"eyebrow": "a 2 to 4 word label for the topic",
"title": "the hook: the same hook shape you filled for the caption's first line, at most 10 words", "lead": "one short line
under the title, at most 14 words", "points": [2 to 3 points of at most 12 words each: only the MOST important facts from the
SOURCE, each with its figure, entry, clause or date], "foot": "Definisi: term = meaning" (up to 2 terms the poster uses, ""
when none; FACTS FIRST rule 4a)}. A poster is read in three seconds (Wan, 22 Nov 2026: "jangan letak
semua info dalam 1 card, hanya info penting"): never put the whole story on it, the caption carries the rest. The title is
drawn big, the lead smaller and the points smallest, so keep each one to its own job. Mark the one key word of the title with
*asterisks*. The same rules apply to every word: no call to action, no follow line, no URL, no fact the SOURCE does not give.
The citation is drawn at its foot automatically.""",
    "linkedin": """

POSTER WANTED. Also return "poster": ONE 4:5 poster in English: {"eyebrow": "a 2 to 4 word topic label", "title": "the hook:
the same hook shape you filled for the caption's first line, at most 10 words", "lead": "one short line under the title, at most
14 words", "points": [2 to 3 points of at most 12 words each: only the most important facts, each with its figure, entry, clause
or date], "foot": "Definition: term = meaning" (up to 2 terms the poster uses, "" when none; FACTS FIRST rule 4a)}. A poster is
read in three seconds: never put the whole post on it, the caption carries the rest. Title big, lead
smaller, points smallest. Mark the one key word of the title with *asterisks*. No company identity, no URL, no blog or
aggregator, no fact the SOURCE does not give. The citation is drawn at its foot automatically.""",
}


# The shortest a caption may be before the writer is asked once more for MORE FACTS (Wan, 21 Nov 2026: "tambahkan lagi fakta,
# termasuk ws regulab, jangan bagi caption yang pendek sangat"). It never fails a post: the second answer is used only
# when longer.
CAPTION_FLOOR = {"regulab": ("instagram", 900), "linkedin": ("linkedin", 1500)}


def caption_short(text: dict[str, Any], stream: str, lang: str) -> tuple[int, int] | None:
    """(length, floor) when the post's main caption is under its floor, else None."""
    key, floor = CAPTION_FLOOR.get(stream, ("", 0))
    have = len(str(((text or {}).get(lang) or {}).get(key) or "").strip())
    return (have, floor) if floor and 0 < have < floor else None


def ask_longer(have: int, floor: int, stream: str) -> str:
    return (f"\n\nYOUR LAST CAPTION WAS TOO SHORT ({have} characters; at least {floor}). Write the whole answer again in "
            "the same "
            "JSON, the same hook shape, and add MORE FACTS from the SOURCE: every figure, name, date, clause, who it covers and "
            "what it means in practice, numbered \"1. ... 2. ...\", each one complete. Add nothing the SOURCE does not say.")


def format_of(idea: dict[str, Any]) -> str:
    """What the idea should become besides its caption: 'carousel' (slides, the default), 'poster' / 'card' (ONE artwork, only
    when Wan chooses it) or 'comic' (a four-panel dialogue comic as the post's one picture). There is no AI-picture-only post any
    more. make_slides (006) still means a carousel; the choice itself rides in the idea's brief."""
    fmt = str(((idea.get("brief") or {}) if isinstance(idea.get("brief"), dict) else {}).get("format") or "")
    if fmt in ("carousel", "poster", "card", "comic"):
        return fmt              # "card": a single Studio card (Wan, 22 Nov 2026: "tambah option poster/single card")
    # no more single-picture post (Wan, 21 Nov 2026: "for ws regulab and linkend no more image single card, because it too ugly"),
    # and every post is a carousel with the worker's illustrations unless Wan chooses a single card (23 Nov 2026: "all post
    # must auto appear carousel ... only if I choose single card, then render new"): an idea that names no format is a carousel
    return "carousel"


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


# LinkedIn takes a news story only when it is about an authority's act (Wan, 20 Nov 2026: "for linkedn, no need include idea from
# recent issue unless berkaitan regulatory, circular from authority etc"): a circular, a guideline, a law or its amendment, a
# recall, a ban, a seizure, a licence or registration, an approval, an enforcement notice, a standard, a fatwa, a named regulator.
AUTHORITY = re.compile(
    r"\b(?:pekeliling|circular|garis\s+panduan|guideline|guidelines|guidance|peraturan|regulations?|regulatory|regulator|akta|"
    r"act\s+\d|pindaan|amendments?|enactment|gazette|warta|direktif|directive|notis|notice|"
    r"laws?|undang-undang|legislation|npra|bkkm|fsqd|jakim|sirim|"
    r"fda|efsa|sccs|echa|opss|hsa|tga|nmpa|mfds|"
    r"ditarik\s+balik|tarik\s+balik|recall(?:s|ed)?|larangan|dilarang|ban(?:s|ned)?|rampas|dirampas|seiz(?:e|es|ed|ure|ures)|"
    r"lesen|licen[cs]e[sd]?|pendaftaran|registration|notifikasi|notification|kelulusan|approv(?:al|ed)|diluluskan|"
    r"penguatkuasaan|enforcement|saman|compound|piawaian|standards?|iso\s*\d|fatwa|pensijilan|certification|sijil\s+halal)\b",
    re.I)


def linkedin_news_gate(idea: dict[str, Any], source: dict[str, Any]) -> str:
    """"" when the idea may be written for LinkedIn; else the reason it may not. Only a NEWS story (a headline from the issue
    feed, `trend_id`) is judged: a regulator's notice, a paper, a website or a folder row, and anything Wan wrote a note on
    (his own words are his decision), pass. A headline with no authority in it is not written, and no writer is paid for it."""
    if (idea.get("stream") or "regulab") != "linkedin" or not idea.get("trend_id"):
        return ""
    if str(idea.get("note") or "").strip():
        return ""
    brief = idea.get("brief") if isinstance(idea.get("brief"), dict) else {}
    if brief.get("source_kind") == "regulator":
        return ""
    hay = " ".join(str(x or "") for x in (idea.get("source_title"), idea.get("source_summary"), source.get("title"),
                                           str(source.get("description") or "")[:600]))
    if AUTHORITY.search(hay):
        return ""
    return ("LinkedIn takes a news story only when it is about a regulation, a circular or another act of an authority, and this "
            "headline is not (Wan, 20 Nov 2026). Add a note saying what you want from it to write it anyway.")


def build_request(idea: dict[str, Any], source: dict[str, Any], brand: dict[str, Any],
                  avoid: str = "", writer: dict[str, Any] | None = None,
                  bank: hook_bank.Bank | None = None, hint: str = "", style_block: str = "") -> tuple[str, str]:
    stream = idea.get("stream") or "regulab"
    if stream == "linkedin":
        angles = (brand.get("linkedin") or {}).get("angles") or {}
        system = LINKEDIN_SYSTEM % "; ".join(f"{k} = {v}" for k, v in sorted(angles.items()))
    else:
        system = REGULAB_SYSTEM % DOMAINS
    system += "\n\n" + VAGUE_CHECK
    system += "\n\n" + facts_first(stream)
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
    if stream == "linkedin" and issuer and str(idea.get("source_url") or "").startswith("http"):
        # the regulator's or the journal's own page may go under the citation as the source link (Wan, 22 Nov 2026)
        lines.append(f"SOURCE ADDRESS: {idea['source_url']} (the issuer's own page: it may go under the citation as the "
                     "source link)")
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
    if flags.get("announcement"):
        lines.append(
            "ANNOUNCEMENT BY A REGULATOR OR THE GOVERNMENT (FACTS FIRST rule 2). The SOURCE below is the issuer's own notice: "
            "open the post with WHO announced WHAT and, when the SOURCE gives it, FROM WHEN it applies, so the reader is "
            "alerted at once, then what it means for them in plain words. Use the notice's own reference only if the SOURCE "
            "prints it.")
    elif flags.get("source_priority") == "official":
        lines.append("OFFICIAL SOURCE (FACTS FIRST): every claim comes from this source's own words; name the issuing body.")
    if stream == "linkedin" and idea.get("trend_id"):
        lines.append("NEWSPAPER STORY ON LINKEDIN (Wan, 20 Nov 2026). This stream takes a news story only when it is about an "
                     "act of an authority: a circular, a guideline, a regulation or its amendment, a recall, a ban, a seizure, "
                     "a licence, an approval, an enforcement notice or a standard. If the story is about a person, an accident, "
                     "an award, a business or an event with no authority's instrument in it, answer "
                     "{\"fit\": false, \"why_not\": \"what is missing\"} and write nothing.")
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


def fit_caption(text: str, limit: int) -> str:
    """A caption over its platform's hard limit brought under it by whole paragraphs from the end of the body (caption_fit)."""
    return caption_fit.fit_caption(text, limit)


def fit_captions(text: dict[str, dict[str, str]], stream: str) -> dict[str, dict[str, str]]:
    """Every caption of the post inside its platform's hard limit, a Threads chain included (caption_fit; Wan, 22 Nov 2026:
    "Make sure caption untuk semua platform di bawah maksimum aksara dibenarkan")."""
    return caption_fit.fit_text(text, stream)


# --- definitions: the footnote on the artwork and the paragraph at the end of the caption (Wan, 22 Nov 2026) ----------------

def _appears(term: str, body: str) -> bool:
    """Does the term a footnote defines appear in the words of the slide it sits on? A glossary term by any of its forms, any
    other term as the writer wrote it."""
    e = glossary.lookup(term)
    if e:
        return any(x["id"] == e["id"] for x, _ in glossary.used(body, scan_only=False))
    return " ".join(term.lower().split()) in " ".join(body.lower().split())


def clean_feet(items: list[dict[str, Any]], lang: str) -> list[dict[str, Any]]:
    """The `foot` of every slide (or of a poster) made safe, and filled where the writer left a glossary term unexplained:
      * the cover and the last slide of a carousel carry none (a lone poster or card carries its own);
      * a glossary term always takes the glossary's own wording, a term of the writer's own is kept only when short;
      * only terms that appear on that slide stay, at most two, and a slide that uses a glossary term its foot does not define
        gets it added (the writer is asked, the code makes sure).
    The caption's Definisi paragraph is built from what is left (build_definitions)."""
    n = len(items)
    out: list[dict[str, Any]] = []
    for i, sl in enumerate(items):
        base = {k: v for k, v in sl.items() if k != "foot"}
        if (n > 1 and i in (0, n - 1)) or sl.get("ayat"):
            out.append(base)                       # the cover, the closing slide and a verse card
            continue
        body = compliance.slide_body(sl)
        pairs = [(t, m) for t, m in glossary.pairs_of(str(sl.get("foot") or "")) if _appears(t, body)]
        have = {e["id"] for t, _ in pairs if (e := glossary.lookup(t))}
        pairs += [(glossary.label(e, lang), glossary.meaning(e, lang)) for e, _ in glossary.used(body) if e["id"] not in have]
        foot = glossary.clean_foot([{"term": t, "meaning": m} for t, m in pairs], lang)
        out.append({**base, "foot": foot} if foot else base)
    return out


def build_definitions(text_slides: list[dict[str, Any]], lang: str, cap: int = glossary.CAPTION_TERMS) -> str:
    """The caption's end paragraph from the slides' footnotes: "Definisi: term = meaning; term2 = meaning." ("Definition:" in
    English), every term once in the order the slides use them, at most `cap`. "" when no slide carries a footnote."""
    pairs = [p for sl in text_slides for p in glossary.pairs_of(str(sl.get("foot") or ""))]
    return _capped(pairs, lang, cap)


def _capped(pairs: list[tuple[str, str]], lang: str, cap: int) -> str:
    kept = glossary.clean_pairs(pairs, lang)[:cap]
    return glossary.build_paragraph(kept, lang)


def caption_definitions(caption: str, feet: list[tuple[str, str]], lang: str, native: bool, cap: int) -> str:
    """One caption with its Definisi paragraph: the terms on the artwork first, then every glossary term the caption itself uses,
    then any the writer defined (a term of its own only in the post's own language). Placed before the follow line and the
    hashtags. A caption with nothing to define loses an empty paragraph and is otherwise untouched."""
    body = glossary.strip_definisi(caption)
    mine = [p for para in glossary.definisi_paragraphs(caption) for p in glossary.pairs_of(para)]
    pairs = list(feet) + [(glossary.label(e, lang), glossary.meaning(e, lang)) for e, _ in glossary.used(body)] + mine
    if not native:
        pairs = [(t, m) for t, m in pairs if glossary.lookup(t)]        # a term of the writer's own is not translated
    paragraph = _capped(pairs, lang, cap)
    if not paragraph:
        return "\n\n".join(p for p in re.split(r"\n\s*\n", caption) if not glossary.DEF_HEAD.match(p)) if mine else caption
    return glossary.place_in_caption(caption, paragraph)


def with_definitions(text: dict[str, dict[str, str]], slide_lists: list[list[dict[str, Any]]], stream: str,
                     lang: str) -> dict[str, dict[str, str]]:
    """Every caption of the post ({lang: {platform: caption}}) with its Definisi paragraph. A Threads chain takes two terms (the
    paragraph rides on its last post); fit_captions afterwards keeps it and trims the body first."""
    feet = [p for lst in slide_lists for sl in lst for p in glossary.pairs_of(str(sl.get("foot") or ""))]
    out: dict[str, dict[str, str]] = {}
    for lg, inner in (text or {}).items():
        if not isinstance(inner, dict):
            out[lg] = inner
            continue
        out[lg] = {plat: caption_definitions(cap, feet, lg, lg == lang, 2 if plat == "threads" else glossary.CAPTION_TERMS)
                   if isinstance(cap, str) and cap.strip() else cap for plat, cap in inner.items()}
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


def taken_positions(store: Any, stream: str, now: datetime | None = None) -> set[tuple[str, str]]:
    """Slots a post of this stream holds from today (Malaysia time) on. `now` defaults to the real clock; a caller that was
    given a moment (video_import.slot_for) passes it, so what is "ahead" and what is "held" are judged at the same time."""
    today = ((now or datetime.now(UTC)) + MYT).date().isoformat()
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
    shut = linkedin_news_gate(idea, source)
    if shut:
        raise IdeaError(shut)
    bank = hook_bank.pick(store, idea, settings)        # a hook style made from screenshots, or None: the built-in 25
    hint = hook_learning.hint(store, bank)              # what has earned views and interaction so far (a hint, never a rule)
    family = str(idea.get("hook_family") or "").strip().lower() or None
    turn = rotation.turn_for(store, stream, bank, family)    # this post's hook shape: the turn goes round, never repeats
    hint = "\n".join(x for x in (hint, turn.hint()) if x)
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
    want_poster = fmt in ("poster", "card")      # a single card is written like a poster and drawn as one card
    if want_slides:
        system += SLIDES_RULES.get(stream, SLIDES_RULES["regulab"])
        if look_of(idea) == "journal":
            system += JOURNAL_RULES
        elif look_of(idea) == "threads":
            system += THREADS_RULES
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
    shape = hook_bank.declared(out, stream, family, bank)
    if shape is not None and turn.assigned and shape not in turn.permitted:
        # not this post's turn (Wan, 20 Nov 2026): one more ask, then what the writer gave stands, so a post is never lost to it
        again = llm.chat_json(system, user + turn.ask_again(), max_tokens=5000 if (want_slides or want_poster) else 3500)
        got = hook_bank.declared(again, stream, family, bank) if isinstance(again, dict) else None
        if again and again.get("fit") is not False and got in turn.permitted:
            out, shape = again, got
        else:
            log.info("idea %s: hook shape %s is not its turn (%s); kept", str(idea.get("id"))[:8], shape, turn.assigned)
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
    short = caption_short(text, stream, lang)
    if short:
        # too brief (Wan, 21 Nov 2026): one more ask for more facts; the longer answer is used only when it is still on this
        # post's hook shape, so the post is never lost to it
        again = llm.chat_json(system, user + ask_longer(*short, stream),
                              max_tokens=5000 if (want_slides or want_poster) else 3500)
        if isinstance(again, dict) and again.get("fit") is not False:
            got = hook_bank.declared(again, stream, family, bank)
            more = normalise_text(again.get("text"), stream, lang)
            longer = caption_short(more, stream, lang)
            if got is not None and (not turn.assigned or got in turn.permitted) and more.get(lang) \
                    and len(str(more[lang].get(CAPTION_FLOOR[stream][0]) or "")) > short[0]:
                out, shape, text = again, got, more
                log.info("idea %s: caption asked again for more facts (%s -> %s chars%s)", str(idea.get("id"))[:8], short[0],
                         len(str(text[lang].get(CAPTION_FLOOR[stream][0]) or "")), "" if not longer else ", still short")
    # grammar and spelling, in the post's own language, before anything is stored (Wan, 10 Nov 2026); never changes a fact
    text = fit_captions(text, stream)           # a caption over the platform's hard limit is trimmed by whole paragraphs
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
        # a model may NAME a verse, never write one: whatever verse text it returned is dropped, and the words are fetched
        # from the published source (quran.py). The tick that says Wan checked the verse is his alone, so the post is
        # written with a hard flag on that slide until he ticks it.
        written = quran.fill(slides.normalise(quran.untrusted(out.get("slides"))), stream)
        written = carousel.compact(written, stream)[0]            # under 10 pictures: a longer set is joined, no word lost
        post["slides"], cover_state = hook_bank.cover(written, post["hook"])
        if cover_state == "too_long":
            short = shorter_hook(llm, post["hook"], stream)
            if short:
                post["slides"], cover_state = hook_bank.cover(post["slides"], short)
                cover_state = "shortened" if cover_state in ("set", "kept") else "too_long"
    poster = slides.normalise(quran.untrusted([out.get("poster")]) if isinstance(out.get("poster"), dict) else [])[:1] \
        if want_poster else []
    poster = quran.fill(poster, stream)
    if poster:
        poster, cover_state = hook_bank.cover(poster, post["hook"])
        if cover_state == "too_long":
            short = shorter_hook(llm, post["hook"], stream)
            if short:
                poster, cover_state = hook_bank.cover(poster, short)
                cover_state = "shortened" if cover_state in ("set", "kept") else "too_long"
    if (not kept and idea.get("make_media") != "none" and fmt in ("poster", "card", "carousel")
            and not poster and not post.get("slides")):
        # the writer gave neither slides nor a poster (Wan, 23 Nov 2026: "for semasa linkedin post, make sure its poster not
        # only generated image"): the post is never left with an AI picture alone. The poster is asked for on its own, from the
        # caption just written, and failing that built from the caption's own words.
        poster = poster_for_post(llm, post, stream, lang)
        cover_state = "fallback"
    # the technical terms (Wan, 22 Nov 2026): a footnote on every slide and the poster that needs one, and ONE Definisi
    # paragraph at the end of every caption, built from them and from the glossary terms the caption itself uses; the paragraph
    # is placed before the follow line and the hashtags and the caption is fitted to its platform's limit again
    if post.get("slides"):
        post["slides"] = clean_feet(post["slides"], lang)
    if poster:
        poster = clean_feet(poster, lang)
    drawn_words = [x for x in (post.get("slides"), poster) if x]
    post["text"] = fit_captions(with_definitions(post["text"], drawn_words, stream, lang), stream)
    text = post["text"]
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

    if fmt in ("carousel", "poster", "card") and not str(brief0.get("look") or "").strip():
        # no look chosen: the Semasa poster looks take their turn and never repeat (Wan, 20 Nov 2026), unless Wan saved a
        # "My design" as the default, which is then the one new drafts use
        dd = settings.get("default_design") if isinstance(settings.get("default_design"), dict) else {}
        if not dd.get("id"):
            idea = {**idea, "brief": {**brief0, "look_auto": True,
                                      "look": rotation.next_look(store, stream, dd.get("hidden"), carousel=fmt == "carousel")}}
    chosen = my_designs.for_idea(store, idea)      # the idea's look, or the default "My design" when it asked for none
    if fmt == "comic":
        # the comic IS the post's picture (17 Nov 2026): no other picture is made for it
        jobs = [] if has_jobs or kept else [comic_job(idea, post, post_id)]
    else:
        jobs = []         # no AI picture beside the slides or the poster (Wan, 21 Nov 2026): it was the "ugly single card"
    if want_slides and post.get("slides") and not has_jobs:
        jobs.append(slide_job(idea, post, post_id, bg=slide_ground(stream, bool(jobs or kept)), chosen=chosen))
    if poster and not has_jobs:
        jobs.append(poster_job(idea, post, post_id, poster, bg=slide_ground(stream, bool(jobs or kept)), chosen=chosen,
                               design="card" if fmt == "card" else "poster"))
    if not jobs and not has_jobs and not kept and fmt not in ("comic", "poster", "card", "carousel"):
        # an AI picture on its own is never a post's artwork any more (Wan, 21 and 23 Nov 2026): only an idea that names no
        # poster, card or carousel can reach this, and format_of gives every idea one of them
        jobs = media_jobs(idea, source, out, post_id)
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
    system += "\n\n" + VAGUE_CHECK          # a revision is checked by the same rule as a first draft
    system += "\n\n" + facts_first(stream)
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
    # the slides stay as they are, so their footnotes are what the rewritten caption's Definisi paragraph is built from
    text = caption_fit.fit_text(with_definitions(text, [post.get("slides") or []], stream, lang), stream)
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

POSTER_FROM_CAPTION = (
    "You turn a finished social-media caption into the words of ONE 4:5 poster. "
    "Answer with ONE JSON object: {\"poster\": {\"eyebrow\": \"a 2 to 4 word topic label\", "
    "\"title\": \"the hook, at most 10 words, one key word marked with *asterisks*\", "
    "\"lead\": \"one short line under the title, at most 14 words\", "
    "\"points\": [2 to 3 points of at most 12 words each: the most important facts of the caption, "
    "each with its figure, entry, clause or date], \"foot\": \"\"}}. "
    "Use ONLY what the caption says: add no fact, no figure, no name. "
    "No call to action, no follow line, no URL. Write in %s.")


def poster_for_post(llm: LLM, post: dict[str, Any], stream: str, lang: str) -> list[dict[str, Any]]:
    """The poster words for a post that has none: the writer is asked for them alone from the post's own caption (nothing new
    can come in); if that gives nothing, the poster is built from the caption's own numbered facts. Never empty while the post
    has a hook, so a poster is always drawn (Wan, 23 Nov 2026)."""
    plat = "linkedin" if stream == "linkedin" else "instagram"
    caption = str(((post.get("text") or {}).get(lang) or {}).get(plat) or "")
    hook = " ".join(str(post.get("hook") or "").split())
    tongue = "natural English" if stream == "linkedin" else "casual Malaysian Malay (never Bahasa Indonesia)"
    got: list[dict[str, Any]] = []
    try:
        out = llm.chat_json(POSTER_FROM_CAPTION % tongue, f"HOOK: {hook}\n\nCAPTION:\n{caption[:3500]}", max_tokens=900)
        if isinstance(out, dict) and isinstance(out.get("poster"), dict):
            got = slides.normalise([out["poster"]])[:1]
    except Exception as exc:  # noqa: BLE001 - the words built from the caption below always stand in
        log.info("poster asked from the caption: %s", str(exc)[:120])
    if got and stream == "linkedin" and language.is_malay(compliance.slide_body(got[0])):
        got = []                                       # LinkedIn is English only
    if not got:
        got = [poster_from_caption(hook, caption, llm, stream)]
    got, _ = hook_bank.cover(got, hook)
    return got


def poster_from_caption(hook: str, caption: str, llm: LLM | None, stream: str) -> dict[str, Any]:
    """A poster built only from the caption's own words: the hook as the title (shortened when too long for a headline),
    and up to three of its numbered facts, each its first complete sentence, kept only when short enough to read in three
    seconds. No new word is written."""
    title = hook
    if len(title.split()) > 10:
        short = shorter_hook(llm, hook, stream, words=10) if llm is not None else ""
        title = short or " ".join(title.split()[:10]).rstrip(",;:-")
    points: list[str] = []
    for m in re.finditer(r"(?m)^\s*\d{1,2}[.)]\s*(.+)$", caption):
        first = re.split(r"(?<=[.!?])\s", m.group(1).strip())[0].strip()
        if first and len(first.split()) <= 16:
            points.append(first)
        if len(points) == 3:
            break
    return {"title": title, "points": points}


def poster_job_for_draft(store: Any, post: dict[str, Any], words: list[dict[str, Any]]) -> dict[str, Any]:
    """The Design job that draws a poster for a draft that has none, in the look the Semasa rotation gives it."""
    idea = {"id": post.get("idea_id"), "brief": {}, "created_by": post.get("created_by")}
    stream = post.get("stream") or "regulab"
    idea["brief"] = {"look": rotation.next_look(store, stream, None, carousel=False), "format": "poster"}
    return poster_job(idea, post, post["id"], words, bg=slide_ground(stream, False), chosen=(look_of(idea), None))


def repair_picture_only(store: Any, llm: LLM, limit: int = 3) -> str:
    """A LinkedIn DRAFT whose only picture is an AI image (a poster the writer never returned) gets its poster (Wan, 23 Nov
    2026: "for semasa linkedin post, make sure its poster not only generated image"). The poster is made from the draft's own
    caption, the AI picture comes off the post and a new job draws the poster. A draft only: an approved post is what Wan
    approved, and the worker never touches it."""
    try:
        drafts = (store.table(db.POSTS).select("*").eq("stream", "linkedin").eq("status", "draft").limit(60).execute().data
                  or [])
    except Exception as exc:  # noqa: BLE001 - a read that fails must not stop the writing step
        return f"Poster repair: skipped ({str(exc)[:80]})"
    fixed = 0
    for post in drafts:
        ids = [str(x) for x in (post.get("media_ids") or [])]
        if not ids or fixed >= limit:
            continue
        rows = store.table(db.MEDIA).select("id,mode,status,meta").in_("id", ids).execute().data or []
        if len(rows) != len(ids) or any(r.get("mode") not in ("prompt", "recreate") for r in rows):
            continue                                   # a poster, slides, a comic or a kept picture: nothing to repair
        try:
            lang = post.get("lang") or "en"
            words = poster_for_post(llm, post, "linkedin", lang)
            job = poster_job_for_draft(store, post, words)
            got = store.table(db.POSTS).update({"media_ids": []}).eq("id", post["id"]).eq("status", "draft").execute().data
            if not got:
                continue                               # approved meanwhile
            store.table(db.MEDIA).insert(job).execute()
            fixed += 1
            db.log_event(store, "info", "post", "post.poster_repaired",
                         "LinkedIn draft had only an AI picture: its poster is being drawn from its own caption",
                         ref_table="semasa_posts", ref_id=post["id"])
        except Exception as exc:  # noqa: BLE001 - recorded; the next run tries again
            log.warning("poster repair of %s: %s", str(post.get("id"))[:8], str(exc)[:160])
    return f"Poster repair: {fixed} LinkedIn draft(s) given a poster" if fixed else "Poster repair: none needed"


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
    elif (bg == "none" and studio_cards.is_studio_look(look) and look not in OWN_PICTURE_ONLY
          and not (saved and saved.get("layouts"))):
        bg = cards_library.default_ground(post.get("stream") or "regulab", post.get("domain"), post.get("angle")) or "none"
    return {"idea_id": idea["id"], "post_id": post_id, "type": "image", "mode": "slides", "status": "pending",
            "prompt": "", "created_by": idea.get("created_by"),
            "meta": {"flow": "A", "slides": post.get("slides") or [], "stream": post.get("stream"),
                     **({"design": "threads", "format": "portrait"} if look == "threads" else {}),
                     "citation": post.get("citation") or "", "domain": post.get("domain"),
                     "angle": post.get("angle"), "bg": bg, "look": look, "fit": look != "classic",
                     **({"look_auto": True} if look_auto(idea) else {}),
                     **({"review": review} if review else {}), **({"design_pack": saved} if saved else {})}}


def look_auto(idea: dict[str, Any]) -> bool:
    """True when the look was taken from the rotation, not chosen by Wan: a look that cannot be drawn then gives way."""
    brief = idea.get("brief") if isinstance(idea.get("brief"), dict) else {}
    return bool(brief.get("look_auto"))


def slide_ground(stream: str, has_picture: bool) -> str:
    """What sits behind a slide: the post's own picture, blurred, when it has one, except on LinkedIn, whose slides are plain
    cream paper (Wan, 21 Nov 2026: "I want like this for linkedn": a serif title over sans text, the source at the foot)."""
    return "post_image" if has_picture and stream != "linkedin" else "none"


def poster_job(idea: dict[str, Any], post: dict[str, Any], post_id: str, words: list[dict[str, Any]],
               bg: str = "none", chosen: tuple[str, dict[str, Any] | None] | None = None,
               design: str = "poster") -> dict[str, Any]:
    """The idea's poster: a Design job (one 4:5 artwork) attached to its draft, in the look chosen on the idea."""
    look, saved = chosen or (look_of(idea), None)
    review: dict[str, Any] = {}
    if bg == "none" and saved and saved.get("bg"):
        bg = saved["bg"]
    elif bg == "none" and saved and saved.get("bg_prompt"):
        bg, review = "from_ref", {"background": saved["bg_prompt"]}
    return {"idea_id": idea["id"], "post_id": post_id, "type": "image", "mode": "slides", "status": "pending",
            "prompt": "", "created_by": idea.get("created_by"),
            "meta": {"flow": "A", "design": design, "format": "portrait", "slides": words, "stream": post.get("stream"),
                     "citation": post.get("citation") or "", "domain": post.get("domain"), "angle": post.get("angle"),
                     "bg": bg, "look": look, "fit": look != "classic",
                     **({"review": review} if review else {}), **({"design_pack": saved} if saved else {})}}


def comic_job(idea: dict[str, Any], post: dict[str, Any], post_id: str) -> dict[str, Any]:
    """The idea's comic: a Design job (comic_job.py) attached to its draft as the post's one picture. Its script is written
    by the comic's own writer from the post's words, which were written from the source under the post rules, so the comic
    states nothing the caption does not. The series and style picked on the idea ride in its brief ({"comic": {series,
    style}}); none picked means the library's defaults. The source goes under the comic when it fits there."""
    from . import comic
    brief = (idea.get("brief") or {}) if isinstance(idea.get("brief"), dict) else {}
    pick = brief.get("comic") if isinstance(brief.get("comic"), dict) else {}
    stream = post.get("stream") or "regulab"
    lang = post.get("lang") or ("en" if stream == "linkedin" else "bm")
    words = (post.get("text") or {}).get(lang) or {}
    caption = str(words.get("linkedin" if stream == "linkedin" else "instagram") or next(iter(words.values()), "") or "")
    citation = " ".join(str(post.get("citation") or "").split())
    told = "\n\n".join(x for x in (str(post.get("hook") or "").strip(), caption.strip(),
                                    f"Source: {citation}" if citation else "") if x)
    return {"idea_id": idea["id"], "post_id": post_id, "type": "image", "mode": "slides", "status": "pending",
            "prompt": "", "created_by": idea.get("created_by"),
            "meta": {"flow": "A", "design": "comic", "format": "portrait", "stream": stream, "brief": told[:4000],
                     "citation": citation if len(citation) <= comic.MAX_SOURCE else "",
                     "comic": {"series": str(pick.get("series") or ""), "style": str(pick.get("style") or ""),
                               "words_mode": "auto"}}}


LOOKS = ("classic", "grid", "era", "photo", "image", "threads", "hand", "marker", "torn", "block", "neon",
         "deck", "chalk", "metro", "strip", "journal")
# looks that show a picture ON the slide (Image, and the cover of the four poster looks): only the post's own picture is ever
# placed there, never a stock ground from the library
OWN_PICTURE_ONLY = ("image", "marker", "torn", "block", "neon", "deck", "chalk", "metro", "strip", "journal")
DEFAULT_LOOK = "journal"        # Wan, 23 Nov 2026: Diari is the primary and main look for a carousel (was Image, 8 Nov 2026)
POSTER_DEFAULT_LOOK = "hand"    # Wan, 13 Nov 2026: a poster (format=poster) is the hand-drawn look by default


def look_of(idea: dict[str, Any]) -> str:
    """The carousel look chosen on the idea, carried in its brief ({"look": ...}) until the bot writes the draft:
    Semasa's own drawing ("classic"), Threads-style text + picture, or one of ws.regulab Studio's designs.
    No choice is the default look ("journal", Diari), except a poster or card, which defaults to the hand-drawn look ("hand"),
    and which never takes Diari (it draws a picture on every slide: a poster has one); a name nobody knows is "classic", the
    drawing that never needs a picture or the browser."""
    brief = (idea.get("brief") or {}) if isinstance(idea.get("brief"), dict) else {}
    raw = brief.get("look")
    one_picture = format_of(idea) in ("poster", "card")
    if raw and not (one_picture and str(raw) == "journal"):
        look = str(raw)
    elif one_picture:
        look = POSTER_DEFAULT_LOOK
    else:
        look = DEFAULT_LOOK
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
    log.info("%s", fill)                                    # the run's log said nothing about autofill before (26 Nov 2026)
    repair = repair_picture_only(store, llm) if llm.configured else "Poster repair: waiting for a writer"
    return "\n".join([fill, run(store, llm), revise_posts(store, llm), repair])
