"""Motion: a motion-graphics video from an idea or a link (Wan, 23 Oct 2026: "in video segment, add motion segment that can
create the motion video ... add this skill/prompt to create motion, create the video for this [link/idea]").

How a motion video is made, and why this way:
  1. the AI team's writer (semasa.ai_config.llm_for, so the fastest healthy robot) writes ONE HTML file to the HyperFrames
     contract: a root composition with timed `.clip` elements and one paused GSAP timeline registered on
     window.__timelines. The contract is the authoring prompt below (SYSTEM), condensed from heygen-com/hyperframes
     skills/hyperframes/SKILL.md, plus Semasa's own rules (two voices, no CTA, no URL, a source line) and whatever Wan
     puts in settings.motion.prompt (his own skill/prompt text).
  2. `npx hyperframes check --json` validates it (lint, runtime in headless Chrome, layout, contrast). Errors go back to
     the writer ONCE with the findings; warnings are kept in the row for Wan to see.
  3. `npx hyperframes render` turns it into an MP4 by seeking the timeline frame by frame, so a render is deterministic.
     Measured 23 Oct 2026 in this environment: a 3 s portrait composition rendered to a 1080x1920 H.264 MP4 in seconds
     with the pre-installed Chromium and the system ffmpeg; the GitHub runner has both.
  4. the MP4 and a poster frame go to the semasa-generated bucket; the row is `done` and the Video tab plays it.

Not used: MotionClone (Windows only, Codex login, no licence) and the hosted Claude Motion / HyperFrames cloud (needs an
account token and an upload the page cannot make). HyperFrames the open-source CLI (Apache-2.0) runs on the runner with
no key at all; the only key spent is the writer's.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import ai_config, api_status, db, fetch
from .llm import LLM

log = logging.getLogger("semasa.motion")
TABLE = "semasa_motions"
SETTINGS_KEY = "motion"
CLI_VERSION = "0.8.188"
MAX_ATTEMPTS = 2
MAX_HTML = 60_000
SIZES = {"portrait": (1080, 1920), "landscape": (1920, 1080), "square": (1080, 1080)}
GSAP = "https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"
PALETTE = {"regulab": {"ground": "#0f172a", "ink": "#f8fafc", "accent": "#38bdf8", "accent2": "#fbbf24"},
           "linkedin": {"ground": "#111827", "ink": "#f9fafb", "accent": "#34d399", "accent2": "#f472b6"}}
VOICE = {
    "regulab": "ws.regulab, a Malaysian regulatory consultancy speaking Bahasa Malaysia (Malaysian, never Indonesian: boleh not "
               "bisa, ubat not obat, syarikat not perusahaan) in a warm, plain BM-mix voice to SME owners.",
    "linkedin": "a named Malaysian chemist speaking English to peers on LinkedIn: precise, plain, no hype.",
}

SYSTEM = """You write a short motion-graphics video as ONE self-contained HTML file for HyperFrames (HTML rendered to video by
seeking a paused GSAP timeline frame by frame). Answer with ONE JSON object: {{"title": "<short title>", "html": "<the whole
index.html as a string>"}}. Nothing else.

THE CONTRACT (a render fails or looks wrong if any is broken):
1. The file starts with <!doctype html>, <html lang="{lang}" data-resolution="{resolution}">, a <meta name="viewport"
   content="width={w}, height={h}">, and loads GSAP with exactly: <script src="{gsap}"></script>. No other script, stylesheet,
   font or network request. html, body are {w}px by {h}px, overflow hidden, with the film's background.
2. The root is <div id="root" data-composition-id="main" data-start="0" data-duration="{seconds}" data-width="{w}"
   data-height="{h}"> and holds every scene. The video's length is the root's data-duration: {seconds} seconds.
3. Every timed element has class="clip", data-start and data-duration in seconds, a stable id, and shows over
   [start, start + duration). Land an end state just before its end. Elements are written in the HTML, never made by script.
4. One paused timeline, registered AFTER its tweens: const tl = gsap.timeline({{ paused: true }}); ... ;
   window.__timelines["main"] = tl; tl.seek(0); Position every tween with an absolute time as the last argument.
5. No Date.now(), no Math.random(), no fetch, no timers, no repeat: -1, no <video>, <audio> or <img>. Everything visible is a
   function of timeline time. Draw with CSS only: type, shapes, gradients, borders, simple SVG written inline.
6. Never tween display, visibility or autoAlpha on a .clip; animate a child. Animate transforms and opacity, never left/top/
   width/height. No CSS transform on an element GSAP transforms.
7. Fonts: font-family: "Inter", system-ui, -apple-system, "Segoe UI", sans-serif (no @font-face). Keep all content inside the
   central 90% of the frame; key text inside the central 80%. Type at least 44px on a 1080-wide frame.
8. Frame 0 already shows the title (it is the social thumbnail): do not enter from an empty frame.

THE FILM: 3 to 6 scenes for {seconds} seconds: a hook (the title, big), two to four points (one idea each, short lines,
numbers big), and a closing card with the source line "{source_line}" in small type. Motion: eases power3.out / power2.inOut,
0.4 to 0.8 s entrances, staggered lines, a slow background drift, punchy but readable; every line stays on screen at least 2.5 s.
Palette: background {ground}, text {ink}, accent {accent}, second accent {accent2}.
VOICE: {voice}
RULES: no call to action, no website, no URL, no handle, no hashtag, no emoji on screen; never invent a fee, date, number or
clause that the brief did not give; end on the substance. Write the words in {language}.
{extra}"""


def load_settings(store: Any) -> dict[str, Any]:
    try:
        rows = store.table(db.SETTINGS).select("value").eq("key", SETTINGS_KEY).execute().data or []
        v = (rows[0].get("value") or {}) if rows else {}
    except Exception as exc:  # noqa: BLE001
        log.info("motion settings not read (%s)", str(exc)[:120])
        v = {}
    return {"prompt": str(v.get("prompt") or "").strip(), "cli": str(v.get("cli") or CLI_VERSION).strip() or CLI_VERSION}


def source_words(url: str, timeout: int = 25) -> tuple[str, str]:
    """(title, text) of the page a brief points at, trimmed; ('', '') when it cannot be read."""
    if not url:
        return "", ""
    try:
        from .brain import page_text
        r = fetch.get(url, timeout=timeout)
        title, desc, text = page_text(r.text)
        return title[:200], (text or desc)[:6000]
    except Exception as exc:  # noqa: BLE001 - the brief alone still makes a film
        log.info("source not read (%s): %s", url, str(exc)[:120])
        return "", ""


def build_system(row: dict[str, Any], extra: str) -> str:
    stream = row.get("stream") or "regulab"
    res = row.get("resolution") or "portrait"
    w, h = SIZES.get(res, SIZES["portrait"])
    pal = PALETTE.get(stream, PALETTE["regulab"])
    return SYSTEM.format(lang="ms" if stream == "regulab" else "en", resolution=res, w=w, h=h, gsap=GSAP,
                         seconds=int(row.get("seconds") or 12), source_line=row.get("source_line") or "Sumber: lihat kapsyen",
                         voice=VOICE.get(stream, VOICE["regulab"]),
                         language="Bahasa Malaysia" if stream == "regulab" else "English",
                         extra=("WAN'S OWN INSTRUCTIONS:\n" + extra) if extra else "", **pal)


def build_user(row: dict[str, Any], src_title: str, src_text: str, findings: list[dict[str, Any]] | None = None,
               previous: str = "") -> str:
    parts = [f"BRIEF: {row.get('brief') or '(none)'}"]
    if row.get("source_url"):
        parts.append(f"LINK: {row['source_url']}")
        if src_title or src_text:
            parts.append(f"WHAT THE LINK SAYS (title: {src_title or '?'}):\n{src_text or '(could not be read)'}")
    if findings:
        parts.append("THE CHECK FAILED. Fix every finding and return the WHOLE corrected file:\n" +
                     "\n".join(f"- [{f.get('code')}] {f.get('message')}" for f in findings))
        parts.append("PREVIOUS FILE:\n" + previous[:MAX_HTML])
    return "\n\n".join(parts)


# --- the HyperFrames CLI ------------------------------------------------------------------------------------------------

def _npx(cli: str) -> list[str]:
    return ["npx", "-y", f"hyperframes@{cli}"]


def cli_env() -> dict[str, str]:
    env = dict(os.environ)
    chrome = os.environ.get("PUPPETEER_EXECUTABLE_PATH") or shutil.which("google-chrome") or shutil.which("chromium") \
        or "/opt/pw-browsers/chromium-1243/chrome-linux64/chrome"
    if chrome and Path(chrome).exists():
        env.setdefault("PUPPETEER_EXECUTABLE_PATH", chrome)
    env.setdefault("HYPERFRAMES_SKIP_SKILLS", "1")
    env.setdefault("HF_TELEMETRY", "0")
    return env


def write_project(folder: Path, html: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "index.html").write_text(html, encoding="utf-8")
    (folder / "hyperframes.json").write_text(json.dumps({
        "$schema": "https://hyperframes.heygen.com/schema/hyperframes.json",
        "paths": {"blocks": "compositions", "components": "compositions/components", "assets": "assets"},
        "media": {"autoProxy": False},
    }), encoding="utf-8")


def check(folder: Path, cli: str, runner: Any = subprocess.run, timeout: int = 300) -> dict[str, Any]:
    """{ok, errors: [{code, message}], warnings: [...]} from `hyperframes check --json`."""
    p = runner([*_npx(cli), "check", "--json", "."], cwd=str(folder), capture_output=True, text=True, timeout=timeout,
               env=cli_env())
    out = (p.stdout or "").strip()
    try:
        data = json.loads(out[out.index("{"):out.rindex("}") + 1]) if "{" in out else {}
    except (ValueError, json.JSONDecodeError):
        data = {}
    if not data:
        return {"ok": p.returncode == 0, "errors": [{"code": "check_unreadable", "message": (p.stderr or out)[-600:]}]
                if p.returncode != 0 else [], "warnings": []}
    errors, warnings = [], []
    for section in ("lint", "runtime", "layout", "motion", "contrast", "craft"):
        for f in (data.get(section) or {}).get("findings") or []:
            item = {"code": f.get("code") or section, "message": str(f.get("message") or "")[:300], "section": section}
            (errors if f.get("severity") == "error" else warnings).append(item)
    return {"ok": bool(data.get("ok")) and not errors, "errors": errors, "warnings": warnings[:20]}


def render(folder: Path, cli: str, resolution: str, runner: Any = subprocess.run, timeout: int = 900) -> Path:
    out = folder / "renders" / "motion.mp4"
    p = runner([*_npx(cli), "render", ".", "--fps", "30", "--quality", "looks", "--resolution", resolution, "--quiet",
                "--output", str(out)], cwd=str(folder), capture_output=True, text=True, timeout=timeout, env=cli_env())
    if p.returncode != 0 or not out.exists():
        raise RuntimeError("render failed: " + ((p.stderr or p.stdout or "")[-800:]).strip())
    return out


def poster(video: Path, runner: Any = subprocess.run) -> bytes | None:
    """The frame at 0.5 s as JPEG (ffmpeg on the runner), or None."""
    out = video.with_suffix(".jpg")
    try:
        runner(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", "0.5", "-i", str(video), "-frames:v", "1",
                "-q:v", "3", str(out)], capture_output=True, text=True, timeout=120)
        return out.read_bytes() if out.exists() else None
    except Exception as exc:  # noqa: BLE001 - a poster is a nicety
        log.info("no poster: %s", str(exc)[:120])
        return None


def probe(video: Path, runner: Any = subprocess.run) -> dict[str, Any]:
    try:
        p = runner(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration",
                    "-of", "json", str(video)], capture_output=True, text=True, timeout=60)
        j = json.loads(p.stdout or "{}")
        s = (j.get("streams") or [{}])[0]
        return {"width": int(s.get("width") or 0), "height": int(s.get("height") or 0),
                "duration_s": round(float((j.get("format") or {}).get("duration") or 0), 2)}
    except Exception:  # noqa: BLE001
        return {"width": 0, "height": 0, "duration_s": 0}


# --- the worker ----------------------------------------------------------------------------------------------------------

def clean_html(html: Any) -> str:
    s = str(html or "").strip()
    s = re.sub(r"^```(?:html)?\s*|\s*```$", "", s)
    if "<html" not in s.lower() or "__timelines" not in s:
        raise ValueError("the writer did not return a whole HyperFrames composition")
    if re.search(r"<(?:video|audio|img)\b", s, re.I) or "fetch(" in s or "Math.random" in s:
        raise ValueError("the composition uses media, fetch or random, which the contract forbids")
    return s[:MAX_HTML]


def claim(store: Any, limit: int = 3) -> list[dict[str, Any]]:
    q = store.table(TABLE).select("*").eq("status", "pending").order("created_at").limit(limit)
    out = []
    for r in q.execute().data or []:
        attempts = int(r.get("attempts") or 0) + 1
        got = store.table(TABLE).update({"status": "working", "attempts": attempts, "error": ""}) \
            .eq("id", r["id"]).eq("status", "pending").execute().data
        if got:
            out.append({**r, "attempts": attempts})
    return out


def process(store: Any, llm: Any, row: dict[str, Any], settings: dict[str, Any], *, runner: Any = subprocess.run,
            workdir: Path | None = None, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    folder = (workdir or Path(tempfile.mkdtemp(prefix="motion-"))) / str(row["id"])[:8]
    try:
        if llm is None:
            raise RuntimeError("no AI writer: set a reader key in Tetapan → Tetapan AI")
        title, text = source_words(row.get("source_url") or "")
        system = build_system(row, settings.get("prompt") or "")
        out = llm.chat_json(system, build_user(row, title, text), max_tokens=7000)
        if not isinstance(out, dict):
            raise RuntimeError("the writer gave no answer")
        html = clean_html(out.get("html"))
        write_project(folder, html)
        report = check(folder, settings["cli"], runner)
        if not report["ok"] and report["errors"]:
            out2 = llm.chat_json(system, build_user(row, title, text, report["errors"], html), max_tokens=7000)
            if isinstance(out2, dict) and out2.get("html"):
                html = clean_html(out2.get("html"))
                write_project(folder, html)
                report = check(folder, settings["cli"], runner)
        if report["errors"]:
            # render anyway in best-effort mode: a lint error is often cosmetic; the row keeps the report either way
            log.warning("%s: %d check error(s) remain; rendering best-effort", row["id"], len(report["errors"]))
        video = render(folder, settings["cli"], row.get("resolution") or "portrait", runner)
        data = video.read_bytes()
        path = f"motion/{row['id']}.mp4"
        url = db.upload_generated(store, path, data, "video/mp4")
        poster_url = ""
        jpg = poster(video, runner)
        if jpg:
            poster_url = db.upload_generated(store, f"motion/{row['id']}.jpg", jpg, "image/jpeg")
        store.table(TABLE).update({
            "status": "done", "title": str(out.get("title") or "")[:160], "html": html, "check_report": report,
            "video_path": path, "video_url": url, "poster_url": poster_url, "bytes": len(data),
            **probe(video, runner),
            "model": getattr(llm, "last_model", "") or "", "error": "",
        }).eq("id", row["id"]).execute()
        db.log_event(store, "info", "media", "motion.done", f"Motion siap: {(out.get('title') or row.get('brief') or '')[:80]}",
                     ref_table=TABLE, ref_id=row["id"])
        return True
    except Exception as exc:  # noqa: BLE001 - the row records it
        err = f"{type(exc).__name__}: {str(exc)[:600]}"
        final = int(row.get("attempts") or 0) >= MAX_ATTEMPTS or isinstance(exc, ValueError)
        store.table(TABLE).update({"status": "error" if final else "pending", "error": err}).eq("id", row["id"]).execute()
        log.warning("%s: %s", row["id"], err)
        return False
    finally:
        if workdir is None:
            shutil.rmtree(folder.parent, ignore_errors=True)


def run(store: Any, llm: Any, *, runner: Any = subprocess.run, now: datetime | None = None) -> dict[str, int]:
    settings = load_settings(store)
    rows = claim(store)
    done = sum(process(store, llm, r, settings, runner=runner, now=now) for r in rows)
    return {"claimed": len(rows), "done": done, "failed": len(rows) - done}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    store = db.client()
    llm = None
    try:
        api_status.attach(store, "media")
        llm = LLM(ai_config.llm_for(store))
    except Exception as exc:  # noqa: BLE001
        log.warning("no LLM: %s", exc)
    counts = run(store, llm)
    log.info("motion: %s", counts)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as fh:
            fh.write("## Motion\n" + "\n".join(f"- {k}: {v}" for k, v in counts.items()) + "\n")
    print(json.dumps(counts))
    return 0 if not counts["failed"] else 1


if __name__ == "__main__":
    sys.exit(main())
