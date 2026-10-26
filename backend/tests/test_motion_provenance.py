import json

from test_motion import GOOD, SCRIPT, FakeLLM, Store, _row, _runner

from semasa import motion


def test_provenance_sidecar_survives_export_without_onscreen_source_tags(tmp_path):
    store=Store()
    row=_row(store,language='en',voice='off',options={'evidence':{'source_name':'Journal',
        'citations':[{'doi':'10.1234/example'}]}})
    assert motion.process(store,FakeLLM([SCRIPT,{'html':GOOD}]),row,{'cli':motion.CLI_VERSION,'prompt':''},
                          runner=_runner(),workdir=tmp_path)
    raw=store.bucket.files[f"motion/{row['id']}-provenance.json"][0]
    sidecar=json.loads(raw)
    assert sidecar['evidence']['citations'] == [{'doi':'10.1234/example'}]
    assert sidecar['stock_is_evidence'] is False
    assert sidecar['photos'] == []
