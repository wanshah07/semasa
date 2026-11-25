"""A ws.regulab carousel ends on the logo card; a long carousel is squeezed (Wan, 11 Nov 2026)."""

import io

import pytest
from PIL import Image

from semasa import carousel, media_generator, slides


def _set(n, lead="Satu ayat sokongan yang pendek."):
    out = [{"title": "Tajuk utama", "points": []}]
    out += [{"title": f"Fakta nombor {i}", "points": [], "lead": lead} for i in range(1, n - 1)]
    out.append({"title": "Penutup yang jelas", "points": [], "lead": "Satu baris akhir."})
    return out


def _words(items):
    return " ".join(" ".join([s.get("title", ""), s.get("lead", ""), *s.get("points", [])]) for s in items)


def test_a_carousel_of_twelve_is_squeezed_to_seven_written_slides_and_keeps_every_word():
    items = _set(12)
    out, joined = carousel.compact(items, "regulab")
    assert len(out) == 7 and joined == 5
    assert out[0] == items[0] and out[-1] == items[-1]                # the cover and the closing slide stay alone
    kept = _words(out)
    for i in range(1, 11):
        assert f"Fakta nombor {i}" in kept                              # nothing is dropped, only joined
    assert len(items) == 12                                             # the words as written are not touched


def test_a_carousel_is_under_ten_pictures_cover_and_logo_card_included():
    # Wan, 23 Nov 2026: "limitkan slide less 10": 7 written + the brand cover + the logo card = 9; LinkedIn has neither: 9
    assert carousel.MAX_SLIDES == 9 and carousel.text_target("regulab") == 7 and carousel.text_target("linkedin") == 9
    assert len(carousel.compact(_set(12), "linkedin")[0]) == 9


def test_a_short_carousel_is_left_alone():
    items = _set(5)
    assert carousel.compact(items, "regulab") == (items, 0)


def test_slides_too_full_to_join_are_not_joined():
    long = "Ayat yang sangat panjang tentang peraturan dan notifikasi " * 16
    items = _set(8, lead=long)
    out, joined = carousel.compact(items, "regulab")
    assert joined == 0 and out == items


def test_which_carousels_get_the_logo_card():
    assert carousel.has_logo_card("regulab", 5) and carousel.has_logo_card("regulab", 2)
    assert not carousel.has_logo_card("regulab", 1)          # a lone card or a poster
    assert not carousel.has_logo_card("linkedin", 6)         # rule 7: no ws.regulab identity on LinkedIn


def test_the_logo_card_is_a_4_by_5_jpeg_with_the_logo_and_the_follow_line():
    data = carousel.closing_jpeg(5, 6)
    im = Image.open(io.BytesIO(data))
    assert im.format == "JPEG" and im.size == (1080, 1350)
    dark = [v for v in im.convert("L").resize((108, 135)).tobytes() if v < 100]
    assert len(dark) > 200                                   # the dark-green logo and the line are there on the paper
    ground = io.BytesIO()
    Image.new("RGB", (900, 1100), (30, 60, 90)).save(ground, "JPEG")
    over = Image.open(io.BytesIO(carousel.closing_jpeg(5, 6, ground=ground.getvalue())))
    assert over.size == (1080, 1350)


def _drawing() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (900, 600), (239, 235, 224)).save(buf, "JPEG")
    return buf.getvalue()


@pytest.fixture
def worker(monkeypatch):
    import base64

    from semasa import db, ideas, illustrated
    saved, uploads = {}, []
    # A card's illustration is mandatory (Wan, 25 Nov 2026), so a job with no picture maker fails instead of drawing a bare card.
    # These tests are about the squeeze and the logo card, not the pictures: a drawing is handed to every slide and the cover
    # without being uploaded (the uploads below count the pages).
    uri = "data:image/jpeg;base64," + base64.b64encode(_drawing()).decode("ascii")
    monkeypatch.setattr(illustrated, "with_art", lambda store, s, row, meta, items, stream, llm=None, **k: [
        {**it, "art_url": uri, "art_label": ""} for it in items])
    monkeypatch.setattr(illustrated, "cover_art", lambda *a, **k: _drawing())
    monkeypatch.setattr(db, "upload_generated", lambda store, path, data, ct: uploads.append(data) or f"https://x/{len(uploads)}.jpg")
    monkeypatch.setattr(db, "finish_media", lambda store, rid, **kw: saved.update(kw))
    monkeypatch.setattr(db, "attach_slides_to_draft", lambda *a, **k: None)
    monkeypatch.setattr(ideas, "load_settings", lambda store: {"brand": {}})
    monkeypatch.setattr(media_generator, "picture_pending", lambda store, row: False)
    monkeypatch.setattr(media_generator, "slide_ground", lambda store, row: (None, None))
    monkeypatch.setattr(media_generator, "_drop_files", lambda *a, **k: None)
    return saved, uploads


