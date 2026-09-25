"""Carousel slides, drawn here with Pillow: words in, JPEGs out. No AI, no cost per slide.

The words come from the draft (`semasa_posts.slides`, written by the writer and edited by Wan);
a render job (`media_generations`, mode `slides`) carries a SNAPSHOT of them, so the pictures are
exactly what was asked for and the page can tell when the words have moved on since.

Rules carried over from ws.regulab Studio, each one learned the hard way:
  * every word is kept. A slide that cannot fit at the smallest type size FAILS the render with
    the slide named; it is never cut, and nothing (not the badge, not a picture) costs a point;
  * a token too wide for the column (a MAL number, a DOI, a long reference) is split by
    character instead of running off the edge;
  * `*word*` is emphasis: drawn in the accent colour, and the asterisks never reach the picture;
  * the content block is centred between the header and the footer. That is only safe because
    nothing here sizes itself off where the block starts;
  * ws.regulab: the website is on the artwork footer and nowhere else. LinkedIn: no ws.regulab
    identity at all, no logo, no website, no name;
  * the closing slide carries the source line, so the instrument is on the artwork.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from . import compliance

FONTS = Path(__file__).resolve().parent / "fonts"
DISPLAY = FONTS / "Fraunces-SemiBold.ttf"
BODY = FONTS / "Inter-Regular.ttf"
BODY_BOLD = FONTS / "Inter-SemiBold.ttf"

SIZES = {"regulab": (1080, 1080), "linkedin": (1080, 1350)}

# The regulab theme of the page (web/src/design/themes/regulab.css), so the cards look like home.
PAPER = (250, 247, 242)
INK = (28, 25, 23)
MUTED = (120, 113, 108)
ACCENT = (176, 121, 42)
LINE = (230, 221, 206)
ON_GROUND_INK = (255, 255, 255)
ON_GROUND_MUTED = (226, 222, 216)
ON_GROUND_ACCENT = (246, 206, 160)

MARGIN = 88
HEAD_H = 64            # eyebrow + counter row
FOOT_H = 64            # the ws.regulab website row (kept on LinkedIn as plain margin)
MIN_SCALE = 0.55
SCALE_STEP = 0.05

_EMPH = re.compile(r"\*([^*\n]+)\*")


class SlideError(ValueError):
    """A render that must not go ahead; the message is shown to Wan on the job."""


# --- the words ----------------------------------------------------------------------

def normalise(raw: Any) -> list[dict[str, Any]]:
    """Force [{title, points[]}] with sane limits; empty slides are dropped. One definition,
    shared with the compliance scan (and mirrored in the page), so all three agree."""
    return compliance.normalise_slides(raw)


def same_words(a: Any, b: Any) -> bool:
    """True when two slide lists carry the same words (what the scan and the page compare)."""
    return compliance.slides_key(a) == compliance.slides_key(b)


# --- layout ---------------------------------------------------------------------------

@dataclass
class Run:
    text: str
    emph: bool


@dataclass
class Line:
    runs: list[Run] = field(default_factory=list)
    width: float = 0.0


def tokens(text: str) -> list[Run]:
    """Words with an emphasis flag. A matched *pair* on one line is a marker; a lone * is text."""
    out: list[Run] = []
    pos = 0
    for m in _EMPH.finditer(text):
        out += [Run(w, False) for w in text[pos:m.start()].split()]
        out += [Run(w, True) for w in m.group(1).split()]
        pos = m.end()
    out += [Run(w, False) for w in text[pos:].split()]
    return out


def strip_emphasis(text: str) -> str:
    return _EMPH.sub(r"\1", text)


def hard_split(word: str, font: ImageFont.FreeTypeFont, width: float) -> list[str]:
    """Split a token wider than the column by character. A token that fits is returned whole."""
    if font.getlength(word) <= width:
        return [word]
    parts, cur = [], ""
    for ch in word:
        if cur and font.getlength(cur + ch) > width:
            parts.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        parts.append(cur)
    return parts


def wrap(text: str, font: ImageFont.FreeTypeFont, width: float) -> list[Line]:
    space = font.getlength(" ")
    lines: list[Line] = []
    cur = Line()
    for run in tokens(text):
        for piece in hard_split(run.text, font, width):
            w = font.getlength(piece)
            add = w if not cur.runs else space + w
            if cur.runs and cur.width + add > width:
                lines.append(cur)
                cur = Line()
                add = w
            cur.runs.append(Run(piece, run.emph))
            cur.width += add
    if cur.runs:
        lines.append(cur)
    return lines


@dataclass
class Block:
    """One laid-out slide body: title lines, then points, at one scale."""
    title_font: ImageFont.FreeTypeFont
    body_font: ImageFont.FreeTypeFont
    title: list[Line]
    points: list[list[Line]]
    title_lh: int
    body_lh: int
    gap_title: int
    gap_point: int
    bullet: bool

    @property
    def height(self) -> int:
        h = len(self.title) * self.title_lh
        if self.points:
            if self.title:
                h += self.gap_title
            h += sum(len(p) * self.body_lh for p in self.points) + self.gap_point * (len(self.points) - 1)
        return h


def _font(path: Path, size: float) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), max(8, round(size)))


def layout(slide: dict[str, Any], kind: str, width: int, scale: float, tall: bool) -> Block:
    base_title = {"cover": 92 if not tall else 100, "point": 68, "close": 68}[kind]
    base_body = {"cover": 38, "point": 40, "close": 40}[kind]
    tf = _font(DISPLAY, base_title * scale)
    bf = _font(BODY, base_body * scale)
    bullet = kind != "cover" and len(slide["points"]) > 1
    indent = round(34 * scale) if bullet else 0
    title = wrap(slide["title"], tf, width) if slide["title"] else []
    points = [wrap(p, bf, width - indent) for p in slide["points"]]
    return Block(tf, bf, title, points, title_lh=round(tf.size * 1.12), body_lh=round(bf.size * 1.38),
                 gap_title=round(34 * scale), gap_point=round(22 * scale), bullet=bullet)


def fit(slide: dict[str, Any], kind: str, width: int, height: int, tall: bool) -> Block:
    scale = 1.0
    while scale >= MIN_SCALE - 1e-9:
        block = layout(slide, kind, width, scale, tall)
        if block.height <= height:
            return block
        scale = round(scale - SCALE_STEP, 2)
    raise SlideError("too long to fit even at the smallest type size; shorten it or split it into two slides")


# --- drawing --------------------------------------------------------------------------

def cover_fit(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    w, h = size
    src = img.convert("RGB")
    ratio = max(w / src.width, h / src.height)
    src = src.resize((max(w, round(src.width * ratio)), max(h, round(src.height * ratio))), Image.LANCZOS)
    left, top = (src.width - w) // 2, (src.height - h) // 2
    return src.crop((left, top, left + w, top + h))


def background(size: tuple[int, int], ground: bytes | None) -> tuple[Image.Image, bool]:
    """(canvas, on_ground). A ground is a photograph under a dark scrim, so white ink reads on it."""
    w, h = size
    if ground:
        try:
            photo = cover_fit(Image.open(io.BytesIO(ground)), size)
        except Exception as exc:  # noqa: BLE001 - a bad ground is reported, never drawn half
            raise SlideError(f"the background picture could not be opened ({type(exc).__name__})") from exc
        scrim = Image.new("L", (1, h))
        for y in range(h):
            scrim.putpixel((0, y), round(150 + 70 * (y / max(1, h - 1))))   # 59% at the top, 86% at the foot
        black = Image.new("RGB", size, (12, 10, 9))
        return Image.composite(black, photo, scrim.resize(size)), True
    canvas = Image.new("RGB", size, PAPER)
    ImageDraw.Draw(canvas).rectangle([MARGIN, MARGIN - 28, MARGIN + 120, MARGIN - 22], fill=ACCENT)
    return canvas, False


def eyebrow_text(label: str, font: ImageFont.FreeTypeFont, width: float) -> str:
    """The small label above the slide. Decoration, not a fact, so it may be shortened to fit."""
    plain = re.sub(r"\s+", " ", strip_emphasis(label)).strip().upper()
    spaced = " ".join(plain)
    if font.getlength(spaced) <= width:
        return spaced
    if font.getlength(plain) <= width:
        return plain
    words = plain.split(" ")
    while len(words) > 1 and font.getlength(" ".join(words) + "…") > width:
        words.pop()
    return " ".join(words) + "…"


def draw_lines(d: ImageDraw.ImageDraw, lines: list[Line], x: int, y: int, font: ImageFont.FreeTypeFont,
               lh: int, ink: tuple[int, int, int], accent: tuple[int, int, int]) -> int:
    space = font.getlength(" ")
    for line in lines:
        cx = float(x)
        for i, run in enumerate(line.runs):
            if i:
                cx += space
            d.text((cx, y), run.text, font=font, fill=accent if run.emph else ink)
            cx += font.getlength(run.text)
        y += lh
    return y


def render_one(slide: dict[str, Any], index: int, total: int, *, stream: str, eyebrow: str, source: str,
               website: str, ground: bytes | None) -> Image.Image:
    size = SIZES.get(stream, SIZES["regulab"])
    w, h = size
    tall = h > w
    canvas, on_ground = background(size, ground)
    ink, muted, accent = (ON_GROUND_INK, ON_GROUND_MUTED, ON_GROUND_ACCENT) if on_ground else (INK, MUTED, ACCENT)
    d = ImageDraw.Draw(canvas)
    col = w - 2 * MARGIN

    small = _font(BODY_BOLD, 24)
    counter = f"{index + 1}/{total}"
    d.text((w - MARGIN - small.getlength(counter), MARGIN), counter, font=small, fill=muted)
    if eyebrow:
        d.text((MARGIN, MARGIN), eyebrow_text(eyebrow, small, col - small.getlength(counter) - 40), font=small,
               fill=accent)

    top = MARGIN + HEAD_H
    bottom = h - MARGIN - FOOT_H
    kind = "cover" if index == 0 else ("close" if index == total - 1 and total > 1 else "point")

    src_lines: list[Line] = []
    src_font = _font(BODY, 24)
    if kind == "close" and source.strip():
        label = "Sumber: " if stream != "linkedin" else "Source: "
        for sz in (24, 22, 20):
            src_font = _font(BODY, sz)
            src_lines = wrap(label + strip_emphasis(source.strip()), src_font, col)
            if len(src_lines) <= 4:
                break
        if len(src_lines) > 4:
            raise SlideError("the source line is too long for the closing slide; shorten the Source field")
    src_lh = round(src_font.size * 1.35)
    src_h = (len(src_lines) * src_lh + 28) if src_lines else 0

    block = fit(slide, kind, col, bottom - top - src_h, tall)
    y = top + max(0, (bottom - top - src_h - block.height) // 2)
    y = draw_lines(d, block.title, MARGIN, y, block.title_font, block.title_lh, ink, accent)
    if block.points and block.title:
        y += block.gap_title
    indent = round(34 * block.body_font.size / 40) if block.bullet else 0
    for i, pts in enumerate(block.points):
        if block.bullet and pts:
            r = max(4, round(block.body_font.size * 0.16))
            cy = y + block.body_lh // 2
            d.ellipse([MARGIN + 2, cy - r, MARGIN + 2 + 2 * r, cy + r], fill=accent)
        y = draw_lines(d, pts, MARGIN + indent, y, block.body_font, block.body_lh, ink if kind != "cover" else muted,
                       accent)
        if i < len(block.points) - 1:
            y += block.gap_point

    if src_lines:
        sy = bottom - len(src_lines) * src_lh
        d.line([MARGIN, sy - 16, MARGIN + 80, sy - 16], fill=accent if on_ground else LINE, width=2)
        draw_lines(d, src_lines, MARGIN, sy, src_font, src_lh, muted, muted)

    if stream != "linkedin" and website.strip():
        foot = _font(BODY_BOLD, 26)
        d.text((MARGIN, h - MARGIN - foot.size), website.strip(), font=foot, fill=muted)
    return canvas


def render(slides: Any, *, stream: str = "regulab", eyebrow: str = "", source: str = "", website: str = "",
           ground: bytes | None = None, quality: int = 90) -> list[bytes]:
    """JPEG bytes, one per slide, in order. Raises SlideError naming the slide that cannot be drawn."""
    items = normalise(slides)
    if not items:
        raise SlideError("no slides to draw: write at least one slide")
    if stream == "linkedin":
        website = ""                                   # rule: no ws.regulab identity on LinkedIn
    out = []
    for i, s in enumerate(items):
        try:
            img = render_one(s, i, len(items), stream=stream, eyebrow=eyebrow, source=source,
                             website=website, ground=ground)
        except SlideError as exc:
            raise SlideError(f"slide {i + 1}: {exc}") from exc
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
        out.append(buf.getvalue())
    return out
