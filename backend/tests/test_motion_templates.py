"""Motion's two film templates (Wan, 7 Nov 2026: "buatkan motion boleh buat macam ni, storyboard dari gemini, picture from chatgpt
or cloudflare"): a product showcase and a photo story. Fakes only: nothing here reaches Gemini, OpenAI, Cloudflare or Unsplash."""
from __future__ import annotations

import io
import os
import re

import pytest
from fakestore import FakeStore
from PIL import Image

from semasa import motion, motion_gpt_images
from semasa import motion_templates as T

STORY = {"title": "Malaysia", "subtitle": "Tempat yang patut diingati", "hook_shape": 1,
         "hook": "Takde sapa cakap pasal kabus pagi tapi ni sebab aku balik", "photo_query": "malaysia rainforest",
         "scenes": [{"caption": f"Sudut nombor {i}", "prompt": "A misty rainforest at sunrise, tall trees, soft light rays, "
                     "wide upright frame", "accent": c} for i, c in enumerate(("#6f8fb8", "#e0b04f", "#4f9f8f", "#47b5b8",
                                                                                 "#c06a3a"), 1)]}
SHOW = {"title": "Serum harian", "hook_shape": 1, "hook": "Takde sapa cakap pasal serum pagi tapi ni sebab aku tukar",
        "headline": ["SAINS", "KULIT"], "caption": "Tiga pilihan untuk rutin pagi",
        "background": "Sunlit pale blue water caustics over a soft surface, palm leaf shadows, glass bubbles, empty centre",
        "products": [{"name": "Serum Satu", "benefits": ["Tanpa pewangi"], "accent": "#d0335f"},
                     {"name": "Serum Dua", "benefits": ["Ringan", "Tidak melekit"], "accent": "#3aa36b"}]}
PRODUCTS = [{"name": "", "benefits": "", "media_id": "m1", "ref": None},
            {"name": "", "benefits": "", "media_id": "m2", "ref": None}]
ROW = {"id": "f1", "stream": "regulab", "language": "bm", "brief": "kosmetik harian", "created_by": "u1"}


def png(side=300, mode="RGB"):
    buf = io.BytesIO()
    Image.frombytes(mode, (side, side), os.urandom(side * side * len(mode))).save(buf, "PNG")
    return buf.getvalue()


def visible_text(html):
    body = re.sub(r"<(script|style|title)[^>]*>.*?</\1>", "", html, flags=re.S)
    return [t.strip() for t in re.split(r"<[^>]+>", body) if t.strip()]


# ---- which films are templates ---------------------------------------------------------------------------------------------

def test_a_template_is_read_from_the_row_options_and_anything_else_is_an_explainer():
    assert T.template_of({"options": {"template": "showcase"}}) == "showcase"
    assert T.template_of({"options": {"template": "story"}}) == "story"
    assert T.template_of({"options": {"template": "nope"}}) == ""
    assert T.template_of({"options": {}}) == "" and T.template_of({}) == ""


