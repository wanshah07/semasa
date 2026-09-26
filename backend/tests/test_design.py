"""The Design tab: posters, single cards and carousels, from Wan's own words or from an idea the writer turns into
words, on paper, on an uploaded picture or on a picture made for them; judged by the post rules; never mistaken for
the post's own carousel."""

import io

import pytest
from fakestore import FakeStore
from PIL import Image

from semasa import compliance, design, media_generator, publisher, slides
from semasa.config import LLMSettings, MediaSettings

POSTER = [{"title": "Sijil halal *tidak* menyembunyikan pengilang",
           "points": ["Nama dan alamat pengilang OEM tetap dicetak.", "Maklumat juga boleh dibaca melalui kod QR.",
                      "Permohonan untuk menyembunyikannya tidak diluluskan."]}]
CAROUSEL = [{"title": "Notifikasi *bukan* kelulusan", "points": []},
            {"title": "Apa NPRA semak", "points": ["Dokumen PIF selepas produk dipasarkan."]},
            {"title": "Ringkasnya", "points": ["Notifikasi ialah pendaftaran."]}]


def _img(b):
    return Image.open(io.BytesIO(b)).convert("RGB")


def _settings():
    return MediaSettings(provider="cloudflare", batch=5, max_attempts=3, poll_seconds=0, max_wait_image=1,
                         max_wait_video=1, replicate_token=None, replicate_image_model="a/b",
                         replicate_video_model="c/d", replicate_image_input_key="input_image",
                         replicate_video_input_key="start_image", openai_key=None,
                         openai_base_url="https://api.openai.com/v1", openai_image_model="gpt-image-1",
                         openai_video_model="sora-2", openai_image_size="1024x1024", openai_video_seconds="8",
                         openai_video_size="1280x720")


class Writer:
    def __init__(self, out):
        self.out, self.seen, self.last_model = out, [], "rootsys-m"
        self.s = LLMSettings(provider="openai", api_key="k", base_url="https://rootsys.cloud/v1", model="m", timeout=5)

    configured = True

    def why_off(self):
        return "off"

    def chat_json(self, system, user, max_tokens=0, **k):
        self.seen.append((system, user))
        return self.out


def _store(meta, **row):
    job = {"id": "d1", "mode": "slides", "type": "image", "status": "processing", "attempts": 1,
           "created_at": "2099-01-01T00:00:00+00:00", "meta": {"stream": "regulab", "bg": "none", **meta}, **row}
    return FakeStore(semasa_settings=[{"key": "brand", "value": {"regulab": {"website": "www.kkmhalalconsultant.com"}}}],
                     semasa_posts=[{"id": "p1", "status": "draft", "media_ids": ["own"]}],
                     media_generations=[job, {"id": "own", "mode": "slides", "type": "image", "status": "done", "meta": {}}])


def _run(store, llm=None, monkeypatch=None):
    return media_generator.process_row(store, store.tables["media_generations"][0], _settings(), {}, llm)


@pytest.fixture(autouse=True)
def _uploads(monkeypatch):
    got = {}
    monkeypatch.setattr(media_generator.db, "upload_generated",
                        lambda store, path, data, ct: got.setdefault(path, data) and f"https://cdn/{path}")
    return got


# --- the renderer ---------------------------------------------------------------------

def test_a_poster_is_one_portrait_picture_with_no_page_count(_uploads):
    store = _store({"design": "poster", "slides": POSTER, "citation": "JAKIM, MPPHM 2020"})
    assert _run(store) is True
    done = store.tables["media_generations"][0]
    assert done["status"] == "done" and done["meta"]["count"] == 1
    assert _img(next(iter(_uploads.values()))).size == (1080, 1350)
    one = slides.render(POSTER, size=slides.FORMATS["portrait"], source="JAKIM")
    two = slides.render(POSTER + POSTER, size=slides.FORMATS["portrait"], source="JAKIM")
    assert one[0] != two[0]                                   # "1/2" is drawn on a carousel, nothing on a poster


def test_card_and_story_shapes(_uploads):
    store = _store({"design": "card", "slides": [POSTER[0] | {"points": POSTER[0]["points"][:2]}]})
    _run(store)
    assert _img(next(iter(_uploads.values()))).size == (1080, 1080)
    _uploads.clear()
    store = _store({"design": "poster", "format": "story", "slides": POSTER})
    _run(store)
    assert _img(next(iter(_uploads.values()))).size == (1080, 1920)


def test_a_carousel_follows_its_stream_unless_a_shape_is_chosen(_uploads):
    store = _store({"design": "carousel", "slides": CAROUSEL, "stream": "linkedin"})
    _run(store)
    assert [_img(b).size for b in _uploads.values()] == [(1080, 1350)] * 3


