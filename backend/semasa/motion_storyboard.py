"""The storyboard of a Motion film, written by ChatGPT or Gemini (Wan, 7 Nov 2026: "storyboard from chatgpt and gemini";
the flow Scrape > Idea > Motion (storyboard) > Motion (Picture) > Motion).

Before this the "storyboard" was a filter over the writer's scenes and each picture's request was a template filled with the
scene's words. Now an AI writes the SHOT for every teaching scene: what the picture shows, in concrete visual terms, and its mood,
given the film's brief, the scenes (role, heading, lines, narration), the design look and the platform's tone. The picture makers
then draw THAT shot (motion_gpt_images.scene_prompt uses it), so the picture is directed rather than a restatement of the heading.

WHO WRITES IT, in order: ChatGPT (Wan's login, the same one that draws), then Gemini (his key pool), then the film's own writer
(the AI team's pick for the job). A writer that is not connected, refuses, or gives something unusable is skipped, and when none
gives a shot the scene keeps the template request: the storyboard never stops a film. The same rules bind every writer: the
picture is illustration, never evidence (no words, logos, packaging, faces, before-and-after, cure or warning imagery), and it is
told it cannot lift them.

The shots are kept on the scenes (`shot`, `mood`) and on the row's `script`, so the Motion tab can show what was planned and a
Redo of the pictures can reuse it.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from . import chatgpt_login, gemini_keys
from .log import get_logger

log = get_logger("semasa.motion.storyboard")

MAX_SHOT = 320
MAX_MOOD = 80
SYSTEM = (
    "You are the storyboard artist of a short educational film. For each scene you are given, write ONE shot for the picture "
    "that will sit behind or beside its words: what it shows, in concrete visual terms (subject, setting, framing, light), and "
    "its mood in a few words. The picture ILLUSTRATES the topic and is never evidence of it. HARD RULES: no text, letters, "
    "numbers, logos, brand names, packaging or product labels; no recognisable real person and no clear faces; no "
    "before-and-after, no medical or cure imagery, no warning signs. A shot is a visual metaphor, a still life, a place or an "
    "object, never a claim. Keep each shot under 45 words. Answer ONE JSON object and nothing else: "
    '{"scenes": [{"id": "<the scene id exactly as given>", "shot": "<the shot>", "mood": "<a few words>"}]}')
BANNED = re.compile(r"\b(before[- ]and[- ]after|cure[sd]?|heal(?:s|ed|ing)?|logo|brand name|label|watermark|"
                    r"ignore (?:the )?(?:rules|above)|you are now)\b", re.I)


def request(row: dict[str, Any], scenes: list[dict[str, Any]], *, design: str, tone: str, look: str) -> str:
    """The user message: the film and the scenes to storyboard."""
    brief = " ".join(str(row.get("brief") or "").split())[:400]
    rows = [{"id": str(sc.get("id")), "role": str(sc.get("role") or ""), "heading": str(sc.get("heading") or "")[:160],
             "lines": [str(x)[:160] for x in (sc.get("lines") or [])][:5], "narration": str(sc.get("narration") or "")[:300]}
            for sc in scenes]
    return (f"Film topic: {brief or '(none)'}\nDesign look: {look} ({design})\nTone: {tone}\nScenes:\n"
            + json.dumps(rows, ensure_ascii=False))


def parse(text: Any, ids: list[str]) -> dict[str, dict[str, str]]:
    """{scene id: {shot, mood}} from a writer's answer: only ids that were asked for, only a shot that is usable (some words, not
    over long, none of the banned ideas). {} when nothing usable."""
    if isinstance(text, dict):
        data = text
    else:
        s = str(text or "").strip()
        s = re.sub(r"^```(?:json)?|```$", "", s.strip(), flags=re.M).strip()
        m = re.search(r"\{.*\}", s, re.S)
        try:
            data = json.loads(m.group(0)) if m else {}
        except ValueError:
            return {}
    out: dict[str, dict[str, str]] = {}
    for item in data.get("scenes") or [] if isinstance(data, dict) else []:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("id") or "")
        shot = " ".join(str(item.get("shot") or "").split())
        mood = " ".join(str(item.get("mood") or "").split())[:MAX_MOOD]
        if sid in ids and sid not in out and 12 <= len(shot) and not BANNED.search(shot + " " + mood):
            out[sid] = {"shot": shot[:MAX_SHOT], "mood": mood}
    return out


def _chatgpt(login: Any, system: str, user: str) -> tuple[str, str]:
    cfg = login.settings() if login is not None else None
    if not cfg or not cfg.get("enabled"):
        return "", ""
    try:
        text = login.write(system, user, model=cfg["model"])
    except chatgpt_login.ChatGPTError as exc:
        _mark(login, False, str(exc))
        return "", f"ChatGPT: {str(exc)[:100]}"
    except Exception as exc:  # noqa: BLE001 - a storyboard never stops a film
        _mark(login, False, str(exc))
        return "", f"ChatGPT: {str(exc)[:100]}"
    _mark(login, True)        # a real call answered: the login is proven, not only its token refreshed (Wan, 7 Nov 2026)
    return text, ""


def _mark(login: Any, ok: bool, message: str = "") -> None:
    """Record on the login whether a real ChatGPT call answered; a bookkeeping failure never stops a film."""
    try:
        login.ok() if ok else login.failed(message)
    except Exception:  # noqa: BLE001
        pass


def _gemini(store: Any, gemini_llm: Any, system: str, user: str) -> tuple[Any, str]:
    """Gemini through the AI team's own candidate for this job (its key pool and model), or a stand-in in tests."""
    try:
        llm = gemini_llm if gemini_llm is not None else _gemini_llm(store)
        if llm is None:
            return "", ""
        return llm.chat_json(system, user, max_tokens=1500), ""
    except Exception as exc:  # noqa: BLE001
        return "", f"Gemini: {str(exc)[:100]}"


