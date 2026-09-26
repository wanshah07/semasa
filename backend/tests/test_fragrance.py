"""Wangian: three concepts from the perfume's notes (or a reference ad), each drawn two ways with OUR bottle, one kept.
Badges carry only the claims Wan approved; every word is typeset, never drawn by the image model; nothing is kept
unless Wan keeps it."""

import io
import os

import pytest
from fakestore import FakeStore
from PIL import Image, ImageDraw

from semasa import fragrance as f
from semasa import media_generator
from semasa.config import LLMSettings, MediaSettings
from semasa.providers import Generated

NOIR = {"id": "f1", "brand": "Valorith", "name": "Noir Rush", "concentration": "Extrait de Parfum", "size": "30ml",
        "notes": "Top: bergamot, pink pepper. Heart: rose, oud. Base: amber, vanilla, musk.", "mood": "dark, warm",
        "claims": ["More than 8 hours lasting*"], "footnote": "*Based on 25% oil concentration",
        "bottle_url": "https://ref/bottle.jpg", "logo_url": None}

CONCEPTS = {"designs": [
    {"title": "Amber hour", "why": "Hangat dan gelap, sesuai dengan oud.", "layout": "hero", "side": "left",
     "scene": "A dark wooden table in amber evening light with vanilla pods and rose petals, empty space on the left.",
     "ink": "#FFF4E0", "accent": "#e8c98a", "headline": "Noir Rush", "tagline": "timeless elegant",
     "badges": ["More than 8 hours lasting*", "Long lasting", "Extrait de Parfum", "No.1 in Malaysia"], "callouts": []},
    {"title": "Big words", "why": "Tegas.", "layout": "behind", "side": "left", "scene": "Warm studio backdrop.",
     "ink": "red", "accent": "#abc", "headline": "LUSHER SOFTER WARMER", "tagline": "", "badges": [], "callouts": []},
    {"title": "Notes", "why": "Nota.", "layout": "notes", "side": "right", "scene": "Rose, amber and vanilla on silk.",
     "headline": "NOIR RUSH", "badges": [], "callouts": [{"title": "Warm & woody", "line": "oud and amber"}] * 5},
    {"title": "Broken", "layout": "hero"},
]}


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

    def __init__(self, out=CONCEPTS, sees=None, reads="VALORITH NOIR RUSH EXTRAIT DE PARFUM"):
        self.out, self.sees, self.reads, self.seen, self.looked = out, sees, reads, [], []
        self.s = LLMSettings(provider="openai", api_key="k", base_url="https://x/v1", model="m", timeout=5)

    def chat_json(self, system, user, max_tokens=0, **k):
        self.seen.append(user)
        return self.out

    def describe_image(self, system, prompt, data, mime, max_tokens=900):
        self.looked.append(prompt)
        if "words printed" in prompt:
            return {"reads": self.reads}
        return self.sees


def _png(size=(600, 900), bg=(250, 250, 248), alpha=False):
    img = Image.new("RGBA" if alpha else "RGB", size, (0, 0, 0, 0) if alpha else bg)
    d = ImageDraw.Draw(img)
    d.rectangle((250, 120, 350, 260), fill=(200, 160, 70, 255) if alpha else (200, 160, 70))
    d.rounded_rectangle((150, 250, 450, 820), 40, fill=(30, 30, 40, 255) if alpha else (30, 30, 40))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _jpeg(color=(120, 70, 40)):
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color).save(buf, "JPEG")
    return buf.getvalue()


def _job(**meta):
    return {"id": "g1", "mode": "fragrance", "type": "image", "status": "processing", "attempts": 1,
            "created_at": "2099-01-01T00:00:00+00:00", "meta": {"fragrance_id": "f1", **meta}}


def _store(job, product=NOIR):
    return FakeStore(semasa_fragrances=[dict(product)], media_generations=[job])


@pytest.fixture
def rig(monkeypatch):
    got = {"uploads": {}, "t2i": [], "edit": [], "art": []}
    monkeypatch.setattr(media_generator.db, "upload_generated",
                        lambda store, path, data, ct: got["uploads"].setdefault(path, data) and f"https://cdn/{path}")
    monkeypatch.setattr(f, "fetch_reference", lambda url: (_png(), "image/png", "b.png"))

    class Maker:
        def generate_from_text(self, prompt, options):
            got["t2i"].append(prompt)
            return Generated(_jpeg(), "image/jpeg", "flux")

        def generate(self, kind, url, prompt, options):
            got["edit"].append((url, prompt))
            return Generated(_jpeg((90, 50, 30)), "image/jpeg", "klein")
    monkeypatch.setattr(media_generator, "make_provider", lambda name, s: Maker())
    monkeypatch.setattr(f, "render_art", lambda c, p, size, scene, bottle, logo=None: got["art"].append(
        {"c": c, "size": size, "bottle": bottle is not None}) or _jpeg())
    return got


