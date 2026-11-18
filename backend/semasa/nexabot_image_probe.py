"""Probe Nexabot Image Generator UI + the video generator's sfv/i2v mode controls (read-only).

Reports controls, model options, aspect ratio, and whether sfv (Start Frame) accepts an image upload. Never Generate.
Run on GitHub with NEXABOT_STORAGE_STATE_B64, from backend:
  python -m semasa.nexabot_image_probe OUTDIR
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from . import nexabot_check as chk
from . import nexabot_generate as gen

IMG_URL = chk.ORIGIN + "/image-generator"
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
        print("nexabot: no saved login.")
        return 2
    from playwright.sync_api import sync_playwright

    report = {"started": datetime.now(UTC).isoformat(), "image": {}, "video": {}}
    with sync_playwright() as pw:
        browser = chk.launch_browser(pw)
        try:
            ctx = browser.new_context(storage_state=state, locale="ms-MY", timezone_id="Asia/Kuala_Lumpur")
            page = ctx.new_page()

            # image generator
            page.goto(IMG_URL, wait_until="domcontentloaded", timeout=45_000)
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:  # noqa: BLE001
                pass
            page.wait_for_timeout(2500)
            report["image"]["url"] = page.url
            report["image"]["controls"] = dump(page)
            report["image"]["body"] = page.evaluate("() => (document.body.innerText||'').slice(0,2000)")
            page.screenshot(path=str(outdir / "image-generator.png"))

            # video generator
            page.goto(VID_URL, wait_until="domcontentloaded", timeout=45_000)
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:  # noqa: BLE001
                pass
            page.wait_for_timeout(2500)
            report["video"]["url"] = page.url
            report["video"]["controls"] = dump(page)
            report["video"]["body"] = page.evaluate("() => (document.body.innerText||'').slice(0,2500)")
            page.screenshot(path=str(outdir / "video-generator.png"))
        finally:
            browser.close()

    (outdir / "report.json").write_text(json.dumps(report, indent=2), "utf-8")
    print(json.dumps({"ok": True, "image_controls": len(report["image"]["controls"]),
                      "video_controls": len(report["video"]["controls"])}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
