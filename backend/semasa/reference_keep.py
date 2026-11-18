"""Keep a reference video, its frames and its sound for one day, so a person (or a session) can look at what the style reader
only describes. Wan, 18 Nov 2026: "please help to do like this" with a TikTok link: the style reader (motion_reference) says how a
video looks, not what happens in it or what is said, and a TikTok link cannot be fetched from a session, only from a runner.

    python -m semasa.reference_keep OUTDIR URL

Writes OUTDIR/reference.mp4, OUTDIR/ref-1.jpg ... ref-8.jpg (even moments), OUTDIR/audio.wav (mono 16 kHz, for a speech reader)
and OUTDIR/info.txt. Read-only: nothing is written to the database and nothing is posted.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from . import motion_reference as ref
from . import video

FRAME_COUNT = 8


def keep(url: str, outdir: Path) -> dict:
    outdir.mkdir(parents=True, exist_ok=True)
    path = ref.fetch(url, outdir)
    seconds = float(video.probe_duration(path) or 0)
    shots = ref.frames(path, outdir, seconds or 30.0, n=FRAME_COUNT)
    wav = outdir / "audio.wav"
    cmd = [video.ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(path),
           "-vn", "-ac", "1", "-ar", "16000", str(wav)]
    subprocess.run(cmd, capture_output=True, timeout=300)
    has_audio = wav.exists() and wav.stat().st_size > 0
    info = {"video": path.name, "seconds": round(seconds, 1), "frames": len(shots), "audio": has_audio,
            "cuts": ref.cuts(path, seconds or 30.0)}
    (outdir / "info.txt").write_text("\n".join(f"{k}: {v}" for k, v in info.items()) + "\n", "utf-8")
    return info


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print("usage: python -m semasa.reference_keep OUTDIR URL")
        return 2
    info = keep(args[1], Path(args[0]))
    print(info)
    return 0 if info["frames"] else 1


if __name__ == "__main__":
    sys.exit(main())
