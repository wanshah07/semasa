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


def test_every_first_slide_takes_a_picture_and_on_the_brand_cover_it_is_the_hooks_illustration():
    # Wan, 23 Nov 2026: "can adjust coverpage by add illustration hook"
    assert illustrated.slides_needing_art(SLIDES, "regulab") == [0, 1, 2], "slide 1 is the brand cover, with its picture"
    assert illustrated.slides_needing_art(SLIDES, "linkedin") == [0, 1, 2]
    many = [{"title": f"S{n}", "points": []} for n in range(14)]
    assert len(illustrated.slides_needing_art(many, "linkedin")) == 14, "every page, however long the set"
    # Codex review on #328: a verse card has no place for a picture, so it is never asked for one
    verse = [*SLIDES, {"title": "Peringatan", "points": [], "ayat": "2:168"}]
    assert illustrated.slides_needing_art(verse, "linkedin") == [0, 1, 2]
    huge = [{"title": f"S{n}", "points": []} for n in range(illustrated.MAX_ART + 1)]
    with pytest.raises(illustrated.ArtError, match="shorten the set"):
        illustrated.with_art(_store(), None, {"id": "j1"}, {}, huge, "linkedin", Llm(None), draw_fn=lambda p: _paper())


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
    assert len(made) == 3 and out[0]["art_url"], "slide 1 is the cover, and its picture is the hook's illustration"
    assert out[1]["art_url"].startswith("data:image/jpeg;base64,") and out[2]["art_url"]
    assert len(meta["art"]) == 3 and len(meta["art_paths"]) == 3
    assert store.tables["media_generations"][0]["meta"]["art"] == meta["art"], "kept on the job before the next picture"
    # a redraw of the same words: nothing is made again
    illustrated.with_art(store, None, row, meta, [dict(x) for x in SLIDES], "regulab", Llm(None), draw_fn=draw,
                         fetch_fn=lambda u: _paper())
    assert len(made) == 3
    # one slide's words change: only that slide gets a new picture
    changed = [dict(x) for x in SLIDES]
    changed[2] = {**changed[2], "title": "Dia mesti ada di Malaysia."}
    illustrated.with_art(store, None, row, meta, changed, "regulab", Llm(None), draw_fn=draw, fetch_fn=lambda u: _paper())
    assert len(made) == 4
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
    with pytest.raises(illustrated.ArtError, match="slide 2"):
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
    assert not illustrated.wants("journal", "threads") and not illustrated.wants("grid", "threads")
    assert not illustrated.wants("grid", "comic")
    # a single card or poster takes a picture too (Wan, 23 Nov 2026: "single card must have illustration in it"), never Diari
    assert illustrated.wants("grid", "poster") and illustrated.wants("hand", "card") and illustrated.wants("classic", "poster")
    assert not illustrated.wants("journal", "poster") and not illustrated.wants("journal", "card")
    # every other Studio look draws one too, in a band at the foot (Wan, 23 Nov 2026); Semasa's own (classic) cannot
    for look in studio_cards.LOOKS:
        assert illustrated.wants(look, "") and illustrated.wants(look, "carousel"), look
    assert illustrated.wants("classic", "") and not illustrated.wants("threads", "")
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
    assert seen["total"] == len(seen["items"]) + 2 and seen["offset"] == 1, "the cover and the logo card count in '04 / 10'"
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
    assert all(it.get("art_url") for it in seen["items"]), "every page has its picture, the hook page too"
    assert not any(it.get("art_skip") for it in seen["items"])
    assert illustrated.art_bytes(seen["items"][0]) and illustrated.art_bytes({}) is None
    assert meta["count"] == len(seen["items"]) + 2, "the brand cover is a picture in front of the first page, then the logo card"
    assert meta["cover_title"], "the cover's own short title is kept on the job"


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
    assert illustrated.slides_needing_art(SLIDES, "regulab", covered=True) == [0, 1, 2]
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


def _bold_art() -> str:
    """A picture no look's own paper resembles: deep blue with orange bars."""
    import base64
    im = Image.new("RGB", (900, 600), (20, 70, 150))
    d = ImageDraw.Draw(im)
    for k in range(0, 900, 90):
        d.rectangle([k, 0, k + 45, 600], fill=(235, 120, 20))
    b = io.BytesIO()
    im.save(b, "JPEG")
    return "data:image/jpeg;base64," + base64.b64encode(b.getvalue()).decode()


