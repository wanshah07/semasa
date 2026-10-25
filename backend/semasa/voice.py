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
import time
from pathlib import Path
from typing import Any

from .log import get_logger

log = get_logger("semasa.voice")

VOICES = {
    "bm": {"male": "ms-MY-OsmanNeural", "female": "ms-MY-YasminNeural"},
    "en": {"male": "en-US-AndrewMultilingualNeural", "female": "en-US-AvaMultilingualNeural"},
}
# a narrated film is brisk (Wan, 25 Oct 2026: "for video with narrator make it faster rate"): English x1.15, Malay x1.25. The
# speed is applied AFTER the recording, with ffmpeg's pitch-keeping atempo: on GitHub's runner the service answered "No audio
# was received" for every request that carried a rate or a boundary setting (25 Oct 2026, three runs), while the plain call
# that the first voiced films used (24 Oct) still works.
TEMPO_EN = 1.15
TEMPO_BM = 1.25


def tempo_for(voice: str) -> float:
    return TEMPO_BM if voice.startswith("ms-MY-") else TEMPO_EN


def voice_for(language: str, choice: str) -> str:
    """The Edge voice name for a film's language (bm | en | both -> bm) and Wan's choice (male | female | an Edge name)."""
    lang = "en" if language == "en" else "bm"
    c = (choice or "male").strip()
    if c in ("male", "female"):
        return VOICES[lang][c]
    return c or VOICES[lang]["male"]


def spread(text: str, start: float, end: float) -> list[tuple[float, float, str]]:
    """Words of one spoken sentence timed across its real span [start, end], each in proportion to its length. Real word timing
    is used whenever the service gives it."""
    words = text.split()
    if not words or end <= start:
        return []
    weights = [len(w.strip(".,;:!?\"'()")) + 1 for w in words]
    total = float(sum(weights))
    out, t = [], start
    for w, wt in zip(words, weights, strict=True):
        d = (end - start) * wt / total
        out.append((round(t, 3), round(t + d, 3), w))
        t += d
    return out


async def _synth(text: str, voice: str, out: Path) -> list[tuple[float, float, str]]:
    """The plain call: no rate, no boundary setting. Word times from whatever boundary events the service sends."""
    import edge_tts
    words: list[tuple[float, float, str]] = []
    with out.open("wb") as f:
        async for chunk in edge_tts.Communicate(text, voice).stream():
            kind = chunk["type"]
            if kind == "audio":
                f.write(chunk["data"])
            elif kind in ("WordBoundary", "SentenceBoundary"):
                start = chunk["offset"] / 10_000_000
                end = start + chunk["duration"] / 10_000_000
                if kind == "WordBoundary":
                    words.append((round(start, 3), round(end, 3), str(chunk.get("text") or "")))
                else:
                    words.extend(spread(str(chunk.get("text") or ""), start, end))
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


def fallback(text: str, voice: str, out: Path, runner: Any, edge_error: Exception) -> dict[str, Any]:
    """Edge gave no audio three times (it did so on GitHub's runner on 25 Oct 2026, every request, after 30 s of silence):
    narrate with Google's text-to-speech, no key needed, and say so. Word times are not invented: `words` stays empty."""
    try:
        from gtts import gTTS
        gTTS(text, lang="ms" if voice.startswith("ms-MY-") else "en").save(str(out))
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"no voice: Edge said {str(edge_error)[:120]}; Google said {str(exc)[:120]}") from exc
    factor = tempo_for(voice)
    fast = out.with_name(out.stem + "-fast.mp3")
    done = runner(["ffmpeg", "-v", "error", "-y", "-i", str(out), "-filter:a", f"atempo={factor:g}", "-c:a", "libmp3lame",
                   str(fast)], capture_output=True, text=True, timeout=120)
    if done.returncode == 0 and fast.exists() and fast.stat().st_size >= 1000:
        fast.replace(out)
    if not out.exists() or out.stat().st_size < 1000:
        raise RuntimeError("no audio from Google either")
    return {"duration": duration_of(out, runner), "words": [], "provider": "google"}


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
        converted = runner(["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-af", "atempo=1.0", "-c:a", "libmp3lame", str(out)],
                           capture_output=True, text=True, timeout=60)
        if converted.returncode != 0:
            raise RuntimeError("KittenTTS MP3 conversion failed")
        words = []  # The adapter supplies no alignment: never fabricate word timestamps.
    else:
        words = []
        for attempt in range(3):                      # the service is sometimes empty-handed for a moment
            try:
                words = asyncio.run(_synth(text, voice, out))
                if out.exists() and out.stat().st_size >= 1000:
                    break
                raise RuntimeError("no audio")
            except Exception as exc:  # noqa: BLE001
                log.warning("edge-tts %s attempt %d gave nothing: %s", voice, attempt + 1, str(exc)[:160])
                if attempt == 2:
                    return fallback(text, voice, out, runner, exc)
                time.sleep(2 * (attempt + 1))
        factor = tempo_for(voice)
        fast = out.with_name(out.stem + "-fast.mp3")
        done = runner(["ffmpeg", "-v", "error", "-y", "-i", str(out), "-filter:a", f"atempo={factor:g}", "-c:a", "libmp3lame",
                       str(fast)], capture_output=True, text=True, timeout=120)
        if done.returncode == 0 and fast.exists() and fast.stat().st_size >= 1000:
            fast.replace(out)
            words = [(round(a / factor, 3), round(b / factor, 3), w) for a, b, w in words]
        else:
            log.warning("tempo x%g not applied to %s: %s", factor, voice, (done.stderr or "")[-160:])
    if not out.exists() or out.stat().st_size < 1000:
        raise RuntimeError(f"no audio from {voice}")
    dur = duration_of(out, runner) or (words[-1][1] + 0.3 if words else 0.0)
    return {"duration": dur, "words": [list(w) for w in words]}
