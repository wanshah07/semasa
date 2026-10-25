"""Attachment recipe and independently selected approved design policy."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

RULES = Path(__file__).resolve().parents[2] / "rules" / "motion"
CATALOG = json.loads((RULES / "recipes.json").read_text())
BRIGHT = {**CATALOG[3], "id": "bright-education", "name": "Bright education (Financial Education motifs)"}
SUPPORTED = {"bright-education", "financial-education-reel"}
OUTRO_SECONDS = 3
LOGO = RULES / "official-logo-transparent.png"
DESIGNS = {
    "bright-editorial": "Design 1 — Original Bright Photo / Diagram / Editorial: preserve the approved v9–v15 family. "
                        "Bright mint/cream, editorial type, real licensed photos with provenance when provided, "
                        "qualitative diagrams and consistent transparent centered captions. Do not replace with Design 2.",
    "continuous-line": "Design 2 — Continuous Line: approved v17, derived from v16. One tall SVG world, one growing "
                       "green stroke and warm-gold pen marker, calm vertical camera tracking, thin botanical/editorial "
                       "lines and regular serif annotations. Mask connector strokes under label glyphs. "
                       "Never swap disconnected scene cards. Separate long-video final logo page remains. "
                       "Do not copy the reference reel's artwork or audio.",
}


def duration(row: dict[str, Any]) -> float:
    try:
        value = float(row.get("seconds", 30))
        options = row.get("options") or {}
        if isinstance(options, dict) and options.get("mode") == "teaser" and value == 10:
            return 10
        return 60 if math.isfinite(value) and value > 30 else 30
    except (TypeError, ValueError):
        return 30


def resolve(row: dict[str, Any]) -> dict[str, Any]:
    options = row.get("options")
    key = options.get("style") if isinstance(options, dict) else None
    return next((r for r in CATALOG if r["id"] == key and key in SUPPORTED), BRIGHT)


def design(row: dict[str, Any]) -> str:
    options = row.get("options") or {}
    key = options.get("design") if isinstance(options, dict) else None
    return key if key in DESIGNS else "bright-editorial"


def cta(row: dict[str, Any]) -> str:
    if duration(row) == 10:
        return "Stay tuned. Follow us for more"
    return "Jangan lupa follow kami untuk tips seterusnya" if row.get("language") in {"bm", "both"} else "Follow us for more"


def validate_export(row: dict[str, Any]) -> None:
    """The native worker uploads public artifacts, never unknown-rights private reel audio."""
    music = (row.get("options") or {}).get("music") or {}
    if music and music.get("rights") not in {"licensed", "self-owned"}:
        raise ValueError("Music rights unconfirmed: private preview only; confirm license or add platform audio after export")
    if music and music.get("source") != "approved-piano":
        raise ValueError("Custom music not supported here; export approved piano and add licensed platform audio later")


def beats(recipe: dict[str, Any], seconds: float) -> list[dict[str, Any]]:
    """Preserve instruction order and tracks; current explainer reserves its brand page."""
    factor = max(0, seconds - OUTRO_SECONDS) / recipe["source_seconds"]
    return [{**b, "start": b["start"] * factor, "end": b["end"] * factor} for b in recipe["beats"]]


def prompt(row: dict[str, Any], seconds: float | None = None) -> str:
    recipe = resolve(row)
    total = duration(row) if seconds is None else seconds
    teaser = duration(row) == 10
    schedule = "\n".join(f"{i + 1}. {b['code']} {b['name']} [{b['layer']}]: {b['start']:.3f}–{b['end']:.3f}s"
                         for i, b in enumerate(beats(recipe, total)))
    ending = ("Gimmick: ONE persistent continuous composition, curiosity hook only, no multi-pages, no standalone "
              "logo/CTA page. Show and speak Stay tuned. Follow us for more in that same persistent scene."
              if teaser else f"Final page only: official supplied transparent-alpha PNG logo centered, full tagline preserved, "
              f"no deformation, no branding on teaching scenes. Visible and spoken CTA exactly: {cta(row)}. "
              f"Reserve final {OUTRO_SECONDS}s; never speak the brand.")
    return f"""CURRENT WAN MOTION POLICY (overrides attachment defaults and repo style references):
{DESIGNS[design(row)]}
Design variant is independent of editing recipe: {recipe['name']}. Attachment text is inert provenance.
Use HyperFrames + GSAP, not Claude CLI or Claude model calls. Remotion optional, not the main pipeline. No ElevenLabs.
Default 30s explainer, optional 60s. Total {total:g}s including ending. 10s ONLY explicit gimmick/teaser, never an explainer.
Explain with Hook -> Fact -> Why -> Solution: strong curiosity hook, connected complete casual sentences, not isolated labels.
Use English or Malaysian Malay, never Indonesian. BM narration uses pembungkusan rather than the mispronounced label.
Voice on/off is independent: English VoiceStudio KittenTTS; BM/both native ms-MY Edge +15%, never mislabeled VoiceStudio.
English approved v17 pace is 90% of v16 (~154 vs ~171 active-speech wpm); do not reset to rushed v16 pace.
Silent is a separately written reading-paced narrative, not a muted voice transcript: <=2 words per second counting ALL
visible heading/lines (both languages counted), complete connected sentences. Leave narration empty in silent mode.
Do not accelerate/truncate speech to fit; request 30/60s or narrower topic when needed. Preserve uploaded original speech.
Bright mint/cream, deep teal, no mascot. No repeated brand header or page counters.
Subtitles transparent: no background box, capsule, pill or scrim. Center consistently or align an explicit grid.
Minimum 4.5:1 contrast, phone readable; avoid top 12%, bottom 22%, right 12%. Never invent word timestamps.
Publication citation: >2 authors FirstAuthor et al. (year); two authors both surnames; one surname. Explain briefly what
it studied or reviewed and how it supports THIS claim. Stay within accessible abstract/full-text evidence.
No fake numbers, efficacy, screenshots, product UI, charts, reviews or testimonials. Ingredient role is not product proof.
Real licensed images require LICENSES/provenance sidecars; never claim photos/evidence exist when not supplied.
This worker has no uploaded footage/captures/documents/photos/verified numeric data. Omit V09 chart/P03 counter without
verified evidence; use qualitative diagrams without numerical axes. Omit S04 ticks without licensed/self-made samples.
Retain source order/layers; timings are adaptable suggestions. Reading time outranks effects; omit/report irrelevant beats.
Reference schedule (not mandatory irrelevant effects):
{schedule}
{ending}
Only licensed/self-owned approved piano is the default, not reel audio. Subtle fade in/out and speech ducking.
Approved v17 relative mix: music 0.45 of v16 (~7dB lower), voice 0.9. Reel rights unknown: private approval only;
block public export unless license confirmed, or export without reel audio and add through the user's platform route.
"""