def test_two_slides_of_words_for_a_poster_is_named_not_cut():
    store = _store({"design": "poster", "slides": CAROUSEL})
    assert _run(store) is False
    job = store.tables["media_generations"][0]
    assert job["status"] == "error" and "one picture" in job["error"]


# --- the writer ---------------------------------------------------------------------------

def test_an_idea_becomes_words_saved_before_drawing():
    llm = Writer({"slides": POSTER + CAROUSEL, "citation": "JAKIM, MPPHM (Domestik) 2020"})
    store = _store({"design": "poster", "brief": "OEM name on the halal certificate cannot be hidden"})
    assert _run(store, llm) is True
    meta = store.tables["media_generations"][0]["meta"]
    assert meta["slides"] == compliance.normalise_slides(POSTER)            # a poster keeps the first only
    assert meta["citation"] == "JAKIM, MPPHM (Domestik) 2020" and meta["written_by"] == "rootsys-m"
    system, user = llm.seen[0]
    assert "ONE poster" in system and "No call to action" in system and "OEM name" in user


def test_wan_citation_wins_over_the_writers():
    llm = Writer({"slides": POSTER, "citation": "the writer's"})
    store = _store({"design": "card", "brief": "x", "citation": "Wan's own"})
    _run(store, llm)
    assert store.tables["media_generations"][0]["meta"]["citation"] == "Wan's own"


def test_an_idea_with_the_writer_off_says_write_it_yourself():
    class Off(Writer):
        configured = False
    store = _store({"design": "poster", "brief": "x"})
    assert _run(store, Off({})) is False
    assert "Write the words yourself" in store.tables["media_generations"][0]["error"]


def test_rule_breaking_words_are_drawn_but_flagged():
    store = _store({"design": "card", "slides": [{"title": "Hubungi kami sekarang", "points": ["www.kkmhalalconsultant.com"]}]})
    _run(store)
    flags = store.tables["media_generations"][0]["meta"]["flags"]
    assert any(f["hard"] and f["where"].startswith("Design") for f in flags)


# --- backgrounds ----------------------------------------------------------------------------

def test_an_uploaded_picture_is_the_ground(monkeypatch):
    buf = io.BytesIO()
    Image.new("RGB", (900, 600), (20, 120, 200)).save(buf, "PNG")
    monkeypatch.setattr(media_generator, "fetch_reference", lambda url: (buf.getvalue(), "image/png", "x.png"))
    store = _store({"design": "poster", "slides": POSTER, "bg": "reference"}, reference_url="https://ref/x.png")
    _run(store)
    assert store.tables["media_generations"][0]["meta"]["bg_used"] == "reference"


def test_it_waits_for_the_picture_made_for_it():
    store = _store({"design": "poster", "slides": POSTER, "bg": "pic"})
    store.tables["media_generations"].append({"id": "pic", "mode": "prompt", "type": "image", "status": "pending"})
    assert _run(store) is True
    assert store.tables["media_generations"][0]["status"] == "pending"      # back in the queue, not drawn on paper


# --- the post it is attached to ---------------------------------------------------------------

def test_attached_to_a_post_it_is_added_never_replacing_the_posts_carousel():
    store = _store({"design": "poster", "slides": POSTER}, post_id="p1")
    _run(store)
    assert store.tables["semasa_posts"][0]["media_ids"] == ["own", "d1"]


def test_the_publisher_judges_it_as_artwork_not_as_the_posts_slides():
    entry = publisher.scan_entry({"mode": "slides", "meta": {"design": "poster", "slides": POSTER}})
    assert entry == {"alt": "", "artwork": POSTER}
    cap = "Notifikasi kosmetik bukan kelulusan produk. NPRA menyemak dokumen selepas produk dipasarkan."
    post = {"stream": "regulab", "lang": "bm", "text": {"bm": {p: cap for p in ("instagram", "facebook", "threads")}},
            "media": [entry]}
    assert not [f for f in compliance.scan(post) if f["hard"]]


def test_design_size_defaults():
    assert design.size_of({"design": "poster"}, "regulab") == (1080, 1350)
    assert design.size_of({"design": "card"}, "linkedin") == (1080, 1080)
    assert design.size_of({"design": "carousel"}, "linkedin") is None          # the stream's own shape


# --- from a reference: review, draw, wait for Wan's confirmation --------------------------------------------------

REVIEW = {"summary": "Rujukan ini tenang dan kemas. Reka bentuk baharu mengekalkan ruang lapang.",
          "keep": ["Tajuk besar di atas", "Warna krim lembut"], "change": ["Buang laman web", "Buang logo jenama lain"],
          "look": "era", "background": "A soft cream paper texture with warm window light", "words_note": "one short headline",
          "text_in_image": "SHOP NOW", "brands": ["Acme"]}


