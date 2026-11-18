"""Nexabot Voice Generator — batch: generate one test line across several voices in ONE session, download each.

Used to classify which of the 30 voices are female vs male (by pitch) for Hana/Hassan. Drives the studio UI,
one Generate Voice click per voice, downloads each result.

Run on GitHub with NEXABOT_STORAGE_STATE_B64, from backend:
  python -m semasa.nexabot_voice_batch OUTDIR --text "..." --voices Achernar,Algieba,Aoede
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

VOICE_URL = chk.ORIGIN + "/voice-generator"
MAX_WAIT_S = 120


def _is_audio(ctype: str, url: str) -> bool:
    c = (ctype or "").lower()
    return "audio" in c or "mpeg" in c or "wav" in c or url.lower().endswith((".mp3", ".wav", ".m4a", ".ogg"))


def run(outdir: Path, text: str, voices: list[str]) -> int:
    state = gen.storage_state()
    if not state:
        print("nexabot: no saved login.")
        return 2
    from playwright.sync_api import sync_playwright

    report: dict = {"started": datetime.now(UTC).isoformat(), "text": text,
                    "voices": voices, "results": []}

    with sync_playwright() as pw:
        browser = chk.launch_browser(pw)
        try:
            ctx = browser.new_context(storage_state=state, locale="ms-MY", timezone_id="Asia/Kuala_Lumpur",
                                      viewport={"width": 1366, "height": 900}, accept_downloads=True)
            page = ctx.new_page()
            audio_urls: dict[str, str] = {}

            def on_response(resp):
                req = resp.request
                ctype = resp.headers.get("content-type", "")
                if req.method == "GET" and _is_audio(ctype, req.url):
                    audio_urls.setdefault(req.url, ctype)

            page.on("response", on_response)
            page.goto(VOICE_URL, wait_until="domcontentloaded", timeout=45_000)
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:  # noqa: BLE001
                pass
            page.wait_for_timeout(2500)
            if "/login" in page.url:
                print("nexabot: LOGIN WALL.")
                return 1

            # the script textarea
            box = page.locator("textarea").first
            box.wait_for(state="visible", timeout=30_000)

            for voice in voices:
                before = set(audio_urls.keys())
                # select voice
                page.get_by_role("button", name="Achernar").first.click()
                page.wait_for_timeout(600)
                page.get_by_role("button", name=voice, exact=True).first.click()
                page.wait_for_timeout(500)
                # fill + generate
                box.fill(text)
                page.wait_for_timeout(300)
                btn = page.get_by_role("button", name="Generate Voice", exact=True).first
                # wait enabled
                t0 = time.time()
                while time.time() - t0 < 20:
                    try:
                        if not btn.is_disabled():
                            break
                    except Exception:  # noqa: BLE001
                        pass
                    time.sleep(1)
                btn.click()
                # wait for a NEW audio url
                t1 = time.time()
                new_url = None
                while time.time() - t1 < MAX_WAIT_S:
                    new = [u for u in audio_urls.keys() if u not in before]
                    if new:
                        new_url = new[0]
                        break
                    time.sleep(2)
                if new_url:
                    full = new_url if new_url.startswith("http") else chk.ORIGIN + new_url
                    try:
                        resp = page.context.request.get(full, timeout=120_000)
                        if resp.status == 200 and len(resp.body()) > 500:
                            safe = "".join(c for c in voice if c.isalnum())
                            dest = outdir / f"v-{safe}.wav"
                            dest.write_bytes(resp.body())
                            report["results"].append({"voice": voice, "saved": str(dest),
                                                      "bytes": len(resp.body())})
                        else:
                            report["results"].append({"voice": voice, "error": f"status {resp.status}"})
                    except Exception as exc:  # noqa: BLE001
                        report["results"].append({"voice": voice, "error": str(exc)[:100]})
                else:
                    report["results"].append({"voice": voice, "error": "no audio url in 120s"})
                time.sleep(2)
        finally:
            browser.close()

    (outdir / "report.json").write_text(json.dumps(report, indent=2), "utf-8")
    ok = sum(1 for r in report["results"] if r.get("saved"))
    print(json.dumps({"ok": ok == len(voices), "generated": ok, "total": len(voices)}, indent=2))
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--text", required=True)
    ap.add_argument("--voices", required=True)
    a = ap.parse_args(sys.argv[1:])
    voices = [v.strip() for v in a.voices.split(",") if v.strip()]
    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    return run(outdir, a.text, voices)


if __name__ == "__main__":
    sys.exit(main())
