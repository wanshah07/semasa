"""A dialogue (comic) poster: two people talk a regulatory question through in four panels (Wan, 16 Nov 2026: "make poster
dialogue like this using gemini or chatgpt").

The picture maker (ChatGPT or Gemini) draws the people. Who writes the WORDS was Wan's to choose, and on 17 Nov 2026 he chose
("Follow your recommendation"): the picture maker draws them, and Semasa reads the picture back before it is used.

  full  the picture maker draws everything, the words inside the speech bubbles included. It looks most natural, but an image
        model can misspell a word or change a number, and on a regulatory comic a wrong clause number is a wrong fact.
  art   the picture maker draws the four panels with NO words and NO bubbles, leaving the top of every panel empty; Semasa
        then draws the bubbles and prints the words itself (`letter`), so every word and number is exactly the script's.

`make` is the recommendation: draw `full`, read every bubble back (`readback`, ChatGPT's own sight) and compare it with the
script letter for letter. A picture with a bubble that differs is drawn again; after `TRIES` that still differ, or with no
reader at all, the page is drawn `art` and Semasa prints the words. A picture whose words were not proven exact is never used.

Both come out in the same frame (`frame`): the title above the comic and the source at the foot, both printed by Semasa.
`write` turns Wan's idea into the script under the rules a post is judged by. This module touches no database;
comic_sample.py is the hand-run comparison and media_generator.process_comic is the job that uses it.
"""

from __future__ import annotations

import io
import json
import re
import unicodedata
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
TRIES = 2                       # drawings with the words in them that are read back before the page falls back to printing
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


# ------------------------------------------------------------------------------------------------- the script (written)

RULES = """Rules. Breaking any of them blocks the artwork:
1. No call to action of any kind ("hubungi kami", "DM", "klik link", "follow", "comment below").
2. No website, URL, handle or brand name anywhere: not in a bubble, not in the title, not in a scene. The people wear and
   hold nothing with lettering or a logo on it.
3. Never name Reddit, YouTube, TikTok, a forum or a news portal as a source.
4. No fee, duration, date, circular, clause, entry number or figure unless it is in the BRIEF. If one is not in the brief,
   write around it: never guess one, and never write a placeholder or a note in brackets.
5. No em dash. No superlatives, no promise of approval, no cure.
6. B is an unnamed consultant, A an unnamed person with the question. Neither is a real person."""

SHAPE = ('ONE comic page of exactly four panels: {"title": "a headline of at most 9 words, plain text", "source": "the '
         'regulator and instrument the words rest on, or \\"\\" when the brief names none", "setting": "one English '
         'sentence: the place, with nothing written anywhere in it", "cast": {"A": "English: who A is, clothes, what A '
         'holds", "B": "English: who B is, clothes, what B holds"}, "panels": [{"scene": "English: what the picture '
         'shows, no words in it", "lines": [{"who": "A", "text": "what A says"}]}, ...]}. Each panel has one or two lines, '
         'each person at most once per panel, each line at most {max_chars} characters of natural spoken words. Panel 1 is the '
         'question, the middle panels the answer, panel 4 the point to remember and the source in words. The spoken words '
         'are in the stream\'s language; the scenes, the cast and the setting are always English.'
         ).replace('{max_chars}', str(MAX_CHARS))

VOICES = {
    "regulab": "Write the spoken words in Malaysian Malay (never Bahasa Indonesia: boleh, ubat, syarikat, kualiti, "
               "pembungkusan), the way two Malaysians really talk, with English technical terms where people use them.",
    "linkedin": "Write the spoken words in English, the way two regulatory peers really talk. No company identity at all.",
}


def write(llm: Any, brief: str, stream: str, note: str = "") -> dict[str, Any]:
    """The script written from Wan's idea, under the rules a post is judged by, or ComicError saying why not. The writer is
    given the anti-slop prompt and every word that comes back goes through antislop.clean (a new writer of public text gets
    both, CLAUDE.md). The result is checked as a page (`check`) before it is returned."""
    from . import antislop
    if not llm or not getattr(llm, "configured", False):
        raise ComicError("the writer is off, so the comic cannot be written from the idea"
                         + (": " + llm.why_off() if llm and hasattr(llm, "why_off") else "") + ". Give the script yourself.")
    system = ("You write a four-panel dialogue comic for a regulatory social-media post. "
              f"{VOICES.get(stream, VOICES['regulab'])}\n\n{RULES}\n\nAnswer with ONE JSON object only. {SHAPE}"
              f"{antislop.prompt_block()}")
    user = f"BRIEF (Wan's idea or prompt):\n{str(brief).strip()[:4000]}"
    if note.strip():
        user += f"\n\nChanges Wan asked for on the last version: {note.strip()[:600]}"
    out = llm.chat_json(system, user, max_tokens=2500)
    if not isinstance(out, dict):
        raise ComicError("the writer did not answer (see the run log); press Retry, or give the script yourself")
    cast = out.get("cast") if isinstance(out.get("cast"), dict) else {}
    panels = []
    for panel in out.get("panels") if isinstance(out.get("panels"), list) else []:
        lines = panel.get("lines") if isinstance(panel, dict) and isinstance(panel.get("lines"), list) else []
        panels.append({"scene": " ".join(str((panel or {}).get("scene") or "").split()),
                       "lines": [{"who": str(line.get("who") or "").strip().upper(),
                                  "text": antislop.clean(" ".join(str(line.get("text") or "").split()))}
                                 for line in lines if isinstance(line, dict)]})
    script = {"title": antislop.clean(" ".join(str(out.get("title") or "").split())),
              "source": " ".join(str(out.get("source") or "").split())[:160],
              "setting": " ".join(str(out.get("setting") or "").split()),
              "cast": {k: " ".join(str(cast.get(k) or "").split()) for k in SPEAKERS}, "panels": panels}
    if not script["title"]:
        raise ComicError("the writer gave the comic no title; press Retry")
    return check(script)


