"""Short-film categories (Wan, 22 Nov 2026): the two built-in categories film exactly what their scripts filmed before the words
moved into rules/short_films.json, Wan's own categories merge over them by id like the comic library, and a category with no
hand-written scenes is written by the writer and checked."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from semasa import nexabot_api_film as api
from semasa import nexabot_cat_film as cat_film
from semasa import nexabot_charsheet as charsheet
from semasa import nexabot_comic_film as comic_film
from semasa import nexabot_film as web_film
from semasa import short_films as sf

ROOT = Path(__file__).resolve().parents[2]

# The words as they stood in the scripts before they moved into the rules file. A built-in film must look the same.
CAT_SHEET = (
    "Photorealistic wildlife-style photograph, three real cats sitting side by side on the wooden steps of a Malaysian "
    "kampung house, facing the camera, soft warm morning light, shallow depth of field, full body of each cat visible: "
    "on the left Comot, a ginger orange tabby with a white chest and green eyes; in the middle Putih, a fluffy pure-white "
    "long-haired cat with blue eyes; on the right Belang, a young black-and-white tuxedo kitten with yellow eyes. "
    "Highly detailed fur, natural proportions, three clearly different cats. "
    "No people, no text, no logo, no watermark, no cartoon, no illustration."
)
CAT_NARRATION = [
    "Pagi di kampung. Comot, si kucing oren, baru bangun, dan dua sahabatnya sudah menunggu.",
    "Bersama Putih dan Belang, dia meronda di tepi sawah, seperti setiap pagi.",
    "Hari ini Comot menjumpai seekor ikan. Walaupun lapar, dia berkongsi dengan kawan-kawannya.",
    "Kerana bagi Comot, kawan yang baik lebih berharga daripada seekor ikan.",
]
CAT_SCENE_1 = (
    "Photorealistic video. Pagi di kampung Malaysia. Comot, kucing oren, menguap dan meregangkan badan di tangga kayu "
    "sebuah rumah kampung. Putih, kucing putih gebu, dan Belang, anak kucing hitam putih, berjalan menghampirinya "
    "dengan ekor tegak. Cahaya matahari pagi yang lembut. Kamera statik, pergerakan semula jadi."
)
FAMILY_SHEET_START = "Photorealistic character sheet, two real people standing side by side, full body, facing the camera, "
FAMILY_SCENE_1_END = "Hana berkata eh logo halal ni ada tarikh luput ke, ingatkan kekal je. Tiada dialog lain. Kamera statik."
SUBTITLES = [
    ("Hana", "Eh, logo halal kat paket ni warna hijau. Bukan sepatutnya hitam ke?"),
    ("Hassan", "Jangan-jangan logo palsu?"),
    ("Hana", "Tak semestinya. Warna bukan penentu."),
    ("Hana", "Pemegang sijil boleh cetak logo ikut warna pembungkusan, asalkan spesifikasi logo tak diubah."),
    ("Hassan", "Mana tulis tu?"),
    ("Hana", "MPPHM (Domestik) 2020, Klausa 40(2)."),
]

RABBITS = {"id": "arnab-di-kebun", "name": "Arnab di kebun", "about": "Dua ekor arnab", "style": "Photorealistic video.",
           "setting": "kebun sayur di belakang rumah kampung", "scene_count": 3,
           "voice": {"mode": "in_prompt", "name": "Aoede", "notes": "lembut"},
           "cast": [{"name": "Tompok", "look": "arnab putih gebu dengan tompok coklat di telinga kiri"},
                    {"name": "Labu", "look": "arnab kelabu kecil dengan ekor putih gebu"}]}


def test_the_cats_film_is_word_for_word_what_it_was():
    assert cat_film.CHAR_SHEET_PROMPT == CAT_SHEET
    assert cat_film.NARRATION == CAT_NARRATION
    assert len(cat_film.SCENES) == 4 and cat_film.SCENES[0] == CAT_SCENE_1
    assert cat_film.FILM_NAME == "kucing-dan-kawan-kawan"
    assert cat_film.plan() == {"scenes": 4, "narration": CAT_NARRATION, "sheet_prompt_chars": len(CAT_SHEET)}


def test_the_halal_family_films_are_word_for_word_what_they_were():
    assert charsheet.CHAR_SHEET_PROMPT.startswith(FAMILY_SHEET_START)
    # the sheet's words live in rules/short_films.json and change by episode (ep4, 22 Nov 2026: a fresh fish and the orange cat);
    # the script's copy must be the file's, word for word, whatever the episode says
    family = next(c for c in sf.RULES["categories"] if c["id"] == "kisah-keluarga-halal")
    assert charsheet.CHAR_SHEET_PROMPT == family["script"]["sheet_prompt"] and "orange cat" in charsheet.CHAR_SHEET_PROMPT
    assert len(api.SCENES) == 2 and api.SCENES[0].endswith(FAMILY_SCENE_1_END)
    assert web_film.SCENES == api.SCENES, "the web route and the API route film the same two scenes"
    assert comic_film.SUBTITLES == SUBTITLES
    assert comic_film.CREDIT == "Sumber: MPPHM (Domestik) 2020, Klausa 40(2)"
    assert api.SHEET == ROOT / "web" / "public" / "comic-panels" / "charsheet.png"


def test_the_two_built_ins_and_their_fields():
    lib = sf.library(None)
    assert [c["id"] for c in lib["categories"]] == ["kisah-keluarga-halal", "cats"] == sf.built_in_ids()
    assert lib["default"] == "cats"
    family, cats = lib["categories"]
    assert family["voice"]["mode"] == "in_prompt" and family["workflow"] == "nexabot-film-api.yml" and family["scene_count"] == 2
    assert cats["voice"] == {"mode": "narrator", "name": "Sulafat", "notes": cats["voice"]["notes"]}
    assert cats["workflow"] == "nexabot-cat-film.yml" and cats["scene_count"] == 4
    assert [p["name"] for p in cats["cast"]] == ["Comot", "Putih", "Belang"]
    assert [p["name"] for p in family["cast"]] == ["Hana", "Hassan"]
    for p in cats["cast"]:
        assert p["look"] in cats["script"]["sheet_prompt"], "the cast and the hand-written sheet say the same thing"
    assert all(c.get("built_in") and not c["hidden"] for c in lib["categories"])


def test_own_categories_merge_by_id_and_never_replace_a_built_in():
    lib = sf.library({"categories": [RABBITS, dict(RABBITS, id="cats", name="Not the cats")], "hidden": ["cats"]})
    assert [c["id"] for c in lib["categories"]] == ["kisah-keluarga-halal", "cats", "arnab-di-kebun"]
    cats = sf.category_of(lib, "cats")
    assert cats["name"]["bm"] == "Kucing (Comot, Putih dan Belang)" and cats["hidden"] and cats.get("script")
    own = sf.category_of(lib, "arnab-di-kebun")
    assert own["own"] and "script" not in own
    assert own["voice"] == {"mode": "narrator", "name": "Aoede", "notes": "lembut"}, "an own category is always narrated"
    assert own["workflow"] == sf.OWN_WORKFLOW and own["scene_count"] == 3
    # a later copy of his own one wins
    lib2 = sf.library({"categories": [RABBITS, dict(RABBITS, about="edited")]})
    assert sf.category_of(lib2, "arnab-di-kebun")["about"]["bm"] == "edited"
    assert len(lib2["categories"]) == 3


@pytest.mark.parametrize("bad", [
    dict(RABBITS, cast=[{"name": "Tompok", "look": ""}]),
    dict(RABBITS, cast=[{"name": "Tompok", "look": "putih"}]),
    dict(RABBITS, cast=[RABBITS["cast"][0], dict(RABBITS["cast"][1], name="tompok")]),
    dict(RABBITS, cast=[{"name": f"K{i}", "look": "seekor kucing oren dengan dada putih"} for i in range(sf.LIMITS["cast"] + 1)]),
    dict(RABBITS, setting=""), dict(RABBITS, style="x"), dict(RABBITS, id="Bad Id"), dict(RABBITS, name="x" * 61),
    dict(RABBITS, cast=[{"name": "Tompok", "look": "a" * (sf.LIMITS["look"] + 1)}]), None, "cats", 7,
])
def test_a_broken_entry_is_left_out_whole(bad):
    assert len(sf.library({"categories": [bad]})["categories"]) == 2


def test_sanitise_and_caps():
    look = "arnab putih\u2028gebu dengan tompok coklat"
    raw = dict(RABBITS, name="  Arnab\n di\tkebun  ", scene_count=99, cast=[{"name": "Tompok", "look": look}])
    c = sf.clean_category(raw)
    assert c["name"] == {"bm": "Arnab di kebun", "en": "Arnab di kebun"}
    assert c["cast"][0]["look"] == "arnab putih gebu dengan tompok coklat"
    assert c["scene_count"] == sf.LIMITS["scenes_max"]
    assert sf.clean_category(dict(RABBITS, scene_count="x"))["scene_count"] == 4
    many = [dict(RABBITS, id=f"arnab-{i}") for i in range(sf.LIMITS["own"] + 5)]
    assert len(sf.library({"categories": many})["categories"]) == 2 + sf.LIMITS["own"]
    assert sf.library({"default": "nope"})["default"] == "cats"
    assert sf.library({"categories": [RABBITS], "default": "arnab-di-kebun"})["default"] == "arnab-di-kebun"


def test_the_page_and_the_worker_read_one_file():
    rules = json.loads((ROOT / "rules" / "short_films.json").read_text("utf-8"))
    page = (ROOT / "web" / "src" / "lib" / "shortFilms.js").read_text("utf-8")
    assert 'import RULES from "../../../rules/short_films.json"' in page
    assert rules["limits"] == sf.LIMITS
    assert "'short_films'" in (ROOT / "supabase" / "090_short_films.sql").read_text("utf-8")


class FakeLLM:
    configured = True

    def __init__(self, answers):
        self.answers = list(answers)
        self.asked: list[str] = []

    def chat_json(self, system, user, **_):
        self.asked.append(user)
        return self.answers.pop(0) if self.answers else None


def _scenes(n, narration="Tompok dan Labu bermain di kebun pada waktu pagi."):
    action = "Tompok dan Labu melompat di antara batas sayur, babak {}."
    return {"title": "Pagi di kebun",
            "scenes": [{"action": action.format(chr(97 + i)), "narration": narration} for i in range(n)]}


def test_a_category_without_scenes_is_written_with_its_cast_word_for_word_in_every_scene():
    cat = sf.category_of(sf.library({"categories": [RABBITS]}), "arnab-di-kebun")
    llm = FakeLLM([_scenes(3)])
    script = sf.film_script(cat, llm=llm, topic="hari hujan")
    assert script["written"] and script["title"] == "Pagi di kebun"
    assert len(script["scenes"]) == 3 and len(script["narration"]) == 3
    for prompt in script["scenes"]:
        assert prompt.startswith("Photorealistic video. Tempat: kebun sayur di belakang rumah kampung.")
        for p in RABBITS["cast"]:
            assert f"{p['name']}: {p['look']}" in prompt
        assert "Tiada teks" in prompt
    assert "arnab putih gebu dengan tompok coklat di telinga kiri" in script["sheet_prompt"]
    assert "hari hujan" in llm.asked[0]


@pytest.mark.parametrize("first, reason", [
    (_scenes(2), "not 3"),
    (_scenes(3, narration="Tompok makan 5 lobak hari ini."), "figure"),
    (_scenes(3, narration="x" * 150), "longer"),
])
def test_a_refused_script_is_asked_for_once_more_with_the_reason(first, reason):
    cat = sf.category_of(sf.library({"categories": [RABBITS]}), "arnab-di-kebun")
    llm = FakeLLM([first, _scenes(3)])
    assert sf.film_script(cat, llm=llm)["written"]
    assert reason in llm.asked[1]
    with pytest.raises(sf.FilmError, match="refused twice"):
        sf.film_script(cat, llm=FakeLLM([first, first]))


def test_dashes_and_indonesian_are_edited_out_of_what_the_narrator_says():
    cat = sf.category_of(sf.library({"categories": [RABBITS]}), "arnab-di-kebun")
    script = sf.film_script(cat, llm=FakeLLM([_scenes(3, narration="Tompok mau bermain \u2014 di kebun.")]))
    assert all("\u2014" not in n and "mau" not in n.split() for n in script["narration"])


def test_a_writer_that_is_off_or_silent_is_a_reason_not_a_crash():
    cat = sf.category_of(sf.library({"categories": [RABBITS]}), "arnab-di-kebun")
    with pytest.raises(sf.FilmError, match="writer is off"):
        sf.film_script(cat, llm=None)
    with pytest.raises(sf.FilmError, match="did not answer"):
        sf.film_script(cat, llm=FakeLLM([None]))


def test_the_cat_film_takes_any_narrated_category(monkeypatch):
    lib = sf.library({"categories": [RABBITS]})
    try:
        script = cat_film.use("arnab-di-kebun", "", lib=lib, llm=FakeLLM([_scenes(3)]))
        assert script["written"] and cat_film.FILM_NAME == "arnab-di-kebun" and len(cat_film.SCENES) == 3
        assert cat_film.plan()["scenes"] == 3
        with pytest.raises(sf.FilmError, match="nexabot-film-api.yml"):
            cat_film.use("kisah-keluarga-halal", lib=lib)
        with pytest.raises(sf.FilmError, match="no short-film category"):
            cat_film.use("nope", lib=lib)
        # a built-in category needs no database and no writer
        monkeypatch.setattr(cat_film, "own_library", lambda: pytest.fail("a built-in category read the database"))
        monkeypatch.setattr(cat_film, "writer", lambda: pytest.fail("a built-in category asked the writer"))
        assert not cat_film.use("cats")["written"]
        assert cat_film.CHAR_SHEET_PROMPT == CAT_SHEET and cat_film.NARRATION == CAT_NARRATION
    finally:
        cat_film.use("cats")


def test_the_cat_film_dry_run_for_a_built_in(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["x", str(tmp_path), "--dry"])
    assert cat_film.main() == 0
    report = json.loads((tmp_path / "report.json").read_text("utf-8"))
    assert report["voice"] == "Sulafat" and report["plan"]["narration"] == CAT_NARRATION
    monkeypatch.setattr("sys.argv", ["x", str(tmp_path), "--category", "kisah-keluarga-halal", "--dry"])
    assert cat_film.main() == 2
    assert "nexabot-film-api.yml" in json.loads((tmp_path / "report.json").read_text("utf-8"))["failed"]
    cat_film.use("cats")


def test_the_api_film_refuses_a_category_it_cannot_film():
    with pytest.raises(SystemExit, match="nexabot-cat-film.yml"):
        api.use("cats")
    with pytest.raises(SystemExit, match="no built-in"):
        api.use("nope")


def test_panel_lines_spread_over_the_clips():
    assert comic_film.spread(6, 4) == {0: [0], 1: [1, 2], 2: [3], 3: [4, 5]}
    assert comic_film.spread(5, 2) == {0: [0, 1, 2], 1: [3, 4]}
    assert comic_film.spread(0, 3) == {0: [], 1: [], 2: []}
    assert comic_film.lines_of("cats") == ([], "")


def test_the_workflows_take_the_category_as_an_input_through_an_env_var():
    import re
    for name, default in (("nexabot-cat-film", "cats"), ("nexabot-film-api", "kisah-keluarga-halal"),
                          ("nexabot-comic-film", "kisah-keluarga-halal")):
        text = (ROOT / ".github" / "workflows" / f"{name}.yml").read_text("utf-8")
        assert re.search(r"\n      category:\n(?:        .*\n)*?        default: \"" + re.escape(default) + '"', text), name
        assert "NB_CATEGORY: ${{ inputs.category }}" in text
        runs = re.findall(r"\n        run: \|\n((?:          .*\n)+)|\n        run: (.*)", text)
        assert runs and not any("${{" in a + b for a, b in runs), f"{name}: an input reaches the shell only through an env var"
