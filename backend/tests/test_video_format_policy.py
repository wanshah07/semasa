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
    from test_motion import SCRIPT, FakeLLM
    plan = motion.plan_scenes(FakeLLM([SCRIPT]), {'voice':'off'}, '', '', '')
    assert all(not scene['narration'] for scene in plan['scenes'])


def test_requested_voice_never_silently_becomes_silent(tmp_path):
    def unavailable(*args):
        raise RuntimeError('offline')
    with pytest.raises(RuntimeError, match='offline'):
        motion.voice_scenes([{'narration':'A fact.'}], 'en', 'female', tmp_path, speak=unavailable)


def test_zero_duration_voice_blocks_instead_of_shipping_silence(tmp_path):
    def empty(*args):
        return {'duration':0, 'words':[]}
    with pytest.raises(RuntimeError, match='duration'):
        motion.voice_scenes([{'narration':'A fact.'}], 'en', 'female', tmp_path, speak=empty)


def test_preview_is_half_master_without_touching_audio(tmp_path):
    from types import SimpleNamespace
    calls = []
    def run(cmd, **kwargs):
        calls.append(cmd)
        from pathlib import Path
        Path(cmd[-1]).write_bytes(b'test-double')
        return SimpleNamespace(returncode=0, stderr='')
    source = tmp_path / 'master.mp4'
    source.write_bytes(b'test-double')
    assert motion.make_preview(source, run).name == 'motion-preview.mp4'
    assert 'scale=iw/2:ih/2' in calls[0]
    assert calls[0][calls[0].index('-c:a')+1] == 'copy'


@pytest.mark.parametrize('row', [
    {'voice':'clone'}, {'options':{'talking_avatar':True}},
    {'options':{'source_footage':'private/source.mp4'}},
])
def test_unconfigured_runtime_capabilities_block_clearly(row):
    from semasa.video_format_policy import normalize
    with pytest.raises(ValueError, match='unconfigured|unsupported'):
        normalize(row)


@pytest.mark.parametrize('text', [
    'Hook -> Fact -> Why -> Solution', 'Frame one: strong truthful hook',
    'reading-paced', '2 words', '154', 'ms-MY Edge +15%', 'never Indonesian', 'pembungkusan',
    'no background', 'No source-labels', 'Protect faces; torso overlays allowed',
    'No LabelLiteracy', 'page counters', 'FirstAuthor et al.',
    'LICENSES/provenance', 'never imply that a stock product was tested',
    'qualitative diagrams', 'ducking', 'licensed/self-owned', 'no noise/drone',
])
def test_policy_in_both_writer_prompts(text):
    row = {'language':'en', 'voice':'off', 'options':{'format':'silent-first'}}
    assert text in motion.build_script_system(row, '')
    assert text in motion.build_system(row, '')


def test_policy_capabilities_are_honest():
    from semasa.video_format_policy import POLICY
    assert 'unconfigured' in POLICY['capabilities']['talking_avatar']
    assert 'unconfigured' in POLICY['capabilities']['voice_clone']
    assert 'unconfigured' in POLICY['capabilities']['drive_archive']


def test_mute_all_consumption(tmp_path):
    from test_motion import GOOD, SCRIPT, FakeLLM, Store, _row, _runner
    store = Store()
    row = _row(store, language='en', voice='kitten', options={'mute_all':True, 'format':'english-voiced'})
    calls = []
    def never_speak(*args):
        raise AssertionError('mute all must not synthesize')
    assert motion.process(store, FakeLLM([SCRIPT, {'html':GOOD}]), row,
                          {'prompt':'', 'cli':motion.CLI_VERSION}, runner=_runner(calls=calls),
                          speak=never_speak, workdir=tmp_path)
    assert not any('-filter_complex' in cmd for cmd in calls)
    saved = store.table(motion.TABLE).select('*').eq('id',row['id']).execute().data[0]
    assert saved['check_report']['video_policy']['mute_all']
    assert saved['check_report']['video_policy']['voice'] == 'off'
    assert 'all audio muted' in saved['style_note']
    assert 'wan-brand-final' in saved['html']
