"""Real boundary provenance, normal approved pace, retries, and disclosed fallback."""
import asyncio
from pathlib import Path
from types import SimpleNamespace

import edge_tts
import pytest

from semasa import voice


class _Comm:
    seen: dict = {}
    fails = 0

    def __init__(self, text, voice_name, **kw):
        _Comm.seen = {'text':text, 'voice':voice_name, **kw}

    async def stream(self):
        if _Comm.fails > 0:
            _Comm.fails -= 1
            raise RuntimeError('No audio was received')
        yield {'type':'audio', 'data': b'ID3' + b'\x00' * 2000}
        yield {'type':'WordBoundary', 'offset':10000000, 'duration':5000000, 'text':'Hello'}
        yield {'type':'WordBoundary', 'offset':16000000, 'duration':5000000, 'text':'world'}


def _ffmpeg(calls):
    def run(cmd, **kw):
        calls.append(cmd)
        if cmd[0] == 'ffmpeg':
            Path(cmd[-1]).write_bytes(b'ID3' + b'\x01' * 2000)
        return SimpleNamespace(returncode=0, stdout='{"format":{"duration":"3.5"}}', stderr='')
    return run


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(voice.time, 'sleep', lambda _:None)
    monkeypatch.setattr(edge_tts, 'Communicate', _Comm)
    _Comm.fails = 0


def test_explicit_word_boundary_request(tmp_path):
    words = asyncio.run(voice._synth('Hello world', 'en-SG-WayneNeural', tmp_path / 'a.mp3'))
    assert _Comm.seen == {'text':'Hello world', 'voice':'en-SG-WayneNeural', 'boundary':'WordBoundary'}
    assert words == [(1.0, 1.5, 'Hello'), (1.6, 2.1, 'world')]


def test_approved_rate_and_report_preserve_real_word_times(tmp_path):
    for name in ['en-SG-WayneNeural', 'ms-MY-OsmanNeural']:
        calls = []
        got = voice.speak('Hello world', name, tmp_path / 'c.mp3', runner=_ffmpeg(calls))
        assert any('atempo=1' in cmd for cmd in calls)
        assert got == {'duration':3.5, 'words':[[1.0,1.5,'Hello'],[1.6,2.1,'world']],
                       'provider':'edge', 'voice_id':name, 'timing_source':'actual-word'}


def test_retry_and_disclosed_google_fallback(tmp_path, monkeypatch):
    import sys
    _Comm.fails = 2
    assert voice.speak('Hello world', 'en-SG-WayneNeural', tmp_path / 'e.mp3', runner=_ffmpeg([]))['provider'] == 'edge'
    class Google:
        def __init__(self, *args, **kw):
            pass
        def save(self, path):
            Path(path).write_bytes(b'ID3' + b'\x02' * 2000)
    monkeypatch.setitem(sys.modules, 'gtts', SimpleNamespace(gTTS=Google))
    _Comm.fails = 9
    got = voice.speak('Hai dunia', 'ms-MY-OsmanNeural', tmp_path / 'g.mp3', runner=_ffmpeg([]))
    assert got['provider'] == 'google' and got['voice_id'] == 'google-ms'
    assert got['requested_voice'] == 'ms-MY-OsmanNeural'
    assert got['words'] == [] and got['timing_source'] == 'estimated-phrase'
    monkeypatch.setitem(sys.modules, 'gtts', SimpleNamespace(gTTS=lambda *a, **k: (_ for _ in ()).throw(OSError('blocked'))))
    _Comm.fails = 9
    with pytest.raises(RuntimeError, match='Google said blocked'):
        voice.speak('Hello world', 'en-SG-WayneNeural', tmp_path / 'h.mp3', runner=_ffmpeg([]))


def test_spread_is_only_an_estimate_not_provider_alignment():
    assert voice.spread('a bb cccc', 0, 4)[-1][1] == 4
    assert voice.spread('', 0, 1) == []
