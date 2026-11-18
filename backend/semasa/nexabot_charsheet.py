"""Nexabot Image Generator — generate the two-character sheet (Hana + Hassan), then the video sfv with that sheet.

Step 1: Image Generator (Nano Banana Pro) draws the character sheet (16:9, both characters full body, same style).
Step 2: Video Generator sfv (Start Frame) uses that sheet as the first frame -> consistent characters.

Run on GitHub with NEXABOT_STORAGE_STATE_B64, from backend:
  python -m semasa.nexabot_charsheet OUTDIR
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

IMG_URL = chk.ORIGIN + "/image-generator"
VID_URL = chk.ORIGIN + "/video-generator"

CHAR_SHEET_PROMPT = (
    "Gaya komik kartun anime, lukisan 2D berwarna terang, garisan luar hitam jelas, mata besar, ekspresi muka terang. "
    "Lembaran watak (character sheet) dua watak bersebelahan, badan penuh, berdiri menghadap kamera: "
    "di kiri, Hana, wanita muda Melayu bertudung merah jambu dan blaus krim; di kanan, Hassan, lelaki Melayu 30-an, "
    "rambut hitam pendek, cermin mata hitam, baju polo biru laut. Latar belakang rata putih ala komik. "
    "Tidak ada teks, tiada logo, tiada gelembung cakap. Bukan foto realistik, bukan 3D."
)


def _is_image(ctype, url):
    c = (ctype or "").lower()
    return "image" in c or url.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))


def _is_video(ctype, url):
    c = (ctype or "").lower()
    return "video" in c or "mp4" in c or url.lower().endswith(".mp4")


def run(outdir: Path) -> int:
    state = gen.storage_state()
    if not state:
        return 2
    from playwright.sync_api import sync_playwright
    report = {"started": datetime.now(UTC).isoformat()}

    with sync_playwright() as pw:
        browser = chk.launch_browser(pw)
        try:
            ctx = browser.new_context(storage_state=state, locale="ms-MY", timezone_id="Asia/Kuala_Lumpur",
                                      viewport={"width": 1366, "height": 900}, accept_downloads=True)
            page = ctx.new_page()

            # ---- Step 1: image generator -> character sheet ----
            page.goto(IMG_URL, wait_until="domcontentloaded", timeout=45_000)
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:  # noqa: BLE001
                pass
            page.wait_for_timeout(2500)
            # ratio 16:9
            page.get_by_role("button", name="16:9").first.click()
            page.wait_for_timeout(400)
            # prompt
            box = page.locator("textarea").first
            box.fill(CHAR_SHEET_PROMPT)
            page.wait_for_timeout(400)
            btn = page.get_by_role("button", name="Generate Image", exact=True).first
            # wait enabled
            t0 = time.time()
            while time.time() - t0 < 20:
                try:
                    if not btn.is_disabled():
                        break
                except Exception:  # noqa: BLE001
                    pass
                time.sleep(1)
            page.screenshot(path=str(outdir / "img-preclick.png"))
            img_urls: list[str] = []
            events: list[dict] = []

            def on_resp(resp):
                req = resp.request
                ctype = resp.headers.get("content-type", "")
                row = {"m": req.method, "u": req.url[:160], "s": resp.status, "c": ctype[:50]}
                events.append(row)
                if req.method == "GET" and _is_image(ctype, req.url):
                    img_urls.append(req.url)
                # the image may come back on the POST's own JSON (synchronous image API returns url)
                if req.method == "POST" and "image" in req.url.lower():
                    try:
                        j = resp.json()
                        u = j.get("url") or (j.get("data") or {}).get("url")
                        if u:
                            img_urls.append(u)
                    except Exception:  # noqa: BLE001
                        pass

            page.on("response", on_resp)
            btn.click()
            report["img_clicked_at"] = datetime.now(UTC).isoformat()
            t1 = time.time()
            while time.time() - t1 < 120 and not img_urls:
                time.sleep(2)
            # fallback: the result <img> in the DOM
            if not img_urls:
                try:
                    dom = page.evaluate("""() => {
                        const imgs = [...document.querySelectorAll('img')].map(i => i.src).filter(s => s && /storage|supabase|media|blob/i.test(s));
                        return imgs;
                    }""")
                    if dom:
                        img_urls = dom
                        report["img_via_dom"] = True
                except Exception as exc:  # noqa: BLE001
                    report["dom_err"] = str(exc)[:100]
            report["img_url_count"] = len(img_urls)
            report["events"] = [e for e in events if e["s"] != 304][-40:]
            if img_urls:
                full = img_urls[-1] if img_urls[-1].startswith("http") else chk.ORIGIN + img_urls[-1]
                resp = page.context.request.get(full, timeout=120_000)
                if resp.status == 200 and len(resp.body()) > 1000:
                    dest = outdir / "charsheet.png"
                    dest.write_bytes(resp.body())
                    report["charsheet"] = str(dest)
                    report["charsheet_bytes"] = len(resp.body())
                else:
                    report["download_status"] = resp.status
            page.screenshot(path=str(outdir / "img-after.png"))

        finally:
            browser.close()

    (outdir / "report.json").write_text(json.dumps(report, indent=2), "utf-8")
    print(json.dumps({"ok": bool(report.get("charsheet")), "charsheet": report.get("charsheet")}, indent=2))
    return 0 if report.get("charsheet") else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    a = ap.parse_args(sys.argv[1:])
    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    return run(outdir)


if __name__ == "__main__":
    sys.exit(main())