def _job(stream, items):
    return {"id": "j1", "post_id": "p1", "mode": "slides", "type": "image", "status": "processing", "attempts": 1,
            "meta": {"slides": items, "stream": stream, "bg": "none", "citation": "NPRA"}}


def test_the_worker_squeezes_a_twelve_slide_ws_regulab_carousel_and_ends_it_on_the_logo_card(worker):
    from fakestore import FakeStore
    saved, uploads = worker
    row = _job("regulab", _set(12))
    assert media_generator.process_slides(FakeStore(media_generations=[row]), row, media_generator.MediaSettings.load()) is True
    meta = saved["meta"]
    # the brand cover is a picture in front of the first page (Wan, 23 Nov 2026), so seven pages + cover + logo card = 9
    assert meta["count"] == 9 and len(uploads) == 9 and meta["closing_logo"] is True and meta["squeezed_from"] == 12
    assert len(meta["slides"]) == 12                             # the words on the job are the ones written


def test_a_linkedin_carousel_has_no_logo_card(worker):
    from fakestore import FakeStore
    saved, uploads = worker
    row = _job("linkedin", _set(4))
    assert media_generator.process_slides(FakeStore(media_generations=[row]), row, media_generator.MediaSettings.load()) is True
    assert saved["meta"]["count"] == 4 and saved["meta"]["closing_logo"] is False


def test_a_squeezed_set_that_fails_to_draw_is_drawn_as_written(worker, monkeypatch):
    from fakestore import FakeStore
    saved, uploads = worker
    real = slides.render
    seen = []

    def render(words, **kw):
        seen.append(len(words))
        if len(words) < 11:
            raise slides.SlideError("slide 3: too long to fit")
        return real(words, **kw)
    monkeypatch.setattr(slides, "render", render)
    row = _job("regulab", _set(12))
    assert media_generator.process_slides(FakeStore(media_generations=[row]), row, media_generator.MediaSettings.load()) is True
    # the hook slide is the cover, so the eleven content slides are what is squeezed or drawn as written: 11 pages + cover + logo
    assert seen == [7, 11] and saved["meta"]["count"] == 13 and saved["meta"]["squeezed_from"] is None


def test_a_studio_look_that_cannot_fit_a_slide_falls_back_to_the_classic_look(worker, monkeypatch):
    from fakestore import FakeStore

    from semasa import studio_cards
    saved, uploads = worker

    def too_full(*a, **k):
        raise slides.SlideError("slide 5 (i_title): The slide is fuller than the card: shorten a line.")
    monkeypatch.setattr(studio_cards, "render", too_full)
    row = _job("regulab", _set(4))
    row["meta"]["look"] = "image"
    assert media_generator.process_slides(FakeStore(media_generations=[row]), row, media_generator.MediaSettings.load()) is True
    meta = saved["meta"]
    assert meta["look"] == "classic" and "fuller than the card" in meta["look_fallback"] and len(uploads) >= 4


def _top_right_ink(jpeg):
    im = Image.open(io.BytesIO(jpeg)).convert("L").crop((700, 40, 1000, 110))
    return sum(1 for v in im.tobytes() if v < 110)


def test_every_ws_regulab_slide_carries_the_logo_top_right_and_linkedin_carries_none():
    words = [{"title": "Notifikasi bukan kelulusan", "points": ["NPRA menetapkan had."]}, {"title": "Fakta dua", "points": []}]
    reg = slides.render(words, stream="regulab", eyebrow="Kosmetik")
    li = slides.render(words, stream="linkedin", eyebrow="Angle")
    assert all(_top_right_ink(p) > 300 for p in reg)           # the dark-green logo is there on every slide
    assert all(_top_right_ink(p) < 20 for p in li)             # rule 7: LinkedIn has no ws.regulab identity


# --- the cover (Wan, 11 Nov 2026) -------------------------------------------------------------------------------------------

