"""Remotion as the second Motion renderer (Wan, 10 Nov 2026: "go ahead with Remotion").

HyperFrames stays the default. A film whose options say `renderer: "remotion"` is drawn by the Remotion project in
backend/remotion from the SAME scenes the worker already planned, timed and voiced: headings, lines, pictures, subtitle
chunks and the closing card arrive as props, and Remotion returns a silent MP4. The worker then mixes the recorded voice and
the music onto it exactly as it does for a HyperFrames render, so voice, captions, storyboard approval and the queue are
shared. What Remotion does NOT have yet: the 99 effect styles, the design templates and the asset panels (those are written
for HyperFrames' HTML), so a Remotion film is one clean look.

If the Remotion render fails, the caller falls back to HyperFrames and the film's report says so: a film is never lost to
the second renderer.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from . import motion_layout

PROJECT = Path(__file__).resolve().parents[1] / "remotion"
FPS = 30
NAME = "remotion"


def wanted(row: dict[str, Any]) -> bool:
    options = row.get("options")
    return isinstance(options, dict) and str(options.get("renderer") or "").lower() == NAME


def ready() -> bool:
    """The project and its packages are on this machine (motion.yml installs them)."""
    return (PROJECT / "node_modules" / "remotion").is_dir()


def props(scenes: list[dict[str, Any]], total: float, w: int, h: int, palette: dict[str, str],
          name: str = "", logo: str = "") -> dict[str, Any]:
    """What the Remotion composition draws: nothing here is new wording, only the worker's own scenes reshaped. `name` is
    the closing card's name: the brand on ws.regulab, Wan's byline on LinkedIn (which never carries the brand)."""
    out = []
    for sc in scenes:
        outro = sc.get("id") == "brand-outro"
        chunks = motion_layout.caption_chunks(sc) if sc.get("audio") and not outro else []
        # no kicker: the scene labels (HOOK, FAKTA...) are the writer's own notes, never drawn (Wan, 10 Nov 2026)
        out.append({"id": str(sc.get("id") or ""), "role": str(sc.get("role") or ""),
                    "heading": str(sc.get("heading") or ""), "lines": [str(x) for x in (sc.get("lines") or [])][:3],
                    "photo": str(sc.get("photo") or ""), "start": float(sc["start"]), "duration": float(sc["duration"]),
                    "captions": [[text, round(a, 2), round(b, 2)] for text, a, b in chunks]})
    last = next((sc for sc in scenes if sc.get("id") == "brand-outro"), None)
    return {"width": w, "height": h, "fps": FPS, "seconds": round(float(total), 2), "palette": palette, "scenes": out,
            "outro": {"name": name, "line": str(last.get("heading") or ""), "logo": logo,
                      "brand": name == "ws.regulab"} if last else None}


def render(folder: Path, data: dict[str, Any], runner: Any = subprocess.run, timeout: int = 900) -> Path:
    """Render the film's props to renders/motion.mp4 (silent). Raises RuntimeError with Remotion's own last words."""
    if not ready():
        raise RuntimeError("Remotion is not installed on this worker (backend/remotion/node_modules is missing)")
    out = folder / "renders" / "motion.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    file = folder / "remotion-props.json"
    file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    cmd = ["npx", "remotion", "render", "src/index.jsx", "Film", str(out), f"--props={file}", f"--public-dir={folder}",
           "--muted", "--log=error", "--overwrite"]
    browser = os.environ.get("REMOTION_BROWSER", "")
    if browser:
        cmd.append(f"--browser-executable={browser}")
    p = runner(cmd, cwd=str(PROJECT), capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0 or not out.exists():
        raise RuntimeError("Remotion render failed: " + ((p.stderr or p.stdout or "")[-600:]).strip())
    return out
