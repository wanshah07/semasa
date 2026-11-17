"""A dialogue (comic) poster: two people talk a regulatory question through in four panels (Wan, 16 Nov 2026: "make poster
dialogue like this using gemini or chatgpt").

The picture maker (ChatGPT or Gemini) draws the people. Who writes the WORDS was the open question, and Wan asked to see both
before choosing ("Try both and compare"):

  full  the picture maker draws everything, the words inside the speech bubbles included. It looks most natural, but an image
        model can misspell a word or change a number, and on a regulatory comic a wrong clause number is a wrong fact.
  art   the picture maker draws the four panels with NO words and NO bubbles, leaving the top of every panel empty; Semasa
        then draws the bubbles and prints the words itself (`letter`), so every word and number is exactly the script's.

The 16 Nov comparison: both makers spelled every bubble exactly in `full`, and it reads more naturally. So a comic is drawn
`full` first and the words are then read back and compared with the script (comic_job.py); `art` is what it falls back to.

A STYLE is remembered as words (rules/comic.json, comic_library.py): the same description goes into both prompts verbatim
every time, so another picture maker draws the same look. A SERIES fixes the two people: their appearance is the same words
in every episode.

Both come out in the same frame (`frame`): the series and episode, the title, the square comic and the source, all printed
by Semasa. This module draws and prints only. It writes no post and reads no database.
"""

from __future__ import annotations

import io
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFont

from . import comic_library
from .slides import BODY, BODY_BOLD, DISPLAY, _font, brand_mark, hard_split

LIMITS = comic_library.LIMITS
PANELS = int(LIMITS["panels"])  # a 2 by 2 page
MAX_LINES = int(LIMITS["lines"])   # speech bubbles in one panel
MAX_CHARS = int(LIMITS["chars"])   # one bubble's words: past this the lettering is too small to read on a phone
MAX_TITLE = int(LIMITS["title"])
MAX_SOURCE = int(LIMITS["source"])
SIDE = 1080                     # the comic itself is square; the poster around it is 4:5
POSTER = (1080, 1350)
TITLE_H, FOOT_H = 190, 80
ZONE = 0.44                     # the top part of a panel that the picture maker is asked to leave empty, for the bubbles
FONT_MAX, FONT_MIN = 30, 19
INK, PAPER, MUTED = (17, 17, 17), (255, 255, 255), (90, 90, 90)
SPEAKERS = ("A", "B")           # A stands on the left of every panel and B on the right, so a bubble's tail knows where to point
LANGUAGES = {"bm": "Malay", "en": "English"}

DEFAULT_STYLE: dict[str, Any] = next(s for s in comic_library.RULES["styles"]
                                     if s["id"] == comic_library.RULES["default_style"])
STYLE = DEFAULT_STYLE["prompt"]  # the 16 Nov look, as words


class ComicError(ValueError):
    """A script that cannot be drawn as written. The message is for Wan."""


def check(script: dict[str, Any]) -> dict[str, Any]:
    """The script, or ComicError naming what is wrong. Shape: {title, source, setting, cast: {A, B}, panels: [{scene, lines:
    [{who, text}]}]} with exactly four panels and one or two lines in each."""
    panels = script.get("panels")
    if not isinstance(panels, list) or len(panels) != PANELS:
        raise ComicError(f"a comic page has exactly {PANELS} panels")
    cast = script.get("cast") or {}
    if any(not str(cast.get(s) or "").strip() for s in SPEAKERS):
        raise ComicError("the cast needs a description of both people, A and B")
    for n, panel in enumerate(panels, 1):
        lines = panel.get("lines") if isinstance(panel, dict) else None
        if not isinstance(lines, list) or not 1 <= len(lines) <= MAX_LINES:
            raise ComicError(f"panel {n} needs one or two speech bubbles")
        for line in lines:
            who, text = str(line.get("who") or ""), " ".join(str(line.get("text") or "").split())
            if who not in SPEAKERS:
                raise ComicError(f"panel {n}: a bubble's speaker is A or B")
            if not text:
                raise ComicError(f"panel {n}: a bubble has no words")
            if len(text) > MAX_CHARS:
                raise ComicError(f"panel {n}: a bubble has {len(text)} characters, more than the {MAX_CHARS} that stay readable")
        if len({str(line.get("who")) for line in lines}) != len(lines):
            raise ComicError(f"panel {n}: each person speaks once in a panel")
    title, source = _flat(script.get("title")), _flat(script.get("source"))
    if len(title) > MAX_TITLE:
        raise ComicError(f"the title has {len(title)} characters, more than the {MAX_TITLE} that fit above the comic")
    if len(source) > MAX_SOURCE:
        raise ComicError(f"the source has {len(source)} characters, more than the {MAX_SOURCE} that fit under the comic")
    return script


