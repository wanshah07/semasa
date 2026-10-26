"""The anti-slop filter for every text this system writes for the public: captions, clip captions, carousel and card words,
the words of a motion film, the ad copy of the fragrance tab.

The rules are the copywriting skill of github.com/miqdadbadjuber/anti-slop (v3.2.23, MIT; the skills are vendored in
.claude/skills/antislop*, Wan, 26 Oct 2026: "apply github miqdadbadjuber/anti-slop untuk buang AI slop dalam sistem").
Three pieces, one idea each:

  PROMPT   what the writers are told (appended to their system prompts), so the slop is not written in the first place
  clean()  the edits that are safe to make by machine on whatever still comes back: the em dash, a decorative emoji that
           opens a line, a chatbot closer, a filler phrase. Words are never added and no fact is touched
  tells()  the patterns that need a person (empty vocabulary, fake-candid openers, negative parallelism, weasel
           attribution), read from rules/compliance.json so the page's own scan and this module name the same tells; they
           are warnings in the post editor, never a block

Wan's own voice outranks the filter (the skill's own rule, R-37): the film hooks (Tahukah anda, Amaran, Berita terkini, Did
you know, Warning, Breaking news), the casual connecting sentences between scenes and the closing line stay as he asked.
"""

from __future__ import annotations

import re

from . import compliance

PROMPT = """WRITE LIKE A PERSON, NOT A MODEL (the anti-slop rules; they apply to every word you write, in Malay and in English):
- No em dash and no double hyphen: use a full stop or a comma. No emoji as a bullet or a heading. No whole clause in ALL CAPS.
- No empty vocabulary: unlock, elevate, empower, delve, showcase, testament, landscape, journey, robust, seamless, cutting-edge,
  revolutionary, game-changer, next-level, "in today's fast-paced world"; in Malay no "era baharu", "pengubah permainan",
  "kelas dunia", "tanpa had", "perjalanan anda". Say what the thing does, with a concrete detail from the SOURCE.
- No claim that something is a turning point, a new era or the future of anything. No "experts say" or "kajian menunjukkan"
  unless the SOURCE names who. Never invent a number, name, date, quote or citation to sound specific.
- No fake-candid opener ("Honestly?", "Let's be honest", "Here's the thing", "Real talk"), no announcing what you are about to say
  ("Let's dive in", "Here's what you need to know"), no chatbot closer ("I hope this helps", "Let me know if", "Harap membantu").
- No "not just X, it's Y" ("bukan sekadar X, malah Y"), no run of short dramatic fragments ("No templates. No defaults. No
  safety."), no forced list of three, no aphorism ("X is the language of Y"), no upbeat send-off that says nothing ("the future
  looks bright"). End on the last concrete fact.
- Name who does what: no passive with the actor missing when the actor is known, and no object that "understands" or "decides".
- Vary the sentence length. One short sentence for emphasis is fine; a row of them is not. Repeat the clearest word instead of
  cycling synonyms. No filler ("in order to", "it is important to note that").
- Keep a voice: plain, specific, a little warm. Cold and sterile text is as obvious as padded text."""

PROMPT_FILM = PROMPT + """
- A film keeps its hook (Tahukah anda / Amaran / Berita terkini; Did you know / Warning / Breaking news) and the short
  connecting sentences between scenes: those are the owner's own voice, not slop."""

_EMOJI = r"[\U0001F000-\U0001FAFF☀-➿⭐⬆✅❌‼⁉️‍]"
_LINE_EMOJI = re.compile(rf"(?m)^[ \t]*(?:{_EMOJI})+[ \t]*")
_DASH = re.compile(r"\s*(?:—|--+| – )\s*")
_CLOSER = re.compile(
    r"(?:(?<=[.!?])\s+|^)(?:I hope this helps|Hope this helps|Let me know if[^.!?\n]*|Would you like me to[^.!?\n]*|"
    r"Feel free to (?:reach out|ask)[^.!?\n]*|Harap (?:ini )?membantu|Semoga (?:ini )?bermanfaat)[.!?]*\s*$", re.I)
_OPENER = re.compile(r"^\s*(?:Let'?s dive in|Here'?s what you need to know|Without further ado)[.!:,]?\s*", re.I)
_FILLERS = (
    (re.compile(r"\bin order to\b", re.I), "to"),
    (re.compile(r"\bdue to the fact that\b", re.I), "because"),
    (re.compile(r"\bat this point in time\b", re.I), "now"),
    (re.compile(r"\bdalam usaha untuk\b", re.I), "untuk"),
    (re.compile(r"\bbagi tujuan untuk\b", re.I), "untuk"),
)
_LEAD_INS = re.compile(r"(^|[.!?]\s+|)(?:it is important to note that|adalah penting untuk diingat bahawa),?\s+(\w)", re.I)


def _as_cased(match: re.Match[str], to: str) -> str:
    """`to`, starting with a capital when the words it replaces did (a sentence that began with them keeps beginning)."""
    return to[:1].upper() + to[1:] if match.group(0)[:1].isupper() else to


def clean(text: str) -> str:
    """`text` with the machine-safe slop taken out. Nothing is added, no number or name is changed, and a text with none of
    these in it comes back as it was."""
    if not text:
        return text
    out = _DASH.sub(", ", text)
    out = re.sub(r",\s*([.,;:!?])", r"\1", out)                       # ", ." left by a dash at the end of a clause
    out = re.sub(r"(?m)^[ \t]*,\s*", "", out)                         # a dash that opened a line
    out = _LINE_EMOJI.sub("", out)
    out = _OPENER.sub("", out)
    for rx, to in _FILLERS:
        out = rx.sub(lambda m, to=to: _as_cased(m, to), out)
    out = _LEAD_INS.sub(lambda m: m.group(1) + (m.group(2).upper() if m.group(1) or m.start() == 0 else m.group(2)), out)
    for _ in range(3):                                                        # a closer can be several sentences long
        shorter = _CLOSER.sub("", out)
        if shorter == out:
            break
        out = shorter.rstrip()
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"(?m)[ \t]+$", "", out)
    return out.strip() if out != text else text


def tells(text: str) -> list[str]:
    """The tells that need a person (the labels of the `tell` entries in rules/compliance.json) found in `text`."""
    return [r["label"] for r in compliance.RULES["soft"]
            if r.get("tell") and re.search(r["re"], text, re.I if "i" in r.get("flags", "") else 0)]
