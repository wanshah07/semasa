"""Auto-fit in Semasa's own drawing (Wan, 16 Nov 2026: "for all poster, single card, comic, image make auto-fit application").

Whatever words a poster, a card, a carousel slide or a Threads-style page is given, the picture fits by itself: nothing in
the margins, nothing on the source line or under the footer, and a card with little to say is not left half empty with
small type. Each card is drawn twice, with its words and without, and the two pictures are compared: ink that the
wordless card does not have, inside a place words may never be, is words that escaped. The browser-drawn looks have the
same checks in test_studio_cards.py."""

import pytest
from PIL import ImageChops

from semasa import slides, threads_slides

TOKEN = "NPRA.600-1/9/13(13)Jld.2"
# 110 characters, one token no wrapper can break on a space
LONG_TITLE = f"Direktif {TOKEN} mewajibkan label *pembungkusan* kosmetik dikemas kini sebelum tarikh kuat kuasa"
SENTENCE = ("Pemegang notifikasi mesti mengemas kini label pembungkusan dan menyimpan rekod pengilangan lengkap bagi setiap "
            "kelompok produk kosmetik yang dipasarkan di seluruh Malaysia tanpa pengecualian.")
LONG = {"title": LONG_TITLE, "points": [SENTENCE] * 5}          # the writer's poster maximum: five points of 22 words
SHORT = {"title": "Semak label *dahulu*", "points": ["Label ada nombor NOT."]}
SOURCE = "Garis Panduan Kawalan Produk Kosmetik di Malaysia, NPRA; Peraturan-Peraturan Kawalan Dadah dan Kosmetik 1984"
WEBSITE = "www.kkmhalalconsultant.com"
SIZES = [(1080, 1080), (1080, 1350)]
MARGIN_BAND = 30          # the outer safe margin, in pixels of a 1080 px card
HALF = 0.5                # a short load must span at least this share of its room


def _escaped(with_words, without, box):
    """How many pixels differ between the two pictures inside `box` (left, top, right, bottom)."""
    left, top, right, bottom = [int(v) for v in box]
    if right <= left or bottom <= top:
        return 0
    d = ImageChops.difference(with_words.convert("L").crop((left, top, right, bottom)),
                              without.convert("L").crop((left, top, right, bottom)))
    return sum(1 for v in d.tobytes() if v > 48)


def _margins(a, b):
    w, h = a.size
    m = MARGIN_BAND
    return sum(_escaped(a, b, box) for box in ((0, 0, w, m), (0, h - m, w, h), (0, 0, m, h), (w - m, 0, w, h)))


