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


# --- the cover (Wan, 11 Nov 2026) -------------------------------------------------------------------------------------------
# "for instagram & tiktok, create cover page so the tile pages look aesthetic, the cover must contain the ws.regulab logo and
# the hook title." Instagram's profile grid shows a post by its FIRST picture, cropped to 3:4 (a Reel's 9:16 is cropped top and
# bottom to the same shape), and TikTok shows the opening frame. So the first picture of every ws.regulab carousel, and the
# opening frames of every ws.regulab film, are this one branded cover: deep green, the white ws.regulab logo, the hook title
# big, kept inside the part the grid does not crop. Drawn, never written: the hook stays the post's words and the caption
# does not change.

GREEN_TOP = (6, 46, 29)
GREEN_BOTTOM = (4, 104, 101)           # the two ends of the logo's own green-to-teal
COVER_GOLD = (246, 206, 160)
COVER_CREAM = (244, 240, 232)
COVER_SECONDS = 1.1                    # the cover frame at the start of a film (TikTok takes its cover at 1.0 s by default)


def _gradient(size: tuple[int, int]) -> Image.Image:
    w, h = size
    mask = Image.linear_gradient("L").resize((w, h))
    return Image.composite(Image.new("RGB", size, GREEN_BOTTOM), Image.new("RGB", size, GREEN_TOP), mask)


def _glow(canvas: Image.Image) -> None:
    """A soft lighter patch top right: the cover reads as a lit surface, not a flat fill."""
    from PIL import ImageFilter
    w, h = canvas.size
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse([w * 0.35, -h * 0.18, w * 1.25, h * 0.42], fill=(120, 210, 190, 46))
    layer = layer.filter(ImageFilter.GaussianBlur(w * 0.12))
    canvas.paste(layer, (0, 0), layer)


def _watermark(canvas: Image.Image) -> None:
    """The logo's mark, very faint and large, bleeding off the bottom right corner."""
    w, h = canvas.size
    mark = _logo(round(w * 0.9), white=True)
    mark = mark.crop((0, 0, mark.width, round(mark.height * 0.5)))
    alpha = mark.getchannel("A").point(lambda v: round(v * 0.07))
    mark.putalpha(alpha)
    canvas.paste(mark, (round(w * 0.42), round(h * 0.70)), mark)


def _balanced(text: str, font: Any, width: float) -> list[Any]:
    """The title wrapped to the same number of lines it needs at full width, as narrow as that allows: the lines come out even
    and a lone word is not left on the last line."""
    lines = slides.wrap(text, font, width)
    if len(lines) < 2:
        return lines
    w = width
    while w > width * 0.6:
        w -= width * 0.02
        trial = slides.wrap(text, font, w)
        if len(trial) != len(lines):
            break
        best = trial
        lines = best
    return lines


def cover_card(title: str, lead: str = "", eyebrow: str = "", *, ground: bytes | None = None,
               size: tuple[int, int] | None = None) -> Image.Image:
    """The branded cover: logo, a gold rule, the domain, the hook title, a short supporting line. Everything sits in a block
    centred inside the part of the picture an Instagram grid tile keeps (for a tall film frame, the middle three quarters of
    the height). A hook that is too long for the cover is drawn smaller, never cut."""
    if not LOGO.exists():
        raise SlideError("the ws.regulab logo file is missing (rules/motion/official-logo-transparent.png)")
    w, h = size or slides.SIZES["regulab"]
    if ground:
        canvas, _ = slides.background((w, h), ground)
        wash = _gradient((w, h)).convert("RGBA")
        wash.putalpha(214)
        canvas = canvas.convert("RGBA")
        canvas.alpha_composite(wash)
        canvas = canvas.convert("RGB")
    else:
        canvas = _gradient((w, h))
    _glow(canvas)
    _watermark(canvas)
    d = ImageDraw.Draw(canvas)

    margin = round(w * 0.11)
    col = w - 2 * margin
    band = h * (0.62 if h / w > 1.6 else 0.80)            # the vertical room the block may use: inside the grid's crop
    logo = _logo(round(w * 0.46), white=True)
    small = slides._font(slides.BODY_BOLD, round(w * 0.026))
    label = slides.eyebrow_text(eyebrow, small, col) if eyebrow.strip() else ""
    body_font = slides._font(slides.BODY, round(w * 0.036))
    lead_lines = slides.wrap(_clean(lead), body_font, col) if _clean(lead) else []
    if len(lead_lines) > 3:
        raise SlideError("the supporting line is too long for the cover")
    body_lh = round(body_font.size * 1.4)
    gap = round(w * 0.05)
    fixed = logo.height + gap + 4 + gap + (round(small.size * 1.4) + round(gap * 0.5) if label else 0)
    fixed += (len(lead_lines) * body_lh + round(gap * 0.7)) if lead_lines else 0

    size_px = round(w * 0.108)
    floor = round(w * 0.05)
    while True:
        font = slides._font(slides.DISPLAY, size_px)
        lines = _balanced(_clean(title), font, col)
        lh = round(font.size * 1.1)
        if fixed + len(lines) * lh <= band or size_px <= floor:
            break
        size_px -= 4
    total = fixed + len(lines) * lh
    y = round((h - total) / 2)

    canvas.paste(logo, ((w - logo.width) // 2, y), logo)
    y += logo.height + gap
    d.line([w // 2 - 44, y, w // 2 + 44, y], fill=COVER_GOLD, width=4)
    y += 4 + gap
    if label:
        d.text(((w - small.getlength(label)) / 2, y), label, font=small, fill=COVER_GOLD)
        y += round(small.size * 1.4) + round(gap * 0.5)
    for line in lines:                                     # centred, one line at a time
        x = (w - line.width) / 2
        space = font.getlength(" ")
        cx = x
        for i, run in enumerate(line.runs):
            if i:
                cx += space
            d.text((cx, y), run.text, font=font, fill=COVER_GOLD if run.emph else (255, 255, 255))
            cx += font.getlength(run.text)
        y += lh
    if lead_lines:
        y += round(gap * 0.7)
        for line in lead_lines:
            cx = (w - line.width) / 2
            for i, run in enumerate(line.runs):
                if i:
                    cx += body_font.getlength(" ")
                d.text((cx, y), run.text, font=body_font, fill=COVER_CREAM)
                cx += body_font.getlength(run.text)
            y += body_lh
    return canvas


def cover_jpeg(title: str, lead: str = "", eyebrow: str = "", *, ground: bytes | None = None,
               size: tuple[int, int] | None = None, quality: int = 92) -> bytes:
    buf = io.BytesIO()
    cover_card(title, lead, eyebrow, ground=ground, size=size).save(buf, "JPEG", quality=quality, optimize=True)
    return buf.getvalue()
