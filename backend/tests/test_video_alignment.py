"""Latest-wins video behavior on current main, not stale PR86 signatures."""
from types import SimpleNamespace

from semasa import motion, motion_styles


def test_gimmick_is_always_ten_seconds():
    assert motion_styles.duration({'seconds':60,'options':{'mode':'teaser'}}) == 10
    row = {'seconds':10,'options':{'mode':'teaser'}}
    assert motion_styles.cta(row) == 'Stay tuned'
    assert 'Show and speak Stay tuned only' in motion_styles.prompt(row)
    assert motion_styles.video_format_policy.POLICY['cta']['gimmick'] == 'Stay tuned'


def test_personal_cta_is_not_corporate():
    assert motion_styles.cta({'stream':'linkedin','language':'en'}) == 'Follow me for more'


def test_silent_outro_has_no_voice():
    from test_motion import SCRIPT, FakeLLM
    plan = motion.plan_scenes(FakeLLM([SCRIPT]), {'voice':'off'}, '', '', '')
    assert all(not sc['narration'] for sc in plan['scenes'])


def test_preview_is_half_size(tmp_path):
    calls = []
    def run(cmd, **kw):
        calls.append(cmd)
        from pathlib import Path
        Path(cmd[-1]).write_bytes(b'fixture')
        return SimpleNamespace(returncode=0, stderr='')
    assert motion.make_preview(tmp_path / 'master.mp4',run).name == 'motion-preview.mp4'
    assert 'scale=iw/2:ih/2' in calls[0]


def test_personal_avatar_not_corporate_substitution():
    html = motion.inject_layers('<div id="root" data-duration="30"></div>',
        [{'id':'brand-outro','start':27,'duration':3,'heading':'Follow me for more'}],30,1080,1920,
        brand={'profile':'linkedin-personal','avatar':'assets/personal-avatar.png'})
    assert 'Ts. ChM. Muhammad' in html and 'personal-avatar.png' in html and 'official-logo' not in html


def test_continuous_line_never_silently_falls_back_to_editorial_cards(tmp_path):
    from test_motion import SCRIPT, FakeLLM, Store, _row, _runner
    store = Store()
    row = _row(store, voice='off', options={'design':'continuous-line'})
    assert not motion.process(store, FakeLLM([SCRIPT, None, None]), row,
                              {'cli':motion.CLI_VERSION, 'prompt':''}, runner=_runner(), workdir=tmp_path)
    saved = store.table(motion.TABLE).select('*').eq('id',row['id']).execute().data[0]
    assert 'Continuous Line' in saved['error']
    assert saved['status'] != 'done'


def test_source_label_only_appears_when_legally_required():
    row = {'language':'en', 'source_line':'Unsplash illustration'}
    assert 'source line "Unsplash illustration"' not in motion.build_system(row,'')
    row['options'] = {'legally_required_attribution':True}
    assert 'source line "Unsplash illustration"' in motion.build_system(row,'')


def test_no_sped_up_voice_instruction():
    prompt = motion.build_script_system({'language':'en','voice':'male'},'')
    assert 'BRISK' not in prompt
    assert 'Wayne' in prompt
