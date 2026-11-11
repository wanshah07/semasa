"""A post's carousel, finished (Wan, 11 Nov 2026).

  * the LAST picture of a ws.regulab carousel is the logo card: the official ws.regulab logo and "Follow us for more". It is
    drawn here, not written as a slide, so it is never in the post's words, never scanned as a call to action and never
    edited by mistake. LinkedIn carries none of it (rule 7: that stream is Wan's own byline, no ws.regulab identity at all);
  * a carousel of more than six pictures is squeezed: neighbouring slides are joined, the sparsest pair first, so the set
    does not read as page after page of one line. The cover and the closing slide stay on their own. A join is made only
    when the joined slide still fits comfortably at the normal type size; when none does, the set stays as written. The
    words kept on the job and on the post are never changed: only what is drawn is squeezed.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from . import compliance, slides
from .slides import SlideError

MAX_SLIDES = 6                      # pictures in one carousel, the logo card included
COMFORT = 0.8                       # a joined slide must fit at this share of the normal type size, or it is not joined
ROOT = Path(__file__).resolve().parents[2]
LOGO = ROOT / "rules" / "motion" / "official-logo-transparent.png"      # the same file the Motion films' logo card uses

FOLLOW_EN = "Follow us for more"
FOLLOW_BM = "Ikuti kami untuk info seterusnya"


def has_logo_card(stream: str, count: int) -> bool:
    """A ws.regulab carousel (two pictures or more) ends on the logo card; a lone card, a poster and LinkedIn do not."""
    return stream != "linkedin" and count >= 2


def text_target(stream: str) -> int:
    """How many written slides a carousel keeps: the cap less the logo card, which takes a place of its own."""
    return MAX_SLIDES - (1 if stream != "linkedin" else 0)


def _clean(text: Any) -> str:
    return " ".join(str(text or "").split())


def _sentence(title: str, lead: str) -> str:
    title, lead = _clean(title), _clean(lead)
    if not lead:
        return title
    if not title:
        return lead
    return f"{title}{' ' if title[-1] in '.!?:;' else '. '}{lead}"


def join(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any] | None:
    """Two neighbouring slides as one: a's headline, then a's own words and b's whole slide as points. Every word is kept;
    None when the points would not all fit the slide shape (a join never drops one)."""
    points = [_clean(a.get("lead")), *(a.get("points") or []), _sentence(b.get("title", ""), b.get("lead", "")),
              *(b.get("points") or []), _clean(b.get("note"))]
    points = [p for p in (_clean(p) for p in points) if p]
    if len(points) > compliance.MAX_POINTS:
        return None
    keep = {k: v for k, v in a.items() if k not in ("title", "points", "lead", "note")}
    return {"title": a.get("title", ""), "points": points, **keep}


def _text_size(slide: dict[str, Any]) -> int:
    return len(_clean(slide.get("title"))) + sum(len(_clean(p)) for p in (slide.get("points") or [])) + len(
        _clean(slide.get("lead"))) + len(_clean(slide.get("note")))


def comfortable(slide: dict[str, Any], stream: str, size: tuple[int, int] | None = None) -> bool:
    """Does this slide fit a middle card at COMFORT of the normal type size? (Semasa's own drawing is the measure: the
    other designs have their own room, so this is a cautious proxy, and a render that still fails is drawn unjoined.)"""
    w, h = size or slides.SIZES.get(stream, slides.SIZES["regulab"])
    col, room = w - 2 * slides.MARGIN, h - 2 * slides.MARGIN - slides.HEAD_H - slides.FOOT_H
    words = {"title": slide.get("title") or "", "points": list(slide.get("points") or [])}
    scale = 1.0
    while scale >= COMFORT - 1e-9:
        if slides.layout(words, "point", col, scale, h > w).height <= room:
            return True
        scale = round(scale - slides.SCALE_STEP, 2)
    return False


def compact(items: list[dict[str, Any]], stream: str, target: int | None = None) -> tuple[list[dict[str, Any]], int]:
    """(the slides to draw, how many joins were made). Only when the set is longer than the target; never touches the
    cover or the closing slide; joins the pair with the least words first, and stops when the next join would not fit."""
    target = target or text_target(stream)
    out = [dict(s) for s in items]
    joined = 0
    while len(out) > target and len(out) >= 4:
        best = None
        for i in range(1, len(out) - 2):                  # a pair inside: never slide 0 (cover) or the last (closing)
            merged = join(out[i], out[i + 1])
            if merged is None or not comfortable(merged, stream):
                continue
            weight = _text_size(out[i]) + _text_size(out[i + 1])
            if best is None or weight < best[0]:
                best = (weight, i, merged)
        if best is None:
            break
        _, i, merged = best
        out[i:i + 2] = [merged]
        joined += 1
    return out, joined


# --- the logo card ---------------------------------------------------------------------

def _logo(width: int, white: bool) -> Image.Image:
    im = Image.open(LOGO).convert("RGBA")
    box = im.getchannel("A").getbbox()
    if box:
        im = im.crop(box)
    h = round(width * im.height / im.width)
    im = im.resize((width, h), Image.LANCZOS)
    if white:
        flat = Image.new("RGBA", im.size, (255, 255, 255, 0))
        flat.putalpha(im.getchannel("A"))
        flat.paste((255, 255, 255, 255), mask=im.getchannel("A"))
        return flat
    return im


def _centred(d: ImageDraw.ImageDraw, text: str, font: Any, cx: int, y: int, fill: Any) -> None:
    d.text((cx - font.getlength(text) / 2, y), text, font=font, fill=fill)


def closing_card(index: int, total: int, *, ground: bytes | None = None, size: tuple[int, int] | None = None) -> Image.Image:
    """The last picture: the logo, a short rule, "Follow us for more" and its Malay line, centred, with the page count the
    other slides carry. On a photograph ground the logo is knocked out in white, as on the other slides' marks."""
    if not LOGO.exists():
        raise SlideError("the ws.regulab logo file is missing (rules/motion/official-logo-transparent.png)")
    w, h = size or slides.SIZES["regulab"]
    canvas, on_ground = slides.background((w, h), ground)
    ink, muted, accent = ((slides.ON_GROUND_INK, slides.ON_GROUND_MUTED, slides.ON_GROUND_ACCENT) if on_ground
                          else (slides.INK, slides.MUTED, slides.ACCENT))
    d = ImageDraw.Draw(canvas)
    small = slides._font(slides.BODY_BOLD, 24)
    counter = f"{index + 1}/{total}"
    d.text((w - slides.MARGIN - small.getlength(counter), slides.MARGIN), counter, font=small, fill=muted)

    logo = _logo(round(w * 0.64), white=on_ground)
    big, body = slides._font(slides.DISPLAY, 74), slides._font(slides.BODY, 34)
    rule_gap, line_gap = 56, 28
    block = logo.height + rule_gap + 4 + rule_gap + round(big.size * 1.12) + line_gap + round(body.size * 1.3)
    y = max(slides.MARGIN + slides.HEAD_H, (h - block) // 2)
    canvas.paste(logo, ((w - logo.width) // 2, y), logo)
    y += logo.height + rule_gap
    d.line([w // 2 - 40, y, w // 2 + 40, y], fill=accent, width=4)
    y += 4 + rule_gap
    _centred(d, FOLLOW_EN, big, w // 2, y, ink)
    y += round(big.size * 1.12) + line_gap
    _centred(d, FOLLOW_BM, body, w // 2, y, muted)
    return canvas


def closing_jpeg(index: int, total: int, *, ground: bytes | None = None, size: tuple[int, int] | None = None,
                 quality: int = 90) -> bytes:
    buf = io.BytesIO()
    closing_card(index, total, ground=ground, size=size).save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
    return buf.getvalue()
