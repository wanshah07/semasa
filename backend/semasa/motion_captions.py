"""The caption of a finished film on each platform it can go to (Wan, 26 Oct 2026: "make sure terus setkan caption ikut
platform").

Until now every platform started from the one long caption of the idea's draft, so Threads came up at 1,553 characters
against its 500. The worker now writes each platform's own caption when it finishes the film, from the film's own script, in
the film's language and its stream's voice, and fits it to the platform's limits in rules/compliance.json (the same file the
post editor and the publisher scan with). The page starts from them, Wan edits, and the publisher scans again before anything
is sent.

  write()  asks the writer for one caption per platform; on any failure it falls back to captions built from the script
  fit()    the deterministic part: at most the platform's characters and hashtags, cut at a paragraph or sentence, never mid-word

Nothing here raises: a film is never lost because its captions could not be written.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import Any

from . import antislop, compliance

log = logging.getLogger("semasa.motion_captions")

# how long each platform's caption is asked to be (the rule's own maximum is the hard stop, fit() enforces it)
SOFT = {"instagram": 900, "facebook": 1100, "threads": 420, "linkedin": 1400}
STYLE = {
    "instagram": "A hook in the first line (it is all that shows before 'more'), then two to four short paragraphs. Plain words.",
    "facebook": "Two to four short paragraphs for people who read. Plain words, a calm opening line.",
    "threads": "ONE tight post, the way a person talks. No paragraphs of explanation: the one fact that matters and why.",
    "linkedin": "First person: a named chemist writing to peers. Short paragraphs, the point first. Name the instrument, "
                "regulation or study that decides it (never a blog or a news site).",
}
SYSTEM = """You write the caption a finished short film is posted with, once for each platform. The film's script is below: the
caption says the same facts and nothing more.

VOICE: {voice}
LANGUAGE: {language}

For each platform write its own caption (never the same text twice; each is shaped for where it is read):
{platforms}

RULES (every one is checked before anything is posted):
- Only facts that are in the script. Never invent a number, name, date, clause, quote or source.
- No call to action ("follow", "click", "comment below", "DM us"), no website or link, no mention of Reddit, YouTube or TikTok.
- The hashtags go on the last line, at most the number given for the platform, none inside a sentence.
- Never go over a platform's character limit.

Answer with ONE JSON object only: {{"captions": {{{shape}}}}}{extra}"""


def hashtags_split(text: str) -> tuple[str, list[str]]:
    """`text` without its trailing hashtag line(s), and those hashtags in order."""
    lines = text.rstrip().split("\n")
    tags: list[str] = []
    while lines and lines[-1].strip() and all(w.startswith("#") for w in lines[-1].split()):
        tags = lines[-1].split() + tags
        lines.pop()
    return "\n".join(lines).rstrip(), list(dict.fromkeys(tags))


def _cut(body: str, budget: int) -> str:
    """`body` cut to `budget` characters at the last paragraph end, else sentence end, else word end that fits."""
    if len(body) <= budget:
        return body
    head = body[:budget]
    para = head.rfind("\n\n")
    if para >= budget * 0.4:
        return head[:para].rstrip()
    ends = [m.end() for m in re.finditer(r"[.!?](?=\s|$)", head)]
    if ends and ends[-1] >= budget * 0.4:
        return head[:ends[-1]].rstrip()
    head = body[:max(budget - 1, 1)]                       # room for the full stop that closes it
    space = head.rfind(" ")
    return (head[:space] if space > 0 else head).rstrip(" ,;:") + "."


def fit(text: str, stream: str, platform: str) -> str:
    """`text` shortened to the platform's limits: its character maximum and its hashtag count (rules/compliance.json)."""
    text = (text or "").strip()
    lim = (compliance.RULES["limits"].get(stream) or {}).get(platform) or {}
    hard, tags_max = int(lim.get("max") or 0), lim.get("hashtags")
    body, tags = hashtags_split(text)
    if tags_max is not None:
        tags = tags[:int(tags_max)]
    tail = ("\n\n" + " ".join(tags)) if tags else ""
    if hard and len(body) + len(tail) > hard:
        body = _cut(body, hard - len(tail))
    return (body + tail).strip()


def platforms_of(stream: str) -> list[str]:
    return list(compliance.RULES["platforms"].get(stream) or compliance.RULES["platforms"]["regulab"])


def from_script(title: str, scenes: list[dict[str, Any]], stream: str) -> dict[str, str]:
    """The fallback: the film's own words as a caption, fitted to each platform. The title is the hook, then every teaching
    scene's heading and lines in order (the intro and the closing brand scene are not facts)."""
    parts = [str(title or "").strip()]
    for sc in scenes:
        if sc.get("id") == "brand-outro":
            continue
        words = [str(sc.get("heading") or "").strip(), *[str(ln).strip() for ln in sc.get("lines") or []]]
        parts.append(" ".join(x for x in words if x))
    first, *rest = [p for p in parts if p]
    out = {}
    for plat in platforms_of(stream):
        soft = SOFT.get(plat, 900)
        body = first + ("\n\n" + "\n\n".join(rest) if rest else "")
        out[plat] = fit(_cut(body, soft), stream, plat)
    return out


def _script(title: str, scenes: list[dict[str, Any]]) -> str:
    lines = [f"TITLE: {title}"]
    for sc in scenes:
        if sc.get("id") == "brand-outro":
            continue
        lines.append(f"- {sc.get('heading') or ''}" + "".join(f"\n    {ln}" for ln in sc.get("lines") or []))
        if sc.get("narration"):
            lines.append(f"    (said: {str(sc['narration'])[:400]})")
    return "\n".join(lines)


def write(llm: Any, row: dict[str, Any], scenes: list[dict[str, Any]], title: str, *, lang: str, voice: str,
          speak_as: Callable[[str], str]) -> dict[str, str]:
    """One fitted caption per platform of the row's stream, in the film's language. Never raises."""
    stream = row.get("stream") or "regulab"
    plats = platforms_of(stream)
    fallback = from_script(title, scenes, stream)
    try:
        limits = compliance.RULES["limits"].get(stream) or {}
        spec = "\n".join(
            f"- {p}: {STYLE.get(p, '')} Under {min(SOFT.get(p, 900), int(limits.get(p, {}).get('max') or 9999))} "
            f"characters, at most {limits.get(p, {}).get('hashtags', 0)} hashtag(s)." for p in plats)
        language = {"bm": "Bahasa Malaysia (Malaysian, never Indonesian: boleh not bisa, ubat not obat, syarikat not perusahaan)",
                    "en": "English",
                    "both": "BOTH: the Bahasa Malaysia text first, then the English text, each about half the length"}[lang]
        system = SYSTEM.format(voice=voice, language=language, platforms=spec,
                               shape=", ".join(f'"{p}": "..."' for p in plats), extra=antislop.prompt_block())
        out = llm.chat_json(system, _script(title, scenes), max_tokens=1800) if llm else None
        got = (out or {}).get("captions") if isinstance(out, dict) else None
        if not isinstance(got, dict):
            return fallback
        result = {}
        for p in plats:
            text = got.get(p)
            result[p] = fit(speak_as(text.strip()), stream, p) if isinstance(text, str) and text.strip() else fallback[p]
        return result
    except Exception as exc:  # noqa: BLE001 - the film is done without them
        log.warning("film captions fell back to the script: %s", str(exc)[:160])
        return fallback
