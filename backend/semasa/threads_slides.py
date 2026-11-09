"""Threads-style slides: 2 to 5 pages, each one a short piece of text with a picture under it (or beside it), drawn here
with Pillow. No AI, no cost per page.

Wan, 9 Nov 2026: "add an original text+image slide design inspired by the public Threads reference". The reference page
could not be read by a plain fetch, so this is an original design from the brief and not a copy of anyone's artwork: a
visual carousel, never a native Threads reply series. Nothing is published from here; the pictures go through the same
approval gates as every other Design artwork.

What the layout promises (each one has a test in tests/test_threads_slides.py):
  * page 1 is the cover and carries the hook; every page shows "n/total" in a solid box, and a row of connected nodes
    marks the place in the set (filled node = this page, outlined = the others), so the position never depends on colour;
  * all words are kept. The text is fitted first and the picture takes what is left, down to a floor; a page that cannot
    fit at the smallest type size fails the render with the page named, it is never cut;
  * no word is ever drawn on the picture, so contrast never depends on what the picture is: ink on paper;
  * the picture is the page's own (its `bg`), else the job's background, else an ORIGINAL abstract drawing made here, so
    no page is left with an empty hole and no stock illustration or logo is borrowed;
  * ws.regulab: the website is on the foot and nowhere else. LinkedIn: no ws.regulab identity at all;
  * the closing page carries the source line, as on every other carousel.
"""

from __future__ import annotations

import io
import random
from dataclasses import dataclass
from typing import Any

from PIL import Image, ImageDraw

from . import slides
from .slides import BODY, BODY_BOLD, DISPLAY, Line, SlideError, _font, draw_lines, strip_emphasis, wrap

MIN_PAGES, MAX_PAGES = 2, 5
MAX_POINTS = 3                  # concise: the picture is half of the page
MAX_PAGE_CHARS = 420            # title and points together
MAX_HOOK_WORDS = 16             # the cover's headline
MIN_SIDE, MAX_RATIO = 600, 2.0  # sizes this layout can hold: tall, square or wide, but not a banner

PAPER = slides.PAPER
INK = slides.INK
# the classic muted grey is 4.48:1 on PAPER, just under the 4.5:1 that text needs; this layout draws muted TEXT (the cover's
# lines, the source, the website), so it has its own, darker one (5.2:1). The classic drawing keeps its own.
MUTED = (110, 103, 98)
# the emphasis colour and the small label are text, so they are darker than the classic accent (4.5:1 on PAPER, tested)
ACCENT_TEXT = (133, 86, 18)
ACCENT = slides.ACCENT
PANEL = (238, 229, 214)
EDGE = (196, 184, 166)

# how much of the page's body the picture may take, from the first choice to the floor
IMAGE_SHARES = (0.44, 0.38, 0.32, 0.27)
MIN_SCALE = 0.6
SCALE_STEP = 0.05
SCALES = tuple(round(1 - i * SCALE_STEP, 2) for i in range(round((1 - MIN_SCALE) / SCALE_STEP) + 1))   # 1.0 down to MIN_SCALE
# one picture shared by the whole set is shown this much larger than the page's window, so the window can slide across it
SHARED_ZOOM = 1.45


# --- the words ---------------------------------------------------------------------------

def check(items: list[dict[str, Any]], size: tuple[int, int]) -> None:
    """The rules of this design, with a message Wan can act on. Raised before anything is drawn."""
    if not MIN_PAGES <= len(items) <= MAX_PAGES:
        raise SlideError(f"a Threads-style set must have {MIN_PAGES} to {MAX_PAGES} pages, but {len(items)} were given")
    w, h = size
    if min(w, h) < MIN_SIDE or max(w, h) > MAX_RATIO * min(w, h):
        raise SlideError(f"this design needs a size at least {MIN_SIDE}px on the short side and no more than "
                         f"{MAX_RATIO:g}:1; {w}x{h} does not fit, pick a feed square, a 4:5 portrait or a story")
    for n, item in enumerate(items, 1):
        title = str(item.get("title") or "")
        points = [str(p) for p in item.get("points") or []]
        if n == 1 and not title.strip():
            raise SlideError("page 1 is the cover and needs a headline: that is the hook")
        if n == 1 and len(strip_emphasis(title).split()) > MAX_HOOK_WORDS:
            raise SlideError(f"page 1: the hook is {len(strip_emphasis(title).split())} words, at most {MAX_HOOK_WORDS}")
        if len(points) > MAX_POINTS:
            raise SlideError(f"page {n}: {len(points)} points, at most {MAX_POINTS} on a Threads-style page")
        if len(title) + sum(len(p) for p in points) > MAX_PAGE_CHARS:
            raise SlideError(f"page {n}: too long for a Threads-style page (at most {MAX_PAGE_CHARS} characters); "
                             "shorten it or split it into two pages")


