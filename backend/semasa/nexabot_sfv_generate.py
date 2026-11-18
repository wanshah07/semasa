"""Nexabot sfv generate — generate ONE scene with the character sheet as Start Frame (consistent characters).

Reuses nexabot_i2v.choose_mode's substring-matching approach but targets "Start Frame to Video" (sfv). Uploads the
charsheet, keeps prompt minimal (NO dialogue in the prompt — dialogue is voice+subtitle only), picks 1080p, Unlimited,
Generate, poll the job, download the MP4.

Run on GitHub with NEXABOT_STORAGE_STATE_B64, from backend:
  python -m semasa.nexabot_sfv_generate OUTDIR --sheet path/to/charsheet.png --prompt "..." [--dry]
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


def choose_sfv(page, report: dict) -> bool:
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


def run(outdir: Path, sheet: Path, prompt: str, dry: bool) -> int:
    state = gen.storage_state()
    if not state:
        return 2
    from playwright.sync_api import sync_playwright

    report = {"started": datetime.now(UTC).isoformat(), "sheet": sheet.name, "dry": dry,
              "video_url": None, "video_saved": None}
    with sync_playwright() as pw:
        browser = chk.launch_browser(pw)
        try:
            ctx = browser.new_context(storage_state=state, locale="ms-MY", timezone_id="Asia/Kuala_Lumpur",
                                      viewport={"width": 1366, "height": 900}, accept_downloads=True)
            page = ctx.new_page()

            def on_response(resp):
                req = resp.request
                ctype = resp.headers.get("content-type", "")
                if req.method == "GET" and gen._is_video(ctype, req.url) and not report.get("video_url"):
                    report["video_url"] = req.url

            page.on("response", on_response)
            page.goto(STUDIO, wait_until="domcontentloaded", timeout=45_000)
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:  # noqa: BLE001
                pass
            page.wait_for_timeout(2500)
            if "/login" in page.url:
                return 1

            if not choose_sfv(page, report):
                (outdir / "report.json").write_text(json.dumps(report, indent=2), "utf-8")
                return 1
            i2v.select_1080p(page, report)
            # upload the charsheet as the start frame
            file_inputs = page.locator("input[type=file]")
            if file_inputs.count() == 0:
                report["upload"] = "no input[type=file]"
                i2v.dump_controls(page, report, "sfv_upload_state")
                (outdir / "report.json").write_text(json.dumps(report, indent=2), "utf-8")
                return 1
            file_inputs.first.set_input_files(str(sheet))
            try:
                file_inputs.first.evaluate("(el) => el.dispatchEvent(new Event('change', {bubbles:true}))")
            except Exception:  # noqa: BLE001
                pass
            page.wait_for_timeout(3500)
            report["upload"] = f"set {sheet.name}"

            # prompt (NO dialogue — description only)
            box = page.locator("textarea[placeholder*='Describe your video']").first
            if box.count():
                box.fill(prompt)
                report["prompt_filled"] = True

            page.screenshot(path=str(outdir / "sfv-preclick.png"))
            if dry:
                report["dry_done"] = True
                (outdir / "report.json").write_text(json.dumps(report, indent=2), "utf-8")
                return 0

            # capture baseline jobs BEFORE Generate, so we only ever take a job created by THIS click
            try:
                baseline = page.evaluate("""async () => {
                    const r = await fetch('/api/v1/jobs?scope=recent&limit=30');
                    const j = await r.json();
                    return Array.isArray(j) ? j : (j.jobs || j.data || []);
                }""")
                baseline_ids = {str(j.get("id")) for j in (baseline or []) if j.get("id")}
                report["baseline_jobs"] = len(baseline_ids)
            except Exception as exc:  # noqa: BLE001
                baseline_ids = set()
                report["baseline_err"] = str(exc)[:100]

            gen_btn = page.get_by_role("button", name="Generate", exact=True).first
            report["generate_disabled"] = gen_btn.is_disabled()
            gen_btn.click()
            report["generate_clicked_at"] = datetime.now(UTC).isoformat()

            # poll for a NEW video job (id not in baseline) that is done
            deadline = time.time() + MAX_WAIT_S
            meta = {}
            while time.time() < deadline:
                try:
                    jobs = page.evaluate("""async () => {
                        const r = await fetch('/api/v1/jobs?scope=recent&limit=30');
                        const j = await r.json();
                        return Array.isArray(j) ? j : (j.jobs || j.data || []);
                    }""")
                except Exception:  # noqa: BLE001
                    jobs = []
                done = [j for j in jobs
                        if str(j.get("status") or "").lower() in ("done", "complete", "ready", "success")
                        and str(j.get("mode") or "").lower() in ("sfv", "i2v", "t2v", "video", "r2v", "extend")
                        and str(j.get("id")) not in baseline_ids]
                if done:
                    meta = done[0]
                    report["job_done"] = True
                    report["job_meta"] = {k: meta.get(k) for k in ("id", "status", "mode", "model", "width", "height", "size_bytes") if meta.get(k) is not None}
                    break
                time.sleep(4)
            else:
                report["timed_out"] = True

            if report.get("job_done"):
                jid = str(meta.get("id"))
                cands = [meta.get(k) for k in ("download_url", "video_url", "url") if meta.get(k)]
                if jid:
                    cands.append(f"/api/v1/jobs/{jid}/download")
                for u in cands:
                    full = u if u.startswith("http") else chk.ORIGIN + u
                    try:
                        resp = page.context.request.get(full, timeout=300_000)
                        if resp.status == 200 and len(resp.body()) > 100_000:
                            dest = outdir / f"scene-{datetime.now(UTC).strftime('%H%M%S')}.mp4"
                            dest.write_bytes(resp.body())
                            report["video_saved"] = str(dest)
                            report["video_size_final"] = len(resp.body())
                            break
                    except Exception as exc:  # noqa: BLE001
                        report["download_error"] = f"{u[:60]} -> {str(exc)[:120]}"
        finally:
            browser.close()

    (outdir / "report.json").write_text(json.dumps(report, indent=2), "utf-8")
    print(json.dumps({"ok": bool(report.get("video_saved")), "video_saved": report.get("video_saved"),
                      "mode_chosen": report.get("mode_chosen"), "upload": report.get("upload")}, indent=2))
    return 0 if report.get("video_saved") else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--sheet", required=True)
    ap.add_argument("--prompt", default="")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args(sys.argv[1:])
    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    return run(outdir, Path(a.sheet), a.prompt, a.dry)


if __name__ == "__main__":
    sys.exit(main())