def _flat(value: Any) -> str:
    return " ".join(str(value or "").split())


def _words(line: dict[str, Any]) -> str:
    return " ".join(str(line.get("text") or "").split())


def _scenes(script: dict[str, Any], with_words: bool) -> str:
    out = []
    for n, panel in enumerate(script["panels"], 1):
        where = ("top left", "top right", "bottom left", "bottom right")[n - 1]
        text = f"Panel {n} ({where}): {str(panel.get('scene') or '').strip()}"
        if with_words:
            said = " ".join(f'{line["who"]} says, in a speech bubble: "{_words(line)}"' for line in panel["lines"])
            text += f" {said}"
        else:
            who = " and ".join(str(line["who"]) for line in panel["lines"])
            text += f" ({who} is speaking: mouth open, gesturing.)" if len(panel["lines"]) == 1 else " (Both are talking.)"
        out.append(text)
    return "\n".join(out)


def _style(style: dict[str, Any] | None) -> dict[str, Any]:
    return style if style and str(style.get("prompt") or "").strip() else DEFAULT_STYLE


def _base(script: dict[str, Any], style: dict[str, Any] | None = None) -> str:
    cast = script["cast"]
    return ("A square comic page of four equal panels in a 2 by 2 grid, separated by thin white gutters. The comic fills the "
            "whole picture from edge to edge: no outer border, no margin and no frame around the page.\n"
            f"ART STYLE. Draw every part of the page in exactly this style, and in no other:\n{_style(style)['prompt']}\n"
            "The same two characters in all four panels, looking the same every time: the same face, hair, clothes and "
            "colours.\n"
            f"Setting: {str(script.get('setting') or 'an everyday Malaysian place').strip()}\n"
            f"Character A, always on the LEFT side of a panel: {str(cast['A']).strip()}\n"
            f"Character B, always on the RIGHT side of a panel: {str(cast['B']).strip()}\n")


def prompt_full(script: dict[str, Any], style: dict[str, Any] | None = None) -> str:
    """The picture maker draws the words too. Every bubble's text is given exactly, with the instruction to copy it letter
    for letter: that is all a prompt can do, so the picture is read back afterwards (comic_job.py)."""
    check(script)
    lettering = str(_style(style).get("lettering") or "").strip()
    language = LANGUAGES.get(str(script.get("lang") or "bm"), "Malay")
    return (_base(script, style) + _scenes(script, True) + "\n"
            "Each line is in a speech bubble with a tail pointing to its speaker. "
            + (f"{lettering} " if lettering else "White speech bubbles with a black outline, clear upright comic lettering. ")
            + f"The lettering is large enough to read on a phone. The words are in {language}. Copy every bubble's text "
            "EXACTLY as written between the quotation marks, letter for letter, including "
            "numbers, brackets and punctuation: do not translate, shorten, correct or add words. "
            "No other text anywhere in the picture: no title, no caption, no sound effects, no signs, no brand names.")


def prompt_art(script: dict[str, Any], style: dict[str, Any] | None = None) -> str:
    """The picture maker draws the people only. The words are printed afterwards by `letter`, in the empty top of each panel."""
    check(script)
    return (_base(script, style) + _scenes(script, False) + "\n"
            f"IMPORTANT: no text of any kind anywhere, and NO speech bubbles: no letters, numbers, signs, labels or brand names. "
            f"In EVERY panel keep the top {round(ZONE * 100)} percent completely empty: a plain, flat, light-coloured wall or "
            "sky with nothing on it. The characters' heads stay below that empty area, in the lower part of the panel.")


