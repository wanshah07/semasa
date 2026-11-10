"""Wan, 10 Nov 2026: style presets from two sites for Motion, copywriting frameworks for every post, and one film drawn by
both engines."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from semasa import copywriting, motion_presets, motion_remotion


def test_the_preset_list_has_both_sources_and_stores_no_prompt_text():
    groups = {p["group"] for p in motion_presets.PRESETS}
    assert groups == {"MotionPrompt", "Motion patterns"}
    assert len({p["id"] for p in motion_presets.PRESETS}) == len(motion_presets.PRESETS)
    for p in motion_presets.PRESETS:
        if p["group"] == "MotionPrompt":                    # read at film time, never kept here
            assert p["url"].startswith("https://raw.githubusercontent.com/epool86/motionprompt/") and "look" not in p
        else:
            assert len(p["look"]) > 30


def test_a_preset_is_a_fenced_style_reference_and_an_unreadable_one_never_stops_the_film():
    assert motion_presets.chosen({"options": {"preset": "nope"}}) is None and motion_presets.chosen({}) is None
    own = motion_presets.chosen({"options": {"preset": "rl:kinetic-type"}})
    name, text, note = motion_presets.words(own)
    assert name == "Motion patterns: Kinetic type" and "ONLY the visual language" in text and "word by word" in text
    remote = motion_presets.chosen({"options": {"preset": "mp:kopitiam"}})
    got = motion_presets.words(remote, get=lambda url: SimpleNamespace(text="warm kopitiam palette " * 30,
                                                                       raise_for_status=lambda: None))
    assert got[0] == "MotionPrompt: Kopitiam" and got[1].startswith(motion_presets.FENCE) and len(got[1]) <= 4300

    def gone(url):
        raise OSError("offline")
    assert motion_presets.words(remote, get=gone)[:2] == ("", "") and "house look" in motion_presets.words(remote, get=gone)[2]


def test_each_kind_of_post_takes_its_framework():
    k = copywriting.kind_of
    assert k({}, "regulab") == "caption" and k({}, "regulab", "carousel") == "carousel" and k({}, "linkedin") == "linkedin"
    assert k({"domain": "kajian_kes"}, "regulab", "carousel") == "case" and k({"angle": "E"}, "linkedin") == "case"
    assert "HOOK - STORY - LESSON - CTA" in copywriting.block("caption")
    assert "PROBLEM - PROCESS - RESULT - PROOF - LESSON" in copywriting.block("case")
    film = copywriting.block("film")
    assert "scene 1 is the HOOK" in film and "HOOK - PROBLEM - SOLUTION - PROOF - CTA" in film
    for kind in copywriting.STEPS:                                 # the guard rides with every framework
        b = copywriting.block(kind)
        assert "never a testimonial" in b and "Do not print the step names" in b
    assert copywriting.block("unknown") == ""


def test_the_writers_are_given_the_framework():
    from semasa import ideas, motion
    assert "copywriting.block(copywriting.kind_of(idea, stream, fmt))" in Path(ideas.__file__).read_text()
    assert 'copywriting.block("film")' in Path(motion.__file__).read_text()


def test_a_combined_film_changes_engine_on_a_scene_boundary():
    scenes = [{"id": f"s{i}", "start": s} for i, s in enumerate([0.0, 8.0, 20.0, 31.0], 1)]
    scenes.append({"id": "brand-outro", "start": 40.0})
    assert motion_remotion.cut_point(scenes) == 20.0                # scenes 1-2 HyperFrames, 3-4 and the close Remotion
    assert motion_remotion.cut_point(scenes[:1]) == 0.0
    assert motion_remotion.choice({"options": {"renderer": "combined"}}) == "combined"
    assert motion_remotion.choice({"options": {"renderer": "remotion"}}) == "remotion"
    assert motion_remotion.choice({"options": {"renderer": "x"}}) == ""
    assert not motion_remotion.wanted({"options": {"renderer": "combined"}})


def test_combine_joins_the_two_renders_and_says_when_it_cannot(tmp_path):
    seen = {}

    def ok(cmd, **kw):
        seen["cmd"] = cmd
        Path(cmd[-1]).write_bytes(b"x")
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    out = motion_remotion.combine(tmp_path / "a.mp4", tmp_path / "b.mp4", 20.0, tmp_path / "c.mp4", ok)
    assert out.exists() and "trim=end=20" in " ".join(seen["cmd"]) and "trim=start=20" in " ".join(seen["cmd"])
    with pytest.raises(RuntimeError, match="could not be joined"):
        motion_remotion.combine(tmp_path / "a.mp4", tmp_path / "b.mp4", 20.0, tmp_path / "d.mp4",
                                lambda cmd, **kw: SimpleNamespace(returncode=1, stdout="", stderr="bad"))