def test_process_hands_a_template_film_to_the_template_path_and_an_explainer_never(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(motion, "template_film", lambda store, llm, row, *a, **k: seen.append(row["id"]) or True)
    store = FakeStore(semasa_motions=[{"id": "t1", "status": "working"}])
    assert motion.process(store, None, {"id": "t1", "options": {"template": "story"}}, {"cli": "x"}, workdir=tmp_path)
    assert seen == ["t1"]


# ---- the storyboard is strict JSON, checked by code -----------------------------------------------------------------------

def test_a_good_story_storyboard_passes_and_its_first_caption_is_the_hook():
    sb = T.validate_story(STORY, lang="bm", stream="regulab")
    assert len(sb["scenes"]) == 5 and sb["scenes"][0]["caption"] == STORY["hook"] and sb["hook_shape"] == 1


@pytest.mark.parametrize("change, why", [
    ({"scenes": STORY["scenes"][:4]}, "exactly 5"),
    ({"hook_shape": 999}, "hook_shape"),
    ({"hook": "Takde sapa cakap pasal ___ tapi"}, "hook_shape"),
    ({"title": "Satu dua tiga empat lima enam"}, '"title"'),
    ({"subtitle": "Lihat www.contoh.com sekarang"}, "link"),
])
def test_a_story_storyboard_with_a_wrong_field_is_refused_with_the_reason(change, why):
    with pytest.raises(T.StoryboardError, match=re.escape(why)):
        T.validate_story({**STORY, **change}, lang="bm", stream="regulab")


def test_a_scene_colour_must_be_a_real_colour_and_never_black_or_white():
    bad = {**STORY, "scenes": [{**STORY["scenes"][0], "accent": "blue"}, *STORY["scenes"][1:]]}
    with pytest.raises(T.StoryboardError, match="colour"):
        T.validate_story(bad, lang="bm", stream="regulab")
    white = {**STORY, "scenes": [{**STORY["scenes"][0], "accent": "#FFFFFF"}, *STORY["scenes"][1:]]}
    with pytest.raises(T.StoryboardError, match="black or white"):
        T.validate_story(white, lang="bm", stream="regulab")


def test_a_showcase_storyboard_needs_one_entry_per_product_and_the_users_own_words_win():
    with pytest.raises(T.StoryboardError, match="exactly 3"):
        T.validate_showcase(SHOW, PRODUCTS + [PRODUCTS[0]], lang="bm", stream="regulab")
    mine = [{**PRODUCTS[0], "name": "Nama Saya", "benefits": "Satu, Dua"}, PRODUCTS[1]]
    sb = T.validate_showcase(SHOW, mine, lang="bm", stream="regulab")
    assert sb["products"][0]["name"] == "Nama Saya" and sb["products"][0]["benefits"] == ["Satu", "Dua"]
    assert sb["products"][1]["name"] == "Serum Dua" and sb["products"][1]["accent"] == "#3aa36b"


def test_a_background_prompt_that_asks_for_a_label_or_a_cure_is_refused():
    with pytest.raises(T.StoryboardError, match="never show"):
        T.validate_showcase({**SHOW, "background": "A clean bench with the product label and a cure for acne shown big"},
                            PRODUCTS, lang="bm", stream="regulab")


def test_the_storyboard_prompt_asks_for_strict_json_the_hook_shapes_and_the_product_count():
    system = T.system_for("showcase", count=3, lang="bm", stream="regulab")
    assert "EXACTLY 3" in system and "hook_shape" in system and "Malaysia" in system and "bertemu" in system
    assert "EXACTLY 5" in T.system_for("story", count=0, lang="en", stream="linkedin")


class Writer:
    def __init__(self, answers):
        self.answers, self.asked = list(answers), []

    def chat_json(self, system, user, max_tokens=0):
        self.asked.append(user)
        return self.answers.pop(0) if self.answers else {}


class Login:
    def __init__(self, text=None, cfg=None):
        self.text, self.cfg, self.wrote = text, cfg if cfg is not None else {"enabled": True, "model": "m", "max_images": 6}, 0

    def settings(self):
        return self.cfg

    def write(self, system, user, *, model):
        self.wrote += 1
        return self.text

    def ok(self):
        pass

    def failed(self, message):
        pass


def test_gemini_writes_the_storyboard_first_and_the_others_are_not_asked():
    gem, gpt, own = Writer([STORY]), Login(text="{}"), Writer([STORY])
    sb, note = T.write_storyboard(None, ROW, "story", [], {}, gemini_llm=gem, login=gpt, llm=own)
    assert note.startswith("Storyboard by Gemini") and sb["title"] == "Malaysia"
    assert gpt.wrote == 0 and own.asked == []


def test_a_refused_gemini_answer_is_asked_once_more_with_the_reason_then_chatgpt_takes_over():
    import json
    gem, gpt = Writer([{"title": "x"}, {"title": "y"}]), Login(text=json.dumps(STORY))
    sb, note = T.write_storyboard(None, ROW, "story", [], {}, gemini_llm=gem, login=gpt, llm=None)
    assert len(gem.asked) == 2 and "YOUR LAST ANSWER WAS REFUSED" in gem.asked[1]
    assert gpt.wrote == 1 and note.startswith("Storyboard by ChatGPT") and "Gemini:" in note


def test_the_films_own_writer_is_last_and_no_usable_answer_stops_the_film_with_the_reasons():
    sb, note = T.write_storyboard(None, ROW, "story", [], {}, gemini_llm=Writer([{}, {}]), login=Login(cfg={}),
                                  llm=Writer([STORY]))
    assert note.startswith("Storyboard by the film's writer")
    with pytest.raises(RuntimeError, match="no writer gave a usable storyboard"):
        T.write_storyboard(None, ROW, "story", [], {}, gemini_llm=Writer([]), login=None, llm=None)


# ---- pictures: ChatGPT, then Cloudflare, then Gemini, then Unsplash -------------------------------------------------------

class Maker:
    def __init__(self, name, log, fail=False, ready=True):
        self.name, self.log, self.fail, self._ready = name, log, fail, ready

    def ready(self):
        return self._ready

    def max_images(self):
        return 6

    def settings(self):
        return {"enabled": self._ready, "model": "m", "max_images": 6}

    def draw(self, prompt, **kw):
        self.log.append(self.name)
        if self.fail:
            raise RuntimeError(f"{self.name} down")
        return png()

    def ok(self):
        pass

    def failed(self, message):
        pass


def test_template_pictures_ask_chatgpt_then_cloudflare_then_gemini(tmp_path):
    log = []
    paths, source, note = T.draw(None, ROW, "story", T.validate_story(STORY, lang="bm", stream="regulab"), tmp_path,
                                 login=Maker("chatgpt", log, fail=True), cloudflare=Maker("cloudflare", log, fail=True),
                                 gemini=Maker("gemini", log), search=lambda *a: [], get=None)
    assert log[:3] == ["chatgpt", "cloudflare", "gemini"]
    assert len(paths) == 5 and set(source.values()) == {"ai"}
    assert T.ORDER == ("chatgpt", "cloudflare", "gemini")
    assert motion_gpt_images.ORDER == ("chatgpt", "gemini", "cloudflare"), "an explainer keeps its own order"


def test_unsplash_fills_what_no_picture_maker_drew_and_the_footer_says_so(tmp_path):
    log = []
    photos = [{"id": f"u{i}", "name": "Aminah"} for i in range(5)]
    paths, source, note = T.draw(None, ROW, "story", T.validate_story(STORY, lang="bm", stream="regulab"), tmp_path,
                                 login=Maker("chatgpt", log, ready=False), cloudflare=Maker("cloudflare", log, ready=False),
                                 gemini=Maker("gemini", log, ready=False), search=lambda q, o: photos, get=lambda p: png())
    assert len(paths) == 5 and all(v.startswith("assets/unsplash-") for v in paths.values())
    footer = T.story_footer(source, "bm")
    assert "Unsplash" in footer and "Aminah" in footer and "DIJANA AI" not in footer
    assert T.story_footer({"p1": "ai"}, "en") == "IMAGES GENERATED WITH AI"
    assert T.story_footer({}, "en") == ""


def test_the_showcase_draws_only_its_background_never_a_product(tmp_path):
    log = []
    sb = T.validate_showcase(SHOW, PRODUCTS, lang="bm", stream="regulab")
    prompts = []
    maker = Maker("chatgpt", log)
    maker.draw = lambda prompt, **kw: prompts.append(prompt) or png()
    paths, source, _ = T.draw(None, ROW, "showcase", sb, tmp_path, login=maker, cloudflare=Maker("c", log, ready=False),
                              gemini=Maker("g", log, ready=False))
    assert list(paths) == ["bg"] and source["bg"] == "ai" and len(prompts) == 1
    assert "No product, no bottle" in prompts[0]


# ---- the user's own product pictures and the brand -------------------------------------------------------------------------

def test_a_showcase_needs_one_to_five_products_each_with_its_own_picture():
    for products in ([], [{"media_id": "a"}] * 6, [{"name": "x"}], [{"media_id": "../etc"}]):
        with pytest.raises(ValueError):
            T.products_of({"options": {"products": products}})
    assert T.products_of({"options": {"products": [{"media_id": "m1", "name": " A  B "}]}})[0]["name"] == "A B"


def test_a_library_picture_is_fetched_from_the_address_in_the_database_never_from_the_browser(tmp_path):
    store = FakeStore(media_generations=[{"id": "m1", "status": "done", "type": "image", "generated_media_url": "https://s/1.png"},
                                         {"id": "m2", "status": "pending", "type": "image", "generated_media_url": "https://s/2"}])
    fetched = []
    out = T.product_pictures(store, ROW, [{"media_id": "m1", "ref": None, "url": "https://evil"}], tmp_path,
                             get=lambda url: fetched.append(url) or png(mode="RGBA"))
    assert out == ["assets/product-1.jpg"] and fetched == ["https://s/1.png"]
    assert Image.open(tmp_path / out[0]).mode == "RGB"
    with pytest.raises(ValueError, match="Product 1"):
        T.product_pictures(store, ROW, [{"media_id": "m2", "ref": None}], tmp_path, get=lambda url: png())


def test_an_uploaded_product_picture_must_be_the_creators_own_private_image(tmp_path):
    data = png()
    ref = {"path": "u1/abc-bottle.png", "mime": "image/png", "size": len(data), "rights": "self-owned"}
    out = T.product_pictures(FakeStore(), ROW, [{"media_id": "", "ref": ref}], tmp_path, download=lambda path: data)
    assert out == ["assets/product-1.jpg"]
    with pytest.raises(ValueError):
        T.product_pictures(FakeStore(), ROW, [{"media_id": "", "ref": {**ref, "path": "someone/abc.png"}}], tmp_path,
                           download=lambda path: data)
    with pytest.raises(ValueError):
        T.product_pictures(FakeStore(), ROW, [{"media_id": "", "ref": {**ref, "rights": ""}}], tmp_path, download=lambda p: data)


def test_the_brand_is_the_chosen_business_and_linkedin_never_wears_ws_regulab(tmp_path):
    kedai = {"id": "kedai", "name": "Kedai Ujian", "billing": {"company": {"tagline": "Dari dapur"}}}
    store = FakeStore(semasa_businesses=[kedai])
    other = T.brand_of(store, {**ROW, "options": {"brand": {"business_id": "kedai"}}}, tmp_path)
    assert other == {"id": "kedai", "name": "Kedai Ujian", "tagline": "Dari dapur", "logo": ""}
    own = T.brand_of(FakeStore(), {**ROW, "options": {"brand": {"tagline": "Taip sendiri"}}}, tmp_path)
    assert own["logo"] == "assets/brand-logo.png" and own["tagline"] == "Taip sendiri"
    assert T.brand_of(FakeStore(), {**ROW, "stream": "linkedin"}, tmp_path)["logo"] == ""


# ---- the compositions ------------------------------------------------------------------------------------------------------

def test_the_photo_story_has_five_photos_a_counter_on_each_and_a_dark_closing_card():
    sb = T.validate_story(STORY, lang="bm", stream="regulab")
    html, total = T.compose_story(sb, [f"assets/p{i}.jpg" for i in range(1, 6)], lang="bm", footer="GAMBAR DIJANA AI")
    assert total == 20.0 and 'data-duration="20"' in html
    assert len(re.findall(r'class="clip ph"', html)) == 5
    for i in range(1, 6):
        assert f"0{i} / 05" in html
    assert "#0b0f17" in html and "GAMBAR DIJANA AI" in html and html.count('class="eb"') == 5
    assert "window.__timelines" in html and "Math.random" not in html and "<img" not in html


def test_one_story_scenes_words_never_share_the_screen_with_the_next_ones():
    sb = T.validate_story(STORY, lang="bm", stream="regulab")
    html, _ = T.compose_story(sb, [], lang="en", footer="")
    spans = [(float(a), float(a) + float(b)) for a, b in
             re.findall(r'class="clip tx" id="t\d" data-start="([\d.]+)" data-duration="([\d.]+)"', html)]
    assert len(spans) == 5 and all(spans[i][1] <= spans[i + 1][0] + 1e-9 for i in range(4))
    assert "IMAGES GENERATED" not in html, "no pictures were generated, so no AI line"


def test_the_showcase_has_an_intro_one_scene_per_product_a_finale_and_the_ai_line_only_when_true():
    sb = T.validate_showcase(SHOW, PRODUCTS, lang="en", stream="regulab")
    brand = {"name": "Kedai Ujian", "tagline": "", "logo": ""}
    html, total = T.compose_showcase(sb, ["assets/product-1.jpg", "assets/product-2.jpg"], "assets/bg.jpg", brand, lang="en",
                                     ai_background=True)
    assert total == T.seconds_of("showcase", 2)
    assert re.findall(r'class="clip" id="(\w+)"', html) == ["bg", "intro", "p1", "p2", "fin"]
    assert "BACKGROUNDS GENERATED WITH AI" in html and ">meets<" in html
    plain, _ = T.compose_showcase(sb, ["a.jpg", "b.jpg"], "", brand, lang="en", ai_background=False)
    assert "GENERATED WITH AI" not in plain


def test_three_products_make_the_reference_films_twenty_seconds():
    assert T.seconds_of("showcase", 3) == 20.0 and T.seconds_of("story") == 20.0


def test_every_word_on_a_showcase_is_the_users_or_the_storyboards_and_no_brand_is_built_in():
    sb = T.validate_showcase(SHOW, PRODUCTS, lang="bm", stream="regulab")
    brand = {"name": "Kedai Ujian", "tagline": "Dari dapur", "logo": ""}
    html, _ = T.compose_showcase(sb, ["a.jpg", "b.jpg"], "bg.jpg", brand, lang="bm", ai_background=True)
    allowed = {sb["title"], sb["hook"], sb["caption"], brand["name"], brand["tagline"], "bertemu", "LATAR DIJANA AI",
               *sb["headline"], *(p["name"] for p in sb["products"]), *(" · ".join(p["benefits"]) for p in sb["products"])}
    assert set(visible_text(html)) <= allowed
    tid = re.compile(r'tl\.\w+\("#([\w-]+)"')
    assert all(f'id="{m}"' in html for m in tid.findall(html)), "every tween names an element that exists"


def test_the_script_kept_on_the_row_shows_the_planned_scenes_with_the_hook_shape():
    story = T.script_of("story", T.validate_story(STORY, lang="bm", stream="regulab"), "bm")
    assert len(story) == 6 and story[0]["hook_shape"] == 1 and story[0]["shot"]
    show = T.script_of("showcase", T.validate_showcase(SHOW, PRODUCTS, lang="bm", stream="regulab"), "bm")
    assert [s["id"] for s in show] == ["intro", "p1", "p2", "finale"] and "bertemu" in show[-1]["heading"]
