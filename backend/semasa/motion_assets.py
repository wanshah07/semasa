"""Prepared local files and conservative native adapters for the complete effect library.

Never execute raw source instructions. Unsupported editing remains an explicit adaptation.
"""

from __future__ import annotations

import hashlib
import html
import io
import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

from .motion_styles import EFFECT_LIBRARY, RULES

CATALOG = {e["id"]: e for e in EFFECT_LIBRARY["effects"]}
POLICY = json.loads((RULES / "effect-adapters.json").read_text())
BUCKET = "semasa-motion-assets"
MAX_BYTES = 20 * 1024 * 1024
TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "application/pdf": ".pdf",
    "text/plain": ".txt",
}


def validate_ref(ref: dict, owner: str) -> None:
    path = PurePosixPath(str(ref.get("path") or ""))
    if not owner or path.is_absolute() or len(path.parts) != 2 or path.parts[0] != owner or ".." in path.parts:
        raise ValueError("Asset must be in the creator-owned private folder")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", path.name) or path.name.startswith("."):
        raise ValueError("Unsafe asset filename")
    if ref.get("mime") not in TYPES or path.suffix.lower() != TYPES[ref["mime"]]:
        raise ValueError("Unsupported MIME or file extension")
    if not 0 < int(ref.get("size") or 0) <= MAX_BYTES:
        raise ValueError("Asset must be between 1 byte and 20 MB")
    if ref.get("rights") not in {"licensed", "self-owned"}:
        raise ValueError("Confirm asset rights before public export")


def is_auto(row: dict) -> bool:
    """Auto is the default (Wan, 25 Oct 2026: every video gets the styles that suit it, motion_auto.py): a row asks for the
    hand-picked list only by saying effect_mode "manual", or by listing effects with no mode at all (rows from before it)."""
    options = row.get("options") or {}
    mode = options.get("effect_mode")
    return mode == "auto" or (mode is None and not options.get("effects"))


