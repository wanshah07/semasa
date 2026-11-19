"""Nexabot mode test — generate ONE video in a chosen mode, to compare how each mode behaves.

Modes (from the "Text to Video" dropdown):
  t2v   Text to Video          (prompt only)
  sfv   Start Frame to Video   (1 image -> first frame)
  i2v1  Ingredients to Video 1-1 img (1 image)
  i2v3  Ingredients to Video 1-3 img (up to 3 images)
  r2v   Reference Video to Video (video + img)

Each mode uploads its required media, fills the prompt, picks 1080p + Unlimited, Generate,
then follows OUR job id (from the Generate POST answer) and downloads the MP4.

Run on GitHub with NEXABOT_STORAGE_STATE_B64, from backend:
  python -m semasa.nexabot_mode_test OUTDIR --mode t2v --prompt "..." [--img a.png] [--img2 b.png] [--video v.mp4]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from . import nexabot_check as chk
from . import nexabot_generate as gen

STUDIO = chk.STUDIO_URL
MAX_WAIT_S = 15 * 60
LATE_WAIT_S = 10 * 60

# mode -> (menu item text to click, needs)
MODES = {
    "t2v": ("Text to Video", []),
    "sfv": ("Start Frame to Video", ["img"]),
    "i2v1": ("Ingredients to Video", ["img"]),
    "i2v3": ("Ingredients to Video", ["img", "img2", "img3"]),
    "r2v": ("Reference Video to Video", ["video", "img"]),
}


def dump_controls(page, report, label):
    try:
        report[label] = page.evaluate("""() => ({
            buttons: [...document.querySelectorAll('button')].map(b=>(b.innerText||'').trim().slice(0,40)).filter(Boolean),
            inputs: [...document.querySelectorAll('input[type=file]')].map(i=>({accept:i.accept||'',name:i.name||''})),
            options: [...document.querySelectorAll('[role=option],[role=menuitem]')].map(o=>(o.innerText||'').trim().slice(0,40)).filter(Boolean)
        })""")
    except Exception as exc:  # noqa: BLE001
        report[label] = f"dump failed: {str(exc)[:100]}"


def choose_mode(page, report, mode_key):
    menu_item = MODES[mode_key][0]
    btn = page.get_by_role("button", name="Text to Video").first
    btn.click()
    page.wait_for_timeout(800)
    items = page.locator("button")
    for i in range(items.count()):
        try:
            text = (items.nth(i).inner_text() or "").strip()
        except Exception:  # noqa: BLE001
            continue
        if menu_item in text:
            items.nth(i).click()
            page.wait_for_timeout(900)
            report["mode_chosen"] = text.split("\n")[0].strip()
            return True
    report["mode_chosen"] = "NOT FOUND"
    dump_controls(page, report, "mode_dropdown_state")
    return False


def run(outdir: Path, mode_key: str, prompt: str, imgs: list[Path], video: Path | None) -> int:
    state = gen.storage_state()
    if not state:
        return 2
    from playwright.sync_api import sync_playwright

    report = {"started": datetime.now(UTC).isoformat(), "mode": mode_key, "prompt": prompt[:200]}
    with sync_playwright() as pw:
        browser = chk.launch_browser(pw)
        try:
            ctx = browser.new_context(storage_state=state, locale="ms-MY", timezone_id="Asia/Kuala_Lumpur",
                                      viewport={"width": 1366, "height": 900}, accept_downloads=True)
            page = ctx.new_page()

            def on_response(resp):
                req = resp.request
                if req.method == "POST" and req.url.rstrip("/").endswith("/api/v1/generate") and resp.status in (200, 201, 202):
                    try:
                        j = resp.json()
                        j = j.get("job") if isinstance(j.get("job"), dict) else j
                        jid = j.get("id") or j.get("job_id") or j.get("jobId")
                        if jid:
                            report["job_id"] = str(jid)
                            report["job_id_via"] = "generate_answer"
                    except Exception:  # noqa: BLE001
                        pass

            page.on("response", on_response)
            page.goto(STUDIO, wait_until="domcontentloaded", timeout=45_000)
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:  # noqa: BLE001
                pass
            page.wait_for_timeout(2500)
            if "/login" in page.url:
                return 1

            if not choose_mode(page, report, mode_key):
                (outdir / "report.json").write_text(json.dumps(report, indent=2), "utf-8")
                return 1

            # upload media per mode
            file_inputs = page.locator("input[type=file]")
            if imgs:
                if file_inputs.count() == 0:
                    report["upload"] = "no input[type=file]"
                    dump_controls(page, report, "upload_state")
                else:
                    for k, img in enumerate(imgs):
                        inp = file_inputs.nth(k) if file_inputs.count() > k else file_inputs.first
                        inp.set_input_files(str(img))
                        try:
                            inp.evaluate("(el) => el.dispatchEvent(new Event('change', {bubbles:true}))")
                        except Exception:  # noqa: BLE001
                            pass
                        page.wait_for_timeout(1500)
                    report["upload"] = f"set {len(imgs)} image(s)"
            if video:
                # reference video: an input accepting video
                vid_inputs = page.locator("input[type=file]")
                vid_inputs.first.set_input_files(str(video))
                try:
                    vid_inputs.first.evaluate("(el) => el.dispatchEvent(new Event('change', {bubbles:true}))")
                except Exception:  # noqa: BLE001
                    pass
                page.wait_for_timeout(3000)
                report["upload"] += f" + video {video.name}"

            # 1080p
            try:
                page.get_by_role("button", name="1080p", exact=True).first.click()
                page.wait_for_timeout(600)
                report["resolution"] = "1080p"
            except Exception:  # noqa: BLE001
                report["resolution"] = "default"

            # prompt
            box = page.locator("textarea[placeholder*='Describe your video']").first
            if box.count():
                box.fill(prompt)
                report["prompt_filled"] = True

            page.screenshot(path=str(outdir / "preclick.png"))

            # baseline jobs
            try:
                baseline = page.evaluate("""async () => {
                    const r = await fetch('/api/v1/jobs?scope=recent&limit=30');
                    const j = await r.json();
                    return Array.isArray(j) ? j : (j.jobs || j.data || []);
                }""")
                baseline_ids = {str(j.get("id")) for j in (baseline or []) if j.get("id")}
            except Exception:  # noqa: BLE001
                baseline_ids = set()

            gen_btn = page.get_by_role("button", name="Generate", exact=True).first
            report["generate_disabled"] = gen_btn.is_disabled()
            gen_btn.click()
            report["generate_clicked_at"] = datetime.now(UTC).isoformat()

            deadline = time.time() + MAX_WAIT_S + LATE_WAIT_S
            meta = {}
            while time.time() < deadline:
                job_id = report.get("job_id")
                if job_id:
                    try:
                        m = page.evaluate("""async (id) => {
                            const r = await fetch('/api/v1/jobs/' + encodeURIComponent(id));
                            return r.ok ? await r.json() : null;
                        }""", job_id)
                        if isinstance(m, dict):
                            m = m.get("job") if isinstance(m.get("job"), dict) else m
                            meta = m
                    except Exception:  # noqa: BLE001
                        meta = {}
                    st = str(meta.get("status") or "").lower()
                    if st in ("done", "complete", "ready", "success"):
                        report["job_done"] = True
                        break
                    if st in ("failed", "error", "cancelled", "canceled"):
                        report["job_failed"] = st
                        break
                else:
                    try:
                        jobs = page.evaluate("""async () => {
                            const r = await fetch('/api/v1/jobs?scope=recent&limit=30');
                            const j = await r.json();
                            return Array.isArray(j) ? j : (j.jobs || j.data || []);
                        }""")
                    except Exception:  # noqa: BLE001
                        jobs = []
                    fresh = [j for j in jobs if str(j.get("id")) not in baseline_ids]
                    if fresh:
                        report["job_id"] = str(fresh[0].get("id"))
                        report["job_id_via"] = "list_diff"
                        meta = fresh[0]
                        st = str(meta.get("status") or "").lower()
                        if st in ("done", "complete", "ready", "success"):
                            report["job_done"] = True
                            break
                time.sleep(4)
            else:
                report["timed_out"] = True

            if report.get("job_done"):
                jid = str(report.get("job_id") or meta.get("id"))
                cands = [meta.get(k) for k in ("download_url", "video_url", "url") if meta.get(k)]
                if jid:
                    cands.append(f"/api/v1/jobs/{jid}/download")
                for u in cands:
                    full = u if u.startswith("http") else chk.ORIGIN + u
                    try:
                        resp = page.context.request.get(full, timeout=300_000)
                        ctype = (resp.headers.get("content-type") or "").lower()
                        body = resp.body()
                        is_video = "video" in ctype or "mp4" in ctype or full.lower().endswith(".mp4")
                        if resp.status == 200 and is_video and len(body) > 500_000:
                            dest = outdir / f"mode-{mode_key}.mp4"
                            dest.write_bytes(body)
                            report["video_saved"] = str(dest)
                            report["video_size_final"] = len(body)
                            break
                    except Exception as exc:  # noqa: BLE001
                        report["download_error"] = f"{u[:60]} -> {str(exc)[:100]}"
        finally:
            browser.close()

    (outdir / "report.json").write_text(json.dumps(report, indent=2, default=str), "utf-8")
    print(json.dumps({"ok": bool(report.get("video_saved")), "mode": mode_key,
                      "video_saved": report.get("video_saved")}, indent=2))
    return 0 if report.get("video_saved") else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--mode", required=True, choices=list(MODES))
    ap.add_argument("--prompt", default="")
    ap.add_argument("--img", action="append", default=[], help="image (repeatable)")
    ap.add_argument("--video", default="", help="reference video path")
    a = ap.parse_args(sys.argv[1:])
    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    imgs = [Path(x) for x in a.img if x]
    video = Path(a.video) if a.video else None
    return run(outdir, a.mode, a.prompt, imgs, video)


if __name__ == "__main__":
    sys.exit(main())