# ----------------------------------------------------------------------------------------- the picture maker's stray border

TRIM_BAND = 0.06        # how far in from an edge a stray border may reach
FRAME_DARK = 0.85       # a row this dark from end to end is a panel's outline, not part of a drawing
_DARK = 70


def _profile(mask: Image.Image, side: str, band: int) -> list[float]:
    """How much of each of the first `band` rows (or columns) from one side is set in `mask`, 0 to 1, the edge first."""
    w, h = mask.size
    if side in ("top", "bottom"):
        strip = mask.crop((0, 0, w, band) if side == "top" else (0, h - band, w, h)).resize((1, band), Image.BOX)
        vals = [strip.getpixel((0, i)) / 255 for i in range(band)]
    else:
        strip = mask.crop((0, 0, band, h) if side == "left" else (w - band, 0, w, h)).resize((band, 1), Image.BOX)
        vals = [strip.getpixel((i, 0)) / 255 for i in range(band)]
    return vals if side in ("top", "left") else vals[::-1]


def _edge_cut(dark: list[float], plain: list[float]) -> int:
    """How many rows to take off one side. The comic begins at its outermost panel outline: everything outside that line is
    the picture maker's own border (the speckled coloured edge of the 16 Nov ChatGPT sample, Gemini's grey margin). A thin
    line just outside the real outline (a doubled line) goes too. With no outline in reach (a style without outlines), only a
    plain margin of one flat colour is taken off."""
    runs: list[tuple[int, int]] = []
    for i, v in enumerate(dark):
        if v >= FRAME_DARK:
            if runs and i == runs[-1][1] + 1:
                runs[-1] = (runs[-1][0], i)
            else:
                runs.append((i, i))
    if runs:
        first = runs[0]
        for nxt in runs[1:]:
            if nxt[0] - first[1] <= 6 and nxt[1] - nxt[0] >= first[1] - first[0]:
                first = nxt                     # the thicker line a few pixels further in is the panel's own outline
        return first[0]
    cut = 0
    while cut < len(plain) and plain[cut] >= 0.97:
        cut += 1
    return cut if cut < len(plain) else 0       # plain all the way in is a plain picture, not a margin


def trim(picture: Image.Image | bytes) -> Image.Image:
    """The comic without the picture maker's stray border, as an RGB picture. At most TRIM_BAND of each side is ever taken,
    so a picture with nothing to trim comes back whole and a wrong guess costs a sliver, never a face or a word."""
    img = Image.open(io.BytesIO(picture)) if isinstance(picture, bytes) else picture
    img = img.convert("RGB")
    w, h = img.size
    if min(w, h) < 200:
        return img
    grey = img.convert("L")
    dark = grey.point(lambda p: 255 if p < _DARK else 0)
    corner = Image.new("RGB", img.size, img.getpixel((1, 1)))
    plain = ImageChops.difference(img, corner).convert("L").point(lambda p: 255 if p <= 18 else 0)
    cuts = {}
    for side in ("top", "bottom", "left", "right"):
        band = max(4, round((h if side in ("top", "bottom") else w) * TRIM_BAND))
        cuts[side] = _edge_cut(_profile(dark, side, band), _profile(plain, side, band))
    if any(cuts.values()):
        img = img.crop((cuts["left"], cuts["top"], w - cuts["right"], h - cuts["bottom"]))
        dark = dark.crop((cuts["left"], cuts["top"], w - cuts["right"], h - cuts["bottom"]))
    return _clean_gutters(img, dark)


