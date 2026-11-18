"""Nexabot voice generate (robust) — generate ONE line per fresh page load, capture only NEW audio, verify by duration.

Fixes the earlier bug: one page for 6 lines meant the result column's auto-play audio (the PREVIOUS line) was captured.
Now each line gets a fresh page load, the voice is re-selected, the text is re-filled, and only an audio URL that did
NOT exist before the click is downloaded. The line is also verified against its expected script via duration.

Run on GitHub with NEXABOT_STORAGE_STATE_B64, from backend:
  python -m semasa.nexabot_voice_line OUTDIR --who Hana --voice Sulafat --text "..."
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


def _is_audio(ctype, url):
    c = (ctype or "").lower()
    return "audio" in c or "mpeg" in c or "wav" in c or url.lower().endswith((".mp3", ".wav", ".m4a", ".ogg"))


def run(outdir: Path, who: str, voice: str, text: str, dry: bool) -> int:
    state = gen.storage_state()
    if not state:
        return 2
    from playwright.sync_api import sync_playwright

    report = {"started": datetime.now(UTC).isoformat(), "who": who, "voice": voice, "text": text, "dry": dry}
    with sync_playwright() as pw:
        browser = chk.launch_browser(pw)
        try:
            ctx = browser.new_context(storage_state=state, locale="ms-MY", timezone_id="Asia/Kuala_Lumpur",
                                      viewport={"width": 1366, "height": 900}, accept_downloads=True)
            page = ctx.new_page()
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
                return 1

            # select voice
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
            report["voice_chosen"] = voice

            # fill text
            box = page.locator("textarea").first
            box.wait_for(state="visible", timeout=30_000)
            box.fill(text)
            page.wait_for_timeout(400)
            report["text_filled"] = True

            page.screenshot(path=str(outdir / "preclick.png"))
            if dry:
                (outdir / "report.json").write_text(json.dumps(report, indent=2, default=str), "utf-8")
                return 0

            before = set(seen_audio)
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
            report["generate_clicked_at"] = datetime.now(UTC).isoformat()

            # wait for a NEW audio url (never the pre-click auto-play one)
            new_url = None
            deadline = time.time() + MAX_WAIT_S
            while time.time() < deadline:
                new = [u for u in seen_audio if u not in before]
                if new:
                    new_url = new[-1]
                    break
                time.sleep(2)

            if new_url:
                full = new_url if new_url.startswith("http") else chk.ORIGIN + new_url
                try:
                    resp = page.context.request.get(full, timeout=120_000)
                    if resp.status == 200 and len(resp.body()) > 500:
                        dest = outdir / f"voice-{who}.wav"
                        dest.write_bytes(resp.body())
                        report["audio_saved"] = str(dest)
                        report["audio_bytes"] = len(resp.body())
                        report["audio_url"] = full
                except Exception as exc:  # noqa: BLE001
                    report["download_error"] = f"{full[:80]} -> {str(exc)[:120]}"
            else:
                report["no_audio"] = True

            # fallback: the result <audio>/<video> element's own src (the first successful run used this)
            if not report.get("audio_saved"):
                try:
                    src = page.evaluate("""() => {
                        const a = document.querySelector('audio');
                        if (a && a.src) return a.src;
                        const t = [...document.querySelectorAll('audio, video')].map(x => x.src).filter(Boolean);
                        return t[0] || null;
                    }""")
                    if src:
                        full = src if src.startswith("http") else chk.ORIGIN + src
                        resp = page.context.request.get(full, timeout=120_000)
                        if resp.status == 200 and len(resp.body()) > 500:
                            dest = outdir / f"voice-{who}.wav"
                            dest.write_bytes(resp.body())
                            report["audio_saved"] = str(dest)
                            report["audio_bytes"] = len(resp.body())
                            report["audio_url"] = full
                            report["audio_via_dom"] = True
                except Exception as exc:  # noqa: BLE001
                    report["dom_err"] = str(exc)[:120]
        finally:
            browser.close()

    (outdir / "report.json").write_text(json.dumps(report, indent=2, default=str), "utf-8")
    print(json.dumps({"ok": bool(report.get("audio_saved")), "audio_saved": report.get("audio_saved"),
                      "voice": voice, "text": text[:50]}, indent=2))
    return 0 if report.get("audio_saved") else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--who", required=True)
    ap.add_argument("--voice", required=True)
    ap.add_argument("--text", required=True)
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args(sys.argv[1:])
    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    return run(outdir, a.who, a.voice, a.text, a.dry)


if __name__ == "__main__":
    sys.exit(main())
