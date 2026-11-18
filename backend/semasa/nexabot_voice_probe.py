"""Probe Nexabot Voice Generator UI (read-only) using the saved Unlimited session.

Reports: controls (voices, language, speed/pitch, generate), MIDI-style names — NEVER values/secrets. No Generate click.
Run on GitHub with NEXABOT_STORAGE_STATE_B64, from backend:
  python -m semasa.nexabot_voice_probe OUTDIR
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from . import nexabot_check as chk
from . import nexabot_generate as gen
from . import nexabot_probe as pr

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

    report = {"started": datetime.now(UTC).isoformat(), "url": VOICE_URL, "events": [], "blocked": []}
    with sync_playwright() as pw:
        browser = chk.launch_browser(pw)
        try:
            ctx = browser.new_context(storage_state=state, locale="ms-MY", timezone_id="Asia/Kuala_Lumpur")
            ctx.route("**/*", pr.guard_route(report["blocked"]))  # abort every write
            page = ctx.new_page()
            page.on("response", lambda r: report["events"].append(
                {"method": r.request.method, "url": pr.clean_path(r.url), "status": r.status}))
            page.goto(VOICE_URL, wait_until="domcontentloaded", timeout=45_000)
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:  # noqa: BLE001
                pass
            page.wait_for_timeout(2500)
            report["final_url"] = page.url
            report["title"] = page.title()
            # dump controls (roles, names, options) but no values
            body = pr.probe(page, outdir, report["events"], report["blocked"])
            for k, v in body.items():
                report[k] = v
        finally:
            browser.close()
    (outdir / "report.json").write_text(json.dumps(report, indent=2), "utf-8")
    print(json.dumps({"ok": True, "final_url": report.get("final_url"),
                      "controls": len(report.get("elements", []))}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