def _gutter(dark: list[float]) -> tuple[int, int] | None:
    """The gap between two panel outlines that face each other across the middle of the page, as (first, last) offsets
    into `dark`, or None when the middle does not show two outlines with a narrow gap between them."""
    runs: list[list[int]] = []
    for i, v in enumerate(dark):
        if v >= FRAME_DARK:
            if runs and i == runs[-1][1] + 1:
                runs[-1][1] = i
            else:
                runs.append([i, i])
    mid = len(dark) / 2
    for a, b in zip(runs, runs[1:], strict=False):
        if a[1] < mid <= b[0] + (b[1] - b[0]) and 2 <= b[0] - a[1] - 1 <= len(dark) * 0.6:
            return a[1] + 1, b[0] - 1
    return None


def _clean_gutters(img: Image.Image, dark: Image.Image) -> Image.Image:
    """The gutter between the panels painted plain white. The 16 Nov ChatGPT picture carried the same coloured speckle in
    its gutters as on its edge; only a gap that sits between two full outlines is touched, so no drawing is painted over."""
    w, h = img.size
    span_x, span_y = max(8, round(w * 0.06)), max(8, round(h * 0.06))
    x0, y0 = w // 2 - span_x, h // 2 - span_y
    cols = dark.crop((x0, 0, x0 + 2 * span_x, h)).resize((2 * span_x, 1), Image.BOX)
    rows = dark.crop((0, y0, w, y0 + 2 * span_y)).resize((1, 2 * span_y), Image.BOX)
    gx = _gutter([cols.getpixel((i, 0)) / 255 for i in range(2 * span_x)])
    gy = _gutter([rows.getpixel((0, i)) / 255 for i in range(2 * span_y)])
    if not gx and not gy:
        return img
    img = img.copy()
    d = ImageDraw.Draw(img)
    if gx:
        d.rectangle([x0 + gx[0], 0, x0 + gx[1], h - 1], fill=PAPER)
    if gy:
        d.rectangle([0, y0 + gy[0], w - 1, y0 + gy[1]], fill=PAPER)
    return img


# ---------------------------------------------------------------------------------------------------- lettering (Semasa's)

def _wrap(text: str, font: ImageFont.FreeTypeFont, width: float) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if cur and font.getlength(trial) > width:
            lines.append(cur)
            cur = word
        else:
            cur = trial
    return lines + ([cur] if cur else [])


