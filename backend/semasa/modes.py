"""What a piece is FOR: the mode, chosen from the content and rotated (Wan, 10 Nov 2026: "make sure you rotate the mode except
gimmick, and also u choose the suitable mode based on the content, the mode also apply for post not only motion").

Five content modes, shared by Motion films and by posts: explainer, news, myth (myth vs fact), howto and case (case study). The
10-second gimmick (teaser) is not one of them and is never chosen here. A mode is picked when Wan leaves it on Auto:

  1. what the content says decides first: cue words in the headline, the brief and the source score each mode;
  2. rotation decides the rest: a mode that has just been used twice in a row is set aside when another fits nearly as well, and a
     tie goes to the mode used least recently, so a week of films and posts does not read as one shape on repeat;
  3. when the content carries no cue at all the modes simply take turns.

Nothing here invents a fact: a mode only changes how the same facts are arranged and said. Pure functions, no network."""

from __future__ import annotations

import re
from typing import Any

from .log import get_logger

log = get_logger("semasa.modes")

MODES = ("explainer", "news", "myth", "howto", "case")
AUTO = "auto"
NAMES = {"explainer": ("Penerang", "Explainer"), "news": ("Berita semasa", "Current news"),
         "myth": ("Mitos vs fakta", "Myth vs fact"), "howto": ("Cara buat", "How-to"), "case": ("Kajian kes", "Case study")}

# (cue, weight): 2 is a cue that nearly settles it, 1 a hint. Malay and English, because the headlines are both.
_CUES: dict[str, list[tuple[str, int]]] = {
    "news": [(r"terkini|baru-baru ini|baharu diumumkan|diumumkan|mengumumkan|kenyataan media|pekeliling|circular|"
              r"announce[ds]?\b|announcement|breaking|berkuat kuasa|effective (?:from|on)|dikuatkuasakan|tarik balik|recall|"
              r"withdrawn|ditarik|amaran keselamatan|safety alert|dibatalkan|cancell?ed|diharamkan|banned|warta|gazette|"
              r"pindaan|amendment|directive", 2),
             (r"notis|notice|baharu|new rule|peraturan baharu|tarikh akhir|deadline|dikemas kini|updated?\b", 1)],
    "myth": [(r"mitos|myth|salah faham|misconception|benarkah|betul ke|adakah benar|tular|viral|fact-?check|true or false|"
              r"rumou?rs?|dakwaan|tak betul|bukan benar", 2),
             (r"sebenarnya|actually|claims?\b|dakwa|kononnya|percaya|believe", 1)],
    "howto": [(r"cara |langkah|macam mana|bagaimana|how to|step[- ]by[- ]step|steps? to|senarai semak|checklist|"
               r"panduan langkah", 2),
              (r"panduan|guide|prosedur|procedure|daftar|mohon|permohonan|borang|apply|submit|proses |sediakan|prepare", 1)],
    "case": [(r"laporan kes|case report|case study|kajian kes|didakwa|prosecuted|mahkamah|court|serbuan|raid|disabit|"
              r"mengaku salah|dikompaun|compounded|dirampas|seized", 2),
             (r"\bkes\b|\bcase\b|denda|fined?\b|penguatkuasaan|enforcement|pesakit|patient|kecederaan|injur(?:y|ies)|"
              r"adverse|kesan buruk|incident|insiden", 1)],
    "explainer": [(r"apa itu|what is|what are|maksud|definisi|explain|terangkan|perbezaan|difference between", 2),
                  (r"kenapa|why |bagaimana ia|how it works|asas|basics?\b", 1)],
}
_RX = {m: [(re.compile(p, re.I), w) for p, w in cues] for m, cues in _CUES.items()}


def scores(text: str) -> dict[str, int]:
    """How strongly the words point at each mode: the weights of the cues found (each cue counts once)."""
    text = str(text or "")
    out = {}
    for mode, cues in _RX.items():
        out[mode] = sum(w for rx, w in cues if rx.search(text))
    return out


