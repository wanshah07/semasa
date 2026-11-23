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
import re
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from . import compliance, glossary, slides
from .log import get_logger
from .slides import SlideError

log = get_logger("semasa.carousel")

MAX_SLIDES = 6                      # pictures in one carousel, the logo card included
COMFORT = 0.8                       # a joined slide must fit at this share of the normal type size, or it is not joined
ROOT = Path(__file__).resolve().parents[2]
LOGO = ROOT / "rules" / "motion" / "official-logo-transparent.png"      # the same file the Motion films' logo card uses

FOLLOW_EN = "Follow us for more"
FOLLOW_BM = "Ikuti kami untuk info seterusnya"
# the closing card's tagline: the caption's own follow line (Wan, 22 Nov 2026: "logo ... ketengah, besarkan dan letak tagline
# 'follow untuk...'"), drawn big under the logo, with the English line small beneath it
TAGLINE = "Follow untuk tip regulatori yang senang faham."


def is_follow_slide(slide: dict[str, Any]) -> bool:
    """A slide whose words are only the caption's follow invitation: never drawn (the closing card carries that line)."""
    from . import motion_captions
    words = " ".join(str(slide.get(k) or "") for k in ("title", "lead", "note")) + " " + " ".join(
        str(p) for p in (slide.get("points") or []))
    words = " ".join(words.split())
    return bool(words) and not slide.get("ayat") and motion_captions.follow_ask(words) and len(words) <= 160


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
    None when the points would not all fit the slide shape (a join never drops one), and None for a slide that carries
    an ayat al-Quran: a verse is drawn whole on a card of its own and is never folded into another slide's points."""
    if a.get("ayat") or b.get("ayat"):
        return None
    points = [_clean(a.get("lead")), *(a.get("points") or []), _sentence(b.get("title", ""), b.get("lead", "")),
              *(b.get("points") or []), _clean(b.get("note"))]
    points = [p for p in (_clean(p) for p in points) if p]
    if len(points) > compliance.MAX_POINTS:
        return None
    keep = {k: v for k, v in a.items() if k not in ("title", "points", "lead", "note")}
    feet = [str(x.get("foot") or "") for x in (a, b) if x.get("foot")]
    if len(feet) == 2:                 # both slides' definition notes ride on the joined one, two terms at most
        keep["foot"] = glossary.merge_feet(feet, "en" if "Definition:" in feet[0] else "bm")
    elif feet:
        keep["foot"] = feet[0]
    return {"title": a.get("title", ""), "points": points, **keep}


