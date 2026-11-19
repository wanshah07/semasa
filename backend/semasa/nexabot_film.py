# ruff: noqa: E501
"""Nexabot film — generate the 4 photorealistic scenes (Ingredients to Video 1-1, consistent characters).

Each scene uploads the committed character sheet (web/public/comic-panels/charsheet.png) as the ingredient image
so Hana and Hassan stay the SAME people. Ingredients mode (i2v1) is proven faster and 1080p-capable (Start Frame
mode timed out). The prompt is a description only — NO dialogue (dialogue is voice + subtitle, added later).
One fresh page load per scene, 1080p, Unlimited.

Run on GitHub with NEXABOT_STORAGE_STATE_B64, from backend:
  python -m semasa.nexabot_film OUTDIR
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from . import nexabot_check as chk
from . import nexabot_generate as gen
from . import nexabot_i2v as i2v

STUDIO = chk.STUDIO_URL
MODE_I2V = "Ingredients to Video"
MAX_WAIT_S = 15 * 60
FFMPEG = "ffmpeg"
SHEET = Path(__file__).resolve().parents[2] / "web" / "public" / "comic-panels" / "charsheet.png"

# 2 scenes, SAME shop location (no change). Scene 1 = Hana asks + Hassan cites MPPHM 40(2).
# Scene 2 = Hassan continues "pemegang sijil..." + Hana "baru tahu, jom beli keropok ni".
# "Tiada dialog lain" stops i2v improvising. Citation spelled letter-by-letter so the voice reads it fully.
SCENES = [
    "Photorealistic video, vertical 9:16 portrait framing. Di kedai runcit di Malaysia, Hana, wanita muda bertudung merah jambu dan blaus krim, "
    "memandang bungkusan snek kuning di tangannya dengan wajah hairan. Hassan, lelaki bercermin mata hitam dan baju "
    "polo biru laut, berdiri di sebelahnya. Hana berkata eh logo halal ni warna hijau, bukan sepatutnya hitam ke, "
    "jangan-jangan logo palsu. Hassan terus menjawab tak semestinya, warna bukan penentu, ada tertulis dalam M P P H M "
    "Domestik dua ribu dua puluh, Klausa empat puluh. Tiada dialog lain. Kamera statik.",
    "Photorealistic video, vertical 9:16 portrait framing. Di kedai runcit di Malaysia, rak makanan snek yang sama, latar yang sama persis seperti "
    "video sebelum ini, Hassan, lelaki bercermin mata hitam dan baju polo biru laut, terus bercakap sambil memberi "
    "isyarat tangan. Hana, wanita muda bertudung merah jambu, berdiri di tempat yang sama mendengar sambil membelek "
    "bungkusan snek kuning. Hassan berkata klausa empat puluh ayat dua itu bermaksud pemegang sijil boleh cetak logo "
    "ikut warna bungkusan. Hana tersenyum lega dan berkata ooo baru tahu, kalau macam tu jom beli keropok ni. Tiada dialog lain. Kamera statik.",
]


def choose_i2v(page, report):
    btn = page.get_by_role("button", name="Text to Video").first
    btn.click()
    page.wait_for_timeout(800)
    items = page.locator("button")
    for i in range(items.count()):
        try:
            text = (items.nth(i).inner_text() or "").strip()
        except Exception:  # noqa: BLE001
            continue
        if MODE_I2V in text:
            items.nth(i).click()
            page.wait_for_timeout(900)
            report["mode_chosen"] = text.split("\n")[0].strip()
            return True
    report["mode_chosen"] = "NOT FOUND"
    i2v.dump_controls(page, report, "i2v_dropdown_state")
    return False


def choose_r2v(page, report):
    btn = page.get_by_role("button", name="Text to Video").first
    btn.click()
    page.wait_for_timeout(800)
    items = page.locator("button")
    for i in range(items.count()):
        try:
            text = (items.nth(i).inner_text() or "").strip()
        except Exception:  # noqa: BLE001
            continue
        if "Reference Video" in text:
            items.nth(i).click()
            page.wait_for_timeout(900)
            report["mode_chosen"] = text.split("\n")[0].strip()
            return True
    report["mode_chosen"] = "NOT FOUND"
    i2v.dump_controls(page, report, "r2v_dropdown_state")
    return False


def select_portrait(page, report):
    """Pick Portrait ratio (9:16 vertical) — needed so the film fits TikTok/Reels/Threads without side-cropping."""
    try:
        btn = page.get_by_role("button", name="Portrait", exact=True).first
        if btn.count() and btn.is_visible():
            btn.click()
            page.wait_for_timeout(600)
            report["ratio_chosen"] = "Portrait"
            return True
    except Exception:  # noqa: BLE001
        pass
    report["ratio_chosen"] = "NOT FOUND"
    return False


def one_scene(page, prompt, outdir, report, idx, pre_jobs, consumed, ref_frame=None):
    """Generate one clip; return (saved_path, job_id). pre_jobs is the immutable set of job ids that existed
    before this run started; consumed is the mutable set of job ids already downloaded by earlier scenes in this run.
    A job is 'ours to download' only if its id is NOT in pre_jobs AND NOT in consumed.
    ref_frame: if set (scene 2+), use i2v Ingredients mode with TWO images — the last frame of the previous clip
    (keeps the background) + the charsheet (keeps the characters)."""
    report["scene"] = idx + 1
    if not choose_i2v(page, report):
        return None, None
    i2v.select_1080p(page, report)
    select_portrait(page, report)
    file_inputs = page.locator("input[type=file]")
    if file_inputs.count() == 0:
        report["upload"] = "no input[type=file]"
        i2v.dump_controls(page, report, "upload_state")
        return None, None
    if ref_frame:
        # Ingredients mode: frame (background) first, then charsheet (characters)
        file_inputs.first.set_input_files(str(ref_frame))
        try:
            file_inputs.first.evaluate("(el) => el.dispatchEvent(new Event('change', {bubbles:true}))")
        except Exception:  # noqa: BLE001
            pass
        page.wait_for_timeout(2500)
        if file_inputs.count() > 1:
            file_inputs.nth(1).set_input_files(str(SHEET))
            try:
                file_inputs.nth(1).evaluate("(el) => el.dispatchEvent(new Event('change', {bubbles:true}))")
            except Exception:  # noqa: BLE001
                pass
            page.wait_for_timeout(2500)
        report["upload"] = f"frame {Path(ref_frame).name} + charsheet"
    else:
        file_inputs.first.set_input_files(str(SHEET))
        try:
            file_inputs.first.evaluate("(el) => el.dispatchEvent(new Event('change', {bubbles:true}))")
        except Exception:  # noqa: BLE001
            pass
        page.wait_for_timeout(3500)
        report["upload"] = "charsheet"
    box = page.locator("textarea[placeholder*='Describe your video']").first
    if box.count():
        box.fill(prompt)
    page.screenshot(path=str(outdir / f"scene{idx+1}-preclick.png"))
    gen_btn = page.get_by_role("button", name="Generate", exact=True).first
    t0 = time.time()
    while time.time() - t0 < 60:
        try:
            if not gen_btn.is_disabled():
                break
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2)
    gen_btn.click()
    report[f"scene{idx+1}_clicked_at"] = datetime.now(UTC).isoformat()

    def fetch_jobs():
        return page.evaluate("""async () => {
            const r = await fetch('/api/v1/jobs?scope=recent&limit=30');
            const j = await r.json();
            return Array.isArray(j) ? j : (j.jobs || j.data || []);
        }""")

    def is_video_job(meta):
        # reject voice/audio/TTS jobs that the voice run may have created concurrently
        mode = str(meta.get("mode") or "").lower()
        if any(k in mode for k in ("voice", "audio", "tts", "speech")):
            return False
        # video jobs carry a width/height and a .mp4 download; audio jobs do not
        if meta.get("width") or meta.get("height"):
            return True
        # heuristic: mode text for video modes
        if any(k in mode for k in ("video", "start frame", "text to video", "image to video", "i2v", "t2v", "sfv")):
            return True
        return False

    def download(meta):
        jid = str(meta.get("id"))
        report[f"scene{idx+1}_job"] = {k: meta.get(k) for k in ("id", "mode", "width", "height", "size_bytes") if meta.get(k) is not None}
        cands = [meta.get(k) for k in ("download_url", "video_url", "url") if meta.get(k)]
        if jid:
            cands.append(f"/api/v1/jobs/{jid}/download")
        for u in cands:
            full = u if u.startswith("http") else chk.ORIGIN + u
            try:
                resp = page.context.request.get(full, timeout=300_000)
                ctype = (resp.headers.get("content-type") or "").lower()
                body = resp.body()
                is_video = ("video" in ctype or "mp4" in ctype or full.lower().endswith(".mp4"))
                if resp.status == 200 and is_video and len(body) > 500_000:
                    dest = outdir / f"clip{idx+1}.mp4"
                    dest.write_bytes(body)
                    report[f"scene{idx+1}_saved"] = str(dest)
                    consumed.add(jid)
                    return dest, jid
                # audio or too-small: skip (wrong job), keep waiting for the real video
                consumed.add(jid)
                report[f"scene{idx+1}_skip"] = f"{u[:60]} ctype={ctype[:30]} bytes={len(body)}"
            except Exception as exc:  # noqa: BLE001
                report[f"scene{idx+1}_dl_try"] = f"{u[:60]} -> {str(exc)[:80]}"
        return None, None

    deadline = time.time() + MAX_WAIT_S
    while time.time() < deadline:
        try:
            jobs = fetch_jobs()
        except Exception:  # noqa: BLE001
            jobs = []
        ours = [j for j in jobs if str(j.get("id")) not in pre_jobs and str(j.get("id")) not in consumed and is_video_job(j)]
        if ours:
            report[f"scene{idx+1}_first_seen"] = {k: ours[0].get(k) for k in ("id", "status", "mode", "progress") if ours[0].get(k) is not None}
        done = [j for j in ours if str(j.get("status") or "").lower() in ("done", "complete", "ready", "success")]
        failed = [j for j in ours if str(j.get("status") or "").lower() in ("failed", "error", "cancelled", "canceled")]
        if done:
            saved, jid = download(done[0])
            if saved:
                return saved, jid
        if failed:
            report[f"scene{idx+1}_job_failed"] = {k: failed[0].get(k) for k in ("id", "status", "error", "message") if failed[0].get(k) is not None}
            return None, None
        time.sleep(4)

    # server can be slow; give it a late-wait window before giving up
    report[f"scene{idx+1}_late_wait"] = True
    late = time.time() + 10 * 60
    while time.time() < late:
        try:
            jobs = fetch_jobs()
        except Exception:  # noqa: BLE001
            jobs = []
        ours = [j for j in jobs if str(j.get("id")) not in pre_jobs and str(j.get("id")) not in consumed and is_video_job(j)]
        done = [j for j in ours if str(j.get("status") or "").lower() in ("done", "complete", "ready", "success")]
        failed = [j for j in ours if str(j.get("status") or "").lower() in ("failed", "error", "cancelled", "canceled")]
        if done:
            saved, jid = download(done[0])
            if saved:
                return saved, jid
        if failed:
            report[f"scene{idx+1}_job_failed"] = {k: failed[0].get(k) for k in ("id", "status", "error", "message") if failed[0].get(k) is not None}
            return None, None
        time.sleep(4)
    report[f"scene{idx+1}_timed_out"] = True
    return None, None


def run(outdir: Path) -> int:
    state = gen.storage_state()
    if not state:
        print("nexabot: no saved login.")
        return 2
    if not SHEET.exists():
        print(f"missing charsheet: {SHEET}")
        return 2
    from playwright.sync_api import sync_playwright

    report = {"started": datetime.now(UTC).isoformat(), "clips": []}
    pre_jobs: set[str] = set()
    consumed: set[str] = set()
    with sync_playwright() as pw:
        browser = chk.launch_browser(pw)
        try:
            ctx = browser.new_context(storage_state=state, locale="ms-MY", timezone_id="Asia/Kuala_Lumpur",
                                      viewport={"width": 1366, "height": 900}, accept_downloads=True)
            page = ctx.new_page()
            page.goto(STUDIO, wait_until="domcontentloaded", timeout=45_000)
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:  # noqa: BLE001
                pass
            page.wait_for_timeout(2500)
            if "/login" in page.url:
                print("nexabot: LOGIN WALL.")
                return 1

            # seed pre_jobs with EVERY pre-existing job, so each scene downloads only a job created in this run
            try:
                pre = page.evaluate("""async () => {
                    const r = await fetch('/api/v1/jobs?scope=recent&limit=30');
                    const j = await r.json();
                    return Array.isArray(j) ? j : (j.jobs || j.data || []);
                }""")
                pre_jobs = {str(j.get("id")) for j in (pre or []) if j.get("id")}
                report["pre_existing_jobs"] = len(pre_jobs)
            except Exception as exc:  # noqa: BLE001
                report["pre_jobs_err"] = str(exc)[:100]

            prev_frame = None
            for idx, prompt in enumerate(SCENES):
                if idx > 0:
                    # fresh page per scene clears prior attachment
                    page.goto(STUDIO, wait_until="domcontentloaded", timeout=45_000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=15_000)
                    except Exception:  # noqa: BLE001
                        pass
                    page.wait_for_timeout(2500)
                saved = None
                # scene 2+ uses the last frame of the previous clip (background) + charsheet (characters)
                ref = prev_frame if idx > 0 else None
                for attempt in range(1, 4):
                    saved, jid = one_scene(page, prompt, outdir, report, idx, pre_jobs, consumed, ref_frame=ref)
                    if saved:
                        break
                    # retry transient server failures (e.g. "server restart")
                    reason = report.get(f"scene{idx+1}_job_failed") or {}
                    err = str(reason.get("error") or reason.get("message") or "")
                    if "restart" in err.lower() or "try again" in err.lower() or "interrupted" in err.lower():
                        report[f"scene{idx+1}_attempt"] = attempt
                        # fresh page + re-choose mode/upload for the retry
                        page.goto(STUDIO, wait_until="domcontentloaded", timeout=45_000)
                        try:
                            page.wait_for_load_state("networkidle", timeout=15_000)
                        except Exception:  # noqa: BLE001
                            pass
                        page.wait_for_timeout(2500)
                        time.sleep(5)
                        continue
                    break
                if saved:
                    report["clips"].append(str(saved))
                    # extract the last frame of this clip as the background reference for the next scene
                    try:
                        frame = outdir / f"frame{idx+1}.png"
                        subprocess.run([FFMPEG, "-y", "-sseof", "-1", "-i", str(saved),
                                        "-frames:v", "1", str(frame)], check=True,
                                       capture_output=True, timeout=120)
                        if frame.exists() and frame.stat().st_size > 1000:
                            prev_frame = str(frame)
                            report[f"scene{idx+1}_frame_ref"] = str(frame)
                    except Exception as exc:  # noqa: BLE001
                        report[f"scene{idx+1}_frame_err"] = str(exc)[:120]
                else:
                    report["error_scene"] = idx + 1
                    break
        finally:
            browser.close()

    (outdir / "report.json").write_text(json.dumps(report, indent=2, default=str), "utf-8")
    print(json.dumps({"ok": len(report["clips"]) == len(SCENES), "clips": len(report["clips"]),
                      "total": len(SCENES)}, indent=2))
    return 0 if len(report["clips"]) == len(SCENES) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    a = ap.parse_args(sys.argv[1:])
    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    return run(outdir)


if __name__ == "__main__":
    sys.exit(main())
