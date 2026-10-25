"""Executable effect adapters, not catalog-only prompt promises."""

import json

from semasa import motion_assets as assets
from semasa.motion_styles import EFFECT_LIBRARY


def test_auto_recommends_compatible_small_recipe(tmp_path):
    row = {"brief": "Explain a safety process", "options": {"effect_mode": "auto", "mode": "explainer"}}
    report = assets.prepare(row, tmp_path)
    assert [e["id"] for e in report["effects"]] == ["B04", "M03"]
    assert all(e["readiness"] != "fallback" for e in report["effects"])
    row["options"]["mode"] = "teaser"
    row["brief"] = "Calm abstract introduction"
    assert [e["id"] for e in assets.prepare(row, tmp_path)["effects"]] == ["B08"]


def test_legacy_job_without_effects_keeps_original_composition(tmp_path):
    assert assets.prepare({"options": {"style": "bright-education"}}, tmp_path)["effects"] == []


def test_every_catalog_effect_has_an_honest_adapter(tmp_path):
    effects = EFFECT_LIBRARY["effects"]
    assert len(effects) == len({e["id"] for e in effects}) == 99
    report = assets.prepare({"brief": "Packaging safety", "options": {"effects": [e["id"] for e in effects]}}, tmp_path)
    assert {p["id"] for p in report["effects"]} == {e["id"] for e in effects}
    assert all(p["readiness"] in {"ready", "autoasset", "manualasset", "fallback"} for p in report["effects"])
    assert report["mode"] == "auto"
    assert (tmp_path / report["assets"][0]["path"]).is_file()
    assert json.loads((tmp_path / "asset-plan.json").read_text()) == report
    assert all(p.get("reason") for p in report["effects"] if p["readiness"] == "fallback")
