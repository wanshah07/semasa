"""Assemble the drama: two talking-head lipsync clips -> shot-reverse-shot scene with burned subtitles.

Usage: python assemble_drama.py <siti.mp4> <aiman.mp4> <voice-manifest.json>

The manifest gives each line's speaker + exact duration. We cut the character clips at those
durations and alternate shots: whoever speaks is on screen, with their subtitle synced.
"""
import json
import subprocess
import sys
from pathlib import Path

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"

W, H = 1080, 1920


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("FAIL:", " ".join(cmd)[:200], "\n", r.stderr[-1500:])
        raise SystemExit(1)
    return r


def dur(p):
    r = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    return float(r.stdout.strip())


def main():
    siti, aiman, manifest_path = sys.argv[1], sys.argv[2], sys.argv[3]
    manifest = json.loads(Path(manifest_path).read_text("utf-8"))

    # build timeline: each line -> its speaker, start, end
    GAP = 0.35
    timeline = []
    t = 0.0
    for m in manifest:
        d = m["duration"]
        timeline.append((m["n"], m["who"], m["text"], t, t + d))
        t += d + GAP
    total = t - GAP

    # cut each character's full talking clip to the right segment, scale/crop to 9:16
    # character clip durations: Siti-audio ~ lines 1+3, Aiman-audio ~ lines 2+4
    # each char clip has their lines concatenated with 0.4s gaps (see gen_voice)
    # map: within each char clip, line k starts at (sum of prior line durations + k*0.4)
    char_clips = {"Siti": siti, "Aiman": aiman}

    def char_line_offsets(char):
        lines = [m for m in manifest if m["who"] == char]
        offs = []
        acc = 0.0
        for m in lines:
            offs.append((m["n"], acc))
            acc += m["duration"] + 0.4
        return offs

    seg_files = []
    for (n, who, text, start, end) in timeline:
        d = end - start
        src = char_clips[who]
        offs = dict(char_line_offsets(who))
        inner = offs[n]  # offset of this line inside its char clip
        seg = f"seg{n}.mp4"
        # cut + scale to 9:16 with slight zoom (crop faces to fill vertical)
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
              f"crop={W}:{H}")
        run([FFMPEG, "-y", "-ss", f"{inner:.3f}", "-t", f"{d:.3f}", "-i", src,
             "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-an", seg])
        seg_files.append((n, seg, start, end, who, text, d))
        print(f"seg{n} {who}: {d:.3f}s (from {inner:.3f} in {who} clip)")

    # concat segments in timeline order
    with open("segs.txt", "w") as f:
        for n, seg, *_ in seg_files:
            f.write(f"file '{seg}'\n")
    concat = "concat.mp4"
    run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", "segs.txt", "-c", "copy", concat])

    # voiceover: per-line delayed mix from the ORIGINAL per-line wavs is simpler;
    # but we only have per-char audio + manifest. Rebuild per-line from char audio offsets.
    # Actually simplest: use the char audio offsets to cut per-line wav, then delay.
    inputs = ["-f", "lavfi", "-t", f"{total:.3f}", "-i", "anullsrc=r=44100:cl=stereo"]
    per_line_wavs = []
    for (n, who, text, start, end) in timeline:
        offs = dict(char_line_offsets(who))
        inner = offs[n]
        d = end - start
        wav = f"line{n}.wav"
        run([FFMPEG, "-y", "-ss", f"{inner:.3f}", "-t", f"{d:.3f}",
             "-i", char_clips[who], "-vn", "-ar", "44100", "-ac", "2", wav])
        inputs += ["-i", wav]
        per_line_wavs.append((n, wav, start))

    fparts = []
    for i, (n, wav, start) in enumerate(per_line_wavs, start=1):
        dm = int(round(start * 1000))
        fparts.append(f"[{i}:a]adelay={dm}|{dm}[a{i}]")
    mixin = "".join(f"[a{i}]" for i in range(1, len(per_line_wavs) + 1))
    fc = ";".join(fparts) + f";[0:a]{mixin}amix=inputs={len(per_line_wavs)+1}:normalize=0[outa]"
    run([FFMPEG, "-y", *inputs, "-filter_complex", fc, "-map", "[outa]",
         "-ac", "2", "-ar", "44100", "voiceover.wav"])

    # SRT
    def ts(x):
        x = max(0.0, min(x, total))
        ms = int(round(x * 1000))
        h, rem = divmod(ms, 3600_000); m, rem = divmod(rem, 60_000); s, ms = divmod(rem, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    with open("subs.srt", "w", encoding="utf-8") as f:
        for i, (n, seg, start, end, who, text, d) in enumerate(seg_files, 1):
            f.write(f"{i}\n{ts(start)} --> {ts(end)}\n{who}: {text}\n\n")

    # mux
    vf = ("subtitles=subs.srt:force_style="
          "'FontName=DejaVu Sans,FontSize=15,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,"
          "BorderStyle=1,Outline=2,BackColour=&H80000000,Alignment=2,MarginV=140,WrapStyle=0'")
    run([FFMPEG, "-y", "-i", concat, "-i", "voiceover.wav",
         "-map", "0:v", "-map", "1:a", "-vf", vf,
         "-c:v", "libx264", "-crf", "20", "-c:a", "aac", "-shortest", "drama-episode.mp4"])

    print("FINAL drama-episode.mp4:", round(dur("drama-episode.mp4"), 3), "s")
    return 0


if __name__ == "__main__":
    main()
