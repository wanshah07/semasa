"""Remotion, the second Motion renderer: chosen per film, fed the worker's own scenes, never fatal."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from semasa import motion_remotion as mr

PAL = {"ground": "#e5f6ed", "ink": "#143e35", "accent": "#287b65", "accent2": "#fff7e6"}
SCENES = [
    {"id": "s1", "role": "hook", "kicker": "HOOK", "heading": "Tajuk", "lines": ["a", "b", "c", "d"],
     "photo": "assets/scene-s1.jpg",
     "start": 0.0, "duration": 6.0, "audio": "assets/voice-1.mp3", "audio_s": 5.5, "words": [],
     "narration": "satu dua tiga empat lima enam tujuh lapan sembilan sepuluh sebelas dua belas"},
    {"id": "brand-outro", "kicker": "", "heading": "Ikuti kami", "lines": [], "start": 6.2, "duration": 2.8,
     "audio": "assets/voice-2.mp3", "narration": "Ikuti kami"},
]


def test_only_a_film_that_asks_for_remotion_gets_it():
    assert mr.wanted({"options": {"renderer": "remotion"}})
    assert mr.wanted({"options": {"renderer": "Remotion"}})
    assert not mr.wanted({"options": {}}) and not mr.wanted({"options": None}) and not mr.wanted({})
    assert not mr.wanted({"options": {"renderer": "hyperframes"}})


def test_props_carry_the_workers_own_scenes_times_and_subtitles():
    p = mr.props(SCENES, 9.0, 1080, 1920, PAL, name="ws.regulab")
    assert (p["width"], p["height"], p["fps"], p["seconds"]) == (1080, 1920, 30, 9.0)
    s1, outro = p["scenes"]
    assert s1["heading"] == "Tajuk" and s1["lines"] == ["a", "b", "c"] and s1["photo"] == "assets/scene-s1.jpg"
    assert s1["captions"] and s1["captions"][0][1] == 0.0 and s1["captions"][-1][2] == 6.0
    assert " ".join(c[0] for c in s1["captions"]) == SCENES[0]["narration"]          # the narration, whole, in order
    assert outro["captions"] == []                                                   # the closing card has no subtitle
    assert p["outro"] == {"name": "ws.regulab", "line": "Ikuti kami", "logo": "", "brand": True}
    assert mr.props(SCENES, 9.0, 1080, 1080, PAL, name="Ts. ChM Ridzuan")["outro"]["name"] == "Ts. ChM Ridzuan"
    assert mr.props(SCENES, 9.0, 1080, 1080, PAL)["outro"]["name"] == ""        # LinkedIn with no byline: no brand either
    assert mr.props(SCENES[:1], 6.0, 1080, 1920, PAL)["outro"] is None


def test_render_runs_the_project_and_returns_the_silent_film(tmp_path, monkeypatch):
    monkeypatch.setattr(mr, "ready", lambda: True)
    monkeypatch.setenv("REMOTION_BROWSER", "/x/chrome")
    seen = {}

    def runner(cmd, **kw):
        seen["cmd"], seen["cwd"] = cmd, kw["cwd"]
        Path(cmd[5]).write_bytes(b"mp4")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    out = mr.render(tmp_path, mr.props(SCENES, 9.0, 1080, 1920, PAL), runner)
    assert out == tmp_path / "renders" / "motion.mp4" and out.read_bytes() == b"mp4"
    assert seen["cwd"] == str(mr.PROJECT) and "--muted" in seen["cmd"]               # the worker mixes the sound itself
    assert f"--public-dir={tmp_path}" in seen["cmd"] and "--browser-executable=/x/chrome" in seen["cmd"]
    assert (tmp_path / "remotion-props.json").exists()


def test_a_failed_or_missing_remotion_raises_so_the_worker_falls_back(tmp_path, monkeypatch):
    monkeypatch.setattr(mr, "ready", lambda: False)
    with pytest.raises(RuntimeError, match="not installed"):
        mr.render(tmp_path, {}, lambda *a, **k: None)
    monkeypatch.setattr(mr, "ready", lambda: True)
    with pytest.raises(RuntimeError, match="boom"):
        mr.render(tmp_path, {}, lambda *a, **k: SimpleNamespace(returncode=1, stdout="", stderr="boom"))


def test_the_project_is_in_the_repo_with_pinned_versions():
    import json
    pkg = json.loads((mr.PROJECT / "package.json").read_text())
    assert pkg["dependencies"]["remotion"] == pkg["dependencies"]["@remotion/cli"]      # Remotion needs one version
    assert not pkg["dependencies"]["remotion"].startswith(("^", "~"))
    assert (mr.PROJECT / "package-lock.json").exists() and (mr.PROJECT / "src" / "Film.jsx").exists()
