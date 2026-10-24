"""A voice for the motion videos (Wan, 24 Oct 2026: "add mascot looks like talking, and make sure got voice or audio").

Microsoft Edge's neural voices through `edge-tts`: free, no key, Malay (ms-MY Osman / Yasmin) and English (Andrew / Ava),
and every word comes back with its time, which is what makes the mascot's mouth move on the words. It runs on the GitHub
runner (speech.platform.bing.com); from a proxied session it may fail on TLS, so the worker treats a voice that cannot be
made as "no voice" and still makes the film.

Wan's own VoiceStudio link (debpalash/VoiceStudio) is a desktop app with a local Python backend (OmniVoice, ~5 GB of
PyTorch on CPU, AGPL): voice cloning and dubbing on his own machine. It is not something a 30-minute runner job can
install each hour, so it is not the route here; a cloned voice from it can be used later as a reference file.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any

from .log import get_logger

log = get_logger("semasa.voice")

VOICES = {
    "bm": {"male": "ms-MY-OsmanNeural", "female": "ms-MY-YasminNeural"},
    "en": {"male": "en-US-AndrewMultilingualNeural", "female": "en-US-AvaMultilingualNeural"},
}
RATE = "+0%"


def voice_for(language: str, choice: str) -> str:
    """The Edge voice name for a film's language (bm | en | both -> bm) and Wan's choice (male | female | an Edge name)."""
    lang = "en" if language == "en" else "bm"
    c = (choice or "male").strip()
    if c in ("male", "female"):
        return VOICES[lang][c]
    return c or VOICES[lang]["male"]


async def _synth(text: str, voice: str, out: Path) -> list[tuple[float, float, str]]:
    import edge_tts
    words: list[tuple[float, float, str]] = []
    with out.open("wb") as f:
        # edge-tts >=7.2 defaults Communicate(boundary=...) to "SentenceBoundary"; without "WordBoundary" explicitly, no
        # per-word timing ever comes back and the mascot's mouth cannot move on the words (Wan, 25 Oct 2026: found while
        # making the mascot actually talk while it walks)
        async for chunk in edge_tts.Communicate(text, voice, rate=RATE, boundary="WordBoundary").stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 10_000_000
                words.append((round(start, 3), round(start + chunk["duration"] / 10_000_000, 3), str(chunk.get("text") or "")))
    return words


def duration_of(path: Path, runner: Any = subprocess.run) -> float:
    try:
        p = runner(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
                   capture_output=True, text=True, timeout=60)
        return round(float((json.loads(p.stdout or "{}").get("format") or {}).get("duration") or 0), 3)
    except Exception:  # noqa: BLE001
        return 0.0


def speak(text: str, voice: str, out: Path, runner: Any = subprocess.run) -> dict[str, Any]:
    """Write `text` as MP3 to `out`. {"duration": seconds, "words": [[start, end, word], ...]}; raises when nothing came back."""
    out.parent.mkdir(parents=True, exist_ok=True)
    words = asyncio.run(_synth(text, voice, out))
    if not out.exists() or out.stat().st_size < 1000:
        raise RuntimeError(f"no audio from {voice}")
    dur = duration_of(out, runner) or (words[-1][1] + 0.3 if words else 0.0)
    return {"duration": dur, "words": [list(w) for w in words]}
