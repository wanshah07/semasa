"""Carousel slides: the renderer, the slide job in the media worker, the writer's slides, the
publisher's picture list, and the SQL that keeps 005 and 006 in step."""

import io
import re
from pathlib import Path

import pytest
from fakestore import FakeStore
from PIL import Image

from semasa import compliance, db, ideas, media_generator, publisher, slides
from semasa.config import MediaSettings

ROOT = Path(__file__).resolve().parents[2]
GOOD = [{"title": "Notifikasi *bukan* kelulusan", "points": []},
        {"title": "Apa NPRA semak", "points": ["Dokumen PIF selepas produk dipasarkan.", "Label dan tuntutan."]},
        {"title": "Ringkasnya", "points": ["Notifikasi ialah pendaftaran, bukan pengesahan keselamatan."]}]


def _img(b: bytes) -> Image.Image:
    return Image.open(io.BytesIO(b)).convert("RGB")


# --- the renderer ---------------------------------------------------------------------

def test_sizes_count_and_format_per_stream():
    reg = slides.render(GOOD, stream="regulab", website="www.kkmhalalconsultant.com", source="NPRA")
    li = slides.render(GOOD, stream="linkedin", source="EC 1223/2009")
    assert len(reg) == len(li) == 3
    assert all(_img(b).size == (1080, 1080) for b in reg)
    assert all(_img(b).size == (1080, 1350) for b in li)
    assert all(b[:2] == b"\xff\xd8" for b in reg + li)


def test_rendering_is_deterministic():
    assert slides.render(GOOD) == slides.render(GOOD)


def _ink_outside_safe_area(img: Image.Image, blank: Image.Image, edge: int = 60) -> int:
    """Pixels that differ from the same card drawn without words, inside the outer `edge` band."""
    w, h = img.size
    a, b = img.load(), blank.load()
    n = 0
    for y in range(h):
        for x in range(w):
            if (x < edge or x >= w - edge or y < edge or y >= h - edge) and a[x, y] != b[x, y]:
                n += 1
    return n


def test_long_tokens_and_long_text_stay_inside_the_card():
    """Studio's longfit lesson: diff the card against the same card carrying one short word; nothing
    may reach the edge band. Both go through the same JPEG encoder, so a flat 8x8 block that holds
    only background encodes identically in both and cannot itself differ."""
    long = [{"title": "Rujukan NPRA.600-1/9/13(13)Jld.2),NOT221001118K,MAL19962457T,10.1007/s11356-026-38214-9",
             "points": ["x" * 300, "Direktif Bilangan 19 Tahun 2026 " * 6]}]
    for stream in ("regulab", "linkedin"):
        img = _img(slides.render(long, stream=stream)[0])
        ref = _img(slides.render([{"title": "a", "points": []}], stream=stream)[0])
        assert _ink_outside_safe_area(img, ref) == 0, stream
        assert img.tobytes() != ref.tobytes()


def test_a_word_is_never_cut_too_long_is_an_error_naming_the_slide():
    too_long = GOOD[:1] + [{"title": "Panjang", "points": ["perkataan " * 80] * 5}]
    with pytest.raises(slides.SlideError, match=r"slide 2: too long"):
        slides.render(too_long)


def test_hard_split_only_splits_what_does_not_fit():
    f = slides._font(slides.BODY, 40)
    assert slides.hard_split("MAL19962457T", f, 900) == ["MAL19962457T"]
    parts = slides.hard_split("NOT221001118K" * 8, f, 200)
    assert len(parts) > 1 and "".join(parts) == "NOT221001118K" * 8
    assert all(f.getlength(p) <= 200 for p in parts)


def test_emphasis_markers_never_reach_the_picture():
    runs = slides.tokens("Notifikasi *bukan* kelulusan, harga 5 * 3")
    assert [r.text for r in runs] == ["Notifikasi", "bukan", "kelulusan,", "harga", "5", "*", "3"]
    assert [r.emph for r in runs][:3] == [False, True, False]
    assert slides.strip_emphasis("*a* b") == "a b"


def test_linkedin_never_draws_the_website_and_regulab_does():
    one = [{"title": "T", "points": []}]
    with_site = _img(slides.render(one, stream="regulab", website="www.kkmhalalconsultant.com")[0])
    without = _img(slides.render(one, stream="regulab", website="")[0])
    assert with_site.tobytes() != without.tobytes()
    li_site = slides.render(one, stream="linkedin", website="www.kkmhalalconsultant.com")
    li_none = slides.render(one, stream="linkedin", website="")
    assert li_site == li_none