# --- concepts ------------------------------------------------------------------------------------------------------

def test_concepts_are_written_from_the_notes_and_badges_are_only_approved_claims(rig):
    llm = Writer()
    store = _store(_job(step="concepts"))
    assert f.process(store, store.tables["media_generations"][0], _settings(), llm) is True
    job = store.tables["media_generations"][0]
    m = job["meta"]
    assert job["status"] == "done" and m["step"] == "choose" and len(m["concepts"]) == 3
    one, two, three = m["concepts"]
    # "Long lasting" and "No.1 in Malaysia" were never approved: dropped, whatever the writer answered
    assert one["badges"] == ["More than 8 hours lasting*", "Extrait de Parfum"]
    assert one["headline"] == "NOIR RUSH" and one["tagline"] == "TIMELESS ELEGANT" and one["ink"] == "#FFF4E0"
    assert two["side"] == "center" and two["ink"] == "#fffaf0" and two["accent"] == "#abc"   # "red" is not a hex
    assert three["side"] == "center" and len(three["callouts"]) == 3
    assert "bergamot" in llm.seen[0] and "More than 8 hours lasting*" in llm.seen[0]
    assert "NO bottle" in llm.seen[0] and "Bahasa Indonesia" in llm.seen[0]
    assert m["product"]["name"] == "Noir Rush" and "review" not in m


def test_no_approved_claims_means_the_writer_is_told_to_use_none(rig):
    llm = Writer()
    store = _store(_job(step="concepts"), product={**NOIR, "claims": []})
    f.process(store, store.tables["media_generations"][0], _settings(), llm)
    m = store.tables["media_generations"][0]["meta"]
    assert "none: use no claim badges" in llm.seen[0]
    assert m["concepts"][0]["badges"] == ["Extrait de Parfum"]                   # the concentration is a fact, not a claim


def test_a_reference_ad_is_read_and_leads_the_first_concept(rig):
    llm = Writer(sees={"layout": "behind", "mood": "Warm beige studio, soft shadows", "type": "Heavy condensed caps",
                       "keep": ["Tajuk besar di belakang botol"], "brands": ["Valorith"]})
    store = _store(_job(step="concepts", style_ref={"url": "https://ref/ad.jpg", "path": "u/ad.jpg"}))
    f.process(store, store.tables["media_generations"][0], _settings(), llm)
    m = store.tables["media_generations"][0]["meta"]
    assert m["review"]["layout"] == "behind" and m["review"]["keep"] == ["Tajuk besar di belakang botol"]
    assert "Warm beige studio" in llm.seen[0] and "never its artwork" in llm.seen[0]


def test_an_unread_reference_still_gives_concepts_and_says_why(rig):
    store = _store(_job(step="concepts", style_ref={"url": "https://ref/ad.jpg"}))
    f.process(store, store.tables["media_generations"][0], _settings(), Writer(sees=None))
    m = store.tables["media_generations"][0]["meta"]
    assert "unread" in m["review"] and len(m["concepts"]) == 3


def test_no_writer_is_a_clear_final_error(rig):
    store = _store(_job(step="concepts"))
    assert f.process(store, store.tables["media_generations"][0], _settings(), None) is False
    job = store.tables["media_generations"][0]
    assert job["status"] == "error" and "LLM_API_KEY" in job["error"]


def test_a_deleted_perfume_is_a_clear_final_error(rig):
    store = FakeStore(semasa_fragrances=[], media_generations=[_job(step="concepts")])
    f.process(store, store.tables["media_generations"][0], _settings(), Writer())
    assert store.tables["media_generations"][0]["status"] == "error"
    assert "no longer in the list" in store.tables["media_generations"][0]["error"]


# --- render --------------------------------------------------------------------------------------------------------

def _chosen(**meta):
    c = f.clean_concept(CONCEPTS["designs"][0], NOIR)
    return _job(**{"step": "render", "product": NOIR, "concepts": [c], "pick": 0, **meta})


