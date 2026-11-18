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

    python -m semasa.nexabot_cat_film OUTDIR [--voice Sulafat] [--dry]

--dry prints the plan and spends nothing. A failed stage stops the run and keeps whatever was made, with report.json beside it.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

CHAR_SHEET_PROMPT = (
    "Photorealistic wildlife-style photograph, three real cats sitting side by side on the wooden steps of a Malaysian "
    "kampung house, facing the camera, soft warm morning light, shallow depth of field, full body of each cat visible: "
    "on the left Comot, a ginger orange tabby with a white chest and green eyes; in the middle Putih, a fluffy pure-white "
    "long-haired cat with blue eyes; on the right Belang, a young black-and-white tuxedo kitten with yellow eyes. "
    "Highly detailed fur, natural proportions, three clearly different cats. "
    "No people, no text, no logo, no watermark, no cartoon, no illustration."
)

# one description per scene (no dialogue in it) and the narration line that goes over it
SCENES = [
    "Photorealistic video. Pagi di kampung Malaysia. Comot, kucing oren, menguap dan meregangkan badan di tangga kayu "
    "sebuah rumah kampung. Putih, kucing putih gebu, dan Belang, anak kucing hitam putih, berjalan menghampirinya "
    "dengan ekor tegak. Cahaya matahari pagi yang lembut. Kamera statik, pergerakan semula jadi.",
    "Photorealistic video. Comot, Putih dan Belang berjalan beriringan di batas sawah padi yang hijau pada waktu pagi, "
    "ekor tegak, sekali-sekala saling memandang. Kamera mengekori perlahan dari sisi.",
    "Photorealistic video. Di bawah sebatang pokok, Comot menjumpai seekor ikan di atas daun pisang. Dia menolak ikan itu "
    "ke tengah, dan Putih serta Belang mendekat. Ketiga-tiga kucing makan bersama dengan tenang. Kamera statik.",
    "Photorealistic video. Petang di kampung, cahaya matahari terbenam yang keemasan. Comot, Putih dan Belang tidur "
    "bersusun rapat di atas pangkin kayu, perut kenyang, mata terpejam. Kamera bergerak perlahan menghampiri mereka.",
]
NARRATION = [
    "Pagi di kampung. Comot, si kucing oren, baru bangun, dan dua sahabatnya sudah menunggu.",
    "Bersama Putih dan Belang, dia meronda di tepi sawah, seperti setiap pagi.",
    "Hari ini Comot menjumpai seekor ikan. Walaupun lapar, dia berkongsi dengan kawan-kawannya.",
    "Kerana bagi Comot, kawan yang baik lebih berharga daripada seekor ikan.",
]
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
ATTEMPTS = 3      # a video that Nexabot refuses is asked for again, up to this many times
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


def _jobs(page) -> list:
    try:
        return page.evaluate("""async () => {
            const r = await fetch('/api/v1/jobs?scope=recent&limit=30');
            const j = await r.json();
            return Array.isArray(j) ? j : (j.jobs || j.data || []);
        }""") or []
    except Exception:  # noqa: BLE001
        return []


def scene_clip(page, prompt: str, clip_dir: Path, report: dict, idx: int, seen: set[str], wait_s: int = 40 * 60) -> Path | None:
    """One Start Frame clip. The job it waits for is the first VIDEO (sfv) job that was not on the account before the click:
    the account is shared, and on 18 Nov a voice job started by another run was taken for scene 3's video and waited on for
    25 minutes. A video job that fails ends the wait at once, with the reason in the report.
    The finished job's id joins `seen`."""
    import time

    from . import nexabot_check as chk
    from . import nexabot_film as film
    from . import nexabot_i2v as i2v

    n = idx + 1
    if not film.choose_sfv(page, report):
        return None
    i2v.select_1080p(page, report)
    files = page.locator("input[type=file]")
    if files.count() == 0:
        report[f"scene{n}_error"] = "no file input"
        return None
    files.first.set_input_files(str(film.SHEET))
    try:
        files.first.evaluate("(el) => el.dispatchEvent(new Event('change', {bubbles:true}))")
    except Exception:  # noqa: BLE001
        pass
    page.wait_for_timeout(3500)
    box = page.locator("textarea[placeholder*='Describe your video']").first
    if box.count():
        box.fill(prompt)
    button = page.get_by_role("button", name="Generate", exact=True).first
    t0 = time.time()
    while time.time() - t0 < 60:
        try:
            if not button.is_disabled():
                break
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2)
    button.click()
    report[f"scene{n}_clicked_at"] = datetime.now(UTC).isoformat()

    deadline = time.time() + wait_s
    while time.time() < deadline:
        mine = [j for j in _jobs(page) if str(j.get("mode") or "").lower() == "sfv" and str(j.get("id")) not in seen]
        for job in mine:
            status = str(job.get("status") or "").lower()
            keep = ("id", "status", "mode", "progress", "width", "height", "size_bytes")
            report[f"scene{n}_job"] = {k: job.get(k) for k in keep if job.get(k) is not None}
            if status in ("failed", "error", "cancelled", "canceled"):
                report[f"scene{n}_error"] = f"the video job {status}: {job.get('progress') or job.get('error') or ''}"[:200]
                seen.add(str(job.get("id")))
                return None
            if status in ("done", "complete", "ready", "success"):
                urls = [job.get(k) for k in ("download_url", "video_url", "url") if job.get(k)]
                urls.append(f"/api/v1/jobs/{job['id']}/download")
                for url in urls:
                    full = url if url.startswith("http") else chk.ORIGIN + url
                    try:
                        resp = page.context.request.get(full, timeout=300_000)
                        body = resp.body() if resp.status == 200 else b""
                    except Exception as exc:  # noqa: BLE001
                        report[f"scene{n}_download_try"] = f"{url[:60]} -> {str(exc)[:80]}"
                        continue
                    if len(body) > 100_000:
                        dest = clip_dir / f"clip{n}.mp4"
                        dest.write_bytes(body)
                        seen.add(str(job["id"]))
                        report[f"scene{n}_saved"] = str(dest)
                        return dest
                report[f"scene{n}_error"] = "the video job is done but its file could not be downloaded"
                seen.add(str(job["id"]))
                return None
            break  # the first video job of ours is still going: wait for it, never look past it
        time.sleep(4)
    report[f"scene{n}_error"] = f"no video job finished within {wait_s // 60} minutes"
    return None


