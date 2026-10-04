"""ws.regulab Studio's card designs in Semasa: the slide job carries the look, the worker draws it with Studio's own
code in headless Chrome, and a slide Studio calls too full fails with its number instead of shipping clipped.

The drawing itself needs a browser. Those tests run when SEMASA_CHROME names one (a local run); in CI the routing,
the refusals and the bookkeeping are checked with the renderer stubbed."""

import io
import os

import pytest
from fakestore import FakeStore
from PIL import Image

from semasa import cards_library, ideas, media_generator, studio_cards
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
                    "ground": None, "ground_mime": "image/jpeg", "size": None, "n": 3, "fit": False, "design": None,
                    "mascots": [{"k": k, "url": f"/cards/mascots/{k}.webp"} for k in ("wave", "point", "confused", "shocked")]}


def test_fit_the_design_to_each_slide_reaches_the_renderer_only_when_the_job_says_so(monkeypatch, _uploads):
    seen = []
    monkeypatch.setattr(studio_cards, "render", lambda items, **kw: seen.append(kw["fit"]) or [_jpeg() for _ in items])
    for meta in ({"look": "era", "fit": True}, {"look": "era", "fit": False}, {"look": "era"}):
        assert _run(_store(meta)) is True
    assert seen == [True, False, False]


def test_each_slide_gets_its_own_background_once_fetched(monkeypatch, _uploads):
    """Studio's per-slide ground (27 Sep 2026): a slide naming Wan's photograph gets its bytes as a data address;
    the set's background stays for the others; the words kept on the job carry no address."""
    seen = {}

    def fake(items, **kw):
        seen["items"] = items
        return [_jpeg() for _ in items]

    monkeypatch.setattr(studio_cards, "render", fake)
    store = _store({"look": "grid", "citation": "NPRA", "slides": [
        {"title": "Satu", "points": ["a"], "bg": "lib:g_makmal02", "scrim": "heavy"},
        {"title": "Dua", "points": ["b"]},
        {"title": "Tiga", "points": ["c"], "bg": "lib:g_tiada"}]})
    assert _run(store) is True
    got = seen["items"]
    assert got[0]["bg_url"].startswith("data:image/jpeg;base64,") and got[0]["scrim"] == "heavy"
    assert "bg_url" not in got[1] and "bg_url" not in got[2]           # an unknown photograph: the set's background
    kept = store.tables["media_generations"][0]["meta"]["slides"]
    assert kept[0]["bg"] == "lib:g_makmal02" and not any("bg_url" in k for k in kept)


def test_the_classic_drawing_keeps_a_lead_and_a_note():
    from semasa.media_generator import classic_words
    got = classic_words([{"title": "T", "points": ["a", "b", "c", "d"], "lead": "L", "note": "N"}])
    assert got == [{"title": "T", "points": ["L", "a", "b", "c", "d · N"]}]


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
    assert ideas.slide_job(idea, post, "p1")["meta"]["fit"] is True            # a Studio look fits each slide by default
    assert ideas.slide_job({"id": "i2", "brief": {}}, post, "p1")["meta"]["fit"] is False
    # no picture made: a Studio look is drawn on Studio's ground for the domain; Semasa's own look stays on paper
    assert ideas.slide_job(idea, post, "p1")["meta"]["bg"] == "lib:g_makmal02"
    assert ideas.slide_job(idea, post, "p1", bg="post_image")["meta"]["bg"] == "post_image"
    assert ideas.slide_job({"id": "i2", "brief": {}}, post, "p1")["meta"]["bg"] == "none"
    li = {**post, "stream": "linkedin", "domain": None, "angle": "E"}
    assert ideas.slide_job(idea, li, "p1")["meta"]["bg"] == "lib:g_gudang01"
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


@browser
def test_a_mascot_a_template_and_a_photograph_really_reach_the_picture():
    """Studio's per-slide editor, drawn for real: each choice must change the pixels, not only the settings."""
    from semasa import cards_library
    from semasa.media_generator import own_grounds

    def px(items, **kw):
        return Image.open(io.BytesIO(studio_cards.render(items, look="grid", stream="regulab", **kw)[0])).convert("L")

    def differs(a, b):
        from PIL import ImageChops
        return ImageChops.difference(a, b).getbbox() is not None

    base = [{"title": "Semak *dahulu*", "points": []}]           # short: a full slide makes the character stand down
    plain = px(base)
    assert differs(plain, px(base, mascots=cards_library.mascots())), "the auto pose was not drawn"
    assert not differs(plain, px([{**base[0], "mascot": "none"}], mascots=cards_library.mascots())), "None still drew one"
    bars = [{"title": "Had", "template": "g_bars", "points": ["Malaysia | 0.5 | 0.5%", "EU | 0.4 | 0.4%"]}]
    assert differs(plain, px(bars)), "the chosen template was not used"
    ground = own_grounds(None, {"id": "t"}, [{**base[0], "bg": "lib:g_makmal02"}])
    assert differs(plain, px(ground)), "the photograph was not drawn behind the slide"


