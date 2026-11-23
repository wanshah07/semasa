"""The Journal look (Wan, 23 Nov 2026: "try develop carousel like this, each slide got illustration in the middle related to
content"): a hand-inked picture per slide, made once and kept on the job, drawn on a deep-blue card with an editorial serif."""

import io
import os

import pytest
from fakestore import FakeStore
from PIL import Image, ImageDraw

from semasa import carousel, illustrated, media_generator, studio_cards
from semasa.config import MediaSettings
from semasa.slides import SlideError

SLIDES = [
    {"title": "Notifikasi kosmetik bukan kelulusan produk.", "points": [], "lead": "Ramai ingat NPRA sudah semak produk mereka.",
     "note": "Tapi ada satu perkara yang ramai tak perasan."},
    {"title": "Setiap produk ada orang bertanggungjawab.", "points": [], "lead": "Pemegang notifikasi menjawab untuk produknya.",
     "note": "Siapa orang itu?"},
    {"title": "Dia dalam syarikat Malaysia.", "points": [], "lead": "Syarikat berdaftar di Malaysia memegang notifikasi.",
     "note": "Itulah syaratnya."},
]


def _paper(w=900, h=600) -> bytes:
    im = Image.new("RGB", (w, h), (239, 235, 224))
    d = ImageDraw.Draw(im)
    for k in range(0, w, 60):
        d.line([(k, 40), (w - k, h - 40)], fill=(40, 40, 60), width=3)
    d.ellipse([300, 150, 600, 450], outline=(24, 46, 178), width=8)
    b = io.BytesIO()
    im.save(b, "JPEG")
    return b.getvalue()


def _store():
    job = {"id": "j1", "mode": "slides", "type": "image", "status": "processing", "attempts": 1, "meta": {}}
    return FakeStore(media_generations=[job], semasa_settings=[], semasa_posts=[])


class Llm:
    def __init__(self, answer):
        self.answer, self.seen = answer, []

    def chat_json(self, system, user, **kw):
        self.seen.append((system, user))
        return self.answer


def test_a_picture_belongs_to_a_slides_words():
    a = illustrated.key_of(SLIDES[0])
    assert a == illustrated.key_of(dict(SLIDES[0]))
    assert a != illustrated.key_of({**SLIDES[0], "title": "Notifikasi kosmetik ialah permulaan."})
    assert a != illustrated.key_of({**SLIDES[0], "lead": "Lain."})


def test_the_brand_cover_takes_no_picture_but_a_linkedin_first_slide_does():
    assert illustrated.slides_needing_art(SLIDES, "regulab") == [1, 2], "slide 1 becomes the white brand cover"
    assert illustrated.slides_needing_art(SLIDES, "linkedin") == [0, 1, 2]
    many = [{"title": f"S{n}", "points": []} for n in range(14)]
    assert len(illustrated.slides_needing_art(many, "linkedin")) == illustrated.MAX_ART


def test_the_scenes_are_planned_together_and_a_failed_plan_never_stops_the_set():
    llm = Llm({"slides": [{"n": 1, "scene": "A woman reads a form at a desk.", "label": "Borang NPRA"},
                          {"n": 2, "scene": "A shopkeeper points to a shelf.", "label": "Siapa menjawab?"}]})
    got = illustrated.plan(llm, SLIDES, [1, 2], "regulab")
    assert got[1]["scene"].startswith("A woman") and got[2]["label"] == "Siapa menjawab?"
    assert "Malaysian Malay" in llm.seen[0][0] and "never any writing" in llm.seen[0][0]
    for dead in (Llm(None), Llm({"slides": "x"}), None):
        got = illustrated.plan(dead, SLIDES, [1, 2], "regulab")
        assert set(got) == {1, 2} and got[1]["scene"] and got[1]["label"] == ""


def test_a_label_that_breaks_a_rule_is_left_off_and_the_prompt_forbids_every_letter():
    assert illustrated.safe_label("Siapa menjawab?", "regulab", "bm") == "Siapa menjawab?"
    assert illustrated.safe_label("Hubungi kami di www.contoh.com", "regulab", "bm") == ""
    assert illustrated.safe_label("satu dua tiga empat lima enam", "regulab", "bm") == ""
    assert "no letters" in illustrated.prompt_of("a scene") and "Scene: a scene" in illustrated.prompt_of("a scene")


