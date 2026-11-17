"""Nexabot Creator Studio — Phase B: generate a real video through the studio UI and hand it to Semasa.

Phase A (nexabot_probe.py) only READ the studio. This module DRIVES it: it types a prompt, keeps the default mode/ratio/
resolution, picks the UNLIMITED payment mode (the web-only plan — no credits are deducted), presses Generate, waits for the
job, and captures the MP4. It then sends the MP4 to Semasa through the import-video route (docs/VIDEO-IMPORT.md), which
makes a DRAFT post — Wan's Approve stays the only gate.

The first real run is ALSO an observation run: because the studio has no public API and Phase A aborted every write, the
download mechanism is not yet known. So every network call is recorded (method + path + status + content-type + body size,
and a response that looks like video is SAVED), and the report is written beside the MP4. Nothing else is inferred.

Spend guard (the guide's Phase B promise): one generation per run by default; `--max` raises it, `--dry` does everything
except the final Generate click (records, spends nothing).

Run it on the GitHub runner (the secret NEXABOT_STORAGE_STATE_B64 exists there), from the backend folder:

    python -m semasa.nexabot_generate OUTDIR --prompt "a cozy coffee cup on a wooden table"

With --import the film can carry its own post text, so Semasa does not have to write it (docs/VIDEO-IMPORT.md): --title, --caption
(one text for every channel), --captions-json (an object {"instagram": "...", "facebook": "...", "threads": "..."}), --channels
(comma list), --lang (bm|en), --source (default nexabot). With none of them the film is sent with only its prompt as the title and
Semasa writes the caption from that title.

Env:
  NEXABOT_STORAGE_STATE_B64   the saved session login (base64)
  SEMASA_IMPORT_TOKEN         bearer token for the import-video route (docs/VIDEO-IMPORT.md)
  SEMASA_IMPORT_URL           https://<project>.supabase.co/functions/v1/semasa-import-video (optional; default from env)
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from . import nexabot_check as chk

STUDIO = chk.STUDIO_URL
PROMPT_PLACEHOLDER = "Describe your video"
GENERATE_NAME = "Generate"
PAYMENT_NAME = "Choose payment mode"
UNLIMITED_NAME = "Unlimited"
RESULTS_SELECTOR = "[data-results] *, [class*='result'] *"
MAX_WAIT_S = 15 * 60
POLL_S = 4


def storage_state() -> dict | None:
    raw = (os.environ.get("NEXABOT_STORAGE_STATE_B64") or "").strip()
    if not raw:
        return None
    try:
        data = base64.b64decode(raw, validate=False)
        if b'"cookies"' not in data:
            return None
        return json.loads(data)
    except (ValueError, json.JSONDecodeError):
        return None


def _is_video(ctype: str, url: str) -> bool:
    c = (ctype or "").lower()
    if "video" in c or "octet-stream" in c or "mp4" in c:
        return True
    return ".mp4" in url.lower()


def generate(page: object, prompt: str, outdir: Path, max_gen: int, dry: bool, report: dict) -> None:
    """Drive the studio: fill the prompt, pick Unlimited, press Generate, poll jobs, capture the MP4."""
    # 1. the prompt box
    box = page.locator(f"textarea[placeholder*='{PROMPT_PLACEHOLDER}']").first
    box.wait_for(state="visible", timeout=30_000)
    box.fill(prompt)
    report["prompt_filled"] = True

    # 2. payment mode -> Unlimited (the web-only plan: no credits deducted). Defaults may already be Unlimited.
    try:
        pay = page.get_by_role("button", name=PAYMENT_NAME).first
        if pay.is_visible():
            pay.click()
            page.wait_for_timeout(600)
            opt = page.get_by_role("option", name=UNLIMITED_NAME).first
            if opt.is_visible():
                opt.click()
                page.wait_for_timeout(400)
            else:
                page.keyboard.press("Escape")
    except Exception as exc:  # noqa: BLE001 - a default that is already Unlimited needs no click
        report["payment_note"] = f"payment select skipped: {str(exc)[:120]}"

    # 3. Generate (disabled until a prompt is present)
    gen = page.get_by_role("button", name=GENERATE_NAME, exact=True).first
    report["generate_disabled_before"] = gen.is_disabled()
    if dry:
        report["dry"] = True
        return
    gen.click()
    report["generate_clicked_at"] = datetime.now(UTC).isoformat()

    # 4. wait for the result: the MP4 is captured by the on_response handler (a GET whose body is video);
    #    break as soon as a video lands, and otherwise keep polling the jobs list until the deadline.
    deadline = time.time() + MAX_WAIT_S
    while time.time() < deadline:
        if report.get("video_saved"):
            report["video_captured_at"] = datetime.now(UTC).isoformat()
            break
        try:
            jobs = page.evaluate("""async () => {
                const r = await fetch('/api/v1/jobs?scope=recent&limit=30');
                const j = await r.json();
                return Array.isArray(j) ? j : (j.jobs || j.data || []);
            }""")
        except Exception:  # noqa: BLE001
            jobs = []
        done = [j for j in jobs if (j.get("status") in ("done", "complete", "ready", "success"))]
        if done:
            report["job_done"] = True
            keys = ("id", "status", "mode", "model", "width", "height", "size_bytes", "download_url")
            report["job_meta"] = {k: done[0].get(k) for k in keys if done[0].get(k) is not None}
            break
        time.sleep(POLL_S)
    else:
        report["timed_out"] = True

    # 5. download the full MP4 with a plain GET (no Range), from the recorded video URL; fall back to the job's download_url.
    if report.get("job_done") and not report.get("video_saved"):
        url = report.get("video_url") or (report.get("job_meta") or {}).get("download_url")
        if url:
            try:
                import requests
                r = requests.get(url, timeout=300, stream=True)
                if r.status_code == 200:
                    dest = outdir / f"nexabot-{datetime.now(UTC).strftime('%H%M%S')}.mp4"
                    with open(dest, "wb") as fh:
                        for chunk in r.iter_content(1 << 20):
                            fh.write(chunk)
                    report["video_saved"] = str(dest)
                    report["video_via"] = "direct_get"
                    report["video_size_final"] = dest.stat().st_size
                else:
                    report["download_error"] = f"status {r.status_code}"
            except Exception as exc:  # noqa: BLE001
                report["download_error"] = str(exc)[:200]


def run(outdir: Path, prompt: str, max_gen: int, dry: bool, import_ok: bool, opts: dict | None = None) -> int:
    state = storage_state()
    if not state:
        print("nexabot: no saved login (NEXABOT_STORAGE_STATE_B64 empty or not JSON).")
        return 2
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is not installed.")
        return 2

    report: dict = {"started": datetime.now(UTC).isoformat(), "prompt": prompt, "max_gen": max_gen,
                    "dry": dry, "events": [], "video_saved": None, "import": None}

    with sync_playwright() as pw:
        browser = chk.launch_browser(pw)
        try:
            ctx = browser.new_context(storage_state=state, locale="en-MY", timezone_id="Asia/Kuala_Lumpur",
                                      viewport={"width": 1366, "height": 900}, accept_downloads=True)
            page = ctx.new_page()

            def on_response(resp):
                req = resp.request
                url = req.url
                ctype = resp.headers.get("content-type", "")
                status = resp.status
                row = {"method": req.method, "url": url, "status": status, "ctype": ctype}
                try:
                    body = resp.body()
                    row["size"] = len(body)
                except Exception:  # noqa: BLE001 - a streamed body is just not read
                    row["size"] = None
                # record the FIRST full video URL (not a partial 206 chunk). The real download happens after the job
                # is done, with a plain GET that does not ask for a range, so the whole MP4 comes back.
                if req.method == "GET" and _is_video(ctype, url) and status in (200, 206) and not report.get("video_url"):
                    report["video_url"] = url
                    report["video_size_hint"] = row["size"]
                report["events"].append(row)

            page.on("response", on_response)
            page.goto(STUDIO, wait_until="domcontentloaded", timeout=45_000)
            try:
                page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:  # noqa: BLE001
                pass
            page.wait_for_timeout(2500)
            final_url = page.url
            report["final_url"] = final_url
            if "/login" in final_url:
                print("nexabot: LOGIN WALL — record the login again (ops/NEXABOT-LOGIN.md).")
                return 1
            generate(page, prompt, outdir, max_gen, dry, report)
            page.wait_for_timeout(3000)
        finally:
            browser.close()

    (outdir / "report.json").write_text(json.dumps(report, indent=2), "utf-8")
    print(json.dumps({"ok": True, "dry": dry, "video_saved": report.get("video_saved"),
                      "events": len(report["events"])}, indent=2))
    if report.get("video_saved") and import_ok and not dry:
        return _import(report["video_saved"], report, opts)
    return 0


CHANNELS = ("instagram", "facebook", "threads", "linkedin")


def import_form(prompt: str, opts: dict | None = None, now: datetime | None = None) -> dict:
    """The form fields sent beside the file, as the intake's parseOptions reads them
    (supabase/functions/semasa-import-video/logic.js). A caption as one text goes in `caption`; per-channel captions go in
    `caption` as one JSON object (a multipart field is text: the worker reads a JSON object there, video_import.texts_of).
    Empty options are left out, so a bare run sends what it always did."""
    o = opts or {}
    now = now or datetime.now(UTC)
    data = {"source": (o.get("source") or "nexabot")[:60], "title": (o.get("title") or prompt or "")[:160],
            "idempotency_key": f"nexabot-{now.strftime('%Y%m%d-%H%M%S')}"}
    channels = [c.strip().lower() for c in str(o.get("channels") or "").split(",") if c.strip()]
    by_channel = o.get("captions") if isinstance(o.get("captions"), dict) else {}
    plain = str(o.get("caption") or "").strip()
    if by_channel:
        merged = {c: plain for c in (channels or CHANNELS[:3])} if plain else {}
        merged.update({c: t for c, t in by_channel.items() if str(t).strip()})
        data["caption"] = json.dumps(merged, ensure_ascii=False)
    elif plain:
        data["caption"] = plain
    if channels:
        data["channels"] = ",".join(channels)
    if o.get("lang"):
        data["lang"] = str(o["lang"])
    return data


def parse_captions_json(raw: str) -> dict:
    """--captions-json as a dict {channel: text}; ValueError (with the reason) when it is not that."""
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"--captions-json is not valid JSON ({exc.msg})") from exc
    if not isinstance(obj, dict) or not obj:
        raise ValueError("--captions-json must be a JSON object such as {\"instagram\": \"...\"}")
    bad = [k for k, v in obj.items() if k not in CHANNELS or not isinstance(v, str)]
    if bad:
        names = ", ".join(map(str, bad))
        raise ValueError(f"--captions-json: {names} is not a channel with a text (channels: {', '.join(CHANNELS)})")
    return obj


def _import(mp4: str, report: dict, opts: dict | None = None) -> int:
    import requests
    url = os.environ.get("SEMASA_IMPORT_URL")
    token = os.environ.get("SEMASA_IMPORT_TOKEN")
    if not url or not token:
        report["import"] = {"error": "SEMASA_IMPORT_URL/TOKEN not set; the MP4 is saved but not imported"}
        print("nexabot: MP4 saved but SEMASA_IMPORT_URL/TOKEN not set.")
        return 0
    with open(mp4, "rb") as f:
        r = requests.post(url, headers={"Authorization": f"Bearer {token}"},
                          files={"file": ("film.mp4", f, "video/mp4")},
                          data=import_form(report.get("prompt", ""), opts), timeout=300)
    report["import"] = {"status": r.status_code, "body": r.text[:500]}
    print(f"import: {r.status_code} {r.text[:300]}")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--max", type=int, default=1, dest="max_gen")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--import", dest="import_ok", action="store_true", help="send the MP4 to Semasa import-video")
    ap.add_argument("--title", default="", help="the post's title (default: the prompt)")
    ap.add_argument("--caption", default="", help="one caption for every channel")
    ap.add_argument("--captions-json", default="", dest="captions_json", help='per-channel captions, {"instagram": "...", ...}')
    ap.add_argument("--channels", default="", help="comma list: instagram,facebook,threads")
    ap.add_argument("--lang", default="", choices=["", "bm", "en"])
    ap.add_argument("--source", default="nexabot")
    a = ap.parse_args(argv[1:])
    opts = {"title": a.title, "caption": a.caption, "channels": a.channels, "lang": a.lang, "source": a.source}
    if a.captions_json.strip():
        try:  # refused before anything is generated: a bad caption must not cost a run
            opts["captions"] = parse_captions_json(a.captions_json)
        except ValueError as exc:
            print(f"nexabot: {exc}")
            return 2
    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    return run(outdir, a.prompt, a.max_gen, a.dry, a.import_ok, opts)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