@browser
@pytest.mark.parametrize("look", [k for k in studio_cards.LOOKS if k not in ("journal", "photo")])
def test_every_other_look_draws_the_illustration_in_a_band_at_the_foot(look):
    # Wan, 23 Nov 2026: "all carousel slide design ... must have illustration but no need to have illustration at the centre
    # page and no need to have same size with diary"
    art = _bold_art()
    drawn = studio_cards.render([{**SLIDES[1], "art_url": art}, {**SLIDES[2], "art_url": art}], look=look, stream="regulab",
                                final=True)
    assert len(drawn) == 2
    for pic in drawn:
        im = Image.open(io.BytesIO(pic)).convert("RGB")
        assert im.size == (1080, 1350)
        w, h = im.size
        band = [(x, y) for x in range(160, w - 160, 40) for y in range(int(h * 0.70), int(h * 0.92), 40)]
        blue_or_orange = sum(1 for xy in band if (im.getpixel(xy)[2] > 120 > im.getpixel(xy)[0])
                             or (im.getpixel(xy)[0] > 200 and im.getpixel(xy)[2] < 80))
        assert blue_or_orange > len(band) * 0.6, f"{look}: the picture fills the band at the foot"


@browser
def test_a_picture_that_cannot_be_read_leaves_the_slide_drawn_without_it():
    broken = [{**SLIDES[1], "art_url": "data:image/jpeg;base64,AAAA"}]
    [pic] = studio_cards.render(broken, look="hand", stream="regulab", final=True)
    assert Image.open(io.BytesIO(pic)).size == (1080, 1350)


