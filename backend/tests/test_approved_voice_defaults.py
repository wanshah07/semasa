"""Latest approved stock voices, provenance, and fail-closed narration."""
import asyncio

import pytest

from semasa import motion, voice


def test_language_defaults_and_explicit_overrides():
    assert voice.voice_for('en', '') == 'en-SG-WayneNeural'
    assert voice.voice_for('bm', '') == 'ms-MY-OsmanNeural'
    assert voice.voice_for('both', '') == 'ms-MY-OsmanNeural'
    assert voice.voice_for('en', 'female') == 'en-US-AvaMultilingualNeural'
    assert voice.voice_for('en', 'kitten') == 'kitten'
    assert voice.voice_for('en', 'en-GB-RyanNeural') == 'en-GB-RyanNeural'
    assert voice.tempo_for('en-SG-WayneNeural') == 1.0
    assert voice.tempo_for('ms-MY-OsmanNeural') == 1.0


def test_sentence_boundaries_never_impersonate_actual_words(tmp_path, monkeypatch):
    import edge_tts
    seen = {}
    class Communicate:
        def __init__(self, text, name, **kw):
            seen.update(kw)
        async def stream(self):
            yield {'type':'audio', 'data':b'x' * 2000}
            yield {'type':'SentenceBoundary', 'offset':0, 'duration':10000000, 'text':'Hello world'}
    monkeypatch.setattr(edge_tts, 'Communicate', Communicate)
    assert asyncio.run(voice._synth('Hello world', 'en-SG-WayneNeural', tmp_path / 'v.mp3')) == []
    assert seen['boundary'] == 'WordBoundary'


def test_speech_failure_is_not_a_successful_silent_film(tmp_path):
    def fail(*args):
        raise RuntimeError('service unavailable')
    with pytest.raises(RuntimeError, match='service unavailable'):
        motion.voice_scenes([{'narration':'Hello world'}], 'en', 'male', tmp_path, speak=fail)


def test_voice_report_records_actual_provider_and_alignment(tmp_path):
    def speak(text, name, path, runner):
        return {'duration':1.2, 'words':[[0, .5, 'Hello'], [.6, 1.2, 'world']],
                'provider':'edge', 'voice_id':name, 'timing_source':'actual-word'}
    scenes, _, note = motion.voice_scenes([{'narration':'Hello world'}], 'en', 'male', tmp_path, speak=speak)
    assert scenes[0]['voice_id'] == 'en-SG-WayneNeural'
    assert scenes[0]['voice_provider'] == 'edge'
    assert scenes[0]['timing_source'] == 'actual-word'
    assert 'en-SG-WayneNeural' in note
