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
    monkeypatch.setattr(edge_tts, "Communicate", _Comm)
    out = Path(tmp_path) / "a.mp3"
    words = asyncio.run(voice._synth("Hai dunia", "en-US-AndrewMultilingualNeural", out))
    assert _Comm.seen["boundary"] == "WordBoundary", "edge-tts >= 7.2 defaults to SentenceBoundary: no word timing"
    assert words == [(0.5, 0.8, "Hai"), (0.9, 1.15, "dunia")]
    assert out.read_bytes().startswith(b"ID3")


def test_malay_voices_are_read_a_little_faster(monkeypatch, tmp_path):
    monkeypatch.setattr(edge_tts, "Communicate", _Comm)
    asyncio.run(voice._synth("Hai", "ms-MY-OsmanNeural", Path(tmp_path) / "b.mp3"))
    assert _Comm.seen["rate"] == "+15%" and _Comm.seen["boundary"] == "WordBoundary"