def prepare(row: dict, folder: Path, *, download: Any = None) -> dict:
    options = row.get("options") or {}
    mode = options.get("asset_mode", "auto")
    if mode not in {"auto", "manual", "mixed"}:
        raise ValueError("Unknown asset mode")
    refs = options.get("assets") or []
    # Auto picks no placeholder panel here: motion_auto.choose() assigns styles to the scenes once the film is planned
    ids = [] if is_auto(row) else list(dict.fromkeys(options.get("effects", [])))
    if any(code not in CATALOG for code in ids):
        raise ValueError("Unknown effect ID")
    if len(refs) > 8:
        raise ValueError("At most eight manual assets")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "assets").mkdir(exist_ok=True)
    report = {"mode": mode, "effects": [], "assets": [], "notes": []}
    # Private storage downloads only, not arbitrary URLs supplied by the browser.
    for i, ref in enumerate(refs):
        validate_ref(ref, str(row.get("created_by") or ""))
        if download is None:
            raise ValueError("Private asset download unavailable")
        data = download(ref["path"])
        if len(data) != int(ref["size"]) or len(data) > MAX_BYTES:
            raise ValueError("Downloaded asset size differs from manifest")
        rel = f"assets/manual-{i}{TYPES[ref['mime']]}"
        image = ref["mime"].startswith("image/")
        if image:
            from PIL import Image

            with Image.open(io.BytesIO(data)) as im:
                if im.format != {"image/png": "PNG", "image/jpeg": "JPEG", "image/webp": "WEBP"}[ref["mime"]]:
                    raise ValueError("Image bytes do not match MIME")
                if im.width * im.height > 25_000_000:
                    raise ValueError("Image exceeds pixel limit")
                im.load()
                im.thumbnail((1600, 1600))
                output = io.BytesIO()
                im.convert("RGB").save(output, format="PNG")
                data = output.getvalue()
                rel = f"assets/manual-{i}.png"
        else:
            # Retained for future editing; never pretend these are rendered footage/audio/proof.
            signatures = {"video/mp4": b"ftyp", "audio/mpeg": b"ID3", "audio/wav": b"RIFF", "application/pdf": b"%PDF-"}
            if ref["mime"] == "text/plain":
                data.decode("utf-8")
            elif signatures[ref["mime"]] not in data[:16]:
                raise ValueError("Asset bytes do not match MIME")
        (folder / rel).write_bytes(data)
        report["assets"].append(
            {
                "path": rel,
                "origin": "manual",
                "image": image,
                "role": ref.get("role", "reference"),
                "source": ref.get("source", ""),
                "attribution": ref.get("attribution", ""),
                "rights": ref["rights"],
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )
        if not image:
            report["notes"].append(f"{rel}: stored only; source-video/audio/document editing is not supported")
    # A neutral self-authored illustration is safe for concepts, never an evidence substitute.
    concept = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="720" height="360" viewBox="0 0 720 360">'
        '<path d="M150 180H570" stroke="#287b65" stroke-width="5"/>'
        '<g fill="#e5f6ed" stroke="#287b65" stroke-width="5"><circle cx="150" cy="180" r="60"/>'
        '<rect x="300" y="120" width="120" height="120" rx="18"/><circle cx="570" cy="180" r="60"/></g></svg>'
    )
    rel = "assets/concept.svg"
    (folder / rel).write_text(concept)
    report["assets"].append(
        {
            "path": rel,
            "origin": "bot",
            "image": True,
            "role": "concept",
            "source": "Original neutral vector; no evidence, numbers or product depiction",
            "attribution": "Semasa",
            "rights": "self-owned",
            "sha256": hashlib.sha256(concept.encode()).hexdigest(),
        }
    )
    screenshots = [
        a for a in report["assets"] if a["origin"] == "manual" and a["image"] and a["role"] == "screenshot" and a["source"]
    ]
    for code in ids:
        policy = POLICY[code]
        readiness = policy["readiness"]
        reason = policy["reason"]
        asset = rel
        if readiness == "manualasset":
            if screenshots:
                asset = screenshots[0]["path"]
            else:
                readiness = "fallback"
                reason = ("Authentic screenshot with source metadata absent; concept diagram, not evidence. "
                          "Automatic URL capture integration unavailable.")
        report["effects"].append(
            {
                "id": code,
                "readiness": readiness,
                "reason": reason,
                "adapter": policy["adapter"] if readiness != "fallback" else "concept",
                "asset": asset,
            }
        )
    (folder / "asset-plan.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def inject(document: str, report: dict, scenes: list[dict], total: float, *, design: str = "bright-editorial") -> str:
    """Worker-owned deterministic layer: consumes files, never asks the writer to simulate them."""
    if not report["effects"]:
        return document
    from . import native_text

    document = native_text.inject(document, report, scenes, total)
    selected = [p for p in report["effects"] if p["id"] not in native_text.NATIVE_IDS]
    if not selected:
        return document
    first = scenes[0]
    end = min(float(first["duration"]), total)
    # Legacy asset adaptations retain their single prepared panel.
    primary = next((p for p in selected if p["readiness"] == "manualasset"), selected[0])
    source = next(a for a in report["assets"] if a["path"] == primary["asset"])
    fallback = [p["id"] for p in selected if p["readiness"] == "fallback"]
    label = (
        ("Adapted " + ", ".join(fallback) + ": concept only, not evidence")
        if fallback
        else (
            ("Source: " + source["source"] + " · " + source["attribution"])
            if source["origin"] == "manual"
            else "Concept illustration · not evidence"
        )
    )
    label = html.escape(label)
    panel = (
        f'<div class="clip" id="effect-panel" data-start="0" data-duration="{end:g}" '
        'style="position:absolute;left:12%;top:48%;width:70%;height:22%;z-index:20;pointer-events:none;">'
        f'<img id="effect-art" src="{primary["asset"]}" alt="" style="width:100%;height:75%;object-fit:contain;">'
        f'<div style="font:28px system-ui;color:#143e35;text-align:center;">{label}</div></div>'
    )
    m = re.search(r"<div\b[^>]*\bid=[\"\']root[\"\'][^>]*>", document)
    if not m:
        raise ValueError("No root for prepared effect assets")
    document = document[: m.end()] + panel + document[m.end() :]
    commands = []
    for p in selected:
        adapter = p["adapter"]
        if adapter == "headline":
            commands.append('tl.fromTo("#effect-art",{scale:1.15},{scale:1,duration:.45,ease:"back.out(1.3)"},0);')
        elif adapter == "morph":
            commands.append(
                'tl.fromTo("#effect-art",{borderRadius:"50%",rotation:-8},{borderRadius:"0%",rotation:0,duration:1.2},0);'
            )
        elif adapter == "push":
            commands.append(f'tl.fromTo("#effect-art",{{scale:1}},{{scale:1.06,duration:{end:g},ease:"none"}},0);')
        elif adapter == "screenshot":
            commands.append('tl.fromTo("#effect-art",{scale:.92,y:20},{scale:1,y:0,duration:.5,ease:"power2.out"},0);')
        else:
            commands.append(f'tl.fromTo("#effect-art",{{x:-6}},{{x:6,duration:{end:g},ease:"none"}},0);')
    # Access the writer's registered timeline rather than its lexical variable name.
    script = '<script>{const tl=window.__timelines["main"];' + "".join(dict.fromkeys(commands)) + "tl.seek(0);}</script>"
    return document.replace("</body>", script + "</body>")
