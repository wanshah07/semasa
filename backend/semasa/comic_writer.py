"""The comic's script: written from Wan's idea, or typed by him, and judged by the same rules either way.

A script is four panels of one or two speech bubbles between the two people of a series (comic_library.py). The writer
works under the rules every artwork is written under (design.COMMON: no call to action, no URL, no social source, no fact
the brief does not give, the source named apart from the words) and in the stream's voice (design.VOICE). What comes back
is checked before a single picture is paid for:

  * its shape (comic.check: four panels, one or two bubbles, each person once a panel, a bubble short enough to read);
  * the post rules over the title and every bubble (compliance.scan, as for a poster's words), the vague-wording rule
    (compliance.vague_hits, over the title and the bubbles in reading order) and, on LinkedIn, that it is in English;
  * for a script the writer wrote: every figure in it must be in the brief (a number the brief never gave is invented).

A script that fails is asked for once more with the reason, then refused with that reason, which the page shows. A script
Wan typed is checked the same way, except for the figures: his own words are his own source.
"""

from __future__ import annotations

import re
from typing import Any

from . import antislop, comic, comic_library, compliance, design
from .llm import LLM
from .log import get_logger

log = get_logger("semasa.comic_writer")

LANG = {"regulab": "bm", "linkedin": "en"}
_FIGURE = re.compile(r"\d+(?:[.,/]\d+)*")
_SOURCE_LABEL = re.compile(r"^\s*(sumber|source|rujukan)\s*:", re.I)

SHAPE = """THE PAGE. Exactly 4 panels, read top left, top right, bottom left, bottom right.
- Panel 1 raises the question or the wrong belief, the way a real person would say it. Panels 2 and 3 work it out. Panel 4
  lands on the answer the BRIEF gives. It never ends on an invitation, an offer or a call to action.
- Each panel has 1 or 2 speech bubbles. Each character speaks at most once in a panel. A bubble has at most {chars}
  characters, spaces included; under 70 reads best. Natural spoken sentences, one thought a bubble.
- No narrator boxes, no sound effects, no thought bubbles. A name of an instrument, a clause number or a figure appears in a
  bubble only if the BRIEF gives it, copied exactly as the BRIEF writes it. If the BRIEF gives no figure, the comic has none.
- "title": the poster's headline above the comic: the question or the wrong belief in at most 9 words and {title}
  characters. No asterisks anywhere (rule 6 above does not apply to a comic).
- "scene": for each panel, ONE English sentence for the illustrator: what A and B are doing and feeling (posture, gesture,
  expression, a prop in a hand). A is always on the left and B on the right. Never ask for text, a sign, a label, a logo
  or a brand name in a scene; a real mark (a halal logo, a regulator's logo) is never drawn: describe a plain unmarked
  emblem instead.
- "setting": "" to use the series' usual place, or ONE English sentence when this episode needs another place or a prop.
- "citation": the regulator and instrument the comic rests on, exactly as the BRIEF names it, or "" when it names none.

Answer with ONE JSON object only:
{{"title": "...", "setting": "", "panels": [{{"scene": "...", "lines": [{{"who": "A", "text": "..."}}, {{"who": "B",
"text": "..."}}]}}, {{...}}, {{...}}, {{...}}], "citation": "..."}}"""


def _flat(value: Any) -> str:
    return " ".join(str(value or "").split())


def _words_only(value: Any) -> str:
    """One bubble or the title as plain words: no emphasis marks (the lettering has none) and no line breaks."""
    return _flat(str(value or "").replace("*", ""))


def lang_of(stream: str) -> str:
    return LANG.get(stream, "bm")


def source_line(source: str, stream: str) -> str:
    """What is printed under the comic: "Sumber: ..." ("Source: ..." in English). A source typed with its own label keeps it."""
    source = _flat(source)
    if not source or _SOURCE_LABEL.match(source):
        return source
    return f"{'Source' if lang_of(stream) == 'en' else 'Sumber'}: {source}"