# --- geometry --------------------------------------------------------------------------------

Rect = tuple[int, int, int, int]       # left, top, right, bottom


@dataclass(frozen=True)
class Zones:
    """Where everything goes on one page size. Pure arithmetic, so it is tested without drawing."""
    size: tuple[int, int]
    unit: float
    margin: int
    head: Rect
    text: Rect
    image: Rect
    foot: Rect
    side_by_side: bool


def zones(size: tuple[int, int], share: float) -> Zones:
    """Header, text, picture and foot for a page of `size`; `share` is the part of the body the picture takes (its height when
    stacked, its width when the page is wide enough to put it beside the text)."""
    w, h = size
    u = min(w, h) / 1080
    m = round(72 * u)
    head_h, foot_h, gap = round(52 * u), round(44 * u), round(34 * u)
    head: Rect = (m, m, w - m, m + head_h)
    foot: Rect = (m, h - m - foot_h, w - m, h - m)
    top, bottom = head[3] + gap, foot[1] - gap
    side = w > h * 1.15
    if side:
        img_w = round((w - 2 * m - gap) * share)
        text: Rect = (m, top, w - m - img_w - gap, bottom)
        image: Rect = (w - m - img_w, top, w - m, bottom)
    else:
        img_h = round((bottom - top - gap) * share)
        text = (m, top, w - m, bottom - img_h - gap)
        image = (m, bottom - img_h, w - m, bottom)
    return Zones((w, h), u, m, head, text, image, foot, side)


@dataclass
class PageBlock:
    title: list[Line]
    points: list[list[Line]]
    title_font: Any
    body_font: Any
    title_lh: int
    body_lh: int
    gap: int
    gap_point: int
    height: int
    scale: float


def _block(page: dict[str, Any], cover: bool, width: int, unit: float, scale: float) -> PageBlock:
    base_title = (88 if cover else 62) * unit * scale
    base_body = (38 if cover else 40) * unit * scale
    tf, bf = _font(DISPLAY, base_title), _font(BODY, base_body)
    title = wrap(page["title"], tf, width) if page["title"] else []
    points = [wrap(p, bf, width) for p in page["points"]]
    title_lh, body_lh = round(tf.size * 1.14), round(bf.size * 1.4)
    gap, gap_point = round(28 * unit * scale), round(16 * unit * scale)
    height = len(title) * title_lh
    if points:
        height += (gap if title else 0) + sum(len(p) * body_lh for p in points) + gap_point * (len(points) - 1)
    return PageBlock(title, points, tf, bf, title_lh, body_lh, gap, gap_point, height, scale)


def _source_lines(source: str, stream: str, width: int) -> tuple[list[Line], Any]:
    """The closing page's source line: the smallest of three sizes that takes four lines or fewer, else an error (never cut)."""
    label = "Sumber: " if stream != "linkedin" else "Source: "
    lines: list[Line] = []
    font = _font(BODY, 22)
    for sz in (24, 22, 20):
        font = _font(BODY, sz)
        lines = wrap(label + strip_emphasis(source.strip()), font, width)
        if len(lines) <= 4:
            return lines, font
    raise SlideError("the source line is too long for the closing page; shorten the Source field")


@dataclass
class Plan:
    zones: Zones
    share: float
    blocks: list[PageBlock]
    source: list[Line]
    source_font: Any


def _fit_all(items: list[dict[str, Any]], size: tuple[int, int], share: float, stream: str, source: str,
             scales: tuple[float, ...]) -> Plan | int:
    """The plan when every page's words fit the text zone at the picture share `share`, each page at the largest of `scales`
    that fits it; else the index of the first page that does not."""
    z = zones(size, share)
    width = z.text[2] - z.text[0]
    src_lines, src_font = _source_lines(source, stream, width) if source.strip() else ([], _font(BODY, 22))
    src_h = (len(src_lines) * round(src_font.size * 1.35) + round(24 * z.unit)) if src_lines else 0
    last = len(items) - 1
    blocks: list[PageBlock] = []
    for i, page in enumerate(items):
        room = (z.text[3] - z.text[1]) - (src_h if i == last else 0)
        found = next((b for b in (_block(page, i == 0, width, z.unit, s) for s in scales) if b.height <= room), None)
        if found is None:
            return i
        blocks.append(found)
    return Plan(z, share, blocks, src_lines, src_font)