def make_clips(clip_dir: Path, sheet: Path, report: dict) -> list[Path]:
    """One Start Frame clip per scene, each from its OWN job. nexabot_film.run keeps one fixed set of "jobs that existed before
    the run", so scene 2 saw scene 1's finished job as new and downloaded it again: four identical clips (18 Nov, run 1). Here
    every finished job's id joins the set before the next scene starts, so a scene can only ever take a job made after it."""
    from . import nexabot_check as chk
    from . import nexabot_film as film
    from . import nexabot_generate as gen

    state = gen.storage_state()
    if not state:
        report["video_error"] = "no saved login"
        return []
    from playwright.sync_api import sync_playwright

    film.SHEET = sheet
    clips: list[Path] = []
    with sync_playwright() as pw:
        browser = chk.launch_browser(pw)
        try:
            ctx = browser.new_context(storage_state=state, locale="ms-MY", timezone_id="Asia/Kuala_Lumpur",
                                      viewport={"width": 1366, "height": 900}, accept_downloads=True)
            page = ctx.new_page()
            seen: set[str] = set()
            for idx, prompt in enumerate(SCENES):
                page.goto(chk.STUDIO_URL, wait_until="domcontentloaded", timeout=45_000)
                try:
                    page.wait_for_load_state("networkidle", timeout=15_000)
                except Exception:  # noqa: BLE001
                    pass
                page.wait_for_timeout(2500)
                if "/login" in page.url:
                    report["video_error"] = "login wall"
                    break
                if idx == 0:
                    jobs = page.evaluate("""async () => {
                        const r = await fetch('/api/v1/jobs?scope=recent&limit=30');
                        const j = await r.json();
                        return Array.isArray(j) ? j : (j.jobs || j.data || []);
                    }""") or []
                    seen = {str(j.get("id")) for j in jobs if j.get("id")}
                    report["jobs_before"] = len(seen)
                saved = None
                for attempt in range(1, ATTEMPTS + 1):
                    report[f"scene{idx + 1}_attempt"] = attempt
                    saved = scene_clip(page, prompt, clip_dir, report, idx, seen)
                    if saved:
                        break
                    report.setdefault(f"scene{idx + 1}_errors", []).append(report.get(f"scene{idx + 1}_error"))
                    # a refused video is often Nexabot's own temporary trouble ("preparing an account"): fresh page, ask again
                    page.goto(chk.STUDIO_URL, wait_until="domcontentloaded", timeout=45_000)
                    page.wait_for_timeout(2500)
                if not saved:
                    report["error_scene"] = idx + 1
                    break
                clips.append(Path(saved))
        finally:
            browser.close()
    (clip_dir / "clips-report.json").write_text(json.dumps(report, indent=2, default=str), "utf-8")
    return clips


def run(outdir: Path, voice: str, dry: bool) -> int:
    report: dict = {"started": datetime.now(UTC).isoformat(), "voice": voice, "dry": dry, "plan": plan()}

    def save() -> None:
        (outdir / "report.json").write_text(json.dumps(report, indent=2, default=str), "utf-8")

    if dry:
        save()
        print(json.dumps(report["plan"], indent=2, ensure_ascii=False))
        return 0

    from . import nexabot_charsheet as cs
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
    clips = make_clips(clip_dir, sheet_dir / "charsheet.png", report)
    report["clips"] = [str(c) for c in clips]
    save()
    if len(clips) != len(SCENES):
        report["failed"] = f"video: {len(clips)} of {len(SCENES)} clips were made"
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
    final = join(segments, outdir / "kucing-dan-kawan-kawan.mp4")
    report["film"] = str(final)
    report["film_seconds"] = round(duration(final), 1)
    save()
    print(json.dumps({"ok": True, "film": str(final), "seconds": report["film_seconds"]}, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--voice", default="Sulafat", help="the Voice Generator voice for the narrator")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args(sys.argv[1:])
    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    return run(outdir, a.voice, a.dry)


if __name__ == "__main__":
    sys.exit(main())