def assemble(raw: Any, series: dict[str, Any], stream: str, source: str = "") -> dict[str, Any]:
    """The script as it is drawn, from what the writer or Wan gave: {title, source, setting, cast, names, lang, panels}. The
    cast is ALWAYS the series' own words (comic_library.cast_of), whatever the input carried, so every episode describes
    the two people identically. A speaker given by name becomes A or B. Raises comic.ComicError naming what is wrong."""
    if not isinstance(raw, dict):
        raise comic.ComicError("there is no script: write the four panels, or give an idea for Semasa to write from")
    names = comic_library.names_of(series)
    by_name = {v.casefold(): k for k, v in names.items()}
    panels = []
    for panel in raw.get("panels") if isinstance(raw.get("panels"), list) else []:
        panel = panel if isinstance(panel, dict) else {}
        lines = []
        for line in panel.get("lines") if isinstance(panel.get("lines"), list) else []:
            if not isinstance(line, dict) or not _words_only(line.get("text")):
                continue                                   # an empty second bubble in the form is no bubble
            who = _flat(line.get("who"))
            who = who.upper() if who.upper() in comic.SPEAKERS else by_name.get(who.casefold(), who)
            lines.append({"who": who, "text": _words_only(line.get("text"))})
        panels.append({"scene": _flat(panel.get("scene"))[:comic.LIMITS["scene"]], "lines": lines})
    script = {"title": _words_only(raw.get("title")), "source": source_line(source, stream),
              "setting": _flat(raw.get("setting"))[:comic.LIMITS["setting"]] or series.get("setting") or "",
              "cast": comic_library.cast_of(series), "names": names, "lang": lang_of(stream), "panels": panels}
    if not script["title"]:
        raise comic.ComicError("the comic needs a title")
    comic.check(script)
    comic.bubbles(script)             # the words must also fit Semasa's own lettering: that is what a comic falls back to
    comic.layout(script)              # ... and the title and the source must fit the frame
    return script


def units(script: dict[str, Any]) -> list[str]:
    """The comic's words in reading order: the title, then every bubble."""
    return [script.get("title") or ""] + [line["text"] for panel in script["panels"] for line in panel["lines"]]


def artwork(script: dict[str, Any]) -> list[dict[str, Any]]:
    """The comic's words in the shape a design's words are kept in (meta.slides), so a post the comic is attached to has
    them judged like any artwork's: the title, then one entry a panel."""
    return [{"title": script.get("title") or "", "points": []}] + [
        {"title": "", "points": [line["text"] for line in panel["lines"]]} for panel in script["panels"]]


