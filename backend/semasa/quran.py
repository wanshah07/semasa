"""Ayat al-Quran on a card (Wan, 16 Nov 2026: "make sure can write ayat al-Quran for reminder or under fatwa").

THE VERSE IS NEVER TYPED BY A WRITER, HUMAN OR AI. A slide names a verse by surah:ayat ("2:168", or "2:168-169" for up to
`max_span` ayat). This module fetches the Arabic (Uthmani script) and the translation for the post's stream from a published
source and stores them on the slide. Anything a model returned in the text fields is thrown away first (`untrusted`), so the
only way a verse's words reach a post is through `fetch`.

Two published sources: alquran.cloud (the Tanzil Uthmani text, translations by edition id) and quran.com (the same
translations by their id there). Both were read on 16 Nov 2026 and agree on the 114 surahs and their 6,236 ayat
(rules/compliance.json, "quran"). The Arabic prefers alquran.cloud; the translation asks them in the order its edition
names. When both answered, their Arabic is compared letter for letter and a verse they disagree on is refused.

The page mirrors the reference rules and the fetch in web/src/lib/quran.js; the scan (compliance.py / compliance.js) blocks a
verse slide whose reference does not exist, whose text has not been fetched, or that Wan has not ticked as checked.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any

import httpx

from . import compliance

log = logging.getLogger(__name__)

RULES: dict[str, Any] = compliance.RULES["quran"]       # one copy, in rules/compliance.json, read by the page too
SURAHS: list[list[Any]] = RULES["surahs"]
MAX_SPAN: int = RULES["max_span"]
BISMILLAH: str = RULES["bismillah"]
ARABIC_FROM = "alquran.cloud"            # the Tanzil Uthmani text; quran.com's stands in only when this one cannot answer
REF = re.compile(r"^(\d{1,3}):(\d{1,3})(?:-(\d{1,3}))?$")
TEXT_KEYS = ("ayat_ar", "ayat_tr", "ayat_ed", "ayat_ok", "ayat_label")     # what only this module (and Wan's tick) may set
CLOUD = "https://api.alquran.cloud/v1/ayah/{key}/editions/{arabic},{edition}"
QURAN_COM = "https://api.quran.com/api/v4/verses/by_key/{key}?translations={tid}&fields=text_uthmani"
_TAG = re.compile(r"<sup[^>]*>.*?</sup>|<[^>]+>", re.S)


class QuranError(ValueError):
    """A verse that cannot be used as asked; the message is shown to Wan."""


def parse(ref: Any) -> tuple[int, int, int] | None:
    """(surah, first ayat, last ayat) of a reference that exists, else None. "2:168" and "2:168-169" are references;
    a surah or ayat that does not exist, a range that runs backwards and one longer than MAX_SPAN are not."""
    m = REF.match(str(ref or "").strip())
    if not m:
        return None
    surah, first = int(m.group(1)), int(m.group(2))
    last = int(m.group(3)) if m.group(3) else first
    if not 1 <= surah <= len(SURAHS):
        return None
    count = int(SURAHS[surah - 1][1])
    if not (1 <= first <= last <= count) or last - first + 1 > MAX_SPAN:
        return None
    return surah, first, last


def label(ref: Any) -> str:
    """How a reference is written on the card: "Al-Baqarah 2:168". "" for a reference that does not exist."""
    p = parse(ref)
    if not p:
        return ""
    surah, first, last = p
    return f"{SURAHS[surah - 1][0]} {surah}:{first}" + (f"-{last}" if last != first else "")


def edition(stream: str) -> dict[str, Any]:
    return RULES["editions"]["linkedin" if stream == "linkedin" else "regulab"]


def skeleton(arabic: Any) -> str:
    """The letters of an Arabic text with every mark removed. The sources write the same Uthmani words with different marks
    (a dagger alif on a tatweel at one, without it at the other; the Bismillah before a surah marked differently from the
    Bismillah that is Al-Fatihah 1), so anything that compares Arabic compares letters, never code points."""
    # tatweel is a carrier with no sound; alif wasla is an alif; a hamza written on the line at one source is a hamza mark
    # on a tatweel at the other (the word "al-akhirah" in 34:1), so it is dropped like every other mark
    t = unicodedata.normalize("NFD", str(arabic or "")).replace("\u0640", "").replace("\u0671", "\u0627").replace("\u0621", "")
    return "".join(ch for ch in t if unicodedata.category(ch) in ("Lo", "Nd"))


_BISMILLAH = [skeleton(w) for w in BISMILLAH.split()]


def clean_arabic(text: str, surah: int, ayat: int) -> str:
    """The ayat as the source gives it, minus two things that are not part of it: a byte-order mark, and the Bismillah that
    alquran.cloud puts in front of ayat 1 of every surah. In Al-Fatihah the Bismillah IS ayat 1 and is kept. The four words
    are recognised by their letters: the source marks them differently from the constant in the rules, so an exact
    string match left the Bismillah on 112:1 (found on 16 Nov 2026 by comparing the two sources letter for letter)."""
    words = str(text or "").replace("\ufeff", "").split()
    n = len(_BISMILLAH)
    if ayat == 1 and surah != 1 and len(words) > n and [skeleton(w) for w in words[:n]] == _BISMILLAH:
        words = words[n:]
    return " ".join(words)


def clean_translation(text: str) -> str:
    """A translation as the source gives it, minus footnote markers and markup (quran.com sends <sup> footnotes)."""
    return re.sub(r"\s+", " ", _TAG.sub("", str(text or "")).replace("﻿", "")).strip()


def _get(url: str, client: Any) -> Any:
    r = client.get(url, timeout=20, headers={"Accept": "application/json", "User-Agent": "semasa-cards/1"})
    if r.status_code != 200:
        raise QuranError(f"HTTP {r.status_code}")
    return r.json()


def _from_cloud(surah: int, ayat: int, ed: dict[str, Any], client: Any) -> tuple[str, str]:
    data = _get(CLOUD.format(key=f"{surah}:{ayat}", arabic=RULES["arabic"]["edition"], edition=ed["id"]), client).get("data")
    by = {str((e.get("edition") or {}).get("identifier")): e for e in (data if isinstance(data, list) else [])}
    ar, tr = by.get(RULES["arabic"]["edition"]), by.get(ed["id"])
    for e in (ar, tr):
        # the answer must be the ayat that was asked for: the source's own surah and ayat numbers are checked, not assumed
        if not e or int((e.get("surah") or {}).get("number") or 0) != surah or int(e.get("numberInSurah") or 0) != ayat:
            raise QuranError("the source answered with a different ayat")
    return clean_arabic(ar.get("text"), surah, ayat), clean_translation(tr.get("text"))


def _from_quran_com(surah: int, ayat: int, ed: dict[str, Any], client: Any) -> tuple[str, str]:
    v = (_get(QURAN_COM.format(key=f"{surah}:{ayat}", tid=ed["quran_com"]), client) or {}).get("verse") or {}
    if str(v.get("verse_key")) != f"{surah}:{ayat}":
        raise QuranError("the source answered with a different ayat")
    trs = [t for t in (v.get("translations") or []) if int(t.get("resource_id") or 0) == int(ed["quran_com"])]
    if not trs:
        raise QuranError("the source has no such translation")
    return clean_arabic(v.get("text_uthmani"), surah, ayat), clean_translation(trs[0].get("text"))


SOURCES = {"alquran.cloud": _from_cloud, "quran.com": _from_quran_com}
ED = re.compile(r"^([a-z]{2}\.[a-z]{2,20})@(alquran\.cloud|quran\.com)$")


def _all(name: str, surah: int, first: int, last: int, ed: dict[str, Any], client: Any,
         why: list[str]) -> list[tuple[str, str]] | None:
    """Every ayat of a reference from ONE source, or None (with the reason added to `why`) when it cannot give them all."""
    out = []
    for n in range(first, last + 1):
        try:
            ar, tr = SOURCES[name](surah, n, ed, client)
        except (QuranError, httpx.HTTPError, ValueError, KeyError, TypeError) as e:
            why.append(f"{name}: {str(e) or type(e).__name__}")
            return None
        if not ar or not tr:
            why.append(f"{name}: empty text for {surah}:{n}")
            return None
        out.append((ar, tr))
    return out


def fetch(ref: Any, stream: str, client: Any = None) -> dict[str, str]:
    """{ayat, ayat_ar, ayat_tr, ayat_ed} for a reference: the Arabic and the stream's translation, one line per ayat.
    `ayat_ed` names the translation and the source that gave it ("ms.basmeih@alquran.cloud").
    Raises QuranError when the reference does not exist, when no source could give every ayat of it, or when both
    sources answered and their Arabic is not letter for letter the same."""
    p = parse(ref)
    if not p:
        raise QuranError(f'"{ref}" is not an ayat: write surah:ayat, for example 2:168 (at most {MAX_SPAN} ayat, e.g. 2:168-169)')
    surah, first, last = p
    ed = edition(stream)
    own = client is None
    client = client or httpx.Client(follow_redirects=True)
    try:
        why: list[str] = []
        got: dict[str, list[tuple[str, str]] | None] = {}
        tr_src = ""
        for name in ed["sources"]:
            got[name] = _all(name, surah, first, last, ed, client, why)
            if got[name]:
                tr_src = name
                break
        if not tr_src:
            raise QuranError(f"could not fetch {label(ref)} from a published source ({'; '.join(why)}). Try again.")
        if ARABIC_FROM not in got:
            got[ARABIC_FROM] = _all(ARABIC_FROM, surah, first, last, ed, client, why)
    finally:
        if own:
            client.close()
    arabic = got.get(ARABIC_FROM) or got[tr_src]
    both = [v for v in got.values() if v]
    if len(both) == 2 and [skeleton(a) for a, _ in both[0]] != [skeleton(a) for a, _ in both[1]]:
        raise QuranError(f"the two published sources do not give the same Arabic for {label(ref)}. It is not used.")
    return {"ayat": f"{surah}:{first}" + (f"-{last}" if last != first else ""), "ayat_ar": "\n".join(a for a, _ in arabic),
            "ayat_tr": "\n".join(t for _, t in got[tr_src]), "ayat_ed": f"{ed['id']}@{tr_src}"}


def _letters(text: Any) -> str:
    """A translation reduced to its letters and digits, accents folded: one source writes "Allah", the other "Allāh"."""
    t = unicodedata.normalize("NFKD", str(text or "").lower())
    return "".join(ch for ch in t if ch.isalnum())


def untrusted(raw: Any) -> Any:
    """Slides as a model returned them, with every verse text field removed: a model may NAME a verse, never write one."""
    if not isinstance(raw, list):
        return raw
    return [{k: v for k, v in s.items() if k not in TEXT_KEYS} if isinstance(s, dict) else s for s in raw]


def fill(slides: list[dict[str, Any]], stream: str, client: Any = None) -> list[dict[str, Any]]:
    """The slides with each named verse fetched. A verse that could not be fetched keeps its reference and no text, which
    the scan blocks ("the verse text has not been fetched"); it is never left for a model's words to stand in. The tick
    that says Wan checked the verse is never set here."""
    out = []
    for s in slides or []:
        if not (isinstance(s, dict) and s.get("ayat")):
            out.append(s)
            continue
        bare = {k: v for k, v in s.items() if k not in TEXT_KEYS}
        try:
            out.append({**bare, **fetch(s["ayat"], stream, client)})
        except QuranError as e:
            log.warning("quran: %s", e)
            out.append(bare)
    return out


def verify(slides: list[dict[str, Any]], stream: str, client: Any = None) -> None:
    """Before a verse slide is drawn: its stored words must equal what the published source gives now. Raises QuranError
    naming the slide when they differ. The Arabic is compared by its letters whichever source answers. The translation is
    compared only when the source that gave it answers again: the two sources carry different revisions of the English one.
    A source that cannot be reached is not a difference: the stored words came from `fetch`, and a network fault must not
    stop a post that was already checked."""
    for i, s in enumerate(slides or [], 1):
        if not (isinstance(s, dict) and s.get("ayat") and s.get("ayat_ar")):
            continue
        if parse(s["ayat"]) is None:
            raise QuranError(f'slide {i}: "{s["ayat"]}" is not an ayat')
        m = ED.match(str(s.get("ayat_ed") or ""))
        if not m or m.group(1) != edition(stream)["id"]:
            raise QuranError(f"slide {i}: the translation of {label(s['ayat'])} is not this stream's ({s.get('ayat_ed')}). "
                             "Fetch the verse again.")
        try:
            now = fetch(s["ayat"], stream, client)
        except QuranError as e:
            log.warning("quran: could not re-check slide %s (%s); drawing the stored verse", i, e)
            continue
        same_ar = [skeleton(x) for x in now["ayat_ar"].split("\n")] == [skeleton(x) for x in str(s["ayat_ar"]).split("\n")]
        same_tr = now["ayat_ed"] != s["ayat_ed"] or _letters(now["ayat_tr"]) == _letters(s.get("ayat_tr"))
        if not same_ar or not same_tr:
            raise QuranError(f"slide {i}: the words stored for {label(s['ayat'])} differ from the published source. "
                             "Fetch the verse again; it is not drawn as it stands.")
