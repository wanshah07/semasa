"""Native motion transforms existing authored headings, not duplicate overlay copy."""

import pytest
from bs4 import BeautifulSoup

from semasa import motion_assets


@pytest.mark.parametrize(
    ("code", "text", "marker"),
    [
        ("H03", "Why read labels?", "expo.out"),
        ("V01", "Read the label", "yPercent:110"),
        ("V03", "Read labels", "border"),
    ],
)
def test_other_native_effects_transform_only_existing_copy(tmp_path, code, text, marker):
    report = motion_assets.prepare({"options": {"effects": [code]}}, tmp_path)
    document = (f'<html><body><div id="root"><h2>{text}</h2><p id="captions">Caption unchanged</p></div>'
                '<script>window.__timelines={main:gsap.timeline({paused:true})};</script></body></html>')
    out = motion_assets.inject(document, report, [{"id": "s1", "heading": text, "start": 0, "duration": 4}], 4)
    assert f'data-native-effect="{code}"' in out
    assert marker in out
    assert BeautifulSoup(out, "html.parser").h2.get_text(" ", strip=True) == text
    assert '<p id="captions">Caption unchanged</p>' in out
    assert report["effects"][0]["readiness"] == "ready"


@pytest.mark.parametrize("code", ["H01", "H03", "V01", "V03"])
def test_missing_or_ineligible_heading_is_skipped_not_fabricated(tmp_path, code):
    report = motion_assets.prepare({"options": {"effects": [code]}}, tmp_path)
    document = '<html><body><div id="root"><p>Original only</p></div></body></html>'
    out = motion_assets.inject(document, report, [{"id": "brand-outro", "heading": "Follow us", "start": 0, "duration": 3}], 3)
    assert "data-native-effect" not in out
    assert "effect-panel" not in out
    assert "Follow us" not in out
    assert report["effects"][0]["readiness"] == "fallback"
    assert "skipped" in report["effects"][0]["reason"]


def test_hooks_do_not_stack_and_visual_cues_use_later_scenes(tmp_path):
    report = motion_assets.prepare({"options": {"effects": ["H01", "H03", "V01", "V03"]}}, tmp_path)
    texts = ["Why read labels?", "Read the label", "Keep safe"]
    scenes = [{"id": f"s{i}", "heading": t, "start": i * 4, "duration": 4} for i, t in enumerate(texts)]
    document = '<html><body><div id="root">' + "".join(f"<h2>{t}</h2>" for t in texts) + "</div></body></html>"
    out = motion_assets.inject(document, report, scenes, 12)
    assert len(BeautifulSoup(out, "html.parser").select("h2")) == 3
    assert [e["readiness"] for e in report["effects"]] == ["ready", "fallback", "ready", "ready"]
    assert [e["cue"]["start"] for e in report["effects"] if "cue" in e] == [0, 4, 8]


def test_question_preserves_inline_design_and_escaped_copy(tmp_path):
    report = motion_assets.prepare({"options": {"effects": ["H03"]}}, tmp_path)
    document = '<html><body><div id="root"><h1>Why <em style="color:red">read &amp; learn?</em></h1></div></body></html>'
    out = motion_assets.inject(document, report, [{"id": "s1", "heading": "Why read & learn?", "duration": 4}], 4)
    soup = BeautifulSoup(out, "html.parser")
    assert soup.select_one('h1 em[style="color:red"]') is not None
    assert soup.h1.get_text(" ", strip=True) == "Why read & learn?"
    assert report["effects"][0]["adapter"] == "native-text"
    assert report["effects"][0]["asset"] is None


def test_question_first_does_not_invent_a_question(tmp_path):
    report = motion_assets.prepare({"options": {"effects": ["H03"]}}, tmp_path)
    document = '<html><body><div id="root"><h1>Read labels</h1></div></body></html>'
    out = motion_assets.inject(document, report, [{"id": "s1", "heading": "Read labels", "duration": 4}], 4)
    assert "data-native-effect" not in out
    assert report["effects"][0]["readiness"] == "fallback"


def test_repeated_heading_is_scoped_to_its_scene(tmp_path):
    report = motion_assets.prepare({"options": {"effects": ["V01", "V03"]}}, tmp_path)
    document = ('<html><body><div id="root"><section id="s1"><h1>Read labels</h1></section>'
                '<section id="s2"><h1>Read labels</h1></section></div></body></html>')
    scenes = [{"id": f"s{i}", "heading": "Read labels", "start": (i-1)*4, "duration": 4} for i in [1, 2]]
    out = motion_assets.inject(document, report, scenes, 8)
    soup = BeautifulSoup(out, "html.parser")
    assert soup.select_one('#s1 [data-native-effect="V01"]') is not None
    assert soup.select_one('#s2 [data-native-effect="V03"]') is not None
    assert report["effects"][1]["cue"]["start"] == 4


def test_ambiguous_unscoped_heading_is_skipped(tmp_path):
    report = motion_assets.prepare({"options": {"effects": ["H01"]}}, tmp_path)
    document = '<html><body><div id="root"><h1>Read labels</h1><h2>Read labels</h2></div></body></html>'
    out = motion_assets.inject(document, report, [{"id": "s1", "heading": "Read labels", "duration": 4}], 4)
    assert 'data-native-effect' not in out
    assert report["effects"][0]["readiness"] == "fallback"


def test_headline_selection_reaches_deterministic_timeline(tmp_path):
    report = motion_assets.prepare({"options": {"effects": ["H01"]}}, tmp_path)
    document = ('<html><body><div id="root"><h1>Keep food safe</h1></div>'
                '<script>window.__timelines={main:gsap.timeline({paused:true})};</script></body></html>')
    out = motion_assets.inject(document, report, [{"id": "s1", "heading": "Keep food safe", "start": 0, "duration": 4}], 4)
    assert 'data-native-effect="H01"' in out
    assert "scale:2.2" in out
    assert "assets/concept.svg" not in out
    assert out.count("Keep food safe") == 1
    assert report["effects"][0]["readiness"] == "ready"
    assert report["effects"][0]["cue"] == {"start": 0.0, "duration": 1.8, "scene_id": "s1"}
