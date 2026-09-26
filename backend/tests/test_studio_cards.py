"""ws.regulab Studio's card designs in Semasa: the slide job carries the look, the worker draws it with Studio's own
code in headless Chrome, and a slide Studio calls too full fails with its number instead of shipping clipped.

The drawing itself needs a browser. Those tests run when SEMASA_CHROME names one (a local run); in CI the routing,
the refusals and the bookkeeping are checked with the renderer stubbed."""

import io
import os

import pytest
from fakestore import FakeStore
from PIL import Image

from semasa import ideas, media_generator, studio_cards
from semasa.config import MediaSettings
from semasa.slides import SlideError

SLIDES = [{"title": "Notifikasi *bukan* kelulusan", "points": ["Nombor NOT bermaksud produk telah dinotifikasi."]},
          {"title": "Apa NPRA semak", "points": ["Maklumat pada borang.", "Bukan formula penuh.", "Bukan label."]},
          {"title": "Ingat ini", "points": ["Notifikasi ialah permulaan."]}]


def _settings():
    return MediaSettings(provider="cloudflare", batch=5, max_attempts=3, poll_seconds=0, max_wait_image=1,
                         max_wait_video=1, replicate_token=None, replicate_image_model="a/b",
                         replicate_video_model="c/d", replicate_image_input_key="input_image",
                         replicate_video_input_key="start_image", openai_key=None,
                         openai_base_url="https://api.openai.com/v1", openai_image_model="gpt-image-1",
                         openai_video_model="sora-2", openai_image_size="1024x1024", openai_video_seconds="8",
                         openai_video_size="1280x720")


def _store(meta, attempts=1):
    job = {"id": "s1", "mode": "slides", "type": "image", "status": "processing", "attempts": attempts,
           "created_at": "2099-01-01T00:00:00+00:00",
           "meta": {"stream": "regulab", "bg": "none", "slides": SLIDES, "domain": "kosmetik", **meta}}
    brand = {"regulab": {"website": "www.kkmhalalconsultant.com", "domains": {"kosmetik": "Kosmetik"}}}
    return FakeStore(semasa_settings=[{"key": "brand", "value": brand}], semasa_posts=[], media_generations=[job])


def _run(store):
    return media_generator.process_row(store, store.tables["media_generations"][0], _settings(), {}, None)


@pytest.fixture(autouse=True)
def _uploads(monkeypatch):
    got = {}
    monkeypatch.setattr(media_generator.db, "upload_generated",
                        lambda store, path, data, ct: got.setdefault(path, data) and f"https://cdn/{path}")
    return got


def _jpeg(w=1080, h=1080):
    b = io.BytesIO()
    Image.new("RGB", (w, h), (240, 235, 220)).save(b, "JPEG")
    return b.getvalue()


# --- routing and bookkeeping (no browser) -------------------------------------------------------

def test_a_studio_look_is_drawn_by_studio_and_recorded(monkeypatch, _uploads):
    seen = {}

    def fake(items, **kw):
        seen.update(kw, n=len(items))
        return [_jpeg() for _ in items]

    monkeypatch.setattr(studio_cards, "render", fake)
    store = _store({"look": "era", "citation": "NPRA, Garis Panduan"})
    assert _run(store) is True
    done = store.tables["media_generations"][0]
    assert done["status"] == "done" and done["model"] == "studio-era" and done["meta"]["look"] == "era"
    assert done["meta"]["count"] == 3 and len(_uploads) == 3
    assert seen == {"look": "era", "stream": "regulab", "eyebrow": "Kosmetik", "source": "NPRA, Garis Panduan",
                    "ground": None, "ground_mime": "image/jpeg", "size": None, "n": 3}


def test_no_look_or_an_unknown_one_is_semasas_own_drawing(monkeypatch, _uploads):
    monkeypatch.setattr(studio_cards, "render", lambda *a, **k: pytest.fail("Studio must not draw this"))
    for meta in ({}, {"look": "classic"}, {"look": "neon"}):
        store = _store(meta)
        assert _run(store) is True
        done = store.tables["media_generations"][0]
        assert done["model"] == "slides-v1" and done["meta"]["look"] == "classic"