def bubbles(script: dict[str, Any], side: int = SIDE) -> list[dict[str, Any]]:
    """Where every bubble goes on a square comic of `side` pixels: [{panel, who, text, lines, size, box: (x0, y0, x1, y1),
    tail: [(x, y) * 3]}]. One size of lettering for the whole page (the largest that fits every panel's empty top), so the
    page reads as one hand. A's bubble hangs from the left and B's from the right, the second one a step lower."""
    check(script)
    half = side // 2
    pad, gap, edge = round(side * 0.013), round(side * 0.011), round(side * 0.017)
    zone_h = round(half * ZONE)
    for size in range(FONT_MAX, FONT_MIN - 1, -1):
        font, lh = _font(BODY_BOLD, size * side / SIDE), round(size * side / SIDE * 1.24)
        out, fits = [], True
        for n, panel in enumerate(script["panels"]):
            px, py = (n % 2) * half, (n // 2) * half
            two = len(panel["lines"]) == 2
            max_w = round(half * (0.70 if two else 0.84)) - 2 * pad
            y = py + edge
            for line in panel["lines"]:
                text = _words(line)
                rows = _wrap(text, font, max_w)
                if any(font.getlength(r) > max_w for r in rows):
                    fits = False
                w = round(max(font.getlength(r) for r in rows)) + 2 * pad
                h = len(rows) * lh + 2 * pad
                left = line["who"] == "A"
                x0 = px + edge if left else px + half - edge - w
                box = (x0, y, x0 + w, y + h)
                tx = x0 + round(w * (0.28 if left else 0.72))
                tip = (tx + round(half * (-0.03 if left else 0.03)), y + h + round(half * 0.07))
                out.append({"panel": n + 1, "who": line["who"], "text": text, "lines": rows, "size": size, "box": box,
                            "tail": [(tx - round(side * 0.012), y + h - 2), (tx + round(side * 0.012), y + h - 2), tip]})
                y += h + gap
            if y - gap > py + zone_h:
                fits = False
        if fits:
            return out
    raise ComicError("the words do not fit above the people at a readable size: shorten the longest bubble")


def letter(art: Image.Image | bytes, script: dict[str, Any], side: int = SIDE) -> Image.Image:
    """The wordless comic with Semasa's own bubbles and words on it, as a square picture."""
    img = Image.open(io.BytesIO(art)) if isinstance(art, bytes) else art
    img = img.convert("RGB").resize((side, side), Image.LANCZOS)
    d = ImageDraw.Draw(img)
    stroke = max(2, round(side * 0.003))
    for b in bubbles(script, side):
        font = _font(BODY_BOLD, b["size"] * side / SIDE)
        lh, pad = round(b["size"] * side / SIDE * 1.24), round(side * 0.013)
        d.polygon(b["tail"], fill=PAPER, outline=INK)
        d.line([b["tail"][0], b["tail"][2], b["tail"][1]], fill=INK, width=stroke, joint="curve")
        d.rounded_rectangle(b["box"], radius=round(side * 0.02), fill=PAPER, outline=INK, width=stroke)
        d.line([(b["tail"][0][0] + stroke, b["tail"][0][1]), (b["tail"][1][0] - stroke, b["tail"][1][1])], fill=PAPER,
               width=stroke + 2)                                          # open the bubble's edge where the tail joins it
        x0, y0, x1, _ = b["box"]
        for i, row in enumerate(b["lines"]):
            w = font.getlength(row)
            d.text((x0 + (x1 - x0 - w) / 2, y0 + pad + i * lh), row, font=font, fill=INK)
    return img


# ------------------------------------------------------------------------------------------------------------ the frame

PAD = 60                 # the frame's side margin
HEAD_ROW = 44            # the row above the title: the series and episode on the left, the ws.regulab logo on the right
LOGO_H = 34


def _rows(text: str, font: ImageFont.FreeTypeFont, width: float) -> list[str]:
    """`text` wrapped to `width`. A single token wider than the line (a long reference with no space) is split by character,
    so no row is ever wider than the line."""
    rows, cur = [], ""
    for word in text.split():
        for piece in hard_split(word, font, width):
            trial = f"{cur} {piece}".strip()
            if cur and font.getlength(trial) > width:
                rows.append(cur)
                cur = piece
            else:
                cur = trial
    return rows + ([cur] if cur else [])


def fit_text(text: str, face: Any, sizes: Any, width: float, height: float, max_rows: int,
             leading: float = 1.14) -> tuple[ImageFont.FreeTypeFont, list[str], int] | None:
    """(font, rows, line height) at the largest of `sizes` where the text takes at most `max_rows` rows, every row is within
    `width` and the block is within `height`; None when no size does. Nothing is cut and nothing is shortened."""
    for size in sizes:
        font = _font(face, size)
        rows = _rows(text, font, width)
        lh = round(size * leading)
        if len(rows) <= max_rows and len(rows) * lh <= height and all(font.getlength(r) <= width for r in rows):
            return font, rows, lh
    return None


def layout(script: dict[str, Any], *, episode: str = "", stream: str | None = None,
           website: str = "") -> dict[str, Any]:
    """Where every word of the frame goes: {episode, title, source, website, logo}, each {font, rows, lh, x, y, w, h, align}
    or None. Raises ComicError when something cannot fit at a readable size, naming it. The title, the episode line and the
    source are fitted to their own areas, so none of them can run off the poster or into another.

    `stream`: "regulab" carries the ws.regulab logo (top right) and the website (foot, right), as its cards do; "linkedin"
    carries no brand identity at all; None is the bare frame of the 16 Nov sample."""
    w = POSTER[0]
    brand = stream == "regulab"
    logo = brand_mark(LOGO_H, False) if brand else None
    episode, title, source = _flat(episode), _flat(script.get("title")), _flat(script.get("source"))
    website = _flat(website) if brand else ""
    out: dict[str, Any] = {"episode": None, "title": None, "source": None, "website": None, "logo": None}
    top = 0
    if episode or logo:
        top = HEAD_ROW + 14
        if logo:
            out["logo"] = {"image": logo, "x": w - PAD - logo.width, "y": 16 + (HEAD_ROW - logo.height) // 2,
                           "w": logo.width, "h": logo.height}
        if episode:
            room = w - 2 * PAD - ((logo.width + 28) if logo else 0)
            got = fit_text(episode, BODY_BOLD, range(24, 11, -1), room, HEAD_ROW, 1, 1.2)
            if not got:
                raise ComicError("the series name is too long for the poster: shorten it")
            font, rows, lh = got
            out["episode"] = {"font": font, "rows": rows, "lh": lh, "x": PAD, "y": 16 + (HEAD_ROW - lh) // 2,
                              "w": room, "h": lh, "align": "left"}
    if title:
        area_y, area_h = top + 4, TITLE_H - top - 12
        got = (fit_text(title, DISPLAY, range(64 if not top else 54, 33, -2), w - 2 * PAD, area_h, 2)
               or fit_text(title, DISPLAY, range(34, 21, -1), w - 2 * PAD, area_h, 3))
        if not got:
            raise ComicError("the title is too long for the poster: shorten it")
        font, rows, lh = got
        out["title"] = {"font": font, "rows": rows, "lh": lh, "x": PAD, "y": area_y + (area_h - len(rows) * lh) // 2,
                        "w": w - 2 * PAD, "h": len(rows) * lh, "align": "centre"}
    foot_y = TITLE_H + SIDE
    site_w = 0
    if website:
        got = fit_text(website, BODY_BOLD, range(22, 11, -1), (w - 2 * PAD) * 0.45, FOOT_H - 16, 1, 1.2)
        if got:                                     # a website too long to print in one row is left off, never cut
            font, rows, lh = got
            site_w = round(font.getlength(rows[0]))
            out["website"] = {"font": font, "rows": rows, "lh": lh, "x": w - PAD - site_w, "y": foot_y + (FOOT_H - lh) // 2,
                              "w": site_w, "h": lh, "align": "left"}
    if source:
        room = w - 2 * PAD - ((site_w + 36) if site_w else 0)
        got = (fit_text(source, BODY, range(24, 16, -1), room, FOOT_H - 16, 2, 1.25)
               or fit_text(source, BODY, range(17, 12, -1), room, FOOT_H - 12, 3, 1.25))
        if not got:
            raise ComicError("the source is too long for the poster: shorten it")
        font, rows, lh = got
        out["source"] = {"font": font, "rows": rows, "lh": lh, "x": PAD, "y": foot_y + (FOOT_H - len(rows) * lh) // 2,
                         "w": room, "h": len(rows) * lh, "align": "left" if site_w else "centre"}
    return out


def frame(comic: Image.Image | bytes, script: dict[str, Any], *, episode: str = "", stream: str | None = None,
          website: str = "") -> bytes:
    """The 4:5 poster as JPEG bytes: the series and episode, the title, the square comic, the source. All of it is printed
    by Semasa in both modes, so two posters differ only in who wrote the bubbles. See `layout` for `stream`."""
    if isinstance(comic, bytes):
        comic = Image.open(io.BytesIO(comic)).convert("RGB")
    plan = layout(script, episode=episode, stream=stream, website=website)
    page = Image.new("RGB", POSTER, PAPER)
    d = ImageDraw.Draw(page)
    page.paste(comic.resize((SIDE, SIDE), Image.LANCZOS), (0, TITLE_H))
    if plan["logo"]:
        page.paste(plan["logo"]["image"], (plan["logo"]["x"], plan["logo"]["y"]), plan["logo"]["image"])
    for key, fill in (("episode", MUTED), ("title", INK), ("source", MUTED), ("website", MUTED)):
        box = plan[key]
        if not box:
            continue
        for i, row in enumerate(box["rows"]):
            x = box["x"] + ((box["w"] - box["font"].getlength(row)) / 2 if box["align"] == "centre" else 0)
            d.text((x, box["y"] + i * box["lh"]), row, font=box["font"], fill=fill)
    buf = io.BytesIO()
    page.save(buf, "JPEG", quality=90)
    return buf.getvalue()
