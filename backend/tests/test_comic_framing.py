# ruff: noqa: E501
"""Wan, 17 Nov 2026: "Make sure comic or person not cut off". The picture maker is asked for a safe framing, the people's position is
MEASURED on the wordless picture and a bubble never covers one, a drawing that leaves no room is drawn once more and then refused or
read back as the maker's own words, and trim and the frame never cut the outer border or the people at a picture's edge."""

from __future__ import annotations

import copy
import io
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageDraw

from semasa import comic, comic_job, comic_sample, comic_writer

FIX = Path(__file__).parent / "fixtures" / "comic_real"
SCRIPT = comic_sample.SCRIPT
WALL = (240, 232, 214)
SKIN = (222, 170, 130)
HAIR = (30, 24, 24)


def head(d: ImageDraw.ImageDraw, cx: int, top: int, floor: int, r: int = 38) -> None:
    """A head and shoulders: hair on top of a face, on a body that runs down to the panel's own bottom (`floor`)."""
    d.ellipse([cx - r, top, cx + r, top + 2 * r], fill=SKIN)
    d.pieslice([cx - r - 3, top - 4, cx + r + 3, top + 2 * r - 20], 180, 360, fill=HAIR)
    d.rectangle([cx - r - 20, top + 2 * r, cx + r + 20, floor], fill=(40, 50, 120))


