"""Motion's hook scene is built on one of the 25 hook shapes (Wan, 7 Nov 2026: "do 1,2,3", the third being that the film's hook
scene uses the shapes instead of Tahukah anda / Amaran / Berita terkini)."""

from __future__ import annotations

import pytest

from semasa import hook_bank, motion, motion_auto

ROW = {"voice": "off", "language": "bm", "stream": "regulab"}


class Seq:
    def __init__(self, answers):
        self.answers, self.asked = list(answers), []

    def chat_json(self, system, user, **kw):
        self.asked.append((system, user))
        return self.answers.pop(0) if self.answers else None


def plan(**top):
    scenes = [{"heading": h, "lines": ["satu"], "narration": ""} for h in
              ("Stop buat label sendiri kalau nak produk selamat", "Fakta", "Kenapa", "Solusi")]
    return {"title": "t", "photo_query": "lab", "hook_shape": 17, "hook": scenes[0]["heading"], "scenes": scenes, **top}


def test_the_script_prompt_carries_the_shapes_and_no_longer_asks_for_a_fixed_opener():
    system = motion.build_script_system(ROW, "")
    assert "THE HOOK (REQUIRED" in system and '"hook_shape"' in system and '"hook"' in system
    assert "17. Stop buat ___ kalau kau nak ___" in system
    assert "Pick the one the topic is" not in system and "'Tahukah anda...?' (a surprising fact)" not in system
    one = motion.build_script_system({**ROW, "duration": 10}, "", 1)
    assert "THE HOOK (REQUIRED" in one


def test_the_company_account_is_not_offered_the_first_person_family_but_linkedin_is():
    reg = motion.build_script_system(ROW, "")
    li = motion.build_script_system({**ROW, "stream": "linkedin", "language": "en"}, "")
    assert "VULNERABLE:" not in reg and "VULNERABLE:" in li


def test_a_hooked_script_makes_scene_one_the_hook_and_records_the_shape():
    got = motion.plan_scenes(Seq([plan()]), ROW, "", "", "")
    first = got["scenes"][0]
    assert first["heading"] == "Stop buat label sendiri kalau nak produk selamat" and first["hook_shape"] == 17
    assert got["hook_shape"] == 17 and got["hook"] == first["heading"]
    assert "hook_shape" not in got["scenes"][1]


def test_scene_one_is_made_to_equal_the_hook_even_when_the_writer_wrote_another_heading():
    other = plan(hook="POV: kau nak lulus notifikasi tapi label salah", hook_shape=21)
    got = motion.plan_scenes(Seq([other]), ROW, "", "", "")
    assert got["scenes"][0]["heading"] == "POV: kau nak lulus notifikasi tapi label salah"


@pytest.mark.parametrize("bad", [{"hook_shape": None}, {"hook_shape": 99}, {"hook_shape": "x"}, {"hook": ""},
                                 {"hook": "Stop buat ___ kalau nak ___"}, {"hook_shape": 12}])
def test_a_script_without_a_usable_shape_is_asked_again_once_and_the_second_answer_is_used(bad):
    llm = Seq([plan(**bad), plan()])
    got = motion.plan_scenes(llm, ROW, "", "", "")
    assert len(llm.asked) == 2 and "DID NOT USE A HOOK SHAPE" in llm.asked[1][1]
    assert got["hook_shape"] == 17


def test_two_scripts_without_a_shape_fail_the_film_with_a_plain_reason():
    llm = Seq([plan(hook_shape=None), plan(hook_shape=None)])
    with pytest.raises(RuntimeError, match="no hook shape twice"):
        motion.plan_scenes(llm, ROW, "", "", "")
    assert len(llm.asked) == 2


def test_a_shape_the_company_account_may_not_use_is_refused_but_linkedin_may_use_it():
    first_person = plan(hook_shape=12, hook="Kegagalan terbesar aku dgn label ajar aku sabar")
    with pytest.raises(RuntimeError):
        motion.plan_scenes(Seq([first_person, first_person]), ROW, "", "", "")
    got = motion.plan_scenes(Seq([first_person]), {**ROW, "stream": "linkedin", "language": "en"}, "", "", "")
    assert got["hook_shape"] == 12