@browser
def test_text_size_font_and_mascot_choices_really_change_the_picture_and_the_default_does_not():
    """Wan, 3 Oct 2026: compact the text, change the font, move and resize the mascot. A card with none of these
    drawn exactly as before; each choice must move pixels, not only a setting."""
    from PIL import ImageChops

    from semasa import cards_library

    def px(items):
        return Image.open(io.BytesIO(studio_cards.render(items, look="era", stream="regulab",
                                                         mascots=cards_library.mascots())[0])).convert("L")

    def differs(a, b):
        return ImageChops.difference(a, b).getbbox() is not None

    base = [{"title": "Notifikasi *bukan* kelulusan", "template": "e_explain", "lead": "Semak selepas dipasarkan.",
             "points": ["Satu", "Dua", "Tiga"]}]
    plain = px(base)
    assert not differs(plain, px([{**base[0]}])), "the same slide drew two different pictures"
    for key, val in (("type_size", "70"), ("font", "sans"), ("font", "hand"), ("mascot_size", "60")):
        assert differs(plain, px([{**base[0], key: val}])), f"{key}={val} changed nothing"
    # the automatic place is picked from the title, so one of the three may be the one already drawn: the other two move it
    spots = {pos: px([{**base[0], "mascot_pos": pos}]) for pos in ("bl", "bc", "br")}
    assert sum(differs(plain, img) for img in spots.values()) == 2, "a chosen place must move the mascot, except to where it was"


# the twenty-one designs, each on words shaped for it (4 Oct 2026: nine added). A slide the browser calls too full raises.
SHAPES = {
    "g_title": {"note": "Semak sumber."}, "g_stat": {"points": ["245", "hari"]},
    "g_bars": {"points": ["Malaysia | 0.5 | 0.5%", "EU | 0.4 | 0.4%"]}, "g_rows": {"points": ["A | b", "C | d", "E | f"]},
    "g_table": {"points": ["I | Surat | amaran", "II | Batal | produk"]},
    "g_check": {"points": ["Senarai INCI | Setiap bahan.", "Artwork label | Bahasa betul.", "Surat pengilang"]},
    "g_myth": {"points": ["Ada nombor, sudah lulus | Nombor bukan kelulusan", "NPRA uji semua | NPRA semak maklumat"]},
    "g_steps": {"points": ["PIF | Dokumen lengkap.", "Hantar | QUEST3+.", "Nombor | Boleh jual."]},
    "e_hook": {"lead": "Padahal sudah di pasaran?", "points": ["Apa dilanggar?", "Siapa semak?"]},
    "e_explain": {"points": ["INCI | Padan formula.", "Label | Nama."]},
    "e_flow": {"points": ["Aduan | Fail dibuka.", "Sampel | Diuji."], "note": "Kos ditanggung syarikat."},
    "e_vs": {"points": ["Ujian | RM8,000", "Tarik balik | RM240,000", "Kos henti"], "note": "Contoh."},
    "e_myth": {"points": ["Bernombor bermakna lulus | Nombor bukan kelulusan."], "note": "Semak sumber."},
    "e_check": {"points": ["INCI | Padan formula.", "Label | Nama.", "Surat"], "note": "Satu tiada, lot tertahan."},
    "e_stat": {"points": ["14", "hari bekerja"], "lead": "Hantar hingga nombor.", "note": "Contoh."},
    "e_event": {"eyebrow": "Bengkel", "lead": "Notifikasi kosmetik\nbagi pemilik SME",
                "title": "*NOTIFIKASI* langkah demi langkah untuk *SME*",
                "points": ["Penceramah A | Malaysia", "Penceramah B | Singapura", "Penceramah C | Thailand"],
                "note": "Rabu 14 Okt 2026 | 10:00 – 12:00 | Bilik seminar 2", "chip": "Contoh"},
    "p_title": {}, "p_fact": {"points": ["Surat", "INCI", "Label"]}, "p_quote": {"lead": "NPRA"},
    "p_stat": {"points": ["245", "hari"]},
    "p_list": {"points": ["Surat | Pengeluar asal.", "INCI | Setiap bahan.", "Label | Betul."]},
    "p_split": {"lead": "Nombor hanya bukti.", "points": ["Semak maklumat", "Bukan ujian"]},
}


