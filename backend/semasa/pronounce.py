"""What the voice is given to read (Wan, 10 Nov 2026: "make sure grammar always betul, audio dan voice pun betul").

The recorded voice reads text, not spelling: an SMS abbreviation, a symbol or an acronym is said wrongly or skipped. So the text
sent to the voice is made speakable first, while the words on screen and in the subtitles stay exactly as written:

  * SMS abbreviations written in a narration are expanded ("yg" -> "yang");
  * a symbol is said as a word ("%" -> "peratus" / "percent");
  * an acronym in the list `letters`, or any short all-capital word with no vowel, is said letter by letter ("NPRA" -> "N P R A");
  * anything in rules/motion/pronunciation.json's per-language table is replaced as written, so a word the voice gets wrong is
    fixed by editing that file.

It also checks the recording itself (`problem`): a clip that is silent, or far too fast or too slow for its words, is reported
so the worker can record it again with the other voice.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

FILE = Path(__file__).resolve().parents[2] / "rules" / "motion" / "pronunciation.json"
RULES: dict[str, Any] = json.loads(FILE.read_text(encoding="utf-8"))
LETTERS = {x.upper() for x in RULES.get("letters", [])}
VOWELS = set("AEIOU")
_CAPS = re.compile(r"(?<![\w])([A-Z]{2,6})(\d{0,5})(?![\w])")
_ABBR = RULES.get("abbreviations_bm", {})
_ABBR_RX = (re.compile(r"(?<![\w])(" + "|".join(sorted(map(re.escape, _ABBR), key=len, reverse=True)) + r")(?![\w])", re.I)
            if _ABBR else None)
MIN_WPS, MAX_WPS = 1.0, 5.2           # words a second a human can follow: outside it the clip is wrong, whatever the voice was


def expand_abbreviations(text: str, lang: str) -> str:
    """SMS spellings written out in full, Malay only (the first letter's case is kept). Words from Wan's own casual register
    (tak, dah, nak, korang, jom...) are not in the table and are never touched."""
    if lang not in ("bm", "both") or _ABBR_RX is None:
        return text

    def swap(m: re.Match[str]) -> str:
        full = _ABBR[m.group(1).lower()]
        return full[:1].upper() + full[1:] if m.group(1)[:1].isupper() else full
    return _ABBR_RX.sub(swap, text)


def speech_text(text: str, lang: str) -> str:
    """The text the voice reads. `lang` is bm | en | both (both is read in Malay)."""
    key = "en" if lang == "en" else "bm"
    out = expand_abbreviations(str(text or ""), lang)
    for src, dst in sorted((RULES.get(key) or {}).items(), key=lambda kv: -len(kv[0])):
        if src.isalpha():
            out = re.sub(rf"(?<![\w]){re.escape(src)}(?![\w])", dst, out, flags=re.I)
        else:
            out = out.replace(src, dst)

    def spell(m: re.Match[str]) -> str:
        word, digits = m.group(1), m.group(2)
        if word in LETTERS or not (set(word) & VOWELS):
            return " ".join(word) + (f" {digits}" if digits else "")
        return m.group(0)
    return " ".join(_CAPS.sub(spell, out).split())


def volume_db(path: Path, runner: Any = subprocess.run) -> float | None:
    """The clip's mean volume in dB from ffmpeg's volumedetect (None when it cannot be measured)."""
    try:
        p = runner(["ffmpeg", "-v", "info", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
                   capture_output=True, text=True, timeout=120)
        m = re.search(r"mean_volume:\s*(-?[\d.]+) dB", (p.stderr or "") + (p.stdout or ""))
        return float(m.group(1)) if m else None
    except Exception:  # noqa: BLE001
        return None


def problem(path: Path, text: str, seconds: float, runner: Any = subprocess.run) -> str:
    """"" when the recording is fit to use, else why not: silent, or a speed no listener can follow for that many words."""
    words = len(str(text or "").split())
    if words >= 3 and seconds > 0:
        wps = words / seconds
        if wps < MIN_WPS:
            return f"too slow ({wps:.1f} words a second): the clip is padded or stalled"
        if wps > MAX_WPS:
            return f"too fast ({wps:.1f} words a second): words were skipped"
    db = volume_db(path, runner)
    if db is not None and db < -50:
        return f"silent (mean volume {db:.0f} dB)"
    return ""
