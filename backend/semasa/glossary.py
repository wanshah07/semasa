"""The glossary of technical terms (rules/glossary.json) and everything that follows from it (Wan, 22 Nov 2026: "if got technical
terms, must have small foot note for definition in the poster/carousel/card, and end of caption").

A term a layperson would not know is explained twice, in the same words:
  * on the artwork, as the slide's `foot` ("Definisi: PIF = ..."; up to two terms, only terms that appear on that slide);
  * at the end of the caption, as ONE paragraph "Definisi: PIF = ...; NPRA = ..." placed before the follow line and the hashtags.
This module holds the data and the small tools both paths use: finding a glossary term in a text, reading a `foot` or a Definisi
paragraph back into terms, cleaning a footnote the writer returned (a glossary term always takes the glossary's own wording, so
the writer can never reword a definition into a claim), merging footnotes, and building the caption's paragraph. The page has the
same rules in web/src/lib/glossary.js (a test holds the two equal on the same cases).

A footnote is MEANING ONLY. The glossary file is Wan's to review: nothing here adds a term or a wording of its own.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

GLOSSARY_PATH = Path(__file__).resolve().parents[2] / "rules" / "glossary.json"
GLOSSARY: dict[str, Any] = json.loads(GLOSSARY_PATH.read_text(encoding="utf-8"))
ENTRIES: list[dict[str, Any]] = list(GLOSSARY["terms"])

LABEL = {"bm": "Definisi", "en": "Definition"}
FOOT_TERMS = 2          # terms on one slide's footnote
CAPTION_TERMS = 5       # terms in one caption's Definisi paragraph
MEANING_WORDS = 14      # the most words a footnote's meaning takes (the glossary's own are within it)
CUSTOM_WORDS = 16       # a term the writer defined itself may run slightly longer; past this the pair is dropped
FOOT_CAP = 300          # compliance.SLIDE_WORDS["foot"]

# "Definisi:" or "Definition:" opens a footnote and the caption's paragraph
DEF_HEAD = re.compile(r"^\s*(?:definisi|definition)s?\s*:\s*", re.I)
_WORDISH = r"[\w]"


def _form_re(form: str) -> re.Pattern[str]:
    """A form as a whole word (never inside another word). A form with two or more capital letters (NPRA, MoS, PIF) keeps its
    capitals; any other form matches in any case. Mirrored by formRe in web/src/lib/glossary.js."""
    pat = r"\s+".join(re.escape(p) for p in form.split())
    flags = 0 if sum(c.isupper() for c in form) >= 2 else re.I
    return re.compile(rf"(?<!{_WORDISH}){pat}(?!{_WORDISH})", flags)


_COMPILED: list[tuple[dict[str, Any], list[tuple[str, re.Pattern[str]]]]] = [
    (e, [(f, _form_re(f)) for f in e["term"]]) for e in ENTRIES]
_BY_ID = {e["id"]: e for e in ENTRIES}


def entry(ident: str) -> dict[str, Any] | None:
    return _BY_ID.get(ident)


def meaning(e: dict[str, Any], lang: str) -> str:
    return str(e["en" if lang == "en" else "bm"]).strip()


def label(e: dict[str, Any], lang: str) -> str:
    return str((e.get("label") or {}).get("en" if lang == "en" else "bm") or e["term"][0])


def used(text: str, scan_only: bool = True) -> list[tuple[dict[str, Any], str]]:
    """[(entry, the form as written)] for every glossary term `text` uses, in the order each first appears. `scan_only` skips
    the words so common that the check never asks for their footnote (`"scan": false`)."""
    text = str(text or "")
    found: list[tuple[int, dict[str, Any], str]] = []
    for e, forms in _COMPILED:
        if scan_only and e.get("scan") is False:
            continue
        hits = [(m.start(), m.group(0)) for _, rx in forms for m in [rx.search(text)] if m]
        if hits:
            at, written = min(hits, key=lambda h: (h[0], -len(h[1])))      # the longer form wins at the same place (QUEST3+)
            found.append((at, e, written))
    return [(e, w) for _, e, w in sorted(found, key=lambda x: x[0])]


def lookup(term: str) -> dict[str, Any] | None:
    """The glossary entry a footnote's term names (the term as one of its forms or its label), else None."""
    low = " ".join(str(term or "").split()).lower()
    if not low:
        return None
    for e, forms in _COMPILED:
        names = {f.lower() for f, _ in forms} | {str(v).lower() for v in (e.get("label") or {}).values()}
        if low in names:
            return e
    for e, forms in _COMPILED:                      # "Notifikasi kosmetik (NPRA)": a form inside the term
        if any(rx.search(term) for _, rx in forms):
            return e
    return None


# --- reading a footnote or a caption's paragraph back ----------------------------------------------------------------------

def pairs_of(text: str) -> list[tuple[str, str]]:
    """[(term, meaning)] of a footnote or a Definisi paragraph: the leading "Definisi:" is dropped, pairs split on ";" and a
    pair on its first "=" (or ":" when there is no "="). A piece with no meaning is ignored."""
    body = DEF_HEAD.sub("", str(text or "").strip())
    out: list[tuple[str, str]] = []
    for piece in re.split(r"[;\n]+", body):
        piece = piece.strip().rstrip(".")
        sep = "=" if "=" in piece else (":" if ":" in piece else "")
        if not sep:
            continue
        term, _, mean = piece.partition(sep)
        term, mean = " ".join(term.split()), " ".join(mean.split())
        if term and mean:
            out.append((term, mean))
    return out


