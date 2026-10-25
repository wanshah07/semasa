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

from . import ai_config, api_status, db, fetch, motion_styles
from . import voice as voice_mod
from .llm import LLM
from .repos import GitHub

log = logging.getLogger("semasa.motion")
TABLE = "semasa_motions"
SETTINGS_KEY = "motion"
CLI_VERSION = "0.8.188"
MAX_ATTEMPTS = 2
MAX_HTML = 60_000
# the whole film is one JSON answer, and a thinking model reasons first: 7000 was eaten by reasoning alone on 24 Oct 2026
WRITER_TOKENS = 20_000
SCRIPT_TOKENS = 6_000
# the presenter (Wan, 24 Oct 2026: "add mascot looks like talking, and make sure got voice or audio"): the poses in
# rules/cards.json, served from web/public/cards/mascots; the mouth sits at this fraction of the picture (x, y), measured
# by eye on each pose, and opens on every word of the narration
MASCOT_DIR = Path(__file__).resolve().parents[2] / "web" / "public" / "cards" / "mascots"
MOUTH = {"wave": (0.55, 0.20), "point": (0.55, 0.30), "confused": (0.54, 0.22), "shocked": (0.60, 0.24)}
SCENE_GAP = 0.35                        # seconds of air between two narrated scenes
SCENE_MIN = 2.5                         # a scene is never shorter than this, whatever the voice says
VOICE_PAD = 0.6                         # a scene stays up this long after its last word
STYLE_MAX = 9_000                      # characters of a style repo handed to the writer
STYLE_FILES = ("SKILL.md", "skills/SKILL.md", "STYLE.md", "DESIGN.md", "frame.md", "FRAME.md", "AGENTS.md", "CLAUDE.md")
SIZES = {"portrait": (1080, 1920), "landscape": (1920, 1080), "square": (1080, 1080)}
GSAP = "https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"
PALETTE = {"regulab": {"ground": "#e5f6ed", "ink": "#143e35", "accent": "#287b65", "accent2": "#fff7e6"},
           "linkedin": {"ground": "#111827", "ink": "#f9fafb", "accent": "#34d399", "accent2": "#f472b6"}}
# the words on screen (Wan, 24 Oct 2026: "choice for english, malay, or english + malay version"); the default follows the stream
LANGUAGE = {
    "bm": ("ms", "Bahasa Malaysia (Malaysian, never Indonesian)"),
    "en": ("en", "English"),
    "both": ("ms", "BOTH languages on every scene: the Bahasa Malaysia line first and its English line directly under it, "
                   "a little smaller and in the second accent colour; the title in both; the source line once"),
}
VOICE = {
    "regulab": "ws.regulab, a Malaysian regulatory consultancy speaking Bahasa Malaysia (Malaysian, never Indonesian: boleh not "
               "bisa, ubat not obat, syarikat not perusahaan) in a warm, plain BM-mix voice to SME owners.",
    "linkedin": "a named Malaysian chemist speaking English to peers on LinkedIn: precise, plain, no hype.",
}
# the same voices when the film's language is not the stream's own (24 Oct 2026: an English film for ws.regulab came out
# with Malay narration, because the brand line above said "speaking Bahasa Malaysia" and the writer obeyed it)
VOICE_EN = {
    "regulab": "ws.regulab, a Malaysian regulatory consultancy speaking warm, plain English to SME owners.",
    "linkedin": VOICE["linkedin"],
}
VOICE_BM = {
    "regulab": VOICE["regulab"],
    "linkedin": "a named Malaysian chemist speaking Bahasa Malaysia (Malaysian, never Indonesian) to peers: precise, plain, "
                "no hype.",
}


def voice_line(stream: str, lang: str) -> str:
    """The brand voice in the language the film is in, so the voice line never contradicts the language line."""
    table = VOICE_EN if lang == "en" else VOICE_BM
    return table.get(stream, table["regulab"])

