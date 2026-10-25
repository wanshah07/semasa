"""Actual selected format -> worker configuration; no network or paid synthesis."""
import pytest
from semasa import motion, motion_styles


@pytest.mark.parametrize('fmt,language,voice,seconds', [
    ('english-voiced', 'en', 'kitten', 60), ('malay-voiced', 'bm', 'female', 60),
    ('silent-first', 'en', 'off', 60), ('gimmick', 'en', 'kitten', 10),
])
def test_selected_format_resolves_in_worker(fmt, language, voice, seconds):
    from semasa.video_format_policy import normalize
    row = normalize({'seconds':60, 'options':{'format':fmt}})
    assert (row['language'], row['voice'], row['seconds']) == (language, voice, seconds)
    assert row['options']['policy_version'] == 1
    assert motion_styles.duration(row) == seconds
    assert fmt in motion.build_script_system(row, '')


def test_all_teasers_are_ten_seconds():
    assert motion_styles.duration({'seconds':60, 'options':{'mode':'teaser'}}) == 10


def test_personal_profile_never_uses_ws_logo():
    from semasa.video_format_policy import normalize
    row = normalize({'stream':'linkedin', 'language':'bm', 'resolution':'square'})
    assert row['language'] == 'en' and row['resolution'] == 'portrait'
    assert motion_styles.cta(row) == 'Follow me for more'
    html = motion.inject_layers('<div id="root" data-duration="30"></div>',
        [{'id':'brand-outro', 'heading':'Follow me for more', 'start':27, 'duration':3}],
        30, 1080, 1920, False, brand={'profile':'linkedin-personal', 'avatar':'assets/personal-avatar.png'})
    assert 'Ts. ChM. Muhammad' in html and 'personal-avatar.png' in html
    assert 'official-logo' not in html


def test_missing_personal_avatar_blocks_before_any_writer(tmp_path):
    from semasa.video_format_policy import prepare_brand
    with pytest.raises(ValueError, match='avatar'):
        prepare_brand(None, {'stream':'linkedin'}, tmp_path)


def test_silent_outro_has_no_narration():
    from test_motion import FakeLLM, SCRIPT
    plan = motion.plan_scenes(FakeLLM([SCRIPT]), {'voice':'off'}, '', '', '')
    assert all(not scene['narration'] for scene in plan['scenes'])


def test_requested_voice_never_silently_becomes_silent(tmp_path):
    def unavailable(*args):
        raise RuntimeError('offline')
    with pytest.raises(RuntimeError, match='offline'):
        motion.voice_scenes([{'narration':'A fact.'}], 'en', 'female', tmp_path, speak=unavailable)
