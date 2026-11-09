"""Is a short piece of text Malay? Used to keep the LinkedIn stream English (Wan, 9 Nov 2026).

The LinkedIn caption was already checked (compliance.NOT_ENGLISH needs five Malay function words, which suits a caption and can
never fire on a cover headline of nine words). The hook shapes are written in casual Malay and the writer sometimes copied them
onto an English post's hook, its cover and its last slide ("Benda pasal siasatan aduan makanan yg takde sapa bagitau kau" on a
card whose other slides were English). So this check is built for SHORT text: a casual-Malay marker is enough on its own, and
two ordinary Malay function words are enough otherwise. It never needs a language model.
"""

from __future__ import annotations

import re
from typing import Any

# Words that are not English and do not occur in an English sentence by accident. One of them is enough.
STRONG = frozenset("""yg takde sapa bagitau kau aku korang benda pasal ckp tapi dgn sbb
tahukah berfaedah ilmu maksudnya senang sekali boleh kerana adalah tidak untuk dengan anda kami selepas sebelum""".split())
# Ordinary Malay function words: two of them make a Malay line.
WEAK = frozenset("""yang pada ini itu dan atau dari dalam kepada juga sudah masih lagi bukan akan telah hanya
setiap semua""".split())

_WORD = re.compile(r"[a-z]+")


def is_malay(text: Any) -> bool:
    words = _WORD.findall(str(text or "").lower().replace("*", ""))
    if any(w in STRONG for w in words):
        return True
    return len({w for w in words if w in WEAK}) >= 2


def slide_text(slide: Any) -> list[str]:
    """Every string a slide (or a poster) puts on the artwork: title, lead, points."""
    if not isinstance(slide, dict):
        return []
    out = [str(slide.get("title") or ""), str(slide.get("lead") or "")]
    pts = slide.get("points")
    out += [str(p) for p in pts] if isinstance(pts, list) else []
    return [t for t in out if t.strip()]


def malay_fields(out: Any) -> list[str]:
    """The fields of a writer's answer that should be English and are not: the hook, every slide, the poster. The caption is the
    compliance scan's job. Empty when the answer is clean."""
    if not isinstance(out, dict):
        return []
    bad = []
    if is_malay(out.get("hook")):
        bad.append("hook")
    slides = out.get("slides") if isinstance(out.get("slides"), list) else []
    for i, s in enumerate(slides, 1):
        if any(is_malay(t) for t in slide_text(s)):
            bad.append(f"slide {i}")
    if isinstance(out.get("poster"), dict) and any(is_malay(t) for t in slide_text(out["poster"])):
        bad.append("poster")
    return bad


def english_ask(fields: list[str]) -> str:
    """The second ask when a LinkedIn answer carried Malay somewhere an English post cannot."""
    return ("\n\nYOUR LAST ANSWER HAD MALAY WORDS IN FIELDS THAT MUST BE ENGLISH (" + ", ".join(fields[:8]) + "). The LinkedIn "
            "stream is English only: the hook, every slide title, lead and point, the cover and the last slide. The hook shapes "
            "are written in casual Malay, so TRANSLATE the shape into natural English, keeping its structure and what each blank "
            "is for, and never print the Malay words. Answer again in the same JSON, every field English, the hook equal to the "
            "caption's first line.")


def first_line(text: Any) -> str:
    for line in str(text or "").splitlines():
        if line.strip():
            return line.strip()
    return ""