class Seer(Writer):
    def __init__(self, out, review=REVIEW):
        super().__init__(out)
        self.review_out, self.looked = review, []

    def describe_image(self, system, prompt, data, mime, max_tokens=900):
        self.looked.append(prompt)
        return self.review_out


def _jpeg():
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), (200, 180, 150)).save(buf, "JPEG")
    return buf.getvalue()


@pytest.fixture
def studio(monkeypatch):
    drawn = []
    from semasa import studio_cards
    monkeypatch.setattr(studio_cards, "render", lambda items, **k: drawn.append(k) or [_jpeg() for _ in items])
    monkeypatch.setattr(media_generator, "fetch_reference", lambda url: (_jpeg(), "image/jpeg", "r.jpg"))
    made = []

    class Maker:
        def generate_from_text(self, prompt, options):
            from semasa.providers import Generated
            made.append(prompt)
            return Generated(_jpeg(), "image/jpeg", "flux-schnell")
    monkeypatch.setattr(media_generator, "make_provider", lambda name, s: Maker())
    return {"drawn": drawn, "made": made}


def _ref_store(**meta):
    return _store({"design": "poster", "brief": "Pengilang OEM mesti dicetak pada sijil", "look": "auto", "bg": "from_ref",
                   "style_ref": {"url": "https://ref/style.jpg", "path": "u/style.jpg"}, **meta}, post_id="p1")


def test_a_reference_is_reviewed_drawn_and_waits_for_wan(studio):
    llm = Seer({"slides": POSTER, "citation": "JAKIM, MPPHM 2020"})
    store = _ref_store()
    assert _run(store, llm) is True
    job = store.tables["media_generations"][0]
    m = job["meta"]
    assert job["status"] == "done" and m["awaiting_confirm"] is True and not m.get("saved")
    assert m["review"]["look"] == "era" and m["look_chosen"] == "era" and studio["drawn"][0]["look"] == "era"
    assert m["review"]["change"] == ["Buang laman web", "Buang logo jenama lain"]
    assert "never copies" in llm.looked[0] and "Bahasa Indonesia" in llm.looked[0]
    assert "one short headline" in llm.seen[0][1]                                   # the words follow the reference's shape
    assert studio["made"] and "cream paper" in studio["made"][0] and "no logos" in studio["made"][0]
    assert m["ground_url"].endswith("-ground.jpg")
    assert store.tables["semasa_posts"][0]["media_ids"] == ["own"]                  # not attached before Simpan


def test_simpan_keeps_it_and_attaches_it_without_drawing_again(studio):
    store = _ref_store(slides=POSTER, review=REVIEW, awaiting_confirm=True, confirm="save")
    job = store.tables["media_generations"][0]
    job["generated_media_url"] = "https://cdn/x.jpg"
    assert _run(store, Seer({})) is True
    assert job["status"] == "done" and job["meta"]["saved"] is True and job["meta"]["awaiting_confirm"] is False
    assert "confirm" not in job["meta"] and not studio["drawn"] and not studio["made"]
    assert store.tables["semasa_posts"][0]["media_ids"] == ["own", "d1"]


def test_ubah_rewrites_with_the_note_and_makes_the_background_again(studio):
    llm = Seer({"slides": POSTER, "citation": ""})
    store = _ref_store(slides=POSTER, review=REVIEW, awaiting_confirm=True, ground_url="https://cdn/old-ground.jpg",
                       revise={"note": "lebih gelap, tajuk lebih pendek"})
    _run(store, llm)
    m = store.tables["media_generations"][0]["meta"]
    assert "lebih gelap, tajuk lebih pendek" in llm.seen[0][1]                       # the words were written again
    assert "lebih gelap" in studio["made"][0]                                          # and the background made again
    assert m["revisions"][0]["note"] == "lebih gelap, tajuk lebih pendek" and "revise" not in m
    assert m["awaiting_confirm"] is True


def test_an_unread_reference_still_draws_and_says_why(studio):
    llm = Seer({"slides": POSTER, "citation": ""}, review=None)
    store = _ref_store()
    _run(store, llm)
    m = store.tables["media_generations"][0]["meta"]
    assert "unread" in m["review"] and m["look_chosen"] == "grid" and "bg_missing" in m and not studio["made"]
    assert store.tables["media_generations"][0]["status"] == "done"


def test_a_design_without_a_reference_is_unchanged(studio):
    store = _store({"design": "poster", "slides": POSTER}, post_id="p1")
    _run(store)
    m = store.tables["media_generations"][0]["meta"]
    assert "awaiting_confirm" not in m and "review" not in m
    assert store.tables["semasa_posts"][0]["media_ids"] == ["own", "d1"]
