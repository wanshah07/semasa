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
