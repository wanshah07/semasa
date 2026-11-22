# ruff: noqa: E501
"""Nexabot comic film — animate the four comic panels (one i2v generation each) and concatenate them into one MP4.

Reads the 4 panels from web/public/comic-panels/panel-p{1..4}.png (committed temporarily for an episode), drives the
Creator Studio once per panel (i2v mode), downloads each clip, concatenates them with ffmpeg, and hands the finished
film to Semasa's import-video route (SEMASA_IMPORT_TOKEN / SEMASA_IMPORT_URL) as a DRAFT post.

The i2v UI was not yet seen, so every run records the controls it finds; a UI difference is visible in the artifact
instead of a mysterious timeout. By hand only.

Run on the GitHub runner (NEXABOT_STORAGE_STATE_B64), from backend:
  python -m semasa.nexabot_comic_film OUTDIR [--dry]
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from . import nexabot_check as chk
from . import nexabot_generate as gen
from . import nexabot_i2v as i2v
from . import short_films

PANELS_DIR = Path(__file__).resolve().parents[2] / "web" / "public" / "comic-panels"
PANELS = ["panel-p1.png", "panel-p2.png", "panel-p3.png", "panel-p4.png"]
PROMPT = "Animate this comic panel: the two characters gesture and talk naturally, the scene stays still, no camera zoom"
MAX_WAIT_S = 15 * 60
POLL_S = 4

# each panel's dialogue, burned as a subtitle AFTER Nexabot animates the panel (Nexabot cannot render text reliably). The words are
# the short-film category's (rules/short_films.json `panel_lines`): the halal family's by default, exactly as before.
DEFAULT_CATEGORY = "kisah-keluarga-halal"


def lines_of(category_id: str) -> tuple[list[tuple[str, str]], str]:
    """(who, text) lines and the credit of a built-in category's panel film; ([], "") when it has none."""
    cat = short_films.category_of(short_films.library(), category_id)
    script = (cat or {}).get("script") or {}
    return [(x["who"], x["text"]) for x in script.get("panel_lines") or []], str(script.get("credit") or "")


SUBTITLES, CREDIT = lines_of(DEFAULT_CATEGORY)


def _clip(page, panel: Path, outdir: Path, report: dict, fresh: bool = False) -> bool:
    """One i2v generation: choose mode, upload the panel, generate, poll, download. Returns whether an MP4 landed."""
    if fresh:
        # a fresh page load clears the previous panel's attachment and any stuck state, so each panel starts clean
        page.goto(chk.STUDIO_URL, wait_until="domcontentloaded", timeout=45_000)
        try:
            page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:  # noqa: BLE001
            pass
        page.wait_for_timeout(2500)
    # mode dropdown
    if not i2v.choose_mode(page, report):
        return False
    # pick 1080p (default is 720p) — the film is 1920x1080
    i2v.select_1080p(page, report)
    if not i2v.upload_panel(page, panel, report):
        return False
    # i2v REQUIRES a text prompt too (the Generate button stays disabled with an empty prompt)
    box = page.locator("textarea[placeholder*='Describe your video']").first
    if box.count():
        box.fill(PROMPT)
        report["prompt_filled"] = True
    # verify the mode actually stayed on Ingredients (a UI quirk can reset it to t2v)
    try:
        mode_now = page.evaluate("""() => {
            const b = [...document.querySelectorAll('button')].find(b => /Text to Video|Start Frame|Ingredients|Reference/.test((b.innerText||'')) && (b.innerText||'').length < 60);
            return b ? (b.innerText||'').trim() : '';
        }""")
        report["mode_after_upload"] = mode_now
    except Exception as exc:  # noqa: BLE001
        report["mode_after_upload"] = f"err {str(exc)[:80]}"
    # the Generate button stays disabled until the uploaded image is processed: wait for it, then click
    gen_btn = page.get_by_role("button", name="Generate", exact=True).first
    # screenshot the pre-click state so a wrong mode/empty attach is visible, not guessed
    page.screenshot(path=str(outdir / f"preclick-{panel.stem}.png"))
    enabled_at = time.time() + 60
    while time.time() < enabled_at:
        try:
            if not gen_btn.is_disabled():
                break
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2)
    else:
        report["generate_never_enabled"] = True
        i2v.dump_controls(page, report, "generate_disabled_state")
        page.screenshot(path=str(outdir / "generate-disabled.png"))
        return False
    gen_btn.click()
    report["generate_clicked_at"] = datetime.now(UTC).isoformat()
    # follow OUR job (the POST's own answer id), then download its MP4 — the same approach nexabot_generate.py uses.
    # A job id comes from the Generate answer captured in `report["job_id"]`, else from the one job not in the list before.
    before = gen._recent_jobs(page)
    before_ids = {str(j.get("id")) for j in before or [] if j.get("id")}
    deadline = time.time() + MAX_WAIT_S
    meta: dict = {}
    job_id = report.get("job_id")
    while time.time() < deadline:
        if not job_id and before is not None:
            fresh = [j for j in (gen._recent_jobs(page) or []) if str(j.get("id")) not in before_ids]
            if fresh:
                job_id = str(fresh[0].get("id"))
                report["job_id"] = job_id
        if job_id:
            meta = gen._job(page, job_id) or {}
            status = str(meta.get("status") or "").lower()
            if status in gen.DONE_STATES:
                break
            if status in gen.FAILED_STATES:
                report["job_failed"] = {k: meta.get(k) for k in ("id", "status", "error") if meta.get(k)}
                return False
        time.sleep(POLL_S)
    else:
        report["timed_out"] = True
        return False
    # download: the job's own link first, then the documented download route, with the studio login
    cands = [meta.get(k) for k in ("download_url", "video_url", "url")]
    cands += [f"/api/v1/jobs/{job_id}/download"] if job_id else []
    for url in [c for c in cands if isinstance(c, str) and c]:
        full = url if url.startswith("http") else "https://nexabot.id" + url
        try:
            resp = page.context.request.get(full, timeout=300_000)
            if resp.status == 200 and len(resp.body()) > 10_000:
                dest = outdir / f"clip-{datetime.now(UTC).strftime('%H%M%S')}.mp4"
                dest.write_bytes(resp.body())
                report["clip_saved"] = str(dest)
                report.setdefault("clips", []).append(str(dest))
                return True
        except Exception as exc:  # noqa: BLE001
            report["download_tries"] = report.get("download_tries", []) + [f"{url[:60]} -> {str(exc)[:80]}"]
    report["download_error"] = "; ".join(report.get("download_tries", []))[:400]
    return False