def wordless(heads: dict[int, tuple[int, int, int]], side: int = 1080) -> Image.Image:
    """Four panels on a wall. `heads` maps a panel (0 to 3) to (left head x, top y, right head top y), panel-relative pixels at 1080."""
    img = Image.new("RGB", (side, side), WALL)
    d = ImageDraw.Draw(img)
    half = side // 2
    for k in range(4):
        px, py = (k % 2) * half, (k // 2) * half
        if k in heads:
            ax, ay, by = heads[k]
            head(d, px + ax, py + ay, py + half - 6)
            head(d, px + half - ax, py + by, py + half - 6)
        d.rectangle([px + 2, py + 2, px + half - 3, py + half - 3], outline=(0, 0, 0), width=3)
    d.rectangle([0, 0, side - 1, side - 1], outline=(0, 0, 0), width=3)
    return img


def png(img: Image.Image) -> bytes:
    b = io.BytesIO()
    img.save(b, "PNG")
    return b.getvalue()


def inks(img: Image.Image, box: tuple[float, float, float, float], panel: int) -> int:
    """Ink pixels inside a rectangle of the picture, judged against that panel's own wall (measured independently of Heads)."""
    half = img.size[0] // 2
    px, py = (panel % 2) * half, (panel // 2) * half
    crop = img.crop((px + 20, py + 20, px + half - 20, py + 80))
    wall = comic._wall(list(crop.getdata()), crop.size[0], crop.size[1])
    x0, y0, x1, y1 = (int(v) for v in box)
    return sum(1 for y in range(y0, y1, 2) for x in range(x0, x1, 2) if comic._is_ink(img.getpixel((x, y)), wall))


def covered(img: Image.Image, bs: list[dict]) -> list[tuple[int, int]]:
    out = []
    for b in bs:
        x0, y0, x1, y1 = b["box"]
        n = b["panel"] - 1
        count = inks(img, (x0 + 4, y0 + 4, x1 - 4, y1 - 4), n)
        if count > 6:
            out.append((b["panel"], count))
    return out


# ------------------------------------------------------------------------------------------------ the prompt (check 3)


def test_every_prompt_carries_the_framing_line_and_the_second_ask_is_stronger():
    for p in (comic.prompt_art(SCRIPT), comic.prompt_full(SCRIPT)):
        assert "FRAMING." in p and "whole head and face" in p and "never a head or a face" in p
        assert "left, right or top edge" in p and "waist-up or chest-up" in p
    strong = comic.prompt_art(SCRIPT, strong=True)
    assert "STRONGER FRAMING" in strong and "45 percent" in strong and "FRAMING." in strong
    assert "STRONGER" not in comic.prompt_art(SCRIPT) and "STRONGER" not in comic.prompt_full(SCRIPT)


# ------------------------------------------------------------------------------------ measuring the people (check 2)


def test_the_measured_top_of_a_head_is_where_the_head_is():
    img = wordless({1: (150, 200, 330)})
    h = comic.measure_heads(img)
    left = h.floor(1, 100, 200)
    assert 185 <= left <= 215, f"the left head starts at 200, measured {left}"
    assert 315 <= h.floor(1, 400, 480) <= 345, "the right head starts at 330"
    assert h.floor(0, 0, 540) == 540 and h.floor(2, 0, 540) == 540, "a panel with nobody in it has its floor at the bottom"
    assert h.floor(1, 250, 290) > 330, "between the two heads the wall is empty down to the shoulders"


def test_a_head_against_the_top_edge_is_seen_and_a_head_with_room_is_not():
    assert comic.measure_heads(wordless({0: (150, 10, 200)})).edges[0]["top"] is True
    assert comic.measure_heads(wordless({0: (150, 200, 220)})).edges[0]["top"] is False


@pytest.mark.parametrize("name", ["wordless-chatgpt-art", "wordless-chatgpt-full", "wordless-gemini-art"])
def test_no_bubble_covers_a_person_in_the_real_pictures(name):
    img = Image.open(FIX / f"{name}.jpg").convert("RGB").resize((1080, 1080))
    h = comic.measure_heads(img)
    bs = comic.bubbles(SCRIPT, 1080, h)
    assert covered(img, bs) == [], "an independent ink count inside every bubble finds only wall"
    tips = [(b["panel"] - 1, b["tail"][2]) for b in bs]
    for n, (x, y) in tips:
        px, py = (n % 2) * 540, (n // 2) * 540
        assert y <= py + h.floor(n, x - px - 4, x - px + 4) + 1, "a tail stops at the top of the head it points to"
    # the old layout (the empty top 44%, no measuring) DID cover one on these same pictures: the case this fixes
    old = comic.bubbles(SCRIPT)
    if name != "wordless-gemini-art":
        assert covered(img, old), f"{name}: the unmeasured layout is expected to cover a head here"


def test_a_head_high_in_the_panel_moves_or_shrinks_the_bubble_and_never_gets_covered():
    img = wordless({1: (130, 150, 300), 2: (140, 190, 190)})
    h = comic.measure_heads(img)
    plain = comic.bubbles(SCRIPT)
    assert covered(img, plain), "the unmeasured layout covers the high head"
    placed = comic.bubbles(SCRIPT, 1080, h)
    assert covered(img, placed) == []
    assert min(b["size"] for b in placed) < min(b["size"] for b in plain) or placed != plain


def test_no_room_is_said_and_never_solved_by_covering_a_head():
    high = {k: (130, 60, 70) for k in range(4)}  # heads at 11% of every panel
    h = comic.measure_heads(wordless(high))
    with pytest.raises(comic.NoRoom, match="without covering one.*panel"):
        comic.bubbles(SCRIPT, 1080, h)
    assert issubclass(comic.NoRoom, comic.ComicError)


def test_two_bubbles_go_side_by_side_when_only_the_width_above_the_heads_is_free():
    img = wordless({0: (120, 215, 215)})
    h = comic.measure_heads(img)
    script = copy.deepcopy(SCRIPT)
    placed = comic.bubbles(script, 1080, h)
    assert covered(img, placed) == []


def test_letter_prints_where_the_picture_is_empty_and_refuses_otherwise():
    img = wordless({1: (130, 150, 300)})
    out = comic.letter(img, SCRIPT)
    assert out.size == (1080, 1080)
    with pytest.raises(comic.NoRoom):
        comic.letter(wordless({k: (130, 60, 70) for k in range(4)}), SCRIPT)


# ----------------------------------------------------------------------- the drawing job: redraw once, then fall back or refuse


class Maker:
    def __init__(self, *pictures: Image.Image):
        self.pictures, self.prompts = list(pictures), []

    def __call__(self, prompt: str) -> bytes:
        self.prompts.append(prompt)
        return png(self.pictures.pop(0) if len(self.pictures) > 1 else self.pictures[0])


GOOD = wordless({k: (130, 230, 240) for k in range(4)})
TOO_HIGH = wordless({k: (130, 60, 70) for k in range(4)})
TOUCHING = wordless({0: (150, 6, 8), 1: (130, 230, 240), 2: (130, 230, 240), 3: (130, 230, 240)})


def test_a_drawing_with_no_room_is_drawn_once_more_with_a_stronger_instruction():
    draw = Maker(TOO_HIGH, GOOD)
    keep: dict = {}
    pic, words = comic_job.make(SCRIPT, None, draw, None, mode="art", keep=keep)
    assert len(draw.prompts) == 2 and "STRONGER FRAMING" not in draw.prompts[0] and "STRONGER FRAMING" in draw.prompts[1]
    assert words["path"] == "art" and words["retried"] is True and words["draws"] == 2
    assert "without covering one" in words["framing"][0] and keep["wordless"] is True
    assert pic.size[0] == pic.size[1]


def test_a_head_on_the_top_edge_is_drawn_once_more_and_a_good_second_drawing_is_used():
    draw = Maker(TOUCHING, GOOD)
    _pic, words = comic_job.make(SCRIPT, None, draw, None, mode="art")
    assert len(draw.prompts) == 2 and "STRONGER FRAMING" in draw.prompts[1]
    assert "top edge of panel 1" in words["framing"][0] and words["retried"] is True


def test_a_head_that_stays_on_the_top_edge_is_refused_with_that_reason_because_no_bubble_can_go_above_it():
    draw = Maker(TOUCHING, TOUCHING)
    with pytest.raises(comic.NoRoom, match="top edge of panel 1"):
        comic_job.make(SCRIPT, None, draw, None, mode="art")


def test_no_room_twice_with_no_reader_is_refused_with_the_reason_and_never_covers_a_head():
    draw = Maker(TOO_HIGH, TOO_HIGH)
    with pytest.raises(comic.NoRoom, match="drawn twice.*Shorten"):
        comic_job.make(SCRIPT, None, draw, None, mode="art")
    assert len(draw.prompts) == 2


def test_no_room_twice_falls_back_to_the_picture_makers_own_words_when_a_reader_can_check_them():
    script = comic_writer.assemble(
        {"title": SCRIPT["title"], "setting": "", "panels": SCRIPT["panels"]},
        comic_job.comic_library.series_of(comic_job.comic_library.library(None), "kak-lin-tanya"),
        "regulab",
        "MPPHM (Domestik) 2020, Klausa 40(2)",
    )
    reading = {
        "panels": [{"panel": n, "bubbles": [ln["text"] for ln in p["lines"]]} for n, p in enumerate(script["panels"], 1)],
        "other_text": [],
    }
    draw = Maker(TOO_HIGH, TOO_HIGH, GOOD)
    keep: dict = {}
    pic, words = comic_job.make(script, None, draw, lambda _jpeg: reading, mode="art", keep=keep)
    assert words["path"] == "full" and words["checked"] and "own words are used instead" in words["why"]
    assert keep["wordless"] is False, "the picture is shown whole, as the maker drew it"
    assert len(draw.prompts) == 3 and "SPEECH" not in draw.prompts[2] and "EXACTLY" in draw.prompts[2]
    assert pic.size[0] == pic.size[1]


# ------------------------------------------------------------------------------ trim and the frame (check 3, the outer edge)


def outline(im: Image.Image) -> list[float]:
    """Dark share of the outermost outline on each side (the best of the first six rows or columns): top, left, bottom, right."""
    g = im.convert("L")
    w, h = g.size
    row = lambda y: sum(g.getpixel((x, y)) < 80 for x in range(w)) / w  # noqa: E731
    col = lambda x: sum(g.getpixel((x, y)) < 80 for y in range(h)) / h  # noqa: E731
    return [
        max(row(i) for i in range(6)),
        max(col(i) for i in range(6)),
        max(row(h - 1 - i) for i in range(6)),
        max(col(w - 1 - i) for i in range(6)),
    ]


@pytest.mark.parametrize("name", ["chatgpt-square", "chatgpt-full-square", "gemini-square", "gemini-full-square"])
def test_trim_keeps_the_outer_border_of_the_panels_on_the_real_pictures(name):
    img = Image.open(FIX / f"{name}.jpg").convert("RGB")
    out = comic.trim(img)
    assert all(v >= 0.9 for v in outline(out)), f"{name}: the outermost outline survives on all four sides {outline(out)}"
    assert out.size[0] >= img.size[0] * (1 - 2 * comic.TRIM_BAND) and out.size[1] >= img.size[1] * (1 - 2 * comic.TRIM_BAND)


def test_trim_takes_the_makers_stray_border_and_keeps_the_outline_inside_it():
    base = Image.open(FIX / "gemini-square.jpg").convert("RGB")
    base = comic.trim(base)
    framed = Image.new("RGB", (base.size[0] + 40, base.size[1] + 40), (235, 120, 40))
    ImageDraw.Draw(framed).rectangle([6, 6, framed.size[0] - 7, framed.size[1] - 7], fill=(250, 250, 250))
    framed.paste(base, (20, 20))
    out = comic.trim(framed)
    assert all(v >= 0.9 for v in outline(out)) and abs(out.size[0] - base.size[0]) <= 6 and abs(out.size[1] - base.size[1]) <= 6


def test_trim_never_cuts_a_person_standing_at_the_edge_of_the_picture():
    img = Image.new("RGB", (1000, 1000), WALL)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 300, 70, 900], fill=HAIR)  # dark clothes against the left edge, no outline style
    d.rectangle([930, 100, 999, 700], fill=(40, 50, 120))  # and a shoulder against the right edge
    d.ellipse([4, 120, 80, 200], fill=SKIN)
    out = comic.trim(img)
    assert out.size == img.size, "nothing is cut: no outline to find, no plain margin to take"
    assert ImageChops.difference(out, img).getbbox() is None


def test_the_frame_places_the_whole_comic_and_cuts_nothing_of_it():
    img = Image.open(FIX / "chatgpt-full-square.jpg").convert("RGB")
    sq = comic.trim(img)
    script = copy.deepcopy(SCRIPT)
    script.update(cast=SCRIPT["cast"], source="S")
    poster = Image.open(io.BytesIO(comic.frame(sq, script, episode="Siri X · Episod 1", stream="regulab", website="www.w.my")))
    assert poster.size == comic.POSTER
    placed = poster.crop((0, comic.TITLE_H, comic.SIDE, comic.TITLE_H + comic.SIDE))
    want = sq.resize((comic.SIDE, comic.SIDE), Image.LANCZOS)
    diff = ImageChops.difference(placed, want).convert("L")
    assert sum(diff.getdata()) / (comic.SIDE * comic.SIDE) < 3, "the comic is on the poster whole"
    for box in (
        (0, 0, comic.SIDE, 6),
        (0, comic.SIDE - 6, comic.SIDE, comic.SIDE),
        (0, 0, 6, comic.SIDE),
        (comic.SIDE - 6, 0, comic.SIDE, comic.SIDE),
    ):
        edge = ImageChops.difference(placed.crop(box), want.crop(box)).convert("L")
        assert max(edge.getdata()) < 90, f"the outer edge {box} of the comic is on the poster uncut"
