"""The narration's word timing: edge-tts must be asked for WordBoundary, or the mascot's mouth never moves."""

import asyncio
from pathlib import Path

import edge_tts

from semasa import voice


class _Comm:
    seen: dict = {}

    def __init__(self, text, voice_name, **kw):
        _Comm.seen = {"text": text, "voice": voice_name, **kw}

    async def stream(self):
        yield {"type": "audio", "data": b"ID3" + b"\x00" * 40}
        yield {"type": "WordBoundary", "offset": 5_000_000, "duration": 3_000_000, "text": "Hai"}
        yield {"type": "WordBoundary", "offset": 9_000_000, "duration": 2_500_000, "text": "dunia"}


def test_the_word_boundary_is_asked_for_and_the_words_come_back_timed(monkeypatch, tmp_path):
    monkeypatch.setattr(voice, "_WORD_OK", True)
    monkeypatch.setattr(edge_tts, "Communicate", _Comm)
    out = Path(tmp_path) / "a.mp3"
    words = asyncio.run(voice._synth("Hai dunia", "en-US-AndrewMultilingualNeural", out))
    assert _Comm.seen["boundary"] == "WordBoundary", "edge-tts >= 7.2 defaults to SentenceBoundary: no word timing"
    assert words == [(0.5, 0.8, "Hai"), (0.9, 1.15, "dunia")]
    assert out.read_bytes().startswith(b"ID3")


def test_malay_voices_are_read_a_little_faster(monkeypatch, tmp_path):
    monkeypatch.setattr(voice, "_WORD_OK", True)
    monkeypatch.setattr(edge_tts, "Communicate", _Comm)
    asyncio.run(voice._synth("Hai", "ms-MY-OsmanNeural", Path(tmp_path) / "b.mp3"))
    assert _Comm.seen["rate"] == "+25%" and _Comm.seen["boundary"] == "WordBoundary"


class _NoWords:
    """The runner's behaviour on 25 Oct 2026: word boundaries -> no audio; sentence boundaries -> audio + one sentence span."""
    calls: list = []

    def __init__(self, text, voice_name, **kw):
        self.boundary = kw.get("boundary")
        _NoWords.calls.append(self.boundary)

    async def stream(self):
        if self.boundary == "WordBoundary":
            raise RuntimeError("No audio was received. Please verify that your parameters are correct.")
        yield {"type": "audio", "data": b"ID3" + b"\x00" * 2000}
        yield {"type": "SentenceBoundary", "offset": 10_000_000, "duration": 20_000_000, "text": "Swipe three or four times."}


def test_when_word_boundaries_give_no_audio_sentences_are_used_and_words_are_spread(monkeypatch, tmp_path):
    # the film came out silent because of exactly this (25 Oct 2026)
    monkeypatch.setattr(voice, "_WORD_OK", True)
    monkeypatch.setattr(edge_tts, "Communicate", _NoWords)
    _NoWords.calls.clear()
    got = voice.speak("Swipe three or four times.", "en-US-AndrewMultilingualNeural", Path(tmp_path) / "c.mp3",
                      runner=lambda *a, **k: type("R", (), {"stdout": '{"format": {"duration": "3.5"}}'})())
    assert _NoWords.calls == ["WordBoundary", "SentenceBoundary"] and voice._WORD_OK is False
    words = got["words"]
    assert [w[2] for w in words] == ["Swipe", "three", "or", "four", "times."]
    assert words[0][0] == 1.0 and abs(words[-1][1] - 3.0) < 0.01, "spread across the sentence's own span, 1 s to 3 s"
    assert all(a[1] <= b[0] + 0.001 for a, b in zip(words, words[1:], strict=False)), "in order, no overlap"
    # the second call goes straight to sentences: no wasted attempt
    _NoWords.calls.clear()
    voice.speak("Again.", "en-US-AndrewMultilingualNeural", Path(tmp_path) / "d.mp3",
                runner=lambda *a, **k: type("R", (), {"stdout": '{"format": {"duration": "1.0"}}'})())
    assert _NoWords.calls == ["SentenceBoundary"]


def test_spread_is_proportional_and_safe():
    s = voice.spread("a bb cccc", 0.0, 4.0)
    assert [w[2] for w in s] == ["a", "bb", "cccc"] and s[0][0] == 0.0 and abs(s[-1][1] - 4.0) < 0.01
    assert (s[2][1] - s[2][0]) > (s[0][1] - s[0][0])
    assert voice.spread("", 0, 1) == [] and voice.spread("x", 2, 2) == []