SYSTEM = """You write a short motion-graphics video as ONE self-contained HTML file for HyperFrames (HTML rendered to video by
seeking a paused GSAP timeline frame by frame). Answer with ONE JSON object: {{"title": "<short title>", "html": "<the whole
index.html as a string>"}}. Nothing else.

THE CONTRACT (a render fails or looks wrong if any is broken):
1. The file starts with <!doctype html>, <html lang="{lang}" data-resolution="{resolution}">, a <meta name="viewport"
   content="width={w}, height={h}">, and loads GSAP with exactly: <script src="{gsap}"></script>. No other script, stylesheet,
   font or network request. html, body are {w}px by {h}px, overflow hidden, with the film's background.
2. The root is <div id="root" data-composition-id="main" data-start="0" data-duration="{seconds}" data-width="{w}"
   data-height="{h}"> and holds every scene. The video's length is the root's data-duration: {seconds:g} seconds.
3. Every timed element has class="clip", data-start and data-duration in seconds, a stable id, and shows over
   [start, start + duration). Land an end state just before its end. Elements are written in the HTML, never made by script.
4. One paused timeline, registered AFTER its tweens: const tl = gsap.timeline({{ paused: true }}); ... ;
   window.__timelines["main"] = tl; tl.seek(0); Position every tween with an absolute time as the last argument.
5. No Date.now(), no Math.random(), no fetch, no timers, no repeat: -1, no <video>, <audio> or <img>. Everything visible is a
   function of timeline time. Draw with CSS only: type, shapes, gradients, borders, simple SVG written inline.{background}
6. Never tween display, visibility or autoAlpha on a .clip; animate a child. Animate transforms and opacity, never left/top/
   width/height. No CSS transform on an element GSAP transforms.
7. Fonts: font-family: "Inter", system-ui, -apple-system, "Segoe UI", sans-serif (no @font-face). Keep all content inside the
   central 90% of the frame; key text inside the central 80%. Type at least 44px on a 1080-wide frame.
8. Frame 0 already shows the title (it is the social thumbnail): do not enter from an empty frame.

THE FILM: 3 to 6 scenes for {seconds:g} seconds: a hook (the title, big), two to four points (one idea each, short lines,
numbers big), and a closing card with the source line "{source_line}" in small type. Motion: eases power3.out / power2.inOut,
0.4 to 0.8 s entrances, staggered lines, a slow background drift, punchy but readable; every line stays on screen at least 2.5 s.
Palette: background {ground}, text {ink}, accent {accent}, second accent {accent2}.
VOICE: {voice}
RULES: no website, no URL, no handle, no hashtag, no emoji on screen; never invent a fee, date, number or
clause that the brief did not give; finish on the standalone brand outro. Write the words in {language}.
{extra}"""


SCRIPT_SYSTEM = """You plan a short narrated motion-graphics video. Answer with ONE JSON object:
{{"title": "<short title>", "scenes": [{{"kicker": "<2-3 words, upper case label>", "heading": "<the line, big>",
"lines": ["<short supporting line>", "..."], "narration": "<what the presenter SAYS over this scene, spoken, 1-3 sentences>",
"mascot": "wave|point|confused|shocked"}}]}}. Nothing else.

Plan ONLY the teaching scenes, not the outro (the worker appends that). Hook -> Fact -> Why -> Solution,
combined into 1–4 concise scenes for about {seconds:g} seconds INCLUDING the worker's 3-second outro.
Narration is spoken {language}: plain, warm, short sentences, about
{words} words in all (2.3 words a second), never reading the headings word for word, no URL, no
handle, no hashtag; never invent a fee, date, number or clause the brief did not give. The on-screen lines are {lines}.
Pick the presenter's pose per scene: wave for a greeting or the close, point for a fact with numbers, confused for a
doubt or a myth, shocked for a warning.
NARRATION LANGUAGE: {language}. Every spoken word of every narration is in {language}; a product name may stay as it is.
VOICE: {voice}
{extra}"""


