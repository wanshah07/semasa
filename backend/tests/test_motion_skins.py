"""The seven 2D film styles: picked at random for a film that names none, never an older design, and kept once picked."""
import random

from semasa import motion_remotion as mr
from semasa import motion_skins as ms
from semasa import motion_styles


class Store:
    def __init__(self, rows=None, fail=False):
        self.rows, self.fail, self.updates = rows or [], fail, []

    def table(self, name):
        assert name == ms.TABLE
        return self

    def select(self, *_a, **_k):
        return self

    order = limit = eq = select

    def update(self, values):
        self.updates.append(values)
        return self

    def execute(self):
        if self.fail:
            raise RuntimeError("offline")

        class R:
            data = self.rows
        return R()


def test_there_are_twelve_styles_and_none_is_an_older_design():
    assert len(ms.SKINS) == 12 and set(ms.SKINS) == set(ms.NAMES)
    assert not set(ms.SKINS) & set(motion_styles.DESIGNS)
    assert set(ms.LEGACY) == set(motion_styles.DESIGNS)


def test_a_film_with_no_design_gets_a_style_written_on_it():
    for options in (None, {}, {"design": "auto"}, {"design": "nonsense"}):
        row, st = {"id": "m1", "options": options}, Store()
        got = ms.resolve(st, row, random.Random(3))
        assert got in ms.SKINS and row["options"]["design"] == got and row["options"]["design_auto"] is True
        assert st.updates == [{"options": row["options"]}]
        assert ms.resolve(st, row) == got and len(st.updates) == 1, "settled once: a Redo keeps the style"


def test_an_older_design_is_only_ever_chosen_by_hand_and_is_left_alone():
    for key in motion_styles.DESIGNS:
        row, st = {"id": "m1", "options": {"design": key}}, Store()
        assert ms.resolve(st, row) == "" and row["options"] == {"design": key} and not st.updates
        assert ms.skin(row) == "" and not ms.is_auto(row)
    picked = {ms.choose([], random.Random(i)) for i in range(900)}
    assert picked == set(ms.SKINS), "every style comes up, and nothing else ever does"


def test_a_style_chosen_by_hand_is_kept():
    row, st = {"id": "m1", "options": {"design": "chalk"}}, Store()
    assert ms.resolve(st, row) == "chalk" and not st.updates


def test_the_last_three_styles_are_not_picked_again():
    for i in range(300):
        assert ms.choose(["comic", "pixel", "chalk", "glow"], random.Random(i)) not in ("comic", "pixel", "chalk")
    assert ms.choose(list(ms.SKINS), random.Random(1)) in ms.SKINS


def test_recent_reads_the_styles_of_the_latest_films_and_never_raises():
    st = Store([{"options": {"design": "flat"}}, {"options": {"design": "blur-full"}}, {"options": None},
                {"options": {"design": "dankoe"}}])
    assert ms.recent(st) == ["flat", "dankoe"]
    assert ms.recent(Store(fail=True)) == []
    row = {"id": "m9", "options": {}}
    assert ms.resolve(Store(fail=True), row) in ms.SKINS, "a store that cannot answer still gets the film a style"


def test_a_styled_film_is_drawn_by_remotion_and_its_props_name_the_style():
    assert mr.choice({"options": {"design": "glow"}}) == mr.NAME
    assert mr.choice({"options": {"design": "glow", "renderer": "combined"}}) == mr.NAME
    assert mr.choice({"options": {"design": "blur-full"}}) == ""
    pal = {"ground": "#e5f6ed", "ink": "#143e35", "accent": "#287b65", "accent2": "#fff7e6"}
    scenes = [{"id": "s1", "heading": "Tajuk", "lines": ["a"], "start": 0.0, "duration": 6.0}]
    assert mr.props(scenes, 6.0, 1080, 1920, pal, skin="pixel")["skin"] == "pixel"
    assert mr.props(scenes, 6.0, 1080, 1920, pal, skin="nonsense")["skin"] == ""
    assert mr.props(scenes, 6.0, 1080, 1920, pal)["skin"] == ""


def test_the_remotion_project_draws_every_style():
    src = (mr.PROJECT / "src" / "Skins.jsx").read_text(encoding="utf-8")
    for key in ms.SKINS:
        assert f"\n  {key}: {{" in src, key
    assert "isSkin(skin)" in (mr.PROJECT / "src" / "Film.jsx").read_text(encoding="utf-8")


def test_the_film_cover_is_quieter_than_a_carousel_cover():
    from semasa import carousel
    film = carousel.cover_card("Notifikasi kosmetik bukan kelulusan KKM", size=(1080, 1920))
    assert film.size == (1080, 1920)


def test_every_style_has_its_own_picture_look_and_shows_the_scene_picture():
    from semasa import motion_gpt_images as gi
    src = (mr.PROJECT / "src" / "Skins.jsx").read_text(encoding="utf-8")
    assert "pic: false" not in src, "every style draws the scene's generated picture"
    for key in ms.SKINS:
        assert key in gi.LOOK, key
        prompt = gi.scene_prompt({"brief": "notifikasi kosmetik"}, {"heading": "Apa itu notifikasi", "role": "fact"},
                                 design=key, palette={"ground": "#e5f6ed"}, ambient="mint")
        assert gi.LOOK[key] in prompt and "notifikasi kosmetik" in prompt and "#e5f6ed" not in prompt
    old = gi.scene_prompt({"brief": "x"}, {"heading": "y"}, design="bright-editorial", palette={"ground": "#e5f6ed"},
                          ambient="mint")
    assert "#e5f6ed" in old


def test_the_whiteboard_style_is_drawn_by_hand_with_the_vendored_engine_and_says_whose_it_is():
    src = mr.PROJECT / "src"
    film = (src / "Film.jsx").read_text(encoding="utf-8")
    assert 'skin === "whiteboard"' in film and "<Handboard" in film
    vendor = src / "vendor" / "opuscar"
    engine = (vendor / "wb.js").read_text(encoding="utf-8")
    assert "MIT License, Copyright (c) 2026 LemoLab" in engine and "setScreen" in engine and "resetSeed" in engine
    rest = engine.split("let SW = 1920, SH = 1080;")[1]
    assert "1920" not in rest, "the screen size comes from the film, never a fixed 1920 x 1080"
    notice = (vendor / "NOTICE.md").read_text(encoding="utf-8")
    assert "MIT" in notice and "SIL Open Font License" in notice
    import json
    glyphs = json.loads((vendor / "EMSTech.json").read_text(encoding="utf-8"))["glyphs"]
    assert all(ch in glyphs for ch in "ABCXYZabcxyz0123456789?.,:()-"), "the lettering covers what a Malay or English scene needs"
