"""Attachment recipes consumed by the real worker (CLI/TTS boundaries stubbed)."""
import pytest
from test_motion import GOOD, NOW, SCRIPT, FakeLLM, Store, _row, _runner, fake_speak

from semasa import motion
from semasa import motion_styles as styles


def test_kitten_requires_english_and_configured_worker(tmp_path, monkeypatch):
    assert motion.voice_mod.voice_for("en", "kitten") == "kitten"
    with pytest.raises(ValueError, match="English"):
        motion.voice_scenes([{"narration": "Hai"}], "bm", "kitten", tmp_path)
    monkeypatch.delenv("VOICESTUDIO_PYTHON", raising=False)
    with pytest.raises(RuntimeError, match="VOICESTUDIO_PYTHON"):
        motion.voice_mod.speak("Hello", "kitten", tmp_path / "voice.mp3")


def test_music_mix_uses_approved_v8_and_speech_ducking(tmp_path):
    calls = []
    video = tmp_path / "motion.mp4"
    video.write_bytes(b"test fixture")
    scenes = [{"audio": "assets/voice-1.mp3", "start": 0, "audio_s": 2}]
    motion.mix_music(video, scenes, 10, runner=_runner(calls=calls))
    command = calls[0]
    assert "music-v8.mp3" in " ".join(command)
    graph = command[command.index("-filter_complex") + 1]
    assert "afade=t=in" in graph and "afade=t=out" in graph
    assert "between(t,0,2)" in graph and "amix" in graph
    assert command[command.index("-c:v") + 1] == "copy"


def test_catalog_defaults_and_asset_fallback():
    assert len(styles.CATALOG) == 8
    assert styles.resolve({})["id"] == "bright-education"
    assert styles.resolve({"options": {"style": "invalid"}})["id"] == "bright-education"
    assert styles.resolve({"options": {"style": "saas-product-demo"}})["id"] == "bright-education"
    assert styles.CATALOG[6]["duplicate_of"] == "tutorial-screen-recording"
    assert styles.duration({}) == 30
    assert styles.duration({"seconds": 10}) == 30
    assert styles.duration({"seconds": 10, "options": {"mode": "teaser"}}) == 10
    assert "10s ONLY" in styles.prompt({})
    assert "teaser" in motion.build_script_system({"seconds": 10, "options": {"mode": "teaser"}}, "")
    for value in [0, -1, 61, float("nan"), "oops"]:
        assert 3 <= styles.duration({"seconds": value}) <= 60


def test_prompt_scaled_beats_and_current_defaults():
    row = {"seconds": 30, "language": "en", "options": {"style": "financial-education-reel"}}
    prompt = styles.prompt(row)
    assert "Hook -> Fact -> Why -> Solution" in prompt
    assert "transparent" in prompt and "no background box" in prompt
    assert "FirstAuthor et al. (year)" in prompt
    assert "studied or reviewed" in prompt and "abstract" in prompt
    beats = styles.beats(styles.CATALOG[3], 30)
    assert beats[1]["start"] == pytest.approx(14.33 / 45 * 27)
    assert [b["code"] for b in beats] == ["H03", "V09", "P03", "V03", "S04"]
    assert "no call to action" not in motion.build_system(row, "")
    assert "Follow for more tips!" in motion.build_system(row, "")
    assert "closing scene that ends on the substance" not in motion.build_script_system(row, "")


def test_worker_rejects_rendered_duration_mismatch(tmp_path):
    store = Store()
    row = _row(store, seconds=60, voice="off", language="en")
    assert not motion.process(store, FakeLLM([SCRIPT, {"html": GOOD}]), row,
                              {"prompt": "", "cli": motion.CLI_VERSION},
                              runner=_runner(), workdir=tmp_path, now=NOW)
    saved = store.table(motion.TABLE).select("*").eq("id", row["id"]).execute().data[0]
    assert "duration" in saved["error"].lower()


def test_worker_consumes_recipe_and_enforces_selected_duration(tmp_path):
    store = Store()
    row = _row(store, seconds=30, language="en", mascot="", voice="off",
               options={"style": "financial-education-reel"})
    llm = FakeLLM([SCRIPT, {"html": GOOD}])
    assert motion.process(store, llm, row, {"prompt": "", "cli": motion.CLI_VERSION},
                          runner=_runner(), workdir=tmp_path, now=NOW, speak=fake_speak)
    assert all("Financial Education Reel" in system + user for system, user in llm.asked)
    index = (tmp_path / row["id"][:8] / "index.html").read_text()
    assert 'data-duration="30"' in index and "official-logo-transparent.png" in index
    assert "Follow for more tips!" in index and "mascot-wave" not in index
    saved = store.table(motion.TABLE).select("*").eq("id", row["id"]).execute().data[0]
    assert saved["script"][-1]["narration"] == "Follow us for more."
    assert saved["script"][-1]["start"] == 27


def test_narration_that_cannot_fit_fails_instead_of_speeding_or_overrunning(tmp_path):
    store = Store()
    row = _row(store, seconds=10, language="en", voice="male", mascot="", options={"mode": "teaser"})
    long = {"title": "Too long", "scenes": [{"heading": "Study", "narration": "word " * 100}]}
    llm = FakeLLM([long])
    assert not motion.process(store, llm, row, {"prompt": "", "cli": motion.CLI_VERSION},
                              runner=_runner(), workdir=tmp_path, now=NOW, speak=fake_speak)
    got = store.table(motion.TABLE).select("*").eq("id", row["id"]).execute().data[0]
    assert "30/60" in got["error"]
