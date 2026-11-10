# ruff: noqa: E501
"""Wan, 10 Nov 2026: grammar always right, the voice and the audio right, for ws.regulab (Malay) and LinkedIn (English)."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from semasa import motion_layout, pronounce, proofread


class LLM:
    def __init__(self, answer):
        self.answer, self.asked = answer, []

    def chat_json(self, system, user, **kw):
        self.asked.append((system, user))
        return self.answer


def test_the_deterministic_step_writes_abbreviations_out_and_leaves_wans_casual_words_alone():
    assert proofread.fix_spelling("yg  boleh  dgn HIFU??  sbb korang tak tahu", "bm") == "Yang boleh dengan HIFU? sebab korang tak tahu"
    assert proofread.fix_spelling("dah tahu, nak jom?", "bm") == "Dah tahu, nak jom?"
    assert proofread.fix_spelling("yg is not expanded in english", "en") == "Yg is not expanded in english"[:0] + "Yg is not expanded in english"
    assert proofread.fix_spelling("see #tag and www.x.my", "en") == "See #tag and www.x.my"


def test_a_correction_is_accepted_only_when_it_changes_the_writing_and_not_the_facts():
    old = "Denda 50% kes NPRA pada 2026."
    assert proofread.safe(old, "Denda 50% bagi kes NPRA pada 2026.")
    assert not proofread.safe(old, "Denda 60% kes NPRA pada 2026.")                 # a number moved
    assert not proofread.safe(old, "Denda 50% kes BPOM pada 2026.")                 # an acronym moved
    assert not proofread.safe("Lihat #halal", "Lihat #haram")                       # a hashtag moved
    assert not proofread.safe(old, "x") and not proofread.safe(old, "")             # a collapse is refused
    assert not proofread.safe(old, old * 2)


@pytest.mark.real_proofread
def test_the_writer_corrects_each_field_and_a_bad_answer_costs_only_that_field():
    fields = {"a": "Kes ini tidak sah kerana ia ada bahan larang.", "b": "Denda 50% pada 2026.", "c": "Sudah betul."}
    llm = LLM({"fixed": {"a": "Kes ini tidak sah kerana ia ada bahan larangan.", "b": "Denda 70% pada 2026.", "c": "Sudah betul."}})
    got, changed = proofread.proofread(llm, fields, "bm")
    assert got["a"].endswith("ada bahan larangan.") and got["b"] == "Denda 50% pada 2026." and got["c"] == "Sudah betul."
    assert changed == ["a"]                                                    # the moved number was refused, the correct one kept
    assert "Bahasa Malaysia" in llm.asked[0][0] and "korang" in llm.asked[0][0]
    li = LLM({"fixed": {}})
    proofread.proofread(li, {"a": "We tested 100 products."}, "en")             # LinkedIn: English, no Malay register
    assert "English" in li.asked[0][0] and "korang" not in li.asked[0][0]


@pytest.mark.real_proofread
def test_a_proofreader_that_fails_or_is_absent_leaves_the_text_as_it_was():
    fields = {"a": "yg betul"}
    assert proofread.proofread(None, fields, "bm")[0] == {"a": "Yang betul"}

    class Boom:
        def chat_json(self, *a, **k):
            raise RuntimeError("down")
    assert proofread.proofread(Boom(), fields, "bm")[0] == {"a": "Yang betul"}
    assert proofread.proofread(LLM("junk"), fields, "bm")[0] == {"a": "Yang betul"}


@pytest.mark.real_proofread
def test_a_post_is_corrected_in_each_language_and_its_hook_still_leads_its_caption():
    out = {"hook": "Benda pasal HIFU yg takde sapa bagitau kau", "slides": [{"title": "Tajuk yg salah", "lead": "Lead.", "points": ["satu", "dua"]}]}
    text = {"bm": {"instagram": "Benda pasal HIFU yg takde sapa bagitau kau. Cerita di sini."},
            "en": {"instagram": "Did you know HIFU is a thing? More here."}}
    llm = LLM({"fixed": {"hook": "Benda pasal HIFU yang takde sapa bagitau kau",
                         "cap.instagram": "Benda pasal HIFU yang takde sapa bagitau kau. Cerita di sini.",
                         "s0.title": "Tajuk yang betul"}})
    hook, new_text, slides, changed = proofread.post(llm, out, text, "bm")
    assert hook.startswith("Benda pasal HIFU yang") and new_text["bm"]["instagram"].startswith("Benda pasal HIFU yang")
    assert slides[0]["title"] == "Tajuk yang betul" and slides[0]["points"] == ["Satu", "Dua"]
    assert new_text["en"]["instagram"].startswith("Did you know")
    # a correction that would stop the caption opening with the hook is dropped on both
    llm2 = LLM({"fixed": {"hook": "Hook baharu sepenuhnya", "cap.instagram": "Kapsyen lain dari awal."}})
    h2, t2, _, _ = proofread.post(llm2, {"hook": "Hook asal di sini"}, {"bm": {"instagram": "Hook asal di sini. Teruskan."}}, "bm")
    assert h2 == "Hook asal di sini" and t2["bm"]["instagram"] == "Hook asal di sini. Teruskan."


def test_the_voice_reads_a_speakable_text_while_the_screen_keeps_its_spelling():
    assert pronounce.speech_text("NPRA dan KKM kata 80% produk yg ada HIFU, sbb dgn UV & SPF.", "bm") == (
        "N P R A dan K K M kata 80 peratus produk yang ada HIFU, sebab dengan U V dan S P F.")
    assert pronounce.speech_text("The PFAS in MS1500 is 5% of GMP", "en") == "The PFAS in M S 1500 is 5 percent of G M P"
    assert pronounce.speech_text("Kes ni tak sah, dah tahu korang?", "bm") == "Kes ni tak sah, dah tahu korang?"
    assert pronounce.speech_text("yg tidak ditukar", "en") == "yg tidak ditukar"          # English is not rewritten as Malay


def test_a_silent_or_impossible_clip_is_reported(tmp_path):
    clip = tmp_path / "a.mp3"
    clip.write_bytes(b"x")
    silent = lambda *a, **k: SimpleNamespace(stderr="mean_volume: -91.0 dB", stdout="", returncode=0)  # noqa: E731
    fine = lambda *a, **k: SimpleNamespace(stderr="mean_volume: -22.3 dB", stdout="", returncode=0)  # noqa: E731
    ten = "satu dua tiga empat lima enam tujuh lapan sembilan sepuluh"
    assert "silent" in pronounce.problem(clip, ten, 4.0, silent)
    assert pronounce.problem(clip, ten, 4.0, fine) == ""
    assert "too slow" in pronounce.problem(clip, ten, 30.0, fine)
    assert "too fast" in pronounce.problem(clip, ten, 1.0, fine)
    assert pronounce.problem(clip, "dua", 30.0, fine) == ""                          # too few words to judge by speed
    assert Path(pronounce.FILE).exists()


def test_a_subtitle_never_ends_on_a_preposition_or_inside_a_name():
    sc = {"narration": "Okay, sekarang kita tengok apa yang berlaku. Satu laporan kes dalam Frontiers in Medicine catat seorang "
                       "wanita berusia 38 tahun alami kecederaan segmen anterior bilateral selepas prosedur kosmetik HIFU di "
                       "kawasan periokular untuk pengurangan lemak kelopak mata.", "start": 0.0, "duration": 20.0, "audio_s": 19.7}
    chunks = [c[0] for c in motion_layout.caption_chunks(sc)]
    assert " ".join(chunks) == sc["narration"]                                       # nothing lost, nothing added
    assert not any(c.endswith((" in", " di", " dalam", " untuk")) for c in chunks)
    assert any("Frontiers in Medicine" in c for c in chunks)