@browser
@pytest.mark.parametrize("stream,size", [("regulab", (1080, 1080)), ("linkedin", (1080, 1350))])
def test_every_template_draws_at_the_streams_size_without_a_warning(stream, size):
    assert set(SHAPES) == {t["k"] for t in cards_library.catalogue()["templates"]}, "a template with no sample here is untested"
    ground = _jpeg(900, 1100)
    for k, shape in SHAPES.items():
        look = {"g": "grid", "e": "era", "p": "photo"}[k[0]]
        slide = {"title": "Semak *dahulu*", "template": k, **shape}
        pics = studio_cards.render([slide], look=look, stream=stream, eyebrow="Kosmetik", source="NPRA",
                                   ground=ground if look == "photo" else None, mascots=cards_library.mascots())
        assert Image.open(io.BytesIO(pics[0])).size == size, k


@browser
def test_fit_draws_a_figure_slide_with_the_figure_design():
    deck = [{"title": "Kulit", "points": []}, {"title": "Tempoh purata", "points": ["14", "hari"]},
            {"title": "Langkah notifikasi", "points": ["PIF | Lengkap.", "Hantar | QUEST3+."]}]
    pics = studio_cards.render(deck, look="grid", stream="regulab", eyebrow="K", source="NPRA", fit=True)
    assert len(pics) == 3


def _pale(w=900, h=1100):
    """A light, airy ground like a studio background: pale lilac to blush, with a soft pink disc low on the right."""
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        for x in range(w):
            t = (x / w + y / h) / 2
            px[x, y] = (int(226 + 26 * t), int(218 + 30 * t), int(236 + 12 * t))
    from PIL import ImageDraw
    ImageDraw.Draw(im).ellipse([w * 0.5, h * 0.62, w * 1.3, h * 1.4], fill=(238, 170, 190))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    return buf.getvalue()


def _mean_luma(png: bytes, box) -> float:
    crop = Image.open(io.BytesIO(png)).convert("L").crop(box)
    return sum(crop.get_flattened_data() if hasattr(crop, 'get_flattened_data') else crop.getdata()) / (crop.width * crop.height)


@browser
def test_a_light_ground_keeps_dark_ink_and_no_scrim_unless_a_scrim_was_chosen():
    slide = {"title": "*Semak* dahulu", "template": "e_event", **SHAPES["e_event"]}
    auto = studio_cards.render([slide], look="era", stream="regulab", ground=_pale())[0]
    assert Image.open(io.BytesIO(auto)).size == (1080, 1080)
    # the corner under the logo stays as bright as the picture: no dark scrim was laid over a light ground
    assert _mean_luma(auto, (700, 380, 1000, 520)) > 170
    chosen = studio_cards.render([{**slide, "scrim": "heavy"}], look="era", stream="regulab", ground=_pale())[0]
    assert _mean_luma(chosen, (700, 380, 1000, 520)) < 130        # Wan chose a heavy scrim on purpose: it is honoured


@browser
def test_a_light_ground_is_light_under_every_grid_and_era_design_and_every_size():
    """A carousel slide and a single card go through the same designs: none of them may grey a pale picture out."""
    for stream, size in (("regulab", (1080, 1080)), ("linkedin", (1080, 1350))):
        for k, shape in SHAPES.items():
            if k[0] == "p":
                continue                                    # the Photo family is a dark photograph by design
            look = "grid" if k[0] == "g" else "era"
            pic = studio_cards.render([{"title": "Semak *dahulu*", "template": k, **shape}], look=look, stream=stream,
                                      eyebrow="Kosmetik", source="NPRA", ground=_pale(), mascots=cards_library.mascots())[0]
            assert Image.open(io.BytesIO(pic)).size == size
            # the right margin carries no words on any design: it shows the picture as it is, under no scrim
            assert _mean_luma(pic, (1030, 300, 1070, 700)) > 150, (k, stream)


def _solid(rgb, size=(400, 300)):
    buf = io.BytesIO()
    Image.new("RGB", size, rgb).save(buf, "JPEG", quality=90)
    return buf.getvalue()


UID = "0b1c2d3e-4f50-4a6b-8c7d-9e0f1a2b3c4d"


class _Bucket:
    def __init__(self, files):
        self.files = files

    def download(self, path):
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]


class _Storage:
    def __init__(self, files):
        self.files = files

    def from_(self, name):
        assert name == "semasa-reference"
        return _Bucket(self.files)


class _Store:
    def __init__(self, files):
        self.storage = _Storage(files)


