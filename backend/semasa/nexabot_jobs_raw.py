"""Dump the RAW /api/v1/jobs response (multiple scopes) to see the real structure and where queued/processing jobs live."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from . import nexabot_check as chk
from . import nexabot_generate as gen

VID_URL = chk.ORIGIN + "/video-generator"


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
            except Exception:
                pass
            page.wait_for_timeout(2500)
            report["url"] = page.url

            # try several endpoints, capture raw status + body shape
            for label, path in [
                ("recent", "/api/v1/jobs?scope=recent&limit=30"),
                ("noscope", "/api/v1/jobs?limit=50"),
                ("all", "/api/v1/jobs"),
            ]:
                try:
                    raw = page.evaluate("""async (p) => {
                        const r = await fetch(p);
                        const txt = await r.text();
                        return {http: r.status, body: txt.slice(0, 4000)};
                    }""", path)
                    report[label] = raw
                except Exception as exc:
                    report[label] = {"err": str(exc)[:120]}

            # also try the dashboard stats endpoint
            for label, path in [
                ("stats", "/api/v1/stats"),
                ("usage", "/api/v1/usage"),
                ("me", "/api/v1/me"),
                ("account", "/api/v1/account"),
            ]:
                try:
                    raw = page.evaluate("""async (p) => {
                        const r = await fetch(p);
                        const txt = await r.text();
                        return {http: r.status, body: txt.slice(0, 2000)};
                    }""", path)
                    report[label] = raw
                except Exception as exc:
                    report[label] = {"err": str(exc)[:120]}
        finally:
            browser.close()

    (outdir / "report.json").write_text(json.dumps(report, indent=2), "utf-8")
    print(json.dumps({"ok": True}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
