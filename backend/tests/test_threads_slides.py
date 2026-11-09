"""Threads-style slides: 2 to 5 pages of short text over a picture, drawn with Pillow. The layout and the validation are the
parts worth testing: where things go, what is refused, and what is never drawn (a word over a picture, a cut word, another
company's identity)."""

import dataclasses
import io

import pytest
from fakestore import FakeStore
from PIL import Image

from semasa import compliance, design, media_generator, publisher, slides, threads_slides
from semasa.config import LLMSettings, MediaSettings

PAGES = [{"title": "Notifikasi *bukan* kelulusan", "points": []},
         {"title": "Apa NPRA semak", "points": ["Dokumen PIF selepas produk dipasarkan."]},
         {"title": "Ringkasnya", "points": ["Notifikasi ialah pendaftaran.", "Rekod tetap perlu disimpan."]}]
SIZES = [(1080, 1080), (1080, 1350), (1080, 1920), (1200, 628)]


def _img(b: bytes) -> Image.Image:
    return Image.open(io.BytesIO(b)).convert("RGB")


def _photo(color=(20, 120, 200), size=(900, 600)) -> bytes:
    img = Image.new("RGB", size, color)
    for x in range(0, size[0], 90):                       # stripes, so a different crop is a different picture
        img.paste((255 - color[0], 255 - color[1], 255 - color[2]), (x, 0, x + 30, size[1]))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _lum(rgb) -> float:
    def ch(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def _contrast(a, b) -> float:
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


# --- the words: what is refused -----------------------------------------------------------------

def test_a_set_is_two_to_five_pages():
    for n in (2, 5):
        threads_slides.check([{"title": f"Tajuk {i}", "points": []} for i in range(n)], (1080, 1350))
    for n in (1, 6):
        with pytest.raises(slides.SlideError, match=rf"2 to 5 pages, but {n}"):
            threads_slides.check([{"title": f"Tajuk {i}", "points": []} for i in range(n)], (1080, 1350))


def test_the_cover_needs_a_hook_of_sane_length():
    with pytest.raises(slides.SlideError, match="page 1 is the cover and needs a headline"):
        threads_slides.check([{"title": "", "points": ["satu"]}, PAGES[1]], (1080, 1350))
    long_hook = " ".join(["kata"] * (threads_slides.MAX_HOOK_WORDS + 1))
    with pytest.raises(slides.SlideError, match=r"page 1: the hook is 17 words"):
        threads_slides.check([{"title": long_hook, "points": []}, PAGES[1]], (1080, 1350))
    # an emphasis marker is not a word
    threads_slides.check([{"title": "*satu* dua tiga", "points": []}, PAGES[1]], (1080, 1350))


def test_a_page_stays_concise_and_says_which_page_is_too_much():
    four = {"title": "Tajuk", "points": ["a", "b", "c", "d"]}
    with pytest.raises(slides.SlideError, match=r"page 2: 4 points, at most 3"):
        threads_slides.check([PAGES[0], four], (1080, 1350))
    wordy = {"title": "Tajuk", "points": ["perkataan " * 50]}
    with pytest.raises(slides.SlideError, match=r"page 2: too long for a Threads-style page"):
        threads_slides.check([PAGES[0], wordy], (1080, 1350))


def test_a_size_it_cannot_hold_is_refused_not_squeezed():
    for bad in ((851, 315), (1584, 396), (500, 500)):
        with pytest.raises(slides.SlideError, match="needs a size"):
            threads_slides.check(PAGES, bad)
    for ok in SIZES:
        threads_slides.check(PAGES, ok)


# --- the layout: where everything goes ---------------------------------------------------------

def _inside(inner, outer) -> bool:
    return inner[0] >= outer[0] and inner[1] >= outer[1] and inner[2] <= outer[2] and inner[3] <= outer[3]


def _overlap(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("share", threads_slides.IMAGE_SHARES)
def test_every_zone_is_on_the_page_and_none_overlap(size, share):
    z = threads_slides.zones(size, share)
    page = (0, 0, *size)
    zs = {"head": z.head, "text": z.text, "image": z.image, "foot": z.foot}
    for name, r in zs.items():
        assert r[0] < r[2] and r[1] < r[3], f"{name} has no area"
        assert _inside(r, page), f"{name} leaves the page"
        assert r[0] >= z.margin and r[2] <= size[0] - z.margin, f"{name} breaks the margin"
    names = list(zs)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            assert not _overlap(zs[a], zs[b]), f"{a} overlaps {b}"


def test_tall_pages_stack_and_wide_pages_go_side_by_side():
    assert not threads_slides.zones((1080, 1350), 0.44).side_by_side
    assert not threads_slides.zones((1080, 1080), 0.44).side_by_side
    wide = threads_slides.zones((1200, 628), 0.44)
    assert wide.side_by_side and wide.image[0] > wide.text[2]          # the picture sits right of the text
    tall = threads_slides.zones((1080, 1350), 0.44)
    assert tall.image[1] > tall.text[3]                                # under the text


def test_a_smaller_share_gives_the_text_more_room():
    big, small = threads_slides.zones((1080, 1350), 0.44), threads_slides.zones((1080, 1350), 0.27)
    assert (small.text[3] - small.text[1]) > (big.text[3] - big.text[1])
    assert (small.image[3] - small.image[1]) < (big.image[3] - big.image[1])


def test_the_picture_shrinks_before_a_word_is_cut():
    easy = threads_slides.plan(PAGES, (1080, 1350))
    assert easy.share == threads_slides.IMAGE_SHARES[0]
    heavy = PAGES[:1] + [{"title": "Apa pemilik perlu simpan sebelum produk dipasarkan",
                          "points": ["Dokumen PIF lengkap dengan bukti keselamatan bahan. " * 3,
                                     "Rekod pengilangan dan bukti tuntutan produk. " * 3]}]
    p = threads_slides.plan(heavy, (1080, 1350))
    assert p.share < easy.share, "the picture gave way to the words"
    for block, page in zip(p.blocks, heavy, strict=True):
        drawn = [r.text for ln in block.title for r in ln.runs] + [r.text for pts in block.points for ln in pts for r in ln.runs]
        assert drawn == slides.strip_emphasis(" ".join([page["title"], *page["points"]])).split(), "every word is kept"
        assert block.height <= (p.zones.text[3] - p.zones.text[1])


def test_one_picture_share_for_the_whole_set_so_pages_line_up():
    heavy = [PAGES[0], {"title": "Satu", "points": ["Dokumen PIF lengkap dengan bukti keselamatan bahan. " * 5]}, PAGES[2]]
    p = threads_slides.plan(heavy, (1080, 1350))
    assert len(p.blocks) == 3 and p.zones.image == threads_slides.zones((1080, 1350), p.share).image


def test_text_that_cannot_fit_names_the_page(monkeypatch):
    # Within the character cap no real page fails to fit at the smallest size (the cap is what keeps pages short), so the
    # fit failure is forced: page 2's block is always taller than any text zone, at every type size and picture share.
    real = threads_slides._block

    def tall_second_page(page, cover, width, unit, scale):
        block = real(page, cover, width, unit, scale)
        return dataclasses.replace(block, height=10**6) if page["title"] == "Halaman dua" else block
    monkeypatch.setattr(threads_slides, "_block", tall_second_page)
    crowded = [PAGES[0], {"title": "Halaman dua", "points": ["Satu poin."]}]
    with pytest.raises(slides.SlideError, match=r"page 2: too long to fit even at the smallest type size"):
        threads_slides.plan(crowded, (1080, 1350))


def test_a_page_over_the_character_cap_is_refused_before_any_fitting():
    over = [PAGES[0], {"title": "x " * 25, "points": ["perkataan " * 15] * 3}]
    with pytest.raises(slides.SlideError, match=r"page 2: too long for a Threads-style page"):
        threads_slides.plan(over, (600, 600))


def test_a_source_too_long_for_the_closing_page_is_an_error():
    with pytest.raises(slides.SlideError, match="source line is too long"):
        threads_slides.plan(PAGES, (1080, 1350), source="Rujukan " * 200)


# --- drawing ----------------------------------------------------------------------------------

def test_a_set_comes_back_as_one_jpeg_per_page_in_the_asked_size():
    for size in SIZES:
        out = threads_slides.render(PAGES, size=size, source="NPRA, 2026")
        assert len(out) == 3 and all(b[:2] == b"\xff\xd8" for b in out)
        assert all(_img(b).size == size for b in out)
        assert len({bytes(b) for b in out}) == 3, "no two pages are the same picture"


def test_rendering_is_deterministic():
    assert threads_slides.render(PAGES) == threads_slides.render(PAGES)


def test_the_page_number_changes_with_the_set_and_the_place():
    three = threads_slides.render(PAGES)
    two = threads_slides.render(PAGES[:2])
    assert three[0] != two[0], "'1/3' and '1/2' are drawn"
    p = threads_slides.plan(slides.normalise(PAGES), (1080, 1350))
    box = _img(three[0]).crop((p.zones.head[2] - 160, p.zones.head[1], p.zones.head[2], p.zones.head[3]))
    assert (box.getpixel((4, box.height // 2)) == threads_slides.PAPER
            or box.getpixel((box.width - 6, box.height // 2)) == threads_slides.INK)


def test_the_place_in_the_set_is_told_by_shape_not_colour():
    p = threads_slides.plan(slides.normalise(PAGES), (1080, 1350))
    z = p.zones
    pages = [threads_slides.render_page(pg, i, 3, p, eyebrow="", website="", stream="regulab", photo=None, focus=0.5)
             for i, pg in enumerate(slides.normalise(PAGES))]
    r = max(7, round(10 * z.unit))
    cy = (z.foot[1] + z.foot[3]) // 2
    centres = [z.foot[0] + r + i * round(54 * z.unit) for i in range(3)]
    for page_no, img in enumerate(pages):
        filled = [img.getpixel((cx, cy)) == threads_slides.INK for cx in centres]
        assert filled == [i == page_no for i in range(3)], f"page {page_no + 1}: only its own node is filled"


def test_ink_and_the_label_read_on_paper():
    for name in ("INK", "ACCENT_TEXT", "MUTED"):
        assert _contrast(getattr(threads_slides, name), threads_slides.PAPER) >= 4.5, name
    assert _contrast(threads_slides.PAPER, threads_slides.INK) >= 4.5          # the counter's text on its box


def test_no_word_is_ever_drawn_over_the_picture():
    z = threads_slides.zones((1080, 1350), threads_slides.IMAGE_SHARES[0])
    inset = (z.image[0] + 6, z.image[1] + 6, z.image[2] - 6, z.image[3] - 6)
    photo = _photo()
    a = threads_slides.plan(slides.normalise(PAGES), (1080, 1350))
    b_words = [{"title": "Tajuk lain sama sekali", "points": ["Dan satu baris lagi."]}, {"title": "Dua", "points": []}]
    b = threads_slides.plan(b_words, (1080, 1350))
    assert a.zones.image == b.zones.image == z.image, "the picture's place does not depend on the words"
    one = threads_slides.render_page(slides.normalise(PAGES)[0], 0, 2, a, eyebrow="", website="", stream="regulab",
                                     photo=photo, focus=0.5)
    two = threads_slides.render_page(b_words[0], 0, 2, b, eyebrow="LABEL", website="", stream="regulab",
                                     photo=photo, focus=0.5)
    assert one.crop(inset).tobytes() == two.crop(inset).tobytes(), "the picture is the same whatever the words are"


def test_one_shared_background_pans_across_the_pages_and_own_pictures_do_not():
    photo = _photo()
    shared = threads_slides.render(PAGES, photos=[photo] * 3)
    p = threads_slides.plan(slides.normalise(PAGES), (1080, 1350))
    z = p.zones
    crops = [_img(b).crop((z.image[0] + 40, z.image[1] + 40, z.image[2] - 40, z.image[3] - 40)).tobytes() for b in shared]
    assert len(set(crops)) == 3, "each page shows another part of the one picture"
    first, last = threads_slides.focus_crop(Image.open(io.BytesIO(photo)), (400, 300), 0), \
        threads_slides.focus_crop(Image.open(io.BytesIO(photo)), (400, 300), 1)
    assert first.tobytes() != last.tobytes() and first.size == last.size == (400, 300)


def test_a_page_with_no_picture_gets_an_original_drawing_that_belongs_to_its_place():
    a, b = threads_slides.illustration((500, 400), 0, 3), threads_slides.illustration((500, 400), 1, 3)
    assert a.size == (500, 400) and a.tobytes() != b.tobytes()
    assert a.tobytes() == threads_slides.illustration((500, 400), 0, 3).tobytes()
    colours = {c for _, c in a.getcolors(maxcolors=500 * 400)}
    assert colours <= {threads_slides.PANEL, threads_slides.INK, threads_slides.ACCENT, threads_slides.PAPER}, \
        "only the page's own four colours"


def test_a_picture_that_cannot_be_opened_names_the_page():
    with pytest.raises(slides.SlideError, match=r"page 2: the picture could not be opened"):
        threads_slides.render(PAGES, photos=[None, b"not a picture", None])


def test_every_word_stays_inside_the_margins():
    long = [{"title": "Rujukan NPRA.600-1/9/13(13)Jld.2),NOT221001118K,MAL19962457T,10.1007/s11356-026-38214-9",
             "points": ["x" * 120]}, {"title": "Dua", "points": ["Direktif Bilangan 19 Tahun 2026 " * 4]}]
    for size in SIZES[:3]:
        z = threads_slides.zones(size, threads_slides.IMAGE_SHARES[-1])
        img = _img(threads_slides.render(long, size=size)[0])
        blank = _img(threads_slides.render([{"title": "a", "points": []}, {"title": "b", "points": []}], size=size)[0])
        edge = z.margin - 12
        w, h = size
        bad = sum(1 for y in range(0, h, 2) for x in range(0, w, 2)
                  if (x < edge or x >= w - edge or y < edge or y >= h - edge) and img.getpixel((x, y)) != blank.getpixel((x, y)))
        assert bad == 0, size


def test_the_website_is_on_ws_regulab_only():
    reg = threads_slides.render(PAGES, stream="regulab", website="www.kkmhalalconsultant.com")
    reg_none = threads_slides.render(PAGES, stream="regulab", website="")
    li = threads_slides.render(PAGES, stream="linkedin", website="www.kkmhalalconsultant.com")
    li_none = threads_slides.render(PAGES, stream="linkedin", website="")
    assert reg != reg_none and li == li_none


def test_the_closing_page_carries_the_source_and_the_others_do_not():
    with_src = threads_slides.render(PAGES, source="NPRA, 2026")
    without = threads_slides.render(PAGES)
    assert with_src[0] == without[0] and with_src[1] == without[1] and with_src[2] != without[2]


# --- the job in the media worker ----------------------------------------------------------------

def _settings():
    return MediaSettings(provider="cloudflare", batch=5, max_attempts=3, poll_seconds=0, max_wait_image=1,
                         max_wait_video=1, replicate_token=None, replicate_image_model="a/b",
                         replicate_video_model="c/d", replicate_image_input_key="input_image",
                         replicate_video_input_key="start_image", openai_key=None,
                         openai_base_url="https://api.openai.com/v1", openai_image_model="gpt-image-1",
                         openai_video_model="sora-2", openai_image_size="1024x1024", openai_video_seconds="8",
                         openai_video_size="1280x720")


class Writer:
    configured = True

    def __init__(self, out):
        self.out, self.seen, self.last_model = out, [], "rootsys-m"
        self.s = LLMSettings(provider="openai", api_key="k", base_url="https://rootsys.cloud/v1", model="m", timeout=5)

    def why_off(self):
        return "off"

    def chat_json(self, system, user, max_tokens=0, **k):
        self.seen.append((system, user))
        return self.out


def _store(meta, **row):
    job = {"id": "t1", "mode": "slides", "type": "image", "status": "processing", "attempts": 1,
           "created_at": "2099-01-01T00:00:00+00:00",
           "meta": {"stream": "regulab", "bg": "none", "design": "threads", **meta}, **row}
    return FakeStore(semasa_settings=[{"key": "brand", "value": {"regulab": {"website": "www.kkmhalalconsultant.com"}}}],
                     semasa_posts=[{"id": "p1", "status": "draft", "media_ids": ["own"]}],
                     media_generations=[job, {"id": "own", "mode": "slides", "type": "image", "status": "done", "meta": {}}])


def _run(store, llm=None):
    return media_generator.process_row(store, store.tables["media_generations"][0], _settings(), {}, llm)


@pytest.fixture(autouse=True)
def _uploads(monkeypatch):
    got = {}
    monkeypatch.setattr(media_generator.db, "upload_generated",
                        lambda store, path, data, ct: got.setdefault(path, data) and f"https://cdn/{path}")
    return got


def test_a_threads_job_draws_the_set_and_records_it(_uploads):
    store = _store({"slides": PAGES, "citation": "NPRA, 2026"})
    assert _run(store) is True
    job = store.tables["media_generations"][0]
    assert job["status"] == "done" and job["meta"]["count"] == 3 and job["meta"]["look"] == "threads"
    assert job["model"] == "threads-v1"
    assert [_img(b).size for b in _uploads.values()] == [(1080, 1350)] * 3


def test_a_threads_job_takes_the_chosen_size(_uploads):
    store = _store({"slides": PAGES, "format": "story", "size": [1080, 1920]})
    assert _run(store) is True
    assert {_img(b).size for b in _uploads.values()} == {(1080, 1920)}


def test_a_threads_job_with_one_page_is_refused_with_the_reason(_uploads):
    store = _store({"slides": PAGES[:1]})
    assert _run(store) is False
    job = store.tables["media_generations"][0]
    assert job["status"] == "error" and "2 to 5 pages, but 1" in job["error"] and not _uploads


def test_a_threads_job_with_six_pages_is_refused_not_cut(_uploads):
    store = _store({"slides": PAGES + PAGES})
    assert _run(store) is False
    assert "2 to 5 pages, but 6" in store.tables["media_generations"][0]["error"]


def test_the_picture_of_the_job_goes_under_every_page(monkeypatch, _uploads):
    monkeypatch.setattr(media_generator, "fetch_reference", lambda url: (_photo(), "image/png", "x.png"))
    store = _store({"slides": PAGES, "bg": "reference"}, reference_url="https://ref/x.png")
    assert _run(store) is True
    assert store.tables["media_generations"][0]["meta"]["bg_used"] == "reference"
    z = threads_slides.zones((1080, 1350), threads_slides.IMAGE_SHARES[0])
    centre = ((z.image[0] + z.image[2]) // 2, (z.image[1] + z.image[3]) // 2)
    for data in _uploads.values():
        px = _img(data).getpixel(centre)
        assert px != threads_slides.PANEL and sum(px) > 0


def test_a_page_with_its_own_picture_token_uses_it(monkeypatch):
    own = _photo((200, 30, 30))
    seen = []

    def fake_ground_for(store, row, tok):
        seen.append(tok)
        return (own, tok) if tok == "lib:g_demo" else (None, None)
    monkeypatch.setattr(media_generator, "ground_for", fake_ground_for)
    items = slides.normalise([{**PAGES[0], "bg": "lib:g_demo"}, PAGES[1], {**PAGES[2], "bg": "lib:g_demo"}])
    got = media_generator.thread_photos(_store({}), {"id": "t1"}, items, b"job-ground")
    assert got == [own, b"job-ground", own] and seen == ["lib:g_demo"], "fetched once, the others keep the job's ground"


def test_a_page_picture_that_fails_falls_back_to_the_job_ground(monkeypatch):
    def boom(store, row, tok):
        raise OSError("storage down")
    monkeypatch.setattr(media_generator, "ground_for", boom)
    items = slides.normalise([{**PAGES[0], "bg": "lib:g_demo"}, PAGES[1]])
    assert media_generator.thread_photos(_store({}), {"id": "t1"}, items, None) == [None, None]


def test_rule_breaking_words_are_drawn_but_flagged(_uploads):
    store = _store({"slides": [{"title": "Hubungi kami sekarang", "points": ["www.kkmhalalconsultant.com"]}, PAGES[1]]})
    _run(store)
    flags = store.tables["media_generations"][0]["meta"]["flags"]
    assert any(f["hard"] and f["where"].startswith("Design") for f in flags)


def test_attached_to_a_post_it_is_added_never_replacing_the_posts_pictures():
    store = _store({"slides": PAGES}, post_id="p1")
    _run(store)
    assert store.tables["semasa_posts"][0]["media_ids"] == ["own", "t1"]


def test_the_threads_set_is_judged_by_the_post_rules_like_other_artwork():
    entry = publisher.scan_entry({"mode": "slides", "meta": {"design": "threads", "slides": PAGES}})
    assert entry == {"alt": "", "artwork": PAGES}
    # a post carries a caption on every platform of its stream; without one the scan says "empty" for the caption, which is not
    # what this test is about, so the post is given one that passes
    caption = {p: "Notifikasi ialah pendaftaran, bukan kelulusan." for p in compliance.platforms_for("regulab")}
    post = {"stream": "regulab", "citation": "", "text": {"bm": caption}, "media": [entry]}
    assert not [f for f in compliance.scan(post) if f["hard"]]
    # the same scan finds a rule broken inside the Threads-style words, and names the Design set
    bad = publisher.scan_entry({"mode": "slides", "meta": {"design": "threads", "slides": [
        {"title": "Hubungi kami sekarang", "points": []}, PAGES[1]]}})
    hits = [f for f in compliance.scan({**post, "media": [bad]}) if f["hard"]]
    assert hits and all(f["where"].startswith("Design 1") for f in hits)


# --- the writer ---------------------------------------------------------------------------------

def test_the_writer_is_asked_for_a_hook_cover_and_is_held_to_five_pages():
    words = [{"title": f"Halaman {i}", "points": [f"Satu fakta {i}."]} for i in range(7)]
    llm = Writer({"slides": words, "citation": "NPRA"})
    items, cit = design.write(llm, "Notifikasi bukan kelulusan", "threads", "regulab")
    assert len(items) == threads_slides.MAX_PAGES and cit == "NPRA"
    system, user = llm.seen[0]
    assert "Threads-style set of 2 to 5 pages" in system and "HOOK SHAPES" in system and "Notifikasi" in user
    assert "No call to action" in system, "the post rules still lead"


def test_the_company_stream_is_never_given_a_first_person_confession_for_its_hook():
    from semasa import hook_bank
    confession = hook_bank.FAMILIES["vulnerable"][0]
    assert confession in design.thread_hooks("linkedin")
    assert confession not in design.thread_hooks("regulab")


def test_a_writer_that_gives_one_page_fails_the_job_with_the_page_rule(_uploads):
    llm = Writer({"slides": PAGES[:1], "citation": ""})
    store = _store({"brief": "Notifikasi bukan kelulusan"})
    assert _run(store, llm) is False
    assert "2 to 5 pages, but 1" in store.tables["media_generations"][0]["error"]


def test_a_brief_becomes_words_saved_on_the_job_before_drawing(_uploads):
    llm = Writer({"slides": PAGES, "citation": "NPRA"})
    store = _store({"brief": "Notifikasi bukan kelulusan"})
    assert _run(store, llm) is True
    meta = store.tables["media_generations"][0]["meta"]
    assert len(meta["slides"]) == 3 and meta["written_by"] == "rootsys-m" and meta["citation"] == "NPRA"


def test_threads_is_a_design_with_a_4_5_default_and_other_designs_are_unchanged():
    assert "threads" in design.DESIGNS
    assert design.size_of({"design": "threads"}, "regulab") == (1080, 1350)
    assert design.size_of({"design": "carousel"}, "linkedin") is None
    design.check(slides.normalise(PAGES[:2] * 1), "carousel")           # a carousel has no minimum (9 Nov 2026)
    design.check(slides.normalise(PAGES[:2]), "threads")