def test_source_line_is_on_the_closing_slide_only():
    with_src = slides.render(GOOD, source="NPRA, Guidelines for Control of Cosmetic Products in Malaysia")
    no_src = slides.render(GOOD, source="")
    assert with_src[0] == no_src[0] and with_src[1] == no_src[1]
    assert with_src[2] != no_src[2]


def test_a_ground_is_drawn_under_a_scrim():
    photo = Image.new("RGB", (1600, 900), (40, 160, 90))
    buf = io.BytesIO()
    photo.save(buf, "PNG")
    out = _img(slides.render(GOOD[:1], ground=buf.getvalue())[0])
    r, g, b = out.getpixel((540, 20))
    assert g > r and g > b and g < 160                   # the photo shows through, darkened
    with pytest.raises(slides.SlideError, match="background picture"):
        slides.render(GOOD[:1], ground=b"not a picture")


def test_empty_slides_are_an_error_and_normalise_matches_the_scan():
    with pytest.raises(slides.SlideError, match="no slides"):
        slides.render([{"title": " ", "points": [""]}])
    raw = [{"title": " A ", "points": "x\n\ny\n", "body": None}, {"title": None, "points": []}, "B", 7]
    assert slides.normalise(raw) == [{"title": "A", "points": ["x", "y"]}, {"title": "B", "points": []}]
    assert slides.same_words(raw, [{"title": "A", "points": ["x", "y"]}, {"title": "B"}])


# --- the slide job ----------------------------------------------------------------------

def _settings():
    return MediaSettings(provider="replicate", batch=5, max_attempts=3, poll_seconds=0, max_wait_image=1,
                         max_wait_video=1, replicate_token=None, replicate_image_model="a/b",
                         replicate_video_model="c/d", replicate_image_input_key="input_image",
                         replicate_video_input_key="start_image", openai_key=None,
                         openai_base_url="https://api.openai.com/v1", openai_image_model="gpt-image-1",
                         openai_video_model="sora-2", openai_image_size="1024x1024", openai_video_seconds="8",
                         openai_video_size="1280x720")


def _job_store(post_status="draft", media_ids=None, extra_media=None):
    return FakeStore(
        semasa_settings=[{"key": "brand", "value": {"regulab": {"website": "www.kkmhalalconsultant.com",
                                                               "domains": {"halal_my": "Halal Malaysia"}}}}],
        semasa_posts=[{"id": "p1", "status": post_status, "media_ids": media_ids or []}],
        media_generations=[{"id": "s1", "mode": "slides", "type": "image", "status": "processing", "attempts": 1,
                            "post_id": "p1", "meta": {"slides": GOOD, "stream": "regulab", "citation": "JAKIM",
                                                      "domain": "halal_my", "bg": "none"}}] + (extra_media or []))


def test_slide_job_draws_uploads_and_replaces_the_old_set(monkeypatch):
    uploads = {}
    monkeypatch.setattr(media_generator.db, "upload_generated",
                        lambda store, path, data, ct: uploads.setdefault(path, (data, ct)) and f"https://cdn/{path}")
    old = {"id": "old", "mode": "slides", "type": "image", "status": "done"}
    pic = {"id": "pic", "mode": "prompt", "type": "image", "status": "done"}
    store = _job_store(media_ids=["pic", "old"], extra_media=[old, pic])
    row = store.tables["media_generations"][0]
    assert media_generator.process_row(store, row, _settings(), {}) is True     # no provider, no token needed
    done = store.tables["media_generations"][0]
    assert done["status"] == "done" and done["provider"] == "semasa" and done["model"] == "slides-v1"
    assert done["meta"]["count"] == 3 and len(done["meta"]["slide_urls"]) == 3
    assert done["generated_media_url"] == done["meta"]["slide_urls"][0]
    assert done["meta"]["slides"] == compliance.normalise_slides(GOOD)
    assert all(ct == "image/jpeg" for _, ct in uploads.values())
    assert [p.rsplit("/", 1)[1] for p in uploads] == ["s1-slide01.jpg", "s1-slide02.jpg", "s1-slide03.jpg"]
    assert store.tables["semasa_posts"][0]["media_ids"] == ["pic", "s1"]         # the old set replaced in place


def test_slide_job_never_touches_an_approved_post(monkeypatch):
    monkeypatch.setattr(media_generator.db, "upload_generated", lambda store, path, data, ct: f"https://cdn/{path}")
    store = _job_store(post_status="approved", media_ids=["old"])
    media_generator.process_row(store, store.tables["media_generations"][0], _settings(), {})
    assert store.tables["semasa_posts"][0]["media_ids"] == ["old"]


