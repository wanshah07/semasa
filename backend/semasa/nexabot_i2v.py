"""Nexabot i2v — animate one comic panel into a short clip (Phase B, comic film step 1).

Drives the Creator Studio with the saved session login: opens the studio, switches the mode dropdown to
"Ingredients to Video", uploads ONE panel image, keeps the prompt (optional), picks Unlimited, presses Generate,
polls the job and downloads the MP4. One panel per run (the film is 4 panels -> 4 clips -> concatenated).

Because the i2v UI was not yet seen (Phase A's probe only opened the dropdown, never chose a mode), every step
records the controls it finds into report.json, so a difference in the UI is visible in the artifact instead of a
mysterious timeout. Run on the GitHub runner (NEXABOT_STORAGE_STATE_B64), from backend:

  python -m semasa.nexabot_i2v OUTDIR --panel path/to/panel.png --prompt "..."

Env: NEXABOT_STORAGE_STATE_B64.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from . import nexabot_check as chk
from . import nexabot_generate as gen

STUDIO = chk.STUDIO_URL
MODE_BUTTON = "Text to Video"
MODE_I2V = "Ingredients to Video"
MAX_WAIT_S = 15 * 60
POLL_S = 4


def dump_controls(page, report: dict, label: str) -> None:
    try:
        controls = page.evaluate("""() => {
            const pick = (sel) => [...document.querySelectorAll(sel)].map(e => ({
                tag: e.tagName, type: e.getAttribute('type') || '', name: (e.getAttribute('aria-label')||e.getAttribute('placeholder')||'').slice(0,60),
                accept: e.getAttribute('accept') || '', text: (e.innerText||'').trim().slice(0,50),
                disabled: !!e.disabled
            }));
            return {
                buttons: [...document.querySelectorAll('button')].map(b=>(b.innerText||'').trim().slice(0,40)).filter(Boolean),
                inputs: pick('input'),
                textareas: pick('textarea'),
                options: [...document.querySelectorAll('[role=option], [role=menuitem]')].map(o=>(o.innerText||'').trim().slice(0,40)).filter(Boolean)
            };
        }""")
        report[label] = controls
    except Exception as exc:  # noqa: BLE001
        report[label] = f"dump failed: {str(exc)[:120]}"


def choose_mode(page, report: dict) -> bool:
    # open the mode dropdown
    btn = page.get_by_role("button", name=MODE_BUTTON).first
    btn.click()
    page.wait_for_timeout(800)
    opt = page.get_by_role("option", name=MODE_I2V).first
    if opt.is_visible():
        opt.click()
        page.wait_for_timeout(800)
        report["mode_chosen"] = MODE_I2V
        return True
    # the menu items may be [role=menuitem] or plain text
    items = page.locator("[role=option], [role=menuitem]")
    for i in range(items.count()):
        if MODE_I2V in (items.nth(i).inner_text() or ""):
            items.nth(i).click()
            page.wait_for_timeout(800)
            report["mode_chosen"] = MODE_I2V
            return True
    report["mode_chosen"] = "NOT FOUND"
    dump_controls(page, report, "mode_dropdown_state")
    return False


def upload_panel(page, panel: Path, report: dict) -> bool:
    # an i2v UI normally has an <input type=file> (a dropzone wraps a hidden one)
    file_inputs = page.locator("input[type=file]")
    if file_inputs.count() == 0:
        report["upload"] = "no input[type=file] found"
        dump_controls(page, report, "upload_state")
        return False
    file_inputs.first.set_input_files(str(panel))
    page.wait_for_timeout(2500)
    report["upload"] = f"set {panel.name}"
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--panel", required=True)
    ap.add_argument("--prompt", default="")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args(sys.argv[1:])
    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    panel = Path(a.panel)

    state = gen.storage_state()
    if not state:
        print("nexabot: no saved login (NEXABOT_STORAGE_STATE_B64 empty).")
        return 2
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is not installed.")
        return 2

    report: dict = {"started": datetime.now(UTC).isoformat(), "panel": panel.name, "dry": a.dry,
                    "events": [], "video_saved": None, "video_url": None, "job_done": False}

    with sync_playwright() as pw:
        browser = chk.launch_browser(pw)
        try:
            ctx = browser.new_context(storage_state=state, locale="en-MY", timezone_id="Asia/Kuala_Lumpur",
                                      viewport={"width": 1366, "height": 900}, accept_downloads=True)
            page = ctx.new_page()

            def on_response(resp):
                req = resp.request
                ctype = resp.headers.get("content-type", "")
                row = {"method": req.method, "url": req.url, "status": resp.status, "ctype": ctype}
                try:
                    row["size"] = len(resp.body())
                except Exception:  # noqa: BLE001
                    row["size"] = None
                if req.method == "GET" and gen._is_video(ctype, req.url) and not report.get("video_url"):
                    report["video_url"] = req.url
                report["events"].append(row)

            page.on("response", on_response)
            page.goto(STUDIO, wait_until="domcontentloaded", timeout=45_000)
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:  # noqa: BLE001
                pass
            page.wait_for_timeout(2500)
            report["final_url"] = page.url
            if "/login" in page.url:
                print("nexabot: LOGIN WALL — record the login again.")
                return 1

            if not choose_mode(page, report):
                (outdir / "report.json").write_text(json.dumps(report, indent=2), "utf-8")
                print(json.dumps({"ok": False, "reason": "could not choose i2v mode", "report": report}, indent=2))
                return 1
            if not upload_panel(page, panel, report):
                (outdir / "report.json").write_text(json.dumps(report, indent=2), "utf-8")
                print(json.dumps({"ok": False, "reason": "could not upload panel", "report": report}, indent=2))
                return 1

            # optional prompt
            if a.prompt:
                box = page.locator("textarea[placeholder*='Describe your video']").first
                if box.count():
                    box.fill(a.prompt)
                    report["prompt_filled"] = True

            if a.dry:
                report["dry_done"] = True
                (outdir / "report.json").write_text(json.dumps(report, indent=2), "utf-8")
                print(json.dumps({"ok": True, "dry": True}, indent=2))
                return 0

            # Generate
            gen_btn = page.get_by_role("button", name="Generate", exact=True).first
            report["generate_disabled"] = gen_btn.is_disabled()
            gen_btn.click()
            report["generate_clicked_at"] = datetime.now(UTC).isoformat()

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
                done = [j for j in jobs if j.get("status") in ("done", "complete", "ready", "success")]
                if done:
                    report["job_done"] = True
                    report["job_meta"] = {k: done[0].get(k) for k in ("id", "status", "mode", "model", "width", "height", "size_bytes") if done[0].get(k) is not None}
                    break
                time.sleep(POLL_S)
            else:
                report["timed_out"] = True

            # download the full MP4 (plain GET, no Range)
            if report.get("job_done") and report.get("video_url"):
                import requests
                try:
                    r = requests.get(report["video_url"], timeout=300, stream=True)
                    if r.status_code == 200:
                        dest = outdir / f"panel-{datetime.now(UTC).strftime('%H%M%S')}.mp4"
                        with open(dest, "wb") as fh:
                            for chunk in r.iter_content(1 << 20):
                                fh.write(chunk)
                        report["video_saved"] = str(dest)
                        report["video_size_final"] = dest.stat().st_size
                except Exception as exc:  # noqa: BLE001
                    report["download_error"] = str(exc)[:200]
            page.wait_for_timeout(2000)
        finally:
            browser.close()

    (outdir / "report.json").write_text(json.dumps(report, indent=2), "utf-8")
    print(json.dumps({"ok": report.get("job_done", False), "video_saved": report.get("video_saved"),
                      "video_size_final": report.get("video_size_final"), "mode_chosen": report.get("mode_chosen"),
                      "upload": report.get("upload")}, indent=2))
    return 0 if report.get("video_saved") else 1


if __name__ == "__main__":
    sys.exit(main())
