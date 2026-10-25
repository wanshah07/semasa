"""The published roadmap is the exact deduplicated PR79 fallback cohort."""
import json
from pathlib import Path

from semasa import motion_assets


def test_inventory_preserves_all_source_sections_and_exact_cohort():
    root = Path(__file__).resolve().parents[2]
    inventory = json.loads((root / "docs/motion/native-effects-roadmap/inventory.json").read_text())
    sections = json.loads((root / "rules/motion/effect-sections.json").read_text())
    library = json.loads((root / "rules/motion/style-effects.json").read_text())
    originals = {e["id"]: e for e in library["effects"]}
    effects = inventory["effects"]
    assert len(effects) == len({e["id"] for e in effects}) == 94
    assert inventory["missing_codes"] == ["H07"]
    assert "H07" not in {e["id"] for e in effects}
    assert inventory["conflicting_codes"] == []
    assert [g["title"] for g in inventory["groups"]] == [g["title"] for g in sections["groups"]]
    assert {e["id"] for e in effects} == set(motion_assets.POLICY) - set(inventory["existing_adaptations"])
    assert {e["id"] for e in effects if e["status"] == "render_tested_heading_adaptation"} == {"H01", "H03", "V01", "V03"}
    for entry in effects:
        assert entry["source_sections"] == [g["title"] for g in sections["groups"] if entry["id"] in g["ids"]]
        assert entry["original_fallback"]
        assert entry["required_assets_original"] == originals[entry["id"]]["required_assets"]
