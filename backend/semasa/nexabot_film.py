# ruff: noqa: E501
"""Nexabot film — generate the 4 photorealistic scenes (Start Frame, consistent characters) for the halal-logo story.

Each scene uses the committed character sheet (web/public/comic-panels/charsheet.png) as the Start Frame so Hana and
Hassan stay the SAME people. The prompt is a description only — NO dialogue (dialogue is voice + subtitle, added later).
One fresh page load per scene, 1080p, Unlimited.

Run on GitHub with NEXABOT_STORAGE_STATE_B64, from backend:
  python -m semasa.nexabot_film OUTDIR
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
from . import nexabot_i2v as i2v

STUDIO = chk.STUDIO_URL
MODE_SFV = "Start Frame"
MAX_WAIT_S = 15 * 60
SHEET = Path(__file__).resolve().parents[2] / "web" / "public" / "comic-panels" / "charsheet.png"

# 4 scenes, description only (no dialogue text — the model would garble it and it repeats)
SCENES = [
    "Photorealistic video. Di kedai runcit di Malaysia, Hana, wanita muda bertudung merah jambu dan blaus krim, "
    "memandang bungkusan snek kuning di tangannya dengan wajah hairan. Hassan, lelaki bercermin mata hitam dan baju "
    "polo biru laut, berdiri di sebelahnya sambil melihat. Kamera statik, pergerakan semula jadi.",
    "Photorealistic video. Di kedai runcit di Malaysia, Hassan, lelaki bercermin mata hitam dan baju polo biru laut, "
    "memandang bungkusan snek kuning dengan risau, tangan menyentuh dagu. Hana, wanita muda bertudung merah jambu, "
    "tersenyum tenang dan mengangkat satu tangan. Kamera statik.",
    "Photorealistic video. Di kedai runcit di Malaysia, Hana, wanita muda bertudung merah jambu, menunjuk bungkusan "
    "snek kuning dan menerangkan sesuatu. Hassan, lelaki bercermin mata hitam dan baju polo biru laut, mendengar "
    "dengan minat. Kamera statik.",
    "Photorealistic video. Di kedai runcit di Malaysia, Hassan, lelaki bercermin mata hitam dan baju polo biru laut, "
    "kelihatan lega dan ingin tahu. Hana, wanita muda bertudung merah jambu, mengangkat bungkusan snek kuning dan "
    "menunjuk ke arahnya. Kamera statik.",
]


def choose_sfv(page, report):
    btn = page.get_by_role("button", name="Text to Video").first
    btn.click()
    page.wait_for_timeout(800)
    items = page.locator("button")
    for i in range(items.count()):
        try:
            text = (items.nth(i).inner_text() or "").strip()
        except Exception:  # noqa: BLE001
            continue
        if MODE_SFV in text:
            items.nth(i).click()
            page.wait_for_timeout(900)
            report["mode_chosen"] = text.split("\n")[0].strip()
            return True
    report["mode_chosen"] = "NOT FOUND"
    i2v.dump_controls(page, report, "sfv_dropdown_state")
    return False


def one_scene(page, prompt, outdir, report, idx, seen_jobs):
    """Generate one sfv clip; return the saved path or None. seen_jobs is a set of job ids already downloaded."""
    report["scene"] = idx + 1
    if not choose_sfv(page, report):
        return None
    i2v.select_1080p(page, report)
    file_inputs = page.locator("input[type=file]")
    if file_inputs.count() == 0:
        report["upload"] = "no input[type=file]"
        i2v.dump_controls(page, report, "sfv_upload_state")
        return None
    file_inputs.first.set_input_files(str(SHEET))
    try:
        file_inputs.first.evaluate("(el) => el.dispatchEvent(new Event('change', {bubbles:true}))")
    except Exception:  # noqa: BLE001
        pass
    page.wait_for_timeout(3500)
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

    deadline = time.time() + MAX_WAIT_S
    while time.time() < deadline:
        try:
            jobs = page.evaluate("""async () => {
                const r = await fetch('/api/v1/jobs?scope=recent&limit=30');
                const j = await r.json();
                return Array.isArray(j) ? j : (j.jobs || j.data || []);
            }""")
        except Exception:  # noqa: BLE001
            jobs = []
        # a NEW done video job we have not already downloaded (skip stale/old jobs)
        done = [j for j in jobs
                if str(j.get("status") or "").lower() in ("done", "complete", "ready", "success")
                and str(j.get("mode") or "").lower() in ("sfv", "i2v", "t2v", "video", "r2v", "extend")
                and str(j.get("id")) not in seen_jobs]
        if done:
            meta = done[0]
            jid = str(meta.get("id"))
            seen_jobs.add(jid)
            report[f"scene{idx+1}_job"] = {k: meta.get(k) for k in ("id", "mode", "width", "height", "size_bytes") if meta.get(k) is not None}
            cands = [meta.get(k) for k in ("download_url", "video_url", "url") if meta.get(k)]
            if jid:
                cands.append(f"/api/v1/jobs/{jid}/download")
            for u in cands:
                full = u if u.startswith("http") else chk.ORIGIN + u
                try:
                    resp = page.context.request.get(full, timeout=300_000)
                    if resp.status == 200 and len(resp.body()) > 100_000:
                        dest = outdir / f"clip{idx+1}.mp4"
                        dest.write_bytes(resp.body())
                        report[f"scene{idx+1}_saved"] = str(dest)
                        return str(dest)
                except Exception as exc:  # noqa: BLE001
                    report[f"scene{idx+1}_dl_try"] = f"{u[:60]} -> {str(exc)[:80]}"
            return None
        time.sleep(4)
    report[f"scene{idx+1}_timed_out"] = True
    return None


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
    seen_jobs: set[str] = set()
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

            for idx, prompt in enumerate(SCENES):
                if idx > 0:
                    # fresh page per scene clears prior attachment
                    page.goto(STUDIO, wait_until="domcontentloaded", timeout=45_000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=15_000)
                    except Exception:  # noqa: BLE001
                        pass
                    page.wait_for_timeout(2500)
                saved = one_scene(page, prompt, outdir, report, idx, seen_jobs)
                if saved:
                    report["clips"].append(saved)
                else:
                    report["error_scene"] = idx + 1
                    break
        finally:
            browser.close()

    (outdir / "report.json").write_text(json.dumps(report, indent=2), "utf-8")
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