def test_photo_with_no_picture_is_refused_by_name_before_any_browser(monkeypatch):
    store = _store({"look": "photo"})
    assert _run(store) is False
    job = store.tables["media_generations"][0]
    assert job["status"] == "error" and "Photo look is drawn on a picture" in job["error"]


def test_a_slide_studio_calls_too_full_is_final_and_named(monkeypatch):
    def full(items, **kw):
        raise SlideError("slide 2 (e_explain): The slide is fuller than the card. Shorten it, split it into two "
                         "slides, or pick another look.")
    monkeypatch.setattr(studio_cards, "render", full)
    store = _store({"look": "era"})
    assert _run(store) is False
    job = store.tables["media_generations"][0]
    assert job["status"] == "error" and "slide 2" in job["error"]


def test_a_browser_that_would_not_start_is_tried_again(monkeypatch):
    monkeypatch.setattr(studio_cards, "render", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("chrome crashed")))
    store = _store({"look": "grid"}, attempts=1)
    assert _run(store) is False
    assert store.tables["media_generations"][0]["status"] == "pending"


def test_the_idea_carries_its_look_to_the_slide_job():
    idea = {"id": "i1", "created_by": "u", "brief": {"look": "grid"}}
    post = {"slides": SLIDES, "stream": "regulab", "citation": "", "domain": "kosmetik", "angle": None}
    assert ideas.slide_job(idea, post, "p1")["meta"]["look"] == "grid"
    for brief in ({}, None, {"look": "neon"}, "not a dict"):
        assert ideas.look_of({"brief": brief}) == "classic"


class _Route:
    def __init__(self, path):
        self.request = type("R", (), {"url": studio_cards.ORIGIN + path})()
        self.got = None

    def fulfill(self, status=200, **kw):
        self.got = (status, kw.get("content_type"), kw.get("body"))


@pytest.mark.parametrize("path,status", [("/index.html", 200), ("/studio.js", 200), ("/cards/fonts.css", 200),
                                         ("/cards/logo.png", 200), ("/cards/../../backend/semasa/config.py", 404),
                                         ("/cards/nothing.woff2", 404), ("/elsewhere", 404)])
def test_the_page_origin_serves_only_the_card_files(path, status):
    r = _Route(path)
    studio_cards._serve(r)
    assert r.got[0] == status


def test_the_card_files_are_in_the_checkout():
    assert studio_cards.MODULE.is_file()
    css = (studio_cards.ASSETS / "fonts.css").read_text()
    both = css + (studio_cards.ASSETS / "fragrance-fonts.css").read_text()     # Wangian's Playfair Display and Anton
    for f in (studio_cards.ASSETS / "fonts").glob("*.woff2"):
        assert f"fonts/{f.name}" in both
    for family in ("Poppins", "Instrument Sans", "JetBrains Mono", "Caveat"):
        assert f"font-family: '{family}'" in css


# --- the real drawing (needs a browser: SEMASA_CHROME=/path/to/chrome) ---------------------------

browser = pytest.mark.skipif(not os.environ.get("SEMASA_CHROME"), reason="set SEMASA_CHROME to draw in a real browser")


@browser
@pytest.mark.parametrize("stream,size", [("regulab", (1080, 1080)), ("linkedin", (1080, 1350))])
def test_grid_and_era_draw_every_slide_at_the_streams_size(stream, size):
    for look in ("grid", "era"):
        pics = studio_cards.render(SLIDES, look=look, stream=stream, eyebrow="Kosmetik", source="NPRA")
        assert [Image.open(io.BytesIO(p)).size for p in pics] == [size] * 3


@browser
def test_photo_draws_on_the_picture_and_a_design_shape_is_honoured():
    pics = studio_cards.render(SLIDES[:1], look="photo", stream="regulab", ground=_jpeg(800, 600), size=(1080, 1920))
    assert Image.open(io.BytesIO(pics[0])).size == (1080, 1920)


@browser
def test_too_much_for_the_card_fails_with_the_slide_number_never_clipped():
    long = [SLIDES[0], {"title": "Senarai panjang " * 6,
                        "points": ["Satu ayat yang agak panjang untuk mengisi ruang pada kad ini. " * 3] * 5}]
    with pytest.raises(SlideError, match="slide 2"):
        studio_cards.render(long, look="grid", stream="regulab")