def _cut_png() -> bytes:
    """A cut-out stand-in: a blue block with orange bars inside a fully transparent margin."""
    im = Image.new("RGBA", (900, 600), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([150, 100, 750, 500], fill=(20, 70, 150, 255))
    for k in range(150, 750, 90):
        d.rectangle([k, 100, k + 45, 500], fill=(235, 120, 20, 255))
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


def test_the_brand_cover_carries_a_short_title_and_the_hooks_cutout_at_the_foot_with_no_card_behind_it():
    from semasa import carousel
    title = "Mikrobiom kulit kepala"
    plain = Image.open(io.BytesIO(carousel.cover_jpeg(title, "", "", size=(1080, 1350)))).convert("RGB")
    drawn = Image.open(io.BytesIO(carousel.cover_jpeg(title, "", "", size=(1080, 1350), art=_cut_png()))).convert("RGB")
    assert plain.size == drawn.size == (1080, 1350)
    band = [(x, y) for x in range(380, 700, 20) for y in range(1010, 1230, 20)]
    coloured = sum(1 for xy in band if (drawn.getpixel(xy)[2] > 120 > drawn.getpixel(xy)[0])
                   or (drawn.getpixel(xy)[0] > 200 and drawn.getpixel(xy)[2] < 80))
    assert coloured > len(band) * 0.6, "the cut-out stands at the foot"
    assert not any((plain.getpixel(xy)[2] > 120 > plain.getpixel(xy)[0]) for xy in band), "and the plain cover has none"
    # no card: the margin of the cut-out is transparent, so the cover's own white shows beside it
    assert min(drawn.getpixel((130, 1120))) > 225 and min(drawn.getpixel((950, 1120))) > 225
    ink = sum(1 for x in range(100, 980, 10) for y in range(400, 700, 10) if max(drawn.getpixel((x, y))) < 60)
    assert ink > 100, "the short title is drawn above it"
    # a film's tall frame keeps its own layout: no band
    tall = Image.open(io.BytesIO(carousel.cover_jpeg(title, "", "", size=(1080, 1920), art=_cut_png()))).convert("RGB")
    assert not any(tall.getpixel(xy)[2] > 120 > tall.getpixel(xy)[0] for xy in [(x, y) for x in range(200, 880, 60)
                                                                                for y in range(1500, 1800, 60)])


def _white_page_drawing() -> bytes:
    im = Image.new("RGB", (900, 600), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.ellipse([300, 150, 600, 450], outline=(20, 20, 20), width=6, fill=(255, 255, 255))      # white INSIDE the drawing
    d.ellipse([380, 230, 420, 270], fill=(20, 20, 20))
    b = io.BytesIO()
    im.save(b, "JPEG")
    return b.getvalue()


def test_a_cutout_takes_the_white_page_away_and_keeps_the_white_inside_the_drawing():
    out = illustrated.cutout(_white_page_drawing())
    im = Image.open(io.BytesIO(out))
    assert im.mode == "RGBA" and im.width < 400, "cropped to the drawing"
    assert im.getpixel((1, 1))[3] == 0, "the page is transparent"
    assert im.getpixel((im.width // 2, im.height // 2 + 40))[3] == 255, "the inside of the drawing is kept"
    with pytest.raises(illustrated.ArtError, match="no plain page"):
        illustrated.cutout(_paper())                                     # a picture with no white page round it


def test_the_cover_picture_is_the_whole_drawing_made_once_and_kept(monkeypatch):
    monkeypatch.setattr(illustrated.db, "upload_generated", lambda st, path, data, ct: f"https://cdn/{path}")
    store, meta, made = _store(), {}, []

    def draw(prompt):
        made.append(prompt)
        return _white_page_drawing()

    row = store.tables["media_generations"][0]
    item = {"title": "Aku baca kajian 12 minggu ni.", "points": []}
    first = illustrated.cover_art(store, None, row, meta, item, "regulab", Llm(None), draw_fn=draw)
    assert Image.open(io.BytesIO(first)).mode == "RGB" and len(made) == 1, "no cut-out any more (Wan revoked it, 23 Nov 2026)"
    assert "pure white page" not in made[0] and "Scene:" in made[0], "the picture is drawn as it is for every slide"
    again = illustrated.cover_art(store, None, row, meta, item, "regulab", Llm(None), draw_fn=draw, fetch_fn=lambda u: first)
    assert again == first and len(made) == 1, "kept on the job: a redraw pays for nothing"
    assert any(p.endswith("-cover.jpg") for p in meta["art_paths"])
    def broken(prompt):
        raise RuntimeError("the maker said no")

    with pytest.raises(illustrated.ArtError, match="cover"):
        illustrated.cover_art(_store(), None, {"id": "j1"}, {}, {"title": "Lain", "points": []}, "regulab", Llm(None),
                              draw_fn=broken)


def test_the_cover_title_is_short_and_never_invents(monkeypatch):
    from semasa import carousel
    hook = "Aku: esok lah aku fikir pasal mikrobiom kulit kepala. Lepas tu aku: baca kajian 12 minggu ni."

    class Said:
        def __init__(self, title):
            self.title = title

        def chat_json(self, system, user, max_tokens=0):
            return {"title": self.title}

    assert carousel.short_title(Said("Kajian *mikrobiom* kulit kepala"), hook) == "Kajian *mikrobiom* kulit kepala"
    first = "Aku: esok lah aku fikir pasal mikrobiom kulit kepala"
    many = "Aku esok fikir pasal mikrobiom kulit kepala lepas tu baca kajian " + "kajian " * 7
    long = carousel.short_title(Said(many), hook)
    assert long == first, "a too-long answer falls back to the first WHOLE sentence"
    assert carousel.short_title(None, hook) == first
    assert carousel.short_title(Said("Kajian"), hook) == first, "a fragment is refused"
    # a hook of 12 words or fewer is the cover title whole: never a few words cut from it (Wan, 23 Nov 2026: "ayat lengkap")
    whole = "Perasaan tu bila kau dah submit borang NPRA tapi tak tahu status"
    assert carousel.short_title(None, whole) == whole
    blocked = carousel.short_title(Said("Produk ini dijamin lulus NPRA"), hook)
    assert "dijamin" not in blocked, "a title that breaks a blocking rule is dropped"
    assert carousel.short_title(Said("x"), "Tajuk pendek sahaja") == "Tajuk pendek sahaja", "a short hook is the title"


def _bold_art_bytes() -> bytes:
    import base64
    return base64.b64decode(_bold_art().split(",", 1)[1])


def test_semasas_own_look_gets_the_cutout_in_a_band_at_the_foot():
    from semasa import slides
    full = (1080, 1350)
    band = round(full[1] * illustrated.ART_BAND)
    card = slides.render([{"title": "Satu tajuk", "points": ["Satu perkara."]}], stream="regulab",
                         size=(full[0], full[1] - band))[0]
    out = Image.open(io.BytesIO(illustrated.compose_band(card, _cut_png(), full))).convert("RGB")
    assert out.size == full
    zone = [(x, y) for x in range(380, 700, 20) for y in range(full[1] - band + 40, full[1] - 60, 20)]
    coloured = sum(1 for xy in zone if (out.getpixel(xy)[2] > 120 > out.getpixel(xy)[0])
                   or (out.getpixel(xy)[0] > 200 and out.getpixel(xy)[2] < 80))
    assert coloured > len(zone) * 0.6, "the cut-out stands on the band"


def _poster_job(job_id: str, look: str = "hand") -> dict:
    return {"id": job_id, "mode": "slides", "type": "image", "status": "processing", "attempts": 1,
            "created_at": "2099-01-01T00:00:00+00:00",
            "meta": {"stream": "regulab", "bg": "none", "slides": [SLIDES[1]], "look": look, "design": "poster",
                     "format": "portrait", "citation": "NPRA"}}


def test_a_single_poster_gets_a_picture_in_its_look(monkeypatch):
    kept, seen = {}, {}
    monkeypatch.setattr(illustrated, "makers", lambda s, store: ["x"])
    monkeypatch.setattr(illustrated, "draw", lambda *a, **k: (_white_page_drawing(), "x"))
    monkeypatch.setattr(illustrated, "fetch", lambda url: kept.get(url))
    monkeypatch.setattr(media_generator.db, "upload_generated",
                        lambda st, path, data, ct: kept.setdefault(f"https://cdn/{path}", data) and f"https://cdn/{path}")
    monkeypatch.setattr(studio_cards, "render",
                        lambda items, **kw: seen.update(items=items, look=kw["look"]) or [_paper(1080, 1350)])
    store = FakeStore(semasa_settings=[{"key": "brand", "value": {"regulab": {"website": "www.x.com"}}}], semasa_posts=[],
                      media_generations=[_poster_job("s1")])
    assert media_generator.process_row(store, store.tables["media_generations"][0], _settings(), {}, None) is True
    assert seen["look"] == "hand" and len(seen["items"]) == 1
    assert seen["items"][0]["art_url"].startswith("data:image/jpeg;base64,"), "the card carries its own picture"


def test_a_poster_with_no_picture_maker_is_still_drawn_without_the_band(monkeypatch):
    monkeypatch.setattr(illustrated, "makers", lambda s, store: [])
    monkeypatch.setattr(studio_cards, "render", lambda items, **kw: [_paper(1080, 1350)])
    monkeypatch.setattr(media_generator.db, "upload_generated", lambda st, path, data, ct: f"https://cdn/{path}")
    store = FakeStore(semasa_settings=[{"key": "brand", "value": {"regulab": {"website": "www.x.com"}}}], semasa_posts=[],
                      media_generations=[_poster_job("s2")])
    assert media_generator.process_row(store, store.tables["media_generations"][0], _settings(), {}, None) is True
    assert "no picture maker" in store.tables["media_generations"][0]["meta"].get("art_missing", "")


def test_a_studio_look_that_overflows_falls_back_to_classic_and_keeps_its_pictures(monkeypatch):
    # Codex review of #333: the classic fallback used to drop the illustrations the Studio look had already made
    from semasa import slides
    monkeypatch.setattr(illustrated, "makers", lambda s, store: ["x"])
    monkeypatch.setattr(illustrated, "draw", lambda *a, **k: (_white_page_drawing(), "x"))
    monkeypatch.setattr(illustrated, "fetch", lambda url: _white_page_drawing())
    banded = []
    monkeypatch.setattr(illustrated, "compose_band", lambda page, art, size: banded.append(size) or page)
    monkeypatch.setattr(media_generator.db, "upload_generated", lambda st, path, data, ct: f"https://cdn/{path}")

    def too_full(items, **kw):
        raise slides.SlideError("slide 2: The slide is fuller than the card: shorten a line.")
    monkeypatch.setattr(studio_cards, "render", too_full)
    monkeypatch.setattr(slides, "render", lambda words, **kw: [_paper(1080, 1350 - 400) for _ in words])
    store = FakeStore(semasa_settings=[{"key": "brand", "value": {"regulab": {"website": "www.x.com"}}}], semasa_posts=[],
                      media_generations=[_job({"look": "image"})])
    assert media_generator.process_row(store, store.tables["media_generations"][0], _settings(), {}, None) is True
    meta = store.tables["media_generations"][0]["meta"]
    assert meta["look"] == "classic" and "fuller than the card" in meta["look_fallback"]
    assert len(banded) >= len(SLIDES), "every fallback page gets its illustration band"