def concat(clips: list[str], out: Path) -> Path:
    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    list_file = out.parent / "clips.txt"
    list_file.write_text("".join(f"file '{c}'\n" for c in clips), "utf-8")
    subprocess.run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(out)],
                   check=True, capture_output=True)
    return out


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:").replace(",", "\\,").replace("%", "\\%")


def _dur(path: Path) -> float:
    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    p = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path)], capture_output=True, text=True)
    import re
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", p.stderr)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


def spread(n_lines: int, n_clips: int) -> dict[int, list[int]]:
    """Which lines go on which clip, in order. Six lines on four clips keep the family film's own pattern (1, 2+3, 4, 5+6);
    any other count is shared out as evenly as it goes, the earlier clips taking one more."""
    if n_lines == 6 and n_clips == 4:
        return {0: [0], 1: [1, 2], 2: [3], 3: [4, 5]}
    out: dict[int, list[int]] = {}
    at = 0
    for ci in range(n_clips):
        take = n_lines // n_clips + (1 if ci < n_lines % n_clips else 0)
        out[ci] = list(range(at, at + take))
        at += take
    return out


def burn_subtitles(clips: list[str], film: Path, out: Path, lines: list[tuple[str, str]] | None = None,
                   credit: str | None = None) -> Path:
    """Burn each dialogue line as a subtitle into the concatenated film. Nexabot animated the panels; this step adds
    the exact words (Nexabot cannot render text reliably), one line per clip, plus the credit on the last one.
    Six dialogue lines map onto the four clips: clip 1 -> line 1, clip 2 -> lines 2+3, clip 3 -> line 4, clip 4 -> lines 5+6.
    """
    import imageio_ffmpeg
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    durs = [_dur(Path(c)) for c in clips]
    # line -> (start, end) inside the film timeline
    starts: list[float] = []
    t = 0.0
    for d in durs:
        starts.append(t)
        t += d
    total = t
    lines = SUBTITLES if lines is None else lines
    credit = CREDIT if credit is None else credit
    per_clip = spread(len(lines), len(clips))
    vf = []
    fontfile = "C\\:/Windows/Fonts/arialbd.ttf"  # fallback; the runner has DejaVu, use a robust path
    # actually use DejaVu on the ubuntu runner (always present)
    fontfile = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    for ci, line_idxs in per_clip.items():
        cstart = starts[ci]
        cdur = durs[ci]
        n = len(line_idxs)
        if not n:
            continue
        seg = cdur / n
        for k, li in enumerate(line_idxs):
            who, text = lines[li]
            s = cstart + k * seg
            e = s + seg
            label = f"{who}\\: {text}"
            vf.append(
                f"drawtext=fontfile={fontfile}:text='{_escape(label)}':fontsize=44:fontcolor=white:"
                f"borderw=3:bordercolor=black:box=1:boxcolor=black@0.6:boxborderw=18:"
                f"x=(w-text_w)/2:y=h-140:enable='between(t,{s:.2f},{e:.2f})'"
            )
    # the credit, held on the final clip's tail (last 2s)
    if credit:
        vf.append(
            f"drawtext=fontfile={fontfile}:text='{_escape(credit)}':fontsize=36:fontcolor=white:"
            f"borderw=3:bordercolor=black:box=1:boxcolor=black@0.6:boxborderw=18:"
            f"x=(w-text_w)/2:y=h-140:enable='between(t,{total - 2:.2f},{total:.2f})'"
        )
    if not vf:
        shutil.copyfile(film, out)
        return out
    chain = ",".join(vf)
    subprocess.run([ffmpeg, "-y", "-i", str(film), "-vf", chain, "-c:a", "copy", str(out)],
                   check=True, capture_output=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--category", default=DEFAULT_CATEGORY, help="the built-in short-film category whose panel lines are burned in")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args(sys.argv[1:])
    lines, credit = lines_of(a.category.strip() or DEFAULT_CATEGORY)
    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    panels = [PANELS_DIR / p for p in PANELS]
    missing = [str(p) for p in panels if not p.exists()]
    if missing:
        print("missing panels:", missing)
        return 2

    state = i2v.gen.storage_state()
    if not state:
        print("nexabot: no saved login.")
        return 2
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is not installed.")
        return 2

    report: dict = {"started": datetime.now(UTC).isoformat(), "dry": a.dry, "clips": [], "video_url": None}
    with sync_playwright() as pw:
        browser = chk.launch_browser(pw)
        try:
            ctx = browser.new_context(storage_state=state, locale="en-MY", timezone_id="Asia/Kuala_Lumpur",
                                      viewport={"width": 1366, "height": 900}, accept_downloads=True)
            page = ctx.new_page()

            def on_request(req):
                if req.method == "POST" and ("/api/" in req.url or "generate" in req.url.lower()):
                    try:
                        body = req.post_data or ""
                    except Exception:  # noqa: BLE001
                        body = ""
                    # record the mode + whether media/images are present, but NEVER a token or full base64
                    report.setdefault("posts", []).append({
                        "url": req.url[:200],
                        "has_media": "media" in body or "image" in body.lower() or "base64" in body,
                        "body_head": body[:200],
                    })

            def on_response(resp):
                req = resp.request
                ctype = resp.headers.get("content-type", "")
                if req.method == "GET" and i2v.gen._is_video(ctype, req.url) and not report.get("video_url"):
                    report["video_url"] = req.url
                if req.method == "POST" or i2v.gen._is_video(ctype, req.url):
                    report.setdefault("network", []).append(
                        {"method": req.method, "url": req.url[:200], "status": resp.status, "ctype": ctype[:80]})

            page.on("request", on_request)
            page.on("response", on_response)
            page.goto(chk.STUDIO_URL, wait_until="domcontentloaded", timeout=45_000)
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:  # noqa: BLE001
                pass
            page.wait_for_timeout(2500)
            report["final_url"] = page.url
            if "/login" in page.url:
                print("nexabot: LOGIN WALL.")
                return 1

            if a.dry:
                # dry: just record the i2v UI (mode + upload controls), no generate
                if i2v.choose_mode(page, report):
                    i2v.dump_controls(page, report, "i2v_ui_dry")
                (outdir / "report.json").write_text(json.dumps(report, indent=2), "utf-8")
                print(json.dumps({"ok": True, "dry": True}, indent=2))
                return 0

            for i, panel in enumerate(panels):
                report["video_url"] = None
                ok = _clip(page, panel, outdir, report, fresh=(i > 0))
                if not ok:
                    report["error_panel"] = panel.name
                    break
            if len(report.get("clips", [])) == len(panels):
                raw = concat(report["clips"], outdir / "comic-film-raw.mp4")
                film = burn_subtitles(report["clips"], raw, outdir / "comic-film.mp4", lines, credit)
                report["film"] = str(film)
                print("film saved:", film)
        finally:
            browser.close()

    (outdir / "report.json").write_text(json.dumps(report, indent=2), "utf-8")
    print(json.dumps({"ok": bool(report.get("film")), "clips": len(report.get("clips", [])),
                      "film": report.get("film")}, indent=2))
    return 0 if report.get("film") else 1


if __name__ == "__main__":
    sys.exit(main())
