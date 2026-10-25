"""Latest approved designs and policies must reach both worker prompts."""
import pytest
from test_motion import SCRIPT, FakeLLM, Store

from semasa import motion, motion_styles


def test_worker_hydrates_origin_evidence_separately():
    store = Store()
    store.table('semasa_ideas').insert({'id': 'i', 'source_name': 'Journal', 'citations': [{'doi': '10.1/x'}],
                                       'source_summary': 'x' * 4000}).execute()
    row = motion.hydrate_evidence(store, {'idea_id': 'i', 'brief': 'short', 'options': {}})
    assert row['brief'] == 'short'
    assert row['options']['evidence']['source_name'] == 'Journal'
    assert '10.1/x' in motion.build_user(row, '', '')


@pytest.mark.parametrize("design,label", [("bright-editorial", "Design 1"), ("continuous-line", "Design 2")])
def test_design_consumed_by_both_prompts(design, label):
    row = {"language": "en", "options": {"design": design}}
    assert label in motion.build_script_system(row, "")
    assert label in motion.build_system(row, "")
    user = motion.build_user(row, '', '')
    assert 'APPROVED DESIGN' in user and '<!doctype html>' in user


def test_bm_and_silent_policy_and_cta():
    row = {"language": "bm", "voice": "off"}
    prompt = motion.build_script_system(row, "")
    assert "reading-paced" in prompt and "2 words" in prompt
    plan = motion.plan_scenes(FakeLLM([SCRIPT]), row, "", "", "")
    assert plan["scenes"][-1]["narration"] == "Jangan lupa follow kami untuk tips seterusnya"


def test_gimmick_is_one_persistent_scene():
    row = {"language": "en", "seconds": 10, "options": {"mode": "teaser"}}
    plan = motion.plan_scenes(FakeLLM([SCRIPT]), row, "", "", "")
    assert len(plan["scenes"]) == 1
    assert plan["scenes"][0]["id"] != "brand-outro"
    assert "Stay tuned. Follow us for more" in plan["scenes"][0]["heading"]
    assert "no standalone" in motion_styles.prompt(row)


def test_silent_overfull_reading_fails():
    scenes = [{"id": "s1", "heading": "word " * 80, "lines": [], "narration": ""},
              {"id": "brand-outro", "heading": "Follow us for more", "lines": []}]
    with pytest.raises(ValueError, match="30/60"):
        motion.fit_scenes(scenes, 30)


def test_unknown_audio_rights_block_export(tmp_path):
    with pytest.raises(ValueError, match="rights"):
        motion_styles.validate_export({"options": {"music": {"source": "user-reel", "rights": "unknown"}}})