def plan(items: list[dict[str, Any]], size: tuple[int, int], stream: str = "regulab", source: str = "") -> Plan:
    """Fit every page's words. The words come first and the picture takes what is left: the picture's share is chosen ONCE for
    the whole set (so the pages line up as a carousel) and is the largest one at which every page's text fits at full type
    size. Only when the picture is at its floor does the type shrink, page by page, down to MIN_SCALE. A page that still does
    not fit fails with its number, it is never cut."""
    check(items, size)
    for share in IMAGE_SHARES:
        got = _fit_all(items, size, share, stream, source, (1.0,))
        if isinstance(got, Plan):
            return got
    got = _fit_all(items, size, IMAGE_SHARES[-1], stream, source, SCALES)
    if isinstance(got, Plan):
        return got
    raise SlideError(f"page {got + 1}: too long to fit even at the smallest type size; shorten it or split it into two pages")


# --- drawing -----------------------------------------------------------------------------------

def _rounded_paste(canvas: Image.Image, art: Image.Image, rect: Rect, radius: int) -> None:
    mask = Image.new("L", art.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, art.width - 1, art.height - 1], radius=radius, fill=255)
    canvas.paste(art, (rect[0], rect[1]), mask)


def focus_crop(photo: Image.Image, size: tuple[int, int], focus: float, zoom: float = 1.0) -> Image.Image:
    """Cover-fit `photo` into `size`, the crop window slid sideways by `focus` (0 = left edge, 1 = right edge). A set that shares
    one background uses this so each page shows another part of it and the pages do not repeat each other. `zoom` above 1 shows
    the picture larger than the window, which is what gives the window room to slide: a photo that already matches the
    window's shape has none at zoom 1."""
    w, h = size
    src = photo.convert("RGB")
    ratio = max(w / src.width, h / src.height) * max(1.0, zoom)
    src = src.resize((max(w, round(src.width * ratio)), max(h, round(src.height * ratio))), Image.LANCZOS)
    left = round((src.width - w) * min(1.0, max(0.0, focus)))
    top = (src.height - h) // 2
    return src.crop((left, top, left + w, top + h))


