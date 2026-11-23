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
    assert illustrated.wants("journal", "") and illustrated.wants("journal", "carousel"), "a post's carousel, or the Design tab's"
    assert not illustrated.wants("journal", "poster") and not illustrated.wants("journal", "card")
    assert not illustrated.wants("journal", "threads") and not illustrated.wants("grid", "")
    from semasa import rotation
    assert "journal" not in rotation.LOOK_TURN, "the turn is for posters; every carousel takes Diari (Wan, 23 Nov 2026)"
    assert ideas.DEFAULT_LOOK == "journal"
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


def _luminance(p) -> float:
    def lin(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(p[0]) + 0.7152 * lin(p[1]) + 0.0722 * lin(p[2])


def _contrast(a, b) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


@browser
def test_the_journal_card_is_light_green_with_dark_green_type_that_reads_and_a_picture_in_the_middle():
    slides = [{**SLIDES[1], "art_url": _art_url(), "art_label": "Siapa menjawab?"}]
    [pic] = studio_cards.render(slides, look="journal", stream="regulab", eyebrow="Diari Semasa", final=True, total=10)
    im = Image.open(io.BytesIO(pic)).convert("RGB")
    assert im.size == (1080, 1350)
    corners = [im.getpixel(xy) for xy in ((4, 4), (4, 1345), (1075, 4), (1075, 1345))]
    for c in corners:
        assert c[1] > c[0] and c[1] > c[2], f"every corner is green, never blue: {c}"
        assert _luminance(c) > 0.55, f"and light, not dark: {c}"
    paper = [im.getpixel((x, y)) for x in range(300, 800, 50) for y in range(560, 860, 50)]
    assert sum(1 for p in paper if min(p) > 150) > len(paper) * 0.5, "the cream illustration card sits in the middle"
    dark = sum(1 for x in range(72, 1000, 6) for y in range(120, 330, 6) if max(im.getpixel((x, y))) < 90)
    assert dark > 150, "the headline is dark-green serif type at the top"
    # the type reads on the ground behind it: the darkest ink against the lightest and the deepest corner
    ink = (11, 61, 38)
    assert min(_contrast(ink, c) for c in corners) >= 7, "the headline against the deepest corner"
    assert min(_contrast((15, 74, 44), c) for c in corners) >= 5, "the foot line against the deepest corner"


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


# ---- Diari in the automatic rotation, a green ground, the white cover kept (Wan, 23 Nov 2026) ----------------------------------

def test_a_lone_poster_or_card_never_takes_diari_but_a_carousel_always_does():
    from semasa import rotation
    store = FakeStore(semasa_ideas=[{"stream": "regulab", "brief": {"look": "image"}, "updated_at": "2026-11-23"}])
    assert rotation.next_look(store, "regulab", None, carousel=True) == "journal"
    assert rotation.next_look(store, "regulab", None, carousel=False) == "classic", "a poster has the turn, which starts again"
    every = list(rotation.LOOK_TURN)
    assert rotation.next_look(store, "regulab", every, carousel=False) != "journal"
    assert rotation.next_look(store, "regulab", ["journal"], carousel=True) != "journal", "Wan can hide it in the picker"


def test_a_look_from_the_rotation_is_marked_so_it_can_give_way(monkeypatch):
    from semasa import ideas
    idea = {"id": "i1", "created_by": "u", "brief": {"look": "journal", "look_auto": True}}
    job = ideas.slide_job(idea, {"slides": SLIDES, "stream": "regulab"}, "p1", chosen=("journal", None))
    assert job["meta"]["look"] == "journal" and job["meta"]["look_auto"] is True and job["meta"]["bg"] == "none"
    chosen = ideas.slide_job({"id": "i2", "brief": {"look": "journal"}}, {"slides": SLIDES, "stream": "regulab"}, "p1",
                             chosen=("journal", None))
    assert "look_auto" not in chosen["meta"], "a look Wan picked is never swapped for another"


def _job(meta):
    return {"id": "s1", "mode": "slides", "type": "image", "status": "processing", "attempts": 1,
            "created_at": "2099-01-01T00:00:00+00:00",
            "meta": {"stream": "regulab", "bg": "none", "slides": SLIDES, "look": "journal", "citation": "NPRA", **meta}}


def _run(job, monkeypatch):
    monkeypatch.setattr(media_generator.db, "upload_generated", lambda st, path, data, ct: f"https://cdn/{path}")
    store = FakeStore(semasa_settings=[{"key": "brand", "value": {"regulab": {"website": "www.x.com"}}}], semasa_posts=[],
                      media_generations=[job])
    monkeypatch.setattr(studio_cards, "render", lambda items, **kw: [_paper(1080, 1350) for _ in items])
    ok = media_generator.process_row(store, store.tables["media_generations"][0], _settings(), {}, None)
    return ok, store.tables["media_generations"][0]


def test_an_automatic_diari_with_no_picture_maker_is_drawn_in_the_image_look_not_lost(monkeypatch):
    monkeypatch.setattr(illustrated, "makers", lambda s, store: [])
    ok, row = _run(_job({"look_auto": True}), monkeypatch)
    assert ok is True and row["status"] == "done" and row["meta"]["look"] == "image"
    assert "no picture maker" in row["meta"]["look_fallback"]


def test_a_diari_wan_chose_fails_with_the_reason_instead_of_changing_look(monkeypatch):
    monkeypatch.setattr(illustrated, "makers", lambda s, store: [])
    ok, row = _run(_job({}), monkeypatch)
    assert ok is False and "no picture maker" in str(row.get("error") or "")


def test_a_diari_poster_job_is_drawn_in_the_hand_look_never_without_its_picture(monkeypatch):
    ok, row = _run(_job({"design": "poster", "format": "portrait", "slides": [SLIDES[1]]}), monkeypatch)
    assert ok is True and row["meta"]["look"] == "hand" and "one picture" in row["meta"]["look_fallback"]


def test_the_ws_regulab_set_keeps_the_white_brand_cover_first_and_the_logo_card_last(monkeypatch):
    monkeypatch.setattr(illustrated, "makers", lambda s, store: ["x"])
    monkeypatch.setattr(illustrated, "draw", lambda *a, **k: (_paper(), "x"))
    monkeypatch.setattr(illustrated, "fetch", lambda url: _paper())
    monkeypatch.setattr(illustrated.db, "upload_generated", lambda st, path, data, ct: f"https://cdn/{path}")
    seen = {}
    monkeypatch.setattr(studio_cards, "render",
                        lambda items, **kw: seen.update(items=items) or [_paper(1080, 1350) for _ in items])
    uploaded = {}
    monkeypatch.setattr(media_generator.db, "upload_generated",
                        lambda st, path, data, ct: uploaded.setdefault(path, data) and f"https://cdn/{path}")
    job = _job({"slides": [{"title": "Notifikasi bukan kelulusan", "points": ["Satu fakta penting yang ringkas."],
                            "lead": "Ramai tersalah faham."}, *SLIDES[1:]]})
    store = FakeStore(semasa_settings=[{"key": "brand", "value": {"regulab": {"website": "www.x.com"}}}], semasa_posts=[],
                      media_generations=[job])
    assert media_generator.process_row(store, store.tables["media_generations"][0], _settings(), {}, None) is True
    meta = store.tables["media_generations"][0]["meta"]
    assert meta["look"] == "journal" and meta["cover"] is True and meta["closing_logo"] is True
    assert seen["items"][0].get("art_skip") is True and not seen["items"][0].get("art_url"), "slide 1 is the cover: no picture"
    assert all(it.get("art_url") for it in seen["items"][1:])
    assert meta["count"] == len(seen["items"]) + 1


@browser
def test_the_front_page_the_brand_cover_replaces_draws_without_a_picture_frame_and_without_a_warning():
    [pic] = studio_cards.render([{**SLIDES[0], "art_skip": True}], look="journal", stream="regulab", final=True)
    im = Image.open(io.BytesIO(pic)).convert("RGB")
    assert im.size == (1080, 1350)
    cream = lambda p: all(abs(a - b) < 5 for a, b in zip(p, (239, 235, 224), strict=True))  # noqa: E731
    paper = sum(1 for x in range(100, 980, 20) for y in range(300, 1250, 20) if cream(im.getpixel((x, y))))
    assert paper == 0, "no cream picture card on a front page"


def test_a_design_tab_carousel_takes_diari_with_a_picture_on_every_slide_the_cover_included(monkeypatch):
    # Codex review of #324: the Design tab's Carousel mode must get Diari too; it has no brand cover, so slide 1 gets a picture
    assert illustrated.slides_needing_art(SLIDES, "regulab", covered=False) == [0, 1, 2]
    assert illustrated.slides_needing_art(SLIDES, "regulab", covered=True) == [1, 2]
    monkeypatch.setattr(illustrated, "makers", lambda s, store: ["x"])
    monkeypatch.setattr(illustrated, "draw", lambda *a, **k: (_paper(), "x"))
    monkeypatch.setattr(illustrated, "fetch", lambda url: _paper())
    monkeypatch.setattr(media_generator.db, "upload_generated", lambda st, path, data, ct: f"https://cdn/{path}")
    seen = {}
    monkeypatch.setattr(studio_cards, "render",
                        lambda items, **kw: seen.update(items=items) or [_paper(1080, 1350) for _ in items])
    store = FakeStore(semasa_settings=[{"key": "brand", "value": {"regulab": {"website": "www.x.com"}}}], semasa_posts=[],
                      media_generations=[_job({"design": "carousel", "format": "portrait"})])
    assert media_generator.process_row(store, store.tables["media_generations"][0], _settings(), {}, None) is True
    meta = store.tables["media_generations"][0]["meta"]
    assert meta["look"] == "journal" and "look_fallback" not in meta
    assert len(seen["items"]) == 3 and all(it.get("art_url") for it in seen["items"])
    assert not any(it.get("art_skip") for it in seen["items"])
