"""The mode of a film or a post is chosen from the content and rotated (Wan, 10 Nov 2026)."""

import pytest

from semasa import ideas, modes, motion, motion_styles


@pytest.mark.parametrize("text, expected", [
    ("KKM mengumumkan tarik balik produk kosmetik, berkuat kuasa serta-merta", "news"),
    ("Mitos: produk berlabel halal pasti selamat? Betul ke? Tular di media sosial", "myth"),
    ("Cara mendaftar notifikasi kosmetik: langkah demi langkah", "howto"),
    ("Laporan kes: pesakit alami kecederaan mata selepas HIFU, kes di mahkamah", "case"),
    ("Apa itu PIF dan maksud dokumen maklumat produk", "explainer"),
])
def test_the_mode_that_suits_the_content_is_chosen(text, expected):
    mode, why = modes.choose(text, [])
    assert mode == expected, (mode, why)
    assert "content" in why


def test_content_with_no_cue_rotates_through_all_the_modes_least_used_first():
    seen = []
    for _ in range(10):
        mode, why = modes.choose("Produk ini ada di kedai", seen)
        assert "rotated" in why
        seen.insert(0, mode)
    assert set(seen[:5]) == set(modes.MODES), "every mode takes a turn in five"
    assert seen[0] != seen[1], "never the same mode twice running when nothing points at one"


def test_the_same_mode_is_not_used_a_third_time_in_a_row_when_another_fits_nearly_as_well():
    text = "KKM mengumumkan tarik balik produk, kes didakwa di mahkamah"          # news 2, case 2
    mode, _ = modes.choose(text, ["news", "news"])
    assert mode == "case"
    mode, _ = modes.choose(text, ["case", "case"])
    assert mode == "news"
    only_news = "KKM mengumumkan tarik balik produk"
    assert modes.choose(only_news, ["news", "news"])[0] == "news", "a clear fit still wins when nothing else fits"


def test_the_teaser_is_never_chosen_and_a_picked_mode_is_never_overridden():
    assert "teaser" not in modes.MODES
    row = {"id": "r", "options": {"mode": "myth"}}
    assert motion.resolve_mode(object(), row, "KKM mengumumkan tarik balik") == ("myth", "")
    teaser = {"id": "t", "options": {"mode": "teaser"}}
    assert motion.resolve_mode(object(), teaser, "anything")[0] == "teaser"


def test_an_auto_film_gets_its_mode_written_onto_the_row_so_a_redo_keeps_it():
    saved = {}

    class T:
        def update(self, v):
            saved.update(v)
            return self

        def eq(self, *a):
            return self

        def execute(self):
            return self

        def select(self, *a):
            return self

        def order(self, *a, **k):
            return self

        def limit(self, *a):
            return self

        data: list = []

    class Store:
        def table(self, name):
            return T()

    row = {"id": "r1", "options": {"mode": "auto", "design": "blur-full"}}
    mode, why = motion.resolve_mode(Store(), row, "Cara mendaftar notifikasi kosmetik, langkah demi langkah")
    assert mode == "howto" and saved["options"]["mode"] == "howto" and saved["options"]["design"] == "blur-full"
    assert row["options"]["mode"] == "howto" and "content" in saved["options"]["mode_why"]
    assert motion_styles.mode({"options": {"mode": "auto"}}) == "auto" and motion_styles.mode({}) == "auto"


def test_every_mode_shapes_a_post_without_touching_the_voice_or_the_rules():
    for mode in modes.MODES:
        for stream, voice in (("regulab", "SME owners"), ("linkedin", "chemist")):
            block = modes.post_block(mode, stream)
            assert modes.NAMES[mode][1] in block and voice in block
            assert "never licenses a number, date, clause or case the source does not carry" in block
    assert modes.post_block("teaser") == "" and modes.post_block("auto") == ""
    assert ideas.modes is modes