def test_render_draws_both_ways_with_our_bottle_and_waits_for_wan(rig):
    store = _store(_chosen())
    llm = Writer()
    assert f.process(store, store.tables["media_generations"][0], _settings(), llm) is True
    m = store.tables["media_generations"][0]["meta"]
    assert m["step"] == "pick" and [r["method"] for r in m["renders"]] == ["cutout", "ai_edit"]
    assert m["render_errors"] == {}
    cut, edit = rig["art"]
    assert cut["bottle"] is True and edit["bottle"] is False                    # the AI edit already has the bottle
    assert "No bottles" in rig["t2i"][0] and "no text" in rig["t2i"][0]          # the scene for the cut-out is empty
    assert rig["edit"][0][0] == NOIR["bottle_url"] and "same label text" in rig["edit"][0][1]
    assert m["renders"][1]["label"] == {"reads": "VALORITH NOIR RUSH EXTRAIT DE PARFUM", "ok": True}
    assert cut["size"] == (1080, 1080)
    assert sorted(p.rsplit("-", 2)[1] for p in rig["uploads"]) == ["ai_edit", "cutout"]
    assert store.removed == []


def test_rendering_another_concept_replaces_the_last_round_under_new_names(rig):
    before = [{"method": "cutout", "url": "https://cdn/old", "path": "2026/09/g1-cutout-26100000.jpg"}]
    store = _store(_chosen(renders=before))
    f.process(store, store.tables["media_generations"][0], _settings(), Writer())
    m = store.tables["media_generations"][0]["meta"]
    assert store.removed == [("semasa-generated", ["2026/09/g1-cutout-26100000.jpg"])]
    assert before[0]["path"] not in [r["path"] for r in m["renders"]] and len(m["renders"]) == 2


def test_a_redraw_that_fails_keeps_the_last_round(rig, monkeypatch):
    monkeypatch.setattr(f, "cutout", lambda data: (_ for _ in ()).throw(f.FragranceError("busy background")))
    before = [{"method": "cutout", "url": "https://cdn/old", "path": "2026/09/g1-cutout-26100000.jpg"}]
    store = _store(_chosen(renders=before, methods=["cutout"]))
    assert f.process(store, store.tables["media_generations"][0], _settings(), Writer()) is False
    job = store.tables["media_generations"][0]
    assert job["status"] == "error" and job["meta"]["renders"] == before and store.removed == []


def test_a_wrong_label_is_flagged_not_hidden(rig):
    store = _store(_chosen())
    f.process(store, store.tables["media_generations"][0], _settings(), Writer(reads="VALORTIH NOIR RASH"))
    assert store.tables["media_generations"][0]["meta"]["renders"][1]["label"]["ok"] is False


def test_one_method_failing_leaves_the_other_to_pick(rig, monkeypatch):
    monkeypatch.setattr(f, "cutout", lambda data: (_ for _ in ()).throw(f.FragranceError("busy background")))
    store = _store(_chosen())
    assert f.process(store, store.tables["media_generations"][0], _settings(), Writer()) is True
    m = store.tables["media_generations"][0]["meta"]
    assert [r["method"] for r in m["renders"]] == ["ai_edit"] and "busy background" in m["render_errors"]["cutout"]


def test_edited_words_and_the_portrait_shape_reach_the_artwork(rig):
    store = _store(_chosen(edits={"headline": "NOIR", "tagline": "", "badges": ["No.1"]}, format="portrait",
                           methods=["cutout"]))
    f.process(store, store.tables["media_generations"][0], _settings(), Writer())
    art = rig["art"][0]
    assert art["c"]["headline"] == "NOIR" and art["c"]["tagline"] == "" and art["size"] == (1080, 1350)
    assert art["c"]["badges"] == ["More than 8 hours lasting*", "Extrait de Parfum"]   # badges cannot be edited in
    assert len(rig["art"]) == 1


def test_no_bottle_photo_is_a_clear_final_error(rig):
    store = _store(_chosen(product={**NOIR, "bottle_url": None}))
    f.process(store, store.tables["media_generations"][0], _settings(), Writer())
    job = store.tables["media_generations"][0]
    assert job["status"] == "error" and "no bottle photo" in job["error"]


# --- keep one ------------------------------------------------------------------------------------------------------

def test_saving_keeps_the_chosen_version_and_deletes_the_other(rig):
    renders = [{"method": "cutout", "url": "https://cdn/a", "path": "2026/09/g1-cutout.jpg"},
               {"method": "ai_edit", "url": "https://cdn/b", "path": "2026/09/g1-ai_edit.jpg"}]
    store = _store(_job(step="save", chosen="ai_edit", renders=renders))
    assert f.process(store, store.tables["media_generations"][0], _settings(), None) is True
    job = store.tables["media_generations"][0]
    assert job["meta"]["saved"] is True and job["meta"]["renders"] == [renders[1]]
    assert job["generated_media_url"] == "https://cdn/b"
    assert store.removed == [("semasa-generated", ["2026/09/g1-cutout.jpg"])]


