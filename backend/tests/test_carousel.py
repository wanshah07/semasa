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


def test_a_carousel_of_nine_is_squeezed_to_five_written_slides_and_keeps_every_word():
    items = _set(9)
    out, joined = carousel.compact(items, "regulab")
    assert len(out) == 5 and joined == 4
    assert out[0] == items[0] and out[-1] == items[-1]                # the cover and the closing slide stay alone
    kept = _words(out)
    for i in range(1, 8):
        assert f"Fakta nombor {i}" in kept                              # nothing is dropped, only joined
    assert len(items) == 9                                              # the words as written are not touched


def test_linkedin_keeps_six_written_slides_because_it_has_no_logo_card():
    assert len(carousel.compact(_set(9), "linkedin")[0]) == 6
    assert carousel.text_target("regulab") == 5 and carousel.text_target("linkedin") == 6


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


@pytest.fixture
def worker(monkeypatch):
    from semasa import db, ideas
    saved, uploads = {}, []
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


def test_the_worker_squeezes_a_nine_slide_ws_regulab_carousel_and_ends_it_on_the_logo_card(worker):
    from fakestore import FakeStore
    saved, uploads = worker
    row = _job("regulab", _set(9))
    assert media_generator.process_slides(FakeStore(media_generations=[row]), row, media_generator.MediaSettings.load()) is True
    meta = saved["meta"]
    assert meta["count"] == 6 and len(uploads) == 6 and meta["closing_logo"] is True and meta["squeezed_from"] == 9
    assert len(meta["slides"]) == 9                              # the words on the job are the ones written


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
        if len(words) < 9:
            raise slides.SlideError("slide 3: too long to fit")
        return real(words, **kw)
    monkeypatch.setattr(slides, "render", render)
    row = _job("regulab", _set(9))
    assert media_generator.process_slides(FakeStore(media_generations=[row]), row, media_generator.MediaSettings.load()) is True
    assert seen == [5, 9] and saved["meta"]["count"] == 10 and saved["meta"]["squeezed_from"] is None


def _top_right_ink(jpeg):
    im = Image.open(io.BytesIO(jpeg)).convert("L").crop((700, 40, 1000, 110))
    return sum(1 for v in im.tobytes() if v < 110)


def test_every_ws_regulab_slide_carries_the_logo_top_right_and_linkedin_carries_none():
    words = [{"title": "Notifikasi bukan kelulusan", "points": ["NPRA menetapkan had."]}, {"title": "Fakta dua", "points": []}]
    reg = slides.render(words, stream="regulab", eyebrow="Kosmetik")
    li = slides.render(words, stream="linkedin", eyebrow="Angle")
    assert all(_top_right_ink(p) > 300 for p in reg)           # the dark-green logo is there on every slide
    assert all(_top_right_ink(p) < 20 for p in li)             # rule 7: LinkedIn has no ws.regulab identity
