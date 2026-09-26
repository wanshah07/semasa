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


# --- a design from a reference (Wan, 26 Sep 2026: "let us upload reference and AI will review > render and get
# confirmation to save the design") --------------------------------------------------------------------------------
# The reference is read by the vision model as an art director would: what it does well, what must change for the
# post rules, which of the looks it is nearest, and an ORIGINAL background in its mood (never a copy of its artwork,
# its brand or its people). The preview is drawn, then waits for Wan: Simpan attaches and keeps it, Ubah re-draws it
# with his note, Buang deletes it. A preview nobody confirms is cleared after UNCONFIRMED_DAYS.

LOOK_CHOICES = ("grid", "era", "photo", "classic")
UNCONFIRMED_DAYS = 7

REVIEW_SYSTEM = ("You are an art director reviewing a reference picture for a new social media design. "
                 "Answer with one JSON object only.")
REVIEW_PROMPT = """Review this reference for a new {kind} for {who}. The new design takes ideas from it but never copies
its artwork, its brand, its products or its people. JSON keys:
"summary": two sentences in Malaysian Malay (never Bahasa Indonesia): what the reference does well and what the new
  design will do;
"keep": up to 4 short points in Malaysian Malay: what to take from it (layout, hierarchy, colour mood, spacing, type);
"change": up to 4 short points in Malaysian Malay: what must change. Always flag, if present: a call to action, a
  website or handle, another brand's logo or name, a real person's face, more text than one headline and a few points;
"look": the nearest of "grid" (clean editorial grid, flat colour blocks), "era" (bold magazine style, strong accent
  colour, a character), "photo" (a full-bleed photograph with the words over it), "classic" (quiet brand paper);
"background": one English sentence describing an ORIGINAL background picture in the reference's mood and colours,
  with calm empty space for text: no words, no letters, no logos, no products, no recognisable people;
"words_note": one English sentence on the words' tone and length (e.g. "one short punchy headline, three short points");
"text_in_image": the words printed in the reference, verbatim, or "";
"brands": logos or brand names visible, or [].{note}"""


def review(llm: LLM | None, data: bytes, mime: str, kind: str, stream: str, note: str = "") -> dict[str, Any] | None:
    """The art director's reading of a reference, or None when no model that can see answered (the page then says the
    reference was not read, and the design is drawn from Wan's own choices)."""
    if llm is None or not getattr(llm, "configured", False):
        return None
    from .media_generator import shrink_for_read
    small, small_ct = shrink_for_read(data, mime)
    who = ("ws.regulab, a Malaysian regulatory brand speaking Malay to SME owners" if stream != "linkedin"
           else "a named chemist's LinkedIn, in English, with no company identity")
    prompt = REVIEW_PROMPT.format(kind=kind or "poster", who=who,
                                  note=f"\nWan's note on the last version: {note}" if note.strip() else "")
    out = llm.describe_image(REVIEW_SYSTEM, prompt, small, small_ct, max_tokens=900)
    if not out or not str(out.get("summary") or "").strip():
        return None
    look = str(out.get("look") or "").strip().lower()

    def points(key: str) -> list[str]:
        vals = out.get(key) if isinstance(out.get(key), list) else []
        return [str(v).strip()[:160] for v in vals if str(v).strip()][:4]
    return {"summary": str(out["summary"]).strip()[:500], "keep": points("keep"), "change": points("change"),
            "look": look if look in LOOK_CHOICES else "grid",
            "background": str(out.get("background") or "").strip()[:500],
            "words_note": str(out.get("words_note") or "").strip()[:200],
            "text_in_image": str(out.get("text_in_image") or "").strip()[:300],
            "brands": [str(b)[:60] for b in (out.get("brands") or []) if str(b).strip()][:6],
            "model": getattr(llm, "last_model", "") or None}


def background_prompt(review_out: dict[str, Any] | None, note: str = "") -> str:
    base = (review_out or {}).get("background") or ""
    if not base:
        return ""
    return (f"{base} {note.strip()}. " if note.strip() else f"{base} ") + (
        "A calm, uncluttered background for text: no words, no letters, no logos, no products, no people's faces.")


def purge_unconfirmed(store: Any, now: Any = None) -> int:
    """Previews Wan never confirmed are cleared after UNCONFIRMED_DAYS: the row and its files (compact storage)."""
    from datetime import UTC, datetime, timedelta

    from . import db
    now = now or datetime.now(UTC)
    cutoff = (now - timedelta(days=UNCONFIRMED_DAYS)).isoformat()
    try:
        rows = store.table(db.MEDIA).select("id,meta,reference_path").eq("mode", "slides") \
            .eq("meta->>awaiting_confirm", "true").lt("created_at", cutoff).limit(100).execute().data or []
    except Exception as exc:  # noqa: BLE001 - housekeeping never fails the run
        log.info("could not look for unconfirmed designs: %s", str(exc)[:120])
        return 0
    gone = 0
    for r in rows:
        m = r.get("meta") or {}
        files = [p for p in (m.get("slide_paths") or []) + [m.get("ground_path")] if p]
        try:
            if files:
                store.storage.from_(db.GENERATED_BUCKET).remove(files)
            refs = [p for p in [(m.get("style_ref") or {}).get("path"), r.get("reference_path")] if p]
            if refs:
                store.storage.from_("semasa-reference").remove(refs)
            store.table(db.MEDIA).delete().eq("id", r["id"]).execute()
            gone += 1
        except Exception as exc:  # noqa: BLE001
            log.info("could not clear design %s: %s", r.get("id"), str(exc)[:120])
    return gone