def test_the_cover_carries_the_logo_and_the_hook_inside_the_grid_crop():
    data = carousel.cover_jpeg("Benda pasal pensijilan halal rumah sembelih yg takde sapa bagitau kau", "satu baris sokongan",
                               "Halal Malaysia")
    im = Image.open(io.BytesIO(data)).convert("L")
    assert im.size == (1080, 1350)
    # since 22 Nov 2026 a white card: a green logo and a black title (the light-blue circles are not ink)
    ink = lambda box: sum(1 for v in im.crop(box).tobytes() if v < 110)       # noqa: E731
    assert ink((300, 120, 780, 380)) > 3000                                    # the logo, near the top of the block
    assert ink((100, 540, 980, 1060)) > 8000                                   # the hook title
    assert ink((0, 0, 60, 1350)) < 50 and ink((1020, 0, 1080, 1350)) < 400     # nothing in the strip the 3:4 tile crops
    assert im.getpixel((540, 20)) > 200, "the card is white"


def test_a_tall_film_cover_keeps_its_block_in_the_middle_band():
    im = Image.open(io.BytesIO(carousel.cover_jpeg("Kesan sampingan ni akan hilang sendiri?", size=(1080, 1920)))).convert("L")
    ink = lambda box: sum(1 for v in im.crop(box).tobytes() if v < 110)       # noqa: E731
    assert ink((0, 0, 1080, 300)) < 200 and ink((0, 1620, 1080, 1920)) < 200   # the 3:4 crop removes these bands
    assert ink((100, 400, 980, 1500)) > 8000


def test_a_cover_too_long_for_its_supporting_line_is_refused_not_cut():
    with pytest.raises(slides.SlideError):
        carousel.cover_jpeg("Tajuk", "ayat yang sangat panjang " * 20)


def test_the_worker_puts_the_cover_first_for_ws_regulab_and_leaves_linkedin_alone(worker):
    from fakestore import FakeStore
    saved, uploads = worker
    row = _job("regulab", _set(4))
    assert media_generator.process_slides(FakeStore(media_generations=[row]), row, media_generator.MediaSettings.load()) is True
    assert saved["meta"]["cover"] is True and saved["meta"]["closing_logo"] is True
    assert saved["meta"]["count"] == 5            # the hook is the cover, not a page too: 3 pages + the cover + the logo card
    assert saved["meta"]["cover_v"] == carousel.COVER_VERSION, "the cover is marked with its design version"
    cover = Image.open(io.BytesIO(uploads[0])).convert("RGB")
    assert min(cover.getpixel((540, 20))) > 240 and cover.getpixel((540, 20)) != slides.PAPER    # the white cover (22 Nov 2026)
    saved.clear()
    uploads.clear()
    row = _job("linkedin", _set(4))
    assert media_generator.process_slides(FakeStore(media_generations=[row]), row, media_generator.MediaSettings.load()) is True
    assert saved["meta"]["cover"] is False
    assert Image.open(io.BytesIO(uploads[0])).convert("RGB").getpixel((20, 20)) == slides.PAPER


def test_a_first_slide_with_points_keeps_its_points_behind_a_cover_in_front(worker):
    from fakestore import FakeStore
    saved, uploads = worker
    items = _set(4)
    items[0] = {"title": "Tajuk", "points": ["satu", "dua"]}
    row = _job("regulab", items)
    assert media_generator.process_slides(FakeStore(media_generations=[row]), row, media_generator.MediaSettings.load()) is True
    # Wan, 11 Nov 2026 ("add cover in front"): the cover goes in front and the content slide follows whole
    assert saved["meta"]["cover"] is True
    assert saved["meta"]["slides"][0].get("front_cover") is True and saved["meta"]["slides"][1] == items[0]
    # the hook put in front IS the cover (not a page as well), so the pictures are the content slides + cover + logo card
    assert saved["meta"]["count"] == len(items) + 1 + (1 if saved["meta"]["closing_logo"] else 0)


def test_a_hook_with_one_line_under_it_gets_the_cover_and_a_content_slide_does_not():
    hook = {"title": "Semua org ckp sunscreen *non-comedogenic* sesuai untuk kulit acne",
            "points": ["Realitinya itu cuma dakwaan label, bukan jaminan."]}
    assert carousel.cover_words(hook) == (hook["title"], hook["points"][0])
    assert carousel.cover_words({"title": "Hook", "lead": "baris sokongan", "points": []}) == ("Hook", "baris sokongan")
    assert carousel.cover_words({"title": "Hook"}) == ("Hook", "")
    assert carousel.cover_words({"title": "Tiga fakta", "points": ["satu", "dua"]}) is None       # a content slide stays
    assert carousel.cover_words({"title": "Hook", "points": ["satu"], "note": "nota"}) is None
    assert carousel.cover_words({"points": ["tiada tajuk"]}) is None and carousel.cover_words(None) is None
    carousel.cover_jpeg(*carousel.cover_words(hook))                                                  # and it draws


