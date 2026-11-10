"""Grammar and spelling, checked before anything is shown or recorded (Wan, 10 Nov 2026: "make sure grammar always betul",
and "buatkan benda yang sama untuk linkedin").

Two steps, the same for ws.regulab (Bahasa Malaysia) and LinkedIn (English):

  1. `fix_spelling`: deterministic. SMS abbreviations are written out ("yg" -> "yang", Malay only), runs of spaces and doubled
     punctuation are tidied, and a sentence starts with a capital.
  2. `proofread`: ONE writer call over every field of the work, asked to correct spelling, grammar, agreement, punctuation and
     capitalisation and nothing else. Its answer is accepted field by field, and only when `safe`: the numbers, the acronyms and
     capitalised names, the hashtags and the links are exactly the same, and the length moved by no more than a fifth. A field
     that fails keeps its original words, so a proofreader can never change a fact, only the way it is written.

Wan's casual spoken register stays (korang, jom, tak, dah, bagitau, takde, "benda pasal..." from his own hook shapes): the
proofreader is told that casual is allowed and wrong is not. It fails open: no writer, a refusal or a bad answer leaves the
text as it was.
"""

from __future__ import annotations

import json
import re
from typing import Any

from . import pronounce
from .log import get_logger

log = get_logger("semasa.proofread")

SYSTEM = (
    "You are the proofreader of a social-media team. You are given short pieces of text in {tongue}. Correct ONLY: spelling, "
    "grammar, word agreement, punctuation, capitalisation, and a sentence that is broken or cut off. {register} "
    "HARD RULES: never change a number, a date, a name, an acronym, a citation, a hashtag or a link; never add or remove a fact, "
    "a claim or a sentence; never reword for style; keep the line breaks; keep each piece at about its length. A piece that is "
    "already correct comes back exactly as it is. Answer ONE JSON object and nothing else: "
    '{{"fixed": {{"<the key exactly as given>": "<the corrected text>"}}}}, with every key you were given.')
REGISTER = {
    "bm": ("The register is casual spoken Bahasa Malaysia as written and spoken in MALAYSIA, never Indonesian: words such as "
           "'korang', 'jom', 'tak', 'dah', 'bagitau', 'takde', 'benda pasal', 'senang cerita' are intended and must stay; wrong "
           "spelling ('mmg', 'x', 'yg'), a missing word or a wrong preposition is what you fix."),
    "en": "The register is a professional speaking plainly to a peer: keep it natural, correct it, do not formalise it.",
}
_NUM = re.compile(r"\d+(?:[.,]\d+)*")
_NAME = re.compile(r"\b(?:[A-Z]{2,}[A-Za-z0-9-]*|[A-Z][a-z]+\d+)\b")
_TAG = re.compile(r"[#@]\w+|https?://\S+|www\.\S+")


def fix_spelling(text: str, lang: str) -> str:
    """The deterministic step: abbreviations in full (Malay), tidy spaces, tidy repeated punctuation, a capital to start."""
    out = pronounce.expand_abbreviations(str(text or ""), lang)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"([!?.,;:])\1{1,}", lambda m: "..." if m.group(1) == "." and len(m.group(0)) == 3 else m.group(1), out)
    out = re.sub(r"\s+([,.;:!?])", r"\1", out)
    out = out.strip()
    return out[:1].upper() + out[1:] if out[:1].islower() and not out.startswith(("http", "www", "#", "@")) else out


def _tokens(text: str) -> tuple[list[str], set[str], set[str]]:
    return sorted(_NUM.findall(text)), set(_NAME.findall(text)), set(_TAG.findall(text))


def safe(old: str, new: str) -> bool:
    """A correction is accepted only when it changed the way the text is written and nothing it says."""
    if not isinstance(new, str) or not new.strip():
        return False
    a, b = _tokens(old), _tokens(new)
    if a[0] != b[0] or a[1] - b[1] or b[1] - a[1] or a[2] != b[2]:
        return False
    ratio = len(new) / max(1, len(old))
    return 0.8 <= ratio <= 1.2


