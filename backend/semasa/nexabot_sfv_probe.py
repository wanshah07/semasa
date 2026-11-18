# ruff: noqa: E501
"""Probe Nexabot Video Generator sfv (Start Frame) mode — how to upload the charsheet as the first frame.

Read-only: switch to "Start Frame" mode, dump the upload controls (file input, image preview), record the POST body
shape (has media/image), NEVER press Generate. Names only, no secrets.

Run on GitHub with NEXABOT_STORAGE_STATE_B64, from backend:
  python -m semasa.nexabot_sfv_probe OUTDIR
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from . import nexabot_check as chk
from . import nexabot_generate as gen

VID_URL = chk.ORIGIN + "/video-generator"


def dump(page):
    return page.evaluate("""() => {
        const els = [...document.querySelectorAll('button, textarea, select, input, [role=button], [role=option], [role=menuitem]')];
        return els.map((e, i) => ({
            i, tag: e.tagName, role: e.getAttribute('role') || '',
            name: (e.innerText || e.getAttribute('aria-label') || e.placeholder || '').trim().slice(0, 70),
            disabled: e.disabled === true, haspopup: e.getAttribute('aria-haspopup') || '',
            type: e.type || '', placeholder: (e.placeholder || '').slice(0, 50),
        }));
    }""")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    a = ap.parse_args(sys.argv[1:])
    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    state = gen.storage_state()
    if not state:
        return 2
    from playwright.sync_api import sync_playwright

    report = {"started": datetime.now(UTC).isoformat()}
    with sync_playwright() as pw:
        browser = chk.launch_browser(pw)
        try:
            ctx = browser.new_context(storage_state=state, locale="ms-MY", timezone_id="Asia/Kuala_Lumpur")
            page = ctx.new_page()
            page.goto(VID_URL, wait_until="domcontentloaded", timeout=45_000)
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:  # noqa: BLE001
                pass
            page.wait_for_timeout(2500)

            # the mode dropdown is the button with haspopup=menu near the top of the composer
            # (named "Text to Video" by default)
            mode_btn = page.get_by_role("button", name="Text to Video").first
            if not mode_btn.count():
                mode_btn = page.get_by_role("button", name="Text to Video", exact=False).first
            report["mode_btn_found"] = mode_btn.count() > 0
            if mode_btn.count():
                mode_btn.click()
                page.wait_for_timeout(700)
                page.screenshot(path=str(outdir / "mode-menu-open.png"))
                # list menu items
                items = page.evaluate("""() => {
                    const els = [...document.querySelectorAll('[role=menuitem], [role=option], li, [class*=menu] button, [class*=dropdown] button')];
                    return els.map(e => (e.innerText||'').trim()).filter(t => t && t.length < 40);
                }""")
                report["mode_menu_items"] = items
                # click Start Frame
                sf = page.get_by_text("Start Frame", exact=False).first
                if sf.count():
                    sf.click()
                    page.wait_for_timeout(1000)
                    report["sf_selected"] = True
                else:
                    report["sf_selected"] = False
                page.screenshot(path=str(outdir / "sf-selected.png"))

            report["controls_after"] = dump(page)
            report["body_after"] = page.evaluate("() => (document.body.innerText||'').slice(0,1500)")
            # look for file inputs and any upload/dropzone
            report["file_inputs"] = page.evaluate("""() => {
                const ins = [...document.querySelectorAll('input[type=file]')].map(i => ({accept: i.accept||'', name: i.name||''}));
                return ins;
            }""")
            report["dropzone_text"] = page.evaluate("""() => {
                const t = [...document.querySelectorAll('[class*=drop],[class*=upload],[class*=attach]')].map(e => (e.innerText||'').trim().slice(0,80)).filter(Boolean);
                return t.slice(0,5);
            }""")
        finally:
            browser.close()

    (outdir / "report.json").write_text(json.dumps(report, indent=2), "utf-8")
    print(json.dumps({"ok": True, "sf_selected": report.get("sf_selected"),
                      "file_inputs": len(report.get("file_inputs", []))}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
