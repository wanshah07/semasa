"""A ws.regulab film opens on the branded cover (Wan, 11 Nov 2026)."""

import shutil
import subprocess

import pytest
from PIL import Image

from semasa import motion

pytestmark = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")


def _film(tmp_path, audio=True):
    out = tmp_path / "film.mp4"
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0xaa3333:s=270x480:r=30:d=2"]
    if audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440:duration=2"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p"] + (["-c:a", "aac", "-shortest"] if audio else []) + [str(out)]
    subprocess.run(cmd, check=True)
    return out


def _frame(video, at, tmp_path):
    jpg = tmp_path / f"f{at}.jpg"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(at), "-i", str(video), "-frames:v", "1", str(jpg)], check=True)
    return Image.open(jpg).convert("RGB")


@pytest.mark.parametrize("audio", [True, False])
def test_the_cover_is_the_first_second_and_the_film_follows(tmp_path, audio):
    film = _film(tmp_path, audio)
    before = motion.probe(film)
    out = motion.with_cover(film, "Kesan sampingan ni akan hilang sendiri?", eyebrow="Kosmetik")
    assert out != film and out.is_file()
    after = motion.probe(out)
    assert (after["width"], after["height"]) == (before["width"], before["height"])
    assert abs(after["duration_s"] - (before["duration_s"] + 1.1)) < 0.25
    assert motion.probe_audio(out) is audio
    first = _frame(out, 0.2, tmp_path).getpixel((135, 470))
    at_one = _frame(out, 1.0, tmp_path).getpixel((135, 470))               # TikTok's default cover frame
    later = _frame(out, 2.0, tmp_path).getpixel((135, 240))
    assert first[1] > first[0] and at_one[1] > at_one[0]                   # the green cover, not the red film
    assert later[0] > later[1] + 60                                        # then the film itself


def test_a_film_that_cannot_be_covered_is_returned_unchanged(tmp_path):
    film = _film(tmp_path)
    assert motion.with_cover(film, "") == film                             # no hook, no cover
    broken = tmp_path / "nope.mp4"
    broken.write_bytes(b"not a video")
    assert motion.with_cover(broken, "Tajuk") == broken