def flags(script: dict[str, Any], stream: str, brand: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """[{hard, where, msg}] for a script, by the rules a post's artwork is judged by. `where` is "Comic title", "Comic panel
    N", "Source" or "Comic"."""
    art = artwork(script)
    # normalise_slides drops an entry with no words, so each kept entry carries its own name
    labels = [("Comic title" if n == 0 else f"Comic panel {n}") for n, it in enumerate(art) if it["title"] or it["points"]]
    found = compliance.scan({"stream": stream, "citation": script.get("source") or "", "media": [{"artwork": art}]},
                            brand=brand)
    out = []
    for f in found:
        m = re.match(r"^Design \d+, slide (\d+)$", f["where"])
        if m:
            n = int(m.group(1)) - 1
            out.append({**f, "where": labels[n] if n < len(labels) else "Comic"})
        elif f["where"] == "Source":
            out.append(f)
    for phrase in compliance.vague_hits(units(script)):
        out.append({"hard": True, "where": "Comic",
                    "msg": f'vague: "{phrase}". {compliance.VAGUE_FIX} in that bubble or the two after it.'})
    text = "\n".join(units(script))
    if stream == "linkedin" and compliance.NOT_ENGLISH.search(text):
        out.append({"hard": True, "where": "Comic", "msg": "reads as Bahasa Malaysia. The LinkedIn stream is English: write "
                                                           "the comic in English."})
    if re.search(r"[\u2014\u2013]", text):
        out.append({"hard": True, "where": "Comic", "msg": "an em dash. Use a full stop or a comma."})
    return out


def refusal(found: list[dict[str, Any]]) -> str:
    """The hard flags as one sentence for the page, or "" when nothing blocks."""
    hard = [f for f in found if f["hard"]]
    return "; ".join(f"{f['where']}: {f['msg']}" for f in hard[:4])


def unsourced_figures(script: dict[str, Any], given: str) -> list[str]:
    """Figures in the title or a bubble that the brief (and the source Wan typed) never gave. A writer that puts "30 hari"
    in a bubble when the brief has no 30 has invented it."""
    known = set(_FIGURE.findall(given or ""))
    known |= {part for token in list(known) for part in re.split(r"[.,/]", token)}
    out: list[str] = []
    for token in _FIGURE.findall("\n".join(units(script))):
        if token not in known and not all(part in known for part in re.split(r"[.,/]", token)) and token not in out:
            out.append(token)
    return out


def system_prompt(stream: str, series: dict[str, Any]) -> str:
    def person(who: str, default: str) -> str:
        p = series["cast"][who]
        return (f"Character {who} is {p['name']}: {p.get('role') or default}. How {who} speaks: "
                f"{p.get('voice') or 'plainly'}.\n")
    return (f"You write the script of a four-panel dialogue comic for social media: two fixed characters talk one regulatory "
            f"question through. {design.VOICE.get(stream, design.VOICE['regulab'])}\n\n"
            f"THE SERIES \"{series['name']}\". The same two people appear in every episode.\n"
            + person("A", "the one who asks") + person("B", "the one who answers")
            + "These notes describe each person's manner, whatever language the notes are in; the bubbles are in the language "
            "named above. A character never says the company's name, and nobody is a mascot or a spokesperson.\n\n"
            f"{design.COMMON}\n\n"
            + SHAPE.format(chars=comic.MAX_CHARS, title=comic.MAX_TITLE) + antislop.prompt_block())


def _tidy(out: dict[str, Any]) -> dict[str, Any]:
    """The writer's answer with the machine-safe slop taken out of every public word (antislop.clean) and nothing else changed."""
    panels = []
    for panel in out.get("panels") if isinstance(out.get("panels"), list) else []:
        panel = panel if isinstance(panel, dict) else {}
        lines = [{"who": line.get("who"), "text": antislop.clean(_words_only(line.get("text")))}
                 for line in (panel.get("lines") if isinstance(panel.get("lines"), list) else []) if isinstance(line, dict)]
        panels.append({"scene": _flat(panel.get("scene")), "lines": lines})
    return {"title": antislop.clean(_words_only(out.get("title"))), "setting": _flat(out.get("setting")), "panels": panels,
            "citation": _flat(out.get("citation"))[:comic.MAX_SOURCE]}


def write(llm: LLM | None, brief: str, stream: str, series: dict[str, Any], *, source: str = "",
          note: str = "", brand: dict[str, Any] | None = None) -> dict[str, Any]:
    """The script written from Wan's idea: {title, setting, panels, citation}, already checked. Raises comic.ComicError with
    the reason for the page when the writer is off, does not answer, or twice returns a script that breaks a rule."""
    brief = str(brief or "").strip()
    if not brief:
        raise comic.ComicError("there is no idea to write the comic from: give an idea, or write the script yourself")
    if not llm or not llm.configured:
        raise comic.ComicError("the writer is off, so the script cannot be written from the idea: "
                               + (llm.why_off() if llm else "no writer") + ". Write the script yourself instead.")
    system = system_prompt(stream, series)
    user = f"BRIEF (Wan's idea or prompt):\n{brief[:4000]}"
    if source.strip():
        user += f"\n\nSOURCE Wan named (printed under the comic; a bubble may name it): {source.strip()[:comic.MAX_SOURCE]}"
    if note.strip():
        user += f"\n\nChanges Wan asked for on the last version: {note.strip()[:600]}"
    why = ""
    for _ in range(2):
        ask = user + (f"\n\nYour last script was refused: {why}. Write it again and fix exactly that." if why else "")
        out = llm.chat_json(system, ask, max_tokens=2200)
        if not isinstance(out, dict):
            raise comic.ComicError("the writer did not answer (see the run log): press Retry, or write the script yourself")
        written = _tidy(out)
        try:
            script = assemble(written, series, stream, source or written["citation"])
        except comic.ComicError as exc:
            why = str(exc)
            continue
        why = refusal(flags(script, stream, brand))
        if not why:
            extra = unsourced_figures(script, f"{brief}\n{source}\n{note}")
            if extra:
                why = (f"it gives a figure the brief does not ({', '.join(extra[:4])}): a comic states only what the "
                       "brief states")
        if not why:
            return written
        log.info("comic script refused (%s); asked again", why[:160])
    raise comic.ComicError(f"the script was refused twice: {why}. Change the idea, or write the script yourself.")