def test_a_slide_that_cannot_fit_is_a_final_error_naming_it(monkeypatch):
    monkeypatch.setattr(media_generator.db, "upload_generated", lambda store, path, data, ct: f"https://cdn/{path}")
    store = _job_store()
    row = store.tables["media_generations"][0]
    row["meta"]["slides"] = GOOD[:1] + [{"title": "P", "points": ["perkataan " * 80] * 5}]
    assert media_generator.process_row(store, row, _settings(), {}) is False
    got = store.tables["media_generations"][0]
    assert got["status"] == "error" and "slide 2: too long" in got["error"]
    assert store.tables["semasa_posts"][0]["media_ids"] == []


def test_post_image_ground_falls_back_to_paper_and_says_so(monkeypatch):
    monkeypatch.setattr(media_generator.db, "upload_generated", lambda store, path, data, ct: f"https://cdn/{path}")
    store = _job_store(extra_media=[{"id": "pic", "post_id": "p1", "type": "image", "mode": "prompt",
                                     "status": "error", "created_at": "1"}])
    row = store.tables["media_generations"][0]
    row["meta"]["bg"] = "post_image"
    assert media_generator.process_row(store, row, _settings(), {}) is True
    meta = store.tables["media_generations"][0]["meta"]
    assert meta["bg_used"] is None and "drawn on paper" in meta["bg_missing"]


def test_post_image_ground_uses_the_finished_picture(monkeypatch):
    monkeypatch.setattr(media_generator.db, "upload_generated", lambda store, path, data, ct: f"https://cdn/{path}")
    buf = io.BytesIO()
    Image.new("RGB", (800, 800), (200, 30, 30)).save(buf, "PNG")
    monkeypatch.setattr(media_generator, "fetch_reference", lambda url: (buf.getvalue(), "image/png", "x.png"))
    store = _job_store(extra_media=[{"id": "pic", "post_id": "p1", "type": "image", "mode": "prompt",
                                     "status": "done", "generated_media_url": "https://cdn/pic.png", "created_at": "1"}])
    row = store.tables["media_generations"][0]
    row["meta"]["bg"] = "post_image"
    media_generator.process_row(store, row, _settings(), {})
    assert store.tables["media_generations"][0]["meta"]["bg_used"] == "pic"


# --- the writer ------------------------------------------------------------------------

class FakeLLM:
    def __init__(self, out):
        self.out, self.seen = out, []
        from semasa.config import LLMSettings
        self.s = LLMSettings(provider="openai", api_key="k", base_url="https://x/v1", model="m", timeout=5)

    @property
    def configured(self):
        return True

    def chat_json(self, system, user, max_tokens=0, model=None):
        self.seen.append((system, user))
        return self.out


def test_an_idea_that_asks_for_slides_gets_them_and_one_slide_job(monkeypatch):
    monkeypatch.setattr(ideas, "read_source", lambda url: {"ok": False, "why": "x", "image": None})
    cap = "Notifikasi kosmetik bukan kelulusan produk."
    store = FakeStore(semasa_settings=[], semasa_posts=[], media_generations=[], semasa_ideas=[])
    llm = FakeLLM({"fit": True, "hook": "h", "domain": "kosmetik", "citation": "NPRA",
                   "text": {"bm": {"instagram": cap, "facebook": cap, "threads": cap}},
                   "visual_prompt": "botol", "alt": "botol", "slides": GOOD + [{"title": "", "points": []}]})
    idea = {"id": "i1", "stream": "regulab", "source_title": "T", "created_by": "u", "make_media": "image",
            "make_slides": True}
    ideas.process_idea(store, llm, idea, {})
    assert "SLIDES WANTED" in llm.seen[0][0]
    post = store.tables["semasa_posts"][0]
    assert post["slides"] == compliance.normalise_slides(GOOD)
    jobs = store.tables["media_generations"]
    assert [j["mode"] for j in jobs] == ["prompt", "slides"]                   # the picture first: it is the ground
    assert jobs[1]["meta"]["bg"] == "post_image" and jobs[1]["meta"]["slides"] == post["slides"]
    assert any(f["where"] == "Slides" and not f["hard"] for f in post["flags"])  # written, not drawn yet


