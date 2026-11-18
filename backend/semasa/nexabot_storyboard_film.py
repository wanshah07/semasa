# ruff: noqa: E501
"""Nexabot storyboard film — feed each scene's Malay text prompt to Nexabot t2v, then concatenate into one film.

Wan's instruction: build the storyboard as TEXT in Bahasa Melayu (not English), then hand each scene to Nexabot. So each
scene is a Malay prompt sent to the studio's Text-to-Video mode (no image upload), the four 15s clips are concatenated,
and the Malay dialogue is burned as subtitles (Nexabot cannot render text reliably).

Run on the GitHub runner (NEXABOT_STORAGE_STATE_B64), from backend:
  python -m semasa.nexabot_storyboard_film OUTDIR [--dry]
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
from .nexabot_comic_film import CREDIT, SUBTITLES, burn_subtitles, concat

# each scene: a Malay prompt (t2v) + its dialogue (burned as a subtitle afterwards)
# the shared comic style, told in Malay so the model draws a cartoon/anime look, not a realistic photo
STYLE = ("Gaya komik kartun anime, lukisan 2D yang berwarna terang, garisan luar hitam yang jelas, watak dengan mata "
         "besar dan ekspresi muka yang terang, latar belakang rata ala komik. Bukan foto realistik, bukan 3D. ")
# the two characters, described once so every scene draws the SAME people
CAST = ("Hana ialah wanita muda Melayu bertudung merah jambu dan berbaju krim. Pak Mat ialah lelaki Melayu berusia "
        "30-an, rambut hitam pendek, bercermin mata hitam, berbaju polo biru laut, memegang papan klip. ")

SCENES = [
    {
        "prompt": (STYLE + CAST +
                   "Babak pertama: di kedai runcit kecil di Malaysia, di depan rak makanan berbungkus. Hana memandang "
                   "dekat bungkusan snek kuning di tangannya dengan wajah hairan. Ada logo halal berwarna hijau pada "
                   "bungkusan itu. Pak Mat berdiri di sebelahnya sambil mendengar."),
        "lines": [("Hana", "Eh, logo halal kat paket ni warna hijau. Bukan sepatutnya hitam ke?")],
    },
    {
        "prompt": (STYLE + CAST +
                   "Babak kedua: di kedai runcit kecil di Malaysia, di depan rak makanan berbungkus. Pak Mat memandang "
                   "bungkusan snek kuning dengan risau, tangan menyentuh dagu. Hana tersenyum tenang dan mengangkat "
                   "satu tangan sambil memegang bungkusan snek kuning yang ada logo halal hijau."),
        "lines": [("Pak Mat", "Jangan-jangan logo palsu?"),
                  ("Hana", "Tak semestinya. Warna bukan penentu.")],
    },
    {
        "prompt": (STYLE + CAST +
                   "Babak ketiga: di kedai runcit kecil di Malaysia, di depan rak makanan berbungkus. Hana menunjuk "
                   "logo halal hijau pada bungkusan snek kuning dan menerangkan sesuatu. Pak Mat mendengar dengan minat "
                   "sambil memegang papan klip."),
        "lines": [("Hana", "Pemegang sijil boleh cetak logo ikut warna pembungkusan, asalkan spesifikasi logo tak diubah.")],
    },
    {
        "prompt": (STYLE + CAST +
                   "Babak keempat: di kedai runcit kecil di Malaysia, di depan rak makanan berbungkus. Pak Mat kelihatan "
                   "lega dan ingin tahu. Hana mengangkat bungkusan snek kuning dengan logo halal hijau dan menunjuk ke "
                   "arah logo itu."),
        "lines": [("Pak Mat", "Mana tulis tu?"),
                  ("Hana", "MPPHM (Domestik) 2020, Klausa 40(2).")],
    },
]


def run(outdir: Path, dry: bool) -> int:
    state = gen.storage_state()
    if not state:
        print("nexabot: no saved login (NEXABOT_STORAGE_STATE_B64 empty or not JSON).")
        return 2
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is not installed.")
        return 2

    report: dict = {"started": datetime.now(UTC).isoformat(), "dry": dry, "clips": []}

    with sync_playwright() as pw:
        browser = chk.launch_browser(pw)
        try:
            ctx = browser.new_context(storage_state=state, locale="ms-MY", timezone_id="Asia/Kuala_Lumpur",
                                      viewport={"width": 1366, "height": 900}, accept_downloads=True)
            page = ctx.new_page()

            def on_response(resp):
                req = resp.request
                if req.method == "POST" and req.url.rstrip("/").endswith("/api/v1/generate") and resp.status in (200, 201, 202):
                    try:
                        j = resp.json()
                        j = j.get("job") if isinstance(j.get("job"), dict) else j
                        jid = j.get("id") or j.get("job_id") or j.get("jobId")
                        if jid:
                            report["job_id"] = str(jid)
                    except Exception:  # noqa: BLE001
                        pass

            page.on("response", on_response)
            page.goto(chk.STUDIO_URL, wait_until="domcontentloaded", timeout=45_000)
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:  # noqa: BLE001
                pass
            page.wait_for_timeout(2500)
            report["final_url"] = page.url
            if "/login" in page.url:
                print("nexabot: LOGIN WALL.")
                return 1

            for i, scene in enumerate(SCENES):
                if i > 0:
                    # fresh page load per scene, so the next generation starts clean
                    page.goto(chk.STUDIO_URL, wait_until="domcontentloaded", timeout=45_000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=15_000)
                    except Exception:  # noqa: BLE001
                        pass
                    page.wait_for_timeout(2500)
                report["job_id"] = None
                report["video_saved"] = None
                gen.generate(page, scene["prompt"], outdir, 1, dry, report)
                if dry:
                    report.setdefault("dry_scenes", []).append({"scene": i + 1, "prompt": scene["prompt"][:120]})
                    continue
                if report.get("video_saved"):
                    report["clips"].append(report["video_saved"])
                    report.setdefault("scene_results", []).append({"scene": i + 1, "saved": report["video_saved"]})
                else:
                    report["error_scene"] = i + 1
                    break
        finally:
            browser.close()

    (outdir / "report.json").write_text(json.dumps(report, indent=2), "utf-8")

    if dry:
        print(json.dumps({"ok": True, "dry": True, "scenes": len(SCENES)}, indent=2))
        return 0

    if len(report.get("clips", [])) == len(SCENES):
        raw = concat(report["clips"], outdir / "comic-film-raw.mp4")
        film = burn_subtitles(report["clips"], raw, outdir / "comic-film.mp4")
        report["film"] = str(film)
        print("film saved:", film)
        (outdir / "report.json").write_text(json.dumps(report, indent=2), "utf-8")
        print(json.dumps({"ok": True, "clips": len(report["clips"]), "film": str(film)}, indent=2))
        return 0

    print(json.dumps({"ok": False, "clips": len(report.get("clips", []))}, indent=2))
    return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args(sys.argv[1:])
    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    return run(outdir, a.dry)


if __name__ == "__main__":
    sys.exit(main())