def test_a_style_made_from_screenshots_replaces_the_shapes_and_its_number_is_checked():
    bank = hook_bank.Bank(id="st1", name="Berani", instruction="Open with a flat challenge.",
                          shapes=((1, "bold", "Jangan ___ sebelum ___"), (2, "bold", "Kenapa ___ gagal")))
    system = motion.build_script_system(ROW, "", 4, bank)
    assert "HOOK STYLE \"Berani\"" in system and "1. Jangan ___ sebelum ___" in system and "Open with a flat challenge." in system
    assert "17. Stop buat" not in system
    llm = Seq([plan(hook_shape=1, hook="Jangan jual sebelum notifikasi"), ])
    got = motion.plan_scenes(llm, ROW, "", "", "", bank=bank)
    assert got["hook_shape"] == 1 and got["hook_style"] == "st1"
    again = Seq([plan(hook_shape=17), plan(hook_shape=2, hook="Kenapa label gagal")])        # 17 is not in this style
    assert motion.plan_scenes(again, ROW, "", "", "", bank=bank)["hook_shape"] == 2


def test_the_teaser_keeps_its_hook_and_adds_the_call_to_action_after_it():
    got = motion.plan_scenes(Seq([plan()]), {**ROW, "duration": 10}, "", "", "")
    assert got["scenes"][0]["heading"].startswith("Stop buat label sendiri kalau nak produk selamat")
    assert got["scenes"][0]["hook_shape"] == 17


def test_a_voiced_film_records_whether_the_hook_is_the_first_thing_said():
    said = plan()
    said["scenes"][0]["narration"] = "Stop buat label sendiri kalau nak produk selamat. Ini faktanya."
    said["scenes"][1]["narration"] = said["scenes"][2]["narration"] = said["scenes"][3]["narration"] = "Okay."
    assert motion.plan_scenes(Seq([said]), {**ROW, "voice": "male"}, "", "", "")["scenes"][0]["hook_first_said"] is True
    other = plan()
    other["scenes"][0]["narration"] = "Tahukah anda soalan lain."
    assert motion.plan_scenes(Seq([other]), {**ROW, "voice": "male"}, "", "", "")["scenes"][0]["hook_first_said"] is False


def test_a_hook_shape_film_draws_no_tahukah_anda_chip_and_an_old_film_still_does():
    scenes = [{"id": f"s{i}", "kicker": "x", "heading": h, "lines": ["satu dua"], "narration": ""}
              for i, h in enumerate(("Amaran produk ditarik balik", "Fakta", "Kenapa", "Solusi"), 1)]
    row = {"brief": "produk ditarik balik", "voice": "off"}
    old = motion_auto.choose(row, [dict(s) for s in scenes], voiced=False, lang="bm")
    assert old["hook"] == "warn"
    shaped = [dict(s) for s in scenes]
    shaped[0]["hook_shape"] = 17
    assert motion_auto.choose(row, shaped, voiced=False, lang="bm")["hook"] == ""


def test_pick_for_idea_reads_the_idea_then_the_default_and_never_raises():
    class Table:
        def __init__(self, rows):
            self.rows = rows

        def select(self, *a):
            return self

        def eq(self, *a):
            return self

        def execute(self):
            return type("R", (), {"data": self.rows})()

    class Store:
        def table(self, name):
            return Table([{"value": {}}] if name == "semasa_settings" else [{"brief": {}}] if name == "semasa_ideas" else [])

    assert hook_bank.pick_for_idea(Store(), "i1") is None

    class Broken:
        def table(self, name):
            raise RuntimeError("down")

    assert hook_bank.pick_for_idea(Broken(), "i1") is None and hook_bank.pick_for_idea(Broken(), None) is None
