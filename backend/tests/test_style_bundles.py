"""Selectable NEW Styles recipes drive the complete script and composition, not one overlay."""
import json

import pytest
from test_motion import GOOD, NOW, SCRIPT, FakeLLM, Store, _row, _runner

from semasa import motion
from semasa import motion_styles as styles


def test_new_editorial_is_a_complete_selectable_recipe():
    row = {"seconds": 30, "language": "en", "voice": "off",
           "options": {"style": "styles-editorial-explainer"}}
    recipe = styles.resolve(row)
    assert recipe["id"] == "styles-editorial-explainer"
    assert recipe["source"] == "Styles.docx"
    assert recipe["required_assets"] == []  # Native illustrations, NOT footage support.
    assert set(recipe["tracks"]) == {"hook", "captions", "layout", "proof", "illustration", "motion", "audio", "look"}
    plan = styles.complete_plan(row)
    assert [stage["role"] for stage in plan["stages"]] == ["Hook", "Fact", "Why", "Solution", "Outro"]
    assert plan["stages"][0]["start"] == 0
    assert plan["stages"][-1]["start"] == 27
    assert plan["stages"][-1]["end"] == 30
    assert all(stage["end"] > stage["start"] for stage in plan["stages"])
    prompt = motion.build_script_system(row, "")
    assert "COMPLETE STYLES.DOCX RECIPE" in prompt
    assert "styles-editorial-explainer" in prompt
    assert "proof" in prompt and "C06" in prompt and "B04" in prompt
    assert "no scrim" in prompt
    assert "stage plan" in motion.build_system(row, "")


@pytest.mark.parametrize("key", ["styles-editorial-explainer", "styles-kinetic-explainer", "styles-blueprint-explainer"])
def test_each_bundle_has_valid_effects_and_all_tracks(key):
    row = {"seconds": 60, "language": "bm", "options": {"style": key, "design": "continuous-line"}}
    recipe = styles.resolve(row)
    assert recipe["id"] == key
    effects = {e["id"]: e for e in styles.EFFECT_LIBRARY["effects"]}
    assert len(recipe["tracks"]) == 8
    for track in recipe["tracks"].values():
        assert track["adaptation"]
        assert all(code in effects and not effects[code]["conflict"] for code in track["codes"])
    plan = styles.complete_plan(row)
    assert plan["design"] == "continuous-line" and plan["stages"][-1]["start"] == 57
    assert plan["cta"] == "Jangan lupa follow kami untuk tip seterusnya"
    assert "one growing" in styles.prompt(row)


def test_footage_recipe_cannot_bypass_native_asset_gate():
    row = {"options": {"style": "styles-creator-footage", "assets": {"source-video": "fake.mp4"}}}
    assert any(r["id"] == "styles-creator-footage" and r["required_assets"] for r in styles.BUNDLES)
    with pytest.raises(ValueError, match="uploaded-footage"):
        styles.validate_export(row)


def test_worker_passes_complete_bundle_to_both_writers_and_saves_actual_plan(tmp_path):
    store = Store()
    row = _row(store, seconds=30, language="en", mascot="", voice="off",
               options={"style": "styles-editorial-explainer"})
    script = {"title": "A complete explanation", "scenes": [
        {"heading": h, "lines": [], "narration": ""}
        for h in ["Why check labels?", "Labels describe ingredients.",
                  "Context changes interpretation.", "Check the source before deciding."]
    ]}
    llm = FakeLLM([script, {"html": GOOD}])
    assert motion.process(store, llm, row, {"prompt": "", "cli": motion.CLI_VERSION},
                          runner=_runner(), workdir=tmp_path, now=NOW)
    assert all("COMPLETE STYLES.DOCX RECIPE" in system for system, _ in llm.asked
               if not system.startswith("You write the caption"))
    folder = tmp_path / row["id"][:8]
    plan = json.loads((folder / "recipe-plan.json").read_text())
    assert plan["recipe_id"] == "styles-editorial-explainer"
    assert [s["role"] for s in plan["stages"]] == ["Hook", "Fact", "Why", "Solution", "Outro"]
    saved = store.table(motion.TABLE).select("*").eq("id", row["id"]).execute().data[0]
    assert [s["role"] for s in saved["script"]] == ["Hook", "Fact", "Why", "Solution", "Outro"]
    assert [(s["start"], s["end"]) for s in plan["stages"]] == [
        (s["start"], s["start"] + s["duration"]) for s in saved["script"]
    ]


def test_complete_recipe_refuses_an_isolated_overlay_script():
    row = {"voice": "off", "options": {"style": "styles-kinetic-explainer"}}
    one = {**SCRIPT, "scenes": SCRIPT["scenes"][:1]}
    with pytest.raises(RuntimeError, match="1 scenes instead of 4"):
        motion.plan_scenes(FakeLLM([one, one]), row, "", "", "")


def test_teaser_plan_has_one_persistent_stage_not_four_pages():
    row = {"seconds": 10, "options": {"style": "styles-blueprint-explainer", "mode": "teaser"}}
    plan = styles.complete_plan(row)
    assert len(plan["stages"]) == 1 and plan["stages"][0]["end"] == 10
    assert plan["cta"] == "Stay tuned. Follow us for more"