def test_a_content_first_slide_gets_a_hook_in_front_once():
    items = [{"title": "Symptom *PJ.2.1* nampak macam demam biasa", "points": ["satu", "dua", "tiga"]},
             {"title": "Kedua", "points": ["x"]}]
    out = carousel.with_front_cover(items, "regulab")
    assert len(out) == 3 and out[1:] == items and carousel.cover_words(out[0]) == (items[0]["title"], "")
    assert carousel.with_front_cover(out, "regulab") == out                      # again: nothing changes
    hook = [{"title": "Hook", "points": ["satu baris"]}, {"title": "Kedua"}]
    assert carousel.with_front_cover(hook, "regulab") == hook                    # already a hook
    assert carousel.with_front_cover(items, "linkedin") == items                 # LinkedIn has no cover
    assert carousel.with_front_cover(items[:1], "regulab") == items[:1]          # a single card stays single


# --- a slide that carries an ayat al-Quran (16 Nov 2026) ---------------------------------------------------------------

_VERSE = {"title": "Peringatan", "points": [], "ayat": "2:168", "ayat_ar": "ar", "ayat_tr": "tr",
          "ayat_ed": "ms.basmeih@alquran.cloud", "ayat_ok": "1", "ayat_label": "Al-Baqarah 2:168"}


def _jpeg_bytes():
    buf = io.BytesIO()
    Image.new("RGB", (1080, 1350), (247, 242, 230)).save(buf, "JPEG")
    return buf.getvalue()


def _verse_set():
    deck = _set(4)
    return [deck[0], deck[1], dict(_VERSE), deck[3]]


def test_a_set_with_a_verse_is_checked_against_the_source_and_drawn_by_the_studio_renderer(worker, monkeypatch):
    """The classic look has no Quran face: a set that carries a verse is drawn in a Studio look, after the stored words were
    checked against the published source. The verse slide reaches the renderer whole."""
    from fakestore import FakeStore

    from semasa import quran, studio_cards
    saved, uploads = worker
    checked, drawn = [], []
    monkeypatch.setattr(quran, "verify", lambda items, stream, client=None: checked.append((len(items), stream)))

    def render(items, **kw):
        drawn.append((kw["look"], [s.get("ayat") for s in items]))
        return [_jpeg_bytes()] * len(items)
    monkeypatch.setattr(studio_cards, "render", render)
    row = _job("regulab", _verse_set())                              # no look on the job: the classic one
    assert media_generator.process_slides(FakeStore(media_generations=[row]), row, media_generator.MediaSettings.load()) is True
    assert checked == [(4, "regulab")] and drawn[0][0] == "grid" and "2:168" in drawn[0][1]
    assert "Grid" in saved["meta"]["look_ayat"] and saved["meta"]["look"] == "grid"


def test_a_verse_that_no_longer_matches_the_source_is_not_drawn(worker, monkeypatch):
    from fakestore import FakeStore

    from semasa import quran, studio_cards
    saved, uploads = worker

    def differs(items, stream, client=None):
        raise quran.QuranError("slide 3: the words stored for Al-Baqarah 2:168 differ from the published source.")
    monkeypatch.setattr(quran, "verify", differs)
    monkeypatch.setattr(studio_cards, "render", lambda *a, **k: pytest.fail("a verse that failed its check was drawn"))
    row = _job("regulab", _verse_set())
    media_generator.process_slides(FakeStore(media_generations=[row]), row, media_generator.MediaSettings.load())
    assert saved.get("status") == "error" and "differ from the published source" in str(saved.get("error_message") or saved)
    assert not uploads