def test_each_picture_is_made_once_and_kept_so_a_redraw_pays_for_nothing(monkeypatch):
    store, meta, made = _store(), {}, []
    monkeypatch.setattr(illustrated.db, "upload_generated", lambda st, path, data, ct: f"https://cdn/{path}")

    def draw(prompt):
        made.append(prompt)
        return _paper()

    row = store.tables["media_generations"][0]
    items = [dict(x) for x in SLIDES]
    out = illustrated.with_art(store, None, row, meta, items, "regulab", Llm(None), draw_fn=draw, fetch_fn=lambda u: _paper())
    assert len(made) == 2 and "art_url" not in out[0], "slide 1 is the cover"
    assert out[1]["art_url"].startswith("data:image/jpeg;base64,") and out[2]["art_url"]
    assert len(meta["art"]) == 2 and len(meta["art_paths"]) == 2
    assert store.tables["media_generations"][0]["meta"]["art"] == meta["art"], "kept on the job before the next picture"
    # a redraw of the same words: nothing is made again
    illustrated.with_art(store, None, row, meta, [dict(x) for x in SLIDES], "regulab", Llm(None), draw_fn=draw,
                         fetch_fn=lambda u: _paper())
    assert len(made) == 2
    # one slide's words change: only that slide gets a new picture
    changed = [dict(x) for x in SLIDES]
    changed[2] = {**changed[2], "title": "Dia mesti ada di Malaysia."}
    illustrated.with_art(store, None, row, meta, changed, "regulab", Llm(None), draw_fn=draw, fetch_fn=lambda u: _paper())
    assert len(made) == 3
    stale = illustrated.stale_paths(meta, changed, "regulab")
    assert len(stale) == 1 and "art03" in stale[0], "the old third picture is left to be removed"


def test_a_failure_part_way_keeps_what_was_made(monkeypatch):
    store, meta = _store(), {}
    monkeypatch.setattr(illustrated.db, "upload_generated", lambda st, path, data, ct: f"https://cdn/{path}")
    calls = []

    def draw(prompt):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("quota")
        return _paper()

    row = store.tables["media_generations"][0]
    with pytest.raises(illustrated.ArtError, match="slide 3"):
        illustrated.with_art(store, None, row, meta, [dict(x) for x in SLIDES], "regulab", Llm(None), draw_fn=draw)
    assert len(meta["art"]) == 1, "the first picture is kept, so the retry pays only for the rest"


def test_no_picture_maker_is_a_clear_refusal(monkeypatch):
    monkeypatch.setattr(illustrated, "makers", lambda s, store: [])
    store = _store()
    with pytest.raises(illustrated.ArtError, match="no picture maker"):
        row = store.tables["media_generations"][0]
        illustrated.with_art(store, None, row, {}, [dict(x) for x in SLIDES], "regulab", Llm(None))


def test_the_look_is_known_to_every_list_and_only_a_carousel_draws_pictures():
    from semasa import ideas
    assert "journal" in studio_cards.LOOKS and "journal" in ideas.LOOKS and "journal" in ideas.OWN_PICTURE_ONLY
    assert illustrated.wants("journal", "") and not illustrated.wants("journal", "poster") and not illustrated.wants("grid", "")
    assert "journal" not in __import__("semasa.rotation", fromlist=["LOOK_TURN"]).LOOK_TURN, "costs credits: only when chosen"
    assert "JOURNAL LOOK" in ideas.JOURNAL_RULES and carousel.has_logo_card("regulab", 3)


def _settings():
    return MediaSettings(provider="cloudflare", batch=5, max_attempts=3, poll_seconds=0, max_wait_image=1, max_wait_video=1,
                         replicate_token=None, replicate_image_model="a/b", replicate_video_model="c/d",
                         replicate_image_input_key="input_image", replicate_video_input_key="start_image", openai_key=None,
                         openai_base_url="https://api.openai.com/v1", openai_image_model="gpt-image-1",
                         openai_video_model="sora-2", openai_image_size="1024x1024", openai_video_seconds="8",
                         openai_video_size="1280x720")


