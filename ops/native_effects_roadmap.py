"""Rebuild the deduplicated PR79 fallback inventory without modifying source imports."""
import argparse
import collections
import json
import subprocess
from pathlib import Path

BASE = "f5e6fb4e23ae17ec1a6cba3f8d8bc97108718931"
BATCH = {"H01", "H03", "V01", "V03"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    rules = root / "rules/motion"
    baseline = json.loads(subprocess.check_output(["git", "show", f"{BASE}:rules/motion/effect-adapters.json"], cwd=root))
    policy = json.loads((rules / "effect-adapters.json").read_text())
    library = json.loads((rules / "style-effects.json").read_text())
    sections = json.loads((rules / "effect-sections.json").read_text())
    effects = {e["id"]: e for e in library["effects"]}
    fallback = {code for code, p in baseline.items() if p["readiness"] == "fallback"}
    assert len(effects) == 99 and len(fallback) == 94
    entries = []
    for code in baseline:
        if code not in fallback:
            continue
        e = effects[code]
        groups = [g["title"] for g in sections["groups"] if code in g["ids"]]
        # Core-only means an authored-text adaptation is possible without source editing,
        # NOT equivalence to the full catalog footage specification.
        text_adaptation = code in BATCH | {"V10"}
        core_only = text_adaptation or not e["required_assets"]
        entries.append({"id": code, "name": e["name"], "source_sections": groups,
                        "primary_section": groups[0], "source_occurrences": e["occurrences"],
                        "conflict": e["conflict"], "baseline_readiness": "fallback",
                        "implementation_track": "core_renderer" if core_only else "needs_assets_and_core_renderer",
                        "required_assets_original": e["required_assets"], "optional_assets_original": e["optional_assets"],
                        "asset_note": ("Authored heading suffices for limited text adaptation; original footage technique remains unsupported." if text_adaptation else
                                       "No required assets in original source; core renderer missing. Optional inputs remain optional." if core_only else
                                       "Original asset requirements remain blockers; a native renderer is also required. Assets alone do not implement this effect."),
                        "original_fallback": e["fallback"],
                        "status": "render_tested_heading_adaptation" if code in BATCH and policy[code]["readiness"] == "ready" else "not_implemented",
                        "native_scope": policy[code].get("scope", "none")})
    assert len(entries) == len({e["id"] for e in entries}) == 94
    inventory = {"baseline_commit": BASE, "catalog_unique_ids": 99, "source_occurrences": library["occurrences"],
                 "source_exact_duplicates": library["exact_duplicates"], "missing_codes": library["missing_codes"],
                 "conflicting_codes": library["conflicting_codes"], "baseline_fallback_count": len(entries),
                 "batch_ids": sorted(BATCH), "status_counts": dict(collections.Counter(e["status"] for e in entries)),
                 "track_counts": dict(collections.Counter(e["implementation_track"] for e in entries)),
                 "existing_adaptations": {k: v for k, v in baseline.items() if k not in fallback},
                 "groups": [{"title": g["title"], "ids": [code for code in dict.fromkeys(g["ids"]) if code in fallback]} for g in sections["groups"]],
                 "effects": entries}
    lines = ["# Native effects roadmap — PR79 baseline", "", f"Frozen baseline: `{BASE}` (PR79, not modified).", "",
             "99 unique IDs / 106 source occurrences; 7 exact duplicates retained as provenance, H07 absent (not invented), no imported conflicting codes.",
             "94 unique concept fallbacks enumerated below. Group headings preserve all 11 exact source section titles. Each checklist row occurs once under its first source section; JSON also retains all section memberships and original asset/fallback requirements.", "",
             "## Scope and counts", "", f"Status counts: `{inventory['status_counts']}`.", f"Implementation tracks: `{inventory['track_counts']}`.",
             "Four render-tested **heading-only** native adaptations are not full source-video equivalents. Existing five prepared-panel/vector/screenshot adaptations are unchanged. The other 90 baseline fallbacks remain unimplemented. V10 is deferred: its source says both 3s overall and ≥3.3s hold after the last chunk; this timing conflict is not silently resolved.",
             "Core-renderer track can use existing authored headings, or has no required assets in the original source (V08). Needs-assets-and-core-renderer requires both authentic original inputs AND native implementation; source video, word timing, masks, data, audio and rights are not created by this batch. Captions are not fake word-aligned. No source-footage processing is claimed.", ""]
    for group in sections["groups"]:
        lines += [f"## {group['title']}", ""]
        owned = [e for e in entries if e["primary_section"] == group["title"]]
        if not owned:
            lines += ["All IDs in this section are listed under earlier source sections or were already adaptations at baseline.", ""]
        for e in owned:
            lines.append(f"- [{'x' if e['status'].startswith('render_tested') else ' '}] **{e['id']} — {e['name']}** · `{e['implementation_track']}` · {e['status']}. Original required assets: {', '.join(e['required_assets_original']) or 'None specified'}. Sections: {' / '.join(e['source_sections'])}.")
        lines.append("")
    lines += ["## Acceptance / evidence", "", "See `native-text-batch1-qa.md` for executed tests, real 2-second HyperFrames renders and limitations. `ops/smoke_native_text.py` reproduces the local render proof without LLM, TTS, live storage or new installs. No migrations, deployment or merge.", ""]
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "inventory.json").write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n")
    (args.output / "checklist.md").write_text("\n".join(lines))
    print(json.dumps({"unique_entries": len(entries), "groups": len(inventory["groups"]), "status_counts": inventory["status_counts"], "track_counts": inventory["track_counts"]}))


if __name__ == "__main__":
    main()
