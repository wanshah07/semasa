import importlib.util
import json
from pathlib import Path


def test_original_docx_sections_and_occurrences():
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("sections", root / "ops/import_effect_sections.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    groups = module.parse(root / "docs/motion/Styles.docx")
    catalog = json.loads((root / "rules/motion/effect-sections.json").read_text())
    assert catalog["groups"] == groups
    import hashlib
    assert catalog["sha256"] == hashlib.sha256((root / "docs/motion/Styles.docx").read_bytes()).hexdigest()
    assert [g["title"] for g in groups] == [
        "Featured Effects",
        "Hooks",
        "Captions",
        "Layouts",
        "Proof",
        "Visual Beats",
        "Animated B-Roll",
        "Signature Effects",
        "Motion Pace",
        "Sound",
        "Colour & Finish",
    ]
    assert [len(g["ids"]) for g in groups] == [6, 10, 10, 10, 10, 10, 10, 10, 10, 10, 10]
    assert groups[1]["ids"].count("H06") == 2
    assert len({code for g in groups for code in g["ids"]}) == 99
