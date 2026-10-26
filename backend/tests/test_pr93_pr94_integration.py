"""Combined PR93/94 contracts; fixtures are not generated-film acceptance."""
import pytest

from semasa import motion, motion_layout


@pytest.mark.parametrize("design", ["bright-editorial", "continuous-line"])
def test_layout_accepts_design_and_worker_caption_ownership_together(design):
    scene = {"id": "s1", "heading": "Keep the heading", "lines": [], "start": 0,
             "duration": 6, "audio": "assets/voice.mp3", "audio_s": 2,
             "narration": "One two three four", "timing_source": "actual-word",
             "words": [[0, .3, "One"], [.4, .7, "two"], [.8, 1.1, "three"], [1.2, 1.5, "four"]]}
    page, _ = motion_layout.compose(
        scenes=[scene], total=6, w=1080, h=1920, lang="en", plan={"scenes": {}, "video": {}},
        palette=motion.PALETTE["regulab"], gsap=motion.GSAP, html_lang="en", resolution="portrait",
        design=design, worker_captions=True)
    assert motion_layout.GRADIENT[design] in page and 'id="grad2"' in page
    assert 'id="s1-c0"' not in page, "worker owns subtitles; safe layout must not duplicate them"
    assert 'id="s1-h"' in page
    assert motion_layout.caption_chunks(scene) == [("One two three four", 0.0, 1.5)]


def test_writer_failure_preserves_gradient_and_worker_caption_arguments(tmp_path, monkeypatch):
    from test_motion import SCRIPT, FakeLLM, Store, _row, _runner, fake_speak

    original = motion_layout.compose
    seen = []

    def compose(**kwargs):
        seen.append(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(motion_layout, "compose", compose)
    store = Store()
    row = _row(store, voice="male", language="en", options={"design": "bright-editorial"})
    assert motion.process(store, FakeLLM([SCRIPT, None, None]), row,
                          {"cli": motion.CLI_VERSION, "prompt": ""}, runner=_runner(),
                          workdir=tmp_path, speak=fake_speak)
    assert len(seen) == 1
    assert seen[0]["design"] == "bright-editorial" and seen[0]["worker_captions"] is True
    saved = store.table(motion.TABLE).select("*").eq("id", row["id"]).execute().data[0]
    assert "linear-gradient(145deg,#e0f5e9,#fff9ed 70%)" in saved["html"]
    assert 'id="s1-c0"' not in saved["html"]
    assert "safe layout used" in saved["style_note"]
