"""Lossless NEW Styles.docx importer. Source instructions remain inert reference data.

Run: python ops/import_style_effects.py /path/to/Styles.docx
Only exact (code, instruction body) duplicates collapse. Conflicts retain separate IDs.
The final quality-check line delimits each instruction, excluding adjacent Word labels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START = "# CES style instruction — "
END = "- Report any missing asset or unimplemented effect explicitly."
CATEGORIES = dict(H="Hooks", C="Captions", L="Layouts", P="Proof", V="Visual emphasis",
                  B="B-roll and illustration", X="Signature effects", M="Motion", S="Sound", F="Colour and finish")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def extract_docx(path: Path) -> str:
    """Read all document paragraphs, including tables, without executing embedded material."""
    with zipfile.ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs = ["".join(t.text or "" for t in p.findall(".//w:t", ns)) for p in root.findall(".//w:p", ns)]
    return "\n".join(paragraphs) + "\n"


def parse_effects(text: str) -> dict:
    effects = []
    seen = {}
    chunks = text.split(START)[1:]
    for ordinal, chunk in enumerate(chunks, 1):
        if END not in chunk:
            raise ValueError(f"Incomplete instruction at occurrence {ordinal}")
        body = START + chunk.split(END, 1)[0] + END
        title = chunk.splitlines()[0]
        code, name = title.split(" ", 1)
        if not re.fullmatch(r"[HCLPVBXMSF]\d{2}", code):
            raise ValueError(f"Invalid source code {code!r}")
        identity = (code, body)
        if identity in seen:
            seen[identity]["occurrences"].append(ordinal)
            continue

        def field(label, body=body, code=code):
            match = re.search(r"^- \*\*" + re.escape(label) + r":\*\* (.*)$", body, re.M)
            if not match:
                raise ValueError(f"Missing {label} in {code}")
            return match[1]

        steps = body.split("- **Steps:**", 1)[1].split("- **Assets:**", 1)[0].strip()
        assets = field("Assets")
        required, _, optional = assets.partition(" · optional: ")
        digest = sha(body.encode())
        effect = dict(id=code, code=code, name=name, category=CATEGORIES[code[0]],
                      description=field("What it does"), parameters=field("Parameters"),
                      when=field("When"), layer=field("Layer / track"), steps=steps,
                      required_assets=[a.replace(" (⚠ MISSING)", "") for a in required.split(", ") if a != "—"],
                      optional_assets=optional.split(", ") if optional else [], fallback=field("Fallback"),
                      instruction=body, content_sha256=digest, occurrences=[ordinal], conflict=False)
        effects.append(effect)
        seen[identity] = effect
    counts = Counter(e["code"] for e in effects)
    conflicts = sorted(code for code, count in counts.items() if count > 1)
    for effect in effects:
        if effect["code"] in conflicts:
            effect["conflict"] = True
            effect["id"] = effect["code"] + "@" + effect["content_sha256"][:12]
    return dict(source_filename="Styles.docx", occurrences=len(chunks), exact_duplicates=len(chunks) - len(effects),
                conflicting_codes=conflicts, missing_codes=["H07"] if "H07" not in counts else [],
                categories=dict(Counter(e["category"] for e in effects)), effects=effects)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    text = extract_docx(args.source)
    catalog = parse_effects(text)
    if catalog["occurrences"] != 106:
        raise ValueError("Expected the NEW 106-occurrence Styles.docx; review changed source before importing")
    docs = ROOT / "docs/motion"
    docs.mkdir(parents=True, exist_ok=True)
    destination = docs / "Styles.docx"
    if args.source.resolve() != destination.resolve():
        shutil.copyfile(args.source, destination)
    (docs / "Styles.txt").write_text(text, encoding="utf-8")
    folder = ROOT / "rules/motion"
    (folder / "style-effects.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    provenance = {k: v for k, v in catalog.items() if k != "effects"}
    provenance.update(docx_sha256=sha(args.source.read_bytes()), extraction_sha256=sha(text.encode()),
                      unique_effect_bodies=len(catalog["effects"]),
                      note="Separate from the old 8-section/7-distinct complete-recipe attachment. H07 not supplied.")
    (folder / "style-effects-provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(provenance, indent=2))


if __name__ == "__main__":
    main()