def defined_in(text: str) -> set[str]:
    """Ids of the glossary entries a footnote or a Definisi paragraph defines (a pair's TERM names the entry)."""
    ids: set[str] = set()
    for term, _ in pairs_of(text):
        e = lookup(term)
        if e:
            ids.add(e["id"])
    return ids


def definisi_paragraphs(caption: str) -> list[str]:
    """The paragraphs of a caption that are Definisi paragraphs."""
    return [p.strip() for p in re.split(r"\n\s*\n", str(caption or "").strip()) if DEF_HEAD.match(p)]


def defined_in_caption(caption: str) -> set[str]:
    ids: set[str] = set()
    for p in definisi_paragraphs(caption):
        ids |= defined_in(p)
    return ids


def strip_definisi(caption: str) -> str:
    """The caption without its Definisi paragraphs: what the check reads for the terms the caption USES."""
    paras = [p for p in re.split(r"\n\s*\n", str(caption or "")) if not DEF_HEAD.match(p)]
    return "\n\n".join(paras)


# --- cleaning and building -------------------------------------------------------------------------------------------------

def _pair_text(term: str, mean: str) -> str:
    return f"{term} = {mean.rstrip('.')}"


def clean_pairs(raw_pairs: list[tuple[str, str]], lang: str) -> list[tuple[str, str]]:
    """A glossary term takes the glossary's own label and meaning, verbatim. Any other term is the writer's own plain
    explanation: kept only when short (CUSTOM_WORDS) and when it is not a way of sending the reader away. Duplicates go."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for term, mean in raw_pairs:
        e = lookup(term)
        if e:
            key = e["id"]
            term, mean = label(e, lang), meaning(e, lang)
        else:
            key = term.lower()
            if len(mean.split()) > CUSTOM_WORDS or re.search(r"https?://|www\.", mean, re.I):
                continue
        if key in seen:
            continue
        seen.add(key)
        out.append((term, mean))
    return out


def clean_foot(raw: Any, lang: str, limit: int = FOOT_TERMS) -> str:
    """The `foot` of one slide or poster as stored: "Definisi: term = meaning; term2 = meaning." (BM) or "Definition: ..." (EN),
    at most `limit` terms, within FOOT_CAP. A term that would not fit is dropped whole, never cut mid-word. "" when nothing
    usable is left."""
    if isinstance(raw, list):                       # [{"term","meaning"}] is accepted too
        pairs = [(str(x.get("term") or ""), str(x.get("meaning") or "")) for x in raw if isinstance(x, dict)]
    else:
        pairs = pairs_of(str(raw or ""))
    kept = clean_pairs(pairs, lang)[:limit]
    while kept:
        text = f"{LABEL['en' if lang == 'en' else 'bm']}: " + "; ".join(_pair_text(t, m) for t, m in kept) + "."
        if len(text) <= FOOT_CAP:
            return text
        kept.pop()
    return ""


def merge_feet(feet: list[str], lang: str, limit: int = FOOT_TERMS) -> str:
    """Several footnotes as one (two slides joined into one): the first terms win, duplicates go, `limit` terms at most."""
    pairs = [p for f in feet for p in pairs_of(f)]
    return clean_foot(pairs and [{"term": t, "meaning": m} for t, m in pairs], lang, limit)


def foot_for(text: str, lang: str, limit: int = FOOT_TERMS) -> str:
    """A footnote built from the glossary for the terms `text` uses (what the writer did not define itself)."""
    ents = [e for e, _ in used(text)][:limit]
    return clean_foot([{"term": label(e, lang), "meaning": meaning(e, lang)} for e in ents], lang, limit)


def build_paragraph(pairs: list[tuple[str, str]], lang: str) -> str:
    """"Definisi: term = meaning; term2 = meaning." (BM) / "Definition: ..." (EN), at most CAPTION_TERMS terms. "" for none."""
    kept = clean_pairs(pairs, lang)[:CAPTION_TERMS]
    return f"{LABEL['en' if lang == 'en' else 'bm']}: " + "; ".join(_pair_text(t, m) for t, m in kept) + "." if kept else ""


# the tail of a caption: the follow line and the hashtags, which the Definisi paragraph goes in front of
_FOLLOW = re.compile(r"\b(follow|ikuti|ikut kami|ikut saya)\b", re.I)
_TAGS_ONLY = re.compile(r"^(?:\s*#[^\s#]+)+\s*$")


def place_in_caption(caption: str, paragraph: str) -> str:
    """The caption with `paragraph` as its last body paragraph: after the facts, BEFORE the follow line and the hashtags. A
    caption that already has a Definisi paragraph has it replaced, not doubled. Nothing else of the caption is touched."""
    if not paragraph:
        return caption
    paras = [p.strip() for p in re.split(r"\n\s*\n", str(caption or "").strip()) if p.strip() and not DEF_HEAD.match(p)]
    cut = len(paras)
    while cut > 1 and (_TAGS_ONLY.match(paras[cut - 1]) or (_FOLLOW.search(paras[cut - 1]) and len(paras[cut - 1]) <= 200)):
        cut -= 1
    return "\n\n".join([*paras[:cut], paragraph, *paras[cut:]])


def prompt_block(lang: str) -> str:
    """The glossary as a block for a writer's prompt: every entry with the exact wording it must use."""
    rows = []
    for e in ENTRIES:
        rows.append(f'- {label(e, lang)} ({" / ".join(e["term"][:3])}) = {meaning(e, lang)}')
    return "\n".join(rows)