def build_script_system(row: dict[str, Any], extra: str) -> str:
    stream = row.get("stream") or "regulab"
    lang = language_of(row)
    seconds = motion_styles.duration(row)
    spoken = {"bm": "Bahasa Malaysia (Malaysian, never Indonesian)", "en": "English", "both": "Bahasa Malaysia"}[lang]
    lines = {"bm": "in Bahasa Malaysia", "en": "in English",
             "both": "in Bahasa Malaysia with the English line after it, in the same string, separated by ' / '"}[lang]
    return SCRIPT_SYSTEM.format(seconds=seconds, language=spoken, words=max(1, int(max(0, seconds - 3) * 2.3)), lines=lines,
                                voice=voice_line(stream, lang),
                                extra=(("WAN'S OWN INSTRUCTIONS:\n" + extra + "\n") if extra else "") + motion_styles.prompt(row))


def plan_scenes(llm: Any, row: dict[str, Any], extra: str, src_title: str, src_text: str,
                style: tuple[str, str] = ("", "")) -> dict[str, Any]:
    """The writer's plan: title and scenes with on-screen words, narration and a pose. Raises when it gives none."""
    out = llm.chat_json(build_script_system(row, extra), build_user(row, src_title, src_text, style=style),
                        max_tokens=SCRIPT_TOKENS)
    scenes = [sc for sc in ((out or {}).get("scenes") or [])
              if isinstance(sc, dict) and (sc.get("heading") or sc.get("narration"))]
    if not isinstance(out, dict) or not scenes:
        raise RuntimeError("the writer gave no script")
    clean = []
    for i, sc in enumerate(scenes[:6]):
        clean.append({"id": f"s{i + 1}", "kicker": str(sc.get("kicker") or "")[:40],
                      "heading": str(sc.get("heading") or "")[:160],
                      "lines": [str(x)[:200] for x in (sc.get("lines") or []) if str(x).strip()][:4],
                      "narration": " ".join(str(sc.get("narration") or "").split())[:600],
                      "mascot": sc.get("mascot") if sc.get("mascot") in MOUTH else "wave"})
    clean.append({"id": "brand-outro", "kicker": "", "heading": "Follow for more tips!", "lines": [],
                  "narration": "Follow us for more.", "mascot": ""})
    return {"title": str(out.get("title") or "")[:160], "scenes": clean}


def voice_scenes(scenes: list[dict[str, Any]], language: str, choice: str, folder: Path, *, speak: Any = None,
                 runner: Any = subprocess.run) -> tuple[list[dict[str, Any]], float, str]:
    """Record each scene's narration and fix the timeline to it: (scenes with start/duration/audio/words, total seconds,
    note). With choice 'off', or when the voice cannot be made, the scenes are timed evenly and carry no audio."""
    if choice == "kitten" and language != "en":
        raise ValueError("VoiceStudio KittenTTS supports English only; pick English or an Edge voice")
    speak = speak or voice_mod.speak
    name = voice_mod.voice_for(language, choice) if choice != "off" else ""
    t = 0.0
    note = f"voice: {name}" if name else "no voice"
    for i, sc in enumerate(scenes):
        sc.update(start=round(t, 2), audio="", words=[])
        dur = 0.0
        if name and sc.get("narration"):
            rel = f"assets/voice-{i + 1}.mp3"
            try:
                got = speak(sc["narration"], name, folder / rel, runner)
                sc["audio"], sc["words"], sc["audio_s"] = rel, got["words"], got["duration"]
                dur = float(got["duration"]) + VOICE_PAD
            except Exception as exc:  # noqa: BLE001 - a scene without its voice is still a scene
                if choice == "kitten":
                    raise RuntimeError(str(exc)) from exc
                log.warning("voice not made for scene %d: %s", i + 1, str(exc)[:160])
                note = f"voice failed ({str(exc)[:80]})"
                name = ""
        sc["duration"] = round(max(SCENE_MIN, dur or 3.0), 2)
        t += sc["duration"] + SCENE_GAP
    total = round(t - SCENE_GAP, 2)
    return scenes, total, note


