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
import base64
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from . import nexabot_check as chk
from . import nexabot_i2v as i2v

PANELS_DIR = Path(__file__).resolve().parents[2] / "web" / "public" / "comic-panels"
PANELS = ["panel-p1.png", "panel-p2.png", "panel-p3.png", "panel-p4.png"]
PROMPT = "Animate this comic panel: the two characters gesture and talk naturally, the scene stays still, no camera zoom"
MAX_WAIT_S = 15 * 60
POLL_S = 4


def _clip(page, panel: Path, outdir: Path, report: dict) -> bool:
    """One i2v generation: choose mode, upload the panel, generate, poll, download. Returns whether an MP4 landed."""
    # mode dropdown
    if not i2v.choose_mode(page, report):
        return False
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
    gen_epoch = int(time.time() * 1000)  # ms; the new job's created_at is after this
    deadline = time.time() + MAX_WAIT_S
    url = report.get("video_url")
    job_meta = {}
    first_poll = True
    while time.time() < deadline:
        try:
            jobs = page.evaluate("""async () => {
                const r = await fetch('/api/v1/jobs?scope=recent&limit=30');
                const j = await r.json();
                return Array.isArray(j) ? j : (j.jobs || j.data || []);
            }""")
        except Exception:  # noqa: BLE001
            jobs = []
        if first_poll:
            report["jobs_sample"] = [{k: j.get(k) for k in ("id", "status", "mode", "created_at") if j.get(k) is not None} for j in jobs[:5]]
            first_poll = False
        # the NEW job: created after the Generate click, or (if no timestamps) the latest one
        new = [j for j in jobs if (j.get("created_at") or 0) >= gen_epoch - 2000]
        if not new:
            new = jobs[:1]
        done = [j for j in new if j.get("status") in ("done", "complete", "ready", "success")]
        if done:
            job_meta = done[0]
            url = url or report.get("video_url") or job_meta.get("download_url") or job_meta.get("video_url") or job_meta.get("url")
            break
        time.sleep(POLL_S)
    if not url:
        report["job_meta_no_url"] = {k: job_meta.get(k) for k in ("id", "status", "mode", "model", "download_url", "video_url", "url", "created_at") if job_meta.get(k)}
        return False
    import requests
    r = requests.get(url, timeout=300, stream=True)
    if r.status_code != 200:
        # a download_url may be relative; try against the base
        if url.startswith("/"):
            url2 = "https://nexabot.id" + url
            r = requests.get(url2, timeout=300, stream=True)
            if r.status_code != 200:
                report["download_error"] = f"status {r.status_code}"
                return False
        else:
            report["download_error"] = f"status {r.status_code}"
            return False
    dest = outdir / f"clip-{datetime.now(UTC).strftime('%H%M%S')}.mp4"
    with open(dest, "wb") as fh:
        for chunk in r.iter_content(1 << 20):
            fh.write(chunk)
    report.setdefault("clips", []).append(str(dest))
    return True


def concat(clips: list[str], out: Path) -> Path:
    list_file = out.parent / "clips.txt"
    list_file.write_text("".join(f"file '{c}'\n" for c in clips), "utf-8")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(out)],
                   check=True, capture_output=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args(sys.argv[1:])
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

            def on_response(resp):
                req = resp.request
                ctype = resp.headers.get("content-type", "")
                if req.method == "GET" and i2v.gen._is_video(ctype, req.url) and not report.get("video_url"):
                    report["video_url"] = req.url
                # record every POST and any video-bearing response, for diagnosing where the result lands
                if req.method == "POST" or i2v.gen._is_video(ctype, req.url):
                    report.setdefault("network", []).append(
                        {"method": req.method, "url": req.url[:200], "status": resp.status, "ctype": ctype[:80]})

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

            for panel in panels:
                report["video_url"] = None
                ok = _clip(page, panel, outdir, report)
                if not ok:
                    report["error_panel"] = panel.name
                    break
            if len(report.get("clips", [])) == len(panels):
                film = concat(report["clips"], outdir / "comic-film.mp4")
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
