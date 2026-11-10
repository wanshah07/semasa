"""A reference video is watched for its style and never reused (Wan, 10 Nov 2026)."""

from pathlib import Path

from PIL import Image

from semasa import motion
from semasa import motion_reference as ref


def test_a_link_is_a_repo_a_video_or_a_page():
    assert ref.kind_of("https://github.com/heygen-com/hyperframes") == "repo"
    assert ref.kind_of("https://www.youtube.com/watch?v=abc") == "video"
    assert ref.kind_of("https://youtu.be/abc") == "video"
    assert ref.kind_of("https://www.tiktok.com/@a/video/1") == "video"
    assert ref.kind_of("https://www.instagram.com/reel/abc/") == "video"
    assert ref.kind_of("https://drive.google.com/file/d/1/view") == "video"
    assert ref.kind_of("https://cdn.example.com/film.MP4?x=1") == "video"
    assert ref.kind_of("https://www.npra.gov.my/index.php/en/") == "page"
    assert ref.kind_of("https://github.com/heygen-com") == "page"            # an owner page is not a repo
    assert ref.kind_of("not a link") == "" and ref.kind_of(None) == ""


def test_pace_reads_as_a_sentence_the_writer_can_match():
    assert "a new shot every 2.0 s (fast pace)" in ref.pace(30, 14)
    assert "one continuous shot" in ref.pace(30, 0)
    assert "could not be counted" in ref.pace(30, None)


def test_the_style_block_carries_pace_palette_and_look_and_drops_junk():
    seen = [{"palette": ["#FFFFFF", "#0f5d4a", "red"], "type": "bold sans, white, black outline", "layout": "words centre",
             "devices": "captions, arrows", "picture": "talking head", "mood": "calm clear bright"},
            {"palette": ["#ffffff", "#111827"], "type": "Bold sans, white, black outline", "layout": "words top third"}]
    text = ref.style_text(seen, "30 s long")
    assert "PACE: 30 s long" in text and "PALETTE (as hex, background first): #ffffff, #0f5d4a, #111827" in text
    assert text.count("bold sans") + text.count("Bold sans") == 1            # the same note twice is said once
    assert "words centre | words top third" in text and "red" not in text


class Reader:
    def __init__(self, answer):
        self.answer, self.asked = answer, 0

    def describe_image(self, system, prompt, data, mime, **kw):
        self.asked += 1
        return self.answer


def _fake_video(tmp_path: Path):
    f = tmp_path / "v.mp4"
    f.write_bytes(b"x")

    def runner(cmd, **kw):
        out = Path(cmd[-1])
        if out.suffix == ".jpg":
            Image.new("RGB", (64, 64), "#0f5d4a").save(out, "JPEG")

        class R:
            returncode, stderr = 0, "pts_time:1 pts_time:2 pts_time:3"
        return R()
    return f, runner


def test_a_reference_video_becomes_style_words_and_fails_soft(tmp_path, monkeypatch):
    f, runner = _fake_video(tmp_path)
    monkeypatch.setattr(ref.video, "probe_duration", lambda p: 20.0)
    monkeypatch.setattr(ref.video, "ffmpeg", lambda: "ffmpeg")
    reader = Reader({"palette": ["#0f5d4a"], "type": "bold sans", "mood": "calm"})
    name, text, note = ref.style("https://x/v.mp4", tmp_path, reader, runner=runner, fetcher=lambda u, d: f)
    assert name == "the reference video" and "PALETTE" in text and "3 cuts" in text and reader.asked == ref.FRAMES
    assert note == f"reference video read: {ref.FRAMES} of {ref.FRAMES} frames"
    assert ref.style("https://x/v.mp4", tmp_path, Reader(None), runner=runner, fetcher=lambda u, d: f)[:2] == ("", "")

    def broken(u, d):
        raise ref.video.VideoError("private video")
    name, text, note = ref.style("https://x/v.mp4", tmp_path, reader, runner=runner, fetcher=broken)
    assert (name, text) == ("", "") and "private video" in note


def test_the_writer_is_told_it_is_a_reference_video_not_a_repo():
    row = {"brief": "b", "options": {}}
    user = motion.build_user(row, "", "", style=("the reference video", "PACE: fast"))
    assert "STYLE REFERENCE (the reference video)" in user and "use none of its files, media" in user
    user = motion.build_user(row, "", "", style=("owner/repo", "README"))
    assert "STYLE REFERENCE (the motion repo owner/repo)" in user