def split_full(items: list[dict[str, Any]], keep: int = 3) -> list[dict[str, Any]]:
    """The last resort for a slide that no look can fit: every slide with more than `keep` points is drawn as two, the same
    headline marked 1/2 and 2/2 and the points shared between them. Every word is kept; a verse is never split."""
    out: list[dict[str, Any]] = []
    for s in items:
        pts = [p for p in (_clean(p) for p in (s.get("points") or [])) if p]
        if s.get("ayat") or len(pts) <= keep:
            out.append(s)
            continue
        half = (len(pts) + 1) // 2
        title = _clean(s.get("title"))
        rest = {k: v for k, v in s.items() if k not in ("title", "points", "lead", "note")}
        out.append({**rest, "title": f"{title} (1/2)".strip(), "points": pts[:half], "lead": s.get("lead") or ""})
        out.append({**rest, "title": f"{title} (2/2)".strip(), "points": pts[half:], "note": s.get("note") or ""})
    return out


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
    """The last picture, one standard format (Wan, 22 Nov 2026): the logo large in the middle, a short rule, the tagline
    "Follow untuk tip regulatori yang senang faham." big and "Follow us for more" small under it, with the page count the other
    slides carry. No logo in the corner. On a photograph ground the logo is knocked out in white, as on the other slides'."""
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

    logo = _logo(round(w * 0.78), white=on_ground)
    big, body = slides._font(slides.DISPLAY, 66), slides._font(slides.BODY, 32)
    lines = _balanced(TAGLINE, big, w - 2 * slides.MARGIN - 40)
    rule_gap, line_gap, lh = 60, 30, round(big.size * 1.14)
    block = logo.height + rule_gap + 4 + rule_gap + lh * len(lines) + line_gap + round(body.size * 1.3)
    y = max(slides.MARGIN + slides.HEAD_H, (h - block) // 2)
    canvas.paste(logo, ((w - logo.width) // 2, y), logo)
    y += logo.height + rule_gap
    d.line([w // 2 - 40, y, w // 2 + 40, y], fill=accent, width=4)
    y += 4 + rule_gap
    for line in lines:
        _centred(d, " ".join(r.text for r in line.runs), big, w // 2, y, ink)
        y += lh
    y += line_gap
    _centred(d, FOLLOW_EN, body, w // 2, y, muted)
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
COVER_WHITE = (255, 255, 255)
COVER_INK = (17, 17, 17)
COVER_RED = (211, 32, 39)
COVER_MUTED = (90, 90, 90)
COVER_VERSION = 3          # 1: dark green; 2: white, light-blue waves, red hook word; 3: a short title + a cut-out (23 Nov 2026)
COVER_SECONDS = 1.1                    # the cover frame at the start of a film (TikTok takes its cover at 1.0 s by default)


def _gradient(size: tuple[int, int]) -> Image.Image:
    w, h = size
    mask = Image.linear_gradient("L").resize((w, h))
    return Image.composite(Image.new("RGB", size, GREEN_BOTTOM), Image.new("RGB", size, GREEN_TOP), mask)


def _layer(size: tuple[int, int]) -> Image.Image:
    return Image.new("RGBA", size, (0, 0, 0, 0))


def _orb(canvas: Image.Image, box: tuple[float, float, float, float], fill: tuple[int, int, int, int], blur: float) -> None:
    from PIL import ImageFilter
    layer = _layer(canvas.size)
    ImageDraw.Draw(layer).ellipse(box, fill=fill)
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    canvas.paste(layer, (0, 0), layer)


def _rings(canvas: Image.Image) -> None:
    """Fine concentric rings around the middle of the cover, like a lens or a ripple: the cover reads as a lit, designed
    surface and the eye is drawn to the logo and the hook at the centre. Drawn at twice the size and brought down, so the
    hairlines are smooth."""
    w, h = canvas.size
    k = 2
    layer = _layer((w * k, h * k))
    d = ImageDraw.Draw(layer)
    cx, cy = w * k * 0.5, h * k * 0.47
    for i in range(9):
        r = (w * 0.34 + i * w * 0.15) * k
        alpha = max(16, 74 - i * 7)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(196, 242, 226, alpha), width=2 * k // 2 + 1)
    r = (w * 0.34 + 3 * w * 0.15) * k                       # one ring in the brand gold
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(246, 206, 160, 130), width=k + 1)
    layer = layer.resize((w, h), Image.LANCZOS)
    canvas.paste(layer, (0, 0), layer)


def _blue_waves(canvas: Image.Image) -> None:
    """The white cover's wave circles (Wan, 22 Nov 2026: "with wave circle light blue"): concentric light-blue rings around the
    middle, the inner ones a little stronger, with a soft blue glow at the centre. Drawn at twice the size and brought down so
    the lines are smooth; light enough that the black title and the green logo stay crisp over them."""
    from PIL import ImageFilter
    w, h = canvas.size
    glow = Image.new("RGBA", (w, h), (214, 236, 250, 0))      # blue even where transparent: the blur never greys the white
    ImageDraw.Draw(glow).ellipse([w * 0.12, h * 0.17, w * 0.88, h * 0.77], fill=(214, 236, 250, 150))
    glow = glow.filter(ImageFilter.GaussianBlur(w * 0.09))
    canvas.paste(glow, (0, 0), glow)
    k = 2
    layer = Image.new("RGBA", (w * k, h * k), (150, 205, 238, 0))
    d = ImageDraw.Draw(layer)
    cx, cy = w * k * 0.5, h * k * 0.47
    for i in range(10):
        r = (w * 0.30 + i * w * 0.12) * k
        alpha = max(70, 200 - i * 14)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(150, 205, 238, alpha), width=k * 3 if i % 3 == 0 else k + 2)
    layer = layer.resize((w, h), Image.LANCZOS)
    canvas.paste(layer, (0, 0), layer)


def _vignette(canvas: Image.Image) -> None:
    w, h = canvas.size
    mask = Image.radial_gradient("L").resize((w, h)).point(lambda v: round(max(0, v - 70) * 0.62))
    canvas.paste(Image.new("RGB", canvas.size, (2, 18, 14)), (0, 0), mask)


def _grain(canvas: Image.Image) -> Image.Image:
    """A fine film grain, so the gradients do not band when the platform compresses the picture."""
    noise = Image.effect_noise(canvas.size, 36).convert("RGB")
    return Image.blend(canvas, noise, 0.028)


def _glow(canvas: Image.Image) -> Image.Image:
    """The cover's backdrop finish: a mint light top right, a warm gold glow low left, a deep emerald pool behind the title,
    fine rings, a vignette and a little grain. Returns the finished canvas."""
    w, h = canvas.size
    _orb(canvas, (w * 0.30, -h * 0.14, w * 1.35, h * 0.30), (110, 224, 190, 70), w * 0.14)
    _orb(canvas, (-w * 0.55, h * 0.70, w * 0.62, h * 1.14), (246, 190, 120, 46), w * 0.16)
    _orb(canvas, (-w * 0.20, h * 0.34, w * 1.20, h * 0.78), (2, 40, 30, 70), w * 0.18)
    _orb(canvas, (w * 0.18, h * 0.16, w * 0.82, h * 0.40), (150, 240, 205, 52), w * 0.12)      # a bloom behind the logo
    _rings(canvas)
    _vignette(canvas)
    return _grain(canvas)


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


ART_BAND = 0.36            # the share of the cover's height the hook's illustration takes, at the foot (Wan, 23 Nov 2026)


def _art_band(canvas: Image.Image, art: bytes, band: int) -> None:
    """The hook's illustration, a transparent cut-out (illustrated.cutout), standing on the foot of the cover: fitted inside the
    band without cropping, centred, no card behind it, so the cover's light-blue rings show round it."""
    w, h = canvas.size
    margin = round(w * 0.11)
    pic = Image.open(io.BytesIO(art)).convert("RGBA")
    box_w, box_h = w - 2 * margin, band - round(w * 0.05)
    scale = min(box_w / pic.width, box_h / pic.height)
    pic = pic.resize((max(1, round(pic.width * scale)), max(1, round(pic.height * scale))), Image.LANCZOS)
    canvas.paste(pic, ((w - pic.width) // 2, h - round(w * 0.05) - pic.height), pic)


def cover_card(title: str, lead: str = "", eyebrow: str = "", *, ground: bytes | None = None,
               size: tuple[int, int] | None = None, art: bytes | None = None) -> Image.Image:
    """The branded cover: logo, a rule, the hook title, a short supporting line (`eyebrow` is accepted, never drawn: the
    cover carries no tag). Since 22 Nov 2026 (Wan: "background white, green color logo, title black text and red hook word") it
    is a white card with light-blue wave circles: the logo in its own green, the title in black and its hook word (the *marked*
    one, else the last word) in red. Everything sits in a block
    centred inside the part of the picture an Instagram grid tile keeps (for a tall film frame, the middle three quarters of
    the height). A hook that is too long for the cover is drawn smaller, never cut."""
    if not LOGO.exists():
        raise SlideError("the ws.regulab logo file is missing (rules/motion/official-logo-transparent.png)")
    w, h = size or slides.SIZES["regulab"]
    canvas = Image.new("RGB", (w, h), COVER_WHITE)        # white whatever the ground: the picture stays on the slides after it
    _blue_waves(canvas)
    d = ImageDraw.Draw(canvas)
    title = _clean(title)
    if title and "*" not in title:                        # no hook word marked: the last word carries the red
        head, _, last = title.rpartition(" ")
        title = f"{head} *{last}*".strip() if last else title

    margin = round(w * 0.11)
    col = w - 2 * margin
    tall = h / w > 1.6                                    # a film's opening frame, not a carousel's first slide
    band = h * (0.62 if tall else 0.80)                   # the vertical room the block may use: inside the grid's crop
    art_h = round(h * ART_BAND) if (art and not tall) else 0       # the hook's illustration takes the foot of a carousel's cover
    if art_h:
        band = (h - art_h) * 0.94                         # the words keep the part above it
    # a film's cover is quieter (Wan, 11 Nov 2026: "make sure the cover text not too big & make it aesthetic"): on the tall
    # frame the same sizes read as shouting, so the logo and the hook are both drawn smaller and the hook gets more air
    logo = _logo(round(w * (0.36 if tall else 0.46)), white=False)
    small = slides._font(slides.BODY_BOLD, round(w * 0.026))
    label = ""                                              # no tag on the cover (Wan, 11 Nov: "remove word hook")
    body_font = slides._font(slides.BODY, round(w * 0.036))
    lead_lines = slides.wrap(_clean(lead), body_font, col) if _clean(lead) else []
    if len(lead_lines) > 3:
        raise SlideError("the supporting line is too long for the cover")
    body_lh = round(body_font.size * 1.4)
    gap = round(w * 0.05)
    fixed = logo.height + gap + 4 + gap + (round(small.size * 1.4) + round(gap * 0.5) if label else 0)
    fixed += (len(lead_lines) * body_lh + round(gap * 0.7)) if lead_lines else 0

    size_px = round(w * (0.072 if tall else 0.108))
    floor = round(w * (0.046 if tall else 0.05))
    while True:
        font = slides._font(slides.DISPLAY, size_px)
        lines = _balanced(title, font, col)
        lh = round(font.size * (1.2 if tall else 1.1))
        if fixed + len(lines) * lh <= band or size_px <= floor:
            break
        size_px -= 4
    total = fixed + len(lines) * lh
    y = round(((h - art_h) - total) / 2)

    canvas.paste(logo, ((w - logo.width) // 2, y), logo)
    y += logo.height + gap
    d.line([w // 2 - 44, y, w // 2 + 44, y], fill=COVER_RED, width=4)
    y += 4 + gap
    if label:
        d.text(((w - small.getlength(label)) / 2, y), label, font=small, fill=COVER_RED)
        y += round(small.size * 1.4) + round(gap * 0.5)
    for line in lines:                                     # centred, one line at a time
        x = (w - line.width) / 2
        space = font.getlength(" ")
        cx = x
        for i, run in enumerate(line.runs):
            if i:
                cx += space
            d.text((cx, y), run.text, font=font, fill=COVER_RED if run.emph else COVER_INK)
            cx += font.getlength(run.text)
        y += lh
    if lead_lines:
        y += round(gap * 0.7)
        for line in lead_lines:
            cx = (w - line.width) / 2
            for i, run in enumerate(line.runs):
                if i:
                    cx += body_font.getlength(" ")
                d.text((cx, y), run.text, font=body_font, fill=COVER_MUTED)
                cx += body_font.getlength(run.text)
            y += body_lh
    if art_h:
        _art_band(canvas, art, art_h)
    return canvas


COVER_TITLE_WORDS = 6      # the cover's own title: short (Wan, 23 Nov 2026: the long hook is the first PAGE, not the cover)
COVER_TITLE_SYSTEM = (
    "You write the TITLE on the cover of a social-media carousel. The first page after the cover carries the full hook; "
    "the cover carries only a short title that names the same idea. Write at most %d words, in the SAME language and "
    "voice as the hook (Malaysian Malay mix stays Malaysian Malay; never Bahasa Indonesia), no full stop, no emoji, no "
    "hashtag. Take only words and facts that are in the hook: add no number, name, date or claim of your own. Put "
    "*asterisks* round the ONE word that carries the idea. Answer with ONE JSON object: {\"title\": \"...\"}")


def short_title(llm: Any, hook: str, stream: str = "regulab") -> str:
    """The short title for the cover. The writer shortens the hook; any answer that is long, empty or breaks a rule that blocks
    a post is dropped for the hook's own first words, so the cover is always short and never invents anything."""
    from . import compliance
    hook = _clean(hook)
    plain = hook.replace("*", "")
    fallback = _lead_words(plain, COVER_TITLE_WORDS)
    if len(plain.split()) <= COVER_TITLE_WORDS:
        return hook
    got = ""
    try:
        out = llm.chat_json(COVER_TITLE_SYSTEM % COVER_TITLE_WORDS, hook[:600], max_tokens=200) if llm is not None else None
        got = _clean(str(out.get("title") or "")) if isinstance(out, dict) else ""
    except Exception as exc:  # noqa: BLE001 - the hook's own first words stand in
        got = ""
        log.info("cover title not shortened (%s)", str(exc)[:100])
    words = got.replace("*", "").split()
    if not got or len(words) > COVER_TITLE_WORDS + 1 or len(words) < 2:
        return fallback
    flags = compliance.scan({"stream": stream, "media": [{"artwork": [{"title": got.replace("*", ""), "points": []}]}]})
    if compliance.hard_count([f for f in flags if str(f.get("where") or "").startswith(("Design", "Slide", "Artwork"))]):
        return fallback
    return got


def _lead_words(text: str, n: int) -> str:
    """The first clause of `text` when it is short enough, else its first `n` words; no trailing punctuation."""
    for part in re.split(r"(?<=[.:;!?])\s+", text):
        part = part.strip().rstrip(".:;!?,")
        if 2 <= len(part.split()) <= n:
            return part
        break
    return " ".join(text.split()[:n]).rstrip(".:;!?,")


def cover_words(first: dict | None) -> tuple[str, str] | None:
    """(title, supporting line) for the cover when a carousel's first slide is a hook, else None.

    A hook is a title with no note and at most ONE short line under it. The writer usually gives the hook exactly one
    such line, as a point, and the first rule ("no points at all") refused all of those: six approved carousels were
    redrawn on 11 Nov 2026 and still had no cover, which the Instagram gate then holds back. That one line is the cover's
    supporting line. A first slide with two or more points or a note is a content slide: the cover must not replace it,
    so there is none."""
    first = first if isinstance(first, dict) else {}
    title = str(first.get("title") or "").strip()
    points = [str(p).strip() for p in (first.get("points") or []) if str(p or "").strip()]
    if not title or first.get("note") or len(points) > 1 or first.get("ayat"):       # a verse slide is never a hook: the cover
        return None                                                                  # must not replace it
    return title, str(first.get("lead") or "").strip() or (points[0] if points else "")


def with_front_cover(items: list[dict], stream: str) -> list[dict]:
    """The slides with a hook slide put in front when the first one is a content slide (Wan, 11 Nov 2026: "add cover in
    front"). A first slide with several points cannot BE the cover without losing its points, and without a cover the
    Instagram gate holds the post back. So the title is repeated on a slide of its own in front, which the cover then
    replaces, and the content slide follows whole. Nothing changes when the first slide is already a hook, for LinkedIn
    (no cover), or for a single picture. Doing it twice changes nothing: the second time the first slide is a hook."""
    if stream == "linkedin" or len(items) < 2 or not isinstance(items[0], dict):
        return items
    title = str(items[0].get("title") or "").strip()
    if not title or cover_words(items[0]) is not None:
        return items
    return [{"title": title, "points": [], "front_cover": True}, *items]


def cover_jpeg(title: str, lead: str = "", eyebrow: str = "", *, ground: bytes | None = None,
               size: tuple[int, int] | None = None, quality: int = 92, art: bytes | None = None) -> bytes:
    buf = io.BytesIO()
    cover_card(title, lead, eyebrow, ground=ground, size=size, art=art).save(buf, "JPEG", quality=quality, optimize=True)
    return buf.getvalue()
