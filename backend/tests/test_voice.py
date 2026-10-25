"""The Edge voice: the plain call (no rate, no boundary setting), retried, then sped up by ffmpeg afterwards."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import edge_tts
import pytest

from semasa import voice


class _Comm:
    seen: dict = {}
    fails = 0                     # how many calls come back empty before one succeeds

    def __init__(self, text, voice_name, **kw):
        _Comm.seen = {"text": text, "voice": voice_name, **kw}

    async def stream(self):
        if _Comm.fails > 0:
            _Comm.fails -= 1
            raise RuntimeError("No audio was received. Please verify that your parameters are correct.")
        yield {"type": "audio", "data": b"ID3" + b"\x00" * 2000}
        yield {"type": "SentenceBoundary", "offset": 10_000_000, "duration": 20_000_000, "text": "Swipe three or four times."}


def _ffmpeg(calls):
    """A runner that answers ffprobe with 3.5 s and ffmpeg by writing the 'faster' file."""
    def run(cmd, **kw):
        calls.append(cmd)
        if cmd[0] == "ffmpeg":
            Path(cmd[-1]).write_bytes(b"ID3" + b"\x01" * 2000)
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout='{"format": {"duration": "3.5"}}', stderr="")
    return run


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(voice.time, "sleep", lambda s: None)
    monkeypatch.setattr(edge_tts, "Communicate", _Comm)
    _Comm.fails = 0


def test_the_call_to_the_service_is_plain_no_rate_and_no_boundary_setting(tmp_path):
    # on the runner (25 Oct 2026) any request carrying a rate or a boundary setting got "No audio was received"
    asyncio.run(voice._synth("Hai", "ms-MY-OsmanNeural", Path(tmp_path) / "a.mp3"))
    assert _Comm.seen == {"text": "Hai", "voice": "ms-MY-OsmanNeural"}


def test_the_speed_comes_from_ffmpeg_afterwards_and_the_word_times_follow(tmp_path):
    calls: list = []
    got = voice.speak("Swipe three or four times.", "en-US-AndrewMultilingualNeural", Path(tmp_path) / "c.mp3",
                      runner=_ffmpeg(calls))
    tempo = next(c for c in calls if c[0] == "ffmpeg")
    assert "atempo=1.15" in tempo and "libmp3lame" in tempo
    words = got["words"]
    assert [w[2] for w in words] == ["Swipe", "three", "or", "four", "times."]
    assert abs(words[0][0] - 1.0 / 1.15) < 0.01 and abs(words[-1][1] - 3.0 / 1.15) < 0.01, "times scaled by the tempo"
    assert got["duration"] == 3.5 and (Path(tmp_path) / "c.mp3").read_bytes()[3:5] == b"\x01\x01", "the faster file replaced it"
    calls.clear()
    voice.speak("Hai.", "ms-MY-OsmanNeural", Path(tmp_path) / "d.mp3", runner=_ffmpeg(calls))
    assert any("atempo=1.25" in c for c in calls if c[0] == "ffmpeg"), "Malay is read faster than English"
    assert (voice.tempo_for("en-US-AvaMultilingualNeural"), voice.tempo_for("ms-MY-YasminNeural")) == (1.15, 1.25)


def test_an_empty_answer_is_asked_again_and_a_service_that_stays_silent_raises(tmp_path, monkeypatch):
    _Comm.fails = 2
    got = voice.speak("Hai.", "en-US-AndrewMultilingualNeural", Path(tmp_path) / "e.mp3", runner=_ffmpeg([]))
    assert got["duration"] == 3.5 and _Comm.fails == 0, "two empty answers, the third call worked"
    _Comm.fails = 5
    import sys
    monkeypatch.setitem(sys.modules, "gtts", SimpleNamespace(gTTS=lambda *a, **k: (_ for _ in ()).throw(OSError("blocked"))))
    with pytest.raises(RuntimeError, match="No audio was received"):
        voice.speak("Hai.", "en-US-AndrewMultilingualNeural", Path(tmp_path) / "f.mp3", runner=_ffmpeg([]))


def test_a_failed_tempo_keeps_the_plain_recording(tmp_path):
    def run(cmd, **kw):
        if cmd[0] == "ffmpeg":
            return SimpleNamespace(returncode=1, stdout="", stderr="atempo broke")
        return SimpleNamespace(returncode=0, stdout='{"format": {"duration": "3.5"}}', stderr="")
    got = voice.speak("Hai.", "en-US-AndrewMultilingualNeural", Path(tmp_path) / "g.mp3", runner=run)
    assert got["duration"] == 3.5 and got["words"][0][0] == 1.0, "unscaled times: the recording was not sped up"


def test_spread_is_proportional_and_safe():
    s = voice.spread("a bb cccc", 0.0, 4.0)
    assert [w[2] for w in s] == ["a", "bb", "cccc"] and s[0][0] == 0.0 and abs(s[-1][1] - 4.0) < 0.01
    assert (s[2][1] - s[2][0]) > (s[0][1] - s[0][0])
    assert voice.spread("", 0, 1) == [] and voice.spread("x", 2, 2) == []


def test_when_edge_stays_silent_google_narrates_and_the_row_can_say_so(tmp_path, monkeypatch):
    import sys
    saved = {}

    class _G:
        def __init__(self, text, lang="en"):
            saved.update(text=text, lang=lang)

        def save(self, path):
            Path(path).write_bytes(b"ID3" + b"\x02" * 2000)
    monkeypatch.setitem(sys.modules, "gtts", SimpleNamespace(gTTS=_G))
    _Comm.fails = 9
    got = voice.speak("Hai dunia.", "ms-MY-OsmanNeural", Path(tmp_path) / "h.mp3", runner=_ffmpeg([]))
    assert got["provider"] == "google" and got["words"] == [] and saved == {"text": "Hai dunia.", "lang": "ms"}
    _Comm.fails = 9
    voice.speak("Hello.", "en-US-AvaMultilingualNeural", Path(tmp_path) / "i.mp3", runner=_ffmpeg([]))
    assert saved["lang"] == "en"
    monkeypatch.setitem(sys.modules, "gtts", SimpleNamespace(gTTS=lambda *a, **k: (_ for _ in ()).throw(OSError("blocked"))))
    _Comm.fails = 9
    with pytest.raises(RuntimeError, match="Edge said No audio.*Google said blocked"):
        voice.speak("Hello.", "en-US-AvaMultilingualNeural", Path(tmp_path) / "j.mp3", runner=_ffmpeg([]))
