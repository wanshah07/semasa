"""Nexabot cat film — a short photorealistic film in Bahasa Malaysia, made with Nexabot's image, video and voice generators.

Wan, 18 Nov 2026: "cat with his friends short film in malay". A FILE for Wan to watch, nothing more: it is not imported into
Semasa, makes no post and touches no gate. The four generators it drives are the ones already proven in this repo, reused as they
are (nothing of the comic film's scripts is edited):

  1. image  - nexabot_charsheet draws ONE sheet of the three cats together, so they stay the same cats in every scene;
  2. video  - nexabot_film makes one Start Frame clip per scene from that sheet (description only, no dialogue in the prompt:
              the model garbles words, so the words are voice + subtitle);
  3. voice  - nexabot_voice_line makes one narration line per scene, each on a fresh page;
  4. mix    - ffmpeg (the static imageio-ffmpeg build) lays each line over its clip, holds the last frame when a line runs longer
              than the clip, burns the line as a subtitle and joins the four scenes.

Run on the GitHub runner (NEXABOT_STORAGE_STATE_B64), from backend:

    python -m semasa.nexabot_cat_film OUTDIR [--category cats] [--topic "..."] [--voice Sulafat] [--dry]

The film is one short-film category (semasa.short_films, Wan 22 Nov 2026: categories are data, not code). `cats` (the default)
and every built-in category film their hand-written script word for word; one of Wan's own is written by the writer from its
cast, setting and style plus --topic, and that script is kept beside the film as script.json.
--dry prints the plan and spends nothing on Nexabot (a written category's script is still written, so it can be read
first). A failed stage stops the run and keeps whatever was made, with report.json beside it.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from . import short_films

# The film comes from a short-film category (rules/short_films.json, plus Wan's own in the settings row `short_films`). These are
# the default category's, exactly the words this film always used; `use` swaps in another category's before `run`.
CATEGORY = short_films.category_of(short_films.library(), "cats")
_DEFAULT = short_films.film_script(CATEGORY)
CHAR_SHEET_PROMPT: str = _DEFAULT["sheet_prompt"]
# one description per scene (no dialogue in it) and the narration line that goes over it
SCENES: list[str] = _DEFAULT["scenes"]
NARRATION: list[str] = _DEFAULT["narration"]
FILM_NAME = CATEGORY.get("file") or CATEGORY["id"]
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
LEAD_S = 0.6      # the voice starts this long after a scene starts
TAIL_S = 0.8      # and the scene holds this long after the voice ends


def _ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def duration(path: Path) -> float:
    """Seconds of a media file, read from ffmpeg's own banner (0.0 when it cannot be read)."""
    import re
    p = subprocess.run([_ffmpeg(), "-hide_banner", "-i", str(path)], capture_output=True, text=True)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", p.stderr)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:").replace(",", "\\,").replace("%", "\\%")


def _wrap(text: str, width: int = 38) -> str:
    """Hard line breaks for the subtitle (drawtext does not wrap); the break is a real newline inside the text."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return "\n".join(lines)


def scene_segment(clip: Path, voice: Path, line: str, out: Path, size: tuple[int, int] = (1280, 720)) -> Path:
    """One scene: the clip with its voice laid over it and the line burned in. The scene lasts as long as the longer of the
    clip and (lead + voice + tail); a clip that is shorter holds its last frame rather than cutting the voice."""
    cd, vd = duration(clip), duration(voice)
    total = max(cd, LEAD_S + vd + TAIL_S)
    w, h = size
    text = _escape(_wrap(line))
    vf = (f"tpad=stop_mode=clone:stop_duration={max(0.0, total - cd):.2f},scale={w}:{h}:force_original_aspect_ratio=decrease,"
          f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,fps=24,"
          f"drawtext=fontfile={FONT}:text='{text}':fontsize=40:fontcolor=white:borderw=3:bordercolor=black:"
          f"box=1:boxcolor=black@0.55:boxborderw=16:line_spacing=8:x=(w-text_w)/2:y=h-text_h-70:"
          f"enable='between(t,{LEAD_S:.2f},{LEAD_S + vd + 0.4:.2f})'")
    af = f"adelay={int(LEAD_S * 1000)}|{int(LEAD_S * 1000)},apad=whole_dur={total:.2f}"
    subprocess.run([_ffmpeg(), "-y", "-i", str(clip), "-i", str(voice), "-filter_complex",
                    f"[0:v]{vf}[v];[1:a]aresample=44100,{af}[a]", "-map", "[v]", "-map", "[a]", "-t", f"{total:.2f}",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
                    str(out)], check=True, capture_output=True)
    return out


def join(segments: list[Path], out: Path) -> Path:
    """The scenes end to end (they share one encoding, so the join copies)."""
    lst = out.parent / "segments.txt"
    lst.write_text("".join(f"file '{s}'\n" for s in segments), "utf-8")
    subprocess.run([_ffmpeg(), "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)],
                   check=True, capture_output=True)
    return out


def plan() -> dict:
    return {"scenes": len(SCENES), "narration": NARRATION, "sheet_prompt_chars": len(CHAR_SHEET_PROMPT)}


def run(outdir: Path, voice: str, dry: bool) -> int:
    report: dict = {"started": datetime.now(UTC).isoformat(), "voice": voice, "dry": dry, "plan": plan()}

    def save() -> None:
        (outdir / "report.json").write_text(json.dumps(report, indent=2, default=str), "utf-8")

    if dry:
        save()
        print(json.dumps(report["plan"], indent=2, ensure_ascii=False))
        return 0

    from . import nexabot_charsheet as cs
    from . import nexabot_film as film
    from . import nexabot_voice_line as vl

    # 1 · image: one sheet with the three cats
    sheet_dir = outdir / "sheet"
    sheet_dir.mkdir(exist_ok=True)
    cs.CHAR_SHEET_PROMPT = CHAR_SHEET_PROMPT
    if cs.run(sheet_dir) != 0 or not (sheet_dir / "charsheet.png").exists():
        report["failed"] = "image: the character sheet was not made"
        save()
        print(report["failed"])
        return 1
    report["sheet"] = str(sheet_dir / "charsheet.png")
    save()

    # 2 · video: one Start Frame clip per scene from that sheet
    clip_dir = outdir / "clips"
    clip_dir.mkdir(exist_ok=True)
    film.SHEET = sheet_dir / "charsheet.png"
    film.SCENES = SCENES
    code = film.run(clip_dir)
    clips = [clip_dir / f"clip{i + 1}.mp4" for i in range(len(SCENES))]
    report["clips"] = [str(c) for c in clips if c.exists()]
    save()
    if code != 0 or len(report["clips"]) != len(SCENES):
        report["failed"] = f"video: {len(report['clips'])} of {len(SCENES)} clips were made"
        print(report["failed"])
        return 1

    # 3 · voice: one narration line per scene, a fresh page each
    voices: list[Path] = []
    for i, line in enumerate(NARRATION):
        vdir = outdir / f"voice{i + 1}"
        vdir.mkdir(exist_ok=True)
        if vl.run(vdir, "Narator", voice, line, False) != 0 or not (vdir / "voice-Narator.wav").exists():
            report["failed"] = f"voice: line {i + 1} was not made"
            save()
            print(report["failed"])
            return 1
        voices.append(vdir / "voice-Narator.wav")
    report["voices"] = [str(v) for v in voices]
    save()

    # 4 · mix
    seg_dir = outdir / "segments"
    seg_dir.mkdir(exist_ok=True)
    segments = [scene_segment(c, v, ln, seg_dir / f"scene{i + 1}.mp4")
                for i, (c, v, ln) in enumerate(zip(clips, voices, NARRATION, strict=True))]
    final = join(segments, outdir / f"{FILM_NAME}.mp4")
    report["film"] = str(final)
    report["film_seconds"] = round(duration(final), 1)
    save()
    print(json.dumps({"ok": True, "film": str(final), "seconds": report["film_seconds"]}, indent=2))
    return 0


def own_library() -> dict:
    """The categories with Wan's own merged in, read from the settings row `short_films` (service role, on the runner)."""
    from . import db, ideas
    from .config import SupabaseSettings
    store = db.client(SupabaseSettings.load())
    return short_films.library(ideas.load_settings(store).get("short_films"))


