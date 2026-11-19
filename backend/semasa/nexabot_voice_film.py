"""Nexabot voice film — generate all 6 dialogue lines SEQUENTIALLY in one run (fresh page per line).

Reuses the proven nexabot_voice_line logic (fresh page + diff DOM audio src, never the old result).
Sequential (not parallel) avoids the race where concurrent runs captured the same cached audio.

Casting: Hana = Sulafat (female), Hassan = Aoede (male).
Lines 3 & 4 use Indonesian spelling — Nexabot's Sulafat voice rejects pure-Malay ("Tak semestinya",
"Pemegang sijil...") with "text language not supported"; these spellings are the ones the voice accepted.

Run on GitHub with NEXABOT_STORAGE_STATE_B64, from backend:
  python -m semasa.nexabot_voice_film OUTDIR
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
MAX_WAIT_S = 5 * 60
LATE_WAIT_S = 8 * 60

# (who, voice, text) — 6 lines in film order, ALL in consistent Indonesian (the Nexabot voices are Indonesian).
# Consistent spelling = the voice sounds natural and consistent; subtitles stay Malay for the audience.
LINES = [
    ("Hana", "Sulafat", "Eh, logo halal di paket ini warnanya hijau. Bukankah seharusnya hitam?"),
    ("Hassan", "Aoede", "Jangan-jangan logo palsu?"),
    ("Hana", "Sulafat", "Belum tentu. Warna bukan penentu."),
    ("Hana", "Sulafat", "Pemegang sertifikat boleh mencetak logo sesuai warna kemasan."),
    ("Hassan", "Aoede", "Mana tulisnya?"),
    ("Hana", "Sulafat", "MPPHM Domestik 2020, Klausa 40 ayat 2."),
]


def _is_audio(ctype, url):
    c = (ctype or "").lower()
    return "audio" in c or "mpeg" in c or "wav" in c or url.lower().endswith((".mp3", ".wav", ".m4a", ".ogg"))


def one_line(page, outdir, who, voice, text, idx, report):
    report[f"line{idx}"] = {"who": who, "voice": voice, "text": text}
    seen_audio: set[str] = set()

    def on_response(resp):
        req = resp.request
        if req.method == "GET" and _is_audio(resp.headers.get("content-type", ""), req.url):
            seen_audio.add(req.url)

    page.on("response", on_response)
    page.goto(VOICE_URL, wait_until="domcontentloaded", timeout=45_000)
    try:
        page.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:  # noqa: BLE001
        pass
    page.wait_for_timeout(2500)
    if "/login" in page.url:
        return None

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
    page.wait_for_timeout(700)
    page.get_by_role("button", name=voice, exact=True).first.click()
    page.wait_for_timeout(600)

    box = page.locator("textarea").first
    box.wait_for(state="visible", timeout=30_000)
    box.fill(text)
    page.wait_for_timeout(400)

    before = set(seen_audio)
    before_dom = page.evaluate("""() =>
        [...document.querySelectorAll('audio, video')].map(x => x.src).filter(Boolean)
    """)
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
    report[f"line{idx}"]["clicked_at"] = datetime.now(UTC).isoformat()

    new_url = None
    deadline = time.time() + MAX_WAIT_S + LATE_WAIT_S
    while time.time() < deadline:
        new_net = [u for u in seen_audio if u not in before]
        if new_net:
            new_url = new_net[-1]
            report[f"line{idx}"]["via"] = "network"
            break
        try:
            after_dom = page.evaluate("""() =>
                [...document.querySelectorAll('audio, video')].map(x => x.src).filter(Boolean)
            """)
            new_dom = [s for s in after_dom if s not in before_dom]
            if new_dom:
                new_url = new_dom[-1]
                report[f"line{idx}"]["via"] = "dom_new"
                break
        except Exception:  # noqa: BLE001
            pass
        time.sleep(3)

    if not new_url:
        report[f"line{idx}"]["no_audio"] = True
        return None

    full = new_url if new_url.startswith("http") else chk.ORIGIN + new_url
    try:
        resp = page.context.request.get(full, timeout=120_000)
        if resp.status == 200 and len(resp.body()) > 500:
            dest = outdir / f"line{idx:02d}-{who}.wav"
            dest.write_bytes(resp.body())
            report[f"line{idx}"]["saved"] = str(dest)
            report[f"line{idx}"]["bytes"] = len(resp.body())
            return str(dest)
    except Exception as exc:  # noqa: BLE001
        report[f"line{idx}"]["dl_error"] = str(exc)[:120]
    return None


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
            for i, (who, voice, text) in enumerate(LINES, 1):
                path = one_line(page, outdir, who, voice, text, i, report)
                if path:
                    saved.append(path)
                else:
                    report["error_line"] = i
                    # continue with remaining lines; do not abort the whole film
        finally:
            browser.close()

    (outdir / "report.json").write_text(json.dumps(report, indent=2, default=str), "utf-8")
    print(json.dumps({"ok": len(saved) == len(LINES), "saved": len(saved), "total": len(LINES)}, indent=2))
    return 0 if len(saved) == len(LINES) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    a = ap.parse_args(sys.argv[1:])
    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    return run(outdir)


if __name__ == "__main__":
    sys.exit(main())
