"""antislop.py: the machine-safe edits, the tells that need a person, and where the rules are handed to the writers."""

from semasa import antislop, ideas, motion


def test_an_em_dash_becomes_a_comma_or_a_full_stop_and_nothing_else_moves():
    assert antislop.clean("The policy — announced without warning — affects workers.") == \
        "The policy, announced without warning, affects workers."
    assert antislop.clean("Notifikasi bukan kelulusan — NPRA menyemak selepas dipasarkan.") == \
        "Notifikasi bukan kelulusan, NPRA menyemak selepas dipasarkan."
    assert antislop.clean("Lalu -- selepas itu -- siap.") == "Lalu, selepas itu, siap."
    text = "NPRA.600-1/9/13(13)Jld.2 dalam 2020–2025 dan 3-5 hari."
    assert antislop.clean(text) == text, "a hyphen, a figure range and a reference number are not slop"
    assert antislop.clean("") == "" and antislop.clean("Bersih sahaja.") == "Bersih sahaja."


def test_a_decorative_emoji_that_opens_a_line_goes_and_an_inline_one_stays():
    got = antislop.clean("\U0001F680 Pelancaran bulan depan\n\U0001F4A1 Pengguna suka harga mudah\nTerima kasih \U0001F64F")
    assert got == "Pelancaran bulan depan\nPengguna suka harga mudah\nTerima kasih \U0001F64F"


def test_chatbot_closers_openers_and_filler_are_cut_without_adding_a_word():
    said = "Here is our pricing. The Starter tier has three seats. I hope this helps! Let me know if you need more."
    assert antislop.clean(said) == "Here is our pricing. The Starter tier has three seats."
    assert antislop.clean("Let's dive in. Next.js caches data at several layers.") == "Next.js caches data at several layers."
    assert antislop.clean("In order to reach this goal, it is important to note that we need more data.") == \
        "To reach this goal, we need more data."
    assert antislop.clean("Dalam usaha untuk lulus, semak label.") == "Untuk lulus, semak label."
    assert antislop.clean("Harap membantu.") == ""


def test_the_tells_that_need_a_person_are_named_from_the_shared_rules():
    found = antislop.tells("Unlock the power of seamless collaboration. Honestly? It's not just a tool, it's a command center.")
    assert any("empty AI vocabulary" in x for x in found) and any("fake-candid" in x for x in found)
    assert any("not just X" in x for x in found)
    assert any("BM" in x for x in antislop.tells("Satu perjalanan anda ke era baharu tanpa had."))
    assert antislop.tells("NPRA menyemak dokumen selepas produk dipasarkan. Notifikasi bukan kelulusan.") == []
    assert any("ALL CAPS" in x for x in antislop.tells("Kita MESTI BERTINDAK SEKARANG sebelum terlambat"))
    assert not antislop.tells("NPRA KKM JAKIM menyemak")


def test_the_writers_are_handed_the_rules_and_a_film_keeps_its_hooks():
    assert "NOT A MODEL" in ideas.build_request({"stream": "regulab", "source_title": "t"}, {"text": "x"}, {})[0]
    system = motion.build_script_system({"language": "bm", "seconds": 30}, "")
    assert "NOT A MODEL" in system and "Tahukah anda" in system and "connecting sentences" in system


def test_new_ai_written_captions_come_out_clean_and_the_shape_is_unchanged():
    got = ideas.normalise_text({"bm": {"instagram": "Fakta — bukan kelulusan.\nHarap membantu!", "threads": "Ringkas."}},
                               "regulab", "bm")
    assert got == {"bm": {"instagram": "Fakta, bukan kelulusan.", "threads": "Ringkas."}}


def test_the_plan_of_a_film_is_cleaned_too():
    class LLM:
        def chat_json(self, system, user, **kw):
            return {"title": "t", "photo_query": "q", "scenes": [
                {"heading": f"Fakta — penting {i}", "lines": ["Tips dan obat"], "narration": ""} for i in range(4)]}
    plan = motion.plan_scenes(LLM(), {"voice": "off", "language": "bm"}, "", "", "")
    assert plan["scenes"][0]["heading"] == "Fakta, penting 0" and plan["scenes"][0]["lines"] == ["Tip dan ubat"]


class _Log:
    """A store that keeps what is inserted into the anti-slop log."""
    def __init__(self):
        self.rows = []

    def table(self, name):
        log = self

        class T:
            def insert(self, row):
                log.rows.append((name, row))
                return self

            def execute(self):
                return self
        return T()


def test_the_levels_decide_what_a_writer_is_told_and_what_is_edited():
    dirty = "Let's dive in. Fakta — penting. In order to lulus, semak label."
    try:
        antislop.begin({"level": "full"})
        assert "NOT A MODEL" in antislop.prompt_block() and "owner's own voice" in antislop.prompt_block(film=True)
        assert antislop.clean(dirty) == "Fakta, penting. To lulus, semak label."
        antislop.begin({"level": "clean"})
        assert antislop.prompt_block() == "" and antislop.clean(dirty) == "Fakta, penting. To lulus, semak label."
        antislop.begin({"level": "off"})
        assert antislop.prompt_block() == "" and antislop.clean(dirty) == dirty, "off is the control: nothing is edited"
        assert antislop.level_of({"level": "nonsense"}) == "full" and antislop.level_of(None) == "full"
        assert antislop.level_of("clean") == "clean"
    finally:
        antislop.begin(None)


def test_every_output_is_scored_before_and_after_the_edits_and_logged_with_its_level():
    store = _Log()
    try:
        antislop.begin({"level": "clean"})
        antislop.clean("Fakta — satu. Harap membantu.")
        antislop.clean("Bersih sahaja.")
        antislop.finish(store, "post", "p1")
        (table, row), = store.rows
        assert table == "semasa_antislop_log" and row["kind"] == "post" and row["ref"] == "p1" and row["level"] == "clean"
        assert row["chars"] == len("Fakta — satu. Harap membantu.") + len("Bersih sahaja.")
        assert row["raw_hits"] >= 2 and row["final_hits"] == 0, "a dash and a closer were in it; both were edited out"
        antislop.finish(store, "post", "p2")
        assert len(store.rows) == 1, "nothing written since the last output, so no empty row"
        antislop.begin({"level": "off"})
        antislop.clean("Fakta — satu.")
        antislop.finish(store, "film", "f1")
        assert store.rows[-1][1]["level"] == "off" and store.rows[-1][1]["final_hits"] == store.rows[-1][1]["raw_hits"] == 1
    finally:
        antislop.begin(None)


def test_a_missing_log_table_never_breaks_a_post():
    class Broken:
        def table(self, name):
            raise RuntimeError("no such table")
    antislop.begin({"level": "full"})
    antislop.clean("Fakta — satu.")
    antislop.finish(Broken(), "post", "p1")
    antislop.begin(None)