def test_buang_deletes_the_files_the_reference_and_the_job(rig):
    renders = [{"method": "cutout", "path": "2026/09/g1-cutout-1.jpg"}, {"method": "ai_edit", "path": "2026/09/g1-ai_edit-1.jpg"}]
    store = _store(_job(step="discard", renders=renders, style_ref={"url": "u", "path": "u/ad.jpg"}))
    assert f.process(store, store.tables["media_generations"][0], _settings(), None) is True
    assert store.tables["media_generations"] == []
    assert store.removed == [("semasa-generated", [r["path"] for r in renders]), ("semasa-reference", ["u/ad.jpg"])]


def test_unsaved_designs_are_cleared_after_a_week_and_saved_ones_kept():
    old = "2026-09-01T00:00:00+00:00"
    store = FakeStore(media_generations=[
        {"id": "a", "mode": "fragrance", "created_at": old,
         "meta": {"renders": [{"path": "x/a-cutout.jpg"}], "style_ref": {"path": "u/ad.jpg"}}},
        {"id": "b", "mode": "fragrance", "created_at": old, "meta": {"saved": True, "renders": [{"path": "x/b.jpg"}]}},
        {"id": "c", "mode": "fragrance", "created_at": "2099-01-01T00:00:00+00:00", "meta": {}},
        {"id": "d", "mode": "slides", "created_at": old, "meta": {}}])
    from datetime import UTC, datetime
    assert f.purge_unsaved(store, datetime(2026, 9, 26, tzinfo=UTC)) == 1
    assert [r["id"] for r in store.tables["media_generations"]] == ["b", "c", "d"]
    assert ("semasa-generated", ["x/a-cutout.jpg"]) in store.removed and ("semasa-reference", ["u/ad.jpg"]) in store.removed


def test_the_worker_routes_fragrance_jobs_here(monkeypatch):
    seen = []
    monkeypatch.setattr(f, "process", lambda store, row, s, llm=None: seen.append(row["id"]) or True)
    assert media_generator.process_row(None, {"id": "g9", "mode": "fragrance"}, _settings(), {}, None) is True
    assert seen == ["g9"]


# --- the bottle and the page ---------------------------------------------------------------------------------------

def test_a_plain_background_is_cut_away_and_the_bottle_kept():
    out = Image.open(io.BytesIO(f.cutout(_png())))
    assert out.mode == "RGBA" and out.getpixel((0, 0))[3] == 0
    assert out.getpixel((out.width // 2, out.height // 2))[3] == 255
    assert 280 <= out.width <= 330 and 680 <= out.height <= 720                   # cropped to the bottle


def test_a_transparent_png_is_used_as_it_is():
    out = Image.open(io.BytesIO(f.cutout(_png(alpha=True))))
    assert out.getpixel((out.width // 2, out.height // 2))[3] == 255 and out.width <= 310


def test_a_busy_background_is_refused_rather_than_cut_badly():
    img = Image.effect_noise((600, 900), 90).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    with pytest.raises(f.FragranceError, match="busy background"):
        f.cutout(buf.getvalue())


def test_the_page_escapes_words_and_puts_badges_away_from_the_bottle():
    c = f.clean_concept({**CONCEPTS["designs"][0], "side": "right", "headline": "<b>Noir</b> & Rush"}, NOIR)
    html = f.page_html(c, NOIR, (1080, 1080), _jpeg(), f.cutout(_png()), None)
    assert "&lt;B&gt;NOIR&lt;/B&gt;" in html and "<b>" not in html
    assert 'class="hero left"' in html and 'class="badges left"' in html and 'class="bottle right"' in html
    assert "Based on 25% oil concentration" in html                             # an asterisked badge carries its note
    plain = f.page_html({**c, "badges": ["Extrait de Parfum"]}, NOIR, (1080, 1080), _jpeg(), None, None)
    assert "oil concentration" not in plain and 'class="bottle' not in plain


def test_a_real_render_fits_the_words(tmp_path):
    if not os.environ.get("SEMASA_CHROME"):
        pytest.skip("set SEMASA_CHROME to draw in a real browser")
    c = f.clean_concept({**CONCEPTS["designs"][0], "headline": "EXTRAORDINARILY MAGNIFICENT"}, NOIR)
    art = Image.open(io.BytesIO(f.render_art(c, NOIR, (1080, 1350), _jpeg(), f.cutout(_png()))))
    assert art.size == (1080, 1350)
