# ruff: noqa: E501
"""Probe Nexabot Voice Generator with the ELEVENLABS engine selected (read-only).

Clicks the "Natural TTS" engine menu -> picks "ElevenLabs", then dumps the voice dropdown options and any new
controls (language, speed, pitch) that appear. Never presses Generate Voice. Names only, no secrets.

Run on GitHub with NEXABOT_STORAGE_STATE_B64, from backend:
  python -m semasa.nexabot_voice_probe2 OUTDIR
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from . import nexabot_check as chk
from . import nexabot_generate as gen

VOICE_URL = chk.ORIGIN + "/voice-generator"


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

    report = {"started": datetime.now(UTC).isoformat(), "url": VOICE_URL, "steps": []}
    with sync_playwright() as pw:
        browser = chk.launch_browser(pw)
        try:
            ctx = browser.new_context(storage_state=state, locale="ms-MY", timezone_id="Asia/Kuala_Lumpur")
            page = ctx.new_page()
            page.goto(VOICE_URL, wait_until="domcontentloaded", timeout=45_000)
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:  # noqa: BLE001
                pass
            page.wait_for_timeout(2500)
            report["final_url"] = page.url
            if "/login" in page.url:
                report["login_wall"] = True
                print("nexabot: LOGIN WALL")
                return 1

            def snapshot():
                return page.evaluate("""() => {
                    const els = [...document.querySelectorAll('button, textarea, select, input, [role=button], [role=menu], [role=option], [role=menuitem]')];
                    return els.map((e, i) => ({
                        i, tag: e.tagName, role: e.getAttribute('role') || '',
                        name: (e.innerText || e.getAttribute('aria-label') || e.placeholder || '').trim().slice(0, 80),
                        disabled: e.disabled === true,
                        haspopup: e.getAttribute('aria-haspopup') || '',
                        expanded: e.getAttribute('aria-expanded') || '',
                    }));
                }""")

            # 1. open the engine menu (button named "Natural TTS")
            eng_btn = page.get_by_role("button", name="Natural TTS").first
            eng_btn.click()
            page.wait_for_timeout(800)
            snapshot()
            # find a menu item named ElevenLabs
            item = page.get_by_role("menuitem", name="ElevenLabs").first
            if not item.count():
                item = page.get_by_text("ElevenLabs", exact=False).first
            report["steps"].append({"open_engine": "clicked Natural TTS",
                                    "elevenlabs_visible": item.count() > 0})
            if item.count():
                item.click()
                page.wait_for_timeout(1200)
            else:
                # try clicking by text in the panel
                page.get_by_text("ElevenLabs", exact=False).first.click()
                page.wait_for_timeout(1200)

            report["engine_selected"] = True
            page.screenshot(path=str(outdir / "11-elevenlabs-selected.png"))

            # 2. dump the voice dropdown (the "Achernar" menu) and any new controls
            snap = snapshot()
            # voice menu button: the one that is a button with haspopup=menu and is NOT Natural TTS/Clone/payment
            voice_btn = None
            for e in snap:
                if e["tag"] in ("BUTTON",) and e["haspopup"] == "menu" and e["name"] not in ("Natural TTS", "Choose payment mode", "ElevenLabs"):
                    voice_btn = e
                    break
            if voice_btn:
                page.get_by_role("button", name=voice_btn["name"]).first.click()
                page.wait_for_timeout(800)
                page.screenshot(path=str(outdir / "12-elevenlabs-voices.png"))
                voice_panel = page.evaluate("""() => {
                    const p = [...document.querySelectorAll('[role=menu], [role=listbox], [class*=menu], [class*=dropdown], [class*=list]')]
                        .map(x => (x.innerText||'').trim()).filter(t => t && t.length < 3000);
                    return p;
                }""")
                report["voice_panel"] = voice_panel
            else:
                report["voice_panel"] = None

            # 3. full control dump after ElevenLabs selected
            report["controls_after"] = snapshot()

        finally:
            browser.close()

    (outdir / "report.json").write_text(json.dumps(report, indent=2), "utf-8")
    print(json.dumps({"ok": True, "final_url": report.get("final_url"),
                      "controls_after": len(report.get("controls_after", []))}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
