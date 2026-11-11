"""The mode of a film or a post is chosen from the content and rotated (Wan, 10 Nov 2026)."""

import pytest

from semasa import ideas, modes, motion, motion_styles


@pytest.mark.parametrize("text, expected", [
    ("KKM mengumumkan tarik balik produk kosmetik, berkuat kuasa serta-merta", "news"),
    ("Mitos: produk berlabel halal pasti selamat? Betul ke? Tular di media sosial", "myth"),
    ("Cara mendaftar notifikasi kosmetik: langkah demi langkah", "howto"),
    ("Laporan kes: pesakit alami kecederaan mata selepas HIFU, kes di mahkamah", "case"),
    ("Apa itu PIF dan maksud dokumen maklumat produk", "explainer"),
    # the eight modes added 11 Nov 2026
    ("Serum vitamin C vs retinol: mana lebih baik untuk kulit sensitif", "compare"),
    ("Dahulu had 0.5% kini 0.3%, peraturan baharu menggantikan yang lama", "change"),
    ("Apa maksud singkatan INCI pada label kosmetik?", "define"),
    ("Boleh ke jual produk tanpa notifikasi?", "decide"),
    ("Kesilapan biasa semasa mendaftar notifikasi kosmetik", "mistake"),
    ("Senarai semak sebelum eksport kosmetik ke China", "checklist"),
    ("Statistik: berapa ramai pengguna alami ruam selepas guna produk ini", "number"),
    ("Soalan lazim tentang label halal untuk produk import", "qna"),
])
def test_the_mode_that_suits_the_content_is_chosen(text, expected):
    mode, why = modes.choose(text, [])
    assert mode == expected, (mode, why)
    assert "content" in why


def test_content_with_no_cue_rotates_through_all_the_modes_least_used_first():
    seen = []
    for _ in range(2 * len(modes.MODES)):
        mode, why = modes.choose("Produk ini ada di kedai", seen)
        assert "rotated" in why
        seen.insert(0, mode)
    assert set(seen[:len(modes.MODES)]) == set(modes.MODES), "every mode takes a turn before any repeats"
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


def test_there_are_thirteen_modes_each_with_a_name_in_both_languages_and_the_original_five_keep_their_places():
    assert modes.MODES[:5] == ("explainer", "news", "myth", "howto", "case")
    assert len(modes.MODES) == len(set(modes.MODES)) == 13
    for mode in modes.MODES:
        bm, en = modes.NAMES[mode]
        assert bm and en and modes.name(mode, bm=True) == bm and modes.name(mode) == en
    assert motion_styles.MODES == ("auto", *modes.MODES, "teaser") and motion.MODES == modes.MODES


def test_a_checklist_cue_no_longer_makes_a_how_to():
    assert modes.choose("Senarai semak dokumen sebelum mohon", [])[0] == "checklist"
