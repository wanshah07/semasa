# ruff: noqa: E501
"""Nexabot film via the official REST API (v1) — no Playwright, no web UI.

The web /api/v1/generate endpoint now returns 403 ("Akses otomatis tidak diizinkan ...
gunakan API key POST /api/v1/api"). So this module drives the documented API instead:

    POST /api/v1/api            -> 202 {job_id}   (model, mode, prompt, ratio, resolution, media)
    GET  /api/v1/jobs/:id       -> {job: {status: queued|processing|done|failed}}
    GET  /api/v1/jobs/:id/download -> mp4 (x-api-key header)

Scene 1 = i2v with the charsheet (1 image). Scene 2 = i2v with last-frame + charsheet (2 images),
so the background and characters stay consistent. Dialogue stays in the prompt (i2v auto-TTS).

Env:
  NEXABOT_API_KEY    the account's API key (nxb_...)

Run on GitHub, from backend:
  python -m semasa.nexabot_api_film OUTDIR
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib import error, request

BASE = "https://nexabot.id"
API = BASE + "/api/v1/api"
SHEET = Path(__file__).resolve().parents[2] / "web" / "public" / "comic-panels" / "charsheet.png"

SCENES = [
    "Photorealistic video, vertical 9:16 portrait framing. Di kedai runcit di Malaysia, Hana, perempuan bertudung merah jambu dan berbaju krim, "
    "memandang bungkusan snek kuning di tangan dengan wajah hairan. Hassan, lelaki bercermin mata hitam dan berbaju "
    "polo biru laut, berdiri di sebelah. Hana berkata eh logo halal ni ada tarikh luput ke, ingatkan kekal je. "
    "Tiada dialog lain. Kamera statik.",
    "Photorealistic video, vertical 9:16 portrait framing. Di kedai runcit di Malaysia, rak makanan snek yang sama, latar yang sama persis seperti "
    "video sebelum ini, Hassan, lelaki bercermin mata hitam dan berbaju polo biru laut, terus bercakap sambil memberi "
    "isyarat tangan. Hana, perempuan bertudung merah jambu, berdiri di tempat yang sama mendengar sambil membelek "
    "bungkusan snek kuning. Hassan berkata sijil halal ni ada tempoh, makanan macam ni biasanya dua tahun, ubat dengan "
    "kosmetik pulak sampai tiga tahun. Hana tersenyum lega dan berkata baru tahu sekarang, dulu tak tahu ada tarikh luput halal ni. Tiada dialog lain. Kamera statik.",
]


def _key() -> str:
    k = (os.environ.get("NEXABOT_API_KEY") or "").strip()
    if not k:
        raise SystemExit("NEXABOT_API_KEY is not set")
    return k


def _post(url: str, body: dict, key: str) -> dict:
    data = json.dumps(body).encode()
    req = request.Request(url, data=data, method="POST",
                          headers={"x-api-key": key, "Content-Type": "application/json"})
    try:
        with request.urlopen(req, timeout=60) as r:
            return {"status": r.status, "body": json.loads(r.read().decode())}
    except error.HTTPError as e:
        try:
            return {"status": e.code, "body": json.loads(e.read().decode())}
        except Exception:  # noqa: BLE001
            return {"status": e.code, "body": {"error": str(e)}}


def _get(url: str, key: str) -> dict:
    req = request.Request(url, headers={"x-api-key": key})
    try:
        with request.urlopen(req, timeout=60) as r:
            return {"status": r.status, "body": json.loads(r.read().decode())}
    except error.HTTPError as e:
        try:
            return {"status": e.code, "body": json.loads(e.read().decode())}
        except Exception:  # noqa: BLE001
            return {"status": e.code, "body": {"error": str(e)}}


def _b64_image(path: Path) -> str:
    raw = path.read_bytes()
    if path.suffix.lower() == ".png":
        mime = "image/png"
    elif path.suffix.lower() in (".jpg", ".jpeg"):
        mime = "image/jpeg"
    else:
        mime = "image/png"
    return f"data:{mime};base64," + base64.b64encode(raw).decode()


def submit(key: str, prompt: str, media: list[str]) -> dict:
    body = {
        "model": "omni_flash",
        "mode": "i2v",
        "prompt": prompt,
        "ratio": 2,          # 9:16 portrait
        "resolution": 1080,
        "media": media,
    }
    return _post(API, body, key)


def poll(key: str, job_id: str) -> dict:
    return _get(f"{BASE}/api/v1/jobs/{job_id}", key)


def download(key: str, job_id: str, dest: Path) -> bool:
    req = request.Request(f"{BASE}/api/v1/jobs/{job_id}/download", headers={"x-api-key": key})
    try:
        with request.urlopen(req, timeout=300) as r:
            body = r.read()
    except error.HTTPError as e:
        print(f"download http {e.code}")
        return False
    if len(body) > 500_000:
        dest.write_bytes(body)
        return True
    print(f"download too small: {len(body)} bytes")
    return False


def extract_last_frame(video: Path, out: Path) -> Path | None:
    ffmpeg = os.environ.get("FFMPEG") or "ffmpeg"
    try:
        subprocess.run([ffmpeg, "-y", "-sseof", "-1", "-i", str(video), "-frames:v", "1", str(out)],
                       check=True, capture_output=True, timeout=120)
    except Exception as exc:  # noqa: BLE001
        print(f"last-frame err: {exc}")
        return None
    return out if out.exists() and out.stat().st_size > 1000 else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("outdir")
    a = ap.parse_args(sys.argv[1:])
    outdir = Path(a.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    key = _key()
    if not SHEET.exists():
        print(f"missing charsheet: {SHEET}")
        return 2

    report = {"started": datetime.now(UTC).isoformat(), "clips": []}
    sheet_b64 = _b64_image(SHEET)
    prev_frame_b64 = None

    for idx, prompt in enumerate(SCENES):
        report["scene"] = idx + 1
        media = [sheet_b64] if idx == 0 else ([prev_frame_b64, sheet_b64] if prev_frame_b64 else [sheet_b64])

        resp = submit(key, prompt, media)
        report[f"scene{idx+1}_submit_status"] = resp["status"]
        body = resp.get("body") or {}
        job_id = body.get("job_id")
        report[f"scene{idx+1}_job_id"] = job_id
        if resp["status"] != 202 or not job_id:
            report[f"scene{idx+1}_submit_error"] = body.get("error")
            report["error_scene"] = idx + 1
            break

        # poll until done/failed (i2v ~150s per docs; allow generous window)
        DONE = ("done", "completed", "complete", "ready", "success")
        FAILED = ("failed", "error", "cancelled", "canceled")
        deadline = time.time() + 15 * 60
        status = ""
        while time.time() < deadline:
            r = poll(key, job_id)
            job = (r.get("body") or {}).get("job") or (r.get("body") or {})
            status = str(job.get("status") or "").lower()
            report[f"scene{idx+1}_status"] = status
            if status in DONE:
                break
            if status in FAILED:
                report[f"scene{idx+1}_job_failed"] = {k: job.get(k) for k in ("id", "status", "error", "message") if job.get(k)}
                break
            time.sleep(4)
        if status not in DONE:
            report[f"scene{idx+1}_timed_out"] = True
            report["error_scene"] = idx + 1
            break

        dest = outdir / f"clip{idx+1}.mp4"
        ok = download(key, job_id, dest)
        report[f"scene{idx+1}_saved"] = str(dest) if ok else None
        if not ok:
            report["error_scene"] = idx + 1
            break

        report["clips"].append(str(dest))

        # last frame of this clip -> background ref for the next scene
        frame = outdir / f"frame{idx+1}.png"
        if extract_last_frame(dest, frame):
            prev_frame_b64 = _b64_image(frame)
            report[f"scene{idx+1}_frame_ref"] = str(frame)

    (outdir / "report.json").write_text(json.dumps(report, indent=2, default=str), "utf-8")
    print(json.dumps({"ok": len(report["clips"]) == len(SCENES), "clips": len(report["clips"]),
                      "total": len(SCENES)}, indent=2))
    return 0 if len(report["clips"]) == len(SCENES) else 1


if __name__ == "__main__":
    sys.exit(main())