def fit_scenes(scenes: list[dict[str, Any]], seconds: float) -> tuple[list[dict[str, Any]], float]:
    """Fit pauses, never speech. Reserve 3s for the final CTA; fail with actionable scope advice."""
    teaching, outro = scenes[:-1], scenes[-1]
    available = seconds - motion_styles.OUTRO_SECONDS
    floors = [max(.7, float(sc.get("audio_s") or 0) + .15) for sc in teaching]
    if not teaching or sum(floors) > available or float(outro.get("audio_s") or 0) > 3:
        raise ValueError("Narration cannot fit this duration including the outro; choose 30/60s or a narrower micro-topic")
    slack = (available - sum(floors)) / len(teaching)
    start = 0.0
    for sc, floor in zip(teaching, floors, strict=True):
        sc.update(start=round(start, 3), duration=round(floor + slack, 3))
        start += floor + slack
    outro.update(start=available, duration=3, mascot="")
    return scenes, seconds


def plan_text(scenes: list[dict[str, Any]]) -> str:
    """What the HTML writer is told: the scenes with their FIXED times and words."""
    rows = []
    for sc in scenes:
        rows.append(f"- {sc['id']}: data-start=\"{sc['start']:g}\" data-duration=\"{sc['duration']:g}\" · "
                    f"kicker \"{sc['kicker']}\" · heading \"{sc['heading']}\" · "
                    f"lines {json.dumps(sc.get('lines') or [], ensure_ascii=False)}")
    return "\n".join(rows)


def mascot_layer(scenes: list[dict[str, Any]], total: float, w: int, h: int) -> tuple[str, str]:
    """(markup, script) for the presenter and the voice: one <img> per scene pose in the lower-left of the frame, a mouth
    that opens on each word, a gentle bob, and one <audio> clip per narrated scene. Added by the worker AFTER the writer,
    so the film never loses a word to the character."""
    size = int(w * 0.34) if w < h else int(h * 0.42)
    parts, audio, script = [], [], []
    for sc in scenes:
        if sc.get("audio"):
            # the slot is the recording's own length (hyperframes check: a longer slot is "shortened to the media length")
            audio.append(f'<audio class="clip" id="sv-{sc["id"]}" src="{sc["audio"]}" data-start="{sc["start"]:g}" '
                         f'data-duration="{float(sc.get("audio_s") or sc["duration"]):g}" data-volume="1"></audio>')
        if sc.get("id") == "brand-outro":
            continue
        pose = sc.get("mascot") or "wave"
        mx, my = MOUTH.get(pose, MOUTH["wave"])
        box = f"position:absolute;left:{int(w * 0.04)}px;bottom:{int(h * 0.05)}px;width:{size}px;height:{int(size * 4 / 3)}px;"
        img = ("position:absolute;inset:0;width:100%;height:100%;object-fit:contain;"
               "filter:drop-shadow(0 18px 30px rgba(0,0,0,.45));")
        mouth = (f"position:absolute;left:{mx * 100:.1f}%;top:{my * 100:.1f}%;width:4.2%;height:2.4%;margin-left:-2.1%;"
                 "margin-top:-1.2%;border-radius:50%;background:#3a1616;transform:scaleY(.2);transform-origin:50% 50%;")
        parts.append(
            f'<div class="clip sm-scene" id="sm-{sc["id"]}" data-start="{sc["start"]:g}" data-duration="{sc["duration"]:g}" '
            f'style="position:absolute;left:0;top:0;width:{w}px;height:{h}px;pointer-events:none;z-index:40;">'
            f'<div class="sm-wrap" style="{box}"><img src="assets/mascot-{pose}.webp" alt="" style="{img}">'
            f'<div class="sm-mouth" data-scene="{sc["id"]}" style="{mouth}"></div></div></div>')
    words = [[round(sc["start"] + ws, 3), round(sc["start"] + we, 3), sc["id"]]
             for sc in scenes for ws, we, _ in (sc.get("words") or [])]
    script.append("<script>(function(){var T=window.__timelines&&window.__timelines.main;if(!T)return;"
                  f"var W={json.dumps(words)};var mouths={{}};"
                  "document.querySelectorAll('.sm-mouth').forEach(function(m){mouths[m.dataset.scene]=m;});"
                  "W.forEach(function(w){var m=mouths[w[2]];if(!m)return;T.set(m,{scaleY:1},w[0]);"
                  "T.set(m,{scaleY:.2},Math.max(w[0]+.06,w[1]));});"
                  f"var total={total};document.querySelectorAll('.sm-wrap').forEach(function(el){{for(var t=0;t<total;t+=0.8){{"
                  "T.to(el,{y:-6,duration:.4,ease:'sine.inOut'},t);T.to(el,{y:0,duration:.4,ease:'sine.inOut'},t+.4);}});"
                  "T.seek(0);})();</script>")
    return "\n".join(audio + parts), "\n".join(script)


