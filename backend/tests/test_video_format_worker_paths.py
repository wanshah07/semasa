"""Actual JS entrypoint payloads through real worker orchestration; renderer, writer and voice are explicit doubles."""
import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_motion import GOOD, SCRIPT, FakeLLM, Store, _row, _runner, fake_speak

from semasa import motion

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('entry', ['form', 'idea', 'draft'])
@pytest.mark.parametrize('design', ['bright-editorial', 'continuous-line'])
@pytest.mark.parametrize('fmt', ['english-voiced', 'malay-voiced', 'silent-first', 'gimmick'])
def test_actual_entrypoint_payload_reaches_worker(entry, design, fmt, tmp_path):
    if not shutil.which('node'):
        pytest.skip('Node required for cross-language payload check')
    script = '''import {motionRow,motionFromIdea,motionFromPost} from './web/src/lib/motion.js';
const d=JSON.parse(process.argv[1]);
const f={form:()=>motionRow({brief:'Local policy fixture',...d}).row,
idea:()=>motionFromIdea({id:'origin',source_title:'Local policy fixture'},null,d),
draft:()=>motionFromPost({id:'post',text:{en:{facebook:'Local policy fixture'}}},null,d)};
console.log(JSON.stringify(f[d.entry]()));'''
    payload = json.loads(subprocess.check_output(['node', '--input-type=module', '-e', script,
                         json.dumps({'entry':entry, 'design':design, 'format':fmt})], cwd=ROOT, text=True))
    store = Store()
    row = _row(store, **payload)
    seconds = 10 if fmt == 'gimmick' else 30
    base_run = _runner()
    def run(cmd, **kwargs):
        if cmd[0] == 'ffprobe':
            return SimpleNamespace(returncode=0, stderr='', stdout=json.dumps({
                'streams':[{'width':1080,'height':1920}], 'format':{'duration':str(seconds)}}))
        return base_run(cmd, **kwargs)
    llm = FakeLLM([SCRIPT, {'html':GOOD}])
    assert motion.process(store, llm, row, {'prompt':'', 'cli':motion.CLI_VERSION},
                          workdir=tmp_path, runner=run, speak=fake_speak)
    saved = store.table(motion.TABLE).select('*').eq('id',row['id']).execute().data[0]
    report = saved['check_report']['video_policy']
    assert report['format'] == fmt and report['seconds'] == seconds
    assert saved['options']['design'] == design
    assert saved['check_report']['preview']['width'] == 540
    assert fmt in llm.asked[0][0] and fmt in llm.asked[1][0]
    if fmt == 'silent-first':
        assert all(not scene['narration'] for scene in saved['script'])
        assert saved['check_report']['caption_timing'] == []
    if fmt == 'gimmick':
        assert len(saved['script']) == 1
        assert 'Stay tuned. Follow us for more.' in saved['script'][0]['heading']
