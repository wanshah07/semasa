"""A small picture on every poster (Wan, 22 Nov 2026): a real picture cut out on a transparent background, laid where it never
covers the words."""

import io

from PIL import Image, ImageDraw

from semasa import stickers


def _jar() -> bytes:
    im = Image.new("RGB", (512, 512), "white")
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([170, 190, 345, 410], 20, fill=(80, 170, 220), outline=(20, 40, 60), width=8)
    buf = io.BytesIO()
    im.save(buf, "JPEG")
    return buf.getvalue()


def _slide(words_at: tuple[int, int, int, int] | None) -> bytes:
    im = Image.new("RGB", (1080, 1350), (247, 242, 232))
    if words_at:
        ImageDraw.Draw(im).rectangle(words_at, fill=(20, 20, 20))
    buf = io.BytesIO()
    im.save(buf, "JPEG")
    return buf.getvalue()


def test_the_white_around_a_drawing_becomes_transparent():
    png = stickers.cutout(_jar())
    im = Image.open(io.BytesIO(png))
    assert im.mode == "RGBA" and im.getpixel((0, 0))[3] == 0, "the corner is transparent"
    assert im.getpixel((im.width // 2, im.height // 2))[3] == 255, "the drawing stays"
    assert stickers.cutout(_slide(None)) is None, "a blank picture is not a cut-out"


def test_a_photo_becomes_a_round_badge():
    im = Image.open(io.BytesIO(stickers.circle(_jar())))
    assert im.getpixel((0, 0))[3] == 0 and im.getpixel((im.width // 2, im.height // 2))[3] == 255


def _busy() -> bytes:
    im = Image.new("RGB", (1080, 1350), (247, 242, 232))
    d = ImageDraw.Draw(im)
    for y in range(0, 1350, 24):
        d.rectangle((0, y, 1080, y + 10), fill=(20, 20, 20))       # words everywhere
    buf = io.BytesIO()
    im.save(buf, "JPEG")
    return buf.getvalue()


def _changed_rows(a: bytes, b: bytes) -> list[int]:
    x, y = Image.open(io.BytesIO(a)).convert("L"), Image.open(io.BytesIO(b)).convert("L")
    px, py = x.load(), y.load()
    return sorted({j for j in range(0, x.height, 4) for i in range(0, x.width, 4) if abs(px[i, j] - py[i, j]) > 40})


def test_the_sticker_goes_in_a_free_corner_and_never_on_the_words():
    png = stickers.cutout(_jar())
    words = (60, 120, 1020, 900)                                     # the words fill the top two thirds
    slide = _slide(words)
    rows = _changed_rows(slide, stickers.lay(slide, png, "single", 0))
    assert rows, "the sticker was laid somewhere"
    assert min(rows) > 900, "below the words, where the card is empty"


def test_a_middle_slide_with_no_room_gets_none_and_the_last_slide_is_left_alone():
    png = stickers.cutout(_jar())
    busy = _busy()
    assert stickers.lay(busy, png, "middle", 1) == busy
    pics = [_slide(None), _slide(None), _slide(None)]
    out = stickers.on_slides(pics, png)
    assert out[2] == pics[2] and out[0] != pics[0]
    assert stickers.on_slides(pics, None) == pics, "no sticker: the slides as drawn"


def test_wan_can_remove_it():
    assert stickers.ensure(None, None, "r1", {"sticker": False}) is None
    assert stickers.subject_for({"domain": "halal_my"}).startswith("a plate")
    assert stickers.subject_for({}) == stickers.DEFAULT_SUBJECT