def inject_layers(html: str, scenes: list[dict[str, Any]], total: float, w: int, h: int, mascot: bool) -> str:
    """Put the voice clips (and the presenter, when wanted) into the writer's film: inside the root composition, with the
    mouth script at the end of the body, after the writer's own timeline is registered."""
    markup, script = mascot_layer(scenes, total, w, h)
    if not mascot:
        markup = "\n".join(line for line in markup.split("\n") if line.startswith("<audio"))
        script = ""
    m = re.search(r"<div\b[^>]*\bid=[\"']root[\"'][^>]*>", html)
    if not m:
        raise ValueError("the composition has no #root")
    if any(sc.get("id") == "brand-outro" for sc in scenes):
        start = total - 3
        markup += (f'<div class="clip" id="wan-brand-final" data-start="{start:g}" data-duration="3" '
                   f'style="position:absolute;inset:0;z-index:100;background:#e5f6ed;display:flex;flex-direction:column;'
                   f'align-items:center;justify-content:center;gap:{w * .04:g}px;">'
                   f'<img src="assets/official-logo-transparent.png" alt="" style="width:64%;height:auto;object-fit:contain;">'
                   f'<div style="color:#143e35;font-family:Inter,system-ui,sans-serif;font-size:{w * .05:g}px;'
                   'text-align:center;">Follow for more tips!</div></div>')
    out = html[:m.end()] + "\n" + markup + "\n" + html[m.end():]
    out = re.sub(r'(<div\b[^>]*\bid=[\"\']root[\"\'][^>]*data-duration=)[\"\'][^\"\']+[\"\']',
                 lambda match: match[1] + f'"{total:g}"', out, count=1)
    if script:
        out = re.sub(r"</body>", script + "\n</body>", out, count=1) if "</body>" in out else out + script
    return out


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


