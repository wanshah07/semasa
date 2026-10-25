"""NEW Styles.docx is a separate, lossless effect library, not eight old recipes."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def importer():
    spec = importlib.util.spec_from_file_location("import_styles", ROOT / "ops/import_style_effects.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_new_source_is_complete_and_deduplicates_exact_bodies():
    module = importer()
    text = module.extract_docx(ROOT / "docs/motion/Styles.docx")
    data = module.parse_effects(text)
    assert data["occurrences"] == 106
    assert len(data["effects"]) == 99
    assert data["exact_duplicates"] == 7
    assert data["conflicting_codes"] == []
    assert "H07" not in {e["code"] for e in data["effects"]}
    assert sum(len(e["occurrences"]) for e in data["effects"]) == 106
    for effect in data["effects"]:
        assert effect["parameters"] and effect["steps"] and effect["fallback"]
        assert effect["instruction"] and effect["content_sha256"]
    assert {e["code"] for e in data["effects"] if len(e["occurrences"]) > 1} == {
        "H01", "C01", "P01", "X01", "X02", "X03", "H06",
    }


def test_conflicting_same_code_is_preserved_not_overwritten():
    module = importer()
    text = module.extract_docx(ROOT / "docs/motion/Styles.docx")
    first = module.parse_effects(text)["effects"][0]["instruction"]
    changed = first.replace("Cards: 5 cards", "Cards: 3 cards")
    data = module.parse_effects(first + "\n" + first + "\n" + changed)
    assert data["occurrences"] == 3
    assert data["exact_duplicates"] == 1
    assert len(data["effects"]) == 2
    assert data["conflicting_codes"] == ["X01"]
    assert len({e["id"] for e in data["effects"]}) == 2
    assert all(e["conflict"] for e in data["effects"])


def test_committed_catalog_and_provenance_match_the_archived_source():
    module = importer()
    source = ROOT / "docs/motion/Styles.docx"
    text = module.extract_docx(source)
    data = module.parse_effects(text)
    rules = ROOT / "rules/motion"
    assert (ROOT / "docs/motion/Styles.txt").read_text() == text
    assert json.loads((rules / "style-effects.json").read_text()) == data
    provenance = json.loads((rules / "style-effects-provenance.json").read_text())
    assert provenance["docx_sha256"] == module.sha(source.read_bytes())
    assert provenance["extraction_sha256"] == module.sha(text.encode())
    assert provenance["unique_effect_bodies"] == len(data["effects"])
    assert all(provenance[key] == value for key, value in data.items() if key != "effects")