def test_the_slide_job_draws_the_pictures_then_the_card_and_records_them(monkeypatch):
    seen = {}

    def render(items, **kw):
        seen.update(kw, items=items)
        return [_paper(1080, 1350) for _ in items]

    monkeypatch.setattr(studio_cards, "render", render)
    monkeypatch.setattr(illustrated, "with_art", lambda store, s, row, meta, items, stream, llm=None, **k: (
        meta.update(art={"k": {"path": "p/art01.jpg"}}, art_paths=["p/art01.jpg"]) or
        [{**it, "art_url": "data:image/jpeg;base64,AAAA"} for it in items]))
    monkeypatch.setattr(media_generator.db, "upload_generated", lambda st, path, data, ct: f"https://cdn/{path}")
    job = {"id": "s1", "mode": "slides", "type": "image", "status": "processing", "attempts": 1,
           "created_at": "2099-01-01T00:00:00+00:00",
           "meta": {"stream": "regulab", "bg": "none", "slides": SLIDES, "look": "journal", "citation": "NPRA"}}
    store = FakeStore(semasa_settings=[{"key": "brand", "value": {"regulab": {"website": "www.x.com"}}}], semasa_posts=[],
                      media_generations=[job])
    assert media_generator.process_row(store, store.tables["media_generations"][0], _settings(), {}, None) is True
    assert seen["look"] == "journal" and seen["final"] is True
    assert seen["total"] == len(seen["items"]) + 1, "the closing logo card counts in '04 / 10'"
    assert all(it.get("art_url") for it in seen["items"])
    meta = store.tables["media_generations"][0]["meta"]
    assert meta["look"] == "journal" and meta["art_paths"] == ["p/art01.jpg"]


# --- the real drawing (needs a browser: SEMASA_CHROME=/path/to/chrome) ---------------------------
browser = pytest.mark.skipif(not os.environ.get("SEMASA_CHROME"), reason="set SEMASA_CHROME to draw in a real browser")


def _art_url() -> str:
    import base64
    return "data:image/jpeg;base64," + base64.b64encode(_paper()).decode()


@browser
def test_the_journal_card_has_the_references_ground_and_a_picture_in_the_middle():
    slides = [{**SLIDES[1], "art_url": _art_url(), "art_label": "Siapa menjawab?"}]
    [pic] = studio_cards.render(slides, look="journal", stream="regulab", eyebrow="Diari Semasa", final=True, total=10)
    im = Image.open(io.BytesIO(pic)).convert("RGB")
    assert im.size == (1080, 1350)
    tl, bl, tr, br = im.getpixel((4, 4)), im.getpixel((4, 1345)), im.getpixel((1075, 4)), im.getpixel((1075, 1345))
    assert max(tl) < 70 and max(br) < 70, "navy in the top-left and bottom-right corners"
    assert bl[2] > 110 and tr[2] > 130, "royal blue in the other two"
    paper = [im.getpixel((x, y)) for x in range(300, 800, 50) for y in range(560, 860, 50)]
    assert sum(1 for p in paper if min(p) > 150) > len(paper) * 0.5, "the cream illustration card sits in the middle"
    white = sum(1 for x in range(72, 1000, 6) for y in range(120, 330, 6) if min(im.getpixel((x, y))) > 235)
    assert white > 150, "the headline is white serif type at the top"


@browser
def test_a_posted_journal_slide_without_its_picture_is_refused_but_the_preview_shows_a_placeholder():
    with pytest.raises(SlideError, match="No illustration"):
        studio_cards.render([SLIDES[1]], look="journal", stream="regulab", final=True)
    [pic] = studio_cards.render([SLIDES[1]], look="journal", stream="regulab")
    assert Image.open(io.BytesIO(pic)).size == (1080, 1350)


@browser
def test_a_slide_with_too_many_words_for_its_picture_says_so():
    long = {"title": "Satu tajuk yang sangat panjang " * 6, "points": [], "lead": "Ayat panjang sekali. " * 16,
            "note": "Satu baris penutup yang juga terlalu panjang untuk muat di bawah. " * 3, "art_url": _art_url()}
    with pytest.raises(SlideError, match="fuller than the card"):
        studio_cards.render([long], look="journal", stream="regulab", final=True)
