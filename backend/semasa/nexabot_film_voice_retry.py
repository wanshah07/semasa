"""Nexabot film voice — retry the missing lines (1,3,5) with a longer wait (5 min) and one retry each."""
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
MAX_WAIT_S = 300

VOICES = {"Hana": "Sulafat", "Hassan": "Aoede"}
LINES = [
    ("Hana", "Eh, logo halal kat paket ni warna hijau. Bukan sepatutnya hitam ke?"),
    ("Hana", "Tak semestinya. Warna bukan penentu."),
    ("Hassan", "Mana tulis tu?"),
]


def _is_audio(ctype, url):
    c = (ctype or "").lower()
    return "audio" in c or "mpeg" in c or "wav" in c or url.lower().endswith((".mp3", ".wav", ".m4a", ".ogg"))


def run(outdir: Path) -> int:
    state = gen.storage_state()
    if not state:
        return 2
    from playwright.sync_api import sync_playwright
    report = {"started": datetime.now(UTC).isoformat(), "lines": []}
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
                return 1
            box = page.locator("textarea").first
            box.wait_for(state="visible", timeout=30_000)

            for i, (who, text) in enumerate(LINES, 1):
                voice = VOICES[who]
                # retry up to 2 times per line
                got = False
                for attempt in (1, 2):
                    before = set(audio_urls.keys())
                    vbtn = page.evaluate("""() => {
                        const bs = [...document.querySelectorAll('button')];
                        for (const b of bs) {
                            const n = (b.innerText||'').trim();
                            if (b.getAttribute('aria-haspopup') === 'menu'
                                && n !== 'Natural TTS' && n !== 'ElevenLabs'
                                && !/Choose payment|Unlimited|Clone Voice/i.test(n)
                                && n.length < 20) return n;
                        }
                        return '';
                    }""")
                    if vbtn:
                        page.get_by_role("button", name=vbtn, exact=True).first.click()
                    else:
                        page.get_by_role("button", name="Achernar").first.click()
                    page.wait_for_timeout(600)
                    page.get_by_role("button", name=voice, exact=True).first.click()
                    page.wait_for_timeout(500)
                    box.fill(text)
                    page.wait_for_timeout(300)
                    btn = page.get_by_role("button", name="Generate Voice", exact=True).first
                    t0 = time.time()
                    while time.time() - t0 < 20:
                        try:
                            if not btn.is_disabled():
                                break
                        except Exception:  # noqa: BLE001
                            pass
                        time.sleep(1)
                    btn.click()
                    new_url = None
                    t1 = time.time()
                    while time.time() - t1 < MAX_WAIT_S:
                        new = [u for u in audio_urls.keys() if u not in before]
                        if new:
                            new_url = new[0]
                            break
                        time.sleep(3)
                    if new_url:
                        full = new_url if new_url.startswith("http") else chk.ORIGIN + new_url
                        resp = page.context.request.get(full, timeout=120_000)
                        if resp.status == 200 and len(resp.body()) > 500:
                            dest = outdir / f"retry{i:02d}-{who}.wav"
                            dest.write_bytes(resp.body())
                            report["lines"].append({"i": i, "who": who, "attempt": attempt,
                                                    "saved": str(dest), "bytes": len(resp.body())})
                            got = True
                            break
                    time.sleep(2)
                if not got:
                    report["lines"].append({"i": i, "who": who, "error": "no audio after 2 attempts"})
        finally:
            browser.close()
    (outdir / "report.json").write_text(json.dumps(report, indent=2), "utf-8")
    ok = sum(1 for r in report["lines"] if r.get("saved"))
    print(json.dumps({"ok": ok == len(LINES), "generated": ok, "total": len(LINES)}, indent=2))
    return 0 if ok == len(LINES) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    a = ap.parse_args(sys.argv[1:])
    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    return run(outdir)


if __name__ == "__main__":
    sys.exit(main())