def proofread(llm: Any, fields: dict[str, str], lang: str) -> tuple[dict[str, str], list[str]]:
    """({key: corrected text} for every field, [keys that were changed]). The input is never mutated; any failure returns the
    deterministic fixes only."""
    base = {k: fix_spelling(v, lang) for k, v in fields.items() if str(v or "").strip()}
    changed = [k for k, v in base.items() if v != fields[k]]
    if llm is None or not base:
        return base, changed
    key = "en" if lang == "en" else "bm"
    system = SYSTEM.format(tongue="English" if key == "en" else "Bahasa Malaysia", register=REGISTER[key])
    try:
        out = llm.chat_json(system, json.dumps(base, ensure_ascii=False), max_tokens=3000)
    except Exception as exc:  # noqa: BLE001 - a proofreader that fails leaves the text as it was
        log.info("proofread skipped (%s)", str(exc)[:120])
        return base, changed
    fixed = (out or {}).get("fixed") if isinstance(out, dict) else None
    if not isinstance(fixed, dict):
        return base, changed
    result = dict(base)
    for k, old in base.items():
        new = fixed.get(k)
        if isinstance(new, str) and new.strip() != old and safe(old, new):
            result[k] = new.strip()
            if k not in changed:
                changed.append(k)
    return result, changed


def post(llm: Any, out: dict[str, Any], text: dict[str, Any], lang: str) -> tuple[str, dict[str, Any], Any, list[str]]:
    """The words of a written post, proofread: (hook, text, slides, [what was corrected]). Each language variant of the caption is
    corrected in its own language, the hook and every slide word in the post's language. A hook that led its caption still leads
    it afterwards, or both keep their original words."""
    hook = str(out.get("hook") or "")
    slides = out.get("slides")
    fields: dict[str, str] = {"hook": hook}
    for i, sc in enumerate(slides if isinstance(slides, list) else []):
        if isinstance(sc, dict):
            fields[f"s{i}.title"], fields[f"s{i}.lead"] = str(sc.get("title") or ""), str(sc.get("lead") or "")
            for j, pt in enumerate(sc.get("points") if isinstance(sc.get("points"), list) else []):
                fields[f"s{i}.p{j}"] = str(pt)
    own_text = {p: v for p, v in ((text.get(lang) or {}).items()) if isinstance(v, str)}
    for p, v in own_text.items():
        fields[f"cap.{p}"] = v
    fixed, changed = proofread(llm, fields, lang)
    new_text = {k: (dict(v) if isinstance(v, dict) else v) for k, v in text.items()}
    for p in own_text:
        old_cap, new_cap = own_text[p], fixed.get(f"cap.{p}", own_text[p])
        if hook_leads(hook, old_cap) and not hook_leads(fixed.get("hook", hook), new_cap):
            fixed[f"cap.{p}"], fixed["hook"] = old_cap, hook             # never break "the hook is the first line"
        new_text.setdefault(lang, {})[p] = fixed.get(f"cap.{p}", old_cap)
    other = "en" if lang == "bm" else "bm"
    if isinstance(text.get(other), dict):                                    # the other variant, in its own language
        o_fields = {p: v for p, v in text[other].items() if isinstance(v, str)}
        o_fixed, o_changed = proofread(llm, o_fields, other)
        new_text[other] = {**text[other], **o_fixed}
        changed += [f"{other}.{k}" for k in o_changed]
    new_slides = slides
    if isinstance(slides, list):
        new_slides = []
        for i, sc in enumerate(slides):
            if not isinstance(sc, dict):
                new_slides.append(sc)
                continue
            pts = [fixed.get(f"s{i}.p{j}", str(pt)) for j, pt in enumerate(sc.get("points") or [])] if isinstance(
                sc.get("points"), list) else sc.get("points")
            new_slides.append({**sc, **({"title": fixed.get(f"s{i}.title", sc.get("title"))} if "title" in sc else {}),
                               **({"lead": fixed.get(f"s{i}.lead", sc.get("lead"))} if "lead" in sc else {}),
                               **({"points": pts} if pts is not None else {})})
    return fixed.get("hook", hook), new_text, new_slides, changed


def hook_leads(hook: str, caption: str) -> bool:
    """Does the caption open with the hook (the first words, ignoring case and punctuation)?"""
    norm = lambda s: re.sub(r"[^\w\s]", " ", str(s).lower()).split()  # noqa: E731
    h, c = norm(hook), norm(caption)
    return bool(h) and c[:len(h)] == h
