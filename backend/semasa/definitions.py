"""What the subject IS, in every flow (Wan, 10 Nov 2026: "make sure semua flow ada definition", after "aku tak tahu HIFU
tu apa").

Every writer (the film planner, the photo-story and showcase storyboards, and the post writer for a caption, a carousel, a
poster and LinkedIn) is asked for the same small list, `terms`: up to three words or acronyms a shopkeeper would not know
(a procedure, device, ingredient, test, rule or body), each with one plain sentence saying what it IS. The list is kept where
the person approving reads it (the storyboard review, the idea card), so someone new to the subject can judge the work, and
the writer is told to say the meaning in the work itself before the fact that uses it. A definition is meaning only: no
figure, no claim that it works or is safe, no brand, no price, and never a way of sending the reader away to look it up.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from . import motion_captions, motion_layout

MAX_TERMS = 3
SHAPE = '"terms": [{"term": "<a word or acronym the reader may not know>", "meaning": "<what it is, in one plain sentence>"}]'
LIST = ("WHAT IT IS: the reader, and the person approving this, may not know the main subject. List up to 3 words or acronyms a "
        "shopkeeper would not know (a procedure, device, ingredient, test, rule or body, e.g. HIFU, PIF, MS 1500) in `terms`, "
        "each with `meaning`: what it IS, in one plain sentence, from the source when it defines it. Meaning only: no figure, no "
        "claim that it works or is safe, no brand, no price. When every word is everyday, give `terms: []`.")
SAY_IT = " In the work itself, say that meaning in plain words BEFORE the fact that uses it."
RULE = LIST + SAY_IT                  # a caption, a carousel, a poster, a narrated film
RULE_LIST_ONLY = LIST                 # a film with no narrator: the list is for the person approving


def clean(raw: Any, speak: Callable[[str], str] = str) -> list[dict[str, str]]:
    """The writer's `terms` made safe: at most three, each a short term and one sentence, nothing that sends the reader away.
    Anything else is dropped, so a malformed answer costs the list and never the work."""
    out: list[dict[str, str]] = []
    for t in raw if isinstance(raw, list) else []:
        if len(out) >= MAX_TERMS:
            break                              # the cap counts what is KEPT: junk ahead of a good term costs it nothing
        if not isinstance(t, dict):
            continue
        term = " ".join(str(t.get("term") or "").split())[:60]
        meaning = speak(motion_layout.plain(t.get("meaning")))[:240].strip()
        if term and meaning and not motion_captions.hand_off(meaning):
            out.append({"term": term, "meaning": meaning})
    return out