def choose(text: str, recent: list[str] | None = None) -> tuple[str, str]:
    """(mode, why) for this content. `recent` is the modes used lately, newest first (see recent_modes)."""
    recent = [m for m in (recent or []) if m in MODES]
    sc = scores(text)
    last_used = {m: (recent.index(m) if m in recent else len(recent) + 1) for m in MODES}     # bigger = longer ago
    uses = {m: recent.count(m) for m in MODES}
    top = max(sc.values())
    if top == 0:
        mode = min(MODES, key=lambda m: (uses[m], -last_used[m], MODES.index(m)))
        return mode, "rotated: nothing in the content points at one mode, so it is the turn of the one used least lately"
    near = [m for m in MODES if sc[m] >= max(1, top - 1)]
    if len(recent) >= 2 and recent[0] == recent[1] and recent[0] in near and len(near) > 1:
        near.remove(recent[0])                  # the same mode twice in a row: another that fits nearly as well gets the turn
    mode = max(near, key=lambda m: (sc[m], -uses[m], last_used[m], -MODES.index(m)))
    found = [m for m in MODES if sc[m]]
    why = ("chosen from the content" if sc[mode] == top else "rotated among the modes the content fits") \
        + f" ({', '.join(f'{m} {sc[m]}' for m in found)})"
    return mode, why


def name(mode: str, bm: bool = False) -> str:
    return NAMES.get(mode, NAMES["explainer"])[0 if bm else 1]


def recent_modes(store: Any, limit: int = 12) -> list[str]:
    """The modes used lately by films AND posts, newest first. Never raises: a store that cannot answer means no rotation
    history, which only costs the rotation, never the piece."""
    from . import db
    seen: list[tuple[str, str]] = []
    try:
        films = store.table("semasa_motions").select("options,updated_at").order("updated_at", desc=True).limit(limit)
        for r in films.execute().data or []:
            m = (r.get("options") or {}).get("mode") if isinstance(r.get("options"), dict) else None
            if m in MODES:
                seen.append((str(r.get("updated_at") or ""), m))
        ideas = store.table(db.IDEAS).select("brief,updated_at").order("updated_at", desc=True).limit(limit)
        for r in ideas.execute().data or []:
            m = (r.get("brief") or {}).get("mode") if isinstance(r.get("brief"), dict) else None
            if m in MODES:
                seen.append((str(r.get("updated_at") or ""), m))
    except Exception as exc:  # noqa: BLE001
        log.warning("recent modes not read (%s): the modes simply start their turns again", str(exc)[:120])
        return []
    return [m for _, m in sorted(seen, key=lambda x: x[0], reverse=True)][:limit]


_POST_PARTS = {
    "explainer": (
        "HOOK, then the story and the fact inside it (the number, limit, name or rule, its source named once), "
        "then the one thing most people overlook, then the one thing to do next."),
    "news": (
        "HOOK on what happened, then WHAT HAPPENED (who, what, when, with the instrument or notice named once), "
        "then WHY IT MATTERS to the reader (what it changes, the deadline or the thing to check, what getting it "
        "wrong costs), then what to do now."),
    "myth": (
        "HOOK that states the myth the way people say it, then the MYTH (someone who acted on it), then the FACT "
        "that corrects it (the rule, study or notice that decides it, named once), then why people believe it, "
        "then what to do."),
    "howto": (
        "HOOK on the result the reader wants, then the STEPS in order (three or four short actions with the real "
        "values: the limit, the form, the deadline), then the MISTAKES that cost people most at those steps, "
        "then the next step."),
    "case": (
        "HOOK on the case, then THE CASE (what happened to a real product, person or company, who did what, what "
        "was found, what was done about it), then WHAT THE RULE SAYS (the instrument that decided it and why the "
        "outcome followed), then the lesson for the reader."),
}


def post_block(mode: str, stream: str = "regulab") -> str:
    """What the writer is told about the shape of THIS post (Wan: the mode applies to posts too). Every other rule in the prompt
    still outranks it: the voice, the compliance checks, the source rules, no invented figure."""
    if mode not in MODES:
        return ""
    voice = "a named chemist writing to peers" if stream == "linkedin" else "the brand speaking to SME owners"
    return (f"\n\nMODE OF THIS POST: {NAMES[mode][1]}. Arrange the SAME facts as {_POST_PARTS[mode]} Say it as {voice}; a mode "
            "changes the arrangement only, never the voice, never a rule above, and it never licenses a number, date, clause or "
            "case the source does not carry. In a thread of several posts, the posts follow these parts in order.\n")
