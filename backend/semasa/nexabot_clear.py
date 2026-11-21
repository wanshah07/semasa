# ruff: noqa: E501
"""Nexabot clear — padam job lama yang stuck dari panel Results (CANCEL ALL + DELETE ALL).

Server Nexabot boleh degrade dan tinggalkan job stuck yang tak di-expose ke /api/v1/jobs
(list kosong tapi dashboard tunjuk PROCESSING). Job stuck ni menyumbat longgokan server.
Skrip ini buka studio, klik CANCEL ALL (henti semua job aktif) kemudian DELETE ALL (buang
hasil dari panel), supaya longgokan bersih sebelum render episod baru.

Run on GitHub (NEXABOT_STORAGE_STATE_B64), from backend:
  python -m semasa.nexabot_clear OUTDIR
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    a = ap.parse_args(sys.argv[1:])
    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    state = gen.storage_state()
    if not state:
        print("nexabot: no saved login (NEXABOT_STORAGE_STATE_B64 empty or not JSON).")
        return 2

    from playwright.sync_api import sync_playwright

    report: dict = {"started": datetime.now(UTC).isoformat(), "clicks": []}

    def try_click(name: str) -> dict:
        btn = None
        for _ in range(3):
            try:
                btn = sync_page.get_by_role("button", name=name, exact=False).first
                if btn.count() and btn.is_visible():
                    btn.click()
                    sync_page.wait_for_timeout(1200)
                    return {"name": name, "clicked": True}
            except Exception as exc:  # noqa: BLE001
                pass
            time.sleep(1)
        return {"name": name, "clicked": False}

    with sync_playwright() as pw:
        browser = chk.launch_browser(pw)
        try:
            ctx = browser.new_context(storage_state=state, locale="ms-MY",
                                      timezone_id="Asia/Kuala_Lumpur", viewport={"width": 1366, "height": 900})
            sync_page = ctx.new_page()
            sync_page.goto(chk.STUDIO_URL, wait_until="domcontentloaded", timeout=45_000)
            try:
                sync_page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:  # noqa: BLE001
                pass
            sync_page.wait_for_timeout(2500)
            report["url"] = sync_page.url
            if "/login" in sync_page.url:
                print("nexabot: LOGIN WALL.")
                return 1

            # capture the results area text before, to see how many jobs are listed
            try:
                report["results_before"] = sync_page.evaluate(
                    "() => { const el = document.querySelector('[class*=result], [data-results]'); "
                    "return el ? el.innerText.slice(0, 800) : null; }")
            except Exception:  # noqa: BLE001
                report["results_before"] = None

            report["clicks"].append(try_click("Cancel all"))
            time.sleep(1.0)
            report["clicks"].append(try_click("Delete all"))
            time.sleep(1.0)

            # confirm any dialog (Delete All may ask "are you sure")
            for _ in range(3):
                try:
                    confirm = sync_page.get_by_role("button", name="Delete", exact=False).first
                    if confirm.count() and confirm.is_visible():
                        confirm.click()
                        sync_page.wait_for_timeout(800)
                        break
                except Exception:  # noqa: BLE001
                    break

            sync_page.screenshot(path=str(outdir / "after-clear.png"))
            try:
                report["results_after"] = sync_page.evaluate(
                    "() => { const el = document.querySelector('[class*=result], [data-results]'); "
                    "return el ? el.innerText.slice(0, 800) : null; }")
            except Exception:  # noqa: BLE001
                report["results_after"] = None
        finally:
            browser.close()

    (outdir / "report.json").write_text(json.dumps(report, indent=2, default=str), "utf-8")
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
