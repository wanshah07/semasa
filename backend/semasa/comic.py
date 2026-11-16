"""A dialogue (comic) poster: two people talk a regulatory question through in four panels (Wan, 16 Nov 2026: "make poster
dialogue like this using gemini or chatgpt").

The picture maker (ChatGPT or Gemini) draws the people. Who writes the WORDS is the open question, and Wan asked to see both
before choosing ("Try both and compare"):

  full  the picture maker draws everything, the words inside the speech bubbles included. It looks most natural, but an image
        model can misspell a word or change a number, and on a regulatory comic a wrong clause number is a wrong fact.
  art   the picture maker draws the four panels with NO words and NO bubbles, leaving the top of every panel empty; Semasa
        then draws the bubbles and prints the words itself (`letter`), so every word and number is exactly the script's.

Both come out in the same frame (`frame`): the title above the comic and the source at the foot, both printed by Semasa.
This module draws and prints only. It writes no post and reads no database; comic_sample.py is the hand-run comparison.
"""

from __future__ import annotations

import io
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from .slides import BODY, BODY_BOLD, DISPLAY, _font

PANELS = 4                      # a 2 by 2 page
MAX_LINES = 2                   # speech bubbles in one panel
MAX_CHARS = 110                 # one bubble's words: past this the lettering is too small to read on a phone
SIDE = 1080                     # the comic itself is square; the poster around it is 4:5
POSTER = (1080, 1350)
TITLE_H, FOOT_H = 190, 80
ZONE = 0.44                     # the top part of a panel that the picture maker is asked to leave empty, for the bubbles
FONT_MAX, FONT_MIN = 30, 19
INK, PAPER, MUTED = (17, 17, 17), (255, 255, 255), (90, 90, 90)
SPEAKERS = ("A", "B")           # A stands on the left of every panel and B on the right, so a bubble's tail knows where to point

STYLE = ("Clean modern comic illustration, flat colours with soft shading, bold consistent black outlines, warm friendly "
         "palette, Malaysian setting. The same two characters, looking the same, in all four panels.")


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
    return script


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


def _base(script: dict[str, Any]) -> str:
    cast = script["cast"]
    return (f"A square comic page of four equal panels in a 2 by 2 grid, separated by thin white gutters.\n{STYLE}\n"
            f"Setting: {str(script.get('setting') or 'an everyday Malaysian place').strip()}\n"
            f"Character A, always on the LEFT side of a panel: {str(cast['A']).strip()}\n"
            f"Character B, always on the RIGHT side of a panel: {str(cast['B']).strip()}\n")


def prompt_full(script: dict[str, Any]) -> str:
    """The picture maker draws the words too. Every bubble's text is given exactly, with the instruction to copy it letter
    for letter: that is all a prompt can do, and the sample shows how well it holds."""
    check(script)
    return (_base(script) + _scenes(script, True) + "\n"
            "Each line is in a white speech bubble with a black outline and a tail pointing to its speaker. The words are in "
            "Malay. Copy every bubble's text EXACTLY as written between the quotation marks, letter for letter, including "
            "numbers, brackets and punctuation: do not translate, shorten, correct or add words. Clear, large, upright comic "
            "lettering. No other text anywhere in the picture: no title, no caption, no sound effects, no signs, no brand names.")


def prompt_art(script: dict[str, Any]) -> str:
    """The picture maker draws the people only. The words are printed afterwards by `letter`, in the empty top of each panel."""
    check(script)
    return (_base(script) + _scenes(script, False) + "\n"
            f"IMPORTANT: no text of any kind anywhere, and NO speech bubbles: no letters, numbers, signs, labels or brand names. "
            f"In EVERY panel keep the top {round(ZONE * 100)} percent completely empty: a plain, flat, light-coloured wall or "
            "sky with nothing on it. The characters' heads stay below that empty area, in the lower part of the panel.")


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


def letter(art: bytes, script: dict[str, Any], side: int = SIDE) -> Image.Image:
    """The wordless comic with Semasa's own bubbles and words on it, as a square picture."""
    img = Image.open(io.BytesIO(art)).convert("RGB").resize((side, side), Image.LANCZOS)
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


def frame(comic: Image.Image | bytes, script: dict[str, Any]) -> bytes:
    """The 4:5 poster as JPEG bytes: the title, the square comic, the source. The title and the source are printed by Semasa
    in both modes, so the two samples differ only in who wrote the bubbles."""
    if isinstance(comic, bytes):
        comic = Image.open(io.BytesIO(comic)).convert("RGB")
    w, h = POSTER
    page = Image.new("RGB", POSTER, PAPER)
    d = ImageDraw.Draw(page)
    title = " ".join(str(script.get("title") or "").split())
    for size in range(64, 35, -2):
        font = _font(DISPLAY, size)
        rows = _wrap(title, font, w - 120)
        if len(rows) <= 2:
            break
    lh = round(size * 1.12)
    y = (TITLE_H - len(rows) * lh) // 2
    for row in rows[:2]:
        d.text(((w - font.getlength(row)) / 2, y), row, font=font, fill=INK)
        y += lh
    page.paste(comic.resize((SIDE, SIDE), Image.LANCZOS), (0, TITLE_H))
    source = " ".join(str(script.get("source") or "").split())
    if source:
        font = _font(BODY, 24)
        text = _wrap(source, font, w - 120)[0]
        d.text(((w - font.getlength(text)) / 2, TITLE_H + SIDE + (FOOT_H - 30) // 2), text, font=font, fill=MUTED)
    buf = io.BytesIO()
    page.save(buf, "JPEG", quality=90)
    return buf.getvalue()
