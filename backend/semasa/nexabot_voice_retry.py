"""Nexabot voice retry — regenerate only the missing lines (1 and 4), with retries.

Reuses nexabot_voice_film.one_line; runs each missing line up to 3 attempts.
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
from .nexabot_voice_film import one_line

MISSING = [
    (1, "Hana", "Sulafat", "Eh, logo halal kat paket ni warna hijau. Bukan sepatutnya hitam ke?"),
    (4, "Hana", "Sulafat", "Pemegang sertifikat boleh mencetak logo sesuai warna kemasan."),
]


def run(outdir: Path) -> int:
    state = gen.storage_state()
    if not state:
        return 2
    from playwright.sync_api import sync_playwright

    report = {"started": datetime.now(UTC).isoformat()}
    saved = []
    with sync_playwright() as pw:
        browser = chk.launch_browser(pw)
        try:
            ctx = browser.new_context(storage_state=state, locale="ms-MY", timezone_id="Asia/Kuala_Lumpur",
                                      viewport={"width": 1366, "height": 900}, accept_downloads=True)
            page = ctx.new_page()
            for (idx, who, voice, text) in MISSING:
                got = None
                for attempt in range(1, 4):
                    report.setdefault(f"line{idx}", {})["attempt"] = attempt
                    got = one_line(page, outdir, who, voice, text, idx, report)
                    if got:
                        saved.append(got)
                        break
                    time.sleep(5)
                if not got:
                    report["failed_line"] = idx
        finally:
            browser.close()

    (outdir / "report.json").write_text(json.dumps(report, indent=2, default=str), "utf-8")
    print(json.dumps({"ok": len(saved) == len(MISSING), "saved": len(saved), "total": len(MISSING)}, indent=2))
    return 0 if len(saved) == len(MISSING) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    a = ap.parse_args(sys.argv[1:])
    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    return run(outdir)


if __name__ == "__main__":
    sys.exit(main())
