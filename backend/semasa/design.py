"""The Design tab's words (Wan, 25 Sep 2026: "add design section - to create poster, single card and carousel for
post" / "the slide can create based on upload and prompt/idea provided").

A design job is a `slides` render job (media_generations, mode `slides`) whose meta carries `design`:
  poster    one picture, 4:5 portrait by default: a headline and up to five points, the source at the foot
  card      one picture, square by default: a headline and up to three points
  carousel  5 to 7 slides, the stream's own shape by default

The words come from Wan (meta.slides) or, when he gives only an idea or a prompt (meta.brief), from the writer here,
under the same rules as a post: no call to action, no URL, no social source, and [SAHKAN: <the missing fact>] for any
fact the brief does not give. The drawing is semasa.slides, with no AI and no cost.
"""

from __future__ import annotations

from typing import Any

from . import compliance, slides
from .llm import LLM
from .log import get_logger

log = get_logger("semasa.design")

DESIGNS = ("poster", "card", "carousel")
DEFAULT_FORMAT = {"poster": "portrait", "card": "square"}        # a carousel follows its stream

COMMON = """Rules. Breaking any of them blocks the artwork:
1. No call to action of any kind ("hubungi kami", "DM", "klik link", "follow", "semak kelayakan", "comment below").
2. No website or URL anywhere in the words: the artwork footer carries the website.
3. Never name Reddit, YouTube, TikTok, a forum or a news portal as a source.
4. No fee, duration, date, circular, entry number or figure unless it is in the BRIEF. Where one is needed and the
   brief does not give it, write [SAHKAN: <the exact missing fact>]. Never an empty [SAHKAN].
5. No em dash. No superlatives, no promise of approval.
6. Mark the one key word of a title with *asterisks*, at most once per title.
7. "citation" names the regulator and instrument the words rest on, or "" when the brief names none. It is drawn at
   the foot, so do not write it into the words."""

VOICE = {
    "regulab": "Write in Malaysian Malay (never Bahasa Indonesia: boleh, ubat, syarikat, kualiti, pembungkusan) mixed "
               "naturally with English technical terms, for Malaysian SME owners, as the brand ws.regulab.",
    "linkedin": "Write in English for regulatory and formulation peers, as a named chemist. No company identity at "
                "all: never ws.regulab, KKM Halal Consultant or any website.",
}

SHAPE = {
    "poster": 'ONE poster: {"slides": [{"title": "a headline of at most 10 words", "points": [up to 5 points of at '
              'most 22 words each]}], "citation": "..."}',
    "card": 'ONE card: {"slides": [{"title": "a headline of at most 9 words", "points": [up to 3 points of at most '
            '18 words each]}], "citation": "..."}',
    "carousel": 'A carousel of 5 to 7 slides: {"slides": [{"title": "...", "points": ["..."]}, ...], "citation": "..."}. '
                'Slide 1 is the cover (a headline of at most 9 words, points empty or one short line). Each middle '
                'slide carries ONE fact: a title of at most 8 words and at most 3 points of at most 20 words. The last '
                'slide is the takeaway, never a call to action.',
}


def write(llm: LLM, brief: str, design: str, stream: str) -> tuple[list[dict[str, Any]], str]:
    """(slides, citation) written from Wan's idea or prompt. Raises slides.SlideError with a message for the page."""
    if design not in DESIGNS:
        raise slides.SlideError(f"unknown design {design!r}")
    if not llm or not llm.configured:
        raise slides.SlideError("the writer is off, so the words cannot be written from the idea: "
                                + (llm.why_off() if llm else "no writer") + ". Write the words yourself instead.")
    system = (f"You write the words for a social-media artwork. {VOICE.get(stream, VOICE['regulab'])}\n\n{COMMON}\n\n"
              f"Answer with ONE JSON object only. {SHAPE[design]}")
    out = llm.chat_json(system, f"BRIEF (Wan's idea or prompt):\n{brief.strip()[:4000]}", max_tokens=2500)
    if not isinstance(out, dict):
        raise slides.SlideError("the writer did not answer (see the run log); press Retry, or write the words yourself")
    items = compliance.normalise_slides(out.get("slides"))
    if design in ("poster", "card"):
        items = items[:1]
    if not items:
        raise slides.SlideError("the writer returned no words for the artwork; press Retry, or write them yourself")
    return items, str(out.get("citation") or "").strip()[:600]


def check(items: list[dict[str, Any]], design: str) -> None:
    """A poster or a card is ONE picture: more than one slide of words is a mistake to name, not to cut."""
    if design in ("poster", "card") and len(items) > 1:
        raise slides.SlideError(f"a {design} is one picture, and {len(items)} slides of words were given: "
                                "keep one, or make it a carousel")


def size_of(meta: dict[str, Any], stream: str) -> tuple[int, int] | None:
    """The picture's shape: meta.format when set, else the design's default, else the stream's carousel shape."""
    fmt = meta.get("format") or DEFAULT_FORMAT.get(str(meta.get("design") or ""))
    return slides.FORMATS.get(str(fmt)) if fmt else None
