"""Executed ONLY by a configured, already-installed VoiceStudio Python. No installer/downloads."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> None:
    root = Path(os.environ["VOICESTUDIO_ROOT"])
    sys.path[:0] = [str(root / "backend"), str(root)]
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("OMNIVOICE_TTS_BACKEND", "kittentts")
    os.environ.setdefault("OMNIVOICE_KITTENTTS_MODEL", "KittenML/kitten-tts-mini-0.8")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    import soundfile as sf
    import torch
    from services.tts_backend import KittenTTSBackend
    torch.set_num_threads(1)
    request = json.loads(sys.stdin.read())
    backend = KittenTTSBackend()
    ready, reason = backend.is_available()
    if not ready:
        raise RuntimeError(reason)
    audio = backend.generate(request["text"], language="en", voice="expr-voice-2-f", speed=1.0)
    sf.write(request["output"], audio.squeeze(0).cpu().numpy(), backend.sample_rate, subtype="PCM_16")


if __name__ == "__main__":
    main()
