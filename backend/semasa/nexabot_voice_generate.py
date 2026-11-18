"""Nexabot Voice Generator — generate ONE voiceover line through the studio UI (Unlimited Standard, no credits).

Drives /voice-generator: pick the engine (Natural TTS default; ElevenLabs optional), pick a voice, type the Malay
script, keep Unlimited payment mode, press Generate Voice, then capture the audio result (network observe + the
result <audio> element) and download it.

The first real run is an observation run: the result/download mechanism is not yet known, so every network call is
recorded and an audio-looking response is saved.

Run on GitHub with NEXABOT_STORAGE_STATE_B64, from backend:
  python -m semasa.nexabot_voice_generate OUTDIR --text "..." [--voice Achernar] [--engine natural|elevenlabs]
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
MAX_WAIT_S = 3 * 60
POLL_S = 3


def _is_audio(ctype: str, url: str) -> bool:
    c = (ctype or "").lower()
    if "audio" in c or "mpeg" in c or "wav" in c or "octet-stream" in c:
        return True
    return url.lower().endswith((".mp3", ".wav", ".m4a", ".ogg", ".mp4")) and "video" not in c


def run(outdir: Path, text: str, voice: str, engine: str, dry: bool) -> int:
    state = gen.storage_state()
    if not state:
        print("nexabot: no saved login.")
        return 2
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is not installed.")
        return 2

    report: dict = {"started": datetime.now(UTC).isoformat(), "text": text, "voice": voice,
                    "engine": engine, "dry": dry, "events": [], "audio_url": None}

    with sync_playwright() as pw:
        browser = chk.launch_browser(pw)
        try:
            ctx = browser.new_context(storage_state=state, locale="ms-MY", timezone_id="Asia/Kuala_Lumpur",
                                      viewport={"width": 1366, "height": 900}, accept_downloads=True)
            page = ctx.new_page()

            def on_response(resp):
                req = resp.request
                ctype = resp.headers.get("content-type", "")
                row = {"method": req.method, "url": req.url[:200], "status": resp.status, "ctype": ctype[:60]}
                if req.method == "GET" and _is_audio(ctype, req.url) and not report.get("audio_url"):
                    report["audio_url"] = req.url
                    report["audio_ctype"] = ctype
                report["events"].append(row)

            page.on("response", on_response)
            page.goto(VOICE_URL, wait_until="domcontentloaded", timeout=45_000)
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:  # noqa: BLE001
                pass
            page.wait_for_timeout(2500)
            report["final_url"] = page.url
            if "/login" in page.url:
                print("nexabot: LOGIN WALL.")
                return 1

            # 1. engine (optional): Natural TTS is default; to use ElevenLabs, open the engine menu and pick it
            if engine == "elevenlabs":
                try:
                    page.get_by_role("button", name="Natural TTS").first.click()
                    page.wait_for_timeout(600)
                    page.get_by_text("ElevenLabs", exact=False).first.click()
                    page.wait_for_timeout(800)
                    report["engine_switched"] = True
                except Exception as exc:  # noqa: BLE001
                    report["engine_note"] = f"elevenlabs select failed: {str(exc)[:120]}"

            # 2. voice dropdown -> the named voice (buttons in the open menu)
            try:
                page.get_by_role("button", name="Achernar").first.click()
                page.wait_for_timeout(700)
                page.get_by_role("button", name=voice, exact=True).first.click()
                page.wait_for_timeout(600)
                report["voice_chosen"] = voice
            except Exception as exc:  # noqa: BLE001
                report["voice_note"] = f"voice select failed: {str(exc)[:120]}"

            # 3. script textarea
            box = page.get_by_role("textbox", name=re_type_script()).first
            if not box.count():
                box = page.locator("textarea").first
            box.wait_for(state="visible", timeout=30_000)
            box.fill(text)
            report["text_filled"] = True

            # 4. payment mode -> Unlimited (already default; confirm)
            try:
                pay = page.get_by_role("button", name="Choose payment mode").first
                if not pay.count():
                    pay = page.get_by_role("button", name="♾️ Unlimited").first
                if pay.count() and pay.is_visible():
                    pay.click()
                    page.wait_for_timeout(600)
                    opt = page.get_by_role("option", name="Unlimited").first
                    if opt.count() and opt.is_visible():
                        opt.click()
                        page.wait_for_timeout(400)
                    else:
                        page.keyboard.press("Escape")
            except Exception as exc:  # noqa: BLE001
                report["payment_note"] = f"payment select skipped: {str(exc)[:120]}"

            # 5. Generate Voice (disabled until text is present)
            gen_btn = page.get_by_role("button", name="Generate Voice", exact=True).first
            report["generate_disabled_before"] = gen_btn.is_disabled() if gen_btn.count() else None
            page.screenshot(path=str(outdir / "preclick.png"))
            if dry:
                report["dry"] = True
                (outdir / "report.json").write_text(json.dumps(report, indent=2), "utf-8")
                print(json.dumps({"ok": True, "dry": True}, indent=2))
                return 0

            # wait enabled, then click
            deadline = time.time() + 30
            while time.time() < deadline:
                try:
                    if gen_btn.count() and not gen_btn.is_disabled():
                        break
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(1)
            gen_btn.click()
            report["generate_clicked_at"] = datetime.now(UTC).isoformat()

            # 6. wait for the audio URL to appear
            wait = time.time() + MAX_WAIT_S
            while time.time() < wait and not report.get("audio_url"):
                time.sleep(POLL_S)
            report["waited_for_audio"] = bool(report.get("audio_url"))

            # 7. download the audio
            if report.get("audio_url"):
                url = report["audio_url"]
                full = url if url.startswith("http") else chk.ORIGIN + url
                try:
                    resp = page.context.request.get(full, timeout=120_000)
                    if resp.status == 200 and len(resp.body()) > 500:
                        dest = outdir / f"voice-{datetime.now(UTC).strftime('%H%M%S')}.mp3"
                        dest.write_bytes(resp.body())
                        report["audio_saved"] = str(dest)
                        report["audio_size"] = len(resp.body())
                except Exception as exc:  # noqa: BLE001
                    report["download_error"] = f"{full[:80]} -> {str(exc)[:120]}"

            # 8. also try the result <audio> element src
            if not report.get("audio_saved"):
                try:
                    src = page.evaluate("""() => {
                        const a = document.querySelector('audio');
                        if (a && a.src) return a.src;
                        const t = [...document.querySelectorAll('audio, video')].map(x => x.src).filter(Boolean);
                        return t[0] || null;
                    }""")
                    if src:
                        report["dom_audio_src"] = src
                        full = src if src.startswith("http") else chk.ORIGIN + src
                        resp = page.context.request.get(full, timeout=120_000)
                        if resp.status == 200 and len(resp.body()) > 500:
                            dest = outdir / f"voice-{datetime.now(UTC).strftime('%H%M%S')}.mp3"
                            dest.write_bytes(resp.body())
                            report["audio_saved"] = str(dest)
                            report["audio_size"] = len(resp.body())
                except Exception as exc:  # noqa: BLE001
                    report["dom_note"] = str(exc)[:120]

            page.screenshot(path=str(outdir / "after.png"))
        finally:
            browser.close()

    (outdir / "report.json").write_text(json.dumps(report, indent=2), "utf-8")
    print(json.dumps({"ok": bool(report.get("audio_saved")), "audio_saved": report.get("audio_saved"),
                      "audio_url": report.get("audio_url")}, indent=2))
    return 0 if report.get("audio_saved") else 1


def re_type_script():
    # the accessible name is the placeholder text; match by prefix
    return "Type the script to speak"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--text", required=True)
    ap.add_argument("--voice", default="Achernar")
    ap.add_argument("--engine", default="natural", choices=["natural", "elevenlabs"])
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args(sys.argv[1:])
    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    return run(outdir, a.text, a.voice, a.engine, a.dry)


if __name__ == "__main__":
    sys.exit(main())
