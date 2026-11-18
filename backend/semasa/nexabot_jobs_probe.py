"""Diagnose Nexabot job list: dump the raw /api/v1/jobs response (id, status, mode, created_at, download_url, video_url)
so the correct job-selection logic can be written. Read-only — never Generate.

Run on GitHub with NEXABOT_STORAGE_STATE_B64, from backend:
  python -m semasa.nexabot_jobs_probe OUTDIR
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

            report["jobs_recent"] = page.evaluate("""async () => {
                const r = await fetch('/api/v1/jobs?scope=recent&limit=30');
                if (!r.ok) return {http: r.status};
                const j = await r.json();
                const arr = Array.isArray(j) ? j : (j.jobs || j.data || []);
                return arr.map(x => ({
                    id: x.id, status: x.status, mode: x.mode,
                    created_at: x.created_at, finished_at: x.finished_at,
                    size_bytes: x.size_bytes, width: x.width, height: x.height,
                    download_url: x.download_url || null,
                    video_url: x.video_url || null,
                    url: x.url || null,
                }));
            }""")
        finally:
            browser.close()

    (outdir / "report.json").write_text(json.dumps(report, indent=2), "utf-8")
    jobs = report.get("jobs_recent") or []
    print(json.dumps({"ok": True, "jobs": len(jobs)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