def test_an_idea_without_slides_writes_no_slides_column(monkeypatch):
    """A database that has not run 006 has no `slides` column: never send one it did not ask for."""
    monkeypatch.setattr(ideas, "read_source", lambda url: {"ok": False, "why": "x", "image": None})
    cap = "Notifikasi kosmetik bukan kelulusan produk."
    store = FakeStore(semasa_settings=[], semasa_posts=[], media_generations=[], semasa_ideas=[])
    llm = FakeLLM({"fit": True, "hook": "h", "citation": "NPRA", "slides": GOOD,
                   "text": {"bm": {"instagram": cap, "facebook": cap, "threads": cap}}})
    ideas.process_idea(store, llm, {"id": "i1", "stream": "regulab", "make_media": "none"}, {})
    assert "slides" not in store.tables["semasa_posts"][0]
    assert "SLIDES WANTED" not in llm.seen[0][0]
    assert store.tables["media_generations"] == []


# --- the publisher ------------------------------------------------------------------------

def test_the_publisher_sends_every_slide_and_blocks_stale_pictures():
    from datetime import UTC, datetime
    now = datetime(2026, 9, 24, 2, 0, tzinfo=UTC)
    cap = "Notifikasi kosmetik bukan kelulusan produk. NPRA menyemak dokumen selepas produk dipasarkan."
    post = {"id": "p1", "stream": "regulab", "lang": "bm", "status": "approved", "date": "2026-09-25", "slot": "08:00",
            "text": {"bm": {"instagram": cap, "facebook": cap, "threads": cap}}, "citation": "NPRA",
            "media_ids": ["s1"], "published": {}, "errors": {}, "slides": GOOD}
    media = {"id": "s1", "status": "done", "mode": "slides", "generated_media_url": "https://cdn/1.jpg",
             "meta": {"slides": GOOD, "slide_urls": ["https://cdn/1.jpg", "https://cdn/2.jpg", "https://cdn/3.jpg"]}}
    store = FakeStore(semasa_settings=[], semasa_posts=[post], media_generations=[media], semasa_publish_log=[])
    c = publisher.run(store, now)
    assert c["dry_run"] == 3
    assert store.tables["semasa_publish_log"][0]["detail"]["would_send"]["media"] == media["meta"]["slide_urls"]

    store.tables["semasa_posts"][0]["slides"] = GOOD[:2]                       # edited after drawing
    store.tables["semasa_publish_log"] = []
    c = publisher.run(store, now)
    assert c["blocked"] == 3 and c["dry_run"] == 0
    assert any("different words" in w for w in store.tables["semasa_publish_log"][0]["detail"]["why"])


# --- the 48-hour drop ----------------------------------------------------------------------

def test_unpicked_headlines_are_dropped_only_when_they_cannot_come_back():
    store = FakeStore(
        isu_semasa_trends=[
            {"id": "old", "created_at": "2026-09-20T00:00:00+00:00", "published_at": "2026-09-19T00:00:00+00:00"},
            {"id": "picked", "created_at": "2026-09-20T00:00:00+00:00", "published_at": "2026-09-19T00:00:00+00:00"},
            {"id": "undated", "created_at": "2026-09-20T00:00:00+00:00", "published_at": None},
            {"id": "fresh", "created_at": "2026-09-24T00:00:00+00:00", "published_at": "2026-09-23T23:00:00+00:00"},
        ],
        semasa_ideas=[{"id": "i", "trend_id": "picked"}, {"id": "j", "trend_id": None}])
    n = db.drop_unpicked(store, "2026-09-22T02:00:00+00:00", "2026-09-22T02:00:00+00:00")
    assert n == 1
    assert {r["id"] for r in store.tables["isu_semasa_trends"]} == {"picked", "undated", "fresh"}


def test_drop_never_raises():
    class Broken:
        def table(self, name):
            raise RuntimeError("down")
    assert db.drop_unpicked(Broken(), "a", "b") == 0


# --- SQL ---------------------------------------------------------------------------------

def _gate(path: str) -> str:
    sql = (ROOT / "supabase" / path).read_text(encoding="utf-8")
    m = re.search(r"create or replace function public\.semasa_posts_gate\(\).*?end \$\$;", sql, re.S)
    assert m, path
    return m.group(0)


def test_005_and_006_define_the_same_gate_and_it_watches_slides():
    assert _gate("005_studio.sql") == _gate("006_slides.sql")
    assert "new.slides is distinct from old.slides" in _gate("006_slides.sql")


def test_scrape_runs_every_eight_hours():
    wf = (ROOT / ".github" / "workflows" / "scrape.yml").read_text(encoding="utf-8")
    cron = re.search(r'cron:\s*"([^"]+)"', wf).group(1)
    minute, hours, *_ = cron.split()
    assert minute.isdigit() and [int(h) for h in hours.split(",")] == [7, 15, 23]