def writer():
    """The writer the worker uses (the AI team's chain), for a category that has no hand-written scenes."""
    from . import ai_config, db
    from .config import SupabaseSettings
    from .llm import LLM
    return LLM(ai_config.llm_for(db.client(SupabaseSettings.load())))


def use(category_id: str, topic: str = "", lib: dict | None = None, llm=None) -> dict:
    """Point the film at one category: its character sheet, scenes and narration replace the defaults before `run`. A built-in
    category needs nothing but the file; one of Wan's own is read from the settings row and written by the writer now.
    Raises short_films.FilmError with the reason."""
    global CATEGORY, CHAR_SHEET_PROMPT, SCENES, NARRATION, FILM_NAME
    if lib is None:
        try:
            lib = short_films.library() if category_id in short_films.built_in_ids() else own_library()
        except Exception as exc:  # noqa: BLE001
            raise short_films.FilmError(f"your categories could not be read (settings row short_films): {exc}") from exc
    cat = short_films.category_of(lib, category_id)
    if not cat:
        raise short_films.FilmError(f"there is no short-film category {category_id!r}: "
                                    + ", ".join(c["id"] for c in lib["categories"]))
    if cat["voice"]["mode"] != "narrator":
        raise short_films.FilmError(f"{category_id!r} speaks its dialogue inside the video: it is made by {cat['workflow']}")
    if not cat.get("script") and llm is None:
        try:
            llm = writer()
        except Exception as exc:  # noqa: BLE001
            raise short_films.FilmError(f"the writer could not be set up: {exc}") from exc
    script = short_films.film_script(cat, llm=llm, topic=topic)
    CATEGORY, CHAR_SHEET_PROMPT, SCENES, NARRATION = cat, script["sheet_prompt"], script["scenes"], script["narration"]
    FILM_NAME = cat.get("file") or cat["id"]
    return script


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--category", default="cats", help="the short-film category id (rules/short_films.json or Wan's own)")
    ap.add_argument("--topic", default="", help="the day's topic, for a category the writer writes")
    ap.add_argument("--voice", default="", help="the Voice Generator voice for the narrator (default: the category's)")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args(sys.argv[1:])
    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    try:
        script = use(a.category.strip() or "cats", a.topic)
    except short_films.FilmError as exc:
        (outdir / "report.json").write_text(json.dumps({"category": a.category, "failed": str(exc)}, indent=2), "utf-8")
        print(f"short film: {exc}")
        return 2
    print(json.dumps({"category": CATEGORY["id"], "written": script["written"], "title": script["title"]}, ensure_ascii=False))
    if script["written"]:
        (outdir / "script.json").write_text(json.dumps(script, indent=2, ensure_ascii=False), "utf-8")
    return run(outdir, a.voice or CATEGORY["voice"]["name"] or "Sulafat", a.dry)


if __name__ == "__main__":
    sys.exit(main())