def illustration(size: tuple[int, int], index: int, total: int) -> Image.Image:
    """An original abstract drawing for a page that has no picture: shapes in the page's own three colours, placed by the page's
    number so the set reads as one family. It shows nothing real (no person, product, logo or object) and is not a stock asset."""
    w, h = size
    rnd = random.Random(1009 * (index + 1) + 31 * total)
    img = Image.new("RGB", size, PANEL)
    d = ImageDraw.Draw(img)
    big = round(min(w, h) * (0.62 + 0.08 * rnd.random()))
    cx = round(w * (0.28 + 0.44 * (index / max(1, total - 1)))) if total > 1 else w // 2
    cy = round(h * (0.42 + 0.16 * rnd.random()))
    d.ellipse([cx - big // 2, cy - big // 2, cx + big // 2, cy + big // 2], fill=INK)
    ring = round(big * 0.62)
    d.ellipse([cx - ring // 2, cy - ring // 2, cx + ring // 2, cy + ring // 2], fill=ACCENT)
    # a quarter-disc from the nearest corner and two bars, all clipped by the panel
    corner = rnd.choice([(0, 0), (w, 0), (0, h), (w, h)])
    r = round(min(w, h) * 0.46)
    d.pieslice([corner[0] - r, corner[1] - r, corner[0] + r, corner[1] + r], 0, 360, fill=PAPER)
    bar = max(6, round(min(w, h) * 0.035))
    for k in range(2):
        y = round(h * (0.70 + 0.11 * k) + rnd.random() * h * 0.03)
        x0 = round(w * (0.08 + 0.2 * rnd.random()))
        d.rectangle([x0, y, x0 + round(w * (0.34 + 0.2 * rnd.random())), y + bar], fill=INK if k == 0 else PAPER)
    return img


def _picture(data: bytes | None, size: tuple[int, int], index: int, total: int, focus: float,
             zoom: float = 1.0) -> Image.Image:
    if not data:
        return illustration(size, index, total)
    try:
        from .images import open_upright
        return focus_crop(open_upright(data), size, focus, zoom)
    except Exception as exc:  # noqa: BLE001 - a bad picture is reported, never drawn half
        raise SlideError(f"the picture could not be opened ({type(exc).__name__})") from exc


def _nodes(d: ImageDraw.ImageDraw, rect: Rect, index: int, total: int, unit: float) -> None:
    """The thread: nodes joined by a line, the current page filled. Position is told by shape, not by colour."""
    r = max(7, round(10 * unit))
    gap = round(54 * unit)
    cy = (rect[1] + rect[3]) // 2
    xs = [rect[0] + r + i * gap for i in range(total)]
    d.line([xs[0], cy, xs[-1], cy], fill=MUTED, width=max(2, round(3 * unit)))
    for i, x in enumerate(xs):
        if i == index:
            d.ellipse([x - r, cy - r, x + r, cy + r], fill=INK)
        else:
            d.ellipse([x - r, cy - r, x + r, cy + r], fill=PAPER, outline=MUTED, width=max(2, round(3 * unit)))


def render_page(page: dict[str, Any], index: int, total: int, p: Plan, *, eyebrow: str, website: str, stream: str,
                photo: bytes | None, focus: float, zoom: float = 1.0) -> Image.Image:
    z = p.zones
    canvas = Image.new("RGB", z.size, PAPER)
    d = ImageDraw.Draw(canvas)
    small = _font(BODY_BOLD, round(24 * z.unit))

    counter = f"{index + 1}/{total}"
    cw, ch = round(small.getlength(counter) + 36 * z.unit), z.head[3] - z.head[1]
    d.rounded_rectangle([z.head[2] - cw, z.head[1], z.head[2], z.head[1] + ch], radius=round(10 * z.unit), fill=INK)
    d.text((z.head[2] - cw + (cw - small.getlength(counter)) / 2, z.head[1] + (ch - small.size) / 2 - 2), counter,
           font=small, fill=PAPER)
    if eyebrow.strip():
        d.text((z.head[0], z.head[1] + (ch - small.size) / 2 - 2),
               slides.eyebrow_text(eyebrow, small, z.head[2] - z.head[0] - cw - 40), font=small, fill=ACCENT_TEXT)

    b = p.blocks[index]
    y = draw_lines(d, b.title, z.text[0], z.text[1], b.title_font, b.title_lh, INK, ACCENT_TEXT)
    if b.points and b.title:
        y += b.gap
    for i, pts in enumerate(b.points):
        y = draw_lines(d, pts, z.text[0], y, b.body_font, b.body_lh, INK if index else MUTED, ACCENT_TEXT)
        if i < len(b.points) - 1:
            y += b.gap_point
    if p.source and index == total - 1:
        lh = round(p.source_font.size * 1.35)
        sy = z.text[3] - len(p.source) * lh
        d.line([z.text[0], sy - round(12 * z.unit), z.text[0] + round(80 * z.unit), sy - round(12 * z.unit)], fill=EDGE, width=2)
        draw_lines(d, p.source, z.text[0], sy, p.source_font, lh, MUTED, MUTED)

    ir = z.image
    size = (ir[2] - ir[0], ir[3] - ir[1])
    radius = round(28 * z.unit)
    _rounded_paste(canvas, _picture(photo, size, index, total, focus, zoom), ir, radius)
    d.rounded_rectangle([ir[0], ir[1], ir[2] - 1, ir[3] - 1], radius=radius, outline=EDGE, width=2)

    _nodes(d, (z.foot[0], z.foot[1], z.foot[0] + round(54 * z.unit) * total, z.foot[3]), index, total, z.unit)
    if stream != "linkedin" and website.strip():
        foot = _font(BODY_BOLD, round(24 * z.unit))
        d.text((z.foot[2] - foot.getlength(website.strip()), (z.foot[1] + z.foot[3]) / 2 - foot.size / 2),
               website.strip(), font=foot, fill=MUTED)
    return canvas


def render(items: Any, *, stream: str = "regulab", eyebrow: str = "", source: str = "", website: str = "",
           photos: list[bytes | None] | None = None, size: tuple[int, int] = (1080, 1350), quality: int = 90) -> list[bytes]:
    """JPEG bytes, one per page, in order. `photos` holds one picture per page (None = the original drawing). Raises SlideError
    naming the page that cannot be drawn, before any page is drawn when the problem is in the words or the size."""
    words = slides.normalise(items)
    if stream == "linkedin":
        website = ""                                       # rule: no ws.regulab identity on LinkedIn
    p = plan(words, size, stream, source)
    pics = list(photos or [])[:len(words)]
    pics += [None] * (len(words) - len(pics))
    shared = len({x for x in pics if x}) == 1 and sum(1 for x in pics if x) > 1
    out = []
    for i, page in enumerate(words):
        try:
            img = render_page(page, i, len(words), p, eyebrow=eyebrow, website=website, stream=stream, photo=pics[i],
                              focus=(i / (len(words) - 1)) if shared else 0.5, zoom=SHARED_ZOOM if shared else 1.0)
        except SlideError as exc:
            raise SlideError(f"page {i + 1}: {exc}") from exc
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
        out.append(buf.getvalue())
    return out