def _span(img, top, bottom):
    """The share of [top, bottom] between the first and the last row that carries ink."""
    g = img.convert("L")
    w = g.size[0]
    paper = g.getpixel((w // 2, top + 2))
    rows = [y for y in range(top, bottom) if sum(1 for x in range(90, w - 90, 3) if abs(g.getpixel((x, y)) - paper) > 40) > 3]
    return (rows[-1] - rows[0]) / (bottom - top) if rows else 0.0


def _draw(slide, index, total, size, stream="regulab", source=SOURCE):
    return slides.render_one(slide, index, total, stream=stream, eyebrow="Sains kosmetik (penerbitan terkini)", source=source,
                             website="" if stream == "linkedin" else WEBSITE, ground=None, size=size)


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("stream", ["regulab", "linkedin"])
@pytest.mark.parametrize("index,total", [(0, 1), (0, 3), (1, 3), (2, 3)])
def test_the_long_load_stays_out_of_the_margins_the_header_the_source_and_the_footer(size, stream, index, total):
    """A poster or a lone card (0 of 1), a cover, a middle slide and a closing slide. The 110-character title with its
    unbreakable reference and five points of 22 words is drawn whole, smaller, and never where words may not be."""
    w, h = size
    slide = {**LONG, "points": LONG["points"][:1] if (index, total) == (0, 3) else LONG["points"]}
    words = _draw(slide, index, total, size, stream)
    blank = _draw({"title": "", "points": []}, index, total, size, stream)
    assert _margins(words, blank) == 0, "words in the outer margin"
    assert _escaped(words, blank, (0, 0, w, slides.MARGIN + slides.HEAD_H - 8)) == 0, "words under the logo and the label"
    assert _escaped(words, blank, (0, h - slides.MARGIN - slides.FOOT_H, w, h)) == 0, "words under the footer"
    no_source = _draw({"title": "", "points": []}, index, total, size, stream, source="")
    box = ImageChops.difference(blank.convert("L"), no_source.convert("L")).point(lambda v: 255 if v > 48 else 0).getbbox()
    if box:                                                # the closing slide and the lone card carry the source line
        assert _escaped(words, blank, (box[0] - 4, box[1] - 4, box[2] + 4, box[3] + 4)) == 0, "words on the source line"


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("index,total", [(0, 1), (0, 3), (1, 3)])
def test_a_short_load_fills_at_least_half_of_its_room(size, index, total):
    """Three words and one short point used to sit in the upper third of the card at 1.35 times the template's size."""
    h = size[1]
    img = _draw(SHORT, index, total, size, source="NPRA")
    top, bottom = slides.MARGIN + slides.HEAD_H, h - slides.MARGIN - slides.FOOT_H - (70 if total == 1 else 0)
    assert _span(img, top, bottom) >= HALF, "the card is left half empty"


def test_growing_never_cuts_a_word_in_two_and_a_full_slide_never_grows():
    width, room = 1080 - 2 * slides.MARGIN, 900
    word = {"title": "Pembungkusan", "points": ["Bertanggungjawab sepenuhnya."]}
    base = slides.layout(word, "single", width, 1.0, True)
    grown = slides.fit(word, "single", width, room, True)
    assert grown.title_font.size > base.title_font.size, "a sparse slide grows"
    assert slides.pieces(grown) == slides.pieces(base) and len(grown.title) == 1, "its long word is still one word"
    assert grown.title_font.getlength("Pembungkusan") <= width
    full = slides.fit(LONG, "single", width, room, True)
    assert full.title_font.size < base.title_font.size and full.height <= room, "a full slide shrinks until it fits"
    with pytest.raises(slides.SlideError, match="too long to fit"):
        slides.fit({"title": LONG_TITLE, "points": [SENTENCE * 3] * 5}, "single", width, room, True)


# --- the Threads-style pages -----------------------------------------------------------------------------------------

PAGES_LONG = [{"title": LONG_TITLE, "points": []},
              {"title": "Apa yang berubah untuk pemegang notifikasi", "points": [SENTENCE[:118].rsplit(" ", 1)[0]] * 3},
              {"title": "Nombor NOT ialah permulaan", "points": [SENTENCE[:118].rsplit(" ", 1)[0]] * 2}]
PAGES_SHORT = [{"title": "Semak label *dahulu*", "points": []}, {"title": "Apa itu NOT", "points": ["Label ada nombor NOT."]},
               {"title": "Ingat ini", "points": ["Label ada nombor NOT."]}]


@pytest.mark.parametrize("size", SIZES)
def test_a_threads_page_keeps_its_longest_words_inside_the_text_zone(size):
    items = slides.normalise(PAGES_LONG)
    p = threads_slides.plan(items, size, "regulab", SOURCE)
    z = p.zones
    empty = threads_slides.Plan(z, p.share, [threads_slides._block({"title": "", "points": []}, i == 0, 100, z.unit, 1.0)
                                             for i in range(len(items))], p.source, p.source_font)
    for i, page in enumerate(items):
        kw = dict(eyebrow="Kosmetik", website=WEBSITE, stream="regulab", photo=None, focus=0.5)
        words = threads_slides.render_page(page, i, len(items), p, **kw)
        blank = threads_slides.render_page({"title": "", "points": []}, i, len(items), empty, **kw)
        w, h = size
        assert _margins(words, blank) == 0, f"page {i + 1}: words in the outer margin"
        assert _escaped(words, blank, (0, 0, w, z.head[3])) == 0, f"page {i + 1}: words in the header"
        assert _escaped(words, blank, (0, z.image[1], w, h)) == 0, f"page {i + 1}: words on the picture or the foot"


@pytest.mark.parametrize("size", SIZES)
def test_a_threads_page_with_little_to_say_grows_into_its_text_zone(size):
    items = slides.normalise(PAGES_SHORT)
    p = threads_slides.plan(items, size, "regulab", "")
    zone = p.zones.text[3] - p.zones.text[1]
    width = p.zones.text[2] - p.zones.text[0]
    for i, (page, block) in enumerate(zip(items, p.blocks, strict=True)):
        plain = threads_slides._block(page, i == 0, width, p.zones.unit, 1.0)
        assert block.scale > 1.0 and block.height > plain.height, f"page {i + 1} kept the template's size in an empty zone"
        assert block.height <= threads_slides.FILL_TARGET * zone + 1, f"page {i + 1} grew past its zone"
        assert slides.pieces(block) == slides.pieces(plain), f"page {i + 1}: a word was cut in two to grow"
    dense = threads_slides.plan(slides.normalise(PAGES_LONG), size, "regulab", SOURCE)
    assert all(b.scale <= 1.0 for b in dense.blocks), "a full page never grows"
