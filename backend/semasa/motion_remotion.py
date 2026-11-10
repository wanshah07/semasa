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


COMBINED = "combined"


def choice(row: dict[str, Any]) -> str:
    """"remotion", "combined" (HyperFrames draws the first half, Remotion the second: Wan, 10 Nov 2026, "make one motion
    film using Remotion and combine hyperframes"), or "" for HyperFrames alone."""
    options = row.get("options")
    name = str(options.get("renderer") or "").lower() if isinstance(options, dict) else ""
    return name if name in (NAME, COMBINED) else ""


def wanted(row: dict[str, Any]) -> bool:
    return choice(row) == NAME


def cut_point(scenes: list[dict[str, Any]]) -> float:
    """Where a combined film changes engine: the start of the scene after the middle one (scene 3 of 4), so each engine
    draws whole scenes. 0 when there are too few scenes to share."""
    body = [sc for sc in scenes if sc.get("id") != "brand-outro"]
    if len(body) < 2:
        return 0.0
    return float(body[len(body) // 2]["start"])


def combine(first: Path, second: Path, at: float, out: Path, runner: Any = subprocess.run) -> Path:
    """One film from two renders of the SAME timeline: `first` up to `at` seconds, `second` from there. Both are silent and
    the same size and rate, so the cut is exact and the worker's sound mix lies over it unchanged."""
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(first), "-i", str(second), "-filter_complex",
           f"[0:v]trim=end={at:g},setpts=PTS-STARTPTS,fps=30,format=yuv420p[a];"
           f"[1:v]trim=start={at:g},setpts=PTS-STARTPTS,fps=30,format=yuv420p[b];[a][b]concat=n=2:v=1:a=0[v]",
           "-map", "[v]", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-an", str(out)]
    p = runner(cmd, capture_output=True, text=True, timeout=600)
    if p.returncode != 0 or not out.exists():
        raise RuntimeError("the two renders could not be joined: " + ((p.stderr or p.stdout or "")[-400:]).strip())
    return out


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


def render(folder: Path, data: dict[str, Any], runner: Any = subprocess.run, timeout: int = 900,
           name: str = "motion.mp4") -> Path:
    """Render the film's props to renders/motion.mp4 (silent). Raises RuntimeError with Remotion's own last words."""
    if not ready():
        raise RuntimeError("Remotion is not installed on this worker (backend/remotion/node_modules is missing)")
    out = folder / "renders" / name
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