def test_a_verse_too_long_for_its_card_never_falls_back_to_the_classic_look(worker, monkeypatch):
    """The classic look would draw the slide WITHOUT its verse, so the usual "too full, draw it in classic" rescue is off."""
    from fakestore import FakeStore

    from semasa import quran, studio_cards
    saved, uploads = worker
    monkeypatch.setattr(quran, "verify", lambda *a, **k: None)

    def too_full(*a, **k):
        raise slides.SlideError("slide 3 (q_ayat): The slide is fuller than the card: this verse is too long for one card.")
    monkeypatch.setattr(studio_cards, "render", too_full)
    monkeypatch.setattr(slides, "render", lambda *a, **k: pytest.fail("the classic renderer was given a verse slide"))
    row = _job("regulab", _verse_set())
    row["meta"]["look"] = "era"
    media_generator.process_slides(FakeStore(media_generations=[row]), row, media_generator.MediaSettings.load())
    assert saved.get("status") == "error" and not uploads


def test_a_join_keeps_the_first_slides_note_too():
    # Codex review on #340: join() left a's note out
    out = carousel.join({"title": "A", "lead": "satu", "note": "catatan satu", "points": []},
                        {"title": "B", "lead": "dua", "note": "catatan dua", "points": []})
    assert "catatan satu" in " ".join(out["points"]) and "catatan dua" in " ".join(out["points"])



# --- the cover is the hook, so slide 1 says something else (Wan, 25 Nov 2026) ---------------------------------------------------

def _pages_drawn(monkeypatch):
    """The words of every page the classic look is asked to draw (the cover is a picture of its own, never one of these)."""
    seen = []
    real = slides.render

    def render(words, **kw):
        seen.append([str(w.get("title") or "") for w in words])
        return real(words, **kw)
    monkeypatch.setattr(slides, "render", render)
    return seen


def test_page_one_after_the_cover_is_not_the_hook_the_cover_carries(worker, monkeypatch):
    from fakestore import FakeStore
    saved, uploads = worker
    seen = _pages_drawn(monkeypatch)
    items = _set(5)                                     # "Tajuk utama" is the hook slide, then three facts and a closing slide
    row = _job("regulab", items)
    assert media_generator.process_slides(FakeStore(media_generations=[row]), row, media_generator.MediaSettings.load()) is True
    assert seen == [["Fakta nombor 1", "Fakta nombor 2", "Fakta nombor 3", "Penutup yang jelas"]]
    assert saved["meta"]["cover"] is True and saved["meta"]["count"] == 6      # 4 pages + the cover + the logo card
    assert saved["meta"]["cover_title"] == "Tajuk utama"                        # the cover still wears the hook
    assert saved["meta"]["slides"] == items                                     # the words on the job are as written


def test_a_hook_and_one_more_slide_still_get_their_cover(worker, monkeypatch):
    from fakestore import FakeStore
    saved, uploads = worker
    seen = _pages_drawn(monkeypatch)
    row = _job("regulab", _set(2))
    assert media_generator.process_slides(FakeStore(media_generations=[row]), row, media_generator.MediaSettings.load()) is True
    assert seen == [["Penutup yang jelas"]] and saved["meta"]["cover"] is True and saved["meta"]["count"] == 3


def test_a_hook_put_in_front_of_a_content_slide_is_the_cover_and_not_a_page(worker, monkeypatch):
    from fakestore import FakeStore
    saved, uploads = worker
    seen = _pages_drawn(monkeypatch)
    items = _set(4)
    items[0] = {"title": "Tajuk", "points": ["satu", "dua"]}
    row = _job("regulab", items)
    assert media_generator.process_slides(FakeStore(media_generations=[row]), row, media_generator.MediaSettings.load()) is True
    assert seen[0][0] == "Tajuk" and seen[0].count("Tajuk") == 1               # the content slide keeps its title, once


def test_the_cover_illustration_is_made_from_the_hook_slide(worker, monkeypatch):
    from fakestore import FakeStore

    from semasa import illustrated
    got = []
    monkeypatch.setattr(illustrated, "cover_art",
                        lambda store, s, row, meta, item, *a, **k: got.append(item["title"]) or _drawing())
    row = _job("regulab", _set(4))
    assert media_generator.process_slides(FakeStore(media_generations=[row]), row, media_generator.MediaSettings.load()) is True
    assert got == ["Tajuk utama"]


def test_linkedin_has_no_cover_and_keeps_every_slide(worker, monkeypatch):
    from fakestore import FakeStore
    saved, uploads = worker
    seen = _pages_drawn(monkeypatch)
    row = _job("linkedin", _set(4))
    assert media_generator.process_slides(FakeStore(media_generations=[row]), row, media_generator.MediaSettings.load()) is True
    assert seen == [["Tajuk utama", "Fakta nombor 1", "Fakta nombor 2", "Penutup yang jelas"]]
