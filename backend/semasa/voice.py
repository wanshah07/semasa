"""A voice for the motion videos (Wan, 24 Oct 2026: "add mascot looks like talking, and make sure got voice or audio").

Microsoft Edge's neural voices through `edge-tts`: free, no key, Malay (ms-MY Osman / Yasmin) and English (Andrew / Ava),
and every word comes back with its time, which is what makes the mascot's mouth move on the words. It runs on the GitHub
runner (speech.platform.bing.com); from a proxied session it may fail on TLS, so the worker treats a voice that cannot be
made as "no voice" and still makes the film.

VoiceStudio KittenTTS is an optional English-only adapter to an already-installed local worker. It requires
VOICESTUDIO_PYTHON and VOICESTUDIO_ROOT, cached model weights and VoiceStudio's services.tts_backend API.
No installation, model downloads or cloning occurs here. Missing prerequisites fail explicitly, never silently re-voice.
"""

from __future__ import annotations

import asyncio
import json
import os
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
        # boundary="WordBoundary" is explicit: edge-tts >= 7.2 defaults to "SentenceBoundary", which returns no per-word
        # timing at all, so the mascot's mouth never opened on a real film (found 25 Oct 2026; PR #76 found it first)
        comm = edge_tts.Communicate(text, voice, rate="+15%" if voice.startswith("ms-MY-") else RATE, boundary="WordBoundary")
        async for chunk in comm.stream():
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


def kitten_ready() -> bool:
    """True when this machine has a VoiceStudio worker for the English Kitten voice (both variables set). GitHub's hosted
    runner has none, so a film asking for Kitten there narrates with an Edge voice and says so (Wan, 25 Oct 2026)."""
    return bool(os.environ.get("VOICESTUDIO_PYTHON") and os.environ.get("VOICESTUDIO_ROOT"))


def speak(text: str, voice: str, out: Path, runner: Any = subprocess.run) -> dict[str, Any]:
    """Write `text` as MP3 to `out`. {"duration": seconds, "words": [[start, end, word], ...]}; raises when nothing came back."""
    out.parent.mkdir(parents=True, exist_ok=True)
    if voice == "kitten":
        python = os.environ.get("VOICESTUDIO_PYTHON")
        root = os.environ.get("VOICESTUDIO_ROOT")
        if not python or not root:
            raise RuntimeError("Configure VOICESTUDIO_PYTHON and VOICESTUDIO_ROOT on a preinstalled VoiceStudio worker")
        wav = out.with_suffix(".wav")
        p = runner([python, str(Path(__file__).with_name("kitten_voice.py"))],
                   input=json.dumps({"text": text, "output": str(wav.resolve())}),
                   capture_output=True, text=True, timeout=300, env=dict(os.environ))
        if p.returncode != 0 or not wav.exists():
            raise RuntimeError("VoiceStudio KittenTTS failed: " + (p.stderr or "no WAV")[-300:])
        converted = runner(["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-af", "atempo=0.936", "-c:a", "libmp3lame", str(out)],
                           capture_output=True, text=True, timeout=60)
        if converted.returncode != 0:
            raise RuntimeError("KittenTTS MP3 conversion failed")
        words = []  # The adapter supplies no alignment: never fabricate word timestamps.
    else:
        words = asyncio.run(_synth(text, voice, out))
    if not out.exists() or out.stat().st_size < 1000:
        raise RuntimeError(f"no audio from {voice}")
    dur = duration_of(out, runner) or (words[-1][1] + 0.3 if words else 0.0)
    return {"duration": dur, "words": [list(w) for w in words]}