def style_words(store: Any, gh: GitHub | None, row: dict[str, Any]) -> tuple[str, str]:
    """(name, text) of the motion repo chosen as the style: its library summary and how-to-run, then its README and any
    skill/style file it carries (SKILL.md, DESIGN.md, frame.md ...). Read only, never run; ('', '') when none is chosen or
    it cannot be read. The writer is told it is a STYLE reference: patterns, palette, pacing, never its media or scripts."""
    rid = row.get("style_repo_id")
    if not rid:
        return "", ""
    try:
        rows = store.table("semasa_repo_library").select("*").eq("id", rid).execute().data or []
    except Exception as exc:  # noqa: BLE001
        log.info("style repo not read (%s)", str(exc)[:120])
        return "", ""
    if not rows:
        return "", ""
    lib = rows[0]
    name = lib.get("full_name") or lib.get("url") or str(rid)
    parts = [f"{name}: {lib.get('summary_en') or lib.get('summary_bm') or lib.get('description') or ''}".strip()]
    if lib.get("how_to_run"):
        parts.append("How it runs: " + str(lib["how_to_run"]))
    if gh is not None and lib.get("full_name"):
        base = f"/repos/{lib['full_name']}"
        branch = lib.get("default_branch") or "main"
        readme = gh.maybe(f"{base}/readme", raw=True, default="") or ""
        if readme:
            parts.append("README:\n" + readme[:STYLE_MAX // 2])
        for f in STYLE_FILES:
            text = gh.maybe(f"{base}/contents/{f}", {"ref": branch}, raw=True, default="") or ""
            if text:
                parts.append(f"{f}:\n{text[:STYLE_MAX // 3]}")
    elif lib.get("readme_excerpt"):
        parts.append("README:\n" + str(lib["readme_excerpt"]))
    return name, "\n\n".join(parts)[:STYLE_MAX]


BACKGROUND = """
   ONE picture exists for you at {path}: use it ONLY as a CSS background-image (url({path}), background-size: cover) on a
   full-frame element at the bottom of the stack, under a dark gradient scrim so the type stays readable, with a slow scale or
   drift tween.
   No other file exists: do not reference any other asset."""


def language_of(row: dict[str, Any]) -> str:
    """bm | en | both: the row's own choice, else the stream's language (rows written before 045 have no column)."""
    lang = str(row.get("language") or "").strip().lower()
    if lang in LANGUAGE:
        return lang
    return "en" if (row.get("stream") or "regulab") == "linkedin" else "bm"


def build_system(row: dict[str, Any], extra: str, background: str = "", seconds: float | None = None,
                 presenter: bool = False) -> str:
    stream = row.get("stream") or "regulab"
    html_lang, language = LANGUAGE[language_of(row)]
    if presenter:
        extra = (extra + "\n" if extra else "") + ("THE PRESENTER: a character stands in the lower-left 34% of the frame, added "
                                                   "after you; keep the bottom 36% of the frame free of text on every scene.")
    res = row.get("resolution") or "portrait"
    w, h = SIZES.get(res, SIZES["portrait"])
    pal = PALETTE.get(stream, PALETTE["regulab"])
    return SYSTEM.format(lang=html_lang, resolution=res, w=w, h=h, gsap=GSAP,
                         seconds=(seconds if seconds else motion_styles.duration(row)),
                         source_line=row.get("source_line") or "Sumber: lihat kapsyen",
                         voice=voice_line(stream, language_of(row)),
                         language=language,
                         extra=(("WAN'S OWN INSTRUCTIONS:\n" + extra + "\n") if extra else "")
                         + motion_styles.prompt(row, seconds),
                         background=BACKGROUND.format(path=background) if background else "", **pal)


def make_background(store: Any, row: dict[str, Any], folder: Path, provider: Any = None) -> tuple[str, str]:
    """(path relative to the project, note) of one picture drawn by the page's image slot (KiosAPI, OpenAI, Cloudflare or
    Replicate, whichever Wan set), written under assets/. ('', note) when it cannot be made: the video is made without it."""
    try:
        if provider is None:
            from .config import MediaSettings
            from .media_generator import make_provider
            s = ai_config.media_for(store, MediaSettings.load())
            provider = make_provider(s.provider, s)
        words = " ".join(str(row.get("brief") or "").split())[:300]
        prompt = ("An abstract, cinematic background plate for a motion-graphics video about: " + words +
                  ". Soft depth, calm dark tones, plenty of empty space for large type. "
                  "No text, no letters, no logos, no people.")
        gen = provider.generate_from_text(prompt, {})
        ext = gen.extension if gen.extension != "bin" else "png"
        rel = f"assets/bg.{ext}"
        (folder / "assets").mkdir(parents=True, exist_ok=True)
        (folder / rel).write_bytes(gen.data)
        return rel, f"background: {gen.model} via {getattr(provider, 'name', 'image slot')}"
    except Exception as exc:  # noqa: BLE001 - a missing picture never stops the video
        log.warning("background not made: %s", str(exc)[:200])
        return "", f"background not made: {str(exc)[:120]}"


def build_user(row: dict[str, Any], src_title: str, src_text: str, findings: list[dict[str, Any]] | None = None,
               previous: str = "", style: tuple[str, str] = ("", "")) -> str:
    parts = [f"BRIEF: {row.get('brief') or '(none)'}"]
    if style[1]:
        parts.append(f"STYLE REFERENCE (the motion repo {style[0]}): follow its visual language, scene patterns, pacing, type "
                     "and palette ideas. It is a reference, not a dependency: use none of its files, media, fonts or scripts, "
                     "and keep the contract above.\n" + style[1])
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


def write_project(folder: Path, html: str, poses: set[str] | None = None) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "index.html").write_text(html, encoding="utf-8")
    (folder / "assets").mkdir(exist_ok=True)
    shutil.copyfile(motion_styles.LOGO, folder / "assets" / motion_styles.LOGO.name)
    for pose in poses or ():
        src = MASCOT_DIR / f"{pose}.webp"
        if src.is_file():
            (folder / "assets").mkdir(exist_ok=True)
            shutil.copyfile(src, folder / "assets" / f"mascot-{pose}.webp")
        else:
            log.warning("mascot pose %s not found at %s", pose, src)
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


def mix_music(video: Path, scenes: list[dict[str, Any]], seconds: float, runner: Any = subprocess.run) -> Path:
    """Keep the rendered video; mux original v8 melody + recorded stems, with explicit speech ducking and fades."""
    music = motion_styles.RULES / "music-v8.mp3"
    voiced = [sc for sc in scenes if sc.get("audio")]
    folder = video.parent.parent if video.parent.name == "renders" else video.parent
    out = video.with_name("motion-mixed.mp4")
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(video), "-stream_loop", "-1", "-i", str(music)]
    for sc in voiced:
        cmd += ["-i", str(folder / sc["audio"])]
    active = "+".join(f"between(t,{sc['start']:g},{sc['start'] + sc['audio_s']:g})" for sc in voiced) or "0"
    filters = [f"[1:a]atrim=duration={seconds:g},asetpts=PTS-STARTPTS,"
               f"volume='if(gt({active},0),0.16,0.27)':eval=frame,afade=t=in:d=0.2,"
               f"afade=t=out:st={max(0, seconds - 1.15):g}:d=1.15[music]"]
    for i, sc in enumerate(voiced):
        filters.append(f"[{i + 2}:a]adelay={round(sc['start'] * 1000)}:all=1[v{i}]")
    inputs = "[music]" + "".join(f"[v{i}]" for i in range(len(voiced)))
    filters.append(f"{inputs}amix=inputs={len(voiced) + 1}:normalize=0,alimiter=limit=0.95:level=0[a]")
    cmd += ["-filter_complex", ";".join(filters), "-map", "0:v:0", "-map", "[a]", "-c:v", "copy", "-c:a", "aac",
            "-b:a", "160k", "-t", f"{seconds:g}", "-movflags", "+faststart", str(out)]
    result = runner(cmd, capture_output=True, text=True, timeout=180)
    if result.returncode != 0 or not out.is_file():
        raise RuntimeError("Music mix failed: " + (result.stderr or "no output")[-400:])
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
            workdir: Path | None = None, now: datetime | None = None, gh: GitHub | None = None,
            picture_provider: Any = None, speak: Any = None) -> bool:
    now = now or datetime.now(UTC)
    folder = (workdir or Path(tempfile.mkdtemp(prefix="motion-"))) / str(row["id"])[:8]
    try:
        if llm is None:
            raise RuntimeError("no AI writer: set a reader key in Tetapan → Tetapan AI")
        title, text = source_words(row.get("source_url") or "")
        style = style_words(store, gh, row)
        bg_path, bg_note = ("", "")
        if row.get("ai_background"):
            folder.mkdir(parents=True, exist_ok=True)
            bg_path, bg_note = make_background(store, row, folder, provider=picture_provider)
        # the voice first (Wan, 24 Oct 2026): the writer plans the scenes, each narration is recorded, and the film is
        # written to those exact times; with the voice off the plan still fixes the scenes and nothing is recorded
        plan = plan_scenes(llm, row, settings.get("prompt") or "", title, text, style=style)
        want_mascot = bool(row.get("mascot")) and row.get("mascot") in MOUTH
        scenes, total, voice_note = voice_scenes(plan["scenes"], language_of(row), str(row.get("voice") or "male"), folder,
                                                 speak=speak, runner=runner)
        scenes, total = fit_scenes(scenes, motion_styles.duration(row))
        w, h = SIZES.get(row.get("resolution") or "portrait", SIZES["portrait"])
        system = build_system(row, settings.get("prompt") or "", bg_path, seconds=total, presenter=want_mascot)
        fixed = ("SCENES, FIXED: the voice is already recorded to these times. One .clip per scene with EXACTLY this id, "
                 "data-start and data-duration; show these words (you may add a short extra line, never a fact):\n"
                 + plan_text(scenes))
        out = llm.chat_json(system, build_user(row, title, text, style=style) + "\n\n" + fixed, max_tokens=WRITER_TOKENS)
        if not isinstance(out, dict):
            raise RuntimeError("the writer gave no answer")
        out.setdefault("title", plan.get("title"))
        html = clean_html(out.get("html"))
        poses = {sc.get("mascot") or "wave" for sc in scenes} if want_mascot else set()
        write_project(folder, inject_layers(html, scenes, total, w, h, want_mascot), poses)
        report = check(folder, settings["cli"], runner)
        if not report["ok"] and report["errors"]:
            out2 = llm.chat_json(system, build_user(row, title, text, report["errors"], html, style=style) + "\n\n" + fixed,
                                 max_tokens=WRITER_TOKENS)
            if isinstance(out2, dict) and out2.get("html"):
                html = clean_html(out2.get("html"))
                write_project(folder, inject_layers(html, scenes, total, w, h, want_mascot), poses)
                report = check(folder, settings["cli"], runner)
        if report["errors"]:
            # render anyway in best-effort mode: a lint error is often cosmetic; the row keeps the report either way
            log.warning("%s: %d check error(s) remain; rendering best-effort", row["id"], len(report["errors"]))
        style_line = (f"{style[0]}: {len(style[1])} characters read · " if style[1] else "") + motion_styles.resolve(row)["name"]
        video = render(folder, settings["cli"], row.get("resolution") or "portrait", runner)
        meta = probe(video, runner)
        if not 0 < meta["duration_s"] <= 60.5 or abs(meta["duration_s"] - total) > .5:
            raise ValueError("Rendered duration does not match selected duration; choose 30/60s or narrow the topic")
        video = mix_music(video, scenes, total, runner)
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
            **meta,
            "model": getattr(llm, "last_model", "") or "", "error": "",
            "style_note": " · ".join(x for x in (style_line, bg_note, voice_note,
                                               "original synthesized melody v8; faded and speech-ducked") if x),
            "script": [{k: sc.get(k) for k in ("id", "kicker", "heading", "lines", "narration", "mascot", "start", "duration")}
                       for sc in scenes],
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


def run(store: Any, llm: Any, *, runner: Any = subprocess.run, now: datetime | None = None,
        gh: GitHub | None = None) -> dict[str, int]:
    settings = load_settings(store)
    rows = claim(store)
    done = sum(process(store, llm, r, settings, runner=runner, now=now, gh=gh) for r in rows)
    return {"claimed": len(rows), "done": done, "failed": len(rows) - done}


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    store = db.client()
    llm = None
    try:
        api_status.attach(store, "media")
        llm = LLM(ai_config.llm_for(store, job="motion"))      # the page's own motion API first, then the team
    except Exception as exc:  # noqa: BLE001
        log.warning("no LLM: %s", exc)
    token = os.environ.get("REPOS_TOKEN") or os.environ.get("LANDING_REPO_TOKEN") or os.environ.get("GITHUB_TOKEN")
    counts = run(store, llm, gh=GitHub(token))
    log.info("motion: %s", counts)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as fh:
            fh.write("## Motion\n" + "\n".join(f"- {k}: {v}" for k, v in counts.items()) + "\n")
    print(json.dumps(counts))
    return 0 if not counts["failed"] else 1


if __name__ == "__main__":
    sys.exit(main())