def as_words(script: dict[str, Any]) -> list[dict[str, Any]]:
    """The comic's words shaped as one artwork slide, so the post rules scan them like any poster: the title, then every
    bubble in reading order. (The scenes are for the picture maker and never printed.)"""
    return [{"title": " ".join(str(script.get("title") or "").split()),
             "points": [_words(line) for panel in script["panels"] for line in panel["lines"]]}]


# ------------------------------------------------------------------------------------------------ the read-back (proof)

READ_SYSTEM = "You read lettering in pictures exactly as it is printed. Answer with one JSON object only."
READ_PROMPT = ("This comic page has four panels in a 2 by 2 grid. Read the text printed inside the speech bubbles of each "
               "panel, in reading order (top left, top right, bottom left, bottom right), EXACTLY as printed: every letter, "
               "number, bracket and punctuation mark, with no correction, no translation and no tidying. Answer "
               '{"panels": [["text of one bubble", ...], ...], "other_text": "text that is NOT inside a speech bubble, or '
               'an empty string"}. A panel with no bubble is an empty list.')

_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', " ": " "})


def norm(text: Any) -> str:
    """A bubble's words for comparing: the same letters, digits and punctuation, with spacing and curly quotes made plain.
    Case is kept (a changed capital in a clause name is a change)."""
    return " ".join(unicodedata.normalize("NFC", str(text or "")).translate(_QUOTES).split())


def _json(text: str) -> dict[str, Any] | None:
    m = re.search(r"\{.*\}", str(text or ""), re.S)
    if not m:
        return None
    try:
        out = json.loads(m.group(0))
    except ValueError:
        return None
    return out if isinstance(out, dict) else None


def compare(script: dict[str, Any], seen: dict[str, Any] | None) -> list[str]:
    """What differs between the script and what was read off the picture: [] means every bubble is exact and nothing else
    is written on it. Within a panel the bubbles are compared as a set (which hangs higher is the picture's choice)."""
    if not isinstance(seen, dict) or not isinstance(seen.get("panels"), list):
        return ["the picture could not be read back"]
    diffs: list[str] = []
    got = seen["panels"]
    if len(got) != PANELS:
        diffs.append(f"{len(got)} panels were read, not {PANELS}")
    for n, panel in enumerate(script["panels"]):
        want = sorted(norm(_words(line)) for line in panel["lines"])
        have = sorted(norm(t) for t in (got[n] if n < len(got) and isinstance(got[n], list) else []))
        if want != have:
            lost = [w for w in want if w not in have]
            extra = [h for h in have if h not in want]
            diffs.append(f"panel {n + 1}: " + (f"expected {lost!r}, read {extra!r}" if lost or extra else "bubble count differs"))
    if norm(seen.get("other_text")):
        diffs.append(f"text outside a bubble: {norm(seen.get('other_text'))[:80]!r}")
    return diffs


def _for_reader(art: bytes) -> bytes:
    """A JPEG of the picture small enough to send inline, with the lettering still readable (longest side 1280)."""
    img = Image.open(io.BytesIO(art)).convert("RGB")
    img.thumbnail((1280, 1280), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return buf.getvalue()


def readback(read: Any, art: bytes, script: dict[str, Any]) -> list[str]:
    """[] when `read(system, prompt, jpeg_bytes, mime)` (ChatGPT's own sight) finds every bubble exactly as scripted, else
    what differs. A reader that fails raises: the caller decides what an unreadable proof is worth."""
    seen = _json(read(READ_SYSTEM, READ_PROMPT, _for_reader(art), "image/jpeg"))
    return compare(script, seen)


# ------------------------------------------------------------------------------------------------- the recommendation

def make(draw: Any, read: Any, script: dict[str, Any], tries: int = TRIES) -> dict[str, Any]:
    """One finished poster as {jpeg, how, tries, notes}. `draw(prompt) -> bytes` is the picture maker, `read(system, prompt,
    data, mime) -> str` is a reader that can see (or None). The picture maker draws the words; every bubble is read back and
    compared with the script; a page that differs is drawn again, up to `tries` times. When none is exact, or nothing can
    read it back, the page is drawn WITHOUT words and Semasa prints them (how "printed"): the words on a finished poster are
    always the script's, whichever way it was made. A failing picture maker raises: the caller tries another one."""
    check(script)
    notes: list[str] = []
    if read is None:
        notes.append("no reader that can see, so nothing could be proven: the words were printed by Semasa")
    else:
        for n in range(1, max(1, tries) + 1):
            art = draw(prompt_full(script))
            try:
                diffs = readback(read, art, script)
            except Exception as exc:  # noqa: BLE001 - an unreadable proof is no proof: print the words instead
                notes.append(f"try {n}: the read-back failed ({type(exc).__name__}: {str(exc)[:120]})")
                break
            if not diffs:
                return {"jpeg": frame(art, script), "how": "ai", "tries": n, "notes": notes}
            notes.append(f"try {n}: " + "; ".join(diffs)[:300])
    art = draw(prompt_art(script))
    return {"jpeg": frame(letter(art, script), script), "how": "printed", "tries": len(notes), "notes": notes}