def _gemini_llm(store: Any) -> Any:
    from . import ai_team
    from .config import LLMSettings
    from .llm import LLM
    cand, _seed = gemini_keys.candidate(store, "motion", ai_team.LIVE, datetime.now(UTC))
    if not cand:
        return None
    return LLM(LLMSettings(provider="openai", api_key=cand["key"], base_url=cand["base_url"], model=cand["model"], timeout=120))


def write(store: Any, row: dict[str, Any], scenes: list[dict[str, Any]], *, login: Any = None, llm: Any = None,
          gemini_llm: Any = None, design: str = "bright-editorial", look: str = "",
          tone: str = "") -> tuple[dict[str, dict[str, str]], str]:
    """(the shots by scene id, a note). Tries ChatGPT, then Gemini, then the film's own writer; the first that gives a usable shot
    for at least one scene is used and the others are not asked. ({}, note) when none does."""
    todo = [sc for sc in scenes if sc.get("id") != "brand-outro" and (sc.get("heading") or sc.get("narration"))]
    ids = [str(sc.get("id")) for sc in todo]
    if not ids:
        return {}, ""
    user = request(row, todo, design=design, tone=tone, look=look)
    problems: list[str] = []
    text, why = _chatgpt(login, SYSTEM, user)
    if why:
        problems.append(why)
    got = parse(text, ids) if text else {}
    who = "ChatGPT"
    if not got:
        answer, why = _gemini(store, gemini_llm, SYSTEM, user)
        if why:
            problems.append(why)
        got, who = (parse(answer, ids) if answer else {}), "Gemini"
    if not got and llm is not None:
        try:
            got, who = parse(llm.chat_json(SYSTEM, user, max_tokens=1500), ids), "the film's writer"
        except Exception as exc:  # noqa: BLE001
            problems.append(f"writer: {str(exc)[:100]}")
    if not got:
        tail = f" ({'; '.join(problems)[:240]})" if problems else ""
        return {}, "Storyboard: no AI gave a shot, so each picture uses its template" + tail
    return got, f"Storyboard by {who}: {len(got)} of {len(ids)} scenes" + (f" ({'; '.join(problems)[:200]})" if problems else "")


def apply(scenes: list[dict[str, Any]], shots: dict[str, dict[str, str]]) -> None:
    """Keep each shot on its scene (`shot`, `mood`); a scene without one keeps nothing and uses the template."""
    for sc in scenes:
        got = shots.get(str(sc.get("id")))
        if got:
            sc["shot"], sc["mood"] = got["shot"], got["mood"]
