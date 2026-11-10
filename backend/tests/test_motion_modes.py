"""More modes for a Motion film (Wan, 10 Nov 2026: "add more mode for motion, not only as explainer or gimmick only")."""

import pytest

from semasa import motion, motion_styles


@pytest.mark.parametrize("mode, part2, part3", [
    ("explainer", "CERITA & FAKTA", "TERLEPAS"),
    ("news", "APA JADI", "KENAPA PENTING"),
    ("myth", "MITOS", "KENAPA ORANG PERCAYA"),
    ("howto", "LANGKAH", "KESILAPAN"),
    ("case", "KES (the case)", "PERATURAN"),
])
def test_each_mode_gives_the_writer_its_own_scene_jobs_in_the_same_four_parts(mode, part2, part3):
    for lang in ("bm", "en"):
        system = motion.build_script_system({"stream": "regulab", "seconds": 30, "language": lang, "voice": "male",
                                             "options": {"mode": mode}}, "")
        a, b, c, d = (system.index(x) for x in ("1. HOOK", "2. " + part2, "3. " + part3, "4. CTA"))
        assert a < b < c < d
        assert "Do NOT invite the viewer to follow" in system, "the follow line stays the closing card's alone"
        assert "Never invent a number, date, clause or case" in system


def test_a_mode_nobody_knows_is_an_explainer_and_the_teaser_is_still_its_own_thing():
    assert motion_styles.mode({"options": {"mode": "news"}}) == "news"
    assert motion_styles.mode({"options": {"mode": "nonsense"}}) == "explainer"
    assert motion_styles.mode({}) == "explainer"
    assert motion_styles.mode({"options": {"mode": "teaser"}}) == "teaser"
    assert motion.STRUCTURE_RULE == motion.structure_rule("explainer"), "films without a mode are written exactly as before"
    system = motion.build_script_system({"stream": "regulab", "seconds": 10, "language": "bm", "voice": "male",
                                         "options": {"mode": "teaser"}}, "", count=1)
    assert "ONE scene" in system and "4. CTA" not in system
