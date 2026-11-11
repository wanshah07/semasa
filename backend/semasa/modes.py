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

# Wan, 11 Nov 2026: "make as many model for motion as you can" (film modes and formats). Five original modes and eight more:
# every one is the same four teaching scenes (hook, the two scenes that mode is about, the closing card), so a mode changes what
# scenes 2 and 3 are FOR and never the machinery. The new ones follow `case`, so the tie-breaks of the original five do not move.
MODES = ("explainer", "news", "myth", "howto", "case",
         "compare", "change", "define", "decide", "mistake", "checklist", "number", "qna")
AUTO = "auto"
NAMES = {"explainer": ("Penerang", "Explainer"), "news": ("Berita semasa", "Current news"),
         "myth": ("Mitos vs fakta", "Myth vs fact"), "howto": ("Cara buat", "How-to"), "case": ("Kajian kes", "Case study"),
         "compare": ("Banding", "Compare"), "change": ("Apa berubah", "What changed"),
         "define": ("Maksud istilah", "Term explained"),
         "decide": ("Boleh ke tak?", "Can I or can't I"), "mistake": ("Kesilapan biasa", "Common mistake"),
         "checklist": ("Senarai semak", "Checklist"), "number": ("Satu nombor", "One number"), "qna": ("Soal jawab", "Q&A")}

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
    "howto": [(r"cara |langkah|macam mana|bagaimana|how to|step[- ]by[- ]step|steps? to|panduan langkah", 2),
              (r"panduan|guide|prosedur|procedure|daftar|mohon|permohonan|borang|apply|submit|proses |sediakan|prepare", 1)],
    "case": [(r"laporan kes|case report|case study|kajian kes|didakwa|prosecuted|mahkamah|court|serbuan|raid|disabit|"
              r"mengaku salah|dikompaun|compounded|dirampas|seized", 2),
             (r"\bkes\b|\bcase\b|denda|fined?\b|penguatkuasaan|enforcement|pesakit|patient|kecederaan|injur(?:y|ies)|"
              r"adverse|kesan buruk|incident|insiden", 1)],
    "explainer": [(r"apa itu|what is|what are|maksud|definisi|explain|terangkan|perbezaan|difference between", 2),
                  (r"kenapa|why |bagaimana ia|how it works|asas|basics?\b", 1)],
    # the new modes: strong cues are specific phrases, so none of them takes a piece the original five already fit
    "compare": [(r"\bvs\.?\b|versus|berbanding|dibanding|bandingkan|compare[sd]?\b|comparison|mana (?:lebih )?(?:baik|bagus)|"
                 r"better than|pilih (?:mana|yang)|atau\b.{0,25}\?", 2),
                (r"kelebihan dan kekurangan|pros and cons|beza antara|bezanya", 1)],
    "change": [(r"sebelum ini.{0,40}(?:kini|sekarang)|dahulu.{0,40}(?:kini|sekarang)|kini.{0,30}sebelum|before.{0,40}\bnow\b|"
                r"previously.{0,60}now|old rule|new rule|peraturan lama|peraturan baharu|replaces?\b|menggantikan|diganti|"
                r"revised|disemak semula|kemas kini peraturan", 2),
               (r"berubah|changes?\b|perubahan|tidak lagi|no longer|mulai|starting from", 1)],
    "define": [(r"apa maksud|singkatan|stands? for|what does .{1,40} mean|definition of|apa erti|istilah", 3),
               (r"terminologi|jargon|glossary|glosari|bermaksud", 2),
               (r"\bmaksudnya\b|bermakna|means\b", 1)],
    "decide": [(r"boleh (?:ke|tak|kah)\b|bolehkah|adakah boleh|dibenarkan(?:kah)?|tak boleh|tidak boleh|can i\b|can you\b|"
               r"is it (?:legal|allowed|okay|ok)|are we allowed|allowed to|haram ke|halal ke|wajib ke|perlu ke", 2),
              (r"dibenarkan|dilarang|permitted|prohibited|larangan", 1)],
    "mistake": [(r"kesilapan|silap|common mistake|mistakes?\b|jangan buat|elak(?:kan)?\b|avoid\b|biasa tersilap|"
                 r"ditolak sebab|ditolak kerana|rejected because|kenapa ditolak|why .{0,30}rejected", 2),
                (r"tersilap|salah buat|wrong\b|pitfall|perangkap|ralat", 1)],
    "checklist": [(r"senarai semak|checklist|semak sebelum|check before|sebelum (?:hantar|mohon|mendaftar|eksport|jual)|"
                   r"before (?:you )?(?:submit|apply|register|export|launch)|pastikan (?:anda )?ada", 2),
                  (r"dokumen diperlukan|required documents|keperluan|requirements?\b|syarat", 1)],
    "number": [(r"berapa (?:banyak|ramai|had|kadar|peratus)|how (?:many|much)\b|statistik|statistics?\b|data menunjukkan|"
                r"data shows?|nombor (?:sebenar|sebenarnya)|the number", 2),
               (r"\d[\d.,]*\s?(?:%|peratus|percent|ppm|mg|ug|µg|ml|kg|ribu|juta|million|billion|bilion)|\brm\s?\d[\d.,]*|"
                r"\b\d{1,3}(?:,\d{3})+\b|\bhad\b|\blimit\b|kadar|jumlah", 1)],
    "qna": [(r"soalan lazim|\bfaq\b|frequently asked|soal jawab|q ?& ?a|\bq:|tanya (?:jawab|pakar)|ask the expert|"
             r"ramai (?:tanya|bertanya)|many (?:people )?ask", 2),
            (r"ditanya|asked\b|soalan|question\b", 1)],
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
    "compare": (
        "HOOK on the choice, then the TWO OPTIONS side by side (each with its real value: the limit, the cost, the "
        "requirement, the rule, the source named once), then WHICH FITS WHOM and the fact that decides it, then what to do."),
    "change": (
        "HOOK on what changed, then BEFORE AND NOW (the old rule or practice and the new one with the real values and the "
        "date it takes effect, the instrument named once), then WHAT TO DO about it before the date."),
    "define": (
        "HOOK on the term, then WHAT IT MEANS (one plain sentence, an everyday comparison, the real definition or limit with "
        "its source named once), then WHERE THE READER MEETS IT (a label, a form, a certificate) and the usual mix-up."),
    "decide": (
        "HOOK that asks the question the reader really has, then THE STRAIGHT ANSWER (yes, no or yes only if, with the real "
        "condition and the rule named once), then THE EXCEPTION where the answer flips or the line not to cross."),
    "mistake": (
        "HOOK on the mistake, then THE MISTAKE (someone who made it and what it cost them, with the real fact and its source "
        "named once), then THE RIGHT WAY and the rule that says so, then the next step."),
    "checklist": (
        "HOOK on what is about to be done, then THE CHECK (three or four short checkable items with the real values: the "
        "limit, the document, the deadline), then THE ONE MOST OFTEN MISSED and what skipping it costs."),
    "number": (
        "HOOK on the one number, then THE NUMBER (what exactly it counts, who it covers, where it comes from, the source "
        "named once), then WHAT IT MEANS in practice and the context that stops it being misread."),
    "qna": (
        "HOOK worded as the question people really ask, then THE QUESTION (who asks it and why it worries them), then THE "
        "ANSWER with the real fact and its source named once, then the follow-up that always comes next and its answer."),
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