def test_speaker_photos_are_read_cropped_square_and_a_missing_one_is_skipped():
    from semasa import media_generator
    ok, gone = f"ref:{UID}/a.jpg", f"ref:{UID}/missing.jpg"
    store = _Store({f"{UID}/a.jpg": _solid((200, 30, 30))})
    out = media_generator.own_photos(store, [{"title": "x", "photos": f"{ok},{gone},not-a-token"}, {"title": "no photos"}])
    assert out[1] == {"title": "no photos"}                          # a slide without photos is untouched
    urls = out[0]["photo_urls"]
    assert urls[0].startswith("data:image/jpeg;base64,") and urls[1] == ""
    got = Image.open(io.BytesIO(__import__("base64").b64decode(urls[0].split(",", 1)[1])))
    assert got.size == (media_generator.PHOTO_EDGE, media_generator.PHOTO_EDGE)       # a landscape photo, cropped square
    assert len(urls) == 2                                           # the malformed third entry was dropped by the rules


@browser
def test_the_event_poster_draws_a_speakers_own_photo_in_the_round_slot_and_initials_for_the_rest():
    import base64
    red = "data:image/jpeg;base64," + base64.b64encode(_solid((220, 20, 20), (480, 480))).decode("ascii")
    slide = {"title": "*Simposium*", "template": "e_event", **SHAPES["e_event"], "photo_urls": [red, ""]}
    pic = studio_cards.render([slide], look="era", stream="regulab", ground=_pale())[0]
    left = Image.open(io.BytesIO(pic)).convert("RGB").crop((60, 540, 560, 1000))
    px = left.load()
    n = sum(1 for x in range(left.width) for y in range(left.height)
            if px[x, y][0] > 180 and px[x, y][1] < 70 and px[x, y][2] < 70)
    assert n > 2500                                                 # the first speaker's circle holds the photo
    bare = {k: v for k, v in slide.items() if k != "photo_urls"}
    plain = studio_cards.render([bare], look="era", stream="regulab", ground=_pale())[0]
    px2 = Image.open(io.BytesIO(plain)).convert("RGB").crop((60, 540, 560, 1000)).load()
    assert sum(1 for x in range(500) for y in range(460) if px2[x, y][0] > 180 and px2[x, y][1] < 70) < 50


def test_a_saved_design_on_the_job_reaches_the_renderer_and_decides_the_look(monkeypatch, _uploads):
    seen = {}
    monkeypatch.setattr(studio_cards, "render", lambda items, **kw: seen.update(kw) or [_jpeg() for _ in items])
    pack = {"look": "era", "cover": "e_hook", "accent": "#0a7c6e"}
    assert _run(_store({"look": "classic", "fit": True, "design_pack": pack})) is True
    assert seen["look"] == "era" and seen["design"] == pack            # the design's family wins over the job's look
    seen.clear()
    assert _run(_store({"look": "grid", "design_pack": {"look": "classic"}})) is True
    assert seen["look"] == "grid" and seen["design"] is None           # an unusable snapshot is ignored, the job's look stands


def _near(png: bytes, rgb, tol=18) -> int:
    px = Image.open(io.BytesIO(png)).convert("RGB")
    data = px.tobytes()
    return sum(1 for i in range(0, len(data), 3)
               if abs(data[i] - rgb[0]) < tol and abs(data[i + 1] - rgb[1]) < tol and abs(data[i + 2] - rgb[2]) < tol)


@browser
def test_a_saved_design_recolours_the_cards_and_the_next_card_gets_its_own_colours_back():
    deck = [{"title": "*Kenapa* ditarik balik", "points": ["Apa yang dilanggar?", "Siapa menyemak?"]},
            {"title": "Sebelum *notifikasi*", "points": ["INCI | Padan.", "Label | Nama.", "Surat"]},
            {"title": "Tutup", "points": ["Satu ayat."]}]
    design = {"look": "era", "cover": "e_hook", "middle": "e_check", "closing": "e_explain",
              "accent": "#0a7c6e", "paper": "#eaf3f1"}
    kw = dict(look="era", stream="regulab", eyebrow="Kosmetik", source="NPRA", mascots=cards_library.mascots())
    mine = studio_cards.render(deck, design=design, **kw)
    plain = studio_cards.render(deck, **kw)
    assert len(mine) == 3
    assert _near(mine[1], (10, 124, 110)) > 400 and _near(mine[1], (216, 35, 42)) < 100           # teal, no ERA red
    assert _near(plain[1], (216, 35, 42)) > 400 and _near(plain[1], (10, 124, 110)) < 100         # the family's own again
    assert _near(mine[0], (234, 243, 241)) > _near(plain[0], (234, 243, 241))                      # the design's paper
